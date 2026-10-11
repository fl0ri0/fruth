"""Characterize the initial worker pass through its existing injected boundaries."""
from copy import deepcopy
from dataclasses import replace

import pytest

from fruth_server.multi_materialization_runtime import MultiMaterializationRuntimeOwner
from fruth_webserver import _LATE_FILL_RUNTIME


def branch(identity, capability='chat', **extra):
    record = dict(branch_id=identity, phase_id='phase-' + identity,
                  obligation_id='owed-' + identity, capability=capability,
                  content_payload='Execute ' + identity, output_type='text', queue_index=1)
    record.update(extra)
    return record


def initial_pass(monkeypatch, branches, *, prior=None, fulfilled=True):
    events, store, executed, selected = [], {}, [], []
    initial = True
    payload = dict(id='initial-eligibility', status='completed', output_text='seed',
                   late_fill=deepcopy(prior or {}))

    def note(*event):
        if initial:
            events.append(event)

    def gap(base, *, capability, artifact_payload, **kwargs):
        if 'pending_capabilities' not in kwargs:
            note('gap', capability)
        return dict(base, expected_capability=capability, **kwargs)

    def generic_evidence(gap, payload):
        note('generic', gap['expected_capability'])
        return fulfilled

    def batches(graph, **state):
        nonlocal initial
        if initial:
            selected.extend(deepcopy(state['pending_branches']))
        initial = False
        return [state['pending_branches']]

    def terminal(value, *, terminal_status, **kwargs):
        nonlocal initial
        initial = False
        return value, terminal_status

    def publish(identity, **kwargs):
        if 'response_payload' in kwargs:
            store[identity] = {'response_payload': deepcopy(kwargs['response_payload'])}
        return store.get(identity)

    def execute(plan):
        executed.append(plan['branch_id'])
        return {'route_info': {}, 'instance': {}, 'effective_data': {},
                'infer_result': {'content': 'answer ' + plan['branch_id']}}

    owner = replace(
        _LATE_FILL_RUNTIME,
        get_response_lookup_record=lambda identity: deepcopy(store.get(identity)),
        touch_response_lookup=publish,
        ensure_response_lookup_for_payload=lambda *a, **k: None,
        finalize_response_frame_payload=lambda value, **k: deepcopy(value),
        response_registry_now_iso=lambda: '2026-10-09T12:00:00Z',
        log_unified_event=lambda **k: None,
        release_response_late_fill=lambda identity: None,
        schedule_post_response_substrate_hygiene=None,
        prepare_terminal_graph_patch_successor=None,
        project_terminal_closure_repair=None,
        review_terminal_graph_rebase=None,
        attach_runtime_graph_repair_evidence=None,
        load_latest_response_state=None,
        load_latest_response_observation_state=None,
        # Inject at the selected boundary to retain legacy records and repeated
        # ids; the normal builder's separate normalization contract is unchanged.
        build_pending_late_fill_branches=lambda **k: deepcopy(branches),
        artifact_gap_is_already_fulfilled=generic_evidence,
        downstream_request_phase_batches=batches,
        execute_materialization_branches=MultiMaterializationRuntimeOwner(
            max_parallel_workers=1).execute_materialization_branches,
    )
    counts = owner.late_fill_capability_counts

    def count(values):
        note('counts', tuple(b.get('branch_id') for b in values))
        return counts(values)

    monkeypatch.setattr(owner, 'late_fill_capability_counts', count)
    monkeypatch.setattr(owner, 'finalize_terminal_materialization_contract', terminal)
    monkeypatch.setattr(owner, '_text_artifact_branch_has_canonical_evidence',
                        lambda b, p: (note('text', b['branch_id']) or fulfilled))
    monkeypatch.setattr(owner, '_terminal_materialization_branch_has_canonical_evidence',
                        lambda b, p, s: (note('image', b['branch_id']) or fulfilled))
    owner.complete_response_late_fill(
        response_payload=payload, request_payload={'prompt': 'Execute accepted branches.'},
        assistant_message='seed', artifact_gap={'expected_capability': 'chat',
            'pending_branches': deepcopy(branches), 'trigger': 'fixture'},
        source_route_payload=None, build_deferred_follow_up_gap_for_capability=gap,
        prepare_late_fill_branch_plan=lambda **k: {
            'route_info': {}, 'instance': {}, 'effective_data': {}},
        execute_prepared_late_fill_branch=execute,
    )
    return dict(events=events, selected=selected, executed=executed,
                late_fill=store[payload['id']]['response_payload']['late_fill'])


