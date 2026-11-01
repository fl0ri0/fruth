"""Canonical response lifecycle and frozen projection identity.

Pure projections consumed by finalization, lookup and stream adapters. These
functions create no continuation permission and perform no persistence.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any, Optional
from fruth_server.responses_runtime import (
    derive_response_lifecycle_state,
    late_fill_has_actionable_repair_work,
)


_OPEN_RESPONSE_LIFECYCLE_STATES = {
    'accepted',
    'active',
    'in_progress',
    'late_fill_pending',
    'late_fill_running',
    'pending',
    'queued',
    'running',
    'streaming',
}


_ACTIONABLE_RESPONSE_LIFECYCLE_STATES = {
    'blocked',
    'late_fill_repair_needed',
    'rebuild_from_promoted_obligations',
    'repair_branch_contract',
    'repair_dependency_chain',
    'repair_needed',
}


_TERMINAL_RESPONSE_LIFECYCLE_STATES = {
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
}


def _response_lifecycle_has_open_continuation(lifecycle_state: Any) -> bool:
    normalized = str(lifecycle_state or '').strip().lower()
    return normalized in _OPEN_RESPONSE_LIFECYCLE_STATES


def _response_lifecycle_has_actionable_repair(
    lifecycle_state: Any,
    response_payload: Mapping[str, Any],
) -> bool:
    normalized = str(lifecycle_state or '').strip().lower()
    if normalized in _ACTIONABLE_RESPONSE_LIFECYCLE_STATES:
        return True
    payload = response_payload if isinstance(response_payload, Mapping) else {}
    late_fill = payload.get('late_fill') if isinstance(payload.get('late_fill'), Mapping) else {}
    if late_fill:
        late_fill_status = str(late_fill.get('status') or '').strip().lower()
        pending_branches = late_fill.get('pending_branches') if isinstance(late_fill.get('pending_branches'), list) else []
        active_branches = late_fill.get('active_branches') if isinstance(late_fill.get('active_branches'), list) else []
        failed_branches = late_fill.get('failed_branches') if isinstance(late_fill.get('failed_branches'), list) else []
        recovery_candidates = (
            late_fill.get('recovery_candidates')
            if isinstance(late_fill.get('recovery_candidates'), list)
            else []
        )
        actionable_repair_loop = late_fill_has_actionable_repair_work(late_fill)
        if (
            late_fill_status in {'completed', 'skipped', 'cancelled', 'waived', 'superseded'}
            and not pending_branches
            and not active_branches
            and not failed_branches
            and not recovery_candidates
            and not actionable_repair_loop
        ):
            return False
    if not late_fill:
        return False
    if late_fill_has_actionable_repair_work(late_fill):
        return True
    if isinstance(late_fill.get('recovery_candidates'), list) and late_fill.get('recovery_candidates'):
        return True
    if isinstance(late_fill.get('repair_actions'), list) and late_fill.get('repair_actions'):
        return True
    if late_fill.get('repair_action') not in (None, '', [], {}):
        return True
    recovery_state = late_fill.get('recovery_state') if isinstance(late_fill.get('recovery_state'), Mapping) else {}
    if recovery_state and str(recovery_state.get('status') or '').strip().lower() in {'candidate', 'ready', 'blocked'}:
        return True
    failed_branches = late_fill.get('failed_branches') if isinstance(late_fill.get('failed_branches'), list) else []
    for branch in failed_branches:
        if not isinstance(branch, Mapping):
            continue
        recovery_context = (
            branch.get('recovery_context')
            if isinstance(branch.get('recovery_context'), Mapping)
            else {}
        )
        if recovery_context.get('suggested_action') not in (None, '', [], {}):
            return True
    for branch in list(pending_branches) + list(active_branches):
        if not isinstance(branch, Mapping):
            continue
        branch_status = str(branch.get('status') or '').strip().lower()
        if branch_status in _ACTIONABLE_RESPONSE_LIFECYCLE_STATES or branch_status in {
            'blocked',
            'failed',
            'partial_failed',
            'repair_needed',
        }:
            return True
        recovery_context = (
            branch.get('recovery_context')
            if isinstance(branch.get('recovery_context'), Mapping)
            else {}
        )
        if recovery_context.get('suggested_action') not in (None, '', [], {}):
            return True
    return False


def _response_lifecycle_is_terminal(lifecycle_state: Any) -> bool:
    normalized = str(lifecycle_state or '').strip().lower()
    return normalized in _TERMINAL_RESPONSE_LIFECYCLE_STATES


def _select_canonical_response_lifecycle_state(
    response_payload: Mapping[str, Any],
    *,
    compatibility_status: Optional[str] = None,
) -> str:
    """Choose lifecycle truth without preserving stale active continuation state."""

    payload = response_payload if isinstance(response_payload, Mapping) else {}
    return str(
        derive_response_lifecycle_state(payload, requested_status=compatibility_status)
        or compatibility_status
        or ''
    ).strip() or 'completed'


def _attach_response_status_semantics(response_payload: dict[str, Any]) -> dict[str, Any]:
    """Make lifecycle_state the machine-readable continuation authority."""

    payload = dict(response_payload)
    compatibility_status = str(payload.get('status') or '').strip() or None
    lifecycle_state = _select_canonical_response_lifecycle_state(
        payload,
        compatibility_status=compatibility_status,
    )
    payload['lifecycle_state'] = lifecycle_state
    has_open_continuation = _response_lifecycle_has_open_continuation(lifecycle_state)
    has_actionable_repair = _response_lifecycle_has_actionable_repair(lifecycle_state, payload)
    late_fill = payload.get('late_fill') if isinstance(payload.get('late_fill'), Mapping) else {}
    late_fill_status = str(late_fill.get('status') or '').strip().lower()
    is_terminal = bool(
        _response_lifecycle_is_terminal(lifecycle_state)
        or (
            lifecycle_state == 'repair_needed'
            and late_fill_status == 'repair_needed'
        )
    )
    status_compatibility = bool(
        compatibility_status
        and compatibility_status != lifecycle_state
        and (
            compatibility_status == 'completed'
            or has_open_continuation
            or has_actionable_repair
            or is_terminal
        )
    )
    payload['canonical_status_field'] = 'lifecycle_state'
    payload['status_compatibility'] = status_compatibility
    payload['status_semantics'] = {
        'compatibility_status': compatibility_status,
        'canonical_lifecycle_state': lifecycle_state,
        'canonical_status_field': 'lifecycle_state',
        'status_compatibility': status_compatibility,
        'has_open_continuation': has_open_continuation,
        'has_actionable_repair': has_actionable_repair,
        'is_terminal': is_terminal,
        'terminal': is_terminal,
    }
    return payload


def _preserve_frozen_response_frame_identity(
    projected_frame: Mapping[str, Any],
    frozen_frame: Mapping[str, Any],
) -> dict[str, Any]:
    """Keep a read projection attached to the exact frozen frame it represents."""

    preserved = dict(projected_frame)
    for key in ('frame_id', 'frame_sequence', 'frame_relation'):
        if key in frozen_frame:
            preserved[key] = copy.deepcopy(frozen_frame.get(key))
        else:
            preserved.pop(key, None)
    return preserved


