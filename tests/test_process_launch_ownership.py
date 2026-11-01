"""Pure launch-boundary controls. Native launch→registry→cleanup is separate."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from fruth_core import process_ownership as owner
from fruth_core import registry

IDENTITY = 'Sat Oct 31 09:30:00 2026 /fixture/server --port 12345'
COMMAND = ['/fixture/server', '--port', '12345']


@pytest.fixture
def child(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(owner, '_identity', lambda pid: IDENTITY)
    monkeypatch.setattr(owner, 'process_cwd', lambda pid: tmp_path)
    monkeypatch.setattr(owner, 'listener_pids', lambda port: [123456])
    process = SimpleNamespace(pid=123456, poll=Mock(return_value=None), terminate=Mock(),
                              kill=Mock(), wait=Mock())
    return process


def test_capture_is_bound_to_live_child_and_original_command(child):
    spawned = owner.capture_spawned_process(child, COMMAND)
    assert spawned.child is child and spawned.pid == child.pid
    assert owner.verify_spawned_process(spawned, port=12345) == dict(process_identity=IDENTITY, server_command=COMMAND)


@pytest.mark.parametrize('mutation', ['exited', 'command', 'missing', 'cwd'])
def test_capture_refuses_unknown_or_changed_identity(child, monkeypatch, mutation, tmp_path):
    if mutation == 'exited': child.poll.return_value = 1
    elif mutation == 'command': monkeypatch.setattr(owner, '_identity', lambda pid: IDENTITY + ' changed')
    elif mutation == 'missing': monkeypatch.setattr(owner, '_identity', lambda pid: '')
    else: monkeypatch.setattr(owner, 'process_cwd', lambda pid: tmp_path / 'other')
    with pytest.raises(owner.OwnershipError): owner.capture_spawned_process(child, COMMAND)
    child.terminate.assert_not_called()
    child.kill.assert_not_called()


@pytest.mark.parametrize('mutation', ['birth', 'pid', 'port', 'exited'])
def test_readiness_never_recaptures_or_adopts_foreign_listener(child, monkeypatch, mutation):
    spawned = owner.capture_spawned_process(child, COMMAND)
    if mutation == 'birth': monkeypatch.setattr(owner, '_identity', lambda pid: IDENTITY.replace('09:30:00', '09:30:01'))
    elif mutation == 'pid': child.pid += 1
    elif mutation == 'port': monkeypatch.setattr(owner, 'listener_pids', lambda port: [654321])
    else: child.poll.return_value = 1
    with pytest.raises(owner.OwnershipError): owner.verify_spawned_process(spawned, port=12345)
    assert spawned.identity == IDENTITY


def test_failed_launch_cleanup_rechecks_before_escalating(child, monkeypatch):
    import subprocess
    spawned = owner.capture_spawned_process(child, COMMAND)
    def waited(**kwargs):
        monkeypatch.setattr(owner, '_identity', lambda pid: IDENTITY + ' replaced')
        raise subprocess.TimeoutExpired('fixture', 1)
    child.wait.side_effect = waited
    with pytest.raises(owner.OwnershipError): owner.terminate_spawned_process(spawned)
    child.terminate.assert_called_once()
    child.kill.assert_not_called()


@pytest.mark.parametrize('transition', ['expected', 'birth', 'command', 'missing'])
def test_framework_exec_is_only_accepted_at_capture_with_same_birth(child, monkeypatch, transition):
    framework = '/fixture/Python.app/Contents/MacOS/Python'
    final = IDENTITY.replace('/fixture/server', framework)
    if transition == 'birth': final = final.replace('09:30:00', '09:30:01')
    elif transition == 'command': final += ' changed'
    elif transition == 'missing': final = ''
    monkeypatch.setattr(owner, '_framework_python_executable', lambda exe: framework)
    monkeypatch.setattr(owner, '_identity', Mock(side_effect=[IDENTITY, final, final]))
    if transition == 'expected':
        spawned = owner.capture_spawned_process(child, COMMAND)
        assert spawned.identity == final
        # A reversal after capture is still a changed identity, never recaptured.
        monkeypatch.setattr(owner, '_identity', lambda pid: IDENTITY)
        with pytest.raises(owner.OwnershipError): owner.verify_spawned_process(spawned)
    else:
        with pytest.raises(owner.OwnershipError): owner.capture_spawned_process(child, COMMAND)
    child.terminate.assert_not_called()
    child.kill.assert_not_called()


def test_service_survives_model_snapshot_without_becoming_model(tmp_path, monkeypatch):
    path = tmp_path / 'model_ports.json'
    service = dict(instance_id='ollama-default', backend='ollama', runtime_service='ollama_default',
                   pid=123456, port=11434, process_identity=IDENTITY, server_command=COMMAND)
    registry.write_registry_entries([service], path=path)
    before = registry.read_registry_entries(path)[0]
    # Also reject stale ownership supplied by a caller's earlier model snapshot.
    stale = {**service, 'process_identity': 'stale'}
    registry.write_registry_entries([stale, {'instance_id': 'model-1', 'model': 'fixture', 'port': 11435}],
                                    path=path, preserve_services=True)
    assert registry.read_registry_entries(path)[-1] == before
    assert [e['instance_id'] for e in registry.list_runtime_entries(path=path, prune=False)] == ['model-1']
    sync = Mock()
    monkeypatch.setattr(registry, '_sync_downstream_integrations', sync)
    registry.write_registry_entries([service], path=path, sync_external=True)
    sync.assert_called_once_with([])


def test_service_preservation_does_not_hide_corrupt_registry(tmp_path):
    path = tmp_path / 'model_ports.json'
    path.write_text('{bad')
    with pytest.raises(ValueError): registry.write_registry_entries([], path=path, preserve_services=True)
    assert path.read_text() == '{bad'
