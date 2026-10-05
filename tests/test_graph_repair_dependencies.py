"""Executable dependency topology at additive repair validation and apply."""

import copy

import pytest

from fruth_server.responses_request_runtime import ResponsesRequestRuntimeOwner
from fruth_services.graph_repair import (
    GRAPH_REPAIR_PROPOSAL_KIND,
    PROPOSAL_ALLOWED_USE,
    PROPOSAL_FORBIDDEN_USE,
    apply_validated_graph_patch,
    apply_validated_graph_repair_patch,
    build_graph_patch_lifecycle,
    build_graph_repair_proposals,
    validate_graph_repair_proposal,
)


def _phase(number, depends_on=()):
    return {
        'phase_id': f'phase-{number}',
        'branch_id': f'branch-{number}',
        'capability': 'chat',
        'output_type': 'text',
        'status': 'pending',
        **({'depends_on': list(depends_on)} if depends_on else {}),
    }


def _graph(*phases):
    return {
        'phases': list(phases),
        'downstream_branches': copy.deepcopy(list(phases)),
        'output_obligations': [],
    }


def _edge(target, source):
    return {'target_phase_id': target, 'source_phase_id': source}


def _review(graph, patch):
    return validate_graph_repair_proposal(
        {
            'kind': GRAPH_REPAIR_PROPOSAL_KIND,
            'proposal_id': 'graph-repair-dependency-test',
            'source': 'runtime',
            'repair_type': 'rebind_artifact_dependency',
            'evidence_refs': ['runtime:missing_dependency_edge'],
            'patch': patch,
            'allowed_use': PROPOSAL_ALLOWED_USE,
            'forbidden_use': PROPOSAL_FORBIDDEN_USE,
        },
        request_phase_graph=graph,
    )


@pytest.mark.parametrize(('graph', 'patch', 'reason'), [
    (_graph(_phase(1), _phase(2)),
     {'add_dependencies': [_edge('phase-2', 'missing-producer')]},
     'dependency_source_not_in_graph_or_patch'),
    (_graph(_phase(1)),
     {'add_dependencies': [_edge('missing-consumer', 'phase-1')]},
     'dependency_target_not_in_graph_or_patch'),
    (_graph(_phase(1)),
     {'add_dependencies': [_edge('phase-1', 'branch-1')]},
     'dependency_cycle'),
    (_graph(_phase(1), _phase(2, ['branch-1'])),
     {'add_dependencies': [_edge('branch-1', 'phase-2')]},
     'dependency_cycle'),
    (_graph(_phase(1), _phase(2)),
     {'add_dependencies': [_edge('phase-1', 'branch-2'), _edge('branch-2', 'phase-1')]},
     'dependency_cycle'),
    (_graph(_phase(1)),
     {'add_phases': [_phase(2, ['missing-producer'])]},
     'dependency_source_not_in_graph_or_patch'),
    (_graph(_phase(1)),
     {'add_phases': [_phase(2, ['branch-3']), _phase(3, ['phase-2'])]},
     'dependency_cycle'),
    (_graph(_phase(1)),
     {'add_phases': [_phase(2, ['phase-1'])],
      'add_dependencies': [_edge('phase-1', 'branch-2')]},
     'dependency_cycle'),
    (_graph(_phase(1), {**_phase(2), 'branch_id': 'branch-1'}),
     {'add_dependencies': [_edge('phase-2', 'branch-1')]},
     'dependency_identity_ambiguous'),
])
def test_dependency_topology_rejects_invalid_combined_patch(graph, patch, reason):
    before = copy.deepcopy(graph)
    review = _review(graph, patch)

    assert review['status'] == 'rejected'
    assert reason in review['reasons']
    assert not review.get('accepted_patch')
    assert review['allowed_runtime_action'] == 'none'
    assert graph == before


@pytest.mark.parametrize('dependency', [
    {'depends_on': ['branch-1']},
    {'dependsOn': ['branch-1']},
    {'execution_contract': {'depends_on': ['branch-1']}},
    {'execution_contract': {'dependencies': ['branch-1']}},
])
def test_dependency_topology_checks_downstream_projection_edges(dependency):
    graph = _graph(_phase(1), _phase(2))
    graph['downstream_branches'][1].update(dependency)
    review = _review(graph, {'add_dependencies': [_edge('phase-1', 'phase-2')]})

    assert review['status'] == 'rejected'
    assert 'dependency_cycle' in review['reasons']


def test_dependency_topology_accepts_new_sources_and_branch_aliases_idempotently():
    graph = _graph(_phase(1))
    patch = {
        'add_phases': [_phase(3, ['branch-2']), _phase(2, ['phase-1'])],
        'add_dependencies': [_edge('branch-3', 'branch-1')],
    }
    review = _review(graph, patch)
    assert review['status'] == 'accepted'

    first = apply_validated_graph_repair_patch(graph, review)
    second = apply_validated_graph_repair_patch(first['graph'], review)

    assert first['status'] == 'applied'
    assert second['status'] == 'already_applied'
    for collection in ('phases', 'downstream_branches', 'output_obligations'):
        phase = next(item for item in first['graph'][collection] if item['phase_id'] == 'phase-3')
        assert phase['depends_on'] == ['branch-2', 'branch-1']
    assert graph == _graph(_phase(1))


