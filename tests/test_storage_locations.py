from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from scripts import storage_locations as storage


def configure(root, **sections):
    path = root / storage.CONFIG
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(version=1, **sections)))
    return path


def external(path, **extra):
    return dict(id='external', path=str(path), **extra)


def test_absent_configuration_keeps_defaults_without_creating_them(tmp_path):
    for kind, relative in storage.DEFAULTS.items():
        assert storage.write_root(tmp_path, kind) == tmp_path / relative
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('section', [
    {'default_enabled': False}, {'write_target': 'missing'},
    {'default_enabled': 1}, {'locations': {}}, {'unknown': True},
    {'locations': [{'id': 'default', 'path': 'old'}]},
    {'locations': [{'id': 'x', 'path': 'old', 'write': 'true'}]},
    {'locations': [{'id': 'x', 'path': ''}]},
    {'locations': [{'id': 'x', 'path': 'old\nroot'}]},
    {'locations': [{'id': 'x', 'path': 'old', 'unknown': 1}]},
    {'locations': [{'id': 'x', 'path': 'state/other'}]},
    {'locations': [{'id': 'x', 'path': '.'}]},
    {'locations': [{'id': 'x', 'path': '..'}]},
    {'locations': [{'id': 'x', 'path': '.fruth_archiv/nested'}]},
    {'locations': [{'id': 'x', 'path': 'htmlcov/archive'}]},
    {'locations': [{'id': 'x', 'path': 'model_ports.json'}]},
    {'locations': [{'id': 'x', 'path': 'data/__pycache__/archive'}]},
    {'locations': [{'id': 'x', 'path': 'old'}, {'id': 'x', 'path': 'older'}]},
])
def test_invalid_configuration_fails_before_effects(tmp_path, section):
    config = configure(tmp_path, archive=section)
    before = config.read_bytes()
    with pytest.raises(ValueError):
        storage.write_root(tmp_path, 'archive')
    assert config.read_bytes() == before
    assert not (tmp_path / '.fruth_archiv').exists()


@pytest.mark.parametrize('raw', ['{"version":true}', '{"version":2}',
                                 '{"version":1,"version":1}', '[]', '{'])
def test_invalid_top_level_and_duplicate_keys(tmp_path, raw):
    configure(tmp_path).write_text(raw)
    with pytest.raises(ValueError):
        storage.load(tmp_path)


def test_one_writer_multiple_readers_and_disabled_default(tmp_path):
    root, first, second = [tmp_path / p for p in ('repo', 'disk one', 'disk two')]
    first.mkdir(); second.mkdir()
    configure(root, archive=dict(default_enabled=False, write_target='external',
        locations=[external(first, write=True), dict(id='older', path=str(second))]))
    assert storage.write_root(root, 'archive') == first
    (second / 'old-run').mkdir()
    assert storage.find(root, 'archive', 'old-run') == second / 'old-run'
    (root / '.fruth_archiv/local').mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        storage.find(root, 'archive', 'local')
    configure(root, archive=dict(default_enabled=False, write_target=None))
    with pytest.raises(ValueError, match='No write target'):
        storage.write_root(root, 'archive')


def test_missing_media_never_creates_path_or_falls_back(tmp_path):
    root, drive = tmp_path / 'repo', tmp_path / 'missing drive/archive'
    configure(root, archive=dict(write_target='external', locations=[external(drive, write=True)]))
    with pytest.raises(ValueError, match='unavailable; no fallback'):
        storage.write_root(root, 'archive')
    assert not drive.parent.exists()
    assert not (root / '.fruth_archiv').exists()


def test_symlink_writer_and_escaped_reader_fail(tmp_path):
    root, drive = tmp_path / 'repo', tmp_path / 'disk'
    drive.mkdir(); root.mkdir()
    (root / '.fruth_archiv').symlink_to(drive)
    with pytest.raises(ValueError, match='symlink'):
        storage.write_root(root, 'archive')
    secret = tmp_path / 'elsewhere'
    secret.mkdir()
    (drive / 'escaped').symlink_to(secret)
    with pytest.raises(ValueError, match='escapes'):
        storage.find(root, 'archive', 'escaped')


def test_external_location_cannot_alias_a_live_cleanup_input(tmp_path):
    root, live = tmp_path / 'repo', tmp_path / 'live'
    root.mkdir(); live.mkdir()
    (root / 'logs').symlink_to(live)
    configure(root, archive=dict(locations=[external(live / 'archive')]))
    with pytest.raises(ValueError, match='overlaps live'):
        storage.load(root)


