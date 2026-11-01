"""Shared PDF/OCR and OCR-quality helpers for Fruth."""

from __future__ import annotations

import hashlib
import resource
import shutil
import logging
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Callable, Optional

OCR_STRUCTURAL_LINE_TOKENS = {
    'text',
    'image',
    'table',
    'title',
    'sub_title',
    'table_caption',
}

PDF_TEXT_EXTRACTION_MAX_CHARS = 2_000_000
PDF_PAGE_OCR_NUM_PREDICT = 8192
IMAGE_OCR_NUM_PREDICT = 4096


def extract_pdf_text_content(
    pdf_path: Path,
    max_chars: Optional[int] = PDF_TEXT_EXTRACTION_MAX_CHARS,
    *,
    warnings: Optional[list[str]] = None,
) -> str:
    from fruth_core.pdf_preparation import prepare_pdf
    texts, _total, messages = prepare_pdf(pdf_path, 'text', max_chars=max_chars)
    if warnings is not None:
        warnings.extend(messages)
    return texts[0] if texts else ''


def _open_native_pdf(pdf_path: Path):
    if sys.platform != 'darwin':
        raise ValueError('PDF page rendering requires macOS; text-layer extraction remains available.')
    try:
        import Quartz  # type: ignore
    except ImportError as exc:
        raise ValueError(
            'macOS PDF rendering requires pyobjc-framework-Quartz. '
            'Install the updated requirements.txt in the Fruth environment.'
        ) from exc

    path_bytes = bytes(pdf_path.resolve())
    url = Quartz.CFURLCreateFromFileSystemRepresentation(None, path_bytes, len(path_bytes), False)
    document = Quartz.PDFDocument.alloc().initWithURL_(url)
    if document is None:
        raise ValueError('PDF could not be opened.')
    if document.isLocked():
        raise ValueError('PDF is password locked.')
    if document.pageCount() == 0:
        raise ValueError('PDF contains no pages.')
    return Quartz, document


