"""PDF preparation/dispatch with native rendering and deterministic providers."""

import base64
import hashlib
import io
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from fruth_core.transports import persist_input_file_locally
from tests.test_ocr_pdf import write_pdf


@pytest.fixture
def local_route(tmp_path, monkeypatch):
    if sys.platform != 'darwin':
        pytest.skip('Native PDF route requires macOS')
    # Also run API suites in a disposable physical checkout (TESTING_PROTOCOL).
    monkeypatch.chdir(tmp_path)
    import fruth_webserver as web

    monkeypatch.setitem(web.app.config, 'TESTING', True)
    monkeypatch.setattr(web, 'OCR_EXPORT_DIR', tmp_path / 'ocr')
    monkeypatch.setattr(web, 'ARTIFACT_REGISTRY_LEDGER', tmp_path / 'artifact_registry.jsonl')
    monkeypatch.setattr(web, 'RESPONSE_FRAMES_DIR', tmp_path / 'response_frames')
    monkeypatch.setattr(web, '_persist_input_file_locally', lambda path, **kw: persist_input_file_locally(
        path, output_root=tmp_path / 'inputs', **kw,
    ))
    monkeypatch.setattr(web, '_lookup_instance', Mock(return_value={
        'instance_id': 'pdf-test', 'model': 'vision-test', 'backend': 'ollama',
        'capability': 'vision_analysis', 'port': 11437,
    }))
    for name in ('record_instance_activity', 'record_instance_success', 'record_instance_failure'):
        monkeypatch.setattr(web, name, Mock(return_value=({}, {})))
    monkeypatch.setattr(web, '_log_unified_event', Mock())
    monkeypatch.setattr(web, '_append_infer_history', Mock())
    history = Mock(side_effect=AssertionError('New PDF requests must not reuse history'))
    monkeypatch.setattr(web, '_read_infer_history', history)
    ocr = Mock(side_effect=lambda **kw: (f'Contents from page {kw["page_index"]}', None))
    monkeypatch.setattr(web, '_ocr_pdf_page_with_ollama', ocr)
    monkeypatch.setattr(web, '_ollama_generate', Mock(return_value={'response': 'Image or text result'}))
    return web, ocr, history


@pytest.mark.parametrize('kind', ['scanned', 'mixed'])
@pytest.mark.parametrize('page_count', [1, 3])
def test_native_pages_reach_existing_ocr_with_original_source_identity(local_route, tmp_path, kind, page_count):
    web, ocr, _history = local_route
    path = write_pdf(tmp_path / 'document.pdf', rotations=(0, 90, 180)[:page_count], scanned=kind == 'scanned', mixed=kind == 'mixed')
    original = path.read_bytes()
    response = web.app.test_client().post('/api/infer', data={
        'instance_id': 'pdf-test', 'prompt': 'Read this document faithfully.',
        'file': (io.BytesIO(original), 'document.pdf'), 'pdf_max_pages': '2', 'pdf_dpi': '144',
    })
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['pdf_source'] == 'rendered_pages'
    expected_pages = min(2, page_count)
    assert payload['pdf_total_pages'] == page_count and payload['pdf_processed_pages'] == expected_pages
    assert [call.kwargs['page_index'] for call in ocr.call_args_list] == list(range(1, expected_pages + 1))
    assert all(call.kwargs['total_pages'] == page_count for call in ocr.call_args_list)
    assert all(call.kwargs['base_prompt'] == 'Read this document faithfully.' for call in ocr.call_args_list)
    assert all(base64.b64decode(call.kwargs['image_b64']).startswith(b'\x89PNG') for call in ocr.call_args_list)
    saved = Path(payload['saved_text_path'])
    assert saved.parent == tmp_path / 'ocr'
    assert saved.read_text().strip() == payload['content'].strip()
    assert all(f'[Page {page}]' in payload['content'] for page in range(1, expected_pages + 1))
    artifact = payload['input_artifacts'][0]
    assert Path(artifact['path']).read_bytes() == original
    assert web._append_infer_history.call_args.args[0]['file_sha256'] == hashlib.sha256(original).hexdigest()
    assert artifact['name'] == 'document.pdf'
    assert any('first 2' in warning for warning in payload['warnings']) is (page_count > 2)


