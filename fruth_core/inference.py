"""Shared inference service layer for Fruth capability dispatch."""

from __future__ import annotations

from fruth_core import text_artifacts
from fruth_core.text_artifacts import (
    TEXT_ARTIFACT_EXTENSIONS,
    _JSON_TEXT_ARTIFACT_DIRECT_FILENAME_LIST_PREFIX_RE,
    _JSON_TEXT_ARTIFACT_DIRECT_FILE_RE,
    _JSON_TEXT_ARTIFACT_EXTRA_ACTION_RE,
    _JSON_TEXT_ARTIFACT_FILE_FORMAT_RE,
    _JSON_TEXT_ARTIFACT_FORMAT_ACTION_RE,
    _JSON_TEXT_ARTIFACT_IMPLICIT_MANIFEST_TARGET_RE,
    _JSON_TEXT_ARTIFACT_MANIFEST_ACTION_RE,
    _JSON_TEXT_ARTIFACT_MANIFEST_DELIBERATION_RE,
    _JSON_TEXT_ARTIFACT_MANIFEST_ITEM_RE,
    _JSON_TEXT_ARTIFACT_MANIFEST_SOURCE_CONTEXT_RE,
    _JSON_TEXT_ARTIFACT_MANIFEST_TARGET_RE,
    _JSON_TEXT_ARTIFACT_META_ACTION_PREFIX_RE,
    _JSON_TEXT_ARTIFACT_MULTILINE_QUOTED_SPAN_RE,
    _JSON_TEXT_ARTIFACT_NEGATED_CONTEXT_RE,
    _JSON_TEXT_ARTIFACT_NEGATION_PREFIX_RE,
    _JSON_TEXT_ARTIFACT_NEGATION_SUFFIX_RE,
    _JSON_TEXT_ARTIFACT_NON_OUTPUT_LIST_CONTEXT_RE,
    _JSON_TEXT_ARTIFACT_QUOTED_FILENAME_ACTION_RE,
    _JSON_TEXT_ARTIFACT_QUOTED_FILENAME_RE,
    _JSON_TEXT_ARTIFACT_QUOTED_SPAN_RE,
    _JSON_TEXT_ARTIFACT_RELATIVE_PATH_SUFFIX_RE,
    _JSON_TEXT_ARTIFACT_RESPONSE_FORMAT_RE,
    _JSON_TEXT_ARTIFACT_SITE_COMPONENT_LIST_PREFIX_RE,
    _JsonTextArtifactIntent,
    _RELATIVE_ARTIFACT_CONTENT_THAT_RE,
    _SVG_ARTIFACT_ACTION_RE,
    _SVG_ARTIFACT_TARGET_JOIN_RE,
    _SVG_ARTIFACT_TYPED_NOUN_PATTERN,
    _SVG_ARTIFACT_TYPED_TARGET_RE,
    _TEXT_ARTIFACT_ACTION_CUE_RE,
    _TEXT_ARTIFACT_BARE_GERMAN_PAGE_RE,
    _TEXT_ARTIFACT_BLOCKED_CONTENT_RE,
    _TEXT_ARTIFACT_CARDINALITY_CONSTRAINT_RE,
    _TEXT_ARTIFACT_COMMAND_PROHIBITION_RE,
    _TEXT_ARTIFACT_CONTROL_JSON_KEYS,
    _TEXT_ARTIFACT_COUNT_WORDS,
    _TEXT_ARTIFACT_DEMONSTRATIVE_REFERENCE_RE,
    _TEXT_ARTIFACT_DISTINCT_FORMAT_CUE_RE,
    _TEXT_ARTIFACT_EACH_PART_CUE_RE,
    _TEXT_ARTIFACT_EXTENSION_RE,
    _TEXT_ARTIFACT_FENCED_BLOCK_RE,
    _TEXT_ARTIFACT_FILE_CUE_RE,
    _TEXT_ARTIFACT_FORMAT_NEGATION_RE,
    _TEXT_ARTIFACT_FORMAT_RE,
    _TEXT_ARTIFACT_FORMAT_SCOPE_BOUNDARY_RE,
    _TEXT_ARTIFACT_GENERATED_VISUAL_CONTEXT_RE,
    _TEXT_ARTIFACT_GENERIC_FALLBACK_CUE_RE,
    _TEXT_ARTIFACT_IMPLICIT_WEB_PAGE_RE,
    _TEXT_ARTIFACT_INLINE_SOURCE_RE,
    _TEXT_ARTIFACT_LANGUAGE_EXTENSIONS,
    _TEXT_ARTIFACT_MISSING_RE,
    _TEXT_ARTIFACT_NEGATION_RE,
    _TEXT_ARTIFACT_NON_PAYLOAD_LANGS,
    _TEXT_ARTIFACT_PART_COUNT_RE,
    _TEXT_ARTIFACT_RESERVED_SUFFIX_RE,
    _TEXT_ARTIFACT_RESPONSE_FORMAT_ONLY_EXTENSIONS,
    _TEXT_ARTIFACT_SAME_PROMPT_GENERATED_SOURCE_RE,
    _TEXT_ARTIFACT_SELF_CLAIM_RE,
    _TEXT_ARTIFACT_SELF_CONTAINED_CODE_BUNDLE_RE,
    _TEXT_ARTIFACT_SELF_CONTAINED_SOURCE_RE,
    _TEXT_ARTIFACT_SOURCE_EDIT_ACTION_RE,
    _TEXT_ARTIFACT_SOURCE_EDIT_CLAUSE_RE,
    _TEXT_ARTIFACT_SOURCE_EDIT_CODE_CONTENT_RE,
    _TEXT_ARTIFACT_SOURCE_EDIT_COMMON_CONTENT_RE,
    _TEXT_ARTIFACT_SOURCE_EDIT_COMPETING_TARGET_RE,
    _TEXT_ARTIFACT_SOURCE_EDIT_COMPOUND_CONTENT_RE,
    _TEXT_ARTIFACT_SOURCE_EDIT_CUE_RE,
    _TEXT_ARTIFACT_SOURCE_EDIT_DATA_CONTENT_RE,
    _TEXT_ARTIFACT_SOURCE_EDIT_DIRECT_PRONOUN_RE,
    _TEXT_ARTIFACT_SOURCE_EDIT_EXPLICIT_SOURCE_RE,
    _TEXT_ARTIFACT_SOURCE_EDIT_JSON_TARGET_RE,
    _TEXT_ARTIFACT_SOURCE_EDIT_NEXT_DIRECTIVE_RE,
    _TEXT_ARTIFACT_SOURCE_EDIT_QUALIFIED_JSON_RESPONSE_TARGET_RE,
    _TEXT_ARTIFACT_SOURCE_EDIT_STRONG_CONTENT_RE,
    _TEXT_ARTIFACT_SOURCE_EDIT_WEB_CONTENT_RE,
    _TEXT_ARTIFACT_TAG_ATTR_RE,
    _TEXT_ARTIFACT_TAG_RE,
    _TEXT_ARTIFACT_VALIDATION_ONLY_RE,
    _TEXT_ARTIFACT_WEB_PAGE_NEED_CUE_RE,
    _artifact_request_with_code_block_metadata,
    _artifact_request_with_json_obligation_metadata,
    _artifact_request_with_tag_metadata,
    _code_block_language_matches_extension,
    _json_text_artifact_candidate_state,
    _json_text_artifact_content_payload_is_safe,
    _json_text_artifact_control_wrapper_without_payload,
    _json_text_artifact_filename_has_manifest_authority,
    _json_text_artifact_intent,
    _json_text_artifact_list_separator_only,
    _json_text_artifact_manifest_header_has_output_authority,
    _json_text_artifact_manifest_item_line,
    _json_text_artifact_manifest_sibling_line,
    _json_text_artifact_obligation_content,
    _json_text_artifact_obligation_extension,
    _json_text_artifact_obligation_source_name,
    _json_text_artifact_obligations,
    _json_text_artifact_payloads,
    _json_text_artifact_span_is_inside_quoted_instruction,
    _json_text_artifact_value_has_control_shape,
    _json_text_artifact_wrapper_candidates,
    _looks_like_raw_artifact_payload,
    _mask_json_text_artifact_quotes,
    _normalize_text_artifact_block_language,
    _normalize_text_artifact_extension,
    _parse_text_artifact_tag_attrs,
    _text_artifact_block_extension,
    _text_artifact_block_language_is_payload,
    _text_artifact_count_from_token,
    _text_artifact_each_part_count,
    _text_artifact_filename_has_declaration_authority,
    _text_artifact_filename_match_is_validation_only,
    _text_artifact_format_is_embedded,
    _text_artifact_format_match_has_distinct_artifact_cue,
    _text_artifact_format_match_is_negated,
    _text_artifact_match_scope,
    _text_artifact_negation_match_is_cardinality_constraint,
    _text_artifact_prompt_has_positive_request_outside_negation,
    _text_artifact_prompt_is_negated,
    _text_artifact_selected_source_edit_is_bound,
    _text_artifact_source_content_is_local_target,
    _text_artifact_source_format_is_local_target,
    _text_artifact_source_name_is_local_target,
    _text_artifact_source_strong_content_is_local_target,
    _text_artifact_tag_extension,
    _text_artifact_tag_source_name,
    _typed_text_artifact_payload_is_plausible,
    detect_text_artifact_request,
    detect_text_artifact_requests,
    explicit_svg_artifact_request_spans,
    extract_text_artifact_payload,
    extract_text_artifact_payloads,
    generated_text_blocks_artifact_persistence,
    generated_text_is_artifact_self_claim,
    normalize_text_artifact_extension,
    prompt_has_inline_text_artifact_source,
    text_artifact_request_is_generic,
    text_artifact_request_is_ungrounded_reference,
)

import base64
import hashlib
import json
import logging
import math
import re
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from helpers.model_capabilities import (
    CAPABILITY_IMAGE_GENERATION,
    CAPABILITY_SPEECH_TO_TEXT,
    CAPABILITY_TEXT_TO_SPEECH,
    CAPABILITY_VISION_ANALYSIS,
)
from helpers.ocr_modes import GENERIC_OCR_FALLBACK_PROMPT, resolve_ocr_prompt
from fruth_core.apple_fm_tools import (
    APPLE_FM_IMAGE_TOOL_MODES, AppleFMImageToolError, run_apple_fm_image_tool,
)
from fruth_core.transports import (
    AppleFMTransportError,
    join_pcm_wav_bytes,
    text_artifact_content_is_materializer_instruction_echo,
)
from fruth_services.tts_audio_integrity import (
    TTS_QWEN_SENTENCE_CHUNK_INTEGRITY_PROFILE,
    build_tts_audio_integrity_evidence,
    build_tts_semantic_source,
    tts_audio_has_qwen_generation_limit_exhaustion,
)
from fruth_services.tts_source import extract_legacy_tts_wrapper_text
from fruth_core.image_generation import ImageAdapterError, ImageRequest, select_image_adapter, supports_image_steps, validate_image_steps

# Closed JSON grammar: quoted filenames require ``create/save ... file``;
# field/reference/path/url compounds remain response shapes, not file requests.

QWEN3_CUSTOMVOICE_SPEAKERS = [
    'serena',
    'vivian',
    'uncle_fu',
    'ryan',
    'aiden',
    'ono_anna',
    'sohee',
    'eric',
    'dylan',
]


