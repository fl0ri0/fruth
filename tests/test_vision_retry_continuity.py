"""Generated-image retry keeps exact inputs, sibling evidence and dependent work."""
import copy
import json
from pathlib import Path

import pytest

from tests.test_vision_evidence_recovery import dispatch, fixture, GOOD_TEXT


REFUSAL = ('As Gemma 4, a large language model, I generate text only and do not '
           'have the capability to create or generate images, including funny animal selfies.')


def test_explicit_retry_preserves_results_and_resumes_dependent_join(tmp_path, monkeypatch):
    import fruth_webserver as web
    from tests.fake_backends import FakeBackendHarness
    from fruth_inference.request_phase_graph import build_request_phase_graph

    prompt = ('Create exactly three funny animal selfies. Then inspect each generated '
              'image separately and describe only what is actually visible. Finally summarize the inspections.')
    graph = build_request_phase_graph(prompt, response_payload={'output_text': 'Image prompts ready.'})
    branches = graph['downstream_branches']
    images = [b for b in branches if b['capability'] == 'image_generation']
    images = [{**b, 'phase_id': f'phase-{i + 2}', 'obligation_id': f'obligation-phase-{i + 2}'}
              for i, b in enumerate(images)]
    # Accepted planner topology, independent of the heuristic prompt parser.
    visions = [{
        'branch_id': f'branch-vision_analysis-{i + 1}', 'phase_id': f'phase-{i + 5}',
        'capability': 'vision_analysis', 'output_type': 'text', 'queue_index': i + 1,
        'depends_on': [image['phase_id']],
        'input_refs': [{'kind': 'phase_output', 'phase_id': image['phase_id'], 'role': 'dependency'}],
        'output_contract': {'required': True, 'output_type': 'text'},
    } for i, image in enumerate(images)]
    joins = [{'branch_id': 'branch-chat-1', 'phase_id': 'phase-8', 'capability': 'chat',
              'output_type': 'text', 'depends_on': [v['phase_id'] for v in visions],
              'stage_direction': 'write_text_after_artifact_generation',
              'content_payload_source': 'prior_artifact_result'}]
    graph = {'prompt': prompt, 'current_phase_id': 'phase-1', 'current_phase_capability': 'chat',
             'current_phase_resolution': 'graph_resolved',
             'downstream_branches': [*images, *visions, *joins],
             'phases': [{'phase_id': 'phase-1', 'capability': 'chat', 'status': 'fulfilled'},
                        *copy.deepcopy([*images, *visions, *joins])]}
    graph.update(json.loads(Path(__file__).with_name('fixtures').joinpath(
        'vision_retry_obligations.json').read_text()))
    graph['kind'] = 'fruth.request_phase_graph'
    assert len(images) == len(visions) == 3 and len(joins) == 1
    target = visions[1]
    with FakeBackendHarness() as harness, monkeypatch.context() as patch:
        runtime = web._LATE_FILL_RUNTIME
        patch.setenv('FRUTH_AUTO_EXECUTABLE_REPAIR_MAX_ATTEMPTS', '1')
        for instance in harness.instances.values():
            instance['runtime_status'].update(process_alive=True, port_listening=True)
        second = copy.deepcopy(harness.instances['vision_analysis'])
        second.update(instance_id='second-vision', model='second-vision-model')
        patch.setattr(runtime, 'load_running_instances', lambda: list(harness.instances.values()))
        patch.setattr(runtime, 'merge_instances_with_runtime_status', lambda entries, **kw: entries)
        resolver = lambda value: Path(value).resolve() if Path(value).resolve().is_relative_to(harness.root) else None
        patch.setattr(runtime, 'resolve_saved_file_input_path', resolver)
        patch.setattr(web, '_resolve_saved_viewable_artifact_path', resolver)
        patch.setitem(web.app.config, 'TESTING', True)
        producers = []
        for index, branch in enumerate(images):
            directory = harness.images_dir / str(index)
            directory.mkdir()
            _, _, _, image = fixture(directory)
            producers.append({**branch, 'status': 'fulfilled', 'saved_image_path': str(image)})
        image_bytes = {p['saved_image_path']: Path(p['saved_image_path']).read_bytes() for p in producers}
        payload = {'id': 'vision-explicit-retry', 'object': 'response', 'capability': 'chat',
                   'output_text': 'Image prompts ready.', 'runtime': {'request_phase_graph': graph},
                   'late_fill': {'status': 'pending', 'fill_results': copy.deepcopy(producers),
                                 'completed_branches': copy.deepcopy(producers),
                                 'pending_branches': [*visions, *joins]}}
        request = {'prompt': prompt, 'inference_route': True}
        calls = []
        retrying = False

        def backend(*, payload, upload):
            calls.append(copy.deepcopy(payload))
            assert payload['capability'] in {'vision_analysis', 'chat'}
            if payload['capability'] == 'vision_analysis':
                contract = payload['execution_contract']
                expected = next(p for p in producers if p['phase_id'] in contract['depends_on'])
                assert payload.get('file_path') == expected['saved_image_path']
                assert prompt not in payload['prompt']
                if contract['branch_id'] == target['branch_id'] and not retrying:
                    return {'error': '500 fixture vision failure'}, 500
                return dispatch(image_bytes[expected['saved_image_path']], GOOD_TEXT,
                                instance=payload['instance_id']), 200
            assert retrying and GOOD_TEXT in payload['prompt']
            return {'content': 'The three inspections are complete.'}, 200

        patch.setattr(web, '_invoke_internal_api_json_route', backend)
        with web.app.app_context():
            runtime.complete_response_late_fill(response_payload=payload, request_payload=request,
                assistant_message=payload['output_text'], artifact_gap={
                    'trigger': 'execution_planner_deferred_follow_up',
                    'pending_branches': [*visions, *joins], 'expected_capability': 'vision_analysis'},
                source_route_payload=None)
        failed = copy.deepcopy(runtime.get_response_lookup_record(payload['id'])['response_payload'])
        assert {b['branch_id'] for b in failed['late_fill']['failed_branches']} == {
            target['branch_id'], joins[0]['branch_id']}
        accepted = copy.deepcopy(failed['late_fill']['fill_results'])
        assert len(accepted) == 5
        # Persist the failed parent and recover through the same API used by the UI.
        patch.setitem(web.app.config, 'TESTING', False)
        harness.freeze_manual_response(failed, request_payload=request)
        parent = harness.response_frames_dir.joinpath('responses.jsonl').read_bytes()
        harness.clear_response_lookup()
        patch.setitem(web.app.config, 'TESTING', True)
        harness.instances['vision_alternative'] = second
        response = harness.client.post('/api/responses/' + payload['id'] + '/late_fill/retry',
                                       json={'branch_id': target['branch_id']})
        assert response.status_code == 202, response.get_json()
        queued = runtime.get_response_lookup_record(payload['id'])['response_payload']
        assert queued['late_fill'].get('fill_results') == accepted
        assert {b['branch_id'] for b in queued['late_fill']['pending_branches']} == {
            target['branch_id'], joins[0]['branch_id']}
        retrying = True
        before_retry = len(calls)
        with web.app.app_context():
            runtime.complete_response_late_fill(response_payload=queued,
                request_payload=web._request_payload_for_late_fill_retry(queued),
                assistant_message=queued['output_text'], artifact_gap=queued['late_fill'],
                source_route_payload=None)
        final = runtime.get_response_lookup_record(payload['id'])['response_payload']
        assert final['lifecycle_state'] == 'completed', {
            'failed': final['late_fill'].get('failed_branches'),
            'checks': final['late_fill'].get('materialization_contract_open_checks'),
            'calls': calls[before_retry:]}
        assert final['runtime']['graph_closure_review']['status'] == 'fulfilled'
        assert all(o['status'] == 'fulfilled' and not o.get('error_ref')
                   and not o.get('blocked_reason') for o in final['outputs'])
        assert len(calls) - before_retry == 2
        assert calls[before_retry]['instance_id'] == 'second-vision'
        assert all(r in final['late_fill']['fill_results'] for r in accepted)
        assert len(final['late_fill']['fill_results']) == 7
        assert all(Path(path).read_bytes() == data for path, data in image_bytes.items())
        patch.setitem(web.app.config, 'TESTING', False)
        harness.freeze_manual_response(final, request_payload=request)
        assert harness.response_frames_dir.joinpath('responses.jsonl').read_bytes().startswith(parent)
        harness.clear_response_lookup()
        recovered = harness.response_state(payload['id'])['response_payload']
        assert recovered['lifecycle_state'] == 'completed'
        assert all(r in recovered['late_fill']['fill_results'] for r in accepted)