def test_explicit_text_preference_keeps_mixed_coverage_visible(local_route, tmp_path):
    web, ocr, _history = local_route
    path = write_pdf(tmp_path / 'mixed.pdf', rotations=(0, 0), mixed=True)
    response = web.app.test_client().post('/api/infer', data={
        'instance_id': 'pdf-test', 'prompt': 'Read the searchable text.',
        'file': (io.BytesIO(path.read_bytes()), 'mixed.pdf'), 'pdf_prefer_text': 'true',
    })
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['pdf_source'] == 'text_layer'
    assert any('absent' in warning for warning in payload['warnings'])
    assert 'Page 1' in Path(payload['saved_source_text_path']).read_text()
    ocr.assert_not_called()


@pytest.mark.parametrize('controls', [{'pdf_max_pages': '1'}, {'pdf_dpi': '120'}, {'pdf_synthesize': 'false'}])
def test_explicit_pdf_controls_apply_to_new_execution(local_route, tmp_path, controls):
    web, ocr, history = local_route
    path = write_pdf(tmp_path / 'scan.pdf', rotations=(0, 0), scanned=True)
    response = web.app.test_client().post('/api/infer', data={
        'instance_id': 'pdf-test', 'prompt': 'Read this.',
        'file': (io.BytesIO(path.read_bytes()), 'scan.pdf'), **controls,
    })
    assert response.status_code == 200
    history.assert_not_called()
    assert ocr.call_count == (1 if 'pdf_max_pages' in controls else 2)


def test_single_image_bypasses_pdf_preparation(local_route, monkeypatch):
    web, _ocr, _history = local_route
    render = Mock(side_effect=AssertionError('Images must not enter PDF rendering'))
    monkeypatch.setattr(web, '_render_pdf_pages_to_base64', render)
    monkeypatch.setattr(web, '_extract_pdf_text_content', render)
    image = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aE1sAAAAASUVORK5CYII=')
    response = web.app.test_client().post('/api/infer', data={
        'instance_id': 'pdf-test', 'prompt': 'Describe this image.',
        'file': (io.BytesIO(image), 'image.png'),
    })
    assert response.status_code == 200
    render.assert_not_called()
    assert web._ollama_generate.call_args.kwargs['images'] == [base64.b64encode(image).decode('ascii')]


@pytest.mark.parametrize('reuse', [None, 'true', 'false'])
def test_repeated_incoming_pdf_uses_current_page_selection(local_route, tmp_path, reuse):
    web, ocr, history = local_route
    path = write_pdf(tmp_path / 'scan.pdf', rotations=(0, 0), scanned=True)
    for limit, expected in [('1', 1), ('', 2)]:
        ocr.reset_mock()
        response = web.app.test_client().post('/api/infer', data={
            'instance_id': 'pdf-test', 'prompt': 'Read this document.',
            'file': (io.BytesIO(path.read_bytes()), 'scan.pdf'),
            'pdf_max_pages': limit, **({'reuse_cached': reuse} if reuse else {}),
        })
        assert response.status_code == 200
        assert response.get_json()['pdf_total_pages'] == 2
        assert response.get_json()['pdf_processed_pages'] == expected
        assert ocr.call_count == expected
    history.assert_not_called()


def test_missing_renderer_fails_scanned_pdf_without_recognition(local_route, tmp_path, monkeypatch):
    web, ocr, _history = local_route
    path = write_pdf(tmp_path / 'scan.pdf', scanned=True)
    monkeypatch.setitem(sys.modules, 'Quartz', None)
    response = web.app.test_client().post('/api/infer', data={
        'instance_id': 'pdf-test', 'prompt': 'Read this.',
        'file': (io.BytesIO(path.read_bytes()), 'scan.pdf'),
    })
    assert response.status_code == 400
    assert 'requirements.txt' in response.get_json()['error']
    ocr.assert_not_called()


