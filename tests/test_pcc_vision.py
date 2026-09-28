"""PCC image boundaries, exact handoffs and ordinary vision dispatch; no real cloud calls."""
import base64
import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from fruth_integrations.shortcuts import pcc, server, transport
from fruth_runtime import apple_pcc_model_manager as manager
from fruth_core.inference import InferContext, InferArtifacts, dispatch_infer_request
from helpers.model_capabilities import supports_capability
from tests.fake_backends.fixtures import tiny_png_bytes


@pytest.fixture
def picture():
    data = tiny_png_bytes()
    return data, 'data:image/png;base64,' + base64.b64encode(data).decode()


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def test_ordered_image_parts_preserve_every_message_and_bind_exact_files(picture):
    data, url = picture
    messages = [{'role': 'system', 'content': 'Read visible content only.'},
                {'role': 'user', 'content': [{'type': 'text', 'text': 'First picture:'},
                    {'type': 'image_url', 'image_url': {'url': url}}]},
                {'role': 'assistant', 'content': 'Earlier answer'},
                {'role': 'user', 'content': [{'type': 'input_text', 'text': 'Compare this picture:'},
                    {'type': 'input_image', 'image_url': url}]}]
    original = json.dumps(messages)
    images = []
    prompt = server.prompt_from_messages(messages, image_inputs=images)
    decoded = json.loads(prompt.split('\n', 1)[1].removesuffix(server.PCC_MESSAGE_ENVELOPE_SUFFIX))['messages']
    assert decoded[0] == messages[0] and decoded[2] == messages[2]
    assert decoded[1]['content'][0]['text'] == 'First picture:'
    assert decoded[3]['content'][0]['text'] == 'Compare this picture:'
    for i, message in enumerate((decoded[1], decoded[3]), 1):
        assert message['content'][1] == {'type': 'input_image', 'attachment': f'image-{i:04d}.png',
                                       'sha256': hashlib.sha256(data).hexdigest()}
    assert images == [url, url] and url not in prompt
    assert json.dumps(messages) == original
    with pytest.raises(ValueError, match='attachment transport'):
        server.prompt_from_messages(messages)  # Cannot silently lose pixels via text-only API.


@pytest.mark.parametrize('role', ['system', 'assistant'])
def test_images_in_instruction_or_assistant_messages_are_rejected(role, picture):
    execute = Mock()
    with pytest.raises(ValueError):
        server.complete({'model': 'auto', 'messages': [{'role': role, 'content': [
            {'type': 'input_image', 'image_url': picture[1]}]}]}, execute=execute)
    execute.assert_not_called()


@pytest.mark.parametrize('url', ['https://example.com/private.png', 'file:///etc/passwd', '/tmp/a.png',
    'data:image/png;base64,a', 'data:image/png;base64,@@@', 'data:audio/wav;base64,YWJj', None])
def test_unsafe_or_malformed_image_transport_never_invokes_shortcuts(url, monkeypatch):
    command = Mock()
    monkeypatch.setattr(pcc, '_command', command)
    assert pcc.run_pcc_text('read', images=[url])['status'] == 'invalid_request'
    command.assert_not_called()
    execute = Mock()
    with pytest.raises(ValueError):
        server.complete({'model': 'auto', 'messages': [{'role': 'user', 'content': [
            {'type': 'image_url', 'image_url': url}]}]}, execute=execute)
    execute.assert_not_called()


def test_transport_budget_applies_before_cloud_discovery(picture, monkeypatch):
    command = Mock()
    monkeypatch.setattr(pcc, '_command', command)
    monkeypatch.setattr(pcc, 'PCC_MAX_REQUEST_BYTES', len(picture[1]))
    assert pcc.run_pcc_text('read', images=[picture[1]])['status'] == 'invalid_request'
    command.assert_not_called()


