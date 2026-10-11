"""Archive Epoch reuse retains byte/identity checks with constant map work."""
import os
import shutil
from unittest.mock import patch

import pytest

from fruth_services import graph_rebase_readiness_registry as registry
from fruth_services import response_frames as rf
from fruth_services.graph_rebase_rollout import project_graph_rebase_readiness_observation


def frame(response_id, reason='archive-evidence'):
    return {
        'kind': 'fruth.response_frame', 'frame_version': 9,
        'response_id': response_id, 'status': 'completed',
        'current_state': {'id': response_id, 'status': 'completed', 'lifecycle_state': 'completed'},
        'request': {'prompt': f'Archive {response_id}', 'workload_family': 'archive-pass'},
        'runtime': {'developer_diagnostics': {
            'response_time_graph_rebase_candidate': {'candidate': True, 'reason': reason},
        }},
    }


def history(tmp_path, count=3):
    root = tmp_path / 'frames'
    for number in range(count):
        rf.persist_response_frame(frame(f'resp-{number}'), frames_dir=root)
    return root


def sync(root, output, **kwargs):
    return registry.sync_graph_rebase_readiness_epoch(
        frames_dir=root, registry_path=output, write=True,
        require_all_settled=True, **kwargs,
    )


def replace_same(path):
    replacement = path.with_suffix('.replacement')
    replacement.write_bytes(path.read_bytes())
    replacement.replace(path)


@pytest.mark.parametrize('count', [1, 6, 25])
def test_archive_full_map_work_is_constant_and_registry_bytes_match_ordinary(tmp_path, count):
    root = history(tmp_path, count)
    epoch = rf.verify_response_frame_epoch(frames_dir=root)
    source = registry.build_graph_rebase_source_epoch_identity(epoch)
    selected = rf.select_graph_rebase_observation_response_ids(frames_dir=root, index_state=epoch['index_state'])
    expected = []
    for rid in selected['selected_response_ids']:
        observed = rf.load_latest_response_observation_state(rid, frames_dir=root, index_state=epoch['index_state'])
        expected.append(registry.build_graph_rebase_readiness_registry_record(
            project_graph_rebase_readiness_observation(observed['response_payload']),
            source_epoch=source, source_frame_sha256=epoch['source_frame_sha256_by_response'][rid],
        ))
    output = tmp_path / 'registry.jsonl'
    with patch.object(rf, 'verify_response_frame_epoch', wraps=rf.verify_response_frame_epoch) as audits, \
         patch.object(rf, '_index_response_map_digest', wraps=rf._index_response_map_digest) as digests, \
         patch.object(rf, '_response_frame_index_has_verified_response_map', wraps=rf._response_frame_index_has_verified_response_map) as repeated, \
         patch.object(rf, '_read_indexed_response_frame', wraps=rf._read_indexed_response_frame) as rows:
        result = sync(root, output)
    assert result['ok'] and result['registered_observation_count'] == count
    assert audits.call_count == 1
    assert digests.call_count == 1
    assert repeated.call_count == 0
    assert rows.call_count == count
    expected_output = tmp_path / 'ordinary.jsonl'
    registry.append_graph_rebase_readiness_registry_records(expected, registry_path=expected_output)
    assert output.read_bytes() == expected_output.read_bytes()


@pytest.mark.parametrize('change', ['append', 'index_replace', 'ledger_replace', 'selector_replace'])
def test_epoch_movement_restarts_full_audit_and_never_mixes_observations(tmp_path, change):
    root = history(tmp_path)
    original = rf.load_latest_response_observation_state
    fired = False

    def load(*args, **kwargs):
        nonlocal fired
        value = original(*args, **kwargs)
        if not fired:
            fired = True
            if change == 'append':
                rf.persist_response_frame(frame('resp-1', reason='successor-evidence'), frames_dir=root)
            else:
                path = {'index_replace': rf._index_path(frames_dir=root),
                        'ledger_replace': root / 'responses.jsonl',
                        'selector_replace': root / 'current_index.active.json'}[change]
                replace_same(path)
        return value

    output = tmp_path / 'registry.jsonl'
    verified_states = []
    verify = rf.verify_response_frame_epoch

    def audit(**kwargs):
        value = verify(**kwargs)
        verified_states.append(value.get('ledger_file_state'))
        return value

    with patch.object(rf, 'load_latest_response_observation_state', side_effect=load), \
         patch.object(rf, 'verify_response_frame_epoch', side_effect=audit) as audits:
        result = sync(root, output)
    assert fired and audits.call_count == 2
    assert result['ok'] and result['registered_observation_count'] == 3
    if change == 'ledger_replace':
        # A full fresh audit can accept equal bytes, but it must bind the new
        # physical Ledger; the original pass cannot certify the replacement.
        assert verified_states[0]['inode'] != verified_states[1]['inode']
        assert verified_states[1]['inode'] == (root / 'responses.jsonl').stat().st_ino
    if change == 'append':
        records = registry.load_graph_rebase_readiness_records(output)
        target = next(item['observation'] for item in records if item['observation']['response_id'] == 'resp-1')
        assert target['ledger_sequence'] == 2