def _render_native_pdf_page(
    quartz,
    document,
    *,
    page_index: int,
    dpi: int,
    max_image_side_px: int,
    crop_margin_ratio: float = 0.0,
    output_path: Path,
) -> tuple[int, int, bool]:
    import objc  # type: ignore

    # Bound native temporaries to one page in the disposable worker.
    with objc.autorelease_pool():
        page = document.pageAtIndex_(page_index)
        if page is None:
            raise ValueError(f'PDF page {page_index + 1} is unavailable.')
        box = quartz.kPDFDisplayBoxCropBox
        bounds = page.boundsForBox_(box)  # PDFKit intersects CropBox with MediaBox.
        width, height = float(bounds.size.width), float(bounds.size.height)
        # PDFKit's box/drawing coordinates do not apply PDF /UserUnit. Preserve
        # physical size at the requested DPI before enforcing the pixel ceiling.
        dictionary = quartz.CGPDFPageGetDictionary(page.pageRef())
        has_unit, raw_unit = quartz.CGPDFDictionaryGetNumber(dictionary, b'UserUnit', None)
        unit = float(raw_unit) if has_unit else 1.0
        if not math.isfinite(unit) or unit <= 0:
            raise ValueError(f'PDF page {page_index + 1} has invalid page units.')
        width, height = width * unit, height * unit
        if not all(math.isfinite(value) and value > 0 for value in (width, height)):
            raise ValueError(f'PDF page {page_index + 1} has invalid geometry.')
        if page.rotation() % 180:
            width, height = height, width
        if max_image_side_px <= 0 or not math.isfinite(float(dpi)) or dpi <= 0:
            raise ValueError('PDF rendering requires positive DPI and image-side limits.')
        base_zoom = max(1.0, float(dpi) / 72.0)
        # No minimum zoom: oversized PDF pages must still obey the pixel ceiling.
        zoom = min(base_zoom, float(max_image_side_px) / max(width, height))
        ratio = max(0.0, min(0.2, float(crop_margin_ratio or 0.0)))
        if min(width, height) * (1.0 - 2.0 * ratio) <= 72:
            ratio = 0.0
        pixel_width = min(max_image_side_px, max(1, math.ceil(width * zoom * (1.0 - 2.0 * ratio))))
        pixel_height = min(max_image_side_px, max(1, math.ceil(height * zoom * (1.0 - 2.0 * ratio))))
        context = quartz.CGBitmapContextCreate(
            None, pixel_width, pixel_height, 8, pixel_width * 4,
            quartz.CGColorSpaceCreateDeviceRGB(),
            quartz.kCGImageAlphaNoneSkipLast | quartz.kCGBitmapByteOrder32Big,
        )
        if context is None:
            raise RuntimeError('Could not allocate the PDF page bitmap.')
        quartz.CGContextSetRGBFillColor(context, 1, 1, 1, 1)
        quartz.CGContextFillRect(context, quartz.CGRectMake(0, 0, pixel_width, pixel_height))
        quartz.CGContextTranslateCTM(context, -width * zoom * ratio, -height * zoom * ratio)
        quartz.CGContextScaleCTM(context, zoom * unit, zoom * unit)
        # PDFKit applies the intrinsic rotation and box origin exactly once, and
        # includes visible annotations. CoreGraphics alone draws page content.
        page.setDisplaysAnnotations_(True)
        page.drawWithBox_toContext_(box, context)
        image = quartz.CGBitmapContextCreateImage(context)
        if image is None:
            raise RuntimeError('Could not create the PDF page image.')
        # Encode to a private file under the worker's current RLIMIT_FSIZE.
        # Avoid an unbounded CFData PNG buffer before the byte-budget check.
        path_bytes = bytes(output_path)
        url = quartz.CFURLCreateFromFileSystemRepresentation(None, path_bytes, len(path_bytes), False)
        destination = quartz.CGImageDestinationCreateWithURL(url, 'public.png', 1, None)
        if destination is None:
            raise RuntimeError('Could not create the PDF page PNG destination.')
        quartz.CGImageDestinationAddImage(destination, image, None)
        if not quartz.CGImageDestinationFinalize(destination):
            raise RuntimeError('Could not encode the PDF page PNG.')
        return pixel_width, pixel_height, zoom + 1e-6 < base_zoom


def render_pdf_pages_to_base64(
    pdf_path: Path, *, max_pages: Optional[int] = None, dpi: int = 180,
    max_image_side_px: int = 2400,
) -> tuple[list[str], int, list[str]]:
    from fruth_core.pdf_preparation import prepare_pdf
    return prepare_pdf(pdf_path, 'render', max_pages=max_pages, dpi=dpi,
                       max_image_side_px=max_image_side_px)


def render_single_pdf_page_to_base64(
    pdf_path: Path, *, page_index: int, dpi: int, max_image_side_px: int = 2400,
    crop_margin_ratio: float = 0.0,
) -> Optional[str]:
    from fruth_core.pdf_preparation import prepare_pdf
    pages, _total, _warnings = prepare_pdf(pdf_path, 'page', page_index=page_index, dpi=dpi,
        max_image_side_px=max_image_side_px, crop_margin_ratio=crop_margin_ratio)
    return pages[0] if pages else None


