"""Read and select from an accepted request phase graph.

These queries preserve branch aliases, terminal dispositions, dependency order
and batches. They never derive intent, promote candidates or dispatch workers.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional
from helpers.model_capabilities import (
    CAPABILITY_CHAT,
    CAPABILITY_IMAGE_GENERATION,
    CAPABILITY_SPEECH_TO_TEXT,
    CAPABILITY_TEXT_TO_SPEECH,
    CAPABILITY_VISION_ANALYSIS,
    normalize_capability,
)


_CANDIDATE_CONTRACT_STATES = {
    'candidate',
    'reserved',
    'possible',
    'draft',
    'optional',
    'not_promoted',
    'not-promoted',
    'unpromoted',
    'discarded',
    'rejected',
}


_PROMOTED_CONTRACT_STATES = {
    'promoted',
    'promoted_to_obligation',
    'promotion_accepted',
}


def _clean_text(value: Any) -> str:
    return str(value or '').strip()


def _output_type_for_capability(capability: Any) -> Optional[str]:
    token = normalize_capability(capability)
    if token == CAPABILITY_TEXT_TO_SPEECH:
        return 'audio'
    if token == CAPABILITY_IMAGE_GENERATION:
        return 'image'
    if token == CAPABILITY_SPEECH_TO_TEXT:
        return 'text'
    if token == CAPABILITY_VISION_ANALYSIS:
        return 'text'
    if token == CAPABILITY_CHAT:
        return 'text'
    return None


def _coerce_positive_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def _clean_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _unique_capabilities(values: list[Any]) -> list[str]:
    items: list[str] = []
    for value in values:
        capability = normalize_capability(value)
        if not capability or capability in items:
            continue
        items.append(capability)
    return items


def _contract_state(record: Mapping[str, Any]) -> str:
    for key in ('contract_state', 'contract_status', 'obligation_state', 'intent_state'):
        token = _clean_text(record.get(key)).lower()
        if token:
            return token
    return _clean_text(record.get('status')).lower()


def _explicit_required_flag(record: Mapping[str, Any]) -> Optional[bool]:
    if 'required' not in record:
        return None
    value = record.get('required')
    if isinstance(value, bool):
        return value
    token = _clean_text(value).lower()
    if token in {'true', 'yes', '1', 'required'}:
        return True
    if token in {'false', 'no', '0', 'optional'}:
        return False
    return None


def _is_unpromoted_candidate_record(record: Mapping[str, Any]) -> bool:
    state = _contract_state(record)
    if state in _PROMOTED_CONTRACT_STATES or _clean_text(record.get('promoted_from_candidate_id')):
        return False
    if _clean_text(record.get('candidate_id')):
        return True
    if state in _CANDIDATE_CONTRACT_STATES:
        return True
    return _explicit_required_flag(record) is False


def _phase_records(phase_graph: Optional[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(phase_graph, Mapping):
        return []
    phases = phase_graph.get('phases')
    if not isinstance(phases, list):
        return []
    return [dict(item) for item in phases if isinstance(item, Mapping)]


def _downstream_phase_records(
    phase_graph: Optional[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(phase_graph, Mapping):
        return []
    current_phase_id = _clean_text(phase_graph.get('current_phase_id'))
    records: list[dict[str, Any]] = []
    for phase in _phase_records(phase_graph):
        phase_id = _clean_text(phase.get('phase_id'))
        if not phase_id or phase_id == current_phase_id:
            continue
        if _is_unpromoted_candidate_record(phase):
            continue
        records.append(phase)
    return records


def _phase_ids_for_capability(
    phase_graph: Optional[Mapping[str, Any]],
    capability: Any,
) -> list[str]:
    normalized_capability = normalize_capability(capability)
    if not normalized_capability:
        return []
    phase_ids: list[str] = []
    for phase in _phase_records(phase_graph):
        if normalize_capability(phase.get('capability')) != normalized_capability:
            continue
        phase_id = _clean_text(phase.get('phase_id'))
        if phase_id:
            phase_ids.append(phase_id)
    return phase_ids


def _completed_phase_ids(phase_graph: Optional[Mapping[str, Any]]) -> set[str]:
    completed: set[str] = set()
    for phase in _phase_records(phase_graph):
        phase_id = _clean_text(phase.get('phase_id'))
        status = _clean_text(phase.get('status')).lower()
        if phase_id and status == 'completed':
            completed.add(phase_id)
    return completed


def _failed_phase_ids(phase_graph: Optional[Mapping[str, Any]]) -> set[str]:
    failed: set[str] = set()
    for phase in _phase_records(phase_graph):
        phase_id = _clean_text(phase.get('phase_id'))
        status = _clean_text(phase.get('status')).lower()
        if phase_id and status in {'blocked', 'failed'}:
            failed.add(phase_id)
    return failed


def _normalize_explicit_downstream_branch(
    raw_branch: Any,
    *,
    fallback_index: int,
) -> Optional[dict[str, Any]]:
    if isinstance(raw_branch, Mapping):
        capability = normalize_capability(raw_branch.get('capability'))
        branch_id = _clean_text(raw_branch.get('branch_id') or raw_branch.get('phase_id'))
        phase_id = _clean_text(raw_branch.get('phase_id') or branch_id)
        output_type = _clean_text(raw_branch.get('output_type')).lower() or _output_type_for_capability(capability)
        if not capability:
            return None
        if not branch_id:
            branch_id = f'branch-{capability}-{fallback_index}'
        if not phase_id:
            phase_id = f'phase-{fallback_index + 1}'
        record = {
            'branch_id': branch_id,
            'phase_id': phase_id,
            'capability': capability,
            'output_type': output_type,
            'depends_on': [
                _clean_text(item)
                for item in (raw_branch.get('depends_on') or [])
                if _clean_text(item)
            ] or ['phase-1'],
        }
        queue_index = _coerce_positive_int(raw_branch.get('queue_index'))
        if queue_index:
            record['queue_index'] = queue_index
        status = _clean_text(raw_branch.get('status')).lower()
        if status:
            record['status'] = status
        required = raw_branch.get('required')
        if isinstance(required, bool):
            record['required'] = required
        elif _clean_text(required):
            record['required'] = _clean_text(required)
        source = _clean_text(raw_branch.get('source'))
        if source:
            record['source'] = source
        for key in (
            'candidate_id',
            'contract_state',
            'contract_status',
            'obligation_state',
            'intent_state',
            'promotion_policy',
            'promotion_reason',
            'promotion_source',
            'promoted_from_candidate_id',
            'artifact_prompt',
            'artifact_prompt_source',
            'content_payload',
            'content_payload_source',
            'phase_summary',
            'stage_direction',
            'candidate_selection_index',
            'candidate_selection_count',
            'selection_policy',
            'selection_reason',
            'lang_code',
            'audio_variant_index',
            'audio_variant_role',
            'audio_variant_contract_source',
            'structured_output_contract',
            'branch_contract_error',
            'audio_variant_contract_conflicting_fields',
            'kind',
            'role',
            'semantic_intent',
            'objective',
            'deliverable',
            'rationale',
            'review_criteria',
            'input_refs',
            'execution_contract',
            'workload_task_ref',
            'output_obligation_ref',
            'output_contract',
            'accepted_proposals',
            'requires_artifact',
            'dependency_contract',
            'image_asset_binding_required',
            'required_image_phase_ids',
            'text_artifact_extension',
            'text_artifact_source_name',
            'text_artifact_source',
            'text_artifact_target_path',
            'text_artifact_revision_required',
            'text_artifact_revision_source',
            'text_artifact_revision_binding_state',
            'text_artifact_source_is_input',
            'retained_input_alias_required',
            'retained_input_binding_state',
            'retained_input_source_path',
            'retained_input_source_name',
            'retained_input_target_name',
            'retained_input_candidate_count',
            'artifact_request',
            'repair_action',
            'recovery_action',
            'repair_action_reason',
            'blocked_by_dependency_input',
            'blocked_by_branch_contract',
            'materialization_blocked',
        ):
            value = raw_branch.get(key)
            if value not in (None, '', [], {}):
                record[key] = value
        batch_prompts = _clean_string_list(raw_branch.get('batch_prompts'))
        if batch_prompts:
            record['batch_prompts'] = batch_prompts
        promotion = raw_branch.get('promotion')
        if isinstance(promotion, Mapping):
            record['promotion'] = dict(promotion)
        return record
    capability = normalize_capability(raw_branch)
    if not capability:
        return None
    return {
        'branch_id': f'branch-{capability}-{fallback_index}',
        'phase_id': f'phase-{fallback_index + 1}',
        'capability': capability,
        'output_type': _output_type_for_capability(capability),
        'depends_on': ['phase-1'],
    }


def current_phase_capability(phase_graph: Optional[Mapping[str, Any]]) -> Optional[str]:
    if not isinstance(phase_graph, Mapping):
        return None
    return normalize_capability(phase_graph.get('current_phase_capability'))


def downstream_phase_capabilities(phase_graph: Optional[Mapping[str, Any]]) -> list[str]:
    if not isinstance(phase_graph, Mapping):
        return []
    return _unique_capabilities([item.get('capability') for item in downstream_phase_records(phase_graph)])


def downstream_phase_records(phase_graph: Optional[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(item) for item in _downstream_phase_records(phase_graph)]


def next_executable_downstream_branches(
    phase_graph: Optional[Mapping[str, Any]],
    *,
    pending_branches: Optional[list[Mapping[str, Any]]] = None,
    completed_branches: Optional[list[Mapping[str, Any]]] = None,
    failed_branches: Optional[list[Mapping[str, Any]]] = None,
    pending_capabilities: Optional[list[Any]] = None,
    completed_capabilities: Optional[list[Any]] = None,
    failed_capabilities: Optional[list[Any]] = None,
    resolve_dependency_aliases: bool = False,
) -> list[dict[str, Any]]:
    phases = _phase_records(phase_graph)
    pending = [
        _normalize_explicit_downstream_branch(item, fallback_index=index)
        for index, item in enumerate(
            pending_branches if isinstance(pending_branches, list) and pending_branches else downstream_phase_records(phase_graph),
            start=1,
        )
    ]
    pending = [item for item in pending if item and not _is_unpromoted_candidate_record(item)]
    if not phases or not pending:
        if pending:
            return [dict(item) for item in pending[:1]]
        return []

    completed_phase_ids = _completed_phase_ids(phase_graph)
    failed_phase_ids = _failed_phase_ids(phase_graph)
    for branch_list, target in ((completed_branches, completed_phase_ids), (failed_branches, failed_phase_ids)):
        if not isinstance(branch_list, list):
            continue
        for index, item in enumerate(branch_list, start=1):
            normalized = _normalize_explicit_downstream_branch(item, fallback_index=index)
            phase_id = _clean_text((normalized or {}).get('phase_id'))
            if not phase_id and isinstance(item, Mapping):
                phase_id = _clean_text(item.get('phase_id') or item.get('branch_id'))
            if phase_id:
                target.add(phase_id)
    for capability in _unique_capabilities(completed_capabilities or []):
        phase_ids = _phase_ids_for_capability(phase_graph, capability)
        if len(phase_ids) == 1:
            completed_phase_ids.add(phase_ids[0])
    for capability in _unique_capabilities(failed_capabilities or []):
        phase_ids = _phase_ids_for_capability(phase_graph, capability)
        if len(phase_ids) == 1:
            failed_phase_ids.add(phase_ids[0])

    ready: list[dict[str, Any]] = []
    for branch in pending:
        phase_id = _clean_text(branch.get('phase_id'))
        if not phase_id or phase_id in completed_phase_ids or phase_id in failed_phase_ids:
            continue
        phase = next((item for item in phases if _clean_text(item.get('phase_id')) == phase_id), None)
        if phase is None:
            phase = dict(branch)
        depends_on = [
            _clean_text(item)
            for item in (phase.get('depends_on') or branch.get('depends_on') or [])
            if _clean_text(item)
        ]
        dependency_ids = depends_on
        if resolve_dependency_aliases:
            # Guarded continuation has no first-pending fallback. An alias is
            # usable only through one current graph phase and its exact result;
            # capability-level completion cannot establish this identity.
            dependency_ids = []
            for dependency in depends_on:
                matches = [item for item in phases if dependency in {
                    _clean_text(item.get('phase_id')), _clean_text(item.get('branch_id'))}]
                if len(matches) != 1 or _is_unpromoted_candidate_record(matches[0]):
                    break
                producer = matches[0]
                producer_phase = _clean_text(producer.get('phase_id'))
                if not producer_phase:
                    break
                if dependency != producer_phase:
                    results = [item for item in (completed_branches or [])
                               if isinstance(item, Mapping) and (
                                   item.get('branch_id') == producer.get('branch_id')
                                   or item.get('phase_id') == producer_phase)]
                    if (len(results) != 1
                            or results[0].get('status') not in {'fulfilled', 'completed'}
                            or any(producer.get(key)
                            and results[0].get(key) != producer[key]
                            for key in ('branch_id', 'phase_id', 'obligation_id', 'capability', 'output_type'))):
                        break
                dependency_ids.append(producer_phase)
            if len(dependency_ids) != len(depends_on):
                continue
        if any(dep_id in failed_phase_ids for dep_id in dependency_ids):
            continue
        if all(dep_id in completed_phase_ids for dep_id in dependency_ids):
            ready.append(
                {
                    **dict(phase),
                    **{
                        key: branch.get(key)
                        for key in (
                            'queue_index',
                            'artifact_prompt',
                            'artifact_prompt_source',
                            'content_payload',
                            'content_payload_source',
                            'phase_summary',
                            'stage_direction',
                            'repair_scope',
                            'resource_class',
                            'dependency_policy',
                            'runtime_scheduling_context',
                            'allow_gpu_heavy_concurrency',
                            'candidate_selection_index',
                            'candidate_selection_count',
                            'selection_policy',
                            'lang_code',
                            'audio_variant_index',
                            'audio_variant_role',
                            'audio_variant_contract_source',
                            'structured_output_contract',
                            'branch_contract_error',
                            'audio_variant_contract_conflicting_fields',
                            'batch_prompts',
                            'semantic_intent',
                            'objective',
                            'deliverable',
                            'rationale',
                            'review_criteria',
                            'input_refs',
                            'execution_contract',
                            'workload_task_ref',
                            'output_obligation_ref',
                            'output_contract',
                            'accepted_proposals',
                            'requires_artifact',
                            'text_artifact_extension',
                            'text_artifact_source_name',
                            'text_artifact_source',
                            'text_artifact_target_path',
                            'text_artifact_revision_required',
                            'text_artifact_revision_source',
                            'text_artifact_revision_binding_state',
                            'text_artifact_source_is_input',
                            'artifact_request',
                            'repair_action',
                            'recovery_action',
                            'repair_action_reason',
                            'repair_contract',
                            'repair_contract_id',
                            'repair_contract_status',
                            'repair_execution_policy',
                            'repair_promotion_source',
                            'contract_state',
                            'promotion_source',
                            'reconsideration_rebuild',
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
                            'blocked_by_dependency_input',
                            'blocked_by_branch_contract',
                        )
                        if branch.get(key) not in (None, '', [], {})
                    },
                    'branch_id': _clean_text(branch.get('branch_id') or phase.get('branch_id') or phase_id),
                    'phase_id': phase_id,
                    'capability': normalize_capability(branch.get('capability') or phase.get('capability')),
                    'output_type': _clean_text(branch.get('output_type') or phase.get('output_type')).lower()
                    or _output_type_for_capability(branch.get('capability') or phase.get('capability')),
                }
            )
    if ready:
        return ready
    return []


def downstream_phase_branch_batches(
    phase_graph: Optional[Mapping[str, Any]],
    *,
    pending_branches: Optional[list[Mapping[str, Any]]] = None,
    completed_branches: Optional[list[Mapping[str, Any]]] = None,
    failed_branches: Optional[list[Mapping[str, Any]]] = None,
    pending_capabilities: Optional[list[Any]] = None,
    completed_capabilities: Optional[list[Any]] = None,
    failed_capabilities: Optional[list[Any]] = None,
    resolve_dependency_aliases: bool = False,
) -> list[list[dict[str, Any]]]:
    remaining = [
        _normalize_explicit_downstream_branch(item, fallback_index=index)
        for index, item in enumerate(
            pending_branches if isinstance(pending_branches, list) and pending_branches else downstream_phase_records(phase_graph),
            start=1,
        )
    ]
    remaining = [item for item in remaining if item and not _is_unpromoted_candidate_record(item)]
    completed = [
        _normalize_explicit_downstream_branch(item, fallback_index=index)
        for index, item in enumerate(completed_branches or [], start=1)
    ]
    completed = [item for item in completed if item]
    if resolve_dependency_aliases:
        # Keep exact completion identity fields (notably obligation_id) for
        # alias proof; the normal scheduling projection intentionally omits them.
        completed = [dict(item) for item in (completed_branches or []) if isinstance(item, Mapping)]
    failed = [
        _normalize_explicit_downstream_branch(item, fallback_index=index)
        for index, item in enumerate(failed_branches or [], start=1)
    ]
    failed = [item for item in failed if item]
    batches: list[list[dict[str, Any]]] = []
    while remaining:
        batch = next_executable_downstream_branches(
            phase_graph,
            pending_branches=remaining,
            completed_branches=completed,
            failed_branches=failed,
            pending_capabilities=pending_capabilities,
            completed_capabilities=completed_capabilities,
            failed_capabilities=failed_capabilities,
            resolve_dependency_aliases=resolve_dependency_aliases,
        )
        if not batch:
            break
        batches.append(batch)
        completed.extend(item for item in batch if item not in completed)
        completed_ids = {_clean_text(item.get('branch_id') or item.get('phase_id')) for item in completed}
        remaining = [
            item
            for item in remaining
            if _clean_text(item.get('branch_id') or item.get('phase_id')) not in completed_ids
        ]
    return batches


def next_executable_downstream_capabilities(
    phase_graph: Optional[Mapping[str, Any]],
    *,
    pending_capabilities: Optional[list[Any]] = None,
    completed_capabilities: Optional[list[Any]] = None,
    failed_capabilities: Optional[list[Any]] = None,
) -> list[str]:
    batch = next_executable_downstream_branches(
        phase_graph,
        pending_capabilities=pending_capabilities,
        completed_capabilities=completed_capabilities,
        failed_capabilities=failed_capabilities,
    )
    return _unique_capabilities([item.get('capability') for item in batch])


def downstream_phase_batches(
    phase_graph: Optional[Mapping[str, Any]],
    *,
    pending_capabilities: Optional[list[Any]] = None,
    completed_capabilities: Optional[list[Any]] = None,
    failed_capabilities: Optional[list[Any]] = None,
) -> list[list[str]]:
    batches = downstream_phase_branch_batches(
        phase_graph,
        pending_capabilities=pending_capabilities,
        completed_capabilities=completed_capabilities,
        failed_capabilities=failed_capabilities,
    )
    return [_unique_capabilities([item.get('capability') for item in batch]) for batch in batches if batch]


def current_phase_is_graph_resolved(phase_graph: Optional[Mapping[str, Any]]) -> bool:
    if not isinstance(phase_graph, Mapping):
        return False
    return _clean_text(phase_graph.get('current_phase_resolution')).lower() == 'graph_resolved'


def current_phase_reason(phase_graph: Optional[Mapping[str, Any]]) -> Optional[str]:
    if not isinstance(phase_graph, Mapping):
        return None
    phases = phase_graph.get('phases')
    if not isinstance(phases, list):
        return None
    for raw_phase in phases:
        if not isinstance(raw_phase, Mapping):
            continue
        if _clean_text(raw_phase.get('phase_id')) != _clean_text(phase_graph.get('current_phase_id')):
            continue
        reason = _clean_text(raw_phase.get('reason'))
        return reason or None
    return None


