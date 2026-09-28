"""Native image tool receipts and dispatch; no live models or production state."""
import base64
import copy
import hashlib
import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from fruth_core import apple_fm_tools as tools
from fruth_core.inference import InferArtifacts, InferContext, dispatch_infer_request
from fruth_services.responses import build_canonical_response_payload
from helpers.session_controls import build_session_controls

SOURCE = b'original-image-bytes'
ENCODED = base64.b64encode(SOURCE).decode()


def transcript(mode='apple_ocr', text='Zürich — Café'):
    name = tools.APPLE_FM_IMAGE_TOOL_MODES[mode][1]
    return {'modelName': 'system', 'transcript': {
        'version': '1.1', 'type': 'FoundationModels.Transcript', 'transcript': {'entries': [
            {'role': 'user', 'contents': [{'type': 'attachment', 'attachment': {
                'type': 'image', 'label': 'input',
                'data': 'data:image/jpeg;base64,' + base64.b64encode(b'reencoded-image').decode(),
            }}]},
            {'role': 'response', 'toolCalls': [{'name': name, 'id': 'call-1',
                'arguments': json.dumps({'image': {'attachmentLabel': 'input'}})}]},
            {'role': 'tool', 'toolName': name, 'toolCallID': 'call-1',
                'contents': [{'type': 'text', 'text': text}] if text else []},
            {'role': 'response', 'contents': [{'type': 'text', 'text': 'Wrong model-only answer'}],
                'metadata': {'assetIDs': ['reported-id']}},
        ]}}}


def parse(document, mode='apple_ocr'):
    return tools.parse_image_tool_transcript(document, mode=mode, source_bytes=SOURCE,
                                             instance_id='apple_fm:system:11602')


def context(mode='apple_ocr', backend='apple_fm', capability='chat'):
    return InferContext(instance_id='apple_fm:system:11602', backend=backend,
        capability=capability, model_name='system', port=11602, prompt='Read the image',
        user_prompt='Read the image', infer_timeout_sec=60, pdf_page_timeout_sec=60,
        pdf_max_image_side=1000, pdf_synthesize=False, ocr_mode=mode)


def test_receipt_uses_native_tool_text_and_distinct_source_attachment_digests():
    text, evidence = parse(transcript())
    assert text == 'Zürich — Café'
    assert evidence['result']['sha256'] == hashlib.sha256(text.encode()).hexdigest()
    assert evidence['source_image_sha256'] == hashlib.sha256(SOURCE).hexdigest()
    assert evidence['attachment_sha256'] == hashlib.sha256(b'reencoded-image').hexdigest()
    assert evidence['image_reencoded'] is True
    assert evidence['execution_scope'] == 'local_cli_session'
    assert evidence['reported_asset_ids'] == ['reported-id']
    assert 'model_variant' not in evidence


@pytest.mark.parametrize('mode', list(tools.APPLE_FM_IMAGE_TOOL_MODES))
def test_empty_recognition_requires_a_real_tool_result(mode):
    text, evidence = parse(transcript(mode, ''), mode)
    assert text == ''
    assert evidence['result']['empty'] is True


@pytest.mark.parametrize('fault', ['skipped', 'no_result', 'wrong_label', 'wrong_name',
    'wrong_call_id', 'duplicate_call', 'duplicate_result', 'extra_image', 'bad_attachment',
    'non_text_result', 'version', 'wrong_model', 'result_before_call', 'error'])
def test_unverified_execution_fails_closed(fault):
    document = transcript()
    entries = document['transcript']['transcript']['entries']
    if fault == 'skipped': del entries[1:3]
    elif fault == 'no_result': del entries[2]
    elif fault == 'wrong_label': entries[1]['toolCalls'][0]['arguments'] = '{"image":{"attachmentLabel":"other"}}'
    elif fault == 'wrong_name': entries[1]['toolCalls'][0]['name'] = 'readBarcodes'
    elif fault == 'wrong_call_id': entries[2]['toolCallID'] = 'other'
    elif fault == 'duplicate_call': entries.insert(2, copy.deepcopy(entries[1]))
    elif fault == 'duplicate_result': entries.insert(3, copy.deepcopy(entries[2]))
    elif fault == 'extra_image': entries.insert(0, copy.deepcopy(entries[0]))
    elif fault == 'bad_attachment': entries[0]['contents'][0]['attachment']['data'] = 'invalid base64'
    elif fault == 'non_text_result': entries[2]['contents'][0]['type'] = 'attachment'
    elif fault == 'version': document['transcript']['version'] = 'unknown'
    elif fault == 'wrong_model': document['modelName'] = 'other'
    elif fault == 'result_before_call': entries[1], entries[2] = entries[2], entries[1]
    elif fault == 'error': entries[-1]['error'] = 'provider failed'
    with pytest.raises(tools.AppleFMImageToolError, match='not verified'):
        parse(document)


def prepare_runner(monkeypatch):
    monkeypatch.setattr(tools, '_fm_binary', lambda: '/usr/bin/fm')
    monkeypatch.setattr(tools, 'available_apple_fm_image_tool_modes', lambda: ['apple_ocr', 'apple_barcode'])