@pytest.mark.parametrize('field', ['completed_branches', 'failed_branches', 'cancelled_branches'])
def test_terminal_exclusion_precedes_evidence_and_counts_remain_unpruned(monkeypatch, field):
    first, second = branch('terminal'), branch('pending')
    run = initial_pass(monkeypatch, [first, second], prior={field: [first]})
    assert run['events'] == [('counts', ('terminal', 'pending')), ('gap', 'chat'), ('generic', 'chat')]
    # The terminal sibling still contributes to the original duplicate count.
    assert run['selected'] == [second]
    assert run['executed'] == ['pending']


@pytest.mark.parametrize('field', ['completed_capabilities', 'failed_capabilities', 'cancelled_capabilities'])
def test_legacy_terminal_capability_and_missing_capability_skip_evidence(monkeypatch, field):
    legacy = {'capability': 'chat'}
    missing = {'branch_id': 'missing', 'phase_id': 'missing'}
    prior_result = {'branch_id': 'previous', 'saved_image_path': '/retained/result.png',
                    'artifact_ref': 'artifact:previous', 'provenance': {'producer': 'previous'}}
    run = initial_pass(monkeypatch, [legacy, missing],
                       prior={field: ['chat'], 'fill_results': [prior_result]})
    assert run['events'] == [('counts', (None, 'missing'))]
    assert run['executed'] == []
    assert run['late_fill']['fill_results'] == [prior_result]


def test_named_branch_is_not_excluded_by_legacy_capability(monkeypatch):
    item = branch('new')
    run = initial_pass(monkeypatch, [item], prior={'completed_capabilities': ['chat']}, fulfilled=False)
    assert run['events'] == [('counts', ('new',)), ('gap', 'chat'), ('generic', 'chat')]
    assert run['selected'] == [item]
    assert run['executed'] == ['new']


def test_earlier_caller_completion_excludes_later_matching_identity(monkeypatch):
    first = branch('same')
    second = branch('same', capability='speech_to_text')
    run = initial_pass(monkeypatch, [first, second])
    assert run['events'] == [('counts', ('same', 'same')), ('gap', 'chat'), ('generic', 'chat')]
    assert run['executed'] == []
    assert run['late_fill']['completed_branches'] == [dict(first, status='fulfilled')]
    assert run['late_fill']['completed_capabilities'] == ['chat']


def test_duplicate_guard_keeps_evidence_evaluation_and_order(monkeypatch):
    items = [branch('second'), branch('first')]
    run = initial_pass(monkeypatch, items)
    assert run['events'] == [('counts', ('second', 'first')),
                             ('gap', 'chat'), ('generic', 'chat'),
                             ('gap', 'chat'), ('generic', 'chat')]
    assert run['selected'] == items
    assert run['executed'] == ['second', 'first']


@pytest.mark.parametrize('capability', ['chat', 'image_generation'])
def test_required_text_evidence_precedes_modality_evidence(monkeypatch, capability):
    item = branch('text', capability=capability, requires_artifact=True,
                  output_type='text', text_artifact_extension='md',
                  stage_direction='materialize_requested_text_artifact')
    run = initial_pass(monkeypatch, [item])
    assert run['events'] == [('counts', ('text',)), ('gap', capability), ('text', 'text')]
    assert run['executed'] == []


def test_image_uses_branch_evidence_after_gap_and_preserves_prior_result(monkeypatch):
    item = branch('image', capability='image_generation', output_type='image')
    result = {'branch_id': 'earlier', 'artifact_ref': 'artifact:earlier',
              'saved_image_path': '/retained/earlier.png', 'obligation_id': 'owed-earlier'}
    run = initial_pass(monkeypatch, [item], prior={'fill_results': [result]})
    assert run['events'] == [('counts', ('image',)), ('gap', 'image_generation'), ('image', 'image')]
    assert run['executed'] == []
    assert run['late_fill']['completed_branches'] == [dict(item, status='fulfilled')]
    assert run['late_fill']['fill_results'] == [result]
