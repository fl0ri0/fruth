"""Exercise canonical producer -> dependency -> infer, before Registry publication."""
import copy
import hashlib
import math
import json
import shutil
import struct
import wave
from types import SimpleNamespace

import pytest

from fruth_services.tts_audio_integrity import build_tts_audio_integrity_evidence


@pytest.fixture
def handoff(tmp_path, monkeypatch):
    import fruth_webserver as web
    root = tmp_path.resolve()
    path = root / 'first.wav'
    with wave.open(str(path), 'wb') as wav:
        wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        wav.writeframes(b''.join(struct.pack('<h', int(9000 * math.sin(i / 12))) for i in range(48000)))
    raw = {'saved_audio_path': str(path), 'capability': 'text_to_speech',
           'tts_audio_integrity_evidence': build_tts_audio_integrity_evidence(path, 'The lighthouse is quiet.')}
    current = {'id': 'response-current', 'runtime': {}, 'artifacts': []}
    owner = web._LATE_FILL_RUNTIME
    producer = owner.attach_late_fill_result_artifact_identity(
        {**raw, 'branch_id': 'tts-1', 'phase_id': 'phase-2', 'obligation_id': 'audio-1'},
        current, raw, capability='text_to_speech')
    current['late_fill'] = {'fill_results': [producer]}
    consumer = {'branch_id': 'stt-1', 'phase_id': 'phase-3', 'capability': 'speech_to_text',
                'depends_on': ['phase-2'], 'input_refs': [{'kind': 'phase_output', 'phase_id': 'phase-2', 'role': 'dependency'}]}
    instance = {'instance_id': 'whisper-fixture', 'port': 11504, 'model': 'whisper',
                'backend': 'mlx', 'capability': 'speech_to_text'}
    ledger = root / 'registry.jsonl'
    monkeypatch.setattr(web, 'ARTIFACT_REGISTRY_LEDGER', ledger)
    monkeypatch.setattr(web, '_get_response_lookup_record', lambda _: {})
    monkeypatch.setattr(web, '_resolve_saved_downloadable_artifact_path',
                        lambda p: web._resolve_saved_artifact_path(p, allowed_roots={root}))
    monkeypatch.setattr(web, '_lookup_instance', lambda _: instance)
    for name in ('record_instance_activity', 'record_instance_success', 'record_instance_failure'):
        monkeypatch.setattr(web, name, lambda *a, **kw: ({}, {}))
    monkeypatch.setattr(web, '_persist_transcript_text_locally', lambda *a, **kw: str(root / 'transcript.txt'))
    calls = []
    monkeypatch.setattr(web, '_whisper_transcribe', lambda port, p, **kw:
                        calls.append(hashlib.sha256(p.read_bytes()).hexdigest()) or {'text': 'The lighthouse is quiet.'})
    monkeypatch.setattr(owner, 'prepare_effective_request_data', lambda data, **kw:
                        (dict(data), kw['route_info'], {}, {}))
    monkeypatch.setattr(owner, 'build_missing_required_session_controls', lambda *a: [])

    def prepare():
        dependency = owner.branch_dependency_payload(consumer, current_payload=current)
        request = {**dependency, 'instance_id': instance['instance_id'], 'prompt': 'Transcribe the generated audio.',
                   'execution_contract': copy.deepcopy(consumer)}
        with web.app.test_request_context('/api/responses', method='POST'):
            infer, _, _, _ = web._INFER_RUNTIME.build_responses_infer_execution_payload(
                request, route_info=None, instance=instance, instance_id=instance['instance_id'],
                backend='mlx', capability='speech_to_text', request_model_override=None)
        return dependency, infer

    def plan():
        dependency, _ = prepare()
        return owner.prepare_late_fill_branch_plan(
            expected_capability='speech_to_text', artifact_gap=copy.deepcopy(consumer),
            current_payload=current, request_payload={}, assistant_message='',
            source_route_payload=None, failed_instance_id=None,
            build_deferred_follow_up_gap_for_capability=lambda gap, **kw: dict(gap),
            prepare_late_fill_request_payload=lambda *a, **kw: {
                **dependency, 'prompt': 'Transcribe the generated audio.',
                'instance_id': instance['instance_id'], 'execution_contract': copy.deepcopy(consumer)},
            resolve_late_fill_route=lambda data, **kw: (dict(data),
                {'instance_id': instance['instance_id'], 'capability': 'speech_to_text',
                 'backend': 'mlx', 'instance': instance}, None))

    return SimpleNamespace(**locals())


