"""Storage, migration and crash proofs use only disposable synthetic history."""

import collections
import copy
import hashlib
import json
import multiprocessing
import os
import random
import shutil
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest

from fruth_services import response_frames as rf
from fruth_services import response_index_sqlite as storage
from fruth_services import response_index_maintenance as maintenance
from fruth_services.response_persistence import ResponseFramePersistenceError
from tests.test_response_persistence import frame
from tests.test_readiness_index_pass import frame as readiness_frame


def select_sqlite(root):
    result = maintenance.maintain_response_index(frames_dir=root, action='migrate', writers_stopped=True)
    assert result['ok'], result
    return rf._index_path(frames_dir=root)


def history(root, count=7):
    for i in range(count):
        rf.persist_response_frame(frame(f'resp-{i:04}'), frames_dir=root)
    return select_sqlite(root)


def test_migration_normal_reads_and_successors_preserve_exact_work(tmp_path):
    value = frame('kept')
    value['runtime'] = {'diagnostic_body': 'complete evidence ' * 10_000}
    receipt = {}
    from tests.response_index_fixtures import legacy_history
    ledger = legacy_history(tmp_path, [value])
    receipt['frame_id'] = json.loads(ledger.read_bytes())['frame_id']
    before = ledger.read_bytes()
    old_index = (tmp_path / storage.LEGACY_NAME).read_bytes()
    prior = rf.load_latest_response_state('kept', frames_dir=tmp_path)['response_payload']
    sidecars = {p: p.read_bytes() for p in tmp_path.rglob('snapshots/**/*.json')}
    select_sqlite(tmp_path)
    assert ledger.read_bytes() == before
    assert rf.load_latest_response_state('kept', frames_dir=tmp_path)['response_payload'] == prior
    appended = rf.append_response_frame_with_parent_cas(
        value, expected_parent_frame_id=receipt['frame_id'], expected_parent_frame_sequence=1,
        frames_dir=tmp_path,
    )
    assert appended['response_frame']['frame_sequence'] == 2
    assert appended['response_frame']['frame_relation']['parent_frame_id'] == receipt['frame_id']
    assert ledger.read_bytes().startswith(before)
    assert (tmp_path / storage.LEGACY_NAME).read_bytes() == old_index
    assert all(p.read_bytes() == raw for p, raw in sidecars.items())
    assert rf.verify_response_frame_epoch(frames_dir=tmp_path)['ok']
    assert rf.load_latest_response_wire_state('kept', frames_dir=tmp_path)['ok']


@pytest.mark.parametrize('migration_spelling', ['absolute', 'relative'])
def test_migrated_index_accepts_equivalent_writer_paths_without_reconstruction(
    tmp_path, monkeypatch, migration_spelling,
):
    from tests.response_index_fixtures import legacy_history

    monkeypatch.chdir(tmp_path)
    absolute = tmp_path / 'frames'
    relative = Path('frames')
    migration_root, writer_root = (
        (absolute, relative) if migration_spelling == 'absolute' else (relative, absolute)
    )
    ledger = legacy_history(absolute, [frame('kept')])
    before = ledger.read_bytes()
    parent = json.loads(before)['frame_id']
    legacy_index = (absolute / storage.LEGACY_NAME).read_bytes()
    select_sqlite(migration_root)
    generation = storage.selection(absolute)['generation']

    with patch.object(maintenance, 'rebuild_sqlite_locked', side_effect=AssertionError('reconstruction')), \
         patch.object(rf, '_iter_ledger_frames', side_effect=AssertionError('Ledger fallback')), \
         patch.object(storage, '_complete_map', side_effect=AssertionError('full tree scan')):
        receipt = {}
        rf.persist_response_frame(frame('new'), frames_dir=writer_root, receipt=receipt)
        assert receipt['status'] == 'committed' and receipt['index_status'] == 'published'
        successor = rf.append_response_frame_with_parent_cas(
            frame('kept'), frames_dir=writer_root,
            expected_parent_frame_id=parent, expected_parent_frame_sequence=1,
        )
        assert successor['response_frame']['frame_sequence'] == 2
        assert successor['response_frame']['frame_relation']['parent_frame_id'] == parent
        for root in (migration_root, writer_root):
            recovered = rf.load_latest_response_state('kept', frames_dir=root)
            assert recovered['ok'] and recovered['index_used']
            assert not recovered['ledger_fallback_used']
            assert recovered['response_frame']['frame_sequence'] == 2

    assert storage.selection(absolute)['generation'] == generation
    assert ledger.read_bytes().startswith(before)
    assert len(ledger.read_bytes().splitlines()) == 3
    assert (absolute / storage.LEGACY_NAME).read_bytes() == legacy_index
    for root in (migration_root, writer_root):
        epoch = rf.verify_response_frame_epoch(frames_dir=root)
        assert epoch['ok'], epoch
        assert epoch['response_map_entry_count'] == 2


