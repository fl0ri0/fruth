"""Fake same-response audio traverses production binding owners, not predeclared evidence."""
import copy
import hashlib
import json
import shutil
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.fake_backends.self_attack import SelfAttackBackend
from fruth_services.artifact_contracts import bind_direct_audio_dependency
from fruth_services.tts_audio_integrity import build_tts_audio_integrity_evidence

SOURCE = 'The lighthouse is quiet.'


def test_fake_same_response_tts_stt_exercises_exact_source_binding(tmp_path):
    from scripts.fruth_self_attack import run_profile
    corpus = json.loads((Path(__file__).parents[1] / 'config/self_attack_corpus.json').read_text())
    corpus['cases'] = [c for c in corpus['cases'] if c['case_id'] == 'evidence-root']
    run = run_profile(corpus, {'id': 'baseline', 'request': {}, 'environment': {}, 'settings': {}},
                      tmp_path / 'sequence', mode='fake', base_url='http://invalid',
                      cycles=300, namespace='fake-audio-integration')
    case = run['cases'][0]
    assert not case['missing'], case
    assert not case['findings'], case
    assert 'exact_source_binding' in case['exercised']
    fills = case['payload']['late_fill']['fill_results']
    tts = next(x for x in fills if x['capability'] == 'text_to_speech')
    stt = next(x for x in fills if x['capability'] == 'speech_to_text')
    evidence = stt['tts_stt_semantic_evidence']
    assert evidence['status'] == 'matched'
    assert evidence['producer_phase_id'] == tts['phase_id']
    assert evidence['source_sha256'] == hashlib.sha256(SOURCE.encode()).hexdigest()
    assert stt['result_text'] == SOURCE
    binding = stt['audio_reference_input_evidence']
    assert binding['authority'] == 'canonical_direct_audio_dependency'
    assert binding['artifact_ref'] == tts['artifact_ref']
    assert binding['file_sha256'] == hashlib.sha256(Path(tts['saved_audio_path']).read_bytes()).hexdigest()
    assert binding['provider_input_sha256'] == binding['file_sha256']


@pytest.fixture
def prepared(tmp_path):
    import fruth_webserver as web
    with SelfAttackBackend(root=tmp_path / 'fake') as backend:
        raw, status = backend._invoke_internal_api_json_route(payload={
            'capability': 'text_to_speech', 'prompt': SOURCE})
        assert status == 200
        path = Path(raw['saved_audio_path'])
        raw['capability'] = 'text_to_speech'
        raw['tts_audio_integrity_evidence'] = build_tts_audio_integrity_evidence(path, SOURCE)
        owner = web._LATE_FILL_RUNTIME
        current = {'id': 'response-current', 'runtime': {}, 'artifacts': []}
        producer = owner.attach_late_fill_result_artifact_identity(
            {**raw, 'branch_id': 'tts-1', 'phase_id': 'phase-2', 'obligation_id': 'audio-1'},
            current, raw, capability='text_to_speech')
        current['late_fill'] = {'fill_results': [producer]}
        consumer = {'branch_id': 'stt-1', 'phase_id': 'phase-3', 'capability': 'speech_to_text',
                    'depends_on': ['phase-2'], 'input_refs': [
                        {'kind': 'phase_output', 'phase_id': 'phase-2', 'role': 'dependency'}]}
        inputs = owner.branch_dependency_payload(consumer, current_payload=current)
        payload = dict(inputs, capability='speech_to_text', prompt='Transcribe this audio.',
                       execution_contract=copy.deepcopy(consumer))
        binding = bind_direct_audio_dependency(current, consumer)
        assert binding is not None
        yield SimpleNamespace(**locals())


def invoke(h, binding=True):
    kwargs = {'direct_audio_dependency': h.binding} if binding else {}
    return h.backend._invoke_internal_api_json_route(payload=h.payload, **kwargs)