@pytest.fixture
def apple_pdf_route(local_route, monkeypatch):
    web, _ocr, _history = local_route
    web._lookup_instance.return_value = {
        'instance_id': 'pdf-test', 'model': 'system', 'request_model': 'system',
        'backend': 'apple_fm', 'capability': 'chat', 'port': 11602,
        'inputs': ['text', 'image'], 'outputs': ['text'],
        'features': {'vision_input': True},
    }
    completion = Mock(side_effect=lambda *a, **kw: {
        'content': f'Read page {completion.call_count}.',
    })
    monkeypatch.setattr(web, '_openai_chat_completions', completion)
    return web, completion


@pytest.mark.parametrize('endpoint', ['/api/infer', '/api/responses'])
@pytest.mark.parametrize('kind', ['scanned', 'mixed'])
@pytest.mark.parametrize('page_count', [1, 3])
def test_chat_pdf_uses_selected_vision_instance_for_every_selected_page(
    apple_pdf_route, tmp_path, endpoint, kind, page_count,
):
    web, completion = apple_pdf_route
    path = write_pdf(tmp_path / 'document.pdf', rotations=(0, 90, 180)[:page_count],
                     scanned=kind == 'scanned', mixed=kind == 'mixed')
    original = path.read_bytes()
    prompt = 'Transcribe every page, preserving the original language.'
    response = web.app.test_client().post(endpoint, data={
        'instance_id': 'pdf-test', 'capability': 'chat', 'prompt': prompt,
        'file': (io.BytesIO(original), 'document.pdf'), 'ocr_mode': 'auto',
        'pdf_max_pages': '2', 'pdf_dpi': '144', 'pdf_page_timeout_sec': '75',
    })
    payload = response.get_json()
    assert response.status_code == 200, payload
    expected = min(page_count, 2)
    assert payload['pdf_total_pages'] == page_count
    assert payload['pdf_processed_pages'] == expected
    assert any('first 2' in w for w in payload['warnings']) is (page_count > 2)
    assert completion.call_count == expected
    for index, call in enumerate(completion.call_args_list, start=1):
        assert call.args[:3] == ('apple_fm', 11602, 'system')
        parts = call.args[3][-1]['content']
        assert parts[0]['text'] == f'{prompt}\n\nPage {index} of {page_count}.'
        assert base64.b64decode(parts[1]['image_url'].split(',', 1)[1]).startswith(b'\x89PNG')
        assert call.kwargs['timeout_sec'] == 75
    if endpoint == '/api/infer':
        assert payload['capability'] == 'chat'
        assert payload['pdf_total_pages'] == page_count
        assert payload['pdf_processed_pages'] == expected
        assert payload['pdf_source'] == 'rendered_pages'
        assert any('first 2' in w for w in payload['warnings']) is (page_count > 2)
        source = payload['input_artifacts'][0]
        assert source['name'] == 'document.pdf'
        assert Path(source['path']).read_bytes() == original
        assert web._append_infer_history.call_args.args[0]['file_sha256'] == hashlib.sha256(original).hexdigest()
    else:
        assert payload['status'] == 'completed'
        assert f'[Page {expected}]' in payload['output_text']


