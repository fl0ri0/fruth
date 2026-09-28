"""Storage and active-content boundaries; fake work, real temporary persistence."""

import errno
import gzip
import json
import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

import fruth_webserver as web
from fruth_services import response_frames as rf
from fruth_services.response_persistence import ResponsePersistenceError


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setitem(web.app.config, 'TESTING', False)
    monkeypatch.setattr(web, 'RESPONSE_FRAMES_DIR', tmp_path / 'frames')
    monkeypatch.setattr(web, 'ARTIFACT_REGISTRY_LEDGER', tmp_path / 'artifacts.jsonl')
    monkeypatch.setattr(web, 'CHAT_HISTORY_DIR', tmp_path / 'history')
    monkeypatch.setattr(web, 'ARTIFACT_OUTPUTS_IMAGES_DIR', tmp_path / 'images')
    monkeypatch.setattr(web, 'ARTIFACT_OUTPUTS_DOCUMENTS_DIR', tmp_path / 'documents')
    monkeypatch.setattr(web, 'ARTIFACT_BUNDLES_DIR', tmp_path / 'bundles')
    monkeypatch.setattr(web, '_register_durable_graph_rebase_readiness_observation', Mock(return_value={'status': 'not_relevant'}))
    monkeypatch.setattr(web, '_persist_output_artifact_registry_records', Mock(return_value=None))
    monkeypatch.setattr(web, '_RESPONSE_LOOKUP', {})
    monkeypatch.setattr(web._RESPONSES_RUNTIME, 'response_lookup', web._RESPONSE_LOOKUP)
    with web.app.app_context():
        yield web.app.test_client()


def payload(response_id='resp-api-storage'):
    return {'id': response_id, 'object': 'response', 'status': 'completed',
            'output_text': 'The work already exists.'}


def inject_index_failure():
    return patch.object(rf, '_write_response_frame_index', side_effect=OSError(errno.ENOSPC, 'index full'))


def test_confirmed_ledger_survives_index_failure_without_semantic_failure(isolated):
    with inject_index_failure():
        result = web._finalize_response_frame_payload(payload(), request_payload={'prompt': 'Hello'})
    assert result['persistence']['status'] == 'committed'
    assert result['persistence']['index_status'] == 'failed'
    assert result['lifecycle_state'] == 'completed'
    assert len((web.RESPONSE_FRAMES_DIR / 'responses.jsonl').read_bytes().splitlines()) == 1
    public = web._project_response_payload_for_wire(result)
    assert public['persistence'] == result['persistence']
    recovered = rf.load_latest_response_state(result['id'], frames_dir=web.RESPONSE_FRAMES_DIR)
    assert recovered['ok']
    assert recovered['response_frame']['frame_id'] == result['persistence']['frame_id']


def test_registry_failure_is_visible_but_does_not_undo_a_ledger_commit(isolated):
    with patch.object(web, '_persist_output_artifact_registry_records', side_effect=OSError(errno.ENOSPC, 'registry full')):
        result = web._finalize_response_frame_payload(payload())
    assert result['persistence']['status'] == 'committed'
    assert result['persistence']['artifact_registry']['status'] == 'failed'
    assert result['lifecycle_state'] == 'completed'


def test_metadata_preparation_failure_is_not_an_uncertain_append(isolated):
    with patch.object(web, '_enrich_response_frame_for_ledger_append', side_effect=OSError(errno.ENOSPC, 'full')):
        with pytest.raises(ResponsePersistenceError) as raised:
            web._finalize_response_frame_payload(payload())
    assert raised.value.response_payload['persistence']['status'] == 'not_committed'
    assert not (web.RESPONSE_FRAMES_DIR / 'responses.jsonl').exists()


