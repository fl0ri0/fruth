"""Construct and finalize a response before handing exact truth to persistence.

The composition is independent of HTTP. The commit adapter owns durable writes;
read projections preserve frozen identity and never enter the commit operation.
"""
from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional
from fruth_orchestration.working_frame import build_working_frame as _build_working_frame
from fruth_services.events import causal_snapshot, causal_timing, measure_operation
from fruth_services.response_frame_commit import ResponseFrameCommit
from fruth_services.response_frames import enrich_response_frame_metadata as _enrich_response_frame_metadata
from fruth_services.responses import hoist_response_output_surfaces as _hoist_response_output_surfaces
from fruth_services.response_lifecycle import (
    _attach_response_status_semantics, _preserve_frozen_response_frame_identity,
)


@dataclass(frozen=True)
class ResponseFrameFinalizer:
    attach_frame: Callable[..., dict[str, Any]]
    frame_commit: ResponseFrameCommit
    persistence_disabled: Callable[[], bool]

    def finalize(
        self,
        response_payload: dict[str, Any],
        *,
        request_payload: Optional[dict[str, Any]] = None,
        persist: bool = True,
        expected_parent_frame_id: Optional[str] = None,
        expected_parent_frame_sequence: Optional[int] = None,
    ) -> dict[str, Any]:
        total_started_at = time.perf_counter()
        response_payload = dict(response_payload)
        if persist:
            response_payload.pop('persistence', None)
        raw_late_fill = response_payload.get('late_fill') if isinstance(response_payload.get('late_fill'), Mapping) else {}

        def _branch_count(key: str) -> int:
            values = raw_late_fill.get(key) if isinstance(raw_late_fill, Mapping) else None
            return len(values) if isinstance(values, list) else 0

        pending_count = _branch_count('pending_branches')
        active_count = _branch_count('active_branches')
        completed_count = _branch_count('completed_branches')
        failed_count = _branch_count('failed_branches')
        late_fill_status = str(raw_late_fill.get('status') or '').strip().lower() if raw_late_fill else ''
        if raw_late_fill and (pending_count or active_count or late_fill_status in {'pending', 'running'}):
            timing_phase = 'nonterminal_late_fill'
        elif raw_late_fill:
            timing_phase = 'terminal_late_fill'
        else:
            timing_phase = 'ordinary_response'
        finalize_timing: dict[str, Any] = {
            'kind': 'fruth.response_frame_finalize_timing',
            'phase': timing_phase,
            'persist_requested': bool(persist),
            'persist_effective': bool(persist and not self.persistence_disabled()),
            'late_fill_status': late_fill_status or None,
            'pending_branch_count': pending_count,
            'active_branch_count': active_count,
            'completed_branch_count': completed_count,
            'failed_branch_count': failed_count,
            'steps': [],
        }

        def _mark_step(name: str, started_at: float, **metadata: Any) -> None:
            entry: dict[str, Any] = {
                'name': name,
                'elapsed_ms': round((time.perf_counter() - started_at) * 1000, 3),
            }
            for key, value in metadata.items():
                if value not in (None, '', [], {}):
                    entry[key] = value
            finalize_timing['steps'].append(entry)

        def _publish_finalize_timing(payload: dict[str, Any]) -> dict[str, Any]:
            finalize_timing.update(causal_timing())
            telemetry = causal_snapshot(payload.get('id'))
            finalize_timing['total_elapsed_ms'] = round((time.perf_counter() - total_started_at) * 1000, 3)
            runtime = dict(payload.get('runtime') or {}) if isinstance(payload.get('runtime'), Mapping) else {}
            developer_diagnostics = (
                dict(runtime.get('developer_diagnostics'))
                if isinstance(runtime.get('developer_diagnostics'), Mapping)
                else {}
            )
            if telemetry is not None:
                developer_diagnostics['causal_telemetry'] = telemetry
            developer_diagnostics['response_frame_finalize_timing'] = dict(finalize_timing)
            runtime['developer_diagnostics'] = developer_diagnostics
            payload['runtime'] = runtime
            frame = payload.get('response_frame') if isinstance(payload.get('response_frame'), Mapping) else None
            if isinstance(frame, dict):
                frame_runtime = dict(frame.get('runtime') or {}) if isinstance(frame.get('runtime'), Mapping) else {}
                frame_diagnostics = (
                    dict(frame_runtime.get('developer_diagnostics'))
                    if isinstance(frame_runtime.get('developer_diagnostics'), Mapping)
                    else {}
                )
                frame_diagnostics['response_frame_finalize_timing'] = dict(finalize_timing)
                frame_runtime['developer_diagnostics'] = frame_diagnostics
                frame['runtime'] = frame_runtime
                current_state = frame.get('current_state') if isinstance(frame.get('current_state'), Mapping) else None
                if isinstance(current_state, dict):
                    current_runtime = (
                        dict(current_state.get('runtime'))
                        if isinstance(current_state.get('runtime'), Mapping)
                        else {}
                    )
                    current_diagnostics = (
                        dict(current_runtime.get('developer_diagnostics'))
                        if isinstance(current_runtime.get('developer_diagnostics'), Mapping)
                        else {}
                    )
                    current_diagnostics['response_frame_finalize_timing'] = dict(finalize_timing)
                    current_runtime['developer_diagnostics'] = current_diagnostics
                    current_state['runtime'] = current_runtime
            return payload

        step_started_at = time.perf_counter()
        finalized_payload = _attach_response_status_semantics(dict(response_payload))
        _mark_step(
            'status_semantics',
            step_started_at,
            lifecycle_state=finalized_payload.get('lifecycle_state'),
            compatibility_status=finalized_payload.get('status'),
        )
        existing_frame = (
            copy.deepcopy(finalized_payload.get('response_frame'))
            if isinstance(finalized_payload.get('response_frame'), Mapping)
            else {}
        )
        if existing_frame:
            finalized_payload['response_frame'] = existing_frame
        step_started_at = time.perf_counter()
        frame_relation_added = False
        preserve_bounded_successor_relation = False
        if persist and existing_frame:
            response_id = str(finalized_payload.get('id') or existing_frame.get('response_id') or '').strip()
            parent_frame_id = str(existing_frame.get('frame_id') or '').strip()
            if response_id:
                explicit_relation = (
                    dict(finalized_payload.get('frame_relation'))
                    if isinstance(finalized_payload.get('frame_relation'), Mapping)
                    else {}
                )
                explicit_relation_kind = str(explicit_relation.get('kind') or '').strip()
                if explicit_relation_kind == 'graph_patch_terminal_review':
                    audit_identifiers = {
                        key: explicit_relation.get(key)
                        for key in (
                            'audit_key',
                            'patch_id',
                            'proposal_id',
                            'review_id',
                            'policy_review_id',
                        )
                    }
                    if all(
                        isinstance(value, str)
                        and bool(value)
                        and value == value.strip()
                        for value in audit_identifiers.values()
                    ):
                        explicit_relation = {
                            'kind': 'graph_patch_terminal_review',
                            'reason': 'terminal_graph_patch_enforced_policy_denied',
                            **audit_identifiers,
                            'audit_only': True,
                            'executable': False,
                            'runtime_effect': 'audit_only_no_execution',
                            'owed_work': 'none',
                            'scheduled_branch_ids': [],
                        }
                    else:
                        explicit_relation = {}
                        explicit_relation_kind = ''
                preserve_bounded_successor_relation = explicit_relation_kind in {
                    'graph_patch_reopen_successor',
                    'graph_patch_terminal_review',
                    'graph_rebase_partial_successor',
                    'graph_rebase_stage_successor',
                }
                finalized_payload['frame_relation'] = {
                    **(explicit_relation if preserve_bounded_successor_relation else {}),
                    'kind': (
                        explicit_relation_kind
                        if preserve_bounded_successor_relation
                        else 'late_fill_successor'
                        if isinstance(finalized_payload.get('late_fill'), Mapping)
                        else 'successor'
                    ),
                    'response_id': response_id,
                    'parent_response_id': response_id,
                    'parent_frame_id': parent_frame_id or None,
                    'parent_frame_sequence': existing_frame.get('frame_sequence'),
                }
                frame_relation_added = True
        _mark_step(
            'frame_relation',
            step_started_at,
            had_existing_frame=bool(existing_frame),
            relation_added=frame_relation_added,
        )
        step_started_at = time.perf_counter()
        working_frame = _build_working_frame(
            request_payload=request_payload,
            response_payload=finalized_payload,
            freeze=True,
        )
        _mark_step('build_working_frame', step_started_at)
        finalized_payload['working_frame'] = working_frame
        runtime = dict(finalized_payload.get('runtime') or {}) if isinstance(finalized_payload.get('runtime'), dict) else {}
        runtime['working_frame'] = working_frame
        finalized_payload['runtime'] = runtime
        _publish_finalize_timing(finalized_payload)
        step_started_at = time.perf_counter()
        with measure_operation('attach_response_frame', role='canonical_truth'):
            framed_payload = self.attach_frame(finalized_payload, request_payload=request_payload)
        with measure_operation('hoist_response_outputs', role='public_projection'):
            framed_payload = _hoist_response_output_surfaces(framed_payload)
        # Artifact identity is adjudicated during frame/output construction. Bind
        # lifecycle to that final truth before persisting this new frame.
        framed_payload = _attach_response_status_semantics(framed_payload)
        current_state = framed_payload['response_frame'].get('current_state')
        if isinstance(current_state, dict):
            for key in ('lifecycle_state', 'canonical_status_field', 'status_compatibility', 'status_semantics'):
                current_state[key] = copy.deepcopy(framed_payload[key])
        if preserve_bounded_successor_relation:
            # The explicit relation applies to this append only. Later frames in the
            # successor wave derive their ordinary parent relation from response_frame.
            framed_payload.pop('frame_relation', None)
        _mark_step(
            'attach_response_frame_and_hoist_outputs',
            step_started_at,
            output_count=len(framed_payload.get('outputs') or []) if isinstance(framed_payload.get('outputs'), list) else None,
            artifact_count=len(framed_payload.get('artifacts') or []) if isinstance(framed_payload.get('artifacts'), list) else None,
        )
        _publish_finalize_timing(framed_payload)
        response_frame = framed_payload.get('response_frame')
        if isinstance(response_frame, Mapping):
            step_started_at = time.perf_counter()
            framed_payload['response_frame'] = _enrich_response_frame_metadata(
                response_frame,
                parent_frame=existing_frame if isinstance(existing_frame, Mapping) else None,
            )
            if not persist and existing_frame:
                framed_payload['response_frame'] = _preserve_frozen_response_frame_identity(
                    framed_payload['response_frame'],
                    existing_frame,
                )
            _mark_step('response_frame_metadata', step_started_at)
            _publish_finalize_timing(framed_payload)
        if persist and not self.persistence_disabled():
            framed_payload = self.frame_commit.commit(
                framed_payload,
                expected_parent_frame_id=expected_parent_frame_id,
                expected_parent_frame_sequence=expected_parent_frame_sequence,
                _mark_step=_mark_step,
                _publish_finalize_timing=_publish_finalize_timing,
            )
        _publish_finalize_timing(framed_payload)
        return framed_payload

