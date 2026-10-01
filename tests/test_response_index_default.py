"""SQLite is the sole runtime index; legacy history needs explicit migration."""
from unittest.mock import patch
import errno
import os
import stat

import pytest

from fruth_services import response_frames as frames, response_index_sqlite as storage
from fruth_services.response_index_maintenance import maintain_response_index
from tests.response_index_fixtures import legacy_history
from tests.test_response_persistence import frame


def test_passive_new_root_reads_never_create_storage(tmp_path):
    root=tmp_path/'absent'
    assert not frames.load_response_frame_index(frames_dir=root)['ok']
    assert not frames.verify_response_frame_epoch(frames_dir=root)['ok']
    assert frames.load_latest_response_state('missing',frames_dir=root)['status_code']==404
    assert not root.exists()


def test_genesis_directory_fsync_failure_does_not_claim_a_frame_commit(tmp_path):
    native_fsync = os.fsync
    def fsync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError(errno.EIO, 'synthetic genesis directory fsync failure')
        return native_fsync(fd)
    with patch.object(frames.os, 'fsync', side_effect=fsync), \
         patch.object(frames, '_write_response_frame_index') as publish:
        with pytest.raises(frames.ResponseFramePersistenceError) as raised:
            frames.persist_response_frame(frame('first'), frames_dir=tmp_path)
    assert raised.value.receipt['status'] == 'not_committed'
    assert raised.value.receipt['stage'] == 'prepare'
    assert raised.value.receipt['index_status'] == 'not_attempted'
    assert (tmp_path / 'responses.jsonl').read_bytes() == b''
    assert not (tmp_path / storage.SELECTOR_NAME).exists()
    publish.assert_not_called()


def test_first_write_initializes_only_sqlite_then_avoids_map_work(tmp_path):
    frames.persist_response_frame(frame('first'),frames_dir=tmp_path)
    assert storage.selection(tmp_path)['backend']=='sqlite'
    assert not (tmp_path/storage.LEGACY_NAME).exists()
    assert frames.verify_response_frame_epoch(frames_dir=tmp_path)['ok']
    with patch.object(storage,'_complete_map',side_effect=AssertionError('unexpected whole-map work')), \
         patch.object(frames,'_response_map_digest',side_effect=AssertionError('unexpected JSON map digest')):
        frames.persist_response_frame(frame('second'),frames_dir=tmp_path)
        assert frames.load_latest_response_state('second',frames_dir=tmp_path)['ok']
    assert not (tmp_path/storage.LEGACY_NAME).exists()


