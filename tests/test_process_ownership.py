"""Bounded identity/interleaving checks; native evidence has a separate fixture."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from fruth_core import process_ownership as owner
from fruth_core.registry import read_registry_entries

IDENTITY = 'Sat Oct 31 09:30:00 2026 /usr/bin/python3 worker.py'


@pytest.fixture
def observed(tmp_path, monkeypatch):
    record = dict(instance_id='fixture', backend='mlx', model='fixture', pid=999999,
                  port=12345, process_identity=IDENTITY,
                  server_command=['/usr/bin/python3', 'worker.py'])
    (tmp_path / 'model_ports.json').write_text(json.dumps([record]))
    monkeypatch.setattr(owner, 'listener_pids', lambda port: [999999])
    monkeypatch.setattr(owner, 'process_cwd', lambda pid: tmp_path)
    monkeypatch.setattr(owner, '_identity', lambda pid: IDENTITY)
    # Pure unit fixtures must not depend on the installed interpreter/symlinks.
    monkeypatch.setattr(owner, '_executable_variants', lambda exe: {exe})
    kill = Mock()
    monkeypatch.setattr(owner.os, 'kill', kill)
    return tmp_path, record, kill


def test_valid_record_and_inert_dry_run(observed, capsys):
    root, row, kill = observed
    owner.stop_listener(root, row['port'], dry_run=True)
    kill.assert_not_called()
    assert 'Would stop verified' in capsys.readouterr().out


@pytest.mark.parametrize('key,value', [('process_identity', ''), ('process_identity', 'malformed'),
    ('process_identity', IDENTITY.replace('09:30:00', '09:30:01')),
    ('pid', 999998), ('port', 12346), ('server_command', ['wrong']), ('agent', True)])
def test_stale_missing_or_conflicting_evidence_denies_signals(observed, key, value):
    root, row, kill = observed
    row[key] = value
    (root / 'model_ports.json').write_text(json.dumps([row]))
    with pytest.raises(owner.OwnershipError):
        owner.stop_listener(root, 12345)
    kill.assert_not_called()


@pytest.mark.parametrize('change', ['identity', 'cwd', 'port', 'registry'])
def test_revalidate_blocks_change_before_term(observed, monkeypatch, change):
    root, row, kill = observed
    snapshot = owner.inspect_listener(root, 12345)
    monkeypatch.setattr(owner, 'inspect_listener', lambda *a, **kw: snapshot)
    if change == 'identity':
        monkeypatch.setattr(owner, '_identity', lambda pid: IDENTITY + ' changed')
    elif change == 'cwd':
        monkeypatch.setattr(owner, 'process_cwd', lambda pid: root / 'other')
    elif change == 'port':
        monkeypatch.setattr(owner, 'listener_pids', lambda port: [999998])
    else:
        (root / 'model_ports.json').write_text('[]')
    with pytest.raises(owner.OwnershipError):
        owner.stop_listener(root, 12345)
    kill.assert_not_called()


def test_escalation_rechecks_even_after_grace_expires(observed, monkeypatch):
    root, row, kill = observed
    def term(pid, sig):
        assert sig == 15
        monkeypatch.setattr(owner, '_identity', lambda pid: IDENTITY + ' changed')
    kill.side_effect = term
    with pytest.raises(owner.OwnershipError):
        owner.stop_listener(root, 12345, grace=0)
    kill.assert_called_once_with(999999, 15)


def test_missing_identity_after_term_is_not_confirmed_exit(observed, monkeypatch):
    root, row, kill = observed
    def term(pid, sig):
        monkeypatch.setattr(owner, '_identity', lambda pid: '')
    kill.side_effect = term
    monkeypatch.setattr(owner, '_exited', lambda pid: False)
    with pytest.raises(owner.OwnershipError, match='identity unavailable after SIGTERM'):
        owner.stop_listener(root, 12345)
    kill.assert_called_once_with(999999, 15)


@pytest.mark.parametrize('exited,replacement', [(True, False), (False, False), (True, True)])
def test_exit_between_wait_observations_requires_confirmation(observed, monkeypatch, exited, replacement):
    root, row, kill = observed
    def term(pid, sig):
        def missing_cwd(pid):
            raise owner.OwnershipError('Working directory unavailable')
        monkeypatch.setattr(owner, 'process_cwd', missing_cwd)
        monkeypatch.setattr(owner, 'listener_pids', lambda port: [999998] if replacement else [])
    kill.side_effect = term
    monkeypatch.setattr(owner, '_exited', lambda pid: exited)
    if exited and not replacement:
        owner.stop_listener(root, 12345)
    else:
        with pytest.raises(owner.OwnershipError): owner.stop_listener(root, 12345)
    kill.assert_called_once_with(999999, 15)


@pytest.mark.parametrize('result', [SimpleNamespace(returncode=2, stdout='', stderr=''),
    SimpleNamespace(returncode=1, stdout='', stderr='permission denied'),
    SimpleNamespace(returncode=0, stdout='not-a-pid', stderr=''),
    SimpleNamespace(returncode=0, stdout='', stderr='')])
def test_discovery_error_is_not_available_port(monkeypatch, result):
    monkeypatch.setattr(owner, '_observe', lambda args: result)
    with pytest.raises(owner.OwnershipError):
        owner.listener_pids(12345)


def test_registry_strict_read_preserves_legacy_default(tmp_path):
    path = tmp_path / 'model_ports.json'
    path.write_text('{malformed')
    assert read_registry_entries(path) == []
    with pytest.raises(ValueError):
        read_registry_entries(path, strict=True)


def test_cleanup_scope_unchanged_and_unresolved_is_failure(tmp_path, monkeypatch, capsys):
    calls = []
    def stop(root, port, **kwargs):
        calls.append((port, kwargs))
        if port == 11434:
            raise owner.OwnershipError('missing ownership; left untouched')
    monkeypatch.setattr(owner, 'stop_listener', stop)
    assert owner.main(['cleanup', '--root', str(tmp_path), '--dry-run']) == 1
    assert [port for port, _ in calls] == [5011, *range(11434, 11551)]
    assert all(options['dry_run'] for _, options in calls)
    assert 'Unresolved ownership' in capsys.readouterr().err


def test_web_command_exact_checkout_and_argument_boundaries(tmp_path, monkeypatch):
    monkeypatch.setattr(owner, '_executable_variants', lambda exe: {exe})
    monkeypatch.setattr(owner.sys, 'executable', '/usr/bin/python3')
    assert owner._web_command('/usr/bin/python3 fruth_webserver.py', tmp_path)
    assert owner._web_command(f'/usr/bin/python3 {tmp_path}/fruth_webserver.py', tmp_path)
    for command in ('/usr/bin/python3 -c fruth_webserver.py',
                    '/usr/bin/python3 /another/checkout/fruth_webserver.py',
                    '/other/python3 fruth_webserver.py',
                    '/usr/bin/python3 fruth_webserver.py --unexpected'):
        assert not owner._web_command(command, tmp_path)
