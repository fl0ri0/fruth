"""Ownership fixtures use synthetic registry and OS observations, never live PIDs."""
import json
from unittest.mock import Mock

import pytest

from fruth_runtime import apple_fm_model_manager as fm
from fruth_runtime import apple_pcc_model_manager as pcc

OLD = 'Wed 14 Oct 21:21:30 2026'
NEW = 'Wed Oct 14 21:21:30 2026'


def setup_stop(tmp_path, monkeypatch, manager, stored=OLD, observed=NEW):
    is_fm = manager is fm
    command = ['/usr/bin/fm', 'serve', '--host', '127.0.0.1', '--port', '11601'] if is_fm else manager._server_command(11651)
    suffix = '     ' + ' '.join(command)
    path = tmp_path / 'registry.json'
    row = dict(instance_id='fixture', backend='apple_fm' if is_fm else 'apple_pcc',
               pid=987654, port=11601 if is_fm else 11651,
               process_identity=stored + suffix, server_command=command)
    path.write_text(json.dumps([row, {'instance_id': 'unrelated', 'backend': 'ollama', 'user_setting': 'preserve'}]))
    monkeypatch.setattr(manager, 'pid_is_running', lambda _: True)
    monkeypatch.setattr(manager, 'process_identity', Mock(side_effect=[observed + suffix, '', '']))
    kill = Mock()
    monkeypatch.setattr(manager.os, 'kill', kill)
    stop = manager.stop_apple_fm_instance if is_fm else manager.stop_apple_pcc_instance
    return path, row, kill, lambda: stop('fixture', config_path=path)


@pytest.mark.parametrize('manager', [fm, pcc])
def test_observed_legacy_format_through_stop(tmp_path, monkeypatch, manager):
    path, row, kill, stop = setup_stop(tmp_path, monkeypatch, manager)
    assert stop()[0]
    kill.assert_called_once_with(row['pid'], 15)
    remaining = manager.read_registry_entries(path)
    assert len(remaining) == 1
    assert remaining[0]['instance_id'] == 'unrelated'
    assert remaining[0]['backend'] == 'ollama'
    assert remaining[0]['user_setting'] == 'preserve'


@pytest.mark.parametrize('stored,observed', [(OLD, NEW), (NEW, OLD), (NEW, NEW), (OLD, OLD),
    ('Thu  1 Oct 01:02:03 2026', 'Thu Oct  1 01:02:03 2026')])
def test_supported_formats(stored, observed):
    assert fm.process_identity_matches(observed + ' /usr/bin/fm serve', stored + ' /usr/bin/fm serve')


@pytest.mark.parametrize('value', [None, '', {}, 'birth /usr/bin/fm serve',
    'Wed 10 14 21:21:30 2026 /usr/bin/fm serve',
    'Wed Okt 14 21:21:30 2026 /usr/bin/fm serve',
    'Thu Oct 14 21:21:30 2026 /usr/bin/fm serve',
    'Wed Oct 32 21:21:30 2026 /usr/bin/fm serve',
    'Wed Oct 14 25:21:30 2026 /usr/bin/fm serve',
    NEW, NEW + ' fm serve', NEW + ' /usr/bin/fm\nother',
    NEW + ' /usr/bin/fm\x00serve'])
def test_insufficient_evidence_never_matches_even_itself(value):
    assert not fm.process_identity_matches(value, value)


@pytest.mark.parametrize('manager', [fm, pcc])
@pytest.mark.parametrize('mutation', ['birth', 'executable', 'command', 'missing', 'malformed', 'record_command'])
def test_stop_rejects_ownership_changes(tmp_path, monkeypatch, manager, mutation):
    path, row, kill, stop = setup_stop(tmp_path, monkeypatch, manager)
    identity = NEW + '     ' + ' '.join(row['server_command'])
    if mutation == 'birth':
        identity = identity.replace('21:21:30', '21:21:31')
    elif mutation == 'executable':
        identity = NEW + ' /other/executable ' + ' '.join(row['server_command'][1:])
    elif mutation == 'command':
        identity += ' --extra'
    elif mutation == 'missing':
        identity = ''
    elif mutation == 'malformed':
        identity = 'birth ' + ' '.join(row['server_command'])
        row['process_identity'] = identity
        path.write_text(json.dumps([row]))
    else:
        row['server_command'][-1] = '11999'
        path.write_text(json.dumps([row]))
    before = path.read_bytes()
    monkeypatch.setattr(manager, 'process_identity', lambda _: identity)
    with pytest.raises(RuntimeError, match='ownership'):
        stop()
    kill.assert_not_called()
    assert path.read_bytes() == before


@pytest.mark.parametrize('locale', ['C', 'en_GB.UTF-8', 'de_CH.UTF-8'])
def test_capture_pins_locale_and_retains_credential_sanitization(monkeypatch, locale):
    monkeypatch.setenv('LC_ALL', locale)
    monkeypatch.setenv('LC_TIME', locale)
    monkeypatch.setenv('LANG', locale)
    monkeypatch.setenv('FRUTH_GRAPH_REBASE_OPERATOR_TOKEN', 'fixture-secret')
    def fake_ps(argv, **kwargs):
        assert argv == ['ps', '-ww', '-p', '987654', '-o', 'lstart=', '-o', 'command=']
        assert kwargs['env']['LC_ALL'] == kwargs['env']['LANG'] == 'C'
        assert 'FRUTH_GRAPH_REBASE_OPERATOR_TOKEN' not in kwargs['env']
        assert kwargs['timeout'] == 5
        return Mock(returncode=0, stdout=NEW + '     /usr/bin/fm serve\n')
    monkeypatch.setattr(fm.subprocess, 'run', fake_ps)
    assert fm.process_identity(987654) == NEW + '     /usr/bin/fm serve'


