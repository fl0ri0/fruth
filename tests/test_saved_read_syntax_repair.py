"""Retained R3: real saved-read repair, exact dispatch gates and durable closure."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import threading

import pytest

FIXTURES = json.loads(Path(__file__).with_name('reference_improvement_witnesses.json').read_text())


def retained(name, root):
    data = deepcopy(FIXTURES[name]['data'])
    replacements = {}
    for old, item in FIXTURES['saved_text'].items():
        if old in json.dumps(data):
            target = root / Path(old).name
            target.write_text(item['text'])
            assert hashlib.sha256(target.read_bytes()).hexdigest() == item['sha256']
            replacements[old] = str(target)
    def visit(value):
        if isinstance(value, dict):
            return {k: visit(v) for k, v in value.items()}
        if isinstance(value, list):
            return [visit(v) for v in value]
        if isinstance(value, str):
            for old, new in replacements.items():
                value = value.replace(old, new)
        return value
    return visit(data)


def receipt(name, data):
    path = Path(os.environ['FRUTH_A1_EVIDENCE_DIR']) / (name + '.json')
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str) + '\n')


@contextmanager
def runtime_for(root, monkeypatch):
    import fruth_webserver as web
    import fruth_server.late_fill_runtime as late_module
    from tests.fake_backends import FakeBackendHarness
    from tests.test_saved_file_consumer_path import owner_for
    with FakeBackendHarness(root=root / 'runtime') as harness, monkeypatch.context() as patch:
        harness.instances['chat']['runtime_status'].update(process_alive=True, port_listening=True)
        runtime = web._LATE_FILL_RUNTIME
        resolver = owner_for(root).resolve_saved_file_input_path
        patch.setattr(runtime, 'resolve_saved_file_input_path', resolver)
        patch.setattr(web, '_resolve_saved_viewable_artifact_path', resolver)
        patch.setattr(web, 'ARTIFACT_OUTPUTS_DOCUMENTS_DIR', root)
        patch.setattr(late_module, 'ARTIFACT_OUTPUTS_DOCUMENTS_DIR', root)
        yield web, runtime, harness, patch


def repair_plan(root, runtime):
    data = retained('r3-replay', root)
    graph = data['graph']
    consumer = next(b for b in graph['downstream_branches'] if b.get('dependency_contract'))
    contract = consumer['artifact_request']['saved_file_dependency']
    producer = next(r for r in data['fill_results'] if r['branch_id'] == contract['producer_branch_id'])
    payload = {'id': data['provenance']['response_id'], 'output_text': 'Preparation complete.',
               'runtime': {'request_phase_graph': graph},
               'late_fill': {'fill_results': [producer], 'completed_branches': [deepcopy(producer)]}}
    target = Path(data['failed_branches'][0]['artifact_request']['target_path'])
    error = runtime._text_artifact_saved_payload_error(str(target), extension='html')
    assert error['code'] == 'TEXT_ARTIFACT_SYNTAX_SANITY_FAILED'
    attempt = {'stage': 'text_artifact_saved_truth_gate', 'capability': 'chat', 'instance_id': 'offline-bad'}
    context = runtime.late_fill_recovery_context(error=runtime.normalize_late_fill_error_payload(error), attempt=attempt)
    state = runtime.late_fill_recovery_state(consumer, recovery_context=context, attempt=attempt,
        status='candidate', trigger='text_artifact_saved_truth_gate')
    retry = runtime.build_auto_executable_repair_retry_branch(consumer, recovery_context=context,
        recovery_state=state, attempt=attempt, trigger='auto_executable_repair_retry')
    assert retry and retry['artifact_request']['saved_file_dependency'] == contract
    assert retry['artifact_request']['content_requirements'] == consumer['artifact_request']['content_requirements']
    assert runtime.repair_branch_execution_error(retry, current_payload=payload) is None
    spec = runtime.build_late_fill_materialization_branch_spec(branch=retry, artifact_gap={},
        current_payload=payload, request_payload={'prompt': graph['prompt'], 'inference_route': True},
        assistant_message='Preparation complete.', source_route_payload=None, failed_instance_id=None)
    assert spec
    plan = runtime.prepare_late_fill_branch_plan(**spec['prepare_args'])
    return data, consumer, payload, retry, target, plan


def test_retained_repair_dispatch_and_fresh_consumption(tmp_path, monkeypatch):
    from fruth_services.artifact_contracts import saved_file_consumption_artifact_issue, saved_file_consumer_prompt
    with runtime_for(tmp_path, monkeypatch) as (web, runtime, harness, patch):
        data, consumer, payload, retry, target, plan = repair_plan(tmp_path, runtime)
        before = target.read_text()
        calls = []
        def backend(*, payload, upload):
            calls.append(deepcopy(payload))
            assert 'Deterministic syntax sanity issues:' in payload['prompt']
            assert before in payload['prompt']
            raw = payload['prompt'].split('--- SAVED FILE START ---\n')[1].split('\n--- SAVED FILE END ---')[0]
            assert json.loads(raw) == [17, 146]
            body = before.replace('<meta charset="UTF="UTF-8">', '<meta charset="UTF-8">')
            target.write_text(body)
            return {'saved_text_path': str(target), 'content': body, 'saved_text_artifacts': [
                {'path': str(target), 'text_artifact_request': payload['artifact_request']}]}, 200
        patch.setattr(web, '_invoke_internal_api_json_route', backend)
        result = runtime.execute_prepared_late_fill_branch(plan)['infer_result']
        assert len(calls) == 1
        record = runtime.attach_late_fill_result_artifact_identity({**retry, **result}, payload, result, capability='chat')
        payload['late_fill']['fill_results'].append(record)
        assert runtime.saved_file_consumption_error(consumer, record, current_payload=payload) is None
        assert saved_file_consumption_artifact_issue(consumer, payload, runtime.resolve_saved_file_input_path) == ''
        assert runtime._text_artifact_saved_payload_error(str(target), extension='html') is None
        assert target.read_text() == before.replace('<meta charset="UTF="UTF-8">', '<meta charset="UTF-8">')
        for value in (17, 146, 163):
            assert f'<td>{value}</td>' in target.read_text()
        evidence = record['saved_file_consumption_evidence']
        ordinary_prompt = saved_file_consumer_prompt(evidence['contract'], evidence['read'])
        assert hashlib.sha256(ordinary_prompt.encode()).hexdigest() != evidence['input_sha256']
        receipt('r3-dispatch', {'calls': calls, 'result': record, 'original_contract': consumer['artifact_request'],
                               'syntax_clear': True, 'values': [17, 146], 'sum': 163})
        bad = deepcopy(record)
        bad['saved_file_consumption_evidence'].pop('syntax_repair')
        bad['saved_file_consumption_evidence']['input_sha256'] = hashlib.sha256(ordinary_prompt.encode()).hexdigest()
        assert runtime.saved_file_consumption_error(consumer, bad, current_payload=payload)


@pytest.mark.parametrize('fault', ['source', 'source_identity', 'target', 'same_bytes_new_identity',
    'target_path', 'foreign_target', 'unauthorized_target', 'consumer', 'phase', 'prompt', 'output_request', 'packet', 'authority'])
def test_repair_dispatch_rejects_changed_or_foreign_inputs(tmp_path, monkeypatch, fault):
    with runtime_for(tmp_path, monkeypatch) as (web, runtime, harness, patch):
        _, consumer, payload, retry, target, plan = repair_plan(tmp_path, runtime)
        execution = plan['execution_contract']
        read = execution['saved_file_read_evidence']
        repair = execution['artifact_request']['saved_file_syntax_repair']
        if fault == 'source': Path(read['path']).write_text('[1,2]')
        elif fault == 'source_identity': payload['late_fill']['fill_results'][0]['artifacts'][0]['artifact_ref'] = 'artifact:foreign'
        elif fault == 'target': target.write_text(target.read_text() + '\n<!--changed-->')
        elif fault == 'same_bytes_new_identity':
            other = target.with_suffix('.new'); other.write_bytes(target.read_bytes()); other.replace(target)
        elif fault == 'target_path': execution['artifact_request']['target_path'] = str(tmp_path / 'sibling.html')
        elif fault == 'foreign_target': repair['target']['path'] = str(tmp_path / 'sibling.html')
        elif fault == 'unauthorized_target':
            resolver = runtime.resolve_saved_file_input_path
            patch.setattr(runtime, 'resolve_saved_file_input_path', lambda path: None if path == str(target) else resolver(path))
        elif fault == 'consumer': execution['branch_id'] = 'foreign'
        elif fault == 'phase': execution['phase_id'] = 'foreign'
        elif fault == 'prompt': plan['infer_payload']['prompt'] += '\nArbitrary input'
        elif fault == 'output_request': plan['infer_payload']['text_artifact_requests'][0]['target_path'] = str(tmp_path / 'sibling.html')
        elif fault == 'packet': repair['target']['sha256'] = '0' * 64
        elif fault == 'authority': execution['recovery_attempt']['trigger'] = 'ordinary_retry'
        patch.setattr(web, '_invoke_internal_api_json_route', lambda **kw: pytest.fail('invalid repair dispatched'))
        with pytest.raises(ValueError, match='saved_file_'):
            runtime.execute_prepared_late_fill_branch(plan)


def test_invalid_repair_remains_blocked_without_another_attempt(tmp_path, monkeypatch):
    with runtime_for(tmp_path, monkeypatch) as (web, runtime, harness, patch):
        _, _, payload, retry, target, plan = repair_plan(tmp_path, runtime)
        patch.setattr(web, '_invoke_internal_api_json_route', lambda **kw: ({'saved_text_path': str(target),
            'saved_text_artifacts': [{'path': str(target), 'text_artifact_request': retry['artifact_request']}]}, 200))
        result = runtime.execute_prepared_late_fill_branch(plan)['infer_result']
        _, error = runtime._ensure_required_text_artifact_saved_truth(retry, result, plan['effective_data'], payload)
        assert error['code'] == 'TEXT_ARTIFACT_SYNTAX_SANITY_FAILED'
        attempt = {'stage': 'text_artifact_saved_truth_gate', 'capability': 'chat'}
        context = runtime.late_fill_recovery_context(error=runtime.normalize_late_fill_error_payload(error), attempt=attempt)
        assert runtime.build_auto_executable_repair_retry_branch(retry, recovery_context=context,
            recovery_state=retry['recovery_state'], attempt=attempt, trigger='auto_executable_repair_retry') is None


def test_repair_cannot_authorize_the_producer_path_as_its_target(tmp_path, monkeypatch):
    from fruth_services.artifact_contracts import saved_file_syntax_repair_issue
    with runtime_for(tmp_path, monkeypatch) as (_, runtime, _, _):
        _, consumer, _, _, _, plan = repair_plan(tmp_path, runtime)
        repair = deepcopy(plan['execution_contract']['artifact_request']['saved_file_syntax_repair'])
        producer = plan['execution_contract']['saved_file_read_evidence']
        repair['target'] = deepcopy(producer)
        repair['target_request']['target_path'] = producer['path']
        assert saved_file_syntax_repair_issue(consumer['artifact_request']['saved_file_dependency'], repair) == 'saved_file_syntax_repair_target_mismatch'


def test_native_repair_reviews_publication_and_recovery(tmp_path, monkeypatch):
    from fruth_services.responses import capture_request_intent
    from fruth_inference.request_phase_graph import build_request_phase_graph
    from tests.test_saved_file_consumer_path import saved
    original = FIXTURES['r3-replay']['data']
    request = capture_request_intent({'prompt': original['graph']['prompt'], 'inference_route': True})
    graph = build_request_phase_graph(request['prompt'], request_payload=request,
                                      response_payload={'output_text': 'Preparation complete.'})
    bad_html = FIXTURES['saved_text'][original['failed_branches'][0]['artifact_request']['target_path']]['text']
    calls, reviews, dispatched = [], [], []
    with runtime_for(tmp_path, monkeypatch) as (web, runtime, harness, patch):
        execute = runtime.execute_prepared_late_fill_branch
        def trace(plan):
            result = execute(plan)
            dispatched.append(deepcopy(result['infer_result']))
            return result
        patch.setattr(runtime, 'execute_prepared_late_fill_branch', trace)
        payload = {'id': 'r3-native-corrected', 'object': 'response', 'capability': 'chat',
            'output_text': 'Preparation complete.', 'runtime': {'request_phase_graph': graph},
            'late_fill': {'status': 'pending', 'pending_branches': graph['downstream_branches'], 'pending_capabilities': ['chat']}}
        def backend(*, payload, upload):
            ar = payload.get('artifact_request') or (payload.get('execution_contract') or {}).get('artifact_request') or {}
            if not ar.get('extension'):
                packet = json.JSONDecoder().raw_decode(payload['prompt'].split('Branch runtime evidence:\n', 1)[1])[0]
                reviews.append(packet)
                calls.append('review-' + packet['content_coverage']['requirements'][0]['role'])
                criteria = packet['branch_check']['semantic_review_criteria']; ref = packet['source_branch_id']
                if packet['content_coverage']['requirements'][0]['role'] == 'consumer':
                    assert packet['artifact_refs'][0]['content_excerpt'] == bad_html.replace('<meta charset="UTF="UTF-8">', '<meta charset="UTF-8">')
                return {'content': json.dumps({'kind': 'fruth.semantic_review_verdict', 'verdict': 'passed',
                    'overall_status': 'fulfilled', 'whole_intent_fit': 'Controlled content review of current exact bytes.',
                    'criterion_results': [{'criterion': c, 'status': 'passed', 'evidence_refs': [ref]} for c in criteria],
                    'evidence_refs': [ref], 'defects': [], 'recommended_transition': 'truthful_freeze'})}, 200
            calls.append('repair' if ar.get('saved_file_syntax_repair') else ar['extension'])
            if ar['extension'] == 'json': body = '[17,146]'
            else:
                raw = payload['prompt'].split('--- SAVED FILE START ---\n')[1].split('\n--- SAVED FILE END ---')[0]
                assert json.loads(raw) == [17, 146]
                body = bad_html
                if ar.get('saved_file_syntax_repair'):
                    assert bad_html in payload['prompt']
                    body = body.replace('<meta charset="UTF="UTF-8">', '<meta charset="UTF-8">')
            if ar.get('target_path'):
                path = ar['target_path']; Path(path).write_text(body)
            else: path = saved(tmp_path, ar['source_name'], ar['extension'], body)
            return {'saved_text_path': path, 'content': body,
                    'saved_text_artifacts': [{'path': path, 'text_artifact_request': ar}]}, 200
        patch.setattr(web, '_invoke_internal_api_json_route', backend)
        patch.setitem(web.app.config, 'TESTING', True)
        with web.app.app_context():
            admitted = harness.freeze_manual_response(payload, request_payload=request)
            runtime.complete_response_late_fill(response_payload=admitted, request_payload=request,
                assistant_message='Preparation complete.', artifact_gap=admitted['late_fill'], source_route_payload=None)
        current = runtime.get_response_lookup_record(payload['id'])['response_payload']
        receipt('r3-native-before-reviews', {'calls': calls, 'payload': current})
        assert calls == ['json', 'html', 'repair']
        assert current['runtime']['graph_closure_review']['status'] != 'fulfilled'
        patch.setitem(web.app.config, 'TESTING', False)
        current = harness.freeze_manual_response(current, request_payload=request)
        runtime.touch_response_lookup(payload['id'], response_payload=current)
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
        assert not errors
        final = runtime.get_response_lookup_record(payload['id'])['response_payload']
        receipt('r3-native-final', {'calls': calls, 'reviews': reviews, 'payload': final})
        assert sorted(calls[3:]) == ['review-consumer', 'review-producer']
        assert final['runtime']['graph_closure_review']['status'] == 'fulfilled'
        assert final['lifecycle_state'] == 'completed'
        harness.clear_response_lookup()
        recovered = harness.response_state(payload['id'])
        assert recovered['ok']
        restored = recovered['response_payload']
        assert restored['runtime']['graph_closure_review']['status'] == 'fulfilled'
        assert restored['lifecycle_state'] == 'completed'
        from fruth_services.artifact_contracts import saved_file_consumption_artifact_issue
        consumer = next(b for b in graph['downstream_branches'] if b.get('dependency_contract'))
        assert saved_file_consumption_artifact_issue(consumer, restored, runtime.resolve_saved_file_input_path) == ''
        current_result = next(r for r in restored['late_fill']['fill_results'] if r['branch_id'] == consumer['branch_id'])
        old_result = next(r for r in dispatched if r.get('saved_file_consumption_evidence')
                          and not r['saved_file_consumption_evidence'].get('syntax_repair'))
        stale = deepcopy(current_result)
        stale['saved_file_consumption_evidence'] = old_result['saved_file_consumption_evidence']
        assert runtime.saved_file_consumption_error(consumer, stale, current_payload=restored)
        assert len([o for o in restored['outputs'] if o.get('type') in {'text', 'artifact'}]) >= 2
        receipt('r3-recovered', restored)
