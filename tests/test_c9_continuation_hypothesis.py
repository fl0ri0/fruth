"""Bounded continuation study; no new runtime continuation authority.

Extends the retained real-owner overlap harness. Initial graph admission is a
fixture premise, as in the earlier lineage families; provider transport alone
is synthetic. S completes before the contested T reply; P depends only on S.
"""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hypothesis import Phase, given, settings, strategies as st
import pytest

import fruth_webserver as web
from fruth_server.responses_runtime import ResponseMutationConflict
from fruth_services.response_frames import load_response_frame_records
from tests.test_graph_lineage_c3_c4_corrections import durable_evidence
from tests.test_graph_lineage_stateful_hypothesis import (
    PREPARATION, ROOT_PROMPT, PersistedGraphLineageMachine, graph_of, required_units, stable,
)
from tests.test_late_fill_c9_correction import current_scheduling
from tests.test_late_fill_control_overlap_hypothesis import OverlapStudy, Progress, RESPONSE_ID
from tests.http_client import api_client


PROMPTS = {'repair-image': 'Draw the accepted cobalt circle, duty S.',
           'unrelated-image': 'Draw the accepted amber star, duty T.',
           'pending-image': 'Draw the accepted green square, duty P.'}


class ContinuationProgress(Progress):
    race_ready = False

    def gate(self, actor, boundary):
        # Preparatory S is finite and serial; only the contested window pauses.
        if actor == 'setup' or (boundary != 'start' and not self.race_ready):
            self.record('preparation_seam', actor, boundary=boundary)
            return
        return super().gate(actor, boundary)