@pytest.mark.parametrize('code,stdout', [(1, ''), (0, ''), (0, 'birth /usr/bin/fm'),
                                       (0, NEW + ' /usr/bin/fm\nother')])
def test_capture_absent_or_invalid(monkeypatch, code, stdout):
    monkeypatch.setattr(fm.subprocess, 'run', lambda *a, **k: Mock(returncode=code, stdout=stdout))
    assert fm.process_identity(987654) == ''


@pytest.mark.parametrize('manager', [fm, pcc])
def test_disappeared_before_observation_does_not_signal(tmp_path, monkeypatch, manager):
    path, row, kill, stop = setup_stop(tmp_path, monkeypatch, manager)
    monkeypatch.setattr(manager, 'pid_is_running', lambda _: False)
    assert stop()[0]
    kill.assert_not_called()


@pytest.mark.parametrize('manager', [fm, pcc])
def test_disappeared_between_liveness_and_identity_refuses(tmp_path, monkeypatch, manager):
    path, row, kill, stop = setup_stop(tmp_path, monkeypatch, manager)
    monkeypatch.setattr(manager, 'process_identity', lambda _: '')
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match='ownership'):
        stop()
    kill.assert_not_called()
    assert path.read_bytes() == before


@pytest.mark.parametrize('manager', [fm, pcc])
def test_disappeared_at_signal_retains_record(tmp_path, monkeypatch, manager):
    path, row, kill, stop = setup_stop(tmp_path, monkeypatch, manager)
    before = path.read_bytes()
    kill.side_effect = ProcessLookupError
    with pytest.raises(ProcessLookupError):
        stop()
    assert path.read_bytes() == before
    kill.assert_called_once_with(row['pid'], 15)


@pytest.mark.parametrize('manager', [fm, pcc])
def test_reused_pid_after_signal_never_signaled_again(tmp_path, monkeypatch, manager):
    path, row, kill, stop = setup_stop(tmp_path, monkeypatch, manager)
    expected = NEW + ' ' + ' '.join(row['server_command'])
    reused = expected.replace('21:21:30', '21:21:31')
    monkeypatch.setattr(manager, 'process_identity', Mock(side_effect=[expected, reused, reused]))
    assert stop()[0]
    kill.assert_called_once_with(row['pid'], 15)


@pytest.mark.parametrize('manager', [fm, pcc])
def test_still_running_timeout_retains_record_without_escalation(tmp_path, monkeypatch, manager):
    path, row, kill, stop = setup_stop(tmp_path, monkeypatch, manager)
    before = path.read_bytes()
    monkeypatch.setattr(manager, 'process_identity', lambda _: NEW + ' ' + ' '.join(row['server_command']))
    monkeypatch.setattr(manager.time, 'monotonic', Mock(side_effect=[0, 6]))
    assert stop()[0] is False
    assert path.read_bytes() == before
    kill.assert_called_once_with(row['pid'], 15)


@pytest.mark.parametrize('manager', [fm, pcc])
def test_positive_through_core_lifecycle(tmp_path, monkeypatch, manager):
    from fruth_core import lifecycle
    path, row, kill, stop = setup_stop(tmp_path, monkeypatch, manager)
    result, target = lifecycle.stop_instance('fixture', config_path=str(path))
    assert result.state == 'stopped'
    assert target['pid'] == row['pid']
    kill.assert_called_once_with(row['pid'], 15)


@pytest.mark.parametrize('manager', [fm, pcc])
def test_wait_rechecks_legacy_identity_and_preserves_concurrent_sibling(tmp_path, monkeypatch, manager):
    path, row, kill, stop = setup_stop(tmp_path, monkeypatch, manager)
    identity = NEW + ' ' + ' '.join(row['server_command'])
    monkeypatch.setattr(manager, 'process_identity', Mock(side_effect=[identity, identity, '', '']))
    wait = Mock(side_effect=ChildProcessError)
    monkeypatch.setattr(manager.os, 'waitpid', wait)
    monkeypatch.setattr(manager.time, 'sleep', lambda _: None)
    def signal(pid, sig):
        entries = json.loads(path.read_text())
        entries.append({'instance_id': 'concurrent', 'backend': 'ollama', 'user_setting': 'new'})
        path.write_text(json.dumps(entries))
    kill.side_effect = signal
    assert stop()[0]
    wait.assert_called_once_with(row['pid'], manager.os.WNOHANG)
    kill.assert_called_once_with(row['pid'], 15)
    remaining = manager.read_registry_entries(path)
    assert {r['instance_id'] for r in remaining} == {'unrelated', 'concurrent'}
    assert next(r for r in remaining if r['instance_id'] == 'concurrent')['user_setting'] == 'new'


def test_afm_record_command_must_match_complete_executable(tmp_path, monkeypatch):
    path, row, kill, stop = setup_stop(tmp_path, monkeypatch, fm)
    row['process_identity'] = NEW + ' /other' + ' '.join(row['server_command'])
    path.write_text(json.dumps([row]))
    monkeypatch.setattr(fm, 'process_identity', lambda _: row['process_identity'])
    with pytest.raises(RuntimeError, match='ownership'):
        stop()
    kill.assert_not_called()
