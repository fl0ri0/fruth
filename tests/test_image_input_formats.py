"""Image upload bytes and media types at the selected backend boundary."""

import base64
import hashlib
import io
from pathlib import Path
from unittest.mock import Mock

import pytest

from fruth_core.inference import _build_mlx_multimodal_user_message
from fruth_core.transports import apple_fm_chat_payload, persist_input_file_locally


# One-pixel fixtures; no image codec or model is needed to run these tests.
PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC'
)
JPEG = base64.b64decode(
    '/9j/4AAQSkZJRgABAQAASABIAAD/4QBMRXhpZgAATU0AKgAAAAgAAYdpAAQAAAABAAAAGgAAAAAAA6ABAAMAAAAB'
    'AAEAAKACAAQAAAABAAAAAaADAAQAAAABAAAAAQAAAAD/7QA4UGhvdG9zaG9wIDMuMAA4QklNBAQAAAAAAAA4QklN'
    'BCUAAAAAABDUHYzZjwCyBOmACZjs+EJ+/8AAEQgAAQABAwEiAAIRAQMRAf/EAB8AAAEFAQEBAQEBAAAAAAAAAAAB'
    'AgMEBQYHCAkKC//EALUQAAIBAwMCBAMFBQQEAAABfQECAwAEEQUSITFBBhNRYQcicRQygZGhCCNCscEVUtHwJDNic'
    'oIJChYXGBkaJSYnKCkqNDU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6g4SFhoeIiYqSk5SV'
    'lpeYmZqio6Slpqeoqaqys7S1tre4ubrCw8TFxsfIycrS09TV1tfY2drh4uPk5ebn6Onq8fLz9PX29/j5+v/EAB8B'
    'AAMBAQEBAQEBAQEAAAAAAAABAgMEBQYHCAkKC//EALURAAIBAgQEAwQHBQQEAAECdwABAgMRBAUhMQYSQVEHYXET'
    'IjKBCBRCkaGxwQkjM1LwFWJy0QoWJDThJfEXGBkaJicoKSo1Njc4OTpDREVGR0hJSlNUVVZXWFlaY2RlZmdoaWpzd'
    'HV2d3h5eoKDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uLj5OXm'
    '5+jp6vLz9PX29/j5+v/bAEMAAgICAgICAwICAwUDAwMFBgUFBQUGCAYGBgYGCAoICAgICAgKCgoKCgoKCgwMDAwM'
    'DA4ODg4ODw8PDw8PDw8PD//bAEMBAgICBAQEBwQEBxALCQsQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQ'
    'EBAQEBAQEBAQEBAQEBAQEBAQEBAQEP/dAAQAAf/aAAwDAQACEQMRAD8A+L6KKK/lM/38P//Z'
)


@pytest.mark.parametrize(('raw', 'mime'), [
    (JPEG, 'image/jpeg'), (PNG, 'image/png'),
    (b'GIF87a' + bytes(10), 'image/gif'),
    (b'GIF89a' + bytes(10), 'image/gif'),
    (b'RIFF' + bytes(4) + b'WEBP' + bytes(8), 'image/webp'),
    (b'BM' + bytes(16), 'image/bmp'),
    (b'II*\x00' + bytes(12), 'image/tiff'),
    (b'MM\x00*' + bytes(12), 'image/tiff'),
], ids=['jpeg', 'png', 'gif87', 'gif89', 'webp', 'bmp', 'tiff-little', 'tiff-big'])
def test_raw_image_format_reaches_apple_transport_without_reencoding(raw, mime):
    encoded = base64.b64encode(raw).decode('ascii')
    message = _build_mlx_multimodal_user_message('Read the text.', encoded)
    payload = apple_fm_chat_payload('system', [message])
    parts = payload['messages'][0]['content']
    assert parts[0] == {'type': 'text', 'text': 'Read the text.'}
    assert parts[1]['image_url']['url'] == f'data:{mime};base64,{encoded}'


