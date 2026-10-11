"""Admission regressions; controlled Chrome evidence supplements forged-header tests."""
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

import fruth_webserver as web
from fruth_core.transports import resolve_saved_artifact_path
from fruth_core.http_contract import action_headers
from tests.http_client import api_client

FOREIGN = 'http://localhost:49199'


@pytest.fixture
def isolated_api(tmp_path, monkeypatch):
    monkeypatch.setitem(web.app.config, 'TESTING', True)
    monkeypatch.setitem(web.app.config, 'GRAPH_REBASE_OPERATOR_TOKEN', 'a' * 40)
    monkeypatch.setitem(web.app.config, 'GRAPH_REBASE_OPERATOR_IDENTITY', 'audit-operator')
    monkeypatch.setattr(web, 'INFERENCE_PREFERENCES_PATH', tmp_path / 'preferences.json')
    monkeypatch.setattr(web, 'RUNTIME_STATUS_PATH', tmp_path / 'status.json')
    monkeypatch.setattr(web, 'SETTINGS_ARTIFACTS_DIR', tmp_path / 'settings')
    monkeypatch.setattr(web, '_log_unified_event', Mock())
    monkeypatch.setattr(web, '_saved_viewable_artifact_roots', lambda: {tmp_path.resolve()})
    monkeypatch.setattr(web, '_resolve_saved_downloadable_artifact_path',
        lambda path: resolve_saved_artifact_path(path, allowed_roots={tmp_path.resolve()}))
    with web.app.app_context():
        yield api_client(web.app, authorized=False), tmp_path


def seed_preferences():
    return web.persist_inference_preferences({'preferences': {'primary_mode': 'lock',
        'primary_target': {'backend': 'ollama', 'model': 'authority-audit-only'}}})


@pytest.mark.parametrize('encoding,body', [
    ('text/plain', '{"primary_target":{"model":"unread"}}'),
    ('application/x-www-form-urlencoded', 'primary_mode=manual'),
    ('multipart/form-data', {'primary_mode': 'manual'}),
])
def test_foreign_safelisted_preferences_post_preserves_state(isolated_api, encoding, body):
    client, root = isolated_api
    before = seed_preferences()
    assert before['preferences']['primary_target']['model'] == 'authority-audit-only'
    original = (root / 'preferences.json').read_bytes()
    response = client.post('/api/inference_preferences', data=body,
                           content_type=encoding, headers={'Origin': FOREIGN})
    assert response.status_code == 403
    assert (root / 'preferences.json').read_bytes() == original
    assert response.headers.get('Access-Control-Allow-Origin') is None


def test_matching_dashboard_origin_json_positive_control(isolated_api):
    client, root = isolated_api
    origin = f'http://127.0.0.1:{web.APP_PORT}'
    response = client.post('/api/inference_preferences', json={'preferences': {'primary_mode': 'lock',
        'primary_target': {'backend': 'ollama', 'model': 'authorized-fixture'}}},
        headers={'Origin': origin, **action_headers()})
    assert response.status_code == 200
    assert response.headers['Access-Control-Allow-Origin'] == origin
    assert json.loads((root / 'preferences.json').read_text())['preferences']['primary_target']['model'] == 'authorized-fixture'


def test_foreign_preflight_and_wrong_host_reject_before_persistence(isolated_api):
    client, root = isolated_api
    preflight = client.options('/api/inference_preferences', headers={
        'Origin': FOREIGN, 'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type'})
    assert preflight.headers.get('Access-Control-Allow-Origin') is None
    assert preflight.status_code == 403
    seed_preferences()
    original = (root / 'preferences.json').read_bytes()
    result = client.post('/api/inference_preferences', json={'preferences': {'primary_mode': 'lock',
        'primary_target': {'backend': 'ollama', 'model': 'forged-header-only'}}},
        headers={'Origin': FOREIGN, 'Host': 'untrusted.invalid'})
    assert result.status_code == 400
    assert (root / 'preferences.json').read_bytes() == original