def test_index_publication_rejects_different_ledger_path_even_with_same_inode(tmp_path):
    from tests.response_index_fixtures import legacy_history

    ledger = legacy_history(tmp_path, [frame('kept')])
    other = tmp_path / 'other-responses.jsonl'
    os.link(ledger, other)
    index = select_sqlite(tmp_path)
    original = index.read_bytes()
    native = storage.update

    def wrong_path(path, **kwargs):
        assert storage.file_state(other) == storage.file_state(ledger)
        return native(path, **{**kwargs, 'ledger_path': other})

    with patch.object(storage, 'update', side_effect=wrong_path):
        with pytest.raises(ResponseFramePersistenceError) as raised:
            rf.persist_response_frame(frame('new'), frames_dir=tmp_path)
    assert raised.value.receipt['status'] == 'committed'
    assert raised.value.receipt['index_status'] == 'failed'
    assert 'Cannot advance uncertain SQLite index coverage' in str(raised.value)
    assert index.read_bytes() == original
    recovered = rf.load_latest_response_state('new', frames_dir=tmp_path)
    assert recovered['ok'] and recovered['ledger_fallback_used']


@pytest.mark.parametrize('lifecycle', ['incomplete', 'blocked', 'failed'])
def test_non_successful_frames_are_durable_and_indexed(tmp_path, lifecycle):
    select_sqlite(tmp_path)
    value = frame('unfinished')
    value.update(status=lifecycle)
    value['current_state'].update(status=lifecycle, lifecycle_state=lifecycle)
    rf.persist_response_frame(value, frames_dir=tmp_path)
    recovered = rf.load_latest_response_state('unfinished', frames_dir=tmp_path)
    assert recovered['ok'] and recovered['index_used']
    assert recovered['response_payload']['lifecycle_state'] == lifecycle


def test_routine_insert_update_hit_and_absence_avoid_full_map_work(tmp_path):
    history(tmp_path, 100)
    counts = collections.Counter()
    def observe_work(**kwargs):
        # The observer accepts both numeric work and named digest identities.
        counts.update({key: value for key, value in kwargs.items()
                       if isinstance(value, int) and not isinstance(value, bool)})
    with patch.object(rf, '_iter_ledger_frames', side_effect=AssertionError('full Ledger scan')), \
         patch.object(rf, '_response_map_digest', side_effect=AssertionError('flat-map digest')), \
         patch.object(storage, '_complete_map', side_effect=AssertionError('full tree scan')), \
         patch.object(storage, 'state_flow_note', observe_work):
        rf.persist_response_frame(frame('resp-new'), frames_dir=tmp_path)
        rf.persist_response_frame(frame('resp-0050'), frames_dir=tmp_path)
        assert rf.load_latest_response_state('resp-0050', frames_dir=tmp_path)['ok']
        assert rf.load_latest_response_wire_state('resp-0050', frames_dir=tmp_path)['ok']
        missing = rf.load_latest_response_state('unknown', frames_dir=tmp_path)
    assert missing['status_code'] == 404 and missing['error']['index_used']
    assert counts['sqlite_index_full_map_passes'] == 0
    assert counts['sqlite_index_node_writes'] < 30
    assert counts['sqlite_index_transactions'] == 2


def test_balanced_tree_rotations_and_updates_bind_all_keys(tmp_path):
    select_sqlite(tmp_path)
    keys = [f'resp-{i:04}' for i in range(80)]
    random.Random(41).shuffle(keys)
    for key in keys:
        rf.persist_response_frame(frame(key), frames_dir=tmp_path)
    for key in keys[::7]:
        rf.persist_response_frame(frame(key), frames_dir=tmp_path)
    epoch = rf.verify_response_frame_epoch(frames_dir=tmp_path)
    assert epoch['ok'], epoch
    assert set(epoch['index_state']['responses']) == set(keys)
    for key in keys:
        result = rf.load_latest_response_state(key, frames_dir=tmp_path)
        assert result['ok'] and result['index_used']
        assert result['response_frame']['frame_sequence'] == (2 if key in keys[::7] else 1)


@pytest.mark.parametrize('damage', ['missing_db', 'corrupt_db', 'delete_entry', 'node_bytes',
                                   'off_path_bytes', 'metadata_bytes', 'metadata_scalar', 'resealed_subset', 'replace_db',
                                   'replace_ledger', 'stale_db', 'bad_selector', 'missing_selector'])
