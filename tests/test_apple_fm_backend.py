"""AFM conformance with isolated registry and deterministic HTTP/process evidence."""
import json
import io
from unittest.mock import Mock

import pytest
import requests
from urllib3.response import HTTPResponse

from fruth_runtime import apple_fm_model_manager as fm
from fruth_runtime import ollama_model_manager as ollama
from fruth_core.transports import (
    AppleFMTransportError, apple_fm_chat_payload, iter_apple_fm_stream_deltas,
    validate_apple_fm_response,
)
from helpers.session_controls import build_session_controls


@pytest.fixture
def registry(tmp_path, monkeypatch):
    path = tmp_path / 'model_ports.json'
    path.write_text('[]')
    monkeypatch.setattr(fm, 'CONFIG_FILE', path)
    monkeypatch.setattr(fm, 'LOG_DIR', tmp_path / 'logs')
    monkeypatch.setattr(fm, 'is_port_listening', lambda port: False)
    monkeypatch.setattr(ollama, 'is_port_listening', lambda port: False)
    return path


def test_ports_boundaries_occupancy_and_exhaustion(registry, monkeypatch):
    assert fm.APPLE_FM_START_PORT == fm.LLAMA_CPP_PORT_MAX + 1
    assert fm.APPLE_FM_PORT_MAX - fm.APPLE_FM_START_PORT + 1 == 50
    assert fm._next_free_port() == fm.APPLE_FM_START_PORT
    with pytest.raises(ValueError):
        fm._next_free_port(fm.APPLE_FM_START_PORT - 1)
    with pytest.raises(ValueError):
        fm._next_free_port(fm.APPLE_FM_PORT_MAX + 1)
    assert fm._next_free_port(fm.APPLE_FM_PORT_MAX) == fm.APPLE_FM_PORT_MAX
    monkeypatch.setattr(ollama, 'is_port_listening', lambda p: p == fm.APPLE_FM_START_PORT)
    assert fm._next_free_port() == fm.APPLE_FM_START_PORT + 1
    registry.write_text(json.dumps([{'port': p} for p in range(fm.APPLE_FM_START_PORT, fm.APPLE_FM_PORT_MAX)]))
    assert fm._next_free_port() == fm.APPLE_FM_PORT_MAX
    with pytest.raises(RuntimeError, match='occupied'):
        fm._next_free_port(fm.APPLE_FM_START_PORT)
    registry.write_text(json.dumps([{'port': p} for p in range(fm.APPLE_FM_START_PORT, fm.APPLE_FM_PORT_MAX + 1)]))
    with pytest.raises(RuntimeError, match='No free ports'):
        fm._next_free_port()


@pytest.mark.parametrize('platform,binary', [('Linux', None), ('Darwin', None)])
def test_missing_prerequisites_do_not_invoke_cli(monkeypatch, platform, binary):
    monkeypatch.setattr(fm.platform, 'system', lambda: platform)
    monkeypatch.setattr(fm, 'resolve_fm_bin', lambda: binary)
    diagnostic = Mock(side_effect=AssertionError('must not run'))
    monkeypatch.setattr(fm, '_diagnostic', diagnostic)
    probe = fm.describe_apple_fm_runtime_probe()
    assert probe['runtime_state'] == 'missing'
    assert fm.list_available_apple_fm_models()[0]['runnable'] is False
    diagnostic.assert_not_called()


