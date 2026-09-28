"""PCC instance transport/lifecycle with isolated state and no cloud requests."""
import json
import hashlib
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from fruth_integrations.shortcuts import server, transport
from fruth_runtime import apple_pcc_model_manager as pcc
from fruth_server.backend_transport_runtime import BackendTransportRuntimeOwner
from fruth_server.response_semantics_runtime import ResponseSemanticsRuntimeOwner
from fruth_core.inference import InferContext, InferArtifacts, dispatch_infer_request
from helpers.session_controls import build_session_controls


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pcc, '_shortcut_installation_observation', None)
    pcc.pcc_sdk_metadata.cache_clear()
    yield
    pcc.pcc_sdk_metadata.cache_clear()


def result(text='answer'):
    return {'status': 'completed', 'model': 'cloud', 'output': text, 'attempts': [], 'exit_code': 0}


def test_full_policy_and_order_cross_text_envelope_without_reduction():
    policy = (pcc.PROJECT_ROOT / 'FRUTH_INFERENCE.md').read_text()
    messages = [{'role': 'system', 'content': policy}, {'role': 'user', 'content': 'one'},
                {'role': 'assistant', 'content': 'two'}, {'role': 'user', 'content': 'three'}]
    prompt = server.prompt_from_messages(messages)
    assert json.loads(prompt.split('\n', 1)[1].removesuffix(server.PCC_MESSAGE_ENVELOPE_SUFFIX))['messages'] == messages
    execute = Mock(return_value=result())
    response, status = server.complete({'model': 'auto', 'messages': messages, 'fruth_timeout_sec': 19}, execute=execute)
    assert status == 200 and transport.validate_response(response) == 'answer'
    execute.assert_called_once_with(prompt, timeout_sec=19)
    assert response['pcc_execution']['message_transport'] == 'text_role_envelope'
    assert len(response['pcc_execution']['input_sha256']) == 64


@pytest.mark.parametrize('content,expected', [
    ('explain in high detail the process of osmosis', 'explain in high detail the process of osmosis'),
    ('  Zürich — write JSON: {"value": 100}\n', '  Zürich — write JSON: {"value": 100}\n'),
    ([{'type': 'input_text', 'text': 'First line.'}, {'type': 'text', 'text': 'Second line.'}],
     'First line.\nSecond line.'),
])
def test_single_direct_user_message_reaches_shortcuts_without_a_wrapper(content, expected):
    execute = Mock(return_value=result())
    response, status = server.complete({
        'model': 'auto', 'messages': [{'role': 'user', 'content': content}],
    }, execute=execute)
    assert status == 200
    execute.assert_called_once_with(expected, timeout_sec=120)
    assert response['pcc_execution']['message_transport'] == 'plain_user_text'
    assert response['pcc_execution']['input_sha256'] == hashlib.sha256(expected.encode()).hexdigest()


def test_single_user_inference_call_keeps_full_policy_in_role_envelope():
    owner = ResponseSemanticsRuntimeOwner({})
    messages = owner.inject_inference_runtime_policy_into_chat_messages(
        [{'role': 'user', 'content': 'Plan this work.'}], backend='apple_pcc',
        request_payload={'inference_route': True},
    )
    execute = Mock(return_value=result())
    response, status = server.complete({'model': 'auto', 'messages': messages}, execute=execute)
    assert status == 200
    prompt = execute.call_args.args[0]
    serialized = json.loads(prompt.split('\n', 1)[1].removesuffix(server.PCC_MESSAGE_ENVELOPE_SUFFIX))['messages']
    assert serialized == messages
    assert (pcc.PROJECT_ROOT / 'FRUTH_INFERENCE.md').read_text().strip() in serialized[0]['content']
    assert response['pcc_execution']['message_transport'] == 'text_role_envelope'


