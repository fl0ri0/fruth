"""Readiness pass: reuse global representation, never response or source authority."""
import collections
import copy
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest

from ollmo_services import response_frames as rf
from ollmo_services import graph_rebase_readiness_registry as registry
from ollmo_services.graph_rebase_rollout import project_graph_rebase_readiness_observation


def frame(rid, *, relevant=True, reason='additive_repair_insufficient'):
    value = {
        'kind': 'ollmo.response_frame', 'frame_version': 9,
        'response_id': rid, 'status': 'completed',
        'current_state': {'id': rid, 'status': 'completed', 'lifecycle_state': 'completed'},
        'request': {'prompt': 'A bounded readiness case', 'workload_family': 'readiness-pass'},
    }
    if relevant:
        value['runtime'] = {'developer_diagnostics': {
            'response_time_graph_rebase_candidate': {'candidate': True, 'reason': reason},
        }}
    return value


@pytest.fixture
def history(tmp_path):
    root = tmp_path / 'frames'
    for rid in ('a', 'b', 'c'):
        rf.persist_response_frame(frame(rid), frames_dir=root)
    rf.persist_response_frame(frame('unselected', relevant=False), frames_dir=root)
    assert rf.verify_response_frame_epoch(frames_dir=root)['ok']
    return root


def ordinary(root):
    index = rf.load_response_frame_index(frames_dir=root)
    selection = rf.select_graph_rebase_observation_response_ids(frames_dir=root, index_state=index)
    states = [{'response_id': rid, 'state': rf.load_latest_response_observation_state(
        rid, frames_dir=root, index_state=index,
    )} for rid in selection['selected_response_ids']]
    return index, selection, states


def run(root):
    return rf.load_graph_rebase_readiness_observation_pass(frames_dir=root)


def meter():
    counts = collections.Counter()
    return counts, patch.object(rf, 'state_flow_note', lambda **kw: counts.update(
        {k: v for k, v in kw.items() if type(v) is int}
    ))


def test_stable_one_map_proof_and_independent_response_checks(history):
    index, selected, expected = ordinary(history)
    counts, measured = meter()
    with measured, patch.object(rf, '_response_frame_index_has_verified_response_map',
                               wraps=rf._response_frame_index_has_verified_response_map) as full, \
         patch.object(rf, '_read_indexed_response_frame', wraps=rf._read_indexed_response_frame) as rows:
        result = run(history)
    assert result['ok'] and not result['empty_current_epoch']
    assert result['selection'] == selected
    assert result['observations'] == expected
    assert result['response_ids'] == list(index['responses'])
    assert full.call_count == 1
    assert rows.call_count == len(expected) == 3
    assert counts['readiness_pass_full_verifications'] == 1
    assert counts['readiness_pass_freshness_guards'] >= len(expected)


def after_first_response(root, mutate):
    original = rf.load_latest_response_observation_state
    fired = False
    def load(*args, **kwargs):
        nonlocal fired
        result = original(*args, **kwargs)
        if not fired:
            fired = True
            mutate()
        return result
    counts, measured = meter()
    with measured, patch.object(rf, 'load_latest_response_observation_state', side_effect=load):
        result = run(root)
    assert fired
    return result, counts


@pytest.mark.parametrize('target', ['new-response', 'a', 'b'])
def test_append_restarts_selection_and_discards_old_observations(history, target):
    result, counts = after_first_response(history, lambda: rf.persist_response_frame(
        frame(target, reason='new accepted evidence'), frames_dir=history,
    ))
    assert result['ok']
    assert counts['readiness_pass_full_verifications'] == 2
    assert counts['readiness_pass_invalidations'] == 1
    index, selected, expected = ordinary(history)
    assert result['selection'] == selected and result['observations'] == expected
    assert result['response_ids'] == list(index['responses'])
    if target != 'new-response':
        state = next(x['state'] for x in result['observations'] if x['response_id'] == target)
        assert state['response_frame']['frame_sequence'] == 2


