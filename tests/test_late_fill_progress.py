"""Progress through the real worker, with local state and deterministic providers."""
from copy import deepcopy
from dataclasses import replace
from unittest.mock import patch

import pytest

from fruth_server.multi_materialization_runtime import MultiMaterializationRuntimeOwner
from fruth_services import events
from fruth_webserver import _LATE_FILL_RUNTIME


def branch(name, capability='chat', *, waiting=False, depends_on=()):
    item = {
        'branch_id': name, 'phase_id': name, 'capability': capability,
        'output_type': 'image' if capability == 'image_generation' else 'text',
        'status': 'pending', 'content_payload': 'Produce ' + name,
        'artifact_prompt': 'Draw ' + name,
        'stage_direction': 'follow_up_text', 'depends_on': list(depends_on) or ['phase-1'],
    }
    if waiting:
        item['availability_wait'] = {
            'status': 'waiting', 'reason': 'live_candidates_in_cooldown',
            'candidate_instance_ids': ['fixture-' + name],
            'started_at_epoch': 99.0, 'next_check_epoch': 100.0, 'check_count': 1,
        }
    return item


def run_worker(branches, *, unavailable, targets, clock_step=0.0):
    """Cancel unavailable producers after the target work has actually executed.

    A finite test guard fails an unfair execution trace; it is not a runtime
    timeout or an assertion about providers eventually becoming available.
    """
    store, publications, prepared, executed, sleeps, released = {}, [], [], [], [], []
    clock, prepared_at = [100.0], []
    response_id = 'progress-fixture'
    payload = {
        'id': response_id, 'mode': 'chat', 'status': 'completed', 'output_text': 'seed',
        'runtime': {'request_phase_graph': {
            'current_phase_id': 'phase-1',
            'phases': [{'phase_id': 'phase-1', 'capability': 'chat', 'status': 'completed'},
                       *deepcopy(branches)],
            'downstream_branches': deepcopy(branches),
        }},
        'late_fill': {'status': 'pending', 'pending_branches': deepcopy(branches),
                      'expected_capability': 'chat'},
    }

    def lookup(rid):
        record = deepcopy(store.get(rid))
        if record and set(targets).issubset(executed):
            record['response_payload']['late_fill']['branch_controls'] = [
                {'branch_id': name, 'action': 'cancelled', 'authority': 'user',
                 'reason': 'Fixture ends unavailable work after sibling progress.'}
                for name in (item['branch_id'] for item in branches)
                if name not in targets
            ]
        return record

    def touch(rid, **kwargs):
        publications.append(deepcopy(kwargs))
        if 'response_payload' in kwargs:
            store[rid] = {'response_payload': deepcopy(kwargs['response_payload'])}
        return store.get(rid)

    def prepare(**kwargs):
        name = kwargs['artifact_gap']['branch_id']
        prepared.append(name)
        prepared_at.append(clock[0])
        assert len(prepared) <= 20, ('ready work was starved', prepared)
        clock[0] += clock_step
        if name in unavailable:
            error = RuntimeError("No ready late-fill instance for capability 'image_generation'.")
            error.route_diagnostics = {'availability_wait': {
                'reason': 'live_candidates_in_cooldown',
                'candidate_instance_ids': ['fixture-' + name],
            }}
            raise error
        return {'route_info': {'instance_id': 'fixture-' + name},
                'instance': {}, 'effective_data': {}}

    def execute(plan):
        name = plan['branch_id']
        executed.append(name)
        return {'route_info': plan['route_info'], 'instance': {},
                'effective_data': {}, 'infer_result': {'content': 'Result for ' + name}}

    def sleep(seconds):
        sleeps.append(seconds)
        assert len(sleeps) <= 20, ('ready work was starved while sleeping', prepared)
        assert 0 < seconds <= 1
        clock[0] += seconds

    owner = replace(
        _LATE_FILL_RUNTIME,
        get_response_lookup_record=lookup, touch_response_lookup=touch,
        ensure_response_lookup_for_payload=lambda *a, **kw: None,
        finalize_response_frame_payload=lambda value, **kw: deepcopy(value),
        response_registry_now_iso=lambda: '2026-10-05T12:00:00Z',
        log_unified_event=lambda **entry: None,
        release_response_late_fill=lambda rid: released.append(rid),
        schedule_post_response_substrate_hygiene=None,
        prepare_terminal_graph_patch_successor=None,
        project_terminal_closure_repair=None, review_terminal_graph_rebase=None,
        attach_runtime_graph_repair_evidence=None,
        load_latest_response_state=None, load_latest_response_observation_state=None,
        execute_materialization_branches=MultiMaterializationRuntimeOwner(
            max_parallel_workers=1).execute_materialization_branches,
    )
    with patch('fruth_server.late_fill_runtime.time.time', side_effect=lambda: clock[0]), \
            patch('fruth_server.late_fill_runtime.time.sleep', side_effect=sleep), \
            patch.dict('os.environ', {'FRUTH_LATE_FILL_AVAILABILITY_POLL_SEC': '1'}), \
            events.causal_scope(lambda **entry: None, response_id=response_id):
        owner.complete_response_late_fill(
            response_payload=payload, request_payload={'prompt': 'Run the admitted branches.'},
            assistant_message='seed', artifact_gap={'expected_capability': 'chat',
                'pending_branches': deepcopy(branches), 'trigger': 'fixture'},
            source_route_payload=None, prepare_late_fill_branch_plan=prepare,
            execute_prepared_late_fill_branch=execute,
        )
    assert released == [response_id]
    return {'prepared': prepared, 'prepared_at': prepared_at,
            'executed': executed, 'sleeps': sleeps,
            'publications': publications, 'payload': store[response_id]['response_payload']}


