"""Response-semantics owners for Fruth."""

from __future__ import annotations

from fruth_services.text_artifact_syntax import _HTML_CSS_SELECTOR_BINDING_CONTENT_LIMIT

from fruth_inference.selected_reference_context import SelectedReferenceContext

from fruth_services.saved_artifact_readback import SavedArtifactReadback
from fruth_services.saved_artifact_readback import (
    _SELECTED_ARTIFACT_READBACK_MAX_CHARS,
)

from fruth_inference.phase_preparation import PhasePreparation
from fruth_inference.phase_preparation import (
    _INFERENCE_RUNTIME_POLICY_SYSTEM_MARKER,
    _PREPARE_PHASE_SYSTEM_MARKER,
    _SEMANTIC_PHASE_PAYLOAD_KEYS,
)

from fruth_services.semantic_closure_review import SemanticClosureReview
from fruth_services.semantic_closure_review import (
    _BRANCH_SEMANTIC_REVIEW_EVIDENCE_POLICY,
    _DETERMINISTIC_REVIEW_CRITERIA,
    _GLOBAL_SEMANTIC_ARTIFACT_EXCERPT_LIMIT,
    _GLOBAL_SEMANTIC_ARTIFACT_EXCERPT_TOTAL_LIMIT,
    _GLOBAL_SEMANTIC_LATE_FILL_BRANCH_LIMIT,
    _GLOBAL_SEMANTIC_REVIEW_EVIDENCE_POLICY,
    _GLOBAL_SEMANTIC_TEXT_CARRIER_LIMIT,
    _SEMANTIC_REVIEW_SURFACE_ROLE,
    _SEMANTIC_REVIEW_VISIBILITY,
)

from fruth_services.semantic_artifact_reader import SemanticArtifactReader

from fruth_services.structured_dependency_review import StructuredDependencyReview
from fruth_services.structured_dependency_review import (
    _STRUCTURED_JOIN_ARTIFACT_REF_FIELDS,
    _STRUCTURED_JOIN_CONSUMER_PRODUCER_TYPES,
    _STRUCTURED_JOIN_DIRECT_PRODUCER_TYPES,
    _STRUCTURED_JOIN_ENUMERATED_LABEL_RE,
    _STRUCTURED_JOIN_FIELDS_RE,
    _STRUCTURED_JOIN_FIELD_STOP_WORDS,
    _STRUCTURED_JOIN_FOR_LABELS_RE,
    _STRUCTURED_JSON_LIST_CONTRACT_RE,
    _artifact_path,
    _bounded_visual_evidence_from_selected_message,
    _extension_from_path_like,
)

from fruth_services import closure_repair_feedback
from fruth_services.closure_repair_feedback import (
    _CLOSURE_REPAIR_PAYLOAD_KEYS,
)

from fruth_services import intent_coverage
from fruth_services.intent_coverage import (
    _INTENT_SEMANTIC_FIT_RE,
    _INTENT_SEMANTIC_QUALITY_RE,
    _NON_EXECUTABLE_BRANCH_ROLES,
    _NON_EXECUTABLE_BRANCH_STATUSES,
    _NON_EXECUTABLE_POLICY_TOKENS,
    _RESERVED_CANDIDATE_STATUSES,
    _SUPERSEDED_OBLIGATION_STATUSES,
    _WAIVED_OBLIGATION_STATUSES,
)

from fruth_services import phase_output
from fruth_services.phase_output import (
    _EXPLICIT_CONTROL_DIAGNOSTIC_RE,
    _INTERNAL_CONTROL_ENVELOPE_KEYS,
    _JSON_BOUNDARY_START_RE,
    _JSON_BOUNDARY_TOKEN_RE,
    _PHASE_OUTPUT_REPAIR_NOTICE,
    _PHASE_OUTPUT_REPAIR_SYSTEM_MESSAGE,
    _collect_control_json_content_payloads,
    _control_envelope_mapping,
    _parse_visible_json_boundary,
    _phase_graph_from_runtime_payload,
    _phase_output_graph,
    _visible_control_json_substantive_payload,
    attach_phase_output_acceptance,
    classify_phase_output_text,
    control_json_envelope_suspected,
    phase_output_acceptance_metadata,
    phase_output_defers_saved_file_materialization,
    phase_output_is_graph_preparation,
    phase_output_repair_notice,
    phase_output_repair_system_message,
    request_explicitly_allows_control_diagnostics,
    visible_control_json_envelope,
)

from fruth_inference import image_prompt_preparation
from fruth_inference.image_prompt_preparation import (
    _ARTIFACT_LABELED_IMAGE_PROMPT_HEADING_RE,
    _ARTIFACT_SECTION_HEADING_RE,
    _EMBEDDED_LABELED_IMAGE_PROMPT_RE,
    _FILENAME_SOCIAL_ASSET_ROW_RE,
    _HEX_BYTE_FRAGMENT_RE,
    _HTML_ATTR_RE,
    _HTML_CARD_CONTEXT_CLASS_RE,
    _HTML_CARD_CONTEXT_STOP_RE,
    _HTML_CARD_HANDLE_CLASS_RE,
    _HTML_HEX_BYTE_FRAGMENT_RE,
    _HTML_IMG_TAG_RE,
    _HTML_TEXT_TAG_RE,
    _IMAGE_ASSET_LABEL_PREFIX_RE,
    _INLINE_LABELED_IMAGE_PROMPT_LINE_RE,
    _MARKDOWN_SEPARATOR_LINE_RE,
    _MULTI_IMAGE_HEADING_LINE_RE,
    _MULTI_IMAGE_PROMPT_SECTION_RE,
    _NAMED_TEXT_ARTIFACT_FILENAME_RE,
    _NUMBERED_ARTIFACT_SECTION_HEADING_RE,
    _NUMBERED_IMAGE_PROMPT_SEGMENT_PATTERNS,
    _NUMBERED_PREPARED_IMAGE_PROMPT_RE,
    _NUMBERED_PREPARED_IMAGE_SIGNAL_RE,
    _PARAGRAPH_BREAK_RE,
    _PARAGRAPH_IMAGE_PROMPT_STRONG_SIGNAL_RE,
    _PLAIN_ALPHA_IMAGE_PROMPT_LINE_RE,
    _SEQUENTIAL_BOLD_ALPHA_IMAGE_PROMPT_LINE_RE,
    _SOCIAL_ASSET_FILENAME_STOPWORDS,
    _SOCIAL_MANIFEST_CAPTION_COPY_RE,
    _SOCIAL_MANIFEST_HANDLE_RE,
    _SOCIAL_MANIFEST_VISUAL_SIGNAL_RE,
    _STRUCTURAL_PAGE_IMAGE_ASSET_LABEL_RE,
    _clean_html_prompt_text,
    _clean_image_prompt_boundary_candidate,
    _clean_numbered_image_prompt_candidate,
    _clean_social_manifest_piece,
    _clean_social_manifest_prefix_prompt_body,
    _contains_plain_alpha_image_prompt_line,
    _embedded_labeled_image_prompt_body,
    _extract_filename_social_asset_image_prompt_lines,
    _extract_html_image_card_prompt_units,
    _extract_inline_labeled_image_prompt_lines,
    _extract_leading_plain_alpha_image_prompt_lines,
    _extract_markdown_table_image_prompt_anywhere,
    _extract_markdown_table_image_prompt_section,
    _extract_markdown_table_image_prompts_from_lines,
    _extract_numbered_artifact_image_prompt_bodies,
    _extract_numbered_image_prompt_section,
    _extract_numbered_prepared_image_prompt_units,
    _extract_sequential_bold_alpha_image_prompt_lines,
    _extract_social_manifest_pipe_image_prompt_lines,
    _filename_social_asset_prompt_from_row,
    _filename_social_asset_subject_piece,
    _html_attrs,
    _html_card_context_piece,
    _image_prompt_batch_looks_like_weak_social_copy,
    _image_prompt_candidate_has_subject_anchor,
    _image_prompt_candidate_is_code_or_css_polluted,
    _inline_labeled_image_prompt_body,
    _inline_labeled_image_prompt_body_is_title,
    _is_image_prompt_section_heading,
    _is_image_prompt_section_stop,
    _is_named_text_artifact_section_heading,
    _is_non_image_markdown_section_heading,
    _limit_numbered_image_prompts_for_expected_count,
    _markdown_table_cells,
    _markdown_table_compose_row_context_prompt,
    _markdown_table_header_token,
    _markdown_table_prompt_column_index,
    _markdown_table_row_context_piece,
    _markdown_table_row_context_piece_is_placeholder,
    _markdown_table_row_context_role,
    _markdown_table_separator_cells,
    _normalize_handoff_heading_line,
    _numbered_image_prompts_allow_structural_surplus,
    _parse_image_batch_expected_count,
    _social_manifest_handle_to_subject,
    _social_manifest_piece_is_quoted,
    _social_manifest_piece_looks_like_caption_copy,
    _social_manifest_prefix_body_looks_like_image_prompt,
    _social_manifest_subject_to_prompt_piece,
    _split_numbered_image_prompt_raw_items,
    _split_numbered_image_prompt_segment,
    _split_social_manifest_labeled_piece,
    _strip_handoff_markdown_wrappers,
    _strip_social_manifest_image_prompt_metadata,
    _strip_social_manifest_prefix_label,
    _strip_unlabeled_social_manifest_image_prompt_metadata,
)

from fruth_services import text_artifact_syntax
from fruth_services.text_artifact_syntax import (
    _CSS_AMBIGUOUS_PROPERTY_TYPOS,
    _CSS_ANY_VAR_REFERENCE_RE,
    _CSS_BACKGROUND_DECLARATION_RE,
    _CSS_CUSTOM_PROPERTY_DEFINITION_RE,
    _CSS_DECLARATION_NAME_FORMATTING_TAG_RE,
    _CSS_DECLARATION_NAME_RE,
    _CSS_DECLARATION_VALUE_RE,
    _CSS_HTML_ENTITY_FRAGMENT_IN_FUNCTION_RE,
    _CSS_INVALID_BACKGROUND_SHORTHAND_TOKENS,
    _CSS_INVALID_BACKGROUND_SHORTHAND_TOKEN_RE,
    _CSS_INVALID_FUNCTION_TOKENS,
    _CSS_INVALID_VAR_SLASH_REFERENCE_RE,
    _CSS_KNOWN_INVALID_PROPERTY_VALUES,
    _CSS_KNOWN_PROPERTY_TYPOS,
    _CSS_PROPERTY_IDENTIFIER_RE,
    _CSS_VAR_REFERENCE_RE,
    _HTML_ATTRIBUTE_VALUE_RE,
    _HTML_BARE_DUPLICATE_ATTRIBUTE_RE,
    _HTML_CLASS_ATTR_RE,
    _HTML_DUPLICATE_OPEN_ANGLE_KNOWN_TAG_RE,
    _HTML_HERO_ATTR_VALUE_RE,
    _HTML_HERO_LANDMARK_TAGS,
    _HTML_HREF_ALLOWED_TAGS,
    _HTML_HREF_ALLOWED_TAG_ALT,
    _HTML_HREF_ATTR_RE,
    _HTML_HREF_REPAIR_EXCLUDED_TAGS,
    _HTML_LITERAL_UNSUPPORTED_TAG_RE,
    _HTML_MALFORMED_ANCHOR_OPEN_TAG_RE,
    _HTML_MALFORMED_CLASS_ATTR_COLON_RE,
    _HTML_MALFORMED_CLASS_ONLY_OPEN_TAG_RE,
    _HTML_MALFORMED_CLOSE_EMBEDDED_TAG_RE,
    _HTML_MALFORMED_CLOSE_KNOWN_SUFFIX_RE,
    _HTML_MALFORMED_CLOSE_PREFIX_RE,
    _HTML_MALFORMED_FORMATTED_ANCHOR_FRAGMENT_RE,
    _HTML_MALFORMED_OPEN_PREFIX_KNOWN_TAG_RE,
    _HTML_MALFORMED_STYLESHEET_LINK_ATTR_RE,
    _HTML_MARKUP_IN_ATTRIBUTE_RE,
    _HTML_PARTIAL_OPEN_TAG_WITH_STRAY_FORMATTING_CLOSE_RE,
    _HTML_QUOTED_KNOWN_OPEN_TAG_RE,
    _HTML_RAW_TEXT_BLOCK_RE,
    _HTML_REPEATED_SIBLING_CLASS_HINT_RE,
    _HTML_STRAY_FORMATTING_CLOSE_IN_OPEN_TAG_RE,
    _HTML_STRAY_FORMATTING_CLOSE_TAG_ALT,
    _HTML_STRAY_KNOWN_CLOSING_TAG_REMOVABLE_TAGS,
    _HTML_STRAY_NESTED_CLOSE_RE,
    _HTML_STRAY_PUNCTUATION_PSEUDO_TAG_BEFORE_KNOWN_TAG_RE,
    _HTML_STYLESHEET_REL_TOKENS,
    _HTML_SYNTAX_REPAIR_CLOSING_TAGS,
    _HTML_SYNTAX_REPAIR_TAG_ALT,
    _HTML_SYNTAX_TAG_RE,
    _HTML_SYNTAX_VOID_TAGS,
    _HTML_UNKNOWN_CLASS_WRAPPER_TAG_RE,
    _HTML_UNSUPPORTED_HREF_ELEMENT_RE,
    _HTML_UNSUPPORTED_NAV_ANCHOR_WRAPPER_RE,
    _HTML_UNTERMINATED_KNOWN_OPEN_TAG_RE,
    _TEXT_ARTIFACT_EXTENSION_ALIASES,
    _normalize_text_artifact_extension,
    _strip_fenced_json_boundary,
)

from fruth_services.state_flow import observe_state, note as state_flow_note

from fruth_services.artifact_contracts import (
    saved_file_dependency_contract, saved_file_consumption_artifact_issue,
    separate_image_report_contract, separate_image_report_delivery_issue,
)
from fruth_services.events import observe_call, exact_target, judgment_summary

import copy
import hashlib
import html
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from helpers.model_capabilities import (
    CAPABILITY_CHAT,
    CAPABILITY_IMAGE_GENERATION,
    CAPABILITY_SPEECH_TO_TEXT,
    CAPABILITY_TEXT_TO_SPEECH,
    CAPABILITY_VISION_ANALYSIS,
    normalize_capability,
    normalize_backend,
)
from fruth_core.text_artifacts import (
    detect_text_artifact_requests,
    text_artifact_request_is_ungrounded_reference,
)
from fruth_core.transports import TEXT_ARTIFACT_EXTENSIONS
from fruth_inference.execution_planner import (
    _semantic_role_guidance,
    plan_compound_execution,
    split_visible_image_payload,
    split_visible_tts_payload,
)
from fruth_inference.intent import (
    analyze_prompt_intent, intent_span_is_literal_payload,
    materialization_is_deferred, visual_action_is_negated,
)
from fruth_inference.intent_obligations import (
    required_intent_obligations,
    summarize_required_intent_obligations,
)
from fruth_inference.router import _load_runtime_inference_policy
from fruth_inference.request_phase_graph import build_request_phase_graph
from fruth_inference.phase_graph_queries import current_phase_capability, current_phase_is_graph_resolved, current_phase_reason, downstream_phase_capabilities, downstream_phase_records
from fruth_inference.request_ir import output_obligations_from_graph
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
    RECOVERY_SUGGESTED_ACTIONS,
    normalize_recovery_suggested_action,
)
from fruth_server.repair_gate_runtime import (
    classify_repair_execution_policy,
    repair_item_has_concrete_input_evidence,
)
from fruth_services.responses import (
    request_intent_payload,
    extract_canonical_predecessor_image_prompts,
    extract_responses_current_turn_prompt,
    project_truth_guard_text,
    truth_guard_text_projection,
)
from fruth_services.semantic_review_verdict import (
    CONTENT_REVIEW_REFERENCE_POLICY,
    semantic_review_evidence_reference_catalog,
    semantic_review_verdict_freeze_acceptance,
    semantic_review_verdict_from_text,
)
from fruth_services.tts_source import resolve_explicit_tts_source


_TEXT_ONLY_IMAGE_COMPLETION_RE = re.compile(
    r'(?im)(?:^|\n)\s*(?:\*\*[^*\n]{0,120}\*\*\s*)?image generated\.\s*(?:$|\n)'
)
_TEXT_ONLY_AUDIO_COMPLETION_RE = re.compile(
    r'(?im)(?:^|\n)\s*(?:\*\*[^*\n]{0,120}\*\*\s*)?audio generated\.\s*(?:$|\n)'
)

_LINKED_IMAGE_INTENT_RE = re.compile(
    r'\b(?:use|insert|include|embed|link|reference|wire|place|background|hero|'
    r'nutze|verwende|fuege|füge|verlinke|referenziere|hintergrund)\b'
    r'[\s\S]{0,180}\b(?:generated|saved|local|actual|erzeugte(?:n|s|m|r)?|generierte(?:n|s|m|r)?|gespeicherte(?:n|s|m|r)?)?\s*'
    r'(?:image|images|picture|pictures|png|jpg|jpeg|webp|bild|bilder|bildartefakt)\b|'
    r'\b(?:generated|saved|local|actual|erzeugte(?:n|s|m|r)?|generierte(?:n|s|m|r)?|gespeicherte(?:n|s|m|r)?)?\s*'
    r'(?:image|images|picture|pictures|png|jpg|jpeg|webp|bild|bilder|bildartefakt)\b'
    r'[\s\S]{0,180}\b(?:hero|background|hintergrund|use|insert|include|embed|link|reference|place|nutze|verwende)\b',
    re.IGNORECASE,
)
_LINK_PLACEHOLDER_RE = re.compile(
    r'\b(?:placeholder|replace[_\-\s]?me|todo|tbd|dummy|'
    r'asset[_\-\s]?placeholder|image[_\-\s]?placeholder|generated[_\-\s]?image|'
    r'hero[_\-\s]?image|your[_\-\s]?(?:image|asset)|'
    r'platzhalter|zu[_\-\s]?ersetzen|ersetzen[_\-\s]?(?:bild|asset))\b',
    re.IGNORECASE,
)
_LINK_ATTRIBUTE_PLACEHOLDER_RE = re.compile(
    r'<(?P<tag_name>[a-z][a-z0-9:-]*)\b[^>]{0,800}?\b(?P<attr>src|href)\s*=\s*'
    r'(?P<quote>["\'])(?P<value>#|about:blank|placeholder:[^"\']*|)(?P=quote)[^>]*>',
    re.IGNORECASE,
)
_LINK_ATTRIBUTE_VALUE_RE = re.compile(
    r'<(?P<tag_name>[a-z][a-z0-9:-]*)\b[^>]{0,800}?\b(?P<attr>src|href)\s*=\s*'
    r'(?P<quote>["\'])(?P<value>[^"\']*)(?P=quote)[^>]*>',
    re.IGNORECASE,
)
_LINK_CSS_URL_VALUE_RE = re.compile(
    r'\burl\(\s*[\'"]?(?P<value>[^\'")]+)[\'"]?\s*\)',
    re.IGNORECASE,
)
_HERO_LOCAL_IMAGE_SIGNAL_RE = re.compile(
    r'\b(?:hero|hero[-_\s]?image|background|hintergrund|titelbild|title\s+image)\b',
    re.IGNORECASE,
)
_HERO_IMAGE_PLACEMENT_SIGNAL_RE = re.compile(
    r'\b(?:hero|titelbild|title\s+image|background[-_\s]+image|hintergrundbild)\b|'
    r'\b(?:image|picture|photo|bild)\s+(?:as|als)\s+'
    r'(?:(?:the|a|den|einen)\s+)?(?:background|hintergrund)\b',
    re.IGNORECASE,
)
_HTML_HERO_BLOCK_RE = re.compile(
    r'<(?P<tag>header|section|main|div)\b(?P<attrs>[^>]*(?:\b(?:class|id)\s*=\s*["\'][^"\']*hero[^"\']*["\'][^>]*)?)>'
    r'(?P<body>[\s\S]{0,12000}?)</\s*(?P=tag)\s*>',
    re.IGNORECASE,
)
_CSS_HERO_BLOCK_RE = re.compile(
    r'(?P<selectors>[^{}]*(?:[.#][A-Za-z0-9_-]*hero[A-Za-z0-9_-]*|\bheader\b)[^{}]*)\{(?P<body>[^{}]*)\}',
    re.IGNORECASE,
)
_CSS_BLOCK_SELECTOR_RE = re.compile(r'(?P<selectors>[^{}]+)\{', re.DOTALL)
_CSS_CLASS_SELECTOR_RE = re.compile(r'(?<![A-Za-z0-9_-])\.(?P<class>-?[_A-Za-z][A-Za-z0-9_-]*)')
_HTML_CSS_SELECTOR_BINDING_MIN_TOKENS = 6
_HTML_CSS_SELECTOR_BINDING_MIN_MISSING = 4
_HTML_CSS_SELECTOR_BINDING_MIN_RATIO = 0.35
_HTML_CSS_IGNORABLE_CLASS_TOKENS = {
    'active',
    'container',
    'hidden',
    'is-active',
    'is-hidden',
    'is-open',
    'open',
    'primary',
    'reverse',
    'secondary',
    'selected',
    'show',
    'visible',
}
_ASSET_LINK_PLACEHOLDER_TAGS = {
    'audio',
    'embed',
    'iframe',
    'image',
    'img',
    'link',
    'object',
    'script',
    'source',
    'track',
    'video',
}


def _link_placeholder_attribute_targets_asset(match: re.Match[str]) -> bool:
    tag_name = str(match.group('tag_name') or '').strip().lower()
    attr = str(match.group('attr') or '').strip().lower()
    if attr == 'src':
        return True
    return tag_name in _ASSET_LINK_PLACEHOLDER_TAGS


def _content_has_unresolved_link_placeholder(content: str) -> bool:
    if not content:
        return False
    text = str(content or '')
    for match in _LINK_ATTRIBUTE_PLACEHOLDER_RE.finditer(text):
        if _link_placeholder_attribute_targets_asset(match):
            return True
    for match in _LINK_ATTRIBUTE_VALUE_RE.finditer(text):
        if not _link_placeholder_attribute_targets_asset(match):
            continue
        value = str(match.group('value') or '').strip()
        if value and _LINK_PLACEHOLDER_RE.search(value):
            return True
    return any(
        _LINK_PLACEHOLDER_RE.search(str(match.group('value') or '').strip())
        for match in _LINK_CSS_URL_VALUE_RE.finditer(text)
    )
_TEXT_LINK_ARTIFACT_EXTENSIONS = {'html', 'htm', 'css', 'js', 'mjs', 'cjs'}
_HTML_LINK_TARGET_EXTENSIONS = {'css', 'js', 'mjs', 'cjs'}


_ACTIVE_LATE_FILL_STATUSES = {'pending', 'queued', 'running', 'scheduled', 'accepted'}
_TERMINAL_FULFILLED_BRANCH_STATUSES = {
    'canceled',
    'cancelled',
    'completed',
    'fulfilled',
    'skipped',
    'superseded',
    'waived',
}
_DEFER_DOWNSTREAM_PROMPT_RE = re.compile(
    r'\b('
    r'do\s+not\s+(?:execute|run|generate|create|make|materiali[sz]e)|'
    r'don[\'’]?t\s+(?:execute|run|generate|create|make|materiali[sz]e)|'
    r'not\s+(?:yet|now)|hold\s+(?:it|them|this|that|back|off)|keep\s+(?:it|them|this|that)?\s*(?:for\s+later|reserved)|'
    r'possible\s+later|later\s+(?:step|steps|phase|phases|turn)|'
    r'nicht\s+ausf(?:ue|ü|u)hren|nicht\s+(?:erzeugen|generieren|erstellen)|noch\s+nicht\s+ausgef(?:ue|ü|u)hrt|'
    r'nur\s+vorbereiten|vorbereitet,\s*aber\s+noch\s+nicht|'
    r'zur(?:ue|ü|u)ckhalten|halte\s+[^.;!?]{0,120}\s+zur(?:ue|ü|u)ck|'
    r'm(?:oe|ö|o)gliche\s+sp(?:ae|ä|a)tere\s+schritte|sp(?:ae|ä|a)tere\s+(?:schritte|phasen)'
    r')\b',
    re.IGNORECASE,
)
_CURRENT_ONLY_PROMPT_RE = re.compile(
    r'\b('
    r'only\s+(?:the\s+)?(?:first|current)\s+phase|execute\s+only\s+(?:the\s+)?(?:first|current)|'
    r'generate\s+only\s+(?:the\s+)?(?:first|current)|visible\s+result|'
    r'nur\s+(?:die\s+)?(?:erste|aktuelle)\s+phase|erzeuge\s+nur\s+(?:die\s+)?erste\s+phase|'
    r'nur\s+[^.;!?]{0,80}\s+als\s+sichtbares\s+ergebnis|sichtbares\s+ergebnis'
    r')\b',
    re.IGNORECASE,
)
_TEXT_ARTIFACT_EXTENSION_BY_MIME = {
    'application/javascript': 'js',
    'application/json': 'json',
    'text/css': 'css',
    'text/html': 'html',
    'text/javascript': 'js',
    'text/markdown': 'md',
    'text/plain': 'txt',
}


def _text_artifact_extension_from_record(record: Mapping[str, Any]) -> str:
    request_payload = record.get('text_artifact_request') if isinstance(record.get('text_artifact_request'), Mapping) else {}
    for value in (
        record.get('text_artifact_extension'),
        request_payload.get('extension'),
        _TEXT_ARTIFACT_EXTENSION_BY_MIME.get(str(record.get('mime_type') or '').strip().lower()),
        _extension_from_path_like(record.get('path') or record.get('source_path') or record.get('saved_text_path')),
        _extension_from_path_like(record.get('name')),
    ):
        normalized = _normalize_text_artifact_extension(value)
        if normalized:
            return normalized
    return ''


def _fruth_relative_path(value: Any) -> str:
    raw = str(value or '').strip()
    if not raw:
        return ''
    try:
        target = Path(raw).expanduser()
        if not target.is_absolute():
            return raw
        repo_root = Path(__file__).resolve().parent.parent
        candidates: list[str] = []
        for root in (Path.cwd(), repo_root):
            try:
                relative = target.resolve().relative_to(root.resolve())
            except (OSError, RuntimeError, ValueError):
                continue
            normalized = relative.as_posix()
            if normalized and normalized not in candidates:
                candidates.append(normalized)
        if candidates:
            return min(candidates, key=len)
    except (OSError, RuntimeError, ValueError):
        pass
    return raw


def _artifact_source_name(record: Mapping[str, Any]) -> str:
    request_payload = record.get('text_artifact_request') if isinstance(record.get('text_artifact_request'), Mapping) else {}
    path = _artifact_path(record)
    fallback_name = Path(path).stem if path else ''
    return str(
        record.get('name')
        or record.get('source_name')
        or request_payload.get('source_name')
        or fallback_name
        or ''
    ).strip()


def _artifact_link_tokens(record: Mapping[str, Any]) -> list[str]:
    tokens: list[str] = []
    for value in (
        _artifact_path(record),
        str(record.get('source_path') or '').strip(),
        str(record.get('url') or '').strip(),
        str(record.get('name') or '').strip(),
    ):
        if value and value not in tokens:
            tokens.append(value)
        if value:
            basename = Path(value.split('?', 1)[0].split('#', 1)[0]).name
            if basename and basename not in tokens:
                tokens.append(basename)
    return [token for token in tokens if len(token) >= 3]


def _expected_text_artifact_extension(record: Mapping[str, Any]) -> str:
    request_payload = record.get('artifact_request') if isinstance(record.get('artifact_request'), Mapping) else {}
    for value in (
        record.get('text_artifact_extension'),
        request_payload.get('extension'),
    ):
        normalized = _normalize_text_artifact_extension(value)
        if normalized:
            return normalized
    return ''


def _expected_text_artifact_source_name(record: Mapping[str, Any]) -> str:
    request_payload = record.get('artifact_request') if isinstance(record.get('artifact_request'), Mapping) else {}
    return str(
        record.get('text_artifact_source_name')
        or request_payload.get('source_name')
        or ''
    ).strip().lower()
_FALSE_LOCAL_ARTIFACT_CLAIM_RE = re.compile(
    r'(?is)('
    r'\[artifact:\s*[^\]]+\]|'
    r'artifact created|'
    r'artifact generated|'
    r'saved locally|'
    r'saved as a local artifact|'
    r'saved into a final artifact container|'
    r'downloadable artifact|'
    r'download and run this file|'
    r'ready-to-run artifact|'
    r'ready to be downloaded'
    r')'
)
_TEXT_ONLY_MATERIALIZATION_CLAIM_RE = re.compile(
    r'(?is)('
    r'materiali[sz]ed artifacts?|'
    r'materialisierte artefakte|'
    r'materialisiertes artefakt|'
    r'artefakt\s*\d+[^.\n]{0,120}\b(?:fulfilled|erfüllt|erfuellt|materialisiert)\b|'
    r'artefakt\s*\d+[^.\n]{0,160}\b(?:nicht\s+materialisiert|not\s+materiali[sz]ed|'
    r'deferred|offen|open|failed|fehlgeschlagen)\b|'
    r'(?:bild|image)\s*\d+[^.\n]{0,80}\b(?:fulfilled|erfüllt|erfuellt|materialisiert)\b'
    r')'
)
_TEXT_ONLY_IMAGE_CAPABILITY_CLAIM_RE = re.compile(
    r'(?i)\b(?:image[_ -]?generation|image|images|bild|bilder|visual|visuell|grafik|illustration)\b'
)
_TEXT_ONLY_AUDIO_CAPABILITY_CLAIM_RE = re.compile(
    r'(?i)\b(?:text[_ -]?to[_ -]?speech|tts|audio|akustisch(?:e|er|es|en)?|'
    r'sprach(?:ausgabe|version)|speech|voice|vorlesen|hörfassung|hoerfassung)\b'
)
_MARKDOWN_CODE_BLOCK_RE = re.compile(r'```[^\n`]*\n.*?```', re.DOTALL)
_DEICTIC_SOURCE_TRANSFORM_RE = re.compile(
    r'(?is)\b(?:mach(?:e|en)?|make|create|generate|turn|convert|transform|show|display|'
    r'visuali[sz]e|render|use|using|zeig(?:e|en|st|t)?|darstell(?:e|en|st|t)?|'
    r'visualisier(?:e|en|st|t)?|'
    r'nutz(?:e|en|t)?|verwend(?:e|en|et)?|wandle|verwandle|erstelle|erzeuge)\b'
    r'(?:[^.!?\n]|\.(?=\S)){0,120}?\b(?:daraus|davon|hieraus|this|that|these|those|them|it|das|dies(?:e|er|es|en|em)?|sie|es)\b|'
    r'\b(?:daraus|davon|hieraus|(?:from|with|given|using)\s+(?:this|that|these|those)|'
    r'(?:mit|aus)\s+dies(?:e|er|es|en|em)?)\b'
    r'(?:[^.!?\n]|\.(?=\S)){0,120}?\b(?:mach(?:e|en)?|make|create|generate|turn|convert|transform|show|display|'
    r'visuali[sz]e|render|use|using|zeig(?:e|en|st|t)?|darstell(?:e|en|st|t)?|'
    r'visualisier(?:e|en|st|t)?|'
    r'nutz(?:e|en|t)?|verwend(?:e|en|et)?|wandle|verwandle|erstelle|erzeuge)\b'
)
_SOURCE_TRANSFORM_ARTIFACT_TARGET_RE = re.compile(
    r'(?i)\b(?:html|html[-_\s]?file|website|webseite|page|seite|datei|file|artifact|artefact|artefakt|'
    r'audio|speech|spoken|voice(?:\s+clip)?|sprachclip|recording|recordings|'
    r'(?:sprach)?aufnahme(?:n)?|mp3|wav|vorlesen|'
    r'image|images|picture|pictures|photo|photos|graphic|graphics|bild|bilder|foto|fotos|'
    r'grafik|grafiken|illustration|illustrations|illustrationen|poster)\b'
)
_DEICTIC_SOURCE_REFERENCE_RE = re.compile(
    r'(?i)\b(?:daraus|davon|hieraus|from\s+this|from\s+that|from\s+these|from\s+those|'
    r'this|that|these|those|them|it|das|dies(?:e|er|es|en|em)?|sie|es)\b'
)
_DIRECT_TTS_SOURCE_REFERENCE_TAIL_RE = re.compile(
    r'(?is)^\s*(?:text|sentence|passage|quote|words?|line|phrase|content|'
    r'satz|passage|zitat|w(?:o|ö)rter|zeile|inhalt)\b'
    r'(?:\s+(?:exactly|verbatim|only|aloud|genau|wortgetreu|vor))*'
    r'\s*[.,:;\-]*\s*["“„«]?\s*$'
)
_DEICTIC_SOURCE_TRANSFORM_ACTION_RE = re.compile(
    r'(?i)\b(?:mach(?:e|en)?|make|create|generate|turn|convert|transform|show|display|'
    r'visuali[sz]e|render|use|using|zeig(?:e|en|st|t)?|darstell(?:e|en|st|t)?|'
    r'visualisier(?:e|en|st|t)?|'
    r'nutz(?:e|en|t)?|verwend(?:e|en|et)?|wandle|verwandle|erstelle|erzeuge)\b'
)
_COORDINATED_DEICTIC_FOLLOW_UP_ACTION_RE = re.compile(
    r'(?is)(?:'
    r'[,;]\s*|'
    r'(?:[,;]\s*)?\b(?:and|then|next|und|sowie|dann|danach|anschließend|anschliessend)\b'
    r'[\s,:-]{0,24}'
    r')(?=(?:mach(?:e|en)?|make|create|generate|turn|convert|transform|show|display|'
    r'visuali[sz]e|render|use|using|zeig(?:e|en|st|t)?|darstell(?:e|en|st|t)?|'
    r'visualisier(?:e|en|st|t)?|nutz(?:e|en|t)?|verwend(?:e|en|et)?|wandle|verwandle|'
    r'erstelle|erzeuge)\b)'
)
_RELATIVE_ARTIFACT_CONTENT_NOUN_RE = re.compile(
    r'(?i)\b(?:audio|speech|voice|recording|image|picture|photo|illustration|'
    r'file|artifact|artefact|document|text|aufnahme|bild|datei|artefakt|dokument)\b'
    r'(?:\s+[\w-]+){0,3}\s*$'
)
_RELATIVE_ARTIFACT_CONTENT_PREDICATE_RE = re.compile(
    r'(?i)^\s+(?:says?|reads?|contains?|shows?|depicts?|features?|states?|speaks?|narrates?)\b'
)
_SAME_TURN_TEXT_SOURCE_ACTION_PATTERN = (
    r'write|draft|compose|invent|formulate|create|generate|produce|describe|tell|'
    r'schreib(?:e|en|st|t)?|verfass(?:e|en|est|t)?|'
    r'entwirf|entwerf(?:e|en|t)?|formulier(?:e|en|st|t)?|'
    r'erfind(?:e|en|est|et)?|dicht(?:e|en|est|et)?|'
    r'erstell(?:e|en|st|t)?|erzeug(?:e|en|st|t)?|'
    r'generier(?:e|en|st|t)?|produzier(?:e|en|st|t)?|'
    r'beschreib(?:e|en|st|t)?|schilder(?:e|n|st|t)?|'
    r'erzähl(?:e|en|st|t)?|erzaehl(?:e|en|st|t)?'
)
_SAME_TURN_TEXT_SOURCE_NOUN_PATTERN = (
    r'scene(?:\s+text)?|place|location|setting|concept|idea|design|'
    r'source\s+text|starting\s+text|story|stories|sentence|description|'
    r'prompt|slogan|script|narration|poem|announcement|warning(?:\s+text)?|notice|summary|'
    r'report|article|e[-\s]?mail|message|copy|text|'
    r'(?:szenen|quell|ausgangs|produkt|werbe|warn)text(?:e|en|s)?|'
    r'geschichte(?:n)?|[\wäöüß-]{0,32}szene(?:n)?|ort|schauplatz|umgebung|konzept|idee|entwurf|'
    r'satz|sätze|saetze|beschreibung(?:en)?|'
    r'warnslogan|prompt|slogan|skript(?:e|en|s)?|erzählung(?:en)?|erzaehlung(?:en)?|'
    r'gedicht(?:e|en|s)?|ansage(?:n)?|warnung(?:en)?|hinweis(?:e|en)?|zusammenfassung(?:en)?|'
    r'bericht(?:e|en|s)?|artikel|e[-\s]?mail|nachricht(?:en)?'
)
_SAME_TURN_GENERATED_TEXT_SOURCE_RE = re.compile(
    rf'(?is)\b(?P<action>{_SAME_TURN_TEXT_SOURCE_ACTION_PATTERN})\b'
    rf'[^.!?\n]{{0,180}}?\b(?P<source>{_SAME_TURN_TEXT_SOURCE_NOUN_PATTERN})\b'
)
_SAME_TURN_ARTIFACT_SOURCE_ACTION_PATTERN = (
    r'create|generate|produce|draw|paint|illustrate|sketch|render|make|synthesize|'
    r'mach(?:e|en)?|erstell(?:e|en|st|t)?|erzeug(?:e|en|st|t)?|'
    r'generier(?:e|en|st|t)?|produzier(?:e|en|st|t)?|'
    r'zeichn(?:e|en|est|et)?|mal(?:e|en|st|t)?|'
    r'illustrier(?:e|en|st|t)?|skizzier(?:e|en|st|t)?|render(?:e|n|st|t)?'
)
_SAME_TURN_ARTIFACT_SOURCE_NOUN_PATTERN = (
    r'image(?:s)?|picture(?:s)?|illustration(?:s)?|graphic(?:s)?|photo(?:s)?|'
    r'audio(?:s)?|recording(?:s)?|speech|voice(?:\s+clip)?|sprachclip|'
    r'bild(?:e|er|ern|es)?|grafik(?:en)?|illustration(?:en)?|foto(?:s)?|'
    r'aufnahme(?:n)?|sprachaufnahme(?:n)?'
)
_SAME_TURN_GENERATED_ARTIFACT_SOURCE_RE = re.compile(
    rf'(?is)\b(?P<action>{_SAME_TURN_ARTIFACT_SOURCE_ACTION_PATTERN})\b'
    rf'[^.!?\n]{{0,180}}?\b(?P<source>{_SAME_TURN_ARTIFACT_SOURCE_NOUN_PATTERN})\b'
)
_SAME_TURN_IMPLICIT_IMAGE_SOURCE_RE = re.compile(
    r'(?is)\b(?P<action>paint|illustrate|sketch|'
    r'mal(?:e|en|st|t)?|illustrier(?:e|en|st|t)?|skizzier(?:e|en|st|t)?)\b'
    r'(?P<source>[^.!?\n]{1,180}?)'
    r'(?=(?:\s*[,;:-]?\s*(?:and|then|next|und|sowie|dann|danach)\s+|\s*[,;:-]\s*)'
    r'(?:analy[sz](?:e|ed|ing)?|inspect|describe|review|'
    r'analysier(?:e|en|st|t)?|untersuch(?:e|en|st|t)?|beschreib(?:e|en|st|t)?)\b)'
)


def _same_turn_generated_artifact_source_matches(
    prompt_text: str,
    start: int = 0,
    end: Optional[int] = None,
) -> list[re.Match[str]]:
    bounded_end = len(prompt_text) if end is None else max(start, min(len(prompt_text), end))
    matches_by_action_start: dict[int, re.Match[str]] = {}
    for match in _SAME_TURN_GENERATED_ARTIFACT_SOURCE_RE.finditer(
        prompt_text,
        start,
        bounded_end,
    ):
        matches_by_action_start[match.start('action')] = match
    for match in _SAME_TURN_IMPLICIT_IMAGE_SOURCE_RE.finditer(
        prompt_text,
        start,
    ):
        if match.end() > bounded_end:
            continue
        matches_by_action_start.setdefault(match.start('action'), match)
    return sorted(
        matches_by_action_start.values(),
        key=lambda item: (item.start(), item.end()),
    )
_SAME_TURN_IMAGE_CONSUMER_ACTION_RE = re.compile(
    r'(?is)\b(?:analy[sz](?:e|ed|ing)?|inspect|describe|review|'
    r'analysier(?:e|en|st|t)?|untersuch(?:e|en|st|t)?|beschreib(?:e|en|st|t)?)\b'
)
_SAME_TURN_AUDIO_CONSUMER_ACTION_RE = re.compile(
    r'(?is)\b(?:transcrib(?:e|es|ed|ing)?|listen|review|'
    r'transkribier(?:e|en|st|t)?|hör(?:e|en|st|t)?|hoer(?:e|en|st|t)?)\b'
)
_DEICTIC_ARTIFACT_CONSUMER_RE = re.compile(
    r'(?is)(?:\b(?:analy[sz](?:e|ed|ing)?|inspect|describe|review|'
    r'transcrib(?:e|es|ed|ing)?|listen|'
    r'analysier(?:e|en|st|t)?|untersuch(?:e|en|st|t)?|beschreib(?:e|en|st|t)?|'
    r'transkribier(?:e|en|st|t)?|hör(?:e|en|st|t)?|hoer(?:e|en|st|t)?)\b'
    r'(?:[^.!?\n]|\.(?=\S)){0,100}?'
    r'\b(?:daraus|davon|hieraus|this|that|these|those|them|it|das|dies(?:e|er|es|en|em)?|sie|es)\b|'
    r'\b(?:in|on|from|for|using|with|bei|aus|für|fuer|mit)\s+'
    r'(?:this|that|these|those|them|das|dies(?:e|er|es|en|em)?|sie|es)\b'
    r'[^.!?\n]{0,50}?\b(?:images?|pictures?|photos?|audios?|recordings?|'
    r'bild(?:e|er|ern|es)?|audio(?:s)?|aufnahme(?:n)?)\b'
    r'[^.!?\n]{0,60}?\b(?:analy[sz](?:e|ed|ing)?|inspect|describe|review|'
    r'transcrib(?:e|es|ed|ing)?|listen|analysier(?:e|en|st|t)?|'
    r'untersuch(?:e|en|st|t)?|beschreib(?:e|en|st|t)?|'
    r'transkribier(?:e|en|st|t)?|hör(?:e|en|st|t)?|hoer(?:e|en|st|t)?)\b)'
)
_INLINE_TEXTUAL_ARTIFACT_SOURCE_RE = re.compile(
    r'(?is)\b(?P<action>review|describe|inspect|analy[sz](?:e|ed|ing)?|'
    r'beschreib(?:e|en|st|t)?|analysier(?:e|en|st|t)?)\b'
    r'[^.!?\n]{0,40}?\b(?:this|that|these|those|das|dies(?:e|er|es|en|em)?)\b\s*'
    r'(?P<source>(?:image|audio)\s+(?:prompt|concept|idea|script|text)|'
    r'html|code|document|page)\s*:\s*(?P<content>[^.;!?\n]{1,400})'
)
_INLINE_TEXTUAL_ARTIFACT_LABEL_SOURCE_RE = re.compile(
    r'(?is)(?:^|[.!?;\n])\s*'
    r'(?P<label>(?:this\s+|dieser?\s+|dieses\s+)?'
    r'(?:image\s+(?:prompt|concept|idea)|audio\s+(?:script|text|prompt)|'
    r'bild(?:prompt|konzept|idee)|audio(?:skript|text|prompt)|'
    r'script|skript|html|code|document|dokument|page|seite))\s*:\s*'
    r'(?P<content>[^.;!?\n]{1,400})'
)
_ARTIFACT_SOURCE_NOUN_RE = re.compile(
    rf'(?is)\b(?:{_SAME_TURN_ARTIFACT_SOURCE_NOUN_PATTERN})\b'
)
_SAME_TURN_ARTIFACT_CONTEXT_PREFIX_RE = re.compile(
    r'(?is)^\s*(?:(?:'
    r'for\s+this\s+(?:test|request|task|experiment|exercise|demo)|'
    r'in\s+this\s+(?:test|request|task|experiment|exercise|demo)|'
    r'as\s+part\s+of\s+this\s+(?:test|request|task|experiment|exercise|demo)|'
    r'as\s+(?:a\s+)?(?:(?:quick|brief|small)\s+)?(?:test|experiment|exercise|demo)|'
    r'(?:in\s+)?step\s+1|to\s+begin|'
    r'für\s+diese(?:n|r)?\s+(?:test|anfrage|aufgabe|versuch|experiment|demo)|'
    r'in\s+dieser\s+(?:aufgabe|übung|uebung|demo)|'
    r'im\s+ersten\s+schritt|'
    r'als\s+(?:kurze(?:n|r|s)?\s+)?(?:test|versuch|experiment|demo)'
    r')\s*[,;:-]?\s*)$'
)
_EXTERNAL_ARTIFACT_SOURCE_LOCATOR_RE = re.compile(
    r'(?is)(?:\b[A-Za-z][A-Za-z0-9+.-]{1,31}://[^\s,;]+|'
    r'\b(?:data|blob|urn|magnet|ipfs):[^\s,;]+|'
    r'(?:^|\s)(?:\.\.?/|~/|/|\$[A-Za-z_][A-Za-z0-9_]*[\\/])(?:[^\s,;]+)|'
    r'(?:^|\s)\\\\[^\s\\]+\\[^\s,;]+|'
    r'\b(?:[A-Za-z0-9._-]+@)?[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+:[^\s,;]+|'
    r'\b[A-Za-z]:[\\/][^\s,;]+|\b[^\s,;]+\.(?:png|jpe?g|gif|webp|svg|wav|mp3|m4a|flac|ogg|html?|json|txt|md)\b|'
    r'\b(?:provided|supplied|uploaded|attached|selected|stored|hosted|fetched|downloaded)\s+'
    r'(?:by|in|at|on|from)\b|'
    r'\b(?:from|via|at|under|aus|von|über|ueber)\s+(?:an?\s+|the\s+|einer?\s+|dem\s+|der\s+)?'
    r'(?:remote|external|url|uri|path|web|internet|server|s3|bucket|storage|'
    r'extern(?:en|er|es|e)?|entfernt(?:en|er|es|e)?|pfad|netz|server)\b)'
)
_GENERATED_ARTIFACT_REFERENCE_RE = re.compile(
    r'(?i)\b(?:generated|created|rendered|produced|'
    r'erzeugt(?:e|en|er|es)?|erstellt(?:e|en|er|es)?|generiert(?:e|en|er|es)?)\b'
)
_REMOTE_ARTIFACT_SOURCE_QUALIFIER_RE = re.compile(
    r'(?i)\b(?:remote|external|url|uri|path|web|internet|server|'
    r'extern(?:e|en|er|es)?|entfernt(?:e|en|er|es)?|pfad)\b'
)
_SENTENCE_BOUNDARY_RE = re.compile(r'[.!?](?=\s|$)|\n')
_SAME_TURN_MODAL_TEXT_SOURCE_RE = re.compile(
    rf'(?is)\b(?P<directive>'
    rf'(?:kannst|könntest|koenntest|würdest|wuerdest)\s+du|'
    rf'du\s+(?:sollst|musst|kannst)|lass\s+uns|bitte'
    rf')\b[^.!?\n]{{0,120}}?\b(?P<source>{_SAME_TURN_TEXT_SOURCE_NOUN_PATTERN})\b'
    rf'[^.!?\n]{{0,80}}?\b(?P<action>{_SAME_TURN_TEXT_SOURCE_ACTION_PATTERN})\b'
)
_SAME_TURN_SOURCE_LEADING_NEGATION_RE = re.compile(
    r'(?is)\b(?:do\s+not|don[\'’]?t|never|without|no|not|'
    r'kein(?:e|en|er|es)?|nicht|ohne)\b'
    r'(?:\s+(?:ever|ever\s+again|please|bitte|under\s+any\s+circumstances))?\s*$'
)
_SAME_TURN_SOURCE_BETWEEN_NEGATION_RE = re.compile(
    r'(?is)\b(?:'
    r'no\s+(?!less\b)|'
    r'not\s+(?:a|an|any|the|this|that)\b|'
    r'without\s+(?:a|an|any|the|this|that)?\s*$|'
    r'kein(?:e|en|er|es)?\b|'
    r'nicht\s+(?:ein(?:e|en|em|er|es)?|den|die|das|diese(?:n|r|s|m)?)\b|'
    r'ohne\s+(?:ein(?:e|en|em|er|es)?)?\s*$'
    r')'
)
_SAME_TURN_SOURCE_DIRECT_PREFIX_RE = re.compile(
    r'(?is)^\s*(?:(?:please|kindly|first|then|next|now|and|'
    r'bitte|zuerst|dann|danach|nun|jetzt|und|anschließend|anschliessend)'
    r'[\s,:-]*)*$'
)
_SAME_TURN_SOURCE_YOU_DIRECTED_PREFIX_RE = re.compile(
    r'(?is)^\s*(?:please\s+|bitte\s+)?(?:'
    r'(?:can|could|would|will|should)\s+you\b|'
    r'you\s+(?:should|must|need\s+to|can|could|will|shall)\b|'
    r'i\s+(?:want|need|ask)\s+you\s+to\b|'
    r'(?:kannst|könntest|koenntest|würdest|wuerdest)\s+du\b|'
    r'du\s+(?:sollst|musst|kannst)\b|'
    r'ich\s+(?:möchte|moechte|will)\s*,?\s*dass\s+du\b'
    r')[^.!?\n]{0,100}$'
)
_SAME_TURN_SOURCE_AFFIRMATIVE_NEGATION_PREFIX_RE = re.compile(
    r'(?is)^\s*(?:do\s+not|don[\'’]?t|never)\s+(?:hesitate|forget|fail)\s+to\s*$'
)
_SAME_TURN_SOURCE_META_PREFIX_RE = re.compile(
    r'(?is)(?:'
    r'\b(?:how\s+to|whether\s+to|wie\s+man|ob\s+man)\b|'
    r'\b(?:example|for\s+example|hypothetical|quoted\s+instruction|'
    r'beispiel|zum\s+beispiel|hypothetisch|zitierte\s+anweisung)\b|'
    r'\bif\s+(?:a|the|someone)\s+user\s+(?:asks|says)\b|'
    r'\bwenn\s+(?:ein|der)\s+user\s+(?:fragt|sagt)\b'
    r')[^.!?\n]{0,120}$'
)
_SAME_TURN_SOURCE_COORDINATED_TARGET_RE = re.compile(
    r'(?is)^\s*,?\s*(?:and|und|sowie|plus)\s+'
    r'(?:(?:an?|the|ein(?:e|en|em|er|es)?)\s+)?'
    r'(?:html|website|webseite|page|seite|file|datei|artifact|artefact|artefakt|'
    r'image|picture|bild|audio|speech|mp3|wav)\b[^.!?\n]{0,80}$'
)
_EXPLICIT_DEICTIC_SOURCE_NOUN_RE = re.compile(
    rf'(?is)\b(?P<noun>{_SAME_TURN_TEXT_SOURCE_NOUN_PATTERN}|'
    r'files?|artifacts?|artefacts?|documents?|html|code|pages?|images?|pictures?|audios?|recordings?|'
    r'datei(?:en)?|artefakt(?:e|en)?|dokument(?:e|en)?|html|code|seite(?:n)?|'
    r'bild(?:e|er|ern|es)?|audio(?:s)?|aufnahme(?:n)?'
    r')\b'
)
_COMPETING_DEICTIC_SOURCE_QUALIFIER_RE = re.compile(
    r'(?i)\b(?:old|previous|existing|uploaded|attached|selected|different|another|other|'
    r'unrelated|named|specific|referenced|missing|local|alt|vorherig|bestehend|'
    r'hochgeladen|angehäng|angehaeng|referenziert|fehlend|lokal|'
    r'ausgewählt|ausgewaehlt|ander|weitere|fremd|unabhängig|unabhaengig|genannt|bestimmt)'
)
_EXTERNAL_DEICTIC_SOURCE_NOUN_RE = re.compile(
    r'(?i)\b(?:files?|artifacts?|artefacts?|documents?|html|code|pages?|images?|pictures?|'
    r'audios?|recordings?|datei(?:en)?|artefakt(?:e|en)?|dokument(?:e|en)?|'
    r'seite(?:n)?|bild(?:e|er|ern|es)?|aufnahme(?:n)?)\b'
)
_DEICTIC_SOURCE_CONNECTOR_RE = re.compile(r'(?i)\b(?:into|to|as|in|zu|als)\b')


def _payload_has_direct_artifact_source(*payloads: Optional[Mapping[str, Any]]) -> bool:
    for payload in payloads:
        if not isinstance(payload, Mapping):
            continue
        for key in (
            'input_artifacts',
            'selected_reference_artifacts',
            'selectedReferenceArtifacts',
        ):
            raw_items = payload.get(key)
            if not isinstance(raw_items, list):
                continue
            if any(
                isinstance(item, Mapping)
                and str(
                    item.get('path')
                    or item.get('source_path')
                    or item.get('url')
                    or item.get('content')
                    or ''
                ).strip()
                for item in raw_items
            ):
                return True
        raw_item = payload.get('selected_reference_artifact') or payload.get('selectedReferenceArtifact')
        if isinstance(raw_item, Mapping) and str(
            raw_item.get('path')
            or raw_item.get('source_path')
            or raw_item.get('url')
            or raw_item.get('content')
            or ''
        ).strip():
            return True
        for key in (
            'file_path',
            'route_artifact_path',
            'artifact_path',
        ):
            if str(payload.get(key) or '').strip():
                return True
    return False


def _direct_artifact_record_source_capabilities(record: Mapping[str, Any]) -> set[str]:
    if not isinstance(record, Mapping):
        return set()
    capabilities: set[str] = set()
    metadata_values = [
        str(record.get(key) or '').strip().lower()
        for key in (
            'type',
            'artifact_type',
            'output_type',
            'mime_type',
            'content_type',
        )
        if str(record.get(key) or '').strip()
    ]
    path_values = [
        str(record.get(key) or '').strip().lower()
        for key in ('path', 'source_path', 'url')
        if str(record.get(key) or '').strip()
    ]
    for source_probe in [*metadata_values, *path_values]:
        if re.search(
            r'(?:^|[\s/])image(?:/|\b)|'
            r'\.(?:png|jpe?g|gif|webp|svg|bmp|tiff?)(?:$|[?#])',
            source_probe,
            flags=re.IGNORECASE,
        ):
            capabilities.add(CAPABILITY_IMAGE_GENERATION)
        if re.search(
            r'(?:^|[\s/])audio(?:/|\b)|'
            r'\.(?:wav|mp3|m4a|flac|ogg|aac)(?:$|[?#])',
            source_probe,
            flags=re.IGNORECASE,
        ):
            capabilities.add(CAPABILITY_TEXT_TO_SPEECH)
        if re.search(
            r'(?:^|[\s/])(?:text|html|json|javascript)(?:/|\b)|'
            r'^(?:code|document|html|json|markdown|message|page|text)$|'
            r'\.(?:html?|json|txt|md|css|js|mjs|cjs|ts|py)(?:$|[?#])',
            source_probe,
            flags=re.IGNORECASE,
        ):
            capabilities.add(CAPABILITY_CHAT)
    if not capabilities and str(record.get('content') or '').strip():
        capabilities.add(CAPABILITY_CHAT)
    return capabilities


def _iter_direct_artifact_source_records(
    *payloads: Optional[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for payload in payloads:
        if not isinstance(payload, Mapping):
            continue
        for key in (
            'input_artifacts',
            'selected_reference_artifacts',
            'selectedReferenceArtifacts',
        ):
            raw_items = payload.get(key)
            if isinstance(raw_items, list):
                records.extend(
                    dict(item)
                    for item in raw_items
                    if isinstance(item, Mapping)
                )
        raw_item = payload.get('selected_reference_artifact') or payload.get(
            'selectedReferenceArtifact'
        )
        if isinstance(raw_item, Mapping):
            records.append(dict(raw_item))
        for key in ('file_path', 'route_artifact_path', 'artifact_path'):
            source_path = str(payload.get(key) or '').strip()
            if source_path:
                records.append({'path': source_path})
    unique_records: list[dict[str, Any]] = []
    seen_identity_keys: set[tuple[str, str]] = set()
    for record in records:
        identity_keys: set[tuple[str, str]] = set()
        for key in ('path', 'source_path', 'url'):
            value = str(record.get(key) or '').strip()
            if value:
                identity_keys.add(('locator', value))
        for key in ('artifact_ref', 'artifact_id', 'ref', 'source_id', 'id'):
            value = str(record.get(key) or '').strip()
            if value:
                identity_keys.add(('artifact_ref', value))
        content = record.get('content')
        if isinstance(content, str) and content.strip():
            identity_keys.add(('content', content.strip()))
        if not identity_keys:
            identity_keys.add(
                (
                    'record',
                    json.dumps(record, sort_keys=True, ensure_ascii=False, default=str),
                )
            )
        if identity_keys.intersection(seen_identity_keys):
            continue
        unique_records.append(record)
        seen_identity_keys.update(identity_keys)
    return unique_records


def _transform_reference_source_capability_counts(
    prompt_text: str,
    transform_match: re.Match[str],
) -> dict[str, int]:
    reference_match, _, reference_end = _deictic_transform_reference(
        prompt_text,
        transform_match,
    )
    normalized_reference = re.sub(
        r'\s+',
        ' ',
        str(reference_match.group(0) if reference_match else '').strip().lower(),
    )
    if normalized_reference in {'daraus', 'davon', 'hieraus'}:
        return {}
    clause_end = _sentence_clause_end(prompt_text, reference_end)
    reference_tail = prompt_text[reference_end:min(clause_end, reference_end + 120)]
    boundary_matches = [
        match
        for pattern in (_DEICTIC_SOURCE_CONNECTOR_RE, _DEICTIC_SOURCE_TRANSFORM_ACTION_RE)
        for match in [pattern.search(reference_tail)]
        if match
    ]
    for consumer_re in (
        _SAME_TURN_IMAGE_CONSUMER_ACTION_RE,
        _SAME_TURN_AUDIO_CONSUMER_ACTION_RE,
    ):
        next_consumer = consumer_re.search(reference_tail)
        if next_consumer is not None:
            boundary_matches.append(next_consumer)
    if boundary_matches:
        reference_tail = reference_tail[:min(match.start() for match in boundary_matches)]
    capability_counts: dict[str, int] = {}
    number_words = {
        'one': 1,
        'two': 2,
        'three': 3,
        'four': 4,
        'five': 5,
        'six': 6,
        'seven': 7,
        'eight': 8,
        'nine': 9,
        'ten': 10,
        'ein': 1,
        'eine': 1,
        'zwei': 2,
        'drei': 3,
        'vier': 4,
        'fünf': 5,
        'fuenf': 5,
    }
    last_noun_end_by_capability: dict[str, int] = {}
    last_noun_count_by_capability: dict[str, int] = {}
    for noun_match in _EXPLICIT_DEICTIC_SOURCE_NOUN_RE.finditer(reference_tail):
        noun = str(noun_match.group('noun') or '').strip().lower()
        capability = _artifact_source_capability(noun)
        if capability:
            required_count = 1
            count_prefix = reference_tail[
                max(0, noun_match.start() - 24):noun_match.start()
            ]
            explicit_count = re.search(
                r'(?i)\b(?P<count>\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten|'
                r'ein|eine|zwei|drei|vier|fünf|fuenf)\s*$',
                count_prefix,
            )
            if explicit_count:
                raw_count = explicit_count.group('count').lower()
                required_count = (
                    int(raw_count)
                    if raw_count.isdigit()
                    else number_words.get(raw_count, 1)
                )
            elif normalized_reference in {'these', 'those', 'from these', 'from those'} or re.search(
                r'(?:images|pictures|audios|recordings|files|artifacts|artefacts|documents|pages|'
                r'dateien|artefakte|dokumente|seiten|bilder|aufnahmen)$',
                noun,
                flags=re.IGNORECASE,
            ):
                required_count = 2
            required_count = max(1, required_count)
            previous_end = last_noun_end_by_capability.get(capability)
            if previous_end is not None and not reference_tail[
                previous_end:noun_match.start()
            ].strip():
                previous_count = last_noun_count_by_capability.get(capability, 0)
                capability_counts[capability] = (
                    capability_counts.get(capability, 0)
                    - previous_count
                    + max(previous_count, required_count)
                )
                last_noun_count_by_capability[capability] = max(
                    previous_count,
                    required_count,
                )
            else:
                capability_counts[capability] = (
                    capability_counts.get(capability, 0) + required_count
                )
                last_noun_count_by_capability[capability] = required_count
            last_noun_end_by_capability[capability] = noun_match.end()
    reference_occurrence_count = (
        2
        if normalized_reference
        in {'these', 'those', 'them', 'from these', 'from those', 'sie'}
        else 1
    )
    reference_occurrence_count += len(
        list(_DEICTIC_SOURCE_REFERENCE_RE.finditer(reference_tail))
    )
    if len(capability_counts) == 1:
        capability = next(iter(capability_counts))
        capability_counts[capability] = max(
            capability_counts[capability],
            reference_occurrence_count,
        )
    elif not capability_counts and transform_match.re is _DEICTIC_ARTIFACT_CONSUMER_RE:
        consumer_text = transform_match.group(0)
        is_image_consumer = bool(
            _SAME_TURN_IMAGE_CONSUMER_ACTION_RE.search(consumer_text)
        )
        is_audio_consumer = bool(
            _SAME_TURN_AUDIO_CONSUMER_ACTION_RE.search(consumer_text)
        )
        if is_image_consumer != is_audio_consumer:
            capability_counts[
                CAPABILITY_IMAGE_GENERATION
                if is_image_consumer
                else CAPABILITY_TEXT_TO_SPEECH
            ] = reference_occurrence_count
    return capability_counts


def _transform_reference_source_capability(
    prompt_text: str,
    transform_match: re.Match[str],
) -> str:
    capability_counts = _transform_reference_source_capability_counts(
        prompt_text,
        transform_match,
    )
    return next(iter(capability_counts), '')


def _payload_has_compatible_direct_artifact_source(
    prompt_text: str,
    transform_match: re.Match[str],
    *payloads: Optional[Mapping[str, Any]],
) -> bool:
    records = _iter_direct_artifact_source_records(*payloads)
    source_capability_counts: dict[str, int] = {}
    has_direct_source = False
    direct_source_count = 0
    for record in records:
        has_source_value = bool(
            str(
                record.get('path')
                or record.get('source_path')
                or record.get('url')
                or record.get('content')
                or ''
            ).strip()
        )
        if not has_source_value:
            continue
        has_direct_source = True
        direct_source_count += 1
        record_capabilities = _direct_artifact_record_source_capabilities(record)
        if len(record_capabilities) > 1:
            return False
        for capability in record_capabilities:
            source_capability_counts[capability] = (
                source_capability_counts.get(capability, 0) + 1
            )
    expected_capability_counts = _transform_reference_source_capability_counts(
        prompt_text,
        transform_match,
    )
    if not expected_capability_counts:
        reference_match, _, _ = _deictic_transform_reference(
            prompt_text,
            transform_match,
        )
        normalized_reference = re.sub(
            r'\s+',
            ' ',
            str(reference_match.group(0) if reference_match else '').strip().lower(),
        )
        required_count = (
            2
            if normalized_reference
            in {'these', 'those', 'them', 'from these', 'from those', 'sie'}
            else 1
        )
        return has_direct_source and direct_source_count >= required_count
    return all(
        source_capability_counts.get(capability, 0) >= required_count
        for capability, required_count in expected_capability_counts.items()
    )


def _payload_has_grounded_predecessor_image_specification(
    prompt_text: str,
    transform_match: re.Match[str],
    *payloads: Optional[Mapping[str, Any]],
) -> bool:
    generation_request = bool(
        re.search(
            r'\b(?:create|generate|make|produce|render|'
            r'erstell(?:e|en|t)?|generier(?:e|en|t)?|erzeug(?:e|en|t)?|mach(?:e|en|t)?)\b'
            r'[^.;!?\n]{0,120}\b(?:image(?:s)?|picture(?:s)?|photo(?:s)?|bild(?:er)?|foto(?:s)?)\b|'
            r'\b(?:image(?:s)?|picture(?:s)?|photo(?:s)?|bild(?:er)?|foto(?:s)?)\b'
            r'[^.;!?\n]{0,120}\b(?:create|generate|make|produce|render|'
            r'erstell(?:e|en|t)?|generier(?:e|en|t)?|erzeug(?:e|en|t)?|mach(?:e|en|t)?)\b',
            prompt_text,
            flags=re.IGNORECASE,
        )
    )
    page_binding_request = bool(
        re.search(
            r'\b(?:link|bind|embed|insert|include|update|repair|fix|'
            r'verlink(?:e|en|t)?|verkn(?:u|ü)pf(?:e|en|t)?|einbind(?:e|en|et)?|'
            r'einf(?:u|ü)g(?:e|en|t)?|aktualisier(?:e|en|t)?|reparier(?:e|en|t)?)\b'
            r'[^.;!?\n]{0,160}\b(?:site|page|website|webseite|seite|landingpage|landing[\s-]?page|html)\b|'
            r'\b(?:site|page|website|webseite|seite|landingpage|landing[\s-]?page|html)\b'
            r'[^.;!?\n]{0,160}\b(?:link|bind|embed|insert|include|update|repair|fix|'
            r'verlink(?:e|en|t)?|verkn(?:u|ü)pf(?:e|en|t)?|einbind(?:e|en|et)?|'
            r'einf(?:u|ü)g(?:e|en|t)?|aktualisier(?:e|en|t)?|reparier(?:e|en|t)?)\b',
            prompt_text,
            flags=re.IGNORECASE,
        )
    )
    if not generation_request or not page_binding_request:
        return False

    context = next(
        (
            payload.get('current_predecessor_context')
            for payload in payloads
            if isinstance(payload, Mapping)
            and isinstance(payload.get('current_predecessor_context'), Mapping)
            and str(
                payload.get('current_predecessor_context', {}).get('status')
                or ''
            ).strip().lower()
            == 'authorized'
            and str(
                payload.get('current_predecessor_context', {}).get('authorization')
                or ''
            ).strip()
            == 'canonical_same_conversation_predecessor'
        ),
        None,
    )
    prompts = [
        str(item).strip()
        for item in ((context or {}).get('batch_prompts') or [])
        if str(item).strip()
    ]
    if not prompts:
        return False
    expected_counts = _transform_reference_source_capability_counts(
        prompt_text,
        transform_match,
    )
    if any(
        capability != CAPABILITY_IMAGE_GENERATION
        for capability in expected_counts
    ):
        return False
    if len(prompts) < max(expected_counts.values(), default=1):
        return False
    return any(
        CAPABILITY_CHAT in _direct_artifact_record_source_capabilities(record)
        and str(record.get('path') or record.get('source_path') or '').strip()
        for record in _iter_direct_artifact_source_records(*payloads)
    )


def _offset_is_inside_quote(text: str, offset: int) -> bool:
    prompt_text = str(text or '')
    bounded_offset = max(0, int(offset or 0))
    prefix = prompt_text[:bounded_offset]
    current_line = prefix[prefix.rfind('\n') + 1:]
    if re.match(r'^\s*>', current_line):
        return True
    quoted_span_patterns = (
        r'(?<!\\)"[^"\n]{1,1000}(?<!\\)"',
        r'“[^”\n]{1,1000}”',
        r'„[^“\n]{1,1000}“',
        r'«[^»\n]{1,1000}»',
        r'‹[^›\n]{1,1000}›',
        r'‘[^’\n]{1,1000}’',
        r'‚[^‘\n]{1,1000}‘',
        r"(?<![\w])'[^'\n]{1,1000}'(?![\w])",
        r'```[\s\S]{1,4000}?```',
        r'`[^`\n]{1,1000}`',
    )
    quoted_spans = [
        span_match
        for pattern in quoted_span_patterns
        for span_match in re.finditer(pattern, prompt_text)
    ]
    if any(
        span_match.start() < bounded_offset < span_match.end()
        for span_match in quoted_spans
    ):
        return True
    if len(re.findall(r'(?<!\\)"', prefix)) % 2:
        return True

    # German closing curly quotes are also English opening curly quotes.  A
    # completed German span must therefore consume its closing mark instead of
    # making all later text look quoted under the English convention (and the
    # same ambiguity exists for the single-curly pair).
    consumed_closing_offsets = {
        span_match.end() - 1
        for span_match in quoted_spans
    }
    for opening, closing in (
        ('“', '”'),
        ('„', '“'),
        ('«', '»'),
        ('‹', '›'),
        ('‘', '’'),
        ('‚', '‘'),
    ):
        opening_offsets = [
            index
            for index, char in enumerate(prefix)
            if char == opening and index not in consumed_closing_offsets
        ]
        if opening_offsets and opening_offsets[-1] > prefix.rfind(closing):
            return True
    return False


def _deictic_transform_reference(
    prompt_text: str,
    match: re.Match[str],
) -> tuple[Optional[re.Match[str]], int, int]:
    reference_match = _DEICTIC_SOURCE_REFERENCE_RE.search(match.group(0))
    if not reference_match:
        return None, match.start(), match.start()
    return (
        reference_match,
        match.start() + reference_match.start(),
        match.start() + reference_match.end(),
    )


def _action_offset_is_user_directive(prompt_text: str, action_start: int) -> bool:
    clause_start = max(
        prompt_text.rfind('.', 0, action_start),
        prompt_text.rfind('!', 0, action_start),
        prompt_text.rfind('?', 0, action_start),
        prompt_text.rfind('\n', 0, action_start),
        prompt_text.rfind(';', 0, action_start),
    ) + 1
    leading = prompt_text[clause_start:action_start]
    candidate_leadings = [leading]
    last_comma = leading.rfind(',')
    if last_comma >= 0:
        candidate_leadings.append(leading[last_comma + 1:])
    candidate_leadings.extend(
        re.sub(r'^\s*[\'"`„“”‚‘’«»‹›]+\s*', '', candidate)
        for candidate in list(candidate_leadings)
    )
    return any(
        _SAME_TURN_SOURCE_DIRECT_PREFIX_RE.fullmatch(candidate)
        or _SAME_TURN_SOURCE_YOU_DIRECTED_PREFIX_RE.fullmatch(candidate)
        or _SAME_TURN_SOURCE_AFFIRMATIVE_NEGATION_PREFIX_RE.fullmatch(candidate)
        or _SAME_TURN_ARTIFACT_CONTEXT_PREFIX_RE.fullmatch(candidate)
        for candidate in candidate_leadings
    )


def _deictic_consumer_is_inline_text_source(
    prompt_text: str,
    match: re.Match[str],
) -> bool:
    return any(
        inline_match.start() == match.start()
        and bool(str(inline_match.group('content') or '').strip())
        for inline_match in _INLINE_TEXTUAL_ARTIFACT_SOURCE_RE.finditer(
            prompt_text,
            match.start(),
            min(len(prompt_text), match.start() + 520),
        )
    )


def _deictic_consumer_reference_targets_artifact(
    prompt_text: str,
    match: re.Match[str],
) -> bool:
    reference_match, reference_start, reference_end = _deictic_transform_reference(
        prompt_text,
        match,
    )
    if _DEICTIC_SOURCE_TRANSFORM_ACTION_RE.search(
        prompt_text,
        min(match.end(), match.start() + 1),
        reference_start,
    ):
        return False
    reference = re.sub(
        r'\s+',
        ' ',
        str(reference_match.group(0) if reference_match else '').strip().lower(),
    )
    if reference in {'daraus', 'davon', 'hieraus', 'it', 'them', 'sie', 'es'}:
        return True
    boundary = _SENTENCE_BOUNDARY_RE.search(prompt_text, reference_end)
    reference_tail_end = min(
        boundary.start() if boundary else len(prompt_text),
        reference_end + 80,
    )
    reference_tail = prompt_text[reference_end:reference_tail_end]
    next_transform_action = _DEICTIC_SOURCE_TRANSFORM_ACTION_RE.search(
        reference_tail
    )
    if next_transform_action is not None:
        reference_tail = reference_tail[:next_transform_action.start()]
    noun_match = _EXPLICIT_DEICTIC_SOURCE_NOUN_RE.search(reference_tail)
    return bool(
        noun_match
        and _artifact_source_capability(noun_match.group('noun') or '')
    )


def _deictic_consumer_follows_generated_artifact_source(
    prompt_text: str,
    match: re.Match[str],
) -> bool:
    clause_start = max(
        prompt_text.rfind('.', 0, match.start()),
        prompt_text.rfind('!', 0, match.start()),
        prompt_text.rfind('?', 0, match.start()),
        prompt_text.rfind('\n', 0, match.start()),
        prompt_text.rfind(';', 0, match.start()),
    ) + 1
    candidate_sources = [
        source_match
        for source_match in _same_turn_generated_artifact_source_matches(
            prompt_text,
            clause_start,
            match.start(),
        )
        if source_match.end() <= match.start()
    ]
    for source_match in reversed(candidate_sources):
        if _offset_is_inside_quote(prompt_text, source_match.start()):
            continue
        if not _artifact_source_declaration_is_user_directive(
            prompt_text,
            source_match,
        ):
            continue
        if _source_declaration_is_negated(prompt_text, source_match):
            continue
        source_leading = prompt_text[
            max(clause_start, source_match.start() - 180):source_match.start()
        ]
        if _SAME_TURN_SOURCE_META_PREFIX_RE.search(source_leading):
            continue
        coordination = prompt_text[source_match.end():match.start()]
        if re.search(
            r'(?is)(?:\b(?:and|then|next|und|sowie|dann|danach|anschließend|anschliessend)\b|[,;])'
            r'[\s,:-]*$',
            coordination,
        ):
            return True
    return False


def _deictic_match_is_actionable(
    prompt_text: str,
    match: re.Match[str],
) -> bool:
    reference_match, reference_start, reference_end = _deictic_transform_reference(
        prompt_text,
        match,
    )
    if (
        reference_match
        and reference_match.group(0).strip().lower() == 'that'
        and _RELATIVE_ARTIFACT_CONTENT_NOUN_RE.search(
            prompt_text[max(0, reference_start - 100):reference_start]
        )
        and _RELATIVE_ARTIFACT_CONTENT_PREDICATE_RE.search(
            prompt_text[reference_end:min(len(prompt_text), reference_end + 40)]
        )
    ):
        return False
    if (
        _offset_is_inside_quote(prompt_text, match.start())
        or _offset_is_inside_quote(prompt_text, reference_start)
    ):
        return False
    clause_start = max(
        prompt_text.rfind('.', 0, match.start()),
        prompt_text.rfind('!', 0, match.start()),
        prompt_text.rfind('?', 0, match.start()),
        prompt_text.rfind('\n', 0, match.start()),
        prompt_text.rfind(';', 0, match.start()),
    ) + 1
    leading = prompt_text[clause_start:match.start()]
    negation_leading = re.sub(r'[\s,;:-]+$', '', leading)
    is_user_directive = _action_offset_is_user_directive(
        prompt_text,
        match.start(),
    ) or (
        match.re is _DEICTIC_ARTIFACT_CONSUMER_RE
        and _deictic_consumer_follows_generated_artifact_source(
            prompt_text,
            match,
        )
    )
    if (
        _SAME_TURN_SOURCE_LEADING_NEGATION_RE.search(negation_leading)
        or _SAME_TURN_SOURCE_META_PREFIX_RE.search(leading[-180:])
        or not is_user_directive
    ):
        return False
    if match.re is not _DEICTIC_ARTIFACT_CONSUMER_RE:
        return True
    if _deictic_consumer_is_inline_text_source(prompt_text, match):
        return False
    return _deictic_consumer_reference_targets_artifact(prompt_text, match)


def _deictic_source_transform_matches(prompt_text: str) -> list[re.Match[str]]:
    matches = [
        *_DEICTIC_SOURCE_TRANSFORM_RE.finditer(prompt_text),
        *_DEICTIC_ARTIFACT_CONSUMER_RE.finditer(prompt_text),
    ]
    matches_by_reference: dict[int, re.Match[str]] = {}
    for match in matches:
        if not _deictic_match_is_actionable(prompt_text, match):
            continue
        _, reference_start, _ = _deictic_transform_reference(prompt_text, match)
        previous = matches_by_reference.get(reference_start)
        if previous is None or match.start() < previous.start():
            matches_by_reference[reference_start] = match
    return sorted(
        matches_by_reference.values(),
        key=lambda item: (item.start(), item.end()),
    )


def _sentence_clause_start(prompt_text: str, offset: int) -> int:
    boundaries = list(_SENTENCE_BOUNDARY_RE.finditer(prompt_text[:max(0, offset)]))
    return boundaries[-1].end() if boundaries else 0


def _sentence_clause_end(prompt_text: str, offset: int) -> int:
    boundary = _SENTENCE_BOUNDARY_RE.search(prompt_text, max(0, offset))
    return boundary.start() if boundary else len(prompt_text)


def _deictic_transform_order_anchor(prompt_text: str, match: re.Match[str]) -> int:
    reference_match, reference_start, _ = _deictic_transform_reference(prompt_text, match)
    if not reference_match:
        return match.start()
    preceding_actions = list(
        _DEICTIC_SOURCE_TRANSFORM_ACTION_RE.finditer(
            prompt_text[match.start():reference_start]
        )
    )
    if not preceding_actions:
        return reference_start
    return match.start() + preceding_actions[-1].start()


def _same_turn_generated_text_source_matches(prompt_text: str) -> list[re.Match[str]]:
    matches = [
        *_SAME_TURN_GENERATED_TEXT_SOURCE_RE.finditer(prompt_text),
        *_SAME_TURN_MODAL_TEXT_SOURCE_RE.finditer(prompt_text),
    ]
    return sorted(matches, key=lambda item: (item.start(), item.end()))


def _source_declaration_is_user_directive(
    prompt_text: str,
    source_match: re.Match[str],
) -> bool:
    action_start = source_match.start('action')
    clause_start = max(
        prompt_text.rfind('.', 0, action_start),
        prompt_text.rfind('!', 0, action_start),
        prompt_text.rfind('?', 0, action_start),
        prompt_text.rfind('\n', 0, action_start),
        prompt_text.rfind(';', 0, action_start),
    ) + 1
    action_leading = prompt_text[clause_start:action_start]
    return bool(
        _SAME_TURN_SOURCE_DIRECT_PREFIX_RE.fullmatch(action_leading)
        or _SAME_TURN_SOURCE_YOU_DIRECTED_PREFIX_RE.fullmatch(action_leading)
        or _SAME_TURN_SOURCE_AFFIRMATIVE_NEGATION_PREFIX_RE.fullmatch(action_leading)
    )


def _source_declaration_is_negated(
    prompt_text: str,
    source_match: re.Match[str],
) -> bool:
    action_start = source_match.start('action')
    clause_start = max(
        prompt_text.rfind('.', 0, action_start),
        prompt_text.rfind('!', 0, action_start),
        prompt_text.rfind('?', 0, action_start),
        prompt_text.rfind('\n', 0, action_start),
        prompt_text.rfind(';', 0, action_start),
    ) + 1
    leading = prompt_text[clause_start:action_start]
    if _SAME_TURN_SOURCE_LEADING_NEGATION_RE.search(leading):
        return True
    before_source = prompt_text[source_match.start():source_match.start('source')]
    return bool(_SAME_TURN_SOURCE_BETWEEN_NEGATION_RE.search(before_source))


def _text_source_kind(value: str) -> str:
    source = str(value or '').strip().lower()
    for kind, pattern in (
        (
            'scene',
            r'\b(?:scene|place|location|setting|concept|idea|design|'
            r'szenentext|[\wäöüß-]*szene|ort|schauplatz|umgebung|konzept|idee|entwurf)\b',
        ),
        ('story', r'\b(?:story|stories|geschichte|erzählung|erzaehlung)\b'),
        ('sentence', r'\b(?:sentence|satz|sätze|saetze)\b'),
        ('description', r'\b(?:description|beschreibung)\b'),
        ('prompt', r'\bprompt\b'),
        ('slogan', r'\b(?:slogan|warnslogan)\b'),
        ('script', r'\b(?:script|skript)\b'),
        ('narration', r'\b(?:narration|ansage)\b'),
        ('poem', r'\b(?:poem|gedicht)\b'),
        ('warning', r'\b(?:warning|notice|announcement|warntext|warnung|hinweis)\b'),
        ('summary', r'\b(?:summary|zusammenfassung)\b'),
        ('report', r'\b(?:report|bericht)\b'),
        ('article', r'\b(?:article|artikel)\b'),
        ('email', r'\b(?:e[-\s]?mail)\b'),
        ('message', r'\b(?:message|nachricht)\b'),
        ('text', r'\b(?:text|copy)\b'),
    ):
        if re.search(pattern, source, flags=re.IGNORECASE):
            return kind
    return ''


def _transform_has_competing_explicit_source(
    prompt_text: str,
    transform_match: re.Match[str],
    generated_source_match: re.Match[str],
) -> bool:
    reference_match, _, reference_end = _deictic_transform_reference(prompt_text, transform_match)
    if not reference_match:
        return False
    reference = re.sub(r'\s+', ' ', reference_match.group(0).strip().lower())
    if reference in {'daraus', 'davon', 'hieraus'}:
        return False
    clause_end_candidates = [
        index
        for index in (
            prompt_text.find('.', reference_end),
            prompt_text.find('!', reference_end),
            prompt_text.find('?', reference_end),
            prompt_text.find('\n', reference_end),
        )
        if index >= 0
    ]
    clause_end = min(clause_end_candidates) if clause_end_candidates else len(prompt_text)
    reference_tail = prompt_text[reference_end:min(clause_end, reference_end + 120)]
    connector_match = _DEICTIC_SOURCE_CONNECTOR_RE.search(reference_tail)
    explicit_source_span = (
        reference_tail[:connector_match.start()]
        if connector_match
        else reference_tail
    )
    explicit_match = _EXPLICIT_DEICTIC_SOURCE_NOUN_RE.search(explicit_source_span)
    if not explicit_match:
        return False
    if _COMPETING_DEICTIC_SOURCE_QUALIFIER_RE.search(explicit_source_span):
        return True
    explicit_noun = explicit_match.group('noun') or ''
    if _EXTERNAL_DEICTIC_SOURCE_NOUN_RE.search(explicit_noun):
        return True
    explicit_kind = _text_source_kind(explicit_noun)
    generated_kind = _text_source_kind(generated_source_match.group('source') or '')
    if explicit_kind == 'text':
        return False
    return bool(explicit_kind and generated_kind and explicit_kind != generated_kind)


def _source_declaration_is_ordered_or_coordinated(
    prompt_text: str,
    transform_match: re.Match[str],
    source_match: re.Match[str],
    *,
    transform_anchor: int,
    reference_start: int,
) -> bool:
    if source_match.end() <= transform_anchor:
        return True
    if source_match.start() != transform_match.start() or source_match.end() >= reference_start:
        return False
    coordinated_target = prompt_text[source_match.end():reference_start]
    return bool(_SAME_TURN_SOURCE_COORDINATED_TARGET_RE.search(coordinated_target))


def _prompt_declares_generated_text_source_before_transform(
    prompt_text: str,
    transform_match: re.Match[str],
) -> bool:
    expected_capabilities = set(
        _transform_reference_source_capability_counts(
            prompt_text,
            transform_match,
        )
    )
    if expected_capabilities and expected_capabilities != {CAPABILITY_CHAT}:
        return False
    transform_anchor = _deictic_transform_order_anchor(prompt_text, transform_match)
    _, reference_start, _ = _deictic_transform_reference(prompt_text, transform_match)
    candidate_prefix = prompt_text[:reference_start]
    for source_match in _same_turn_generated_text_source_matches(candidate_prefix):
        if not _source_declaration_is_ordered_or_coordinated(
            prompt_text,
            transform_match,
            source_match,
            transform_anchor=transform_anchor,
            reference_start=reference_start,
        ):
            continue
        if _offset_is_inside_quote(prompt_text, source_match.start()):
            continue
        if not _source_declaration_is_user_directive(prompt_text, source_match):
            continue
        source_scope = source_match.group(0)
        if _source_declaration_is_negated(prompt_text, source_match):
            continue
        leading = prompt_text[max(0, source_match.start() - 160):source_match.start()]
        if (
            _SAME_TURN_SOURCE_META_PREFIX_RE.search(leading)
            or _SAME_TURN_SOURCE_META_PREFIX_RE.search(source_scope)
        ):
            continue
        if _transform_has_competing_explicit_source(
            prompt_text,
            transform_match,
            source_match,
        ):
            continue
        return True
    return False


def _inline_text_source_records(
    prompt_text: str,
) -> list[tuple[int, int, int, str]]:
    records = [
        (
            source_match.start(),
            source_match.end(),
            source_match.start('action'),
            str(source_match.group('content') or '').strip(),
        )
        for source_match in _INLINE_TEXTUAL_ARTIFACT_SOURCE_RE.finditer(prompt_text)
    ]
    records.extend(
        (
            source_match.start('label'),
            source_match.end(),
            source_match.start('label'),
            str(source_match.group('content') or '').strip(),
        )
        for source_match in _INLINE_TEXTUAL_ARTIFACT_LABEL_SOURCE_RE.finditer(
            prompt_text
        )
    )
    return sorted(records, key=lambda item: (item[0], item[1]))


def _prompt_declares_inline_text_source_before_transform(
    prompt_text: str,
    transform_match: re.Match[str],
) -> bool:
    expected_capabilities = set(
        _transform_reference_source_capability_counts(
            prompt_text,
            transform_match,
        )
    )
    if expected_capabilities and expected_capabilities != {CAPABILITY_CHAT}:
        return False
    transform_anchor = _deictic_transform_order_anchor(prompt_text, transform_match)
    _, reference_start, _ = _deictic_transform_reference(prompt_text, transform_match)
    for source_start, source_end, action_start, content in _inline_text_source_records(
        prompt_text[:reference_start]
    ):
        if source_end > transform_anchor:
            continue
        if _offset_is_inside_quote(prompt_text, source_start):
            continue
        if not _action_offset_is_user_directive(prompt_text, action_start):
            continue
        leading = prompt_text[
            max(0, source_start - 180):source_start
        ]
        if _SAME_TURN_SOURCE_META_PREFIX_RE.search(leading):
            continue
        if not content:
            continue
        return True
    return False


def _prompt_has_actionable_inline_text_source(prompt_text: str) -> bool:
    for source_start, _, action_start, content in _inline_text_source_records(
        prompt_text
    ):
        if _offset_is_inside_quote(prompt_text, source_start):
            continue
        if not _action_offset_is_user_directive(prompt_text, action_start):
            continue
        leading = prompt_text[
            max(0, source_start - 180):source_start
        ]
        if _SAME_TURN_SOURCE_META_PREFIX_RE.search(leading):
            continue
        if content:
            return True
    return False


def _artifact_source_capability(value: Any) -> str:
    source = str(value or '').strip().lower()
    if re.search(
        r'\b(?:image(?:s)?|picture(?:s)?|illustration(?:s)?|graphic(?:s)?|photo(?:s)?|'
        r'poster(?:s)?|png|jpe?g|gif|webp|svg|'
        r'bild(?:e|er|ern|es)?|grafik(?:en)?|illustration(?:en)?|foto(?:s)?)\b',
        source,
        flags=re.IGNORECASE,
    ):
        return CAPABILITY_IMAGE_GENERATION
    if re.search(
        r'\b(?:audio(?:s)?|recording(?:s)?|speech|voice|mp3|wav|m4a|flac|ogg|'
        r'aufnahme(?:n)?|sprachaufnahme(?:n)?)\b',
        source,
        flags=re.IGNORECASE,
    ):
        return CAPABILITY_TEXT_TO_SPEECH
    if re.search(
        r'\b(?:html|code|document|page|text|message|json|markdown|css|javascript|'
        r'dokument(?:e|en|s)?|seite(?:n)?|text(?:e|en|s)?|nachricht(?:en)?|quellcode)\b',
        source,
        flags=re.IGNORECASE,
    ):
        return CAPABILITY_CHAT
    return ''


def _route_phase_graph_has_artifact_consumer_edge(
    route_payload: Optional[Mapping[str, Any]],
    producer_capability: str,
    *,
    minimum_edge_count: int = 1,
    minimum_producer_count: int = 1,
) -> bool:
    if not isinstance(route_payload, Mapping):
        return False
    if (
        type(minimum_edge_count) is not int
        or minimum_edge_count < 1
        or type(minimum_producer_count) is not int
        or minimum_producer_count < 1
    ):
        return False
    route_runtime = (
        route_payload.get('route_runtime')
        if isinstance(route_payload.get('route_runtime'), Mapping)
        else {}
    )
    phase_graph = (
        route_runtime.get('request_phase_graph')
        if isinstance(route_runtime.get('request_phase_graph'), Mapping)
        else route_payload.get('request_phase_graph')
        if isinstance(route_payload.get('request_phase_graph'), Mapping)
        else {}
    )
    if not current_phase_is_graph_resolved(dict(phase_graph)):
        return False
    raw_phases = phase_graph.get('phases')
    if not isinstance(raw_phases, list):
        return False
    phases = [
        dict(item)
        for item in raw_phases
        if isinstance(item, Mapping)
    ]
    if len(phases) != len(raw_phases):
        return False
    phase_ids = [str(item.get('phase_id') or '').strip() for item in phases]
    if not phases or any(not phase_id for phase_id in phase_ids):
        return False
    if len(phase_ids) != len(set(phase_ids)):
        return False
    phase_id_set = set(phase_ids)

    def _normalized_dependency_ids(
        value: Any,
        *,
        allow_missing: bool = False,
    ) -> Optional[list[str]]:
        if value is None and allow_missing:
            return []
        if not isinstance(value, list):
            return None
        dependency_ids = [str(item or '').strip() for item in value]
        if any(not dependency_id for dependency_id in dependency_ids):
            return None
        if len(dependency_ids) != len(set(dependency_ids)):
            return None
        return dependency_ids

    phase_dependencies: dict[str, set[str]] = {}
    phase_dependency_inputs: dict[str, set[str]] = {}
    for item in phases:
        phase_id = str(item.get('phase_id') or '').strip()
        dependency_ids = _normalized_dependency_ids(item.get('depends_on'))
        input_refs = item.get('input_refs')
        if dependency_ids is None or not isinstance(input_refs, list):
            return False
        if phase_id in dependency_ids or any(
            dependency_id not in phase_id_set for dependency_id in dependency_ids
        ):
            return False
        dependency_input_ids: list[str] = []
        for input_ref in input_refs:
            if not isinstance(input_ref, Mapping):
                return False
            if str(input_ref.get('kind') or '').strip().lower() != 'phase_output':
                continue
            input_phase_id = str(input_ref.get('phase_id') or '').strip()
            if not input_phase_id or input_phase_id not in phase_id_set:
                return False
            if str(input_ref.get('role') or '').strip().lower() == 'dependency':
                dependency_input_ids.append(input_phase_id)
        if len(dependency_input_ids) != len(set(dependency_input_ids)):
            return False
        if set(dependency_input_ids) != set(dependency_ids):
            return False
        phase_dependencies[phase_id] = set(dependency_ids)
        phase_dependency_inputs[phase_id] = set(dependency_input_ids)

    unresolved_dependency_count = {
        phase_id: len(dependencies)
        for phase_id, dependencies in phase_dependencies.items()
    }
    dependent_phase_ids: dict[str, set[str]] = {
        phase_id: set()
        for phase_id in phase_ids
    }
    for phase_id, dependencies in phase_dependencies.items():
        for dependency_id in dependencies:
            dependent_phase_ids[dependency_id].add(phase_id)
    ready_phase_ids = [
        phase_id
        for phase_id, dependency_count in unresolved_dependency_count.items()
        if dependency_count == 0
    ]
    visited_count = 0
    while ready_phase_ids:
        phase_id = ready_phase_ids.pop()
        visited_count += 1
        for dependent_phase_id in dependent_phase_ids.get(phase_id, set()):
            unresolved_dependency_count[dependent_phase_id] -= 1
            if unresolved_dependency_count[dependent_phase_id] == 0:
                ready_phase_ids.append(dependent_phase_id)
    if visited_count != len(phase_ids):
        return False
    candidate_graph = (
        phase_graph.get('candidate_graph')
        if isinstance(phase_graph.get('candidate_graph'), Mapping)
        else {}
    )
    raw_candidates = candidate_graph.get('candidates')
    if not isinstance(raw_candidates, list):
        return False
    if any(not isinstance(item, Mapping) for item in raw_candidates):
        return False
    output_candidates = [
        dict(item)
        for item in raw_candidates
        if isinstance(item, Mapping)
        and str(item.get('candidate_type') or '').strip().lower() == 'output'
    ]
    allowed_phase_statuses = {
        'completed',
        'fulfilled',
        'in_progress',
        'pending',
        'planned',
        'queued',
        'running',
    }
    allowed_phase_resolutions = {
        'completed',
        'executable',
        'fulfilled',
        'pending_dependency',
        'promoted',
        'ready',
        'resolved',
        'running',
    }
    allowed_contract_states = {
        'active',
        'executable',
        'promoted',
        'required',
    }

    def _expected_output_type(capability: Any) -> str:
        normalized = normalize_capability(capability)
        if normalized == CAPABILITY_IMAGE_GENERATION:
            return 'image'
        if normalized == CAPABILITY_TEXT_TO_SPEECH:
            return 'audio'
        if normalized in {CAPABILITY_VISION_ANALYSIS, CAPABILITY_SPEECH_TO_TEXT}:
            return 'text'
        return ''

    def _promoted_output_candidate(item: Mapping[str, Any]) -> dict[str, Any]:
        phase_id = str(item.get('phase_id') or '').strip()
        obligation_id = str(item.get('obligation_id') or '').strip()
        capability = normalize_capability(item.get('capability'))
        expected_output_type = _expected_output_type(capability)
        if not phase_id or not obligation_id or not capability or not expected_output_type:
            return {}
        matches = [
            candidate
            for candidate in output_candidates
            if str(candidate.get('phase_id') or '').strip() == phase_id
            and normalize_capability(candidate.get('capability')) == capability
            and str(candidate.get('kind') or '').strip().lower() == 'fruth.candidate'
            and str(candidate.get('status') or '').strip().lower() == 'promoted'
            and str(candidate.get('execution_policy') or '').strip().lower()
            == 'executable_obligation'
            and str(candidate.get('promotion_policy') or '').strip().lower()
            == 'runtime_required'
            and str(candidate.get('output_type') or '').strip().lower()
            == expected_output_type
            and (
                not str(candidate.get('contract_state') or '').strip()
                or str(candidate.get('contract_state') or '').strip().lower()
                in allowed_contract_states
            )
            and str(candidate.get('contract_ref') or '').strip() == obligation_id
            and str(candidate.get('obligation_id') or '').strip() == obligation_id
            and set(
                _normalized_dependency_ids(
                    candidate.get('depends_on'),
                    allow_missing=True,
                )
                or []
            )
            == phase_dependencies.get(phase_id, set())
            and _normalized_dependency_ids(
                candidate.get('depends_on'),
                allow_missing=True,
            )
            is not None
        ]
        return matches[0] if len(matches) == 1 else {}

    def _phase_is_promoted_nonreserved(item: Mapping[str, Any]) -> bool:
        output_contract = (
            item.get('output_contract')
            if isinstance(item.get('output_contract'), Mapping)
            else {}
        )
        capability = normalize_capability(item.get('capability'))
        expected_output_type = _expected_output_type(capability)
        phase_status = str(item.get('status') or '').strip().lower()
        phase_resolution = str(item.get('resolution') or '').strip().lower()
        phase_contract_state = str(item.get('contract_state') or '').strip().lower()
        phase_execution_policy = str(item.get('execution_policy') or '').strip().lower()
        allowed_phase_kinds = (
            {'evidence', 'materialize'}
            if capability == CAPABILITY_VISION_ANALYSIS
            else {'materialize'}
        )
        if (
            str(item.get('kind') or '').strip().lower() not in allowed_phase_kinds
            or not expected_output_type
            or str(item.get('output_type') or '').strip().lower() != expected_output_type
            or phase_status not in allowed_phase_statuses
            or phase_resolution not in allowed_phase_resolutions
            or (phase_contract_state and phase_contract_state not in allowed_contract_states)
            or (
                phase_execution_policy
                and phase_execution_policy != 'executable_obligation'
            )
            or output_contract.get('required') is not True
            or str(output_contract.get('output_type') or '').strip().lower()
            != expected_output_type
            or str(output_contract.get('status') or '').strip().lower()
            not in allowed_phase_statuses
        ):
            return False
        return bool(_promoted_output_candidate(item))

    producer_ids = {
        str(item.get('phase_id') or '').strip()
        for item in phases
        if normalize_capability(item.get('capability')) == producer_capability
        and _phase_is_promoted_nonreserved(item)
    }
    if not producer_ids:
        return False
    consumer_capability = (
        CAPABILITY_VISION_ANALYSIS
        if producer_capability == CAPABILITY_IMAGE_GENERATION
        else CAPABILITY_SPEECH_TO_TEXT
        if producer_capability == CAPABILITY_TEXT_TO_SPEECH
        else ''
    )
    if not consumer_capability:
        return False
    valid_consumer_edges: set[tuple[str, str]] = set()
    for item in phases:
        if normalize_capability(item.get('capability')) != consumer_capability:
            continue
        if not _phase_is_promoted_nonreserved(item):
            continue
        consumer_phase_id = str(item.get('phase_id') or '').strip()
        dependencies = phase_dependencies.get(consumer_phase_id, set())
        direct_producers = producer_ids.intersection(dependencies)
        if len(direct_producers) != 1:
            continue
        direct_producer_id = next(iter(direct_producers))
        input_phase_ids = phase_dependency_inputs.get(consumer_phase_id, set())
        consumer_candidate = _promoted_output_candidate(item)
        candidate_dependencies = set(
            _normalized_dependency_ids(
                consumer_candidate.get('depends_on'),
                allow_missing=True,
            )
            or []
        )
        if (
            direct_producer_id in input_phase_ids
            and direct_producer_id in candidate_dependencies
        ):
            valid_consumer_edges.add((direct_producer_id, consumer_phase_id))
    valid_producer_ids = {
        producer_id
        for producer_id, _ in valid_consumer_edges
    }
    return bool(
        len(valid_consumer_edges) >= minimum_edge_count
        and len(valid_producer_ids)
        >= minimum_producer_count
    )


def _artifact_source_declaration_is_user_directive(
    prompt_text: str,
    source_match: re.Match[str],
) -> bool:
    if _action_offset_is_user_directive(
        prompt_text,
        source_match.start('action'),
    ):
        return True
    action_start = source_match.start('action')
    clause_start = max(
        _sentence_clause_start(prompt_text, action_start),
        prompt_text.rfind(';', 0, action_start) + 1,
    )
    return bool(
        _SAME_TURN_ARTIFACT_CONTEXT_PREFIX_RE.fullmatch(
            prompt_text[clause_start:action_start]
        )
    )


def _prompt_has_matching_artifact_consumer_cue(
    prompt_text: str,
    source_match: re.Match[str],
    transform_match: re.Match[str],
    producer_capability: str,
) -> bool:
    _, reference_start, reference_end = _deictic_transform_reference(
        prompt_text,
        transform_match,
    )
    if source_match.end() > reference_start:
        return False
    consumer_action_re = None
    if producer_capability == CAPABILITY_IMAGE_GENERATION:
        consumer_action_re = _SAME_TURN_IMAGE_CONSUMER_ACTION_RE
    elif producer_capability == CAPABILITY_TEXT_TO_SPEECH:
        consumer_action_re = _SAME_TURN_AUDIO_CONSUMER_ACTION_RE
    if consumer_action_re is None:
        return False
    consumer_segment_end = _sentence_clause_end(prompt_text, reference_end)
    consumer_scope = prompt_text[source_match.end():consumer_segment_end]
    consumer_actions = list(consumer_action_re.finditer(consumer_scope))
    if not consumer_actions:
        return False
    absolute_consumer_actions = [
        (
            source_match.end() + action_match.start(),
            source_match.end() + action_match.end(),
        )
        for action_match in consumer_actions
    ]
    preceding_actions = [
        action_span
        for action_span in absolute_consumer_actions
        if action_span[0] < reference_start
    ]
    following_actions = [
        action_span
        for action_span in absolute_consumer_actions
        if action_span[0] >= reference_end
    ]
    selected_action = (
        preceding_actions[-1]
        if preceding_actions
        else following_actions[0]
        if following_actions
        else None
    )
    if selected_action is None:
        return False
    consumer_action_start, consumer_action_end = selected_action
    if consumer_action_start < reference_start:
        later_transform_action = _DEICTIC_SOURCE_TRANSFORM_ACTION_RE.search(
            prompt_text,
            consumer_action_end,
            reference_start,
        )
        if later_transform_action is not None:
            return False
    opposite_consumer_action_re = (
        _SAME_TURN_AUDIO_CONSUMER_ACTION_RE
        if producer_capability == CAPABILITY_IMAGE_GENERATION
        else _SAME_TURN_IMAGE_CONSUMER_ACTION_RE
    )
    opposite_consumer_action = opposite_consumer_action_re.search(
        prompt_text,
        reference_end,
        consumer_segment_end,
    )
    if opposite_consumer_action is not None:
        consumer_segment_end = opposite_consumer_action.start()
    next_source = next(
        (
            match
            for match in _same_turn_generated_artifact_source_matches(
                prompt_text,
                reference_end,
                consumer_segment_end,
            )
            if match.start() > reference_start
            and not _offset_is_inside_quote(prompt_text, match.start())
        ),
        None,
    )
    if next_source is not None:
        consumer_segment_end = next_source.start()
    references = [
        match
        for match in _DEICTIC_SOURCE_REFERENCE_RE.finditer(
            prompt_text,
            min(reference_start, consumer_action_end),
            consumer_segment_end,
        )
        if not _offset_is_inside_quote(prompt_text, match.start())
    ]
    if not any(match.start() == reference_start for match in references):
        return False
    for index, reference_match in enumerate(references):
        next_reference_start = (
            references[index + 1].start()
            if index + 1 < len(references)
            else consumer_segment_end
        )
        reference_span = prompt_text[
            reference_match.end():min(
                next_reference_start,
                reference_match.end() + 120,
            )
        ]
        if _artifact_reference_is_competing_source(reference_span):
            return False
        explicit_capability = _artifact_source_capability(reference_span)
        if explicit_capability and explicit_capability != producer_capability:
            return False
    return True


def _artifact_reference_is_competing_source(
    explicit_reference_span: str,
) -> bool:
    reference_span = str(explicit_reference_span or '')
    if _EXTERNAL_ARTIFACT_SOURCE_LOCATOR_RE.search(reference_span):
        return True
    noun_match = _ARTIFACT_SOURCE_NOUN_RE.search(reference_span)
    qualifier_scope = (
        reference_span[:noun_match.end()]
        if noun_match
        else reference_span[:60]
    )
    if _REMOTE_ARTIFACT_SOURCE_QUALIFIER_RE.search(qualifier_scope):
        return True
    generated_reference = bool(_GENERATED_ARTIFACT_REFERENCE_RE.search(qualifier_scope))
    for qualifier_match in _COMPETING_DEICTIC_SOURCE_QUALIFIER_RE.finditer(qualifier_scope):
        qualifier = qualifier_match.group(0).strip().lower()
        if qualifier in {'local', 'lokal'} and generated_reference:
            continue
        return True
    return False


def _artifact_source_declaration_scope(
    prompt_text: str,
    source_match: re.Match[str],
    *,
    reference_start: int,
) -> str:
    declaration_end = min(
        _sentence_clause_end(prompt_text, source_match.end()),
        reference_start,
    )
    consumer_actions = [
        action_match
        for pattern in (
            _SAME_TURN_IMAGE_CONSUMER_ACTION_RE,
            _SAME_TURN_AUDIO_CONSUMER_ACTION_RE,
        )
        for action_match in [
            pattern.search(prompt_text, source_match.end(), declaration_end)
        ]
        if action_match is not None
    ]
    if consumer_actions:
        declaration_end = min(match.start() for match in consumer_actions)
    return prompt_text[source_match.start():declaration_end]


def _declared_artifact_source_count(
    prompt_text: str,
    source_match: re.Match[str],
    producer_capability: str,
    *,
    reference_start: int,
) -> int:
    declaration_scope = _artifact_source_declaration_scope(
        prompt_text,
        source_match,
        reference_start=reference_start,
    )
    count_words = {
        'one': 1,
        'two': 2,
        'three': 3,
        'four': 4,
        'five': 5,
        'six': 6,
        'seven': 7,
        'eight': 8,
        'nine': 9,
        'ten': 10,
        'ein': 1,
        'eine': 1,
        'zwei': 2,
        'drei': 3,
        'vier': 4,
        'fünf': 5,
        'fuenf': 5,
    }
    total = 0
    previous_noun_end: Optional[int] = None
    previous_count = 0
    for noun_match in _ARTIFACT_SOURCE_NOUN_RE.finditer(declaration_scope):
        noun = noun_match.group(0).strip().lower()
        if _artifact_source_capability(noun) != producer_capability:
            continue
        count_prefix = declaration_scope[
            max(0, noun_match.start() - 24):noun_match.start()
        ]
        explicit_count = re.search(
            r'(?i)\b(?P<count>\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten|'
            r'ein|eine|zwei|drei|vier|fünf|fuenf)\s*$',
            count_prefix,
        )
        noun_count = 1
        if explicit_count:
            raw_count = explicit_count.group('count').lower()
            noun_count = (
                int(raw_count)
                if raw_count.isdigit()
                else count_words.get(raw_count, 1)
            )
        elif re.search(
            r'(?:images|pictures|audios|recordings|bilder|aufnahmen)$',
            noun,
            flags=re.IGNORECASE,
        ):
            noun_count = 2
        noun_count = max(1, noun_count)
        if previous_noun_end is not None and not declaration_scope[
            previous_noun_end:noun_match.start()
        ].strip():
            total = total - previous_count + max(previous_count, noun_count)
            previous_count = max(previous_count, noun_count)
        else:
            total += noun_count
            previous_count = noun_count
        previous_noun_end = noun_match.end()
    return max(1, total)


def _graph_grounded_artifact_sources_for_transform(
    prompt_text: str,
    transform_match: re.Match[str],
) -> list[tuple[re.Match[str], str]]:
    _, reference_start, reference_end = _deictic_transform_reference(
        prompt_text,
        transform_match,
    )
    clause_end = _sentence_clause_end(prompt_text, reference_end)
    explicit_reference_span = prompt_text[reference_end:min(clause_end, reference_end + 120)]
    eligible_sources: list[tuple[re.Match[str], str]] = []
    for source_match in _same_turn_generated_artifact_source_matches(prompt_text):
        if source_match.end() > reference_start:
            continue
        if _offset_is_inside_quote(prompt_text, source_match.start()):
            continue
        if not _artifact_source_declaration_is_user_directive(prompt_text, source_match):
            continue
        if _source_declaration_is_negated(prompt_text, source_match):
            continue
        leading = prompt_text[max(0, source_match.start() - 160):source_match.start()]
        if (
            _SAME_TURN_SOURCE_META_PREFIX_RE.search(leading)
            or _SAME_TURN_SOURCE_META_PREFIX_RE.search(source_match.group(0))
        ):
            continue
        source_declaration_scope = _artifact_source_declaration_scope(
            prompt_text,
            source_match,
            reference_start=reference_start,
        )
        producer_capabilities = {
            capability
            for noun_match in _ARTIFACT_SOURCE_NOUN_RE.finditer(
                source_declaration_scope
            )
            for capability in [_artifact_source_capability(noun_match.group(0))]
            if capability
        }
        if source_match.re is _SAME_TURN_IMPLICIT_IMAGE_SOURCE_RE:
            producer_capabilities.add(CAPABILITY_IMAGE_GENERATION)
        for producer_capability in producer_capabilities:
            if not _prompt_has_matching_artifact_consumer_cue(
                prompt_text,
                source_match,
                transform_match,
                producer_capability,
            ):
                continue
            if _artifact_reference_is_competing_source(explicit_reference_span):
                continue
            explicit_capability = _artifact_source_capability(explicit_reference_span)
            if explicit_capability and explicit_capability != producer_capability:
                continue
            eligible_sources.append((source_match, producer_capability))
    return eligible_sources


def _graph_grounded_artifact_pair_count(
    prompt_text: str,
    producer_capability: str,
) -> int:
    source_required_counts: dict[int, int] = {}
    for transform_match in _deictic_source_transform_matches(prompt_text):
        _, reference_start, _ = _deictic_transform_reference(
            prompt_text,
            transform_match,
        )
        sources = _graph_grounded_artifact_sources_for_transform(
            prompt_text,
            transform_match,
        )
        matching_sources = [
            source_match
            for source_match, capability in sources
            if capability == producer_capability
        ]
        if not matching_sources:
            continue
        nearest_source = max(matching_sources, key=lambda item: item.end())
        reference_counts = _transform_reference_source_capability_counts(
            prompt_text,
            transform_match,
        )
        source_key = nearest_source.start()
        source_required_counts[source_key] = max(
            source_required_counts.get(source_key, 0),
            reference_counts.get(producer_capability, 1),
            _declared_artifact_source_count(
                prompt_text,
                nearest_source,
                producer_capability,
                reference_start=reference_start,
            ),
        )
    return sum(source_required_counts.values())


def _graph_grounded_artifact_producer_count(
    prompt_text: str,
    producer_capability: str,
) -> int:
    source_required_counts: dict[int, int] = {}
    for transform_match in _deictic_source_transform_matches(prompt_text):
        _, reference_start, _ = _deictic_transform_reference(
            prompt_text,
            transform_match,
        )
        matching_sources = [
            source_match
            for source_match, capability in _graph_grounded_artifact_sources_for_transform(
                prompt_text,
                transform_match,
            )
            if capability == producer_capability
        ]
        if not matching_sources:
            continue
        nearest_source = max(matching_sources, key=lambda item: item.end())
        source_required_counts[nearest_source.start()] = max(
            source_required_counts.get(nearest_source.start(), 0),
            _declared_artifact_source_count(
                prompt_text,
                nearest_source,
                producer_capability,
                reference_start=reference_start,
            ),
        )
    return sum(source_required_counts.values())


def _transform_match_binds_direct_tts_source(
    prompt_text: str,
    transform_match: re.Match[str],
    *,
    source_start: int,
) -> bool:
    """Return whether this deictic span names the inline TTS data that follows."""

    if source_start <= 0:
        return False
    _, _, reference_end = _deictic_transform_reference(
        prompt_text,
        transform_match,
    )
    if reference_end <= 0 or reference_end >= source_start:
        return False
    return bool(
        _DIRECT_TTS_SOURCE_REFERENCE_TAIL_RE.fullmatch(
            prompt_text[reference_end:source_start]
        )
    )


def _transform_match_targets_artifact_in_own_action(
    prompt_text: str,
    transform_match: re.Match[str],
) -> bool:
    """Bind an artifact target to this deictic action, not the whole request."""

    _, reference_start, reference_end = _deictic_transform_reference(
        prompt_text,
        transform_match,
    )
    preceding_actions = list(
        _DEICTIC_SOURCE_TRANSFORM_ACTION_RE.finditer(
            prompt_text,
            transform_match.start(),
            reference_start,
        )
    )
    action_start = (
        preceding_actions[-1].start()
        if preceding_actions
        else transform_match.start()
    )
    action_end = _sentence_clause_end(prompt_text, reference_end)
    follow_up = _COORDINATED_DEICTIC_FOLLOW_UP_ACTION_RE.search(
        prompt_text,
        reference_end,
        action_end,
    )
    if follow_up is not None:
        action_end = follow_up.start()
    return bool(
        _SOURCE_TRANSFORM_ARTIFACT_TARGET_RE.search(
            prompt_text,
            action_start,
            action_end,
        )
    )


def _prompt_declares_graph_grounded_artifact_source_before_transform(
    prompt_text: str,
    transform_match: re.Match[str],
    *,
    route_payload: Optional[Mapping[str, Any]],
) -> bool:
    eligible_sources = _graph_grounded_artifact_sources_for_transform(
        prompt_text,
        transform_match,
    )
    for _, producer_capability in eligible_sources:
        required_edge_count = _graph_grounded_artifact_pair_count(
            prompt_text,
            producer_capability,
        )
        required_producer_count = _graph_grounded_artifact_producer_count(
            prompt_text,
            producer_capability,
        )
        if _route_phase_graph_has_artifact_consumer_edge(
            route_payload,
            producer_capability,
            minimum_edge_count=required_edge_count,
            minimum_producer_count=required_producer_count,
        ):
            return True
    return False


def _prompt_binds_graph_prepared_text_artifact_before_transform(
    prompt_text: str,
    transform_match: re.Match[str],
    *,
    route_payload: Optional[Mapping[str, Any]],
) -> bool:
    """Bind a bare pronoun to a named text artifact created in this graph."""

    reference_match, reference_start, _ = _deictic_transform_reference(
        prompt_text,
        transform_match,
    )
    reference = re.sub(
        r'\s+',
        ' ',
        str(reference_match.group(0) if reference_match else '').strip().lower(),
    )
    if reference not in {'it', 'them', 'es', 'sie'}:
        return False

    phase_graph = _phase_graph_from_runtime_payload(route_payload)
    if not current_phase_is_graph_resolved(phase_graph):
        return False
    current_phase_id = str(phase_graph.get('current_phase_id') or '').strip()
    phases = [
        dict(item)
        for item in (phase_graph.get('phases') or [])
        if isinstance(item, Mapping)
    ]
    current_phase = next(
        (
            item
            for item in phases
            if str(item.get('phase_id') or '').strip() == current_phase_id
        ),
        {},
    )
    if (
        normalize_capability(current_phase.get('capability')) != CAPABILITY_CHAT
        or str(current_phase.get('kind') or '').strip().lower() != 'prepare'
        or str(current_phase.get('role') or '').strip().lower()
        != 'text_preparation'
    ):
        return False

    phase_dependencies = {
        str(item.get('phase_id') or '').strip(): {
            str(dependency or '').strip()
            for dependency in (item.get('depends_on') or [])
            if str(dependency or '').strip()
        }
        for item in phases
        if str(item.get('phase_id') or '').strip()
    }

    def descends_from_current_phase(phase_id: str) -> bool:
        pending = list(phase_dependencies.get(phase_id, set()))
        visited: set[str] = set()
        while pending:
            dependency_id = pending.pop()
            if dependency_id == current_phase_id:
                return True
            if dependency_id in visited:
                continue
            visited.add(dependency_id)
            pending.extend(phase_dependencies.get(dependency_id, set()))
        return False

    text_artifact_successors = [
        item
        for item in phases
        if normalize_capability(item.get('capability')) == CAPABILITY_CHAT
        and str(item.get('kind') or '').strip().lower() == 'materialize'
        and str(item.get('role') or '').strip().lower()
        == 'text_artifact_output'
        and item.get('requires_artifact') is True
        and str(item.get('content_payload_source') or '').strip().lower()
        == 'current_phase_output'
        and descends_from_current_phase(
            str(item.get('phase_id') or '').strip()
        )
        and (
            not isinstance(item.get('output_contract'), Mapping)
            or item.get('output_contract', {}).get('required') is True
        )
    ]
    if not text_artifact_successors:
        return False
    if reference == 'them' and len(text_artifact_successors) < 2:
        return False

    prefix = prompt_text[transform_match.start():reference_start]
    coordinators = list(
        re.finditer(
            r'(?is)(?:\b(?:and|then|next|und|sowie|dann|danach|anschließend|anschliessend)\b|;)',
            prefix,
        )
    )
    if not coordinators:
        # A later sentence may refer to a named output in this preparation
        # graph ("Create styles.css. Use it for the page background"). Bind the
        # declaration to its exact owed artifact, not to an arbitrary earlier
        # noun or a claim that the file already exists.
        declarations = list(re.finditer(
            rf'(?i)\b(?:{_SAME_TURN_TEXT_SOURCE_ACTION_PATTERN})\b',
            prompt_text[:transform_match.start()],
        ))
        if not declarations or reference not in {'it', 'es'}:
            return False
        declaration = declarations[-1]
        if (
            _offset_is_inside_quote(prompt_text, declaration.start())
            or not _action_offset_is_user_directive(prompt_text, declaration.start())
        ):
            return False
        declaration_end = _sentence_clause_end(prompt_text, declaration.end())
        declaration_text = prompt_text[declaration.start():declaration_end]
        # A requested output derived from unspecified input does not supply
        # that input. It must pass the ordinary source checks independently.
        if re.search(
            r'(?i)\b(?:from|using|based\s+on|derived\s+from|aus|anhand|auf\s+basis)\b',
            declaration_text,
        ):
            return False
        intervening = prompt_text[declaration_end:transform_match.start()]
        if (
            _COMPETING_DEICTIC_SOURCE_QUALIFIER_RE.search(intervening)
            or _EXTERNAL_ARTIFACT_SOURCE_LOCATOR_RE.search(intervening)
        ):
            return False
        requests = [
            item for item in detect_text_artifact_requests(declaration_text)
            if item.get('source') == 'explicit_extension'
        ]
        if len(requests) != 1:
            return False
        requested = requests[0]
        matches = [
            phase for phase in text_artifact_successors
            if isinstance(phase.get('artifact_request'), Mapping)
            and all(
                phase['artifact_request'].get(key) == requested.get(key)
                for key in ('source_name', 'extension')
            )
            and str(phase.get('contract_state') or '').lower()
            not in {'reserved', 'candidate', 'optional', 'waived', 'superseded'}
        ]
        return len(matches) == 1
    source_scope = prefix[:coordinators[-1].start()]
    source_binding = re.search(
        r'(?is)\b(?:from|using|based\s+on|derived\s+from|aus|anhand|auf\s+basis)\b'
        r'(?P<source>[^,;.!?\n]{1,160})$',
        source_scope,
    )
    if source_binding:
        bound_source = str(source_binding.group('source') or '').strip()
        if (
            _DEICTIC_SOURCE_REFERENCE_RE.search(bound_source)
            or _COMPETING_DEICTIC_SOURCE_QUALIFIER_RE.search(bound_source)
            or _EXTERNAL_ARTIFACT_SOURCE_LOCATOR_RE.search(bound_source)
        ):
            return False
    return bool(_SOURCE_TRANSFORM_ARTIFACT_TARGET_RE.search(source_scope))


def _request_requires_current_source_for_transform(
    prompt: Any,
    request_payload: Optional[Mapping[str, Any]] = None,
    route_payload: Optional[Mapping[str, Any]] = None,
    response_payload: Optional[Mapping[str, Any]] = None,
) -> bool:
    prompt_text = str(prompt or '').strip()
    if not prompt_text:
        return False
    direct_tts_source = resolve_explicit_tts_source(prompt_text)
    direct_tts_source_start = int(direct_tts_source.get('start') or 0)
    transform_matches = [
        match
        for match in _deictic_source_transform_matches(prompt_text)
        if not _transform_match_binds_direct_tts_source(
            prompt_text,
            match,
            source_start=direct_tts_source_start,
        )
        and _transform_match_targets_artifact_in_own_action(
            prompt_text,
            match,
        )
    ]
    if not transform_matches:
        return False
    return any(
        not _payload_has_compatible_direct_artifact_source(
            prompt_text,
            match,
            response_payload,
            request_payload,
            route_payload,
        )
        and not _payload_has_grounded_predecessor_image_specification(
            prompt_text,
            match,
            response_payload,
            request_payload,
            route_payload,
        )
        and not _prompt_declares_generated_text_source_before_transform(prompt_text, match)
        and not _prompt_declares_inline_text_source_before_transform(
            prompt_text,
            match,
        )
        and not _prompt_declares_graph_grounded_artifact_source_before_transform(
            prompt_text,
            match,
            route_payload=route_payload,
        )
        and not _prompt_binds_graph_prepared_text_artifact_before_transform(
            prompt_text,
            match,
            route_payload=route_payload,
        )
        for match in transform_matches
    )


@dataclass
class ResponseSemanticsRuntimeOwner:
    hooks: dict[str, Any]

    @property
    def selected_reference_context(self) -> SelectedReferenceContext:
        return SelectedReferenceContext(
            build_instance_trait_summary=lambda value: self._hook('build_instance_trait_summary')(value),
            sanitize_selected_reference_artifacts=lambda value: self._hook('sanitize_selected_reference_artifacts')(value),
            read_saved_artifact_context=self.saved_artifact_readback._selected_artifact_state_readback,
        )

    @property
    def saved_artifact_readback(self) -> SavedArtifactReadback:
        return SavedArtifactReadback(
            get_response_lookup_record=self.hooks.get('get_response_lookup_record'),
            build_canonical_response_artifacts=self.hooks.get('build_canonical_response_artifacts'),
            resolve_semantic_review_artifact_path=self.hooks.get('resolve_semantic_review_artifact_path'),
            find_artifact_registry_record_by_artifact_ref=self.hooks.get('find_artifact_registry_record_by_artifact_ref'),
        )

    @property
    def phase_preparation(self) -> PhasePreparation:
        return PhasePreparation(
            extract_responses_prompt=lambda payload: self._hook('extract_responses_prompt')(payload),
        )

    @property
    def semantic_closure_review(self) -> SemanticClosureReview:
        return SemanticClosureReview(
            artifact_file_identity=self._global_semantic_artifact_file_identity,
            text_artifact_excerpt=self._global_semantic_text_artifact_excerpt,
            build_canonical_response_artifacts=lambda payload: self._hook('build_canonical_response_artifacts')(payload),
            runtime_capability_availability=self.runtime_capability_availability,
        )

    @property
    def semantic_artifact_reader(self) -> SemanticArtifactReader:
        return SemanticArtifactReader(
            resolve_semantic_review_artifact_path=self.hooks.get('resolve_semantic_review_artifact_path'),
        )

    @property
    def structured_dependency_review(self) -> StructuredDependencyReview:
        return StructuredDependencyReview(
            build_canonical_response_artifacts=self._hook('build_canonical_response_artifacts'),
        )

    def _hook(self, name: str) -> Any:
        return self.hooks[name]

    artifact_type_for_capability = staticmethod(intent_coverage.artifact_type_for_capability)

    def response_payload_has_artifact_type(
        self,
        payload: Optional[dict[str, Any]],
        artifact_type: Optional[str],
    ) -> bool:
        build_canonical_response_artifacts = self._hook('build_canonical_response_artifacts')

        if not isinstance(payload, dict):
            return False
        normalized_type = str(artifact_type or '').strip().lower()
        if not normalized_type:
            return False
        artifacts = payload.get('artifacts')
        if not isinstance(artifacts, list):
            artifacts = build_canonical_response_artifacts(payload)
        artifact_types = {
            str(item.get('type') or '').strip().lower()
            for item in artifacts
            if isinstance(item, dict) and str(item.get('type') or '').strip()
        }
        if normalized_type == 'image':
            return bool(
                str(payload.get('saved_image_path') or payload.get('savedImagePath') or '').strip()
                or str(payload.get('image_data_url') or payload.get('imageDataUrl') or '').strip()
                or 'image' in artifact_types
            )
        if normalized_type == 'audio':
            return bool(
                str(payload.get('saved_audio_path') or payload.get('savedAudioPath') or '').strip()
                or 'audio' in artifact_types
            )
        if normalized_type == 'text':
            return bool(
                str(payload.get('saved_text_path') or payload.get('savedTextPath') or '').strip()
                or 'text' in artifact_types
            )
        return normalized_type in artifact_types

    def response_payload_artifact_type_count(
        self,
        payload: Optional[dict[str, Any]],
        artifact_type: Optional[str],
    ) -> int:
        build_canonical_response_artifacts = self._hook('build_canonical_response_artifacts')

        if not isinstance(payload, dict):
            return 0
        normalized_type = str(artifact_type or '').strip().lower()
        if not normalized_type:
            return 0
        artifacts = payload.get('artifacts')
        if not isinstance(artifacts, list):
            artifacts = build_canonical_response_artifacts(payload)
        aliases = {
            'image': {'image', 'png', 'jpg', 'jpeg', 'webp'},
            'audio': {'audio', 'wav', 'mp3', 'm4a', 'flac'},
            'text': {'text', 'markdown', 'md', 'json', 'csv', 'message'},
        }.get(normalized_type, {normalized_type})
        count = 0
        for item in artifacts or []:
            if not isinstance(item, Mapping):
                continue
            item_type = str(item.get('type') or '').strip().lower()
            if item_type in aliases:
                count += 1
        if normalized_type == 'image' and count == 0 and (
            str(payload.get('saved_image_path') or payload.get('savedImagePath') or '').strip()
            or str(payload.get('image_data_url') or payload.get('imageDataUrl') or '').strip()
        ):
            return 1
        if normalized_type == 'audio' and count == 0 and str(
            payload.get('saved_audio_path') or payload.get('savedAudioPath') or ''
        ).strip():
            return 1
        if normalized_type == 'text' and count == 0 and str(
            payload.get('saved_text_path') or payload.get('savedTextPath') or ''
        ).strip():
            return 1
        return count

    def response_payload_real_text_artifact_count(
        self,
        payload: Optional[dict[str, Any]],
    ) -> int:
        build_canonical_response_artifacts = self._hook('build_canonical_response_artifacts')

        if not isinstance(payload, dict):
            return 0
        paths: set[str] = set()
        for key in ('saved_text_path', 'savedTextPath'):
            value = str(payload.get(key) or '').strip()
            if value:
                paths.add(value)
        for item in payload.get('saved_text_artifacts') or []:
            if not isinstance(item, Mapping):
                continue
            value = str(item.get('path') or item.get('source_path') or '').strip()
            if value:
                paths.add(value)
        artifacts = payload.get('artifacts')
        if not isinstance(artifacts, list):
            artifacts = build_canonical_response_artifacts(payload)
        for item in artifacts or []:
            if not isinstance(item, Mapping):
                continue
            if str(item.get('type') or '').strip().lower() != 'text':
                continue
            value = str(item.get('path') or item.get('source_path') or '').strip()
            if value:
                paths.add(value)
        return len(paths)

    @staticmethod
    def source_requires_text_artifact(source: Mapping[str, Any], output_type: str) -> bool:
        if str(output_type or '').strip().lower() != 'text':
            return False
        value = source.get('requires_artifact')
        if isinstance(value, bool):
            return value
        token = str(value or '').strip().lower()
        if token in {'true', 'yes', '1', 'required'}:
            return True
        role = str(source.get('role') or '').strip().lower()
        policy = str(source.get('fulfillment_policy') or '').strip().lower()
        return role in {'text_artifact_output', 'document_output'} or policy == 'runtime_text_artifact'

    @staticmethod
    def _text_artifact_revision_required_for_closure(source: Mapping[str, Any]) -> bool:
        value = source.get('text_artifact_revision_required')
        if isinstance(value, bool):
            return value
        return str(value or '').strip().lower() in {'1', 'required', 'true', 'yes'}

    @staticmethod
    def _text_artifact_revision_target_for_closure(source: Mapping[str, Any]) -> str:
        artifact_request = (
            source.get('artifact_request')
            if isinstance(source.get('artifact_request'), Mapping)
            else {}
        )
        return str(
            source.get('text_artifact_target_path')
            or artifact_request.get('target_path')
            or ''
        ).strip()

    @staticmethod
    def _normalized_text_artifact_path_for_closure(value: Any) -> str:
        raw = str(value or '').strip()
        if not raw:
            return ''
        if raw.startswith('file://'):
            raw = raw[7:]
        try:
            return str(Path(raw).expanduser().resolve(strict=False))
        except (OSError, RuntimeError, ValueError):
            return raw

    @classmethod
    def _text_artifact_revision_closure_evidence(
        cls,
        source: Mapping[str, Any],
        *,
        artifact_payload: Mapping[str, Any],
        late_fill: Mapping[str, Any],
        branch_id: str,
        phase_id: str,
    ) -> dict[str, Any]:
        """Validate branch-local revision write and preservation evidence."""

        target_path = cls._text_artifact_revision_target_for_closure(source)
        normalized_target = cls._normalized_text_artifact_path_for_closure(target_path)
        preservation_required = source.get(
            'text_artifact_revision_preservation_required'
        ) is True
        preservation_policy = str(
            source.get('text_artifact_revision_preservation_policy')
            or 'structural_anchor_retention_v1'
        ).strip()
        result: dict[str, Any] = {
            'required': True,
            'target_path': target_path or None,
            'write_proven': False,
            'preservation_required': preservation_required,
            'preservation_passed': not preservation_required,
            'status': 'failed',
            'evidence': 'text_artifact_revision_write_proof_missing_or_invalid',
        }
        if not normalized_target:
            result['evidence'] = 'text_artifact_revision_target_contract_missing'
            return result

        matching_tokens = {token for token in (branch_id, phase_id) if token}
        candidate_records: list[Mapping[str, Any]] = []
        for record in late_fill.get('fill_results') or []:
            if not isinstance(record, Mapping):
                continue
            record_tokens = {
                str(record.get('branch_id') or '').strip(),
                str(record.get('phase_id') or '').strip(),
            }
            record_tokens.discard('')
            if matching_tokens and not matching_tokens.intersection(record_tokens):
                continue
            candidate_records.append(record)
        for record in late_fill.get('completed_branches') or []:
            if not isinstance(record, Mapping):
                continue
            record_tokens = {
                str(record.get('branch_id') or '').strip(),
                str(record.get('phase_id') or '').strip(),
            }
            record_tokens.discard('')
            if matching_tokens and not matching_tokens.intersection(record_tokens):
                continue
            candidate_records.append(record)

        # The synchronous path has no Late Fill record. It remains bounded by
        # the contracted target path and an explicit current-response proof.
        candidate_records.append(artifact_payload)
        candidate_records.extend(
            record
            for record in (artifact_payload.get('saved_text_artifacts') or [])
            if isinstance(record, Mapping)
        )

        proof_seen = False
        target_matching_proof_seen = False
        saved_path_seen = False
        hash_mismatch_seen = False
        preservation_failed = False
        preservation_seen = False
        for record in candidate_records:
            nested_records = [record]
            nested_records.extend(
                item
                for item in (record.get('saved_text_artifacts') or [])
                if isinstance(item, Mapping)
            )
            for evidence_record in nested_records:
                proof = (
                    evidence_record.get('text_artifact_revision_write_proof')
                    if isinstance(
                        evidence_record.get('text_artifact_revision_write_proof'),
                        Mapping,
                    )
                    else {}
                )
                if not proof:
                    continue
                proof_seen = True
                if str(proof.get('status') or '').strip().lower() != 'applied':
                    continue
                proof_target = cls._normalized_text_artifact_path_for_closure(
                    proof.get('target_path')
                )
                if proof_target != normalized_target:
                    continue
                target_matching_proof_seen = True

                saved_paths = {
                    cls._normalized_text_artifact_path_for_closure(
                        evidence_record.get(key)
                    )
                    for key in ('path', 'saved_text_path', 'source_path')
                }
                saved_paths.update(
                    cls._normalized_text_artifact_path_for_closure(
                        record.get(key)
                    )
                    for key in ('path', 'saved_text_path', 'source_path')
                )
                saved_paths.discard('')
                matching_saved_paths = {
                    path for path in saved_paths if path == normalized_target
                }
                if not matching_saved_paths:
                    continue
                saved_path_seen = True
                saved_path = next(iter(matching_saved_paths))
                try:
                    saved_bytes = Path(saved_path).read_bytes()
                except OSError:
                    continue
                expected_output_sha256 = str(
                    proof.get('output_sha256') or ''
                ).strip().lower()
                actual_output_sha256 = hashlib.sha256(saved_bytes).hexdigest()
                if (
                    expected_output_sha256
                    and expected_output_sha256 != actual_output_sha256
                ):
                    hash_mismatch_seen = True
                    continue

                preservation_evidence = (
                    evidence_record.get(
                        'text_artifact_revision_preservation_evidence'
                    )
                    if isinstance(
                        evidence_record.get(
                            'text_artifact_revision_preservation_evidence'
                        ),
                        Mapping,
                    )
                    else record.get(
                        'text_artifact_revision_preservation_evidence'
                    )
                    if isinstance(
                        record.get('text_artifact_revision_preservation_evidence'),
                        Mapping,
                    )
                    else {}
                )
                if preservation_required:
                    if not preservation_evidence:
                        continue
                    preservation_seen = True
                    preservation_target = (
                        cls._normalized_text_artifact_path_for_closure(
                            preservation_evidence.get('target_path')
                        )
                    )
                    preservation_status = str(
                        preservation_evidence.get('status') or ''
                    ).strip().lower()
                    if preservation_status == 'failed':
                        preservation_failed = True
                    if (
                        preservation_status != 'passed'
                        or preservation_target != normalized_target
                        or str(
                            preservation_evidence.get('policy') or ''
                        ).strip()
                        != preservation_policy
                    ):
                        continue

                result.update(
                    {
                        'write_proven': True,
                        'preservation_passed': True,
                        'status': 'passed',
                        'evidence': 'text_artifact_revision_write_proven',
                        'saved_text_path': saved_path,
                        'actual_output_sha256': actual_output_sha256,
                        'write_proof': dict(proof),
                    }
                )
                if preservation_evidence:
                    result['preservation_evidence'] = dict(
                        preservation_evidence
                    )
                return result

        if preservation_required and preservation_failed:
            result['evidence'] = 'text_artifact_revision_preservation_failed'
            result['preservation_evidence_status'] = 'failed'
        elif preservation_required and target_matching_proof_seen and saved_path_seen:
            result['evidence'] = (
                'text_artifact_revision_preservation_evidence_missing_or_invalid'
            )
            result['preservation_evidence_status'] = (
                'invalid' if preservation_seen else 'missing'
            )
        elif hash_mismatch_seen:
            result['evidence'] = 'text_artifact_revision_output_hash_mismatch'
        elif proof_seen and not target_matching_proof_seen:
            result['evidence'] = 'text_artifact_revision_write_proof_target_mismatch'
        elif target_matching_proof_seen and not saved_path_seen:
            result['evidence'] = 'text_artifact_revision_saved_target_missing'
        return result

    _branch_record_is_non_executable_candidate = staticmethod(intent_coverage._branch_record_is_non_executable_candidate)

    @staticmethod
    def _branch_record_is_terminally_fulfilled(source: Mapping[str, Any]) -> bool:
        status = str(source.get('status') or source.get('contract_state') or '').strip().lower()
        output_contract = source.get('output_contract') if isinstance(source.get('output_contract'), Mapping) else {}
        output_contract_status = str(output_contract.get('status') or '').strip().lower()
        return (
            status in _TERMINAL_FULFILLED_BRANCH_STATUSES
            or output_contract_status in _TERMINAL_FULFILLED_BRANCH_STATUSES
        )

    @staticmethod
    def _request_graph_defers_downstream_execution(request_phase_graph: Optional[Mapping[str, Any]]) -> bool:
        if not isinstance(request_phase_graph, Mapping):
            return False
        prompt_intent = (
            request_phase_graph.get('prompt_intent')
            if isinstance(request_phase_graph.get('prompt_intent'), Mapping)
            else {}
        )
        if isinstance(prompt_intent.get('materialization_defer_scope'), dict):
            return materialization_is_deferred(prompt_intent)
        if bool(prompt_intent.get('explicit_defer_materialization')) and not (
            bool(prompt_intent.get('requests_audio_output'))
            or bool(prompt_intent.get('requests_visual_output'))
            or bool(prompt_intent.get('requests_speech_to_text_output'))
            or bool(prompt_intent.get('has_audio_follow_up_request'))
            or bool(prompt_intent.get('has_visual_follow_up_request'))
            or bool(prompt_intent.get('text_preparation_before_audio_output'))
            or bool(prompt_intent.get('text_preparation_before_visual_output'))
        ):
            return True
        prompt = str(
            request_phase_graph.get('prompt')
            or prompt_intent.get('prompt')
            or prompt_intent.get('normalized_prompt')
            or ''
        ).strip()
        if not prompt:
            return False
        return bool(_CURRENT_ONLY_PROMPT_RE.search(prompt) and _DEFER_DOWNSTREAM_PROMPT_RE.search(prompt))

    _coerce_positive_int = staticmethod(intent_coverage._coerce_positive_int)

    _current_request_prompt_for_review = staticmethod(intent_coverage._current_request_prompt_for_review)

    _merged_prompt_intent_for_review = staticmethod(intent_coverage._merged_prompt_intent_for_review)

    _reserved_material_output_counts = staticmethod(intent_coverage._reserved_material_output_counts)

    _expected_material_output_counts = staticmethod(intent_coverage._expected_material_output_counts)

    _graph_material_output_counts = staticmethod(intent_coverage._graph_material_output_counts)

    _graph_required_capability_counts = staticmethod(intent_coverage._graph_required_capability_counts)

    _intent_obligation_summary = staticmethod(intent_coverage._intent_obligation_summary)

    _phase_lookup_for_intent_review = staticmethod(intent_coverage._phase_lookup_for_intent_review)

    _missing_intent_dependency_edges = staticmethod(intent_coverage._missing_intent_dependency_edges)

    _intent_graph_has_explicit_promise_ledger = staticmethod(intent_coverage._intent_graph_has_explicit_promise_ledger)

    _intent_semantic_fit_requested = staticmethod(intent_coverage._intent_semantic_fit_requested)

    _build_intent_lens_review = staticmethod(intent_coverage._build_intent_lens_review)

    build_intent_graph_adequacy_review = staticmethod(intent_coverage.build_intent_graph_adequacy_review)

    _json_for_semantic_review_prompt = staticmethod(SemanticClosureReview._json_for_semantic_review_prompt)

    _semantic_manifest_sha256 = staticmethod(SemanticClosureReview._semantic_manifest_sha256)

    _semantic_review_evidence_sha256_from_record = staticmethod(SemanticClosureReview._semantic_review_evidence_sha256_from_record)

    _late_fill_branch_record = staticmethod(SemanticClosureReview._late_fill_branch_record)

    @classmethod
    def _late_fill_branch_status(cls, artifact_payload: Optional[dict[str, Any]], branch_id: str) -> str:
        _, status = SemanticClosureReview._late_fill_branch_record(artifact_payload, branch_id)
        return status

    _semantic_review_verdict_from_late_fill = staticmethod(SemanticClosureReview._semantic_review_verdict_from_late_fill)

    _global_semantic_review_evidence_summary = staticmethod(SemanticClosureReview._global_semantic_review_evidence_summary)

    _bounded_global_semantic_text = staticmethod(SemanticClosureReview._bounded_global_semantic_text)

    _bounded_semantic_value = staticmethod(SemanticClosureReview._bounded_semantic_value)

    _global_semantic_late_fill_summary = staticmethod(SemanticClosureReview._global_semantic_late_fill_summary)

    def _resolved_semantic_review_artifact_path(
        self,
        path_value: Any,
    ) -> Optional[Path]:
        return self.semantic_artifact_reader._resolved_semantic_review_artifact_path(path_value)

    def _global_semantic_text_artifact_excerpt(
        self,
        path_value: Any,
        *,
        byte_limit: int,
    ) -> dict[str, Any]:
        return self.semantic_artifact_reader._global_semantic_text_artifact_excerpt(path_value, byte_limit=byte_limit)

    def _global_semantic_artifact_file_identity(
        self,
        path_value: Any,
    ) -> dict[str, Any]:
        return self.semantic_artifact_reader._global_semantic_artifact_file_identity(path_value)

    def _global_semantic_evidence_payload(
        self,
        *,
        artifact_payload: Optional[dict[str, Any]],
        checks: Sequence[Mapping[str, Any]],
        intent_graph_adequacy: Mapping[str, Any],
        decision_contract: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self.semantic_closure_review._global_semantic_evidence_payload(artifact_payload=artifact_payload, checks=checks, intent_graph_adequacy=intent_graph_adequacy, decision_contract=decision_contract)

    _global_semantic_intent_graph_adequacy_summary = staticmethod(SemanticClosureReview._global_semantic_intent_graph_adequacy_summary)

    def _global_semantic_review_instruction(
        self,
        *,
        prompt: str,
        output_text: str,
        evidence_payload: Mapping[str, Any],
    ) -> str:
        return self.semantic_closure_review._global_semantic_review_instruction(prompt=prompt, output_text=output_text, evidence_payload=evidence_payload)

    _global_semantic_review_generation = staticmethod(SemanticClosureReview._global_semantic_review_generation)

    _semantic_review_branch_slug = staticmethod(SemanticClosureReview._semantic_review_branch_slug)

    _branch_semantic_review_generation = staticmethod(SemanticClosureReview._branch_semantic_review_generation)

    _branch_semantic_check_projection = staticmethod(SemanticClosureReview._branch_semantic_check_projection)

    _check_is_branch_semantic_review_target = staticmethod(SemanticClosureReview._check_is_branch_semantic_review_target)

    _branch_semantic_accepted_scope = staticmethod(SemanticClosureReview._branch_semantic_accepted_scope)

    def _branch_semantic_evidence_payload(
        self,
        *,
        artifact_payload: Optional[dict[str, Any]],
        check: Mapping[str, Any],
        output_text: str,
    ) -> dict[str, Any]:
        return self.semantic_closure_review._branch_semantic_evidence_payload(artifact_payload=artifact_payload, check=check, output_text=output_text)

    def _branch_semantic_review_instruction(
        self,
        *,
        prompt: str,
        check: Mapping[str, Any],
        evidence_payload: Mapping[str, Any],
    ) -> str:
        return self.semantic_closure_review._branch_semantic_review_instruction(prompt=prompt, check=check, evidence_payload=evidence_payload)

    def _branch_semantic_review_contract(
        self,
        *,
        artifact_payload: Optional[dict[str, Any]],
        check: Mapping[str, Any],
        prompt: str,
        output_text: str,
    ) -> tuple[dict[str, Any], str, dict[str, Any]]:
        return self.semantic_closure_review._branch_semantic_review_contract(artifact_payload=artifact_payload, check=check, prompt=prompt, output_text=output_text)

    def _apply_branch_semantic_verdict_to_check(
        self,
        check: Mapping[str, Any],
        *,
        artifact_payload: Optional[dict[str, Any]],
        prompt: str,
        output_text: str,
    ) -> dict[str, Any]:
        return self.semantic_closure_review._apply_branch_semantic_verdict_to_check(check, artifact_payload=artifact_payload, prompt=prompt, output_text=output_text)

    def _branch_semantic_review_checks(
        self,
        *,
        checks: Sequence[Mapping[str, Any]],
        request_payload: Optional[dict[str, Any]],
        request_phase_graph: Mapping[str, Any],
        artifact_payload: Optional[dict[str, Any]],
        output_text: str,
    ) -> list[dict[str, Any]]:
        return self.semantic_closure_review._branch_semantic_review_checks(checks=checks, request_payload=request_payload, request_phase_graph=request_phase_graph, artifact_payload=artifact_payload, output_text=output_text)

    _recovery_action_for_semantic_review_transition = staticmethod(SemanticClosureReview._recovery_action_for_semantic_review_transition)

    _global_semantic_required_criteria = staticmethod(SemanticClosureReview._global_semantic_required_criteria)

    _global_semantic_verdict_proposal = staticmethod(SemanticClosureReview._global_semantic_verdict_proposal)

    def build_global_semantic_closure_review(
        self,
        *,
        output_text: str,
        request_payload: Optional[dict[str, Any]],
        request_phase_graph: Mapping[str, Any],
        artifact_payload: Optional[dict[str, Any]],
        checks: Sequence[Mapping[str, Any]],
        intent_graph_adequacy: Mapping[str, Any],
        decision_contract: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self.semantic_closure_review.build_global_semantic_closure_review(output_text=output_text, request_payload=request_payload, request_phase_graph=request_phase_graph, artifact_payload=artifact_payload, checks=checks, intent_graph_adequacy=intent_graph_adequacy, decision_contract=decision_contract)

    def _global_semantic_closure_checks(
        self,
        global_review: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        return self.semantic_closure_review._global_semantic_closure_checks(global_review)

    def artifact_gap_is_already_fulfilled(
        self,
        artifact_gap: Optional[dict[str, Any]],
        payload: Optional[dict[str, Any]],
    ) -> bool:
        if not isinstance(artifact_gap, dict):
            return False
        missing_artifact_type = str(artifact_gap.get('missing_artifact_type') or '').strip().lower()
        if not missing_artifact_type:
            missing_artifact_type = str(
                intent_coverage.artifact_type_for_capability(artifact_gap.get('expected_capability')) or ''
            ).strip().lower()
        if not missing_artifact_type:
            return False
        if missing_artifact_type == 'text' and self.source_requires_text_artifact(artifact_gap, 'text'):
            return self._text_artifact_gap_is_already_fulfilled(artifact_gap, payload)
        if normalize_capability(artifact_gap.get('expected_capability')) == CAPABILITY_SPEECH_TO_TEXT:
            return self._speech_to_text_gap_is_already_fulfilled(artifact_gap, payload)
        return self.response_payload_has_artifact_type(payload, missing_artifact_type)

    def _speech_to_text_gap_is_already_fulfilled(
        self,
        artifact_gap: Mapping[str, Any],
        payload: Optional[dict[str, Any]],
    ) -> bool:
        if not isinstance(payload, Mapping):
            return False
        expected_branch_id = str(
            artifact_gap.get('expected_branch_id')
            or artifact_gap.get('branch_id')
            or ''
        ).strip()
        expected_phase_id = str(
            artifact_gap.get('expected_phase_id')
            or artifact_gap.get('phase_id')
            or ''
        ).strip()
        late_fill = payload.get('late_fill') if isinstance(payload.get('late_fill'), Mapping) else {}
        for result in late_fill.get('fill_results') or []:
            if not isinstance(result, Mapping):
                continue
            if normalize_capability(result.get('capability')) != CAPABILITY_SPEECH_TO_TEXT:
                continue
            result_branch_id = str(result.get('branch_id') or '').strip()
            result_phase_id = str(result.get('phase_id') or '').strip()
            if expected_branch_id and result_branch_id and result_branch_id != expected_branch_id:
                continue
            if expected_phase_id and result_phase_id and result_phase_id != expected_phase_id:
                continue
            if (
                str(result.get('saved_text_path') or '').strip()
                or str(result.get('content_payload') or '').strip()
                or str(result.get('result_text') or '').strip()
            ):
                return True
        return normalize_capability(payload.get('response_capability') or payload.get('capability')) == CAPABILITY_SPEECH_TO_TEXT and bool(
            str(payload.get('saved_text_path') or payload.get('savedTextPath') or '').strip()
            or str(payload.get('output_text') or '').strip()
        )

    def _text_artifact_gap_is_already_fulfilled(
        self,
        artifact_gap: Mapping[str, Any],
        payload: Optional[dict[str, Any]],
    ) -> bool:
        build_canonical_response_artifacts = self._hook('build_canonical_response_artifacts')

        if not isinstance(payload, Mapping):
            return False
        expected_extension = _expected_text_artifact_extension(artifact_gap)
        expected_source_name = _expected_text_artifact_source_name(artifact_gap)
        artifacts = payload.get('artifacts')
        if not isinstance(artifacts, list):
            artifacts = build_canonical_response_artifacts(dict(payload))
        candidates: list[Mapping[str, Any]] = [
            item
            for item in artifacts or []
            if isinstance(item, Mapping)
            and str(item.get('type') or '').strip().lower() == 'text'
        ]
        if not candidates and str(payload.get('saved_text_path') or payload.get('savedTextPath') or '').strip():
            candidates = [
                {
                    'type': 'text',
                    'path': payload.get('saved_text_path') or payload.get('savedTextPath'),
                    'text_artifact_request': payload.get('text_artifact_request')
                    if isinstance(payload.get('text_artifact_request'), Mapping)
                    else {},
                }
            ]
        for artifact in candidates:
            artifact_extension = _text_artifact_extension_from_record(artifact)
            if expected_extension and artifact_extension != expected_extension:
                continue
            if expected_source_name and not expected_extension:
                artifact_source_name = str(
                    artifact.get('name')
                    or (
                        artifact.get('text_artifact_request', {}).get('source_name')
                        if isinstance(artifact.get('text_artifact_request'), Mapping)
                        else ''
                    )
                    or ''
                ).strip().lower()
                if artifact_source_name != expected_source_name:
                    continue
            if str(artifact.get('path') or artifact.get('source_path') or '').strip():
                return True
        return False

    def response_payload_has_real_saved_artifact(
        self,
        payload: Optional[dict[str, Any]],
    ) -> bool:
        build_canonical_response_artifacts = self._hook('build_canonical_response_artifacts')

        if not isinstance(payload, Mapping):
            return False
        artifacts = payload.get('artifacts')
        if not isinstance(artifacts, list):
            artifacts = build_canonical_response_artifacts(dict(payload))
        for artifact in artifacts or []:
            if not isinstance(artifact, Mapping):
                continue
            if str(artifact.get('path') or '').strip():
                return True
        return False

    def _claimed_materialization_capabilities_from_text(self, text: str) -> list[str]:
        normalized = str(text or '').strip()
        capabilities: list[str] = []
        for capability, pattern in (
            (CAPABILITY_IMAGE_GENERATION, _TEXT_ONLY_IMAGE_CAPABILITY_CLAIM_RE),
            (CAPABILITY_TEXT_TO_SPEECH, _TEXT_ONLY_AUDIO_CAPABILITY_CLAIM_RE),
        ):
            if pattern.search(normalized) and capability not in capabilities:
                capabilities.append(capability)
        return capabilities

    def _instance_capability_set(self, instance: Mapping[str, Any]) -> set[str]:
        capabilities: set[str] = set()

        def add(raw_value: Any) -> None:
            normalized = normalize_capability(raw_value)
            if normalized:
                capabilities.add(normalized)

        for key in ('capability', 'mode'):
            add(instance.get(key))
        for key in (
            'supported_capabilities',
            'provider_capabilities',
            'capabilities',
            'instance_capabilities',
            'package_capabilities',
        ):
            values = instance.get(key)
            if isinstance(values, list):
                for value in values:
                    add(value)
        backend_metadata = instance.get('backend_metadata')
        if isinstance(backend_metadata, Mapping):
            for key in ('capabilities', 'instance_capabilities', 'package_capabilities'):
                values = backend_metadata.get(key)
                if isinstance(values, list):
                    for value in values:
                        add(value)
        return capabilities

    def _instance_is_runtime_available(self, instance: Mapping[str, Any]) -> bool:
        runtime_status = instance.get('runtime_status') if isinstance(instance.get('runtime_status'), Mapping) else {}
        readiness = str(runtime_status.get('readiness') or instance.get('readiness') or '').strip().lower()
        if readiness and readiness not in {'ready', 'degraded'}:
            return False
        process_alive = runtime_status.get('process_alive', instance.get('process_alive'))
        if process_alive is False:
            return False
        port_listening = runtime_status.get('port_listening', instance.get('port_listening'))
        if port_listening is False:
            return False
        return True

    def runtime_capability_availability(self, capability: Optional[str]) -> dict[str, Any]:
        normalized_capability = normalize_capability(capability)
        payload: dict[str, Any] = {
            'capability': normalized_capability or None,
            'status': 'unknown',
            'available': False,
            'instances': [],
        }
        if not normalized_capability:
            return payload

        load_running_instances = self.hooks.get('load_running_instances')
        merge_instances_with_runtime_status = self.hooks.get('merge_instances_with_runtime_status')
        if not callable(load_running_instances):
            payload['reason'] = 'runtime_instance_loader_unavailable'
            return payload

        try:
            instances = load_running_instances()
            if callable(merge_instances_with_runtime_status):
                kwargs: dict[str, Any] = {'refresh': True}
                runtime_status_path_getter = self.hooks.get('runtime_status_path_getter')
                if callable(runtime_status_path_getter):
                    path = runtime_status_path_getter()
                    if path:
                        kwargs['path'] = path
                instances = merge_instances_with_runtime_status(instances, **kwargs)
        except Exception as exc:
            logging.getLogger(__name__).debug(
                'failed to load runtime capability availability for %s',
                normalized_capability,
                exc_info=True,
            )
            payload['reason'] = 'runtime_instance_load_failed'
            payload['error'] = str(exc)
            return payload

        matching_instances: list[dict[str, Any]] = []
        for raw_instance in instances if isinstance(instances, list) else []:
            if not isinstance(raw_instance, Mapping):
                continue
            capabilities = self._instance_capability_set(raw_instance)
            if normalized_capability not in capabilities:
                continue
            instance_summary = {
                'instance_id': str(raw_instance.get('instance_id') or '').strip() or None,
                'model': str(raw_instance.get('model') or raw_instance.get('modelName') or '').strip() or None,
                'backend': str(raw_instance.get('backend') or '').strip() or None,
                'readiness': str(
                    (
                        raw_instance.get('runtime_status')
                        if isinstance(raw_instance.get('runtime_status'), Mapping)
                        else {}
                    ).get('readiness')
                    or raw_instance.get('readiness')
                    or ''
                ).strip() or None,
                'available': self._instance_is_runtime_available(raw_instance),
            }
            matching_instances.append(
                {
                    key: value
                    for key, value in instance_summary.items()
                    if value not in (None, '', [], {})
                }
            )
        available_instances = [item for item in matching_instances if item.get('available')]
        payload['instances'] = matching_instances
        if available_instances:
            payload['status'] = 'available'
            payload['available'] = True
            payload['available_instance_ids'] = [
                item.get('instance_id')
                for item in available_instances
                if item.get('instance_id')
            ]
            return payload
        if matching_instances:
            payload['status'] = 'unavailable'
            payload['reason'] = 'matching_instances_not_ready'
            return payload
        payload['status'] = 'unavailable'
        payload['reason'] = 'no_matching_running_instance'
        return payload

    def _truth_gate_text_only_artifact_claim(
        self,
        text: str,
    ) -> str:
        normalized = str(text or '').strip()
        if not normalized:
            return normalized
        match = _MARKDOWN_CODE_BLOCK_RE.search(normalized)
        if match:
            return (
                'No local file or downloadable artifact was created in this response. '
                'The content below exists only as response text.\n\n'
                f'{match.group(0).strip()}'
            ).strip()
        return (
            'No local file or downloadable artifact was created in this response. '
            'The content exists only as response text.'
        )

    def _truth_gate_annotated_text_only_artifact_claim(
        self,
        text: str,
    ) -> str:
        normalized = str(text or '').strip()
        prefix = (
            'Runtime truth: no separate local or downloadable artifacts were materialized in this response. '
            'Items labeled as artifacts, images, or fulfilled outputs below are response text unless an `outputs[]` '
            'entry or artifact record says otherwise.'
        )
        if normalized.startswith(prefix):
            return normalized
        if not normalized:
            return prefix
        return f'{prefix}\n\n{normalized}'

    def _truth_guard_predecessor_bundle_is_authorized(
        self,
        request_payload: Mapping[str, Any],
        raw_references: Any,
        sanitized_references: list[dict[str, Any]],
    ) -> bool:
        """Prove that a multi-reference expansion is one carried predecessor."""

        if not isinstance(raw_references, list):
            return False
        raw_items = [dict(item) for item in raw_references if isinstance(item, Mapping)]
        if len(raw_items) < 2 or len(raw_items) != len(sanitized_references):
            return False

        source_response_ids = {
            str(item.get('source_response_id') or '').strip()
            for item in raw_items
        }
        if len(source_response_ids) != 1 or not next(iter(source_response_ids), ''):
            return False
        source_response_id = next(iter(source_response_ids))
        current_conversation_id = str(
            request_payload.get('conversation_id')
            or request_payload.get('conversationId')
            or ''
        ).strip()
        if not current_conversation_id:
            return False

        carrier = next(
            (
                dict(item)
                for item in reversed(request_payload.get('inference_messages') or [])
                if isinstance(item, Mapping)
                and str(item.get('role') or '').strip().lower() == 'assistant'
                and str(item.get('response_id') or '').strip() == source_response_id
            ),
            None,
        )
        if not carrier:
            return False
        carrier_message_id = str(
            carrier.get('message_id') or carrier.get('messageId') or ''
        ).strip()
        carrier_content = str(carrier.get('content') or '').strip()
        if not carrier_message_id or not carrier_content:
            return False

        get_response_lookup_record = self.hooks.get('get_response_lookup_record')
        if not callable(get_response_lookup_record):
            return False
        try:
            predecessor_record = get_response_lookup_record(source_response_id)
        except Exception:  # noqa: BLE001 - predecessor truth lookup must fail closed
            return False
        if not isinstance(predecessor_record, Mapping):
            return False
        if str(predecessor_record.get('id') or '').strip() != source_response_id:
            return False
        predecessor_payload = (
            predecessor_record.get('response_payload')
            if isinstance(predecessor_record.get('response_payload'), Mapping)
            else {}
        )
        predecessor_frame = (
            predecessor_payload.get('response_frame')
            if isinstance(predecessor_payload.get('response_frame'), Mapping)
            else {}
        )
        predecessor_request = (
            predecessor_frame.get('request')
            if isinstance(predecessor_frame.get('request'), Mapping)
            else {}
        )
        predecessor_conversation_id = str(
            predecessor_request.get('conversation_id')
            or predecessor_request.get('conversationId')
            or ''
        ).strip()
        predecessor_message_id = str(
            predecessor_record.get('message_id') or ''
        ).strip()
        predecessor_lifecycle = str(
            predecessor_record.get('lifecycle_state')
            or predecessor_payload.get('lifecycle_state')
            or predecessor_payload.get('status')
            or ''
        ).strip().lower()
        if (
            predecessor_conversation_id != current_conversation_id
            or predecessor_message_id != carrier_message_id
            or predecessor_lifecycle not in {'completed', 'repair_needed'}
        ):
            return False
        predecessor_text = str(predecessor_payload.get('output_text') or '').strip()
        if not predecessor_text or predecessor_text != carrier_content:
            return False

        def _artifacts_by_ref(raw_artifacts: Any) -> dict[str, dict[str, Any]]:
            artifacts: dict[str, dict[str, Any]] = {}
            for raw_artifact in raw_artifacts if isinstance(raw_artifacts, list) else []:
                if not isinstance(raw_artifact, Mapping):
                    continue
                artifact = dict(raw_artifact)
                artifact_ref = str(
                    artifact.get('artifact_ref') or artifact.get('ref') or ''
                ).strip()
                if artifact_ref:
                    artifacts[artifact_ref] = artifact
            return artifacts

        carrier_artifacts = _artifacts_by_ref(carrier.get('artifacts'))
        predecessor_artifacts = _artifacts_by_ref(predecessor_payload.get('artifacts'))
        sanitized_artifacts = _artifacts_by_ref(sanitized_references)
        seen_artifact_refs: set[str] = set()
        for raw_item in raw_items:
            artifact_type = str(raw_item.get('type') or '').strip().lower()
            raw_source_message_id = str(
                raw_item.get('source_message_id')
                or raw_item.get('message_id')
                or raw_item.get('messageId')
                or ''
            ).strip()
            if raw_source_message_id != carrier_message_id:
                return False
            if artifact_type == 'message':
                raw_content = str(
                    raw_item.get('content')
                    or raw_item.get('text')
                    or raw_item.get('prompt')
                    or ''
                ).strip()
                if raw_content != carrier_content:
                    return False
                continue

            artifact_ref = str(
                raw_item.get('artifact_ref') or raw_item.get('ref') or ''
            ).strip()
            if not artifact_ref or artifact_ref in seen_artifact_refs:
                return False
            seen_artifact_refs.add(artifact_ref)
            carrier_artifact = carrier_artifacts.get(artifact_ref)
            predecessor_artifact = predecessor_artifacts.get(artifact_ref)
            sanitized_artifact = sanitized_artifacts.get(artifact_ref)
            if not carrier_artifact or not predecessor_artifact or not sanitized_artifact:
                return False
            canonical_type = str(
                predecessor_artifact.get('type')
                or predecessor_artifact.get('kind')
                or ''
            ).strip().lower()
            if artifact_type and canonical_type and artifact_type != canonical_type:
                return False
            canonical_path = str(
                predecessor_artifact.get('path')
                or predecessor_artifact.get('source_path')
                or ''
            ).strip()
            carrier_path = str(
                carrier_artifact.get('path')
                or carrier_artifact.get('source_path')
                or ''
            ).strip()
            sanitized_path = str(
                sanitized_artifact.get('path')
                or sanitized_artifact.get('source_path')
                or ''
            ).strip()
            if not canonical_path or carrier_path != canonical_path or sanitized_path != canonical_path:
                return False
            canonical_artifact_id = str(predecessor_artifact.get('artifact_id') or '').strip()
            raw_artifact_id = str(raw_item.get('artifact_id') or '').strip()
            if raw_artifact_id and canonical_artifact_id != raw_artifact_id:
                return False
        return True

    def _truth_guard_request_payload(
        self,
        request_payload: Optional[Mapping[str, Any]],
    ) -> Optional[dict[str, Any]]:
        if not isinstance(request_payload, Mapping):
            return None
        sanitized_payload = dict(request_payload)
        sanitize_selected_references = self.hooks.get(
            'sanitize_selected_reference_artifacts'
        )
        if not callable(sanitize_selected_references):
            return sanitized_payload

        def _sanitize_records(raw_value: Any) -> list[dict[str, Any]]:
            try:
                sanitized_records = sanitize_selected_references(raw_value)
            except Exception:  # noqa: BLE001 - malformed client evidence must fail closed
                return []
            return [
                dict(item)
                for item in sanitized_records
                if isinstance(item, Mapping)
            ]

        def _sanitize_record_collection(raw_value: Any) -> list[dict[str, Any]]:
            if not isinstance(raw_value, list):
                return _sanitize_records(raw_value)
            sanitized_collection: list[dict[str, Any]] = []
            for raw_item in raw_value:
                sanitized_collection.extend(_sanitize_records(raw_item))
            return sanitized_collection

        raw_selected_references = (
            request_payload.get('reference_artifacts')
            if request_payload.get('reference_artifacts') is not None
            else request_payload.get('selected_reference_artifact')
            if request_payload.get('selected_reference_artifact') is not None
            else request_payload.get('selectedReferenceArtifact')
            if request_payload.get('selectedReferenceArtifact') is not None
            else request_payload.get('selected_reference_artifacts')
            if request_payload.get('selected_reference_artifacts') is not None
            else request_payload.get('selectedReferenceArtifacts')
        )
        # Collection normalization preserves files; its output length is not
        # evidence that a carried predecessor message/bundle is authorized.
        compatibility_selected_references = _sanitize_records(raw_selected_references)
        expanded_selected_references = _sanitize_record_collection(raw_selected_references)
        predecessor_bundle_verified = (
            isinstance(raw_selected_references, list)
            and len(raw_selected_references) >= 2
            and self._truth_guard_predecessor_bundle_is_authorized(
                request_payload,
                raw_selected_references,
                expanded_selected_references,
            )
        )
        carried_predecessor_bundle_claim = bool(
            isinstance(raw_selected_references, list)
            and len(raw_selected_references) >= 2
            and any(
                isinstance(item, Mapping)
                and str(item.get('type') or '').strip().lower() == 'message'
                and str(item.get('source_response_id') or '').strip()
                for item in raw_selected_references
            )
        )
        if predecessor_bundle_verified:
            selected_references = expanded_selected_references
        elif carried_predecessor_bundle_claim:
            # Neither the claimed message nor its files can ground this guard
            # after the canonical bundle proof fails. Independent explicit
            # file selections (without a carried message claim) stay intact.
            selected_references = []
        else:
            selected_references = compatibility_selected_references
        raw_predecessor_context = request_payload.get(
            'current_predecessor_context'
        )
        sanitized_payload.pop('current_predecessor_context', None)
        if predecessor_bundle_verified and isinstance(
            raw_predecessor_context,
            Mapping,
        ):
            context_source_response_id = str(
                raw_predecessor_context.get('source_response_id') or ''
            ).strip()
            reference_source_response_ids = {
                str(item.get('source_response_id') or '').strip()
                for item in (
                    raw_selected_references
                    if isinstance(raw_selected_references, list)
                    else []
                )
                if isinstance(item, Mapping)
                and str(item.get('source_response_id') or '').strip()
            }
            get_response_lookup_record = self.hooks.get(
                'get_response_lookup_record'
            )
            predecessor_record = None
            if (
                callable(get_response_lookup_record)
                and len(reference_source_response_ids) == 1
                and context_source_response_id in reference_source_response_ids
            ):
                try:
                    predecessor_record = get_response_lookup_record(
                        context_source_response_id
                    )
                except Exception:  # noqa: BLE001 - context proof must fail closed
                    predecessor_record = None
            predecessor_payload = (
                predecessor_record.get('response_payload')
                if isinstance(predecessor_record, Mapping)
                and isinstance(
                    predecessor_record.get('response_payload'),
                    Mapping,
                )
                else {}
            )
            canonical_prompts = extract_canonical_predecessor_image_prompts(
                predecessor_payload
            )
            if not canonical_prompts:
                predecessor_late_fill = (
                    predecessor_payload.get('late_fill')
                    if isinstance(predecessor_payload.get('late_fill'), Mapping)
                    else {}
                )
                prepared_content = str(
                    predecessor_late_fill.get('content_payload')
                    or predecessor_payload.get('content_payload')
                    or ''
                ).strip()
                if prepared_content:
                    canonical_prompts = image_prompt_preparation.extract_batch_image_prompts(
                        prepared_content,
                        expected_count=0,
                        allow_plain_alpha_sequence=False,
                    )
            claimed_prompts = [
                str(item).strip()
                for item in (
                    raw_predecessor_context.get('batch_prompts') or []
                )
                if str(item).strip()
            ]
            if canonical_prompts and claimed_prompts == canonical_prompts:
                sanitized_payload['current_predecessor_context'] = {
                    'kind': 'fruth.current_predecessor_context',
                    'status': 'authorized',
                    'authorization': (
                        'canonical_same_conversation_predecessor'
                    ),
                    'source_response_id': context_source_response_id,
                    'source_message_id': str(
                        raw_predecessor_context.get('source_message_id') or ''
                    ).strip(),
                    'batch_prompts': canonical_prompts,
                    'text_artifact_refs': [
                        str(item).strip()
                        for item in (
                            raw_predecessor_context.get(
                                'text_artifact_refs'
                            )
                            or []
                        )
                        if str(item).strip()
                    ],
                }
        for key in (
            'reference_artifacts',
            'selected_reference_artifact',
            'selectedReferenceArtifact',
            'selected_reference_artifacts',
            'selectedReferenceArtifacts',
        ):
            sanitized_payload.pop(key, None)
        sanitized_payload['selected_reference_artifacts'] = selected_references

        sanitized_input_artifacts: list[dict[str, Any]] = []
        raw_input_artifacts = request_payload.get('input_artifacts')
        if isinstance(raw_input_artifacts, list):
            for raw_input_artifact in raw_input_artifacts:
                sanitized_input_artifacts.extend(
                    _sanitize_records(raw_input_artifact)
                )
        for key in ('file_path', 'route_artifact_path', 'artifact_path'):
            raw_path = str(request_payload.get(key) or '').strip()
            sanitized_payload.pop(key, None)
            if not raw_path:
                continue
            path_capabilities = _direct_artifact_record_source_capabilities(
                {'path': raw_path}
            )
            artifact_type = (
                'image'
                if path_capabilities == {CAPABILITY_IMAGE_GENERATION}
                else 'audio'
                if path_capabilities == {CAPABILITY_TEXT_TO_SPEECH}
                else 'text'
                if path_capabilities == {CAPABILITY_CHAT}
                else ''
            )
            if artifact_type:
                sanitized_input_artifacts.extend(
                    _sanitize_records({'type': artifact_type, 'path': raw_path})
                )
        sanitized_payload['input_artifacts'] = sanitized_input_artifacts
        return sanitized_payload

    def truth_gate_response_output_claims(
        self,
        payload: Optional[dict[str, Any]],
        *,
        route_payload: Optional[dict[str, Any]] = None,
        request_payload: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        text = str(payload.get('output_text') or payload.get('content') or '').strip()
        prior_runtime = payload.get('runtime') if isinstance(payload.get('runtime'), Mapping) else {}
        prior_guard = prior_runtime.get('truth_guard') if isinstance(prior_runtime.get('truth_guard'), Mapping) else {}
        prior_projection = prior_guard.get('text_projection') if isinstance(prior_guard.get('text_projection'), Mapping) else {}
        already_corrected_claim = (
            prior_guard.get('kind') == 'local_artifact_claims'
            and prior_guard.get('status') in {'rewritten', 'annotated'}
            and prior_projection.get('corrected_sha256') == hashlib.sha256(text.encode('utf-8')).hexdigest()
        )
        truth_request_payload = self._truth_guard_request_payload(request_payload)
        request_prompt = ''
        if isinstance(truth_request_payload, Mapping):
            request_prompt = extract_responses_current_turn_prompt(truth_request_payload) or str(
                truth_request_payload.get('prompt') or truth_request_payload.get('input') or ''
            ).strip()
        if (
            text
            and request_prompt
            and (
                _request_requires_current_source_for_transform(
                    request_prompt,
                    request_payload=truth_request_payload,
                    route_payload=route_payload,
                    response_payload=payload,
                )
                or (
                    detect_text_artifact_requests(
                        request_prompt,
                        source_available=True,
                    )
                    and text_artifact_request_is_ungrounded_reference(
                        request_prompt,
                        source_available=_payload_has_direct_artifact_source(
                            truth_request_payload,
                            route_payload,
                            payload,
                        )
                        or _prompt_has_actionable_inline_text_source(request_prompt),
                    )
                )
            )
        ):
            rewritten_text = (
                'I need the source/content for the referenced file before I can create that artifact. '
                'Please provide or select the HTML/code/content to materialize.'
            )
            updated = dict(payload)
            updated['output_text'] = rewritten_text
            if 'content' in updated and isinstance(updated.get('content'), str):
                updated['content'] = rewritten_text
            runtime = dict(updated.get('runtime') or {}) if isinstance(updated.get('runtime'), Mapping) else {}
            runtime['truth_guard'] = {
                'kind': 'ungrounded_text_artifact_reference',
                'status': 'clarification_required',
                'reason': 'artifact request used a demonstrative reference without a current or selected source',
            }
            updated['runtime'] = runtime
            return updated
        response_capability = str(
            payload.get('capability')
            or (route_payload or {}).get('capability')
            or (request_payload or {}).get('capability')
            or ''
        ).strip()
        control_json_leak = control_json_envelope_suspected(text) and not request_explicitly_allows_control_diagnostics(
            request_payload=truth_request_payload,
            route_payload=route_payload,
            capability=response_capability,
        )
        explicit_false_claim = not already_corrected_claim and bool(_FALSE_LOCAL_ARTIFACT_CLAIM_RE.search(text))
        soft_materialization_claim = not already_corrected_claim and bool(_TEXT_ONLY_MATERIALIZATION_CLAIM_RE.search(text))
        if not text or not (control_json_leak or explicit_false_claim or soft_materialization_claim):
            return dict(payload)
        if not control_json_leak and self.response_payload_has_real_saved_artifact(payload):
            return dict(payload)

        updated = dict(payload)
        if control_json_leak:
            acceptance = classify_phase_output_text(text)
            substantive_payload = str(acceptance.get('accepted_text') or '').strip()
            rewritten_text = substantive_payload or (
                'Runtime truth: internal planner/control JSON was withheld from the user-facing answer. '
                'The requested output remains open until a real response or artifact payload is materialized.'
            )
            guard_status = 'unwrapped' if substantive_payload else 'repair_required'
            guard_reason = (
                'internal control JSON was unwrapped to its substantive content_payload'
                if substantive_payload
                else 'internal control JSON leaked into visible output'
            )
            guard_kind = 'control_json_boundary'
        elif explicit_false_claim:
            rewritten_text = self._truth_gate_text_only_artifact_claim(text)
            guard_status = 'rewritten'
            guard_reason = 'response claimed local file or artifact creation without runtime artifact truth'
            guard_kind = 'local_artifact_claims'
        else:
            rewritten_text = self._truth_gate_annotated_text_only_artifact_claim(text)
            guard_status = 'annotated'
            guard_reason = 'response labeled text sections as materialized artifacts without runtime artifact truth'
            guard_kind = 'local_artifact_claims'
        claimed_capabilities = self._claimed_materialization_capabilities_from_text(text)
        updated['output_text'] = rewritten_text
        if 'content' in updated and isinstance(updated.get('content'), str):
            updated['content'] = rewritten_text
        runtime = dict(updated.get('runtime') or {}) if isinstance(updated.get('runtime'), Mapping) else {}
        runtime['truth_guard'] = {
            'kind': guard_kind,
            'status': guard_status,
            'reason': guard_reason,
            **(
                {
                    'repair_action': RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT,
                    'runtime_effect': 'materialization_blocked',
                }
                if guard_status == 'repair_required'
                else {}
            ),
            **({'claimed_capabilities': claimed_capabilities} if claimed_capabilities else {}),
        }
        if control_json_leak:
            runtime['phase_output_acceptance'] = phase_output_acceptance_metadata([acceptance])
        if guard_kind == 'local_artifact_claims':
            projection = truth_guard_text_projection(payload, text, rewritten_text)
            if projection:
                runtime['truth_guard']['text_projection'] = projection
        updated['runtime'] = runtime
        for key in ('outputs', 'output_slots', 'output_branches'):
            if isinstance(updated.get(key), list):
                updated[key] = project_truth_guard_text(updated, updated[key])
        return updated

    def _current_phase_payload(self, phase_graph: Optional[dict[str, Any]]) -> dict[str, Any]:
        return self.phase_preparation._current_phase_payload(phase_graph)

    def _request_is_inference_owned(
        self,
        *,
        route_payload: Optional[dict[str, Any]] = None,
        request_payload: Optional[dict[str, Any]] = None,
    ) -> bool:
        return self.phase_preparation._request_is_inference_owned(route_payload=route_payload, request_payload=request_payload)

    def build_inference_runtime_policy_system_message(
        self,
        *,
        route_payload: Optional[dict[str, Any]] = None,
        request_payload: Optional[dict[str, Any]] = None,
        backend: Optional[str] = None,
    ) -> Optional[dict[str, str]]:
        return self.phase_preparation.build_inference_runtime_policy_system_message(route_payload=route_payload, request_payload=request_payload, backend=backend)

    def inject_inference_runtime_policy_into_chat_messages(
        self,
        messages: list[dict[str, Any]],
        *,
        route_payload: Optional[dict[str, Any]] = None,
        request_payload: Optional[dict[str, Any]] = None,
        backend: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        return self.phase_preparation.inject_inference_runtime_policy_into_chat_messages(messages, route_payload=route_payload, request_payload=request_payload, backend=backend)

    def _extract_semantic_phase_payload_from_payload(self, payload: Any) -> dict[str, Any]:
        return self.phase_preparation._extract_semantic_phase_payload_from_payload(payload)

    def semantic_payload_for_capability(
        self,
        payload: Optional[dict[str, Any]],
        *,
        capability: Optional[str],
    ) -> dict[str, Any]:
        return self.phase_preparation.semantic_payload_for_capability(payload, capability=capability)

    extract_batch_image_prompts = staticmethod(image_prompt_preparation.extract_batch_image_prompts)

    _extract_labeled_multi_image_prompts = staticmethod(image_prompt_preparation._extract_labeled_multi_image_prompts)

    def _expand_image_pending_branches_from_batch_prompts(
        self,
        pending_branches: list[dict[str, Any]],
        batch_prompts: Any,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        prompts = [
            str(item).strip()
            for item in (batch_prompts or [])
            if str(item).strip()
        ] if isinstance(batch_prompts, list) else []
        if len(prompts) <= 1:
            return pending_branches, {}
        expanded = [
            dict(item)
            for item in (pending_branches or [])
            if isinstance(item, Mapping)
        ]
        image_branches = [
            item
            for item in expanded
            if normalize_capability(item.get('capability')) == CAPABILITY_IMAGE_GENERATION
        ]
        existing_count = len(image_branches)
        if existing_count >= len(prompts) or existing_count <= 0:
            return expanded, {}
        seen_ids = {
            str(item.get('branch_id') or item.get('phase_id') or '').strip()
            for item in expanded
            if str(item.get('branch_id') or item.get('phase_id') or '').strip()
        }
        template = dict(image_branches[-1])

        def sibling_identifier(seed: Any, index: int, fallback_prefix: str) -> str:
            token = str(seed or '').strip()
            match = re.match(r'^(?P<prefix>.*?)(?P<number>\d+)$', token)
            if match and match.group('prefix'):
                candidate = f"{match.group('prefix')}{index}"
            else:
                candidate = f'{fallback_prefix}{index}'
            base = candidate
            suffix = 2
            while candidate in seen_ids:
                candidate = f'{base}-{suffix}'
                suffix += 1
            seen_ids.add(candidate)
            return candidate

        for prompt_index in range(existing_count + 1, len(prompts) + 1):
            branch_id = sibling_identifier(
                template.get('branch_id') or 'branch-image_generation-1',
                prompt_index,
                'branch-image_generation-',
            )
            phase_id = sibling_identifier(
                template.get('phase_id') or 'phase-2',
                prompt_index + 1,
                'phase-',
            )
            obligation_id = ''
            raw_obligation_id = str(template.get('obligation_id') or '').strip()
            if raw_obligation_id:
                obligation_id = sibling_identifier(
                    raw_obligation_id,
                    prompt_index + 1,
                    'obligation-phase-',
                )
            branch = {
                'branch_id': branch_id,
                'phase_id': phase_id,
                'capability': CAPABILITY_IMAGE_GENERATION,
                'output_type': 'image',
                'depends_on': [
                    str(item).strip()
                    for item in (template.get('depends_on') or ['phase-1'])
                    if str(item).strip()
                ],
                'queue_index': prompt_index,
                'status': str(template.get('status') or 'pending').strip().lower() or 'pending',
                'branch_expansion_source': 'prepared_image_prompt_units',
                'branch_expansion_prompt_index': prompt_index,
                'branch_expansion_original_branch_count': existing_count,
            }
            if obligation_id:
                branch['obligation_id'] = obligation_id
            for key in (
                'stage_direction',
                'content_payload',
                'content_payload_source',
                'phase_summary',
                'requires_artifact',
                'runtime_scheduling_context',
                'allow_gpu_heavy_concurrency',
            ):
                value = template.get(key)
                if value not in (None, '', [], {}):
                    branch[key] = value
            expanded.append(branch)
        return expanded, {
            'status': 'applied',
            'source': 'prepared_image_prompt_units',
            'original_image_branch_count': existing_count,
            'prepared_prompt_count': len(prompts),
            'added_branch_count': len(prompts) - existing_count,
        }

    def _extract_pending_deferred_capabilities(
        self,
        *,
        route_payload: Optional[dict[str, Any]] = None,
        artifact_payload: Optional[dict[str, Any]] = None,
    ) -> list[str]:
        pending_branches = self._extract_pending_deferred_branches(
            route_payload=route_payload,
            artifact_payload=artifact_payload,
        )
        return self._hook('normalize_capability_list')(
            [item.get('capability') for item in pending_branches if isinstance(item, Mapping)]
        )

    def _extract_pending_deferred_branches(
        self,
        *,
        route_payload: Optional[dict[str, Any]] = None,
        artifact_payload: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        normalize_capability_list = self._hook('normalize_capability_list')

        route_info = route_payload if isinstance(route_payload, dict) else {}
        artifact_info = artifact_payload if isinstance(artifact_payload, dict) else {}
        artifact_late_fill = (
            artifact_info.get('late_fill')
            if isinstance(artifact_info.get('late_fill'), dict)
            else {}
        )
        pending_from_state = artifact_late_fill.get('pending_branches')
        completed_capabilities = set(
            normalize_capability_list(artifact_late_fill.get('completed_capabilities'))
        )
        completed_branch_ids = {
            str(item.get('branch_id') or item.get('phase_id') or '').strip()
            for item in (artifact_late_fill.get('completed_branches') or [])
            if isinstance(item, Mapping) and str(item.get('branch_id') or item.get('phase_id') or '').strip()
        }
        failed_branch_ids = {
            str(item.get('branch_id') or item.get('phase_id') or '').strip()
            for item in (artifact_late_fill.get('failed_branches') or [])
            if isinstance(item, Mapping) and str(item.get('branch_id') or item.get('phase_id') or '').strip()
        }
        candidates: list[dict[str, Any]] = []

        def records_share_branch_identity(
            left: Mapping[str, Any],
            right: Mapping[str, Any],
        ) -> bool:
            left_capability = normalize_capability(left.get('capability'))
            right_capability = normalize_capability(right.get('capability'))
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

        def remember_candidate(candidate: dict[str, Any]) -> None:
            def branch_payload_score(source: Mapping[str, Any]) -> int:
                branch_id = str(source.get('branch_id') or '').strip()
                phase_id = str(source.get('phase_id') or '').strip()
                score = 4 if branch_id and phase_id and branch_id != phase_id else 0
                for key in (
                    'artifact_prompt',
                    'artifact_prompt_source',
                    'content_payload',
                    'content_payload_source',
                    'phase_summary',
                    'stage_direction',
                    'batch_prompts',
                ):
                    if source.get(key) not in (None, '', [], {}):
                        score += 2
                if source.get('depends_on') not in (None, '', [], {}):
                    score += 1
                return score

            for existing in candidates:
                if not records_share_branch_identity(existing, candidate):
                    continue
                primary, supplement = (
                    (candidate, existing)
                    if branch_payload_score(candidate) > branch_payload_score(existing)
                    else (existing, candidate)
                )
                merged = dict(primary)
                for key, value in supplement.items():
                    if merged.get(key) in (None, '', [], {}) and value not in (
                        None,
                        '',
                        [],
                        {},
                    ):
                        merged[key] = value
                existing.clear()
                existing.update(merged)
                return
            candidates.append(candidate)

        if isinstance(pending_from_state, list) and pending_from_state:
            for item in pending_from_state:
                if isinstance(item, Mapping):
                    remember_candidate(dict(item))
            return candidates
        route_runtime = (
            route_info.get('route_runtime')
            if isinstance(route_info.get('route_runtime'), dict)
            else {}
        )
        artifact_runtime = (
            artifact_info.get('runtime')
            if isinstance(artifact_info.get('runtime'), dict)
            else {}
        )
        artifact_request_phase_graph = (
            artifact_runtime.get('request_phase_graph')
            if isinstance(artifact_runtime.get('request_phase_graph'), dict)
            else None
        )
        route_request_phase_graph = (
            route_runtime.get('request_phase_graph')
            if isinstance(route_runtime.get('request_phase_graph'), dict)
            else None
        )
        request_phase_graph = (
            artifact_request_phase_graph
            if artifact_request_phase_graph
            else route_request_phase_graph
        )
        defer_downstream_execution = self._request_graph_defers_downstream_execution(request_phase_graph)
        prompt_intent = (request_phase_graph or {}).get('prompt_intent') or {}
        execution_planner = (
            route_runtime.get('execution_planner')
            if isinstance(route_runtime.get('execution_planner'), dict)
            else (
                ((artifact_info.get('runtime') or {}).get('execution_planner'))
                if isinstance(artifact_info.get('runtime'), dict)
                and isinstance((artifact_info.get('runtime') or {}).get('execution_planner'), dict)
                else {}
            )
        )
        for raw_branch in (
            execution_planner.get('deferred_branches')
            if isinstance(execution_planner.get('deferred_branches'), list)
            else []
        ):
            if not isinstance(raw_branch, Mapping):
                continue
            if (
                defer_downstream_execution
                or materialization_is_deferred(prompt_intent, raw_branch)
                or intent_coverage._branch_record_is_non_executable_candidate(raw_branch)
                or self._branch_record_is_terminally_fulfilled(raw_branch)
            ):
                continue
            capability = normalize_capability(raw_branch.get('capability'))
            branch_id = str(raw_branch.get('branch_id') or raw_branch.get('phase_id') or '').strip()
            phase_id = str(raw_branch.get('phase_id') or raw_branch.get('branch_id') or '').strip()
            identity = branch_id or phase_id
            if not capability:
                continue
            if not identity:
                continue
            if identity in completed_branch_ids or identity in failed_branch_ids:
                continue
            remember_candidate(
                {
                    'branch_id': branch_id or phase_id,
                    'phase_id': phase_id or branch_id,
                    'obligation_id': str(raw_branch.get('obligation_id') or '').strip() or None,
                    'capability': capability,
                    'output_type': str(raw_branch.get('output_type') or '').strip().lower() or intent_coverage.artifact_type_for_capability(capability),
                    'depends_on': [
                        str(item).strip()
                        for item in (raw_branch.get('depends_on') or [])
                        if str(item).strip()
                    ],
                    **{
                        key: raw_branch.get(key)
                        for key in (
                            'queue_index',
                            'artifact_prompt',
                            'artifact_prompt_source',
                            'content_payload',
                            'content_payload_source',
                            'phase_summary',
                            'stage_direction',
                            'batch_prompts',
                            'requires_artifact',
                            'text_artifact_extension',
                            'text_artifact_source_name',
                            'text_artifact_source',
                            'text_artifact_target_path',
                            'artifact_request',
                        )
                        if raw_branch.get(key) not in (None, '', [], {})
                    },
                }
            )
        for candidate in downstream_phase_records(request_phase_graph or {}):
            if (
                defer_downstream_execution
                or materialization_is_deferred(prompt_intent, candidate)
                or intent_coverage._branch_record_is_non_executable_candidate(candidate)
                or self._branch_record_is_terminally_fulfilled(candidate)
            ):
                continue
            capability = normalize_capability(candidate.get('capability'))
            branch_id = str(candidate.get('branch_id') or candidate.get('phase_id') or '').strip()
            phase_id = str(candidate.get('phase_id') or candidate.get('branch_id') or '').strip()
            identity = branch_id or phase_id
            if not capability:
                continue
            if not identity:
                continue
            if identity in completed_branch_ids or identity in failed_branch_ids:
                continue
            remember_candidate(
                {
                    'branch_id': branch_id or phase_id,
                    'phase_id': phase_id or branch_id,
                    'obligation_id': str(candidate.get('obligation_id') or '').strip() or None,
                    'capability': capability,
                    'output_type': str(candidate.get('output_type') or '').strip().lower() or intent_coverage.artifact_type_for_capability(capability),
                    'depends_on': [
                        str(item).strip()
                        for item in (candidate.get('depends_on') or [])
                        if str(item).strip()
                    ],
                    **{
                        key: candidate.get(key)
                        for key in (
                            'queue_index',
                            'artifact_prompt',
                            'artifact_prompt_source',
                            'content_payload',
                            'content_payload_source',
                            'phase_summary',
                            'stage_direction',
                            'batch_prompts',
                            'requires_artifact',
                            'text_artifact_extension',
                            'text_artifact_source_name',
                            'text_artifact_source',
                            'text_artifact_target_path',
                            'artifact_request',
                        )
                        if candidate.get(key) not in (None, '', [], {})
                    },
                }
            )
        for candidate in output_obligations_from_graph(request_phase_graph or {}):
            if str(candidate.get('role') or '').strip() == 'preparation_output':
                continue
            if (
                defer_downstream_execution
                or materialization_is_deferred(prompt_intent, candidate)
                or intent_coverage._branch_record_is_non_executable_candidate(candidate)
                or self._branch_record_is_terminally_fulfilled(candidate)
            ):
                continue
            graph_current_phase_id = ''
            if isinstance(request_phase_graph, Mapping):
                graph_current_phase_id = str(request_phase_graph.get('current_phase_id') or '').strip()
            capability = normalize_capability(candidate.get('capability'))
            branch_id = str(candidate.get('branch_id') or candidate.get('phase_id') or '').strip()
            phase_id = str(candidate.get('phase_id') or candidate.get('branch_id') or '').strip()
            if graph_current_phase_id and phase_id == graph_current_phase_id:
                continue
            identity = branch_id or phase_id
            if not capability or not identity:
                continue
            if identity in completed_branch_ids or identity in failed_branch_ids:
                continue
            remember_candidate(
                {
                    'branch_id': branch_id or phase_id,
                    'phase_id': phase_id or branch_id,
                    'obligation_id': str(candidate.get('obligation_id') or '').strip() or None,
                    'capability': capability,
                    'output_type': str(candidate.get('output_type') or '').strip().lower() or intent_coverage.artifact_type_for_capability(capability),
                    'depends_on': [
                        str(item).strip()
                        for item in (candidate.get('depends_on') or [])
                        if str(item).strip()
                    ],
                    **{
                        key: candidate.get(key)
                        for key in (
                            'queue_index',
                            'artifact_prompt',
                            'artifact_prompt_source',
                            'content_payload',
                            'content_payload_source',
                            'phase_summary',
                            'stage_direction',
                            'batch_prompts',
                            'requires_artifact',
                            'text_artifact_extension',
                            'text_artifact_source_name',
                            'text_artifact_source',
                            'text_artifact_target_path',
                            'artifact_request',
                        )
                        if candidate.get(key) not in (None, '', [], {})
                    },
                }
            )
        if not candidates:
            if not defer_downstream_execution and not prompt_intent.get('explicit_defer_materialization'):
                for candidate in normalize_capability_list(execution_planner.get('deferred_capabilities')):
                    if candidate in completed_capabilities:
                        continue
                    if candidate in {normalize_capability(item.get('capability')) for item in candidates}:
                        continue
                    candidates.append(
                        {
                            'branch_id': f'branch-{candidate}-{len(candidates) + 1}',
                            'phase_id': f'branch-{candidate}-{len(candidates) + 1}',
                            'capability': candidate,
                            'output_type': intent_coverage.artifact_type_for_capability(candidate),
                            'depends_on': ['phase-1'],
                        }
                    )
                deferred_capability = normalize_capability(execution_planner.get('deferred_capability'))
                if deferred_capability and deferred_capability not in completed_capabilities and deferred_capability not in {
                    normalize_capability(item.get('capability')) for item in candidates
                }:
                    candidates.append(
                        {
                            'branch_id': f'branch-{deferred_capability}-{len(candidates) + 1}',
                            'phase_id': f'branch-{deferred_capability}-{len(candidates) + 1}',
                            'capability': deferred_capability,
                            'output_type': intent_coverage.artifact_type_for_capability(deferred_capability),
                            'depends_on': ['phase-1'],
                        }
                    )
        return candidates

    def extract_pending_deferred_branches(
        self,
        *,
        route_payload: Optional[dict[str, Any]] = None,
        artifact_payload: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        return self._extract_pending_deferred_branches(
            route_payload=route_payload,
            artifact_payload=artifact_payload,
        )

    def extract_pending_deferred_capabilities(
        self,
        *,
        route_payload: Optional[dict[str, Any]] = None,
        artifact_payload: Optional[dict[str, Any]] = None,
    ) -> list[str]:
        return self._extract_pending_deferred_capabilities(
            route_payload=route_payload,
            artifact_payload=artifact_payload,
        )

    def build_planner_deferred_follow_up_gap_spec(
        self,
        output_text: str,
        *,
        route_payload: Optional[dict[str, Any]] = None,
        artifact_payload: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        normalize_capability_list = self._hook('normalize_capability_list')

        route_info = route_payload if isinstance(route_payload, dict) else {}
        route_runtime = (
            route_info.get('route_runtime')
            if isinstance(route_info.get('route_runtime'), dict)
            else {}
        )
        pending_branches = self._extract_pending_deferred_branches(
            route_payload=route_payload,
            artifact_payload=artifact_payload,
        )
        if not pending_branches:
            return None
        pending_capabilities = normalize_capability_list(
            [item.get('capability') for item in pending_branches if isinstance(item, Mapping)]
        )
        for raw_expected_branch in pending_branches:
            if not isinstance(raw_expected_branch, Mapping):
                continue
            expected_branch = dict(raw_expected_branch)
            expected_capability = normalize_capability(expected_branch.get('capability'))
            missing_artifact_type = intent_coverage.artifact_type_for_capability(expected_capability)
            if not missing_artifact_type and self.source_requires_text_artifact(
                expected_branch,
                str(expected_branch.get('output_type') or '').strip().lower(),
            ):
                missing_artifact_type = 'text'
            if not missing_artifact_type:
                continue
            semantic_payload = self.phase_preparation.semantic_payload_for_capability(
                artifact_payload,
                capability=expected_capability,
            )
            payload = {
                'code': 'deferred_follow_up_fill',
                'trigger': 'execution_planner_deferred_follow_up',
                'expected_branch_id': str(expected_branch.get('branch_id') or expected_branch.get('phase_id') or '').strip() or None,
                'expected_phase_id': str(expected_branch.get('phase_id') or expected_branch.get('branch_id') or '').strip() or None,
                'expected_capability': expected_capability,
                'missing_artifact_type': missing_artifact_type,
                'pending_branches': pending_branches,
                'pending_capabilities': pending_capabilities,
                'completed_capabilities': normalize_capability_list(
                    (
                        (artifact_payload or {}).get('late_fill', {})
                        if isinstance((artifact_payload or {}).get('late_fill'), dict)
                        else {}
                    ).get('completed_capabilities')
                ),
                'planner_reason': str(
                    (
                        route_runtime.get('execution_planner')
                        if isinstance(route_runtime.get('execution_planner'), dict)
                        else {}
                    ).get('reason') or ''
                ).strip() or None,
            }
            for key in (
                'stage_direction',
                'phase_summary',
                'requires_artifact',
                'text_artifact_extension',
                'text_artifact_source_name',
                'text_artifact_source',
                'text_artifact_target_path',
                'artifact_request',
            ):
                value = expected_branch.get(key)
                if value not in (None, '', [], {}):
                    payload[key] = value
            if semantic_payload:
                for key in ('content_payload', 'stage_direction', 'phase_summary', 'content_payload_source'):
                    value = semantic_payload.get(key)
                    if value not in (None, '', [], {}):
                        payload[key] = value
                for key in (
                    'content_payload',
                    'phase_summary',
                    'artifact_prompt',
                    'artifact_prompt_source',
                    'batch_prompts',
                    'batch_prompts_source',
                    'batch_prompt_source_phase_id',
                    'batch_prompt_expected_count',
                    'batch_prompt_expected_count_invalid',
                    'batch_prompt_actual_count',
                    'branch_contract_error',
                    'candidate_extraction_issue',
                    'materialization_blocked',
                    'repair_action',
                    'counted_batch_prompt_carriers_blocked',
                ):
                    value = semantic_payload.get(key)
                    if value not in (None, '', [], {}):
                        payload[key] = value
                if (
                    expected_capability == CAPABILITY_IMAGE_GENERATION
                    and semantic_payload.get('materialization_blocked') is True
                    and str(semantic_payload.get('branch_contract_error') or '').strip()
                    == 'incomplete_image_prompt_batch'
                ):
                    for key in (
                        'content_payload',
                        'phase_summary',
                        'artifact_prompt',
                        'artifact_prompt_source',
                        'batch_prompts',
                        'batch_prompts_source',
                        'batch_prompt_source_phase_id',
                        'batch_prompt_expected_count',
                    ):
                        payload.pop(key, None)
                    return payload
                if self.artifact_gap_is_already_fulfilled(payload, artifact_payload):
                    continue
                expanded_branches, expansion = self._expand_image_pending_branches_from_batch_prompts(
                    pending_branches,
                    payload.get('batch_prompts'),
                )
                if expansion:
                    payload['pending_branches'] = expanded_branches
                    payload['pending_capabilities'] = normalize_capability_list(
                        [item.get('capability') for item in expanded_branches]
                    )
                    payload['prepared_image_prompt_branch_expansion'] = expansion
                return payload
            if str(output_text or '').strip():
                if expected_capability == CAPABILITY_TEXT_TO_SPEECH:
                    fallback_payload = split_visible_tts_payload(output_text)
                    for key in ('content_payload', 'stage_direction', 'phase_summary', 'content_payload_source'):
                        value = fallback_payload.get(key)
                        if value not in (None, '', [], {}):
                            payload[key] = value
                elif expected_capability == CAPABILITY_IMAGE_GENERATION:
                    fallback_payload = split_visible_image_payload(output_text)
                    for key in ('content_payload', 'phase_summary', 'artifact_prompt', 'artifact_prompt_source'):
                        value = fallback_payload.get(key)
                        if value not in (None, '', [], {}):
                            payload[key] = value
                    expected_count = 0
                    invalid_expected_count = False
                    request_phase_graph = (
                        route_runtime.get('request_phase_graph')
                        if isinstance(route_runtime.get('request_phase_graph'), Mapping)
                        else {}
                    )
                    if isinstance(request_phase_graph.get('prompt_intent'), Mapping):
                        prompt_intent = request_phase_graph.get('prompt_intent') or {}
                        expected_count, invalid_expected_count = (
                            _parse_image_batch_expected_count(
                                prompt_intent.get('requested_visual_output_count'),
                                present='requested_visual_output_count' in prompt_intent,
                            )
                        )
                    plain_alpha_authority = self.phase_preparation.plain_alpha_image_prompt_prepare_authority(
                        request_phase_graph,
                        expected_count=expected_count,
                    )
                    numbered_image_authority = self.phase_preparation.numbered_image_prepare_authority(
                        request_phase_graph
                    )
                    batch_prompt_authority = (
                        numbered_image_authority or plain_alpha_authority
                    )
                    batch_prompts = image_prompt_preparation.extract_batch_image_prompts(
                        output_text,
                        expected_count=expected_count,
                        allow_plain_alpha_sequence=bool(plain_alpha_authority),
                    )
                    if invalid_expected_count:
                        for key in (
                            'content_payload',
                            'phase_summary',
                            'artifact_prompt',
                            'artifact_prompt_source',
                            'batch_prompts',
                            'batch_prompts_source',
                            'batch_prompt_source_phase_id',
                            'batch_prompt_expected_count',
                        ):
                            payload.pop(key, None)
                        payload['branch_contract_error'] = (
                            'incomplete_image_prompt_batch'
                        )
                        payload['candidate_extraction_issue'] = (
                            'invalid_image_prompt_batch_count'
                        )
                        payload['batch_prompt_expected_count_invalid'] = True
                        payload['batch_prompt_actual_count'] = len(batch_prompts)
                        payload['materialization_blocked'] = True
                        payload['repair_action'] = RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT
                        payload['counted_batch_prompt_carriers_blocked'] = True
                        return payload
                    if len(batch_prompts) > 1:
                        payload['batch_prompts'] = batch_prompts
                        payload['batch_prompt_expected_count'] = (
                            expected_count if expected_count >= 2 else len(batch_prompts)
                        )
                        if batch_prompt_authority:
                            payload['batch_prompts_source'] = 'semantic_prepare_phase_output'
                            payload['batch_prompt_source_phase_id'] = batch_prompt_authority[
                                'source_phase_id'
                            ]
                        # Once a complete ordered batch is proven, its first item
                        # is the only valid root prompt. Free-text extraction may
                        # otherwise retain the final labelled prompt plus the
                        # following HTML/CSS section even though the batch parser
                        # correctly stopped at that boundary.
                        payload['artifact_prompt'] = batch_prompts[0]
                        payload['artifact_prompt_source'] = 'semantic_batch_prompts'
                    expanded_branches, expansion = self._expand_image_pending_branches_from_batch_prompts(
                        pending_branches,
                        payload.get('batch_prompts'),
                    )
                    if expansion:
                        payload['pending_branches'] = expanded_branches
                        payload['pending_capabilities'] = normalize_capability_list(
                            [item.get('capability') for item in expanded_branches]
                        )
                        payload['prepared_image_prompt_branch_expansion'] = expansion
            if self.artifact_gap_is_already_fulfilled(payload, artifact_payload):
                continue
            return payload
        return None

    def _extract_expected_non_chat_capability_from_route(
        self,
        route_payload: Optional[dict[str, Any]],
    ) -> Optional[str]:
        normalize_capability_list = self._hook('normalize_capability_list')

        route_info = route_payload if isinstance(route_payload, dict) else {}
        route_runtime = (
            route_info.get('route_runtime')
            if isinstance(route_info.get('route_runtime'), dict)
            else {}
        )
        embedding_audit = (
            route_runtime.get('embedding_audit')
            if isinstance(route_runtime.get('embedding_audit'), dict)
            else {}
        )
        execution_planner = (
            route_runtime.get('execution_planner')
            if isinstance(route_runtime.get('execution_planner'), dict)
            else {}
        )
        request_phase_graph = (
            route_runtime.get('request_phase_graph')
            if isinstance(route_runtime.get('request_phase_graph'), dict)
            else {}
        )
        if self._request_graph_defers_downstream_execution(request_phase_graph):
            return None
        request_meta = (
            route_runtime.get('request_meta')
            if isinstance(route_runtime.get('request_meta'), dict)
            else {}
        )
        for candidate in (
            execution_planner.get('deferred_capability'),
            *(normalize_capability_list(execution_planner.get('deferred_capabilities'))),
            *(normalize_capability_list(downstream_phase_capabilities(request_phase_graph))),
            request_meta.get('capability_hint'),
            embedding_audit.get('route_hint_capability') or embedding_audit.get('heuristic_capability'),
        ):
            normalized_candidate = normalize_capability(candidate)
            if normalized_candidate and normalized_candidate != CAPABILITY_CHAT:
                return normalized_candidate
        return None

    def _extract_expected_non_chat_capability(
        self,
        *,
        route_payload: Optional[dict[str, Any]] = None,
        request_payload: Optional[dict[str, Any]] = None,
    ) -> Optional[str]:
        extract_request_meta = self._hook('extract_request_meta')

        route_capability = self._extract_expected_non_chat_capability_from_route(route_payload)
        if route_capability:
            return route_capability
        request_meta = extract_request_meta(request_payload or {})
        request_meta_hint = normalize_capability((request_meta or {}).get('capability_hint'))
        if request_meta_hint and request_meta_hint != CAPABILITY_CHAT:
            return request_meta_hint
        return None

    def build_artifact_completion_gap_spec(
        self,
        output_text: str,
        *,
        route_payload: Optional[dict[str, Any]] = None,
        request_payload: Optional[dict[str, Any]] = None,
        artifact_payload: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        text = str(output_text or '').strip()
        if not text:
            return None
        expected_capability = self._extract_expected_non_chat_capability(
            route_payload=route_payload,
            request_payload=request_payload,
        )
        if expected_capability == CAPABILITY_IMAGE_GENERATION and _TEXT_ONLY_IMAGE_COMPLETION_RE.search(text):
            candidate_gap = {
                'code': 'late_artifact_fill',
                'expected_capability': CAPABILITY_IMAGE_GENERATION,
                'missing_artifact_type': 'image',
            }
            if not self.artifact_gap_is_already_fulfilled(candidate_gap, artifact_payload):
                return candidate_gap
        if expected_capability == CAPABILITY_TEXT_TO_SPEECH and _TEXT_ONLY_AUDIO_COMPLETION_RE.search(text):
            candidate_gap = {
                'code': 'late_artifact_fill',
                'expected_capability': CAPABILITY_TEXT_TO_SPEECH,
                'missing_artifact_type': 'audio',
            }
            if not self.artifact_gap_is_already_fulfilled(candidate_gap, artifact_payload):
                return candidate_gap
        planner_deferred_gap = self.build_planner_deferred_follow_up_gap_spec(
            text,
            route_payload=route_payload,
            artifact_payload=artifact_payload,
        )
        if planner_deferred_gap:
            if self.artifact_gap_is_already_fulfilled(planner_deferred_gap, artifact_payload):
                return None
            return planner_deferred_gap
        return None

    _explicit_recovery_action_from_payload = staticmethod(closure_repair_feedback._explicit_recovery_action_from_payload)

    _closure_check_recovery_action = staticmethod(closure_repair_feedback._closure_check_recovery_action)

    @staticmethod
    def _workload_task_indexes(request_phase_graph: Mapping[str, Any]) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
        request_ir = (
            request_phase_graph.get('request_ir')
            if isinstance(request_phase_graph.get('request_ir'), Mapping)
            else {}
        )
        workload_graph = (
            request_phase_graph.get('workload_graph')
            if isinstance(request_phase_graph.get('workload_graph'), Mapping)
            else (
                request_ir.get('workload_graph')
                if isinstance(request_ir.get('workload_graph'), Mapping)
                else {}
            )
        )
        tasks = workload_graph.get('tasks') if isinstance(workload_graph.get('tasks'), list) else []
        by_phase: dict[str, Mapping[str, Any]] = {}
        by_branch: dict[str, Mapping[str, Any]] = {}
        for task in tasks:
            if not isinstance(task, Mapping):
                continue
            phase_id = str(task.get('phase_id') or '').strip()
            branch_id = str(task.get('branch_id') or phase_id or '').strip()
            if phase_id:
                by_phase[phase_id] = task
            if branch_id:
                by_branch[branch_id] = task
        return by_phase, by_branch

    @staticmethod
    def _check_has_dependency_runtime_evidence(check: Mapping[str, Any]) -> bool:
        source = str(check.get('content_payload_source') or '').strip()
        if (
            source.startswith('late_fill_result')
            or source.startswith('late_fill_results')
            or source in {'late_fill_dependency_artifacts', 'prior_artifact_result'}
        ):
            return True
        evidence = str(check.get('evidence') or '').strip()
        if evidence.startswith('late_fill_completed'):
            return True
        if str(check.get('file_path') or '').strip():
            return True
        for key in ('input_artifacts', 'reference_artifacts'):
            if isinstance(check.get(key), list) and check.get(key):
                return True
        return False

    _sequential_structured_join_labels = staticmethod(StructuredDependencyReview._sequential_structured_join_labels)

    _structured_dependency_join_prompt_contract = staticmethod(StructuredDependencyReview._structured_dependency_join_prompt_contract)

    _structured_join_graph_records = staticmethod(StructuredDependencyReview._structured_join_graph_records)

    _structured_join_fill_result_for_record = staticmethod(StructuredDependencyReview._structured_join_fill_result_for_record)

    _structured_join_terminal_result_text = staticmethod(StructuredDependencyReview._structured_join_terminal_result_text)

    _structured_join_alias_tokens = staticmethod(StructuredDependencyReview._structured_join_alias_tokens)

    _structured_join_artifact_aliases = staticmethod(StructuredDependencyReview._structured_join_artifact_aliases)

    _structured_join_artifact_path_aliases = staticmethod(StructuredDependencyReview._structured_join_artifact_path_aliases)

    _structured_join_artifact_matches_type = staticmethod(StructuredDependencyReview._structured_join_artifact_matches_type)

    _structured_object_reference_records = staticmethod(StructuredDependencyReview._structured_object_reference_records)

    _structured_object_source_artifact_refs = staticmethod(StructuredDependencyReview._structured_object_source_artifact_refs)

    def _structured_output_object_contract_checks(
        self,
        *,
        request_payload: Optional[Mapping[str, Any]],
        artifact_payload: Optional[Mapping[str, Any]],
        request_phase_graph: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        return self.structured_dependency_review._structured_output_object_contract_checks(request_payload=request_payload, artifact_payload=artifact_payload, request_phase_graph=request_phase_graph)

    def _structured_dependency_join_checks(
        self,
        *,
        request_payload: Optional[Mapping[str, Any]],
        artifact_payload: Optional[Mapping[str, Any]],
        request_phase_graph: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        return self.structured_dependency_review._structured_dependency_join_checks(request_payload=request_payload, artifact_payload=artifact_payload, request_phase_graph=request_phase_graph)

    def _artifact_records_for_link_binding(
        self,
        payload: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        if not isinstance(payload, Mapping):
            return []
        records: list[dict[str, Any]] = []
        record_index_by_identity: dict[tuple[str, ...], int] = {}

        def add_record(raw_record: Any, *, defaults: Optional[Mapping[str, Any]] = None) -> None:
            if not isinstance(raw_record, Mapping):
                return
            record = dict(defaults or {})
            record.update(dict(raw_record))
            artifact_type = str(record.get('type') or record.get('kind') or '').strip().lower()
            path = _artifact_path(record)
            content = str(record.get('content') or record.get('text') or record.get('result_text') or '').strip()
            if not artifact_type and not path and not content:
                return
            normalized_path = self._normalized_text_artifact_path_for_closure(path)
            artifact_ref = str(record.get('artifact_ref') or record.get('ref') or '').strip()
            if normalized_path:
                # The saved path is the physical artifact identity.  Type,
                # branch, and phase describe that artifact but must not turn
                # one shared target into competing Closure owners.
                identity = ('path', normalized_path)
            elif artifact_ref:
                identity = ('artifact_ref', artifact_type, artifact_ref)
            else:
                identity = (
                    'unbound',
                    artifact_type,
                    str(record.get('branch_id') or '').strip(),
                    str(record.get('phase_id') or '').strip(),
                    hashlib.sha256(content.encode('utf-8')).hexdigest() if content else '',
                )
            existing_index = record_index_by_identity.get(identity)
            if existing_index is not None:
                existing = records[existing_index]
                for key, value in record.items():
                    if value in (None, '', [], {}):
                        continue
                    if existing.get(key) in (None, '', [], {}):
                        existing[key] = value
                return
            record_index_by_identity[identity] = len(records)
            records.append(
                {
                    key: value
                    for key, value in record.items()
                    if value not in (None, '', [], {})
                }
            )

        for artifact in payload.get('artifacts') or []:
            add_record(artifact)
        for artifact in self._hook('build_canonical_response_artifacts')(dict(payload)):
            add_record(artifact)
        for item in payload.get('saved_text_artifacts') or []:
            source = item if isinstance(item, Mapping) else {'path': item}
            add_record({'type': 'text', **dict(source)})
        if str(payload.get('saved_text_path') or payload.get('savedTextPath') or '').strip():
            add_record({'type': 'text', 'path': payload.get('saved_text_path') or payload.get('savedTextPath')})
        if str(payload.get('saved_image_path') or payload.get('savedImagePath') or '').strip():
            add_record({'type': 'image', 'path': payload.get('saved_image_path') or payload.get('savedImagePath')})

        late_fill = payload.get('late_fill') if isinstance(payload.get('late_fill'), Mapping) else {}
        for result in late_fill.get('fill_results') or []:
            if not isinstance(result, Mapping):
                continue
            defaults = {
                'branch_id': result.get('branch_id'),
                'phase_id': result.get('phase_id'),
                'source': 'late_fill_result',
            }
            if str(result.get('saved_text_path') or '').strip():
                add_record(
                    {
                        'type': 'text',
                        'path': result.get('saved_text_path'),
                        'content': result.get('result_text') or result.get('content_payload'),
                        'text_artifact_extension': result.get('text_artifact_extension'),
                        'text_artifact_source_name': result.get('text_artifact_source_name'),
                        'text_artifact_target_path': result.get('text_artifact_target_path'),
                        'text_artifact_request': result.get('artifact_request'),
                    },
                    defaults=defaults,
                )
            if str(result.get('saved_image_path') or '').strip():
                add_record({'type': 'image', 'path': result.get('saved_image_path')}, defaults=defaults)
            for artifact in result.get('artifacts') or []:
                add_record(artifact, defaults=defaults)
        return records

    @staticmethod
    def _text_artifact_record_content(record: Mapping[str, Any]) -> str:
        # Saved files are canonical artifact bytes.  In-memory content may be
        # a bounded preview or a target-bound repair prompt carried by the
        # same branch, so prefer the current file whenever it is available.
        path = _artifact_path(record)
        if path:
            try:
                target = Path(path).expanduser()
                if target.is_file() and target.stat().st_size <= 512_000:
                    return target.read_text(
                        encoding='utf-8',
                        errors='replace',
                    ).strip()
            except OSError:
                pass
        for key in ('content', 'text', 'result_text', 'content_payload'):
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ''

    _bounded_repair_content_block = staticmethod(text_artifact_syntax._bounded_repair_content_block)

    @staticmethod
    def _class_token_is_meaningful(value: str) -> bool:
        token = str(value or '').strip().lower()
        if not token or token in _HTML_CSS_IGNORABLE_CLASS_TOKENS:
            return False
        if len(token) < 3 or token.isdigit():
            return False
        if token.startswith(('js-', 'is-', 'has-')):
            return False
        return True

    @classmethod
    def _html_class_tokens(cls, content: str) -> set[str]:
        tokens: set[str] = set()
        for match in _HTML_CLASS_ATTR_RE.finditer(str(content or '')):
            for token in re.split(r'\s+', str(match.group('value') or '').strip()):
                normalized = token.strip().lower()
                if cls._class_token_is_meaningful(normalized):
                    tokens.add(normalized)
        return tokens

    @classmethod
    def _css_class_selector_tokens(cls, content: str) -> set[str]:
        text = re.sub(r'/\*[\s\S]*?\*/', '', str(content or ''))
        tokens: set[str] = set()
        for match in _CSS_BLOCK_SELECTOR_RE.finditer(text):
            selectors = str(match.group('selectors') or '').strip()
            if not selectors or selectors.startswith('@'):
                continue
            selectors = re.sub(r'(?P<quote>["\']).*?(?P=quote)', '', selectors)
            for selector_match in _CSS_CLASS_SELECTOR_RE.finditer(selectors):
                normalized = str(selector_match.group('class') or '').strip().lower()
                if cls._class_token_is_meaningful(normalized):
                    tokens.add(normalized)
        return tokens

    @staticmethod
    def _html_links_css_artifact(html_content: str, css_record: Mapping[str, Any]) -> bool:
        content = str(html_content or '')
        if not content:
            return False
        return any(token and token in content for token in _artifact_link_tokens(css_record))

    _line_number_for_offset = staticmethod(text_artifact_syntax._line_number_for_offset)

    _html_open_tag_stack_before_offset = staticmethod(text_artifact_syntax._html_open_tag_stack_before_offset)

    _html_attrs_have_hero_marker = staticmethod(text_artifact_syntax._html_attrs_have_hero_marker)

    _html_hero_header_landmark_containment_defects = staticmethod(text_artifact_syntax._html_hero_header_landmark_containment_defects)

    _html_unsupported_nav_anchor_wrapper_issue = staticmethod(text_artifact_syntax._html_unsupported_nav_anchor_wrapper_issue)

    _html_attribute_values = staticmethod(text_artifact_syntax._html_attribute_values)

    _html_href_targets_stylesheet = staticmethod(text_artifact_syntax._html_href_targets_stylesheet)

    _html_link_stylesheet_rel_is_invalid = staticmethod(text_artifact_syntax._html_link_stylesheet_rel_is_invalid)

    _html_attrs_have_unbalanced_quote = staticmethod(text_artifact_syntax._html_attrs_have_unbalanced_quote)

    _offset_is_inside_spans = staticmethod(text_artifact_syntax._offset_is_inside_spans)

    _html_stray_open_angle_offsets = staticmethod(text_artifact_syntax._html_stray_open_angle_offsets)

    _html_syntax_sanity_issues = staticmethod(text_artifact_syntax._html_syntax_sanity_issues)

    _css_custom_property_names = staticmethod(text_artifact_syntax._css_custom_property_names)

    _css_custom_property_var_reference_suggestion = staticmethod(text_artifact_syntax._css_custom_property_var_reference_suggestion)

    _bounded_edit_distance = staticmethod(text_artifact_syntax._bounded_edit_distance)

    _css_custom_property_var_reference_near_miss_suggestion = staticmethod(text_artifact_syntax._css_custom_property_var_reference_near_miss_suggestion)

    _css_custom_property_var_reference_typos = staticmethod(text_artifact_syntax._css_custom_property_var_reference_typos)

    _css_custom_property_var_reference_near_misses = staticmethod(text_artifact_syntax._css_custom_property_var_reference_near_misses)

    _css_property_identifier_is_valid = staticmethod(text_artifact_syntax._css_property_identifier_is_valid)

    _css_invalid_property_value_suggestion = staticmethod(text_artifact_syntax._css_invalid_property_value_suggestion)

    _css_malformed_declaration_name_suggestion = staticmethod(text_artifact_syntax._css_malformed_declaration_name_suggestion)

    _css_declaration_name_formatting_tag_suggestion = staticmethod(text_artifact_syntax._css_declaration_name_formatting_tag_suggestion)

    _css_offset_inside_string_or_parentheses = staticmethod(text_artifact_syntax._css_offset_inside_string_or_parentheses)

    _css_syntax_sanity_issues = staticmethod(text_artifact_syntax._css_syntax_sanity_issues)

    _json_syntax_sanity_issues = staticmethod(text_artifact_syntax._json_syntax_sanity_issues)

    text_artifact_syntax_sanity_issues_for_extension = staticmethod(text_artifact_syntax.text_artifact_syntax_sanity_issues_for_extension)

    _repair_html_syntax_sanity_content = staticmethod(text_artifact_syntax._repair_html_syntax_sanity_content)

    _repair_css_syntax_sanity_content = staticmethod(text_artifact_syntax._repair_css_syntax_sanity_content)

    _repair_json_syntax_sanity_content = staticmethod(text_artifact_syntax._repair_json_syntax_sanity_content)

    repair_text_artifact_syntax_content = staticmethod(text_artifact_syntax.repair_text_artifact_syntax_content)

    @classmethod
    def _text_artifact_syntax_sanity_issues(
        cls,
        record: Mapping[str, Any],
        content: str,
    ) -> list[str]:
        return text_artifact_syntax.text_artifact_syntax_sanity_issues_for_extension(
            _text_artifact_extension_from_record(record),
            content,
        )

    @staticmethod
    def _artifact_record_is_image(record: Mapping[str, Any]) -> bool:
        artifact_type = str(record.get('type') or record.get('kind') or '').strip().lower()
        extension = _extension_from_path_like(_artifact_path(record))
        return artifact_type in {'image', 'png', 'jpg', 'jpeg', 'webp'} or extension in {'png', 'jpg', 'jpeg', 'webp'}

    @staticmethod
    def _html_hero_snippets(content: str) -> list[str]:
        text = str(content or '')
        snippets: list[str] = []
        for match in _HTML_HERO_BLOCK_RE.finditer(text):
            tag = str(match.group('tag') or '').strip().lower()
            attrs = str(match.group('attrs') or '')
            if tag != 'header' and not _HERO_LOCAL_IMAGE_SIGNAL_RE.search(attrs):
                continue
            snippet = match.group(0)
            if snippet and snippet not in snippets:
                snippets.append(snippet)
        return snippets

    @staticmethod
    def _css_hero_snippets(content: str) -> list[str]:
        text = str(content or '')
        snippets: list[str] = []
        for match in _CSS_HERO_BLOCK_RE.finditer(text):
            snippet = match.group(0)
            if snippet and snippet not in snippets:
                snippets.append(snippet)
        return snippets

    @classmethod
    def _hero_local_image_required(
        cls,
        prompt_text: str,
        *,
        html_contents: list[str],
        css_contents: list[str],
    ) -> bool:
        # A page background color does not require image placement. Keep the
        # broader selector signal for existing artifact regions, but require
        # image-specific placement language when inspecting the request.
        if _HERO_IMAGE_PLACEMENT_SIGNAL_RE.search(str(prompt_text or '')):
            return True
        return any(cls._html_hero_snippets(content) for content in html_contents) or any(
            cls._css_hero_snippets(content) for content in css_contents
        )

    @classmethod
    def _hero_snippets_have_artifact_link(
        cls,
        *,
        html_contents: list[str],
        css_contents: list[str],
        image_records: list[Mapping[str, Any]],
    ) -> bool:
        snippets: list[str] = []
        for content in html_contents:
            snippets.extend(cls._html_hero_snippets(content))
        for content in css_contents:
            snippets.extend(cls._css_hero_snippets(content))
        if not snippets:
            return False
        hero_content = '\n'.join(snippets)
        return any(
            token and token in hero_content
            for image_record in image_records
            for token in _artifact_link_tokens(image_record)
        )

    @classmethod
    def _preferred_hero_image_rebind_target(
        cls,
        *,
        html_records: list[Mapping[str, Any]],
        css_records: list[Mapping[str, Any]],
        content_by_id: Mapping[int, str],
    ) -> Optional[Mapping[str, Any]]:
        for record in css_records:
            if cls._css_hero_snippets(content_by_id.get(id(record), '')):
                return record
        for record in html_records:
            if cls._html_hero_snippets(content_by_id.get(id(record), '')):
                return record
        return css_records[0] if css_records else (html_records[0] if html_records else None)

    def _linked_artifact_binding_checks(
        self,
        *,
        request_payload: Optional[Mapping[str, Any]],
        artifact_payload: Optional[Mapping[str, Any]],
        request_phase_graph: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        payload = artifact_payload if isinstance(artifact_payload, Mapping) else {}
        if not payload:
            return []
        prompt_text = str(
            (request_payload or {}).get('prompt')
            or (request_payload or {}).get('input')
            or ((request_phase_graph.get('prompt_intent') or {}).get('normalized_prompt') if isinstance(request_phase_graph.get('prompt_intent'), Mapping) else '')
            or ''
        ).strip()
        records = self._artifact_records_for_link_binding(payload)
        text_records = [
            record
            for record in records
            if str(record.get('type') or record.get('kind') or '').strip().lower() == 'text'
            and _text_artifact_extension_from_record(record) in _TEXT_LINK_ARTIFACT_EXTENSIONS
        ]
        if not text_records:
            return []
        html_records = [
            record for record in text_records
            if _text_artifact_extension_from_record(record) in {'html', 'htm'}
        ]
        link_asset_records = [
            record for record in text_records
            if _text_artifact_extension_from_record(record) in _HTML_LINK_TARGET_EXTENSIONS
        ]
        if link_asset_records:
            best_by_path: dict[str, Mapping[str, Any]] = {}

            def asset_record_score(record: Mapping[str, Any]) -> int:
                score = 0
                if str(record.get('text_artifact_source_name') or '').strip():
                    score += 8
                if isinstance(record.get('artifact_request'), Mapping):
                    score += 4
                if str(record.get('source') or '').strip() == 'late_fill_result':
                    score += 3
                source_name = _artifact_source_name(record).lower()
                path_stem = Path(_artifact_path(record)).stem.lower()
                if source_name and source_name in path_stem:
                    score += 2
                return score

            for record in link_asset_records:
                path = _artifact_path(record)
                if not path:
                    continue
                existing = best_by_path.get(path)
                if existing is None or asset_record_score(record) > asset_record_score(existing):
                    best_by_path[path] = record
            link_asset_records = list(best_by_path.values()) or link_asset_records
        image_records = [record for record in records if self._artifact_record_is_image(record)]
        if not html_records and not link_asset_records:
            return []

        content_by_id: dict[int, str] = {
            id(record): self._text_artifact_record_content(record)
            for record in text_records
        }

        def has_any_token(content: str, artifact: Mapping[str, Any]) -> bool:
            return any(token and token in content for token in _artifact_link_tokens(artifact))

        issues_by_target: dict[int, dict[str, Any]] = {}

        def add_issue(target: Mapping[str, Any], issue: str) -> None:
            if not issue:
                return
            key = id(target)
            payload = issues_by_target.setdefault(key, {'target': target, 'issues': []})
            if issue not in payload['issues']:
                payload['issues'].append(issue)

        for record in text_records:
            content = content_by_id.get(id(record), '')
            if _content_has_unresolved_link_placeholder(content):
                add_issue(record, 'text artifact still contains placeholder or unresolved link tokens')

        grouped_assets: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
        for asset_record in link_asset_records:
            extension = _text_artifact_extension_from_record(asset_record)
            source_name = _artifact_source_name(asset_record).lower()
            if not source_name:
                source_name = Path(_artifact_path(asset_record)).stem.lower()
            grouped_assets.setdefault(
                (extension, source_name or extension),
                [],
            ).append(asset_record)

        script_extensions = {'js', 'mjs', 'cjs'}
        for html_index, html_record in enumerate(html_records):
            html_content = content_by_id.get(id(html_record), '')
            if not html_content:
                continue
            for (extension, _source_name), asset_group in grouped_assets.items():
                if not asset_group:
                    continue
                if extension in script_extensions:
                    linked_by_any_page = any(
                        any(
                            has_any_token(
                                content_by_id.get(id(candidate_html), ''),
                                asset_record,
                            )
                            for asset_record in asset_group
                        )
                        for candidate_html in html_records
                    )
                    if linked_by_any_page:
                        continue
                    # A page-specific script is a response-level dependency,
                    # not a mandate that every page execute it. When no page
                    # links the script, emit one repair target only.
                    if html_index != 0:
                        continue
                if not any(has_any_token(html_content, asset_record) for asset_record in asset_group):
                    asset_record = asset_group[0]
                    add_issue(
                        html_record,
                        f'HTML does not link concrete artifact `{_fruth_relative_path(_artifact_path(asset_record)) or _artifact_source_name(asset_record)}`',
                    )

        if image_records and _LINKED_IMAGE_INTENT_RE.search(prompt_text):
            linked_text_records = text_records or html_records
            all_link_content = '\n\n'.join(
                content_by_id.get(id(record), '')
                for record in linked_text_records
                if content_by_id.get(id(record), '')
            )
            css_records = [
                record for record in text_records
                if _text_artifact_extension_from_record(record) == 'css'
            ]
            html_contents = [content_by_id.get(id(record), '') for record in html_records]
            css_contents = [content_by_id.get(id(record), '') for record in css_records]
            missing_image_records = [
                image_record
                for image_record in image_records
                if not all_link_content or not has_any_token(all_link_content, image_record)
            ]
            hero_rebind_required = (
                self._hero_local_image_required(
                    prompt_text,
                    html_contents=html_contents,
                    css_contents=css_contents,
                )
                and not self._hero_snippets_have_artifact_link(
                    html_contents=html_contents,
                    css_contents=css_contents,
                    image_records=image_records,
                )
            )
            hero_target = None
            hero_designated_image = None
            if hero_rebind_required:
                hero_target = self._preferred_hero_image_rebind_target(
                    html_records=html_records,
                    css_records=css_records,
                    content_by_id=content_by_id,
                )
                if (
                    hero_target is not None
                    and _text_artifact_extension_from_record(hero_target) == 'css'
                    and missing_image_records
                ):
                    # A CSS-owned hero repair will make one currently missing
                    # generated image concrete. Reserve that exact image for
                    # the hero target so Closure does not also schedule an
                    # overlapping HTML repair for the same obligation.
                    hero_designated_image = missing_image_records[0]
                if hero_target is not None:
                    hero_issue = (
                        'Hero section does not use a concrete generated image artifact path; '
                        'bind one saved generated image into the hero/header image or background'
                    )
                    if hero_designated_image is not None:
                        hero_issue += (
                            f' using `{_fruth_relative_path(_artifact_path(hero_designated_image))}`'
                        )
                    add_issue(
                        hero_target,
                        hero_issue,
                    )

            for image_record in missing_image_records:
                if image_record is hero_designated_image:
                    continue
                # General image representation belongs to the composed page.
                # CSS is authoritative only for the one concrete image owned
                # by the dedicated hero-background repair above.
                preferred_target = (
                    html_records[0]
                    if html_records
                    else linked_text_records[0]
                )
                add_issue(
                    preferred_target,
                    f'Generated image artifact is not linked by its real saved path `{_fruth_relative_path(_artifact_path(image_record))}`',
                )

        if not issues_by_target:
            return []

        artifact_lines = [
            f"- {str(record.get('type') or record.get('kind') or 'artifact').strip() or 'artifact'}: {_fruth_relative_path(_artifact_path(record))}"
            for record in records
            if _artifact_path(record)
        ]
        checks: list[dict[str, Any]] = []
        for payload_item in issues_by_target.values():
            target = payload_item['target']
            target_extension = _text_artifact_extension_from_record(target) or 'txt'
            target_name = _artifact_source_name(target) or f'generated-{target_extension}'
            target_path = _artifact_path(target)
            issues = payload_item['issues']
            target_display_path = _fruth_relative_path(target_path) if target_path else ''
            target_content_lines = text_artifact_syntax._bounded_repair_content_block(
                'Current saved target file content',
                content_by_id.get(id(target), ''),
            )
            content_payload = '\n'.join(
                [
                    f'Target text artifact: {target_display_path or target_name}',
                    'Unresolved linked artifact binding:',
                    *[f'- {issue}' for issue in issues],
                    'Resolved runtime artifacts:',
                    *artifact_lines,
                    *target_content_lines,
                    'Update only the target text artifact. Replace placeholders or guessed asset references with the concrete saved artifact paths or basenames above.',
                ]
            ).strip()
            check = {
                'check_kind': 'linked_artifact_binding',
                'status': 'pending',
                'evidence': 'unresolved_linked_artifact_binding',
                'reason': 'linked artifacts must be rebound to concrete runtime artifact paths before closure',
                'capability': CAPABILITY_CHAT,
                'output_type': 'text',
                'role': 'linked_artifact_binding_review',
                'branch_id': str(target.get('branch_id') or '').strip() or None,
                'phase_id': str(target.get('phase_id') or target.get('branch_id') or '').strip() or None,
                'repair_action': RECOVERY_ACTION_REBIND_DEPENDENCY_EVIDENCE,
                'recovery_action': RECOVERY_ACTION_REBIND_DEPENDENCY_EVIDENCE,
                'repair_action_reason': 'runtime artifacts exist but linked text artifacts still contain placeholders or unbound asset references',
                'content_payload': content_payload,
                'content_payload_source': 'closure_linked_artifact_binding_review',
                'stage_direction': 'materialize_requested_text_artifact',
                'requires_artifact': True,
                'text_artifact_extension': target_extension,
                'text_artifact_source_name': target_name,
                'text_artifact_source': 'closure_link_rebind',
                'text_artifact_target_path': target_path,
                'artifact_request': {
                    'extension': target_extension,
                    'source_name': target_name,
                    'source': 'closure_link_rebind',
                    'target_path': target_path,
                },
                'review_criteria': [
                    'linked_artifact_paths_resolve_to_runtime_artifacts',
                    'no_unresolved_asset_placeholders',
                ],
            }
            checks.append({key: value for key, value in check.items() if value not in (None, '', [], {})})
        return checks

    def _html_css_selector_binding_checks(
        self,
        *,
        artifact_payload: Optional[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        payload = artifact_payload if isinstance(artifact_payload, Mapping) else {}
        if not payload:
            return []
        records = self._artifact_records_for_link_binding(payload)
        text_records = [
            record
            for record in records
            if str(record.get('type') or record.get('kind') or '').strip().lower() == 'text'
        ]
        html_records = [
            record
            for record in text_records
            if _text_artifact_extension_from_record(record) in {'html', 'htm'}
        ]
        css_records = [
            record
            for record in text_records
            if _text_artifact_extension_from_record(record) == 'css'
        ]
        if not html_records or not css_records:
            return []

        content_by_id: dict[int, str] = {
            id(record): self._text_artifact_record_content(record)
            for record in [*html_records, *css_records]
        }
        html_records_by_css_id: dict[int, list[dict[str, Any]]] = {
            id(css_record): [] for css_record in css_records
        }
        for html_record in html_records:
            html_content = content_by_id.get(id(html_record), '')
            linked_css_records = [
                css_record
                for css_record in css_records
                if self._html_links_css_artifact(html_content, css_record)
            ]
            if not linked_css_records and len(css_records) == 1:
                linked_css_records = css_records
            for css_record in linked_css_records:
                html_records_by_css_id[id(css_record)].append(html_record)

        checks: list[dict[str, Any]] = []
        for css_record in css_records:
            linked_html_records = html_records_by_css_id.get(id(css_record), [])
            if not linked_html_records:
                continue
            html_tokens: set[str] = set()
            html_display_paths: list[str] = []
            for html_record in linked_html_records:
                html_content = content_by_id.get(id(html_record), '')
                html_tokens.update(self._html_class_tokens(html_content))
                html_path = _artifact_path(html_record)
                html_display_path = (
                    _fruth_relative_path(html_path)
                    if html_path
                    else _artifact_source_name(html_record)
                )
                html_display_paths.append(
                    html_display_path
                    or f'linked-html-{len(html_display_paths) + 1}.html'
                )
            if len(html_tokens) < _HTML_CSS_SELECTOR_BINDING_MIN_TOKENS:
                continue

            css_content = content_by_id.get(id(css_record), '')
            css_tokens = self._css_class_selector_tokens(css_content)
            if len(css_tokens) < _HTML_CSS_SELECTOR_BINDING_MIN_TOKENS:
                continue
            html_without_css = sorted(html_tokens - css_tokens)
            css_without_html = sorted(css_tokens - html_tokens)
            if (
                len(html_without_css) < _HTML_CSS_SELECTOR_BINDING_MIN_MISSING
                or len(css_without_html) < _HTML_CSS_SELECTOR_BINDING_MIN_MISSING
                or len(html_without_css) / max(1, len(html_tokens))
                < _HTML_CSS_SELECTOR_BINDING_MIN_RATIO
                or len(css_without_html) / max(1, len(css_tokens))
                < _HTML_CSS_SELECTOR_BINDING_MIN_RATIO
            ):
                continue

            css_path = _artifact_path(css_record)
            css_name = _artifact_source_name(css_record) or 'styles'
            css_display_path = _fruth_relative_path(css_path) if css_path else ''
            per_html_content_limit = max(
                1000,
                _HTML_CSS_SELECTOR_BINDING_CONTENT_LIMIT
                // max(1, len(linked_html_records)),
            )
            html_content_lines: list[str] = []
            for html_record, html_display_path in zip(
                linked_html_records,
                html_display_paths,
            ):
                html_content_lines.extend(
                    text_artifact_syntax._bounded_repair_content_block(
                        f'Current saved HTML file content ({html_display_path})',
                        content_by_id.get(id(html_record), ''),
                        limit=per_html_content_limit,
                    )
                )
            content_payload = '\n'.join(
                [
                    f'Target text artifact: {css_display_path or css_name}',
                    'Linked HTML artifacts:',
                    *[f'- {path}' for path in html_display_paths],
                    'HTML/CSS selector binding drift across the shared stylesheet:',
                    '- HTML classes not targeted by linked CSS: '
                    + ', '.join(html_without_css[:16]),
                    '- CSS class selectors not present in linked HTML: '
                    + ', '.join(css_without_html[:16]),
                    *html_content_lines,
                    *text_artifact_syntax._bounded_repair_content_block(
                        'Current saved CSS target file content', css_content
                    ),
                    'Update only the target CSS artifact. Cover the combined class vocabulary of every linked HTML artifact while preserving declarations, copy, valid runtime artifact links, and visual intent. Rename or add selectors only as needed so the shared CSS targets the actual saved HTML classes.',
                ]
            ).strip()
            check = {
                'check_kind': 'html_css_selector_binding',
                'status': 'pending',
                'evidence': 'html_css_selector_drift',
                'reason': 'saved HTML and linked CSS use divergent class vocabularies before closure',
                'capability': CAPABILITY_CHAT,
                'output_type': 'text',
                'role': 'html_css_selector_binding_repair',
                'branch_id': str(css_record.get('branch_id') or '').strip() or None,
                'phase_id': str(css_record.get('phase_id') or css_record.get('branch_id') or '').strip() or None,
                'repair_action': RECOVERY_ACTION_RETRY_SAME_BRANCH,
                'recovery_action': RECOVERY_ACTION_RETRY_SAME_BRANCH,
                'repair_action_reason': 'linked CSS must be patched to target the saved HTML class vocabulary',
                'content_payload': content_payload,
                'content_payload_source': 'closure_html_css_selector_binding_review',
                'stage_direction': 'materialize_requested_text_artifact',
                'requires_artifact': True,
                'text_artifact_extension': 'css',
                'text_artifact_source_name': css_name,
                'text_artifact_source': 'closure_selector_binding_repair',
                'text_artifact_target_path': css_path,
                'artifact_request': {
                    'extension': 'css',
                    'source_name': css_name,
                    'source': 'closure_selector_binding_repair',
                    'target_path': css_path,
                },
                'review_criteria': [
                    'html_css_selector_binding',
                    'preserve_runtime_artifact_links',
                ],
                'html_class_tokens_missing_css_selectors': html_without_css[:24],
                'css_class_selectors_missing_html_usage': css_without_html[:24],
                'html_class_count': len(html_tokens),
                'css_selector_class_count': len(css_tokens),
                'linked_html_artifact_count': len(linked_html_records),
                'linked_html_artifact_paths': html_display_paths,
            }
            checks.append(
                {
                    key: value
                    for key, value in check.items()
                    if value not in (None, '', [], {})
                }
            )
        return checks

    def _text_artifact_syntax_sanity_checks(
        self,
        *,
        artifact_payload: Optional[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        payload = artifact_payload if isinstance(artifact_payload, Mapping) else {}
        if not payload:
            return []
        records = self._artifact_records_for_link_binding(payload)
        checks: list[dict[str, Any]] = []
        for record in records:
            if str(record.get('type') or record.get('kind') or '').strip().lower() != 'text':
                continue
            extension = _text_artifact_extension_from_record(record)
            if extension not in {'html', 'htm', 'css', 'json'}:
                continue
            content = self._text_artifact_record_content(record)
            issues = self._text_artifact_syntax_sanity_issues(record, content)
            if not issues:
                continue
            target_path = _artifact_path(record)
            target_display_path = _fruth_relative_path(target_path) if target_path else ''
            target_name = _artifact_source_name(record) or f'generated-{extension}'
            target_content_lines = text_artifact_syntax._bounded_repair_content_block(
                'Current saved target file content',
                content,
            )
            content_payload = '\n'.join(
                [
                    f'Target text artifact: {target_display_path or target_name}',
                    'Deterministic syntax sanity issues:',
                    *[f'- {issue}' for issue in issues],
                    *target_content_lines,
                    'Update only the target text artifact. Preserve valid runtime artifact links, copy, and layout intent. Fix the syntax defects above before closure.',
                ]
            ).strip()
            check = {
                'check_kind': 'text_artifact_syntax_sanity',
                'status': 'pending',
                'evidence': 'text_artifact_syntax_issue',
                'reason': 'saved HTML/CSS artifact has deterministic syntax defects before closure',
                'capability': CAPABILITY_CHAT,
                'output_type': 'text',
                'role': 'text_artifact_syntax_repair',
                'repair_scope': 'syntax_only',
                'resource_class': 'text_io',
                'dependency_policy': 'target_artifact_snapshot_only',
                'runtime_scheduling_context': {
                    'repair_scope': 'syntax_only',
                    'resource_class': 'text_io',
                    'dependency_policy': 'target_artifact_snapshot_only',
                },
                'branch_id': str(record.get('branch_id') or '').strip() or None,
                'phase_id': str(record.get('phase_id') or record.get('branch_id') or '').strip() or None,
                'repair_action': RECOVERY_ACTION_RETRY_SAME_BRANCH,
                'recovery_action': RECOVERY_ACTION_RETRY_SAME_BRANCH,
                'repair_action_reason': 'text artifact has deterministic syntax defects; repair the same bounded artifact branch',
                'content_payload': content_payload,
                'content_payload_source': 'closure_text_artifact_syntax_sanity',
                'stage_direction': 'materialize_requested_text_artifact',
                'requires_artifact': True,
                'text_artifact_extension': extension,
                'text_artifact_source_name': target_name,
                'text_artifact_source': 'closure_syntax_repair',
                'text_artifact_target_path': target_path,
                'artifact_request': {
                    'extension': extension,
                    'source_name': target_name,
                    'source': 'closure_syntax_repair',
                    'target_path': target_path,
                },
                'review_criteria': [
                    'html_css_syntax_sanity',
                    'preserve_runtime_artifact_links',
                ],
            }
            checks.append({key: value for key, value in check.items() if value not in (None, '', [], {})})
        return checks

    _normalized_review_criterion = staticmethod(SemanticClosureReview._normalized_review_criterion)

    _review_criterion_is_deterministic = staticmethod(SemanticClosureReview._review_criterion_is_deterministic)

    _decision_contract_from_graph = staticmethod(closure_repair_feedback._decision_contract_from_graph)

    _compact_mapping = staticmethod(intent_coverage._compact_mapping)

    @staticmethod
    def _identity_tokens(value: Mapping[str, Any]) -> set[str]:
        if not isinstance(value, Mapping):
            return set()
        tokens: set[str] = set()
        for key in ('task_id', 'workload_task_id', 'phase_id', 'branch_id', 'obligation_id', 'candidate_id'):
            token = str(value.get(key) or '').strip()
            if token:
                tokens.add(token)
        for container_key in ('workload_task_ref', 'output_obligation_ref'):
            container = value.get(container_key)
            if not isinstance(container, Mapping):
                continue
            for key in ('task_id', 'workload_task_id', 'phase_id', 'branch_id', 'obligation_id'):
                token = str(container.get(key) or '').strip()
                if token:
                    tokens.add(token)
        return tokens

    @classmethod
    def _decision_contract_item_matches_check(cls, item: Mapping[str, Any], check: Mapping[str, Any]) -> bool:
        return bool(cls._identity_tokens(item) & cls._identity_tokens(check))

    @classmethod
    def _decision_contract_matching_items(
        cls,
        decision_contract: Mapping[str, Any],
        check: Mapping[str, Any],
        key: str,
    ) -> list[dict[str, Any]]:
        if not isinstance(decision_contract, Mapping):
            return []
        raw_items = decision_contract.get(key)
        if not isinstance(raw_items, list):
            return []
        matches: list[dict[str, Any]] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, Mapping):
                continue
            if cls._decision_contract_item_matches_check(raw_item, check):
                matches.append(intent_coverage._compact_mapping(raw_item))
        return matches

    _string_list = staticmethod(SemanticClosureReview._string_list)

    @classmethod
    def _merge_string_list(cls, existing: Any, incoming: Any) -> list[str]:
        return SemanticClosureReview._string_list([*SemanticClosureReview._string_list(existing), *SemanticClosureReview._string_list(incoming)])

    @classmethod
    def _apply_semantic_lens_metadata(cls, updated: dict[str, Any], source: Mapping[str, Any]) -> None:
        if not isinstance(source, Mapping):
            return
        for key in ('semantic_review_lens', 'success_definition', 'semantic_review_lens_contract'):
            if source.get(key) not in (None, '', [], {}) and updated.get(key) in (None, '', [], {}):
                updated[key] = source.get(key)
        failure_modes = cls._merge_string_list(updated.get('failure_modes'), source.get('failure_modes'))
        if failure_modes:
            updated['failure_modes'] = failure_modes
        lens_evidence = cls._merge_string_list(
            updated.get('semantic_lens_evidence_requirements'),
            source.get('semantic_lens_evidence_requirements') or source.get('evidence_requirements'),
        )
        if lens_evidence:
            updated['semantic_lens_evidence_requirements'] = lens_evidence

    @classmethod
    def _decision_contract_review_payload(cls, decision_contract: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(decision_contract, Mapping) or not decision_contract:
            return {}
        accepted_learning = (
            decision_contract.get('accepted_learning')
            if isinstance(decision_contract.get('accepted_learning'), Mapping)
            else {}
        )
        payload = {
            'kind': 'fruth.decision_contract_closure_review',
            'status': 'available',
            'decision_contract_version': decision_contract.get('decision_contract_version'),
            'candidate_count': decision_contract.get('candidate_count'),
            'open_obligation_ids': decision_contract.get('open_obligation_ids'),
            'blocked_obligation_ids': decision_contract.get('blocked_obligation_ids'),
            'closed_obligation_ids': decision_contract.get('closed_obligation_ids'),
            'reconsideration_candidate_count': len(decision_contract.get('reconsideration_candidates') or []),
            'promotion_suggestion_count': len(decision_contract.get('promotion_suggestions') or []),
            'waiver_candidate_count': len(decision_contract.get('waiver_candidates') or []),
            'repair_candidate_count': len(decision_contract.get('repair_candidates') or []),
            'semantic_review_candidate_count': len(decision_contract.get('semantic_review_candidates') or []),
            'supersession_candidate_count': len(decision_contract.get('supersession_candidates') or []),
            'supersession_record_count': len(decision_contract.get('supersession_records') or []),
            'block_resolution_reflex': decision_contract.get('block_resolution_reflex'),
            'block_resolution_signal_count': (
                (decision_contract.get('block_resolution_reflex') or {}).get('signal_count')
                if isinstance(decision_contract.get('block_resolution_reflex'), Mapping)
                else None
            ),
            'active_reconsideration_review': decision_contract.get('active_reconsideration_review'),
            'active_reconsideration_decision_count': len(decision_contract.get('active_reconsideration_decisions') or []),
            'semantic_quality_review': decision_contract.get('semantic_quality_review'),
            'semantic_quality_contract_count': len(decision_contract.get('semantic_quality_contracts') or []),
            'recursive_cycle_review': decision_contract.get('recursive_cycle_review'),
            'recursive_cycle_task_count': len(decision_contract.get('recursive_cycle_tasks') or []),
            'aspiration_review': decision_contract.get('aspiration_review'),
            'aspiration_frame_count': len(decision_contract.get('aspiration_frames') or []),
            'commitment_review': decision_contract.get('commitment_review'),
            'commitment_frame_count': len(decision_contract.get('commitment_frames') or []),
            'semantic_decision_review': decision_contract.get('semantic_decision_review'),
            'semantic_decision_proposal_count': len(decision_contract.get('semantic_decision_proposals') or []),
            'controlled_attention_review': decision_contract.get('controlled_attention_review'),
            'controlled_attention_frame_count': len(decision_contract.get('controlled_attention_frames') or []),
            'semantic_review_lens_review': decision_contract.get('semantic_review_lens_review'),
            'semantic_review_lens_count': len(decision_contract.get('semantic_review_lenses') or []),
            'next_decision_priorities': decision_contract.get('next_decision_priorities'),
            'semantic_planning_contract': decision_contract.get('semantic_planning_contract'),
            'accepted_learning': {
                key: accepted_learning.get(key)
                for key in ('status', 'authority', 'runtime_effect', 'hint_count', 'allowed_use')
                if accepted_learning.get(key) not in (None, '', [], {})
            },
            'authority': 'read_model_only_not_runtime_truth',
        }
        return intent_coverage._compact_mapping(payload)

    _decision_contract_guidance_payload = staticmethod(closure_repair_feedback._decision_contract_guidance_payload)

    @classmethod
    def _surface_state_item(cls, source: Mapping[str, Any], *, category: str) -> dict[str, Any]:
        return intent_coverage._compact_mapping(
            {
                'category': category,
                'status': str(source.get('status') or '').strip().lower() or None,
                'check_kind': str(source.get('check_kind') or '').strip() or None,
                'obligation_id': str(source.get('obligation_id') or '').strip() or None,
                'task_id': str(source.get('task_id') or source.get('workload_task_id') or '').strip() or None,
                'phase_id': str(source.get('phase_id') or '').strip() or None,
                'branch_id': str(source.get('branch_id') or '').strip() or None,
                'candidate_id': str(source.get('candidate_id') or '').strip() or None,
                'capability': normalize_capability(source.get('capability')) or None,
                'output_type': str(source.get('output_type') or '').strip() or None,
                'reason': str(source.get('reason') or source.get('repair_action_reason') or '').strip() or None,
                'action': str(
                    source.get('aspiration_action')
                    or source.get('commitment_recommended_transition')
                    or source.get('commitment_action')
                    or source.get('active_reconsideration_action')
                    or source.get('controlled_attention_question')
                    or source.get('attention_question')
                    or source.get('repair_action')
                    or source.get('recovery_action')
                    or source.get('recommended_action')
                    or ''
                ).strip() or None,
                'review_type': str(
                    source.get('aspiration_review_type')
                    or source.get('commitment_review_type')
                    or source.get('active_reconsideration_review_type')
                    or source.get('review_type')
                    or source.get('scope')
                    or ''
                ).strip() or None,
                'semantic_review_lens': str(source.get('semantic_review_lens') or '').strip() or None,
                'success_definition': str(source.get('success_definition') or '').strip() or None,
                'priority': str(source.get('controlled_attention_priority') or source.get('priority') or '').strip() or None,
            }
        )

    @classmethod
    def _closure_surface_state(
        cls,
        *,
        review_status: str,
        reason: str,
        counts: Mapping[str, Any],
        checks: Sequence[Mapping[str, Any]],
        decision_contract: Mapping[str, Any],
        late_fill_status: str,
        pending_branches: Sequence[Mapping[str, Any]],
        semantic_review_required_count: int,
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        category_counts: dict[str, int] = {
            'open': int(counts.get('pending') or 0) + int(counts.get('deferred') or 0),
            'blocked': int(counts.get('blocked') or 0),
            'waived': int(counts.get('waived') or 0),
            'superseded': int(counts.get('superseded') or 0),
            'completed': int(counts.get('fulfilled') or 0),
            'semantic_review_pending': int(semantic_review_required_count or 0),
        }
        repair_pending_count = 0
        for check in checks:
            if not isinstance(check, Mapping):
                continue
            status = str(check.get('status') or '').strip().lower()
            if status in {'pending', 'planned', 'active', 'deferred'}:
                items.append(cls._surface_state_item(check, category='open'))
            elif status == 'blocked':
                items.append(cls._surface_state_item(check, category='blocked'))
            elif status == 'waived':
                items.append(cls._surface_state_item(check, category='waived'))
            elif status == 'superseded':
                items.append(cls._surface_state_item(check, category='superseded'))
            elif status == 'fulfilled':
                items.append(cls._surface_state_item(check, category='completed'))
            unresolved_for_repair = status in {'pending', 'planned', 'active', 'deferred', 'blocked', ''}
            if (
                unresolved_for_repair
                and (
                    check.get('repair_action') not in (None, '', [], {})
                    or check.get('repair_required') is True
                )
            ):
                repair_pending_count += 1
                items.append(cls._surface_state_item(check, category='repair_pending'))
            if check.get('semantic_review_required') is True:
                items.append(cls._surface_state_item(check, category='semantic_review_pending'))
        category_counts['repair_pending'] = repair_pending_count

        reconsideration_decisions = (
            decision_contract.get('active_reconsideration_decisions')
            if isinstance(decision_contract, Mapping) and isinstance(decision_contract.get('active_reconsideration_decisions'), list)
            else []
        )
        reconsiderable_count = 0
        waived_candidate_count = 0
        superseded_candidate_count = 0
        repair_advisory_count = 0
        semantic_review_advisory_count = 0
        for decision in reconsideration_decisions:
            if not isinstance(decision, Mapping):
                continue
            category = str(decision.get('source_category') or '').strip().lower()
            if category in {'reconsiderable_candidate', 'waiver_candidate', 'supersession_candidate'}:
                reconsiderable_count += 1
                items.append(cls._surface_state_item(decision, category='reconsiderable'))
            elif category in {'waived_candidate'}:
                waived_candidate_count += 1
                items.append(cls._surface_state_item(decision, category='waived'))
            elif category in {'superseded_candidate'}:
                superseded_candidate_count += 1
                items.append(cls._surface_state_item(decision, category='superseded'))
            elif category in {'repair_candidate'}:
                repair_advisory_count += 1
                items.append(cls._surface_state_item(decision, category='repair_advisory'))
            elif category in {'semantic_review_candidate'}:
                semantic_review_advisory_count += 1
                items.append(cls._surface_state_item(decision, category='semantic_review_advisory'))
        category_counts['reconsiderable'] = reconsiderable_count
        category_counts['waived'] = int(category_counts.get('waived') or 0) + waived_candidate_count
        category_counts['superseded'] = int(category_counts.get('superseded') or 0) + superseded_candidate_count
        if repair_advisory_count:
            category_counts['repair_advisory'] = repair_advisory_count
        if semantic_review_advisory_count:
            category_counts['semantic_review_advisory'] = semantic_review_advisory_count

        attention_frames = (
            decision_contract.get('controlled_attention_frames')
            if isinstance(decision_contract, Mapping) and isinstance(decision_contract.get('controlled_attention_frames'), list)
            else []
        )
        controlled_attention_count = 0
        for frame in attention_frames:
            if not isinstance(frame, Mapping):
                continue
            controlled_attention_count += 1
            items.append(cls._surface_state_item(frame, category='controlled_attention_advisory'))
        if controlled_attention_count:
            category_counts['controlled_attention_advisory'] = controlled_attention_count

        aspiration_frames = (
            decision_contract.get('aspiration_frames')
            if isinstance(decision_contract, Mapping) and isinstance(decision_contract.get('aspiration_frames'), list)
            else []
        )
        aspiration_count = 0
        for frame in aspiration_frames:
            if not isinstance(frame, Mapping):
                continue
            aspiration_count += 1
            items.append(cls._surface_state_item(frame, category='aspiration_advisory'))
        if aspiration_count:
            category_counts['aspiration_advisory'] = aspiration_count

        commitment_frames = (
            decision_contract.get('commitment_frames')
            if isinstance(decision_contract, Mapping) and isinstance(decision_contract.get('commitment_frames'), list)
            else []
        )
        commitment_count = 0
        for frame in commitment_frames:
            if not isinstance(frame, Mapping):
                continue
            commitment_count += 1
            items.append(cls._surface_state_item(frame, category='commitment_advisory'))
        if commitment_count:
            category_counts['commitment_advisory'] = commitment_count

        if pending_branches:
            category_counts['late_fill_pending'] = len([item for item in pending_branches if isinstance(item, Mapping)])
        active_categories = [
            category
            for category, count in category_counts.items()
            if int(count or 0) > 0
        ]
        return intent_coverage._compact_mapping(
            {
                'kind': 'fruth.surface_state',
                'status': str(review_status or '').strip().lower() or None,
                'reason': str(reason or '').strip() or None,
                'authority': 'runtime_projection_not_ui_truth',
                'late_fill_status': str(late_fill_status or '').strip().lower() or None,
                'category_counts': category_counts,
                'active_categories': active_categories,
                'items': items,
            }
        )

    @classmethod
    def _apply_decision_contract_to_check(
        cls,
        check: Mapping[str, Any],
        decision_contract: Mapping[str, Any],
    ) -> dict[str, Any]:
        updated = dict(check)
        if not isinstance(decision_contract, Mapping) or not decision_contract:
            return updated

        matched_repairs = cls._decision_contract_matching_items(
            decision_contract,
            updated,
            'repair_candidates',
        )
        if matched_repairs:
            flattened_repair_candidates: list[dict[str, Any]] = []
            for item in matched_repairs:
                if item.get('repair_action') not in (None, '', [], {}) or item.get('recovery_action') not in (None, '', [], {}):
                    flattened_repair_candidates.append(intent_coverage._compact_mapping(item))
                for candidate in item.get('repair_candidates') or []:
                    if isinstance(candidate, Mapping):
                        flattened_repair_candidates.append(intent_coverage._compact_mapping(candidate))
                for key in ('advisory_role', 'evidence_requirements', 'reconsideration_triggers', 'learning_hint_refs'):
                    if item.get(key) not in (None, '', [], {}) and updated.get(key) in (None, '', [], {}):
                        updated[key] = item.get(key)
                cls._apply_semantic_lens_metadata(updated, item)
            if flattened_repair_candidates:
                updated['decision_contract_repair_candidates'] = flattened_repair_candidates
                if updated.get('repair_candidates') in (None, '', [], {}):
                    updated['repair_candidates'] = flattened_repair_candidates
                if updated.get('repair_action') in (None, '', [], {}):
                    for candidate in flattened_repair_candidates:
                        action = normalize_recovery_suggested_action(candidate.get('repair_action') or candidate.get('recovery_action'))
                        if action:
                            updated['repair_action'] = action
                            updated['recovery_action'] = action
                            updated['repair_action_reason'] = (
                                str(candidate.get('reason') or '').strip()
                                or 'decision contract repair candidate matched this open closure check'
                            )
                            break

        matched_semantic_reviews = cls._decision_contract_matching_items(
            decision_contract,
            updated,
            'semantic_review_candidates',
        )
        if matched_semantic_reviews:
            updated['decision_contract_semantic_review_candidates'] = matched_semantic_reviews
            for item in matched_semantic_reviews:
                criteria = item.get('review_criteria') or item.get('semantic_review_criteria')
                merged = cls._merge_string_list(updated.get('semantic_review_criteria'), criteria)
                if merged:
                    updated['semantic_review_criteria'] = merged
                    updated['review_criteria'] = cls._merge_string_list(updated.get('review_criteria'), merged)
                for key in ('advisory_role', 'evidence_requirements', 'reconsideration_triggers', 'learning_hint_refs'):
                    if item.get(key) not in (None, '', [], {}) and updated.get(key) in (None, '', [], {}):
                        updated[key] = item.get(key)
                cls._apply_semantic_lens_metadata(updated, item)

        matched_quality_contracts = cls._decision_contract_matching_items(
            decision_contract,
            updated,
            'semantic_quality_contracts',
        )
        if matched_quality_contracts:
            updated['decision_contract_semantic_quality_contracts'] = matched_quality_contracts
            first_contract = matched_quality_contracts[0]
            quality_criteria = SemanticClosureReview._string_list(first_contract.get('semantic_review_criteria')) or SemanticClosureReview._string_list(first_contract.get('review_criteria'))
            quality_requires_semantic_review = any(
                not SemanticClosureReview._review_criterion_is_deterministic(item)
                for item in quality_criteria
            )
            updated['semantic_quality_contract'] = first_contract
            updated['semantic_quality_status'] = (
                str(first_contract.get('status') or '').strip()
                or 'pending_semantic_review'
            )
            updated['semantic_quality_review_id'] = str(first_contract.get('quality_review_id') or '').strip() or None
            cls._apply_semantic_lens_metadata(updated, first_contract)
            updated['semantic_review_authority'] = 'advisory_until_promoted_semantic_verifier'
            if quality_requires_semantic_review:
                updated['semantic_review_required'] = True
                updated['semantic_review_action'] = RECOVERY_ACTION_SEMANTIC_REVIEW
            merged = cls._merge_string_list(
                updated.get('semantic_review_criteria'),
                quality_criteria,
            )
            if merged:
                updated['semantic_review_criteria'] = merged
                updated['review_criteria'] = cls._merge_string_list(updated.get('review_criteria'), merged)

        matched_block_resolution = cls._decision_contract_matching_items(
            decision_contract,
            updated,
            'reconsideration_reflex_signals',
        )
        if matched_block_resolution:
            updated['decision_contract_block_resolution_signals'] = matched_block_resolution
            first_signal = matched_block_resolution[0]
            updated['block_resolution_signal'] = first_signal
            updated['block_resolution_action'] = str(first_signal.get('action') or '').strip() or None
            updated['block_resolution_policy'] = (
                str(first_signal.get('resolution_policy') or '').strip()
                or 'right_sized_verified_state_transition'
            )
            updated['reconsideration_reflex'] = {
                'kind': 'fruth.check_reconsideration_reflex',
                'authority': 'advisory_read_model_only',
                'signal_count': len(matched_block_resolution),
                'principle': 'the_solution_to_a_block_is_the_blocks_own_resolution',
            }

        matched_active_reconsideration = cls._decision_contract_matching_items(
            decision_contract,
            updated,
            'active_reconsideration_decisions',
        )
        if matched_active_reconsideration:
            updated['decision_contract_active_reconsideration_decisions'] = matched_active_reconsideration
            first_decision = matched_active_reconsideration[0]
            updated['active_reconsideration_decision'] = first_decision
            updated['active_reconsideration_action'] = str(first_decision.get('recommended_action') or '').strip() or None
            updated['active_reconsideration_review_type'] = str(first_decision.get('review_type') or '').strip() or None
            updated['active_reconsideration_review'] = {
                'kind': 'fruth.check_active_reconsideration_review',
                'authority': 'advisory_read_model_only',
                'decision_count': len(matched_active_reconsideration),
                'status': 'pending_review',
            }

        matched_recursive_cycle = cls._decision_contract_matching_items(
            decision_contract,
            updated,
            'recursive_cycle_tasks',
        )
        if matched_recursive_cycle:
            updated['recursive_cycle_state'] = matched_recursive_cycle[0]
            cls._apply_semantic_lens_metadata(updated, matched_recursive_cycle[0])

        matched_aspiration = cls._decision_contract_matching_items(
            decision_contract,
            updated,
            'aspiration_frames',
        )
        if matched_aspiration:
            updated['decision_contract_aspiration_frames'] = matched_aspiration
            first_frame = matched_aspiration[0]
            updated['aspiration_frame'] = first_frame
            updated['aspiration_frame_id'] = str(first_frame.get('frame_id') or '').strip() or None
            updated['aspiration_action'] = str(first_frame.get('aspiration_action') or first_frame.get('recommended_action') or '').strip() or None
            updated['aspiration_reason'] = str(first_frame.get('reason') or '').strip() or None
            updated['aspiration_allowed_actions'] = first_frame.get('allowed_actions')
            cls._apply_semantic_lens_metadata(updated, first_frame)
            updated['aspiration_review'] = {
                'kind': 'fruth.check_aspiration_review',
                'authority': 'advisory_read_model_only',
                'frame_count': len(matched_aspiration),
                'status': 'attention_pending',
            }

        matched_commitment = cls._decision_contract_matching_items(
            decision_contract,
            updated,
            'commitment_frames',
        )
        if matched_commitment:
            updated['decision_contract_commitment_frames'] = matched_commitment
            first_frame = matched_commitment[0]
            updated['commitment_frame'] = first_frame
            updated['commitment_frame_id'] = str(first_frame.get('frame_id') or '').strip() or None
            updated['commitment_action'] = str(first_frame.get('commitment_action') or first_frame.get('recommended_action') or '').strip() or None
            updated['commitment_recommended_transition'] = str(first_frame.get('recommended_transition') or '').strip() or None
            updated['commitment_reason'] = str(first_frame.get('reason') or '').strip() or None
            updated['commitment_allowed_transitions'] = first_frame.get('allowed_transitions')
            cls._apply_semantic_lens_metadata(updated, first_frame)
            updated['commitment_review'] = {
                'kind': 'fruth.check_commitment_review',
                'authority': 'advisory_read_model_only',
                'frame_count': len(matched_commitment),
                'status': 'attention_pending',
            }

        matched_semantic_decisions = cls._decision_contract_matching_items(
            decision_contract,
            updated,
            'semantic_decision_proposals',
        )
        if matched_semantic_decisions:
            updated['decision_contract_semantic_decision_proposals'] = matched_semantic_decisions
            first_proposal = matched_semantic_decisions[0]
            updated['semantic_decision_proposal'] = first_proposal
            updated['semantic_decision_action'] = str(first_proposal.get('decision_action') or '').strip() or None
            confidence = first_proposal.get('confidence')
            if isinstance(confidence, (int, float)):
                updated['semantic_decision_confidence'] = confidence
            updated['semantic_decision_reason'] = str(first_proposal.get('reason') or '').strip() or None
            cls._apply_semantic_lens_metadata(updated, first_proposal)
            action = str(first_proposal.get('decision_action') or '').strip()
            if action == RECOVERY_ACTION_SEMANTIC_REVIEW or action == 'semantic_review':
                updated['semantic_review_required'] = True
                updated['semantic_review_action'] = RECOVERY_ACTION_SEMANTIC_REVIEW
                if updated.get('semantic_review_authority') in (None, '', [], {}):
                    updated['semantic_review_authority'] = 'advisory_until_promoted_semantic_verifier'
            normalized_action = (
                normalize_recovery_suggested_action(action)
                if action.lower() in RECOVERY_SUGGESTED_ACTIONS
                else ''
            )
            if normalized_action and updated.get('repair_action') in (None, '', [], {}):
                updated['repair_action'] = normalized_action
                updated['recovery_action'] = normalized_action
                updated['repair_action_reason'] = (
                    str(first_proposal.get('reason') or '').strip()
                    or 'semantic decision proposal matched this open closure check'
                )

        matched_controlled_attention = cls._decision_contract_matching_items(
            decision_contract,
            updated,
            'controlled_attention_frames',
        )
        if matched_controlled_attention:
            updated['decision_contract_controlled_attention_frames'] = matched_controlled_attention
            first_frame = matched_controlled_attention[0]
            updated['controlled_attention_frame'] = first_frame
            updated['controlled_attention_frame_id'] = str(first_frame.get('frame_id') or '').strip() or None
            updated['controlled_attention_scope'] = str(first_frame.get('scope') or '').strip() or None
            updated['controlled_attention_priority'] = str(first_frame.get('priority') or '').strip() or None
            updated['controlled_attention_question'] = str(first_frame.get('attention_question') or '').strip() or None
            updated['controlled_attention_allowed_transitions'] = first_frame.get('allowed_transitions')
            cls._apply_semantic_lens_metadata(updated, first_frame)

        matched_semantic_lenses = cls._decision_contract_matching_items(
            decision_contract,
            updated,
            'semantic_review_lenses',
        )
        if matched_semantic_lenses:
            updated['decision_contract_semantic_review_lenses'] = matched_semantic_lenses
            cls._apply_semantic_lens_metadata(updated, matched_semantic_lenses[0])

        matched_promotions = cls._decision_contract_matching_items(
            decision_contract,
            updated,
            'promotion_suggestions',
        )
        if matched_promotions and updated.get('promotion_suggestions') in (None, '', [], {}):
            flattened_promotions: list[dict[str, Any]] = []
            for item in matched_promotions:
                for candidate in item.get('promotion_suggestions') or []:
                    if isinstance(candidate, Mapping):
                        flattened_promotions.append(intent_coverage._compact_mapping(candidate))
            if flattened_promotions:
                updated['promotion_suggestions'] = flattened_promotions

        matched_waivers = cls._decision_contract_matching_items(
            decision_contract,
            updated,
            'waiver_candidates',
        )
        if matched_waivers and updated.get('waiver_candidates') in (None, '', [], {}):
            flattened_waivers: list[dict[str, Any]] = []
            for item in matched_waivers:
                for candidate in item.get('waiver_candidates') or []:
                    if isinstance(candidate, Mapping):
                        flattened_waivers.append(intent_coverage._compact_mapping(candidate))
            if flattened_waivers:
                updated['waiver_candidates'] = flattened_waivers

        matched_supersessions = cls._decision_contract_matching_items(
            decision_contract,
            updated,
            'supersession_candidates',
        )
        if matched_supersessions:
            flattened_supersession_candidates: list[dict[str, Any]] = []
            for item in matched_supersessions:
                for candidate in item.get('supersession_candidates') or []:
                    if isinstance(candidate, Mapping):
                        flattened_supersession_candidates.append(intent_coverage._compact_mapping(candidate))
            if flattened_supersession_candidates:
                updated['decision_contract_supersession_candidates'] = flattened_supersession_candidates
                if updated.get('supersession_candidates') in (None, '', [], {}):
                    updated['supersession_candidates'] = flattened_supersession_candidates
                updated['supersession_review_required'] = True
                updated['supersession_review_authority'] = 'closure_review_required'

        return updated

    def _apply_review_criteria_to_check(self, check: Mapping[str, Any]) -> dict[str, Any]:
        updated = dict(check)
        criteria = [
            str(item or '').strip()
            for item in (updated.get('review_criteria') or [])
            if str(item or '').strip()
        ] if isinstance(updated.get('review_criteria'), list) else []
        if not criteria:
            return updated
        updated['review_criteria'] = criteria
        status = str(updated.get('status') or '').strip().lower()
        capability = normalize_capability(updated.get('capability'))
        depends_on = [
            str(item or '').strip()
            for item in (updated.get('depends_on') or [])
            if str(item or '').strip()
        ] if isinstance(updated.get('depends_on'), list) else []
        if status in {'superseded', 'waived'}:
            updated['review_criteria_status'] = 'not_required'
            return updated
        issues: list[dict[str, Any]] = []
        for criterion in criteria:
            normalized = self.semantic_closure_review._normalized_review_criterion(criterion)
            if (
                status == 'fulfilled'
                and capability == CAPABILITY_CHAT
                and depends_on
                and normalized in {'uses_dependency_evidence', 'does_not_restart_root_request'}
                and not self._check_has_dependency_runtime_evidence(updated)
            ):
                issues.append(
                    {
                        'criterion': criterion,
                        'code': 'dependency_evidence_not_bound_to_branch',
                        'severity': 'blocking',
                        'suggested_action': RECOVERY_ACTION_REPAIR_DEPENDENCY_CHAIN,
                        'reason': 'fulfilled text branch lacks branch-local dependency evidence',
                    }
                )
        if not issues:
            semantic_criteria = [
                criterion
                for criterion in criteria
                if not self.semantic_closure_review._review_criterion_is_deterministic(criterion)
            ]
            if semantic_criteria:
                updated['review_criteria_status'] = 'semantic_review_required'
                updated['semantic_review_required'] = True
                if updated.get('semantic_review_authority') in (None, '', [], {}):
                    updated['semantic_review_authority'] = 'advisory'
                if updated.get('semantic_review_action') in (None, '', [], {}):
                    updated['semantic_review_action'] = RECOVERY_ACTION_SEMANTIC_REVIEW
                updated['semantic_review_criteria'] = semantic_criteria
            else:
                updated['review_criteria_status'] = 'passed'
            return updated
        updated['review_criteria_status'] = 'repair_required'
        updated['review_criteria_issues'] = issues
        updated['status'] = 'pending'
        updated['evidence'] = 'review_criteria_unverified'
        updated['blocked_by_dependency_input'] = True
        updated['repair_required'] = True
        updated['repair_action'] = RECOVERY_ACTION_REPAIR_DEPENDENCY_CHAIN
        updated['recovery_action'] = RECOVERY_ACTION_REPAIR_DEPENDENCY_CHAIN
        updated['repair_action_reason'] = 'review criteria require dependency evidence before freeze'
        return updated

    _repair_contract_id = staticmethod(closure_repair_feedback._repair_contract_id)

    _repair_item_has_concrete_input_evidence = staticmethod(closure_repair_feedback._repair_item_has_concrete_input_evidence)

    _repair_contract_execution_policy = staticmethod(closure_repair_feedback._repair_contract_execution_policy)

    _repair_contract_resolution_state = staticmethod(closure_repair_feedback._repair_contract_resolution_state)

    _expand_counted_repair_items = staticmethod(closure_repair_feedback._expand_counted_repair_items)

    _repair_rebuild_contracts = staticmethod(closure_repair_feedback._repair_rebuild_contracts)

    build_inference_repair_feedback = staticmethod(closure_repair_feedback.build_inference_repair_feedback)

    @observe_call('response_semantics.build_graph_closure_review',
                  target=lambda a: exact_target(a['artifact_payload'] or {}),
                  result=judgment_summary)
    def _saved_file_consumption_review(self, branch, payload):
        return saved_file_consumption_artifact_issue(
            branch, payload, self.semantic_artifact_reader._resolved_semantic_review_artifact_path)

    def build_graph_closure_review(
        self,
        output_text: str,
        *,
        route_payload: Optional[dict[str, Any]] = None,
        request_payload: Optional[dict[str, Any]] = None,
        artifact_payload: Optional[dict[str, Any]] = None,
        artifact_gap: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        artifact_info = artifact_payload if isinstance(artifact_payload, dict) else {}
        route_runtime = (
            route_payload.get('route_runtime')
            if isinstance(route_payload, Mapping) and isinstance(route_payload.get('route_runtime'), Mapping)
            else {}
        )
        artifact_runtime = (
            artifact_info.get('runtime')
            if isinstance(artifact_info.get('runtime'), Mapping)
            else {}
        )
        request_phase_graph = (
            artifact_runtime.get('request_phase_graph')
            if isinstance(artifact_runtime.get('request_phase_graph'), Mapping)
            else (
                route_runtime.get('request_phase_graph')
                if isinstance(route_runtime.get('request_phase_graph'), Mapping)
                else {}
            )
        )
        payload: dict[str, Any] = {
            'kind': 'fruth.graph_closure_review',
            'intent_boundary': 'anchored_intent_fluid_state',
            'status': 'not_applicable',
            'reason': 'no_request_phase_graph',
            'checks': [],
        }
        if not isinstance(request_phase_graph, Mapping) or not request_phase_graph:
            return payload

        raw_content = request_phase_graph.get('content_requirements')
        accepted_content = raw_content if isinstance(raw_content, list) else []
        named_saved_path = any(saved_file_dependency_contract(branch)
            for branch in request_phase_graph.get('downstream_branches', [])
            if isinstance(branch, Mapping))
        content_policy = (
            request_phase_graph.get('content_requirement_policy') == 'named_saved_text_v1'
            or (named_saved_path and request_intent_payload(request_payload or {}).get(
                'content_requirement_policy') == 'named_saved_text_v1')
        )
        # The accepted request is independent of graph/result metadata. Losing a
        # downstream policy label cannot downgrade a newly captured request.
        reference_sources = [request_intent_payload(request_payload or {}), request_phase_graph]
        reference_sources.extend(branch.get('artifact_request') or {}
            for branch in request_phase_graph.get('downstream_branches', []) if isinstance(branch, Mapping))
        reference_policies = [source.get('content_review_reference_policy') for source in reference_sources
            if isinstance(source, Mapping) and 'content_review_reference_policy' in source]
        content_reference_policy = (
            CONTENT_REVIEW_REFERENCE_POLICY if reference_policies
            and all(policy == CONTENT_REVIEW_REFERENCE_POLICY for policy in reference_policies)
            else 'invalid' if reference_policies else '')
        try:
            content_metadata_valid = isinstance(raw_content, list) and len(accepted_content) == 2 and all(
                isinstance(item, Mapping) and all(isinstance(item.get(key), str) and item[key].strip()
                    for key in ('branch_id', 'phase_id', 'requirement_id', 'role', 'text'))
                and item.get('criterion') == f"accepted_{item.get('role')}_content"
                and item.get('sha256') == hashlib.sha256(item['text'].encode('utf-8')).hexdigest()
                for item in accepted_content
            )
            content_metadata_valid = content_metadata_valid and len({item['branch_id'] for item in accepted_content}) == 2
            content_metadata_valid = content_metadata_valid and {item['role'] for item in accepted_content} == {'producer', 'consumer'}
        except (TypeError, ValueError, UnicodeError):
            content_metadata_valid = False

        decision_contract = closure_repair_feedback._decision_contract_from_graph(request_phase_graph)
        decision_contract_review = self._decision_contract_review_payload(decision_contract)
        workload_tasks_by_phase, workload_tasks_by_branch = self._workload_task_indexes(request_phase_graph)
        late_fill = artifact_info.get('late_fill') if isinstance(artifact_info.get('late_fill'), Mapping) else {}
        late_fill_status = str(late_fill.get('status') or '').strip().lower()
        pending_branches = self._extract_pending_deferred_branches(
            route_payload=route_payload,
            artifact_payload=artifact_payload,
        )
        pending_branch_ids = {
            str(item.get('branch_id') or item.get('phase_id') or '').strip()
            for item in pending_branches
            if isinstance(item, Mapping) and str(item.get('branch_id') or item.get('phase_id') or '').strip()
        }
        completed_branch_ids = {
            str(item.get('branch_id') or item.get('phase_id') or '').strip()
            for item in (late_fill.get('completed_branches') or [])
            if isinstance(item, Mapping) and str(item.get('branch_id') or item.get('phase_id') or '').strip()
        }
        completed_branches_by_id = {
            str(item.get('branch_id') or item.get('phase_id') or '').strip(): item
            for item in (late_fill.get('completed_branches') or [])
            if isinstance(item, Mapping) and str(item.get('branch_id') or item.get('phase_id') or '').strip()
        }
        final_materialization_contract_fulfilled = bool(
            late_fill_status == 'completed'
            and str(late_fill.get('final_materialization_contract_status') or '').strip().lower()
            == 'fulfilled'
            and late_fill.get('materialization_contract_unmet') is not True
        )
        failed_branch_records = [
            item
            for item in (late_fill.get('failed_branches') or [])
            if isinstance(item, Mapping)
        ]
        cancelled_branch_records = [
            item
            for item in (late_fill.get('cancelled_branches') or [])
            if isinstance(item, Mapping)
        ]
        failed_branch_ids = {
            str(item.get('branch_id') or item.get('phase_id') or '').strip()
            for item in failed_branch_records
            if str(item.get('branch_id') or item.get('phase_id') or '').strip()
        }
        cancelled_branch_ids = {
            str(item.get('branch_id') or item.get('phase_id') or '').strip()
            for item in cancelled_branch_records
            if str(item.get('branch_id') or item.get('phase_id') or '').strip()
        }
        failed_branches_by_id = {
            str(item.get('branch_id') or item.get('phase_id') or '').strip(): item
            for item in failed_branch_records
            if str(item.get('branch_id') or item.get('phase_id') or '').strip()
        }
        completed_capabilities = set(self._hook('normalize_capability_list')(late_fill.get('completed_capabilities')))
        failed_capabilities = set(self._hook('normalize_capability_list')(late_fill.get('failed_capabilities')))
        cancelled_capabilities = set(self._hook('normalize_capability_list')(late_fill.get('cancelled_capabilities')))
        current_phase_id = str(request_phase_graph.get('current_phase_id') or '').strip()
        phases = request_phase_graph.get('phases') if isinstance(request_phase_graph.get('phases'), list) else []
        output_obligations = output_obligations_from_graph(request_phase_graph)
        check_sources: list[dict[str, Any]]
        if output_obligations:
            check_sources = output_obligations
        else:
            check_sources = [dict(item) for item in phases if isinstance(item, Mapping)]
        capability_source_counts: dict[str, int] = {}
        for raw_source in check_sources:
            if not isinstance(raw_source, Mapping):
                continue
            source_capability = normalize_capability(raw_source.get('capability'))
            if source_capability:
                capability_source_counts[source_capability] = (
                    capability_source_counts.get(source_capability, 0) + 1
                )
        checks: list[dict[str, Any]] = []
        artifact_type_counts: dict[str, int] = {}
        consumed_artifact_type_counts: dict[str, int] = {}

        def tts_integrity_evidence_for(
            branch_id: str,
            phase_id: str,
        ) -> dict[str, Any]:
            candidates: list[Mapping[str, Any]] = []
            for result in late_fill.get('fill_results') or []:
                if not isinstance(result, Mapping):
                    continue
                result_tokens = {
                    str(result.get('branch_id') or '').strip(),
                    str(result.get('phase_id') or '').strip(),
                }
                result_tokens.discard('')
                if (
                    (branch_id or phase_id)
                    and not result_tokens.intersection(
                        {token for token in (branch_id, phase_id) if token}
                    )
                ):
                    continue
                evidence = result.get('tts_audio_integrity_evidence')
                if isinstance(evidence, Mapping):
                    candidates.append(evidence)
            top_level = artifact_info.get('tts_audio_integrity_evidence')
            if isinstance(top_level, Mapping):
                candidates.append(top_level)
            return dict(candidates[0]) if candidates else {}

        semantic_review_prompt = intent_coverage._current_request_prompt_for_review(
            request_payload,
            request_phase_graph,
        )
        accepted_file_identities = {
            (str(item.get('target_name') or '').strip().lower(),
             str(item.get('target_extension') or '').strip().lower())
            for item in required_intent_obligations(request_phase_graph.get('intent_obligations') or [])
            if item.get('kind') == 'text_artifact' and item.get('source') == 'current_user_intent'
        }
        file_evidence_check = self.hooks.get('text_artifact_branch_has_canonical_evidence')
        for raw_source in check_sources:
            if not isinstance(raw_source, Mapping):
                continue
            obligation_id = str(raw_source.get('obligation_id') or '').strip()
            phase_id = str(raw_source.get('phase_id') or '').strip()
            branch_id = str(raw_source.get('branch_id') or phase_id or '').strip()
            workload_task_record = (
                workload_tasks_by_phase.get(phase_id)
                or workload_tasks_by_branch.get(branch_id)
                or {}
            )
            capability = normalize_capability(raw_source.get('capability'))
            is_unique_capability_source = (
                bool(capability)
                and capability_source_counts.get(capability, 0) <= 1
            )
            output_type = str(raw_source.get('output_type') or '').strip().lower()
            if not output_type:
                output_type = str(intent_coverage.artifact_type_for_capability(capability) or '').strip().lower()
            source_status = str(raw_source.get('status') or '').strip().lower()
            evidence = 'output_obligation_status' if output_obligations else 'phase_status'
            source_role = str(raw_source.get('role') or '').strip()
            requires_text_artifact = self.source_requires_text_artifact(raw_source, output_type)
            text_artifact_revision_required = (
                self._text_artifact_revision_required_for_closure(raw_source)
            )
            source_depends_on = [
                str(item or '').strip()
                for item in (raw_source.get('depends_on') or [])
                if str(item or '').strip()
            ]
            failed_branch_record = failed_branches_by_id.get(branch_id) if branch_id else None
            completed_branch_record = completed_branches_by_id.get(branch_id) if branch_id else None
            completed_branch_status = str(
                completed_branch_record.get('status')
                if isinstance(completed_branch_record, Mapping)
                else ''
            ).strip().lower()
            completed_branch_evidence = str(
                completed_branch_record.get('evidence')
                if isinstance(completed_branch_record, Mapping)
                else ''
            ).strip()
            text_artifact_revision_evidence = (
                self._text_artifact_revision_closure_evidence(
                    raw_source,
                    artifact_payload=artifact_info,
                    late_fill=late_fill,
                    branch_id=branch_id,
                    phase_id=phase_id,
                )
                if text_artifact_revision_required
                else {}
            )
            tts_audio_integrity_evidence = (
                tts_integrity_evidence_for(branch_id, phase_id)
                if capability == CAPABILITY_TEXT_TO_SPEECH
                and output_type == 'audio'
                else {}
            )
            tts_audio_artifact_present = bool(
                capability == CAPABILITY_TEXT_TO_SPEECH
                and output_type == 'audio'
                and (
                    str(artifact_info.get('saved_audio_path') or '').strip()
                    or self.response_payload_artifact_type_count(
                        artifact_info,
                        'audio',
                    )
                    or branch_id in completed_branch_ids
                    or source_status in {'completed', 'fulfilled'}
                )
            )
            tts_audio_integrity_passed = bool(
                str(
                    tts_audio_integrity_evidence.get('status') or ''
                ).strip().lower()
                == 'passed'
                and tts_audio_integrity_evidence.get(
                    'materialization_eligible'
                )
                is True
            )
            completed_in_place_materialization_repair = bool(
                isinstance(completed_branch_record, Mapping)
                and completed_branch_status in {'completed', 'fulfilled'}
                and (
                    completed_branch_record.get('non_blocking_after_final_contract_fulfilled') is True
                    or completed_branch_evidence
                    in {
                        'canonical_text_artifact_evidence',
                        'terminal_inline_text_artifact_materialized',
                        'terminal_linked_artifact_rebind_applied',
                    }
                    or (
                        final_materialization_contract_fulfilled
                        and source_role
                        in {
                            'linked_artifact_binding_review',
                            'text_artifact_syntax_repair',
                        }
                    )
                )
            )
            status = source_status or 'pending'

            if (
                tts_audio_artifact_present
                and not tts_audio_integrity_passed
                and source_status not in _SUPERSEDED_OBLIGATION_STATUSES
                and source_status not in _WAIVED_OBLIGATION_STATUSES
            ):
                status = 'blocked'
                evidence = (
                    'tts_audio_integrity_failed'
                    if tts_audio_integrity_evidence
                    else 'tts_audio_integrity_evidence_missing'
                )
            elif source_status in _SUPERSEDED_OBLIGATION_STATUSES:
                status = 'superseded'
                evidence = 'explicit_obligation_superseded'
            elif source_status in _WAIVED_OBLIGATION_STATUSES:
                status = 'waived'
                evidence = 'explicit_obligation_waiver'
            elif raw_source.get('branch_contract_error') == 'saved_file_dependency_unbound':
                status = 'blocked'
                evidence = 'saved_file_dependency_unbound'
            elif branch_id and branch_id in failed_branch_ids:
                status = 'blocked'
                evidence = 'late_fill_failed_branch'
            elif branch_id and branch_id in cancelled_branch_ids:
                status = 'waived'
                evidence = 'late_fill_cancelled_branch'
            elif saved_file_dependency_contract(raw_source):
                saved_issue = self._saved_file_consumption_review(raw_source, artifact_info)
                status = 'blocked' if saved_issue else 'fulfilled'
                evidence = saved_issue or 'saved_file_consumption_verified'
                if not saved_issue:
                    consumed_artifact_type_counts['text'] = consumed_artifact_type_counts.get('text', 0) + 1
            elif text_artifact_revision_required:
                revision_evidence = str(
                    text_artifact_revision_evidence.get('evidence') or ''
                ).strip()
                if text_artifact_revision_evidence.get('status') == 'passed':
                    status = 'fulfilled'
                    evidence = revision_evidence or 'text_artifact_revision_write_proven'
                else:
                    status = (
                        'blocked'
                        if revision_evidence
                        in {
                            'text_artifact_revision_output_hash_mismatch',
                            'text_artifact_revision_preservation_failed',
                            'text_artifact_revision_saved_target_missing',
                            'text_artifact_revision_write_proof_target_mismatch',
                        }
                        else 'pending'
                    )
                    evidence = (
                        revision_evidence
                        or 'text_artifact_revision_write_proof_missing_or_invalid'
                    )
            elif completed_in_place_materialization_repair:
                # A verified in-place rebind/repair updates an existing saved
                # artifact; it must not consume a fictitious extra artifact.
                status = 'fulfilled'
                evidence = 'late_fill_completed_in_place_materialization_repair'
            elif branch_id and branch_id in completed_branch_ids and not requires_text_artifact:
                status = 'fulfilled'
                evidence = 'late_fill_completed_branch'
            elif is_unique_capability_source and capability in failed_capabilities:
                status = 'blocked'
                evidence = 'late_fill_failed_capability'
            elif is_unique_capability_source and capability in cancelled_capabilities:
                status = 'waived'
                evidence = 'late_fill_cancelled_capability'
            elif (
                is_unique_capability_source
                and capability in completed_capabilities
                and not requires_text_artifact
            ):
                status = 'fulfilled'
                evidence = 'late_fill_completed_capability'
            elif (
                phase_id == current_phase_id
                and capability == CAPABILITY_CHAT
                and str(output_text or '').strip()
                and not requires_text_artifact
            ):
                status = 'fulfilled'
                evidence = 'current_phase_output_text'
            elif output_type:
                if output_type not in artifact_type_counts:
                    artifact_type_counts[output_type] = (
                        self.response_payload_real_text_artifact_count(artifact_info)
                        if requires_text_artifact and output_type == 'text'
                        else self.response_payload_artifact_type_count(
                            artifact_info,
                            output_type,
                        )
                    )
                consumed_count = consumed_artifact_type_counts.get(output_type, 0)
                if artifact_type_counts.get(output_type, 0) > consumed_count:
                    consumed_artifact_type_counts[output_type] = consumed_count + 1
                    status = 'fulfilled'
                    evidence = f'output_artifact_type:{output_type}'
                elif branch_id and branch_id in pending_branch_ids:
                    status = 'pending'
                    evidence = 'pending_graph_branch'
                elif status == 'completed':
                    status = 'fulfilled'
                elif status in {'failed', 'error'}:
                    status = 'blocked'
                elif status in _SUPERSEDED_OBLIGATION_STATUSES:
                    status = 'superseded'
                    evidence = 'explicit_obligation_superseded'
                elif status in _WAIVED_OBLIGATION_STATUSES:
                    status = 'waived'
                    evidence = 'explicit_obligation_waiver'
                elif status not in {'fulfilled', 'blocked', 'pending', 'deferred', 'planned', 'active', 'waived', 'superseded'}:
                    status = 'pending'
            elif branch_id and branch_id in pending_branch_ids:
                status = 'pending'
                evidence = 'pending_graph_branch'
            elif status == 'completed':
                status = 'fulfilled'
            elif status in {'failed', 'error'}:
                status = 'blocked'
            elif status in _SUPERSEDED_OBLIGATION_STATUSES:
                status = 'superseded'
                evidence = 'explicit_obligation_superseded'
            elif status in _WAIVED_OBLIGATION_STATUSES:
                status = 'waived'
                evidence = 'explicit_obligation_waiver'
            elif status not in {'fulfilled', 'blocked', 'pending', 'deferred', 'planned', 'active', 'waived', 'superseded'}:
                status = 'pending'

            # A type count cannot discharge an accepted named file obligation.
            # Reuse the terminal owner's read-only identity/dependency/write
            # evidence check; do not reinterpret the prompt or artifact content.
            if (
                status == 'fulfilled'
                and requires_text_artifact
                and (_expected_text_artifact_source_name(raw_source),
                     _expected_text_artifact_extension(raw_source)) in accepted_file_identities
                and callable(file_evidence_check)
                and not file_evidence_check(raw_source, artifact_info)
            ):
                status = 'pending'
                evidence = 'requested_text_artifact_missing'

            if (
                status == 'fulfilled'
                and evidence.startswith('late_fill_completed')
                and output_type
                and not (output_type == 'text' and not requires_text_artifact)
            ):
                if output_type not in artifact_type_counts:
                    artifact_type_counts[output_type] = self.response_payload_artifact_type_count(
                        artifact_info,
                        output_type,
                    )
                consumed_count = consumed_artifact_type_counts.get(output_type, 0)
                if artifact_type_counts.get(output_type, 0) > consumed_count:
                    consumed_artifact_type_counts[output_type] = consumed_count + 1

            check = {
                'obligation_id': obligation_id or None,
                'phase_id': phase_id or None,
                'branch_id': branch_id or None,
                'capability': capability or None,
                'output_type': output_type or None,
                'role': source_role or None,
                'depends_on': source_depends_on or None,
                'status': status,
                'evidence': evidence,
            }
            if text_artifact_revision_required:
                check['text_artifact_revision_required'] = True
                check['text_artifact_target_path'] = (
                    text_artifact_revision_evidence.get('target_path')
                )
                check['text_artifact_revision_closure_evidence'] = (
                    text_artifact_revision_evidence
                )
                if text_artifact_revision_evidence.get('status') != 'passed':
                    check['reason'] = (
                        'the required existing-file revision lacks matching '
                        'current-branch write and preservation evidence'
                    )
                    check['repair_action'] = RECOVERY_ACTION_RETRY_SAME_BRANCH
                    check['recovery_action'] = RECOVERY_ACTION_RETRY_SAME_BRANCH
                    check['repair_action_reason'] = (
                        'retry only this text-artifact revision against its '
                        'contracted source and target path'
                    )
                    check['materialization_blocked'] = True
            if (
                capability == CAPABILITY_TEXT_TO_SPEECH
                and output_type == 'audio'
                and tts_audio_artifact_present
            ):
                check['audio_integrity_status'] = (
                    str(tts_audio_integrity_evidence.get('status') or '').strip()
                    or 'unavailable'
                )
                check['audio_integrity_reason_code'] = (
                    str(
                        tts_audio_integrity_evidence.get('reason_code') or ''
                    ).strip()
                    or 'TTS_AUDIO_INTEGRITY_EVIDENCE_MISSING'
                )
                if tts_audio_integrity_evidence:
                    check['tts_audio_integrity_evidence'] = (
                        tts_audio_integrity_evidence
                    )
                if not tts_audio_integrity_passed:
                    check['reason'] = (
                        'generated audio exists but did not pass output-side '
                        'physical integrity verification'
                    )
                    check['repair_action'] = (
                        RECOVERY_ACTION_RETRY_SAME_BRANCH
                    )
                    check['recovery_action'] = (
                        RECOVERY_ACTION_RETRY_SAME_BRANCH
                    )
                    check['repair_action_reason'] = (
                        'retry the bounded TTS branch and require passed '
                        'audio-integrity evidence before fulfillment'
                    )
                    check['materialization_blocked'] = True
            for source in (
                raw_source,
                workload_task_record if isinstance(workload_task_record, Mapping) else {},
                failed_branch_record if isinstance(failed_branch_record, Mapping) else {},
            ):
                if not isinstance(source, Mapping):
                    continue
                for key in _CLOSURE_REPAIR_PAYLOAD_KEYS:
                    value = source.get(key)
                    if (
                        key in {'review_criteria', 'semantic_review_criteria'}
                        and isinstance(value, list)
                    ):
                        merged_criteria = self._merge_string_list(
                            check.get(key),
                            value,
                        )
                        if merged_criteria:
                            check[key] = merged_criteria
                    elif value not in (None, '', [], {}) and check.get(key) in (None, '', [], {}):
                        check[key] = value
                if check.get('depends_on') in (None, '', [], {}) and isinstance(source.get('depends_on'), list):
                    depends_on = [
                        str(item or '').strip()
                        for item in source.get('depends_on')
                        if str(item or '').strip()
                    ]
                    if depends_on:
                        check['depends_on'] = depends_on
                for key in ('recovery_context', 'recovery_state', 'attempt'):
                    value = source.get(key)
                    if value not in (None, '', [], {}) and check.get(key) in (None, '', [], {}):
                        check[key] = value
            check = self._apply_decision_contract_to_check(check, decision_contract)
            recovery_context = (
                check.get('recovery_context')
                if isinstance(check.get('recovery_context'), Mapping)
                else {}
            )
            recovery_state = (
                check.get('recovery_state')
                if isinstance(check.get('recovery_state'), Mapping)
                else {}
            )
            attempt_payload = check.get('attempt') if isinstance(check.get('attempt'), Mapping) else {}
            for key in ('blocked_by_dependency_input', 'blocked_by_branch_contract', 'repair_required'):
                value = recovery_context.get(key)
                if not isinstance(value, bool):
                    value = recovery_state.get(key)
                if isinstance(value, bool):
                    check[key] = value
            repair_action, repair_action_reason = closure_repair_feedback._closure_check_recovery_action(check)
            if repair_action:
                check['recovery_action'] = repair_action
                check['repair_action'] = repair_action
            if repair_action_reason:
                check['repair_action_reason'] = repair_action_reason
            failed_instance_id = str(
                attempt_payload.get('instance_id')
                or recovery_state.get('failed_instance_id')
                or ''
            ).strip()
            if failed_instance_id:
                check['failed_instance_id'] = failed_instance_id
            exclude_instance_ids = [
                str(item or '').strip()
                for item in (
                    recovery_context.get('exclude_instance_ids')
                    if isinstance(recovery_context.get('exclude_instance_ids'), list)
                    else recovery_state.get('exclude_instance_ids')
                    if isinstance(recovery_state.get('exclude_instance_ids'), list)
                    else []
                )
                if str(item or '').strip()
            ]
            if exclude_instance_ids:
                check['exclude_instance_ids'] = exclude_instance_ids
            if content_policy:
                requirements = [item for item in accepted_content if isinstance(item, Mapping)
                                and item.get('branch_id') == branch_id]
                request_contract = raw_source.get('artifact_request') or {}
                governed_branch = bool(requirements or request_contract.get('saved_file_producer')
                                       or saved_file_dependency_contract(raw_source))
                if governed_branch:
                    check['content_requirement_policy'] = 'named_saved_text_v1'
                    if content_reference_policy:
                        check['content_review_reference_policy'] = content_reference_policy
                    check['content_requirements'] = requirements
                    check['content_coverage_status'] = 'unverified'
                    check['completion_basis'] = 'technical_evidence_only' if check.get('status') == 'fulfilled' else 'technical_evidence_unresolved'
                    if check.get('status') in {'waived', 'superseded'}:
                        check['content_coverage_status'] = 'authorized_disposition'
                        check['completion_basis'] = 'existing_authorized_disposition'
                    elif (not content_metadata_valid or len(requirements) != 1
                          or requirements[0].get('phase_id') != phase_id
                          or request_contract.get('content_requirement_policy') != 'named_saved_text_v1'
                          or request_contract.get('content_requirements') != requirements):
                        check.update(status='blocked', reason='content_requirement_accounting_missing_or_invalid',
                                     repair_action=RECOVERY_ACTION_MANUAL_REVIEW,
                                     recovery_action=RECOVERY_ACTION_MANUAL_REVIEW)
                    else:
                        check['review_criteria'] = self._merge_string_list(
                            check.get('review_criteria'), [item['criterion'] for item in requirements])
            check = self._apply_review_criteria_to_check(check)
            if (phase_id == current_phase_id
                    and any(p.get('phase_id') == phase_id
                            and p.get('role') == 'saved_artifact_state_explanation'
                            for p in phases if isinstance(p, Mapping))
                    and status not in {'waived', 'superseded', 'cancelled'}):
                request_info = request_payload if isinstance(request_payload, dict) else {}
                sanitize = self.hooks.get('sanitize_selected_reference_artifacts')
                references = request_info.get('reference_artifacts') or request_info.get('selected_reference_artifact') or []
                references = sanitize(references) if callable(sanitize) else []
                check['saved_artifact_state'] = self.saved_artifact_readback._selected_artifact_state_projection(references)
                check = self.saved_artifact_readback._reject_saved_artifact_transcript_echo(
                    check, output_text, prompt=semantic_review_prompt,
                )
            check = self.semantic_closure_review._apply_branch_semantic_verdict_to_check(
                check,
                artifact_payload=artifact_payload,
                prompt=semantic_review_prompt,
                output_text=output_text,
            )
            repair_action, repair_action_reason = closure_repair_feedback._closure_check_recovery_action(check)
            if repair_action and check.get('repair_action') in (None, '', [], {}):
                check['recovery_action'] = repair_action
                check['repair_action'] = repair_action
            if repair_action_reason and check.get('repair_action_reason') in (None, '', [], {}):
                check['repair_action_reason'] = repair_action_reason
            checks.append({key: value for key, value in check.items() if value not in (None, '', [], {})})

        intent_graph_adequacy = intent_coverage.build_intent_graph_adequacy_review(
            request_payload=request_payload,
            request_phase_graph=request_phase_graph,
        )
        adequacy_checks = (
            intent_graph_adequacy.get('checks')
            if isinstance(intent_graph_adequacy.get('checks'), list)
            else []
        )
        checks.extend(
            dict(item)
            for item in adequacy_checks
            if isinstance(item, Mapping)
        )
        truth_guard = artifact_runtime.get('truth_guard') if isinstance(artifact_runtime, Mapping) else {}
        if isinstance(truth_guard, Mapping):
            truth_guard_status = str(truth_guard.get('status') or '').strip().lower()
            if truth_guard_status in {'annotated', 'rewritten'}:
                checks.append(
                    {
                        'check_kind': 'truth_guard',
                        'status': 'pending',
                        'evidence': 'text_only_artifact_claim_guard',
                        'reason': str(truth_guard.get('reason') or '').strip()
                        or 'artifact/materialization claim was not backed by runtime truth',
                    }
                )
                claimed_capabilities = self._hook('normalize_capability_list')(
                    truth_guard.get('claimed_capabilities')
                )
                # A false model claim is a text-truth defect, not permission to
                # create the claimed media. Only already-promoted obligations
                # can supply materialization/repair authority here.
                promised_capabilities = {
                    normalize_capability(item.get('capability'))
                    for key in ('intent_obligations', 'output_obligations')
                    for item in required_intent_obligations(request_phase_graph.get(key) or [])
                    if str(item.get('status') or '').lower() not in
                    {'waived', 'superseded', 'cancelled', 'canceled', 'rejected'}
                }
                for claimed_capability in claimed_capabilities:
                    if claimed_capability not in promised_capabilities:
                        continue
                    availability = self.runtime_capability_availability(claimed_capability)
                    availability_status = str(availability.get('status') or '').strip().lower()
                    if availability_status == 'available':
                        status = 'pending'
                        evidence = 'runtime_capability_available_but_unmaterialized'
                    elif availability_status == 'unavailable':
                        status = 'blocked'
                        evidence = 'runtime_capability_unavailable'
                    else:
                        status = 'pending'
                        evidence = 'runtime_capability_unverified'
                    capability_check = {
                        'check_kind': 'truth_guard_capability',
                        'capability': claimed_capability,
                        'output_type': intent_coverage.artifact_type_for_capability(claimed_capability),
                        'status': status,
                        'evidence': evidence,
                        'runtime_availability_status': availability_status or None,
                        'available_instance_ids': availability.get('available_instance_ids'),
                        'reason': (
                            'claimed material output did not have matching runtime artifact evidence'
                            if status == 'pending'
                            else availability.get('reason')
                        ),
                    }
                    checks.append(
                        {
                            key: value
                            for key, value in capability_check.items()
                            if value not in (None, '', [], {})
                        }
                    )

        if content_policy and (not content_metadata_valid or any(
                not any(check.get('branch_id') == item.get('branch_id') and check.get('content_requirement_policy')
                        for check in checks)
                for item in accepted_content if isinstance(item, Mapping))):
            checks.append({
                'check_kind': 'content_requirement_accounting', 'status': 'blocked',
                'reason': 'content_requirement_accounting_missing_or_invalid',
                'content_coverage_status': 'unverified',
                'repair_action': RECOVERY_ACTION_MANUAL_REVIEW,
                'recovery_action': RECOVERY_ACTION_MANUAL_REVIEW,
            })
        checks.extend(
            self.semantic_closure_review._branch_semantic_review_checks(
                checks=checks,
                request_payload=request_payload,
                request_phase_graph=request_phase_graph,
                artifact_payload=artifact_payload,
                output_text=output_text,
            )
        )
        checks.extend(
            self._linked_artifact_binding_checks(
                request_payload=request_payload,
                artifact_payload=artifact_payload,
                request_phase_graph=request_phase_graph,
            )
        )
        checks.extend(
            self._html_css_selector_binding_checks(
                artifact_payload=artifact_payload,
            )
        )
        checks.extend(
            self._text_artifact_syntax_sanity_checks(
                artifact_payload=artifact_payload,
            )
        )
        checks.extend(
            self.structured_dependency_review._structured_dependency_join_checks(
                request_payload=request_payload,
                artifact_payload=artifact_payload,
                request_phase_graph=request_phase_graph,
            )
        )
        # A completed synthesis marker cannot certify delivery of separate
        # accepted reports. Check every exact contribution and the rendered text.
        for branch in request_phase_graph.get('downstream_branches') or []:
            if not isinstance(branch, Mapping) or not separate_image_report_contract(branch):
                continue
            results = [r for r in ((artifact_payload or {}).get('late_fill') or {}).get('fill_results', [])
                       if isinstance(r, Mapping) and (r.get('branch_id') == branch.get('branch_id')
                                                     or r.get('phase_id') == branch.get('phase_id'))]
            issue = 'separate_image_reports_terminal_missing_or_ambiguous'
            if len(results) == 1:
                issue = separate_image_report_delivery_issue(branch, results[0], artifact_payload or {},
                    self.semantic_artifact_reader._resolved_semantic_review_artifact_path)
            checks.append({'check_kind': 'structured_dependency_join', 'branch_id': branch.get('branch_id'),
                'phase_id': branch.get('phase_id'), 'capability': CAPABILITY_CHAT, 'output_type': 'text',
                'status': 'blocked' if issue else 'fulfilled',
                'evidence': 'structured_dependency_join_contract_unmet' if issue else 'separate_image_reports_delivered',
                'reason': issue or 'Every accepted source report is delivered exactly once.',
                'structured_output_contract': separate_image_report_contract(branch),
                'depends_on': branch.get('depends_on') or []})

        global_semantic_closure_review = self.semantic_closure_review.build_global_semantic_closure_review(
            output_text=output_text,
            request_payload=request_payload,
            request_phase_graph=request_phase_graph,
            artifact_payload=artifact_payload,
            checks=checks,
            intent_graph_adequacy=intent_graph_adequacy,
            decision_contract=decision_contract,
        )
        checks.extend(self.semantic_closure_review._global_semantic_closure_checks(global_semantic_closure_review))

        normalized_checks: list[dict[str, Any]] = []
        for raw_check in checks:
            check = dict(raw_check)
            repair_action, repair_action_reason = closure_repair_feedback._closure_check_recovery_action(check)
            if repair_action and check.get('repair_action') in (None, '', [], {}):
                check['repair_action'] = repair_action
                check['recovery_action'] = repair_action
            if repair_action_reason and check.get('repair_action_reason') in (None, '', [], {}):
                check['repair_action_reason'] = repair_action_reason
            normalized_checks.append(
                {key: value for key, value in check.items() if value not in (None, '', [], {})}
            )
        checks = normalized_checks
        semantic_review_required_count = sum(
            1 for item in checks if item.get('semantic_review_required') is True
        )
        countable_checks = [
            item for item in checks
            if str(item.get('check_kind') or '').strip() not in {'intent_attention_review'}
        ]

        counts = {
            'fulfilled': sum(1 for item in countable_checks if item.get('status') == 'fulfilled'),
            'pending': sum(1 for item in countable_checks if item.get('status') in {'pending', 'planned', 'active'}),
            'deferred': sum(1 for item in countable_checks if item.get('status') == 'deferred'),
            'blocked': sum(1 for item in countable_checks if item.get('status') == 'blocked'),
            'superseded': sum(1 for item in countable_checks if item.get('status') == 'superseded'),
            'waived': sum(1 for item in countable_checks if item.get('status') == 'waived'),
        }
        open_check_branch_ids = {
            str(item.get('branch_id') or item.get('phase_id') or '').strip()
            for item in checks
            if item.get('status') in {'pending', 'planned', 'active', 'deferred'}
            and str(item.get('branch_id') or item.get('phase_id') or '').strip()
        }
        if checks:
            effective_pending_branches = [
                item
                for item in pending_branches
                if not isinstance(item, Mapping)
                or str(item.get('branch_id') or item.get('phase_id') or '').strip() in open_check_branch_ids
            ]
        else:
            effective_pending_branches = pending_branches
        active_late_fill = late_fill_status in _ACTIVE_LATE_FILL_STATUSES and (
            not checks or counts['pending'] or counts['deferred'] or bool(effective_pending_branches)
        )

        if counts['blocked']:
            review_status = 'blocked'
            reason = 'one or more graph obligations are blocked by runtime truth'
        elif intent_graph_adequacy.get('status') == 'pending':
            review_status = 'pending'
            reason = 'graph/IR does not fully cover current user intent'
        elif counts['pending'] or counts['deferred'] or effective_pending_branches or active_late_fill:
            review_status = 'pending'
            reason = 'one or more graph obligations remain open inside the same intent'
        elif checks:
            review_status = 'fulfilled'
            reason = 'all checked graph obligations are fulfilled, waived, or superseded by runtime truth'
        else:
            review_status = 'not_applicable'
            reason = 'request phase graph has no output obligations or phase records'

        surface_state = self._closure_surface_state(
            review_status=review_status,
            reason=reason,
            counts=counts,
            checks=checks,
            decision_contract=decision_contract,
            late_fill_status=late_fill_status,
            pending_branches=effective_pending_branches,
            semantic_review_required_count=semantic_review_required_count,
        )
        continuation_required = review_status in {'pending', 'blocked'}
        payload.update(
            {
                'status': review_status,
                'reason': reason,
                'graph_mode': str(request_phase_graph.get('mode') or '').strip() or None,
                'current_phase_id': current_phase_id or None,
                'continuation_required': continuation_required,
                'late_fill_status': late_fill_status or None,
                'pending_branch_count': len(effective_pending_branches),
                'counts': counts,
                'checks': checks,
                'semantic_review_required_count': semantic_review_required_count,
                'semantic_review_status': 'required_advisory' if semantic_review_required_count else None,
                'surface_state': surface_state,
            }
        )
        if content_policy:
            covered = sum(len(check.get('content_requirements') or []) for check in checks
                          if check.get('content_coverage_status') in {'accepted_review', 'authorized_disposition'})
            reviewed = sum(len(check.get('content_requirements') or []) for check in checks
                           if check.get('content_coverage_status') == 'accepted_review')
            summary = {
                'content_requirement_policy': 'named_saved_text_v1',
                'content_requirement_count': 2,
                'unresolved_content_requirement_count': max(0, 2 - covered) if content_metadata_valid else 2,
                'content_coverage_status': 'covered' if covered == 2 and content_metadata_valid else 'unverified',
                'completion_basis': (
                    ('bound_semantic_review' if reviewed == 2 else
                     'bound_review_and_authorized_disposition' if reviewed else 'existing_authorized_disposition')
                    if covered == 2 and content_metadata_valid else 'content_coverage_unresolved'),
                'correctness_basis': ('not_established_by_disposition' if covered == 2 and not reviewed
                                      else 'reviewer_soundness_assumption'),
            }
            payload.update(summary)
            payload['surface_state'].update(summary)
        if decision_contract_review:
            payload['decision_contract_review'] = decision_contract_review
        if global_semantic_closure_review:
            payload['global_semantic_closure_review'] = global_semantic_closure_review
        inference_repair_feedback = closure_repair_feedback.build_inference_repair_feedback(
            review_status=review_status,
            reason=reason,
            checks=checks,
            request_phase_graph=request_phase_graph,
        )
        if inference_repair_feedback:
            payload['inference_repair_feedback'] = inference_repair_feedback
        if intent_graph_adequacy.get('status') != 'not_applicable':
            payload['intent_graph_adequacy'] = intent_graph_adequacy
        if output_obligations:
            payload['contract_source'] = 'request_ir.output_obligations'
            payload['obligation_count'] = len(output_obligations)
        if continuation_required and isinstance(artifact_gap, Mapping) and artifact_gap:
            payload['closure_gap_code'] = str(artifact_gap.get('code') or '').strip() or None
            payload['closure_gap_trigger'] = str(artifact_gap.get('trigger') or '').strip() or None
        if effective_pending_branches:
            payload['pending_branches'] = [
                {
                    key: item.get(key)
                    for key in ('branch_id', 'phase_id', 'capability', 'output_type')
                    if item.get(key) not in (None, '', [], {})
                }
                for item in effective_pending_branches
                if isinstance(item, Mapping)
            ]
        return {
            key: value
            for key, value in payload.items()
            if value not in (None, '', [], {})
        }

    def build_pre_freeze_closure_review_gap(
        self,
        output_text: str,
        *,
        route_payload: Optional[dict[str, Any]] = None,
        request_payload: Optional[dict[str, Any]] = None,
        artifact_payload: Optional[dict[str, Any]] = None,
        artifact_gap: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        normalize_capability_list = self._hook('normalize_capability_list')

        artifact_info = artifact_payload if isinstance(artifact_payload, dict) else {}
        late_fill = artifact_info.get('late_fill') if isinstance(artifact_info.get('late_fill'), Mapping) else {}
        late_fill_status = str(late_fill.get('status') or '').strip().lower()
        if late_fill_status in _ACTIVE_LATE_FILL_STATUSES:
            return None
        route_runtime = (
            route_payload.get('route_runtime')
            if isinstance(route_payload, Mapping) and isinstance(route_payload.get('route_runtime'), Mapping)
            else {}
        )
        execution_planner = (
            route_runtime.get('execution_planner')
            if isinstance(route_runtime.get('execution_planner'), Mapping)
            else {}
        )
        planner_deferred_explicit = bool(
            execution_planner.get('deferred_capability')
            or execution_planner.get('deferred_capabilities')
            or execution_planner.get('deferred_branches')
        )

        pending_branches = self._extract_pending_deferred_branches(
            route_payload=route_payload,
            artifact_payload=artifact_payload,
        )
        pending_capabilities = normalize_capability_list(
            [item.get('capability') for item in pending_branches if isinstance(item, Mapping)]
        )
        completed_capabilities = normalize_capability_list(late_fill.get('completed_capabilities'))

        base_gap = dict(artifact_gap) if isinstance(artifact_gap, dict) else self.build_artifact_completion_gap_spec(
            output_text,
            route_payload=route_payload,
            request_payload=request_payload,
            artifact_payload=artifact_payload,
        )
        if isinstance(base_gap, dict):
            base_gap = dict(base_gap)

        if pending_branches:
            expected_branch = dict(pending_branches[0])
            expected_capability = normalize_capability(
                (base_gap or {}).get('expected_capability') or expected_branch.get('capability')
            )
            if not expected_capability:
                return None
            payload = dict(base_gap or {})
            preserve_base_gap = str(payload.get('code') or '').strip() == 'late_artifact_fill'
            planner_gap = self.build_planner_deferred_follow_up_gap_spec(
                output_text,
                route_payload=route_payload,
                artifact_payload=artifact_payload,
            )
            if isinstance(planner_gap, dict) and planner_gap:
                for key, value in planner_gap.items():
                    if preserve_base_gap and key in {'code', 'trigger'}:
                        continue
                    if preserve_base_gap and payload.get(key) not in (None, '', [], {}):
                        continue
                    payload[key] = value
            payload['expected_capability'] = expected_capability
            payload['active_capability'] = expected_capability
            payload['missing_artifact_type'] = (
                str(payload.get('missing_artifact_type') or '').strip()
                or str(intent_coverage.artifact_type_for_capability(expected_capability) or '').strip()
                or None
            )
            if (
                len(pending_branches) == 1
                and payload['missing_artifact_type']
                and self.response_payload_has_artifact_type(
                    artifact_payload,
                    payload['missing_artifact_type'],
                )
            ):
                return None
            payload['expected_branch_id'] = (
                str(payload.get('expected_branch_id') or '').strip()
                or str(expected_branch.get('branch_id') or expected_branch.get('phase_id') or '').strip()
                or None
            )
            payload['expected_phase_id'] = (
                str(payload.get('expected_phase_id') or '').strip()
                or str(expected_branch.get('phase_id') or expected_branch.get('branch_id') or '').strip()
                or None
            )
            effective_pending_branches = (
                payload.get('pending_branches')
                if isinstance(payload.get('pending_branches'), list)
                else pending_branches
            )
            payload['pending_branches'] = effective_pending_branches
            payload['pending_capabilities'] = normalize_capability_list(
                [item.get('capability') for item in effective_pending_branches if isinstance(item, Mapping)]
            ) or pending_capabilities
            if completed_capabilities:
                payload['completed_capabilities'] = completed_capabilities
            if not planner_deferred_explicit:
                payload['code'] = 'closure_review_fill'
                payload['trigger'] = 'pre_freeze_closure_review'
            elif not str(payload.get('code') or '').strip():
                payload['code'] = 'closure_review_fill'
            if not str(payload.get('trigger') or '').strip():
                payload['trigger'] = 'pre_freeze_closure_review'
            semantic_payload = self.phase_preparation.semantic_payload_for_capability(
                artifact_payload,
                capability=expected_capability,
            )
            for key, value in semantic_payload.items():
                if payload.get(key) in (None, '', [], {}):
                    payload[key] = value
            if (
                expected_capability == CAPABILITY_IMAGE_GENERATION
                and not isinstance(payload.get('batch_prompts'), list)
            ):
                route_runtime_for_count = (
                    ((route_payload or {}).get('route_runtime') or {})
                    if isinstance(((route_payload or {}).get('route_runtime') or {}), Mapping)
                    else {}
                )
                artifact_runtime_for_count = (
                    ((artifact_payload or {}).get('runtime') or {})
                    if isinstance(((artifact_payload or {}).get('runtime') or {}), Mapping)
                    else {}
                )
                request_phase_graph = (
                    artifact_runtime_for_count.get('request_phase_graph')
                    if isinstance(artifact_runtime_for_count.get('request_phase_graph'), Mapping)
                    else (
                        route_runtime_for_count.get('request_phase_graph')
                        if isinstance(route_runtime_for_count.get('request_phase_graph'), Mapping)
                        else {}
                    )
                )
                expected_count = 0
                invalid_expected_count = False
                if (
                    isinstance(request_phase_graph, Mapping)
                    and isinstance(request_phase_graph.get('prompt_intent'), Mapping)
                ):
                    prompt_intent = request_phase_graph.get('prompt_intent') or {}
                    raw_expected_count = prompt_intent.get(
                        'requested_visual_output_count'
                    )
                    expected_count, invalid_expected_count = (
                        _parse_image_batch_expected_count(
                            raw_expected_count,
                            present='requested_visual_output_count' in prompt_intent,
                        )
                    )
                    # Older underplanned graphs used numeric zero to mean
                    # "unknown", before counted visual obligations became an
                    # explicit contract.  Preserve that narrow recovery path:
                    # strong numbered image prompts may still expand the one
                    # planned branch.  A counted graph (or any other malformed
                    # count carrier) remains fail-closed.
                    if (
                        invalid_expected_count
                        and raw_expected_count in (0, '0')
                        and not bool(
                            prompt_intent.get('counted_visual_output_obligation')
                        )
                    ):
                        invalid_expected_count = False
                extraction_expected_count = expected_count
                if expected_count <= 0:
                    expected_count = len(pending_branches)
                    # A single pending image branch can be an underplanned
                    # graph.  Let the strong numbered-prompt parser discover
                    # the complete cohort so closure review can expand it.
                    # With multiple planned branches, retain their count as
                    # the extraction bound to avoid treating unrelated
                    # numbered prose as additional image work.
                    extraction_expected_count = (
                        0 if len(pending_branches) == 1 else expected_count
                    )
                batch_prompts = image_prompt_preparation.extract_batch_image_prompts(
                    output_text,
                    expected_count=extraction_expected_count,
                    allow_plain_alpha_sequence=False,
                )
                if len(batch_prompts) > 1 and not invalid_expected_count:
                    payload['batch_prompts'] = batch_prompts
                    payload['batch_prompt_expected_count'] = (
                        expected_count if expected_count >= 2 else len(batch_prompts)
                    )
                    expanded_branches, expansion = (
                        self._expand_image_pending_branches_from_batch_prompts(
                            payload.get('pending_branches') or pending_branches,
                            batch_prompts,
                        )
                    )
                    if expansion:
                        payload['pending_branches'] = expanded_branches
                        payload['pending_capabilities'] = normalize_capability_list(
                            [
                                item.get('capability')
                                for item in expanded_branches
                                if isinstance(item, Mapping)
                            ]
                        )
                        payload['prepared_image_prompt_branch_expansion'] = expansion
                elif invalid_expected_count:
                    for key in (
                        'artifact_prompt',
                        'artifact_prompt_source',
                        'batch_prompts',
                        'batch_prompts_source',
                        'batch_prompt_source_phase_id',
                        'batch_prompt_expected_count',
                    ):
                        payload.pop(key, None)
                    payload['branch_contract_error'] = 'incomplete_image_prompt_batch'
                    payload['candidate_extraction_issue'] = 'invalid_image_prompt_batch_count'
                    payload['batch_prompt_expected_count_invalid'] = True
                    payload['batch_prompt_actual_count'] = len(batch_prompts)
                    payload['materialization_blocked'] = True
                    payload['repair_action'] = RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT
                    payload['counted_batch_prompt_carriers_blocked'] = True
            return payload

        if isinstance(base_gap, dict):
            if self.artifact_gap_is_already_fulfilled(base_gap, artifact_payload):
                return None
            payload = dict(base_gap)
            if not str(payload.get('trigger') or '').strip():
                payload['trigger'] = 'pre_freeze_closure_review'
            return payload
        return None

    @observe_state('late_fill.state_build', 'prior_late_fill_and_branch_results', 'late_fill_state', labels=('NEW_REPRESENTATION',))
    def build_late_fill_state(
        self,
        artifact_gap: dict[str, Any],
        *,
        status: str,
        prior_state: Optional[dict[str, Any]] = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        normalize_capability_list = self._hook('normalize_capability_list')
        normalize_late_fill_branches = self._hook('normalize_late_fill_branches')
        response_registry_now_iso = self._hook('response_registry_now_iso')

        previous = prior_state if isinstance(prior_state, dict) else {}
        now_iso = response_registry_now_iso()
        status_token = str(status or '').strip().lower()
        terminal_without_pending_surface = status_token in {
            'completed',
            'skipped',
            'cancelled',
        }
        terminal_late_fill_status = status_token in {
            'completed',
            'skipped',
            'cancelled',
            'failed',
            'partial_failed',
            'partial_cancelled',
        }
        payload = {
            'status': str(status or '').strip() or 'pending',
            'code': str(artifact_gap.get('code') or 'late_artifact_fill'),
            'trigger': str(artifact_gap.get('trigger') or 'chat_text_only_completion'),
            'expected_capability': normalize_capability(artifact_gap.get('expected_capability')),
            'active_capability': normalize_capability(
                artifact_gap.get('active_capability') or artifact_gap.get('expected_capability')
            ),
            'missing_artifact_type': str(artifact_gap.get('missing_artifact_type') or '').strip() or None,
            'late_fill_supported': True,
            'created_at': str(previous.get('created_at') or now_iso),
            'updated_at': now_iso,
        }
        if payload['status'] == 'running':
            payload['started_at'] = str(previous.get('started_at') or now_iso)
        if payload['status'] in {'completed', 'partial_failed', 'partial_cancelled'}:
            payload['started_at'] = str(previous.get('started_at') or now_iso)
            payload['completed_at'] = now_iso
        if payload['status'] == 'cancelled':
            payload['started_at'] = str(previous.get('started_at') or now_iso)
            payload['cancelled_at'] = now_iso
        if payload['status'] in {'failed', 'partial_failed'}:
            payload['started_at'] = str(previous.get('started_at') or now_iso)
            payload['failed_at'] = now_iso
        for key in ('content_payload', 'stage_direction', 'phase_summary', 'content_payload_source'):
            value = artifact_gap.get(key)
            if value in (None, '', [], {}):
                value = previous.get(key)
            if value not in (None, '', [], {}):
                payload[key] = value
        for key in ('artifact_prompt', 'artifact_prompt_source'):
            value = artifact_gap.get(key)
            if value in (None, '', [], {}):
                value = previous.get(key)
            if value not in (None, '', [], {}):
                payload[key] = value
        for key in ('batch_prompts_source', 'batch_prompt_source_phase_id'):
            value = artifact_gap.get(key)
            if value in (None, '', [], {}):
                value = previous.get(key)
            if value not in (None, '', [], {}):
                payload[key] = str(value).strip()
        for key in ('expected_branch_id', 'expected_phase_id'):
            value = artifact_gap.get(key)
            if value in (None, '', [], {}):
                value = previous.get(key)
            if value not in (None, '', [], {}):
                payload[key] = str(value).strip() or None
        for key in (
            'branch_contract_error',
            'candidate_extraction_issue',
            'materialization_blocked',
            'counted_batch_prompt_carriers_blocked',
            'batch_prompt_expected_count_invalid',
        ):
            value = artifact_gap.get(key)
            if value in (None, '', [], {}):
                value = previous.get(key)
            if value not in (None, '', [], {}):
                payload[key] = value
        for key in (
            'inference_repair_feedback',
            'repair_scope',
            'repair_mode',
            'repair_action',
            'repair_actions',
            'repair_action_reason',
            'repair_loop',
            'repair_rebuild_contracts',
            'reconsideration_rebuild',
            'block_resolution_reflex',
            'reconsideration_reflex',
            'active_reconsideration_review',
            'active_reconsideration_decisions',
            'semantic_quality_review',
            'semantic_quality_contracts',
            'aspiration_review',
            'aspiration_frames',
            'commitment_review',
            'commitment_frames',
            'semantic_decision_review',
            'semantic_decision_proposals',
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
            'controlled_attention_review',
            'controlled_attention_frames',
            'recursive_cycle_review',
            'surface_state',
            'branch_controls',
            'execution_gate_status',
            'repair_code',
            'repair_trigger',
            'preserve_request_id',
            'pending_branch_scope',
            'authoritative_pending_branches',
        ):
            value = artifact_gap.get(key)
            if value in (None, '', [], {}):
                value = previous.get(key)
            if key == 'surface_state' and terminal_without_pending_surface:
                value = None
            if value not in (None, '', [], {}):
                payload[key] = value
        # Running/checkpoint state belongs to the same admitted execution. Losing
        # its envelope makes the publication guard reject the worker's own state.
        # New execution authority still comes from the admitting owner; this
        # constructor only carries the supplied record, like successor state.
        for key in ('successor_reopen_execution', 'terminal_closure_repair_reopen',
                    'partial_rebase_execution'):
            value = artifact_gap.get(key)
            if value in (None, '', [], {}):
                value = previous.get(key)
            if value not in (None, '', [], {}):
                payload[key] = copy.deepcopy(value)
        batch_prompts = artifact_gap.get('batch_prompts')
        if not isinstance(batch_prompts, list):
            batch_prompts = previous.get('batch_prompts') if isinstance(previous.get('batch_prompts'), list) else None
        if isinstance(batch_prompts, list):
            normalized_batch_prompts = [
                str(item).strip()
                for item in batch_prompts
            ]
            if any(normalized_batch_prompts):
                payload['batch_prompts'] = normalized_batch_prompts
        raw_batch_prompt_expected_count = artifact_gap.get('batch_prompt_expected_count')
        if raw_batch_prompt_expected_count in (None, '', [], {}):
            raw_batch_prompt_expected_count = previous.get('batch_prompt_expected_count')
        has_batch_prompt_expected_count = raw_batch_prompt_expected_count not in (
            None,
            '',
            [],
            {},
        )
        batch_prompt_expected_count, invalid_batch_prompt_count = (
            _parse_image_batch_expected_count(
                raw_batch_prompt_expected_count,
                present=has_batch_prompt_expected_count,
            )
        )
        invalid_batch_prompt_count = bool(
            invalid_batch_prompt_count
            or payload.get('batch_prompt_expected_count_invalid') is True
        )
        if invalid_batch_prompt_count:
            # Preserve malformed count metadata as explicit contract truth;
            # do not normalize it to zero and let a later state transition
            # accidentally reopen a shared or partial image prompt carrier.
            if has_batch_prompt_expected_count:
                payload['batch_prompt_expected_count'] = raw_batch_prompt_expected_count
            payload['batch_prompt_expected_count_invalid'] = True
            payload['batch_prompt_actual_count'] = len(
                [
                    item
                    for item in (payload.get('batch_prompts') or [])
                    if str(item or '').strip()
                ]
            )
            payload['branch_contract_error'] = 'incomplete_image_prompt_batch'
            payload['candidate_extraction_issue'] = 'invalid_image_prompt_batch_count'
            payload['materialization_blocked'] = True
            payload['repair_action'] = RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT
            payload['counted_batch_prompt_carriers_blocked'] = True
        elif 2 <= batch_prompt_expected_count <= 26:
            payload['batch_prompt_expected_count'] = batch_prompt_expected_count
        for key in ('pending_branches', 'completed_branches', 'failed_branches', 'cancelled_branches', 'active_branches'):
            value = artifact_gap.get(key)
            if not isinstance(value, list):
                value = previous.get(key) if isinstance(previous.get(key), list) else None
            if isinstance(value, list):
                normalized_branches = normalize_late_fill_branches(value)
                if normalized_branches or key in previous or key in artifact_gap:
                    payload[key] = normalized_branches
        for key in ('pending_capabilities', 'completed_capabilities', 'failed_capabilities', 'cancelled_capabilities'):
            value = artifact_gap.get(key)
            if not isinstance(value, list):
                value = previous.get(key) if isinstance(previous.get(key), list) else None
            if isinstance(value, list):
                payload[key] = normalize_capability_list(value)
        # A state transition carries accepted evidence as well as completion
        # markers. Retry/control callers must not have to reconstruct saved
        # sibling results from paths or public projections.
        if isinstance(previous.get('fill_results'), list):
            payload['fill_results'] = copy.deepcopy(previous['fill_results'])
        if extra:
            payload.update(
                {
                    key: value
                    for key, value in extra.items()
                    if value not in (None, '', [], {})
                    and not (key == 'surface_state' and terminal_without_pending_surface)
                }
            )
            if terminal_without_pending_surface:
                payload.pop('surface_state', None)
            for key in ('pending_capabilities', 'completed_capabilities', 'failed_capabilities', 'cancelled_capabilities'):
                if key in extra and isinstance(extra.get(key), list):
                    payload[key] = normalize_capability_list(extra.get(key))
            for key in ('pending_branches', 'completed_branches', 'failed_branches', 'cancelled_branches', 'active_branches'):
                if key in extra and isinstance(extra.get(key), list):
                    payload[key] = normalize_late_fill_branches(extra.get(key))
            if isinstance(extra.get('fill_results'), list):
                payload['fill_results'] = copy.deepcopy(extra['fill_results'])
            for key in ('expected_branch_id', 'expected_phase_id'):
                if key in extra and extra.get(key) not in (None, '', [], {}):
                    payload[key] = str(extra.get(key)).strip() or None
            if 'active_capability' in extra:
                payload['active_capability'] = normalize_capability(extra.get('active_capability'))
        for key, terminal_status in (
            ('completed_branches', 'fulfilled'),
            ('failed_branches', 'failed'),
            ('cancelled_branches', None),
        ):
            branches = payload.get(key)
            if not isinstance(branches, list):
                continue
            normalized: list[dict[str, Any]] = []
            for branch in branches:
                if not isinstance(branch, Mapping):
                    continue
                branch_payload = dict(branch)
                if terminal_status:
                    branch_payload['status'] = terminal_status
                elif not str(branch_payload.get('status') or '').strip():
                    branch_payload['status'] = 'cancelled'
                normalized.append(branch_payload)
            payload[key] = normalized
        if terminal_late_fill_status:
            payload['pending_branches'] = []
            payload['active_branches'] = []
            payload['pending_capabilities'] = []
            payload['active_capabilities'] = []
        successor_execution = (
            dict(payload.get('successor_reopen_execution'))
            if isinstance(payload.get('successor_reopen_execution'), Mapping)
            else {}
        )
        if successor_execution:
            execution_status = {
                'pending': 'queued',
                'queued': 'queued',
                'scheduled': 'queued',
                'running': 'running',
                'completed': 'completed',
                'skipped': 'completed',
                'partial_failed': 'failed',
                'failed': 'failed',
                'partial_cancelled': 'cancelled',
                'cancelled': 'cancelled',
            }.get(status_token, str(successor_execution.get('status') or 'queued').strip())
            successor_execution['status'] = execution_status
            successor_execution['late_fill_status'] = status_token or payload.get('status')
            successor_execution['updated_at'] = now_iso
            payload['successor_reopen_execution'] = successor_execution
        return payload

    def extract_semantic_materializer_prompt(
        self,
        payload: Any,
        *,
        capability: Optional[str],
    ) -> Optional[str]:
        if not isinstance(payload, dict):
            return None
        normalized_capability = normalize_capability(capability)
        if normalized_capability == CAPABILITY_IMAGE_GENERATION:
            prompt = str(payload.get('artifact_prompt') or '').strip()
            return prompt or None
        if normalized_capability == CAPABILITY_TEXT_TO_SPEECH:
            prompt = str(payload.get('content_payload') or '').strip()
            return prompt or None
        return None

    def selected_reference_matches_capability(
        self,
        selected_reference_artifact: Optional[dict[str, Any]],
        capability: Optional[str],
        *,
        instance: Optional[dict[str, Any]] = None,
    ) -> bool:
        return self.selected_reference_context.selected_reference_matches_capability(selected_reference_artifact, capability, instance=instance)

    def select_matching_selected_reference_artifact(
        self,
        selected_reference_artifacts: Any,
        capability: Optional[str],
        *,
        instance: Optional[dict[str, Any]] = None,
        artifact_ref: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        return self.selected_reference_context.select_matching_selected_reference_artifact(selected_reference_artifacts, capability, instance=instance, artifact_ref=artifact_ref)

    def should_attach_selected_reference_file_context(
        self,
        *,
        prompt: Any,
        capability: Optional[str],
        selected_reference_artifact: Optional[dict[str, Any]],
    ) -> bool:
        return self.selected_reference_context.should_attach_selected_reference_file_context(prompt=prompt, capability=capability, selected_reference_artifact=selected_reference_artifact)

    def build_selected_reference_prompt_prefix(
        self,
        selected_reference_artifacts: Any,
        capability: Optional[str],
    ) -> str:
        return self.selected_reference_context.build_selected_reference_prompt_prefix(selected_reference_artifacts, capability)

    def apply_selected_reference_prompt_prefix(
        self,
        prompt: Any,
        selected_reference_artifacts: Any,
        capability: Optional[str],
    ) -> str:
        return self.selected_reference_context.apply_selected_reference_prompt_prefix(prompt, selected_reference_artifacts, capability)

    _saved_audio_digest_equalities = staticmethod(SavedArtifactReadback._saved_audio_digest_equalities)

    _artifact_readback_projection = staticmethod(SavedArtifactReadback._artifact_readback_projection)

    def _selected_artifact_state_projection(self, references: list[dict[str, Any]]) -> dict[str, Any]:
        return self.saved_artifact_readback._selected_artifact_state_projection(references)

    _reject_saved_artifact_transcript_echo = staticmethod(SavedArtifactReadback._reject_saved_artifact_transcript_echo)

    def _selected_artifact_state_readback(self, references: list[dict[str, Any]]) -> str:
        return self.saved_artifact_readback._selected_artifact_state_readback(references)

    def inject_selected_reference_into_chat_messages(
        self,
        messages: list[dict[str, Any]],
        selected_reference_artifact: Any,
    ) -> list[dict[str, Any]]:
        return self.selected_reference_context.inject_selected_reference_into_chat_messages(messages, selected_reference_artifact)

    def resolve_prepare_phase_contract(
        self,
        *,
        route_payload: Optional[dict[str, Any]] = None,
        request_payload: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        return self.phase_preparation.resolve_prepare_phase_contract(route_payload=route_payload, request_payload=request_payload)

    def plain_alpha_image_prompt_prepare_authority(
        self,
        phase_graph: Any,
        *,
        expected_count: int,
    ) -> dict[str, Any]:
        return self.phase_preparation.plain_alpha_image_prompt_prepare_authority(phase_graph, expected_count=expected_count)

    def _format_prepare_phase_capability_label(self, capability: str) -> str:
        return self.phase_preparation._format_prepare_phase_capability_label(capability)

    def numbered_image_prepare_authority(
        self,
        phase_graph: Any,
    ) -> dict[str, Any]:
        return self.phase_preparation.numbered_image_prepare_authority(phase_graph)

    def numbered_audio_prepare_authority(
        self,
        phase_graph: Any,
    ) -> dict[str, Any]:
        return self.phase_preparation.numbered_audio_prepare_authority(phase_graph)

    def build_prepare_phase_system_message(
        self,
        prepare_contract: Optional[dict[str, Any]],
    ) -> Optional[dict[str, str]]:
        return self.phase_preparation.build_prepare_phase_system_message(prepare_contract)

    def build_external_prepare_phase_bounded_task(
        self,
        *,
        prepare_contract: Optional[dict[str, Any]] = None,
        route_payload: Optional[dict[str, Any]] = None,
        request_payload: Optional[dict[str, Any]] = None,
    ) -> str:
        return self.phase_preparation.build_external_prepare_phase_bounded_task(prepare_contract=prepare_contract, route_payload=route_payload, request_payload=request_payload)

    def inject_prepare_phase_contract_into_chat_messages(
        self,
        messages: list[dict[str, Any]],
        *,
        route_payload: Optional[dict[str, Any]] = None,
        request_payload: Optional[dict[str, Any]] = None,
        backend: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        return self.phase_preparation.inject_prepare_phase_contract_into_chat_messages(messages, route_payload=route_payload, request_payload=request_payload, backend=backend)

    _scope_saved_artifact_explanation_messages = staticmethod(PhasePreparation._scope_saved_artifact_explanation_messages)

    def build_response_semantic_phase_payload(
        self,
        *,
        output_text: str,
        route_payload: Optional[dict[str, Any]] = None,
        request_payload: Optional[dict[str, Any]] = None,
        source_payload: Optional[dict[str, Any]] = None,
        capability: Optional[str] = None,
    ) -> dict[str, Any]:
        return self.phase_preparation.build_response_semantic_phase_payload(output_text=output_text, route_payload=route_payload, request_payload=request_payload, source_payload=source_payload, capability=capability)

    def attach_response_semantic_phase_payload(
        self,
        payload: Optional[dict[str, Any]],
        *,
        output_text: str,
        route_payload: Optional[dict[str, Any]] = None,
        request_payload: Optional[dict[str, Any]] = None,
        capability: Optional[str] = None,
    ) -> dict[str, Any]:
        return self.phase_preparation.attach_response_semantic_phase_payload(payload, output_text=output_text, route_payload=route_payload, request_payload=request_payload, capability=capability)

    def plan_compound_execution_payload(
        self,
        payload: dict[str, Any],
        *,
        route_info: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        plan_compound_execution_hook = self._hook('plan_compound_execution')
        normalize_request_payload = self._hook('normalize_request_payload')
        merge_instances_with_runtime_status = self._hook('merge_instances_with_runtime_status')
        load_running_instances = self._hook('load_running_instances')
        runtime_status_path_getter = self._hook('runtime_status_path_getter')
        planner_timeout_seconds_for_payload = self._hook('planner_timeout_seconds_for_payload')
        extract_inference_route_messages = self._hook('extract_inference_route_messages')
        extract_responses_current_turn_prompt = self._hook('extract_responses_current_turn_prompt')
        extract_responses_prompt = self._hook('extract_responses_prompt')
        execute_chat_backend_request = self._hook('execute_chat_backend_request')

        base_payload = normalize_request_payload(payload)
        current_turn_prompt = (
            extract_responses_current_turn_prompt(base_payload)
            or str(base_payload.get('_current_turn_prompt') or '').strip()
            or str(base_payload.get('_prompt_hint') or '').strip()
            or extract_responses_prompt(base_payload)
        )
        if current_turn_prompt:
            base_payload['_current_turn_prompt'] = current_turn_prompt
            base_payload['_prompt_hint'] = current_turn_prompt
        try:
            instances = merge_instances_with_runtime_status(
                load_running_instances(),
                path=runtime_status_path_getter(),
                refresh=True,
            )
            route_runtime = (
                route_info.get('route_runtime')
                if isinstance(route_info.get('route_runtime'), dict)
                else {}
            )
            semantic_role_profile = (
                route_runtime.get('semantic_role_profile')
                if isinstance(route_runtime.get('semantic_role_profile'), dict)
                else {}
            )
            planner_timeout_sec = planner_timeout_seconds_for_payload(
                base_payload,
                semantic_role_profile=semantic_role_profile,
            )
            planned_payload, planner_meta = plan_compound_execution_hook(
                base_payload,
                route_info=route_info,
                instances=instances,
                context_messages=extract_inference_route_messages(base_payload),
                execute_chat_request=execute_chat_backend_request,
                planner_timeout_sec=planner_timeout_sec,
                semantic_role_profile=semantic_role_profile,
            )
            return planned_payload, planner_meta
        except Exception as exc:  # noqa: BLE001
            logging.warning('interpretive inference resolver fallback: %s', exc)
            return base_payload, {
                'attempted': True,
                'applied': False,
                'capability': normalize_capability(
                    (route_info or {}).get('capability')
                    or ((route_info or {}).get('instance') or {}).get('capability')
                    or base_payload.get('capability')
                ) or None,
                'reason': 'planner_error',
                'error': str(exc),
            }
