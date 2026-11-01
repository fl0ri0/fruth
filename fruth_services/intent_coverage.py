"""Current-intent coverage and graph adequacy decisions.

Consumes captured request scope and explicit graph/runtime records. This owner
compares accepted duties, reservations and dependency edges; it cannot promote,
execute, persist, or obtain authority from provider availability.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Mapping, Optional
from helpers.model_capabilities import (
    CAPABILITY_CHAT,
    CAPABILITY_IMAGE_GENERATION,
    CAPABILITY_SPEECH_TO_TEXT,
    CAPABILITY_TEXT_TO_SPEECH,
    CAPABILITY_VISION_ANALYSIS,
    normalize_capability,
)
from fruth_inference.intent import analyze_prompt_intent, materialization_is_deferred
from fruth_inference.intent_obligations import (
    required_intent_obligations,
    summarize_required_intent_obligations,
)
from fruth_inference.request_ir import output_obligations_from_graph
from fruth_server.recovery_contract import (
    RECOVERY_ACTION_REBUILD_FROM_PROMOTED_OBLIGATIONS,
    RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT,
    RECOVERY_ACTION_SEMANTIC_REVIEW,
)
from fruth_services.responses import extract_responses_current_turn_prompt


_INTENT_SEMANTIC_FIT_RE = re.compile(
    r'\b(?:'
    r'exactly\s+match(?:es|ed|ing)?|match(?:es|ed|ing)?\s+(?:its|their|the)\s+'
    r'(?:image|images|section|sections|artifact|artifacts)|'
    r'fit(?:s|ting)?\s+together|coherent\s+(?:local\s+)?artifact\s+set|'
    r'consistent\s+(?:artifact|visual|content|section)|'
    r'aligned\s+(?:text|image|visual|artifact|section)|'
    r'whole[-\s]?turn\s+fit|'
    r'inhaltlich\s+exakt|exakt\s+(?:zum|zur|zu|mit)|'
    r'passt\s+(?:exakt|genau|inhaltlich)|passen\s+(?:exakt|genau|inhaltlich)|'
    r'zusammenpassen|sauber\s+zusammenpassen|stimmig\s+zusammen|'
    r'texte?\s+.*(?:bild|bilder).*(?:passt|passen|exakt|stimmig)|'
    r'bilder?\s+.*(?:text|texte|abschnitt|abschnitte).*(?:passt|passen|exakt|stimmig)'
    r')\b',
    re.IGNORECASE,
)


_INTENT_SEMANTIC_QUALITY_RE = re.compile(
    r'\b(?:'
    r'(?:page|site|website|design|world|copy|text|image|images|section|sections)\s+'
    r'(?:must|should|needs?\s+to)\s+(?:feel|look|be|match|fit|refer|correspond)|'
    r'each\s+[^.;!?\n]{0,100}(?:image|section)\s+[^.;!?\n]{0,140}'
    r'(?:match|fit|refer|correspond|belong)|'
    r'(?:not|no)\s+[^.;!?\n]{0,60}'
    r'(?:dystopian|generic|luxury|wellness|saas|stock|childish|futuristic)|'
    r'(?:seite|gestaltung|welt|design|text|bilder?|tierbild|section|sections|abschnitt|abschnitte)\s+'
    r'(?:soll|sollen|muss|müssen|darf|dürfen)\s+[^.;!?\n]{0,180}'
    r'(?:wirken|sein|passen|passend|eingehen|verwendet|wiederverwendet|vertauscht)|'
    r'jed(?:e|es|er|en)\s+[^.;!?\n]{0,100}(?:bild|tierbild|section|abschnitt)\s+'
    r'[^.;!?\n]{0,160}(?:passen|passend|eingehen|verwendet|wiederverwendet|vertauscht)|'
    r'(?:nicht|kein|keine)\s+[^.;!?\n]{0,60}'
    r'(?:dystopisch|generisch|luxus|wellness|saas|stockfoto|kindisch|futuristisch)'
    r')\b',
    re.IGNORECASE,
)


_WAIVED_OBLIGATION_STATUSES = {
    'waived',
    'not_needed',
    'not-needed',
    'not_needed_verified',
    'skipped_verified',
    'unnecessary_verified',
}


_SUPERSEDED_OBLIGATION_STATUSES = {
    'obsolete',
    'replaced',
    'superseded',
    'no-longer-relevant',
    'no_longer_relevant',
}


_RESERVED_CANDIDATE_STATUSES = {
    'draft',
    'optional',
    'possible',
    'reserved',
}


_NON_EXECUTABLE_BRANCH_STATUSES = {
    'candidate',
    'deferred_not_executable',
    'future',
    'future_candidate',
    'held',
    'non_executable',
    'not_executable',
    'optional',
    'possible',
    'reserved',
    'reserved_candidate',
    'skipped',
}


_NON_EXECUTABLE_BRANCH_ROLES = {
    'candidate',
    'deferred_candidate',
    'future_candidate',
    'non_executable',
    'optional_output',
    'possible_future',
    'preparation_output',
    'reserved_candidate',
}


_NON_EXECUTABLE_POLICY_TOKENS = {
    'blocked_until_user_promotion',
    'candidate_only',
    'manual_promotion_required',
    'non_executable',
    'non_executable_until_promoted',
    'reserved_for_later',
}


def artifact_type_for_capability(capability: Optional[str]) -> Optional[str]:
    normalized = normalize_capability(capability)
    if normalized == CAPABILITY_IMAGE_GENERATION:
        return 'image'
    if normalized == CAPABILITY_TEXT_TO_SPEECH:
        return 'audio'
    if normalized == CAPABILITY_SPEECH_TO_TEXT:
        return 'text'
    return None


def _branch_record_is_non_executable_candidate(source: Mapping[str, Any]) -> bool:
    status = str(source.get('status') or source.get('contract_state') or '').strip().lower()
    role = str(source.get('role') or '').strip().lower()
    execution_policy = str(
        source.get('execution_policy')
        or source.get('promotion_policy')
        or source.get('repair_execution_policy')
        or ''
    ).strip().lower()
    output_contract = source.get('output_contract') if isinstance(source.get('output_contract'), Mapping) else {}
    output_contract_status = str(output_contract.get('status') or '').strip().lower()
    if status in _NON_EXECUTABLE_BRANCH_STATUSES:
        return True
    if output_contract_status in _NON_EXECUTABLE_BRANCH_STATUSES:
        return True
    if role in _NON_EXECUTABLE_BRANCH_ROLES:
        return True
    if execution_policy in _NON_EXECUTABLE_POLICY_TOKENS:
        return True
    if execution_policy.startswith('non_executable'):
        return True
    return bool(source.get('reserved_for_later') or source.get('deferred_not_executable'))


def _coerce_positive_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value if value > 0 else 0
    if isinstance(value, float):
        return int(value) if value > 0 else 0
    token = str(value or '').strip()
    if not token:
        return 0
    try:
        parsed = int(token)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def _current_request_prompt_for_review(
    request_payload: Optional[dict[str, Any]],
    request_phase_graph: Mapping[str, Any],
) -> str:
    if isinstance(request_payload, dict):
        try:
            prompt = extract_responses_current_turn_prompt(request_payload)
        except Exception:
            logging.getLogger(__name__).debug(
                'failed to extract current turn prompt for closure review',
                exc_info=True,
            )
            prompt = ''
        if str(prompt or '').strip():
            return str(prompt or '').strip()
        for key in ('prompt', 'input', 'instructions', 'message', 'query'):
            value = request_payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    graph_prompt = request_phase_graph.get('prompt') if isinstance(request_phase_graph, Mapping) else None
    return str(graph_prompt or '').strip()


def _merged_prompt_intent_for_review(
    prompt: str,
    request_phase_graph: Mapping[str, Any],
) -> dict[str, Any]:
    graph_intent = (
        request_phase_graph.get('prompt_intent')
        if isinstance(request_phase_graph.get('prompt_intent'), Mapping)
        else {}
    )
    analyzed = analyze_prompt_intent(prompt) if str(prompt or '').strip() else {}
    current_turn_suppresses_visual_artifact_execution = bool(
        analyzed.get('visual_artifact_execution_suppressed_by_preservation')
    )
    current_turn_suppresses_visual_analysis_execution = bool(
        analyzed.get('visual_analysis_execution_suppressed_by_preservation')
    )
    merged: dict[str, Any] = {}
    for source in (analyzed, graph_intent):
        for key, value in source.items():
            if value not in (None, '', [], {}):
                merged[key] = value
    for key in (
        'requests_visual_output',
        'has_visual_follow_up_request',
        'text_preparation_before_visual_output',
        'requests_audio_output',
        'requests_speech_to_text_output',
        'has_audio_follow_up_request',
        'text_preparation_before_audio_output',
        'direct_audio_materialization_request',
        'counted_audio_output_obligation',
        'audio_output_count_exceeds_bound',
        'explicit_defer_materialization',
        'explicit_visual_defer_materialization',
        'explicit_audio_defer_materialization',
    ):
        merged[key] = bool(analyzed.get(key) or graph_intent.get(key))
    intent_obligations = [
        item
        for item in (request_phase_graph.get('intent_obligations') or [])
        if isinstance(item, Mapping)
    ]
    required_obligations = required_intent_obligations(intent_obligations)
    required_summary = summarize_required_intent_obligations(required_obligations)
    required_capabilities = list(required_summary.get('capabilities') or [])
    required_capability_counts = dict(required_summary.get('capability_counts') or {})
    required_output_counts = dict(required_summary.get('material_output_counts') or {})

    analyzed_downstream = analyzed.get('downstream_follow_up_capabilities')
    graph_downstream = graph_intent.get('downstream_follow_up_capabilities')
    downstream: list[str] = []
    for raw_list in (analyzed_downstream, graph_downstream, required_capabilities):
        if not isinstance(raw_list, list):
            continue
        for item in raw_list:
            capability = normalize_capability(item)
            if capability and capability not in downstream:
                downstream.append(capability)
    if downstream:
        merged['downstream_follow_up_capabilities'] = downstream
    merged['requested_visual_output_count'] = max(
        _coerce_positive_int(analyzed.get('requested_visual_output_count')),
        _coerce_positive_int(graph_intent.get('requested_visual_output_count')),
        _coerce_positive_int(required_output_counts.get('image')),
    )
    if merged.get('audio_output_count_exceeds_bound'):
        merged['requested_audio_output_count'] = 0
    else:
        merged['requested_audio_output_count'] = max(
            _coerce_positive_int(analyzed.get('requested_audio_output_count')),
            _coerce_positive_int(graph_intent.get('requested_audio_output_count')),
            _coerce_positive_int(required_output_counts.get('audio')),
        )
    if required_output_counts.get('image') and not merged.get('explicit_visual_defer_materialization'):
        merged['requests_visual_output'] = True
    if required_output_counts.get('audio') and not merged.get('explicit_audio_defer_materialization'):
        merged['requests_audio_output'] = True
    if required_capability_counts.get(CAPABILITY_SPEECH_TO_TEXT):
        merged['requests_speech_to_text_output'] = True

    required_phase_ids_by_capability: dict[str, set[str]] = {}
    for obligation in required_obligations:
        capability = normalize_capability(obligation.get('capability'))
        phase_id = str(obligation.get('phase_id') or obligation.get('branch_id') or '').strip()
        if capability and phase_id:
            required_phase_ids_by_capability.setdefault(capability, set()).add(phase_id)
    if normalize_capability(request_phase_graph.get('current_phase_capability')) == CAPABILITY_CHAT:
        current_phase_id = str(request_phase_graph.get('current_phase_id') or '').strip()
        for record in request_phase_graph.get('downstream_branches') or []:
            if not isinstance(record, Mapping):
                continue
            capability = normalize_capability(record.get('capability'))
            phase_id = str(record.get('phase_id') or record.get('branch_id') or '').strip()
            dependencies = {
                str(item or '').strip()
                for item in (record.get('depends_on') or [])
                if str(item or '').strip()
            }
            if (
                not capability
                or phase_id not in required_phase_ids_by_capability.get(capability, set())
                or not current_phase_id
                or current_phase_id not in dependencies
            ):
                continue
            if capability == CAPABILITY_IMAGE_GENERATION:
                merged['text_preparation_before_visual_output'] = True
            elif capability == CAPABILITY_TEXT_TO_SPEECH:
                merged['text_preparation_before_audio_output'] = True

    # The fresh turn is the intent boundary.  A graph may still carry positive
    # visual cues or counts from the predecessor turn, but an explicit
    # preserve-without-regeneration instruction makes that image a reference,
    # not a newly owed output.  Only an independently detected request for a
    # new/separate visual artifact may keep image execution active.
    if current_turn_suppresses_visual_artifact_execution:
        merged['visual_artifact_preservation_without_regeneration'] = True
        merged['visual_artifact_execution_suppressed_by_preservation'] = True
        merged['requests_visual_output'] = False
        merged['has_visual_follow_up_request'] = False
        merged['text_preparation_before_visual_output'] = False
        merged['requested_visual_output_count'] = 0
        merged['counted_visual_output_obligation'] = False
        if normalize_capability(merged.get('primary_capability')) == CAPABILITY_IMAGE_GENERATION:
            merged.pop('primary_capability', None)
        downstream = [
            capability
            for capability in (merged.get('downstream_follow_up_capabilities') or [])
            if normalize_capability(capability) != CAPABILITY_IMAGE_GENERATION
        ]
        if downstream:
            merged['downstream_follow_up_capabilities'] = downstream
        else:
            merged.pop('downstream_follow_up_capabilities', None)
        required_output_counts.pop('image', None)
        required_capability_counts.pop(CAPABILITY_IMAGE_GENERATION, None)
        required_capabilities = [
            capability
            for capability in required_capabilities
            if normalize_capability(capability) != CAPABILITY_IMAGE_GENERATION
        ]
    if current_turn_suppresses_visual_analysis_execution:
        merged['visual_analysis_preservation_without_reanalysis'] = True
        merged['visual_analysis_execution_suppressed_by_preservation'] = True
        if normalize_capability(merged.get('primary_capability')) == CAPABILITY_VISION_ANALYSIS:
            merged.pop('primary_capability', None)
        downstream = [
            capability
            for capability in (merged.get('downstream_follow_up_capabilities') or [])
            if normalize_capability(capability) != CAPABILITY_VISION_ANALYSIS
        ]
        if downstream:
            merged['downstream_follow_up_capabilities'] = downstream
        else:
            merged.pop('downstream_follow_up_capabilities', None)
        required_capability_counts.pop(CAPABILITY_VISION_ANALYSIS, None)
        required_capabilities = [
            capability
            for capability in required_capabilities
            if normalize_capability(capability) != CAPABILITY_VISION_ANALYSIS
        ]
    merged['required_intent_obligation_count'] = int(required_summary.get('required_count') or 0)
    merged['required_intent_obligation_kinds'] = list(required_summary.get('kinds') or [])
    merged['required_intent_capabilities'] = required_capabilities
    merged['required_intent_capability_counts'] = required_capability_counts
    merged['required_intent_output_counts'] = required_output_counts
    return merged


def _reserved_material_output_counts(
    request_phase_graph: Mapping[str, Any],
) -> dict[str, int]:
    if not isinstance(request_phase_graph, Mapping):
        return {}
    request_ir = (
        request_phase_graph.get('request_ir')
        if isinstance(request_phase_graph.get('request_ir'), Mapping)
        else {}
    )
    source_lists = (
        (request_phase_graph.get('candidate_graph') or {}).get('candidates')
        if isinstance(request_phase_graph.get('candidate_graph'), Mapping)
        else None,
        (request_ir.get('candidate_graph') or {}).get('candidates')
        if isinstance(request_ir.get('candidate_graph'), Mapping)
        else None,
        request_phase_graph.get('output_candidates'),
        request_ir.get('output_candidates'),
        request_phase_graph.get('downstream_branches'),
        request_phase_graph.get('phases'),
    )
    counts: dict[str, int] = {}
    seen: set[str] = set()
    for raw_list in source_lists:
        if not isinstance(raw_list, list):
            continue
        for raw_item in raw_list:
            if not isinstance(raw_item, Mapping):
                continue
            status = ''
            for key in (
                'status',
                'candidate_status',
                'contract_state',
                'contract_status',
                'obligation_state',
                'intent_state',
            ):
                status = str(raw_item.get(key) or '').strip().lower()
                if status:
                    break
            if status not in _RESERVED_CANDIDATE_STATUSES:
                continue
            capability = normalize_capability(raw_item.get('capability'))
            output_type = str(raw_item.get('output_type') or '').strip().lower()
            if not output_type:
                output_type = str(artifact_type_for_capability(capability) or '').strip().lower()
            if output_type not in {'audio', 'image'}:
                continue
            identity = str(
                raw_item.get('branch_id')
                or raw_item.get('phase_id')
                or raw_item.get('obligation_id')
                or raw_item.get('candidate_id')
                or f'{output_type}:{len(seen) + 1}'
            ).strip()
            if identity in seen:
                continue
            seen.add(identity)
            counts[output_type] = counts.get(output_type, 0) + 1
    return counts


def _expected_material_output_counts(
    *,
    request_payload: Optional[dict[str, Any]],
    request_phase_graph: Mapping[str, Any],
) -> dict[str, int]:
    prompt = _current_request_prompt_for_review(request_payload, request_phase_graph)
    prompt_intent = _merged_prompt_intent_for_review(prompt, request_phase_graph)
    explicit_visual_defer = bool(prompt_intent.get('explicit_visual_defer_materialization'))
    explicit_audio_defer = bool(prompt_intent.get('explicit_audio_defer_materialization'))
    suppress_visual_artifact_execution = bool(
        prompt_intent.get('visual_artifact_execution_suppressed_by_preservation')
    )
    if (
        materialization_is_deferred(prompt_intent)
        and not explicit_visual_defer
        and not explicit_audio_defer
    ):
        return {}

    required_summary = summarize_required_intent_obligations(
        request_phase_graph.get('intent_obligations')
        if isinstance(request_phase_graph.get('intent_obligations'), list)
        else []
    )
    required_output_counts = required_summary.get('material_output_counts')
    if not isinstance(required_output_counts, Mapping):
        required_output_counts = {}

    authoritative_image_count = _coerce_positive_int(required_output_counts.get('image'))
    authoritative_image_refs: set[str] = set()
    authoritative_sources: list[Mapping[str, Any]] = []
    request_ir = (
        request_phase_graph.get('request_ir')
        if isinstance(request_phase_graph.get('request_ir'), Mapping)
        else {}
    )
    authoritative_collections: list[Any] = [
        request_ir.get('output_obligations'),
        request_phase_graph.get('output_obligations'),
        request_phase_graph.get('downstream_branches'),
    ]
    if bool(
        prompt_intent.get('requests_visual_output')
        or prompt_intent.get('has_visual_follow_up_request')
        or prompt_intent.get('text_preparation_before_visual_output')
        or _coerce_positive_int(prompt_intent.get('requested_visual_output_count'))
    ):
        # Older graphs may represent an explicitly requested executable
        # image branch only in `phases`. Prompt intent cannot promote a
        # branch by itself, but it can identify such a phase as belonging
        # to the current request rather than preserved prior evidence.
        authoritative_collections.append(request_phase_graph.get('phases'))
    for source_collection in authoritative_collections:
        if not isinstance(source_collection, list):
            continue
        authoritative_sources.extend(
            item for item in source_collection if isinstance(item, Mapping)
        )
    for index, source in enumerate(authoritative_sources, start=1):
        if source.get('required') is False or _branch_record_is_non_executable_candidate(source):
            continue
        status = str(source.get('status') or source.get('contract_state') or '').strip().lower()
        if status in _WAIVED_OBLIGATION_STATUSES or status in _SUPERSEDED_OBLIGATION_STATUSES:
            continue
        capability = normalize_capability(source.get('capability'))
        output_type = str(source.get('output_type') or '').strip().lower()
        if not output_type:
            output_type = str(artifact_type_for_capability(capability) or '').strip().lower()
        if output_type != 'image' and capability != CAPABILITY_IMAGE_GENERATION:
            continue
        identity = str(
            source.get('branch_id')
            or source.get('phase_id')
            or source.get('obligation_id')
            or source.get('candidate_id')
            or f'image:{index}'
        ).strip()
        authoritative_image_refs.add(identity)
    authoritative_image_count = max(authoritative_image_count, len(authoritative_image_refs))

    downstream_capabilities = {
        normalize_capability(item)
        for item in (prompt_intent.get('downstream_follow_up_capabilities') or [])
        if normalize_capability(item)
    }
    current_capability = normalize_capability(request_phase_graph.get('current_phase_capability'))
    primary_capability = normalize_capability(prompt_intent.get('primary_capability'))
    expected: dict[str, int] = {}

    # Prompt inference may refine a promoted image obligation, but it cannot
    # create one. Graph authority must come from a required intent
    # obligation or an executable current-turn image output record.
    expects_image = authoritative_image_count > 0
    if explicit_visual_defer or suppress_visual_artifact_execution:
        expects_image = False
    if expects_image:
        requested_count = _coerce_positive_int(prompt_intent.get('requested_visual_output_count'))
        if isinstance(request_payload, Mapping):
            for key in ('batch_count', 'n', 'count'):
                requested_count = max(requested_count, _coerce_positive_int(request_payload.get(key)))
            batch_prompts = request_payload.get('batch_prompts')
            if isinstance(batch_prompts, list):
                requested_count = max(requested_count, len([item for item in batch_prompts if item]))
        expected['image'] = max(1, requested_count, authoritative_image_count)

    expects_audio = bool(
        not prompt_intent.get('audio_output_count_exceeds_bound')
        and (
            prompt_intent.get('requests_audio_output')
            or prompt_intent.get('has_audio_follow_up_request')
            or prompt_intent.get('text_preparation_before_audio_output')
            or prompt_intent.get('direct_audio_materialization_request')
            or CAPABILITY_TEXT_TO_SPEECH in downstream_capabilities
            or current_capability == CAPABILITY_TEXT_TO_SPEECH
            or primary_capability == CAPABILITY_TEXT_TO_SPEECH
        )
    )
    if explicit_audio_defer:
        expects_audio = False
    if expects_audio:
        expected['audio'] = max(
            1,
            _coerce_positive_int(
                prompt_intent.get('requested_audio_output_count')
            ),
        )

    if not explicit_visual_defer and not suppress_visual_artifact_execution:
        image_count = _coerce_positive_int(required_output_counts.get('image'))
        if image_count:
            expected['image'] = max(expected.get('image', 0), image_count)
    if not explicit_audio_defer:
        audio_count = _coerce_positive_int(required_output_counts.get('audio'))
        if audio_count:
            expected['audio'] = max(expected.get('audio', 0), audio_count)

    return expected


def _graph_material_output_counts(request_phase_graph: Mapping[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    obligations = output_obligations_from_graph(request_phase_graph)
    sources = obligations if obligations else request_phase_graph.get('phases')
    if not isinstance(sources, list):
        return counts
    current_phase_id = str(request_phase_graph.get('current_phase_id') or '').strip()
    for raw_source in sources:
        if not isinstance(raw_source, Mapping):
            continue
        if _branch_record_is_non_executable_candidate(raw_source):
            continue
        phase_id = str(raw_source.get('phase_id') or '').strip()
        if not obligations and current_phase_id and phase_id == current_phase_id:
            continue
        required = raw_source.get('required')
        if required is False:
            continue
        output_type = str(raw_source.get('output_type') or '').strip().lower()
        if not output_type:
            output_type = str(
                artifact_type_for_capability(raw_source.get('capability')) or ''
            ).strip().lower()
        if output_type in {'image', 'audio'}:
            counts[output_type] = counts.get(output_type, 0) + 1
    return counts


def _graph_required_capability_counts(request_phase_graph: Mapping[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    obligations = output_obligations_from_graph(request_phase_graph)
    sources = obligations if obligations else request_phase_graph.get('phases')
    if not isinstance(sources, list):
        return counts
    current_phase_id = str(request_phase_graph.get('current_phase_id') or '').strip()
    for raw_source in sources:
        if not isinstance(raw_source, Mapping):
            continue
        if _branch_record_is_non_executable_candidate(raw_source):
            continue
        if raw_source.get('required') is False:
            continue
        capability = normalize_capability(raw_source.get('capability'))
        if not capability:
            continue
        if capability == CAPABILITY_CHAT:
            phase_id = str(raw_source.get('phase_id') or raw_source.get('branch_id') or '').strip()
            if not phase_id or phase_id == current_phase_id:
                continue
        counts[capability] = counts.get(capability, 0) + 1
    return counts


def _intent_obligation_summary(intent_obligations: list[Mapping[str, Any]]) -> dict[str, Any]:
    kind_counts: dict[str, int] = {}
    dependency_contract_counts: dict[str, int] = {}
    required_count = 0
    execution_dependency_count = 0
    for obligation in required_intent_obligations(intent_obligations):
        required_count += 1
        kind = str(obligation.get('kind') or '').strip().lower()
        if kind:
            kind_counts[kind] = kind_counts.get(kind, 0) + 1
        dependency_contract = str(obligation.get('dependency_contract') or '').strip().lower()
        if dependency_contract:
            dependency_contract_counts[dependency_contract] = (
                dependency_contract_counts.get(dependency_contract, 0) + 1
            )
        if kind == 'dependency' and obligation.get('execution_dependency_required') is True:
            execution_dependency_count += 1
    return {
        'required_count': required_count,
        'kind_counts': kind_counts,
        'dependency_contract_counts': dependency_contract_counts,
        'execution_dependency_count': execution_dependency_count,
    }


def _phase_lookup_for_intent_review(request_phase_graph: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    phase_lookup: dict[str, Mapping[str, Any]] = {}
    if not isinstance(request_phase_graph, Mapping):
        return phase_lookup
    for collection_key in ('phases', 'downstream_branches'):
        collection = request_phase_graph.get(collection_key)
        if not isinstance(collection, list):
            continue
        for record in collection:
            if not isinstance(record, Mapping):
                continue
            for record_id in (
                str(record.get('phase_id') or '').strip(),
                str(record.get('branch_id') or '').strip(),
                str(record.get('obligation_id') or '').strip(),
            ):
                if record_id and record_id not in phase_lookup:
                    phase_lookup[record_id] = record
    return phase_lookup


def _missing_intent_dependency_edges(
    intent_obligations: list[Mapping[str, Any]],
    phase_lookup: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    for obligation in required_intent_obligations(intent_obligations):
        if str(obligation.get('kind') or '').strip().lower() != 'dependency':
            continue
        if obligation.get('execution_dependency_required') is not True:
            continue
        target_phase_id = str(
            obligation.get('target_phase_id') or obligation.get('target_branch_id') or ''
        ).strip()
        source_phase_ids = [
            str(item or '').strip()
            for item in (obligation.get('source_phase_ids') or [])
            if str(item or '').strip()
        ]
        if not target_phase_id or not source_phase_ids:
            continue
        target_record = phase_lookup.get(target_phase_id)
        actual_dependencies = [
            str(item or '').strip()
            for item in ((target_record or {}).get('depends_on') or [])
            if str(item or '').strip()
        ]
        missing_source_phase_ids = [
            source_phase_id
            for source_phase_id in source_phase_ids
            if source_phase_id not in actual_dependencies
        ]
        if not target_record or missing_source_phase_ids:
            missing.append(
                {
                    'obligation_id': str(obligation.get('obligation_id') or '').strip() or None,
                    'dependency_contract': str(obligation.get('dependency_contract') or '').strip() or None,
                    'target_phase_id': target_phase_id,
                    'target_branch_id': str(obligation.get('target_branch_id') or '').strip() or None,
                    'source_phase_ids': source_phase_ids,
                    'missing_source_phase_ids': missing_source_phase_ids or source_phase_ids,
                    'actual_depends_on': actual_dependencies,
                    'add_dependencies': [
                        {
                            'target_phase_id': target_phase_id,
                            'source_phase_id': source_phase_id,
                            'dependency_contract': obligation.get('dependency_contract'),
                        }
                        for source_phase_id in (missing_source_phase_ids or source_phase_ids)
                    ],
                }
            )
    return missing


def _intent_graph_has_explicit_promise_ledger(request_phase_graph: Mapping[str, Any]) -> bool:
    for key in ('output_obligations', 'intent_obligations'):
        records = request_phase_graph.get(key)
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, Mapping):
                continue
            if record.get('required') is False:
                continue
            capability = normalize_capability(record.get('capability'))
            output_type = str(record.get('output_type') or '').strip().lower()
            kind = str(record.get('kind') or '').strip().lower()
            if capability or output_type or kind:
                return True
    return False


def _intent_semantic_fit_requested(prompt: str, prompt_intent: Mapping[str, Any]) -> bool:
    prompt_text = str(prompt or '').strip()
    if prompt_text and (
        _INTENT_SEMANTIC_FIT_RE.search(prompt_text)
        or _INTENT_SEMANTIC_QUALITY_RE.search(prompt_text)
    ):
        return True
    cues = [
        str(item or '').strip().lower()
        for item in (
            prompt_intent.get('local_visual_asset_cues')
            if isinstance(prompt_intent.get('local_visual_asset_cues'), list)
            else []
        )
        if str(item or '').strip()
    ]
    return any(
        'fit' in cue
        or 'match' in cue
        or 'zusammen' in cue
        or 'stimmig' in cue
        or 'exakt' in cue
        for cue in cues
    )


def _build_intent_lens_review(
    *,
    prompt: str,
    prompt_intent: Mapping[str, Any],
    request_phase_graph: Mapping[str, Any],
    intent_obligations: list[Mapping[str, Any]],
    expected_counts: Mapping[str, int],
    expected_capability_counts: Mapping[str, int],
    existing_structural_gap_count: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    summary = _intent_obligation_summary(intent_obligations)
    kind_counts = summary.get('kind_counts') if isinstance(summary.get('kind_counts'), dict) else {}
    dependency_contract_counts = (
        summary.get('dependency_contract_counts')
        if isinstance(summary.get('dependency_contract_counts'), dict)
        else {}
    )
    required_count = int(summary.get('required_count') or 0)
    material_expected = bool(
        expected_counts
        or expected_capability_counts
        or prompt_intent.get('requests_text_artifact_output')
        or prompt_intent.get('requests_visual_output')
        or prompt_intent.get('requests_audio_output')
        or prompt_intent.get('requests_speech_to_text_output')
    )
    phase_lookup = _phase_lookup_for_intent_review(request_phase_graph)
    missing_dependencies = _missing_intent_dependency_edges(intent_obligations, phase_lookup)
    semantic_fit_requested = _intent_semantic_fit_requested(prompt, prompt_intent)
    text_media_combo = bool(kind_counts.get('text_artifact') and kind_counts.get('media_artifact'))

    checks: list[dict[str, Any]] = []
    attention_status = 'not_applicable'
    if material_expected:
        explicit_promise_ledger = _intent_graph_has_explicit_promise_ledger(
            request_phase_graph
        )
        attention_status = (
            'fulfilled'
            if required_count or explicit_promise_ledger or existing_structural_gap_count
            else 'pending'
        )
        if attention_status == 'pending':
            checks.append(
                {
                    'check_kind': 'intent_attention_review',
                    'status': 'pending',
                    'evidence': 'intent_attention_missing_promise_ledger',
                    'reason': 'current material intent has no normalized intent obligations',
                    'repair_action': RECOVERY_ACTION_REBUILD_FROM_PROMOTED_OBLIGATIONS,
                    'recovery_action': RECOVERY_ACTION_REBUILD_FROM_PROMOTED_OBLIGATIONS,
                }
            )

    commitment_applicable = bool(
        dependency_contract_counts
        or text_media_combo
        or prompt_intent.get('local_visual_asset_requirement')
    )
    commitment_status = 'not_applicable'
    if commitment_applicable:
        commitment_status = 'pending' if missing_dependencies else 'fulfilled'
    for item in missing_dependencies:
        checks.append(
            {
                'check_kind': 'intent_commitment_review',
                'obligation_id': item.get('obligation_id') or f"missing-dependency-{item.get('target_phase_id')}",
                'status': 'pending',
                'evidence': 'intent_commitment_missing_dependency_edge',
                'reason': 'current intent requires producer/consumer binding before truthful materialization',
                'dependency_contract': item.get('dependency_contract'),
                'target_phase_id': item.get('target_phase_id'),
                'target_branch_id': item.get('target_branch_id'),
                'source_phase_ids': item.get('source_phase_ids'),
                'missing_source_phase_ids': item.get('missing_source_phase_ids'),
                'actual_depends_on': item.get('actual_depends_on'),
                'repair_action': 'rebind_artifact_dependency',
                'recovery_action': 'rebind_artifact_dependency',
                'add_dependencies': item.get('add_dependencies'),
            }
        )

    aspiration_status = 'not_applicable'
    if semantic_fit_requested and text_media_combo:
        aspiration_status = 'fulfilled'
        checks.append(
            {
                'check_kind': 'intent_aspiration_review',
                'status': 'fulfilled',
                'evidence': 'intent_aspiration_semantic_fit_requested',
                'reason': 'current intent explicitly asks generated text/media/artifacts to fit together',
                'semantic_review_required': True,
                'semantic_review_action': RECOVERY_ACTION_SEMANTIC_REVIEW,
                'semantic_review_authority': 'global_semantic_closure_review',
                'semantic_review_criteria': [
                    'whole_current_intent_fit_between_text_media_and_artifacts',
                    'section_text_matches_its_declared_image_or_artifact_role',
                    'local_artifact_set_is_coherent_with_prompt_intent',
                    'explicit_visual_and_tone_constraints_match_prompt',
                ],
                'review_criteria': [
                    'runtime_artifacts_exist_before_semantic_fit_review',
                    'whole_current_intent_fit_between_text_media_and_artifacts',
                ],
            }
        )

    status = 'not_applicable'
    if any(str(item.get('status') or '').strip().lower() in {'pending', 'blocked'} for item in checks):
        status = 'pending'
    elif attention_status != 'not_applicable' or commitment_status != 'not_applicable' or aspiration_status != 'not_applicable':
        status = 'fulfilled'

    review = {
        'kind': 'fruth.intent_lens_review',
        'status': status,
        'authority': 'closure_review_runtime_projection',
        'policy': 'attention_commitment_aspiration_lenses_apply_to_current_intent_before_freeze',
        'required_intent_obligation_count': required_count,
        'intent_obligation_kinds': [
            key for key, value in sorted(kind_counts.items()) if int(value or 0) > 0
        ],
        'dependency_contract_counts': dependency_contract_counts,
        'semantic_fit_requested': bool(semantic_fit_requested and text_media_combo),
        'attention_review': {
            'kind': 'fruth.intent_attention_review',
            'status': attention_status,
            'policy': 'current_material_intent_must_have_a_visible_promise_ledger',
        },
        'commitment_review': {
            'kind': 'fruth.intent_commitment_review',
            'status': commitment_status,
            'policy': 'promised_dependency_and_binding_order_must_be_executable_or_repairable',
            'missing_dependency_count': len(missing_dependencies),
        },
        'aspiration_review': {
            'kind': 'fruth.intent_aspiration_review',
            'status': aspiration_status,
            'policy': 'semantic_fit_promises_require_whole_turn_review_after_runtime_evidence',
        },
        'check_count': len(checks),
    }
    return _compact_mapping(review), [
        _compact_mapping(check) for check in checks
    ]


def build_intent_graph_adequacy_review(
    *,
    request_payload: Optional[dict[str, Any]],
    request_phase_graph: Mapping[str, Any],
) -> dict[str, Any]:
    prompt = _current_request_prompt_for_review(request_payload, request_phase_graph)
    prompt_intent = _merged_prompt_intent_for_review(prompt, request_phase_graph)
    suppress_visual_artifact_execution = bool(
        prompt_intent.get('visual_artifact_execution_suppressed_by_preservation')
    )
    suppress_visual_analysis_execution = bool(
        prompt_intent.get('visual_analysis_execution_suppressed_by_preservation')
    )
    intent_obligations = [
        item for item in (request_phase_graph.get('intent_obligations') or [])
        if isinstance(item, Mapping)
    ]
    required_obligations = required_intent_obligations(intent_obligations)
    required_intent_summary = summarize_required_intent_obligations(required_obligations)
    required_output_counts = dict(
        required_intent_summary.get('material_output_counts') or {}
    )
    expected_counts = _expected_material_output_counts(
        request_payload=request_payload,
        request_phase_graph=request_phase_graph,
    )
    graph_counts = _graph_material_output_counts(request_phase_graph)
    reserved_counts = _reserved_material_output_counts(request_phase_graph)
    for output_type, reserved_count in reserved_counts.items():
        if output_type not in expected_counts:
            continue
        if (
            output_type == 'image'
            and bool(prompt_intent.get('counted_visual_output_obligation'))
            and _coerce_positive_int(prompt_intent.get('requested_visual_output_count')) > 0
            and not bool(prompt_intent.get('explicit_visual_defer_materialization'))
        ):
            continue
        expected_count = max(0, expected_counts.get(output_type, 0) - reserved_count)
        if expected_count <= graph_counts.get(output_type, 0):
            expected_counts.pop(output_type, None)
        else:
            expected_counts[output_type] = expected_count
    generic_materialization_defer = bool(
        materialization_is_deferred(prompt_intent)
        and not prompt_intent.get('explicit_visual_defer_materialization')
        and not prompt_intent.get('explicit_audio_defer_materialization')
    )
    for output_type, required_count in required_output_counts.items():
        if generic_materialization_defer:
            continue
        if output_type == 'image' and (
            prompt_intent.get('explicit_visual_defer_materialization')
            or suppress_visual_artifact_execution
        ):
            continue
        if output_type == 'audio' and prompt_intent.get('explicit_audio_defer_materialization'):
            continue
        expected_counts[output_type] = max(
            expected_counts.get(output_type, 0),
            _coerce_positive_int(required_count),
        )
    graph_capability_counts = _graph_required_capability_counts(request_phase_graph)
    checks: list[dict[str, Any]] = []
    if prompt_intent.get('audio_output_count_exceeds_bound'):
        requested_audio_count = _coerce_positive_int(
            prompt_intent.get('requested_audio_output_count_raw')
        )
        maximum_audio_count = _coerce_positive_int(
            prompt_intent.get('requested_audio_output_count_max')
        ) or 6
        checks.append(
            {
                'check_kind': 'intent_cardinality_guard',
                'obligation_id': 'blocked-obligation-audio-cardinality',
                'capability': CAPABILITY_TEXT_TO_SPEECH,
                'output_type': 'audio',
                'status': 'blocked',
                'evidence': 'audio_output_count_exceeds_bound',
                'reason': (
                    f'requested audio output count {requested_audio_count} exceeds '
                    f'the bounded maximum {maximum_audio_count}'
                ),
                'expected_count': requested_audio_count,
                'actual_count': 0,
                # This is one contract-clarification obligation, not N safe
                # materialization attempts.
                'missing_count': 1,
                'requested_audio_output_count_raw': requested_audio_count,
                'requested_audio_output_count_max': maximum_audio_count,
                'repair_action': RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT,
                'recovery_action': RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT,
                'blocked_by_branch_contract': True,
                'materialization_blocked': True,
                'needs_external_input': True,
            }
        )
    for output_type, expected_count in sorted(expected_counts.items()):
        actual_count = graph_counts.get(output_type, 0)
        if actual_count >= expected_count:
            continue
        capability = (
            CAPABILITY_IMAGE_GENERATION
            if output_type == 'image'
            else CAPABILITY_TEXT_TO_SPEECH
            if output_type == 'audio'
            else None
        )
        checks.append(
            {
                'check_kind': 'intent_graph_adequacy',
                'obligation_id': f'missing-obligation-{output_type}',
                'capability': capability,
                'output_type': output_type,
                'status': 'pending',
                'evidence': 'intent_graph_adequacy_missing_output_obligation',
                'expected_count': expected_count,
                'actual_count': actual_count,
                'missing_count': expected_count - actual_count,
            }
        )

    downstream_capabilities = {
        normalize_capability(item)
        for item in (prompt_intent.get('downstream_follow_up_capabilities') or [])
        if normalize_capability(item)
    }
    # Multiple intent-ledger records may describe different semantic roles
    # of the same executable branch (for example, one HTML branch can be
    # both the text artifact and the evidence join). Count execution
    # identities, not ledger rows, when comparing against the graph.
    expected_capability_counts: dict[str, int] = {}
    seen_capability_executions: set[tuple[str, str]] = set()
    for obligation in required_obligations:
        capability = normalize_capability(obligation.get('capability'))
        if not capability:
            continue
        execution_identity = str(
            obligation.get('branch_id')
            or obligation.get('phase_id')
            or ''
        ).strip()
        if execution_identity:
            identity_key = (capability, execution_identity)
            if identity_key in seen_capability_executions:
                continue
            seen_capability_executions.add(identity_key)
        try:
            obligation_count = int(obligation.get('count') or 1)
        except (TypeError, ValueError):
            obligation_count = 1
        expected_capability_counts[capability] = (
            expected_capability_counts.get(capability, 0)
            + max(1, obligation_count)
        )
    if suppress_visual_artifact_execution:
        expected_capability_counts.pop(CAPABILITY_IMAGE_GENERATION, None)
    if suppress_visual_analysis_execution:
        expected_capability_counts.pop(CAPABILITY_VISION_ANALYSIS, None)
    if (
        prompt_intent.get('requests_speech_to_text_output')
        or normalize_capability(prompt_intent.get('primary_capability')) == CAPABILITY_SPEECH_TO_TEXT
        or CAPABILITY_SPEECH_TO_TEXT in downstream_capabilities
    ):
        expected_capability_counts[CAPABILITY_SPEECH_TO_TEXT] = max(
            expected_capability_counts.get(CAPABILITY_SPEECH_TO_TEXT, 0),
            1,
        )
    for capability, expected_count in sorted(expected_capability_counts.items()):
        actual_count = graph_capability_counts.get(capability, 0)
        if actual_count >= expected_count:
            continue
        checks.append(
            {
                'check_kind': 'intent_graph_adequacy',
                'obligation_id': f'missing-obligation-{capability}',
                'capability': capability,
                'output_type': artifact_type_for_capability(capability),
                'status': 'pending',
                'evidence': 'intent_graph_adequacy_missing_capability_obligation',
                'expected_count': expected_count,
                'actual_count': actual_count,
                'missing_count': expected_count - actual_count,
            }
        )

    required_intent_obligation_count = int(
        required_intent_summary.get('required_count') or 0
    )
    phase_lookup: dict[str, Mapping[str, Any]] = {}
    for collection_key in ('phases', 'downstream_branches'):
        collection = request_phase_graph.get(collection_key)
        if not isinstance(collection, list):
            continue
        for record in collection:
            if not isinstance(record, Mapping):
                continue
            for record_id in (
                str(record.get('phase_id') or '').strip(),
                str(record.get('branch_id') or '').strip(),
                str(record.get('obligation_id') or '').strip(),
            ):
                if record_id and record_id not in phase_lookup:
                    phase_lookup[record_id] = record

    for obligation in required_obligations:
        kind = str(obligation.get('kind') or '').strip().lower()
        obligation_id = str(obligation.get('obligation_id') or '').strip()
        if kind == 'text_artifact':
            target_name = str(obligation.get('target_name') or '').strip().lower()
            target_extension = str(obligation.get('target_extension') or '').strip().lower()
            if not target_name or not target_extension:
                continue
            matched = False
            for record in phase_lookup.values():
                if (
                    str(record.get('text_artifact_source_name') or '').strip().lower() == target_name
                    and str(record.get('text_artifact_extension') or '').strip().lower() == target_extension
                ):
                    matched = True
                    break
            if not matched:
                checks.append(
                    {
                        'check_kind': 'intent_graph_adequacy',
                        'obligation_id': obligation_id or f'missing-text-artifact-{target_name}-{target_extension}',
                        'intent_obligation_id': obligation_id,
                        'capability': CAPABILITY_CHAT,
                        'output_type': 'text',
                        'status': 'pending',
                        'evidence': 'intent_graph_adequacy_missing_text_artifact_obligation',
                        'target_name': target_name,
                        'target_extension': target_extension,
                        'repair_action': 'repair_missing_materialization_contract',
                    }
                )
            continue
        if kind != 'dependency' or not obligation.get('execution_dependency_required'):
            continue
        target_phase_id = str(
            obligation.get('target_phase_id') or obligation.get('target_branch_id') or ''
        ).strip()
        source_phase_ids = [
            str(item or '').strip()
            for item in (obligation.get('source_phase_ids') or [])
            if str(item or '').strip()
        ]
        if not target_phase_id or not source_phase_ids:
            continue
        target_record = phase_lookup.get(target_phase_id)
        actual_dependencies = [
            str(item or '').strip()
            for item in ((target_record or {}).get('depends_on') or [])
            if str(item or '').strip()
        ]
        missing_dependencies = [
            source_phase_id
            for source_phase_id in source_phase_ids
            if source_phase_id not in actual_dependencies
        ]
        if not target_record or missing_dependencies:
            checks.append(
                {
                    'check_kind': 'intent_graph_adequacy',
                    'obligation_id': obligation_id or f'missing-dependency-{target_phase_id}',
                    'intent_obligation_id': obligation_id,
                    'status': 'pending',
                    'evidence': 'intent_graph_adequacy_missing_dependency_edge',
                    'dependency_contract': obligation.get('dependency_contract'),
                    'target_phase_id': target_phase_id,
                    'source_phase_ids': source_phase_ids,
                    'missing_source_phase_ids': missing_dependencies or source_phase_ids,
                    'actual_depends_on': actual_dependencies,
                    'repair_action': 'rebind_artifact_dependency',
                    'add_dependencies': [
                        {
                            'target_phase_id': target_phase_id,
                            'source_phase_id': source_phase_id,
                            'dependency_contract': obligation.get('dependency_contract'),
                        }
                        for source_phase_id in (missing_dependencies or source_phase_ids)
                    ],
                }
            )

    intent_lens_review, intent_lens_checks = _build_intent_lens_review(
        prompt=prompt,
        prompt_intent=prompt_intent,
        request_phase_graph=request_phase_graph,
        intent_obligations=intent_obligations,
        expected_counts=expected_counts,
        expected_capability_counts=expected_capability_counts,
        existing_structural_gap_count=len(checks),
    )
    checks.extend(intent_lens_checks)

    open_checks = [
        item
        for item in checks
        if str(item.get('status') or '').strip().lower() in {
            'pending',
            'planned',
            'active',
            'deferred',
            'blocked',
        }
    ]
    if open_checks:
        status = 'pending'
        reason = 'graph/IR does not fully cover current user intent'
    elif (
        expected_counts
        or expected_capability_counts
        or required_intent_obligation_count
        or str(intent_lens_review.get('status') or '').strip().lower() != 'not_applicable'
    ):
        status = 'fulfilled'
        reason = 'graph/IR covers current materialization intent'
    else:
        status = 'not_applicable'
        reason = 'current intent has no material output requirement'
    payload = {
        'kind': 'fruth.intent_graph_adequacy_review',
        'status': status,
        'reason': reason,
        'expected_output_counts': expected_counts,
        'graph_output_counts': graph_counts,
        'expected_capability_counts': expected_capability_counts,
        'graph_capability_counts': graph_capability_counts,
        'intent_obligation_count': len(intent_obligations),
        'required_intent_obligation_count': required_intent_obligation_count,
        'required_intent_capabilities': list(
            required_intent_summary.get('capabilities') or []
        ),
        'intent_obligation_kinds': list(
            dict.fromkeys(
                str(item.get('kind') or '').strip()
                for item in intent_obligations
                if str(item.get('kind') or '').strip()
            )
        ),
        'checks': checks,
    }
    if intent_lens_review:
        payload['intent_lens_review'] = intent_lens_review
    return payload


def _compact_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in dict(value or {}).items()
        if item not in (None, '', [], {})
    }