def test_explicit_image_data_url_is_preserved():
    url = 'data:image/jpeg;base64,' + base64.b64encode(JPEG).decode('ascii')
    message = _build_mlx_multimodal_user_message('Describe it.', url)
    assert message['content'][1]['image_url'] == url


@pytest.fixture
def image_route(tmp_path, monkeypatch):
    # Run API checks in a disposable physical checkout as well as temporary roots.
    monkeypatch.chdir(tmp_path)
    import fruth_webserver as web

    monkeypatch.setitem(web.app.config, 'TESTING', True)
    monkeypatch.setattr(web, 'ARTIFACT_REGISTRY_LEDGER', tmp_path / 'artifact_registry.jsonl')
    monkeypatch.setattr(web, 'RESPONSE_FRAMES_DIR', tmp_path / 'response_frames')
    monkeypatch.setattr(web, '_persist_input_file_locally', lambda path, **kw: persist_input_file_locally(
        path, output_root=tmp_path / 'inputs', **kw,
    ))
    monkeypatch.setattr(web, '_lookup_instance', Mock(return_value={
        'instance_id': 'image-test', 'model': 'system', 'backend': 'apple_fm',
        'capability': 'chat', 'port': 11602, 'inputs': ['text', 'image'],
        'supported_capabilities': ['chat', 'vision_analysis'],
        'features': {'vision_input': True},
    }))
    for name in ('record_instance_activity', 'record_instance_success', 'record_instance_failure'):
        monkeypatch.setattr(web, name, Mock(return_value=({}, {})))
    monkeypatch.setattr(web, '_log_unified_event', Mock())
    monkeypatch.setattr(web, '_append_infer_history', Mock())
    deny = Mock(side_effect=AssertionError('Image uploads must not render or extract PDFs'))
    monkeypatch.setattr(web, '_render_pdf_pages_to_base64', deny)
    monkeypatch.setattr(web, '_extract_pdf_text_content', deny)
    completion = Mock(return_value={'content': 'Detected text.'})
    monkeypatch.setattr(web, '_openai_chat_completions', completion)
    return web, completion


@pytest.mark.parametrize('capability', ['chat', 'vision_analysis'])
@pytest.mark.parametrize(('raw', 'name', 'mime'), [
    (JPEG, 'photo.jpg', 'image/jpeg'),
    (JPEG, 'photo.JPEG', 'image/jpeg'),
    (JPEG, 'misnamed.png', 'image/jpeg'),
    (PNG, 'page.png', 'image/png'),
], ids=['jpg', 'uppercase-jpeg', 'misnamed-jpeg', 'png'])
def test_uploaded_image_preserves_prompt_target_format_and_artifact(
    image_route, capability, raw, name, mime,
):
    web, completion = image_route
    prompt = "What's the text in this image?"
    response = web.app.test_client().post('/api/infer', data={
        'instance_id': 'image-test', 'capability': capability,
        'prompt': prompt, 'ocr_mode': 'auto', 'file': (io.BytesIO(raw), name),
    })
    assert response.status_code == 200, response.get_json()
    completion.assert_called_once()
    call = completion.call_args
    assert call.args[:3] == ('apple_fm', 11602, 'system')
    wire = apple_fm_chat_payload('system', call.args[3])
    parts = wire['messages'][-1]['content']
    assert parts[0]['text'] == prompt
    url = parts[1]['image_url']['url']
    assert url.startswith(f'data:{mime};base64,')
    assert base64.b64decode(url.split(',', 1)[1]) == raw
    artifact = response.get_json()['input_artifacts'][0]
    assert artifact['name'] == name
    saved_bytes = Path(artifact['path']).read_bytes()
    assert saved_bytes == raw
    if capability == 'vision_analysis':
        evidence = response.get_json()['vision_input_evidence']
        assert evidence['image_sha256'] == hashlib.sha256(saved_bytes).hexdigest()
