"""Validated additive graph-patch lifecycle and terminal continuation projection.

Two explicit state-shaping operations connect accepted successor work to Late
Fill. This owner has no HTTP context, worker claim, provider or persistence port.
The caller still owns mutation locking, parent CAS, append and scheduling.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
import copy
from typing import Any, Mapping, Optional
from fruth_server.repair_gate_runtime import classify_repair_execution_policy
from fruth_services.enforced_policy import (
    build_enforced_policy_review,
    describe_enforced_policy_from_env,
    enforced_policy_allows_application,
)
from fruth_services.graph_repair import (
    apply_validated_graph_patch,
    apply_validated_graph_repair_patch,
    build_graph_patch_lifecycle,
    build_graph_repair_proposals_from_runtime_evidence,
    classify_surface_repair_actionability,
    describe_graph_repair_autonomy,
    describe_graph_repair_autonomy_from_env,
    normalize_graph_repair_autonomy,
    stable_graph_repair_graph_digest,
    validate_graph_repair_proposal,
)
from fruth_services.redraw_scope import build_redraw_scope_ladder_review


_FROZEN_GRAPH_PATCH_RESPONSE_STATES = {
    'cancelled',
    'completed',
    'failed',
    'late_fill_completed',
    'late_fill_failed',
}


_MAX_GRAPH_PATCH_SUCCESSOR_REOPEN_DEPTH = 6


def _compact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if value not in (None, '', [], {})
    }


def _graph_patch_successor_owed_scope(
    successor_graph: dict[str, Any],
    patch_application: dict[str, Any],
    *,
    fallback_branch_ids: Optional[list[Any]] = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Derive the only executable successor scope from applied patch truth."""

    target_ids = {
        str(item).strip()
        for key in (
            'applied_branch_ids',
            'applied_phase_ids',
            'applied_obligation_ids',
        )
        for item in (patch_application.get(key) or [])
        if str(item or '').strip()
    }
    target_ids.update(
        str(item.get('target_id') or '').strip()
        for item in (patch_application.get('applied_dependency_edges') or [])
        if isinstance(item, dict) and str(item.get('target_id') or '').strip()
    )
    if not target_ids:
        target_ids = {
            str(item).strip()
            for item in (fallback_branch_ids or [])
            if str(item or '').strip()
        }

    owed_branch_ids: list[str] = []
    for collection in (
        successor_graph.get('downstream_branches') or [],
        successor_graph.get('phases') or [],
    ):
        for record in collection:
            if not isinstance(record, dict):
                continue
            branch_id = str(record.get('branch_id') or record.get('phase_id') or '').strip()
            record_ids = {
                branch_id,
                str(record.get('phase_id') or '').strip(),
                str(record.get('obligation_id') or '').strip(),
            }
            record_ids.discard('')
            if branch_id and target_ids.intersection(record_ids) and branch_id not in owed_branch_ids:
                owed_branch_ids.append(branch_id)

    owed_identity_ids = {*target_ids, *owed_branch_ids}
    owed_output_obligations = []
    for record in successor_graph.get('output_obligations') or []:
        if not isinstance(record, dict):
            continue
        record_ids = {
            str(record.get('obligation_id') or '').strip(),
            str(record.get('branch_id') or '').strip(),
            str(record.get('phase_id') or '').strip(),
        }
        record_ids.discard('')
        if owed_identity_ids.intersection(record_ids):
            owed_output_obligations.append(dict(record))
    return owed_branch_ids, owed_output_obligations


def _graph_patch_successor_parent_depth(response_payload: dict[str, Any]) -> int:
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
        late_fill.get('successor_reopen_execution')
        if isinstance(late_fill.get('successor_reopen_execution'), dict)
        else {}
    )
    parent_depth = 0
    for raw_depth in (
        relation.get('successor_reopen_depth'),
        prior_execution.get('successor_reopen_depth'),
    ):
        try:
            parent_depth = max(parent_depth, int(raw_depth or 0))
        except (TypeError, ValueError):
            continue
    return parent_depth


def _graph_patch_successor_keys(
    *,
    response_id: str,
    parent_frame_id: str,
    patch_id: str,
    idempotency_key: str,
    owed_branch_ids: list[str],
    successor_depth: int,
) -> tuple[str, str]:
    owed_scope = ','.join(sorted(owed_branch_ids))
    reopen_key = '|'.join(
        [
            response_id,
            parent_frame_id,
            patch_id,
            idempotency_key,
            owed_scope,
            str(successor_depth),
        ]
    )
    execution_key = '|'.join([patch_id, idempotency_key, owed_scope])
    return reopen_key, execution_key

