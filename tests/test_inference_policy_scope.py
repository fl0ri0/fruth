from pathlib import Path

import pytest

from fruth_inference.policy_scope import select_policy_scope
from fruth_inference import router
from fruth_server.response_semantics_runtime import ResponseSemanticsRuntimeOwner


POLICY = Path(__file__).resolve().parents[1] / 'FRUTH_INFERENCE.md'


def marked_policy(common='Runtime owns truth.', execution='Answer the user.', routing='Return route JSON.'):
    return '\n'.join(
        f'<!-- fruth-policy:{name}:start -->\n{body}\n<!-- fruth-policy:{name}:end -->'
        for name, body in [('common', common), ('execution', execution), ('routing', routing)]
    )


def test_role_selection_keeps_complete_common_and_selected_scope_only():
    tail = 'KEEP_EXACT_BRANCH_CONTRACT_TAIL'
    execution = 'Execution rule\n' * 1000 + tail
    source = marked_policy(execution=execution) + '\nDetailed authoring reference.'
    result = select_policy_scope(source, 'execution')
    assert execution in result
    assert 'Runtime owns truth.' in result
    assert 'Return route JSON.' not in result
    assert 'Detailed authoring reference.' not in result
    assert 'source_sha256:' in result
    assert tail in result
    assert execution not in select_policy_scope(source, 'routing')


def test_legacy_policy_is_not_truncated_or_reinterpreted():
    source = 'custom instruction\n' * 4000 + 'KEEP_TAIL'
    assert select_policy_scope(source, 'execution') == source
    assert select_policy_scope(source, 'routing') == source


@pytest.mark.parametrize('bad', [
    marked_policy().replace('<!-- fruth-policy:common:end -->', ''),
    marked_policy(common=''),
    marked_policy() + '\n<!-- fruth-policy:execution:start -->',
    marked_policy(common='<!-- fruth-policy:routing:start -->'),
])
def test_malformed_scoped_policy_fails_instead_of_silently_losing_rules(bad):
    with pytest.raises(ValueError):
        select_policy_scope(bad, 'execution')


def test_current_policy_leaves_room_for_input_and_output_in_small_context():
    # The explicitly expanded AFM policy has a larger authored allocation than
    # the previous 1,232-token estimate. This conservative fixture ceiling is
    # not runtime model metadata; native context acceptance also needs live tests.
    for scope in ('routing', 'execution'):
        selected = router._load_runtime_inference_policy(scope, backend='apple_fm')
        assert len(selected.encode('utf-8')) / 3 < 4000
        assert len(selected) > 5207  # richer than the previous common+role projection
        assert 'Runtime owns promotion, execution, artifacts' in selected
        assert 'Frozen parents stay' in selected
        assert 'not replay the root request' in selected
        assert 'deterministic review_criteria' in selected
        assert 'source_sha256:' in selected


@pytest.mark.parametrize('backend', [None, 'ollama', 'mlx', 'llama_cpp', 'codex_cli', 'apple_pcc'])
def test_non_afm_receives_the_entire_canonical_policy(backend):
    for scope in ('routing', 'execution'):
        assert router._load_runtime_inference_policy(scope, backend=backend) == POLICY.read_text()


def test_available_afm_is_not_the_executing_policy_backend():
    context = {'prompt': 'hello', 'runtime': {'instances': [{'backend': 'apple_fm'}]}}
    full = router.build_router_messages(context, backend='ollama')[0]['content']
    compact = router.build_router_messages(context, backend='apple_fm')[0]['content']
    assert POLICY.read_text() in full
    assert POLICY.read_text() not in compact
    assert 'source: fruth_inference/policies/apple_fm.md' in compact
    assert router._load_runtime_inference_policy(backend='ollama') == POLICY.read_text()


def test_custom_policy_is_not_replaced_with_bundled_afm_guidance(tmp_path, monkeypatch):
    path = tmp_path / 'custom.md'
    text = 'Custom policy\n' * 4000 + 'EXACT_CUSTOM_TAIL\n'
    path.write_text(text)
    monkeypatch.setattr(router, 'INFERENCE_POLICY_PATH', path)
    assert router._load_runtime_inference_policy(backend='apple_fm') == text
    assert router._load_runtime_inference_policy(backend='ollama') == text


def test_missing_or_malformed_afm_projection_fails_visibly(tmp_path, monkeypatch):
    path = tmp_path / 'apple_fm.md'
    monkeypatch.setattr(router, 'AFM_INFERENCE_POLICY_PATH', path)
    with pytest.raises(ValueError, match='unavailable'):
        router._load_runtime_inference_policy(backend='apple_fm')
    path.write_text(marked_policy().replace('<!-- fruth-policy:execution:end -->', ''))
    with pytest.raises(ValueError, match='complete execution'):
        router._load_runtime_inference_policy(backend='apple_fm')
    assert router._load_runtime_inference_policy(backend='ollama') == POLICY.read_text()