def test_missing_generated_input_cannot_become_text_only_retry(tmp_path):
    owner, branch, payload, image = fixture(tmp_path)
    payload['late_fill']['fill_results'] = []
    result = {'content': REFUSAL, 'instance_id': 'vision-second'}
    error = owner.dependency_evidence_error_for_branch_result(branch, result, current_payload=payload)
    assert error and error['code'] == 'DEPENDENCY_CHAIN_REPAIR_REQUIRED'


@pytest.mark.parametrize('text,rejected', [
    (REFUSAL, True), ('I cannot generate images.', True),
    ('The sign reads "I cannot generate images" beside a cat.', False),
    ('I can describe this image: a cat holds a sign.', False),
])
def test_refusal_is_not_inspection_but_visible_text_is_valid(tmp_path, text, rejected):
    from tests.test_vision_evidence_recovery import failed_result
    owner, branch, payload, image = fixture(tmp_path)
    result = failed_result(owner, branch, payload, image, text)
    error = owner.dependency_evidence_error_for_branch_result(branch, result, current_payload=payload)
    assert bool(error) is rejected
    if rejected:
        assert error['code'] == 'VISION_DEPENDENCY_EVIDENCE_REJECTED'


@pytest.mark.parametrize('defect', ['missing', 'wrong_path', 'ambiguous', 'changed_digest'])
def test_prepared_vision_requires_its_own_saved_input(tmp_path, defect):
    owner, branch, payload, image = fixture(tmp_path)
    inputs = {'file_path': str(image)}
    if defect == 'missing': payload['late_fill']['fill_results'] = []
    elif defect == 'wrong_path':
        sibling = tmp_path / 'other.png'
        sibling.write_bytes(image.read_bytes())
        inputs['file_path'] = str(sibling)
    elif defect == 'ambiguous': payload['late_fill']['fill_results'] *= 2
    else:
        payload['late_fill']['fill_results'][0]['artifacts'] = [
            {'path': str(image), 'metadata': {'file_sha256': '0' * 64}}]
    with pytest.raises(ValueError, match='Vision dependency'):
        owner._prepared_vision_dependency(branch, payload, inputs, 'vision-second')


