"""Portable form of the study runners' pre-import audit guard (stdlib only).

This guards trusted offline tests, not hostile native code. No broad subprocess
escape hatch: cold fixtures and source-bound native routes have separate admission.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys


PROTECTED = ('state', 'artifacts', 'logs', '.fruth_archiv', 'model_ports.json',
             'config', 'fruth_research/retained-evidence', 'fruth_research/candidates')
EXTERNAL = {'socket.connect', 'socket.connect_ex', 'socket.bind', 'socket.getaddrinfo',
            'socket.sendto', 'subprocess.Popen', 'os.system', 'os.posix_spawn',
            'os.fork', 'os.forkpty', 'os.exec'}


def within(path, root):
    return path == root or root in path.parents


def cold_child_allowed(executable, argv, cwd, env, *, source, evidence, job, production,
                       environment, enabled):
    if not enabled or not isinstance(argv, list) or len(argv) != 6 or not isinstance(env, dict):
        return False
    try:
        source, evidence, job, production = (Path(p).resolve() for p in (source, evidence, job, production))
        script = source / 'tests/cold_process_child.py'
        if (Path(executable).resolve() != Path(sys.executable).resolve()
                or argv[:3] != [sys.executable, '-B', str(script)]
                or argv[3] not in {'writer', 'reader'} or Path(cwd).resolve() != source):
            return False
        input_path, output = (Path(p) for p in argv[4:])
        if (not input_path.is_absolute() or not output.is_absolute()
                or input_path != input_path.resolve() or output != output.resolve()
                or input_path.parent != output.parent or input_path.parent.parent != evidence
                or input_path.name != output.stem + '-input.json' or output.suffix != '.json'
                or not output.stem.startswith(argv[3]) or output.exists()):
            return False
        expected = dict(environment, TMPDIR=str(input_path.parent / 'temporary'),
                        PYTHONDONTWRITEBYTECODE='1',
                        FRUTH_HYPOTHESIS_EVIDENCE_DIR=str(input_path.parent / 'writer-fixture'))
        # Context is set per pytest item, before child creation.
        expected['FRUTH_LINEAGE_CONTEXT'] = os.environ.get('FRUTH_LINEAGE_CONTEXT', '')
        for key in ('PYTEST_CURRENT_TEST', 'PYTEST_VERSION'):
            if key in os.environ:
                expected[key] = os.environ[key]
        return (env == expected and env.get('FRUTH_COLD_PLAN') == str(job)
                and env.get('FRUTH_COLD_PRODUCTION') == str(production))
    except (TypeError, ValueError, OSError):
        return False


def make_guard(*, source, evidence, job, production, environment, cold=False, routes=None):
    source, evidence, job, production = (Path(p).resolve() for p in (source, evidence, job, production))
    protected = tuple(production / name for name in PROTECTED)
    violations = []

    def deny(event, path=None):
        violations.append({'event': event, 'path': str(path) if path else None})
        raise PermissionError('Offline test isolation denied: ' + event + (f' {path}' if path else ''))

    def check(raw, write, event):
        if not isinstance(raw, (str, bytes, os.PathLike)):
            return
        path = Path(os.fsdecode(raw)).resolve()
        if any(within(path, root) for root in protected):
            deny(event, path)
        if write and path != Path(os.devnull) and not within(path, job):
            deny(event, path)

    def audit(event, values):
        if event == 'subprocess.Popen' and routes is not None and routes.admitted(*values):
            return
        if event == 'subprocess.Popen' and cold_child_allowed(
                *values, source=source, evidence=evidence, job=job, production=production,
                environment=environment, enabled=cold):
            return
        if event in EXTERNAL:
            deny(event)
        if event == 'open':
            mode, flags = values[1:3]
            write = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
                isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)))
            check(values[0], write, event)
        elif event in {'os.listdir', 'os.scandir'}:
            check(values[0], False, event)
        elif event in {'os.remove', 'os.rmdir', 'os.mkdir', 'os.chmod', 'os.utime', 'os.truncate'}:
            check(values[0], True, event)
        elif event in {'os.rename', 'os.link', 'os.symlink'}:
            for raw in values[:2]:
                check(raw, True, event)
        elif event == 'sqlite3.connect' and values[0] != ':memory:':
            raw = values[0]
            if isinstance(raw, str) and raw.startswith('file:'):
                from urllib.parse import unquote
                raw = unquote(raw[5:].split('?', 1)[0])
            check(raw, True, event)

    return audit, violations


def install_guard(**kwargs):
    audit, violations = make_guard(**kwargs)
    sys.addaudithook(audit)
    return violations