def test_license_not_accepted_automatically(monkeypatch):
    monkeypatch.setattr(fm.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(fm, 'resolve_fm_bin', lambda: '/usr/bin/fm')
    diagnostic = Mock(return_value=(1, 'License not agreed'))
    monkeypatch.setattr(fm, '_diagnostic', diagnostic)
    assert fm.describe_apple_fm_runtime_probe()['runtime_state'] == 'degraded'
    diagnostic.assert_called_once_with('/usr/bin/fm', 'license', '--status')


def _prepare_start(monkeypatch):
    monkeypatch.setattr(fm, 'system_model_metadata', lambda: {})
    monkeypatch.setattr(fm, 'describe_apple_fm_runtime_probe', lambda: {
        'runtime_state': 'runnable', 'detection': {'binary': '/usr/bin/fm'}, 'issues': []})
    child = Mock(pid=321)
    child.poll.return_value = None
    monkeypatch.setattr(fm.subprocess, 'Popen', Mock(return_value=child))
    monkeypatch.setattr(fm, 'process_identity', lambda pid: 'birth /usr/bin/fm serve --host 127.0.0.1 --port 11601')
    monkeypatch.setattr(fm, 'owns_listener', lambda pid, port: True)
    monkeypatch.setattr(fm, 'server_metadata', lambda port: fm.transport_metadata())
    return child


def test_start_registers_distinct_instances_and_preserves_other_entries(registry, monkeypatch):
    registry.write_text('[{"instance_id":"unrelated","backend":"ollama","port":11435}]')
    child = _prepare_start(monkeypatch)
    one = fm.start_apple_fm_instance('system', start_source='api_start_model')
    child.pid = 322
    two = fm.start_apple_fm_instance('system', start_source='api_start_model')
    assert one['instance_id'] != two['instance_id']
    assert one['port'] != two['port']
    assert len(json.loads(registry.read_text())) == 3
    assert one['request_model'] == two['request_model'] == 'system'
    assert one['backend_metadata']['context_size'] is None
    assert one['backend_metadata']['model_variant'] is None
    assert one['supported_capabilities'] == ['chat', 'vision_analysis']
    assert one['features']['vision_input'] is True
    assert one['features']['audio_input'] is False
    assert one['features']['audio_output'] is False
    child.terminate.assert_not_called()


def test_start_retains_separate_host_default_observation(registry, monkeypatch):
    _prepare_start(monkeypatch)
    observed = {'source': 'FoundationModels.SystemLanguageModel.default',
                'scope': 'host_default_model', 'status': 'available',
                'model_variant': 'coreAdvanced3', 'context_size': 8192}
    monkeypatch.setattr(fm, 'system_model_metadata', lambda: observed)
    monkeypatch.setattr(fm, 'describe_apple_fm_runtime_probe', lambda: {
        'runtime_state': 'runnable', 'issues': [],
        'detection': {'binary': '/usr/bin/fm'}})
    instance = fm.start_apple_fm_instance('system', start_source='startup_policy')
    saved = json.loads(registry.read_text())[0]
    assert saved['backend_metadata']['system_model'] == observed
    assert instance['backend_metadata']['model_variant'] is None
    assert instance['backend_metadata']['context_size'] is None
    assert instance['request_model'] == 'system'


@pytest.mark.parametrize('failure', ['readiness', 'registry', 'early_exit'])
def test_failed_start_cleans_only_owned_child(registry, monkeypatch, failure):
    child = _prepare_start(monkeypatch)
    if failure == 'readiness':
        monkeypatch.setattr(fm, 'server_metadata', Mock(side_effect=RuntimeError('unavailable')))
    elif failure == 'registry':
        monkeypatch.setattr(fm, 'write_registry_entries', lambda *a, **kw: None)
    else:
        child.poll.return_value = 1
    with pytest.raises(RuntimeError):
        fm.start_apple_fm_instance('system', start_source='api_start_model')
    if failure != 'early_exit':
        child.terminate.assert_called_once()
        child.wait.assert_called()
    assert json.loads(registry.read_text()) == []
    assert fm._next_free_port() == fm.APPLE_FM_START_PORT


def test_stop_rejects_reused_pid(registry, monkeypatch):
    registry.write_text(json.dumps([{'instance_id':'afm-test','backend':'apple_fm','pid':321,
                                    'port':11601,'process_identity':'old'}]))
    monkeypatch.setattr(fm, 'pid_is_running', lambda pid: True)
    monkeypatch.setattr(fm, 'process_identity', lambda pid: 'different process')
    kill = Mock()
    monkeypatch.setattr(fm.os, 'kill', kill)
    with pytest.raises(RuntimeError, match='ownership'):
        fm.stop_apple_fm_instance('afm-test')
    kill.assert_not_called()
    assert len(json.loads(registry.read_text())) == 1


def test_missing_stop_never_touches_processes(registry, monkeypatch):
    kill = Mock()
    monkeypatch.setattr(fm.os, 'kill', kill)
    assert fm.stop_apple_fm_instance('missing') == (False, None)
    kill.assert_not_called()


def test_payload_uses_actual_limit_key_and_keeps_history():
    messages = [{'role':'system','content':'Rules'}, {'role':'user','content':'First'},
                {'role':'assistant','content':'Reply'}, {'role':'user','content':'Second'}]
    payload = apple_fm_chat_payload('system', messages, max_tokens=10, temperature=.4, top_p=.9)
    assert payload['messages'] == messages
    assert payload['max_completion_tokens'] == 10 and 'max_tokens' not in payload
    assert 'max_completion_tokens' not in apple_fm_chat_payload('system', messages)


@pytest.mark.parametrize('message', [
    {'role':'developer','content':'instructions'}, {'role':'tool','content':'result'},
    {'role':'user','content':[{'type':'image_url','image_url':'x'}]},
])
def test_unsupported_input_rejected(message):
    with pytest.raises(AppleFMTransportError):
        apple_fm_chat_payload('system', [message])


def _chunk(content=None, reason=None, **extra):
    choice = {'delta': {}}
    if content is not None:
        choice['delta']['content'] = content
    if reason is not None:
        choice['finish_reason'] = reason
    return 'data: ' + json.dumps({'model':'system','choices':[choice], **extra})


def _response(lines):
    response = Mock()
    response.iter_lines.return_value = iter(lines)
    return response


def test_stream_deltas_are_not_snapshots():
    response = _response([_chunk('Apple'), _chunk('Apple'), _chunk(reason='stop'), 'data: [DONE]'])
    assert ''.join(iter_apple_fm_stream_deltas(response)) == 'AppleApple'
    response.close.assert_called_once()


def test_stream_utf8_does_not_use_http_text_default_encoding():
    text = 'Zürich — grüezi'
    chunk = {'model': 'system', 'choices': [{'delta': {'content': text}}]}
    wire = '\n\n'.join(['data: ' + json.dumps(chunk, ensure_ascii=False),
                         _chunk(reason='stop'), 'data: [DONE]']) + '\n\n'
    response = requests.Response()
    response.status_code = 200
    response.encoding = 'ISO-8859-1'  # requests' default for text/* without charset.
    response.raw = HTTPResponse(body=io.BytesIO(wire.encode('utf-8')), preload_content=False)
    assert ''.join(iter_apple_fm_stream_deltas(response)) == text
    assert response.raw.closed


@pytest.mark.parametrize('tail', [[], ['data: [DONE]'], [_chunk(reason='stop')],
    ['data: {bad'], ['data: {"error":{"message":"guardrails triggered"}}'], [_chunk(reason='length')]])
def test_incomplete_or_failed_stream_cannot_complete(tail):
    response = _response([_chunk('partial'), *tail])
    with pytest.raises(AppleFMTransportError):
        list(iter_apple_fm_stream_deltas(response))
    response.close.assert_called_once()


def test_closing_iterator_closes_connection_without_claiming_inference_stopped():
    response = _response([_chunk('partial'), _chunk('more')])
    iterator = iter_apple_fm_stream_deltas(response)
    assert next(iterator) == 'partial'
    iterator.close()
    response.close.assert_called_once()
    assert fm.transport_metadata()['inference_cancellation'] == 'unverified'


def test_nonstream_completion_and_refusal():
    data = {'model':'system','choices':[{'finish_reason':'stop','message':{'content':'hello'}}]}
    assert validate_apple_fm_response(data) == 'hello'
    data['choices'][0]['message']['refusal'] = 'refused'
    with pytest.raises(AppleFMTransportError, match='refusal'):
        validate_apple_fm_response(data)


def test_server_metadata_does_not_attribute_unverified_framework_or_future_variant(monkeypatch):
    responses = [Mock(), Mock()]
    responses[0].json.return_value = {'models':[{'name':'system','available':True}]}
    responses[1].json.return_value = {'data':[{'id':'system','future_variant':'coreFuture9'}]}
    monkeypatch.setattr(fm.requests, 'get', Mock(side_effect=responses))
    metadata = fm.server_metadata(11601)
    assert metadata['model_variant'] is None and metadata['context_size'] is None
    assert metadata['reported_model']['future_variant'] == 'coreFuture9'
    assert metadata['observed_at'] and metadata['models_url'].endswith('11601/v1/models')
    monkeypatch.setattr('helpers.session_controls.available_apple_fm_image_tool_modes', lambda: [])
    fields = build_session_controls({'backend':'apple_fm','capability':'chat','model':'system'})['fields']
    assert set(fields) == {'temperature', 'top_p'}


def test_transport_owner_uses_exact_port_and_validates_completion():
    from fruth_server.backend_transport_runtime import BackendTransportRuntimeOwner
    response = Mock()
    response.json.return_value = {'model': 'system', 'choices': [
        {'finish_reason': 'stop', 'message': {'content': 'answer'}}]}
    post = Mock(return_value=response)
    owner = BackendTransportRuntimeOwner(
        hooks={'chat_timeout_seconds': lambda *args: 600,
               'normalize_chat_messages_for_backend': lambda messages, **kw: messages,
               'requests_post': post}, capability_chat='chat',
        request_timeout_error=TimeoutError, request_connection_error=ConnectionError,
        request_exception_error=Exception)
    assert owner.execute_chat_backend_request(target_port=11602, model_name='system',
        backend='apple_fm', capability='chat', messages=[{'role':'user','content':'hi'}]) == 'answer'
    assert post.call_args.args[0] == 'http://127.0.0.1:11602/v1/chat/completions'
    response.close.assert_called_once()
    response.json.return_value['choices'][0]['finish_reason'] = 'length'
    with pytest.raises(AppleFMTransportError):
        owner.execute_chat_backend_request(target_port=11602, model_name='system',
            backend='apple_fm', capability='chat', messages=[{'role':'user','content':'hi'}])


def test_api_missing_explicit_target_does_not_forward_to_supplied_port(monkeypatch):
    import fruth_webserver as web
    monkeypatch.setattr(web, 'load_running_instances', lambda: [])
    post = Mock(side_effect=AssertionError('must not forward missing target'))
    monkeypatch.setattr(web.requests, 'post', post)
    response = web.app.test_client().post('/api/chat', json={
        'instance_id':'apple_fm:system:11601', 'backend':'apple_fm',
        'model':'system', 'port':11602, 'messages':[{'role':'user','content':'hi'}]})
    assert response.status_code == 404
    post.assert_not_called()


@pytest.mark.parametrize('capability', ['text_to_speech', 'speech_to_text', 'image_generation'])
def test_infer_api_rejects_unsupported_capability_even_with_backend_override(monkeypatch, capability):
    import fruth_webserver as web
    monkeypatch.setattr(web, '_lookup_instance', lambda instance_id: {
        'instance_id': instance_id, 'backend':'apple_fm','model':'system','port':11601})
    post = Mock(side_effect=AssertionError('must not forward unsupported input'))
    monkeypatch.setattr(web.requests, 'post', post)
    response = web.app.test_client().post('/api/infer', json={
        'instance_id':'apple_fm:system:11601', 'backend':'ollama',
        'model':'other', 'capability':capability, 'prompt':'hi'})
    assert response.status_code == 400
    assert 'speech and image generation are unsupported' in response.json['error']
    post.assert_not_called()


def test_partial_afm_stream_stays_failed_in_canonical_responses(monkeypatch):
    import fruth_webserver as web
    from tests.fake_backends import FakeBackendHarness
    response = _response([_chunk('partial text'), 'data: {"error":{"message":"generation failed"}}'])
    response.fruth_stream_protocol = 'apple_fm'
    with FakeBackendHarness() as harness:
        monkeypatch.setattr(web, '_open_openai_chat_stream', lambda **kw: response)
        # Failure accounting checks listener state; this fixture has no real
        # server. Keep that observation deterministic and inside the I/O fence.
        monkeypatch.setattr('fruth_core.status._port_listening', lambda port: False)
        with web.app.test_request_context('/api/responses', method='POST'):
            stream = web._stream_chat_backend_as_responses(
                instance_id='apple_fm:system:11601', target_port=11601,
                model_name='system', backend='apple_fm', capability='chat',
                messages=[{'role':'user','content':'hello'}], response_id='resp_afm_partial')
            body = stream.get_data(as_text=True)
        assert 'event: response.output_text.delta' in body
        assert 'event: response.failed' in body
        assert 'event: response.completed' not in body
        truth = harness.client.get('/api/responses/resp_afm_partial?view=truth').json
        assert truth['lifecycle_state'] == 'failed'
        assert not any(o.get('status') == 'fulfilled' for o in truth.get('outputs', []))
        response.close.assert_called_once()


def test_image_payload_preserves_history_multiple_images_and_input_bytes():
    import copy
    one = 'data:image/png;base64,c291cmNlMQ=='
    two = 'data:image/jpeg;base64,c291cmNlMg=='
    messages = [{'role': 'system', 'content': 'Preserve the comparison order.'},
                {'role': 'user', 'content': [
                    {'type': 'input_text', 'text': 'Compare these.'},
                    {'type': 'input_image', 'image_url': one},
                    {'type': 'image_url', 'image_url': {'url': two}}]},
                {'role': 'assistant', 'content': 'Previous answer.'},
                {'role': 'user', 'content': 'Which is wider?'}]
    original = copy.deepcopy(messages)
    payload = apple_fm_chat_payload('system', messages, stream=True)
    assert messages == original
    assert payload['messages'][0] == messages[0]
    assert payload['messages'][2:] == messages[2:]
    assert payload['messages'][1]['content'] == [
        {'type': 'text', 'text': 'Compare these.'},
        {'type': 'image_url', 'image_url': {'url': one}},
        {'type': 'image_url', 'image_url': {'url': two}}]
    assert payload['stream'] is True


@pytest.mark.parametrize('content', [
    [], [{'type': 'text', 'text': 123}], [{'type': 'input_audio', 'input_audio': {'data': 'YQ=='}}],
    [{'type': 'unknown', 'text': 'Do not silently discard me.'}],
    [{'type': 'image_url', 'image_url': {'url': 'https://example.com/image.png'}}],
    [{'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,?'}}],
    [{'type': 'image_url', 'image_url': {'url': 'data:audio/wav;base64,YQ=='}}],
    ['not a content object'],
])
def test_bad_or_unsupported_multimodal_input_fails_before_dispatch(content):
    with pytest.raises(AppleFMTransportError):
        apple_fm_chat_payload('system', [{'role': 'user', 'content': content}])