def test_uncertain_storage_cannot_hide_work_or_reset_parent(tmp_path, damage):
    path = history(tmp_path)
    parent = rf.load_latest_response_state('resp-0001', frames_dir=tmp_path)['response_frame']
    saved_db, saved_selector = path.read_bytes(), (tmp_path / storage.SELECTOR_NAME).read_bytes()
    rf.persist_response_frame(frame('resp-0001'), frames_dir=tmp_path)
    if damage == 'missing_db':
        path.unlink()
    elif damage == 'corrupt_db':
        path.write_bytes(b'not a SQLite database')
    elif damage in {'delete_entry', 'node_bytes', 'off_path_bytes', 'metadata_bytes', 'metadata_scalar', 'resealed_subset'}:
        with sqlite3.connect(path) as conn:
            if damage == 'delete_entry':
                conn.execute('DELETE FROM nodes WHERE response_id=?', ('resp-0001',))
            elif damage == 'node_bytes':
                conn.execute('UPDATE nodes SET body=? WHERE response_id=?', (b'{}', 'resp-0001'))
            elif damage == 'off_path_bytes':
                conn.execute('UPDATE nodes SET body=? WHERE response_id=?', (b'{}', 'resp-0006'))
            elif damage == 'metadata_bytes':
                conn.execute('UPDATE metadata SET payload=?', (b'{}',))
            elif damage == 'metadata_scalar':
                conn.execute('UPDATE metadata SET payload=?,sha256=?',
                             (b'[]', hashlib.sha256(b'[]').hexdigest()))
            else:
                # A self-consistent, transactionally committed subset still
                # cannot replace the externally sealed complete-map coverage.
                metadata = storage._read_metadata(conn)
                metadata['root'] = storage.EMPTY
                conn.execute('DELETE FROM nodes')
                storage._write_metadata(conn, metadata)
    elif damage in {'replace_db', 'replace_ledger'}:
        target = path if damage == 'replace_db' else tmp_path / 'responses.jsonl'
        replacement = target.with_suffix('.replacement')
        replacement.write_bytes(target.read_bytes())
        os.utime(replacement, ns=(target.stat().st_atime_ns, target.stat().st_mtime_ns))
        replacement.replace(target)
    elif damage == 'stale_db':
        path.write_bytes(saved_db)
        (tmp_path / storage.SELECTOR_NAME).write_bytes(saved_selector)
    elif damage == 'bad_selector':
        (tmp_path / storage.SELECTOR_NAME).write_bytes(b'{broken')
    else:
        (tmp_path / storage.SELECTOR_NAME).unlink()
    before = (tmp_path / 'responses.jsonl').read_bytes()
    recovered = rf.load_latest_response_state('resp-0001', frames_dir=tmp_path)
    assert recovered['ok'] and recovered['ledger_fallback_used']
    assert recovered['response_frame']['frame_sequence'] == 2
    assert not rf.load_latest_response_wire_state('resp-0001', frames_dir=tmp_path)['ok']
    assert not rf.verify_response_frame_epoch(frames_dir=tmp_path)['ok']
    if damage in {'bad_selector', 'missing_selector'}:
        assert maintenance.maintain_response_index(
            frames_dir=tmp_path, action='rebuild', writers_stopped=True)['ok']
    with pytest.raises(rf.ResponseFrameParentCASMismatch):
        rf.append_response_frame_with_parent_cas(frame('resp-0001'), frames_dir=tmp_path,
                                                expected_parent_frame_id=parent['frame_id'])
    assert (tmp_path / 'responses.jsonl').read_bytes() == before
    rf.append_response_frame_with_parent_cas(frame('resp-0001'), frames_dir=tmp_path,
                                             expected_parent_frame_id='resp-0001:frame-2')
    assert rf.load_latest_response_state('resp-0001', frames_dir=tmp_path)['response_frame']['frame_sequence'] == 3
    assert rf.verify_response_frame_epoch(frames_dir=tmp_path)['ok']


@pytest.mark.parametrize('window', ['before_transaction', 'during_transaction', 'after_transaction'])
def test_ledger_committed_index_unpublished_recovery(tmp_path, window):
    select_sqlite(tmp_path)
    receipt = {}
    ledger = rf.persist_response_frame(frame(), frames_dir=tmp_path, receipt=receipt)
    parent = receipt['frame_id']
    if window == 'before_transaction':
        failing = patch.object(storage, 'update', side_effect=OSError('index unavailable'))
    elif window == 'during_transaction':
        failing = patch.object(storage, '_write_metadata', side_effect=OSError('transaction interrupted'))
    else:
        native = rf._atomic_replace_file_bytes

        def fail_checkpoint(path, data):
            if path.name == storage.SELECTOR_NAME:
                raise OSError('checkpoint publication interrupted')
            return native(path, data)
        failing = patch.object(rf, '_atomic_replace_file_bytes', side_effect=fail_checkpoint)
    with failing, pytest.raises(ResponseFramePersistenceError) as raised:
        rf.append_response_frame_with_parent_cas(frame(), frames_dir=tmp_path,
                                                expected_parent_frame_id=parent)
    receipt = raised.value.receipt
    assert receipt['status'] == 'committed' and receipt['index_status'] == 'failed'
    assert receipt['frame_sequence'] == 2
    before = ledger.read_bytes()
    recovered = rf.load_latest_response_state('resp-storage', frames_dir=tmp_path)
    assert recovered['ok'] and recovered['ledger_fallback_used']
    assert recovered['response_frame']['frame_id'] == receipt['frame_id']
    assert ledger.read_bytes() == before
    with pytest.raises(rf.ResponseFrameParentCASMismatch):
        rf.append_response_frame_with_parent_cas(frame(), frames_dir=tmp_path,
                                                expected_parent_frame_id=parent)
    assert ledger.read_bytes() == before and len(before.splitlines()) == 2
    rf.append_response_frame_with_parent_cas(frame(), frames_dir=tmp_path,
                                            expected_parent_frame_id=receipt['frame_id'])
    assert rf.verify_response_frame_epoch(frames_dir=tmp_path)['ok']


