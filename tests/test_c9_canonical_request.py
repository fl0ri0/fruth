"""Real persisted request mutations must still deny guarded continuation.

These are owner negatives, not claims that public callers can edit frozen frames.
The separate POST regression proves actual scheduler-created context/execution.
"""
from copy import deepcopy

import pytest
import fruth_webserver as web
from fruth_server.responses_runtime import ResponseMutationConflict
from fruth_services.response_frames import build_response_frame, persist_response_frame
from fruth_services.responses import capture_request_intent
from tests.fake_backends import FakeBackendHarness


def test_canonical_preview_projection_is_idempotent_without_hiding_new_content():
    from fruth_services.response_frames import _compact_request_inference_preview

    original = {'model':'finite-provider', 'unknown_semantics':'retained',
                'runtime':{'request_phase_graph':{'branches':['original']}}}
    projected = _compact_request_inference_preview(original)
    assert projected['compaction']['duplicate_orchestration_truth_omitted']
    # Unknown audit fields remain binding too; no comparison allowlist is added.
    projected['compaction']['unknown_audit_field'] = {'original':True}
    assert _compact_request_inference_preview(projected) == projected
    changed = deepcopy(projected)
    changed['runtime'] = {'request_phase_graph':{'branches':['new-work']}}
    recomputed = _compact_request_inference_preview(changed)
    assert recomputed['compaction']['omitted_content_refs'] != projected['compaction']['omitted_content_refs']
    assert recomputed['unknown_semantics'] == 'retained'
    assert changed['runtime']['request_phase_graph']['branches'] == ['new-work']


@pytest.mark.parametrize('change', [
    'unchanged', 'prompt', 'execution_prompt', 'intent_source',
    'content_requirement_policy', 'content_review_reference_policy', 'request_meta',
    'unknown_semantic_field', 'preview_semantics', 'preview_audit', 'missing_request',
])
def test_persisted_request_mutation_remains_binding(tmp_path, change):
    branch = dict(branch_id='bounded', phase_id='bounded', obligation_id='owed',
                  contract_state='promoted', capability='chat', output_type='text',
                  content_payload='Inspect the accepted artifact only.', status='pending')
    payload = dict(id='canonical-c9', object='response', output_text='Prepared.',
                   runtime={'request_phase_graph': {'phases':[deepcopy(branch)],
                       'downstream_branches':[deepcopy(branch)],
                       'output_obligations':[deepcopy(branch)]}},
                   late_fill={'status':'pending','pending_branches':[deepcopy(branch)]})
    request = capture_request_intent({'prompt':'Review the existing artifact.', 'inference_route':True})
    with FakeBackendHarness(root=tmp_path) as harness:
        provider_calls = deepcopy(harness.calls)
        frame = build_response_frame(payload, request_payload=request)
        frame['request']['unknown_semantic_field'] = {'must_preserve':['original']}
        frame['request']['inference_preview'] = {'unknown_semantics':'original',
                                                'compaction':{'unknown_audit_field':'original'}}
        persist_response_frame(frame, frames_dir=harness.response_frames_dir)
        state = harness.response_state(payload['id'])
        assert state['ok']
        initial = state['response_payload']
        runtime = web._LATE_FILL_RUNTIME
        context = runtime._new_pending_continuation(initial, request)
        assert context is not None
        admitted_request = deepcopy(context.chain.admission['response_frame']['request'])
        next_frame = deepcopy(state['response_frame'])
        if change == 'missing_request': next_frame.pop('request')
        elif change == 'preview_semantics': next_frame['request']['inference_preview']['unknown_semantics']='changed'
        elif change == 'preview_audit': next_frame['request']['inference_preview']['compaction']['unknown_audit_field']='changed'
        elif change != 'unchanged': next_frame['request'][change]={'changed':True} if change in {'request_meta','unknown_semantic_field'} else 'changed'
        ledger = harness.response_frames_dir/'responses.jsonl'
        prefix = ledger.read_bytes()
        persist_response_frame(next_frame, frames_dir=harness.response_frames_dir)
        harness.clear_response_lookup()
        current = harness.response_state(payload['id'])
        assert current['ok'] and ledger.read_bytes().startswith(prefix)
        current_payload = current['response_payload']
        before_read = ledger.read_bytes()
        if change == 'unchanged':
            runtime._require_pending_continuation(context, current_payload, exact_frame=False)
        else:
            assert current['response_frame'].get('request') != admitted_request
            with pytest.raises(ResponseMutationConflict, match='admission changed'):
                runtime._require_pending_continuation(context, current_payload, exact_frame=False)
        with pytest.raises(ResponseMutationConflict, match='canonical request frame changed'):
            runtime._pending_frame_request(initial)
        assert context.chain.admission['response_frame']['request'] == admitted_request
        assert ledger.read_bytes() == before_read
        assert not web._RESPONSE_LATE_FILL_IN_FLIGHT and harness.calls == provider_calls


@pytest.mark.parametrize('proof', [
    'missing', 'reserved', 'rejected', 'branch_mismatch', 'phase_mismatch',
    'obligation_mismatch',
])
def test_passive_recovery_does_not_promote_or_authorize(tmp_path, proof):
    branch = dict(branch_id='bounded', phase_id='bounded-phase', obligation_id='owed',
                  contract_state='promoted', capability='chat', output_type='text',
                  content_payload='Inspect only the accepted artifact.', status='pending')
    obligation = deepcopy(branch)
    if proof == 'missing': obligation.pop('contract_state')
    elif proof in {'reserved', 'rejected'}: obligation['contract_state'] = proof
    else: obligation[proof.removesuffix('_mismatch') + '_id'] = 'foreign'
    payload = dict(id='unproven-c9', object='response', output_text='Prepared.',
                   runtime={'request_phase_graph': {'phases':[deepcopy(branch)],
                       'downstream_branches':[deepcopy(branch)],
                       'output_obligations':[obligation]}},
                   late_fill={'status':'pending','pending_branches':[deepcopy(branch)]})
    request = capture_request_intent({'prompt':'Review the existing artifact.'})
    with FakeBackendHarness(root=tmp_path) as harness:
        calls = deepcopy(harness.calls)
        persist_response_frame(build_response_frame(payload, request_payload=request),
                               frames_dir=harness.response_frames_dir)
        ledger = harness.response_frames_dir/'responses.jsonl'
        prefix = ledger.read_bytes()
        for _ in range(2):
            harness.clear_response_lookup()
            recovered = harness.response_state(payload['id'])
            assert recovered['ok']
            current = recovered['response_payload']
            assert current['runtime']['request_phase_graph']['output_obligations'] == [obligation]
            assert web._LATE_FILL_RUNTIME._new_pending_continuation(current, request) is None
            assert ledger.read_bytes() == prefix
            assert harness.calls == calls and not web._RESPONSE_LATE_FILL_IN_FLIGHT