def test_producer_identity_survives_real_dependency_preparation(handoff):
    h = handoff
    dependency, infer = h.prepare()
    expected = h.producer['artifact_ref']
    assert dependency['reference_artifacts'][0].get('artifact_ref') == expected
    assert infer['reference_artifacts'][0].get('artifact_ref') == expected
    assert infer['file_path'] == str(h.path)


def test_first_attempt_reaches_whisper_before_publication(handoff):
    h = handoff
    plan = h.plan()
    assert not h.ledger.exists()
    result = h.owner.execute_prepared_late_fill_branch(plan)
    assert h.calls == [hashlib.sha256(h.path.read_bytes()).hexdigest()]
    evidence = result['infer_result']['audio_reference_input_evidence']
    assert evidence['artifact_ref'] == h.producer['artifact_ref']
    assert evidence['authority'] == 'canonical_direct_audio_dependency'
    assert not h.ledger.exists()


@pytest.mark.parametrize('key,value', [
    ('artifact_id', 'foreign'), ('artifact_ref', 'artifact:foreign'),
    ('artifact_ref', None), ('source_response_id', 'foreign-response'),
    ('branch_id', 'foreign-producer'), ('phase_id', 'foreign-phase'),
    ('obligation_id', 'foreign-obligation'), ('file_sha256', '0' * 64),
])
def test_prepared_reference_tampering_is_rejected(handoff, key, value):
    h = handoff
    plan = h.plan()
    for field in ('reference_artifacts', 'input_artifacts'):
        for ref in plan['infer_payload'].get(field) or []:
            ref[key] = value
            if key == 'artifact_ref':
                ref['ref'] = value
    with pytest.raises(RuntimeError):
        h.owner.execute_prepared_late_fill_branch(plan)
    assert h.calls == []


@pytest.mark.parametrize('change', ['missing_file', 'changed_bytes', 'symlink',
                                   'consumer_contract', 'suppress_references', 'missing_references'])
def test_bound_input_cannot_drift(handoff, change):
    h = handoff
    plan = h.plan()
    if change == 'missing_file':
        h.path.unlink()
    elif change == 'changed_bytes':
        h.path.write_bytes(b'different audio')
    elif change == 'symlink':
        other = h.root / 'other.wav'
        shutil.copyfile(h.path, other)
        h.path.unlink()
        h.path.symlink_to(other)
    elif change == 'consumer_contract':
        plan['infer_payload']['execution_contract']['branch_id'] = 'other-consumer'
    elif change == 'suppress_references':
        plan['infer_payload']['suppress_reference_file_context'] = True
    else:
        plan['infer_payload']['reference_artifacts'] = []
        plan['infer_payload']['input_artifacts'] = []
    with pytest.raises(RuntimeError):
        h.owner.execute_prepared_late_fill_branch(plan)
    assert not h.calls


@pytest.mark.parametrize('key', ['artifact_ref', 'artifact_id', 'branch_id', 'phase_id', 'source_response_id'])
def test_conflicting_producer_identity_never_creates_private_authority(handoff, key):
    h = handoff
    h.producer['artifacts'][0][key] = 'foreign'
    with pytest.raises(ValueError, match='Direct audio dependency'):
        h.plan()
    assert not h.calls