class _PdfOutputs:
    """Worker-only incremental output accounting; publish a manifest last."""
    def __init__(self, directory, request):
        from fruth_core.pdf_preparation import PdfLimits
        self.directory, self.request = directory / 'results', request
        self.directory.mkdir()
        self.limits = PdfLimits(**request['limits'])
        self.files, self.selected, self.warnings = [], [], []
        self.total, self.used = 0, 0

    def limit(self, message):
        from fruth_core.pdf_preparation import PdfPreparationError
        raise PdfPreparationError('PDF_PREPARATION_LIMIT', message)

    def remaining(self, *, text=False):
        ceiling = min(self.limits.result_bytes, self.limits.output_bytes - self.used)
        return min(ceiling, self.limits.text_bytes) if text else ceiling

    def add(self, path, *, page_index=None, width=None, height=None):
        size, digest = 0, hashlib.sha256()
        with path.open('rb') as stream:
            while block := stream.read(1024 * 1024):
                size += len(block)
                if size > self.remaining(text=page_index is None):
                    self.limit('PDF result exceeds its per-result/aggregate output byte budget.')
                digest.update(block)
        self.used += size
        self.files.append(dict(name=path.name, size_bytes=size, sha256=digest.hexdigest(),
                               page_index=page_index, width=width, height=height))

    def manifest(self, status='complete'):
        from fruth_core.pdf_preparation import digest_bytes, json_bytes, MAX_MANIFEST_BYTES
        value = {key: self.request[key] for key in
                 ('protocol', 'version', 'invocation_id', 'source_sha256', 'operation', 'controls')}
        value.update(request_sha256=digest_bytes(json_bytes(self.request)), status=status,
                     total_pages=self.total, selected_pages=self.selected,
                     warnings=self.warnings, files=self.files)
        raw = json_bytes(value)
        if len(raw) > MAX_MANIFEST_BYTES:
            self.limit('PDF result manifest exceeds its 1 MiB byte budget.')
        return raw

    def unreadable(self, message):
        # An ordinary unavailable/invalid document is an explicit complete outcome.
        # Earlier pages never survive a later page failure or change retry indices.
        shutil.rmtree(self.directory)
        self.directory.mkdir()
        self.files, self.selected, self.used = [], [], 0
        self.warnings = [message]
        (self.directory / 'manifest.json').write_bytes(self.manifest('unreadable'))


def _extract_pdf_text_file(outputs):
    from pypdf import PdfReader
    from pypdf.errors import LimitReachedError, PyPdfError
    from fruth_core.pdf_preparation import PdfPreparationError
    max_chars = outputs.request['controls']['max_chars']
    try:
        reader = PdfReader(str(outputs.directory.parent / 'source.pdf'))
        outputs.total = len(reader.pages)
        size = chars = pages_without_text = 0
        path = outputs.directory / 'text.txt'
        with path.open('xb') as stream:
            for index, page in enumerate(reader.pages):
                text = (page.extract_text() or '').strip()
                outputs.selected.append(index)
                if index % 256 == 0:
                    outputs.manifest()  # Bound selected-page metadata as it grows.
                if not text:
                    pages_without_text += 1
                    continue
                if chars:
                    text = '\n\n' + text
                if max_chars is not None and chars + len(text) > max_chars:
                    outputs.limit('PDF text exceeds its explicit character budget; no partial text accepted.')
                chars += len(text)
                for offset in range(0, len(text), 65536):
                    block = text[offset:offset + 65536].encode('utf-8')
                    if size + len(block) > outputs.remaining(text=True):
                        outputs.limit('PDF text exceeds its text/per-result/aggregate byte budget.')
                    stream.write(block)
                    size += len(block)
        outputs.add(path)
        if chars and pages_without_text:
            outputs.warnings.append(
                f'{pages_without_text} PDF page(s) had no extractable text and are absent '
                'from the text result. Use image analysis to include scanned content.')
    except LimitReachedError as exc:
        outputs.limit(f'PDF parser resource guard reached: {exc}')
    except (PyPdfError, ValueError) as exc:
        # Infrastructure, memory, I/O and unexpected worker exceptions are fatal.
        # Only ordinary document errors may use the existing OCR fallback.
        outputs.unreadable(f'PDF text extraction failed: {exc}')
        return
    (outputs.directory / 'manifest.json').write_bytes(outputs.manifest())


