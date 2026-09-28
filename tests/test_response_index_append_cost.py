"""Index representation and absence proofs use only synthetic temporary history."""
import json
import os
from unittest.mock import patch

import pytest

from fruth_services import response_frames as frames
from tests.test_response_persistence import frame


def test_compact_index_preserves_legacy_json_values_map_proof_and_recovery(tmp_path):
    ledger = frames.persist_response_frame(frame('resp-first'), frames_dir=tmp_path)
    index = tmp_path / 'current_index.json'
    raw = index.read_bytes()
    decoded = json.loads(raw)
    pretty = (json.dumps(decoded, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
    assert len(raw) < len(pretty)
    assert raw.count(b'\n') == 1
    index.write_bytes(pretty)
    legacy = frames.load_response_frame_index(frames_dir=tmp_path)
    assert frames._response_frame_index_has_verified_response_map(legacy, ledger)
    before = ledger.read_bytes()
    frames.persist_response_frame(frame('resp-second'), frames_dir=tmp_path)
    current = frames.load_response_frame_index(frames_dir=tmp_path)
    assert current['responses']['resp-first'] == legacy['responses']['resp-first']
    assert frames._response_frame_index_has_verified_response_map(current, ledger)
    assert ledger.read_bytes().startswith(before)
    for rid in ('resp-first', 'resp-second'):
        recovered = frames.load_latest_response_state(rid, frames_dir=tmp_path)
        assert recovered['ok']
        assert recovered['response_frame']['frame_sequence'] == 1
        assert recovered['response_payload']['output_text'] == 'Kept work.'


def test_proved_new_response_append_does_not_scan_unrelated_ledger(tmp_path):
    frames.persist_response_frame(frame('resp-first'), frames_dir=tmp_path)
    with patch.object(frames, '_iter_ledger_frames', side_effect=AssertionError('unexpected full scan')):
        frames.persist_response_frame(frame('resp-new'), frames_dir=tmp_path)
        recovered = frames.load_latest_response_state('resp-new', frames_dir=tmp_path)
    assert recovered['ok']
    assert recovered['response_frame']['frame_sequence'] == 1


@pytest.mark.parametrize('damage', ['missing', 'legacy', 'corrupt', 'digest', 'incomplete', 'stale'])
def test_uncertain_index_retains_ledger_fallback_for_new_response(tmp_path, damage):
    frames.persist_response_frame(frame('resp-first'), frames_dir=tmp_path)
    index = tmp_path / 'current_index.json'
    old = index.read_bytes()
    frames.persist_response_frame(frame('resp-second'), frames_dir=tmp_path)
    data = json.loads(index.read_bytes())
    if damage == 'missing':
        index.unlink()
    elif damage == 'corrupt':
        index.write_text('{broken')
    elif damage == 'stale':
        index.write_bytes(old)
    else:
        if damage == 'legacy':
            data.pop('response_map_verified_size_bytes')
        elif damage == 'digest':
            data['response_map_digest'] = '0' * 64
        else:
            data['responses'].pop('resp-first')
        index.write_text(json.dumps(data))
    with patch.object(frames, '_iter_ledger_frames', wraps=frames._iter_ledger_frames) as scan:
        frames.persist_response_frame(frame('resp-new'), frames_dir=tmp_path)
    assert scan.call_count >= 1
    assert frames.load_latest_response_state('resp-first', frames_dir=tmp_path)['ok']
    assert frames.load_latest_response_state('resp-new', frames_dir=tmp_path)['ok']


@pytest.mark.parametrize('moving_file', ['current_index.json', 'responses.jsonl'])
def test_same_byte_replacement_during_absence_proof_retains_scan(tmp_path, moving_file):
    frames.persist_response_frame(frame('resp-first'), frames_dir=tmp_path)
    native = frames._response_frame_index_has_verified_response_map
    moved = []

    def proof(index, ledger):
        result = native(index, ledger)
        if not moved:
            target = tmp_path / moving_file
            old_stat = target.stat()
            replacement = target.with_suffix('.replacement')
            replacement.write_bytes(target.read_bytes())
            os.utime(replacement, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
            replacement.replace(target)
            moved.append(True)
        return result

    with patch.object(frames, '_response_frame_index_has_verified_response_map', side_effect=proof), \
            patch.object(frames, '_iter_ledger_frames', wraps=frames._iter_ledger_frames) as scan:
        frames.persist_response_frame(frame('resp-new'), frames_dir=tmp_path)
    assert moved and scan.call_count >= 1
    assert frames.load_latest_response_state('resp-first', frames_dir=tmp_path)['ok']


def test_new_response_cannot_satisfy_expected_parent_cas(tmp_path):
    frames.persist_response_frame(frame('resp-first'), frames_dir=tmp_path)
    ledger = tmp_path / 'responses.jsonl'
    before = ledger.read_bytes()
    with pytest.raises(frames.ResponseFrameParentCASMismatch):
        frames.append_response_frame_with_parent_cas(
            frame('resp-new'), expected_parent_frame_id='resp-new:frame-1', frames_dir=tmp_path)
    assert ledger.read_bytes() == before


def test_incomplete_map_cannot_reset_existing_response_lineage(tmp_path):
    receipt = {}
    frames.persist_response_frame(frame('resp-hidden'), frames_dir=tmp_path)
    ledger = frames.persist_response_frame(frame('resp-hidden'), frames_dir=tmp_path, receipt=receipt)
    frames.persist_response_frame(frame('resp-other'), frames_dir=tmp_path)
    index = tmp_path / 'current_index.json'
    data = json.loads(index.read_bytes())
    data['responses'].pop('resp-hidden')
    index.write_text(json.dumps(data))
    before = ledger.read_bytes()
    appended = frames.append_response_frame_with_parent_cas(
        frame('resp-hidden'), frames_dir=tmp_path,
        expected_parent_frame_id=receipt['frame_id'], expected_parent_frame_sequence=2)
    assert appended['response_frame']['frame_sequence'] == 3
    assert ledger.read_bytes().startswith(before)
    recovered = frames.load_latest_response_state('resp-hidden', frames_dir=tmp_path)
    assert recovered['ok']
    assert recovered['response_frame']['frame_id'] == appended['response_frame']['frame_id']
    assert recovered['response_frame']['frame_sequence'] == 3
