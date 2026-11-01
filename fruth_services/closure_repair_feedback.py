"""Closure check classification and bounded repair feedback.

Produces candidate repair records from existing checks and accepted obligations.
Validation, promotion, retry budgets and execution remain separate caller gates.
"""

from __future__ import annotations

from fruth_services import intent_coverage
import re
from typing import Any, Mapping, Optional
from helpers.model_capabilities import (
    CAPABILITY_CHAT,
    CAPABILITY_IMAGE_GENERATION,
    CAPABILITY_TEXT_TO_SPEECH,
    normalize_capability,
)
from fruth_inference.phase_graph_queries import current_phase_capability
from fruth_server.recovery_contract import (
    RECOVERY_ACTION_MANUAL_REVIEW,
    RECOVERY_ACTION_REBIND_DEPENDENCY_EVIDENCE,
    RECOVERY_ACTION_REBUILD_FROM_PROMOTED_OBLIGATIONS,
    RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT,
    RECOVERY_ACTION_REPAIR_DEPENDENCY_CHAIN,
    RECOVERY_ACTION_RETRY_EXCLUDING_INSTANCE,
    RECOVERY_ACTION_RETRY_SAME_BRANCH,
    RECOVERY_ACTION_SEMANTIC_REVIEW,
    RECOVERY_ACTION_START_COMPATIBLE_INSTANCE,
    normalize_recovery_suggested_action,
)
from fruth_server.repair_gate_runtime import (
    classify_repair_execution_policy,
    repair_item_has_concrete_input_evidence,
)


_CLOSURE_REPAIR_PAYLOAD_KEYS = (
    'execution_contract',
    'workload_task_ref',
    'output_obligation_ref',
    'output_contract',
    'input_refs',
    'review_criteria',
    'artifact_prompt',
    'artifact_prompt_source',
    'batch_prompts',
    'batch_prompts_source',
    'batch_prompt_source_phase_id',
    'batch_prompt_expected_count',
    'artifact_request',
    'accepted_proposals',
    'requires_artifact',
    'text_artifact_extension',
    'text_artifact_source_name',
    'text_artifact_source',
    'text_artifact_target_path',
    'repair_scope',
    'resource_class',
    'dependency_policy',
    'runtime_scheduling_context',
    'allow_gpu_heavy_concurrency',
    'semantic_intent',
    'objective',
    'deliverable',
    'rationale',
    'advisory_role',
    'decision_notes',
    'evidence_requirements',
    'reconsideration_triggers',
    'semantic_review_criteria',
    'semantic_review_lens',
    'success_definition',
    'failure_modes',
    'semantic_lens_evidence_requirements',
    'semantic_review_lens_contract',
    'semantic_review_lens_review',
    'decision_contract_semantic_review_lenses',
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
    'semantic_review_evidence_binding',
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
    'content_payload',
    'content_payload_source',
    'stage_direction',
    'phase_summary',
    'surface_state',
    'repair_contract',
    'repair_contract_id',
    'repair_contract_status',
    'repair_execution_policy',
    'repair_promotion_source',
    'contract_state',
    'promotion_source',
    'supersession_review_required',
    'supersession_review_authority',
    'superseded_by',
    'superseded_by_candidate_id',
    'superseded_by_obligation_id',
    'supersession_reason',
)


def _explicit_recovery_action_from_payload(payload: Mapping[str, Any]) -> Optional[str]:
    for source_key in (
        'repair_action',
        'recovery_action',
        'suggested_action',
        'suggestedAction',
    ):
        action = str(payload.get(source_key) or '').strip()
        if action:
            return normalize_recovery_suggested_action(action)
    for container_key in ('recovery_state', 'recovery_context'):
        container = payload.get(container_key)
        if isinstance(container, Mapping):
            action = _explicit_recovery_action_from_payload(container)
            if action:
                return action
    return None