def _prepare_pdf_files(directory: Path, request: dict):
    """Native algorithms are entered only by the fresh worker role."""
    from fruth_core.pdf_preparation import PdfPreparationError, open_regular
    source = directory / 'source.pdf'
    digest, size = hashlib.sha256(), 0
    with open_regular(source) as stream:
        while block := stream.read(1024 * 1024):
            size += len(block)
            if size > request['limits']['input_bytes']:
                raise PdfPreparationError('PDF_PREPARATION_LIMIT', 'PDF source exceeds input byte budget.')
            digest.update(block)
    if size != request['source_bytes'] or digest.hexdigest() != request['source_sha256']:
        raise RuntimeError('PDF source identity changed before parsing.')
    outputs = _PdfOutputs(directory, request)
    if request['operation'] == 'text':
        return _extract_pdf_text_file(outputs)
    controls = request['controls']
    try:
        quartz, document = _open_native_pdf(source)
        outputs.total = int(document.pageCount())
        if request['operation'] == 'page':
            index = controls['page_index']
            indices = [index] if 0 <= index < outputs.total else []
        else:
            count = outputs.total if controls['max_pages'] is None else min(outputs.total, controls['max_pages'])
            indices = range(count)
        downscaled = False
        for index in indices:
            path = outputs.directory / f'page-{index:08d}.png'
            ceiling = outputs.remaining()
            if ceiling <= 0:
                outputs.limit('PDF aggregate output byte budget exhausted.')
            previous = resource.getrlimit(resource.RLIMIT_FSIZE)
            soft = min(ceiling, previous[1]) if previous[1] != resource.RLIM_INFINITY else ceiling
            try:
                resource.setrlimit(resource.RLIMIT_FSIZE, (soft, previous[1]))
                width, height, scaled = _render_native_pdf_page(
                    quartz, document, page_index=index, dpi=controls['dpi'],
                    max_image_side_px=controls['max_image_side_px'],
                    crop_margin_ratio=controls.get('crop_margin_ratio', 0.0), output_path=path)
            finally:
                resource.setrlimit(resource.RLIMIT_FSIZE, previous)
            outputs.selected.append(index)
            outputs.add(path, page_index=index, width=width, height=height)
            outputs.manifest()
            downscaled |= scaled
        if downscaled:
            outputs.warnings.append(
                f"PDF pages were limited to a maximum edge length of {controls['max_image_side_px']}px to keep OCR stable.")
        if request['operation'] == 'render' and outputs.total > len(outputs.selected):
            outputs.warnings.append(f'PDF contains {outputs.total} pages; only the first {len(outputs.selected)} pages were rendered.')
    except ValueError as exc:
        outputs.unreadable(f'PDF pages could not be rendered: {exc}')
        return
    (outputs.directory / 'manifest.json').write_bytes(outputs.manifest())


def is_generic_ocr_instruction_prompt(prompt: str) -> bool:
    text = re.sub(r'\s+', ' ', str(prompt or '').strip().lower())
    if not text:
        return True
    exact_markers = {
        'ocr',
        'free ocr',
        'extract text',
        'read text',
        'scan text',
        'text',
        'ocr these',
        'ocr all',
        'transcribe',
    }
    if text in exact_markers:
        return True
    if text.startswith('ocr ') and len(text) <= 36:
        return True
    if len(text) <= 18 and 'text' in text:
        return True
    return False


def looks_like_ocr_prompt_echo(content: str, *, user_hint: str) -> bool:
    text = str(content or '').strip()
    if not text:
        return True
    lowered = text.lower()
    marker_values = [
        'user request/context:',
        'for each page:',
        'verbatim transcription (preserve line breaks and structure)',
        'mark uncertain readings as [unclear]',
        'open questions / ambiguities',
        'action items',
        '<|grounding|>convert the document to markdown',
        'free ocr.',
    ]
    marker_hits = sum(1 for marker in marker_values if marker in lowered)
    if lowered.startswith('user request/context:'):
        return True
    if lowered.count('user request/context:') >= 2:
        return True
    if marker_hits >= 3:
        return True

    normalized_text = re.sub(r'\s+', ' ', lowered).strip()
    normalized_hint = re.sub(r'\s+', ' ', str(user_hint or '').lower()).strip()
    if normalized_hint and not is_generic_ocr_instruction_prompt(normalized_hint):
        if normalized_text.count(normalized_hint) >= 2:
            return True
        if normalized_hint in normalized_text and len(normalized_text) <= max(1000, len(normalized_hint) * 6):
            return True
    return False


