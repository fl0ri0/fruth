"""Passive response/frame truth projections for the API-first operator CLI.

These transformations inspect supplied response data only. HTTP requests,
credentials, commands, lifecycle actions and printing remain with the CLI adapter.
"""

from __future__ import annotations

from typing import Any, Optional


OPEN_RESPONSE_LIFECYCLE_STATES = {
    'accepted',
    'active',
    'in_progress',
    'late_fill_pending',
    'late_fill_running',
    'pending',
    'queued',
    'running',
    'scheduled',
    'started',
    'streaming',
}


ACTIONABLE_RESPONSE_LIFECYCLE_STATES = {
    'blocked',
    'late_fill_blocked',
    'late_fill_repair_needed',
    'rebuild_from_promoted_obligations',
    'repair_branch_contract',
    'repair_dependency_chain',
    'repair_needed',
}


TERMINAL_RESPONSE_LIFECYCLE_STATES = {
    'cancelled',
    'canceled',
    'completed',
    'failed',
    'frozen',
    'late_fill_completed',
    'late_fill_failed',
    'partial_cancelled',
    'partial_failed',
    'skipped',
    'superseded',
    'waived',
}


LEGACY_ACTIVE_LATE_FILL_STATUSES = {
    'accepted',
    'pending',
    'queued',
    'running',
    'scheduled',
    'started',
    'active',
    'in_progress',
}


KNOWN_RESPONSE_LIFECYCLE_STATES = (
    OPEN_RESPONSE_LIFECYCLE_STATES
    | ACTIONABLE_RESPONSE_LIFECYCLE_STATES
    | TERMINAL_RESPONSE_LIFECYCLE_STATES
    | LEGACY_ACTIVE_LATE_FILL_STATUSES
    | {'partial_failed'}
)