@pytest.mark.parametrize('route', ['/api/infer', '/api/responses', '/v1/responses'])
def test_foreign_multipart_cannot_reach_execution_owner(isolated_api, monkeypatch, route):
    client, root = isolated_api
    captured = []
    def harmless(data, **kwargs):
        captured.append(dict(data))
        (root / 'dispatch.json').write_text(json.dumps(captured))
        return web.jsonify({'fixture_only': True})
    if route == '/api/infer':
        monkeypatch.setattr(web, '_execute_infer_request', harmless)
    else:
        def handle(**kwargs):
            return harmless(web.request.form)
        monkeypatch.setattr(web, '_handle_responses_request', handle)
    response = client.post(route, data={'prompt': 'Harmless isolated witness', 'instance_id': 'fixture'},
                           content_type='multipart/form-data', headers={'Origin': FOREIGN})
    assert response.status_code == 403
    assert captured == []
    assert not (root / 'dispatch.json').exists()
    assert response.headers.get('Access-Control-Allow-Origin') is None


@pytest.mark.parametrize('refresh', [False, True])
def test_originless_status_get_requires_action_only_for_refresh(isolated_api, monkeypatch, refresh):
    client, root = isolated_api
    status_path = root / 'status.json'
    original = b'{"instances": {}}\n'
    status_path.write_bytes(original)
    monkeypatch.setattr(web, 'load_running_instances', lambda: [])
    def harmless_refresh(instances, **kwargs):
        status_path.write_text('{"instances": {}, "fixture_refreshed": true}')
        return {}
    refresh_sink = Mock(side_effect=harmless_refresh)
    monkeypatch.setattr(web, 'refresh_runtime_status_entries', refresh_sink)
    response = client.get('/api/runtime_status' + ('?refresh=true' if refresh else ''))
    assert response.status_code == (403 if refresh else 200)
    refresh_sink.assert_not_called()
    assert status_path.read_bytes() == original
    assert response.headers.get('Access-Control-Allow-Origin') is None


@pytest.mark.parametrize('headers,expected', [
    ({}, 401),
    ({'Authorization': 'Bearer wrong', 'X-Fruth-Graph-Rebase-Operator': 'audit-operator'}, 401),
    ({'Authorization': 'Bearer ' + 'a' * 40, 'X-Fruth-Graph-Rebase-Operator': 'wrong-actor'}, 401),
    ({'Authorization': 'Bearer ' + 'a' * 40, 'X-Fruth-Graph-Rebase-Operator': '*'}, 400),
])
def test_operator_gate_rejects_missing_or_wrong_actor(isolated_api, monkeypatch, headers, expected):
    client, _ = isolated_api
    registry = Mock()
    monkeypatch.setattr(web, '_record_graph_rebase_operator_action', registry)
    response = client.post('/api/responses/fixture/graph_rebase/operator', json={'action': 'stage'},
                           headers={**action_headers(), **headers})
    assert response.status_code == expected
    registry.assert_not_called()


def test_correct_operator_credential_reaches_durable_truth_gate(isolated_api, monkeypatch):
    client, _ = isolated_api
    durable = Mock(return_value=(None, {'error': 'isolated missing frame'}, 404))
    monkeypatch.setattr(web, '_graph_rebase_payload_for_operator', durable)
    response = client.post('/api/responses/fixture/graph_rebase/operator', json={'action': 'adjudicate',
        'expected_response_id': 'fixture', 'expected_frame_id': 'frame-fixture',
        'expected_proposal_id': 'proposal-fixture', 'expected_base_graph_digest': 'base',
        'expected_candidate_graph_digest': 'candidate', 'expected_requested_rebase_class': 'partial_subtree_rebase',
        'expected_frame_sequence': 1},
        headers={**action_headers(), 'Authorization': 'Bearer ' + 'a' * 40,
                 'X-Fruth-Graph-Rebase-Operator': 'audit-operator'})
    assert response.status_code == 404
    durable.assert_called_once_with('fixture')


def test_delete_preserves_caller_and_path_confinement_gates(isolated_api):
    client, root = isolated_api
    file = root / 'harmless.txt'
    file.write_text('temporary')
    foreign = client.post('/api/delete_saved_artifact', json={'path': str(file)},
                          headers={'Origin': FOREIGN, **action_headers()})
    assert foreign.status_code == 403
    assert file.exists()
    denied = client.post('/api/delete_saved_artifact', json={'path': '/etc/passwd'}, headers=action_headers())
    assert denied.status_code == 400
    assert file.exists()
    deleted = client.post('/api/delete_saved_artifact', json={'path': str(file)}, headers=action_headers())
    assert deleted.status_code == 200
    assert not file.exists()