@pytest.mark.parametrize('mode', ['apple_ocr', 'apple_barcode'])
def test_native_pdf_tools_receive_each_rendered_page_with_source_receipts(
    apple_pdf_route, tmp_path, monkeypatch, mode,
):
    web, completion = apple_pdf_route
    path = write_pdf(tmp_path / 'scan.pdf', rotations=(90, 0, 180), scanned=True)
    original = path.read_bytes()
    def recognize(**kwargs):
        raw = base64.b64decode(kwargs['image_b64'])
        assert raw.startswith(b'\x89PNG')
        assert kwargs['instance_id'] == 'pdf-test'
        assert kwargs['mode'] == mode
        assert kwargs['timeout_sec'] == 75
        return 'Exact detected text.', {
            'source_image_sha256': hashlib.sha256(raw).hexdigest(),
            'source_size_bytes': len(raw), 'attachment_sha256': 'a' * 64,
            'image_reencoded': True, 'result': {'empty': False},
        }
    tool = Mock(side_effect=recognize)
    monkeypatch.setattr('fruth_core.inference.run_apple_fm_image_tool', tool)
    response = web.app.test_client().post('/api/responses', data={
        'instance_id': 'pdf-test', 'capability': 'chat', 'ocr_mode': mode,
        'prompt': 'Read each page.', 'file': (io.BytesIO(original), 'scan.pdf'),
        'pdf_max_pages': '2', 'pdf_page_timeout_sec': '75',
    })
    payload = response.get_json()
    assert response.status_code == 200, payload
    assert tool.call_count == 2
    completion.assert_not_called()
    assert payload['output_text'] == '[Page 1]\nExact detected text.\n\n---\n\n[Page 2]\nExact detected text.'
    saved = web.app.test_client().get(f"/api/responses/{payload['id']}?view=truth").get_json()
    receipt = saved['runtime']['apple_fm_image_tool_evidence']
    assert receipt['kind'] == 'fruth.apple_fm_pdf_tool_evidence'
    assert receipt['source_pdf_sha256'] == hashlib.sha256(original).hexdigest()
    assert receipt['pdf_total_pages'] == 3
    assert [p['page_index'] for p in receipt['pages']] == [1, 2]
    assert all(p['evidence']['source_image_sha256'] for p in receipt['pages'])


@pytest.mark.parametrize('backend', ['apple_fm', 'mlx', 'llama_cpp', 'apple_pcc', 'ollama'])
def test_chat_pdf_uses_existing_image_capability_contract(apple_pdf_route, tmp_path, backend):
    web, completion = apple_pdf_route
    web._lookup_instance.return_value.update(backend=backend, model='multimodal-test')
    path = write_pdf(tmp_path / 'scan.pdf', rotations=(0, 90), scanned=True)
    response = web.app.test_client().post('/api/infer', data={
        'instance_id': 'pdf-test', 'prompt': 'Describe each page.',
        'phase_system_prompt': 'Keep the answer in the source language.',
        'file': (io.BytesIO(path.read_bytes()), 'scan.pdf'), 'pdf_page_timeout_sec': '75',
    })
    payload = response.get_json()
    assert response.status_code == 200, payload
    assert payload['capability'] == 'chat'
    assert payload['pdf_processed_pages'] == 2
    if backend == 'ollama':
        assert web._ocr_pdf_page_with_ollama.call_count == 2
        assert all(c.kwargs['port'] == 11602 for c in web._ocr_pdf_page_with_ollama.call_args_list)
        assert all(c.kwargs['base_prompt'] == 'Keep the answer in the source language.\n\nDescribe each page.'
                   for c in web._ocr_pdf_page_with_ollama.call_args_list)
        completion.assert_not_called()
    else:
        assert completion.call_count == 2
        for call in completion.call_args_list:
            assert call.args[:3] == (backend, 11602, 'auto' if backend == 'apple_pcc' else 'system')
            assert call.kwargs['timeout_sec'] == 75
            assert call.args[3][0] == {'role': 'system', 'content': 'Keep the answer in the source language.'}