@pytest.mark.parametrize('inference_context', [
    {'request_payload': {'inference_route': True}},
    {'route_payload': {'route_source': 'inference_carried'}},
    {'route_payload': {'route_source': 'self_heal'}},
])
def test_direct_and_inference_calls_share_transport_without_role_leakage(inference_context):
    owner = ResponseSemanticsRuntimeOwner({})
    policy = (pcc.PROJECT_ROOT / 'FRUTH_INFERENCE.md').read_text().strip()
    role = "You implement Fruth's interpretive inference layer for this turn."
    messages = [{'role': 'system', 'content': 'Answer in German.'},
                {'role': 'user', 'content': 'What is 44 + 56?'}]
    execute = Mock(return_value=result('100'))
    for context, inference_owned in [({}, False), (inference_context, True),
                                      ({'request_payload': {'inference_route': False}}, False)]:
        prepared = owner.inject_inference_runtime_policy_into_chat_messages(
            messages, backend='apple_pcc', **context)
        response, status = server.complete({'model': 'auto', 'messages': prepared}, execute=execute)
        assert status == 200 and transport.validate_response(response) == '100'
        prompt = execute.call_args.args[0]
        serialized = json.loads(prompt.split('\n', 1)[1].removesuffix(server.PCC_MESSAGE_ENVELOPE_SUFFIX))['messages']
        assert serialized == prepared
        if inference_owned:
            assert policy in serialized[0]['content']
            assert serialized[0]['content'].count(role) == 1
            assert serialized[1:] == messages
        else:
            assert serialized == messages
            assert 'Fruth' not in prompt
    assert execute.call_count == 3
    assert messages == [{'role': 'system', 'content': 'Answer in German.'},
                        {'role': 'user', 'content': 'What is 44 + 56?'}]


@pytest.mark.parametrize('message', [
    {'role': 'tool', 'content': 'a'}, {'role': 'user', 'content': [{'type': 'input_image', 'image_url': 'data:x'}]},
    {'role': 'user', 'content': 'a', 'tool_calls': ['x']}, {'role': 'user', 'content': None}])
def test_bad_inputs_never_invoke_shortcut(message):
    execute = Mock()
    with pytest.raises(ValueError):
        server.complete({'model': 'auto', 'messages': [message]}, execute=execute)
    execute.assert_not_called()


