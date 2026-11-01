"""Controlled subprocess faults, never enabled by product payload/environment."""
from pathlib import Path
import ctypes
import json
import os
import resource
import signal
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fruth_core import pdf_worker
from fruth_core.pdf_preparation import PdfPreparation, PdfLimits


def command(role, directory, mode):
    return [sys.executable, '-I', '-B', str(Path(__file__).resolve()), role, str(directory), mode]


class FixturePreparation(PdfPreparation):
    def __init__(self, limits, mode, evidence):
        super().__init__(limits)
        self.mode, self.evidence = mode, evidence

    def _supervisor_command(self, directory):
        (directory/'fixture-evidence.txt').write_text(str(self.evidence))
        (self.evidence/'workspace.txt').write_text(str(directory))
        return command('supervise', directory, self.mode)


def main():
    role, directory, mode = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if role == 'supervise':
        evidence = Path((directory/'fixture-evidence.txt').read_text())
        original_save = pdf_worker._save
        def save(path, value):
            original_save(path, value)
            if path.name in {'identity.json', 'supervisor.json'}:
                original_save(evidence/path.name, value)
        pdf_worker._save = save
        return pdf_worker.supervise(directory, worker_command=command('fault', directory, mode))
    if role == 'caller':
        source = directory/'source.pdf'; source.write_bytes(b'synthetic')
        FixturePreparation(PdfLimits(timeout_sec=10), 'descendant', directory).run(source, 'text', {'max_chars': None})
        return 0
    if role == 'foreign':
        time.sleep(20)
        return 0
    if role == 'descendant':
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        while True:
            with (directory/'writes.txt').open('ab') as stream:
                stream.write(b'x')
            time.sleep(.02)
    if mode == 'exit':
        os._exit(23)
    if mode == 'exception':
        raise RuntimeError('controlled worker exception')
    if mode == 'partial':
        (directory/'results').mkdir()
        (directory/'results/text.txt').write_text('partial')
        return 0
    if mode == 'native-proof':
        evidence = Path((directory/'fixture-evidence.txt').read_text())
        code = pdf_worker.run_worker(directory)
        (evidence/'imports.json').write_text(json.dumps({
            'webserver_imported': 'fruth_webserver' in sys.modules,
            'pdf_library_imported': 'pypdf' in sys.modules or 'Quartz' in sys.modules,
            'cwd': os.getcwd(), 'temporary': tempfile.gettempdir()}))
        return code
    if mode in {'hang', 'descendant'}:
        evidence = Path((directory/'fixture-evidence.txt').read_text())
        with tempfile.NamedTemporaryFile(delete=False) as scratch:
            scratch.write(b'controlled decoder scratch')
        (evidence/'scratch.json').write_text(json.dumps({'path': scratch.name}))
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        if mode == 'descendant':
            child = subprocess.Popen(command('descendant', evidence, mode), close_fds=True)
            (evidence/'descendant.json').write_text(json.dumps({'pid': child.pid}))
        (evidence/'ready').touch()
        ctypes.PyDLL(None).sleep(30)  # Holds the GIL; no Python watchdog can run.
    return 0


if __name__ == '__main__':
    sys.exit(main())
