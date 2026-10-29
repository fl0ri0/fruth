"""R2 scope presentation and unchanged negative-review authority, offline only."""
from copy import deepcopy
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import threading

import pytest

from fruth_server.response_semantics_runtime import ResponseSemanticsRuntimeOwner as Semantics
from fruth_services.artifact_contracts import saved_file_consumer_prompt
from fruth_services.semantic_review_verdict import (
    semantic_review_verdict_freeze_acceptance, semantic_review_verdict_from_text,
    semantic_review_evidence_reference_catalog,
)
from tests.test_saved_read_syntax_repair import FIXTURES, receipt, runtime_for, retained


def packet(instruction):
    return json.JSONDecoder().raw_decode(instruction.split('Branch runtime evidence:\n', 1)[1])[0]


def retained_reviews(name):
    data = FIXTURES[name]['data']
    for result in data['fill_results']:
        binding = result.get('semantic_review_evidence_binding')
        if binding:
            branch = next(b for b in data['graph']['downstream_branches'] if b['branch_id'] == result['branch_id'])
            evidence = packet(branch['content_payload'])
            yield result, binding, branch, evidence


@pytest.mark.parametrize('name', ['r2-replay', 'alpha-positive-replay'])
def test_exact_retained_packets_verdicts_and_generations(name):
    rows = []
    for result, binding, branch, evidence in retained_reviews(name):
        instruction = branch['content_payload']
        assert Semantics._branch_semantic_review_generation(evidence['branch_check'], instruction)['sha256'] == binding['sha256']
        assert hashlib.sha256(instruction.encode()).hexdigest() == binding['instruction_sha256']
        payload = {'late_fill': {'fill_results': [deepcopy(result)], 'completed_branches': [deepcopy(result)]}}
        verdict = Semantics._semantic_review_verdict_from_late_fill(payload, result['branch_id'],
            review_id=binding['logical_review_id'], expected_evidence_sha256=binding['sha256'],
            require_content_review_result=True, evidence_reference_policy='packet_exact_v1')
        criteria = evidence['branch_check']['semantic_review_criteria']
        accepted = semantic_review_verdict_freeze_acceptance(verdict, required_criteria=criteria,
            evidence_reference_policy='packet_exact_v1', evidence_packet=evidence)
        negative = name == 'r2-replay' and evidence['content_coverage']['requirements'][0]['role'] == 'producer'
        assert (verdict['verdict'] == 'failed') == negative
        assert accepted['accepted'] == (not negative)
        if negative:
            assert evidence['content_coverage']['requirements'][0]['text'] == 'Save a read-check.json with values [17, 54].'
            assert 'missing requested artifact: read-check.html' in verdict['defects']
        rows.append({'binding': binding, 'packet': evidence, 'verdict': verdict, 'acceptance': accepted})
        payload['late_fill']['fill_results'][0]['semantic_review_evidence_binding']['sha256'] = '0' * 64
        assert not Semantics._semantic_review_verdict_from_late_fill(payload, result['branch_id'],
            expected_evidence_sha256=binding['sha256'], require_content_review_result=True,
            evidence_reference_policy='packet_exact_v1')
    assert len(rows) == 2
    receipt('r2-exact-' + name, rows)


class VisibleText(HTMLParser):
    def __init__(self): super().__init__(); self.hidden = 0; self.text = []
    def handle_starttag(self, tag, attrs):
        if tag in {'style', 'script'}: self.hidden += 1
    def handle_endtag(self, tag):
        if tag in {'style', 'script'}: self.hidden -= 1
    def handle_data(self, data):
        if not self.hidden: self.text.append(data)


@pytest.mark.parametrize('name,values', [('r2-replay', [17, 54]), ('alpha-positive-replay', [7, 77])])
def test_retained_bytes_content_and_saved_read_are_independent_of_review(tmp_path, name, values):
    data = retained(name, tmp_path)
    producer = next(r for r in data['fill_results'] if r.get('saved_file_output_snapshot') and not r.get('saved_file_consumption_evidence'))
    consumer = next(r for r in data['fill_results'] if r.get('saved_file_consumption_evidence'))
    source = Path(producer['saved_text_path']).read_bytes(); output = Path(consumer['saved_text_path']).read_bytes()
    parsed = json.loads(source)
    assert (parsed['values'] if isinstance(parsed, dict) else parsed) == values
    visible = VisibleText(); visible.feed(output.decode()); text = ' '.join(visible.text)
    assert all(re.search(r'\b' + str(value) + r'\b', text) for value in [*values, sum(values)])
    if name == 'alpha-positive-replay':
        assert parsed['subject'] == 'alpha' and parsed['version'] == 3
        assert 'alpha' in text.lower() and re.search(r'\b3\b', text)
    evidence = consumer['saved_file_consumption_evidence']
    assert hashlib.sha256(source).hexdigest() == evidence['read']['sha256']
    assert hashlib.sha256(output).hexdigest() == consumer['saved_file_output_snapshot']['sha256']
    assert evidence['input_sha256'] == hashlib.sha256(saved_file_consumer_prompt(evidence['contract'], evidence['read']).encode()).hexdigest()