_TTS_AUTO_LANGUAGE_CODES = {'auto', 'autodetect', 'detect'}
_TTS_LANGUAGE_ALIASES: dict[str, tuple[str, ...]] = {
    'english': ('english', 'en', 'eng'),
    'german': ('german', 'de', 'deu', 'deutsch'),
    'french': ('french', 'fr', 'fra', 'francais', 'français'),
    'spanish': ('spanish', 'es', 'spa', 'espanol', 'español'),
    'italian': ('italian', 'it', 'ita', 'italiano'),
    'portuguese': ('portuguese', 'pt', 'por', 'portugues', 'português'),
    'chinese': ('chinese', 'zh', 'zho', 'mandarin'),
    'japanese': ('japanese', 'ja', 'jpn'),
    'korean': ('korean', 'ko', 'kor'),
    'russian': ('russian', 'ru', 'rus'),
}
_TTS_FALLBACK_LANGUAGE_CODES: dict[str, str] = {
    'english': 'en',
    'german': 'de',
    'french': 'fr',
    'spanish': 'es',
    'italian': 'it',
    'portuguese': 'pt',
    'chinese': 'zh',
    'japanese': 'ja',
    'korean': 'ko',
    'russian': 'ru',
}
_TTS_LANGUAGE_MARKERS: dict[str, tuple[str, ...]] = {
    'english': (
        'the', 'and', 'that', 'with', 'from', 'this', 'was', 'were', 'once', 'little', 'story',
    ),
    'german': (
        'der', 'die', 'das', 'und', 'ist', 'war', 'waren', 'ein', 'eine', 'einem', 'einen', 'eines',
        'nicht', 'mit', 'als', 'dass', 'wurde', 'wusste', 'plötzlich', 'kleiner', 'geschichte',
        'guten', 'tag', 'hallo', 'aus',
    ),
    'french': (
        'le', 'la', 'les', 'des', 'une', 'un', 'et', 'est', 'était', 'dans', 'avec', 'que',
        'bonjour', 'fois', 'petit',
    ),
    'spanish': (
        'el', 'la', 'los', 'las', 'una', 'un', 'y', 'es', 'era', 'con', 'que', 'hola', 'había',
    ),
    'italian': (
        'il', 'lo', 'la', 'gli', 'una', 'un', 'e', 'è', 'era', 'con', 'che', 'ciao', 'volta',
    ),
    'portuguese': (
        'o', 'a', 'os', 'as', 'um', 'uma', 'e', 'é', 'era', 'com', 'que', 'olá', 'vez',
    ),
    'russian': ('и', 'в', 'не', 'что', 'он', 'она', 'это', 'как', 'привет'),
    'japanese': ('です', 'ます', 'した', 'する', 'これ', 'そして'),
    'korean': ('합니다', '했다', '그리고', '있는', '에서'),
    'chinese': ('的', '了', '在', '是', '和', '有', '一个'),
}
_TTS_LANGUAGE_CHARS: dict[str, str] = {
    'german': 'äöüß',
    'french': 'àâçéèêëîïôùûüÿœæ',
    'spanish': 'áéíñóúü¿¡',
    'italian': 'àèéìíîòóù',
    'portuguese': 'áâãàçéêíóôõú',
}
_TTS_TOKEN_RE = re.compile(r"[a-zà-ÿ]+", re.IGNORECASE)
_TTS_SPOKEN_WORD_RE = re.compile(
    r"[^\W_]+(?:['\u2019][^\W_]+)?",
    re.UNICODE,
)
_QWEN3_TTS_GENERATION_BUDGET_POLICY_ID = 'qwen3_tts_adaptive_audio_tokens_v2'
_QWEN3_TTS_SAMPLING_PROFILE_POLICY_ID = 'qwen3_tts_model_native_sampling_v1'
_QWEN3_TTS_AUDIO_TOKENS_PER_SECOND = 12.5
_QWEN3_TTS_WORDS_PER_SECOND = 2.0
_QWEN3_TTS_ORDINARY_CHARS_PER_SECOND = 12.0
_QWEN3_TTS_CJK_CHARS_PER_SECOND = 4.0
_QWEN3_TTS_DURATION_SAFETY_MULTIPLIER = 1.5
_QWEN3_TTS_FIXED_BUFFER_SECONDS = 8.0
_QWEN3_TTS_MIN_GENERATION_TOKENS = 256
_QWEN3_TTS_MAX_GENERATION_TOKENS = 1200
_QWEN3_TTS_TEMPERATURE = 0.9
_QWEN3_TTS_TOP_P = 1.0
_QWEN3_TTS_TOP_K = 50
_QWEN3_TTS_REPETITION_PENALTY = 1.05
_QWEN3_TTS_CHUNKING_POLICY_ID = 'qwen3_tts_sentence_chunks_v1'
_QWEN3_TTS_CHUNK_TRIGGER_SPEECH_SECONDS = 16.0
_QWEN3_TTS_BASE_CHUNK_TRIGGER_SPEECH_SECONDS = 56.0
_QWEN3_TTS_DESIGNED_VOICE_CHUNK_TRIGGER_SPEECH_SECONDS = 28.0
_QWEN3_TTS_CHUNK_TARGET_SPEECH_SECONDS = 10.0
_QWEN3_TTS_GENERATION_LIMIT_RECOVERY_POLICY_ID = (
    'qwen3_tts_single_sequence_generation_limit_retry_v2'
)
_QWEN3_TTS_GENERATION_LIMIT_RECOVERY_MULTIPLIER = 1.5
_QWEN3_TTS_GENERATION_LIMIT_RECOVERY_ADDITIONAL_TOKENS = 128
_QWEN3_TTS_GENERATION_LIMIT_RECOVERY_MODEL_TYPES = {
    'base',
    'custom_voice',
    'voice_design',
}
_TTS_SENTENCE_END_RE = re.compile(
    r'(?:[.!?…]+["\'’”»\)\]]*|\n{2,})(?=\s|$)'
)
_TTS_CHUNK_BOUNDARY_RE = re.compile(r'(?:[,;:—–-]\s+|\s+)')


@dataclass
class InferContext:
    instance_id: str
    backend: str
    capability: str
    model_name: str
    port: int
    prompt: str
    user_prompt: str
    infer_timeout_sec: int
    pdf_page_timeout_sec: int
    pdf_max_image_side: int
    pdf_synthesize: bool
    task: str = 'transcribe'
    language: Optional[str] = None
    voice: Optional[str] = None
    instruct: Optional[str] = None
    response_format: Optional[str] = None
    speed: float = 1.0
    pitch: float = 1.0
    lang_code: Optional[str] = None
    tts_model_type: Optional[str] = None
    tts_speakers: list[str] = field(default_factory=list)
    tts_languages: list[str] = field(default_factory=list)
    ocr_mode: Optional[str] = None
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    image_seed: Optional[int] = None
    text_artifact_requests: list[dict[str, str]] = field(default_factory=list)
    prompt_is_semantic_materializer_payload: bool = False
    reasoning_effort: Optional[str] = None
    phase_system_prompt: Optional[str] = None
    supports_vision_input: bool = False
    backend_package: str = ''
    backend_metadata: dict = field(default_factory=dict)
    request_model: Optional[str] = None
    image_steps: Optional[int] = None


@dataclass
class InferArtifacts:
    temp_path: Optional[Path] = None
    file_kind: str = ''
    file_name: str = ''
    file_sha256: str = ''
    image_b64: Optional[str] = None
    text_from_file: str = ''
    text_from_file_truncated: bool = False
    text_from_file_inline_bytes: int = 0
    text_from_file_total_bytes: int = 0
    pdf_page_images: list[str] = field(default_factory=list)
    pdf_warnings: list[str] = field(default_factory=list)
    pdf_total_pages: int = 0
    pdf_render_dpi: int = 180
    pdf_page_retry_dpi: int = 120


def dispatch_infer_request(
    ctx: InferContext,
    artifacts: InferArtifacts,
    ops: Dict[str, Callable[..., Any]],
) -> Tuple[dict, int]:
    if ctx.backend == 'apple_pcc' and ctx.capability not in {'chat', CAPABILITY_VISION_ANALYSIS}:
        return {'error': 'PCC Shortcuts supports chat and vision_analysis; speech and image generation are unsupported.'}, 400
    image_tool_mode = str(ctx.ocr_mode or '').strip().lower()
    if image_tool_mode in APPLE_FM_IMAGE_TOOL_MODES:
        if ctx.backend != 'apple_fm' or ctx.capability not in {'chat', CAPABILITY_VISION_ANALYSIS}:
            return {'error': 'Apple image tool modes require an Apple AI chat or vision instance.'}, 400
        if artifacts.file_kind == 'pdf':
            if not artifacts.pdf_page_images:
                return {'error': 'Apple PDF tools require rendered page images.'}, 400
            return _run_pdf_vision_analysis(ctx, artifacts, ops)
        if artifacts.file_kind != 'image' or not artifacts.image_b64:
            return {'error': 'Apple OCR and barcode modes require an image or PDF.'}, 400
        try:
            content, evidence = run_apple_fm_image_tool(
                mode=image_tool_mode, image_b64=artifacts.image_b64,
                instance_id=ctx.instance_id, timeout_sec=ctx.infer_timeout_sec,
            )
        except ValueError as exc:
            return {'error': str(exc)}, 400
        except AppleFMImageToolError as exc:
            return {'error': str(exc), 'mode': image_tool_mode, 'instance_id': ctx.instance_id}, 502
        if evidence['result']['empty']:
            content = 'No text detected.' if image_tool_mode == 'apple_ocr' else 'No barcodes detected.'
        return {
            'instance_id': ctx.instance_id, 'capability': ctx.capability,
            'mode': image_tool_mode, 'content': content,
            'apple_fm_image_tool_evidence': evidence,
            'vision_input_evidence': {
                'kind': 'fruth.vision_input_evidence', 'version': 1,
                'authority': 'runtime_vision_image_dispatch', 'status': 'supplied',
                'instance_id': ctx.instance_id,
                'image_sha256': evidence['source_image_sha256'],
                'size_bytes': evidence['source_size_bytes'],
                'transport': 'fm.respond', 'execution_scope': 'local_cli_session',
                'attachment_sha256': evidence['attachment_sha256'],
                'image_reencoded': evidence['image_reencoded'],
            },
        }, 200
    if ctx.backend == 'apple_fm' and image_tool_mode not in {'', 'auto'}:
        return {'error': 'Invalid Apple AI image mode. Choose auto, apple_ocr or apple_barcode.'}, 400
    if ctx.capability == CAPABILITY_SPEECH_TO_TEXT:
        return _run_speech_to_text(ctx, artifacts, ops)
    if ctx.capability == CAPABILITY_TEXT_TO_SPEECH:
        return _run_text_to_speech(ctx, artifacts, ops)
    if ctx.capability == CAPABILITY_IMAGE_GENERATION:
        return _run_image_generation(ctx, artifacts, ops)
    if ctx.capability == CAPABILITY_VISION_ANALYSIS:
        return _run_vision_analysis(ctx, artifacts, ops)
    if (
        ctx.capability == 'chat' and ctx.supports_vision_input
        and artifacts.file_kind == 'pdf' and artifacts.pdf_page_images
    ):
        return _run_pdf_vision_analysis(ctx, artifacts, ops)
    return _run_chat_fallback(ctx, artifacts, ops)


def _extract_transcript_text(result: dict) -> str:
    text = str(result.get('text') or '').strip()
    if text:
        return text
    segments = result.get('segments')
    if not isinstance(segments, list):
        return ''
    parts: list[str] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        chunk = str(segment.get('text') or '').strip()
        if chunk:
            parts.append(chunk)
    return '\n'.join(parts).strip()


def _effective_vision_prompt(ctx: InferContext) -> str:
    return resolve_ocr_prompt(
        ctx.model_name,
        user_prompt=ctx.prompt,
        ocr_mode=ctx.ocr_mode,
        generic_fallback=GENERIC_OCR_FALLBACK_PROMPT,
    )


def _run_backend_chat_completion(
    ctx: InferContext,
    ops: Dict[str, Callable[..., Any]],
    messages: list[dict],
    *,
    timeout_sec: int,
) -> dict:
    if ctx.backend == 'mlx':
        return ops['mlx_chat_completions'](
            ctx.port,
            ctx.model_name,
            messages,
            timeout_sec=timeout_sec,
            reasoning_effort=ctx.reasoning_effort,
        )
    return ops['openai_chat_completions'](
        ctx.port,
        ctx.model_name,
        messages,
        timeout_sec=timeout_sec,
    )


def _build_pdf_inline_response_content(
    full_content: str,
    *,
    warnings: list[str],
    max_inline_chars: Optional[int],
) -> tuple[str, bool]:
    response_content = str(full_content or '')
    if not response_content or not max_inline_chars or len(response_content) <= max_inline_chars:
        return response_content, False
    warnings.append(
        f'UI output was truncated to {max_inline_chars} chars for stability. '
        'Use the saved markdown artifact for full content.'
    )
    return (
        response_content[:max_inline_chars].rstrip()
        + '\n\n...[UI output truncated for stability; full OCR result saved locally.]'
    ), True


def _run_speech_to_text(ctx: InferContext, artifacts: InferArtifacts, ops: Dict[str, Callable[..., Any]]) -> Tuple[dict, int]:
    if not artifacts.temp_path:
        return {'error': 'speech_to_text requires an audio file.'}, 400
    if artifacts.file_kind != 'audio':
        return {'error': f"Expected an audio file, received: {artifacts.file_kind or 'unknown'}."}, 400
    result = ops['whisper_transcribe'](ctx.port, artifacts.temp_path, task=ctx.task, language=ctx.language)
    transcript_text = _extract_transcript_text(result)
    if not transcript_text:
        return {'error': 'Whisper did not return transcript text.'}, 502
    saved_text_path = ops['persist_transcript_text_locally'](
        transcript_text,
        model_name=ctx.model_name,
        source_file_name=artifacts.file_name or 'audio',
        mode='speech_to_text',
    )
    return (
        {
            'instance_id': ctx.instance_id,
            'capability': ctx.capability,
            'mode': 'speech_to_text',
            'content': transcript_text,
            'saved_text_path': saved_text_path,
            'result': result,
        },
        200,
    )