@pytest.mark.parametrize('change', ['remove_source', 'reverse_edge'])
def test_dependency_topology_rechecked_before_applying_accepted_review(change):
    graph = _graph(_phase(1), _phase(2))
    review = _review(graph, {'add_dependencies': [_edge('phase-2', 'phase-1')]})
    assert review['status'] == 'accepted'
    if change == 'remove_source':
        graph = _graph(_phase(2))
    else:
        graph = _graph(_phase(1, ['branch-2']), _phase(2))
    before = copy.deepcopy(graph)

    result = apply_validated_graph_repair_patch(graph, review)

    assert result['status'] == 'rejected'
    assert result['reason'] == 'dependency_topology_invalid'
    assert result['dependency_issues']
    assert not result.get('applied_dependency_edges')
    assert not result['graph'].get('graph_refinements')
    assert graph == before


def test_dependency_topology_rejection_is_visible_in_lifecycle_for_old_review():
    graph = _graph(_phase(1), _phase(2))
    review = _review(graph, {'add_dependencies': [_edge('phase-2', 'phase-1')]})
    # A persisted review from before topology validation must not bypass the sink.
    review['accepted_patch']['add_dependencies'][0]['source_phase_id'] = 'missing-producer'
    lifecycle = build_graph_patch_lifecycle(
        request_phase_graph=graph, proposal_review=review, autonomy_level='apply_safe',
    )
    result = apply_validated_graph_patch(graph, lifecycle, autonomy_level='apply_safe')

    assert result['status'] == 'rejected'
    recorded = result['graph']['graph_patch_lifecycle'][0]
    assert recorded['outcome'] == {'status': 'rejected', 'runtime_effect': 'none'}
    assert recorded['blocked_reasons'] == ['dependency_topology_invalid']
    assert recorded['dependency_issues'][0]['source_id'] == 'missing-producer'
    assert not result['graph'].get('applied_graph_patches')


@pytest.mark.parametrize('autonomy', ['apply_safe', 'apply_enforced'])
@pytest.mark.parametrize(('target', 'source', 'expected'), [
    ('phase-2', 'missing-producer', 'rejected'),
    ('branch-1', 'phase-2', 'rejected'),
    ('phase-3', 'branch-2', 'accepted'),
])
def test_dependency_topology_through_runtime_scope_evidence_and_lifecycle(
    monkeypatch, autonomy, target, source, expected,
):
    monkeypatch.setenv('FRUTH_APPLY_ENFORCED_POLICY', 'safe_v1')
    owner = ResponsesRequestRuntimeOwner(
        hooks={}, capability_chat='chat', capability_embedding='embedding',
        capability_image_generation='image_generation', capability_speech_to_text='speech_to_text',
        request_timeout_error=TimeoutError, request_exception_error=Exception,
    )
    graph = _graph(_phase(1), _phase(2, ['phase-1']), _phase(3))
    payload = {
        'id': 'resp-dependency-topology',
        'runtime': {
            'request_phase_graph': graph,
            'graph_closure_review': {
                'status': 'pending',
                'intent_graph_adequacy': {
                    'status': 'pending',
                    'checks': [{
                        'check_kind': 'intent_graph_adequacy',
                        'intent_obligation_id': 'dependency-test',
                        'status': 'pending',
                        'evidence': 'intent_graph_adequacy_missing_dependency_edge',
                        'repair_action': 'rebind_artifact_dependency',
                        'add_dependencies': [_edge(target, source)],
                    }],
                },
            },
        },
    }
    before = copy.deepcopy(payload)
    scoped = owner._attach_redraw_scope_ladder_review(payload)
    repair_graph = copy.deepcopy(scoped['runtime']['request_phase_graph'])
    closure = scoped['runtime']['graph_closure_review']
    proposals = build_graph_repair_proposals(request_phase_graph=repair_graph, closure_review=closure)
    reviews = [validate_graph_repair_proposal(
        proposal, request_phase_graph=repair_graph, closure_review=closure,
    ) for proposal in proposals]
    repair_graph['graph_repair_proposals'] = proposals
    repair_graph['graph_repair_reviews'] = reviews
    scoped['runtime']['request_phase_graph'] = repair_graph
    reviewed = owner._attach_runtime_graph_repair_evidence(scoped)
    result = owner._attach_graph_patch_lifecycle(reviewed, graph_repair_autonomy=autonomy)
    result_graph = result['runtime']['request_phase_graph']

    assert result_graph['redraw_scope_ladder_review']['selected_scope'] == 'repair_binding_dependency'
    assert result_graph['graph_repair_reviews'][0]['status'] == expected
    assert payload == before
    if expected == 'rejected':
        assert not result_graph.get('applied_graph_patches')
        assert result_graph['graph_patch_lifecycle'][0]['status'] == 'rejected'
        for collection in ('phases', 'downstream_branches', 'output_obligations'):
            assert result_graph.get(collection, []) == graph[collection]
    else:
        assert result_graph['graph_patch_lifecycle'][0]['status'] == 'applied'
        phase = next(item for item in result_graph['phases'] if item['phase_id'] == target)
        assert phase['depends_on'] == [source]


def test_dependency_topology_handles_long_chains_without_recursion_limit():
    graph = _graph(*[_phase(i, [f'phase-{i - 1}'] if i else []) for i in range(1100)])
    review = _review(graph, {'add_dependencies': [_edge('phase-0', 'branch-1099')]})

    assert review['status'] == 'rejected'
    assert 'dependency_cycle' in review['reasons']
