"""Opt-in synthetic PDF fixture route. Requires macOS application services.

Stages via the maintained runner. Parent audit guard blocks external I/O; only
fixed PDF/fixture children in the job's temporary root may launch. Those children
are trusted source-bound fixtures, not an OS sandbox. No general runner bypass.
"""
from pathlib import Path
import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
from scripts import run_tests as runner

SELECTORS = ['tests/test_ocr_pdf.py', 'tests/test_pdf_request_handling.py', 'tests/test_pdf_worker_native.py']


class PdfFixtureRoutes:
    def __init__(self, source, temporary):
        self.source, self.temporary, self.events = source, temporary, []

    def admitted(self, executable, argv, cwd, env):
        if not isinstance(argv, list) or len(argv) not in (6, 7):
            return False
        if executable != sys.executable or argv[:3] != [sys.executable, '-I', '-B']:
            return False
        script = Path(argv[3])
        native = script == self.source/'fruth_core/pdf_worker.py' and len(argv) == 6 and argv[4] == 'supervise'
        fixture = script == self.source/'tests/pdf_worker_fixture.py' and argv[4] in {'supervise', 'caller', 'foreign'}
        target = Path(argv[5])
        if not (native or fixture) or target != target.resolve() or not target.is_relative_to(self.temporary):
            return False
        self.events.append({'argv': argv, 'time': time.time()})
        return True


def worker(job):
    job = Path(job).resolve()
    config = runner.load_config(job)
    if config['selectors'] != SELECTORS:
        raise ValueError('PDF route accepts only its three maintained synthetic suites')
    source, temporary = job/'source', job/'temporary'
    os.chdir(source)
    env = runner.clean_environment(job, hashseed='0')
    os.environ.clear(); os.environ.update(env)
    tempfile.tempdir = str(temporary)
    from scripts.test_isolation import install_guard
    routes = PdfFixtureRoutes(source, temporary)
    violations = install_guard(source=source, evidence=job, job=job, production=config['production'],
                               environment=env, routes=routes)
    from scripts.validation_record import capture_environment
    before = capture_environment(source)
    runner.save(job/'environment-before.json', before)
    # Prevent requests' import-time IPv6 socket probe, as in maintained runner.
    import socket
    prior = socket.has_ipv6; socket.has_ipv6 = False
    import requests
    socket.has_ipv6 = prior
    import pytest
    results = []
    class Reporter:
        def pytest_runtest_logreport(self, report):
            results.append(dict(nodeid=report.nodeid, when=report.when, outcome=report.outcome))
    started = time.monotonic()
    code = int(pytest.main([*SELECTORS, '-q', '-x', '--tb=short', '-p', 'no:cacheprovider',
                           '--import-mode=importlib', '--basetemp='+str(temporary/'pytest'),
                           '--junitxml='+str(job/'junit.xml')], plugins=[Reporter()]))
    after = capture_environment(source)
    runner.save(job/'environment-after.json', after)
    runner.save(job/'results.json', results)
    runner.save(job/'worker.json', dict(exit_code=code, violations=violations, launches=routes.events,
        environment_unchanged=before == after, elapsed_seconds=time.monotonic()-started,
        source_file_map_sha256=runner.verify_source(job)))
    return code or (3 if violations or before != after else 0)


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '_worker':
        return worker(sys.argv[2])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--storage-root', required=True)
    args = parser.parse_args()
    args.source, args.tests, args.seconds = str(SOURCE), SELECTORS, 240
    args.mode, args.collect_only, args.hashseed, args.record_validation = 'regression', False, '0', True
    job, config = runner.prepare(args)
    command = [sys.executable, '-I', '-B', str(job/'source/tests/pdf_native_runner.py'), '_worker', str(job)]
    with (job/'native.log').open('xb', buffering=0) as log:
        child = subprocess.Popen(command, cwd=job/'source', env=runner.clean_environment(job, hashseed='0'),
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        runner.save(job/'job.json', dict(pid=child.pid, command=command))
        deadline, reason = time.monotonic()+240, 'completed'
        while child.poll() is None:
            capacity = runner.storage_snapshot(Path(args.storage_root))
            if time.monotonic() >= deadline or capacity['stop_reason']:
                reason = capacity['stop_reason'] or 'job_deadline'
                child.kill()  # Parent-lease EOF independently stops all PDF jobs.
                break
            time.sleep(.2)
        code = child.wait(timeout=10)
    runner.save(job/'completion.json', dict(exit_code=code, reason=reason,
        source_file_map_sha256=runner.verify_source(job), log_sha256=runner.sha(job/'native.log')))
    print(json.dumps(dict(job=str(job), exit_code=code, reason=reason)))
    return code


if __name__ == '__main__':
    sys.exit(main())