def replace_same(path):
    other = path.with_suffix('.replacement')
    other.write_bytes(path.read_bytes())
    other.replace(path)


@pytest.mark.parametrize('filename', ['current_index.json', 'responses.jsonl'])
@pytest.mark.parametrize('change', ['replace_same', 'mtime_only', 'ctime_only'])
def test_physical_changes_invalidate_even_when_bytes_equal(history, filename, change):
    path = history / filename
    before = path.read_bytes()
    def mutate():
        stat = path.stat()
        if change == 'replace_same':
            replace_same(path)
        elif change == 'mtime_only':
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
        else:
            # chmod changes ctime without changing file bytes, inode or mtime.
            os.chmod(path, stat.st_mode ^ 0o100)
    result, counts = after_first_response(history, mutate)
    assert path.read_bytes() == before
    assert result['ok']
    assert counts['readiness_pass_full_verifications'] == 2
    assert result['observations'] == ordinary(history)[2]


@pytest.mark.parametrize('change', ['index_size', 'index_corrupt', 'index_missing',
    'map_digest', 'target_coordinate', 'ledger_append', 'ledger_corrupt_same_size'])
def test_changed_or_broken_global_state_uses_fresh_normal_checks(history, change):
    index = history / 'current_index.json'
    ledger = history / 'responses.jsonl'
    def mutate():
        if change == 'index_size':
            index.write_bytes(index.read_bytes() + b' ')
        elif change == 'index_corrupt':
            index.write_bytes(b'{')
        elif change == 'index_missing':
            index.unlink()
        elif change in ('map_digest', 'target_coordinate'):
            value = json.loads(index.read_bytes())
            if change == 'map_digest':
                value['response_map_digest'] = '0' * 64
            else:
                value['responses']['b']['latest_frame_sequence'] += 1
                value['response_map_digest'] = rf._response_map_digest(value['responses'])
            index.write_text(json.dumps(value))
        elif change == 'ledger_append':
            with ledger.open('ab') as stream:
                stream.write(b'{}\n')
        else:
            old = ledger.stat()
            raw = bytearray(ledger.read_bytes())
            raw[0] = ord('!')
            ledger.write_bytes(raw)
            # A same-size rewrite with restored mtime still changes ctime.
            os.utime(ledger, ns=(old.st_atime_ns, old.st_mtime_ns))
    result, counts = after_first_response(history, mutate)
    assert counts['readiness_pass_full_verifications'] == 2
    assert counts['readiness_pass_invalidations'] == 1
    _, selected, expected = ordinary(history)
    assert result['ok']
    assert result['selection'] == selected and result['observations'] == expected
    if change != 'index_size':
        assert selected['scan_error_count'] or any(not x['state']['ok'] for x in expected)


def test_corrupt_target_cas_is_checked_per_response_without_global_mutation(history):
    index = rf.load_response_frame_index(frames_dir=history)
    ref = index['responses']['b']['effective_snapshot_manifest']['runtime']
    path = history / ref['path']
    result, counts = after_first_response(history, lambda: path.write_bytes(b'corrupt'))
    assert counts['readiness_pass_full_verifications'] == 1
    assert result['observations'][0]['state']['ok']
    # Corruption happened after selection and the first response. The shared
    # runtime CAS must be checked afresh by each remaining response, exactly as
    # in the ordinary loader; a new selection would already exclude these rows.
    for item in result['observations'][1:]:
        assert not item['state']['ok']
        assert item['state'] == rf.load_latest_response_observation_state(
            item['response_id'], frames_dir=history, index_state=index,
        )


def test_mutation_during_initial_proof_is_not_bound_to_old_bytes(history):
    original = rf._response_frame_index_has_verified_response_map
    fired = False
    def verify(*args, **kwargs):
        nonlocal fired
        result = original(*args, **kwargs)
        if not fired:
            fired = True
            rf.persist_response_frame(frame('d'), frames_dir=history)
        return result
    with patch.object(rf, '_response_frame_index_has_verified_response_map', side_effect=verify):
        result = run(history)
    assert result['ok'] and result['selection'] == ordinary(history)[1]
    assert 'd' in result['response_ids']


