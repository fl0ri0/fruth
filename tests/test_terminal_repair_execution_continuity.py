"""Execution identity survives ordinary Late Fill state transitions."""
from copy import deepcopy
from dataclasses import replace
import threading

import pytest

import fruth_webserver as web
from fruth_server.responses_runtime import (
    ResponseMutationConflict, require_response_mutation_base,
)


REOPEN = {
    'kind': 'fruth.terminal_closure_repair_reopen',
    'status': 'queued',
    'execution_key': 'terminal-closure-repair-fixture',
    'authority': 'terminal_graph_closure_review',
    'parent_frame_id': 'repair-fixture:frame-1',
    'branch_ids': ['repair-local'],
    'contract_ids': ['repair-contract-local'],
}


def test_running_state_preserves_terminal_repair_execution():
    """The child's first publication must retain its admitted execution key."""
    prior = {'status': 'pending', 'terminal_closure_repair_reopen': deepcopy(REOPEN),
             'fill_results': [{'branch_id': 'accepted-sibling', 'content': 'retained'}]}
    admitted = {'id': 'repair-fixture', 'late_fill': deepcopy(prior)}
    running = web._build_late_fill_state(
        {'expected_capability': 'chat'}, status='running', prior_state=prior)
    candidate = web._attach_late_fill_state(admitted, running)
    # This is the real mutation check used by the worker before publication.
    require_response_mutation_base(candidate, admitted)
    assert candidate['late_fill']['terminal_closure_repair_reopen'] == REOPEN
    assert candidate['late_fill']['fill_results'] == prior['fill_results']


@pytest.mark.parametrize('change', ['missing', 'foreign'])
def test_changed_execution_still_rejects(change):
    admitted = {'id': 'repair-fixture', 'late_fill': {
        'terminal_closure_repair_reopen': deepcopy(REOPEN)}}
    candidate = deepcopy(admitted)
    if change == 'missing':
        candidate['late_fill'].pop('terminal_closure_repair_reopen')
    else:
        candidate['late_fill']['terminal_closure_repair_reopen']['execution_key'] = 'foreign'
    with pytest.raises(ResponseMutationConflict, match='execution changed'):
        require_response_mutation_base(candidate, admitted)


@pytest.mark.parametrize('key', ['terminal_closure_repair_reopen', 'partial_rebase_execution'])
@pytest.mark.parametrize('status', ['pending', 'running', 'completed', 'partial_failed', 'cancelled'])
@pytest.mark.parametrize('carrier', ['prior', 'gap'])
def test_execution_envelope_survives_state_rebuild_by_value(key, status, carrier):
    record = deepcopy(REOPEN)
    if key == 'partial_rebase_execution':
        record.update(kind='fruth.graph_rebase_partial_successor_execution',
                      execution_key='partial-fixture', root_prompt_replay=False)
    prior = {key: record} if carrier == 'prior' else {}
    gap = {key: record} if carrier == 'gap' else {}
    state = web._build_late_fill_state(gap, status=status, prior_state=prior)
    assert state[key] == record
    state[key]['branch_ids'].append('not-admitted')
    assert record['branch_ids'] == ['repair-local'], 'state aliased prior authority'


def test_state_builder_does_not_invent_execution_authority():
    state = web._build_late_fill_state({'expected_capability': 'chat'}, status='running')
    assert not any(key in state for key in (
        'terminal_closure_repair_reopen', 'partial_rebase_execution', 'successor_reopen_execution'))


@pytest.mark.parametrize('terminal_key', ['completed_branches', 'failed_branches', 'cancelled_branches'])
@pytest.mark.parametrize('pending_kind', ['admitted', 'same_terminal_id', 'foreign_execution', 'unbound', 'unadmitted', 'malformed_admission'])
def test_terminal_member_does_not_suppress_exact_pending_sibling(terminal_key, pending_kind):
    execution_key = REOPEN['execution_key']
    terminal = {'branch_id': 'settled', 'terminal_closure_repair_execution_key': execution_key}
    pending = {'branch_id': 'pending', 'terminal_closure_repair_execution_key': execution_key}
    if pending_kind == 'same_terminal_id':
        pending['branch_id'] = 'settled'
    elif pending_kind == 'foreign_execution':
        pending['terminal_closure_repair_execution_key'] = 'foreign'
    elif pending_kind == 'unbound':
        pending.pop('terminal_closure_repair_execution_key')
    elif pending_kind == 'unadmitted':
        pending['branch_id'] = 'foreign-duty'
    payload = {'late_fill': {
        'terminal_closure_repair_reopen': {**REOPEN, 'branch_ids': ['settled', 'pending']},
        terminal_key: [terminal], 'pending_branches': [pending],
    }}
    if pending_kind == 'malformed_admission':
        payload['late_fill']['terminal_closure_repair_reopen']['branch_ids'] = ['settled', {'branch_id': 'pending'}]
    assert web._LATE_FILL_RUNTIME._payload_has_terminal_closure_repair_execution(
        payload, execution_key) is (pending_kind != 'admitted')


