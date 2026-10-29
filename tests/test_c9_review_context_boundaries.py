"""Exact dependency and review-context proofs cannot widen execution authority."""
from copy import deepcopy
import pytest
from fruth_inference.request_phase_graph import downstream_phase_branch_batches


@pytest.mark.parametrize('fault', ['none','missing_result','phase','branch','obligation','capability',
    'output_type','duplicate_result','ambiguous','collision','foreign','reserved','failed'])
def test_guarded_alias_requires_exact_current_completion(fault):
    producer=dict(branch_id='producer',phase_id='producer-phase',obligation_id='producer-duty',
                  capability='chat',output_type='text',status='planned')
    review=dict(branch_id='review',phase_id='review-phase',obligation_id='review-duty',
                capability='chat',output_type='text',contract_state='promoted',status='pending',
                depends_on=['producer'],content_payload='Inspect the saved artifact.')
    result={**producer,'status':'fulfilled'}
    phases=[producer,review]; completed=[result];failed=[]
    if fault=='missing_result':completed=[]
    elif fault in {'phase','branch','obligation'}:result[fault+'_id']='foreign'
    elif fault in {'capability','output_type'}:result[fault]='foreign'
    elif fault=='duplicate_result':completed.append(deepcopy(result))
    elif fault=='ambiguous':phases.append({**producer,'phase_id':'other-phase'})
    elif fault=='collision':phases.append({**producer,'phase_id':'producer','branch_id':'other'})
    elif fault=='foreign':review['depends_on']=['other']
    elif fault=='reserved':producer['contract_state']='reserved'
    elif fault=='failed':failed=[deepcopy(result)]
    graph={'phases':phases,'downstream_branches':[review]};before=deepcopy((graph,completed,failed))
    batches=downstream_phase_branch_batches(graph,pending_branches=[review],completed_branches=completed,
        failed_branches=failed,resolve_dependency_aliases=True)
    assert bool(batches) is (fault=='none')
    assert (graph,completed,failed)==before
    if batches:
        assert batches[0][0]['depends_on']==['producer']
        assert batches[0][0]['content_payload']==review['content_payload']


def test_ordinary_alias_wave_order_is_unchanged():
    producer=dict(branch_id='producer',phase_id='producer-phase',capability='chat',output_type='text')
    reviews=[dict(branch_id='review-'+s,phase_id='review-'+s,capability='chat',output_type='text',
        contract_state='promoted',depends_on=['producer']) for s in ['one','two']]
    graph={'phases':[producer,*reviews]}
    assert downstream_phase_branch_batches(graph,pending_branches=reviews,completed_branches=[producer])==[]