@pytest.mark.parametrize('text_only', [False, True])
def test_chat_pdf_keeps_text_preference_and_text_only_targets(apple_pdf_route, tmp_path, monkeypatch, text_only):
    web, completion = apple_pdf_route
    if text_only:
        web._lookup_instance.return_value.update(
            backend='llama_cpp', model='text-test', inputs=['text'], features={'vision_input': False},
        )
    renderer = Mock(side_effect=AssertionError('Text-first PDF must not render when text exists'))
    monkeypatch.setattr(web, '_render_pdf_pages_to_base64', renderer)
    path = write_pdf(tmp_path / 'mixed.pdf', rotations=(0, 0), mixed=True)
    response = web.app.test_client().post('/api/infer', data={
        'instance_id': 'pdf-test', 'prompt': 'Summarize the searchable text.',
        'file': (io.BytesIO(path.read_bytes()), 'mixed.pdf'),
        **({} if text_only else {'pdf_prefer_text': 'true'}),
    })
    payload = response.get_json()
    assert response.status_code == 200, payload
    assert completion.call_count == 1
    assert isinstance(completion.call_args.args[3][-1]['content'], str)
    assert any('absent' in w for w in payload['warnings'])
    renderer.assert_not_called()


@pytest.mark.parametrize('all_empty', [False, True])
def test_empty_pdf_recognition_keeps_page_gaps_visible(apple_pdf_route, tmp_path, all_empty):
    web, completion = apple_pdf_route
    completion.side_effect = [{'content': text} for text in (
        ['', '', ''] if all_empty else ['First page.', '', 'Third page.']
    )]
    path = write_pdf(tmp_path / 'scan.pdf', rotations=(0, 90, 180), scanned=True)
    response = web.app.test_client().post('/api/infer', data={
        'instance_id': 'pdf-test', 'prompt': 'Read each page.',
        'file': (io.BytesIO(path.read_bytes()), 'scan.pdf'),
    })
    payload = response.get_json()
    assert response.status_code == (502 if all_empty else 200), payload
    assert completion.call_count == 3
    assert payload['pdf_total_pages'] == 3
    assert payload['pdf_processed_pages'] == (0 if all_empty else 2)
    assert any('Page 2:' in w for w in payload['warnings'])
    if not all_empty:
        assert '[Page 2]\n[No text returned' in payload['content']
        assert '[Page 3]\nThird page.' in payload['content']
        assert Path(payload['saved_text_path']).read_text().strip() == payload['content'].strip()


@pytest.mark.parametrize('mode,empty_text', [('apple_ocr', 'No text detected.'), ('apple_barcode', 'No barcodes detected.')])
def test_native_pdf_tools_render_text_layers_and_preserve_verified_empty_results(
    apple_pdf_route, tmp_path, monkeypatch, mode, empty_text,
):
    web, completion = apple_pdf_route
    tool = Mock(return_value=('', {'result': {'empty': True}}))
    monkeypatch.setattr('fruth_core.inference.run_apple_fm_image_tool', tool)
    path = write_pdf(tmp_path / 'text.pdf', rotations=(0, 90))
    response = web.app.test_client().post('/api/infer', data={
        'instance_id': 'pdf-test', 'ocr_mode': mode, 'pdf_prefer_text': 'true',
        'file': (io.BytesIO(path.read_bytes()), 'text.pdf'),
    })
    payload = response.get_json()
    assert response.status_code == 200, payload
    assert tool.call_count == payload['pdf_processed_pages'] == 2
    assert payload['content'] == f'[Page 1]\n{empty_text}\n\n---\n\n[Page 2]\n{empty_text}'
    assert all(p['evidence']['result']['empty'] for p in payload['apple_fm_image_tool_evidence']['pages'])
    completion.assert_not_called()


