"""Bounded real-owner worker/control interleavings, with no production edits.

Each actor retains its stack while the other advances at explicit unlocked seams.
The scheduler controls progress, not lock acquisition, authority or owner outputs.
"""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import uuid
from unittest.mock import patch

from hypothesis import Phase, given, settings, strategies as st
import pytest

import fruth_webserver as web
from fruth_services.response_frames import (
    load_latest_response_state, load_response_frame_records,
)
from tests.test_graph_lineage_c3_c4_corrections import durable_evidence
from tests.test_graph_lineage_stateful_hypothesis import PREPARATION, graph_of, required_units, stable
from tests.test_late_cancel_lineage_hypothesis import LateCancelMachine
from tests.http_client import api_client


WAIT_SECONDS = 20
MAX_DECISIONS = 32
RESPONSE_ID = 'stateful-lineage'


class FixtureTimeout(AssertionError):
    """A failed test rendezvous is not evidence of a runtime deadlock."""


class Progress:
    def __init__(self):
        self.condition = threading.Condition()
        self.waiting = {}
        self.done = set()
        self.aborting = False
        self.events = []
        self.decisions = []

    def record(self, kind, actor=None, **data):
        with self.condition:
            item = {'ordinal': len(self.events), 'kind': kind, 'actor': actor,
                    'thread': threading.current_thread().name,
                    'thread_id': threading.get_ident(), 'monotonic_ns': time.monotonic_ns(), **data}
            self.events.append(item)
            return item

    def gate(self, actor, boundary):
        with self.condition:
            if self.aborting:
                return
            assert actor not in self.waiting, 'fixture created two simultaneous actor gates'
            event = threading.Event()
            self.waiting[actor] = (boundary, event)
            self.record('gate_arrive', actor, boundary=boundary)
            self.condition.notify_all()
        if not event.wait(WAIT_SECONDS):
            raise FixtureTimeout(f'{actor} gate {boundary} timed out')
        self.record('gate_resume', actor, boundary=boundary)

    def finish(self, actor):
        with self.condition:
            self.done.add(actor)
            self.record('actor_finished', actor)
            self.condition.notify_all()

    def rendezvous(self, actor):
        with self.condition:
            if not self.condition.wait_for(
                    lambda: actor in self.waiting or actor in self.done, WAIT_SECONDS):
                raise FixtureTimeout(f'{actor} did not reach the next unlocked seam')

    def step(self, actor):
        self.rendezvous(actor)
        with self.condition:
            if actor in self.done:
                return False
            boundary, event = self.waiting.pop(actor)
            assert len(self.decisions) < MAX_DECISIONS, 'fixture exceeded schedule budget'
            self.decisions.append({'actor': actor, 'boundary': boundary})
            self.record('schedule_release', actor, boundary=boundary)
            event.set()
        self.rendezvous(actor)
        return True

    def release_all(self):
        with self.condition:
            self.aborting = True
            for _, event in self.waiting.values():
                event.set()
            self.waiting.clear()
            self.condition.notify_all()