def normalize_ocr_line(line: str) -> str:
    return re.sub(r'\s+', ' ', str(line or '').strip()).lower()


def strip_ocr_structural_lines(text: str) -> str:
    lines = str(text or '').splitlines()
    kept: list[str] = []
    for raw_line in lines:
        if normalize_ocr_line(raw_line) in OCR_STRUCTURAL_LINE_TOKENS:
            continue
        kept.append(raw_line)
    cleaned = '\n'.join(kept)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


def collapse_repeated_ocr_lines(text: str, *, max_repeats: int = 3) -> str:
    lines = str(text or '').splitlines()
    if not lines:
        return ''
    collapsed: list[str] = []
    prev_norm = None
    repeat_count = 0
    for raw_line in lines:
        norm = normalize_ocr_line(raw_line)
        if norm and norm == prev_norm:
            repeat_count += 1
            if repeat_count <= max_repeats:
                collapsed.append(raw_line)
            continue
        prev_norm = norm if norm else None
        repeat_count = 1
        collapsed.append(raw_line)
    cleaned = '\n'.join(collapsed)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


def line_has_ocr_garbage_pattern(line: str) -> bool:
    normalized = re.sub(r'[^0-9a-zA-Z]+', ' ', str(line or '').lower()).strip()
    if not normalized:
        return False
    tokens = [token for token in normalized.split() if token]
    if len(tokens) < 20:
        return False

    max_run = 1
    run_token = tokens[0]
    current_run = 1
    current_token = tokens[0]
    for token in tokens[1:]:
        if token == current_token:
            current_run += 1
            if current_run > max_run:
                max_run = current_run
                run_token = token
        else:
            current_run = 1
            current_token = token
    if max_run >= 18:
        return True

    token_counts = Counter(tokens)
    top_token, top_count = token_counts.most_common(1)[0]
    token_ratio = top_count / max(1, len(tokens))
    if top_token.isdigit() and top_count >= 24 and token_ratio >= 0.45:
        return True
    if len(run_token) >= 2 and max_run >= 12 and (max_run / max(1, len(tokens))) >= 0.45:
        return True

    for n in (6, 5, 4, 3):
        if len(tokens) < n * 6:
            continue
        ngram_counts = Counter(' '.join(tokens[i : i + n]) for i in range(len(tokens) - n + 1))
        _top_phrase, phrase_count = ngram_counts.most_common(1)[0]
        phrase_coverage = (phrase_count * n) / max(1, len(tokens))
        if (phrase_count >= 8 and phrase_coverage >= 0.30) or (phrase_count >= 20 and phrase_coverage >= 0.18):
            return True
    return False


def sanitize_ocr_noise_lines(text: str) -> str:
    lines = str(text or '').splitlines()
    if not lines:
        return ''
    sanitized_lines: list[str] = []
    replaced_lines = 0
    for raw_line in lines:
        if line_has_ocr_garbage_pattern(raw_line):
            replaced_lines += 1
            if not sanitized_lines or normalize_ocr_line(sanitized_lines[-1]) != '[unclear]':
                sanitized_lines.append('[unclear]')
            continue
        sanitized_lines.append(raw_line)
    if replaced_lines:
        logging.info('OCR cleanup replaced %s noisy line(s) with [unclear].', replaced_lines)
    cleaned = '\n'.join(sanitized_lines)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