@pytest.mark.parametrize('origin', [FOREIGN, 'null', '', 'https://', 'http://127.0.0.1:5011/',
                                   'http://127.0.0.1:5011, http://localhost:5011'])
def test_untrusted_origin_is_rejected_even_with_action_marker(isolated_api, monkeypatch, origin):
    client, _ = isolated_api
    persist = Mock()
    monkeypatch.setattr(web, 'persist_inference_preferences', persist)
    response = client.post('/api/inference_preferences', json={},
                           headers={'Origin': origin, **action_headers()})
    assert response.status_code == 403
    assert response.json['error_code'] == 'HTTP_ORIGIN_NOT_ALLOWED'
    persist.assert_not_called()


@pytest.mark.parametrize('host', ['untrusted.invalid', '127.0.0.1:5012', '127.0.0.1',
                                 '127.0.0.1:5011, localhost:5011'])
def test_wrong_host_cannot_borrow_origin_or_forwarding_authority(isolated_api, monkeypatch, host):
    client, _ = isolated_api
    dispatch = Mock()
    monkeypatch.setattr(web, '_handle_responses_request', dispatch)
    response = client.post('/v1/responses', json={'input': 'fixture'}, headers={
        **action_headers(), 'Host': host, 'Origin': 'http://127.0.0.1:5011',
        'X-Forwarded-Host': '127.0.0.1:5011', 'Forwarded': 'host=127.0.0.1:5011',
    })
    assert response.status_code == 400
    assert response.json['error_code'] == 'HTTP_HOST_NOT_ALLOWED'
    dispatch.assert_not_called()


@pytest.mark.parametrize('marker', [None, '', '0', 'true', '1, 1'])
@pytest.mark.parametrize('origin', [None, 'http://127.0.0.1:5011'])
def test_missing_or_incorrect_action_marker_never_persists(isolated_api, monkeypatch, marker, origin):
    client, _ = isolated_api
    persist = Mock()
    monkeypatch.setattr(web, 'persist_inference_preferences', persist)
    headers = {}
    if marker is not None:
        headers['X-Fruth-Action'] = marker
    if origin is not None:
        headers['Origin'] = origin
    response = client.post('/api/inference_preferences', json={}, headers=headers)
    assert response.status_code == 403
    assert response.json['error_code'] == 'HTTP_ACTION_REQUIRED'
    persist.assert_not_called()


@pytest.mark.parametrize('media,body,expected,code', [
    ('text/plain', '{}', 415, 'PREFERENCES_UNSUPPORTED_MEDIA_TYPE'),
    ('application/x-www-form-urlencoded', 'primary_mode=manual', 415, 'PREFERENCES_UNSUPPORTED_MEDIA_TYPE'),
    ('multipart/form-data', {'primary_mode': 'manual'}, 415, 'PREFERENCES_UNSUPPORTED_MEDIA_TYPE'),
    (None, '{}', 415, 'PREFERENCES_UNSUPPORTED_MEDIA_TYPE'),
    ('application/json', '', 400, 'PREFERENCES_INVALID_JSON'),
    ('application/json', '   ', 400, 'PREFERENCES_INVALID_JSON'),
    ('application/json', '{', 400, 'PREFERENCES_INVALID_JSON'),
    ('application/json', b'\xff', 400, 'PREFERENCES_INVALID_JSON'),
    ('application/json', 'null', 400, 'PREFERENCES_OBJECT_REQUIRED'),
    ('application/json', '[]', 400, 'PREFERENCES_OBJECT_REQUIRED'),
    ('application/json', '[{}]', 400, 'PREFERENCES_OBJECT_REQUIRED'),
    ('application/json', '"text"', 400, 'PREFERENCES_OBJECT_REQUIRED'),
    ('application/json', '1', 400, 'PREFERENCES_OBJECT_REQUIRED'),
    ('application/json', 'false', 400, 'PREFERENCES_OBJECT_REQUIRED'),
])
def test_rejected_preference_body_preserves_exact_bytes(isolated_api, monkeypatch, media, body, expected, code):
    client, root = isolated_api
    seed_preferences()
    original = (root / 'preferences.json').read_bytes()
    persist = Mock(wraps=web.persist_inference_preferences)
    monkeypatch.setattr(web, 'persist_inference_preferences', persist)
    response = client.post('/api/inference_preferences', data=body, content_type=media,
                           headers=action_headers())
    assert response.status_code == expected
    assert response.json['error_code'] == code
    assert (root / 'preferences.json').read_bytes() == original
    persist.assert_not_called()