class ContinuationStudy(OverlapStudy):
    def __init__(self, reverse=False):
        self.progress = ContinuationProgress()
        self.threads, self.errors, self.commits, self.recoveries = [], [], [], []
        self.control_result = self.worker_result = None
        self.materialized = self.post_gate_seen = self.failed = False
        self.source_inputs = {'family': 'c9_continuation', 'reverse': reverse,
                              'admission': 'accepted_fixture_graph'}
        self.engine = engine = PersistedGraphLineageMachine()
        engine.accepted(True, 0)
        self.sibling, self.target = (('unrelated-image', 'repair-image') if reverse
                                     else ('repair-image', 'unrelated-image'))
        self.pending = 'pending-image'
        self.sibling_result = None
        self.pending_result = None
        self.window_started = False
        self.contracts = {}
        for branch in (self.sibling, self.target, self.pending):
            self.contracts[branch] = {
                'branch_id': branch, 'phase_id': branch, 'obligation_id': 'obligation-' + branch,
                'capability': 'image_generation', 'output_type': 'image', 'status': 'pending',
                'required': True, 'contract_state': 'promoted', 'artifact_prompt': PROMPTS[branch],
                'artifact_prompt_source': 'current_turn_direct_image_clause',
                'depends_on': ['phase-1'] if branch == self.sibling else [self.sibling],
            }
        self.contracts[self.pending]['availability_wait'] = {
            'status': 'waiting', 'next_check_epoch': 0, 'attempt_count': 0}
        graph = graph_of(engine.payload)
        graph['output_obligations'].append({
            'obligation_id': 'obligation-' + self.pending, 'branch_id': self.pending,
            'phase_id': self.pending, 'capability': 'image_generation', 'output_type': 'image',
            'required': True, 'contract_state': 'promoted', 'status': 'pending'})
        graph['downstream_branches'] = list(deepcopy(self.contracts).values())
        graph['downstream_branch_ids'] = list(self.contracts)
        graph['phases'] = [graph['phases'][0], *deepcopy(graph['downstream_branches'])]
        self.units = {'obligation-preparation': ('phase-1', 'phase-1', 'chat', 'text', True),
                      **{'obligation-' + b: (b, b, 'image_generation', 'image', True)
                         for b in self.contracts}}
        gap = {'expected_capability': 'image_generation', 'pending_capabilities': ['image_generation'],
               'pending_branches': list(deepcopy(self.contracts).values()),
               'authoritative_pending_branches': True}
        engine.payload['late_fill'] = web._build_late_fill_state(gap, status='pending')
        engine.payload = engine.finalize(engine.payload)
        engine.store = {'response_payload': deepcopy(engine.payload)}
        self.initial_payload = deepcopy(engine.payload)
        self.initial_frames = load_response_frame_records(RESPONSE_ID,
            frames_dir=engine.harness.response_frames_dir)['frames']
        self.initial_ledger = engine.ledger_bytes()
        self.relations = []
        sequence = SimpleNamespace(units=self.units, handoff={'artifact_gap': gap})
        self.machine = SimpleNamespace(sequence=sequence, failed=False,
                                       teardown=lambda: self.teardown_engine())
        web._ensure_response_lookup_for_payload(self.initial_payload, mode_hint='chat')
        web._touch_response_lookup(RESPONSE_ID, response_payload=self.initial_payload)
        engine.late = replace(engine.late,
            get_response_lookup_record=lambda rid: web._get_response_lookup_record(rid),
            touch_response_lookup=lambda *a, **kw: web._touch_response_lookup(*a, **kw),
            ensure_response_lookup_for_payload=web._ensure_response_lookup_for_payload,
            finalize_response_frame_payload=lambda *a, **kw: web._finalize_response_frame_payload(*a, **kw),
            claim_response_late_fill=web._claim_response_late_fill,
            release_response_late_fill=web._release_response_late_fill)
        self.original_lookup = web._get_response_lookup_record
        self.original_finalize = web._finalize_response_frame_payload
        self.original_touch = web._touch_response_lookup
        self.original_persist = web._persist_response_frame
        self.original_cas = web._append_response_frame_with_parent_cas
        provider = web.requests.post

        def finite_provider(*args, **kwargs):
            reply = provider(*args, **kwargs)
            request = stable(kwargs.get('json', {}))
            if PROMPTS[self.target] in request:
                self.progress.race_ready = True
            return reply

        self.original_provider = finite_provider
        self.original_materialize = engine.late.execute_materialization_branches
        self.original_gate = type(engine.late).semantic_execution_gate_decision
        self.original_merge = type(engine.late).merge_late_fill_result_fields
        self.stack = engine.stack
        self.install_seams()
        # Reuse the harness's explicit test scheduler for any real handoff. No
        # child may start outside the recorded finite schedule in this study.
        schedule = type(engine.late).schedule_response_late_fill
        def bounded_schedule(owner, **kwargs):
            if owner is self.engine.late:
                engine.harness.scheduled.append(deepcopy(kwargs))
                self.progress.record('schedule_handoff', value=deepcopy(kwargs))
                return True
            return schedule(owner, **kwargs)
        self.stack.enter_context(patch.object(type(engine.late), 'schedule_response_late_fill', bounded_schedule))

    def teardown_engine(self):
        self.engine.failed = self.failed
        self.engine.teardown()

    def begin_window(self):
        self.start()
        self.progress.step('worker')
        assert self.progress.waiting['worker'][0] == 'provider_reply', self.progress.events[-3:]
        live = self.original_lookup(RESPONSE_ID)['response_payload']
        self.sibling_result = durable_evidence(next(
            r for r in live['late_fill']['fill_results'] if r['branch_id'] == self.sibling))
        assert any(b['branch_id'] == self.target for b in live['late_fill']['active_branches'])
        assert any(b['branch_id'] == self.pending for b in live['late_fill']['pending_branches'])
        assert not any(r.get('branch_id') == self.pending for r in live['late_fill']['fill_results'])
        self.window_started = True
        self.progress.record('c9_window', value=deepcopy(live))
        self.progress.step('control')
        assert self.progress.waiting['control'][0] == 'after_lookup'

    def check_value(self, value, cancelled=False):
        assert required_units(graph_of(value)) == self.units, 'accepted duties changed'
        assert value['output_text'] == PREPARATION, 'accepted preparation changed'
        late = value['late_fill']
        results = late.get('fill_results', [])
        outputs = value['response_frame']['output']['outputs']
        if self.sibling_result is not None:
            own = [r for r in results if r.get('branch_id') == self.sibling]
            assert len(own) == 1 and durable_evidence(own[0]) == self.sibling_result, 'sibling evidence lost'
            assert Path(own[0]['saved_image_path']).read_bytes() == self.engine.model.png
            assert any(o.get('branch_id') == self.sibling and o.get('status') == 'fulfilled' for o in outputs), 'sibling public evidence lost'
        for result in results:
            branch = result.get('branch_id')
            assert branch in self.contracts, 'foreign accepted result'
            assert result.get('phase_id') == branch and result.get('obligation_id') == 'obligation-' + branch, 'accepted result identity changed'
        if cancelled:
            assert any(b.get('branch_id') == self.target and b.get('status') == 'cancelled'
                       for b in late.get('cancelled_branches', [])), 'committed cancellation silently undone'
            assert not any(r.get('branch_id') == self.target for r in results), 'cancelled result accepted'
            assert not any(b.get('branch_id') == self.target for key in ('pending_branches', 'active_branches')
                           for b in late.get(key, [])), 'cancelled branch revived'
            assert not any(o.get('branch_id') == self.target and o.get('status') == 'fulfilled' for o in outputs), 'cancelled output fulfilled'
        own = [r for r in results if r.get('branch_id') == self.pending]
        if not own:
            records = [b for key in ('pending_branches', 'active_branches', 'failed_branches')
                       for b in late.get(key, []) if b.get('branch_id') == self.pending]
            assert records, 'pending obligation lost from continuation state'
            for b in records:
                for key in ('branch_id', 'phase_id', 'obligation_id', 'artifact_prompt', 'depends_on'):
                    assert b.get(key) == self.contracts[self.pending][key], 'pending local contract changed: ' + key
            assert not any(o.get('branch_id') == self.pending and o.get('status') == 'fulfilled' for o in outputs), 'pending obligation falsely fulfilled'
        else:
            assert len(own) == 1, 'pending result duplicated'
            assert Path(own[0]['saved_image_path']).read_bytes() == self.engine.model.png
            assert any(PROMPTS[self.pending] in stable(call['request']) for call in self.engine.harness.provider_calls), 'pending fulfilled without own provider request'

    def passive(self, boundary):
        ledger, calls = self.engine.ledger_bytes(), len(self.engine.harness.provider_calls)
        scheduled = len(self.engine.harness.scheduled)
        value = self.recover(boundary)
        self.check_value(value, self.control_result['status_code'] == 200)
        assert self.engine.ledger_bytes() == ledger, 'passive recovery appended history'
        assert len(self.engine.harness.provider_calls) == calls, 'passive recovery dispatched'
        assert len(self.engine.harness.scheduled) == scheduled, 'passive recovery scheduled'
        assert not web._response_late_fill_is_in_flight(RESPONSE_ID)
        self.progress.record('transition', operation='passive_recovery')
        return value

    def retry(self, expected):
        before, calls = self.engine.ledger_bytes(), len(self.engine.harness.provider_calls)
        with api_client(web.app) as client:
            reply = client.post(f'/api/responses/{RESPONSE_ID}/late_fill/retry', json={'branch_id': self.pending})
        self.progress.record('transition', operation='explicit_retry', status=reply.status_code, body=reply.get_json())
        assert reply.status_code == expected, reply.get_json()
        assert len(self.engine.harness.provider_calls) == calls
        assert not web._response_late_fill_is_in_flight(RESPONSE_ID)
        if expected == 409:
            assert self.engine.ledger_bytes() == before, 'unsupported retry changed history'
        return self.original_lookup(RESPONSE_ID)['response_payload']

    def stale_publication(self):
        before, calls = self.engine.ledger_bytes(), len(self.engine.harness.provider_calls)
        with pytest.raises(ResponseMutationConflict):
            with self.engine.late._late_fill_publication(deepcopy(self.initial_payload),
                                                        expected_payload=self.initial_payload):
                pytest.fail('stale candidate reacquired publication authority')
        assert self.engine.ledger_bytes() == before and len(self.engine.harness.provider_calls) == calls
        self.progress.record('transition', operation='stale_publication_rejected')

    def check_dispatch(self):
        plans = [p for e in self.progress.events if e['kind'] == 'materialized'
                 for p in e['value'].get('prepared_branch_plans', [])]
        for plan in plans:
            branch = plan['branch_id']
            assert branch in self.contracts, 'unadmitted dispatch'
            assert plan['effective_data']['prompt'] == PROMPTS[branch], 'local dispatch instruction changed'
            binding = plan['execution_contract']
            assert binding['branch_id'] == binding['phase_id'] == branch
            assert binding['output_obligation_ref']['obligation_id'] == 'obligation-' + branch
            assert binding['depends_on'] == self.contracts[branch]['depends_on'], 'dispatch dependencies changed'
            if branch != self.sibling:
                # Verify actual accepted evidence carried into preparation, not
                # only dependency names in the admitted fixture.
                value = plan['branch']['prepare_args']['current_payload']
                result = next(r for r in value['late_fill']['fill_results']
                              if r.get('branch_id') == self.sibling)
                assert durable_evidence(result) == self.sibling_result, 'dispatch dependency evidence changed'
        for call in self.engine.harness.provider_calls:
            assert ROOT_PROMPT not in stable(call['request']), 'root prompt replay'


