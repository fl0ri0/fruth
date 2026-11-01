"""Project accepted Closure repair duties into an exact terminal repair gap.

This transformation preserves promoted contract identity, inherited dependencies,
and bounded execution policy. It neither invokes inference nor schedules, writes,
or publishes a successor; the request/worker adapters retain those authorities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from fruth_server.graph_rebase_continuation import _ACTIVE_LATE_FILL_STATUSES
from fruth_server.graph_patch_continuation import _compact_payload
import hashlib
import json
import re
from typing import Any, Mapping, Optional
from fruth_server.repair_gate_runtime import classify_repair_execution_policy
from fruth_services.graph_repair import (
    build_graph_repair_proposal_from_repair_gap,
    validate_graph_repair_proposal,
)


@dataclass(frozen=True)
class TerminalRepairProjection:
    normalize_capability: Callable[[Any], Optional[str]]
    capability_chat: str
    capability_image_generation: str
    capability_speech_to_text: str

    def _repair_output_type_for_capability(self, capability: Any) -> Optional[str]:
        normalize_capability = self.normalize_capability

        normalized = normalize_capability(capability)
        if normalized == self.capability_image_generation:
            return 'image'
        if normalized == self.capability_speech_to_text:
            return 'text'
        if normalized == self.capability_chat:
            return 'text'
        if normalized == 'text_to_speech':
            return 'audio'
        return None

    def _inference_repair_feedback_gap(
        self,
        graph_closure_review: Optional[dict[str, Any]],
        *,
        prior_gap: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        normalize_capability = self.normalize_capability

        review = graph_closure_review if isinstance(graph_closure_review, dict) else {}
        feedback = (
            review.get('inference_repair_feedback')
            if isinstance(review.get('inference_repair_feedback'), dict)
            else {}
        )
        if str(feedback.get('status') or '').strip().lower() != 'repair_required':
            return None
        if str(review.get('late_fill_status') or '').strip().lower() in _ACTIVE_LATE_FILL_STATUSES:
            return None
        items = feedback.get('items') if isinstance(feedback.get('items'), list) else []
        if not items:
            return None
        repair_loop = (
            feedback.get('repair_loop')
            if isinstance(feedback.get('repair_loop'), dict)
            else None
        )

        existing_branches = (
            list(prior_gap.get('pending_branches') or [])
            if isinstance(prior_gap, dict) and isinstance(prior_gap.get('pending_branches'), list)
            else []
        )
        seen_branch_ids = {
            str(item.get('branch_id') or item.get('phase_id') or '').strip()
            for item in existing_branches
            if isinstance(item, dict) and str(item.get('branch_id') or item.get('phase_id') or '').strip()
        }
        pending_branches: list[dict[str, Any]] = []
        pending_capabilities: list[str] = []
        repair_actions: list[str] = []
        repair_loop_contracts = (
            repair_loop.get('promoted_contracts')
            if isinstance(repair_loop, dict) and isinstance(repair_loop.get('promoted_contracts'), list)
            else []
        )
        feedback_contracts = (
            feedback.get('repair_rebuild_contracts')
            if isinstance(feedback.get('repair_rebuild_contracts'), list)
            else []
        )
        promoted_contracts = []
        seen_contract_ids: set[str] = set()

        for item in [*feedback_contracts, *repair_loop_contracts]:
            if not isinstance(item, dict):
                continue
            contract = dict(item)
            contract_id = str(contract.get('contract_id') or repr(sorted(contract.items()))).strip()
            if contract_id in seen_contract_ids:
                continue
            seen_contract_ids.add(contract_id)
            for key, value in classify_repair_execution_policy(contract).items():
                contract.setdefault(key, value)
            promoted_contracts.append(contract)
        repair_loop_payload = dict(repair_loop or {}) if isinstance(repair_loop, dict) else None
        if repair_loop_payload is not None:
            repair_work_available_count = sum(
                1 for item in promoted_contracts if item.get('repair_work_available') is True
            )
            needs_external_input_count = sum(
                1 for item in promoted_contracts if item.get('needs_external_input') is True
            )
            blocked_contract_count = sum(
                1 for item in promoted_contracts if item.get('auto_execute') is not True
            )
            repair_loop_payload.setdefault('repair_work_available', bool(repair_work_available_count))
            repair_loop_payload.setdefault('repair_work_available_count', repair_work_available_count)
            repair_loop_payload.setdefault('needs_external_input_count', needs_external_input_count)
            repair_loop_payload.setdefault('materialization_blocked_contract_count', blocked_contract_count)
            repair_loop_payload['promoted_contracts'] = promoted_contracts
        contract_by_identity: dict[str, dict[str, Any]] = {}
        for contract in promoted_contracts:
            for key in ('branch_id', 'phase_id', 'obligation_id', 'task_id', 'contract_id'):
                token = str(contract.get(key) or '').strip()
                if token:
                    contract_by_identity.setdefault(token, contract)

        def _slug(value: Any, fallback: str) -> str:
            token = str(value or '').strip().lower()
            token = re.sub(r'[^a-z0-9_]+', '-', token.replace(' ', '-'))
            token = re.sub(r'-+', '-', token).strip('-')
            return token or fallback

        def _repair_contract_for_item(raw_item: dict[str, Any]) -> dict[str, Any]:
            direct_contract = raw_item.get('repair_contract')
            if isinstance(direct_contract, dict):
                return dict(direct_contract)
            for key in ('branch_id', 'phase_id', 'obligation_id', 'task_id', 'repair_contract_id'):
                token = str(raw_item.get(key) or '').strip()
                if token and token in contract_by_identity:
                    return dict(contract_by_identity[token])
            return {}

        for raw_item in items:
            if not isinstance(raw_item, dict):
                continue
            repair_contract = _repair_contract_for_item(raw_item)
            capability = normalize_capability(raw_item.get('capability'))
            if not capability:
                capability = normalize_capability(repair_contract.get('capability'))
            output_type = str(raw_item.get('output_type') or '').strip().lower()
            if not output_type:
                output_type = str(repair_contract.get('output_type') or '').strip().lower()
            if not output_type:
                output_type = self._repair_output_type_for_capability(capability) or ''
            repair_action = str(
                raw_item.get('repair_action')
                or raw_item.get('recovery_action')
                or repair_contract.get('repair_action')
                or ''
            ).strip()
            allow_chat_repair = (
                capability == self.capability_chat
                and output_type == 'text'
                and (
                    repair_action
                    or raw_item.get('depends_on')
                    or raw_item.get('execution_contract')
                    or raw_item.get('workload_task_ref')
                )
            )
            if not capability or (capability == self.capability_chat and not allow_chat_repair):
                continue
            if not output_type:
                continue
            if repair_action and repair_action not in repair_actions:
                repair_actions.append(repair_action)
            raw_branch_identity = str(raw_item.get('branch_id') or raw_item.get('phase_id') or '').strip()
            if raw_branch_identity and raw_branch_identity in seen_branch_ids:
                continue
            try:
                missing_count = int(raw_item.get('missing_count') or 1)
            except (TypeError, ValueError):
                missing_count = 1
            missing_count = max(1, missing_count)
            if capability not in pending_capabilities:
                pending_capabilities.append(capability)
            base_identity = (
                repair_contract.get('branch_id')
                or repair_contract.get('phase_id')
                or repair_contract.get('obligation_id')
                or raw_item.get('branch_id')
                or raw_item.get('phase_id')
                or raw_item.get('obligation_id')
                or f'repair-{capability}'
            )
            for occurrence in range(1, missing_count + 1):
                branch_seed = _slug(base_identity, f'repair-{capability}')
                branch_id = branch_seed if missing_count == 1 else f'{branch_seed}-{occurrence}'
                if not branch_id.startswith('repair-') and not branch_id.startswith('branch-'):
                    branch_id = f'repair-{branch_id}'
                while branch_id in seen_branch_ids:
                    branch_id = f'{branch_id}-{len(seen_branch_ids) + 1}'
                seen_branch_ids.add(branch_id)
                # Retrying one existing branch does not create a new phase.
                # Fresh/expanded repair identities still own their new phase.
                phase_id = branch_id
                if missing_count == 1 and branch_id == raw_branch_identity:
                    phase_id = str(repair_contract.get('phase_id') or raw_item.get('phase_id') or branch_id).strip()
                if repair_contract and missing_count == 1:
                    # Preserve the originating contract identities and bind
                    # their actual execution identity before scheduling.
                    binding = {
                        'branch_id': branch_id,
                        'phase_id': phase_id,
                        'contract_id': repair_contract.get('contract_id'),
                    }
                    repair_contract['execution_binding'] = binding
                    for promoted_contract in promoted_contracts:
                        if promoted_contract.get('contract_id') == repair_contract.get('contract_id'):
                            promoted_contract['execution_binding'] = dict(binding)
                depends_on = [
                    str(item or '').strip()
                    for item in (raw_item.get('depends_on') or [])
                    if str(item or '').strip()
                ]
                branch_payload = {
                    'branch_id': branch_id,
                    'phase_id': phase_id,
                    'obligation_id': str(raw_item.get('obligation_id') or repair_contract.get('obligation_id') or '').strip() or None,
                    'capability': capability,
                    'output_type': output_type,
                    'role': str(raw_item.get('role') or '').strip() or None,
                    'depends_on': depends_on or None,
                    'repair_scope': str(raw_item.get('repair_scope') or repair_contract.get('repair_scope') or '').strip() or None,
                    'resource_class': str(raw_item.get('resource_class') or repair_contract.get('resource_class') or '').strip() or None,
                    'dependency_policy': str(raw_item.get('dependency_policy') or repair_contract.get('dependency_policy') or '').strip() or None,
                    'runtime_scheduling_context': raw_item.get('runtime_scheduling_context') or repair_contract.get('runtime_scheduling_context'),
                    'allow_gpu_heavy_concurrency': raw_item.get('allow_gpu_heavy_concurrency') or repair_contract.get('allow_gpu_heavy_concurrency'),
                    'status': 'pending',
                    'queue_index': len(existing_branches) + len(pending_branches) + 1,
                    'repair_source': 'inference_repair_feedback',
                    'repair_evidence': str(raw_item.get('evidence') or '').strip() or None,
                    'repair_action': repair_action or None,
                    'recovery_action': repair_action or None,
                    'repair_action_reason': str(raw_item.get('repair_action_reason') or '').strip() or None,
                    'total_missing_count': (
                        raw_item.get('total_missing_count')
                        or repair_contract.get('total_missing_count')
                    ),
                    'repair_occurrence_index': (
                        raw_item.get('repair_occurrence_index')
                        or repair_contract.get('repair_occurrence_index')
                    ),
                    'repair_occurrence_count': (
                        raw_item.get('repair_occurrence_count')
                        or repair_contract.get('repair_occurrence_count')
                    ),
                    'repair_contract': repair_contract or None,
                    'repair_contract_id': str(repair_contract.get('contract_id') or '').strip() or None,
                    'repair_contract_status': str(repair_contract.get('status') or '').strip() or None,
                    'repair_execution_policy': str(repair_contract.get('execution_policy') or '').strip() or None,
                    'repair_promotion_source': str(repair_contract.get('promotion_source') or '').strip() or None,
                    'contract_state': str(repair_contract.get('status') or raw_item.get('contract_state') or '').strip() or None,
                    'promotion_source': str(repair_contract.get('promotion_source') or '').strip() or None,
                }
                execution_policy = str(repair_contract.get('execution_policy') or '').strip()
                if execution_policy == 'blocked_until_dependency_evidence':
                    branch_payload['blocked_by_dependency_input'] = True
                if execution_policy == 'blocked_until_branch_contract':
                    branch_payload['blocked_by_branch_contract'] = True
                if execution_policy == 'blocked_until_promoted_obligation_branch':
                    branch_payload['blocked_by_underplanned_promoted_obligations'] = True
                for key in (
                    'execution_contract',
                    'workload_task_ref',
                    'output_obligation_ref',
                    'output_contract',
                    'input_refs',
                    'review_criteria',
                    'artifact_prompt',
                    'artifact_prompt_source',
                    'batch_prompts',
                    'content_payload',
                    'content_payload_source',
                    'stage_direction',
                    'phase_summary',
                    'repair_scope',
                    'resource_class',
                    'dependency_policy',
                    'runtime_scheduling_context',
                    'allow_gpu_heavy_concurrency',
                    'artifact_request',
                    'requires_artifact',
                    'text_artifact_extension',
                    'text_artifact_source_name',
                    'text_artifact_source',
                    'text_artifact_target_path',
                    'semantic_intent',
                    'objective',
                    'deliverable',
                    'rationale',
                    'advisory_role',
                    'decision_notes',
                    'evidence_requirements',
                    'reconsideration_triggers',
                    'semantic_review_criteria',
                    'promotion_suggestions',
                    'waiver_candidates',
                    'repair_candidates',
                    'supersession_candidates',
                    'learning_hint_refs',
                    'decision_contract_repair_candidates',
                    'decision_contract_semantic_review_candidates',
                    'decision_contract_supersession_candidates',
                    'decision_contract_block_resolution_signals',
                    'decision_contract_active_reconsideration_decisions',
                    'decision_contract_semantic_quality_contracts',
                    'block_resolution_reflex',
                    'block_resolution_signal',
                    'block_resolution_action',
                    'block_resolution_policy',
                    'reconsideration_reflex',
                    'active_reconsideration_review',
                    'active_reconsideration_decision',
                    'active_reconsideration_action',
                    'active_reconsideration_review_type',
                    'semantic_quality_review',
                    'semantic_quality_contract',
                    'semantic_quality_status',
                    'semantic_quality_review_id',
                    'recursive_cycle_review',
                    'recursive_cycle_state',
                    'aspiration_review',
                    'aspiration_frame',
                    'aspiration_frame_id',
                    'aspiration_action',
                    'aspiration_reason',
                    'aspiration_allowed_actions',
                    'decision_contract_aspiration_frames',
                    'commitment_review',
                    'commitment_frame',
                    'commitment_frame_id',
                    'commitment_action',
                    'commitment_recommended_transition',
                    'commitment_reason',
                    'commitment_allowed_transitions',
                    'decision_contract_commitment_frames',
                    'semantic_decision_review',
                    'semantic_decision_proposal',
                    'semantic_decision_action',
                    'semantic_decision_confidence',
                    'semantic_decision_reason',
                    'semantic_review_verdict',
                    'semantic_review_verdict_status',
                    'semantic_review_recommended_transition',
                    'branch_semantic_review',
                    'branch_semantic_review_branch_id',
                    'branch_semantic_review_phase_id',
                    'branch_semantic_review_status',
                    'branch_semantic_review_reason',
                    'branch_semantic_review_source_branch_id',
                    'branch_semantic_review_source_phase_id',
                    'decision_contract_semantic_decision_proposals',
                    'controlled_attention_review',
                    'controlled_attention_frame',
                    'controlled_attention_frame_id',
                    'controlled_attention_scope',
                    'controlled_attention_priority',
                    'controlled_attention_question',
                    'controlled_attention_allowed_transitions',
                    'decision_contract_controlled_attention_frames',
                    'global_semantic_closure_review',
                    'global_semantic_closure_proposal',
                    'global_semantic_closure_status',
                    'global_semantic_closure_reason',
                    'global_semantic_closure_confidence',
                    'surface_state',
                    'supersession_review_required',
                    'supersession_review_authority',
                    'failed_instance_id',
                    'exclude_instance_ids',
                    'blocked_by_dependency_input',
                    'blocked_by_branch_contract',
                    'materialization_blocked',
                    'blocked_scope',
                    'blocked_prerequisite',
                    'repair_work_available',
                    'repair_work_policy',
                    'needs_external_input',
                    'contract_state',
                    'promotion_source',
                ):
                    value = raw_item.get(key)
                    if value not in (None, '', [], {}):
                        branch_payload[key] = value
                for key in (
                    'execution_contract',
                    'workload_task_ref',
                    'output_obligation_ref',
                    'output_contract',
                    'input_refs',
                    'review_criteria',
                    'semantic_review_criteria',
                    'evidence_requirements',
                    'artifact_prompt',
                    'artifact_prompt_source',
                    'batch_prompts',
                    'artifact_request',
                    'requires_artifact',
                    'text_artifact_extension',
                    'text_artifact_source_name',
                    'text_artifact_source',
                    'text_artifact_target_path',
                    'materialization_blocked',
                    'blocked_scope',
                    'blocked_prerequisite',
                    'repair_work_available',
                    'repair_work_policy',
                    'needs_external_input',
                ):
                    value = repair_contract.get(key)
                    if value not in (None, '', [], {}) and branch_payload.get(key) in (None, '', [], {}):
                        branch_payload[key] = value
                for key, value in classify_repair_execution_policy(branch_payload).items():
                    if value in (None, '', [], {}):
                        continue
                    target_key = 'repair_execution_policy' if key == 'execution_policy' else key
                    if branch_payload.get(target_key) in (None, '', [], {}):
                        branch_payload[target_key] = value
                pending_branches.append(_compact_payload(branch_payload))

        if not pending_branches:
            return None

        first_branch = pending_branches[0]
        merged_gap = dict(prior_gap or {})
        merged_pending_branches = [*existing_branches, *pending_branches]
        merged_gap.update(
            {
                'code': str(merged_gap.get('code') or '').strip() or 'closure_review_repair',
                'trigger': str(merged_gap.get('trigger') or '').strip() or 'inference_repair_feedback',
                'expected_capability': (
                    normalize_capability(merged_gap.get('expected_capability'))
                    or first_branch.get('capability')
                ),
                'active_capability': (
                    normalize_capability(merged_gap.get('active_capability'))
                    or normalize_capability(merged_gap.get('expected_capability'))
                    or first_branch.get('capability')
                ),
                'missing_artifact_type': (
                    str(merged_gap.get('missing_artifact_type') or '').strip()
                    or str(first_branch.get('output_type') or '').strip()
                    or None
                ),
                'pending_branches': merged_pending_branches,
                'pending_capabilities': list(
                    dict.fromkeys(
                        [
                            *(
                                str(item).strip()
                                for item in (merged_gap.get('pending_capabilities') or [])
                                if str(item).strip()
                            ),
                            *pending_capabilities,
                        ]
                    )
                ),
                'inference_repair_feedback': feedback,
                'repair_scope': str(feedback.get('patch_scope') or '').strip() or None,
                'repair_mode': str(feedback.get('repair_mode') or '').strip() or None,
                'repair_loop': repair_loop_payload,
                'repair_rebuild_contracts': promoted_contracts or None,
                'reconsideration_rebuild': {
                    'kind': 'fruth.contract_driven_reconsideration_rebuild',
                    'status': 'promoted' if promoted_contracts else 'candidate',
                    'authority': 'closure_review_runtime_truth',
                    'promoted_contract_count': len(promoted_contracts),
                    'pending_branch_count': len(merged_pending_branches),
                    'auto_execute': bool((repair_loop_payload or {}).get('auto_execute')) if isinstance(repair_loop_payload, dict) else False,
                    'repair_work_available': bool((repair_loop_payload or {}).get('repair_work_available')) if isinstance(repair_loop_payload, dict) else False,
                    'repair_work_available_count': (
                        repair_loop_payload.get('repair_work_available_count')
                        if isinstance(repair_loop_payload, dict)
                        else None
                    ),
                    'needs_external_input_count': (
                        repair_loop_payload.get('needs_external_input_count')
                        if isinstance(repair_loop_payload, dict)
                        else None
                    ),
                },
                'repair_action': repair_actions[0] if repair_actions else None,
                'repair_actions': repair_actions or None,
                'preserve_request_id': bool(feedback.get('preserve_request_id')),
            }
        )
        if not str(merged_gap.get('code') or '').strip():
            merged_gap['code'] = 'closure_review_repair'
        if (
            isinstance(prior_gap, dict)
            and prior_gap
            and str(merged_gap.get('code') or '').strip() != 'closure_review_repair'
        ):
            merged_gap['repair_code'] = 'closure_review_repair'
            merged_gap['repair_trigger'] = 'inference_repair_feedback'
        return _compact_payload(merged_gap)

    def _attach_repair_gap_to_request_phase_graph(
        self,
        response_payload: dict[str, Any],
        repair_gap: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(repair_gap, dict) or not repair_gap:
            return response_payload
        pending_branches = [
            dict(item)
            for item in (repair_gap.get('pending_branches') or [])
            if isinstance(item, dict)
        ]
        if not pending_branches:
            return response_payload
        updated = dict(response_payload or {})
        runtime = dict(updated.get('runtime') or {}) if isinstance(updated.get('runtime'), dict) else {}
        graph = (
            dict(runtime.get('request_phase_graph') or {})
            if isinstance(runtime.get('request_phase_graph'), dict)
            else {}
        )
        if not graph:
            return response_payload
        repair_loop = (
            repair_gap.get('repair_loop')
            if isinstance(repair_gap.get('repair_loop'), dict)
            else {}
        )
        reconsideration_rebuild = (
            repair_gap.get('reconsideration_rebuild')
            if isinstance(repair_gap.get('reconsideration_rebuild'), dict)
            else {}
        )
        promotion_status = ''
        if str(repair_loop.get('status') or '').strip().lower() == 'promoted':
            promotion_status = 'promoted'
        elif str(reconsideration_rebuild.get('status') or '').strip().lower() == 'promoted':
            promotion_status = 'promoted'
        graph_repair_proposal = build_graph_repair_proposal_from_repair_gap(
            request_phase_graph=graph,
            repair_gap=repair_gap,
        )
        graph_repair_review = validate_graph_repair_proposal(
            graph_repair_proposal or {},
            request_phase_graph=graph,
            closure_review={
                'status': 'repair_required',
                'inference_repair_feedback': repair_gap.get('inference_repair_feedback'),
                'repair_loop': repair_loop,
                'pending_branches': pending_branches,
            },
            candidate_graph={},
            promotion_review={'status': promotion_status} if promotion_status else {},
        )
        if str(graph_repair_review.get('status') or '').strip().lower() != 'accepted':
            graph_refinements = [
                dict(item)
                for item in (graph.get('graph_refinements') or [])
                if isinstance(item, dict)
            ]
            graph_refinements.append(
                _compact_payload(
                    {
                        'kind': 'graph_repair_proposal_review',
                        'source': 'closure_repair_contract',
                        'status': graph_repair_review.get('status'),
                        'proposal_id': graph_repair_review.get('proposal_id'),
                        'review_id': graph_repair_review.get('review_id'),
                        'reasons': graph_repair_review.get('reasons'),
                    }
                )
            )
            graph['graph_refinements'] = graph_refinements
            graph['graph_repair_reviews'] = [
                *[
                    dict(item)
                    for item in (graph.get('graph_repair_reviews') or [])
                    if isinstance(item, dict)
                ],
                graph_repair_review,
            ]
            runtime['request_phase_graph'] = graph
            developer_diagnostics = (
                dict(runtime.get('developer_diagnostics') or {})
                if isinstance(runtime.get('developer_diagnostics'), dict)
                else {}
            )
            developer_diagnostics['graph_repair_proposal'] = graph_repair_proposal
            developer_diagnostics['graph_repair_proposal_review'] = graph_repair_review
            runtime['developer_diagnostics'] = developer_diagnostics
            updated['runtime'] = runtime
            return updated

        def _branch_id(value: dict[str, Any]) -> str:
            return str(value.get('branch_id') or value.get('phase_id') or '').strip()

        def _phase_id(value: dict[str, Any]) -> str:
            return str(value.get('phase_id') or value.get('branch_id') or '').strip()

        existing_branch_ids = {
            _branch_id(item)
            for item in (graph.get('downstream_branches') or [])
            if isinstance(item, dict) and _branch_id(item)
        }
        downstream_branches = [
            dict(item)
            for item in (graph.get('downstream_branches') or [])
            if isinstance(item, dict)
        ]
        phases = [
            dict(item)
            for item in (graph.get('phases') or [])
            if isinstance(item, dict)
        ]
        existing_phase_ids = {
            str(item.get('phase_id') or '').strip()
            for item in phases
            if str(item.get('phase_id') or '').strip()
        }
        output_obligations = [
            dict(item)
            for item in (graph.get('output_obligations') or [])
            if isinstance(item, dict)
        ]
        existing_obligation_ids = {
            str(item.get('obligation_id') or '').strip()
            for item in output_obligations
            if str(item.get('obligation_id') or '').strip()
        }

        patched_count = 0
        for branch in pending_branches:
            branch_id = _branch_id(branch)
            phase_id = _phase_id(branch) or branch_id
            capability = str(branch.get('capability') or '').strip()
            output_type = str(branch.get('output_type') or self._repair_output_type_for_capability(capability) or '').strip()
            if not branch_id or not capability:
                continue
            graph_branch = _compact_payload(
                {
                    **branch,
                    'branch_id': branch_id,
                    'phase_id': phase_id,
                    'capability': capability,
                    'output_type': output_type or None,
                    'status': str(branch.get('status') or '').strip() or 'pending',
                    'source': 'closure_repair_contract',
                }
            )
            if branch_id not in existing_branch_ids:
                downstream_branches.append(graph_branch)
                existing_branch_ids.add(branch_id)
                patched_count += 1
            if phase_id and phase_id not in existing_phase_ids:
                phases.append(
                    _compact_payload(
                        {
                            'phase_id': phase_id,
                            'branch_id': branch_id,
                            'capability': capability,
                            'output_type': output_type or None,
                            'status': 'pending',
                            'depends_on': branch.get('depends_on'),
                            'required': True,
                            'source': 'closure_repair_contract',
                            'repair_action': branch.get('repair_action'),
                            'repair_contract': branch.get('repair_contract'),
                            'repair_contract_id': branch.get('repair_contract_id'),
                            'repair_execution_policy': branch.get('repair_execution_policy'),
                            'contract_state': branch.get('contract_state') or 'promoted',
                            'promotion_source': branch.get('promotion_source') or 'graph_closure_review',
                            'semantic_intent': branch.get('semantic_intent'),
                            'objective': branch.get('objective'),
                            'deliverable': branch.get('deliverable'),
                            'content_payload': branch.get('content_payload'),
                            'content_payload_source': branch.get('content_payload_source'),
                            'stage_direction': branch.get('stage_direction'),
                            'phase_summary': branch.get('phase_summary'),
                            'input_refs': branch.get('input_refs'),
                            'review_criteria': branch.get('review_criteria'),
                            'semantic_review_criteria': branch.get('semantic_review_criteria'),
                            'semantic_review_verdict': branch.get('semantic_review_verdict'),
                            'semantic_review_verdict_status': branch.get('semantic_review_verdict_status'),
                            'semantic_review_recommended_transition': branch.get('semantic_review_recommended_transition'),
                            'branch_semantic_review': branch.get('branch_semantic_review'),
                            'branch_semantic_review_branch_id': branch.get('branch_semantic_review_branch_id'),
                            'branch_semantic_review_phase_id': branch.get('branch_semantic_review_phase_id'),
                            'branch_semantic_review_status': branch.get('branch_semantic_review_status'),
                            'branch_semantic_review_reason': branch.get('branch_semantic_review_reason'),
                            'branch_semantic_review_source_branch_id': branch.get('branch_semantic_review_source_branch_id'),
                            'branch_semantic_review_source_phase_id': branch.get('branch_semantic_review_source_phase_id'),
                            'global_semantic_closure_review': branch.get('global_semantic_closure_review'),
                            'global_semantic_closure_proposal': branch.get('global_semantic_closure_proposal'),
                        }
                    )
                )
                existing_phase_ids.add(phase_id)
            obligation_id = str(branch.get('obligation_id') or '').strip() or f'obligation-{phase_id}'
            if obligation_id and obligation_id not in existing_obligation_ids and output_type:
                # Graph acceptance alone does not promote a repair. Preserve the
                # runtime contract's existing authority only at its exact sink.
                contract = branch.get('repair_contract')
                contract = contract if isinstance(contract, Mapping) else {}
                binding = contract.get('execution_binding')
                binding = binding if isinstance(binding, Mapping) else {}
                accepted_phases = (graph_repair_review.get('accepted_patch') or {}).get('add_phases') or []
                matching_phases = [
                    item for item in accepted_phases if isinstance(item, Mapping)
                    and (item.get('branch_id') == branch_id
                         or item.get('phase_id') == phase_id
                         or item.get('obligation_id') == obligation_id)
                ]
                promotion = {}
                if (branch.get('contract_state') == contract.get('status') == 'promoted'
                        and contract.get('authority') == 'closure_review_runtime_truth'
                        and branch.get('promotion_source') == contract.get('promotion_source')
                        and contract.get('promotion_source')
                        and branch.get('repair_contract_id') == contract.get('contract_id')
                        and contract.get('contract_id')
                        and binding.get('contract_id') == contract.get('contract_id')
                        and binding.get('branch_id') == branch_id
                        and binding.get('phase_id') == phase_id
                        and contract.get('obligation_id') == obligation_id
                        and contract.get('capability') == capability
                        and contract.get('output_type') == output_type
                        and len(matching_phases) == 1
                        and all(matching_phases[0].get(key) == value for key, value in (
                            ('branch_id', branch_id), ('phase_id', phase_id),
                            ('obligation_id', obligation_id),
                            ('repair_contract_id', contract.get('contract_id'))))):
                    promotion = {
                        'contract_state': branch['contract_state'],
                        'promotion_source': branch['promotion_source'],
                        'graph_repair_proposal_id': graph_repair_review['proposal_id'],
                        'graph_repair_review_id': graph_repair_review['review_id'],
                    }
                output_obligations.append(
                    _compact_payload(
                        {
                            **promotion,
                            'obligation_id': obligation_id,
                            'phase_id': phase_id,
                            'branch_id': branch_id,
                            'capability': capability,
                            'output_type': output_type,
                            'status': 'pending',
                            'required': True,
                            'source': 'closure_repair_contract',
                            'repair_action': branch.get('repair_action'),
                            'repair_contract_id': branch.get('repair_contract_id'),
                            'repair_execution_policy': branch.get('repair_execution_policy'),
                            'depends_on': branch.get('depends_on'),
                            'input_refs': branch.get('input_refs'),
                            'review_criteria': branch.get('review_criteria'),
                            'semantic_review_criteria': branch.get('semantic_review_criteria'),
                            'semantic_review_verdict': branch.get('semantic_review_verdict'),
                            'semantic_review_verdict_status': branch.get('semantic_review_verdict_status'),
                            'semantic_review_recommended_transition': branch.get('semantic_review_recommended_transition'),
                            'branch_semantic_review': branch.get('branch_semantic_review'),
                            'branch_semantic_review_branch_id': branch.get('branch_semantic_review_branch_id'),
                            'branch_semantic_review_phase_id': branch.get('branch_semantic_review_phase_id'),
                            'branch_semantic_review_status': branch.get('branch_semantic_review_status'),
                            'branch_semantic_review_reason': branch.get('branch_semantic_review_reason'),
                            'branch_semantic_review_source_branch_id': branch.get('branch_semantic_review_source_branch_id'),
                            'branch_semantic_review_source_phase_id': branch.get('branch_semantic_review_source_phase_id'),
                            'content_payload_source': branch.get('content_payload_source'),
                            'stage_direction': branch.get('stage_direction'),
                            'global_semantic_closure_status': branch.get('global_semantic_closure_status'),
                        }
                    )
                )
                existing_obligation_ids.add(obligation_id)

        if not patched_count:
            return response_payload
        graph['downstream_branches'] = downstream_branches
        graph['downstream_branch_ids'] = [
            _branch_id(item)
            for item in downstream_branches
            if _branch_id(item)
        ]
        graph['downstream_capabilities'] = list(
            dict.fromkeys(
                str(item.get('capability') or '').strip()
                for item in downstream_branches
                if str(item.get('capability') or '').strip()
            )
        )
        graph['phases'] = phases
        graph['output_obligations'] = output_obligations
        graph['continuation_required'] = True
        graph_refinements = [
            dict(item)
            for item in (graph.get('graph_refinements') or [])
            if isinstance(item, dict)
        ]
        graph_refinements.append(
            {
                'kind': 'closure_repair_graph_patch',
                'source': 'closure_repair_contract',
                'status': 'promoted',
                'graph_repair_proposal_id': graph_repair_review.get('proposal_id'),
                'graph_repair_review_id': graph_repair_review.get('review_id'),
                'graph_repair_review_status': graph_repair_review.get('status'),
                'patched_branch_count': patched_count,
                'repair_action': repair_gap.get('repair_action'),
                'repair_actions': repair_gap.get('repair_actions'),
            }
        )
        graph['graph_refinements'] = graph_refinements
        graph['graph_repair_reviews'] = [
            *[
                dict(item)
                for item in (graph.get('graph_repair_reviews') or [])
                if isinstance(item, dict)
            ],
            graph_repair_review,
        ]
        runtime['request_phase_graph'] = graph
        developer_diagnostics = (
            dict(runtime.get('developer_diagnostics') or {})
            if isinstance(runtime.get('developer_diagnostics'), dict)
            else {}
        )
        developer_diagnostics['graph_repair_proposal'] = graph_repair_proposal
        developer_diagnostics['graph_repair_proposal_review'] = graph_repair_review
        developer_diagnostics['closure_repair_graph_patch'] = graph_refinements[-1]
        runtime['developer_diagnostics'] = developer_diagnostics
        updated['runtime'] = runtime
        return updated

    def project_terminal_closure_repair(
        self,
        response_payload: dict[str, Any],
        *,
        repair_feedback_gap: Callable[..., Optional[dict[str, Any]]],
        attach_repair_gap: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        """Project only new executable terminal Closure work into the graph."""

        if not isinstance(response_payload, dict):
            return {'status': 'not_applicable', 'reason': 'response_payload_invalid'}
        runtime = response_payload.get('runtime') if isinstance(response_payload.get('runtime'), dict) else {}
        closure_review = (
            runtime.get('graph_closure_review')
            if isinstance(runtime.get('graph_closure_review'), dict)
            else {}
        )
        late_fill = response_payload.get('late_fill') if isinstance(response_payload.get('late_fill'), dict) else {}
        repair_gap = repair_feedback_gap(closure_review, prior_gap=None)

        def _repair_identity(item: Mapping[str, Any]) -> tuple[str, str]:
            artifact_request = (
                item.get('artifact_request')
                if isinstance(item.get('artifact_request'), Mapping)
                else {}
            )
            return (
                str(item.get('branch_id') or item.get('phase_id') or '').strip(),
                str(
                    item.get('text_artifact_target_path')
                    or artifact_request.get('target_path')
                    or ''
                ).strip(),
            )

        def _projection_identity(item: Mapping[str, Any]) -> tuple[str, str]:
            branch_id, target_path = _repair_identity(item)
            return ('target', target_path) if target_path else ('branch', branch_id)

        def _promoted_contract_identity(item: Mapping[str, Any]) -> tuple[str, ...]:
            contract_id = str(
                item.get('contract_id') or item.get('repair_contract_id') or ''
            ).strip()
            if contract_id:
                return ('contract', contract_id)
            branch_id, target_path = _repair_identity(item)
            phase_id = str(item.get('phase_id') or '').strip()
            obligation_id = str(item.get('obligation_id') or '').strip()
            if branch_id or phase_id or obligation_id or target_path:
                return (
                    'repair',
                    branch_id,
                    phase_id,
                    obligation_id,
                    target_path,
                )
            return (
                'payload',
                hashlib.sha256(
                    json.dumps(
                        dict(item),
                        ensure_ascii=True,
                        separators=(',', ':'),
                        sort_keys=True,
                        default=str,
                    ).encode('utf-8')
                ).hexdigest(),
            )

        def _terminal_promoted_contract(branch: Mapping[str, Any]) -> dict[str, Any]:
            embedded = (
                dict(branch.get('repair_contract') or {})
                if isinstance(branch.get('repair_contract'), Mapping)
                else {}
            )
            contract_id = str(
                branch.get('repair_contract_id')
                or embedded.get('contract_id')
                or ''
            ).strip()
            contract = {
                **embedded,
                **{
                    key: branch.get(key)
                    for key in (
                        'branch_id',
                        'phase_id',
                        'obligation_id',
                        'capability',
                        'output_type',
                        'repair_action',
                        'content_payload',
                        'content_payload_source',
                        'stage_direction',
                        'requires_artifact',
                        'text_artifact_extension',
                        'text_artifact_source_name',
                        'text_artifact_source',
                        'text_artifact_target_path',
                        'artifact_request',
                    )
                    if branch.get(key) not in (None, '', [], {})
                },
            }
            contract.update(
                {
                    'kind': str(contract.get('kind') or '').strip()
                    or 'fruth.repair_rebuild_contract',
                    'contract_id': contract_id,
                    'status': 'promoted',
                    'authority': str(contract.get('authority') or '').strip()
                    or 'terminal_materialization_contract',
                    'promotion_source': 'terminal_materialization_contract',
                    'execution_policy': str(
                        branch.get('repair_execution_policy')
                        or branch.get('execution_policy')
                        or contract.get('execution_policy')
                        or ''
                    ).strip(),
                    'auto_execute': branch.get('auto_execute') is True,
                    'repair_work_available': (
                        branch.get('repair_work_available') is True
                    ),
                    'materialization_blocked': (
                        branch.get('materialization_blocked') is True
                    ),
                    'needs_external_input': (
                        branch.get('needs_external_input') is True
                    ),
                }
            )
            return _compact_payload(contract)

        current_demoted_identities = {
            _repair_identity(branch)
            for branch in (
                late_fill.get('materialization_contract_current_demoted_branches')
                or []
            )
            if isinstance(branch, Mapping)
            and all(_repair_identity(branch))
        }

        terminal_materialization_branches: list[dict[str, Any]] = []
        for raw_branch in late_fill.get('pending_branches') or []:
            if not isinstance(raw_branch, Mapping):
                continue
            branch = dict(raw_branch)
            if branch.get('materialization_contract_unmet') is not True:
                continue
            identity = _repair_identity(branch)
            if identity not in current_demoted_identities:
                continue
            if (
                str(branch.get('promotion_source') or '').strip()
                == 'terminal_materialization_contract'
            ):
                # Reconsideration/Rebuild permits one bounded repair round.
                # Backend retries inside that round retain their separate
                # auto-executable attempt policy; Closure must not mint an
                # unbounded chain of fresh successor identities.
                continue
            policy = classify_repair_execution_policy(branch)
            if (
                str(policy.get('execution_policy') or '').strip().lower()
                != 'schedule_late_fill_branch'
                or policy.get('auto_execute') is not True
                or policy.get('materialization_blocked') is True
                or policy.get('needs_external_input') is True
            ):
                continue
            owner_branch_id = str(
                branch.get('branch_id') or branch.get('phase_id') or ''
            ).strip()
            repair_fingerprint = hashlib.sha256(
                json.dumps(
                    {
                        'owner_branch_id': owner_branch_id,
                        'target_path': identity[1],
                        'evidence': branch.get('evidence'),
                        'content_payload': branch.get('content_payload'),
                    },
                    ensure_ascii=True,
                    separators=(',', ':'),
                    sort_keys=True,
                ).encode('utf-8')
            ).hexdigest()[:12]
            repair_owner_slug = re.sub(
                r'[^a-z0-9]+',
                '-',
                owner_branch_id.lower(),
            ).strip('-') or 'text-artifact'
            repair_branch_id = (
                f'branch-repair-{repair_owner_slug}-{repair_fingerprint}'
            )
            branch['repair_owner_branch_id'] = owner_branch_id
            branch['repair_owner_phase_id'] = str(
                branch.get('phase_id') or owner_branch_id
            ).strip()
            branch['branch_id'] = repair_branch_id
            branch['phase_id'] = repair_branch_id
            branch['obligation_id'] = f'obligation-{repair_branch_id}'
            branch['repair_contract_id'] = f'repair-contract-{repair_branch_id}'
            branch['contract_state'] = 'promoted'
            branch['promotion_source'] = 'terminal_materialization_contract'
            branch['status'] = 'pending'
            branch.pop('materialization_contract_open_checks', None)
            branch.setdefault(
                'repair_execution_policy',
                policy.get('execution_policy'),
            )
            for key in (
                'auto_execute',
                'materialization_blocked',
                'repair_work_available',
                'needs_external_input',
            ):
                branch.setdefault(key, policy.get(key))
            terminal_materialization_branches.append(branch)

        if terminal_materialization_branches:
            merged_gap = dict(repair_gap or {})
            merged_branches = [
                dict(branch)
                for branch in (merged_gap.get('pending_branches') or [])
                if isinstance(branch, Mapping)
            ]
            branch_index_by_identity = {
                _projection_identity(branch): index
                for index, branch in enumerate(merged_branches)
            }
            promoted_terminal_branches: list[dict[str, Any]] = []
            replaced_contract_bindings: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
            for branch in terminal_materialization_branches:
                identity = _projection_identity(branch)
                existing_index = branch_index_by_identity.get(identity)
                if existing_index is not None:
                    existing_branch = merged_branches[existing_index]
                    existing_branch_id = str(
                        existing_branch.get('branch_id')
                        or existing_branch.get('phase_id')
                        or ''
                    ).strip()
                    owner_branch_id = str(
                        branch.get('repair_owner_branch_id') or ''
                    ).strip()
                    if existing_branch_id and existing_branch_id == owner_branch_id:
                        # Closure can describe a materialization repair with the
                        # already-completed owner phase. Prefer the equivalent
                        # fresh bounded identity or graph projection will
                        # correctly reject the reserved original phase.
                        merged_branches[existing_index] = branch
                        promoted_terminal_branches.append(branch)
                        prior_contract_id = str(existing_branch.get('repair_contract_id') or '').strip()
                        if prior_contract_id:
                            replaced_contract_bindings[prior_contract_id] = (existing_branch, branch)
                    continue
                branch_index_by_identity[identity] = len(merged_branches)
                merged_branches.append(branch)
                promoted_terminal_branches.append(branch)
            pending_capabilities = list(
                dict.fromkeys(
                    str(branch.get('capability') or '').strip()
                    for branch in merged_branches
                    if str(branch.get('capability') or '').strip()
                )
            )
            repair_loop = (
                dict(merged_gap.get('repair_loop') or {})
                if isinstance(merged_gap.get('repair_loop'), Mapping)
                else {}
            )
            promoted_contracts: list[dict[str, Any]] = []
            promoted_contract_identities: set[tuple[str, ...]] = set()
            superseded_contracts = [dict(item) for item in repair_loop.get('superseded_contracts') or []
                                    if isinstance(item, Mapping)]
            for raw_contract in [
                *(repair_loop.get('promoted_contracts') or []),
                *[
                    _terminal_promoted_contract(branch)
                    for branch in promoted_terminal_branches
                ],
            ]:
                if not isinstance(raw_contract, Mapping):
                    continue
                contract = dict(raw_contract)
                replacement = replaced_contract_bindings.get(str(contract.get('contract_id') or ''))
                if replacement is not None:
                    prior_branch, new_branch = replacement
                    binding = contract.get('execution_binding') or {}
                    # Retire only the contract whose executable branch was just
                    # replaced, not another duty sharing its artifact path. The
                    # replacement still has to pass graph admission below and
                    # later prove Closure; this is not a completion receipt.
                    if (binding.get('contract_id') == contract.get('contract_id')
                            and binding.get('branch_id') == prior_branch.get('branch_id')
                            and binding.get('phase_id') == prior_branch.get('phase_id')
                            and _repair_identity(contract)[1] == _repair_identity(new_branch)[1]
                            and _repair_identity(contract)[1]):
                        superseded_contracts.append({
                            **contract, 'status': 'superseded',
                            'supersession_evidence': {
                                'authority': 'terminal_materialization_contract',
                                'reason': 'executable_branch_replaced_by_bounded_terminal_repair',
                                'replacement_contract_id': new_branch.get('repair_contract_id'),
                                'replacement_branch_id': new_branch.get('branch_id'),
                                'replacement_phase_id': new_branch.get('phase_id'),
                                'target_path': _repair_identity(new_branch)[1],
                            },
                        })
                        continue
                identity = _promoted_contract_identity(contract)
                if identity in promoted_contract_identities:
                    continue
                promoted_contract_identities.add(identity)
                promoted_contracts.append(contract)
            executable_contract_count = 0
            for contract in promoted_contracts:
                policy = classify_repair_execution_policy(contract)
                if (
                    str(policy.get('execution_policy') or '').strip().lower()
                    == 'schedule_late_fill_branch'
                    and policy.get('auto_execute') is True
                    and policy.get('materialization_blocked') is not True
                    and policy.get('needs_external_input') is not True
                ):
                    executable_contract_count += 1
            repair_loop.update(
                {
                    'status': 'promoted',
                    'auto_execute': bool(executable_contract_count),
                    'repair_work_available': bool(executable_contract_count),
                    'repair_work_available_count': executable_contract_count,
                    'executable_contract_count': executable_contract_count,
                    'promoted_contract_count': len(promoted_contracts),
                    'promoted_contracts': promoted_contracts,
                }
            )
            if superseded_contracts:
                repair_loop['superseded_contracts'] = superseded_contracts
                repair_loop['superseded_contract_count'] = len(superseded_contracts)
            feedback = dict(merged_gap.get('inference_repair_feedback') or {})
            if feedback:
                replaced_ids = {item.get('contract_id') for item in superseded_contracts}
                feedback['items'] = [item for item in feedback.get('items') or []
                                     if not isinstance(item, Mapping)
                                     or (item.get('repair_contract_id')
                                         or (item.get('repair_contract') or {}).get('contract_id')) not in replaced_ids]
                feedback['repair_rebuild_contracts'] = promoted_contracts
                feedback['repair_loop'] = dict(repair_loop)
                merged_gap['inference_repair_feedback'] = feedback
            merged_gap.update(
                {
                    'code': str(merged_gap.get('code') or '').strip()
                    or 'closure_review_repair',
                    'trigger': str(merged_gap.get('trigger') or '').strip()
                    or 'terminal_materialization_contract',
                    'pending_branches': merged_branches,
                    'pending_capabilities': pending_capabilities,
                    'expected_capability': (
                        merged_gap.get('expected_capability')
                        or (pending_capabilities[0] if pending_capabilities else None)
                    ),
                    'repair_loop': repair_loop,
                    'repair_rebuild_contracts': promoted_contracts,
                    'reconsideration_rebuild': {
                        **(merged_gap.get('reconsideration_rebuild') or {}),
                        'status': 'promoted',
                        'auto_execute': bool(executable_contract_count),
                        'repair_work_available': bool(executable_contract_count),
                        'repair_work_available_count': executable_contract_count,
                        'promoted_contract_count': len(promoted_contracts),
                        'pending_branch_count': len(merged_branches),
                    },
                }
            )
            repair_gap = merged_gap

        if not isinstance(repair_gap, dict) or not repair_gap:
            return {'status': 'not_applicable', 'reason': 'no_terminal_closure_repair_gap'}
        completed_contracts_by_branch: dict[str, set[str]] = {}
        completed_without_contract: set[str] = set()
        for record in late_fill.get('completed_branches') or []:
            if isinstance(record, Mapping):
                branch_id = str(record.get('branch_id') or record.get('phase_id') or '').strip()
                contract_id = str(record.get('repair_contract_id') or '').strip()
            else:
                branch_id = str(record or '').strip()
                contract_id = ''
            if not branch_id:
                continue
            if contract_id:
                completed_contracts_by_branch.setdefault(branch_id, set()).add(contract_id)
            else:
                completed_without_contract.add(branch_id)
        exhausted_contracts_by_branch: dict[str, set[str]] = {}
        exhausted_without_contract: set[str] = set()
        for key in ('failed_branches', 'cancelled_branches'):
            for record in late_fill.get(key) or []:
                if isinstance(record, Mapping):
                    branch_id = str(record.get('branch_id') or record.get('phase_id') or '').strip()
                    contract_id = str(record.get('repair_contract_id') or '').strip()
                else:
                    branch_id = str(record or '').strip()
                    contract_id = ''
                if not branch_id:
                    continue
                if contract_id:
                    exhausted_contracts_by_branch.setdefault(branch_id, set()).add(contract_id)
                else:
                    exhausted_without_contract.add(branch_id)

        executable_branches: list[dict[str, Any]] = []
        seen_branch_ids: set[str] = set()
        for record in repair_gap.get('pending_branches') or []:
            if not isinstance(record, dict):
                continue
            branch = dict(record)
            branch_id = str(branch.get('branch_id') or branch.get('phase_id') or '').strip()
            contract_id = str(branch.get('repair_contract_id') or '').strip()
            completed_contract_ids = completed_contracts_by_branch.get(branch_id, set())
            contract_already_completed = (
                branch_id in completed_without_contract
                or (bool(contract_id) and contract_id in completed_contract_ids)
                or (not contract_id and bool(completed_contract_ids))
            )
            exhausted_contract_ids = exhausted_contracts_by_branch.get(branch_id, set())
            contract_attempt_exhausted = (
                branch_id in exhausted_without_contract
                or (bool(contract_id) and contract_id in exhausted_contract_ids)
                or (not contract_id and bool(exhausted_contract_ids))
            )
            if (
                not branch_id
                or contract_already_completed
                or contract_attempt_exhausted
                or branch_id in seen_branch_ids
            ):
                continue
            policy_input = dict(branch)
            execution_policy = str(
                policy_input.get('repair_execution_policy')
                or policy_input.get('execution_policy')
                or ''
            ).strip().lower()
            if execution_policy and not policy_input.get('execution_policy'):
                policy_input['execution_policy'] = execution_policy
            policy = classify_repair_execution_policy(policy_input)
            if (
                str(policy.get('execution_policy') or '').strip().lower()
                != 'schedule_late_fill_branch'
                or policy.get('auto_execute') is not True
                or policy.get('materialization_blocked') is True
                or policy.get('needs_external_input') is True
            ):
                continue
            seen_branch_ids.add(branch_id)
            executable_branches.append(branch)

        if not executable_branches:
            return {
                'status': 'not_applicable',
                'reason': 'no_new_executable_terminal_closure_contract',
            }

        pending_capabilities = list(
            dict.fromkeys(
                str(branch.get('capability') or '').strip().lower()
                for branch in executable_branches
                if str(branch.get('capability') or '').strip()
            )
        )
        repair_gap = dict(repair_gap)
        repair_gap.update(
            {
                'pending_branches': executable_branches,
                'pending_capabilities': pending_capabilities,
                'expected_capability': pending_capabilities[0] if pending_capabilities else None,
                'active_capability': pending_capabilities[0] if pending_capabilities else None,
                'authoritative_pending_branches': True,
                'pending_branch_scope': 'exact_terminal_closure_repair',
            }
        )
        updated = attach_repair_gap(response_payload, repair_gap)
        updated_runtime = updated.get('runtime') if isinstance(updated.get('runtime'), dict) else {}
        updated_graph = (
            updated_runtime.get('request_phase_graph')
            if isinstance(updated_runtime.get('request_phase_graph'), dict)
            else {}
        )
        graph_branch_ids = {
            str(item.get('branch_id') or item.get('phase_id') or '').strip()
            for item in updated_graph.get('downstream_branches') or []
            if isinstance(item, Mapping)
        }
        if not seen_branch_ids.issubset(graph_branch_ids):
            return {
                'status': 'blocked',
                'reason': 'terminal_closure_repair_graph_projection_rejected',
                'response_payload': updated,
            }
        return {
            'status': 'queued',
            'response_payload': updated,
            'artifact_gap': _compact_payload(repair_gap),
            'branch_ids': sorted(seen_branch_ids),
        }

