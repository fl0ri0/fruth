"""Bounded evidence projections for shadow-corpus observations.

Input is captured status/debug/readiness data. These summaries do not issue HTTP
requests, write manifests, authorize rebase or establish full canonical truth.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
from typing import Any, Optional


MAX_SUMMARY_RECORDS = 48


MAX_EVIDENCE_STRING_CHARS = 2_048


MAX_FINAL_TEXT_CHARS = 8_192


SMALLER_REBASE_PRECEDENCE_SCOPES = {
    'promote_reserved_slot',
    'fill_reserved_slot',
    'additive_repair',
    'add_missing_branch',
    'repair_binding_dependency',
    'repair_artifact_ref_identity',
}


STRUCTURAL_REBASE_ACTIONS = {
    'rebuild_from_promoted_obligations',
    'partial_subtree_rebase',
    'full_successor_rebase',
}


STRUCTURAL_REBASE_OPERATIONS = {
    'merge_branch',
    'merge_branches',
    'rebind_dependency',
    'remove_branch',
    'remove_dependency',
    'remove_obligation',
    'remove_phase',
    'split_branch',
    'supersede_with_replacement',
}


OPEN_REBASE_EVIDENCE_STATUSES = {
    'actionable',
    'active',
    'blocked',
    'failed',
    'pending',
    'repair_needed',
    'repair_required',
    'unmet',
}


ACTIVE_LATE_FILL_STATUSES = {
    'accepted',
    'active',
    'in_progress',
    'pending',
    'queued',
    'running',
    'scheduled',
    'started',
}


REPAIR_LATE_FILL_STATUSES = {
    'blocked',
    'failed',
    'late_fill_failed',
    'partial_failed',
    'repair_needed',
}


NON_SUCCESS_TERMINAL_LATE_FILL_STATUSES = {
    'canceled',
    'cancelled',
    'partial_cancelled',
    'superseded',
}


EVIDENCE_BULK_KEYS = {
    'accepted_patch',
    'audio_data',
    'audio_data_url',
    'base_graph',
    'candidate_graph',
    'content',
    'content_payload',
    'image_data',
    'image_data_url',
    'messages',
    'output_text',
    'prompt',
    'request',
    'request_payload',
    'response_frame',
    'result_text',
    'source_proposal',
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _safe_count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def classify_compact_status(payload: Mapping[str, Any]) -> str:
    semantics = payload.get('status_semantics')
    semantics = semantics if isinstance(semantics, Mapping) else {}
    late_fill = payload.get('late_fill')
    late_fill = late_fill if isinstance(late_fill, Mapping) else {}
    open_count = _safe_count(late_fill.get('pending_count')) + _safe_count(
        late_fill.get('active_count')
    )
    failed_count = _safe_count(late_fill.get('failed_count'))
    late_fill_status = str(late_fill.get('status') or '').strip().lower()
    if late_fill_status in ACTIVE_LATE_FILL_STATUSES:
        return 'open'
    lifecycle = str(
        payload.get('lifecycle_state')
        or semantics.get('canonical_lifecycle_state')
        or ''
    ).strip().lower()
    if lifecycle in {
        'accepted',
        'active',
        'in_progress',
        'late_fill_pending',
        'late_fill_running',
        'pending',
        'queued',
        'running',
        'streaming',
    }:
        return 'open'
    if bool(semantics.get('has_open_continuation')) or open_count > 0:
        return 'open'
    if bool(semantics.get('has_actionable_repair')):
        return 'settled_repair_needed'
    if lifecycle in {
        'blocked',
        'late_fill_repair_needed',
        'rebuild_from_promoted_obligations',
        'repair_branch_contract',
        'repair_dependency_chain',
        'repair_needed',
    }:
        return 'settled_repair_needed'
    if late_fill_status in REPAIR_LATE_FILL_STATUSES or failed_count > 0:
        return 'settled_repair_needed'
    if late_fill_status in NON_SUCCESS_TERMINAL_LATE_FILL_STATUSES:
        return 'settled_terminal'
    if bool(semantics.get('is_terminal') or semantics.get('terminal')):
        return 'settled_terminal'
    if lifecycle in {
        'cancelled',
        'canceled',
        'completed',
        'failed',
        'frozen',
        'late_fill_completed',
        'late_fill_failed',
        'partial_cancelled',
        'skipped',
        'superseded',
        'waived',
    }:
        return 'settled_terminal'
    return 'unknown_nonterminal'


def compact_status_observation(payload: Mapping[str, Any]) -> dict[str, Any]:
    semantics = payload.get('status_semantics')
    late_fill = payload.get('late_fill')
    output_counts = payload.get('output_counts')
    surface_state = payload.get('surface_state')
    return {
        key: value
        for key, value in {
            'observed_at': utc_now(),
            'state_version': payload.get('state_version'),
            'status': payload.get('status'),
            'lifecycle_state': payload.get('lifecycle_state'),
            'status_semantics': dict(semantics) if isinstance(semantics, Mapping) else {},
            'frame_id': payload.get('frame_id'),
            'frame_sequence': payload.get('frame_sequence'),
            'late_fill': dict(late_fill) if isinstance(late_fill, Mapping) else {},
            'output_counts': dict(output_counts) if isinstance(output_counts, Mapping) else {},
            'surface_state': dict(surface_state) if isinstance(surface_state, Mapping) else {},
            'error': payload.get('error'),
        }.items()
        if value not in (None, '', [], {})
    }


def _bounded_evidence(value: Any, *, depth: int = 0) -> Any:
    """Bound nested diagnostic evidence while dropping prompt/media bodies."""

    if depth >= 6:
        return {'truncated': True, 'kind': type(value).__name__}
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key in list(value)[:96]:
            key = str(raw_key)
            if key in EVIDENCE_BULK_KEYS or key.startswith('raw_'):
                continue
            item = value.get(raw_key)
            if item in (None, '', [], {}):
                continue
            result[key] = _bounded_evidence(item, depth=depth + 1)
        if len(value) > 96:
            result['_truncated_key_count'] = len(value) - 96
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        result = [_bounded_evidence(item, depth=depth + 1) for item in value[:MAX_SUMMARY_RECORDS]]
        if len(value) > MAX_SUMMARY_RECORDS:
            result.append({'_truncated_item_count': len(value) - MAX_SUMMARY_RECORDS})
        return result
    if isinstance(value, str) and len(value) > MAX_EVIDENCE_STRING_CHARS:
        return {
            'text': value[:MAX_EVIDENCE_STRING_CHARS],
            'length_chars': len(value),
            'sha256': hashlib.sha256(value.encode('utf-8')).hexdigest(),
            'truncated': True,
        }
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _bounded_final_text(payload: Mapping[str, Any]) -> dict[str, Any]:
    text = str(payload.get('output_text') or '')
    source = 'output_text'
    if not text:
        frame = payload.get('response_frame')
        frame = frame if isinstance(frame, Mapping) else {}
        output = frame.get('output') if isinstance(frame.get('output'), Mapping) else {}
        text = str(output.get('text') or '')
        source = 'response_frame.output.text'
    if not text:
        for item in payload.get('outputs') or []:
            if not isinstance(item, Mapping):
                continue
            if str(item.get('type') or '').strip().lower() not in {'text', 'message', 'chat'}:
                continue
            candidate = str(item.get('text') or item.get('content') or '')
            if candidate:
                text = candidate
                source = 'outputs.text'
                break
    if not text:
        return {}
    return {
        'source': source,
        'text': text[:MAX_FINAL_TEXT_CHARS],
        'length_chars': len(text),
        'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
        'truncated': len(text) > MAX_FINAL_TEXT_CHARS,
    }


def _debug_message_identity(
    payload: Mapping[str, Any],
    frame: Mapping[str, Any],
) -> dict[str, Any]:
    """Extract one exact assistant-message id without guessing among candidates."""

    current_state = (
        frame.get('current_state')
        if isinstance(frame.get('current_state'), Mapping)
        else {}
    )
    candidates: list[str] = []
    for raw_value in (payload.get('message_id'), current_state.get('message_id')):
        value = str(raw_value or '').strip()
        if value and value not in candidates:
            candidates.append(value)
    output = payload.get('output') if isinstance(payload.get('output'), list) else []
    for item in output:
        if not isinstance(item, Mapping):
            continue
        item_type = str(item.get('type') or '').strip().lower()
        if item_type not in {'assistant', 'assistant_message', 'message'}:
            continue
        value = str(item.get('id') or item.get('message_id') or '').strip()
        if value and value not in candidates:
            candidates.append(value)
    if len(candidates) == 1:
        return {'status': 'exact', 'message_id': candidates[0]}
    if len(candidates) > 1:
        return {'status': 'ambiguous', 'candidate_count': len(candidates)}
    return {'status': 'missing'}


def _bounded_records(
    values: Any,
    *,
    allowed_keys: Sequence[str],
    limit: int = MAX_SUMMARY_RECORDS,
) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    result: list[dict[str, Any]] = []
    for item in values[:limit]:
        if not isinstance(item, Mapping):
            continue
        result.append(
            {
                key: item.get(key)
                for key in allowed_keys
                if item.get(key) not in (None, '', [], {})
            }
        )
    return result


def _record_group_summary(values: Any) -> dict[str, Any]:
    if not isinstance(values, list):
        return {'total': 0}
    statuses: Counter[str] = Counter()
    classes: Counter[str] = Counter()
    ids: list[str] = []
    blocked_reasons: Counter[str] = Counter()
    for item in values:
        if not isinstance(item, Mapping):
            continue
        status = str(item.get('status') or '').strip().lower()
        if status:
            statuses[status] += 1
        rebase_class = str(
            item.get('requested_rebase_class') or item.get('rebase_class') or ''
        ).strip().lower()
        if rebase_class:
            classes[rebase_class] += 1
        for key in ('proposal_id', 'review_id', 'rebase_id', 'idempotency_key', 'outcome_id'):
            identity = str(item.get(key) or '').strip()
            if identity:
                if identity not in ids and len(ids) < MAX_SUMMARY_RECORDS:
                    ids.append(identity)
                break
        for reason in item.get('blocked_reasons') or []:
            token = str(reason or '').strip()
            if token:
                blocked_reasons[token] += 1
    return {
        'total': len([item for item in values if isinstance(item, Mapping)]),
        'by_status': dict(sorted(statuses.items())),
        'by_class': dict(sorted(classes.items())),
        'blocked_reasons': dict(sorted(blocked_reasons.items())),
        'record_ids': ids,
    }


def _summarize_late_fill(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    branch_keys = (
        'branch_id',
        'slot_id',
        'phase_id',
        'capability',
        'expected_capability',
        'output_type',
        'artifact_type',
        'status',
        'lifecycle',
        'repair_action',
        'recovery_action',
        'progress_stage',
        'instance_id',
        'depends_on',
        'input_refs',
        'output_contract',
        'artifact_request',
        'execution_contract',
        'local_execution_contract',
        'requires_artifact',
        'repair_action_reason',
    )
    result: dict[str, Any] = {
        key: value.get(key)
        for key in (
            'status',
            'linked_artifact_rebind_status',
            'final_materialization_contract_status',
            'partial_failure',
            'stale_active_reconciled',
            'repair_action',
            'repair_actions',
            'recovery_state',
            'repair_loop',
            'open_checks',
        )
        if value.get(key) not in (None, '', [], {})
    }
    for key in ('repair_actions', 'recovery_state', 'repair_loop', 'open_checks'):
        if key in result:
            result[key] = _bounded_evidence(result[key])
    for key in (
        'pending_branches',
        'active_branches',
        'failed_branches',
        'completed_branches',
        'cancelled_branches',
        'branch_progress',
        'recovery_candidates',
    ):
        records = value.get(key) if isinstance(value.get(key), list) else []
        result[f'{key.removesuffix("_branches")}_count'] = len(records)
        if records:
            result[key] = [
                {
                    field: _bounded_evidence(item.get(field))
                    for field in branch_keys
                    if item.get(field) not in (None, '', [], {})
                }
                for item in records[:MAX_SUMMARY_RECORDS]
                if isinstance(item, Mapping)
            ]
    fill_results = value.get('fill_results') if isinstance(value.get('fill_results'), list) else []
    result['fill_result_count'] = len(fill_results)
    result['fill_results'] = [
        {
            key: _bounded_evidence(item.get(key))
            for key in (
                'branch_id',
                'phase_id',
                'capability',
                'status',
                'path',
                'saved_text_path',
                'saved_image_path',
                'saved_audio_path',
                'artifact_ref',
                'output_obligation_ref',
                'extension',
                'mime_type',
                'file_sha256',
                'file_size_bytes',
                'content_sha256',
                'content_length_chars',
                'content_source',
                'artifact_request',
                'execution_contract',
                'local_execution_contract',
                'repair_action',
                'recovery_action',
            )
            if item.get(key) not in (None, '', [], {})
        }
        for item in fill_results[:MAX_SUMMARY_RECORDS]
        if isinstance(item, Mapping)
    ]
    return result


def _summarize_intent_adequacy(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result = {
        key: value.get(key)
        for key in (
            'status',
            'decision',
            'reason',
            'adequate',
            'graph_adequate',
            'blocked_reasons',
            'missing_obligation_count',
            'unfulfilled_obligation_count',
            'missing_dependency_count',
            'orphan_count',
        )
        if value.get(key) not in (None, '', [], {})
    }
    for key in (
        'checks',
        'expected_output_counts',
        'graph_capability_counts',
        'graph_output_counts',
        'intent_lens_review',
        'intent_obligation_kinds',
    ):
        if value.get(key) not in (None, '', [], {}):
            result[key] = _bounded_evidence(value.get(key))
    return result


def _summarize_phase_records(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    allowed = (
        'kind',
        'phase_id',
        'branch_id',
        'task_id',
        'workload_task_id',
        'capability',
        'role',
        'status',
        'lifecycle',
        'resolution',
        'reason',
        'output_type',
        'obligation_id',
        'queue_index',
        'requires_artifact',
        'source',
        'input_refs',
        'depends_on',
        'downstream_phase_ids',
        'child_task_ids',
        'output_contract',
        'review_criteria',
        'execution_contract',
        'local_execution_contract',
        'artifact_request',
        'repair_action',
        'recovery_action',
    )
    return [
        {
            key: _bounded_evidence(item.get(key))
            for key in allowed
            if item.get(key) not in (None, '', [], {})
        }
        for item in values[:MAX_SUMMARY_RECORDS]
        if isinstance(item, Mapping)
    ]


def _summarize_obligations(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    allowed = (
        'kind',
        'obligation_id',
        'branch_id',
        'phase_id',
        'task_id',
        'capability',
        'role',
        'relationship',
        'required',
        'status',
        'count',
        'output_type',
        'target_name',
        'target_extension',
        'source',
        'input_refs',
        'depends_on',
        'depends_on_obligation_ids',
        'source_phase_ids',
        'target_phase_id',
        'execution_dependency_required',
        'dependency_contract',
        'evidence',
        'promotion_policy',
        'fulfillment_policy',
        'output_contract',
        'review_criteria',
    )
    return [
        {
            key: _bounded_evidence(item.get(key))
            for key in allowed
            if item.get(key) not in (None, '', [], {})
        }
        for item in values[:MAX_SUMMARY_RECORDS]
        if isinstance(item, Mapping)
    ]


def _summarize_workload_graph(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result = {
        key: _bounded_evidence(value.get(key))
        for key in (
            'kind',
            'graph_mode',
            'root_workload_id',
            'workload_graph_version',
            'intent_anchor',
            'task_ids',
            'leaf_task_ids',
            'visibility_summary',
            'proposal_review',
        )
        if value.get(key) not in (None, '', [], {})
    }
    tasks = value.get('tasks') if isinstance(value.get('tasks'), list) else []
    result['task_count'] = len(tasks)
    result['tasks'] = _summarize_phase_records(tasks)
    return result


def _summarize_request_phase_graph(graph: Mapping[str, Any]) -> dict[str, Any]:
    phases = graph.get('phases') if isinstance(graph.get('phases'), list) else []
    downstream = (
        graph.get('downstream_branches')
        if isinstance(graph.get('downstream_branches'), list)
        else []
    )
    intent_obligations = (
        graph.get('intent_obligations')
        if isinstance(graph.get('intent_obligations'), list)
        else []
    )
    output_obligations = (
        graph.get('output_obligations')
        if isinstance(graph.get('output_obligations'), list)
        else []
    )
    return {
        **{
            key: _bounded_evidence(graph.get(key))
            for key in (
                'kind',
                'mode',
                'graph_version',
                'is_multi_phase',
                'continuation_required',
                'current_phase_id',
                'current_phase_capability',
                'current_phase_resolution',
                'downstream_phase_ids',
                'downstream_branch_ids',
                'downstream_capabilities',
                'workload_task_ids',
                'prompt_intent',
                'workload_proposal_review',
                'promotion_review',
            )
            if graph.get(key) not in (None, '', [], {})
        },
        'phase_count': len(phases),
        'phases': _summarize_phase_records(phases),
        'downstream_branch_count': len(downstream),
        'downstream_branches': _summarize_phase_records(downstream),
        'intent_obligation_count': len(intent_obligations),
        'intent_obligations': _summarize_obligations(intent_obligations),
        'output_obligation_count': len(output_obligations),
        'output_obligations': _summarize_obligations(output_obligations),
        'workload_graph': _summarize_workload_graph(graph.get('workload_graph')),
    }


def summarize_debug_payload(payload: Mapping[str, Any], *, byte_count: int = 0) -> dict[str, Any]:
    """Return bounded runtime truth without copying model/artifact bodies."""

    runtime = payload.get('runtime') if isinstance(payload.get('runtime'), Mapping) else {}
    graph = (
        runtime.get('request_phase_graph')
        if isinstance(runtime.get('request_phase_graph'), Mapping)
        else {}
    )
    diagnostics = (
        runtime.get('developer_diagnostics')
        if isinstance(runtime.get('developer_diagnostics'), Mapping)
        else {}
    )
    frame = payload.get('response_frame') if isinstance(payload.get('response_frame'), Mapping) else {}
    closure = (
        runtime.get('graph_closure_review')
        if isinstance(runtime.get('graph_closure_review'), Mapping)
        else payload.get('graph_closure_review')
        if isinstance(payload.get('graph_closure_review'), Mapping)
        else {}
    )
    scope_review = (
        graph.get('redraw_scope_ladder_review')
        if isinstance(graph.get('redraw_scope_ladder_review'), Mapping)
        else {}
    )
    output_keys = (
        'slot_id',
        'output_id',
        'type',
        'kind',
        'status',
        'lifecycle',
        'artifact_ref',
        'path',
        'source',
        'capability',
        'branch_id',
        'phase_id',
        'parent_slot_id',
        'parent_branch_id',
        'parent_phase_id',
        'follow_up_capability',
        'follow_up_branch_id',
        'follow_up_phase_id',
        'obligation_id',
    )
    artifact_keys = (
        'artifact_id',
        'artifact_ref',
        'type',
        'kind',
        'status',
        'path',
        'source',
        'capability',
        'sha256',
        'file_sha256',
        'size_bytes',
        'file_size_bytes',
        'mime',
        'mime_type',
        'extension',
        'branch_id',
        'phase_id',
        'obligation_id',
        'origin',
        'ref',
        'name',
    )
    graph_groups = {
        key: _record_group_summary(graph.get(key))
        for key in (
            'graph_rebase_proposals',
            'graph_rebase_reviews',
            'graph_rebase_lifecycle',
            'staged_graph_rebases',
            'successor_rebase_requests',
            'applied_graph_rebases',
            'graph_rebase_outcomes',
            'partial_rebase_outcomes',
            'successor_rebase_executions',
            'graph_repair_proposals',
            'graph_repair_reviews',
            'graph_patch_lifecycle',
            'successor_reopen_requests',
        )
    }
    diagnostic_groups = {
        key: _record_group_summary(diagnostics.get(key))
        for key in (
            'runtime_graph_rebase_proposals',
            'runtime_graph_rebase_reviews',
            'graph_rebase_lifecycle',
            'staged_graph_rebases',
            'successor_rebase_requests',
            'applied_graph_rebases',
            'graph_rebase_outcomes',
            'partial_rebase_outcomes',
            'successor_rebase_executions',
            'runtime_graph_repair_proposals',
            'runtime_graph_repair_proposal_reviews',
            'graph_patch_lifecycle',
            'graph_patch_successor_reopen_requests',
        )
    }
    candidate_review = diagnostics.get('runtime_graph_rebase_candidate_review')
    candidate_context = diagnostics.get('response_time_graph_rebase_candidate')
    current_state = frame.get('current_state') if isinstance(frame.get('current_state'), Mapping) else {}
    message_identity = _debug_message_identity(payload, frame)
    global_semantic = (
        closure.get('global_semantic_closure_review')
        if isinstance(closure.get('global_semantic_closure_review'), Mapping)
        else {}
    )
    closure_surface = (
        closure.get('surface_state')
        if isinstance(closure.get('surface_state'), Mapping)
        else payload.get('surface_state')
        if isinstance(payload.get('surface_state'), Mapping)
        else {}
    )
    return {
        'causal_telemetry': {
            key: value for key, value in (diagnostics.get('causal_telemetry') or {}).items()
            if key != 'events'
        } if isinstance(diagnostics.get('causal_telemetry'), Mapping) else {},
        'response_bytes': int(byte_count or 0),
        'id': payload.get('id') or payload.get('response_id'),
        'status': payload.get('status'),
        'lifecycle_state': payload.get('lifecycle_state'),
        'status_semantics': dict(payload.get('status_semantics') or {})
        if isinstance(payload.get('status_semantics'), Mapping)
        else {},
        'target': {
            key: payload.get(key)
            for key in ('instance_id', 'model', 'backend', 'capability', 'mode')
            if payload.get(key) not in (None, '', [], {})
        },
        'message_identity': message_identity,
        'message_id': message_identity.get('message_id'),
        'response_frame': {
            key: frame.get(key)
            for key in ('frame_id', 'frame_sequence', 'status', 'lifecycle_state')
            if frame.get(key) not in (None, '', [], {})
        }
        | (
            {
                'current_state': {
                    key: current_state.get(key)
                    for key in ('status', 'lifecycle_state', 'canonical_status_field')
                    if current_state.get(key) not in (None, '', [], {})
                }
            }
            if current_state
            else {}
        ),
        'final_text': _bounded_final_text(payload),
        'output_count': len(payload.get('outputs') or [])
        if isinstance(payload.get('outputs'), list)
        else 0,
        'artifact_count': len(payload.get('artifacts') or [])
        if isinstance(payload.get('artifacts'), list)
        else 0,
        'outputs': _bounded_records(payload.get('outputs'), allowed_keys=output_keys),
        'output_branches': _bounded_records(
            payload.get('output_branches'),
            allowed_keys=(
                'branch_id',
                'phase_id',
                'slot_id',
                'parent_slot_id',
                'child_slot_ids',
                'obligation_id',
                'type',
                'status',
                'lifecycle',
            ),
        ),
        'artifacts': _bounded_records(payload.get('artifacts'), allowed_keys=artifact_keys),
        'late_fill': _summarize_late_fill(payload.get('late_fill')),
        'closure': {
            key: (
                _summarize_intent_adequacy(closure.get(key))
                if key == 'intent_graph_adequacy'
                else _bounded_evidence(closure.get(key))
            )
            for key in (
                'kind',
                'status',
                'decision',
                'reason',
                'continuation_required',
                'closure_status',
                'closure_gap_code',
                'closure_gap_trigger',
                'materialization_status',
                'blocked_reasons',
                'open_obligation_count',
                'fulfilled_obligation_count',
                'obligation_count',
                'pending_branch_count',
                'semantic_review_required_count',
                'semantic_review_status',
                'late_fill_status',
                'repair_action',
                'recovery_action',
                'recommended_transition',
                'decision_action',
                'semantic_review_recommended_transition',
                'counts',
                'checks',
                'repair_needed',
                'intent_graph_adequacy',
            )
            if closure.get(key) not in (None, '', [], {})
        }
        | {
            'global_semantic_closure_review': _bounded_evidence(global_semantic),
            'surface_state': _bounded_evidence(closure_surface),
        },
        'request_phase_graph': _summarize_request_phase_graph(graph),
        'redraw_scope': {
            key: _bounded_evidence(scope_review.get(key))
            for key in (
                'review_id',
                'status',
                'selected_scope',
                'selected_scope_reason',
                'smaller_scope',
                'selected_candidate',
                'scopes_considered',
                'artifact_identity',
                'scope_floor',
                'scope_ceiling',
                'base_graph_digest',
                'intent_contract_digest',
                'blocked_reasons',
            )
            if scope_review.get(key) not in (None, '', [], {})
        },
        'graph_evidence': graph_groups,
        'graph_records': {
            key: _bounded_evidence(graph.get(key))
            for key in (
                'graph_rebase_proposals',
                'graph_rebase_reviews',
                'graph_rebase_lifecycle',
                'staged_graph_rebases',
                'successor_rebase_requests',
                'graph_rebase_outcomes',
                'partial_rebase_outcomes',
                'successor_rebase_executions',
                'graph_repair_proposals',
                'graph_repair_reviews',
                'graph_patch_lifecycle',
                'successor_reopen_requests',
            )
            if graph.get(key) not in (None, '', [], {})
        },
        'diagnostic_evidence': diagnostic_groups,
        'diagnostic_records': {
            key: _bounded_evidence(diagnostics.get(key))
            for key in (
                'runtime_graph_rebase_proposals',
                'runtime_graph_rebase_reviews',
                'graph_rebase_lifecycle',
                'staged_graph_rebases',
                'successor_rebase_requests',
                'graph_rebase_outcomes',
                'partial_rebase_outcomes',
                'successor_rebase_executions',
                'runtime_graph_repair_proposals',
                'runtime_graph_repair_proposal_reviews',
                'graph_patch_lifecycle',
                'graph_patch_successor_reopen_requests',
            )
            if diagnostics.get(key) not in (None, '', [], {})
        },
        'rebase_candidate': {
            'review': {
                key: _bounded_evidence(candidate_review.get(key))
                for key in (
                    'kind',
                    'status',
                    'reason',
                    'proposal_id',
                    'requested_rebase_class',
                    'selected_scope',
                    'smaller_scope',
                    'base_graph_digest',
                    'candidate_graph_digest',
                    'candidate_origin',
                    'runtime_effect',
                    'diff_summary',
                    'blocked_reasons',
                )
                if isinstance(candidate_review, Mapping)
                and candidate_review.get(key) not in (None, '', [], {})
            },
            'context': {
                key: _bounded_evidence(candidate_context.get(key))
                for key in (
                    'kind',
                    'status',
                    'reason',
                    'requested_rebase_class',
                    'selected_scope',
                    'base_graph_digest',
                    'candidate_graph_digest',
                    'runtime_effect',
                    'diff_summary',
                )
                if isinstance(candidate_context, Mapping)
                and candidate_context.get(key) not in (None, '', [], {})
            },
        },
        'repair_actionability': {
            key: diagnostics.get('surface_repair_actionability', {}).get(key)
            for key in (
                'status',
                'actionable',
                'actionable_count',
                'advisory_count',
                'blocked_reasons',
                'actionable_classes',
                'advisory_classes',
            )
            if isinstance(diagnostics.get('surface_repair_actionability'), Mapping)
            and diagnostics.get('surface_repair_actionability', {}).get(key)
            not in (None, '', [], {})
        },
        'autonomy': {
            key: dict(diagnostics.get(key) or {})
            for key in ('graph_patch_autonomy', 'graph_rebase_autonomy')
            if isinstance(diagnostics.get(key), Mapping)
        },
    }


def derive_rebase_opportunity_summary(
    debug_summary: Mapping[str, Any],
    *,
    opportunity_contract: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Classify inspection eligibility without creating rebase authority."""

    summary = debug_summary if isinstance(debug_summary, Mapping) else {}
    contract = (
        dict(opportunity_contract)
        if isinstance(opportunity_contract, Mapping)
        else {}
    )
    closure = summary.get('closure') if isinstance(summary.get('closure'), Mapping) else {}
    adequacy = (
        closure.get('intent_graph_adequacy')
        if isinstance(closure.get('intent_graph_adequacy'), Mapping)
        else {}
    )
    closure_status = str(closure.get('status') or '').strip().lower()
    closure_records: list[Mapping[str, Any]] = [closure]
    closure_records.extend(
        item for item in closure.get('checks') or [] if isinstance(item, Mapping)
    )
    closure_records.extend(
        item for item in adequacy.get('checks') or [] if isinstance(item, Mapping)
    )
    structural_actions: list[str] = []
    for record in closure_records:
        record_status = str(record.get('status') or closure_status).strip().lower()
        if record_status not in OPEN_REBASE_EVIDENCE_STATUSES:
            continue
        for key in (
            'repair_action',
            'recovery_action',
            'recommended_transition',
            'decision_action',
            'semantic_review_recommended_transition',
        ):
            action = str(record.get(key) or '').strip().lower()
            if action in STRUCTURAL_REBASE_ACTIONS and action not in structural_actions:
                structural_actions.append(action)

    candidate_root = (
        summary.get('rebase_candidate')
        if isinstance(summary.get('rebase_candidate'), Mapping)
        else {}
    )
    candidate = (
        candidate_root.get('review')
        if isinstance(candidate_root.get('review'), Mapping)
        else {}
    )
    diff = candidate.get('diff_summary') if isinstance(candidate.get('diff_summary'), Mapping) else {}
    meaningful_change_count = _safe_count(diff.get('meaningful_change_count'))
    operation_counts = (
        diff.get('operation_counts')
        if isinstance(diff.get('operation_counts'), Mapping)
        else {}
    )
    structural_change_count = sum(
        _safe_count(count)
        for operation, count in operation_counts.items()
        if str(operation).strip().lower() in STRUCTURAL_REBASE_OPERATIONS
        or str(operation).strip().lower().startswith('change_')
    )
    if (
        _safe_count(operation_counts.get('add_phase')) > 0
        and (
            _safe_count(operation_counts.get('add_branch')) > 0
            or _safe_count(operation_counts.get('add_obligation')) > 0
        )
    ):
        structural_change_count += _safe_count(operation_counts.get('add_phase'))
    removed_ids = diff.get('removed_ids') if isinstance(diff.get('removed_ids'), Mapping) else {}
    if any(value for value in removed_ids.values()):
        structural_change_count += 1

    redraw = summary.get('redraw_scope') if isinstance(summary.get('redraw_scope'), Mapping) else {}
    selected_scope = str(redraw.get('selected_scope') or '').strip().lower()
    smaller_scope = str(candidate.get('smaller_scope') or '').strip().lower()
    if not smaller_scope and selected_scope in SMALLER_REBASE_PRECEDENCE_SCOPES:
        smaller_scope = selected_scope

    graph_evidence = (
        summary.get('graph_evidence')
        if isinstance(summary.get('graph_evidence'), Mapping)
        else {}
    )
    diagnostic_evidence = (
        summary.get('diagnostic_evidence')
        if isinstance(summary.get('diagnostic_evidence'), Mapping)
        else {}
    )
    proposal_count = max(
        _safe_count((graph_evidence.get('graph_rebase_proposals') or {}).get('total'))
        if isinstance(graph_evidence.get('graph_rebase_proposals'), Mapping)
        else 0,
        _safe_count((diagnostic_evidence.get('runtime_graph_rebase_proposals') or {}).get('total'))
        if isinstance(diagnostic_evidence.get('runtime_graph_rebase_proposals'), Mapping)
        else 0,
    )
    late_fill = summary.get('late_fill') if isinstance(summary.get('late_fill'), Mapping) else {}
    late_fill_status = str(late_fill.get('status') or '').strip().lower()
    active_late_fill = bool(
        late_fill_status in ACTIVE_LATE_FILL_STATUSES
        or _safe_count(late_fill.get('active_count')) > 0
        or _safe_count(late_fill.get('pending_count')) > 0
    )

    blockers: list[str] = []
    disposition = 'insufficient_observation'
    false_negative_review = 'not_applicable'
    eligible_for_operator_inspection = False
    if proposal_count > 0:
        disposition = 'formal_proposal_present'
        eligible_for_operator_inspection = True
    elif not candidate:
        blockers.append('runtime_candidate_observation_missing')
    elif active_late_fill:
        disposition = 'active_late_fill'
        blockers.append('active_late_fill_must_settle')
    elif smaller_scope:
        disposition = 'smaller_scope_precedes_rebase'
        blockers.append(f'smaller_scope_selected:{smaller_scope}')
    elif not structural_actions:
        disposition = 'no_current_structural_closure_evidence'
        blockers.append('no_current_structural_closure_action')
    elif meaningful_change_count < 1:
        disposition = 'candidate_has_no_meaningful_change'
        blockers.append('candidate_graph_has_no_meaningful_change')
    elif structural_change_count < 1:
        disposition = 'candidate_change_is_not_structural'
        blockers.append('candidate_change_is_additive_or_non_structural')
    else:
        disposition = 'unproposed_structural_opportunity'
        false_negative_review = 'candidate_requires_operator_judgment'
        eligible_for_operator_inspection = True

    return {
        'kind': 'fruth.graph_rebase_opportunity_summary',
        'disposition': disposition,
        'eligible_for_operator_inspection': eligible_for_operator_inspection,
        'false_negative_review': false_negative_review,
        'authority': 'diagnostic_only_operator_judgment_required',
        'runtime_effect': 'none',
        **{
            key: contract.get(key)
            for key in ('sequence_id', 'motif', 'turn_index', 'turn_role')
            if contract.get(key) not in (None, '')
        },
        'closure_status': closure_status or None,
        'structural_closure_actions': structural_actions,
        'selected_scope': selected_scope or None,
        'candidate_status': candidate.get('status'),
        'candidate_reason': candidate.get('reason'),
        'requested_rebase_class': candidate.get('requested_rebase_class'),
        'meaningful_change_count': meaningful_change_count,
        'structural_change_count': structural_change_count,
        'formal_proposal_count': proposal_count,
        'blockers': blockers,
    }