@pytest.mark.parametrize('invalid_input', [False, True])
@pytest.mark.parametrize('endpoint', ['/api/infer', '/api/responses'])
def test_native_pdf_tool_failure_retains_receipts_without_model_fallback(
    apple_pdf_route, tmp_path, monkeypatch, invalid_input, endpoint,
):
    from fruth_core.apple_fm_tools import AppleFMImageToolError
    web, completion = apple_pdf_route
    error_type = ValueError if invalid_input else AppleFMImageToolError
    tool = Mock(side_effect=[('First page.', {'result': {'empty': False}}), error_type('tool failed')])
    monkeypatch.setattr('fruth_core.inference.run_apple_fm_image_tool', tool)
    path = write_pdf(tmp_path / 'scan.pdf', rotations=(0, 0, 0), scanned=True)
    response = web.app.test_client().post(endpoint, data={
        'instance_id': 'pdf-test', 'ocr_mode': 'apple_ocr',
        'file': (io.BytesIO(path.read_bytes()), 'scan.pdf'),
    })
    payload = response.get_json()
    assert response.status_code == (400 if invalid_input else 502), payload
    if endpoint == '/api/responses':
        payload = web.app.test_client().get(f"/api/responses/{payload['id']}?view=truth").get_json()
        evidence = payload['runtime']['apple_fm_image_tool_evidence']
        assert 'PDF page 2: tool failed' in str(payload['error'])
    else:
        evidence = payload['apple_fm_image_tool_evidence']
        assert payload['error'] == 'PDF page 2: tool failed'
    assert payload['pdf_total_pages'] == 3 and payload['pdf_processed_pages'] == 1
    assert [p['page_index'] for p in evidence['pages']] == [1]
    assert tool.call_count == 2
    completion.assert_not_called()


def test_native_pdf_tool_cannot_replace_failed_rendering_with_text_extraction(
    apple_pdf_route, tmp_path, monkeypatch,
):
    web, completion = apple_pdf_route
    monkeypatch.setattr(web, '_render_pdf_pages_to_base64', Mock(return_value=([], 1, ['Rendering failed.'])))
    extract = Mock(side_effect=AssertionError('Native tools require pixels'))
    monkeypatch.setattr(web, '_extract_pdf_text_content', extract)
    tool = Mock(side_effect=AssertionError('No pages available'))
    monkeypatch.setattr('fruth_core.inference.run_apple_fm_image_tool', tool)
    path = write_pdf(tmp_path / 'text.pdf')
    response = web.app.test_client().post('/api/infer', data={
        'instance_id': 'pdf-test', 'ocr_mode': 'apple_ocr',
        'file': (io.BytesIO(path.read_bytes()), 'text.pdf'),
    })
    assert response.status_code == 400
    assert 'Rendering failed.' in response.get_json()['error']
    extract.assert_not_called()
    tool.assert_not_called()
    completion.assert_not_called()


def test_single_tab_pdf_sends_independent_page_images_without_frame_instructions(
    apple_pdf_route, tmp_path, monkeypatch,
):
    web, _completion = apple_pdf_route
    monkeypatch.setattr(web, '_openai_chat_completions', web._BACKEND_TRANSPORT_RUNTIME.openai_chat_completions)
    received = []
    responses = []

    def receive(url, *, json, timeout):
        index = len(received) + 1
        assert url == 'http://127.0.0.1:11602/v1/chat/completions'
        assert timeout == 75
        assert json['model'] == 'system' and json['stream'] is False
        assert len(json['messages']) == 1
        message = json['messages'][0]
        assert message['role'] == 'user'
        assert len(message['content']) == 2
        text, image = message['content']
        assert text == {'type': 'text', 'text': f'Read every page.\n\nPage {index} of 2.'}
        assert image['type'] == 'image_url'
        assert image['image_url']['url'].startswith('data:image/png;base64,')
        received.append(image['image_url']['url'])
        response = Mock()
        response.json.return_value = {'model': 'system', 'choices': [{
            'finish_reason': 'stop', 'message': {'content': f'Page result {index}.'},
        }]}
        responses.append(response)
        return response

    post = Mock(side_effect=receive)
    monkeypatch.setattr(web.requests, 'post', post)
    path = write_pdf(tmp_path / 'mixed.pdf', rotations=(0, 90), mixed=True)
    response = web.app.test_client().post('/api/responses', data={
        'instance_id': 'pdf-test', 'capability': 'chat', 'prompt': 'Read every page.',
        'ocr_mode': 'auto', 'file': (io.BytesIO(path.read_bytes()), 'mixed.pdf'),
        'pdf_page_timeout_sec': '75',
    })
    payload = response.get_json()
    assert response.status_code == 200, payload
    assert len(received) == 2 and received[0] != received[1]
    assert payload['output_text'] == '[Page 1]\nPage result 1.\n\n---\n\n[Page 2]\nPage result 2.'
    assert payload['status'] == 'completed' and payload['pdf_processed_pages'] == 2
    for page_response in responses:
        page_response.close.assert_called_once()