@dataclass(frozen=True)
class GraphPatchContinuation:
    build_late_fill_state: Callable[..., dict[str, Any]]
    attach_late_fill_state: Callable[..., dict[str, Any]]

    @staticmethod
    def _dedupe_graph_repair_records(items: list[dict[str, Any]], *keys: str) -> list[dict[str, Any]]:
        unique: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            identity = ''
            for key in keys:
                identity = str(item.get(key) or '').strip()
                if identity:
                    break
            if not identity:
                identity = repr(sorted(item.items()))
            if identity in seen:
                continue
            seen.add(identity)
            unique.append(item)
        return unique

    @staticmethod
    def _terminal_graph_patch_parent_frame(response_payload: dict[str, Any]) -> dict[str, Any]:
        response_id = str(response_payload.get('response_id') or response_payload.get('id') or '').strip()
        frame = (
            dict(response_payload.get('response_frame'))
            if isinstance(response_payload.get('response_frame'), dict)
            else {}
        )
        relation = dict(frame.get('frame_relation')) if isinstance(frame.get('frame_relation'), dict) else {}
        return _compact_payload(
            {
                'parent_response_id': response_id or None,
                'parent_frame_id': str(frame.get('frame_id') or '').strip() or None,
                'parent_frame_sequence': frame.get('frame_sequence'),
                'parent_frame_relation': relation or None,
            }
        )

    def _build_graph_patch_successor_reopen_request(
        self,
        response_payload: dict[str, Any],
        lifecycle: dict[str, Any],
        successor_application: dict[str, Any],
        *,
        autonomy_level: str,
    ) -> dict[str, Any]:
        successor_graph = (
            dict(successor_application.get('graph') or {})
            if isinstance(successor_application.get('graph'), dict)
            else {}
        )
        if not successor_graph:
            return {}
        parent = self._terminal_graph_patch_parent_frame(response_payload)
        owed_branch_ids, output_obligations = _graph_patch_successor_owed_scope(
            successor_graph,
            successor_application,
            fallback_branch_ids=lifecycle.get('scheduled_branch_ids') or [],
        )
        if not owed_branch_ids:
            return {}
        successor_reopen_depth = _graph_patch_successor_parent_depth(response_payload) + 1
        successor_reopen_key, successor_execution_key = _graph_patch_successor_keys(
            response_id=str(parent.get('parent_response_id') or '').strip(),
            parent_frame_id=str(parent.get('parent_frame_id') or '').strip(),
            patch_id=str(lifecycle.get('patch_id') or '').strip(),
            idempotency_key=str(lifecycle.get('idempotency_key') or '').strip(),
            owed_branch_ids=owed_branch_ids,
            successor_depth=successor_reopen_depth,
        )
        request = {
            'kind': 'fruth.graph_patch_successor_reopen_request',
            'status': 'candidate',
            **parent,
            'successor_reopen_key': successor_reopen_key,
            'successor_execution_key': successor_execution_key,
            'proposal_id': lifecycle.get('proposal_id'),
            'patch_id': lifecycle.get('patch_id'),
            'idempotency_key': lifecycle.get('idempotency_key'),
            'repair_class': lifecycle.get('repair_class'),
            'risk_level': lifecycle.get('risk_level'),
            'autonomy_level': autonomy_level,
            'runtime_effect': 'successor_reopen_required',
            'source_evidence_refs': lifecycle.get('source_evidence_refs') or [],
            'before_graph_digest': lifecycle.get('before_graph_digest'),
            'patch_digest': lifecycle.get('patch_digest'),
            'successor_graph_digest': (
                stable_graph_repair_graph_digest(successor_graph)
            ),
            'successor_reopen_depth': successor_reopen_depth,
            'enforced_policy_id': lifecycle.get('enforced_policy_id'),
            'enforced_class': lifecycle.get('enforced_class'),
            'policy_mode': lifecycle.get('policy_mode'),
            'allowed_by_policy': lifecycle.get('allowed_by_policy'),
            'current_evidence_refs': lifecycle.get('current_evidence_refs'),
            'forbidden_evidence_seen': lifecycle.get('forbidden_evidence_seen'),
            'blocked_reasons': [],
            'frame_relation': _compact_payload(
                {
                    'kind': 'graph_patch_reopen_successor',
                    'reason': 'graph_patch_reopen',
                    'parent_response_id': parent.get('parent_response_id'),
                    'parent_frame_id': parent.get('parent_frame_id'),
                    'parent_frame_sequence': parent.get('parent_frame_sequence'),
                    'successor_reopen_depth': successor_reopen_depth,
                }
            ),
            'owed_branch_ids': owed_branch_ids,
            'owed_output_obligations': output_obligations,
            'successor_request_phase_graph': successor_graph,
            'patch_application': _compact_payload(
                {
                    'kind': successor_application.get('kind'),
                    'status': successor_application.get('status'),
                    'proposal_id': successor_application.get('proposal_id'),
                    'patch_id': successor_application.get('patch_id'),
                    'idempotency_key': successor_application.get('idempotency_key'),
                    'original_graph_digest': successor_application.get('original_graph_digest'),
                    'patched_graph_digest': successor_application.get('patched_graph_digest'),
                    'applied_branch_ids': successor_application.get('applied_branch_ids'),
                    'applied_phase_ids': successor_application.get('applied_phase_ids'),
                    'applied_obligation_ids': successor_application.get('applied_obligation_ids'),
                    'applied_dependency_edges': successor_application.get('applied_dependency_edges'),
                }
            ),
            'execution_contract': {
                'execution_scope': 'successor_owed_branches_only',
                'root_scoped': False,
                'allow_root_prompt': False,
                'preserve_request_id': True,
            },
        }
        return _compact_payload(request)

    def _attach_runtime_graph_repair_evidence(
        self,
        response_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Attach backend-owned runtime graph-repair proposal/review diagnostics."""

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
        closure_review = (
            dict(runtime.get('graph_closure_review') or {})
            if isinstance(runtime.get('graph_closure_review'), dict)
            else {}
        )
        late_fill = (
            dict(updated.get('late_fill') or {})
            if isinstance(updated.get('late_fill'), dict)
            else dict(runtime.get('late_fill') or {})
            if isinstance(runtime.get('late_fill'), dict)
            else {}
        )
        accepted_learning_hints = (
            dict(runtime.get('accepted_learning_hints') or {})
            if isinstance(runtime.get('accepted_learning_hints'), dict)
            else {}
        )
        surface_state = (
            closure_review.get('surface_state')
            if isinstance(closure_review.get('surface_state'), dict)
            else late_fill.get('surface_state')
            if isinstance(late_fill.get('surface_state'), dict)
            else {}
        )
        surface_actionability = (
            classify_surface_repair_actionability(
                surface_state,
                closure_review=closure_review,
                late_fill=late_fill,
                monitor_report={},
            )
            if isinstance(surface_state, dict) and surface_state
            else {}
        )
        proposals = build_graph_repair_proposals_from_runtime_evidence(
            response_frame=updated,
            request_phase_graph=graph,
            closure_review=closure_review,
            late_fill=late_fill,
            monitor_report={
                'response_id': updated.get('response_id') or updated.get('id'),
                'lifecycle_state': updated.get('lifecycle_state'),
                'status': updated.get('status'),
                'final_materialization_contract_status': late_fill.get('final_materialization_contract_status'),
                'materialization_contract_unmet': late_fill.get('materialization_contract_unmet'),
                'branch_counts': {
                    'pending': len(late_fill.get('pending_branches') or []),
                    'active': len(late_fill.get('active_branches') or []),
                    'failed': len(late_fill.get('failed_branches') or []),
                    'completed': len(late_fill.get('completed_branches') or []),
                },
            },
            accepted_learning_hints=accepted_learning_hints,
        )
        reviews = [
            validate_graph_repair_proposal(
                proposal,
                request_phase_graph=graph,
                closure_review=closure_review,
                promotion_review={},
                accepted_learning_hints=accepted_learning_hints,
            )
            for proposal in proposals
            if isinstance(proposal, dict)
        ]

        existing_proposals = [
            dict(item)
            for item in (graph.get('graph_repair_proposals') or [])
            if isinstance(item, dict)
        ]
        existing_reviews = [
            dict(item)
            for item in (graph.get('graph_repair_reviews') or [])
            if isinstance(item, dict)
        ]
        graph['graph_repair_proposals'] = self._dedupe_graph_repair_records(
            [*existing_proposals, *proposals],
            'proposal_id',
            'id',
        )
        graph['graph_repair_reviews'] = self._dedupe_graph_repair_records(
            [*existing_reviews, *reviews],
            'review_id',
            'proposal_id',
            'id',
        )
        runtime['request_phase_graph'] = graph

        developer_diagnostics = (
            dict(runtime.get('developer_diagnostics') or {})
            if isinstance(runtime.get('developer_diagnostics'), dict)
            else {}
        )
        developer_diagnostics['surface_repair_actionability'] = surface_actionability
        developer_diagnostics['runtime_graph_repair_proposals'] = proposals
        developer_diagnostics['runtime_graph_repair_proposal_reviews'] = reviews
        runtime['developer_diagnostics'] = developer_diagnostics
        updated['runtime'] = runtime
        return updated

    def _attach_redraw_scope_ladder_review(
        self,
        response_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Attach backend-owned intent-aligned redraw scope review diagnostics."""

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
        closure_review = (
            dict(runtime.get('graph_closure_review') or {})
            if isinstance(runtime.get('graph_closure_review'), dict)
            else {}
        )
        late_fill = (
            dict(updated.get('late_fill') or {})
            if isinstance(updated.get('late_fill'), dict)
            else dict(runtime.get('late_fill') or {})
            if isinstance(runtime.get('late_fill'), dict)
            else {}
        )
        surface_state = (
            closure_review.get('surface_state')
            if isinstance(closure_review.get('surface_state'), dict)
            else late_fill.get('surface_state')
            if isinstance(late_fill.get('surface_state'), dict)
            else {}
        )
        accepted_learning_hints = (
            runtime.get('accepted_learning_hints')
            if isinstance(runtime.get('accepted_learning_hints'), list)
            else runtime.get('accepted_learning_hints', {}).get('hints')
            if isinstance(runtime.get('accepted_learning_hints'), dict)
            else []
        )
        review = build_redraw_scope_ladder_review(
            response_payload=updated,
            request_phase_graph=graph,
            closure_review=closure_review,
            surface_state=surface_state,
            accepted_learning_hints=accepted_learning_hints,
        )
        graph['redraw_scope_ladder_review'] = review
        runtime['request_phase_graph'] = graph

        developer_diagnostics = (
            dict(runtime.get('developer_diagnostics') or {})
            if isinstance(runtime.get('developer_diagnostics'), dict)
            else {}
        )
        developer_diagnostics['redraw_scope_ladder_review'] = review
        runtime['developer_diagnostics'] = developer_diagnostics
        updated['runtime'] = runtime
        return updated

    def _attach_graph_patch_lifecycle(
        self,
        response_payload: dict[str, Any],
        *,
        graph_repair_autonomy: Optional[str] = None,
    ) -> dict[str, Any]:
        """Attach staged/applied graph patch lifecycle truth according to autonomy."""

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
            describe_graph_repair_autonomy(graph_repair_autonomy)
            if graph_repair_autonomy is not None
            else describe_graph_repair_autonomy_from_env()
        )
        autonomy_level = normalize_graph_repair_autonomy(autonomy_description.get('autonomy_level'))
        developer_diagnostics = (
            dict(runtime.get('developer_diagnostics') or {})
            if isinstance(runtime.get('developer_diagnostics'), dict)
            else {}
        )
        autonomy_source = (
            'explicit_override'
            if graph_repair_autonomy is not None
            else str(autonomy_description.get('source') or 'environment').strip()
        )
        explicit_lifecycle_state = str(
            updated.get('lifecycle_state')
            or runtime.get('lifecycle_state')
            or ''
        ).strip().lower().replace('-', '_')
        response_frame = (
            updated.get('response_frame')
            if isinstance(updated.get('response_frame'), dict)
            else {}
        )
        identified_frame = bool(
            str(response_frame.get('frame_id') or '').strip()
            or response_frame.get('frame_sequence') not in (None, '')
        )
        compatibility_status = str(
            updated.get('status')
            or runtime.get('status')
            or ''
        ).strip().lower().replace('-', '_')
        response_state = (
            explicit_lifecycle_state
            or (compatibility_status if identified_frame else 'pre_freeze')
        )
        terminal_apply_blocked = (
            autonomy_level.startswith('apply_')
            and (
                identified_frame
                or response_state in _FROZEN_GRAPH_PATCH_RESPONSE_STATES
            )
        )
        developer_diagnostics['graph_patch_autonomy'] = {
            **autonomy_description,
            'autonomy_level': autonomy_level,
            'normalized': autonomy_level,
            'source': autonomy_source,
            'response_state': response_state,
            'response_state_source': (
                'lifecycle_state'
                if explicit_lifecycle_state
                else 'identified_response_frame'
                if identified_frame
                else 'pre_freeze_runtime'
            ),
            'terminal_apply_blocked': terminal_apply_blocked,
        }
        developer_diagnostics['enforced_policy'] = describe_enforced_policy_from_env()
        if autonomy_level == 'off':
            developer_diagnostics['graph_patch_lifecycle'] = graph.get('graph_patch_lifecycle') or []
            developer_diagnostics['graph_patch_enforced_policy_reviews'] = [
                item.get('enforced_policy_review')
                for item in graph.get('graph_patch_lifecycle') or []
                if isinstance(item, dict) and isinstance(item.get('enforced_policy_review'), dict)
            ]
            developer_diagnostics['staged_graph_patches'] = graph.get('staged_graph_patches') or []
            developer_diagnostics['applied_graph_patches'] = graph.get('applied_graph_patches') or []
            runtime['developer_diagnostics'] = developer_diagnostics
            updated['runtime'] = runtime
            return updated

        reviews = [
            dict(item)
            for item in (graph.get('graph_repair_reviews') or [])
            if isinstance(item, dict)
        ]
        working_graph = graph
        lifecycle_results: list[dict[str, Any]] = []
        successor_reopen_requests: list[dict[str, Any]] = []
        for review in reviews:
            lifecycle = build_graph_patch_lifecycle(
                request_phase_graph=working_graph,
                proposal_review=review,
                autonomy_level=autonomy_level,
            )
            successor_reopen_request = None
            if terminal_apply_blocked:
                if (
                    autonomy_level in {'apply_safe', 'apply_enforced'}
                    and lifecycle.get('risk_level') == 'safe_additive'
                    and lifecycle.get('status') not in {'blocked', 'rejected'}
                ):
                    successor_application = apply_validated_graph_patch(
                        working_graph,
                        lifecycle,
                        autonomy_level=autonomy_level,
                    )
                    if (
                        successor_application.get('status') == 'applied'
                        and isinstance(successor_application.get('graph'), dict)
                    ):
                        successor_reopen_request = self._build_graph_patch_successor_reopen_request(
                            updated,
                            lifecycle,
                            successor_application,
                            autonomy_level=autonomy_level,
                        )
                blocked_reasons = [
                    str(item)
                    for item in (lifecycle.get('blocked_reasons') or [])
                    if str(item or '').strip()
                ]
                if 'terminal_frame_requires_successor_reopen' not in blocked_reasons:
                    blocked_reasons.append('terminal_frame_requires_successor_reopen')
                lifecycle = {
                    **lifecycle,
                    'status': 'blocked',
                    'blocked_reasons': blocked_reasons,
                    'outcome': {
                        'status': 'blocked',
                        'runtime_effect': 'terminal_frame_not_mutated',
                    },
                }
            application = apply_validated_graph_patch(
                working_graph,
                lifecycle,
                autonomy_level=autonomy_level,
            )
            working_graph = (
                dict(application.get('graph') or {})
                if isinstance(application.get('graph'), dict)
                else working_graph
            )
            if successor_reopen_request:
                successor_reopen_requests.append(successor_reopen_request)
                working_graph['successor_reopen_requests'] = self._dedupe_graph_repair_records(
                    [
                        *[
                            dict(item)
                            for item in (working_graph.get('successor_reopen_requests') or [])
                            if isinstance(item, dict)
                        ],
                        successor_reopen_request,
                    ],
                    'successor_reopen_key',
                    'patch_id',
                    'proposal_id',
                    'idempotency_key',
                )
                application['graph'] = working_graph
            lifecycle_results.append(application)

        runtime['request_phase_graph'] = working_graph
        developer_diagnostics['graph_patch_lifecycle'] = working_graph.get('graph_patch_lifecycle') or []
        developer_diagnostics['graph_patch_lifecycle_results'] = lifecycle_results
        developer_diagnostics['graph_patch_enforced_policy_reviews'] = [
            item.get('enforced_policy_review')
            for item in working_graph.get('graph_patch_lifecycle') or []
            if isinstance(item, dict) and isinstance(item.get('enforced_policy_review'), dict)
        ]
        developer_diagnostics['graph_patch_successor_reopen_requests'] = (
            working_graph.get('successor_reopen_requests') or successor_reopen_requests
        )
        developer_diagnostics['staged_graph_patches'] = working_graph.get('staged_graph_patches') or []
        developer_diagnostics['applied_graph_patches'] = working_graph.get('applied_graph_patches') or []
        runtime['developer_diagnostics'] = developer_diagnostics
        updated['runtime'] = runtime
        return updated

    def _reconcile_applied_graph_patch_late_fill_gap(
        self,
        response_payload: dict[str, Any],
        closure_gap: Optional[dict[str, Any]],
    ) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
        """Expose branches added by this lifecycle pass as same-turn Late Fill work."""

        if not isinstance(response_payload, dict):
            return response_payload, closure_gap
        updated = dict(response_payload)
        runtime = dict(updated.get('runtime') or {}) if isinstance(updated.get('runtime'), dict) else {}
        graph = (
            dict(runtime.get('request_phase_graph') or {})
            if isinstance(runtime.get('request_phase_graph'), dict)
            else {}
        )
        developer_diagnostics = (
            dict(runtime.get('developer_diagnostics') or {})
            if isinstance(runtime.get('developer_diagnostics'), dict)
            else {}
        )
        lifecycle_results = [
            dict(item)
            for item in (developer_diagnostics.get('graph_patch_lifecycle_results') or [])
            if isinstance(item, dict)
            and str(item.get('status') or '').strip().lower() == 'applied'
        ]
        if not graph or not lifecycle_results:
            return updated, closure_gap

        applied_branch_ids: set[str] = set()
        applied_phase_ids: set[str] = set()
        applied_obligation_ids: set[str] = set()
        dependency_target_ids: set[str] = set()
        patch_ids: list[str] = []

        def _remember_tokens(target: set[str], values: Any) -> None:
            for value in values if isinstance(values, list) else []:
                token = str(value or '').strip()
                if token:
                    target.add(token)

        for result in lifecycle_results:
            patch_id = str(result.get('patch_id') or '').strip()
            if patch_id and patch_id not in patch_ids:
                patch_ids.append(patch_id)
            _remember_tokens(applied_branch_ids, result.get('applied_branch_ids'))
            _remember_tokens(applied_phase_ids, result.get('applied_phase_ids'))
            _remember_tokens(applied_obligation_ids, result.get('applied_obligation_ids'))
            for edge in result.get('applied_dependency_edges') or []:
                if not isinstance(edge, dict):
                    continue
                target_id = str(edge.get('target_id') or '').strip()
                if target_id:
                    dependency_target_ids.add(target_id)

        target_ids = {
            *applied_branch_ids,
            *applied_phase_ids,
            *dependency_target_ids,
        }
        obligations = [
            dict(item)
            for item in (graph.get('output_obligations') or [])
            if isinstance(item, dict)
        ]
        matched_obligations: list[dict[str, Any]] = []
        for obligation in obligations:
            obligation_id = str(obligation.get('obligation_id') or '').strip()
            record_ids = {
                obligation_id,
                str(obligation.get('branch_id') or '').strip(),
                str(obligation.get('phase_id') or '').strip(),
            }
            record_ids.discard('')
            if obligation_id in applied_obligation_ids or target_ids.intersection(record_ids):
                matched_obligations.append(obligation)
                target_ids.update(record_ids)

        phases = [
            dict(item)
            for item in (graph.get('phases') or [])
            if isinstance(item, dict)
        ]
        matched_phases: list[dict[str, Any]] = []
        for phase in phases:
            record_ids = {
                str(phase.get('branch_id') or '').strip(),
                str(phase.get('phase_id') or '').strip(),
                str(phase.get('obligation_id') or '').strip(),
            }
            record_ids.discard('')
            if target_ids.intersection(record_ids):
                matched_phases.append(phase)
                target_ids.update(record_ids)

        terminal_branch_states = {
            'cancelled',
            'candidate',
            'completed',
            'deferred_not_executable',
            'future',
            'future_candidate',
            'fulfilled',
            'held',
            'non_executable',
            'not_executable',
            'optional',
            'possible',
            'reserved',
            'reserved_candidate',
            'skipped',
            'superseded',
            'waived',
        }
        pending_branches: list[dict[str, Any]] = []
        unscheduled_branches: list[dict[str, Any]] = []
        seen_branch_ids: set[str] = set()
        seen_unscheduled_branch_ids: set[str] = set()

        def _record_unscheduled_branch(branch: dict[str, Any], reason: str) -> None:
            branch_id = str(branch.get('branch_id') or branch.get('phase_id') or '').strip()
            if not branch_id or branch_id in seen_unscheduled_branch_ids:
                return
            seen_unscheduled_branch_ids.add(branch_id)
            unscheduled_branches.append(
                _compact_payload(
                    {
                        'branch_id': branch_id,
                        'phase_id': str(branch.get('phase_id') or branch_id).strip() or branch_id,
                        'obligation_id': str(branch.get('obligation_id') or '').strip() or None,
                        'capability': str(branch.get('capability') or '').strip().lower() or None,
                        'output_type': str(branch.get('output_type') or '').strip().lower() or None,
                        'status': str(branch.get('status') or '').strip().lower() or None,
                        'repair_action': str(branch.get('repair_action') or '').strip() or None,
                        'repair_execution_policy': str(
                            branch.get('repair_execution_policy')
                            or branch.get('execution_policy')
                            or ''
                        ).strip() or None,
                        'reason': reason,
                    }
                )
            )

        def _append_pending_branch(raw_record: dict[str, Any]) -> None:
            branch = dict(raw_record)
            branch_id = str(branch.get('branch_id') or branch.get('phase_id') or '').strip()
            phase_id = str(branch.get('phase_id') or branch_id).strip() or branch_id
            capability = str(branch.get('capability') or '').strip().lower()
            if (
                not branch_id
                or not capability
                or branch_id in seen_branch_ids
                or branch_id in seen_unscheduled_branch_ids
            ):
                return
            if str(branch.get('status') or '').strip().lower() in terminal_branch_states:
                return
            if bool(branch.get('reserved_for_later') or branch.get('deferred_not_executable')):
                return
            if str(branch.get('role') or '').strip().lower() in {
                'candidate',
                'deferred_candidate',
                'future_candidate',
                'non_executable',
                'optional_output',
                'possible_future',
                'reserved_candidate',
            }:
                return
            matching_obligation = next(
                (
                    item
                    for item in matched_obligations
                    if branch_id
                    in {
                        str(item.get('branch_id') or '').strip(),
                        str(item.get('phase_id') or '').strip(),
                    }
                    or phase_id
                    in {
                        str(item.get('branch_id') or '').strip(),
                        str(item.get('phase_id') or '').strip(),
                    }
                ),
                None,
            )
            if matching_obligation:
                for key in (
                    'obligation_id',
                    'output_type',
                    'required',
                    'depends_on',
                    'input_refs',
                    'review_criteria',
                    'repair_action',
                    'repair_contract_id',
                    'repair_execution_policy',
                ):
                    if branch.get(key) in (None, '', [], {}) and matching_obligation.get(key) not in (None, '', [], {}):
                        branch[key] = matching_obligation.get(key)
            repair_policy_input = dict(branch)
            repair_execution_policy = str(
                repair_policy_input.get('repair_execution_policy')
                or repair_policy_input.get('execution_policy')
                or ''
            ).strip().lower()
            if repair_execution_policy and not repair_policy_input.get('execution_policy'):
                repair_policy_input['execution_policy'] = repair_execution_policy
            if repair_execution_policy in {
                'manual_review_required',
                'non_executable_until_promoted',
                'semantic_review_required',
            }:
                _record_unscheduled_branch(branch, 'repair_execution_policy_non_executable')
                return
            repair_policy = classify_repair_execution_policy(repair_policy_input)
            policy_schedules = (
                str(repair_policy.get('execution_policy') or '').strip().lower()
                == 'schedule_late_fill_branch'
                and repair_policy.get('auto_execute') is True
                and repair_policy.get('materialization_blocked') is not True
            )
            branch_status = str(branch.get('status') or '').strip().lower()
            resolved_blocked_policy = (
                repair_execution_policy.startswith('blocked_until_')
                and policy_schedules
            )
            if not policy_schedules:
                for key, value in repair_policy.items():
                    target_key = 'repair_execution_policy' if key == 'execution_policy' else key
                    if value not in (None, '', [], {}):
                        branch[target_key] = value
                _record_unscheduled_branch(branch, 'repair_execution_policy_blocked')
                return
            if branch_status in {'blocked', 'repair_needed', 'repair_pending'} and not resolved_blocked_policy:
                _record_unscheduled_branch(branch, 'branch_status_not_executable')
                return
            if (
                branch.get('auto_execute') is False
                or branch.get('materialization_blocked') is True
            ) and not resolved_blocked_policy:
                _record_unscheduled_branch(branch, 'branch_execution_contract_not_executable')
                return
            for key, value in repair_policy.items():
                target_key = 'repair_execution_policy' if key == 'execution_policy' else key
                if value not in (None, '', [], {}):
                    branch[target_key] = value
            branch['branch_id'] = branch_id
            branch['phase_id'] = phase_id
            branch['capability'] = capability
            branch['status'] = 'pending'
            branch.setdefault('source', 'runtime_applied_graph_patch')
            branch.setdefault('queue_index', len(pending_branches) + 1)
            seen_branch_ids.add(branch_id)
            pending_branches.append(_compact_payload(branch))

        for branch in graph.get('downstream_branches') or []:
            if not isinstance(branch, dict):
                continue
            record_ids = {
                str(branch.get('branch_id') or '').strip(),
                str(branch.get('phase_id') or '').strip(),
                str(branch.get('obligation_id') or '').strip(),
            }
            record_ids.discard('')
            if target_ids.intersection(record_ids):
                _append_pending_branch(branch)
        for phase in matched_phases:
            _append_pending_branch(phase)
        for obligation in matched_obligations:
            _append_pending_branch(obligation)

        reconciliation = {
            'kind': 'fruth.graph_patch_late_fill_reconciliation',
            'status': 'applied' if pending_branches else 'no_executable_branches',
            'authority': 'runtime_applied_graph_patch',
            'patch_ids': patch_ids,
            'applied_branch_ids': sorted(applied_branch_ids),
            'applied_phase_ids': sorted(applied_phase_ids),
            'applied_obligation_ids': sorted(applied_obligation_ids),
            'dependency_target_ids': sorted(dependency_target_ids),
            'scheduled_branch_ids': [
                str(item.get('branch_id') or item.get('phase_id') or '').strip()
                for item in pending_branches
            ],
            'unscheduled_branch_ids': [
                str(item.get('branch_id') or item.get('phase_id') or '').strip()
                for item in unscheduled_branches
            ],
            'unscheduled_branches': unscheduled_branches,
        }
        developer_diagnostics['graph_patch_late_fill_reconciliation'] = reconciliation
        runtime['developer_diagnostics'] = developer_diagnostics

        if unscheduled_branches:
            unscheduled_ids = {
                str(item.get('branch_id') or item.get('phase_id') or '').strip()
                for item in unscheduled_branches
                if str(item.get('branch_id') or item.get('phase_id') or '').strip()
            }

            def _remove_unscheduled_late_fill_branches(raw_state: Any) -> dict[str, Any]:
                state = dict(raw_state) if isinstance(raw_state, dict) else {}
                raw_pending = state.get('pending_branches')
                if not isinstance(raw_pending, list):
                    return state
                remaining = [
                    dict(item)
                    for item in raw_pending
                    if isinstance(item, dict)
                    and str(item.get('branch_id') or item.get('phase_id') or '').strip()
                    not in unscheduled_ids
                ]
                if len(remaining) == len([item for item in raw_pending if isinstance(item, dict)]):
                    return state
                existing_blocked = [
                    dict(item)
                    for item in (state.get('blocked_branches') or [])
                    if isinstance(item, dict)
                ]
                blocked_by_id = {
                    str(item.get('branch_id') or item.get('phase_id') or '').strip(): index
                    for index, item in enumerate(existing_blocked)
                    if str(item.get('branch_id') or item.get('phase_id') or '').strip()
                }
                for item in unscheduled_branches:
                    branch_id = str(item.get('branch_id') or item.get('phase_id') or '').strip()
                    blocked_record = {**item, 'status': 'blocked'}
                    if branch_id in blocked_by_id:
                        existing_blocked[blocked_by_id[branch_id]] = blocked_record
                    else:
                        blocked_by_id[branch_id] = len(existing_blocked)
                        existing_blocked.append(blocked_record)
                remaining_capabilities = []
                for item in remaining:
                    capability = str(item.get('capability') or '').strip().lower()
                    if capability and capability not in remaining_capabilities:
                        remaining_capabilities.append(capability)
                state['pending_branches'] = remaining
                state['pending_capabilities'] = remaining_capabilities
                state['blocked_branches'] = existing_blocked
                state['graph_patch_reconciliation'] = reconciliation
                if remaining:
                    state['status'] = 'pending'
                    for key in ('expected_capability', 'active_capability'):
                        if str(state.get(key) or '').strip().lower() not in remaining_capabilities:
                            state[key] = remaining_capabilities[0] if remaining_capabilities else None
                else:
                    state['status'] = 'blocked'
                    state['expected_capability'] = None
                    state['active_capability'] = None
                return state

            top_late_fill = _remove_unscheduled_late_fill_branches(updated.get('late_fill'))
            if top_late_fill:
                updated['late_fill'] = top_late_fill
            runtime_late_fill = _remove_unscheduled_late_fill_branches(runtime.get('late_fill'))
            if runtime_late_fill:
                runtime['late_fill'] = runtime_late_fill
        updated['runtime'] = runtime

        reconciled_closure_gap = (
            dict(closure_gap)
            if isinstance(closure_gap, dict)
            else None
        )
        if reconciled_closure_gap is not None and unscheduled_branches:
            if isinstance(reconciled_closure_gap.get('pending_branches'), list):
                remaining_pending_branches = [
                    dict(item)
                    for item in reconciled_closure_gap.get('pending_branches') or []
                    if isinstance(item, dict)
                    and str(item.get('branch_id') or item.get('phase_id') or '').strip()
                    not in unscheduled_ids
                ]
                if remaining_pending_branches:
                    reconciled_closure_gap['pending_branches'] = remaining_pending_branches
                    remaining_capabilities = []
                    for item in remaining_pending_branches:
                        capability = str(item.get('capability') or '').strip().lower()
                        if capability and capability not in remaining_capabilities:
                            remaining_capabilities.append(capability)
                    reconciled_closure_gap['pending_capabilities'] = remaining_capabilities
                    if remaining_capabilities:
                        for key in ('expected_capability', 'active_capability'):
                            if str(reconciled_closure_gap.get(key) or '').strip().lower() not in remaining_capabilities:
                                reconciled_closure_gap[key] = remaining_capabilities[0]
                else:
                    reconciled_closure_gap = None
            else:
                gap_branch_id = str(
                    reconciled_closure_gap.get('branch_id')
                    or reconciled_closure_gap.get('phase_id')
                    or ''
                ).strip()
                if gap_branch_id and gap_branch_id in unscheduled_ids:
                    reconciled_closure_gap = None

        if not pending_branches:
            if reconciled_closure_gap is not None:
                reconciled_closure_gap['graph_patch_reconciliation'] = reconciliation
                return updated, _compact_payload(reconciled_closure_gap)
            return updated, None

        gap = dict(reconciled_closure_gap or {})
        existing_branches = [
            dict(item)
            for item in (gap.get('pending_branches') or [])
            if isinstance(item, dict)
        ]
        branch_positions = {
            str(item.get('branch_id') or item.get('phase_id') or '').strip(): index
            for index, item in enumerate(existing_branches)
            if str(item.get('branch_id') or item.get('phase_id') or '').strip()
        }
        for branch in pending_branches:
            branch_id = str(branch.get('branch_id') or branch.get('phase_id') or '').strip()
            if branch_id in branch_positions:
                index = branch_positions[branch_id]
                existing_branches[index] = {
                    **branch,
                    **existing_branches[index],
                    'depends_on': branch.get('depends_on') or existing_branches[index].get('depends_on'),
                }
                continue
            branch_positions[branch_id] = len(existing_branches)
            existing_branches.append(branch)

        pending_capabilities = [
            str(item or '').strip().lower()
            for item in (gap.get('pending_capabilities') or [])
            if str(item or '').strip()
        ]
        for branch in existing_branches:
            capability = str(branch.get('capability') or '').strip().lower()
            if capability and capability not in pending_capabilities:
                pending_capabilities.append(capability)

        first_branch = existing_branches[0]
        gap.update(
            {
                'code': str(gap.get('code') or 'graph_patch_late_fill').strip(),
                'trigger': str(gap.get('trigger') or 'runtime_applied_graph_patch').strip(),
                'expected_capability': str(
                    gap.get('expected_capability')
                    or first_branch.get('capability')
                    or ''
                ).strip(),
                'active_capability': str(
                    gap.get('active_capability')
                    or gap.get('expected_capability')
                    or first_branch.get('capability')
                    or ''
                ).strip(),
                'missing_artifact_type': str(
                    gap.get('missing_artifact_type')
                    or first_branch.get('output_type')
                    or ''
                ).strip(),
                'pending_branches': existing_branches,
                'pending_capabilities': pending_capabilities,
                'graph_patch_reconciliation': reconciliation,
            }
        )
        return updated, _compact_payload(gap)

    @staticmethod
    def _graph_patch_successor_lifecycle(
        graph: dict[str, Any],
        candidate: dict[str, Any],
    ) -> dict[str, Any]:
        proposal_id = str(candidate.get('proposal_id') or '').strip()
        patch_id = str(candidate.get('patch_id') or '').strip()
        idempotency_key = str(candidate.get('idempotency_key') or '').strip()
        if not proposal_id or not patch_id or not idempotency_key:
            return {}
        for item in graph.get('graph_patch_lifecycle') or []:
            if not isinstance(item, dict):
                continue
            if str(item.get('proposal_id') or '').strip() != proposal_id:
                continue
            if str(item.get('patch_id') or '').strip() != patch_id:
                continue
            if str(item.get('idempotency_key') or '').strip() != idempotency_key:
                continue
            return dict(item)
        return {}

    @staticmethod
    def _rederive_graph_patch_successor_application(
        parent_graph: dict[str, Any],
        lifecycle: dict[str, Any],
        candidate: dict[str, Any],
    ) -> dict[str, Any]:
        """Re-apply exact validated patch truth instead of trusting candidate scope."""

        base_graph = copy.deepcopy(parent_graph)
        # Terminal production may contain several proposal/lifecycle candidates.
        # Those records are audit ordering, not patch input. Re-derive the
        # candidate's semantic delta against the parent graph with only terminal
        # repair bookkeeping removed, then bind the executable scope to that
        # independently produced application result.
        for key in (
            'graph_patch_lifecycle',
            'staged_graph_patches',
            'applied_graph_patches',
            'successor_reopen_requests',
            'successor_reopen_executions',
        ):
            base_graph.pop(key, None)
        validation_review = (
            lifecycle.get('validation_review')
            if isinstance(lifecycle.get('validation_review'), dict)
            else {}
        )
        application = apply_validated_graph_repair_patch(
            base_graph,
            validation_review,
        )
        if str(application.get('status') or '').strip().lower() != 'applied':
            return {
                'status': 'blocked',
                'blocked_reasons': application.get('blocked_reasons') or [
                    'successor_patch_reapplication_not_applied'
                ],
                'application': application,
            }
        return {
            'status': 'applied',
            'base_graph': base_graph,
            'application': application,
        }

    def _prepare_graph_patch_successor_reopen(
        self,
        response_payload: dict[str, Any],
        candidate: dict[str, Any],
    ) -> dict[str, Any]:
        """Project one validated terminal patch candidate into exact Late Fill work."""

        blocked_reasons: list[str] = []

        def block(reason: str) -> None:
            token = str(reason or '').strip()
            if token and token not in blocked_reasons:
                blocked_reasons.append(token)

        if not isinstance(response_payload, dict) or not isinstance(candidate, dict):
            return {'status': 'blocked', 'blocked_reasons': ['successor_payload_invalid']}
        if candidate.get('kind') != 'fruth.graph_patch_successor_reopen_request':
            block('successor_request_kind_mismatch')
        if str(candidate.get('status') or '').strip().lower() != 'candidate':
            block('successor_request_not_candidate')
        if str(candidate.get('risk_level') or '').strip().lower() != 'safe_additive':
            block('successor_repair_not_safe_additive')
        if str(candidate.get('runtime_effect') or '').strip() != 'successor_reopen_required':
            block('successor_runtime_effect_mismatch')

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
        if not response_id or str(candidate.get('parent_response_id') or '').strip() != response_id:
            block('successor_parent_response_mismatch')
        if not parent_frame_id or str(candidate.get('parent_frame_id') or '').strip() != parent_frame_id:
            block('successor_parent_frame_mismatch')
        if candidate.get('parent_frame_sequence') != parent_frame_sequence:
            block('successor_parent_frame_sequence_mismatch')

        identity = {
            key: str(candidate.get(key) or '').strip()
            for key in ('proposal_id', 'patch_id', 'idempotency_key')
        }
        for key, value in identity.items():
            if not value:
                block(f'successor_{key}_missing')

        try:
            successor_depth = int(candidate.get('successor_reopen_depth') or 0)
        except (TypeError, ValueError):
            successor_depth = 0
        expected_successor_depth = _graph_patch_successor_parent_depth(response_payload) + 1
        if successor_depth < 1:
            block('successor_reopen_depth_invalid')
        if successor_depth != expected_successor_depth:
            block('successor_reopen_depth_parent_mismatch')
        if successor_depth > _MAX_GRAPH_PATCH_SUCCESSOR_REOPEN_DEPTH:
            block('successor_reopen_depth_exhausted')

        successor_graph = (
            copy.deepcopy(candidate.get('successor_request_phase_graph'))
            if isinstance(candidate.get('successor_request_phase_graph'), dict)
            else {}
        )
        if not successor_graph:
            block('successor_graph_missing')
        expected_successor_digest = str(candidate.get('successor_graph_digest') or '').strip()
        actual_successor_digest = stable_graph_repair_graph_digest(successor_graph)
        if not expected_successor_digest or expected_successor_digest != actual_successor_digest:
            block('successor_graph_digest_mismatch')

        parent_runtime = (
            response_payload.get('runtime')
            if isinstance(response_payload.get('runtime'), dict)
            else {}
        )
        parent_graph = (
            parent_runtime.get('request_phase_graph')
            if isinstance(parent_runtime.get('request_phase_graph'), dict)
            else {}
        )
        lifecycle = self._graph_patch_successor_lifecycle(parent_graph, candidate)
        if not lifecycle:
            identity_lifecycle = next(
                (
                    dict(item)
                    for item in (parent_graph.get('graph_patch_lifecycle') or [])
                    if isinstance(item, dict)
                    and identity['patch_id']
                    and identity['idempotency_key']
                    and str(item.get('patch_id') or '').strip() == identity['patch_id']
                    and str(item.get('idempotency_key') or '').strip() == identity['idempotency_key']
                ),
                {},
            )
            if identity_lifecycle and str(identity_lifecycle.get('proposal_id') or '').strip() != identity['proposal_id']:
                block('successor_proposal_id_lifecycle_mismatch')
                lifecycle = identity_lifecycle
            else:
                block('successor_patch_lifecycle_missing')
        else:
            for key, value in identity.items():
                if str(lifecycle.get(key) or '').strip() != value:
                    block(f'successor_{key}_lifecycle_mismatch')
            if str(lifecycle.get('autonomy_level') or '').strip().lower() != str(
                candidate.get('autonomy_level') or ''
            ).strip().lower():
                block('successor_autonomy_lifecycle_mismatch')
            if str(lifecycle.get('risk_level') or '').strip().lower() != 'safe_additive':
                block('successor_patch_lifecycle_risk_mismatch')
            if str(lifecycle.get('before_graph_digest') or '').strip() != str(
                candidate.get('before_graph_digest') or ''
            ).strip():
                block('successor_before_graph_digest_mismatch')
            if str(lifecycle.get('patch_digest') or '').strip() != str(
                candidate.get('patch_digest') or ''
            ).strip():
                block('successor_patch_digest_mismatch')
            validation_review = (
                lifecycle.get('validation_review')
                if isinstance(lifecycle.get('validation_review'), dict)
                else {}
            )
            if (
                validation_review.get('kind') != 'fruth.graph_repair_proposal_review'
                or str(validation_review.get('status') or '').strip().lower() != 'accepted'
            ):
                block('successor_runtime_validation_not_accepted')
            non_terminal_blockers = {
                str(item).strip()
                for item in (lifecycle.get('blocked_reasons') or [])
                if str(item or '').strip()
            } - {'terminal_frame_requires_successor_reopen'}
            if non_terminal_blockers:
                block('successor_patch_lifecycle_has_nonterminal_blocker')

        patch_application = (
            candidate.get('patch_application')
            if isinstance(candidate.get('patch_application'), dict)
            else {}
        )
        if str(patch_application.get('status') or '').strip().lower() != 'applied':
            block('successor_patch_application_not_applied')
        for key in ('proposal_id', 'patch_id', 'idempotency_key'):
            if str(patch_application.get(key) or '').strip() != str(candidate.get(key) or '').strip():
                block(f'successor_patch_application_{key}_mismatch')
        expected_execution_contract = {
            'execution_scope': 'successor_owed_branches_only',
            'root_scoped': False,
            'allow_root_prompt': False,
            'preserve_request_id': True,
        }
        execution_contract = (
            candidate.get('execution_contract')
            if isinstance(candidate.get('execution_contract'), dict)
            else {}
        )
        if execution_contract != expected_execution_contract:
            block('successor_execution_contract_mismatch')
        if blocked_reasons:
            return {'status': 'blocked', 'blocked_reasons': blocked_reasons}

        rederived = self._rederive_graph_patch_successor_application(
            parent_graph,
            lifecycle,
            candidate,
        )
        if rederived.get('status') != 'applied':
            return {
                'status': 'blocked',
                'blocked_reasons': rederived.get('blocked_reasons') or [
                    'successor_patch_reapplication_not_applied'
                ],
            }
        expected_application = (
            rederived.get('application')
            if isinstance(rederived.get('application'), dict)
            else {}
        )
        expected_graph = (
            expected_application.get('graph')
            if isinstance(expected_application.get('graph'), dict)
            else {}
        )
        expected_semantic_graph = copy.deepcopy(expected_graph)
        candidate_semantic_graph = copy.deepcopy(successor_graph)
        for graph_payload in (expected_semantic_graph, candidate_semantic_graph):
            for key in (
                'graph_patch_lifecycle',
                'staged_graph_patches',
                'applied_graph_patches',
                'successor_reopen_requests',
                'successor_reopen_executions',
            ):
                graph_payload.pop(key, None)
        if stable_graph_repair_graph_digest(expected_semantic_graph) != stable_graph_repair_graph_digest(
            candidate_semantic_graph
        ):
            block('successor_rederived_graph_digest_mismatch')

        if str(patch_application.get('kind') or '').strip() != 'fruth.graph_patch_lifecycle':
            block('successor_patch_application_kind_rederived_mismatch')
        if str(patch_application.get('status') or '').strip().lower() != 'applied':
            block('successor_patch_application_status_rederived_mismatch')
        if str(patch_application.get('proposal_id') or '').strip() != identity['proposal_id']:
            block('successor_patch_application_proposal_id_rederived_mismatch')
        if str(patch_application.get('patch_id') or '').strip() != identity['patch_id']:
            block('successor_patch_application_patch_id_rederived_mismatch')
        if str(patch_application.get('idempotency_key') or '').strip() != identity['idempotency_key']:
            block('successor_patch_application_idempotency_key_rederived_mismatch')
        if str(patch_application.get('original_graph_digest') or '').strip() != str(
            lifecycle.get('before_graph_digest') or ''
        ).strip():
            block('successor_patch_application_original_graph_digest_rederived_mismatch')
        def is_current_patch_record(record: Any) -> bool:
            return bool(
                isinstance(record, dict)
                and all(
                    str(record.get(key) or '').strip() == value
                    for key, value in identity.items()
                )
            )

        patched_graph_before_lifecycle = copy.deepcopy(successor_graph)
        for key in ('graph_patch_lifecycle', 'applied_graph_patches'):
            remaining = [
                dict(item)
                for item in (patched_graph_before_lifecycle.get(key) or [])
                if isinstance(item, dict) and not is_current_patch_record(item)
            ]
            if remaining:
                patched_graph_before_lifecycle[key] = remaining
            else:
                patched_graph_before_lifecycle.pop(key, None)
        if str(patch_application.get('patched_graph_digest') or '').strip() != (
            stable_graph_repair_graph_digest(patched_graph_before_lifecycle)
        ):
            block('successor_patch_application_patched_graph_digest_rederived_mismatch')

        for key in ('applied_branch_ids', 'applied_phase_ids', 'applied_obligation_ids'):
            actual_ids = [
                str(item).strip()
                for item in (patch_application.get(key) or [])
                if str(item or '').strip()
            ]
            expected_ids = [
                str(item).strip()
                for item in (expected_application.get(key) or [])
                if str(item or '').strip()
            ]
            if actual_ids != expected_ids:
                block(f'successor_patch_application_{key}_rederived_mismatch')

        def normalized_edges(values: Any) -> list[tuple[str, str]]:
            return sorted(
                (
                    str(item.get('target_id') or '').strip(),
                    str(item.get('source_id') or '').strip(),
                )
                for item in (values or [])
                if isinstance(item, dict)
            )

        if normalized_edges(patch_application.get('applied_dependency_edges')) != normalized_edges(
            expected_application.get('applied_dependency_edges')
        ):
            block('successor_patch_application_applied_dependency_edges_rederived_mismatch')

        owed_branch_ids, owed_output_obligations = _graph_patch_successor_owed_scope(
            expected_graph,
            expected_application,
            fallback_branch_ids=lifecycle.get('scheduled_branch_ids') or [],
        )
        candidate_owed_branch_ids = list(
            dict.fromkeys(
                str(item).strip()
                for item in (candidate.get('owed_branch_ids') or [])
                if str(item or '').strip()
            )
        )
        if not owed_branch_ids:
            block('successor_owed_branch_ids_missing')
        if candidate_owed_branch_ids != owed_branch_ids:
            block('successor_owed_branch_scope_mismatch')
        if (candidate.get('owed_output_obligations') or []) != owed_output_obligations:
            block('successor_owed_obligation_scope_mismatch')

        expected_reopen_key, expected_execution_key = _graph_patch_successor_keys(
            response_id=response_id,
            parent_frame_id=parent_frame_id,
            patch_id=identity['patch_id'],
            idempotency_key=identity['idempotency_key'],
            owed_branch_ids=owed_branch_ids,
            successor_depth=expected_successor_depth,
        )
        if str(candidate.get('successor_reopen_key') or '').strip() != expected_reopen_key:
            block('successor_reopen_key_mismatch')
        if str(candidate.get('successor_execution_key') or '').strip() != expected_execution_key:
            block('successor_execution_key_mismatch')
        expected_relation = {
            'kind': 'graph_patch_reopen_successor',
            'reason': 'graph_patch_reopen',
            'parent_response_id': response_id,
            'parent_frame_id': parent_frame_id,
            'parent_frame_sequence': parent_frame_sequence,
            'successor_reopen_depth': expected_successor_depth,
        }
        if candidate.get('frame_relation') != expected_relation:
            block('successor_frame_relation_mismatch')
        if blocked_reasons:
            return {'status': 'blocked', 'blocked_reasons': blocked_reasons}

        synthetic_result = {
            'status': 'applied',
            'patch_id': candidate.get('patch_id'),
            'applied_branch_ids': owed_branch_ids,
            'applied_phase_ids': expected_application.get('applied_phase_ids') or owed_branch_ids,
            'applied_obligation_ids': expected_application.get('applied_obligation_ids') or [],
            'applied_dependency_edges': expected_application.get('applied_dependency_edges') or [],
        }
        successor_payload = copy.deepcopy(response_payload)
        successor_runtime = (
            dict(successor_payload.get('runtime') or {})
            if isinstance(successor_payload.get('runtime'), dict)
            else {}
        )
        successor_diagnostics = (
            dict(successor_runtime.get('developer_diagnostics') or {})
            if isinstance(successor_runtime.get('developer_diagnostics'), dict)
            else {}
        )
        successor_diagnostics['graph_patch_lifecycle_results'] = [synthetic_result]
        successor_runtime['request_phase_graph'] = successor_graph
        successor_runtime['developer_diagnostics'] = successor_diagnostics
        successor_payload['runtime'] = successor_runtime
        successor_payload, artifact_gap = self._reconcile_applied_graph_patch_late_fill_gap(
            successor_payload,
            None,
        )
        if not isinstance(artifact_gap, dict):
            return {
                'status': 'blocked',
                'blocked_reasons': ['successor_owed_branches_not_executable'],
            }
        pending_branches = [
            dict(item)
            for item in (artifact_gap.get('pending_branches') or [])
            if isinstance(item, dict)
        ]
        scheduled_branch_ids = [
            str(item.get('branch_id') or item.get('phase_id') or '').strip()
            for item in pending_branches
            if str(item.get('branch_id') or item.get('phase_id') or '').strip()
        ]
        if set(scheduled_branch_ids) != set(owed_branch_ids):
            return {
                'status': 'blocked',
                'blocked_reasons': ['successor_owed_branches_not_exactly_executable'],
                'scheduled_branch_ids': scheduled_branch_ids,
                'owed_branch_ids': owed_branch_ids,
            }
        for branch in pending_branches:
            branch_contract = (
                branch.get('execution_contract')
                if isinstance(branch.get('execution_contract'), dict)
                else {}
            )
            if (
                str(branch_contract.get('execution_scope') or '').strip().lower()
                in {'root', 'root_scoped', 'whole_request', 'original_prompt'}
                or branch_contract.get('root_scoped') is True
                or branch_contract.get('allow_root_prompt') is True
            ):
                block('successor_branch_root_prompt_execution_forbidden')
            if branch.get('needs_external_input') is True:
                block('successor_branch_needs_external_input')
            if branch.get('materialization_blocked') is True:
                block('successor_branch_materialization_blocked')
        if blocked_reasons:
            return {'status': 'blocked', 'blocked_reasons': blocked_reasons}

        prior_late_fill = (
            response_payload.get('late_fill')
            if isinstance(response_payload.get('late_fill'), dict)
            else {}
        )
        owed_id_set = set(owed_branch_ids)

        def without_owed(values: Any) -> list[dict[str, Any]]:
            return [
                dict(item)
                for item in (values or [])
                if isinstance(item, dict)
                and str(item.get('branch_id') or item.get('phase_id') or '').strip()
                not in owed_id_set
            ]

        pending_capabilities = list(
            dict.fromkeys(
                str(item.get('capability') or '').strip().lower()
                for item in pending_branches
                if str(item.get('capability') or '').strip()
            )
        )
        execution_record = _compact_payload(
            {
                'kind': 'fruth.graph_patch_successor_reopen_execution',
                'status': 'queued',
                'successor_reopen_key': candidate.get('successor_reopen_key'),
                'successor_execution_key': candidate.get('successor_execution_key'),
                'patch_id': candidate.get('patch_id'),
                'idempotency_key': candidate.get('idempotency_key'),
                'successor_graph_digest': expected_successor_digest,
                'successor_reopen_depth': successor_depth,
                'parent_response_id': response_id,
                'parent_frame_id': parent_frame_id,
                'parent_frame_sequence': parent_frame_sequence,
                'scheduled_branch_ids': scheduled_branch_ids,
                'root_prompt_replay': False,
            }
        )
        # Publish the exact execution only after the admission gates above have
        # passed, before attaching its envelope. The callback merge can then
        # distinguish fresh authorized repair from an old/foreign execution.
        admitted_graph = copy.deepcopy(successor_payload['runtime']['request_phase_graph'])
        admitted_graph['successor_reopen_executions'] = [
            *[dict(item) for item in (admitted_graph.get('successor_reopen_executions') or [])
              if isinstance(item, Mapping)
              and item.get('successor_execution_key') != execution_record['successor_execution_key']],
            execution_record,
        ]
        successor_payload['runtime']['request_phase_graph'] = admitted_graph
        artifact_gap.update(
            {
                'code': 'graph_patch_late_fill',
                'trigger': 'graph_patch_successor_reopen',
                'pending_branch_scope': 'exact_successor_reopen',
                'authoritative_pending_branches': True,
                'preserve_request_id': True,
                'pending_branches': pending_branches,
                'pending_capabilities': pending_capabilities,
                'active_branches': [],
                'completed_branches': without_owed(prior_late_fill.get('completed_branches')),
                'failed_branches': without_owed(prior_late_fill.get('failed_branches')),
                'cancelled_branches': without_owed(prior_late_fill.get('cancelled_branches')),
                'successor_reopen_execution': execution_record,
                'execution_contract': {
                    'execution_scope': 'successor_owed_branches_only',
                    'root_scoped': False,
                    'allow_root_prompt': False,
                    'preserve_request_id': True,
                },
            }
        )
        build_late_fill_state = self.build_late_fill_state
        attach_late_fill_state = self.attach_late_fill_state
        pending_late_fill = build_late_fill_state(
            artifact_gap,
            status='pending',
            prior_state=prior_late_fill,
            extra={
                'pending_branch_scope': 'exact_successor_reopen',
                'authoritative_pending_branches': True,
                'successor_reopen_execution': execution_record,
                'fill_results': prior_late_fill.get('fill_results') or [],
            },
        )
        successor_payload = attach_late_fill_state(successor_payload, pending_late_fill)

        successor_runtime = (
            dict(successor_payload.get('runtime') or {})
            if isinstance(successor_payload.get('runtime'), dict)
            else {}
        )
        execution_graph = (
            copy.deepcopy(successor_runtime.get('request_phase_graph'))
            if isinstance(successor_runtime.get('request_phase_graph'), dict)
            else successor_graph
        )
        candidate_record = {
            key: copy.deepcopy(value)
            for key, value in candidate.items()
            if key != 'successor_request_phase_graph'
        }
        candidate_record.update(
            {
                'status': 'applied_to_successor',
                'runtime_effect': 'successor_late_fill_queued',
                'execution': execution_record,
            }
        )
        existing_requests = [
            dict(item)
            for item in (execution_graph.get('successor_reopen_requests') or [])
            if isinstance(item, dict)
            and str(item.get('successor_execution_key') or '').strip()
            != str(candidate.get('successor_execution_key') or '').strip()
        ]
        execution_graph['successor_reopen_requests'] = [*existing_requests, candidate_record]
        existing_executions = [
            dict(item)
            for item in (execution_graph.get('successor_reopen_executions') or [])
            if isinstance(item, dict)
            and str(item.get('successor_execution_key') or '').strip()
            != str(candidate.get('successor_execution_key') or '').strip()
        ]
        execution_graph['successor_reopen_executions'] = [*existing_executions, execution_record]
        successor_runtime['request_phase_graph'] = execution_graph
        successor_diagnostics = (
            dict(successor_runtime.get('developer_diagnostics') or {})
            if isinstance(successor_runtime.get('developer_diagnostics'), dict)
            else {}
        )
        successor_diagnostics['graph_patch_successor_reopen_execution'] = execution_record
        successor_diagnostics['graph_patch_successor_reopen_request'] = candidate_record
        successor_runtime['developer_diagnostics'] = successor_diagnostics
        successor_runtime['lifecycle_state'] = 'late_fill_pending'
        successor_payload['runtime'] = successor_runtime
        successor_payload['lifecycle_state'] = 'late_fill_pending'
        successor_payload['late_fill_pending'] = True
        successor_payload['frame_relation'] = {
            **dict(candidate.get('frame_relation') or {}),
            'kind': 'graph_patch_reopen_successor',
            'reason': 'graph_patch_reopen',
            'response_id': response_id,
            'parent_response_id': response_id,
            'parent_frame_id': parent_frame_id,
            'parent_frame_sequence': parent_frame_sequence,
            'successor_reopen_depth': successor_depth,
            'successor_execution_key': candidate.get('successor_execution_key'),
        }
        return {
            'status': 'queued',
            'response_payload': successor_payload,
            'artifact_gap': _compact_payload(artifact_gap),
            'successor_reopen_request': candidate_record,
            'execution': execution_record,
        }

    def prepare_terminal_graph_patch_successor(
        self,
        response_payload: dict[str, Any],
        *,
        graph_repair_autonomy: Optional[str] = None,
    ) -> dict[str, Any]:
        """Produce and prepare one bounded terminal graph-patch successor wave."""

        if not isinstance(response_payload, dict):
            return {'status': 'not_applicable', 'reason': 'response_payload_invalid'}
        autonomy_description = (
            describe_graph_repair_autonomy(
                graph_repair_autonomy,
                source='explicit_override',
                configured=True,
            )
            if graph_repair_autonomy is not None
            else describe_graph_repair_autonomy_from_env()
        )
        autonomy_level = normalize_graph_repair_autonomy(
            autonomy_description.get('autonomy_level')
        )
        if autonomy_level == 'off':
            return {'status': 'not_applicable', 'reason': 'graph_repair_autonomy_off'}
        if autonomy_level not in {'apply_safe', 'apply_enforced'}:
            return {
                'status': 'not_applicable',
                'reason': 'graph_repair_autonomy_not_executable',
                'autonomy_level': autonomy_level,
            }
        parent_frame = (
            response_payload.get('response_frame')
            if isinstance(response_payload.get('response_frame'), dict)
            else {}
        )
        if not str(parent_frame.get('frame_id') or '').strip():
            return {'status': 'not_applicable', 'reason': 'terminal_parent_frame_missing'}

        reviewed = self._attach_redraw_scope_ladder_review(copy.deepcopy(response_payload))
        reviewed = self._attach_runtime_graph_repair_evidence(reviewed)
        reviewed = self._attach_graph_patch_lifecycle(
            reviewed,
            graph_repair_autonomy=autonomy_level,
        )
        runtime = reviewed.get('runtime') if isinstance(reviewed.get('runtime'), dict) else {}
        graph = (
            runtime.get('request_phase_graph')
            if isinstance(runtime.get('request_phase_graph'), dict)
            else {}
        )
        candidates = [
            dict(item)
            for item in (graph.get('successor_reopen_requests') or [])
            if isinstance(item, dict)
            and str(item.get('status') or '').strip().lower() == 'candidate'
        ]
        if not candidates:
            return {
                'status': 'not_applicable',
                'reason': 'no_safe_terminal_graph_patch_successor',
                'response_payload': reviewed,
            }

        blocked_results: list[dict[str, Any]] = []
        for candidate in candidates:
            if str(candidate.get('autonomy_level') or '').strip().lower() != autonomy_level:
                blocked_results.append(
                    {
                        'status': 'blocked',
                        'blocked_reasons': ['successor_autonomy_binding_mismatch'],
                    }
                )
                continue
            lifecycle = self._graph_patch_successor_lifecycle(graph, candidate)
            if autonomy_level == 'apply_enforced':
                policy_review = build_enforced_policy_review(
                    autonomy_level=autonomy_level,
                    lifecycle=lifecycle,
                    request_phase_graph=graph,
                )
                if not enforced_policy_allows_application(policy_review):
                    blocked_results.append(
                        {
                            'status': 'blocked',
                            'blocked_reasons': policy_review.get('blocked_reasons') or [
                                'successor_enforced_policy_recheck_blocked'
                            ],
                            'enforced_policy_review': policy_review,
                        }
                    )
                    continue
                if (
                    candidate.get('allowed_by_policy') is not True
                    or str(candidate.get('policy_mode') or '').strip().lower() != 'safe_v1'
                ):
                    blocked_results.append(
                        {
                            'status': 'blocked',
                            'blocked_reasons': ['successor_enforced_policy_binding_mismatch'],
                        }
                    )
                    continue
            prepared = self._prepare_graph_patch_successor_reopen(reviewed, candidate)
            if prepared.get('status') == 'queued':
                prepared['autonomy'] = autonomy_description
                return prepared
            blocked_results.append(prepared)
        blocked_reasons = list(
            dict.fromkeys(
                str(reason).strip()
                for result in blocked_results
                for reason in (result.get('blocked_reasons') or [])
                if str(reason or '').strip()
            )
        )
        return {
            'status': 'blocked',
            'blocked_reasons': blocked_reasons or ['terminal_graph_patch_successor_blocked'],
            'response_payload': reviewed,
        }

