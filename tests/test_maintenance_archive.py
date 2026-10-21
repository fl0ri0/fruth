from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
from types import SimpleNamespace

import pytest

from scripts import maintenance_archive as archive
from test_clean_repo_state_policy import make_isolated_cleanup_repo, run_isolated_cleanup


EVIDENCE_ROOTS = ('state/self_attack', 'state/benchmarks', 'state/diagnostics', 'fruth_research')


def evidence_fixture(root: Path) -> dict[str, bytes]:
    files = {}
    for relative in EVIDENCE_ROOTS:
        files.update({
            f'{relative}/completed/completion.json': b'{"exit_code":0,"finished_at":"2026-09-14T10:00:00Z"}',
            f'{relative}/completed/report.md': (
                b'[JSON](evidence.json) [resolution](nested/resolution/report.md) '
                b'[log](logs/run.log) [diff](retained/fix.diff) [source](source/owner.py)'
            ),
            f'{relative}/completed/evidence.json': b'{"result":"accepted"}',
            f'{relative}/completed/nested/resolution/report.md': b'[parent](../../report.md)',
            f'{relative}/completed/logs/run.log': b'all observed\n',
            f'{relative}/completed/retained/fix.diff': b'+ fix\n',
            f'{relative}/completed/source/owner.py': b'retained_source = True\n',
            f'{relative}/completed/replay.py': b'print("campaign-local evidence")\n',
            f'{relative}/completed/__pycache__/retained.pyc': b'\x00retained cache evidence',
            f'{relative}/completed/.DS_Store': b'retained metadata',
            f'{relative}/active/progress.json': b'{"status":"RUNNING"}',
            f'{relative}/active/in-progress.jsonl': b'{"pending":true}\n',
            f'{relative}/unknown/fixture.bin': b'\x00\xffunknown',
            f'{relative}/loose-evidence.json': b'{}',
        })
    for relative in ('scripts/reusable.py', 'tests/test_reusable.py', 'fruth_services/owner.py', 'docs/guide.md', 'plans/note.md'):
        files[relative] = b'active repository implementation\n'
    for relative, body in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    (root / 'state/self_attack/completed/replay.py').chmod(0o755)
    return files


@pytest.mark.parametrize('full_flag', [None, '--full', '--empty-state'])
@pytest.mark.parametrize('external_destination', [False, True])
def test_archive_can_omit_campaign_copy_without_losing_learning_or_work(
    tmp_path: Path, full_flag: str | None, external_destination: bool,
) -> None:
    from test_storage_locations import configure, external

    root, env, _ = make_isolated_cleanup_repo(tmp_path, readiness_summary={
        'status': 'unchanged', 'selected_observation_count': 1,
        'settled_observation_count': 1, 'registered_observation_count': 1,
        'missing_settled_observation_count': 0, 'active_observation_count': 0,
        'scan_error_count': 0, 'hydration_error_count': 0,
        'registry_error_count': 0, 'appended_record_count': 0,
        'already_present_count': 1, 'error_count': 0,
    })
    files = evidence_fixture(root)
    for relative, body in {
        'state/self_learning/eval_cases.jsonl': b'{"case_id":"retained"}\n',
        'state/self_learning/accepted_policy_snapshot.json': b'{"enabled":false}\n',
        'state/self_learning/retained_sidecars/proof.json': b'{"evidence":true}\n',
        'state/inference_preferences.json': b'{"preserve":"preferences"}\n',
        'state/fruth_run_monitor/last_seen.json': b'{"last":"historical"}\n',
        'state/fruth_run_monitor/reports.jsonl': b'{"response":"historical"}\n',
        'state/fruth_run_monitor/reports.md': b'Historical monitor report\n',
    }.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        files[relative] = body
    frame = (root / 'state/response_frames/responses.jsonl').read_bytes()
    archive_root = root / '.fruth_archiv'
    if external_destination:
        archive_root = tmp_path / 'external archive'
        archive_root.mkdir()
        configure(root, archive=dict(write_target='external',
                  locations=[external(archive_root, write=True)]))

    flags = ('--archive', full_flag or '--exclude-self-attack')
    result = run_isolated_cleanup(root, env, *flags)

    assert result.returncode == 0, result.stderr or result.stdout
    destination, = archive_root.iterdir()
    assert not (destination / 'state/self_attack').exists()
    assert 'archive copy bytes: state/self_attack =' not in result.stdout
    assert 'self-attack snapshot: excluded by request' in result.stdout
    for relative, body in files.items():
        if relative.startswith('state/fruth_run_monitor/'):
            if full_flag:
                assert not (root / relative).exists()
                assert (destination / relative).read_bytes() == body
            else:
                assert (root / relative).read_bytes() == body
                assert not (destination / relative).exists()
            continue
        if full_flag and relative.startswith('state/self_attack/') and len(Path(relative).parts) > 3:
            assert not (root / relative).exists()
            continue
        assert (root / relative).read_bytes() == body
        if relative.startswith(('state/self_learning/', 'state/inference_preferences',
                                'state/benchmarks/', 'state/diagnostics/', 'fruth_research/')):
            assert (destination / relative).read_bytes() == body
    assert (destination / 'artifacts/bundles/keep.html').read_text() == '<p>fixture</p>\n'
    assert (destination / 'state/response_frames/responses.jsonl').read_bytes() == frame
    assert not (root / 'state/response_frames/responses.jsonl').exists()
    assert not (root / 'artifacts/bundles/keep.html').exists()
    manifest = (destination / 'manifest.txt').read_text()
    assert 'evidence_snapshot_paths=state/benchmarks,state/diagnostics\n' in manifest
    assert 'exclude_self_attack=1\n' in manifest
    if full_flag:
        assert 'self_attack_cleanup_policy=remove_local_run_directories_without_snapshot_after_retention;' in manifest
        assert 'monitor_history_snapshot_paths=state/fruth_run_monitor/last_seen.json,state/fruth_run_monitor/reports.jsonl,state/fruth_run_monitor/reports.md\n' in manifest
    else:
        assert 'self_attack_cleanup_policy=preserve\n' in manifest