def test_manual_move_resolves_exact_suffix_without_changing_bytes(tmp_path):
    root, drive = tmp_path / 'repo', tmp_path / 'disk'
    drive.mkdir()
    configure(root, self_attack=dict(locations=[external(drive)]))
    old = root / 'state/self_attack/campaign/profile/captures/response'
    old.mkdir(parents=True)
    body = json.dumps(dict(original_path=str(old), digest='historical')).encode()
    (old / 'capture.json').write_bytes(body)
    shutil.move(root / 'state/self_attack/campaign', drive / 'campaign')
    selected = storage.find(root, 'self_attack', 'campaign')
    relocated = storage.evidence_path(root, old, selected)
    assert relocated == drive / 'campaign/profile/captures/response'
    assert (relocated / 'capture.json').read_bytes() == body
    with pytest.raises(FileNotFoundError, match='Unknown recorded'):
        storage.evidence_path(root, tmp_path / 'unknown/campaign/profile', selected)
    with pytest.raises(ValueError, match='outside'):
        storage.evidence_path(root, relocated, drive / 'different-campaign')
    with pytest.raises(ValueError, match='traversal'):
        storage.evidence_path(root, '../other', selected)


def test_duplicates_require_explicit_path_and_existing_old_copy_is_not_substituted(tmp_path):
    root, drive = tmp_path / 'repo', tmp_path / 'disk'
    drive.mkdir()
    configure(root, self_attack=dict(locations=[external(drive)]))
    old = root / 'state/self_attack/run'
    old.mkdir(parents=True); (drive / 'run').mkdir()
    with pytest.raises(ValueError, match='Ambiguous'):
        storage.find(root, 'self_attack', 'run')
    assert storage.find(root, 'self_attack', drive / 'run') == drive / 'run'
    with pytest.raises(ValueError, match='outside'):
        storage.evidence_path(root, old, drive / 'run')


def test_status_and_list_are_read_only(tmp_path, capsys):
    assert storage.main(['--root', str(tmp_path), 'list', 'archive']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['write_target'] == 'default'
    assert result['locations'][0]['available'] is False
    assert list(tmp_path.iterdir()) == []


def test_runner_defaults_and_detach_freeze_the_selected_destinations(tmp_path, monkeypatch):
    from scripts import fruth_self_attack as runner
    root, drive = tmp_path / 'repo', tmp_path / 'disk'
    drive.mkdir()
    configure(root, self_attack=dict(write_target='external', locations=[external(drive, write=True)]))
    monkeypatch.setattr(runner, 'ROOT', root)
    assert runner.storage_output(None, 'run') == drive / 'run'
    assert runner.storage_output(tmp_path / 'explicit', 'run') == tmp_path / 'explicit'
    launched = []
    monkeypatch.setattr(runner, 'launch_detached', lambda argv, output: launched.append((output, argv)) or 0)
    assert runner.main(['--detach']) == 0
    output, argv = launched.pop()
    assert output.parent == drive
    assert argv[argv.index('--regressions') + 1] == str(drive / 'regressions')
    assert output.is_dir() and list(output.iterdir()) == []


def test_relocated_capture_uses_selected_tree_and_checks_response_identity(tmp_path, monkeypatch):
    from scripts import self_attack_windows as windows
    root, drive = tmp_path / 'repo', tmp_path / 'disk'
    drive.mkdir()
    configure(root, self_attack=dict(locations=[external(drive)]))
    monkeypatch.setattr(windows, 'ROOT', root)
    old = root / 'state/self_attack/run/captures/r1'
    new = drive / 'run/captures/r1'
    new.mkdir(parents=True)
    capture = new / 'settled.json'
    capture.write_text(json.dumps(dict(source='settled', observed_ns=1, payload={'id': 'r1'}), sort_keys=True))
    case = dict(capture_path=str(old), response_id='r1')
    assert windows.final_capture(case, drive / 'run')[0] == capture
    with pytest.raises(windows.CorpusError, match='identity'):
        windows.final_capture(dict(case, response_id='other'), drive / 'run')


def test_release_requires_storage_owner(tmp_path):
    from test_release_archive import _make_release_source
    from scripts import build_release_archive as release
    root = _make_release_source(tmp_path)
    (root / 'scripts/storage_locations.py').unlink()
    with pytest.raises(release.ReleaseArchiveError, match='storage_locations'):
        release.discover_release_files(root)


def test_monitor_resolves_registered_run_without_writing(tmp_path, monkeypatch, capsys):
    from scripts import self_attack_monitor as monitor
    root, drive = tmp_path / 'repo', tmp_path / 'disk'
    run = drive / 'finished-run'
    run.mkdir(parents=True)
    configure(root, self_attack=dict(locations=[external(drive)]))
    (run / 'run.json').write_text(json.dumps(dict(mode='live', profiles=[], corpus={'cases': []})))
    (run / 'completion.json').write_text('{"exit_code":2}')
    before = {p.name: p.read_bytes() for p in run.iterdir()}
    monkeypatch.setattr(monitor, 'CHECKOUT', root)
    monkeypatch.setattr(monitor, 'ROOT', root)
    monitor.main(['finished-run', '--once'])
    assert 'FINISHED' in capsys.readouterr().out
    assert {p.name: p.read_bytes() for p in run.iterdir()} == before
