"""Acceptance-time cancellation composed with real successor execution/recovery.

The model's timing choice precedes execution. No production validator determines
the expected verdict. These are deterministic callback orderings, not races.
"""
from copy import deepcopy
import os
from unittest.mock import patch

import pytest
from hypothesis import Phase, reproduce_failure, settings, strategies as st
from hypothesis.stateful import RuleBasedStateMachine, get_state_machine_test, initialize, invariant, rule

import fruth_webserver as web
from fruth_services.response_frames import load_latest_response_state, load_response_frame_records
from tests.test_graph_lineage_c3_c4_corrections import durable_evidence
from tests.test_graph_lineage_stateful_hypothesis import PREPARATION, ROOT_PROMPT, graph_of, required_units, stable
from tests.test_graph_lineage_two_successors_hypothesis import TwoSuccessorMachine


TIMINGS = ('before_dispatch', 'during_provider', 'after_acceptance', 'no_cancel')


class LateCancelMachine(RuleBasedStateMachine):
    control = False

    def __init__(self):
        super().__init__()
        self.sequence = None
        self.failed = False
        self.steps = 0

    @initialize(reverse=st.booleans(), representation=st.sampled_from(('base64', 'data_uri')),
                timing=st.sampled_from(TIMINGS))
    def accepted(self, reverse, representation, timing):
        self.sequence = TwoSuccessorMachine()
        self.sequence.control = self.control
        self.sequence.accepted(reverse, 0)
        self.engine = self.sequence.engine
        self.timing, self.representation = timing, representation
        self.stage = 'sibling_admit'
        self.target = self.sequence.order[1]
        self.sibling = self.sequence.order[0]
        self.cancelled = timing in {'before_dispatch', 'during_provider'}
        self.settled = False
        self.control_applied = False
        self.sibling_result = None
        self.target_result = None
        self.control_requests = []
        self.boundary_errors = []
        self.parent_relations = []
        self.engine.inputs.update(family='late_cancel', timing=timing,
                                  representation=representation, target=self.target)
        self.engine.counts['model_transition_attempts'] += 1
        self.note('accepted')

    def note(self, operation, **fields):
        self.steps += 1
        self.engine.record('cancel_' + operation, **fields)
        self.engine.counts['model_transitions'] = self.steps

    def control_branch(self):
        """Real Flask control endpoint; only the fixture lookup store is injected."""
        engine = self.engine
        before = deepcopy(engine.store['response_payload'])
        active = before['late_fill'].get('active_branches', [])
        if self.timing == 'during_provider':
            assert any(b['branch_id'] == self.target for b in active), 'control was not in flight'
        with patch.object(web, '_get_response_lookup_record', engine.late.get_response_lookup_record), \
             patch.object(web, '_touch_response_lookup', engine.late.touch_response_lookup):
            response = engine.harness.client.post('/api/responses/stateful-lineage/late_fill/control',
                json={'branch_id': self.target, 'action': 'cancel',
                      'reason': 'Stop this exact branch; retain independently accepted sibling work.'})
        observation = {'timing': self.timing, 'status_code': response.status_code,
                       'body': response.get_json(), 'before': before,
                       'after': deepcopy(engine.store['response_payload'])}
        engine.observations.append({'boundary': 'control_endpoint', **observation})
        self.control_requests.append(response.status_code)
        engine.counts['control_endpoint_calls'] += 1
        assert response.status_code == (404 if self.timing == 'after_acceptance' else 200), observation
        if response.status_code == 200:
            self.control_applied = True
            engine.counts['control_frame_finalizations'] += 1
            # Observe the persisted control boundary before the provider returns.
            # Keep executing the original delayed-result path, then report every
            # boundary failure; a later worker must not mask an invalid frame.
            recovered = load_latest_response_state('stateful-lineage',
                frames_dir=engine.harness.response_frames_dir)
            engine.counts['durable_recovery_reads'] += 1
            assert recovered['ok'], recovered
            engine.observations.append({'boundary': 'control_durable_recovery',
                                        'payload': deepcopy(recovered['response_payload'])})
            self.check_history()
            for label, value in (('control_projection', observation['after']),
                                 ('control_recovery', recovered['response_payload'])):
                try:
                    self.check(value)
                except AssertionError as exc:
                    self.boundary_errors.append({'boundary': label, 'error': str(exc)})
        else:
            assert durable_evidence(engine.store['response_payload']['late_fill']) == \
                durable_evidence(before['late_fill']), 'late control rewrote accepted evidence'

    def dispatch_target(self):
        engine, sequence = self.engine, self.sequence
        before = len(engine.harness.provider_calls)
        if self.timing == 'before_dispatch':
            self.control_branch()
            sequence.publish(engine.store['response_payload'])
        provider = web.requests.post
        callback_errors = []

        def delayed_provider(url, **kwargs):
            reply = provider(url, **kwargs)
            assert url.endswith(('/v1/images/generations', '/api/generate'))
            # Exercise supported transport representation, not a provider label.
            content = reply.content
            if self.representation == 'data_uri':
                if 'data' in content:
                    content['data'][0]['b64_json'] = 'data:image/png;base64,' + content['data'][0]['b64_json']
                else:
                    content['images'][0] = 'data:image/png;base64,' + content['images'][0]
            if self.timing == 'during_provider':
                try:
                    assert len(engine.harness.provider_calls) == before + 1, 'provider not entered'
                    self.control_branch()
                except BaseException as exc:
                    # A transport catches provider exceptions and may fall back.
                    # Surface fixture errors outside it without manufacturing a
                    # transport failure or silently turning a control into no-op.
                    callback_errors.append(exc)
            return reply

        with patch.object(web.requests, 'post', delayed_provider):
            engine.late.complete_response_late_fill(response_payload=deepcopy(engine.payload),
                request_payload=engine.request, assistant_message=PREPARATION,
                artifact_gap=deepcopy(sequence.handoff['artifact_gap']), source_route_payload=None)
        sequence.publish(engine.store['response_payload'])
        engine.counts['worker_calls'] += 1
        if callback_errors:
            raise callback_errors[0]
        expected_calls = 0 if self.timing == 'before_dispatch' else 1
        assert len(engine.harness.provider_calls) == before + expected_calls, 'unexpected target dispatch'
        if expected_calls:
            call = engine.harness.provider_calls[-1]
            assert sequence.prompts[self.target] in stable(call['request'])
            assert ROOT_PROMPT not in stable(call['request'])
        self.settled = True
        if not self.cancelled:
            sequence.expected.add(self.target)
            self.target_result = durable_evidence(next(r for r in engine.payload['late_fill']['fill_results']
                                                     if r.get('branch_id') == self.target))
        if self.timing == 'after_acceptance':
            self.control_branch()
        files = [p for p in engine.harness.images_dir.rglob('*') if p.is_file()]
        assert len(files) == 1 + expected_calls, 'physical result count differs from actual dispatch'
        assert all(p.read_bytes() == engine.model.png for p in files)
        engine.counts['provider_induced_image_writes'] = len(files)
        engine.inputs['control_boundary_errors'] = self.boundary_errors
        engine.observations.append({'boundary': 'post_worker', 'payload': deepcopy(engine.payload)})
        # Record the final durable view even when the earlier projection failed.
        recovered = load_latest_response_state('stateful-lineage',
            frames_dir=engine.harness.response_frames_dir)
        engine.counts['durable_recovery_reads'] += 1
        assert recovered['ok'], recovered
        engine.observations.append({'boundary': 'post_worker_recovery',
                                    'payload': deepcopy(recovered['response_payload'])})
        self.check_history()
        self.check(engine.payload)
        self.check(recovered['response_payload'])
        assert not self.boundary_errors, ('control boundary lost accepted evidence', self.boundary_errors)

    @rule()
    def advance(self):
        self.engine.counts['model_transition_attempts'] += 1
        try:
            sequence, engine = self.sequence, self.engine
            operation = self.stage
            if self.stage == 'sibling_admit':
                sequence.admit()
                self.parent_relations.append(deepcopy(engine.payload['response_frame']['frame_relation']))
                self.stage = 'sibling_execute'
            elif self.stage == 'sibling_execute':
                sequence.execute()
                self.sibling_result = durable_evidence(next(r for r in engine.payload['late_fill']['fill_results']
                                                          if r.get('branch_id') == self.sibling))
                self.stage = 'target_parent'
            elif self.stage == 'target_parent':
                sequence.next_parent()
                self.stage = 'target_admit'
            elif self.stage == 'target_admit':
                sequence.admit()
                self.parent_relations.append(deepcopy(engine.payload['response_frame']['frame_relation']))
                self.stage = 'target_dispatch'
            elif self.stage == 'target_dispatch':
                self.dispatch_target()
                self.stage = 'recover'
            else:
                self.recover()
            self.note(operation)
        except BaseException:
            self.failed = True
            raise

    @rule(observation=st.sampled_from(('reload', 'repeat_worker', 'late_callback')))
    def observe_settled(self, observation):
        # Advance until a complete interaction; every generated trace remains
        # reachable and short traces are counted honestly in the report.
        if not self.settled:
            self.advance()
            return
        try:
            engine = self.engine
            engine.counts['model_transition_attempts'] += 1
            if observation == 'reload':
                self.recover()
            elif observation == 'repeat_worker':
                before = len(engine.harness.provider_calls)
                engine.late.complete_response_late_fill(response_payload=deepcopy(engine.payload),
                    request_payload=engine.request, assistant_message=PREPARATION,
                    artifact_gap=deepcopy(self.sequence.handoff['artifact_gap']), source_route_payload=None)
                self.sequence.publish(engine.store['response_payload'])
                engine.counts['worker_calls'] += 1
                assert len(engine.harness.provider_calls) == before, 'terminal work dispatched again'
                self.check(engine.payload)
            else:
                before = deepcopy(engine.payload['late_fill'])
                execution = deepcopy(before['successor_reopen_execution'])
                execution['status'] = 'running'
                value = engine.late.attach_late_fill_state(deepcopy(engine.payload), {
                    'status': 'running', 'fill_results': [],
                    'pending_branches': [self.sequence.branch_contract()],
                    'successor_reopen_execution': execution})
                engine.counts['direct_callback_owner_calls'] += 1
                assert durable_evidence(value['late_fill']) == durable_evidence(before), 'late callback revived terminal work'
                self.check(value)
                self.sequence.publish(value)
            self.note(observation)
        except BaseException:
            self.failed = True
            raise

    def check(self, value):
        assert required_units(graph_of(value)) == self.sequence.units, 'accepted duties changed'
        assert value['output_text'] == PREPARATION, 'accepted preparation changed'
        late = value['late_fill']
        results = late.get('fill_results', [])
        if self.sibling_result is not None:
            own = [r for r in results if r.get('branch_id') == self.sibling]
            assert len(own) == 1 and durable_evidence(own[0]) == self.sibling_result, 'sibling evidence lost'
        self.sequence.check_payload(value)
        if self.settled:
            own = [r for r in results if r.get('branch_id') == self.target]
            if self.cancelled:
                assert not own, 'cancelled result accepted'
                stopped = [r for r in late.get('cancelled_branches', []) if r.get('branch_id') == self.target]
                assert len(stopped) == 1 and stopped[0]['status'] == 'cancelled', 'cancellation disposition lost'
                assert not any(r.get('branch_id') == self.target for key in ('pending_branches', 'active_branches')
                               for r in late.get(key, [])), 'cancelled branch revived'
            else:
                assert len(own) == 1 and durable_evidence(own[0]) == self.target_result, 'accepted target changed'
            outputs = value['response_frame']['output']['outputs']
            assert any(o.get('branch_id') == self.sibling and o.get('status') == 'fulfilled' for o in outputs)
            if self.cancelled:
                assert not any(o.get('branch_id') == self.target and o.get('status') == 'fulfilled' for o in outputs), \
                    'cancelled canonical output fulfilled'

    def recover(self):
        engine = self.engine
        state = load_latest_response_state('stateful-lineage', frames_dir=engine.harness.response_frames_dir)
        engine.counts['durable_recovery_reads'] += 1
        assert state['ok'], state
        self.check_history()
        self.check(state['response_payload'])
        compact = web._build_response_status_lookup_payload({'id': 'stateful-lineage',
            'status': state['response_payload'].get('status'), 'response_payload': state['response_payload']})
        engine.counts['compact_projections'] += 1
        assert compact['frame_id'] == state['response_payload']['response_frame']['frame_id']

    def check_history(self):
        engine = self.engine
        engine.frames = load_response_frame_records('stateful-lineage', frames_dir=engine.harness.response_frames_dir)['frames']
        engine.counts['durable_history_reads'] += 1
        for parent, canonical, prefix in self.sequence.parents:
            recovered = next(f for f in engine.frames if f['frame_id'] == parent['frame_id'])
            assert stable(recovered) == canonical, 'frozen parent rewritten'
            assert engine.ledger_bytes().startswith(prefix), 'parent ledger overwritten'
        for relation in self.parent_relations:
            assert relation['kind'] == 'graph_patch_reopen_successor'
            assert relation['parent_response_id'] == 'stateful-lineage'
            assert any(f['frame_id'] == relation['parent_frame_id'] and
                       f['frame_sequence'] == relation['parent_frame_sequence'] for f in engine.frames)
            assert any(f.get('frame_relation') == relation for f in engine.frames), 'successor relation lost on recovery'

    @invariant()
    def conservation(self):
        if self.sequence is not None and hasattr(self, 'sibling_result'):
            try:
                self.check(self.engine.payload)
            except BaseException:
                self.failed = True
                raise

    def teardown(self):
        if self.sequence is not None:
            engine = self.sequence.engine
            engine.counts['final_ledger_rows'] = len(engine.ledger_bytes().splitlines())
            engine.inputs.update(settled=getattr(self, 'settled', False),
                                 control_requests=getattr(self, 'control_requests', []),
                                 control_boundary_errors=getattr(self, 'boundary_errors', []),
                                 final_stage=getattr(self, 'stage', None))
            # Existing witness writer retains complete frames/sidecars/artifacts
            # only for failures. Routine deterministic controls stay compact.
            engine.control = False
            engine.failed = self.failed
            engine.teardown()


