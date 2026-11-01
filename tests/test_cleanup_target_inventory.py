"""Maintenance contracts exercised only in disposable cleanup checkouts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from test_clean_repo_state_policy import (
    REPO_ROOT,
    make_isolated_cleanup_repo,
    run_isolated_cleanup,
)


MODES = [
    (), ('--full',), ('--empty-state',), ('--forget-inference',),
    ('--reset-registry',), ('--reset-llama-catalog',),
    ('--archive',), ('--archiv',), ('--archive', '--full'),
    ('--archive', '--empty-state'), ('--archive', '--forget-inference'),
    ('--archive', '--full', '--forget-inference'),
]
VOLATILE = (
    'logs/runtime.log', 'state/chat_history/chat.json', 'state/events.jsonl',
    'state/infer_history.jsonl', 'state/artifact_registry.jsonl',
    'state/generated_image_provenance.jsonl', 'state/runtime_status.json',
    'state/response_frames/responses.jsonl', 'outputs/legacy-result.txt',
)
INFERENCE = (
    'state/inference_preferences.json', 'state/inference_compiled_memory.json',
    'state/inference_compiled_memory.md',
)
PROTECTED = (
    'state/self_learning/accepted_policy_snapshot.json',
    'state/self_learning/retained_sidecars/snapshots/content_sha256/retained.json',
    'state/inference_learning_archives/old/state/self_learning/__pycache__/proof.pyc',
    'state/self_learning/retained_sidecars/nested/.DS_Store',
    'state/self_learning/__pycache__/proof.pyc',
    'state/self_attack/nested/.DS_Store', 'state/benchmarks/__pycache__/proof.pyc',
    'state/diagnostics/nested/proof.pyo', 'fruth_research/nested/proof.pyc',
    '.fruth_archiv/old/nested/proof.pyc', '00_backup/nested/.DS_Store',
    'fruth-upload/nested/proof.pyo',
    'state/response_frame_ledger_backups/old/responses.jsonl',
    'state/inference_learned_policy.json', 'state/inference_learned_policy.md',
)
BUCKETS = (
    'audio', 'audits', 'images', 'ocr', 'transcripts', 'documents', 'manifests',
    'bundles', 'benchmarks', 'settings', 'inputs/audio', 'inputs/image',
    'inputs/pdf', 'inputs/text',
)


def populated_fixture(tmp_path: Path):
    root, env, _ = make_isolated_cleanup_repo(
        tmp_path, readiness_summary={
            'status': 'unchanged', 'selected_observation_count': 1,
            'settled_observation_count': 1, 'registered_observation_count': 1,
            'missing_settled_observation_count': 0, 'active_observation_count': 0,
            'scan_error_count': 0, 'hydration_error_count': 0,
            'registry_error_count': 0, 'error_count': 0, 'appended_record_count': 0,
        },
    )
    tool = root / 'scripts/sync_graph_rebase_readiness_registry.py'
    tool.write_text(tool.read_text().replace(
        "print('status=unchanged')",
        "print('status=verified' if '--check-only' in sys.argv else 'status=unchanged')",
    ))
    files = {}
    for relative in (*VOLATILE, *INFERENCE, *PROTECTED, 'state/llama_cpp_catalog.json'):
        body = b'{}\n' if relative.endswith(('.json', '.jsonl')) else b'synthetic retained bytes\n'
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        files[relative] = body
    (root / 'model_ports.json').write_text('[{"instance_id":"fixture"}]\n')
    files['model_ports.json'] = (root / 'model_ports.json').read_bytes()
    for bucket in BUCKETS:
        target = root / 'artifacts' / bucket
        target.mkdir(parents=True, exist_ok=True)
        (target / 'generated.bin').write_bytes(b'generated bucket content')
    for relative in ('artifacts/extra.bin', 'artifacts/inputs/unknown/input.bin',
                     '.pytest_cache/v/cache/nodeids', '.coverage', 'htmlcov/index.html',
                     '.mypy_cache/cache.json', '.ruff_cache/cache.bin',
                     'scripts/__pycache__/generated.pyc', 'scripts/nested/generated.pyo',
                     'scripts/nested/.DS_Store'):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'ordinary generated residue')
    return root, env, files


@pytest.mark.parametrize('flags', MODES)
@pytest.mark.parametrize('dry_run', [False, True])
def test_modes_match_target_and_recovery_contracts(tmp_path, flags, dry_run):
    root, env, files = populated_fixture(tmp_path)
    before_dirs = {bucket: (root / 'artifacts' / bucket).stat().st_ino for bucket in BUCKETS}
    result = run_isolated_cleanup(root, env, *flags, *(['--dry-run'] if dry_run else []))
    assert result.returncode == 0, result.stderr or result.stdout
    if dry_run:
        assert all((root / path).read_bytes() == body for path, body in files.items())
        assert not [p for p in (root / '.fruth_archiv').iterdir() if p.name != 'old']
        return

    archived = '--archive' in flags or '--archiv' in flags
    full = '--full' in flags or '--empty-state' in flags
    forget = '--forget-inference' in flags or (full and not archived)
    reset_registry = '--reset-registry' in flags or full
    reset_catalog = '--reset-llama-catalog' in flags or full
    for path in PROTECTED:
        if archived and full and path.startswith('state/self_attack/'):
            assert not (root / path).exists(), path
        else:
            assert (root / path).read_bytes() == files[path], path
    for path in VOLATILE:
        assert not (root / path).exists(), path
    for path in INFERENCE:
        assert (root / path).exists() is (not forget), path
        if not forget:
            assert (root / path).read_bytes() == files[path]
    if reset_registry:
        assert json.loads((root / 'model_ports.json').read_text()) == []
    else:
        assert (root / 'model_ports.json').read_bytes() == files['model_ports.json']
    assert (root / 'state/llama_cpp_catalog.json').exists() is (not reset_catalog)
    for bucket, inode in before_dirs.items():
        target = root / 'artifacts' / bucket
        assert target.is_dir() and target.stat().st_ino == inode
        assert not list(target.iterdir())
    assert not (root / 'artifacts/extra.bin').exists()
    assert not (root / 'artifacts/inputs/unknown').exists()
    assert not (root / 'scripts/__pycache__').exists()
    assert not (root / 'scripts/nested/generated.pyo').exists()
    assert not (root / 'scripts/nested/.DS_Store').exists()
    if archived:
        destination, = [p for p in (root / '.fruth_archiv').iterdir() if p.name != 'old']
        if full:
            assert not (destination / 'state/self_attack').exists()
        else:
            assert (destination / 'state/self_attack/nested/.DS_Store').read_bytes() == files[
                'state/self_attack/nested/.DS_Store']
        for path in (*VOLATILE, *INFERENCE):
            assert (destination / path).read_bytes() == files[path], path
        assert (destination / 'artifacts/extra.bin').read_bytes() == b'ordinary generated residue'
        assert (destination / 'state/self_learning/__pycache__/proof.pyc').read_bytes() == files[
            'state/self_learning/__pycache__/proof.pyc']
        if reset_registry:
            assert (destination / 'model_ports.json').read_bytes() == files['model_ports.json']
        if reset_catalog:
            assert (destination / 'state/llama_cpp_catalog.json').read_bytes() == files['state/llama_cpp_catalog.json']
        assert 'outputs' in (destination / 'manifest.txt').read_text()


@pytest.mark.parametrize('flags', [(), ('--full',), ('--archive',), ('--archive', '--full')])
@pytest.mark.parametrize('dry_run', [False, True])
def test_absent_targets_and_missing_buckets_are_supported(tmp_path, flags, dry_run):
    root, env, _ = populated_fixture(tmp_path)
    for relative in ('artifacts', 'logs', 'outputs', 'state', 'model_ports.json',
                     '.pytest_cache', '.coverage', 'htmlcov', '.mypy_cache', '.ruff_cache',
                     '.fruth_archiv'):
        path = root / relative
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
    result = run_isolated_cleanup(root, env, *flags, *(['--dry-run'] if dry_run else []))
    assert result.returncode == 0, result.stderr or result.stdout
    assert '[dry-run] remove: state/inference_compiled_memory' not in result.stdout
    if '--full' in flags:
        assert 'removed when present (missing targets skipped)' in result.stdout
    if dry_run:
        assert not (root / 'artifacts').exists()
        assert not (root / 'state').exists()
        assert not (root / '.fruth_archiv').exists()
    else:
        assert all((root / 'artifacts' / bucket).is_dir() for bucket in BUCKETS)
        assert (root / 'logs').is_dir()
        assert (root / 'state/response_frames/snapshots').is_dir()


def test_archive_retains_root_outputs_before_cleanup(tmp_path):
    root, env, files = populated_fixture(tmp_path)
    result = run_isolated_cleanup(root, env, '--archive')
    assert result.returncode == 0, result.stderr or result.stdout
    destination, = [p for p in (root / '.fruth_archiv').iterdir() if p.name != 'old']
    assert (destination / 'outputs/legacy-result.txt').read_bytes() == files['outputs/legacy-result.txt']


@pytest.mark.parametrize('target', [
    'inference_preferences.json', 'inference_compiled_memory.json',
    'inference_compiled_memory.md', 'self_learning', 'readiness_observations.jsonl',
])
def test_all_protected_copies_verify_before_runtime_movement(tmp_path, target):
    root, env, files = populated_fixture(tmp_path)
    helper = root / 'scripts/maintenance_archive.py'
    helper.write_text(helper.read_text().replace(
        'before = inventory(source)',
        f'if source.name == {target!r}:\n'
        '        raise OSError("injected protected snapshot failure")\n'
        '    before = inventory(source)',
    ))
    result = run_isolated_cleanup(root, env, '--archive', '--full', '--forget-inference')
    assert result.returncode != 0
    assert 'injected protected snapshot failure' in result.stderr
    assert 'Removing repo-local generated/runtime ballast' not in result.stdout
    for path in (*VOLATILE, *INFERENCE, 'model_ports.json', 'state/llama_cpp_catalog.json'):
        assert (root / path).read_bytes() == files[path], path


@pytest.mark.parametrize('flags', [(), ('--full',), ('--archive',), ('--archive', '--full', '--forget-inference')])
def test_dry_run_summary_describes_plans_without_claiming_effects(tmp_path, flags):
    root, env, files = populated_fixture(tmp_path)
    result = run_isolated_cleanup(root, env, *flags, '--dry-run')
    assert result.returncode == 0, result.stderr or result.stdout
    summary = result.stdout.split('Preserved/reset summary', 1)[1]
    assert '(planned; no changes applied)' in summary
    lines = [line for line in summary.splitlines() if line.startswith(('-', '[dry-run] -'))]
    # Scope to the reset summary, before the separate Chrome advice paragraph.
    reset_lines = summary.split('Chrome/macOS artifact preview note:', 1)[0].splitlines()[1:]
    assert reset_lines and all(line.startswith('[dry-run] -') for line in reset_lines if line)
    assert lines
    assert all((root / path).read_bytes() == body for path, body in files.items())


@pytest.mark.parametrize('command', ['clean', 'reset-state', 'archiv', 'archive'])
@pytest.mark.parametrize('dry_run', [False, True])
def test_fruth_cleanup_aliases_route_only_to_fixture_checkout(tmp_path, command, dry_run):
    root, env, _ = populated_fixture(tmp_path)
    shutil.copy2(REPO_ROOT / 'fruth', root / 'fruth')
    # Empty configuration prevents the copied status command from probing ports.
    (root / 'model_ports.json').write_text('[]\n')
    result = subprocess.run([str(root / 'fruth'), command, *(['--dry-run'] if dry_run else [])],
                            cwd=root, env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr or result.stdout
    assert f'repo: {root}' in result.stdout
    assert ('mode: archive' in result.stdout) is (command in ('archiv', 'archive'))


def test_chrome_reset_uses_explicit_flag_and_fixture_os_stubs(tmp_path):
    root, env, _ = populated_fixture(tmp_path)
    calls = tmp_path / 'chrome-args.txt'
    for name, script in {
        'uname': '#!/bin/sh\nprintf "Darwin\\n"\n',
        'tccutil': '#!/bin/sh\nprintf "%s\\n" "$*" > "$CHROME_ARGS_FILE"\n',
    }.items():
        path = tmp_path / 'bin' / name
        path.write_text(script)
        path.chmod(0o755)
    env['CHROME_ARGS_FILE'] = str(calls)
    result = run_isolated_cleanup(root, env)
    assert result.returncode == 0 and not calls.exists()
    result = run_isolated_cleanup(root, env, '--reset-chrome-file-access-prompt')
    assert result.returncode == 0, result.stderr or result.stdout
    assert calls.read_text().strip() == 'reset SystemPolicyDesktopFolder com.google.Chrome'


@pytest.mark.parametrize('missing', [False, True])
def test_real_learning_and_readiness_collectors_gate_fixture_rotation(tmp_path, missing):
    from fruth_services import response_frames
    from test_readiness_archive_pass import frame

    root, env, _ = populated_fixture(tmp_path)
    frames = root / 'state/response_frames'
    shutil.rmtree(frames)
    registry = root / 'state/graph_rebase/readiness_observations.jsonl'
    registry.unlink()
    response_frames.persist_response_frame(frame('maintenance-fixture'), frames_dir=frames)
    sidecar = frames / 'snapshots/learning.json'
    sidecar.parent.mkdir(exist_ok=True)
    body = b'{"retained":"fixture evidence"}'
    sidecar.write_bytes(body)
    learning = root / 'state/self_learning'
    (learning / 'refs.json').write_text(json.dumps({'runtime_snapshot_ref': {
        'path': 'snapshots/learning.json', 'sha256': hashlib.sha256(body).hexdigest(),
    }}))
    if missing:
        sidecar.unlink()
    for name in ('collect_self_learning_retention_roots.py', 'sync_graph_rebase_readiness_registry.py'):
        shutil.copy2(REPO_ROOT / 'scripts' / name, root / 'scripts' / name)
    # These real collectors need the complete staged packages through PYTHONPATH;
    # the minimal ownership-only copies would shadow their other dependencies.
    for package in ('fruth_core', 'fruth_runtime', 'helpers'):
        shutil.rmtree(root / package)
    env['PYTHONPATH'] = str(REPO_ROOT)
    result = run_isolated_cleanup(root, env, '--archive')
    assert result.returncode == 0, result.stderr or result.stdout
    assert registry.is_file() and 'maintenance-fixture' in registry.read_text()
    manifest = json.loads((learning / 'retention_manifest.json').read_text())
    if missing:
        assert manifest['status'] == 'partial' and manifest['missing_sidecar_count'] == 1
        assert (frames / 'responses.jsonl').is_file()
        assert 'preserving state/response_frames' in result.stdout
    else:
        assert manifest['status'] == 'complete'
        assert (learning / 'retained_sidecars/snapshots/learning.json').read_bytes() == body
        assert not (frames / 'responses.jsonl').exists()


@pytest.mark.parametrize('populated', [False, True])
def test_explicit_learning_reset_cli_is_separate_and_recoverable(tmp_path, populated):
    root, env, files = populated_fixture(tmp_path)
    sources = ('state/events.jsonl', 'state/inference_learned_policy.json',
               'state/inference_learned_policy.md', 'state/inference_compiled_memory.json',
               'state/inference_compiled_memory.md', 'state/self_learning')
    log = root / 'logs/flask_webserver.log'
    log.write_text('reset fixture runtime log\n')
    if not populated:
        for relative in (*sources, 'logs/flask_webserver.log'):
            path = root / relative
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
    result = subprocess.run([sys.executable, str(REPO_ROOT / 'scripts/fruthctl.py'),
                             'inference', '--reset-learning-state', '--json'],
                            cwd=root, env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload['ok']
    assert (root / 'state/events.jsonl').read_bytes() == b''
    assert log.read_bytes() == b''
    assert (root / 'state/response_frames/responses.jsonl').read_bytes() == files['state/response_frames/responses.jsonl']
    assert (root / 'state/inference_preferences.json').read_bytes() == files['state/inference_preferences.json']
    for relative in sources[1:]:
        assert not (root / relative).exists()
    archive = root / payload['archive_dir']
    assert (archive / 'manifest.json').is_file()
    if populated:
        for relative in sources[:5]:
            assert (archive / relative).read_bytes() == files[relative]
        assert (archive / 'state/self_learning/__pycache__/proof.pyc').read_bytes() == files[
            'state/self_learning/__pycache__/proof.pyc']
    else:
        assert payload['archived_files'] == {}
