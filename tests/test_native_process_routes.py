"""Real owned-process identity and fail-closed native runner controls; no servers."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from scripts.test_process_routes import ProcessRoutes, native_profile

ROOT = Path(__file__).resolve().parents[1]


def test_native_identity_capture_and_legacy_comparison(tmp_path):
    from fruth_runtime import apple_fm_model_manager as fm
    from fruth_runtime import apple_pcc_model_manager as pcc
    # This is intentionally a sleep process, not an impersonated AFM/PCC service.
    child = subprocess.Popen(['/bin/sleep', '30'], cwd=ROOT)
    try:
        deadline = time.monotonic() + 5
        while True:
            first = fm.process_identity(child.pid)
            parsed = fm._parsed_process_identity(first)
            if parsed and parsed[1] == '/bin/sleep 30':
                break
            assert time.monotonic() < deadline, 'Disposable sleep did not finish exec startup'
            time.sleep(.01)
        second = fm.process_identity(child.pid)
        assert first and first == second
        date, command = fm._parsed_process_identity(first)
        fields = first.split(maxsplit=5)
        legacy = f'{fields[0]} {fields[2]} {fields[1]} {fields[3]} {fields[4]} {fields[5]}'
        assert fm.process_identity_matches(first, legacy)
        assert pcc.process_identity_matches(first, legacy)
        assert not fm.process_identity_matches(first, legacy + ' altered')
        assert not fm.process_identity_matches(first, first.replace('/bin/sleep', '/bin/other'))
        assert command == '/bin/sleep 30'
        receipt = dict(pid=child.pid, first=first, second=second, legacy=legacy,
                       afm_comparison=True, pcc_comparison=True, service_lifecycle=False)
        (tmp_path / 'native-identity.json').write_text(json.dumps(receipt, indent=2))
    finally:
        child.terminate()
        child.wait(timeout=5)
    assert child.returncode == -15


def controller(tmp_path):
    work = tmp_path / 'phase'
    (work / 'temporary').mkdir(parents=True)
    manifest = {str(p.relative_to(ROOT)): __import__('hashlib').sha256(p.read_bytes()).hexdigest()
                for p in (ROOT / 'tests').glob('test_*.py')}
    route = ProcessRoutes(source=ROOT, work=work, environment=dict(os.environ), manifest=manifest)
    route.active = 'tests/test_frontend_apple_pcc.py::test_pcc_tab_and_preferred_ii_use_normal_instance_controls'
    return route


def test_admission_rejects_altered_commands_paths_environments_and_unowned_pids(tmp_path):
    route = controller(tmp_path)
    program = next(p for p in route.programs['test_frontend_apple_pcc.py'] if "const fs = require('fs'), vm" in p)
    command = ['node','-e',program]
    assert route.classify(command, ROOT, None)[0] == 'node'
    changes = [(['node','-e',program+';process.exit(0)'], ROOT, None),
               (['/bin/sh','-c','true'], ROOT, None),
               (['node','--eval',program], ROOT, None),
               (command, tmp_path, None),
               (command, ROOT, dict(os.environ, NODE_OPTIONS='--require /outside')),
               (command, ROOT, dict(os.environ, PYTHONPATH='/outside')),
               (command, ROOT, dict(os.environ, HOME='/outside'))]
    for args, cwd, env in changes:
        with pytest.raises(PermissionError): route.classify(args,cwd,env)
    route.active = 'tests/test_native_process_routes.py::test_native_identity_capture_and_legacy_comparison'
    for pid in (os.getpid(), 1, -1):
        with pytest.raises(PermissionError):
            route.classify(['ps','-ww','-p',str(pid),'-o','lstart=','-o','command='],ROOT,None)
    route.active = 'tests/test_response_frames.py::control'
    for path in ('/outside/frames', str(ROOT/'state/response_frames')):
        with pytest.raises(PermissionError):
            route.classify([sys.executable,'scripts/attest_response_frame_index.py','--frames-dir',path], ROOT, None)


def test_native_containment_denies_external_io_exec_and_signal(tmp_path):
    canary = Path(os.environ['FRUTH_COLD_PLAN']) / 'native-outside-canary'
    canary.write_text('retained')
    child = subprocess.Popen(['/bin/sleep','30'], cwd=ROOT)
    try:
        program = '''import json,os,pathlib,socket,subprocess,sys
out = {}
for name, operation in [
 ('read', lambda: pathlib.Path(sys.argv[1]).read_text()),
 ('write', lambda: pathlib.Path(sys.argv[1]).write_text('changed')),
 ('network', lambda: socket.socket().connect(('127.0.0.1',9))),
 ('exec', lambda: subprocess.run(['/bin/echo','forbidden'],check=True)),
 ('signal', lambda: os.kill(int(sys.argv[2]),18))]:
 try:
  operation()
 except (OSError,subprocess.SubprocessError):
  out[name] = 'denied'
 else:
  out[name] = 'ALLOWED'
print(json.dumps(out))
'''
        result = subprocess.run([sys.executable,'-c',program,str(canary),str(child.pid)],
                                cwd=ROOT, capture_output=True,text=True,check=True)
        assert json.loads(result.stdout) == dict.fromkeys(('read','write','network','exec','signal'),'denied')
        assert canary.read_text() == 'retained'
        assert child.poll() is None
        owned_pid = child.pid
        try:
            child.pid = os.getpid()
            with pytest.raises(PermissionError, match='ownership changed'):
                child.terminate()
        finally:
            child.pid = owned_pid
    finally:
        child.terminate(); child.wait(timeout=5)


def test_fixture_executable_and_source_drift_fail_closed(tmp_path):
    route = controller(tmp_path)
    executable = route.work / 'temporary/lsof'
    executable.write_text('#!/bin/sh\nexit 1\n')
    route.fixture_executable(executable, 'test_clean_repo_state_policy.py')
    executable.write_text('#!/bin/sh\n/bin/echo altered\n')
    with pytest.raises(PermissionError):
        route.fixture_executable(executable, 'test_clean_repo_state_policy.py')
    unknown = executable.with_name('unreviewed-program')
    unknown.write_text('#!/bin/sh\nexit 1\n')
    with pytest.raises(PermissionError):
        route.fixture_executable(unknown, 'test_clean_repo_state_policy.py')
    alias = route.work / 'temporary/alias'
    alias.symlink_to(ROOT / 'scripts/attest_response_frame_index.py')
    with pytest.raises(PermissionError): route.temporary(alias)
    with pytest.raises(PermissionError): route.source_file(alias)
    source = route.work / 'temporary/source'
    source.mkdir()
    owner = source / 'owner.py'
    owner.write_text('before')
    route.source = source
    route.manifest = {'owner.py': __import__('hashlib').sha256(owner.read_bytes()).hexdigest()}
    assert route.source_file(owner) == owner
    owner.write_text('after')
    with pytest.raises(PermissionError): route.source_file(owner)


def test_cli_requires_exact_shapes_and_disposable_paths(tmp_path):
    route = controller(tmp_path)
    path = str(route.work / 'temporary/output')
    route.cli_arguments('test_self_learning.py', 'manage_self_learning_policy.py', ['--snapshot',path,'init'])
    for args in ([], ['init'], ['--snapshot',path,'init','enable'], ['--snapshot',str(ROOT/'state/policy'),'init']):
        with pytest.raises(PermissionError):
            route.cli_arguments('test_self_learning.py', 'manage_self_learning_policy.py', args)
    for args in (['--no-persist'], ['--frames',path,'--merge-existing'], ['--frames',path,'--unknown']):
        with pytest.raises(PermissionError):
            route.cli_arguments('test_self_learning.py', 'build_self_learning_eval_cases.py', args)


def test_codex_fixture_route_binds_bytes_paths_arguments_and_environment(tmp_path):
    from tests.test_codex_execution import FAKE_CODEX_SOURCE
    route = controller(tmp_path)
    route.active = 'tests/test_codex_execution.py::CodexExecutionTests::test_login_status_probe_is_structured_and_cached'
    cwd = route.work / 'temporary'
    executable = cwd / 'codex'
    body = f'#!{sys.executable}\n{FAKE_CODEX_SOURCE}'
    executable.write_text(body)
    executable.chmod(0o755)
    command = [str(executable), 'login', 'status']
    assert route.classify(command, cwd, None)[0] == 'codex-fixture'
    alias = cwd / 'alias'
    alias.symlink_to(executable)
    outside = tmp_path / 'codex'
    outside.write_text(body)
    outside.chmod(0o755)
    cases = [([str(outside), '--version'], cwd, None),
             ([str(alias), '--version'], cwd, None),
             (['/bin/sh', '-c', 'true'], cwd, None),
             ([str(executable), 'exec', '--dangerously-bypass-approvals-and-sandbox'], cwd, None),
             (command, ROOT, None),
             (command, cwd, dict(os.environ, PYTHONPATH='/outside')),
             (command, cwd, dict(os.environ, OPENAI_API_KEY='unapproved-value')),
             (command, cwd, dict(os.environ, FAKE_CODEX_CALL_LOG=str(outside)))]
    for args, directory, env in cases:
        with pytest.raises(PermissionError):
            route.classify(args, directory, env)
    prefix = [str(executable), 'exec', '--ephemeral', '--ignore-user-config', '--ignore-rules',
              '--skip-git-repo-check', '--sandbox', 'read-only', '--color', 'never',
              '--output-last-message', str(cwd / 'last-message.txt')]
    assert route.classify(prefix + ['-'], cwd, None)[0] == 'codex-fixture'
    for tail in (['--image', '../outside.png', '-'], ['--image', '/outside.png', '-'],
                 ['--image', 'inputs/input-01.png', '-'], ['--model', 'anything', '-']):
        with pytest.raises(PermissionError):
            route.classify(prefix + tail, cwd, None)
    executable.write_text(body + '\nprint("altered")\n')
    with pytest.raises(PermissionError):
        route.classify(command, cwd, None)


def test_new_session_is_exclusive_to_exact_codex_route_and_other_options_stay_denied(tmp_path):
    route = controller(tmp_path)
    route.validate_launch_options('codex-fixture', (), {'start_new_session': True})
    route.validate_launch_options('owned-sleep', (), {})
    for name, positional, options in [
        ('owned-sleep', (), {'start_new_session': True}),
        ('node', (), {'start_new_session': True}),
        ('codex-fixture', (), {}),
        ('codex-fixture', (), {'start_new_session': False}),
        ('codex-fixture', (), {'start_new_session': 1}),
        ('codex-fixture', (0,), {'start_new_session': True}),
        *[('codex-fixture', (), dict(start_new_session=True, **{key: value})) for key, value in
          [('shell', True), ('executable', '/bin/sh'), ('preexec_fn', lambda: None),
           ('pass_fds', (1,)), ('process_group', 0), ('user', 0)]]]:
        with pytest.raises(PermissionError):
            route.validate_launch_options(name, positional, options)