@pytest.mark.parametrize('control', [None, 'unrelated', 'executed', 'changed_edges',
    'duplicate', 'optional', 'external', 'cancelled', 'graph_cancelled', 'missing_graph'])
def test_dependent_retry_only_reconsiders_accepted_blocked_consumers(control):
    import fruth_webserver as web
    owner = web._LATE_FILL_RUNTIME
    retry = {'branch_id': 'vision', 'phase_id': 'phase-2', 'capability': 'vision_analysis'}
    first = {'branch_id': 'summary', 'phase_id': 'phase-3', 'capability': 'chat',
             'depends_on': ['phase-2'], 'output_contract': {'required': True, 'output_type': 'text'}}
    second = {**first, 'branch_id': 'followup', 'phase_id': 'phase-4', 'depends_on': ['phase-3']}
    graph = [copy.deepcopy(first), copy.deepcopy(second)]
    failures = [{**b, 'status': 'blocked', 'error': {
        'code': 'DEPENDENCY_CHAIN_REPAIR_REQUIRED', 'stage': 'dependency_gate',
        'failed_dependency_ids': b['depends_on']}} for b in (first, second)]
    if control == 'unrelated': failures[0]['error']['failed_dependency_ids'] = ['unrelated']
    elif control == 'executed': failures[0]['error']['stage'] = 'execute_prepared_branch'
    elif control == 'changed_edges': graph[0]['depends_on'] = ['unrelated']
    elif control == 'duplicate': graph.append(copy.deepcopy(first))
    elif control == 'optional': graph[0]['output_contract']['required'] = False
    elif control == 'external': failures[0]['needs_external_input'] = True
    elif control == 'cancelled': failures[0]['status'] = 'cancelled'
    elif control == 'graph_cancelled': graph[0]['status'] = 'cancelled'
    elif control == 'missing_graph': graph = []
    payload = {'runtime': {'request_phase_graph': {'downstream_branches': graph}},
               'late_fill': {'failed_branches': failures}}
    before = copy.deepcopy(payload)
    candidates = owner.retry_dependency_continuations(payload, [retry])
    assert payload == before
    assert [b['branch_id'] for b in candidates] == (['summary', 'followup'] if control is None else [])
    if candidates:
        assert candidates[0]['retry_dependency_failure'] == failures[0]['error']


@pytest.mark.parametrize('control', [None, 'marker_only', 'duplicate_result', 'foreign_phase',
    'failed', 'cancelled', 'pending', 'slot_cancelled', 'file_contract', 'empty'])