class OverlapStudy:
    def __init__(self, reverse=False):
        self.progress = Progress()
        self.machine = LateCancelMachine()
        self.threads = []
        self.errors = []
        self.commits = []
        self.recoveries = []
        self.control_result = None
        self.worker_result = None
        self.materialized = False
        self.post_gate_seen = False
        self.source_inputs = {'reverse': reverse}
        self.failed = False
        self.machine.accepted(reverse, 'base64', 'no_cancel')
        for _ in range(4):
            self.machine.advance()
        self.engine = self.machine.engine
        self.target, self.sibling = self.machine.target, self.machine.sibling
        self.sibling_result = deepcopy(self.machine.sibling_result)
        self.initial_frames = load_response_frame_records(RESPONSE_ID,
            frames_dir=self.engine.harness.response_frames_dir)['frames']
        self.initial_ledger = self.engine.ledger_bytes()
        self.relations = deepcopy(self.machine.parent_relations)
        self.initial_payload = deepcopy(self.engine.payload)
        # The old dictionary is setup-only. Contested state is the actual registry,
        # including its original locks, durable arbitration and recovery owner.
        web._ensure_response_lookup_for_payload(self.initial_payload, mode_hint='chat')
        web._touch_response_lookup(RESPONSE_ID, response_payload=self.initial_payload)
        self.engine.late = replace(self.engine.late,
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
        self.original_provider = web.requests.post
        self.original_materialize = self.engine.late.execute_materialization_branches
        self.original_gate = type(self.engine.late).semantic_execution_gate_decision
        self.original_merge = type(self.engine.late).merge_late_fill_result_fields
        self.stack = self.engine.stack
        self.install_seams()

    @staticmethod
    def actor():
        name = threading.current_thread().name
        return name.removeprefix('overlap-') if name.startswith('overlap-') else 'setup'

    def install_seams(self):
        progress = self.progress

        def lookup(*args, **kwargs):
            value = self.original_lookup(*args, **kwargs)
            actor = self.actor()
            progress.record('lookup_read', actor, value=deepcopy(value))
            if actor == 'control':
                progress.gate(actor, 'after_lookup')
            return value

        def provider(*args, **kwargs):
            result = self.original_provider(*args, **kwargs)
            progress.record('adapter_reply', 'worker', call=deepcopy(self.engine.harness.provider_calls[-1]))
            progress.gate('worker', 'provider_reply')
            return result

        def materialize(*args, **kwargs):
            result = self.original_materialize(*args, **kwargs)
            self.materialized = True
            progress.record('materialized', 'worker', value=deepcopy(result))
            progress.gate('worker', 'materialized_before_acceptance_read')
            return result

        def gate(owner, branch, current_payload=None):
            post = owner is self.engine.late and self.materialized and not self.post_gate_seen
            if post:
                self.post_gate_seen = True
                progress.record('post_acceptance_read', 'worker', value=deepcopy(current_payload))
                progress.gate('worker', 'post_read_before_gate')
            result = self.original_gate(owner, branch, current_payload)
            if owner is self.engine.late:
                progress.record('eligibility_decision', 'worker', post_materialization=post,
                                value=deepcopy(result))
            if post:
                progress.gate('worker', 'post_gate_before_acceptance')
            return result

        def merge(owner, *args, **kwargs):
            result = self.original_merge(owner, *args, **kwargs)
            if owner is self.engine.late:
                progress.record('result_merge', 'worker', value=deepcopy(result))
            return result

        def persist(*args, **kwargs):
            result = self.original_persist(*args, **kwargs)
            self.capture_commit('regular_append', kwargs.get('receipt'))
            return result

        def cas(*args, **kwargs):
            try:
                result = self.original_cas(*args, **kwargs)
            except Exception as exc:
                progress.record('conflict', self.actor(), error=repr(exc))
                raise
            self.capture_commit('parent_cas', kwargs.get('receipt'))
            return result

        def finalize(value, **kwargs):
            actor = self.actor()
            progress.record('finalization_candidate', actor, value=deepcopy(value), arguments=deepcopy(kwargs))
            progress.gate(actor, 'before_finalize')
            result = self.original_finalize(value, **kwargs)
            progress.record('finalization_return', actor, value=deepcopy(result))
            progress.gate(actor, 'committed_before_publication')
            return result

        def touch(*args, **kwargs):
            result = self.original_touch(*args, **kwargs)
            progress.record('lookup_publication', self.actor(), value=deepcopy(result))
            return result

        for obj, name, callback in (
            (web, '_get_response_lookup_record', lookup),
            (web.requests, 'post', provider),
            (web, '_persist_response_frame', persist),
            (web, '_append_response_frame_with_parent_cas', cas),
            (web, '_finalize_response_frame_payload', finalize),
            (web, '_touch_response_lookup', touch),
            (type(self.engine.late), 'semantic_execution_gate_decision', gate),
            (type(self.engine.late), 'merge_late_fill_result_fields', merge),
        ):
            self.stack.enter_context(patch.object(obj, name, callback))
        self.engine.late = replace(self.engine.late, execute_materialization_branches=materialize)

    def capture_commit(self, mechanism, receipt):
        # Called after the real writer returns and releases its production locks.
        frames = load_response_frame_records(RESPONSE_ID,
            frames_dir=self.engine.harness.response_frames_dir)['frames']
        known = {f['frame_id'] for f in self.initial_frames}
        known.update(c['frame']['frame_id'] for c in self.commits)
        for frame in frames:
            if frame['frame_id'] not in known:
                # Raw ledger rows may inherit a snapshot-manifest delta. Use the
                # canonical reader while this is the latest committed frame;
                # reconstructing a lone raw row can expose only compact results.
                state = load_latest_response_state(RESPONSE_ID,
                    frames_dir=self.engine.harness.response_frames_dir)
                assert state['ok'] and state['response_frame']['frame_id'] == frame['frame_id']
                event = self.progress.record('durable_commit', self.actor(), mechanism=mechanism,
                                             frame_id=frame['frame_id'], receipt=deepcopy(receipt))
                self.commits.append({'ordinal': event['ordinal'], 'actor': self.actor(),
                                     'frame': deepcopy(frame), 'receipt': deepcopy(receipt),
                                     'payload': deepcopy(state['response_payload'])})

    def recover(self, boundary):
        state = load_latest_response_state(RESPONSE_ID, frames_dir=self.engine.harness.response_frames_dir)
        self.recoveries.append({'boundary': boundary, 'state': deepcopy(state)})
        self.progress.record('recovery_read', self.actor(), boundary=boundary, ok=state.get('ok'))
        assert state['ok'], state
        return state['response_payload']

    def worker(self):
        assert web._claim_response_late_fill(RESPONSE_ID), 'fixture duplicated worker ownership'
        self.progress.record('worker_claim', 'worker', claimed=True)
        try:
            result = self.engine.late.complete_response_late_fill(
                response_payload=deepcopy(self.initial_payload), request_payload=deepcopy(self.engine.request),
                assistant_message=PREPARATION, artifact_gap=deepcopy(self.machine.sequence.handoff['artifact_gap']),
                source_route_payload=None)
            self.worker_result = {'return': result, 'lookup': deepcopy(self.original_lookup(RESPONSE_ID))}
            self.progress.record('worker_result', 'worker', value=deepcopy(self.worker_result))
        finally:
            # The worker's real finally owns release, including failure paths.
            assert not web._response_late_fill_is_in_flight(RESPONSE_ID), 'worker claim leaked'

    def control(self):
        # A new Flask client/request context belongs only to this actor.
        with api_client(web.app) as client:
            reply = client.post(f'/api/responses/{RESPONSE_ID}/late_fill/control', json={
                'branch_id': self.target, 'action': 'cancel', 'reason': 'Stop only the independently admitted target.'})
            self.control_result = {'status_code': reply.status_code, 'body': reply.get_json()}
            self.progress.record('control_acknowledgement', 'control', value=deepcopy(self.control_result))
            self.recover('immediate_control_result')

    def start(self, control=True):
        for actor, operation in [('worker', self.worker)] + ([('control', self.control)] if control else []):
            def execute(actor=actor, operation=operation):
                try:
                    with web.app.app_context():
                        self.progress.gate(actor, 'start')
                        self.progress.record('actor_operation_begin', actor)
                        operation()
                except BaseException as exc:
                    self.errors.append((actor, exc))
                    self.progress.record('actor_exception', actor, error=repr(exc))
                finally:
                    self.progress.finish(actor)
            thread = threading.Thread(target=execute, name='overlap-' + actor, daemon=True)
            self.threads.append(thread)
            thread.start()
            self.progress.rendezvous(actor)

    def drain(self, actor):
        while self.progress.step(actor):
            pass

    def schedule(self, choices):
        self.source_inputs['choices'] = list(choices)
        self.start()
        for choice in choices:
            if len(self.progress.done) == 2:
                break
            actor = 'control' if choice else 'worker'
            if actor in self.progress.done:
                actor = 'worker' if choice else 'control'
            self.progress.step(actor)
        assert len(self.progress.done) == 2, 'schedule budget exhausted: incomplete fixture'

    def check_value(self, value, cancelled=False):
        assert required_units(graph_of(value)) == self.machine.sequence.units, 'accepted duties changed'
        assert value['output_text'] == PREPARATION, 'accepted preparation changed'
        late = value['late_fill']
        sibling = [r for r in late.get('fill_results', []) if r.get('branch_id') == self.sibling]
        assert len(sibling) == 1 and durable_evidence(sibling[0]) == self.sibling_result, 'sibling evidence lost'
        for result in late.get('fill_results', []):
            branch = result.get('branch_id')
            assert branch in {self.target, self.sibling}, 'foreign accepted result'
            assert result.get('phase_id') == branch and result.get('obligation_id') == 'obligation-' + branch, \
                'accepted result identity changed'
        outputs = value['response_frame']['output']['outputs']
        assert any(o.get('branch_id') == self.sibling and o.get('status') == 'fulfilled' for o in outputs), \
            'sibling public evidence lost'
        if cancelled:
            stopped = [b for b in late.get('cancelled_branches', []) if b.get('branch_id') == self.target]
            assert len(stopped) == 1 and stopped[0]['status'] == 'cancelled', 'committed cancellation silently undone'
            assert not any(r.get('branch_id') == self.target for r in late.get('fill_results', [])), \
                'result accepted after committed cancellation'
            assert not any(o.get('branch_id') == self.target and o.get('status') == 'fulfilled' for o in outputs), \
                'physical output published after committed cancellation'

    def check(self):
        if self.errors:
            raise self.errors[0][1]
        final = self.recover('after_both_actors')
        assert self.worker_result is not None
        cancelled = False
        for commit in self.commits:
            assert commit['receipt']['status'] == 'committed', 'append without committed receipt'
            value = commit['payload']
            if commit['actor'] == 'control':
                cancelled = any(b.get('branch_id') == self.target and b.get('status') == 'cancelled'
                                for b in value['late_fill'].get('cancelled_branches', [])) or cancelled
            self.check_value(value, cancelled)
        self.check_value(final, cancelled)
        if self.control_result:
            assert self.control_result['status_code'] in {200, 404, 409, 503}, self.control_result
            if self.control_result['status_code'] == 200:
                assert cancelled, 'successful control without durable disposition'
            if self.control_result['status_code'] == 404:
                assert any(r.get('branch_id') == self.target for r in final['late_fill']['fill_results']), \
                    'late rejected control lost accepted target'
        history = load_response_frame_records(RESPONSE_ID,
            frames_dir=self.engine.harness.response_frames_dir)['frames']
        assert [stable(f) for f in history[:len(self.initial_frames)]] == [stable(f) for f in self.initial_frames], \
            'frozen parent values changed'
        assert self.engine.ledger_bytes().startswith(self.initial_ledger), 'committed ledger prefix changed'
        assert len({f['frame_id'] for f in history}) == len(history)
        assert [f['frame_sequence'] for f in history] == list(range(1, len(history) + 1))
        for relation in self.relations:
            assert any(f.get('frame_relation') == relation for f in history), 'committed successor relation lost'
            assert any(f['frame_id'] == relation['parent_frame_id'] and
                       f['frame_sequence'] == relation['parent_frame_sequence'] for f in history)
        assert not web._response_late_fill_is_in_flight(RESPONSE_ID)
        assert not self.engine.harness.scheduled, 'fixture created unexamined child work'
        return final

    def close(self):
        self.progress.release_all()
        for thread in self.threads:
            thread.join(WAIT_SECONDS)
        leaked = [t.name for t in self.threads if t.is_alive()]
        try:
            assert not leaked, f'fixture actor join timed out: {leaked}'
            self.engine.frames = load_response_frame_records(RESPONSE_ID,
                frames_dir=self.engine.harness.response_frames_dir)['frames']
            self.engine.payload = deepcopy((self.original_lookup(RESPONSE_ID) or {}).get('response_payload') or self.initial_payload)
            record = {'kind': 'fruth.control_worker_overlap', 'context': self.engine.context,
                'inputs': self.source_inputs, 'failed': self.failed,
                'decisions': self.progress.decisions, 'events': self.progress.events,
                'commits': self.commits, 'recoveries': self.recoveries,
                'control_result': self.control_result, 'worker_result': self.worker_result,
                'fixture_errors': [{'actor': a, 'error': repr(e)} for a, e in self.errors],
                'adapter_calls': deepcopy(self.engine.harness.provider_calls),
                'initial_frames': self.initial_frames, 'sibling_result': self.sibling_result,
                'physical_files': {str(p.relative_to(self.engine.harness.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in self.engine.harness.images_dir.rglob('*') if p.is_file()}}
            destination = os.environ.get('FRUTH_HYPOTHESIS_EVIDENCE_DIR')
            if destination:
                path = Path(destination) / ('overlap-' + uuid.uuid4().hex + '.json')
                path.write_text(json.dumps(record, indent=2, default=str) + '\n')
            self.engine.inputs.update(overlap=self.source_inputs, scheduling_decisions=len(self.progress.decisions))
            self.engine.observations = self.progress.events
        finally:
            self.machine.failed = self.failed
            self.machine.teardown()


def run_schedule(choices, reverse=False):
    study = OverlapStudy(reverse)
    try:
        study.schedule(choices)
        return study.check()
    except BaseException:
        study.failed = True
        raise
    finally:
        study.close()


@settings(max_examples=min(32, int(os.environ.get('FRUTH_HYPOTHESIS_ADAPTER', '32'))),
          phases=(Phase.generate,), deadline=None, print_blob=True, report_multiple_bugs=False)
@given(choices=st.lists(st.booleans(), min_size=MAX_DECISIONS, max_size=MAX_DECISIONS),
       reverse=st.booleans())
def test_bounded_control_worker_schedules(choices, reverse):
    run_schedule(choices, reverse)


@pytest.mark.parametrize('order', ['worker_first', 'control_first', 'no_control', 'overlap_before_read'])
def test_serial_and_overlap_controls(order):
    study = OverlapStudy()
    try:
        study.source_inputs['control'] = order
        study.start(control=order != 'no_control')
        if order == 'control_first':
            study.drain('control')
            study.drain('worker')
        elif order == 'overlap_before_read':
            study.progress.step('worker')  # provider reply, worker operation is in flight
            assert study.progress.waiting['worker'][0] == 'provider_reply'
            study.drain('control')
            study.drain('worker')
        else:
            study.drain('worker')
            if order != 'no_control':
                study.drain('control')
        final = study.check()
        if order in {'worker_first', 'no_control'}:
            assert len(final['late_fill']['fill_results']) == 2
        if order == 'worker_first':
            assert study.control_result['status_code'] == 404
        if order in {'control_first', 'overlap_before_read'}:
            assert study.control_result['status_code'] == 200
        if order == 'overlap_before_read':
            events = study.progress.events
            worker_begin = next(e['ordinal'] for e in events if e['kind'] == 'actor_operation_begin' and e['actor'] == 'worker')
            control_ack = next(e['ordinal'] for e in events if e['kind'] == 'control_acknowledgement')
            worker_end = next(e['ordinal'] for e in events if e['kind'] == 'actor_finished' and e['actor'] == 'worker')
            assert worker_begin < control_ack < worker_end
            assert len(study.engine.harness.provider_calls) == 2
    except BaseException:
        study.failed = True
        raise
    finally:
        study.close()


def test_oracle_detects_observed_sibling_loss():
    study = OverlapStudy()
    try:
        study.source_inputs['control'] = 'observed_state_fault'
        study.start(control=False)
        study.drain('worker')
        value = deepcopy(study.check())
        value['late_fill']['fill_results'] = [r for r in value['late_fill']['fill_results']
                                            if r['branch_id'] != study.sibling]
        with pytest.raises(AssertionError, match='sibling evidence lost'):
            study.check_value(value)
        study.progress.record('test_only_fault_detected', fault='drop_sibling_result')
    except BaseException:
        study.failed = True
        raise
    finally:
        study.close()