def test_multiframe_image_bytes_reach_shortcuts_unchanged(monkeypatch):
    encoded = ('R0lGODdhAgACAIEAAP8AAAAAAAAAAAAAACwAAAAAAgACAAAIBgABCAQQEAAh+QQBAAABACwAAAAA'
               'AgACAIEAAP8AAAAAAAAAAAAIBgABCAQQEAA7')
    calls = []
    def command(args, timeout_sec):
        if args == ['list']:
            return {'status': 'completed', 'stdout': 'Fruth PCC\n', 'stderr': ''}
        image = Path(args[args.index('--input-path') + 2])
        assert image.suffix == '.gif'
        assert image.read_bytes() == base64.b64decode(encoded)
        calls.append(image)
        Path(args[args.index('--output-path') + 1]).write_text('Native image result.')
        return {'status': 'completed'}
    monkeypatch.setattr(pcc, '_command', command)
    result = pcc.run_pcc_text('Describe.', model='cloud', images=['data:image/gif;base64,' + encoded])
    assert result['status'] == 'completed' and len(calls) == 1
    assert not calls[0].exists()


def test_native_image_rejection_stays_failure_without_fallback(monkeypatch):
    calls = []
    def command(args, timeout_sec):
        if args == ['list']:
            return {'status': 'completed', 'stdout': 'Fruth PCC\nFruth PCC Pro\n', 'stderr': ''}
        image = Path(args[args.index('--input-path') + 2])
        assert image.read_bytes() == b'abc'
        calls.append(image)
        return {'status': 'shortcut_error', 'stderr': 'Unable to read the image.'}
    monkeypatch.setattr(pcc, '_command', command)
    result = pcc.run_pcc_text('Describe.', images=['data:image/png;base64,YWJj'])
    assert result['status'] == 'shortcut_error' and len(calls) == 1
    assert result['stderr'] == 'Unable to read the image.' and 'output' not in result
    assert result['image_inputs'][0]['sha256'] == hashlib.sha256(b'abc').hexdigest()
    assert not calls[0].exists()


@pytest.mark.parametrize('fault', ['fallback', 'timeout', 'blocked'])
def test_private_image_staging_preserves_bytes_and_fallback_identity(picture, monkeypatch, fault):
    data, url = picture
    calls = []
    def command(args, timeout_sec):
        if args == ['list']:
            return {'status': 'completed', 'stdout': 'Fruth PCC\nFruth PCC Pro\n', 'stderr': ''}
        sources = [Path(p) for p in args[args.index('--input-path')+1:args.index('--output-path')]]
        target = Path(args[args.index('--output-path')+1])
        assert sources[0].read_text() == 'Describe only these pixels.'
        assert [p.read_bytes() for p in sources[1:]] == [data, data]
        assert sources[0].parent.stat().st_mode & 0o077 == 0
        assert not target.exists()
        calls.append(sources)
        if fault == 'timeout':
            return {'status': 'timeout'}
        if fault == 'blocked':
            target.write_text('BLOCKED: cannot inspect')
            return {'status': 'completed'}
        if args[1] == 'Fruth PCC Pro':
            target.write_text('must be discarded')
            return {'status': 'shortcut_error', 'stderr': 'Sign in with an iCloud+ account to use Cloud Pro.'}
        assert not calls[0][0].parent.exists()
        target.write_text('A green rectangle.')
        return {'status': 'completed'}
    monkeypatch.setattr(pcc, '_command', command)
    result = pcc.run_pcc_text('Describe only these pixels.', images=[url, url])
    assert all(not path.exists() for call in calls for path in call)
    if fault == 'fallback':
        assert result['status'] == 'completed' and len(calls) == 2
        assert result['model'] == 'cloud' and result['output'] == 'A green rectangle.'
        assert result['attempts'][0]['image_inputs'] == result['attempts'][1]['image_inputs'] == result['image_inputs']
    else:
        assert len(calls) == 1 and 'output' not in result and result['status'] == fault
    assert result['image_inputs'][0]['sha256'] == hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize('capability', ['vision_analysis', 'chat'])