TestLateCancelLineage = LateCancelMachine.TestCase
TestLateCancelLineage.settings = settings(
    max_examples=int(os.environ.get('FRUTH_HYPOTHESIS_ADAPTER', '32')),
    stateful_step_count=min(32, int(os.environ.get('FRUTH_LINEAGE_STEPS', '32'))),
    phases=(Phase.generate,), deadline=None, print_blob=True, report_multiple_bugs=False)


@pytest.mark.parametrize('timing', TIMINGS)
@pytest.mark.parametrize('representation', ['base64', 'data_uri'])
@pytest.mark.parametrize('reverse', [False, True])
def test_cancel_timing_controls(timing, representation, reverse):
    machine = LateCancelMachine()
    machine.control = True
    try:
        machine.accepted(reverse, representation, timing)
        for _ in range(5):
            machine.advance()
        machine.recover()
        machine.observe_settled('repeat_worker')
        machine.observe_settled('late_callback')
        machine.recover()
    except BaseException:
        machine.failed = True
        raise
    finally:
        machine.teardown()


def test_retained_cancellation_failure_blob():
    """Original generated input stays red until a separately authorized fix."""
    replay = reproduce_failure('6.168.5', b'AXicY2BwhEBGMMWAjgEu7wKM')(
        get_state_machine_test(LateCancelMachine, settings=TestLateCancelLineage.settings))
    replay()


