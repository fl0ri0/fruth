"""Bounded additive repair / freeze / successor / recovery composition.

Expected duties and local work precede runtime proposals and provider output.
The cheap owner lane does not claim provider execution or durable persistence.
The adapter lane reuses the real isolated worker, provider adapters and writer.
"""
from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import dataclass, replace
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time

import pytest
from hypothesis import settings, strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, precondition, rule

import fruth_webserver as web
from fruth_services.response_frames import (
    ResponseFrameParentCASMismatch, append_response_frame_with_parent_cas,
    build_response_frame, enrich_response_frame_metadata, load_latest_response_state,
    load_response_frame_records, response_payload_from_frame,
)
from tests.fake_backends.fixtures import tiny_png_bytes
from tests.test_graph_repair_self_healing import GraphRepairSelfHealingTests
from tests.test_instruction_admission_contract import real_owners


PREPARATION = 'Accepted preparation: preserve this exact sentence.'
ROOT_PROMPT = 'Describe the accepted scene, create its image, and retain other owed work.'
ERROR = 'CONTROLLED_PROVIDER_FAILURE'
_SERIAL = Counter()


def witnessed(function):
    """Retain failing rule attempts and every Hypothesis shrink invocation."""
    @wraps(function)
    def invoke(self, *args, **kwargs):
        try:
            return function(self, *args, **kwargs)
        except BaseException as exc:
            self.failed = True
            self.operations.append({'operation': function.__name__, 'failed_attempt': True,
                                    'args': args, 'kwargs': kwargs, 'error': repr(exc)})
            raise
    return invoke


def stable(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, default=str)


def graph_of(payload):
    return payload['runtime']['request_phase_graph']


def required_units(graph):
    """Read observations without using a runtime validity/identity matcher."""
    return {item['obligation_id']: (item.get('branch_id'), item.get('phase_id'),
            item.get('capability'), item.get('output_type'), item.get('required', True))
            for item in graph.get('output_obligations', [])}


@dataclass
class Reference:
    units: dict
    local_prompt: str
    png: bytes
    admitted: bool = False
    outcome: str | None = None
    frozen: bool = False
    refrozen: bool = False

    def check(self, payload):
        observed = required_units(graph_of(payload))
        for identity, meaning in self.units.items():
            assert observed.get(identity) == meaning, ('lost/substituted duty', identity, observed)
        assert payload.get('output_text') == PREPARATION, 'preparation output changed'
        repair = [o for o in payload.get('outputs', [])
                  if o.get('branch_id') == 'repair-image' or o.get('phase_id') == 'repair-image']
        observed_outputs = list(payload.get('outputs', []))
        if self.refrozen:
            observed_outputs += payload['response_frame']['output']['outputs']
        for identity, meaning in self.units.items():
            branch, phase, _, output_type, _ = meaning
            if output_type == 'image' and branch != 'repair-image':
                assert not any(item.get('status') == 'fulfilled' and (
                    item.get('obligation_id') == identity or item.get('branch_id') == branch or
                    item.get('phase_id') == phase) for item in observed_outputs), \
                    'unexecuted unrelated duty falsely fulfilled'
        if self.outcome != 'completed':
            assert not any(o.get('status') == 'fulfilled' for o in repair), 'invented fulfillment'
        if self.outcome == 'failed':
            assert ERROR in stable(payload.get('late_fill', {})), 'blocking evidence erased'
        if self.outcome == 'completed':
            results = [item for item in payload.get('late_fill', {}).get('fill_results', [])
                       if item.get('branch_id') == 'repair-image' and item.get('phase_id') == 'repair-image']
            assert len(results) == 1, 'accepted result binding erased'
            path = Path(results[0]['saved_image_path'])
            assert path.read_bytes() == self.png, 'accepted result bytes changed'
            if self.refrozen:
                # The just-built frozen frame owns canonical outputs. The
                # in-flight outer compatibility projection can lag that frame.
                frozen_outputs = payload['response_frame']['output']['outputs']
                assert any(item.get('branch_id') == 'repair-image' and
                           item.get('phase_id') == 'repair-image' and
                           item.get('status') == 'fulfilled' for item in frozen_outputs), \
                    'validated repair no longer fulfills its own output'
        if not self.admitted:
            assert 'repair-image' not in graph_of(payload).get('downstream_branch_ids', []), \
                'proposal created executable work'

    def check_lineage(self, payload, parent_frame):
        relation = payload['response_frame']['frame_relation']
        assert relation['kind'] == 'graph_patch_reopen_successor'
        assert relation['parent_response_id'] == 'stateful-lineage'
        assert relation['parent_frame_id'] == parent_frame['frame_id'], 'foreign predecessor'
        assert relation['parent_frame_sequence'] == parent_frame['frame_sequence'], 'stale predecessor'