def detect_low_quality_ocr_reason(content: str) -> Optional[str]:
    text = str(content or '').strip()
    if not text:
        return 'empty OCR output'

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return 'empty OCR output'

    useful_lines = [line for line in lines if normalize_ocr_line(line) not in OCR_STRUCTURAL_LINE_TOKENS]
    if not useful_lines:
        return 'only structural OCR markers'

    normalized_lines = [normalize_ocr_line(line) for line in useful_lines if normalize_ocr_line(line)]
    if normalized_lines:
        unique_line_count = len(set(normalized_lines))
        if unique_line_count == 1 and len(normalized_lines) >= 3 and len(normalized_lines[0]) >= 4:
            return f'single-line repetition only ({normalized_lines[0][:64]})'
        line_counts = Counter(normalized_lines)
        top_line, top_count = line_counts.most_common(1)[0]
        if top_count >= 6 and (top_count / max(1, len(normalized_lines))) >= 0.7:
            return f'dominant repeated line ({top_count}x: {top_line[:64]})'
        if top_count >= 20 and (top_count / max(1, len(normalized_lines))) >= 0.35:
            return f'repeated line pattern ({top_count}x: {top_line[:64]})'

    tokens = [token.lower() for token in re.findall(r'\w+', ' '.join(useful_lines), flags=re.UNICODE) if token]
    if len(tokens) >= 120:
        max_run = 1
        run_token = tokens[0]
        current_run = 1
        current_token = tokens[0]
        for token in tokens[1:]:
            if token == current_token:
                current_run += 1
                if current_run > max_run:
                    max_run = current_run
                    run_token = token
            else:
                current_run = 1
                current_token = token
        if max_run >= 24:
            return f'consecutive repeated token run ({max_run}x: {run_token})'

        token_counts = Counter(token for token in tokens if token.strip())
        if token_counts:
            top_token, top_token_count = token_counts.most_common(1)[0]
            top_ratio = top_token_count / max(1, len(tokens))
            if (len(top_token) >= 2 or top_token.isdigit()) and top_token_count >= 40 and top_ratio >= 0.28:
                return f'repeated token pattern ({top_token_count}x: {top_token})'

        for n in (4, 3):
            if len(tokens) < n * 10:
                continue
            ngram_counts = Counter(tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1))
            top_ngram, top_ngram_count = ngram_counts.most_common(1)[0]
            ngram_coverage = (top_ngram_count * n) / max(1, len(tokens))
            if top_ngram_count >= 10 and ngram_coverage >= 0.22:
                return f"repeated phrase loop ({top_ngram_count}x: {' '.join(top_ngram[:3])})"

    return None


