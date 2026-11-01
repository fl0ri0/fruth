"""Canonical /api/responses request-runtime owners for Fruth."""

from __future__ import annotations

from fruth_server.terminal_repair_projection import TerminalRepairProjection

from fruth_server.graph_rebase_continuation import GraphRebaseContinuation
from fruth_server.graph_rebase_continuation import (
    _ACTIVE_LATE_FILL_STATUSES,
    _MAX_PARTIAL_GRAPH_REBASE_SUCCESSOR_DEPTH,
    _RESPONSE_TIME_GRAPH_REBASE_CANDIDATE_KEY,
    _RUNTIME_REBASE_ACTIONS,
    _RUNTIME_REBASE_OPEN_STATUSES,
    _RUNTIME_REBASE_STRUCTURAL_OPERATIONS,
    _SMALLER_REDRAW_SCOPES,
    _partial_graph_rebase_execution_keys,
    _partial_graph_rebase_parent_depth,
    _runtime_rebase_closure_evidence,
    _runtime_rebase_diff_summary,
    _runtime_rebase_has_structural_change,
    _runtime_rebase_late_fill_status,
    _runtime_rebase_scope_from_diff,
    _runtime_rebase_smaller_scope,
)

from fruth_server.graph_patch_continuation import GraphPatchContinuation
from fruth_server.graph_patch_continuation import (
    _FROZEN_GRAPH_PATCH_RESPONSE_STATES,
    _MAX_GRAPH_PATCH_SUCCESSOR_REOPEN_DEPTH,
    _compact_payload,
    _graph_patch_successor_keys,
    _graph_patch_successor_owed_scope,
    _graph_patch_successor_parent_depth,
)

from fruth_services.state_flow import observe_state, note as state_flow_note

from fruth_services.events import observe_call, observe_request

import copy
from dataclasses import dataclass
import hashlib
import json
import logging
from pathlib import Path
import re
from typing import Any, Mapping, Optional

from flask import Response, jsonify, request, stream_with_context

from helpers.model_capabilities import CAPABILITY_TEXT_TO_SPEECH
from helpers.session_controls import (
    normalize_reasoning_effort,
    validate_reasoning_effort_for_instance,
)
from fruth_services.artifact_contracts import execution_input_artifact_ref
from fruth_services.responses import capture_request_intent
from fruth_core.text_artifacts import detect_text_artifact_requests
from fruth_core.pdf_preparation import PdfPreparationError
from fruth_inference.request_phase_graph import build_request_phase_graph
from fruth_inference.execution_planner import resolve_internal_reasoning_effort
from fruth_server.repair_gate_runtime import classify_repair_execution_policy
from fruth_server.backend_transport_runtime import provider_failover_reason, provider_failure_prohibits_retry
from fruth_services.phase_output import attach_phase_output_acceptance, classify_phase_output_text, control_json_envelope_suspected, phase_output_is_graph_preparation, phase_output_defers_saved_file_materialization, phase_output_repair_notice, phase_output_repair_system_message, request_explicitly_allows_control_diagnostics
from fruth_services.enforced_policy import (
    build_enforced_policy_review,
    describe_enforced_policy_from_env,
    enforced_policy_allows_application,
)
from fruth_services.graph_repair import (
    apply_validated_graph_patch,
    apply_validated_graph_repair_patch,
    build_graph_patch_lifecycle,
    build_graph_repair_proposal_from_repair_gap,
    build_graph_repair_proposals_from_runtime_evidence,
    classify_surface_repair_actionability,
    describe_graph_repair_autonomy,
    describe_graph_repair_autonomy_from_env,
    normalize_graph_repair_autonomy,
    stable_graph_repair_graph_digest,
    validate_graph_repair_proposal,
)
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
from fruth_services.redraw_scope import build_redraw_scope_ladder_review
from fruth_services.tts_audio_integrity import (
    build_tts_audio_integrity_evidence,
)

_DIRECT_BATCH_VARIANT_ASPECT_RATIO_CYCLE = ('16:9', '9:16', '1:1', '4:3', '3:4', '3:2', '2:3')
# Includes the initial provider; each instance may be attempted only once.
PROVIDER_FAILOVER_MAX_ATTEMPTS = 4
_TRANSLATION_LANGUAGE_LABELS = {
    'de': 'German',
    'en': 'English',
    'es': 'Spanish',
    'fr': 'French',
    'it': 'Italian',
    'ja': 'Japanese',
    'ko': 'Korean',
    'pt': 'Portuguese',
    'ru': 'Russian',
    'zh': 'Chinese',
}
_DIRECT_BATCH_MATCHING_OUTPUT_RE = re.compile(
    r'\b(same image|same prompt|same scene|same subject|same animal|same character|identical|matching)\b',
    re.IGNORECASE,
)
_DIRECT_BATCH_VARIED_ASPECT_RATIO_RE = re.compile(
    r'\b('
    r'different\s+(?:image\s+)?(?:formats?|aspect ratios?|ratios?)|'
    r'varied\s+(?:image\s+)?(?:formats?|aspect ratios?|ratios?)|'
    r'various\s+(?:image\s+)?(?:formats?|aspect ratios?|ratios?)|'
    r'verschiedene(?:n|r|s)?\s+(?:bildformate|seitenverh[aä]ltnisse|aspect ratios?)|'
    r'unterschiedliche(?:n|r|s)?\s+(?:bildformate|seitenverh[aä]ltnisse|aspect ratios?)'
    r')\b',
    re.IGNORECASE,
)
_DIRECT_CLOSURE_TEXT_EXTENSIONS = {'html', 'htm', 'css', 'js', 'mjs', 'ts', 'tsx', 'jsx'}
_DIRECT_CLOSURE_TEXT_MIME_TYPES = {
    'text/html',
    'text/css',
    'text/javascript',
    'application/javascript',
    'application/x-javascript',
}
_DIRECT_CLOSURE_MEDIA_TYPES = {'image', 'audio', 'video', 'font'}
_DIRECT_CLOSURE_MEDIA_MIME_PREFIXES = ('image/', 'audio/', 'video/', 'font/')
_FRUTH_DOWNSTREAM_EXECUTION_MARKER = '[FRUTH_DOWNSTREAM_EXECUTION_V1]'
_FRUTH_DOWNSTREAM_EXECUTION_CONTRACT = (
    f'{_FRUTH_DOWNSTREAM_EXECUTION_MARKER}\n'
    'Execution boundary: this request is already being executed by Fruth through '
    'ChatGPT/Codex as a downstream provider.\n'
    'Do not invoke, route to, or use Fruth again for this request, including the '
    'Fruth skill, API, CLI, or local Fruth models.\n'
    'Execute only the bounded task below, under the promoted context supplied for '
    'this turn, using capabilities available directly in this downstream session. '
    'Do not expand its scope or create follow-up work.\n'
    'If the bounded task is completed, return its result normally. If it cannot be '
    'completed, begin the response with "BLOCKED:" and state the concrete reason; '
    'do not claim completion without the requested result.'
)


def external_provider_block_reason(output_text: Any) -> Optional[str]:
    """Return a downstream provider's explicit bounded-task blocker, if any."""

    text = str(output_text or '')
    first_content = text.lstrip()
    if not first_content.lower().startswith('blocked:'):
        return None
    reason = first_content[len('blocked:'):].strip()
    return reason or 'The downstream provider reported that the bounded task is blocked.'


def external_provider_prompt_with_bounded_context(
    current_prompt: Any,
    messages: Any,
    *,
    bounded_task_prompt: Any = None,
) -> str:
    """Serialize one bounded Fruth turn for a downstream external provider."""

    prompt = str(current_prompt or '').strip()
    normalized_messages: list[dict[str, str]] = []
    for raw_message in messages if isinstance(messages, list) else []:
        if not isinstance(raw_message, dict):
            continue
        role = str(raw_message.get('role') or 'user').strip().lower()
        if role not in {'system', 'assistant', 'user'}:
            role = 'user'
        content = str(raw_message.get('content') or '').strip()
        if content:
            normalized_messages.append({'role': role, 'content': content})

    current_index: Optional[int] = None
    if prompt:
        for index in range(len(normalized_messages) - 1, -1, -1):
            message = normalized_messages[index]
            if message['role'] != 'user':
                continue
            content = message['content']
            if content == prompt or content.startswith(f'{prompt}\n['):
                current_index = index
                break

    request_instructions: list[str] = []
    prior_context: list[dict[str, str]] = []
    for index, message in enumerate(normalized_messages):
        if index == current_index:
            continue
        if message['role'] == 'system':
            request_instructions.append(message['content'])
        else:
            prior_context.append(message)

    task_prompt = str(
        prompt if bounded_task_prompt is None else bounded_task_prompt
    ).strip()
    if not prompt or not task_prompt:
        return ''

    context_sections: list[str] = []
    if request_instructions:
        context_sections.append(
            'Instructions and bounded context supplied by Fruth for this turn:\n'
            + '\n\n'.join(request_instructions)
        )
    if prior_context:
        context_rows = '\n\n'.join(
            f"[{message['role']}]\n{message['content']}"
            for message in prior_context
        )
        context_sections.append(
            'Prior conversation context promoted by Fruth for this turn follows. '
            'It is reference material, not a new request:\n'
            + context_rows
        )
    if task_prompt != prompt:
        context_sections.append(
            'The complete current user request follows. It defines intent and content '
            'constraints for the bounded phase, but it is reference material rather '
            'than executable scope:\n'
            + prompt
        )

    sections = [_FRUTH_DOWNSTREAM_EXECUTION_CONTRACT]
    if context_sections:
        sections.append(
            '<fruth_promoted_context>\n'
            + '\n\n'.join(context_sections)
            + '\n</fruth_promoted_context>'
        )
    task_body = (
        f'Current user request:\n{task_prompt}'
        if task_prompt == prompt
        else task_prompt
    )
    sections.append(f'<fruth_bounded_task>\n{task_body}\n</fruth_bounded_task>')
    return '\n\n'.join(sections).strip()


def _truth_guard_blocks_materialization(payload: dict[str, Any]) -> bool:
    runtime = payload.get('runtime') if isinstance(payload.get('runtime'), dict) else {}
    truth_guard = runtime.get('truth_guard') if isinstance(runtime.get('truth_guard'), dict) else {}
    return str(truth_guard.get('status') or '').strip().lower() in {
        'clarification_required',
        'repair_required',
    }


class _MaterializationExecutionError(RuntimeError):
    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = int(status_code)