def check_frozen(frame, canonical, ledger=None, prefix=None):
    assert stable(frame) == canonical, 'frozen parent rewritten'
    if ledger is not None:
        assert ledger.startswith(prefix), 'parent ledger bytes rewritten'


class GraphLineageMachine(RuleBasedStateMachine):
    """One exact additive successor; no upper rebase, maintenance or arbitrary calls."""
    persistent = False
    automatic = False
    control = False

    def __init__(self):
        super().__init__()
        self.stack = ExitStack()
        self.operations = []
        self.counts = Counter()
        self.states = Counter()
        self.frames = []
        self.frozen_values = []
        self.ledger_prefix = b''
        self.parent = None
        self.reviewed = None
        self.candidate = None
        self.handoff = None
        self.failed = False
        self.observations = []
        self.started = time.monotonic()

    @initialize(unrelated=st.booleans(), variant=st.integers(min_value=0, max_value=2))
    @witnessed
    def accepted(self, unrelated, variant):
        # Independently accepted identities and values; not read from an actual graph.
        units = {'obligation-preparation': ('phase-1', 'phase-1', 'chat', 'text', True),
                 'obligation-repair-image': ('repair-image', 'repair-image',
                                             'image_generation', 'image', True)}
        if unrelated:
            units['obligation-unrelated-image'] = ('unrelated-image', 'unrelated-image',
                                                  'image_generation', 'image', True)
        prompt = ('Draw the single accepted cobalt circle.',
                  'Draw the single accepted amber triangle.',
                  'Draw the single accepted green square.')[variant]
        self.model = Reference(units, prompt, tiny_png_bytes())
        self.inputs = {'unrelated': unrelated, 'variant': variant, 'accepted_units': units,
                       'local_prompt': prompt, 'png_sha256': hashlib.sha256(self.model.png).hexdigest()}
        self.context = os.environ.get('FRUTH_LINEAGE_CONTEXT', 'unrecorded')
        tmp = self.stack.enter_context(tempfile.TemporaryDirectory(prefix='fruth-lineage-'))
        self.harness = self.stack.enter_context(real_owners(Path(tmp), 'Controlled preparation.'))
        self.stack.enter_context(web.app.app_context())
        # A supported narrow fixture override, not a changed policy/default or safety limit.
        from unittest.mock import patch
        self.stack.enter_context(patch.dict(os.environ, {'FRUTH_GRAPH_REPAIR_AUTONOMY': 'apply_safe'}))
        self.request = {'prompt': ROOT_PROMPT, 'input': ROOT_PROMPT,
                        'messages': [{'role': 'user', 'content': ROOT_PROMPT}]}
        fixture = GraphRepairSelfHealingTests()
        self.request_owner = fixture._runtime_owner()
        graph = fixture._base_graph()
        graph['output_obligations'] = [
            {'obligation_id': identity, 'branch_id': unit[0], 'phase_id': unit[1],
             'capability': unit[2], 'output_type': unit[3], 'required': True,
             'contract_state': 'promoted', 'status': 'fulfilled' if unit[0] == 'phase-1' else 'pending'}
            for identity, unit in units.items()]
        if unrelated:
            graph['downstream_branch_ids'] = ['unrelated-image']
            graph['downstream_branches'] = [{
                'branch_id': 'unrelated-image', 'phase_id': 'unrelated-image',
                'obligation_id': 'obligation-unrelated-image', 'capability': 'image_generation',
                'output_type': 'image', 'status': 'pending',
                'artifact_prompt': 'Separate accepted work; not this successor.'}]
        self.payload = {
            'id': 'stateful-lineage', 'response_id': 'stateful-lineage', 'object': 'response',
            'status': 'completed', 'lifecycle_state': 'repair_needed', 'mode': 'chat',
            'capability': 'chat', 'output_text': PREPARATION,
            'runtime': {'request_phase_graph': graph},
            'late_fill': {'status': 'partial_failed',
                'final_materialization_contract_status': 'unmet', 'materialization_contract_unmet': True,
                'pending_branches': [{'phase_id': 'repair-image', 'branch_id': 'repair-image',
                    'obligation_id': 'obligation-repair-image', 'capability': 'image_generation',
                    'output_type': 'image', 'status': 'pending', 'artifact_prompt': prompt}]}}
        self.store = {'response_payload': deepcopy(self.payload)}

        def touch(rid, **kwargs):
            assert rid == 'stateful-lineage'
            if 'response_payload' in kwargs:
                self.store = {'response_payload': deepcopy(kwargs['response_payload'])}
            return deepcopy(self.store)

        self.late = replace(web._LATE_FILL_RUNTIME,
            get_response_lookup_record=lambda rid: deepcopy(self.store),
            touch_response_lookup=touch,
            ensure_response_lookup_for_payload=lambda *a, **kw: None,
            finalize_response_frame_payload=self.finalize,
            prepare_terminal_graph_patch_successor=self.prepare_successor,
            load_running_instances=self.harness._load_running_instances,
            merge_instances_with_runtime_status=self.harness._merge_instances_with_runtime_status,
            resolve_inference_auto_route=web._resolve_inference_auto_route,
            release_response_late_fill=lambda rid: self.counts.update(['worker_release']),
            schedule_post_response_substrate_hygiene=None)
        self.record('initialize')

    def prepare_successor(self, value):
        if self.automatic:
            self.last_prepared = self.request_owner.prepare_terminal_graph_patch_successor(
                value, graph_repair_autonomy='apply_safe')
        else:
            # Exercise the existing exact validated-candidate sink, separately
            # from the automatic producer's redraw-orientation composition.
            reviewed = self.request_owner._attach_graph_patch_lifecycle(
                self.request_owner._attach_runtime_graph_repair_evidence(deepcopy(value)),
                graph_repair_autonomy='apply_safe')
            candidate = next(item for item in graph_of(reviewed)['successor_reopen_requests']
                             if item.get('owed_branch_ids') == ['repair-image'])
            self.last_prepared = self.request_owner._prepare_graph_patch_successor_reopen(reviewed, candidate)
        return self.last_prepared

    def record(self, name, **arguments):
        self.operations.append({'operation': name, **arguments})
        self.counts[name] += 1
        state = ('settled_' + self.model.outcome if self.model.outcome else
                 'queued' if self.model.admitted else 'frozen' if self.model.frozen else 'initial')
        self.states[state] += 1

    def finalize(self, value, **kwargs):
        self.counts['frame_builds'] += 1
        if self.persistent:
            before = self.ledger_bytes()
            value = self.harness.freeze_manual_response(deepcopy(value), request_payload=self.request)
            after = self.ledger_bytes()
            assert after.startswith(before), 'historical ledger changed'
            self.counts['ledger_appends'] += len(after.splitlines()) - len(before.splitlines())
            self.counts['persistence_calls'] += 1
            self.frames = load_response_frame_records('stateful-lineage',
                frames_dir=self.harness.response_frames_dir)['frames']
        else:
            frame = build_response_frame(value, request_payload=self.request)
            frame = enrich_response_frame_metadata(frame, previous_frames=self.frames, force_append_sequence=True)
            self.frames.append(deepcopy(frame))
            value = response_payload_from_frame(frame)
        return deepcopy(value)

    def ledger_bytes(self):
        path = self.harness.response_frames_dir / 'responses.jsonl'
        return path.read_bytes() if path.exists() else b''

    @precondition(lambda self: not self.model.admitted)
    @rule(mode=st.sampled_from(('shadow', 'stage')))
    @witnessed
    def propose(self, mode):
        before = required_units(graph_of(self.payload))
        branches = deepcopy(graph_of(self.payload).get('downstream_branches', []))
        evidence = self.request_owner._attach_runtime_graph_repair_evidence(deepcopy(self.payload))
        observed = self.request_owner._attach_graph_patch_lifecycle(evidence, graph_repair_autonomy=mode)
        assert required_units(graph_of(observed)) == before
        assert graph_of(observed).get('downstream_branches', []) == branches
        assert not self.harness.provider_calls
        self.record('propose', mode=mode)

    @precondition(lambda self: not self.model.frozen)
    @rule()
    @witnessed
    def freeze_parent(self):
        self.payload = self.finalize(self.payload)
        self.parent = deepcopy(self.payload)
        self.parent_frame = deepcopy(self.payload['response_frame'])
        self.parent_canonical = stable(self.frames[0])
        self.ledger_prefix = self.ledger_bytes()
        self.model.frozen = True
        self.reviewed = self.request_owner._attach_graph_patch_lifecycle(
            self.request_owner._attach_runtime_graph_repair_evidence(deepcopy(self.parent)),
            graph_repair_autonomy='apply_safe')
        self.candidate = next(deepcopy(item) for item in
            graph_of(self.reviewed)['successor_reopen_requests']
            if item.get('owed_branch_ids') == ['repair-image'])
        self.record('freeze_parent')

    @precondition(lambda self: self.model.frozen and not self.model.admitted)
    @rule(fault=st.sampled_from(('parent_frame_id', 'parent_frame_sequence', 'parent_response_id',
              'successor_execution_key', 'successor_reopen_key', 'scope', 'graph', 'contract', 'off')))
    @witnessed
    def reject_successor(self, fault):
        before = self.ledger_bytes()
        candidate = deepcopy(self.candidate)
        if fault == 'off':
            result = self.request_owner.prepare_terminal_graph_patch_successor(self.parent,
                graph_repair_autonomy='off')
            assert result.get('reason') == 'graph_repair_autonomy_off'
        else:
            if fault == 'scope':
                candidate['owed_branch_ids'] = ['repair-image', 'unaccepted-image']
            elif fault == 'graph':
                candidate['successor_request_phase_graph']['continuation_required'] = False
            elif fault == 'contract':
                candidate['execution_contract'] = {}
            elif fault == 'parent_frame_sequence':
                candidate[fault] += 1
            else:
                candidate[fault] = 'foreign-or-stale'
            result = self.request_owner._prepare_graph_patch_successor_reopen(self.reviewed, candidate)
            assert result['status'] == 'blocked' and result['blocked_reasons'], result
        assert self.ledger_bytes() == before
        assert not self.harness.provider_calls
        self.record('reject_successor', fault=fault)

    @precondition(lambda self: self.model.frozen and not self.model.admitted)
    @rule()
    @witnessed
    def admit(self):
        before = deepcopy(self.parent)
        self.payload, self.handoff = self.late._prepare_terminal_graph_patch_successor_handoff(
            deepcopy(self.parent), request_payload=self.request, assistant_message=PREPARATION,
            artifact_gap={}, source_route_payload=None)
        assert self.handoff and not self.handoff.get('skip_schedule'), self.last_prepared
        assert self.parent == before
        relation = self.payload['response_frame']['frame_relation']
        assert relation['kind'] == 'graph_patch_reopen_successor'
        assert relation['parent_frame_id'] == self.parent_frame['frame_id']
        assert relation['parent_frame_sequence'] == self.parent_frame['frame_sequence']
        assert relation['parent_response_id'] == 'stateful-lineage'
        pending = self.handoff['artifact_gap']['pending_branches']
        assert [branch['branch_id'] for branch in pending] == ['repair-image']
        assert pending[0]['artifact_prompt'] == self.model.local_prompt
        self.model.admitted = True
        self.record('admit')

    def branch_gap(self):
        branch = deepcopy(self.handoff['artifact_gap']['pending_branches'][0])
        return {**deepcopy(self.handoff['artifact_gap']), **branch}

    @precondition(lambda self: self.model.admitted and not self.model.outcome)
    @rule(missing=st.booleans())
    @witnessed
    def local_work(self, missing):
        gap = self.branch_gap()
        if missing:
            for key in ('artifact_prompt', 'content_payload', 'phase_summary'):
                gap.pop(key, None)
            gap['pending_branches'] = []
            gap['execution_contract'] = {}
        prepared = self.late.prepare_late_fill_request_payload(self.request,
            expected_capability='image_generation', assistant_message=PREPARATION, artifact_gap=gap)
        if missing:
            assert prepared.get('branch_contract_error'), prepared
            assert prepared.get('prompt') != ROOT_PROMPT
        else:
            assert prepared['prompt'] == self.model.local_prompt, prepared
            assert all(key not in prepared for key in ('input', 'messages', 'inference_messages', 'batch_prompts'))
        self.record('local_work', missing=missing)

    @precondition(lambda self: self.model.admitted and not self.model.outcome)
    @rule(success=st.booleans())
    @witnessed
    def result(self, success):
        # Expensive adapter sequences use successful real provider/writer results.
        # Controlled provider-error evidence is explored separately by the owner lane.
        if self.persistent:
            success = True
            self.late.complete_response_late_fill(
                response_payload=deepcopy(self.payload), request_payload=self.request,
                assistant_message=PREPARATION, artifact_gap=deepcopy(self.handoff['artifact_gap']),
                source_route_payload=None)
            self.payload = deepcopy(self.store['response_payload'])
            self.counts['worker_calls'] += 1
            self.counts['adapter_calls'] = len(self.harness.provider_calls)
            files = [path for path in self.harness.images_dir.rglob('*') if path.is_file()]
            assert len(files) == 1, files
            assert files[0].read_bytes() == self.model.png
            calls = [call for call in self.harness.provider_calls if
                     call['url'].endswith(('/v1/images/generations', '/api/generate'))]
            assert len(calls) == 1, calls
            assert self.model.local_prompt in stable(calls[0]['request'])
            assert ROOT_PROMPT not in stable(calls[0]['request'])
            self.counts['provider_induced_image_writes'] = len(files)
        else:
            execution = deepcopy(self.payload['late_fill']['successor_reopen_execution'])
            execution['status'] = 'completed' if success else 'failed'
            branch = deepcopy(self.handoff['artifact_gap']['pending_branches'][0])
            branch['status'] = 'fulfilled' if success else 'failed'
            state = {**deepcopy(self.payload['late_fill']),
                'status': 'completed' if success else 'failed', 'pending_branches': [], 'active_branches': [],
                'successor_reopen_execution': execution, 'fill_results': [],
                'completed_branches': [], 'failed_branches': []}
            result = {}
            if success:
                path = self.harness.images_dir / 'controlled-owner-image.png'
                path.write_bytes(self.model.png)
                self.counts['fixture_saved_image_writes'] += 1
                result = {'saved_image_path': str(path), 'branch_id': 'repair-image',
                    'phase_id': 'repair-image', 'capability': 'image_generation',
                    'artifacts': [{'type': 'image', 'path': str(path), 'branch_id': 'repair-image',
                                   'phase_id': 'repair-image'}]}
                state['fill_results'] = [deepcopy(result)]
                state['completed_branches'] = [branch]
            else:
                branch['error'] = {'code': ERROR, 'message': 'Controlled provider failed.',
                                   'retryable': False, 'stage': 'execute_prepared_branch'}
                state['failed_branches'] = [branch]
                state['error'] = ERROR
            self.payload = self.late.merge_late_fill_result_into_response_payload(self.payload, result, state)
            self.store = {'response_payload': deepcopy(self.payload)}
            self.counts['controlled_result_merges'] += 1
        self.model.outcome = 'completed' if success else 'failed'
        self.accepted_result_payload = deepcopy(self.payload)
        if success:
            assert self.payload['late_fill']['successor_reopen_execution']['status'] == 'completed'
        self.record('result', outcome=self.model.outcome)

    @precondition(lambda self: bool(self.model.outcome))
    @rule(status=st.sampled_from(('queued', 'running', 'completed', 'failed')))
    @witnessed
    def stale_callback(self, status):
        execution = deepcopy(self.payload['late_fill']['successor_reopen_execution'])
        execution['status'] = status
        state = {'status': 'pending', 'pending_branches': [deepcopy(self.branch_gap())],
                 'active_branches': [], 'successor_reopen_execution': execution}
        updated = self.late.attach_late_fill_state(deepcopy(self.payload), state)
        self.observations.append({'boundary': 'terminal_callback', 'submitted': state,
                                  'before': deepcopy(self.payload), 'after': deepcopy(updated)})
        assert updated['late_fill']['successor_reopen_execution']['status'] == self.model.outcome
        assert not updated['late_fill'].get('pending_branches')
        self.payload = updated
        self.store = {'response_payload': deepcopy(updated)}
        self.record('stale_callback', status=status)

    @precondition(lambda self: bool(self.model.outcome) and not self.model.refrozen)
    @rule()
    @witnessed
    def freeze_result(self):
        self.payload = self.finalize(self.payload)
        self.model.refrozen = True
        self.store = {'response_payload': deepcopy(self.payload)}
        self.record('freeze_result')

    @precondition(lambda self: self.model.frozen)
    @rule()
    @witnessed
    def recover(self):
        frame = deepcopy(self.frames[-1])
        if self.persistent:
            state = load_latest_response_state('stateful-lineage', frames_dir=self.harness.response_frames_dir)
            assert state['ok'] is True, state
            observed = state['response_payload']
            self.counts['durable_recovery_reads'] += 1
        else:
            observed = response_payload_from_frame(frame)
            self.counts['owner_frame_reconstructions'] += 1
        self.observations.append({'boundary': 'recovery', 'payload': deepcopy(observed)})
        # A frame frozen before its later in-flight result still owes the old work.
        expected = replace(self.model)
        if self.model.outcome and not self.model.refrozen and not self.persistent:
            expected.outcome = None
        expected.check(observed)
        compact = web._build_response_status_lookup_payload({
            'id': 'stateful-lineage', 'status': observed.get('status'),
            'response_payload': deepcopy(observed)})
        assert compact.get('id') == 'stateful-lineage'
        assert compact.get('frame_id') == frame['frame_id']
        if expected.outcome != 'completed':
            assert compact.get('lifecycle_state') != 'completed', compact
        self.counts['compact_projections'] += 1
        self.record('recover')

    @precondition(lambda self: self.model.admitted)
    @rule()
    @witnessed
    def duplicate(self):
        calls, ledger = len(self.harness.provider_calls), self.ledger_bytes()
        payload, handoff = self.late._prepare_terminal_graph_patch_successor_handoff(
            deepcopy(self.parent), request_payload=self.request, assistant_message=PREPARATION,
            artifact_gap={}, source_route_payload=None)
        assert handoff['status'] == 'already_recorded' and handoff['skip_schedule'], handoff
        assert payload['response_frame']['frame_id'] == self.payload['response_frame']['frame_id']
        assert len(self.harness.provider_calls) == calls and self.ledger_bytes() == ledger
        if self.persistent:
            with pytest.raises(ResponseFrameParentCASMismatch):
                append_response_frame_with_parent_cas(deepcopy(self.parent_frame),
                    expected_parent_frame_id=self.parent_frame['frame_id'],
                    expected_parent_frame_sequence=self.parent_frame['frame_sequence'],
                    frames_dir=self.harness.response_frames_dir)
            assert self.ledger_bytes() == ledger
            self.counts['stale_cas_rejections'] += 1
        self.record('duplicate')

    @invariant()
    def conservation(self):
        if not hasattr(self, 'model'):
            return
        try:
            self.model.check(self.payload)
            if self.model.frozen:
                check_frozen(self.frames[0], self.parent_canonical)
                assert stable(self.parent['response_frame']) == stable(self.parent_frame)
                if self.persistent:
                    check_frozen(self.frames[0], self.parent_canonical,
                                 self.ledger_bytes(), self.ledger_prefix)
            if self.model.admitted and not self.model.outcome:
                self.model.check_lineage(self.payload, self.parent_frame)
            assert len(self.harness.provider_calls) <= 1, 'duplicate adapter execution'
        except BaseException:
            self.failed = True
            raise

    def teardown(self):
        try:
            if hasattr(self, 'model'):
                lane = 'producer' if self.automatic else 'adapter' if self.persistent else 'owner'
                self.counts['adapter_calls'] = len(self.harness.provider_calls)
                record = {'kind': 'fruth.graph_lineage_stateful_sequence', 'lane': lane,
                    'control': self.control, 'context': self.context,
                    'inputs': self.inputs, 'operations': self.operations,
                    'counts': dict(self.counts), 'states': dict(self.states),
                    'outcome': self.model.outcome, 'failed': self.failed,
                    'elapsed_seconds': round(time.monotonic() - self.started, 6)}
                if self.failed or self.control:
                    record['witness'] = {'accepted_request': self.request,
                        'parent': self.parent, 'payload': self.payload, 'frames': self.frames,
                        'candidate': self.candidate, 'handoff': self.handoff,
                        'last_prepared': getattr(self, 'last_prepared', None),
                        'accepted_result_payload': getattr(self, 'accepted_result_payload', None),
                        'observations': self.observations,
                        'frame_sidecars': {str(path.relative_to(self.harness.response_frames_dir)): {
                            'bytes_hex': path.read_bytes().hex(),
                            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                            for path in (self.harness.response_frames_dir / 'snapshots').rglob('*')
                            if path.is_file()} if self.persistent else {},
                        'ledger_bytes_hex': self.ledger_bytes().hex() if self.persistent else '',
                        'physical_files': {str(path.relative_to(self.harness.root)): {
                            'bytes_hex': path.read_bytes().hex(),
                            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                            for path in self.harness.artifacts_dir.rglob('*') if path.is_file()},
                        'provider_calls': self.harness.provider_calls}
                evidence = os.environ.get('FRUTH_HYPOTHESIS_EVIDENCE_DIR')
                if evidence:
                    directory = Path(evidence)
                    directory.mkdir(exist_ok=True)
                    _SERIAL[lane] += 1
                    path = directory / ('lineage-' + lane + '-' + str(_SERIAL[lane]).zfill(5) + '.json')
                    assert not path.exists(), 'append-only witness collision'
                    path.write_text(json.dumps(record, indent=2, default=str) + '\n')
        finally:
            self.stack.close()


def budgets(lane):
    return settings(max_examples=int(os.environ.get('FRUTH_HYPOTHESIS_' + lane.upper(),
                         '12' if lane == 'adapter' else '128')),
                    stateful_step_count=int(os.environ.get('FRUTH_LINEAGE_STEPS', '24')),
                    deadline=None, print_blob=True, report_multiple_bugs=False)


TestGraphLineageOwners = GraphLineageMachine.TestCase
TestGraphLineageOwners.settings = budgets('owner')


class PersistedGraphLineageMachine(GraphLineageMachine):
    persistent = True


TestGraphLineageAdapters = PersistedGraphLineageMachine.TestCase
TestGraphLineageAdapters.settings = budgets('adapter')


@pytest.mark.parametrize('persistent', [False, True])
@pytest.mark.parametrize('unrelated', [False, True])
def test_exact_successor_control(persistent, unrelated):
    machine = PersistedGraphLineageMachine() if persistent else GraphLineageMachine()
    machine.control = True
    try:
        machine.accepted(unrelated, 0)
        machine.propose('shadow')
        machine.propose('stage')
        machine.freeze_parent()
        machine.recover()
        for fault in ('parent_frame_id', 'parent_frame_sequence', 'parent_response_id',
                      'successor_execution_key', 'successor_reopen_key', 'scope', 'graph', 'contract', 'off'):
            machine.reject_successor(fault)
        machine.admit()
        machine.local_work(False)
        machine.local_work(True)
        machine.duplicate()
        machine.result(True)
        for status in ('queued', 'running', 'failed'):
            machine.stale_callback(status)
        machine.freeze_result()
        machine.duplicate()
        machine.recover()
        machine.recover()
        machine.conservation()
    except BaseException:
        machine.failed = True
        raise
    finally:
        machine.teardown()


def test_blocked_result_control():
    machine = GraphLineageMachine()
    machine.control = True
    try:
        machine.accepted(True, 1)
        machine.freeze_parent()
        machine.admit()
        machine.result(False)
        machine.freeze_result()
        machine.stale_callback('completed')
        machine.recover()
        machine.recover()
        machine.conservation()
    except BaseException:
        machine.failed = True
        raise
    finally:
        machine.teardown()


@pytest.mark.parametrize('fault', ['drop', 'substitute', 'invent_fulfillment',
                                 'invent_unrelated_fulfillment', 'erase_blocker',
                                 'frozen_parent', 'lineage', 'root_replay', 'erase_result'])
def test_independent_oracle_detects_fixture_fault(fault):
    machine = GraphLineageMachine()
    machine.control = True
    try:
        machine.accepted(True, 0)
        payload = deepcopy(machine.payload)
        if fault == 'drop':
            graph_of(payload)['output_obligations'].pop()
        elif fault == 'substitute':
            graph_of(payload)['output_obligations'][1]['branch_id'] = 'unaccepted-image'
        elif fault == 'invent_fulfillment':
            payload['outputs'] = [{'branch_id': 'repair-image', 'status': 'fulfilled'}]
        elif fault == 'invent_unrelated_fulfillment':
            payload['outputs'] = [{'branch_id': 'unrelated-image', 'status': 'fulfilled'}]
        elif fault == 'erase_blocker':
            machine.model.outcome = 'failed'
            payload['late_fill'] = {'status': 'failed'}
        elif fault == 'frozen_parent':
            machine.freeze_parent()
            frame = deepcopy(machine.frames[0])
            frame['output']['text'] = 'Substituted parent output.'
            with pytest.raises(AssertionError):
                check_frozen(frame, machine.parent_canonical)
            return
        elif fault == 'erase_result':
            machine.freeze_parent()
            machine.admit()
            machine.result(True)
            payload = deepcopy(machine.payload)
            payload['late_fill'].pop('fill_results')
            with pytest.raises(AssertionError):
                machine.model.check(payload)
            return
        else:
            machine.freeze_parent()
            machine.admit()
            if fault == 'lineage':
                payload = deepcopy(machine.payload)
                payload['response_frame']['frame_relation']['parent_frame_id'] = 'foreign-parent'
                with pytest.raises(AssertionError):
                    machine.model.check_lineage(payload, machine.parent_frame)
            else:
                # The fixture mutates the submitted input, not the runtime owner.
                observed_prompt = ROOT_PROMPT
                with pytest.raises(AssertionError):
                    assert observed_prompt == machine.model.local_prompt
            return
        with pytest.raises(AssertionError):
            machine.model.check(payload)
    finally:
        machine.teardown()