def clean_ocr_output_text(raw_text: str, *, max_chars: Optional[int] = None) -> str:
    text = str(raw_text or '')
    if max_chars is not None and len(text) > max_chars:
        logging.warning('OCR raw output truncated from %s to %s chars for stability.', len(text), max_chars)
        text = text[:max_chars]
    if not text:
        return ''
    text = re.sub(r'<\|/?ref\|>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<\|det\|>\s*\[\[[^\]]*\]\]\s*<\|/det\|>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<\|/?grounding\|>', '', text, flags=re.IGNORECASE)
    text = strip_ocr_structural_lines(text)
    text = collapse_repeated_ocr_lines(text, max_repeats=3)
    text = sanitize_ocr_noise_lines(text)
    text = re.sub(r'[ \t]+\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def ocr_pdf_page_with_ollama(
    *,
    port: int,
    model_name: str,
    base_prompt: str,
    page_index: int,
    total_pages: int,
    image_b64: str,
    timeout_sec: int,
    generate_func: Callable[..., dict],
    extract_generate_content_func: Callable[[dict], str],
    request_timeout_error,
    request_connection_error,
    request_exception_error,
) -> tuple[str, Optional[str]]:
    user_hint_raw = str(base_prompt or '').strip()

    logging.info(
        'PDF OCR page request: page=%s/%s model=%s timeout_sec=%s',
        page_index,
        total_pages,
        model_name,
        timeout_sec,
    )
    page_prompt = '<image>\n<|grounding|>Convert the document to markdown.'
    generate_error: Optional[str] = None
    try:
        page_out = generate_func(
            port,
            model_name,
            page_prompt,
            images=[image_b64],
            timeout_sec=timeout_sec,
            options={'num_predict': PDF_PAGE_OCR_NUM_PREDICT},
            max_retries=1,
            allow_port_fallback=False,
        )
        page_content = clean_ocr_output_text(extract_generate_content_func(page_out))
        logging.info('PDF OCR page=%s primary generate chars=%s', page_index, len(page_content))
        if page_content:
            if looks_like_ocr_prompt_echo(page_content, user_hint=user_hint_raw):
                generate_error = f'Page {page_index}: prompt echo returned instead of OCR text via /api/generate.'
            else:
                low_quality_reason = detect_low_quality_ocr_reason(page_content)
                if low_quality_reason:
                    generate_error = f'Page {page_index}: low OCR quality ({low_quality_reason}).'
                else:
                    return page_content, None
    except request_timeout_error:
        generate_error = f'Page {page_index}: timed out after {timeout_sec}s.'
    except request_connection_error as exc:
        generate_error = f'Page {page_index}: connection dropped ({exc}).'
    except request_exception_error as exc:
        status_code = getattr(getattr(exc, 'response', None), 'status_code', None)
        details = ''
        response_obj = getattr(exc, 'response', None)
        if response_obj is not None:
            try:
                payload = response_obj.json()
                details = str(payload.get('error') or payload.get('message') or '').strip() if isinstance(payload, dict) else ''
            except Exception:
                details = str(getattr(response_obj, 'text', '') or '').strip()[:220]
        if status_code:
            generate_error = f'Page {page_index}: upstream HTTP {status_code}.'
            if details:
                generate_error = f'{generate_error} {details}'
        else:
            generate_error = f'Page {page_index}: upstream error ({exc}).'
    except Exception as exc:  # noqa: BLE001
        generate_error = f'Page {page_index}: unexpected OCR error ({exc}).'

    logging.info(
        'PDF OCR page=%s has no usable /api/generate content (%s); trying emergency /api/generate fallback.',
        page_index,
        generate_error or 'empty-response',
    )

    emergency_prompt = '<image>\nFree OCR.'
    emergency_error: Optional[str] = None
    emergency_timeout_sec = max(45, min(timeout_sec, 45))
    try:
        logging.info('PDF OCR page=%s emergency generate fallback timeout_sec=%s', page_index, emergency_timeout_sec)
        emergency_out = generate_func(
            port,
            model_name,
            emergency_prompt,
            images=[image_b64],
            timeout_sec=emergency_timeout_sec,
            options={'num_predict': PDF_PAGE_OCR_NUM_PREDICT},
            max_retries=1,
            allow_port_fallback=False,
        )
        emergency_content = clean_ocr_output_text(extract_generate_content_func(emergency_out))
        logging.info('PDF OCR page=%s emergency generate chars=%s', page_index, len(emergency_content))
        if emergency_content:
            if looks_like_ocr_prompt_echo(emergency_content, user_hint=user_hint_raw):
                emergency_error = f'Page {page_index}: prompt echo returned instead of OCR text in the emergency fallback.'
            else:
                low_quality_reason = detect_low_quality_ocr_reason(emergency_content)
                if low_quality_reason:
                    emergency_error = f'Page {page_index}: low OCR quality in the emergency fallback ({low_quality_reason}).'
                else:
                    return emergency_content, None
    except request_timeout_error:
        emergency_error = f'Page {page_index}: emergency fallback timed out after {emergency_timeout_sec}s.'
    except request_connection_error as exc:
        emergency_error = f'Page {page_index}: emergency fallback connection dropped ({exc}).'
    except request_exception_error as exc:
        status_code = getattr(getattr(exc, 'response', None), 'status_code', None)
        if status_code:
            emergency_error = f'Page {page_index}: emergency fallback HTTP {status_code}.'
        else:
            emergency_error = f'Page {page_index}: emergency fallback error ({exc}).'
    except Exception as exc:  # noqa: BLE001
        emergency_error = f'Page {page_index}: unexpected emergency fallback error ({exc}).'
        logging.info('PDF OCR emergency generate retry failed for page=%s: %s', page_index, exc)

    if generate_error and emergency_error:
        return '', f'{generate_error} {emergency_error}'
    if generate_error:
        return '', generate_error
    if emergency_error:
        return '', emergency_error
    return '', f'Page {page_index}: no OCR text was returned.'