def test_repeated_movement_rejects_without_registry_write(tmp_path):
    root = history(tmp_path)
    original = rf.load_latest_response_observation_state

    def load(*args, **kwargs):
        value = original(*args, **kwargs)
        replace_same(rf._index_path(frames_dir=root))
        return value

    output = tmp_path / 'registry.jsonl'
    with patch.object(rf, 'load_latest_response_observation_state', side_effect=load):
        result = sync(root, output)
    assert not result.get('ok') and not output.exists()
    assert result['errors'][0]['code'] == 'response_frame_index_moved'


@pytest.mark.parametrize('change', ['missing_cas', 'corrupt_cas', 'same_size_ledger_corruption'])
def test_each_response_keeps_fresh_byte_checks(tmp_path, change):
    root = history(tmp_path)
    index = rf.load_response_frame_index(frames_dir=root)
    ref = index['responses']['resp-1']['effective_snapshot_manifest']['runtime']
    original = rf.load_latest_response_observation_state
    fired = False

    def load(*args, **kwargs):
        nonlocal fired
        value = original(*args, **kwargs)
        if not fired:
            fired = True
            if change == 'missing_cas':
                (root / ref['path']).unlink()
            elif change == 'corrupt_cas':
                (root / ref['path']).write_bytes(b'corrupt')
            else:
                ledger = root / 'responses.jsonl'
                before = ledger.stat()
                data = bytearray(ledger.read_bytes())
                data[0] = ord('!')
                ledger.write_bytes(data)
                os.utime(ledger, ns=(before.st_atime_ns, before.st_mtime_ns))
        return value

    output = tmp_path / 'registry.jsonl'
    with patch.object(rf, 'load_latest_response_observation_state', side_effect=load):
        result = sync(root, output)
    assert fired and not result.get('ok') and not output.exists()
    assert result['scan_error_count'] or result['hydration_error_count']


@pytest.mark.parametrize('source', ['index', 'ledger', 'selector'])
def test_source_movement_after_collection_rejects_before_registry_append(tmp_path, source):
    root = history(tmp_path)
    original = registry.load_graph_rebase_readiness_registry

    def read(path):
        value = original(path)
        target = {'index': rf._index_path(frames_dir=root), 'ledger': root / 'responses.jsonl',
                  'selector': root / 'current_index.active.json'}[source]
        replace_same(target)
        return value

    output = tmp_path / 'registry.jsonl'
    with patch.object(registry, 'load_graph_rebase_readiness_registry', side_effect=read):
        result = sync(root, output)
    assert not result.get('ok') and not output.exists()
    assert result['errors'][0]['code'] == 'readiness_epoch_moved'


def test_relocated_epoch_reuses_only_its_own_map_and_preserves_source_bytes(tmp_path):
    original = history(tmp_path)
    archive = tmp_path / 'archived'
    before = {p.relative_to(original): p.read_bytes() for p in original.rglob('*') if p.is_file()}
    shutil.move(str(original), archive)
    strict = sync(archive, tmp_path / 'strict.jsonl', allow_relocated=False)
    assert not strict.get('ok') and not (tmp_path / 'strict.jsonl').exists()
    result = sync(archive, tmp_path / 'relocated.jsonl', allow_relocated=True)
    assert result['ok'] and result['source']['relocated']
    assert all((archive / rel).read_bytes() == data for rel, data in before.items())
    collected = rf.load_graph_rebase_readiness_observation_pass(
        frames_dir=archive, verify_epoch=True, allow_relocated=True,
    )
    assert collected['ok']
    assert 'responses' not in collected['index_state']
    assert 'index_state' not in collected['verified_epoch']


def test_explicit_ledger_name_keeps_same_epoch_and_per_response_checks(tmp_path):
    root = tmp_path / 'frames'
    rf.persist_response_frame(frame('named-ledger'), frames_dir=root, ledger_name='history.jsonl')
    collected = rf.load_graph_rebase_readiness_observation_pass(
        frames_dir=root, ledger_name='history.jsonl', verify_epoch=True,
    )
    assert collected['ok'] and collected['observations'][0]['state']['ok']
    assert collected['verified_epoch']['ledger_path'] == str(root / 'history.jsonl')
    # Observation support does not relax the Registry's canonical-name schema.
    output = tmp_path / 'registry.jsonl'
    result = sync(root, output, ledger_name='history.jsonl')
    assert not result.get('ok') and not output.exists()
    assert result['errors'][0]['code'] == 'readiness_registry_source_epoch_ledger_invalid'
