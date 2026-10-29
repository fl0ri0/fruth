"""R1 delivery coverage over retained reports/images; no visual-truth claim."""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import threading

import pytest

from fruth_inference.request_phase_graph import build_request_phase_graph
from fruth_services.artifact_contracts import (
    assemble_separate_image_reports, render_separate_image_reports, separate_image_report_contract,
)
from fruth_services.responses import capture_request_intent
from tests.test_saved_read_syntax_repair import FIXTURES, receipt, runtime_for

IMAGES = json.loads(Path(__file__).with_name('reference_image_bytes.json').read_text())


def setup_reports(root, name='r1-replay', marker=True):
    data = deepcopy(FIXTURES[name]['data'])
    replacements = {}
    for result in data['fill_results']:
        old = result.get('saved_image_path')
        if old:
            item = IMAGES[old]; path = root / Path(old).name
            path.write_bytes(base64.b64decode(item['base64']))
            assert hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256']
            replacements[old] = str(path)
    def rebind(value):
        if isinstance(value, dict): return {k: rebind(v) for k, v in value.items()}
        if isinstance(value, list): return [rebind(v) for v in value]
        if isinstance(value, str):
            for old, new in replacements.items(): value = value.replace(old, new)
        return value
    data = rebind(data)
    request = capture_request_intent({'prompt': data['graph']['prompt'], 'inference_route': True})
    graph = build_request_phase_graph(request['prompt'], request_payload=request,
                                     response_payload={'output_text': 'Preparation complete.'})
    terminal = next(b for b in graph['downstream_branches'] if separate_image_report_contract(b))
    sources = deepcopy(data['fill_results'][:-1])
    analyses = [r for r in sources if r['capability'] == 'vision_analysis']
    if not marker:
        for report in analyses: report['result_text'] = report['result_text'].replace('</think>', '')
    elif not any('</think>' in r['result_text'] for r in analyses):
        analyses[0]['result_text'] = '</think>\n' + analyses[0]['result_text']
    payload = {'id': data['provenance']['response_id'], 'object': 'response', 'capability': 'chat',
        'output_text': 'Preparation complete.', 'runtime': {'request_phase_graph': graph},
        'late_fill': {'status': 'pending', 'fill_results': sources,
            'completed_branches': [{**r, 'status': 'fulfilled'} for r in sources],
            'pending_branches': [deepcopy(terminal)], 'pending_capabilities': ['chat']}}
    return request, payload, terminal, data


def prepare(runtime, request, payload, branch):
    spec = runtime.build_late_fill_materialization_branch_spec(branch=branch, artifact_gap={},
        current_payload=payload, request_payload=request, assistant_message='Preparation complete.',
        source_route_payload=None, failed_instance_id=None)
    assert spec
    return runtime.prepare_late_fill_branch_plan(**spec['prepare_args'])


@pytest.mark.parametrize('name', ['r1-replay', 'r1-positive-replay'])
@pytest.mark.parametrize('marker', [True, False])
def test_every_report_is_delivered_without_synthesis_omission(tmp_path, monkeypatch, name, marker):
    request, payload, terminal, data = setup_reports(tmp_path, name, marker)
    with runtime_for(tmp_path, monkeypatch) as (web, runtime, harness, patch):
        patch.setattr(web, '_invoke_internal_api_json_route', lambda **kw: pytest.fail('delivery called a model'))
        # The retained incomplete synthesis/complete echo are controlled legacy
        # results, never source evidence for the corrected deterministic delivery.
        plan = prepare(runtime, request, payload, terminal)
        result = runtime.execute_prepared_late_fill_branch(plan)['infer_result']
        expected = assemble_separate_image_reports(terminal, payload, runtime.resolve_saved_file_input_path)
        assert result['result_text'] == render_separate_image_reports(expected)
        assert len(result['report_delivery_evidence']['contributions']) == 3
        assert len({c['source_branch_id'] for c in expected['contributions']}) == 3
        for contribution in expected['contributions']:
            assert result['result_text'].count(contribution['report_text']) == 1
        subjects = ['capybara', 'raccoon', 'lion'] if name == 'r1-replay' else ['capybara', 'squirrel', 'sloth']
        assert all(word in result['result_text'].lower() for word in subjects)
        record = {**terminal, **result}
        payload['late_fill']['fill_results'].append(record)
        payload['late_fill'].update(status='completed', pending_branches=[], pending_capabilities=[],
            completed_branches=payload['late_fill']['completed_branches'] + [{**record, 'status': 'fulfilled'}])
        closure = web._RESPONSE_SEMANTICS_RUNTIME.build_graph_closure_review(result['result_text'],
            request_payload=request, artifact_payload=payload)
        assert closure['status'] == 'fulfilled', closure
        receipt(f'r1-delivery-{name}-{marker}', {'source_fixture_sha256': FIXTURES[name]['sha256'],
            'result': result, 'closure': closure, 'subjects': subjects})