def check_native_review_context(runtime, gap, current, request, *, verify):
    """Read-only negative controls on an actually admitted native review.

    Mutations affect copies only; none supply a permit or result to the worker.
    """
    from fruth_server.response_semantics_runtime import ResponseSemanticsRuntimeOwner
    import hashlib
    from fruth_services.responses import request_intent_frame_source, request_intent_payload, restore_request_intent

    instruction = gap['content_payload']
    root = request['prompt']
    assert root in instruction
    verified = verify(gap, current, request)
    assert verified == instruction
    guard = runtime._enforce_graph_patch_successor_branch_local_payload
    def guarded(payload, g=gap, proof=None, root_scope=False):
        return guard(payload, original_prompt=root, artifact_gap=g,
                     normalized_expected_capability='chat', root_scoped_execution=root_scope,
                     _verified_review_instruction=proof)
    payload = {'prompt': instruction, 'content_payload': instruction}
    assert guarded(payload).get('branch_contract_error')  # exact original rejection
    assert not guarded(payload, proof=verified).get('branch_contract_error')
    outcomes = ['original_guard_reproduced', 'exact_bound_context_accepted']
    for fault in ['missing_local', 'root', 'relabelled_root', 'instruction', 'phase', 'obligation',
                  'generation', 'reference_policy', 'promotion', 'repair_identity', 'patch_identity',
                  'duplicate_patch', 'dependency', 'caller_policy', 'widened_scope', 'self_consistent_root']:
        g, c, q = deepcopy((gap, current, request))
        b = next(b for b in c['late_fill']['pending_branches'] if b['branch_id'] == g['branch_id'])
        graph = c['runtime']['request_phase_graph']
        if fault == 'missing_local': g.pop('content_payload')
        elif fault == 'root': g['content_payload'] = root
        elif fault == 'relabelled_root': g['content_payload'] = 'Review this request: ' + root
        elif fault == 'instruction': g['content_payload'] += '\nDo additional work.'
        elif fault in {'phase', 'obligation'}: g[fault + '_id'] = 'foreign'
        elif fault in {'generation', 'reference_policy'}:
            binding = g['execution_contract']['branch_semantic_review']['semantic_review_evidence_binding']
            binding['generation_id' if fault == 'generation' else 'evidence_reference_policy'] = 'foreign'
        elif fault == 'promotion': b['contract_state'] = 'reserved'
        elif fault == 'repair_identity': b['repair_contract_id'] = 'foreign'
        elif fault in {'patch_identity', 'duplicate_patch'}:
            review = next(r for r in graph['graph_repair_reviews'] if any(
                p['branch_id'] == b['branch_id'] for p in r.get('accepted_patch', {}).get('add_phases', [])))
            if fault == 'patch_identity': review['status'] = 'rejected'
            else: graph['graph_repair_reviews'].append(deepcopy(review))
        elif fault == 'dependency': b['depends_on'] = ['foreign']
        elif fault == 'caller_policy':
            captured = request_intent_frame_source(q)
            captured['content_review_reference_policy'] = 'foreign'
            q = restore_request_intent(captured)
            assert request_intent_payload(q)['content_review_reference_policy'] == 'foreign'
        elif fault == 'widened_scope': g['execution_contract']['execution_scope'] = 'root'
        elif fault == 'self_consistent_root':
            # Even coherent review labels, identities and hashes cannot turn root
            # execution into the current Closure owner's exact review instruction.
            old = runtime._content_review_binding(g)
            new_instruction = 'Run a branch-local semantic review.\n' + root
            fresh = ResponseSemanticsRuntimeOwner._branch_semantic_review_generation(
                {'branch_id': old['source_branch_id'], 'phase_id': old['source_phase_id']}, new_instruction)
            replacements = {old[k]: v for k, v in fresh.items() if k in old and old[k] != v}
            replacements[instruction] = new_instruction
            replacements[old['instruction_sha256']] = hashlib.sha256(new_instruction.encode()).hexdigest()
            def replace(v):
                if isinstance(v, dict): return {k: replace(x) for k, x in v.items()}
                if isinstance(v, list): return [replace(x) for x in v]
                if isinstance(v, str):
                    if v in replacements: return replacements[v]
                    # Repair and graph-phase identifiers embed the generation ID.
                    for before, after in replacements.items():
                        if before == old['generation_id']: v = v.replace(before, after)
                return v
            g, c = replace(g), replace(c)
        assert verify(g, c, q) is None, fault
        outcomes.append(fault)
    for carrier in ['instruct', 'artifact_prompt', 'phase_summary', 'review_criteria',
                    'semantic_review_criteria', 'controlled_attention_question']:
        assert guarded({**payload, carrier: root}, proof=verified).get('branch_contract_error'), carrier
        outcomes.append('root_carrier:' + carrier)
    assert guarded(payload, proof=verified, root_scope=True).get('branch_contract_error')
    for trigger in ['graph_patch_successor_reopen', 'graph_rebase_partial_successor']:
        assert guarded(payload, g={**gap, 'trigger': trigger}, proof=verified).get('branch_contract_error')
        outcomes.append(trigger)
    return outcomes
