"""Fault injection at the Ledger commit boundary; all bytes live in tmp_path."""

import errno
import json
import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from fruth_services import response_frames as rf
from fruth_services.response_persistence import ResponseFramePersistenceError


def frame(response_id='resp-storage'):
    return {
        'frame_version': 9, 'kind': 'fruth.response_frame',
        'response_id': response_id, 'status': 'completed',
        'current_state': {'id': response_id, 'status': 'completed',
                          'lifecycle_state': 'completed', 'output_text': 'Kept work.'},
        'output': {'item_count': 0, 'outputs': []}, 'artifacts': {'output': []},
    }


@pytest.mark.parametrize('tail', [b'{"unfinished":', b'\xf0\x9f', b'{"valid_json_but_no_newline":true}'])
def test_unterminated_tail_rejects_append_without_changing_any_existing_bytes(tmp_path, tail):
    ledger = rf.persist_response_frame(frame('resp-before'), frames_dir=tmp_path)
    with ledger.open('ab') as handle:
        handle.write(tail)
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    with pytest.raises(ResponseFramePersistenceError) as raised:
        rf.persist_response_frame(frame('resp-after'), frames_dir=tmp_path)
    receipt = raised.value.receipt
    assert receipt['status'] == 'not_committed'
    assert receipt['error']['code'] == 'response_frame_ledger_unterminated_tail'
    assert receipt['automatic_retry'] is False
    after = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    assert before == after


def test_torn_utf8_tail_does_not_hide_earlier_valid_frames_during_recovery(tmp_path):
    ledger = rf.persist_response_frame(frame('resp-before'), frames_dir=tmp_path)
    with ledger.open('ab') as handle:
        handle.write(b'{"response_id":"interrupted","text":"\xf0\x9f')
    rf._index_path(frames_dir=tmp_path).unlink()
    original = ledger.read_bytes()
    prior = rf.load_latest_response_state('resp-before', frames_dir=tmp_path)
    missing = rf.load_latest_response_state('interrupted', frames_dir=tmp_path)
    assert prior['ok']
    assert prior['response_frame']['response_id'] == 'resp-before'
    assert missing['status_code'] == 409
    assert missing['error']['code'] == 'response_frame_ledger_corrupt'
    assert ledger.read_bytes() == original


def test_binary_recovery_still_requires_the_existing_utf8_ledger_format(tmp_path):
    ledger = tmp_path / 'responses.jsonl'
    ledger.write_bytes((json.dumps(frame()) + '\n').encode('utf-16'))
    frames, errors = rf._iter_ledger_frames(ledger)
    assert frames == []
    assert errors


def test_index_failure_retains_committed_identity_and_recovers_without_duplicate_work(tmp_path):
    receipt = {}
    ledger = rf.persist_response_frame(frame(), frames_dir=tmp_path, receipt=receipt)
    parent_id = receipt['frame_id']
    index_path = rf._index_path(frames_dir=tmp_path)
    original_index = index_path.read_bytes()
    with patch.object(rf, '_write_response_frame_index', side_effect=OSError(errno.ENOSPC, 'index full')):
        with pytest.raises(ResponseFramePersistenceError) as raised:
            rf.append_response_frame_with_parent_cas(
                frame(), frames_dir=tmp_path, expected_parent_frame_id=parent_id,
                expected_parent_frame_sequence=1,
            )
    outcome = raised.value.receipt
    assert outcome['status'] == 'committed'
    assert outcome['index_status'] == 'failed'
    assert outcome['frame_sequence'] == 2
    assert outcome['frame_id'] == raised.value.frame['frame_id']
    assert index_path.read_bytes() == original_index
    recovered = rf.load_latest_response_state('resp-storage', frames_dir=tmp_path)
    assert recovered['ok']
    assert recovered['ledger_fallback_used']
    assert recovered['response_frame']['frame_id'] == outcome['frame_id']
    # Recovery is read-only, and the old parent cannot authorize a duplicate.
    before = ledger.read_bytes()
    with pytest.raises(rf.ResponseFrameParentCASMismatch):
        rf.append_response_frame_with_parent_cas(
            frame(), frames_dir=tmp_path, expected_parent_frame_id=parent_id,
            expected_parent_frame_sequence=1,
        )
    assert ledger.read_bytes() == before
    assert len(before.splitlines()) == 2