@pytest.mark.parametrize('media', ['application/json', 'application/json; charset=utf-8',
                                  'application/vnd.fruth.preferences+json'])
def test_declared_native_client_can_intentionally_reset(isolated_api, media):
    client, root = isolated_api
    seed_preferences()
    response = client.post('/api/inference_preferences', data='{}', content_type=media,
                           headers=action_headers())
    assert response.status_code == 200
    assert json.loads((root / 'preferences.json').read_text())['preferences'] == {}


@pytest.mark.parametrize('route', ['/api/infer', '/api/responses', '/v1/responses',
                                  '/api/local_provider/fixture/v1/responses'])
def test_admitted_multipart_preserves_form_and_file(isolated_api, monkeypatch, route):
    import io
    client, _ = isolated_api
    captured = []
    def handle(*args, **kwargs):
        captured.append((web.request.form.to_dict(), web.request.files['file'].read()))
        return web.jsonify({'fixture_only': True})
    monkeypatch.setattr(web, '_execute_infer_request', handle)
    monkeypatch.setattr(web, '_handle_responses_request', handle)
    response = client.post(route, data={'prompt': 'intentional', 'file': (io.BytesIO(b'file bytes'), 'input.txt')},
        headers={'Origin': 'http://127.0.0.1:5011', **action_headers()})
    assert response.status_code == 200
    assert captured == [({'prompt': 'intentional'}, b'file bytes')]


def test_admitted_refresh_runs_exact_writer(isolated_api, monkeypatch):
    client, _ = isolated_api
    monkeypatch.setattr(web, 'load_running_instances', lambda: [])
    writer = Mock(return_value={})
    monkeypatch.setattr(web, 'refresh_runtime_status_entries', writer)
    assert client.get('/api/runtime_status?refresh=true', headers=action_headers()).status_code == 200
    writer.assert_called_once_with([], path=web.RUNTIME_STATUS_PATH)


@pytest.mark.parametrize('route', ['/api/running_instances', '/api/runtime_status', '/api/runtime_manifest',
    '/api/routing_table', '/api/backend_fabric', '/api/inference', '/api/agent_contract',
    '/api/integrations/codex/status'])
def test_every_explicit_refresh_get_requires_action(isolated_api, route):
    client, _ = isolated_api
    response = client.get(route + '?refresh=y')
    assert response.status_code == 403
    assert response.json['error_code'] == 'HTTP_ACTION_REQUIRED'


