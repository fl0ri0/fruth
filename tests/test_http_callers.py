"""Public action marker is emitted by actual native/client configuration owners."""

import io
import json
import tomllib

import pytest

from helpers import fruthctl
from fruth_integrations.codex.config_sync import build_provider_blocks
from scripts.run_graph_rebase_shadow_corpus import JsonHttpClient


class _Reply(io.BytesIO):
    status = 200
    headers = {}


@pytest.mark.parametrize('method,path,payload', [
    ('POST', '/api/responses', {'input': 'intentional'}),
    ('DELETE', '/api/chat_history', None),
    ('GET', '/api/runtime_status?refresh=true', None),
])
def test_fruthctl_declares_actions_without_changing_payload(monkeypatch, method, path, payload):
    captured = []
    def open_request(request, **kwargs):
        captured.append(request)
        return _Reply(b'{}')
    monkeypatch.setattr(fruthctl, 'urlopen', open_request)
    fruthctl._request(method, 'http://127.0.0.1:5011', path, payload=payload)
    request = captured[0]
    assert request.get_header('X-fruth-action') == '1'
    assert request.get_method() == method
    assert (json.loads(request.data) if request.data else None) == payload


@pytest.mark.parametrize('method,path,payload', [
    ('POST', '/api/responses', {'input': 'intentional'}),
    ('GET', '/api/runtime_status?refresh=true', None),
])
def test_conformance_http_owner_declares_actions(monkeypatch, method, path, payload):
    client = JsonHttpClient('http://127.0.0.1:5011')
    captured = []
    def open_request(request, **kwargs):
        captured.append(request)
        return _Reply(b'{}')
    monkeypatch.setattr(client._opener, 'open', open_request)
    assert client.request_json(method, path, payload=payload).ok
    assert captured[0].get_header('X-fruth-action') == '1'
    assert (json.loads(captured[0].data) if captured[0].data else None) == payload


def test_synced_codex_control_plane_provider_declares_action_but_direct_provider_does_not():
    blocks, count = build_provider_blocks([
        {'port': 11435, 'instance_id': 'fixture', 'model': 'fixture'},
        {'port': 11436, 'model': 'direct-provider'},
    ])
    parsed = tomllib.loads(blocks)['model_providers']
    assert count == 2
    assert parsed['local-11435']['http_headers'] == {'X-Fruth-Action': '1'}
    assert parsed['local-11435']['base_url'].endswith('/api/local_provider/fixture/v1')
    assert 'http_headers' not in parsed['local-11436']