def test_ledger_fsync_failure_is_uncertain_even_if_bytes_can_be_read(tmp_path):
    native_fsync = os.fsync
    ledger = tmp_path / 'responses.jsonl'
    def fsync(fd):
        if ledger.exists() and os.fstat(fd).st_size > 0 and os.fstat(fd).st_ino == ledger.stat().st_ino:
            raise OSError(errno.EIO, 'synthetic ledger fsync failure')
        return native_fsync(fd)
    with patch.object(rf.os, 'fsync', side_effect=fsync), patch.object(rf, '_write_response_frame_index') as index:
        with pytest.raises(ResponseFramePersistenceError) as raised:
            rf.persist_response_frame(frame(), frames_dir=tmp_path)
    assert raised.value.receipt['status'] == 'uncertain'
    assert raised.value.receipt['stage'] == 'ledger_fsync'
    assert raised.value.receipt['index_status'] == 'not_attempted'
    assert json.loads(ledger.read_bytes())['response_id'] == 'resp-storage'
    index.assert_not_called()


def test_snapshot_preparation_failure_never_claims_an_append(tmp_path):
    with patch.object(rf, 'compact_response_frame_for_ledger', side_effect=OSError(errno.ENOSPC, 'snapshots full')):
        with pytest.raises(ResponseFramePersistenceError) as raised:
            rf.persist_response_frame(frame(), frames_dir=tmp_path)
    assert raised.value.receipt['status'] == 'not_committed'
    # Genesis is durably initialized before preparing the first frame, but no
    # frame or canonical evidence of the failed append has been committed.
    assert (tmp_path / 'responses.jsonl').read_bytes() == b''


@pytest.mark.legacy_response_index
def test_new_ledger_directory_fsync_failure_is_uncertain(tmp_path):
    native_fsync = os.fsync
    def fsync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError(errno.EIO, 'synthetic directory fsync failure')
        return native_fsync(fd)
    # Use an existing directory and a new Ledger, with snapshot preparation
    # omitted so the injected failure is specifically at the Ledger boundary.
    with patch.object(rf.os, 'fsync', side_effect=fsync), \
            patch.object(rf, 'compact_response_frame_for_ledger', side_effect=lambda value, **kw: value), \
            patch.object(rf, '_write_response_frame_index') as index:
        with pytest.raises(ResponseFramePersistenceError) as raised:
            rf.persist_response_frame(frame(), frames_dir=tmp_path)
    assert raised.value.receipt['status'] == 'uncertain'
    assert raised.value.receipt['stage'] == 'directory_fsync'
    assert json.loads((tmp_path / 'responses.jsonl').read_bytes())['response_id'] == 'resp-storage'
    index.assert_not_called()


def test_partial_write_is_uncertain_and_next_append_is_blocked(tmp_path):
    native_open = Path.open
    ledger = tmp_path / 'responses.jsonl'
    class TornWriter:
        def __init__(self, handle): self.handle = handle
        def __enter__(self): return self
        def __exit__(self, *args): self.handle.close()
        def fileno(self): return self.handle.fileno()
        def write(self, data):
            self.handle.write(data[:31])
            self.handle.flush()
            raise OSError(errno.ENOSPC, 'synthetic partial write')
    def open_path(path, mode='r', *args, **kwargs):
        handle = native_open(path, mode, *args, **kwargs)
        return TornWriter(handle) if path == ledger and mode == 'ab' else handle
    with patch.object(Path, 'open', open_path):
        with pytest.raises(ResponseFramePersistenceError) as raised:
            rf.persist_response_frame(frame(), frames_dir=tmp_path)
    assert raised.value.receipt['status'] == 'uncertain'
    assert raised.value.receipt['stage'] == 'append'
    before = ledger.read_bytes()
    with pytest.raises(ResponseFramePersistenceError) as blocked:
        rf.persist_response_frame(frame('resp-next'), frames_dir=tmp_path)
    assert blocked.value.receipt['status'] == 'not_committed'
    assert ledger.read_bytes() == before


def test_success_receipt_is_bound_to_actual_ledger_row_and_not_written_into_it(tmp_path):
    receipt = {}
    ledger = rf.persist_response_frame(frame(), frames_dir=tmp_path, receipt=receipt)
    row = json.loads(ledger.read_bytes())
    assert receipt['status'] == 'committed'
    assert receipt['index_status'] == 'published'
    assert receipt['frame_id'] == row['frame_id']
    assert receipt['line_length'] == ledger.stat().st_size
    assert '_frame' not in receipt
    assert 'persistence' not in row