class CliError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, payload: Optional[dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


def _normalize_lifecycle_token(value: Any) -> str:
    if not isinstance(value, str):
        return ''
    normalized = value.strip().lower()
    return normalized if normalized in KNOWN_RESPONSE_LIFECYCLE_STATES else ''


def _canonical_lifecycle_from_response(payload: Any) -> tuple[str, str]:
    if not isinstance(payload, dict):
        return '', ''
    response_frame = (
        payload.get('response_frame')
        if isinstance(payload.get('response_frame'), dict)
        else {}
    )
    current_state = (
        response_frame.get('current_state')
        if isinstance(response_frame.get('current_state'), dict)
        else {}
    )
    frame_lifecycle = _normalize_lifecycle_token(
        current_state.get('lifecycle_state')
        or current_state.get('lifecycleState')
    )
    if frame_lifecycle:
        return frame_lifecycle, 'response_frame.current_state.lifecycle_state'
    lifecycle_state = _normalize_lifecycle_token(payload.get('lifecycle_state') or payload.get('lifecycleState'))
    if lifecycle_state:
        return lifecycle_state, 'lifecycle_state'
    status_semantics = payload.get('status_semantics') or payload.get('statusSemantics') or {}
    if isinstance(status_semantics, dict):
        semantic_lifecycle = _normalize_lifecycle_token(
            status_semantics.get('canonical_lifecycle_state')
            or status_semantics.get('canonicalLifecycleState')
        )
        if semantic_lifecycle:
            return semantic_lifecycle, 'status_semantics.canonical_lifecycle_state'
    return '', ''


def _legacy_late_fill_status(payload: dict[str, Any]) -> str:
    late_fill = payload.get('late_fill') or payload.get('lateFill') or {}
    if not isinstance(late_fill, dict):
        return ''
    return _normalize_lifecycle_token(late_fill.get('status'))


def _bool_from_semantics(status_semantics: dict[str, Any], snake_key: str, camel_key: str) -> Optional[bool]:
    if snake_key in status_semantics:
        value = status_semantics.get(snake_key)
        return value if isinstance(value, bool) else None
    if camel_key in status_semantics:
        value = status_semantics.get(camel_key)
        return value if isinstance(value, bool) else None
    return None


def _response_has_open_continuation(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    lifecycle_state, _source = _canonical_lifecycle_from_response(payload)
    if lifecycle_state:
        return lifecycle_state in OPEN_RESPONSE_LIFECYCLE_STATES

    status_semantics = payload.get('status_semantics') or payload.get('statusSemantics') or {}
    if isinstance(status_semantics, dict):
        semantic_open = _bool_from_semantics(status_semantics, 'has_open_continuation', 'hasOpenContinuation')
        if semantic_open is not None:
            return semantic_open
        semantic_terminal = _bool_from_semantics(status_semantics, 'is_terminal', 'isTerminal')
        if semantic_terminal:
            return False

    return _legacy_late_fill_status(payload) in LEGACY_ACTIVE_LATE_FILL_STATUSES


def _response_has_actionable_repair(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    lifecycle_state, _source = _canonical_lifecycle_from_response(payload)
    if lifecycle_state in ACTIONABLE_RESPONSE_LIFECYCLE_STATES:
        return True
    status_semantics = payload.get('status_semantics') or payload.get('statusSemantics') or {}
    if isinstance(status_semantics, dict):
        semantic_repair = _bool_from_semantics(status_semantics, 'has_actionable_repair', 'hasActionableRepair')
        if semantic_repair is not None:
            return semantic_repair
    late_fill = payload.get('late_fill') or payload.get('lateFill') or {}
    if not isinstance(late_fill, dict):
        return False
    if _legacy_late_fill_status(payload) in ACTIONABLE_RESPONSE_LIFECYCLE_STATES:
        return True
    for key in ('repair_action', 'repair_actions', 'recovery_candidates'):
        value = late_fill.get(key)
        if value not in (None, '', [], {}):
            return True
    return False


def _response_is_terminal(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    lifecycle_state, _source = _canonical_lifecycle_from_response(payload)
    if lifecycle_state:
        return lifecycle_state in TERMINAL_RESPONSE_LIFECYCLE_STATES
    status_semantics = payload.get('status_semantics') or payload.get('statusSemantics') or {}
    if isinstance(status_semantics, dict):
        semantic_terminal = _bool_from_semantics(status_semantics, 'is_terminal', 'isTerminal')
        if semantic_terminal is not None:
            return semantic_terminal
    return _normalize_lifecycle_token(payload.get('status')) in TERMINAL_RESPONSE_LIFECYCLE_STATES


def _response_frame_truth(payload: dict[str, Any]) -> dict[str, Any]:
    frame = payload.get('response_frame') if isinstance(payload.get('response_frame'), dict) else {}
    relation = frame.get('frame_relation') if isinstance(frame.get('frame_relation'), dict) else {}
    if not relation and isinstance(payload.get('frame_relation'), dict):
        relation = payload.get('frame_relation') or {}
    return {
        'frame_id': frame.get('frame_id'),
        'frame_sequence': frame.get('frame_sequence'),
        'frame_relation': relation.get('kind') or frame.get('frame_relation_kind'),
        'parent_frame_id': relation.get('parent_frame_id') or frame.get('parent_frame_id'),
        'parent_frame_sequence': relation.get('parent_frame_sequence') or frame.get('parent_frame_sequence'),
    }


def _response_identity(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ''
    frame = payload.get('response_frame') if isinstance(payload.get('response_frame'), dict) else {}
    current_state = frame.get('current_state') if isinstance(frame.get('current_state'), dict) else {}
    identities = {
        str(value).strip()
        for value in (
            payload.get('id'),
            payload.get('response_id'),
            frame.get('response_id'),
            current_state.get('id'),
        )
        if str(value or '').strip()
    }
    if len(identities) > 1:
        raise CliError(
            'Canonical response truth contains conflicting response identities.',
            status_code=409,
            payload={'response_ids': sorted(identities)},
        )
    return next(iter(identities), '')


def _complete_response_frame_identity(payload: Any) -> tuple[str, int] | None:
    if not isinstance(payload, dict):
        return None
    frame = payload.get('response_frame') if isinstance(payload.get('response_frame'), dict) else {}
    frame_id = str(frame.get('frame_id') or '').strip()
    frame_sequence = frame.get('frame_sequence')
    if (
        not frame_id
        or not isinstance(frame_sequence, int)
        or isinstance(frame_sequence, bool)
        or frame_sequence <= 0
    ):
        return None
    return frame_id, frame_sequence


def _require_response_truth_binding(
    expected_response_id: str,
    truth_payload: Any,
    *,
    minimum_frame_payload: Any = None,
) -> None:
    actual_response_id = _response_identity(truth_payload)
    if actual_response_id != expected_response_id:
        raise CliError(
            'Canonical response truth does not match the requested response id.',
            status_code=409,
            payload={
                'expected_response_id': expected_response_id,
                'actual_response_id': actual_response_id or None,
            },
        )
    minimum_identity = _complete_response_frame_identity(minimum_frame_payload)
    if minimum_identity is None:
        return
    truth_identity = _complete_response_frame_identity(truth_payload)
    if truth_identity is None:
        raise CliError(
            'Canonical response truth is missing the frozen frame identity returned by POST.',
            status_code=409,
            payload={
                'expected_frame_id': minimum_identity[0],
                'expected_minimum_frame_sequence': minimum_identity[1],
            },
        )
    if (
        truth_identity[1] < minimum_identity[1]
        or (
            truth_identity[1] == minimum_identity[1]
            and truth_identity[0] != minimum_identity[0]
        )
    ):
        raise CliError(
            'Canonical response truth regressed behind the frame returned by POST.',
            status_code=409,
            payload={
                'post_frame_id': minimum_identity[0],
                'post_frame_sequence': minimum_identity[1],
                'truth_frame_id': truth_identity[0],
                'truth_frame_sequence': truth_identity[1],
            },
        )


def _response_outputs_truth(payload: dict[str, Any]) -> dict[str, Any]:
    frame = payload.get('response_frame') if isinstance(payload.get('response_frame'), dict) else {}
    output_frame = frame.get('output') if isinstance(frame.get('output'), dict) else {}
    outputs = output_frame.get('outputs') if isinstance(output_frame.get('outputs'), list) else []
    if not outputs:
        outputs = payload.get('outputs') if isinstance(payload.get('outputs'), list) else []

    canonical_count = 0
    compatibility_count = 0
    unknown_count = 0
    sources: list[str] = []
    for item in outputs:
        if not isinstance(item, dict):
            continue
        source = str(item.get('source') or '').strip() or 'unknown'
        if source not in sources:
            sources.append(source)
        if bool(item.get('compatibility_derived')) or source == 'compatibility_derived':
            compatibility_count += 1
        elif source == 'unknown':
            unknown_count += 1
        else:
            canonical_count += 1
    return {
        'count': len(outputs),
        'canonical_count': canonical_count,
        'compatibility_derived_count': compatibility_count,
        'unknown_provenance_count': unknown_count,
        'sources': sources,
    }


def _response_work_tree_truth(payload: dict[str, Any]) -> dict[str, Any]:
    frame = payload.get('response_frame') if isinstance(payload.get('response_frame'), dict) else {}
    planning = frame.get('planning') if isinstance(frame.get('planning'), dict) else {}
    artifact_flow = planning.get('artifact_flow') if isinstance(planning.get('artifact_flow'), dict) else {}
    work_tree = artifact_flow.get('work_tree') if isinstance(artifact_flow.get('work_tree'), dict) else {}
    return {
        'work_tree_source': work_tree.get('work_tree_source') or artifact_flow.get('work_tree_source'),
        'authoritative': work_tree.get('authoritative'),
        'compatibility_derived': work_tree.get('compatibility_derived'),
    }


def _response_message_identity(payload: dict[str, Any]) -> str:
    direct = str(payload.get('message_id') or payload.get('messageId') or '').strip()
    if direct:
        return direct
    frame = payload.get('response_frame') if isinstance(payload.get('response_frame'), dict) else {}
    current_state = frame.get('current_state') if isinstance(frame.get('current_state'), dict) else {}
    for candidate in (
        payload.get('output'),
        current_state.get('output'),
    ):
        if not isinstance(candidate, list):
            continue
        for item in candidate:
            if not isinstance(item, dict):
                continue
            message_id = str(item.get('id') or '').strip()
            if message_id:
                return message_id
    return ''


def _build_response_truth_summary(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise CliError('Response truth summary requires a JSON object response payload.')
    status_semantics = payload.get('status_semantics') or payload.get('statusSemantics') or {}
    if not isinstance(status_semantics, dict):
        status_semantics = {}
    lifecycle_state, lifecycle_source = _canonical_lifecycle_from_response(payload)
    status = _normalize_lifecycle_token(payload.get('status'))
    return {
        'response_id': payload.get('id') or payload.get('response_id'),
        'message_id': _response_message_identity(payload) or None,
        'compatibility_status': status or None,
        'lifecycle_state': lifecycle_state or None,
        'canonical_lifecycle_source': lifecycle_source or 'legacy_fallback',
        'canonical_status_field': payload.get('canonical_status_field') or status_semantics.get('canonical_status_field'),
        'status_compatibility': bool(payload.get('status_compatibility') or status_semantics.get('status_compatibility')),
        'has_open_continuation': _response_has_open_continuation(payload),
        'has_actionable_repair': _response_has_actionable_repair(payload),
        'is_terminal': _response_is_terminal(payload),
        'late_fill_status': _legacy_late_fill_status(payload) or None,
        'response_frame': _response_frame_truth(payload),
        'outputs': _response_outputs_truth(payload),
        'work_tree': _response_work_tree_truth(payload),
        'durability': payload.get('durability') if isinstance(payload.get('durability'), dict) else {},
        'lookup_source': payload.get('lookup_source'),
    }