@pytest.mark.parametrize('reverse', [False, True])
def test_cancel_queued_successor_preserves_sibling_at_durable_control_boundary(reverse):
    """Reduced C8 regression: no target provider/result or repeat worker needed."""
    machine = LateCancelMachine()
    try:
        machine.accepted(reverse, 'base64', 'before_dispatch')
        for _ in range(4):
            machine.advance()
        before_calls = len(machine.engine.harness.provider_calls)
        machine.control_branch()
        assert len(machine.engine.harness.provider_calls) == before_calls == 1
        machine.recover()
    except BaseException:
        machine.failed = True
        raise
    finally:
        machine.teardown()


@pytest.mark.parametrize('prefix', range(6))
def test_bounded_original_prefix_reduction(prefix):
    """Bounded deterministic prefix reduction, not a global minimality claim.

    The original generated trace has initialization plus five advance actions.
    Execute each prefix and record whether its unchanged oracle detects C8.
    Separate red regressions above retain the defect as an actual test failure.
    """
    machine = LateCancelMachine()
    detected = False
    try:
        machine.accepted(False, 'base64', 'before_dispatch')
        machine.engine.inputs.update(reduction='original_prefix', prefix=prefix)
        for _ in range(prefix):
            try:
                machine.advance()
                machine.conservation()
            except AssertionError as exc:
                assert str(exc).startswith('sibling evidence lost'), 'different reduction failure'
                detected = True
                break
        assert detected == (prefix == 5)
        machine.engine.inputs['reproduced_counterexample'] = detected
    finally:
        machine.teardown()


@pytest.mark.parametrize('fault', ['drop_sibling_result', 'replace_target_binding'])
def test_cancellation_oracle_detects_test_only_result_fault(fault):
    machine = LateCancelMachine()
    try:
        machine.accepted(False, 'base64', 'no_cancel')
        for _ in range(5):
            machine.advance()
        # Deliberately corrupt observations only, leaving runtime and oracle fixed.
        value = deepcopy(machine.engine.payload)
        if fault == 'drop_sibling_result':
            value['late_fill']['fill_results'] = [r for r in value['late_fill']['fill_results']
                                                 if r['branch_id'] != machine.sibling]
        else:
            next(r for r in value['late_fill']['fill_results'] if r['branch_id'] == machine.target)[
                'obligation_id'] = 'a-different-obligation'
        with pytest.raises(AssertionError):
            machine.check(value)
        machine.engine.counts['detected_test_only_faults'] += 1
    finally:
        machine.teardown()