def _crash_writer(root, window):
    root = Path(root)
    if window == 'transaction':
        def die(*args, **kwargs):
            os._exit(73)
        storage._write_metadata = die
    else:
        native = rf._atomic_replace_file_bytes
        def die(path, data):
            if path.name == storage.SELECTOR_NAME:
                os._exit(73)
            return native(path, data)
        rf._atomic_replace_file_bytes = die
    rf.append_response_frame_with_parent_cas(frame(), frames_dir=root,
                                            expected_parent_frame_id='resp-storage:frame-1')


@pytest.mark.parametrize('window', ['transaction', 'checkpoint'])
def test_real_process_interruption_recovers_committed_frame(tmp_path, window):
    select_sqlite(tmp_path)
    rf.persist_response_frame(frame(), frames_dir=tmp_path)
    child = multiprocessing.get_context('fork').Process(target=_crash_writer, args=(str(tmp_path), window))
    child.start()
    child.join(15)
    assert child.exitcode == 73
    before = (tmp_path / 'responses.jsonl').read_bytes()
    recovered = rf.load_latest_response_state('resp-storage', frames_dir=tmp_path)
    assert recovered['ok'] and recovered['response_frame']['frame_sequence'] == 2
    assert (tmp_path / 'responses.jsonl').read_bytes() == before
    result = maintenance.maintain_response_index(frames_dir=tmp_path, action='rebuild', writers_stopped=True)
    assert result['ok'], result
    assert rf.verify_response_frame_epoch(frames_dir=tmp_path)['ok']
    assert len((tmp_path / 'responses.jsonl').read_bytes().splitlines()) == 2


def _cas_writer(root, result_queue):
    try:
        result = rf.append_response_frame_with_parent_cas(
            frame(), frames_dir=Path(root), expected_parent_frame_id='resp-storage:frame-1')
        result_queue.put(result['response_frame']['frame_sequence'])
    except rf.ResponseFrameParentCASMismatch:
        result_queue.put('stale')


def test_concurrent_process_parent_cas_has_exactly_one_successor(tmp_path):
    select_sqlite(tmp_path)
    rf.persist_response_frame(frame(), frames_dir=tmp_path)
    context = multiprocessing.get_context('fork')
    queue = context.Queue()
    children = [context.Process(target=_cas_writer, args=(str(tmp_path), queue)) for _ in range(4)]
    for child in children:
        child.start()
    for child in children:
        child.join(15)
        assert child.exitcode == 0
    results = [queue.get(timeout=2) for _ in children]
    assert results.count(2) == 1 and results.count('stale') == 3
    assert len((tmp_path / 'responses.jsonl').read_bytes().splitlines()) == 2
    assert rf.verify_response_frame_epoch(frames_dir=tmp_path)['ok']


def test_concurrent_readers_and_writers_do_not_mix_frames(tmp_path):
    history(tmp_path, 20)
    def write(i):
        rf.persist_response_frame(frame(f'new-{i}'), frames_dir=tmp_path)
    def read(i):
        result = rf.load_latest_response_state(f'resp-{i % 20:04}', frames_dir=tmp_path)
        assert result['ok'], result
        assert result['response_frame']['response_id'] == f'resp-{i % 20:04}'
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(write if i % 3 == 0 else read, i) for i in range(60)]
        for future in futures:
            future.result()
    assert rf.verify_response_frame_epoch(frames_dir=tmp_path)['ok']