def _closure_check_recovery_action(check: Mapping[str, Any]) -> tuple[Optional[str], Optional[str]]:
    explicit_action = _explicit_recovery_action_from_payload(check)
    if explicit_action:
        return explicit_action, 'explicit recovery action carried by runtime branch state'

    status = str(check.get('status') or '').strip().lower()
    check_kind = str(check.get('check_kind') or '').strip().lower()
    evidence = str(check.get('evidence') or '').strip().lower()
    capability = normalize_capability(check.get('capability'))
    depends_on = [
        str(item or '').strip()
        for item in (check.get('depends_on') or [])
        if str(item or '').strip()
    ] if isinstance(check.get('depends_on'), list) else []

    if check_kind == 'intent_graph_adequacy' or evidence.startswith('intent_graph_adequacy_'):
        return (
            RECOVERY_ACTION_REBUILD_FROM_PROMOTED_OBLIGATIONS,
            'request graph does not contain enough promoted obligations for the current intent',
        )
    if evidence == 'runtime_capability_unavailable':
        return (
            RECOVERY_ACTION_START_COMPATIBLE_INSTANCE,
            'required capability is not currently available in runtime',
        )
    if (
        check.get('blocked_by_dependency_input') is True
        or 'dependency' in evidence
        or (
            status == 'blocked'
            and depends_on
            and evidence in {'late_fill_failed_branch', 'late_fill_failed_capability'}
        )
    ):
        if _repair_item_has_concrete_input_evidence(check):
            return (
                RECOVERY_ACTION_REBIND_DEPENDENCY_EVIDENCE,
                'branch has concrete dependency evidence that can be rebound to resolve the block',
            )
        return (
            RECOVERY_ACTION_REPAIR_DEPENDENCY_CHAIN,
            'branch is blocked by missing or failed dependency evidence',
        )
    if status == 'blocked' and evidence in {'late_fill_failed_branch', 'late_fill_failed_capability'}:
        if check.get('failed_instance_id') or check.get('exclude_instance_ids'):
            return (
                RECOVERY_ACTION_RETRY_EXCLUDING_INSTANCE,
                'branch failed after selecting a concrete runtime instance',
            )
        return (
            RECOVERY_ACTION_RETRY_SAME_BRANCH,
            'branch failed without dependency evidence; retry the same bounded branch',
        )
    if (
        check.get('blocked_by_branch_contract') is True
        or (
            status in {'pending', 'planned', 'active', 'deferred', 'blocked'}
            and capability
            and capability != CAPABILITY_CHAT
            and not isinstance(check.get('execution_contract'), Mapping)
            and not check.get('branch_id')
        )
    ):
        return (
            RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT,
            'branch has material work but lacks a bounded executable branch contract',
        )
    if check_kind in {'truth_guard', 'truth_guard_capability'}:
        return (
            RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT,
            'runtime truth detected an unmaterialized output claim that needs a promoted branch contract',
        )
    if (
        check.get('semantic_review_required') is True
        and status in {'pending', 'blocked'}
    ):
        return (
            RECOVERY_ACTION_SEMANTIC_REVIEW,
            'branch has qualitative review criteria that need semantic evaluation before freeze',
        )
    if status == 'blocked':
        return RECOVERY_ACTION_MANUAL_REVIEW, 'blocked branch has no safe automatic repair path'
    return None, None


