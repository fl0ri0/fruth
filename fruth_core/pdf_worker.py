"""Fresh PDF child and independent, parent-lease-driven process supervisor.

Only the worker role imports the PDF algorithms. This is process containment,
not a filesystem/network sandbox or a native-memory quota.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import resource
import select
import shutil
import signal
import subprocess
import sys
import time

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fruth_core.pdf_preparation import (
    MAX_DIAGNOSTIC_BYTES, POLL_SECONDS, REAP_SECONDS, TERMINATE_GRACE_SECONDS,
    PdfLimits, PdfPreparationError, checked_controls, digest_bytes, json_bytes, load_json,
)
from fruth_runtime.child_process_env import sanitized_child_process_env


def _save(path, value):
    raw = json_bytes(value)
    if len(raw) > MAX_DIAGNOSTIC_BYTES:
        raise ValueError('PDF supervisor receipt exceeds budget')
    path.write_bytes(raw)


def _command(role, directory):
    return [sys.executable, '-I', '-B', str(Path(__file__).resolve()), role, str(directory)]


def supervise(directory: Path, *, worker_command=None):
    """Own both children. Private command injection is for maintained fixtures only."""
    request = load_json(directory/'request.json')
    invocation = request['invocation_id']
    deadline = request['deadline']
    anchor = child = None
    reason, cleaned, diagnostics, code = 'startup_failure', False, bytearray(), None
    error_code, error = 'PDF_PREPARATION_FAILED', 'PDF preparation could not start.'
    env = sanitized_child_process_env()
    try:
        anchor = subprocess.Popen(_command('anchor', directory), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, process_group=0, close_fds=True, env=env)
        # Anchor signals readiness only after ignoring TERM. It remains alive
        # until group cleanup, even if the native worker exits before supervision.
        while not select.select([anchor.stdout, sys.stdin.buffer], [], [], POLL_SECONDS)[0]:
            if time.monotonic() >= deadline:
                raise PdfPreparationError('PDF_PREPARATION_TIMEOUT', 'PDF worker startup deadline exceeded.')
        if select.select([sys.stdin.buffer], [], [], 0)[0]:
            reason = 'parent_disappeared' if not os.read(sys.stdin.fileno(), 1) else 'cancelled'
        elif os.read(anchor.stdout.fileno(), 1) != b'R':
            raise RuntimeError('PDF group anchor failed before readiness')
        else:
            child = subprocess.Popen(worker_command or _command('worker', directory),
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                process_group=anchor.pid, close_fds=True, env=env)
            _save(directory/'identity.json', {'invocation_id': invocation, 'supervisor': os.getpid(),
                  'anchor': anchor.pid, 'worker': child.pid})
            watched = [sys.stdin.buffer, child.stdout, child.stderr]
            reason = 'deadline'
            while time.monotonic() < deadline:
                stop = False
                for stream in select.select(watched, [], [], POLL_SECONDS)[0]:
                    data = os.read(stream.fileno(), 4096)
                    if stream is sys.stdin.buffer:
                        reason = 'parent_disappeared' if not data else 'cancelled'
                        stop = True
                        break
                    if not data:
                        watched.remove(stream)
                        if stream is child.stdout:
                            reason, stop = 'worker_exit', True
                            break
                    elif stream is child.stderr:
                        diagnostics.extend(data[:max(0, MAX_DIAGNOSTIC_BYTES // 2-len(diagnostics))])
                if stop:
                    break
    except BaseException as exc:
        reason = 'supervisor_failure'
        error = str(exc)[:1024]
        if isinstance(exc, PdfPreparationError):
            error_code = exc.code
    finally:
        # Retain anchor handle without poll/wait until all group signals finish.
        # No registry/PID/port discovery supplies signal authority.
        signals = []
        try:
            if anchor is not None:
                if reason != 'worker_exit':
                    os.killpg(anchor.pid, signal.SIGTERM)
                    signals.append('TERM')
                    time.sleep(TERMINATE_GRACE_SECONDS)
                os.killpg(anchor.pid, signal.SIGKILL)
                signals.append('KILL')
                if child is not None:
                    code = child.wait(timeout=REAP_SECONDS)
                anchor.wait(timeout=REAP_SECONDS)
            cleaned = True
        except (OSError, subprocess.TimeoutExpired) as exc:
            error_code = 'PDF_PREPARATION_CLEANUP_UNCONFIRMED'
            error = f'Owned PDF group cleanup unconfirmed: {exc}'
        if reason in {'deadline', 'cancelled', 'parent_disappeared'} and cleaned:
            error_code = 'PDF_PREPARATION_TIMEOUT' if reason == 'deadline' else 'PDF_PREPARATION_CANCELLED'
            error = 'PDF preparation deadline exceeded.' if reason == 'deadline' else 'PDF preparation caller cancelled or exited.'
        if cleaned and reason == 'worker_exit' and code == -signal.SIGXFSZ:
            error_code, error = 'PDF_PREPARATION_LIMIT', 'PDF output exceeded its per-file/remaining aggregate byte budget.'
        if cleaned and reason == 'worker_exit' and code and (directory/'error.json').is_file():
            try:
                failure = load_json(directory/'error.json', MAX_DIAGNOSTIC_BYTES)
                if failure.get('invocation_id') == invocation and failure.get('code') in {
                        'PDF_PREPARATION_LIMIT', 'PDF_PREPARATION_FAILED'}:
                    error_code, error = failure['code'], str(failure['error'])[:1024]
            except (ValueError, OSError, TypeError, KeyError):
                pass
        # Cover a parent exit racing with worker stdout EOF/group cleanup.
        if cleaned and select.select([sys.stdin.buffer], [], [], 0)[0]:
            if not os.read(sys.stdin.fileno(), 1):
                reason = 'parent_disappeared'
        _save(directory/'supervisor.json', dict(invocation_id=invocation, reason=reason,
            reaped=cleaned, group_cleaned=cleaned, worker_exit=code, signals=signals,
            child_max_rss_bytes=int(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
                                    * (1 if sys.platform == 'darwin' else 1024)),
            error_code=error_code, error=error,
            diagnostics=diagnostics.decode('utf-8', errors='replace')[:2048]))
        if reason == 'parent_disappeared' and cleaned:
            shutil.rmtree(directory)
    return 0 if cleaned and reason == 'worker_exit' and code == 0 else 1


def run_worker(directory: Path):
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    signal.signal(signal.SIGXFSZ, signal.SIG_DFL)
    os.umask(0o077)
    request = load_json(directory/'request.json')
    try:
        PdfLimits(**request['limits'])
        checked_controls(request['operation'], request['controls'])
        # Fresh child only; never import the webserver or discover models.
        from fruth_core.ocr_pdf import _prepare_pdf_files
        _prepare_pdf_files(directory, request)
        return 0
    except BaseException as exc:
        code = exc.code if isinstance(exc, PdfPreparationError) else 'PDF_PREPARATION_FAILED'
        _save(directory/'error.json', dict(invocation_id=request['invocation_id'], code=code, error=str(exc)[:1024]))
        return 1


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in {'supervise', 'worker', 'anchor'}:
        raise SystemExit('Expected PDF role and private workspace')
    directory = Path(sys.argv[2])
    if directory != directory.resolve() or not directory.is_dir() or directory.is_symlink():
        raise SystemExit('PDF workspace must be a physical absolute directory')
    if sys.argv[1] == 'anchor':
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        os.write(sys.stdout.fileno(), b'R')
        # Independent supervisor owns this process. No native imports or threads.
        while True:
            time.sleep(60)
    return supervise(directory) if sys.argv[1] == 'supervise' else run_worker(directory)


if __name__ == '__main__':
    sys.exit(main())