def test_normal_vision_dispatch_uses_real_attachment_and_keeps_receipts(picture, capability):
    data, url = picture
    execute = Mock(return_value={'status': 'completed', 'model': 'cloud', 'output': 'A green rectangle.',
        'image_inputs': [{'attachment': 'image-0001.png', 'sha256': hashlib.sha256(data).hexdigest()}]})
    def complete(port, model, messages, **kwargs):
        assert messages[0]['content'][1]['image_url'] == url
        response, status = server.complete({'model': model, 'messages': messages}, execute=execute)
        assert status == 200
        return {'content': transport.validate_response(response), 'result': response}
    ctx = InferContext(instance_id='pcc', model_name='auto', backend='apple_pcc', capability=capability,
        port=11651, prompt='Describe.', user_prompt='Describe.', infer_timeout_sec=30,
        pdf_page_timeout_sec=30, pdf_max_image_side=1000, pdf_synthesize=False)
    payload, status = dispatch_infer_request(ctx, InferArtifacts(image_b64=url, file_kind='image'),
                                           {'openai_chat_completions': complete})
    assert status == 200 and payload['mode'] == ('vision_analysis' if capability == 'vision_analysis' else 'chat_with_image')
    assert payload['content'] == 'A green rectangle.'
    assert execute.call_args.kwargs['images'] == [url]
    if capability == 'vision_analysis':
        assert payload['vision_input_evidence']['image_sha256'] == hashlib.sha256(data).hexdigest()
    assert payload['pcc_execution']['image_inputs'][0]['sha256'] == hashlib.sha256(data).hexdigest()
    assert payload['pcc_execution']['message_transport'] == 'text_role_envelope_with_image_files'


@pytest.mark.parametrize('modalities', [None, ['text'], ['text', 'image']])
def test_live_adapter_metadata_does_not_upgrade_old_text_only_process(monkeypatch, modalities):
    health = {'backend': 'apple_pcc', 'transport_ready': True}
    if modalities is not None:
        health['input_modalities'] = modalities
    first, second = Mock(), Mock()
    first.json.return_value = health
    second.json.return_value = {'data': [{'id': 'auto', 'owned_by': 'apple_pcc'}]}
    monkeypatch.setattr(manager.requests, 'get', Mock(side_effect=[first, second]))
    assert manager.server_metadata(11651)['input_modalities'] == (modalities or ['text'])


def test_catalog_routes_vision_ocr_but_not_speech_or_native_scanner_tools(monkeypatch):
    monkeypatch.setattr(manager, 'describe_apple_pcc_runtime_probe', lambda **_: {'runtime_state':'runnable', 'issues':[]})
    monkeypatch.setattr(manager, 'pcc_sdk_metadata', lambda: {'status': 'unavailable'})
    entry = manager.list_available_apple_pcc_models()[0]
    assert supports_capability('vision_analysis', model_name='auto', backend='apple_pcc', metadata=entry)
    assert entry['supported_capabilities'] == ['chat', 'vision_analysis']
    assert not entry['features']['tool_calling'] and not entry['features']['audio_input']
    for capability in ('image_generation','text_to_speech','speech_to_text'):
        assert not supports_capability(capability, model_name='auto', backend='apple_pcc', metadata=entry)


@pytest.mark.parametrize('mime,suffix', [('image/png', '.png'), ('image/jpeg', '.jpg'),
    ('image/heic', '.heic'), ('image/unknown', '.bin')])
def test_declared_mime_names_files_without_inspecting_or_rewriting_bytes(mime, suffix):
    assert pcc.decode_image_input(f'data:{mime};base64,YWJj') == (b'abc', suffix)


def test_cli_attaches_only_the_explicit_image_files(picture, monkeypatch, tmp_path, capsys):
    data, _ = picture
    task = tmp_path / 'task.txt'; task.write_text('Read this image.')
    image = tmp_path / 'image.png'; image.write_bytes(data)
    run = Mock(return_value={'status': 'completed', 'output': 'done'})
    monkeypatch.setattr(pcc, 'run_pcc_text', run)
    assert pcc.main(['run','--input',str(task),'--image',str(image)]) == 0
    assert run.call_args.kwargs['images'][0].startswith('data:image/png;base64,')
    assert pcc.decode_image_input(run.call_args.kwargs['images'][0])[0] == data
    assert run.call_args.kwargs['model'] == 'auto'
