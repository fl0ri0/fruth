"""Independent C9 pending-work expectations, using actual scheduler threads.

The accepted graph is fixture input. Provider transport alone is synthetic;
claims, mutation, scheduler, worker, evidence and durable recovery remain real.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import fruth_server.late_fill_runtime as late_module
import fruth_webserver as web
from tests.http_client import api_client
from tests.test_c9_continuation_hypothesis import ContinuationStudy, PROMPTS
from tests.test_graph_lineage_c3_c4_corrections import durable_evidence
from tests.test_graph_lineage_stateful_hypothesis import PREPARATION, stable
from tests.test_late_fill_control_overlap_hypothesis import RESPONSE_ID, WAIT_SECONDS


class PendingHandoffStudy(ContinuationStudy):
    """Only unlocked provider/control/child-entry seams are paused."""

    def __init__(self, reverse=False, *, child_mode='run'):
        self.target_reply = threading.Event()
        self.release_target = threading.Event()
        self.control_read = threading.Event()
        self.release_control = threading.Event()
        self.pending_reply = threading.Event()
        self.release_pending = threading.Event()
        self.child_arrived = threading.Event()
        self.release_child = threading.Event()
        self.parent_done = threading.Event()
        self.child_done = threading.Event()
        self.child_mode = child_mode
        self.competitor_claimed = False
        self.callbacks = []
        self.submissions = []
        self.entries = []
        self.claim_events = []
        self.transition_count = 0
        self.schedule = late_module.LateFillRuntimeOwner.schedule_response_late_fill
        super().__init__(reverse)
        # The historical constructor records handoffs. Restore the real scheduler
        # for this subclass only, without modifying that retained fixture.
        self.stack.enter_context(patch.object(type(self.engine.late),
                                             'schedule_response_late_fill', self.schedule))
        self.stack.enter_context(patch.dict(web.app.config, TESTING=False))
        original_log = self.engine.late.log_unified_event
        def log_event(**event):
            if event.get('action') != 'causal_observation':
                self.progress.record('runtime_event', value={k: deepcopy(event.get(k)) for k in ('action', 'status', 'message')})
            return original_log(**event)
        self.engine.late = replace(self.engine.late, log_unified_event=log_event)
        original_claim = self.engine.late.claim_response_late_fill
        original_release = self.engine.late.release_response_late_fill

        def claim(rid):
            second = any(a == 'claim' and ok for a, ok, _ in self.claim_events)
            if second and self.child_mode == 'claim_lost' and not self.competitor_claimed:
                assert original_claim(rid)
                self.competitor_claimed = True
                self.claim_events.append(('claim', True, 'competing-owner'))
            result = original_claim(rid)
            self.claim_events.append(('claim', result, threading.current_thread().name))
            if result and second and self.child_mode == 'cancel_after_claim':
                self.cancel_pending()
            return result

        def release(rid):
            self.claim_events.append(('release', True, threading.current_thread().name))
            original_release(rid)
            if self.child_mode == 'cancel_before_claim' and threading.current_thread().name == 'handoff-parent':
                self.cancel_pending()

        self.engine.late = replace(self.engine.late, claim_response_late_fill=claim,
                                  release_response_late_fill=release)
        original_thread = threading.Thread

        def thread_factory(*args, **kwargs):
            index = len(self.submissions)
            target, arguments = kwargs['target'], kwargs['kwargs']
            self.submissions.append(arguments)
            if index and self.child_mode == 'construction_failure':
                raise RuntimeError('controlled construction failure')
            if index and self.child_mode == 'cancel_before_start':
                self.cancel_pending()
            if index and self.child_mode == 'start_failure':
                return SimpleNamespace(start=lambda: (_ for _ in ()).throw(RuntimeError('controlled start failure')))

            def invoke():
                try:
                    if index:
                        self.child_arrived.set()
                        assert self.release_child.wait(WAIT_SECONDS), 'child entry fixture timeout'
                    self.entries.append(index)
                    with web.app.app_context():
                        target(**arguments)
                    if index == 0:
                        self.worker_result = {'return': None}
                except BaseException as exc:
                    self.errors.append(('child' if index else 'parent', exc))
                finally:
                    (self.child_done if index else self.parent_done).set()

            worker = original_thread(target=invoke, name='handoff-child' if index else 'handoff-parent', daemon=True)
            self.threads.append(worker)
            return worker

        self.stack.enter_context(patch.object(late_module, 'threading',
            SimpleNamespace(**{**vars(threading), 'Thread': thread_factory})))

    def install_seams(self):
        def lookup(rid):
            result = self.original_lookup(rid)
            if threading.current_thread().name == 'overlap-control' and not self.control_read.is_set():
                self.control_read.set()
                assert self.release_control.wait(WAIT_SECONDS), 'control admission fixture timeout'
            return result

        def provider(*args, **kwargs):
            result = self.original_provider(*args, **kwargs)
            if PROMPTS[self.target] in stable(kwargs.get('json', {})):
                self.target_reply.set()
                assert self.release_target.wait(WAIT_SECONDS), 'provider fixture timeout'
            if self.child_mode == 'cancel_after_dispatch' and PROMPTS[self.pending] in stable(kwargs.get('json', {})):
                self.pending_reply.set()
                assert self.release_pending.wait(WAIT_SECONDS), 'P provider fixture timeout'
            return result

        def materialize(*args, **kwargs):
            self.callbacks.append(kwargs['on_branch_progress'])
            result = self.original_materialize(*args, **kwargs)
            self.progress.record('materialized', value=deepcopy(result))
            return result

        def persist(*args, **kwargs):
            result = self.original_persist(*args, **kwargs)
            self.capture_commit('regular_append', kwargs.get('receipt'))
            return result

        def cas(*args, **kwargs):
            result = self.original_cas(*args, **kwargs)
            self.capture_commit('parent_cas', kwargs.get('receipt'))
            return result

        for obj, name, callback in ((web, '_get_response_lookup_record', lookup),
                                   (web.requests, 'post', provider),
                                   (web, '_persist_response_frame', persist),
                                   (web, '_append_response_frame_with_parent_cas', cas)):
            self.stack.enter_context(patch.object(obj, name, callback))
        self.engine.late = replace(self.engine.late, execute_materialization_branches=materialize)

    def transition(self, operation):
        self.transition_count += 1
        assert self.transition_count <= 32, 'actual transition cap'
        self.progress.record('transition', operation=operation)

    def start_parent(self):
        with web.app.app_context():
            assert self.schedule(self.engine.late,
                response_payload=deepcopy(self.initial_payload), request_payload=deepcopy(self.engine.request),
                assistant_message=PREPARATION,
                artifact_gap=deepcopy(self.machine.sequence.handoff['artifact_gap']), source_route_payload=None)
        self.transition('schedule_parent')
        assert self.target_reply.wait(WAIT_SECONDS), self.errors
        value = self.original_lookup(RESPONSE_ID)['response_payload']
        self.sibling_result = durable_evidence(next(r for r in value['late_fill']['fill_results']
                                                  if r['branch_id'] == self.sibling))
        assert not any(r.get('branch_id') == self.pending for r in value['late_fill']['fill_results'])
        self.transition('accept_S_and_dispatch_T')

    def admit_control(self):
        def invoke():
            try:
                self.control()
            except BaseException as exc:
                self.errors.append(('control', exc))
        worker = threading.Thread(target=invoke, name='overlap-control', daemon=True)
        self.threads.append(worker)
        worker.start()
        assert self.control_read.wait(WAIT_SECONDS), self.errors
        self.transition('admit_control')
        return worker

    def cancel_pending(self):
        with api_client(web.app) as client:
            result = client.post(f'/api/responses/{RESPONSE_ID}/late_fill/control', json={
                'branch_id': self.pending, 'action': 'cancel', 'reason': 'Cancel P at the child boundary.'})
        assert result.status_code == 200, result.get_json()
        self.transition('cancel_P')

    def finish_race(self, control_wins):
        control = self.admit_control()
        if control_wins:
            self.release_control.set()
            control.join(WAIT_SECONDS)
            assert not control.is_alive(), 'control fixture timeout'
            assert self.control_result['status_code'] == 200, self.control_result
            self.transition('commit_control')
            self.recover('control_before_provider_return')
            self.transition('passive_recovery_before_release')
            self.release_target.set()
        else:
            self.release_target.set()
            assert self.parent_done.wait(WAIT_SECONDS), self.errors
            self.release_control.set()
            control.join(WAIT_SECONDS)
            assert self.control_result['status_code'] == 409, self.control_result
        self.transition('release_provider_and_control')
        assert self.parent_done.wait(WAIT_SECONDS), self.errors
        self.transition('parent_exit')
        if self.errors:
            raise self.errors[0][1]

    def run_child(self):
        assert len(self.submissions) == 2, [e for e in self.progress.events if e['kind'] == 'runtime_event']
        assert self.child_arrived.wait(WAIT_SECONDS), ('no actual child', len(self.submissions), self.errors)
        self.transition('child_claimed_and_started')
        self.release_child.set()
        assert self.child_done.wait(WAIT_SECONDS), self.errors
        self.transition('child_entry_and_exit')
        if self.errors:
            raise self.errors[0][1]

    def observation(self):
        before = (len(self.submissions), len(self.engine.harness.provider_calls), self.engine.ledger_bytes())
        final = self.recover('settled')
        assert before == (len(self.submissions), len(self.engine.harness.provider_calls), self.engine.ledger_bytes()), 'passive read executed or wrote'
        self.transition('passive_recovery_settled')
        plans = [deepcopy(plan) for event in self.progress.events if event['kind'] == 'materialized'
                 for plan in event['value'].get('prepared_branch_plans', [])]
        return {'payload': final, 'entries': list(self.entries), 'plans': plans, 'passive_unchanged': True,
                'submissions': len(self.submissions), 'claims': list(self.claim_events),
                'pending_calls': sum(PROMPTS[self.pending] in stable(c['request'])
                                     for c in self.engine.harness.provider_calls),
                'ledger_prefix_preserved': self.engine.ledger_bytes().startswith(self.initial_ledger)}

    def assert_outcome(self, observed, *, continued, cancelled=True, pending_cancelled=False):
        value = observed['payload']
        # These assertions read output only; no production eligibility/authority
        # helper supplies expected truth.
        if not pending_cancelled:
            self.check_value(value, cancelled)
        else:
            invariant_view = deepcopy(value)
            invariant_view['late_fill'].setdefault('pending_branches', []).append(deepcopy(self.contracts[self.pending]))
            self.check_value(invariant_view, cancelled)
            assert any(b['branch_id'] == self.pending and b['status'] == 'cancelled'
                       for b in value['late_fill']['cancelled_branches'])
            assert not any(r['branch_id'] == self.pending for r in value['late_fill']['fill_results'])
        results = value['late_fill']['fill_results']
        assert sum(r['branch_id'] == self.pending for r in results) == int(continued)
        assert observed['pending_calls'] == int(continued)
        assert observed['ledger_prefix_preserved'], 'frozen history changed'
        assert observed['entries'] == ([0, 1] if cancelled and self.child_mode not in {'start_failure', 'construction_failure', 'cancel_before_claim', 'cancel_after_claim', 'claim_lost'} else [0])
        assert observed['submissions'] == (2 if cancelled and self.child_mode not in {'cancel_before_claim', 'cancel_after_claim', 'claim_lost'} else 1)
        held = False
        for action, success, _ in observed['claims']:
            if action == 'claim' and success:
                assert not held, 'two claimed workers'
                held = True
            elif action == 'release':
                assert held, 'release without ownership'
                held = False
        assert not held and not web._response_late_fill_is_in_flight(RESPONSE_ID)
        ctx = self.submissions[0].get('pending_continuation')
        assert ctx is not None and ctx.chain.attempts == int(cancelled)
        assert ctx.chain.submitted == ({self.sibling, self.target, self.pending} if continued else {self.sibling, self.target})
        assert not web._RESPONSES_RUNTIME._mutation_locks, 'mutation lock leaked'
        assert observed['passive_unchanged'], 'passive recovery executed'
        for plan in observed['plans']:
            branch = plan['branch_id']
            assert plan['effective_data']['prompt'] == PROMPTS[branch]
            binding = plan['execution_contract']
            assert binding['branch_id'] == binding['phase_id'] == branch
            assert binding['output_obligation_ref']['obligation_id'] == 'obligation-' + branch
            assert binding['depends_on'] == self.contracts[branch]['depends_on']
        self.check_dispatch()

    def close(self):
        self.release_target.set()
        self.release_pending.set()
        self.release_control.set()
        self.release_child.set()
        if self.submissions and self.submissions[0].get('pending_continuation'):
            ctx = self.submissions[0]['pending_continuation']
            now = self.original_lookup(RESPONSE_ID)['response_payload']
            self.source_inputs['admission_comparison'] = {
                'graph_equal': ctx.chain.admission.get('runtime', {}).get('request_phase_graph') == now.get('runtime', {}).get('request_phase_graph'),
                'request': [ctx.chain.admission.get('request'), now.get('request')],
                'frame_request': [ctx.chain.admission.get('response_frame', {}).get('request'), now.get('response_frame', {}).get('request')]}
        self.source_inputs.update(family='c9_pending_handoff', actual_transitions=self.transition_count,
                                 observed_child_entries=self.entries, submissions=len(self.submissions),
                                 child_mode=self.child_mode, claim_events=self.claim_events,
                                 context_present=bool(self.submissions and self.submissions[0].get('pending_continuation')),
                                 attempts=(self.submissions[0]['pending_continuation'].chain.attempts
                                           if self.submissions and self.submissions[0].get('pending_continuation') else None))
        super().close()


def exercise_handoff(control_wins=True, reverse=False, child_mode='run', sensitivity=False, probes=0, duplicate=False):
    study = PendingHandoffStudy(reverse, child_mode=child_mode)
    try:
        study.source_inputs.update(control_wins=control_wins, probes=probes, duplicate=duplicate)
        study.start_parent()
        study.finish_race(control_wins)
        for _ in range(probes):
            before = (len(study.submissions), len(study.engine.harness.provider_calls), study.engine.ledger_bytes())
            value = study.recover('generated_passive_probe')
            study.check_value(value, control_wins)
            assert before == (len(study.submissions), len(study.engine.harness.provider_calls), study.engine.ledger_bytes())
            study.transition('passive_probe')
        if duplicate and control_wins and child_mode != 'start_failure':
            assert study.schedule(study.engine.late, **study.submissions[1]) is False
            study.transition('duplicate_trigger_denied')
        if control_wins and child_mode != 'start_failure':
            if child_mode == 'cancel':
                assert study.child_arrived.wait(WAIT_SECONDS)
                study.cancel_pending()
            study.run_child()
        observed = study.observation()
        continued = not control_wins or child_mode == 'run'
        study.assert_outcome(observed, continued=continued, cancelled=control_wins,
                             pending_cancelled=control_wins and child_mode == 'cancel')
        study.source_inputs['classification'] = ('finite_continuation_completed' if continued else
            'acknowledged_cancelled' if child_mode == 'cancel' else 'unresolved_submission_failure')
        if sensitivity:
            for fault in ('sibling', 'cancelled', 'pending_call', 'child_entry', 'duplicate_claim', 'frozen',
                          'prompt', 'obligation', 'dependency', 'extra_release', 'double_dispatch', 'passive'):
                bad = deepcopy(observed)
                if fault == 'sibling':
                    bad['payload']['late_fill']['fill_results'] = [r for r in bad['payload']['late_fill']['fill_results']
                                                                  if r['branch_id'] != study.sibling]
                elif fault == 'cancelled':
                    bad['payload']['late_fill']['cancelled_branches'] = []
                elif fault == 'pending_call':
                    bad['pending_calls'] = 0
                elif fault == 'child_entry':
                    bad['entries'] = [0]
                elif fault == 'duplicate_claim':
                    bad['claims'].insert(1, ('claim', True, 'foreign'))
                elif fault in {'prompt', 'obligation', 'dependency'}:
                    plan = next(p for p in bad['plans'] if p['branch_id'] == study.pending)
                    if fault == 'prompt':
                        plan['effective_data']['prompt'] = 'replay root'
                    elif fault == 'obligation':
                        plan['execution_contract']['output_obligation_ref']['obligation_id'] = 'foreign'
                    else:
                        plan['execution_contract']['depends_on'] = [study.target]
                elif fault == 'extra_release':
                    bad['claims'].insert(2, ('release', True, 'loser'))
                elif fault == 'double_dispatch':
                    bad['pending_calls'] = 2
                elif fault == 'passive':
                    bad['passive_unchanged'] = False
                else:
                    bad['ledger_prefix_preserved'] = False
                with pytest.raises(AssertionError):
                    study.assert_outcome(bad, continued=True)
                study.progress.record('sensitivity_detected', fault=fault)
        return observed
    except BaseException:
        study.failed = True
        raise
    finally:
        study.close()


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('control_wins', [False, True])
def test_actual_scheduler_positive(control_wins, reverse):
    exercise_handoff(control_wins, reverse)


def test_independent_child_oracle_sensitivity():
    exercise_handoff(sensitivity=True)


@pytest.mark.parametrize('child_mode', ['cancel', 'start_failure'])
def test_actual_child_handoff_failure_boundaries(child_mode):
    exercise_handoff(child_mode=child_mode)


def assert_safe_stop(study, *, pending_cancelled=False, evidence_removed=False, pending_calls=0):
    value = study.observation()['payload']
    late = value['late_fill']
    assert not any(r['branch_id'] in {study.target, study.pending} for r in late['fill_results'])
    assert any(b['branch_id'] == study.target and b['status'] == 'cancelled' for b in late['cancelled_branches'])
    bucket = 'cancelled_branches' if pending_cancelled else 'pending_branches'
    assert any(b['branch_id'] == study.pending for b in late[bucket])
    assert not any(b['branch_id'] == study.pending for b in late.get('failed_branches', []))
    if not evidence_removed:
        own = next(r for r in late['fill_results'] if r['branch_id'] == study.sibling)
        assert durable_evidence(own) == study.sibling_result
    assert sum(PROMPTS[study.pending] in stable(c['request']) for c in study.engine.harness.provider_calls) == pending_calls
    assert study.engine.ledger_bytes().startswith(study.initial_ledger)
    assert not web._response_late_fill_is_in_flight(RESPONSE_ID)
    assert not web._RESPONSES_RUNTIME._mutation_locks
    assert study.submissions[0]['pending_continuation'].chain.attempts == 1


@pytest.mark.parametrize('mode', ['construction_failure', 'cancel_before_claim', 'cancel_after_claim',
                                  'cancel_before_start', 'claim_lost'])
def test_claim_and_submission_seams(mode):
    study = PendingHandoffStudy(child_mode=mode)
    try:
        study.start_parent()
        study.finish_race(True)
        if mode == 'cancel_before_start':
            study.run_child()
        if mode == 'claim_lost':
            assert web._response_late_fill_is_in_flight(RESPONSE_ID), 'loser released winner'
            assert len(study.submissions) == 1
            study.engine.late.release_response_late_fill(RESPONSE_ID)
        assert_safe_stop(study, pending_cancelled=mode.startswith('cancel'))
        context = study.submissions[0]['pending_continuation']
        assert study.engine.late._prepare_pending_control_handoff(context,
            artifact_gap=study.machine.sequence.handoff['artifact_gap'], source_route_payload=None) is None
        assert context.chain.attempts == 1, 'denied attempt refunded its budget'
    except BaseException:
        study.failed = True
        raise
    finally:
        study.close()


@pytest.mark.parametrize('change', ['frame', 'execution', 'parent', 'digest', 'scheduled_scope',
                                   'prompt', 'obligation', 'dependency', 'unknown_contract',
                                   'graph', 'evidence_loss', 'physical_loss', 'uncertain'])
def test_child_entry_rechecks_current_authority(change):
    study = PendingHandoffStudy()
    try:
        study.start_parent()
        study.finish_race(True)
        assert study.child_arrived.wait(WAIT_SECONDS)
        value = deepcopy(study.original_lookup(RESPONSE_ID)['response_payload'])
        late = value['late_fill']
        pending = next(b for b in late['pending_branches'] if b['branch_id'] == study.pending)
        if change == 'frame':
            value = study.original_finalize(value, request_payload=study.engine.request, persist=True)
        elif change in {'execution', 'parent', 'digest', 'scheduled_scope'}:
            key = {'execution': 'successor_execution_key', 'parent': 'parent_response_id',
                   'digest': 'successor_graph_digest', 'scheduled_scope': 'scheduled_branch_ids'}[change]
            late['successor_reopen_execution'] = {key: ['different'] if change == 'scheduled_scope' else 'different'}
        elif change in {'prompt', 'obligation', 'dependency', 'unknown_contract'}:
            key = {'prompt': 'artifact_prompt', 'obligation': 'obligation_id',
                   'dependency': 'depends_on', 'unknown_contract': 'new_semantic_field'}[change]
            pending[key] = [study.target] if change == 'dependency' else 'changed'
        elif change == 'graph':
            value['runtime']['request_phase_graph']['downstream_branch_ids'].append('foreign')
        elif change == 'evidence_loss':
            late['fill_results'] = []
        elif change == 'physical_loss':
            Path(next(r for r in late['fill_results'] if r['branch_id'] == study.sibling)['saved_image_path']).unlink()
        else:
            value['persistence'] = {**value['persistence'], 'status': 'uncertain'}
        study.original_touch(RESPONSE_ID, response_payload=value)
        study.transition('invalidate_' + change)
        study.run_child()
        assert_safe_stop(study, evidence_removed=change == 'evidence_loss')
        assert len(study.submissions) == 2, 'child spent a second handoff'
    except BaseException:
        study.failed = True
        raise
    finally:
        study.close()


@pytest.mark.parametrize('case', ['cancelled_dependency', 'missing_local', 'ordinary_execution'])
def test_original_admission_prerequisites(case):
    study = PendingHandoffStudy()
    try:
        payload = deepcopy(study.initial_payload)
        if case != 'ordinary_execution':
            for records in (payload['late_fill']['pending_branches'],
                            payload['runtime']['request_phase_graph']['phases'],
                            payload['runtime']['request_phase_graph']['downstream_branches']):
                for branch in records:
                    if branch.get('branch_id') == study.pending:
                        if case == 'cancelled_dependency':
                            branch['depends_on'] = [study.target]
                        else:
                            branch.pop('artifact_prompt', None)
                            branch.pop('artifact_prompt_source', None)
                            branch['depends_on'] = []
            payload = study.original_finalize(payload, request_payload=study.engine.request, persist=True)
            study.initial_payload = deepcopy(payload)
            study.original_touch(RESPONSE_ID, response_payload=payload)
            study.machine.sequence.handoff['artifact_gap']['pending_branches'] = deepcopy(payload['late_fill']['pending_branches'])
        study.start_parent()
        study.finish_race(True)
        if case == 'ordinary_execution':
            study.run_child()
            study.assert_outcome(study.observation(), continued=True)
            assert not study.observation()['payload']['late_fill'].get('successor_reopen_execution')
        else:
            assert len(study.submissions) == 1
            assert_safe_stop(study)
            study.retry(409)
            study.transition('pending_retry_409')
    except BaseException:
        study.failed = True
        raise
    finally:
        study.close()


def test_duplicate_delivery_and_already_completed_work_are_inert():
    study = PendingHandoffStudy()
    try:
        study.start_parent()
        study.finish_race(True)
        assert study.child_arrived.wait(WAIT_SECONDS)
        handoff = study.submissions[1]
        before_claims = len(study.claim_events)
        assert study.schedule(study.engine.late, **handoff) is False
        assert len(study.claim_events) == before_claims
        assert web._response_late_fill_is_in_flight(RESPONSE_ID)
        study.transition('duplicate_submission_denied')
        study.run_child()
        before = (len(study.claim_events), len(study.engine.harness.provider_calls), study.engine.ledger_bytes())
        study.engine.late.complete_response_late_fill(**handoff)
        assert before == (len(study.claim_events), len(study.engine.harness.provider_calls), study.engine.ledger_bytes())
        assert study.schedule(study.engine.late, **handoff) is False
        study.transition('duplicate_entry_after_completion_denied')
        study.assert_outcome(study.observation(), continued=True)
        study.stale_publication()
    except BaseException:
        study.failed = True
        raise
    finally:
        study.close()


def test_cancel_after_child_dispatch_does_not_accept_physical_result_or_rehandoff():
    study = PendingHandoffStudy(child_mode='cancel_after_dispatch')
    try:
        study.start_parent()
        study.finish_race(True)
        assert study.child_arrived.wait(WAIT_SECONDS)
        study.release_child.set()
        study.transition('release_child_entry')
        assert study.pending_reply.wait(WAIT_SECONDS)
        study.transition('P_provider_reply_held')
        study.cancel_pending()
        study.recover('cancelled_P_before_provider_return')
        study.transition('recover_cancelled_P')
        study.release_pending.set()
        assert study.child_done.wait(WAIT_SECONDS)
        study.transition('release_P_and_child_exit')
        assert_safe_stop(study, pending_cancelled=True, pending_calls=1)
        assert len(study.submissions) == 2
    except BaseException:
        study.failed = True
        raise
    finally:
        study.close()


@pytest.mark.parametrize('permanent', [False, True])
def test_child_availability_finite_clock_and_cancellation(permanent):
    study = PendingHandoffStudy()
    clock = {'now': late_module.time.time(), 'polls': 0}
    original_sleep = late_module.time.sleep
    try:
        value = deepcopy(study.initial_payload)
        for records in (value['late_fill']['pending_branches'], value['runtime']['request_phase_graph']['phases'],
                        value['runtime']['request_phase_graph']['downstream_branches']):
            for branch in records:
                if branch.get('branch_id') == study.pending:
                    branch['availability_wait']['next_check_epoch'] = clock['now'] + (3 if permanent else 2)
        value = study.original_finalize(value, request_payload=study.engine.request, persist=True)
        study.initial_payload = deepcopy(value)
        study.original_touch(RESPONSE_ID, response_payload=value)
        study.machine.sequence.handoff['artifact_gap']['pending_branches'] = deepcopy(value['late_fill']['pending_branches'])
        def sleep(seconds):
            if threading.current_thread().name != 'handoff-child':
                return original_sleep(seconds)
            clock['now'] += 1
            clock['polls'] += 1
            study.transition('finite_availability_poll')
            assert clock['polls'] <= 2
            if permanent and clock['polls'] == 2:
                study.cancel_pending()
        study.stack.enter_context(patch.object(late_module, 'time',
            SimpleNamespace(**{**vars(late_module.time), 'time': lambda: clock['now'], 'sleep': sleep})))
        study.start_parent()
        study.finish_race(True)
        study.run_child()
        assert clock['polls'] == 2
        if permanent:
            assert_safe_stop(study, pending_cancelled=True)
        else:
            study.assert_outcome(study.observation(), continued=True)
    except BaseException:
        study.failed = True
        raise
    finally:
        study.close()


def test_post_start_trace_error_never_releases_child_claim():
    study = PendingHandoffStudy()
    original = late_module.LateFillTrace.handoff
    @contextmanager
    def post_start(trace):
        with original(trace):
            yield
        if threading.current_thread().name == 'handoff-parent':
            raise RuntimeError('controlled trace error after successful child start')
    try:
        study.stack.enter_context(patch.object(late_module.LateFillTrace, 'handoff', post_start))
        study.start_parent()
        study.finish_race(True)
        assert study.child_arrived.wait(WAIT_SECONDS)
        assert web._response_late_fill_is_in_flight(RESPONSE_ID)
        assert [a for a, ok, _ in study.claim_events if ok] == ['claim', 'release', 'claim']
        study.transition('post_start_error_retains_child_claim')
        study.run_child()
        study.assert_outcome(study.observation(), continued=True)
    except BaseException:
        study.failed = True
        raise
    finally:
        study.close()


def test_stale_parent_callbacks_cannot_claim_pending_or_completed_child_work():
    study = PendingHandoffStudy()
    try:
        study.start_parent()
        study.finish_race(True)
        for settled in (False, True):
            if settled:
                study.run_child()
            before = stable(study.original_lookup(RESPONSE_ID)['response_payload'])
            ledger = study.engine.ledger_bytes()
            for branch in (study.target, study.pending):
                study.callbacks[1]({'branch_id': branch, 'phase_id': branch,
                                    'capability': 'image_generation', 'status': 'completed'})
            assert stable(study.original_lookup(RESPONSE_ID)['response_payload']) == before
            assert study.engine.ledger_bytes() == ledger
            study.transition('reject_stale_parent_callbacks')
        study.assert_outcome(study.observation(), continued=True)
    except BaseException:
        study.failed = True
        raise
    finally:
        study.close()