def test_retained_incomplete_synthesis_cannot_close_new_delivery_contract(tmp_path, monkeypatch):
    request, payload, terminal, data = setup_reports(tmp_path)
    old = data['fill_results'][-1]
    assert 'capybara' not in old['result_text'].lower()
    payload['late_fill']['fill_results'].append(old)
    payload['late_fill'].update(status='completed', pending_branches=[], pending_capabilities=[],
        completed_branches=payload['late_fill']['completed_branches'] + [{**terminal, 'status': 'fulfilled'}])
    with runtime_for(tmp_path, monkeypatch) as (web, runtime, harness, patch):
        closure = web._RESPONSE_SEMANTICS_RUNTIME.build_graph_closure_review(old['result_text'],
            request_payload=request, artifact_payload=payload)
        assert closure['status'] != 'fulfilled'
        assert any(c.get('evidence') == 'structured_dependency_join_contract_unmet' for c in closure['checks'])
        receipt('r1-retained-omission-rejected', closure)


@pytest.mark.parametrize('fault', ['omission', 'duplicate', 'substitution', 'text_omission'])
def test_incomplete_or_misbound_delivery_cannot_fulfill_closure(tmp_path, monkeypatch, fault):
    request, payload, terminal, _ = setup_reports(tmp_path)
    with runtime_for(tmp_path, monkeypatch) as (web, runtime, harness, patch):
        result = runtime.execute_prepared_late_fill_branch(prepare(runtime, request, payload, terminal))['infer_result']
        contributions = result['report_delivery_evidence']['contributions']
        if fault == 'omission': contributions.pop(0)
        elif fault == 'duplicate': contributions.append(deepcopy(contributions[0]))
        elif fault == 'substitution': contributions[0] = deepcopy(contributions[1])
        elif fault == 'text_omission': result['result_text'] = 'Only reports 2 and 3.'
        record = {**terminal, **result}
        payload['late_fill']['fill_results'].append(record)
        payload['late_fill'].update(status='completed', pending_branches=[], pending_capabilities=[],
            completed_branches=payload['late_fill']['completed_branches'] + [{**terminal, 'status': 'fulfilled'}])
        closure = web._RESPONSE_SEMANTICS_RUNTIME.build_graph_closure_review(result['result_text'],
            request_payload=request, artifact_payload=payload)
        assert closure['status'] != 'fulfilled'
        assert any(c.get('evidence') == 'structured_dependency_join_contract_unmet' for c in closure['checks'])


@pytest.mark.parametrize('fault', ['missing', 'duplicate', 'foreign', 'substitution', 'vision_binding', 'unavailable_image'])
def test_missing_or_foreign_sources_never_prepare(tmp_path, monkeypatch, fault):
    request, payload, terminal, _ = setup_reports(tmp_path)
    results = payload['late_fill']['fill_results']
    analyses = [r for r in results if r['capability'] == 'vision_analysis']
    if fault == 'missing': results.remove(analyses[0])
    elif fault == 'duplicate': results.append(deepcopy(analyses[0]))
    elif fault == 'foreign': analyses[0]['branch_id'] = 'foreign'
    elif fault == 'substitution': analyses[0]['vision_input_evidence'] = deepcopy(analyses[1]['vision_input_evidence'])
    elif fault == 'vision_binding': analyses[0]['vision_input_evidence']['image_sha256'] = '0' * 64
    elif fault == 'unavailable_image': next(r for r in results if r['capability'] == 'image_generation')['artifacts'][0]['availability'] = 'purged'
    with runtime_for(tmp_path, monkeypatch) as (web, runtime, harness, patch):
        error = runtime.repair_branch_execution_error(terminal, current_payload=payload)
        assert error and error['stage'] == 'dependency_gate'
        assert runtime.branch_dependency_payload(terminal, current_payload=payload).get('materialization_blocked')


@pytest.mark.parametrize('fault', ['omission', 'duplicate', 'substitution', 'prepared_text', 'source_text', 'image', 'identity'])
def test_prepared_delivery_requires_current_exact_contributions(tmp_path, monkeypatch, fault):
    request, payload, terminal, _ = setup_reports(tmp_path)
    with runtime_for(tmp_path, monkeypatch) as (web, runtime, harness, patch):
        plan = prepare(runtime, request, payload, terminal)
        contributions = plan['report_delivery_evidence']['contributions']
        if fault == 'omission': contributions.pop(0)
        elif fault == 'duplicate': contributions.append(deepcopy(contributions[0]))
        elif fault == 'substitution': contributions[0] = deepcopy(contributions[1])
        elif fault == 'prepared_text': plan['infer_payload']['prompt'] = 'Only report 2 and 3.'
        elif fault == 'source_text':
            next(r for r in payload['late_fill']['fill_results'] if r['capability'] == 'vision_analysis')['result_text'] += '\nChanged'
        elif fault == 'image': Path(contributions[0]['path']).write_bytes(b'changed')
        elif fault == 'identity':
            result = next(r for r in payload['late_fill']['fill_results'] if r['capability'] == 'image_generation')
            result['artifact_ref'] = result['artifacts'][0]['artifact_ref'] = 'artifact:foreign'
        patch.setattr(web, '_invoke_internal_api_json_route', lambda **kw: pytest.fail('invalid delivery called a provider'))
        with pytest.raises(ValueError, match='separate_image_reports_'):
            runtime.execute_prepared_late_fill_branch(plan)


