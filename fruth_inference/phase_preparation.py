"""Interpret accepted phase contracts into bounded preparation and message payloads.

Prompt bytes, cohort cardinality and downstream scope are preserved. This owner
assembles instructions; it does not promote intent, invoke providers, dispatch
branches or accept their results.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from fruth_services import intent_coverage
from fruth_inference import image_prompt_preparation
from fruth_inference.image_prompt_preparation import _parse_image_batch_expected_count
import json
import re
from typing import Any, Mapping, Optional
from helpers.model_capabilities import (
    CAPABILITY_CHAT,
    CAPABILITY_IMAGE_GENERATION,
    CAPABILITY_SPEECH_TO_TEXT,
    CAPABILITY_TEXT_TO_SPEECH,
    CAPABILITY_VISION_ANALYSIS,
    normalize_capability,
    normalize_backend,
)
from fruth_inference.execution_planner import (
    _semantic_role_guidance,
    split_visible_image_payload,
    split_visible_tts_payload,
)
from fruth_inference.intent import analyze_prompt_intent
from fruth_inference.router import _load_runtime_inference_policy
from fruth_inference.request_phase_graph import build_request_phase_graph
from fruth_inference.phase_graph_queries import (
    current_phase_capability,
    current_phase_is_graph_resolved,
    current_phase_reason,
    downstream_phase_capabilities,
    downstream_phase_records,
)
from fruth_server.recovery_contract import RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT
from fruth_services.responses import extract_responses_current_turn_prompt


_INFERENCE_RUNTIME_POLICY_SYSTEM_MARKER = 'Fruth interpretive inference runtime policy: attached.'


_PREPARE_PHASE_SYSTEM_MARKER = 'Fruth phase contract: prepare-only.'


_SEMANTIC_PHASE_PAYLOAD_KEYS = (
    'content_payload',
    'stage_direction',
    'phase_summary',
    'content_payload_source',
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
    'requires_artifact',
    'text_artifact_extension',
    'text_artifact_source_name',
    'text_artifact_source',
    'text_artifact_target_path',
    'artifact_request',
    'repair_scope',
    'resource_class',
    'dependency_policy',
    'runtime_scheduling_context',
)

@dataclass(frozen=True)
class PhasePreparation:
    extract_responses_prompt: Callable[[Any], str]

    def _current_phase_payload(self, phase_graph: Optional[dict[str, Any]]) -> dict[str, Any]:
        if not isinstance(phase_graph, dict):
            return {}
        current_phase_id = str(phase_graph.get('current_phase_id') or '').strip()
        phases = phase_graph.get('phases')
        if not current_phase_id or not isinstance(phases, list):
            return {}
        for raw_phase in phases:
            if not isinstance(raw_phase, dict):
                continue
            if str(raw_phase.get('phase_id') or '').strip() != current_phase_id:
                continue
            return dict(raw_phase)
        return {}

    def _request_is_inference_owned(
        self,
        *,
        route_payload: Optional[dict[str, Any]] = None,
        request_payload: Optional[dict[str, Any]] = None,
    ) -> bool:
        if isinstance(request_payload, Mapping):
            raw_value = request_payload.get('inference_route')
            if isinstance(raw_value, bool):
                return raw_value
            token = str(raw_value or '').strip().lower()
            if token in {'1', 'true', 'yes', 'on'}:
                return True
        if isinstance(route_payload, Mapping):
            token = str(route_payload.get('route_source') or '').strip().lower()
            if token in {'inference_carried', 'self_heal'}:
                return True
        return False

    def build_inference_runtime_policy_system_message(
        self,
        *,
        route_payload: Optional[dict[str, Any]] = None,
        request_payload: Optional[dict[str, Any]] = None,
        backend: Optional[str] = None,
    ) -> Optional[dict[str, str]]:
        if not self._request_is_inference_owned(
            route_payload=route_payload,
            request_payload=request_payload,
        ):
            return None
        runtime_policy = str(_load_runtime_inference_policy(scope='execution', backend=backend) or '').strip()
        if not runtime_policy:
            return None
        route_runtime = (
            route_payload.get('route_runtime')
            if isinstance(route_payload, Mapping)
            and isinstance(route_payload.get('route_runtime'), Mapping)
            else {}
        )
        profile = route_runtime.get('semantic_role_profile')
        # Graph-resolved preparation can skip model-backed planning. Carry the
        # already-selected guidance into execution through the same renderer.
        role_guidance = (
            [_semantic_role_guidance(dict(profile))]
            if isinstance(profile, Mapping) and profile else []
        )
        transport_guidance = []
        if normalize_backend(backend) == 'apple_pcc':
            transport_guidance = [
                'Apple Shortcuts only transports this text exchange to PCC and returns your text. '
                'It does not execute Fruth image, audio, file or review branches. Fruth dispatches '
                'those branches through its own runtime. Produce only the current phase result; '
                'do not promise work in Shortcuts or claim downstream results without supplied evidence.'
            ]
        return {
            'role': 'system',
            'content': '\n'.join(
                [
                    _INFERENCE_RUNTIME_POLICY_SYSTEM_MARKER,
                    "You implement Fruth's interpretive inference layer for this turn.",
                    'The applicable repository policy is attached below in full.',
                    runtime_policy,
                    *transport_guidance,
                    *role_guidance,
                ]
            ),
        }

    def inject_inference_runtime_policy_into_chat_messages(
        self,
        messages: list[dict[str, Any]],
        *,
        route_payload: Optional[dict[str, Any]] = None,
        request_payload: Optional[dict[str, Any]] = None,
        backend: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        injected = list(messages or [])
        system_message = self.build_inference_runtime_policy_system_message(
            route_payload=route_payload,
            request_payload=request_payload,
            backend=backend,
        )
        if not system_message:
            return injected
        # Rebind an existing injection when execution moves to a different backend.
        return [system_message] + [
            item for item in injected
            if not (isinstance(item, dict)
                    and str(item.get('role') or '').strip().lower() == 'system'
                    and str(item.get('content') or '').startswith(_INFERENCE_RUNTIME_POLICY_SYSTEM_MARKER))
        ]

    def _extract_semantic_phase_payload_from_payload(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        nested = payload.get('phase_payload') if isinstance(payload.get('phase_payload'), dict) else {}
        semantic_payload: dict[str, Any] = {}
        for key in _SEMANTIC_PHASE_PAYLOAD_KEYS:
            value = payload.get(key)
            if value in (None, '', [], {}):
                value = nested.get(key)
            if value not in (None, '', [], {}):
                semantic_payload[key] = value
        return semantic_payload

    def semantic_payload_for_capability(
        self,
        payload: Optional[dict[str, Any]],
        *,
        capability: Optional[str],
    ) -> dict[str, Any]:
        semantic_payload = self._extract_semantic_phase_payload_from_payload(payload)
        normalized_capability = normalize_capability(capability)
        if normalized_capability == CAPABILITY_IMAGE_GENERATION:
            artifact_prompt = str(semantic_payload.get('artifact_prompt') or '').strip()
            expected_batch_count, invalid_batch_count = _parse_image_batch_expected_count(
                semantic_payload.get('batch_prompt_expected_count'),
                present='batch_prompt_expected_count' in semantic_payload,
            )
            batch_prompts = [
                str(item or '').strip()
                for item in (semantic_payload.get('batch_prompts') or [])
                if str(item or '').strip()
            ]
            exact_counted_batch = bool(
                expected_batch_count < 2
                or len(batch_prompts) == expected_batch_count
            )
            counted_batch_incomplete = bool(
                expected_batch_count >= 2
                and not exact_counted_batch
            )
            blocked_batch_contract = bool(
                semantic_payload.get('materialization_blocked') is True
                or str(
                    semantic_payload.get('branch_contract_error') or ''
                ).strip()
                == 'incomplete_image_prompt_batch'
                or invalid_batch_count
                or counted_batch_incomplete
            )
            if invalid_batch_count or counted_batch_incomplete:
                # A counted image cohort is executable only when every
                # branch-local slot is present. Never turn the preparation
                # response (or a stale prompt carried beside it) into a
                # shared image prompt when that contract is incomplete.
                semantic_payload.pop('artifact_prompt', None)
                semantic_payload.pop('artifact_prompt_source', None)
                semantic_payload.pop('batch_prompts', None)
                semantic_payload.pop('batch_prompts_source', None)
                semantic_payload.pop('batch_prompt_source_phase_id', None)
                semantic_payload.update(
                    {
                        'branch_contract_error': 'incomplete_image_prompt_batch',
                        'candidate_extraction_issue': (
                            'invalid_image_prompt_batch_count'
                            if invalid_batch_count
                            else 'missing_exact_branch_local_image_prompt_batch'
                        ),
                        **(
                            {'batch_prompt_expected_count': expected_batch_count}
                            if not invalid_batch_count
                            else {'batch_prompt_expected_count_invalid': True}
                        ),
                        'batch_prompt_actual_count': len(batch_prompts),
                        'materialization_blocked': True,
                        'repair_action': RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT,
                        'counted_batch_prompt_carriers_blocked': True,
                    }
                )
            if not artifact_prompt and not blocked_batch_contract:
                shared_body = str(semantic_payload.get('content_payload') or '').strip()
                if shared_body:
                    semantic_payload['artifact_prompt'] = shared_body
                    semantic_payload['artifact_prompt_source'] = (
                        str(semantic_payload.get('content_payload_source') or '').strip()
                        or 'shared_content_payload'
                    )
                    semantic_payload.setdefault('phase_summary', shared_body)
        if normalized_capability == CAPABILITY_TEXT_TO_SPEECH:
            content_payload = str(semantic_payload.get('content_payload') or '').strip()
            if not content_payload:
                shared_prompt = str(semantic_payload.get('artifact_prompt') or '').strip()
                if shared_prompt:
                    semantic_payload['content_payload'] = shared_prompt
                    semantic_payload['content_payload_source'] = (
                        str(semantic_payload.get('artifact_prompt_source') or '').strip()
                        or 'shared_artifact_prompt'
                    )
        return {
            key: value
            for key, value in semantic_payload.items()
            if value not in (None, '', [], {})
        }

    def resolve_prepare_phase_contract(
        self,
        *,
        route_payload: Optional[dict[str, Any]] = None,
        request_payload: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        extract_responses_prompt = self.extract_responses_prompt

        route_info = route_payload if isinstance(route_payload, dict) else {}
        request_info = request_payload if isinstance(request_payload, dict) else {}
        route_runtime = (
            route_info.get('route_runtime')
            if isinstance(route_info.get('route_runtime'), dict)
            else {}
        )
        request_phase_graph = (
            dict(route_runtime.get('request_phase_graph'))
            if isinstance(route_runtime.get('request_phase_graph'), dict)
            else None
        )
        if not request_phase_graph:
            request_phase_graph = build_request_phase_graph(
                extract_responses_prompt(request_info),
                intent_prompt=extract_responses_current_turn_prompt(request_info),
                request_payload=request_info,
                route_payload=route_info,
            )
        if not current_phase_is_graph_resolved(request_phase_graph):
            return None
        if current_phase_capability(request_phase_graph) != CAPABILITY_CHAT:
            return None
        current_phase = self._current_phase_payload(request_phase_graph)
        current_phase_kind = str(current_phase.get('kind') or '').strip().lower()
        current_phase_role = str(current_phase.get('role') or '').strip().lower()
        downstream = downstream_phase_capabilities(request_phase_graph)
        if not downstream:
            return None
        if current_phase_kind != 'prepare' and current_phase_role != 'text_preparation':
            return None
        return {
            'phase_graph': request_phase_graph,
            'current_phase': current_phase,
            'downstream_capabilities': downstream,
            'reason': current_phase_reason(request_phase_graph),
        }

    def plain_alpha_image_prompt_prepare_authority(
        self,
        phase_graph: Any,
        *,
        expected_count: int,
    ) -> dict[str, Any]:
        """Prove that untyped A..N text is the direct producer for N image slots."""

        try:
            normalized_count = int(expected_count or 0)
        except (TypeError, ValueError):
            normalized_count = 0
        if not 2 <= normalized_count <= 26 or not isinstance(phase_graph, Mapping):
            return {}
        graph = dict(phase_graph)
        if not current_phase_is_graph_resolved(graph):
            return {}
        if current_phase_capability(graph) != CAPABILITY_CHAT:
            return {}
        current_phase = self._current_phase_payload(graph)
        current_phase_id = str(current_phase.get('phase_id') or '').strip()
        if not current_phase_id:
            return {}
        current_phase_kind = str(current_phase.get('kind') or '').strip().lower()
        current_phase_role = str(current_phase.get('role') or '').strip().lower()
        if current_phase_kind != 'prepare' and current_phase_role != 'text_preparation':
            return {}
        prompt_intent = (
            graph.get('prompt_intent')
            if isinstance(graph.get('prompt_intent'), Mapping)
            else {}
        )
        try:
            requested_count = int(prompt_intent.get('requested_visual_output_count') or 0)
        except (TypeError, ValueError):
            requested_count = 0
        if requested_count != normalized_count:
            return {}

        direct_children: list[dict[str, Any]] = []
        for raw_phase in graph.get('phases') or []:
            if not isinstance(raw_phase, Mapping):
                continue
            dependencies = [
                str(item or '').strip()
                for item in (raw_phase.get('depends_on') or [])
                if str(item or '').strip()
            ]
            if current_phase_id not in dependencies:
                continue
            direct_children.append(dict(raw_phase))
        if len(direct_children) != normalized_count:
            return {}
        if any(
            normalize_capability(item.get('capability')) != CAPABILITY_IMAGE_GENERATION
            or [
                str(value or '').strip()
                for value in (item.get('depends_on') or [])
                if str(value or '').strip()
            ] != [current_phase_id]
            for item in direct_children
        ):
            return {}
        queue_indexes: list[int] = []
        for child in direct_children:
            try:
                queue_indexes.append(int(child.get('queue_index') or 0))
            except (TypeError, ValueError):
                return {}
        if sorted(queue_indexes) != list(range(1, normalized_count + 1)):
            return {}
        return {
            'kind': 'graph_direct_image_producer_contract',
            'source_phase_id': current_phase_id,
            'expected_count': normalized_count,
        }

    def _format_prepare_phase_capability_label(self, capability: str) -> str:
        normalized = normalize_capability(capability)
        if normalized == CAPABILITY_IMAGE_GENERATION:
            return 'image generation'
        if normalized == CAPABILITY_TEXT_TO_SPEECH:
            return 'speech synthesis'
        if normalized == CAPABILITY_SPEECH_TO_TEXT:
            return 'speech transcription'
        if normalized == CAPABILITY_VISION_ANALYSIS:
            return 'vision analysis'
        return normalized.replace('_', ' ') if normalized else 'follow-up materialization'

    def numbered_image_prepare_authority(
        self,
        phase_graph: Any,
    ) -> dict[str, Any]:
        """Prove that one prepare phase directly produces an exact image cohort."""

        if not isinstance(phase_graph, Mapping):
            return {}
        graph = dict(phase_graph)
        if not current_phase_is_graph_resolved(graph):
            return {}
        if current_phase_capability(graph) != CAPABILITY_CHAT:
            return {}
        current_phase = self._current_phase_payload(graph)
        current_phase_id = str(current_phase.get('phase_id') or '').strip()
        current_phase_kind = str(current_phase.get('kind') or '').strip().lower()
        current_phase_role = str(current_phase.get('role') or '').strip().lower()
        if (
            not current_phase_id
            or (current_phase_kind != 'prepare' and current_phase_role != 'text_preparation')
        ):
            return {}
        prompt_intent = (
            graph.get('prompt_intent')
            if isinstance(graph.get('prompt_intent'), Mapping)
            else {}
        )
        if not bool(prompt_intent.get('counted_visual_output_obligation')):
            return {}
        expected_count, invalid_expected_count = _parse_image_batch_expected_count(
            prompt_intent.get('requested_visual_output_count'),
            present='requested_visual_output_count' in prompt_intent,
        )
        if invalid_expected_count or not 2 <= expected_count <= 26:
            return {}

        direct_image_children: list[dict[str, Any]] = []
        for raw_branch in downstream_phase_records(graph):
            if not isinstance(raw_branch, Mapping):
                continue
            if normalize_capability(raw_branch.get('capability')) != CAPABILITY_IMAGE_GENERATION:
                continue
            dependencies = [
                str(item or '').strip()
                for item in (raw_branch.get('depends_on') or [])
                if str(item or '').strip()
            ]
            if dependencies == [current_phase_id]:
                direct_image_children.append(dict(raw_branch))
        if len(direct_image_children) != expected_count:
            return {}
        queue_indexes: list[int] = []
        for child in direct_image_children:
            try:
                queue_indexes.append(int(child.get('queue_index') or 0))
            except (TypeError, ValueError):
                return {}
        if sorted(queue_indexes) != list(range(1, expected_count + 1)):
            return {}
        return {
            'kind': 'graph_direct_numbered_image_producer_contract',
            'source_phase_id': current_phase_id,
            'expected_count': expected_count,
        }

    def numbered_audio_prepare_authority(
        self,
        phase_graph: Any,
    ) -> dict[str, Any]:
        """Prove that one prepare phase directly feeds N distinct TTS slots."""

        if not isinstance(phase_graph, Mapping):
            return {}
        graph = dict(phase_graph)
        if not current_phase_is_graph_resolved(graph):
            return {}
        if current_phase_capability(graph) != CAPABILITY_CHAT:
            return {}
        current_phase = self._current_phase_payload(graph)
        current_phase_id = str(current_phase.get('phase_id') or '').strip()
        current_phase_kind = str(current_phase.get('kind') or '').strip().lower()
        current_phase_role = str(current_phase.get('role') or '').strip().lower()
        if (
            not current_phase_id
            or (current_phase_kind != 'prepare' and current_phase_role != 'text_preparation')
        ):
            return {}
        prompt_intent = (
            graph.get('prompt_intent')
            if isinstance(graph.get('prompt_intent'), Mapping)
            else {}
        )
        if (
            not bool(prompt_intent.get('counted_audio_output_obligation'))
            or bool(prompt_intent.get('audio_output_count_exceeds_bound'))
        ):
            return {}
        requested_count = intent_coverage._coerce_positive_int(
            prompt_intent.get('requested_audio_output_count')
        )
        if not 2 <= requested_count <= 6:
            return {}
        direct_tts_children: list[dict[str, Any]] = []
        for raw_branch in downstream_phase_records(graph):
            if not isinstance(raw_branch, Mapping):
                continue
            if normalize_capability(raw_branch.get('capability')) != CAPABILITY_TEXT_TO_SPEECH:
                continue
            dependencies = [
                str(item or '').strip()
                for item in (raw_branch.get('depends_on') or [])
                if str(item or '').strip()
            ]
            if dependencies != [current_phase_id]:
                continue
            direct_tts_children.append(dict(raw_branch))
        if len(direct_tts_children) != requested_count:
            return {}
        candidate_indexes: list[int] = []
        variants: list[dict[str, Any]] = []
        for branch in direct_tts_children:
            if str(branch.get('selection_policy') or '').strip().lower() != 'selected_candidate_only':
                return {}
            candidate_index = intent_coverage._coerce_positive_int(
                branch.get('candidate_selection_index')
            )
            candidate_count = intent_coverage._coerce_positive_int(
                branch.get('candidate_selection_count')
            )
            variant_index = intent_coverage._coerce_positive_int(
                branch.get('audio_variant_index')
            )
            if (
                not candidate_index
                or candidate_count != requested_count
                or variant_index != candidate_index
            ):
                return {}
            candidate_indexes.append(candidate_index)
            variants.append(
                {
                    'index': candidate_index,
                    'lang_code': str(branch.get('lang_code') or '').strip().lower() or None,
                    'role': str(branch.get('audio_variant_role') or '').strip() or None,
                    'contract_source': str(
                        branch.get('audio_variant_contract_source') or ''
                    ).strip() or None,
                }
            )
        if sorted(candidate_indexes) != list(range(1, requested_count + 1)):
            return {}
        variants.sort(key=lambda item: int(item['index']))
        return {
            'kind': 'graph_direct_numbered_audio_producer_contract',
            'source_phase_id': current_phase_id,
            'expected_count': requested_count,
            'variants': variants,
        }

    def build_prepare_phase_system_message(
        self,
        prepare_contract: Optional[dict[str, Any]],
    ) -> Optional[dict[str, str]]:
        if not isinstance(prepare_contract, dict):
            return None
        downstream_capabilities = [
            normalize_capability(candidate)
            for candidate in (prepare_contract.get('downstream_capabilities') or [])
            if normalize_capability(candidate)
        ]
        if not downstream_capabilities:
            return None
        phase_graph = (
            prepare_contract.get('phase_graph')
            if isinstance(prepare_contract.get('phase_graph'), Mapping)
            else {}
        )
        numbered_image_contract = self.numbered_image_prepare_authority(phase_graph)
        numbered_audio_contract = self.numbered_audio_prepare_authority(phase_graph)
        file_phases = [
            phase for phase in (phase_graph.get('phases') or [])
            if isinstance(phase, Mapping) and isinstance(phase.get('artifact_request'), Mapping)
        ]
        saved_read_consumers = [
            phase for phase in file_phases
            if phase.get('dependency_contract') == 'saved_file_read_required'
        ]
        downstream_labels = [
            self._format_prepare_phase_capability_label(candidate)
            for candidate in downstream_capabilities
        ]
        if len(downstream_labels) == 1:
            downstream_clause = downstream_labels[0]
        elif len(downstream_labels) == 2:
            downstream_clause = f'{downstream_labels[0]} and {downstream_labels[1]}'
        else:
            downstream_clause = ', '.join(downstream_labels[:-1]) + f', and {downstream_labels[-1]}'
        reason = str(prepare_contract.get('reason') or '').strip()
        lines = [
            _PREPARE_PHASE_SYSTEM_MARKER,
            'You are executing only the current text-preparation phase of a multi-phase Fruth request.',
            f'Downstream phases will handle {downstream_clause} separately after this phase completes.',
            'Return only the prepared substantive text needed by those downstream phases.',
            'Do not pre-answer downstream artifact-dependent review, analysis, comparison, transcription, or final-summary tasks before their evidence branches have run.',
            'If the user says to review, analyze, compare, or summarize after an artifact is ready, leave that work to the downstream branch.',
            'Do not say that you cannot generate images, audio, or other media.',
            'Do not mention being text-only, incapable, unable to help, or that another model or route will finish the task.',
            'Preserve the user-requested tone, structure, wording constraints, and exactness requirements when they belong to the content itself.',
        ]
        if numbered_image_contract:
            expected_image_count = int(numbered_image_contract['expected_count'])
            lines.append(
                'Start the response with exactly one `### Image Generation Prompts` section.'
            )
            lines.append(
                f'Under that heading, return exactly {expected_image_count} numbered image prompts '
                f'using labels 1. through {expected_image_count}.'
            )
            lines.append(
                'Each numbered prompt feeds exactly one downstream image-generation branch. '
                'Keep every prompt self-contained, visually concrete, distinct, and in the '
                'user-requested order; do not merge, omit, duplicate, or add slots.'
            )
            lines.append(
                'Keep code, data, filenames, implementation notes, and downstream review claims '
                'outside the numbered image prompts.'
            )
            if any(
                capability != CAPABILITY_IMAGE_GENERATION
                for capability in downstream_capabilities
            ):
                lines.append(
                    f'After image prompt {expected_image_count}, continue with separately labeled '
                    'substantive content required by non-image downstream phases. Keep each requested '
                    'file or payload in its own clearly named section.'
                )
        if numbered_audio_contract:
            expected_count = int(numbered_audio_contract['expected_count'])
            if numbered_image_contract:
                lines.append(
                    'After the image-prompt section and before any file sections, add exactly one '
                    '`### Text-to-Speech Payload` section.'
                )
                lines.append(
                    f'In that section, return exactly {expected_count} numbered, directly speakable '
                    f'bodies using the labels 1. through {expected_count}. Each numbered body must be '
                    'self-contained and distinct, and its text must contain only wording that should be spoken.'
                )
            else:
                lines.append(
                    f'Return exactly {expected_count} numbered, directly speakable bodies using the labels '
                    f'1. through {expected_count}. Each numbered body must be self-contained and distinct, '
                    'and its text must contain only wording that should be spoken.'
                )
                lines.append(
                    'Do not add any other heading, label, bullet, explanation, or meta commentary.'
                )
            language_labels = {'de': 'German', 'en': 'English'}
            for variant in numbered_audio_contract.get('variants') or []:
                lang_code = str(variant.get('lang_code') or '').strip().lower()
                role = str(variant.get('role') or '').strip()
                if not lang_code and not role:
                    continue
                language = language_labels.get(lang_code, lang_code or 'the requested language')
                role_clause = f' and fulfill the {role.replace("_", " ")} role' if role else ''
                lines.append(
                    f'Numbered body {int(variant["index"])} must be in {language}{role_clause}.'
                )
        elif not numbered_image_contract and not file_phases:
            lines.append(
                'Do not add headings, labels, prompt wrappers, bullet framing, or meta commentary unless the user explicitly requested them.'
            )
        if CAPABILITY_IMAGE_GENERATION in downstream_capabilities:
            if not numbered_image_contract:
                lines.append(
                    'If downstream image generation depends on this text, make the body prompt-ready and visually concrete.'
                )
        if CAPABILITY_TEXT_TO_SPEECH in downstream_capabilities:
            if numbered_audio_contract:
                lines.append(
                    'Each numbered body feeds exactly one downstream speech-synthesis branch.'
                )
            else:
                lines.append(
                    'If downstream speech depends on this text, make the body directly speakable without capability notes.'
                )
        if (
            len(downstream_capabilities) > 1
            and not numbered_audio_contract
            and not numbered_image_contract
            and not file_phases
        ):
            lines.append(
                'When multiple downstream phases depend on the same text, produce one clean reusable body that all of them can consume.'
            )
        if (CAPABILITY_TEXT_TO_SPEECH in downstream_capabilities
                and not numbered_audio_contract
                and (file_phases or CAPABILITY_IMAGE_GENERATION in downstream_capabilities)):
            lines.append(
                'Before the file blocks, use exactly the heading ### Text-to-Speech Payload '
                'and put only the narration beneath it as plain text. This is a speech-producer '
                'input, not a WAV file body; never use a wav fence or a .wav filename heading.'
            )
        if file_phases:
            lines.append(
                'File contents use separate filename headings and language-labelled fenced blocks. '
                'Each block contains only that file body, never a JSON object mapping filenames to contents.'
            )
        if saved_read_consumers:
            lines.append(
                'This workflow has a saved-file-read dependency. Prepare only the source file data now. '
                'Do not prepare the consumer file or calculate its result before the actual saved-file '
                'read; that dependent branch will receive the read bytes and author its own output.'
            )
        if reason:
            lines.append(f'Current phase reason: {reason}')
        return {
            'role': 'system',
            'content': '\n'.join(lines),
        }

    def build_external_prepare_phase_bounded_task(
        self,
        *,
        prepare_contract: Optional[dict[str, Any]] = None,
        route_payload: Optional[dict[str, Any]] = None,
        request_payload: Optional[dict[str, Any]] = None,
    ) -> str:
        """Return the live external task for a graph-owned preparation phase."""

        if not isinstance(prepare_contract, dict):
            prepare_contract = self.resolve_prepare_phase_contract(
                route_payload=route_payload,
                request_payload=request_payload,
            )
        system_message = self.build_prepare_phase_system_message(prepare_contract)
        if not system_message:
            return ''
        phase_contract = str(system_message.get('content') or '').strip()
        if not phase_contract:
            return ''
        return '\n'.join(
            [
                phase_contract,
                '',
                'The complete user request is supplied separately in '
                '<fruth_promoted_context> as reference-only intent for this phase.',
                'Do not perform filesystem writes, invoke downstream media generation, '
                'or claim that downstream artifacts were created.',
                'Return only the current preparation result to Fruth. Fruth retains '
                'authority for downstream execution, materialization, integrity checks, '
                'Closure, and publication.',
            ]
        )

    def inject_prepare_phase_contract_into_chat_messages(
        self,
        messages: list[dict[str, Any]],
        *,
        route_payload: Optional[dict[str, Any]] = None,
        request_payload: Optional[dict[str, Any]] = None,
        backend: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        normalized_backend = normalize_backend(backend)
        current_prompt = extract_responses_current_turn_prompt(request_payload or {})
        if (normalized_backend == 'apple_fm'
                and analyze_prompt_intent(current_prompt).get('artifact_state_readback_request')):
            return self._scope_saved_artifact_explanation_messages(messages, current_prompt)
        if normalized_backend == 'apple_pcc' and not self._request_is_inference_owned(
            route_payload=route_payload, request_payload=request_payload,
        ):
            return list(messages or [])
        prepare_contract = self.resolve_prepare_phase_contract(
            route_payload=route_payload,
            request_payload=request_payload,
        )
        if not prepare_contract:
            return list(messages or [])
        injected = list(messages or [])
        if normalized_backend in {'apple_fm', 'apple_pcc'}:
            downstream = set(prepare_contract.get('downstream_capabilities') or [])
            if CAPABILITY_IMAGE_GENERATION in downstream and CAPABILITY_TEXT_TO_SPEECH in downstream:
                task = ('Write the requested image prompts, spoken text and file contents in the '
                        'separate sections specified by the preparation contract. In HTML/CSS, '
                        'place each image in its requested section using its own distinct filename. '
                        'Include all requested images as img elements or CSS backgrounds, with '
                        'responsive sizing. Label each image prompt with its requested page role. '
                        'Check that every numbered image has a matching HTML/CSS reference. '
                        'Do not replace their section placements with a gallery. '
                        'Put the exact narration alone under ### Text-to-Speech Payload as plain text, '
                        'never a wav code block or file-content section.')
            elif CAPABILITY_IMAGE_GENERATION in downstream:
                task = ('Write only the requested number of distinct, self-contained textual '
                        'image-generation prompts. Apply the reference request\'s subjects, settings, '
                        'poses, camera framing and style to each prompt. End after the last prompt.')
            elif CAPABILITY_TEXT_TO_SPEECH in downstream:
                task = ('Compose only the requested answer or creative passage as directly speakable '
                        'text. Apply the reference request\'s sentence count, language, tone and exact '
                        'wording. Return only the sentences to be spoken and end immediately after '
                        'the last sentence.')
            else:
                task = ('Author only the substantive text or file contents required by the current '
                        'preparation contract, using its declared output format. For separately '
                        'requested files, provide each file\'s complete contents in its own '
                        'filename-labelled fenced block; preserve all requested data values.')
            phase_graph = prepare_contract.get('phase_graph') or {}
            numbered_images = self.numbered_image_prepare_authority(phase_graph)
            if numbered_images:
                count = int(numbered_images['expected_count'])
                task += (f' Start with ### Image Generation Prompts and exactly {count} numbered '
                         f'paragraphs, labelled 1. through {count}. Use plain prompt text, not JSON. '
                         'Describe only the scene for each image, including the requested camera framing.')
            request_prompt = extract_responses_current_turn_prompt(request_payload or {})
            if CAPABILITY_IMAGE_GENERATION in downstream and re.search(
                r'\bselfies?\b', request_prompt, re.IGNORECASE,
            ):
                task += ' Every prompt must explicitly describe a selfie camera composition.'
            if any(
                isinstance(phase, Mapping)
                and phase.get('dependency_contract') == 'saved_file_read_required'
                for phase in (phase_graph.get('phases') or [])
            ):
                task = ('Prepare only the initial source file data in a filename heading and '
                        'language-labelled fenced block. The saved-file-read consumer runs later: '
                        'do not include its output file or a calculated result now. Do not return '
                        'a JSON object mapping filenames to file contents.')
                producers = [
                    phase['artifact_request']
                    for phase in (phase_graph.get('phases') or [])
                    if isinstance(phase, Mapping)
                    and isinstance(phase.get('artifact_request'), Mapping)
                    and phase['artifact_request'].get('saved_file_producer')
                ]
                if producers:
                    filenames = [
                        f"{item.get('source_name')}.{item.get('extension')}"
                        for item in producers
                    ]
                    task += (' The only file contents required in this response are: '
                             + ', '.join(filenames) + '. End after the source file block(s).')
                    if len(producers) == 1 and producers[0].get('extension') == 'json':
                        task = (f'Return only the raw JSON source data for {filenames[0]}. '
                                'Begin with { or [ and end with the matching } or ]. '
                                'No heading, code fence, filename wrapper, HTML or consumer result. '
                                'The consumer will be authored after the actual saved-file read.')
            for index in range(len(injected) - 1, -1, -1):
                item = injected[index]
                if not isinstance(item, dict) or item.get('role') != 'user':
                    continue
                content = item.get('content')
                if isinstance(content, str) and not (
                    content.startswith('<fruth_bounded_task>')
                    or (content.startswith('<fruth_promoted_context>')
                        and content.endswith('</fruth_bounded_task>'))
                ):
                    injected[index] = {**item, 'content': (
                        '<fruth_promoted_context>\n' + content + '\n</fruth_promoted_context>\n\n'
                        'The workflow above is reference context. '
                        'Later producers and evidence branches remain Fruth runtime work. '
                        'Execute only the following current phase task:\n'
                        '<fruth_bounded_task>\n' + task + '\n</fruth_bounded_task>'
                    )}
                break
        if any(
            str(item.get('role') or '').strip().lower() == 'system'
            and _PREPARE_PHASE_SYSTEM_MARKER in str(item.get('content') or '')
            for item in injected
            if isinstance(item, dict)
        ):
            return injected
        system_message = self.build_prepare_phase_system_message(prepare_contract)
        if not system_message:
            return injected
        return [system_message] + injected

    @staticmethod
    def _scope_saved_artifact_explanation_messages(
        messages: list[dict[str, Any]], current_prompt: str,
    ) -> list[dict[str, Any]]:
        """Keep selected history as data while making AFM's live task explicit.

        No history or evidence is removed. Canonical request/history stays typed;
        only this backend's execution projection uses the existing bounded-task
        and promoted-context envelope instead of replaying old executable turns.
        """
        injected = list(messages or [])
        if not injected or injected[-1].get('role') != 'user':
            return injected
        if str(injected[-1].get('content') or '').startswith('<fruth_promoted_context>'):
            return injected
        history = [item for item in injected[:-1] if item.get('role') in {'user', 'assistant'}]
        if (any(item.get('role') not in {'system', 'user', 'assistant'}
                or item.get('tool_calls') or item.get('function_call') for item in injected)
                or any(not isinstance(item.get('content'), str) for item in [*history, injected[-1]])):
            # Preserve typed multimodal/tool payloads; this text-only envelope
            # must not serialize images as prose or discard current attachments.
            return injected
        preserved = [item for item in injected[:-1] if item.get('role') not in {'user', 'assistant'}]
        context = json.dumps({'historical_messages': history}, ensure_ascii=False, separators=(',', ':'))
        task = (
            '<fruth_promoted_context>\n' + context + '\n</fruth_promoted_context>\n\n'
            'The prior conversation above is reference-only. Answer the current evidence question; '
            'do not execute an earlier speaking or transcription request.\n'
            'Write a concise explanation to the user, not a semantic-review verdict or a lifecycle decision. '
            'An artifact\'s producer instance is the saved observation whose branch_id and phase_id '
            'match that artifact; other observations may belong to its consumers. State when that '
            'identity is missing. Keep file-byte hashes separate from source/transcript text hashes.\n'
            '<fruth_bounded_task>\n' + current_prompt + '\n</fruth_bounded_task>'
        )
        return [*preserved, {**injected[-1], 'content': task}]

    def build_response_semantic_phase_payload(
        self,
        *,
        output_text: str,
        route_payload: Optional[dict[str, Any]] = None,
        request_payload: Optional[dict[str, Any]] = None,
        source_payload: Optional[dict[str, Any]] = None,
        capability: Optional[str] = None,
    ) -> dict[str, Any]:
        existing = self._extract_semantic_phase_payload_from_payload(source_payload)
        normalized_capability = normalize_capability(capability)
        prepared_text = str(output_text or '').strip()
        # A non-empty chat preparation output is the newest semantic source.
        # Re-evaluate it even when an earlier payload already carried shared
        # or full-display semantic fields; otherwise stale fields can bypass
        # counted-batch validation entirely. Preserve existing semantics when
        # there is no new preparation output or this is not a chat phase.
        if existing and (normalized_capability != CAPABILITY_CHAT or not prepared_text):
            return existing
        if normalized_capability != CAPABILITY_CHAT:
            return {}
        prepare_contract = self.resolve_prepare_phase_contract(
            route_payload=route_payload,
            request_payload=request_payload,
        )
        if not prepare_contract or not prepared_text:
            return existing
        downstream = [
            normalize_capability(candidate)
            for candidate in (prepare_contract.get('downstream_capabilities') or [])
            if normalize_capability(candidate)
        ]
        expected_visual_output_count = 0
        phase_graph = (
            prepare_contract.get('phase_graph')
            if isinstance(prepare_contract.get('phase_graph'), Mapping)
            else {}
        )
        prompt_intent = (
            phase_graph.get('prompt_intent')
            if isinstance(phase_graph.get('prompt_intent'), Mapping)
            else {}
        )
        expected_visual_output_count, invalid_visual_output_count = (
            _parse_image_batch_expected_count(
                prompt_intent.get('requested_visual_output_count'),
                present='requested_visual_output_count' in prompt_intent,
            )
        )
        plain_alpha_authority = self.plain_alpha_image_prompt_prepare_authority(
            phase_graph,
            expected_count=expected_visual_output_count,
        )
        numbered_image_authority = self.numbered_image_prepare_authority(
            phase_graph
        )
        batch_prompt_authority = numbered_image_authority or plain_alpha_authority
        if not downstream:
            return {}
        semantic_payload: dict[str, Any] = {}
        if CAPABILITY_TEXT_TO_SPEECH in downstream:
            semantic_payload.update(
                {
                    key: value
                    for key, value in split_visible_tts_payload(prepared_text).items()
                    if value not in (None, '', [], {})
                }
            )
        if CAPABILITY_IMAGE_GENERATION in downstream:
            image_payload = {
                key: value
                for key, value in split_visible_image_payload(prepared_text).items()
                if value not in (None, '', [], {})
            }
            batch_prompts = image_prompt_preparation.extract_batch_image_prompts(
                prepared_text,
                expected_count=expected_visual_output_count,
                allow_plain_alpha_sequence=bool(plain_alpha_authority),
            )
            incomplete_counted_batch = bool(
                invalid_visual_output_count
                or expected_visual_output_count >= 2
                and len(batch_prompts) != expected_visual_output_count
            )
            if incomplete_counted_batch:
                diagnostic_prompts = image_prompt_preparation.extract_batch_image_prompts(
                    prepared_text,
                    allow_plain_alpha_sequence=bool(plain_alpha_authority),
                )
                image_payload.pop('artifact_prompt', None)
                image_payload.pop('artifact_prompt_source', None)
                image_payload.update(
                    {
                        'branch_contract_error': 'incomplete_image_prompt_batch',
                        'candidate_extraction_issue': (
                            'invalid_image_prompt_batch_count'
                            if invalid_visual_output_count
                            else 'missing_exact_branch_local_image_prompt_batch'
                        ),
                        **(
                            {'batch_prompt_expected_count': expected_visual_output_count}
                            if not invalid_visual_output_count
                            else {'batch_prompt_expected_count_invalid': True}
                        ),
                        'batch_prompt_actual_count': len(diagnostic_prompts),
                        'materialization_blocked': True,
                        'repair_action': RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT,
                        'counted_batch_prompt_carriers_blocked': True,
                    }
                )
            if len(batch_prompts) > 1 and not incomplete_counted_batch:
                image_payload['batch_prompts'] = batch_prompts
                image_payload['batch_prompt_expected_count'] = (
                    expected_visual_output_count
                    if expected_visual_output_count >= 2
                    else len(batch_prompts)
                )
                if batch_prompt_authority:
                    image_payload['batch_prompts_source'] = 'semantic_prepare_phase_output'
                    image_payload['batch_prompt_source_phase_id'] = batch_prompt_authority[
                        'source_phase_id'
                    ]
                if str(image_payload.get('artifact_prompt_source') or '').strip() == 'full_display_text':
                    image_payload['artifact_prompt'] = batch_prompts[0]
                    image_payload['artifact_prompt_source'] = 'semantic_batch_prompts'
                    image_payload.setdefault('phase_summary', batch_prompts[0])
            if (
                not incomplete_counted_batch
                and
                semantic_payload.get('content_payload')
                and str(image_payload.get('artifact_prompt_source') or '').strip() == 'full_display_text'
            ):
                image_payload['artifact_prompt'] = semantic_payload.get('content_payload')
                image_payload['artifact_prompt_source'] = (
                    str(semantic_payload.get('content_payload_source') or '').strip()
                    or 'shared_content_payload'
                )
                image_payload.setdefault('phase_summary', semantic_payload.get('content_payload'))
            semantic_payload.update(image_payload)
        if not semantic_payload:
            semantic_payload = {
                'content_payload': prepared_text,
                'content_payload_source': 'current_phase_output',
            }
            if CAPABILITY_IMAGE_GENERATION in downstream:
                semantic_payload['artifact_prompt'] = prepared_text
                semantic_payload['artifact_prompt_source'] = 'current_phase_output'
                semantic_payload['phase_summary'] = prepared_text
            elif len(downstream) > 1:
                semantic_payload['phase_summary'] = prepared_text
        return semantic_payload

    def attach_response_semantic_phase_payload(
        self,
        payload: Optional[dict[str, Any]],
        *,
        output_text: str,
        route_payload: Optional[dict[str, Any]] = None,
        request_payload: Optional[dict[str, Any]] = None,
        capability: Optional[str] = None,
    ) -> dict[str, Any]:
        updated = dict(payload or {})
        semantic_payload = self.build_response_semantic_phase_payload(
            output_text=output_text,
            route_payload=route_payload,
            request_payload=request_payload,
            source_payload=updated,
            capability=capability,
        )
        if not semantic_payload:
            return updated
        updated['phase_payload'] = {
            **(
                updated.get('phase_payload')
                if isinstance(updated.get('phase_payload'), dict)
                else {}
            ),
            **semantic_payload,
        }
        for key, value in semantic_payload.items():
            updated[key] = value
        return updated