@pytest.mark.parametrize('terminal_repair', [False, True])
def test_real_scheduled_worker_preserves_repair_identity(terminal_repair, monkeypatch):
    """Exercise publication, dispatch, persistence and replay, not TESTING's shortcut.

    The admitted branch is fixture input; only provider transport is synthetic.
    """
    from tests.fake_backends import FakeBackendHarness

    branch = {
        'branch_id': 'repair-local', 'phase_id': 'phase-2', 'capability': 'chat',
        'output_type': 'text', 'status': 'pending', 'contract_state': 'promoted',
        'obligation_id': 'obligation-summary', 'content_payload': 'Say: Alpine winds.',
        'content_payload_source': 'explicit_phase_contract',
        'stage_direction': 'write_text_after_artifact_generation',
        'depends_on': [], 'output_contract': {'required': True, 'output_type': 'text'},
    }
    if terminal_repair:
        branch['terminal_closure_repair_execution_key'] = REOPEN['execution_key']
    graph = {
        'kind': 'fruth.request_phase_graph', 'current_phase_id': 'phase-1',
        'current_phase_capability': 'chat', 'current_phase_resolution': 'graph_resolved',
        'phases': [{'phase_id': 'phase-1', 'capability': 'chat', 'status': 'fulfilled'}, branch],
        'downstream_branches': [branch], 'output_obligations': [{
            'obligation_id': branch['obligation_id'], 'branch_id': branch['branch_id'],
            'phase_id': branch['phase_id'], 'contract_state': 'promoted',
            'output_type': 'text', 'required': True,
        }],
    }
    request = {'prompt': 'Provide a short alpine summary.', 'inference_route': True}
    late = {'status': 'pending', 'pending_branches': [deepcopy(branch)], 'fill_results': []}
    if terminal_repair:
        late.update(terminal_closure_repair_reopen=deepcopy(REOPEN),
                    authoritative_pending_branches=True,
                    pending_branch_scope='exact_terminal_closure_repair')
    payload = {'id': 'scheduled-repair-fixture', 'object': 'response',
               'output_text': 'Preparing the summary.', 'runtime': {'request_phase_graph': graph},
               'late_fill': late}
    with FakeBackendHarness() as harness:
        runtime = web._LATE_FILL_RUNTIME
        calls, events, errors, workers = [], [], [], []
        done = threading.Event()
        for instance in harness.instances.values():
            instance['runtime_status'].update(process_alive=True, port_listening=True)
        monkeypatch.setattr(runtime, 'load_running_instances', lambda: list(harness.instances.values()))
        monkeypatch.setattr(runtime, 'merge_instances_with_runtime_status', lambda entries, **kw: entries)
        monkeypatch.setattr(web, '_invoke_internal_api_json_route',
                            lambda **kw: (calls.append(deepcopy(kw['payload'])) or {'content': 'Alpine winds.'}, 200))
        runtime = replace(runtime, log_unified_event=lambda **event: events.append(event))
        with web.app.app_context():
            admitted = harness.freeze_manual_response(payload, request_payload=request)
            runtime.touch_response_lookup(payload['id'], response_payload=admitted)
        original = harness.response_frames_dir.joinpath('responses.jsonl').read_bytes()

        def worker(**kwargs):
            workers.append(threading.current_thread())
            try:
                with web.app.app_context():
                    runtime.complete_response_late_fill(**kwargs)
            except BaseException as exc:
                errors.append(exc)
            finally:
                done.set()

        with web.app.app_context():
            assert web.app.config['TESTING'] is False
            handoff = (runtime._terminal_closure_repair_handoff(
                admitted, request_payload=request, assistant_message=payload['output_text'],
                source_route_payload=None) if terminal_repair else {
                'response_payload': admitted, 'request_payload': request,
                'assistant_message': payload['output_text'], 'artifact_gap': {
                    **deepcopy(late), 'expected_capability': 'chat',
                    'authoritative_pending_branches': True},
                'source_route_payload': None})
            assert handoff is not None
            assert runtime.schedule_response_late_fill(**handoff, complete_response_late_fill=worker)
        assert done.wait(30), 'bounded worker did not finish'
        for thread in workers:
            thread.join(30)
            assert not thread.is_alive(), 'worker cleanup did not finish'
        assert not errors, errors
        assert not web._response_late_fill_is_in_flight(payload['id'])
        rejected = [e for e in events if e.get('status') == 'stale_result_rejected']
        assert not rejected, rejected
        assert len(calls) == 1, calls
        assert request['prompt'] not in calls[0]['prompt']
        assert 'Alpine winds.' in calls[0]['prompt']
        final = runtime.get_response_lookup_record(payload['id'])['response_payload']
        assert final['lifecycle_state'] == 'completed', final['late_fill']
        assert not final['late_fill'].get('pending_branches')
        if terminal_repair:
            assert final['late_fill']['terminal_closure_repair_reopen'] == REOPEN
        ledger = harness.response_frames_dir.joinpath('responses.jsonl').read_bytes()
        assert ledger.startswith(original), 'prior frame rewritten'
        harness.clear_response_lookup()
        recovered = harness.response_state(payload['id'])
        assert recovered['ok']
        assert recovered['response_payload']['lifecycle_state'] == 'completed'
        if terminal_repair:
            assert runtime._payload_has_terminal_closure_repair_execution(
                recovered['response_payload'], REOPEN['execution_key'])
        if terminal_repair:
            before = len(calls)
            with web.app.app_context():
                runtime.complete_response_late_fill(response_payload=admitted, request_payload=request,
                    assistant_message=payload['output_text'], artifact_gap=late, source_route_payload=None)
            assert len(calls) == before, 'completed terminal handoff redispatched'