@pytest.mark.parametrize('suffix', [' Then compare the three images.', ' Write a poem about them.',
    ' Translate the descriptions into French.', ' Which image is funniest?', ' Summarize the reports in one sentence.'])
def test_comparison_and_transformation_requests_keep_their_execution(suffix):
    prompt = FIXTURES['r1-replay']['data']['graph']['prompt'] + suffix
    graph = build_request_phase_graph(prompt, response_payload={'output_text': 'Preparation complete.'})
    assert not any(separate_image_report_contract(b) for b in graph['downstream_branches'])


@pytest.mark.parametrize('suffix', [' Then compare the three images.', ' Translate the descriptions into French.'])
def test_distinct_transformation_reaches_ordinary_transport(tmp_path, monkeypatch, suffix):
    request, payload, _, _ = setup_reports(tmp_path)
    request = capture_request_intent({'prompt': request['prompt'] + suffix, 'inference_route': True})
    graph = build_request_phase_graph(request['prompt'], request_payload=request,
                                     response_payload={'output_text': 'Preparation complete.'})
    terminal = next(b for b in graph['downstream_branches'] if b.get('role') == 'post_artifact_text_follow_up')
    payload['runtime']['request_phase_graph'] = graph
    payload['late_fill']['pending_branches'] = [terminal]
    with runtime_for(tmp_path, monkeypatch) as (web, runtime, harness, patch):
        calls = []
        def backend(**kwargs):
            calls.append(kwargs)
            return {'content': 'Controlled requested transformation.'}, 200
        patch.setattr(web, '_invoke_internal_api_json_route', backend)
        result = runtime.execute_prepared_late_fill_branch(prepare(runtime, request, payload, terminal))['infer_result']
        assert len(calls) == 1
        assert result['content'] == 'Controlled requested transformation.'
        assert not result.get('report_delivery_evidence')


@pytest.mark.parametrize('name', ['r1-replay', 'r1-positive-replay'])
def test_native_delivery_public_output_and_durable_recovery(tmp_path, monkeypatch, name):
    request, payload, terminal, _ = setup_reports(tmp_path, name)
    with runtime_for(tmp_path, monkeypatch) as (web, runtime, harness, patch):
        patch.setattr(web, '_invoke_internal_api_json_route', lambda **kw: pytest.fail('delivery invoked model transport'))
        patch.setitem(web.app.config, 'TESTING', False)
        expected = assemble_separate_image_reports(terminal, payload, runtime.resolve_saved_file_input_path)
        admitted = harness.freeze_manual_response(payload, request_payload=request)
        runtime.touch_response_lookup(payload['id'], response_payload=admitted)
        done = threading.Event(); workers = []; errors = []
        def worker(**kwargs):
            workers.append(threading.current_thread())
            try:
                with web.app.app_context(): runtime.complete_response_late_fill(**kwargs)
            except BaseException as exc: errors.append(exc)
            finally: done.set()
        with web.app.app_context():
            assert runtime.schedule_response_late_fill(response_payload=admitted, request_payload=request,
                assistant_message='Preparation complete.', artifact_gap=admitted['late_fill'], source_route_payload=None,
                complete_response_late_fill=worker)
        assert done.wait(60)
        for thread in workers: thread.join(5); assert not thread.is_alive()
        assert not errors, errors
        final = runtime.get_response_lookup_record(payload['id'])['response_payload']
        receipt('r1-native-' + name, final)
        assert final['runtime']['graph_closure_review']['status'] == 'fulfilled'
        assert final['lifecycle_state'] == 'completed'
        harness.clear_response_lookup()
        recovered = harness.response_state(payload['id'])
        assert recovered['ok']
        restored = recovered['response_payload']
        assert restored['runtime']['graph_closure_review']['status'] == 'fulfilled'
        assert restored['lifecycle_state'] == 'completed'
        result = next(r for r in restored['late_fill']['fill_results'] if r['branch_id'] == terminal['branch_id'])
        assert result['report_delivery_evidence'] == expected
        assert result['result_text'] == render_separate_image_reports(expected)
        public = restored.get('output_text', '')
        assert all(c['report_text'] in public for c in expected['contributions'])
        public_output = next(o for o in restored['outputs'] if o.get('branch_id') == terminal['branch_id'])
        assert public_output['status'] == 'fulfilled'
        assert public_output['value'] == render_separate_image_reports(expected)
        receipt('r1-recovered-' + name, restored)