def test_migration_restart_rollback_and_read_only_checks(tmp_path):
    from tests.response_index_fixtures import legacy_history
    legacy_history(tmp_path, [frame()])
    ledger = tmp_path / 'responses.jsonl'
    before = ledger.read_bytes()
    existing = {p: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    assert maintenance.maintain_response_index(frames_dir=tmp_path, action='migrate', check_only=True)['ok']
    assert {p: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()} == existing
    assert not maintenance.maintain_response_index(frames_dir=tmp_path, action='migrate')['ok']
    native = rf._atomic_replace_file_bytes
    def fail_activation(path, data):
        if path.name == storage.SELECTOR_NAME:
            raise OSError('interrupted activation')
        return native(path, data)
    with patch.object(rf, '_atomic_replace_file_bytes', side_effect=fail_activation):
        failed = maintenance.maintain_response_index(frames_dir=tmp_path, action='migrate', writers_stopped=True)
    assert not failed['ok'] and not (tmp_path / storage.SELECTOR_NAME).exists()
    assert rf.load_latest_response_state('resp-storage', frames_dir=tmp_path)['ok']
    select_sqlite(tmp_path)
    selected = (tmp_path / storage.SELECTOR_NAME).read_bytes()
    assert not maintenance.maintain_response_index(frames_dir=tmp_path, action='migrate', writers_stopped=True)['changed']
    assert (tmp_path / storage.SELECTOR_NAME).read_bytes() == selected
    assert ledger.read_bytes() == before
    rf.persist_response_frame(frame(), frames_dir=tmp_path)
    before_rollback = ledger.read_bytes()
    assert maintenance.maintain_response_index(frames_dir=tmp_path, action='rollback', writers_stopped=True)['ok']
    assert ledger.read_bytes() == before_rollback
    assert rf.verify_response_frame_epoch(frames_dir=tmp_path, allow_legacy_index=True)['ok']
    assert rf.load_latest_response_state('resp-storage', frames_dir=tmp_path)['response_frame']['frame_sequence'] == 2
    with pytest.raises(rf.ResponseFramePersistenceError):
        rf.persist_response_frame(frame(), frames_dir=tmp_path)
    select_sqlite(tmp_path)
    rf.persist_response_frame(frame(), frames_dir=tmp_path)
    assert rf.load_latest_response_state('resp-storage', frames_dir=tmp_path)['response_frame']['frame_sequence'] == 3
    assert rf.verify_response_frame_epoch(frames_dir=tmp_path)['ok']


@pytest.mark.parametrize('damage', ['malformed', 'unterminated', 'incomplete_json_index'])
def test_migration_rejects_uncertain_legacy_sources_without_rewriting_history(tmp_path, damage):
    from tests.response_index_fixtures import legacy_history
    legacy_history(tmp_path, [frame()])
    ledger = tmp_path / 'responses.jsonl'
    if damage == 'malformed':
        with ledger.open('ab') as handle:
            handle.write(b'bad\n')
    elif damage == 'unterminated':
        with ledger.open('ab') as handle:
            handle.write(ledger.read_bytes().rstrip(b'\n'))
    else:
        path = tmp_path / storage.LEGACY_NAME
        value = json.loads(path.read_bytes())
        value['responses'] = {}
        path.write_bytes(storage.encode(value))
    before = ledger.read_bytes()
    result = maintenance.maintain_response_index(frames_dir=tmp_path, action='migrate', writers_stopped=True)
    assert not result['ok']
    assert ledger.read_bytes() == before and not (tmp_path / storage.SELECTOR_NAME).exists()


def test_readiness_epoch_registry_and_relocated_archive(tmp_path):
    root = tmp_path / 'frames'
    for rid in ('a', 'b', 'c'):
        rf.persist_response_frame(readiness_frame(rid), frames_dir=root)
    select_sqlite(root)
    epoch = rf.verify_response_frame_epoch(frames_dir=root)
    observed = rf.load_latest_response_observation_state('a', frames_dir=root, index_state=epoch['index_state'])
    assert epoch['ok'] and observed['ok']
    from fruth_services.graph_rebase_readiness_registry import append_graph_rebase_readiness_observation
    from fruth_services.graph_rebase_rollout import project_graph_rebase_readiness_observation
    appended = append_graph_rebase_readiness_observation(
        project_graph_rebase_readiness_observation(observed['response_payload']), frames_dir=root,
        source_frame=epoch['source_frame_sha256_by_response']['a'],
        registry_path=tmp_path / 'registry.jsonl', verified_epoch=epoch,
    )
    assert appended['ok'], appended
    assert rf.load_graph_rebase_readiness_observation_pass(frames_dir=root)['ok']
    archived = tmp_path / 'archive'
    shutil.copytree(root, archived)
    snapshot = {p: p.read_bytes() for p in archived.iterdir() if p.is_file()}
    assert not rf.load_latest_response_wire_state('a', frames_dir=archived)['ok']
    relocated = rf.verify_response_frame_epoch(frames_dir=archived, allow_relocated=True)
    assert relocated['ok'], relocated
    assert relocated['relocated']
    assert rf.load_latest_response_observation_state('a', frames_dir=archived, index_state=relocated['index_state'])['ok']
    assert {p: p.read_bytes() for p in archived.iterdir() if p.is_file()} == snapshot


def test_returned_lookup_proof_is_bound_to_exact_entry_and_sources(tmp_path):
    history(tmp_path)
    index = rf.load_response_frame_index(frames_dir=tmp_path, response_id='resp-0001')
    assert rf._response_frame_index_proves_response(index, tmp_path / 'responses.jsonl', 'resp-0001')
    changed = copy.deepcopy(index)
    changed['responses']['resp-0001']['latest_frame_sequence'] += 1
    assert not rf._response_frame_index_proves_response(changed, tmp_path / 'responses.jsonl', 'resp-0001')
    (tmp_path / storage.SELECTOR_NAME).touch()
    assert not rf._response_frame_index_proves_response(index, tmp_path / 'responses.jsonl', 'resp-0001')


def test_scoped_proof_cannot_prove_another_key_absence_or_enumerate_map(tmp_path):
    history(tmp_path)
    index = rf.load_response_frame_index(frames_dir=tmp_path, response_id='unknown')
    assert rf._response_frame_index_proves_response(index, tmp_path / 'responses.jsonl', 'unknown')
    assert not rf._response_frame_index_proves_response(index, tmp_path / 'responses.jsonl', 'resp-0001')
    assert not rf._response_frame_index_has_verified_response_map(index, tmp_path / 'responses.jsonl')
    assert not rf.load_latest_response_wire_state('resp-0001', frames_dir=tmp_path, index_state=index)['ok']
    assert not rf.load_latest_response_observation_state('resp-0001', frames_dir=tmp_path, index_state=index)['ok']
    selection = rf.select_graph_rebase_observation_response_ids(frames_dir=tmp_path, index_state=index)
    assert selection['selected_response_ids'] == [] and selection['scan_error_count'] == 1


def test_sqlite_maintenance_compaction_preserves_frame_identities_and_backups(tmp_path):
    from tests.test_response_frame_ledger_maintenance import _frame, _large_inference_preview, _write_ledger
    from fruth_services.response_frame_ledger_maintenance import compact_response_frame_ledger
    values = [_frame('history', inference_preview=_large_inference_preview())]
    _write_ledger(tmp_path, values)
    assert maintenance.maintain_response_index(frames_dir=tmp_path, action='rebuild', writers_stopped=True)['ok']
    report = compact_response_frame_ledger(frames_dir=tmp_path, execute=True, writers_stopped=True,
                                         backup_dir=tmp_path / 'backups')
    assert report['ok'], report
    assert report['rewrite']['changed_frame_count'] == 1
    assert (tmp_path / 'backups' / storage.SELECTOR_NAME).exists()
    assert rf.verify_response_frame_epoch(frames_dir=tmp_path)['ok']
    assert rf.load_latest_response_state('history', frames_dir=tmp_path)['response_frame']['frame_id'] == values[0]['frame_id']


def test_bad_tail_blocks_sqlite_append_without_touching_canonical_bytes(tmp_path):
    history(tmp_path)
    ledger = tmp_path / 'responses.jsonl'
    with ledger.open('ab') as handle:
        handle.write(b'{unfinished')
    before = ledger.read_bytes()
    with pytest.raises(ResponseFramePersistenceError) as raised:
        rf.persist_response_frame(frame('new'), frames_dir=tmp_path)
    assert raised.value.receipt['status'] == 'not_committed'
    assert ledger.read_bytes() == before


def test_missing_canonical_ledger_never_resets_existing_index_to_empty(tmp_path):
    history(tmp_path)
    (tmp_path / 'responses.jsonl').unlink()
    selected = (tmp_path / storage.SELECTOR_NAME).read_bytes()
    result = maintenance.maintain_response_index(frames_dir=tmp_path, action='rebuild', writers_stopped=True)
    assert not result['ok']
    with pytest.raises(ResponseFramePersistenceError) as raised:
        rf.persist_response_frame(frame('resp-0001'), frames_dir=tmp_path)
    assert raised.value.receipt['status'] == 'not_committed'
    assert not (tmp_path / 'responses.jsonl').exists()
    assert (tmp_path / storage.SELECTOR_NAME).read_bytes() == selected


def test_initial_empty_generation_is_attested_and_restartable(tmp_path):
    result = maintenance.maintain_response_index(frames_dir=tmp_path, action='migrate', check_only=True)
    assert result['ok'] and not list(tmp_path.iterdir())
    select_sqlite(tmp_path)
    assert (tmp_path / 'responses.jsonl').read_bytes() == b''
    assert maintenance.maintain_response_index(frames_dir=tmp_path, action='check')['ok']
    select_sqlite(tmp_path)
    assert rf.verify_response_frame_epoch(frames_dir=tmp_path)['ok']


def test_missing_selector_cannot_reactivate_even_a_fresh_legacy_json_map(tmp_path):
    history(tmp_path)
    ledger = tmp_path / 'responses.jsonl'
    scan = rf._scan_response_frame_ledger_index_truth(ledger, include_entries=True)
    (tmp_path / storage.LEGACY_NAME).write_bytes(storage.encode(maintenance._rollback_payload(ledger, scan)))
    (tmp_path / storage.SELECTOR_NAME).unlink()
    assert not rf.load_latest_response_wire_state('resp-0001', frames_dir=tmp_path)['ok']
    recovered = rf.load_latest_response_state('resp-0001', frames_dir=tmp_path)
    assert recovered['ok'] and recovered['ledger_fallback_used']
    assert maintenance.maintain_response_index(frames_dir=tmp_path, action='migrate', writers_stopped=True)['ok']
    assert rf.verify_response_frame_epoch(frames_dir=tmp_path)['ok']


def test_failed_sqlite_compaction_backups_survive_later_appends(tmp_path):
    from tests.test_response_frame_ledger_maintenance import _frame, _large_inference_preview, _write_ledger
    from fruth_services import response_frame_ledger_maintenance as compact
    _write_ledger(tmp_path, [_frame('history', inference_preview=_large_inference_preview())])
    assert maintenance.maintain_response_index(frames_dir=tmp_path, action='rebuild', writers_stopped=True)['ok']
    backups = tmp_path / 'backups'
    with patch.object(compact, '_write_compacted_ledger', side_effect=OSError('interrupted compaction')):
        result = compact.compact_response_frame_ledger(frames_dir=tmp_path, execute=True,
                                                       writers_stopped=True, backup_dir=backups)
    assert not result['ok'] and result['backup_created']
    before = {p.name: p.read_bytes() for p in backups.iterdir() if p.is_file()}
    rf.persist_response_frame(frame('history'), frames_dir=tmp_path)
    assert {p.name: p.read_bytes() for p in backups.iterdir() if p.is_file()} == before
    assert rf.verify_response_frame_epoch(frames_dir=tmp_path)['ok']


def test_sqlite_finalizer_registration_keeps_closed_owner_proof(tmp_path):
    from fruth_services import graph_rebase_readiness_registry as registry
    from fruth_services.graph_rebase_rollout import project_graph_rebase_readiness_observation
    rf.persist_response_frame(readiness_frame('a'), frames_dir=tmp_path)
    select_sqlite(tmp_path)
    observed = rf.load_latest_response_observation_state('a', frames_dir=tmp_path)
    result = registry._register_finalizer_readiness_observation(
        project_graph_rebase_readiness_observation(observed['response_payload']),
        frames_dir=tmp_path, registry_path=tmp_path / 'registry.jsonl',
    )
    assert result['status'] == 'appended', result


def test_inactive_staged_tree_does_not_grant_current_lookup_authority(tmp_path):
    rf.persist_response_frame(frame(), frames_dir=tmp_path)
    scan = rf._scan_response_frame_ledger_index_truth(tmp_path / 'responses.jsonl', include_entries=True)
    generation = 'a' * 32
    selected = storage.selector_payload(generation, 'sqlite')
    path = tmp_path / selected['filename']
    selected['metadata_sha256'] = storage.build(
        path, generation=generation, entries=scan['entries'], ledger_path=tmp_path / 'responses.jsonl',
        ledger_state=scan['ledger_state'], line_count=scan['ledger_line_count'],
        chain_digest=scan['ledger_chain_digest'],
    )
    selected['index_state'] = storage.file_state(path)
    candidate = storage.read(path, selected=selected, ledger_path=tmp_path / 'responses.jsonl')
    assert not rf._response_frame_index_has_verified_response_map(candidate, tmp_path / 'responses.jsonl')
    with pytest.raises(storage.IndexInvalid):
        storage.read(path, selected=selected, ledger_path=tmp_path / 'responses.jsonl', response_id='resp-storage')


def test_migration_command_handles_empty_check_conversion_and_rollback(tmp_path, capsys):
    from scripts.migrate_response_frame_index import main
    assert main(['migrate', '--frames-dir', str(tmp_path), '--check-only']) == 0
    assert not json.loads(capsys.readouterr().out)['changed']
    assert main(['migrate', '--frames-dir', str(tmp_path), '--writers-stopped']) == 0
    capsys.readouterr()
    assert main(['check', '--frames-dir', str(tmp_path)]) == 0
    capsys.readouterr()
    assert main(['rollback', '--frames-dir', str(tmp_path), '--writers-stopped']) == 0
    capsys.readouterr()
    assert main(['check', '--frames-dir', str(tmp_path)]) == 0
    capsys.readouterr()
    assert not (tmp_path / 'responses.jsonl').read_bytes()


def test_rollback_rejects_lossy_legacy_key_normalization_without_changing_selection(tmp_path):
    select_sqlite(tmp_path)
    rf.persist_response_frame(frame('response_frame'), frames_dir=tmp_path)
    before = (tmp_path / storage.SELECTOR_NAME).read_bytes()
    preview = maintenance.maintain_response_index(frames_dir=tmp_path, action='rollback', check_only=True)
    assert not preview['ok'] and not preview['changed']
    result = maintenance.maintain_response_index(frames_dir=tmp_path, action='rollback', writers_stopped=True)
    assert not result['ok']
    assert (tmp_path / storage.SELECTOR_NAME).read_bytes() == before
    assert rf.load_latest_response_state('response_frame', frames_dir=tmp_path)['ok']
    assert rf.verify_response_frame_epoch(frames_dir=tmp_path)['ok']


def test_reconstruction_keeps_manifest_parents_scoped_to_response_identity(tmp_path):
    a = {**frame('a'), 'frame_id': 'shared-frame-id', 'runtime': {'evidence': 'A' * 50000}}
    b = {**frame('b'), 'frame_id': 'shared-frame-id', 'runtime': {'evidence': 'B' * 50000}}
    rf.persist_response_frame(a, frames_dir=tmp_path)
    rf.persist_response_frame(b, frames_dir=tmp_path)
    rf.persist_response_frame(a, frames_dir=tmp_path)
    expected = rf.load_latest_response_state('a', frames_dir=tmp_path)['response_payload']
    select_sqlite(tmp_path)
    recovered = rf.load_latest_response_state('a', frames_dir=tmp_path)
    assert recovered['ok'] and recovered['response_payload'] == expected
    assert rf.verify_response_frame_epoch(frames_dir=tmp_path)['ok']


def test_interrupted_rollback_reports_unselected_json_and_is_restartable(tmp_path):
    history(tmp_path)
    rf.persist_response_frame(frame('resp-0001'), frames_dir=tmp_path)
    ledger = tmp_path / 'responses.jsonl'
    before = ledger.read_bytes()
    selector = tmp_path / storage.SELECTOR_NAME
    selected = selector.read_bytes()
    native = rf._atomic_replace_file_bytes

    def fail_activation(path, data):
        if path == selector:
            raise OSError('rollback activation interrupted')
        return native(path, data)

    with patch.object(rf, '_atomic_replace_file_bytes', side_effect=fail_activation):
        result = maintenance.maintain_response_index(
            frames_dir=tmp_path, action='rollback', writers_stopped=True)
    assert not result['ok'] and result['changed'] and result['legacy_index_changed']
    assert not result['active_generation_changed']
    assert selector.read_bytes() == selected and ledger.read_bytes() == before
    assert rf.load_latest_response_state('resp-0001', frames_dir=tmp_path)['response_frame']['frame_sequence'] == 2
    assert maintenance.maintain_response_index(
        frames_dir=tmp_path, action='rollback', writers_stopped=True)['ok']
    assert rf.verify_response_frame_epoch(frames_dir=tmp_path, allow_legacy_index=True)['ok']
    assert ledger.read_bytes() == before


@pytest.mark.parametrize('movement', ['once', 'continuous'])
def test_readiness_pass_rechecks_active_generation_before_reuse(tmp_path, movement):
    rf.persist_response_frame(readiness_frame('resp-selector'), frames_dir=tmp_path)
    select_sqlite(tmp_path)
    native = rf.select_graph_rebase_observation_response_ids
    moves = []

    def select(**kwargs):
        result = native(**kwargs)
        if not moves or movement == 'continuous':
            path = tmp_path / storage.SELECTOR_NAME
            # Equal selector bytes replaced during a pass still require a
            # fresh read/verification before any cached map receipt is reused.
            rf._atomic_replace_file_bytes(path, path.read_bytes())
            moves.append(True)
        return result

    with patch.object(rf, 'select_graph_rebase_observation_response_ids', side_effect=select):
        result = rf.load_graph_rebase_readiness_observation_pass(frames_dir=tmp_path)
    if movement == 'once':
        assert result['ok'] and len(moves) == 1
    else:
        assert not result['ok'] and result['error']['code'] == 'response_frame_index_moved'
        assert len(moves) == 2


def test_missing_selector_and_ledger_cannot_claim_empty_readiness_epoch(tmp_path):
    history(tmp_path)
    (tmp_path / 'responses.jsonl').unlink()
    (tmp_path / storage.SELECTOR_NAME).unlink()
    result = rf.load_graph_rebase_readiness_observation_pass(frames_dir=tmp_path)
    assert not result['empty_current_epoch']
    assert result['selection']['scan_errors'][0]['code'] == 'response_frame_index_unverified'


@pytest.mark.parametrize('name', ['current_index.active.json', 'current_index.' + 'a' * 32 + '.sqlite3',
                                 'current_index.' + 'a' * 32 + '.sqlite3-journal', '.response_frame_append.lock'])
def test_learning_output_guards_protect_selected_generations_and_lock(tmp_path, monkeypatch, name):
    from fruth_services import self_learning
    from scripts import build_self_learning_eval_cases as cli

    monkeypatch.chdir(tmp_path)
    repository = tmp_path / 'repository'
    monkeypatch.setattr(self_learning, '_REPOSITORY_ROOT', repository)
    monkeypatch.setattr(cli, 'REPO_ROOT', repository)
    explicit_root = tmp_path / 'fixture' / 'frames'
    roots = [tmp_path / 'state' / 'response_frames', repository / 'state' / 'response_frames', explicit_root]
    for root in roots:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'index-sentinel')
        if root != explicit_root:
            with pytest.raises(ValueError, match='protected state'):
                self_learning._validate_default_self_learning_output_targets([target])
        with pytest.raises(ValueError, match='response index state'):
            cli._validate_merge_output_paths(
                output_path=tmp_path / 'eval_cases.jsonl', report_path=target,
                accepted_policy_path=tmp_path / 'accepted.json', self_learning_dir=tmp_path / 'learning',
                frame_paths=[explicit_root / 'responses.jsonl'], monitor_report_path=None,
                graph_rebase_corpus_dir=tmp_path / 'corpus',
            )
        assert target.read_bytes() == b'index-sentinel'
    assert not (tmp_path / 'eval_cases.jsonl').exists()
