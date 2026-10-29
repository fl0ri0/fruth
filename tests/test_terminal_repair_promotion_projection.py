"""Projection cannot manufacture promotion from graph acceptance or labels."""
from copy import deepcopy
import pytest
import tests.test_graph_repair_self_healing as repair_tests


@pytest.mark.parametrize('fault', [
    'none', 'missing_state', 'missing_contract', 'missing_source', 'provider_authority',
    'rejected', 'reserved', 'contract_id', 'binding_branch', 'binding_phase',
    'binding_contract', 'obligation', 'capability', 'output_type', 'duplicate',
    'rejected_patch',
])
def test_projection_requires_exact_runtime_promotion(fault):
    fixture = repair_tests.GraphRepairSelfHealingTests()
    owner = fixture._runtime_owner()
    branch = dict(branch_id='review', phase_id='review-phase', obligation_id='review-duty',
                  capability='chat', output_type='text', status='pending', required=True,
                  repair_action='semantic_review', contract_state='promoted',
                  promotion_source='graph_closure_review', repair_contract_id='repair-review')
    contract = dict(contract_id='repair-review', status='promoted',
                    authority='closure_review_runtime_truth', promotion_source='graph_closure_review',
                    obligation_id='review-duty', capability='chat', output_type='text',
                    execution_binding=dict(contract_id='repair-review', branch_id='review', phase_id='review-phase'))
    branch['repair_contract'] = contract
    if fault == 'missing_state': branch.pop('contract_state')
    elif fault == 'missing_contract': branch.pop('repair_contract')
    elif fault == 'missing_source': branch.pop('promotion_source')
    elif fault == 'provider_authority': contract['authority'] = 'provider_claim'
    elif fault in {'rejected', 'reserved'}: branch['contract_state'] = contract['status'] = fault
    elif fault in {'contract_id', 'obligation', 'capability', 'output_type'}:
        contract[{'obligation': 'obligation_id'}.get(fault, fault)] = 'foreign'
    elif fault.startswith('binding_'):
        contract['execution_binding'][fault.removeprefix('binding_') + '_id'] = 'foreign'
    elif fault == 'rejected_patch': branch['provider_bans'] = ['backend-family']
    gap = dict(repair_loop={'status':'promoted'}, inference_repair_feedback={'status':'repair_required'},
               pending_branches=[branch] * (2 if fault == 'duplicate' else 1))
    payload = {'runtime': {'request_phase_graph': fixture._base_graph()}}
    before = deepcopy((payload, gap))
    result = owner._attach_repair_gap_to_request_phase_graph(payload, gap)
    assert (payload, gap) == before
    graph = result['runtime']['request_phase_graph']
    obligations = [o for o in graph.get('output_obligations', []) if o.get('obligation_id') == 'review-duty']
    assert any(o.get('contract_state') == 'promoted' for o in obligations) is (fault == 'none')
    if fault == 'none':
        obligation = obligations[0]
        review = graph['graph_repair_reviews'][-1]
        assert obligation['promotion_source'] == branch['promotion_source']
        assert obligation['repair_contract_id'] == contract['contract_id']
        assert obligation['graph_repair_review_id'] == review['review_id']
        assert obligation['graph_repair_proposal_id'] == review['proposal_id']
        assert review['status'] == 'accepted'