def _decision_contract_from_graph(request_phase_graph: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(request_phase_graph, Mapping):
        return {}
    direct = request_phase_graph.get('decision_contract')
    if isinstance(direct, Mapping) and direct:
        return dict(direct)
    request_ir = (
        request_phase_graph.get('request_ir')
        if isinstance(request_phase_graph.get('request_ir'), Mapping)
        else {}
    )
    nested = request_ir.get('decision_contract') if isinstance(request_ir, Mapping) else {}
    if isinstance(nested, Mapping) and nested:
        return dict(nested)
    return {}


def _decision_contract_guidance_payload(decision_contract: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(decision_contract, Mapping) or not decision_contract:
        return {}
    payload = {
        'kind': 'fruth.decision_contract_repair_guidance',
        'authority': 'advisory_until_matched_to_open_closure_check',
        'next_decision_priorities': decision_contract.get('next_decision_priorities'),
        'reconsideration_candidates': decision_contract.get('reconsideration_candidates'),
        'promotion_suggestions': decision_contract.get('promotion_suggestions'),
        'waiver_candidates': decision_contract.get('waiver_candidates'),
        'supersession_records': decision_contract.get('supersession_records'),
        'block_resolution_reflex': decision_contract.get('block_resolution_reflex'),
        'reconsideration_reflex_signals': decision_contract.get('reconsideration_reflex_signals'),
        'active_reconsideration_review': decision_contract.get('active_reconsideration_review'),
        'active_reconsideration_decisions': decision_contract.get('active_reconsideration_decisions'),
        'semantic_quality_review': decision_contract.get('semantic_quality_review'),
        'semantic_quality_contracts': decision_contract.get('semantic_quality_contracts'),
        'recursive_cycle_review': decision_contract.get('recursive_cycle_review'),
        'recursive_cycle_tasks': decision_contract.get('recursive_cycle_tasks'),
        'aspiration_review': decision_contract.get('aspiration_review'),
        'aspiration_frames': decision_contract.get('aspiration_frames'),
        'commitment_review': decision_contract.get('commitment_review'),
        'commitment_frames': decision_contract.get('commitment_frames'),
        'semantic_decision_review': decision_contract.get('semantic_decision_review'),
        'semantic_decision_proposals': decision_contract.get('semantic_decision_proposals'),
        'controlled_attention_review': decision_contract.get('controlled_attention_review'),
        'controlled_attention_frames': decision_contract.get('controlled_attention_frames'),
        'semantic_review_lens_review': decision_contract.get('semantic_review_lens_review'),
        'semantic_review_lenses': decision_contract.get('semantic_review_lenses'),
        'semantic_planning_contract': decision_contract.get('semantic_planning_contract'),
        'workload_proposal_coverage': decision_contract.get('workload_proposal_coverage'),
    }
    accepted_learning = decision_contract.get('accepted_learning')
    if isinstance(accepted_learning, Mapping):
        payload['accepted_learning'] = {
            key: accepted_learning.get(key)
            for key in ('status', 'authority', 'runtime_effect', 'hint_count', 'allowed_use')
            if accepted_learning.get(key) not in (None, '', [], {})
        }
    return intent_coverage._compact_mapping(payload)


def _repair_contract_id(item: Mapping[str, Any], *, index: int) -> str:
    raw_identity = (
        item.get('branch_id')
        or item.get('phase_id')
        or item.get('obligation_id')
        or item.get('task_id')
        or item.get('capability')
        or f'item-{index}'
    )
    token = re.sub(r'[^a-z0-9_]+', '-', str(raw_identity or '').strip().lower())
    token = re.sub(r'-+', '-', token).strip('-') or f'item-{index}'
    return f'repair-contract-{token}'


def _repair_item_has_concrete_input_evidence(item: Mapping[str, Any]) -> bool:
    return repair_item_has_concrete_input_evidence(item)


def _repair_contract_execution_policy(item: Mapping[str, Any]) -> tuple[str, bool]:
    policy = classify_repair_execution_policy(item)
    return (
        str(policy.get('execution_policy') or 'manual_review_required'),
        bool(policy.get('auto_execute')),
    )


def _repair_contract_resolution_state(
    item: Mapping[str, Any],
    *,
    execution_policy: str,
    auto_execute: bool,
) -> dict[str, Any]:
    policy = classify_repair_execution_policy(item)
    return {
        key: value
        for key, value in policy.items()
        if key not in {'execution_policy', 'auto_execute'}
    }


def _expand_counted_repair_items(repair_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    for item in repair_items:
        if not isinstance(item, Mapping):
            continue
        try:
            missing_count = int(item.get('missing_count') or 1)
        except (TypeError, ValueError):
            missing_count = 1
        missing_count = max(1, missing_count)
        action = normalize_recovery_suggested_action(
            item.get('repair_action') or item.get('recovery_action')
        )
        should_expand = bool(
            missing_count > 1
            and str(item.get('check_kind') or '').strip() == 'intent_graph_adequacy'
            and action == RECOVERY_ACTION_REBUILD_FROM_PROMOTED_OBLIGATIONS
            and normalize_capability(item.get('capability'))
            and str(item.get('output_type') or '').strip().lower() in {'audio', 'image'}
        )
        if not should_expand:
            expanded.append(dict(item))
            continue

        parent_obligation_id = str(item.get('obligation_id') or '').strip() or None
        raw_identity = str(
            item.get('branch_id')
            or item.get('phase_id')
            or parent_obligation_id
            or item.get('output_type')
            or 'material-output'
        ).strip()
        identity = re.sub(r'[^a-z0-9_]+', '-', raw_identity.lower())
        identity = re.sub(r'-+', '-', identity).strip('-') or 'material-output'
        if not identity.startswith('repair-'):
            identity = f'repair-{identity}'
        for occurrence in range(1, missing_count + 1):
            branch_id = f'{identity}-{occurrence}'
            occurrence_item = dict(item)
            occurrence_item.update(
                {
                    'branch_id': branch_id,
                    'phase_id': branch_id,
                    'missing_count': 1,
                    'total_missing_count': missing_count,
                    'repair_occurrence_index': occurrence,
                    'repair_occurrence_count': missing_count,
                }
            )
            if parent_obligation_id:
                occurrence_item['parent_obligation_id'] = parent_obligation_id
            expanded.append(occurrence_item)
    return expanded


def _repair_rebuild_contracts(repair_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    contracts: list[dict[str, Any]] = []
    for index, item in enumerate(repair_items, start=1):
        if not isinstance(item, Mapping):
            continue
        action = normalize_recovery_suggested_action(item.get('repair_action') or item.get('recovery_action'))
        execution_policy, auto_execute = _repair_contract_execution_policy(item)
        resolution_state = _repair_contract_resolution_state(
            item,
            execution_policy=execution_policy,
            auto_execute=auto_execute,
        )
        contract = {
            'kind': 'fruth.repair_rebuild_contract',
            'contract_id': _repair_contract_id(item, index=index),
            'status': 'promoted',
            'authority': 'closure_review_runtime_truth',
            'promotion_source': 'graph_closure_review',
            'promotion_reason': str(item.get('repair_action_reason') or item.get('reason') or '').strip()
            or 'Closure Review found open promoted work that needs repair or rebuild',
            'repair_action': action,
            'execution_policy': execution_policy,
            'auto_execute': auto_execute,
            **resolution_state,
            'check_kind': item.get('check_kind'),
            'task_id': item.get('task_id') or item.get('workload_task_id'),
            'phase_id': item.get('phase_id'),
            'branch_id': item.get('branch_id'),
            'obligation_id': item.get('obligation_id'),
            'parent_obligation_id': item.get('parent_obligation_id'),
            'capability': normalize_capability(item.get('capability')),
            'output_type': str(item.get('output_type') or '').strip() or None,
            'missing_count': item.get('missing_count'),
            'total_missing_count': item.get('total_missing_count'),
            'repair_occurrence_index': item.get('repair_occurrence_index'),
            'repair_occurrence_count': item.get('repair_occurrence_count'),
            'depends_on': item.get('depends_on'),
            'repair_scope': item.get('repair_scope'),
            'resource_class': item.get('resource_class'),
            'dependency_policy': item.get('dependency_policy'),
            'runtime_scheduling_context': item.get('runtime_scheduling_context'),
            'allow_gpu_heavy_concurrency': item.get('allow_gpu_heavy_concurrency'),
            'execution_contract': item.get('execution_contract'),
            'workload_task_ref': item.get('workload_task_ref'),
            'output_obligation_ref': item.get('output_obligation_ref'),
            'output_contract': item.get('output_contract'),
            'input_refs': item.get('input_refs'),
            'review_criteria': item.get('review_criteria'),
            'semantic_review_criteria': item.get('semantic_review_criteria'),
            'semantic_review_verdict': item.get('semantic_review_verdict'),
            'semantic_review_verdict_status': item.get('semantic_review_verdict_status'),
            'semantic_review_recommended_transition': item.get('semantic_review_recommended_transition'),
            'branch_semantic_review': item.get('branch_semantic_review'),
            'branch_semantic_review_branch_id': item.get('branch_semantic_review_branch_id'),
            'branch_semantic_review_phase_id': item.get('branch_semantic_review_phase_id'),
            'branch_semantic_review_status': item.get('branch_semantic_review_status'),
            'branch_semantic_review_reason': item.get('branch_semantic_review_reason'),
            'branch_semantic_review_source_branch_id': item.get('branch_semantic_review_source_branch_id'),
            'branch_semantic_review_source_phase_id': item.get('branch_semantic_review_source_phase_id'),
            'evidence_requirements': item.get('evidence_requirements'),
            'content_payload': item.get('content_payload'),
            'content_payload_source': item.get('content_payload_source'),
            'artifact_prompt': item.get('artifact_prompt'),
            'artifact_prompt_source': item.get('artifact_prompt_source'),
            'batch_prompts': item.get('batch_prompts'),
            'artifact_request': item.get('artifact_request'),
            'requires_artifact': item.get('requires_artifact'),
            'text_artifact_extension': item.get('text_artifact_extension'),
            'text_artifact_source_name': item.get('text_artifact_source_name'),
            'text_artifact_source': item.get('text_artifact_source'),
            'stage_direction': item.get('stage_direction'),
            'global_semantic_closure_review': item.get('global_semantic_closure_review'),
            'global_semantic_closure_proposal': item.get('global_semantic_closure_proposal'),
            'global_semantic_closure_status': item.get('global_semantic_closure_status'),
            'global_semantic_closure_reason': item.get('global_semantic_closure_reason'),
            'global_semantic_closure_confidence': item.get('global_semantic_closure_confidence'),
            'aspiration_review': item.get('aspiration_review'),
            'aspiration_frame': item.get('aspiration_frame'),
            'aspiration_frame_id': item.get('aspiration_frame_id'),
            'aspiration_action': item.get('aspiration_action'),
            'aspiration_reason': item.get('aspiration_reason'),
            'aspiration_allowed_actions': item.get('aspiration_allowed_actions'),
            'commitment_review': item.get('commitment_review'),
            'commitment_frame': item.get('commitment_frame'),
            'commitment_frame_id': item.get('commitment_frame_id'),
            'commitment_action': item.get('commitment_action'),
            'commitment_recommended_transition': item.get('commitment_recommended_transition'),
            'commitment_reason': item.get('commitment_reason'),
            'commitment_allowed_transitions': item.get('commitment_allowed_transitions'),
            'controlled_attention_review': item.get('controlled_attention_review'),
            'controlled_attention_frame': item.get('controlled_attention_frame'),
            'controlled_attention_frame_id': item.get('controlled_attention_frame_id'),
            'controlled_attention_scope': item.get('controlled_attention_scope'),
            'controlled_attention_priority': item.get('controlled_attention_priority'),
            'controlled_attention_question': item.get('controlled_attention_question'),
            'controlled_attention_allowed_transitions': item.get('controlled_attention_allowed_transitions'),
        }
        contracts.append(intent_coverage._compact_mapping(contract))
    return contracts


def build_inference_repair_feedback(
    *,
    review_status: str,
    reason: str,
    checks: list[dict[str, Any]],
    request_phase_graph: Mapping[str, Any],
) -> Optional[dict[str, Any]]:
    if review_status not in {'pending', 'blocked'}:
        return None
    current_phase_id = str(request_phase_graph.get('current_phase_id') or '').strip()
    current_phase_capability = normalize_capability(request_phase_graph.get('current_phase_capability'))
    decision_contract = _decision_contract_from_graph(request_phase_graph)
    decision_contract_guidance = _decision_contract_guidance_payload(decision_contract)
    graph_intent = (
        request_phase_graph.get('prompt_intent')
        if isinstance(request_phase_graph.get('prompt_intent'), Mapping)
        else {}
    )
    downstream_capabilities = {
        normalize_capability(item)
        for item in (graph_intent.get('downstream_follow_up_capabilities') or [])
        if normalize_capability(item)
    }
    graph_records: list[Mapping[str, Any]] = []
    for key in ('downstream_branches', 'phases', 'output_obligations'):
        records = request_phase_graph.get(key)
        if isinstance(records, list):
            graph_records.extend(item for item in records if isinstance(item, Mapping))

    def _normalized_depends_on(raw_value: Any) -> list[str]:
        if not isinstance(raw_value, list):
            return []
        return [
            str(item or '').strip()
            for item in raw_value
            if str(item or '').strip()
        ]

    def _exemplar_depends_on(capability: Optional[str]) -> list[str]:
        normalized_capability = normalize_capability(capability)
        if not normalized_capability:
            return []
        for record in graph_records:
            if normalize_capability(record.get('capability')) != normalized_capability:
                continue
            depends_on = _normalized_depends_on(record.get('depends_on'))
            if depends_on:
                return depends_on
        return []

    def _inferred_repair_depends_on(capability: Optional[str]) -> list[str]:
        normalized_capability = normalize_capability(capability)
        exemplar = _exemplar_depends_on(normalized_capability)
        if exemplar:
            return exemplar
        if not current_phase_id or current_phase_capability != CAPABILITY_CHAT:
            return []
        if normalized_capability == CAPABILITY_IMAGE_GENERATION and (
            graph_intent.get('text_preparation_before_visual_output')
            or CAPABILITY_IMAGE_GENERATION in downstream_capabilities
        ):
            return [current_phase_id]
        if normalized_capability == CAPABILITY_TEXT_TO_SPEECH and (
            graph_intent.get('text_preparation_before_audio_output')
            or CAPABILITY_TEXT_TO_SPEECH in downstream_capabilities
        ):
            return [current_phase_id]
        return []

    def _repair_check_uses_target_artifact_snapshot_only(raw_check: Mapping[str, Any]) -> bool:
        context = (
            raw_check.get('runtime_scheduling_context')
            if isinstance(raw_check.get('runtime_scheduling_context'), Mapping)
            else {}
        )
        dependency_policy = str(
            raw_check.get('dependency_policy')
            or context.get('dependency_policy')
            or ''
        ).strip().lower()
        if dependency_policy == 'target_artifact_snapshot_only':
            return True
        repair_scope = str(
            raw_check.get('repair_scope')
            or context.get('repair_scope')
            or ''
        ).strip().lower()
        resource_class = str(
            raw_check.get('resource_class')
            or context.get('resource_class')
            or ''
        ).strip().lower()
        if repair_scope in {'syntax_only', 'text_artifact_syntax'} and resource_class in {'text_io', 'local_text_io'}:
            return True
        check_kind = str(raw_check.get('check_kind') or '').strip()
        payload_source = str(raw_check.get('content_payload_source') or '').strip()
        artifact_request = (
            raw_check.get('artifact_request')
            if isinstance(raw_check.get('artifact_request'), Mapping)
            else {}
        )
        target_path = str(
            raw_check.get('text_artifact_target_path')
            or artifact_request.get('target_path')
            or ''
        ).strip()
        return bool(
            target_path
            and (
                check_kind == 'text_artifact_syntax_sanity'
                or payload_source == 'closure_text_artifact_syntax_sanity'
            )
        )

    repair_items: list[dict[str, Any]] = []
    for raw_check in checks:
        if not isinstance(raw_check, Mapping):
            continue
        status = str(raw_check.get('status') or '').strip().lower()
        if status not in {'pending', 'planned', 'active', 'deferred', 'blocked'}:
            continue
        capability = normalize_capability(raw_check.get('capability'))
        repair_action, repair_action_reason = _closure_check_recovery_action(raw_check)
        if capability == CAPABILITY_CHAT and not repair_action:
            capability = None
        check_kind = str(raw_check.get('check_kind') or '').strip()
        if not capability and check_kind not in {'truth_guard', 'intent_graph_adequacy'} and not repair_action:
            continue
        depends_on = _normalized_depends_on(raw_check.get('depends_on'))
        if not depends_on and not _repair_check_uses_target_artifact_snapshot_only(raw_check):
            depends_on = _inferred_repair_depends_on(capability)
        repair_item = {
            'check_kind': check_kind or 'graph_obligation',
            'status': status,
            'capability': capability,
            'output_type': str(raw_check.get('output_type') or '').strip() or None,
            'role': str(raw_check.get('role') or '').strip() or None,
            'depends_on': depends_on or None,
            'missing_count': raw_check.get('missing_count'),
            'evidence': str(raw_check.get('evidence') or '').strip() or None,
            'reason': str(raw_check.get('reason') or '').strip() or None,
            'obligation_id': str(raw_check.get('obligation_id') or '').strip() or None,
            'phase_id': str(raw_check.get('phase_id') or '').strip() or None,
            'branch_id': str(raw_check.get('branch_id') or '').strip() or None,
            'repair_action': repair_action,
            'recovery_action': repair_action,
            'repair_action_reason': repair_action_reason,
        }
        for key in _CLOSURE_REPAIR_PAYLOAD_KEYS:
            value = raw_check.get(key)
            if value not in (None, '', [], {}):
                repair_item[key] = value
        for key in (
            'failed_instance_id',
            'exclude_instance_ids',
            'blocked_by_dependency_input',
            'blocked_by_branch_contract',
        ):
            value = raw_check.get(key)
            if value not in (None, '', [], {}):
                repair_item[key] = value
        repair_items.append(
            {
                key: value
                for key, value in repair_item.items()
                if value not in (None, '', [], {})
            }
        )
    if not repair_items:
        return None
    repair_items = _expand_counted_repair_items(repair_items)
    next_actions: list[str] = []
    for item in repair_items:
        raw_action = str(item.get('repair_action') or '').strip()
        if not raw_action:
            continue
        action = normalize_recovery_suggested_action(raw_action)
        if action not in next_actions:
            next_actions.append(action)
    if not next_actions:
        next_actions.append(RECOVERY_ACTION_MANUAL_REVIEW)
    repair_contracts = _repair_rebuild_contracts(repair_items)
    contracts_by_identity = {
        str(
            contract.get('branch_id')
            or contract.get('phase_id')
            or contract.get('obligation_id')
            or contract.get('task_id')
            or contract.get('contract_id')
            or ''
        ).strip(): contract
        for contract in repair_contracts
        if str(
            contract.get('branch_id')
            or contract.get('phase_id')
            or contract.get('obligation_id')
            or contract.get('task_id')
            or contract.get('contract_id')
            or ''
        ).strip()
    }
    for item in repair_items:
        identity = str(
            item.get('branch_id')
            or item.get('phase_id')
            or item.get('obligation_id')
            or item.get('task_id')
            or ''
        ).strip()
        contract = contracts_by_identity.get(identity)
        if contract:
            item['repair_contract'] = contract
            item['repair_contract_id'] = contract.get('contract_id')
            item['repair_execution_policy'] = contract.get('execution_policy')
            item['repair_promotion_source'] = contract.get('promotion_source')
            item['contract_state'] = 'promoted'
            for key in (
                'materialization_blocked',
                'blocked_scope',
                'blocked_prerequisite',
                'repair_work_available',
                'repair_work_policy',
                'needs_external_input',
            ):
                value = contract.get(key)
                if value not in (None, '', [], {}):
                    item[key] = value
    executable_contract_count = sum(1 for item in repair_contracts if item.get('auto_execute') is True)
    blocked_contract_count = sum(1 for item in repair_contracts if item.get('auto_execute') is not True)
    repair_work_available_count = sum(1 for item in repair_contracts if item.get('repair_work_available') is True)
    needs_external_input_count = sum(1 for item in repair_contracts if item.get('needs_external_input') is True)
    repair_loop_status = 'promoted' if repair_contracts else 'candidate'
    payload = {
        'kind': 'fruth.inference_repair_feedback',
        'status': 'repair_required',
        'target': 'request_ir_patch',
        'patch_scope': 'current_working_frame_request_phase_graph',
        'preserve_request_id': True,
        'repair_mode': 'bounded_graph_patch',
        'intent_reanalysis_policy': 'only_if_repair_items_are_ambiguous',
        'reason': reason,
        'graph_mode': str(request_phase_graph.get('mode') or '').strip() or None,
        'current_phase_id': str(request_phase_graph.get('current_phase_id') or '').strip() or None,
        'instruction': (
            'Patch the Request IR / phase graph from runtime evidence; do not answer prose. '
            'Promote missing work to obligations, preserve fulfilled evidence, waive only with an explicit runtime reason, '
            'then rerun executable work before freeze.'
        ),
        'items': repair_items,
        'repair_rebuild_contracts': repair_contracts,
        'repair_loop': {
            'kind': 'fruth.repair_loop',
            'status': repair_loop_status,
            'authority': 'runtime_review_promoted',
            'auto_execute': bool(executable_contract_count),
            'round': 1,
            'max_rounds_policy': 'bounded_runtime_repair_policy',
            'next_actions': next_actions,
            'requires_promotion': not bool(repair_contracts),
            'promoted_contract_count': len(repair_contracts),
            'executable_contract_count': executable_contract_count,
            'blocked_contract_count': blocked_contract_count,
            'materialization_blocked_contract_count': blocked_contract_count,
            'repair_work_available': bool(repair_work_available_count),
            'repair_work_available_count': repair_work_available_count,
            'needs_external_input_count': needs_external_input_count,
            'promotion_review': {
                'status': 'promoted' if repair_contracts else 'candidate',
                'authority': 'closure_review_runtime_truth',
                'policy': 'promote_only_current_open_closure_checks',
            },
            'promoted_contracts': repair_contracts,
        },
    }
    if decision_contract_guidance:
        payload['decision_contract_guidance'] = decision_contract_guidance
    return {
        key: value
        for key, value in payload.items()
        if value not in (None, '', [], {})
    }
