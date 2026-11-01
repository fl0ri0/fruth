"""Construct response frames and reconcile accepted outputs before persistence.

Consumes request/runtime records and existing artifact services. Ledger, Index,
CAS sidecar writing, successor version assignment and durability stay with the
response frame storage owner. Construction alone is never a commit receipt.
"""

from __future__ import annotations

from fruth_services.artifact_contracts import (
    _projection_token,
    _artifact_projection_type,
    _artifact_type_aliases,
)

from fruth_services.state_flow import observe_state
import json
import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Optional
from fruth_inference.request_phase_graph import build_request_phase_graph
from fruth_orchestration.working_frame import build_working_frame
from fruth_services.artifact_dossiers import build_artifact_dossier_index
from fruth_services.control_snapshots import build_control_snapshot
from fruth_services.frame_planning import build_artifact_flow_plan
from fruth_services.redraw_scope import (
    apply_artifact_identity_to_outputs,
    canonicalize_duplicate_artifact_refs,
)
from fruth_services.responses import (
    build_canonical_response_artifacts,
    build_canonical_outputs,
    build_public_output_branches_from_slots,
    extract_responses_current_turn_prompt,
    request_intent_frame_source,
    filter_public_response_artifacts,
    merge_canonical_response_artifacts,
    output_artifact_is_qualified,
    project_truth_guard_text,
    response_item_is_internal_control_work,
    response_text_is_internal_control_protocol,
    select_public_output_text as select_canonical_public_output_text,
)


RESPONSE_FRAME_VERSION = 9


_OUTPUT_SLOT_STATUS_SCORES = {
    'fulfilled': 12,
    'completed': 12,
    'blocked': 8,
    'failed': 8,
    'cancelled': 8,
    'waived': 8,
    'superseded': 8,
    'pending': 2,
    'queued': 2,
    'running': 2,
    'scheduled': 2,
}


_TERMINAL_OUTPUT_STATUSES = {
    'blocked',
    'cancelled',
    'completed',
    'failed',
    'fulfilled',
    'skipped',
    'superseded',
    'waived',
}


_CURRENT_STATE_FRAME_KEYS = (
    'id',
    'object',
    'status',
    'lifecycle_state',
    'canonical_status_field',
    'status_compatibility',
    'status_semantics',
    'mode',
    'instance_id',
    'model',
    'request_model',
    'backend',
    'capability',
    'output_text',
    'output',
    'result',
    'outputs',
    'output_slots',
    'output_branches',
    'work_tree',
    'artifacts',
    'input_artifacts',
    'reference_artifacts',
    'late_fill',
    'runtime',
    'saved_text_path',
    'saved_text_artifacts',
    'text_artifact_requests',
    'text_artifact_binding_errors',
    'saved_audio_path',
    'saved_image_path',
    'image_state',
    'audio_mimetype',
    'tts_audio_integrity_evidence',
    'seed',
    'provenance_id',
    'message_id',
    'route_source',
    'route_reason',
    'route_confidence',
    'route_reuse_last_artifact',
    'route_artifact_ref',
    'route_artifact_path',
    'usage',
    'lang_code',
    'lang_code_source',
    'response_format',
    'output_format',
    'error',
    'error_detail',
    'error_ref',
    'recovery_hint',
)


_REQUEST_FRAME_KEYS = (
    'content_requirement_policy',
    'content_review_reference_policy',
    'request_id',
    'conversation_id',
    'instance_id',
    'model',
    'request_model',
    'backend',
    'capability',
    'mode',
    'prompt',
    'input',
    'instructions',
    'file_path',
    'batch_prompts',
    'inference_route',
    'inference_preview',
    'current_predecessor_context',
    'request_meta',
    'reference_artifacts',
    'selected_reference_artifacts',
    'context_candidates',
    'memory_candidates',
    'history_candidates',
    'reference_candidates',
    'input_artifacts',
    'stream',
    'intent_source',
    'execution_prompt',
    'text_artifact_requests',
    'artifact_request',
    'text_artifact_extension',
    'text_artifact_source_name',
    'text_artifact_source',
    'text_artifact_target_path',
    'execution_contract',
    'branch_id',
    'phase_id',
    'output_type',
    'depends_on',
    'input_refs',
)


_REQUEST_FRAME_DIRECT_KEYS = tuple(
    key for key in _REQUEST_FRAME_KEYS if key != 'inference_preview'
)


_INFERENCE_PREVIEW_AUDIT_TEXT_LIMIT = 512


_INFERENCE_PREVIEW_AUDIT_ITEM_LIMIT = 16


_INFERENCE_PREVIEW_AUDIT_KEY_LIMIT = 128


_INFERENCE_PREVIEW_AUDIT_SCAN_LIMIT = 64


_INFERENCE_PREVIEW_INSTANCE_KEYS = (
    'instance_id',
    'model',
    'backend',
    'capability',
    'supported_capabilities',
    'text_capable',
    'backend_package',
    'backend_contract',
    'provider_capabilities',
    'tts_model_type',
    'tts_speakers',
    'tts_languages',
    'readiness',
    'activity',
)


_INFERENCE_PREVIEW_ROUTE_KEYS = (
    'source',
    'reason',
    'confidence',
    'reuse_last_artifact',
    'artifact_ref',
    'artifact_path',
    'context_mode',
    'context_reason',
)


_INFERENCE_PREVIEW_REQUEST_META_KEYS = (
    'semantic_role_ids',
    'semantic_role_ids_source',
    'capability_hint',
    'capability_hint_source',
    'language_hint',
    'language_hint_source',
    'source',
    'case_id',
    'corpus_id',
    'corpus_digest',
    'wave',
    'workload_family',
)


_INFERENCE_PREVIEW_DEVELOPER_DIAGNOSTIC_KEYS = (
    'routing_contract',
    'routing_policy',
    'heuristic_role',
    'embedding_signals_enabled',
    'accepted_learning_authority',
    'planner_timeout_ms',
    'planner_timeout_sec',
)


_INFERENCE_PREVIEW_LEGACY_KEYS = (
    'instance_id',
    'instanceId',
    'capability',
    'reuse_last_artifact',
    'artifact_ref',
    'artifactRef',
    'artifact_path',
    'confidence',
    'reason',
    'route_source',
    'routeSource',
)


_TARGET_FRAME_KEYS = (
    'instance_id',
    'model',
    'backend',
    'capability',
    'mode',
)


_ROUTE_FRAME_KEYS = (
    'route_source',
    'route_reason',
    'route_confidence',
    'route_reuse_last_artifact',
    'route_artifact_ref',
    'route_artifact_path',
    'route_traits',
)


def _is_empty(value: Any) -> bool:
    return value is None or value == '' or value == [] or value == {}