@pytest.mark.parametrize('initial_wait', [False, True])
@pytest.mark.parametrize('clock_step', [0.0, 2.0])
def test_unavailable_image_cannot_starve_independent_ready_chat(initial_wait, clock_step):
    run = run_worker([
        branch('image', 'image_generation', waiting=initial_wait), branch('text'),
    ], unavailable={'image'}, targets={'text'}, clock_step=clock_step)
    assert run['executed'] == ['text'], (run['prepared'], run['payload']['late_fill'].get('error'))
    assert run['prepared'].count('image') <= 1
    assert not run['payload']['late_fill']['pending_branches']
    assert run['payload']['late_fill']['cancelled_branches'][0]['branch_id'] == 'image'


@pytest.mark.parametrize('clock_step', [0.0, 2.0])
def test_due_waiters_cannot_starve_each_other_by_capability_priority(clock_step):
    run = run_worker([
        branch('image', 'image_generation', waiting=True), branch('text', waiting=True),
    ], unavailable={'image'}, targets={'text'}, clock_step=clock_step)
    assert run['executed'] == ['text'], (run['prepared'], run['payload']['late_fill'].get('error'))
    assert run['prepared'].count('image') <= 1
    assert not run['payload']['late_fill']['pending_branches']


def test_ready_branch_positive_control():
    run = run_worker([branch('text')], unavailable=set(), targets={'text'})
    assert run['executed'] == ['text']
    assert run['payload']['late_fill']['status'] == 'completed'


def test_recovered_waiter_does_not_wait_for_new_waiter_to_catch_up_in_poll_count():
    older = branch('text', waiting=True)
    older['availability_wait']['check_count'] = 1000
    older['availability_wait']['next_check_epoch'] = 99.0
    run = run_worker([
        branch('image', 'image_generation', waiting=True), older,
    ], unavailable={'image'}, targets={'text'}, clock_step=2.0)
    assert run['executed'] == ['text']
    assert run['prepared'] == ['text']


def test_independent_dependency_chain_advances_past_waiting_image():
    run = run_worker([
        branch('image', 'image_generation', waiting=True),
        branch('first'), branch('second', depends_on=['first']),
        branch('third', depends_on=['second']),
    ], unavailable={'image'}, targets={'first', 'second', 'third'})
    assert run['executed'] == ['first', 'second', 'third']
    assert run['prepared'] == run['executed']
    assert not run['payload']['late_fill']['pending_branches']


def test_wait_selection_never_skips_a_real_dependency():
    run = run_worker([
        branch('image', 'image_generation', waiting=True), branch('text'),
        branch('consumer', depends_on=['image']),
    ], unavailable={'image'}, targets={'text'})
    assert run['executed'] == ['text']
    assert 'consumer' not in run['prepared']


def test_future_wait_is_not_probed_until_due():
    text = branch('text', waiting=True)
    text['availability_wait']['next_check_epoch'] = 103.0
    run = run_worker([text], unavailable=set(), targets={'text'})
    assert run['prepared'] == ['text']
    assert run['prepared_at'] == [103.0]
    assert sum(run['sleeps']) == 3.0


def test_active_images_keep_the_existing_resource_guard():
    candidates = [branch('image', 'image_generation'), branch('text')]
    before = deepcopy(candidates)
    active, policy = _LATE_FILL_RUNTIME.select_active_late_fill_branches(candidates)
    assert [item['branch_id'] for item in active] == ['image']
    assert policy['reason'] == 'required_image_generation_first'
    assert candidates == before


@pytest.mark.parametrize('deadline', [None, 'invalid', float('inf'), float('nan'), 1000.0])
def test_stale_wait_deadline_gets_revalidated_instead_of_starved(deadline):
    text = branch('text', waiting=True)
    text['availability_wait']['next_check_epoch'] = deadline
    run = run_worker([
        branch('image', 'image_generation', waiting=True), text,
    ], unavailable={'image'}, targets={'text'})
    assert run['executed'] == ['text']
    assert run['prepared'] == ['text']