def test_cli_owns_private_files_timeout_and_sanitized_environment(monkeypatch):
    prepare_runner(monkeypatch)
    monkeypatch.setenv('FRUTH_GRAPH_REBASE_OPERATOR_TOKEN', 'test-secret')
    paths = []
    def run(command, **kwargs):
        assert command[:6] == ['/usr/bin/fm', 'respond', '--model', 'system', '--tool', 'ocr']
        assert kwargs['timeout'] == 37
        assert kwargs['encoding'] == 'utf-8'
        assert kwargs['stdin'] == subprocess.DEVNULL
        assert 'FRUTH_GRAPH_REBASE_OPERATOR_TOKEN' not in kwargs['env']
        source = Path(command[command.index('--image') + 1])
        saved = Path(command[command.index('--save-transcript') + 1])
        paths.extend([source, saved])
        assert source.read_bytes() == SOURCE
        saved.write_text(json.dumps(transcript()), encoding='utf-8')
        return Mock(returncode=0)
    monkeypatch.setattr(tools.subprocess, 'run', run)
    text, _ = tools.run_apple_fm_image_tool(mode='apple_ocr', image_b64=ENCODED,
                                          instance_id='apple-2', timeout_sec=37)
    assert text == 'Zürich — Café'
    assert all(not p.exists() for p in paths)


@pytest.mark.parametrize('failure', ['exit', 'timeout', 'no_transcript', 'invalid_transcript'])
def test_failed_process_never_returns_model_prose_or_retries(monkeypatch, failure):
    prepare_runner(monkeypatch)
    paths = []
    def run(command, **kwargs):
        saved = Path(command[command.index('--save-transcript') + 1])
        paths.append(saved.parent)
        if failure == 'timeout': raise subprocess.TimeoutExpired(command, kwargs['timeout'])
        if failure == 'invalid_transcript': saved.write_text('{bad')
        return Mock(returncode=1 if failure == 'exit' else 0, stdout='Unverified answer')
    process = Mock(side_effect=run)
    monkeypatch.setattr(tools.subprocess, 'run', process)
    with pytest.raises(tools.AppleFMImageToolError):
        tools.run_apple_fm_image_tool(mode='apple_ocr', image_b64=ENCODED, instance_id='a', timeout_sec=1)
    assert process.call_count == 1
    assert all(not p.exists() for p in paths)


def test_capability_discovery_requires_flags_and_tools(monkeypatch):
    tools._probe_tools.cache_clear()
    run = Mock(return_value=Mock(returncode=0, stdout='--image X\n--label L\n--save-transcript P\n  --tool <name>\n    Possible values: barcode, ocr\n  --text <text>'))
    monkeypatch.setattr(tools.subprocess, 'run', run)
    assert tools._probe_tools('/test/fm', 1) == ('apple_ocr', 'apple_barcode')
    tools._probe_tools('/test/fm', 1)
    assert run.call_count == 1
    run.return_value.stdout = '--image --tool ocr'
    assert tools._probe_tools('/test/fm', 2) == ()
    tools._probe_tools.cache_clear()


@pytest.mark.parametrize('capability', ['chat', 'vision_analysis'])
def test_controls_discover_tools_for_both_apple_capabilities(monkeypatch, capability):
    monkeypatch.setattr('helpers.session_controls.available_apple_fm_image_tool_modes', lambda: ['apple_ocr', 'apple_barcode'])
    schema = build_session_controls({'backend': 'apple_fm', 'model': 'system', 'capability': capability})
    field = schema['fields']['ocr_mode']
    assert field['options'] == ['auto', 'apple_ocr', 'apple_barcode']
    assert field['option_labels']['apple_barcode'] == 'Read barcodes / QR codes'
    assert field['default_first_option'] is True
    assert 'ocr_mode' not in build_session_controls({'backend': 'ollama', 'model': 'system', 'capability': capability})['fields']


@pytest.mark.parametrize('capability', ['chat', 'vision_analysis'])
def test_tool_dispatch_and_canonical_receipt(monkeypatch, capability):
    tool = Mock(return_value=parse(transcript()))
    monkeypatch.setattr('fruth_core.inference.run_apple_fm_image_tool', tool)
    payload, code = dispatch_infer_request(context(capability=capability),
        InferArtifacts(file_kind='image', image_b64=ENCODED), {})
    assert code == 200
    assert payload['content'] == 'Zürich — Café'
    assert payload['vision_input_evidence']['transport'] == 'fm.respond'
    canonical = build_canonical_response_payload(source_payload=payload, instance_id='apple_fm:system:11602',
        model_name='system', backend='apple_fm', capability=capability,
        mode=payload['mode'], output_text=payload['content'])
    assert canonical['runtime']['apple_fm_image_tool_evidence'] == payload['apple_fm_image_tool_evidence']
    assert tool.call_args.kwargs['instance_id'] == 'apple_fm:system:11602'


@pytest.mark.parametrize('kind,backend,capability,mode', [
    ('pdf','apple_fm','vision_analysis','apple_ocr'),
    ('image','ollama','vision_analysis','apple_ocr'),
    ('image','apple_fm','text_to_speech','apple_ocr'),
    (None,'apple_fm','chat','apple_barcode'),
    ('image','apple_fm','chat','unknown'),
])
def test_invalid_tool_request_does_not_fall_back(kind, backend, capability, mode):
    payload, code = dispatch_infer_request(context(mode, backend, capability),
        InferArtifacts(file_kind=kind, image_b64=ENCODED if kind else None), {})
    assert code == 400
    assert payload.get('error')


def test_failed_tool_dispatch_is_visible(monkeypatch):
    monkeypatch.setattr('fruth_core.inference.run_apple_fm_image_tool',
        Mock(side_effect=tools.AppleFMImageToolError('tool skipped')))
    payload, code = dispatch_infer_request(context(), InferArtifacts(file_kind='image', image_b64=ENCODED), {})
    assert code == 502 and payload['error'] == 'tool skipped'
