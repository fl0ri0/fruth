"""Run in a disposable offline source checkout; no live inference requests."""

from unittest.mock import patch

import pytest

import fruth_webserver as web
from fruth_services import response_frames as rf
from fruth_services import response_index_sqlite as storage
from fruth_services.response_index_maintenance import maintain_response_index
from tests.test_storage_and_svg_api import isolated, payload
from tests.response_index_fixtures import legacy_history
from tests.test_response_persistence import frame
from fruth_services.response_persistence import ResponsePersistenceError


def sqlite_root():
    result = maintain_response_index(frames_dir=web.RESPONSE_FRAMES_DIR,
                                     action='migrate', writers_stopped=True)
    assert result['ok'], result


def test_finalizer_wire_and_all_http_lookup_views_preserve_frame_identity(isolated):
    sqlite_root()
    with patch.object(storage, '_complete_map', side_effect=AssertionError('unexpected enumeration')):
        result = web._finalize_response_frame_payload(payload(), request_payload={'prompt': 'Hello'})
        public, state = web._response_wire_payload_from_index(result['id'])
        assert public and state['ok']
    assert result['persistence']['index_status'] == 'published'
    for view in ('ui', 'status', 'debug', 'truth'):
        response = isolated.get('/api/responses/resp-api-storage', query_string={'view': view})
        assert response.status_code == 200, (view, response.get_json())
        body = response.get_json()
        assert body['id'] == result['id']
        assert body['lifecycle_state'] == 'completed'
    epoch = rf.verify_response_frame_epoch(frames_dir=web.RESPONSE_FRAMES_DIR)
    assert epoch['ok'], epoch
    assert epoch['index_state']['responses'][result['id']]['latest_frame_id'] == result['persistence']['frame_id']


def test_postcommit_checkpoint_failure_keeps_saved_work_recoverable_in_http(isolated):
    sqlite_root()
    native = rf._atomic_replace_file_bytes
    def fail_checkpoint(path, data):
        if path.name == storage.SELECTOR_NAME:
            raise OSError('checkpoint disk full')
        return native(path, data)
    with patch.object(rf, '_atomic_replace_file_bytes', side_effect=fail_checkpoint):
        result = web._finalize_response_frame_payload(payload(), request_payload={'prompt': 'Hello'})
    assert result['persistence']['status'] == 'committed'
    assert result['persistence']['index_status'] == 'failed'
    before = (web.RESPONSE_FRAMES_DIR / 'responses.jsonl').read_bytes()
    for view in ('ui', 'status', 'truth'):
        response = isolated.get('/api/responses/resp-api-storage', query_string={'view': view})
        assert response.status_code == 200, response.get_json()
        assert response.get_json()['lifecycle_state'] == 'completed'
    assert (web.RESPONSE_FRAMES_DIR / 'responses.jsonl').read_bytes() == before


def test_unmigrated_finalizer_guidance_precedes_registry_and_ledger_writes(isolated):
    legacy_history(web.RESPONSE_FRAMES_DIR,[frame('old-response')])
    before={p:p.read_bytes() for p in web.RESPONSE_FRAMES_DIR.rglob('*') if p.is_file()}
    with patch.object(web,'_persist_output_artifact_registry_records',side_effect=AssertionError('unmigrated write')) as registry:
        import pytest
        with pytest.raises(ResponsePersistenceError) as raised:
            web._finalize_response_frame_payload(payload(),request_payload={'prompt':'Hello'})
    receipt=raised.value.response_payload['persistence']
    assert receipt['error']['code']=='response_frame_index_migration_required'
    assert receipt['status']=='not_committed' and receipt['artifact_registry']['status']=='not_attempted'
    registry.assert_not_called()
    assert {p:p.read_bytes() for p in web.RESPONSE_FRAMES_DIR.rglob('*') if p.is_file()}==before
    for view in ('ui','status','truth'):
        response=isolated.get('/api/responses/resp-api-storage',query_string={'view':view})
        assert response.status_code==200,response.get_json()
        assert response.get_json()['persistence']['error']['code']=='response_frame_index_migration_required'
