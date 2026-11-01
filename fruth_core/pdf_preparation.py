"""Owned PDF preparation transport. No PDF library is imported in this process."""
from __future__ import annotations

import base64
import codecs
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
from typing import Callable
import uuid
import zlib

from fruth_runtime.child_process_env import sanitized_child_process_env

MIB = 1024 * 1024
PROTOCOL = 'fruth.pdf_preparation'
VERSION = 1
POLL_SECONDS = .05
TERMINATE_GRACE_SECONDS = .25
REAP_SECONDS = 3.0
SUPERVISOR_EXIT_SECONDS = 2 * REAP_SECONDS + TERMINATE_GRACE_SECONDS + 2
MAX_MANIFEST_BYTES = MIB
MAX_DIAGNOSTIC_BYTES = 16 * 1024
MAX_IMAGE_SIDE = 6000
_CANCELLED: ContextVar[Callable[[], bool] | None] = ContextVar('pdf_cancelled', default=None)


class PdfPreparationError(RuntimeError):
    """Infrastructure/limit/cancellation failure; never an empty-PDF fallback."""
    def __init__(self, code: str, message: str, *, operation: str = ''):
        super().__init__(message)
        self.code, self.operation = code, operation
        self.status_code = {'PDF_PREPARATION_TIMEOUT': 504, 'PDF_PREPARATION_BUSY': 429,
                            'PDF_PREPARATION_CANCELLED': 409, 'PDF_PREPARATION_LIMIT': 413}.get(code, 502)

    @classmethod
    def from_response(cls, payload):
        """Preserve preparation failures across the internal HTTP/materialization seam."""
        info = payload.get('pdf_preparation') if isinstance(payload, dict) else None
        if (not isinstance(info, dict) or info.get('status') != 'failed'
                or not str(info.get('code', '')).startswith('PDF_PREPARATION_')):
            return None
        error = cls(info['code'], str(payload.get('error') or 'PDF preparation failed.'),
                    operation=str(info.get('operation') or ''))
        error.pdf_evidence = {key: payload[key] for key in
            ('pdf_preparation', 'pdf_source', 'pdf_total_pages', 'pdf_processed_pages', 'warnings') if key in payload}
        return error


@dataclass(frozen=True)
class PdfLimits:
    timeout_sec: float = 120.0
    admission_timeout_sec: float = 5.0
    workers: int = 1
    input_bytes: int = 100 * MIB
    result_bytes: int = 160 * MIB
    output_bytes: int = 256 * MIB
    text_bytes: int = 16 * MIB

    def __post_init__(self):
        for key, value in asdict(self).items():
            if key.endswith('_sec'):
                valid = type(value) in (int, float) and math.isfinite(value) and value > 0
            else:
                valid = type(value) is int and value > 0
            if not valid:
                raise ValueError(f'Invalid PDF preparation limit: {key}')

    @classmethod
    def from_environment(cls):
        values = {}
        for name, default in asdict(cls()).items():
            raw = os.environ.get('FRUTH_PDF_' + name.upper())
            if raw is not None:
                values[name] = float(raw) if name.endswith('_sec') else int(raw)
        return cls(**values)


@contextmanager
def pdf_cancellation_scope(cancelled: Callable[[], bool]):
    """Trusted in-process branch authority, never a user payload callback."""
    token = _CANCELLED.set(cancelled)
    try:
        yield
    finally:
        _CANCELLED.reset(token)


def check_cancelled():
    callback = _CANCELLED.get()
    if callback is not None and callback():
        raise PdfPreparationError('PDF_PREPARATION_CANCELLED', 'PDF preparation was cancelled by its branch control.')


def check_progress(deadline=None):
    check_cancelled()
    if deadline is not None and time.monotonic() >= deadline:
        raise PdfPreparationError('PDF_PREPARATION_TIMEOUT', 'PDF preparation deadline exceeded.')