@pytest.mark.parametrize('control', ['temperature', 'top_p', 'max_tokens', 'tools', 'reasoning_effort'])
def test_unsupported_wire_controls_fail(control):
    with pytest.raises(ValueError):
        server.complete({'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}], control: 1})


def test_provider_failures_carry_evidence_without_output():
    response, status = server.complete({'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}]},
        execute=Mock(return_value={'status': 'timeout', 'error': 'timed out', 'model': 'cloud-pro'}))
    assert status == 502 and 'choices' not in response
    assert response['pcc_execution']['status'] == 'timeout'


def sse_response(*, done=True, finish=True, identity_change=False):
    receipt = {'status': 'completed', 'model': 'cloud'}
    records = [json.dumps({'model': 'auto', 'choices': [{'delta': {'content': 'answer'}, 'finish_reason': None}],
                           'pcc_execution': receipt})]
    if finish:
        records.append(json.dumps({'model': 'auto', 'choices': [{'delta': {}, 'finish_reason': 'stop'}],
                                   'pcc_execution': dict(receipt, model='cloud-pro') if identity_change else receipt}))
    if done:
        records.append('[DONE]')
    response = Mock()
    response.iter_lines.return_value = [('data: ' + value).encode() for value in records]
    return response


def test_buffered_stream_retains_tier_and_requires_completion():
    response = sse_response()
    assert list(transport.stream_deltas(response)) == ['answer']
    assert response.fruth_pcc_execution['model'] == 'cloud'
    response.close.assert_called_once()


def test_stream_decodes_utf8_independently_of_http_default_encoding():
    response = sse_response()
    response.iter_lines.return_value[0] = response.iter_lines.return_value[0].replace(
        b'answer', 'Zürich — grüezi'.encode('utf-8'))
    assert list(transport.stream_deltas(response)) == ['Zürich — grüezi']
    response.iter_lines.assert_called_once_with(decode_unicode=False)


def test_catalog_discovers_newly_installed_shortcuts_without_server_restart(monkeypatch):
    listing = Mock(side_effect=[{'status': 'completed', 'models': []},
        {'status': 'completed', 'models': [{'installation': 'installed'}]}])
    monkeypatch.setattr(pcc, 'list_pcc_shortcuts', listing)
    monkeypatch.setattr(pcc, 'pcc_sdk_metadata', Mock(return_value={'status': 'unsupported_os'}))
    assert pcc.list_available_apple_pcc_models()[0]['runnable'] is False
    assert pcc.list_available_apple_pcc_models()[0]['runnable'] is True
    assert listing.call_count == 2


def test_passive_pcc_observation_never_discovers_on_a_cold_snapshot(monkeypatch):
    listing = Mock(side_effect=AssertionError('Passive status contacted Shortcuts'))
    monkeypatch.setattr(pcc, 'list_pcc_shortcuts', listing)
    for _ in range(3):
        snapshot = pcc.describe_apple_pcc_runtime_probe()
        assert snapshot['runtime_state'] == 'degraded'
        assert snapshot['detection']['status'] == 'not_observed'
        assert snapshot['detection']['observed_at'] is None
        assert snapshot['detection']['cached'] is True
        assert snapshot['operations']['start_instance'] is False
    listing.assert_not_called()


def test_passive_pcc_observation_retains_original_time_and_isolates_projection(monkeypatch):
    listing = Mock(return_value={'status': 'completed', 'models': [{'installation': 'installed'}]})
    monkeypatch.setattr(pcc, 'list_pcc_shortcuts', listing)
    monkeypatch.setattr(pcc, '_now', lambda: '2026-09-22T10:00:00+00:00')
    fresh = pcc.describe_apple_pcc_runtime_probe(refresh=True)
    assert fresh['detection']['cached'] is False
    fresh['detection']['models'][0]['installation'] = 'missing'
    monkeypatch.setattr(pcc, '_now', lambda: '2026-09-22T11:00:00+00:00')
    cached = pcc.describe_apple_pcc_runtime_probe()
    assert cached['runtime_state'] == 'runnable'
    assert cached['detection']['observed_at'] == '2026-09-22T10:00:00+00:00'
    assert cached['detection']['cached'] is True
    cached['detection']['models'].clear()
    assert pcc.describe_apple_pcc_runtime_probe()['runtime_state'] == 'runnable'
    listing.assert_called_once_with(timeout_sec=10)


def test_explicit_pcc_discovery_failure_replaces_cached_success(monkeypatch):
    listing = Mock(side_effect=[{'status': 'completed', 'models': [{'installation': 'installed'}]},
                                {'status': 'timeout', 'error': 'Shortcuts CLI timed out'}])
    monkeypatch.setattr(pcc, 'list_pcc_shortcuts', listing)
    assert pcc.describe_apple_pcc_runtime_probe(refresh=True)['runtime_state'] == 'runnable'
    assert pcc.describe_apple_pcc_runtime_probe(refresh=True)['runtime_state'] == 'missing'
    assert pcc.describe_apple_pcc_runtime_probe()['detection']['status'] == 'timeout'
    assert listing.call_count == 2


def test_explicit_pcc_start_rechecks_installation_instead_of_trusting_cache(monkeypatch):
    monkeypatch.setattr(pcc, '_shortcut_installation_observation', {
        'status': 'completed', 'observed_at': '2026-09-21T10:00:00+00:00',
        'models': [{'installation': 'installed'}]})
    listing = Mock(return_value={'status': 'completed', 'models': []})
    monkeypatch.setattr(pcc, 'list_pcc_shortcuts', listing)
    launch = Mock(side_effect=AssertionError('Must not start without an installed shortcut'))
    monkeypatch.setattr(pcc.subprocess, 'Popen', launch)
    with pytest.raises(RuntimeError, match='Install Fruth PCC'):
        pcc.start_apple_pcc_instance('auto', start_source='frontend_button')
    listing.assert_called_once_with(timeout_sec=10)
    launch.assert_not_called()


@pytest.mark.parametrize('kwargs', [{'done': False}, {'finish': False}, {'identity_change': True}])
def test_partial_stream_is_never_yielded(kwargs):
    response = sse_response(**kwargs)
    iterator = transport.stream_deltas(response)
    with pytest.raises(ValueError):
        next(iterator)
    response.close.assert_called_once()


def test_existing_transport_uses_pcc_adapter_and_keeps_full_messages():
    messages = [{'role': 'system', 'content': 'full policy'}, {'role': 'user', 'content': 'hello'}]
    data, _ = server.complete({'model': 'auto', 'messages': messages}, execute=Mock(return_value=result()))
    response = Mock()
    response.json.return_value = data
    post = Mock(return_value=response)
    owner = BackendTransportRuntimeOwner(hooks={'requests_post': post,
        'chat_timeout_seconds': lambda *_: 120, 'normalize_chat_messages_for_backend': lambda m, **_: m},
        capability_chat='chat', request_timeout_error=TimeoutError,
        request_connection_error=ConnectionError, request_exception_error=Exception)
    text = owner.execute_chat_backend_request(target_port=11651, model_name='auto', backend='apple_pcc',
        capability='chat', messages=messages, temperature=.2, max_tokens=200)
    assert text == 'answer' and text.pcc_execution['model'] == 'cloud'
    assert post.call_args.kwargs['json'] == {'model': 'auto', 'messages': messages,
        'stream': False, 'fruth_timeout_sec': 120}
    response.iter_lines.return_value = sse_response().iter_lines.return_value
    stream = owner.open_openai_chat_stream(backend='apple_pcc', target_port=11651,
        request_model_override='auto', model_name='auto', messages=messages, timeout_sec=80)
    assert list(owner.iter_openai_stream_deltas(stream)) == ['answer']


def test_pcc_keeps_unsupported_speech_capabilities_blocked():
    schema = build_session_controls({'backend': 'apple_pcc', 'capability': 'chat', 'model': 'auto'})
    assert schema['fields'] == {}
    ctx = InferContext(instance_id='pcc', model_name='auto', backend='apple_pcc', capability='speech_to_text',
        port=11651, prompt='hi', user_prompt='hi', infer_timeout_sec=30,
        pdf_page_timeout_sec=30, pdf_max_image_side=1000, pdf_synthesize=False)
    payload, status = dispatch_infer_request(ctx, InferArtifacts(image_b64='image'), {})
    assert status == 400 and 'speech and image generation are unsupported' in payload['error']


@pytest.mark.parametrize('payload,status', [
    ({'status': 'available', 'context_size': 32768}, 'available'),
    ({'status': 'available', 'context_size': 0}, 'probe_unavailable'),
    ({'status': 'available', 'context_size': '32768'}, 'probe_unavailable'),
    ({'status': 'unavailable', 'error': 'permission'}, 'unavailable'),
    ({'status': 'other'}, 'probe_unavailable'),
])
def test_native_metadata_is_separate_from_shortcuts_identity(monkeypatch, payload, status):
    monkeypatch.setattr(pcc.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(pcc.shutil, 'which', lambda _: '/usr/bin/xcrun')
    run = Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps(payload), ''))
    monkeypatch.setattr(pcc.subprocess, 'run', run)
    observation = pcc.pcc_sdk_metadata()
    assert observation['status'] == status
    assert observation['scope'] == 'sdk_default_not_shortcuts_tier'
    assert observation['model_variant'] is None
    assert pcc.transport_metadata()['context_size'] is None
    pcc.pcc_sdk_metadata()
    assert run.call_count == 1


def prepare_manager(monkeypatch):
    monkeypatch.setattr(pcc, 'describe_apple_pcc_runtime_probe', lambda **_: {'runtime_state': 'runnable', 'issues': []})
    monkeypatch.setattr(pcc, 'pcc_sdk_metadata', lambda: {'status': 'available', 'context_size': 32768})
    # Preserve fixture cleanup's cache API when stubbing the optional probe.
    pcc.pcc_sdk_metadata.cache_clear = lambda: None
    child = Mock(pid=2345)
    child.poll.return_value = None
    monkeypatch.setattr(pcc.subprocess, 'Popen', Mock(return_value=child))
    monkeypatch.setattr(pcc, 'process_identity', lambda _: 'birth ' + ' '.join(pcc._server_command(11651)))
    monkeypatch.setattr(pcc, 'owns_listener', lambda *_: True)
    monkeypatch.setattr(pcc, 'server_metadata', lambda _: pcc.transport_metadata())
    monkeypatch.setattr(pcc, '_next_free_port', lambda _: 11651)
    return child


def test_start_registry_and_owned_stop_preserve_other_instances(monkeypatch):
    Path('model_ports.json').write_text('[{"instance_id":"other","backend":"ollama","model":"gemma",'
                                       '"port":11435,"user_setting":"preserve"}]')
    child = prepare_manager(monkeypatch)
    instance = pcc.start_apple_pcc_instance('auto', start_source='frontend_button')
    assert instance['instance_id'] == 'apple_pcc:auto:11651'
    assert instance['supported_capabilities'] == ['chat', 'vision_analysis']
    assert instance['backend_metadata']['sdk_model']['context_size'] == 32768
    assert instance['backend_metadata']['context_size'] is None
    assert child.terminate.call_count == 0
    original = next(e for e in pcc.read_registry_entries('model_ports.json') if e['instance_id'] == 'other')
    assert original['user_setting'] == 'preserve' and original['port'] == 11435
    monkeypatch.setattr(pcc, 'pid_is_running', lambda _: False)
    assert pcc.stop_apple_pcc_instance(instance['instance_id'])[0]
    assert pcc.read_registry_entries('model_ports.json') == [original]


def test_stop_refuses_reused_pid(monkeypatch):
    Path('model_ports.json').write_text(json.dumps([{'instance_id': 'pcc', 'backend': 'apple_pcc',
        'pid': 3, 'port': 11651, 'process_identity': 'old', 'server_command': pcc._server_command(11651)}]))
    monkeypatch.setattr(pcc, 'pid_is_running', lambda _: True)
    monkeypatch.setattr(pcc, 'process_identity', lambda _: 'different')
    kill = Mock()
    monkeypatch.setattr(pcc.os, 'kill', kill)
    with pytest.raises(RuntimeError, match='ownership'):
        pcc.stop_apple_pcc_instance('pcc')
    kill.assert_not_called()


def test_stop_accepts_framework_python_identity_but_checks_birth_and_arguments(monkeypatch):
    identity = 'birth /Frameworks/Python.app/Contents/MacOS/Python -m fruth_integrations.shortcuts.server --port 11651'
    Path('model_ports.json').write_text(json.dumps([{'instance_id': 'pcc', 'backend': 'apple_pcc',
        'pid': 3, 'port': 11651, 'process_identity': identity, 'server_command': pcc._server_command(11651)}]))
    monkeypatch.setattr(pcc, 'pid_is_running', lambda _: True)
    monkeypatch.setattr(pcc, 'process_identity', Mock(side_effect=[identity, '', '']))
    kill = Mock()
    monkeypatch.setattr(pcc.os, 'kill', kill)
    assert pcc.stop_apple_pcc_instance('pcc')[0]
    kill.assert_called_once_with(3, 15)
    assert pcc.read_registry_entries('model_ports.json') == []


def test_failed_start_reaps_owned_child_and_does_not_publish(monkeypatch):
    child = prepare_manager(monkeypatch)
    child.poll.return_value = 1
    terminate = Mock()
    monkeypatch.setattr(pcc, '_terminate_child', terminate)
    with pytest.raises(RuntimeError, match='failed to start'):
        pcc.start_apple_pcc_instance('auto', start_source='api_start_model')
    terminate.assert_called_once_with(child)
    assert pcc.read_registry_entries('model_ports.json') == []


def test_pcc_ports_do_not_overlap_local_afm_and_reject_reserved_ports(monkeypatch):
    from fruth_runtime import ollama_model_manager
    monkeypatch.setattr(ollama_model_manager, 'is_port_listening', lambda _: False)
    monkeypatch.setattr(pcc, 'is_port_listening', lambda _: False)
    assert pcc.APPLE_PCC_START_PORT == pcc.APPLE_FM_PORT_MAX + 1
    assert pcc.APPLE_PCC_PORT_MAX - pcc.APPLE_PCC_START_PORT + 1 == 50
    with pytest.raises(ValueError):
        pcc._next_free_port(pcc.APPLE_PCC_START_PORT - 1)
    with pytest.raises(ValueError):
        pcc._next_free_port(pcc.APPLE_PCC_PORT_MAX + 1)
    Path('model_ports.json').write_text(json.dumps([{'port': pcc.APPLE_PCC_START_PORT}]))
    assert pcc._next_free_port() == pcc.APPLE_PCC_START_PORT + 1
    with pytest.raises(RuntimeError, match='occupied or reserved'):
        pcc._next_free_port(pcc.APPLE_PCC_START_PORT)


def test_catalog_keeps_sdk_context_separate_and_controls_truthful(monkeypatch):
    prepare_manager(monkeypatch)
    entry = pcc.list_available_apple_pcc_models()[0]
    assert entry['backend'] == 'apple_pcc' and entry['name'] == 'auto'
    assert entry['display_name'] == 'Apple PCC' and entry['removable'] is False
    assert '32,768' in entry['description'] and 'Shortcuts limit unreported' in entry['description']
    assert entry['features']['vision_input'] is True


def test_existing_preferred_ii_resolver_selects_pcc_without_provider_special_case():
    from fruth_server.inference_route_runtime import InferenceRouteRuntimeOwner
    from helpers.model_capabilities import supports_capability
    owner = InferenceRouteRuntimeOwner(hooks={'instance_supports_capability':
        lambda instance, capability: supports_capability(capability,
            model_name=instance['model'], backend=instance['backend'],
            capability=instance['capability'], metadata=instance)},
        wrapper_capability_aliases={}, max_recent_messages=8)
    candidates = [{'instance_id': 'local', 'model': 'gemma', 'backend': 'ollama', 'capability': 'chat'},
                  {'instance_id': 'apple_pcc:auto:11651', 'model': 'auto', 'backend': 'apple_pcc', 'capability': 'chat'}]
    context = {'runtime': {'inference_preferences': {'primary_mode': 'prefer',
                'primary_target': {'model': 'auto', 'backend': 'apple_pcc', 'capability': 'chat'}}}}
    selected, evidence = owner.pick_inference_preference_instance(candidates, context, requested_capability='chat')
    assert selected == 'apple_pcc:auto:11651' and evidence['applied'] == 'primary_target'
    selected, _ = owner.pick_inference_preference_instance(candidates, context, requested_capability='image_generation')
    assert selected is None