def test_inline_retry_slot_requires_exact_accepted_result(control):
    import fruth_webserver as web
    branch = {'branch_id': 'vision', 'phase_id': 'phase-2', 'capability': 'vision_analysis'}
    result = {**branch, 'result_text': GOOD_TEXT}
    late = {'completed_branches': [{**branch, 'status': 'fulfilled'}], 'fill_results': [result]}
    slot = {**branch, 'type': 'text', 'status': 'blocked', 'blocked_reason': 'old failure',
            'error_ref': {'code': 'BACKEND_ERROR'}}
    if control == 'marker_only': late['fill_results'] = []
    elif control == 'duplicate_result': late['fill_results'].append(copy.deepcopy(result))
    elif control == 'foreign_phase': result['phase_id'] = 'other'
    elif control in {'failed', 'cancelled', 'pending'}: late[control + '_branches'] = [branch]
    elif control == 'slot_cancelled': slot['status'] = 'cancelled'
    elif control == 'file_contract': branch['artifact_request'] = {'extension': 'txt', 'source_name': 'owed.txt'}
    elif control == 'empty': result['result_text'] = ''
    payload = {'runtime': {'request_phase_graph': {'downstream_branches': [branch]}},
               'late_fill': late, 'output_slots': [slot]}
    result = web._LATE_FILL_RUNTIME.reconcile_completed_inline_outputs(copy.deepcopy(payload))['output_slots'][0]
    if control is None:
        assert result['status'] == 'fulfilled' and result['value'] == GOOD_TEXT
        assert 'error_ref' not in result and 'blocked_reason' not in result
    else:
        assert result == slot


def test_state_transition_retains_evidence_without_aliasing_or_ignoring_explicit_replacement():
    import fruth_webserver as web
    previous = {'fill_results': [{'branch_id': 'accepted', 'result_text': 'durable'}]}
    state = web._RESPONSE_SEMANTICS_RUNTIME.build_late_fill_state({}, status='pending', prior_state=previous)
    assert state['fill_results'] == previous['fill_results']
    state['fill_results'][0]['result_text'] = 'changed'
    assert previous['fill_results'][0]['result_text'] == 'durable'
    cleared = web._RESPONSE_SEMANTICS_RUNTIME.build_late_fill_state(
        {}, status='pending', prior_state=previous, extra={'fill_results': []})
    assert cleared['fill_results'] == []


@pytest.mark.parametrize('defect', ['changed_bytes', 'foreign_branch', 'same_instance',
                                  'text_only_transport', 'wrong_transport_bytes'])
def test_backend_alternative_cannot_change_input_or_claim_text_only_dispatch(tmp_path, defect):
    owner, branch, payload, image = fixture(tmp_path)
    before = owner._prepared_vision_dependency(branch, payload, {'file_path': str(image)}, 'first')
    prepared = owner._prepared_vision_dependency(branch, payload, {'file_path': str(image)}, 'second')
    calls = []
    def backend(**kwargs):
        calls.append(kwargs)
        data = None if defect == 'text_only_transport' else b'other' if defect == 'wrong_transport_bytes' else image.read_bytes()
        return dispatch(data, GOOD_TEXT, instance='second'), 200
    owner.invoke_internal_api_json_route = backend
    plan = {'response_id': payload['id'], **branch, 'execution_contract': dict(branch),
            'instance': {'instance_id': 'second', 'backend': 'ollama'},
            'infer_payload': {'file_path': str(image), 'instance_id': 'second'}, 'effective_data': {},
            'vision_dependency_binding': prepared,
            'vision_recovery_attempt': {'recovery_policy_id': 'vision_bounded_backend_recovery_v1',
                                       'prior_vision_backend_failure': before}}
    if defect == 'changed_bytes': image.write_bytes(b'changed')
    elif defect == 'foreign_branch': prepared['branch_id'] = 'other'
    elif defect == 'same_instance': prepared['instance_id'] = 'first'
    with pytest.raises(RuntimeError, match='Vision'):
        owner.execute_prepared_late_fill_branch(plan)
    assert len(calls) == (1 if 'transport' in defect else 0)


@pytest.mark.parametrize('previous_policy', ['vision_bounded_backend_recovery_v1',
                                           'vision_bounded_evidence_recovery_v1'])
def test_backend_and_evidence_recovery_share_consumed_budget(tmp_path, previous_policy):
    owner, branch, payload, image = fixture(tmp_path)
    binding = owner._prepared_vision_dependency(branch, payload, {'file_path': str(image)}, 'first')
    context = {'error_code': 'BACKEND_ERROR', 'can_retry': True, 'preserve_intent': True,
               'retry_scope': 'same_branch', 'suggested_action': 'retry_excluding_instance',
               'exclude_instance_ids': ['first'], 'vision_backend_failure': binding}
    assert owner._vision_evidence_recovery_allowed(branch, context)
    branch['recovery_attempt'] = {'recovery_policy_id': previous_policy}
    assert not owner._vision_evidence_recovery_allowed(branch, context)