def _json_safe(value: Any) -> Any:
    # Parsed JSON dominates large Index/Readiness reads. Exact built-in values
    # need no protocol checks; subclasses and other inputs keep the same path.
    value_type = type(value)
    if (
        value is None or value_type is str or value_type is int
        or value_type is float or value_type is bool
    ):
        return value
    if value_type is dict or isinstance(value, Mapping):
        payload: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key or '').strip()
            if not key or key in {'response_frame', 'image_data_url', 'imageDataUrl'}:
                continue
            if _is_empty(raw_value):
                continue
            payload[key] = _json_safe(raw_value)
        return payload
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value if not _is_empty(item)]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _select_frame_keys(source: Mapping[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in keys:
        if key not in source:
            continue
        value = source.get(key)
        if _is_empty(value):
            continue
        payload[key] = _json_safe(value)
    return payload


def _bounded_inference_preview_scalar(value: Any) -> Any:
    if isinstance(value, Path):
        value = str(value)
    if isinstance(value, str):
        if len(value) <= _INFERENCE_PREVIEW_AUDIT_TEXT_LIMIT:
            return value
        return f'{value[:_INFERENCE_PREVIEW_AUDIT_TEXT_LIMIT - 3]}...'
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return None


def _bounded_inference_preview_key(value: Any) -> Optional[str]:
    key = str(value or '').strip()
    if not key or len(key) > _INFERENCE_PREVIEW_AUDIT_KEY_LIMIT:
        return None
    return key


def _inference_preview_content_digest_ref(value: Any, *, json_path: str) -> dict[str, Any]:
    encoded = json.dumps(
        _json_safe(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return {
        'kind': 'fruth.inference_preview_content_digest_ref',
        'json_path': json_path,
        'sha256': hashlib.sha256(encoded).hexdigest(),
        'size_bytes': len(encoded),
        'content_addressed': True,
        'storage': 'digest_only',
        'authority': 'audit_identity_only',
    }


def _compact_inference_preview_scalar_mapping(
    value: Any,
    *,
    preferred_keys: tuple[str, ...] = (),
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    source = value
    compact: dict[str, Any] = {}
    seen_keys: set[str] = set()
    ordered_items: list[tuple[str, Any]] = []
    for preferred_key in preferred_keys:
        if preferred_key in source and preferred_key not in seen_keys:
            seen_keys.add(preferred_key)
            ordered_items.append((preferred_key, source.get(preferred_key)))
    scanned_unknown = 0
    for raw_key, raw in source.items():
        key = _bounded_inference_preview_key(raw_key)
        if key is None or key in seen_keys:
            continue
        scanned_unknown += 1
        if scanned_unknown > _INFERENCE_PREVIEW_AUDIT_SCAN_LIMIT:
            break
        seen_keys.add(key)
        ordered_items.append((key, raw))
    for key, raw in ordered_items:
        if len(compact) >= _INFERENCE_PREVIEW_AUDIT_ITEM_LIMIT:
            break
        if raw in (None, '', [], {}):
            continue
        if isinstance(raw, (list, tuple)):
            items = [
                bounded
                for item in raw[:_INFERENCE_PREVIEW_AUDIT_ITEM_LIMIT]
                if (bounded := _bounded_inference_preview_scalar(item)) not in (None, '')
            ]
            if items:
                compact[key] = items
            continue
        bounded = _bounded_inference_preview_scalar(raw)
        if bounded not in (None, ''):
            compact[key] = bounded
    return compact


def _inference_preview_omitted_key_summary(
    value: Any,
    *,
    retained_keys: set[str],
) -> tuple[int, list[str]]:
    if not isinstance(value, Mapping):
        return 0, []
    count = 0
    keys: list[str] = []
    for raw_key, item in value.items():
        key = _bounded_inference_preview_key(raw_key)
        if key in retained_keys or item in (None, '', [], {}):
            continue
        count += 1
        if key is not None and len(keys) < _INFERENCE_PREVIEW_AUDIT_ITEM_LIMIT:
            keys.append(key)
    return count, sorted(keys)


def _compact_request_inference_preview(value: Any) -> Optional[dict[str, Any]]:
    """Keep route identity/audit truth without duplicating orchestration bodies."""

    if not isinstance(value, Mapping):
        return None
    preview = value
    payload = _compact_inference_preview_scalar_mapping(
        preview,
        preferred_keys=_INFERENCE_PREVIEW_LEGACY_KEYS,
    )

    instance_source = preview.get('instance') if isinstance(preview.get('instance'), Mapping) else {}
    instance = _compact_inference_preview_scalar_mapping(
        instance_source,
        preferred_keys=_INFERENCE_PREVIEW_INSTANCE_KEYS,
    )
    if instance_source:
        for key in ('backend_metadata', 'backend_runtime', 'session_controls', 'session_controls_summary'):
            nested = _compact_inference_preview_scalar_mapping(instance_source.get(key))
            if nested:
                instance[key] = nested
    if instance:
        payload['instance'] = instance

    route = _compact_inference_preview_scalar_mapping(
        preview.get('route'),
        preferred_keys=_INFERENCE_PREVIEW_ROUTE_KEYS,
    )
    route_source = preview.get('route') if isinstance(preview.get('route'), Mapping) else {}
    route_traits = _compact_inference_preview_scalar_mapping(route_source.get('traits'))
    if route_traits:
        route['traits'] = route_traits
    if route:
        payload['route'] = route

    request_meta = _compact_inference_preview_scalar_mapping(
        preview.get('request_meta'),
        preferred_keys=_INFERENCE_PREVIEW_REQUEST_META_KEYS,
    )
    request_meta_source = (
        preview.get('request_meta')
        if isinstance(preview.get('request_meta'), Mapping)
        else {}
    )
    developer_flags = _compact_inference_preview_scalar_mapping(
        request_meta_source.get('developer_flags')
    )
    if developer_flags:
        request_meta['developer_flags'] = developer_flags
    if request_meta:
        payload['request_meta'] = request_meta

    runtime = preview.get('runtime') if isinstance(preview.get('runtime'), Mapping) else {}
    diagnostics_source = (
        runtime.get('developer_diagnostics')
        if isinstance(runtime.get('developer_diagnostics'), Mapping)
        else {}
    )
    diagnostics = _compact_inference_preview_scalar_mapping(
        diagnostics_source,
        preferred_keys=_INFERENCE_PREVIEW_DEVELOPER_DIAGNOSTIC_KEYS,
    )
    route_graph_consistency = _compact_inference_preview_scalar_mapping(
        diagnostics_source.get('route_graph_consistency')
    )
    if route_graph_consistency:
        diagnostics['route_graph_consistency'] = route_graph_consistency
    if diagnostics:
        payload['runtime'] = {'developer_diagnostics': diagnostics}

    prior_compaction = preview.get('compaction')
    if (isinstance(prior_compaction, Mapping)
            and prior_compaction.get('kind') == 'fruth.inference_preview_response_frame_projection'
            and prior_compaction.get('policy') == 'route_identity_and_bounded_routing_audit_only'
            and payload == {key: item for key, item in preview.items() if key != 'compaction'}):
        # An already projected canonical request has no new omissions. Retain
        # its original audit provenance across control/successor freezes instead
        # of replacing it with diagnostics about this second compaction pass.
        payload['compaction'] = dict(prior_compaction)
        return _json_safe(payload)

    retained_preview_keys = set(payload)
    retained_preview_keys.add('compaction')
    omitted_preview_key_count, omitted_preview_keys = _inference_preview_omitted_key_summary(
        preview,
        retained_keys=retained_preview_keys,
    )
    omitted_runtime_key_count, omitted_runtime_keys = _inference_preview_omitted_key_summary(
        runtime,
        retained_keys={'developer_diagnostics'},
    )
    omitted_diagnostic_key_count, omitted_diagnostic_keys = _inference_preview_omitted_key_summary(
        diagnostics_source,
        retained_keys=set(diagnostics),
    )
    detail_omission_count = 0
    detail_omission_paths: list[str] = []
    detail_omission_counts_by_path: dict[str, int] = {}
    detail_sources: list[tuple[str, Mapping[str, Any], Mapping[str, Any]]] = [
        ('inference_preview.instance', instance_source, instance),
        ('inference_preview.route', route_source, route),
        ('inference_preview.request_meta', request_meta_source, request_meta),
    ]
    developer_flags_source = (
        request_meta_source.get('developer_flags')
        if isinstance(request_meta_source.get('developer_flags'), Mapping)
        else {}
    )
    if developer_flags:
        detail_sources.append(
            ('inference_preview.request_meta.developer_flags', developer_flags_source, developer_flags)
        )
    route_graph_consistency_source = (
        diagnostics_source.get('route_graph_consistency')
        if isinstance(diagnostics_source.get('route_graph_consistency'), Mapping)
        else {}
    )
    if route_graph_consistency:
        detail_sources.append(
            (
                'inference_preview.runtime.developer_diagnostics.route_graph_consistency',
                route_graph_consistency_source,
                route_graph_consistency,
            )
        )
    for key in ('backend_metadata', 'backend_runtime', 'session_controls', 'session_controls_summary'):
        nested_source = instance_source.get(key) if isinstance(instance_source.get(key), Mapping) else {}
        nested_compact = instance.get(key) if isinstance(instance.get(key), Mapping) else {}
        if nested_compact:
            detail_sources.append((f'inference_preview.instance.{key}', nested_source, nested_compact))
    route_traits_source = route_source.get('traits') if isinstance(route_source.get('traits'), Mapping) else {}
    if route_traits:
        detail_sources.append(('inference_preview.route.traits', route_traits_source, route_traits))
    for base_path, detail_source, detail_compact in detail_sources:
        omitted_count, omitted_keys = _inference_preview_omitted_key_summary(
            detail_source,
            retained_keys=set(detail_compact),
        )
        detail_omission_counts_by_path[base_path] = omitted_count
        detail_omission_count += omitted_count
        for key in omitted_keys:
            if len(detail_omission_paths) >= _INFERENCE_PREVIEW_AUDIT_ITEM_LIMIT:
                break
            detail_omission_paths.append(f'{base_path}.{key}')

    content_digest_refs: list[dict[str, Any]] = []
    working_frame_source = (
        preview.get('working_frame')
        if isinstance(preview.get('working_frame'), Mapping)
        else {}
    )
    if working_frame_source:
        content_digest_refs.append(
            _inference_preview_content_digest_ref(
                working_frame_source,
                json_path='inference_preview.working_frame',
            )
        )
    runtime_detail_omitted = any(
        count > 0 and path.startswith('inference_preview.runtime.')
        for path, count in detail_omission_counts_by_path.items()
    )
    if runtime and (
        omitted_runtime_key_count
        or omitted_diagnostic_key_count
        or runtime_detail_omitted
    ):
        content_digest_refs.append(
            _inference_preview_content_digest_ref(runtime, json_path='inference_preview.runtime')
        )
    for json_path, source_value in (
        ('inference_preview.instance', instance_source),
        ('inference_preview.route', route_source),
        ('inference_preview.request_meta', request_meta_source),
    ):
        source_detail_omitted = any(
            count > 0 and (path == json_path or path.startswith(f'{json_path}.'))
            for path, count in detail_omission_counts_by_path.items()
        )
        if source_value and source_detail_omitted:
            content_digest_refs.append(
                _inference_preview_content_digest_ref(source_value, json_path=json_path)
            )
    payload['compaction'] = {
        'kind': 'fruth.inference_preview_response_frame_projection',
        'policy': 'route_identity_and_bounded_routing_audit_only',
        'duplicate_orchestration_truth_omitted': bool(
            working_frame_source
            or omitted_runtime_key_count
            or omitted_diagnostic_key_count
        ),
        'preview_detail_omitted': bool(
            omitted_preview_key_count
            or omitted_runtime_key_count
            or omitted_diagnostic_key_count
            or detail_omission_count
        ),
        'canonical_response_truth_paths': [
            'runtime',
            'planning.request_phase_graph',
            'working_frame',
        ],
        'omitted_preview_key_count': omitted_preview_key_count,
        'omitted_preview_keys': omitted_preview_keys,
        'omitted_runtime_key_count': omitted_runtime_key_count,
        'omitted_runtime_keys': omitted_runtime_keys,
        'omitted_developer_diagnostic_key_count': omitted_diagnostic_key_count,
        'omitted_developer_diagnostic_keys': omitted_diagnostic_keys,
        'omitted_nested_detail_count': detail_omission_count,
        'omitted_nested_detail_paths': sorted(detail_omission_paths),
        'omitted_content_refs': content_digest_refs,
    }
    return _json_safe(payload)


def _build_request_frame(request_payload: Optional[Mapping[str, Any]], response_payload: Mapping[str, Any]) -> dict[str, Any]:
    source = request_intent_frame_source(request_payload) if isinstance(request_payload, Mapping) else {}
    payload = _select_frame_keys(source, _REQUEST_FRAME_DIRECT_KEYS)
    inference_preview = _compact_request_inference_preview(source.get('inference_preview'))
    if inference_preview:
        payload['inference_preview'] = inference_preview
    if not payload and isinstance(response_payload.get('request_meta'), Mapping):
        payload['request_meta'] = _json_safe(response_payload.get('request_meta'))
    input_artifacts = response_payload.get('input_artifacts')
    if 'input_artifacts' not in payload and isinstance(input_artifacts, list) and input_artifacts:
        payload['input_artifacts'] = _json_safe(input_artifacts)
    reference_artifacts = response_payload.get('reference_artifacts')
    if 'reference_artifacts' not in payload:
        if isinstance(reference_artifacts, list) and reference_artifacts:
            payload['reference_artifacts'] = _json_safe(reference_artifacts)
        else:
            legacy_references = (
                source.get('reference_artifacts')
                if isinstance(source.get('reference_artifacts'), list)
                else (
                    source.get('selected_reference_artifacts')
                    if isinstance(source.get('selected_reference_artifacts'), list)
                    else None
                )
            )
            if isinstance(legacy_references, list) and legacy_references:
                payload['reference_artifacts'] = _json_safe(legacy_references)
    return payload


def _build_error_frame(response_payload: Mapping[str, Any]) -> Optional[dict[str, Any]]:
    error_detail = response_payload.get('error_detail')
    if isinstance(error_detail, Mapping):
        return _json_safe(error_detail)
    error_value = response_payload.get('error')
    if isinstance(error_value, Mapping):
        return _json_safe(error_value)
    if not _is_empty(error_value):
        return {'message': str(error_value)}
    status = str(response_payload.get('status') or '').strip().lower()
    if status in {'failed', 'error', 'cancelled'}:
        return {'message': 'Request failed.'}
    return None


@observe_state('response_frame.runtime_copy', 'response_payload', 'frame_runtime_subtree', labels=('NEW_REPRESENTATION',), full_normalization=True)
def _build_runtime_frame(response_payload: Mapping[str, Any]) -> dict[str, Any]:
    runtime = dict(response_payload.get('runtime') or {}) if isinstance(response_payload.get('runtime'), Mapping) else {}
    runtime.pop('working_frame', None)
    return _json_safe(runtime)


def _select_public_output_text(
    response_payload: Mapping[str, Any],
    outputs: Any,
) -> str:
    fallback = str(response_payload.get('output_text') or '').strip()
    return select_canonical_public_output_text(response_payload, outputs, fallback_text=fallback)


def _response_truth_guard(response_payload: Mapping[str, Any]) -> Mapping[str, Any]:
    runtime = response_payload.get('runtime') if isinstance(response_payload.get('runtime'), Mapping) else {}
    truth_guard = runtime.get('truth_guard') if isinstance(runtime.get('truth_guard'), Mapping) else {}
    return truth_guard


def _response_truth_guard_requires_clarification(response_payload: Mapping[str, Any]) -> bool:
    truth_guard = _response_truth_guard(response_payload)
    return str(truth_guard.get('status') or '').strip().lower() in {
        'clarification_required',
        'repair_required',
    }


def _slot_is_root_text_output(slot: Mapping[str, Any]) -> bool:
    slot_type = str(slot.get('type') or '').strip().lower()
    if slot_type not in {'text', 'document'}:
        return False
    if str(slot.get('parent_slot_id') or '').strip():
        return False
    if str(slot.get('follow_up_capability') or '').strip():
        return False
    branch_id = str(slot.get('branch_id') or '').strip()
    phase_id = str(slot.get('phase_id') or '').strip()
    slot_id = str(slot.get('slot_id') or '').strip()
    if branch_id.startswith(('branch-', 'repair-')):
        return False
    if phase_id and phase_id not in {'phase-1', 'current'} and not phase_id.endswith('-1'):
        return False
    if slot_id and slot_id.startswith('output-phase-') and slot_id not in {'output-phase-1'}:
        return False
    return True


def _slot_is_deferred_materialization(slot: Mapping[str, Any]) -> bool:
    if str(slot.get('parent_slot_id') or '').strip():
        return True
    if str(slot.get('follow_up_capability') or '').strip():
        return True
    branch_id = str(slot.get('branch_id') or '').strip()
    phase_id = str(slot.get('phase_id') or '').strip()
    return branch_id.startswith(('branch-', 'repair-')) or phase_id.startswith(('branch-', 'repair-'))


def _apply_truth_guard_to_output_slots(
    response_payload: Mapping[str, Any],
    output_slots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not output_slots or not _response_truth_guard_requires_clarification(response_payload):
        return output_slots
    truth_guard = _response_truth_guard(response_payload)
    truth_guard_status = str(truth_guard.get('status') or '').strip().lower()
    reason = (
        str(truth_guard.get('reason') or '').strip()
        or 'current turn needs a concrete source before materialization'
    )
    clarification = str(response_payload.get('output_text') or '').strip()
    guarded_slots: list[dict[str, Any]] = []
    for raw_slot in output_slots:
        if not isinstance(raw_slot, Mapping):
            continue
        slot = dict(raw_slot)
        if _slot_is_root_text_output(slot):
            if clarification:
                slot['value'] = clarification
                slot['content_payload'] = clarification
                slot['output_text'] = clarification
            slot['status'] = 'fulfilled'
            slot['lifecycle'] = 'materialized_output'
        elif _slot_is_deferred_materialization(slot) and not (
            str(slot.get('artifact_ref') or '').strip()
            or str(slot.get('artifact_path') or '').strip()
            or str(slot.get('saved_text_path') or '').strip()
            or str(slot.get('saved_audio_path') or '').strip()
            or str(slot.get('saved_image_path') or '').strip()
        ):
            slot['status'] = 'blocked'
            slot['lifecycle'] = 'blocked_output'
            slot['blocked_reason'] = reason
            slot['error_ref'] = {
                'branch_id': str(slot.get('branch_id') or slot.get('phase_id') or '').strip() or None,
                'code': (
                    'UPSTREAM_REPAIR_REQUIRED'
                    if truth_guard_status == 'repair_required'
                    else 'UPSTREAM_CLARIFICATION_REQUIRED'
                ),
                'stage': 'truth_guard',
            }
            slot['recovery_context'] = {
                'can_retry': False,
                'retry_scope': 'branch_contract',
                'suggested_action': 'repair_branch_contract',
                'preserve_intent': True,
            }
            slot.pop('placeholder_ref', None)
        guarded_slots.append(
            {
                key: value
                for key, value in slot.items()
                if value not in (None, '', [], {})
            }
        )
    return _json_safe(guarded_slots)


_ARTIFACT_BINDING_KEYS = (
    'branch_id',
    'phase_id',
    'slot_id',
    'obligation_id',
    'output_type',
)


_ARTIFACT_IDENTITY_KEYS = ('artifact_id', 'artifact_ref', 'ref')


_ARTIFACT_PATH_KEYS = (
    'path',
    'source_path',
    'artifact_path',
    'saved_text_path',
    'saved_audio_path',
    'saved_image_path',
    'saved_video_path',
)


_LATE_FILL_SAVED_PATH_KEYS = (
    ('saved_image_path', 'image'),
    ('saved_audio_path', 'audio'),
    ('saved_text_path', 'text'),
    ('saved_video_path', 'video'),
    ('path', ''),
    ('artifact_path', ''),
)


_NON_REBINDABLE_SLOT_STATUSES = {
    'blocked',
    'cancelled',
    'failed',
    'skipped',
    'superseded',
    'waived',
}




def _artifact_projection_path(record: Mapping[str, Any]) -> str:
    for key in _ARTIFACT_PATH_KEYS:
        token = _projection_token(record.get(key))
        if token:
            return token
    return ''






def _artifact_types_compatible(left: str, right: str) -> bool:
    if not left or not right:
        return True
    return bool(_artifact_type_aliases(left).intersection(_artifact_type_aliases(right)))


def _artifact_binding_tokens(record: Mapping[str, Any]) -> set[str]:
    tokens = {
        _projection_token(record.get('branch_id')),
        _projection_token(record.get('phase_id')),
        _projection_token(record.get('slot_id')),
        _projection_token(record.get('obligation_id')),
    }
    tokens.discard('')
    return tokens


def _late_fill_result_type_and_path(result: Mapping[str, Any]) -> tuple[str, str]:
    declared_type = _artifact_projection_type(result)
    for key, fallback_type in _LATE_FILL_SAVED_PATH_KEYS:
        path = _projection_token(result.get(key))
        if path:
            return declared_type or fallback_type, path
    return declared_type, ''


def _iter_late_fill_result_records(response_payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    late_fill = response_payload.get('late_fill') if isinstance(response_payload.get('late_fill'), Mapping) else {}
    records: list[Mapping[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for key in ('fill_results', 'completed_branches'):
        value = late_fill.get(key)
        if not isinstance(value, list):
            continue
        for raw_result in value:
            if not isinstance(raw_result, Mapping):
                continue
            _result_type, result_path = _late_fill_result_type_and_path(raw_result)
            signature = (
                _projection_token(raw_result.get('branch_id')),
                _projection_token(raw_result.get('phase_id')),
                result_path,
            )
            if signature in seen:
                continue
            seen.add(signature)
            records.append(raw_result)
    return records


def _conflicting_artifact_refs_by_path(artifacts: Any) -> set[str]:
    paths_by_ref: dict[str, set[str]] = {}
    if not isinstance(artifacts, list):
        return set()
    for raw_artifact in artifacts:
        if not isinstance(raw_artifact, Mapping):
            continue
        artifact_ref = _artifact_ref_from_projection(raw_artifact)
        artifact_path = _artifact_projection_path(raw_artifact)
        if not artifact_ref or not artifact_path:
            continue
        paths_by_ref.setdefault(artifact_ref, set()).add(artifact_path)
    return {
        artifact_ref
        for artifact_ref, paths in paths_by_ref.items()
        if len(paths) > 1
    }


def _canonical_artifacts_by_late_fill_path(
    response_payload: Mapping[str, Any],
    canonical_artifacts: Any,
) -> dict[str, Mapping[str, Any]]:
    late_fill_paths = {
        path
        for _result_type, path in (
            _late_fill_result_type_and_path(result)
            for result in _iter_late_fill_result_records(response_payload)
        )
        if path
    }
    if not late_fill_paths or not isinstance(canonical_artifacts, list):
        return {}
    artifacts_by_path: dict[str, Mapping[str, Any]] = {}
    for raw_artifact in canonical_artifacts:
        if not isinstance(raw_artifact, Mapping):
            continue
        artifact_path = _artifact_projection_path(raw_artifact)
        if artifact_path and artifact_path in late_fill_paths:
            artifacts_by_path.setdefault(artifact_path, raw_artifact)
    return artifacts_by_path


def _reconcile_output_artifacts_with_late_fill_branch_paths(
    response_payload: Mapping[str, Any],
    output_artifacts: Any,
    canonical_artifacts: Any,
) -> list[dict[str, Any]]:
    if not isinstance(output_artifacts, list) or not output_artifacts:
        return _json_safe(output_artifacts) if isinstance(output_artifacts, list) else []
    canonical_by_path = _canonical_artifacts_by_late_fill_path(response_payload, canonical_artifacts)
    if not canonical_by_path:
        return _json_safe(output_artifacts)
    conflicting_refs = _conflicting_artifact_refs_by_path(output_artifacts)
    reconciled: list[dict[str, Any]] = []
    for raw_artifact in output_artifacts:
        if not isinstance(raw_artifact, Mapping):
            continue
        artifact = dict(raw_artifact)
        artifact_path = _artifact_projection_path(artifact)
        canonical = canonical_by_path.get(artifact_path)
        if canonical and _artifact_types_compatible(
            _artifact_projection_type(artifact),
            _artifact_projection_type(canonical),
        ):
            current_ref = _artifact_ref_from_projection(artifact)
            canonical_ref = _artifact_ref_from_projection(canonical)
            for key in _ARTIFACT_BINDING_KEYS:
                value = canonical.get(key)
                if value not in (None, '', [], {}) and artifact.get(key) in (None, '', [], {}):
                    artifact[key] = value
            if current_ref in conflicting_refs and canonical_ref and canonical_ref != current_ref:
                for key in _ARTIFACT_IDENTITY_KEYS:
                    value = canonical.get(key)
                    if value not in (None, '', [], {}):
                        artifact[key] = value
        normalized = {
            key: value
            for key, value in artifact.items()
            if value not in (None, '', [], {})
        }
        if normalized:
            reconciled.append(normalized)
    return _json_safe(reconciled)


def _late_fill_artifacts_by_binding(
    response_payload: Mapping[str, Any],
    output_artifacts: Any,
) -> dict[tuple[str, str], Mapping[str, Any]]:
    if not isinstance(output_artifacts, list):
        return {}
    artifacts_by_path: dict[str, Mapping[str, Any]] = {}
    candidates_by_binding: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for raw_artifact in output_artifacts:
        if not isinstance(raw_artifact, Mapping):
            continue
        if not output_artifact_is_qualified(response_payload, raw_artifact):
            continue
        artifact_path = _artifact_projection_path(raw_artifact)
        if artifact_path:
            artifacts_by_path.setdefault(artifact_path, raw_artifact)
        artifact_type = _artifact_projection_type(raw_artifact)
        for token in _artifact_binding_tokens(raw_artifact):
            for alias in _artifact_type_aliases(artifact_type):
                candidates_by_binding.setdefault((token, alias), []).append(raw_artifact)

    for result in _iter_late_fill_result_records(response_payload):
        result_type, result_path = _late_fill_result_type_and_path(result)
        if not result_path:
            continue
        artifact = artifacts_by_path.get(result_path)
        if not artifact:
            continue
        artifact_type = _artifact_projection_type(artifact)
        if not _artifact_types_compatible(result_type, artifact_type):
            continue
        aliases = _artifact_type_aliases(result_type or artifact_type) or {artifact_type}
        for token in _artifact_binding_tokens(result):
            for alias in aliases:
                candidates_by_binding.setdefault((token, alias), []).append(artifact)
    # Collection and set iteration order cannot resolve competing identities.
    return {key: records[0] for key, records in candidates_by_binding.items()
            if len({(_artifact_ref_from_projection(record), _artifact_projection_path(record))
                    for record in records}) == 1}


def _reconcile_output_slots_with_late_fill_artifacts(
    response_payload: Mapping[str, Any],
    output_slots: list[dict[str, Any]],
    output_artifacts: Any,
) -> list[dict[str, Any]]:
    if not output_slots:
        return output_slots
    artifacts_by_binding = _late_fill_artifacts_by_binding(response_payload, output_artifacts)

    # An explicitly bound canonical/late-fill artifact has one owner (or a
    # bounded set of equivalent owner tokens). Persisted payload slots can
    # predate that binding and still carry the same ref/path on an earlier branch.
    # Aggregate the ownership evidence by artifact identity so reconciliation can
    # remove only those proven stale claims while leaving genuinely unbound
    # legacy refs untouched.
    ownership_by_identity: dict[tuple[str, str], dict[str, Any]] = {}
    for (owner_token, artifact_type), artifact in artifacts_by_binding.items():
        artifact_ref = _artifact_ref_from_projection(artifact)
        artifact_path = _artifact_projection_path(artifact)
        if not artifact_ref and not artifact_path:
            continue
        identity = ('ref', artifact_ref) if artifact_ref else ('path', artifact_path)
        ownership = ownership_by_identity.setdefault(
            identity,
            {
                'artifact_ref': artifact_ref,
                'artifact_paths': set(),
                'artifact_types': set(),
                'owner_tokens': set(),
            },
        )
        if artifact_path:
            ownership['artifact_paths'].add(artifact_path)
        if artifact_type:
            ownership['artifact_types'].add(artifact_type)
        ownership['owner_tokens'].add(owner_token)

    reconciled: list[dict[str, Any]] = []
    for raw_slot in output_slots:
        if not isinstance(raw_slot, Mapping):
            continue
        slot = dict(raw_slot)
        slot_type = _artifact_projection_type(slot)
        slot_types = _artifact_type_aliases(slot_type)
        slot_tokens = _artifact_binding_tokens(slot)

        for ownership in ownership_by_identity.values():
            owner_types = ownership['artifact_types']
            if slot_types and owner_types and not slot_types.intersection(owner_types):
                continue
            if slot_tokens.intersection(ownership['owner_tokens']):
                continue

            slot_ref = _artifact_ref_from_projection(slot)
            slot_path = _artifact_projection_path(slot)
            ref_matches = bool(ownership['artifact_ref'] and slot_ref == ownership['artifact_ref'])
            path_matches = bool(slot_path and slot_path in ownership['artifact_paths'])
            if not ref_matches and not path_matches:
                continue

            # A path match proves that any inline identity on the slot is the
            # same artifact, even when an older alias ref was persisted there.
            # A ref match likewise invalidates all direct identity aliases.
            for key in _ARTIFACT_IDENTITY_KEYS:
                slot.pop(key, None)
            for key in _ARTIFACT_PATH_KEYS:
                if _projection_token(slot.get(key)) in ownership['artifact_paths']:
                    slot.pop(key, None)

        matched_artifact = None
        for token in slot_tokens:
            for alias in slot_types:
                matched_artifact = artifacts_by_binding.get((token, alias))
                if matched_artifact and not output_artifact_is_qualified(
                    response_payload, matched_artifact, slot=slot,
                ):
                    matched_artifact = None
                if matched_artifact:
                    break
            if matched_artifact:
                break
        if matched_artifact:
            artifact_ref = _artifact_ref_from_projection(matched_artifact)
            artifact_path = _artifact_projection_path(matched_artifact)
            if artifact_ref:
                slot['artifact_ref'] = artifact_ref
            if artifact_path:
                slot['artifact_path'] = artifact_path
            status = _projection_token(slot.get('status')).lower()
            if status not in _NON_REBINDABLE_SLOT_STATUSES:
                slot['status'] = 'fulfilled'
                slot['lifecycle'] = 'materialized_output'
                slot.pop('blocked_reason', None)
            if _projection_token(slot.get('status')).lower() in _TERMINAL_OUTPUT_STATUSES:
                slot.pop('placeholder_ref', None)
        elif slot_type == 'image' and not output_artifact_is_qualified(
            response_payload, {**slot, 'type': 'image'}, slot=slot,
        ):
            for key in (*_ARTIFACT_IDENTITY_KEYS, *_ARTIFACT_PATH_KEYS):
                slot.pop(key, None)
            if _projection_token(slot.get('status')).lower() in {'fulfilled', 'completed'}:
                slot.update(status='pending', lifecycle='unresolved_output',
                            blocked_reason='accepted_image_evidence_unresolved')
        normalized = {
            key: value
            for key, value in slot.items()
            if value not in (None, '', [], {})
        }
        if normalized:
            reconciled.append(normalized)
    return _json_safe(reconciled)


def _output_slot_truth_score(slots: list[dict[str, Any]]) -> int:
    score = 0
    for raw_slot in slots:
        if not isinstance(raw_slot, Mapping):
            continue
        status = str(raw_slot.get('status') or '').strip().lower()
        score += _OUTPUT_SLOT_STATUS_SCORES.get(status, 0)
        if str(raw_slot.get('artifact_ref') or '').strip():
            score += 4
        if any(
            str(raw_slot.get(key) or '').strip()
            for key in ('artifact_path', 'path', 'saved_image_path', 'saved_audio_path', 'saved_text_path')
        ):
            score += 4
        if str(raw_slot.get('placeholder_ref') or '').strip():
            score -= 1
    return score


def _output_slots_should_refresh_from_plan(
    payload_slots: list[dict[str, Any]],
    plan_slots: list[dict[str, Any]],
) -> bool:
    if not payload_slots or not plan_slots:
        return False
    plan_score = _output_slot_truth_score(plan_slots)
    payload_score = _output_slot_truth_score(payload_slots)
    if plan_score <= payload_score:
        return False
    payload_open = any(
        str(slot.get('status') or '').strip().lower() in {'pending', 'queued', 'running', 'scheduled'}
        for slot in payload_slots
        if isinstance(slot, Mapping)
    )
    plan_materialized = any(
        str(slot.get('status') or '').strip().lower() in {'fulfilled', 'completed'}
        and any(
            str(slot.get(key) or '').strip()
            for key in ('artifact_ref', 'artifact_path', 'path', 'saved_image_path', 'saved_audio_path', 'saved_text_path')
        )
        for slot in plan_slots
        if isinstance(slot, Mapping)
    )
    return payload_open and plan_materialized


def _project_output_items_text(output_items: Any, output_text: str) -> list[dict[str, Any]]:
    text = str(output_text or '').strip()
    items = _json_safe(output_items) if isinstance(output_items, list) else []
    public_items: list[dict[str, Any]] = []
    for raw_item in items:
        if not isinstance(raw_item, Mapping):
            continue
        if response_item_is_internal_control_work(raw_item):
            continue
        content = raw_item.get('content') if isinstance(raw_item.get('content'), list) else []
        content_texts = [
            str(part.get('text') or '').strip()
            for part in content
            if isinstance(part, Mapping)
            and str(part.get('type') or '').strip() == 'output_text'
            and str(part.get('text') or '').strip()
        ]
        if content_texts and all(response_text_is_internal_control_protocol(value) for value in content_texts):
            continue
        public_items.append(dict(raw_item))
    items = public_items
    if not text:
        return items
    for item in items:
        content = item.get('content')
        if not isinstance(content, list):
            continue
        for content_item in content:
            if not isinstance(content_item, dict):
                continue
            if str(content_item.get('type') or '').strip() == 'output_text':
                content_item['text'] = text
                return _json_safe(items)
    if items:
        items[0]['content'] = [{'type': 'output_text', 'text': text, 'annotations': []}]
        return _json_safe(items)
    return [
        {
            'type': 'message',
            'status': 'completed',
            'role': 'assistant',
            'content': [{'type': 'output_text', 'text': text, 'annotations': []}],
        }
    ]


def _reconcile_output_branches_with_slots(
    output_branches: Any,
    output_slots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not output_slots:
        return _json_safe(
            [
                dict(branch)
                for branch in output_branches
                if isinstance(branch, Mapping)
                and not response_item_is_internal_control_work(branch)
            ]
        ) if isinstance(output_branches, list) else []
    slot_lookup: dict[str, Mapping[str, Any]] = {}
    for slot in output_slots:
        if not isinstance(slot, Mapping):
            continue
        for key in ('slot_id', 'branch_id', 'phase_id'):
            token = str(slot.get(key) or '').strip()
            if token:
                slot_lookup[token] = slot

    raw_branches = (
        output_branches
        if isinstance(output_branches, list) and output_branches
        else build_public_output_branches_from_slots(output_slots)
    )
    reconciled: list[dict[str, Any]] = []
    for raw_branch in raw_branches:
        if not isinstance(raw_branch, Mapping):
            continue
        if response_item_is_internal_control_work(raw_branch):
            continue
        branch = dict(raw_branch)
        matching_slot = None
        for key in ('slot_id', 'branch_id', 'phase_id'):
            token = str(branch.get(key) or '').strip()
            if token and token in slot_lookup:
                matching_slot = slot_lookup[token]
                break
        if matching_slot is not None:
            for key in (
                'slot_id',
                'branch_id',
                'phase_id',
                'obligation_id',
                'type',
                'status',
                'lifecycle',
                'follow_up_capability',
                'artifact_ref',
                'artifact_path',
                'blocked_reason',
                'parent_slot_id',
            ):
                value = matching_slot.get(key)
                if value not in (None, '', [], {}):
                    branch[key] = value
                elif key in {'artifact_ref', 'blocked_reason'}:
                    branch.pop(key, None)
            if isinstance(matching_slot.get('child_slot_ids'), list):
                branch['child_slot_ids'] = list(matching_slot.get('child_slot_ids') or [])
            if str(matching_slot.get('status') or '').strip().lower() in _TERMINAL_OUTPUT_STATUSES:
                branch.pop('placeholder_ref', None)
            elif str(matching_slot.get('placeholder_ref') or '').strip():
                branch['placeholder_ref'] = str(matching_slot.get('placeholder_ref') or '').strip()
        normalized = {
            key: value
            for key, value in branch.items()
            if value not in (None, '', [], {})
        }
        if normalized:
            reconciled.append(normalized)
    return _json_safe(reconciled)


@observe_state('response_frame.current_state_copy', 'response_payload', 'frame_current_state_subtree', labels=('NEW_REPRESENTATION',))
def _build_current_state_frame(
    response_payload: Mapping[str, Any],
    *,
    output_slots: list[dict[str, Any]],
    output_branches: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    work_tree: Mapping[str, Any],
    public_output_text: Optional[str] = None,
) -> dict[str, Any]:
    payload = _select_frame_keys(response_payload, _CURRENT_STATE_FRAME_KEYS)
    surface = response_payload.get('surface_state')
    if isinstance(surface, Mapping) and surface.get('content_requirement_policy') == 'named_saved_text_v1':
        from fruth_services.response_wire import surface_handle
        # Keep the scalar accounting beside the indexed state. Full Clause/
        # verdict evidence remains in the canonical runtime/CAS owner.
        payload['surface_state'] = surface_handle(surface)
    payload['id'] = str(response_payload.get('id') or response_payload.get('response_id') or '').strip() or None
    payload['status'] = str(response_payload.get('status') or '').strip() or None
    projected_output_items = _project_output_items_text(
        response_payload.get('output'),
        public_output_text or '',
    )
    if public_output_text:
        payload['output_text'] = public_output_text
    else:
        payload.pop('output_text', None)
    if projected_output_items:
        payload['output'] = projected_output_items
    else:
        payload.pop('output', None)
    if output_slots:
        payload['output_slots'] = _json_safe(output_slots)
    else:
        payload.pop('output_slots', None)
    if output_branches:
        payload['output_branches'] = _json_safe(output_branches)
    else:
        payload.pop('output_branches', None)
    if outputs:
        payload['outputs'] = _json_safe(outputs)
    else:
        payload.pop('outputs', None)
    result_value = payload.get('result')
    if (
        response_item_is_internal_control_work(result_value)
        if isinstance(result_value, Mapping)
        else response_text_is_internal_control_protocol(result_value)
    ):
        payload.pop('result', None)
    if isinstance(response_payload.get('artifacts'), list):
        public_artifacts = filter_public_response_artifacts(
            response_payload,
            response_payload.get('artifacts'),
            outputs=outputs,
        )
        if public_artifacts:
            payload['artifacts'] = _json_safe(public_artifacts)
        else:
            payload.pop('artifacts', None)
    if work_tree:
        payload['work_tree'] = _json_safe(work_tree)
    if isinstance(response_payload.get('late_fill'), Mapping):
        payload['late_fill'] = _json_safe(response_payload.get('late_fill'))
    if isinstance(response_payload.get('runtime'), Mapping):
        payload['runtime'] = _build_runtime_frame(response_payload)
    return {
        key: value
        for key, value in _json_safe(payload).items()
        if value not in (None, '', [], {})
    }


def _artifact_ref_from_projection(item: Mapping[str, Any]) -> str:
    direct = str(item.get('artifact_ref') or item.get('ref') or item.get('artifact_id') or '').strip()
    if direct:
        return direct
    artifacts = item.get('artifacts')
    if isinstance(artifacts, list):
        for artifact in artifacts:
            if not isinstance(artifact, Mapping):
                continue
            token = str(
                artifact.get('artifact_ref')
                or artifact.get('ref')
                or artifact.get('artifact_id')
                or ''
            ).strip()
            if token:
                return token
    artifact = item.get('artifact') if isinstance(item.get('artifact'), Mapping) else {}
    return str(
        artifact.get('artifact_ref')
        or artifact.get('ref')
        or artifact.get('artifact_id')
        or ''
    ).strip()


def _artifact_identity_summary(canonicalized: Mapping[str, Any]) -> dict[str, Any]:
    summary = {
        'canonicalization_required': canonicalized.get('canonicalization_required') or False,
        'duplicate_refs': canonicalized.get('duplicate_refs') or [],
        'final_projection_blocked': canonicalized.get('final_projection_blocked') or False,
        'conflicts': canonicalized.get('conflicts') or [],
    }
    return {
        key: _json_safe(value)
        for key, value in summary.items()
        if value not in (None, '', [], {})
    }


def prepare_response_output_state(
    response_payload: Mapping[str, Any],
    *,
    request_payload: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Reconcile current artifact and output truth without freezing a frame.

    Terminal materialization and frame construction use the same slot guards,
    branch bindings and artifact identity adjudication. A previous frame's
    pending output projection must not hide an accepted Late Fill result.
    """
    if not isinstance(response_payload, Mapping):
        raise TypeError('response_payload must be a mapping')
    request_frame = _build_request_frame(request_payload, response_payload)
    output_artifacts = response_payload.get('artifacts') if isinstance(response_payload.get('artifacts'), list) else []
    diagnostic_output_artifacts = [dict(artifact) for artifact in output_artifacts
                                  if isinstance(artifact, Mapping)
                                  and not output_artifact_is_qualified(response_payload, artifact)]
    output_artifacts = [artifact for artifact in output_artifacts
                        if isinstance(artifact, Mapping)
                        and output_artifact_is_qualified(response_payload, artifact)]
    canonical_artifacts = build_canonical_response_artifacts(dict(response_payload))
    canonical_artifacts = [artifact for artifact in canonical_artifacts
                           if output_artifact_is_qualified(response_payload, artifact)]
    if canonical_artifacts:
        output_artifacts = merge_canonical_response_artifacts(output_artifacts, canonical_artifacts)
    output_artifacts = _reconcile_output_artifacts_with_late_fill_branch_paths(
        response_payload,
        output_artifacts,
        canonical_artifacts,
    )
    if output_artifacts != response_payload.get('artifacts'):
        response_payload = {**dict(response_payload), 'artifacts': output_artifacts}
    input_artifacts = response_payload.get('input_artifacts') if isinstance(response_payload.get('input_artifacts'), list) else []
    reference_artifacts = response_payload.get('reference_artifacts') if isinstance(response_payload.get('reference_artifacts'), list) else []
    if not input_artifacts and isinstance(request_frame.get('input_artifacts'), list):
        input_artifacts = request_frame.get('input_artifacts') or []
    if not reference_artifacts and isinstance(request_frame.get('reference_artifacts'), list):
        reference_artifacts = request_frame.get('reference_artifacts') or []
    artifact_identity_canonicalization = canonicalize_duplicate_artifact_refs(output_artifacts)
    artifact_identity = _artifact_identity_summary(artifact_identity_canonicalization)
    if artifact_identity.get('canonicalization_required'):
        output_artifacts = artifact_identity_canonicalization.get('artifacts') or output_artifacts
    artifact_flow_plan = build_artifact_flow_plan(
        input_artifacts,
        output_artifacts,
        reference_artifacts=reference_artifacts,
        request_payload=request_frame,
        response_payload=response_payload,
    )
    plan_output_slots = artifact_flow_plan.get('output_slots') if isinstance(artifact_flow_plan.get('output_slots'), list) else []
    payload_output_slots = response_payload.get('output_slots') if isinstance(response_payload.get('output_slots'), list) else []
    artifact_flow_authoritative = bool(artifact_flow_plan.get('authoritative')) or (
        str(artifact_flow_plan.get('work_tree_source') or '').strip() == 'runtime_owned'
    )
    if artifact_flow_authoritative and plan_output_slots:
        output_slots = plan_output_slots
    elif _output_slots_should_refresh_from_plan(payload_output_slots, plan_output_slots):
        output_slots = plan_output_slots
    else:
        output_slots = payload_output_slots or plan_output_slots
    output_slots = project_truth_guard_text(response_payload, output_slots)
    output_slots = _apply_truth_guard_to_output_slots(response_payload, output_slots)
    output_slots = [
        dict(slot)
        for slot in output_slots
        if isinstance(slot, Mapping)
        and not response_item_is_internal_control_work(slot)
    ]
    output_slots = _reconcile_output_slots_with_late_fill_artifacts(
        response_payload,
        output_slots,
        output_artifacts,
    )
    if output_slots:
        artifact_flow_plan = dict(artifact_flow_plan)
        artifact_flow_plan['output_slots'] = output_slots
        artifact_flow_plan['steps'] = [
            {
                **dict(step),
                'status': next(
                    (
                        slot.get('status')
                        for slot in output_slots
                        if isinstance(slot, Mapping)
                        and str(slot.get('slot_id') or '').strip()
                        == str(step.get('slot_id') or '').strip()
                    ),
                    step.get('status'),
                ),
                'lifecycle': next(
                    (
                        slot.get('lifecycle')
                        for slot in output_slots
                        if isinstance(slot, Mapping)
                        and str(slot.get('slot_id') or '').strip()
                        == str(step.get('slot_id') or '').strip()
                    ),
                    step.get('lifecycle'),
                ),
            }
            if isinstance(step, Mapping) and str(step.get('slot_id') or '').strip()
            else step
            for step in (artifact_flow_plan.get('steps') or [])
        ] if isinstance(artifact_flow_plan.get('steps'), list) else []
    output_branches = _reconcile_output_branches_with_slots(
        response_payload.get('output_branches'),
        output_slots,
    )
    outputs = build_canonical_outputs(
        response_payload,
        output_slots=output_slots,
        artifacts=output_artifacts,
        output_branches=output_branches,
    )
    if not outputs and isinstance(response_payload.get('outputs'), list):
        outputs = [
            dict(output)
            for output in response_payload.get('outputs') or []
            if isinstance(output, Mapping)
            and not response_item_is_internal_control_work(output)
        ]
    outputs = apply_artifact_identity_to_outputs(
        outputs,
        artifact_identity=artifact_identity,
        canonical_artifacts=output_artifacts,
    )
    public_output_artifacts = filter_public_response_artifacts(
        response_payload,
        output_artifacts,
        outputs=outputs,
    )
    return {
        'response_payload': response_payload,
        'request_frame': request_frame,
        'input_artifacts': input_artifacts,
        'reference_artifacts': reference_artifacts,
        'output_artifacts': output_artifacts,
        'diagnostic_output_artifacts': diagnostic_output_artifacts,
        'public_output_artifacts': public_output_artifacts,
        'artifact_identity': artifact_identity,
        'artifact_flow_plan': artifact_flow_plan,
        'output_slots': output_slots,
        'output_branches': output_branches,
        'outputs': outputs,
    }


@observe_state('response_frame.build', 'live_response_record', 'response_frame_before_compaction', labels=('NEW_REPRESENTATION',))
def build_response_frame(
    response_payload: Mapping[str, Any],
    *,
    request_payload: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Build an auditable frozen frame from a canonical Responses payload."""

    if not isinstance(response_payload, Mapping):
        raise TypeError('response_payload must be a mapping')

    output_items = response_payload.get('output') if isinstance(response_payload.get('output'), list) else []
    prepared = prepare_response_output_state(response_payload, request_payload=request_payload)
    response_payload = prepared['response_payload']
    request_frame = prepared['request_frame']
    output_artifacts = prepared['output_artifacts']
    input_artifacts = prepared['input_artifacts']
    reference_artifacts = prepared['reference_artifacts']
    artifact_identity = prepared['artifact_identity']
    artifact_flow_plan = prepared['artifact_flow_plan']
    output_slots = prepared['output_slots']
    output_branches = prepared['output_branches']
    outputs = prepared['outputs']
    public_output_artifacts = prepared['public_output_artifacts']
    error_frame = _build_error_frame(response_payload)
    request_source = request_payload if isinstance(request_payload, Mapping) else request_frame
    artifact_dossiers = build_artifact_dossier_index(
        input_artifacts=input_artifacts,
        reference_artifacts=reference_artifacts,
        output_artifacts=output_artifacts,
        response_payload=response_payload,
    )
    # Rejected candidates remain inspectable without sharing a fulfillment ref
    # with the accepted dossier. The canonical dossier always owns that ref.
    diagnostic_dossiers = build_artifact_dossier_index(
        output_artifacts=prepared['diagnostic_output_artifacts'], response_payload=response_payload,
    )
    for ref, dossier in diagnostic_dossiers.items():
        if ref not in artifact_dossiers:
            artifact_dossiers[ref] = dossier
        artifact_dossiers[ref]['output_qualification'] = (
            'accepted_with_rejected_candidates' if ref in {_artifact_ref_from_projection(a) for a in output_artifacts}
            else 'rejected')
        artifact_dossiers[ref]['rejected_output_candidates'] = [
            artifact for artifact in prepared['diagnostic_output_artifacts']
            if _artifact_ref_from_projection(artifact) == ref]
    control_snapshot = build_control_snapshot(request_source, response_payload)
    runtime_payload = response_payload.get('runtime') if isinstance(response_payload.get('runtime'), Mapping) else {}
    runtime_request_phase_graph = (
        runtime_payload.get('request_phase_graph')
        if isinstance(runtime_payload.get('request_phase_graph'), Mapping)
        else None
    )
    request_phase_graph = (
        runtime_request_phase_graph
        if runtime_request_phase_graph
        else build_request_phase_graph(
            str(response_payload.get('output_text') or request_frame.get('prompt') or request_frame.get('input') or ''),
            intent_prompt=extract_responses_current_turn_prompt(request_source),
            request_payload=request_source,
            response_payload=response_payload,
        )
    )
    public_output_text = _select_public_output_text(response_payload, outputs)
    output_items = _project_output_items_text(output_items, public_output_text)
    working_frame = (
        response_payload.get('working_frame')
        if isinstance(response_payload.get('working_frame'), Mapping)
        else build_working_frame(
            request_payload=request_payload,
            response_payload=response_payload,
            freeze=True,
        )
    )

    frame: dict[str, Any] = {
        'frame_version': RESPONSE_FRAME_VERSION,
        'kind': 'fruth.response_frame',
        'response_id': str(response_payload.get('id') or '').strip() or None,
        'status': str(response_payload.get('status') or '').strip() or None,
        'object': str(response_payload.get('object') or '').strip() or None,
        'target': _select_frame_keys(response_payload, _TARGET_FRAME_KEYS),
        'route': _select_frame_keys(response_payload, _ROUTE_FRAME_KEYS),
        'runtime': _build_runtime_frame(response_payload),
        'request': request_frame,
        'artifacts': {
            'input': _json_safe(input_artifacts),
            'reference': _json_safe(reference_artifacts),
            'output': _json_safe(public_output_artifacts),
            'dossiers': _json_safe(artifact_dossiers),
            **({'identity': _json_safe(artifact_identity)} if artifact_identity else {}),
        },
        'memory_delta': _json_safe(response_payload.get('memory_delta')) if isinstance(response_payload.get('memory_delta'), Mapping) else {},
        'planning': {
            'intent_contract': _json_safe(
                working_frame.get('intent_contract')
                if isinstance(working_frame, Mapping) and isinstance(working_frame.get('intent_contract'), Mapping)
                else {}
            ),
            'context_contract': _json_safe(
                working_frame.get('context_contract')
                if isinstance(working_frame, Mapping) and isinstance(working_frame.get('context_contract'), Mapping)
                else {}
            ),
            'artifact_flow': _json_safe(artifact_flow_plan),
            'request_phase_graph': _json_safe(request_phase_graph),
            'work_tree': _json_safe(artifact_flow_plan.get('work_tree') or {}),
        },
        'output': {
            'text': public_output_text,
            'item_count': len(outputs) if outputs else len(output_items),
            'outputs': _json_safe(outputs),
            **({'artifact_identity': _json_safe(artifact_identity)} if artifact_identity else {}),
        },
        'current_state': _build_current_state_frame(
            response_payload,
            output_slots=output_slots,
            output_branches=output_branches,
            outputs=outputs,
            work_tree=artifact_flow_plan.get('work_tree') if isinstance(artifact_flow_plan.get('work_tree'), Mapping) else {},
            public_output_text=public_output_text,
        ),
        'working_frame': _json_safe(working_frame),
    }
    if isinstance(response_payload.get('late_fill'), Mapping):
        frame['late_fill'] = _json_safe(response_payload.get('late_fill'))
    if isinstance(response_payload.get('frame_relation'), Mapping):
        frame['frame_relation'] = _json_safe(response_payload.get('frame_relation'))
    if control_snapshot:
        frame['controls'] = _json_safe(control_snapshot)
    if error_frame:
        frame['error'] = error_frame
    if response_payload.get('batch_count') not in (None, ''):
        frame['batch'] = {
            'count': response_payload.get('batch_count'),
            'prompts': _json_safe(response_payload.get('batch_prompts') or []),
        }
    return _json_safe(frame)


def attach_response_frame(
    response_payload: Mapping[str, Any],
    *,
    request_payload: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Return a payload copy with its current response-frame snapshot attached."""

    if not isinstance(response_payload, Mapping):
        raise TypeError('response_payload must be a mapping')
    payload = dict(response_payload)
    payload['response_frame'] = build_response_frame(payload, request_payload=request_payload)
    return payload