def test_http_cannot_supply_runtime_dependency_authority(handoff):
    from dataclasses import asdict
    h = handoff
    plan = h.plan()
    wire = copy.deepcopy(plan['infer_payload'])
    wire['direct_audio_dependency'] = asdict(plan['direct_audio_dependency'])
    response = h.web.app.test_client().post('/api/infer', json=wire)
    assert response.status_code == 400
    assert 'artifact identity unavailable' in response.get_json()['error']
    assert not h.calls


def add_producer(h):
    other = h.root / 'other' / h.path.name
    other.parent.mkdir()
    shutil.copyfile(h.path, other)
    raw = {**h.raw, 'saved_audio_path': str(other),
           'tts_audio_integrity_evidence': build_tts_audio_integrity_evidence(other, 'The lighthouse is quiet.')}
    producer = h.owner.attach_late_fill_result_artifact_identity(
        {**raw, 'branch_id': 'tts-2', 'phase_id': 'phase-4', 'obligation_id': 'audio-2'},
        h.current, raw, capability='text_to_speech')
    h.current['late_fill']['fill_results'].insert(0, producer)
    return producer


def test_multiple_producers_select_exact_dependency_despite_equal_name_and_bytes(handoff):
    h = handoff
    other = add_producer(h)
    plan = h.plan()
    result = h.owner.execute_prepared_late_fill_branch(plan)['infer_result']
    assert result['audio_reference_input_evidence']['artifact_ref'] == h.producer['artifact_ref']
    assert result['audio_reference_input_evidence']['artifact_ref'] != other['artifact_ref']


def test_equal_digest_does_not_authorize_another_artifact(handoff):
    h = handoff
    other = add_producer(h)
    h.consumer['input_refs'] = [{'kind': 'artifact', 'artifact_ref': other['artifact_ref']}]
    with pytest.raises(ValueError, match='unavailable'):
        h.plan()
    assert not h.calls


def test_ambiguous_producers_fail_but_explicit_artifact_selects_one(handoff):
    h = handoff
    other = add_producer(h)
    h.consumer['depends_on'].append('phase-4')
    h.consumer['input_refs'] = []
    with pytest.raises(ValueError, match='ambiguous'):
        h.plan()
    h.consumer['input_refs'] = [{'kind': 'artifact', 'artifact_ref': h.producer['artifact_ref']}]
    result = h.owner.execute_prepared_late_fill_branch(h.plan())['infer_result']
    assert result['audio_reference_input_evidence']['artifact_ref'] == h.producer['artifact_ref']


def test_same_path_conflicting_canonical_identities_are_not_deduplicated(handoff):
    h = handoff
    h.producer['artifacts'].append({**h.producer['artifacts'][0], 'artifact_id': 'other', 'artifact_ref': 'artifact:other'})
    assert len(h.owner._artifact_records_from_late_fill_result(h.producer)) == 2
    with pytest.raises(ValueError, match='ambiguous'):
        h.plan()


def test_later_frame_registry_publication_preserves_direct_identity(handoff, monkeypatch):
    from fruth_services.artifact_registry import persist_output_artifact_registry_records
    from fruth_services.response_frames import attach_response_frame
    h = handoff
    direct = h.owner.execute_prepared_late_fill_branch(h.plan())['infer_result']['audio_reference_input_evidence']
    payload = h.owner.merge_late_fill_result_fields(h.current, h.producer)
    payload = attach_response_frame(payload)
    persist_output_artifact_registry_records(payload, ledger_path=h.ledger)
    monkeypatch.setattr(h.web, '_get_response_lookup_record', lambda rid: {'response_payload': payload})
    _, infer = h.prepare()
    response = h.web.app.test_client().post('/api/infer', json=infer)
    assert response.status_code == 200, response.get_json()
    retained = response.get_json()['audio_reference_input_evidence']
    for key in ('artifact_ref', 'artifact_id', 'source_response_id', 'branch_id', 'phase_id', 'path', 'file_sha256'):
        assert retained[key] == direct[key]