def ocr_image_with_deepseek(
    *,
    port: int,
    model_name: str,
    image_b64: str,
    user_prompt: str,
    timeout_sec: int,
    generate_func: Callable[..., dict],
    extract_generate_content_func: Callable[[dict], str],
    request_timeout_error,
    request_connection_error,
    request_exception_error,
) -> tuple[str, Optional[str]]:
    user_hint_raw = str(user_prompt or '').strip()
    primary_prompt = '<image>\n<|grounding|>Convert the document to markdown.'
    primary_error: Optional[str] = None
    try:
        primary_out = generate_func(
            port,
            model_name,
            primary_prompt,
            images=[image_b64],
            timeout_sec=timeout_sec,
            options={'num_predict': IMAGE_OCR_NUM_PREDICT},
            max_retries=1,
            allow_port_fallback=False,
        )
        primary_content = clean_ocr_output_text(extract_generate_content_func(primary_out))
        logging.info('Image OCR primary generate chars=%s', len(primary_content))
        if primary_content:
            if looks_like_ocr_prompt_echo(primary_content, user_hint=user_hint_raw):
                primary_error = 'Image OCR: prompt echo returned instead of OCR text via /api/generate.'
            else:
                low_quality_reason = detect_low_quality_ocr_reason(primary_content)
                if low_quality_reason:
                    primary_error = f'Image OCR: low OCR quality ({low_quality_reason}).'
                else:
                    return primary_content, None
    except request_timeout_error:
        primary_error = f'Image OCR: timed out after {timeout_sec}s.'
    except request_connection_error as exc:
        primary_error = f'Image OCR: connection dropped ({exc}).'
    except request_exception_error as exc:
        status_code = getattr(getattr(exc, 'response', None), 'status_code', None)
        if status_code:
            primary_error = f'Image OCR: upstream HTTP {status_code}.'
        else:
            primary_error = f'Image OCR: upstream error ({exc}).'
    except Exception as exc:  # noqa: BLE001
        primary_error = f'Image OCR: unexpected error ({exc}).'

    logging.info(
        'Image OCR has no usable /api/generate content (%s); trying emergency fallback.',
        primary_error or 'empty-response',
    )

    emergency_prompt = '<image>\nFree OCR.'
    emergency_error: Optional[str] = None
    try:
        emergency_timeout_sec = max(45, min(timeout_sec, 90))
        emergency_out = generate_func(
            port,
            model_name,
            emergency_prompt,
            images=[image_b64],
            timeout_sec=emergency_timeout_sec,
            options={'num_predict': IMAGE_OCR_NUM_PREDICT},
            max_retries=1,
            allow_port_fallback=False,
        )
        emergency_content = clean_ocr_output_text(extract_generate_content_func(emergency_out))
        logging.info('Image OCR emergency generate chars=%s', len(emergency_content))
        if emergency_content:
            if looks_like_ocr_prompt_echo(emergency_content, user_hint=user_hint_raw):
                emergency_error = 'Image OCR: prompt echo returned instead of OCR text in the emergency fallback.'
            else:
                low_quality_reason = detect_low_quality_ocr_reason(emergency_content)
                if low_quality_reason:
                    emergency_error = f'Image OCR: low OCR quality in the emergency fallback ({low_quality_reason}).'
                else:
                    return emergency_content, None
    except request_timeout_error:
        emergency_error = 'Image OCR: emergency fallback timed out.'
    except request_connection_error as exc:
        emergency_error = f'Image OCR: emergency fallback connection dropped ({exc}).'
    except request_exception_error as exc:
        status_code = getattr(getattr(exc, 'response', None), 'status_code', None)
        if status_code:
            emergency_error = f'Image OCR: emergency fallback HTTP {status_code}.'
        else:
            emergency_error = f'Image OCR: emergency fallback error ({exc}).'
    except Exception as exc:  # noqa: BLE001
        emergency_error = f'Image OCR: unexpected emergency fallback error ({exc}).'

    if primary_error and emergency_error:
        return '', f'{primary_error} {emergency_error}'
    if primary_error:
        return '', primary_error
    if emergency_error:
        return '', emergency_error
    return '', 'Image OCR: no OCR text was returned.'
