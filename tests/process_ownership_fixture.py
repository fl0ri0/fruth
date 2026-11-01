#!/usr/bin/env python3
"""Native ownership checks on minimal copied source and harmless loopback children.

Run explicitly: python -B tests/process_ownership_fixture.py --output /new/temp/path
No models, real webserver, production registry or cleanup command are executed.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
FILES = ('fruth_core/__init__.py', 'fruth_core/process_identity.py',
         'fruth_core/process_ownership.py', 'fruth_core/registry.py',
         'fruth_runtime/__init__.py', 'fruth_runtime/child_process_env.py',
         'helpers/__init__.py', 'helpers/model_capabilities.py', 'start_multi_models.sh')
CHILD = '''import json,os,pathlib,signal,socket,time
marker=pathlib.Path(os.environ['FIXTURE_MARKER'])
stop=pathlib.Path(os.environ['FIXTURE_STOP'])
events=pathlib.Path(os.environ['FIXTURE_EVENTS'])
def term(sig,frame):
 with events.open('a') as stream: stream.write(str(sig)+'\\n')
 if marker.with_suffix('.term-exec').exists():
  target=marker.with_suffix('.term-exec').read_text(); marker.with_suffix('.term-exec').unlink()
  os.environ['FIXTURE_PORT']=str(sock.getsockname()[1])
  os.execv(__import__('sys').executable,[__import__('sys').executable,target])
 if os.environ.get('FIXTURE_STUBBORN') != '1': raise SystemExit(0)
signal.signal(signal.SIGTERM,term)
sock=socket.socket(); sock.bind(('127.0.0.1',int(os.environ.get('FIXTURE_PORT','0')))); sock.listen()
marker.write_text(json.dumps(dict(pid=os.getpid(),port=sock.getsockname()[1])))
while not stop.exists():
 if marker.with_suffix('.exec').exists():
  target=marker.with_suffix('.exec').read_text(); marker.with_suffix('.exec').unlink()
  os.environ['FIXTURE_PORT']=str(sock.getsockname()[1])
  os.execv(__import__('sys').executable,[__import__('sys').executable,target])
 time.sleep(.01)
'''
OWNER = None
WORK = None
RECEIPTS = []


def wait_for(predicate, seconds=5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.02)
    raise AssertionError('Disposable fixture did not reach expected state')


class OwnershipChecks(unittest.TestCase):
    def setUp(self):
        self.root = WORK / self._testMethodName / 'checkout with spaces'
        self.root.mkdir(parents=True)
        self.children = []
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(('FRUTH_', 'GRAPH_REBASE_'))
                    and k not in {'PYTHONPATH', 'PYTHONHOME', 'BASH_ENV'}}
        self.env['PYTHONDONTWRITEBYTECODE'] = '1'
        (self.root / 'model_ports.json').write_text('[]')

    def tearDown(self):
        for child, info, identity, stop in self.children:
            stop.touch()  # Cooperative fixture-only shutdown, including shell-launched children.
            if child is not None:
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    if OWNER.process_identity_matches(OWNER._identity(child.pid), identity):
                        child.terminate()
                    child.wait(timeout=3)
            else:
                wait_for(lambda: not OWNER._identity(info['pid']))
        RECEIPTS.append({'case': self._testMethodName, 'children': [row[1] for row in self.children]})

    def start(self, *, root=None, name='fruth_webserver.py', stubborn=False):
        root = root or self.root
        root.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(CHILD)
        marker = root / f'marker-{len(self.children)}'
        stop = root / f'stop-{len(self.children)}'
        events = root / f'events-{len(self.children)}'
        events.touch()
        env = dict(self.env, FIXTURE_MARKER=str(marker), FIXTURE_STOP=str(stop),
                   FIXTURE_EVENTS=str(events), FIXTURE_STUBBORN=str(int(stubborn)))
        child = subprocess.Popen([sys.executable, str(root / name)], cwd=root, env=env)
        # Register the handle before observing readiness, so failed startup is reaped too.
        self.children.append((child, {'pid': child.pid}, '', stop))
        info = wait_for(lambda: json.loads(marker.read_text()) if marker.exists() else None)
        identity = OWNER._identity(child.pid)
        self.assertTrue(identity)
        self.children[-1] = (child, info, identity, stop)
        return child, info, identity, events

    def record(self, info, identity, *, name='worker.py'):
        row = dict(instance_id='owned-fixture', backend='mlx', model='fixture',
                   pid=info['pid'], port=info['port'], process_identity=identity,
                   server_command=[sys.executable, str(self.root / name)])
        (self.root / 'model_ports.json').write_text(json.dumps([row]))
        return row

    def test_owned_webserver_term(self):
        child, info, _, events = self.start()
        OWNER.stop_listener(self.root, info['port'], webserver=True)
        child.wait(timeout=3)
        self.assertEqual(events.read_text(), '15\n')
        self.assertEqual(OWNER.listener_pids(info['port']), [])

    def test_owned_model_term_and_forced_stop(self):
        for stubborn in (False, True):
            child, info, identity, events = self.start(name='worker.py', stubborn=stubborn)
            self.record(info, identity)
            OWNER.stop_listener(self.root, info['port'], grace=.2)
            child.wait(timeout=3)
            self.assertEqual(events.read_text(), '15\n')
            self.assertEqual(child.returncode, -9 if stubborn else 0)

    def test_unrelated_listener_untouched(self):
        child, info, _, events = self.start(name='unrelated.py')
        for web in (False, True):
            with self.assertRaises(OWNER.OwnershipError):
                OWNER.stop_listener(self.root, info['port'], webserver=web)
        self.assertIsNone(child.poll())
        self.assertEqual(events.read_text(), '')

    def test_other_checkout_untouched_even_with_copied_record(self):
        other = self.root.parent / 'other checkout'
        child, info, identity, events = self.start(root=other)
        row = self.record(info, identity)
        row['server_command'] = [sys.executable, str(other / 'fruth_webserver.py')]
        (self.root / 'model_ports.json').write_text(json.dumps([row]))
        for web in (False, True):
            with self.assertRaises(OWNER.OwnershipError):
                OWNER.stop_listener(self.root, info['port'], webserver=web)
        self.assertIsNone(child.poll())
        self.assertEqual(events.read_text(), '')

    def test_missing_stale_conflicting_and_malformed_records(self):
        child, info, identity, events = self.start(name='worker.py')
        row = self.record(info, identity)
        birth_time = identity.split(maxsplit=5)[3]
        stale = identity.replace(birth_time, '00:00:00' if birth_time != '00:00:00' else '00:00:01', 1)
        variants = [[], [{**row, 'process_identity': ''}],
                    [{**row, 'process_identity': stale}],
                    [{**row, 'pid': info['pid'] + 1}],
                    [{**row, 'server_command': [sys.executable, 'wrong.py']}],
                    [row, {**row, 'instance_id': 'conflict'}], 'malformed']
        for value in variants:
            (self.root / 'model_ports.json').write_text(json.dumps(value))
            with self.assertRaises(OWNER.OwnershipError):
                OWNER.stop_listener(self.root, info['port'])
            with self.assertRaises(OWNER.OwnershipError):
                OWNER.check_webserver(self.root, info['port'])
        self.assertIsNone(child.poll())
        self.assertEqual(events.read_text(), '')

    def test_conflicting_listener_discovery(self):
        child, info, _, events = self.start()
        with patch.object(OWNER, 'listener_pids', return_value=[child.pid, child.pid + 1]):
            with self.assertRaises(OWNER.OwnershipError):
                OWNER.stop_listener(self.root, info['port'], webserver=True)
        self.assertEqual(events.read_text(), '')

    def test_identity_change_after_discovery_blocks_term(self):
        child, info, _, events = self.start()
        snapshot = OWNER.inspect_listener(self.root, info['port'], webserver=True)
        target = self.root / 'unrelated.py'
        target.write_text(CHILD)
        (self.root / 'marker-0.exec').write_text(str(target))
        wait_for(lambda: 'unrelated.py' in OWNER._identity(child.pid))
        wait_for(lambda: OWNER.listener_pids(info['port']) == [child.pid])
        # Only discovery is frozen. The exec, PID, fresh observations and signals
        # are real; the same PID now runs a different program.
        with patch.object(OWNER, 'inspect_listener', return_value=snapshot):
            with self.assertRaises(OWNER.OwnershipError):
                OWNER.stop_listener(self.root, info['port'], webserver=True)
        self.assertIsNone(child.poll())
        self.assertEqual(events.read_text(), '')

    def test_identity_change_after_term_blocks_kill(self):
        child, info, identity, events = self.start(stubborn=True)
        target = self.root / 'unrelated.py'
        target.write_text(CHILD)
        (self.root / 'marker-0.term-exec').write_text(str(target))
        with self.assertRaises(OWNER.OwnershipError):
            OWNER.stop_listener(self.root, info['port'], webserver=True, grace=.2)
        wait_for(lambda: 'unrelated.py' in OWNER._identity(child.pid))
        wait_for(lambda: OWNER.listener_pids(info['port']) == [child.pid])
        self.assertIsNone(child.poll())
        self.assertEqual(events.read_text(), '15\n')

    def test_webserver_missing_or_conflicting_evidence_blocks_reuse(self):
        child, info, identity, events = self.start()
        with patch.object(OWNER, '_identity', return_value=''):
            with self.assertRaises(OWNER.OwnershipError):
                OWNER.check_webserver(self.root, info['port'])
        self.record(info, identity, name='fruth_webserver.py')
        with self.assertRaises(OWNER.OwnershipError):
            OWNER.check_webserver(self.root, info['port'])
        (self.root / 'model_ports.json').write_text('{malformed')
        with self.assertRaises(OWNER.OwnershipError):
            OWNER.check_webserver(self.root, info['port'])
        self.assertIsNone(child.poll())
        self.assertEqual(events.read_text(), '')

    def test_registry_change_after_discovery_blocks_term(self):
        child, info, identity, events = self.start(name='worker.py')
        self.record(info, identity)
        original = OWNER.inspect_listener
        def changed(*args, **kwargs):
            owned = original(*args, **kwargs)
            (self.root / 'model_ports.json').write_text('[]')
            return owned
        with patch.object(OWNER, 'inspect_listener', side_effect=changed):
            with self.assertRaises(OWNER.OwnershipError):
                OWNER.stop_listener(self.root, info['port'])
        self.assertIsNone(child.poll())
        self.assertEqual(events.read_text(), '')

    def test_dry_run_has_no_signals_and_reports_unknown(self):
        child, info, _, events = self.start()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            OWNER.stop_listener(self.root, info['port'], webserver=True, dry_run=True)
        self.assertIn('Would stop verified', output.getvalue())
        with self.assertRaisesRegex(OWNER.OwnershipError, 'missing or conflicting'):
            OWNER.stop_listener(self.root, info['port'], dry_run=True)
        self.assertIsNone(child.poll())
        self.assertEqual(events.read_text(), '')

    def shell(self, port, *, launch=False):
        for name in FILES:
            dest = self.root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(WORK / 'source' / name, dest)
        script = self.root / 'start_multi_models.sh'
        script.write_text(script.read_text().replace('WEBSERVER_PORT="5011"', f'WEBSERVER_PORT="{port}"'))
        (self.root / 'scripts').mkdir(exist_ok=True)
        # This fixture qualifies native ownership, not package installation.
        # Bootstrap itself is qualified by python_bootstrap_fixture.py.
        (self.root / 'requirements.txt').write_text('Requests\n')
        (self.root / 'scripts/bootstrap_preflight.py').write_text('pass\n')
        (self.root / 'scripts/startup_model_manager.py').write_text("print('Isolated empty model selection')\n")
        (self.root / 'fruth_runtime/runtime_log_hygiene.py').write_text('def prepare_clean_global_log(*a, **kw): pass\n')
        venv = self.root / '.venv/bin'
        venv.mkdir(parents=True, exist_ok=True)
        (venv / 'activate').write_text('deactivate() { :; }\n')
        (venv / 'python3').symlink_to(sys.executable)
        (self.root / 'fruth_webserver.py').write_text(CHILD)
        marker, stop, events = (self.root / name for name in ('shell-marker', 'shell-stop', 'shell-events'))
        events.touch()
        env = dict(self.env, FIXTURE_PORT=str(port), FIXTURE_MARKER=str(marker),
                   FIXTURE_STOP=str(stop), FIXTURE_EVENTS=str(events), FRUTH_ALLOW_BREW_OLLAMA_SERVICE='1')
        result = subprocess.run(['bash', str(script)], cwd=self.root, env=env, capture_output=True, text=True, timeout=10)
        (self.root.parent / 'shell-result.json').write_text(json.dumps(dict(exit=result.returncode, stdout=result.stdout, stderr=result.stderr), indent=2))
        if marker.exists():
            info = json.loads(marker.read_text())
            self.children.append((None, info, OWNER._identity(info['pid']), stop))
        return result

    def test_shell_reuses_verified_existing_webserver(self):
        child, info, _, events = self.start()
        result = self.shell(info['port'])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('already running', result.stdout)
        self.assertIn('Dashboard:', result.stdout)
        self.assertFalse((self.root / 'shell-marker').exists())
        self.assertEqual(events.read_text(), '')
        self.assertIsNone(child.poll())

    def test_shell_foreign_listener_fails_without_dashboard(self):
        child, info, _, events = self.start(name='unrelated.py')
        result = self.shell(info['port'])
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('unresolved ownership', result.stdout)
        self.assertNotIn('Dashboard:', result.stdout)
        self.assertNotIn('Startup complete', result.stdout)
        self.assertFalse((self.root / 'shell-marker').exists())
        self.assertIsNone(child.poll())
        self.assertEqual(events.read_text(), '')

    def test_shell_free_port_starts_fixture(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        result = self.shell(port, launch=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('started successfully', result.stdout)
        self.assertIn('Startup complete', result.stdout)
        self.assertEqual(len(self.children), 1)
        self.assertIsNotNone(OWNER.check_webserver(self.root, port))


def main():
    global WORK, OWNER
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    WORK = args.output.resolve()
    WORK.mkdir()  # Exclusive output, never reuse old fixture state.
    staging = WORK / 'source'
    hashes = {}
    for name in FILES:
        origin, dest = SOURCE / name, staging / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, dest)
        hashes[name] = hashlib.sha256(dest.read_bytes()).hexdigest()
    sys.path.insert(0, str(staging))
    from fruth_core import process_ownership
    OWNER = process_ownership
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(OwnershipChecks))
    (WORK / 'results.json').write_text(json.dumps(dict(tests=result.testsRun, passed=result.wasSuccessful(),
        failures=[(str(t), s) for t, s in result.failures + result.errors], source=hashes, cases=RECEIPTS), indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()