def summarize_readiness(payload: Mapping[str, Any], *, byte_count: int = 0) -> dict[str, Any]:
    corpus = payload.get('corpus') if isinstance(payload.get('corpus'), Mapping) else {}
    candidate_root = (
        payload.get('candidate_opportunities')
        if isinstance(payload.get('candidate_opportunities'), Mapping)
        else {}
    )
    settled_candidates = (
        candidate_root.get('settled_final')
        if isinstance(candidate_root.get('settled_final'), Mapping)
        else {}
    )
    formal = payload.get('formal_evidence') if isinstance(payload.get('formal_evidence'), Mapping) else {}
    qualifying = (
        payload.get('qualifying_evidence')
        if isinstance(payload.get('qualifying_evidence'), Mapping)
        else {}
    )
    safety = payload.get('safety') if isinstance(payload.get('safety'), Mapping) else {}
    observer = payload.get('observer') if isinstance(payload.get('observer'), Mapping) else {}
    gate_summary: dict[str, Any] = {}
    for name, gate in (payload.get('gates') or {}).items():
        if not isinstance(gate, Mapping):
            continue
        gate_summary[str(name)] = {
            'ready': gate.get('ready'),
            'decision': gate.get('decision'),
            'unmet_requirements': list(gate.get('unmet_requirements') or []),
        }
    return {
        'response_bytes': int(byte_count or 0),
        'report_digest': payload.get('report_digest'),
        'corpus_digest': corpus.get('corpus_digest'),
        'settled_final_response_count': corpus.get('settled_final_response_count'),
        'nonterminal_active_late_fill_response_count': corpus.get(
            'nonterminal_active_late_fill_response_count'
        ),
        'unique_workload_family_count': corpus.get('unique_workload_family_count'),
        'workload_family_counts': dict(corpus.get('workload_family_counts') or {}),
        'settled_candidates': {
            key: settled_candidates.get(key)
            for key in (
                'total',
                'not_proposed_count',
                'with_formal_proposal_count',
                'by_status',
                'by_reason',
                'by_smaller_scope',
                'by_selected_scope',
                'by_class',
            )
            if settled_candidates.get(key) not in (None, '', [], {})
        },
        'formal_proposals': dict(formal.get('proposals') or {})
        if isinstance(formal.get('proposals'), Mapping)
        else {},
        'qualifying_evidence': {
            key: qualifying.get(key)
            for key in (
                'qualifying_proposal_count',
                'partial_proposal_count',
                'full_proposal_count',
                'passed_preservation_proof_count',
                'partial_stage_count',
                'partial_useful_adjudication_count',
                'partial_replay_confirmation_count',
                'partial_local_execution_contract_proof_count',
            )
            if qualifying.get(key) not in (None, '', [], {})
        },
        'safety': {
            key: safety.get(key)
            for key in (
                'unresolved_critical_finding_count',
                'unresolved_partial_or_unknown_finding_count',
                'zero_tolerance_satisfied',
                'unresolved_by_category',
            )
            if safety.get(key) not in (None, '', [], {})
        },
        'gates': gate_summary,
        'observer': {
            key: observer.get(key)
            for key in (
                'hydrated_response_count',
                'selected_graph_rebase_observation_count',
                'trusted_operator_record_count',
                'load_error_count',
                'selection_scan_error_count',
            )
            if observer.get(key) not in (None, '', [], {})
        },
    }