def exercise(choices, reverse=False, sensitivity=False):
    with current_scheduling():
        study = ContinuationStudy(reverse)
        try:
            study.source_inputs['choices'] = list(choices)
            study.begin_window()
            for choice in choices:
                if len(study.progress.done) == 2:
                    break
                actor = 'control' if choice else 'worker'
                if actor in study.progress.done:
                    actor = 'worker' if choice else 'control'
                study.progress.step(actor)
            assert len(study.progress.done) == 2, 'bounded schedule did not finish'
            final = study.check()
            assert study.control_result['status_code'] in {200, 409}
            cancelled = study.control_result['status_code'] == 200
            # Explicit finite assumptions: all worker/provider releases supplied;
            # synthetic compatible capacity remains available.
            if cancelled:
                assert not any(r.get('branch_id') == study.pending for r in final['late_fill']['fill_results'])
                study.retry(409)
                classification = 'intentionally_unresolved_pending; unsupported_pending_retry'
            else:
                assert any(r.get('branch_id') == study.pending for r in final['late_fill']['fill_results']), 'finite existing worker did not complete P'
                classification = 'existing_worker_continuation_completed'
            study.stale_publication()
            final = study.passive('settled_passive_recovery')
            study.check_dispatch()
            if sensitivity:
                faults = ('sibling', 'binding', 'pending', 'dependency', 'cancellation', 'false_fulfillment') if cancelled else ('sibling', 'binding')
                for fault in faults:
                    bad = deepcopy(final)
                    if fault == 'sibling':
                        bad['late_fill']['fill_results'] = []
                    elif fault == 'binding':
                        bad['late_fill']['fill_results'][0]['obligation_id'] = 'foreign'
                    elif fault == 'pending':
                        for key in ('pending_branches', 'active_branches', 'failed_branches'):
                            bad['late_fill'][key] = []
                    elif fault == 'dependency':
                        bad['late_fill']['pending_branches'][0]['depends_on'] = [study.target]
                    elif fault == 'cancellation':
                        bad['late_fill']['cancelled_branches'] = []
                    else:
                        bad['response_frame']['output']['outputs'].append({'branch_id': study.pending, 'status': 'fulfilled'})
                    with pytest.raises(AssertionError):
                        study.check_value(bad, cancelled)
                    study.progress.record('sensitivity_detected', fault=fault)
            transitions = len(study.progress.decisions) + sum(e['kind'] == 'transition' for e in study.progress.events)
            assert transitions <= 32, 'actual transition budget exceeded'
            study.source_inputs.update(classification=classification, actual_transitions=transitions)
            assert not web._RESPONSES_RUNTIME._mutation_locks
        except BaseException:
            study.failed = True
            raise
        finally:
            study.source_inputs['actual_transitions'] = len(study.progress.decisions) + sum(
                e['kind'] == 'transition' for e in study.progress.events)
            study.source_inputs['reached_schedule_releases'] = len(study.progress.decisions)
            study.close()


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('control_wins', [False, True])
def test_positive_orders(reverse, control_wins):
    exercise([control_wins] * 24, reverse)


def test_independent_oracle_sensitivity():
    exercise([True] * 24, sensitivity=True)


@settings(max_examples=32, phases=(Phase.generate,), deadline=None,
          print_blob=True, report_multiple_bugs=False)
@given(choices=st.lists(st.booleans(), min_size=24, max_size=24), reverse=st.booleans())
def test_bounded_continuation(choices, reverse):
    exercise(choices, reverse)