def test_fake_stt_decodes_verified_private_copy(prepared, monkeypatch):
    h = prepared
    original = h.backend._transcribe_audio
    read_paths = []

    def transcribe(path):
        read_paths.append(path)
        assert path != h.path
        assert path.read_bytes() == h.path.read_bytes()
        return original(path)

    monkeypatch.setattr(h.backend, '_transcribe_audio', transcribe)
    result, status = invoke(h)
    assert status == 200
    assert result['result']['transcript'] == SOURCE
    assert result['audio_reference_input_evidence']['source_response_id'] == h.current['id']
    assert len(read_paths) == 1
    assert h.backend.calls['speech_to_text'] == 1


@pytest.mark.parametrize('field,value', [
    ('artifact_ref', 'artifact:wrong'), ('artifact_id', 'wrong'),
    ('branch_id', 'wrong'), ('phase_id', 'wrong'), ('source_response_id', 'wrong'),
    ('path', '/nonexistent/audio.wav'), ('file_sha256', '0' * 64),
])
def test_fake_input_identity_tampering_rejected_before_stt(prepared, field, value):
    h = prepared
    for key in ('reference_artifacts', 'input_artifacts'):
        for ref in h.payload.get(key, []):
            ref[field] = value
            if field == 'artifact_ref':
                ref['ref'] = value
    result, status = invoke(h)
    assert status == 400, result
    assert h.backend.calls['speech_to_text'] == 0


@pytest.mark.parametrize('change', ['consumer', 'bytes', 'path_only', 'other_equal_audio', 'missing_dependency'])
def test_fake_stale_or_unbound_input_rejected(prepared, change):
    h = prepared
    if change == 'consumer':
        h.payload['execution_contract']['branch_id'] = 'other-consumer'
    elif change == 'bytes':
        h.path.write_bytes(h.path.read_bytes() + b'changed')
    elif change == 'path_only':
        h.payload.pop('reference_artifacts', None)
        h.payload.pop('input_artifacts', None)
    elif change == 'missing_dependency':
        h.payload['execution_contract']['depends_on'] = []
    else:
        other = h.path.with_name('same-bytes-other-artifact.wav')
        shutil.copyfile(h.path, other)
        h.payload['file_path'] = str(other)
        for key in ('reference_artifacts', 'input_artifacts'):
            for ref in h.payload.get(key, []):
                ref['path'] = str(other)
                ref['artifact_ref'] = ref['ref'] = 'artifact:other'
                ref['artifact_id'] = 'other'
    result, status = invoke(h)
    assert status == 400, result
    assert h.backend.calls['speech_to_text'] == 0


def test_fake_json_cannot_create_private_authority(prepared):
    h = prepared
    h.payload['direct_audio_dependency'] = asdict(h.binding)
    # At the fake replacement of the internal route, this remains untrusted data.
    result, status = invoke(h, binding=False)
    assert status == 400, result
    assert h.backend.calls['speech_to_text'] == 0


def test_fake_path_only_is_not_canonical_dependency_authority(prepared):
    h = prepared
    h.payload = {'capability': 'speech_to_text', 'file_path': str(h.path), 'prompt': 'Transcribe.'}
    result, status = invoke(h, binding=False)
    assert status == 200
    assert 'audio_reference_input_evidence' not in result


def test_fake_dependency_dict_is_not_private_object(prepared):
    h = prepared
    h.binding = asdict(h.binding)
    result, status = invoke(h)
    assert status == 400, result
    assert h.backend.calls['speech_to_text'] == 0


def test_fake_binding_never_copies_outside_isolated_artifacts(prepared, monkeypatch):
    h = prepared
    outside = h.backend.root / 'outside-artifacts.wav'
    outside.write_bytes(h.path.read_bytes())
    h.payload['file_path'] = str(outside)
    for key in ('reference_artifacts', 'input_artifacts'):
        for ref in h.payload.get(key, []):
            ref['path'] = str(outside)

    def no_copy(*args, **kwargs):
        pytest.fail('Disallowed source was copied before path authorization')

    monkeypatch.setattr('tests.fake_backends.harness.shutil.copyfile', no_copy)
    result, status = invoke(h)
    assert status == 400, result
    assert h.backend.calls['speech_to_text'] == 0