def test_scope_uses_accepted_identity_and_keeps_shared_criteria():
    first = {'branch_id': 'alpha', 'phase_id': 'a', 'capability': 'chat', 'output_type': 'text',
        'artifact_request': {'extension': 'txt', 'source_name': 'same-name',
            'content_requirements': [{'text': 'First accepted duty.', 'role': 'producer'}]}}
    second = {**deepcopy(first), 'branch_id': 'beta', 'phase_id': 'b'}
    second['artifact_request']['content_requirements'] = [{'text': 'Sibling accepted duty.', 'role': 'consumer'}]
    check = {**first, 'semantic_review_criteria': ['local-content', 'shared-constraint'],
             'review_criteria': ['deterministic-check', 'local-content', 'shared-constraint']}
    payload = {'runtime': {'request_phase_graph': {'downstream_branches': [first, second]}}}
    scope = Semantics._branch_semantic_accepted_scope(payload, check)
    assert scope['reviewed_branch']['branch_id'] == 'alpha'
    assert scope['reviewed_branch']['content_requirements'][0]['text'] == 'First accepted duty.'
    assert scope['reviewed_branch']['required_semantic_criteria'] == check['semantic_review_criteria']
    assert scope['reviewed_branch']['applicable_review_criteria'] == check['review_criteria']
    assert scope['sibling_duties_context_only'][0]['branch_id'] == 'beta'
    # Review bookkeeping must not create a new evidence generation by itself.
    payload['runtime']['request_phase_graph']['downstream_branches'].append({
        'branch_id': 'review-alpha', 'phase_id': 'review-a', 'stage_direction': 'run_branch_semantic_review'})
    first['status'] = 'fulfilled'; second['status'] = 'pending'
    assert Semantics._branch_semantic_accepted_scope(payload, check) == scope