@pytest.mark.parametrize('route', ['/api/responses', '/v1/responses'])
def test_matching_origin_preflight_declares_action_header(isolated_api, route):
    client, _ = isolated_api
    response = client.options(route, headers={'Origin': 'http://localhost:5011',
        'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'content-type,x-fruth-action'})
    assert response.status_code == 200
    assert response.headers['Access-Control-Allow-Origin'] == 'http://localhost:5011'
    assert 'X-Fruth-Action' in response.headers['Access-Control-Allow-Headers']


def test_operator_credentials_do_not_bypass_browser_channel(isolated_api, monkeypatch):
    client, _ = isolated_api
    durable = Mock()
    monkeypatch.setattr(web, '_graph_rebase_payload_for_operator', durable)
    response = client.post('/api/responses/fixture/graph_rebase/operator', json={'action': 'adjudicate'},
        headers={'Authorization': 'Bearer ' + 'a' * 40, 'X-Fruth-Graph-Rebase-Operator': 'audit-operator'})
    assert response.status_code == 403
    durable.assert_not_called()


def test_trusted_server_configuration_controls_host_origin_and_alias_cors(isolated_api, monkeypatch):
    client, _ = isolated_api
    monkeypatch.setitem(web.app.config, 'FRUTH_HTTP_ALLOWED_ORIGINS', ('http://fixture.local:51423',))
    dispatch = Mock(return_value=web.jsonify({'fixture_only': True}))
    monkeypatch.setattr(web, '_handle_responses_request', dispatch)
    response = client.post('/v1/responses', base_url='http://fixture.local:51423',
        json={'input': 'intentional'}, headers={**action_headers(), 'Origin': 'http://fixture.local:51423'})
    assert response.status_code == 200
    assert response.headers['Access-Control-Allow-Origin'] == 'http://fixture.local:51423'
    assert dispatch.call_count == 1
    denied = client.post('/v1/responses', json={'input': 'intentional'}, headers=action_headers())
    assert denied.status_code == 400
    assert dispatch.call_count == 1


def test_preview_preparation_requires_action_and_signed_navigation_is_passive(isolated_api, monkeypatch):
    client, root = isolated_api
    bundle = root / 'project'
    bundle.mkdir()
    page = bundle / 'index.html'
    page.write_text('<!doctype html><h1>Scoped preview</h1>')
    package_writer = Mock(side_effect=AssertionError('Portable preview must not create a package'))
    monkeypatch.setattr(web, '_create_response_bound_saved_html_preview_package', package_writer)
    preparation = '/api/preview_saved_artifact'
    rejected = client.get(preparation, query_string={'path': str(page), 'response_id': 'fixture'})
    assert rejected.status_code == 403
    assert rejected.json['error_code'] == 'HTTP_ACTION_REQUIRED'
    package_writer.assert_not_called()
    # Explicit fixture artifact base uses the same genuine HMAC/navigation path.
    monkeypatch.setattr(web, '_saved_artifact_interactive_preview_base_root_for_path', lambda path: bundle)
    prepared = client.get(preparation, query_string={'path': str(page)}, headers=action_headers())
    assert prepared.status_code == 200
    url = prepared.headers['X-Fruth-Preview-Url']
    assert url.startswith('/api/preview_saved_artifact_wrapper/')
    navigated = client.get(url)
    assert navigated.status_code == 200
    assert 'sandbox="allow-scripts allow-top-navigation-to-custom-protocols"' in navigated.text
    assert "frame-ancestors 'self'" in navigated.headers['Content-Security-Policy']
    package_writer.assert_not_called()
    assert client.get(url.replace('index.html', '../outside.html')).status_code == 404


def test_signed_preview_rejects_forgery_and_escape_while_serving_exact_asset(isolated_api):
    client, root = isolated_api
    bundle = root / 'bundle'
    bundle.mkdir()
    asset = bundle / 'data.txt'
    asset.write_text('only this bundle')
    token = web._encode_saved_artifact_interactive_preview_base_root(bundle)
    assert web._decode_saved_artifact_interactive_preview_base_root(token) == bundle
    forged = ('B' if token[0] != 'B' else 'C') + token[1:]
    assert web._decode_saved_artifact_interactive_preview_base_root(forged) is None
    assert web._decode_saved_artifact_interactive_preview_base_root(
        web._encode_saved_artifact_preview_base_root(bundle)) is None
    assert web._resolve_saved_artifact_interactive_preview_asset_path(token, '../preferences.json') is None
    outside = root / 'sibling.txt'
    outside.write_text('not in bundle')
    (bundle / 'escape.txt').symlink_to(outside)
    assert web._resolve_saved_artifact_interactive_preview_asset_path(token, 'escape.txt') is None
    result = client.get(f'/api/preview_saved_artifact_assets/{token}/data.txt', headers={'Origin': FOREIGN})
    assert result.status_code == 200
    assert result.data == asset.read_bytes()
    assert result.headers['Access-Control-Allow-Origin'] == '*'
    assert "sandbox" in result.headers['Content-Security-Policy']


def test_interactive_html_csp_scopes_network_and_keeps_opaque_origin(isolated_api):
    _, root = isolated_api
    bundle = root / 'bundle'
    bundle.mkdir()
    page = bundle / 'index.html'
    page.write_text('<script>fetch("/api/inference_preferences")</script>')
    token = web._encode_saved_artifact_interactive_preview_base_root(bundle)
    with web.app.test_request_context('/api/preview_saved_artifact_assets/' + token + '/index.html'):
        result = web._send_saved_artifact_interactive_preview_asset_response(page, base_token=token)
    policy = result.headers['Content-Security-Policy']
    assert 'allow-same-origin' not in policy
    assert "form-action 'none'" in policy
    connect = next(p.strip() for p in policy.split(';') if p.strip().startswith('connect-src '))
    assert '/api/preview_saved_artifact_assets/' + token + '/' in connect
    assert 'connect-src *' not in policy
    assert page.read_text() == '<script>fetch("/api/inference_preferences")</script>'
