"""Late-fill continuation resolver/executor owners for Fruth."""

from __future__ import annotations

from fruth_services.text_artifact_files import TextArtifactFiles
from fruth_services.text_artifact_files import (
    _TERMINAL_SYNTAX_REPAIR_EXTENSIONS,
)

from fruth_services import text_artifact_syntax

from fruth_services.text_artifact_result_evidence import TextArtifactResultEvidence

from fruth_services.branch_dependency_evidence import BranchDependencyEvidence
from fruth_services.branch_dependency_evidence import (
    _BRANCH_LOCAL_ARTIFACT_IDENTITY_FIELD_RE,
    _BRANCH_LOCAL_STRUCTURED_JOIN_RE,
)

from fruth_server.pending_continuation import PendingContinuationAuthority
from fruth_server.pending_continuation import (
    C9_CONTROL_CONTINUATION_MAX_HANDOFFS,
    _PendingContinuation,
    _PendingContinuationChain,
)

from fruth_services.linked_artifact_materialization import LinkedArtifactMaterialization
from fruth_services.linked_artifact_materialization import (
    _EXTERNAL_LINK_RE,
    _INLINE_SCRIPT_RE,
    _JS_AWAITED_JSON_BINDING_RE,
    _JS_COLLECTION_ITERATOR_RE,
    _JS_FETCH_RESPONSE_ASSIGNMENT_RE,
    _JS_INVALID_IDENTIFIER_SEPARATOR_RE,
    _LINK_REBIND_ATTR_RE,
    _LINK_REBIND_EXTENSION_FAMILIES,
    _LINK_REBIND_FETCH_RE,
    _LINK_REBIND_HTML_TARGET_EXTENSIONS,
    _LINK_REBIND_IMAGE_EXTENSIONS,
    _LINK_REBIND_JSON_PATH_KEY_RE,
    _LINK_REBIND_PLACEHOLDER_RE,
    _LINK_REBIND_TEXT_EXTENSIONS,
    _LINK_REBIND_URL_RE,
    _SectionImageMarkup,
    _TERMINAL_CSS_HERO_BLOCK_RE,
    _TERMINAL_HERO_LOCAL_IMAGE_SIGNAL_RE,
    _TERMINAL_HTML_HERO_BLOCK_RE,
    _TERMINAL_MATERIALIZABLE_LOCAL_DEPENDENCY_EXTENSIONS,
    _static_fetch_url_is_local_file_dependency,
)

from fruth_services import text_artifact_materialization

from fruth_server.late_fill_selection import LateFillSelection
from fruth_server.late_fill_selection import (
    _late_fill_instance_is_mlx_vlm,
)

from fruth_services.tts_result_evidence import TtsResultEvidence
from fruth_services.tts_result_evidence import (
    _TTS_STT_MIN_SEQUENCE_RATIO,
    _TTS_STT_MIN_SOURCE_TOKENS_FOR_FULL_POLICY,
    _TTS_STT_MIN_TOKEN_PRECISION,
    _TTS_STT_MIN_TOKEN_RECALL,
    _TTS_STT_NEGATION_TOKENS,
    _TTS_STT_SEMANTIC_POLICY_ID,
    _TTS_STT_SHORT_MIN_SEQUENCE_RATIO,
    _TTS_STT_SHORT_MIN_TOKEN_F1,
)

from fruth_services import branch_result_contracts
from fruth_services.branch_result_contracts import (
    _DEPENDENCY_EVIDENCE_MISSING_CLAIM_RE,
    _PATH_ONLY_DEPENDENCY_EVIDENCE_RE,
    _VISION_GENERATION_REFUSAL_RE,
)

from fruth_services.text_artifact_syntax import repair_text_artifact_syntax_content
from fruth_services.text_artifact_syntax import text_artifact_syntax_sanity_issues_for_extension

from fruth_services.response_persistence import ResponsePersistenceError, response_persistence_blocked

from fruth_services.state_flow import observe_state

from fruth_services.artifact_contracts import (
    bind_direct_audio_dependency,
    read_saved_file_snapshot, saved_file_dependency_contract,
    saved_file_consumer_prompt, saved_file_read_text, saved_file_read_issue, saved_file_consumption_issue,
    saved_file_consumption_artifact_issue,
    saved_file_syntax_repair_issue,
    separate_image_report_contract, assemble_separate_image_reports, render_separate_image_reports,
)
from fruth_services.events import select_fields, traced_thread_target
from fruth_services.late_fill_telemetry import (
    LateFillTrace,
    observe_execution_gate,
    observe_prepared_branch,
    observe_worker,
    observe_schedule,
)

from fruth_server import tts_semantic_regeneration

import copy
import hashlib
import json
import logging
import math
import os
import re
import shutil
import tempfile
import threading
import time
import unicodedata
from contextlib import contextmanager
from collections import Counter
from difflib import SequenceMatcher
from html.parser import HTMLParser
from flask import current_app, has_app_context
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Optional

from fruth_server.response_lookup_runtime import response_wire_frame_identity


from helpers.session_controls import (
    normalize_reasoning_effort,
    resolve_reasoning_effort_for_instance,
)
from fruth_inference.control_hints import infer_tts_language_from_prompt
from fruth_inference.execution_planner import extract_atx_tts_sections
from fruth_inference.intent_obligations import required_intent_obligations
from fruth_core.text_artifacts import TEXT_ARTIFACT_EXTENSIONS, extract_text_artifact_payloads, text_artifact_request_is_generic
from fruth_core.runtime_liveness import (
    runtime_instance_liveness,
    runtime_instance_is_selectable,
    runtime_instance_score,
    runtime_liveness_summary,
)
from fruth_core.transports import (
    ARTIFACT_OUTPUTS_DOCUMENTS_DIR,
    persist_text_artifact_locally,
    strip_enclosing_text_artifact_fence,
    text_artifact_content_is_materializer_instruction_echo,
)
from fruth_server.recovery_contract import (
    RECOVERY_ACTION_MANUAL_REVIEW,
    RECOVERY_ACTION_REBIND_DEPENDENCY_EVIDENCE,
    RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT,
    RECOVERY_ACTION_REPAIR_DEPENDENCY_CHAIN,
    RECOVERY_ACTION_REBUILD_FROM_PROMOTED_OBLIGATIONS,
    RECOVERY_ACTION_SEMANTIC_REVIEW,
    RECOVERY_ACTION_RETRY_EXCLUDING_INSTANCE,
    RECOVERY_ACTION_RETRY_SAME_BRANCH,
    RECOVERY_ACTION_START_COMPATIBLE_INSTANCE,
    normalize_recovery_suggested_action,
)
from fruth_server.repair_gate_runtime import classify_repair_execution_policy
from fruth_server.responses_runtime import (
    ResponseMutationConflict,
    require_response_mutation_base,
    require_response_mutation_target,
    repair_contract_matches_completion,
    terminal_repair_loop_is_fully_satisfied,
)
from fruth_server.response_semantics_runtime import ResponseSemanticsRuntimeOwner, _bounded_visual_evidence_from_selected_message as _extract_bounded_visual_evidence_from_selected_message
from fruth_inference.image_prompt_preparation import _image_prompt_candidate_is_code_or_css_polluted, _image_prompt_batch_looks_like_weak_social_copy, _extract_filename_social_asset_image_prompt_lines, _extract_inline_labeled_image_prompt_lines, _extract_leading_plain_alpha_image_prompt_lines, _extract_sequential_bold_alpha_image_prompt_lines, _extract_html_image_card_prompt_units, _extract_numbered_image_prompt_section, _parse_image_batch_expected_count, _extract_social_manifest_pipe_image_prompt_lines, _strip_social_manifest_image_prompt_metadata
from fruth_services.phase_output import control_json_envelope_suspected
from fruth_services.artifact_contracts import (
    artifact_authority_rank,
    artifact_is_current_authoritative,
    text_artifact_output_declaration,
    text_artifact_same_output,
    artifact_logical_identities_match,
    select_authoritative_artifact_records,
    sanitize_artifact_record,
)
from fruth_services.artifact_registry import refresh_text_artifact_record_from_saved_path
from fruth_services.response_artifact_bundles import JS_QUOTED_RE, FETCH_LITERAL_PREFIX_RE
from fruth_services.response_frame_construction import prepare_response_output_state
from fruth_services.responses import (
    _is_public_output_artifact_record,
    capture_request_intent,
    extract_responses_current_turn_prompt,
    has_captured_request_intent,
    request_intent_evidence_missing,
    restore_request_intent,
)
from fruth_services.graph_rebase import (
    graph_rebase_prompt_contains_root,
    stable_graph_rebase_prompt_digest,
)
from fruth_services.enforced_policy import (
    ENFORCED_POLICY_DEFAULT_ID,
    ENFORCED_POLICY_PRODUCT_DEFAULT_MODE,
    ENFORCED_POLICY_REVIEW_KIND,
)
from fruth_services.response_frames import (
    RESPONSE_FRAME_STALE_PARENT_REASON,
    ResponseFrameParentCASMismatch,
)
from fruth_services.tts_audio_integrity import (
    TTS_AUDIO_INTEGRITY_POLICY_ID,
    TTS_SEMANTIC_SOURCE_POLICY_ID,
    build_tts_audio_integrity_evidence,
    build_tts_semantic_source,
)


_DEPENDENCY_INPUT_MISSING_RE = re.compile(
    r'\b('
    r'(?:requires|expected|missing|needs?)\s+(?:an?\s+)?(?:audio|image|file)\s+file|'
    r'missing\s+dependency\s+(?:artifact|evidence|input)|'
    r'(?:audio|image)\s+file\s+(?:required|missing)|'
    r'no\s+(?:audio|image)\s+(?:file|artifact)'
    r')\b',
    re.IGNORECASE,
)

_REASONING_EFFORT_KEYS = ('reasoning_effort', 'reasoningEffort')


def _retarget_model_scoped_reasoning_effort(
    payload: Mapping[str, Any],
    instance: Optional[dict[str, Any]],
    *,
    source_instance_id: str = '',
) -> dict[str, Any]:
    """Resolve inherited reasoning against the model that runs this branch."""

    updated = dict(payload or {})
    request_meta = (
        updated.get('request_meta')
        if isinstance(updated.get('request_meta'), Mapping)
        else {}
    )
    reasoning_provenance = (
        request_meta.get('reasoning_effort_control')
        if isinstance(request_meta.get('reasoning_effort_control'), Mapping)
        else {}
    )
    requested: Any = None
    for key in _REASONING_EFFORT_KEYS:
        if updated.get(key) not in (None, ''):
            requested = updated.get(key)
            break
    if requested in (None, '') and reasoning_provenance.get('value') not in (None, ''):
        requested = reasoning_provenance.get('value')
    for key in _REASONING_EFFORT_KEYS:
        updated.pop(key, None)

    target = instance if isinstance(instance, dict) else {}
    target_default = resolve_reasoning_effort_for_instance(None, target)
    if target_default is None:
        return updated

    try:
        normalized_requested = normalize_reasoning_effort(requested)
    except ValueError:
        normalized_requested = None
    target_instance_id = str(target.get('instance_id') or '').strip()
    if not source_instance_id:
        source_instance_id = str(
            reasoning_provenance.get('source_instance_id') or ''
        ).strip()
    same_instance = bool(
        source_instance_id
        and target_instance_id
        and source_instance_id == target_instance_id
    )

    if normalized_requested == 'off':
        resolved = 'off'
    elif same_instance and normalized_requested is not None:
        try:
            resolved = resolve_reasoning_effort_for_instance(
                normalized_requested,
                target,
            )
        except ValueError:
            resolved = target_default
    else:
        resolved = target_default
    if resolved is not None:
        updated['reasoning_effort'] = resolved
    return updated


_AUDIO_VARIANT_HEADER_RE = re.compile(
    r'^(?:audio\s*[- ]?\s*(?:version|variant|variante|fassung)|audiofassung|'
    r'spoken\s+(?:version|variant)|speech\s+(?:version|variant))\s*'
    r'(?P<index>\d{1,2})\b.*?:?\s*$',
    re.IGNORECASE,
)
_AUDIO_SPEAKABLE_FIELD_LABELS = {
    'audio text',
    'audio-text',
    'content',
    'erzaehlung',
    'erzählung',
    'inhalt',
    'narration',
    'script',
    'sprechtext',
    'spoken text',
    'tts text',
    'voiceover',
}
_AUDIO_SINGLE_SPEAKABLE_SECTION_TOKENS = (
    'audio text',
    'audio-text',
    'erzaehlung',
    'erzählung',
    'narration',
    'script',
    'sprechtext',
    'spoken text',
    'tts text',
    'voiceover',
)
_LATE_FILL_ALPHA_PROMPT_RESIDUE_RE = re.compile(
    r'^\s*(?:[-*#>\u2022]+\s*)?'
    r'(?:\*\*|__)?(?P<label>[A-Z])\s*'
    r'(?:(?:\*\*|__)\s*)?:\s*'
    r'(?:(?:\*\*|__)\s*)?.+$'
)
_LATE_FILL_COLLAPSED_ALPHA_LABEL_RE = re.compile(
    r'(?<![A-Za-z0-9_])(?P<label>[A-Z])\s*:\s+'
)
_BRANCH_LOCAL_ARTIFACT_ALPHA_LABEL_RE = re.compile(
    r'(?:^|[;:\n])\s*(?P<label>[A-Z])\s*(?:[-\u2013\u2014:])\s*',
    re.MULTILINE,
)
_BRANCH_LOCAL_VISION_DIRECTIVE_START_RE = re.compile(
    r'\b(?:'
    r'analy[sz](?:e|es|ed|ing)|inspect(?:s|ed|ing)?|examin(?:e|es|ed|ing)|'
    r'describ(?:e|es|ed|ing)|caption(?:s|ed|ing)?|summari[sz](?:e|es|ed|ing)|'
    r'analysier(?:e|en|t)?|untersuch(?:e|en|t)?|pr[uü]f(?:e|en|t)?|'
    r'beschreib(?:e|en|t)?|schilder(?:e|n|t)?|fass(?:e|en|t)?'
    r')\b',
    re.IGNORECASE,
)
_BRANCH_LOCAL_VISION_TARGET_RE = re.compile(
    r'\b(?:actual|attached|generated|visible|visual|image|picture|photo|artifact|'
    r'tats[aä]chlich|angeh[aä]ngt|erzeugt|sichtbar|bild|foto|artefakt)\w*\b|'
    r'\b(?:it|them)\b|\beach\s+one\b',
    re.IGNORECASE,
)
_BRANCH_LOCAL_VISION_DIRECTIVE_STOP_RE = re.compile(
    r'(?:,\s*)?\b(?:then|finally|afterwards|abschlie(?:ss|ß)end|anschlie(?:ss|ß)end)\s+'
    r'(?:compare|transcribe|generate|create|speak|read|vergleiche|transkribiere|erzeuge|erstelle|sprich|lies)\b|'
    r'\s+\b(?:and|und)\s+'
    r'(?:transcrib(?:e|es|ed|ing)|generate|create|compare|speak|read|'
    r'transkribier(?:e|en|t)?|erzeuge|erstelle|vergleiche|sprich|lies)\b',
    re.IGNORECASE,
)
_BRANCH_LOCAL_VISION_GLOBAL_JOIN_STOP_RE = re.compile(
    r'(?:'
    r'(?:,\s*)?\b(?:then|finally|afterwards|abschlie(?:ss|ß)end|anschlie(?:ss|ß)end)\s+|'
    r'\s+\b(?:and|und)\s+'
    r')'
    r'(?:return|give|provide|output|gib|liefere)\b'
    r'(?=[^.!?\n]{0,240}(?:'
    r'\bjson\s*(?:[-_/]\s*|\s+)(?:list(?:e)?|array)\b|'
    r'\btable\b|\b(?:in\s+the\s+chat|im\s+chat)\b|'
    r'\b(?:combined|global|final)\s+(?:answer|output|result|structure)\b'
    r'))',
    re.IGNORECASE,
)
_BRANCH_LOCAL_VISION_FOCUS_PATTERNS = (
    re.compile(
        r'\bob\s+(?P<focus>[^.!?\n]{1,180}?)\s+in\s+(?:beiden|allen)\b',
        re.IGNORECASE,
    ),
    re.compile(
        r'\b(?:whether|if)\s+(?P<focus>[^.!?\n]{1,180}?)\s+'
        r'(?:appear|appears|occur|occurs|are\s+present|is\s+present)\s+in\s+both\b',
        re.IGNORECASE,
    ),
)
_BRANCH_LOCAL_VISION_MULTI_ARTIFACT_RE = re.compile(
    r'\b(?:two|three|four|five|six|2|3|4|5|6|zwei|drei|vier|f[uü]nf|sechs|'
    r'multiple|several|mehrere)\b[^.!?\n]{0,56}\b'
    r'(?:images?|pictures?|artifacts?|bilder?|artefakte?)\b|'
    r'\b(?:each|every|all|jedes|jeden|alle)\b[^.!?\n]{0,32}\b'
    r'(?:images?|pictures?|artifacts?|bilder?|artefakte?)\b',
    re.IGNORECASE,
)
_BRANCH_LOCAL_VISION_FOR_MULTIPLE_LABELS_RE = re.compile(
    r'\b(?:for|f[uü]r)\s+(?:[A-Za-z]|[0-9]+)\s*(?:,|/)\s*'
    r'(?:[A-Za-z]|[0-9]+)',
    re.IGNORECASE,
)
_BRANCH_LOCAL_VISION_EXPLICIT_GLOBAL_JOIN_RE = re.compile(
    r'\b(?:in\s+the\s+chat|im\s+chat|multi[-\s]?artifact|'
    r'(?:combined|global|final)\s+(?:answer|output|result|structure|join))\b',
    re.IGNORECASE,
)
_BRANCH_CONTRACT_REPAIR_RE = re.compile(
    r'\b('
    r'contract|execution\s+contract|branch\s+identity|obligation|'
    r'output\s+contract|validation|schema|control\s+validation'
    r')\b',
    re.IGNORECASE,
)
_SEMANTIC_EXECUTION_TERMINAL_STATUSES = {'cancelled', 'waived', 'superseded'}
_SEMANTIC_EXECUTION_CONTROL_ACTIONS = {
    'cancel': 'cancelled',
    'cancelled': 'cancelled',
    'stop': 'cancelled',
    'waive': 'waived',
    'waived': 'waived',
    'supersede': 'superseded',
    'superseded': 'superseded',
}


_INLINE_TEXT_ARTIFACT_FENCE_RE = re.compile(
    r'```(?P<lang>[A-Za-z0-9_+.-]*)(?:[^\n`]*)?\n(?P<body>.*?)(?:\n```|```)',
    re.DOTALL,
)
_INLINE_COMPLETE_HTML_RE = re.compile(r'(?is)\b<!doctype\s+html\b|<html\b')
_INLINE_HTML_CSS_EXTENSIONS = {'html', 'htm', 'css'}
_TEXT_ARTIFACT_REVISION_PRESERVATION_RE = re.compile(
    r'(?:'
    r'\b(?:keep|preserve|retain|leave)\b[\s\S]{0,140}'
    r'\b(?:rest|remainder|existing|unrelated|unchanged|intact|outside)\b|'
    r'\b(?:rest|remainder|existing|unrelated|unchanged)\b[\s\S]{0,100}'
    r'\b(?:intact|unchanged|preserved)\b|'
    r'\b(?:behalte|erhalte|bewahre|lass|halte)\b[\s\S]{0,140}'
    r'\b(?:rest|bestehende[nmrs]?|unver[aä]ndert|intakt|au(?:s|ß)erhalb)\b|'
    r'\b(?:rest|bestehende[nmrs]?)\b[\s\S]{0,100}'
    r'\b(?:unver[aä]ndert|intakt|erhalten)\b'
    r')',
    re.IGNORECASE,
)
_RAW_IMAGE_RESULT_KEYS = {'image', 'image_base64', 'image_b64', 'image_data', 'png_base64', 'image_data_url'}
_RAW_IMAGE_LIST_KEYS = {'images'}
_AUTO_EXECUTABLE_REPAIR_RETRY_ACTIONS = {
    RECOVERY_ACTION_RETRY_EXCLUDING_INSTANCE,
    RECOVERY_ACTION_RETRY_SAME_BRANCH,
}
_AUTO_EXECUTABLE_REPAIR_DEFAULT_MAX_ATTEMPTS = 6
_AUTO_EXECUTABLE_REPAIR_MAX_ATTEMPTS_LIMIT = 12
_AUTO_EXECUTABLE_REPAIR_MAX_ATTEMPTS_ENV = 'FRUTH_AUTO_EXECUTABLE_REPAIR_MAX_ATTEMPTS'
_COALESCED_TEXT_ARTIFACT_RECOVERY_TRIGGER = (
    'coalesced_text_artifact_atomic_retry'
)
_COALESCED_TEXT_ARTIFACT_RECOVERY_MAX_ATTEMPTS = 2
_TTS_AUTO_RECOVERY_POLICY_ID = 'tts_bounded_materialization_recovery_v1'
_TTS_AUTO_RECOVERY_TRIGGER = 'tts_auto_recovery'
_TTS_AUTO_RECOVERY_MAX_ATTEMPTS = 2
_VISION_EVIDENCE_RECOVERY_POLICY_ID = 'vision_bounded_evidence_recovery_v1'
_VISION_BACKEND_RECOVERY_POLICY_ID = 'vision_bounded_backend_recovery_v1'
_VISION_BACKEND_RECOVERY_TRIGGER = 'vision_backend_recovery'
_VISION_EVIDENCE_RECOVERY_TRIGGER = 'vision_evidence_recovery'
_VISION_EVIDENCE_RECOVERY_MAX_ATTEMPTS = 2
EXPLICIT_IMAGE_EXCLUDED_POOL_RETRY_POLICY_ID = (
    'explicit_image_excluded_pool_retry_v1'
)
_TARGET_BOUND_SAVED_TEXT_SYNTAX_REPAIR_TRIGGER = (
    'target_bound_saved_text_syntax_repair'
)
_PARTIAL_GRAPH_REBASE_HANDOFF_LOCK = threading.RLock()
_GRAPH_PATCH_TERMINAL_REVIEW_HANDOFF_LOCK = threading.RLock()
_GRAPH_PATCH_TERMINAL_REVIEW_RELATION = 'graph_patch_terminal_review'

_BRANCH_LOCAL_PUBLICATION_FIELDS = {
    'artifact_id',
    'artifact_ref',
    'ref',
    'path',
    'artifact_path',
    'saved_text_path',
    'saved_text_artifacts',
    'saved_audio_path',
    'saved_image_path',
    'saved_video_path',
    'image_data_url',
    'image_state',
    'artifacts',
    'provenance_id',
    'derived_from',
    'source_response_id',
}
_BRANCH_LOCAL_MATERIALIZATION_FIELDS = {
    'artifact_request',
    'text_artifact_request',
    'text_artifact_requests',
    'requires_artifact',
    'text_artifact_extension',
    'text_artifact_source_name',
    'text_artifact_source',
    'text_artifact_target_path',
    'text_artifact_revision_required',
    'text_artifact_revision_source',
    'text_artifact_source_is_input',
    'text_artifact_revision_binding_state',
    'text_artifact_revision_source_path',
    'text_artifact_revision_source_size_bytes',
    'text_artifact_revision_source_sha256',
    'text_artifact_revision_preservation_required',
    'text_artifact_revision_preservation_policy',
}
_GRAPH_PATCH_TERMINAL_REVIEW_REASON = 'terminal_graph_patch_enforced_policy_denied'
_GRAPH_PATCH_TERMINAL_REVIEW_RUNTIME_EFFECT = 'audit_only_no_execution'
_GRAPH_PATCH_TERMINAL_SAFE_ENFORCED_CLASSES = frozenset({
    'duplicate_artifact_alias_canonicalization',
    'safe_additive_artifact_binding_repair',
    'safe_additive_dependency_repair',
    'safe_additive_missing_branch',
})
_GRAPH_PATCH_TERMINAL_REVIEW_RELATION_KEYS = frozenset({
    'audit_key',
    'audit_only',
    'executable',
    'kind',
    'owed_work',
    'parent_frame_id',
    'parent_frame_sequence',
    'parent_response_id',
    'patch_id',
    'policy_review_id',
    'proposal_id',
    'reason',
    'response_id',
    'review_id',
    'runtime_effect',
    'scheduled_branch_ids',
})


def _late_fill_instance_is_usable(instance: Mapping[str, Any], *, capability: Any = None) -> bool:
    return runtime_instance_is_selectable(instance, capability=capability)


def _late_fill_instance_unusable_summary(instance: Mapping[str, Any], *, capability: Any = None) -> str:
    return runtime_liveness_summary(instance, capability=capability)


def _contract_text(value: Any) -> str:
    return str(value or '').strip()


def _first_contract_value(*values: Any) -> Any:
    for value in values:
        if value not in (None, '', [], {}):
            return value
    return None


def _clean_contract_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        cleaned = {
            str(key): _clean_contract_value(raw_value)
            for key, raw_value in value.items()
            if raw_value not in (None, '', [], {})
        }
        return {
            key: raw_value
            for key, raw_value in cleaned.items()
            if raw_value not in (None, '', [], {})
        }
    if isinstance(value, list):
        cleaned_items = [
            _clean_contract_value(item)
            for item in value
            if item not in (None, '', [], {})
        ]
        return [
            item
            for item in cleaned_items
            if item not in (None, '', [], {})
        ]
    if isinstance(value, tuple):
        return _clean_contract_value(list(value))
    if isinstance(value, str):
        return value.strip()
    return value


def _normalized_terminal_status(value: Any) -> str:
    token = str(value or '').strip().lower()
    return _SEMANTIC_EXECUTION_CONTROL_ACTIONS.get(token, token if token in _SEMANTIC_EXECUTION_TERMINAL_STATUSES else '')


def _payload_has_raw_image_result(value: Any) -> bool:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key or '').strip().lower()
            if key in _RAW_IMAGE_RESULT_KEYS and str(child or '').strip():
                return True
            if _payload_has_raw_image_result(child):
                return True
        return False
    if isinstance(value, list):
        return any(_payload_has_raw_image_result(item) for item in value)
    return False


def _raw_image_data_url_from_candidate(value: Any) -> str:
    if not isinstance(value, str):
        return ''
    token = value.strip()
    if not token:
        return ''
    if token.lower().startswith('data:image/'):
        return token
    return f'data:image/png;base64,{token}'


def _extract_raw_image_data_url(value: Any) -> str:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key or '').strip().lower()
            if key in _RAW_IMAGE_RESULT_KEYS:
                data_url = _raw_image_data_url_from_candidate(child)
                if data_url:
                    return data_url
            if key in _RAW_IMAGE_LIST_KEYS and isinstance(child, list):
                for item in child:
                    data_url = _raw_image_data_url_from_candidate(item)
                    if data_url:
                        return data_url
            data_url = _extract_raw_image_data_url(child)
            if data_url:
                return data_url
        return ''
    if isinstance(value, list):
        for item in value:
            data_url = _extract_raw_image_data_url(item)
            if data_url:
                return data_url
    return ''


@dataclass
class LateFillRuntimeOwner:
    normalize_request_payload: Callable[[dict[str, Any]], dict[str, Any]]
    extract_request_meta: Callable[[dict[str, Any]], Any]
    attach_request_meta: Callable[[dict[str, Any]], dict[str, Any]]
    extract_responses_prompt: Callable[[Any], str]
    sanitize_selected_reference_artifacts: Callable[..., list[dict[str, Any]]]
    parse_bool: Callable[..., bool]
    extract_inference_route_messages: Callable[[dict[str, Any]], list[dict[str, Any]]]
    response_registry_now_iso: Callable[[], str]
    max_recent_messages: int
    normalize_capability: Callable[[Any], Optional[str]]
    capability_text_to_speech: str
    capability_image_generation: str
    resolve_inference_auto_route: Callable[..., tuple[Optional[dict[str, Any]], Optional[str]]]
    merge_instances_with_runtime_status: Callable[..., list[dict[str, Any]]]
    load_running_instances: Callable[[], list[dict[str, Any]]]
    runtime_status_path_getter: Callable[[], Any]
    instance_supports_capability: Callable[[dict[str, Any], str], bool]
    pick_prompt_preferred_instance: Callable[[list[dict[str, Any]], str], str]
    pick_default_capability_instance: Callable[[list[dict[str, Any]]], str]
    merge_request_meta_runtime_truth: Callable[..., dict[str, Any]]
    prepare_effective_request_data: Callable[..., tuple[dict[str, Any], dict[str, Any], Any, Any]]
    build_missing_required_session_controls: Callable[..., list[dict[str, Any]]]
    normalize_backend: Callable[[Any], Optional[str]]
    select_backend_request_model: Callable[..., str]
    build_responses_infer_execution_payload: Callable[..., tuple[dict[str, Any], dict[str, Any], bool, bool]]
    invoke_internal_api_json_route: Callable[..., tuple[dict[str, Any], int]]
    filter_responses_infer_result: Callable[..., dict[str, Any]]
    artifact_type_for_capability: Callable[[Any], Optional[str]]
    semantic_payload_for_capability: Callable[..., dict[str, Any]]
    get_response_lookup_record: Callable[[str], Optional[dict[str, Any]]]
    normalize_capability_list: Callable[[Any], list[str]]
    extract_pending_deferred_branches: Callable[..., list[dict[str, Any]]]
    extract_pending_deferred_capabilities: Callable[..., list[str]]
    build_pending_late_fill_branches: Callable[..., list[dict[str, Any]]]
    branch_id: Callable[[Mapping[str, Any]], str]
    branch_capability: Callable[[Mapping[str, Any]], Optional[str]]
    artifact_gap_is_already_fulfilled: Callable[..., bool]
    build_late_fill_state: Callable[..., dict[str, Any]]
    build_graph_closure_review: Callable[..., dict[str, Any]]
    attach_graph_closure_review_diagnostics: Callable[..., dict[str, Any]]
    finalize_response_frame_payload: Callable[..., dict[str, Any]]
    attach_late_fill_state: Callable[..., dict[str, Any]]
    touch_response_lookup: Callable[..., Optional[dict[str, Any]]]
    ensure_response_lookup_for_payload: Callable[..., Optional[dict[str, Any]]]
    build_canonical_response_artifacts: Callable[[dict[str, Any]], list[dict[str, Any]]]
    downstream_request_phase_batches: Callable[..., list[list[dict[str, Any]]]]
    late_fill_capability_counts: Callable[[list[dict[str, Any]]], dict[str, int]]
    normalize_late_fill_branches: Callable[[Any], list[dict[str, Any]]]
    log_unified_event: Callable[..., Any]
    execute_materialization_branches: Callable[..., dict[str, Any]]
    claim_response_late_fill: Callable[[str], bool]
    release_response_late_fill: Callable[[str], None]
    persist_image_data_url_locally: Callable[[Optional[str], str], Optional[str]]
    response_mutation: Callable[..., Any]
    schedule_post_response_substrate_hygiene: Optional[Callable[..., Any]] = None
    attach_runtime_graph_repair_evidence: Optional[
        Callable[[dict[str, Any]], dict[str, Any]]
    ] = None
    review_terminal_graph_rebase: Optional[Callable[..., dict[str, Any]]] = None
    prepare_terminal_graph_patch_successor: Optional[Callable[..., dict[str, Any]]] = None
    project_terminal_closure_repair: Optional[Callable[..., dict[str, Any]]] = None
    load_latest_response_state: Optional[Callable[..., Mapping[str, Any]]] = None
    load_latest_response_observation_state: Optional[
        Callable[..., Mapping[str, Any]]
    ] = None
    load_external_targets: Optional[Callable[..., list[dict[str, Any]]]] = None
    execute_external_chat_phase: Optional[Callable[..., dict[str, Any]]] = None
    resolve_saved_file_input_path: Optional[Callable[[str], Optional[Path]]] = None

    @property
    def text_artifact_files(self) -> TextArtifactFiles:
        return TextArtifactFiles(
            collect_artifact_records=lambda payload: self.linked_artifact_materialization._collect_link_rebind_artifact_records(payload),
            artifact_outputs_documents_dir=ARTIFACT_OUTPUTS_DOCUMENTS_DIR,
        )

    @property
    def text_artifact_result_evidence(self) -> TextArtifactResultEvidence:
        return TextArtifactResultEvidence(
            build_canonical_response_artifacts=lambda *args, **kwargs: self.build_canonical_response_artifacts(*args, **kwargs),
            branch_requires_text_artifact=LateFillSelection._artifact_gap_is_required_text_materialization,
            saved_file_consumption_error=lambda *args, **kwargs: self.saved_file_consumption_error(*args, **kwargs),
            resolve_saved_file_input_path=self.resolve_saved_file_input_path,
            branch_capability=lambda branch: self.branch_capability(branch),
            branch_id=lambda branch: self.branch_id(branch),
            chat_capability=lambda: self.capability_chat,
        )

    @property
    def branch_dependency_evidence(self) -> BranchDependencyEvidence:
        return BranchDependencyEvidence(
            artifact_type_for_capability=lambda capability: self.artifact_type_for_capability(capability),
            branch_capability=lambda branch: self.branch_capability(branch),
            build_canonical_response_artifacts=lambda *args, **kwargs: self.build_canonical_response_artifacts(*args, **kwargs),
            image_generation_capability=lambda: self.capability_image_generation,
            text_to_speech_capability=lambda: self.capability_text_to_speech,
            normalize_capability=lambda capability: self.normalize_capability(capability),
            resolve_saved_file_input_path=self.resolve_saved_file_input_path,
        )

    @property
    def pending_continuation_authority(self) -> PendingContinuationAuthority:
        return PendingContinuationAuthority(
            branch_id=self.branch_id,
            normalize_late_fill_branches=self.normalize_late_fill_branches,
            load_latest_response_state=self.load_latest_response_state,
        )

    @property
    def linked_artifact_materialization(self) -> LinkedArtifactMaterialization:
        return LinkedArtifactMaterialization(
            branch_id=lambda branch: self.branch_id(branch),
            build_canonical_response_artifacts=lambda *args, **kwargs: self.build_canonical_response_artifacts(*args, **kwargs),
            normalize_capability=lambda capability: self.normalize_capability(capability),
            image_generation_capability=lambda: self.capability_image_generation,
        )

    @property
    def branch_selection(self) -> LateFillSelection:
        return LateFillSelection(
            branch_capability=lambda branch: self.branch_capability(branch),
            image_generation_capability=lambda: self.capability_image_generation,
            clock=time.time,
        )

    @property
    def tts_result_evidence(self) -> TtsResultEvidence:
        return TtsResultEvidence(
            branch_capability=self.branch_capability,
            normalize_capability=self.normalize_capability,
            capability_text_to_speech=self.capability_text_to_speech,
        )

    _artifact_gap_is_required_text_materialization = staticmethod(LateFillSelection._artifact_gap_is_required_text_materialization)

    _text_artifact_revision_required = staticmethod(text_artifact_materialization._text_artifact_revision_required)

    @staticmethod
    def _text_artifact_revision_preservation_requested(prompt: Any) -> bool:
        """Recognize an explicit request to keep bytes outside the edit scope."""

        return bool(
            _TEXT_ARTIFACT_REVISION_PRESERVATION_RE.search(str(prompt or '').strip())
        )

    _text_artifact_revision_anchor_tokens = staticmethod(text_artifact_materialization._text_artifact_revision_anchor_tokens)

    _text_artifact_revision_preservation_review = staticmethod(text_artifact_materialization._text_artifact_revision_preservation_review)

    _text_artifact_revision_write_proven = staticmethod(TextArtifactResultEvidence._text_artifact_revision_write_proven)

    @classmethod
    def _artifact_gap_allows_excluded_candidate_reuse_for_text_repair(
        cls,
        artifact_gap: Optional[Mapping[str, Any]],
    ) -> bool:
        gap = artifact_gap if isinstance(artifact_gap, Mapping) else {}
        if not LateFillSelection._artifact_gap_is_required_text_materialization(gap):
            return False
        action = normalize_recovery_suggested_action(
            gap.get('repair_action') or gap.get('recovery_action') or gap.get('suggested_action'),
            default='',
        )
        if action not in {
            RECOVERY_ACTION_RETRY_SAME_BRANCH,
            RECOVERY_ACTION_RETRY_EXCLUDING_INSTANCE,
        }:
            return False
        execution_policy = str(
            gap.get('repair_execution_policy') or gap.get('execution_policy') or ''
        ).strip()
        if (
            not LateFillSelection._runtime_scheduling_flag_enabled(gap.get('auto_execute'))
            and execution_policy != 'schedule_late_fill_branch'
        ):
            return False
        if gap.get('materialization_blocked') is True or gap.get('needs_external_input') is True:
            return False
        if gap.get('repair_work_available') is False:
            return False
        return True

    def _artifact_gap_allows_excluded_candidate_reuse_for_tts_recovery(
        self,
        artifact_gap: Optional[Mapping[str, Any]],
    ) -> bool:
        gap = artifact_gap if isinstance(artifact_gap, Mapping) else {}
        recovery_attempt = (
            gap.get('recovery_attempt')
            if isinstance(gap.get('recovery_attempt'), Mapping)
            else {}
        )
        recovery_state = (
            gap.get('recovery_state')
            if isinstance(gap.get('recovery_state'), Mapping)
            else {}
        )
        execution_contract = (
            gap.get('execution_contract')
            if isinstance(gap.get('execution_contract'), Mapping)
            else {}
        )
        output_contract = (
            execution_contract.get('output_contract')
            if isinstance(execution_contract.get('output_contract'), Mapping)
            else {}
        )
        attempt_trigger = str(
            recovery_attempt.get('trigger') or ''
        ).strip().lower()
        state_trigger = str(
            recovery_state.get('trigger') or ''
        ).strip().lower()
        if attempt_trigger != state_trigger:
            return False
        if attempt_trigger not in {
            'explicit_retry_endpoint',
            _TTS_AUTO_RECOVERY_TRIGGER,
        }:
            return False
        automatic_tts_recovery = bool(
            attempt_trigger == _TTS_AUTO_RECOVERY_TRIGGER
        )
        capabilities = {
            self.normalize_capability(value)
            for value in (
                gap.get('expected_capability'),
                gap.get('active_capability'),
                execution_contract.get('capability'),
                recovery_attempt.get('capability'),
                recovery_state.get('capability'),
            )
            if str(value or '').strip()
        }
        if capabilities != {self.capability_text_to_speech}:
            return False
        output_type = str(
            gap.get('output_type')
            or execution_contract.get('output_type')
            or gap.get('missing_artifact_type')
            or ''
        ).strip().lower()
        if output_type != 'audio':
            return False
        if output_contract.get('required') is not True:
            return False
        action = normalize_recovery_suggested_action(
            recovery_state.get('suggested_action')
            or gap.get('repair_action')
            or gap.get('recovery_action')
            or gap.get('suggested_action'),
            default='',
        )
        if action not in {
            RECOVERY_ACTION_RETRY_EXCLUDING_INSTANCE,
            RECOVERY_ACTION_START_COMPATIBLE_INSTANCE,
        }:
            return False
        if automatic_tts_recovery and action not in {
            RECOVERY_ACTION_RETRY_EXCLUDING_INSTANCE,
            RECOVERY_ACTION_RETRY_SAME_BRANCH,
            RECOVERY_ACTION_START_COMPATIBLE_INSTANCE,
        }:
            return False
        if action == RECOVERY_ACTION_START_COMPATIBLE_INSTANCE:
            prior_error_code = str(
                recovery_attempt.get('prior_error_code')
                or recovery_state.get('prior_error_code')
                or gap.get('prior_error_code')
                or ''
            ).strip().upper()
            if prior_error_code != 'NO_COMPATIBLE_INSTANCE':
                return False
        if str(recovery_state.get('retry_scope') or '').strip() != 'same_branch':
            return False
        branch_id = str(
            gap.get('branch_id') or execution_contract.get('branch_id') or ''
        ).strip()
        attempt_branch_id = str(recovery_attempt.get('branch_id') or '').strip()
        state_branch_id = str(recovery_state.get('branch_id') or '').strip()
        if not branch_id or branch_id != attempt_branch_id or branch_id != state_branch_id:
            return False
        if recovery_attempt.get('preserve_intent') is not True:
            return False
        if recovery_state.get('preserve_intent') is not True:
            return False
        if (
            gap.get('needs_external_input') is True
            or recovery_state.get('needs_external_input') is True
        ):
            return False
        if automatic_tts_recovery:
            if (
                str(
                    recovery_attempt.get('recovery_policy_id') or ''
                ).strip()
                != _TTS_AUTO_RECOVERY_POLICY_ID
                or str(
                    recovery_state.get('recovery_policy_id') or ''
                ).strip()
                != _TTS_AUTO_RECOVERY_POLICY_ID
            ):
                return False
            if (
                recovery_attempt.get('auto_execute') is not True
                or recovery_state.get('auto_execute') is not True
            ):
                return False
            try:
                attempt_number = int(
                    recovery_attempt.get('attempt_number') or 0
                )
                maximum_attempts = int(
                    recovery_attempt.get('maximum_attempts') or 0
                )
                retry_count = int(
                    gap.get('auto_executable_repair_retry_count') or 0
                )
            except (TypeError, ValueError):
                return False
            if (
                attempt_number != 2
                or maximum_attempts
                != _TTS_AUTO_RECOVERY_MAX_ATTEMPTS
                or retry_count != 1
            ):
                return False
            prior_error_code = str(
                recovery_attempt.get('prior_error_code')
                or recovery_state.get('prior_error_code')
                or ''
            ).strip().upper()
            if not prior_error_code:
                return False
            if prior_error_code == 'TTS_AUDIO_INTEGRITY_REPAIR_REQUIRED':
                prior_integrity = (
                    recovery_attempt.get('prior_audio_integrity_evidence')
                    if isinstance(
                        recovery_attempt.get('prior_audio_integrity_evidence'),
                        Mapping,
                    )
                    else {}
                )
                if not (
                    str(prior_integrity.get('kind') or '').strip()
                    == 'fruth.tts_audio_integrity_evidence'
                    and prior_integrity.get('version') == 1
                    and str(prior_integrity.get('policy_id') or '').strip()
                    == TTS_AUDIO_INTEGRITY_POLICY_ID
                    and prior_integrity.get('materialization_eligible') is False
                ):
                    return False
        return True

    def _artifact_gap_allows_excluded_candidate_reuse_for_explicit_image_retry(
        self,
        artifact_gap: Optional[Mapping[str, Any]],
    ) -> bool:
        """Authorize one user-triggered image retry after local pool exhaustion."""

        gap = artifact_gap if isinstance(artifact_gap, Mapping) else {}
        recovery_attempt = (
            gap.get('recovery_attempt')
            if isinstance(gap.get('recovery_attempt'), Mapping)
            else {}
        )
        recovery_state = (
            gap.get('recovery_state')
            if isinstance(gap.get('recovery_state'), Mapping)
            else {}
        )
        execution_contract = (
            gap.get('execution_contract')
            if isinstance(gap.get('execution_contract'), Mapping)
            else {}
        )
        output_contract = (
            execution_contract.get('output_contract')
            if isinstance(execution_contract.get('output_contract'), Mapping)
            else {}
        )
        policy_values = {
            str(source.get('excluded_reuse_policy_id') or '').strip()
            for source in (gap, recovery_attempt, recovery_state)
        }
        if policy_values != {EXPLICIT_IMAGE_EXCLUDED_POOL_RETRY_POLICY_ID}:
            return False
        if any(
            source.get('automatic_follow_up_allowed') is not False
            for source in (gap, recovery_attempt, recovery_state)
        ):
            return False
        if any(
            source.get('auto_execute') is not False
            for source in (recovery_attempt, recovery_state)
        ):
            return False
        attempt_trigger = str(recovery_attempt.get('trigger') or '').strip().lower()
        state_trigger = str(recovery_state.get('trigger') or '').strip().lower()
        if attempt_trigger != 'explicit_retry_endpoint' or state_trigger != attempt_trigger:
            return False
        capabilities = {
            self.normalize_capability(value)
            for value in (
                gap.get('expected_capability'),
                gap.get('active_capability'),
                execution_contract.get('capability'),
                recovery_attempt.get('capability'),
                recovery_state.get('capability'),
            )
            if str(value or '').strip()
        }
        if capabilities != {self.capability_image_generation}:
            return False
        output_type = str(
            gap.get('output_type')
            or execution_contract.get('output_type')
            or gap.get('missing_artifact_type')
            or ''
        ).strip().lower()
        if output_type != 'image' or output_contract.get('required') is not True:
            return False
        action = normalize_recovery_suggested_action(
            recovery_state.get('suggested_action')
            or gap.get('repair_action')
            or gap.get('recovery_action')
            or gap.get('suggested_action'),
            default='',
        )
        if action not in {
            RECOVERY_ACTION_RETRY_EXCLUDING_INSTANCE,
            RECOVERY_ACTION_START_COMPATIBLE_INSTANCE,
        }:
            return False
        prior_error_codes = {
            str(value or '').strip().upper()
            for value in (
                recovery_attempt.get('prior_error_code'),
                recovery_state.get('prior_error_code'),
            )
            if str(value or '').strip()
        }
        if prior_error_codes != {'NO_COMPATIBLE_INSTANCE'}:
            return False
        if str(recovery_state.get('retry_scope') or '').strip() != 'same_branch':
            return False
        branch_id = str(
            gap.get('branch_id') or execution_contract.get('branch_id') or ''
        ).strip()
        if not branch_id or any(
            str(source.get('branch_id') or '').strip() != branch_id
            for source in (recovery_attempt, recovery_state)
        ):
            return False
        if any(
            source.get('preserve_intent') is not True
            for source in (recovery_attempt, recovery_state)
        ):
            return False
        if any(
            source.get('needs_external_input') is True
            or source.get('materialization_blocked') is True
            for source in (gap, recovery_state)
        ):
            return False
        if gap.get('repair_work_available') is False:
            return False
        artifact_prompt = str(gap.get('artifact_prompt') or '').strip()
        artifact_prompt_source = str(
            gap.get('artifact_prompt_source') or ''
        ).strip()
        authoritative_prompt_sources = {
            'semantic_batch_prompt',
            'semantic_batch_prompts',
            'semantic_prepare_phase_output',
            'current_turn_direct_image_clause',
            'action_input',
            'prompt_blockquote_section',
            'quoted_prompt_section',
            'inline_prompt_capsule',
            'current_turn_explicit_image_manifest',
            'request_prompt_image_slots',
        }
        if (
            not artifact_prompt
            or artifact_prompt_source not in authoritative_prompt_sources
        ):
            return False
        try:
            expected_prompt_count = int(
                gap.get('batch_prompt_expected_count') or 0
            )
        except (TypeError, ValueError):
            return False
        if expected_prompt_count >= 2:
            batch_prompts = (
                gap.get('batch_prompts')
                if isinstance(gap.get('batch_prompts'), list)
                else []
            )
            exact_prompts = [
                str(item or '').strip()
                for item in batch_prompts
                if str(item or '').strip()
            ]
            try:
                selection_index = int(
                    gap.get('image_prompt_selection_index')
                    or execution_contract.get('queue_index')
                    or 0
                )
            except (TypeError, ValueError):
                return False
            if (
                len(batch_prompts) != expected_prompt_count
                or len(exact_prompts) != expected_prompt_count
                or not 1 <= selection_index <= expected_prompt_count
                or artifact_prompt != exact_prompts[selection_index - 1]
            ):
                return False
        attempt_excluded = {
            str(item or '').strip()
            for item in (recovery_attempt.get('excluded_instance_ids') or [])
            if str(item or '').strip()
        }
        state_excluded = {
            str(item or '').strip()
            for item in (recovery_state.get('exclude_instance_ids') or [])
            if str(item or '').strip()
        }
        gap_excluded = {
            str(item or '').strip()
            for item in (gap.get('excluded_instance_ids') or [])
            if str(item or '').strip()
        }
        return bool(
            attempt_excluded
            and attempt_excluded == state_excluded
            and attempt_excluded == gap_excluded
        )

    def _branch_is_explicit_image_excluded_pool_retry(
        self,
        branch: Mapping[str, Any],
    ) -> bool:
        if self.branch_capability(branch) != self.capability_image_generation:
            return False
        recovery_attempt = (
            branch.get('recovery_attempt')
            if isinstance(branch.get('recovery_attempt'), Mapping)
            else {}
        )
        recovery_state = (
            branch.get('recovery_state')
            if isinstance(branch.get('recovery_state'), Mapping)
            else {}
        )
        return bool(
            branch.get('excluded_reuse_policy_id')
            == EXPLICIT_IMAGE_EXCLUDED_POOL_RETRY_POLICY_ID
            and recovery_attempt.get('excluded_reuse_policy_id')
            == EXPLICIT_IMAGE_EXCLUDED_POOL_RETRY_POLICY_ID
            and recovery_state.get('excluded_reuse_policy_id')
            == EXPLICIT_IMAGE_EXCLUDED_POOL_RETRY_POLICY_ID
            and branch.get('automatic_follow_up_allowed') is False
            and recovery_attempt.get('automatic_follow_up_allowed') is False
            and recovery_state.get('automatic_follow_up_allowed') is False
            and str(recovery_attempt.get('trigger') or '').strip().lower()
            == 'explicit_retry_endpoint'
            and str(recovery_state.get('trigger') or '').strip().lower()
            == 'explicit_retry_endpoint'
            and recovery_attempt.get('auto_execute') is False
            and recovery_state.get('auto_execute') is False
        )

    _artifact_gap_is_authoritative_bounded_text_artifact_repair = staticmethod(text_artifact_materialization._artifact_gap_is_authoritative_bounded_text_artifact_repair)

    _artifact_gap_is_required_image_materialization = staticmethod(LateFillSelection._artifact_gap_is_required_image_materialization)

    _prefer_non_mlx_vlm_for_required_text_candidates = staticmethod(LateFillSelection._prefer_non_mlx_vlm_for_required_text_candidates)

    _runtime_scheduling_flag_enabled = staticmethod(LateFillSelection._runtime_scheduling_flag_enabled)

    _instance_identity_text = staticmethod(LateFillSelection._instance_identity_text)

    _late_fill_instance_is_large_chat_candidate = staticmethod(LateFillSelection._late_fill_instance_is_large_chat_candidate)

    _late_fill_instance_is_lightweight_chat_candidate = staticmethod(LateFillSelection._late_fill_instance_is_lightweight_chat_candidate)

    _runtime_scheduling_context = staticmethod(LateFillSelection._runtime_scheduling_context)

    _runtime_context_has_active_image_generation = staticmethod(LateFillSelection._runtime_context_has_active_image_generation)

    _runtime_context_prefers_lightweight_chat = staticmethod(LateFillSelection._runtime_context_prefers_lightweight_chat)

    _prefer_lightweight_chat_for_required_text_candidates = staticmethod(LateFillSelection._prefer_lightweight_chat_for_required_text_candidates)

    def _branch_is_image_generation(self, branch: Mapping[str, Any]) -> bool:
        return self.branch_selection._branch_is_image_generation(branch)

    def _branch_is_required_image_materialization(self, branch: Mapping[str, Any]) -> bool:
        return self.branch_selection._branch_is_required_image_materialization(branch)

    def _branch_is_required_tts_materialization(
        self,
        branch: Mapping[str, Any],
    ) -> bool:
        if (
            not isinstance(branch, Mapping)
            or self.branch_capability(branch) != self.capability_text_to_speech
            or not self.branch_id(branch)
        ):
            return False
        execution_contract = (
            branch.get('execution_contract')
            if isinstance(branch.get('execution_contract'), Mapping)
            else {}
        )
        output_contract = (
            branch.get('output_contract')
            if isinstance(branch.get('output_contract'), Mapping)
            else execution_contract.get('output_contract')
            if isinstance(execution_contract.get('output_contract'), Mapping)
            else {}
        )
        output_type = str(
            branch.get('output_type')
            or execution_contract.get('output_type')
            or output_contract.get('output_type')
            or ''
        ).strip().lower()
        if output_type and output_type != 'audio':
            return False
        if branch.get('required') is False or output_contract.get('required') is False:
            return False
        if branch.get('optional') is True or output_contract.get('optional') is True:
            return False
        return True

    def _required_tts_auto_recovery_allowed(
        self,
        branch: Mapping[str, Any],
        recovery_context: Mapping[str, Any],
    ) -> bool:
        if not self._branch_is_required_tts_materialization(branch):
            return False
        error_code = str(
            recovery_context.get('error_code') or ''
        ).strip().upper()
        if not error_code:
            return False
        if recovery_context.get('can_retry') is not True:
            return False
        if str(recovery_context.get('retry_scope') or '').strip() != 'same_branch':
            return False
        if recovery_context.get('preserve_intent') is not True:
            return False
        if recovery_context.get('needs_external_input') is True:
            return False
        if recovery_context.get('repair_work_available') is False:
            return False
        if any(
            recovery_context.get(key) is True
            for key in (
                'blocked_by_dependency_input',
                'blocked_by_branch_contract',
                'blocked_by_underplanned_promoted_obligations',
            )
        ):
            return False
        action = normalize_recovery_suggested_action(
            recovery_context.get('suggested_action'),
            default='',
        )
        if action not in {
            *_AUTO_EXECUTABLE_REPAIR_RETRY_ACTIONS,
            RECOVERY_ACTION_START_COMPATIBLE_INSTANCE,
        }:
            return False
        materialization_blocked = (
            recovery_context.get('materialization_blocked') is True
        )
        if error_code != 'TTS_AUDIO_INTEGRITY_REPAIR_REQUIRED':
            return not materialization_blocked
        if not materialization_blocked:
            return False
        if str(recovery_context.get('blocked_scope') or '').strip() != (
            'current_tts_branch'
        ):
            return False
        if recovery_context.get('repair_work_available') is not True:
            return False
        integrity_evidence = (
            recovery_context.get('audio_integrity_evidence')
            if isinstance(
                recovery_context.get('audio_integrity_evidence'),
                Mapping,
            )
            else {}
        )
        return bool(
            str(integrity_evidence.get('kind') or '').strip()
            == 'fruth.tts_audio_integrity_evidence'
            and integrity_evidence.get('version') == 1
            and str(integrity_evidence.get('policy_id') or '').strip()
            == TTS_AUDIO_INTEGRITY_POLICY_ID
            and str(integrity_evidence.get('authority') or '').strip()
            == 'runtime_deterministic_audio_verification'
            and str(integrity_evidence.get('status') or '').strip().lower()
            in {'failed', 'unavailable'}
            and integrity_evidence.get('materialization_eligible') is False
        )

    def _branch_is_required_text_artifact(self, branch: Mapping[str, Any]) -> bool:
        return self.branch_selection._branch_is_required_text_artifact(branch)

    def _branch_is_required_artifact(self, branch: Mapping[str, Any]) -> bool:
        return self.branch_selection._branch_is_required_artifact(branch)

    def _branch_is_optional_advisory_helper(self, branch: Mapping[str, Any]) -> bool:
        return self.branch_selection._branch_is_optional_advisory_helper(branch)

    def _branch_scheduling_context(
        self,
        branch: Mapping[str, Any],
        artifact_gap: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        return self.branch_selection._branch_scheduling_context(branch, artifact_gap)

    def _branch_is_target_artifact_snapshot_text_repair(
        self,
        branch: Mapping[str, Any],
        artifact_gap: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        return self.branch_selection._branch_is_target_artifact_snapshot_text_repair(branch, artifact_gap)

    def _branch_conflicts_with_active_image_generation(
        self,
        branch: Mapping[str, Any],
        artifact_gap: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        return self.branch_selection._branch_conflicts_with_active_image_generation(branch, artifact_gap)

    def _branch_allows_gpu_heavy_concurrency(
        self,
        branch: Mapping[str, Any],
        artifact_gap: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        return self.branch_selection._branch_allows_gpu_heavy_concurrency(branch, artifact_gap)

    def shape_active_late_fill_branches(
        self,
        active_branches: list[dict[str, Any]],
        *,
        artifact_gap: Optional[Mapping[str, Any]] = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        return self.branch_selection.shape_active_late_fill_branches(active_branches, artifact_gap=artifact_gap)

    def select_active_late_fill_branches(
        self,
        dependency_ready_branches: list[dict[str, Any]],
        *,
        artifact_gap: Optional[Mapping[str, Any]] = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        return self.branch_selection.select_active_late_fill_branches(dependency_ready_branches, artifact_gap=artifact_gap)

    @staticmethod
    def _text_artifact_request_from_branch_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
        branch = spec.get('branch') if isinstance(spec.get('branch'), Mapping) else {}
        prepare_args = spec.get('prepare_args') if isinstance(spec.get('prepare_args'), Mapping) else {}
        gap = prepare_args.get('artifact_gap') if isinstance(prepare_args.get('artifact_gap'), Mapping) else {}
        artifact_request = (
            branch.get('artifact_request')
            if isinstance(branch.get('artifact_request'), Mapping)
            else gap.get('artifact_request')
            if isinstance(gap.get('artifact_request'), Mapping)
            else {}
        )
        extension = str(
            branch.get('text_artifact_extension')
            or gap.get('text_artifact_extension')
            or artifact_request.get('extension')
            or ''
        ).strip().lower().lstrip('.')
        source_name = str(
            branch.get('text_artifact_source_name')
            or gap.get('text_artifact_source_name')
            or artifact_request.get('source_name')
            or f'generated-{extension or "txt"}'
        ).strip()
        source = str(
            branch.get('text_artifact_source')
            or gap.get('text_artifact_source')
            or artifact_request.get('source')
            or 'runtime_contract'
        ).strip()
        target_path = str(
            branch.get('text_artifact_target_path')
            or gap.get('text_artifact_target_path')
            or artifact_request.get('target_path')
            or ''
        ).strip()
        if not extension or not source_name:
            return {}
        request = {
            'extension': extension,
            'source_name': source_name,
            'source': source,
        }
        if target_path:
            request['target_path'] = target_path
        return request

    @staticmethod
    def _branch_spec_disables_required_text_artifact_coalescing(
        spec: Mapping[str, Any],
        branch: Mapping[str, Any],
    ) -> bool:
        prepare_args = spec.get('prepare_args') if isinstance(spec.get('prepare_args'), Mapping) else {}
        gap = prepare_args.get('artifact_gap') if isinstance(prepare_args.get('artifact_gap'), Mapping) else {}
        for source in (spec, branch, gap, prepare_args):
            if not isinstance(source, Mapping):
                continue
            request = source.get('artifact_request') or {}
            if request.get('saved_file_producer') or request.get('saved_file_dependency'):
                return True
            if source.get('materialization_blocked') or source.get('branch_contract_error'):
                return True
            contract = source.get('execution_contract')
            for dependency_owner in (source, contract if isinstance(contract, Mapping) else {}):
                # One common preparation answer is safe to share. A consumer
                # of any later phase must keep its own accepted input packet.
                if any(str(item or '').strip() != 'phase-1'
                       for item in (dependency_owner.get('depends_on') or [])):
                    return True
            if source.get('disable_coalesced_text_artifact_retry') is True:
                return True
            if source.get('coalesced_text_artifact_split_retry') is True:
                return True
            if str(source.get('failed_instance_id') or '').strip():
                return True
            for exclusion_key in (
                'excluded_instance_ids',
                'excludedInstanceIds',
                'exclude_instance_ids',
                'excludeInstanceIds',
            ):
                if isinstance(source.get(exclusion_key), list) and any(
                    str(item or '').strip()
                    for item in source.get(exclusion_key) or []
                ):
                    return True
            attempt = (
                source.get('attempt')
                if isinstance(source.get('attempt'), Mapping)
                else {}
            )
            if str(attempt.get('instance_id') or '').strip():
                return True
            for recovery_key in (
                'recovery_context',
                'recovery_state',
                'recovery_attempt',
            ):
                if isinstance(source.get(recovery_key), Mapping) and source.get(
                    recovery_key
                ):
                    return True
            if text_artifact_materialization._text_artifact_revision_required(source):
                # Every revision owns a different complete source snapshot.
                # Combining those branches would give one model call only the
                # first file's edit base and would destroy branch-local truth.
                return True
            try:
                retry_count = int(source.get('auto_executable_repair_retry_count') or 0)
            except (TypeError, ValueError):
                retry_count = 0
            if retry_count > 0:
                return True
        return False

    def _coalesce_required_text_artifact_branch_specs(
        self,
        branch_specs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        specs = [dict(spec) for spec in branch_specs if isinstance(spec, dict)]
        if len(specs) <= 1:
            return specs
        branches = [
            spec.get('branch') if isinstance(spec.get('branch'), Mapping) else {}
            for spec in specs
        ]
        if not branches:
            return specs
        requests: list[dict[str, Any]] = []
        branch_refs: list[dict[str, Any]] = []
        request_index_by_identity: dict[tuple[str, ...], int] = {}
        coalesced_indexes: set[int] = set()
        seen_branch_ref_ids: set[str] = set()
        for index, (spec, branch) in enumerate(zip(specs, branches)):
            if self.normalize_capability(spec.get('capability')) != 'chat':
                continue
            if self._branch_spec_disables_required_text_artifact_coalescing(spec, branch):
                continue
            if not self.branch_selection._branch_is_required_text_artifact(branch):
                continue
            request = self._text_artifact_request_from_branch_spec(spec)
            extension = str(request.get('extension') or '').strip().lower()
            target_path = str(request.get('target_path') or '').strip()
            source_name = str(request.get('source_name') or '').strip().lower()
            request_identity = (
                ('target', target_path)
                if target_path
                else ('named', extension, source_name)
            )
            if not request or not extension:
                continue
            coalesced_indexes.add(index)
            if request_identity not in request_index_by_identity:
                request_index_by_identity[request_identity] = len(requests)
                requests.append(request)
            prepare_args = (
                spec.get('prepare_args')
                if isinstance(spec.get('prepare_args'), Mapping)
                else {}
            )
            branch_gap = (
                prepare_args.get('artifact_gap')
                if isinstance(prepare_args.get('artifact_gap'), Mapping)
                else {}
            )
            branch_ref_id = self.branch_id(branch)
            if not branch_ref_id or branch_ref_id in seen_branch_ref_ids:
                continue
            seen_branch_ref_ids.add(branch_ref_id)
            branch_refs.append(
                {
                    'branch_id': branch_ref_id,
                    'phase_id': str(branch.get('phase_id') or branch_ref_id).strip() or branch_ref_id,
                    'capability': self.branch_capability(branch),
                    'output_type': branch.get('output_type'),
                    'text_artifact_extension': request.get('extension'),
                    'text_artifact_source_name': request.get('source_name'),
                    'text_artifact_source': request.get('source'),
                    'artifact_request': dict(request),
                    'execution_contract': self.build_execution_contract(
                        branch,
                        branch_gap,
                        capability='chat',
                    ),
                }
            )
        if len(coalesced_indexes) <= 1 or not requests or len(branch_refs) <= 1:
            return specs
        first_index = min(coalesced_indexes)
        base = dict(specs[first_index])
        base_prepare_args = (
            dict(base.get('prepare_args') or {})
            if isinstance(base.get('prepare_args'), Mapping)
            else {}
        )
        base_gap = (
            dict(base_prepare_args.get('artifact_gap') or {})
            if isinstance(base_prepare_args.get('artifact_gap'), Mapping)
            else {}
        )
        readable_cohort = '-'.join(
            str(ref.get('branch_id') or '').strip()
            for ref in branch_refs
            if str(ref.get('branch_id') or '').strip()
        )
        cohort_digest = hashlib.sha256(
            json.dumps(
                {'branches': branch_refs, 'requests': requests},
                sort_keys=True,
            ).encode('utf-8')
        ).hexdigest()[:12]
        coalesced_branch_id = (
            f'coalesced-text-artifacts-{readable_cohort[:64]}-{cohort_digest}'
        )
        coalesced_branch = {
            'branch_id': coalesced_branch_id,
            'phase_id': coalesced_branch_id,
            'capability': 'chat',
            'output_type': 'text',
            'stage_direction': 'materialize_requested_text_artifact',
            'requires_artifact': True,
            'text_artifact_requests': [dict(request) for request in requests],
            'coalesced_text_artifact_wave': True,
            'coalesced_text_artifact_branches': [dict(ref) for ref in branch_refs],
        }
        base_gap.update(
            {
                'branch_id': coalesced_branch_id,
                'phase_id': coalesced_branch_id,
                'stage_direction': 'materialize_requested_text_artifact',
                'requires_artifact': True,
                'text_artifact_requests': [dict(request) for request in requests],
                'artifact_request': dict(requests[0]),
                'text_artifact_extension': str(requests[0].get('extension') or ''),
                'text_artifact_source_name': str(requests[0].get('source_name') or ''),
                'text_artifact_source': str(requests[0].get('source') or ''),
                'coalesced_text_artifact_wave': True,
                'coalesced_text_artifact_branches': [dict(ref) for ref in branch_refs],
            }
        )
        base_prepare_args['artifact_gap'] = base_gap
        base['branch_id'] = coalesced_branch_id
        base['phase_id'] = coalesced_branch_id
        base['capability'] = 'chat'
        base['reservation_group'] = 'chat'
        base['branch'] = coalesced_branch
        base['text_artifact_requests'] = [dict(request) for request in requests]
        base['coalesced_text_artifact_wave'] = True
        base['coalesced_text_artifact_branches'] = [dict(ref) for ref in branch_refs]
        base['prepare_args'] = base_prepare_args
        coalesced_specs: list[dict[str, Any]] = []
        for index, spec in enumerate(specs):
            if index == first_index:
                coalesced_specs.append(base)
            if index in coalesced_indexes:
                continue
            coalesced_specs.append(spec)
        return coalesced_specs

    def _retry_failed_coalesced_text_artifact_materializations(
        self,
        branch_specs: list[dict[str, Any]],
        materialization_result: dict[str, Any],
        *,
        prepare_branch_plan: Callable[..., dict[str, Any]],
        execute_prepared_branch: Callable[[dict[str, Any]], dict[str, Any]],
        on_branch_progress: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> dict[str, Any]:
        """Retry a failed fresh N-file branch once without splitting it."""

        def expand(raw: Mapping[str, Any], specs: list[dict[str, Any]]) -> dict[str, Any]:
            normalized = dict(raw or {})
            errors = dict(normalized.get('branch_errors') or {})
            plans = [
                dict(plan)
                for plan in (normalized.get('prepared_branch_plans') or [])
                if isinstance(plan, Mapping)
            ]
            planned = {str(plan.get('branch_id') or '').strip() for plan in plans}
            for spec in specs:
                cohort_id = str(spec.get('branch_id') or '').strip()
                if (
                    spec.get('coalesced_text_artifact_wave') is True
                    and cohort_id in errors
                    and cohort_id not in planned
                ):
                    plans.append(
                        {
                            'branch_id': cohort_id,
                            'phase_id': str(spec.get('phase_id') or cohort_id),
                            'capability': 'chat',
                            'branch': dict(spec),
                        }
                    )
            normalized['prepared_branch_plans'] = plans
            return self._expand_coalesced_text_artifact_materialization(normalized)

        initial = expand(materialization_result or {}, branch_specs)
        initial_results = dict(initial.get('branch_results') or {})
        initial_errors = dict(initial.get('branch_errors') or {})
        retry_specs: list[dict[str, Any]] = []
        markers: dict[str, dict[str, Any]] = {}
        for spec in branch_specs:
            requests = [
                dict(item)
                for item in (spec.get('text_artifact_requests') or [])
                if isinstance(item, Mapping)
            ]
            refs = [
                dict(item)
                for item in (spec.get('coalesced_text_artifact_branches') or [])
                if isinstance(item, Mapping)
            ]
            member_ids = [str(item.get('branch_id') or '').strip() for item in refs]
            member_errors = [initial_errors.get(member_id) for member_id in member_ids]
            if (
                spec.get('coalesced_text_artifact_wave') is not True
                or len(requests) < 2
                or len(requests) != len(member_ids)
                or any(not member_id for member_id in member_ids)
                or any(str(item.get('target_path') or '').strip() for item in requests)
                or all(
                    member_id in initial_results and member_id not in initial_errors
                    for member_id in member_ids
                )
                or not any(isinstance(error, Mapping) and error for error in member_errors)
                or any(
                    isinstance(error, Mapping) and error.get('retryable') is False
                    for error in member_errors
                )
                or any(
                    isinstance(error, Mapping)
                    and error.get('code') == 'INSTANCE_UNAVAILABLE'
                    and error.get('stage') == 'prepare_branch_plan'
                    for error in member_errors
                )
            ):
                continue
            cohort_id = str(spec.get('branch_id') or '').strip()
            marker = {
                'kind': 'fruth.coalesced_text_artifact_recovery',
                'trigger': _COALESCED_TEXT_ARTIFACT_RECOVERY_TRIGGER,
                'cohort_id': cohort_id,
                'member_branch_ids': member_ids,
                'artifact_manifest': requests,
                'attempt_number': 2,
                'maximum_attempts': _COALESCED_TEXT_ARTIFACT_RECOVERY_MAX_ATTEMPTS,
                'prior_error_code': str(
                    (member_errors[0] or {}).get('code') or 'BACKEND_ERROR'
                ).strip().upper(),
                'atomic_set_required': True,
                'materialization_authority': 'fruth_runtime',
            }
            retry_spec = copy.deepcopy(spec)
            retry_spec['coalesced_text_artifact_recovery'] = dict(marker)
            prepare_args = dict(retry_spec.get('prepare_args') or {})
            gap = dict(prepare_args.get('artifact_gap') or {})
            gap['coalesced_text_artifact_recovery'] = dict(marker)
            prepare_args.update({'artifact_gap': gap, 'failed_instance_id': None})
            retry_spec['prepare_args'] = prepare_args
            retry_specs.append(retry_spec)
            markers[cohort_id] = marker

        if not retry_specs:
            return initial

        retry_raw = self.execute_materialization_branches(
            retry_specs,
            prepare_branch_plan=prepare_branch_plan,
            execute_prepared_branch=execute_prepared_branch,
            on_branch_progress=on_branch_progress,
            async_branch_progress=True,
        )
        retry = expand(retry_raw, retry_specs)
        retry_results = dict(retry.get('branch_results') or {})
        retry_errors = dict(retry.get('branch_errors') or {})
        retried_members = {
            member_id
            for marker in markers.values()
            for member_id in marker['member_branch_ids']
        }
        combined_results = {
            key: value for key, value in initial_results.items()
            if key not in retried_members
        }
        combined_errors = {
            key: value for key, value in initial_errors.items()
            if key not in retried_members
        }
        history: list[dict[str, Any]] = []
        for marker in markers.values():
            member_ids = marker['member_branch_ids']
            saved_paths = [
                str(
                    (
                        (retry_results.get(member_id) or {}).get('infer_result')
                        or {}
                    ).get('saved_text_path')
                    or ''
                ).strip()
                for member_id in member_ids
            ]
            completed = (
                all(
                    member_id in retry_results and member_id not in retry_errors
                    for member_id in member_ids
                )
                and all(saved_paths)
                and len(set(saved_paths)) == len(member_ids)
                and len({str(Path(path).parent) for path in saved_paths}) == 1
            )
            if completed:
                combined_results.update(
                    {member_id: retry_results[member_id] for member_id in member_ids}
                )
            else:
                for member_id in member_ids:
                    combined_errors[member_id] = {
                        **dict(retry_errors.get(member_id) or {}),
                        'code': 'COALESCED_TEXT_ARTIFACT_COHORT_RETRY_EXHAUSTED',
                        'message': 'The bounded N-file retry did not return the complete set.',
                        'retryable': False,
                        'coalesced_text_artifact_recovery': dict(marker),
                    }
            history.append({**marker, 'status': 'completed' if completed else 'exhausted'})

        combined = dict(initial)
        combined['branch_results'] = combined_results
        combined['branch_errors'] = combined_errors
        combined['prepared_branch_plans'] = [
            *[
                dict(plan)
                for plan in (initial.get('prepared_branch_plans') or [])
                if isinstance(plan, Mapping)
                and str(plan.get('branch_id') or '').strip()
                not in retried_members
            ],
            *[
                dict(plan)
                for plan in (retry.get('prepared_branch_plans') or [])
                if isinstance(plan, Mapping)
            ],
        ]
        combined['coalesced_text_artifact_recovery_history'] = history
        combined['materialization_concurrency_policies'] = [
            dict(policy)
            for policy in (
                materialization_result.get('concurrency_policy'),
                retry_raw.get('concurrency_policy'),
            )
            if isinstance(policy, Mapping) and policy
        ]
        if isinstance(retry_raw.get('concurrency_policy'), Mapping):
            combined['concurrency_policy'] = dict(
                retry_raw.get('concurrency_policy') or {}
            )
        return combined

    _normalized_text_artifact_path_for_match = staticmethod(text_artifact_materialization._normalized_text_artifact_path_for_match)

    _text_artifact_path_matches_target = staticmethod(text_artifact_materialization._text_artifact_path_matches_target)

    _text_artifact_target_path_from_mapping = staticmethod(LinkedArtifactMaterialization._text_artifact_target_path_from_mapping)

    _saved_text_artifact_matches_request = staticmethod(TextArtifactResultEvidence._saved_text_artifact_matches_request)

    _read_small_text_artifact = staticmethod(TextArtifactResultEvidence._read_small_text_artifact)

    _text_artifact_revision_source_payload = staticmethod(TextArtifactFiles._text_artifact_revision_source_payload)

    def _expand_coalesced_text_artifact_materialization(
        self,
        materialization_result: dict[str, Any],
    ) -> dict[str, Any]:
        result = dict(materialization_result or {})
        prepared_plans = [
            dict(plan)
            for plan in (result.get('prepared_branch_plans') or [])
            if isinstance(plan, Mapping)
        ]
        branch_results = (
            dict(result.get('branch_results') or {})
            if isinstance(result.get('branch_results'), Mapping)
            else {}
        )
        branch_errors = (
            dict(result.get('branch_errors') or {})
            if isinstance(result.get('branch_errors'), Mapping)
            else {}
        )
        expanded_results: dict[str, dict[str, Any]] = {}
        expanded_errors: dict[str, dict[str, Any]] = {}
        expanded_plans: list[dict[str, Any]] = []
        expanded_coalesced_branch_ids: set[str] = set()

        def member_execution_contract(
            plan: Mapping[str, Any],
            ref: Mapping[str, Any],
        ) -> dict[str, Any]:
            branch_id = str(ref.get('branch_id') or '').strip()
            phase_id = str(ref.get('phase_id') or branch_id).strip() or branch_id
            contract = dict(
                ref.get('execution_contract')
                if isinstance(ref.get('execution_contract'), Mapping)
                else plan.get('execution_contract')
                if isinstance(plan.get('execution_contract'), Mapping)
                else {}
            )
            workload_ref = dict(contract.get('workload_task_ref') or {})
            obligation_ref = dict(contract.get('output_obligation_ref') or {})
            workload_ref.update({'branch_id': branch_id, 'phase_id': phase_id})
            obligation_ref.update(
                {
                    'branch_id': branch_id,
                    'phase_id': phase_id,
                    'output_type': 'text',
                }
            )
            contract.update(
                {
                    'branch_id': branch_id,
                    'phase_id': phase_id,
                    'capability': 'chat',
                    'output_type': 'text',
                    'workload_task_ref': workload_ref,
                    'output_obligation_ref': obligation_ref,
                }
            )
            return contract

        for plan in prepared_plans:
            branch = plan.get('branch') if isinstance(plan.get('branch'), Mapping) else {}
            nested_branch = branch.get('branch') if isinstance(branch.get('branch'), Mapping) else {}
            branch_refs = (
                branch.get('coalesced_text_artifact_branches')
                if isinstance(branch.get('coalesced_text_artifact_branches'), list)
                else nested_branch.get('coalesced_text_artifact_branches')
                if isinstance(nested_branch.get('coalesced_text_artifact_branches'), list)
                else []
            )
            coalesced_branch_id = str(
                plan.get('branch_id')
                or branch.get('branch_id')
                or nested_branch.get('branch_id')
                or ''
            ).strip()
            if not branch_refs or not coalesced_branch_id:
                expanded_plans.append(plan)
                continue
            expanded_coalesced_branch_ids.add(coalesced_branch_id)
            source_result = branch_results.get(coalesced_branch_id)
            source_error = branch_errors.get(coalesced_branch_id)
            if source_error:
                for ref in branch_refs:
                    branch_id = str((ref or {}).get('branch_id') or '').strip()
                    if branch_id:
                        expanded_errors[branch_id] = dict(source_error)
                continue
            if not isinstance(source_result, Mapping):
                continue
            infer_result = source_result.get('infer_result') if isinstance(source_result.get('infer_result'), Mapping) else {}
            external_provider_block = (
                infer_result.get('external_provider_block')
                if isinstance(
                    infer_result.get('external_provider_block'),
                    Mapping,
                )
                else {}
            )
            if external_provider_block:
                for ref in branch_refs:
                    if not isinstance(ref, Mapping):
                        continue
                    branch_id = str(ref.get('branch_id') or '').strip()
                    if not branch_id:
                        continue
                    phase_id = str(
                        ref.get('phase_id') or branch_id
                    ).strip() or branch_id
                    branch_plan = dict(plan)
                    branch_plan['branch_id'] = branch_id
                    branch_plan['phase_id'] = phase_id
                    branch_plan['execution_contract'] = member_execution_contract(
                        plan,
                        ref,
                    )
                    expanded_plans.append(branch_plan)
                    expanded_results[branch_id] = {
                        **dict(source_result),
                        'branch_id': branch_id,
                        'phase_id': phase_id,
                        'execution_contract': dict(
                            branch_plan['execution_contract']
                        ),
                        'infer_result': dict(infer_result),
                    }
                continue
            saved_text_artifacts: list[dict[str, Any]] = []
            seen_saved_text_paths: set[str] = set()

            def add_saved_text_artifact(raw_item: Any) -> None:
                if not isinstance(raw_item, Mapping):
                    return
                item = dict(raw_item)
                path = str(item.get('path') or item.get('saved_text_path') or '').strip()
                if path and path in seen_saved_text_paths:
                    return
                if path:
                    seen_saved_text_paths.add(path)
                saved_text_artifacts.append(item)

            def collect_saved_text_artifacts(source: Mapping[str, Any]) -> None:
                for key in ('saved_text_artifacts', 'text_artifacts', 'artifacts'):
                    values = source.get(key)
                    if not isinstance(values, list):
                        continue
                    for item in values:
                        add_saved_text_artifact(item)
                saved_path = str(source.get('saved_text_path') or '').strip()
                if saved_path:
                    add_saved_text_artifact(
                        {
                            'path': saved_path,
                            'saved_text_path': saved_path,
                            'text_artifact_request': (
                                dict(source.get('text_artifact_request') or {})
                                if isinstance(source.get('text_artifact_request'), Mapping)
                                else {}
                            ),
                            'text_artifact_extension': source.get('text_artifact_extension'),
                            'text_artifact_source_name': source.get('text_artifact_source_name'),
                            'text_artifact_source': source.get('text_artifact_source'),
                        }
                    )

            collect_saved_text_artifacts(infer_result)
            collect_saved_text_artifacts(source_result)
            for ref in branch_refs:
                if not isinstance(ref, Mapping):
                    continue
                branch_id = str(ref.get('branch_id') or '').strip()
                if not branch_id:
                    continue
                request = ref.get('artifact_request') if isinstance(ref.get('artifact_request'), Mapping) else {}
                matched_artifact = next(
                    (
                        artifact
                        for artifact in saved_text_artifacts
                        if TextArtifactResultEvidence._saved_text_artifact_matches_request(artifact, request)
                    ),
                    {},
                )
                if matched_artifact:
                    request_extension = str(request.get('extension') or '').strip().lower().lstrip('.')
                    request_source_name = str(request.get('source_name') or '').strip()
                    request_target_path = LinkedArtifactMaterialization._text_artifact_target_path_from_mapping(request)
                    repaired_or_clean_artifact = self.text_artifact_result_evidence._canonical_text_artifact_saved_result(
                        {'artifacts': [dict(matched_artifact)]},
                        extension=request_extension,
                        source_name=request_source_name,
                        target_path=request_target_path,
                        allow_deterministic_repair=True,
                    )
                    if repaired_or_clean_artifact:
                        matched_artifact = repaired_or_clean_artifact
                if not matched_artifact:
                    request_target_path = LinkedArtifactMaterialization._text_artifact_target_path_from_mapping(request)
                    target_binding_error = text_artifact_materialization._text_artifact_target_binding_violation(
                        {'saved_text_artifacts': saved_text_artifacts},
                        target_path=request_target_path,
                        extension=str(request.get('extension') or '').strip().lower().lstrip('.'),
                        source_name=str(request.get('source_name') or '').strip(),
                    )
                    expanded_errors[branch_id] = {
                        **(
                            target_binding_error
                            or {
                                'code': 'COALESCED_TEXT_ARTIFACT_NOT_PERSISTED',
                                'message': (
                                    'Coalesced text artifact materialization returned without the expected saved file.'
                                ),
                            }
                        ),
                        'stage': 'execute_prepared_branch',
                        'retryable': True,
                    }
                    continue
                saved_path = str(matched_artifact.get('path') or matched_artifact.get('saved_text_path') or '').strip()
                artifact_content = TextArtifactResultEvidence._read_small_text_artifact(saved_path)
                branch_infer_result = dict(infer_result)
                branch_infer_result['saved_text_path'] = saved_path
                branch_infer_result['saved_text_artifacts'] = [dict(matched_artifact)]
                branch_infer_result['text_artifact_request'] = dict(request)
                branch_infer_result['text_artifact_requests'] = [dict(request)]
                branch_infer_result['text_artifact_extension'] = request.get('extension')
                branch_infer_result['text_artifact_source_name'] = request.get('source_name')
                branch_infer_result['text_artifact_source'] = request.get('source')
                branch_infer_result['coalesced_text_artifact_wave'] = True
                branch_infer_result['coalesced_text_artifact_branch_id'] = coalesced_branch_id
                if artifact_content:
                    branch_infer_result['output_text'] = artifact_content
                    branch_infer_result['content'] = artifact_content
                    branch_infer_result['content_payload'] = artifact_content
                branch_plan = dict(plan)
                branch_plan['branch_id'] = branch_id
                branch_plan['phase_id'] = str(ref.get('phase_id') or branch_id).strip() or branch_id
                branch_plan['execution_contract'] = {
                    **member_execution_contract(plan, ref),
                    'artifact_request': dict(request),
                    'text_artifact_extension': request.get('extension'),
                    'text_artifact_source_name': request.get('source_name'),
                    'text_artifact_source': request.get('source'),
                }
                expanded_plans.append(branch_plan)
                expanded_results[branch_id] = {
                    **dict(source_result),
                    'branch_id': branch_id,
                    'phase_id': str(ref.get('phase_id') or branch_id).strip() or branch_id,
                    'execution_contract': dict(branch_plan['execution_contract']),
                    'infer_result': branch_infer_result,
                }
        for branch_id, value in branch_results.items():
            if branch_id not in expanded_results and not any(
                str((plan.get('branch') or {}).get('branch_id') or '').strip() == branch_id
                and isinstance((plan.get('branch') or {}).get('coalesced_text_artifact_branches'), list)
                for plan in prepared_plans
            ):
                expanded_results[branch_id] = value
        for branch_id, value in branch_errors.items():
            if (
                branch_id not in expanded_errors
                and branch_id not in expanded_coalesced_branch_ids
            ):
                expanded_errors[branch_id] = value
        if expanded_results or expanded_errors:
            result['branch_results'] = expanded_results
            result['branch_errors'] = expanded_errors
            result['prepared_branch_plans'] = expanded_plans or prepared_plans
        return result

    @staticmethod
    def materialization_concurrency_history(
        prior_state: Optional[Mapping[str, Any]],
        policy: Optional[Mapping[str, Any]],
        *,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        policy_payload = dict(policy) if isinstance(policy, Mapping) else {}
        if not policy_payload:
            return []
        history = (
            prior_state.get('materialization_concurrency_history')
            if isinstance(prior_state, Mapping)
            and isinstance(prior_state.get('materialization_concurrency_history'), list)
            else []
        )
        entries = [
            dict(item)
            for item in history
            if isinstance(item, Mapping)
        ]
        entries.append(policy_payload)
        return entries[-max(1, int(limit)):]

    @staticmethod
    def _runtime_candidate_snapshot_meta(
        snapshot: list[dict[str, Any]],
        *,
        source: str,
    ) -> dict[str, Any]:
        instance_ids = [
            str(entry.get('instance_id') or '').strip()
            for entry in snapshot
            if isinstance(entry, Mapping) and str(entry.get('instance_id') or '').strip()
        ]
        return {
            'source': source,
            'candidate_count': len(snapshot),
            'candidate_instance_ids': instance_ids,
        }

    def runtime_candidate_snapshot_for_late_fill_wave(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        try:
            instances = self.merge_instances_with_runtime_status(
                self.load_running_instances(),
                path=self.runtime_status_path_getter(),
                refresh=True,
            )
        except Exception as exc:  # noqa: BLE001
            logging.info('Late-fill runtime candidate snapshot unavailable: %s', exc)
            return [], self._runtime_candidate_snapshot_meta([], source='late_fill_wave_error')
        snapshot = [
            dict(entry)
            for entry in (instances or [])
            if isinstance(entry, Mapping)
        ]
        return snapshot, self._runtime_candidate_snapshot_meta(snapshot, source='late_fill_wave')

    def runtime_scheduling_context_for_branch(
        self,
        branch: Mapping[str, Any],
        *,
        current_payload: Mapping[str, Any],
        source_route_payload: Optional[Mapping[str, Any]],
        artifact_gap: Optional[Mapping[str, Any]],
    ) -> dict[str, Any]:
        late_fill_state = current_payload.get('late_fill') if isinstance(current_payload.get('late_fill'), Mapping) else {}
        active_branches = late_fill_state.get('active_branches') if isinstance(late_fill_state.get('active_branches'), list) else []
        active_capabilities = self.normalize_capability_list(
            [self.branch_capability(item) for item in active_branches if isinstance(item, Mapping) and self.branch_capability(item)]
        )
        context = LateFillSelection._runtime_scheduling_context(artifact_gap, source_route_payload)
        branch_context = self.branch_selection._branch_scheduling_context(branch, artifact_gap)
        for key in ('repair_scope', 'resource_class', 'dependency_policy'):
            value = branch_context.get(key)
            if value not in (None, '', [], {}):
                context[key] = value
        if active_capabilities:
            context['active_capabilities'] = active_capabilities
        if any(capability == self.capability_image_generation for capability in active_capabilities):
            context['active_image_generation'] = True
        if source_route_payload and isinstance(source_route_payload, Mapping):
            route_instance = source_route_payload.get('instance') if isinstance(source_route_payload.get('instance'), Mapping) else {}
            if route_instance:
                if LateFillSelection._late_fill_instance_is_lightweight_chat_candidate(route_instance):
                    context.setdefault('selected_chat_model_class', 'lightweight')
                context.setdefault('selected_chat_model', route_instance.get('model') or route_instance.get('model_name'))
                context.setdefault('selected_chat_instance_id', route_instance.get('instance_id'))
        if self.branch_selection._branch_allows_gpu_heavy_concurrency(branch, artifact_gap):
            context['allow_gpu_heavy_concurrency'] = True
        return {key: value for key, value in context.items() if value not in (None, '', [], {})}

    def response_has_required_artifact_closure_work(self, current_payload: Mapping[str, Any]) -> bool:
        late_fill_state = current_payload.get('late_fill') if isinstance(current_payload.get('late_fill'), Mapping) else {}
        for key in ('pending_branches', 'active_branches'):
            branches = late_fill_state.get(key) if isinstance(late_fill_state.get(key), list) else []
            for branch in branches:
                if isinstance(branch, Mapping) and self.branch_selection._branch_is_required_artifact(branch):
                    return True
        return False

    @staticmethod
    def _late_fill_payload_has_open_work(payload: Mapping[str, Any]) -> bool:
        late_fill = payload.get('late_fill') if isinstance(payload.get('late_fill'), Mapping) else {}
        if not late_fill:
            return False
        for key in ('pending_branches', 'active_branches'):
            if isinstance(late_fill.get(key), list) and late_fill.get(key):
                return True
        if isinstance(late_fill.get('pending_capabilities'), list) and late_fill.get('pending_capabilities'):
            return True
        return str(late_fill.get('status') or '').strip().lower() in {'pending', 'running', 'active'}

    @classmethod
    def _prefer_explicit_late_fill_seed_payload(
        cls,
        explicit_payload: Mapping[str, Any],
        recovered_payload: Mapping[str, Any],
    ) -> bool:
        if not isinstance(explicit_payload, Mapping) or not explicit_payload:
            return False
        if not isinstance(recovered_payload, Mapping) or not recovered_payload:
            return True
        if not cls._late_fill_payload_has_open_work(explicit_payload):
            return False
        return not cls._late_fill_payload_has_open_work(recovered_payload)

    def build_execution_contract(
        self,
        branch: Mapping[str, Any],
        artifact_gap: Optional[Mapping[str, Any]] = None,
        *,
        capability: Optional[str] = None,
    ) -> dict[str, Any]:
        branch_payload = branch if isinstance(branch, Mapping) else {}
        gap_payload = artifact_gap if isinstance(artifact_gap, Mapping) else {}
        normalized_capability = self.normalize_capability(
            capability
            or branch_payload.get('capability')
            or gap_payload.get('capability')
            or gap_payload.get('expected_capability')
        )
        branch_id = _contract_text(
            _first_contract_value(
                branch_payload.get('branch_id'),
                gap_payload.get('branch_id'),
                branch_payload.get('phase_id'),
                gap_payload.get('phase_id'),
            )
        )
        phase_id = _contract_text(
            _first_contract_value(
                branch_payload.get('phase_id'),
                gap_payload.get('phase_id'),
                branch_payload.get('branch_id'),
                gap_payload.get('branch_id'),
            )
        )
        task_id = _contract_text(
            _first_contract_value(
                branch_payload.get('task_id'),
                branch_payload.get('workload_task_id'),
                gap_payload.get('task_id'),
                gap_payload.get('workload_task_id'),
                f'task-{phase_id}' if phase_id else None,
            )
        )
        obligation_id = _contract_text(
            _first_contract_value(
                branch_payload.get('obligation_id'),
                gap_payload.get('obligation_id'),
                f'obligation-{phase_id}' if phase_id else None,
                f'obligation-{branch_id}' if branch_id else None,
            )
        )
        output_type = _contract_text(
            _first_contract_value(
                branch_payload.get('output_type'),
                gap_payload.get('output_type'),
                self.artifact_type_for_capability(normalized_capability),
            )
        ).lower()
        depends_on = [
            _contract_text(item)
            for item in _clean_contract_value(
                _first_contract_value(
                    branch_payload.get('depends_on'),
                    gap_payload.get('depends_on'),
                )
                or []
            )
            if _contract_text(item)
        ]
        input_refs = _clean_contract_value(
            _first_contract_value(
                branch_payload.get('input_refs'),
                gap_payload.get('input_refs'),
            )
            or []
        )
        if not input_refs and depends_on:
            input_refs = [
                {
                    'kind': 'phase_output',
                    'phase_id': dependency_id,
                    'role': 'dependency',
                }
                for dependency_id in depends_on
            ]

        raw_output_contract = _first_contract_value(
            branch_payload.get('output_contract'),
            gap_payload.get('output_contract'),
        )
        output_contract = (
            _clean_contract_value(raw_output_contract)
            if isinstance(raw_output_contract, Mapping)
            else {}
        )
        if output_type:
            output_contract.setdefault('output_type', output_type)
        required_value = _first_contract_value(branch_payload.get('required'), gap_payload.get('required'))
        if required_value not in (None, '', [], {}):
            output_contract.setdefault('required', required_value)
        elif output_type:
            output_contract.setdefault('required', True)
        requires_artifact = _first_contract_value(
            branch_payload.get('requires_artifact'),
            gap_payload.get('requires_artifact'),
        )
        if requires_artifact not in (None, '', [], {}):
            output_contract.setdefault('requires_artifact', requires_artifact)
        if output_contract and 'fulfillment_policy' not in output_contract:
            output_contract['fulfillment_policy'] = (
                'materialized_artifact_required'
                if bool(requires_artifact)
                else 'capability_output_required'
            )

        contract: dict[str, Any] = {
            'kind': 'fruth.execution_contract',
            'branch_id': branch_id or None,
            'phase_id': phase_id or None,
            'capability': normalized_capability or None,
            'output_type': output_type or None,
            'workload_task_ref': {
                'task_id': task_id or None,
                'phase_id': phase_id or None,
                'branch_id': branch_id or None,
            },
            'output_obligation_ref': {
                'obligation_id': obligation_id or None,
                'phase_id': phase_id or None,
                'branch_id': branch_id or None,
                'output_type': output_type or None,
            },
            'output_contract': output_contract,
            'depends_on': depends_on,
            'input_refs': input_refs,
        }
        for key in (
            'queue_index',
            'source',
            'role',
            'stage_direction',
            'dependency_contract',
            'content_payload_source',
            'artifact_prompt_source',
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
            'candidate_extraction_issue',
            'audio_variant_contract_conflicting_fields',
            'candidate_id',
            'contract_state',
            'contract_status',
            'obligation_state',
            'promotion_policy',
            'promotion_reason',
            'promotion_source',
            'promoted_from_candidate_id',
            'requires_artifact',
            'text_artifact_extension',
            'text_artifact_source_name',
            'text_artifact_source',
            'text_artifact_target_path',
            'artifact_request',
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
        ):
            value = _first_contract_value(branch_payload.get(key), gap_payload.get(key))
            if value not in (None, '', [], {}):
                contract[key] = _clean_contract_value(value)

        if gap_payload.get('saved_file_read_evidence'):
            contract['saved_file_read_evidence'] = copy.deepcopy(gap_payload['saved_file_read_evidence'])
            contract['input_refs'] = copy.deepcopy(gap_payload.get('input_refs') or [])
        if (contract.get('artifact_request') or {}).get('saved_file_syntax_repair'):
            for key in ('repair_scope', 'dependency_policy', 'recovery_attempt', 'recovery_state'):
                contract[key] = copy.deepcopy(_first_contract_value(branch_payload.get(key), gap_payload.get(key)))
        existing_contract = gap_payload.get('execution_contract')
        if isinstance(existing_contract, Mapping):
            for key, value in _clean_contract_value(existing_contract).items():
                if contract.get(key) in (None, '', [], {}):
                    contract[key] = value
        return _clean_contract_value(contract)

    def attach_execution_contract_to_gap(
        self,
        branch: Mapping[str, Any],
        artifact_gap: dict[str, Any],
        *,
        capability: Optional[str] = None,
    ) -> dict[str, Any]:
        updated = dict(artifact_gap or {})
        contract = self.build_execution_contract(branch, updated, capability=capability)
        if not contract:
            return updated
        updated['execution_contract'] = contract
        workload_task_ref = contract.get('workload_task_ref') if isinstance(contract.get('workload_task_ref'), Mapping) else {}
        output_obligation_ref = (
            contract.get('output_obligation_ref')
            if isinstance(contract.get('output_obligation_ref'), Mapping)
            else {}
        )
        for key in ('branch_id', 'phase_id', 'capability', 'output_type'):
            value = contract.get(key)
            if value not in (None, '', [], {}) and updated.get(key) in (None, '', [], {}):
                updated[key] = value
        task_id = workload_task_ref.get('task_id') if isinstance(workload_task_ref, Mapping) else None
        if task_id not in (None, '', [], {}) and updated.get('task_id') in (None, '', [], {}):
            updated['task_id'] = task_id
            updated['workload_task_id'] = task_id
        obligation_id = (
            output_obligation_ref.get('obligation_id')
            if isinstance(output_obligation_ref, Mapping)
            else None
        )
        if obligation_id not in (None, '', [], {}) and updated.get('obligation_id') in (None, '', [], {}):
            updated['obligation_id'] = obligation_id
        if workload_task_ref:
            updated.setdefault('workload_task_ref', dict(workload_task_ref))
        if output_obligation_ref:
            updated.setdefault('output_obligation_ref', dict(output_obligation_ref))
        return updated

    def normalize_late_fill_error_payload(
        self,
        error: Any,
        *,
        default_stage: str = 'execute_prepared_branch',
    ) -> dict[str, Any]:
        raw = error if isinstance(error, Mapping) else {}
        message = str(raw.get('message') if raw else error or '').strip()
        if not message:
            message = 'Late fill request failed.'
        stage = str(raw.get('stage') or default_stage or '').strip() or default_stage
        code = str(raw.get('code') or '').strip().upper()
        if not code:
            lowered = message.lower()
            if (
                stage == 'prepare_branch_plan'
                and lowered.startswith('no ready late-fill instance for capability ')
            ):
                code = 'INSTANCE_UNAVAILABLE'
            elif 'timeout' in lowered or 'timed out' in lowered:
                code = 'BACKEND_TIMEOUT'
            elif any(token in lowered for token in ('unavailable', 'connection refused', 'offline')):
                code = 'INSTANCE_UNAVAILABLE'
            else:
                code = 'BACKEND_ERROR' if stage == 'execute_prepared_branch' else 'PREPARE_FAILED'
        payload: dict[str, Any] = {
            'code': code,
            'message': message,
            'stage': stage,
        }
        retryable = raw.get('retryable') if raw else None
        if isinstance(retryable, bool):
            payload['retryable'] = retryable
        else:
            payload['retryable'] = code not in {'CAPABILITY_UNSUPPORTED', 'CONTROL_VALIDATION_FAILED', 'PREPARE_FAILED'}
        status_code = raw.get('status_code') if raw else None
        if status_code is None and raw:
            status_code = raw.get('statusCode')
        if status_code not in (None, ''):
            try:
                payload['status_code'] = int(status_code)
            except (TypeError, ValueError):
                pass
        exception_type = str(raw.get('exception_type') or raw.get('exceptionType') or '').strip() if raw else ''
        if exception_type:
            payload['exception_type'] = exception_type
        for key in (
            'pdf_preparation', 'pdf_source', 'pdf_total_pages', 'pdf_processed_pages', 'warnings',
            'route_diagnostics',
            'reason_code',
            'defect_code',
            'defect_codes',
            'repair_action',
            'recovery_action',
            'suggested_action',
            'materialization_blocked',
            'blocked_scope',
            'blocked_prerequisite',
            'repair_work_available',
            'repair_work_policy',
            'needs_external_input',
            'failed_dependency_ids',
            'semantic_evidence',
            'vision_evidence_failure',
            'vision_backend_failure',
            'audio_integrity_evidence',
            'tts_generation_budget',
            'tts_sampling_profile',
            'diagnostic_artifact',
            'external_execution',
            'coalesced_text_artifact_recovery',
            'saved_text_path',
            'text_artifact_target_path',
            'text_artifact_extension',
            'text_artifact_source_name',
            'syntax_sanity_status',
            'syntax_sanity_issue_count',
            'syntax_sanity_issues',
            'saved_file_syntax_failure',
        ):
            value = raw.get(key) if raw else None
            if value not in (None, '', [], {}):
                payload[key] = value
        return payload

    def late_fill_failure_attempt(
        self,
        branch: Mapping[str, Any],
        error: Mapping[str, Any],
        plan: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        plan_payload = plan if isinstance(plan, Mapping) else {}
        route_info = plan_payload.get('route_info') if isinstance(plan_payload.get('route_info'), Mapping) else {}
        instance = plan_payload.get('instance') if isinstance(plan_payload.get('instance'), Mapping) else {}
        capability = self.branch_capability(branch) or self.normalize_capability(plan_payload.get('capability'))
        payload: dict[str, Any] = {
            'stage': str(error.get('stage') or '').strip() or 'execute_prepared_branch',
            'capability': capability,
        }
        instance_id = str(
            route_info.get('instance_id')
            or instance.get('instance_id')
            or ''
        ).strip()
        if instance_id:
            payload['instance_id'] = instance_id
        backend = str(instance.get('backend') or route_info.get('backend') or '').strip()
        if backend:
            payload['backend'] = backend
        model = str(instance.get('model') or route_info.get('model') or '').strip()
        if model:
            payload['model'] = model
        for source_key, target_key in (
            ('route_source', 'route_source'),
            ('route_reason', 'route_reason'),
        ):
            value = str(route_info.get(source_key) or '').strip()
            if value:
                payload[target_key] = value
        route_runtime = (
            route_info.get('route_runtime')
            if isinstance(route_info.get('route_runtime'), Mapping)
            else {}
        )
        selection_policy = str(
            route_runtime.get('selection_policy') or ''
        ).strip()
        if selection_policy:
            payload['selection_policy'] = selection_policy
        return {
            key: value
            for key, value in payload.items()
            if value not in (None, '', [], {})
        }

    def late_fill_recovery_context(
        self,
        *,
        error: Mapping[str, Any],
        attempt: Mapping[str, Any],
    ) -> dict[str, Any]:
        retryable = bool(error.get('retryable'))
        instance_id = str(attempt.get('instance_id') or '').strip()
        code = str(error.get('code') or '').strip().upper()
        message = str(error.get('message') or '').strip()
        availability_recheck_required = bool(
            code == 'INSTANCE_UNAVAILABLE'
            and str(error.get('stage') or attempt.get('stage') or '').strip()
            == 'prepare_branch_plan'
        )
        explicit_action = normalize_recovery_suggested_action(
            error.get('repair_action') or error.get('recovery_action') or error.get('suggested_action'),
            default='',
        )
        dependency_input_missing = bool(
            code == 'DEPENDENCY_CHAIN_REPAIR_REQUIRED'
            or _DEPENDENCY_INPUT_MISSING_RE.search(message)
        )
        owned_retryable_text_repair_failure = bool(
            code == 'TEXT_ARTIFACT_REPAIR_OUTPUT_MISSING'
            and retryable
            and explicit_action
            in {
                RECOVERY_ACTION_RETRY_SAME_BRANCH,
                RECOVERY_ACTION_RETRY_EXCLUDING_INSTANCE,
            }
        )
        branch_contract_repair = bool(
            code in {'BRANCH_CONTRACT_REPAIR_REQUIRED', 'CONTROL_VALIDATION_FAILED', 'PREPARE_FAILED'}
            or (
                not owned_retryable_text_repair_failure
                and not availability_recheck_required
                and _BRANCH_CONTRACT_REPAIR_RE.search(message)
            )
        )
        rebuild_promoted_obligations = bool(
            code == 'REBUILD_FROM_PROMOTED_OBLIGATIONS_REQUIRED'
            or 'promoted obligation' in message.lower()
            or 'rebuild_from_promoted_obligations' in message.lower()
        )
        saved_text_syntax_failure = bool(
            code == 'TEXT_ARTIFACT_SYNTAX_SANITY_FAILED'
            and error.get('saved_file_syntax_failure') is True
            and str(error.get('saved_text_path') or '').strip()
        )
        if rebuild_promoted_obligations:
            suggested_action = RECOVERY_ACTION_REBUILD_FROM_PROMOTED_OBLIGATIONS
        elif branch_contract_repair:
            suggested_action = RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT
        elif dependency_input_missing and explicit_action == RECOVERY_ACTION_REBIND_DEPENDENCY_EVIDENCE:
            suggested_action = RECOVERY_ACTION_REBIND_DEPENDENCY_EVIDENCE
        elif dependency_input_missing:
            suggested_action = RECOVERY_ACTION_REPAIR_DEPENDENCY_CHAIN
        elif saved_text_syntax_failure:
            suggested_action = RECOVERY_ACTION_RETRY_SAME_BRANCH
        elif not retryable:
            suggested_action = RECOVERY_ACTION_MANUAL_REVIEW
        elif code == 'NO_COMPATIBLE_INSTANCE':
            suggested_action = RECOVERY_ACTION_START_COMPATIBLE_INSTANCE
        elif availability_recheck_required:
            suggested_action = RECOVERY_ACTION_RETRY_SAME_BRANCH
        elif instance_id:
            suggested_action = RECOVERY_ACTION_RETRY_EXCLUDING_INSTANCE
        else:
            suggested_action = RECOVERY_ACTION_RETRY_SAME_BRANCH
        payload: dict[str, Any] = {
            'can_retry': retryable
            and not dependency_input_missing
            and not branch_contract_repair
            and not rebuild_promoted_obligations,
            'retry_scope': (
                'promoted_obligations'
                if rebuild_promoted_obligations
                else
                'branch_contract'
                if branch_contract_repair
                else 'dependency_chain'
                if dependency_input_missing
                else 'same_branch'
            ),
            'suggested_action': suggested_action,
            'preserve_intent': True,
            'error_code': code,
        }
        reason_code = str(error.get('reason_code') or '').strip()
        if availability_recheck_required:
            payload['availability_recheck_required'] = True
        if reason_code:
            payload['reason_code'] = reason_code
        defect_codes = [
            str(item).strip()
            for item in (error.get('defect_codes') or [])
            if str(item).strip()
        ] if isinstance(error.get('defect_codes'), list) else []
        if defect_codes:
            payload['defect_codes'] = defect_codes
        audio_integrity_evidence = (
            error.get('audio_integrity_evidence')
            if isinstance(error.get('audio_integrity_evidence'), Mapping)
            else {}
        )
        if audio_integrity_evidence:
            payload['audio_integrity_evidence'] = dict(
                audio_integrity_evidence
            )
        if isinstance(error.get('vision_evidence_failure'), Mapping):
            payload['vision_evidence_failure'] = copy.deepcopy(error['vision_evidence_failure'])
        if isinstance(error.get('vision_backend_failure'), Mapping):
            payload['vision_backend_failure'] = copy.deepcopy(error['vision_backend_failure'])
        if branch_contract_repair:
            payload['repair_required'] = True
            payload['blocked_by_branch_contract'] = True
        if rebuild_promoted_obligations:
            payload['repair_required'] = True
            payload['blocked_by_underplanned_promoted_obligations'] = True
        if dependency_input_missing:
            payload['repair_required'] = True
            payload['blocked_by_dependency_input'] = True
        if saved_text_syntax_failure:
            payload['repair_required'] = True
            payload['target_bound_syntax_repair'] = True
            for key in (
                'saved_text_path',
                'text_artifact_target_path',
                'text_artifact_extension',
                'text_artifact_source_name',
                'syntax_sanity_status',
                'syntax_sanity_issue_count',
                'syntax_sanity_issues',
                'saved_file_syntax_failure',
            ):
                value = error.get(key)
                if value not in (None, '', [], {}):
                    payload[key] = copy.deepcopy(value)
        for key in (
            'materialization_blocked',
            'blocked_scope',
            'blocked_prerequisite',
            'repair_work_available',
            'repair_work_policy',
            'needs_external_input',
        ):
            value = error.get(key)
            if value not in (None, '', [], {}):
                payload[key] = value
        if instance_id and retryable and not availability_recheck_required:
            payload['exclude_instance_ids'] = [instance_id]
        return payload

    def late_fill_recovery_state(
        self,
        branch: Mapping[str, Any],
        *,
        recovery_context: Mapping[str, Any],
        attempt: Optional[Mapping[str, Any]] = None,
        status: str = 'candidate',
        trigger: str = 'late_fill_failure',
    ) -> dict[str, Any]:
        branch_id = self.branch_id(branch)
        capability = self.branch_capability(branch)
        attempt_payload = attempt if isinstance(attempt, Mapping) else {}
        state_status = str(status or '').strip().lower() or 'candidate'
        auto_execute_recovery = self.auto_executable_repair_recovery_allowed(
            branch,
            recovery_context=recovery_context,
        )
        payload: dict[str, Any] = {
            'kind': 'fruth.late_fill_recovery_state',
            'status': state_status,
            'trigger': str(trigger or '').strip() or 'late_fill_failure',
            'branch_id': branch_id,
            'capability': capability,
            'promotion_required': state_status == 'candidate' and not auto_execute_recovery,
            'auto_execute': auto_execute_recovery,
            'preserve_intent': recovery_context.get('preserve_intent')
            if isinstance(recovery_context.get('preserve_intent'), bool)
            else True,
        }
        for key in ('retry_scope', 'suggested_action'):
            value = str(recovery_context.get(key) or '').strip()
            if value:
                payload[key] = value
        for key in (
            'repair_required',
            'availability_recheck_required',
            'blocked_by_dependency_input',
            'blocked_by_branch_contract',
            'blocked_by_underplanned_promoted_obligations',
            'materialization_blocked',
            'repair_work_available',
            'needs_external_input',
        ):
            value = recovery_context.get(key)
            if isinstance(value, bool):
                payload[key] = value
        for key in ('blocked_scope', 'blocked_prerequisite', 'repair_work_policy'):
            value = str(recovery_context.get(key) or '').strip()
            if value:
                payload[key] = value
        instance_id = str(attempt_payload.get('instance_id') or '').strip()
        if instance_id and not recovery_context.get('availability_recheck_required'):
            payload['failed_instance_id'] = instance_id
        exclude_instance_ids = [
            str(item).strip()
            for item in (recovery_context.get('exclude_instance_ids') or [])
            if str(item).strip()
        ] if isinstance(recovery_context.get('exclude_instance_ids'), list) else []
        if exclude_instance_ids:
            payload['exclude_instance_ids'] = exclude_instance_ids
        return {
            key: value
            for key, value in payload.items()
            if value not in (None, '', [], {})
        }

    @staticmethod
    def _repair_bool_from_branch_or_contract(
        branch: Mapping[str, Any],
        key: str,
    ) -> Optional[bool]:
        value = branch.get(key)
        if isinstance(value, bool):
            return value
        contract = branch.get('repair_contract') if isinstance(branch.get('repair_contract'), Mapping) else {}
        value = contract.get(key)
        if isinstance(value, bool):
            return value
        return None

    @staticmethod
    def _repair_text_from_branch_or_contract(branch: Mapping[str, Any], key: str) -> str:
        value = str(branch.get(key) or '').strip()
        if value:
            return value
        contract = branch.get('repair_contract') if isinstance(branch.get('repair_contract'), Mapping) else {}
        return str(contract.get(key) or '').strip()

    def auto_executable_repair_max_attempts(self, branch: Mapping[str, Any]) -> int:
        contract = branch.get('repair_contract') if isinstance(branch.get('repair_contract'), Mapping) else {}
        attempt_limit = (
            _TTS_AUTO_RECOVERY_MAX_ATTEMPTS
            if self._branch_is_required_tts_materialization(branch)
            else _VISION_EVIDENCE_RECOVERY_MAX_ATTEMPTS
            if self.branch_capability(branch) == 'vision_analysis'
            else _AUTO_EXECUTABLE_REPAIR_MAX_ATTEMPTS_LIMIT
        )
        for key in (
            'auto_executable_repair_max_attempts',
            'repair_auto_execute_max_attempts',
            'max_auto_execute_attempts',
        ):
            for source in (branch, contract):
                try:
                    value = int(source.get(key))
                except (AttributeError, TypeError, ValueError):
                    continue
                if value > 0:
                    return min(value, attempt_limit)
        try:
            env_value = int(os.environ.get(_AUTO_EXECUTABLE_REPAIR_MAX_ATTEMPTS_ENV, ''))
        except (TypeError, ValueError):
            env_value = 0
        if env_value > 0:
            return min(env_value, attempt_limit)
        return (
            _TTS_AUTO_RECOVERY_MAX_ATTEMPTS
            if self._branch_is_required_tts_materialization(branch)
            else _VISION_EVIDENCE_RECOVERY_MAX_ATTEMPTS
            if self.branch_capability(branch) == 'vision_analysis'
            else _AUTO_EXECUTABLE_REPAIR_DEFAULT_MAX_ATTEMPTS
        )

    @staticmethod
    def _branch_has_target_bound_saved_text_syntax_repair_attempt(
        branch: Mapping[str, Any],
    ) -> bool:
        if not isinstance(branch, Mapping):
            return False
        for key in ('recovery_attempt', 'recovery_state'):
            recovery = branch.get(key) if isinstance(branch.get(key), Mapping) else {}
            if str(recovery.get('trigger') or '').strip() == (
                _TARGET_BOUND_SAVED_TEXT_SYNTAX_REPAIR_TRIGGER
            ):
                return True
        return False

    _target_bound_saved_text_syntax_repair_evidence = staticmethod(TextArtifactFiles._target_bound_saved_text_syntax_repair_evidence)

    @staticmethod
    def _late_fill_availability_poll_seconds() -> float:
        try:
            value = float(os.environ.get('FRUTH_LATE_FILL_AVAILABILITY_POLL_SEC', '5'))
        except (TypeError, ValueError):
            value = 5.0
        return max(1.0, min(value, 60.0))

    @classmethod
    def build_availability_wait_branch(
        cls, branch: Mapping[str, Any], *, error: Mapping[str, Any],
    ) -> Optional[dict[str, Any]]:
        diagnostics = error.get('route_diagnostics')
        evidence = diagnostics.get('availability_wait') if isinstance(diagnostics, Mapping) else None
        if (
            error.get('code') != 'INSTANCE_UNAVAILABLE'
            or error.get('stage') != 'prepare_branch_plan'
            or not isinstance(evidence, Mapping)
            or evidence.get('reason') != 'live_candidates_in_cooldown'
            or not evidence.get('candidate_instance_ids')
            or branch.get('automatic_follow_up_allowed') is False
            or BranchDependencyEvidence._content_review_binding(branch)
            or (branch.get('recovery_attempt') or {}).get('recovery_policy_id')
            == _VISION_EVIDENCE_RECOVERY_POLICY_ID
        ):
            return None
        now = time.time()
        previous = branch.get('availability_wait')
        previous = previous if isinstance(previous, Mapping) else {}
        waiting = dict(branch)
        for key in ('error', 'attempt', 'recovery_context', 'recovery_state'):
            waiting.pop(key, None)
        waiting['status'] = 'pending'
        waiting['availability_wait'] = {
            **dict(evidence),
            'status': 'waiting',
            'started_at_epoch': previous.get('started_at_epoch', now),
            'next_check_epoch': now + cls._late_fill_availability_poll_seconds(),
            'check_count': int(previous.get('check_count') or 0) + 1,
        }
        wait_causal = LateFillTrace.availability_wait_started(
            branch, waiting['availability_wait'], previous, evidence,
        )
        if wait_causal:
            waiting['availability_wait']['causal'] = wait_causal
        return waiting

    @staticmethod
    def availability_wait_delay(branch: Mapping[str, Any]) -> float:
        return LateFillSelection.availability_wait_delay(branch, clock=time.time)

    def auto_executable_repair_recovery_allowed(
        self,
        branch: Mapping[str, Any],
        *,
        recovery_context: Mapping[str, Any],
    ) -> bool:
        if not isinstance(branch, Mapping) or not isinstance(recovery_context, Mapping):
            return False
        if recovery_context.get('availability_recheck_required') is True:
            # The pending availability-wait path owns temporary pool waits;
            # they must never consume bounded materialization retry attempts.
            return False
        if self._branch_is_explicit_image_excluded_pool_retry(branch):
            # This policy authorizes exactly one user-triggered wave. A failed
            # attempt returns to explicit user control instead of entering the
            # ordinary required-image auto-repair loop.
            return False
        required_text_artifact = self.branch_selection._branch_is_required_text_artifact(branch)
        required_image_materialization = self.branch_selection._branch_is_required_image_materialization(branch)
        required_tts_recovery = (
            self._required_tts_auto_recovery_allowed(
                branch,
                recovery_context,
            )
        )
        required_vision_recovery = self._vision_evidence_recovery_allowed(branch, recovery_context)
        if (
            not required_text_artifact
            and not required_image_materialization
            and not required_tts_recovery
            and not required_vision_recovery
        ):
            return False
        syntax_failure = str(
            recovery_context.get('error_code') or ''
        ).strip().upper() == 'TEXT_ARTIFACT_SYNTAX_SANITY_FAILED'
        target_bound_syntax_evidence = (
            TextArtifactFiles._target_bound_saved_text_syntax_repair_evidence(
                recovery_context
            )
            if syntax_failure
            else {}
        )
        if syntax_failure and self._branch_has_target_bound_saved_text_syntax_repair_attempt(
            branch
        ):
            return False
        if (
            syntax_failure
            and recovery_context.get('target_bound_syntax_repair') is True
            and not target_bound_syntax_evidence
        ):
            return False
        if target_bound_syntax_evidence and not required_text_artifact:
            return False
        try:
            retry_count = int(branch.get('auto_executable_repair_retry_count') or 0)
        except (TypeError, ValueError):
            retry_count = 0
        max_attempts = self.auto_executable_repair_max_attempts(branch)
        max_retries = max(0, max_attempts - 1)
        if not target_bound_syntax_evidence and retry_count >= max_retries:
            return False
        execution_policy = (
            self._repair_text_from_branch_or_contract(branch, 'repair_execution_policy')
            or self._repair_text_from_branch_or_contract(branch, 'execution_policy')
        )
        auto_requested = (
            self._repair_bool_from_branch_or_contract(branch, 'auto_execute') is True
            or execution_policy == 'schedule_late_fill_branch'
        )
        if required_text_artifact:
            auto_requested = True
        if required_image_materialization and not required_text_artifact:
            auto_requested = True
        if required_tts_recovery:
            auto_requested = True
        if required_vision_recovery:
            auto_requested = True
        if not auto_requested:
            return False
        if self._repair_bool_from_branch_or_contract(branch, 'repair_work_available') is False:
            return False
        for source in (branch, recovery_context):
            if source.get('needs_external_input') is True:
                return False
            if (
                source.get('materialization_blocked') is True
                and not required_tts_recovery
                and not required_vision_recovery
            ):
                return False
        action = normalize_recovery_suggested_action(
            recovery_context.get('suggested_action') or branch.get('recovery_action') or branch.get('repair_action'),
            default='',
        )
        if action not in _AUTO_EXECUTABLE_REPAIR_RETRY_ACTIONS and not (
            required_tts_recovery
            and action == RECOVERY_ACTION_START_COMPATIBLE_INSTANCE
        ):
            return False
        retry_scope = str(recovery_context.get('retry_scope') or '').strip()
        return recovery_context.get('can_retry') is True and retry_scope in {'', 'same_branch'}

    def build_auto_executable_repair_retry_branch(
        self,
        branch: Mapping[str, Any],
        *,
        recovery_context: Mapping[str, Any],
        recovery_state: Mapping[str, Any],
        attempt: Mapping[str, Any],
        trigger: str,
    ) -> Optional[dict[str, Any]]:
        if not self.auto_executable_repair_recovery_allowed(
            branch,
            recovery_context=recovery_context,
        ):
            return None
        branch_id = self.branch_id(branch)
        capability = self.branch_capability(branch)
        if not branch_id or not capability:
            return None
        try:
            retry_count = int(branch.get('auto_executable_repair_retry_count') or 0)
        except (TypeError, ValueError):
            retry_count = 0
        target_bound_syntax_evidence = (
            TextArtifactFiles._target_bound_saved_text_syntax_repair_evidence(
                recovery_context
            )
        )
        tts_auto_recovery = (
            self._required_tts_auto_recovery_allowed(
                branch,
                recovery_context,
            )
        )
        vision_auto_recovery = self._vision_evidence_recovery_allowed(branch, recovery_context)
        resolved_trigger = (
            _VISION_BACKEND_RECOVERY_TRIGGER
            if vision_auto_recovery and recovery_context.get('vision_backend_failure')
            else
            _VISION_EVIDENCE_RECOVERY_TRIGGER
            if vision_auto_recovery
            else _TTS_AUTO_RECOVERY_TRIGGER
            if tts_auto_recovery
            else _TARGET_BOUND_SAVED_TEXT_SYNTAX_REPAIR_TRIGGER
            if target_bound_syntax_evidence
            else str(trigger or '').strip() or 'auto_executable_repair_retry'
        )
        max_attempts = self.auto_executable_repair_max_attempts(branch)
        retry_max_attempts = (
            min(max_attempts, retry_count + 2)
            if target_bound_syntax_evidence
            else max_attempts
        )
        retry_branch = {
            key: value
            for key, value in dict(branch).items()
            if key not in {'error', 'attempt', 'recovery_context', 'recovery_state', 'recovery_attempt'}
        }
        excluded_instance_ids: list[str] = []
        for values in (
            branch.get('excluded_instance_ids'),
            recovery_context.get('exclude_instance_ids'),
            recovery_state.get('exclude_instance_ids'),
        ):
            if not isinstance(values, list):
                continue
            for item in values:
                token = str(item or '').strip()
                if token and token not in excluded_instance_ids:
                    excluded_instance_ids.append(token)
        failed_instance_id = str(
            attempt.get('instance_id')
            or recovery_state.get('failed_instance_id')
            or branch.get('failed_instance_id')
            or ''
        ).strip()
        if failed_instance_id and failed_instance_id not in excluded_instance_ids:
            excluded_instance_ids.append(failed_instance_id)
        action = normalize_recovery_suggested_action(
            recovery_context.get('suggested_action') or recovery_state.get('suggested_action'),
            default=RECOVERY_ACTION_RETRY_SAME_BRANCH,
        )
        if target_bound_syntax_evidence:
            action = RECOVERY_ACTION_RETRY_SAME_BRANCH
        retry_recovery_state = dict(recovery_state)
        retry_recovery_state.update(
            {
                'kind': 'fruth.late_fill_recovery_state',
                'status': 'attempting',
                'trigger': resolved_trigger,
                'branch_id': branch_id,
                'capability': capability,
                'promotion_required': False,
                'auto_execute': True,
                'preserve_intent': True,
                'retry_scope': 'same_branch',
                'suggested_action': action,
            }
        )
        if failed_instance_id:
            retry_recovery_state['failed_instance_id'] = failed_instance_id
        if excluded_instance_ids:
            retry_recovery_state['exclude_instance_ids'] = excluded_instance_ids
        recovery_attempt = {
            'kind': 'fruth.late_fill_recovery_attempt',
            'trigger': resolved_trigger,
            'branch_id': branch_id,
            'capability': capability,
            'preserve_intent': True,
            'auto_execute': True,
            'failed_instance_id': failed_instance_id or None,
            'excluded_instance_ids': excluded_instance_ids,
        }
        if tts_auto_recovery:
            prior_error_code = str(
                recovery_context.get('error_code') or ''
            ).strip().upper()
            prior_reason_code = str(
                recovery_context.get('reason_code') or ''
            ).strip()
            prior_defect_codes = [
                str(item).strip()
                for item in (recovery_context.get('defect_codes') or [])
                if str(item).strip()
            ] if isinstance(recovery_context.get('defect_codes'), list) else []
            prior_integrity = (
                recovery_context.get('audio_integrity_evidence')
                if isinstance(
                    recovery_context.get('audio_integrity_evidence'),
                    Mapping,
                )
                else {}
            )
            retry_recovery_state.update(
                {
                    'recovery_policy_id': (
                        _TTS_AUTO_RECOVERY_POLICY_ID
                    ),
                    'attempt_number': retry_count + 2,
                    'maximum_attempts': max_attempts,
                    'prior_error_code': prior_error_code,
                    'prior_reason_code': prior_reason_code or None,
                    'prior_defect_codes': prior_defect_codes,
                }
            )
            recovery_attempt.update(
                {
                    'recovery_policy_id': (
                        _TTS_AUTO_RECOVERY_POLICY_ID
                    ),
                    'attempt_number': retry_count + 2,
                    'maximum_attempts': max_attempts,
                    'prior_error_code': prior_error_code,
                    'prior_reason_code': prior_reason_code or None,
                    'prior_defect_codes': prior_defect_codes,
                    'prior_audio_integrity_evidence': (
                        dict(prior_integrity) if prior_integrity else None
                    ),
                }
            )
        elif vision_auto_recovery:
            backend_failure = recovery_context.get('vision_backend_failure')
            policy = _VISION_BACKEND_RECOVERY_POLICY_ID if backend_failure else _VISION_EVIDENCE_RECOVERY_POLICY_ID
            retry_recovery_state.update({
                'recovery_policy_id': policy,
                'attempt_number': retry_count + 2,
                'maximum_attempts': max_attempts,
            })
            recovery_attempt.update({
                'recovery_policy_id': policy,
                'attempt_number': retry_count + 2,
                'maximum_attempts': max_attempts,
                'prior_error_code': recovery_context['error_code'],
                ('prior_vision_backend_failure' if backend_failure else 'prior_vision_evidence_failure'):
                    copy.deepcopy(backend_failure or recovery_context['vision_evidence_failure']),
            })
        elif target_bound_syntax_evidence:
            recovery_attempt.update(
                {
                    'attempt_number': 1,
                    'maximum_attempts': 1,
                    'prior_error_code': (
                        'TEXT_ARTIFACT_SYNTAX_SANITY_FAILED'
                    ),
                }
            )
        retry_branch.update(
            {
                'status': 'pending',
                'auto_execute': True,
                'repair_work_available': True,
                'needs_external_input': False,
                'repair_action': action,
                'recovery_action': action,
                'suggested_action': action,
                'auto_executable_repair_retry_count': retry_count + 1,
                'auto_executable_repair_max_attempts': retry_max_attempts,
                'recovery_context': dict(recovery_context),
                'recovery_state': {
                    key: value
                    for key, value in retry_recovery_state.items()
                    if value not in (None, '', [], {})
                },
                'recovery_attempt': {
                    key: value
                    for key, value in recovery_attempt.items()
                    if value not in (None, '', [], {})
                },
            }
        )
        if failed_instance_id:
            retry_branch['failed_instance_id'] = failed_instance_id
        if excluded_instance_ids:
            retry_branch['excluded_instance_ids'] = excluded_instance_ids
        if tts_auto_recovery:
            retry_branch['recovery_policy_id'] = (
                _TTS_AUTO_RECOVERY_POLICY_ID
            )
        if vision_auto_recovery:
            retry_branch['recovery_policy_id'] = _VISION_EVIDENCE_RECOVERY_POLICY_ID
        if target_bound_syntax_evidence:
            target_path = str(
                target_bound_syntax_evidence.get('target_path') or ''
            ).strip()
            extension = str(
                target_bound_syntax_evidence.get('extension') or ''
            ).strip()
            source_name = str(
                target_bound_syntax_evidence.get('source_name') or ''
            ).strip()
            original_request = copy.deepcopy(branch.get('artifact_request') or {})
            saved_contract = saved_file_dependency_contract(branch)
            if saved_contract:
                try:
                    target_snapshot = read_saved_file_snapshot(target_path, self.resolve_saved_file_input_path)
                    info = Path(target_path).stat()
                    repair = {
                        'kind': 'fruth.saved_file_syntax_repair', 'version': 1,
                        'consumer_branch_id': branch_id, 'consumer_phase_id': branch.get('phase_id'),
                        'consumer_request': copy.deepcopy(saved_contract['consumer_request']),
                        'target_request': {**saved_contract['consumer_request'], 'target_path': target_path},
                        'target': target_snapshot,
                        'file_identity': [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns],
                        'syntax_sanity_issues': list(target_bound_syntax_evidence['current_syntax_sanity_issues']),
                    }
                    issue = saved_file_syntax_repair_issue(saved_contract, repair)
                    if issue:
                        return None
                    source_name = saved_contract['consumer_request']['source_name']
                    original_request['saved_file_syntax_repair'] = repair
                except (OSError, ValueError, KeyError, TypeError, UnicodeError):
                    return None
            for key in (
                'artifact_prompt',
                'artifact_prompt_source',
                'batch_prompts',
                'batch_prompts_source',
                'phase_summary',
            ):
                retry_branch.pop(key, None)
            retry_branch.update(
                {
                    'check_kind': 'text_artifact_syntax_sanity',
                    'role': 'text_artifact_syntax_repair',
                    'repair_scope': 'syntax_only',
                    'resource_class': 'text_io',
                    'dependency_policy': 'target_artifact_snapshot_only',
                    'runtime_scheduling_context': {
                        'repair_scope': 'syntax_only',
                        'resource_class': 'text_io',
                        'dependency_policy': (
                            'target_artifact_snapshot_only'
                        ),
                    },
                    'content_payload': target_bound_syntax_evidence[
                        'content_payload'
                    ],
                    'content_payload_source': (
                        'closure_text_artifact_syntax_sanity'
                    ),
                    'stage_direction': (
                        'materialize_requested_text_artifact'
                    ),
                    'requires_artifact': True,
                    'text_artifact_extension': extension,
                    'text_artifact_source_name': source_name,
                    'text_artifact_source': 'closure_syntax_repair',
                    'text_artifact_target_path': target_path,
                    'artifact_request': {
                        **original_request,
                        'extension': extension,
                        'source_name': source_name,
                        'source': 'closure_syntax_repair',
                        'target_path': target_path,
                    },
                    'review_criteria': list(dict.fromkeys([*(branch.get('review_criteria') or []),
                        'html_css_syntax_sanity',
                        'preserve_runtime_artifact_links',
                    ])),
                }
            )
        return retry_branch

    def late_fill_branch_control_records(self, current_payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
        payload = current_payload if isinstance(current_payload, Mapping) else {}
        late_fill = payload.get('late_fill') if isinstance(payload.get('late_fill'), Mapping) else {}
        controls_by_branch_id: dict[str, dict[str, Any]] = {}

        def remember(raw_record: Any, *, source: str) -> None:
            if not isinstance(raw_record, Mapping):
                return
            branch_id = self.branch_id(raw_record)
            if not branch_id:
                return
            status = _normalized_terminal_status(
                raw_record.get('status')
                or raw_record.get('action')
                or raw_record.get('control_action')
                or raw_record.get('execution_gate_status')
            )
            if not status:
                return
            controls_by_branch_id[branch_id] = {
                'branch_id': branch_id,
                'status': status,
                'action': status,
                'source': source,
                'reason': str(
                    raw_record.get('reason')
                    or raw_record.get('cancel_reason')
                    or raw_record.get('waiver_reason')
                    or raw_record.get('supersession_reason')
                    or raw_record.get('execution_gate_reason')
                    or ''
                ).strip() or None,
                'authority': str(raw_record.get('authority') or raw_record.get('cancelled_by') or 'runtime_contract').strip(),
                'created_at': str(raw_record.get('created_at') or raw_record.get('cancelled_at') or '').strip() or None,
            }

        for key, status in (
            ('cancelled_branches', 'cancelled'),
            ('waived_branches', 'waived'),
            ('superseded_branches', 'superseded'),
        ):
            for raw_branch in late_fill.get(key) or []:
                if isinstance(raw_branch, Mapping):
                    record = dict(raw_branch)
                    record.setdefault('status', status)
                    remember(record, source=key)
        for raw_control in late_fill.get('branch_controls') or []:
            remember(raw_control, source='branch_controls')
        return controls_by_branch_id

    def _causal_execution_gate_inputs(self, branch, current_payload):
        # Follow the gate's precedence. A sibling control or a lower-priority
        # cancellation hint cannot change this owner's effective input identity.
        branch = branch if isinstance(branch, Mapping) else {}
        status = _normalized_terminal_status(branch.get('status'))
        selected = {'branch_id': self.branch_id(branch),
                    'phase_id': branch.get('phase_id'),
                    'capability': self.branch_capability(branch), 'status': status}
        if status:
            selected['reason'] = str(branch.get('execution_gate_reason') or '').strip()
            return selected
        control = self.late_fill_branch_control_records(current_payload).get(self.branch_id(branch)) if current_payload is not None else None
        if control:
            selected['control'] = select_fields(control, ('status', 'action', 'reason', 'source', 'authority'))
            status = _normalized_terminal_status(control.get('status') or control.get('action'))
        if not status:
            cancelled = self.parse_bool(branch.get('cancel_requested'), default=False)
            selected['cancel_requested'] = cancelled
            if cancelled:
                selected['cancel_reason'] = str(branch.get('cancel_reason') or '').strip()
        return selected

    @observe_execution_gate
    def semantic_execution_gate_decision(
        self,
        branch: Mapping[str, Any],
        current_payload: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        branch_payload = branch if isinstance(branch, Mapping) else {}
        branch_id = self.branch_id(branch_payload)
        capability = self.branch_capability(branch_payload)
        status = _normalized_terminal_status(branch_payload.get('status'))
        reason = str(branch_payload.get('execution_gate_reason') or '').strip()
        source = 'branch_status'
        control = None
        if not status and current_payload is not None:
            control = self.late_fill_branch_control_records(current_payload).get(branch_id)
            if control:
                status = _normalized_terminal_status(control.get('status') or control.get('action'))
                reason = str(control.get('reason') or '').strip()
                source = str(control.get('source') or 'branch_control').strip() or 'branch_control'
        if not status and self.parse_bool(branch_payload.get('cancel_requested'), default=False):
            status = 'cancelled'
            reason = str(branch_payload.get('cancel_reason') or '').strip()
            source = 'cancel_requested'
        if status in _SEMANTIC_EXECUTION_TERMINAL_STATUSES:
            return {
                'kind': 'fruth.semantic_execution_gate',
                'scope': 'branch',
                'status': status,
                'action': 'skip',
                'branch_id': branch_id or None,
                'phase_id': str(branch_payload.get('phase_id') or branch_id or '').strip() or None,
                'capability': capability or None,
                'authority': str((control or {}).get('authority') or 'runtime_contract').strip() or 'runtime_contract',
                'reason': reason or f'branch marked {status} before execution',
                'source': source,
            }
        return {
            'kind': 'fruth.semantic_execution_gate',
            'scope': 'branch',
            'status': 'allowed',
            'action': 'execute',
            'branch_id': branch_id or None,
            'phase_id': str(branch_payload.get('phase_id') or branch_id or '').strip() or None,
            'capability': capability or None,
            'authority': 'runtime_contract',
            'reason': 'branch remains relevant and executable',
            'source': 'runtime_contract',
        }

    def branch_record_with_execution_gate(
        self,
        branch: Mapping[str, Any],
        decision: Mapping[str, Any],
    ) -> dict[str, Any]:
        branch_payload = dict(branch or {})
        status = _normalized_terminal_status(decision.get('status')) or 'cancelled'
        branch_payload['status'] = status
        branch_payload['execution_gate'] = dict(decision)
        reason = str(decision.get('reason') or '').strip()
        now_iso = self.response_registry_now_iso()
        if status == 'cancelled':
            branch_payload['cancel_requested'] = True
            branch_payload['cancel_reason'] = reason or 'branch cancelled before completion'
            branch_payload['cancelled_by'] = str(decision.get('authority') or 'runtime_contract').strip() or 'runtime_contract'
            branch_payload['cancelled_at'] = now_iso
        elif status == 'waived':
            branch_payload['waiver_reason'] = reason or 'branch waived before execution'
        elif status == 'superseded':
            branch_payload['supersession_reason'] = reason or 'branch superseded before execution'
        return {
            key: value
            for key, value in branch_payload.items()
            if value not in (None, '', [], {})
        }

    def repair_action_for_branch(self, branch: Mapping[str, Any]) -> Optional[str]:
        for source in (
            branch,
            branch.get('recovery_state') if isinstance(branch.get('recovery_state'), Mapping) else {},
            branch.get('recovery_context') if isinstance(branch.get('recovery_context'), Mapping) else {},
        ):
            if not isinstance(source, Mapping):
                continue
            for key in ('repair_action', 'recovery_action', 'suggested_action', 'suggestedAction'):
                action = str(source.get(key) or '').strip()
                if action:
                    return normalize_recovery_suggested_action(action)
        return None

    @staticmethod
    def _branch_has_inline_dependency_evidence(branch: Mapping[str, Any]) -> bool:
        if str(branch.get('file_path') or '').strip():
            return True
        for key in ('input_artifacts', 'reference_artifacts'):
            value = branch.get(key)
            if isinstance(value, list) and any(isinstance(item, Mapping) for item in value):
                return True
        source = str(branch.get('content_payload_source') or '').strip()
        if source in {'late_fill_dependency_artifacts', 'prior_artifact_result'}:
            return bool(str(branch.get('content_payload') or '').strip())
        if source.startswith('late_fill_result'):
            return bool(str(branch.get('content_payload') or '').strip())
        return False

    @staticmethod
    def _current_payload_requires_materialization_repair(current_payload: Mapping[str, Any]) -> bool:
        runtime = (
            current_payload.get('runtime')
            if isinstance(current_payload.get('runtime'), Mapping)
            else {}
        )
        truth_guard = (
            runtime.get('truth_guard')
            if isinstance(runtime.get('truth_guard'), Mapping)
            else {}
        )
        return str(truth_guard.get('status') or '').strip().lower() in {
            'clarification_required',
            'repair_required',
        }

    def _branch_has_current_turn_direct_media_payload(
        self,
        branch: Mapping[str, Any],
    ) -> bool:
        return self.branch_dependency_evidence._branch_has_current_turn_direct_media_payload(branch)

    def _branch_depends_on_rejected_current_payload(
        self,
        branch: Mapping[str, Any],
        *,
        current_payload: Mapping[str, Any],
    ) -> bool:
        capability = self.branch_capability(branch)
        if capability == 'chat':
            return False
        if self.branch_dependency_evidence._branch_has_current_turn_direct_media_payload(branch):
            return False
        depends_on = {
            str(item or '').strip()
            for item in (branch.get('depends_on') or [])
            if str(item or '').strip()
        }
        source = str(branch.get('content_payload_source') or '').strip()
        consumes_current_phase = (
            'phase-1' in depends_on
            or source == 'current_phase_output'
            or not depends_on
        )
        if not consumes_current_phase:
            return False
        if self._current_payload_requires_materialization_repair(current_payload):
            return True
        return control_json_envelope_suspected(
            str(current_payload.get('output_text') or '').strip()
        )

    def repair_branch_execution_error(
        self,
        branch: Mapping[str, Any],
        *,
        current_payload: Mapping[str, Any],
        artifact_gap: Optional[Mapping[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        if any(
            source.get('branch_contract_error') == 'saved_file_dependency_unbound'
            for source in (branch, artifact_gap or {})
        ):
            return {
                'code': 'DEPENDENCY_CHAIN_REPAIR_REQUIRED',
                'message': 'The required saved-file read has no verified execution contract.',
                'stage': 'dependency_gate',
                'retryable': False,
                'repair_action': RECOVERY_ACTION_REPAIR_DEPENDENCY_CHAIN,
                'materialization_blocked': True,
                'branch_contract_error': 'saved_file_dependency_unbound',
            }
        if self._branch_depends_on_rejected_current_payload(branch, current_payload=current_payload):
            runtime = (
                current_payload.get('runtime')
                if isinstance(current_payload.get('runtime'), Mapping)
                else {}
            )
            truth_guard = (
                runtime.get('truth_guard')
                if isinstance(runtime.get('truth_guard'), Mapping)
                else {}
            )
            truth_guard_status = str(truth_guard.get('status') or '').strip().lower()
            control_payload_rejected = (
                truth_guard_status == 'repair_required'
                or control_json_envelope_suspected(
                    str(current_payload.get('output_text') or '').strip()
                )
            )
            return {
                'code': (
                    'UPSTREAM_CONTROL_PAYLOAD_REJECTED'
                    if control_payload_rejected
                    else 'UPSTREAM_CLARIFICATION_REQUIRED'
                ),
                'message': (
                    'Branch contract repair required before this branch can execute: '
                    + (
                        'the upstream result is an internal control envelope, not speakable or materializable payload.'
                        if control_payload_rejected
                        else 'the upstream result is a clarification or missing-source contract error, not materializable payload.'
                    )
                ),
                'stage': 'truth_guard_gate',
                'retryable': False,
                'repair_action': RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT,
                'reason': str(truth_guard.get('reason') or '').strip()
                or ('control_envelope_not_speakable' if control_payload_rejected else None),
            }
        failed_dependency_ids = self.failed_dependency_ids_for_branch(
            branch,
            current_payload=current_payload,
        )
        if failed_dependency_ids:
            return {
                'code': 'DEPENDENCY_CHAIN_REPAIR_REQUIRED',
                'message': (
                    'Dependency-chain repair required before this branch can execute: '
                    'a declared dependency failed or lacks usable evidence.'
                ),
                'stage': 'dependency_gate',
                'retryable': False,
                'repair_action': RECOVERY_ACTION_REPAIR_DEPENDENCY_CHAIN,
                'failed_dependency_ids': failed_dependency_ids,
            }
        gap_payload = artifact_gap if isinstance(artifact_gap, Mapping) else {}
        dependency_payload = self.branch_dependency_evidence.branch_dependency_payload(branch, current_payload=current_payload)
        if (saved_file_dependency_contract(branch) or separate_image_report_contract(branch)) and dependency_payload.get('branch_contract_error'):
            return {'code': 'DEPENDENCY_CHAIN_REPAIR_REQUIRED',
                    'message': dependency_payload['branch_contract_error'],
                    'stage': 'dependency_gate', 'retryable': False, **dependency_payload}
        repair_gate_item: dict[str, Any] = dict(gap_payload)
        repair_gate_item.update(dict(branch))
        if dependency_payload:
            for key, value in dependency_payload.items():
                repair_gate_item.setdefault(key, value)
        if gap_payload.get('depends_on') and not repair_gate_item.get('depends_on'):
            repair_gate_item['depends_on'] = gap_payload.get('depends_on')
        repair_action = self.repair_action_for_branch(branch)
        if repair_action in {
            RECOVERY_ACTION_REPAIR_DEPENDENCY_CHAIN,
            RECOVERY_ACTION_REBIND_DEPENDENCY_EVIDENCE,
        }:
            repair_gate_item['repair_action'] = repair_action
            repair_policy = classify_repair_execution_policy(repair_gate_item)
            if repair_policy.get('execution_policy') == 'schedule_late_fill_branch':
                return None
            return {
                'code': 'DEPENDENCY_CHAIN_REPAIR_REQUIRED',
                'message': 'Dependency-chain repair required before this branch can execute: missing dependency artifact or evidence.',
                'stage': 'repair_gate',
                'retryable': False,
                'repair_action': repair_action,
                'blocked_prerequisite': repair_policy.get('blocked_prerequisite'),
                'materialization_blocked': repair_policy.get('materialization_blocked'),
                'repair_work_available': repair_policy.get('repair_work_available'),
                'repair_work_policy': repair_policy.get('repair_work_policy'),
                'needs_external_input': repair_policy.get('needs_external_input'),
            }
        if repair_action == RECOVERY_ACTION_REBUILD_FROM_PROMOTED_OBLIGATIONS:
            repair_gate_item['repair_action'] = repair_action
            repair_policy = classify_repair_execution_policy(repair_gate_item)
            if repair_policy.get('execution_policy') == 'schedule_late_fill_branch':
                return None
            return {
                'code': 'REBUILD_FROM_PROMOTED_OBLIGATIONS_REQUIRED',
                'message': 'Rebuild from promoted obligations required before late fill can execute: graph planning missed promoted obligations.',
                'stage': 'repair_gate',
                'retryable': False,
                'repair_action': repair_action,
                'blocked_prerequisite': repair_policy.get('blocked_prerequisite') or 'promoted_obligation_branch',
                'materialization_blocked': True,
                'repair_work_available': repair_policy.get('repair_work_available'),
                'repair_work_policy': repair_policy.get('repair_work_policy'),
                'needs_external_input': repair_policy.get('needs_external_input'),
            }
        if repair_action == RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT:
            repair_gate_item['repair_action'] = repair_action
            repair_policy = classify_repair_execution_policy(repair_gate_item)
            if repair_policy.get('execution_policy') == 'schedule_late_fill_branch':
                return None
            return {
                'code': 'BRANCH_CONTRACT_REPAIR_REQUIRED',
                'message': 'Branch contract repair required before this branch can execute: missing bounded execution contract.',
                'stage': 'repair_gate',
                'retryable': False,
                'repair_action': repair_action,
                'blocked_prerequisite': repair_policy.get('blocked_prerequisite'),
                'materialization_blocked': repair_policy.get('materialization_blocked'),
                'repair_work_available': repair_policy.get('repair_work_available'),
                'repair_work_policy': repair_policy.get('repair_work_policy'),
                'needs_external_input': repair_policy.get('needs_external_input'),
            }
        has_inline_evidence = self._branch_has_inline_dependency_evidence(branch)
        has_dependency_payload = bool(dependency_payload)
        depends_on = [
            str(item or '').strip()
            for item in (branch.get('depends_on') or gap_payload.get('depends_on') or [])
            if str(item or '').strip()
        ]
        capability = self.branch_capability(branch) or self.normalize_capability(gap_payload.get('capability'))
        stage_direction = str(branch.get('stage_direction') or gap_payload.get('stage_direction') or '').strip()
        has_branch_payload = bool(
            str(branch.get('content_payload') or gap_payload.get('content_payload') or '').strip()
            or str(branch.get('artifact_prompt') or gap_payload.get('artifact_prompt') or '').strip()
            or str(branch.get('file_path') or gap_payload.get('file_path') or '').strip()
            or has_inline_evidence
            or has_dependency_payload
            or (
                isinstance(branch.get('batch_prompts') or gap_payload.get('batch_prompts'), list)
                and any(str(item or '').strip() for item in (branch.get('batch_prompts') or gap_payload.get('batch_prompts') or []))
            )
            or (
                capability == 'chat'
                and stage_direction == 'materialize_requested_text_artifact'
                and (
                    branch.get('artifact_request') not in (None, '', [], {})
                    or gap_payload.get('artifact_request') not in (None, '', [], {})
                    or str(branch.get('text_artifact_extension') or gap_payload.get('text_artifact_extension') or '').strip()
                )
            )
            or (
                isinstance(branch.get('execution_contract'), Mapping)
                and str(branch['execution_contract'].get('execution_scope') or '').strip() == 'root_scoped'
            )
        )
        if not has_branch_payload and depends_on:
            return {
                'code': 'DEPENDENCY_CHAIN_REPAIR_REQUIRED',
                'message': 'Dependency-chain repair required before this branch can execute: missing dependency artifact or evidence.',
                'stage': 'repair_gate',
                'retryable': False,
            }
        if not has_branch_payload and capability in {'chat', self.capability_image_generation, self.capability_text_to_speech, 'vision_analysis', 'speech_to_text'}:
            return {
                'code': 'BRANCH_CONTRACT_REPAIR_REQUIRED',
                'message': 'Branch contract repair required before this branch can execute: missing branch-local payload or bounded execution contract.',
                'stage': 'repair_gate',
                'retryable': False,
            }
        return None

    def _verified_pending_review_instruction(self, gap, current, request):
        """Prove the exact owed review against current Runtime generation truth.

        This is preparation evidence, never a new execution permit. The claimed
        C9 worker still owns scope, dependency, cancellation and publication gates.
        """
        binding = BranchDependencyEvidence._content_review_binding(gap)
        instruction = gap.get('content_payload')
        if (not binding or not isinstance(instruction, str) or not instruction
                or gap.get('capability') != 'chat'
                or gap.get('stage_direction') != 'run_branch_semantic_review'
                or gap.get('trigger') in {'graph_patch_successor_reopen', 'graph_rebase_partial_successor'}):
            return None
        late = current.get('late_fill') or {}
        branches = [b for b in late.get('pending_branches', [])
                    if isinstance(b, Mapping) and self.branch_id(b) == self.branch_id(gap)]
        if len(branches) != 1:
            return None
        branch = branches[0]
        repair = branch.get('repair_contract') or {}
        projected = gap.get('execution_contract') or {}
        execution = repair.get('execution_contract') or {}
        expected_projection = self.build_execution_contract(branch, capability='chat')
        reopen = late.get('terminal_closure_repair_reopen') or {}
        if (branch.get('contract_state') != 'promoted' or repair.get('status') != 'promoted'
                or repair.get('authority') != 'closure_review_runtime_truth'
                or not repair.get('contract_id')
                or branch.get('repair_contract_id') != repair.get('contract_id')
                or branch.get('promotion_source') != repair.get('promotion_source')
                or not repair.get('promotion_source')
                or reopen.get('authority') != 'terminal_graph_closure_review'
                or self.branch_id(branch) not in (reopen.get('branch_ids') or [])
                or repair['contract_id'] not in (reopen.get('contract_ids') or [])
                or any(gap.get(k) != branch.get(k) for k in ('branch_id', 'phase_id', 'obligation_id'))
                or any(instruction != item.get('content_payload') for item in (branch, repair))
                or binding != BranchDependencyEvidence._content_review_binding(branch)
                or binding != BranchDependencyEvidence._content_review_binding(repair)
                or branch.get('execution_contract') != execution
                or projected.get('repair_contract') != repair
                or projected.get('execution_scope') not in (None, '', 'branch_local')
                or any(projected.get(k) != expected_projection.get(k) for k in (
                    'branch_id', 'phase_id', 'capability', 'output_type',
                    'workload_task_ref', 'output_obligation_ref', 'output_contract',
                    'depends_on', 'input_refs'))
                or execution.get('execution_scope') not in (None, '', 'branch_local')
                or execution.get('capability') != 'chat'
                or execution.get('output_type') != 'text'
                or execution.get('visibility') != 'internal'
                or execution.get('surface_role') != 'closure_evidence'
                or (execution.get('output_contract') or {}).get('fulfillment_policy')
                    != 'branch_semantic_review_verdict_required'
                or branch.get('depends_on') != [binding.get('source_branch_id')]
                or repair.get('depends_on') != branch.get('depends_on')):
            return None
        repair_binding = repair.get('execution_binding') or {}
        if (repair_binding.get('contract_id') != repair['contract_id']
                or any(repair_binding.get(k) != branch.get(k) for k in ('branch_id', 'phase_id'))):
            return None
        graph = (current.get('runtime') or {}).get('request_phase_graph') or {}
        obligations = [o for o in graph.get('output_obligations', [])
                       if isinstance(o, Mapping) and o.get('obligation_id') == branch.get('obligation_id')]
        if len(obligations) != 1:
            return None
        obligation = obligations[0]
        if (obligation.get('contract_state') != 'promoted'
                or obligation.get('repair_contract_id') != repair['contract_id']
                or any(obligation.get(k) != branch.get(k) for k in ('branch_id', 'phase_id'))):
            return None
        reviews = [r for r in graph.get('graph_repair_reviews', [])
                   if r.get('review_id') == obligation.get('graph_repair_review_id')
                   and r.get('proposal_id') == obligation.get('graph_repair_proposal_id')
                   and r.get('status') == 'accepted']
        patches = [p for r in reviews for p in (r.get('accepted_patch') or {}).get('add_phases', [])
                   if p.get('branch_id') == branch.get('branch_id')]
        if (len(reviews) != 1 or len(patches) != 1
                or any(patches[0].get(k) != branch.get(k)
                       for k in ('branch_id', 'phase_id', 'obligation_id', 'repair_contract_id'))):
            return None
        # Re-derive the instruction generation from current caller policy and
        # actual artifact/dependency evidence through its existing owner. A
        # self-consistent caller/provider hash or review label is insufficient.
        fresh = self.build_graph_closure_review(
            str(current.get('output_text') or ''), request_payload=request,
            artifact_payload=current,
        )
        checks = [c for c in fresh.get('checks', [])
                  if c.get('branch_id') == binding.get('source_branch_id')
                  and c.get('phase_id') == binding.get('source_phase_id')]
        if (not checks or any(not c.get('content_requirements')
                or c.get('branch_semantic_review_evidence_binding') != binding for c in checks)
                or hashlib.sha256(instruction.encode('utf-8')).hexdigest() != binding.get('instruction_sha256')):
            return None
        for check in checks:
            generated = ResponseSemanticsRuntimeOwner._branch_semantic_review_generation(check, instruction)
            if any(binding.get(k) != value for k, value in generated.items()):
                return None
        return instruction

    def _enforce_graph_patch_successor_branch_local_payload(
        self,
        late_fill_payload: dict[str, Any],
        *,
        original_prompt: str,
        artifact_gap: Mapping[str, Any],
        normalized_expected_capability: Optional[str],
        root_scoped_execution: bool,
        _verified_review_instruction: Optional[str] = None,
    ) -> dict[str, Any]:
        """Keep every bounded successor execution local to its owed branch."""

        updated = dict(late_fill_payload or {})
        gap = artifact_gap if isinstance(artifact_gap, Mapping) else {}
        trigger = str(gap.get('trigger') or '').strip().lower()
        error_prefix = (
            'graph_rebase_partial_successor'
            if trigger == 'graph_rebase_partial_successor'
            else 'graph_patch_successor'
        )
        effective_prompt = str(updated.get('prompt') or '').strip()
        root_prompt = str(original_prompt or '').strip()
        execution_contract = (
            gap.get('execution_contract')
            if isinstance(gap.get('execution_contract'), Mapping)
            else {}
        )
        forbidden_root_prompt_digest = str(
            execution_contract.get('forbidden_root_prompt_digest') or ''
        ).strip()
        artifact_prompt = str(gap.get('artifact_prompt') or '').strip()
        content_payload = str(gap.get('content_payload') or '').strip()
        phase_summary = str(gap.get('phase_summary') or '').strip()
        has_branch_artifact_input = bool(
            str(gap.get('file_path') or '').strip()
            or any(
                isinstance(item, Mapping)
                for key in ('input_artifacts', 'reference_artifacts')
                for item in (gap.get(key) if isinstance(gap.get(key), list) else [])
            )
        )

        # The successor request owns only the proven owed branches. Compatibility
        # inputs from the frozen parent must never survive as a second prompt path.
        for key in ('input', 'messages', 'inference_messages', 'batch_prompts'):
            updated.pop(key, None)

        partial_root_guard_invalid = bool(
            trigger == 'graph_rebase_partial_successor'
            and (
                not root_prompt
                or not forbidden_root_prompt_digest
                or stable_graph_rebase_prompt_digest(root_prompt)
                != forbidden_root_prompt_digest
            )
        )
        def replays_root(carrier: str, *, review_carrier: bool = False) -> bool:
            return graph_rebase_prompt_contains_root(carrier, root_prompt) and not (
                review_carrier and _verified_review_instruction
                and carrier == _verified_review_instruction
                and trigger not in {'graph_patch_successor_reopen', 'graph_rebase_partial_successor'}
            )

        prompt_replays_root = replays_root(effective_prompt, review_carrier=True)
        if not effective_prompt or prompt_replays_root:
            branch_prompt = next(
                (
                    candidate
                    for candidate in (artifact_prompt, content_payload, phase_summary)
                    if candidate
                    and not graph_rebase_prompt_contains_root(candidate, root_prompt)
                ),
                '',
            )
            if not branch_prompt and has_branch_artifact_input:
                if normalized_expected_capability == 'vision_analysis':
                    branch_prompt = self._vision_artifact_analysis_instruction('', evidence=content_payload)
                elif normalized_expected_capability == 'speech_to_text':
                    branch_prompt = (
                        'Transcribe only the attached branch-local audio artifact. '
                        'Return the transcript without restarting the original request.'
                    )
            effective_prompt = branch_prompt

        def prompt_carrier_strings(value: Any) -> list[str]:
            if isinstance(value, Mapping):
                values: list[str] = []
                for child in value.values():
                    values.extend(prompt_carrier_strings(child))
                return values
            if isinstance(value, (list, tuple, set)):
                values = []
                for child in value:
                    values.extend(prompt_carrier_strings(child))
                return values
            text = str(value or '').strip()
            return [text] if text else []

        prompt_carriers = [(effective_prompt, True)]
        for key in (
            'content_payload',
            'artifact_prompt',
            'batch_prompts',
            'phase_summary',
            'stage_direction',
            'instruct',
            'review_criteria',
            'semantic_review_criteria',
            'controlled_attention_question',
        ):
            prompt_carriers.extend((value, key == 'content_payload')
                                   for value in prompt_carrier_strings(updated.get(key)))
        carrier_replays_root = any(
            replays_root(carrier, review_carrier=review_carrier)
            for carrier, review_carrier in prompt_carriers
        )
        carrier_matches_forbidden_digest = bool(
            forbidden_root_prompt_digest
            and any(
                stable_graph_rebase_prompt_digest(carrier)
                == forbidden_root_prompt_digest
                for carrier, _ in prompt_carriers
                if carrier
            )
        )
        invalid_local_prompt = bool(
            partial_root_guard_invalid
            or not effective_prompt
            or carrier_replays_root
            or carrier_matches_forbidden_digest
        )
        if root_scoped_execution or invalid_local_prompt:
            updated.pop('prompt', None)
            updated.pop('_prompt_hint', None)
            updated.pop('instruct', None)
            updated['repair_action'] = RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT
            updated['branch_contract_error'] = (
                f'{error_prefix}_root_prompt_guard_invalid'
                if partial_root_guard_invalid
                else f'{error_prefix}_root_scoped_contract_forbidden'
                if root_scoped_execution
                else f'{error_prefix}_missing_branch_local_payload'
            )
            updated['successor_root_prompt_replay_forbidden'] = True
            return updated

        updated['prompt'] = effective_prompt
        updated['_prompt_hint'] = effective_prompt
        updated['successor_branch_local_payload_enforced'] = True
        updated['successor_root_prompt_replay_forbidden'] = True
        return updated

    def prepare_late_fill_request_payload(
        self,
        request_payload: dict[str, Any],
        *,
        expected_capability: str,
        assistant_message: str,
        artifact_gap: Optional[dict[str, Any]] = None,
        guarded_pending: bool = False,
        _verified_review_instruction: Optional[str] = None,
    ) -> dict[str, Any]:
        late_fill_payload = self.normalize_request_payload(request_payload)
        missing_root_intent = request_intent_evidence_missing(late_fill_payload)
        request_meta = self.extract_request_meta(late_fill_payload)
        if expected_capability:
            request_meta = dict(request_meta or {})
            request_meta['capability_hint'] = expected_capability
            late_fill_payload['request_meta'] = request_meta
            late_fill_payload = self.attach_request_meta(late_fill_payload)
        artifact_gap_payload = artifact_gap if isinstance(artifact_gap, dict) else {}
        original_prompt = (
            extract_responses_current_turn_prompt(late_fill_payload)
            if has_captured_request_intent(late_fill_payload)
            else self.extract_responses_prompt(late_fill_payload)
        )
        late_fill_trigger = str(artifact_gap_payload.get('trigger') or '').strip().lower()
        late_fill_code = str(artifact_gap_payload.get('code') or '').strip().lower()
        successor_branch_execution = guarded_pending or late_fill_trigger in {
            'graph_patch_successor_reopen',
            'graph_rebase_partial_successor',
        }
        execution_contract = (
            artifact_gap_payload.get('execution_contract')
            if isinstance(artifact_gap_payload.get('execution_contract'), Mapping)
            else {}
        )
        graph_branch_execution = bool(
            artifact_gap_payload.get('branch_id')
            or artifact_gap_payload.get('phase_id')
            or execution_contract.get('branch_id')
            or execution_contract.get('phase_id')
        )
        if graph_branch_execution:
            # Child execution owns its accepted branch payload and typed output
            # scope, rather than inheriting the root's private intent capture.
            late_fill_payload.pop('_request_intent', None)
            if missing_root_intent:
                for key in ('prompt', 'input', 'instructions', '_prompt_hint'):
                    late_fill_payload.pop(key, None)
            # The normalized request is a frozen root envelope. A graph branch
            # may restore only materialization authority explicitly carried by
            # that branch; sibling/root publication must not leak into it.
            inherited_materialization_fields = (
                _BRANCH_LOCAL_MATERIALIZATION_FIELDS
                | _BRANCH_LOCAL_PUBLICATION_FIELDS
                | {
                    key
                    for key in late_fill_payload
                    if str(key).startswith('saved_')
                }
            )
            for key in inherited_materialization_fields:
                late_fill_payload.pop(key, None)
        for key in (
            'execution_contract',
            'workload_task_ref',
            'output_obligation_ref',
            'branch_id',
            'phase_id',
            'obligation_id',
            'task_id',
            'workload_task_id',
            'output_type',
            'depends_on',
            'input_refs',
            'content_payload',
            'stage_direction',
            'phase_summary',
            'content_payload_source',
            'selection_policy',
            'candidate_selection_index',
            'candidate_selection_count',
            'selection_reason',
            'audio_variant_index',
            'audio_variant_role',
            'audio_variant_contract_source',
            'structured_output_contract',
            'artifact_prompt',
            'artifact_prompt_source',
            'review_criteria',
            'semantic_review_criteria',
            'semantic_review_required',
            'semantic_review_action',
            'semantic_review_authority',
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
            'aspiration_review',
            'aspiration_frame',
            'aspiration_frame_id',
            'aspiration_action',
            'aspiration_reason',
            'aspiration_allowed_actions',
            'commitment_review',
            'commitment_frame',
            'commitment_frame_id',
            'commitment_action',
            'commitment_recommended_transition',
            'commitment_reason',
            'commitment_allowed_transitions',
            'controlled_attention_review',
            'controlled_attention_frame',
            'controlled_attention_frame_id',
            'controlled_attention_scope',
            'controlled_attention_priority',
            'controlled_attention_question',
            'controlled_attention_allowed_transitions',
            'global_semantic_closure_review',
            'global_semantic_closure_proposal',
            'global_semantic_closure_status',
            'global_semantic_closure_reason',
            'global_semantic_closure_confidence',
            'requires_artifact',
            'text_artifact_extension',
            'text_artifact_source_name',
            'text_artifact_source',
            'text_artifact_target_path',
            'text_artifact_revision_required',
            'text_artifact_revision_source',
            'text_artifact_source_is_input',
            'text_artifact_revision_binding_state',
            'text_artifact_revision_source_path',
            'text_artifact_revision_source_size_bytes',
            'text_artifact_revision_source_sha256',
            'text_artifact_revision_preservation_required',
            'text_artifact_revision_preservation_policy',
            'text_artifact_requests',
            'text_artifact_request',
            'artifact_request',
            'file_path',
            'input_artifacts',
            'reference_artifacts',
            'lang_code',
            'voice',
            'instruct',
            'response_format',
            'output_format',
            'speed',
            'pitch',
            'suppress_reference_file_context',
            'selected_reference_prompt_policy',
            'dependency_payload_policy',
            'suppress_image_state_enrichment',
            'suppress_generated_image_enrichment',
            'image_state_enrichment_suppression_reason',
            'branch_contract_error',
            'audio_variant_contract_conflicting_fields',
            'materialization_blocked',
            'batch_prompts',
            'batch_prompts_source',
            'batch_prompt_expected_count',
            'batch_prompt_expected_count_invalid',
            'batch_prompt_actual_count',
            'counted_batch_prompt_carriers_blocked',
            'candidate_extraction_issue',
        ):
            value = artifact_gap_payload.get(key)
            if value not in (None, '', [], {}):
                late_fill_payload[key] = value
        execution_contract = (
            late_fill_payload.get('execution_contract')
            if isinstance(late_fill_payload.get('execution_contract'), Mapping)
            else {}
        )
        if execution_contract:
            workload_task_ref = (
                execution_contract.get('workload_task_ref')
                if isinstance(execution_contract.get('workload_task_ref'), Mapping)
                else {}
            )
            output_obligation_ref = (
                execution_contract.get('output_obligation_ref')
                if isinstance(execution_contract.get('output_obligation_ref'), Mapping)
                else {}
            )
            for key in ('branch_id', 'phase_id', 'capability', 'output_type'):
                value = execution_contract.get(key)
                if value not in (None, '', [], {}) and late_fill_payload.get(key) in (None, '', [], {}):
                    late_fill_payload[key] = value
            task_id = workload_task_ref.get('task_id') if isinstance(workload_task_ref, Mapping) else None
            if task_id not in (None, '', [], {}) and late_fill_payload.get('task_id') in (None, '', [], {}):
                late_fill_payload['task_id'] = task_id
                late_fill_payload['workload_task_id'] = task_id
            obligation_id = (
                output_obligation_ref.get('obligation_id')
                if isinstance(output_obligation_ref, Mapping)
                else None
            )
            if obligation_id not in (None, '', [], {}) and late_fill_payload.get('obligation_id') in (None, '', [], {}):
                late_fill_payload['obligation_id'] = obligation_id
        root_scoped_execution = (
            str(execution_contract.get('execution_scope') or '').strip().lower()
            in {'root', 'root_scoped', 'whole_request', 'original_prompt'}
            or self.parse_bool(execution_contract.get('root_scoped'), default=False)
            or self.parse_bool(execution_contract.get('allow_root_prompt'), default=False)
        ) if execution_contract else False
        normalized_expected_capability = self.normalize_capability(expected_capability)
        artifact_prompt = str(artifact_gap_payload.get('artifact_prompt') or '').strip()
        content_payload = str(artifact_gap_payload.get('content_payload') or '').strip()
        content_payload_source = str(artifact_gap_payload.get('content_payload_source') or '').strip()
        selection_policy = str(artifact_gap_payload.get('selection_policy') or '').strip().lower()
        if (
            normalized_expected_capability == 'speech_to_text'
            and content_payload_source == 'selected_reference_audio_artifact'
        ):
            selected_audio_path = ''
            raw_selected_references: Any = None
            for key in (
                'selected_reference_artifacts',
                'selectedReferenceArtifacts',
                'selected_reference_artifact',
                'selectedReferenceArtifact',
            ):
                raw_value = late_fill_payload.get(key)
                if raw_value not in (None, '', [], {}):
                    raw_selected_references = raw_value
                    break
            if raw_selected_references in (None, '', [], {}):
                raw_selected_references = late_fill_payload.get('reference_artifacts')
            selected_reference_candidates = self.sanitize_selected_reference_artifacts(
                raw_selected_references,
                payload_source=late_fill_payload,
            )
            declared_refs = {
                str(item.get('artifact_ref') or item.get('ref') or '').strip()
                for item in execution_contract.get('input_refs') or []
                if isinstance(item, Mapping)
                and str(item.get('artifact_ref') or item.get('ref') or '').strip()
            }
            selected_audio_candidates = []
            for artifact in selected_reference_candidates:
                artifact_type = str(
                    artifact.get('type') or artifact.get('kind') or ''
                ).strip().lower()
                if artifact_type not in {
                    'audio', 'wav', 'mp3', 'm4a', 'flac', 'aac', 'ogg', 'opus'
                }:
                    continue
                artifact_ref = str(artifact.get('artifact_ref') or artifact.get('ref') or '').strip()
                if declared_refs and artifact_ref not in declared_refs:
                    continue
                if branch_result_contracts._artifact_record_path(artifact) and artifact not in selected_audio_candidates:
                    selected_audio_candidates.append(artifact)
            if len(selected_audio_candidates) == 1:
                selected_audio_path = branch_result_contracts._artifact_record_path(selected_audio_candidates[0])
            if selected_audio_path:
                # Explicit file authority outranks both current input fallback
                # and route reuse for this selected-reference branch.
                late_fill_payload['file_path'] = selected_audio_path
            else:
                late_fill_payload['branch_contract_error'] = (
                    'selected_reference_audio_unavailable'
                )
                late_fill_payload['materialization_blocked'] = True
        if (
            normalized_expected_capability == 'speech_to_text'
            and content_payload_source == 'current_input_audio_artifact'
        ):
            # The branch explicitly reselects the current request input. Keep
            # carried predecessor audio as reference truth, but prevent route
            # reuse from replacing the selected input at the infer boundary.
            late_fill_payload['suppress_reference_file_context'] = True
        successor_branch_prompt_context = str(
            artifact_gap_payload.get('phase_summary')
            or artifact_gap_payload.get('stage_direction')
            or ''
        ).strip().replace('_', ' ')
        bounded_prompt_context = (
            successor_branch_prompt_context
            if successor_branch_execution
            else original_prompt
        )
        if (
            normalized_expected_capability == self.capability_text_to_speech
            and late_fill_payload.get('response_format') in (None, '')
            and late_fill_payload.get('output_format') not in (None, '')
        ):
            late_fill_payload['response_format'] = str(late_fill_payload.get('output_format') or '').strip()
        if normalized_expected_capability == self.capability_text_to_speech and late_fill_payload.get('lang_code') in (None, ''):
            inferred_lang_code = (
                infer_tts_language_from_prompt(content_payload)
                or infer_tts_language_from_prompt(original_prompt)
            )
            if inferred_lang_code:
                late_fill_payload['lang_code'] = inferred_lang_code
        is_closure_or_repair = (
            late_fill_trigger in {
                'pre_freeze_closure_review',
                'inference_repair_feedback',
                'phase_continuation',
                'runtime_applied_graph_patch',
                'graph_patch_successor_reopen',
                'graph_rebase_partial_successor',
            }
            or late_fill_code in {
                'closure_review_fill',
                'closure_review_repair',
                'late_artifact_fill',
                'graph_patch_late_fill',
                'graph_rebase_partial_late_fill',
            }
        )
        if (
            normalized_expected_capability == self.capability_image_generation
            and (artifact_prompt or (content_payload and is_closure_or_repair))
            and (is_closure_or_repair or late_fill_trigger == 'execution_planner_deferred_follow_up')
        ):
            focused_prompt = artifact_prompt or content_payload
            late_fill_payload['prompt'] = focused_prompt
            late_fill_payload['_prompt_hint'] = original_prompt or focused_prompt
        elif normalized_expected_capability == self.capability_text_to_speech and content_payload:
            late_fill_payload['prompt'] = content_payload
            late_fill_payload['_prompt_hint'] = original_prompt or content_payload
            # The branch-local payload is the exact text this TTS obligation
            # owns. Carried references remain request truth, but must not be
            # appended as a second, implicit speech source.
            late_fill_payload['suppress_reference_file_context'] = True
        elif (
            normalized_expected_capability == self.capability_text_to_speech
            and late_fill_trigger == 'execution_planner_deferred_follow_up'
        ):
            reference_prompt = 'Read that reply aloud.'
            late_fill_payload['prompt'] = reference_prompt
            late_fill_payload['_prompt_hint'] = original_prompt or reference_prompt
        elif (
            normalized_expected_capability == self.capability_image_generation
            and late_fill_trigger == 'execution_planner_deferred_follow_up'
        ):
            artifact_prompt = str(
                artifact_gap_payload.get('artifact_prompt')
                or (original_prompt if root_scoped_execution else '')
                or ''
            ).strip()
            if artifact_prompt:
                late_fill_payload['prompt'] = artifact_prompt
                late_fill_payload['_prompt_hint'] = original_prompt or artifact_prompt
            elif not root_scoped_execution:
                late_fill_payload.pop('prompt', None)
                late_fill_payload['repair_action'] = RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT
                late_fill_payload['branch_contract_error'] = 'missing_branch_local_payload'
        elif (
            normalized_expected_capability == 'vision_analysis'
            and (
                str(artifact_gap_payload.get('file_path') or '').strip()
                or artifact_gap_payload.get('input_artifacts')
                or content_payload_source == 'late_fill_dependency_artifacts'
            )
        ):
            vision_prompt = self._vision_artifact_analysis_instruction(
                bounded_prompt_context,
                evidence=content_payload,
                execution_contract=execution_contract,
            )
            if vision_prompt:
                late_fill_payload['prompt'] = vision_prompt
                late_fill_payload['_prompt_hint'] = original_prompt or vision_prompt
        elif (
            normalized_expected_capability == 'chat'
            and str(artifact_gap_payload.get('stage_direction') or '').strip() in {
                'run_global_semantic_closure_review',
                'run_branch_semantic_review',
            }
            and content_payload
        ):
            late_fill_payload['prompt'] = content_payload
            late_fill_payload['_prompt_hint'] = content_payload
            late_fill_payload['suppress_reference_file_context'] = True
        elif (
            normalized_expected_capability == 'chat'
            and str(artifact_gap_payload.get('stage_direction') or '').strip() == 'materialize_requested_text_artifact'
        ):
            text_artifact_prompt = self._text_artifact_materialization_instruction(
                bounded_prompt_context,
                artifact_gap_payload,
            )
            if text_artifact_prompt:
                late_fill_payload['prompt'] = text_artifact_prompt
                saved_contract = saved_file_dependency_contract(artifact_gap_payload)
                late_fill_payload['_prompt_hint'] = (saved_contract['consumer_instruction']
                    if saved_contract else original_prompt or text_artifact_prompt)
        elif (
            normalized_expected_capability == 'chat'
            and (
                str(artifact_gap_payload.get('stage_direction') or '').strip() == 'write_text_after_artifact_generation'
                or str(artifact_gap_payload.get('content_payload_source') or '').strip() == 'prior_artifact_result'
                or str(artifact_gap_payload.get('content_payload_source') or '').strip().startswith('late_fill_result')
                or (
                    is_closure_or_repair
                    and content_payload
                    and (
                        content_payload_source == 'current_phase_output'
                        or content_payload_source.startswith('late_fill_result')
                        or content_payload_source in {'prior_artifact_result', 'late_fill_dependency_artifacts'}
                    )
                )
            )
        ):
            follow_up_prompt = self._post_artifact_follow_up_instruction(
                bounded_prompt_context,
                evidence=str(artifact_gap_payload.get('content_payload') or '').strip(),
                structured_output_contract=(
                    artifact_gap_payload.get('structured_output_contract')
                    if isinstance(
                        artifact_gap_payload.get('structured_output_contract'),
                        Mapping,
                    )
                    else None
                ),
            )
            if follow_up_prompt:
                late_fill_payload['prompt'] = follow_up_prompt
                late_fill_payload['_prompt_hint'] = original_prompt or follow_up_prompt
                late_fill_payload['suppress_reference_file_context'] = True
        if successor_branch_execution:
            late_fill_payload = self._enforce_graph_patch_successor_branch_local_payload(
                late_fill_payload,
                original_prompt=original_prompt,
                artifact_gap=artifact_gap_payload,
                normalized_expected_capability=normalized_expected_capability,
                root_scoped_execution=root_scoped_execution,
                _verified_review_instruction=_verified_review_instruction,
            )
        counted_image_prompt_expected, invalid_image_prompt_count = (
            _parse_image_batch_expected_count(
                artifact_gap_payload.get('batch_prompt_expected_count'),
                present=(
                    'batch_prompt_expected_count' in artifact_gap_payload
                    and artifact_gap_payload.get('batch_prompt_expected_count')
                    not in (None, '', [], {})
                ),
            )
        )
        counted_image_prompts = (
            artifact_gap_payload.get('batch_prompts')
            if isinstance(artifact_gap_payload.get('batch_prompts'), list)
            else []
        )
        counted_image_prompt_actual = len(
            [
                item
                for item in counted_image_prompts
                if str(item or '').strip()
            ]
        )
        counted_image_batch_blocked = bool(
            normalized_expected_capability == self.capability_image_generation
            and (
                invalid_image_prompt_count
                or (
                    counted_image_prompt_expected >= 2
                    and (
                        len(counted_image_prompts) != counted_image_prompt_expected
                        or counted_image_prompt_actual != counted_image_prompt_expected
                    )
                )
            )
        )
        if counted_image_batch_blocked:
            # No root prompt, preparation prose, history, or partial batch may
            # become a fallback execution carrier for a missing counted slot.
            for key in (
                'prompt',
                '_prompt_hint',
                'input',
                'messages',
                'inference_messages',
                'artifact_prompt',
                'content_payload',
                'phase_summary',
                'stage_direction',
                'instruct',
                'batch_prompts',
                'artifact_prompt_source',
                'content_payload_source',
                'batch_prompts_source',
                'batch_prompt_source_phase_id',
                'batch_prompt_expected_count',
            ):
                late_fill_payload.pop(key, None)
            late_fill_payload['branch_contract_error'] = (
                'incomplete_image_prompt_batch'
            )
            late_fill_payload['materialization_blocked'] = True
            if invalid_image_prompt_count:
                late_fill_payload['batch_prompt_expected_count_invalid'] = True
            else:
                late_fill_payload['batch_prompt_expected_count'] = (
                    counted_image_prompt_expected
                )
            late_fill_payload['batch_prompt_actual_count'] = (
                counted_image_prompt_actual
            )
            late_fill_payload['repair_action'] = (
                RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT
            )
            late_fill_payload['candidate_extraction_issue'] = (
                'invalid_image_prompt_batch_count'
                if invalid_image_prompt_count
                else 'missing_exact_branch_local_image_prompt_batch'
            )
            late_fill_payload['counted_batch_prompt_carriers_blocked'] = True
            return late_fill_payload
        late_fill_payload.pop('inference_preview', None)
        semantic_review_stage = str(
            artifact_gap_payload.get('stage_direction') or ''
        ).strip() in {
            'run_global_semantic_closure_review',
            'run_branch_semantic_review',
        }
        if semantic_review_stage:
            # Semantic reviewers receive the explicit bounded evidence packet,
            # never a second prompt path through carried conversation history.
            for key in ('input', 'messages', 'inference_messages', 'batch_prompts'):
                late_fill_payload.pop(key, None)
        should_attach_inference_messages = (
            not successor_branch_execution
            and not semantic_review_stage
            and (
                self.parse_bool(late_fill_payload.get('inference_route'), default=False)
                or late_fill_trigger == 'execution_planner_deferred_follow_up'
            )
        )
        if should_attach_inference_messages:
            inference_messages = self.extract_inference_route_messages(late_fill_payload)
            assistant_entry = {
                'role': 'assistant',
                'content': str(assistant_message or '').strip(),
                'timestamp': self.response_registry_now_iso(),
            }
            if assistant_entry['content']:
                last_message = inference_messages[-1] if inference_messages else {}
                last_role = str(last_message.get('role') or '').strip().lower()
                last_content = str(last_message.get('content') or '').strip()
                if last_role != 'assistant' or last_content != assistant_entry['content']:
                    inference_messages.append(assistant_entry)
            late_fill_payload['inference_messages'] = inference_messages[-self.max_recent_messages:]
        if missing_root_intent and (
            not graph_branch_execution
            or not str(late_fill_payload.get('prompt') or '').strip()
        ):
            late_fill_payload['branch_contract_error'] = 'request_intent_evidence_unavailable'
            late_fill_payload['materialization_blocked'] = True
        if graph_branch_execution:
            # Carried root input/history remains execution context, rather than
            # overriding this accepted branch's own current-turn payload.
            branch_request = {key: value for key, value in late_fill_payload.items()
                              if key not in {'input', 'instructions'}}
            late_fill_payload['_request_intent'] = capture_request_intent(branch_request)['_request_intent']
        return late_fill_payload

    @staticmethod
    def _source_route_external_target_identity(
        source_route_payload: Any,
    ) -> tuple[str, dict[str, Any]]:
        """Return a joined external target identity from live or persisted route truth."""

        source_route = (
            source_route_payload
            if isinstance(source_route_payload, Mapping)
            else {}
        )
        source_instance = (
            source_route.get('instance')
            if isinstance(source_route.get('instance'), Mapping)
            else {}
        )
        route_runtime = (
            source_route.get('route_runtime')
            if isinstance(source_route.get('route_runtime'), Mapping)
            else {}
        )
        runtime = (
            source_route.get('runtime')
            if isinstance(source_route.get('runtime'), Mapping)
            else {}
        )
        working_frame = (
            source_route.get('working_frame')
            if isinstance(source_route.get('working_frame'), Mapping)
            else {}
        )
        working_target = (
            working_frame.get('target')
            if isinstance(working_frame.get('target'), Mapping)
            else {}
        )
        live_external_descriptor = bool(
            source_instance
            and str(source_instance.get('target_kind') or '').strip().lower()
            == 'external'
        )
        external_descriptor: dict[str, Any] = (
            dict(source_instance) if live_external_descriptor else {}
        )
        if not external_descriptor:
            for candidate in (
                route_runtime.get('external_target'),
                runtime.get('external_target'),
                source_route.get('external_target'),
            ):
                if (
                    isinstance(candidate, Mapping)
                    and str(candidate.get('target_kind') or '')
                    .strip()
                    .lower()
                    == 'external'
                ):
                    external_descriptor = dict(candidate)
                    break
        if not external_descriptor:
            return '', {}

        descriptor_id = str(
            external_descriptor.get('instance_id')
            or external_descriptor.get('id')
            or ''
        ).strip()
        if not descriptor_id:
            return '', {}
        if not live_external_descriptor:
            external_execution = (
                route_runtime.get('external_execution')
                if isinstance(
                    route_runtime.get('external_execution'),
                    Mapping,
                )
                else runtime.get('external_execution')
                if isinstance(runtime.get('external_execution'), Mapping)
                else {}
            )
            external_phase_policy = (
                route_runtime.get('external_phase_execution_policy')
                if isinstance(
                    route_runtime.get('external_phase_execution_policy'),
                    Mapping,
                )
                else runtime.get('external_phase_execution_policy')
                if isinstance(
                    runtime.get('external_phase_execution_policy'),
                    Mapping,
                )
                else {}
            )
            execution_target_id = str(
                external_execution.get('target_id') or ''
            ).strip()
            descriptor_provider = str(
                external_descriptor.get('provider') or ''
            ).strip().lower()
            execution_provider = str(
                external_execution.get('provider') or ''
            ).strip().lower()
            if (
                str(external_execution.get('status') or '')
                .strip()
                .lower()
                != 'completed'
                or execution_target_id != descriptor_id
                or (
                    descriptor_provider
                    and execution_provider
                    and descriptor_provider != execution_provider
                )
                or str(external_phase_policy.get('status') or '')
                .strip()
                .lower()
                != 'bounded'
                or str(
                    external_phase_policy.get('materialization_authority')
                    or ''
                ).strip()
                != 'fruth_runtime'
                or str(
                    external_phase_policy.get('root_request_authority')
                    or ''
                ).strip()
                != 'promoted_context_reference_only'
            ):
                return '', {}
        for candidate_id in (
            source_route.get('instance_id'),
            source_instance.get('instance_id'),
            source_instance.get('id'),
            working_target.get('instance_id'),
            working_target.get('id'),
        ):
            token = str(candidate_id or '').strip()
            if token and token != descriptor_id:
                return '', {}
        return descriptor_id, external_descriptor

    @staticmethod
    def _source_route_with_response_external_runtime(
        source_route_payload: Any,
        response_payload: Any,
    ) -> dict[str, Any]:
        """Carry only CAS-backed external authority into a recovered route view."""

        source_route = (
            dict(source_route_payload)
            if isinstance(source_route_payload, Mapping)
            else {}
        )
        response_runtime = (
            response_payload.get('runtime')
            if isinstance(response_payload, Mapping)
            and isinstance(response_payload.get('runtime'), Mapping)
            else {}
        )
        external_target = (
            response_runtime.get('external_target')
            if isinstance(response_runtime.get('external_target'), Mapping)
            else {}
        )
        if (
            not external_target
            or str(external_target.get('target_kind') or '')
            .strip()
            .lower()
            != 'external'
        ):
            return source_route
        external_execution = (
            response_runtime.get('external_execution')
            if isinstance(response_runtime.get('external_execution'), Mapping)
            else {}
        )
        external_phase_policy = (
            response_runtime.get('external_phase_execution_policy')
            if isinstance(
                response_runtime.get('external_phase_execution_policy'),
                Mapping,
            )
            else {}
        )
        working_frame = (
            response_payload.get('working_frame')
            if isinstance(response_payload, Mapping)
            and isinstance(response_payload.get('working_frame'), Mapping)
            else {}
        )
        working_target = (
            working_frame.get('target')
            if isinstance(working_frame.get('target'), Mapping)
            else {}
        )
        response_frame = (
            response_payload.get('response_frame')
            if isinstance(response_payload, Mapping)
            and isinstance(response_payload.get('response_frame'), Mapping)
            else {}
        )
        if not working_target:
            frame_working_frame = (
                response_frame.get('working_frame')
                if isinstance(response_frame.get('working_frame'), Mapping)
                else {}
            )
            working_target = (
                frame_working_frame.get('target')
                if isinstance(frame_working_frame.get('target'), Mapping)
                else response_frame.get('target')
                if isinstance(response_frame.get('target'), Mapping)
                else {}
            )
        external_target_id = str(
            external_target.get('instance_id')
            or external_target.get('id')
            or ''
        ).strip()
        execution_target_id = str(
            external_execution.get('target_id') or ''
        ).strip()
        working_target_id = str(
            working_target.get('instance_id')
            or working_target.get('id')
            or ''
        ).strip()
        if (
            not external_target_id
            or execution_target_id != external_target_id
            or working_target_id != external_target_id
            or str(external_execution.get('status') or '').strip().lower()
            != 'completed'
            or str(external_phase_policy.get('status') or '')
            .strip()
            .lower()
            != 'bounded'
            or str(
                external_phase_policy.get('materialization_authority') or ''
            ).strip()
            != 'fruth_runtime'
            or str(
                external_phase_policy.get('root_request_authority') or ''
            ).strip()
            != 'promoted_context_reference_only'
            or str(working_target.get('capability') or '').strip().lower()
            != 'chat'
            or str(working_target.get('mode') or '').strip().lower()
            != 'external_chat'
        ):
            return source_route
        route_runtime = (
            dict(source_route.get('route_runtime') or {})
            if isinstance(source_route.get('route_runtime'), Mapping)
            else {}
        )
        for key in (
            'external_target',
            'external_execution',
            'external_phase_execution_policy',
        ):
            if key in route_runtime:
                continue
            value = response_runtime.get(key)
            if isinstance(value, Mapping) and value:
                route_runtime[key] = dict(value)
        if route_runtime:
            source_route['route_runtime'] = route_runtime
            source_route['working_frame'] = {
                'target': dict(working_target),
            }
        return source_route

    def resolve_late_fill_route(
        self,
        request_payload: dict[str, Any],
        *,
        expected_capability: str,
        failed_instance_id: Optional[str],
        excluded_instance_ids: Optional[list[str]] = None,
        artifact_gap: Optional[dict[str, Any]] = None,
        source_route_payload: Optional[dict[str, Any]] = None,
        resolve_inference_auto_route: Optional[Callable[..., tuple[Optional[dict[str, Any]], Optional[str]]]] = None,
        load_running_instances: Optional[Callable[[], list[dict[str, Any]]]] = None,
        merge_instances_with_runtime_status: Optional[Callable[..., list[dict[str, Any]]]] = None,
    ) -> tuple[dict[str, Any], Optional[dict[str, Any]], Optional[str]]:
        resolve_auto_route = resolve_inference_auto_route or self.resolve_inference_auto_route
        load_instances = load_running_instances or self.load_running_instances
        merge_instances = merge_instances_with_runtime_status or self.merge_instances_with_runtime_status
        late_fill_payload = dict(request_payload or {})
        resolved_excluded_instance_ids = []
        for item in [
            *(excluded_instance_ids if isinstance(excluded_instance_ids, list) else []),
            failed_instance_id,
        ]:
            token = str(item or '').strip()
            if token and token not in resolved_excluded_instance_ids:
                resolved_excluded_instance_ids.append(token)
        artifact_gap_payload = artifact_gap if isinstance(artifact_gap, dict) else {}
        late_fill_trigger = str(artifact_gap_payload.get('trigger') or '').strip().lower()
        phase_continuation = (
            self.normalize_capability(expected_capability) is not None
            and late_fill_trigger == 'execution_planner_deferred_follow_up'
        )
        normalized_expected_capability = self.normalize_capability(
            expected_capability
        )
        source_route = (
            source_route_payload
            if isinstance(source_route_payload, dict)
            else {}
        )
        source_external_instance_id, source_external_descriptor = (
            self._source_route_external_target_identity(source_route)
        )
        execution_contract = (
            artifact_gap_payload.get('execution_contract')
            if isinstance(
                artifact_gap_payload.get('execution_contract'),
                Mapping,
            )
            else {}
        )
        graph_branch_id = str(
            execution_contract.get('branch_id')
            or artifact_gap_payload.get('branch_id')
            or ''
        ).strip()
        graph_phase_id = str(
            execution_contract.get('phase_id')
            or artifact_gap_payload.get('phase_id')
            or ''
        ).strip()
        selected_external_graph_chat = bool(
            normalized_expected_capability == 'chat'
            and execution_contract
            and (graph_branch_id or graph_phase_id)
            and source_external_instance_id
            and source_external_instance_id
            not in resolved_excluded_instance_ids
            and source_external_descriptor
            and callable(self.load_external_targets)
        )
        current_external_target: dict[str, Any] = {}
        if selected_external_graph_chat:
            try:
                current_external_target = next(
                    (
                        dict(item)
                        for item in (self.load_external_targets() or [])
                        if isinstance(item, Mapping)
                        and str(
                            item.get('instance_id') or item.get('id') or ''
                        ).strip()
                        == source_external_instance_id
                    ),
                    {},
                )
            except Exception as exc:  # noqa: BLE001
                logging.info(
                    'Could not refresh selected external chat target %s: %s',
                    source_external_instance_id,
                    exc,
                )
        if (
            current_external_target
            and current_external_target.get('available') is True
            and current_external_target.get('enabled') is True
            and current_external_target.get('selectable') is True
            and self.instance_supports_capability(
                current_external_target,
                expected_capability,
            )
        ):
            route_source = (
                'phase_continuation'
                if phase_continuation
                else 'late_fill'
            )
            route_reason = (
                'Selected external chat provider continued one graph-owned '
                'branch under Fruth materialization authority.'
            )
            candidate_diagnostic = {
                'instance_id': source_external_instance_id,
                'capability': 'chat',
                'backend': str(
                    current_external_target.get('backend') or ''
                ).strip()
                or None,
                'model': str(
                    current_external_target.get('model') or ''
                ).strip()
                or None,
                'target_kind': 'external',
                'supports_expected_capability': True,
                'excluded': False,
                'usable': True,
                'selected': True,
                'readiness': str(
                    current_external_target.get('readiness') or ''
                ).strip()
                or None,
            }
            candidate_diagnostic = {
                key: value
                for key, value in candidate_diagnostic.items()
                if value not in (None, '', [], {})
            }
            route_runtime_seed = {
                **source_route,
                'route_source': route_source,
                'route_reason': route_reason,
                'capability': 'chat',
                'instance_id': source_external_instance_id,
                'instance': current_external_target,
                'selection_policy': (
                    'selected_external_provider_for_graph_chat_phase'
                ),
                'root_request_authority': (
                    'promoted_context_reference_only'
                ),
                'materialization_authority': 'fruth_runtime',
                'excluded_instance_ids': list(
                    resolved_excluded_instance_ids
                ),
                'candidate_diagnostics': [candidate_diagnostic],
            }
            route_runtime = self.merge_request_meta_runtime_truth(
                {},
                late_fill_payload,
                route_payload=route_runtime_seed,
            )
            route_runtime.update(
                {
                    'selection_policy': (
                        'selected_external_provider_for_graph_chat_phase'
                    ),
                    'root_request_authority': (
                        'promoted_context_reference_only'
                    ),
                    'materialization_authority': 'fruth_runtime',
                    'excluded_instance_ids': list(
                        resolved_excluded_instance_ids
                    ),
                    'candidate_diagnostics': [candidate_diagnostic],
                }
            )
            continuation_diagnostic = {
                'active': True,
                'trigger': late_fill_trigger,
                'expected_capability': 'chat',
                'branch_id': graph_branch_id or None,
                'phase_id': graph_phase_id or None,
            }
            route_runtime[
                'phase_continuation'
                if phase_continuation
                else 'graph_chat_continuation'
            ] = continuation_diagnostic
            route_info = {
                'instance_id': source_external_instance_id,
                'instance': current_external_target,
                'capability': 'chat',
                'route_source': route_source,
                'route_reason': route_reason,
                'route_confidence': 1.0,
                'route_reuse_last_artifact': False,
                'route_runtime': route_runtime,
            }
            request_meta = (
                route_runtime.get('request_meta')
                if isinstance(route_runtime.get('request_meta'), dict)
                else {}
            )
            if request_meta:
                route_info['request_meta'] = request_meta
            return late_fill_payload, route_info, None
        if self.parse_bool(late_fill_payload.get('inference_route'), default=False) and not phase_continuation:
            route_info, resolution_error = resolve_auto_route(
                late_fill_payload,
                excluded_instance_ids=resolved_excluded_instance_ids,
            )
            if route_info and self.normalize_capability(route_info.get('capability')) == self.normalize_capability(expected_capability):
                route_instance = (
                    route_info.get('instance')
                    if isinstance(route_info.get('instance'), Mapping)
                    else {}
                )
                if not route_instance or _late_fill_instance_is_usable(
                    route_instance,
                    capability=expected_capability,
                ):
                    return late_fill_payload, route_info, None
                logging.info(
                    'Late fill auto-route fallback: selected instance %s is not usable.',
                    route_info.get('instance_id'),
                )
            if resolution_error:
                logging.info('Late fill auto-route fallback: %s', resolution_error)

        runtime_candidate_snapshot = (
            artifact_gap_payload.get('_runtime_candidate_snapshot')
            if isinstance(artifact_gap_payload.get('_runtime_candidate_snapshot'), list)
            else []
        )
        if runtime_candidate_snapshot:
            instances = [
                dict(entry)
                for entry in runtime_candidate_snapshot
                if isinstance(entry, Mapping)
            ]
            candidate_snapshot_meta = self._runtime_candidate_snapshot_meta(
                instances,
                source='late_fill_wave',
            )
        else:
            instances = merge_instances(
                load_instances(),
                path=self.runtime_status_path_getter(),
                refresh=True,
            )
            candidate_snapshot_meta = self._runtime_candidate_snapshot_meta(
                [
                    dict(entry)
                    for entry in (instances or [])
                    if isinstance(entry, Mapping)
                ],
                source='per_branch_refresh',
            )
        used_runtime_candidate_snapshot = bool(runtime_candidate_snapshot)
        explicit_image_retry_policy_eligible = bool(
            normalized_expected_capability == self.capability_image_generation
            and self._artifact_gap_allows_excluded_candidate_reuse_for_explicit_image_retry(
                artifact_gap_payload
            )
        )

        def refresh_snapshot_candidates_from_live_truth(reason: str) -> bool:
            nonlocal instances, candidate_snapshot_meta
            if not used_runtime_candidate_snapshot:
                return False
            try:
                live_instances = merge_instances(
                    load_instances(),
                    path=self.runtime_status_path_getter(),
                    refresh=True,
                )
            except Exception as exc:  # noqa: BLE001
                logging.info('Late-fill live candidate refresh failed after %s: %s', reason, exc)
                late_fill_payload['_late_fill_route_candidate_refresh'] = {
                    'attempted': True,
                    'applied': False,
                    'reason': str(reason or '').strip(),
                    'error': str(exc),
                }
                return False

            if reason in {
                'snapshot_tts_recovery_requires_live_alternative_check',
                'snapshot_explicit_image_retry_requires_live_pool_check',
            }:
                instances = [
                    dict(entry)
                    for entry in (live_instances or [])
                    if isinstance(entry, Mapping)
                ]
                candidate_snapshot_meta = self._runtime_candidate_snapshot_meta(
                    instances,
                    source=(
                        'per_branch_refresh_for_explicit_image_retry'
                        if reason == 'snapshot_explicit_image_retry_requires_live_pool_check'
                        else 'per_branch_refresh_for_tts_recovery'
                    ),
                )
                candidate_snapshot_meta['refresh_reason'] = str(reason or '').strip()
                candidate_snapshot_meta['snapshot_candidate_count'] = len(runtime_candidate_snapshot)
                candidate_snapshot_meta['live_candidate_count'] = len(instances)
                late_fill_payload['_late_fill_route_candidate_refresh'] = {
                    'attempted': True,
                    'applied': True,
                    'reason': str(reason or '').strip(),
                    'snapshot_candidate_count': len(runtime_candidate_snapshot),
                    'live_candidate_count': len(instances),
                    'candidate_count': len(instances),
                }
                return True

            combined: list[dict[str, Any]] = []
            seen: set[str] = set()
            for entry in [*(instances or []), *(live_instances or [])]:
                if not isinstance(entry, Mapping):
                    continue
                item = dict(entry)
                instance_id = str(item.get('instance_id') or '').strip()
                dedupe_key = instance_id or f'candidate-{len(combined)}'
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                combined.append(item)
            if len(combined) <= len(instances or []):
                late_fill_payload['_late_fill_route_candidate_refresh'] = {
                    'attempted': True,
                    'applied': False,
                    'reason': str(reason or '').strip(),
                    'live_candidate_count': len(live_instances or []),
                    'candidate_count': len(instances or []),
                }
                return False

            instances = combined
            candidate_snapshot_meta = self._runtime_candidate_snapshot_meta(
                [
                    dict(entry)
                    for entry in combined
                    if isinstance(entry, Mapping)
                ],
                source='late_fill_wave_plus_per_branch_refresh',
            )
            candidate_snapshot_meta['refresh_reason'] = str(reason or '').strip()
            candidate_snapshot_meta['snapshot_candidate_count'] = len(runtime_candidate_snapshot)
            candidate_snapshot_meta['live_candidate_count'] = len(live_instances or [])
            late_fill_payload['_late_fill_route_candidate_refresh'] = {
                'attempted': True,
                'applied': True,
                'reason': str(reason or '').strip(),
                'snapshot_candidate_count': len(runtime_candidate_snapshot),
                'live_candidate_count': len(live_instances or []),
                'combined_candidate_count': len(combined),
            }
            return True

        def build_candidate_diagnostics(
            entries: list[dict[str, Any]],
            *,
            selected_instance_id: str = '',
            reused_excluded_instance_id: str = '',
        ) -> list[dict[str, Any]]:
            diagnostics: list[dict[str, Any]] = []
            for entry in entries[:12]:
                instance_id = str(entry.get('instance_id') or '').strip()
                if not instance_id:
                    continue
                supports = self.instance_supports_capability(entry, expected_capability)
                excluded = instance_id in resolved_excluded_instance_ids
                excluded_reuse_applied = bool(
                    excluded
                    and reused_excluded_instance_id
                    and instance_id == reused_excluded_instance_id
                )
                usable = bool(
                    supports
                    and (not excluded or excluded_reuse_applied)
                    and _late_fill_instance_is_usable(entry, capability=expected_capability)
                )
                rejection_reasons: list[str] = []
                if not supports:
                    rejection_reasons.append('capability_mismatch')
                if excluded and not excluded_reuse_applied:
                    rejection_reasons.append('excluded_instance')
                if supports and not _late_fill_instance_is_usable(entry, capability=expected_capability):
                    rejection_reasons.append('not_ready')
                item = {
                    'instance_id': instance_id,
                    'capability': self.normalize_capability(entry.get('capability')) or str(entry.get('capability') or '').strip() or None,
                    'backend': self.normalize_backend(entry.get('backend')) or str(entry.get('backend') or '').strip() or None,
                    'model': str(entry.get('model') or entry.get('modelName') or '').strip() or None,
                    'supports_expected_capability': supports,
                    'excluded': excluded,
                    'excluded_reuse_applied': excluded_reuse_applied,
                    'usable': usable,
                    'selected': bool(selected_instance_id and instance_id == selected_instance_id),
                    'readiness': str(
                        (entry.get('runtime_status') or {}).get('readiness')
                        if isinstance(entry.get('runtime_status'), Mapping)
                        else entry.get('readiness') or ''
                    ).strip() or None,
                    'activity': str(
                        (entry.get('runtime_status') or {}).get('activity')
                        if isinstance(entry.get('runtime_status'), Mapping)
                        else entry.get('activity') or ''
                    ).strip() or None,
                    'rejection_reasons': rejection_reasons,
                }
                diagnostics.append(
                    {
                        key: value
                        for key, value in item.items()
                        if value not in (None, '', [], {})
                    }
                )
            return diagnostics

        def attach_route_diagnostics(message: str) -> str:
            late_fill_payload['_late_fill_route_diagnostics'] = {
                'expected_capability': normalized_expected_capability or str(expected_capability or '').strip(),
                'excluded_instance_ids': list(resolved_excluded_instance_ids),
                'candidate_count': len(instances or []),
                'candidate_diagnostics': build_candidate_diagnostics(
                    [
                        dict(entry)
                        for entry in (instances or [])
                        if isinstance(entry, dict)
                    ]
                ),
                'message': str(message or '').strip(),
            }
            return message

        def compute_candidate_pools() -> tuple[
            list[dict[str, Any]],
            list[dict[str, Any]],
            int,
            bool,
            bool,
            bool,
            list[dict[str, Any]],
            list[dict[str, Any]],
        ]:
            all_items = [
                entry
                for entry in instances
                if isinstance(entry, dict)
                and self.instance_supports_capability(entry, expected_capability)
            ]
            filtered_items = [
                entry
                for entry in all_items
                if str(entry.get('instance_id') or '').strip() not in resolved_excluded_instance_ids
            ]
            usable_compatible_items = [
                entry
                for entry in all_items
                if _late_fill_instance_is_usable(entry, capability=expected_capability)
            ]
            usable_nonexcluded_items = [
                entry
                for entry in usable_compatible_items
                if str(entry.get('instance_id') or '').strip() not in resolved_excluded_instance_ids
            ]
            excluded_count = sum(
                1
                for entry in all_items
                if str(entry.get('instance_id') or '').strip() in resolved_excluded_instance_ids
            )
            reuse_excluded_for_text_repair = bool(
                resolved_excluded_instance_ids
                and not filtered_items
                and self._artifact_gap_allows_excluded_candidate_reuse_for_text_repair(artifact_gap_payload)
            )
            sole_usable_candidate_id = (
                str(usable_compatible_items[0].get('instance_id') or '').strip()
                if len(usable_compatible_items) == 1
                else ''
            )
            recovery_attempt = (
                artifact_gap_payload.get('recovery_attempt')
                if isinstance(artifact_gap_payload.get('recovery_attempt'), Mapping)
                else {}
            )
            recovery_failed_instance_id = str(
                recovery_attempt.get('failed_instance_id') or ''
            ).strip()
            reuse_excluded_for_tts_recovery = bool(
                normalized_expected_capability == self.capability_text_to_speech
                and resolved_excluded_instance_ids
                and not usable_nonexcluded_items
                and len(usable_compatible_items) == 1
                and sole_usable_candidate_id
                and sole_usable_candidate_id == str(failed_instance_id or '').strip()
                and sole_usable_candidate_id == recovery_failed_instance_id
                and sole_usable_candidate_id in resolved_excluded_instance_ids
                and self._artifact_gap_allows_excluded_candidate_reuse_for_tts_recovery(
                    artifact_gap_payload
                )
            )
            reuse_excluded_for_explicit_image_retry = bool(
                normalized_expected_capability == self.capability_image_generation
                and resolved_excluded_instance_ids
                and usable_compatible_items
                and not usable_nonexcluded_items
                and all(
                    str(entry.get('instance_id') or '').strip()
                    in resolved_excluded_instance_ids
                    for entry in usable_compatible_items
                )
                and self._artifact_gap_allows_excluded_candidate_reuse_for_explicit_image_retry(
                    artifact_gap_payload
                )
            )
            base_items = (
                all_items
                if (
                    reuse_excluded_for_text_repair
                    or reuse_excluded_for_tts_recovery
                    or reuse_excluded_for_explicit_image_retry
                )
                else filtered_items
                if resolved_excluded_instance_ids
                else all_items
            )
            usable_items = [
                entry
                for entry in base_items
                if _late_fill_instance_is_usable(entry, capability=expected_capability)
            ]
            usable_items = sorted(
                usable_items,
                key=lambda entry: runtime_instance_score(entry, capability=expected_capability),
                reverse=True,
            )
            return (
                all_items,
                filtered_items,
                excluded_count,
                reuse_excluded_for_text_repair,
                reuse_excluded_for_tts_recovery,
                reuse_excluded_for_explicit_image_retry,
                base_items,
                usable_items,
            )

        (
            all_candidates,
            filtered_candidates,
            excluded_candidate_count,
            reuse_excluded_candidates_for_text_repair,
            reuse_excluded_candidate_for_tts_recovery,
            reuse_excluded_candidates_for_explicit_image_retry,
            base_candidates,
            usable_candidates,
        ) = compute_candidate_pools()
        refresh_reason = ''
        if explicit_image_retry_policy_eligible and used_runtime_candidate_snapshot:
            refresh_reason = 'snapshot_explicit_image_retry_requires_live_pool_check'
        elif reuse_excluded_candidate_for_tts_recovery and used_runtime_candidate_snapshot:
            refresh_reason = 'snapshot_tts_recovery_requires_live_alternative_check'
        elif not all_candidates:
            refresh_reason = 'snapshot_missing_expected_capability'
        elif resolved_excluded_instance_ids and not filtered_candidates and not reuse_excluded_candidates_for_text_repair:
            refresh_reason = 'snapshot_candidates_excluded'
        elif base_candidates and not usable_candidates:
            refresh_reason = 'snapshot_candidates_not_usable'
        if refresh_reason:
            refreshed_candidates = refresh_snapshot_candidates_from_live_truth(refresh_reason)
            if refreshed_candidates:
                (
                    all_candidates,
                    filtered_candidates,
                    excluded_candidate_count,
                    reuse_excluded_candidates_for_text_repair,
                    reuse_excluded_candidate_for_tts_recovery,
                    reuse_excluded_candidates_for_explicit_image_retry,
                    base_candidates,
                    usable_candidates,
                ) = compute_candidate_pools()
            elif refresh_reason in {
                'snapshot_tts_recovery_requires_live_alternative_check',
                'snapshot_explicit_image_retry_requires_live_pool_check',
            }:
                reuse_excluded_candidate_for_tts_recovery = False
                reuse_excluded_candidates_for_explicit_image_retry = False
                base_candidates = list(filtered_candidates)
                usable_candidates = [
                    entry
                    for entry in base_candidates
                    if _late_fill_instance_is_usable(entry, capability=expected_capability)
                ]
        if not all_candidates:
            return late_fill_payload, None, attach_route_diagnostics(
                f"No running instance for late fill capability '{expected_capability}'."
            )
        if base_candidates and not usable_candidates:
            unusable_text = ', '.join(
                _late_fill_instance_unusable_summary(entry, capability=expected_capability)
                for entry in base_candidates
            )
            message = attach_route_diagnostics(
                f"No ready late-fill instance for capability '{expected_capability}'. "
                f"Unusable instance ids: {unusable_text}."
            )
            temporary_candidates = []
            for entry in base_candidates:
                liveness = runtime_instance_liveness(entry, capability=expected_capability)
                if (
                    liveness['fresh_cooldown']
                    and not liveness['hard_unavailable']
                    and liveness['process_alive'] is True
                    and liveness['port_listening'] is True
                ):
                    temporary_candidates.append((entry, liveness))
            if temporary_candidates:
                late_fill_payload['_late_fill_route_diagnostics']['availability_wait'] = {
                    'reason': 'live_candidates_in_cooldown',
                    'candidate_instance_ids': [
                        str(entry.get('instance_id') or '') for entry, _ in temporary_candidates
                    ],
                    'cooldown_until': min(item['cooldown_until'] for _, item in temporary_candidates),
                }
            return late_fill_payload, None, message
        candidates = LateFillSelection._prefer_non_mlx_vlm_for_required_text_candidates(
            usable_candidates,
            artifact_gap_payload,
        )
        candidates = LateFillSelection._prefer_lightweight_chat_for_required_text_candidates(
            candidates,
            artifact_gap_payload,
            source_route_payload,
        )
        if not candidates:
            excluded_text = ', '.join(resolved_excluded_instance_ids)
            return (
                late_fill_payload,
                None,
                attach_route_diagnostics(
                    f"No non-excluded running instance for late fill capability '{expected_capability}'. "
                    f"Excluded instance ids: {excluded_text}."
                ),
            )
        prompt = self.extract_responses_prompt(late_fill_payload)
        spread_retry_preferred_ids = [
            str(item or '').strip()
            for item in artifact_gap_payload.get('_spread_retry_preferred_instance_ids') or []
            if str(item or '').strip()
        ]
        selected_via_spread_retry = ''
        if spread_retry_preferred_ids:
            candidate_ids = {
                str(entry.get('instance_id') or '').strip()
                for entry in candidates
                if str(entry.get('instance_id') or '').strip()
            }
            for instance_id in spread_retry_preferred_ids:
                if instance_id in candidate_ids:
                    selected_via_spread_retry = instance_id
                    break
        selected_instance_id = (
            selected_via_spread_retry
            or self.pick_prompt_preferred_instance(candidates, prompt)
            or self.pick_default_capability_instance(candidates)
            or ''
        )
        if not selected_instance_id:
            return late_fill_payload, None, attach_route_diagnostics(
                f"No selectable instance for late fill capability '{expected_capability}'."
            )
        selected_instance = next(
            (entry for entry in candidates if str(entry.get('instance_id') or '').strip() == selected_instance_id),
            None,
        )
        if not selected_instance:
            return late_fill_payload, None, attach_route_diagnostics(
                f"Late-fill instance '{selected_instance_id}' could not be resolved."
            )
        tts_recovery_attempt = (
            artifact_gap_payload.get('recovery_attempt')
            if isinstance(
                artifact_gap_payload.get('recovery_attempt'),
                Mapping,
            )
            else {}
        )
        tts_recovery_trigger = str(
            tts_recovery_attempt.get('trigger') or ''
        ).strip().lower()
        bounded_tts_recovery = (
            self._artifact_gap_allows_excluded_candidate_reuse_for_tts_recovery(
                artifact_gap_payload
            )
        )
        route_source = 'phase_continuation' if phase_continuation else 'late_fill'
        route_reason = (
            f'phase continuation materialized deferred {self.normalize_capability(expected_capability)} after current phase completion'
            if phase_continuation
            else f'late artifact fill continued closed chat completion as {self.normalize_capability(expected_capability)}'
        )
        route_runtime_seed = {
            **source_route,
            'route_source': route_source,
            'route_reason': route_reason,
            'capability': self.normalize_capability(expected_capability),
            'instance_id': selected_instance_id,
            'instance': selected_instance,
            'excluded_instance_ids': resolved_excluded_instance_ids,
            'excluded_candidate_count': excluded_candidate_count,
            'runtime_candidate_snapshot': candidate_snapshot_meta,
            'candidate_diagnostics': build_candidate_diagnostics(
                [
                    dict(entry)
                    for entry in (instances or [])
                    if isinstance(entry, dict)
                ],
                selected_instance_id=selected_instance_id,
                reused_excluded_instance_id=(
                    selected_instance_id
                    if (
                        reuse_excluded_candidates_for_text_repair
                        or reuse_excluded_candidate_for_tts_recovery
                        or reuse_excluded_candidates_for_explicit_image_retry
                    )
                    else ''
                ),
            ),
        }
        if reuse_excluded_candidates_for_text_repair:
            route_runtime_seed['selection_policy'] = 'excluded_reuse_for_authoritative_text_repair'
            route_runtime_seed['excluded_instance_reuse_reason'] = (
                'auto_executable_text_repair_candidate_pool_exhausted'
            )
        if selected_via_spread_retry:
            route_runtime_seed['selection_policy'] = 'spread_retry_preferred_instance'
            route_runtime_seed['spread_retry_reason'] = str(
                artifact_gap_payload.get('_spread_retry_reason') or 'internal_reservation_exhausted'
            ).strip()
            route_runtime_seed['spread_retry_preferred_instance_ids'] = list(spread_retry_preferred_ids)
        if (
            bounded_tts_recovery
            and not reuse_excluded_candidate_for_tts_recovery
            and selected_instance_id not in resolved_excluded_instance_ids
        ):
            route_runtime_seed['selection_policy'] = (
                'nonexcluded_alternative_for_tts_recovery'
            )
            route_runtime_seed['tts_recovery_trigger'] = (
                tts_recovery_trigger
            )
            route_runtime_seed['tts_recovery_policy_id'] = str(
                tts_recovery_attempt.get('recovery_policy_id') or ''
            ).strip() or None
        if reuse_excluded_candidate_for_tts_recovery:
            route_runtime_seed['selection_policy'] = 'excluded_reuse_for_single_tts_recovery'
            route_runtime_seed['excluded_instance_reuse_reason'] = (
                'bounded_auto_retry_single_compatible_tts_instance'
                if tts_recovery_trigger
                == _TTS_AUTO_RECOVERY_TRIGGER
                else 'explicit_retry_single_compatible_tts_instance'
            )
            route_runtime_seed['excluded_instance_reuse_instance_id'] = selected_instance_id
            route_runtime_seed['excluded_instance_reuse_recovery_trigger'] = (
                tts_recovery_trigger
            )
            route_runtime_seed['tts_recovery_policy_id'] = str(
                tts_recovery_attempt.get('recovery_policy_id') or ''
            ).strip() or None
            logging.info(
                'Late-fill TTS recovery is reusing sole compatible excluded instance %s '
                'for branch %s after live candidate refresh.',
                selected_instance_id,
                artifact_gap_payload.get('branch_id'),
            )
        if reuse_excluded_candidates_for_explicit_image_retry:
            route_runtime_seed['selection_policy'] = (
                'excluded_reuse_for_explicit_image_retry'
            )
            route_runtime_seed['excluded_instance_reuse_reason'] = (
                'user_triggered_retry_after_ready_image_pool_exhausted'
            )
            route_runtime_seed['excluded_instance_reuse_instance_id'] = (
                selected_instance_id
            )
            route_runtime_seed['excluded_instance_reuse_recovery_trigger'] = (
                'explicit_retry_endpoint'
            )
            route_runtime_seed['excluded_reuse_policy_id'] = (
                EXPLICIT_IMAGE_EXCLUDED_POOL_RETRY_POLICY_ID
            )
        route_runtime = self.merge_request_meta_runtime_truth({}, late_fill_payload, route_payload=route_runtime_seed)
        route_runtime['runtime_candidate_snapshot'] = dict(candidate_snapshot_meta)
        route_runtime['candidate_diagnostics'] = list(route_runtime_seed.get('candidate_diagnostics') or [])
        if reuse_excluded_candidate_for_tts_recovery:
            route_runtime['selection_policy'] = 'excluded_reuse_for_single_tts_recovery'
            route_runtime['excluded_instance_reuse_reason'] = str(
                route_runtime_seed.get('excluded_instance_reuse_reason') or ''
            ).strip()
            route_runtime['excluded_instance_reuse_instance_id'] = selected_instance_id
            route_runtime['excluded_instance_reuse_recovery_trigger'] = (
                tts_recovery_trigger
            )
            route_runtime['tts_recovery_policy_id'] = str(
                route_runtime_seed.get('tts_recovery_policy_id') or ''
            ).strip() or None
        elif reuse_excluded_candidates_for_explicit_image_retry:
            route_runtime['selection_policy'] = (
                'excluded_reuse_for_explicit_image_retry'
            )
            route_runtime['excluded_instance_reuse_reason'] = str(
                route_runtime_seed.get('excluded_instance_reuse_reason') or ''
            ).strip()
            route_runtime['excluded_instance_reuse_instance_id'] = (
                selected_instance_id
            )
            route_runtime['excluded_instance_reuse_recovery_trigger'] = (
                'explicit_retry_endpoint'
            )
            route_runtime['excluded_reuse_policy_id'] = (
                EXPLICIT_IMAGE_EXCLUDED_POOL_RETRY_POLICY_ID
            )
        elif selected_via_spread_retry:
            route_runtime['selection_policy'] = 'spread_retry_preferred_instance'
            route_runtime['spread_retry_reason'] = str(route_runtime_seed.get('spread_retry_reason') or '').strip()
            route_runtime['spread_retry_preferred_instance_ids'] = list(spread_retry_preferred_ids)
        elif (
            bounded_tts_recovery
            and selected_instance_id not in resolved_excluded_instance_ids
        ):
            route_runtime['selection_policy'] = (
                'nonexcluded_alternative_for_tts_recovery'
            )
            route_runtime['tts_recovery_trigger'] = tts_recovery_trigger
            route_runtime['tts_recovery_policy_id'] = str(
                route_runtime_seed.get('tts_recovery_policy_id') or ''
            ).strip() or None
        elif reuse_excluded_candidates_for_text_repair:
            route_runtime['selection_policy'] = 'excluded_reuse_for_authoritative_text_repair'
            route_runtime['excluded_instance_reuse_reason'] = str(
                route_runtime_seed.get('excluded_instance_reuse_reason') or ''
            ).strip()
        if resolved_excluded_instance_ids:
            route_runtime['excluded_instance_ids'] = list(resolved_excluded_instance_ids)
            route_runtime['excluded_candidate_count'] = excluded_candidate_count
        request_meta = route_runtime.get('request_meta') if isinstance(route_runtime.get('request_meta'), dict) else {}
        if phase_continuation:
            route_runtime['phase_continuation'] = {
                'active': True,
                'trigger': late_fill_trigger,
                'expected_capability': self.normalize_capability(expected_capability),
            }
        route_info = {
            'instance_id': selected_instance_id,
            'instance': selected_instance,
            'capability': self.normalize_capability(expected_capability),
            'route_source': route_source,
            'route_reason': route_reason,
            'route_confidence': 1.0,
            'route_reuse_last_artifact': bool(source_route.get('route_reuse_last_artifact')),
            'route_artifact_ref': str(source_route.get('route_artifact_ref') or '').strip() or None,
            'route_artifact_path': str(source_route.get('route_artifact_path') or '').strip() or None,
            'route_runtime': route_runtime,
        }
        if request_meta:
            route_info['request_meta'] = request_meta
        return late_fill_payload, route_info, None

    def request_phase_graph_for_late_fill(
        self,
        *,
        route_payload: Optional[dict[str, Any]] = None,
        artifact_payload: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        def _overlay_runtime_phase_statuses(graph: dict[str, Any]) -> dict[str, Any]:
            phases = graph.get('phases')
            if not isinstance(phases, list):
                return graph
            payload = artifact_payload if isinstance(artifact_payload, dict) else {}
            late_fill = payload.get('late_fill') if isinstance(payload.get('late_fill'), dict) else {}
            completed_phase_ids: set[str] = set()
            failed_phase_ids: set[str] = set()
            current_phase_id = str(graph.get('current_phase_id') or '').strip()
            payload_status = str(payload.get('status') or '').strip().lower()
            if current_phase_id and payload_status in {'completed', 'failed', 'incomplete'}:
                completed_phase_ids.add(current_phase_id)
            for branch in (late_fill.get('completed_branches') or []):
                if not isinstance(branch, Mapping):
                    continue
                phase_id = str(branch.get('phase_id') or branch.get('branch_id') or '').strip()
                if phase_id:
                    completed_phase_ids.add(phase_id)
            for branch in (late_fill.get('failed_branches') or []):
                if not isinstance(branch, Mapping):
                    continue
                phase_id = str(branch.get('phase_id') or branch.get('branch_id') or '').strip()
                if phase_id:
                    failed_phase_ids.add(phase_id)
            for result in (late_fill.get('fill_results') or []):
                if not isinstance(result, Mapping):
                    continue
                if not branch_result_contracts.late_fill_result_has_missing_dependency_evidence(result):
                    continue
                phase_id = str(result.get('phase_id') or result.get('branch_id') or '').strip()
                if phase_id:
                    failed_phase_ids.add(phase_id)
                    completed_phase_ids.discard(phase_id)
            if not completed_phase_ids and not failed_phase_ids:
                return graph
            overlaid_phases: list[dict[str, Any]] = []
            for raw_phase in phases:
                if not isinstance(raw_phase, Mapping):
                    continue
                phase = dict(raw_phase)
                phase_id = str(phase.get('phase_id') or '').strip()
                if phase_id in failed_phase_ids:
                    phase['status'] = 'failed'
                elif phase_id in completed_phase_ids:
                    phase['status'] = 'completed'
                overlaid_phases.append(phase)
            return {
                **graph,
                'phases': overlaid_phases,
            }

        artifact_info = artifact_payload if isinstance(artifact_payload, dict) else {}
        artifact_runtime = artifact_info.get('runtime') if isinstance(artifact_info.get('runtime'), dict) else {}
        artifact_graph = (
            artifact_runtime.get('request_phase_graph')
            if isinstance(artifact_runtime.get('request_phase_graph'), dict)
            else {}
        )
        if artifact_graph:
            return _overlay_runtime_phase_statuses(dict(artifact_graph))
        route_info = route_payload if isinstance(route_payload, dict) else {}
        route_runtime = route_info.get('route_runtime') if isinstance(route_info.get('route_runtime'), dict) else {}
        route_graph = (
            route_runtime.get('request_phase_graph')
            if isinstance(route_runtime.get('request_phase_graph'), dict)
            else {}
        )
        return _overlay_runtime_phase_statuses(dict(route_graph)) if route_graph else {}

    @staticmethod
    def overlay_graph_branch_with_runtime_state(
        graph_branch: Mapping[str, Any],
        runtime_branch: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        """Overlay branch state without inheriting another branch's publication."""

        graph_payload = dict(graph_branch or {})
        runtime_payload = dict(runtime_branch or {})
        publication_fields = _BRANCH_LOCAL_PUBLICATION_FIELDS | {
            key for key in (*graph_payload.keys(), *runtime_payload.keys())
            if str(key).startswith('saved_')
        }
        explicit_publication = {
            key: runtime_payload[key]
            for key in publication_fields
            if key in runtime_payload and runtime_payload[key] not in (None, '', [], {})
        }
        for key in publication_fields:
            graph_payload.pop(key, None)
            runtime_payload.pop(key, None)
        graph_payload.update(runtime_payload)
        graph_payload.update(explicit_publication)
        return graph_payload

    _content_review_binding = staticmethod(BranchDependencyEvidence._content_review_binding)

    @staticmethod
    def _is_semantic_review_branch(*payloads: Mapping[str, Any]) -> bool:
        semantic_review_stages = {
            'run_global_semantic_closure_review',
            'run_branch_semantic_review',
        }
        for payload in payloads:
            if not isinstance(payload, Mapping):
                continue
            stage_direction = str(payload.get('stage_direction') or '').strip().lower()
            if stage_direction in semantic_review_stages:
                return True
            execution_contract = (
                payload.get('execution_contract')
                if isinstance(payload.get('execution_contract'), Mapping)
                else {}
            )
            if str(execution_contract.get('stage_direction') or '').strip().lower() in semantic_review_stages:
                return True
        return False

    @staticmethod
    def project_internal_semantic_review_result(
        infer_result: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Keep verdict text while preventing review output from becoming an artifact."""

        projected = dict(infer_result or {})
        publication_fields = _BRANCH_LOCAL_PUBLICATION_FIELDS | {
            key for key in projected if str(key).startswith('saved_')
        }
        for key in publication_fields:
            projected.pop(key, None)
        projected['visibility'] = 'internal'
        projected['surface_role'] = 'closure_evidence'
        for contract_key in ('execution_contract', 'output_contract'):
            contract = projected.get(contract_key)
            if not isinstance(contract, Mapping):
                continue
            projected_contract = dict(contract)
            projected_contract['visibility'] = 'internal'
            projected_contract['surface_role'] = 'closure_evidence'
            projected[contract_key] = projected_contract
        return projected

    _artifact_record_merge_key = staticmethod(branch_result_contracts._artifact_record_merge_key)

    _merge_artifact_record_fields = staticmethod(branch_result_contracts._merge_artifact_record_fields)

    _artifact_record_identity_signature = staticmethod(branch_result_contracts._artifact_record_identity_signature)

    _repair_artifact_record_identity = staticmethod(branch_result_contracts._repair_artifact_record_identity)

    _repair_colliding_artifact_record_identities = staticmethod(branch_result_contracts._repair_colliding_artifact_record_identities)

    merge_unique_artifact_records = staticmethod(branch_result_contracts.merge_unique_artifact_records)

    artifact_records_from_payload = staticmethod(branch_result_contracts.artifact_records_from_payload)

    merge_late_fill_payload_artifacts = staticmethod(branch_result_contracts.merge_late_fill_payload_artifacts)

    late_fill_text_from_result_payload = staticmethod(branch_result_contracts.late_fill_text_from_result_payload)

    late_fill_result_has_missing_dependency_evidence = staticmethod(branch_result_contracts.late_fill_result_has_missing_dependency_evidence)

    late_fill_branch_dependency_ids = staticmethod(branch_result_contracts.late_fill_branch_dependency_ids)

    tts_source_evidence_from_effective_data = staticmethod(TtsResultEvidence.tts_source_evidence_from_effective_data)

    tts_source_evidence_from_prepared_plan = staticmethod(TtsResultEvidence.tts_source_evidence_from_prepared_plan)

    def tts_audio_integrity_evidence_for_branch_result(
        self,
        branch: Mapping[str, Any],
        infer_result: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self.tts_result_evidence.tts_audio_integrity_evidence_for_branch_result(branch, infer_result)

    def tts_audio_integrity_error_for_branch_result(
        self,
        branch: Mapping[str, Any],
        infer_result: Mapping[str, Any],
    ) -> Optional[dict[str, Any]]:
        return self.tts_result_evidence.tts_audio_integrity_error_for_branch_result(branch, infer_result)

    _normalize_tts_stt_semantic_text = staticmethod(TtsResultEvidence._normalize_tts_stt_semantic_text)

    _tts_stt_similarity_metrics = staticmethod(TtsResultEvidence._tts_stt_similarity_metrics)

    def tts_stt_semantic_evidence_for_branch_result(
        self,
        branch: Mapping[str, Any],
        infer_result: Mapping[str, Any],
        *,
        current_payload: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        return self.tts_result_evidence.tts_stt_semantic_evidence_for_branch_result(branch, infer_result, current_payload=current_payload)

    @staticmethod
    def _valid_vision_input_receipt(receipt: Any) -> bool:
        return bool(
            isinstance(receipt, Mapping)
            and receipt.get('kind') == 'fruth.vision_input_evidence'
            and receipt.get('version') == 1
            and receipt.get('authority') == 'runtime_vision_image_dispatch'
            and receipt.get('status') == 'supplied'
            and receipt.get('instance_id')
            and re.fullmatch(r'[0-9a-f]{64}', str(receipt.get('image_sha256') or ''))
            and type(receipt.get('size_bytes')) is int
            and receipt['size_bytes'] > 0
        )

    def _vision_image_snapshot(self, value: Any) -> dict[str, Any]:
        try:
            path = self.resolve_saved_file_input_path(str(value or ''))
            if path is None or not Path(path).is_file():
                return {}
            path = Path(path).resolve()
            with path.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            return {'path': str(path), 'image_sha256': digest, 'size_bytes': path.stat().st_size}
        except (OSError, ValueError):
            return {}

    def _vision_direct_image_binding(
        self, branch: Mapping[str, Any], payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Resolve one completed producer; never recover an input by recency."""
        if self.branch_capability(branch) != 'vision_analysis' or not payload.get('id'):
            return {}
        dependencies = branch_result_contracts.late_fill_branch_dependency_ids(branch, current_payload=payload)
        late_fill = payload.get('late_fill') or {}
        producers = [item for item in late_fill.get('fill_results') or []
                     if isinstance(item, Mapping)
                     and {item.get('branch_id'), item.get('phase_id')}.intersection(dependencies)
                     and item.get('capability') == self.capability_image_generation]
        if len(producers) != 1:
            return {}
        producer = producers[0]
        if producer.get('error') or not producer.get('branch_id') or not producer.get('phase_id'):
            return {}
        if set(dependencies).difference({producer['branch_id'], producer['phase_id']}):
            return {}
        completed = [item for item in late_fill.get('completed_branches') or []
                     if isinstance(item, Mapping)
                     and item.get('branch_id') == producer['branch_id']
                     and item.get('phase_id') == producer['phase_id']]
        if len(completed) != 1 or completed[0].get('status') not in {'completed', 'fulfilled'}:
            return {}
        snapshot = self._vision_image_snapshot(producer.get('saved_image_path'))
        if not snapshot:
            return {}
        for artifact in producer.get('artifacts') or []:
            if not isinstance(artifact, Mapping):
                continue
            if str(artifact.get('path') or '') != str(producer.get('saved_image_path') or ''):
                continue
            metadata = artifact.get('metadata') if isinstance(artifact.get('metadata'), Mapping) else {}
            for source in (artifact, metadata):
                if source.get('file_sha256') and source['file_sha256'] != snapshot['image_sha256']:
                    return {}
        return {
            'artifact': snapshot,
            'producer_branch_id': producer['branch_id'],
            'producer_phase_id': producer['phase_id'],
            'depends_on': dependencies,
        }

    def _vision_evidence_failure(
        self, branch: Mapping[str, Any], result: Mapping[str, Any],
        current_payload: Optional[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Prove supplied direct-producer bytes before allowing output recovery."""
        payload = current_payload if isinstance(current_payload, Mapping) else {}
        receipt = result.get('vision_input_evidence')
        if (not self._valid_vision_input_receipt(receipt)
                or receipt.get('response_id') != payload.get('id')
                or receipt.get('branch_id') != self.branch_id(branch)
                or receipt.get('phase_id') != branch.get('phase_id')):
            return {}
        binding = self._vision_direct_image_binding(branch, payload)
        if not binding or any(binding['artifact'][k] != receipt.get(k) for k in ('image_sha256', 'size_bytes')):
            return {}
        return {
            **binding, 'policy_id': _VISION_EVIDENCE_RECOVERY_POLICY_ID,
            'input_evidence': dict(receipt),
            'rejected_text': branch_result_contracts.late_fill_text_from_result_payload(result),
        }

    def _has_generated_image_dependency(self, branch: Mapping[str, Any], payload: Mapping[str, Any]) -> bool:
        if self.branch_capability(branch) != 'vision_analysis':
            return False
        dependencies = set(branch_result_contracts.late_fill_branch_dependency_ids(branch, current_payload=payload))
        late = payload.get('late_fill') or {}
        graph = (payload.get('runtime') or {}).get('request_phase_graph') or {}
        return any(isinstance(item, Mapping) and item.get('capability') == self.capability_image_generation
                   and dependencies.intersection({item.get('branch_id'), item.get('phase_id')})
                   for key, owner in (('fill_results', late), ('completed_branches', late),
                                      ('downstream_branches', graph), ('phases', graph))
                   for item in owner.get(key) or [])

    def _prepared_vision_dependency(
        self, branch: Mapping[str, Any], payload: Mapping[str, Any],
        infer_payload: Mapping[str, Any], instance_id: str,
    ) -> dict[str, Any]:
        """Bind a generated input before dispatch without claiming it was supplied."""
        if not self._has_generated_image_dependency(branch, payload):
            return {}
        snapshot = self._vision_image_snapshot(infer_payload.get('file_path'))
        binding = self._vision_direct_image_binding(branch, payload)
        if not binding or snapshot != binding['artifact']:
            raise ValueError('Vision dependency input missing, changed or ambiguous.')
        binding.update(policy_id=_VISION_BACKEND_RECOVERY_POLICY_ID,
                       authority='runtime_prepared_vision_input', response_id=payload.get('id'),
                       branch_id=branch.get('branch_id'), phase_id=branch.get('phase_id'),
                       instance_id=instance_id)
        return binding

    def reconcile_completed_inline_outputs(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Refresh old retry slots only from an accepted, exact inline result.

        This runs on a state transition, never on a passive historical read.
        Completion markers alone and saved-file obligations are insufficient.
        """
        late = payload.get('late_fill') or {}
        graph = (payload.get('runtime') or {}).get('request_phase_graph') or {}
        refreshed = []
        for raw in payload.get('output_slots') or []:
            slot = dict(raw)
            identity = (slot.get('branch_id'), slot.get('phase_id'))
            def matches(record):
                return isinstance(record, Mapping) and all(identity) and identity == (
                    record.get('branch_id'), record.get('phase_id'))
            results = [r for r in late.get('fill_results') or [] if matches(r)]
            completed = [r for r in late.get('completed_branches') or [] if matches(r)]
            branches = [r for r in graph.get('downstream_branches') or [] if matches(r)]
            conflicting = any(matches(r) for key in (
                'failed_branches', 'cancelled_branches', 'pending_branches', 'active_branches')
                for r in late.get(key) or [])
            if (slot.get('type') == 'text' and len(results) == len(completed) == len(branches) == 1
                    and not conflicting and not results[0].get('error')
                    and completed[0].get('status') in {'fulfilled', 'completed'}
                    and slot.get('status') not in {'cancelled', 'waived', 'superseded', 'skipped'}
                    and not self.branch_selection._branch_is_required_text_artifact(branches[0])
                    and not any(source.get('requires_artifact') or source.get('artifact_request')
                                or source.get('text_artifact_requests') or source.get('target_extension')
                                or source.get('fulfillment_policy') == 'runtime_text_artifact'
                                for source in (branches[0], branches[0].get('output_contract') or {},
                                               results[0].get('execution_contract') or {}))
                    and not any(slot.get(k) or results[0].get(k) for k in (
                        'artifact_ref', 'artifact_path', 'saved_text_path', 'saved_text_artifacts'))):
                text = branch_result_contracts.late_fill_text_from_result_payload(results[0])
                if text:
                    slot.update(status='fulfilled', lifecycle='materialized_output', value=text)
                    for key in ('blocked_reason', 'error_ref', 'recovery_context', 'recovery_state', 'placeholder_ref'):
                        slot.pop(key, None)
            refreshed.append(slot)
        if refreshed:
            payload['output_slots'] = refreshed
        return payload

    def retry_dependency_continuations(
        self, payload: Mapping[str, Any], retries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Reconsider only never-dispatched consumers of this explicit retry wave.

        This does not repair a graph or certify its inputs. Ordinary dependency,
        execution and result gates still run after each prerequisite settles.
        """
        late = payload.get('late_fill') or {}
        graph = (payload.get('runtime') or {}).get('request_phase_graph') or {}
        graph_branches = graph.get('downstream_branches') or []
        candidates = list(late.get('failed_branches') or [])
        queued = list(retries)
        continuations = []
        while True:
            aliases = {item.get(key) for item in queued for key in ('branch_id', 'phase_id')
                       if item.get(key)}
            added = []
            for branch in candidates:
                if self.branch_id(branch) in aliases:
                    continue
                error = branch.get('error') or {}
                failed = error.get('failed_dependency_ids') or []
                dependencies = branch_result_contracts.late_fill_branch_dependency_ids(branch)
                matching = [b for b in graph_branches if b.get('branch_id') == branch.get('branch_id')
                            and b.get('phase_id') == branch.get('phase_id')]
                if (error.get('code') != 'DEPENDENCY_CHAIN_REPAIR_REQUIRED'
                        or error.get('stage') != 'dependency_gate'
                        or not failed or not set(failed).issubset(aliases)
                        or not set(failed).issubset(dependencies)
                        or len(matching) != 1
                        or branch_result_contracts.late_fill_branch_dependency_ids(matching[0]) != dependencies
                        or self.semantic_execution_gate_decision(branch, payload).get('action') == 'skip'):
                    continue
                if any(source.get('optional') is True or source.get('required') is False
                       or source.get('needs_external_input') is True
                       or source.get('automatic_follow_up_allowed') is False
                       or source.get('status') in {'cancelled', 'waived', 'superseded', 'deferred'}
                       for source in (branch, branch.get('execution_contract') or {},
                                      branch.get('output_contract') or {}, branch.get('recovery_context') or {},
                                      matching[0], matching[0].get('output_contract') or {})):
                    continue
                candidate = copy.deepcopy(branch)
                candidate['retry_dependency_failure'] = copy.deepcopy(error)
                candidate['recovery_context'] = {
                    'can_retry': True, 'preserve_intent': True, 'retry_scope': 'same_branch',
                    'suggested_action': RECOVERY_ACTION_RETRY_SAME_BRANCH,
                }
                added.append(candidate)
            if not added:
                return continuations
            continuations.extend(added)
            queued.extend(added)

    def _vision_evidence_recovery_allowed(
        self, branch: Mapping[str, Any], context: Mapping[str, Any],
    ) -> bool:
        backend_failure = context.get('vision_backend_failure') or {}
        backend_recovery = bool(
            context.get('error_code') in {'BACKEND_ERROR', 'BACKEND_TIMEOUT', 'INSTANCE_UNAVAILABLE'}
            and backend_failure.get('policy_id') == _VISION_BACKEND_RECOVERY_POLICY_ID
            and backend_failure.get('authority') == 'runtime_prepared_vision_input'
            and backend_failure.get('branch_id') == self.branch_id(branch)
            and backend_failure.get('phase_id') == branch.get('phase_id')
            and backend_failure.get('instance_id') in (context.get('exclude_instance_ids') or [])
        )
        if (self.branch_capability(branch) != 'vision_analysis'
                or (context.get('error_code') != 'VISION_DEPENDENCY_EVIDENCE_REJECTED' and not backend_recovery)
                or context.get('can_retry') is not True
                or context.get('preserve_intent') is not True
                or context.get('retry_scope') != 'same_branch'
                or context.get('suggested_action') != RECOVERY_ACTION_RETRY_EXCLUDING_INSTANCE):
            return False
        execution = branch.get('execution_contract') or {}
        for source in (branch, execution, branch.get('output_contract') or {}, execution.get('output_contract') or {}):
            if (source.get('required') is False or source.get('optional') is True
                    or source.get('automatic_follow_up_allowed') is False
                    or source.get('needs_external_input') is True
                    or source.get('status') in {'cancelled', 'waived', 'superseded', 'deferred'}):
                return False
        failure = context.get('vision_evidence_failure') or {}
        receipt = failure.get('input_evidence') or {}
        prior_attempt = branch.get('recovery_attempt') or {}
        try:
            retry_count = int(branch.get('auto_executable_repair_retry_count') or 0)
        except (TypeError, ValueError):
            return False
        return bool(
            retry_count == 0
            and prior_attempt.get('recovery_policy_id') not in {
                _VISION_EVIDENCE_RECOVERY_POLICY_ID, _VISION_BACKEND_RECOVERY_POLICY_ID}
            and (backend_recovery or (
                failure.get('policy_id') == _VISION_EVIDENCE_RECOVERY_POLICY_ID
                and receipt.get('branch_id') == self.branch_id(branch)
                and receipt.get('phase_id') == branch.get('phase_id')
                and receipt.get('instance_id') in (context.get('exclude_instance_ids') or [])))
        )

    def _validate_vision_retry_input(self, plan: Mapping[str, Any]) -> None:
        attempt = plan.get('vision_recovery_attempt') or {}
        prepared = plan.get('vision_dependency_binding') or {}
        if prepared:
            inputs = plan.get('infer_payload') or {}
            if (any(prepared.get(key) != plan.get(key) for key in ('response_id', 'branch_id', 'phase_id'))
                    or prepared.get('instance_id') != (plan.get('instance') or {}).get('instance_id')
                    or prepared.get('instance_id') != inputs.get('instance_id')
                    or prepared.get('depends_on') != branch_result_contracts.late_fill_branch_dependency_ids(plan.get('execution_contract') or {})
                    or self._vision_image_snapshot(inputs.get('file_path')) != prepared.get('artifact')):
                raise RuntimeError('Vision dependency binding changed before dispatch.')
        if attempt.get('recovery_policy_id') == _VISION_BACKEND_RECOVERY_POLICY_ID:
            prior = attempt.get('prior_vision_backend_failure') or {}
            if (not prepared or any(prepared.get(k) != prior.get(k) for k in (
                    'response_id', 'branch_id', 'phase_id', 'depends_on', 'artifact',
                    'producer_branch_id', 'producer_phase_id'))
                    or prepared.get('instance_id') == prior.get('instance_id')):
                raise RuntimeError('Vision recovery did not preserve its prepared image binding.')
            return
        if attempt.get('recovery_policy_id') != _VISION_EVIDENCE_RECOVERY_POLICY_ID:
            return
        failure = attempt.get('prior_vision_evidence_failure') or {}
        receipt = failure.get('input_evidence') or {}
        contract = plan.get('execution_contract') or {}
        infer_payload = plan.get('infer_payload') or {}
        instance_id = str((plan.get('instance') or {}).get('instance_id') or '')
        snapshot = self._vision_image_snapshot(infer_payload.get('file_path'))
        if (
            not snapshot or snapshot != failure.get('artifact')
            or any(plan.get(key) != receipt.get(key) for key in ('response_id', 'branch_id', 'phase_id'))
            or branch_result_contracts.late_fill_branch_dependency_ids(contract) != failure.get('depends_on')
            or not instance_id or instance_id == receipt.get('instance_id')
            or instance_id in (attempt.get('excluded_instance_ids') or [])
            or infer_payload.get('instance_id') != instance_id
        ):
            raise RuntimeError('Vision recovery input or alternate-instance binding changed; repair_branch_contract is required.')

    def dependency_evidence_error_for_branch_result(
        self,
        branch: Mapping[str, Any],
        infer_result: Mapping[str, Any],
        *,
        current_payload: Optional[Mapping[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        saved_error = self.saved_file_consumption_error(branch, infer_result, current_payload=current_payload)
        if saved_error:
            return saved_error
        capability = self.branch_capability(branch)
        result_payload = dict(infer_result or {})
        if capability and not result_payload.get('capability'):
            result_payload['capability'] = capability
        if not result_payload.get('depends_on') and branch.get('depends_on'):
            result_payload['depends_on'] = list(branch.get('depends_on') or [])
        stage_direction = str(
            branch.get('stage_direction')
            or result_payload.get('stage_direction')
            or ''
        ).strip().lower()
        semantic_review_branch = stage_direction in {
            'run_global_semantic_closure_review',
            'run_branch_semantic_review',
        }
        if (not semantic_review_branch and isinstance(current_payload, Mapping)
                and self._has_generated_image_dependency(branch, current_payload)
                and not self._vision_evidence_failure(branch, result_payload, current_payload)):
            return {'code': 'DEPENDENCY_CHAIN_REPAIR_REQUIRED', 'retryable': False,
                    'stage': 'semantic_evidence_gate',
                    'message': 'Generated-image inspection has no matching exact image dispatch evidence.'}
        if (
            not semantic_review_branch
            and branch_result_contracts.late_fill_result_has_missing_dependency_evidence(result_payload)
        ):
            vision_failure = self._vision_evidence_failure(branch, result_payload, current_payload)
            if vision_failure:
                return {
                    'code': 'VISION_DEPENDENCY_EVIDENCE_REJECTED',
                    'message': 'Vision result failed the dependency evidence check after the exact image bytes were supplied.',
                    'stage': 'semantic_evidence_gate',
                    'retryable': True,
                    'repair_action': RECOVERY_ACTION_RETRY_EXCLUDING_INSTANCE,
                    'materialization_blocked': True,
                    'blocked_scope': 'current_vision_branch',
                    'vision_evidence_failure': vision_failure,
                }
            return {
                'code': 'DEPENDENCY_CHAIN_REPAIR_REQUIRED',
                'message': 'Dependency evidence repair required: the branch did not receive or use the artifact evidence it depended on.',
                'stage': 'semantic_evidence_gate',
                'retryable': False,
            }
        audio_integrity_error = self.tts_result_evidence.tts_audio_integrity_error_for_branch_result(
            branch,
            result_payload,
        )
        if audio_integrity_error:
            return audio_integrity_error
        semantic_evidence = (
            result_payload.get('tts_stt_semantic_evidence')
            if isinstance(result_payload.get('tts_stt_semantic_evidence'), Mapping)
            else self.tts_result_evidence.tts_stt_semantic_evidence_for_branch_result(
                branch,
                result_payload,
                current_payload=current_payload,
            )
        )
        semantic_status = str(semantic_evidence.get('status') or '').strip().lower()
        if semantic_status not in {'mismatched', 'unavailable'}:
            return None
        reason_code = str(
            semantic_evidence.get('reason_code')
            or 'TTS_STT_SEMANTIC_EVIDENCE_UNAVAILABLE'
        ).strip()
        failed_dependency_ids = [
            str(item or '').strip()
            for item in (semantic_evidence.get('failed_dependency_ids') or [])
            if str(item or '').strip()
        ] if isinstance(semantic_evidence.get('failed_dependency_ids'), list) else []
        producer_phase_id = str(
            semantic_evidence.get('producer_phase_id') or ''
        ).strip()
        if producer_phase_id and producer_phase_id not in failed_dependency_ids:
            failed_dependency_ids.append(producer_phase_id)
        return {
            'code': 'DEPENDENCY_CHAIN_REPAIR_REQUIRED',
            'reason_code': reason_code,
            'defect_code': reason_code,
            'message': (
                'Audio transcript semantic evidence does not match the exact text '
                'handed to its TTS producer.'
                if semantic_status == 'mismatched'
                else 'Audio transcript semantic evidence cannot be verified from the exact TTS producer source.'
            ),
            'stage': 'semantic_evidence_gate',
            'retryable': False,
            'repair_action': RECOVERY_ACTION_REPAIR_DEPENDENCY_CHAIN,
            'materialization_blocked': True,
            'failed_dependency_ids': [
                item for item in failed_dependency_ids if item
            ],
            'semantic_evidence': dict(semantic_evidence),
        }

    @staticmethod
    def _late_fill_plain_markdown_line(content: Any) -> str:
        text = str(content or '').strip()
        if not text:
            return ''
        text = re.sub(r'^#{1,6}\s*', '', text)
        text = re.sub(r'^[-+*]\s+', '', text)
        text = text.replace('**', '').replace('__', '').replace('`', '')
        return text.strip()

    @staticmethod
    def _late_fill_label_has_speakable_token(label: Any) -> bool:
        normalized = re.sub(r'\s+', ' ', str(label or '').casefold()).strip()
        if not normalized:
            return False
        return any(
            re.search(
                rf'(?<!\w){re.escape(token)}(?!\w)',
                normalized,
                flags=re.UNICODE,
            )
            for token in _AUDIO_SINGLE_SPEAKABLE_SECTION_TOKENS
        )

    @classmethod
    def _trim_late_fill_numbered_candidate_body(cls, content: Any) -> str:
        """Exclude non-authoritative transcript/JSON siblings after a candidate."""

        retained: list[str] = []
        for raw_line in str(content or '').splitlines():
            if retained and raw_line.strip().startswith('```'):
                break
            plain = cls._late_fill_plain_markdown_line(raw_line)
            field_match = re.match(r'^(?P<label>[^:\n]{1,120})\s*:', plain)
            if retained and field_match:
                label = field_match.group('label').casefold()
                if re.search(
                    r'(?<!\w)(?:json|transcript|transkript)(?!\w)',
                    label,
                    flags=re.UNICODE,
                ):
                    break
            retained.append(raw_line)
        return re.sub(r'\s+', ' ', '\n'.join(retained)).strip()

    @classmethod
    def _late_fill_labeled_audio_candidate_contract(cls, content: Any) -> dict[str, Any]:
        """Extract explicitly indexed audio bodies without trusting sibling prose.

        Once an audio-variant heading is present, the labelled slots are the only
        candidate authority. Missing, repeated, or ambiguous slots therefore stay
        fail-closed instead of falling back to paragraph order.
        """

        text = str(content or '').strip()
        if not text:
            return {
                'marker_detected': False,
                'source': 'empty',
                'units': [],
            }
        lines = text.splitlines()
        headers: list[tuple[int, int]] = []
        for line_index, line in enumerate(lines):
            plain = cls._late_fill_plain_markdown_line(line)
            match = _AUDIO_VARIANT_HEADER_RE.fullmatch(plain)
            if match:
                headers.append((line_index, int(match.group('index'))))
        if not headers:
            return {
                'marker_detected': False,
                'source': 'no_labeled_audio_variant_sections',
                'units': [],
            }

        indexes = [index for _line_index, index in headers]
        if len(set(indexes)) != len(indexes):
            return {
                'marker_detected': True,
                'source': 'labeled_audio_variant_sections',
                'units': [],
                'issue': 'duplicate_audio_variant_index',
                'indexes': indexes,
            }
        expected_indexes = list(range(1, len(indexes) + 1))
        if sorted(indexes) != expected_indexes:
            return {
                'marker_detected': True,
                'source': 'labeled_audio_variant_sections',
                'units': [],
                'issue': 'non_contiguous_candidate_indexes',
                'indexes': indexes,
            }

        bodies_by_index: dict[int, str] = {}
        for header_offset, (line_index, variant_index) in enumerate(headers):
            end_line = (
                headers[header_offset + 1][0]
                if header_offset + 1 < len(headers)
                else len(lines)
            )
            section_lines = lines[line_index + 1:end_line]
            speakable_bodies: list[str] = []
            for section_line_index, raw_line in enumerate(section_lines):
                plain = cls._late_fill_plain_markdown_line(raw_line)
                field_match = re.match(
                    r'^(?P<label>[^:\n]{1,80})\s*:\s*(?P<body>.*)$',
                    plain,
                )
                if not field_match:
                    continue
                label = re.sub(
                    r'\s+',
                    ' ',
                    field_match.group('label').strip().casefold(),
                )
                if label not in _AUDIO_SPEAKABLE_FIELD_LABELS:
                    continue
                body = field_match.group('body').strip()
                if not body:
                    continuation: list[str] = []
                    for continuation_line in section_lines[section_line_index + 1:]:
                        continuation_plain = cls._late_fill_plain_markdown_line(
                            continuation_line
                        )
                        if not continuation_plain:
                            if continuation:
                                break
                            continue
                        if re.match(r'^[^:\n]{1,80}\s*:', continuation_plain):
                            break
                        if continuation_plain.startswith(('```', '{', '[')):
                            break
                        continuation.append(continuation_plain)
                    body = ' '.join(continuation).strip()
                body = re.sub(r'\s+', ' ', body).strip()
                if body:
                    speakable_bodies.append(body)
            if len(speakable_bodies) != 1:
                return {
                    'marker_detected': True,
                    'source': 'labeled_audio_variant_sections',
                    'units': [],
                    'issue': (
                        'missing_audio_variant_body'
                        if not speakable_bodies
                        else 'ambiguous_audio_variant_body'
                    ),
                    'indexes': indexes,
                    'variant_index': variant_index,
                }
            bodies_by_index[variant_index] = speakable_bodies[0]

        return {
            'marker_detected': True,
            'source': 'labeled_audio_variant_sections',
            'units': [bodies_by_index[index] for index in expected_indexes],
            'indexes': expected_indexes,
        }

    @classmethod
    def _late_fill_candidate_selection_contract(cls, content: Any) -> dict[str, Any]:
        text = str(content or '').strip()
        if not text:
            return {'source': 'empty', 'units': []}
        labeled = cls._late_fill_labeled_audio_candidate_contract(text)
        if labeled.get('marker_detected'):
            return labeled

        numbered_matches = list(
            re.finditer(
                r'(?ms)^\s*(?P<index>\d+)[.)]\s*(?P<body>.*?)'
                r'(?=^\s*\d+[.)]\s+|\Z)',
                text,
            )
        )
        if numbered_matches:
            indexes = [int(match.group('index')) for match in numbered_matches]
            expected_indexes = list(range(1, len(indexes) + 1))
            if indexes != expected_indexes:
                return {
                    'source': 'numbered_candidate_bodies',
                    'units': [],
                    'indexes': indexes,
                    'issue': 'non_contiguous_candidate_indexes',
                }
            numbered: list[str] = []
            for match in numbered_matches:
                body = cls._trim_late_fill_numbered_candidate_body(
                    match.group('body')
                )
                if body:
                    numbered.append(body)
            if len(numbered) != len(numbered_matches):
                return {
                    'source': 'numbered_candidate_bodies',
                    'units': [],
                    'indexes': indexes,
                    'issue': 'missing_candidate_body',
                }
            return {
                'source': 'numbered_candidate_bodies',
                'units': numbered,
                'indexes': indexes,
            }
        return {
            'source': 'generic_content_units',
            'units': cls._split_late_fill_content_units(text),
        }

    @classmethod
    def _late_fill_candidate_units_for_selection(cls, content: Any) -> list[str]:
        contract = cls._late_fill_candidate_selection_contract(content)
        if contract.get('issue'):
            return []
        return [
            str(unit or '').strip()
            for unit in (contract.get('units') or [])
            if str(unit or '').strip()
        ]

    @classmethod
    def _late_fill_labeled_speakable_sections(cls, content: Any) -> list[str]:
        heading_sections = extract_atx_tts_sections(str(content or ''))
        if heading_sections:
            return heading_sections
        candidates: list[str] = []
        lines = str(content or '').splitlines()
        for line_index, raw_line in enumerate(lines):
            plain = cls._late_fill_plain_markdown_line(raw_line)
            match = re.match(
                r'^(?P<label>[^:\n]{1,120})\s*:\s*(?P<body>.*)$',
                plain,
            )
            if not match:
                continue
            label = re.sub(r'\s+', ' ', match.group('label').casefold()).strip()
            if any(token in label for token in ('transcript', 'transkript', 'json')):
                continue
            if not cls._late_fill_label_has_speakable_token(label):
                continue
            body_parts = [match.group('body').strip()] if match.group('body').strip() else []
            for continuation_line in lines[line_index + 1:]:
                if continuation_line.strip().startswith('```'):
                    break
                continuation_plain = cls._late_fill_plain_markdown_line(
                    continuation_line
                )
                if re.match(r'^[^:\n]{1,120}\s*:', continuation_plain):
                    break
                if continuation_plain:
                    body_parts.append(continuation_plain)
            body = re.sub(r'\s+', ' ', ' '.join(body_parts)).strip()
            if body:
                candidates.append(body)
        return candidates

    @staticmethod
    def _select_late_fill_candidate_unit(content: Any, index: int = 1) -> str:
        units = LateFillRuntimeOwner._late_fill_candidate_units_for_selection(content)
        if not units:
            return ''
        if isinstance(index, bool):
            return ''
        if isinstance(index, int):
            normalized_index = index
        elif (
            isinstance(index, str)
            and index.isascii()
            and index.isdigit()
            and 0 < len(index) <= 6
        ):
            normalized_index = int(index)
        else:
            return ''
        if normalized_index <= 0:
            return ''
        if normalized_index > len(units):
            return ''
        return units[normalized_index - 1].strip()

    @staticmethod
    def _branch_prompt_selection_index(branch: Mapping[str, Any], candidate_count: int) -> int:
        try:
            normalized_count = int(candidate_count)
        except (TypeError, ValueError):
            normalized_count = 0
        if normalized_count <= 0:
            return 0

        def _coerce_index(value: Any) -> int:
            try:
                index = int(value)
            except (TypeError, ValueError):
                return 0
            return index if 1 <= index <= normalized_count else 0

        for key in (
            'candidate_selection_index',
            'prompt_selection_index',
            'image_prompt_index',
            'artifact_prompt_index',
        ):
            raw_value = (branch or {}).get(key)
            try:
                explicit_index = int(raw_value)
            except (TypeError, ValueError):
                explicit_index = 0
            if explicit_index > normalized_count:
                return 0
            index = _coerce_index(raw_value)
            if index:
                return index

        for key in (
            'branch_id',
            'phase_id',
            'slot_id',
            'obligation_id',
            'task_id',
            'workload_task_id',
        ):
            token = str((branch or {}).get(key) or '').strip()
            if 'image' not in token.lower():
                continue
            match = re.search(r'(\d+)\s*$', token)
            if not match:
                continue
            if int(match.group(1)) > normalized_count:
                return 0
            index = _coerce_index(match.group(1))
            if index:
                return index

        raw_queue_index = (branch or {}).get('queue_index')
        try:
            explicit_queue_index = int(raw_queue_index)
        except (TypeError, ValueError):
            explicit_queue_index = 0
        if explicit_queue_index > normalized_count:
            return 0
        queue_index = _coerce_index(raw_queue_index)
        if queue_index:
            return queue_index
        return 1

    def _image_prompt_batch_expected_count(
        self,
        *,
        branch: Mapping[str, Any],
        branch_gap: Mapping[str, Any],
        current_payload: Mapping[str, Any],
    ) -> int:
        """Resolve the original image cohort size, not just the current retry wave."""

        def coerce_count(value: Any) -> int:
            try:
                count = int(value)
            except (TypeError, ValueError):
                return 0
            return count if 2 <= count <= 26 else 0

        def records_share_image_obligation(
            left: Mapping[str, Any],
            right: Mapping[str, Any],
        ) -> bool:
            left_capability = self.normalize_capability(left.get('capability'))
            right_capability = self.normalize_capability(right.get('capability'))
            if (
                left_capability
                and right_capability
                and left_capability != right_capability
            ):
                return False
            left_output_type = str(left.get('output_type') or '').strip().lower()
            right_output_type = str(right.get('output_type') or '').strip().lower()
            if (
                left_output_type
                and right_output_type
                and left_output_type != right_output_type
            ):
                return False
            left_obligation_id = str(left.get('obligation_id') or '').strip()
            right_obligation_id = str(right.get('obligation_id') or '').strip()
            if (
                left_obligation_id
                and right_obligation_id
                and left_obligation_id != right_obligation_id
            ):
                return False
            index_keys = (
                'queue_index',
                'candidate_selection_index',
                'prompt_selection_index',
                'image_prompt_index',
                'artifact_prompt_index',
            )

            def positive_index(source: Mapping[str, Any]) -> int:
                for key in index_keys:
                    try:
                        value = int(source.get(key) or 0)
                    except (TypeError, ValueError):
                        continue
                    if value > 0:
                        return value
                return 0

            left_index = positive_index(left)
            right_index = positive_index(right)
            if left_index and right_index and left_index != right_index:
                return False
            left_branch_id = str(left.get('branch_id') or '').strip()
            right_branch_id = str(right.get('branch_id') or '').strip()
            if left_branch_id and left_branch_id == right_branch_id:
                return True
            if left_obligation_id and right_obligation_id:
                return left_obligation_id == right_obligation_id
            left_phase_id = str(left.get('phase_id') or '').strip()
            right_phase_id = str(right.get('phase_id') or '').strip()
            return bool(left_phase_id and left_phase_id == right_phase_id)

        def distinct_image_obligation_records(
            records: list[Mapping[str, Any]],
        ) -> list[Mapping[str, Any]]:
            distinct: list[Mapping[str, Any]] = []
            for item in records:
                if any(
                    records_share_image_obligation(existing, item)
                    for existing in distinct
                ):
                    continue
                distinct.append(item)
            return distinct

        current_late_fill = (
            current_payload.get('late_fill')
            if isinstance(current_payload.get('late_fill'), Mapping)
            else {}
        )
        runtime = (
            current_payload.get('runtime')
            if isinstance(current_payload.get('runtime'), Mapping)
            else {}
        )
        phase_graph = (
            runtime.get('request_phase_graph')
            if isinstance(runtime.get('request_phase_graph'), Mapping)
            else {}
        )
        graph_phases = phase_graph.get('phases') if isinstance(phase_graph.get('phases'), list) else []
        target_dependencies = tuple(sorted({
            str(item or '').strip()
            for item in (branch.get('depends_on') or [])
            if str(item or '').strip()
        }))
        if not target_dependencies:
            target_tokens = {
                str(branch.get('branch_id') or '').strip(),
                str(branch.get('phase_id') or '').strip(),
            }
            target_tokens.discard('')
            for phase in graph_phases:
                if not isinstance(phase, Mapping):
                    continue
                phase_tokens = {
                    str(phase.get('branch_id') or '').strip(),
                    str(phase.get('phase_id') or '').strip(),
                }
                if not target_tokens.intersection(phase_tokens):
                    continue
                target_dependencies = tuple(sorted({
                    str(item or '').strip()
                    for item in (phase.get('depends_on') or [])
                    if str(item or '').strip()
                }))
                break

        lifecycle_records: list[Mapping[str, Any]] = []
        for source in (branch_gap, current_late_fill):
            for key in (
                'pending_branches',
                'active_branches',
                'completed_branches',
                'failed_branches',
                'cancelled_branches',
            ):
                lifecycle_records.extend(
                    item
                    for item in (source.get(key) or [])
                    if isinstance(item, Mapping)
                )
        lifecycle_records.extend(
            item for item in graph_phases if isinstance(item, Mapping)
        )
        cohort_records: list[tuple[Mapping[str, Any], int]] = []
        if target_dependencies:
            for item in lifecycle_records:
                capability = self.normalize_capability(item.get('capability'))
                output_type = str(item.get('output_type') or '').strip().lower()
                if capability != self.capability_image_generation and output_type != 'image':
                    continue
                item_dependencies = tuple(sorted({
                    str(value or '').strip()
                    for value in (item.get('depends_on') or [])
                    if str(value or '').strip()
                }))
                if item_dependencies != target_dependencies:
                    continue
                try:
                    queue_index = int(item.get('queue_index') or 0)
                except (TypeError, ValueError):
                    continue
                if not 1 <= queue_index <= 26:
                    continue
                matched_group_index = next(
                    (
                        index
                        for index, (existing, _existing_queue_index)
                        in enumerate(cohort_records)
                        if records_share_image_obligation(existing, item)
                    ),
                    None,
                )
                if matched_group_index is None:
                    cohort_records.append((item, queue_index))
                else:
                    existing, existing_queue_index = cohort_records[
                        matched_group_index
                    ]
                    cohort_records[matched_group_index] = (
                        existing,
                        min(existing_queue_index, queue_index),
                    )
        ordered_indexes = sorted({queue_index for _item, queue_index in cohort_records})
        if (
            len(cohort_records) >= 2
            and len(ordered_indexes) == len(cohort_records)
            and ordered_indexes == list(range(1, len(ordered_indexes) + 1))
        ):
            return len(ordered_indexes)

        for source in (branch_gap, current_late_fill):
            count = coerce_count(source.get('batch_prompt_expected_count'))
            source_phase_id = str(source.get('batch_prompt_source_phase_id') or '').strip()
            if (
                count
                and source_phase_id
                and target_dependencies == (source_phase_id,)
            ):
                return count

        batch_prompts = branch_gap.get('batch_prompts')
        raw_batch_count = len([
            item
            for item in (batch_prompts if isinstance(batch_prompts, list) else [])
            if str(item or '').strip()
        ])
        prompt_intent = (
            phase_graph.get('prompt_intent')
            if isinstance(phase_graph.get('prompt_intent'), Mapping)
            else {}
        )
        requested_count = coerce_count(prompt_intent.get('requested_visual_output_count'))
        if requested_count and requested_count == raw_batch_count:
            return requested_count

        pending_branches = branch_gap.get('pending_branches')
        pending_image_records = [
            item
            for item in (pending_branches if isinstance(pending_branches, list) else [])
            if isinstance(item, Mapping)
            and (
                self.normalize_capability(item.get('capability')) == self.capability_image_generation
                or str(item.get('output_type') or '').strip().lower() == 'image'
            )
        ]
        pending_count = len(
            distinct_image_obligation_records(pending_image_records)
        )
        return coerce_count(pending_count)

    @staticmethod
    def _image_branch_prompt_allows_batch_prompt_override(
        branch: Mapping[str, Any],
        branch_gap: Mapping[str, Any],
    ) -> bool:
        branch_prompt = str((branch or {}).get('artifact_prompt') or '').strip()
        prompt = branch_prompt or str((branch_gap or {}).get('artifact_prompt') or '').strip()
        source = str(
            (
                (branch or {}).get('artifact_prompt_source')
                if branch_prompt
                else (branch_gap or {}).get('artifact_prompt_source')
            )
            or ''
        ).strip()
        authoritative_sources = {
            'semantic_batch_prompt',
            'semantic_batch_prompts',
            'semantic_prepare_phase_output',
            'current_turn_direct_image_clause',
            'action_input',
            'prompt_blockquote_section',
            'quoted_prompt_section',
            'inline_prompt_capsule',
            'focused_image_prompt_slot',
            'focused_content_payload',
            'request_prompt_image_slots',
            'current_turn_explicit_image_manifest',
        }
        if (
            not branch_prompt
            and isinstance((branch_gap or {}).get('batch_prompts'), list)
        ):
            # A prompt on the shared gap is only the first prepared slot.  An
            # expanded cohort must still select by each branch identity; only
            # a prompt carried by the branch itself is already branch-local.
            return True
        if source in authoritative_sources:
            return False
        if not prompt:
            return True
        normalized = re.sub(r'[`*]+', '', prompt).strip().lower()
        normalized = re.sub(r'\s+', ' ', normalized)
        if not normalized:
            return True
        mentions_image_generation = 'image_generation' in normalized or 'image generation' in normalized
        asks_for_assets = bool(re.search(r'\b(?:visual\s+)?assets?\b|\bimages?\b', normalized))
        generic_batch_shape = bool(
            re.search(r'\bgenerate\s+\d+\b', normalized)
            or 'distinct' in normalized
            or 'manifest' in normalized
        )
        manifest_based = 'manifest' in normalized and 'based on' in normalized
        return bool(
            mentions_image_generation
            and asks_for_assets
            and (generic_batch_shape or manifest_based)
        )

    @staticmethod
    def _split_late_fill_content_units(content: Any) -> list[str]:
        text = str(content or '').strip()
        if not text:
            return []
        units = [
            re.sub(r'\s+', ' ', item).strip()
            for item in re.split(r'\n\s*\n+', text)
            if re.sub(r'\s+', ' ', item).strip()
        ]
        if len(units) <= 1:
            units = [
                re.sub(r'\s+', ' ', item).strip()
                for item in re.split(r'(?m)^\s*(?:[-*]|\d+[.)])\s+', text)
                if re.sub(r'\s+', ' ', item).strip()
            ]
        if len(units) <= 1 and re.search(
            r'\b(?:image\s+prompt|visual prompt|poster|poster image|graphic design|generated artifacts?|final sentence)\b',
            text,
            flags=re.IGNORECASE,
        ):
            units = [
                re.sub(r'\s+', ' ', item).strip()
                for item in re.split(r'(?<=[.!?])\s+(?=[A-Z0-9"\'])', text)
                if re.sub(r'\s+', ' ', item).strip()
            ]
        return units

    @staticmethod
    def _strip_late_fill_prompt_label(content: str) -> str:
        return re.sub(
            r'(?is)^\s*(?:[#>*\-\d.)\s]*)(?:(?:(?:image|visual|poster|bild)\s*[- ]?\s*)?prompt|bildprompt)'
            r'(?:\s*(?:for|idee|idea|bild|poster)?\s*\d*)?\s*[:\-]\s*',
            '',
            str(content or '').strip(),
        ).strip()

    @staticmethod
    def _late_fill_image_prompt_is_code_polluted(content: Any) -> bool:
        text = str(content or '').strip()
        if not text:
            return False
        return _image_prompt_candidate_is_code_or_css_polluted(text)

    @staticmethod
    def _late_fill_image_prompt_is_page_layout_instruction(content: Any) -> bool:
        text = str(content or '').strip()
        if not text:
            return False
        cleaned = re.sub(r'[`*#_]+', '', text)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip().lower()
        if not cleaned:
            return False
        layout_cues = {
            'background',
            'button',
            'cta',
            'headline',
            'hero section',
            'layout',
            'navigation',
            'section',
            'subheadline',
            'text',
            'text overlay',
            'visual',
        }
        cue_hits = sum(1 for cue in layout_cues if cue in cleaned)
        if cue_hits < 2:
            return False
        if re.search(r'\b(?:hero|about us|craftsmanship|portfolio|featured work|features?|gallery|contact|footer)\s+section\b', cleaned):
            return True
        if re.search(r'\b(?:layout|headline|subheadline|text overlay|text \(|visual \(|cta|navigation)\s*:', cleaned):
            return True
        if re.search(r'\b(?:using|implementation of|display of)\s+(?:the\s+)?[a-z0-9 \"\'-]*\bimage\b\s*\(?image\s*\d+\)?', cleaned):
            return True
        return False

    @staticmethod
    def _extract_late_fill_image_prompt_units(content: Any) -> list[str]:
        inline_prompts = _extract_inline_labeled_image_prompt_lines(str(content or ''))
        if inline_prompts:
            return inline_prompts
        units = LateFillRuntimeOwner._split_late_fill_content_units(content)
        prompts: list[str] = []
        for unit in units:
            raw_unit = str(unit or '').strip()
            if not raw_unit:
                continue
            if LateFillRuntimeOwner._late_fill_image_prompt_is_code_polluted(raw_unit):
                if prompts:
                    break
                continue
            lowered = raw_unit.lower()
            if re.search(
                r'\b('
                r'html\s+materialization|css\s+design|structure\s*&\s*elements|'
                r'document\s+metadata|asset\s+links|visual\s+theme|color\s+palette|'
                r'typography|layout\s*&\s*composition'
                r')\b',
                lowered,
            ):
                if prompts:
                    break
                continue
            prompt_like = (
                re.search(r'\b(?:image\s+generation\s+)?prompts?\s*\d*\s*[:\-]', lowered)
                or re.search(r'\b(?:image|visual|poster|bild)\s*[- ]?\s*prompt\s*\d*\s*[:\-]', lowered)
                or re.search(r'\bprompt\s*(?:\d+|[a-z])\s*[:\-]', lowered)
                or re.search(r'^\s*(?:\d+[.)]\s*)?[^:\n]{0,96}\bimage\b\s*[:\-]', raw_unit, re.IGNORECASE)
            )
            if not prompt_like:
                continue
            cleaned = LateFillRuntimeOwner._strip_late_fill_prompt_label(raw_unit)
            cleaned = re.sub(r'\*\*+', '', cleaned).strip()
            cleaned = re.sub(r'^\s*[:\-–—]\s*', '', cleaned).strip()
            if cleaned and LateFillRuntimeOwner._late_fill_image_prompt_score(raw_unit) > 0:
                prompts.append(cleaned)
        if prompts:
            return prompts
        root_asset_prompts = LateFillRuntimeOwner._extract_late_fill_numbered_image_asset_units(content)
        if root_asset_prompts:
            return root_asset_prompts
        return prompts

    @classmethod
    def _extract_late_fill_compact_numbered_image_prompt_units(cls, content: Any) -> list[str]:
        text = re.sub(r'\s+', ' ', str(content or '').strip())
        if not text:
            return []
        markers = list(re.finditer(r'(?<!\w)(?P<index>\d{1,2})[.)]\s+', text))
        if len(markers) < 2:
            return []
        prompts: list[str] = []
        for index, marker in enumerate(markers):
            start = marker.end()
            end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
            body = text[start:end].strip()
            body = re.sub(r'\(?\s*File\s*:\s*[^)]*\)?', '', body, flags=re.IGNORECASE).strip()
            body = re.sub(r'\$\s*\\text\s*\{[^}]+\}\s*', '', body).strip()
            body = cls._strip_late_fill_prompt_label(body)
            body = re.sub(r'\s+', ' ', body).strip(' ;,')
            if not cls._late_fill_image_batch_prompt_is_viable(body):
                continue
            prompts.append(body)
        return prompts if len(prompts) >= 2 else []

    @classmethod
    def _late_fill_image_batch_prompt_is_viable(cls, content: Any) -> bool:
        text = _strip_social_manifest_image_prompt_metadata(content)
        if not text:
            text = cls._strip_late_fill_prompt_label(str(content or '').strip())
        if not text:
            return False
        if cls._late_fill_image_prompt_is_code_polluted(text):
            return False
        if cls._late_fill_image_prompt_is_page_layout_instruction(text):
            return False
        lowered = text.lower()
        heading_only = re.sub(r'^[\s`#>*_-]+|[\s`#>*_-]+$', '', lowered).strip()
        heading_only = re.sub(
            r'^(?:text|plaintext|markdown|md)\s*(?://|::?|[-\u2013\u2014])\s*',
            '',
            heading_only,
        ).strip()
        if re.fullmatch(
            r'(?:image\s+generation\s+|visual\s+|bild(?:generierungs?|\s+generation)?[-\s]*)?'
            r'prompts?'
            r'(?:\s*(?:\([^)]+\)|\[[^\]]+\]))?'
            r'\s*:?',
            heading_only,
        ):
            return False
        if re.fullmatch(
            r'(?:(?:artifact|artefakt)\s*(?:\d+|[ivx]+)\s*:\s*)?'
            r'(?:'
            r'(?:image|visual|poster)\s*(?:generation\s*)?prompt'
            r'|bild(?:generierungs?|\s+generation)?[-\s]*prompt'
            r')'
            r'(?:\s*(?:\([^)]+\)|\[[^\]]+\]))?',
            lowered,
        ):
            return False
        if re.fullmatch(
            r'(?:image\s+)?(?:prompt|scene|section|hero|workflow|interior|exterior|lounge|detail)(?:\s+\d+)?',
            lowered,
        ):
            return False
        words = re.findall(r'\w+', text)
        if cls._late_fill_image_prompt_score(text) > 0:
            return True
        return len(words) >= 6

    @classmethod
    def _late_fill_structured_image_prompt_unit_is_viable(cls, content: Any) -> bool:
        text = cls._strip_late_fill_prompt_label(str(content or '').strip())
        if cls._late_fill_image_batch_prompt_is_viable(text):
            return True
        if not text or cls._late_fill_image_prompt_is_code_polluted(text):
            return False
        if cls._late_fill_image_prompt_is_page_layout_instruction(text):
            return False
        words = re.findall(r'\w+', text)
        return len(words) >= 4 and cls._late_fill_image_prompt_score(text) >= 0

    _request_payload_prompt_text = staticmethod(BranchDependencyEvidence._request_payload_prompt_text)

    @staticmethod
    def _late_fill_batch_has_nonsequential_alpha_prompt_residue(
        raw_items: list[str],
    ) -> bool:
        labels = [
            str(match.group('label') or '')
            for item in raw_items
            if (match := _LATE_FILL_ALPHA_PROMPT_RESIDUE_RE.fullmatch(str(item or '')))
        ]
        if len(labels) < 2:
            return False
        expected_labels = [chr(ord('A') + index) for index in range(len(labels))]
        return len(labels) != len(raw_items) or labels != expected_labels

    @staticmethod
    def _late_fill_batch_has_collapsed_sequential_alpha_prompt_residue(
        raw_items: list[str],
        *,
        expected_count: int,
    ) -> bool:
        return bool(
            LateFillRuntimeOwner._late_fill_collapsed_sequential_alpha_prompt_bodies(
                raw_items,
                expected_count=expected_count,
            )
        )

    @staticmethod
    def _late_fill_collapsed_sequential_alpha_prompt_bodies(
        raw_items: list[str],
        *,
        expected_count: int,
    ) -> list[str]:
        normalized_count = int(expected_count or 0)
        if normalized_count < 2 or not raw_items:
            return []
        first_item = str(raw_items[0] or '').strip()
        matches = list(_LATE_FILL_COLLAPSED_ALPHA_LABEL_RE.finditer(first_item))
        if len(matches) != normalized_count or not matches or matches[0].start() != 0:
            return []
        labels = [str(match.group('label') or '') for match in matches]
        if labels != [chr(ord('A') + index) for index in range(normalized_count)]:
            return []
        bodies: list[str] = []
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(first_item)
            body = re.sub(r'\s+', ' ', first_item[match.end():end]).strip()
            if not body:
                return []
            bodies.append(body)
        return bodies

    @classmethod
    def _recover_plain_alpha_prompts_from_collapsed_batch_source(
        cls,
        raw_items: list[str],
        *,
        source: Any,
        expected_count: int,
    ) -> list[str]:
        """Recover only when one preserved source proves the corrupt batch lineage."""

        normalized_count = int(expected_count or 0)
        if normalized_count < 2 or len(raw_items) != normalized_count:
            return []
        collapsed_bodies = cls._late_fill_collapsed_sequential_alpha_prompt_bodies(
            raw_items,
            expected_count=normalized_count,
        )
        if not collapsed_bodies:
            return []
        source_text = str(source or '').strip()
        plain_alpha_prompts = _extract_leading_plain_alpha_image_prompt_lines(
            source_text,
            expected_count=normalized_count,
        )
        def normalize_whitespace(value: Any) -> str:
            return re.sub(r'\s+', ' ', str(value or '')).strip()

        if [normalize_whitespace(item) for item in plain_alpha_prompts] != [
            normalize_whitespace(item) for item in collapsed_bodies
        ]:
            return []

        # A full-size direct batch is only replaceable when the same source also
        # proves how the paragraph fallback produced every tail slot. This keeps
        # a legitimate composite first prompt plus healthy siblings authoritative.
        source_units = [
            normalize_whitespace(item)
            for item in re.split(r'\n\s*\n+', source_text)
            if normalize_whitespace(item)
        ]
        if len(source_units) < normalized_count:
            return []
        if source_units[:normalized_count] != [
            normalize_whitespace(item) for item in raw_items
        ]:
            return []
        return plain_alpha_prompts

    @classmethod
    def _normalize_late_fill_image_batch_prompts(
        cls,
        batch_prompts: Any,
        *,
        expected_count: int = 0,
        assistant_message: Any = '',
        content_payload: Any = '',
        request_payload: Any = None,
        artifact_prompt: Any = '',
    ) -> list[str]:
        raw_items = [
            str(item or '').strip()
            for item in (batch_prompts if isinstance(batch_prompts, list) else [])
        ]
        non_empty_items = [item for item in raw_items if item]
        normalized_count = int(expected_count or 0)
        if (
            normalized_count > 0
            and len(raw_items) == normalized_count
            and len(non_empty_items) != len(raw_items)
        ):
            return raw_items
        direct_prompts: list[str] = []
        for item in non_empty_items:
            prompt = _strip_social_manifest_image_prompt_metadata(item)
            if not prompt:
                prompt = cls._strip_late_fill_prompt_label(item).strip()
            if prompt and cls._late_fill_image_batch_prompt_is_viable(prompt):
                direct_prompts.append(prompt)
        compact_prompts: list[str] = []
        for item in non_empty_items:
            compact_prompts.extend(cls._extract_late_fill_compact_numbered_image_prompt_units(item))
        if (
            compact_prompts
            and len(compact_prompts) > len(direct_prompts)
            and (normalized_count <= 0 or len(compact_prompts) >= normalized_count)
        ):
            return compact_prompts

        batch_is_incomplete = bool(normalized_count and len(direct_prompts) < normalized_count)
        batch_has_collapsed_alpha_residue = (
            cls._late_fill_batch_has_collapsed_sequential_alpha_prompt_residue(
                non_empty_items,
                expected_count=normalized_count,
            )
        )
        batch_is_polluted = (
            len(direct_prompts) != len(non_empty_items)
            or len(non_empty_items) != len(raw_items)
            or cls._late_fill_batch_has_nonsequential_alpha_prompt_residue(non_empty_items)
            or batch_has_collapsed_alpha_residue
        )
        batch_looks_like_weak_social_copy = _image_prompt_batch_looks_like_weak_social_copy(
            direct_prompts
        )
        batch_needs_recovery = (
            batch_is_incomplete
            or batch_is_polluted
            or batch_looks_like_weak_social_copy
        )
        source_candidates = [
            '\n\n'.join(non_empty_items),
            artifact_prompt,
            assistant_message,
            content_payload,
            BranchDependencyEvidence._request_payload_prompt_text(request_payload),
        ]
        sequential_recovery_sources = [
            (artifact_prompt, False),
            ('\n\n'.join(non_empty_items), True),
            (assistant_message, True),
            (content_payload, True),
            (BranchDependencyEvidence._request_payload_prompt_text(request_payload), True),
        ]
        if batch_has_collapsed_alpha_residue:
            for source in (artifact_prompt, assistant_message, content_payload):
                plain_alpha_prompts = cls._recover_plain_alpha_prompts_from_collapsed_batch_source(
                    non_empty_items,
                    source=source,
                    expected_count=normalized_count,
                )
                if len(plain_alpha_prompts) == normalized_count:
                    return plain_alpha_prompts
            # Failed provenance must not compact or renumber producer slots.
            # Preserve the original batch shape so queue indexes cannot drift.
            return raw_items
        for source, require_image_heading in sequential_recovery_sources:
            if not batch_needs_recovery:
                break
            sequential_alpha_prompts = _extract_sequential_bold_alpha_image_prompt_lines(
                str(source or ''),
                expected_count=normalized_count,
                require_image_heading=require_image_heading,
            )
            if sequential_alpha_prompts and (
                not normalized_count or len(sequential_alpha_prompts) >= normalized_count
            ):
                return sequential_alpha_prompts
        for source in source_candidates:
            filename_prompt_units = _extract_filename_social_asset_image_prompt_lines(
                str(source or ''),
                expected_count=normalized_count,
            )
            if not filename_prompt_units:
                continue
            if normalized_count and len(filename_prompt_units) < normalized_count:
                continue
            if (
                batch_is_incomplete
                or batch_is_polluted
                or batch_looks_like_weak_social_copy
            ):
                return filename_prompt_units
        if direct_prompts and not batch_is_incomplete and not batch_is_polluted:
            return direct_prompts

        for source_index, source in enumerate(source_candidates):
            def complete_or_empty(items: list[str]) -> list[str]:
                if normalized_count and items and len(items) < normalized_count:
                    return []
                return items

            prompt_units = _extract_filename_social_asset_image_prompt_lines(
                str(source or ''),
                expected_count=normalized_count,
            )
            prompt_units = complete_or_empty(prompt_units)
            if not prompt_units:
                prompt_units = _extract_inline_labeled_image_prompt_lines(
                    str(source or ''),
                    expected_count=normalized_count,
                )
                prompt_units = complete_or_empty(prompt_units)
            if not prompt_units:
                prompt_units = _extract_sequential_bold_alpha_image_prompt_lines(
                    str(source or ''),
                    expected_count=normalized_count,
                    require_image_heading=source_index != 1,
                )
                prompt_units = complete_or_empty(prompt_units)
            if not prompt_units:
                prompt_units = _extract_social_manifest_pipe_image_prompt_lines(
                    str(source or ''),
                    expected_count=normalized_count,
                )
                prompt_units = complete_or_empty(prompt_units)
            if not prompt_units:
                prompt_units = _extract_numbered_image_prompt_section(
                    str(source or ''),
                    expected_count=normalized_count,
                )
                prompt_units = complete_or_empty(prompt_units)
            if (
                prompt_units
                and direct_prompts
                and _image_prompt_batch_looks_like_weak_social_copy(prompt_units)
            ):
                filename_prompt_units = _extract_filename_social_asset_image_prompt_lines(
                    str(source or ''),
                    expected_count=normalized_count,
                )
                if filename_prompt_units and (
                    not normalized_count or len(filename_prompt_units) >= normalized_count
                ):
                    prompt_units = filename_prompt_units
            if not prompt_units:
                prompt_units = _extract_html_image_card_prompt_units(
                    str(source or ''),
                    expected_count=normalized_count,
                )
                prompt_units = complete_or_empty(prompt_units)
            if not prompt_units:
                prompt_units = cls._extract_late_fill_image_prompt_units(source)
                prompt_units = complete_or_empty(prompt_units)
            if not prompt_units:
                prompt_units = cls._extract_late_fill_compact_numbered_image_prompt_units(source)
                prompt_units = complete_or_empty(prompt_units)
            prompt_units = [
                cls._strip_late_fill_prompt_label(item).strip()
                for item in prompt_units
                if cls._late_fill_structured_image_prompt_unit_is_viable(item)
            ]
            if prompt_units and (not normalized_count or len(prompt_units) >= normalized_count):
                return prompt_units
        if (
            normalized_count > 0
            and len(raw_items) == normalized_count
            and len(direct_prompts) != normalized_count
        ):
            return raw_items
        return direct_prompts

    @staticmethod
    def _extract_late_fill_numbered_image_asset_units(content: Any) -> list[str]:
        text = str(content or '').strip()
        if not text:
            return []
        heading_match = re.search(
            r'(?im)^\s*(?:[#>*-]+\s*)?(?:\*\*+|__+)?\s*'
            r'(?:(?:the\s+)?images?\s+should\s+be|image\s+generation\s+prompts?|visual\s+requirements|image\s+assets?)'
            r'\s*(?:\*\*+|__+)?\s*:?\s*$',
            text,
        )
        start_match = re.search(
            r'(?is)\b(?:first[,\s]+)?(?:identify\s+and\s+generate|create|generate)\s+'
            r'(?:exactly\s+)?\d+\s+(?:distinct\s+)?image\s+assets?\s*[:\-]',
            text,
        ) if not heading_match else None
        if not heading_match and not start_match:
            start_match = re.search(
                r'(?is)\b(?:(?:the\s+)?images?\s+should\s+be|visual\s+requirements|image\s+assets?|image\s+generation\s+prompts?)\s*[:\-]',
                text,
            )
        if not heading_match and not start_match:
            return []
        segment = text[(heading_match or start_match).end():]
        stop_match = re.search(
            r'(?ims)(?:^\s*(?:[#>*-]+\s*)?(?:\*\*+|__+)?\s*'
            r'(?:index\.html|styles\.css|html|css|javascript|js|page files?|text artifacts?|'
            r'(?:phase|internal phase|closure|materialization|artifact|runtime)\s+contract|'
            r'summary|notes|implementation notes)\b|'
            r'\b(?:then\s+create|then\s+write|the\s+html\s+must|html\s+must|'
            r'the\s+page\s+should|use\s+correct\s+relative\s+links|do\s+not\s+create\s+extra)\b)',
            segment,
        )
        if stop_match:
            segment = segment[:stop_match.start()]
        prompts = []
        for match in re.finditer(
            r'(?ms)(?:^|\s)(?:\d+)[.)]\s*(?P<body>.*?)(?=(?:\s+\d+[.)]\s+)|\Z)',
            segment,
        ):
            body = re.sub(r'\s+', ' ', match.group('body')).strip()
            body = re.sub(r'^[:\-–—]\s*', '', body).strip()
            if not body:
                continue
            lowered = body.lower()
            if any(token in lowered for token in ('index.html', 'styles.css', '<html', '</', 'url(')):
                continue
            if len(re.findall(r'\w+', body)) >= 3:
                prompts.append(body)
        return prompts if len(prompts) >= 2 else []

    @staticmethod
    def _late_fill_image_prompt_score(content: str) -> int:
        text = str(content or '').strip()
        if not text:
            return -100
        if LateFillRuntimeOwner._late_fill_image_prompt_is_code_polluted(text):
            return -100
        lowered = text.lower()
        words = re.findall(r'\w+', lowered)
        score = 0
        if re.search(r'\b(?:image\s*[- ]?\s*prompt|bild\s*[- ]?\s*prompt|bildprompt|prompt\s+\d*|visual prompt|poster\s*[- ]?\s*prompt|poster image)\b', lowered):
            score += 8
        if re.search(r'\b(?:poster|graphic design|cinematic|photo|photoreal|illustration|render|scene|lighting|composition|camera|style|fantasy|landscape|portrait|bild|szene)\b', lowered):
            score += 3
        if re.search(r'\b(?:compare|comparison|versus|caption|conclusion|after|nach der|slogan|ad copy|voiceover|audio|final sentence|references?\s+both|generated artifacts?)\b', lowered):
            score -= 5
        if len(words) < 6:
            score -= 3
        elif len(words) > 18:
            score += 1
        return score

    @staticmethod
    def _late_fill_speakable_text_score(content: str) -> int:
        text = str(content or '').strip()
        if not text:
            return -100
        lowered = text.lower()
        words = re.findall(r'\w+', lowered)
        score = 0
        if re.search(r'\b(?:ad copy|script|voiceover|narration|manuscript|spoken text|audio text|read aloud|tts)\b', lowered):
            score += 8
        if re.search(r'\b(?:image\s*[- ]?\s*prompt|bild\s*[- ]?\s*prompt|bildprompt|visual prompt|poster\s*[- ]?\s*prompt|poster image|graphic design|camera|photoreal|cinematic|render)\b', lowered):
            score -= 10
        if re.search(r'\b(?:slogan|headline|tagline)\b', lowered):
            score += 7
        if ':' in text and 3 <= len(words) <= 10:
            score += 3
        if re.search(r'\b(?:final sentence|references?\s+both|generated artifacts?|generated image|poster image)\b', lowered):
            score -= 6
        if (
            re.search(r'\b(?:audio|voice|spoken)\b', lowered)
            and re.search(r'\b(?:poster|image|visual|artifact)\b', lowered)
        ):
            score -= 10
        if len(words) < 4:
            score -= 4
        elif len(words) > 12:
            score += 2
        return score

    _artifact_evidence_text = staticmethod(BranchDependencyEvidence._artifact_evidence_text)

    _artifact_records_from_late_fill_result = staticmethod(branch_result_contracts._artifact_records_from_late_fill_result)

    _artifact_record_path = staticmethod(branch_result_contracts._artifact_record_path)

    def _image_artifact_record_sort_key(self, record: Mapping[str, Any]) -> tuple[int, int, str]:
        return self.linked_artifact_materialization._image_artifact_record_sort_key(record)

    _artifact_record_extension = staticmethod(branch_result_contracts._artifact_record_extension)

    _artifact_record_source_name = staticmethod(branch_result_contracts._artifact_record_source_name)

    _normalized_text_artifact_source_name_for_match = staticmethod(LinkedArtifactMaterialization._normalized_text_artifact_source_name_for_match)

    _artifact_record_matches_text_artifact_source_name = staticmethod(LinkedArtifactMaterialization._artifact_record_matches_text_artifact_source_name)

    _text_artifact_candidate_content = staticmethod(text_artifact_materialization._text_artifact_candidate_content)

    _text_artifact_nested_mapping = staticmethod(text_artifact_materialization._text_artifact_nested_mapping)

    _required_text_artifact_target_path = staticmethod(text_artifact_materialization._required_text_artifact_target_path)

    _required_text_artifact_request = staticmethod(text_artifact_materialization._required_text_artifact_request)

    _text_artifact_content_payload_error = staticmethod(text_artifact_materialization._text_artifact_content_payload_error)

    _text_artifact_candidate_looks_like_payload = staticmethod(text_artifact_materialization._text_artifact_candidate_looks_like_payload)

    _required_text_artifact_candidate_payloads = staticmethod(text_artifact_materialization._required_text_artifact_candidate_payloads)

    _with_required_text_artifact_saved_result = staticmethod(text_artifact_materialization._with_required_text_artifact_saved_result)

    @classmethod
    def _retained_input_alias_contract_from_plan(
        cls,
        plan: Mapping[str, Any],
    ) -> dict[str, Any]:
        branch_wrapper = plan.get('branch') if isinstance(plan.get('branch'), Mapping) else {}
        branch = (
            branch_wrapper.get('branch')
            if isinstance(branch_wrapper.get('branch'), Mapping)
            else branch_wrapper
        )
        sources = [
            source
            for source in (
                plan.get('effective_data'),
                branch,
                plan.get('execution_contract'),
            )
            if isinstance(source, Mapping)
        ]
        contract_candidates: list[Mapping[str, Any]] = []
        for source in sources:
            artifact_request = (
                source.get('artifact_request')
                if isinstance(source.get('artifact_request'), Mapping)
                else source.get('text_artifact_request')
                if isinstance(source.get('text_artifact_request'), Mapping)
                else {}
            )
            if artifact_request:
                contract_candidates.append(artifact_request)
            contract_candidates.append(source)
        retained_requested = any(
            str(candidate.get('stage_direction') or '').strip()
            == 'materialize_retained_input_alias'
            or candidate.get('retained_input_alias_required') is True
            for candidate in contract_candidates
        )
        if not retained_requested:
            return {}

        identity_keys = (
            'stage_direction',
            'text_artifact_extension',
            'text_artifact_source_name',
            'retained_input_alias_required',
            'retained_input_binding_state',
            'retained_input_source_path',
            'retained_input_source_name',
            'retained_input_target_name',
        )
        observed_values: dict[str, dict[Any, Any]] = {}

        def comparable_value(key: str, value: Any) -> Any:
            if key == 'retained_input_alias_required':
                return bool(value)
            token = str(value).strip()
            if key in {
                'stage_direction',
                'text_artifact_extension',
                'retained_input_binding_state',
            }:
                return token.casefold().lstrip('.')
            if key in {
                'text_artifact_source_name',
                'retained_input_source_name',
                'retained_input_target_name',
            }:
                return Path(token).name.casefold()
            if key == 'retained_input_source_path':
                return str(Path(token).expanduser().resolve(strict=False))
            return token

        for candidate in contract_candidates:
            for key in identity_keys:
                value = candidate.get(key)
                if value in (None, '', [], {}):
                    continue
                observed_values.setdefault(key, {})[
                    comparable_value(key, value)
                ] = value
        conflicts = {
            key: list(values.values())
            for key, values in observed_values.items()
            if len(values) > 1
        }
        if conflicts:
            conflict_keys = ', '.join(sorted(conflicts))
            raise RuntimeError(
                'RETAINED_INPUT_ALIAS_CONTRACT_CONFLICT: retained input '
                f'identity disagrees across plan carriers ({conflict_keys}).'
            )

        contract: dict[str, Any] = {}
        for candidate in contract_candidates:
            for key in identity_keys:
                value = candidate.get(key)
                if value not in (None, '', [], {}):
                    contract[key] = value
        return contract

    _sha256_for_file = staticmethod(TextArtifactFiles._sha256_for_file)

    def _materialize_retained_input_alias(
        self,
        plan: Mapping[str, Any],
        contract: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self.text_artifact_files._materialize_retained_input_alias(plan, contract)

    _materialize_required_text_artifact_target_path = staticmethod(text_artifact_materialization._materialize_required_text_artifact_target_path)

    _text_artifact_saved_payload_error = staticmethod(text_artifact_materialization._text_artifact_saved_payload_error)

    _saved_text_paths_from_result = staticmethod(text_artifact_materialization._saved_text_paths_from_result)

    _text_artifact_target_binding_violation = staticmethod(text_artifact_materialization._text_artifact_target_binding_violation)

    _text_artifact_saved_binding_violation = staticmethod(TextArtifactResultEvidence._text_artifact_saved_binding_violation)

    def capture_root_text_artifact_saved_evidence(
        self, result: dict[str, Any], *, accepted_requests: list[dict[str, Any]],
        response_id: str, phase_id: str = '',
    ) -> dict[str, Any]:
        return self.text_artifact_result_evidence.capture_root_text_artifact_saved_evidence(result, accepted_requests=accepted_requests, response_id=response_id, phase_id=phase_id)

    def _matching_canonical_text_artifact_path(
        self,
        payload: Mapping[str, Any],
        *,
        extension: str,
        source_name: str,
        target_path: str = '',
        generic: bool = False,
    ) -> str:
        return self.text_artifact_result_evidence._matching_canonical_text_artifact_path(payload, extension=extension, source_name=source_name, target_path=target_path, generic=generic)

    def _canonical_text_artifact_saved_result(
        self,
        payload: Mapping[str, Any],
        *,
        extension: str,
        source_name: str,
        target_path: str = '',
        allow_deterministic_repair: bool = False,
        generic: bool = False,
    ) -> dict[str, Any]:
        return self.text_artifact_result_evidence._canonical_text_artifact_saved_result(payload, extension=extension, source_name=source_name, target_path=target_path, allow_deterministic_repair=allow_deterministic_repair, generic=generic)

    def _ensure_required_text_artifact_saved_truth(
        self,
        branch: Mapping[str, Any],
        infer_result: dict[str, Any],
        effective_data: Mapping[str, Any],
        current_payload: Mapping[str, Any],
    ) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
        return self.text_artifact_result_evidence._ensure_required_text_artifact_saved_truth(branch, infer_result, effective_data, current_payload)

    def _canonical_text_artifact_branch_fulfillment(
        self,
        branch: Mapping[str, Any],
        *payloads: Mapping[str, Any],
        allow_deterministic_repair: bool = True,
    ) -> dict[str, Any]:
        return self.text_artifact_result_evidence._canonical_text_artifact_branch_fulfillment(branch, *payloads, allow_deterministic_repair=allow_deterministic_repair)

    def _text_artifact_branch_has_canonical_evidence(
        self,
        branch: Mapping[str, Any],
        payload: Mapping[str, Any],
    ) -> bool:
        return self.text_artifact_result_evidence._text_artifact_branch_has_canonical_evidence(branch, payload)

    _authoritative_bounded_text_artifact_repair_has_write_evidence = staticmethod(TextArtifactResultEvidence._authoritative_bounded_text_artifact_repair_has_write_evidence)

    def _reconcile_satisfied_failed_text_artifact_branches(
        self,
        payload: Mapping[str, Any],
        late_fill: Mapping[str, Any],
    ) -> dict[str, Any]:
        updated = dict(late_fill or {})
        failed_records = [
            dict(item)
            for item in (updated.get('failed_branches') or [])
            if isinstance(item, Mapping)
        ]
        pending_records = [
            dict(item)
            for item in (updated.get('pending_branches') or [])
            if isinstance(item, Mapping)
        ]
        active_records = [
            dict(item)
            for item in (updated.get('active_branches') or [])
            if isinstance(item, Mapping)
        ]
        if not failed_records and not pending_records and not active_records:
            return updated
        completed_records = [
            dict(item)
            for item in (updated.get('completed_branches') or [])
            if isinstance(item, Mapping)
        ]
        completed_ids = {
            self.branch_id(item)
            for item in completed_records
            if self.branch_id(item)
        }
        reconciled_ids: set[str] = set()
        remaining_failed: list[dict[str, Any]] = []
        remaining_pending: list[dict[str, Any]] = []
        remaining_active: list[dict[str, Any]] = []
        reconciled: list[dict[str, Any]] = []

        def branch_has_satisfied_text_evidence(branch: Mapping[str, Any]) -> bool:
            role = str(branch.get('role') or '').strip()
            artifact_request = (
                branch.get('artifact_request')
                if isinstance(branch.get('artifact_request'), Mapping)
                else {}
            )
            looks_like_text_artifact = (
                str(branch.get('output_type') or '').strip().lower() == 'text'
                or role == 'text_artifact_output'
                or bool(str(branch.get('text_artifact_extension') or '').strip())
                or bool(str(artifact_request.get('extension') or '').strip())
            )
            return bool(
                looks_like_text_artifact
                and self._text_artifact_branch_has_canonical_evidence(branch, payload)
            )

        def remember_satisfied_branch(branch: Mapping[str, Any]) -> None:
            branch_id = self.branch_id(branch)
            fulfilled_branch = dict(branch)
            fulfilled_branch['status'] = 'fulfilled'
            fulfilled_branch['evidence'] = 'canonical_text_artifact_evidence'
            fulfilled_branch['non_blocking_after_final_contract_fulfilled'] = True
            for key in (
                'error',
                'recovery_context',
                'recovery_state',
                'attempt',
                'materialization_contract_open_checks',
                'materialization_contract_unmet',
            ):
                fulfilled_branch.pop(key, None)
            if branch_id:
                reconciled_ids.add(branch_id)
            if branch_id and branch_id not in completed_ids:
                completed_records.append(fulfilled_branch)
                completed_ids.add(branch_id)
            reconciled.append(
                {
                    key: value
                    for key, value in fulfilled_branch.items()
                    if key in {
                        'branch_id',
                        'phase_id',
                        'capability',
                        'output_type',
                        'artifact_request',
                        'status',
                        'evidence',
                        'non_blocking_after_final_contract_fulfilled',
                    }
                    and value not in (None, '', [], {})
                }
            )

        for branch in failed_records:
            if (
                branch_has_satisfied_text_evidence(branch)
            ):
                remember_satisfied_branch(branch)
                continue
            remaining_failed.append(branch)

        for branch in pending_records:
            if branch_has_satisfied_text_evidence(branch):
                remember_satisfied_branch(branch)
                continue
            remaining_pending.append(branch)

        for branch in active_records:
            branch_id = self.branch_id(branch)
            if branch_id and branch_id in reconciled_ids:
                continue
            if branch_has_satisfied_text_evidence(branch):
                remember_satisfied_branch(branch)
                continue
            remaining_active.append(branch)

        if not reconciled:
            return updated
        updated['completed_branches'] = completed_records
        updated['completed_branch_count'] = len(completed_records)
        updated['failed_branches'] = remaining_failed
        updated['failed_branch_count'] = len(remaining_failed)
        updated['pending_branches'] = remaining_pending
        updated['pending_branch_count'] = len(remaining_pending)
        updated['active_branches'] = remaining_active
        previous_reconciled = [
            dict(item)
            for item in (updated.get('satisfied_failed_branches') or [])
            if isinstance(item, Mapping)
        ]
        updated['satisfied_failed_branches'] = previous_reconciled + reconciled
        if reconciled_ids:
            updated['recovery_candidates'] = [
                dict(item)
                for item in (updated.get('recovery_candidates') or [])
                if isinstance(item, Mapping)
                and self.branch_id(item) not in reconciled_ids
            ]
            updated['materialization_contract_demoted_branches'] = [
                dict(item)
                for item in (updated.get('materialization_contract_demoted_branches') or [])
                if isinstance(item, Mapping)
                and self.branch_id(item) not in reconciled_ids
            ]
        if not remaining_failed and not remaining_pending and not remaining_active:
            updated['failed_capabilities'] = []
            updated['pending_capabilities'] = []
            updated['active_capabilities'] = []
            updated['recovery_candidates'] = []
            for key in ('error', 'error_summary', 'failed_at', 'partial_failure', 'auto_recovery_enabled'):
                updated.pop(key, None)
            updated['status'] = 'completed'
        return updated

    _relative_artifact_link = staticmethod(LinkedArtifactMaterialization._relative_artifact_link)

    _url_is_external_or_empty = staticmethod(LinkedArtifactMaterialization._url_is_external_or_empty)

    _link_rebind_is_dynamic_template_url = staticmethod(LinkedArtifactMaterialization._link_rebind_is_dynamic_template_url)

    @staticmethod
    def _link_tokens_for_artifact(record: Mapping[str, Any]) -> set[str]:
        tokens: set[str] = set()
        path = branch_result_contracts._artifact_record_path(record)
        for value in (
            path,
            Path(path).name if path else '',
            str(record.get('url') or '').strip(),
            str(record.get('artifact_ref') or record.get('ref') or '').strip(),
            branch_result_contracts._artifact_record_source_name(record),
        ):
            token = str(value or '').strip()
            if token:
                tokens.add(token)
        return {token for token in tokens if len(token) >= 3}

    _link_rebind_search_text = staticmethod(LinkedArtifactMaterialization._link_rebind_search_text)

    _link_rebind_semantic_tokens = staticmethod(LinkedArtifactMaterialization._link_rebind_semantic_tokens)

    _link_rebind_semantic_score = staticmethod(LinkedArtifactMaterialization._link_rebind_semantic_score)

    def _collect_link_rebind_artifact_records(self, payload: Mapping[str, Any]) -> list[dict[str, Any]]:
        return self.linked_artifact_materialization._collect_link_rebind_artifact_records(payload)

    _preferred_asset_for_url = staticmethod(LinkedArtifactMaterialization._preferred_asset_for_url)

    _link_rebind_url_matches_record_identity = staticmethod(LinkedArtifactMaterialization._link_rebind_url_matches_record_identity)

    _exact_asset_record_for_url = staticmethod(LinkedArtifactMaterialization._exact_asset_record_for_url)

    _unique_artifact_records_by_path = staticmethod(LinkedArtifactMaterialization._unique_artifact_records_by_path)

    _link_rebind_extension_families = staticmethod(LinkedArtifactMaterialization._link_rebind_extension_families)

    _link_rebind_record_declared_families = staticmethod(LinkedArtifactMaterialization._link_rebind_record_declared_families)

    _link_rebind_record_families = staticmethod(LinkedArtifactMaterialization._link_rebind_record_families)

    _link_rebind_record_identity_tokens = staticmethod(LinkedArtifactMaterialization._link_rebind_record_identity_tokens)

    _link_rebind_dependency_values = staticmethod(LinkedArtifactMaterialization._link_rebind_dependency_values)

    _link_rebind_consumer_dependency_ids = staticmethod(LinkedArtifactMaterialization._link_rebind_consumer_dependency_ids)

    _link_rebind_asset_records_for_consumer = staticmethod(LinkedArtifactMaterialization._link_rebind_asset_records_for_consumer)

    _link_rebind_normalize_json_key = staticmethod(LinkedArtifactMaterialization._link_rebind_normalize_json_key)

    _link_rebind_json_path_key_family = staticmethod(LinkedArtifactMaterialization._link_rebind_json_path_key_family)

    _link_rebind_infer_single_family = staticmethod(LinkedArtifactMaterialization._link_rebind_infer_single_family)

    _link_rebind_attr_context_family = staticmethod(LinkedArtifactMaterialization._link_rebind_attr_context_family)

    _link_rebind_css_context_family = staticmethod(LinkedArtifactMaterialization._link_rebind_css_context_family)

    _link_rebind_family_matches = staticmethod(LinkedArtifactMaterialization._link_rebind_family_matches)

    _link_rebind_records_for_family = staticmethod(LinkedArtifactMaterialization._link_rebind_records_for_family)

    _link_rebind_records_for_extension = staticmethod(LinkedArtifactMaterialization._link_rebind_records_for_extension)

    _local_link_target_exists = staticmethod(LinkedArtifactMaterialization._local_link_target_exists)

    _local_link_target_path = staticmethod(LinkedArtifactMaterialization._local_link_target_path)

    _link_url_needs_rebind = staticmethod(LinkedArtifactMaterialization._link_url_needs_rebind)

    def _rebind_text_artifact_content(
        self,
        content: str,
        *,
        target_path: str,
        target_record: Mapping[str, Any],
        asset_records: list[dict[str, Any]],
        fallback_asset_records: Optional[list[dict[str, Any]]] = None,
        static_fetch_asset_records: Optional[list[dict[str, Any]]] = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        return self.linked_artifact_materialization._rebind_text_artifact_content(content, target_path=target_path, target_record=target_record, asset_records=asset_records, fallback_asset_records=fallback_asset_records, static_fetch_asset_records=static_fetch_asset_records)

    def _rebind_json_artifact_content(
        self,
        content: str,
        *,
        target_path: str,
        asset_records: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]]]:
        return self.linked_artifact_materialization._rebind_json_artifact_content(content, target_path=target_path, asset_records=asset_records)

    def _terminal_link_rebind_write_owners(
        self,
        payload: Mapping[str, Any],
        records: list[dict[str, Any]],
        *,
        target_path: str,
        original: str,
        rebound: str,
        asset_records: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        return self.linked_artifact_materialization._terminal_link_rebind_write_owners(payload, records, target_path=target_path, original=original, rebound=rebound, asset_records=asset_records)

    def rebind_terminal_linked_artifacts(self, payload: dict[str, Any], *, current_outputs: Optional[list[dict[str, Any]]]=None, accepted_fill_results: Optional[list[dict[str, Any]]]=None) -> dict[str, Any]:
        return self.linked_artifact_materialization.rebind_terminal_linked_artifacts(payload, current_outputs=current_outputs, accepted_fill_results=accepted_fill_results)

    @observe_state('late_fill.graph_closure_refresh', 'terminal_materialization_state', 'closure_reviewed_response', labels=('NEW_AUTHORITY_BOUNDARY',), new_authority_boundary=True)
    def refresh_terminal_graph_closure_review(
        self,
        payload: dict[str, Any],
        *,
        request_payload: dict[str, Any],
        route_payload: Optional[dict[str, Any]],
        artifact_gap: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            review = self.build_graph_closure_review(
                str((payload or {}).get('output_text') or ''),
                route_payload=route_payload,
                request_payload=request_payload,
                artifact_payload=payload,
                artifact_gap=artifact_gap,
            )
        except Exception as exc:  # noqa: BLE001
            logging.warning('Could not refresh terminal graph closure review: %s', exc)
            return payload
        return self.attach_graph_closure_review_diagnostics(payload, review)

    def refresh_runtime_graph_repair_evidence(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Refresh current repair diagnostics while preserving graph audit records."""

        if not callable(self.attach_runtime_graph_repair_evidence):
            return payload
        try:
            refreshed = self.attach_runtime_graph_repair_evidence(payload)
        except Exception as exc:  # noqa: BLE001
            logging.warning('Could not refresh runtime graph repair evidence: %s', exc)
            return payload
        return refreshed if isinstance(refreshed, dict) else payload

    @staticmethod
    def _inline_text_artifact_block_languages(content: str) -> set[str]:
        languages: set[str] = set()
        for match in _INLINE_TEXT_ARTIFACT_FENCE_RE.finditer(str(content or '')):
            language = re.sub(
                r'[^a-z0-9]+',
                '',
                str(match.group('lang') or '').strip().lower(),
            )
            if language:
                languages.add(language)
        return languages

    @classmethod
    def _inline_text_artifact_requests_for_text(cls, content: str) -> list[dict[str, str]]:
        text = str(content or '').strip()
        if not text or text_artifact_content_is_materializer_instruction_echo(text):
            return []
        languages = cls._inline_text_artifact_block_languages(text)
        has_html_payload = bool(_INLINE_COMPLETE_HTML_RE.search(text)) or bool(languages & {'html', 'htm'})
        if not has_html_payload:
            return []
        requests = [{'extension': 'html', 'source_name': 'index', 'source': 'terminal_inline_output'}]
        if languages & {'css'}:
            requests.append({'extension': 'css', 'source_name': 'styles', 'source': 'terminal_inline_output'})
        return requests

    @staticmethod
    def _inline_text_source_items(payload: Mapping[str, Any]) -> list[dict[str, str]]:
        if not isinstance(payload, Mapping):
            return []
        source_items: list[dict[str, str]] = []
        seen_texts: set[str] = set()

        def add_source(raw_text: Any, source: str) -> None:
            if not isinstance(raw_text, str):
                return
            text = raw_text.strip()
            if not text or text in seen_texts:
                return
            seen_texts.add(text)
            source_items.append({'source': source, 'content': text})

        for output in payload.get('outputs') or []:
            if not isinstance(output, Mapping):
                continue
            output_type = str(output.get('type') or output.get('kind') or '').strip().lower()
            for key in ('value', 'text', 'content', 'content_payload', 'output_text'):
                raw_text = output.get(key)
                if not isinstance(raw_text, str) or not raw_text.strip():
                    continue
                if output_type and output_type not in {'text', 'document', 'html', 'css'}:
                    if not _INLINE_COMPLETE_HTML_RE.search(raw_text):
                        continue
                add_source(raw_text, f"outputs.{str(output.get('slot_id') or output.get('branch_id') or key).strip() or key}")
        add_source(payload.get('content_payload'), 'content_payload')
        add_source(payload.get('output_text'), 'output_text')
        return source_items

    @classmethod
    def find_inline_text_artifact_candidates(
        cls,
        payload: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for source_item in cls._inline_text_source_items(payload):
            content = source_item.get('content') or ''
            requests = cls._inline_text_artifact_requests_for_text(content)
            if not requests:
                continue
            payloads = extract_text_artifact_payloads(content, requests)
            source_candidates: list[dict[str, Any]] = []
            for payload_item in payloads:
                if not isinstance(payload_item, Mapping):
                    continue
                artifact_request = (
                    payload_item.get('artifact_request')
                    if isinstance(payload_item.get('artifact_request'), Mapping)
                    else {}
                )
                extension = re.sub(
                    r'[^a-z0-9]+',
                    '',
                    str(artifact_request.get('extension') or '').strip().lower().lstrip('.'),
                )
                if extension == 'htm':
                    extension = 'html'
                if extension not in _INLINE_HTML_CSS_EXTENSIONS:
                    continue
                candidate_content = str(payload_item.get('content') or '').strip()
                if not candidate_content or text_artifact_content_is_materializer_instruction_echo(candidate_content):
                    continue
                if extension == 'html' and not _INLINE_COMPLETE_HTML_RE.search(candidate_content):
                    continue
                if extension == 'css' and not re.search(r'(?s)[{};]', candidate_content):
                    continue
                source_name = str(
                    artifact_request.get('source_name')
                    or ('styles' if extension == 'css' else 'index')
                ).strip()
                key = (extension, source_name.lower(), candidate_content)
                if key in seen:
                    continue
                seen.add(key)
                source_candidates.append(
                    {
                        'extension': extension,
                        'source_name': source_name,
                        'content': candidate_content,
                        'source': source_item.get('source') or 'inline_output',
                        'artifact_request': {
                            'extension': extension,
                            'source_name': source_name,
                            'source': 'terminal_inline_output',
                        },
                    }
                )
            if any(candidate.get('extension') == 'html' for candidate in source_candidates):
                candidates.extend(source_candidates)
        return candidates

    @classmethod
    def _payload_has_inline_html_css_signal(cls, payload: Mapping[str, Any]) -> bool:
        for source_item in cls._inline_text_source_items(payload):
            content = source_item.get('content') or ''
            if cls._inline_text_artifact_requests_for_text(content):
                return True
        return False

    def _terminal_generated_image_records(self, payload: Mapping[str, Any]) -> list[dict[str, Any]]:
        return self.linked_artifact_materialization._terminal_generated_image_records(payload)

    def _payload_has_durable_html_css_text_artifact(self, payload: Mapping[str, Any]) -> bool:
        records = self.linked_artifact_materialization._collect_link_rebind_artifact_records(payload)
        for record in records:
            if str(record.get('type') or record.get('kind') or '').strip().lower() != 'text':
                continue
            if branch_result_contracts._artifact_record_extension(record) not in _INLINE_HTML_CSS_EXTENSIONS:
                continue
            path = branch_result_contracts._artifact_record_path(record)
            if not path:
                continue
            try:
                if Path(path).expanduser().is_file():
                    return True
            except OSError:
                continue
        return False

    @staticmethod
    def _inline_text_artifact_mime_type(extension: str) -> str:
        ext = str(extension or '').strip().lower().lstrip('.')
        if ext in {'html', 'htm'}:
            return 'text/html'
        if ext == 'css':
            return 'text/css'
        return 'text/plain'

    @staticmethod
    def _inline_text_artifact_open_check(
        candidate: Mapping[str, Any],
        *,
        reason: str,
        error: Optional[str] = None,
    ) -> dict[str, Any]:
        extension = str(candidate.get('extension') or 'html').strip().lower().lstrip('.') or 'html'
        source_name = str(candidate.get('source_name') or ('styles' if extension == 'css' else 'index')).strip()
        check = {
            'check_kind': 'inline_text_artifact_materialization',
            'status': 'pending',
            'evidence': 'inline_text_artifact_unmaterialized',
            'reason': reason,
            'capability': 'chat',
            'output_type': 'text',
            'role': 'text_artifact_output',
            'stage_direction': 'materialize_requested_text_artifact',
            'requires_artifact': True,
            'text_artifact_extension': extension,
            'text_artifact_source_name': source_name,
            'text_artifact_source': 'terminal_inline_output',
            'repair_action': RECOVERY_ACTION_RETRY_SAME_BRANCH,
            'recovery_action': RECOVERY_ACTION_RETRY_SAME_BRANCH,
            'repair_action_reason': 'inline HTML/CSS output must be saved as a durable text artifact before closure',
            'source': candidate.get('source') or 'inline_output',
        }
        if error:
            check['error'] = error
        return {key: value for key, value in check.items() if value not in (None, '', [], {})}

    @staticmethod
    def _canonical_terminal_inline_text_artifact_entry(
        entry: Mapping[str, Any],
        *,
        response_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        raw_entry = dict(entry or {})
        identity_record = {
            'type': 'text',
            'kind': 'text',
            'path': raw_entry.get('path'),
            'name': raw_entry.get('source_name') or raw_entry.get('name'),
            'mime_type': raw_entry.get('mime_type'),
            'origin': raw_entry.get('origin') or 'assistant_output',
            'source_response_id': response_payload.get('id'),
            'provenance_id': response_payload.get('provenance_id'),
            'derived_from': response_payload.get('derived_from'),
        }
        canonical = sanitize_artifact_record(
            identity_record,
            default_kind='text',
            default_origin='assistant_output',
        )
        if canonical:
            raw_entry.update(canonical)
        return {key: value for key, value in raw_entry.items() if value not in (None, '', [], {})}

    def _materialize_inline_text_artifacts_for_terminal_closure(
        self,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if not isinstance(payload, dict):
            return payload, []
        if not self.linked_artifact_materialization._terminal_generated_image_records(payload):
            return payload, []
        if self._payload_has_durable_html_css_text_artifact(payload):
            return payload, []

        candidates = self.find_inline_text_artifact_candidates(payload)
        if not candidates:
            if self._payload_has_inline_html_css_signal(payload):
                return payload, [
                    self._inline_text_artifact_open_check(
                        {'extension': 'html', 'source_name': 'index', 'source': 'inline_output'},
                        reason='inline HTML/CSS-like output was present but no complete safe file payload could be extracted',
                    )
                ]
            return payload, []

        updated = dict(payload)
        model_name = str(
            ((updated.get('target') or {}).get('model') if isinstance(updated.get('target'), Mapping) else '')
            or updated.get('model')
            or updated.get('model_name')
            or 'terminal-inline-text-artifact'
        ).strip()
        saved_entries: list[dict[str, Any]] = []
        open_checks: list[dict[str, Any]] = []
        for candidate in candidates:
            extension = str(candidate.get('extension') or 'html').strip().lower().lstrip('.') or 'html'
            source_name = str(candidate.get('source_name') or ('styles' if extension == 'css' else 'index')).strip()
            content = str(candidate.get('content') or '').strip()
            try:
                saved_path = persist_text_artifact_locally(
                    content,
                    model_name=model_name,
                    source_name=source_name,
                    mode='terminal_inline_text_artifact',
                    extension=extension,
                    output_dir=ARTIFACT_OUTPUTS_DOCUMENTS_DIR,
                    target_path=str(candidate.get('target_path') or '').strip() or None,
                )
            except Exception as exc:  # noqa: BLE001
                logging.warning('Could not materialize inline %s artifact during terminal closure: %s', extension, exc)
                saved_path = None
                open_checks.append(
                    self._inline_text_artifact_open_check(
                        candidate,
                        reason='inline HTML/CSS output could not be saved as a durable text artifact',
                        error=str(exc),
                    )
                )
            if not saved_path:
                if not any(
                    item.get('text_artifact_extension') == extension
                    and item.get('text_artifact_source_name') == source_name
                    for item in open_checks
                ):
                    open_checks.append(
                        self._inline_text_artifact_open_check(
                            candidate,
                            reason='inline HTML/CSS output could not be saved as a durable text artifact',
                        )
                    )
                continue
            artifact_request = dict(candidate.get('artifact_request') or {})
            artifact_request.setdefault('extension', extension)
            artifact_request.setdefault('source_name', source_name)
            artifact_request.setdefault('source', 'terminal_inline_output')
            saved_entries.append(
                self._canonical_terminal_inline_text_artifact_entry(
                    {
                        'type': 'text',
                        'kind': 'text',
                        'path': saved_path,
                        'name': source_name,
                        'source_name': source_name,
                        'extension': extension,
                        'mime_type': self._inline_text_artifact_mime_type(extension),
                        'origin': 'assistant_output',
                        'document_output_kind': 'document',
                        'text_artifact_extension': extension,
                        'text_artifact_source_name': source_name,
                        'text_artifact_source': 'terminal_inline_output',
                        'text_artifact_request': artifact_request,
                        'artifact_request': artifact_request,
                        'content': content,
                        'result_text': content,
                        'source': candidate.get('source') or 'inline_output',
                    },
                    response_payload=updated,
                )
            )

        if not saved_entries:
            return updated, open_checks

        existing_saved_text_artifacts = [
            dict(item)
            for item in (updated.get('saved_text_artifacts') or [])
            if isinstance(item, Mapping)
        ]
        updated['saved_text_artifacts'] = branch_result_contracts.merge_unique_artifact_records(
            existing_saved_text_artifacts,
            saved_entries,
        )
        first_entry = saved_entries[0]
        updated.setdefault('saved_text_path', first_entry.get('path'))
        updated.setdefault('document_output_kind', 'document')
        updated.setdefault('text_artifact_request', first_entry.get('artifact_request'))
        existing_requests = [
            dict(item)
            for item in (updated.get('text_artifact_requests') or [])
            if isinstance(item, Mapping)
        ]
        updated['text_artifact_requests'] = [
            *existing_requests,
            *[
                dict(entry.get('artifact_request') or {})
                for entry in saved_entries
                if isinstance(entry.get('artifact_request'), Mapping)
            ],
        ]
        updated['artifacts'] = branch_result_contracts.merge_unique_artifact_records(
            updated.get('artifacts'),
            saved_entries,
        )
        late_fill = dict(updated.get('late_fill') or {}) if isinstance(updated.get('late_fill'), Mapping) else {}
        fill_results = [
            dict(item)
            for item in (late_fill.get('fill_results') or [])
            if isinstance(item, Mapping)
        ]
        completed_branches = [
            dict(item)
            for item in (late_fill.get('completed_branches') or [])
            if isinstance(item, Mapping)
        ]
        existing_result_paths = {
            str(item.get('saved_text_path') or '').strip()
            for item in fill_results
            if str(item.get('saved_text_path') or '').strip()
        }
        for index, entry in enumerate(saved_entries, start=1):
            path = str(entry.get('path') or '').strip()
            branch_id = f'branch-terminal-inline_text_artifact-{index}'
            if path and path not in existing_result_paths:
                fill_results.append(
                    {
                        'branch_id': branch_id,
                        'phase_id': branch_id,
                        'capability': 'chat',
                        'output_type': 'text',
                        'status': 'fulfilled',
                        'saved_text_path': path,
                        'result_text': entry.get('result_text'),
                        'content_payload': entry.get('content'),
                        'text_artifact_extension': entry.get('text_artifact_extension'),
                        'text_artifact_source_name': entry.get('text_artifact_source_name'),
                        'text_artifact_source': 'terminal_inline_output',
                        'artifact_request': entry.get('artifact_request'),
                        'artifact_id': entry.get('artifact_id'),
                        'artifact_ref': entry.get('artifact_ref'),
                        'ref': entry.get('ref'),
                        'source_response_id': entry.get('source_response_id'),
                        'evidence': 'terminal_inline_text_artifact_materialized',
                    }
                )
                existing_result_paths.add(path)
            completed_branches.append(
                {
                    'branch_id': branch_id,
                    'phase_id': branch_id,
                    'capability': 'chat',
                    'output_type': 'text',
                    'status': 'fulfilled',
                    'saved_text_path': path,
                    'text_artifact_extension': entry.get('text_artifact_extension'),
                    'text_artifact_source_name': entry.get('text_artifact_source_name'),
                    'text_artifact_source': 'terminal_inline_output',
                    'artifact_request': entry.get('artifact_request'),
                    'artifact_id': entry.get('artifact_id'),
                    'artifact_ref': entry.get('artifact_ref'),
                    'ref': entry.get('ref'),
                    'source_response_id': entry.get('source_response_id'),
                    'evidence': 'terminal_inline_text_artifact_materialized',
                }
            )
        late_fill['fill_results'] = fill_results
        late_fill['completed_branches'] = completed_branches
        late_fill['completed_branch_count'] = len(completed_branches)
        late_fill['inline_text_artifact_materialization_status'] = 'applied'
        late_fill['inline_text_artifact_materialized_count'] = len(saved_entries)
        late_fill['inline_text_artifact_materialized_paths'] = [
            entry.get('path') for entry in saved_entries if entry.get('path')
        ]
        updated = self.attach_late_fill_state(updated, late_fill)
        return updated, open_checks

    def _repair_terminal_text_artifact_syntax(
        self,
        payload: dict[str, Any],
        *,
        accepted_fill_results: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        return self.text_artifact_files._repair_terminal_text_artifact_syntax(payload, accepted_fill_results=accepted_fill_results)

    def _refresh_terminal_text_artifacts_from_saved_files(
        self,
        payload: dict[str, Any],
        *,
        accepted_fill_results: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return payload
        records = self.linked_artifact_materialization._collect_link_rebind_artifact_records(payload)
        text_records = LinkedArtifactMaterialization._unique_artifact_records_by_path(
            [
                record
                for record in records
                if str(record.get('type') or record.get('kind') or '').strip().lower() == 'text'
                and branch_result_contracts._artifact_record_path(record)
            ]
        )
        if not text_records:
            return payload

        def normalize_path(path: Any) -> str:
            token = str(path or '').strip()
            if not token:
                return ''
            return str(Path(token).expanduser().resolve(strict=False))

        updated_payload = dict(payload or {})
        refreshed_by_path: dict[str, dict[str, Any]] = {}
        path_by_artifact_ref: dict[str, str] = {}
        refresh_entries: list[dict[str, Any]] = []
        for record in text_records:
            artifact_ref = str(
                record.get('artifact_ref') or record.get('ref') or ''
            ).strip()
            record_path = normalize_path(branch_result_contracts._artifact_record_path(record))
            if artifact_ref and record_path:
                path_by_artifact_ref.setdefault(artifact_ref, record_path)
            refreshed, metadata = refresh_text_artifact_record_from_saved_path(record)
            if metadata.get('final_text_artifact_refresh_status') != 'refreshed':
                continue
            path = normalize_path(branch_result_contracts._artifact_record_path(refreshed))
            if not path:
                continue
            refreshed_by_path[path] = {
                key: refreshed.get(key)
                for key in (
                    'content',
                    'content_length_chars',
                    'content_preview_truncated',
                    'content_sha256',
                    'content_source',
                    'extension',
                    'file_sha256',
                    'file_size_bytes',
                    'path',
                )
                if refreshed.get(key) not in (None, '', [], {})
            }
            refresh_entries.append(
                {
                    'kind': 'fruth.final_text_artifact_refresh',
                    'target_path': path,
                    'target_extension': metadata.get('text_artifact_extension')
                    or branch_result_contracts._artifact_record_extension(refreshed),
                    'target_source_name': branch_result_contracts._artifact_record_source_name(record),
                    'content_sha256': metadata.get('content_sha256'),
                    'file_sha256': metadata.get('file_sha256'),
                    'file_size_bytes': metadata.get('file_size_bytes'),
                    'syntax_sanity_status': metadata.get('syntax_sanity_status'),
                    'syntax_sanity_issue_count': metadata.get('syntax_sanity_issue_count'),
                    'status': 'applied',
                    'source': 'terminal_final_saved_text_artifact',
                }
            )
        if not refreshed_by_path:
            return updated_payload

        def refresh_text_record(raw_record: Any) -> Any:
            if not isinstance(raw_record, dict):
                return raw_record
            record = dict(raw_record)
            path = normalize_path(branch_result_contracts._artifact_record_path(record))
            if not path:
                artifact_ref = str(
                    record.get('artifact_ref') or record.get('ref') or ''
                ).strip()
                path = path_by_artifact_ref.get(artifact_ref, '')
            refreshed = refreshed_by_path.get(path)
            if not refreshed:
                return record
            record.update(refreshed)
            content = refreshed.get('content')
            if isinstance(content, str):
                if 'value' in record:
                    record['value'] = content
                if 'text' in record:
                    record['text'] = content
                if 'result_text' in record:
                    record['result_text'] = content
                if 'content_payload' in record:
                    record['content_payload'] = content
            return record

        if isinstance(updated_payload.get('artifacts'), list):
            updated_payload['artifacts'] = [
                refresh_text_record(item)
                for item in updated_payload.get('artifacts') or []
            ]
        if isinstance(updated_payload.get('saved_text_artifacts'), list):
            updated_payload['saved_text_artifacts'] = [
                refresh_text_record(item)
                for item in updated_payload.get('saved_text_artifacts') or []
            ]
        if isinstance(updated_payload.get('outputs'), list):
            updated_payload['outputs'] = [
                refresh_text_record(item)
                for item in updated_payload.get('outputs') or []
            ]
        if isinstance(updated_payload.get('output_slots'), list):
            updated_payload['output_slots'] = [
                refresh_text_record(item)
                for item in updated_payload.get('output_slots') or []
            ]
        output = (
            dict(updated_payload.get('output') or {})
            if isinstance(updated_payload.get('output'), Mapping)
            else None
        )
        if output is not None and isinstance(output.get('outputs'), list):
            output['outputs'] = [
                refresh_text_record(item)
                for item in output.get('outputs') or []
            ]
            updated_payload['output'] = output
        late_fill = (
            dict(updated_payload.get('late_fill') or {})
            if isinstance(updated_payload.get('late_fill'), Mapping)
            else {}
        )
        if isinstance(late_fill.get('fill_results'), list):
            late_fill['fill_results'] = [
                copy.deepcopy(item) if item in (accepted_fill_results or [])
                else refresh_text_record(item)
                for item in late_fill.get('fill_results') or []
            ]
        existing_refreshes = [
            dict(item)
            for item in (late_fill.get('final_text_artifact_refreshes') or [])
            if isinstance(item, Mapping)
        ]
        late_fill['final_text_artifact_refreshes'] = [*existing_refreshes, *refresh_entries]
        late_fill['final_text_artifact_refresh_status'] = 'applied'
        late_fill['final_text_artifact_refreshed_paths'] = [
            entry.get('target_path')
            for entry in refresh_entries
            if entry.get('target_path')
        ]
        updated_payload['late_fill'] = late_fill
        return updated_payload

    @staticmethod
    def _terminal_materialization_contract_open_checks(
        payload: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        runtime = payload.get('runtime') if isinstance(payload.get('runtime'), Mapping) else {}
        review = runtime.get('graph_closure_review') if isinstance(runtime.get('graph_closure_review'), Mapping) else {}
        checks = review.get('checks') if isinstance(review.get('checks'), list) else []
        open_statuses = {'pending', 'planned', 'active', 'deferred', 'blocked', 'failed'}
        materialization_roles = {
            'text_artifact_output',
            'linked_artifact_binding_review',
            'text_artifact_syntax_repair',
        }
        materialization_check_kinds = {
            'composed_page_image_representation',
            'hero_image_composition',
            'html_css_selector_binding',
            'linked_artifact_binding',
            'structured_dependency_join',
            'text_artifact_syntax_sanity',
            'truth_guard',
            'truth_guard_capability',
        }
        materialization_evidence = {
            'generated_image_not_represented_in_composed_page',
            'generated_image_not_represented_in_hero',
            'html_css_selector_drift',
            'unresolved_linked_artifact_binding',
            'unresolved_local_dependency_link',
            'text_artifact_syntax_issue',
            'text_only_artifact_claim_guard',
            'runtime_capability_available_but_unmaterialized',
            'runtime_capability_unverified',
            'structured_dependency_join_contract_unmet',
        }
        open_checks: list[dict[str, Any]] = []
        for raw_check in checks:
            if not isinstance(raw_check, Mapping):
                continue
            status = str(raw_check.get('status') or '').strip().lower()
            if status not in open_statuses:
                continue
            check_kind = str(raw_check.get('check_kind') or '').strip()
            evidence = str(raw_check.get('evidence') or '').strip()
            role = str(raw_check.get('role') or '').strip()
            stage_direction = str(raw_check.get('stage_direction') or '').strip()
            materialization_relevant = (
                role in materialization_roles
                or check_kind in materialization_check_kinds
                or evidence in materialization_evidence
                or stage_direction == 'materialize_requested_text_artifact'
                or raw_check.get('requires_artifact') is True
                # Media obligations use final_output and may not repeat the
                # text-artifact requires_artifact flag. An open canonical
                # output obligation must not disappear from materialization.
                or (
                    str(raw_check.get('output_type') or '').strip() in {'image', 'audio'}
                    and bool(str(raw_check.get('obligation_id') or '').strip())
                )
            )
            if not materialization_relevant:
                continue
            open_checks.append(dict(raw_check))
        return open_checks

    _terminal_materialization_text_record_content = staticmethod(LinkedArtifactMaterialization._terminal_materialization_text_record_content)

    @staticmethod
    def _terminal_materialization_record_has_link(content: str, record: Mapping[str, Any]) -> bool:
        return any(token and token in content for token in LateFillRuntimeOwner._link_tokens_for_artifact(record))

    _terminal_content_has_unresolved_link_placeholder = staticmethod(LinkedArtifactMaterialization._terminal_content_has_unresolved_link_placeholder)

    _terminal_json_content_has_unresolved_dependency_link = staticmethod(LinkedArtifactMaterialization._terminal_json_content_has_unresolved_dependency_link)

    _mask_inline_javascript_non_code = staticmethod(LinkedArtifactMaterialization._mask_inline_javascript_non_code)

    _inline_javascript_binding_issues = staticmethod(LinkedArtifactMaterialization._inline_javascript_binding_issues)

    def _terminal_web_binding_contract_open_checks(
        self,
        payload: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        return self.linked_artifact_materialization._terminal_web_binding_contract_open_checks(payload)

    _terminal_linked_artifact_dependency_records = staticmethod(LinkedArtifactMaterialization._terminal_linked_artifact_dependency_records)

    _terminal_artifact_link_urls = staticmethod(LinkedArtifactMaterialization._terminal_artifact_link_urls)

    def _terminal_text_branch_hint_for_dependency(
        self,
        *,
        late_fill: Mapping[str, Any],
        extension: str,
        source_name: str,
        target_path: str,
    ) -> dict[str, Any]:
        return self.linked_artifact_materialization._terminal_text_branch_hint_for_dependency(late_fill=late_fill, extension=extension, source_name=source_name, target_path=target_path)

    def _terminal_unresolved_local_dependency_link_open_checks(
        self,
        payload: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        return self.linked_artifact_materialization._terminal_unresolved_local_dependency_link_open_checks(payload)

    def _terminal_linked_artifact_contract_required(
        self, payload: Mapping[str, Any], *,
        current_outputs: Optional[list[dict[str, Any]]] = None,
    ) -> bool:
        if current_outputs is not None and isinstance(payload.get('outputs'), list):
            payload = {**payload, 'outputs': current_outputs}
        records = self.linked_artifact_materialization._collect_link_rebind_artifact_records(payload)
        text_records = [
            record
            for record in records
            if str(record.get('type') or record.get('kind') or '').strip().lower() == 'text'
            and branch_result_contracts._artifact_record_extension(record) in _LINK_REBIND_TEXT_EXTENSIONS
            and branch_result_contracts._artifact_record_path(record)
        ]
        for consumer in text_records:
            dependencies, missing = LinkedArtifactMaterialization._terminal_linked_artifact_dependency_records(
                payload, records, consumer,
            )
            if dependencies or missing or LinkedArtifactMaterialization._terminal_artifact_link_urls(
                consumer, LinkedArtifactMaterialization._terminal_materialization_text_record_content(consumer),
            ):
                return True
        return False

    def _terminal_linked_artifact_contract_is_fulfilled(
        self, payload: Mapping[str, Any], *,
        current_outputs: Optional[list[dict[str, Any]]] = None,
    ) -> bool:
        return self.linked_artifact_materialization._terminal_linked_artifact_contract_is_fulfilled(payload, current_outputs=current_outputs)

    _terminal_exact_link_tokens_for_artifact = staticmethod(LinkedArtifactMaterialization._terminal_exact_link_tokens_for_artifact)

    _terminal_exact_content_has_artifact_link = staticmethod(LinkedArtifactMaterialization._terminal_exact_content_has_artifact_link)

    _terminal_html_hero_snippets = staticmethod(LinkedArtifactMaterialization._terminal_html_hero_snippets)

    _terminal_css_hero_snippets = staticmethod(LinkedArtifactMaterialization._terminal_css_hero_snippets)

    _terminal_html_inline_style_blocks = staticmethod(LinkedArtifactMaterialization._terminal_html_inline_style_blocks)

    _terminal_hero_local_image_required = staticmethod(LinkedArtifactMaterialization._terminal_hero_local_image_required)

    def _terminal_hero_image_composition_open_check(
        self,
        payload: Mapping[str, Any],
        *,
        request_payload: Optional[Mapping[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        return self.linked_artifact_materialization._terminal_hero_image_composition_open_check(payload, request_payload=request_payload)

    _css_url_quote = staticmethod(LinkedArtifactMaterialization._css_url_quote)

    _repair_terminal_hero_css_content = staticmethod(LinkedArtifactMaterialization._repair_terminal_hero_css_content)

    _repair_terminal_hero_html_content = staticmethod(LinkedArtifactMaterialization._repair_terminal_hero_html_content)

    def _repair_terminal_hero_image_composition(
        self,
        payload: dict[str, Any],
        *,
        request_payload: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        return self.linked_artifact_materialization._repair_terminal_hero_image_composition(payload, request_payload=request_payload)

    _terminal_composed_site_role_label = staticmethod(LinkedArtifactMaterialization._terminal_composed_site_role_label)

    _terminal_composed_site_role_is_bound = staticmethod(LinkedArtifactMaterialization._terminal_composed_site_role_is_bound)

    _terminal_composed_site_unstyled_image_paths = staticmethod(LinkedArtifactMaterialization._terminal_composed_site_unstyled_image_paths)

    def _terminal_composed_site_image_composition_open_checks(
        self,
        payload: Mapping[str, Any],
    ) -> Optional[list[dict[str, Any]]]:
        return self.linked_artifact_materialization._terminal_composed_site_image_composition_open_checks(payload)

    def _terminal_composed_page_image_representation_open_checks(
        self,
        payload: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        cohort_checks = self._terminal_composed_site_image_composition_open_checks(payload)
        return cohort_checks if cohort_checks is not None else []

    def _terminal_composed_page_image_representation_open_check(
        self,
        payload: Mapping[str, Any],
    ) -> Optional[dict[str, Any]]:
        checks = self._terminal_composed_page_image_representation_open_checks(payload)
        return checks[0] if checks else None

    _html_attribute_escape = staticmethod(LinkedArtifactMaterialization._html_attribute_escape)

    def _terminal_materialization_branch_has_canonical_evidence(
        self,
        check: Mapping[str, Any],
        payload: Mapping[str, Any],
        late_fill: Mapping[str, Any],
    ) -> bool:
        branch_id = str(check.get('branch_id') or check.get('phase_id') or '').strip()
        completed_branch = {}
        for branch in late_fill.get('completed_branches') or []:
            if not isinstance(branch, Mapping):
                continue
            candidate_id = str(branch.get('branch_id') or branch.get('phase_id') or '').strip()
            if branch_id and candidate_id == branch_id:
                completed_branch = branch
                break
        output_type = str(check.get('output_type') or completed_branch.get('output_type') or '').strip().lower()
        capability = str(check.get('capability') or completed_branch.get('capability') or '').strip().lower()
        role = str(check.get('role') or completed_branch.get('role') or '').strip()
        if output_type == 'text' or role == 'text_artifact_output':
            candidates = [check]
            if completed_branch:
                candidates.append(completed_branch)
            return any(
                self._text_artifact_branch_has_canonical_evidence(candidate, payload)
                for candidate in candidates
                if isinstance(candidate, Mapping)
            )
        if output_type == 'image' or capability == self.capability_image_generation:
            records = self.linked_artifact_materialization._collect_link_rebind_artifact_records(payload)
            for record in records:
                record_type = str(record.get('type') or record.get('kind') or '').strip().lower()
                if record_type != 'image' and branch_result_contracts._artifact_record_extension(record) not in _LINK_REBIND_IMAGE_EXTENSIONS:
                    continue
                record_branch_id = str(record.get('branch_id') or record.get('phase_id') or '').strip()
                if branch_id and record_branch_id != branch_id:
                    continue
                if any(
                    str(check.get(key) or '').strip()
                    and str(record.get(key) or '').strip()
                    and str(check[key]).strip() != str(record[key]).strip()
                    for key in ('phase_id', 'obligation_id')
                ):
                    continue
                if not artifact_is_current_authoritative(
                    record, response_id=str(payload.get('id') or '').strip(),
                ):
                    continue
                path = branch_result_contracts._artifact_record_path(record)
                if path and Path(path).expanduser().is_file():
                    return True
        return False

    def _terminal_materialization_check_still_open(
        self,
        check: Mapping[str, Any],
        payload: Mapping[str, Any],
        late_fill: Mapping[str, Any],
        *,
        linked_artifact_contract_fulfilled: bool,
    ) -> bool:
        check_kind = str(check.get('check_kind') or '').strip()
        evidence = str(check.get('evidence') or '').strip()
        role = str(check.get('role') or '').strip()
        repair_action = str(check.get('repair_action') or check.get('recovery_action') or '').strip()
        if (
            check_kind == 'composed_page_image_representation'
            or evidence == 'generated_image_not_represented_in_composed_page'
        ):
            return True
        if (
            check_kind == 'hero_image_composition'
            or evidence == 'generated_image_not_represented_in_hero'
        ):
            return self.linked_artifact_materialization._terminal_hero_image_composition_open_check(payload) is not None
        if check_kind == 'text_artifact_syntax_sanity' or evidence == 'text_artifact_syntax_issue':
            return True
        if (
            check_kind == 'structured_dependency_join'
            or evidence == 'structured_dependency_join_contract_unmet'
        ):
            return True
        if check_kind == 'html_css_selector_binding' or evidence == 'html_css_selector_drift':
            # This check comes from the just-refreshed Closure review.  A CSS
            # file merely existing is not evidence that it targets the saved
            # HTML vocabulary.  When the final bytes agree, the fresh review
            # emits no selector check at all; otherwise it must remain open.
            return True
        if check_kind == 'web_runtime_binding' or evidence in {
            'inline_javascript_binding_mismatch',
            'static_json_consumer_contract_mismatch',
        }:
            # These checks are recomputed from the current saved web files.
            # Artifact existence cannot satisfy a still-current binding defect.
            return True
        if check_kind in {'truth_guard', 'truth_guard_capability'}:
            return True
        if evidence in {
            'text_only_artifact_claim_guard',
            'runtime_capability_available_but_unmaterialized',
            'runtime_capability_unverified',
        }:
            return True
        if (
            check_kind == 'linked_artifact_binding'
            or role == 'linked_artifact_binding_review'
            or evidence == 'unresolved_linked_artifact_binding'
            or evidence == 'unresolved_local_dependency_link'
            or repair_action == RECOVERY_ACTION_REBIND_DEPENDENCY_EVIDENCE
        ):
            return not linked_artifact_contract_fulfilled

        branch_id = str(check.get('branch_id') or check.get('phase_id') or '').strip()
        completed_branch_ids = {
            str(item.get('branch_id') or item.get('phase_id') or '').strip()
            for item in (late_fill.get('completed_branches') or [])
            if isinstance(item, Mapping) and str(item.get('branch_id') or item.get('phase_id') or '').strip()
        }
        if branch_id and branch_id in completed_branch_ids:
            if self._terminal_materialization_branch_has_canonical_evidence(check, payload, late_fill):
                return False
        return True

    def _filter_terminal_materialization_open_checks(
        self,
        checks: list[dict[str, Any]],
        payload: Mapping[str, Any],
        late_fill: Mapping[str, Any],
        *,
        current_outputs: Optional[list[dict[str, Any]]] = None,
    ) -> list[dict[str, Any]]:
        if not checks:
            return []
        linked_artifact_contract_fulfilled = self.linked_artifact_materialization._terminal_linked_artifact_contract_is_fulfilled(
            payload, current_outputs=current_outputs,
        )
        return [
            dict(check)
            for check in checks
            if self._terminal_materialization_check_still_open(
                check,
                payload,
                late_fill,
                linked_artifact_contract_fulfilled=linked_artifact_contract_fulfilled,
            )
        ]

    @staticmethod
    def _is_linked_artifact_binding_check(check: Mapping[str, Any]) -> bool:
        if str(check.get('check_kind') or '').strip() == 'structured_dependency_join':
            return False
        return (
            str(check.get('check_kind') or '').strip() == 'linked_artifact_binding'
            or str(check.get('role') or '').strip() == 'linked_artifact_binding_review'
            or str(check.get('evidence') or '').strip() == 'unresolved_linked_artifact_binding'
            or str(check.get('evidence') or '').strip() == 'unresolved_local_dependency_link'
            or str(check.get('repair_action') or check.get('recovery_action') or '').strip()
            == RECOVERY_ACTION_REBIND_DEPENDENCY_EVIDENCE
        )

    @staticmethod
    def _terminal_linked_artifact_binding_open_check() -> dict[str, Any]:
        return {
            'check_kind': 'linked_artifact_binding',
            'status': 'pending',
            'evidence': 'unresolved_linked_artifact_binding',
            'role': 'linked_artifact_binding_review',
            'requires_artifact': True,
            'repair_action': RECOVERY_ACTION_REBIND_DEPENDENCY_EVIDENCE,
            'recovery_action': RECOVERY_ACTION_REBIND_DEPENDENCY_EVIDENCE,
            'reason': 'final linked artifact output does not resolve every saved dependency artifact',
        }

    @staticmethod
    def _compact_terminal_materialization_checks(
        checks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        compacted: list[dict[str, Any]] = []
        for check in checks[:8]:
            compacted.append(
                {
                    key: value
                    for key, value in {
                        'check_kind': check.get('check_kind'),
                        'status': check.get('status'),
                        'evidence': check.get('evidence'),
                        'reason': check.get('reason'),
                        'role': check.get('role'),
                        'branch_id': check.get('branch_id'),
                        'phase_id': check.get('phase_id'),
                        'capability': check.get('capability'),
                        'output_type': check.get('output_type'),
                        'repair_action': check.get('repair_action') or check.get('recovery_action'),
                        'text_artifact_extension': check.get('text_artifact_extension'),
                        'text_artifact_source_name': check.get('text_artifact_source_name'),
                        'text_artifact_target_path': check.get('text_artifact_target_path'),
                        'content_payload_source': check.get('content_payload_source'),
                        'dependency_source_path': check.get('dependency_source_path'),
                        'missing_dependency_url': check.get('missing_dependency_url'),
                        'missing_dependency_target_path': check.get('missing_dependency_target_path'),
                        'generated_image_count': check.get('generated_image_count'),
                        'represented_image_count': check.get('represented_image_count'),
                        'missing_image_count': check.get('missing_image_count'),
                        'expected_count': check.get('expected_count'),
                        'actual_count': check.get('actual_count'),
                        'expected_labels': (
                            check.get('expected_labels')[:16]
                            if isinstance(check.get('expected_labels'), list)
                            else check.get('expected_labels')
                        ),
                        'required_fields': (
                            check.get('required_fields')[:16]
                            if isinstance(check.get('required_fields'), list)
                            else check.get('required_fields')
                        ),
                        'issue_codes': (
                            check.get('issue_codes')[:16]
                            if isinstance(check.get('issue_codes'), list)
                            else check.get('issue_codes')
                        ),
                        'missing_image_paths': (
                            check.get('missing_image_paths')[:8]
                            if isinstance(check.get('missing_image_paths'), list)
                            else check.get('missing_image_paths')
                        ),
                    }.items()
                    if value not in (None, '', [], {})
                }
            )
        return compacted

    def _demote_terminal_materialization_branches_with_open_checks(
        self,
        late_fill: Mapping[str, Any],
        open_checks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not open_checks:
            return dict(late_fill or {})
        updated = dict(late_fill or {})
        completed_records = [
            dict(item)
            for item in (updated.get('completed_branches') or [])
            if isinstance(item, Mapping)
        ]
        pending_records = [
            dict(item)
            for item in (updated.get('pending_branches') or [])
            if isinstance(item, Mapping)
        ]
        pending_ids = {
            self.branch_id(item)
            for item in pending_records
            if self.branch_id(item)
        }
        retained_completed: list[dict[str, Any]] = []
        demoted_records: list[dict[str, Any]] = []
        compact_checks = self._compact_terminal_materialization_checks(open_checks)

        def check_matches_branch(check: Mapping[str, Any], branch: Mapping[str, Any]) -> bool:
            branch_request = branch.get('artifact_request') if isinstance(branch.get('artifact_request'), Mapping) else {}
            check_request = check.get('artifact_request') if isinstance(check.get('artifact_request'), Mapping) else {}
            branch_target = str(
                branch.get('text_artifact_target_path')
                or branch_request.get('target_path')
                or ''
            ).strip()
            check_target = str(
                check.get('text_artifact_target_path')
                or check_request.get('target_path')
                or ''
            ).strip()
            if branch_target and check_target:
                return text_artifact_materialization._text_artifact_path_matches_target(
                    branch_target,
                    check_target,
                )
            branch_id = self.branch_id(branch)
            check_id = str(check.get('branch_id') or check.get('phase_id') or '').strip()
            if branch_id and check_id and branch_id == check_id:
                return True
            branch_extension = str(
                branch.get('text_artifact_extension')
                or branch_request.get('extension')
                or ''
            ).strip().lower().lstrip('.')
            check_extension = str(
                check.get('text_artifact_extension')
                or check_request.get('extension')
                or ''
            ).strip().lower().lstrip('.')
            branch_source = str(
                branch.get('text_artifact_source_name')
                or branch_request.get('source_name')
                or ''
            ).strip().lower()
            check_source = str(
                check.get('text_artifact_source_name')
                or check_request.get('source_name')
                or ''
            ).strip().lower()
            return bool(branch_extension and branch_source and branch_extension == check_extension and branch_source == check_source)

        def repair_fields_for_branch(branch: Mapping[str, Any]) -> dict[str, Any]:
            matching_checks = [
                check
                for check in open_checks
                if isinstance(check, Mapping) and check_matches_branch(check, branch)
            ]
            if not matching_checks:
                return {}
            bounded_checks = [
                check for check in matching_checks
                if str(check.get('content_payload') or '').strip()
                and str(check.get('text_artifact_target_path') or '').strip()
            ]
            # The cohort contract includes roles, layout and exact sibling/target
            # boundaries. A generic link check for this same file must not erase
            # it merely because the generic check was collected first. Other
            # defects stay open and are rechecked against the saved replacement.
            preferred = (bounded_checks or matching_checks)[0]
            if (preferred.get('check_kind') == 'linked_artifact_binding'
                    or preferred.get('content_payload_source') == 'closure_linked_artifact_binding_review'):
                preferred = next(
                    (check for check in bounded_checks
                     if isinstance(check.get('execution_contract'), Mapping)
                     and check['execution_contract'].get('repair_mode') == 'composed_site_image_cohort_target'),
                    preferred,
                )
            fields: dict[str, Any] = {}
            for key in (
                'repair_action',
                'recovery_action',
                'suggested_action',
                'repair_action_reason',
                'content_payload',
                'content_payload_source',
                'stage_direction',
                'requires_artifact',
                'text_artifact_extension',
                'text_artifact_source_name',
                'text_artifact_source',
                'text_artifact_target_path',
                'artifact_request',
                'review_criteria',
                'input_refs',
                'execution_contract',
                'output_contract',
                'repair_scope',
                'resource_class',
                'dependency_policy',
                'generated_image_count',
                'represented_image_count',
                'missing_image_count',
                'generated_image_paths',
                'missing_image_paths',
                'represented_image_paths',
                'image_assignments',
                'role_binding_defects',
                'detached_repair_section_present',
                'layout_binding_defect',
            ):
                value = preferred.get(key)
                if value not in (None, '', [], {}):
                    fields[key] = value
            if fields.get('repair_action') == RECOVERY_ACTION_REBIND_DEPENDENCY_EVIDENCE:
                fields.setdefault('repair_execution_policy', 'schedule_late_fill_branch')
                fields.setdefault('auto_execute', True)
                fields.setdefault('repair_work_available', True)
                fields.setdefault('needs_external_input', False)
                fields.setdefault('materialization_blocked', False)
            return fields

        for branch in completed_records:
            branch_id = self.branch_id(branch)
            matching_check = any(
                isinstance(check, Mapping) and check_matches_branch(check, branch)
                for check in open_checks
            )
            should_demote = bool(
                branch_id
                and matching_check
                and str(branch.get('status') or '').strip().lower() == 'fulfilled'
            )
            if not should_demote:
                retained_completed.append(branch)
                continue
            demoted = dict(branch)
            demoted.update(repair_fields_for_branch(branch))
            demoted['status'] = 'repair_needed'
            demoted['evidence'] = 'terminal_materialization_contract_unmet'
            demoted['repair_action'] = (
                demoted.get('repair_action')
                or demoted.get('recovery_action')
                or RECOVERY_ACTION_RETRY_SAME_BRANCH
            )
            demoted['recovery_action'] = demoted.get('repair_action')
            demoted['materialization_contract_unmet'] = True
            demoted['materialization_contract_open_checks'] = compact_checks
            demoted_records.append(demoted)
            if branch_id and branch_id not in pending_ids:
                pending_records.append(demoted)
                pending_ids.add(branch_id)
        # A newly discovered dependency has no completed branch to demote.
        # Give it an exact target identity and use the same bounded projection.
        # Existing work/history must win so repeated checks cannot reset retries.
        known_branches = [
            *completed_records, *pending_records,
            *self.normalize_late_fill_branches(updated.get('active_branches')),
            *self.normalize_late_fill_branches(updated.get('failed_branches')),
            *self.normalize_late_fill_branches(updated.get('cancelled_branches')),
            *self.normalize_late_fill_branches(
                updated.get('materialization_contract_demoted_branches')
            ),
        ]
        for check in open_checks:
            if not isinstance(check, Mapping):
                continue
            if (
                check.get('evidence') != 'unresolved_local_dependency_link'
                or check.get('content_payload_source') != 'closure_local_dependency_link_review'
                or not str(check.get('content_payload') or '').strip()
                or not text_artifact_materialization._artifact_gap_is_authoritative_bounded_text_artifact_repair(check)
                or check.get('materialization_blocked') is True
                or check.get('needs_external_input') is True
            ):
                continue
            if any(check_matches_branch(check, branch) for branch in known_branches):
                continue
            target_path = str(check.get('text_artifact_target_path') or '').strip()
            if not target_path:
                continue
            owner_id = 'missing-local-dependency-' + hashlib.sha256(
                target_path.encode('utf-8')
            ).hexdigest()[:16]
            missing_branch = {
                **dict(check),
                **repair_fields_for_branch(check),
                'branch_id': owner_id,
                'phase_id': owner_id,
                'status': 'repair_needed',
                'evidence': 'terminal_materialization_contract_unmet',
                'materialization_contract_unmet': True,
            }
            pending_records.append(missing_branch)
            pending_ids.add(owner_id)
            demoted_records.append(missing_branch)
            known_branches.append(missing_branch)
        if not demoted_records:
            updated.pop('materialization_contract_current_demoted_branches', None)
            return updated
        updated['completed_branches'] = retained_completed
        updated['completed_branch_count'] = len(retained_completed)
        updated['pending_branches'] = pending_records
        updated['pending_branch_count'] = len(pending_records)
        previous_demoted = [
            dict(item)
            for item in (updated.get('materialization_contract_demoted_branches') or [])
            if isinstance(item, Mapping)
        ]
        updated['materialization_contract_demoted_branches'] = previous_demoted + demoted_records
        # Keep the complete current execution set separate from the compact
        # user-facing check diagnostics. Projection must support N exact
        # branches and must not inherit the diagnostic display cap.
        updated['materialization_contract_current_demoted_branches'] = demoted_records
        return updated

    def _review_terminal_graph_rebase_if_available(
        self,
        payload: dict[str, Any],
        *,
        request_payload: dict[str, Any],
        route_payload: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        if not callable(self.review_terminal_graph_rebase):
            return payload
        try:
            reviewed = self.review_terminal_graph_rebase(
                payload,
                request_payload=request_payload,
                route_payload=route_payload,
            )
        except Exception as exc:  # noqa: BLE001
            logging.warning('Could not review terminal graph rebase shadow candidate: %s', exc)
            return payload
        return reviewed if isinstance(reviewed, dict) else payload

    @staticmethod
    @observe_state('late_fill.reconcile', 'terminal_response_state', 'reconciled_response_state', labels=('NEW_AUTHORITY_BOUNDARY',), new_authority_boundary=True)
    def _reconcile_terminal_satisfied_repair_loop(
        late_fill: Mapping[str, Any],
        *,
        verified_superseded_branches: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        updated = dict(late_fill or {})
        repair_loop = (
            dict(updated.get('repair_loop') or {})
            if isinstance(updated.get('repair_loop'), Mapping)
            else {}
        )
        if not repair_loop:
            return updated

        promoted_contracts = [
            dict(item)
            for item in (repair_loop.get('promoted_contracts') or [])
            if isinstance(item, Mapping)
        ]
        completed_branches = [
            dict(item)
            for item in (updated.get('completed_branches') or [])
            if isinstance(item, Mapping)
        ]
        # The composition owner may supply only branches it has just retired
        # after a fresh applicable review and saved-target hash. Match their
        # exact identities through the normal matcher without publishing a
        # successful execution or changing the persisted superseded status.
        superseded_resolutions = {
            str(branch.get('branch_id') or ''): branch
            for branch in (verified_superseded_branches or [])
        }
        completed_branches = [
            {**branch, 'status': 'completed'}
            if branch == superseded_resolutions.get(str(branch.get('branch_id') or ''))
            else branch
            for branch in completed_branches
        ]
        available_branches = list(completed_branches)
        satisfied_contracts: list[dict[str, Any]] = []
        unresolved_contracts: list[dict[str, Any]] = []
        for contract in promoted_contracts:
            match_index = next(
                (
                    index
                    for index, branch in enumerate(available_branches)
                    if repair_contract_matches_completion(contract, branch)
                ),
                None,
            )
            if match_index is None:
                unresolved_contracts.append(contract)
                continue
            satisfied_contracts.append(contract)
            available_branches.pop(match_index)
        if not satisfied_contracts:
            return updated

        resolved_contracts = [
            {
                key: value
                for key, value in {
                    'contract_id': contract.get('contract_id'),
                    'branch_id': contract.get('branch_id'),
                    'phase_id': contract.get('phase_id'),
                    'obligation_id': contract.get('obligation_id'),
                    'task_id': contract.get('task_id'),
                    'artifact_request': contract.get('artifact_request'),
                    'execution_binding': contract.get('execution_binding'),
                    'supersession_evidence': superseded_resolutions.get(
                        str(contract.get('branch_id') or ''), {}
                    ).get('supersession_evidence'),
                }.items()
                if value not in (None, '', [], {})
            }
            for contract in satisfied_contracts
        ]
        prior_resolved = [
            dict(item)
            for item in (repair_loop.get('resolved_contracts') or [])
            if isinstance(item, Mapping)
        ]
        resolved_contracts = [*prior_resolved, *resolved_contracts]
        repair_loop['resolved_contract_count'] = len(resolved_contracts)
        repair_loop['resolved_contracts'] = resolved_contracts
        repair_loop['promoted_contracts'] = unresolved_contracts
        repair_loop['promoted_contract_count'] = len(unresolved_contracts)

        executable_contract_count = sum(
            1 for contract in unresolved_contracts if contract.get('auto_execute') is True
        )
        blocked_contract_count = len(unresolved_contracts) - executable_contract_count
        repair_work_available_count = sum(
            1 for contract in unresolved_contracts if contract.get('repair_work_available') is True
        )
        needs_external_input_count = sum(
            1 for contract in unresolved_contracts if contract.get('needs_external_input') is True
        )
        repair_loop.update(
            {
                'auto_execute': bool(executable_contract_count),
                'repair_work_available': bool(repair_work_available_count),
                'repair_work_available_count': repair_work_available_count,
                'executable_contract_count': executable_contract_count,
                'blocked_contract_count': blocked_contract_count,
                'materialization_blocked_contract_count': blocked_contract_count,
                'needs_external_input_count': needs_external_input_count,
                'next_actions': list(
                    dict.fromkeys(
                        str(contract.get('repair_action') or contract.get('recovery_action') or '').strip()
                        for contract in unresolved_contracts
                        if str(contract.get('repair_action') or contract.get('recovery_action') or '').strip()
                    )
                ),
            }
        )
        updated['repair_rebuild_contracts'] = unresolved_contracts

        feedback = (
            dict(updated.get('inference_repair_feedback') or {})
            if isinstance(updated.get('inference_repair_feedback'), Mapping)
            else {}
        )
        if feedback:
            feedback_items = [
                dict(item)
                for item in (feedback.get('items') or [])
                if isinstance(item, Mapping)
                and not any(
                    repair_contract_matches_completion(item, branch)
                    for branch in completed_branches
                )
            ]
            feedback['items'] = feedback_items
            feedback['repair_rebuild_contracts'] = unresolved_contracts
            feedback['repair_loop'] = dict(repair_loop)

        if unresolved_contracts:
            updated['repair_loop'] = repair_loop
            if feedback:
                updated['inference_repair_feedback'] = feedback
            unresolved_actions = repair_loop.get('next_actions') or []
            if unresolved_actions:
                updated['repair_actions'] = list(unresolved_actions)
                updated['repair_action'] = unresolved_actions[0]
            else:
                updated.pop('repair_action', None)
                updated.pop('repair_actions', None)
            return updated

        fully_satisfied = terminal_repair_loop_is_fully_satisfied(
            {
                **updated,
                'repair_loop': {
                    **repair_loop,
                    'promoted_contracts': satisfied_contracts,
                },
            },
            {
                **repair_loop,
                'promoted_contracts': satisfied_contracts,
            },
        )
        repair_loop.update(
            {
                'status': 'completed',
                'auto_execute': False,
                'repair_work_available': False,
                'repair_work_available_count': 0,
                'executable_contract_count': 0,
                'blocked_contract_count': 0,
                'materialization_blocked_contract_count': 0,
                'needs_external_input_count': 0,
                'next_actions': [],
                'requires_promotion': False,
                'resolution': {
                    'status': 'completed' if fully_satisfied else 'resolved_from_exact_branch_evidence',
                    'authority': 'terminal_exact_repair_contract_evidence',
                },
            }
        )
        updated['repair_loop'] = repair_loop
        action_values = [updated.get('repair_action')]
        if isinstance(updated.get('repair_actions'), list):
            action_values.extend(updated.get('repair_actions') or [])
        resolved_actions = [
            str(value or '').strip()
            for value in action_values
            if str(value or '').strip()
        ]
        if resolved_actions:
            updated['resolved_repair_actions'] = list(dict.fromkeys(resolved_actions))
        updated.pop('repair_action', None)
        updated.pop('repair_actions', None)

        if feedback:
            feedback['status'] = 'resolved'
            feedback['repair_loop'] = dict(repair_loop)
            feedback['resolution_status'] = repair_loop['resolution']['status']
            updated['inference_repair_feedback'] = feedback
        return updated

    def _supersede_resolved_composition_repairs(
        self, payload: Mapping[str, Any], late_fill: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Retire failed cohort repairs only after a fresh applicable review."""
        updated = dict(late_fill)
        failed = self.normalize_late_fill_branches(updated.get('failed_branches'))
        candidates = [
            branch for branch in failed
            if branch.get('content_payload_source') == 'closure_composed_site_image_composition'
            and branch.get('status') == 'failed'
            and not text_artifact_materialization._text_artifact_revision_required(branch)
        ]
        if not candidates:
            return updated
        # None means the review is inapplicable, not that the defect is closed.
        if self._terminal_composed_site_image_composition_open_checks(payload) != []:
            return updated
        completed = self.normalize_late_fill_branches(updated.get('completed_branches'))
        superseded_ids: set[str] = set()
        for branch in candidates:
            target = LinkedArtifactMaterialization._text_artifact_target_path_from_mapping(branch)
            extension = str(branch.get('text_artifact_extension') or Path(target).suffix).lstrip('.')
            if not target or text_artifact_materialization._text_artifact_saved_payload_error(target, extension=extension):
                continue
            try:
                digest = hashlib.sha256(Path(target).read_bytes()).hexdigest()
            except OSError:
                continue
            branch_id = self.branch_id(branch)
            if not branch_id:
                continue
            superseded = dict(branch)
            superseded.update({
                'status': 'superseded',
                'evidence': 'fresh_composed_site_review_resolved_repair_defect',
                'non_blocking_after_final_contract_fulfilled': True,
                'supersession_evidence': {
                    'review': 'composed_site_image_composition',
                    'open_check_count': 0, 'target_path': target,
                    'target_sha256': digest,
                },
            })
            # Keep the failed attempt as audit evidence, not live retry state.
            superseded['superseded_failure'] = {
                key: superseded.pop(key) for key in
                ('error', 'attempt', 'recovery_context', 'recovery_state')
                if key in superseded
            }
            completed.append(superseded)
            superseded_ids.add(branch_id)
        if superseded_ids:
            updated['failed_branches'] = [b for b in failed if self.branch_id(b) not in superseded_ids]
            updated['failed_branch_count'] = len(updated['failed_branches'])
            updated['completed_branches'] = completed
            updated['completed_branch_count'] = len(completed)
            retired = [branch for branch in completed if self.branch_id(branch) in superseded_ids]

            def matches_retired_recovery(item):
                return isinstance(item, Mapping) and any(
                    repair_contract_matches_completion(item, {**branch, 'status': 'completed'})
                    for branch in retired
                )

            # A candidate is not a separate obligation. Remove only retries
            # belonging to the exact branches just retired; retain others.
            if isinstance(updated.get('recovery_candidates'), list):
                updated['recovery_candidates'] = [
                    item for item in updated['recovery_candidates']
                    if not matches_retired_recovery(item)
                ]
            recovery_state = updated.get('recovery_state')
            if matches_retired_recovery(recovery_state):
                updated.pop('recovery_state', None)
            updated = self._reconcile_terminal_satisfied_repair_loop(
                updated,
                verified_superseded_branches=retired,
            )
        return updated

    @observe_state('late_fill.terminal_materialization', 'branch_artifact_response_state', 'terminal_materialization_state', labels=('NEW_AUTHORITY_BOUNDARY',), new_authority_boundary=True)
    def finalize_terminal_materialization_contract(
        self,
        payload: dict[str, Any],
        *,
        request_payload: dict[str, Any],
        route_payload: Optional[dict[str, Any]],
        artifact_gap: Optional[dict[str, Any]],
        terminal_status: str,
        accepted_fill_results: Optional[list[dict[str, Any]]] = None,
    ) -> tuple[dict[str, Any], str]:
        effective_status = str(terminal_status or '').strip().lower() or 'completed'
        updated_payload, inline_materialization_open_checks = (
            self._materialize_inline_text_artifacts_for_terminal_closure(payload)
        )
        # The last lightweight checkpoint can still expose pending public slots.
        # Reconcile accepted current results before the resolver decides which
        # saved dependencies are public; the parent frame remains untouched.
        current_output_state = prepare_response_output_state(
            updated_payload, request_payload=request_payload,
        )
        updated_payload = self.linked_artifact_materialization.rebind_terminal_linked_artifacts(
            updated_payload, current_outputs=current_output_state['outputs'],
            accepted_fill_results=accepted_fill_results,
        )
        updated_payload = self._repair_terminal_text_artifact_syntax(
            updated_payload, accepted_fill_results=accepted_fill_results,
        )
        updated_payload = self.linked_artifact_materialization._repair_terminal_hero_image_composition(
            updated_payload,
            request_payload=request_payload,
        )
        # Accepted results describe their original execution and bytes. A later
        # repair may replace the same file, but its refreshed evidence belongs
        # to the new result and current artifact projections, not to that history.
        updated_payload = self._refresh_terminal_text_artifacts_from_saved_files(
            updated_payload, accepted_fill_results=accepted_fill_results,
        )
        # A terminal repair may create or replace a named dependency after the
        # initial rebind. Re-run the idempotent resolver over final saved truth
        # before Closure evaluates local links and consumer contracts.
        current_output_state = prepare_response_output_state(
            updated_payload, request_payload=request_payload,
        )
        updated_payload = self.linked_artifact_materialization.rebind_terminal_linked_artifacts(
            updated_payload, current_outputs=current_output_state['outputs'],
            accepted_fill_results=accepted_fill_results,
        )
        late_fill = (
            dict(updated_payload.get('late_fill') or {})
            if isinstance(updated_payload.get('late_fill'), Mapping)
            else {}
        )
        precheck_late_fill = self._reconcile_satisfied_failed_text_artifact_branches(updated_payload, late_fill)
        if precheck_late_fill != late_fill:
            updated_payload = self.attach_late_fill_state(updated_payload, precheck_late_fill)
        updated_payload = self.refresh_terminal_graph_closure_review(
            updated_payload,
            request_payload=request_payload,
            route_payload=route_payload,
            artifact_gap=artifact_gap,
        )
        late_fill = (
            dict(updated_payload.get('late_fill') or {})
            if isinstance(updated_payload.get('late_fill'), Mapping)
            else {}
        )
        post_refresh_late_fill = self._reconcile_satisfied_failed_text_artifact_branches(
            updated_payload,
            late_fill,
        )
        if post_refresh_late_fill != late_fill:
            updated_payload = self.attach_late_fill_state(updated_payload, post_refresh_late_fill)
            late_fill = post_refresh_late_fill
        # Validate against the same accepted-current output projection used by
        # rebinding. Do not publish these handles over the frozen checkpoint.
        current_output_state = prepare_response_output_state(
            updated_payload, request_payload=request_payload,
        )
        open_checks = self._filter_terminal_materialization_open_checks(
            [
                *self._terminal_materialization_contract_open_checks(updated_payload),
                *inline_materialization_open_checks,
                *self.linked_artifact_materialization._terminal_unresolved_local_dependency_link_open_checks(updated_payload),
                *self.linked_artifact_materialization._terminal_web_binding_contract_open_checks(updated_payload),
            ],
            updated_payload,
            late_fill,
            current_outputs=current_output_state['outputs'],
        )
        composed_image_checks = self._terminal_composed_page_image_representation_open_checks(
            updated_payload
        )
        if composed_image_checks:
            existing_composed_identities = {
                (
                    str(check.get('branch_id') or check.get('phase_id') or '').strip(),
                    str(check.get('text_artifact_target_path') or '').strip(),
                )
                for check in open_checks
                if isinstance(check, Mapping)
                and str(check.get('check_kind') or '').strip()
                == 'composed_page_image_representation'
            }
            new_composed_checks = [
                check
                for check in composed_image_checks
                if (
                    str(check.get('branch_id') or check.get('phase_id') or '').strip(),
                    str(check.get('text_artifact_target_path') or '').strip(),
                )
                not in existing_composed_identities
            ]
            open_checks = self._filter_terminal_materialization_open_checks(
                [*open_checks, *new_composed_checks],
                updated_payload,
                late_fill,
                current_outputs=current_output_state['outputs'],
            )
        hero_image_check = self.linked_artifact_materialization._terminal_hero_image_composition_open_check(
            updated_payload,
            request_payload=request_payload,
        )
        if (
            hero_image_check
            and not any(
                str(check.get('check_kind') or '').strip() == 'hero_image_composition'
                for check in open_checks
                if isinstance(check, Mapping)
            )
        ):
            open_checks = self._filter_terminal_materialization_open_checks(
                [*open_checks, hero_image_check],
                updated_payload,
                late_fill,
                current_outputs=current_output_state['outputs'],
            )
        if (
            not open_checks
            and self._terminal_linked_artifact_contract_required(
                updated_payload, current_outputs=current_output_state['outputs'],
            )
            and not self.linked_artifact_materialization._terminal_linked_artifact_contract_is_fulfilled(
                updated_payload, current_outputs=current_output_state['outputs'],
            )
        ):
            open_checks = self._filter_terminal_materialization_open_checks(
                [self._terminal_linked_artifact_binding_open_check()],
                updated_payload,
                late_fill,
                current_outputs=current_output_state['outputs'],
            )
        elif (
            open_checks
            and not any(self._is_linked_artifact_binding_check(check) for check in open_checks)
            and self._terminal_linked_artifact_contract_required(
                updated_payload, current_outputs=current_output_state['outputs'],
            )
            and not self.linked_artifact_materialization._terminal_linked_artifact_contract_is_fulfilled(
                updated_payload, current_outputs=current_output_state['outputs'],
            )
        ):
            open_checks = self._filter_terminal_materialization_open_checks(
                [*open_checks, self._terminal_linked_artifact_binding_open_check()],
                updated_payload,
                late_fill,
                current_outputs=current_output_state['outputs'],
            )
        branch_state_open_checks: list[dict[str, Any]] = []
        for branch_key, branch_status, evidence in (
            ('failed_branches', 'failed', 'late_fill_failed_branch'),
            ('pending_branches', 'pending', 'late_fill_pending_branch'),
            ('active_branches', 'active', 'late_fill_active_branch'),
        ):
            for branch in self.normalize_late_fill_branches(late_fill.get(branch_key)):
                if branch.get('non_blocking_after_final_contract_fulfilled') is True:
                    continue
                branch_id = self.branch_id(branch)
                if str(branch_id or '').startswith('branch-repair-'):
                    continue
                if branch_id and any(
                    str(
                        check.get('branch_id') or check.get('phase_id') or ''
                    ).strip()
                    == branch_id
                    for check in open_checks
                    if isinstance(check, Mapping)
                ):
                    # The authoritative contract check already explains why
                    # this branch is open; avoid a second generic blocker for
                    # the same repair owner.
                    continue
                branch_state_open_checks.append(
                    {
                        'check_kind': 'late_fill_branch_state',
                        'status': branch_status,
                        'evidence': evidence,
                        'branch_id': branch_id or None,
                        'phase_id': str(branch.get('phase_id') or branch_id or '').strip() or None,
                        'capability': self.branch_capability(branch),
                        'output_type': str(branch.get('output_type') or '').strip() or None,
                        'reason': 'late-fill branch has not reached fulfilled, waived, or superseded state',
                    }
                )
        if branch_state_open_checks:
            open_checks = self._filter_terminal_materialization_open_checks(
                [*open_checks, *branch_state_open_checks],
                updated_payload,
                late_fill,
                current_outputs=current_output_state['outputs'],
            )
        if open_checks:
            late_fill = self._demote_terminal_materialization_branches_with_open_checks(
                late_fill,
                open_checks,
            )
            if effective_status in {'completed', 'skipped'}:
                effective_status = 'partial_failed'
            late_fill['status'] = effective_status
            late_fill['final_materialization_contract_status'] = 'unmet'
            late_fill['materialization_contract_unmet'] = True
            late_fill['final_materialization_contract_reason'] = (
                'terminal structured dependency join violates its explicit output contract'
                if any(
                    str(check.get('check_kind') or '').strip() == 'structured_dependency_join'
                    for check in open_checks
                    if isinstance(check, Mapping)
                )
                else 'artifact obligation exists but final materialization contract is unmet'
            )
            late_fill['materialization_contract_open_check_count'] = len(open_checks)
            late_fill['materialization_contract_open_checks'] = (
                self._compact_terminal_materialization_checks(open_checks)
            )
            if str(late_fill.get('skip_reason') or '').strip().lower() == 'already_fulfilled':
                late_fill['skip_reason'] = 'final_materialization_contract_unmet'
                late_fill['skip_kind'] = 'materialization_contract_unmet'
            updated_payload = self.attach_late_fill_state(updated_payload, late_fill)
            # A terminal repair can reveal a new, narrower materialization
            # defect (for example shared-CSS drift after HTML syntax repair).
            # If Closure promoted that exact defect as executable, continue
            # through the existing bounded successor instead of freezing a
            # user-visible needs-attention state. Non-executable or exhausted
            # checks remain terminally repair-needed below.
            updated_payload, terminal_repair_gap = self._project_terminal_closure_repair(
                updated_payload,
            )
            if terminal_repair_gap:
                updated_payload = self.refresh_runtime_graph_repair_evidence(updated_payload)
                projection_status = str(
                    terminal_repair_gap.get('terminal_closure_projection_status') or 'queued'
                ).strip().lower()
                return updated_payload, (
                    'pending' if projection_status == 'queued' else 'repair_needed'
                )
            updated_payload = self.refresh_runtime_graph_repair_evidence(updated_payload)
            updated_payload = self._review_terminal_graph_rebase_if_available(
                updated_payload,
                request_payload=request_payload,
                route_payload=route_payload,
            )
            return updated_payload, effective_status

        late_fill = self._supersede_resolved_composition_repairs(updated_payload, late_fill)
        late_fill['final_materialization_contract_status'] = 'fulfilled'
        late_fill['materialization_contract_unmet'] = False
        for key in (
            'materialization_contract_open_check_count',
            'materialization_contract_open_checks',
            'final_materialization_contract_reason',
        ):
            late_fill.pop(key, None)
        has_blocking_late_fill_state = any(
            isinstance(late_fill.get(key), list) and bool(late_fill.get(key))
            for key in ('failed_branches', 'pending_branches', 'active_branches', 'recovery_candidates')
        )
        if not has_blocking_late_fill_state and effective_status in {
            'failed',
            'partial_failed',
            'blocked',
            'repair_needed',
        }:
            effective_status = 'completed'
        if (
            str(late_fill.get('status') or '').strip().lower() == 'completed'
            and effective_status in {'failed', 'partial_failed', 'blocked', 'repair_needed'}
        ):
            effective_status = 'completed'
        if (
            not has_blocking_late_fill_state
            and str(late_fill.get('status') or '').strip().lower()
            in {'failed', 'partial_failed', 'blocked', 'repair_needed'}
        ):
            late_fill['status'] = 'completed'
            late_fill.pop('partial_failure', None)
            late_fill.pop('failed_at', None)
        late_fill = self._reconcile_terminal_satisfied_repair_loop(late_fill)
        updated_payload = self.attach_late_fill_state(updated_payload, late_fill)
        # The first Closure pass intentionally runs before terminal contract
        # reconciliation so it can expose repairable checks. Once those checks
        # are proven closed and the terminal state is attached, refresh again;
        # otherwise a stale pre-repair review can keep canonical lifecycle open.
        updated_payload = self.refresh_terminal_graph_closure_review(
            updated_payload,
            request_payload=request_payload,
            route_payload=route_payload,
            artifact_gap=artifact_gap,
        )
        updated_payload, terminal_repair_gap = self._project_terminal_closure_repair(
            updated_payload,
        )
        if terminal_repair_gap:
            updated_payload = self.refresh_runtime_graph_repair_evidence(updated_payload)
            projection_status = str(
                terminal_repair_gap.get('terminal_closure_projection_status') or 'queued'
            ).strip().lower()
            return updated_payload, ('pending' if projection_status == 'queued' else 'repair_needed')
        updated_payload = self.refresh_runtime_graph_repair_evidence(updated_payload)
        updated_payload = self._review_terminal_graph_rebase_if_available(
            updated_payload,
            request_payload=request_payload,
            route_payload=route_payload,
        )
        return updated_payload, effective_status

    def _project_terminal_closure_repair(
        self,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
        closure = (payload.get('runtime') or {}).get('graph_closure_review') or {}
        uncovered_content = (closure.get('content_requirement_policy') == 'named_saved_text_v1'
                             and bool(closure.get('unresolved_content_requirement_count')))
        if not callable(self.project_terminal_closure_repair):
            if uncovered_content:
                return self._blocked_terminal_closure_projection(payload, 'content_requirements_unverified')
            return payload, None
        try:
            projection = self.project_terminal_closure_repair(payload)
        except Exception as exc:  # noqa: BLE001
            logging.warning('Could not project terminal Closure repair work: %s', exc)
            return self._blocked_terminal_closure_projection(payload, str(exc))
        projection_status = str(
            projection.get('status') if isinstance(projection, Mapping) else ''
        ).strip().lower()
        if projection_status == 'not_applicable':
            projected_payload = (
                projection.get('response_payload')
                if isinstance(projection, Mapping)
                and isinstance(projection.get('response_payload'), dict)
                else payload
            )
            if uncovered_content:
                return self._blocked_terminal_closure_projection(projected_payload, 'content_requirements_unverified')
            return projected_payload, None
        if projection_status != 'queued':
            projected_payload = (
                projection.get('response_payload')
                if isinstance(projection, Mapping)
                and isinstance(projection.get('response_payload'), dict)
                else payload
            )
            reason = (
                str(projection.get('reason') or '').strip()
                if isinstance(projection, Mapping)
                else 'terminal_closure_projection_invalid'
            )
            return self._blocked_terminal_closure_projection(projected_payload, reason)
        updated_payload = (
            dict(projection.get('response_payload'))
            if isinstance(projection.get('response_payload'), Mapping)
            else dict(payload)
        )
        repair_gap = (
            dict(projection.get('artifact_gap'))
            if isinstance(projection.get('artifact_gap'), Mapping)
            else {}
        )
        pending_branches = self.normalize_late_fill_branches(repair_gap.get('pending_branches'))
        if not pending_branches:
            return self._blocked_terminal_closure_projection(
                updated_payload,
                'terminal_closure_projection_has_no_pending_branches',
            )
        response_frame = (
            updated_payload.get('response_frame')
            if isinstance(updated_payload.get('response_frame'), Mapping)
            else {}
        )
        parent_frame_id = str(
            response_frame.get('frame_id') or updated_payload.get('id') or ''
        ).strip()
        execution_identity = {
            'parent_frame_id': parent_frame_id,
            'branch_ids': sorted(
                self.branch_id(branch)
                for branch in pending_branches
                if self.branch_id(branch)
            ),
            'contract_ids': sorted(
                str(branch.get('repair_contract_id') or '').strip()
                for branch in pending_branches
                if str(branch.get('repair_contract_id') or '').strip()
            ),
        }
        execution_key = 'terminal-closure-repair-' + hashlib.sha256(
            json.dumps(execution_identity, sort_keys=True, separators=(',', ':')).encode('utf-8')
        ).hexdigest()[:24]
        pending_branches = [
            {
                **dict(branch),
                'terminal_closure_repair_execution_key': execution_key,
                'terminal_closure_repair_parent_frame_id': parent_frame_id,
            }
            for branch in pending_branches
        ]
        pending_capabilities = self.normalize_capability_list(
            [self.branch_capability(branch) for branch in pending_branches if self.branch_capability(branch)]
        )
        prior_late_fill = (
            dict(updated_payload.get('late_fill'))
            if isinstance(updated_payload.get('late_fill'), Mapping)
            else {}
        )
        reopen_record = {
            'kind': 'fruth.terminal_closure_repair_reopen',
            'status': 'queued',
            'authority': 'terminal_graph_closure_review',
            'branch_ids': [self.branch_id(branch) for branch in pending_branches if self.branch_id(branch)],
            'contract_ids': list(
                dict.fromkeys(
                    str(branch.get('repair_contract_id') or '').strip()
                    for branch in pending_branches
                    if str(branch.get('repair_contract_id') or '').strip()
                )
            ),
            'parent_frame_id': parent_frame_id,
            'execution_key': execution_key,
        }
        repair_gap.update(
            {
                'pending_branches': pending_branches,
                'pending_capabilities': pending_capabilities,
                'expected_capability': (
                    self.normalize_capability(repair_gap.get('expected_capability'))
                    or (pending_capabilities[0] if pending_capabilities else None)
                ),
                'active_capability': (
                    self.normalize_capability(repair_gap.get('active_capability'))
                    or (pending_capabilities[0] if pending_capabilities else None)
                ),
                'authoritative_pending_branches': True,
                'pending_branch_scope': 'exact_terminal_closure_repair',
                'terminal_closure_projection_status': 'queued',
            }
        )
        pending_late_fill = self.build_late_fill_state(
            repair_gap,
            status='pending',
            prior_state=prior_late_fill,
            extra={
                'pending_branches': pending_branches,
                'pending_capabilities': pending_capabilities,
                'active_branches': [],
                'fill_results': prior_late_fill.get('fill_results') or [],
                'completed_branches': prior_late_fill.get('completed_branches') or [],
                'failed_branches': prior_late_fill.get('failed_branches') or [],
                'cancelled_branches': prior_late_fill.get('cancelled_branches') or [],
                'final_materialization_contract_status': prior_late_fill.get(
                    'final_materialization_contract_status'
                ),
                'materialization_contract_unmet': prior_late_fill.get('materialization_contract_unmet'),
                'terminal_closure_repair_reopen': reopen_record,
            },
        )
        return self.attach_late_fill_state(updated_payload, pending_late_fill), repair_gap

    def _blocked_terminal_closure_projection(
        self,
        payload: dict[str, Any],
        reason: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        updated_payload = dict(payload or {})
        late_fill = (
            dict(updated_payload.get('late_fill'))
            if isinstance(updated_payload.get('late_fill'), Mapping)
            else {}
        )
        late_fill['status'] = 'repair_needed'
        late_fill['terminal_closure_repair_reopen'] = {
            'kind': 'fruth.terminal_closure_repair_reopen',
            'status': 'blocked',
            'authority': 'terminal_graph_closure_review',
            'reason': str(reason or 'terminal_closure_projection_blocked').strip(),
        }
        updated_payload = self.attach_late_fill_state(updated_payload, late_fill)
        return updated_payload, {
            'terminal_closure_projection_status': 'blocked',
            'reason': late_fill['terminal_closure_repair_reopen']['reason'],
        }

    @staticmethod
    def _terminal_closure_repair_execution_key(payload: Any) -> str:
        if not isinstance(payload, Mapping):
            return ''
        late_fill = payload.get('late_fill') if isinstance(payload.get('late_fill'), Mapping) else {}
        reopen = (
            late_fill.get('terminal_closure_repair_reopen')
            if isinstance(late_fill.get('terminal_closure_repair_reopen'), Mapping)
            else {}
        )
        return str(reopen.get('execution_key') or '').strip()

    @classmethod
    def _payload_has_terminal_closure_repair_execution(
        cls,
        payload: Any,
        execution_key: str,
    ) -> bool:
        if not isinstance(payload, Mapping) or not execution_key:
            return False
        late_fill = payload.get('late_fill') if isinstance(payload.get('late_fill'), Mapping) else {}
        terminal_records = []
        for key in ('completed_branches', 'failed_branches', 'cancelled_branches'):
            records = late_fill.get(key) if isinstance(late_fill.get(key), list) else []
            terminal_records.extend(
                branch for branch in records if isinstance(branch, Mapping)
                and str(branch.get('terminal_closure_repair_execution_key') or '').strip()
                == execution_key
            )
        if not terminal_records:
            return False
        reopen = late_fill.get('terminal_closure_repair_reopen') or {}
        if isinstance(reopen, Mapping) and str(reopen.get('execution_key') or '').strip() == execution_key:
            admitted = reopen.get('branch_ids')
            admitted_ids = {
                value.strip() for value in admitted
                if isinstance(value, str) and value.strip()
            } if isinstance(admitted, list) else set()
            terminal_ids = {str(branch.get('branch_id') or '').strip() for branch in terminal_records}
            for branch in late_fill.get('pending_branches') or []:
                if not isinstance(branch, Mapping):
                    continue
                branch_id = str(branch.get('branch_id') or '').strip()
                if (branch_id and branch_id in admitted_ids and branch_id not in terminal_ids
                        and str(branch.get('terminal_closure_repair_execution_key') or '').strip() == execution_key):
                    # One settled/cancelled member does not complete its sibling.
                    # This only permits normal admission/gates after an explicit
                    # scheduling event; it neither schedules nor revives a result.
                    return False
        return True

    def _terminal_closure_repair_handoff(
        self,
        response_payload: Mapping[str, Any],
        *,
        request_payload: Mapping[str, Any],
        assistant_message: str,
        source_route_payload: Optional[Mapping[str, Any]],
    ) -> Optional[dict[str, Any]]:
        late_fill = response_payload.get('late_fill') if isinstance(response_payload.get('late_fill'), Mapping) else {}
        reopen = (
            late_fill.get('terminal_closure_repair_reopen')
            if isinstance(late_fill.get('terminal_closure_repair_reopen'), Mapping)
            else {}
        )
        pending_branches = self.normalize_late_fill_branches(late_fill.get('pending_branches'))
        if str(reopen.get('status') or '').strip().lower() != 'queued' or not pending_branches:
            return None
        pending_capabilities = self.normalize_capability_list(
            [self.branch_capability(branch) for branch in pending_branches if self.branch_capability(branch)]
        )
        artifact_gap = {
            'code': str(late_fill.get('code') or 'closure_review_repair').strip(),
            'trigger': str(late_fill.get('trigger') or 'inference_repair_feedback').strip(),
            'expected_capability': (
                self.normalize_capability(late_fill.get('expected_capability'))
                or (pending_capabilities[0] if pending_capabilities else None)
            ),
            'active_capability': (
                self.normalize_capability(late_fill.get('active_capability'))
                or (pending_capabilities[0] if pending_capabilities else None)
            ),
            'missing_artifact_type': str(late_fill.get('missing_artifact_type') or '').strip() or None,
            'pending_branches': pending_branches,
            'pending_capabilities': pending_capabilities,
            'authoritative_pending_branches': True,
            'pending_branch_scope': 'exact_terminal_closure_repair',
            'inference_repair_feedback': late_fill.get('inference_repair_feedback'),
            'repair_loop': late_fill.get('repair_loop'),
            'repair_rebuild_contracts': late_fill.get('repair_rebuild_contracts'),
            'terminal_closure_repair_reopen': dict(reopen),
        }
        return {
            'response_payload': dict(response_payload),
            'request_payload': dict(request_payload),
            'assistant_message': str(assistant_message or '').strip(),
            'artifact_gap': {
                key: value
                for key, value in artifact_gap.items()
                if value not in (None, '', [], {})
            },
            'source_route_payload': (
                dict(source_route_payload)
                if isinstance(source_route_payload, Mapping)
                else None
            ),
        }

    @staticmethod
    def _post_artifact_follow_up_instruction(
        original_prompt: str,
        evidence: str = '',
        *,
        structured_output_contract: Optional[Mapping[str, Any]] = None,
    ) -> str:
        prompt_text = str(original_prompt or '').strip()
        tail = ''
        markers = list(re.finditer(
            r'\b(?:then|afterwards|danach|anschliessend|anschließend)\b',
            prompt_text,
            flags=re.IGNORECASE,
        ))
        if markers:
            tail = prompt_text[markers[-1].end():]
        if not tail:
            post_match = re.search(
                r'\b(?:compare|confirm|caption|describe|summari[sz]e|write|explain|'
                r'vergleiche|bestaetige|bestätige|beschreibe|schreibe|fasse)\b.+$',
                prompt_text,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if post_match:
                tail = post_match.group(0)
        tail = re.sub(r'\s+', ' ', tail).strip(' ,.;:-')
        if tail:
            task = tail[:1].upper() + tail[1:]
        else:
            task = 'Complete only the requested post-artifact text follow-up.'
        contract = (
            structured_output_contract
            if isinstance(structured_output_contract, Mapping)
            else {}
        )
        lines = [task]
        if contract:
            lines.extend(
                [
                    'Return exactly one JSON object and nothing else: no array, Markdown fence, commentary, or duplicate candidate rows.',
                    'Populate every required field from its named runtime evidence source. Copy canonical artifact_ref values verbatim and never substitute branch ids, paths, or sibling identities for them.',
                ]
            )
            for binding in contract.get('required_bindings') or []:
                if not isinstance(binding, Mapping):
                    continue
                field_name = str(binding.get('field_name') or '').strip()
                field_role = str(binding.get('field_role') or '').strip()
                source_phase_id = str(binding.get('source_phase_id') or '').strip()
                artifact_ref = str(binding.get('artifact_ref') or '').strip()
                message_id = str(binding.get('message_id') or '').strip()
                source = source_phase_id or artifact_ref or message_id or str(
                    binding.get('source_kind') or 'runtime evidence'
                ).strip()
                if field_name:
                    lines.append(
                        f'Required JSON field `{field_name}` ({field_role or "runtime binding"}) must use only source `{source}`.'
                    )
                elif field_role:
                    lines.append(
                        f'Runtime evidence role `{field_role}` is bound to source `{source}`; preserve it without regeneration.'
                    )
        lines.extend([
            'This is a post-artifact text phase. Use the fulfilled dependency artifacts/evidence; do not restart the original request, regenerate media, or say you cannot generate the artifacts.',
            'The dependency evidence is already fulfilled branch output for this phase; treat it as available input and do not ask the user to provide the artifact again.',
            'For a requested structured join, emit only the requested final structure. Treat each dependency block as evidence for its own branch; do not concatenate duplicate candidate rows or reuse one artifact reference for multiple branch identities.',
        ])
        if not contract:
            lines.append(
                'If dependency evidence includes both original text and transcript text, compare those strings directly and report whether they match.'
            )
        evidence_text = str(evidence or '').strip()
        if evidence_text:
            lines.append(f'Dependency evidence:\n{evidence_text}')
        return '\n\n'.join(lines).strip()

    @classmethod
    def _text_artifact_materialization_instruction(
        cls,
        original_prompt: str,
        artifact_gap: Mapping[str, Any],
    ) -> str:
        gap = artifact_gap if isinstance(artifact_gap, Mapping) else {}
        raw_requests = gap.get('text_artifact_requests') if isinstance(gap.get('text_artifact_requests'), list) else []
        text_artifact_requests = [
            {
                'extension': str(item.get('extension') or '').strip().lower().lstrip('.'),
                'source_name': str(item.get('source_name') or '').strip(),
            }
            for item in raw_requests
            if isinstance(item, Mapping)
            and str(item.get('extension') or '').strip()
            and str(item.get('source_name') or '').strip()
        ]
        artifact_request = gap.get('artifact_request') if isinstance(gap.get('artifact_request'), Mapping) else {}
        extension = str(
            gap.get('text_artifact_extension')
            or artifact_request.get('extension')
            or 'txt'
        ).strip().lower()
        source_name = str(
            gap.get('text_artifact_source_name')
            or artifact_request.get('source_name')
            or f'generated-{extension or "txt"}'
        ).strip()
        content_payload = str(gap.get('content_payload') or '').strip()
        target_path = str(
            gap.get('text_artifact_target_path')
            or artifact_request.get('target_path')
            or ''
        ).strip()
        saved_contract = saved_file_dependency_contract(gap)
        if saved_contract:
            read = gap.get('saved_file_read_evidence') or (gap.get('execution_contract') or {}).get('saved_file_read_evidence')
            if not read:
                raise ValueError('saved_file_read_evidence_missing')
            return saved_file_consumer_prompt(saved_contract, read, artifact_request.get('saved_file_syntax_repair'))
        if content_payload and text_artifact_materialization._text_artifact_revision_required(gap):
            # Revision packets are constructed only from a complete, bounded
            # canonical source snapshot. The selected reply itself is not
            # repeated here and cannot become execution authority.
            prompt_text = str(original_prompt or '').strip()
            if len(prompt_text) > 12_000:
                prompt_text = f'{prompt_text[:12_000].rstrip()}\n[request context truncated at bounded revision limit]'
            lines = [
                f'Update the existing {extension or "text"} text artifact `{source_name}` only.',
                f'Target path: {target_path or source_name}',
                (
                    'The current user request below is the authoritative edit delta. '
                    'The source snapshot is input evidence only and does not fulfill this branch.'
                    if prompt_text
                    else 'The current user edit request in Fruth promoted context is the authoritative edit delta. '
                    'The source snapshot is input evidence only and does not fulfill this branch.'
                ),
                'Output only the complete updated file body for that one target artifact.',
                'Preserve all existing copy, structure, selectors, behavior, links, and design outside the changes directly required by the current request.',
                'Do not redesign, summarize, omit unchanged sections, replace unrelated content, add commentary, or restart the earlier multi-file request.',
            ]
            if prompt_text:
                lines.extend(
                    [
                        'Current user edit request:',
                        prompt_text,
                    ]
                )
            lines.extend(
                [
                    'Complete canonical source snapshot:',
                    '--- SOURCE FILE START ---',
                    content_payload,
                    '--- SOURCE FILE END ---',
                ]
            )
            return '\n\n'.join(lines).strip()
        if content_payload and text_artifact_materialization._artifact_gap_is_authoritative_bounded_text_artifact_repair(gap):
            if len(content_payload) > 90_000:
                content_payload = f'{content_payload[:90_000].rstrip()}\n\n[repair evidence truncated for prompt size]'
            lines = [
                f'Repair the existing {extension or "text"} text artifact `{source_name}` only.',
                f'Target path: {target_path or source_name}',
                'This is a bounded closure repair, not a regeneration task.',
                'Output only the complete corrected file body for that one target artifact.',
                'Preserve copy, layout intent, class names, and valid runtime artifact links unless the listed defect directly requires a narrow change.',
                'Do not redesign, translate, rename unrelated classes, replace unrelated content, add commentary, or restart the original request.',
                'Repair evidence and current saved file content:',
                content_payload,
            ]
            return '\n\n'.join(lines).strip()
        prompt_text = re.sub(r'\s+', ' ', str(original_prompt or '').strip())
        if len(prompt_text) > 1200:
            prompt_text = f'{prompt_text[:1200].rstrip()}...'
        if len(text_artifact_requests) > 1:
            request_lines = [
                f'- `{item["source_name"]}` as {item["extension"]}'
                for item in text_artifact_requests
            ]
            lines = [
                'Write the complete file payloads for these requested local text artifacts:',
                *request_lines,
                'Output exactly one fenced code block per file, in the same order, using each file extension as the fence language.',
                'Treat every listed file as one coherent local bundle: use the exact listed basenames for relative links, keep shared data and navigation consistent, and make HTML class names agree with the selectors in shared CSS.',
                'The set is atomic. Return every listed file again; do not return only a changed, missing, or previously failed member.',
                'Do not output planner JSON, request_ir, output_obligations, candidate_graph, or commentary outside those code blocks.',
            ]
            cohort_recovery = (
                gap.get('coalesced_text_artifact_recovery')
                if isinstance(
                    gap.get('coalesced_text_artifact_recovery'),
                    Mapping,
                )
                else {}
            )
            if cohort_recovery:
                lines.append(
                    'This is one bounded complete-set recovery attempt because '
                    'the prior response failed Fruth atomic bundle validation. '
                    'Correct the complete ordered set in this response; do not '
                    'split the files into independent solutions.'
                )
            if prompt_text:
                lines.append(f'Original user request for bounded intent context: {prompt_text}')
            return '\n\n'.join(lines).strip()
        lines = [
            f'Write the complete {extension or "text"} file payload for `{source_name}`.',
            'Output only the file body for that one file.',
            'Do not output planner JSON, request_ir, output_obligations, candidate_graph, or commentary outside the artifact payload.',
        ]
        if prompt_text:
            lines.append(f'Original user request for bounded intent context: {prompt_text}')
        return '\n\n'.join(lines).strip()

    @staticmethod
    def _sequential_branch_local_artifact_labels(original_prompt: str) -> list[str]:
        labels = [
            str(match.group('label') or '').strip().upper()
            for match in _BRANCH_LOCAL_ARTIFACT_ALPHA_LABEL_RE.finditer(
                str(original_prompt or '')
            )
        ]
        if len(labels) < 2:
            return []
        expected = [chr(ord('A') + index) for index in range(len(labels))]
        return labels if labels == expected else []

    @classmethod
    def _branch_local_vision_analysis_directive(cls, original_prompt: str) -> str:
        """Extract the vision-owned instruction without replaying the root task."""

        prompt_text = re.sub(r'\s+', ' ', str(original_prompt or '')).strip()
        if not prompt_text:
            return ''
        candidates: list[tuple[int, int, int, str]] = []
        for segment_index, segment in enumerate(
            re.split(r'(?<=[.!?;])\s+', prompt_text)
        ):
            for start in _BRANCH_LOCAL_VISION_DIRECTIVE_START_RE.finditer(segment):
                directive = segment[start.start():].strip(' ,.;:-')
                stop_patterns = [_BRANCH_LOCAL_VISION_DIRECTIVE_STOP_RE]
                if cls._branch_local_vision_has_global_join(original_prompt):
                    stop_patterns.append(_BRANCH_LOCAL_VISION_GLOBAL_JOIN_STOP_RE)
                stop_matches = [
                    match
                    for pattern in stop_patterns
                    if (match := pattern.search(directive))
                ]
                if stop_matches:
                    stop = min(stop_matches, key=lambda match: match.start())
                    directive = directive[:stop.start()].strip(' ,.;:-')
                if not directive or not _BRANCH_LOCAL_VISION_TARGET_RE.search(directive):
                    continue
                action = str(start.group(0) or '').strip().lower()
                priority = 1
                if re.match(
                    r'(?:analy|inspect|examin|analysier|untersuch|pr[uü]f)',
                    action,
                    flags=re.IGNORECASE,
                ):
                    priority = 3
                elif re.match(
                    r'(?:describ|caption|beschreib|schilder)',
                    action,
                    flags=re.IGNORECASE,
                ):
                    priority = 2
                candidates.append(
                    (priority, segment_index, start.start(), directive[:600].rstrip())
                )
        if not candidates:
            return ''
        return max(candidates, key=lambda item: (item[0], item[1], item[2]))[3]

    @staticmethod
    def _branch_local_vision_evaluation_focus(original_prompt: str) -> str:
        """Extract only criteria that each evidence branch can judge independently."""

        prompt_text = re.sub(r'\s+', ' ', str(original_prompt or '')).strip()
        for pattern in _BRANCH_LOCAL_VISION_FOCUS_PATTERNS:
            match = pattern.search(prompt_text)
            if not match:
                continue
            focus = str(match.group('focus') or '').strip(' ,.;:-')
            if focus:
                return focus[:180].rstrip()
        return ''

    _branch_local_vision_requires_identity_handoff = staticmethod(BranchDependencyEvidence._branch_local_vision_requires_identity_handoff)

    @classmethod
    def _branch_local_vision_has_global_join(cls, original_prompt: str) -> bool:
        prompt_text = str(original_prompt or '')
        if _BRANCH_LOCAL_VISION_EXPLICIT_GLOBAL_JOIN_RE.search(prompt_text):
            return True
        has_multiple_artifacts = bool(
            _BRANCH_LOCAL_VISION_MULTI_ARTIFACT_RE.search(prompt_text)
            or _BRANCH_LOCAL_VISION_FOR_MULTIPLE_LABELS_RE.search(prompt_text)
            or len(cls._sequential_branch_local_artifact_labels(prompt_text)) >= 2
        )
        return bool(
            has_multiple_artifacts
            and BranchDependencyEvidence._branch_local_vision_requires_identity_handoff(prompt_text)
        )

    @classmethod
    def _vision_artifact_analysis_instruction(
        cls,
        original_prompt: str,
        evidence: str = '',
        *,
        execution_contract: Optional[Mapping[str, Any]] = None,
    ) -> str:
        contract = execution_contract if isinstance(execution_contract, Mapping) else {}
        try:
            branch_index = int(contract.get('queue_index') or 0)
        except (TypeError, ValueError):
            branch_index = 0
        labels = cls._sequential_branch_local_artifact_labels(original_prompt)
        branch_label = (
            labels[branch_index - 1]
            if branch_index > 0 and branch_index <= len(labels)
            else ''
        )
        local_analysis_directive = cls._branch_local_vision_analysis_directive(original_prompt)
        local_evaluation_focus = cls._branch_local_vision_evaluation_focus(original_prompt)
        requires_identity_handoff = BranchDependencyEvidence._branch_local_vision_requires_identity_handoff(
            original_prompt
        )
        # Express the bounded task directly. The previous authority/override
        # wording triggered AFM rejections on ordinary image inspections.
        lines = [
            'Inspect exactly one actual attached generated image and return one concise report of what is visibly present.',
            'Base every observation on this attachment. Other images, image generation, and the combined table, list, or JSON output belong to separate tasks.',
            'Use the attached image and its reference below. Keep the report specific to this image so a later text branch can combine it with other reports.',
        ]
        if local_analysis_directive:
            lines.append(
                'Requested branch-local analysis directive (apply it only to this attachment; '
                f'plural wording means this single branch artifact): {local_analysis_directive}'
            )
        if local_evaluation_focus:
            lines.append(
                'Branch-local visual criteria inherited from the final evaluation: report visible '
                f'evidence for {local_evaluation_focus} in this attachment only; do not assess '
                'sibling modalities or perform the global comparison.'
            )
        if branch_index > 0:
            lines.append(f'Branch-local artifact ordinal: {branch_index}.')
        if branch_label:
            lines.append(
                f'Branch-local label: {branch_label}. Use only {branch_label} for this attachment.'
            )
        if requires_identity_handoff:
            if branch_label:
                lines.append(
                    f'Include label {branch_label} explicitly in this single-artifact evidence report.'
                )
            lines.append(
                'Include the exact attached artifact reference or path from Dependency evidence '
                'verbatim in this report. Do not invent, normalize, omit, or reuse a sibling identity.'
            )
        evidence_text = str(evidence or '').strip()
        if evidence_text:
            lines.append(f'Dependency evidence:\n{evidence_text}')
        return '\n\n'.join(lines).strip()

    def focus_late_fill_branch_gap_payload(
        self,
        branch: Mapping[str, Any],
        branch_gap: dict[str, Any],
        *,
        capability: Optional[str],
    ) -> dict[str, Any]:
        payload = dict(branch_gap or {})
        content_payload = str(payload.get('content_payload') or '').strip()
        if not content_payload:
            return payload

        if (
            capability == self.capability_text_to_speech
            and control_json_envelope_suspected(content_payload)
        ):
            payload.pop('prompt', None)
            payload['branch_contract_error'] = 'control_envelope_not_speakable'
            payload['materialization_blocked'] = True
            payload['repair_action'] = RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT
            payload['content_payload_source'] = 'rejected_control_envelope'
            return payload

        artifact_prompt = str(payload.get('artifact_prompt') or '').strip()
        artifact_prompt_source = str(payload.get('artifact_prompt_source') or '').strip()
        authoritative_artifact_prompt_sources = {
            'semantic_batch_prompt',
            'semantic_batch_prompts',
            'semantic_prepare_phase_output',
            'current_turn_direct_image_clause',
            'action_input',
            'prompt_blockquote_section',
            'quoted_prompt_section',
            'inline_prompt_capsule',
            'current_turn_explicit_image_manifest',
        }
        should_focus_image_prompt = (
            not artifact_prompt
            or artifact_prompt == content_payload
            or (
                artifact_prompt_source not in authoritative_artifact_prompt_sources
                and len(artifact_prompt) > 240
                and artifact_prompt in content_payload
            )
        )
        if capability == self.capability_image_generation and should_focus_image_prompt:
            prompt_units = self._extract_late_fill_image_prompt_units(content_payload)
            if prompt_units:
                selected_index = self._branch_prompt_selection_index(branch, len(prompt_units))
                if selected_index <= 0:
                    payload.pop('artifact_prompt', None)
                    payload['branch_contract_error'] = 'incomplete_image_prompt_batch'
                    payload['candidate_extraction_issue'] = 'missing_branch_local_image_prompt_slot'
                    payload['materialization_blocked'] = True
                    payload['repair_action'] = RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT
                    return payload
                selected_prompt = prompt_units[selected_index - 1].strip()
                if selected_prompt:
                    payload['artifact_prompt'] = selected_prompt
                    payload['artifact_prompt_source'] = 'focused_image_prompt_slot'
                    payload['image_prompt_selection_index'] = selected_index
                    return payload
            candidates = [
                (index, self._strip_late_fill_prompt_label(unit), self._late_fill_image_prompt_score(unit))
                for index, unit in enumerate(self._split_late_fill_content_units(content_payload), start=1)
            ]
            viable = [(index, unit, score) for index, unit, score in candidates if unit and score > 0]
            if viable:
                selected_index = self._branch_prompt_selection_index(branch, len(viable))
                if selected_index <= 0:
                    payload.pop('artifact_prompt', None)
                    payload['branch_contract_error'] = 'incomplete_image_prompt_batch'
                    payload['candidate_extraction_issue'] = 'missing_branch_local_image_prompt_slot'
                    payload['materialization_blocked'] = True
                    payload['repair_action'] = RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT
                    return payload
                selected = viable[selected_index - 1]
                payload['artifact_prompt'] = selected[1]
                payload['artifact_prompt_source'] = 'focused_content_payload'
                payload['image_prompt_selection_index'] = selected_index
            return payload

        if capability == self.capability_text_to_speech:
            selection_policy = str(
                branch.get('selection_policy')
                or payload.get('selection_policy')
                or ''
            ).strip().lower()
            stage_direction = str(
                branch.get('stage_direction')
                or payload.get('stage_direction')
                or ''
            ).strip()
            counted_variant_match = re.fullmatch(
                r'materialize_requested_audio_variant_(\d+)',
                stage_direction,
            )
            if counted_variant_match and selection_policy != 'selected_candidate_only':
                payload['branch_contract_error'] = 'ambiguous_audio_variant_contract'
                payload['materialization_blocked'] = True
                payload['repair_action'] = RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT
                return payload
            if selection_policy in {'best_candidate_only', 'selected_candidate_only', 'selected_text_only'}:
                candidate_contract = self._late_fill_candidate_selection_contract(
                    content_payload
                )
                candidate_units = [
                    str(unit or '').strip()
                    for unit in (candidate_contract.get('units') or [])
                    if str(unit or '').strip()
                ]
                candidate_extraction_source = str(
                    candidate_contract.get('source') or ''
                ).strip()
                candidate_extraction_issue = str(
                    candidate_contract.get('issue') or ''
                ).strip()
                if candidate_extraction_issue:
                    payload['branch_contract_error'] = 'selected_candidate_unavailable'
                    payload['candidate_extraction_issue'] = candidate_extraction_issue
                    if candidate_extraction_source:
                        payload['candidate_extraction_source'] = candidate_extraction_source
                    payload['materialization_blocked'] = True
                    payload['repair_action'] = RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT
                    return payload
                raw_selection_count = branch.get('candidate_selection_count')
                if raw_selection_count in (None, ''):
                    raw_selection_count = payload.get('candidate_selection_count')
                if isinstance(raw_selection_count, bool):
                    normalized_selection_count = 0
                elif isinstance(raw_selection_count, int):
                    normalized_selection_count = raw_selection_count
                elif (
                    isinstance(raw_selection_count, str)
                    and raw_selection_count.isascii()
                    and raw_selection_count.isdigit()
                    and 0 < len(raw_selection_count) <= 6
                ):
                    normalized_selection_count = int(raw_selection_count)
                else:
                    normalized_selection_count = 0
                if counted_variant_match:
                    expected_index = int(counted_variant_match.group(1))
                    candidate_index = branch.get('candidate_selection_index')
                    if candidate_index in (None, ''):
                        candidate_index = payload.get('candidate_selection_index')
                    variant_index = branch.get('audio_variant_index')
                    if variant_index in (None, ''):
                        variant_index = payload.get('audio_variant_index')
                    try:
                        normalized_candidate_index = int(candidate_index)
                        normalized_variant_index = int(variant_index)
                    except (TypeError, ValueError):
                        normalized_candidate_index = 0
                        normalized_variant_index = 0
                    if (
                        normalized_selection_count <= 1
                        or normalized_candidate_index != expected_index
                        or normalized_variant_index != expected_index
                    ):
                        payload['branch_contract_error'] = 'ambiguous_audio_variant_contract'
                        payload['materialization_blocked'] = True
                        payload['repair_action'] = RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT
                        return payload
                if normalized_selection_count > 0:
                    normalized_units = [
                        re.sub(r'\s+', ' ', unit).strip().casefold()
                        for unit in candidate_units
                        if str(unit or '').strip()
                    ]
                    if len(normalized_units) != normalized_selection_count:
                        payload['branch_contract_error'] = 'selected_candidate_unavailable'
                        payload['materialization_blocked'] = True
                        payload['repair_action'] = RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT
                        return payload
                    if len(set(normalized_units)) != len(normalized_units):
                        payload['branch_contract_error'] = 'selected_candidate_not_distinct'
                        payload['materialization_blocked'] = True
                        payload['repair_action'] = RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT
                        return payload
                raw_selection_index = branch.get('candidate_selection_index')
                if raw_selection_index in (None, ''):
                    raw_selection_index = payload.get('candidate_selection_index')
                if selection_policy == 'best_candidate_only' and raw_selection_index in (None, ''):
                    raw_selection_index = 1
                if isinstance(raw_selection_index, bool):
                    normalized_selection_index = 0
                elif isinstance(raw_selection_index, int):
                    normalized_selection_index = raw_selection_index
                elif (
                    isinstance(raw_selection_index, str)
                    and raw_selection_index.isascii()
                    and raw_selection_index.isdigit()
                    and 0 < len(raw_selection_index) <= 6
                ):
                    normalized_selection_index = int(raw_selection_index)
                else:
                    normalized_selection_index = 0
                selected = (
                    candidate_units[normalized_selection_index - 1]
                    if 1 <= normalized_selection_index <= len(candidate_units)
                    else ''
                )
                if selected:
                    payload['content_payload'] = selected
                    payload['content_payload_source'] = 'selected_candidate_from_phase_output'
                    payload['selection_policy_applied'] = selection_policy
                    if candidate_extraction_source:
                        payload['candidate_extraction_source'] = candidate_extraction_source
                    return payload
                payload['branch_contract_error'] = 'selected_candidate_unavailable'
                if candidate_extraction_source:
                    payload['candidate_extraction_source'] = candidate_extraction_source
                payload['materialization_blocked'] = True
                payload['repair_action'] = RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT
                return payload
            labeled_speakable_sections = self._late_fill_labeled_speakable_sections(
                content_payload
            )
            labeled_audio_contract = self._late_fill_labeled_audio_candidate_contract(
                content_payload
            )
            if labeled_audio_contract.get('marker_detected'):
                labeled_audio_issue = str(
                    labeled_audio_contract.get('issue') or ''
                ).strip()
                labeled_audio_units = [
                    str(unit or '').strip()
                    for unit in (labeled_audio_contract.get('units') or [])
                    if str(unit or '').strip()
                ]
                if labeled_audio_issue or len(labeled_audio_units) != 1:
                    payload['branch_contract_error'] = 'ambiguous_audio_variant_contract'
                    payload['candidate_extraction_issue'] = (
                        labeled_audio_issue or 'multiple_audio_variant_bodies_without_selection'
                    )
                    payload['candidate_extraction_source'] = (
                        'labeled_audio_variant_sections'
                    )
                    payload['materialization_blocked'] = True
                    payload['repair_action'] = RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT
                    return payload
                payload['content_payload'] = labeled_audio_units[0]
                payload['content_payload_source'] = 'focused_labeled_speakable_text'
                payload['candidate_extraction_source'] = 'labeled_audio_variant_sections'
                return payload
            if len(labeled_speakable_sections) == 1:
                payload['content_payload'] = labeled_speakable_sections[0]
                payload['content_payload_source'] = 'focused_labeled_speakable_text'
                payload['candidate_extraction_source'] = 'labeled_speakable_section'
                return payload
            if len(labeled_speakable_sections) > 1:
                payload['branch_contract_error'] = 'ambiguous_audio_variant_contract'
                payload['candidate_extraction_issue'] = 'multiple_labeled_speakable_sections'
                payload['candidate_extraction_source'] = 'labeled_speakable_section'
                payload['materialization_blocked'] = True
                payload['repair_action'] = RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT
                return payload
            units = self._split_late_fill_content_units(content_payload)
            scored = [
                (index, unit, self._late_fill_speakable_text_score(unit))
                for index, unit in enumerate(units, start=1)
                if unit
            ]
            has_non_speakable_media_prompt = any(score <= -5 for _index, _unit, score in scored)
            has_labeled_speakable_text = any(score >= 8 for _index, _unit, score in scored)
            viable = [(index, unit, score) for index, unit, score in scored if score > -5]
            if viable and (has_non_speakable_media_prompt or has_labeled_speakable_text):
                selected = max(viable, key=lambda item: item[2])
                payload['content_payload'] = selected[1]
                payload['content_payload_source'] = 'focused_content_payload'
            return payload

        return payload

    def failed_dependency_ids_for_branch(
        self,
        branch: Mapping[str, Any],
        *,
        current_payload: Mapping[str, Any],
    ) -> list[str]:
        if not isinstance(branch, Mapping):
            return []
        dependency_ids: list[str] = []

        def _add_dependency_values(raw_value: Any) -> None:
            values = raw_value if isinstance(raw_value, (list, tuple, set)) else [raw_value]
            for value in values:
                token = str(value or '').strip()
                if token and token not in dependency_ids:
                    dependency_ids.append(token)

        _add_dependency_values(branch.get('depends_on') or branch.get('dependsOn'))
        execution_contract = (
            branch.get('execution_contract')
            if isinstance(branch.get('execution_contract'), Mapping)
            else {}
        )
        _add_dependency_values(execution_contract.get('depends_on') or execution_contract.get('dependencies'))
        if not dependency_ids:
            return []

        late_fill = (
            current_payload.get('late_fill')
            if isinstance((current_payload or {}).get('late_fill'), Mapping)
            else {}
        )
        failed_records = self.normalize_late_fill_branches(late_fill.get('failed_branches'))
        failed_tokens: set[str] = set()
        for record in failed_records:
            if not isinstance(record, Mapping):
                continue
            for key in ('branch_id', 'phase_id', 'task_id', 'workload_task_id', 'obligation_id'):
                token = str(record.get(key) or '').strip()
                if token:
                    failed_tokens.add(token)
            error = record.get('error') if isinstance(record.get('error'), Mapping) else {}
            failed_dependency_ids = error.get('failed_dependency_ids')
            if isinstance(failed_dependency_ids, (list, tuple, set)):
                for value in failed_dependency_ids:
                    token = str(value or '').strip()
                    if token:
                        failed_tokens.add(token)

        return [dependency_id for dependency_id in dependency_ids if dependency_id in failed_tokens]

    def _dependency_result_artifact_identity_evidence(
        self,
        result: Mapping[str, Any],
        *,
        fill_results: list[Any],
        current_payload: Mapping[str, Any],
    ) -> str:
        return self.branch_dependency_evidence._dependency_result_artifact_identity_evidence(result, fill_results=fill_results, current_payload=current_payload)

    _bounded_visual_evidence_from_selected_message = staticmethod(BranchDependencyEvidence._bounded_visual_evidence_from_selected_message)

    _selected_reference_records_from_payload = staticmethod(BranchDependencyEvidence._selected_reference_records_from_payload)

    _selected_reference_dependency_payload = staticmethod(BranchDependencyEvidence._selected_reference_dependency_payload)

    def _saved_file_dependency_payload(self, branch, current_payload):
        return self.branch_dependency_evidence._saved_file_dependency_payload(branch, current_payload)

    def saved_file_consumption_error(self, branch, infer_result, *, current_payload):
        return self.branch_dependency_evidence.saved_file_consumption_error(branch, infer_result, current_payload=current_payload)

    def branch_dependency_payload(
        self,
        branch: Mapping[str, Any],
        *,
        current_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self.branch_dependency_evidence.branch_dependency_payload(branch, current_payload=current_payload)

    def merge_late_fill_result_fields(
        self,
        response_payload: dict[str, Any],
        infer_result: dict[str, Any],
    ) -> dict[str, Any]:
        return self.branch_dependency_evidence.merge_late_fill_result_fields(response_payload, infer_result)

    def build_branch_local_late_fill_artifacts(
        self,
        response_payload: Mapping[str, Any],
        infer_result: Mapping[str, Any],
        *,
        capability: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        return self.branch_dependency_evidence.build_branch_local_late_fill_artifacts(response_payload, infer_result, capability=capability)

    def attach_late_fill_result_artifact_identity(
        self,
        fill_record: Mapping[str, Any],
        response_payload: Mapping[str, Any],
        infer_result: Mapping[str, Any],
        *,
        capability: Optional[str] = None,
    ) -> dict[str, Any]:
        return self.branch_dependency_evidence.attach_late_fill_result_artifact_identity(fill_record, response_payload, infer_result, capability=capability)

    def persist_raw_image_result_if_possible(
        self,
        infer_result: dict[str, Any],
        *,
        effective_data: Optional[Mapping[str, Any]] = None,
        late_fill_instance: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        if not isinstance(infer_result, dict):
            return {}
        if str(infer_result.get('saved_image_path') or '').strip():
            return infer_result
        data_url = _extract_raw_image_data_url(infer_result)
        if not data_url:
            return infer_result
        effective_payload = effective_data if isinstance(effective_data, Mapping) else {}
        instance_payload = late_fill_instance if isinstance(late_fill_instance, Mapping) else {}
        model_name = str(
            infer_result.get('model')
            or effective_payload.get('model')
            or instance_payload.get('model')
            or 'image'
        ).strip() or 'image'
        try:
            saved_image_path = self.persist_image_data_url_locally(data_url, model_name)
        except Exception as exc:  # noqa: BLE001
            logging.info('Could not persist raw late-fill image result: %s', exc)
            return infer_result
        if not saved_image_path:
            return infer_result
        updated = dict(infer_result)
        updated['saved_image_path'] = saved_image_path
        updated.setdefault('image_data_url', data_url)
        updated['image_artifact_persisted_from_raw_late_fill'] = True
        return updated

    def branch_has_downstream_capability(
        self,
        branch: Mapping[str, Any],
        *,
        current_payload: Mapping[str, Any],
        downstream_capability: str,
    ) -> bool:
        runtime = current_payload.get('runtime') if isinstance(current_payload.get('runtime'), Mapping) else {}
        phase_graph = (
            runtime.get('request_phase_graph')
            if isinstance(runtime.get('request_phase_graph'), Mapping)
            else {}
        )
        phases = phase_graph.get('phases') if isinstance(phase_graph.get('phases'), list) else []
        source_tokens = {
            str(branch.get('branch_id') or '').strip(),
            str(branch.get('phase_id') or '').strip(),
        }
        source_tokens.discard('')
        if not source_tokens:
            return False
        for phase in phases:
            if not isinstance(phase, Mapping):
                continue
            if self.normalize_capability(phase.get('capability')) != downstream_capability:
                continue
            depends_on = {
                str(item or '').strip()
                for item in (phase.get('depends_on') or [])
                if str(item or '').strip()
            }
            if depends_on.intersection(source_tokens):
                return True
        return False

    def merge_late_fill_result_into_response_payload(
        self,
        response_payload: dict[str, Any],
        infer_result: dict[str, Any],
        late_fill_state: dict[str, Any],
    ) -> dict[str, Any]:
        current_state = response_payload.get('late_fill')
        current_state = current_state if isinstance(current_state, Mapping) else {}
        current_execution = current_state.get('successor_reopen_execution')
        current_execution = current_execution if isinstance(current_execution, Mapping) else {}
        if (
            isinstance(current_execution, Mapping)
            and current_execution.get('successor_execution_key')
            and str(current_execution.get('status') or '').strip().lower()
            in {'completed', 'failed', 'cancelled', 'blocked'}
        ):
            attached = self.attach_late_fill_state(response_payload, late_fill_state)
            attached_execution = attached.get('late_fill', {}).get('successor_reopen_execution') or {}
            if attached_execution.get('successor_execution_key') == current_execution['successor_execution_key']:
                # The same terminal execution has already accepted its result.
                # Do not project replacement infer fields/artifacts before the
                # envelope owner rejects that callback's replacement evidence.
                return attached
        updated = self.branch_dependency_evidence.merge_late_fill_result_fields(response_payload, infer_result)
        return self.attach_late_fill_state(updated, late_fill_state)

    def build_deferred_follow_up_gap_for_capability(
        self,
        artifact_gap: Optional[dict[str, Any]],
        *,
        capability: Optional[str],
        artifact_payload: Optional[dict[str, Any]] = None,
        pending_capabilities: Optional[list[str]] = None,
        completed_capabilities: Optional[list[str]] = None,
        failed_capabilities: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        normalized_capability = self.normalize_capability(capability)
        payload = dict(artifact_gap or {})
        payload['expected_capability'] = normalized_capability
        payload['active_capability'] = normalized_capability
        payload['missing_artifact_type'] = self.artifact_type_for_capability(normalized_capability)
        if pending_capabilities is not None:
            payload['pending_capabilities'] = self.normalize_capability_list(pending_capabilities)
        if completed_capabilities is not None:
            payload['completed_capabilities'] = self.normalize_capability_list(completed_capabilities)
        if failed_capabilities is not None:
            payload['failed_capabilities'] = self.normalize_capability_list(failed_capabilities)
        semantic_payload = self.semantic_payload_for_capability(
            artifact_payload,
            capability=normalized_capability,
        )
        for key, value in semantic_payload.items():
            if payload.get(key) in (None, '', [], {}):
                payload[key] = value
        return payload

    def prepare_late_fill_branch_plan(
        self,
        *,
        expected_capability: str,
        artifact_gap: dict[str, Any],
        current_payload: dict[str, Any],
        request_payload: dict[str, Any],
        assistant_message: str,
        source_route_payload: Optional[dict[str, Any]],
        failed_instance_id: Optional[str],
        excluded_instance_ids: Optional[list[str]] = None,
        guarded_pending: bool = False,
        build_deferred_follow_up_gap_for_capability: Optional[Callable[..., dict[str, Any]]] = None,
        prepare_late_fill_request_payload: Optional[Callable[..., dict[str, Any]]] = None,
        resolve_late_fill_route: Optional[Callable[..., tuple[dict[str, Any], Optional[dict[str, Any]], Optional[str]]]] = None,
    ) -> dict[str, Any]:
        build_gap = build_deferred_follow_up_gap_for_capability or self.build_deferred_follow_up_gap_for_capability
        prepare_payload = prepare_late_fill_request_payload or self.prepare_late_fill_request_payload
        resolve_route = resolve_late_fill_route or self.resolve_late_fill_route

        active_gap = build_gap(
            artifact_gap,
            capability=expected_capability,
            artifact_payload=current_payload,
        )
        if isinstance(active_gap.get('execution_contract'), Mapping) or active_gap.get('branch_id') or active_gap.get('phase_id'):
            active_gap = self.attach_execution_contract_to_gap(
                active_gap,
                active_gap,
                capability=expected_capability,
            )
        verified_review = (self._verified_pending_review_instruction(
            active_gap, current_payload, request_payload) if guarded_pending else None)
        late_fill_request_payload = prepare_payload(
            request_payload,
            expected_capability=expected_capability or '',
            assistant_message=assistant_message,
            artifact_gap=active_gap,
            **({"guarded_pending": True} if guarded_pending else {}),
            **({'_verified_review_instruction': verified_review} if verified_review else {}),
        )
        branch_contract_error = str(
            late_fill_request_payload.get('branch_contract_error') or ''
        ).strip()
        if (
            self.normalize_capability(expected_capability)
            == self.capability_image_generation
            and branch_contract_error == 'incomplete_image_prompt_batch'
            and late_fill_request_payload.get('materialization_blocked') is True
        ):
            raise RuntimeError(
                'Counted image prompt batch is incomplete; late-fill '
                'preparation failed closed without a fallback prompt carrier.'
            )
        if (
            (guarded_pending or str(active_gap.get('trigger') or '').strip().lower()
             in {'graph_patch_successor_reopen', 'graph_rebase_partial_successor'})
            and branch_contract_error
        ):
            raise RuntimeError(
                'Bounded successor execution requires a branch-local payload; '
                f'late-fill preparation failed closed ({branch_contract_error}).'
            )
        if branch_contract_error in {
            'selected_candidate_unavailable',
            'selected_candidate_not_distinct',
            'ambiguous_audio_variant_contract',
        }:
            raise RuntimeError(
                'Selected TTS candidate contract is invalid; '
                'late-fill preparation failed closed instead of reusing or duplicating another candidate.'
            )
        if branch_contract_error == 'selected_reference_audio_unavailable':
            raise RuntimeError(
                'Selected-reference STT contract is invalid; '
                'late-fill preparation failed closed instead of transcribing another audio source.'
            )
        if branch_contract_error in {
            'preserved_visual_reference_missing',
            'preserved_visual_reference_ambiguous',
            'preserved_visual_evidence_missing',
            'preserved_visual_evidence_ambiguous',
            'structured_audio_pair_lineage_ambiguous',
            'selected_reference_unavailable',
            'selected_reference_ambiguous',
            'selected_reference_evidence_unavailable',
            'text_revision_source_unavailable',
            'text_revision_source_exceeds_prompt_bound',
            'ambiguous_text_artifact_revision_source',
            'retained_input_alias_unavailable',
            'retained_input_alias_ambiguous',
        }:
            raise RuntimeError(
                'Preserved selected-reference or text-revision contract is invalid; '
                'late-fill preparation failed closed instead of regenerating or guessing source evidence.'
            )
        if separate_image_report_contract(active_gap):
            execution = active_gap.get('execution_contract') or {}
            evidence = assemble_separate_image_reports(execution, current_payload, self.resolve_saved_file_input_path)
            text = render_separate_image_reports(evidence)
            instance = {'target_kind': 'deterministic_local', 'instance_id': 'fruth-separate-image-reports',
                        'id': 'fruth-separate-image-reports', 'backend': 'fruth'}
            return {'response_id': current_payload.get('id'), 'capability': 'chat',
                'branch_id': active_gap.get('branch_id'), 'phase_id': active_gap.get('phase_id'),
                'execution_contract': dict(execution), 'effective_data': dict(late_fill_request_payload),
                'infer_payload': {'prompt': text}, 'instance': instance,
                'route_info': {'route_source': 'deterministic_separate_image_reports', 'capability': 'chat',
                               'instance_id': instance['instance_id'], 'instance': instance},
                'report_delivery_evidence': evidence, 'report_delivery_context': current_payload,
                'expose_input_artifacts': False}
        retained_alias_required = bool(
            str(
                active_gap.get('stage_direction')
                or late_fill_request_payload.get('stage_direction')
                or ''
            ).strip()
            == 'materialize_retained_input_alias'
            or active_gap.get('retained_input_alias_required') is True
            or late_fill_request_payload.get('retained_input_alias_required') is True
        )
        if retained_alias_required:
            effective_data = dict(late_fill_request_payload)
            retained_keys = (
                'stage_direction',
                'requires_artifact',
                'text_artifact_extension',
                'text_artifact_source_name',
                'text_artifact_source',
                'retained_input_alias_required',
                'retained_input_binding_state',
                'retained_input_source_path',
                'retained_input_source_name',
                'retained_input_target_name',
                'retained_input_candidate_count',
                'artifact_request',
            )
            for key in retained_keys:
                value = active_gap.get(key)
                if value not in (None, '', [], {}):
                    effective_data[key] = value
            execution_contract = (
                effective_data.get('execution_contract')
                if isinstance(effective_data.get('execution_contract'), Mapping)
                else active_gap.get('execution_contract')
                if isinstance(active_gap.get('execution_contract'), Mapping)
                else {}
            )
            if execution_contract:
                effective_data['execution_contract'] = dict(execution_contract)
            deterministic_instance = {
                'target_kind': 'deterministic_local',
                'instance_id': 'fruth-retained-input-alias',
                'id': 'fruth-retained-input-alias',
                'backend': 'fruth',
            }
            deterministic_route = {
                'route_source': 'deterministic_retained_input_alias',
                'capability': 'chat',
                'instance_id': 'fruth-retained-input-alias',
                'instance': dict(deterministic_instance),
            }
            return {
                'response_id': current_payload.get('id'),
                'capability': 'chat',
                'branch_id': str(
                    execution_contract.get('branch_id')
                    or effective_data.get('branch_id')
                    or active_gap.get('branch_id')
                    or ''
                ).strip()
                or None,
                'phase_id': str(
                    execution_contract.get('phase_id')
                    or effective_data.get('phase_id')
                    or active_gap.get('phase_id')
                    or ''
                ).strip()
                or None,
                'execution_contract': dict(execution_contract),
                'route_info': deterministic_route,
                'instance': deterministic_instance,
                'effective_data': effective_data,
                'infer_payload': {},
                'expose_input_artifacts': False,
            }
        late_fill_request_payload = branch_result_contracts.merge_late_fill_payload_artifacts(
            late_fill_request_payload,
            current_payload,
            source_route_payload,
            request_payload,
        )
        late_fill_request_payload, late_fill_route_info, route_error = resolve_route(
            late_fill_request_payload,
            expected_capability=expected_capability or '',
            failed_instance_id=failed_instance_id,
            excluded_instance_ids=excluded_instance_ids,
            artifact_gap=active_gap,
            source_route_payload=source_route_payload,
        )
        if route_error or not late_fill_route_info:
            exc = RuntimeError(route_error or 'Late fill route could not be resolved.')
            route_diagnostics = (
                late_fill_request_payload.get('_late_fill_route_diagnostics')
                if isinstance(late_fill_request_payload.get('_late_fill_route_diagnostics'), Mapping)
                else {}
            )
            if route_diagnostics:
                setattr(exc, 'route_diagnostics', dict(route_diagnostics))
            raise exc

        late_fill_instance = late_fill_route_info.get('instance') if isinstance(late_fill_route_info.get('instance'), dict) else {}
        late_fill_request_payload = _retarget_model_scoped_reasoning_effort(
            late_fill_request_payload,
            late_fill_instance,
            source_instance_id=str(
                request_payload.get('instance_id')
                or request_payload.get('instanceId')
                or ''
            ).strip(),
        )
        if str(
            late_fill_instance.get('target_kind') or ''
        ).strip().lower() == 'external':
            if (
                self.normalize_capability(expected_capability) != 'chat'
                or not callable(self.execute_external_chat_phase)
            ):
                raise RuntimeError(
                    'External late-fill execution is supported only for '
                    'graph-owned chat phases.'
                )
            execution_contract = (
                late_fill_request_payload.get('execution_contract')
                if isinstance(
                    late_fill_request_payload.get('execution_contract'),
                    Mapping,
                )
                else active_gap.get('execution_contract')
                if isinstance(active_gap.get('execution_contract'), Mapping)
                else {}
            )
            if not execution_contract or not str(
                execution_contract.get('branch_id')
                or execution_contract.get('phase_id')
                or ''
            ).strip():
                raise RuntimeError(
                    'External chat continuation requires a graph-owned branch '
                    'execution contract.'
                )
            bounded_task_prompt = self.extract_responses_prompt(
                late_fill_request_payload
            )
            if (
                str(active_gap.get('stage_direction') or '').strip()
                == 'materialize_requested_text_artifact'
            ):
                bounded_task_prompt = (
                    self._text_artifact_materialization_instruction(
                        '',
                        active_gap,
                    )
                    or bounded_task_prompt
                )
            root_prompt = self.extract_responses_prompt(request_payload)
            if not root_prompt:
                root_prompt = str(
                    late_fill_request_payload.get('_prompt_hint') or ''
                ).strip()
            if not bounded_task_prompt or not root_prompt:
                raise RuntimeError(
                    'External graph-owned chat continuation requires both '
                    'root reference context and a branch-local bounded task.'
                )
            root_scoped = bool(
                str(
                    execution_contract.get('execution_scope') or ''
                ).strip().lower()
                in {'root', 'root_scoped', 'whole_request', 'original_prompt'}
                or self.parse_bool(
                    execution_contract.get('root_scoped'),
                    default=False,
                )
                or self.parse_bool(
                    execution_contract.get('allow_root_prompt'),
                    default=False,
                )
            )
            if bounded_task_prompt.strip() == root_prompt.strip() and not root_scoped:
                raise RuntimeError(
                    'External graph-owned chat continuation refused to replay '
                    'the root request as branch-local execution.'
                )
            context_messages = [
                dict(item)
                for item in (
                    late_fill_request_payload.get('inference_messages') or []
                )
                if isinstance(item, Mapping)
            ]
            effective_data = dict(late_fill_request_payload)
            effective_data['execution_contract'] = dict(execution_contract)
            infer_payload = {
                'prompt': bounded_task_prompt,
                'execution_contract': dict(execution_contract),
            }
            return {
                'response_id': current_payload.get('id'),
                'capability': 'chat',
                'branch_id': str(
                    execution_contract.get('branch_id')
                    or effective_data.get('branch_id')
                    or ''
                ).strip()
                or None,
                'phase_id': str(
                    execution_contract.get('phase_id')
                    or effective_data.get('phase_id')
                    or ''
                ).strip()
                or None,
                'execution_contract': dict(execution_contract),
                'route_info': late_fill_route_info,
                'instance': late_fill_instance,
                'effective_data': effective_data,
                'infer_payload': infer_payload,
                'external_chat_phase': {
                    'root_prompt': root_prompt,
                    'context_messages': context_messages,
                    'bounded_task_prompt': bounded_task_prompt,
                },
                'expose_input_artifacts': False,
            }
        effective_data, late_fill_route_info, _planner_meta, _control_hints = self.prepare_effective_request_data(
            late_fill_request_payload,
            route_info=late_fill_route_info,
            instance=late_fill_instance if isinstance(late_fill_instance, dict) else None,
        )
        missing_session_controls = self.build_missing_required_session_controls(
            late_fill_instance if isinstance(late_fill_instance, dict) else {},
            effective_data,
        )
        if missing_session_controls:
            raise RuntimeError(str(missing_session_controls[0].get('message') or 'Required session controls missing for late fill.'))

        late_fill_backend = self.normalize_backend(
            effective_data.get('backend')
            or (late_fill_instance or {}).get('backend')
        )
        late_fill_request_model = self.select_backend_request_model(
            late_fill_instance if isinstance(late_fill_instance, dict) else None,
            effective_data.get('request_model') or (late_fill_instance or {}).get('request_model'),
            effective_data.get('model') or (late_fill_instance or {}).get('model'),
        ) or str(effective_data.get('model') or (late_fill_instance or {}).get('model') or '').strip()
        infer_payload, late_fill_route_info, _has_file_context, late_fill_expose_input_artifacts = self.build_responses_infer_execution_payload(
            effective_data,
            route_info=late_fill_route_info,
            instance=late_fill_instance if isinstance(late_fill_instance, dict) else {},
            instance_id=str((late_fill_route_info or {}).get('instance_id') or '').strip(),
            backend=late_fill_backend,
            capability=str((late_fill_route_info or {}).get('capability') or '').strip(),
            request_model_override=late_fill_request_model,
            upload_present=False,
        )
        execution_contract = (
            infer_payload.get('execution_contract')
            if isinstance(infer_payload.get('execution_contract'), dict)
            else (
                effective_data.get('execution_contract')
                if isinstance(effective_data.get('execution_contract'), dict)
                else {}
            )
        )
        direct_audio_dependency = bind_direct_audio_dependency(current_payload, execution_contract)
        vision_binding = self._prepared_vision_dependency(
            execution_contract, current_payload, infer_payload,
            str(late_fill_instance.get('instance_id') or ''),
        ) if expected_capability == 'vision_analysis' else {}
        return {
            'response_id': current_payload.get('id'),
            'capability': expected_capability,
            'vision_recovery_attempt': copy.deepcopy(active_gap.get('recovery_attempt') or {})
            if expected_capability == 'vision_analysis' else {},
            'vision_dependency_binding': vision_binding,
            'direct_audio_dependency': direct_audio_dependency,
            'branch_id': str((execution_contract or {}).get('branch_id') or effective_data.get('branch_id') or '').strip() or None,
            'phase_id': str((execution_contract or {}).get('phase_id') or effective_data.get('phase_id') or '').strip() or None,
            'execution_contract': dict(execution_contract) if execution_contract else {},
            'saved_file_dependency_context': current_payload if saved_file_dependency_contract(execution_contract) else {},
            'route_info': late_fill_route_info,
            'instance': late_fill_instance,
            'effective_data': effective_data,
            'infer_payload': infer_payload,
            'expose_input_artifacts': late_fill_expose_input_artifacts,
        }

    def _materialize_external_chat_text_artifact_outputs(
        self,
        plan: Mapping[str, Any],
        infer_result: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist external file bodies through Fruth before coalesced expansion."""

        effective_data = (
            plan.get('effective_data')
            if isinstance(plan.get('effective_data'), Mapping)
            else {}
        )
        branch_wrapper = (
            plan.get('branch')
            if isinstance(plan.get('branch'), Mapping)
            else {}
        )
        branch = (
            branch_wrapper.get('branch')
            if isinstance(branch_wrapper.get('branch'), Mapping)
            else branch_wrapper
        )
        stage_direction = str(
            effective_data.get('stage_direction')
            or branch.get('stage_direction')
            or ''
        ).strip()
        if stage_direction != 'materialize_requested_text_artifact':
            return infer_result

        requests = [
            dict(item)
            for item in (effective_data.get('text_artifact_requests') or [])
            if isinstance(item, Mapping)
        ]
        if not requests:
            artifact_request = (
                effective_data.get('artifact_request')
                if isinstance(
                    effective_data.get('artifact_request'),
                    Mapping,
                )
                else branch.get('artifact_request')
                if isinstance(branch.get('artifact_request'), Mapping)
                else {}
            )
            if artifact_request:
                requests = [dict(artifact_request)]
        if not requests:
            return infer_result

        provider_result = dict(infer_result)
        normalized_requests: list[dict[str, Any]] = []
        for request in requests:
            normalized = dict(request)
            extension = str(
                normalized.get('extension')
                or effective_data.get('text_artifact_extension')
                or branch.get('text_artifact_extension')
                or ''
            ).strip().lower().lstrip('.')
            source_name = str(
                normalized.get('source_name')
                or effective_data.get('text_artifact_source_name')
                or branch.get('text_artifact_source_name')
                or ''
            ).strip()
            target_path = str(
                normalized.get('target_path')
                or effective_data.get('text_artifact_target_path')
                or branch.get('text_artifact_target_path')
                or ''
            ).strip()
            if extension:
                normalized['extension'] = extension
            if source_name:
                normalized['source_name'] = source_name
            if target_path:
                normalized['target_path'] = target_path
            normalized_requests.append(normalized)

        provider_text = branch_result_contracts.late_fill_text_from_result_payload(provider_result)
        extracted_payloads = extract_text_artifact_payloads(
            provider_text,
            normalized_requests,
        )
        if len(extracted_payloads) != len(normalized_requests):
            raise RuntimeError(
                'TEXT_ARTIFACT_OUTPUT_SET_INCOMPLETE: External chat did not '
                'return one distinct valid file body for every coalesced text '
                'artifact request.'
            )

        def request_identity(value: Mapping[str, Any]) -> tuple[str, str, str]:
            return (
                str(value.get('target_path') or '').strip(),
                str(value.get('source_name') or '').strip().lower(),
                str(value.get('extension') or '').strip().lower().lstrip('.'),
            )

        unassigned_payload_indexes = set(range(len(extracted_payloads)))
        payload_by_request_index: dict[int, dict[str, Any]] = {}
        for request_index, request in enumerate(normalized_requests):
            identity = request_identity(request)
            candidates = [
                payload_index
                for payload_index in sorted(unassigned_payload_indexes)
                if isinstance(
                    extracted_payloads[payload_index].get('artifact_request'),
                    Mapping,
                )
                and request_identity(
                    extracted_payloads[payload_index]['artifact_request']
                )
                == identity
            ]
            if not candidates and request_index in unassigned_payload_indexes:
                # The extractor walks ordinary fenced output in request order.
                # This fallback is only needed for legacy requests without a
                # stable source name or target-path identity.
                candidates = [request_index]
            if len(candidates) != 1:
                raise RuntimeError(
                    'TEXT_ARTIFACT_OUTPUT_BINDING_AMBIGUOUS: External chat '
                    'file bodies could not be bound one-to-one to the '
                    'coalesced artifact manifest.'
                )
            payload_index = candidates[0]
            unassigned_payload_indexes.remove(payload_index)
            payload_by_request_index[request_index] = dict(
                extracted_payloads[payload_index]
            )

        prepared_outputs: list[tuple[dict[str, Any], str, str, str, str]] = []
        for request_index, request in enumerate(normalized_requests):
            extension = str(
                request.get('extension')
                or effective_data.get('text_artifact_extension')
                or branch.get('text_artifact_extension')
                or ''
            ).strip().lower().lstrip('.')
            source_name = str(
                request.get('source_name')
                or effective_data.get('text_artifact_source_name')
                or branch.get('text_artifact_source_name')
                or ''
            ).strip()
            target_path = str(
                request.get('target_path')
                or effective_data.get('text_artifact_target_path')
                or branch.get('text_artifact_target_path')
                or ''
            ).strip()
            extracted_content = str(
                payload_by_request_index[request_index].get('content') or ''
            ).strip()
            canonical_content, content_error = (
                text_artifact_materialization._text_artifact_content_payload_error(
                    extracted_content,
                    extension=extension,
                    saved_path=target_path,
                )
            )
            if content_error:
                code = str(
                    content_error.get('code')
                    or 'TEXT_ARTIFACT_OUTPUT_INVALID'
                ).strip()
                raise RuntimeError(
                    f"{code}: {content_error.get('message') or 'External chat returned an invalid file body.'}"
                )
            if not canonical_content:
                raise RuntimeError(
                    'TEXT_ARTIFACT_OUTPUT_INVALID: External chat did not '
                    'return a complete file body matching the requested '
                    f'{source_name or "text artifact"}.{extension or "txt"} identity.'
                )
            prepared_outputs.append(
                (
                    dict(request),
                    extension,
                    source_name,
                    target_path,
                    canonical_content,
                )
            )

        late_fill_instance = (
            plan.get('instance')
            if isinstance(plan.get('instance'), Mapping)
            else {}
        )
        persistence_model_name = str(
            late_fill_instance.get('model')
            or late_fill_instance.get('instance_id')
            or late_fill_instance.get('id')
            or 'external-chat'
        ).strip()
        runtime_bundle_dir: Optional[Path] = None
        if any(not target_path for _, _, _, target_path, _ in prepared_outputs):
            response_identity = str(
                effective_data.get('response_id')
                or plan.get('response_id')
                or plan.get('branch_id')
                or ''
            ).strip()
            bundle_identity = '|'.join(
                [
                    response_identity,
                    ','.join(sorted(
                        f'{source_name}.{extension}'
                        for _, extension, source_name, _, _ in prepared_outputs
                    )),
                ]
            )
            bundle_suffix = hashlib.sha256(
                bundle_identity.encode('utf-8')
            ).hexdigest()[:12]
            runtime_bundle_dir = ARTIFACT_OUTPUTS_DOCUMENTS_DIR / (
                f'external_chat_bundle_{bundle_suffix}'
            )
        runtime_allocated_target_paths: dict[int, Path] = {}
        allocated_filename_owners: dict[str, str] = {}
        if runtime_bundle_dir is not None:
            for output_index, (
                _request,
                extension,
                source_name,
                target_path,
                _content,
            ) in enumerate(prepared_outputs):
                if target_path:
                    continue
                safe_source_name = re.sub(
                    r'[^A-Za-z0-9._-]+',
                    '_',
                    Path(
                        source_name or f'generated-{extension or "txt"}'
                    ).stem,
                ).strip('._') or 'generated-text'
                allocated_filename = (
                    f'{safe_source_name}.{extension or "txt"}'
                )
                collision_key = unicodedata.normalize(
                    'NFC',
                    allocated_filename,
                ).casefold()
                request_identity = f'{source_name}.{extension}'
                prior_owner = allocated_filename_owners.get(collision_key)
                if prior_owner is not None:
                    raise RuntimeError(
                        'TEXT_ARTIFACT_PATH_COLLISION: Distinct requested '
                        f'artifacts `{prior_owner}` and `{request_identity}` '
                        f'would both map to `{allocated_filename}`. No file '
                        'was written.'
                    )
                allocated_filename_owners[collision_key] = request_identity
                runtime_allocated_target_paths[output_index] = (
                    runtime_bundle_dir / allocated_filename
                )
        materialized_results: list[dict[str, Any]] = []
        saved_records: list[dict[str, Any]] = []
        for output_index, (
            request,
            extension,
            source_name,
            target_path,
            extracted_content,
        ) in enumerate(prepared_outputs):
            request_payload = {
                **dict(effective_data),
                'artifact_request': dict(request),
                'text_artifact_request': dict(request),
                'text_artifact_extension': extension,
                'text_artifact_source_name': source_name,
                'text_artifact_target_path': target_path,
            }
            request_branch = {
                **dict(branch),
                'requires_artifact': True,
                'stage_direction': 'materialize_requested_text_artifact',
                'artifact_request': dict(request),
                'text_artifact_request': dict(request),
                'text_artifact_extension': extension,
                'text_artifact_source_name': source_name,
                'text_artifact_target_path': target_path,
            }
            materialization_result = {
                **dict(provider_result),
                'content': extracted_content,
                'content_payload': extracted_content,
                'result_text': extracted_content,
                'output_text': extracted_content,
            }
            if target_path:
                materialized, materialization_error = (
                    text_artifact_materialization._materialize_required_text_artifact_target_path(
                        request_branch,
                        materialization_result,
                        request_payload,
                        extension=extension,
                        source_name=source_name,
                    )
                )
                if materialization_error:
                    code = str(
                        materialization_error.get('code')
                        or 'TEXT_ARTIFACT_NOT_PERSISTED'
                    ).strip()
                    raise RuntimeError(
                        f"{code}: {materialization_error.get('message') or 'External chat file body did not pass Fruth materialization checks.'}"
                    )
            else:
                if runtime_bundle_dir is None:
                    raise RuntimeError(
                        'TEXT_ARTIFACT_PATH_ALLOCATION_FAILED: Fruth did not '
                        'allocate a bundle directory for a new text artifact.'
                    )
                allocated_target_path = runtime_allocated_target_paths.get(
                    output_index
                )
                if allocated_target_path is None:
                    raise RuntimeError(
                        'TEXT_ARTIFACT_PATH_ALLOCATION_FAILED: Fruth did not '
                        'bind a unique target path to a new text artifact.'
                    )
                saved_path = persist_text_artifact_locally(
                    extracted_content,
                    model_name=persistence_model_name,
                    source_name=source_name or f'generated-{extension or "txt"}',
                    mode='external_chat_text_artifact',
                    extension=extension or 'txt',
                    output_dir=ARTIFACT_OUTPUTS_DOCUMENTS_DIR,
                    target_path=str(allocated_target_path),
                )
                if not saved_path or not Path(saved_path).is_file():
                    raise RuntimeError(
                        'TEXT_ARTIFACT_NOT_PERSISTED: Fruth could not allocate '
                        'and save the external chat file body.'
                    )
                saved_error = text_artifact_materialization._text_artifact_saved_payload_error(
                    saved_path,
                    extension=extension,
                )
                if saved_error:
                    code = str(
                        saved_error.get('code')
                        or 'TEXT_ARTIFACT_NOT_PERSISTED'
                    ).strip()
                    raise RuntimeError(
                        f"{code}: {saved_error.get('message') or 'The Fruth-persisted file body did not pass saved-truth checks.'}"
                    )
                saved_artifact_request = text_artifact_materialization._required_text_artifact_request(
                    request_branch,
                    materialization_result,
                    request_payload,
                    extension=extension,
                    source_name=source_name,
                    target_path=saved_path,
                )
                materialized = text_artifact_materialization._with_required_text_artifact_saved_result(
                    materialization_result,
                    target_path=saved_path,
                    content=extracted_content,
                    extension=extension,
                    source_name=source_name,
                    artifact_request=saved_artifact_request,
                    evidence='external_chat_runtime_persisted_text_artifact',
                )
            materialized_results.append(materialized)
            for record in materialized.get('saved_text_artifacts') or []:
                if not isinstance(record, Mapping):
                    continue
                path = str(
                    record.get('path') or record.get('saved_text_path') or ''
                ).strip()
                if path and not any(
                    str(
                        item.get('path') or item.get('saved_text_path') or ''
                    ).strip()
                    == path
                    for item in saved_records
                ):
                    saved_records.append(dict(record))

        if len(materialized_results) == 1:
            updated = dict(materialized_results[0])
            if isinstance(provider_result.get('output_text'), str):
                updated['output_text'] = provider_result['output_text']
            return updated
        updated = dict(provider_result)
        updated['saved_text_artifacts'] = saved_records
        if saved_records:
            first = saved_records[0]
            updated['saved_text_path'] = str(
                first.get('path') or first.get('saved_text_path') or ''
            ).strip()
        return updated

    @observe_prepared_branch
    def execute_prepared_late_fill_branch(self, plan: dict[str, Any]) -> dict[str, Any]:
        self._validate_vision_retry_input(plan)
        infer_payload = plan.get('infer_payload') if isinstance(plan.get('infer_payload'), dict) else {}
        saved_execution = copy.deepcopy(plan.get('execution_contract') or {})
        content_review_binding = BranchDependencyEvidence._content_review_binding(saved_execution)
        if content_review_binding:
            submitted = str(infer_payload.get('prompt') or '')
            if hashlib.sha256(submitted.encode('utf-8')).hexdigest() != content_review_binding.get('instruction_sha256'):
                raise ValueError('content_review_prepared_packet_changed')
        saved_contract = saved_file_dependency_contract(saved_execution)
        saved_read = copy.deepcopy(saved_execution.get('saved_file_read_evidence') or {})
        syntax_repair = (saved_execution.get('artifact_request') or {}).get('saved_file_syntax_repair')
        if saved_contract:
            if (plan.get('instance') or {}).get('target_kind') == 'external':
                raise ValueError('saved_file_read_external_transport_unsupported')
            if (any(saved_execution.get(key) != saved_contract.get('consumer_' + key)
                    or plan.get(key) != saved_execution.get(key) for key in ('branch_id', 'phase_id'))
                    or saved_execution.get('depends_on') != [saved_contract.get('producer_phase_id')]):
                raise ValueError('saved_file_read_consumer_contract_mismatch')
            expected_ref = {'kind': 'saved_file_read', **{key: value for key, value in saved_read.items() if key != 'utf8_base64'}}
            if (saved_execution.get('input_refs') != [expected_ref]
                    or not plan.get('response_id') or plan['response_id'] != saved_read.get('response_id')):
                raise ValueError('saved_file_read_input_binding_mismatch')
            fresh = read_saved_file_snapshot(saved_read.get('path', ''), self.resolve_saved_file_input_path)
            if any(fresh.get(key) != saved_read.get(key) for key in ('path', 'utf8_base64', 'sha256', 'size_bytes')):
                raise ValueError('saved_file_read_version_changed_before_consumption')
            if any(saved_read.get(key) != saved_contract.get(key) for key in
                   ('producer_branch_id', 'producer_phase_id', 'consumer_branch_id', 'consumer_phase_id')):
                raise ValueError('saved_file_read_packet_misbound')
            if syntax_repair is not None:
                if (saved_execution.get('repair_scope') != 'syntax_only'
                        or saved_execution.get('dependency_policy') != 'target_artifact_snapshot_only'
                        or any((saved_execution.get(key) or {}).get('trigger') != _TARGET_BOUND_SAVED_TEXT_SYNTAX_REPAIR_TRIGGER
                               for key in ('recovery_attempt', 'recovery_state'))):
                    raise ValueError('saved_file_syntax_repair_authority_missing')
                issue = saved_file_syntax_repair_issue(saved_contract, syntax_repair)
                if issue:
                    raise ValueError(issue)
                issue = saved_file_read_issue(saved_contract, saved_read, plan.get('saved_file_dependency_context') or {})
                if issue:
                    raise ValueError(issue)
                target = syntax_repair['target']
                current_target = read_saved_file_snapshot(target['path'], self.resolve_saved_file_input_path)
                info = Path(target['path']).stat()
                identity = [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]
                if current_target != target or identity != syntax_repair['file_identity']:
                    raise ValueError('saved_file_syntax_repair_target_changed')
                issues = text_artifact_syntax_sanity_issues_for_extension(
                    syntax_repair['target_request']['extension'], saved_file_read_text(current_target))
                if issues != syntax_repair['syntax_sanity_issues']:
                    raise ValueError('saved_file_syntax_repair_defect_changed')
            # Feed the exact reverified packet. No root/history/selected file
            # context may replace or augment this explicitly bounded input.
            infer_payload = dict(infer_payload)
            for key in ('messages', 'context_messages', 'history', 'file_path', 'file_paths',
                        'selected_reference_artifacts', 'reference_artifacts', 'input_artifacts'):
                infer_payload.pop(key, None)
            expected_prompt = saved_file_consumer_prompt(saved_contract, saved_read, syntax_repair)
            submitted_input_sha256 = hashlib.sha256(expected_prompt.encode('utf-8')).hexdigest()
            if infer_payload.get('prompt') != expected_prompt:
                raise ValueError('saved_file_read_prepared_input_changed')
            requested_outputs = infer_payload.get('text_artifact_requests') or []
            authorized_output = syntax_repair['target_request'] if syntax_repair else saved_contract['consumer_request']
            if requested_outputs and (len(requested_outputs) != 1 or any(
                    requested_outputs[0].get(key) != authorized_output.get(key)
                    for key in ('extension', 'source_name', 'target_path'))):
                raise ValueError('saved_file_read_consumer_output_scope_changed')
            infer_payload['_prompt_hint'] = saved_contract['consumer_instruction']
            if syntax_repair and any((saved_execution.get('artifact_request') or {}).get(key) != authorized_output.get(key)
                                     for key in ('extension', 'source_name', 'target_path')):
                raise ValueError('saved_file_read_consumer_output_scope_changed')
            infer_payload['text_artifact_requests'] = [dict(authorized_output)]
            infer_payload['artifact_request'] = dict(saved_execution['artifact_request'])
            infer_payload['suppress_reference_file_context'] = True
            infer_payload['content_payload'] = saved_file_read_text(saved_read)
            infer_payload['content_payload_source'] = 'saved_file_read'
            infer_payload['input_refs'] = [{'kind': 'saved_file_read', **{
                key: value for key, value in saved_read.items() if key != 'utf8_base64'}}]
        semantic_review_execution = self._is_semantic_review_branch(
            plan,
            infer_payload,
            plan.get('effective_data')
            if isinstance(plan.get('effective_data'), Mapping)
            else {},
        )
        late_fill_instance = (
            plan.get('instance')
            if isinstance(plan.get('instance'), Mapping)
            else {}
        )
        external_chat_phase = (
            plan.get('external_chat_phase')
            if isinstance(plan.get('external_chat_phase'), Mapping)
            else {}
        )
        if self.normalize_capability(plan.get('capability')) == self.capability_text_to_speech:
            effective_data = (
                plan.get('effective_data')
                if isinstance(plan.get('effective_data'), Mapping)
                else {}
            )
            for candidate in (
                infer_payload.get('prompt'),
                effective_data.get('content_payload'),
            ):
                if control_json_envelope_suspected(str(candidate or '').strip()):
                    raise RuntimeError(
                        'control_envelope_not_speakable: repair_branch_contract is required '
                        'before text-to-speech execution'
                    )
        route_info = (
            dict(plan.get('route_info'))
            if isinstance(plan.get('route_info'), Mapping)
            else {}
        )
        retained_alias_contract = self._retained_input_alias_contract_from_plan(plan)
        if separate_image_report_contract(saved_execution):
            evidence = assemble_separate_image_reports(saved_execution, plan.get('report_delivery_context') or {},
                                                       self.resolve_saved_file_input_path)
            text = render_separate_image_reports(evidence)
            if (any(plan.get(key) != saved_execution.get(key) for key in ('branch_id', 'phase_id'))
                    or evidence != plan.get('report_delivery_evidence') or infer_payload.get('prompt') != text):
                raise ValueError('separate_image_reports_prepared_input_changed')
            infer_result = {'content': text, 'output_text': text, 'result_text': text,
                            'report_delivery_evidence': evidence, 'execution_contract': saved_execution}
        elif retained_alias_contract:
            infer_result = self.text_artifact_files._materialize_retained_input_alias(
                plan,
                retained_alias_contract,
            )
            route_info = {
                **route_info,
                'route_source': 'deterministic_retained_input_alias',
                'capability': 'chat',
                'instance_id': 'fruth-retained-input-alias',
            }
        elif str(
            late_fill_instance.get('target_kind') or ''
        ).strip().lower() == 'external':
            if (
                self.normalize_capability(plan.get('capability')) != 'chat'
                or not external_chat_phase
                or not callable(self.execute_external_chat_phase)
            ):
                raise RuntimeError(
                    'Invalid external late-fill plan: only a bounded '
                    'graph-owned chat phase may use an external target.'
                )
            external_result = self.execute_external_chat_phase(
                request_payload=(
                    plan.get('effective_data')
                    if isinstance(plan.get('effective_data'), dict)
                    else {}
                ),
                target=dict(late_fill_instance),
                root_prompt=str(
                    external_chat_phase.get('root_prompt') or ''
                ).strip(),
                context_messages=[
                    dict(item)
                    for item in (
                        external_chat_phase.get('context_messages') or []
                    )
                    if isinstance(item, Mapping)
                ],
                bounded_task_prompt=str(
                    external_chat_phase.get('bounded_task_prompt') or ''
                ).strip(),
            )
            external_status = str(
                external_result.get('status') or ''
            ).strip().lower()
            external_execution = (
                external_result.get('external_execution')
                if isinstance(
                    external_result.get('external_execution'),
                    Mapping,
                )
                else {}
            )
            if external_execution:
                route_runtime = (
                    dict(route_info.get('route_runtime') or {})
                    if isinstance(route_info.get('route_runtime'), Mapping)
                    else {}
                )
                route_runtime['external_execution'] = dict(
                    external_execution
                )
                route_info['route_runtime'] = route_runtime
            if external_status == 'failed':
                error = (
                    external_result.get('error')
                    if isinstance(external_result.get('error'), Mapping)
                    else {}
                )
                exc = RuntimeError(
                    str(
                        error.get('message')
                        or 'External graph-owned chat phase failed.'
                    )
                )
                status_code = error.get('status_code')
                if status_code is not None:
                    setattr(exc, 'status_code', status_code)
                raise exc
            if external_status == 'blocked':
                infer_result = {
                    'external_provider_block': {
                        'kind': 'fruth.external_provider_block',
                        'code': 'EXTERNAL_PROVIDER_BLOCKED',
                        'reason': str(
                            external_result.get('blocked_reason')
                            or 'The downstream provider blocked the bounded task.'
                        ).strip(),
                    },
                    'external_execution': dict(external_execution),
                }
            elif external_status == 'completed':
                output_text = str(
                    external_result.get('output_text') or ''
                )
                infer_result = {
                    'output_text': output_text,
                    'content': output_text,
                    'content_payload': output_text,
                    'result_text': output_text,
                    'mode': 'external_chat_phase',
                    'external_execution': dict(external_execution),
                }
                if not semantic_review_execution:
                    infer_result = self._materialize_external_chat_text_artifact_outputs(
                        plan,
                        infer_result,
                    )
            else:
                raise RuntimeError(
                    'External graph-owned chat phase returned no terminal status.'
                )
        else:
            internal_inputs = {}
            if plan.get('direct_audio_dependency') is not None:
                internal_inputs['direct_audio_dependency'] = plan['direct_audio_dependency']
            from fruth_core.pdf_preparation import PdfPreparationError, pdf_cancellation_scope

            def pdf_branch_cancelled():
                response_id = str(plan.get('response_id') or '').strip()
                if not response_id:
                    return False
                record = self.get_response_lookup_record(response_id) or {}
                current = record.get('response_payload')
                if not isinstance(current, Mapping):
                    return False
                decision = self.semantic_execution_gate_decision(plan, current)
                return decision.get('action') == 'skip'

            # Only the existing branch authority may interrupt PDF preparation.
            # Final post-execution relevance and compare-and-swap gates remain.
            with pdf_cancellation_scope(pdf_branch_cancelled):
                infer_result, status_code = self.invoke_internal_api_json_route(
                    payload=infer_payload,
                    upload=None,
                    **internal_inputs,
                )
            if status_code >= 400:
                preparation_error = PdfPreparationError.from_response(infer_result)
                if preparation_error is not None:
                    raise preparation_error
                exc = RuntimeError(str(infer_result.get('error') or 'Late fill request failed.'))
                exc.status_code = status_code
                raise exc
            infer_result = self.filter_responses_infer_result(
                infer_result,
                expose_input_artifacts=bool(plan.get('expose_input_artifacts')),
            )
            if self.normalize_capability(plan.get('capability')) == 'vision_analysis':
                receipt = infer_result.get('vision_input_evidence')
                if isinstance(receipt, Mapping) and receipt.get('authority') == 'runtime_vision_image_dispatch':
                    infer_result['vision_input_evidence'] = {
                        **receipt, **{key: plan.get(key) for key in ('response_id', 'branch_id', 'phase_id')},
                    }
                recovery = plan.get('vision_recovery_attempt') or {}
                prepared = plan.get('vision_dependency_binding') or {}
                if prepared and (not self._valid_vision_input_receipt(receipt)
                        or any(receipt.get(key) != prepared['artifact'].get(key)
                               for key in ('image_sha256', 'size_bytes'))
                        or receipt.get('instance_id') != late_fill_instance.get('instance_id')):
                    raise RuntimeError('Vision dependency did not preserve the exact image dispatch evidence.')
                if recovery.get('recovery_policy_id') == _VISION_EVIDENCE_RECOVERY_POLICY_ID:
                    prior = recovery['prior_vision_evidence_failure']['input_evidence']
                    if (not self._valid_vision_input_receipt(receipt)
                            or any(receipt.get(key) != prior.get(key) for key in ('image_sha256', 'size_bytes'))
                            or receipt.get('instance_id') != late_fill_instance.get('instance_id')):
                        raise RuntimeError('Vision recovery did not preserve the verified image handoff.')
        execution_contract = (
            plan.get('execution_contract')
            if isinstance(plan.get('execution_contract'), dict)
            else (
                infer_payload.get('execution_contract')
                if isinstance(infer_payload.get('execution_contract'), dict)
                else (
                    (plan.get('effective_data') or {}).get('execution_contract')
                    if isinstance(plan.get('effective_data'), dict)
                    and isinstance((plan.get('effective_data') or {}).get('execution_contract'), dict)
                    else {}
                )
            )
        )
        if isinstance(infer_result, dict) and execution_contract:
            infer_result = dict(infer_result)
            infer_result.setdefault('execution_contract', dict(execution_contract))
            workload_task_ref = (
                execution_contract.get('workload_task_ref')
                if isinstance(execution_contract.get('workload_task_ref'), Mapping)
                else {}
            )
            output_obligation_ref = (
                execution_contract.get('output_obligation_ref')
                if isinstance(execution_contract.get('output_obligation_ref'), Mapping)
                else {}
            )
            for key in ('branch_id', 'phase_id', 'capability', 'output_type'):
                value = execution_contract.get(key)
                if value not in (None, '', [], {}):
                    infer_result.setdefault(key, value)
            task_id = workload_task_ref.get('task_id') if isinstance(workload_task_ref, Mapping) else None
            if task_id not in (None, '', [], {}):
                infer_result.setdefault('task_id', task_id)
                infer_result.setdefault('workload_task_id', task_id)
                infer_result.setdefault('workload_task_ref', dict(workload_task_ref))
            obligation_id = (
                output_obligation_ref.get('obligation_id')
                if isinstance(output_obligation_ref, Mapping)
                else None
            )
            if obligation_id not in (None, '', [], {}):
                infer_result.setdefault('obligation_id', obligation_id)
                infer_result.setdefault('output_obligation_ref', dict(output_obligation_ref))
        saved_request = saved_execution.get('artifact_request') or {}
        if saved_contract or saved_request.get('saved_file_producer'):
            path = str(infer_result.get('saved_text_path') or '')
            if (not path or Path(path).suffix.lower() != '.' + saved_request.get('extension', '')
                    or (saved_request.get('target_path') and Path(path).resolve() != Path(saved_request['target_path']).resolve())):
                raise ValueError('saved_file_output_target_mismatch')
            saved_outputs = infer_result.get('saved_text_artifacts') or []
            if len(saved_outputs) > 1 or any(item.get('path') != path for item in saved_outputs):
                raise ValueError('saved_file_output_ambiguous')
            output_record = saved_outputs[0] if saved_outputs else {'path': path}
            if not TextArtifactResultEvidence._saved_text_artifact_matches_request(output_record, saved_request):
                raise ValueError('saved_file_output_request_mismatch')
            snapshot = read_saved_file_snapshot(path, self.resolve_saved_file_input_path)
            infer_result = dict(infer_result)
            infer_result['execution_contract'] = saved_execution
            infer_result['artifact_request'] = copy.deepcopy(saved_request)
            infer_result['saved_file_output_snapshot'] = {key: snapshot[key] for key in ('path', 'sha256', 'size_bytes')}
            if saved_contract:
                infer_result['saved_file_consumption_evidence'] = {
                    'status': 'consumed', 'contract': saved_contract, 'read': saved_read,
                    'input_sha256': submitted_input_sha256,
                    'output': dict(infer_result['saved_file_output_snapshot']),
                    **({'syntax_repair': copy.deepcopy(syntax_repair)} if syntax_repair else {}),
                }
        if (
            self._is_semantic_review_branch(
                plan,
                infer_payload,
                plan.get('effective_data')
                if isinstance(plan.get('effective_data'), Mapping)
                else {},
                execution_contract,
            )
            and isinstance(infer_result, dict)
        ):
            infer_result = self.project_internal_semantic_review_result(infer_result)
            if content_review_binding:
                infer_result['semantic_review_evidence_binding'] = content_review_binding
        if (
            isinstance(infer_result, dict)
            and self.normalize_capability(plan.get('capability'))
            == self.capability_text_to_speech
        ):
            semantic_source = TtsResultEvidence.tts_source_evidence_from_prepared_plan(
                plan,
                infer_result=infer_result,
            )
            if semantic_source:
                infer_result = dict(infer_result)
                infer_result['tts_semantic_source'] = semantic_source
            integrity_branch = {
                'capability': self.capability_text_to_speech,
                'branch_id': plan.get('branch_id'),
                'phase_id': plan.get('phase_id'),
            }
            if isinstance(execution_contract, Mapping):
                integrity_branch.update(dict(execution_contract))
            integrity_evidence = self.tts_result_evidence.tts_audio_integrity_evidence_for_branch_result(
                integrity_branch,
                infer_result,
            )
            if integrity_evidence:
                infer_result = dict(infer_result)
                infer_result['tts_audio_integrity_evidence'] = (
                    integrity_evidence
                )
        return {
            'capability': self.normalize_capability(plan.get('capability')),
            'branch_id': str(plan.get('branch_id') or (execution_contract or {}).get('branch_id') or '').strip() or None,
            'phase_id': str(plan.get('phase_id') or (execution_contract or {}).get('phase_id') or '').strip() or None,
            'execution_contract': dict(execution_contract) if execution_contract else {},
            'route_info': route_info,
            'instance': plan.get('instance') if isinstance(plan.get('instance'), dict) else {},
            'effective_data': plan.get('effective_data') if isinstance(plan.get('effective_data'), dict) else {},
            'infer_result': infer_result if isinstance(infer_result, dict) else {},
        }

    def execute_late_fill_branch(
        self,
        *,
        expected_capability: str,
        artifact_gap: dict[str, Any],
        current_payload: dict[str, Any],
        request_payload: dict[str, Any],
        assistant_message: str,
        source_route_payload: Optional[dict[str, Any]],
        failed_instance_id: Optional[str],
        excluded_instance_ids: Optional[list[str]] = None,
        prepare_late_fill_branch_plan: Optional[Callable[..., dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        prepare_plan = prepare_late_fill_branch_plan or self.prepare_late_fill_branch_plan
        plan = prepare_plan(
            expected_capability=expected_capability,
            artifact_gap=artifact_gap,
            current_payload=current_payload,
            request_payload=request_payload,
            assistant_message=assistant_message,
            source_route_payload=source_route_payload,
            failed_instance_id=failed_instance_id,
            excluded_instance_ids=excluded_instance_ids,
        )
        return self.execute_prepared_late_fill_branch(plan)

    def build_late_fill_materialization_branch_spec(
        self,
        *,
        branch: dict[str, Any],
        artifact_gap: dict[str, Any],
        current_payload: dict[str, Any],
        request_payload: dict[str, Any],
        assistant_message: str,
        source_route_payload: Optional[dict[str, Any]],
        failed_instance_id: Optional[str],
        guarded_pending: bool = False,
    ) -> Optional[dict[str, Any]]:
        capability = self.branch_capability(branch)
        branch_id = self.branch_id(branch)
        if not capability or not branch_id:
            return None
        branch_gap = dict(artifact_gap or {})
        successor_branch_execution = guarded_pending or (
            str(branch_gap.get('trigger') or branch.get('trigger') or '').strip().lower()
            in {'graph_patch_successor_reopen', 'graph_rebase_partial_successor'}
        )
        if successor_branch_execution:
            # A terminal repair successor may inherit the frozen parent's
            # Late Fill envelope, but none of its prompt carriers. Executable
            # prompt truth must be bound to the exact owed branch (or derived
            # from that branch's dependencies) rather than recovered from the
            # original request, assistant prose, or a prior global batch.
            for key in (
                'artifact_prompt',
                'artifact_prompt_source',
                'content_payload',
                'content_payload_source',
                'phase_summary',
                'stage_direction',
                'batch_prompts',
                'batch_prompts_source',
            ):
                branch_gap.pop(key, None)
        recovery_context = branch.get('recovery_context') if isinstance(branch.get('recovery_context'), Mapping) else {}
        attempt = branch.get('attempt') if isinstance(branch.get('attempt'), Mapping) else {}
        retry_excluded_instance_ids = [
            str(item).strip()
            for item in (
                branch.get('excluded_instance_ids')
                if isinstance(branch.get('excluded_instance_ids'), list)
                else recovery_context.get('exclude_instance_ids')
                if isinstance(recovery_context.get('exclude_instance_ids'), list)
                else []
            )
            if str(item).strip()
        ]
        branch_failed_instance_id = str(
            branch.get('failed_instance_id')
            or attempt.get('instance_id')
            or failed_instance_id
            or ''
        ).strip() or None
        if capability in {
            self.capability_text_to_speech,
            self.capability_image_generation,
            'vision_analysis',
        }:
            # A retry-wave envelope carries the anchor's recovery markers.
            # Branch markers remain authoritative so sibling retries do not
            # inherit the anchor identity or lose bounded recovery evidence.
            for key in ('recovery_state', 'recovery_attempt'):
                value = branch.get(key)
                if isinstance(value, Mapping) and value:
                    branch_gap[key] = dict(value)
        for key in (
            'artifact_prompt',
            'artifact_prompt_source',
            'content_payload',
            'content_payload_source',
            'selection_policy',
            'candidate_selection_index',
            'candidate_selection_count',
            'selection_reason',
            'audio_variant_index',
            'audio_variant_role',
            'audio_variant_contract_source',
            'structured_output_contract',
            'branch_contract_error',
            'audio_variant_contract_conflicting_fields',
            'phase_summary',
            'stage_direction',
            'batch_prompts',
            'batch_prompts_source',
            'batch_prompt_source_phase_id',
            'batch_prompt_expected_count',
            'batch_prompt_expected_count_invalid',
            'batch_prompt_actual_count',
            'counted_batch_prompt_carriers_blocked',
            'requires_artifact',
            'text_artifact_extension',
            'text_artifact_source_name',
            'text_artifact_source',
            'text_artifact_target_path',
            'text_artifact_revision_required',
            'text_artifact_revision_source',
            'text_artifact_source_is_input',
            'text_artifact_revision_binding_state',
            'text_artifact_revision_preservation_required',
            'text_artifact_revision_preservation_policy',
            'text_artifact_requests',
            'artifact_request',
            'retained_input_alias_required',
            'retained_input_binding_state',
            'retained_input_source_path',
            'retained_input_source_name',
            'retained_input_target_name',
            'retained_input_candidate_count',
            'lang_code',
            'voice',
            'instruct',
            'response_format',
            'output_format',
            'speed',
            'pitch',
            'repair_scope',
            'resource_class',
            'dependency_policy',
            'runtime_scheduling_context',
            'allow_gpu_heavy_concurrency',
            'repair_action',
            'recovery_action',
            'suggested_action',
            'repair_execution_policy',
            'execution_policy',
            'auto_execute',
            'repair_work_available',
            'needs_external_input',
            'materialization_blocked',
            'auto_executable_repair_retry_count',
            'auto_executable_repair_max_attempts',
            'repair_auto_execute_max_attempts',
            'max_auto_execute_attempts',
            'excluded_instance_ids',
            'excluded_reuse_policy_id',
            'automatic_follow_up_allowed',
        ):
            value = branch.get(key)
            if value not in (None, '', [], {}):
                branch_gap[key] = value
        revision_source_payload = TextArtifactFiles._text_artifact_revision_source_payload(
            branch,
            branch_gap,
        )
        if revision_source_payload:
            branch_gap.update(revision_source_payload)
        if (
            text_artifact_materialization._text_artifact_revision_required(branch, branch_gap)
            and self._text_artifact_revision_preservation_requested(
                BranchDependencyEvidence._request_payload_prompt_text(request_payload)
            )
        ):
            branch_gap['text_artifact_revision_preservation_required'] = True
            branch_gap['text_artifact_revision_preservation_policy'] = (
                'structural_anchor_retention_v1'
            )
        preserve_authoritative_text_repair_payload = (
            text_artifact_materialization._artifact_gap_is_authoritative_bounded_text_artifact_repair(branch_gap)
            and str(branch_gap.get('content_payload') or '').strip()
        )
        preserve_text_artifact_revision_source = bool(
            text_artifact_materialization._text_artifact_revision_required(branch, branch_gap)
            and str(branch_gap.get('content_payload') or '').strip()
            and str(branch_gap.get('content_payload_source') or '').strip()
            == 'canonical_predecessor_text_artifact_snapshot'
        )
        preserve_direct_spoken_payload = bool(
            str(branch_gap.get('content_payload') or '').strip()
            and str(branch_gap.get('content_payload_source') or '').strip()
            == 'current_turn_direct_spoken_clause'
        )
        dependency_payload = self.branch_dependency_evidence.branch_dependency_payload(
            branch,
            current_payload=current_payload,
        )
        for key, value in dependency_payload.items():
            if value not in (None, '', [], {}):
                if (
                    preserve_authoritative_text_repair_payload
                    and key in {'content_payload', 'content_payload_source'}
                ):
                    branch_gap['dependency_payload_policy'] = 'preserve_authoritative_text_repair_payload'
                    continue
                if (
                    preserve_text_artifact_revision_source
                    and key in {'content_payload', 'content_payload_source'}
                ):
                    branch_gap['dependency_payload_policy'] = (
                        'preserve_text_artifact_revision_source'
                    )
                    continue
                if (
                    preserve_direct_spoken_payload
                    and key in {'content_payload', 'content_payload_source'}
                ):
                    branch_gap['dependency_payload_policy'] = (
                        'preserve_current_turn_direct_media_payload'
                    )
                    continue
                branch_gap[key] = value
        branch_gap = self.focus_late_fill_branch_gap_payload(
            branch,
            branch_gap,
            capability=capability,
        )
        selected_reference_dependency_refs: list[Any] = []
        for source in (branch, branch_gap):
            selected_reference_dependency_refs.extend(source.get('input_refs') or [])
            execution_contract = (
                source.get('execution_contract')
                if isinstance(source.get('execution_contract'), Mapping)
                else {}
            )
            selected_reference_dependency_refs.extend(
                execution_contract.get('input_refs') or []
            )
        has_explicit_selected_reference_dependency = any(
            isinstance(item, Mapping)
            and str(item.get('kind') or '').strip().startswith('selected_reference')
            for item in selected_reference_dependency_refs
        )
        branch_local_image_prompt_sources = {
            'semantic_batch_prompt',
            'semantic_batch_prompts',
            'semantic_prepare_phase_output',
            'current_turn_direct_image_clause',
            'action_input',
            'prompt_blockquote_section',
            'quoted_prompt_section',
            'inline_prompt_capsule',
            'focused_image_prompt_slot',
            'focused_content_payload',
            'request_prompt_image_slots',
            'current_turn_explicit_image_manifest',
        }
        counted_image_prompt_authority_sources = (
            branch_local_image_prompt_sources
            - {'focused_image_prompt_slot', 'focused_content_payload'}
        )
        expected_image_prompt_count = (
            self._image_prompt_batch_expected_count(
                branch=branch,
                branch_gap=branch_gap,
                current_payload=current_payload,
            )
            if capability == self.capability_image_generation
            else 0
        )
        current_image_prompt_source = str(
            branch.get('artifact_prompt_source')
            or branch_gap.get('artifact_prompt_source')
            or ''
        ).strip()
        image_prompt_allows_batch_override = bool(
            capability == self.capability_image_generation
            and (
                self._image_branch_prompt_allows_batch_prompt_override(branch, branch_gap)
                or (
                    expected_image_prompt_count >= 2
                    and current_image_prompt_source
                    not in counted_image_prompt_authority_sources
                )
            )
        )
        if (
            capability == self.capability_image_generation
            and image_prompt_allows_batch_override
            and not successor_branch_execution
            and not isinstance(branch_gap.get('batch_prompts'), list)
        ):
            request_prompt_units = self._extract_late_fill_image_prompt_units(
                BranchDependencyEvidence._request_payload_prompt_text(request_payload)
            )
            if len(request_prompt_units) >= 2:
                branch_gap['batch_prompts'] = request_prompt_units
                branch_gap['batch_prompts_source'] = 'request_prompt_image_slots'
        if capability == self.capability_image_generation and image_prompt_allows_batch_override:
            expected_prompt_count = expected_image_prompt_count
            batch_prompts: list[str] = []
            if isinstance(branch_gap.get('batch_prompts'), list):
                batch_prompts = self._normalize_late_fill_image_batch_prompts(
                    branch_gap.get('batch_prompts'),
                    expected_count=expected_prompt_count,
                    assistant_message='' if successor_branch_execution else assistant_message,
                    content_payload=branch_gap.get('content_payload'),
                    request_payload={} if successor_branch_execution else request_payload,
                    artifact_prompt=branch_gap.get('artifact_prompt'),
                )
            if batch_prompts and batch_prompts != branch_gap.get('batch_prompts'):
                branch_gap['batch_prompts'] = batch_prompts
                branch_gap['batch_prompts_normalized'] = True
            non_empty_prompt_count = len(
                [item for item in batch_prompts if str(item or '').strip()]
            )
            if expected_prompt_count >= 2:
                branch_gap['batch_prompt_expected_count'] = expected_prompt_count
                branch_gap['batch_prompt_actual_count'] = non_empty_prompt_count
            exact_counted_batch = bool(
                expected_prompt_count < 2
                or (
                    len(batch_prompts) == expected_prompt_count
                    and non_empty_prompt_count == expected_prompt_count
                )
            )
            selection_index = self._branch_prompt_selection_index(
                branch,
                len(batch_prompts),
            )
            if exact_counted_batch and 1 <= selection_index <= len(batch_prompts):
                branch_gap['artifact_prompt'] = batch_prompts[selection_index - 1]
                branch_gap['artifact_prompt_source'] = (
                    str(branch_gap.get('batch_prompts_source') or '').strip()
                    or 'semantic_batch_prompt'
                )
                branch_gap['image_prompt_selection_index'] = selection_index
            elif expected_prompt_count >= 2 or batch_prompts:
                branch_gap.pop('artifact_prompt', None)
                branch_gap.pop('artifact_prompt_source', None)
                branch_gap['branch_contract_error'] = 'incomplete_image_prompt_batch'
                branch_gap['candidate_extraction_issue'] = (
                    'missing_exact_branch_local_image_prompt_batch'
                    if not exact_counted_batch
                    else 'missing_branch_local_image_prompt_slot'
                )
                branch_gap['materialization_blocked'] = True
                branch_gap['repair_action'] = RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT
        branch_local_image_prompt_source = str(
            branch_gap.get('artifact_prompt_source') or ''
        ).strip()
        if (
            capability == self.capability_image_generation
            and str(branch_gap.get('artifact_prompt') or '').strip()
            and branch_local_image_prompt_source in branch_local_image_prompt_sources
            and not has_explicit_selected_reference_dependency
        ):
            # Apply attachment policy only after the final branch prompt has
            # been selected. Explicit image-edit dependencies remain admitted.
            branch_gap['suppress_reference_file_context'] = True
            branch_gap['selected_reference_prompt_policy'] = (
                'suppressed_for_current_turn_branch_prompt'
                if branch_local_image_prompt_source
                in {
                    'current_turn_direct_image_clause',
                    'current_turn_explicit_image_manifest',
                }
                else 'suppressed_for_branch_local_image_prompt'
            )
        branch_gap = self.attach_execution_contract_to_gap(
            branch,
            branch_gap,
            capability=capability,
        )
        runtime_scheduling_context = self.runtime_scheduling_context_for_branch(
            branch,
            current_payload=current_payload,
            source_route_payload=source_route_payload,
            artifact_gap=branch_gap,
        )
        if runtime_scheduling_context:
            branch_gap['runtime_scheduling_context'] = runtime_scheduling_context
        if (
            capability == self.capability_image_generation
            and self.branch_has_downstream_capability(
                branch,
                current_payload=current_payload,
                downstream_capability='vision_analysis',
            )
        ):
            branch_gap['suppress_image_state_enrichment'] = True
            branch_gap.setdefault('image_state_enrichment_suppression_reason', 'downstream_vision_analysis')
        if (
            capability == self.capability_image_generation
            and not self.branch_selection._branch_allows_gpu_heavy_concurrency(branch, branch_gap)
            and self.response_has_required_artifact_closure_work(current_payload)
        ):
            branch_gap['suppress_image_state_enrichment'] = True
            branch_gap['suppress_generated_image_enrichment'] = True
            branch_gap.setdefault('image_state_enrichment_suppression_reason', 'required_artifact_closure_priority')
        return {
            'branch_id': branch_id,
            'phase_id': str(branch.get('phase_id') or branch_id).strip() or branch_id,
            'capability': capability,
            'reservation_group': capability,
            'branch': dict(branch),
            'prepare_args': {
                **({'guarded_pending': True} if guarded_pending else {}),
                'expected_capability': capability,
                'artifact_gap': branch_gap,
                'current_payload': dict(current_payload),
                'request_payload': dict(request_payload),
                'assistant_message': assistant_message,
                'source_route_payload': source_route_payload,
                'failed_instance_id': branch_failed_instance_id,
                'excluded_instance_ids': retry_excluded_instance_ids,
            },
        }

    def _prepare_terminal_graph_patch_successor_handoff(
        self,
        finalized_parent_payload: dict[str, Any],
        *,
        request_payload: dict[str, Any],
        assistant_message: str,
        artifact_gap: dict[str, Any],
        source_route_payload: Optional[dict[str, Any]],
    ) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
        """Persist a validated pending successor before its Late Fill worker starts."""

        if not callable(self.prepare_terminal_graph_patch_successor):
            return finalized_parent_payload, None
        try:
            prepared = self.prepare_terminal_graph_patch_successor(finalized_parent_payload)
        except Exception as exc:  # noqa: BLE001
            logging.warning('Could not prepare terminal graph-patch successor: %s', exc)
            return finalized_parent_payload, None
        if not isinstance(prepared, dict):
            return finalized_parent_payload, None
        if prepared.get('status') != 'queued':
            return self._persist_terminal_graph_patch_review_audit(
                finalized_parent_payload,
                prepared=prepared,
                request_payload=request_payload,
            )
        successor_payload = (
            prepared.get('response_payload')
            if isinstance(prepared.get('response_payload'), dict)
            else {}
        )
        successor_gap = (
            prepared.get('artifact_gap')
            if isinstance(prepared.get('artifact_gap'), dict)
            else {}
        )
        if not successor_payload or not successor_gap:
            return finalized_parent_payload, None
        execution = prepared.get('execution') if isinstance(prepared.get('execution'), dict) else {}
        successor_execution_key = str(execution.get('successor_execution_key') or '').strip()
        response_id = str(
            successor_payload.get('id')
            or successor_payload.get('response_id')
            or finalized_parent_payload.get('id')
            or finalized_parent_payload.get('response_id')
            or ''
        ).strip()
        durable_record = self.get_response_lookup_record(response_id) if response_id else None
        durable_payload = (
            durable_record.get('response_payload')
            if isinstance(durable_record, dict)
            and isinstance(durable_record.get('response_payload'), dict)
            else {}
        )
        if successor_execution_key and self._payload_has_graph_patch_successor_execution(
            durable_payload,
            successor_execution_key,
        ):
            self.log_unified_event(
                category='responses',
                action='graph_patch_successor_reopen',
                status='already_recorded',
                response_id=response_id,
                successor_execution_key=successor_execution_key,
                message='Skipped replay of an already persisted graph-patch successor.',
            )
            return dict(durable_payload), {
                'status': 'already_recorded',
                'skip_schedule': True,
                'successor_execution_key': successor_execution_key,
            }
        finalized_successor = self.finalize_response_frame_payload(
            successor_payload,
            request_payload=request_payload,
            persist=True,
        )
        response_id = str(
            finalized_successor.get('id')
            or finalized_successor.get('response_id')
            or ''
        ).strip()
        if not response_id:
            return finalized_parent_payload, None
        self.touch_response_lookup(
            response_id,
            status='completed',
            output_text=str(finalized_successor.get('output_text') or ''),
            response_payload=finalized_successor,
        )
        self.log_unified_event(
            category='responses',
            action='graph_patch_successor_reopen',
            status='queued',
            response_id=response_id,
            patch_id=execution.get('patch_id'),
            successor_execution_key=execution.get('successor_execution_key'),
            successor_reopen_depth=execution.get('successor_reopen_depth'),
            scheduled_branch_ids=execution.get('scheduled_branch_ids'),
            message='Queued bounded graph-patch successor through existing Late Fill.',
        )
        handoff = {
            'response_payload': finalized_successor,
            'request_payload': dict(request_payload or {}),
            'assistant_message': str(assistant_message or '').strip(),
            'artifact_gap': dict(successor_gap),
            'source_route_payload': (
                dict(source_route_payload)
                if isinstance(source_route_payload, dict)
                else None
            ),
        }
        return finalized_successor, handoff

    @staticmethod
    def _terminal_graph_patch_request_phase_graph(
        response_payload: Any,
    ) -> Optional[dict[str, Any]]:
        """Return a structurally valid graph, or ``None`` without coercion."""

        if not isinstance(response_payload, Mapping):
            return None
        runtime = response_payload.get('runtime')
        if not isinstance(runtime, Mapping):
            return None
        graph = runtime.get('request_phase_graph')
        if not isinstance(graph, Mapping):
            return None
        if 'graph_patch_lifecycle' in graph:
            lifecycle = graph.get('graph_patch_lifecycle')
            if not isinstance(lifecycle, list) or any(
                not isinstance(item, Mapping) for item in lifecycle
            ):
                return None
        return dict(graph)

    @staticmethod
    def _terminal_graph_patch_stable_json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=True, separators=(',', ':'), sort_keys=True)

    @staticmethod
    def _terminal_graph_patch_identifier(value: Any) -> str:
        if not isinstance(value, str) or not value or value != value.strip():
            return ''
        return value

    @classmethod
    def _terminal_graph_patch_response_identity(cls, response_payload: Any) -> str:
        if not isinstance(response_payload, Mapping):
            return ''
        outer_ids: list[str] = []
        for key in ('id', 'response_id'):
            if key not in response_payload:
                continue
            value = cls._terminal_graph_patch_identifier(response_payload.get(key))
            if not value:
                return ''
            outer_ids.append(value)
        if not outer_ids or any(value != outer_ids[0] for value in outer_ids[1:]):
            return ''
        frame = cls._terminal_graph_patch_frame(response_payload)
        frame_response_id = cls._terminal_graph_patch_identifier(
            frame.get('response_id')
        )
        if frame_response_id != outer_ids[0]:
            return ''
        return outer_ids[0]

    @staticmethod
    def _terminal_graph_patch_frame_sequence(value: Any) -> Optional[int]:
        return value if type(value) is int and value > 0 else None

    @classmethod
    def _terminal_graph_patch_clean_string_list(
        cls,
        value: Any,
    ) -> Optional[list[str]]:
        if not isinstance(value, list) or not value:
            return None
        cleaned: list[str] = []
        for item in value:
            text = cls._terminal_graph_patch_identifier(item)
            if not text:
                return None
            if text not in cleaned:
                cleaned.append(text)
        return sorted(cleaned)

    @classmethod
    def _terminal_graph_patch_policy_denial_record(
        cls,
        lifecycle: Any,
    ) -> dict[str, Any]:
        """Validate and sanitize one explicit apply_enforced policy denial."""

        if not isinstance(lifecycle, Mapping):
            return {}
        outcome = lifecycle.get('outcome')
        policy_review = lifecycle.get('enforced_policy_review')
        if not isinstance(outcome, Mapping) or not isinstance(policy_review, Mapping):
            return {}
        nested_policy = policy_review.get('policy')
        if not isinstance(nested_policy, Mapping):
            return {}

        status = lifecycle.get('status')
        if (
            status not in {'blocked', 'rejected'}
            or outcome.get('status') != status
            or policy_review.get('status') != status
        ):
            return {}
        if (
            lifecycle.get('kind') != 'fruth.graph_patch_lifecycle'
            or lifecycle.get('risk_level') != 'safe_additive'
            or lifecycle.get('autonomy_level') != 'apply_enforced'
            or lifecycle.get('authority') != 'runtime_enforced_policy_denied'
            or lifecycle.get('allowed_by_policy') is not False
            or lifecycle.get('enforced_policy_id') != ENFORCED_POLICY_DEFAULT_ID
            or lifecycle.get('policy_mode') != ENFORCED_POLICY_PRODUCT_DEFAULT_MODE
        ):
            return {}

        enforced_class = cls._terminal_graph_patch_identifier(
            lifecycle.get('enforced_class')
        )
        if enforced_class not in _GRAPH_PATCH_TERMINAL_SAFE_ENFORCED_CLASSES:
            return {}
        if (
            policy_review.get('kind') != ENFORCED_POLICY_REVIEW_KIND
            or policy_review.get('policy_id') != ENFORCED_POLICY_DEFAULT_ID
            or policy_review.get('policy_mode') != ENFORCED_POLICY_PRODUCT_DEFAULT_MODE
            or policy_review.get('mode') != ENFORCED_POLICY_PRODUCT_DEFAULT_MODE
            or policy_review.get('authority') != 'runtime_enforced_policy_denied'
            or policy_review.get('allowed') is not False
            or policy_review.get('enforced_class') != enforced_class
            or policy_review.get('selected_scope_allowed') is not False
        ):
            return {}
        if (
            nested_policy.get('policy_id') != ENFORCED_POLICY_DEFAULT_ID
            or nested_policy.get('mode') != ENFORCED_POLICY_PRODUCT_DEFAULT_MODE
            or nested_policy.get('normalized') != ENFORCED_POLICY_PRODUCT_DEFAULT_MODE
            or nested_policy.get('enabled') is not True
            or nested_policy.get('default_action') != 'deny'
        ):
            return {}

        identifiers: dict[str, str] = {}
        for key in (
            'patch_id',
            'proposal_id',
            'review_id',
            'idempotency_key',
            'repair_class',
        ):
            identifiers[key] = cls._terminal_graph_patch_identifier(
                lifecycle.get(key)
            )
            if not identifiers[key]:
                return {}
        policy_review_id = cls._terminal_graph_patch_identifier(
            policy_review.get('review_id')
        )
        selected_scope = cls._terminal_graph_patch_identifier(
            policy_review.get('selected_scope')
        )
        lifecycle_reasons = cls._terminal_graph_patch_clean_string_list(
            lifecycle.get('blocked_reasons')
        )
        policy_reasons = cls._terminal_graph_patch_clean_string_list(
            policy_review.get('blocked_reasons')
        )
        if (
            not policy_review_id
            or not selected_scope
            or not lifecycle_reasons
            or not policy_reasons
            or not set(policy_reasons).issubset(lifecycle_reasons)
        ):
            return {}

        return {
            'kind': 'fruth.graph_patch_lifecycle',
            **identifiers,
            'risk_level': 'safe_additive',
            'autonomy_level': 'apply_enforced',
            'status': status,
            'blocked_reasons': lifecycle_reasons,
            'authority': 'runtime_enforced_policy_denied',
            'enforced_class': enforced_class,
            'enforced_policy_id': ENFORCED_POLICY_DEFAULT_ID,
            'policy_mode': ENFORCED_POLICY_PRODUCT_DEFAULT_MODE,
            'allowed_by_policy': False,
            'audit_only': True,
            'enforced_policy_review': {
                'kind': ENFORCED_POLICY_REVIEW_KIND,
                'review_id': policy_review_id,
                'policy_id': ENFORCED_POLICY_DEFAULT_ID,
                'status': status,
                'allowed': False,
                'authority': 'runtime_enforced_policy_denied',
                'policy_mode': ENFORCED_POLICY_PRODUCT_DEFAULT_MODE,
                'mode': ENFORCED_POLICY_PRODUCT_DEFAULT_MODE,
                'enforced_class': enforced_class,
                'blocked_reasons': policy_reasons,
                'selected_scope': selected_scope,
                'selected_scope_allowed': False,
            },
            'outcome': {
                'status': status,
                'runtime_effect': _GRAPH_PATCH_TERMINAL_REVIEW_RUNTIME_EFFECT,
            },
        }

    @staticmethod
    def _terminal_graph_patch_frame(response_payload: Any) -> dict[str, Any]:
        if not isinstance(response_payload, Mapping) or not isinstance(response_payload.get('response_frame'), Mapping):
            return {}
        return dict(response_payload['response_frame'])

    @staticmethod
    def _terminal_graph_patch_review_relation(response_payload: Any) -> dict[str, Any]:
        response_frame = LateFillRuntimeOwner._terminal_graph_patch_frame(response_payload)
        if not isinstance(response_frame.get('frame_relation'), Mapping):
            return {}
        relation = response_frame['frame_relation']
        if str(relation.get('kind') or '').strip() != _GRAPH_PATCH_TERMINAL_REVIEW_RELATION:
            return {}
        return dict(relation)

    @classmethod
    def _terminal_graph_patch_audit_is_valid(
        cls,
        response_payload: Any,
        *,
        response_id: str,
        parent_frame_id: str,
        parent_frame_sequence: int,
        audit_key: str,
        denial_record: Mapping[str, Any],
        expected_graph: Mapping[str, Any],
    ) -> bool:
        """Validate the complete durable audit and its current lineage."""

        try:
            if cls._terminal_graph_patch_response_identity(response_payload) != response_id:
                return False
            frame = cls._terminal_graph_patch_frame(response_payload)
            frame_sequence = cls._terminal_graph_patch_frame_sequence(
                frame.get('frame_sequence')
            )
            frame_id = cls._terminal_graph_patch_identifier(frame.get('frame_id'))
            if (
                not frame_id
                or frame_id == parent_frame_id
                or frame_sequence != parent_frame_sequence + 1
            ):
                return False
            relation = cls._terminal_graph_patch_review_relation(response_payload)
            if not relation or not set(relation).issubset(
                _GRAPH_PATCH_TERMINAL_REVIEW_RELATION_KEYS
            ):
                return False
            expected_relation = {
                'kind': _GRAPH_PATCH_TERMINAL_REVIEW_RELATION,
                'reason': _GRAPH_PATCH_TERMINAL_REVIEW_REASON,
                'response_id': response_id,
                'parent_response_id': response_id,
                'parent_frame_id': parent_frame_id,
                'parent_frame_sequence': parent_frame_sequence,
                'audit_key': audit_key,
                'audit_only': True,
                'executable': False,
                'runtime_effect': _GRAPH_PATCH_TERMINAL_REVIEW_RUNTIME_EFFECT,
                'owed_work': 'none',
                'patch_id': denial_record.get('patch_id'),
                'proposal_id': denial_record.get('proposal_id'),
                'review_id': denial_record.get('review_id'),
                'policy_review_id': (
                    denial_record.get('enforced_policy_review', {}).get('review_id')
                    if isinstance(denial_record.get('enforced_policy_review'), Mapping)
                    else None
                ),
            }
            if any(relation.get(key) != value for key, value in expected_relation.items()):
                return False
            if 'scheduled_branch_ids' in relation and relation.get('scheduled_branch_ids') != []:
                return False
            graph = cls._terminal_graph_patch_request_phase_graph(response_payload)
            if graph is None or dict(graph) != dict(expected_graph):
                return False
            lifecycle = graph.get('graph_patch_lifecycle') or []
            matches = [
                item
                for item in lifecycle
                if isinstance(item, Mapping)
                and item.get('patch_id') == denial_record.get('patch_id')
            ]
            return len(matches) == 1 and dict(matches[0]) == dict(denial_record)
        except Exception:  # noqa: BLE001 - malformed durable state fails closed
            return False

    def _load_durable_terminal_graph_patch_payload(self, response_id: str) -> dict[str, Any]:
        if not response_id or not callable(self.load_latest_response_state):
            return {}
        try:
            durable_state = self.load_latest_response_state(response_id)
        except Exception as exc:  # noqa: BLE001
            logging.warning(
                'Could not load durable terminal graph-patch audit parent: %s',
                exc,
            )
            return {}
        if not isinstance(durable_state, Mapping) or durable_state.get('ok') is not True or durable_state.get('errors'):
            return {}
        durable_payload = durable_state.get('response_payload')
        return dict(durable_payload) if isinstance(durable_payload, Mapping) else {}

    def _persist_terminal_graph_patch_review_audit(
        self,
        finalized_parent_payload: dict[str, Any],
        *,
        prepared: Mapping[str, Any],
        request_payload: dict[str, Any],
    ) -> tuple[dict[str, Any], None]:
        """Append denied terminal patch policy truth without creating executable work."""

        if (
            prepared.get('status') != 'not_applicable'
            or prepared.get('reason') != 'no_safe_terminal_graph_patch_successor'
        ):
            return finalized_parent_payload, None
        reviewed_payload = (
            prepared.get('response_payload')
            if isinstance(prepared.get('response_payload'), Mapping)
            else None
        )
        if reviewed_payload is None:
            return finalized_parent_payload, None

        parent_graph = self._terminal_graph_patch_request_phase_graph(finalized_parent_payload)
        reviewed_graph = self._terminal_graph_patch_request_phase_graph(reviewed_payload)
        if parent_graph is None or reviewed_graph is None:
            return finalized_parent_payload, None

        parent_frame = self._terminal_graph_patch_frame(finalized_parent_payload)
        reviewed_frame = self._terminal_graph_patch_frame(reviewed_payload)
        response_id = self._terminal_graph_patch_response_identity(
            finalized_parent_payload
        )
        reviewed_response_id = self._terminal_graph_patch_response_identity(
            reviewed_payload
        )
        parent_frame_id = self._terminal_graph_patch_identifier(
            parent_frame.get('frame_id')
        )
        reviewed_frame_id = self._terminal_graph_patch_identifier(
            reviewed_frame.get('frame_id')
        )
        parent_frame_sequence = self._terminal_graph_patch_frame_sequence(
            parent_frame.get('frame_sequence')
        )
        reviewed_frame_sequence = self._terminal_graph_patch_frame_sequence(
            reviewed_frame.get('frame_sequence')
        )
        if (
            not response_id
            or reviewed_response_id != response_id
            or not parent_frame_id
            or parent_frame_sequence is None
            or reviewed_frame_id != parent_frame_id
            or reviewed_frame_sequence != parent_frame_sequence
        ):
            return finalized_parent_payload, None

        reviewed_denials = [
            denial
            for lifecycle in reviewed_graph.get('graph_patch_lifecycle') or []
            if (
                denial := self._terminal_graph_patch_policy_denial_record(
                    lifecycle
                )
            )
        ]
        if len(reviewed_denials) != 1:
            return finalized_parent_payload, None
        denial_record = reviewed_denials[0]
        parent_lifecycles = [
            copy.deepcopy(dict(item))
            for item in parent_graph.get('graph_patch_lifecycle') or []
        ]
        parent_patch_collisions = [
            item
            for item in parent_lifecycles
            if item.get('patch_id') == denial_record.get('patch_id')
        ]
        if parent_patch_collisions:
            return finalized_parent_payload, None

        audit_graph = copy.deepcopy(parent_graph)
        audit_graph['graph_patch_lifecycle'] = [
            *parent_lifecycles,
            copy.deepcopy(denial_record),
        ]
        audit_digest = hashlib.sha256(
            self._terminal_graph_patch_stable_json(
                {
                    'response_id': response_id,
                    'parent_frame_id': parent_frame_id,
                    'parent_frame_sequence': parent_frame_sequence,
                    'policy_denial': denial_record,
                }
            ).encode('utf-8')
        ).hexdigest()
        audit_key = f'graph-patch-terminal-review-{audit_digest[:24]}'
        audit_payload = copy.deepcopy(finalized_parent_payload)
        audit_runtime = copy.deepcopy(audit_payload.get('runtime'))
        if not isinstance(audit_runtime, dict):
            return finalized_parent_payload, None
        audit_runtime['request_phase_graph'] = audit_graph
        audit_payload['runtime'] = audit_runtime
        audit_payload['frame_relation'] = {
            'kind': _GRAPH_PATCH_TERMINAL_REVIEW_RELATION,
            'reason': _GRAPH_PATCH_TERMINAL_REVIEW_REASON,
            'response_id': response_id,
            'parent_response_id': response_id,
            'parent_frame_id': parent_frame_id,
            'parent_frame_sequence': parent_frame_sequence,
            'audit_key': audit_key,
            'audit_only': True,
            'executable': False,
            'runtime_effect': _GRAPH_PATCH_TERMINAL_REVIEW_RUNTIME_EFFECT,
            'owed_work': 'none',
            'scheduled_branch_ids': [],
            'patch_id': denial_record['patch_id'],
            'proposal_id': denial_record['proposal_id'],
            'review_id': denial_record['review_id'],
            'policy_review_id': denial_record['enforced_policy_review']['review_id'],
        }

        with _GRAPH_PATCH_TERMINAL_REVIEW_HANDOFF_LOCK:
            durable_payload = self._load_durable_terminal_graph_patch_payload(response_id)
            if not durable_payload:
                return finalized_parent_payload, None
            if self._terminal_graph_patch_audit_is_valid(
                durable_payload,
                response_id=response_id,
                parent_frame_id=parent_frame_id,
                parent_frame_sequence=parent_frame_sequence,
                audit_key=audit_key,
                denial_record=denial_record,
                expected_graph=audit_graph,
            ):
                return durable_payload, None
            durable_frame = self._terminal_graph_patch_frame(durable_payload)
            if (
                self._terminal_graph_patch_response_identity(durable_payload)
                != response_id
                or self._terminal_graph_patch_identifier(
                    durable_frame.get('frame_id')
                ) != parent_frame_id
                or self._terminal_graph_patch_frame_sequence(
                    durable_frame.get('frame_sequence')
                ) != parent_frame_sequence
                or self._terminal_graph_patch_request_phase_graph(durable_payload)
                != parent_graph
            ):
                return finalized_parent_payload, None
            try:
                finalized_audit = self.finalize_response_frame_payload(
                    audit_payload,
                    request_payload=request_payload,
                    persist=True,
                    expected_parent_frame_id=parent_frame_id,
                    expected_parent_frame_sequence=parent_frame_sequence,
                )
            except ResponseFrameParentCASMismatch:
                durable_payload = self._load_durable_terminal_graph_patch_payload(response_id)
                if self._terminal_graph_patch_audit_is_valid(
                    durable_payload,
                    response_id=response_id,
                    parent_frame_id=parent_frame_id,
                    parent_frame_sequence=parent_frame_sequence,
                    audit_key=audit_key,
                    denial_record=denial_record,
                    expected_graph=audit_graph,
                ):
                    return durable_payload, None
                return finalized_parent_payload, None
            except ResponsePersistenceError:
                raise
            except Exception as exc:  # noqa: BLE001
                logging.warning(
                    'Could not persist terminal graph-patch review audit: %s',
                    exc,
                )
                return finalized_parent_payload, None

            durable_audit = self._load_durable_terminal_graph_patch_payload(response_id)
            if not self._terminal_graph_patch_audit_is_valid(
                durable_audit,
                response_id=response_id,
                parent_frame_id=parent_frame_id,
                parent_frame_sequence=parent_frame_sequence,
                audit_key=audit_key,
                denial_record=denial_record,
                expected_graph=audit_graph,
            ):
                return finalized_parent_payload, None
            finalized_frame_id = self._terminal_graph_patch_identifier(
                self._terminal_graph_patch_frame(finalized_audit).get('frame_id')
            )
            durable_frame_id = self._terminal_graph_patch_identifier(
                self._terminal_graph_patch_frame(durable_audit).get('frame_id')
            )
            if not finalized_frame_id or durable_frame_id != finalized_frame_id:
                return finalized_parent_payload, None
            finalized_audit = durable_audit
            durable_relation = self._terminal_graph_patch_review_relation(
                finalized_audit
            )

            self.touch_response_lookup(
                response_id,
                status='completed',
                output_text=str(finalized_audit.get('output_text') or ''),
                response_payload=finalized_audit,
            )
            self.log_unified_event(
                category='responses',
                action='graph_patch_terminal_review',
                status='recorded',
                response_id=response_id,
                audit_key=audit_key,
                parent_frame_id=parent_frame_id,
                parent_frame_sequence=parent_frame_sequence,
                patch_id=durable_relation.get('patch_id'),
                proposal_id=durable_relation.get('proposal_id'),
                runtime_effect=_GRAPH_PATCH_TERMINAL_REVIEW_RUNTIME_EFFECT,
                message=(
                    'Recorded blocked terminal graph-patch policy truth without '
                    'creating executable work.'
                ),
            )
            return finalized_audit, None

    @staticmethod
    def _payload_has_graph_patch_successor_execution(
        response_payload: Any,
        successor_execution_key: str,
    ) -> bool:
        """Read durable response truth without treating an inert candidate as consumed."""

        if not isinstance(response_payload, Mapping) or not successor_execution_key:
            return False
        late_fill = (
            response_payload.get('late_fill')
            if isinstance(response_payload.get('late_fill'), Mapping)
            else {}
        )
        execution = (
            late_fill.get('successor_reopen_execution')
            if isinstance(late_fill.get('successor_reopen_execution'), Mapping)
            else {}
        )
        if str(execution.get('successor_execution_key') or '').strip() == successor_execution_key:
            return True
        runtime = (
            response_payload.get('runtime')
            if isinstance(response_payload.get('runtime'), Mapping)
            else {}
        )
        graph = (
            runtime.get('request_phase_graph')
            if isinstance(runtime.get('request_phase_graph'), Mapping)
            else {}
        )
        for record in graph.get('successor_reopen_executions') or []:
            if (
                isinstance(record, Mapping)
                and str(record.get('successor_execution_key') or '').strip()
                == successor_execution_key
            ):
                return True
        for record in graph.get('successor_reopen_requests') or []:
            if not isinstance(record, Mapping):
                continue
            record_execution = (
                record.get('execution')
                if isinstance(record.get('execution'), Mapping)
                else {}
            )
            if str(record_execution.get('successor_execution_key') or '').strip() == successor_execution_key:
                return True
            if (
                str(record.get('status') or '').strip().lower() == 'applied_to_successor'
                and str(record.get('successor_execution_key') or '').strip()
                == successor_execution_key
            ):
                return True
        return False

    @staticmethod
    def _payload_has_partial_graph_rebase_execution(
        response_payload: Any,
        execution_key: str,
    ) -> bool:
        if not isinstance(response_payload, Mapping) or not execution_key:
            return False
        late_fill = (
            response_payload.get('late_fill')
            if isinstance(response_payload.get('late_fill'), Mapping)
            else {}
        )
        execution = (
            late_fill.get('partial_rebase_execution')
            if isinstance(late_fill.get('partial_rebase_execution'), Mapping)
            else {}
        )
        if str(execution.get('execution_key') or '').strip() == execution_key:
            return True
        runtime = (
            response_payload.get('runtime')
            if isinstance(response_payload.get('runtime'), Mapping)
            else {}
        )
        graph = (
            runtime.get('request_phase_graph')
            if isinstance(runtime.get('request_phase_graph'), Mapping)
            else {}
        )
        return any(
            isinstance(item, Mapping)
            and str(item.get('execution_key') or '').strip() == execution_key
            for item in graph.get('successor_rebase_executions') or []
        )

    def persist_and_schedule_partial_graph_rebase_successor(
        self,
        prepared: Mapping[str, Any],
        *,
        source_route_payload: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        """Durably append one reviewed partial successor before scheduling it."""

        prepared_payload = dict(prepared) if isinstance(prepared, Mapping) else {}
        if str(prepared_payload.get('status') or '').strip().lower() != 'queued':
            return {
                'status': 'blocked',
                'blocked_reasons': ['partial_rebase_successor_not_prepared'],
            }
        successor_payload = (
            dict(prepared_payload.get('response_payload'))
            if isinstance(prepared_payload.get('response_payload'), Mapping)
            else {}
        )
        artifact_gap = (
            dict(prepared_payload.get('artifact_gap'))
            if isinstance(prepared_payload.get('artifact_gap'), Mapping)
            else {}
        )
        execution = (
            dict(prepared_payload.get('execution'))
            if isinstance(prepared_payload.get('execution'), Mapping)
            else {}
        )
        response_id = str(
            successor_payload.get('response_id')
            or successor_payload.get('id')
            or execution.get('response_id')
            or ''
        ).strip()
        execution_key = str(execution.get('execution_key') or '').strip()
        parent_frame_id = str(execution.get('parent_frame_id') or '').strip()
        parent_frame_sequence = execution.get('parent_frame_sequence')
        if (
            not response_id
            or not execution_key
            or not parent_frame_id
            or isinstance(parent_frame_sequence, bool)
            or parent_frame_sequence in (None, '')
        ):
            return {
                'status': 'blocked',
                'blocked_reasons': ['partial_rebase_successor_binding_incomplete'],
            }
        if not artifact_gap or str(artifact_gap.get('trigger') or '').strip() != (
            'graph_rebase_partial_successor'
        ):
            return {
                'status': 'blocked',
                'blocked_reasons': ['partial_rebase_successor_gap_invalid'],
            }
        if not callable(self.load_latest_response_state):
            return {
                'status': 'blocked',
                'blocked_reasons': ['durable_partial_rebase_verification_unavailable'],
            }

        with _PARTIAL_GRAPH_REBASE_HANDOFF_LOCK:
            durable_state = self.load_latest_response_state(response_id)
            durable_payload = (
                durable_state.get('response_payload')
                if isinstance(durable_state, Mapping)
                and isinstance(durable_state.get('response_payload'), Mapping)
                else {}
            )
            if (
                not isinstance(durable_state, Mapping)
                or durable_state.get('ok') is not True
                or not durable_payload
                or (
                    isinstance(durable_state.get('errors'), list)
                    and durable_state.get('errors')
                )
            ):
                return {
                    'status': 'blocked',
                    'blocked_reasons': [
                        'durable_partial_rebase_verification_unavailable'
                    ],
                }
            if self._payload_has_partial_graph_rebase_execution(
                durable_payload,
                execution_key,
            ):
                return {
                    'status': 'already_recorded',
                    'execution_key': execution_key,
                    'response_payload': dict(durable_payload),
                    'scheduled': False,
                }
            durable_parent_frame = (
                durable_state.get('response_frame')
                if isinstance(durable_state.get('response_frame'), Mapping)
                else durable_payload.get('response_frame')
                if isinstance(durable_payload.get('response_frame'), Mapping)
                else {}
            )
            durable_parent_frame_id = str(
                durable_parent_frame.get('frame_id') or ''
            ).strip()
            durable_parent_frame_sequence = durable_parent_frame.get('frame_sequence')
            if (
                durable_parent_frame_id != parent_frame_id
                or (
                    parent_frame_sequence is not None
                    and durable_parent_frame_sequence != parent_frame_sequence
                )
            ):
                return {
                    'status': 'blocked',
                    'blocked_reasons': [RESPONSE_FRAME_STALE_PARENT_REASON],
                    'expected_parent_frame_id': parent_frame_id,
                    'current_parent_frame_id': durable_parent_frame_id or None,
                    'expected_parent_frame_sequence': parent_frame_sequence,
                    'current_parent_frame_sequence': durable_parent_frame_sequence,
                }

            durable_request: dict[str, Any] = {}
            if callable(self.load_latest_response_observation_state):
                observation_state = self.load_latest_response_observation_state(
                    response_id
                )
                observation_frame = (
                    observation_state.get('response_frame')
                    if isinstance(observation_state, Mapping)
                    and isinstance(observation_state.get('response_frame'), Mapping)
                    else {}
                )
                observation_payload = (
                    observation_state.get('response_payload')
                    if isinstance(observation_state, Mapping)
                    and isinstance(observation_state.get('response_payload'), Mapping)
                    else {}
                )
                if (
                    not isinstance(observation_state, Mapping)
                    or observation_state.get('ok') is not True
                    or str(observation_frame.get('frame_id') or '').strip()
                    != durable_parent_frame_id
                    or observation_frame.get('frame_sequence')
                    != durable_parent_frame_sequence
                ):
                    return {
                        'status': 'blocked',
                        'blocked_reasons': [
                            'durable_partial_rebase_root_truth_unavailable'
                        ],
                    }
                if isinstance(observation_payload.get('request'), Mapping):
                    durable_request = dict(observation_payload.get('request') or {})
            if not durable_request and isinstance(
                durable_parent_frame.get('request'), Mapping
            ):
                durable_request = dict(durable_parent_frame.get('request') or {})
            if not durable_request and isinstance(durable_payload.get('request'), Mapping):
                durable_request = dict(durable_payload.get('request') or {})
            canonical_frame = (
                durable_payload.get('response_frame')
                if isinstance(durable_payload.get('response_frame'), Mapping)
                else {}
            )
            if isinstance(canonical_frame.get('request'), Mapping):
                durable_request = dict(canonical_frame['request'])
            # For legacy frames this value is only a forbidden replay digest,
            # never original-intent authority. Exact accepted branch/operator
            # gates remain necessary, and the successor retains missing intent.
            current_root_prompt = (
                str(durable_request.get('prompt') or '').strip()
                or extract_responses_current_turn_prompt(durable_request)
            )
            durable_request = restore_request_intent(durable_request)
            execution_contract = (
                artifact_gap.get('execution_contract')
                if isinstance(artifact_gap.get('execution_contract'), Mapping)
                else {}
            )
            forbidden_root_prompt_digest = str(
                execution_contract.get('forbidden_root_prompt_digest') or ''
            ).strip()
            if not current_root_prompt:
                return {
                    'status': 'blocked',
                    'blocked_reasons': [
                        'partial_rebase_current_root_prompt_truth_unavailable'
                    ],
                }
            if not forbidden_root_prompt_digest:
                return {
                    'status': 'blocked',
                    'blocked_reasons': [
                        'partial_rebase_root_prompt_guard_missing'
                    ],
                }
            if (
                stable_graph_rebase_prompt_digest(current_root_prompt)
                != forbidden_root_prompt_digest
            ):
                return {
                    'status': 'blocked',
                    'blocked_reasons': [
                        'partial_rebase_root_prompt_guard_mismatch'
                    ],
                }
            successor_request_payload = durable_request
            durable_request_meta = (
                durable_request.get('request_meta')
                if isinstance(durable_request.get('request_meta'), Mapping)
                else {}
            )
            if durable_request_meta:
                successor_request_payload['request_meta'] = dict(
                    durable_request_meta
                )
                reasoning_provenance = (
                    durable_request_meta.get('reasoning_effort_control')
                    if isinstance(
                        durable_request_meta.get('reasoning_effort_control'),
                        Mapping,
                    )
                    else {}
                )
                if reasoning_provenance.get('value') not in (None, ''):
                    successor_request_payload['reasoning_effort'] = (
                        reasoning_provenance.get('value')
                    )

            try:
                finalized_successor = self.finalize_response_frame_payload(
                    successor_payload,
                    request_payload=successor_request_payload,
                    persist=True,
                    expected_parent_frame_id=parent_frame_id,
                    expected_parent_frame_sequence=parent_frame_sequence,
                )
            except ResponseFrameParentCASMismatch as exc:
                return {
                    'status': 'blocked',
                    'blocked_reasons': [exc.code],
                    **exc.as_dict(),
                }
            finalized_frame = (
                finalized_successor.get('response_frame')
                if isinstance(finalized_successor.get('response_frame'), Mapping)
                else {}
            )
            finalized_frame_id = str(finalized_frame.get('frame_id') or '').strip()
            relation = (
                finalized_frame.get('frame_relation')
                if isinstance(finalized_frame.get('frame_relation'), Mapping)
                else {}
            )
            if (
                not finalized_frame_id
                or finalized_frame_id == parent_frame_id
                or str(relation.get('kind') or '').strip()
                != 'graph_rebase_partial_successor'
                or str(relation.get('parent_frame_id') or '').strip()
                != parent_frame_id
                or str(relation.get('execution_key') or '').strip()
                != execution_key
            ):
                return {
                    'status': 'blocked',
                    'blocked_reasons': ['partial_rebase_successor_frame_relation_invalid'],
                }

            durable_state = self.load_latest_response_state(response_id)
            durable_successor = (
                durable_state.get('response_payload')
                if isinstance(durable_state, Mapping)
                and isinstance(durable_state.get('response_payload'), Mapping)
                else {}
            )
            durable_frame = (
                durable_state.get('response_frame')
                if isinstance(durable_state, Mapping)
                and isinstance(durable_state.get('response_frame'), Mapping)
                else {}
            )
            if (
                durable_state.get('ok') is not True
                or str(durable_frame.get('frame_id') or '').strip() != finalized_frame_id
                or not self._payload_has_partial_graph_rebase_execution(
                    durable_successor,
                    execution_key,
                )
            ):
                return {
                    'status': 'blocked',
                    'blocked_reasons': ['partial_rebase_successor_not_durable'],
                    'execution_key': execution_key,
                }

            self.touch_response_lookup(
                response_id,
                status='completed',
                output_text=str(finalized_successor.get('output_text') or ''),
                response_payload=finalized_successor,
            )
            scheduled = self.schedule_response_late_fill(
                response_payload=finalized_successor,
                request_payload=successor_request_payload,
                assistant_message='',
                artifact_gap=artifact_gap,
                source_route_payload=(
                    dict(source_route_payload)
                    if isinstance(source_route_payload, Mapping)
                    else dict(durable_payload.get('route_payload') or {})
                    if isinstance(durable_payload.get('route_payload'), Mapping)
                    else None
                ),
            )
            status = 'queued' if scheduled else 'durable_pending'
            self.log_unified_event(
                category='responses',
                action='graph_rebase_partial_successor',
                status=status,
                response_id=response_id,
                proposal_id=execution.get('proposal_id'),
                authorization_record_id=execution.get('authorization_record_id'),
                execution_key=execution_key,
                scheduled_branch_ids=execution.get('scheduled_branch_ids'),
                message=(
                    'Persisted exact partial graph-rebase successor before scheduling '
                    'its branch-local Late Fill wave.'
                ),
            )
            return {
                'status': status,
                'execution_key': execution_key,
                'execution': execution,
                'response_payload': finalized_successor,
                'scheduled': bool(scheduled),
            }

    @classmethod
    def _durable_graph_patch_successor_descends_from_parent(
        cls,
        durable_payload: Any,
        parent_payload: Any,
    ) -> bool:
        if not isinstance(durable_payload, Mapping) or not isinstance(parent_payload, Mapping):
            return False
        parent_frame = (
            parent_payload.get('response_frame')
            if isinstance(parent_payload.get('response_frame'), Mapping)
            else {}
        )
        parent_frame_id = str(parent_frame.get('frame_id') or '').strip()
        if not parent_frame_id:
            return False
        durable_frame = (
            durable_payload.get('response_frame')
            if isinstance(durable_payload.get('response_frame'), Mapping)
            else {}
        )
        durable_relation = (
            durable_frame.get('frame_relation')
            if isinstance(durable_frame.get('frame_relation'), Mapping)
            else {}
        )
        if (
            str(durable_relation.get('kind') or '').strip() == 'graph_patch_reopen_successor'
            and str(durable_relation.get('parent_frame_id') or '').strip() == parent_frame_id
        ):
            execution_key = str(durable_relation.get('successor_execution_key') or '').strip()
            if execution_key and cls._payload_has_graph_patch_successor_execution(
                durable_payload,
                execution_key,
            ):
                return True
        runtime = (
            durable_payload.get('runtime')
            if isinstance(durable_payload.get('runtime'), Mapping)
            else {}
        )
        graph = (
            runtime.get('request_phase_graph')
            if isinstance(runtime.get('request_phase_graph'), Mapping)
            else {}
        )
        for request in graph.get('successor_reopen_requests') or []:
            if not isinstance(request, Mapping):
                continue
            if str(request.get('parent_frame_id') or '').strip() != parent_frame_id:
                continue
            execution = (
                request.get('execution')
                if isinstance(request.get('execution'), Mapping)
                else {}
            )
            execution_key = str(
                request.get('successor_execution_key')
                or execution.get('successor_execution_key')
                or ''
            ).strip()
            if execution_key and cls._payload_has_graph_patch_successor_execution(
                durable_payload,
                execution_key,
            ):
                return True
        return False

    _pending_contract = staticmethod(PendingContinuationAuthority._pending_contract)

    _pending_accepted_evidence = staticmethod(PendingContinuationAuthority._pending_accepted_evidence)

    def _new_pending_continuation(self, payload, request_payload):
        return self.pending_continuation_authority._new_pending_continuation(payload, request_payload)

    _pending_execution_binding = staticmethod(PendingContinuationAuthority._pending_execution_binding)

    def _pending_frame_request(self, payload):
        return self.pending_continuation_authority._pending_frame_request(payload)

    def _require_pending_continuation(self, context, current, *, exact_frame=True):
        return self.pending_continuation_authority._require_pending_continuation(context, current, exact_frame=exact_frame)

    _pending_execution_identity = staticmethod(PendingContinuationAuthority._pending_execution_identity)

    def _pending_branch_prerequisites(self, branch, payload, context):
        """Eligibility is separate from the invocation's scheduling permission."""
        branch_id = self.branch_id(branch)
        if (branch_id not in (context.scope or ())
                or self.semantic_execution_gate_decision(branch, payload).get('action') == 'skip'):
            return False
        graph = (payload.get('runtime') or {}).get('request_phase_graph') or {}
        late = payload.get('late_fill') or {}
        for dependency in branch_result_contracts.late_fill_branch_dependency_ids(branch, current_payload=payload):
            producers = [p for p in graph.get('phases', []) if dependency in {
                p.get('branch_id'), p.get('phase_id'), p.get('task_id'), p.get('obligation_id')}]
            if len(producers) != 1:
                return False
            producer = producers[0]
            producer_id = self.branch_id(producer)
            if self.semantic_execution_gate_decision(producer, payload).get('action') == 'skip':
                return False
            if any(self.branch_id(r) == producer_id for key in ('failed_branches', 'cancelled_branches')
                   for r in late.get(key, [])):
                return False
            results = [r for r in late.get('fill_results', []) if self.branch_id(r) == producer_id]
            if len(results) != 1:
                # A canonical source-phase text output can precede Late Fill.
                outputs = ((payload.get('response_frame') or {}).get('output') or {}).get('outputs') or []
                if results or not any(o.get('phase_id') == producer.get('phase_id')
                        and o.get('branch_id') == producer_id and o.get('status') == 'fulfilled'
                        and o.get('type') in {'text', 'message'} for o in outputs):
                    return False
            else:
                result = results[0]
                if (any(producer.get(k) and result.get(k) != producer[k]
                        for k in ('branch_id', 'phase_id', 'obligation_id'))
                        or branch_result_contracts.late_fill_result_has_missing_dependency_evidence(result)):
                    return False
                if (producer.get('output_type') in {'image', 'audio'}
                        or self.branch_selection._branch_is_required_text_artifact(producer)):
                    if not self._terminal_materialization_branch_has_canonical_evidence(producer, payload, late):
                        return False
        local = [branch.get(k) for k in ('artifact_prompt', 'content_payload', 'phase_summary', 'stage_direction')]
        if not any(isinstance(v, str) and v.strip() for v in local):
            dependency = self.branch_dependency_evidence.branch_dependency_payload(branch, current_payload=payload)
            if not dependency.get('content_payload') or not dependency.get('content_payload_source'):
                return False
        return True

    def _prepare_pending_control_handoff(self, context, *, artifact_gap, source_route_payload):
        if not isinstance(context, _PendingContinuation) or not context.chain.take_attempt():
            return None
        response_id = context.chain.admission.get('id')
        try:
            if context.wave_active:
                raise ResponseMutationConflict('pending continuation wave is not quiescent')
            with self.response_mutation(response_id):
                current = copy.deepcopy((self.get_response_lookup_record(response_id) or {}).get('response_payload') or {})
                self._require_pending_continuation(context, current, exact_frame=False)
                old_frame, new_frame = response_wire_frame_identity(context.base), response_wire_frame_identity(current)
                receipt = current.get('persistence') or {}
                if (not old_frame[0] or not new_frame[0] or new_frame[1] <= old_frame[1]
                        or receipt.get('status') != 'committed'
                        or receipt.get('response_id') != response_id
                        or (receipt.get('frame_id'), receipt.get('frame_sequence')) != new_frame):
                    raise ResponseMutationConflict('pending continuation requires committed control frame')
                old = context.base.get('late_fill') or {}
                late = current.get('late_fill') or {}
                controls = late.get('branch_controls') or []
                added = [c for c in controls if c not in (old.get('branch_controls') or [])]
                if (not added or any(c not in controls for c in old.get('branch_controls') or [])
                        or any(c not in (late.get('cancelled_branches') or []) for c in old.get('cancelled_branches') or [])):
                    raise ResponseMutationConflict('pending continuation requires monotone control')
                for control in added:
                    target = context.chain.contracts.get(self.branch_id(control))
                    if (not target or control.get('authority') != 'user_control'
                            or control.get('status') not in {'cancelled', 'waived', 'superseded'}
                            or control.get('action') != control.get('status')
                            or not any(self.branch_id(c) == self.branch_id(control)
                                       and c.get('status') == control['status']
                                       for c in late.get('cancelled_branches') or [])):
                        raise ResponseMutationConflict('pending continuation control is not exact')
                    require_response_mutation_target(target, current)
                pending = self.normalize_late_fill_branches(late.get('pending_branches'))
                terminal = {self.branch_id(b) for key in ('completed_branches', 'failed_branches', 'cancelled_branches')
                            for b in late.get(key, [])}
                scope = set()
                for branch in pending:
                    branch_id = self.branch_id(branch)
                    original = context.chain.contracts.get(branch_id)
                    if not original or PendingContinuationAuthority._pending_contract(original) != PendingContinuationAuthority._pending_contract(branch):
                        raise ResponseMutationConflict('pending continuation local contract changed')
                    if (branch.get('status') == 'pending' and branch_id not in terminal
                            and branch_id not in context.chain.submitted
                            and not any(self.branch_id(b) == branch_id for b in late.get('active_branches', []))):
                        scope.add(branch_id)
                if any(branch_id not in terminal and branch_id not in context.chain.submitted
                       and branch_id not in {self.branch_id(b) for b in pending}
                       for branch_id in context.chain.contracts):
                    raise ResponseMutationConflict('pending continuation lost an obligation')
                if not scope:
                    return None
                child = _PendingContinuation(context.chain, current, frozenset(scope))
            # Preparation/evidence is outside mutation; scheduling revalidates.
            if not any(self._pending_branch_prerequisites(b, current, child) for b in pending):
                return None
            gap = copy.deepcopy(artifact_gap)
            for key in ('artifact_prompt', 'artifact_prompt_source', 'content_payload', 'content_payload_source',
                        'phase_summary', 'stage_direction', 'batch_prompts', 'batch_prompts_source'):
                gap.pop(key, None)
            gap.update(pending_branches=copy.deepcopy(pending), authoritative_pending_branches=True)
            self.log_unified_event(category='responses', action='pending_control_continuation', status='prepared',
                                   response_id=response_id, handoff_attempt=1, branch_ids=sorted(scope))
            return dict(response_payload=current, request_payload=copy.deepcopy(context.chain.request),
                        assistant_message='', artifact_gap=gap, source_route_payload=copy.deepcopy(source_route_payload),
                        pending_continuation=child)
        except (ResponseMutationConflict, ValueError, TypeError, OSError) as exc:
            self.log_unified_event(category='responses', action='pending_control_continuation', status='pending',
                                   response_id=response_id, message=str(exc))
            return None

    def _park_pending_continuation(self, context, pending, request_payload):
        payload = copy.deepcopy(context.base)
        late = dict(payload.get('late_fill') or {})
        late.update(status='pending', pending_branches=copy.deepcopy(pending), active_branches=[],
                    active_capabilities=[], active_capability=None,
                    branch_progress=[r for r in late.get('branch_progress', [])
                                     if self.branch_id(r) not in {self.branch_id(b) for b in pending}])
        late['scheduling_policy'] = {**(late.get('scheduling_policy') or {}),
                                     'pending_continuation': 'blocked_prerequisites'}
        payload = self.attach_late_fill_state(payload, late)
        with self._late_fill_publication(payload, expected_payload=context.base, pending_continuation=context):
            final = self.finalize_response_frame_payload(payload, request_payload=request_payload, persist=True)
            self.touch_response_lookup(str(payload['id']), response_payload=final)

    def _initial_late_fill_branch_eligibility(
        self,
        branch: Mapping[str, Any],
        *,
        artifact_gap: dict[str, Any],
        response_payload: dict[str, Any],
        late_fill_state: dict[str, Any],
        terminal_branch_ids: list[str],
        legacy_terminal_capabilities: list[str],
        duplicate_capability_counts: Mapping[str, int],
        build_gap: Callable[..., dict[str, Any]],
    ) -> Literal['pending', 'excluded', 'fulfilled']:
        """Decide initial eligibility without settling or scheduling the branch.

        Terminal ids must reflect earlier caller updates; capability counts stay
        fixed at the original pending sequence. Gap construction and evidence
        evaluation precede the duplicate guard, even for duplicate capabilities.
        """
        branch_id = self.branch_id(branch)
        candidate = self.branch_capability(branch)
        if not candidate:
            return 'excluded'
        if not branch_id and candidate in legacy_terminal_capabilities:
            return 'excluded'
        if branch_id and branch_id in terminal_branch_ids:
            return 'excluded'

        candidate_gap = build_gap(
            artifact_gap,
            capability=candidate,
            artifact_payload=response_payload,
        )
        if self.branch_selection._branch_is_required_text_artifact(branch):
            branch_already_fulfilled = self._text_artifact_branch_has_canonical_evidence(
                branch,
                response_payload,
            )
        elif candidate == self.capability_image_generation:
            branch_already_fulfilled = self._terminal_materialization_branch_has_canonical_evidence(
                branch,
                response_payload,
                late_fill_state,
            )
        else:
            branch_already_fulfilled = self.artifact_gap_is_already_fulfilled(
                candidate_gap,
                response_payload,
            )
        if duplicate_capability_counts.get(candidate, 0) <= 1 and branch_already_fulfilled:
            return 'fulfilled'
        return 'pending'

    @contextmanager
    def _late_fill_publication(
        self, payload: dict[str, Any], *, expected_payload: Optional[Mapping[str, Any]] = None,
        pending_continuation: Optional[_PendingContinuation] = None,
    ):
        """Revalidate a prepared candidate and hold authority through publication.

        Preparation/physical writes are not accepted evidence. The existing frame
        identity is the version: a changed control frame rejects this candidate,
        retaining its physical artifacts without publishing them as fulfillment.
        """
        response_id = str(payload.get('id') or '')
        with self.response_mutation(response_id):
            current = (self.get_response_lookup_record(response_id) or {}).get('response_payload') or {}
            if current:
                base = expected_payload or payload
                current_controls = (current.get('late_fill') or {}).get('branch_controls') or []
                # Runtime controls may arrive in the live view without a new
                # frame. Carry them forward before revalidation, so an unrelated
                # sibling control does not abort the normal continuation loop.
                # A new durable control frame still conflicts below.
                base = {**base, 'late_fill': {
                    **(base.get('late_fill') or {}), 'branch_controls': current_controls,
                }}
                require_response_mutation_base(base, current)
                if current_controls:
                    candidate_late = dict(payload.get('late_fill') or {})
                    candidate_late['branch_controls'] = [
                        *[record for record in (candidate_late.get('branch_controls') or [])
                          if record not in current_controls],
                        *copy.deepcopy(current_controls),
                    ]
                    payload['late_fill'] = candidate_late
                prior_results = (current.get('late_fill') or {}).get('fill_results') or []
                for result in (payload.get('late_fill') or {}).get('fill_results') or []:
                    if result in prior_results:
                        continue
                    require_response_mutation_target(result, current)
                    decision = self.semantic_execution_gate_decision(result, current)
                    if decision.get('action') == 'skip':
                        raise ResponseMutationConflict('response_mutation_conflict: target is terminal')
            yield
            if pending_continuation is not None:
                pending_continuation.base = copy.deepcopy(
                    (self.get_response_lookup_record(response_id) or {}).get('response_payload') or payload)

    @observe_worker
    def complete_response_late_fill(
        self,
        *,
        response_payload: dict[str, Any],
        request_payload: dict[str, Any],
        assistant_message: str,
        artifact_gap: dict[str, Any],
        source_route_payload: Optional[dict[str, Any]],
        pending_continuation: Optional[_PendingContinuation] = None,
        build_deferred_follow_up_gap_for_capability: Optional[Callable[..., dict[str, Any]]] = None,
        prepare_late_fill_branch_plan: Optional[Callable[..., dict[str, Any]]] = None,
        execute_prepared_late_fill_branch: Optional[Callable[[dict[str, Any]], dict[str, Any]]] = None,
    ) -> None:
        build_gap = build_deferred_follow_up_gap_for_capability or self.build_deferred_follow_up_gap_for_capability
        using_default_prepare_plan = prepare_late_fill_branch_plan is None
        prepare_plan = prepare_late_fill_branch_plan or self.prepare_late_fill_branch_plan
        execute_plan = execute_prepared_late_fill_branch or self.execute_prepared_late_fill_branch

        response_id = str((response_payload or {}).get('id') or '').strip()
        if not response_id:
            return
        # A duplicate entry did not acquire a claim and must never release one.
        if pending_continuation is not None and not pending_continuation.take_entry():
            return
        guarded_pending = pending_continuation is not None and pending_continuation.scope is not None
        trace = LateFillTrace(response_id)
        successor_handoff: Optional[dict[str, Any]] = None
        completed_capabilities: list[str] = []
        failed_capabilities: list[str] = []
        cancelled_capabilities: list[str] = []
        completed_branches: list[str] = []
        failed_branches: list[str] = []
        cancelled_branches: list[str] = []
        try:
            with trace.span('initial_lookup'):
                existing_record = self.get_response_lookup_record(response_id) or {}
            recovered_payload = (
                existing_record.get('response_payload')
                if isinstance(existing_record.get('response_payload'), Mapping)
                else {}
            )
            if guarded_pending:
                with self.response_mutation(response_id):
                    recovered_payload = copy.deepcopy((self.get_response_lookup_record(response_id) or {}).get('response_payload') or {})
                    self._require_pending_continuation(pending_continuation, recovered_payload)
                    if not any(self._pending_branch_prerequisites(b, recovered_payload, pending_continuation)
                               for b in (recovered_payload.get('late_fill') or {}).get('pending_branches', [])):
                        return
                response_payload = recovered_payload
            explicit_payload = response_payload if isinstance(response_payload, Mapping) else {}
            terminal_closure_execution_key = self._terminal_closure_repair_execution_key(
                explicit_payload,
            )
            if (
                terminal_closure_execution_key
                and self._payload_has_terminal_closure_repair_execution(
                    recovered_payload,
                    terminal_closure_execution_key,
                )
            ):
                self.log_unified_event(
                    category='responses',
                    action='terminal_closure_repair_reopen',
                    status='stale_handoff_ignored',
                    response_id=response_id,
                    execution_key=terminal_closure_execution_key,
                    message='Ignored stale terminal Closure handoff after durable branch completion.',
                )
                return
            if self._durable_graph_patch_successor_descends_from_parent(
                recovered_payload,
                explicit_payload,
            ):
                self.log_unified_event(
                    category='responses',
                    action='graph_patch_successor_reopen',
                    status='stale_parent_ignored',
                    response_id=response_id,
                    message='Ignored stale terminal-parent replay after durable successor persistence.',
                )
                return
            current_payload = (
                dict(explicit_payload)
                if self._prefer_explicit_late_fill_seed_payload(explicit_payload, recovered_payload)
                else dict(recovered_payload or explicit_payload or {})
            )
            source_route_payload = (
                self._source_route_with_response_external_runtime(
                    source_route_payload,
                    current_payload,
                )
            )
            current_late_fill = current_payload.get('late_fill') if isinstance(current_payload.get('late_fill'), dict) else {}
            legacy_completed_capabilities = self.normalize_capability_list(current_late_fill.get('completed_capabilities'))
            legacy_failed_capabilities = self.normalize_capability_list(current_late_fill.get('failed_capabilities'))
            legacy_cancelled_capabilities = self.normalize_capability_list(current_late_fill.get('cancelled_capabilities'))
            completed_branch_records = self.normalize_late_fill_branches(current_late_fill.get('completed_branches'))
            failed_branch_records = self.normalize_late_fill_branches(current_late_fill.get('failed_branches'))
            cancelled_branch_records = self.normalize_late_fill_branches(current_late_fill.get('cancelled_branches'))
            completed_branches = [self.branch_id(item) for item in completed_branch_records if self.branch_id(item)]
            failed_branches = [self.branch_id(item) for item in failed_branch_records if self.branch_id(item)]
            cancelled_branches = [self.branch_id(item) for item in cancelled_branch_records if self.branch_id(item)]
            if guarded_pending:
                pending_branches = self.normalize_late_fill_branches(current_late_fill.get('pending_branches'))
                pending_capabilities = self.normalize_capability_list([self.branch_capability(b) for b in pending_branches])
            else:
                extracted_pending_branches = self.extract_pending_deferred_branches(
                    route_payload=source_route_payload,
                    artifact_payload=current_payload,
                )
                gap_pending_branches = self.normalize_late_fill_branches(
                    artifact_gap.get('pending_branches')
                )
                if gap_pending_branches and (
                    artifact_gap.get('authoritative_pending_branches') is True
                    or len(gap_pending_branches) > len(extracted_pending_branches)
                    or artifact_gap.get('prepared_image_prompt_branch_expansion') not in (None, '', [], {})
                ):
                    pending_branch_seed = gap_pending_branches
                else:
                    pending_branch_seed = extracted_pending_branches
                pending_branches = self.build_pending_late_fill_branches(
                    artifact_gap=artifact_gap,
                    late_fill_state=current_late_fill,
                    pending_branches=pending_branch_seed,
                )
                pending_capabilities = self.normalize_capability_list(artifact_gap.get('pending_capabilities'))
                if not pending_capabilities:
                    pending_capabilities = self.normalize_capability_list(
                        [self.branch_capability(item) for item in pending_branches if self.branch_capability(item)]
                    )
                if not pending_branches and not pending_capabilities:
                    pending_capabilities = self.extract_pending_deferred_capabilities(
                        route_payload=source_route_payload,
                        artifact_payload=current_payload,
                    )
                if not pending_branches and pending_capabilities:
                    pending_branches = self.build_pending_late_fill_branches(
                        artifact_gap=artifact_gap,
                        late_fill_state=current_late_fill,
                        pending_capabilities=pending_capabilities,
                    )
                if not pending_branches and not pending_capabilities:
                    expected_capability = self.normalize_capability(artifact_gap.get('expected_capability'))
                    if expected_capability:
                        pending_branches = self.build_pending_late_fill_branches(
                            artifact_gap=artifact_gap,
                            late_fill_state=current_late_fill,
                            pending_capabilities=[expected_capability],
                        )
            def _remember_branch(
                records: list[dict[str, Any]],
                record_ids: list[str],
                branch: Mapping[str, Any],
                *,
                status: Optional[str] = None,
                error: Optional[Mapping[str, Any]] = None,
                attempt: Optional[Mapping[str, Any]] = None,
                recovery_context: Optional[Mapping[str, Any]] = None,
                recovery_state: Optional[Mapping[str, Any]] = None,
            ) -> None:
                branch_id = self.branch_id(branch)
                capability = self.branch_capability(branch)
                if not branch_id or not capability:
                    return
                normalized_branch = dict(branch)
                removed_wait = normalized_branch.pop('availability_wait', None)
                trace.wait_settled(branch, removed_wait, status)
                normalized_branch['branch_id'] = branch_id
                normalized_branch['phase_id'] = str(branch.get('phase_id') or branch_id).strip() or branch_id
                normalized_branch['capability'] = capability
                if status:
                    normalized_branch['status'] = str(status).strip().lower()
                if error:
                    normalized_branch['error'] = dict(error)
                if attempt:
                    normalized_branch['attempt'] = dict(attempt)
                if recovery_context:
                    normalized_branch['recovery_context'] = dict(recovery_context)
                if recovery_state:
                    normalized_branch['recovery_state'] = dict(recovery_state)
                for index, existing in enumerate(records):
                    if self.branch_id(existing) != branch_id:
                        continue
                    records[index] = normalized_branch
                    break
                else:
                    records.append(normalized_branch)
                if branch_id not in record_ids:
                    record_ids.append(branch_id)
                trace.branch_settled(branch, normalized_branch, status, attempt)

            def _final_lookup_status_for_late_fill(final_status: str) -> str:
                normalized = str(final_status or '').strip().lower()
                if normalized == 'partial_failed':
                    return 'incomplete'
                if normalized == 'failed':
                    return 'failed'
                return 'completed'

            def _status_for_terminal_state(
                active_pending_branches: list[dict[str, Any]],
            ) -> str:
                if active_pending_branches:
                    return 'running'
                if failed_branch_records and completed_branch_records:
                    return 'partial_failed'
                if failed_branch_records or failed_capabilities:
                    return 'failed'
                if cancelled_branch_records and completed_branch_records:
                    return 'partial_cancelled'
                if cancelled_branch_records or cancelled_capabilities:
                    return 'cancelled'
                return 'completed'

            completed_branch_records = [
                dict(item)
                for item in completed_branch_records
                if self.branch_id(item) not in failed_branches
                and self.branch_id(item) not in cancelled_branches
            ]

            def _capability_lists_for_branch_state(active_pending_branches: list[dict[str, Any]]) -> tuple[list[str], list[str], list[str]]:
                pending_caps = self.normalize_capability_list(
                    [self.branch_capability(item) for item in active_pending_branches if self.branch_capability(item)]
                )
                pending_capability_set = set(pending_caps)
                completed_caps = [
                    capability
                    for capability in legacy_completed_capabilities
                    if capability not in pending_capability_set
                ]
                failed_caps = [
                    capability
                    for capability in legacy_failed_capabilities
                    if capability not in completed_caps and capability not in pending_capability_set
                ]
                for branch in completed_branch_records:
                    capability = self.branch_capability(branch)
                    if not capability or capability in pending_capability_set or capability in completed_caps:
                        continue
                    completed_caps.append(capability)
                for branch in failed_branch_records:
                    capability = self.branch_capability(branch)
                    if (
                        not capability
                        or capability in pending_capability_set
                        or capability in completed_caps
                        or capability in failed_caps
                    ):
                        continue
                    failed_caps.append(capability)
                return pending_caps, completed_caps, failed_caps

            def _cancelled_capability_list() -> list[str]:
                values = [
                    *legacy_cancelled_capabilities,
                    *[
                        self.branch_capability(branch)
                        for branch in cancelled_branch_records
                        if self.branch_capability(branch)
                    ],
                ]
                return self.normalize_capability_list(values)

            duplicate_capability_counts = self.late_fill_capability_counts(pending_branches)

            pruned_pending: list[dict[str, Any]] = []
            for branch in pending_branches:
                if guarded_pending:
                    pruned_pending.append(branch)
                    continue
                eligibility = self._initial_late_fill_branch_eligibility(
                    branch,
                    artifact_gap=artifact_gap,
                    response_payload=current_payload,
                    late_fill_state=current_late_fill,
                    terminal_branch_ids=[*completed_branches, *failed_branches, *cancelled_branches],
                    legacy_terminal_capabilities=[
                        *legacy_completed_capabilities,
                        *legacy_failed_capabilities,
                        *legacy_cancelled_capabilities,
                    ],
                    duplicate_capability_counts=duplicate_capability_counts,
                    build_gap=build_gap,
                )
                if eligibility == 'excluded':
                    continue
                if eligibility == 'fulfilled':
                    _remember_branch(completed_branch_records, completed_branches, branch, status='fulfilled')
                    continue
                pruned_pending.append(branch)
            pending_branches = pruned_pending
            pending_capabilities, completed_capabilities, failed_capabilities = _capability_lists_for_branch_state(
                pending_branches
            )
            cancelled_capabilities = _cancelled_capability_list()

            if not pending_branches:
                terminal_status = _status_for_terminal_state(pending_branches)
                skipped_late_fill = self.build_late_fill_state(
                    build_gap(
                        artifact_gap,
                        capability=self.normalize_capability(artifact_gap.get('expected_capability')),
                        artifact_payload=current_payload,
                        pending_capabilities=[],
                        completed_capabilities=completed_capabilities,
                        failed_capabilities=failed_capabilities,
                    ),
                    status=terminal_status if terminal_status != 'completed' else 'skipped',
                    prior_state=current_late_fill,
                    extra={
                        'route_source': 'already_fulfilled',
                        'route_reason': 'all requested downstream artifacts were already present before late fill started'
                        if not cancelled_branch_records
                        else 'all remaining downstream branches were cancelled, waived, or superseded before execution',
                        'skip_kind': 'no_work_needed' if not cancelled_branch_records else 'semantic_execution_gate',
                        'skip_reason': 'already_fulfilled' if not cancelled_branch_records else 'terminal_branch_state',
                        'skip_source': 'late_fill_prune',
                        'pending_capabilities': [],
                        'completed_capabilities': completed_capabilities,
                        'failed_capabilities': failed_capabilities,
                        'cancelled_capabilities': cancelled_capabilities,
                        'pending_branches': [],
                        'completed_branches': completed_branch_records,
                        'failed_branches': failed_branch_records,
                        'cancelled_branches': cancelled_branch_records,
                        'fill_results': copy.deepcopy(current_late_fill.get('fill_results') or []),
                    },
                )
                payload_for_finalize, effective_terminal_status = self.finalize_terminal_materialization_contract(
                    self.attach_late_fill_state(current_payload, skipped_late_fill),
                    request_payload=request_payload,
                    route_payload=source_route_payload,
                    artifact_gap=artifact_gap,
                    terminal_status=str(skipped_late_fill.get('status') or terminal_status or 'skipped'),
                    accepted_fill_results=(current_payload.get('late_fill') or {}).get('fill_results') or [],
                )
                with self._late_fill_publication(payload_for_finalize, expected_payload=current_payload, pending_continuation=pending_continuation):
                    finalized_payload = self.finalize_response_frame_payload(
                        payload_for_finalize,
                        request_payload=request_payload,
                        persist=True,
                    )
                    self.touch_response_lookup(
                        response_id,
                        status=_final_lookup_status_for_late_fill(effective_terminal_status),
                        output_text=str(finalized_payload.get('output_text') or ''),
                        response_payload=finalized_payload,
                    )
                successor_handoff = self._terminal_closure_repair_handoff(
                    finalized_payload,
                    request_payload=request_payload,
                    assistant_message=assistant_message,
                    source_route_payload=source_route_payload,
                )
                if successor_handoff is None:
                    finalized_payload, successor_handoff = (
                        self._prepare_terminal_graph_patch_successor_handoff(
                            finalized_payload,
                            request_payload=request_payload,
                            assistant_message=assistant_message,
                            artifact_gap=artifact_gap,
                            source_route_payload=source_route_payload,
                        )
                    )
                if successor_handoff is None:
                    self.schedule_terminal_substrate_hygiene(
                        finalized_payload,
                        route_payload=source_route_payload,
                        reason='late_fill_already_fulfilled',
                    )
                return

            self.ensure_response_lookup_for_payload(current_payload, mode_hint='chat', route_payload=source_route_payload)
            request_phase_graph = self.request_phase_graph_for_late_fill(
                route_payload=source_route_payload,
                artifact_payload=current_payload,
            )
            fill_results = [
                dict(item)
                for item in (current_late_fill.get('fill_results') or [])
                if isinstance(item, dict)
            ]
            last_effective_request_payload = request_payload

            while pending_branches:
                latest_record = self.get_response_lookup_record(response_id) or {}
                latest_payload = latest_record.get('response_payload') if isinstance(latest_record.get('response_payload'), dict) else None
                if guarded_pending:
                    self._require_pending_continuation(pending_continuation, latest_payload)
                if latest_payload:
                    current_payload = dict(latest_payload)
                    current_late_fill = current_payload.get('late_fill') if isinstance(current_payload.get('late_fill'), dict) else current_late_fill
                    cancelled_branch_records = self.normalize_late_fill_branches(current_late_fill.get('cancelled_branches'))
                    cancelled_branches = [self.branch_id(item) for item in cancelled_branch_records if self.branch_id(item)]
                    cancelled_capabilities = _cancelled_capability_list()
                gate_open_pending: list[dict[str, Any]] = []
                gate_terminalized = False
                for branch in pending_branches:
                    decision = self.semantic_execution_gate_decision(branch, current_payload)
                    if str(decision.get('action') or '').strip().lower() == 'skip':
                        gated_branch = self.branch_record_with_execution_gate(branch, decision)
                        _remember_branch(
                            cancelled_branch_records,
                            cancelled_branches,
                            gated_branch,
                            status=str(gated_branch.get('status') or decision.get('status') or 'cancelled'),
                        )
                        gate_terminalized = True
                        self.log_unified_event(
                            category='responses',
                            action='late_fill',
                            status=str(gated_branch.get('status') or 'cancelled'),
                            response_id=response_id,
                            capability=self.branch_capability(gated_branch),
                            message=str(decision.get('reason') or 'Late-fill branch skipped by semantic execution gate.'),
                        )
                    else:
                        gate_open_pending.append(branch)
                if gate_terminalized:
                    pending_branches = gate_open_pending
                    cancelled_capabilities = _cancelled_capability_list()
                    pending_capabilities, completed_capabilities, failed_capabilities = _capability_lists_for_branch_state(
                        pending_branches
                    )
                    gate_state = self.build_late_fill_state(
                        build_gap(
                            artifact_gap,
                            capability=self.normalize_capability(artifact_gap.get('expected_capability')),
                            artifact_payload=current_payload,
                            pending_capabilities=pending_capabilities,
                            completed_capabilities=completed_capabilities,
                            failed_capabilities=failed_capabilities,
                        ),
                        status=_status_for_terminal_state(pending_branches),
                        prior_state=current_late_fill,
                        extra={
                            'pending_capabilities': pending_capabilities,
                            'completed_capabilities': completed_capabilities,
                            'failed_capabilities': failed_capabilities,
                            'cancelled_capabilities': cancelled_capabilities,
                            'pending_branches': pending_branches,
                            'completed_branches': completed_branch_records,
                            'failed_branches': failed_branch_records,
                            'cancelled_branches': cancelled_branch_records,
                            'active_branches': [],
                            'fill_results': fill_results,
                            'execution_gate_status': 'applied',
                        },
                    )
                    payload_for_finalize, effective_gate_status = self.finalize_terminal_materialization_contract(
                        self.attach_late_fill_state(current_payload, gate_state),
                        request_payload=last_effective_request_payload,
                        route_payload=source_route_payload,
                        artifact_gap=artifact_gap,
                        terminal_status=str(gate_state.get('status') or 'completed'),
                        accepted_fill_results=(current_payload.get('late_fill') or {}).get('fill_results') or [],
                    )
                    with self._late_fill_publication(payload_for_finalize, expected_payload=current_payload, pending_continuation=pending_continuation):
                        current_payload = self.finalize_response_frame_payload(
                            payload_for_finalize,
                            request_payload=last_effective_request_payload,
                            persist=True,
                        )
                        current_late_fill = gate_state
                        self.touch_response_lookup(
                            response_id,
                            status=_final_lookup_status_for_late_fill(effective_gate_status),
                            output_text=str(current_payload.get('output_text') or ''),
                            response_payload=current_payload,
                        )
                    if not pending_branches:
                        successor_handoff = self._terminal_closure_repair_handoff(
                            current_payload,
                            request_payload=last_effective_request_payload,
                            assistant_message=assistant_message,
                            source_route_payload=source_route_payload,
                        )
                        if successor_handoff is None:
                            current_payload, successor_handoff = (
                                self._prepare_terminal_graph_patch_successor_handoff(
                                    current_payload,
                                    request_payload=last_effective_request_payload,
                                    assistant_message=assistant_message,
                                    artifact_gap=artifact_gap,
                                    source_route_payload=source_route_payload,
                                )
                            )
                        if successor_handoff is None:
                            self.schedule_terminal_substrate_hygiene(
                                current_payload,
                                route_payload=source_route_payload,
                                reason='late_fill_execution_gate_terminal',
                            )
                        return

                pending_capabilities, completed_capabilities, failed_capabilities = _capability_lists_for_branch_state(
                    pending_branches
                )
                cancelled_capabilities = _cancelled_capability_list()
                executable_batches = self.downstream_request_phase_batches(
                    request_phase_graph,
                    pending_branches=pending_branches,
                    completed_branches=completed_branch_records,
                    failed_branches=failed_branch_records,
                    pending_capabilities=pending_capabilities,
                    completed_capabilities=completed_capabilities,
                    failed_capabilities=failed_capabilities,
                    **({'resolve_dependency_aliases': True} if guarded_pending else {}),
                )
                active_branches = [dict(branch) for branch in (executable_batches[0] if executable_batches else [])]
                if not active_branches and pending_branches and not guarded_pending:
                    active_branches = [dict(pending_branches[0])]
                pending_branch_by_id = {
                    self.branch_id(branch): dict(branch)
                    for branch in pending_branches
                    if self.branch_id(branch)
                }
                active_branches = [
                    self.overlay_graph_branch_with_runtime_state(
                        branch,
                        pending_branch_by_id.get(self.branch_id(branch)),
                    )
                    for branch in active_branches
                ]
                if guarded_pending:
                    active_branches = [b for b in active_branches
                        if self._pending_branch_prerequisites(b, current_payload, pending_continuation)]
                    if not active_branches:
                        self._park_pending_continuation(pending_continuation, pending_branches, request_payload)
                        return
                dependency_ready_branches = active_branches
                active_branches, scheduling_policy = self.select_active_late_fill_branches(
                    dependency_ready_branches,
                    artifact_gap=artifact_gap,
                )
                if not active_branches and dependency_ready_branches:
                    # This response worker holds no backend/device lock here.
                    # Re-enter the execution gate frequently for cancellation;
                    # route preparation is retried only when its poll is due.
                    time.sleep(min(1.0, min(
                        self.availability_wait_delay(branch)
                        for branch in dependency_ready_branches
                    )))
                    continue
                for eligible in active_branches:
                    trace.availability_wake(eligible)
                active_capabilities = self.normalize_capability_list(
                    [self.branch_capability(branch) for branch in active_branches if self.branch_capability(branch)]
                )
                if not active_capabilities:
                    active_capabilities = pending_capabilities[:1]
                active_capability = active_capabilities[0] if active_capabilities else None
                active_gap = build_gap(
                    artifact_gap,
                    capability=active_capability,
                    artifact_payload=current_payload,
                    pending_capabilities=pending_capabilities,
                    completed_capabilities=completed_capabilities,
                    failed_capabilities=failed_capabilities,
                )
                running_state_extra = {
                    'pending_capabilities': pending_capabilities,
                    'completed_capabilities': completed_capabilities,
                    'failed_capabilities': failed_capabilities,
                    'cancelled_capabilities': cancelled_capabilities,
                    'active_capability': active_capability,
                    'active_capabilities': active_capabilities,
                    'scheduling_policy': scheduling_policy,
                    'pending_branches': pending_branches,
                    'completed_branches': completed_branch_records,
                    'failed_branches': failed_branch_records,
                    'cancelled_branches': cancelled_branch_records,
                    'active_branches': active_branches,
                    'fill_results': fill_results,
                }
                for key in ('materialization_concurrency_policy', 'materialization_concurrency_history'):
                    value = current_late_fill.get(key) if isinstance(current_late_fill, Mapping) else None
                    if value not in (None, '', [], {}):
                        running_state_extra[key] = value
                with trace.span('running_state_build'):
                    running_late_fill = self.build_late_fill_state(
                        active_gap,
                        status='running',
                        prior_state=current_late_fill,
                        extra=running_state_extra,
                    )
                current_payload = self.attach_late_fill_state(current_payload, running_late_fill)
                with self._late_fill_publication(current_payload, pending_continuation=pending_continuation):
                    self.touch_response_lookup(
                        response_id,
                        status='completed',
                        output_text=str(current_payload.get('output_text') or ''),
                        response_payload=current_payload,
                    )

                callback_base = copy.deepcopy(current_payload)
                callback_scope = frozenset(self.branch_id(b) for b in active_branches)

                def publish_live_branch_progress(event: dict[str, Any]) -> None:
                    if not isinstance(event, Mapping):
                        return
                    branch_id = self.branch_id(event)
                    if not branch_id:
                        return
                    callback_trace = trace.callback(event)
                    with callback_trace.span('callback.progress_record'):
                        status = str(event.get('status') or '').strip().lower()
                        progress_record: dict[str, Any] = {
                            'branch_id': branch_id,
                            'phase_id': str(event.get('phase_id') or branch_id).strip() or branch_id,
                            'capability': self.normalize_capability(event.get('capability')),
                            'status': status or 'running',
                            'progress_stage': str(event.get('progress_stage') or 'branch_execution').strip(),
                            'updated_at': self.response_registry_now_iso(),
                        }
                        instance_id = str(event.get('instance_id') or '').strip()
                        if instance_id:
                            progress_record['instance_id'] = instance_id
                        timing = event.get('timing') if isinstance(event.get('timing'), Mapping) else {}
                        if timing:
                            progress_record['timing'] = {
                                key: value
                                for key, value in dict(timing).items()
                                if value not in (None, '', [], {})
                            }
                        error = event.get('error') if isinstance(event.get('error'), Mapping) else {}
                        if error:
                            progress_record['error'] = {
                                key: value
                                for key, value in dict(error).items()
                                if value not in (None, '', [], {})
                            }
                    with self.response_mutation(response_id):
                        with callback_trace.span('callback.lookup'):
                            latest_record = self.get_response_lookup_record(response_id) or {}
                        if pending_continuation is not None:
                            try:
                                require_response_mutation_base(callback_base, (latest_record or {}).get('response_payload') or {})
                                if branch_id not in callback_scope:
                                    return
                            except ResponseMutationConflict:
                                return
                        if self.semantic_execution_gate_decision(event, (latest_record or {}).get('response_payload') or {}).get('action') == 'skip':
                            return
                        with callback_trace.span('callback.state_build'):
                            latest_payload = (
                                latest_record.get('response_payload')
                                if isinstance(latest_record.get('response_payload'), dict)
                                else current_payload
                            )
                            latest_late_fill = (
                                dict(latest_payload.get('late_fill'))
                                if isinstance(latest_payload.get('late_fill'), dict)
                                else dict(running_late_fill)
                            )
                            branch_progress = [
                                dict(item)
                                for item in (latest_late_fill.get('branch_progress') or [])
                                if isinstance(item, Mapping) and self.branch_id(item) and self.branch_id(item) != branch_id
                            ]
                            branch_progress.append(
                                {
                                    key: value
                                    for key, value in progress_record.items()
                                    if value not in (None, '', [], {})
                                }
                            )
                            terminal_progress_ids = {
                                self.branch_id(item)
                                for item in branch_progress
                                if str(item.get('status') or '').strip().lower()
                                in {'completed', 'fulfilled', 'failed', 'blocked', 'cancelled', 'waived', 'superseded'}
                                and self.branch_id(item)
                            }
                            if terminal_progress_ids:
                                for key in ('active_branches', 'pending_branches'):
                                    latest_late_fill[key] = [
                                        dict(branch)
                                        for branch in self.normalize_late_fill_branches(latest_late_fill.get(key))
                                        if self.branch_id(branch) not in terminal_progress_ids
                                    ]
                            latest_late_fill['branch_progress'] = branch_progress
                            updated_payload = dict(latest_payload)
                            updated_payload = self.attach_late_fill_state(updated_payload, latest_late_fill)
                        with callback_trace.span('callback.publication'):
                            self.touch_response_lookup(
                                response_id,
                                output_text=str(updated_payload.get('output_text') or ''),
                                response_payload=updated_payload,
                            )

                branch_results: dict[str, dict[str, Any]] = {}
                preblocked_branch_errors: dict[str, dict[str, Any]] = {}
                executable_active_branches: list[dict[str, Any]] = []
                for branch in active_branches:
                    branch_id = self.branch_id(branch)
                    if not branch_id:
                        continue
                    repair_error = tts_semantic_regeneration.consumed_execution_error(
                        branch, current_payload,
                    ) or self.repair_branch_execution_error(
                        branch,
                        current_payload=current_payload,
                        artifact_gap=artifact_gap,
                    )
                    if repair_error:
                        preblocked_branch_errors[branch_id] = self.normalize_late_fill_error_payload(repair_error)
                        continue
                    executable_active_branches.append(branch)
                branch_errors: dict[str, dict[str, Any]] = dict(preblocked_branch_errors)
                # The response target completed the source phase; that alone
                # is not failure evidence for any downstream branch. Actual
                # retry exclusions are carried branch-locally by
                # failed_instance_id, attempt.instance_id, and explicit
                # excluded_instance_ids.
                failed_instance_id = None
                runtime_candidate_snapshot: list[dict[str, Any]] = []
                runtime_candidate_snapshot_meta: dict[str, Any] = {}
                if using_default_prepare_plan and executable_active_branches:
                    runtime_candidate_snapshot, runtime_candidate_snapshot_meta = (
                        self.runtime_candidate_snapshot_for_late_fill_wave()
                    )
                branch_specs = [
                    branch_spec
                    for branch_spec in (
                        self.build_late_fill_materialization_branch_spec(
                            branch=dict(branch),
                            artifact_gap=artifact_gap,
                            current_payload=current_payload,
                            request_payload=request_payload,
                            assistant_message=assistant_message,
                            source_route_payload=source_route_payload,
                            failed_instance_id=failed_instance_id,
                            **({"guarded_pending": True} if guarded_pending else {}),
                        )
                        for branch in executable_active_branches
                    )
                    if isinstance(branch_spec, dict)
                ]
                if runtime_candidate_snapshot:
                    for branch_spec in branch_specs:
                        prepare_args = (
                            dict(branch_spec.get('prepare_args') or {})
                            if isinstance(branch_spec.get('prepare_args'), Mapping)
                            else {}
                        )
                        branch_gap = (
                            dict(prepare_args.get('artifact_gap') or {})
                            if isinstance(prepare_args.get('artifact_gap'), Mapping)
                            else {}
                        )
                        branch_gap['_runtime_candidate_snapshot'] = [
                            dict(entry)
                            for entry in runtime_candidate_snapshot
                            if isinstance(entry, Mapping)
                        ]
                        branch_gap['_runtime_candidate_snapshot_meta'] = dict(runtime_candidate_snapshot_meta)
                        prepare_args['artifact_gap'] = branch_gap
                        branch_spec['prepare_args'] = prepare_args
                prefulfilled_text_branch_ids: set[str] = set()
                executable_branch_specs_for_wave: list[dict[str, Any]] = []
                latest_record_for_preflight = self.get_response_lookup_record(response_id) or {}
                latest_payload_for_preflight = (
                    latest_record_for_preflight.get('response_payload')
                    if isinstance(latest_record_for_preflight.get('response_payload'), Mapping)
                    else {}
                )
                for branch_spec in branch_specs:
                    branch = (
                        dict(branch_spec.get('branch'))
                        if isinstance(branch_spec.get('branch'), Mapping)
                        else {}
                    )
                    prepare_args = (
                        dict(branch_spec.get('prepare_args') or {})
                        if isinstance(branch_spec.get('prepare_args'), Mapping)
                        else {}
                    )
                    branch_gap = (
                        dict(prepare_args.get('artifact_gap') or {})
                        if isinstance(prepare_args.get('artifact_gap'), Mapping)
                        else {}
                    )
                    evidence_branch = dict(branch)
                    for key in (
                        'branch_id',
                        'phase_id',
                        'capability',
                        'output_type',
                        'stage_direction',
                        'requires_artifact',
                        'text_artifact_extension',
                        'text_artifact_source_name',
                        'text_artifact_source',
                        'text_artifact_target_path',
                        'artifact_request',
                    ):
                        value = evidence_branch.get(key)
                        if value in (None, '', [], {}):
                            value = branch_gap.get(key)
                        if value in (None, '', [], {}):
                            value = branch_spec.get(key)
                        if value not in (None, '', [], {}):
                            evidence_branch[key] = value
                    canonical_fulfillment = self.text_artifact_result_evidence._canonical_text_artifact_branch_fulfillment(
                        evidence_branch,
                        current_payload,
                        latest_payload_for_preflight,
                        allow_deterministic_repair=True,
                    )
                    branch_id = str(canonical_fulfillment.get('branch_id') or '').strip()
                    if not canonical_fulfillment or not branch_id:
                        executable_branch_specs_for_wave.append(branch_spec)
                        continue
                    prefulfilled_text_branch_ids.add(branch_id)
                    text_source = str(
                        canonical_fulfillment.get('text_artifact_source')
                        or 'canonical_text_artifact_evidence'
                    ).strip() or 'canonical_text_artifact_evidence'
                    fulfilled_branch = dict(evidence_branch)
                    fulfilled_branch['status'] = 'fulfilled'
                    fulfilled_branch['evidence'] = text_source
                    fulfilled_branch['non_blocking_after_final_contract_fulfilled'] = True
                    _remember_branch(
                        completed_branch_records,
                        completed_branches,
                        fulfilled_branch,
                        status='fulfilled',
                    )
                    failed_branch_records = [
                        record
                        for record in failed_branch_records
                        if self.branch_id(record) != branch_id
                    ]
                    failed_branches = [
                        item
                        for item in failed_branches
                        if item != branch_id
                    ]
                    branch_errors.pop(branch_id, None)
                    if not any(
                        self.branch_id(item) == branch_id
                        and str(item.get('saved_text_path') or '').strip()
                        == str(canonical_fulfillment.get('saved_text_path') or '').strip()
                        for item in fill_results
                        if isinstance(item, Mapping)
                    ):
                        fill_results.append(dict(canonical_fulfillment))
                    self.log_unified_event(
                        category='responses',
                        action='late_fill',
                        status='ok',
                        response_id=response_id,
                        capability=str(canonical_fulfillment.get('capability') or 'chat'),
                        message=(
                            'Required text artifact satisfied by deterministic canonical saved file repair.'
                            if text_source == 'canonical_text_artifact_deterministic_syntax_repair'
                            else 'Required text artifact satisfied by canonical saved file evidence.'
                        ),
                    )
                if prefulfilled_text_branch_ids:
                    active_branches = [
                        dict(branch)
                        for branch in active_branches
                        if self.branch_id(branch) not in prefulfilled_text_branch_ids
                    ]
                branch_specs = executable_branch_specs_for_wave
                branch_specs = self._coalesce_required_text_artifact_branch_specs(branch_specs)
                if branch_specs:
                    if pending_continuation is not None:
                        with self.response_mutation(response_id):
                            dispatch_payload = (self.get_response_lookup_record(response_id) or {}).get('response_payload') or {}
                            require_response_mutation_base(current_payload, dispatch_payload)
                            if guarded_pending:
                                self._require_pending_continuation(pending_continuation, dispatch_payload)
                                if not all(self._pending_branch_prerequisites(b, dispatch_payload, pending_continuation)
                                           for b in executable_active_branches):
                                    self._park_pending_continuation(pending_continuation, pending_branches, request_payload)
                                    return
                            pending_continuation.chain.submitted.update(self.branch_id(b) for b in executable_active_branches)
                            pending_continuation.wave_active = True
                    materialization_result = self.execute_materialization_branches(
                        branch_specs,
                        prepare_branch_plan=prepare_plan,
                        execute_prepared_branch=execute_plan,
                        on_branch_progress=publish_live_branch_progress,
                        async_branch_progress=True,
                    )
                    materialization_result = (
                        self._retry_failed_coalesced_text_artifact_materializations(
                            branch_specs,
                            materialization_result,
                            prepare_branch_plan=prepare_plan,
                            execute_prepared_branch=execute_plan,
                            on_branch_progress=publish_live_branch_progress,
                        )
                    )
                else:
                    materialization_result = {
                        'branch_results': {},
                        'branch_errors': {},
                        'prepared_branch_plans': [],
                        'concurrency_policy': {},
                    }
                if pending_continuation is not None:
                    # The materialization owner drains asynchronous callbacks before returning.
                    pending_continuation.wave_active = False
                if guarded_pending:
                    with self.response_mutation(response_id):
                        acceptance_payload = (self.get_response_lookup_record(response_id) or {}).get('response_payload') or {}
                        self._require_pending_continuation(pending_continuation, acceptance_payload)
                        if not all(self._pending_branch_prerequisites(b, acceptance_payload, pending_continuation)
                                   for b in executable_active_branches):
                            self._park_pending_continuation(pending_continuation, pending_branches, request_payload)
                            return
                materialization_concurrency_policy = (
                    dict(materialization_result.get('concurrency_policy'))
                    if isinstance(materialization_result.get('concurrency_policy'), Mapping)
                    else {}
                )
                materialization_concurrency_history = [
                    dict(item)
                    for item in (
                        (
                            (current_payload.get('late_fill') or {}).get(
                                'materialization_concurrency_history'
                            )
                            or []
                        )
                        if isinstance(current_payload.get('late_fill'), Mapping)
                        else []
                    )
                    if isinstance(item, Mapping)
                ]
                concurrency_policies = (
                    materialization_result.get(
                        'materialization_concurrency_policies'
                    )
                    if isinstance(
                        materialization_result.get(
                            'materialization_concurrency_policies'
                        ),
                        list,
                    )
                    else [materialization_concurrency_policy]
                )
                for concurrency_policy in concurrency_policies:
                    if not isinstance(concurrency_policy, Mapping) or not concurrency_policy:
                        continue
                    materialization_concurrency_history = (
                        self.materialization_concurrency_history(
                            {
                                'materialization_concurrency_history': (
                                    materialization_concurrency_history
                                )
                            },
                            concurrency_policy,
                        )
                    )
                branch_results = {
                    str(branch_id or '').strip(): result
                    for branch_id, result in (
                        (materialization_result.get('branch_results') or {}).items()
                        if isinstance(materialization_result.get('branch_results'), dict)
                        else []
                    )
                    if str(branch_id or '').strip() and isinstance(result, dict)
                }
                materialization_branch_errors = {
                    str(branch_id or '').strip(): self.normalize_late_fill_error_payload(error)
                    for branch_id, error in (
                        (materialization_result.get('branch_errors') or {}).items()
                        if isinstance(materialization_result.get('branch_errors'), dict)
                        else []
                    )
                    if str(branch_id or '').strip() and error
                }
                branch_errors.update(materialization_branch_errors)
                prepared_plans_by_branch_id = {
                    str((plan or {}).get('branch_id') or '').strip(): dict(plan)
                    for plan in (
                        materialization_result.get('prepared_branch_plans') or []
                        if isinstance(materialization_result.get('prepared_branch_plans'), list)
                        else []
                    )
                    if isinstance(plan, dict) and str((plan or {}).get('branch_id') or '').strip()
                }
                retry_branch_replacements: dict[str, dict[str, Any]] = {}

                for branch in active_branches:
                    branch_id = self.branch_id(branch)
                    capability = self.branch_capability(branch)
                    if not branch_id or not capability:
                        continue
                    latest_record = self.get_response_lookup_record(response_id) or {}
                    latest_payload = latest_record.get('response_payload') if isinstance(latest_record.get('response_payload'), dict) else None
                    gate_payload = current_payload
                    if latest_payload:
                        gate_payload = latest_payload
                        latest_late_fill = latest_payload.get('late_fill') if isinstance(latest_payload.get('late_fill'), dict) else {}
                        cancelled_branch_records = self.normalize_late_fill_branches(latest_late_fill.get('cancelled_branches'))
                        cancelled_branches = [self.branch_id(item) for item in cancelled_branch_records if self.branch_id(item)]
                    post_execution_decision = self.semantic_execution_gate_decision(branch, gate_payload)
                    if str(post_execution_decision.get('action') or '').strip().lower() == 'skip':
                        trace.result_ignored(branch, post_execution_decision)
                        gated_branch = self.branch_record_with_execution_gate(branch, post_execution_decision)
                        _remember_branch(
                            cancelled_branch_records,
                            cancelled_branches,
                            gated_branch,
                            status=str(gated_branch.get('status') or post_execution_decision.get('status') or 'cancelled'),
                        )
                        self.log_unified_event(
                            category='responses',
                            action='late_fill',
                            status=str(gated_branch.get('status') or 'cancelled'),
                            response_id=response_id,
                            capability=capability,
                            message=str(post_execution_decision.get('reason') or 'Late-fill result ignored by semantic execution gate.'),
                        )
                        continue
                    branch_result = branch_results.get(branch_id)
                    if not branch_result:
                        canonical_fulfillment: dict[str, Any] = {}
                        if not text_artifact_materialization._text_artifact_revision_required(branch):
                            canonical_fulfillment = self.text_artifact_result_evidence._canonical_text_artifact_branch_fulfillment(
                                branch,
                                current_payload,
                                latest_payload or {},
                                allow_deterministic_repair=True,
                            )
                        canonical_text_path = str(
                            canonical_fulfillment.get('saved_text_path') or ''
                        ).strip()
                        if canonical_text_path:
                            text_source = str(
                                canonical_fulfillment.get('text_artifact_source')
                                or 'canonical_text_artifact_evidence'
                            ).strip()
                            if not text_source:
                                text_source = 'canonical_text_artifact_evidence'
                            event_message = (
                                'Required text artifact satisfied by deterministic canonical saved file repair.'
                                if text_source == 'canonical_text_artifact_deterministic_syntax_repair'
                                else 'Required text artifact satisfied by canonical saved file evidence.'
                            )
                            fulfilled_branch = dict(branch)
                            fulfilled_branch['status'] = 'fulfilled'
                            fulfilled_branch['evidence'] = text_source
                            fulfilled_branch['non_blocking_after_final_contract_fulfilled'] = True
                            _remember_branch(
                                completed_branch_records,
                                completed_branches,
                                fulfilled_branch,
                                status='fulfilled',
                            )
                            failed_branch_records = [
                                record
                                for record in failed_branch_records
                                if self.branch_id(record) != branch_id
                            ]
                            failed_branches = [
                                item
                                for item in failed_branches
                                if item != branch_id
                            ]
                            branch_errors.pop(branch_id, None)
                            if not any(
                                isinstance(item, Mapping)
                                and self.branch_id(item) == branch_id
                                and str(item.get('saved_text_path') or '').strip() == canonical_text_path
                                for item in fill_results
                            ):
                                fill_results.append(dict(canonical_fulfillment))
                            self.log_unified_event(
                                category='responses',
                                action='late_fill',
                                status='ok',
                                response_id=response_id,
                                capability=capability,
                                message=event_message,
                            )
                            continue
                        error_payload = branch_errors.get(branch_id) or self.normalize_late_fill_error_payload(None)
                        plan = prepared_plans_by_branch_id.get(branch_id) or {}
                        binding = plan.get('vision_dependency_binding') or {}
                        if (binding and error_payload.get('stage') == 'execute_prepared_branch'
                                and error_payload.get('retryable') is True
                                and error_payload.get('code') in {'BACKEND_ERROR', 'BACKEND_TIMEOUT', 'INSTANCE_UNAVAILABLE'}
                                and self._vision_image_snapshot((plan.get('infer_payload') or {}).get('file_path')) == binding.get('artifact')
                                and (error_payload.get('status_code') in {408, 429, 500, 502, 503, 504}
                                     or error_payload.get('code') in {'BACKEND_TIMEOUT', 'INSTANCE_UNAVAILABLE'})):
                            error_payload = {**error_payload, 'vision_backend_failure': {
                                **copy.deepcopy(binding), 'error': copy.deepcopy(error_payload)}}
                        attempt_payload = self.late_fill_failure_attempt(
                            branch,
                            error_payload,
                            prepared_plans_by_branch_id.get(branch_id),
                        )
                        recovery_context = self.late_fill_recovery_context(
                            error=error_payload,
                            attempt=attempt_payload,
                        )
                        waiting_branch = self.build_availability_wait_branch(branch, error=error_payload)
                        if waiting_branch:
                            retry_branch_replacements[branch_id] = waiting_branch
                            branch_errors.pop(branch_id, None)
                            self.log_unified_event(
                                category='responses', action='late_fill', status='waiting',
                                response_id=response_id, capability=capability,
                                message='Artifact work is waiting for a compatible live instance to leave cooldown.',
                            )
                            continue
                        recovery_state = self.late_fill_recovery_state(
                            branch,
                            recovery_context=recovery_context,
                            attempt=attempt_payload,
                            status='candidate',
                        )
                        retry_branch = self.build_auto_executable_repair_retry_branch(
                            branch,
                            recovery_context=recovery_context,
                            recovery_state=recovery_state,
                            attempt=attempt_payload,
                            trigger='auto_executable_repair_retry',
                        )
                        if retry_branch:
                            retry_branch_replacements[branch_id] = retry_branch
                            branch_errors.pop(branch_id, None)
                            trace.repair_requeued(
                                self.log_unified_event, branch_id, branch.get('phase_id'),
                                capability, attempt_payload, reason='failed_materialization',
                            )
                            continue
                        _remember_branch(
                            failed_branch_records,
                            failed_branches,
                            branch,
                            status='failed',
                            error=error_payload,
                            attempt=attempt_payload,
                            recovery_context=recovery_context,
                            recovery_state=recovery_state,
                        )
                        self.log_unified_event(
                            category='responses',
                            action='late_fill',
                            status='failed',
                            response_id=response_id,
                            capability=capability,
                            message=str(error_payload.get('message') or 'Late fill request failed.'),
                        )
                        continue

                    late_fill_route_info = branch_result.get('route_info') if isinstance(branch_result.get('route_info'), dict) else {}
                    late_fill_instance = branch_result.get('instance') if isinstance(branch_result.get('instance'), dict) else {}
                    infer_result = branch_result.get('infer_result') if isinstance(branch_result.get('infer_result'), dict) else {}
                    effective_data = branch_result.get('effective_data') if isinstance(branch_result.get('effective_data'), dict) else {}
                    execution_contract = (
                        branch_result.get('execution_contract')
                        if isinstance(branch_result.get('execution_contract'), dict)
                        else (
                            infer_result.get('execution_contract')
                            if isinstance(infer_result.get('execution_contract'), dict)
                            else (
                                effective_data.get('execution_contract')
                                if isinstance(effective_data.get('execution_contract'), dict)
                                else {}
                            )
                        )
                    )
                    external_provider_block = (
                        infer_result.get('external_provider_block')
                        if isinstance(
                            infer_result.get('external_provider_block'),
                            Mapping,
                        )
                        else {}
                    )
                    if external_provider_block:
                        error_payload = self.normalize_late_fill_error_payload(
                            {
                                'code': 'EXTERNAL_PROVIDER_BLOCKED',
                                'message': str(
                                    external_provider_block.get('reason')
                                    or 'The downstream provider blocked the '
                                    'bounded graph-owned chat phase.'
                                ).strip(),
                                'stage': 'external_chat_phase',
                                'retryable': False,
                                'external_execution': dict(
                                    infer_result.get('external_execution') or {}
                                ),
                            }
                        )
                        attempt_payload = self.late_fill_failure_attempt(
                            branch,
                            error_payload,
                            prepared_plans_by_branch_id.get(branch_id),
                        )
                        recovery_context = self.late_fill_recovery_context(
                            error=error_payload,
                            attempt=attempt_payload,
                        )
                        recovery_state = self.late_fill_recovery_state(
                            branch,
                            recovery_context=recovery_context,
                            attempt=attempt_payload,
                            status='blocked',
                            trigger='external_provider_block',
                        )
                        _remember_branch(
                            failed_branch_records,
                            failed_branches,
                            branch,
                            status='blocked',
                            error=error_payload,
                            attempt=attempt_payload,
                            recovery_context=recovery_context,
                            recovery_state=recovery_state,
                        )
                        self.log_unified_event(
                            category='responses',
                            action='late_fill',
                            status='blocked',
                            response_id=response_id,
                            capability=capability,
                            message=str(error_payload.get('message') or ''),
                        )
                        continue
                    if (
                        capability == self.capability_image_generation
                        and not str(infer_result.get('saved_image_path') or effective_data.get('saved_image_path') or '').strip()
                        and _payload_has_raw_image_result(infer_result)
                    ):
                        infer_result = self.persist_raw_image_result_if_possible(
                            infer_result,
                            effective_data=effective_data,
                            late_fill_instance=late_fill_instance,
                        )
                    if capability == self.capability_text_to_speech:
                        integrity_evidence = (
                            self.tts_result_evidence.tts_audio_integrity_evidence_for_branch_result(
                                branch,
                                infer_result,
                            )
                        )
                        if integrity_evidence:
                            infer_result = dict(infer_result)
                            infer_result['tts_audio_integrity_evidence'] = (
                                integrity_evidence
                            )
                    tts_stt_semantic_evidence = (
                        self.tts_result_evidence.tts_stt_semantic_evidence_for_branch_result(
                            branch,
                            infer_result,
                            current_payload=current_payload,
                        )
                    )
                    if str(
                        tts_stt_semantic_evidence.get('status') or ''
                    ).strip().lower() != 'not_applicable':
                        infer_result = dict(infer_result)
                        infer_result['tts_stt_semantic_evidence'] = (
                            tts_stt_semantic_evidence
                        )
                    if tts_stt_semantic_evidence.get('status') == 'mismatched':
                        repair_payload = copy.deepcopy(current_payload)
                        repair_payload.setdefault('late_fill', {}).update(
                            fill_results=copy.deepcopy(fill_results),
                            completed_branches=copy.deepcopy(completed_branch_records),
                            failed_branches=copy.deepcopy(failed_branch_records),
                            pending_branches=copy.deepcopy(pending_branches),
                        )
                        repair_outcome = tts_semantic_regeneration.run(
                            self, branch=branch, result=infer_result,
                            payload=repair_payload,
                            consumer_plan=prepared_plans_by_branch_id.get(branch_id) or {},
                            request_payload=request_payload, artifact_gap=artifact_gap,
                            source_route_payload=source_route_payload,
                            prepare_plan=prepare_plan, execute_plan=execute_plan,
                        )
                        if repair_outcome:
                            current_payload = repair_outcome['payload']
                            infer_result = repair_outcome['infer_result']
                            updated_late_fill = current_payload['late_fill']
                            fill_results = list(updated_late_fill.get('fill_results') or [])
                            completed_branch_records = list(updated_late_fill.get('completed_branches') or [])
                            failed_branch_records = list(updated_late_fill.get('failed_branches') or [])
                            completed_branches = [self.branch_id(r) for r in completed_branch_records]
                            failed_branches = [self.branch_id(r) for r in failed_branch_records]
                    evidence_error = self.dependency_evidence_error_for_branch_result(
                        branch,
                        infer_result,
                        current_payload=current_payload,
                    )
                    if evidence_error:
                        error_payload = self.normalize_late_fill_error_payload(evidence_error)
                        attempt_payload = self.late_fill_failure_attempt(
                            branch,
                            error_payload,
                            prepared_plans_by_branch_id.get(branch_id),
                        )
                        recovery_context = self.late_fill_recovery_context(
                            error=error_payload,
                            attempt=attempt_payload,
                        )
                        recovery_state = self.late_fill_recovery_state(
                            branch,
                            recovery_context=recovery_context,
                            attempt=attempt_payload,
                            status='candidate',
                            trigger='semantic_evidence_gate',
                        )
                        retry_branch = (
                            self.build_auto_executable_repair_retry_branch(
                                branch,
                                recovery_context=recovery_context,
                                recovery_state=recovery_state,
                                attempt=attempt_payload,
                                trigger=(
                                    _TTS_AUTO_RECOVERY_TRIGGER
                                ),
                            )
                        )
                        if retry_branch:
                            retry_branch_replacements[branch_id] = retry_branch
                            branch_errors.pop(branch_id, None)
                            vision_recovery = capability == 'vision_analysis'
                            self.log_unified_event(
                                category='responses',
                                action='late_fill',
                                status='queued',
                                response_id=response_id,
                                capability=capability,
                                recovery_policy_id=(
                                    _VISION_EVIDENCE_RECOVERY_POLICY_ID if vision_recovery
                                    else _TTS_AUTO_RECOVERY_POLICY_ID
                                ),
                                message=(
                                    'Vision branch requeued for one bounded evidence recovery on an alternate instance.'
                                    if vision_recovery else
                                    'Required TTS branch requeued for one bounded integrity recovery attempt.'
                                ),
                            )
                            continue
                        _remember_branch(
                            failed_branch_records,
                            failed_branches,
                            branch,
                            status='blocked',
                            error=error_payload,
                            attempt=attempt_payload,
                            recovery_context=recovery_context,
                            recovery_state=recovery_state,
                        )
                        self.log_unified_event(
                            category='responses',
                            action='late_fill',
                            status='blocked',
                            response_id=response_id,
                            capability=capability,
                            message=str(error_payload.get('message') or 'Dependency evidence repair required.'),
                        )
                        continue
                    infer_result, text_artifact_error = self._ensure_required_text_artifact_saved_truth(
                        branch,
                        infer_result,
                        effective_data,
                        current_payload,
                    )
                    if text_artifact_error:
                        error_payload = self.normalize_late_fill_error_payload(text_artifact_error)
                        attempt_payload = self.late_fill_failure_attempt(
                            branch,
                            error_payload,
                            prepared_plans_by_branch_id.get(branch_id),
                        )
                        if not str(attempt_payload.get('instance_id') or '').strip():
                            attempt_payload = self.late_fill_failure_attempt(
                                branch,
                                error_payload,
                                {
                                    'route_info': late_fill_route_info,
                                    'instance': late_fill_instance,
                                },
                            )
                        recovery_context = self.late_fill_recovery_context(
                            error=error_payload,
                            attempt=attempt_payload,
                        )
                        recovery_state = self.late_fill_recovery_state(
                            branch,
                            recovery_context=recovery_context,
                            attempt=attempt_payload,
                            status='candidate',
                            trigger='text_artifact_saved_truth_gate',
                        )
                        retry_branch = self.build_auto_executable_repair_retry_branch(
                            branch,
                            recovery_context=recovery_context,
                            recovery_state=recovery_state,
                            attempt=attempt_payload,
                            trigger='auto_executable_repair_retry',
                        )
                        if retry_branch:
                            retry_branch_replacements[branch_id] = retry_branch
                            branch_errors.pop(branch_id, None)
                            trace.repair_requeued(
                                self.log_unified_event, branch_id, branch.get('phase_id'),
                                capability, attempt_payload, reason='saved_truth_failure',
                            )
                            continue
                        _remember_branch(
                            failed_branch_records,
                            failed_branches,
                            branch,
                            status='failed',
                            error=error_payload,
                            attempt=attempt_payload,
                            recovery_context=recovery_context,
                            recovery_state=recovery_state,
                        )
                        self.log_unified_event(
                            category='responses',
                            action='late_fill',
                            status='failed',
                            response_id=response_id,
                            capability=capability,
                            message=str(error_payload.get('message') or 'Text artifact saved truth required.'),
                        )
                        continue
                    current_payload = self.branch_dependency_evidence.merge_late_fill_result_fields(current_payload, infer_result)
                    _remember_branch(completed_branch_records, completed_branches, branch, status='fulfilled')
                    last_effective_request_payload = effective_data or last_effective_request_payload
                    semantic_review_branch = self._is_semantic_review_branch(
                        branch,
                        effective_data,
                        execution_contract,
                        infer_result,
                    )
                    fill_record = {
                        'branch_id': branch_id,
                        'phase_id': str(branch.get('phase_id') or branch_id).strip() or branch_id,
                        'capability': capability,
                        'fill_instance_id': str((late_fill_route_info or {}).get('instance_id') or '').strip() or None,
                        'fill_model': str((late_fill_instance or {}).get('model') or '').strip() or None,
                        'fill_backend': str((late_fill_instance or {}).get('backend') or '').strip() or None,
                        'fill_mode': str((infer_result or {}).get('mode') or '').strip() or None,
                        'route_source': str((late_fill_route_info or {}).get('route_source') or '').strip() or None,
                        'route_reason': str((late_fill_route_info or {}).get('route_reason') or '').strip() or None,
                    }
                    if semantic_review_branch:
                        fill_record['visibility'] = 'internal'
                        fill_record['surface_role'] = 'closure_evidence'
                    late_fill_route_runtime = (
                        late_fill_route_info.get('route_runtime')
                        if isinstance(
                            late_fill_route_info.get('route_runtime'),
                            Mapping,
                        )
                        else {}
                    )
                    for key in (
                        'selection_policy',
                        'excluded_instance_ids',
                        'excluded_candidate_count',
                        'candidate_diagnostics',
                        'tts_recovery_trigger',
                        'tts_recovery_policy_id',
                        'excluded_instance_reuse_reason',
                        'excluded_instance_reuse_instance_id',
                        'excluded_instance_reuse_recovery_trigger',
                        'excluded_reuse_policy_id',
                        'external_execution',
                    ):
                        value = late_fill_route_runtime.get(key)
                        if value not in (None, '', [], {}):
                            fill_record[key] = value
                    if capability == self.capability_text_to_speech:
                        generation_request = tts_semantic_regeneration.request_snapshot(
                            prepared_plans_by_branch_id.get(branch_id) or {}, infer_result,
                        )
                        if generation_request:
                            fill_record['tts_generation_request'] = generation_request
                    if isinstance(branch.get('recovery_attempt'), Mapping):
                        fill_record['recovery_attempt'] = dict(
                            branch.get('recovery_attempt') or {}
                        )
                    if execution_contract:
                        fill_record_contract = dict(execution_contract)
                        if semantic_review_branch:
                            fill_record_contract['visibility'] = 'internal'
                            fill_record_contract['surface_role'] = 'closure_evidence'
                        fill_record['execution_contract'] = fill_record_contract
                        workload_task_ref = (
                            execution_contract.get('workload_task_ref')
                            if isinstance(execution_contract.get('workload_task_ref'), Mapping)
                            else {}
                        )
                        output_obligation_ref = (
                            execution_contract.get('output_obligation_ref')
                            if isinstance(execution_contract.get('output_obligation_ref'), Mapping)
                            else {}
                        )
                        if workload_task_ref:
                            fill_record['workload_task_ref'] = dict(workload_task_ref)
                            task_id = str(workload_task_ref.get('task_id') or '').strip()
                            if task_id:
                                fill_record['task_id'] = task_id
                                fill_record['workload_task_id'] = task_id
                        if output_obligation_ref:
                            fill_record['output_obligation_ref'] = dict(output_obligation_ref)
                            obligation_id = str(output_obligation_ref.get('obligation_id') or '').strip()
                            if obligation_id:
                                fill_record['obligation_id'] = obligation_id
                        execution_artifact_request = (
                            execution_contract.get('artifact_request')
                            if isinstance(execution_contract.get('artifact_request'), Mapping)
                            else {}
                        )
                        for key in (
                            'artifact_request',
                            'text_artifact_extension',
                            'text_artifact_source_name',
                            'text_artifact_source',
                            'text_artifact_target_path',
                        ):
                            value = branch.get(key)
                            if value in (None, '', [], {}):
                                value = execution_contract.get(key)
                            if (
                                value in (None, '', [], {})
                                and key == 'text_artifact_extension'
                                and execution_artifact_request
                            ):
                                value = execution_artifact_request.get('extension')
                            if (
                                value in (None, '', [], {})
                                and key == 'text_artifact_source_name'
                                and execution_artifact_request
                            ):
                                value = execution_artifact_request.get('source_name')
                            if (
                                value in (None, '', [], {})
                                and key == 'text_artifact_source'
                                and execution_artifact_request
                            ):
                                value = execution_artifact_request.get('source')
                            if (
                                value in (None, '', [], {})
                                and key == 'text_artifact_target_path'
                                and execution_artifact_request
                            ):
                                value = execution_artifact_request.get('target_path')
                            if value not in (None, '', [], {}):
                                fill_record[key] = value
                    result_text = branch_result_contracts.late_fill_text_from_result_payload(infer_result)
                    review_binding = infer_result.get('semantic_review_evidence_binding') or {}
                    if (isinstance(review_binding, Mapping)
                            and review_binding.get('content_requirement_policy') == 'named_saved_text_v1'):
                        # Only a dispatched, digest-checked result is completion
                        # evidence. The queued instruction is never a verdict.
                        fill_record['semantic_review_evidence_binding'] = dict(review_binding)
                    audio_input_evidence = infer_result.get('audio_reference_input_evidence')
                    if (isinstance(audio_input_evidence, Mapping)
                            and audio_input_evidence.get('authority') == 'canonical_direct_audio_dependency'):
                        fill_record['audio_reference_input_evidence'] = dict(audio_input_evidence)
                    result_artifact_type = self.artifact_type_for_capability(capability)
                    if result_text:
                        fill_record['result_text'] = result_text
                        if result_artifact_type == 'text':
                            fill_record['content_payload'] = result_text
                            fill_record['content_payload_source'] = 'late_fill_infer_result'
                    for key in (
                        'saved_file_output_snapshot',
                        'report_delivery_evidence',
                        'vision_input_evidence',
                        'saved_file_consumption_evidence',
                        'saved_text_path',
                        'saved_text_artifacts',
                        'text_artifact_requests',
                        'coalesced_text_artifact_recovery',
                        'text_artifact_revision_required',
                        'text_artifact_source_is_input',
                        'text_artifact_revision_write_proof',
                        'text_artifact_revision_preservation_evidence',
                        'saved_audio_path',
                        'saved_image_path',
                        'image_data_url',
                        'image_artifact_persisted_from_raw_late_fill',
                        'result',
                        'audio_mimetype',
                        'lang_code',
                        'lang_code_source',
                        'voice',
                        'instruct',
                        'response_format',
                        'output_format',
                        'speed',
                        'pitch',
                        'tts_semantic_source',
                        'tts_generation_budget',
                        'tts_sampling_profile',
                        'tts_audio_integrity_evidence',
                        'tts_stt_semantic_evidence',
                    ):
                        if semantic_review_branch and key in _BRANCH_LOCAL_PUBLICATION_FIELDS:
                            continue
                        value = infer_result.get(key)
                        if value in (None, '', [], {}):
                            value = effective_data.get(key)
                        if value not in (None, '', [], {}):
                            fill_record[key] = value
                    for key in (
                        'artifact_id',
                        'artifact_ref',
                        'ref',
                        'provenance_id',
                        'derived_from',
                        'artifacts',
                    ):
                        if semantic_review_branch and key in _BRANCH_LOCAL_PUBLICATION_FIELDS:
                            continue
                        value = infer_result.get(key)
                        if value not in (None, '', [], {}):
                            fill_record[key] = value
                    fill_record = self.branch_dependency_evidence.attach_late_fill_result_artifact_identity(
                        fill_record,
                        current_payload,
                        infer_result,
                        capability=capability,
                    )
                    fill_results.append(
                        {
                            key: value
                            for key, value in fill_record.items()
                            if value not in (None, '', [], {})
                        }
                    )
                    self.log_unified_event(
                        category='responses',
                        action='late_fill',
                        status='ok',
                        instance_id=str((late_fill_route_info or {}).get('instance_id') or '').strip() or None,
                        model=str((late_fill_instance or {}).get('model') or '').strip() or None,
                        backend=str((late_fill_instance or {}).get('backend') or '').strip() or None,
                        capability=capability,
                        response_id=response_id,
                        message='Late artifact fill completed.',
                    )

                completed_branch_ids = set(completed_branches)
                failed_branch_ids = set(failed_branches)
                cancelled_branch_ids = set(cancelled_branches)
                next_pending_branches: list[dict[str, Any]] = []
                for branch in pending_branches:
                    pending_branch_id = self.branch_id(branch)
                    if (
                        pending_branch_id in completed_branch_ids
                        or pending_branch_id in failed_branch_ids
                        or pending_branch_id in cancelled_branch_ids
                    ):
                        continue
                    if pending_branch_id and pending_branch_id in retry_branch_replacements:
                        next_pending_branches.append(dict(retry_branch_replacements[pending_branch_id]))
                    else:
                        next_pending_branches.append(dict(branch))
                pending_branches = next_pending_branches
                pending_capabilities, completed_capabilities, failed_capabilities = _capability_lists_for_branch_state(
                    pending_branches
                )
                cancelled_capabilities = _cancelled_capability_list()
                next_batches = self.downstream_request_phase_batches(
                    request_phase_graph,
                    pending_branches=pending_branches,
                    completed_branches=completed_branch_records,
                    failed_branches=failed_branch_records,
                    pending_capabilities=pending_capabilities,
                    completed_capabilities=completed_capabilities,
                    failed_capabilities=failed_capabilities,
                )
                next_active_branches = [dict(branch) for branch in (next_batches[0] if next_batches else [])]
                if not next_active_branches and pending_branches and not guarded_pending:
                    next_active_branches = [dict(pending_branches[0])]
                next_pending_branch_by_id = {
                    self.branch_id(branch): dict(branch)
                    for branch in pending_branches
                    if self.branch_id(branch)
                }
                next_active_branches = [
                    self.overlay_graph_branch_with_runtime_state(
                        branch,
                        next_pending_branch_by_id.get(self.branch_id(branch)),
                    )
                    for branch in next_active_branches
                ]
                if guarded_pending:
                    next_active_branches = [b for b in next_active_branches
                                            if self.branch_id(b) in pending_continuation.scope]
                next_active_branches, next_scheduling_policy = self.select_active_late_fill_branches(
                    next_active_branches,
                    artifact_gap=artifact_gap,
                )
                next_active_capabilities = self.normalize_capability_list(
                    [self.branch_capability(branch) for branch in next_active_branches if self.branch_capability(branch)]
                )
                next_active_capability = (
                    self.branch_capability(next_active_branches[0]) if next_active_branches else None
                ) or (next_active_capabilities[0] if next_active_capabilities else None)
                next_gap = build_gap(
                    artifact_gap,
                    capability=next_active_capability or active_capability,
                    artifact_payload=current_payload,
                    pending_capabilities=pending_capabilities,
                    completed_capabilities=completed_capabilities,
                    failed_capabilities=failed_capabilities,
                )
                next_status = _status_for_terminal_state(pending_branches)
                next_state_extra = {
                    'pending_capabilities': pending_capabilities,
                    'completed_capabilities': completed_capabilities,
                    'failed_capabilities': failed_capabilities,
                    'cancelled_capabilities': cancelled_capabilities,
                    'active_capability': next_active_capability or active_capability,
                    'active_capabilities': next_active_capabilities,
                    'pending_branches': pending_branches,
                    'completed_branches': completed_branch_records,
                    'failed_branches': failed_branch_records,
                    'cancelled_branches': cancelled_branch_records,
                    'active_branches': next_active_branches,
                    'scheduling_policy': next_scheduling_policy,
                    'fill_results': fill_results,
                    'completed_branch_count': len(completed_branch_records),
                    'failed_branch_count': len(failed_branch_records),
                    'cancelled_branch_count': len(cancelled_branch_records),
                }
                if materialization_concurrency_policy:
                    next_state_extra['materialization_concurrency_policy'] = materialization_concurrency_policy
                if materialization_concurrency_history:
                    next_state_extra['materialization_concurrency_history'] = materialization_concurrency_history
                cohort_recovery_history = [
                    dict(item)
                    for item in (
                        materialization_result.get(
                            'coalesced_text_artifact_recovery_history'
                        )
                        or []
                    )
                    if isinstance(item, Mapping)
                ]
                if cohort_recovery_history:
                    previous_cohort_recovery_history = [
                        dict(item)
                        for item in (
                            current_late_fill.get(
                                'coalesced_text_artifact_recovery_history'
                            )
                            or []
                        )
                        if isinstance(item, Mapping)
                    ]
                    next_state_extra[
                        'coalesced_text_artifact_recovery_history'
                    ] = [
                        *previous_cohort_recovery_history,
                        *cohort_recovery_history,
                    ][-8:]
                if next_status == 'partial_failed':
                    next_state_extra['partial_failure'] = True
                recovery_candidates = [
                    dict(branch['recovery_state'])
                    for branch in failed_branch_records
                    if isinstance(branch.get('recovery_state'), Mapping)
                ]
                if recovery_candidates:
                    next_state_extra['recovery_candidates'] = recovery_candidates
                    next_state_extra['auto_recovery_enabled'] = False
                if len(fill_results) == 1:
                    next_state_extra.update(fill_results[0])
                if branch_errors and not pending_branches:
                    next_state_extra['error'] = '; '.join(
                        f'{branch_id}: {message}'
                        for branch_id, error_payload in branch_errors.items()
                        for message in [str((error_payload or {}).get('message') or '').strip()]
                        if message
                    )
                next_state = self.build_late_fill_state(
                    next_gap,
                    status=next_status,
                    prior_state=running_late_fill,
                    extra=next_state_extra,
                )
                payload_for_finalize = self.attach_late_fill_state(current_payload, next_state)
                terminal_without_pending = not pending_branches
                effective_next_status = next_status
                if terminal_without_pending:
                    payload_for_finalize, effective_next_status = self.finalize_terminal_materialization_contract(
                        payload_for_finalize,
                        request_payload=request_payload,
                        route_payload=source_route_payload,
                        artifact_gap=next_gap,
                        terminal_status=next_status,
                        accepted_fill_results=(current_payload.get('late_fill') or {}).get('fill_results') or [],
                    )
                checkpoint_mode = (
                    'terminal_full_frame'
                    if terminal_without_pending
                    else 'lightweight_nonterminal'
                )
                with self._late_fill_publication(payload_for_finalize, expected_payload=current_payload, pending_continuation=pending_continuation):
                    if terminal_without_pending:
                        finalize_started_at = trace.clock()
                        current_payload = self.finalize_response_frame_payload(
                            payload_for_finalize,
                            request_payload=request_payload,
                            persist=True,
                        )
                        finalize_elapsed_ms = trace.elapsed_ms(finalize_started_at)
                        response_frame_finalize_timing = trace.finalizer_timing(current_payload)
                    else:
                        finalize_started_at = trace.clock()
                        current_payload = dict(payload_for_finalize)
                        finalize_elapsed_ms = trace.elapsed_ms(finalize_started_at)
                        response_frame_finalize_timing = trace.checkpoint_timing(
                            finalize_elapsed_ms, checkpoint_mode,
                            pending_branch_count=len(pending_branches),
                            active_branch_count=len(next_active_branches),
                            completed_branch_count=len(completed_branch_records),
                            failed_branch_count=len(failed_branch_records),
                        )
                    current_late_fill = (
                        current_payload.get('late_fill')
                        if isinstance(current_payload.get('late_fill'), dict)
                        else next_state
                    )
                    post_wave_backend_timing = trace.post_wave_timing(
                        effective_next_status, terminal_without_pending, checkpoint_mode,
                        finalize_elapsed_ms, response_frame_finalize_timing,
                        pending_branch_count=len(pending_branches),
                        active_branch_count=len(next_active_branches),
                        completed_branch_count=len(completed_branch_records),
                        failed_branch_count=len(failed_branch_records),
                    )
                    if isinstance(current_late_fill, dict):
                        current_late_fill = dict(current_late_fill)
                        current_late_fill['post_wave_backend_timing'] = dict(post_wave_backend_timing)
                        current_payload = self.attach_late_fill_state(current_payload, current_late_fill)
                    lookup_touch_started_at = trace.clock()
                    self.touch_response_lookup(
                        response_id,
                        status=_final_lookup_status_for_late_fill(effective_next_status),
                        output_text=str(current_payload.get('output_text') or ''),
                        response_payload=current_payload,
                        stream_view='ui' if terminal_without_pending else 'status',
                    )
                lookup_touch_elapsed_ms = trace.elapsed_ms(lookup_touch_started_at)
                post_wave_backend_timing['touch_response_lookup_elapsed_ms'] = lookup_touch_elapsed_ms
                if isinstance(current_late_fill, dict):
                    current_late_fill = dict(current_late_fill)
                    current_late_fill['post_wave_backend_timing'] = dict(post_wave_backend_timing)
                    current_payload = self.attach_late_fill_state(current_payload, current_late_fill)
                trace.log_post_wave_timing(
                    self.log_unified_event, post_wave_backend_timing,
                    response_frame_finalize_timing,
                    pending_branch_count=len(pending_branches),
                    active_branch_count=len(next_active_branches),
                    completed_branch_count=len(completed_branch_records),
                    failed_branch_count=len(failed_branch_records),
                )
                if terminal_without_pending:
                    successor_handoff = self._terminal_closure_repair_handoff(
                        current_payload,
                        request_payload=request_payload,
                        assistant_message=assistant_message,
                        source_route_payload=source_route_payload,
                    )
                    if successor_handoff is None:
                        current_payload, successor_handoff = (
                            self._prepare_terminal_graph_patch_successor_handoff(
                                current_payload,
                                request_payload=request_payload,
                                assistant_message=assistant_message,
                                artifact_gap=next_gap,
                                source_route_payload=source_route_payload,
                            )
                        )
                    if successor_handoff is None:
                        self.schedule_terminal_substrate_hygiene(
                            current_payload,
                            route_payload=source_route_payload,
                            reason='late_fill_terminal',
                        )
        except ResponseMutationConflict as exc:
            successor_handoff = self._prepare_pending_control_handoff(
                pending_continuation, artifact_gap=artifact_gap, source_route_payload=source_route_payload)
            self.log_unified_event(
                category='responses', action='late_fill', status='stale_result_rejected',
                response_id=response_id, message=str(exc),
            )
        except ResponsePersistenceError as exc:
            # Stop this worker. The finalizer retained the candidate frame and
            # exact outputs in lookup; storage recovery must not execute again.
            successor_handoff = None
            self.log_unified_event(
                category='responses', action='persistence', status='failed',
                response_id=response_id, message=str(exc),
            )
        except Exception as exc:  # noqa: BLE001
            existing_record = self.get_response_lookup_record(response_id) or {}
            current_payload = dict(existing_record.get('response_payload') or response_payload or {})
            current_late_fill = current_payload.get('late_fill') if isinstance(current_payload.get('late_fill'), dict) else {}
            completed_branch_records = self.normalize_late_fill_branches(current_late_fill.get('completed_branches'))
            failed_branch_records = self.normalize_late_fill_branches(current_late_fill.get('failed_branches'))
            cancelled_branch_records = self.normalize_late_fill_branches(current_late_fill.get('cancelled_branches'))
            active_capability = self.normalize_capability(
                current_late_fill.get('active_capability') or artifact_gap.get('expected_capability')
            )
            active_branches = self.normalize_late_fill_branches(current_late_fill.get('active_branches'))
            if active_branches:
                for branch in active_branches:
                    branch_id = self.branch_id(branch)
                    if not branch_id:
                        continue
                    if branch_id not in failed_branches:
                        failed_branches.append(branch_id)
                    if branch_id not in {self.branch_id(item) for item in failed_branch_records}:
                        error_payload = self.normalize_late_fill_error_payload(exc)
                        attempt_payload = self.late_fill_failure_attempt(branch, error_payload)
                        failed_branch = dict(branch)
                        failed_branch['status'] = 'failed'
                        failed_branch['error'] = error_payload
                        failed_branch['attempt'] = attempt_payload
                        recovery_context = self.late_fill_recovery_context(
                            error=error_payload,
                            attempt=attempt_payload,
                        )
                        failed_branch['recovery_context'] = recovery_context
                        failed_branch['recovery_state'] = self.late_fill_recovery_state(
                            failed_branch,
                            recovery_context=recovery_context,
                            attempt=attempt_payload,
                            status='candidate',
                        )
                        failed_branch_records.append(failed_branch)
            elif active_capability and active_capability not in failed_capabilities:
                failed_capabilities.append(active_capability)
            failed_late_fill = self.build_late_fill_state(
                build_gap(
                    artifact_gap,
                    capability=active_capability,
                    artifact_payload=current_payload,
                    pending_capabilities=self.normalize_capability_list(current_late_fill.get('pending_capabilities')),
                    completed_capabilities=completed_capabilities,
                    failed_capabilities=failed_capabilities,
                ),
                status='failed',
                prior_state=current_late_fill,
                extra={
                    'error': str(exc),
                    'completed_capabilities': completed_capabilities,
                    'failed_capabilities': failed_capabilities,
                    'cancelled_capabilities': self.normalize_capability_list(current_late_fill.get('cancelled_capabilities')),
                    'pending_capabilities': self.normalize_capability_list(current_late_fill.get('pending_capabilities')),
                    'active_capability': active_capability,
                    'pending_branches': self.normalize_late_fill_branches(current_late_fill.get('pending_branches')),
                    'completed_branches': completed_branch_records,
                    'failed_branches': failed_branch_records,
                    'cancelled_branches': cancelled_branch_records,
                    'active_branches': active_branches,
                    'recovery_candidates': [
                        dict(branch['recovery_state'])
                        for branch in failed_branch_records
                        if isinstance(branch.get('recovery_state'), Mapping)
                    ],
                    'auto_recovery_enabled': False,
                },
            )
            updated_payload = self.attach_late_fill_state(current_payload, failed_late_fill)
            try:
                with self._late_fill_publication(updated_payload, pending_continuation=pending_continuation):
                    finalized_payload = self.finalize_response_frame_payload(
                        updated_payload,
                        request_payload=request_payload,
                        persist=True,
                    )
                    self.touch_response_lookup(
                        response_id,
                        status='incomplete' if completed_branch_records else 'failed',
                        output_text=str(finalized_payload.get('output_text') or ''),
                        response_payload=finalized_payload,
                    )
            except (ResponsePersistenceError, ResponseMutationConflict):
                successor_handoff = None
                return
            self.log_unified_event(
                category='responses',
                action='late_fill',
                status='failed',
                response_id=response_id,
                capability=active_capability,
                message=str(exc),
            )
        finally:
            self.release_response_late_fill(response_id)
            if successor_handoff and successor_handoff.get('skip_schedule') is not True:
                successor_gap = (
                    successor_handoff.get('artifact_gap')
                    if isinstance(successor_handoff.get('artifact_gap'), dict)
                    else {}
                )
                pending_control_handoff = successor_handoff.get('pending_continuation') is not None
                terminal_closure_reopen = isinstance(
                    successor_gap.get('terminal_closure_repair_reopen'),
                    Mapping,
                )
                try:
                    scheduled = self.schedule_response_late_fill(**successor_handoff)
                except Exception as exc:  # noqa: BLE001
                    scheduled = False
                    logging.warning(
                        'Could not schedule %s Late Fill: %s',
                        'pending control continuation' if pending_control_handoff else 'terminal Closure repair' if terminal_closure_reopen else 'graph-patch successor',
                        exc,
                    )
                if not scheduled:
                    execution = (
                        successor_gap.get('successor_reopen_execution')
                        if isinstance(successor_gap, dict)
                        else {}
                    )
                    self.log_unified_event(
                        category='responses',
                        action=(
                            'pending_control_continuation' if pending_control_handoff
                            else 'terminal_closure_repair_reopen' if terminal_closure_reopen
                            else 'graph_patch_successor_reopen'
                        ),
                        status='pending',
                        response_id=response_id,
                        successor_execution_key=(execution or {}).get('successor_execution_key'),
                        message=(
                            'Pending continuation truth is durable but its Late Fill worker was not newly claimed; '
                            'no additional pending-work attempt is implied.'
                        ),
                    )

    def schedule_terminal_substrate_hygiene(
        self,
        response_payload: Mapping[str, Any],
        *,
        route_payload: Optional[Mapping[str, Any]] = None,
        reason: str = 'late_fill_terminal',
    ) -> None:
        if not callable(self.schedule_post_response_substrate_hygiene):
            return
        try:
            self.schedule_post_response_substrate_hygiene(
                response_payload,
                route_payload=route_payload,
                reason=reason,
            )
        except Exception:  # noqa: BLE001
            logging.exception('Could not schedule post-response substrate hygiene.')

    @observe_schedule
    def schedule_response_late_fill(
        self,
        *,
        response_payload: dict[str, Any],
        request_payload: dict[str, Any],
        assistant_message: str,
        artifact_gap: dict[str, Any],
        source_route_payload: Optional[dict[str, Any]],
        complete_response_late_fill: Optional[Callable[..., None]] = None,
        pending_continuation: Optional[_PendingContinuation] = None,
    ) -> bool:
        response_id = str((response_payload or {}).get('id') or '').strip()
        if response_persistence_blocked(response_payload):
            return False
        if pending_continuation is not None and not pending_continuation.take_submission():
            return False
        if not response_id or not self.claim_response_late_fill(response_id):
            return False
        transferred = False
        try:
            if pending_continuation is not None:
                with self.response_mutation(response_id):
                    current = (self.get_response_lookup_record(response_id) or {}).get('response_payload') or {}
                    self._require_pending_continuation(pending_continuation, current)
                    if not any(self._pending_branch_prerequisites(b, current, pending_continuation)
                               for b in (current.get('late_fill') or {}).get('pending_branches', [])):
                        return False
            if has_app_context() and bool(current_app.config.get('TESTING')):
                # A deterministic test shortcut is not evidence of child execution.
                return True
            context = pending_continuation
            if context is None:
                with self.response_mutation(response_id):
                    admission = (self.get_response_lookup_record(response_id) or {}).get('response_payload') or {}
                    if admission:
                        require_response_mutation_base(response_payload, admission)
                        try:
                            context = self._new_pending_continuation(admission, request_payload)
                        except ResponseMutationConflict:
                            context = None
            target = complete_response_late_fill or self.complete_response_late_fill
            trace = LateFillTrace(response_id)
            with trace.handoff():
                worker = threading.Thread(
                    target=traced_thread_target(target),
                    kwargs={
                        'response_payload': dict(response_payload or {}),
                        'request_payload': dict(request_payload or {}),
                        'assistant_message': str(assistant_message or '').strip(),
                        'artifact_gap': dict(artifact_gap or {}),
                        'source_route_payload': dict(source_route_payload or {}) if isinstance(source_route_payload, dict) else None,
                        **({'pending_continuation': context} if context is not None else {}),
                    },
                    daemon=True,
                )
                with trace.span('worker_submission'):
                    worker.start()
                    # After start, only the worker releases; tracing can still fail.
                    transferred = True
            return True
        except ResponseMutationConflict:
            return False
        finally:
            if not transferred:
                self.release_response_late_fill(response_id)
