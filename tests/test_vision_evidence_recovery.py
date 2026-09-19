"""One alternate vision attempt, with real dispatch receipts and isolated workers."""
import base64
import copy
import hashlib
import json
from pathlib import Path

import pytest

from fruth_core.inference import InferArtifacts, InferContext, dispatch_infer_request
from fruth_server.late_fill_runtime import LateFillRuntimeOwner


POLICY = 'vision_bounded_evidence_recovery_v1'
GOOD_TEXT = 'The image shows a fox standing beside a green tree.'


def dispatch(image, text, instance='vision-first', backend='ollama'):
    ctx = InferContext(instance_id=instance, backend=backend, capability='vision_analysis',
        model_name='fixture-vision', port=0, prompt='Inspect the supplied image.',
        user_prompt='Inspect the supplied image.', infer_timeout_sec=10,
        pdf_page_timeout_sec=10, pdf_max_image_side=2400, pdf_synthesize=False)
    encoded = base64.b64encode(image).decode() if image else None
    artifacts = InferArtifacts(image_b64=encoded, file_kind='image' if image else '')
    calls = []

    def generate(_port, _model, _prompt, **kwargs):
        calls.append(kwargs['images'])
        return {'response': text}

    def chat(_port, _model, messages, **kwargs):
        calls.append(messages[-1]['content'][-1]['image_url'].split(',', 1)[1])
        return {'content': text, 'result': {}}

    result, status = dispatch_infer_request(ctx, artifacts, {
        'ollama_generate': generate, 'extract_generate_content': lambda result: result['response'],
        'mlx_chat_completions': chat, 'openai_chat_completions': chat,
    })
    assert status == 200
    if image:
        supplied = calls[0][0] if backend == 'ollama' else calls[0]
        assert base64.b64decode(supplied) == image
    return result


