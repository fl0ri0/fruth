"""Independent bounded two-successor image contracts, using real offline owners.

The preceding one-successor model and its sensitivity controls stay unchanged.
This family has exactly two accepted duties, sequential successors and no
concurrency, upper rebase or arbitrary recursive repair.
"""
from copy import deepcopy
from dataclasses import replace
from functools import wraps
import os
from pathlib import Path

import pytest
from hypothesis import Phase, settings, strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, precondition, rule

import fruth_webserver as web
from fruth_services.response_frames import (
    ResponseFrameParentCASMismatch, append_response_frame_with_parent_cas,
    load_latest_response_state,
)
from tests.test_graph_lineage_c3_c4_corrections import durable_evidence
from tests.test_graph_lineage_stateful_hypothesis import (
    PREPARATION, ROOT_PROMPT, PersistedGraphLineageMachine, graph_of, required_units, stable,
)


def witnessed(method):
    @wraps(method)
    def checked(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except BaseException:
            self.failed = True
            raise
    return checked


class TwoSuccessorMachine(RuleBasedStateMachine):
    control = False

    def __init__(self):
        super().__init__()
        self.engine = None
        self.failed = False

    @initialize(reverse=st.booleans(), variant=st.integers(0, 2))
    @witnessed
    def accepted(self, reverse, variant):
        engine = self.engine = PersistedGraphLineageMachine()
        engine.control = self.control
        engine.accepted(True, variant)
        # These duties/local instructions are declared before runtime proposals.
        self.prompts = {'repair-image': engine.model.local_prompt,
                        'unrelated-image': 'Execute the separately accepted amber star.'}
        self.units = deepcopy(engine.model.units)
        self.order = ('unrelated-image', 'repair-image') if reverse else ('repair-image', 'unrelated-image')
        self.expected = set()
        self.expected_failures = {}
        self.executed = []
        self.accepted_results = {}
        self.public_refs = {}
        self.parents = []
        self.index = 0
        self.stage = 'unfrozen'
        self.keys = []
        self.seeds = set()
        engine.inputs.update(family='two_successors', order=self.order,
                             accepted_local_prompts=self.prompts, qualifying_bytes_hex=engine.model.png.hex())
        graph_of(engine.payload)['downstream_branches'] = []
        graph_of(engine.payload)['downstream_branch_ids'] = []
        engine.request_owner = replace(engine.request_owner, hooks={**engine.request_owner.hooks,
            'attach_late_fill_state': web._attach_late_fill_state,
            'build_late_fill_state': web._build_late_fill_state})
        engine.late = replace(engine.late, prepare_terminal_graph_patch_successor=self.prepare_exact)
        self.freeze()

    @property
    def branch(self):
        return self.order[self.index]

    def record(self, name, **args):
        self.engine.record('two_' + name, index=self.index, stage=self.stage, **args)

    def publish(self, value):
        self.engine.payload = deepcopy(value)
        self.engine.store = {'response_payload': deepcopy(value)}

    def branch_contract(self):
        return {'branch_id': self.branch, 'phase_id': self.branch,
                'obligation_id': 'obligation-' + self.branch, 'capability': 'image_generation',
                'output_type': 'image', 'status': 'pending', 'artifact_prompt': self.prompts[self.branch]}

    def prepare_exact(self, value):
        owner = self.engine.request_owner
        reviewed = owner._attach_graph_patch_lifecycle(
            owner._attach_runtime_graph_repair_evidence(deepcopy(value)), graph_repair_autonomy='apply_safe')
        candidate = next((item for item in graph_of(reviewed).get('successor_reopen_requests', [])
                          if item.get('owed_branch_ids') == [self.branch]), None)
        if candidate is None:
            return {'status': 'not_applicable', 'reason': 'no_exact_bounded_candidate', 'response_payload': value}
        self.engine.last_prepared = owner._prepare_graph_patch_successor_reopen(reviewed, candidate)
        return self.engine.last_prepared

    def freeze(self):
        engine = self.engine
        value = deepcopy(engine.payload)
        value['late_fill'].update(status='partial_failed', pending_branches=[self.branch_contract()],
            materialization_contract_unmet=True, final_materialization_contract_status='unmet')
        value = engine.finalize(value)
        self.publish(value)
        self.parent = deepcopy(value)
        self.parent_frame = deepcopy(value['response_frame'])
        engine.parent = self.parent
        engine.parent_frame = self.parent_frame
        self.parents.append((deepcopy(engine.frames[-1]), stable(engine.frames[-1]), engine.ledger_bytes()))
        owner = engine.request_owner
        self.reviewed = owner._attach_graph_patch_lifecycle(
            owner._attach_runtime_graph_repair_evidence(deepcopy(value)), graph_repair_autonomy='apply_safe')
        self.candidate = next(item for item in graph_of(self.reviewed)['successor_reopen_requests']
                              if item.get('owed_branch_ids') == [self.branch])
        engine.candidate = deepcopy(self.candidate)
        self.stage = 'frozen'
        self.record('freeze')

    @precondition(lambda self: self.stage == 'finished' and self.index == 0)
    @rule()
    @witnessed
    def next_parent(self):
        self.index = 1
        self.freeze()

    @precondition(lambda self: self.stage == 'frozen')
    @rule()
    @witnessed
    def admit(self):
        engine = self.engine
        value, handoff = engine.late._prepare_terminal_graph_patch_successor_handoff(
            deepcopy(self.parent), request_payload=engine.request, assistant_message=PREPARATION,
            artifact_gap={}, source_route_payload=None)
        assert handoff and not handoff.get('skip_schedule'), engine.last_prepared
        relation = value['response_frame']['frame_relation']
        assert relation['kind'] == 'graph_patch_reopen_successor'
        for key in ('parent_frame_id', 'parent_frame_sequence'):
            assert relation[key] == self.parent_frame[key.removeprefix('parent_')]
        assert relation['parent_response_id'] == 'stateful-lineage'
        branches = handoff['artifact_gap']['pending_branches']
        assert [b['branch_id'] for b in branches] == [self.branch]
        assert branches[0]['artifact_prompt'] == self.prompts[self.branch]
        key = value['late_fill']['successor_reopen_execution']['successor_execution_key']
        assert key not in self.keys, 'second duty inherited first execution identity'
        self.keys.append(key)
        self.handoff = deepcopy(handoff)
        engine.handoff = self.handoff
        self.publish(value)
        self.stage = 'admitted'
        self.record('admit', execution_key=key)

    @precondition(lambda self: self.stage == 'frozen')
    @rule(fault=st.sampled_from(('parent_frame_id', 'parent_frame_sequence', 'scope', 'graph', 'contract')))
    @witnessed
    def reject(self, fault):
        engine = self.engine
        candidate = deepcopy(self.candidate)
        if fault == 'scope':
            candidate['owed_branch_ids'] = [self.branch, 'unaccepted-third-image']
        elif fault == 'graph':
            candidate['successor_request_phase_graph']['continuation_required'] = False
        elif fault == 'contract':
            candidate['execution_contract'] = {}
        elif fault == 'parent_frame_sequence':
            candidate[fault] += 1
        else:
            candidate[fault] = 'foreign-parent'
        ledger, calls = engine.ledger_bytes(), len(engine.harness.provider_calls)
        result = engine.request_owner._prepare_graph_patch_successor_reopen(self.reviewed, candidate)
        assert result['status'] == 'blocked' and result['blocked_reasons'], result
        assert engine.ledger_bytes() == ledger and len(engine.harness.provider_calls) == calls
        self.record('reject', fault=fault)

    @precondition(lambda self: self.stage == 'admitted')
    @rule(missing=st.booleans())
    @witnessed
    def local_payload(self, missing):
        engine = self.engine
        gap = {**deepcopy(self.handoff['artifact_gap']), **self.branch_contract()}
        if missing:
            for key in ('artifact_prompt', 'content_payload', 'phase_summary'):
                gap.pop(key, None)
            gap.update(pending_branches=[], execution_contract={})
        prepared = engine.late.prepare_late_fill_request_payload(engine.request,
            expected_capability='image_generation', assistant_message=PREPARATION, artifact_gap=gap)
        if missing:
            assert prepared.get('branch_contract_error')
            assert prepared.get('prompt') != ROOT_PROMPT
        else:
            assert prepared['prompt'] == self.prompts[self.branch]
            assert all(k not in prepared for k in ('input', 'messages', 'inference_messages', 'batch_prompts'))
        self.record('local_payload', missing=missing)

    @precondition(lambda self: self.stage == 'admitted')
    @rule()
    @witnessed
    def execute(self):
        engine = self.engine
        before = len(engine.harness.provider_calls)
        reused = self.branch in self.expected
        engine.late.complete_response_late_fill(response_payload=deepcopy(engine.payload),
            request_payload=engine.request, assistant_message=PREPARATION,
            artifact_gap=deepcopy(self.handoff['artifact_gap']), source_route_payload=None)
        self.publish(engine.store['response_payload'])
        engine.counts['worker_calls'] += 1
        if not reused:
            self.executed.append(self.branch)
            self.expected.add(self.branch)
            assert len(engine.harness.provider_calls) == before + 1
            assert self.prompts[self.branch] in stable(engine.harness.provider_calls[-1]['request'])
            assert ROOT_PROMPT not in stable(engine.harness.provider_calls[-1]['request'])
        else:
            assert len(engine.harness.provider_calls) == before, 'legitimate reuse executed again'
        results = [r for r in engine.payload['late_fill'].get('fill_results', []) if r.get('branch_id') == self.branch]
        assert len(results) == 1, 'exact result lost or duplicated'
        self.accepted_results[self.branch] = durable_evidence(results[0])
        engine.counts['provider_induced_image_writes'] = len(self.executed)
        engine.accepted_result_payload = deepcopy(engine.payload)
        self.stage = 'finished'
        self.record('execute', reused=reused)

    @precondition(lambda self: self.stage in {'admitted', 'finished'})
    @rule()
    @witnessed
    def duplicate(self):
        engine = self.engine
        ledger, calls = engine.ledger_bytes(), len(engine.harness.provider_calls)
        value, handoff = engine.late._prepare_terminal_graph_patch_successor_handoff(
            deepcopy(self.parent), request_payload=engine.request, assistant_message=PREPARATION,
            artifact_gap={}, source_route_payload=None)
        assert handoff.get('skip_schedule') and handoff['status'] == 'already_recorded', handoff
        assert len(engine.harness.provider_calls) == calls and engine.ledger_bytes() == ledger
        with pytest.raises(ResponseFrameParentCASMismatch):
            append_response_frame_with_parent_cas(deepcopy(self.parent_frame),
                expected_parent_frame_id=self.parent_frame['frame_id'],
                expected_parent_frame_sequence=self.parent_frame['frame_sequence'],
                frames_dir=engine.harness.response_frames_dir)
        engine.counts['stale_cas_rejections'] += 1
        self.record('duplicate')

    @precondition(lambda self: self.stage == 'finished')
    @rule()
    @witnessed
    def repeat_worker(self):
        engine = self.engine
        calls = len(engine.harness.provider_calls)
        accepted = deepcopy(engine.payload['late_fill'])
        engine.late.complete_response_late_fill(response_payload=deepcopy(engine.payload),
            request_payload=engine.request, assistant_message=PREPARATION,
            artifact_gap=deepcopy(self.handoff['artifact_gap']), source_route_payload=None)
        self.publish(engine.store['response_payload'])
        engine.counts['worker_calls'] += 1
        assert len(engine.harness.provider_calls) == calls, 'repeated worker executed accepted work'
        # A new finalization may append its own refresh receipts. Accepted
        # execution/result/error facts must remain exact, and no provider runs.
        for key in ('status', 'fill_results', 'completed_branches', 'failed_branches',
                    'cancelled_branches', 'pending_branches', 'active_branches',
                    'successor_reopen_execution', 'error'):
            assert durable_evidence(engine.payload['late_fill'].get(key)) == durable_evidence(accepted.get(key)), key
        self.record('repeat_worker')

    @precondition(lambda self: self.stage == 'admitted')
    @rule()
    @witnessed
    def controlled_failure(self):
        """A controlled owner error, not a claim of real provider failure."""
        engine = self.engine
        error = {'code': 'TWO_SUCCESSOR_CONTROLLED_FAILURE', 'retryable': False,
                 'message': 'Controlled second-duty failure.', 'stage': 'execute_prepared_branch'}
        execution = deepcopy(engine.payload['late_fill']['successor_reopen_execution'])
        execution['status'] = 'failed'
        state = {**deepcopy(engine.payload['late_fill']), 'status': 'failed',
            'pending_branches': [], 'active_branches': [],
            'successor_reopen_execution': execution,
            'failed_branches': [*deepcopy(engine.payload['late_fill'].get('failed_branches') or []),
                                {**self.branch_contract(), 'status': 'failed', 'error': error}],
            'error': error['code']}
        updated = engine.late.merge_late_fill_result_into_response_payload(engine.payload, {}, state)
        self.expected_failures[self.branch] = error
        self.publish(engine.finalize(updated))
        engine.counts['controlled_result_merges'] += 1
        engine.accepted_result_payload = deepcopy(engine.payload)
        self.stage = 'finished'
        self.record('controlled_failure')

    @precondition(lambda self: self.stage == 'finished')
    @rule(status=st.sampled_from(('queued', 'running', 'completed', 'failed')),
          identity=st.sampled_from(('current', 'old', 'foreign')))
    @witnessed
    def stale_callback(self, status, identity):
        engine = self.engine
        before = deepcopy(engine.payload['late_fill'])
        execution = deepcopy(before['successor_reopen_execution'])
        execution['status'] = status
        if identity == 'old':
            execution['successor_execution_key'] = self.keys[0]
        elif identity == 'foreign':
            execution['successor_execution_key'] = 'foreign-execution'
        updated = engine.late.attach_late_fill_state(engine.payload,
            {'status': 'pending', 'fill_results': [], 'completed_branches': [],
             'pending_branches': [self.branch_contract()], 'successor_reopen_execution': execution})
        assert updated['late_fill'] == before, 'stale callback changed accepted results'
        self.publish(updated)
        self.record('stale_callback', status=status, identity=identity)

    @rule()
    @witnessed
    def recover(self):
        engine = self.engine
        state = load_latest_response_state('stateful-lineage', frames_dir=engine.harness.response_frames_dir)
        assert state['ok']
        engine.counts['durable_recovery_reads'] += 1
        self.check_payload(state['response_payload'])
        self.record('recover')

    def seed_image(self, kind):
        """Independent preexisting evidence; never copy the first result's identity."""
        engine = self.engine
        path = engine.harness.images_dir / ('fixture-' + kind + '.png')
        if kind != 'missing':
            path.write_bytes(engine.model.png)
            engine.counts['fixture_saved_image_writes'] += 1
        branch = self.branch_contract()
        record = {'type': 'image', 'path': str(path), 'saved_image_path': str(path),
            'artifact_ref': 'artifact:fixture-' + kind, 'artifact_id': 'fixture-' + kind,
            'source_response_id': 'stateful-lineage', 'origin': 'assistant_output',
            **{k: branch[k] for k in ('branch_id', 'phase_id', 'obligation_id', 'capability')}}
        if kind == 'unbound':
            for key in ('branch_id', 'phase_id', 'obligation_id'):
                record.pop(key)
        elif kind == 'foreign':
            record.update(branch_id='different-image', phase_id='different-image', obligation_id='different-duty')
        elif kind == 'wrong_obligation':
            record['obligation_id'] = 'different-duty'
        elif kind == 'wrong_phase':
            record['phase_id'] = 'different-phase'
        elif kind == 'wrong_response':
            record['source_response_id'] = 'different-response'
        engine.payload.setdefault('artifacts', []).append(deepcopy(record))
        if kind == 'valid':
            engine.payload['late_fill'].setdefault('fill_results', []).append(deepcopy(record))
            self.expected.add(self.branch)
            self.accepted_results[self.branch] = durable_evidence(record)
        self.publish(engine.payload)
        self.seeds.add(kind)
        self.record('seed_image', kind=kind)

    @precondition(lambda self: self.index == 1 and self.stage == 'admitted')
    @rule(kind=st.sampled_from(('unbound', 'foreign', 'wrong_obligation', 'wrong_phase', 'missing', 'wrong_response')))
    @witnessed
    def unrelated_evidence(self, kind):
        if kind not in self.seeds:
            self.seed_image(kind)

    @precondition(lambda self: self.index == 1 and self.stage == 'admitted')
    @rule()
    @witnessed
    def reuse_existing(self):
        self.seed_image('valid')
        self.execute()

    @precondition(lambda self: self.stage != 'finished' or self.index == 0)
    @rule()
    @witnessed
    def advance(self):
        # One legal transition, chosen independently of the runtime verdict.
        if self.stage == 'frozen':
            self.admit()
        elif self.stage == 'admitted':
            self.local_payload(False)
            self.execute()
        else:
            self.next_parent()

    def check_payload(self, payload):
        assert required_units(graph_of(payload)) == self.units, 'accepted duties changed'
        assert payload['output_text'] == PREPARATION
        late = payload.get('late_fill') or {}
        results = late.get('fill_results') or []
        for branch in self.expected:
            matches = [r for r in results if r.get('branch_id') == branch and r.get('phase_id') == branch]
            assert len(matches) == 1, ('accepted result lost/duplicated', branch)
            result = matches[0]
            assert result.get('obligation_id') == 'obligation-' + branch
            assert Path(result['saved_image_path']).read_bytes() == self.engine.model.png
            if branch in self.accepted_results:
                assert durable_evidence(result) == self.accepted_results[branch], 'earlier accepted result changed'
        for branch, error in self.expected_failures.items():
            failed = [r for r in late.get('failed_branches', []) if r.get('branch_id') == branch]
            assert len(failed) == 1 and failed[0]['error'] == error, 'failed duty lost error truth'
            assert not any(r.get('branch_id') == branch for r in results), 'failed duty acquired a result'
        frame = payload['response_frame']
        outputs = frame['output']['outputs']
        artifacts = frame['artifacts'].get('output', [])
        for branch in self.order:
            owned = [o for o in outputs if o.get('branch_id') == branch]
            if branch not in self.expected:
                assert not any(o.get('status') == 'fulfilled' for o in owned), 'unexecuted duty falsely fulfilled'
                continue
            assert len(owned) == 1 and owned[0]['status'] == 'fulfilled', ('own canonical output unresolved', branch)
            ref = owned[0].get('artifact_ref')
            assert ref, 'canonical fulfilled output has no artifact ref'
            records = [a for a in artifacts if a.get('artifact_ref') == ref and a.get('branch_id') == branch]
            assert len(records) == 1 and records[0].get('phase_id') == branch
            result = next(r for r in results if r.get('branch_id') == branch)
            assert records[0]['path'] == result['saved_image_path'], 'canonical result path changed owner'
            if branch in self.public_refs:
                assert ref == self.public_refs[branch], 'earlier canonical identity changed'
            self.public_refs[branch] = ref
        assert len(set(self.public_refs.values())) == len(self.public_refs), 'two duties collapsed into one identity'

    @invariant()
    def conservation(self):
        if self.engine is None:
            return
        try:
            self.check_payload(self.engine.payload)
            assert len(self.engine.harness.provider_calls) == len(self.executed), 'duplicate/invented execution'
            for parent, canonical, prefix in self.parents:
                observed = next(f for f in self.engine.frames if f['frame_id'] == parent['frame_id'])
                assert stable(observed) == canonical, 'frozen parent rewritten'
                assert self.engine.ledger_bytes().startswith(prefix), 'parent ledger rewritten'
        except BaseException:
            self.failed = True
            raise

    def teardown(self):
        if self.engine is not None:
            self.engine.failed = self.failed
            self.engine.inputs['final_expected_completed'] = sorted(self.expected)
            self.engine.inputs['executed_local_duties'] = self.executed
            self.engine.teardown()


TestTwoSuccessorImages = TwoSuccessorMachine.TestCase
TestTwoSuccessorImages.settings = settings(
    max_examples=int(os.environ.get('FRUTH_HYPOTHESIS_ADAPTER', '32')),
    stateful_step_count=int(os.environ.get('FRUTH_LINEAGE_STEPS', '32')),
    # Adapter shrinking exceeded the measured sample allowance. This family
    # bounds generation; full failures plus separate minimal deterministic
    # reproductions are retained. The original lanes still use normal shrinking.
    phases=(Phase.generate,), deadline=None, print_blob=True, report_multiple_bugs=False)


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('second_evidence', ['none', 'valid', 'unbound', 'foreign', 'wrong_obligation',
                                           'wrong_phase', 'missing', 'wrong_response'])
def test_two_successor_identity_and_reuse_controls(reverse, second_evidence):
    machine = TwoSuccessorMachine()
    machine.control = True
    try:
        machine.accepted(reverse, 0)
        machine.reject('scope')
        machine.admit()
        machine.local_payload(False)
        machine.execute()
        machine.recover()
        machine.conservation()
        machine.next_parent()
        machine.reject('parent_frame_id')
        machine.admit()
        machine.local_payload(True)
        machine.local_payload(False)
        if second_evidence != 'none':
            machine.seed_image(second_evidence)
        machine.execute()
        machine.duplicate()
        machine.repeat_worker()
        for status in ('queued', 'running', 'completed', 'failed'):
            for identity in ('current', 'old', 'foreign'):
                machine.stale_callback(status, identity)
        machine.recover()
        machine.conservation()
        assert machine.expected == set(machine.order)
        assert len(machine.executed) == (1 if second_evidence == 'valid' else 2)
    except BaseException:
        machine.failed = True
        raise
    finally:
        machine.teardown()


@pytest.mark.parametrize('reverse', [False, True])
def test_image_reference_survives_next_parent_freeze(reverse):
    """Reference continuity is checked before any second worker can run."""
    machine = TwoSuccessorMachine()
    machine.control = True
    try:
        machine.accepted(reverse, 0)
        machine.admit()
        machine.execute()
        machine.recover()
        machine.conservation()
        machine.next_parent()
        machine.recover()
        machine.conservation()
    except BaseException:
        machine.failed = True
        raise
    finally:
        machine.teardown()


@pytest.mark.parametrize('reverse', [False, True])
def test_failed_second_duty_keeps_first_result_and_blocker(reverse):
    machine = TwoSuccessorMachine()
    machine.control = True
    try:
        machine.accepted(reverse, 0)
        machine.admit()
        machine.execute()
        machine.recover()
        machine.next_parent()
        machine.admit()
        machine.controlled_failure()
        machine.duplicate()
        machine.stale_callback('completed', 'old')
        machine.recover()
        machine.conservation()
    except BaseException:
        machine.failed = True
        raise
    finally:
        machine.teardown()
