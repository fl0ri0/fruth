"""Focused corrections; the original stateful model and replay inputs stay intact."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from hypothesis import reproduce_failure
from hypothesis.errors import DidNotReproduce
from hypothesis.stateful import get_state_machine_test
import pytest

import fruth_webserver as web
from fruth_services.graph_repair import validate_graph_repair_proposal
from fruth_services.response_frames import load_latest_response_state
import tests.test_graph_repair_self_healing as repair_fixtures

from tests.test_graph_lineage_stateful_hypothesis import (
    ERROR, GraphLineageMachine, PersistedGraphLineageMachine, budgets, graph_of, stable,
)
from tests.test_graph_lineage_successor_producer_regression import AutomaticSuccessorMachine


@pytest.mark.parametrize('lane,machine_type,blob', [
    ('producer', AutomaticSuccessorMachine, b'AXicY2BwBEIw4QhlMoFIAB2WAkw='),
    ('owner', GraphLineageMachine, b'AXicY2BwBEIwAYRMIBYQczAwMjhyAvkALCECoQ=='),
    ('adapter', PersistedGraphLineageMachine,
     b'AXicjUzZCUAxDLJHeozl/kvV5J3QnxIUxSgSQYDvgdn559OZrl6VQMDd+GYMiLjunYe7UOJteipJU6Pdc8q7rF07k3kBiagRvg=='),
])
def test_original_lineage_failure_blob_no_longer_reproduces(lane, machine_type, blob):
    machines = []

    def factory():
        machine = machine_type()
        machine.control = True
        machines.append(machine)
        return machine

    original_settings = (AutomaticSuccessorMachine.TestCase.settings
                         if lane == 'producer' else budgets(lane))
    replay = reproduce_failure('6.168.5', blob)(
        get_state_machine_test(factory, settings=original_settings))
    with pytest.raises(DidNotReproduce):
        replay()
    assert len(machines) == 1 and not machines[0].failed
    operations = machines[0].operations
    assert machines[0].model.admitted
    if lane != 'producer':
        assert machines[0].model.outcome == 'completed'
        assert any(op['operation'] == 'stale_callback' and op['status'] == 'completed'
                   for op in operations)


@pytest.mark.parametrize('location', ['phases', 'downstream_branches', 'output_obligations',
                                     'output_candidates', 'candidates', 'decisions'])
@pytest.mark.parametrize('matching', [False, True])
@pytest.mark.parametrize('disposition', ['reserved', 'deferred', 'omitted', 'not_promoted',
                                       'candidate_only', 'waived', 'superseded'])
def test_only_matching_structured_dispositions_reject(location, matching, disposition):
    fixture = repair_fixtures.GraphRepairSelfHealingTests()
    graph = fixture._base_graph()
    proposal = fixture._proposal()
    phase = proposal['patch']['add_phases'][0]
    phase['obligation_id'] = 'obligation-repair-image'
    phase['promoted_from_candidate_id'] = 'candidate-accepted-image'
    candidates, promotion = {}, {'status': 'promoted'}
    record = {'contract_state': disposition}
    if location in ('phases', 'downstream_branches'):
        # A phase/branch alias can bind the same accepted work without equal names.
        record.update(phase_id='repair-image' if matching else 'repair-image-unrelated',
                      branch_id='legitimate-branch-alias')
        graph.setdefault(location, []).append(record)
    elif location == 'output_obligations':
        record['obligation_id'] = ('obligation-repair-image' if matching else
                                   'obligation-repair-image-unrelated')
        graph[location] = [record]
    elif location == 'output_candidates':
        record['candidate_id'] = 'candidate-alias'
        record['promoted_obligation_id'] = ('obligation-repair-image' if matching else
                                            'obligation-repair-image-unrelated')
        graph['request_ir'] = {location: [record]}
    elif location == 'candidates':
        record['candidate_id'] = ('candidate-accepted-image' if matching else
                                   'candidate-accepted-image-unrelated')
        candidates[location] = [record]
    else:
        graph['promotions'] = [{'candidate_id': 'candidate-alias',
                               'obligation_id': 'obligation-repair-image'}]
        record = {'candidate_id': 'candidate-alias' if matching else 'candidate-alias-unrelated',
                  'decision': disposition}
        promotion[location] = [record]
    # Prose and scope/field names cannot bind a disposition to any identity.
    graph['redraw_scope_ladder_review'] = {
        'status': 'reserved', 'branch_id': 'repair-image',
        'selected_scope': 'reserved_candidate_fill', 'reason': 'repair-image may be deferred',
    }
    review = validate_graph_repair_proposal(proposal, request_phase_graph=graph,
        candidate_graph=candidates, promotion_review=promotion, closure_review=fixture._closure_review())
    assert ('deferred_or_reserved_intent_conflict' in review.get('reasons', [])) is matching
    assert review['status'] == ('rejected' if matching else 'accepted')


@pytest.mark.parametrize('field', ['status', 'contract_state', 'promotion_status', 'decision'])
def test_diagnostic_prose_and_field_names_are_not_dispositions(field):
    fixture = repair_fixtures.GraphRepairSelfHealingTests()
    graph = fixture._base_graph()
    proposal = fixture._proposal()
    graph['output_obligations'] = [{'branch_id': 'repair-image', field: 'accepted reserved prose',
                                    'reserved': True, 'reason': 'deferred repair-image diagnostics'}]
    review = validate_graph_repair_proposal(proposal, request_phase_graph=graph,
        closure_review=fixture._closure_review(), promotion_review={'status': 'promoted'})
    assert review['status'] == 'accepted'


@pytest.mark.parametrize('matching', [False, True])
def test_automatic_producer_keeps_real_reservation_gate(matching):
    machine = AutomaticSuccessorMachine()
    try:
        machine.accepted(True, 0)
        graph_of(machine.payload)['output_obligations'].append({
            'branch_id': 'repair-image' if matching else 'foreign-branch',
            'status': 'reserved', 'required': False,
        })
        prepared = machine.request_owner.prepare_terminal_graph_patch_successor(
            machine.finalize(machine.payload), graph_repair_autonomy='apply_safe')
        assert prepared['status'] == ('not_applicable' if matching else 'queued'), prepared
        assert not machine.harness.provider_calls
        if matching:
            assert 'deferred_or_reserved_intent_conflict' in stable(prepared)
    except BaseException:
        machine.failed = True
        raise
    finally:
        machine.teardown()


@contextmanager
def settled_machine(persistent, success, *, full_witness=False, missing_second=False):
    machine = PersistedGraphLineageMachine() if persistent else GraphLineageMachine()
    machine.control = full_witness
    try:
        machine.accepted(True, 1)
        if missing_second:
            graph_of(machine.payload)['downstream_branches'] = []
            graph_of(machine.payload)['downstream_branch_ids'] = []
        machine.freeze_parent()
        machine.admit()
        if success:
            machine.result(True)
        else:
            # Controlled owner error; frames/recovery still use real persistence.
            # This does not claim a real provider failure in the adapter lane.
            machine.persistent = False
            try:
                machine.result(False)
            finally:
                machine.persistent = persistent
        machine.conservation()
        yield machine
    except BaseException:
        machine.failed = True
        raise
    finally:
        machine.teardown()


def durable_evidence(value):
    """The frame omits transport bytes/timestamps/empty projections, not evidence."""
    if isinstance(value, dict):
        return {key: durable_evidence(item) for key, item in value.items()
                if key not in {'created_at', 'updated_at', 'started_at', 'completed_at',
                               'failed_at', 'image_data_url'} and item not in (None, '', [], {})}
    if isinstance(value, list):
        return [durable_evidence(item) for item in value]
    return value


@pytest.mark.parametrize('persistent', [False, True])
@pytest.mark.parametrize('success', [False, True])
@pytest.mark.parametrize('shape', ['missing', 'empty', 'partial', 'conflicting', 'no_execution'])
@pytest.mark.parametrize('boundary', ['callback', 'result'])
def test_repeated_terminal_callbacks_keep_exact_evidence(persistent, success, shape, boundary):
    with settled_machine(persistent, success,
                         full_witness=persistent and shape == 'conflicting') as machine:
        accepted = deepcopy(machine.payload['late_fill'])
        execution = deepcopy(accepted['successor_reopen_execution'])
        incoming = {'status': 'completed' if success else 'failed',
                    'successor_reopen_execution': execution,
                    'updated_at': '2026-10-09T12:00:00Z',
                    'timing': {'callback_observed': True}}
        if shape == 'no_execution':
            incoming.pop('successor_reopen_execution')
        elif shape == 'empty':
            incoming.update(fill_results=[], completed_branches=[], failed_branches=[],
                            cancelled_branches=[], error='', recovery_candidates=[])
        elif shape == 'partial':
            incoming['fill_results'] = [{'branch_id': 'repair-image', 'phase_id': 'repair-image'}]
            incoming['failed_branches'] = [{'branch_id': 'repair-image', 'error': {'message': ''}}]
        elif shape == 'conflicting':
            incoming.update(fill_results=[{'branch_id': 'foreign', 'phase_id': 'foreign',
                                          'saved_image_path': '/no-authority/foreign.png'}],
                            completed_branches=[{'branch_id': 'foreign', 'status': 'fulfilled'}],
                            failed_branches=[{'branch_id': 'repair-image',
                                              'error': {'code': 'REPLACEMENT_ERROR', 'retryable': True}}],
                            error='REPLACEMENT_ERROR', final_materialization_contract_status='fulfilled')
        result = {}
        if boundary == 'result' and shape == 'conflicting':
            foreign = machine.harness.images_dir / 'foreign-callback.png'
            foreign.write_bytes(machine.model.png)
            result = {'saved_image_path': str(foreign), 'branch_id': 'foreign', 'phase_id': 'foreign',
                      'artifacts': [{'type': 'image', 'path': str(foreign),
                                     'branch_id': 'foreign', 'phase_id': 'foreign'}]}
        before = deepcopy(machine.payload)
        if boundary == 'result':
            updated = machine.late.merge_late_fill_result_into_response_payload(
                machine.payload, result, incoming)
        else:
            updated = machine.late.attach_late_fill_state(machine.payload, incoming)
        machine.observations.append({'boundary': 'focused_terminal_' + boundary,
                                     'submitted': incoming, 'before': before, 'after': deepcopy(updated)})
        for key in accepted:
            if key not in {'updated_at', 'timing', 'scheduling_policy', 'successor_reopen_execution'}:
                assert updated['late_fill'][key] == accepted[key], key
        assert updated['late_fill']['timing'] == {'callback_observed': True}
        if boundary == 'result' and result:
            for key in ('saved_image_path', 'artifacts'):
                assert updated.get(key) == before.get(key), 'result callback replaced accepted ' + key
        machine.payload = updated
        machine.store = {'response_payload': deepcopy(updated)}
        machine.record('focused_terminal_callback', success=success, shape=shape, boundary=boundary)
        machine.freeze_result()
        machine.recover()
        machine.recover()
        machine.conservation()
        recovered = machine.observations[-1]['payload']['late_fill']
        for key in ('fill_results', 'completed_branches', 'failed_branches', 'error'):
            assert durable_evidence(recovered.get(key) or []) == durable_evidence(accepted.get(key) or []), \
                'recovered evidence changed: ' + key
        if not success:
            assert recovered['failed_branches'][0]['error']['code'] == ERROR


@pytest.mark.parametrize('status', ['completed', 'failed'])
@pytest.mark.parametrize('shape', ['empty', 'conflicting'])
def test_execution_record_replay_preserves_evidence_and_error_provenance(status, shape):
    accepted = {'successor_execution_key': 'accepted-key', 'status': status,
                'parent_frame_id': 'accepted-parent', 'scheduled_branch_ids': ['owed'],
                'late_fill_status': status, 'result': {'artifact_ref': 'artifact:accepted'},
                'error': {'code': ERROR, 'stage': 'execute_prepared_branch', 'source': 'provider'}}
    incoming = deepcopy(accepted)
    incoming.update(result={} if shape == 'empty' else {'artifact_ref': 'artifact:foreign'},
                    error='' if shape == 'empty' else {'code': 'REPLACEMENT_ERROR'},
                    late_fill_status='' if shape == 'empty' else 'pending',
                    updated_at='new-observation')
    merged = web._merge_graph_patch_successor_execution_truth(accepted, incoming)
    assert merged == {**accepted, 'updated_at': 'new-observation'}
    assert accepted['result']['artifact_ref'] == 'artifact:accepted'


@pytest.mark.parametrize('fault', ['foreign_key', 'old_key', 'parent', 'graph_digest',
                                  'scheduled_scope', 'empty_parent'])
def test_callbacks_cannot_reselect_execution_or_change_its_identity(fault):
    with settled_machine(False, True) as machine:
        before = deepcopy(machine.payload)
        execution = deepcopy(before['late_fill']['successor_reopen_execution'])
        if fault in {'foreign_key', 'old_key'}:
            execution['successor_execution_key'] = fault
            if fault == 'old_key':
                graph_of(machine.payload)['successor_reopen_executions'].insert(0, execution)
        else:
            key = {'parent': 'parent_frame_id', 'graph_digest': 'successor_graph_digest',
                   'scheduled_scope': 'scheduled_branch_ids', 'empty_parent': 'parent_frame_id'}[fault]
            execution[key] = (['foreign'] if fault == 'scheduled_scope' else
                              '' if fault == 'empty_parent' else 'foreign')
        updated = machine.late.attach_late_fill_state(machine.payload, {
            'status': 'completed', 'successor_reopen_execution': execution,
            'fill_results': [], 'completed_branches': []})
        assert updated['late_fill'] == before['late_fill']
        assert updated['runtime']['late_fill'] == before['runtime']['late_fill']
        machine.payload = updated
        machine.record('focused_execution_identity_rejection', fault=fault)
        machine.conservation()


def test_second_image_successor_requires_its_own_result():
    """New C5 boundary: repeated successors are outside the generated one-successor family."""
    with settled_machine(True, True, full_witness=True, missing_second=True) as machine:
        # A second independently accepted duty was present from initialization.
        machine.payload['late_fill']['pending_branches'] = [{
            'branch_id': 'unrelated-image', 'phase_id': 'unrelated-image',
            'obligation_id': 'obligation-unrelated-image', 'capability': 'image_generation',
            'output_type': 'image', 'status': 'pending',
            'artifact_prompt': 'Execute the separately accepted amber star.'}]
        machine.payload['late_fill'].update(status='partial_failed',
            materialization_contract_unmet=True, final_materialization_contract_status='unmet')
        parent = machine.finalize(machine.payload)
        prefix = machine.ledger_bytes()
        canonical = stable(parent['response_frame'])
        old_key = parent['late_fill']['successor_reopen_execution']['successor_execution_key']
        owner = replace(machine.request_owner, hooks={**machine.request_owner.hooks,
            'attach_late_fill_state': web._attach_late_fill_state,
            'build_late_fill_state': web._build_late_fill_state})
        def prepare_fresh(value):
            # The validated sink isolates this execution boundary from C3 in
            # the original automatic producer, without bypassing admission gates.
            reviewed = owner._attach_graph_patch_lifecycle(
                owner._attach_runtime_graph_repair_evidence(value), graph_repair_autonomy='apply_safe')
            candidate = next(item for item in graph_of(reviewed)['successor_reopen_requests']
                             if item.get('owed_branch_ids') == ['unrelated-image'])
            return owner._prepare_graph_patch_successor_reopen(reviewed, candidate)

        late = replace(machine.late, prepare_terminal_graph_patch_successor=prepare_fresh)
        fresh, handoff = late._prepare_terminal_graph_patch_successor_handoff(
            deepcopy(parent), request_payload=machine.request, assistant_message='',
            artifact_gap={}, source_route_payload=None)
        assert handoff and not handoff.get('skip_schedule'), handoff
        new_key = fresh['late_fill']['successor_reopen_execution']['successor_execution_key']
        assert new_key != old_key
        assert [branch['branch_id'] for branch in handoff['artifact_gap']['pending_branches']] == ['unrelated-image']
        late.complete_response_late_fill(response_payload=fresh, request_payload=machine.request,
            assistant_message='', artifact_gap=handoff['artifact_gap'], source_route_payload=None)
        settled = machine.store['response_payload']
        machine.counts['worker_calls'] += 1
        machine.counts['provider_induced_image_writes'] = len(list(machine.harness.images_dir.glob('*.png')))
        machine.record('focused_second_successor', new_key=new_key)
        recovered = load_latest_response_state('stateful-lineage',
            frames_dir=machine.harness.response_frames_dir)
        assert recovered['ok']
        machine.counts['durable_recovery_reads'] += 1
        machine.observations.append({'boundary': 'fresh_repair', 'parent': parent,
                                     'fresh': fresh, 'handoff': handoff, 'payload': settled,
                                     'recovered': recovered['response_payload']})
        assert stable(parent['response_frame']) == canonical
        assert machine.ledger_bytes().startswith(prefix)
        assert len(machine.harness.provider_calls) == 2
        assert 'Execute the separately accepted amber star.' in stable(machine.harness.provider_calls[-1])
        results = settled['late_fill']['fill_results']
        assert {record['branch_id'] for record in results} == {'repair-image', 'unrelated-image'}
        for record in results:
            assert Path(record['saved_image_path']).read_bytes() == machine.model.png


def test_fresh_gated_repair_after_a_terminal_execution_remains_possible():
    machine = PersistedGraphLineageMachine()
    machine.control = True
    try:
        machine.accepted(True, 0)
        # Independently accepted failed work and its original provider error.
        prior_execution = {'successor_execution_key': 'earlier-accepted-execution',
            'status': 'failed', 'parent_frame_id': 'earlier-parent', 'parent_frame_sequence': 1,
            'parent_response_id': 'stateful-lineage', 'scheduled_branch_ids': ['unrelated-image'],
            'late_fill_status': 'failed', 'error': {'code': ERROR, 'source': 'provider'}}
        graph_of(machine.payload)['successor_reopen_executions'] = [deepcopy(prior_execution)]
        machine.payload['late_fill'].update(successor_reopen_execution=deepcopy(prior_execution),
            failed_branches=[{'branch_id': 'unrelated-image', 'phase_id': 'unrelated-image',
                             'status': 'failed', 'error': {'code': ERROR, 'source': 'provider'}}])
        machine.request_owner = replace(machine.request_owner, hooks={**machine.request_owner.hooks,
            'attach_late_fill_state': web._attach_late_fill_state,
            'build_late_fill_state': web._build_late_fill_state})
        machine.freeze_parent()
        machine.admit()
        execution = machine.payload['late_fill']['successor_reopen_execution']
        assert execution['successor_execution_key'] != prior_execution['successor_execution_key']
        assert execution['parent_frame_id'] == machine.parent_frame['frame_id']
        assert execution['parent_frame_sequence'] == machine.parent_frame['frame_sequence']
        machine.result(True)
        machine.freeze_result()
        machine.recover()
        machine.conservation()
        assert len(machine.harness.provider_calls) == 1
        old_record = next(record for record in graph_of(machine.payload)['successor_reopen_executions']
                          if record['successor_execution_key'] == prior_execution['successor_execution_key'])
        assert old_record == prior_execution
        assert machine.parent['late_fill']['failed_branches'][0]['error'] == {
            'code': ERROR, 'source': 'provider'}
        machine.record('focused_fresh_gated_repair')
    except BaseException:
        machine.failed = True
        raise
    finally:
        machine.teardown()