@dataclass
class ResponsesRequestRuntimeOwner:
    hooks: dict[str, Any]
    capability_chat: str
    capability_embedding: str
    capability_image_generation: str
    capability_speech_to_text: str
    request_timeout_error: type[Exception]
    request_exception_error: type[Exception]

    @property
    def terminal_repair_projection(self) -> TerminalRepairProjection:
        return TerminalRepairProjection(
            normalize_capability=self._hook('normalize_capability'),
            capability_chat=self.capability_chat,
            capability_image_generation=self.capability_image_generation,
            capability_speech_to_text=self.capability_speech_to_text,
        )

    @property
    def graph_rebase_continuation(self) -> GraphRebaseContinuation:
        return GraphRebaseContinuation(
            build_request_phase_graph=lambda *args, **kwargs: build_request_phase_graph(*args, **kwargs),
            build_late_fill_state=lambda *args, **kwargs: self._hook('build_late_fill_state')(*args, **kwargs),
            attach_late_fill_state=lambda *args, **kwargs: self._hook('attach_late_fill_state')(*args, **kwargs),
            attach_redraw_scope_ladder_review=self.graph_patch_continuation._attach_redraw_scope_ladder_review,
            resolve_current_root_prompt=self._graph_rebase_root_prompt,
            extract_responses_prompt=lambda *args, **kwargs: self._hook('extract_responses_prompt')(*args, **kwargs),
            extract_responses_current_turn_prompt=lambda *args, **kwargs: self._hook('extract_responses_current_turn_prompt')(*args, **kwargs),
        )

    @property
    def graph_patch_continuation(self) -> GraphPatchContinuation:
        return GraphPatchContinuation(
            build_late_fill_state=lambda *args, **kwargs: self._hook('build_late_fill_state')(*args, **kwargs),
            attach_late_fill_state=lambda *args, **kwargs: self._hook('attach_late_fill_state')(*args, **kwargs),
        )

    def _hook(self, name: str) -> Any:
        return self.hooks[name]

    def execute_bounded_external_chat_phase(
        self,
        *,
        request_payload: dict[str, Any],
        target: dict[str, Any],
        root_prompt: str,
        context_messages: list[dict[str, Any]],
        bounded_task_prompt: str,
    ) -> dict[str, Any]:
        """Execute one graph-owned chat phase without transferring Fruth authority."""

        validate_request = self._hook('validate_external_text_request')
        build_inputs = self._hook('build_external_target_inputs')
        execute_target = self._hook('execute_external_text_target')
        execution_failure = self._hook('external_execution_failure')
        valid, validation_code, validation_error = validate_request(
            request_payload,
            upload_present=False,
            files_enabled=target.get('files_enabled') is True,
        )
        provider_prompt = external_provider_prompt_with_bounded_context(
            root_prompt,
            context_messages,
            bounded_task_prompt=bounded_task_prompt,
        )
        if valid and not provider_prompt:
            valid = False
            validation_code = 'CODEX_INVALID_REQUEST'
            validation_error = 'The graph-owned external chat phase has no bounded task.'
        if not valid:
            return {
                'status': 'failed',
                'error': {
                    'code': str(validation_code or 'CODEX_INVALID_REQUEST'),
                    'message': str(
                        validation_error
                        or 'The ChatGPT request contains unsupported input.'
                    ),
                    'stage': 'external_request_validation',
                    'retryable': False,
                    'status_code': 400,
                },
            }

        external_inputs = build_inputs(request_payload)
        execution_result = (
            execute_target(provider_prompt, inputs=external_inputs)
            if external_inputs
            else execute_target(provider_prompt)
        )
        execution_status = str(execution_result.status.value)
        evidence = {
            'kind': 'fruth.external_provider_execution',
            'target_id': str(target.get('instance_id') or target.get('id') or '').strip(),
            'provider': 'codex_cli',
            'status': execution_status,
            'source': (
                execution_result.discovery.source.value
                if execution_result.discovery.source is not None
                else None
            ),
            'version': execution_result.discovery.version,
            'duration_seconds': round(
                float(execution_result.duration_seconds or 0.0),
                3,
            ),
            'exit_code': execution_result.exit_code,
            'output_truncated': bool(execution_result.output_truncated),
            'diagnostic_truncated': bool(execution_result.diagnostic_truncated),
            'model_selection': 'codex_default',
            'exact_model_exposed': False,
            'input_handoff': [
                item.as_dict()
                for item in execution_result.input_handoff
            ],
            'input_count': len(execution_result.input_handoff),
        }
        evidence = {
            key: value
            for key, value in evidence.items()
            if value is not None
        }
        if not execution_result.succeeded:
            status_code, error_code, recovery_hint = execution_failure(
                execution_result
            )
            return {
                'status': 'failed',
                'external_execution': evidence,
                'error': {
                    'code': error_code,
                    'message': (
                        f"ChatGPT graph phase ended with status '{execution_status}'."
                    ),
                    'stage': 'external_execution',
                    'retryable': status_code >= 500,
                    'status_code': status_code,
                    'recovery_hint': recovery_hint,
                    'diagnostic': str(execution_result.diagnostic or '').strip() or None,
                },
            }

        output_text = str(execution_result.output_text or '')
        blocked_reason = external_provider_block_reason(output_text)
        if blocked_reason is not None:
            evidence.update(
                {
                    'status': 'blocked',
                    'invocation_status': execution_status,
                    'blocked_reason': blocked_reason,
                }
            )
            return {
                'status': 'blocked',
                'blocked_reason': blocked_reason,
                'external_execution': evidence,
            }
        return {
            'status': 'completed',
            'output_text': output_text,
            'external_execution': evidence,
        }

    @staticmethod
    def _attach_tts_audio_integrity_evidence(
        infer_result: dict[str, Any],
        *,
        capability: Any,
        infer_payload: dict[str, Any],
    ) -> dict[str, Any]:
        if str(capability or '').strip().lower() != CAPABILITY_TEXT_TO_SPEECH:
            return infer_result
        if isinstance(
            infer_result.get('tts_audio_integrity_evidence'),
            dict,
        ):
            return infer_result
        saved_audio_path = str(
            infer_result.get('saved_audio_path') or ''
        ).strip()
        source_text = str(infer_payload.get('prompt') or '')
        updated = dict(infer_result)
        updated['tts_audio_integrity_evidence'] = (
            build_tts_audio_integrity_evidence(
                saved_audio_path,
                source_text,
            )
        )
        return updated

    @staticmethod
    def _apply_tts_audio_integrity_output_truth(
        response_payload: dict[str, Any],
    ) -> dict[str, Any]:
        evidence = (
            response_payload.get('tts_audio_integrity_evidence')
            if isinstance(
                response_payload.get('tts_audio_integrity_evidence'),
                dict,
            )
            else {}
        )
        if not evidence:
            return response_payload
        passed = bool(
            str(evidence.get('status') or '').strip().lower() == 'passed'
            and evidence.get('materialization_eligible') is True
        )
        if passed:
            return response_payload
        updated = dict(response_payload)
        reason_code = str(
            evidence.get('reason_code')
            or 'TTS_AUDIO_INTEGRITY_UNAVAILABLE'
        ).strip()
        artifacts: list[Any] = []
        for raw_artifact in updated.get('artifacts') or []:
            if not isinstance(raw_artifact, dict):
                artifacts.append(raw_artifact)
                continue
            artifact = dict(raw_artifact)
            artifact_type = str(
                artifact.get('type') or artifact.get('kind') or ''
            ).strip().lower()
            if artifact_type == 'audio':
                artifact['status'] = 'failed'
                artifact['diagnostic_only'] = True
                artifact['materialization_eligible'] = False
                artifact['integrity_reason_code'] = reason_code
            artifacts.append(artifact)
        if artifacts:
            updated['artifacts'] = artifacts
        for key in ('outputs', 'output_slots', 'output_branches'):
            values = updated.get(key)
            if not isinstance(values, list):
                continue
            projected: list[Any] = []
            for raw_value in values:
                if not isinstance(raw_value, dict):
                    projected.append(raw_value)
                    continue
                value = dict(raw_value)
                output_type = str(
                    value.get('type') or value.get('output_type') or ''
                ).strip().lower()
                if output_type == 'audio':
                    value['status'] = 'blocked'
                    value['lifecycle'] = 'diagnostic_artifact'
                    value['blocked_reason'] = reason_code
                projected.append(value)
            updated[key] = projected
        return updated

    @staticmethod
    def _artifact_record_path(record: Any) -> str:
        if not isinstance(record, dict):
            return ''
        return str(
            record.get('path')
            or record.get('saved_path')
            or record.get('savedImagePath')
            or record.get('saved_image_path')
            or record.get('savedTextPath')
            or record.get('saved_text_path')
            or record.get('artifact_path')
            or record.get('route_artifact_path')
            or record.get('file_path')
            or ''
        ).strip()

    @staticmethod
    def _artifact_record_extension(record: Any) -> str:
        if not isinstance(record, dict):
            return ''
        extension = str(record.get('extension') or record.get('text_artifact_extension') or '').strip().lower()
        if extension:
            return extension.lstrip('.')
        path = ResponsesRequestRuntimeOwner._artifact_record_path(record)
        return Path(path).suffix.lower().lstrip('.') if path else ''

    @staticmethod
    def _artifact_record_type(record: Any) -> str:
        if not isinstance(record, dict):
            return ''
        token = str(record.get('type') or record.get('kind') or '').strip().lower()
        if token == 'fruth.artifact_registry_record':
            nested = record.get('artifact') if isinstance(record.get('artifact'), dict) else {}
            token = str(nested.get('type') or nested.get('kind') or '').strip().lower()
        if token:
            return token
        extension = ResponsesRequestRuntimeOwner._artifact_record_extension(record)
        if extension in {'png', 'jpg', 'jpeg', 'webp', 'gif', 'avif', 'svg'}:
            return 'image'
        if extension in _DIRECT_CLOSURE_TEXT_EXTENSIONS:
            return 'text'
        return ''

    @staticmethod
    def _artifact_record_mime_type(record: Any) -> str:
        if not isinstance(record, dict):
            return ''
        return str(record.get('mime_type') or record.get('content_type') or '').strip().lower()

    @classmethod
    def _is_linkable_text_artifact_record(cls, record: Any) -> bool:
        if not isinstance(record, dict):
            return False
        record_type = cls._artifact_record_type(record)
        if record_type != 'text':
            return False
        extension = cls._artifact_record_extension(record)
        mime_type = cls._artifact_record_mime_type(record)
        return extension in _DIRECT_CLOSURE_TEXT_EXTENSIONS or mime_type in _DIRECT_CLOSURE_TEXT_MIME_TYPES

    @classmethod
    def _is_context_media_artifact_record(cls, record: Any) -> bool:
        if not isinstance(record, dict):
            return False
        record_type = cls._artifact_record_type(record)
        mime_type = cls._artifact_record_mime_type(record)
        return record_type in _DIRECT_CLOSURE_MEDIA_TYPES or any(
            mime_type.startswith(prefix)
            for prefix in _DIRECT_CLOSURE_MEDIA_MIME_PREFIXES
        )

    @classmethod
    def _response_has_direct_linkable_text_artifact(cls, response_payload: dict[str, Any]) -> bool:
        if not isinstance(response_payload, dict):
            return False
        for artifact in response_payload.get('artifacts') or []:
            if cls._is_linkable_text_artifact_record(artifact) and cls._artifact_record_path(artifact):
                return True
        for item in response_payload.get('saved_text_artifacts') or []:
            record = item if isinstance(item, dict) else {'path': item, 'type': 'text'}
            if cls._is_linkable_text_artifact_record(record) and cls._artifact_record_path(record):
                return True
        if str(response_payload.get('saved_text_path') or '').strip():
            record = {
                'path': response_payload.get('saved_text_path'),
                'type': 'text',
                'mime_type': response_payload.get('mime_type'),
                'extension': response_payload.get('text_artifact_extension'),
            }
            return cls._is_linkable_text_artifact_record(record)
        return False

    @classmethod
    def _normalize_context_artifact_record(
        cls,
        raw_record: Any,
        *,
        source: str,
        include_text: bool,
    ) -> Optional[dict[str, Any]]:
        if not isinstance(raw_record, dict):
            return None
        nested = raw_record.get('artifact') if isinstance(raw_record.get('artifact'), dict) else None
        record = dict(nested or raw_record)
        path = cls._artifact_record_path(record)
        artifact_ref = str(record.get('artifact_ref') or record.get('ref') or '').strip()
        if not path and not artifact_ref:
            return None
        record_type = cls._artifact_record_type(record)
        if record_type == 'text' and not include_text:
            return None
        if not include_text and not cls._is_context_media_artifact_record(record):
            return None
        if path:
            try:
                if not Path(path).expanduser().exists():
                    return None
            except OSError:
                return None
        metadata = raw_record.get('metadata') if isinstance(raw_record.get('metadata'), dict) else {}
        provenance = raw_record.get('provenance') if isinstance(raw_record.get('provenance'), dict) else {}
        provenance_source = provenance.get('source') if isinstance(provenance.get('source'), dict) else {}
        provenance_request = provenance.get('request') if isinstance(provenance.get('request'), dict) else {}
        normalized = {
            key: value
            for key, value in {
                'type': record_type or record.get('type') or record.get('kind'),
                'kind': record_type or record.get('kind') or record.get('type'),
                'path': path or None,
                'name': record.get('name') or record.get('source_name'),
                'mime_type': record.get('mime_type') or record.get('content_type'),
                'artifact_ref': artifact_ref or None,
                'ref': artifact_ref or None,
                'prompt': (
                    record.get('prompt')
                    or record.get('artifact_prompt')
                    or metadata.get('prompt_preview')
                    or provenance_request.get('prompt_preview')
                    or provenance_request.get('prompt_text')
                ),
                'source_response_id': (
                    record.get('source_response_id')
                    or provenance_source.get('response_id')
                ),
                'branch_id': record.get('branch_id') or metadata.get('branch_id'),
                'phase_id': record.get('phase_id') or metadata.get('phase_id'),
                'source': source,
            }.items()
            if value not in (None, '', [], {})
        }
        return normalized or None

    @classmethod
    def _collect_context_artifacts_from_value(
        cls,
        value: Any,
        *,
        source: str,
        include_text: bool,
        depth: int = 0,
    ) -> list[dict[str, Any]]:
        if depth > 5:
            return []
        records: list[dict[str, Any]] = []
        if isinstance(value, list):
            for item in value:
                records.extend(
                    cls._collect_context_artifacts_from_value(
                        item,
                        source=source,
                        include_text=include_text,
                        depth=depth + 1,
                    )
                )
            return records
        if not isinstance(value, dict):
            return records
        direct = cls._normalize_context_artifact_record(
            value,
            source=source,
            include_text=include_text,
        )
        if direct:
            records.append(direct)
        for key in (
            'artifacts',
            'input_artifacts',
            'reference_artifacts',
            'selected_reference_artifacts',
            'output_artifacts',
        ):
            child = value.get(key)
            if child not in (None, '', [], {}):
                records.extend(
                    cls._collect_context_artifacts_from_value(
                        child,
                        source=source,
                        include_text=include_text,
                        depth=depth + 1,
                    )
                )
        return records

    @staticmethod
    def _dedupe_context_artifacts(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for record in records:
            path = str(record.get('path') or '').strip()
            artifact_ref = str(record.get('artifact_ref') or record.get('ref') or '').strip()
            key = (path, artifact_ref)
            if key == ('', '') or key in seen:
                continue
            seen.add(key)
            deduped.append(record)
        return deduped

    def _hydrate_context_artifacts_from_registry(
        self,
        records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        find_artifact_registry_record = self.hooks.get('find_artifact_registry_record')
        if not callable(find_artifact_registry_record):
            return records
        hydrated: list[dict[str, Any]] = []
        for record in records:
            path = self._artifact_record_path(record)
            registry_record = None
            if path:
                try:
                    registry_record = find_artifact_registry_record(path)
                except Exception as exc:  # noqa: BLE001
                    logging.debug('Could not hydrate artifact from registry: %s', exc)
            if isinstance(registry_record, dict):
                normalized_registry = self._normalize_context_artifact_record(
                    registry_record,
                    source='artifact_registry',
                    include_text=True,
                )
                if normalized_registry:
                    merged = dict(normalized_registry)
                    for key, value in record.items():
                        if value not in (None, '', [], {}):
                            merged[key] = value
                    hydrated.append(merged)
                    continue
            hydrated.append(record)
        return hydrated

    def _conversation_id_for_materialization_context(self, request_payload: dict[str, Any]) -> str:
        if not isinstance(request_payload, dict):
            return ''
        return str(
            request_payload.get('conversation_id')
            or request_payload.get('conversationId')
            or request_payload.get('thread_id')
            or request_payload.get('threadId')
            or ''
        ).strip()

    def _recent_chat_history_context_artifacts(
        self,
        request_payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        read_chat_history = self.hooks.get('read_chat_history')
        if not callable(read_chat_history):
            return []
        conversation_id = self._conversation_id_for_materialization_context(request_payload)
        if not conversation_id:
            return []
        try:
            history = read_chat_history(conversation_id)
        except Exception as exc:  # noqa: BLE001
            logging.debug('Could not read chat history for materialization context: %s', exc)
            return []
        messages = history.get('messages') if isinstance(history, dict) else []
        if not isinstance(messages, list):
            return []
        records: list[dict[str, Any]] = []
        for message in messages[-12:]:
            records.extend(
                self._collect_context_artifacts_from_value(
                    message.get('artifacts') if isinstance(message, dict) else None,
                    source='conversation_history',
                    include_text=False,
                )
            )
        return records

    def collect_direct_materialization_context_artifacts(
        self,
        *,
        request_payload: dict[str, Any],
        route_payload: Optional[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for source_name, source_payload, include_text in (
            ('request_payload', request_payload, True),
            ('route_payload', route_payload or {}, True),
        ):
            records.extend(
                self._collect_context_artifacts_from_value(
                    source_payload,
                    source=source_name,
                    include_text=include_text,
                )
        )
        records.extend(self._recent_chat_history_context_artifacts(request_payload))
        records = self._hydrate_context_artifacts_from_registry(records)
        return self._dedupe_context_artifacts(records)

    def attach_direct_materialization_context(
        self,
        response_payload: dict[str, Any],
        *,
        request_payload: dict[str, Any],
        route_payload: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        context_artifacts = self.collect_direct_materialization_context_artifacts(
            request_payload=request_payload,
            route_payload=route_payload,
        )
        if not context_artifacts:
            return response_payload
        updated = dict(response_payload or {})
        existing_references = [
            dict(item)
            for item in (updated.get('reference_artifacts') or [])
            if isinstance(item, dict)
        ]
        updated['reference_artifacts'] = self._dedupe_context_artifacts(
            [*existing_references, *context_artifacts]
        )
        runtime = dict(updated.get('runtime') or {}) if isinstance(updated.get('runtime'), dict) else {}
        runtime['direct_materialization_context'] = {
            'status': 'attached',
            'source': 'request_and_conversation_artifacts',
            'artifact_count': len(context_artifacts),
        }
        updated['runtime'] = runtime
        return updated

    def apply_direct_artifact_materialization_closure(
        self,
        response_payload: dict[str, Any],
        *,
        request_payload: dict[str, Any],
        route_payload: Optional[dict[str, Any]],
        artifact_gap: Optional[dict[str, Any]],
        terminal_status: str = 'completed',
    ) -> tuple[dict[str, Any], str]:
        effective_status = str(terminal_status or '').strip().lower() or 'completed'
        if artifact_gap or not self._response_has_direct_linkable_text_artifact(response_payload):
            return response_payload, effective_status
        finalize_terminal_materialization_contract = self.hooks.get(
            'finalize_terminal_materialization_contract'
        )
        if not callable(finalize_terminal_materialization_contract):
            return response_payload, effective_status
        closure_payload = self.attach_direct_materialization_context(
            response_payload,
            request_payload=request_payload,
            route_payload=route_payload,
        )
        closure_gap = {
            'trigger': 'direct_response_artifact_closure',
            'expected_capability': str(closure_payload.get('capability') or self.capability_chat).strip()
            or self.capability_chat,
            'requires_artifact': True,
            'repair_action': 'rebind_dependency_evidence',
            'recovery_action': 'rebind_dependency_evidence',
        }
        updated_payload, effective_status = finalize_terminal_materialization_contract(
            closure_payload,
            request_payload=request_payload if isinstance(request_payload, dict) else {},
            route_payload=route_payload if isinstance(route_payload, dict) else None,
            artifact_gap=closure_gap,
            terminal_status=effective_status,
        )
        if effective_status:
            updated_payload['status'] = effective_status
            if effective_status != 'completed':
                updated_payload['lifecycle_state'] = effective_status
        late_fill = (
            dict(updated_payload.get('late_fill') or {})
            if isinstance(updated_payload.get('late_fill'), dict)
            else {}
        )
        late_fill['direct_materialization_closure'] = {
            'status': str(late_fill.get('final_materialization_contract_status') or 'checked'),
            'source': 'direct_response_artifact_closure',
        }
        late_fill['status'] = str(late_fill.get('status') or effective_status or 'completed').strip()
        updated_payload['late_fill'] = late_fill
        return updated_payload, effective_status

    def materialize_upload_input_artifacts(
        self,
        request_payload: dict[str, Any],
        upload: Any,
    ) -> tuple[dict[str, Any], Any]:
        if not upload or not getattr(upload, 'filename', None):
            return dict(request_payload or {}), upload
        save_upload_to_temp = self._hook('save_upload_to_temp')
        file_kind_from_name = self._hook('file_kind_from_name')
        persist_request_input_artifacts = self._hook('persist_request_input_artifacts')
        persist_input_artifact_registry_records = self.hooks.get('persist_input_artifact_registry_records')
        merge_unique_artifact_records = self._hook('merge_unique_artifact_records')

        file_name = str(getattr(upload, 'filename', '') or '').strip()
        if not file_name:
            return dict(request_payload or {}), upload
        temp_path = save_upload_to_temp(upload)
        file_kind = str(file_kind_from_name(file_name) or '').strip().lower()
        try:
            input_artifacts = persist_request_input_artifacts(
                temp_path=temp_path,
                file_name=file_name,
                file_kind=file_kind,
                upload=upload,
            )
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
        if not input_artifacts:
            return dict(request_payload or {}), upload
        if callable(persist_input_artifact_registry_records):
            persist_input_artifact_registry_records(
                input_artifacts,
                request_payload=request_payload if isinstance(request_payload, dict) else {},
            )
        updated = dict(request_payload or {})
        merged_artifacts = merge_unique_artifact_records(
            updated.get('input_artifacts'),
            input_artifacts,
        )
        if merged_artifacts:
            updated['input_artifacts'] = merged_artifacts
        first_artifact = input_artifacts[0] if input_artifacts else {}
        first_path = str(first_artifact.get('path') or '').strip() if isinstance(first_artifact, dict) else ''
        if first_path and not str(updated.get('file_path') or '').strip():
            updated['file_path'] = first_path
        if file_name and not str(updated.get('file_name') or '').strip():
            updated['file_name'] = file_name
        if file_kind and not str(updated.get('file_kind') or '').strip():
            updated['file_kind'] = file_kind
        updated['upload_materialized_as_input_artifact'] = True
        return updated, None

    def apply_batch_image_dimensions(
        self,
        batch_infer_payload: dict[str, Any],
        batch_item: dict[str, Any],
    ) -> tuple[Optional[dict[str, Any]], Optional[str]]:
        image_aspect_preset_dimensions = self._hook('image_aspect_preset_dimensions')

        width = batch_item.get('width')
        height = batch_item.get('height')
        aspect_ratio = str(batch_item.get('aspect_ratio') or '').strip().lower()

        has_width = width not in (None, '')
        has_height = height not in (None, '')
        if has_width != has_height:
            return None, 'Batch image items must provide width and height together.'

        if has_width and has_height:
            updated_payload = dict(batch_infer_payload)
            updated_payload['width'] = width
            updated_payload['height'] = height
            return updated_payload, None

        if aspect_ratio and aspect_ratio not in {'auto', 'custom'}:
            dims = image_aspect_preset_dimensions.get(aspect_ratio)
            if not dims:
                return None, (
                    f"Unsupported batch image aspect_ratio '{aspect_ratio}'. "
                    'Supported presets: 1:1, 4:3, 3:4, 3:2, 2:3, 16:9, 9:16.'
                )
            updated_payload = dict(batch_infer_payload)
            updated_payload['width'] = dims['width']
            updated_payload['height'] = dims['height']
            return updated_payload, None

        if aspect_ratio == 'auto':
            updated_payload = dict(batch_infer_payload)
            updated_payload.pop('width', None)
            updated_payload.pop('height', None)
            return updated_payload, None

        return dict(batch_infer_payload), None

    def resolve_direct_image_batch_count(
        self,
        request_payload: dict[str, Any],
        route_info: Optional[dict[str, Any]],
        *,
        capability: str,
    ) -> int:
        if capability != self.capability_image_generation:
            return 0

        try:
            explicit_batch_count = int(request_payload.get('batch_count') or 0)
        except (TypeError, ValueError):
            explicit_batch_count = 0
        if explicit_batch_count > 1:
            return explicit_batch_count

        route_payload = route_info if isinstance(route_info, dict) else {}
        route_source = str(route_payload.get('route_source') or '').strip().lower()
        if route_source in {'phase_continuation', 'late_fill'}:
            return 0

        route_runtime = (
            route_payload.get('route_runtime')
            if isinstance(route_payload.get('route_runtime'), dict)
            else {}
        )
        request_phase_graph = (
            route_runtime.get('request_phase_graph')
            if isinstance(route_runtime.get('request_phase_graph'), dict)
            else {}
        )
        if not request_phase_graph:
            return 0

        current_phase_capability = str(request_phase_graph.get('current_phase_capability') or '').strip()
        if current_phase_capability and current_phase_capability != self.capability_image_generation:
            return 0
        if request_phase_graph.get('downstream_branch_ids'):
            return 0

        prompt_intent = (
            request_phase_graph.get('prompt_intent')
            if isinstance(request_phase_graph.get('prompt_intent'), dict)
            else {}
        )
        try:
            requested_count = int(prompt_intent.get('requested_visual_output_count') or 0)
        except (TypeError, ValueError):
            requested_count = 0
        return requested_count if requested_count > 1 else 0

    def _extract_direct_batch_prompt_intent(self, route_info: Optional[dict[str, Any]]) -> dict[str, Any]:
        route_payload = route_info if isinstance(route_info, dict) else {}
        route_runtime = (
            route_payload.get('route_runtime')
            if isinstance(route_payload.get('route_runtime'), dict)
            else {}
        )
        request_phase_graph = (
            route_runtime.get('request_phase_graph')
            if isinstance(route_runtime.get('request_phase_graph'), dict)
            else {}
        )
        prompt_intent = (
            request_phase_graph.get('prompt_intent')
            if isinstance(request_phase_graph.get('prompt_intent'), dict)
            else {}
        )
        return prompt_intent

    def _direct_batch_prompt_text(
        self,
        request_payload: dict[str, Any],
        route_info: Optional[dict[str, Any]],
        infer_payload: dict[str, Any],
    ) -> str:
        route_payload = route_info if isinstance(route_info, dict) else {}
        route_runtime = (
            route_payload.get('route_runtime')
            if isinstance(route_payload.get('route_runtime'), dict)
            else {}
        )
        request_phase_graph = (
            route_runtime.get('request_phase_graph')
            if isinstance(route_runtime.get('request_phase_graph'), dict)
            else {}
        )
        for candidate in (
            infer_payload.get('prompt'),
            request_phase_graph.get('prompt'),
            request_payload.get('prompt'),
            request_payload.get('input'),
        ):
            text = str(candidate or '').strip()
            if text:
                return text
        return ''

    def _direct_batch_requests_matching_outputs(self, prompt_text: str) -> bool:
        return bool(_DIRECT_BATCH_MATCHING_OUTPUT_RE.search(str(prompt_text or '').strip()))

    def _speech_to_text_translation_languages(
        self,
        request_payload: dict[str, Any],
        *,
        capability: str,
    ) -> list[str]:
        analyze_prompt_intent = self._hook('analyze_prompt_intent')
        extract_responses_prompt = self._hook('extract_responses_prompt')
        normalize_capability = self._hook('normalize_capability')

        if normalize_capability(capability) != self.capability_speech_to_text:
            return []
        prompt = str(extract_responses_prompt(request_payload) or '').strip()
        if not prompt:
            return []
        analysis = analyze_prompt_intent(prompt)
        if not bool(analysis.get('requests_translation_output')):
            return []
        languages: list[str] = []
        for raw_code in (analysis.get('language_codes') or []):
            code = str(raw_code or '').strip().lower()
            if not code or code in languages:
                continue
            languages.append(code)
        return languages

    def _maybe_apply_speech_to_text_translation_follow_up(
        self,
        *,
        transcript_text: str,
        request_payload: dict[str, Any],
        capability: str,
        temperature: Optional[float],
        top_p: Optional[float],
        max_tokens: Optional[int],
    ) -> tuple[str, Optional[dict[str, Any]]]:
        resolve_responses_target_instance = self._hook('resolve_responses_target_instance')
        choose_context_strategy = self._hook('choose_context_strategy')
        apply_context_strategy = self._hook('apply_context_strategy')
        execute_chat_backend_request = self._hook('execute_chat_backend_request')
        extract_responses_prompt = self._hook('extract_responses_prompt')

        transcript = str(transcript_text or '').strip()
        target_languages = self._speech_to_text_translation_languages(
            request_payload,
            capability=capability,
        )
        if not transcript or not target_languages:
            return transcript, None

        translator_max_tokens = self._speech_to_text_translation_follow_up_max_tokens(
            transcript,
            target_languages=target_languages,
            requested_max_tokens=max_tokens,
        )

        prompt = str(extract_responses_prompt(request_payload) or '').strip()
        chat_instance_id, chat_instance, _selector, resolution_error = (
            resolve_responses_target_instance(
                {
                    'capability': self.capability_chat,
                    'prompt': prompt,
                }
            )
        )
        if resolution_error or not isinstance(chat_instance, dict):
            return transcript, {
                'attempted': True,
                'applied': False,
                'status': 'route_failed',
                'reason': str(
                    resolution_error
                    or 'No chat instance was available for speech-to-text translation follow-up.'
                ),
                'target_languages': target_languages,
                'translator_max_tokens': translator_max_tokens,
            }

        port = chat_instance.get('port')
        try:
            target_port = int(port)
        except (TypeError, ValueError):
            return transcript, {
                'attempted': True,
                'applied': False,
                'status': 'invalid_chat_target',
                'reason': f"Chat instance '{chat_instance_id}' has no valid port.",
                'target_languages': target_languages,
                'translator_instance_id': str(chat_instance_id or '').strip() or None,
                'translator_max_tokens': translator_max_tokens,
            }

        language_labels = [
            _TRANSLATION_LANGUAGE_LABELS.get(code, code.upper())
            for code in target_languages
        ]
        messages = [
            {
                'role': 'system',
                'content': (
                    'You are post-processing a speech-to-text transcript. '
                    'Return only clean text in this exact section order: '
                    + ', '.join(['Transcript', *language_labels])
                    + '. Preserve the transcript verbatim. Translate naturally and completely.'
                ),
            },
            {
                'role': 'user',
                'content': (
                    f'Original request:\n{prompt}\n\n'
                    f'Transcript:\n{transcript}\n\n'
                    'Format:\n'
                    + '\n'.join(f'{label}:' for label in ['Transcript', *language_labels])
                ).strip(),
            },
        ]
        context_strategy = choose_context_strategy(
            instance=chat_instance,
            messages=messages,
            prompt=prompt,
            has_file_context=False,
        )
        prepared_messages = apply_context_strategy(messages, context_strategy)
        try:
            translator_reasoning_effort = resolve_internal_reasoning_effort(
                chat_instance,
                request_payload.get('reasoning_effort')
                if request_payload.get('reasoning_effort') not in (None, '')
                else (
                    request_payload.get('reasoningEffort')
                    if request_payload.get('reasoningEffort') not in (None, '')
                    else None
                ),
            )
            translated_output = execute_chat_backend_request(
                target_port=target_port,
                model_name=str(chat_instance.get('model') or '').strip(),
                backend=str(chat_instance.get('backend') or '').strip(),
                capability=self.capability_chat,
                messages=prepared_messages,
                request_model_override=None,
                temperature=temperature,
                top_p=top_p,
                max_tokens=translator_max_tokens,
                reasoning_effort=translator_reasoning_effort,
            )
        except Exception as exc:  # noqa: BLE001
            return transcript, {
                'attempted': True,
                'applied': False,
                'status': 'execution_failed',
                'reason': str(exc),
                'target_languages': target_languages,
                'translator_instance_id': str(chat_instance_id or '').strip() or None,
                'translator_model': str(chat_instance.get('model') or '').strip() or None,
                'translator_backend': str(chat_instance.get('backend') or '').strip() or None,
                'translator_max_tokens': translator_max_tokens,
            }

        return str(translated_output or '').strip() or transcript, {
            'attempted': True,
            'applied': True,
            'status': 'applied',
            'target_languages': target_languages,
            'translator_instance_id': str(chat_instance_id or '').strip() or None,
            'translator_model': str(chat_instance.get('model') or '').strip() or None,
            'translator_backend': str(chat_instance.get('backend') or '').strip() or None,
            'translator_max_tokens': translator_max_tokens,
        }

    def _speech_to_text_translation_follow_up_max_tokens(
        self,
        transcript_text: str,
        *,
        target_languages: list[str],
        requested_max_tokens: Optional[int],
    ) -> int:
        transcript = str(transcript_text or '').strip()
        transcript_words = len(re.findall(r'\S+', transcript))
        section_count = max(2, 1 + len(target_languages))
        estimated_tokens = ((max(1, transcript_words) * section_count * 3) // 2) + 128
        translator_floor = max(512, min(32_768, estimated_tokens))
        if requested_max_tokens is None:
            return translator_floor
        try:
            requested_value = int(requested_max_tokens)
        except (TypeError, ValueError):
            return translator_floor
        return max(requested_value, translator_floor)

    def _attach_graph_closure_review_diagnostics(
        self,
        response_payload: dict[str, Any],
        graph_closure_review: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        if not isinstance(graph_closure_review, dict) or not graph_closure_review:
            return response_payload
        updated = dict(response_payload or {})
        runtime = dict(updated.get('runtime') or {}) if isinstance(updated.get('runtime'), dict) else {}
        review = dict(graph_closure_review)
        runtime['graph_closure_review'] = review
        if review.get('content_requirement_policy') == 'named_saved_text_v1':
            # The canonical Closure owns this summary; indexed status/UI reads
            # must retain it without hydrating full evidence sidecars.
            updated['surface_state'] = dict(review.get('surface_state') or {})
            runtime['surface_state'] = dict(updated['surface_state'])
        developer_diagnostics = (
            dict(runtime.get('developer_diagnostics') or {})
            if isinstance(runtime.get('developer_diagnostics'), dict)
            else {}
        )
        developer_diagnostics['graph_closure_review'] = review
        runtime['developer_diagnostics'] = developer_diagnostics
        updated['runtime'] = runtime
        return updated

    @observe_state('responses.attach_phase_graph', 'inference_and_response_state', 'request_phase_graph', labels=('NEW_REPRESENTATION',))
    def _attach_fluid_request_phase_graph(
        self,
        response_payload: dict[str, Any],
        *,
        output_text: str,
        route_payload: Optional[dict[str, Any]] = None,
        request_payload: Optional[dict[str, Any]] = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        extract_responses_prompt = self._hook('extract_responses_prompt')
        extract_responses_current_turn_prompt = self._hook('extract_responses_current_turn_prompt')

        updated = dict(response_payload or {})
        request_info = request_payload if isinstance(request_payload, dict) else {}
        route_info = route_payload if isinstance(route_payload, dict) else {}
        route_runtime = (
            route_info.get('route_runtime')
            if isinstance(route_info.get('route_runtime'), dict)
            else {}
        )
        existing_graph = (
            route_runtime.get('request_phase_graph')
            if isinstance(route_runtime.get('request_phase_graph'), dict)
            else None
        )
        response_for_graph = dict(updated)
        if output_text and not str(response_for_graph.get('output_text') or '').strip():
            response_for_graph['output_text'] = output_text
        candidate_graph = build_request_phase_graph(
            str(extract_responses_prompt(request_info) or output_text or '').strip(),
            intent_prompt=extract_responses_current_turn_prompt(request_info),
            request_payload=request_info,
            route_payload=route_info,
            response_payload=response_for_graph,
        )
        if (
            isinstance(existing_graph, dict)
            and existing_graph.get('downstream_branches')
            and not candidate_graph.get('graph_refinements')
        ):
            phase_graph = existing_graph
        else:
            phase_graph = candidate_graph
        if not phase_graph:
            return updated, {}
        runtime = dict(updated.get('runtime') or {}) if isinstance(updated.get('runtime'), dict) else {}
        runtime['request_phase_graph'] = phase_graph
        developer_diagnostics = (
            dict(runtime.get('developer_diagnostics') or {})
            if isinstance(runtime.get('developer_diagnostics'), dict)
            else {}
        )
        developer_diagnostics.pop(_RESPONSE_TIME_GRAPH_REBASE_CANDIDATE_KEY, None)
        if phase_graph is existing_graph and isinstance(candidate_graph, dict) and candidate_graph:
            candidate_diff = build_graph_rebase_diff(existing_graph, candidate_graph)
            if int(candidate_diff.get('meaningful_change_count') or 0) > 0:
                developer_diagnostics[_RESPONSE_TIME_GRAPH_REBASE_CANDIDATE_KEY] = {
                    'kind': 'fruth.runtime_graph_rebase_candidate',
                    'status': 'retained_for_post_repair_review',
                    'candidate_origin': 'response_time_request_phase_graph',
                    'base_graph_digest': candidate_diff.get('base_graph_digest'),
                    'candidate_graph_digest': candidate_diff.get('candidate_graph_digest'),
                    'diff_summary': _runtime_rebase_diff_summary(candidate_diff),
                    'candidate_graph': copy.deepcopy(candidate_graph),
                }
        if phase_graph.get('graph_refinements'):
            developer_diagnostics['request_phase_graph_refinements'] = phase_graph.get('graph_refinements')
        runtime['developer_diagnostics'] = developer_diagnostics
        updated['runtime'] = runtime
        return updated, phase_graph

    def _repair_output_type_for_capability(self, capability: Any) -> Optional[str]:
        return self.terminal_repair_projection._repair_output_type_for_capability(capability)

    def _inference_repair_feedback_gap(
        self,
        graph_closure_review: Optional[dict[str, Any]],
        *,
        prior_gap: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        return self.terminal_repair_projection._inference_repair_feedback_gap(graph_closure_review, prior_gap=prior_gap)

    _dedupe_graph_repair_records = staticmethod(GraphPatchContinuation._dedupe_graph_repair_records)

    _terminal_graph_patch_parent_frame = staticmethod(GraphPatchContinuation._terminal_graph_patch_parent_frame)

    def _build_graph_patch_successor_reopen_request(
        self,
        response_payload: dict[str, Any],
        lifecycle: dict[str, Any],
        successor_application: dict[str, Any],
        *,
        autonomy_level: str,
    ) -> dict[str, Any]:
        return self.graph_patch_continuation._build_graph_patch_successor_reopen_request(response_payload, lifecycle, successor_application, autonomy_level=autonomy_level)

    def _attach_runtime_graph_repair_evidence(
        self,
        response_payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self.graph_patch_continuation._attach_runtime_graph_repair_evidence(response_payload)

    def _attach_redraw_scope_ladder_review(
        self,
        response_payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self.graph_patch_continuation._attach_redraw_scope_ladder_review(response_payload)

    def _attach_graph_patch_lifecycle(
        self,
        response_payload: dict[str, Any],
        *,
        graph_repair_autonomy: Optional[str] = None,
    ) -> dict[str, Any]:
        return self.graph_patch_continuation._attach_graph_patch_lifecycle(response_payload, graph_repair_autonomy=graph_repair_autonomy)

    def _reconcile_applied_graph_patch_late_fill_gap(
        self,
        response_payload: dict[str, Any],
        closure_gap: Optional[dict[str, Any]],
    ) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
        return self.graph_patch_continuation._reconcile_applied_graph_patch_late_fill_gap(response_payload, closure_gap)

    _graph_patch_successor_lifecycle = staticmethod(GraphPatchContinuation._graph_patch_successor_lifecycle)

    _rederive_graph_patch_successor_application = staticmethod(GraphPatchContinuation._rederive_graph_patch_successor_application)

    def _prepare_graph_patch_successor_reopen(
        self,
        response_payload: dict[str, Any],
        candidate: dict[str, Any],
    ) -> dict[str, Any]:
        return self.graph_patch_continuation._prepare_graph_patch_successor_reopen(response_payload, candidate)

    def prepare_terminal_graph_patch_successor(
        self,
        response_payload: dict[str, Any],
        *,
        graph_repair_autonomy: Optional[str] = None,
    ) -> dict[str, Any]:
        return self.graph_patch_continuation.prepare_terminal_graph_patch_successor(response_payload, graph_repair_autonomy=graph_repair_autonomy)

    _partial_graph_rebase_branch_records = staticmethod(GraphRebaseContinuation._partial_graph_rebase_branch_records)

    _payload_has_partial_graph_rebase_execution = staticmethod(GraphRebaseContinuation._payload_has_partial_graph_rebase_execution)

    def prepare_terminal_partial_graph_rebase_successor(
        self,
        response_payload: dict[str, Any],
        *,
        proposal_id: str,
        trusted_authorization: Optional[dict[str, Any]],
        graph_rebase_autonomy: Optional[str] = None,
    ) -> dict[str, Any]:
        return self.graph_rebase_continuation.prepare_terminal_partial_graph_rebase_successor(response_payload, proposal_id=proposal_id, trusted_authorization=trusted_authorization, graph_rebase_autonomy=graph_rebase_autonomy)

    def _graph_rebase_root_prompt(self, payload: Any) -> str:
        """Resolve current-turn request truth only for root-replay rejection."""

        if not isinstance(payload, dict):
            return ''
        candidates = [
            payload.get('request') if isinstance(payload.get('request'), dict) else None,
            payload,
        ]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            for key in ('prompt', 'prompt_text', 'current_turn_prompt'):
                direct_prompt = str(candidate.get(key) or '').strip()
                if direct_prompt:
                    return direct_prompt
            for hook_name in (
                'extract_responses_current_turn_prompt',
                'extract_responses_prompt',
            ):
                try:
                    prompt = str(self._hook(hook_name)(candidate) or '').strip()
                except (KeyError, TypeError, ValueError):
                    prompt = ''
                if prompt:
                    return prompt
        return ''

    _collect_explicit_graph_rebase_proposals = staticmethod(GraphRebaseContinuation._collect_explicit_graph_rebase_proposals)

    def _attach_runtime_graph_rebase_evidence(
        self,
        response_payload: dict[str, Any],
        *,
        root_prompt: str = '',
    ) -> dict[str, Any]:
        return self.graph_rebase_continuation._attach_runtime_graph_rebase_evidence(response_payload, root_prompt=root_prompt)

    def review_terminal_graph_rebase_after_late_fill(
        self,
        response_payload: dict[str, Any],
        *,
        request_payload: Optional[dict[str, Any]] = None,
        route_payload: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        return self.graph_rebase_continuation.review_terminal_graph_rebase_after_late_fill(response_payload, request_payload=request_payload, route_payload=route_payload)

    def _attach_graph_rebase_lifecycle(
        self,
        response_payload: dict[str, Any],
        *,
        graph_rebase_autonomy: Optional[str] = None,
    ) -> dict[str, Any]:
        return self.graph_rebase_continuation._attach_graph_rebase_lifecycle(response_payload, graph_rebase_autonomy=graph_rebase_autonomy)

    def _attach_repair_gap_to_request_phase_graph(
        self,
        response_payload: dict[str, Any],
        repair_gap: dict[str, Any],
    ) -> dict[str, Any]:
        return self.terminal_repair_projection._attach_repair_gap_to_request_phase_graph(response_payload, repair_gap)

    def project_terminal_closure_repair(
        self,
        response_payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self.terminal_repair_projection.project_terminal_closure_repair(
            response_payload,
            repair_feedback_gap=self._inference_repair_feedback_gap,
            attach_repair_gap=self._attach_repair_gap_to_request_phase_graph,
        )

    @observe_state('responses.pre_freeze_closure', 'graph_branch_artifact_state', 'closure_reviewed_response', labels=('NEW_AUTHORITY_BOUNDARY',), new_authority_boundary=True)
    def attach_pre_freeze_closure_review(
        self,
        response_payload: dict[str, Any],
        *,
        output_text: str,
        route_payload: Optional[dict[str, Any]] = None,
        request_payload: Optional[dict[str, Any]] = None,
        artifact_gap: Optional[dict[str, Any]] = None,
    ) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
        build_pre_freeze_closure_review_gap = self._hook('build_pre_freeze_closure_review_gap')
        build_late_fill_state = self._hook('build_late_fill_state')
        attach_late_fill_state = self._hook('attach_late_fill_state')

        def _clean_capability(value: Any) -> str:
            return re.sub(r'[^a-z0-9_]+', '_', str(value or '').strip().lower()).strip('_')

        def _has_direct_dependency_evidence() -> bool:
            for source in (response_payload, request_payload or {}, route_payload or {}):
                if not isinstance(source, dict):
                    continue
                for key in ('input_artifacts', 'reference_artifacts', 'selected_reference_artifacts'):
                    if isinstance(source.get(key), list) and source.get(key):
                        return True
                    if isinstance(source.get(key), dict) and source.get(key):
                        return True
                for key in (
                    'file_path',
                    'artifact_path',
                    'artifact_ref',
                    'route_artifact_path',
                    'route_artifact_ref',
                    'saved_image_path',
                    'saved_audio_path',
                    'saved_text_path',
                ):
                    if str(source.get(key) or '').strip():
                        return True
            return False

        def _gap_is_satisfied_by_direct_target(gap: Any) -> bool:
            if not isinstance(gap, dict) or not gap:
                return False
            target_capability = _clean_capability(
                response_payload.get('capability')
                or (route_payload or {}).get('capability')
                or (request_payload or {}).get('capability')
            )
            if not target_capability or target_capability == self.capability_chat:
                return False
            if not str(response_payload.get('output_text') or '').strip():
                return False
            if not _has_direct_dependency_evidence():
                return False
            pending_branches = [
                item for item in (gap.get('pending_branches') or []) if isinstance(item, dict)
            ]
            capability_tokens = {
                _clean_capability(gap.get('expected_capability')),
                _clean_capability(gap.get('active_capability')),
            }
            capability_tokens.update(
                _clean_capability(item)
                for item in (gap.get('pending_capabilities') or [])
                if str(item or '').strip()
            )
            capability_tokens.update(
                _clean_capability(branch.get('capability'))
                for branch in pending_branches
                if str(branch.get('capability') or '').strip()
            )
            capability_tokens.discard('')
            if not capability_tokens:
                return False
            return capability_tokens == {target_capability}

        def _late_fill_extra_from_closure_review(review: Any) -> dict[str, Any]:
            if not isinstance(review, dict):
                return {}
            extra: dict[str, Any] = {}
            if review.get('surface_state') not in (None, '', [], {}):
                extra['surface_state'] = review.get('surface_state')
            if review.get('global_semantic_closure_review') not in (None, '', [], {}):
                extra['global_semantic_closure_review'] = review.get('global_semantic_closure_review')
            decision_contract_review = review.get('decision_contract_review')
            if isinstance(decision_contract_review, dict):
                for key in (
                    'active_reconsideration_review',
                    'semantic_quality_review',
                    'recursive_cycle_review',
                    'aspiration_review',
                    'commitment_review',
                    'semantic_decision_review',
                    'controlled_attention_review',
                ):
                    if decision_contract_review.get(key) not in (None, '', [], {}):
                        extra[key] = decision_contract_review.get(key)
            return extra

        def _project_graph_patch_reconciliation_to_late_fill(
            state: Any,
            reconciliation: Any,
            *,
            extra: Optional[dict[str, Any]] = None,
        ) -> dict[str, Any]:
            projected = dict(state) if isinstance(state, dict) else {}
            if not isinstance(reconciliation, dict) or not reconciliation:
                if isinstance(extra, dict):
                    projected.update(extra)
                return projected
            projected['graph_patch_reconciliation'] = dict(reconciliation)
            existing_blocked = [
                dict(item)
                for item in (projected.get('blocked_branches') or [])
                if isinstance(item, dict)
            ]
            blocked_by_id = {
                str(item.get('branch_id') or item.get('phase_id') or '').strip(): index
                for index, item in enumerate(existing_blocked)
                if str(item.get('branch_id') or item.get('phase_id') or '').strip()
            }
            for item in reconciliation.get('unscheduled_branches') or []:
                if not isinstance(item, dict):
                    continue
                branch_id = str(item.get('branch_id') or item.get('phase_id') or '').strip()
                if not branch_id:
                    continue
                blocked_record = {**dict(item), 'status': 'blocked'}
                if branch_id in blocked_by_id:
                    existing_blocked[blocked_by_id[branch_id]] = blocked_record
                else:
                    blocked_by_id[branch_id] = len(existing_blocked)
                    existing_blocked.append(blocked_record)
            if existing_blocked:
                projected['blocked_branches'] = existing_blocked
            if isinstance(extra, dict):
                projected.update(extra)
            return projected

        response_payload, _phase_graph = self._attach_fluid_request_phase_graph(
            response_payload,
            output_text=output_text,
            route_payload=route_payload,
            request_payload=request_payload,
        )
        if _truth_guard_blocks_materialization(response_payload):
            runtime = (
                dict(response_payload.get('runtime') or {})
                if isinstance(response_payload.get('runtime'), dict)
                else {}
            )
            truth_guard = runtime.get('truth_guard') if isinstance(runtime.get('truth_guard'), dict) else {}
            truth_guard_status = str(truth_guard.get('status') or '').strip().lower()
            phase_acceptance = (
                runtime.get('phase_output_acceptance')
                if isinstance(runtime.get('phase_output_acceptance'), dict)
                else {}
            )
            control_payload_rejected = truth_guard_status == 'repair_required'
            check_kind = (
                'prepared_substantive_text_accepted'
                if control_payload_rejected
                else 'truth_guard'
            )
            evidence = (
                'control_envelope_not_speakable'
                if control_payload_rejected
                else 'clarification_required'
            )
            reason = str(truth_guard.get('reason') or '').strip() or (
                'current phase returned internal control data instead of substantive content'
                if control_payload_rejected
                else 'current turn needs a concrete source before materialization'
            )
            response_payload['lifecycle_state'] = 'repair_needed'
            response_payload = self._attach_graph_closure_review_diagnostics(
                response_payload,
                _compact_payload(
                    {
                        'kind': 'fruth.graph_closure_review',
                        'status': 'blocked',
                        'surface_state': {
                            'state': 'repair_needed',
                            'reason': reason,
                        },
                        'checks': [
                            {
                                'check_kind': check_kind,
                                'status': 'blocked',
                                'evidence': evidence,
                                'reason': reason,
                                'repair_action': 'repair_branch_contract',
                                'recovery_action': 'repair_branch_contract',
                                **(
                                    {'acceptance_status': 'repair_required'}
                                    if control_payload_rejected
                                    else {}
                                ),
                                **(
                                    {'attempt_count': phase_acceptance.get('attempt_count')}
                                    if phase_acceptance.get('attempt_count') not in (None, '')
                                    else {}
                                ),
                            }
                        ],
                    }
                ),
            )
            response_payload = self.graph_patch_continuation._attach_redraw_scope_ladder_review(response_payload)
            response_payload = self.graph_patch_continuation._attach_runtime_graph_repair_evidence(response_payload)
            response_payload = self.graph_patch_continuation._attach_graph_patch_lifecycle(response_payload)
            response_payload = self.graph_rebase_continuation._attach_runtime_graph_rebase_evidence(
                response_payload,
                root_prompt=self._graph_rebase_root_prompt(request_payload),
            )
            response_payload = self.graph_rebase_continuation._attach_graph_rebase_lifecycle(response_payload)
            return response_payload, None
        closure_gap = build_pre_freeze_closure_review_gap(
            output_text,
            route_payload=route_payload,
            request_payload=request_payload,
            artifact_payload=response_payload,
            artifact_gap=artifact_gap,
        )
        build_graph_closure_review = self._hook('build_graph_closure_review')
        graph_closure_review = build_graph_closure_review(
            output_text,
            route_payload=route_payload,
            request_payload=request_payload,
            artifact_payload=response_payload,
            artifact_gap=closure_gap if isinstance(closure_gap, dict) else artifact_gap,
        )
        repair_gap = self._inference_repair_feedback_gap(
            graph_closure_review,
            prior_gap=closure_gap if isinstance(closure_gap, dict) else None,
        )
        if _gap_is_satisfied_by_direct_target(repair_gap or closure_gap):
            graph_closure_review = dict(graph_closure_review)
            graph_closure_review['direct_target_fulfillment'] = {
                'status': 'satisfied',
                'capability': str(response_payload.get('capability') or '').strip(),
                'reason': 'primary response already fulfilled the same artifact-backed capability',
            }
            graph_closure_review.pop('inference_repair_feedback', None)
            graph_closure_review.pop('repair_gap_code', None)
            graph_closure_review.pop('repair_gap_trigger', None)
            if str(graph_closure_review.get('status') or '').strip().lower() in {'blocked', 'pending'}:
                graph_closure_review['status'] = 'completed'
            surface_state = (
                dict(graph_closure_review.get('surface_state') or {})
                if isinstance(graph_closure_review.get('surface_state'), dict)
                else {}
            )
            if str(surface_state.get('state') or '').strip().lower() in {'blocked', 'repair_needed', 'pending'}:
                surface_state['state'] = 'completed'
                surface_state['reason'] = 'direct target response fulfilled the current artifact-backed request'
                graph_closure_review['surface_state'] = surface_state
            closure_gap = None
            repair_gap = None
        if repair_gap:
            response_payload = self._attach_repair_gap_to_request_phase_graph(response_payload, repair_gap)
            closure_gap = repair_gap
            graph_closure_review = dict(graph_closure_review)
            graph_closure_review['repair_gap_code'] = str(repair_gap.get('code') or '').strip() or None
            graph_closure_review['repair_gap_trigger'] = str(repair_gap.get('trigger') or '').strip() or None
            graph_closure_review['repair_pending_branch_count'] = len(repair_gap.get('pending_branches') or [])
        response_payload = self._attach_graph_closure_review_diagnostics(
            response_payload,
            _compact_payload(graph_closure_review),
        )
        prior_late_fill = (
            response_payload.get('late_fill')
            if isinstance(response_payload.get('late_fill'), dict)
            else None
        )
        late_fill_extra = _late_fill_extra_from_closure_review(graph_closure_review)
        if isinstance(closure_gap, dict) and closure_gap:
            pending_late_fill = build_late_fill_state(
                closure_gap,
                status='pending',
                prior_state=prior_late_fill,
                extra=late_fill_extra,
            )
            if isinstance(closure_gap.get('graph_patch_reconciliation'), dict):
                pending_late_fill['graph_patch_reconciliation'] = dict(
                    closure_gap['graph_patch_reconciliation']
                )
            response_payload = attach_late_fill_state(response_payload, pending_late_fill)
        response_payload = self.graph_patch_continuation._attach_redraw_scope_ladder_review(response_payload)
        response_payload = self.graph_patch_continuation._attach_runtime_graph_repair_evidence(response_payload)
        response_payload = self.graph_patch_continuation._attach_graph_patch_lifecycle(response_payload)
        response_payload, closure_gap = self.graph_patch_continuation._reconcile_applied_graph_patch_late_fill_gap(
            response_payload,
            closure_gap if isinstance(closure_gap, dict) else None,
        )
        response_runtime = (
            response_payload.get('runtime')
            if isinstance(response_payload.get('runtime'), dict)
            else {}
        )
        response_diagnostics = (
            response_runtime.get('developer_diagnostics')
            if isinstance(response_runtime.get('developer_diagnostics'), dict)
            else {}
        )
        graph_patch_reconciliation = (
            closure_gap.get('graph_patch_reconciliation')
            if isinstance(closure_gap, dict)
            and isinstance(closure_gap.get('graph_patch_reconciliation'), dict)
            else response_diagnostics.get('graph_patch_late_fill_reconciliation')
            if isinstance(response_diagnostics.get('graph_patch_late_fill_reconciliation'), dict)
            else {}
        )
        if (
            str(graph_patch_reconciliation.get('status') or '').strip().lower()
            in {'applied', 'no_executable_branches'}
            and graph_patch_reconciliation.get('patch_ids')
        ):
            graph_closure_review = build_graph_closure_review(
                output_text,
                route_payload=route_payload,
                request_payload=request_payload,
                artifact_payload=response_payload,
                artifact_gap=closure_gap,
            )
            response_payload = self._attach_graph_closure_review_diagnostics(
                response_payload,
                _compact_payload(graph_closure_review),
            )
            late_fill_extra = _late_fill_extra_from_closure_review(graph_closure_review)
        if isinstance(closure_gap, dict) and closure_gap:
            prior_late_fill = (
                response_payload.get('late_fill')
                if isinstance(response_payload.get('late_fill'), dict)
                else prior_late_fill
            )
            pending_late_fill = build_late_fill_state(
                closure_gap,
                status='pending',
                prior_state=prior_late_fill,
                extra=late_fill_extra,
            )
            if isinstance(closure_gap.get('graph_patch_reconciliation'), dict):
                pending_late_fill = _project_graph_patch_reconciliation_to_late_fill(
                    pending_late_fill,
                    closure_gap['graph_patch_reconciliation'],
                    extra=late_fill_extra,
                )
            response_payload = attach_late_fill_state(response_payload, pending_late_fill)
        elif (
            str(graph_patch_reconciliation.get('status') or '').strip().lower()
            == 'no_executable_branches'
        ):
            current_late_fill = (
                response_payload.get('late_fill')
                if isinstance(response_payload.get('late_fill'), dict)
                else {}
            )
            blocked_late_fill = _project_graph_patch_reconciliation_to_late_fill(
                current_late_fill,
                graph_patch_reconciliation,
                extra=late_fill_extra,
            )
            blocked_late_fill['status'] = 'blocked'
            blocked_late_fill['pending_branches'] = []
            blocked_late_fill['pending_capabilities'] = []
            blocked_late_fill['expected_capability'] = None
            blocked_late_fill['active_capability'] = None
            response_payload = attach_late_fill_state(response_payload, blocked_late_fill)
        response_payload = self.graph_patch_continuation._attach_redraw_scope_ladder_review(response_payload)
        response_payload = self.graph_rebase_continuation._attach_runtime_graph_rebase_evidence(
            response_payload,
            root_prompt=self._graph_rebase_root_prompt(request_payload),
        )
        response_payload = self.graph_rebase_continuation._attach_graph_rebase_lifecycle(response_payload)
        return response_payload, closure_gap if isinstance(closure_gap, dict) and closure_gap else None

    def _direct_batch_aspect_ratios(
        self,
        *,
        prompt_text: str,
        prompt_intent: dict[str, Any],
        infer_payload: dict[str, Any],
        direct_batch_count: int,
    ) -> list[Optional[str]]:
        if direct_batch_count <= 1:
            return []
        explicit_ratio = str(prompt_intent.get('image_aspect_ratio') or '').strip().lower()
        if explicit_ratio:
            return []
        if infer_payload.get('width') not in (None, '') or infer_payload.get('height') not in (None, ''):
            return []
        if not _DIRECT_BATCH_VARIED_ASPECT_RATIO_RE.search(str(prompt_text or '').strip()):
            return []
        ratios: list[Optional[str]] = []
        for index in range(direct_batch_count):
            ratios.append(_DIRECT_BATCH_VARIANT_ASPECT_RATIO_CYCLE[index % len(_DIRECT_BATCH_VARIANT_ASPECT_RATIO_CYCLE)])
        return ratios

    def _build_direct_batch_variant_prompt(
        self,
        *,
        base_prompt: str,
        index: int,
        total: int,
        matching_outputs: bool,
        aspect_ratio: Optional[str],
    ) -> str:
        prompt = str(base_prompt or '').strip()
        if not prompt or total <= 1:
            return prompt
        instructions = [f'Batch variant guidance: this is image {index} of {total}.']
        if matching_outputs:
            instructions.append(
                'Keep it aligned with the same core scene and subject as the other requested images.'
            )
        else:
            instructions.append(
                'Keep the user request intact, but make this image clearly distinct from the other requested images.'
            )
            instructions.append(
                'Vary composition, framing, perspective, lighting, and scene details, and choose a different subject whenever the request leaves that choice open.'
            )
        if aspect_ratio:
            instructions.append(f'Compose this variant for a {aspect_ratio} aspect ratio.')
        return f"{prompt}\n\n[{' '.join(instructions)}]"

    def build_direct_image_batch_items(
        self,
        request_payload: dict[str, Any],
        route_info: Optional[dict[str, Any]],
        infer_payload: dict[str, Any],
        *,
        direct_batch_count: int,
    ) -> list[dict[str, Any]]:
        prompt_text = self._direct_batch_prompt_text(request_payload, route_info, infer_payload)
        base_prompt = str(prompt_text or '').strip()
        if not base_prompt or direct_batch_count <= 1:
            return []
        prompt_intent = self._extract_direct_batch_prompt_intent(route_info)
        matching_outputs = self._direct_batch_requests_matching_outputs(prompt_text)
        aspect_ratios = self._direct_batch_aspect_ratios(
            prompt_text=prompt_text,
            prompt_intent=prompt_intent,
            infer_payload=infer_payload,
            direct_batch_count=direct_batch_count,
        )
        batch_items: list[dict[str, Any]] = []
        for index in range(direct_batch_count):
            aspect_ratio = aspect_ratios[index] if index < len(aspect_ratios) else None
            batch_items.append(
                {
                    'prompt': self._build_direct_batch_variant_prompt(
                        base_prompt=base_prompt,
                        index=index + 1,
                        total=direct_batch_count,
                        matching_outputs=matching_outputs,
                        aspect_ratio=aspect_ratio,
                    ),
                    'width': None,
                    'height': None,
                    'aspect_ratio': aspect_ratio,
                }
            )
        return batch_items

    def build_direct_batch_branch_specs(
        self,
        *,
        batch_items: list[dict[str, Any]],
        capability: str,
        base_request_payload: dict[str, Any],
        base_route_info: Optional[dict[str, Any]],
        base_instance_id: str,
        base_instance: Optional[dict[str, Any]],
        forced_instance_id: Optional[str],
        upload: Any,
    ) -> list[dict[str, Any]]:
        branch_specs: list[dict[str, Any]] = []
        resolved_request_forced_instance_id = str(forced_instance_id or '').strip()
        request_instance_id = (
            str((base_request_payload or {}).get('instance_id') or '').strip()
            if isinstance(base_request_payload, dict)
            else ''
        )
        effective_forced_instance_id = (
            resolved_request_forced_instance_id or request_instance_id
        )
        for index, batch_item in enumerate(batch_items, start=1):
            prompt = str(batch_item.get('prompt') or '').strip()
            if not prompt:
                continue
            branch_request_payload = dict(base_request_payload)
            branch_request_payload['capability'] = capability
            branch_request_payload['prompt'] = prompt
            branch_request_payload, batch_error = self.apply_batch_image_dimensions(
                branch_request_payload,
                batch_item,
            )
            if batch_error:
                raise ValueError(batch_error)
            branch_request_payload.pop('instance_id', None)
            branch_specs.append(
                {
                    'branch_id': f'direct-batch-{index}',
                    'phase_id': f'direct-batch-{index}',
                    'capability': capability,
                    'reservation_group': capability,
                    'batch_index': index,
                    'prompt': prompt,
                    'branch': {
                        'branch_id': f'direct-batch-{index}',
                        'phase_id': f'direct-batch-{index}',
                        'capability': capability,
                        'batch_index': index,
                        'prompt': prompt,
                    },
                    'prepare_args': {
                        'branch': {
                            'branch_id': f'direct-batch-{index}',
                            'phase_id': f'direct-batch-{index}',
                            'capability': capability,
                            'batch_index': index,
                            'prompt': prompt,
                        },
                        'branch_request_payload': branch_request_payload,
                        'base_route_info': dict(base_route_info or {}) if isinstance(base_route_info, dict) else None,
                        'base_instance_id': str(base_instance_id or '').strip(),
                        'base_instance': dict(base_instance or {}) if isinstance(base_instance, dict) else None,
                        'allow_base_instance_reuse': index == 1,
                        'forced_instance_id': effective_forced_instance_id or None,
                        'upload': upload,
                    },
                }
            )
        return branch_specs

    def prepare_direct_materialization_branch_plan(
        self,
        *,
        branch: dict[str, Any],
        branch_request_payload: dict[str, Any],
        base_route_info: Optional[dict[str, Any]],
        base_instance_id: str,
        base_instance: Optional[dict[str, Any]],
        allow_base_instance_reuse: bool = False,
        forced_instance_id: Optional[str],
        upload: Any,
        excluded_instance_ids: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        parse_bool = self._hook('parse_bool')
        resolve_inference_auto_route = self._hook('resolve_inference_auto_route')
        resolve_responses_target_instance = self._hook('resolve_responses_target_instance')
        normalize_backend = self._hook('normalize_backend')
        normalize_capability = self._hook('normalize_capability')
        select_backend_request_model = self._hook('select_backend_request_model')
        build_responses_infer_execution_payload = self._hook('build_responses_infer_execution_payload')

        branch_payload = dict(branch_request_payload or {})
        branch_id = str(branch.get('branch_id') or branch.get('phase_id') or '').strip()
        capability = normalize_capability(branch.get('capability') or branch_payload.get('capability')) or ''
        excluded = [
            str(item).strip()
            for item in (excluded_instance_ids or [])
            if str(item).strip()
        ]
        if capability and not str(branch_payload.get('capability') or '').strip():
            branch_payload['capability'] = capability
        route_info: Optional[dict[str, Any]] = None
        instance_id = ''
        instance: Optional[dict[str, Any]] = None
        resolved_capability = capability or None
        resolution_error: Optional[str] = None
        forced_pin = str(forced_instance_id or '').strip()
        branch_pin = str(branch_payload.get('instance_id') or '').strip()
        pinned_instance_id = forced_pin or branch_pin
        if pinned_instance_id and pinned_instance_id in excluded and not forced_pin:
            pinned_instance_id = ''

        if pinned_instance_id:
            instance_id, instance, resolved_capability, resolution_error = resolve_responses_target_instance(
                branch_payload,
                forced_instance_id=pinned_instance_id,
            )
        elif parse_bool(branch_payload.get('inference_route'), default=False):
            if allow_base_instance_reuse and not excluded and isinstance(base_route_info, dict):
                route_info = dict(base_route_info)
                instance_id = str(route_info.get('instance_id') or base_instance_id or '').strip()
                route_instance = route_info.get('instance')
                if isinstance(route_instance, dict):
                    instance = dict(route_instance)
                elif isinstance(base_instance, dict):
                    instance = dict(base_instance)
            else:
                route_info, resolution_error = resolve_inference_auto_route(
                    branch_payload,
                    upload=None,
                    excluded_instance_ids=excluded,
                )
                instance_id = str((route_info or {}).get('instance_id') or '').strip()
                route_instance = (route_info or {}).get('instance')
                if isinstance(route_instance, dict):
                    instance = dict(route_instance)
                resolved_capability = normalize_capability((route_info or {}).get('capability')) or resolved_capability
        else:
            if allow_base_instance_reuse and not excluded and str(base_instance_id or '').strip() and isinstance(base_instance, dict):
                instance_id = str(base_instance_id or '').strip()
                instance = dict(base_instance)
            else:
                instance_id, instance, resolved_capability, resolution_error = resolve_responses_target_instance(
                    branch_payload,
                    excluded_instance_ids=excluded,
                )

        if resolution_error:
            raise RuntimeError(resolution_error)
        if not instance_id or not isinstance(instance, dict):
            raise RuntimeError(f"Direct batch branch '{branch_id or capability or 'unknown'}' could not resolve an instance.")

        if not isinstance(route_info, dict):
            route_info = {}
            if isinstance(base_route_info, dict):
                for key in (
                    'route_source',
                    'route_reason',
                    'route_confidence',
                    'route_reuse_last_artifact',
                    'route_artifact_ref',
                    'route_artifact_path',
                    'route_runtime',
                    'request_meta',
                ):
                    value = base_route_info.get(key)
                    if value not in (None, '', [], {}):
                        route_info[key] = dict(value) if isinstance(value, dict) else value
            route_info['route_source'] = str(route_info.get('route_source') or 'responses_batch').strip() or 'responses_batch'
            route_info['route_reason'] = str(route_info.get('route_reason') or 'direct explicit batch item materialization').strip() or 'direct explicit batch item materialization'
        route_info['instance_id'] = instance_id
        route_info['instance'] = dict(instance)
        route_info['capability'] = normalize_capability(route_info.get('capability') or resolved_capability or capability) or capability

        backend = normalize_backend(branch_payload.get('backend') or instance.get('backend'))
        request_model_override = select_backend_request_model(
            instance,
            branch_payload.get('request_model') or instance.get('request_model'),
            branch_payload.get('model') or instance.get('model'),
        ) or str(branch_payload.get('model') or instance.get('model') or '').strip()
        infer_payload, route_info, _has_file_context, expose_input_artifacts = build_responses_infer_execution_payload(
            branch_payload,
            route_info=route_info,
            instance=instance,
            instance_id=instance_id,
            backend=backend,
            capability=route_info['capability'],
            request_model_override=request_model_override,
            upload_present=bool(upload and getattr(upload, 'filename', None)),
        )
        return {
            'capability': route_info['capability'],
            'route_info': route_info,
            'instance': instance,
            'effective_data': branch_payload,
            'infer_payload': infer_payload,
            'expose_input_artifacts': expose_input_artifacts,
            'upload': upload,
        }

    def execute_prepared_materialization_branch(self, plan: dict[str, Any]) -> dict[str, Any]:
        invoke_internal_api_json_route = self._hook('invoke_internal_api_json_route')
        filter_responses_infer_result = self._hook('filter_responses_infer_result')

        infer_payload = plan.get('infer_payload') if isinstance(plan.get('infer_payload'), dict) else {}
        infer_result, status_code = invoke_internal_api_json_route(
            payload=infer_payload,
            upload=plan.get('upload'),
        )
        if status_code >= 400:
            preparation_error = PdfPreparationError.from_response(infer_result)
            if preparation_error is not None:
                raise preparation_error
            raise _MaterializationExecutionError(
                str(infer_result.get('error') or 'Request failed.'),
                status_code=status_code,
            )
        infer_result = filter_responses_infer_result(
            infer_result,
            expose_input_artifacts=bool(plan.get('expose_input_artifacts')),
        )
        infer_result = self._attach_tts_audio_integrity_evidence(
            infer_result,
            capability=plan.get('capability'),
            infer_payload=infer_payload,
        )
        return {
            'capability': str(plan.get('capability') or '').strip() or None,
            'route_info': plan.get('route_info') if isinstance(plan.get('route_info'), dict) else {},
            'instance': plan.get('instance') if isinstance(plan.get('instance'), dict) else {},
            'effective_data': plan.get('effective_data') if isinstance(plan.get('effective_data'), dict) else {},
            'infer_result': infer_result if isinstance(infer_result, dict) else {},
        }

    def build_preview_instance_payload(self, instance: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        normalize_backend = self._hook('normalize_backend')
        normalize_capability = self._hook('normalize_capability')
        infer_supported_capabilities = self._hook('infer_supported_capabilities')
        instance_effective_capability = self._hook('instance_effective_capability')
        compact_string_list = self._hook('compact_string_list')
        summarize_backend_metadata_for_routing = self._hook('summarize_backend_metadata_for_routing')
        summarize_backend_runtime_for_routing = self._hook('summarize_backend_runtime_for_routing')
        summarize_session_controls_for_routing = self._hook('summarize_session_controls_for_routing')

        if not isinstance(instance, dict):
            return None
        runtime_status = instance.get('runtime_status') if isinstance(instance.get('runtime_status'), dict) else {}
        supported_capabilities = [
            item for item in (
                instance.get('supported_capabilities')
                or infer_supported_capabilities(
                    str(instance.get('model') or instance.get('modelName') or '').strip(),
                    instance.get('backend'),
                    instance.get('capability'),
                    metadata=instance,
                )
            )
            if isinstance(item, str) and item
        ]
        return {
            'instance_id': str(instance.get('instance_id') or '').strip() or None,
            'model': str(instance.get('model') or instance.get('modelName') or '').strip() or None,
            'backend': normalize_backend(instance.get('backend')),
            'capability': normalize_capability(instance.get('capability')) or instance_effective_capability(instance),
            'supported_capabilities': supported_capabilities,
            'text_capable': bool(
                instance.get('text_capable')
                if isinstance(instance.get('text_capable'), bool)
                else self.capability_chat in supported_capabilities
            ),
            'backend_package': str(instance.get('backend_package') or '').strip() or None,
            'backend_contract': str(instance.get('backend_contract') or '').strip() or None,
            'provider_capabilities': compact_string_list(instance.get('provider_capabilities')),
            'backend_metadata': summarize_backend_metadata_for_routing(instance.get('backend_metadata')),
            'backend_runtime': summarize_backend_runtime_for_routing(runtime_status.get('backend_runtime')),
            'session_controls': instance.get('session_controls') if isinstance(instance.get('session_controls'), dict) else {},
            'session_controls_summary': summarize_session_controls_for_routing(instance.get('session_controls')),
            'tts_model_type': str(instance.get('tts_model_type') or '').strip() or None,
            'tts_speakers': instance.get('tts_speakers') if isinstance(instance.get('tts_speakers'), list) else [],
            'tts_languages': instance.get('tts_languages') if isinstance(instance.get('tts_languages'), list) else [],
            'readiness': str(runtime_status.get('readiness') or instance.get('readiness') or '').strip() or None,
            'activity': str(runtime_status.get('activity') or instance.get('activity') or '').strip() or None,
        }

    def build_inference_route_preview_payload(
        self,
        route_info: dict[str, Any],
        request_payload: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        build_working_frame = self._hook('build_working_frame')

        route_runtime = route_info.get('route_runtime') if isinstance(route_info.get('route_runtime'), dict) else {}
        context_strategy = route_runtime.get('context_strategy') if isinstance(route_runtime.get('context_strategy'), dict) else {}
        working_frame = route_runtime.get('working_frame') if isinstance(route_runtime.get('working_frame'), dict) else {}
        if not working_frame:
            working_frame = build_working_frame(
                request_payload=request_payload,
                route_payload=route_info,
                freeze=False,
            )
            if working_frame:
                route_runtime = dict(route_runtime)
                route_runtime['working_frame'] = working_frame
        payload = {
            'instance': self.build_preview_instance_payload(route_info.get('instance')),
            'route': {
                'source': route_info.get('route_source'),
                'reason': route_info.get('route_reason'),
                'confidence': route_info.get('route_confidence'),
                'reuse_last_artifact': route_info.get('route_reuse_last_artifact'),
                'artifact_ref': route_info.get('route_artifact_ref'),
                'artifact_path': route_info.get('route_artifact_path'),
                'context_mode': context_strategy.get('mode'),
                'context_reason': context_strategy.get('reason'),
                'traits': route_runtime.get('route_traits') if isinstance(route_runtime.get('route_traits'), dict) else None,
            },
        }
        request_meta = route_info.get('request_meta') if isinstance(route_info.get('request_meta'), dict) else (
            route_runtime.get('request_meta') if isinstance(route_runtime.get('request_meta'), dict) else {}
        )
        if request_meta:
            payload['request_meta'] = request_meta
        if route_runtime:
            payload['runtime'] = route_runtime
        if working_frame:
            payload['working_frame'] = working_frame
        return payload

    def attach_backend_handoff_truth_to_request_payload(
        self,
        data: Any,
        route_info: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        payload = dict(data if isinstance(data, dict) else dict(data or {}))
        if not isinstance(route_info, dict) or not route_info:
            return payload

        route_runtime = route_info.get('route_runtime') if isinstance(route_info.get('route_runtime'), dict) else {}
        request_meta = route_info.get('request_meta') if isinstance(route_info.get('request_meta'), dict) else (
            route_runtime.get('request_meta') if isinstance(route_runtime.get('request_meta'), dict) else {}
        )
        if request_meta and payload.get('request_meta') in (None, '', [], {}):
            payload['request_meta'] = request_meta

        if payload.get('inference_preview') in (None, '', [], {}):
            preview_payload = self.build_inference_route_preview_payload(
                route_info,
                request_payload=payload,
            )
            if preview_payload:
                payload['inference_preview'] = preview_payload
        return payload

    def refresh_live_route_target(
        self,
        *,
        request_payload: dict[str, Any],
        route_info: Optional[dict[str, Any]],
        instance_id: Optional[str],
        instance: Optional[dict[str, Any]],
        resolved_capability: Optional[str],
    ) -> tuple[Optional[str], Optional[dict[str, Any]], Optional[str], Optional[dict[str, Any]], Optional[str]]:
        resolve_responses_target_instance = self._hook('resolve_responses_target_instance')
        normalize_backend = self._hook('normalize_backend')
        normalize_capability = self._hook('normalize_capability')

        route_payload = route_info if isinstance(route_info, dict) else {}
        if not route_payload or not str(instance_id or '').strip():
            return instance_id, instance, resolved_capability, route_info, None

        route_instance = route_payload.get('instance') if isinstance(route_payload.get('instance'), dict) else {}
        rebound_payload = dict(request_payload or {})
        requested_capability = normalize_capability(
            route_payload.get('capability')
            or resolved_capability
            or rebound_payload.get('capability')
        )
        if requested_capability:
            rebound_payload['capability'] = requested_capability
        backend_hint = normalize_backend(
            route_payload.get('backend')
            or route_instance.get('backend')
            or rebound_payload.get('backend')
        )
        if backend_hint:
            rebound_payload['backend'] = backend_hint
        model_hint = str(
            route_payload.get('model')
            or route_instance.get('model')
            or route_instance.get('modelName')
            or rebound_payload.get('model')
            or rebound_payload.get('modelName')
            or rebound_payload.get('request_model')
            or rebound_payload.get('requestModel')
            or ''
        ).strip()
        if model_hint:
            rebound_payload['model'] = model_hint

        rebound_instance_id, rebound_instance, rebound_capability, rebound_error = resolve_responses_target_instance(
            rebound_payload,
            forced_instance_id=str(instance_id or '').strip(),
        )
        if not rebound_instance_id or not rebound_instance:
            fallback_payload = dict(rebound_payload)
            fallback_payload.pop('instance_id', None)
            fallback_instance_id, fallback_instance, fallback_capability, fallback_error = resolve_responses_target_instance(
                fallback_payload,
            )
            if not fallback_instance_id or not fallback_instance:
                return None, None, fallback_capability or rebound_capability or requested_capability, route_info, (
                    fallback_error or rebound_error
                )
            rebound_instance_id = fallback_instance_id
            rebound_instance = fallback_instance
            rebound_capability = fallback_capability or rebound_capability

        updated_route_info = dict(route_payload)
        updated_route_info['instance_id'] = rebound_instance_id
        updated_route_info['instance'] = rebound_instance
        if model_hint:
            updated_route_info['model'] = model_hint
        if backend_hint:
            updated_route_info['backend'] = backend_hint
        if rebound_capability or requested_capability:
            updated_route_info['capability'] = rebound_capability or requested_capability
        if rebound_instance_id != str(instance_id or '').strip():
            route_runtime = (
                dict(updated_route_info.get('route_runtime') or {})
                if isinstance(updated_route_info.get('route_runtime'), dict)
                else {}
            )
            route_runtime['target_rebound'] = {
                'stale_instance_id': str(instance_id or '').strip(),
                'rebound_instance_id': rebound_instance_id,
                'capability': rebound_capability or requested_capability,
                'reason': 'stale_route_target_rebound',
            }
            updated_route_info['route_runtime'] = route_runtime
        return (
            rebound_instance_id,
            rebound_instance,
            rebound_capability or requested_capability or resolved_capability,
            updated_route_info,
            None,
        )

    @observe_request
    @observe_call('responses_request.handle_responses_request', record_kind='request_invocation')
    def handle_responses_request(
        self,
        *,
        forced_instance_id: Optional[str] = None,
        data_override: Optional[Any] = None,
        upload_override: Any = None,
        _provider_retry: Optional[dict[str, Any]] = None,
    ):
        normalize_request_payload = self._hook('normalize_request_payload')
        parse_bool = self._hook('parse_bool')
        resolve_inference_auto_route = self._hook('resolve_inference_auto_route')
        resolve_responses_target_instance = self._hook('resolve_responses_target_instance')
        log_unified_event = self._hook('log_unified_event')
        prepare_effective_request_data = self._hook('prepare_effective_request_data')
        build_missing_required_session_controls = self._hook('build_missing_required_session_controls')
        normalize_backend = self._hook('normalize_backend')
        select_backend_request_model = self._hook('select_backend_request_model')
        normalize_capability = self._hook('normalize_capability')
        instance_supports_capability = self._hook('instance_supports_capability')
        infer_capability = self._hook('infer_capability')
        normalize_response_lookup_id = self._hook('normalize_response_lookup_id')
        register_response_lookup = self._hook('register_response_lookup')
        touch_response_lookup = self._hook('touch_response_lookup')
        build_canonical_error_response_payload = self._hook('build_canonical_error_response_payload')
        finalize_response_frame_payload = self._hook('finalize_response_frame_payload')
        handle_responses_request = self._hook('handle_responses_request')
        extract_responses_batch_items = self._hook('extract_responses_batch_items')
        parse_float_with_bounds = self._hook('parse_float_with_bounds')
        parse_int_with_bounds = self._hook('parse_int_with_bounds')
        extract_selected_reference_artifacts = self._hook('extract_selected_reference_artifacts')
        select_matching_selected_reference_artifact = self._hook('select_matching_selected_reference_artifact')
        extract_responses_prompt = self._hook('extract_responses_prompt')
        extract_responses_current_turn_prompt = self._hook('extract_responses_current_turn_prompt')
        should_attach_selected_reference_file_context = self._hook('should_attach_selected_reference_file_context')
        extract_responses_messages = self._hook('extract_responses_messages')
        extract_inference_route_messages = self._hook('extract_inference_route_messages')
        inject_selected_reference_into_chat_messages = self._hook('inject_selected_reference_into_chat_messages')
        inject_inference_runtime_policy_into_chat_messages = self._hook('inject_inference_runtime_policy_into_chat_messages')
        inject_prepare_phase_contract_into_chat_messages = self._hook('inject_prepare_phase_contract_into_chat_messages')
        resolve_prepare_phase_contract = self._hook('resolve_prepare_phase_contract')
        build_external_prepare_phase_bounded_task = self._hook('build_external_prepare_phase_bounded_task')
        choose_context_strategy = self._hook('choose_context_strategy')
        apply_context_strategy = self._hook('apply_context_strategy')
        stream_chat_backend_as_responses = self._hook('stream_chat_backend_as_responses')
        execute_chat_backend_request = self._hook('execute_chat_backend_request')
        execute_external_text_target = self._hook('execute_external_text_target')
        validate_external_text_request = self._hook('validate_external_text_request')
        build_external_target_inputs = self._hook('build_external_target_inputs')
        external_execution_failure = self._hook('external_execution_failure')
        persist_generated_text_artifact_if_requested = self._hook('persist_generated_text_artifact_if_requested')
        request_exception_details = self._hook('request_exception_details')
        build_canonical_response_payload = self._hook('build_canonical_response_payload')
        attach_response_semantic_phase_payload = self._hook('attach_response_semantic_phase_payload')
        truth_gate_response_output_claims = self._hook('truth_gate_response_output_claims')
        build_late_fill_state = self._hook('build_late_fill_state')
        attach_late_fill_state = self._hook('attach_late_fill_state')
        ensure_response_lookup_for_payload = self._hook('ensure_response_lookup_for_payload')
        schedule_response_late_fill = self._hook('schedule_response_late_fill')
        schedule_post_response_substrate_hygiene = self.hooks.get('schedule_post_response_substrate_hygiene')
        build_responses_infer_execution_payload = self._hook('build_responses_infer_execution_payload')
        invoke_internal_api_json_route = self._hook('invoke_internal_api_json_route')
        filter_responses_infer_result = self._hook('filter_responses_infer_result')
        build_canonical_batch_response_payload = self._hook('build_canonical_batch_response_payload')
        build_canonical_response_stream_events = self._hook('build_canonical_response_stream_events')
        execute_materialization_branches = self._hook('execute_materialization_branches')
        project_response_payload_for_wire = self._hook('project_response_payload_for_wire')
        promote_current_predecessor_context = self.hooks.get(
            'promote_current_predecessor_context'
        )

        def accept_phase_output(
            raw_text: Any,
            *,
            effective_route_payload: Optional[dict[str, Any]],
            effective_request_payload: dict[str, Any],
            effective_capability: Optional[str],
            retry_same_phase: Optional[Any] = None,
        ) -> tuple[str, list[dict[str, Any]]]:
            source_text = str(raw_text or '').strip()
            is_preparation = phase_output_is_graph_preparation(
                route_payload=effective_route_payload,
                request_payload=effective_request_payload,
                capability=effective_capability,
            )
            explicit_diagnostics = request_explicitly_allows_control_diagnostics(
                request_payload=effective_request_payload,
                route_payload=effective_route_payload,
                capability=effective_capability,
            )
            if explicit_diagnostics or (
                not is_preparation and not control_json_envelope_suspected(source_text)
            ):
                return source_text, []
            attempts = [classify_phase_output_text(source_text)]
            if (
                attempts[-1].get('status') == 'repair_required'
                and is_preparation
                and callable(retry_same_phase)
            ):
                try:
                    retry_text = str(retry_same_phase() or '').strip()
                    attempts.append(classify_phase_output_text(retry_text))
                except Exception as exc:  # noqa: BLE001
                    attempts.append(
                        {
                            'status': 'repair_required',
                            'accepted_text': '',
                            'source_sha256': hashlib.sha256(b'').hexdigest(),
                            'source_bytes': 0,
                            'reason': (
                                'bounded same-phase repair call failed before producing '
                                f'content ({type(exc).__name__})'
                            ),
                        }
                    )
            accepted_text = str(attempts[-1].get('accepted_text') or '').strip()
            if attempts[-1].get('status') == 'repair_required':
                accepted_text = phase_output_repair_notice()
            return accepted_text, attempts

        def maybe_schedule_post_response_substrate_hygiene(
            response_payload: dict[str, Any],
            *,
            route_payload: Optional[dict[str, Any]],
            reason: str,
        ) -> None:
            if not callable(schedule_post_response_substrate_hygiene):
                return
            try:
                schedule_post_response_substrate_hygiene(
                    response_payload,
                    route_payload=route_payload,
                    reason=reason,
                )
            except Exception:  # noqa: BLE001
                logging.exception('Could not schedule post-response substrate hygiene.')

        if data_override is not None:
            data = data_override
            upload = upload_override
            uploads = (
                list(upload_override)
                if isinstance(upload_override, (list, tuple))
                else [upload_override]
                if upload_override is not None
                else []
            )
            is_multipart = False
        else:
            is_multipart = request.content_type and request.content_type.startswith('multipart/form-data')
            if is_multipart:
                data = request.form
                uploads = [
                    item
                    for item in [
                        *request.files.getlist('file'),
                        *request.files.getlist('files'),
                    ]
                    if item is not None and getattr(item, 'filename', None)
                ]
                upload = uploads[0] if uploads else None
            else:
                data = request.get_json(silent=True) or {}
                upload = None
                uploads = []
        data = normalize_request_payload(data)
        direct_target = bool(forced_instance_id or data.get('instance_id'))
        if callable(promote_current_predecessor_context) and _provider_retry is None:
            data = promote_current_predecessor_context(data)
        if uploads:
            for current_upload in uploads:
                data, _materialized_upload = self.materialize_upload_input_artifacts(
                    data,
                    current_upload,
                )
            upload = None

        data = capture_request_intent(data)
        route_info = None
        if _provider_retry is not None:
            # Internal execution continuation: never reinterpret the accepted work.
            route_info = copy.deepcopy(_provider_retry['route_info'])
            instance_id = route_info['instance_id']
            instance = route_info['instance']
            resolved_capability = route_info['capability']
            direct_target = False
        elif not forced_instance_id and parse_bool(data.get('inference_route'), default=False):
            route_info, resolution_error = resolve_inference_auto_route(data, upload=upload)
            if resolution_error:
                status_code = 404 if 'was not found' in resolution_error or 'No running instance' in resolution_error else 400
                return jsonify({'error': resolution_error}), status_code
            instance_id = str((route_info or {}).get('instance_id') or '').strip()
            instance = (route_info or {}).get('instance')
            resolved_capability = str((route_info or {}).get('capability') or '').strip() or None
        else:
            instance_id, instance, resolved_capability, resolution_error = resolve_responses_target_instance(
                data,
                forced_instance_id=forced_instance_id,
            )
            if resolution_error:
                status_code = 404 if 'was not found' in resolution_error or 'No running instance' in resolution_error else 400
                return jsonify({'error': resolution_error}), status_code
        if (
            _provider_retry is None
            and route_info
            and str((route_info or {}).get('route_source') or '').strip().lower() == 'inference_carried'
            and bool((route_info or {}).get('route_reuse_last_artifact'))
            and any(
                str(value or '').strip()
                for value in (
                    (route_info or {}).get('route_artifact_ref'),
                    (route_info or {}).get('route_artifact_path'),
                    data.get('artifact_ref'),
                    data.get('artifact_path'),
                )
            )
        ):
            (
                instance_id,
                instance,
                resolved_capability,
                route_info,
                resolution_error,
            ) = self.refresh_live_route_target(
                request_payload=data,
                route_info=route_info,
                instance_id=instance_id,
                instance=instance if isinstance(instance, dict) else None,
                resolved_capability=resolved_capability,
            )
            if resolution_error:
                status_code = 404 if 'was not found' in resolution_error or 'No running instance' in resolution_error else 400
                return jsonify({'error': resolution_error}), status_code
        if route_info:
            route_runtime = route_info.get('route_runtime') if isinstance(route_info.get('route_runtime'), dict) else {}
            log_unified_event(
                category='responses',
                action='route',
                status='ok',
                instance_id=route_info.get('instance_id'),
                model=(instance or {}).get('model') if isinstance(instance, dict) else None,
                backend=(instance or {}).get('backend') if isinstance(instance, dict) else None,
                capability=route_info.get('capability'),
                route_source=route_info.get('route_source'),
                route_confidence=route_info.get('route_confidence'),
                route_artifact_path=route_info.get('route_artifact_path'),
                prompt_class=route_runtime.get('prompt_class'),
                session_class=route_runtime.get('session_class'),
                message=route_info.get('route_reason'),
            )
            embedding_audit = route_runtime.get('embedding_audit') if isinstance(route_runtime.get('embedding_audit'), dict) else {}
            if embedding_audit.get('available') or embedding_audit.get('attached'):
                log_unified_event(
                    category='responses',
                    action='route_embedding_audit',
                    status=str(embedding_audit.get('status') or 'observed'),
                    instance_id=route_info.get('instance_id'),
                    model=(instance or {}).get('model') if isinstance(instance, dict) else None,
                    backend=(instance or {}).get('backend') if isinstance(instance, dict) else None,
                    capability=route_info.get('capability'),
                    prompt_class=embedding_audit.get('prompt_class'),
                    session_class=route_runtime.get('session_class'),
                    route_hint_capability=(
                        embedding_audit.get('route_hint_capability')
                        or embedding_audit.get('heuristic_capability')
                    ),
                    route_hint_confidence=(
                        embedding_audit.get('route_hint_confidence')
                        if embedding_audit.get('route_hint_confidence') is not None
                        else embedding_audit.get('heuristic_confidence')
                    ),
                    suggested_capability=embedding_audit.get('embedding_capability'),
                    suggested_instance_id=embedding_audit.get('embedding_instance_id'),
                    embedding_score=embedding_audit.get('embedding_score'),
                    embedding_score_gap=embedding_audit.get('embedding_score_gap'),
                    bias_applied=embedding_audit.get('bias_applied'),
                    message=(
                        f"embedding audit: route_hint="
                        f"{embedding_audit.get('route_hint_capability') or embedding_audit.get('heuristic_capability') or 'none'} "
                        f"suggested={embedding_audit.get('embedding_capability') or 'none'} "
                        f"final={embedding_audit.get('final_capability') or 'none'}"
                    ),
                )
        if not instance_id or not instance:
            return jsonify({'error': "Parameter 'instance_id' is missing."}), 400
        is_external_target = (
            str(instance.get('target_kind') or '').strip().lower() == 'external'
        )
        if _provider_retry is None:
            data, route_info, _planner_meta, _control_hints = prepare_effective_request_data(
                data,
                route_info=route_info,
                instance=instance if isinstance(instance, dict) else None,
            )
        if is_external_target:
            route_info = dict(route_info or {})
            route_info.update(
                {
                    'instance_id': instance_id,
                    'instance': instance,
                    'capability': self.capability_chat,
                    'route_source': str(
                        route_info.get('route_source')
                        or 'explicit_external_target'
                    ),
                    'route_reason': str(
                        route_info.get('route_reason')
                        or 'Explicitly selected external ChatGPT target via Codex.'
                    ),
                }
            )
            route_runtime = (
                dict(route_info.get('route_runtime') or {})
                if isinstance(route_info.get('route_runtime'), dict)
                else {}
            )
            route_runtime['external_target'] = {
                'id': instance_id,
                'provider': 'codex_cli',
                'target_kind': 'external',
                'lifecycle_managed': False,
                'text_only': False,
                'inputs': ['text', 'image', 'file'],
                'outputs': ['text'],
                'files_enabled': instance.get('files_enabled') is True,
            }
            route_info['route_runtime'] = route_runtime
        if route_info:
            data = self.attach_backend_handoff_truth_to_request_payload(data, route_info)
        if route_info:
            missing_session_controls = build_missing_required_session_controls(instance, data)
            if missing_session_controls:
                preview_payload = self.build_inference_route_preview_payload(route_info)
                preview_payload['missing_fields'] = missing_session_controls
                return (
                    jsonify(
                        {
                            'error': missing_session_controls[0]['message'],
                            'missing_session_controls': preview_payload,
                        }
                    ),
                    400,
                )

        backend = normalize_backend(data.get('backend') or instance.get('backend'))
        model_name = str(data.get('model') or instance.get('model') or '').strip()
        request_model_override = select_backend_request_model(
            instance,
            data.get('request_model') or instance.get('request_model'),
            data.get('model') or model_name,
        ) or model_name
        requested_capability = str(route_info.get('capability') or '').strip() if route_info else normalize_capability(data.get('capability'))
        instance_capability = normalize_capability(instance.get('capability')) or resolved_capability
        if requested_capability and not instance_supports_capability(instance, requested_capability):
            return jsonify(
                {
                    'error': (
                        f"Capability '{requested_capability}' does not match the selected instance "
                        f"'{instance_id}' (capability '{instance_capability}')."
                    )
                }
            ), 400
        capability = requested_capability or instance_capability
        if not capability:
            capability = infer_capability(model_name, backend)
        if capability == self.capability_embedding:
            return jsonify(
                {
                    'error': (
                        'Embedding instances are internal interpretive inference helper models for pre-ranking '
                        'and are not executed through /api/responses.'
                    )
                }
            ), 400
        wants_stream = parse_bool(data.get('stream'), default=False)
        raw_requested_response_id = str(
            data.get('response_id') or data.get('responseId') or ''
        ).strip()
        requested_response_id = (
            normalize_response_lookup_id(raw_requested_response_id)
            if raw_requested_response_id
            else None
        )
        if requested_response_id and isinstance(data, dict):
            data = dict(data)
            data['response_id'] = requested_response_id
        response_lookup_record: Optional[dict[str, Any]] = None
        response_lookup_message_id: Optional[str] = None

        def ensure_response_lookup(mode_hint: str) -> Optional[dict[str, Any]]:
            nonlocal response_lookup_record, response_lookup_message_id
            if not requested_response_id:
                return None
            if response_lookup_record:
                return response_lookup_record
            response_lookup_record = register_response_lookup(
                response_id=requested_response_id,
                message_id='',
                instance_id=instance_id,
                model_name=model_name,
                backend=backend,
                capability=capability,
                mode=mode_hint,
                route_payload=route_info,
            )
            response_lookup_message_id = str(response_lookup_record.get('message_id') or '').strip() or None
            return response_lookup_record

        def mark_response_lookup_failed(
            error_message: str,
            mode_hint: str,
            *,
            response_payload: Optional[dict[str, Any]] = None,
        ) -> None:
            payload_response_id = str(
                (response_payload or {}).get('id')
                or (response_payload or {}).get('response_id')
                or ''
            ).strip()
            target_response_id = requested_response_id or payload_response_id
            if not target_response_id:
                return
            if requested_response_id:
                ensure_response_lookup(mode_hint)
            else:
                ensure_response_lookup_for_payload(
                    response_payload,
                    mode_hint=mode_hint,
                    route_payload=route_info,
                )
            touch_response_lookup(
                target_response_id,
                status='failed',
                error_message=error_message,
                response_payload=response_payload,
            )

        def mark_response_lookup_completed(response_payload: dict, mode_hint: str) -> None:
            payload_response_id = str(
                response_payload.get('id')
                or response_payload.get('response_id')
                or ''
            ).strip()
            target_response_id = requested_response_id or payload_response_id
            if not target_response_id:
                return
            if requested_response_id:
                ensure_response_lookup(mode_hint)
            else:
                ensure_response_lookup_for_payload(
                    response_payload,
                    mode_hint=mode_hint,
                    route_payload=route_info,
                )
            touch_response_lookup(
                target_response_id,
                status='completed',
                output_text=str(response_payload.get('output_text') or ''),
                response_payload=response_payload,
            )

        def build_runtime_error_payload(
            error_message: str, status_code: int, mode_hint: str,
            *, source_payload: Optional[dict[str, Any]] = None,
        ) -> dict[str, Any]:
            error_payload = build_canonical_error_response_payload(
                error_message=error_message,
                status_code=status_code,
                instance_id=instance_id,
                model_name=model_name,
                backend=backend,
                capability=capability or mode_hint or 'response',
                mode=mode_hint or capability or 'response',
                route_payload=route_info,
                response_id=requested_response_id,
                message_id=response_lookup_message_id,
            )
            if isinstance(source_payload, dict):
                # A later PDF page can fail after earlier pages produced verified
                # results. Preserve coverage and receipts before freezing failure.
                for key in ('pdf_source', 'pdf_total_pages', 'pdf_processed_pages', 'warnings', 'pdf_preparation'):
                    if key in source_payload:
                        error_payload[key] = copy.deepcopy(source_payload[key])
                if isinstance(source_payload.get('pdf_preparation'), dict):
                    # The established error_detail handle survives durable/UI
                    # projection even when exceptional top-level keys are omitted.
                    error_payload['error_detail'] = {key: copy.deepcopy(source_payload[key]) for key in
                        ('pdf_preparation', 'pdf_source', 'pdf_total_pages', 'pdf_processed_pages')
                        if key in source_payload}
                image_tool_evidence = source_payload.get('apple_fm_image_tool_evidence')
                if isinstance(image_tool_evidence, dict) and image_tool_evidence:
                    error_payload['runtime'] = {
                        **error_payload.get('runtime', {}),
                        'apple_fm_image_tool_evidence': copy.deepcopy(image_tool_evidence),
                    }
            return finalize_response_frame_payload(error_payload, request_payload=data)

        def maybe_retry_self_healed_response(error_message: str, status_code: int, *, exception=None) -> Optional[Response]:
            if direct_target or _provider_retry is not None:
                return None
            if provider_failover_reason(error_message, exception=exception, status_code=status_code):
                return None
            if provider_failure_prohibits_retry(error_message, exception=exception, status_code=status_code):
                return None
            if (((route_info or {}).get('route_runtime') or {}).get('inference_preferences') or {}).get('primary_mode') == 'lock':
                return None
            if not route_info or not parse_bool(data.get('inference_route'), default=False):
                return None
            if parse_bool(data.get('inference_self_heal_attempted'), default=False):
                return None
            try:
                normalized_status_code = int(status_code or 0)
            except (TypeError, ValueError):
                normalized_status_code = 0
            if normalized_status_code < 500 or normalized_status_code >= 600:
                return None

            retry_failure = {
                'capability': capability,
                'failed_instance_id': instance_id,
                'status_code': normalized_status_code or 500,
                'error_message': str(error_message or '').strip() or 'Request failed.',
            }
            retry_payload = dict(data if isinstance(data, dict) else dict(data))
            retry_payload['inference_self_heal_attempted'] = True
            retry_route_info, retry_error = resolve_inference_auto_route(
                retry_payload,
                upload=upload,
                excluded_instance_ids=[instance_id],
                retry_failure=retry_failure,
            )
            if retry_error or not retry_route_info:
                return None

            retry_instance_id = str((retry_route_info or {}).get('instance_id') or '').strip()
            retry_capability = normalize_capability((retry_route_info or {}).get('capability'))
            if not retry_instance_id:
                return None
            if str((retry_route_info or {}).get('route_source') or '').strip() != 'self_heal':
                return None
            if retry_instance_id == instance_id and retry_capability == capability:
                return None

            retry_payload['inference_preview'] = self.build_inference_route_preview_payload(
                retry_route_info,
                request_payload=retry_payload,
            )
            log_unified_event(
                category='responses',
                action='self_heal_retry',
                status='ok',
                instance_id=retry_instance_id,
                model=((retry_route_info or {}).get('instance') or {}).get('model') if isinstance((retry_route_info or {}).get('instance'), dict) else None,
                backend=((retry_route_info or {}).get('instance') or {}).get('backend') if isinstance((retry_route_info or {}).get('instance'), dict) else None,
                capability=retry_capability,
                previous_instance_id=instance_id,
                previous_model=request_model_override or model_name,
                route_source=retry_route_info.get('route_source'),
                prompt_class=((retry_route_info.get('route_runtime') or {}).get('prompt_class') if isinstance(retry_route_info.get('route_runtime'), dict) else None),
                session_class=((retry_route_info.get('route_runtime') or {}).get('session_class') if isinstance(retry_route_info.get('route_runtime'), dict) else None),
                message=f'Self-heal retry after {status_code}: {error_message}',
            )
            return handle_responses_request(
                data_override=retry_payload,
                upload_override=upload,
            )

        def selected_instance_is_mlx_vlm(candidate: Any) -> bool:
            if not isinstance(candidate, dict):
                return False
            metadata = candidate.get('backend_metadata') if isinstance(candidate.get('backend_metadata'), dict) else {}
            backend_package = str(
                candidate.get('backend_package')
                or metadata.get('backend_package')
                or ''
            ).strip().lower()
            backend_contract = str(
                candidate.get('backend_contract')
                or metadata.get('backend_contract')
                or ''
            ).strip().lower()
            return (
                normalize_backend(candidate.get('backend')) == 'mlx'
                and (
                    backend_package == 'mlx_vlm'
                    or backend_contract.startswith('mlx_vlm.')
                )
            )

        def maybe_retry_provider_failure(error_message, status_code, *, exception=None, response_id=None):
            nonlocal route_info, requested_response_id
            if response_id and not requested_response_id:
                requested_response_id = response_id
            reason = provider_failover_reason(
                error_message, exception=exception, status_code=status_code,
            )
            if direct_target or is_external_target or not reason:
                return None
            if capability not in {self.capability_chat, 'vision_analysis'}:
                return None
            runtime = (route_info or {}).get('route_runtime') or {}
            preferences = runtime.get('inference_preferences') or {}
            if str(preferences.get('primary_mode') or '').lower() == 'lock':
                return None
            attempts = copy.deepcopy((_provider_retry or {}).get('attempts') or [])
            attempts.append({
                'instance_id': instance_id, 'model': model_name, 'backend': backend,
                'reason': reason, 'status_code': status_code,
                **({'provider_status_code': exception.response.status_code}
                   if getattr(getattr(exception, 'response', None), 'status_code', None) is not None else {}),
                'error_message': str(error_message),
            })
            route_info = dict(route_info or {
                'instance_id': instance_id, 'instance': instance, 'capability': capability,
                'route_source': 'capability',
            })
            runtime = dict(runtime)
            audit = {
                'max_attempts': PROVIDER_FAILOVER_MAX_ATTEMPTS,
                'attempts': attempts,
                'status': 'exhausted',
            }
            runtime['provider_failover'] = audit
            route_info['route_runtime'] = runtime
            if len(attempts) >= PROVIDER_FAILOVER_MAX_ATTEMPTS:
                audit['stop_reason'] = 'attempt_limit'
                return None

            retry_payload = copy.deepcopy(dict(data))
            retry_payload['capability'] = capability
            for key in ('instance_id', 'model', 'modelName', 'request_model', 'requestModel', 'backend', 'alias', 'profile'):
                retry_payload.pop(key, None)
            # Keep the exact execution input chosen for this attempt, even when
            # it originated from an accepted artifact reference rather than file_path.
            if raw_file_path:
                retry_payload['file_path'] = raw_file_path
            if response_id:
                retry_payload['response_id'] = response_id

            def compatible(candidate):
                if str(candidate.get('target_kind') or '').lower() == 'external':
                    return False
                if not candidate.get('port'):
                    return False
                if normalize_backend(candidate.get('backend')) == 'apple_pcc' and any(
                    value is not None for value in (temperature, top_p, max_tokens)
                ):
                    return False
                # Attached text is extracted before chat. Image/PDF inputs need
                # a provider that can honor the existing visual input path.
                needs_vision = has_file_context and self._hook('file_kind_from_name')(raw_file_path) != 'text'
                if needs_vision and not instance_supports_capability(candidate, 'vision_analysis'):
                    return False
                if build_missing_required_session_controls(candidate, retry_payload):
                    return False
                try:
                    if reasoning_effort_explicit:
                        validate_reasoning_effort_for_instance(reasoning_effort, candidate)
                except ValueError:
                    return False
                return True

            preferred_targets = []
            # A failed primary is already excluded. Try a configured fallback
            # before the same capability's ordinary automatic selection.
            for key in ('fallback_target',):
                target = preferences.get(key)
                if isinstance(target, dict) and target:
                    target_capability = normalize_capability(target.get('capability')) or self.capability_chat
                    if target_capability == capability:
                        preferred_targets.append(target)
            fallback_id, fallback, _, error = resolve_responses_target_instance(
                retry_payload,
                excluded_instance_ids=[item['instance_id'] for item in attempts],
                preferred_targets=preferred_targets,
                candidate_filter=compatible,
            )
            if error or not fallback_id or not isinstance(fallback, dict):
                audit['stop_reason'] = 'no_compatible_running_alternative'
                return None
            if fallback_id in {item['instance_id'] for item in attempts} or not compatible(fallback):
                audit['stop_reason'] = 'no_compatible_running_alternative'
                return None
            audit.update(status='selected', selected_instance_id=fallback_id)
            retry_route = copy.deepcopy(route_info)
            accepted_preview = data.get('inference_preview') or {}
            if not retry_route['route_runtime'].get('working_frame') and accepted_preview.get('working_frame'):
                retry_route['route_runtime']['working_frame'] = copy.deepcopy(accepted_preview['working_frame'])
            retry_route.update(instance_id=fallback_id, instance=fallback, capability=capability)
            retry_payload['backend'] = normalize_backend(fallback.get('backend'))
            retry_payload['model'] = fallback.get('model') or fallback.get('modelName')
            retry_payload['request_model'] = fallback.get('request_model') or fallback.get('requestModel')
            retry_payload['inference_preview'] = self.build_inference_route_preview_payload(
                retry_route, request_payload=retry_payload,
            )
            log_unified_event(
                category='responses', action='provider_failover', status='retrying',
                instance_id=fallback_id, previous_instance_id=instance_id,
                backend=retry_payload['backend'], capability=capability,
                message=f'{reason}: {error_message}',
            )
            return self.handle_responses_request(
                data_override=retry_payload,
                _provider_retry={'route_info': retry_route, 'attempts': attempts},
            )

        normalized_payload = dict(data) if isinstance(data, dict) else dict(data)
        batch_items = extract_responses_batch_items(normalized_payload)
        batch_prompts = [str(item.get('prompt') or '').strip() for item in batch_items if str(item.get('prompt') or '').strip()]
        if batch_prompts and capability != self.capability_image_generation:
            return jsonify(
                {
                    'error': 'batch_prompts is currently only supported for image_generation.'
                }
            ), 400
        temperature = None
        top_p = None
        max_tokens = None
        reasoning_effort = None
        reasoning_effort_explicit = bool(
            data.get('reasoning_effort') not in (None, '')
            or data.get('reasoningEffort') not in (None, '')
        )
        try:
            if data.get('temperature') not in (None, ''):
                temperature = parse_float_with_bounds(data.get('temperature'), default=0.7, minimum=0.0, maximum=2.0)
            if data.get('top_p') not in (None, '') or data.get('topP') not in (None, ''):
                top_p = parse_float_with_bounds(data.get('top_p') or data.get('topP'), default=0.9, minimum=0.0, maximum=1.0)
            if data.get('max_tokens') not in (None, '') or data.get('maxTokens') not in (None, ''):
                max_tokens = parse_int_with_bounds(
                    data.get('max_tokens') or data.get('maxTokens'),
                    default=1_000_000,
                    minimum=1,
                    maximum=1_000_000,
                )
            reasoning_effort = normalize_reasoning_effort(
                data.get('reasoning_effort')
                if data.get('reasoning_effort') not in (None, '')
                else data.get('reasoningEffort')
            )
            reasoning_effort = validate_reasoning_effort_for_instance(
                reasoning_effort,
                instance,
            )
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
        if backend == 'apple_pcc' and any(value is not None for value in (temperature, top_p, max_tokens)):
            return jsonify({'error': 'PCC Shortcuts does not expose sampling or output-token controls.'}), 400
        if reasoning_effort is not None:
            # Keep the caller payload unchanged for retries that may select a
            # different model, but record the effective per-target value in
            # response truth and any same-target continuation metadata.
            normalized_payload.pop('reasoningEffort', None)
            normalized_payload['reasoning_effort'] = reasoning_effort
            request_meta = (
                dict(normalized_payload.get('request_meta') or {})
                if isinstance(normalized_payload.get('request_meta'), dict)
                else {}
            )
            request_meta['reasoning_effort_control'] = {
                'value': reasoning_effort,
                'explicit': reasoning_effort_explicit,
                'scope': 'model_instance',
                'source_instance_id': instance_id,
            }
            normalized_payload['request_meta'] = request_meta

        selected_reference_artifacts = extract_selected_reference_artifacts(data)
        matched_selected_reference = select_matching_selected_reference_artifact(
            selected_reference_artifacts,
            capability,
            instance=instance,
            artifact_ref=execution_input_artifact_ref(normalized_payload),
        )
        responses_prompt = extract_responses_prompt(normalized_payload)
        responses_current_turn_prompt = extract_responses_current_turn_prompt(normalized_payload)
        raw_file_path = str(data.get('file_path') or '').strip()
        if not raw_file_path and route_info and route_info.get('route_reuse_last_artifact'):
            raw_file_path = str(route_info.get('route_artifact_path') or '').strip()
        if (
            not raw_file_path
            and not upload
            and should_attach_selected_reference_file_context(
                prompt=responses_current_turn_prompt,
                capability=capability,
                selected_reference_artifact=matched_selected_reference,
            )
        ):
            raw_file_path = str(matched_selected_reference.get('path') or '').strip()
        has_file_context = bool((upload and getattr(upload, 'filename', None)) or raw_file_path)

        if (
            normalize_capability(capability) != self.capability_chat
            and normalize_capability(capability) == 'vision_analysis'
            and not has_file_context
            and selected_instance_is_mlx_vlm(instance)
            and instance_supports_capability(instance, self.capability_chat)
        ):
            previous_capability = capability
            capability = self.capability_chat
            requested_capability = self.capability_chat
            data = dict(data if isinstance(data, dict) else dict(data or {}))
            data['capability'] = self.capability_chat
            normalized_payload = dict(normalized_payload)
            normalized_payload['capability'] = self.capability_chat
            if route_info:
                route_info = dict(route_info)
                route_info['capability'] = self.capability_chat
                route_runtime = (
                    dict(route_info.get('route_runtime') or {})
                    if isinstance(route_info.get('route_runtime'), dict)
                    else {}
                )
                route_runtime['capability_rebound'] = {
                    'from': previous_capability,
                    'to': self.capability_chat,
                    'reason': 'text_only_selected_mlx_vlm_turn',
                }
                route_info['route_runtime'] = route_runtime
            log_unified_event(
                category='responses',
                action='capability_rebound',
                status='ok',
                instance_id=instance_id,
                model=model_name,
                backend=backend,
                capability=self.capability_chat,
                previous_capability=previous_capability,
                message='Text-only selected MLX/VLM request rebounded to chat capability.',
            )

        if is_external_target:
            valid_external_request, validation_code, validation_error = (
                validate_external_text_request(
                    normalized_payload,
                    upload_present=bool(upload and getattr(upload, 'filename', None)),
                    files_enabled=instance.get('files_enabled') is True,
                )
            )
            external_prompt = str(
                responses_current_turn_prompt or responses_prompt or ''
            ).strip()
            external_context_messages = (
                extract_inference_route_messages(
                    data,
                    include_selected_reference=False,
                )
                if parse_bool(data.get('inference_route'), default=False)
                else extract_responses_messages(data)
            )
            if external_prompt and not any(
                str(item.get('role') or '').strip().lower() == 'user'
                and str(item.get('content') or '').strip() == external_prompt
                for item in external_context_messages
                if isinstance(item, dict)
            ):
                external_context_messages = [
                    *external_context_messages,
                    {'role': 'user', 'content': external_prompt},
                ]
            external_context_strategy = choose_context_strategy(
                instance=instance,
                messages=external_context_messages,
                prompt=external_prompt,
                has_file_context=False,
                conversation_id=(
                    normalized_payload.get('conversation_id')
                    or normalized_payload.get('conversationId')
                    or normalized_payload.get('thread_id')
                    or normalized_payload.get('threadId')
                ),
            )
            prepared_external_context = apply_context_strategy(
                external_context_messages,
                external_context_strategy,
            )
            prepared_external_context = inject_selected_reference_into_chat_messages(
                prepared_external_context,
                selected_reference_artifacts,
            )
            external_prepare_contract = resolve_prepare_phase_contract(
                route_payload=route_info,
                request_payload=normalized_payload,
            )
            if external_prepare_contract:
                route_info = dict(route_info or {})
                route_runtime = (
                    dict(route_info.get('route_runtime') or {})
                    if isinstance(route_info.get('route_runtime'), dict)
                    else {}
                )
                prepare_phase_graph = external_prepare_contract.get('phase_graph')
                if (
                    isinstance(prepare_phase_graph, dict)
                    and not isinstance(route_runtime.get('request_phase_graph'), dict)
                ):
                    route_runtime['request_phase_graph'] = copy.deepcopy(
                        prepare_phase_graph
                    )
                current_prepare_phase = (
                    external_prepare_contract.get('current_phase')
                    if isinstance(
                        external_prepare_contract.get('current_phase'),
                        dict,
                    )
                    else {}
                )
                route_runtime['external_phase_execution_policy'] = _compact_payload(
                    {
                        'kind': 'fruth.external_phase_execution_policy',
                        'status': 'bounded',
                        'policy': 'graph_current_phase_only',
                        'current_phase_id': current_prepare_phase.get('phase_id'),
                        'current_phase_kind': current_prepare_phase.get('kind'),
                        'current_phase_role': current_prepare_phase.get('role'),
                        'downstream_capabilities': external_prepare_contract.get(
                            'downstream_capabilities'
                        ),
                        'root_request_authority': 'promoted_context_reference_only',
                        'materialization_authority': 'fruth_runtime',
                    }
                )
                route_info['route_runtime'] = route_runtime
            bounded_external_prompt = build_external_prepare_phase_bounded_task(
                prepare_contract=external_prepare_contract,
                route_payload=route_info,
                request_payload=normalized_payload,
            ) or external_prompt
            external_prompt = external_provider_prompt_with_bounded_context(
                external_prompt,
                prepared_external_context,
                bounded_task_prompt=bounded_external_prompt,
            )
            external_inputs = build_external_target_inputs(normalized_payload)
            if valid_external_request and not external_prompt:
                valid_external_request = False
                validation_code = 'CODEX_INVALID_REQUEST'
                validation_error = 'No Responses text input was provided.'

            if not valid_external_request:
                error_message = str(
                    validation_error or 'The ChatGPT request contains unsupported input.'
                )
                error_payload = build_canonical_error_response_payload(
                    error_message=error_message,
                    status_code=400,
                    instance_id=instance_id,
                    model_name=model_name,
                    backend=backend,
                    capability=capability or self.capability_chat,
                    mode='external_chat',
                    route_payload=route_info,
                    response_id=requested_response_id,
                    message_id=response_lookup_message_id,
                )
                error_payload['error_ref'] = {
                    'code': str(validation_code or 'CODEX_INVALID_REQUEST'),
                    'stage': 'external_request_validation',
                }
                error_payload['recovery_hint'] = (
                    'Send a non-empty prompt with explicitly selected local files or Fruth artifacts.'
                )
                error_payload = finalize_response_frame_payload(
                    error_payload,
                    request_payload=normalized_payload,
                )
                mark_response_lookup_failed(
                    error_message,
                    'external_chat',
                    response_payload=error_payload,
                )
                return jsonify(project_response_payload_for_wire(error_payload)), 400

            ensure_response_lookup('external_chat')
            execution_result = (
                execute_external_text_target(
                    external_prompt,
                    inputs=external_inputs,
                )
                if external_inputs
                else execute_external_text_target(external_prompt)
            )
            execution_status = str(execution_result.status.value)
            external_execution_evidence = {
                'kind': 'fruth.external_provider_execution',
                'target_id': instance_id,
                'provider': 'codex_cli',
                'status': execution_status,
                'source': (
                    execution_result.discovery.source.value
                    if execution_result.discovery.source is not None
                    else None
                ),
                'version': execution_result.discovery.version,
                'duration_seconds': round(
                    float(execution_result.duration_seconds or 0.0),
                    3,
                ),
                'exit_code': execution_result.exit_code,
                'output_truncated': bool(execution_result.output_truncated),
                'diagnostic_truncated': bool(execution_result.diagnostic_truncated),
                'model_selection': 'codex_default',
                'exact_model_exposed': False,
                'input_handoff': [
                    item.as_dict()
                    for item in execution_result.input_handoff
                ],
                'input_count': len(execution_result.input_handoff),
            }
            route_info = dict(route_info or {})
            route_runtime = (
                dict(route_info.get('route_runtime') or {})
                if isinstance(route_info.get('route_runtime'), dict)
                else {}
            )
            route_runtime['context_strategy'] = external_context_strategy
            route_runtime['external_execution'] = {
                key: value
                for key, value in external_execution_evidence.items()
                if value is not None
            }
            route_info['route_runtime'] = route_runtime

            if not execution_result.succeeded:
                status_code, error_code, recovery_hint = external_execution_failure(
                    execution_result
                )
                error_message = (
                    f"ChatGPT request via Codex ended with status '{execution_status}'."
                )
                error_payload = build_canonical_error_response_payload(
                    error_message=error_message,
                    status_code=status_code,
                    instance_id=instance_id,
                    model_name=model_name,
                    backend=backend,
                    capability=capability,
                    mode='external_chat',
                    route_payload=route_info,
                    response_id=requested_response_id,
                    message_id=response_lookup_message_id,
                )
                error_payload['error_ref'] = {
                    'code': error_code,
                    'stage': 'external_execution',
                }
                error_payload['recovery_hint'] = recovery_hint
                if execution_result.diagnostic:
                    error_payload['error_detail'] = {
                        'message': error_message,
                        'diagnostic': str(execution_result.diagnostic),
                    }
                error_payload = finalize_response_frame_payload(
                    error_payload,
                    request_payload=normalized_payload,
                )
                mark_response_lookup_failed(
                    error_message,
                    'external_chat',
                    response_payload=error_payload,
                )
                return (
                    jsonify(project_response_payload_for_wire(error_payload)),
                    status_code,
                )

            provider_output_text = str(execution_result.output_text or '')
            provider_block_reason = external_provider_block_reason(
                provider_output_text
            )
            if provider_block_reason is not None:
                blocked_surface_state = {
                    'state': 'blocked',
                    'status': 'blocked',
                    'summary': 'The downstream provider could not complete the bounded task.',
                    'message': provider_block_reason,
                    'reason': provider_block_reason,
                    'category_counts': {'blocked': 1},
                    'active_categories': ['blocked'],
                }
                external_execution_evidence.update(
                    {
                        'status': 'blocked',
                        'invocation_status': execution_status,
                        'blocked_reason': provider_block_reason,
                    }
                )
                route_runtime['external_execution'] = {
                    key: value
                    for key, value in external_execution_evidence.items()
                    if value is not None
                }
                route_runtime['surface_state'] = dict(blocked_surface_state)
                route_info['route_runtime'] = route_runtime

                response_payload = build_canonical_response_payload(
                    instance_id=instance_id,
                    model_name=model_name,
                    backend=backend,
                    capability=capability,
                    mode='external_chat',
                    output_text=provider_output_text,
                    source_payload={},
                    route_payload=route_info,
                    response_id=requested_response_id,
                    message_id=response_lookup_message_id,
                )
                blocked_output = {
                    'slot_id': 'output-1',
                    'branch_id': 'phase-1',
                    'phase_id': 'phase-1',
                    'type': 'text',
                    'status': 'blocked',
                    'lifecycle': 'blocked_output',
                    'source': 'external_provider_execution',
                    'compatibility_derived': False,
                    'value': provider_output_text,
                    'blocked_reason': provider_block_reason,
                }
                response_payload['output_slots'] = [dict(blocked_output)]
                response_payload['outputs'] = [dict(blocked_output)]
                response_payload['artifacts'] = []
                response_payload['surface_state'] = dict(blocked_surface_state)
                response_payload['lifecycle_state'] = 'blocked'
                response_payload = finalize_response_frame_payload(
                    response_payload,
                    request_payload=normalized_payload,
                )
                mark_response_lookup_completed(response_payload, 'external_chat')
                if wants_stream:
                    return Response(
                        stream_with_context(
                            build_canonical_response_stream_events(response_payload)
                        ),
                        mimetype='text/event-stream',
                    )
                return jsonify(project_response_payload_for_wire(response_payload))

            assistant_text, phase_acceptance_attempts = accept_phase_output(
                provider_output_text,
                effective_route_payload=route_info,
                effective_request_payload=normalized_payload,
                effective_capability=capability,
            )
            response_payload = build_canonical_response_payload(
                instance_id=instance_id,
                model_name=model_name,
                backend=backend,
                capability=capability,
                mode='external_chat',
                output_text=assistant_text,
                source_payload=attach_response_semantic_phase_payload(
                    {},
                    output_text=assistant_text,
                    route_payload=route_info,
                    request_payload=normalized_payload,
                    capability=capability,
                ),
                route_payload=route_info,
                response_id=requested_response_id,
                message_id=response_lookup_message_id,
            )
            if phase_acceptance_attempts:
                response_payload = attach_phase_output_acceptance(
                    response_payload,
                    phase_acceptance_attempts,
                )
            response_payload = truth_gate_response_output_claims(
                response_payload,
                route_payload=route_info,
                request_payload=normalized_payload,
            )
            artifact_completion_gap = None
            response_payload, artifact_completion_gap = self.attach_pre_freeze_closure_review(
                response_payload,
                output_text=assistant_text,
                route_payload=route_info,
                request_payload=normalized_payload,
                artifact_gap=artifact_completion_gap,
            )
            if not artifact_completion_gap:
                response_payload, _direct_closure_status = self.apply_direct_artifact_materialization_closure(
                    response_payload,
                    request_payload=normalized_payload,
                    route_payload=route_info,
                    artifact_gap=artifact_completion_gap,
                    terminal_status='completed',
                )
            response_payload = finalize_response_frame_payload(
                response_payload,
                request_payload=normalized_payload,
            )
            mark_response_lookup_completed(response_payload, 'external_chat')
            if artifact_completion_gap:
                schedule_response_late_fill(
                    response_payload=response_payload,
                    request_payload=normalized_payload,
                    assistant_message=assistant_text,
                    artifact_gap=artifact_completion_gap,
                    source_route_payload=route_info,
                )
            if wants_stream:
                return Response(
                    stream_with_context(
                        build_canonical_response_stream_events(response_payload)
                    ),
                    mimetype='text/event-stream',
                )
            return jsonify(project_response_payload_for_wire(response_payload))

        if (capability == self.capability_chat and not has_file_context
                and str(data.get('ocr_mode') or '').strip().lower() not in {'apple_ocr', 'apple_barcode'}):
            messages = extract_responses_messages(data)
            if not messages:
                return jsonify({'error': 'No Responses input was provided.'}), 400
            messages = inject_selected_reference_into_chat_messages(messages, selected_reference_artifacts)
            messages = inject_inference_runtime_policy_into_chat_messages(
                messages,
                route_payload=route_info,
                request_payload=normalized_payload,
                backend=backend,
            )
            messages = inject_prepare_phase_contract_into_chat_messages(
                messages,
                route_payload=route_info,
                request_payload=normalized_payload,
                backend=backend,
            )
            context_strategy = choose_context_strategy(
                instance=instance,
                messages=messages,
                prompt=extract_responses_prompt(normalized_payload),
                has_file_context=False,
                conversation_id=(
                    normalized_payload.get('conversation_id')
                    or normalized_payload.get('conversationId')
                    or normalized_payload.get('thread_id')
                    or normalized_payload.get('threadId')
                ),
            )
            prepared_messages = apply_context_strategy(messages, context_strategy)
            if route_info:
                route_runtime = dict(route_info.get('route_runtime') or {})
                route_runtime['context_strategy'] = context_strategy
                route_info['route_runtime'] = route_runtime
            port = instance.get('port')
            if not port:
                return jsonify({'error': 'Instance has no target port.'}), 400
            try:
                target_port = int(port)
            except (TypeError, ValueError):
                return jsonify({'error': f"Invalid target port '{port}'."}), 400
            if wants_stream:
                streamed_response = stream_chat_backend_as_responses(
                    instance_id=instance_id,
                    target_port=target_port,
                    model_name=model_name,
                    backend=backend,
                    capability=capability,
                    messages=prepared_messages,
                    request_model_override=request_model_override,
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_tokens,
                    reasoning_effort=reasoning_effort,
                    route_payload=route_info,
                    response_id=requested_response_id,
                    request_payload=normalized_payload,
                    artifact_prompt=responses_current_turn_prompt or responses_prompt,
                    provider_failure_retry=maybe_retry_provider_failure,
                )
                # Opening failed before SSE was published. Persist the same
                # canonical failure/attempt evidence as non-streaming requests.
                if isinstance(streamed_response, tuple) and streamed_response[1] >= 400:
                    failure = streamed_response[0].get_json() or {}
                    if failure.get('object') == 'response':
                        return streamed_response
                    error_message = str(failure.get('error') or 'Chat stream failed to open.')
                    status_code = streamed_response[1]
                    error_payload = build_runtime_error_payload(error_message, status_code, 'chat')
                    mark_response_lookup_failed(error_message, 'chat', response_payload=error_payload)
                    return jsonify(project_response_payload_for_wire(error_payload)), status_code
                return streamed_response
            ensure_response_lookup('chat')
            try:
                assistant_message = execute_chat_backend_request(
                    target_port=target_port,
                    model_name=model_name,
                    backend=backend,
                    capability=capability,
                    messages=prepared_messages,
                    request_model_override=request_model_override,
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_tokens,
                    reasoning_effort=reasoning_effort,
                )
            except self.request_timeout_error as exc:
                error_message = f'Timeout Port {target_port}'
                retried_response = maybe_retry_provider_failure(error_message, 504, exception=exc)
                if retried_response is not None:
                    return retried_response
                retried_response = maybe_retry_self_healed_response(error_message, 504, exception=exc)
                if retried_response is not None:
                    return retried_response
                error_payload = build_runtime_error_payload(error_message, 504, 'chat')
                mark_response_lookup_failed(
                    error_message,
                    'chat',
                    response_payload=error_payload,
                )
                return jsonify(project_response_payload_for_wire(error_payload)), 504
            except self.request_exception_error as exc:
                details = request_exception_details(exc)
                error_message = f'Request to port {target_port} failed: {details}'
                retried_response = maybe_retry_provider_failure(error_message, 500, exception=exc)
                if retried_response is not None:
                    return retried_response
                retried_response = maybe_retry_self_healed_response(error_message, 500, exception=exc)
                if retried_response is not None:
                    return retried_response
                error_payload = build_runtime_error_payload(error_message, 500, 'chat')
                mark_response_lookup_failed(
                    error_message,
                    'chat',
                    response_payload=error_payload,
                )
                return jsonify(project_response_payload_for_wire(error_payload)), 500
            except Exception as exc:  # noqa: BLE001
                error_message = str(exc)
                retried_response = maybe_retry_provider_failure(error_message, 500, exception=exc)
                if retried_response is not None:
                    return retried_response
                retried_response = maybe_retry_self_healed_response(error_message, 500, exception=exc)
                if retried_response is not None:
                    return retried_response
                error_payload = build_runtime_error_payload(error_message, 500, 'chat')
                mark_response_lookup_failed(
                    error_message,
                    'chat',
                    response_payload=error_payload,
                )
                return jsonify(project_response_payload_for_wire(error_payload)), 500
            pcc_execution = getattr(assistant_message, 'pcc_execution', None)

            def retain_chat_execution(value):
                nonlocal pcc_execution
                pcc_execution = getattr(value, 'pcc_execution', None)
                return value

            assistant_text, phase_acceptance_attempts = accept_phase_output(
                assistant_message,
                effective_route_payload=route_info,
                effective_request_payload=normalized_payload,
                effective_capability=capability,
                retry_same_phase=lambda: retain_chat_execution(execute_chat_backend_request(
                    target_port=target_port,
                    model_name=model_name,
                    backend=backend,
                    capability=capability,
                    messages=[*prepared_messages, phase_output_repair_system_message()],
                    request_model_override=request_model_override,
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_tokens,
                    reasoning_effort=reasoning_effort,
                )),
            )
            phase_output_repair_required = bool(
                phase_acceptance_attempts
                and phase_acceptance_attempts[-1].get('status') == 'repair_required'
            )
            text_artifact_payload = (
                {}
                if phase_output_repair_required or phase_output_defers_saved_file_materialization(
                    route_payload=route_info,
                    request_payload=normalized_payload,
                    capability=capability,
                )
                else persist_generated_text_artifact_if_requested(
                    assistant_text,
                    prompt=responses_current_turn_prompt or responses_prompt,
                    model_name=model_name,
                    mode='responses_chat_text_artifact',
                    request_payload=normalized_payload,
                )
            )
            if pcc_execution:
                text_artifact_payload = {**text_artifact_payload, 'pcc_execution': pcc_execution}
            response_payload = build_canonical_response_payload(
                instance_id=instance_id,
                model_name=model_name,
                backend=backend,
                capability=capability,
                mode='chat',
                output_text=assistant_text,
                source_payload=attach_response_semantic_phase_payload(
                    text_artifact_payload,
                    output_text=assistant_text,
                    route_payload=route_info,
                    request_payload=normalized_payload,
                    capability=capability,
                ),
                route_payload=route_info,
                response_id=requested_response_id,
                message_id=response_lookup_message_id,
            )
            if phase_acceptance_attempts:
                response_payload = attach_phase_output_acceptance(
                    response_payload,
                    phase_acceptance_attempts,
                )
            response_payload = truth_gate_response_output_claims(
                response_payload,
                route_payload=route_info,
                request_payload=normalized_payload,
            )
            artifact_completion_gap = None
            response_payload, artifact_completion_gap = self.attach_pre_freeze_closure_review(
                response_payload,
                output_text=assistant_text,
                route_payload=route_info,
                request_payload=normalized_payload,
                artifact_gap=artifact_completion_gap,
            )
            _direct_closure_status = 'completed'
            if not artifact_completion_gap:
                response_payload, _direct_closure_status = self.apply_direct_artifact_materialization_closure(
                    response_payload,
                    request_payload=normalized_payload,
                    route_payload=route_info,
                    artifact_gap=artifact_completion_gap,
                    terminal_status='completed',
                )
            response_payload = finalize_response_frame_payload(response_payload, request_payload=normalized_payload)
            ensure_response_lookup_for_payload(response_payload, mode_hint='chat', route_payload=route_info)
            touch_response_lookup(
                str(response_payload.get('id') or '').strip(),
                status='completed',
                output_text=str(response_payload.get('output_text') or ''),
                response_payload=response_payload,
            )
            if artifact_completion_gap:
                schedule_response_late_fill(
                    response_payload=response_payload,
                    request_payload=normalized_payload,
                    assistant_message=assistant_text,
                    artifact_gap=artifact_completion_gap,
                    source_route_payload=route_info,
                )
            else:
                if str(response_payload.get('lifecycle_state') or response_payload.get('status') or '').strip().lower() == 'completed':
                    maybe_schedule_post_response_substrate_hygiene(
                        response_payload,
                        route_payload=route_info,
                        reason='responses_chat_completed',
                    )
            return jsonify(project_response_payload_for_wire(response_payload))

        infer_payload, route_info, _has_file_context, expose_input_artifacts = build_responses_infer_execution_payload(
            data,
            route_info=route_info,
            instance=instance if isinstance(instance, dict) else {},
            instance_id=instance_id,
            backend=backend,
            capability=capability,
            request_model_override=request_model_override,
            upload_present=bool(upload and getattr(upload, 'filename', None)),
        )
        if not batch_prompts and capability == self.capability_image_generation:
            direct_batch_count = self.resolve_direct_image_batch_count(
                normalized_payload,
                route_info,
                capability=capability,
            )
            if direct_batch_count > 1:
                batch_items = self.build_direct_image_batch_items(
                    normalized_payload,
                    route_info,
                    infer_payload,
                    direct_batch_count=direct_batch_count,
                )
                batch_prompts = [
                    str(item.get('prompt') or '').strip()
                    for item in batch_items
                    if str(item.get('prompt') or '').strip()
                ]
        if batch_prompts:
            ensure_response_lookup(f'{capability}_batch')
            try:
                branch_specs = self.build_direct_batch_branch_specs(
                    batch_items=batch_items,
                    capability=capability,
                    base_request_payload=normalized_payload,
                    base_route_info=route_info,
                    base_instance_id=instance_id,
                    base_instance=instance if isinstance(instance, dict) else None,
                    forced_instance_id=forced_instance_id,
                    upload=upload,
                )
            except ValueError as exc:
                error_message = str(exc)
                error_payload = build_runtime_error_payload(error_message, 400, f'{capability}_batch')
                mark_response_lookup_failed(
                    error_message,
                    f'{capability}_batch',
                    response_payload=error_payload,
                )
                return jsonify(project_response_payload_for_wire(error_payload)), 400

            materialization_result = execute_materialization_branches(
                branch_specs,
                prepare_branch_plan=self.prepare_direct_materialization_branch_plan,
                execute_prepared_branch=self.execute_prepared_materialization_branch,
            )
            ordered_branch_results = (
                materialization_result.get('ordered_branch_results')
                if isinstance(materialization_result.get('ordered_branch_results'), list)
                else []
            )
            ordered_branch_errors = (
                materialization_result.get('ordered_branch_errors')
                if isinstance(materialization_result.get('ordered_branch_errors'), list)
                else []
            )
            first_branch_error = (
                ordered_branch_errors[0]
                if ordered_branch_errors and isinstance(ordered_branch_errors[0], dict)
                else None
            )
            if first_branch_error:
                error_message = str(
                    (
                        first_branch_error.get('error', {}) if isinstance(first_branch_error.get('error'), dict) else {}
                    ).get('message')
                    or 'Request failed.'
                ).strip() or 'Request failed.'
                try:
                    error_status_code = int(
                        (
                            first_branch_error.get('error', {}) if isinstance(first_branch_error.get('error'), dict) else {}
                        ).get('status_code')
                        or 500
                    )
                except (TypeError, ValueError):
                    error_status_code = 500
                branch_failure = first_branch_error.get('error')
                branch_failure = branch_failure if isinstance(branch_failure, dict) else {}
                preparation_failure = branch_failure.get('pdf_preparation')
                retried_response = (None if preparation_failure else
                                    maybe_retry_self_healed_response(error_message, error_status_code))
                if retried_response is not None:
                    return retried_response
                error_payload = build_runtime_error_payload(error_message, error_status_code, f'{capability}_batch',
                    source_payload=branch_failure)
                mark_response_lookup_failed(
                    error_message,
                    f'{capability}_batch',
                    response_payload=error_payload,
                )
                return jsonify(project_response_payload_for_wire(error_payload)), error_status_code

            infer_results = [
                result_entry.get('result', {}).get('infer_result')
                for result_entry in ordered_branch_results
                if isinstance(result_entry, dict)
                and isinstance(result_entry.get('result'), dict)
                and isinstance(result_entry.get('result', {}).get('infer_result'), dict)
            ]

            response_payload = build_canonical_batch_response_payload(
                instance_id=instance_id,
                model_name=model_name,
                backend=backend,
                capability=capability,
                batch_mode=f'{capability}_batch',
                batch_prompts=batch_prompts,
                infer_results=infer_results,
                route_payload=route_info,
                response_id=requested_response_id,
                message_id=response_lookup_message_id,
            )
            artifact_completion_gap = None
            route_runtime_for_gateway = (
                route_info.get('route_runtime')
                if isinstance(route_info, dict) and isinstance(route_info.get('route_runtime'), dict)
                else {}
            )
            route_graph_for_gateway = (
                route_runtime_for_gateway.get('request_phase_graph')
                if isinstance(route_runtime_for_gateway.get('request_phase_graph'), dict)
                else {}
            )
            batch_declares_downstream_work = bool(
                route_graph_for_gateway
                and (
                    route_graph_for_gateway.get('continuation_required')
                    or route_graph_for_gateway.get('downstream_branches')
                    or route_graph_for_gateway.get('downstream_branch_ids')
                    or route_graph_for_gateway.get('downstream_phase_ids')
                )
            )
            if batch_declares_downstream_work:
                response_payload, artifact_completion_gap = self.attach_pre_freeze_closure_review(
                    response_payload,
                    output_text=str(response_payload.get('output_text') or ''),
                    route_payload=route_info,
                    request_payload=normalized_payload,
                    artifact_gap=artifact_completion_gap,
                )
            response_payload = finalize_response_frame_payload(response_payload, request_payload=normalized_payload)
            mark_response_lookup_completed(response_payload, f'{capability}_batch')
            if artifact_completion_gap:
                schedule_response_late_fill(
                    response_payload=response_payload,
                    request_payload=normalized_payload,
                    assistant_message=str(response_payload.get('output_text') or ''),
                    artifact_gap=artifact_completion_gap,
                    source_route_payload=route_info,
                )
            else:
                maybe_schedule_post_response_substrate_hygiene(
                    response_payload,
                    route_payload=route_info,
                    reason=f'{capability}_batch_completed',
                )
            if wants_stream:
                return Response(
                    stream_with_context(build_canonical_response_stream_events(response_payload)),
                    mimetype='text/event-stream',
                )
            return jsonify(project_response_payload_for_wire(response_payload))

        ensure_response_lookup(capability or 'response')
        # Capture independently of the returned result, using the same admitted
        # caller/source owners as the writer. Provider metadata is not scope.
        source_meta = self._hook('request_payload_text_artifact_source')(normalized_payload)
        accepted_text_requests = detect_text_artifact_requests(
            responses_current_turn_prompt or responses_prompt,
            source_available=bool(source_meta),
            source_extension=source_meta.get('extension'),
            source_name=source_meta.get('source_name'),
            source_path=source_meta.get('path'),
        ) if capability == self.capability_chat else []
        accepted_root_phase_id = str(((route_info or {}).get('route_runtime') or {}).get(
            'request_phase_graph', {}).get('current_phase_id') or '')
        infer_result, status_code = invoke_internal_api_json_route(
            payload=infer_payload,
            upload=upload,
        )
        if status_code >= 400:
            error_message = str(infer_result.get('error') or 'Request failed.')
            if PdfPreparationError.from_response(infer_result) is None:
                retried_response = maybe_retry_provider_failure(error_message, status_code)
                if retried_response is not None:
                    return retried_response
                retried_response = maybe_retry_self_healed_response(error_message, status_code)
                if retried_response is not None:
                    return retried_response
            error_payload = build_runtime_error_payload(
                error_message, status_code, capability or 'response', source_payload=infer_result,
            )
            mark_response_lookup_failed(
                error_message,
                capability or 'response',
                response_payload=error_payload,
            )
            return jsonify(project_response_payload_for_wire(error_payload)), status_code
        infer_result = filter_responses_infer_result(
            infer_result,
            expose_input_artifacts=expose_input_artifacts,
        )
        infer_result = self._attach_tts_audio_integrity_evidence(
            infer_result,
            capability=capability,
            infer_payload=infer_payload,
        )

        final_output_text = str(infer_result.get('content') or '').strip()
        speech_to_text_translation_follow_up = None
        if capability == self.capability_speech_to_text:
            final_output_text, speech_to_text_translation_follow_up = (
                self._maybe_apply_speech_to_text_translation_follow_up(
                    transcript_text=final_output_text,
                    request_payload=normalized_payload,
                    capability=capability,
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_tokens,
                )
            )
        retry_infer_result: dict[str, Any] = {}

        def retry_infer_phase_output() -> str:
            retry_payload = copy.deepcopy(infer_payload)
            repair_instruction = phase_output_repair_system_message()['content']
            retry_messages = retry_payload.get('messages')
            if isinstance(retry_messages, list):
                retry_payload['messages'] = [
                    *[dict(item) for item in retry_messages if isinstance(item, dict)],
                    phase_output_repair_system_message(),
                ]
            else:
                retry_prompt = str(retry_payload.get('prompt') or '').strip()
                retry_payload['prompt'] = (
                    f'{retry_prompt}\n\n[{repair_instruction}]'
                    if retry_prompt
                    else repair_instruction
                )
            retried_result, retried_status = invoke_internal_api_json_route(
                payload=retry_payload,
                upload=upload,
            )
            if retried_status >= 400:
                raise RuntimeError(str(retried_result.get('error') or 'Phase-output repair failed.'))
            filtered_retry = filter_responses_infer_result(
                retried_result,
                expose_input_artifacts=expose_input_artifacts,
            )
            retry_infer_result.clear()
            retry_infer_result.update(filtered_retry)
            return str(filtered_retry.get('content') or '').strip()

        final_output_text, phase_acceptance_attempts = accept_phase_output(
            final_output_text,
            effective_route_payload=route_info,
            effective_request_payload=normalized_payload,
            effective_capability=capability,
            retry_same_phase=retry_infer_phase_output,
        )
        if (
            retry_infer_result
            and phase_acceptance_attempts
            and phase_acceptance_attempts[-1].get('status') in {'accepted', 'unwrapped'}
        ):
            infer_result = dict(retry_infer_result)
            infer_result['content'] = final_output_text
        phase_output_repair_required = bool(
            phase_acceptance_attempts
            and phase_acceptance_attempts[-1].get('status') == 'repair_required'
        )
        if (
            capability == self.capability_chat
            and final_output_text
            and not phase_output_repair_required
            and not str(infer_result.get('saved_text_path') or infer_result.get('savedTextPath') or '').strip()
            and not infer_result.get('saved_text_artifacts')
            and not phase_output_defers_saved_file_materialization(
                route_payload=route_info,
                request_payload=normalized_payload,
                capability=capability,
            )
        ):
            text_artifact_payload = persist_generated_text_artifact_if_requested(
                final_output_text,
                prompt=responses_current_turn_prompt or responses_prompt,
                model_name=model_name,
                mode='responses_infer_text_artifact',
                request_payload=normalized_payload,
            )
            if text_artifact_payload:
                infer_result = {
                    **infer_result,
                    **text_artifact_payload,
                    'content': final_output_text,
                }
        infer_result = self._hook('capture_root_text_artifact_saved_evidence')(
            infer_result, accepted_requests=accepted_text_requests,
            response_id=requested_response_id, phase_id=accepted_root_phase_id,
        )
        semantic_source_payload = (
            self._apply_tts_audio_integrity_output_truth(dict(infer_result))
        )
        semantic_source_payload['content'] = final_output_text
        response_payload = build_canonical_response_payload(
            instance_id=instance_id,
            model_name=model_name,
            backend=backend,
            capability=capability,
            mode=str(infer_result.get('mode') or capability or 'response'),
            output_text=final_output_text,
            source_payload=attach_response_semantic_phase_payload(
                semantic_source_payload,
                output_text=final_output_text,
                route_payload=route_info,
                request_payload=normalized_payload,
                capability=capability,
            ),
            route_payload=route_info,
            response_id=requested_response_id,
            message_id=response_lookup_message_id,
        )
        response_payload = self._apply_tts_audio_integrity_output_truth(
            response_payload
        )
        if phase_acceptance_attempts:
            response_payload = attach_phase_output_acceptance(
                response_payload,
                phase_acceptance_attempts,
            )
        response_payload = truth_gate_response_output_claims(
            response_payload,
            route_payload=route_info,
            request_payload=normalized_payload,
        )
        artifact_completion_gap = None
        response_payload, artifact_completion_gap = self.attach_pre_freeze_closure_review(
            response_payload,
            output_text=final_output_text,
            route_payload=route_info,
            request_payload=normalized_payload,
            artifact_gap=artifact_completion_gap,
        )
        if not artifact_completion_gap:
            response_payload, _direct_closure_status = self.apply_direct_artifact_materialization_closure(
                response_payload,
                request_payload=normalized_payload,
                route_payload=route_info,
                artifact_gap=artifact_completion_gap,
                terminal_status='completed',
            )
        if isinstance(speech_to_text_translation_follow_up, dict):
            runtime = (
                dict(response_payload.get('runtime') or {})
                if isinstance(response_payload.get('runtime'), dict)
                else {}
            )
            runtime['speech_to_text_translation_follow_up'] = dict(
                speech_to_text_translation_follow_up
            )
            response_payload['runtime'] = runtime
        response_payload = finalize_response_frame_payload(response_payload, request_payload=normalized_payload)
        mark_response_lookup_completed(
            response_payload,
            str(infer_result.get('mode') or capability or 'response'),
        )
        if artifact_completion_gap:
            schedule_response_late_fill(
                response_payload=response_payload,
                request_payload=normalized_payload,
                assistant_message=final_output_text,
                artifact_gap=artifact_completion_gap,
                source_route_payload=route_info,
            )
        else:
            if str(response_payload.get('lifecycle_state') or response_payload.get('status') or '').strip().lower() == 'completed':
                maybe_schedule_post_response_substrate_hygiene(
                    response_payload,
                    route_payload=route_info,
                    reason=f'{capability}_completed',
                )
        if wants_stream:
            return Response(
                stream_with_context(build_canonical_response_stream_events(response_payload)),
                mimetype='text/event-stream',
            )
        return jsonify(project_response_payload_for_wire(response_payload))
