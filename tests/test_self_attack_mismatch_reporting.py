"""Synthetic, isolated evidence/report tests; no model or webserver execution."""
from copy import deepcopy
import hashlib
import json

import pytest

from scripts.fruth_self_attack import evaluate_capture, explain_incomplete, render_report, verdict_scopes
from scripts.self_attack_checks import audit_truth, rejected_audio_mismatch_evidence


def mismatch_truth():
    source, transcript = 'The lighthouse is quiet.', 'The Bine House is quiet.'
    producer = {'phase_id': 'tts', 'branch_id': 'producer', 'capability': 'text_to_speech',
                'status': 'failed', 'error': {'code': 'TTS_STT_SEMANTIC_MISMATCH'}}
    consumer = {'phase_id': 'stt', 'branch_id': 'consumer', 'capability': 'speech_to_text',
                'status': 'failed', 'depends_on': ['tts'], 'error': {
                    'code': 'DEPENDENCY_CHAIN_REPAIR_REQUIRED', 'stage': 'semantic_evidence_gate',
                    'materialization_blocked': True, 'reason_code': 'TTS_STT_SEMANTIC_MISMATCH',
                    'failed_dependency_ids': ['tts'], 'semantic_evidence': {
                        'kind': 'fruth.tts_stt_semantic_evidence', 'status': 'mismatched',
                        'authority': 'runtime_deterministic_verification', 'semantic_match': False,
                        'reason_code': 'TTS_STT_SEMANTIC_MISMATCH',
                        'producer_phase_id': 'tts', 'producer_branch_id': 'producer',
                        'consumer_phase_id': 'stt', 'consumer_branch_id': 'consumer',
                        'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                        'transcript_sha256': hashlib.sha256(transcript.encode()).hexdigest(),
                        'transcript_text': transcript}}}
    phases = [{k: v for k, v in branch.items() if k not in {'error', 'status'}}
              for branch in (producer, consumer)]
    return {'id': 'resp_mismatch', 'lifecycle_state': 'repair_needed',
            'response_frame': {'frame_id': 'frame-1', 'frame_sequence': 1, 'status': 'completed'},
            'outputs': [{'phase_id': 'tts', 'status': 'pending', 'type': 'audio'},
                        {'phase_id': 'stt', 'status': 'pending', 'type': 'text'}], 'artifacts': [],
            'runtime': {'request_phase_graph': {
                'phases': phases, 'downstream_branches': [],
                'intent_obligations': [{'obligation_id': 'audio', 'required': True}],
                'output_obligations': [{'phase_id': 'tts', 'capability': 'text_to_speech', 'required': True},
                                       {'phase_id': 'stt', 'capability': 'speech_to_text', 'required': True}]},
                'graph_closure_review': {'status': 'blocked', 'checks': [
                    {'phase_id': 'tts', 'status': 'blocked'}, {'phase_id': 'stt', 'status': 'blocked'}]}},
            'late_fill': {'status': 'failed', 'failed_branches': [producer, consumer]}}


def explain_case(tmp_path, payload):
    case = {'case_id': 'root', 'category': 'late_fill_binding', 'response_id': 'resp_mismatch',
            'state': 'settled_repair_needed', 'metadata': {'require_exercised': ['exact_source_binding']}}
    folder = tmp_path / 'captures' / case['response_id']
    folder.mkdir(parents=True)
    capture = folder / 'settled.json'
    capture.write_text(json.dumps({'source': 'settled', 'observed_ns': 1,
                                   'payload': payload, 'artifact_evidence': {}}))
    before = capture.read_bytes()
    cases = evaluate_capture({'cases': [case]}, folder.parent)
    audit_before = deepcopy(cases)
    explain_incomplete(cases, tmp_path)
    assert [{k: v for k, v in c.items() if k != 'incomplete_observations'} for c in cases] == audit_before
    assert capture.read_bytes() == before
    return cases[0]


def test_correct_rejection_is_reported_separately_from_missing_successful_handoff(tmp_path):
    payload = mismatch_truth()
    before = deepcopy(payload)
    case = explain_case(tmp_path, payload)
    assert case['findings'] == []
    assert case['missing'] == ['scenario_not_exercised:exact_source_binding']
    assert 'exact_source_binding' not in case['exercised']
    observation = case['incomplete_observations'][0]
    assert observation['classification'] == 'missing_scenario_coverage'
    assert observation['guard_status'] == 'passed'
    assert observation['coverage_status'] == 'incomplete'
    assert observation['guard_evidence'][0]['consumer_phase_id'] == 'stt'
    assert observation['guard_evidence'][0]['evidence_path'] == '/late_fill/failed_branches/1/error/semantic_evidence'
    assert payload == before
    result = {'verdict': 'incomplete', 'mode': 'live', 'fake_conformance_verdict': 'passed',
              'runs': [{'profile': {'id': 'baseline'}, 'cases': [case], 'runner_status': 0, 'probes': {}}],
              'coverage': {'profiles_selected': 1, 'profiles_available': 1, 'design': 'test', 'inventory_only': 0},
              'owner_tests': {}, 'regressions': []}
    scopes_before = verdict_scopes(result)
    report = render_report(result)
    assert 'Guard PASS: correctly rejected audio/transcript mismatch; successful handoff coverage INCOMPLETE.' in report
    assert 'Full live conformance: **INCOMPLETE**' in report
    assert verdict_scopes(result) == scopes_before
    assert result['verdict'] == 'incomplete'
    assert json.loads(json.dumps(case))['incomplete_observations'][0]['guard_status'] == 'passed'