def fixture(root):
    owner = object.__new__(LateFillRuntimeOwner)
    owner.normalize_capability = lambda value: value
    owner.branch_capability = lambda branch: branch.get('capability')
    owner.branch_id = lambda branch: str(branch.get('branch_id') or '')
    owner.capability_chat = 'chat'
    owner.capability_image_generation = 'image_generation'
    owner.capability_text_to_speech = 'text_to_speech'
    owner.filter_responses_infer_result = lambda result, **kw: result
    owner.resolve_saved_file_input_path = lambda value: (
        Path(value).resolve() if Path(value).resolve().is_relative_to(root) else None)
    image = root / 'fox.png'
    # Receipt behavior depends on exact bytes, not a model or image decoder.
    image.write_bytes(base64.b64decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII='))
    producer = {'branch_id': 'image', 'phase_id': 'phase-2', 'capability': 'image_generation',
        'status': 'fulfilled', 'saved_image_path': str(image)}
    branch = {'branch_id': 'vision', 'phase_id': 'phase-3', 'capability': 'vision_analysis',
        'output_type': 'text', 'depends_on': ['phase-2'],
        'content_payload': 'Inspect the actual generated image.',
        'output_contract': {'required': True, 'output_type': 'text'}}
    payload = {'id': 'vision-response', 'late_fill': {
        'fill_results': [copy.deepcopy(producer)], 'completed_branches': [copy.deepcopy(producer)]}}
    return owner, branch, payload, image


def failed_result(owner, branch, payload, image, text=None):
    plan = {'response_id': payload['id'], **branch, 'execution_contract': dict(branch),
        'instance': {'instance_id': 'vision-first', 'backend': 'ollama'},
        'infer_payload': {'file_path': str(image), 'instance_id': 'vision-first'}, 'effective_data': {}}
    owner.invoke_internal_api_json_route = lambda **kw: (dispatch(image.read_bytes(), text or str(image)), 200)
    return owner.execute_prepared_late_fill_branch(plan)['infer_result']


def retry_for(owner, branch, result, payload):
    error = owner.dependency_evidence_error_for_branch_result(branch, result, current_payload=payload)
    attempt = {'instance_id': result['instance_id'], 'capability': 'vision_analysis', 'stage': 'semantic_evidence_gate'}
    context = owner.late_fill_recovery_context(error=owner.normalize_late_fill_error_payload(error), attempt=attempt)
    state = owner.late_fill_recovery_state(branch, recovery_context=context, attempt=attempt)
    retry = owner.build_auto_executable_repair_retry_branch(branch,
        recovery_context=context, recovery_state=state, attempt=attempt, trigger='semantic_evidence_gate')
    return error, context, retry


@pytest.mark.parametrize('backend', ['ollama', 'mlx', 'llama_cpp'])
def test_dispatch_receipt_is_bound_to_actual_image_bytes(backend):
    result = dispatch(b'exact image bytes', GOOD_TEXT, backend=backend)
    receipt = result['vision_input_evidence']
    assert receipt['image_sha256'] == hashlib.sha256(b'exact image bytes').hexdigest()
    assert receipt['size_bytes'] == len(b'exact image bytes')
    assert receipt['instance_id'] == 'vision-first'


def test_text_only_dispatch_does_not_claim_an_image():
    assert dispatch(None, GOOD_TEXT)['vision_input_evidence'] == {}


def test_rejected_result_gets_one_alternate_attempt_and_preserves_failure(tmp_path, monkeypatch):
    owner, branch, payload, image = fixture(tmp_path)
    result = failed_result(owner, branch, payload, image)
    monkeypatch.setenv('FRUTH_AUTO_EXECUTABLE_REPAIR_MAX_ATTEMPTS', '99')
    error, context, retry = retry_for(owner, branch, result, payload)
    assert error['code'] == 'VISION_DEPENDENCY_EVIDENCE_REJECTED'
    assert context['can_retry'] is True
    assert retry['auto_executable_repair_retry_count'] == 1
    assert retry['auto_executable_repair_max_attempts'] == 2
    assert retry['excluded_instance_ids'] == ['vision-first']
    assert retry['branch_id'] == branch['branch_id']
    assert retry['depends_on'] == branch['depends_on']
    assert retry['content_payload'] == branch['content_payload']
    assert retry['recovery_attempt']['prior_vision_evidence_failure']['rejected_text'] == str(image)
    assert retry_for(owner, retry, result, payload)[2] is None
    # Removing the scalar counter cannot erase the retained consumed attempt.
    retry.pop('auto_executable_repair_retry_count')
    assert retry_for(owner, retry, result, payload)[2] is None


@pytest.mark.parametrize('defect', ['missing_receipt', 'foreign_response', 'foreign_branch', 'foreign_phase',
    'wrong_authority', 'changed_image', 'missing_image', 'wrong_dependency', 'duplicate_producer',
    'producer_incomplete', 'failed_producer', 'unauthorized_path', 'extra_dependency'])
def test_unproven_input_stays_dependency_repair(tmp_path, defect):
    owner, branch, payload, image = fixture(tmp_path)
    result = failed_result(owner, branch, payload, image)
    if defect == 'missing_receipt': result.pop('vision_input_evidence')
    elif defect.startswith('foreign_'): result['vision_input_evidence'][defect[8:] + '_id'] = 'other'
    elif defect == 'wrong_authority': result['vision_input_evidence']['authority'] = 'model_claim'
    elif defect == 'changed_image': image.write_bytes(b'changed')
    elif defect == 'missing_image': image.unlink()
    elif defect == 'wrong_dependency': branch['depends_on'] = ['unrelated']
    elif defect == 'extra_dependency': branch['depends_on'].append('unrelated')
    elif defect == 'duplicate_producer': payload['late_fill']['fill_results'] *= 2
    elif defect == 'producer_incomplete': payload['late_fill']['completed_branches'] = []
    elif defect == 'failed_producer': payload['late_fill']['fill_results'][0]['error'] = 'failed'
    elif defect == 'unauthorized_path': owner.resolve_saved_file_input_path = lambda _: None
    error, context, retry = retry_for(owner, branch, result, payload)
    assert error['code'] == 'DEPENDENCY_CHAIN_REPAIR_REQUIRED'
    assert context['can_retry'] is False
    assert retry is None


@pytest.mark.parametrize('control', [{'required': False}, {'optional': True},
    {'automatic_follow_up_allowed': False}, {'needs_external_input': True},
    {'status': 'cancelled'}, {'status': 'waived'}, {'status': 'superseded'}])
def test_recovery_respects_branch_controls(tmp_path, control):
    owner, branch, payload, image = fixture(tmp_path)
    result = failed_result(owner, branch, payload, image)
    branch.update(control)
    assert retry_for(owner, branch, result, payload)[2] is None


@pytest.mark.parametrize('defect', ['image', 'instance', 'response', 'dependency',
    'transport_receipt', 'transport_authority', 'transport_status'])
def test_retry_cannot_change_bound_input_or_reuse_failed_instance(tmp_path, defect):
    owner, branch, payload, image = fixture(tmp_path)
    result = failed_result(owner, branch, payload, image)
    retry = retry_for(owner, branch, result, payload)[2]
    plan = {'response_id': payload['id'], **branch, 'execution_contract': dict(branch),
        'vision_recovery_attempt': retry['recovery_attempt'],
        'instance': {'instance_id': 'vision-second', 'backend': 'ollama'},
        'infer_payload': {'file_path': str(image), 'instance_id': 'vision-second'}, 'effective_data': {}}
    calls = []
    def backend(**kw):
        calls.append(kw)
        result = dispatch(image.read_bytes(), GOOD_TEXT, instance='vision-second')
        if defect == 'transport_receipt': result.pop('vision_input_evidence')
        elif defect == 'transport_authority': result['vision_input_evidence']['authority'] = 'provider_claim'
        elif defect == 'transport_status': result['vision_input_evidence']['status'] = 'pending'
        return result, 200
    owner.invoke_internal_api_json_route = backend
    if defect == 'image': image.write_bytes(b'changed')
    elif defect == 'instance': plan['instance']['instance_id'] = plan['infer_payload']['instance_id'] = 'vision-first'
    elif defect == 'response': plan['response_id'] = 'other'
    elif defect == 'dependency': plan['execution_contract']['depends_on'] = ['other']
    with pytest.raises(RuntimeError, match='Vision recovery'):
        owner.execute_prepared_late_fill_branch(plan)
    assert len(calls) == (1 if defect.startswith('transport_') else 0)


def test_successful_analysis_does_not_consume_recovery(tmp_path):
    owner, branch, payload, image = fixture(tmp_path)
    result = failed_result(owner, branch, payload, image, GOOD_TEXT)
    assert owner.dependency_evidence_error_for_branch_result(branch, result, current_payload=payload) is None


def test_smaller_explicit_budget_is_respected(tmp_path, monkeypatch):
    owner, branch, payload, image = fixture(tmp_path)
    result = failed_result(owner, branch, payload, image)
    monkeypatch.setenv('FRUTH_AUTO_EXECUTABLE_REPAIR_MAX_ATTEMPTS', '1')
    assert retry_for(owner, branch, result, payload)[2] is None


@pytest.mark.parametrize('outcome', ['success', 'exhausted', 'unavailable', 'cancelled'])
def test_worker_routes_one_alternative_and_persists_evidence(tmp_path, monkeypatch, outcome):
    import fruth_webserver
    from tests.fake_backends import FakeBackendHarness
    from fruth_inference.request_phase_graph import build_request_phase_graph

    prompt = 'Generate an image of a fox, then analyze the actual generated image and summarize the analysis.'
    graph = build_request_phase_graph(prompt, response_payload={'output_text': 'Image prompt ready.'})
    branches = graph['downstream_branches']
    producer = next(b for b in branches if b['capability'] == 'image_generation')
    vision = next(b for b in branches if b['capability'] == 'vision_analysis')
    _, _, _, image = fixture(tmp_path)
    initial_image = image.read_bytes()
    producer = {**producer, 'status': 'fulfilled', 'saved_image_path': str(image)}
    pending = [b for b in branches if b['branch_id'] != producer['branch_id']]
    payload = {'id': 'vision-worker-' + outcome, 'object': 'response', 'capability': 'chat',
        'output_text': 'Image prompt ready.', 'runtime': {'request_phase_graph': graph},
        'late_fill': {'status': 'pending', 'fill_results': [producer], 'completed_branches': [producer],
                     'pending_branches': pending, 'pending_capabilities': [b['capability'] for b in pending]}}
    calls = []
    with FakeBackendHarness() as harness, monkeypatch.context() as patch:
        runtime = fruth_webserver._LATE_FILL_RUNTIME
        for instance in harness.instances.values():
            instance['runtime_status'].update(process_alive=True, port_listening=True)
        first = harness.instances['vision_analysis']
        second = copy.deepcopy(first)
        second.update(instance_id='second-vision', model='second-vision-model')
        if outcome != 'unavailable': harness.instances['vision_alternative'] = second
        if outcome == 'exhausted':
            harness.instances['vision_third'] = {**copy.deepcopy(second), 'instance_id': 'third-vision'}
        # The continuation owner retains these callables at composition time;
        # override them as well as the harness's public route hooks.
        patch.setattr(runtime, 'load_running_instances', lambda: list(harness.instances.values()))
        patch.setattr(runtime, 'merge_instances_with_runtime_status', lambda entries, **kw: entries)
        resolver = lambda value: Path(value).resolve() if Path(value).resolve().is_relative_to(tmp_path) else None
        patch.setattr(runtime, 'resolve_saved_file_input_path', resolver)
        patch.setattr(fruth_webserver, '_resolve_saved_viewable_artifact_path', resolver)
        patch.setitem(fruth_webserver.app.config, 'TESTING', True)
        request = {'prompt': prompt, 'inference_route': True}

        def backend(*, payload, upload):
            capability = payload['capability']
            calls.append((capability, payload['instance_id'], copy.deepcopy(payload)))
            if capability == 'vision_analysis':
                assert Path(payload['file_path']).read_bytes() == initial_image
                assert prompt not in payload['prompt']
                vision_calls = [call for call in calls if call[0] == 'vision_analysis']
                text = str(image) if len(vision_calls) == 1 or outcome == 'exhausted' else GOOD_TEXT
                return dispatch(initial_image, text, instance=payload['instance_id']), 200
            assert capability == 'chat'
            assert GOOD_TEXT in payload['prompt']
            return {'content': 'The inspected image shows a fox beside a tree.'}, 200

        patch.setattr(fruth_webserver, '_invoke_internal_api_json_route', backend)
        original_retry_builder = runtime.build_auto_executable_repair_retry_branch
        if outcome == 'cancelled':
            def cancel_retry(*args, **kwargs):
                retry = original_retry_builder(*args, **kwargs)
                if retry: retry.update(status='cancelled', cancel_requested=True)
                return retry
            patch.setattr(runtime, 'build_auto_executable_repair_retry_branch', cancel_retry)
        with fruth_webserver.app.app_context():
            runtime.complete_response_late_fill(response_payload=payload, request_payload=request,
                assistant_message=payload['output_text'], artifact_gap={
                    'trigger': 'execution_planner_deferred_follow_up',
                    'pending_branches': pending, 'pending_capabilities': [b['capability'] for b in pending],
                    'expected_capability': 'vision_analysis'}, source_route_payload=None)
        final = runtime.get_response_lookup_record(payload['id'])['response_payload']
        (tmp_path / 'worker-result.json').write_text(json.dumps({'final': final, 'calls': calls}, default=str))
        vision_calls = [call for call in calls if call[0] == 'vision_analysis']
        assert len(vision_calls) == (2 if outcome in {'success', 'exhausted'} else 1), final['late_fill']
        if len(vision_calls) == 2:
            assert vision_calls[0][1] != vision_calls[1][1]
        assert image.read_bytes() == initial_image
        late_fill = final['late_fill']
        if outcome == 'success':
            assert late_fill['status'] == 'completed', late_fill
            assert final['lifecycle_state'] == 'completed'
            assert final['runtime']['graph_closure_review']['status'] == 'fulfilled'
            result = next(r for r in late_fill['fill_results'] if r['branch_id'] == vision['branch_id'])
            assert result['result_text'] == GOOD_TEXT
            assert result['vision_input_evidence']['image_sha256'] == hashlib.sha256(initial_image).hexdigest()
        else:
            assert final['lifecycle_state'] != 'completed'
            assert not any(call[0] == 'chat' for call in calls)
            assert not any(r['branch_id'] == vision['branch_id'] for r in late_fill['fill_results'])
        records = [r for k in ('completed_branches', 'failed_branches', 'cancelled_branches')
                   for r in late_fill.get(k) or [] if r['branch_id'] == vision['branch_id']]
        assert len(records) == 1
        retained = records[0]['recovery_attempt']
        assert retained['recovery_policy_id'] == POLICY
        assert retained['prior_vision_evidence_failure']['rejected_text'] == str(image)
        assert retained['attempt_number'] == 2
        normalized = fruth_webserver._normalize_late_fill_branches(records)[0]
        assert normalized['auto_executable_repair_retry_count'] == 1
        assert normalized['recovery_attempt'] == retained
        assert first['runtime_status']['process_alive'] is True
        assert not fruth_webserver._RESPONSE_LATE_FILL_IN_FLIGHT
        patch.setitem(fruth_webserver.app.config, 'TESTING', False)
        harness.freeze_manual_response(final, request_payload=request)
        hydrated = harness.response_state(payload['id'])['response_payload']
        hydrated_records = [r for k in ('completed_branches', 'failed_branches', 'cancelled_branches')
                           for r in hydrated['late_fill'].get(k) or [] if r['branch_id'] == vision['branch_id']]
        assert hydrated_records[0]['recovery_attempt'] == retained
        assert hydrated_records[0]['auto_executable_repair_retry_count'] == 1
        if outcome == 'exhausted':
            second_failure = hydrated_records[0]['error']['vision_evidence_failure']
            assert second_failure['input_evidence']['instance_id'] != retained['failed_instance_id']
            assert not runtime.auto_executable_repair_recovery_allowed(
                hydrated_records[0], recovery_context=hydrated_records[0]['recovery_context'])
