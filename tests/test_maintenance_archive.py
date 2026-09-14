from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
from types import SimpleNamespace

import pytest

from scripts import maintenance_archive as archive
from test_clean_repo_state_policy import make_isolated_cleanup_repo, run_isolated_cleanup


EVIDENCE_ROOTS = ('state/self_attack', 'state/benchmarks', 'state/diagnostics', 'ollmo_research')


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
    for relative in ('scripts/reusable.py', 'tests/test_reusable.py', 'ollmo_services/owner.py', 'docs/guide.md', 'plans/note.md'):
        files[relative] = b'active repository implementation\n'
    for relative, body in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    (root / 'state/self_attack/completed/replay.py').chmod(0o755)
    return files


@pytest.mark.parametrize('flags', [(), ('--full',), ('--empty-state',), ('--forget-ghost',), ('--archive',), ('--archive', '--full'), ('--archive', '--full', '--forget-ghost')])
def test_cleanup_preserves_all_evidence_and_reusable_code(tmp_path: Path, flags: tuple) -> None:
    root, env, _ = make_isolated_cleanup_repo(tmp_path)
    files = evidence_fixture(root)
    old_cache = root / '.ollmo_archiv/old/state/self_attack/old/__pycache__/proof.pyc'
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
        destination, = [p for p in (root / '.ollmo_archiv').iterdir() if p.name != 'old']
        for relative, body in files.items():
            if relative.startswith(EVIDENCE_ROOTS):
                assert (destination / relative).read_bytes() == body
            else:
                assert not (destination / relative).exists()
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
        if relative == 'ollmo_research':
            assert 'snapshot protected path: ollmo_research' in result.stdout
            continue
        assert f'snapshot evidence (source stays active): {relative}/completed' in result.stdout
        assert f'snapshot evidence (source stays active): {relative}/active' in result.stdout
    assert 'selected_copy_bytes=' in result.stdout
    assert 'safety_margin_bytes=' in result.stdout
    assert not (root / '.ollmo_archiv').exists()
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
        assert not (root / '.ollmo_archiv').exists()
    if failure == 'move':
        assert (root / 'logs/runtime.log').read_bytes() == b'runtime log'


def test_preflight_estimates_bytes_margin_and_rejects_collision(tmp_path: Path, monkeypatch, capsys) -> None:
    evidence_fixture(tmp_path)
    size = sum(archive.file_bytes(archive.inventory(tmp_path / path)) for path in EVIDENCE_ROOTS)
    destination = tmp_path / '.ollmo_archiv/run'
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
        archive.preflight(root, root / '.ollmo_archiv/run', ['state/self_attack'])
    (root / '.ollmo_archiv').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match='repo-local'):
        archive.preflight(root, root / '.ollmo_archiv/run', [])


def test_missing_artifact_buckets_recreated_without_entering_research(tmp_path: Path) -> None:
    root, env, _ = make_isolated_cleanup_repo(tmp_path)
    files = evidence_fixture(root)
    shutil.rmtree(root / 'artifacts')
    result = run_isolated_cleanup(root, env, '--full')
    assert result.returncode == 0, result.stderr or result.stdout
    assert (root / 'artifacts/bundles').is_dir()
    for relative, body in files.items():
        assert (root / relative).read_bytes() == body
