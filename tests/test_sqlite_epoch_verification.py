"""Full SQLite Epoch evidence with one audit and independent final guards."""
import json
from unittest.mock import patch

import pytest

from fruth_services import response_frames as frames, response_index_sqlite as storage
from tests.test_response_index_sqlite import history


def test_epoch_audits_tree_once_and_hashes_complete_db_at_both_boundaries(tmp_path):
    history(tmp_path)
    with patch.object(storage,'_complete_map',wraps=storage._complete_map) as audit, \
         patch.object(frames,'_stable_response_frame_index_snapshot',side_effect=AssertionError('JSON round trip')), \
         patch.object(frames,'_file_sha256',wraps=frames._file_sha256) as hashes:
        epoch=frames.verify_response_frame_epoch(frames_dir=tmp_path)
    assert epoch['ok'],epoch
    assert audit.call_count==1 and hashes.call_count==2
    assert all(c.args[0]==frames._index_path(frames_dir=tmp_path) for c in hashes.call_args_list)


@pytest.mark.parametrize('change',['entry','off_path_bytes','replace_same_bytes','selector'])
def test_epoch_retains_ledger_correspondence_and_final_movement_checks(tmp_path,change):
    path=history(tmp_path)
    native=frames._scan_response_frame_ledger_index_truth
    def scan(*args,**kwargs):
        result=native(*args,**kwargs)
        if change=='entry':
            result['entries']['resp-0001']['effective_snapshot_manifest']['extra']={'sha256':'0'*64}
        elif change=='off_path_bytes':
            with path.open('r+b') as f:
                f.seek(-1,2); old=f.read(1); f.seek(-1,2); f.write(bytes([old[0]^1]))
        elif change=='replace_same_bytes':
            other=tmp_path/'replacement'; other.write_bytes(path.read_bytes()); other.replace(path)
        else:
            selector=tmp_path/storage.SELECTOR_NAME
            selected=json.loads(selector.read_bytes()); selected['generation']='0'*32
            selector.write_bytes(storage.encode(selected))
        return result
    with patch.object(frames,'_scan_response_frame_ledger_index_truth',side_effect=scan):
        epoch=frames.verify_response_frame_epoch(frames_dir=tmp_path)
    assert not epoch['ok']
    assert epoch['error']['code']==('response_frame_index_ledger_correspondence_mismatch'
                                   if change=='entry' else 'response_frame_index_moved')