def _normalize_language_token(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', str(value or '').strip().lower())


def _supported_tts_language_token(language: str, supported_languages: list[str]) -> Optional[str]:
    normalized_language = _normalize_language_token(language)
    aliases = {
        _normalize_language_token(alias)
        for alias in _TTS_LANGUAGE_ALIASES.get(language, (language,))
    }
    if normalized_language:
        aliases.add(normalized_language)
    supported = [str(item or '').strip() for item in supported_languages if str(item or '').strip()]
    if not supported:
        return _TTS_FALLBACK_LANGUAGE_CODES.get(language)
    for token in supported:
        normalized_supported = _normalize_language_token(token)
        if normalized_supported in aliases:
            return token
    return None


def _score_tts_language(text: str, language: str) -> int:
    normalized_text = str(text or '').strip().lower()
    if not normalized_text:
        return 0
    token_counts = Counter(_TTS_TOKEN_RE.findall(normalized_text))
    markers = _TTS_LANGUAGE_MARKERS.get(language, ())
    score = sum(min(token_counts.get(marker, 0), 3) for marker in markers)
    char_markers = _TTS_LANGUAGE_CHARS.get(language, '')
    if char_markers and any(char in normalized_text for char in char_markers):
        score += 4
    if language == 'russian' and re.search(r'[\u0400-\u04ff]', normalized_text):
        score += 5
    if language == 'japanese' and re.search(r'[\u3040-\u30ff]', normalized_text):
        score += 5
    if language == 'korean' and re.search(r'[\uac00-\ud7af]', normalized_text):
        score += 5
    if language == 'chinese' and re.search(r'[\u4e00-\u9fff]', normalized_text):
        score += 5
    return score


def _infer_tts_language_from_text(text: str, supported_languages: list[str]) -> Optional[str]:
    scores = {
        language: _score_tts_language(text, language)
        for language in _TTS_LANGUAGE_ALIASES
    }
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if not ranked:
        return None
    top_language, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    if top_score < 2 or top_score <= second_score:
        return None
    return _supported_tts_language_token(top_language, supported_languages)


def _resolve_effective_tts_lang_code(
    explicit_lang_code: Optional[str],
    spoken_text: str,
    supported_languages: list[str],
) -> tuple[Optional[str], Optional[str]]:
    explicit = str(explicit_lang_code or '').strip()
    if explicit and _normalize_language_token(explicit) not in _TTS_AUTO_LANGUAGE_CODES:
        return explicit, 'explicit'
    inferred = _infer_tts_language_from_text(spoken_text, supported_languages)
    if inferred:
        return inferred, 'inferred_from_text'
    return None, None


def _is_qwen3_tts_model(model_name: Any) -> bool:
    return bool(
        re.search(
            r'(?<![a-z0-9])qwen3[^a-z0-9]*tts(?![a-z0-9])',
            str(model_name or '').strip().lower(),
        )
    )


def _canonicalize_qwen3_tts_lang_code(
    lang_code: Optional[str],
) -> tuple[Optional[str], bool]:
    """Map known aliases to the full language tokens accepted by Qwen3-TTS."""

    value = str(lang_code or '').strip()
    if not value:
        return None, False
    normalized = _normalize_language_token(value)
    if normalized in _TTS_AUTO_LANGUAGE_CODES:
        return value, False
    for canonical_language, aliases in _TTS_LANGUAGE_ALIASES.items():
        if normalized == _normalize_language_token(canonical_language):
            return value, False
        if normalized in {
            _normalize_language_token(alias)
            for alias in aliases
        }:
            return canonical_language, True
    return value, False


def _is_cjk_speech_character(character: str) -> bool:
    codepoint = ord(character)
    return (
        0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
        or 0x3040 <= codepoint <= 0x30FF
        or 0xAC00 <= codepoint <= 0xD7AF
    )


def build_qwen3_tts_generation_budget(spoken_text: Any) -> dict[str, Any]:
    """Return an observable, conservative Qwen3 audio-token safety budget."""

    text = str(spoken_text or '')
    word_count = len(_TTS_SPOKEN_WORD_RE.findall(text))
    visible_characters = [character for character in text if not character.isspace()]
    cjk_character_count = sum(
        1
        for character in visible_characters
        if _is_cjk_speech_character(character)
    )
    ordinary_character_count = len(visible_characters) - cjk_character_count
    word_estimate_seconds = word_count / _QWEN3_TTS_WORDS_PER_SECOND
    character_estimate_seconds = (
        ordinary_character_count / _QWEN3_TTS_ORDINARY_CHARS_PER_SECOND
        + cjk_character_count / _QWEN3_TTS_CJK_CHARS_PER_SECOND
    )
    estimated_speech_seconds = max(
        word_estimate_seconds,
        character_estimate_seconds,
    )
    buffered_duration_seconds = (
        estimated_speech_seconds * _QWEN3_TTS_DURATION_SAFETY_MULTIPLIER
        + _QWEN3_TTS_FIXED_BUFFER_SECONDS
    )
    calculated_tokens = int(
        math.ceil(
            buffered_duration_seconds
            * _QWEN3_TTS_AUDIO_TOKENS_PER_SECOND
        )
    )
    max_tokens = min(
        _QWEN3_TTS_MAX_GENERATION_TOKENS,
        max(_QWEN3_TTS_MIN_GENERATION_TOKENS, calculated_tokens),
    )
    clamp = (
        'minimum'
        if max_tokens > calculated_tokens
        else 'maximum'
        if max_tokens < calculated_tokens
        else 'none'
    )
    return {
        'kind': 'fruth.tts_generation_budget',
        'version': 1,
        'policy_id': _QWEN3_TTS_GENERATION_BUDGET_POLICY_ID,
        'model_family': 'qwen3_tts',
        'max_tokens': max_tokens,
        'calculated_tokens_before_clamp': calculated_tokens,
        'clamp': clamp,
        'source_word_count': word_count,
        'source_visible_character_count': len(visible_characters),
        'source_cjk_character_count': cjk_character_count,
        'estimated_speech_seconds': round(estimated_speech_seconds, 6),
        'buffered_duration_seconds': round(buffered_duration_seconds, 6),
        'policy': {
            'audio_tokens_per_second': _QWEN3_TTS_AUDIO_TOKENS_PER_SECOND,
            'words_per_second': _QWEN3_TTS_WORDS_PER_SECOND,
            'ordinary_characters_per_second': _QWEN3_TTS_ORDINARY_CHARS_PER_SECOND,
            'cjk_characters_per_second': _QWEN3_TTS_CJK_CHARS_PER_SECOND,
            'duration_safety_multiplier': _QWEN3_TTS_DURATION_SAFETY_MULTIPLIER,
            'fixed_buffer_seconds': _QWEN3_TTS_FIXED_BUFFER_SECONDS,
            'minimum_tokens': _QWEN3_TTS_MIN_GENERATION_TOKENS,
            'maximum_tokens': _QWEN3_TTS_MAX_GENERATION_TOKENS,
        },
    }


def _qwen3_tts_base_segments(spoken_text: Any) -> list[str]:
    """Return the nonempty newline segments generated independently by Base."""

    return [
        line.strip()
        for line in str(spoken_text or '').splitlines()
        if line.strip()
    ]


def _build_qwen3_tts_sampling_profile() -> dict[str, Any]:
    """Return the explicit Qwen3 sampling contract sent to MLX Audio."""

    return {
        'kind': 'fruth.tts_sampling_profile',
        'version': 1,
        'policy_id': _QWEN3_TTS_SAMPLING_PROFILE_POLICY_ID,
        'model_family': 'qwen3_tts',
        'source': 'mlx_audio_qwen3_tts_model_defaults',
        'temperature': _QWEN3_TTS_TEMPERATURE,
        'top_p': _QWEN3_TTS_TOP_P,
        'top_k': _QWEN3_TTS_TOP_K,
        'repetition_penalty': _QWEN3_TTS_REPETITION_PENALTY,
    }


def _trim_text_span(text: str, start: int, end: int) -> tuple[int, int]:
    bounded_start = max(0, min(len(text), start))
    bounded_end = max(bounded_start, min(len(text), end))
    while bounded_start < bounded_end and text[bounded_start].isspace():
        bounded_start += 1
    while bounded_end > bounded_start and text[bounded_end - 1].isspace():
        bounded_end -= 1
    return bounded_start, bounded_end


def _qwen3_tts_estimated_speech_seconds(text: str) -> float:
    return float(
        build_qwen3_tts_generation_budget(text).get('estimated_speech_seconds')
        or 0.0
    )


def _split_qwen3_tts_span_to_target(
    text: str,
    start: int,
    end: int,
) -> list[tuple[int, int]]:
    start, end = _trim_text_span(text, start, end)
    if start >= end:
        return []
    if (
        _qwen3_tts_estimated_speech_seconds(text[start:end])
        <= _QWEN3_TTS_CHUNK_TARGET_SPEECH_SECONDS
    ):
        return [(start, end)]

    spans: list[tuple[int, int]] = []
    cursor = start
    while cursor < end:
        remaining_start, remaining_end = _trim_text_span(text, cursor, end)
        if remaining_start >= remaining_end:
            break
        remaining = text[remaining_start:remaining_end]
        if (
            _qwen3_tts_estimated_speech_seconds(remaining)
            <= _QWEN3_TTS_CHUNK_TARGET_SPEECH_SECONDS
        ):
            spans.append((remaining_start, remaining_end))
            break

        selected_cut = 0
        first_oversized_cut = 0
        for boundary in _TTS_CHUNK_BOUNDARY_RE.finditer(remaining):
            cut = boundary.end()
            candidate = remaining[:cut].strip()
            if not candidate:
                continue
            estimate = _qwen3_tts_estimated_speech_seconds(candidate)
            if estimate <= _QWEN3_TTS_CHUNK_TARGET_SPEECH_SECONDS:
                selected_cut = cut
                continue
            first_oversized_cut = cut
            break
        if not selected_cut:
            selected_cut = first_oversized_cut
        if not selected_cut:
            visible_limit = max(
                1,
                int(
                    _QWEN3_TTS_CHUNK_TARGET_SPEECH_SECONDS
                    * _QWEN3_TTS_CJK_CHARS_PER_SECOND
                ),
            )
            selected_cut = min(len(remaining), visible_limit)
        absolute_cut = min(remaining_end, remaining_start + selected_cut)
        chunk_start, chunk_end = _trim_text_span(
            text,
            remaining_start,
            absolute_cut,
        )
        if chunk_start >= chunk_end:
            absolute_cut = min(remaining_end, remaining_start + 1)
            chunk_start, chunk_end = _trim_text_span(
                text,
                remaining_start,
                absolute_cut,
            )
        if chunk_start < chunk_end:
            spans.append((chunk_start, chunk_end))
        cursor = max(absolute_cut, remaining_start + 1)
    return spans


def build_qwen3_tts_chunk_plan(
    spoken_text: Any,
    *,
    tts_model_type: Optional[str] = None,
) -> dict[str, Any]:
    """Return deterministic ordered sentence/clause spans for long Qwen speech."""

    text = str(spoken_text or '')
    source_sha256 = hashlib.sha256(text.encode('utf-8')).hexdigest()
    full_estimated_seconds = _qwen3_tts_estimated_speech_seconds(text)
    normalized_model_type = str(tts_model_type or '').strip().lower()
    chunk_trigger_speech_seconds = {
        'base': _QWEN3_TTS_BASE_CHUNK_TRIGGER_SPEECH_SECONDS,
        'custom_voice': _QWEN3_TTS_DESIGNED_VOICE_CHUNK_TRIGGER_SPEECH_SECONDS,
        'voice_design': _QWEN3_TTS_DESIGNED_VOICE_CHUNK_TRIGGER_SPEECH_SECONDS,
    }.get(
        normalized_model_type,
        _QWEN3_TTS_CHUNK_TRIGGER_SPEECH_SECONDS,
    )
    base_segments = (
        _qwen3_tts_base_segments(text)
        if normalized_model_type == 'base'
        else []
    )
    trigger_basis = (
        'longest_backend_segment'
        if normalized_model_type == 'base'
        else 'full_source'
    )
    trigger_estimated_speech_seconds = (
        max(
            (
                _qwen3_tts_estimated_speech_seconds(segment)
                for segment in base_segments
            ),
            default=full_estimated_seconds,
        )
        if normalized_model_type == 'base'
        else full_estimated_seconds
    )
    sentence_spans: list[tuple[int, int]] = []
    cursor = 0
    for boundary in _TTS_SENTENCE_END_RE.finditer(text):
        span = _trim_text_span(text, cursor, boundary.end())
        if span[0] < span[1]:
            sentence_spans.append(span)
        cursor = boundary.end()
    trailing = _trim_text_span(text, cursor, len(text))
    if trailing[0] < trailing[1]:
        sentence_spans.append(trailing)
    if not sentence_spans and text.strip():
        sentence_spans = [_trim_text_span(text, 0, len(text))]

    chunk_spans: list[tuple[int, int]] = []
    pending: Optional[tuple[int, int]] = None
    for sentence_start, sentence_end in sentence_spans:
        if pending is None:
            pending = (sentence_start, sentence_end)
            continue
        candidate = text[pending[0]:sentence_end]
        if (
            _qwen3_tts_estimated_speech_seconds(candidate)
            <= _QWEN3_TTS_CHUNK_TARGET_SPEECH_SECONDS
        ):
            pending = (pending[0], sentence_end)
            continue
        chunk_spans.extend(
            _split_qwen3_tts_span_to_target(text, pending[0], pending[1])
        )
        pending = (sentence_start, sentence_end)
    if pending is not None:
        chunk_spans.extend(
            _split_qwen3_tts_span_to_target(text, pending[0], pending[1])
        )

    ordered_span_coverage = bool(chunk_spans)
    previous_end = 0
    for span_start, span_end in chunk_spans:
        if (
            span_start < previous_end
            or text[previous_end:span_start].strip()
            or not text[span_start:span_end].strip()
        ):
            ordered_span_coverage = False
            break
        previous_end = span_end
    if text[previous_end:].strip():
        ordered_span_coverage = False

    applied = bool(
        trigger_estimated_speech_seconds > chunk_trigger_speech_seconds
        and len(chunk_spans) > 1
        and ordered_span_coverage
    )
    chunks = [
        {
            'index': index,
            'source_span_start': span_start,
            'source_span_end': span_end,
            'text': text[span_start:span_end],
            'text_sha256': hashlib.sha256(
                text[span_start:span_end].encode('utf-8')
            ).hexdigest(),
            'estimated_speech_seconds': round(
                _qwen3_tts_estimated_speech_seconds(
                    text[span_start:span_end]
                ),
                6,
            ),
        }
        for index, (span_start, span_end) in enumerate(chunk_spans, start=1)
    ]
    return {
        'kind': 'fruth.tts_chunking_plan',
        'version': 1,
        'policy_id': _QWEN3_TTS_CHUNKING_POLICY_ID,
        'model_family': 'qwen3_tts',
        'status': 'planned' if applied else 'not_applied',
        'applied': applied,
        'reason': (
            'estimated speech exceeds the single-request long-form threshold'
            if applied
            else 'source remains within the single-request long-form threshold'
            if trigger_estimated_speech_seconds <= chunk_trigger_speech_seconds
            else 'safe ordered multi-chunk coverage was not available'
        ),
        'source_sha256': source_sha256,
        'source_character_count': len(text),
        'estimated_speech_seconds': round(full_estimated_seconds, 6),
        'trigger_speech_seconds': chunk_trigger_speech_seconds,
        'trigger_basis': trigger_basis,
        'trigger_estimated_speech_seconds': round(
            trigger_estimated_speech_seconds,
            6,
        ),
        'backend_segment_count': (
            len(base_segments)
            if normalized_model_type == 'base'
            else 1
        ),
        'target_chunk_speech_seconds': _QWEN3_TTS_CHUNK_TARGET_SPEECH_SECONDS,
        'ordered_span_coverage': ordered_span_coverage,
        'chunk_count': len(chunks) if applied else 1,
        'chunks': chunks if applied else [],
    }


def _build_qwen3_tts_generation_limit_recovery(
    initial_budget: Mapping[str, Any],
    *,
    integrity_evidence: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Return one bounded Qwen single-sequence retry budget after cap exhaustion."""

    budget = dict(initial_budget)
    model_family = str(budget.get('model_family') or '').strip().lower()
    tts_model_type = str(budget.get('tts_model_type') or '').strip().lower()
    generation_scope = str(budget.get('generation_scope') or '').strip().lower()
    supported_sequence = bool(
        model_family == 'qwen3_tts'
        and tts_model_type
        in _QWEN3_TTS_GENERATION_LIMIT_RECOVERY_MODEL_TYPES
        and generation_scope == 'single_sequence'
    )
    try:
        initial_max_tokens = int(budget.get('max_tokens') or 0)
    except (TypeError, ValueError):
        initial_max_tokens = 0
    calculated_recovery_tokens = max(
        initial_max_tokens
        + _QWEN3_TTS_GENERATION_LIMIT_RECOVERY_ADDITIONAL_TOKENS,
        int(
            math.ceil(
                initial_max_tokens
                * _QWEN3_TTS_GENERATION_LIMIT_RECOVERY_MULTIPLIER
            )
        ),
    )
    recovery_max_tokens = min(
        _QWEN3_TTS_MAX_GENERATION_TOKENS,
        calculated_recovery_tokens,
    )
    applied = bool(
        supported_sequence
        and initial_max_tokens > 0
        and recovery_max_tokens > initial_max_tokens
    )
    recovery_budget = dict(budget)
    recovery_budget.update(
        {
            'policy_id': _QWEN3_TTS_GENERATION_LIMIT_RECOVERY_POLICY_ID,
            'base_policy_id': str(budget.get('policy_id') or '').strip() or None,
            'max_tokens': recovery_max_tokens,
            'calculated_tokens_before_clamp': calculated_recovery_tokens,
            'clamp': (
                'maximum'
                if recovery_max_tokens < calculated_recovery_tokens
                else 'none'
            ),
            'recovery_trigger_reason_code': (
                'TTS_AUDIO_GENERATION_LIMIT_EXHAUSTED'
            ),
            'recovery_initial_max_tokens': initial_max_tokens,
        }
    )
    return {
        'kind': 'fruth.tts_generation_limit_recovery',
        'version': 1,
        'policy_id': _QWEN3_TTS_GENERATION_LIMIT_RECOVERY_POLICY_ID,
        'status': 'eligible' if applied else 'not_eligible',
        'applied': applied,
        'reason': (
            'one larger bounded Qwen single-sequence retry budget is available'
            if applied
            else 'model scope is unsupported, the initial budget is invalid, or the hard maximum is already active'
        ),
        'trigger_reason_code': 'TTS_AUDIO_GENERATION_LIMIT_EXHAUSTED',
        'model_family_scope': 'qwen3_tts',
        'model_type_scope': sorted(
            _QWEN3_TTS_GENERATION_LIMIT_RECOVERY_MODEL_TYPES
        ),
        'tts_model_type': tts_model_type or None,
        'generation_scope': generation_scope or None,
        'maximum_retry_count': 1,
        'initial_max_tokens': initial_max_tokens,
        'calculated_recovery_tokens_before_clamp': calculated_recovery_tokens,
        'recovery_max_tokens': recovery_max_tokens,
        'clamp': (
            'maximum'
            if recovery_max_tokens < calculated_recovery_tokens
            else 'none'
        ),
        'policy': {
            'multiplier': _QWEN3_TTS_GENERATION_LIMIT_RECOVERY_MULTIPLIER,
            'additional_tokens': (
                _QWEN3_TTS_GENERATION_LIMIT_RECOVERY_ADDITIONAL_TOKENS
            ),
            'maximum_tokens': _QWEN3_TTS_MAX_GENERATION_TOKENS,
        },
        'trigger_primary_reason_code': str(
            (integrity_evidence or {}).get('reason_code') or ''
        ).strip() or None,
        'trigger_defect_codes': [
            str(item).strip()
            for item in (integrity_evidence or {}).get('defect_codes') or []
            if str(item).strip()
        ] if isinstance((integrity_evidence or {}).get('defect_codes'), list) else [],
        'trigger_generation_limit_evidence': dict(
            (integrity_evidence or {}).get('generation_limit_evidence') or {}
        ) if isinstance(
            (integrity_evidence or {}).get('generation_limit_evidence'),
            Mapping,
        ) else {},
        'generation_budget': recovery_budget if applied else None,
    }


def _qwen3_tts_budget_with_scope(
    spoken_text: str,
    *,
    tts_model_type: str,
    generation_scope: str,
) -> dict[str, Any]:
    normalized_model_type = str(tts_model_type or '').strip().lower() or 'unknown'
    base_segments = (
        _qwen3_tts_base_segments(spoken_text)
        if normalized_model_type == 'base'
        and generation_scope == 'segmented_sequence'
        else []
    )
    if base_segments:
        segment_budgets = [
            build_qwen3_tts_generation_budget(segment)
            for segment in base_segments
        ]
        budget = dict(
            max(
                segment_budgets,
                key=lambda item: int(
                    item.get('calculated_tokens_before_clamp') or 0
                ),
            )
        )
        aggregate_budget = build_qwen3_tts_generation_budget(spoken_text)
        budget.update(
            {
                'budget_scope': 'longest_backend_segment',
                'max_tokens_application': 'per_backend_segment',
                'backend_segment_count': len(base_segments),
                'aggregate_source_word_count': aggregate_budget[
                    'source_word_count'
                ],
                'aggregate_source_visible_character_count': aggregate_budget[
                    'source_visible_character_count'
                ],
                'aggregate_estimated_speech_seconds': aggregate_budget[
                    'estimated_speech_seconds'
                ],
            }
        )
    else:
        budget = dict(build_qwen3_tts_generation_budget(spoken_text))
        budget['budget_scope'] = 'full_source'
        budget['max_tokens_application'] = 'single_backend_sequence'
    budget['tts_model_type'] = normalized_model_type
    budget['generation_scope'] = generation_scope
    return budget


def _qwen3_tts_generation_scope(
    spoken_text: str,
    *,
    tts_model_type: str,
) -> str:
    model_type = str(tts_model_type or '').strip().lower()
    if model_type in {'voice_design', 'custom_voice'}:
        return 'single_sequence'
    if model_type == 'base':
        nonempty_line_count = len(_qwen3_tts_base_segments(spoken_text))
        return (
            'segmented_sequence'
            if nonempty_line_count > 1
            else 'single_sequence'
        )
    return 'unverified_sequence'


def _tts_audio_bytes_integrity_evidence(
    audio_bytes: Any,
    source_text: str,
    *,
    source_sha256: str,
    generation_budget: Mapping[str, Any],
    tts_model_type: str,
) -> dict[str, Any]:
    raw = bytes(audio_bytes or b'')
    if not raw:
        return {
            'kind': 'fruth.tts_audio_integrity_evidence',
            'version': 1,
            'status': 'failed',
            'reason_code': 'TTS_AUDIO_CHUNK_BYTES_MISSING',
            'materialization_eligible': False,
            'source_sha256': source_sha256,
        }
    with tempfile.NamedTemporaryFile(suffix='.wav') as handle:
        handle.write(raw)
        handle.flush()
        evidence = build_tts_audio_integrity_evidence(
            handle.name,
            source_text,
            source_sha256=source_sha256,
            generation_budget=generation_budget,
            model_family='qwen3_tts',
            tts_model_type=tts_model_type,
            integrity_profile=TTS_QWEN_SENTENCE_CHUNK_INTEGRITY_PROFILE,
        )
    evidence = dict(evidence)
    evidence.pop('artifact_path', None)
    evidence['artifact_scope'] = 'ephemeral_backend_chunk'
    evidence['persisted'] = False
    return evidence


def _run_text_to_speech(ctx: InferContext, artifacts: InferArtifacts, ops: Dict[str, Callable[..., Any]]) -> Tuple[dict, int]:
    if ctx.backend != 'mlx':
        return {'error': "text_to_speech is currently supported only for MLX."}, 400
    if artifacts.file_kind and artifacts.file_kind not in {'text'}:
        return {'error': 'For text_to_speech, use only a text prompt or text file.'}, 400
    model_name_lower = str(ctx.model_name or '').lower()
    tts_model_type = str(ctx.tts_model_type or '').strip().lower()
    available_speakers = [str(speaker or '').strip() for speaker in (ctx.tts_speakers or []) if str(speaker or '').strip()]
    if not tts_model_type:
        if 'qwen3-tts' in model_name_lower and 'customvoice' in model_name_lower:
            tts_model_type = 'custom_voice'
        elif 'qwen3-tts' in model_name_lower and 'voicedesign' in model_name_lower:
            tts_model_type = 'voice_design'
        elif 'qwen3-tts' in model_name_lower and 'base' in model_name_lower:
            tts_model_type = 'base'
        elif 'kitten-tts' in model_name_lower:
            tts_model_type = 'kitten_tts'
    effective_voice = str(ctx.voice or '').strip()
    if tts_model_type == 'kitten_tts':
        if not effective_voice and available_speakers:
            effective_voice = available_speakers[0]
        if effective_voice and available_speakers and effective_voice.lower() not in {speaker.lower() for speaker in available_speakers}:
            speaker_list = ', '.join(available_speakers)
            return (
                {
                    'error': (
                        f"Speaker '{effective_voice}' is not supported by this Kitten-TTS model. "
                        f"Available: {speaker_list}."
                    )
                },
                400,
            )
        if not effective_voice:
            speaker_list = ', '.join(available_speakers) if available_speakers else 'no automatically detected speakers'
            return (
                {
                    'error': (
                        "This Kitten-TTS model requires a speaker, but Fruth could not derive a valid "
                        f"default from the metadata. Available: {speaker_list}."
                    )
                },
                400,
            )
    if (
        tts_model_type == 'custom_voice'
        and not effective_voice
    ):
        speaker_list = ', '.join(QWEN3_CUSTOMVOICE_SPEAKERS)
        return (
            {
                'error': (
                    "This Qwen3-TTS-CustomVoice model requires a speaker from the list. "
                    f"Available: {speaker_list}. "
                    "If you want to describe the voice in natural language, use a VoiceDesign model."
                )
            },
            400,
        )
    if (
        effective_voice
        and tts_model_type == 'custom_voice'
        and effective_voice.lower() not in {speaker.lower() for speaker in QWEN3_CUSTOMVOICE_SPEAKERS}
    ):
        speaker_list = ', '.join(QWEN3_CUSTOMVOICE_SPEAKERS)
        return (
            {
                'error': (
                    f"Speaker '{effective_voice}' is not supported by this Qwen3-TTS-CustomVoice model. "
                    f"Available: {speaker_list}. "
                    "For free-form voice description in natural language, use a VoiceDesign model."
                )
            },
            400,
        )
    if tts_model_type == 'voice_design' and not str(ctx.instruct or '').strip():
        return (
            {
                'error': (
                    "This Qwen3-TTS-VoiceDesign model requires a description in the "
                    "'Style / Instruct' field. Use a CustomVoice model instead for fixed speakers."
                )
            },
            400,
        )

    prompt = (
        str(ctx.prompt or '').strip()
        if ctx.prompt_is_semantic_materializer_payload
        else extract_legacy_tts_wrapper_text(ctx.prompt)
    )
    if artifacts.text_from_file:
        prompt = f'{prompt}\n\n{artifacts.text_from_file}'.strip() if prompt else artifacts.text_from_file.strip()
    if not prompt:
        return {'error': 'text_to_speech requires a text prompt.'}, 400

    is_qwen3_tts = _is_qwen3_tts_model(ctx.model_name)
    effective_lang_code, lang_code_source = _resolve_effective_tts_lang_code(
        ctx.lang_code,
        prompt,
        ctx.tts_languages,
    )
    if is_qwen3_tts and effective_lang_code:
        effective_lang_code, lang_code_canonicalized = _canonicalize_qwen3_tts_lang_code(
            effective_lang_code,
        )
        if lang_code_canonicalized:
            lang_code_source = (
                f'{lang_code_source or "resolved"}_qwen3_alias_canonicalized'
            )
    if is_qwen3_tts and not effective_lang_code:
        effective_lang_code = 'auto'
        lang_code_source = 'qwen3_model_default'
    semantic_source = build_tts_semantic_source(
        prompt,
        source_text_source='inference_final_spoken_prompt',
        lang_code=effective_lang_code,
    )

    generation_budget = (
        _qwen3_tts_budget_with_scope(
            prompt,
            tts_model_type=tts_model_type,
            generation_scope=_qwen3_tts_generation_scope(
                prompt,
                tts_model_type=tts_model_type,
            ),
        )
        if is_qwen3_tts
        else None
    )
    sampling_profile = _build_qwen3_tts_sampling_profile() if is_qwen3_tts else None
    base_speech_kwargs = {
        'instruct': ctx.instruct,
        'voice': effective_voice or None,
        'response_format': ctx.response_format,
        'speed': ctx.speed,
        'pitch': ctx.pitch,
        'lang_code': effective_lang_code,
        'timeout_sec': ctx.infer_timeout_sec,
    }
    if sampling_profile:
        base_speech_kwargs.update(
            {
                'temperature': sampling_profile['temperature'],
                'top_p': sampling_profile['top_p'],
                'top_k': sampling_profile['top_k'],
                'repetition_penalty': sampling_profile['repetition_penalty'],
            }
        )

    resolved_response_format = str(ctx.response_format or 'wav').strip().lower()
    chunking_evidence: Optional[dict[str, Any]] = None
    single_sequence_recovery_evidence: Optional[dict[str, Any]] = None
    result: dict[str, Any]
    chunk_failure_reason = ''
    chunk_failure_bytes = b''
    chunk_failure_content_type = 'audio/wav'
    chunk_plan = (
        build_qwen3_tts_chunk_plan(
            prompt,
            tts_model_type=tts_model_type,
        )
        if is_qwen3_tts
        and tts_model_type in {'base', 'voice_design', 'custom_voice'}
        and resolved_response_format in {'wav', 'wave', 'x-wav'}
        else None
    )
    if chunk_plan and chunk_plan.get('applied') is True:
        generation_budget = _qwen3_tts_budget_with_scope(
            prompt,
            tts_model_type=tts_model_type,
            generation_scope='chunked_sequence',
        )
        generation_budget['chunk_count'] = int(chunk_plan.get('chunk_count') or 0)
        chunk_diagnostics: list[dict[str, Any]] = []
        chunk_audio_bytes: list[bytes] = []
        passed_chunk_count = 0
        recovered_chunk_count = 0
        backend_call_count = 0
        recovery_attempt_count = 0

        def synthesize_chunk_attempt(
            chunk_text: str,
            *,
            source_sha256: str,
            attempt_index: int,
            attempt_role: str,
            attempt_budget: Mapping[str, Any],
        ) -> tuple[bytes, str, dict[str, Any], dict[str, Any]]:
            speech_kwargs = dict(base_speech_kwargs)
            speech_kwargs['max_tokens'] = int(
                attempt_budget.get('max_tokens') or 0
            )
            attempt_result = ops['mlx_audio_speech'](
                ctx.port,
                ctx.model_name,
                chunk_text,
                **speech_kwargs,
            )
            attempt_audio = bytes(attempt_result.get('audio_bytes') or b'')
            attempt_content_type = str(
                attempt_result.get('content_type') or 'audio/wav'
            )
            attempt_integrity = _tts_audio_bytes_integrity_evidence(
                attempt_audio,
                chunk_text,
                source_sha256=source_sha256,
                generation_budget=attempt_budget,
                tts_model_type=tts_model_type,
            )
            attempt_record = {
                key: value
                for key, value in {
                    'attempt_index': attempt_index,
                    'role': attempt_role,
                    'generation_budget': dict(attempt_budget),
                    'audio_size_bytes': len(attempt_audio),
                    'audio_sha256': (
                        hashlib.sha256(attempt_audio).hexdigest()
                        if attempt_audio
                        else None
                    ),
                    'content_type': attempt_content_type,
                    'integrity_evidence': attempt_integrity,
                    'selected': False,
                }.items()
                if value not in (None, '', [], {})
            }
            return (
                attempt_audio,
                attempt_content_type,
                attempt_integrity,
                attempt_record,
            )

        for raw_chunk in chunk_plan.get('chunks') or []:
            chunk_text = str(raw_chunk.get('text') or '')
            chunk_source_sha256 = str(raw_chunk.get('text_sha256') or '').strip()
            chunk_budget = _qwen3_tts_budget_with_scope(
                chunk_text,
                tts_model_type=tts_model_type,
                generation_scope=_qwen3_tts_generation_scope(
                    chunk_text,
                    tts_model_type=tts_model_type,
                ),
            )
            (
                raw_audio,
                chunk_content_type,
                chunk_integrity,
                initial_attempt,
            ) = synthesize_chunk_attempt(
                chunk_text,
                source_sha256=chunk_source_sha256,
                attempt_index=1,
                attempt_role='initial',
                attempt_budget=chunk_budget,
            )
            backend_call_count += 1
            attempts = [initial_attempt]
            terminal_budget = chunk_budget
            generation_limit_recovery: Optional[dict[str, Any]] = None
            chunk_passed = bool(
                str(chunk_integrity.get('status') or '').strip().lower()
                == 'passed'
                and chunk_integrity.get('materialization_eligible') is True
            )
            if (
                not chunk_passed
                and tts_audio_has_qwen_generation_limit_exhaustion(
                    chunk_integrity,
                    generation_budget=chunk_budget,
                )
            ):
                generation_limit_recovery = (
                    _build_qwen3_tts_generation_limit_recovery(
                        chunk_budget,
                        integrity_evidence=chunk_integrity,
                    )
                )
                if generation_limit_recovery.get('applied') is True:
                    retry_budget = generation_limit_recovery.get(
                        'generation_budget'
                    )
                    if isinstance(retry_budget, Mapping):
                        (
                            raw_audio,
                            chunk_content_type,
                            chunk_integrity,
                            retry_attempt,
                        ) = synthesize_chunk_attempt(
                            chunk_text,
                            source_sha256=chunk_source_sha256,
                            attempt_index=2,
                            attempt_role='generation_limit_recovery',
                            attempt_budget=retry_budget,
                        )
                        backend_call_count += 1
                        recovery_attempt_count += 1
                        terminal_budget = dict(retry_budget)
                        attempts.append(retry_attempt)
                        chunk_passed = bool(
                            str(
                                chunk_integrity.get('status') or ''
                            ).strip().lower()
                            == 'passed'
                            and chunk_integrity.get(
                                'materialization_eligible'
                            )
                            is True
                        )
                        generation_limit_recovery = {
                            **generation_limit_recovery,
                            'status': 'passed' if chunk_passed else 'failed',
                            'retry_count': 1,
                            'selected_attempt_index': 2,
                            'terminal_reason_code': str(
                                chunk_integrity.get('reason_code')
                                or 'TTS_AUDIO_CHUNK_INTEGRITY_FAILED'
                            ).strip(),
                        }
            attempts[-1]['selected'] = True
            chunk_record = {
                key: value
                for key, value in {
                    'index': raw_chunk.get('index'),
                    'source_span_start': raw_chunk.get('source_span_start'),
                    'source_span_end': raw_chunk.get('source_span_end'),
                    'text_sha256': chunk_source_sha256,
                    'estimated_speech_seconds': raw_chunk.get(
                        'estimated_speech_seconds'
                    ),
                    'status': (
                        'recovered'
                        if chunk_passed and len(attempts) > 1
                        else 'passed'
                        if chunk_passed
                        else 'failed'
                    ),
                    'generation_budget': terminal_budget,
                    'audio_size_bytes': len(raw_audio),
                    'audio_sha256': (
                        hashlib.sha256(raw_audio).hexdigest()
                        if raw_audio
                        else None
                    ),
                    'content_type': chunk_content_type,
                    'integrity_evidence': chunk_integrity,
                    'attempt_count': len(attempts),
                    'recovery_attempt_count': max(0, len(attempts) - 1),
                    'attempts': attempts,
                    'generation_limit_recovery': generation_limit_recovery,
                }.items()
                if value not in (None, '', [], {})
            }
            chunk_diagnostics.append(chunk_record)
            if not chunk_passed:
                chunk_failure_reason = str(
                    chunk_integrity.get('reason_code')
                    or 'TTS_AUDIO_CHUNK_INTEGRITY_FAILED'
                ).strip()
                chunk_failure_bytes = raw_audio
                chunk_failure_content_type = chunk_content_type
                break
            passed_chunk_count += 1
            if len(attempts) > 1:
                recovered_chunk_count += 1
            chunk_audio_bytes.append(raw_audio)

        join_evidence: dict[str, Any] = {}
        joined_audio = b''
        if not chunk_failure_reason:
            try:
                joined_audio, join_evidence = join_pcm_wav_bytes(chunk_audio_bytes)
            except ValueError as exc:
                chunk_failure_reason = 'TTS_AUDIO_CHUNK_JOIN_FAILED'
                chunk_failure_bytes = chunk_audio_bytes[0] if chunk_audio_bytes else b''
                chunk_failure_content_type = 'audio/wav'
                join_evidence = {
                    'kind': 'fruth.pcm_wav_join',
                    'version': 1,
                    'status': 'failed',
                    'reason_code': chunk_failure_reason,
                    'error_type': type(exc).__name__,
                }
        chunking_evidence = {
            key: value
            for key, value in {
                **{
                    key: value
                    for key, value in chunk_plan.items()
                    if key != 'chunks'
                },
                'status': 'failed' if chunk_failure_reason else 'passed',
                'chunks': chunk_diagnostics,
                'completed_chunk_count': len(chunk_diagnostics),
                'attempted_chunk_count': len(chunk_diagnostics),
                'passed_chunk_count': passed_chunk_count,
                'backend_call_count': backend_call_count,
                'generation_limit_recovery_attempt_count': (
                    recovery_attempt_count
                ),
                'recovered_chunk_count': recovered_chunk_count,
                'failed_chunk_index': (
                    chunk_diagnostics[-1].get('index')
                    if chunk_failure_reason and chunk_diagnostics
                    else None
                ),
                'failure_reason_code': chunk_failure_reason or None,
                'join_evidence': join_evidence or None,
                'joined_audio_size_bytes': len(joined_audio) if joined_audio else None,
                'joined_audio_sha256': (
                    hashlib.sha256(joined_audio).hexdigest()
                    if joined_audio
                    else None
                ),
            }.items()
            if value not in (None, '', [], {})
        }
        if chunk_failure_reason:
            result = {
                'audio_bytes': chunk_failure_bytes,
                'content_type': chunk_failure_content_type,
                'result': {
                    'bytes': len(chunk_failure_bytes),
                    'diagnostic_only': True,
                    'reason_code': chunk_failure_reason,
                },
            }
        else:
            result = {
                'audio_bytes': joined_audio,
                'content_type': 'audio/wav',
                'result': {
                    'bytes': len(joined_audio),
                    'chunk_count': len(chunk_audio_bytes),
                    'joined_pcm_wav': True,
                },
            }
    else:
        speech_kwargs = dict(base_speech_kwargs)
        if generation_budget:
            speech_kwargs['max_tokens'] = generation_budget['max_tokens']
        result = ops['mlx_audio_speech'](
            ctx.port,
            ctx.model_name,
            prompt,
            **speech_kwargs,
        )
        initial_audio_candidate = bytes(result.get('audio_bytes') or b'')
        if (
            is_qwen3_tts
            and tts_model_type
            in _QWEN3_TTS_GENERATION_LIMIT_RECOVERY_MODEL_TYPES
            and resolved_response_format in {'wav', 'wave', 'x-wav'}
            and isinstance(generation_budget, Mapping)
            and str(
                generation_budget.get('generation_scope') or ''
            ).strip().lower()
            == 'single_sequence'
            and len(initial_audio_candidate) >= 12
            and initial_audio_candidate[:4] == b'RIFF'
            and initial_audio_candidate[8:12] == b'WAVE'
        ):
            initial_audio = initial_audio_candidate
            initial_content_type = str(
                result.get('content_type') or 'audio/wav'
            )
            initial_integrity = _tts_audio_bytes_integrity_evidence(
                initial_audio,
                prompt,
                source_sha256=str(
                    semantic_source.get('tts_source_text_sha256') or ''
                ).strip(),
                generation_budget=generation_budget,
                tts_model_type=tts_model_type,
            )
            if tts_audio_has_qwen_generation_limit_exhaustion(
                initial_integrity,
                generation_budget=generation_budget,
            ):
                recovery = _build_qwen3_tts_generation_limit_recovery(
                    generation_budget,
                    integrity_evidence=initial_integrity,
                )
                retry_budget = recovery.get('generation_budget')
                if (
                    recovery.get('applied') is True
                    and isinstance(retry_budget, Mapping)
                ):
                    retry_kwargs = dict(base_speech_kwargs)
                    retry_kwargs['max_tokens'] = int(
                        retry_budget.get('max_tokens') or 0
                    )
                    retry_result = ops['mlx_audio_speech'](
                        ctx.port,
                        ctx.model_name,
                        prompt,
                        **retry_kwargs,
                    )
                    retry_audio = bytes(
                        retry_result.get('audio_bytes') or b''
                    )
                    retry_content_type = str(
                        retry_result.get('content_type') or 'audio/wav'
                    )
                    retry_integrity = _tts_audio_bytes_integrity_evidence(
                        retry_audio,
                        prompt,
                        source_sha256=str(
                            semantic_source.get(
                                'tts_source_text_sha256'
                            )
                            or ''
                        ).strip(),
                        generation_budget=retry_budget,
                        tts_model_type=tts_model_type,
                    )
                    retry_passed = bool(
                        str(
                            retry_integrity.get('status') or ''
                        ).strip().lower()
                        == 'passed'
                        and retry_integrity.get(
                            'materialization_eligible'
                        )
                        is True
                    )
                    initial_attempt = {
                        'attempt_index': 1,
                        'role': 'initial',
                        'generation_budget': dict(generation_budget),
                        'audio_size_bytes': len(initial_audio),
                        'audio_sha256': (
                            hashlib.sha256(initial_audio).hexdigest()
                            if initial_audio
                            else None
                        ),
                        'content_type': initial_content_type,
                        'integrity_evidence': initial_integrity,
                        'selected': False,
                    }
                    retry_attempt = {
                        'attempt_index': 2,
                        'role': 'generation_limit_recovery',
                        'generation_budget': dict(retry_budget),
                        'audio_size_bytes': len(retry_audio),
                        'audio_sha256': (
                            hashlib.sha256(retry_audio).hexdigest()
                            if retry_audio
                            else None
                        ),
                        'content_type': retry_content_type,
                        'integrity_evidence': retry_integrity,
                        'selected': True,
                    }
                    single_sequence_recovery_evidence = {
                        **recovery,
                        'status': 'passed' if retry_passed else 'failed',
                        'retry_count': 1,
                        'attempt_count': 2,
                        'selected_attempt_index': 2,
                        'terminal_reason_code': str(
                            retry_integrity.get('reason_code')
                            or 'TTS_AUDIO_INTEGRITY_UNAVAILABLE'
                        ).strip(),
                        'attempts': [initial_attempt, retry_attempt],
                    }
                    generation_budget = dict(retry_budget)
                    result = dict(retry_result)

    saved_audio_path = ops['persist_audio_bytes_locally'](
        result.get('audio_bytes'),
        ctx.model_name,
        response_format=ctx.response_format,
        content_type=result.get('content_type'),
    )
    if not saved_audio_path:
        return {'error': 'TTS audio could not be saved locally.'}, 500

    integrity_evidence = build_tts_audio_integrity_evidence(
        saved_audio_path,
        prompt,
        source_sha256=semantic_source.get('tts_source_text_sha256'),
        generation_budget=generation_budget,
        model_family='qwen3_tts' if is_qwen3_tts else None,
        tts_model_type=tts_model_type or None,
    )
    if chunking_evidence:
        integrity_evidence = dict(integrity_evidence)
        integrity_evidence['chunking_evidence'] = chunking_evidence
    if single_sequence_recovery_evidence:
        integrity_evidence = dict(integrity_evidence)
        integrity_evidence['generation_limit_recovery'] = (
            single_sequence_recovery_evidence
        )
    if chunk_failure_reason:
        integrity_evidence = dict(integrity_evidence)
        defect_codes = [
            str(item).strip()
            for item in (integrity_evidence.get('defect_codes') or [])
            if str(item).strip()
        ]
        if chunk_failure_reason not in defect_codes:
            defect_codes.append(chunk_failure_reason)
        integrity_evidence.update(
            {
                'status': 'failed',
                'reason_code': chunk_failure_reason,
                'materialization_eligible': False,
                'defect_codes': defect_codes,
                'diagnostic_scope': 'failed_qwen_chunk',
            }
        )

    payload = {
        'instance_id': ctx.instance_id,
        'capability': ctx.capability,
        'mode': 'text_to_speech',
        'content': 'Audio generated.',
        'saved_audio_path': saved_audio_path,
        'audio_mimetype': result.get('content_type'),
        'result': result.get('result'),
        'tts_semantic_source': semantic_source,
        'tts_audio_integrity_evidence': integrity_evidence,
    }
    if effective_lang_code:
        payload['lang_code'] = effective_lang_code
    if lang_code_source:
        payload['lang_code_source'] = lang_code_source
    if effective_voice:
        payload['voice'] = effective_voice
    if ctx.instruct:
        payload['instruct'] = ctx.instruct
    if ctx.response_format:
        payload['response_format'] = ctx.response_format
    if generation_budget:
        payload['tts_generation_budget'] = generation_budget
    if tts_model_type:
        payload['tts_model_type'] = tts_model_type
    if sampling_profile:
        payload['tts_sampling_profile'] = sampling_profile
    return payload, 200


def _run_image_generation(
    ctx: InferContext,
    artifacts: InferArtifacts,
    ops: Dict[str, Callable[..., Any]],
) -> Tuple[dict, int]:
    if not ctx.prompt:
        return {'error': 'image_generation requires a text prompt.'}, 400
    has_reference_image = bool(artifacts.image_b64)
    try:
        adapter = select_image_adapter(
            ctx.backend, ctx.backend_package, ctx.backend_metadata,
            editing=has_reference_image,
        )
    except ValueError as exc:
        return {'error': str(exc)}, 400
    if ctx.image_steps is not None and not supports_image_steps(
        ctx.backend, ctx.backend_package, ctx.backend_metadata,
    ):
        return {'error': 'Selected instance does not support image steps.'}, 400
    if adapter == 'mlx_vlm_images_v1':
        if ctx.image_steps is not None:
            try:
                validate_image_steps(ctx.image_steps, ctx.backend_metadata)
            except ValueError as exc:
                return {'error': str(exc)}, 400
        request = ImageRequest(
            model=ctx.request_model or ctx.model_name, prompt=ctx.prompt,
            width=ctx.image_width, height=ctx.image_height, seed=ctx.image_seed,
            reference_b64=artifacts.image_b64, timeout_sec=ctx.infer_timeout_sec,
            steps=ctx.image_steps,
        )
        try:
            generated = ops['mlx_vlm_image_request'](ctx.port, request)
        except ImageAdapterError as exc:
            return {'error': str(exc)}, 502
        except ValueError as exc:
            return {'error': str(exc)}, 400
        saved_path = ops['persist_image_data_url_locally'](generated['image_data_url'], ctx.model_name)
        if not saved_path:
            return {'error': 'Generated image could not be persisted.'}, 502
        return {
            'instance_id': ctx.instance_id, 'capability': ctx.capability,
            'mode': 'image_generation_edit' if has_reference_image else 'image_generation',
            'content': 'Image generated.', 'image_data_url': generated['image_data_url'],
            'saved_image_path': saved_path, 'seed': generated['seed'],
            'reference_image_count': 1 if has_reference_image else 0,
            'reference_image_kind': artifacts.file_kind if has_reference_image else None,
            'image_execution': generated['image_execution'],
            'result': {'image_execution': generated['image_execution']},
        }, 200
    data_out: dict[str, Any] = {}
    saved_image_path = None
    image_data_url = None

    if not has_reference_image:
        image_data_url = ops['ollama_openai_image_generation'](
            ctx.port,
            ctx.model_name,
            ctx.prompt,
            width=ctx.image_width,
            height=ctx.image_height,
            seed=ctx.image_seed,
            timeout_sec=ctx.infer_timeout_sec,
        )
    if not image_data_url:
        data_out = ops['ollama_generate'](
            ctx.port,
            ctx.model_name,
            ctx.prompt,
            images=[artifacts.image_b64] if artifacts.image_b64 else None,
            timeout_sec=ctx.infer_timeout_sec,
            options={
                key: value
                for key, value in (
                    ('width', ctx.image_width),
                    ('height', ctx.image_height),
                    ('seed', ctx.image_seed),
                )
                if value is not None
            } or None,
            allow_port_fallback=False,
        )
        saved_image_path = ops['extract_saved_image_path_from_generate_output'](data_out)
        image_data_url = ops['extract_image_data_url_from_generate_output'](data_out)
    if image_data_url and not saved_image_path:
        saved_image_path = ops['persist_image_data_url_locally'](image_data_url, ctx.model_name)
    content = ops['extract_generate_content'](data_out)
    image_seed = None
    extract_seed = ops.get('extract_generate_seed')
    if callable(extract_seed):
        image_seed = extract_seed(data_out)
    if not content:
        if image_data_url:
            content = 'Image generated.'
        else:
            content = (
                'Image request completed, but no inline image payload was returned. '
                'Check Ollama server logs/CLI output for saved image path.'
            )
    return (
        {
            'instance_id': ctx.instance_id,
            'capability': ctx.capability,
            'mode': 'image_generation_edit' if has_reference_image else 'image_generation',
            'content': content,
            'image_data_url': image_data_url,
            'saved_image_path': saved_image_path,
            'seed': image_seed,
            'image_execution': {
                'adapter': adapter, 'requested_seed': ctx.image_seed,
                'reported_seed': image_seed,
            },
            'reference_image_count': 1 if has_reference_image else 0,
            'reference_image_kind': artifacts.file_kind if has_reference_image else None,
            'result': data_out,
        },
        200,
    )


def _run_vision_analysis(
    ctx: InferContext,
    artifacts: InferArtifacts,
    ops: Dict[str, Callable[..., Any]],
) -> Tuple[dict, int]:
    if artifacts.file_kind == 'pdf':
        return _run_pdf_vision_analysis(ctx, artifacts, ops)

    if not artifacts.image_b64 and not ctx.prompt:
        return {'error': 'For vision_analysis, provide an image file, PDF, or prompt.'}, 400

    effective_prompt = _effective_vision_prompt(ctx)
    # This receipt describes the bytes actually handed to the backend, not a
    # provider claim that it saw an image. PDF recovery has a separate contract.
    input_evidence = {}
    if artifacts.image_b64 and artifacts.file_kind == 'image':
        encoded_image = artifacts.image_b64
        if encoded_image.startswith('data:'):
            encoded_image = encoded_image.split(',', 1)[-1]
        try:
            image_bytes = base64.b64decode(encoded_image, validate=True)
        except ValueError:
            image_bytes = b''
        if image_bytes:
            input_evidence = {
                'kind': 'fruth.vision_input_evidence',
                'version': 1,
                'authority': 'runtime_vision_image_dispatch',
                'status': 'supplied',
                'instance_id': ctx.instance_id,
                'image_sha256': hashlib.sha256(image_bytes).hexdigest(),
                'size_bytes': len(image_bytes),
            }
        del image_bytes
    if ctx.backend in {'mlx', 'llama_cpp', 'apple_fm', 'apple_pcc'}:
        mlx_out = _run_backend_chat_completion(
            ctx,
            ops,
            [_build_mlx_multimodal_user_message(effective_prompt, artifacts.image_b64)],
            timeout_sec=ctx.infer_timeout_sec,
        )
        return (
            {
                'instance_id': ctx.instance_id,
                'capability': ctx.capability,
                'mode': 'vision_analysis',
                'content': mlx_out.get('content', ''),
                'result': mlx_out.get('result'),
                'vision_input_evidence': input_evidence,
                **({'pcc_execution': mlx_out['content'].pcc_execution}
                   if ctx.backend == 'apple_pcc' and getattr(mlx_out.get('content'), 'pcc_execution', None) else {}),
            },
            200,
        )

    model_name_lower = str(ctx.model_name or '').lower()
    if artifacts.image_b64 and 'deepseek-ocr' in model_name_lower:
        ocr_content, ocr_error = ops['ocr_image_with_deepseek'](
            port=ctx.port,
            model_name=ctx.model_name,
            image_b64=artifacts.image_b64,
            user_prompt=ctx.prompt,
            timeout_sec=ctx.infer_timeout_sec,
        )
        if ocr_content:
            final_content = ocr_content
            if ctx.prompt and not ops['is_generic_ocr_instruction_prompt'](ctx.prompt):
                try:
                    refine_prompt = (
                        'Apply the user instruction to the OCR result below.\n'
                        'Keep facts faithful to OCR output.\n\n'
                        f'User instruction:\n{ctx.prompt}\n\n'
                        f'[OCR markdown]\n{ocr_content}'
                    )
                    refine_out = ops['ollama_generate'](
                        ctx.port,
                        ctx.model_name,
                        refine_prompt,
                        timeout_sec=min(ctx.infer_timeout_sec, 900),
                        max_retries=1,
                        allow_port_fallback=False,
                    )
                    refined = ops['clean_ocr_output_text'](ops['extract_generate_content'](refine_out))
                    if refined and not ops['looks_like_ocr_prompt_echo'](refined, user_hint=ctx.prompt):
                        final_content = refined
                except Exception as exc:  # noqa: BLE001
                    logging.info('Image OCR refinement skipped: %s', exc)

            payload = {
                'instance_id': ctx.instance_id,
                'capability': ctx.capability,
                'mode': 'vision_analysis_ocr_image',
                'content': final_content,
                'vision_input_evidence': input_evidence,
            }
            if ocr_error:
                payload['warnings'] = [ocr_error]
            return payload, 200
        if ocr_error:
            logging.warning('DeepSeek image OCR fallback to generic mode: %s', ocr_error)

    data_out = ops['ollama_generate'](
        ctx.port,
        ctx.model_name,
        effective_prompt,
        images=[artifacts.image_b64] if artifacts.image_b64 else None,
        timeout_sec=ctx.infer_timeout_sec,
    )
    return (
        {
            'instance_id': ctx.instance_id,
            'capability': ctx.capability,
            'mode': 'vision_analysis',
            'content': ops['extract_generate_content'](data_out),
            'result': data_out,
            'vision_input_evidence': input_evidence,
        },
        200,
    )


def _run_pdf_vision_analysis(
    ctx: InferContext,
    artifacts: InferArtifacts,
    ops: Dict[str, Callable[..., Any]],
) -> Tuple[dict, int]:
    effective_prompt = _effective_vision_prompt(ctx)
    image_tool_mode = str(ctx.ocr_mode or '').strip().lower()
    native_tool_mode = (
        image_tool_mode if ctx.backend == 'apple_fm' and image_tool_mode in APPLE_FM_IMAGE_TOOL_MODES else None
    )
    phase_system_prompt = (
        str(getattr(ctx, 'phase_system_prompt', None) or '').strip() if ctx.capability == 'chat' else ''
    )
    if ctx.backend in {'mlx', 'llama_cpp', 'apple_fm', 'apple_pcc'}:
        if artifacts.text_from_file and not native_tool_mode:
            mlx_out = _run_backend_chat_completion(
                ctx,
                ops,
                [
                    {
                        'role': 'user',
                        'content': (
                            f'{effective_prompt}\n\n'
                            '[PDF extracted text]\n'
                            f'{artifacts.text_from_file}'
                        ),
                    }
                ],
                timeout_sec=ctx.infer_timeout_sec,
            )
            content_text = mlx_out.get('content', '')
            saved_source_text_path = ops['persist_text_markdown_locally'](
                artifacts.text_from_file,
                model_name=ctx.model_name,
                source_file_name=artifacts.file_name,
                mode='vision_analysis_pdf_text_source',
            )
            saved_text_path = ops['persist_text_markdown_locally'](
                content_text,
                model_name=ctx.model_name,
                source_file_name=artifacts.file_name,
                mode='vision_analysis_pdf_text',
            )
            response_content, content_truncated = _build_pdf_inline_response_content(
                content_text,
                warnings=artifacts.pdf_warnings,
                max_inline_chars=ops['max_pdf_inline_response_chars'],
            )
            payload = {
                'instance_id': ctx.instance_id,
                'capability': ctx.capability,
                'mode': 'vision_analysis_pdf_text',
                'content': response_content,
                'pdf_source': 'text_layer',
                'pdf_total_pages': artifacts.pdf_total_pages or None,
                'pdf_processed_pages': None,
                'warnings': artifacts.pdf_warnings,
                'saved_text_path': saved_text_path,
                'saved_source_text_path': saved_source_text_path,
                'content_truncated': content_truncated,
                'full_content_chars': len(content_text),
                'inline_content_chars': len(response_content),
                'result': mlx_out.get('result'),
            }
            ops['log_pdf_infer_event'](
                instance_id=ctx.instance_id,
                model_name=ctx.model_name,
                backend=ctx.backend,
                capability=ctx.capability,
                prompt=ctx.user_prompt,
                file_name=artifacts.file_name,
                file_sha256=artifacts.file_sha256,
                status='ok',
                mode=payload['mode'],
                content=payload['content'],
                warnings=artifacts.pdf_warnings,
                pdf_source='text_layer',
                pdf_total_pages=artifacts.pdf_total_pages or None,
                pdf_processed_pages=None,
                artifact_path=saved_text_path,
            )
            return payload, 200

        page_results = []
        processed_pages = 0
        total_pages = artifacts.pdf_total_pages or len(artifacts.pdf_page_images)
        tool_evidence = {
            'kind': 'fruth.apple_fm_pdf_tool_evidence', 'version': 1,
            'instance_id': ctx.instance_id, 'mode': native_tool_mode,
            'source_pdf_sha256': artifacts.file_sha256,
            'pdf_total_pages': total_pages, 'pages': [],
        } if native_tool_mode else None
        for idx, page_image_b64 in enumerate(artifacts.pdf_page_images, start=1):
            if native_tool_mode:
                try:
                    content, evidence = run_apple_fm_image_tool(
                        mode=native_tool_mode, image_b64=page_image_b64,
                        instance_id=ctx.instance_id, timeout_sec=ctx.pdf_page_timeout_sec,
                    )
                except (ValueError, AppleFMImageToolError) as exc:
                    return {
                        'error': f'PDF page {idx}: {exc}',
                        'instance_id': ctx.instance_id, 'capability': ctx.capability,
                        'mode': f'{native_tool_mode}_pdf',
                        'pdf_source': 'rendered_pages', 'pdf_total_pages': total_pages,
                        'pdf_processed_pages': processed_pages,
                        'warnings': artifacts.pdf_warnings,
                        'apple_fm_image_tool_evidence': tool_evidence,
                    }, 400 if isinstance(exc, ValueError) else 502
                tool_evidence['pages'].append({'page_index': idx, 'evidence': evidence})
                if evidence['result']['empty']:
                    content = 'No text detected.' if native_tool_mode == 'apple_ocr' else 'No barcodes detected.'
            else:
                messages = [
                    _build_mlx_multimodal_user_message(
                        f'{effective_prompt}\n\nPage {idx} of {total_pages}.',
                        page_image_b64,
                    )
                ]
                if phase_system_prompt:
                    messages.insert(0, {'role': 'system', 'content': phase_system_prompt})
                try:
                    mlx_out = _run_backend_chat_completion(
                        ctx,
                        ops,
                        messages,
                        timeout_sec=ctx.pdf_page_timeout_sec,
                    )
                except (
                    ops['request_timeout_error'], ops['request_connection_error'],
                    ops['request_exception_error'], AppleFMTransportError,
                ) as exc:
                    # Keep the failed page and completed coverage at the boundary
                    # where they are known. Refusals never retry or switch mode.
                    status_code = 502
                    if isinstance(exc, ops['request_timeout_error']):
                        status_code = 504
                        details = (
                            'Timed out while waiting for the model request. '
                            'The model process may still be running locally. '
                            'Use smaller PDF chunks or increase infer_timeout_sec/pdf_page_timeout_sec.'
                        )
                    elif isinstance(exc, ops['request_connection_error']):
                        status_code = 503
                        details = f'The connection to the model instance was interrupted ({exc}).'
                    else:
                        details = str(exc)
                        response = getattr(exc, 'response', None)
                        if response is not None:
                            try:
                                body = response.json()
                                if isinstance(body, dict):
                                    error = body.get('error') or body.get('message')
                                    if isinstance(error, dict):
                                        error = error.get('message') or error.get('code')
                                    details = str(error or details)
                            except (ValueError, TypeError):
                                details = str(getattr(response, 'text', '') or details)[:300]
                    error_message = f'PDF page {idx} of {total_pages}: {details}'
                    mode = 'vision_analysis_pdf_scan'
                    ops['log_pdf_infer_event'](
                        instance_id=ctx.instance_id, model_name=ctx.model_name,
                        backend=ctx.backend, capability=ctx.capability,
                        prompt=ctx.user_prompt, file_name=artifacts.file_name,
                        file_sha256=artifacts.file_sha256, status='error', mode=mode,
                        error=error_message, warnings=artifacts.pdf_warnings,
                        pdf_source='rendered_pages', pdf_total_pages=total_pages,
                        pdf_processed_pages=processed_pages,
                    )
                    return {
                        'error': error_message, 'instance_id': ctx.instance_id,
                        'capability': ctx.capability, 'mode': mode,
                        'pdf_source': 'rendered_pages', 'pdf_total_pages': total_pages,
                        'pdf_processed_pages': processed_pages, 'warnings': artifacts.pdf_warnings,
                    }, status_code
                content = str(mlx_out.get('content') or '').strip()
            if content:
                processed_pages += 1
            else:
                artifacts.pdf_warnings.append(f'Page {idx}: the vision model returned no text.')
                content = '[No text returned by the vision model.]'
            page_results.append(f"[Page {idx}]\n{content}")

        if not processed_pages:
            return (
                {
                    'error': 'The PDF was processed, but the vision model returned no text.',
                    'pdf_total_pages': total_pages, 'pdf_processed_pages': 0,
                    'warnings': artifacts.pdf_warnings,
                },
                502,
            )

        final_content = '\n\n---\n\n'.join(page_results)
        mode = f'{native_tool_mode}_pdf' if native_tool_mode else 'vision_analysis_pdf_scan'
        saved_text_path = ops['persist_text_markdown_locally'](
            final_content,
            model_name=ctx.model_name,
            source_file_name=artifacts.file_name,
            mode=mode,
        )
        response_content, content_truncated = _build_pdf_inline_response_content(
            final_content,
            warnings=artifacts.pdf_warnings,
            max_inline_chars=ops['max_pdf_inline_response_chars'],
        )
        payload = {
            'instance_id': ctx.instance_id,
            'capability': ctx.capability,
            'mode': mode,
            'content': response_content,
            'pdf_source': 'rendered_pages',
            'pdf_total_pages': total_pages,
            'pdf_processed_pages': processed_pages,
            'warnings': artifacts.pdf_warnings,
            'saved_text_path': saved_text_path,
            'content_truncated': content_truncated,
            'full_content_chars': len(final_content),
            'inline_content_chars': len(response_content),
        }
        if tool_evidence is not None:
            payload['apple_fm_image_tool_evidence'] = tool_evidence
        ops['log_pdf_infer_event'](
            instance_id=ctx.instance_id,
            model_name=ctx.model_name,
            backend=ctx.backend,
            capability=ctx.capability,
            prompt=ctx.user_prompt,
            file_name=artifacts.file_name,
            file_sha256=artifacts.file_sha256,
            status='ok',
            mode=payload['mode'],
            content=final_content,
            warnings=artifacts.pdf_warnings,
            pdf_source='rendered_pages',
            pdf_total_pages=payload['pdf_total_pages'],
            pdf_processed_pages=payload['pdf_processed_pages'],
            artifact_path=saved_text_path,
        )
        return payload, 200
    if artifacts.text_from_file:
        pdf_prompt_payload = (
            f'{effective_prompt}\n\n'
            '[PDF extracted text]\n'
            f'{artifacts.text_from_file}'
        )
        data_out = ops['ollama_generate'](
            ctx.port,
            ctx.model_name,
            pdf_prompt_payload,
            timeout_sec=ctx.infer_timeout_sec,
        )
        content_text = ops['extract_generate_content'](data_out)
        saved_source_text_path = ops['persist_text_markdown_locally'](
            artifacts.text_from_file,
            model_name=ctx.model_name,
            source_file_name=artifacts.file_name,
            mode='vision_analysis_pdf_text_source',
        )
        saved_text_path = ops['persist_text_markdown_locally'](
            content_text,
            model_name=ctx.model_name,
            source_file_name=artifacts.file_name,
            mode='vision_analysis_pdf_text',
        )
        response_content, content_truncated = _build_pdf_inline_response_content(
            content_text,
            warnings=artifacts.pdf_warnings,
            max_inline_chars=ops['max_pdf_inline_response_chars'],
        )
        payload = {
            'instance_id': ctx.instance_id,
            'capability': ctx.capability,
            'mode': 'vision_analysis_pdf_text',
            'content': response_content,
            'pdf_source': 'text_layer',
            'pdf_total_pages': artifacts.pdf_total_pages or None,
            'pdf_processed_pages': None,
            'warnings': artifacts.pdf_warnings,
            'saved_text_path': saved_text_path,
            'saved_source_text_path': saved_source_text_path,
            'content_truncated': content_truncated,
            'full_content_chars': len(content_text),
            'inline_content_chars': len(response_content),
            'result': data_out,
        }
        ops['log_pdf_infer_event'](
            instance_id=ctx.instance_id,
            model_name=ctx.model_name,
            backend=ctx.backend,
            capability=ctx.capability,
            prompt=ctx.user_prompt,
            file_name=artifacts.file_name,
            file_sha256=artifacts.file_sha256,
            status='ok',
            mode=payload['mode'],
            content=payload['content'],
            warnings=artifacts.pdf_warnings,
            pdf_source='text_layer',
            pdf_total_pages=artifacts.pdf_total_pages or None,
            pdf_processed_pages=None,
            artifact_path=saved_text_path,
        )
        return payload, 200

    page_results_by_number: dict[int, str] = {}
    page_errors: dict[int, str] = {}
    total_for_prompt = artifacts.pdf_total_pages or len(artifacts.pdf_page_images)
    if phase_system_prompt:
        effective_prompt = f'{phase_system_prompt}\n\n{effective_prompt}'
    for idx, page_image_b64 in enumerate(artifacts.pdf_page_images, start=1):
        page_content, page_error = ops['ocr_pdf_page_with_ollama'](
            port=ctx.port,
            model_name=ctx.model_name,
            base_prompt=effective_prompt,
            page_index=idx,
            total_pages=total_for_prompt,
            image_b64=page_image_b64,
            timeout_sec=ctx.pdf_page_timeout_sec,
        )
        if page_content:
            page_results_by_number[idx] = page_content
        elif page_error:
            page_errors[idx] = page_error

    def render_retry(**controls):
        from fruth_core.pdf_preparation import PdfPreparationError
        try:
            return ops['render_single_pdf_page_to_base64'](artifacts.temp_path, **controls)
        except PdfPreparationError as exc:
            exc.pdf_evidence = {
                'pdf_source': 'rendered_pages', 'pdf_total_pages': total_for_prompt,
                'pdf_processed_pages': len(page_results_by_number),
                'warnings': list(artifacts.pdf_warnings),
            }
            raise

    crop_retry_margin_ratio = 0.04
    if page_errors and artifacts.temp_path and artifacts.pdf_render_dpi >= 300:
        failed_pages = sorted(page_errors.keys())
        logging.info(
            'Retrying PDF OCR for failed pages=%s with border-crop margin=%.2f (dpi=%s)',
            failed_pages,
            crop_retry_margin_ratio,
            artifacts.pdf_render_dpi,
        )
        crop_recovered_count = 0
        for page_number in list(failed_pages):
            retry_b64 = render_retry(
                page_index=page_number - 1,
                dpi=artifacts.pdf_render_dpi,
                max_image_side_px=ctx.pdf_max_image_side,
                crop_margin_ratio=crop_retry_margin_ratio,
            )
            if not retry_b64:
                continue
            page_content, page_error = ops['ocr_pdf_page_with_ollama'](
                port=ctx.port,
                model_name=ctx.model_name,
                base_prompt=effective_prompt,
                page_index=page_number,
                total_pages=total_for_prompt,
                image_b64=retry_b64,
                timeout_sec=ctx.pdf_page_timeout_sec,
            )
            if page_content:
                page_results_by_number[page_number] = page_content
                page_errors.pop(page_number, None)
                crop_recovered_count += 1
            elif page_error:
                page_errors[page_number] = f"{page_errors[page_number]} Crop retry failed: {page_error}"
        if crop_recovered_count:
            artifacts.pdf_warnings.append(
                f"{crop_recovered_count} page(s) were successfully recovered with border-crop retry ({int(crop_retry_margin_ratio * 100)}%)."
            )

    if page_errors and artifacts.temp_path and artifacts.pdf_page_retry_dpi < artifacts.pdf_render_dpi:
        failed_pages = sorted(page_errors.keys())
        logging.info(
            'Retrying PDF OCR for failed pages=%s with lower dpi=%s (initial_dpi=%s)',
            failed_pages,
            artifacts.pdf_page_retry_dpi,
            artifacts.pdf_render_dpi,
        )
        recovered_count = 0
        for page_number in list(failed_pages):
            retry_b64 = render_retry(
                page_index=page_number - 1,
                dpi=artifacts.pdf_page_retry_dpi,
                max_image_side_px=ctx.pdf_max_image_side,
                crop_margin_ratio=(crop_retry_margin_ratio if artifacts.pdf_render_dpi >= 300 else 0.0),
            )
            if not retry_b64:
                page_errors[page_number] = (
                    f"{page_errors[page_number]} Low-DPI rerender failed."
                )
                continue
            page_content, page_error = ops['ocr_pdf_page_with_ollama'](
                port=ctx.port,
                model_name=ctx.model_name,
                base_prompt=effective_prompt,
                page_index=page_number,
                total_pages=total_for_prompt,
                image_b64=retry_b64,
                timeout_sec=ctx.pdf_page_timeout_sec,
            )
            if page_content:
                page_results_by_number[page_number] = page_content
                page_errors.pop(page_number, None)
                recovered_count += 1
            elif page_error:
                page_errors[page_number] = f"{page_errors[page_number]} Retry failed: {page_error}"
        if recovered_count:
            artifacts.pdf_warnings.append(
                f"{recovered_count} page(s) were successfully recovered with reduced DPI ({artifacts.pdf_page_retry_dpi})."
            )

    if page_errors:
        ordered_errors = [page_errors[page_no] for page_no in sorted(page_errors.keys())]
        preview_errors = ordered_errors[:8]
        artifacts.pdf_warnings.extend(preview_errors)
        if len(ordered_errors) > len(preview_errors):
            artifacts.pdf_warnings.append(
                f"Additional page errors: {len(ordered_errors) - len(preview_errors)}"
            )

    page_results: list[str] = []
    for page_number in sorted(page_results_by_number.keys()):
        page_results.append(f"[Page {page_number}]\n{page_results_by_number[page_number]}")
    logging.info(
        'PDF OCR page loop completed: ok=%s failed=%s total=%s',
        len(page_results_by_number),
        len(page_errors),
        total_for_prompt,
    )

    if not page_results:
        all_timeout_like = bool(page_errors) and all(
            ('timeout' in message.lower()) or ('timed out' in message.lower())
            for message in page_errors.values()
        )
        error_message = 'The PDF was processed, but no OCR text was returned.'
        if page_errors:
            top_errors = '; '.join([page_errors[i] for i in sorted(page_errors.keys())[:3]])
            error_message = f'{error_message} Errors: {top_errors}'
        ops['log_pdf_infer_event'](
            instance_id=ctx.instance_id,
            model_name=ctx.model_name,
            backend=ctx.backend,
            capability=ctx.capability,
            prompt=ctx.user_prompt,
            file_name=artifacts.file_name,
            file_sha256=artifacts.file_sha256,
            status='error',
            mode='vision_analysis_pdf_scan',
            error=error_message,
            warnings=artifacts.pdf_warnings,
            pdf_source='rendered_pages',
            pdf_total_pages=artifacts.pdf_total_pages or len(artifacts.pdf_page_images),
            pdf_processed_pages=0,
        )
        return (
            {
                'error': error_message,
                'warnings': artifacts.pdf_warnings,
            },
            504 if all_timeout_like else 502,
        )

    joined_pages = '\n\n---\n\n'.join(page_results)
    final_content = joined_pages
    if ctx.pdf_synthesize and ctx.prompt and len(page_results) > 1:
        max_synthesis_pages = 12
        if len(page_results) > max_synthesis_pages:
            artifacts.pdf_warnings.append(
                f'Global synthesis skipped automatically for large batches ({len(page_results)} pages > {max_synthesis_pages}) '
                'to avoid long hangs/timeouts. Process in smaller chunks if you need one merged final narrative.'
            )
        else:
            synthesis_prompt = (
                f'User request:\n{ctx.prompt}\n\n'
                'Below are page-wise OCR/context notes from a PDF. '
                'Provide one consolidated final answer that covers the full document.\n\n'
                f'{joined_pages}'
            )
            synthesis_timeout_sec = max(120, min(int(ctx.infer_timeout_sec), 600))
            logging.info(
                'PDF synthesis request: pages=%s timeout_sec=%s prompt_chars=%s source_chars=%s',
                len(page_results),
                synthesis_timeout_sec,
                len(ctx.prompt),
                len(joined_pages),
            )
            try:
                synthesis_out = ops['ollama_generate'](
                    ctx.port,
                    ctx.model_name,
                    synthesis_prompt,
                    timeout_sec=synthesis_timeout_sec,
                )
                synthesized_content = ops['extract_generate_content'](synthesis_out).strip()
                if synthesized_content:
                    final_content = synthesized_content
                    logging.info('PDF synthesis completed: output_chars=%s', len(synthesized_content))
                else:
                    artifacts.pdf_warnings.append(
                        'Global synthesis returned empty output; keeping page-wise OCR result.'
                    )
            except ops['request_timeout_error']:
                artifacts.pdf_warnings.append(
                    f'Global synthesis timed out after {synthesis_timeout_sec}s; keeping page-wise OCR result.'
                )
            except ops['request_connection_error'] as exc:
                artifacts.pdf_warnings.append(
                    f'Global synthesis connection lost ({exc}); keeping page-wise OCR result.'
                )
            except ops['request_exception_error'] as exc:
                details = str(exc)
                if getattr(exc, 'response', None) is not None:
                    try:
                        payload = exc.response.json()
                        details = payload.get('error') or payload.get('message') or details
                    except Exception:  # noqa: BLE001
                        details = getattr(exc.response, 'text', details)[:260]
                artifacts.pdf_warnings.append(
                    f'Global synthesis failed ({details}); keeping page-wise OCR result.'
                )
            except Exception as exc:  # noqa: BLE001
                artifacts.pdf_warnings.append(
                    f'Global synthesis unexpected error ({exc}); keeping page-wise OCR result.'
                )
    else:
        if ctx.prompt and len(page_results) > 1:
            artifacts.pdf_warnings.append(
                'Global synthesis was skipped by default to avoid long timeouts. '
                'Set pdf_synthesize=true if you want a single merged answer in one pass.'
            )

    response_content, content_truncated = _build_pdf_inline_response_content(
        final_content,
        warnings=artifacts.pdf_warnings,
        max_inline_chars=ops['max_pdf_inline_response_chars'],
    )

    logging.info(
        'PDF OCR finalize begin: pages_ok=%s pages_failed=%s output_chars_full=%s output_chars_ui=%s warnings=%s',
        len(page_results_by_number),
        len(page_errors),
        len(final_content),
        len(response_content),
        len(artifacts.pdf_warnings),
    )

    payload = {
        'instance_id': ctx.instance_id,
        'capability': ctx.capability,
        'mode': 'vision_analysis_pdf_scan',
        'content': response_content,
        'pdf_source': 'rendered_pages',
        'pdf_total_pages': artifacts.pdf_total_pages or len(artifacts.pdf_page_images),
        'pdf_processed_pages': len(page_results_by_number),
        'warnings': artifacts.pdf_warnings,
        'content_truncated': content_truncated,
        'full_content_chars': len(final_content),
        'inline_content_chars': len(response_content),
    }
    payload['saved_text_path'] = ops['persist_text_markdown_locally'](
        final_content,
        model_name=ctx.model_name,
        source_file_name=artifacts.file_name,
        mode='vision_analysis_pdf_scan',
    )
    logging.info(
        'PDF OCR artifact persisted: path=%s',
        payload.get('saved_text_path') or 'none',
    )
    ops['log_pdf_infer_event'](
        instance_id=ctx.instance_id,
        model_name=ctx.model_name,
        backend=ctx.backend,
        capability=ctx.capability,
        prompt=ctx.user_prompt,
        file_name=artifacts.file_name,
        file_sha256=artifacts.file_sha256,
        status='ok',
        mode=payload['mode'],
        content=final_content,
        warnings=artifacts.pdf_warnings,
        pdf_source='rendered_pages',
        pdf_total_pages=payload['pdf_total_pages'],
        pdf_processed_pages=payload['pdf_processed_pages'],
        artifact_path=payload.get('saved_text_path'),
    )
    logging.info(
        'PDF OCR response ready: instance=%s pages=%s warnings=%s',
        ctx.instance_id,
        payload['pdf_processed_pages'],
        len(artifacts.pdf_warnings),
    )
    return payload, 200


def _build_mlx_multimodal_user_message(prompt: str, image_b64: Optional[str] = None) -> dict:
    text = str(prompt or '').strip()
    if not image_b64:
        return {'role': 'user', 'content': text}
    if str(image_b64).startswith('data:'):
        data_url = image_b64
    else:
        # Inspect only the signature, without decoding/re-encoding the full image.
        # Keep the existing PNG default for opaque legacy payloads; the backend
        # still owns image decoding and unsupported-format errors.
        mime = 'image/png'
        try:
            header = base64.b64decode(image_b64[:16], validate=True)
        except ValueError:
            header = b''
        if header.startswith(b'\xff\xd8\xff'):
            mime = 'image/jpeg'
        elif header.startswith((b'GIF87a', b'GIF89a')):
            mime = 'image/gif'
        elif header.startswith(b'RIFF') and header[8:12] == b'WEBP':
            mime = 'image/webp'
        elif header.startswith(b'BM'):
            mime = 'image/bmp'
        elif header.startswith((b'II*\x00', b'MM\x00*', b'II+\x00', b'MM\x00+')):
            mime = 'image/tiff'
        data_url = f'data:{mime};base64,{image_b64}'
    return {
        'role': 'user',
        'content': [
            {'type': 'input_text', 'text': text},
            {'type': 'input_image', 'image_url': data_url},
        ],
    }


def _run_chat_fallback(
    ctx: InferContext,
    artifacts: InferArtifacts,
    ops: Dict[str, Callable[..., Any]],
) -> Tuple[dict, int]:
    prompt = ctx.prompt
    phase_system_prompt = str(ctx.phase_system_prompt or '').strip()
    warnings = list(artifacts.pdf_warnings or [])
    if artifacts.text_from_file:
        file_content_prefix = '[Attached file content]'
        if artifacts.text_from_file_truncated:
            inline_bytes = int(artifacts.text_from_file_inline_bytes or 0)
            total_bytes = int(artifacts.text_from_file_total_bytes or 0)
            file_content_prefix = (
                '[Attached file content truncated to first '
                f'{inline_bytes} of {total_bytes} bytes; request more or use chunks if needed]'
            )
            warnings.append(
                f'Attached text file exceeded inline limit and was truncated to {inline_bytes} of {total_bytes} bytes.'
            )
        if prompt:
            prompt = f'{prompt}\n\n{file_content_prefix}\n{artifacts.text_from_file}'
        else:
            prompt = f'{file_content_prefix}\n{artifacts.text_from_file}'
    elif artifacts.file_kind == 'pdf' and artifacts.pdf_page_images:
        error_message = (
            'Detected a PDF without extractable text. '
            'Use a vision_analysis model (for example deepseek-ocr) for scanned PDFs.'
        )
        ops['log_pdf_infer_event'](
            instance_id=ctx.instance_id,
            model_name=ctx.model_name,
            backend=ctx.backend,
            capability=ctx.capability,
            prompt=ctx.user_prompt,
            file_name=artifacts.file_name,
            file_sha256=artifacts.file_sha256,
            status='error',
            mode='chat',
            error=error_message,
            warnings=warnings,
            pdf_source='rendered_pages',
            pdf_total_pages=artifacts.pdf_total_pages or len(artifacts.pdf_page_images),
            pdf_processed_pages=len(artifacts.pdf_page_images),
        )
        return {'error': error_message, 'warnings': warnings}, 400
    if artifacts.image_b64:
        if ctx.backend in {'mlx', 'llama_cpp', 'apple_fm', 'apple_pcc'}:
            messages = [
                _build_mlx_multimodal_user_message(
                    prompt or 'Describe the attached image.',
                    artifacts.image_b64,
                )
            ]
            if phase_system_prompt:
                messages.insert(
                    0,
                    {'role': 'system', 'content': phase_system_prompt},
                )
            mlx_out = _run_backend_chat_completion(
                ctx,
                ops,
                messages,
                timeout_sec=ctx.infer_timeout_sec,
            )
            return (
                {
                    'instance_id': ctx.instance_id,
                    'capability': ctx.capability,
                    'mode': 'chat_with_image',
                    'content': mlx_out.get('content', ''),
                    'warnings': warnings,
                    'result': mlx_out.get('result'),
                    **({'pcc_execution': mlx_out['content'].pcc_execution}
                       if ctx.backend == 'apple_pcc' and getattr(mlx_out.get('content'), 'pcc_execution', None) else {}),
                },
                200,
            )
        ollama_image_prompt = prompt or 'Describe the attached image.'
        if phase_system_prompt:
            ollama_image_prompt = (
                f'{phase_system_prompt}\n\n{ollama_image_prompt}'
            )
        data_out = ops['ollama_generate'](
            ctx.port,
            ctx.model_name,
            ollama_image_prompt,
            images=[artifacts.image_b64],
            timeout_sec=ctx.infer_timeout_sec,
        )
        return (
                {
                    'instance_id': ctx.instance_id,
                    'capability': ctx.capability,
                    'mode': 'chat_with_image',
                    'content': ops['extract_generate_content'](data_out),
                    'warnings': warnings,
                    'result': data_out,
                },
                200,
            )

    if not prompt:
        return {'error': 'No prompt was provided.'}, 400
    chat_messages = [{'role': 'user', 'content': prompt}]
    if phase_system_prompt:
        chat_messages.insert(
            0,
            {'role': 'system', 'content': phase_system_prompt},
        )
    if ctx.backend in {'mlx', 'llama_cpp', 'apple_fm', 'apple_pcc'}:
        chat_result = _run_backend_chat_completion(
            ctx,
            ops,
            chat_messages,
            timeout_sec=ctx.infer_timeout_sec,
        )
        content = chat_result.get('content', '')
    else:
        chat_result = ops['ollama_chat'](
            ctx.port,
            ctx.model_name,
            chat_messages,
            timeout_sec=ctx.infer_timeout_sec,
        )
        content = chat_result.get('content', '')
    payload = {
        'instance_id': ctx.instance_id,
        'capability': ctx.capability,
        'mode': 'chat',
        'content': content,
        'warnings': warnings,
    }
    if ctx.backend == 'apple_pcc' and getattr(content, 'pcc_execution', None):
        payload['pcc_execution'] = content.pcc_execution
    artifact_requests = [
        dict(item)
        for item in (ctx.text_artifact_requests or [])
        if isinstance(item, dict)
    ]
    if not artifact_requests:
        artifact_requests = detect_text_artifact_requests(
            ctx.user_prompt or ctx.prompt,
            source_available=bool(artifacts.text_from_file or artifacts.temp_path),
            source_extension=Path(artifacts.file_name or '').suffix,
            source_name=Path(artifacts.file_name or '').stem,
            source_path=(
                str(artifacts.temp_path)
                if isinstance(artifacts.temp_path, (str, Path))
                else None
            ),
        )
    persist_text_artifact = ops.get('persist_text_artifact_locally')
    materialization_content = content
    accept_artifact_output = ops.get('classify_text_artifact_output')
    if artifact_requests and callable(accept_artifact_output):
        # The server acceptance owner runs before the inner writer, rather than
        # rejecting control data only after Infer has already persisted it.
        acceptance = accept_artifact_output(content)
        materialization_content = str(acceptance.get('accepted_text') or '')
        payload['text_artifact_output_acceptance'] = {
            key: value for key, value in acceptance.items() if key != 'accepted_text'
        }
    artifact_payloads = extract_text_artifact_payloads(materialization_content, artifact_requests)
    if len(artifact_requests) > 1 and len(artifact_payloads) != len(artifact_requests):
        # A multi-file materialization is one output-set contract.  Do not
        # publish parser-accepted members before every requested identity is
        # present; Late Fill owns retry and final fulfillment truth.
        artifact_payloads = []
    saved_text_artifacts: list[dict[str, Any]] = []
    if artifact_payloads and persist_text_artifact:
        for artifact_payload in artifact_payloads:
            artifact_request = artifact_payload.get('artifact_request') if isinstance(artifact_payload, dict) else {}
            artifact_content = str((artifact_payload or {}).get('content') or '').strip()
            if not artifact_content or not isinstance(artifact_request, dict):
                continue
            saved_text_path = persist_text_artifact(
                artifact_content,
                model_name=ctx.model_name,
                source_name=artifact_request.get('source_name') or 'generated-text',
                mode='chat_text_artifact',
                extension=artifact_request.get('extension') or 'txt',
                target_path=artifact_request.get('target_path'),
            )
            if saved_text_path:
                saved_text_artifacts.append(
                    {
                        'path': saved_text_path,
                        'text_artifact_request': artifact_request,
                        'document_output_kind': 'document',
                    }
                )
    if saved_text_artifacts:
        first_artifact = saved_text_artifacts[0]
        payload['saved_text_path'] = first_artifact['path']
        payload['document_output_kind'] = 'document'
        payload['text_artifact_request'] = first_artifact.get('text_artifact_request')
        payload['saved_text_artifacts'] = saved_text_artifacts
        payload['text_artifact_requests'] = [
            item.get('text_artifact_request')
            for item in saved_text_artifacts
            if isinstance(item.get('text_artifact_request'), dict)
        ]
    if artifacts.file_kind == 'pdf':
        ops['log_pdf_infer_event'](
            instance_id=ctx.instance_id,
            model_name=ctx.model_name,
            backend=ctx.backend,
            capability=ctx.capability,
            prompt=ctx.user_prompt,
            file_name=artifacts.file_name,
            file_sha256=artifacts.file_sha256,
            status='ok',
            mode='chat',
            content=payload['content'],
            warnings=warnings,
            pdf_source='text_layer' if artifacts.text_from_file else None,
            pdf_total_pages=artifacts.pdf_total_pages or None,
            pdf_processed_pages=None,
        )
    return payload, 200