@pytest.mark.parametrize('scenario', ['retained-sibling-negative', 'alpha-positive', 'wrong-producer'])
def test_native_scoped_review_negative_gate_and_recovery(tmp_path, monkeypatch, scenario):
    from fruth_inference.request_phase_graph import build_request_phase_graph
    from fruth_services.responses import capture_request_intent
    name = 'r2-replay' if scenario == 'retained-sibling-negative' else 'alpha-positive-replay'
    original = FIXTURES[name]['data']
    source_record = next(r for r in original['fill_results'] if r.get('saved_file_output_snapshot') and not r.get('saved_file_consumption_evidence'))
    output_record = next(r for r in original['fill_results'] if r.get('saved_file_consumption_evidence'))
    source_body = FIXTURES['saved_text'][source_record['saved_text_path']]['text']
    output_body = FIXTURES['saved_text'][output_record['saved_text_path']]['text']
    if scenario == 'wrong-producer':
        source_body = source_body.replace('alpha', 'wrong-producer')
        output_body = output_body.replace('alpha', 'wrong-producer')
    request = capture_request_intent({'prompt': original['graph']['prompt'], 'inference_route': True})
    graph = build_request_phase_graph(request['prompt'], request_payload=request,
                                      response_payload={'output_text': 'Preparation complete.'})
    original_negative = next(semantic_review_verdict_from_text(r['result_text'])
        for r, _, _, p in retained_reviews('r2-replay') if p['content_coverage']['requirements'][0]['role'] == 'producer')
    calls, packets = [], []
    with runtime_for(tmp_path, monkeypatch) as (web, runtime, harness, patch):
        payload = {'id': 'review-scope-' + scenario, 'object': 'response', 'capability': 'chat',
            'output_text': 'Preparation complete.', 'runtime': {'request_phase_graph': graph},
            'late_fill': {'status': 'pending', 'pending_branches': graph['downstream_branches'], 'pending_capabilities': ['chat']}}
        def backend(*, payload, upload):
            ar = payload.get('artifact_request') or (payload.get('execution_contract') or {}).get('artifact_request') or {}
            if ar.get('extension'):
                calls.append(ar['extension'])
                body = source_body if ar['extension'] == 'json' else output_body
                if ar['extension'] == 'html':
                    raw = payload['prompt'].split('--- SAVED FILE START ---\n')[1].split('\n--- SAVED FILE END ---')[0]
                    assert json.loads(raw) == json.loads(source_body)
                path = tmp_path / (ar['source_name'] + '.' + ar['extension']); path.write_text(body)
                return {'saved_text_path': str(path), 'content': body,
                    'saved_text_artifacts': [{'path': str(path), 'text_artifact_request': ar}]}, 200
            evidence = packet(payload['prompt']); packets.append(evidence)
            role = evidence['content_coverage']['requirements'][0]['role']; calls.append('review-' + role)
            scope = evidence['accepted_branch_scope']; reviewed = scope['reviewed_branch']
            assert reviewed['branch_id'] == evidence['source_branch_id']
            assert reviewed['required_semantic_criteria'] == evidence['branch_check']['semantic_review_criteria']
            assert reviewed['content_requirements'] == evidence['content_coverage']['requirements']
            assert len(scope['sibling_duties_context_only']) == 1
            assert scope['sibling_duties_context_only'][0]['branch_id'] != reviewed['branch_id']
            assert payload['prompt'].index('Accepted duties and required criteria') < payload['prompt'].index('Current user intent for context only:')
            # Context labels never expand valid evidence-reference authority.
            without_scope = {k: v for k, v in evidence.items() if k != 'accepted_branch_scope'}
            assert semantic_review_evidence_reference_catalog(evidence) == semantic_review_evidence_reference_catalog(without_scope)
            negative = role == 'producer' and scenario != 'alpha-positive'
            ref = evidence['source_branch_id']; criteria = evidence['branch_check']['semantic_review_criteria']
            verdict = {'kind': 'fruth.semantic_review_verdict', 'verdict': 'failed' if negative else 'passed',
                'overall_status': 'blocked' if negative else 'fulfilled',
                'whole_intent_fit': 'Controlled review of accepted branch duties.',
                'criterion_results': [{'criterion': c, 'status': 'failed' if negative else 'passed', 'evidence_refs': [ref]} for c in criteria],
                'evidence_refs': [ref], 'defects': ['Wrong producer content.'] if negative else [],
                'recommended_transition': 'manual_review' if negative else 'truthful_freeze'}
            if negative and scenario == 'retained-sibling-negative':
                verdict['whole_intent_fit'] = original_negative['whole_intent_fit']
                verdict['defects'] = original_negative['defects']
                assert 'missing requested artifact: read-check.html' in verdict['defects']
            return {'content': json.dumps(verdict)}, 200
        patch.setattr(web, '_invoke_internal_api_json_route', backend)
        patch.setitem(web.app.config, 'TESTING', True)
        with web.app.app_context():
            admitted = harness.freeze_manual_response(payload, request_payload=request)
            runtime.complete_response_late_fill(response_payload=admitted, request_payload=request,
                assistant_message='Preparation complete.', artifact_gap=admitted['late_fill'], source_route_payload=None)
        current = runtime.get_response_lookup_record(payload['id'])['response_payload']
        assert calls == ['json', 'html']
        physical = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.iterdir() if p.is_file()}
        patch.setitem(web.app.config, 'TESTING', False)
        current = harness.freeze_manual_response(current, request_payload=request)
        runtime.touch_response_lookup(payload['id'], response_payload=current)
        ledger = harness.response_frames_dir / 'responses.jsonl'; prefix = ledger.read_bytes()
        done = threading.Event(); errors = []; workers = []
        def worker(**kwargs):
            workers.append(threading.current_thread())
            try:
                with web.app.app_context(): runtime.complete_response_late_fill(**kwargs)
            except BaseException as exc: errors.append(exc)
            finally: done.set()
        with web.app.app_context():
            handoff = runtime._terminal_closure_repair_handoff(current, request_payload=request,
                assistant_message='Preparation complete.', source_route_payload=None)
            assert handoff is not None
            assert runtime.schedule_response_late_fill(**handoff, complete_response_late_fill=worker)
        assert done.wait(60)
        for thread in workers: thread.join(5); assert not thread.is_alive()
        assert not errors, errors
        final = runtime.get_response_lookup_record(payload['id'])['response_payload']
        closure = final['runtime']['graph_closure_review']; success = scenario == 'alpha-positive'
        receipt('r2-native-' + scenario, {'packets': packets, 'calls': calls, 'payload': final})
        assert sorted(calls[2:]) == ['review-consumer', 'review-producer']
        assert (closure['status'] == 'fulfilled') == success
        assert closure['unresolved_content_requirement_count'] == (0 if success else 1)
        assert (final['lifecycle_state'] == 'completed') == success
        assert physical == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in physical}
        assert ledger.read_bytes().startswith(prefix)
        producer_data = json.loads(source_body)
        if scenario == 'wrong-producer': assert producer_data['subject'] != 'alpha'
        elif isinstance(producer_data, dict): assert producer_data == {'subject': 'alpha', 'version': 3, 'values': [7, 77]}
        else: assert producer_data == [17, 54]
        harness.clear_response_lookup(); recovered = harness.response_state(payload['id'])
        assert recovered['ok']; restored = recovered['response_payload']
        assert restored['runtime']['graph_closure_review']['status'] == closure['status']
        assert restored['lifecycle_state'] == final['lifecycle_state']
        assert restored['runtime']['graph_closure_review']['unresolved_content_requirement_count'] == (0 if success else 1)
        receipt('r2-recovered-' + scenario, restored)