def test_campaign_exclusion_preview_is_read_only_and_matches_copy_scope(tmp_path: Path) -> None:
    root, env, _ = make_isolated_cleanup_repo(tmp_path)
    files = evidence_fixture(root)
    before = archive.inventory(root)
    result = run_isolated_cleanup(root, env, '--archive', '--full', '--dry-run')
    assert result.returncode == 0, result.stderr or result.stdout
    assert archive.inventory(root) == before
    for relative, body in files.items():
        assert (root / relative).read_bytes() == body
    assert 'archive copy bytes: state/self_attack =' not in result.stdout
    assert 'snapshot protected path: state/self_attack' not in result.stdout
    assert 'snapshot protected path: state/benchmarks' in result.stdout
    assert 'snapshot protected path: fruth_research' in result.stdout


def test_campaign_exclusion_rejects_clean_before_side_effects(tmp_path: Path) -> None:
    root, env, args_file = make_isolated_cleanup_repo(tmp_path)
    before = archive.inventory(root)
    result = run_isolated_cleanup(root, env, '--full', '--exclude-self-attack')
    assert result.returncode == 2
    assert 'requires archive mode' in result.stderr
    assert '1. Stopping' not in result.stdout
    assert not args_file.exists()
    assert archive.inventory(root) == before


def test_local_campaign_cleanup_preserves_external_targets_aliases_and_helpers(tmp_path: Path) -> None:
    root = tmp_path / 'repo'
    local = root / 'state/self_attack'
    run = local / 'run'
    run.mkdir(parents=True)
    (run / 'raw.json').write_bytes(b'local raw')
    external = tmp_path / 'external'
    external.mkdir()
    proof = external / 'proof.json'
    proof.write_bytes(b'external proof')
    (run / 'external-link').symlink_to(external, target_is_directory=True)
    (local / 'external-link').symlink_to(external, target_is_directory=True)
    (local / 'monitor.py').write_bytes(b'helper')
    (local / 'Finder alias').write_bytes(b'alias')
    before = archive.inventory(root)
    archive.clean_local_self_attack_runs(root, dry_run=True)
    assert archive.inventory(root) == before
    archive.clean_local_self_attack_runs(root, dry_run=False)
    assert not run.exists()
    assert proof.read_bytes() == b'external proof'
    assert (local / 'external-link').is_symlink()
    assert (local / 'monitor.py').read_bytes() == b'helper'
    assert (local / 'Finder alias').read_bytes() == b'alias'