@pytest.mark.parametrize('mutation', [
    'completed_lifecycle', 'active_work', 'missing_evidence', 'prose_only', 'model_authority',
    'matched', 'semantic_true', 'missing_source_digest', 'bad_transcript_digest', 'same_digest',
    'foreign_producer', 'foreign_consumer', 'foreign_branch', 'changed_dependency',
    'missing_failed_dependency', 'generic_tts_failure', 'duplicate_producer', 'missing_blocked_check',
    'fulfilled_output', 'fulfilled_graph', 'accepted_fill', 'missing_frame', 'malformed_evidence',
    'malformed_phase_id', 'malformed_branch_id', 'unfinished_frame', 'duplicate_consumer', 'malformed_dependencies',
])
def test_unproven_or_contradictory_rejection_is_never_guard_pass(mutation):
    payload = mismatch_truth()
    late = payload['late_fill']
    producer, consumer = late['failed_branches']
    evidence = consumer['error']['semantic_evidence']
    graph = payload['runtime']['request_phase_graph']
    if mutation == 'completed_lifecycle': payload['lifecycle_state'] = 'completed'
    elif mutation == 'active_work': late['active_branches'] = [{'phase_id': 'stt'}]
    elif mutation == 'missing_evidence': consumer['error'].pop('semantic_evidence')
    elif mutation == 'prose_only':
        consumer['error'] = {'message': 'Correctly rejected audio/transcript mismatch'}
    elif mutation == 'model_authority': evidence['authority'] = 'assistant_claim'
    elif mutation == 'matched': evidence['status'] = 'matched'
    elif mutation == 'semantic_true': evidence['semantic_match'] = True
    elif mutation == 'missing_source_digest': evidence.pop('source_sha256')
    elif mutation == 'bad_transcript_digest': evidence['transcript_sha256'] = '0' * 64
    elif mutation == 'same_digest': evidence['source_sha256'] = evidence['transcript_sha256']
    elif mutation == 'foreign_producer': evidence['producer_phase_id'] = 'sibling'
    elif mutation == 'foreign_consumer': evidence['consumer_phase_id'] = 'sibling'
    elif mutation == 'foreign_branch': evidence['consumer_branch_id'] = 'sibling'
    elif mutation == 'changed_dependency': graph['phases'][1]['depends_on'] = ['sibling']
    elif mutation == 'missing_failed_dependency': consumer['error']['failed_dependency_ids'] = []
    elif mutation == 'generic_tts_failure': producer['error']['code'] = 'TIMEOUT'
    elif mutation == 'duplicate_producer': late['failed_branches'].append(deepcopy(producer))
    elif mutation == 'missing_blocked_check': payload['runtime']['graph_closure_review']['checks'] = []
    elif mutation == 'fulfilled_output': payload['outputs'][1]['status'] = 'fulfilled'
    elif mutation == 'fulfilled_graph': graph['phases'][1]['status'] = 'fulfilled'
    elif mutation == 'accepted_fill': late['fill_results'] = [{'phase_id': 'stt', 'status': 'completed'}]
    elif mutation == 'missing_frame': payload['response_frame'] = {}
    elif mutation == 'malformed_evidence': consumer['error']['semantic_evidence'] = 'mismatched'
    elif mutation == 'malformed_phase_id': evidence['producer_phase_id'] = ['tts']
    elif mutation == 'malformed_branch_id': producer['branch_id'] = ['producer']
    elif mutation == 'unfinished_frame': payload['response_frame']['status'] = 'in_progress'
    elif mutation == 'duplicate_consumer': late['failed_branches'].append(deepcopy(consumer))
    elif mutation == 'malformed_dependencies': consumer['error']['failed_dependency_ids'] = 2
    before = deepcopy(payload)
    assert rejected_audio_mismatch_evidence(payload) == []
    assert payload == before


@pytest.mark.parametrize('reason', ['findings', 'missing_truth', 'unsettled', 'no_payload', 'foreign_response'])
def test_case_with_other_uncertainty_or_findings_keeps_existing_classification(tmp_path, reason):
    case = {'case_id': 'root', 'response_id': 'resp_mismatch', 'state': 'settled_repair_needed', 'payload': mismatch_truth(),
            'missing': ['scenario_not_exercised:exact_source_binding'], 'findings': []}
    if reason == 'findings': case['findings'] = [{'code': 'unrelated_violation'}]
    elif reason == 'missing_truth': case['missing'].append('settled_full_truth')
    elif reason == 'unsettled': case['state'] = 'observing'
    elif reason == 'foreign_response': case['response_id'] = 'resp_other'
    else: case.pop('payload')
    missing, findings = deepcopy(case['missing']), deepcopy(case['findings'])
    explain_incomplete([case], tmp_path)
    assert not any('guard_status' in obs for obs in case['incomplete_observations'])
    assert case['missing'] == missing and case['findings'] == findings


def test_accepted_mismatch_remains_a_deterministic_failure(tmp_path):
    payload = mismatch_truth()
    evidence = payload['late_fill']['failed_branches'][1]['error']['semantic_evidence']
    payload['late_fill']['fill_results'] = [{'phase_id': 'stt', 'capability': 'speech_to_text',
                                            'status': 'completed', 'tts_stt_semantic_evidence': evidence}]
    assert 'invalid_source_evidence_accepted' in {f['code'] for f in audit_truth(payload)['findings']}
    case = explain_case(tmp_path, payload)
    assert case['findings']
    assert not any('guard_status' in obs for obs in case['incomplete_observations'])