def json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def load_json(path: Path, limit=MAX_MANIFEST_BYTES):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate PDF protocol key')
            result[key] = value
        return result
    with open_regular(path) as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('PDF protocol message exceeds its named budget')
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def open_regular(path: Path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('PDF result must be a private regular file')
        return os.fdopen(fd, 'rb')
    except BaseException:
        os.close(fd)
        raise


def checked_controls(operation, controls):
    expected = {'text': {'max_chars'}, 'render': {'max_pages', 'dpi', 'max_image_side_px'},
                'page': {'page_index', 'dpi', 'max_image_side_px', 'crop_margin_ratio'}}
    if operation not in expected or set(controls) != expected[operation]:
        raise ValueError('Invalid PDF preparation operation/controls')
    for key in ('max_chars', 'max_pages'):
        value = controls.get(key)
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError(f'Invalid PDF {key}')
    if operation != 'text':
        if (type(controls['dpi']) not in (int, float) or not math.isfinite(controls['dpi'])
                or not 0 < controls['dpi'] <= 600 or type(controls['max_image_side_px']) is not int
                or not 0 < controls['max_image_side_px'] <= MAX_IMAGE_SIDE):
            raise ValueError('PDF DPI/image side exceeds supported geometry bounds')
    if operation == 'page':
        ratio = controls['crop_margin_ratio']
        if (type(controls['page_index']) is not int or type(ratio) not in (int, float)
                or not math.isfinite(ratio)):
            raise ValueError('Invalid PDF page index/crop')
    return dict(controls)


def _png_dimensions(stream, size, deadline=None):
    """Stream-check PNG framing, CRCs and bounded scanlines; no native decoder."""
    if stream.read(8) != b'\x89PNG\r\n\x1a\n':
        raise ValueError('PDF result is not PNG')
    position, dimensions, saw_data = 8, None, False
    decoder, decoded_size, row_size, expected_size = zlib.decompressobj(), 0, 0, 0

    def scanlines(block):
        nonlocal decoded_size
        if decoded_size + len(block) > expected_size:
            raise ValueError('PNG expands beyond its dimensions')
        if any(block[i] > 4 for i in range((-decoded_size) % row_size, len(block), row_size)):
            raise ValueError('Invalid PNG row filter')
        decoded_size += len(block)
    while position < size:
        check_progress(deadline)
        header = stream.read(8)
        if len(header) != 8:
            raise ValueError('Truncated PNG chunk')
        length, kind = struct.unpack('>I4s', header)
        if length > size - position - 12:
            raise ValueError('PNG length mismatch')
        if kind == b'IHDR' and (position != 8 or length != 13):
            raise ValueError('Invalid PNG IHDR')
        crc, remaining, first = zlib.crc32(kind), length, b''
        while remaining:
            check_progress(deadline)
            block = stream.read(min(MIB, remaining))
            if not block:
                raise ValueError('Truncated PNG')
            if kind == b'IHDR':
                first += block
            if kind == b'IDAT':
                if not dimensions:
                    raise ValueError('PNG image data precedes dimensions')
                pending = block
                while pending:
                    check_progress(deadline)
                    scanlines(decoder.decompress(pending, MIB))
                    pending = decoder.unconsumed_tail
                if decoder.unused_data:
                    raise ValueError('Extra compressed PNG data')
            crc = zlib.crc32(block, crc)
            remaining -= len(block)
        raw_crc = stream.read(4)
        if len(raw_crc) != 4 or struct.unpack('>I', raw_crc)[0] != crc:
            raise ValueError('PNG CRC mismatch')
        if position == 8:
            if kind != b'IHDR' or length != 13:
                raise ValueError('PNG has no initial IHDR')
            dimensions = struct.unpack('>II', first[:8])
            width, height = dimensions
            depth, color, compression, filtering, interlace = first[8:]
            allowed = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
            if (not 0 < width <= MAX_IMAGE_SIDE or not 0 < height <= MAX_IMAGE_SIDE
                    or depth not in allowed.get(color, ()) or compression or filtering or interlace):
                raise ValueError('Unsupported PDF PNG geometry/encoding')
            channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
            row_size = (width * depth * channels + 7) // 8 + 1
            expected_size = row_size * height
        elif kind == b'IHDR':
            raise ValueError('Duplicate PNG IHDR')
        saw_data |= kind == b'IDAT'
        position += length + 12
        if kind == b'IEND':
            if length or position != size or not saw_data:
                raise ValueError('Incomplete/extra PNG data')
            if not decoder.eof or decoder.unused_data or decoded_size != expected_size:
                raise ValueError('Incomplete PNG scanlines')
            return dimensions
    raise ValueError('PNG has no IEND')


def accept_result(directory: Path, request: dict, limits: PdfLimits, *, deadline=None):
    check_progress(deadline)
    results = directory / 'results'
    if results.is_symlink() or not results.is_dir():
        raise ValueError('PDF result directory is missing or redirected')
    manifest = load_json(results / 'manifest.json')
    fields = {'protocol', 'version', 'invocation_id', 'request_sha256', 'source_sha256',
              'operation', 'controls', 'status', 'total_pages', 'selected_pages', 'warnings', 'files'}
    if not isinstance(manifest, dict) or set(manifest) != fields:
        raise ValueError('Incomplete/extra PDF result manifest fields')
    for key in ('protocol', 'version', 'invocation_id', 'source_sha256', 'operation', 'controls'):
        if json_bytes(manifest[key]) != json_bytes(request[key]):
            raise ValueError(f'PDF result identity mismatch: {key}')
    if manifest['request_sha256'] != digest_bytes(json_bytes(request)):
        raise ValueError('PDF result request digest mismatch')
    total, selected = manifest['total_pages'], manifest['selected_pages']
    if type(total) is not int or total < 0 or not isinstance(selected, list) or any(type(i) is not int for i in selected):
        raise ValueError('Invalid PDF page counts/indices')
    if manifest['status'] not in {'complete', 'unreadable'}:
        raise ValueError('PDF preparation is incomplete')
    warnings = manifest['warnings']
    if not isinstance(warnings, list) or any(not isinstance(w, str) for w in warnings):
        raise ValueError('Invalid PDF warnings')
    files = manifest['files']
    if not isinstance(files, list):
        raise ValueError('Invalid PDF file manifest')
    operation, controls = request['operation'], request['controls']
    if manifest['status'] == 'unreadable':
        expected_pages, expected_names = [], []
    elif operation == 'text':
        if len(selected) != total:
            raise ValueError('PDF selected page coverage mismatch')
        expected_pages, expected_names = list(range(total)), ['text.txt']
    else:
        if operation == 'page':
            index = controls['page_index']
            expected_pages = [index] if 0 <= index < total else []
        else:
            count = total if controls['max_pages'] is None else min(total, controls['max_pages'])
            if len(selected) != count:
                raise ValueError('PDF selected page coverage mismatch')
            expected_pages = list(range(count))
        expected_names = [f'page-{index:08d}.png' for index in expected_pages]
    if selected != expected_pages or len(files) != len(expected_names):
        raise ValueError('PDF selected page coverage mismatch')
    if {p.name for p in results.iterdir()} != {'manifest.json', *expected_names}:
        raise ValueError('Missing/extra PDF output files')
    loaded, output_size = [], 0
    streams = []
    for index, (record, name) in enumerate(zip(files, expected_names)):
        check_progress(deadline)
        fields = {'name', 'size_bytes', 'sha256', 'page_index', 'width', 'height'}
        if not isinstance(record, dict) or set(record) != fields or record['name'] != name:
            raise ValueError('PDF output name/order mismatch')
        size = record['size_bytes']
        ceiling = min(limits.result_bytes, limits.text_bytes) if operation == 'text' else limits.result_bytes
        if type(size) is not int or not 0 <= size <= ceiling:
            raise ValueError('PDF output size exceeds budget')
        output_size += size
        if output_size > limits.output_bytes:
            raise ValueError('PDF aggregate output exceeds budget')
        with open_regular(results / name) as stream:
            if os.fstat(stream.fileno()).st_size != size:
                raise ValueError('PDF output length mismatch')
            digest, decoder, chars = hashlib.sha256(), codecs.getincrementaldecoder('utf-8')(), 0
            while block := stream.read(MIB):
                check_progress(deadline)
                digest.update(block)
                if operation == 'text':
                    chars += len(decoder.decode(block))
            if digest.hexdigest() != record['sha256']:
                raise ValueError('PDF output digest mismatch')
            stream.seek(0)
            if operation == 'text':
                chars += len(decoder.decode(b'', final=True))
                if any(record[k] is not None for k in ('page_index', 'width', 'height')):
                    raise ValueError('Text result has image fields')
                if controls['max_chars'] is not None and chars > controls['max_chars']:
                    raise ValueError('Text result exceeds explicit character budget')
            else:
                width, height = _png_dimensions(stream, size, deadline)
                if (record['page_index'] != selected[index] or type(record['page_index']) is not int
                        or type(record['width']) is not int or type(record['height']) is not int
                        or (width, height) != (record['width'], record['height'])
                        or not 0 < width <= controls['max_image_side_px']
                        or not 0 < height <= controls['max_image_side_px']):
                    raise ValueError('PDF PNG dimensions/page binding mismatch')
        streams.append((name, size, record['sha256']))
    # Every result validated and aggregate budget proved before materialization.
    check_progress(deadline)
    for name, size, digest in streams:
        check_progress(deadline)
        with open_regular(results / name) as stream:
            raw = stream.read(size + 1)
        if len(raw) != size or digest_bytes(raw) != digest:
            raise ValueError('PDF result changed after validation')
        loaded.append(raw.decode('utf-8') if operation == 'text' else base64.b64encode(raw).decode('ascii'))
    check_progress(deadline)
    return loaded, total, warnings


class PdfPreparation:
    def __init__(self, limits: PdfLimits):
        self.limits = limits
        self.capacity = threading.BoundedSemaphore(limits.workers)

    def _supervisor_command(self, directory):
        return [sys.executable, '-I', '-B', str(Path(__file__).with_name('pdf_worker.py')),
                'supervise', str(directory)]

    @staticmethod
    def _stop(process):
        try:
            process.stdin.write(b'C')
            process.stdin.flush()
        except (BrokenPipeError, OSError):
            pass

    @staticmethod
    def _finish(process, directory, invocation):
        try:
            process.wait(timeout=SUPERVISOR_EXIT_SECONDS)
            receipt = load_json(directory/'supervisor.json', MAX_DIAGNOSTIC_BYTES)
            if (not isinstance(receipt, dict) or receipt.get('invocation_id') != invocation
                    or receipt.get('reaped') is not True or receipt.get('group_cleaned') is not True):
                raise ValueError('Missing bound cleanup confirmation')
            return receipt
        except (subprocess.TimeoutExpired, OSError, ValueError, TypeError) as exc:
            raise PdfPreparationError('PDF_PREPARATION_CLEANUP_UNCONFIRMED',
                f'PDF cleanup unconfirmed; capacity and workspace retained at {directory}.') from exc

    def run(self, pdf_path: Path, operation: str, controls: dict):
        controls = checked_controls(operation, controls)
        admitted_until = time.monotonic() + self.limits.admission_timeout_sec
        while True:
            check_cancelled()
            if self.capacity.acquire(timeout=min(POLL_SECONDS, max(0, admitted_until-time.monotonic()))):
                break
            if time.monotonic() >= admitted_until:
                raise PdfPreparationError('PDF_PREPARATION_BUSY', 'PDF preparation capacity is busy; retry later.', operation=operation)
        directory, process, cleaned, invocation = None, None, True, None
        deadline = time.monotonic() + self.limits.timeout_sec
        try:
            check_cancelled()
            directory = Path(tempfile.mkdtemp(prefix='fruth-pdf-'))
            # macOS TMPDIR commonly uses /var -> /private/var. Pass the owned
            # physical workspace consistently to the strict child entrypoint.
            directory = directory.resolve(strict=True)
            digest, size = hashlib.sha256(), 0
            with open_regular(Path(pdf_path)) as source, (directory/'source.pdf').open('xb') as target:
                if os.fstat(source.fileno()).st_size > self.limits.input_bytes:
                    raise PdfPreparationError('PDF_PREPARATION_LIMIT', 'PDF input exceeds FRUTH_PDF_INPUT_BYTES.')
                while block := source.read(MIB):
                    check_cancelled()
                    if time.monotonic() >= deadline:
                        raise PdfPreparationError('PDF_PREPARATION_TIMEOUT', 'PDF input staging exceeded the preparation deadline.')
                    size += len(block)
                    if size > self.limits.input_bytes:
                        raise PdfPreparationError('PDF_PREPARATION_LIMIT', 'PDF input exceeds FRUTH_PDF_INPUT_BYTES.')
                    target.write(block)
                    digest.update(block)
            (directory/'source.pdf').chmod(0o400)
            request = dict(protocol=PROTOCOL, version=VERSION, invocation_id=uuid.uuid4().hex,
                           source_sha256=digest.hexdigest(), source_bytes=size,
                           operation=operation, controls=controls, limits=asdict(self.limits), deadline=deadline)
            (directory/'request.json').write_bytes(json_bytes(request))
            (directory/'request.json').chmod(0o400)
            invocation = request['invocation_id']
            env = sanitized_child_process_env()
            scratch = directory/'scratch'
            scratch.mkdir(mode=0o700)
            env.update(TMPDIR=str(scratch), TMP=str(scratch), TEMP=str(scratch))
            process = subprocess.Popen(self._supervisor_command(directory),
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                close_fds=True, env=env, cwd=directory, start_new_session=True)
            cleaned = False
            pending_error = None
            while process.poll() is None:
                try:
                    check_cancelled()
                    if time.monotonic() >= deadline:
                        raise PdfPreparationError('PDF_PREPARATION_TIMEOUT', 'PDF preparation deadline exceeded.')
                except BaseException as exc:
                    pending_error = exc
                    self._stop(process)
                    break
                time.sleep(POLL_SECONDS)
            receipt = self._finish(process, directory, invocation)
            cleaned = True
            if pending_error is not None:
                raise pending_error
            if process.returncode or receipt.get('worker_exit') != 0 or receipt.get('reason') != 'worker_exit':
                code = receipt.get('error_code') or 'PDF_PREPARATION_FAILED'
                raise PdfPreparationError(code, receipt.get('error') or 'PDF preparation worker failed; no result accepted.')
            check_cancelled()
            if time.monotonic() >= deadline:
                raise PdfPreparationError('PDF_PREPARATION_TIMEOUT', 'PDF preparation deadline exceeded before acceptance.')
            try:
                result = accept_result(directory, request, self.limits, deadline=deadline)
            except PdfPreparationError:
                raise
            except (ValueError, OSError, TypeError, KeyError, UnicodeError, zlib.error) as exc:
                raise PdfPreparationError('PDF_PREPARATION_INVALID_RESULT', f'Invalid PDF preparation result: {exc}') from exc
            if time.monotonic() >= deadline:
                raise PdfPreparationError('PDF_PREPARATION_TIMEOUT', 'PDF result acceptance exceeded preparation deadline.')
            return result
        except PdfPreparationError as exc:
            exc.operation = operation
            raise
        except (OSError, ValueError) as exc:
            raise PdfPreparationError('PDF_PREPARATION_FAILED', f'PDF preparation failed: {exc}', operation=operation) from exc
        finally:
            if process is not None and not cleaned:
                # Also cover unexpected caller exceptions, not just the normal
                # timeout/cancellation path. Never release an unconfirmed slot.
                self._stop(process)
                try:
                    self._finish(process, directory, invocation)
                    cleaned = True
                except PdfPreparationError:
                    pass
            if process is not None and process.stdin and not process.stdin.closed:
                try:
                    process.stdin.close()
                except OSError:
                    pass  # Reaping/receipt checks above own cleanup evidence.
            if cleaned:
                try:
                    if directory is not None:
                        shutil.rmtree(directory)
                finally:
                    self.capacity.release()
            # An unconfirmed process keeps its slot and workspace. Never launch
            # replacement work or delete files while an owned writer may remain.


_DEFAULT = None
_DEFAULT_LOCK = threading.Lock()


def prepare_pdf(pdf_path, operation, **controls):
    global _DEFAULT
    with _DEFAULT_LOCK:
        if _DEFAULT is None:
            try:
                _DEFAULT = PdfPreparation(PdfLimits.from_environment())
            except ValueError as exc:
                raise PdfPreparationError('PDF_PREPARATION_CONFIGURATION', str(exc), operation=operation) from exc
    return _DEFAULT.run(Path(pdf_path), operation, controls)