def test_local_campaign_cleanup_rejects_redirected_root(tmp_path: Path) -> None:
    root = tmp_path / 'repo'
    (root / 'state').mkdir(parents=True)
    external = tmp_path / 'external'
    external.mkdir()
    proof = external / 'proof.json'
    proof.write_bytes(b'external proof')
    (root / 'state/self_attack').symlink_to(external, target_is_directory=True)
    for dry_run in (True, False):
        with pytest.raises(ValueError, match='real checkout directory'):
            archive.clean_local_self_attack_runs(root, dry_run=dry_run)
    assert proof.read_bytes() == b'external proof'


def test_local_campaign_cleanup_rejects_mount_before_any_deletion(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / 'repo'
    local = root / 'state/self_attack'
    for name in ('a-run', 'z-mount'):
        (local / name).mkdir(parents=True)
        (local / name / 'proof.json').write_bytes(b'proof')
    monkeypatch.setattr(archive.os.path, 'ismount', lambda path: Path(path).name == 'z-mount')
    with pytest.raises(ValueError, match='mounted store'):
        archive.clean_local_self_attack_runs(root, dry_run=False)
    assert (local / 'a-run/proof.json').read_bytes() == b'proof'
    assert (local / 'z-mount/proof.json').read_bytes() == b'proof'


@pytest.mark.parametrize('flags', [(), ('--full',), ('--empty-state',), ('--forget-inference',), ('--archive',), ('--archive', '--full'), ('--archive', '--full', '--forget-inference')])
def test_cleanup_preserves_all_evidence_and_reusable_code(tmp_path: Path, flags: tuple) -> None:
    root, env, _ = make_isolated_cleanup_repo(tmp_path)
    files = evidence_fixture(root)
    old_cache = root / '.fruth_archiv/old/state/self_attack/old/__pycache__/proof.pyc'
    old_cache.parent.mkdir(parents=True)
    old_cache.write_bytes(b'old archive evidence')
    ordinary_cache = root / 'scripts/__pycache__/generated.pyc'
    ordinary_cache.parent.mkdir()
    ordinary_cache.write_bytes(b'ordinary generated cache')
    result = run_isolated_cleanup(root, env, *flags)
    assert result.returncode == 0, result.stderr or result.stdout
    for relative, body in files.items():
        assert (root / relative).read_bytes() == body
    assert old_cache.read_bytes() == b'old archive evidence'
    assert not ordinary_cache.exists()
    assert not (root / 'artifacts/bundles/keep.html').exists()
    assert (root / 'artifacts/bundles').is_dir()
    if '--archive' in flags:
        destination, = [p for p in (root / '.fruth_archiv').iterdir() if p.name != 'old']
        for relative, body in files.items():
            if '--full' in flags and relative.startswith('state/self_attack/'):
                assert not (destination / relative).exists()
            elif relative.startswith(EVIDENCE_ROOTS):
                assert (destination / relative).read_bytes() == body
            else:
                assert not (destination / relative).exists()
        if '--full' not in flags:
            assert (destination / 'state/self_attack/completed/replay.py').stat().st_mode & 0o111
        for report in destination.glob('state/*/completed/**/report.md'):
            for target in re.findall(r'\]\(([^)]+)\)', report.read_text()):
                assert (report.parent / target).is_file()
        assert (destination / 'artifacts/bundles/keep.html').read_text() == '<p>fixture</p>\n'
        assert 'live_sources_preserved' in (destination / 'manifest.txt').read_text()


def test_preview_lists_evidence_bytes_and_leaves_sources_unchanged(tmp_path: Path) -> None:
    root, env, _ = make_isolated_cleanup_repo(tmp_path)
    files = evidence_fixture(root)
    result = run_isolated_cleanup(root, env, '--archive', '--dry-run')
    assert result.returncode == 0, result.stderr
    for relative in EVIDENCE_ROOTS:
        if relative == 'fruth_research':
            assert 'snapshot protected path: fruth_research' in result.stdout
            continue
        assert f'snapshot evidence (source stays active): {relative}/completed' in result.stdout
        assert f'snapshot evidence (source stays active): {relative}/active' in result.stdout
    assert 'selected_copy_bytes=' in result.stdout
    assert 'safety_margin_bytes=' in result.stdout
    assert not (root / '.fruth_archiv').exists()
    for relative, body in files.items():
        assert (root / relative).read_bytes() == body


@pytest.mark.parametrize('failure', ['copy', 'verification', 'artifact_verification', 'space', 'move'])
def test_archive_failure_never_reaches_destructive_clean(tmp_path: Path, failure: str) -> None:
    root, env, args_file = make_isolated_cleanup_repo(tmp_path)
    files = evidence_fixture(root)
    helper = root / 'scripts/maintenance_archive.py'
    source = helper.read_text()
    if failure == 'space':
        source = source.replace('free = shutil.disk_usage(ancestor).free', 'free = 0')
    elif failure == 'copy':
        source = source.replace('shutil.copytree(source, destination, symlinks=True)', 'raise OSError("injected copy failure")')
    elif failure == 'verification':
        source = source.replace('copied = inventory(destination)', "(destination / 'completed/report.md').write_bytes(b'corrupt')\n    copied = inventory(destination)")
    elif failure == 'artifact_verification':
        source = source.replace('copied = inventory(destination)', "if source.name == 'artifacts':\n        (destination / 'bundles/keep.html').write_bytes(b'corrupt')\n    copied = inventory(destination)")
    else:
        fake_mv = tmp_path / 'bin/mv'
        fake_mv.write_text('#!/bin/sh\nexit 9\n')
        fake_mv.chmod(0o755)
        log = root / 'logs/runtime.log'
        log.parent.mkdir()
        log.write_bytes(b'runtime log')
    helper.write_text(source)
    result = run_isolated_cleanup(root, env, '--archive')
    assert result.returncode != 0
    assert 'Removing repo-local generated/runtime ballast' not in result.stdout
    for relative, body in files.items():
        assert (root / relative).read_bytes() == body
    assert (root / 'artifacts/bundles/keep.html').is_file()
    assert (root / 'state/response_frames/responses.jsonl').is_file()
    if failure == 'space':
        assert not args_file.exists()  # preflight precedes retention writes and listener stops
        assert '1. Stopping' not in result.stdout
        assert not (root / '.fruth_archiv').exists()
    if failure == 'move':
        assert (root / 'logs/runtime.log').read_bytes() == b'runtime log'


def test_preflight_estimates_bytes_margin_and_rejects_collision(tmp_path: Path, monkeypatch, capsys) -> None:
    evidence_fixture(tmp_path)
    size = sum(archive.file_bytes(archive.inventory(tmp_path / path)) for path in EVIDENCE_ROOTS)
    destination = tmp_path / '.fruth_archiv/run'
    required = size + max(archive.MIN_FREE_MARGIN_BYTES, (size * archive.COPY_MARGIN_PERCENT + 99) // 100)
    monkeypatch.setattr(archive.shutil, 'disk_usage', lambda path: SimpleNamespace(free=required - 1))
    with pytest.raises(ValueError, match='Insufficient'):
        archive.preflight(tmp_path, destination, list(EVIDENCE_ROOTS))
    assert f'selected_copy_bytes={size}' in capsys.readouterr().out
    monkeypatch.setattr(archive.shutil, 'disk_usage', lambda path: SimpleNamespace(free=required))
    archive.preflight(tmp_path, destination, list(EVIDENCE_ROOTS))
    destination.mkdir(parents=True)
    with pytest.raises(ValueError, match='already exists'):
        archive.preflight(tmp_path, destination, list(EVIDENCE_ROOTS))


def test_copy_preserves_symlink_references_without_crawling(tmp_path: Path) -> None:
    source = tmp_path / 'campaign'
    source.mkdir()
    external_audio = tmp_path / 'artifacts/audio/external.wav'
    (source / 'report.md').write_text(f'[JSON](evidence.json)\n{external_audio}\n')
    (source / 'evidence.json').write_text('{}')
    (source / 'internal').symlink_to('evidence.json')
    (source / 'external').symlink_to('/unavailable/artifacts/audio/external.wav')
    destination = tmp_path / 'archived'
    archive.verified_copy(source, destination)
    assert (destination / 'internal').read_text() == '{}'
    assert (destination / 'external').readlink() == (source / 'external').readlink()
    assert (destination / 'report.md').read_bytes() == (source / 'report.md').read_bytes()
    assert set(p.name for p in source.iterdir()) == set(p.name for p in destination.iterdir())


def test_changing_source_aborts_verification_without_removal(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / 'campaign'
    source.mkdir()
    (source / 'progress.json').write_text('{"status":"RUNNING"}')
    original_copy = shutil.copytree

    def moving_copy(src, dst, **kwargs):
        original_copy(src, dst, **kwargs)
        (src / 'new-observation.json').write_text('{}')

    monkeypatch.setattr(archive.shutil, 'copytree', moving_copy)
    with pytest.raises(ValueError, match='changed during verification'):
        archive.verified_copy(source, tmp_path / 'archived')
    assert json.loads((source / 'progress.json').read_text())['status'] == 'RUNNING'
    assert (source / 'new-observation.json').exists()


def test_copy_scope_and_archive_base_symlinks_fail_safely(tmp_path: Path) -> None:
    root = tmp_path / 'repo'
    root.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    (root / 'state').mkdir()
    (root / 'state/self_attack').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        archive.preflight(root, root / '.fruth_archiv/run', ['state/self_attack'])
    (root / '.fruth_archiv').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink|overlap'):
        archive.preflight(root, root / '.fruth_archiv/run', [])


def test_missing_artifact_buckets_recreated_without_entering_research(tmp_path: Path) -> None:
    root, env, _ = make_isolated_cleanup_repo(tmp_path)
    files = evidence_fixture(root)
    shutil.rmtree(root / 'artifacts')
    result = run_isolated_cleanup(root, env, '--full')
    assert result.returncode == 0, result.stderr or result.stdout
    assert (root / 'artifacts/bundles').is_dir()
    for relative, body in files.items():
        assert (root / relative).read_bytes() == body


@pytest.mark.parametrize('flags', [(), ('--full',), ('--empty-state',), ('--forget-inference',),
    ('--archive',), ('--archive', '--full'), ('--archive', '--full', '--forget-inference')])
def test_storage_configuration_and_registered_roots_survive_all_modes(tmp_path, flags):
    from test_storage_locations import configure, external
    root, env, _ = make_isolated_cleanup_repo(tmp_path)
    archive_root = tmp_path / 'external archive'
    archive_root.mkdir()
    retained = root / 'retained-campaigns[1]/old/__pycache__/evidence.pyc'
    retained.parent.mkdir(parents=True)
    retained.write_bytes(b'retained evidence')
    (root / 'retained-link').symlink_to(root / 'retained-campaigns[1]')
    config = configure(root,
        archive=dict(default_enabled=False, write_target='external',
                     locations=[external(archive_root, write=True)]),
        self_attack=dict(locations=[external(root / 'retained-link')]))
    before = config.read_bytes()
    (root / 'logs').mkdir()
    (root / 'logs/runtime.log').write_bytes(b'archive me')
    result = run_isolated_cleanup(root, env, *flags)
    assert result.returncode == 0, result.stderr or result.stdout
    assert config.read_bytes() == before
    assert retained.read_bytes() == b'retained evidence'
    assert not (root / '.fruth_archiv').exists()
    if '--archive' in flags:
        archives = list(archive_root.iterdir())
        assert len(archives) == 1
        assert (archives[0] / 'state/storage_locations.json').read_bytes() == before
        assert (archives[0] / 'logs/runtime.log').read_bytes() == b'archive me'
        assert not (root / 'logs/runtime.log').exists()
    else:
        assert list(archive_root.iterdir()) == []


def test_missing_external_archive_stops_before_retention_or_lifecycle(tmp_path):
    from test_storage_locations import configure, external
    root, env, args_file = make_isolated_cleanup_repo(tmp_path)
    missing = tmp_path / 'missing disk/archive'
    configure(root, archive=dict(write_target='external', locations=[external(missing, write=True)]))
    before = (root / 'state/response_frames/responses.jsonl').read_bytes()
    result = run_isolated_cleanup(root, env, '--archive', '--full')
    assert result.returncode != 0
    assert 'no fallback' in result.stderr
    assert '1. Stopping' not in result.stdout
    assert not args_file.exists()
    assert not missing.parent.exists()
    assert (root / 'state/response_frames/responses.jsonl').read_bytes() == before


def test_verified_external_move_retains_source_on_bad_copy(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    source.write_bytes(b'exact original')
    destination = tmp_path / 'destination'
    real_copy = archive.shutil.copy2
    def corrupt_copy(src, dst, **kwargs):
        real_copy(src, dst, **kwargs)
        Path(dst).write_bytes(b'corrupt')
    monkeypatch.setattr(archive.shutil, 'copy2', corrupt_copy)
    with pytest.raises(ValueError):
        archive.verified_move(source, destination)
    assert source.read_bytes() == b'exact original'
    assert destination.read_bytes() == b'corrupt'


def test_verified_external_move_removes_source_only_after_exact_copy(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'proof').write_bytes(b'exact evidence')
    archive.verified_move(source, tmp_path / 'destination')
    assert not source.exists()
    assert (tmp_path / 'destination/proof').read_bytes() == b'exact evidence'