def test_repeated_movement_is_bounded_and_never_returns_partial_success(history):
    original = rf.load_latest_response_observation_state
    def load(*args, **kwargs):
        value = original(*args, **kwargs)
        replace_same(history / 'current_index.json')
        return value
    with patch.object(rf, 'load_latest_response_observation_state', side_effect=load):
        result = run(history)
    assert not result['ok']
    assert result['error']['code'] == 'response_frame_index_moved'
    assert not result.get('observations')


def test_output_mutation_and_next_pass_do_not_reuse_old_authority(history):
    result = run(history)
    result['index_state']['response_map_digest'] = '0' * 64
    result['response_ids'].clear()
    result['observations'][0]['state']['response_payload']['runtime'].clear()
    counts, measured = meter()
    with measured:
        again = run(history)
    assert counts['readiness_pass_full_verifications'] == 1
    assert again['observations'] == ordinary(history)[2]


def test_concurrent_passes_have_separate_proofs_and_equal_results(history):
    barrier = threading.Barrier(2)
    def read():
        barrier.wait()
        return run(history)
    counts, measured = meter()
    with measured, ThreadPoolExecutor(max_workers=2) as pool:
        a, b = list(pool.map(lambda _: read(), range(2)))
    assert a == b
    assert counts['readiness_pass_full_verifications'] == 2


def test_private_scope_is_closed_on_success_and_failure(history):
    scopes = []
    original = rf._ReadinessIndexPass.close
    def close(scope):
        scopes.append(scope)
        return original(scope)
    with patch.object(rf._ReadinessIndexPass, 'close', close):
        run(history)
    assert scopes
    for scope in scopes:
        with pytest.raises(RuntimeError, match='closed|scope'):
            scope.selection()


def test_empty_state_and_new_pass_after_recovery(tmp_path):
    result = run(tmp_path)
    assert result['ok'] and result['empty_current_epoch']
    rf.persist_response_frame(frame('new'), frames_dir=tmp_path)
    again = run(tmp_path)
    assert again['ok'] and not again['empty_current_epoch']
    assert again['selection']['selected_response_ids'] == ['new']


def test_deterministic_registry_records_equal(history, tmp_path):
    epoch = rf.verify_response_frame_epoch(frames_dir=history)
    old = ordinary(history)[2]
    new = run(history)['observations']
    for path, states in [(tmp_path / 'old.jsonl', old), (tmp_path / 'new.jsonl', new)]:
        for item in states:
            rid = item['response_id']
            result = registry.append_graph_rebase_readiness_observation(
                project_graph_rebase_readiness_observation(item['state']['response_payload']),
                source_frame=epoch['source_frame_sha256_by_response'][rid],
                verified_epoch=epoch, frames_dir=history, registry_path=path,
            )
            assert result['ok']
    assert (tmp_path / 'old.jsonl').read_bytes() == (tmp_path / 'new.jsonl').read_bytes()


def test_guard_uses_only_physical_state_without_index_io(history):
    scope = rf._ReadinessIndexPass(history)
    try:
        scope.prepare()
        with patch.object(Path, 'open', side_effect=AssertionError('guard read')), \
             patch.object(rf, '_response_map_digest', side_effect=AssertionError('guard hash')), \
             patch.object(json, 'loads', side_effect=AssertionError('guard parse')):
            for _ in range(10):
                scope._guard()
    finally:
        scope.close()


