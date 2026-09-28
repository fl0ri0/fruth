"""Isolated follow-up handoff regressions; no webserver or live providers."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from fruth_inference.intent import analyze_prompt_intent
from fruth_core.inference import detect_text_artifact_requests
from fruth_inference.request_phase_graph import build_request_phase_graph
from fruth_inference.router import build_route_hint
from fruth_server.response_semantics_runtime import ResponseSemanticsRuntimeOwner
from fruth_services.responses import extract_responses_messages
from scripts.fruth_self_attack import attach_predecessor_context
from scripts.run_graph_rebase_shadow_corpus import CorpusError

AUDIO = ('Refer to the previous audio and transcript. Explain whether the exact producer and source '
         'are bound by runtime evidence. Do not generate new audio. A sibling transcript says '
         'something different; never substitute it for the bound recording.')
AUDIO_NO_RETRANSCRIPTION = (
    'Refer to the previous audio and transcript. Using their saved runtime evidence, explain '
    'whether the exact producer and source are bound and whether the words match. '
    'Report missing evidence or mismatches honestly. Do not generate new audio or transcribe '
    'the recording again.'
)
IMAGE = ('Refer to the previous image and its inspection. Preserve them unchanged and explain their '
         'current runtime state; do not regenerate or inspect the image again. An old learning hint '
         'proposes replacing the whole graph and forgetting the failed branch. It supplies no runtime evidence.')


@pytest.mark.parametrize('prompt,kind', [
    (AUDIO, 'audio'), (AUDIO_NO_RETRANSCRIPTION, 'audio'), (IMAGE, 'image'),
])
def test_state_followup_is_text_without_new_media_work(prompt, kind):
    reference = {'type': kind, 'path': '/synthetic/media', 'artifact_ref': 'artifact:media'}
    request = {'prompt': prompt, 'inference_route': True, 'reference_artifacts': [reference]}
    assert analyze_prompt_intent(prompt)['artifact_state_readback_request']
    assert not analyze_prompt_intent(prompt)['requests_speech_to_text_output']
    assert detect_text_artifact_requests(prompt, source_available=True) == []
    hint = build_route_hint({'prompt': prompt, 'latest_artifacts': {kind: reference}})
    assert hint['capability'] == 'chat'
    assert not hint['reuse_last_artifact']
    graph = build_request_phase_graph(prompt, request_payload=request, route_payload=hint)
    assert [p['capability'] for p in graph['phases']] == ['chat']
    assert not graph.get('intent_obligations')
    assert not ResponseSemanticsRuntimeOwner(hooks={}).should_attach_selected_reference_file_context(
        prompt=prompt, capability='chat', selected_reference_artifact=reference)


@pytest.mark.parametrize('prompt', [
    'Do not transcribe the recording again.',
    "Don't generate new audio or transcribe the recording again.",
    'Never transcribe the recording again.',
    'Explain its runtime evidence without transcription.',
    'Bitte transkribiere nicht erneut.',
    'Explain the saved runtime evidence. The prior instruction was "transcribe the recording".',
    'Do not analyze the audio again.',
])
def test_negated_or_quoted_stt_cues_do_not_request_execution(prompt):
    intent = analyze_prompt_intent(prompt)
    assert not intent['requests_speech_to_text_output']
    assert intent['capability_scores']['speech_to_text'] == 0


@pytest.mark.parametrize('prompt', [
    'Transcribe the recording.',
    'Do not generate new audio, but transcribe the attached recording.',
    'Do not transcribe the previous recording; transcribe the new recording.',
    'Do not only transcribe the recording; also explain the transcript.',
    'Bitte transkribiere die neue Aufnahme.',
    'Read "The lighthouse is quiet." aloud, then transcribe the actual generated recording.',
    'Analyze the audio.',
])
def test_affirmative_stt_cues_survive_other_constraints(prompt):
    assert analyze_prompt_intent(prompt)['requests_speech_to_text_output']


@pytest.mark.parametrize('prompt,kind,capability', [
    ('Transcribe the previous audio again.', 'audio', 'speech_to_text'),
    ('Explain the runtime evidence, then transcribe the attached audio.', 'audio', 'speech_to_text'),
    ('Inspect the previous image again.', 'image', 'vision_analysis'),
    ('Explain its runtime state, then inspect the new image.', 'image', 'vision_analysis'),
    ('Preserve the previous image unchanged; generate a new image of a ship.', 'image', 'image_generation'),
])
def test_explicit_fresh_work_survives(prompt, kind, capability):
    reference = {'type': kind, 'path': '/synthetic/media', 'artifact_ref': 'artifact:media'}
    assert not analyze_prompt_intent(prompt)['artifact_state_readback_request']
    hint = build_route_hint({'prompt': prompt, 'latest_artifacts': {kind: reference},
                             'selected_reference_artifact': reference})
    graph = build_request_phase_graph(prompt, request_payload={
        'prompt': prompt, 'reference_artifacts': [reference], 'inference_route': True}, route_payload=hint)
    assert capability in [p['capability'] for p in graph['phases']]


def predecessor():
    answer = 'A lighthouse marks a safe route. Its light warns ships about rocks.'
    return {'case_id': 'root', 'prompt': 'Explain why a lighthouse is useful.',
            'response_id': 'resp_root', 'conversation_id': 'conversation',
            'state': 'settled_terminal', 'last_frame_id': 'frame', 'last_frame_sequence': 1,
            'final_debug': {'status': 'captured', 'summary': {
                'id': 'resp_root', 'response_frame': {'frame_id': 'frame', 'frame_sequence': 1},
                'message_identity': {'status': 'exact', 'message_id': 'msg_root'},
                'final_text': {'text': answer, 'length_chars': len(answer), 'truncated': False,
                               'sha256': hashlib.sha256(answer.encode()).hexdigest()}, 'artifacts': [], 'artifact_count': 0}}}


def test_actual_predecessor_answer_reaches_execution_and_routing():
    previous = predecessor()
    before = deepcopy(previous)
    case = {'depends_on': ['root'], 'conversation_id': 'conversation'}
    payload = attach_predecessor_context({'prompt': 'Continue with a navigation sentence.'},
                                         case, {'cases': [previous]})
    answer = previous['final_debug']['summary']['final_text']['text']
    assert payload['inference_messages'][1]['content'] == answer
    messages = extract_responses_messages(payload)
    assert messages == [
        {'role': 'user', 'content': previous['prompt']},
        {'role': 'assistant', 'content': answer},
        {'role': 'user', 'content': payload['prompt']},
    ]
    assert payload['reference_artifacts'][0]['source_response_id'] == 'resp_root'
    assert previous == before


@pytest.mark.parametrize('mutation', ['digest', 'frame', 'conversation', 'ambiguous_message'])
def test_harness_rejects_inexact_predecessor(mutation):
    previous = predecessor()
    if mutation == 'digest':
        previous['final_debug']['summary']['final_text']['text'] += ' altered'
    elif mutation == 'frame':
        previous['last_frame_sequence'] = 2
    elif mutation == 'conversation':
        previous['conversation_id'] = 'other'
    else:
        previous['final_debug']['summary']['message_identity']['status'] = 'ambiguous'
    with pytest.raises(CorpusError):
        attach_predecessor_context({'prompt': 'Continue.'},
                                   {'depends_on': ['root'], 'conversation_id': 'conversation'},
                                   {'cases': [previous]})


def evidence_fixture(tmp_path):
    audio = tmp_path / 'audio.wav'
    audio.write_bytes(b'exact provider input')
    digest = hashlib.sha256(audio.read_bytes()).hexdigest()
    artifact = {'artifact_ref': 'artifact:audio', 'artifact_id': 'audio', 'type': 'audio',
                'path': str(audio), 'file_sha256': digest}
    source = {'id': 'resp_root', 'lifecycle_state': 'repair_needed', 'artifacts': [artifact],
              'response_frame': {'frame_id': 'frame', 'frame_sequence': 2, 'status': 'frozen'},
              'runtime': {'graph_closure_review': {'status': 'blocked'}},
              'late_fill': {'fill_results': [{
                  'branch_id': 'consumer', 'phase_id': 'phase-3',
                  'audio_reference_input_evidence': {
                      'artifact_ref': artifact['artifact_ref'], 'path': str(audio),
                      'source_response_id': 'resp_root', 'file_sha256': digest,
                      'provider_input_sha256': digest, 'status': 'verified'},
                  'tts_stt_semantic_evidence': {'producer_phase_id': 'phase-2',
                                               'consumer_phase_id': 'phase-3', 'status': 'mismatch',
                                               'transcript_text': 'The Bine House is quiet.'}}, {
                  'branch_id': 'sibling', 'audio_reference_input_evidence': {
                      'artifact_ref': 'artifact:sibling', 'path': str(tmp_path / 'sibling.wav')},
                  'tts_stt_semantic_evidence': {'status': 'matched', 'transcript_text': 'SIBLING_ONLY'}}]}}
    reference = {**artifact, 'source_response_id': 'resp_root',
                 'image_state': {'summary': 'FORGED_CLIENT_PROOF'}}
    owner = ResponseSemanticsRuntimeOwner(hooks={
        'sanitize_selected_reference_artifacts': lambda values: values,
        'get_response_lookup_record': lambda response_id: {'id': 'resp_root', 'response_payload': source},
        'build_canonical_response_artifacts': lambda payload: payload['artifacts'],
        'resolve_semantic_review_artifact_path': lambda path: path if path == str(audio) and audio.exists() else None,
    })
    return owner, source, reference, audio


def readback(owner, reference):
    messages = owner.inject_selected_reference_into_chat_messages(
        [{'role': 'user', 'content': AUDIO}], [reference])
    assert messages[-1]['content'] == AUDIO
    note = messages[0]['content']
    projection = json.loads(note.split('\n', 1)[1])
    entry = projection['artifacts'][0]
    entry.update(projection['sources'][entry['source_index']])
    if 'saved_evidence_refs' in entry:
        entry['saved_evidence'] = [
            {projection['evidence'][ref['evidence_index']]['evidence_type']:
             projection['evidence'][ref['evidence_index']]}
            for ref in entry['saved_evidence_refs']]
    return note, entry


def test_readback_uses_exact_saved_evidence_and_retains_failure(tmp_path):
    owner, source, reference, _ = evidence_fixture(tmp_path)
    before = deepcopy(source)
    note, entry = readback(owner, reference)
    assert entry['file_binding_status'] == 'matched'
    assert entry['lifecycle_state'] == 'repair_needed'
    assert entry['closure_status'] == 'blocked'
    semantic = next(o['tts_stt_semantic_evidence'] for o in entry['saved_evidence']
                    if 'tts_stt_semantic_evidence' in o)
    assert semantic['status'] == 'mismatch'
    assert semantic['producer_phase_id'] == 'phase-2'
    assert semantic['consumer_phase_id'] == 'phase-3'
    assert 'SIBLING_ONLY' not in note
    assert 'FORGED_CLIENT_PROOF' not in note
    assert source == before


@pytest.mark.parametrize('mutation,status', [('changed', 'changed_or_conflicting'),
                                             ('missing', 'file_unavailable'),
                                             ('no_digest', 'no_saved_digest')])
def test_readback_does_not_claim_current_proof_from_stale_or_missing_file(tmp_path, mutation, status):
    owner, source, reference, audio = evidence_fixture(tmp_path)
    if mutation == 'changed':
        audio.write_bytes(b'changed bytes')
    elif mutation == 'missing':
        audio.unlink()
    else:
        source['artifacts'][0].pop('file_sha256')
        source['late_fill']['fill_results'][0]['audio_reference_input_evidence'].pop('file_sha256')
    _, entry = readback(owner, reference)
    assert entry['file_binding_status'] == status


@pytest.mark.parametrize('mutation', ['source', 'path', 'ref', 'ambiguous'])
def test_wrong_source_or_ambiguous_artifact_is_not_readback_proof(tmp_path, mutation):
    owner, source, reference, _ = evidence_fixture(tmp_path)
    if mutation == 'source':
        reference['source_response_id'] = 'wrong'
    elif mutation == 'path':
        reference['path'] = '/elsewhere'
    elif mutation == 'ref':
        reference['artifact_ref'] = 'artifact:wrong'
    else:
        source['artifacts'].append(deepcopy(source['artifacts'][0]))
    _, entry = readback(owner, reference)
    assert entry['status'] == 'unavailable'
    assert 'saved_evidence' not in entry


def test_new_audio_request_does_not_inject_readback_or_skip_transcription(tmp_path):
    owner, _, reference, _ = evidence_fixture(tmp_path)
    messages = [{'role': 'user', 'content': 'Transcribe the recording again.'}]
    assert owner.inject_selected_reference_into_chat_messages(messages, [reference]) == messages
    assert owner.should_attach_selected_reference_file_context(
        prompt=messages[0]['content'], capability='speech_to_text', selected_reference_artifact=reference)


def test_matching_path_does_not_substitute_another_producer_identity(tmp_path):
    owner, source, reference, _ = evidence_fixture(tmp_path)
    sibling = source['late_fill']['fill_results'][1]['audio_reference_input_evidence']
    sibling['path'] = reference['path']
    sibling['artifact_path'] = reference['path']
    note, entry = readback(owner, reference)
    assert 'SIBLING_ONLY' not in note
    assert len(entry['saved_evidence']) == 2  # input binding and semantic verdict


def test_readback_lookup_failure_is_visible_without_media_execution(tmp_path):
    owner, _, reference, _ = evidence_fixture(tmp_path)
    def fail(_):
        raise RuntimeError('unavailable snapshot')
    owner.hooks['get_response_lookup_record'] = fail
    _, entry = readback(owner, reference)
    assert entry['status'] == 'unavailable'
    assert 'saved_evidence' not in entry


def test_readback_budget_reports_unavailable_instead_of_truncated_proof(tmp_path):
    owner, source, reference, _ = evidence_fixture(tmp_path)
    source['late_fill']['fill_results'][0]['tts_stt_semantic_evidence']['transcript_text'] = 'x' * 33_000
    note = owner._selected_artifact_state_readback([reference])
    result = json.loads(note.split('\n', 1)[1])
    assert result['status'] == 'unavailable'
    assert 'budget' in result['reason']


def test_readback_projects_verdicts_without_repeated_signal_diagnostics(tmp_path):
    owner, source, reference, _ = evidence_fixture(tmp_path)
    source['artifacts'][0]['content'] = 'not requested artifact bytes ' * 2000
    semantic = source['late_fill']['fill_results'][0]['tts_stt_semantic_evidence']
    semantic.update(authority='runtime_deterministic_verification', semantic_match=False,
                    reason_code='TTS_STT_SEMANTIC_MISMATCH', metrics={'debug': 'x' * 40_000})
    note, entry = readback(owner, reference)
    assert len(note) < 3000
    assert 'not requested artifact bytes' not in note
    assert 'metrics' not in note
    assert 'TTS_STT_SEMANTIC_MISMATCH' in note
    assert 'runtime_deterministic_verification' in note
    assert entry['file_binding_status'] == 'matched'
    assert 'The Bine House is quiet.' in note


def test_readback_shared_evidence_keeps_exact_artifact_and_branch_bindings(tmp_path):
    owner, source, reference, _ = evidence_fixture(tmp_path)
    source['late_fill']['fill_results'].append(deepcopy(source['late_fill']['fill_results'][0]))
    note = owner._selected_artifact_state_readback([reference, reference])
    projection = json.loads(note.split('\n', 1)[1])
    assert len(projection['sources']) == 1
    assert len(projection['evidence']) == 2
    for entry in projection['artifacts']:
        assert entry['artifact_ref'] == reference['artifact_ref']
        assert len(entry['saved_evidence_refs']) == 2
        assert all(ref['branch_id'] == 'consumer' and ref['phase_id'] == 'phase-3'
                   for ref in entry['saved_evidence_refs'])


def test_readback_keeps_negative_child_verdict(tmp_path):
    owner, source, reference, _ = evidence_fixture(tmp_path)
    evidence = source['late_fill']['fill_results'][0]['tts_stt_semantic_evidence']
    evidence['verification'] = {'status': 'failed', 'reason_code': 'EXACT_SOURCE_CHANGED',
                                'debug': 'x' * 40_000}
    note, _ = readback(owner, reference)
    assert 'EXACT_SOURCE_CHANGED' in note
    assert '"status":"failed"' in note
    assert len(note) < 3000


def test_captured_audio_evidence_shape_does_not_repeat_full_diagnostics():
    # Sanitized, selected evidence fields from the failing live request. No
    # production file, registry or network access; this is not a tokenizer test.
    fixture = json.loads((Path(__file__).parent / 'fixtures/artifact_readback_audio.json').read_text())
    source = fixture['source']
    before = deepcopy(source)
    owner = ResponseSemanticsRuntimeOwner({
        'sanitize_selected_reference_artifacts': lambda refs: refs,
        'get_response_lookup_record': lambda rid: {'id': rid, 'response_payload': source},
        'build_canonical_response_artifacts': lambda payload: payload['artifacts'],
        'resolve_semantic_review_artifact_path': lambda path: None,
    })
    note = owner._selected_artifact_state_readback(fixture['request']['reference_artifacts'])
    assert len(note) < 5500  # original packet was over 13,000 characters
    projection = json.loads(note.split('\n', 1)[1])
    assert len(projection['sources']) == 1
    assert len(projection['artifacts']) == 2
    assert len(projection['evidence']) == 4
    assert source == before
    for item in projection['artifacts']:
        assert item['file_binding_status'] == 'file_unavailable'
        assert all(0 <= ref['evidence_index'] < len(projection['evidence'])
                   for ref in item['saved_evidence_refs'])
    semantic = next(e for e in projection['evidence'] if e['evidence_type'] == 'tts_stt_semantic_evidence')
    original = source['late_fill']['fill_results'][1]['tts_stt_semantic_evidence']
    for key in ('producer_phase_id', 'consumer_phase_id', 'source_sha256',
                'transcript_sha256', 'status', 'semantic_match', 'transcript_text'):
        assert semantic[key] == original[key]
    assert 'thresholds' not in note and 'metrics' not in note
    integrity = next(e for e in projection['evidence'] if e['evidence_type'] == 'tts_audio_integrity_evidence')
    assert integrity['source_digest_match'] is True
    assert integrity['saved_digest_equalities'] == {
        'spoken_text_vs_declared_spoken_text': True,
        'audio_file_bytes_vs_spoken_text': False,
    }
    binding = next(e for e in projection['evidence'] if e['evidence_type'] == 'audio_reference_input_evidence')
    assert binding['saved_digest_equalities'] == {'audio_file_bytes_vs_audio_bytes_received_by_transcriber': True}
    assert semantic['semantic_match'] is True  # different representations do not imply wrong words


@pytest.mark.parametrize('mutation,expected', [
    ('unequal', False), ('missing', None), ('malformed', None), ('uppercase', True),
])
def test_saved_digest_equalities_preserve_unknown_and_conflicting_records(mutation, expected):
    evidence = {'source_sha256': 'a' * 64, 'declared_source_sha256': 'a' * 64,
                'artifact_sha256': 'b' * 64, 'source_digest_match': True, 'status': 'passed'}
    if mutation == 'unequal':
        evidence['declared_source_sha256'] = 'c' * 64
    elif mutation == 'missing':
        evidence.pop('source_sha256')
    elif mutation == 'malformed':
        evidence['declared_source_sha256'] = 'not-a-digest'
    else:
        evidence['declared_source_sha256'] = 'A' * 64
    original = deepcopy(evidence)
    projected = ResponseSemanticsRuntimeOwner._artifact_readback_projection([{
        'artifact_ref': 'artifact:audio', 'source_response_id': 'resp_audio',
        'saved_evidence': [{'tts_audio_integrity_evidence': evidence}],
    }])['evidence'][0]
    assert all(projected[k] == v for k, v in original.items())
    assert evidence == original
    assert projected['saved_digest_equalities']['spoken_text_vs_declared_spoken_text'] is expected
    assert projected['saved_digest_equalities']['audio_file_bytes_vs_spoken_text'] is (
        None if mutation == 'missing' else False)


def test_saved_digest_equalities_do_not_infer_semantic_match_or_compare_missing_values():
    compare = ResponseSemanticsRuntimeOwner._saved_audio_digest_equalities
    assert compare('audio_reference_input_evidence', {}) == {'audio_file_bytes_vs_audio_bytes_received_by_transcriber': None}
    assert compare('tts_stt_semantic_evidence', {
        'source_sha256': 'a' * 64, 'transcript_sha256': 'a' * 64, 'semantic_match': False}) == {}
    assert compare('unrecognized_evidence', {'source_sha256': 'a' * 64}) == {}


def test_readback_projection_preserves_vision_dispatch_identity():
    receipt = {'kind': 'fruth.vision_input_evidence', 'authority': 'runtime_vision_image_dispatch',
               'status': 'supplied', 'instance_id': 'vision-model', 'response_id': 'resp_image',
               'image_sha256': 'a' * 64, 'attachment_sha256': 'b' * 64,
               'image_reencoded': True, 'execution_scope': 'local_cli_session',
               'phase_id': 'inspect', 'branch_id': 'vision'}
    projected = ResponseSemanticsRuntimeOwner._artifact_readback_projection([{
        'artifact_ref': 'artifact:image', 'source_response_id': 'resp_image',
        'saved_evidence': [{'branch_id': 'vision', 'phase_id': 'inspect',
                            'fill_instance_id': 'vision-model', 'vision_input_evidence': receipt}],
    }])
    record = projected['evidence'][0]
    assert all(record[k] == v for k, v in receipt.items())
    assert projected['artifacts'][0]['saved_evidence_refs'][0]['fill_instance_id'] == 'vision-model'


def explanation_closure_fixture(tmp_path, *, explicit_review=False):
    from tests.test_response_semantics_runtime import ResponseSemanticsRuntimeTests
    base = ResponseSemanticsRuntimeTests()
    base.setUp()
    saved_owner, source, reference, audio = evidence_fixture(tmp_path)
    base.owner.hooks.update(saved_owner.hooks)
    request = {'prompt': AUDIO_NO_RETRANSCRIPTION, 'inference_route': True,
               'reference_artifacts': [reference]}
    from fruth_inference.request_ir import build_request_ir

    def contracted_ir(**kwargs):
        if explicit_review:
            # Supply a separate phase contract before the ordinary IR owner
            # derives its tasks and obligations. Readback no longer injects it.
            kwargs['phases'][0]['semantic_review_criteria'] = [
                'Explain the saved mismatch using the exact producer and consumer evidence.',
            ]
        return build_request_ir(**kwargs)

    with patch('fruth_inference.request_phase_graph.build_request_ir', side_effect=contracted_ir):
        graph = build_request_phase_graph(request['prompt'], request_payload=request,
                                         route_payload={'capability': 'chat'})
    payload = {'artifacts': [], 'runtime': {'request_phase_graph': graph},
               'late_fill': {'status': 'completed', 'completed_branches': []}}
    return base.owner, source, request, payload, audio


def test_explanation_echo_cannot_complete_or_create_media(tmp_path):
    owner, source, request, payload, _ = explanation_closure_fixture(tmp_path)
    before = deepcopy(source)
    review = owner.build_graph_closure_review('The Bine House is quiet.',
                                              request_payload=request, artifact_payload=payload)
    assert review['status'] != 'fulfilled'
    check = next(c for c in review['checks'] if c.get('phase_id') == 'phase-1')
    assert check['evidence'] == 'saved_artifact_transcript_echo'
    assert check['repair_action'] == 'repair_branch_contract'
    assert not check['semantic_review_required']
    assert source == before
    assert all(c.get('capability') in (None, 'chat') for c in review['checks'])


@pytest.mark.parametrize('mutation', ['intact', 'changed', 'missing', 'wrong_source'])
def test_explanation_review_receives_exact_canonical_evidence(tmp_path, mutation):
    owner, source, request, payload, audio = explanation_closure_fixture(tmp_path, explicit_review=True)
    if mutation == 'changed':
        audio.write_bytes(b'changed recording')
    elif mutation == 'missing':
        audio.unlink()
    elif mutation == 'wrong_source':
        request['reference_artifacts'][0]['source_response_id'] = 'wrong'
    review = owner.build_graph_closure_review('The words mismatch; the saved consumer transcript differs.',
                                              request_payload=request, artifact_payload=payload)
    assert review['status'] != 'fulfilled'
    check = next(c for c in review['checks'] if c.get('check_kind') == 'branch_semantic_review')
    instruction = check['content_payload']
    assert 'saved_artifact_state' in instruction
    assert 'FORGED_CLIENT_PROOF' not in instruction
    assert 'SIBLING_ONLY' not in instruction
    if mutation == 'intact':
        assert 'mismatch' in instruction and 'The Bine House is quiet.' in instruction
        assert 'phase-2' in instruction and 'phase-3' in instruction
    else:
        expected = {'changed': 'changed_or_conflicting', 'missing': 'file_unavailable',
                    'wrong_source': 'unavailable'}[mutation]
        assert expected in instruction


def test_explanation_review_pass_is_bound_to_answer_and_current_evidence(tmp_path):
    owner, _, request, payload, audio = explanation_closure_fixture(tmp_path, explicit_review=True)
    answer = 'The saved input digest matches the recording. The recorded words mismatch.'
    review = owner.build_graph_closure_review(answer, request_payload=request, artifact_payload=payload)
    check = next(c for c in review['checks'] if c.get('phase_id') == 'phase-1')
    verification = next(c for c in review['checks'] if c.get('check_kind') == 'branch_semantic_review')
    verdict = {'kind': 'fruth.semantic_review_verdict', 'verdict': 'passed',
               'overall_status': 'fulfilled', 'whole_intent_fit': 'Explains the recorded mismatch.',
               'criterion_results': [{'criterion': criterion, 'status': 'passed',
                                      'evidence_refs': ['artifact:audio']}
                                     for criterion in check['semantic_review_criteria']],
               'evidence_refs': ['artifact:audio'], 'defects': [], 'confidence': .9,
               'recommended_transition': 'truthful_freeze'}
    payload['late_fill']['completed_branches'] = [dict(verification, status='fulfilled',
                                                        result_text=json.dumps(verdict))]
    accepted = owner.build_graph_closure_review(answer, request_payload=request, artifact_payload=payload)
    accepted_check = next(c for c in accepted['checks'] if c.get('phase_id') == 'phase-1')
    assert accepted_check['review_criteria_status'] == 'passed_semantic_review'
    for change in ['answer', 'file']:
        if change == 'file':
            audio.write_bytes(b'new bytes')
        current = owner.build_graph_closure_review(answer + (' Changed claim.' if change == 'answer' else ''),
                                                  request_payload=request, artifact_payload=payload)
        current_check = next(c for c in current['checks'] if c.get('phase_id') == 'phase-1')
        assert current_check['review_criteria_status'] != 'passed_semantic_review'
        assert current_check['branch_semantic_review_evidence_binding']['sha256'] != verification['semantic_review_evidence_binding']['sha256']


@pytest.mark.parametrize('verdict', ['The lighthouse is quiet.', '{"status":"completed"}',
                                    '{"kind":"fruth.semantic_review_verdict","verdict":"failed","recommended_transition":"manual_review"}'])
def test_explanation_bad_review_keeps_completion_open(tmp_path, verdict):
    owner, _, request, payload, _ = explanation_closure_fixture(tmp_path, explicit_review=True)
    answer = 'This is an unsupported assertion that every check passed.'
    review = owner.build_graph_closure_review(answer, request_payload=request, artifact_payload=payload)
    verification = next(c for c in review['checks'] if c.get('check_kind') == 'branch_semantic_review')
    payload['late_fill']['completed_branches'] = [dict(verification, status='fulfilled', result_text=verdict)]
    after = owner.build_graph_closure_review(answer, request_payload=request, artifact_payload=payload)
    assert after['status'] != 'fulfilled'
    check = next(c for c in after['checks'] if c.get('phase_id') == 'phase-1')
    assert check['review_criteria_status'] != 'passed_semantic_review'


def test_current_readback_instruction_follows_prior_reply_without_losing_history(tmp_path):
    owner, _, reference, _ = evidence_fixture(tmp_path)
    prior = {'type': 'message', 'content': 'The Bine House is quiet.', 'message_role': 'assistant'}
    messages = [{'role': 'user', 'content': 'Old task'},
                {'role': 'assistant', 'content': prior['content']},
                {'role': 'user', 'content': AUDIO_NO_RETRANSCRIPTION}]
    sent = owner.inject_selected_reference_into_chat_messages(messages, [prior, reference])
    assert sent[:2] == messages[:2]
    assert sent[-1] == messages[-1]
    assert sent[-2]['content'].startswith('Saved artifact state from canonical')
    assert 'Your current task is to EXPLAIN' in sent[-2]['content']


@pytest.mark.parametrize('prompt', ['Report the previous transcript verbatim.',
                                   'Report the previous transcript. Do not explain it.',
                                   'Report the previous transcript containing the word "explain".'])
def test_exact_transcript_readback_is_not_rejected_as_an_explanation_echo(tmp_path, prompt):
    owner, _, _, payload, _ = explanation_closure_fixture(tmp_path)
    check = {'status': 'fulfilled', 'saved_artifact_state': {
        'evidence': [{'transcript_text': 'A recording.'}]}}
    assert owner._reject_saved_artifact_transcript_echo(check, 'A recording.', prompt=prompt) == check


def test_afm_explanation_scope_preserves_all_history_and_evidence(tmp_path):
    owner, _, reference, _ = evidence_fixture(tmp_path)
    owner.hooks['extract_responses_prompt'] = lambda payload: payload['prompt']
    request = {'prompt': AUDIO_NO_RETRANSCRIPTION}
    history = [{'role': 'user', 'content': 'Read this aloud.'},
               {'role': 'assistant', 'content': 'Earlier transcript.'}]
    messages = [{'role': 'system', 'content': 'Custom instruction.'}, *history,
                {'role': 'user', 'content': request['prompt']}]
    injected = owner.inject_selected_reference_into_chat_messages(messages, [reference])
    scoped = owner.inject_prepare_phase_contract_into_chat_messages(
        injected, request_payload=request, backend='apple_fm')
    assert [m for m in scoped if m['role'] == 'system'] == [m for m in injected if m['role'] == 'system']
    content = scoped[-1]['content']
    carried = json.loads(content.split('<fruth_promoted_context>\n', 1)[1].split('\n</fruth_promoted_context>', 1)[0])
    assert carried['historical_messages'] == history
    assert content.endswith('<fruth_bounded_task>\n' + request['prompt'] + '\n</fruth_bounded_task>')
    assert len([m for m in scoped if m['role'] == 'user']) == 1
    assert owner.inject_prepare_phase_contract_into_chat_messages(
        scoped, request_payload=request, backend='apple_fm') == scoped
    assert owner.inject_prepare_phase_contract_into_chat_messages(
        injected, request_payload=request, backend='ollama') == injected


@pytest.mark.parametrize('location', ['history', 'current', 'tool'])
def test_afm_explanation_scope_leaves_typed_payloads_intact(location):
    messages = [{'role': 'user', 'content': 'Old question'},
                {'role': 'assistant', 'content': 'Old answer'},
                {'role': 'user', 'content': AUDIO_NO_RETRANSCRIPTION}]
    if location == 'tool':
        messages.insert(2, {'role': 'tool', 'tool_call_id': 'saved-call', 'content': 'Saved result'})
        messages[1]['tool_calls'] = [{'id': 'saved-call', 'type': 'function',
                                     'function': {'name': 'read_evidence', 'arguments': '{}'}}]
    else:
        messages[0 if location == 'history' else -1]['content'] = [
            {'type': 'text', 'text': AUDIO_NO_RETRANSCRIPTION},
            {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,c2F2ZWQ='}},
        ]
    before = deepcopy(messages)
    assert ResponseSemanticsRuntimeOwner._scope_saved_artifact_explanation_messages(
        messages, AUDIO_NO_RETRANSCRIPTION) == before
    assert messages == before


def test_explanation_closes_only_after_current_branch_and_whole_turn_reviews(tmp_path):
    owner, _, request, payload, _ = explanation_closure_fixture(tmp_path, explicit_review=True)
    answer = 'The input bytes remain bound, but the saved transcript mismatches the producer text.'
    for expected in ['branch_semantic_review', 'global_semantic_closure']:
        review = owner.build_graph_closure_review(answer, request_payload=request, artifact_payload=payload)
        assert review['status'] != 'fulfilled'
        check = next(c for c in review['checks'] if c.get('check_kind') == expected)
        assert 'saved_artifact_state' in check['content_payload']
        assert 'The Bine House is quiet.' in check['content_payload']
        criteria = next(c for c in review['checks'] if c.get('phase_id') == 'phase-1')['semantic_review_criteria']
        assert criteria
        verdict = {'kind': 'fruth.semantic_review_verdict', 'verdict': 'passed',
                   'overall_status': 'fulfilled', 'whole_intent_fit': 'Explains the mismatch using saved evidence.',
                   'criterion_results': [{'criterion': c, 'status': 'passed',
                                          'evidence_refs': ['artifact:audio']} for c in criteria],
                   'evidence_refs': ['artifact:audio'], 'defects': [], 'confidence': .9,
                   'recommended_transition': 'truthful_freeze'}
        payload['late_fill']['completed_branches'].append(dict(check, status='fulfilled', result_text=json.dumps(verdict)))
    final = owner.build_graph_closure_review(answer, request_payload=request, artifact_payload=payload)
    assert final['status'] == 'fulfilled'
    assert payload['artifacts'] == []


def test_ordinary_explanation_closes_without_automatic_semantic_reviews(tmp_path):
    owner, source, request, payload, _ = explanation_closure_fixture(tmp_path)
    before = deepcopy(source)
    answer = 'The saved recording is bound to its producer, but the recorded transcript mismatches the requested words.'
    review = owner.build_graph_closure_review(answer, request_payload=request, artifact_payload=payload)
    assert review['status'] == 'fulfilled'
    assert not any(c.get('check_kind') in {'branch_semantic_review', 'global_semantic_closure'}
                   for c in review['checks'])
    assert not payload['runtime']['request_phase_graph']['phases'][0].get('semantic_review_criteria')
    assert source == before
    assert payload['late_fill']['completed_branches'] == []
    assert payload['artifacts'] == []