@pytest.mark.parametrize('endpoint', ['/api/infer', '/api/responses'])
@pytest.mark.parametrize('failure,status,failed_page', [
    ('guardrail', 502, 1), ('guardrail', 502, 2), ('refusal', 502, 2),
    ('timeout', 504, 2), ('connection', 503, 2),
])
def test_pdf_model_failure_keeps_page_coverage_and_stops_without_retry(
    apple_pdf_route, tmp_path, monkeypatch, endpoint, failure, status, failed_page,
):
    web, _completion = apple_pdf_route
    monkeypatch.setattr(web, '_openai_chat_completions', web._BACKEND_TRANSPORT_RUNTIME.openai_chat_completions)
    first = Mock()
    first.json.return_value = {'model': 'system', 'choices': [{
        'finish_reason': 'stop', 'message': {'content': 'First page result.'},
    }]}
    failed = Mock()
    expected_error = {
        'guardrail': "The model's safety guardrails were triggered.",
        'refusal': 'AFM refusal: The model refused this request.',
        'timeout': 'Timed out', 'connection': 'connection to the model instance was interrupted',
    }[failure]
    if failure == 'guardrail':
        failed.json.return_value = {'error': {'type': 'server_error', 'code': '500', 'message': expected_error}}
        failed.raise_for_status.side_effect = requests.HTTPError('HTTP 500', response=failed)
    elif failure == 'refusal':
        failed.json.return_value = {'model': 'system', 'choices': [{
            'finish_reason': 'stop', 'message': {'refusal': 'The model refused this request.'},
        }]}
    elif failure == 'timeout':
        failed = requests.Timeout('page deadline')
    else:
        failed = requests.ConnectionError('connection closed')
    post = Mock(side_effect=([first] if failed_page == 2 else []) + [failed])
    monkeypatch.setattr(web.requests, 'post', post)
    native = Mock(side_effect=AssertionError('Image analysis must not fall back to native OCR'))
    monkeypatch.setattr('fruth_core.inference.run_apple_fm_image_tool', native)
    path = write_pdf(tmp_path / 'mixed.pdf', rotations=(0, 90, 180), mixed=True)
    response = web.app.test_client().post(endpoint, data={
        'instance_id': 'pdf-test', 'capability': 'chat', 'prompt': 'Read every page.',
        'ocr_mode': 'auto', 'file': (io.BytesIO(path.read_bytes()), 'mixed.pdf'),
        'pdf_page_timeout_sec': '75',
    })
    payload = response.get_json()
    assert response.status_code == status, payload
    if endpoint == '/api/responses':
        payload = web.app.test_client().get(f"/api/responses/{payload['id']}?view=truth").get_json()
        assert payload['status'] == 'failed'
        assert not payload.get('output_text')
    assert f'PDF page {failed_page} of 3:' in str(payload['error'])
    assert expected_error in str(payload['error'])
    # Canonical failures retain the requested chat mode; Infer reports the PDF path.
    assert payload['mode'] == ('chat' if endpoint == '/api/responses' else 'vision_analysis_pdf_scan')
    assert payload['pdf_source'] == 'rendered_pages'
    assert payload['pdf_total_pages'] == 3 and payload['pdf_processed_pages'] == failed_page - 1
    assert post.call_count == failed_page
    assert all(c.args[0] == 'http://127.0.0.1:11602/v1/chat/completions' for c in post.call_args_list)
    assert all(c.kwargs['timeout'] == 75 for c in post.call_args_list)
    if failure in {'guardrail', 'refusal'}:
        failed.close.assert_called_once()
    native.assert_not_called()
    event = web._append_infer_history.call_args.args[0]
    assert event['status'] == 'error' and event['pdf_processed_pages'] == failed_page - 1
    assert event['file_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
