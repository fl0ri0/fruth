"""Graph rebase evidence, lifecycle and exact partial-successor preparation.

Consumes explicit request readers and state constructors. Operator credentials,
parent compare-and-swap, worker scheduling and HTTP remain at their existing
admission/commit boundaries. Full rebase remains non-executable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from fruth_server.graph_patch_continuation import GraphPatchContinuation
from fruth_server.graph_patch_continuation import (
    _FROZEN_GRAPH_PATCH_RESPONSE_STATES,
    _compact_payload,
)
import copy
import hashlib
import json
from typing import Any, Optional
from fruth_services.enforced_policy import describe_enforced_policy_from_env
from fruth_services.graph_rebase import (
    apply_validated_graph_rebase,
    build_graph_rebase_diff,
    build_graph_rebase_execution_contract_proof,
    build_graph_rebase_lifecycle,
    build_graph_rebase_proposal,
    describe_graph_rebase_autonomy,
    describe_graph_rebase_autonomy_from_env,
    normalize_graph_rebase_autonomy,
    stable_graph_digest,
    stable_graph_rebase_prompt_digest,
    validate_graph_rebase_proposal,
)


_ACTIVE_LATE_FILL_STATUSES = {'pending', 'queued', 'running', 'scheduled', 'accepted'}


_RESPONSE_TIME_GRAPH_REBASE_CANDIDATE_KEY = 'response_time_graph_rebase_candidate'


_SMALLER_REDRAW_SCOPES = {
    'promote_reserved_slot',
    'fill_reserved_slot',
    'add_missing_branch',
    'repair_binding_dependency',
    'repair_artifact_ref_identity',
}


_RUNTIME_REBASE_ACTIONS = {
    'rebuild_from_promoted_obligations',
    'partial_subtree_rebase',
    'full_successor_rebase',
}


_RUNTIME_REBASE_OPEN_STATUSES = {
    'actionable',
    'active',
    'blocked',
    'failed',
    'pending',
    'repair_needed',
    'repair_required',
    'unmet',
}


_RUNTIME_REBASE_STRUCTURAL_OPERATIONS = {
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


_MAX_PARTIAL_GRAPH_REBASE_SUCCESSOR_DEPTH = 4


def _partial_graph_rebase_parent_depth(response_payload: dict[str, Any]) -> int:
    frame = (
        response_payload.get('response_frame')
        if isinstance(response_payload.get('response_frame'), dict)
        else {}
    )
    relation = frame.get('frame_relation') if isinstance(frame.get('frame_relation'), dict) else {}
    late_fill = (
        response_payload.get('late_fill')
        if isinstance(response_payload.get('late_fill'), dict)
        else {}
    )
    prior_execution = (
        late_fill.get('partial_rebase_execution')
        if isinstance(late_fill.get('partial_rebase_execution'), dict)
        else {}
    )
    depth = 0
    for raw_depth in (
        relation.get('partial_rebase_depth'),
        prior_execution.get('partial_rebase_depth'),
    ):
        try:
            depth = max(depth, int(raw_depth or 0))
        except (TypeError, ValueError):
            continue
    return depth


def _partial_graph_rebase_execution_keys(
    *,
    response_id: str,
    parent_frame_id: str,
    proposal_id: str,
    review_id: str,
    rebase_id: str,
    idempotency_key: str,
    candidate_graph_digest: str,
    diff_digest: str,
    scope_digest: str,
    owed_branch_ids: list[str],
    partial_rebase_depth: int,
    authorization_record_id: str,
) -> tuple[str, str]:
    identity = {
        'response_id': response_id,
        'parent_frame_id': parent_frame_id,
        'proposal_id': proposal_id,
        'review_id': review_id,
        'rebase_id': rebase_id,
        'idempotency_key': idempotency_key,
        'candidate_graph_digest': candidate_graph_digest,
        'diff_digest': diff_digest,
        'scope_digest': scope_digest,
        'owed_branch_ids': sorted(owed_branch_ids),
        'partial_rebase_depth': partial_rebase_depth,
        'authorization_record_id': authorization_record_id,
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(',', ':')).encode('utf-8')
    execution_key = f"graph-rebase-partial-exec-{hashlib.sha256(encoded).hexdigest()[:24]}"
    frame_identity = {**identity, 'execution_key': execution_key}
    frame_encoded = json.dumps(frame_identity, sort_keys=True, separators=(',', ':')).encode('utf-8')
    successor_key = f"graph-rebase-partial-successor-{hashlib.sha256(frame_encoded).hexdigest()[:24]}"
    return successor_key, execution_key


def _runtime_rebase_late_fill_status(payload: dict[str, Any]) -> str:
    runtime = payload.get('runtime') if isinstance(payload.get('runtime'), dict) else {}
    late_fill = (
        payload.get('late_fill')
        if isinstance(payload.get('late_fill'), dict)
        else runtime.get('late_fill')
        if isinstance(runtime.get('late_fill'), dict)
        else {}
    )
    status = str(late_fill.get('status') or '').strip().lower()
    if status in _ACTIVE_LATE_FILL_STATUSES:
        return status
    for key, fallback in (
        ('active_count', 'running'),
        ('active_branch_count', 'running'),
        ('pending_count', 'pending'),
        ('pending_branch_count', 'pending'),
    ):
        try:
            if int(late_fill.get(key) or 0) > 0:
                return fallback
        except (TypeError, ValueError):
            continue
    if late_fill.get('active_branches'):
        return 'running'
    if late_fill.get('pending_branches'):
        return 'pending'
    if status:
        # Explicit Late Fill truth is newer than a response lifecycle label that
        # may still say late_fill_pending while terminal callbacks are running.
        return ''
    lifecycle_state = str(payload.get('lifecycle_state') or '').strip().lower()
    if lifecycle_state.startswith('late_fill_'):
        lifecycle_status = lifecycle_state.removeprefix('late_fill_')
        if lifecycle_status in _ACTIVE_LATE_FILL_STATUSES:
            return lifecycle_status
    if payload.get('late_fill_pending') is True:
        return 'pending'
    return ''


def _runtime_rebase_closure_evidence(closure_review: dict[str, Any]) -> dict[str, Any]:
    closure_status = str(closure_review.get('status') or '').strip().lower()
    if closure_status not in {'blocked', 'pending', 'repair_needed', 'repair_required'}:
        return {}
    records: list[tuple[str, dict[str, Any]]] = [('closure', closure_review)]
    records.extend(
        ('check', dict(item))
        for item in (closure_review.get('checks') or [])
        if isinstance(item, dict)
    )
    adequacy = (
        closure_review.get('intent_graph_adequacy')
        if isinstance(closure_review.get('intent_graph_adequacy'), dict)
        else {}
    )
    records.extend(
        ('intent_graph_adequacy', dict(item))
        for item in (adequacy.get('checks') or [])
        if isinstance(item, dict)
    )
    actions: list[str] = []
    evidence_refs: list[str] = []
    for source, record in records:
        record_status = (
            str(record.get('status') or closure_status)
            .strip()
            .lower()
            .replace('-', '_')
            .replace(' ', '_')
        )
        if record_status not in _RUNTIME_REBASE_OPEN_STATUSES:
            continue
        for key in (
            'repair_action',
            'recovery_action',
            'recommended_transition',
            'decision_action',
            'semantic_review_recommended_transition',
        ):
            action = str(record.get(key) or '').strip().lower()
            if action not in _RUNTIME_REBASE_ACTIONS:
                continue
            if action not in actions:
                actions.append(action)
            identity = str(
                record.get('check_kind')
                or record.get('branch_id')
                or record.get('phase_id')
                or record.get('obligation_id')
                or source
            ).strip()
            evidence_ref = f'closure:{source}:{identity}:{action}'
            if evidence_ref not in evidence_refs:
                evidence_refs.append(evidence_ref)
    if not actions:
        return {}
    preferred_scope = (
        'full_successor_rebase'
        if 'full_successor_rebase' in actions
        else 'partial_subtree_rebase'
        if 'partial_subtree_rebase' in actions
        else ''
    )
    return _compact_payload(
        {
            'actions': actions,
            'preferred_scope': preferred_scope,
            'evidence_refs': evidence_refs,
        }
    )


def _runtime_rebase_diff_summary(diff: dict[str, Any]) -> dict[str, Any]:
    return _compact_payload(
        {
            'meaningful_change_count': int(diff.get('meaningful_change_count') or 0),
            'operation_counts': dict(diff.get('operation_counts') or {}),
            'meaningful_operations': [
                dict(item)
                for item in (diff.get('meaningful_operations') or [])[:24]
                if isinstance(item, dict)
            ],
            'added_ids': dict(diff.get('added_ids') or {}),
            'removed_ids': dict(diff.get('removed_ids') or {}),
            'semantic_change_count': len(diff.get('semantic_changes') or []),
            'added_dependency_edges': list(diff.get('added_dependency_edges') or [])[:24],
            'removed_dependency_edges': list(diff.get('removed_dependency_edges') or [])[:24],
        }
    )


def _runtime_rebase_has_structural_change(diff: dict[str, Any]) -> bool:
    for operation in diff.get('meaningful_operations') or []:
        if not isinstance(operation, dict):
            continue
        op = str(operation.get('op') or '').strip().lower()
        if op in _RUNTIME_REBASE_STRUCTURAL_OPERATIONS or op.startswith('change_'):
            return True
    operation_counts = (
        diff.get('operation_counts')
        if isinstance(diff.get('operation_counts'), dict)
        else {}
    )
    complete_graph_addition = bool(
        int(operation_counts.get('add_phase') or 0) > 0
        and (
            int(operation_counts.get('add_branch') or 0) > 0
            or int(operation_counts.get('add_obligation') or 0) > 0
        )
    )
    return complete_graph_addition or bool(
        diff.get('removed_ids') and any(diff.get('removed_ids', {}).values())
    )


def _runtime_rebase_smaller_scope(review: dict[str, Any]) -> str:
    for item in review.get('scopes_considered') or []:
        if not isinstance(item, dict) or item.get('eligible') is not True:
            continue
        scope = str(item.get('scope') or '').strip().lower()
        if scope in _SMALLER_REDRAW_SCOPES:
            return scope
    return ''


def _runtime_rebase_scope_from_diff(
    base_graph: dict[str, Any],
    candidate_graph: dict[str, Any],
    diff: dict[str, Any],
    *,
    preferred_scope: str = '',
) -> dict[str, Any]:
    base_phase_ids = {
        str(item.get('phase_id') or '').strip()
        for item in (base_graph.get('phases') or [])
        if isinstance(item, dict) and str(item.get('phase_id') or '').strip()
    }
    base_branch_ids = {
        str(item.get('branch_id') or '').strip()
        for item in (base_graph.get('downstream_branches') or [])
        if isinstance(item, dict) and str(item.get('branch_id') or '').strip()
    }
    candidate_phase_ids = {
        str(item.get('phase_id') or '').strip()
        for item in (candidate_graph.get('phases') or [])
        if isinstance(item, dict) and str(item.get('phase_id') or '').strip()
    }
    candidate_branch_ids = {
        str(item.get('branch_id') or '').strip()
        for item in (candidate_graph.get('downstream_branches') or [])
        if isinstance(item, dict) and str(item.get('branch_id') or '').strip()
    }
    affected_phase_ids: set[str] = set()
    affected_branch_ids: set[str] = set()
    root_ids: set[str] = set()

    for operation in diff.get('meaningful_operations') or []:
        if not isinstance(operation, dict):
            continue
        for key in ('phase_id', 'parent_phase_id'):
            value = str(operation.get(key) or '').strip()
            if value:
                affected_phase_ids.add(value)
                if value in base_phase_ids:
                    root_ids.add(value)
        for key in ('branch_id', 'parent_branch_id'):
            value = str(operation.get(key) or '').strip()
            if value:
                affected_branch_ids.add(value)
                if value in base_branch_ids:
                    root_ids.add(value)
        record_id = str(operation.get('record_id') or '').strip()
        if record_id in base_phase_ids or record_id in candidate_phase_ids:
            affected_phase_ids.add(record_id)
            if record_id in base_phase_ids:
                root_ids.add(record_id)
        if record_id in base_branch_ids or record_id in candidate_branch_ids:
            affected_branch_ids.add(record_id)
            if record_id in base_branch_ids:
                root_ids.add(record_id)
        target_id = str(operation.get('target_id') or '').strip()
        if target_id in base_phase_ids or target_id in candidate_phase_ids:
            affected_phase_ids.add(target_id)
            if target_id in base_phase_ids:
                root_ids.add(target_id)
        if target_id in base_branch_ids or target_id in candidate_branch_ids:
            affected_branch_ids.add(target_id)
            if target_id in base_branch_ids:
                root_ids.add(target_id)
        for key in ('source_id', 'removed_source_id'):
            source_id = str(operation.get(key) or '').strip()
            if source_id in base_phase_ids or source_id in base_branch_ids:
                root_ids.add(source_id)

    preferred = str(preferred_scope or '').strip().lower()
    if preferred == 'full_successor_rebase':
        return {'requested_rebase_class': 'full_successor_rebase'}
    all_base_ids = base_phase_ids | base_branch_ids
    can_be_partial = bool(root_ids and root_ids < all_base_ids)
    if preferred == 'partial_subtree_rebase' and not root_ids:
        return {}
    if preferred == 'partial_subtree_rebase' or can_be_partial:
        scope_phase_ids = sorted(
            affected_phase_ids | {item for item in root_ids if item in base_phase_ids}
        )
        scope_branch_ids = sorted(
            affected_branch_ids | {item for item in root_ids if item in base_branch_ids}
        )
        return _compact_payload(
            {
                'requested_rebase_class': 'partial_subtree_rebase',
                'scope_root_ids': sorted(root_ids),
                'scope_phase_ids': scope_phase_ids,
                'scope_branch_ids': scope_branch_ids,
                'preserve_outside_scope': True,
            }
        )
    return {'requested_rebase_class': 'full_successor_rebase'}

@dataclass(frozen=True)
class GraphRebaseContinuation:
    build_request_phase_graph: Callable[..., dict[str, Any]]
    build_late_fill_state: Callable[..., dict[str, Any]]
    attach_late_fill_state: Callable[..., dict[str, Any]]
    attach_redraw_scope_ladder_review: Callable[[dict[str, Any]], dict[str, Any]]
    resolve_current_root_prompt: Callable[[Any], str]
    extract_responses_prompt: Callable[[Any], str]
    extract_responses_current_turn_prompt: Callable[[Any], str]

    @staticmethod
    def _partial_graph_rebase_branch_records(
        graph: dict[str, Any],
        owed_branch_ids: list[str],
    ) -> list[dict[str, Any]]:
        owed = set(owed_branch_ids)
        records: dict[str, dict[str, Any]] = {}
        for collection in ('phases', 'downstream_branches'):
            for item in graph.get(collection) or []:
                if not isinstance(item, dict):
                    continue
                branch_id = str(item.get('branch_id') or item.get('phase_id') or '').strip()
                if branch_id not in owed:
                    continue
                records[branch_id] = {**records.get(branch_id, {}), **copy.deepcopy(item)}
        return [records[branch_id] for branch_id in owed_branch_ids if branch_id in records]

    @staticmethod
    def _payload_has_partial_graph_rebase_execution(
        response_payload: Any,
        execution_key: str,
    ) -> bool:
        if not isinstance(response_payload, dict) or not execution_key:
            return False
        late_fill = (
            response_payload.get('late_fill')
            if isinstance(response_payload.get('late_fill'), dict)
            else {}
        )
        execution = (
            late_fill.get('partial_rebase_execution')
            if isinstance(late_fill.get('partial_rebase_execution'), dict)
            else {}
        )
        if str(execution.get('execution_key') or '').strip() == execution_key:
            return True
        runtime = (
            response_payload.get('runtime')
            if isinstance(response_payload.get('runtime'), dict)
            else {}
        )
        graph = (
            runtime.get('request_phase_graph')
            if isinstance(runtime.get('request_phase_graph'), dict)
            else {}
        )
        return any(
            isinstance(item, dict)
            and str(item.get('execution_key') or '').strip() == execution_key
            for item in graph.get('successor_rebase_executions') or []
        )

    def prepare_terminal_partial_graph_rebase_successor(
        self,
        response_payload: dict[str, Any],
        *,
        proposal_id: str,
        trusted_authorization: Optional[dict[str, Any]],
        graph_rebase_autonomy: Optional[str] = None,
    ) -> dict[str, Any]:
        """Prepare one exact operator-authorized partial-rebase successor wave."""

        if not isinstance(response_payload, dict):
            return {'status': 'not_applicable', 'reason': 'response_payload_invalid'}
        environment_autonomy = describe_graph_rebase_autonomy_from_env()
        if (
            environment_autonomy.get('configured') is True
            and normalize_graph_rebase_autonomy(environment_autonomy.get('autonomy_level')) == 'off'
        ):
            return {'status': 'not_applicable', 'reason': 'graph_rebase_autonomy_off'}
        requested_autonomy = normalize_graph_rebase_autonomy(
            graph_rebase_autonomy
            if graph_rebase_autonomy is not None
            else environment_autonomy.get('autonomy_level')
        )
        if requested_autonomy != 'apply_reviewed':
            return {
                'status': 'not_applicable',
                'reason': 'graph_rebase_autonomy_not_apply_reviewed',
                'autonomy_level': requested_autonomy,
            }

        # Recompute the ladder from the exact frozen parent at the execution
        # boundary.  A persisted review is evidence, not an evergreen grant;
        # smaller repair scopes may have become authoritative meanwhile.
        reviewed_parent = self.attach_redraw_scope_ladder_review(
            copy.deepcopy(response_payload)
        )
        if isinstance(reviewed_parent, dict):
            response_payload = reviewed_parent

        blocked_reasons: list[str] = []

        def block(reason: str) -> None:
            token = str(reason or '').strip()
            if token and token not in blocked_reasons:
                blocked_reasons.append(token)

        response_id = str(
            response_payload.get('response_id')
            or response_payload.get('id')
            or ''
        ).strip()
        parent_frame = (
            response_payload.get('response_frame')
            if isinstance(response_payload.get('response_frame'), dict)
            else {}
        )
        parent_frame_id = str(parent_frame.get('frame_id') or '').strip()
        parent_frame_sequence = parent_frame.get('frame_sequence')
        if not response_id:
            block('partial_rebase_parent_response_id_missing')
        if not parent_frame_id:
            block('partial_rebase_parent_frame_missing')
        lifecycle_state = str(
            response_payload.get('lifecycle_state')
            or response_payload.get('status')
            or ''
        ).strip().lower()
        if lifecycle_state not in _FROZEN_GRAPH_PATCH_RESPONSE_STATES:
            block('partial_rebase_parent_not_frozen')
        late_fill_status = _runtime_rebase_late_fill_status(response_payload)
        if late_fill_status in _ACTIVE_LATE_FILL_STATUSES:
            block('active_late_fill_must_settle')

        authorization = (
            copy.deepcopy(trusted_authorization)
            if isinstance(trusted_authorization, dict)
            else {}
        )
        if not authorization:
            block('trusted_graph_rebase_authorization_missing')
        if authorization.get('kind') != 'fruth.graph_rebase_authorization':
            block('graph_rebase_authorization_kind_mismatch')
        if str(authorization.get('source') or '').strip() != 'runtime_operator_registry':
            block('graph_rebase_authorization_provenance_mismatch')
        authorization_record_id = str(
            authorization.get('registry_record_id')
            or authorization.get('record_id')
            or ''
        ).strip()
        if not authorization_record_id:
            block('graph_rebase_authorization_record_id_missing')
        if str(authorization.get('response_id') or '').strip() != response_id:
            block('graph_rebase_authorization_response_mismatch')
        if str(authorization.get('frame_id') or '').strip() != parent_frame_id:
            block('graph_rebase_authorization_frame_mismatch')

        runtime = (
            response_payload.get('runtime')
            if isinstance(response_payload.get('runtime'), dict)
            else {}
        )
        graph = (
            copy.deepcopy(runtime.get('request_phase_graph'))
            if isinstance(runtime.get('request_phase_graph'), dict)
            else {}
        )
        if not graph:
            block('partial_rebase_parent_graph_missing')
        current_scope = (
            graph.get('redraw_scope_ladder_review')
            if isinstance(graph.get('redraw_scope_ladder_review'), dict)
            else {}
        )
        selected_scope = str(current_scope.get('selected_scope') or '').strip().lower()
        if selected_scope in _SMALLER_REDRAW_SCOPES:
            block('smaller_redraw_scope_precedes_rebase')
        elif selected_scope != 'partial_subtree_rebase':
            block('current_partial_rebase_scope_not_selected')

        requested_proposal_id = str(proposal_id or '').strip()
        proposal = next(
            (
                copy.deepcopy(item)
                for item in graph.get('graph_rebase_proposals') or []
                if isinstance(item, dict)
                and str(item.get('proposal_id') or '').strip() == requested_proposal_id
            ),
            {},
        )
        if not proposal:
            block('partial_rebase_source_proposal_missing')
        if str(authorization.get('proposal_id') or '').strip() != requested_proposal_id:
            block('graph_rebase_authorization_proposal_mismatch')
        requested_class = str(proposal.get('requested_rebase_class') or '').strip().lower()
        if requested_class != 'partial_subtree_rebase':
            block('apply_reviewed_partial_rebase_only')
        if str(authorization.get('requested_rebase_class') or '').strip().lower() != requested_class:
            block('graph_rebase_authorization_class_mismatch')
        if str(authorization.get('base_graph_digest') or '').strip() != str(
            proposal.get('base_graph_digest') or ''
        ).strip():
            block('graph_rebase_authorization_base_digest_mismatch')
        if str(authorization.get('candidate_graph_digest') or '').strip() != str(
            proposal.get('candidate_graph_digest') or ''
        ).strip():
            block('graph_rebase_authorization_candidate_digest_mismatch')
        if blocked_reasons:
            return {'status': 'blocked', 'blocked_reasons': blocked_reasons}

        closure_review = (
            runtime.get('graph_closure_review')
            if isinstance(runtime.get('graph_closure_review'), dict)
            else {}
        )
        guarded_root_prompt = self.resolve_current_root_prompt(response_payload)
        if not guarded_root_prompt:
            return {
                'status': 'blocked',
                'blocked_reasons': [
                    'partial_rebase_current_root_prompt_truth_unavailable'
                ],
            }
        review = validate_graph_rebase_proposal(
            proposal,
            request_phase_graph=graph,
            closure_review=closure_review,
            artifact_payload=(
                response_payload.get('artifacts')
                if isinstance(response_payload.get('artifacts'), dict)
                else None
            ),
            accepted_learning_hints=(
                runtime.get('accepted_learning_hints')
                if isinstance(runtime.get('accepted_learning_hints'), dict)
                else None
            ),
            trusted_authorization=authorization,
            root_prompt=guarded_root_prompt,
        )
        if str(review.get('status') or '').strip().lower() != 'accepted':
            return {
                'status': 'blocked',
                'blocked_reasons': review.get('blocked_reasons') or [
                    'partial_rebase_validation_not_accepted'
                ],
                'review': review,
            }
        execution_proof = build_graph_rebase_execution_contract_proof(
            graph,
            proposal,
            root_prompt=guarded_root_prompt,
        )
        if execution_proof.get('status') != 'passed':
            return {
                'status': 'blocked',
                'blocked_reasons': [
                    'apply_reviewed_execution_contract_proof_required',
                    *(execution_proof.get('blocked_reasons') or []),
                ],
                'review': review,
                'execution_contract_proof': execution_proof,
            }
        owed_branch_ids = [
            str(item).strip()
            for item in (execution_proof.get('owed_branch_ids') or [])
            if str(item or '').strip()
        ]
        current_branch_ids = {
            str(item.get('branch_id') or item.get('phase_id') or '').strip()
            for item in graph.get('downstream_branches') or []
            if isinstance(item, dict)
        }
        reopened_existing = sorted(set(owed_branch_ids) & current_branch_ids)
        if reopened_existing:
            return {
                'status': 'blocked',
                'blocked_reasons': ['partial_rebase_existing_branch_reopen_not_supported'],
                'existing_branch_ids': reopened_existing,
            }

        lifecycle = build_graph_rebase_lifecycle(
            request_phase_graph=graph,
            rebase_review=review,
            autonomy_level='apply_reviewed',
            trusted_authorization=authorization,
        )
        if lifecycle.get('status') != 'staged':
            return {
                'status': 'blocked',
                'blocked_reasons': lifecycle.get('blocked_reasons') or [
                    'partial_rebase_lifecycle_not_staged'
                ],
                'review': review,
                'lifecycle': lifecycle,
            }
        application = apply_validated_graph_rebase(
            graph,
            lifecycle,
            autonomy_level='apply_reviewed',
            trusted_authorization=authorization,
            root_prompt=guarded_root_prompt,
        )
        if application.get('status') != 'applied':
            return {
                'status': 'blocked',
                'blocked_reasons': application.get('blocked_reasons') or [
                    'partial_rebase_successor_request_not_created'
                ],
                'review': review,
                'lifecycle': lifecycle,
                'application': application,
            }
        successor_request = (
            application.get('successor_request')
            if isinstance(application.get('successor_request'), dict)
            else {}
        )
        successor_graph = (
            copy.deepcopy(successor_request.get('successor_graph'))
            if isinstance(successor_request.get('successor_graph'), dict)
            else {}
        )
        if stable_graph_digest(successor_graph) != str(
            proposal.get('candidate_graph_digest') or ''
        ).strip():
            return {
                'status': 'blocked',
                'blocked_reasons': ['partial_rebase_successor_graph_digest_mismatch'],
            }
        pending_branches = self._partial_graph_rebase_branch_records(
            successor_graph,
            owed_branch_ids,
        )
        if [
            str(item.get('branch_id') or item.get('phase_id') or '').strip()
            for item in pending_branches
        ] != owed_branch_ids:
            return {
                'status': 'blocked',
                'blocked_reasons': ['partial_rebase_owed_branch_records_missing'],
            }
        for branch in pending_branches:
            branch['execution_contract'] = {
                **dict(branch.get('execution_contract') or {}),
                'execution_scope': 'partial_rebase_owed_branches_only',
                'root_scoped': False,
                'allow_root_prompt': False,
                'preserve_request_id': True,
                'forbidden_root_prompt_digest': (
                    stable_graph_rebase_prompt_digest(guarded_root_prompt)
                    or str(execution_proof.get('root_prompt_guard_digest') or '').strip()
                ),
            }

        partial_rebase_depth = _partial_graph_rebase_parent_depth(response_payload) + 1
        if partial_rebase_depth > _MAX_PARTIAL_GRAPH_REBASE_SUCCESSOR_DEPTH:
            return {
                'status': 'blocked',
                'blocked_reasons': ['partial_rebase_successor_depth_exhausted'],
            }
        successor_key, execution_key = _partial_graph_rebase_execution_keys(
            response_id=response_id,
            parent_frame_id=parent_frame_id,
            proposal_id=requested_proposal_id,
            review_id=str(review.get('review_id') or '').strip(),
            rebase_id=str(lifecycle.get('rebase_id') or '').strip(),
            idempotency_key=str(lifecycle.get('idempotency_key') or '').strip(),
            candidate_graph_digest=str(proposal.get('candidate_graph_digest') or '').strip(),
            diff_digest=str(lifecycle.get('diff_digest') or '').strip(),
            scope_digest=str(execution_proof.get('scope_digest') or '').strip(),
            owed_branch_ids=owed_branch_ids,
            partial_rebase_depth=partial_rebase_depth,
            authorization_record_id=authorization_record_id,
        )
        if self._payload_has_partial_graph_rebase_execution(response_payload, execution_key):
            return {
                'status': 'already_recorded',
                'execution_key': execution_key,
            }

        execution_record = {
            'kind': 'fruth.graph_rebase_partial_successor_execution',
            'status': 'queued',
            'successor_key': successor_key,
            'execution_key': execution_key,
            'response_id': response_id,
            'parent_frame_id': parent_frame_id,
            'parent_frame_sequence': parent_frame_sequence,
            'proposal_id': requested_proposal_id,
            'review_id': review.get('review_id'),
            'rebase_id': lifecycle.get('rebase_id'),
            'idempotency_key': lifecycle.get('idempotency_key'),
            'candidate_graph_digest': proposal.get('candidate_graph_digest'),
            'diff_digest': lifecycle.get('diff_digest'),
            'scope_digest': execution_proof.get('scope_digest'),
            'authorization_record_id': authorization_record_id,
            'partial_rebase_depth': partial_rebase_depth,
            'scheduled_branch_ids': owed_branch_ids,
            'root_prompt_replay': False,
        }
        execution_contract = {
            'execution_scope': 'partial_rebase_owed_branches_only',
            'root_scoped': False,
            'allow_root_prompt': False,
            'preserve_request_id': True,
            'forbidden_root_prompt_digest': (
                stable_graph_rebase_prompt_digest(guarded_root_prompt)
                or str(execution_proof.get('root_prompt_guard_digest') or '').strip()
            ),
        }
        prior_late_fill = (
            response_payload.get('late_fill')
            if isinstance(response_payload.get('late_fill'), dict)
            else {}
        )
        owed_set = set(owed_branch_ids)

        def without_owed(values: Any) -> list[dict[str, Any]]:
            return [
                copy.deepcopy(item)
                for item in (values or [])
                if isinstance(item, dict)
                and str(item.get('branch_id') or item.get('phase_id') or '').strip()
                not in owed_set
            ]

        pending_capabilities = list(
            dict.fromkeys(
                str(item.get('capability') or '').strip().lower()
                for item in pending_branches
                if str(item.get('capability') or '').strip()
            )
        )
        artifact_gap = {
            'code': 'graph_rebase_partial_late_fill',
            'trigger': 'graph_rebase_partial_successor',
            'pending_branch_scope': 'exact_partial_rebase_successor',
            'authoritative_pending_branches': True,
            'preserve_request_id': True,
            'pending_branches': pending_branches,
            'pending_capabilities': pending_capabilities,
            'active_branches': [],
            'completed_branches': without_owed(prior_late_fill.get('completed_branches')),
            'failed_branches': without_owed(prior_late_fill.get('failed_branches')),
            'cancelled_branches': without_owed(prior_late_fill.get('cancelled_branches')),
            'partial_rebase_execution': execution_record,
            'execution_contract': execution_contract,
        }
        successor_payload = copy.deepcopy(response_payload)
        pending_late_fill = self.build_late_fill_state(
            artifact_gap,
            status='pending',
            prior_state=prior_late_fill,
            extra={
                'pending_branch_scope': 'exact_partial_rebase_successor',
                'authoritative_pending_branches': True,
                'partial_rebase_execution': execution_record,
                'fill_results': prior_late_fill.get('fill_results') or [],
            },
        )
        successor_payload = self.attach_late_fill_state(
            successor_payload,
            pending_late_fill,
        )

        application_graph = (
            application.get('graph')
            if isinstance(application.get('graph'), dict)
            else {}
        )
        execution_graph = copy.deepcopy(successor_graph)
        for key in (
            'graph_rebase_proposals',
            'graph_rebase_reviews',
            'graph_rebase_lifecycle',
            'staged_graph_rebases',
            'applied_graph_rebases',
            'successor_rebase_requests',
        ):
            if application_graph.get(key) not in (None, '', [], {}):
                execution_graph[key] = copy.deepcopy(application_graph.get(key))
        execution_graph['successor_rebase_executions'] = [execution_record]
        successor_runtime = (
            copy.deepcopy(successor_payload.get('runtime'))
            if isinstance(successor_payload.get('runtime'), dict)
            else {}
        )
        successor_runtime['request_phase_graph'] = execution_graph
        diagnostics = (
            copy.deepcopy(successor_runtime.get('developer_diagnostics'))
            if isinstance(successor_runtime.get('developer_diagnostics'), dict)
            else {}
        )
        diagnostics['graph_rebase_partial_successor_execution'] = execution_record
        diagnostics['graph_rebase_partial_execution_contract_proof'] = execution_proof
        successor_runtime['developer_diagnostics'] = diagnostics
        successor_runtime['lifecycle_state'] = 'late_fill_pending'
        successor_payload['runtime'] = successor_runtime
        successor_payload['lifecycle_state'] = 'late_fill_pending'
        successor_payload['late_fill_pending'] = True
        successor_payload['frame_relation'] = {
            'kind': 'graph_rebase_partial_successor',
            'reason': 'operator_authorized_partial_graph_rebase',
            'response_id': response_id,
            'parent_response_id': response_id,
            'parent_frame_id': parent_frame_id,
            'parent_frame_sequence': parent_frame_sequence,
            'proposal_id': requested_proposal_id,
            'rebase_id': lifecycle.get('rebase_id'),
            'authorization_record_id': authorization_record_id,
            'successor_key': successor_key,
            'execution_key': execution_key,
            'scope_digest': execution_proof.get('scope_digest'),
            'partial_rebase_depth': partial_rebase_depth,
        }
        return {
            'status': 'queued',
            'response_payload': successor_payload,
            'artifact_gap': artifact_gap,
            'successor_rebase_request': successor_request,
            'execution': execution_record,
            'review': review,
            'lifecycle': lifecycle,
        }

    @staticmethod
    def _collect_explicit_graph_rebase_proposals(
        graph: dict[str, Any],
        closure_review: dict[str, Any],
    ) -> list[dict[str, Any]]:
        proposals: list[dict[str, Any]] = []
        for item in graph.get('graph_rebase_proposals') or []:
            if isinstance(item, dict):
                proposals.append(dict(item))
        for source in (
            closure_review,
            closure_review.get('global_semantic_closure_review')
            if isinstance(closure_review.get('global_semantic_closure_review'), dict)
            else {},
            closure_review.get('semantic_review_verdict')
            if isinstance(closure_review.get('semantic_review_verdict'), dict)
            else {},
        ):
            if not isinstance(source, dict):
                continue
            for key in ('graph_rebase_proposals', 'graph_rebase_candidates', 'runtime_graph_rebase_proposals'):
                for item in source.get(key) or []:
                    if isinstance(item, dict):
                        proposals.append(dict(item))
        return GraphPatchContinuation._dedupe_graph_repair_records(
            proposals,
            'proposal_id',
            'id',
        )

    def _attach_runtime_graph_rebase_evidence(
        self,
        response_payload: dict[str, Any],
        *,
        root_prompt: str = '',
    ) -> dict[str, Any]:
        """Attach backend-owned runtime graph-rebase proposal/review diagnostics."""

        if not isinstance(response_payload, dict):
            return response_payload
        updated = dict(response_payload)
        runtime = dict(updated.get('runtime') or {}) if isinstance(updated.get('runtime'), dict) else {}
        developer_diagnostics = (
            dict(runtime.get('developer_diagnostics') or {})
            if isinstance(runtime.get('developer_diagnostics'), dict)
            else {}
        )
        candidate_context = developer_diagnostics.pop(
            _RESPONSE_TIME_GRAPH_REBASE_CANDIDATE_KEY,
            None,
        )
        developer_diagnostics.pop('runtime_graph_rebase_candidate_review', None)
        graph = (
            dict(runtime.get('request_phase_graph') or {})
            if isinstance(runtime.get('request_phase_graph'), dict)
            else {}
        )
        if not graph:
            runtime['developer_diagnostics'] = developer_diagnostics
            updated['runtime'] = runtime
            return updated
        guarded_root_prompt = str(
            root_prompt or self.resolve_current_root_prompt(updated)
        ).strip()
        closure_review = (
            dict(runtime.get('graph_closure_review') or {})
            if isinstance(runtime.get('graph_closure_review'), dict)
            else {}
        )
        accepted_learning_hints = (
            dict(runtime.get('accepted_learning_hints') or {})
            if isinstance(runtime.get('accepted_learning_hints'), dict)
            else {}
        )
        proposals = self._collect_explicit_graph_rebase_proposals(graph, closure_review)
        candidate_review: dict[str, Any] = {}
        if isinstance(candidate_context, dict):
            candidate_graph = (
                copy.deepcopy(candidate_context.get('candidate_graph'))
                if isinstance(candidate_context.get('candidate_graph'), dict)
                else {}
            )
            diff = build_graph_rebase_diff(graph, candidate_graph)
            late_fill_status = _runtime_rebase_late_fill_status(updated)
            closure_evidence = _runtime_rebase_closure_evidence(closure_review)
            scope_review = (
                dict(graph.get('redraw_scope_ladder_review') or {})
                if isinstance(graph.get('redraw_scope_ladder_review'), dict)
                else {}
            )
            smaller_scope = _runtime_rebase_smaller_scope(scope_review)
            candidate_review = {
                'kind': 'fruth.runtime_graph_rebase_candidate_review',
                'candidate_origin': candidate_context.get('candidate_origin'),
                'base_graph_digest': diff.get('base_graph_digest'),
                'candidate_graph_digest': diff.get('candidate_graph_digest'),
                'diff_summary': _runtime_rebase_diff_summary(diff),
                'runtime_effect': 'none',
            }
            blocked_reason = ''
            if late_fill_status:
                blocked_reason = 'active_late_fill_must_settle'
                candidate_review['late_fill_status'] = late_fill_status
            elif not closure_evidence:
                blocked_reason = 'current_structural_closure_evidence_missing'
            elif int(diff.get('meaningful_change_count') or 0) < 1:
                blocked_reason = 'candidate_graph_has_no_meaningful_change'
            elif not _runtime_rebase_has_structural_change(diff):
                blocked_reason = 'candidate_change_is_additive_repair_only'
            elif smaller_scope:
                blocked_reason = 'smaller_redraw_scope_precedes_rebase'
                candidate_review['smaller_scope'] = smaller_scope

            scope_fields: dict[str, Any] = {}
            if not blocked_reason:
                scope_fields = _runtime_rebase_scope_from_diff(
                    graph,
                    candidate_graph,
                    diff,
                    preferred_scope=str(closure_evidence.get('preferred_scope') or ''),
                )
                if not scope_fields:
                    blocked_reason = 'partial_rebase_scope_could_not_be_proven'

            if blocked_reason:
                candidate_review['status'] = 'not_proposed'
                candidate_review['reason'] = blocked_reason
            else:
                requested_class = str(scope_fields.get('requested_rebase_class') or '').strip()
                evidence_refs = [
                    *[
                        str(item).strip()
                        for item in (closure_evidence.get('evidence_refs') or [])
                        if str(item).strip()
                    ],
                    f"runtime_candidate:{diff.get('candidate_graph_digest')}",
                ]
                graph['redraw_scope_evidence'] = _compact_payload(
                    {
                        'kind': 'fruth.redraw_scope_evidence',
                        'status': 'repair_required',
                        'recommended_scope': requested_class,
                        'reason': 'current Closure requests structural rebuild and a concrete backend graph candidate exists',
                        'evidence_refs': evidence_refs,
                        'scope_root_ids': scope_fields.get('scope_root_ids'),
                    }
                )
                runtime['request_phase_graph'] = graph
                runtime['developer_diagnostics'] = developer_diagnostics
                updated['runtime'] = runtime
                updated = self.attach_redraw_scope_ladder_review(updated)
                runtime = (
                    dict(updated.get('runtime') or {})
                    if isinstance(updated.get('runtime'), dict)
                    else {}
                )
                graph = (
                    dict(runtime.get('request_phase_graph') or {})
                    if isinstance(runtime.get('request_phase_graph'), dict)
                    else graph
                )
                developer_diagnostics = (
                    dict(runtime.get('developer_diagnostics') or {})
                    if isinstance(runtime.get('developer_diagnostics'), dict)
                    else developer_diagnostics
                )
                selected_review = (
                    dict(graph.get('redraw_scope_ladder_review') or {})
                    if isinstance(graph.get('redraw_scope_ladder_review'), dict)
                    else {}
                )
                selected_scope = str(selected_review.get('selected_scope') or '').strip().lower()
                if selected_scope != requested_class:
                    candidate_review['status'] = 'not_proposed'
                    candidate_review['reason'] = 'runtime_scope_review_did_not_select_rebase'
                    candidate_review['selected_scope'] = selected_scope
                else:
                    prompt_intent = (
                        dict(graph.get('prompt_intent') or {})
                        if isinstance(graph.get('prompt_intent'), dict)
                        else {}
                    )
                    proposal = build_graph_rebase_proposal(
                        request_phase_graph=graph,
                        candidate_graph=candidate_graph,
                        target_response_id=str(
                            updated.get('response_id')
                            or updated.get('id')
                            or graph.get('response_id')
                            or ''
                        ).strip(),
                        target_frame_id=str(
                            graph.get('frame_id')
                            or (updated.get('response_frame') or {}).get('frame_id')
                            if isinstance(updated.get('response_frame'), dict)
                            else graph.get('frame_id')
                            or ''
                        ).strip(),
                        source='runtime_closure_review',
                        reason='Current Closure requests structural graph rebuild after smaller scopes were exhausted.',
                        intent_anchor=prompt_intent,
                        evidence_refs=evidence_refs,
                        candidate_origin=str(
                            candidate_context.get('candidate_origin')
                            or 'response_time_request_phase_graph'
                        ).strip(),
                        requested_rebase_class=requested_class,
                        scope_root_ids=scope_fields.get('scope_root_ids') or [],
                        scope_phase_ids=scope_fields.get('scope_phase_ids') or [],
                        scope_branch_ids=scope_fields.get('scope_branch_ids') or [],
                        preserve_outside_scope=scope_fields.get('preserve_outside_scope'),
                        redraw_scope_review_ref=str(selected_review.get('review_id') or '').strip(),
                        root_prompt=guarded_root_prompt,
                    )
                    proposals.append(proposal)
                    candidate_review['status'] = 'proposed_for_runtime_validation'
                    candidate_review['requested_rebase_class'] = requested_class
                    candidate_review['proposal_id'] = proposal.get('proposal_id')
                    candidate_review['redraw_scope_review_ref'] = selected_review.get('review_id')

        proposals = GraphPatchContinuation._dedupe_graph_repair_records(
            proposals,
            'proposal_id',
            'id',
        )
        runtime_gate_reasons: list[str] = []
        current_late_fill_status = _runtime_rebase_late_fill_status(updated)
        if current_late_fill_status:
            runtime_gate_reasons.append('active_late_fill_must_settle')
        current_scope_review = (
            dict(graph.get('redraw_scope_ladder_review') or {})
            if isinstance(graph.get('redraw_scope_ladder_review'), dict)
            else {}
        )
        current_smaller_scope = _runtime_rebase_smaller_scope(current_scope_review)
        if current_smaller_scope:
            runtime_gate_reasons.append('smaller_redraw_scope_precedes_rebase')
        reviews = [
            validate_graph_rebase_proposal(
                proposal,
                request_phase_graph=graph,
                closure_review=closure_review,
                accepted_learning_hints=accepted_learning_hints,
                runtime_gate_reasons=runtime_gate_reasons,
                root_prompt=guarded_root_prompt,
            )
            for proposal in proposals
            if isinstance(proposal, dict)
        ]
        existing_reviews = [
            dict(item)
            for item in (graph.get('graph_rebase_reviews') or [])
            if isinstance(item, dict)
        ]
        current_review_proposal_ids = {
            str(item.get('proposal_id') or '').strip()
            for item in reviews
            if str(item.get('proposal_id') or '').strip()
        }
        retained_existing_reviews = [
            item
            for item in existing_reviews
            if str(item.get('proposal_id') or '').strip() not in current_review_proposal_ids
        ]
        graph['graph_rebase_proposals'] = GraphPatchContinuation._dedupe_graph_repair_records(
            proposals,
            'proposal_id',
            'id',
        )
        graph['graph_rebase_reviews'] = GraphPatchContinuation._dedupe_graph_repair_records(
            [*reviews, *retained_existing_reviews],
            'proposal_id',
            'review_id',
            'id',
        )
        runtime['request_phase_graph'] = graph

        developer_diagnostics['runtime_graph_rebase_proposals'] = proposals
        developer_diagnostics['runtime_graph_rebase_reviews'] = reviews
        if candidate_review:
            candidate_proposal_id = str(candidate_review.get('proposal_id') or '').strip()
            current_candidate_validation = next(
                (
                    item
                    for item in reviews
                    if candidate_proposal_id
                    and str(item.get('proposal_id') or '').strip() == candidate_proposal_id
                ),
                {},
            )
            validation_status = str(current_candidate_validation.get('status') or '').strip().lower()
            if validation_status == 'accepted':
                candidate_review['status'] = 'validated_by_runtime_review'
                candidate_review['validation_status'] = validation_status
            elif current_candidate_validation:
                blocked_reasons = [
                    str(item).strip()
                    for item in (current_candidate_validation.get('blocked_reasons') or [])
                    if str(item).strip()
                ]
                candidate_review['status'] = 'blocked_by_runtime_validation'
                candidate_review['validation_status'] = validation_status or 'blocked'
                candidate_review['reason'] = (
                    blocked_reasons[0]
                    if blocked_reasons
                    else 'runtime_graph_rebase_validation_did_not_accept_candidate'
                )
            developer_diagnostics['runtime_graph_rebase_candidate_review'] = candidate_review
        runtime['developer_diagnostics'] = developer_diagnostics
        updated['runtime'] = runtime
        return updated

    def review_terminal_graph_rebase_after_late_fill(
        self,
        response_payload: dict[str, Any],
        *,
        request_payload: Optional[dict[str, Any]] = None,
        route_payload: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Re-derive a shadow candidate after Late Fill settles, without replacing the parent graph."""

        if not isinstance(response_payload, dict):
            return response_payload
        updated = dict(response_payload)
        runtime = dict(updated.get('runtime') or {}) if isinstance(updated.get('runtime'), dict) else {}
        graph = (
            dict(runtime.get('request_phase_graph') or {})
            if isinstance(runtime.get('request_phase_graph'), dict)
            else {}
        )
        if not graph:
            return response_payload

        extract_responses_prompt = self.extract_responses_prompt
        extract_responses_current_turn_prompt = self.extract_responses_current_turn_prompt
        request_info = request_payload if isinstance(request_payload, dict) else {}
        route_info = copy.deepcopy(route_payload) if isinstance(route_payload, dict) else {}
        route_runtime = (
            dict(route_info.get('route_runtime') or {})
            if isinstance(route_info.get('route_runtime'), dict)
            else {}
        )
        route_runtime['request_phase_graph'] = graph
        route_info['route_runtime'] = route_runtime
        response_for_graph = dict(updated)
        output_text = str(updated.get('output_text') or '').strip()
        if output_text:
            response_for_graph['output_text'] = output_text
        candidate_graph = self.build_request_phase_graph(
            str(extract_responses_prompt(request_info) or output_text or '').strip(),
            intent_prompt=extract_responses_current_turn_prompt(request_info),
            request_payload=request_info,
            route_payload=route_info,
            response_payload=response_for_graph,
        )

        developer_diagnostics = (
            dict(runtime.get('developer_diagnostics') or {})
            if isinstance(runtime.get('developer_diagnostics'), dict)
            else {}
        )
        developer_diagnostics.pop(_RESPONSE_TIME_GRAPH_REBASE_CANDIDATE_KEY, None)
        developer_diagnostics.pop('runtime_graph_rebase_candidate_review', None)
        candidate_diff = build_graph_rebase_diff(graph, candidate_graph)
        terminal_candidate_review: dict[str, Any] = {}
        if int(candidate_diff.get('meaningful_change_count') or 0) > 0:
            developer_diagnostics[_RESPONSE_TIME_GRAPH_REBASE_CANDIDATE_KEY] = {
                'kind': 'fruth.runtime_graph_rebase_candidate',
                'status': 'rederived_from_terminal_materialization_truth',
                'candidate_origin': 'terminal_response_time_request_phase_graph',
                'base_graph_digest': candidate_diff.get('base_graph_digest'),
                'candidate_graph_digest': candidate_diff.get('candidate_graph_digest'),
                'diff_summary': _runtime_rebase_diff_summary(candidate_diff),
                'candidate_graph': copy.deepcopy(candidate_graph),
            }
        else:
            terminal_candidate_review = {
                'kind': 'fruth.runtime_graph_rebase_candidate_review',
                'status': 'not_proposed',
                'reason': 'terminal_candidate_has_no_meaningful_change',
                'base_graph_digest': candidate_diff.get('base_graph_digest'),
                'candidate_graph_digest': candidate_diff.get('candidate_graph_digest'),
                'runtime_effect': 'none',
            }
        runtime['request_phase_graph'] = graph
        runtime['developer_diagnostics'] = developer_diagnostics
        updated['runtime'] = runtime
        updated = self.attach_redraw_scope_ladder_review(updated)
        terminal_root_prompt = str(
            extract_responses_current_turn_prompt(request_info)
            or extract_responses_prompt(request_info)
            or ''
        ).strip()
        updated = self._attach_runtime_graph_rebase_evidence(
            updated,
            root_prompt=terminal_root_prompt,
        )
        updated = self._attach_graph_rebase_lifecycle(updated)
        if terminal_candidate_review:
            terminal_runtime = (
                dict(updated.get('runtime') or {})
                if isinstance(updated.get('runtime'), dict)
                else {}
            )
            terminal_diagnostics = (
                dict(terminal_runtime.get('developer_diagnostics') or {})
                if isinstance(terminal_runtime.get('developer_diagnostics'), dict)
                else {}
            )
            terminal_diagnostics['runtime_graph_rebase_candidate_review'] = (
                terminal_candidate_review
            )
            terminal_runtime['developer_diagnostics'] = terminal_diagnostics
            updated['runtime'] = terminal_runtime
        return updated

    def _attach_graph_rebase_lifecycle(
        self,
        response_payload: dict[str, Any],
        *,
        graph_rebase_autonomy: Optional[str] = None,
    ) -> dict[str, Any]:
        """Attach staged/applied graph rebase lifecycle truth according to autonomy."""

        if not isinstance(response_payload, dict):
            return response_payload
        updated = dict(response_payload)
        runtime = dict(updated.get('runtime') or {}) if isinstance(updated.get('runtime'), dict) else {}
        graph = (
            dict(runtime.get('request_phase_graph') or {})
            if isinstance(runtime.get('request_phase_graph'), dict)
            else {}
        )
        if not graph:
            return response_payload

        autonomy_description = (
            describe_graph_rebase_autonomy(
                graph_rebase_autonomy,
                source='explicit_override',
                configured=True,
            )
            if graph_rebase_autonomy is not None
            else describe_graph_rebase_autonomy_from_env()
        )
        autonomy_level = normalize_graph_rebase_autonomy(autonomy_description.get('autonomy_level'))
        developer_diagnostics = (
            dict(runtime.get('developer_diagnostics') or {})
            if isinstance(runtime.get('developer_diagnostics'), dict)
            else {}
        )
        developer_diagnostics['graph_rebase_autonomy'] = {
            **autonomy_description,
            'autonomy_level': autonomy_level,
            'normalized': autonomy_level,
        }
        developer_diagnostics['enforced_policy'] = describe_enforced_policy_from_env()
        if autonomy_level == 'off':
            developer_diagnostics['graph_rebase_lifecycle'] = graph.get('graph_rebase_lifecycle') or []
            developer_diagnostics['graph_rebase_enforced_policy_reviews'] = [
                item.get('enforced_policy_review')
                for item in graph.get('graph_rebase_lifecycle') or []
                if isinstance(item, dict) and isinstance(item.get('enforced_policy_review'), dict)
            ]
            developer_diagnostics['staged_graph_rebases'] = graph.get('staged_graph_rebases') or []
            developer_diagnostics['successor_rebase_requests'] = graph.get('successor_rebase_requests') or []
            runtime['developer_diagnostics'] = developer_diagnostics
            updated['runtime'] = runtime
            return updated

        raw_reviews = [
            dict(item)
            for item in (graph.get('graph_rebase_reviews') or [])
            if isinstance(item, dict)
        ]
        runtime_gate_reasons: list[str] = []
        current_late_fill_status = _runtime_rebase_late_fill_status(updated)
        if current_late_fill_status:
            runtime_gate_reasons.append('active_late_fill_must_settle')
        current_scope_review = (
            dict(graph.get('redraw_scope_ladder_review') or {})
            if isinstance(graph.get('redraw_scope_ladder_review'), dict)
            else {}
        )
        if _runtime_rebase_smaller_scope(current_scope_review):
            runtime_gate_reasons.append('smaller_redraw_scope_precedes_rebase')
        closure_review = (
            dict(runtime.get('graph_closure_review') or {})
            if isinstance(runtime.get('graph_closure_review'), dict)
            else {}
        )
        accepted_learning_hints = (
            dict(runtime.get('accepted_learning_hints') or {})
            if isinstance(runtime.get('accepted_learning_hints'), dict)
            else {}
        )
        reviews: list[dict[str, Any]] = []
        for raw_review in raw_reviews:
            source_proposal = (
                raw_review.get('source_proposal')
                if isinstance(raw_review.get('source_proposal'), dict)
                else {}
            )
            if source_proposal:
                proof = (
                    raw_review.get('preservation_proof')
                    if isinstance(raw_review.get('preservation_proof'), dict)
                    else {}
                )
                reviews.append(
                    validate_graph_rebase_proposal(
                        source_proposal,
                        request_phase_graph=graph,
                        closure_review=closure_review,
                        artifact_payload=(
                            proof.get('artifact_registry_summary')
                            if isinstance(proof.get('artifact_registry_summary'), dict)
                            else None
                        ),
                        accepted_learning_hints=accepted_learning_hints,
                        intent_lens_review=(
                            proof.get('intent_lens_review_summary')
                            if isinstance(proof.get('intent_lens_review_summary'), dict)
                            else None
                        ),
                        runtime_gate_reasons=runtime_gate_reasons,
                        root_prompt=self.resolve_current_root_prompt(updated),
                    )
                )
                continue
            blocked_review = dict(raw_review)
            blocked_review['status'] = 'blocked'
            blocked_reasons = [
                str(item).strip()
                for item in (blocked_review.get('blocked_reasons') or [])
                if str(item).strip()
            ]
            for reason in [
                'rebase_review_source_proposal_missing',
                *runtime_gate_reasons,
            ]:
                if reason not in blocked_reasons:
                    blocked_reasons.append(reason)
            blocked_review['blocked_reasons'] = blocked_reasons
            reviews.append(blocked_review)
        reviews = GraphPatchContinuation._dedupe_graph_repair_records(
            reviews,
            'proposal_id',
            'review_id',
            'id',
        )
        graph['graph_rebase_reviews'] = reviews
        working_graph = graph
        lifecycle_results: list[dict[str, Any]] = []
        for review in reviews:
            lifecycle = build_graph_rebase_lifecycle(
                request_phase_graph=working_graph,
                rebase_review=review,
                autonomy_level=autonomy_level,
            )
            application = apply_validated_graph_rebase(
                working_graph,
                lifecycle,
                autonomy_level=autonomy_level,
                runtime_gate_reasons=runtime_gate_reasons,
                root_prompt=self.resolve_current_root_prompt(updated),
            )
            working_graph = (
                dict(application.get('graph') or {})
                if isinstance(application.get('graph'), dict)
                else working_graph
            )
            lifecycle_results.append(application)

        runtime['request_phase_graph'] = working_graph
        developer_diagnostics['graph_rebase_lifecycle'] = working_graph.get('graph_rebase_lifecycle') or []
        developer_diagnostics['graph_rebase_lifecycle_results'] = lifecycle_results
        developer_diagnostics['graph_rebase_enforced_policy_reviews'] = [
            item.get('enforced_policy_review')
            for item in working_graph.get('graph_rebase_lifecycle') or []
            if isinstance(item, dict) and isinstance(item.get('enforced_policy_review'), dict)
        ]
        developer_diagnostics['staged_graph_rebases'] = working_graph.get('staged_graph_rebases') or []
        developer_diagnostics['successor_rebase_requests'] = working_graph.get('successor_rebase_requests') or []
        runtime['developer_diagnostics'] = developer_diagnostics
        updated['runtime'] = runtime
        return updated