def test_selection_movement_discards_selection_and_restarts(history):
    original = rf.select_graph_rebase_observation_response_ids
    fired = False
    def select(**kwargs):
        nonlocal fired
        result = original(**kwargs)
        if not fired:
            fired = True
            rf.persist_response_frame(frame('new-selection'), frames_dir=history)
        return result
    counts, measured = meter()
    with measured, patch.object(rf, 'select_graph_rebase_observation_response_ids', side_effect=select):
        result = run(history)
    assert counts['readiness_pass_full_verifications'] == 2
    assert result['selection'] == ordinary(history)[1]
    assert result['observations'] == ordinary(history)[2]


def test_scope_rejects_other_thread_and_foreign_mutable_map(history):
    scope = rf._ReadinessIndexPass(history)
    try:
        scope.prepare()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with pytest.raises(RuntimeError, match='process/thread'):
                pool.submit(scope.selection).result()
        foreign = rf.load_response_frame_index(frames_dir=history)
        foreign['response_map_digest'] = '0' * 64
        selected = rf.select_graph_rebase_observation_response_ids(
            frames_dir=history, index_state=foreign, _readiness_index_pass=scope,
        )
        assert selected['scan_error_count'] == 1
    finally:
        scope.close()


def test_forked_process_cannot_reuse_parent_scope(history, tmp_path):
    scope = rf._ReadinessIndexPass(history)
    scope.prepare()
    output = tmp_path / 'child.json'
    pid = os.fork()
    if pid == 0:
        try:
            rejected = False
            try:
                scope.selection()
            except RuntimeError:
                rejected = True
            counts, measured = meter()
            with measured:
                result = run(history)
            output.write_text(json.dumps({
                'rejected': rejected, 'ok': result['ok'],
                'proofs': counts['readiness_pass_full_verifications'],
                'observations': result['observations'],
            }))
            os._exit(0)
        except BaseException:
            os._exit(1)
    try:
        _, status = os.waitpid(pid, 0)
        assert os.waitstatus_to_exitcode(status) == 0
        child = json.loads(output.read_text())
        assert child['rejected'] and child['ok'] and child['proofs'] == 1
        assert child['observations'] == ordinary(history)[2]
    finally:
        scope.close()


def test_unreadable_root_is_not_a_successful_empty_epoch(tmp_path):
    with patch.object(Path, 'stat', side_effect=PermissionError('unreadable root')):
        with pytest.raises(PermissionError):
            run(tmp_path)


def test_private_scope_closes_after_repeated_movement(history):
    scopes = []
    original = rf._ReadinessIndexPass.close
    def close(scope):
        scopes.append(scope)
        original(scope)
    with patch.object(rf._ReadinessIndexPass, 'close', close), \
         patch.object(rf._ReadinessIndexPass, 'selection', side_effect=rf._ReadinessIndexPassChanged('ledger')):
        assert not run(history)['ok']
    assert len(scopes) == 2
    for scope in scopes:
        with pytest.raises(RuntimeError, match='closed'):
            scope._guard()


def test_missing_index_does_not_repair_itself_and_new_pass_sees_restored_evidence(history):
    path = history / 'current_index.json'
    saved = path.read_bytes()
    path.unlink()
    missing = run(history)
    assert missing['selection']['scan_error_count'] == 1
    assert not path.exists()
    # Explicit fixture recovery; observation itself has no recovery authority.
    path.write_bytes(saved)
    counts, measured = meter()
    with measured:
        recovered = run(history)
    assert counts['readiness_pass_full_verifications'] == 1
    assert recovered['observations'] == ordinary(history)[2]


@pytest.mark.parametrize('file', ['current_index.json', 'responses.jsonl'])
def test_device_identity_change_invalidates_scope(history, file):
    scope = rf._ReadinessIndexPass(history)
    original = rf._response_frame_file_state
    try:
        scope.prepare()
        def state(path):
            value = original(path)
            if path.name == file:
                value = {**value, 'device': value['device'] + 1}
            return value
        with patch.object(rf, '_response_frame_file_state', side_effect=state):
            with pytest.raises(rf._ReadinessIndexPassChanged):
                scope._guard()
    finally:
        scope.close()