@pytest.mark.parametrize('failure', ['prepare', 'fsync', 'tail'])
@pytest.mark.parametrize('existing_parent', [False, True])
def test_storage_failure_blocks_http_lookup_and_retry_without_losing_work(isolated, failure, existing_parent):
    ledger = web.RESPONSE_FRAMES_DIR / 'responses.jsonl'
    source = web._finalize_response_frame_payload(payload()) if existing_parent else payload()
    if failure == 'tail':
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with ledger.open('ab') as handle:
            handle.write(b'{"interrupted":')
        injection = patch.object(web, '_persist_output_artifact_registry_records', return_value=None)
    elif failure == 'prepare':
        injection = patch.object(rf, 'compact_response_frame_for_ledger', side_effect=OSError(errno.ENOSPC, 'snapshot full'))
    else:
        native = os.fsync
        def fsync(fd):
            if ledger.exists() and os.fstat(fd).st_ino == ledger.stat().st_ino:
                raise OSError(errno.EIO, 'fsync uncertain')
            return native(fd)
        injection = patch.object(rf.os, 'fsync', side_effect=fsync)
    def finish(**kwargs):
        return web._finalize_response_frame_payload(source, request_payload={'prompt': 'Hello'})
    with injection, patch.object(web, '_handle_responses_request', side_effect=finish):
        response = isolated.post('/api/responses', json={'prompt': 'Hello'})
    assert response.status_code == (507 if failure == 'prepare' else 503)
    body = response.get_json()
    assert body['lifecycle_state'] == 'blocked'
    assert body['persistence']['status'] == ('uncertain' if failure == 'fsync' else 'not_committed')
    assert body['error']['retryable'] is False
    assert body['response_frame']['status'] == 'completed'
    assert body['output_text'] == 'The work already exists.'
    for view in ('status', 'ui', 'truth', 'debug'):
        lookup = isolated.get('/api/responses/resp-api-storage', query_string={'view': view})
        assert lookup.status_code == 200, lookup.get_json()
        observed = lookup.get_json()
        assert observed['lifecycle_state'] == 'blocked', (view, observed)
        assert observed['persistence']['status'] == body['persistence']['status'], view
    with patch.object(web, '_schedule_response_late_fill') as schedule:
        retry = isolated.post('/api/responses/resp-api-storage/late_fill/retry', json={'branch_id': 'any'})
    assert retry.status_code == 409
    schedule.assert_not_called()


def test_failed_storage_emits_failure_instead_of_completed_stream(isolated):
    web._register_response_stream('resp-api-storage')
    try:
        with patch.object(rf, 'compact_response_frame_for_ledger', side_effect=OSError(errno.ENOSPC, 'full')):
            with pytest.raises(ResponsePersistenceError):
                web._finalize_response_frame_payload(payload())
        events, done = web._wait_for_response_stream_events('resp-api-storage', 0)
        stream = ''.join(events)
        assert done
        assert 'event: response.failed' in stream
        assert 'event: response.completed' not in stream
        assert 'response_persistence_failed' in stream
    finally:
        web._close_response_stream('resp-api-storage')


@pytest.mark.parametrize('suffix', ['.svg', '.SVG', '.svgz'])
def test_svg_view_assets_and_download_are_sandboxed_with_identical_bytes(isolated, suffix):
    web.ARTIFACT_OUTPUTS_IMAGES_DIR.mkdir()
    svg = web.ARTIFACT_OUTPUTS_IMAGES_DIR / ('drawing' + suffix)
    body = (b'<svg xmlns="http://www.w3.org/2000/svg" onload="window.parent.bad=true">'
            b'<style>rect{fill:lime}</style><rect width="20" height="20"/>'
            b'<script>fetch("/api/runtime_status")</script></svg>')
    raw = gzip.compress(body) if suffix == '.svgz' else body
    svg.write_bytes(raw)
    with web.app.test_request_context():
        base = web._saved_artifact_preview_base_href(svg)
    responses = [
        isolated.get('/api/view_saved_artifact', query_string={'path': str(svg)}),
        isolated.get(base + svg.name),
        isolated.get('/api/download_saved_artifact', query_string={'path': str(svg)}),
    ]
    for response in responses:
        assert response.status_code == 200
        assert response.data == raw
        csp = response.headers['Content-Security-Policy']
        assert 'sandbox;' in csp and "default-src 'none'" in csp
        assert 'allow-scripts' not in csp and 'allow-same-origin' not in csp
        assert "img-src data:" in csp
        assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert responses[0].headers['Content-Disposition'].startswith('inline')
    assert responses[2].headers['Content-Disposition'].startswith('attachment')
    for response in responses[:2]:
        assert response.headers.get('Content-Encoding') == ('gzip' if suffix == '.svgz' else None)
    assert 'Content-Encoding' not in responses[2].headers


def test_raster_view_keeps_ordinary_delivery(isolated):
    web.ARTIFACT_OUTPUTS_IMAGES_DIR.mkdir()
    path = web.ARTIFACT_OUTPUTS_IMAGES_DIR / 'pixel.png'
    path.write_bytes(b'\x89PNG\r\n\x1a\n')
    response = isolated.get('/api/view_saved_artifact', query_string={'path': str(path)})
    assert response.status_code == 200
    assert response.data == path.read_bytes()
    assert response.mimetype == 'image/png'
    assert response.headers['Content-Disposition'].startswith('inline')