@pytest.mark.parametrize('role', ['system', 'assistant'])
def test_image_roles_cannot_silently_lose_attachments(role):
    with pytest.raises(AppleFMTransportError, match='user message'):
        apple_fm_chat_payload('system', [{'role': role, 'content': [
            {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,YQ=='}}]}])


def test_catalog_exposes_vision_to_shared_capability_routing(monkeypatch):
    from helpers.model_capabilities import supports_capability
    monkeypatch.setattr(fm, 'system_model_metadata', lambda: {})
    monkeypatch.setattr(fm, 'describe_apple_fm_runtime_probe', lambda: {
        'runtime_state': 'runnable', 'issues': [], 'detection': {}})
    entry = fm.list_available_apple_fm_models()[0]
    assert entry['inputs'] == ['text', 'image']
    for capability in ('chat', 'vision_analysis'):
        assert supports_capability(capability, model_name='system', backend='apple_fm', metadata=entry)
    for capability in ('text_to_speech', 'speech_to_text', 'image_generation'):
        assert not supports_capability(capability, model_name='system', backend='apple_fm', metadata=entry)


@pytest.mark.parametrize('backend', ['apple_fm', 'llama_cpp'])
def test_pdf_pages_use_the_selected_backend_transport(backend, tmp_path):
    from types import SimpleNamespace
    from fruth_core.inference import _run_pdf_vision_analysis
    ctx = SimpleNamespace(model_name='system', prompt='Read this scan.', ocr_mode=None,
        backend=backend, port=11602, instance_id='test-vision', capability='vision_analysis',
        user_prompt='Read this scan.', pdf_page_timeout_sec=90, reasoning_effort=None)
    artifacts = SimpleNamespace(text_from_file='', pdf_page_images=['cGFnZTE=', 'cGFnZTI='],
        pdf_warnings=[], file_name='scan.pdf', file_sha256='source-sha', pdf_total_pages=2)
    completion = Mock(side_effect=[{'content': 'First page'}, {'content': 'Second page'}])
    wrong_backend = Mock(side_effect=AssertionError('must use selected backend'))
    ops = {'openai_chat_completions': completion, 'mlx_chat_completions': wrong_backend,
        'persist_text_markdown_locally': lambda *a, **kw: str(tmp_path/'scan.md'),
        'max_pdf_inline_response_chars': None, 'log_pdf_infer_event': Mock()}
    result, status = _run_pdf_vision_analysis(ctx, artifacts, ops)
    assert status == 200 and result['pdf_processed_pages'] == 2
    assert 'First page' in result['content'] and 'Second page' in result['content']
    assert [call.args[0] for call in completion.call_args_list] == [11602, 11602]
    assert [call.args[2][0]['content'][1]['image_url'] for call in completion.call_args_list] == [
        'data:image/png;base64,cGFnZTE=', 'data:image/png;base64,cGFnZTI=']
    wrong_backend.assert_not_called()