@pytest.mark.parametrize('index_present',[True,False])
def test_unmigrated_history_is_readable_but_writes_require_migration(tmp_path,index_present):
    ledger=legacy_history(tmp_path,[frame('kept'),frame('kept')])
    if not index_present: (tmp_path/storage.LEGACY_NAME).rename(tmp_path/'inactive-backup.json')
    before={p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    index=frames.load_response_frame_index(frames_dir=tmp_path)
    assert index['migration_required'] and not index['ok']
    assert 'migrate_response_frame_index.py' in index['error']['message']
    recovered=frames.load_latest_response_state('kept',frames_dir=tmp_path)
    assert recovered['ok'] and recovered['ledger_fallback_used']
    with pytest.raises(frames.ResponseFramePersistenceError) as raised:
        frames.persist_response_frame(frame('kept'),frames_dir=tmp_path)
    receipt=raised.value.receipt
    assert receipt['status']=='not_committed'
    assert receipt['error']['code']=='response_frame_index_migration_required'
    assert {p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}==before
    migrated=maintain_response_index(frames_dir=tmp_path,action='migrate',writers_stopped=True)
    assert migrated['ok'],migrated
    assert ledger.read_bytes()==before[ledger]
    appended=frames.append_response_frame_with_parent_cas(frame('kept'),frames_dir=tmp_path,
                 expected_parent_frame_id=recovered['response_frame']['frame_id'],expected_parent_frame_sequence=2)
    assert appended['response_frame']['frame_sequence']==3


def test_rollback_is_current_history_export_and_cannot_reenable_json_runtime(tmp_path):
    frames.persist_response_frame(frame('kept'),frames_dir=tmp_path)
    frames.persist_response_frame(frame('kept'),frames_dir=tmp_path)
    ledger=tmp_path/'responses.jsonl'; before=ledger.read_bytes()
    exported=maintain_response_index(frames_dir=tmp_path,action='rollback',writers_stopped=True)
    assert exported['ok'],exported
    assert frames.verify_response_frame_epoch(frames_dir=tmp_path,allow_legacy_index=True)['ok']
    assert not frames.verify_response_frame_epoch(frames_dir=tmp_path)['ok']
    assert frames.load_response_frame_index(frames_dir=tmp_path)['migration_required']
    assert frames.load_latest_response_state('kept',frames_dir=tmp_path)['response_frame']['frame_sequence']==2
    with pytest.raises(frames.ResponseFramePersistenceError):
        frames.persist_response_frame(frame('kept'),frames_dir=tmp_path)
    assert ledger.read_bytes()==before
    assert maintain_response_index(frames_dir=tmp_path,action='migrate',writers_stopped=True)['ok']
    frames.persist_response_frame(frame('kept'),frames_dir=tmp_path)
    assert frames.load_latest_response_state('kept',frames_dir=tmp_path)['response_frame']['frame_sequence']==3


def test_truncated_empty_ledger_cannot_reset_retained_history(tmp_path):
    frames.persist_response_frame(frame('kept'),frames_dir=tmp_path)
    ledger=tmp_path/'responses.jsonl'; ledger.write_bytes(b'')
    selected=(tmp_path/storage.SELECTOR_NAME).read_bytes()
    with pytest.raises(frames.ResponseFramePersistenceError):
        frames.persist_response_frame(frame('kept'),frames_dir=tmp_path)
    assert ledger.read_bytes()==b'' and (tmp_path/storage.SELECTOR_NAME).read_bytes()==selected
    result=maintain_response_index(frames_dir=tmp_path,action='rebuild',writers_stopped=True)
    assert not result['ok'] and (tmp_path/storage.SELECTOR_NAME).read_bytes()==selected


def test_missing_ledger_with_retained_snapshot_bytes_cannot_initialize_genesis(tmp_path):
    evidence = tmp_path / 'snapshots/kept.json'
    evidence.parent.mkdir(); evidence.write_bytes(b'kept historical evidence')
    with pytest.raises(frames.ResponseFramePersistenceError) as raised:
        frames.persist_response_frame(frame('first'), frames_dir=tmp_path)
    assert raised.value.receipt['status'] == 'not_committed'
    assert raised.value.receipt['error']['code'] == 'response_frame_index_migration_required'
    result = maintain_response_index(frames_dir=tmp_path, action='rebuild', writers_stopped=True)
    assert not result['ok']
    assert evidence.read_bytes() == b'kept historical evidence'
    assert not (tmp_path / 'responses.jsonl').exists()
    assert not (tmp_path / storage.SELECTOR_NAME).exists()


def test_dangling_legacy_index_cannot_prove_missing_ledger_is_new_genesis(tmp_path):
    legacy = tmp_path / storage.LEGACY_NAME
    unavailable = tmp_path / 'unavailable-backup.json'
    legacy.symlink_to(unavailable)
    before = list(tmp_path.iterdir())
    preflight = maintain_response_index(frames_dir=tmp_path, action='rebuild', check_only=True)
    assert not preflight['ok'] and list(tmp_path.iterdir()) == before
    with pytest.raises(frames.ResponseFramePersistenceError) as raised:
        frames.persist_response_frame(frame('first'), frames_dir=tmp_path)
    assert raised.value.receipt['status'] == 'not_committed'
    assert legacy.is_symlink() and legacy.readlink() == unavailable
    assert not (tmp_path / 'responses.jsonl').exists()
    assert not (tmp_path / storage.SELECTOR_NAME).exists()