def test_backend_rebinding_keeps_one_correct_policy_and_all_task_inputs():
    owner = ResponseSemanticsRuntimeOwner({})
    messages = [{'role': 'system', 'content': 'Exact branch contract.'},
                {'role': 'user', 'content': 'Exact promoted payload.'}]
    for backend in ['ollama', 'apple_fm', 'mlx', 'apple_fm']:
        messages = owner.inject_inference_runtime_policy_into_chat_messages(
            messages, request_payload={'inference_route': True}, backend=backend)
        assert len(messages) == 3
        assert messages[1:] == [{'role': 'system', 'content': 'Exact branch contract.'},
                                {'role': 'user', 'content': 'Exact promoted payload.'}]
        assert (POLICY.read_text().strip() in messages[0]['content']) == (backend != 'apple_fm')


@pytest.mark.parametrize('backend', ['apple_fm', 'apple_pcc'])
def test_apple_prepare_boundary_preserves_reference_and_is_idempotent(backend):
    owner = ResponseSemanticsRuntimeOwner({'extract_responses_prompt': lambda p: p['prompt']})
    prompt = 'Write two sentences about fog, create one WAV reading them, then transcribe that audio.'
    original = [{'role': 'user', 'content': prompt}]
    request = {'inference_route': True, 'prompt': prompt}
    framed = owner.inject_prepare_phase_contract_into_chat_messages(original, request_payload=request, backend=backend)
    assert '<fruth_bounded_task>' in framed[-1]['content']
    assert '<fruth_promoted_context>\n' + prompt in framed[-1]['content']
    assert 'directly speakable' in framed[-1]['content']
    assert '[FRUTH_DOWNSTREAM_EXECUTION_V1]' not in framed[-1]['content']
    assert owner.inject_prepare_phase_contract_into_chat_messages(framed, request_payload=request, backend=backend) == framed
    ordinary = owner.inject_prepare_phase_contract_into_chat_messages(original, request_payload=request, backend='ollama')
    assert ordinary[-1] == original[-1]
    assert original == [{'role': 'user', 'content': prompt}]


def test_pcc_direct_multistep_chat_does_not_inherit_inference_preparation_role():
    owner = ResponseSemanticsRuntimeOwner({'extract_responses_prompt': lambda p: p['prompt']})
    prompt = 'Write two sentences about fog, create one WAV reading them, then transcribe that audio.'
    messages = [{'role': 'user', 'content': prompt}]
    for request in [{'prompt': prompt}, {'prompt': prompt, 'inference_route': False}]:
        prepared = owner.inject_prepare_phase_contract_into_chat_messages(
            messages, request_payload=request, backend='apple_pcc')
        prepared = owner.inject_inference_runtime_policy_into_chat_messages(
            prepared, request_payload=request, backend='apple_pcc')
        assert prepared == messages


def test_pcc_inference_explains_transport_without_replacing_full_policy():
    owner = ResponseSemanticsRuntimeOwner({})
    message = owner.build_inference_runtime_policy_system_message(
        request_payload={'inference_route': True}, backend='apple_pcc')
    assert POLICY.read_text().strip() in message['content']
    assert 'Apple Shortcuts only transports this text exchange' in message['content']
    assert 'Fruth dispatches those branches through its own runtime.' in message['content']
    assert owner.build_inference_runtime_policy_system_message(
        request_payload={'inference_route': False}, backend='apple_pcc') is None


@pytest.mark.parametrize('backend', ['apple_fm', 'ollama', 'mlx', 'llama_cpp', 'apple_pcc'])
def test_execution_receives_existing_route_role_guidance_without_planner_call(backend):
    from fruth_inference.execution_planner import _semantic_role_guidance

    owner = ResponseSemanticsRuntimeOwner({})
    profile = {
        'mode': 'improviser', 'mode_source': 'intent',
        'semantic_role_ids': ['materializer', 'quality_reviewer'],
        'semantic_role_orientation': {
            'mode': 'improviser',
            'suggested_semantic_review_lenses': ['quality_reviewer', 'integrator'],
            'reason': 'Check the current artifact against the accepted intent.',
            'non_authority_boundary': 'Existing Runtime and Closure gates retain authority.',
        },
    }
    route = {'route_source': 'inference_carried', 'route_runtime': {
        'semantic_role_profile': profile,
        'execution_planner': {'attempted': True, 'reason': 'request_phase_graph_follow_up'},
    }}
    messages = [{'role': 'user', 'content': 'Exact current phase payload.'}]
    result = owner.inject_inference_runtime_policy_into_chat_messages(
        messages, route_payload=route, backend=backend)
    assert _semantic_role_guidance(profile) in result[0]['content']
    assert result[1:] == messages
    assert owner.inject_inference_runtime_policy_into_chat_messages(
        result, route_payload=route, backend=backend) == result


@pytest.mark.parametrize('backend', ['apple_fm', 'apple_pcc'])
def test_route_roles_do_not_turn_direct_execution_into_interpretive_inference(backend):
    owner = ResponseSemanticsRuntimeOwner({})
    messages = [{'role': 'user', 'content': 'Exact bounded worker task.'}]
    assert owner.inject_inference_runtime_policy_into_chat_messages(
        messages, route_payload={'route_source': 'direct', 'route_runtime': {
            'semantic_role_profile': {'semantic_role_ids': ['quality_reviewer']}}},
        request_payload={'inference_route': False}, backend=backend) == messages
