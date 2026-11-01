"""Exact TTS source, physical audio and dependent transcript evidence.

Capability normalization is supplied explicitly. Physical verification delegates
to the audio integrity owner; no worker, HTTP or publication state is available.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from fruth_services import branch_result_contracts
import hashlib
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Mapping, Optional
from fruth_server.recovery_contract import RECOVERY_ACTION_RETRY_SAME_BRANCH
from fruth_services.tts_audio_integrity import (
    TTS_AUDIO_INTEGRITY_POLICY_ID,
    TTS_SEMANTIC_SOURCE_POLICY_ID,
    build_tts_audio_integrity_evidence,
    build_tts_semantic_source,
)


_TTS_STT_SEMANTIC_POLICY_ID = TTS_SEMANTIC_SOURCE_POLICY_ID


_TTS_STT_MIN_SOURCE_TOKENS_FOR_FULL_POLICY = 4


_TTS_STT_MIN_TOKEN_RECALL = 0.85


_TTS_STT_MIN_TOKEN_PRECISION = 0.65


_TTS_STT_MIN_SEQUENCE_RATIO = 0.60


_TTS_STT_SHORT_MIN_TOKEN_F1 = 0.80


_TTS_STT_SHORT_MIN_SEQUENCE_RATIO = 0.86


_TTS_STT_NEGATION_TOKENS = {
    'kein',
    'keine',
    'keinem',
    'keinen',
    'keiner',
    'keines',
    'never',
    'nicht',
    'nie',
    'niemals',
    'no',
    'not',
}

@dataclass(frozen=True)
class TtsResultEvidence:
    branch_capability: Callable[[Mapping[str, Any]], Optional[str]]
    normalize_capability: Callable[[Any], Optional[str]]
    capability_text_to_speech: str

    @staticmethod
    def tts_source_evidence_from_effective_data(
        effective_data: Mapping[str, Any],
        *,
        infer_payload: Optional[Mapping[str, Any]] = None,
        execution_contract: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        """Freeze the exact branch-local text handed to the TTS backend."""

        effective = effective_data if isinstance(effective_data, Mapping) else {}
        infer = infer_payload if isinstance(infer_payload, Mapping) else {}
        contract = execution_contract if isinstance(execution_contract, Mapping) else {}
        infer_prompt = infer.get('prompt')
        source_text = str(infer_prompt) if infer_prompt is not None else ''
        source_authority = 'final_infer_prompt' if source_text.strip() else ''
        if not source_text.strip():
            effective_content = effective.get('content_payload')
            source_text = (
                str(effective_content) if effective_content is not None else ''
            )
            if source_text.strip():
                source_authority = 'effective_branch_content_payload'
        if not source_text.strip():
            return {}
        content_payload_source = str(
            effective.get('content_payload_source')
            or contract.get('content_payload_source')
            or ''
        ).strip()
        return build_tts_semantic_source(
            source_text,
            source_authority=source_authority,
            source_text_source=content_payload_source or source_authority,
            branch_id=(
                contract.get('branch_id') or effective.get('branch_id')
            ),
            phase_id=contract.get('phase_id') or effective.get('phase_id'),
            lang_code=(
                infer.get('lang_code')
                or effective.get('lang_code')
                or contract.get('lang_code')
            ),
        )

    @classmethod
    def tts_source_evidence_from_prepared_plan(
        cls,
        plan: Mapping[str, Any],
        *,
        infer_result: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        payload = plan if isinstance(plan, Mapping) else {}
        planned_source = cls.tts_source_evidence_from_effective_data(
            payload.get('effective_data')
            if isinstance(payload.get('effective_data'), Mapping)
            else {},
            infer_payload=(
                payload.get('infer_payload')
                if isinstance(payload.get('infer_payload'), Mapping)
                else {}
            ),
            execution_contract=(
                payload.get('execution_contract')
                if isinstance(payload.get('execution_contract'), Mapping)
                else {}
            ),
        )
        result_payload = infer_result if isinstance(infer_result, Mapping) else {}
        runtime_source = (
            result_payload.get('tts_semantic_source')
            if isinstance(result_payload.get('tts_semantic_source'), Mapping)
            else {}
        )
        if not runtime_source:
            return planned_source
        runtime_source_text = str(
            runtime_source.get('tts_source_text') or ''
        )
        runtime_source_sha256 = str(
            runtime_source.get('tts_source_text_sha256') or ''
        ).strip().lower()
        runtime_source_contract_valid = bool(
            str(runtime_source.get('kind') or '').strip()
            == 'fruth.tts_semantic_source'
            and runtime_source.get('version') == 1
            and str(runtime_source.get('policy_id') or '').strip()
            == TTS_SEMANTIC_SOURCE_POLICY_ID
            and str(runtime_source.get('authority') or '').strip()
            == 'runtime_exact_backend_prompt'
            and runtime_source_text.strip()
            and runtime_source_sha256
            == hashlib.sha256(runtime_source_text.encode('utf-8')).hexdigest()
        )
        if not runtime_source_contract_valid:
            return planned_source

        # The inference owner has observed the post-extraction, post-file-merge
        # prompt actually handed to MLX Audio. Preserve that text/digest and add
        # only branch-local bindings that inference cannot know.
        enriched_source = dict(runtime_source)
        for key in ('branch_id', 'phase_id', 'lang_code'):
            value = planned_source.get(key)
            if (
                enriched_source.get(key) in (None, '', [], {})
                and value not in (None, '', [], {})
            ):
                enriched_source[key] = value
        return enriched_source

    def tts_audio_integrity_evidence_for_branch_result(
        self,
        branch: Mapping[str, Any],
        infer_result: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Return runtime-owned physical TTS evidence bound to the exact source."""

        if self.branch_capability(branch) != self.capability_text_to_speech:
            return {}
        result_payload = infer_result if isinstance(infer_result, Mapping) else {}
        source = (
            result_payload.get('tts_semantic_source')
            if isinstance(result_payload.get('tts_semantic_source'), Mapping)
            else {}
        )
        source_text = str(source.get('tts_source_text') or '')
        source_sha256 = str(source.get('tts_source_text_sha256') or '').strip()
        path = str(result_payload.get('saved_audio_path') or '').strip()
        existing = (
            result_payload.get('tts_audio_integrity_evidence')
            if isinstance(
                result_payload.get('tts_audio_integrity_evidence'),
                Mapping,
            )
            else {}
        )
        generation_budget = (
            result_payload.get('tts_generation_budget')
            if isinstance(result_payload.get('tts_generation_budget'), Mapping)
            else {}
        )
        tts_model_type = str(
            result_payload.get('tts_model_type')
            or generation_budget.get('tts_model_type')
            or ''
        ).strip()
        existing_contract_valid = bool(
            str(existing.get('kind') or '').strip()
            == 'fruth.tts_audio_integrity_evidence'
            and existing.get('version') == 1
            and str(existing.get('policy_id') or '').strip()
            == TTS_AUDIO_INTEGRITY_POLICY_ID
            and str(existing.get('authority') or '').strip()
            == 'runtime_deterministic_audio_verification'
        )
        if existing_contract_valid:
            evidence = dict(existing)
            evidence_source_sha256 = str(
                evidence.get('source_sha256') or ''
            ).strip()
            evidence_path = str(evidence.get('artifact_path') or '').strip()
            if source_sha256 and evidence_source_sha256 != source_sha256:
                defect_codes = [
                    str(item).strip()
                    for item in (evidence.get('defect_codes') or [])
                    if str(item).strip()
                ] if isinstance(evidence.get('defect_codes'), list) else []
                if 'TTS_AUDIO_SOURCE_BINDING_MISMATCH' not in defect_codes:
                    defect_codes.insert(0, 'TTS_AUDIO_SOURCE_BINDING_MISMATCH')
                evidence.update(
                    {
                        'status': 'failed',
                        'reason_code': 'TTS_AUDIO_SOURCE_BINDING_MISMATCH',
                        'materialization_eligible': False,
                        'expected_source_sha256': source_sha256,
                        'defect_codes': defect_codes,
                    }
                )
            elif path and evidence_path and Path(path).expanduser() != Path(
                evidence_path
            ).expanduser():
                defect_codes = [
                    str(item).strip()
                    for item in (evidence.get('defect_codes') or [])
                    if str(item).strip()
                ] if isinstance(evidence.get('defect_codes'), list) else []
                if 'TTS_AUDIO_ARTIFACT_BINDING_MISMATCH' not in defect_codes:
                    defect_codes.insert(0, 'TTS_AUDIO_ARTIFACT_BINDING_MISMATCH')
                evidence.update(
                    {
                        'status': 'failed',
                        'reason_code': 'TTS_AUDIO_ARTIFACT_BINDING_MISMATCH',
                        'materialization_eligible': False,
                        'expected_artifact_path': path,
                        'defect_codes': defect_codes,
                    }
                )
            return evidence
        if not source_text:
            return {
                'kind': 'fruth.tts_audio_integrity_evidence',
                'version': 1,
                'policy_id': TTS_AUDIO_INTEGRITY_POLICY_ID,
                'authority': 'runtime_deterministic_audio_verification',
                'status': 'unavailable',
                'reason_code': 'TTS_AUDIO_SOURCE_EVIDENCE_UNAVAILABLE',
                'materialization_eligible': False,
                'artifact_path': path or None,
                'defect_codes': ['TTS_AUDIO_SOURCE_EVIDENCE_UNAVAILABLE'],
            }
        return build_tts_audio_integrity_evidence(
            path,
            source_text,
            source_sha256=source_sha256 or None,
            generation_budget=generation_budget or None,
            model_family=(generation_budget.get('model_family') or None),
            tts_model_type=tts_model_type or None,
        )

    def tts_audio_integrity_error_for_branch_result(
        self,
        branch: Mapping[str, Any],
        infer_result: Mapping[str, Any],
    ) -> Optional[dict[str, Any]]:
        if self.branch_capability(branch) != self.capability_text_to_speech:
            return None
        evidence = self.tts_audio_integrity_evidence_for_branch_result(
            branch,
            infer_result,
        )
        if (
            str(evidence.get('status') or '').strip().lower() == 'passed'
            and evidence.get('materialization_eligible') is True
        ):
            return None
        reason_code = str(
            evidence.get('reason_code')
            or 'TTS_AUDIO_INTEGRITY_UNAVAILABLE'
        ).strip()
        defect_codes = [
            str(item).strip()
            for item in (evidence.get('defect_codes') or [])
            if str(item).strip()
        ] if isinstance(evidence.get('defect_codes'), list) else []
        if reason_code and reason_code not in defect_codes:
            defect_codes.insert(0, reason_code)
        saved_audio_path = str(
            (infer_result or {}).get('saved_audio_path') or ''
        ).strip()
        generation_budget = (
            (infer_result or {}).get('tts_generation_budget')
            if isinstance((infer_result or {}).get('tts_generation_budget'), Mapping)
            else {}
        )
        sampling_profile = (
            (infer_result or {}).get('tts_sampling_profile')
            if isinstance((infer_result or {}).get('tts_sampling_profile'), Mapping)
            else {}
        )
        return {
            'code': 'TTS_AUDIO_INTEGRITY_REPAIR_REQUIRED',
            'reason_code': reason_code,
            'defect_code': reason_code,
            'defect_codes': defect_codes,
            'message': (
                'Generated audio failed output-side integrity verification; '
                'the preserved file is diagnostic evidence, not fulfilled audio.'
            ),
            'stage': 'tts_audio_integrity_gate',
            'retryable': True,
            'repair_action': RECOVERY_ACTION_RETRY_SAME_BRANCH,
            'materialization_blocked': True,
            'blocked_scope': 'current_tts_branch',
            'repair_work_available': True,
            'repair_work_policy': (
                'bounded_same_response_tts_integrity_retry'
            ),
            'needs_external_input': False,
            'audio_integrity_evidence': evidence,
            'tts_generation_budget': dict(generation_budget) if generation_budget else None,
            'tts_sampling_profile': dict(sampling_profile) if sampling_profile else None,
            'diagnostic_artifact': (
                {
                    'type': 'audio',
                    'path': saved_audio_path,
                    'status': 'failed_integrity',
                }
                if saved_audio_path
                else None
            ),
        }

    @staticmethod
    def _normalize_tts_stt_semantic_text(content: Any) -> tuple[str, list[str]]:
        text = unicodedata.normalize('NFKC', str(content or '')).casefold()
        normalized_chars = [
            char
            if char.isalnum() or char.isspace()
            else ' '
            for char in text
        ]
        normalized = re.sub(r'\s+', ' ', ''.join(normalized_chars)).strip()
        tokens = re.findall(r'[^\W_]+', normalized, flags=re.UNICODE)
        return ' '.join(tokens), tokens

    @classmethod
    def _tts_stt_similarity_metrics(
        cls,
        source_text: Any,
        transcript_text: Any,
    ) -> dict[str, Any]:
        normalized_source, source_tokens = cls._normalize_tts_stt_semantic_text(
            source_text
        )
        normalized_transcript, transcript_tokens = cls._normalize_tts_stt_semantic_text(
            transcript_text
        )
        source_counter = Counter(source_tokens)
        transcript_counter = Counter(transcript_tokens)
        overlap_count = sum((source_counter & transcript_counter).values())
        source_negation_count = sum(
            count
            for token, count in source_counter.items()
            if token in _TTS_STT_NEGATION_TOKENS
        )
        transcript_negation_count = sum(
            count
            for token, count in transcript_counter.items()
            if token in _TTS_STT_NEGATION_TOKENS
        )
        negation_consistent = source_negation_count == transcript_negation_count
        token_recall = overlap_count / len(source_tokens) if source_tokens else 0.0
        token_precision = (
            overlap_count / len(transcript_tokens) if transcript_tokens else 0.0
        )
        token_f1 = (
            (2 * token_precision * token_recall) / (token_precision + token_recall)
            if token_precision + token_recall
            else 0.0
        )
        sequence_ratio = (
            SequenceMatcher(
                None,
                normalized_source,
                normalized_transcript,
                autojunk=False,
            ).ratio()
            if normalized_source and normalized_transcript
            else 0.0
        )
        exact_match = bool(
            normalized_source
            and normalized_source == normalized_transcript
        )
        if exact_match:
            semantic_match = True
        elif len(source_tokens) < _TTS_STT_MIN_SOURCE_TOKENS_FOR_FULL_POLICY:
            semantic_match = bool(
                token_f1 >= _TTS_STT_SHORT_MIN_TOKEN_F1
                and sequence_ratio >= _TTS_STT_SHORT_MIN_SEQUENCE_RATIO
                and negation_consistent
            )
        else:
            semantic_match = bool(
                token_recall >= _TTS_STT_MIN_TOKEN_RECALL
                and token_precision >= _TTS_STT_MIN_TOKEN_PRECISION
                and sequence_ratio >= _TTS_STT_MIN_SEQUENCE_RATIO
                and negation_consistent
            )
        return {
            'normalized_source': normalized_source,
            'normalized_transcript': normalized_transcript,
            'source_token_count': len(source_tokens),
            'transcript_token_count': len(transcript_tokens),
            'overlap_token_count': overlap_count,
            'token_recall': round(token_recall, 6),
            'token_precision': round(token_precision, 6),
            'token_f1': round(token_f1, 6),
            'sequence_ratio': round(sequence_ratio, 6),
            'source_negation_count': source_negation_count,
            'transcript_negation_count': transcript_negation_count,
            'negation_consistent': negation_consistent,
            'exact_match': exact_match,
            'semantic_match': semantic_match,
        }

    def tts_stt_semantic_evidence_for_branch_result(
        self,
        branch: Mapping[str, Any],
        infer_result: Mapping[str, Any],
        *,
        current_payload: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        if self.normalize_capability(branch.get('capability')) != 'speech_to_text':
            return {
                'kind': 'fruth.tts_stt_semantic_evidence',
                'version': 1,
                'status': 'not_applicable',
                'policy_id': _TTS_STT_SEMANTIC_POLICY_ID,
                'reason_code': 'CONSUMER_IS_NOT_SPEECH_TO_TEXT',
            }
        dependency_ids = branch_result_contracts.late_fill_branch_dependency_ids(
            branch,
            current_payload=current_payload,
        )
        if not dependency_ids or not isinstance(current_payload, Mapping):
            return {
                'kind': 'fruth.tts_stt_semantic_evidence',
                'version': 1,
                'status': 'not_applicable',
                'policy_id': _TTS_STT_SEMANTIC_POLICY_ID,
                'reason_code': 'NO_RUNTIME_TTS_DEPENDENCY_CONTEXT',
            }
        late_fill = (
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
        declared_records: list[Mapping[str, Any]] = []
        for key in ('phases', 'downstream_branches'):
            declared_records.extend(
                item
                for item in (
                    phase_graph.get(key)
                    if isinstance(phase_graph.get(key), list)
                    else []
                )
                if isinstance(item, Mapping)
            )
        for key in ('completed_branches', 'pending_branches', 'failed_branches'):
            declared_records.extend(
                item
                for item in (
                    late_fill.get(key) if isinstance(late_fill.get(key), list) else []
                )
                if isinstance(item, Mapping)
            )
        declared_tts_dependency_ids: list[str] = []
        for record in declared_records:
            if (
                self.normalize_capability(record.get('capability'))
                != self.capability_text_to_speech
            ):
                continue
            record_tokens = {
                str(record.get('branch_id') or '').strip(),
                str(record.get('phase_id') or '').strip(),
            }
            record_tokens.discard('')
            for dependency_id in dependency_ids:
                if dependency_id in record_tokens and dependency_id not in declared_tts_dependency_ids:
                    declared_tts_dependency_ids.append(dependency_id)
        producer_results: list[Mapping[str, Any]] = []
        for result in late_fill.get('fill_results') or []:
            if not isinstance(result, Mapping):
                continue
            if self.normalize_capability(result.get('capability')) != self.capability_text_to_speech:
                continue
            result_tokens = {
                str(result.get('branch_id') or '').strip(),
                str(result.get('phase_id') or '').strip(),
            }
            if not result_tokens.intersection(dependency_ids):
                continue
            if not any(dict(result) == dict(existing) for existing in producer_results):
                producer_results.append(result)
        consumer_branch_id = str(
            branch.get('branch_id') or branch.get('phase_id') or ''
        ).strip()
        consumer_phase_id = str(branch.get('phase_id') or '').strip()
        base_evidence = {
            'kind': 'fruth.tts_stt_semantic_evidence',
            'version': 1,
            'policy_id': _TTS_STT_SEMANTIC_POLICY_ID,
            'authority': 'runtime_deterministic_verification',
            'consumer_branch_id': consumer_branch_id or None,
            'consumer_phase_id': consumer_phase_id or None,
        }
        if not producer_results:
            if declared_tts_dependency_ids:
                return {
                    **base_evidence,
                    'status': 'unavailable',
                    'reason_code': 'TTS_PRODUCER_RESULT_UNAVAILABLE',
                    'semantic_match': False,
                    'failed_dependency_ids': declared_tts_dependency_ids,
                }
            return {
                **base_evidence,
                'status': 'not_applicable',
                'reason_code': 'NO_DIRECT_TTS_PRODUCER_RESULT',
            }
        if len(producer_results) != 1:
            return {
                **base_evidence,
                'status': 'unavailable',
                'reason_code': 'TTS_PRODUCER_EVIDENCE_AMBIGUOUS',
                'producer_result_count': len(producer_results),
                'semantic_match': False,
            }
        producer = producer_results[0]
        source = (
            producer.get('tts_semantic_source')
            if isinstance(producer.get('tts_semantic_source'), Mapping)
            else {}
        )
        producer_branch_id = str(
            producer.get('branch_id') or source.get('branch_id') or ''
        ).strip()
        producer_phase_id = str(
            producer.get('phase_id') or source.get('phase_id') or ''
        ).strip()
        evidence = {
            **base_evidence,
            'producer_branch_id': producer_branch_id or None,
            'producer_phase_id': producer_phase_id or None,
        }
        if not source:
            return {
                **evidence,
                'status': 'unavailable',
                'reason_code': 'TTS_SOURCE_EVIDENCE_UNAVAILABLE',
                'semantic_match': False,
            }
        if (
            str(source.get('kind') or '').strip() != 'fruth.tts_semantic_source'
            or source.get('version') != 1
            or str(source.get('policy_id') or '').strip()
            != _TTS_STT_SEMANTIC_POLICY_ID
            or str(source.get('authority') or '').strip()
            != 'runtime_exact_backend_prompt'
            or str(source.get('source_authority') or '').strip()
            != 'final_infer_prompt'
        ):
            return {
                **evidence,
                'status': 'unavailable',
                'reason_code': 'TTS_SOURCE_EVIDENCE_CONTRACT_INVALID',
                'semantic_match': False,
            }
        source_branch_id = str(source.get('branch_id') or '').strip()
        source_phase_id = str(source.get('phase_id') or '').strip()
        if (
            (source_branch_id and producer_branch_id and source_branch_id != producer_branch_id)
            or (source_phase_id and producer_phase_id and source_phase_id != producer_phase_id)
        ):
            return {
                **evidence,
                'status': 'unavailable',
                'reason_code': 'TTS_SOURCE_EVIDENCE_BINDING_MISMATCH',
                'semantic_match': False,
            }
        raw_source_text = source.get('tts_source_text')
        source_text = str(raw_source_text) if raw_source_text is not None else ''
        if not source_text.strip():
            return {
                **evidence,
                'status': 'unavailable',
                'reason_code': 'TTS_SOURCE_EVIDENCE_UNAVAILABLE',
                'semantic_match': False,
            }
        source_sha256 = hashlib.sha256(source_text.encode('utf-8')).hexdigest()
        declared_source_sha256 = str(
            source.get('tts_source_text_sha256') or ''
        ).strip().lower()
        if not re.fullmatch(r'[0-9a-f]{64}', declared_source_sha256):
            return {
                **evidence,
                'status': 'unavailable',
                'reason_code': 'TTS_SOURCE_EVIDENCE_DIGEST_UNAVAILABLE',
                'source_sha256': source_sha256,
                'semantic_match': False,
            }
        if declared_source_sha256 != source_sha256:
            return {
                **evidence,
                'status': 'unavailable',
                'reason_code': 'TTS_SOURCE_EVIDENCE_DIGEST_MISMATCH',
                'source_sha256': source_sha256,
                'declared_source_sha256': declared_source_sha256,
                'semantic_match': False,
            }
        transcript_text = branch_result_contracts.late_fill_text_from_result_payload(infer_result)
        if not transcript_text:
            return {
                **evidence,
                'status': 'unavailable',
                'reason_code': 'TTS_TRANSCRIPT_EVIDENCE_UNAVAILABLE',
                'source_sha256': source_sha256,
                'semantic_match': False,
            }
        transcript_sha256 = hashlib.sha256(
            transcript_text.encode('utf-8')
        ).hexdigest()
        metrics = self._tts_stt_similarity_metrics(source_text, transcript_text)
        result_payload = (
            infer_result.get('result')
            if isinstance(infer_result.get('result'), Mapping)
            else {}
        )
        expected_lang_code = str(
            source.get('lang_code')
            or producer.get('lang_code')
            or ''
        ).strip().lower()
        detected_lang_code = str(
            infer_result.get('language')
            or result_payload.get('language')
            or ''
        ).strip().lower()
        return {
            key: value
            for key, value in {
                **evidence,
                'status': 'matched' if metrics['semantic_match'] else 'mismatched',
                'reason_code': (
                    'TTS_STT_SEMANTIC_MATCH'
                    if metrics['semantic_match']
                    else 'TTS_STT_SEMANTIC_MISMATCH'
                ),
                'semantic_match': bool(metrics['semantic_match']),
                'source_sha256': source_sha256,
                'transcript_sha256': transcript_sha256,
                'transcript_text': transcript_text,
                'expected_lang_code': expected_lang_code or None,
                'detected_lang_code': detected_lang_code or None,
                'metrics': metrics,
                'thresholds': {
                    'min_source_tokens_for_full_policy': (
                        _TTS_STT_MIN_SOURCE_TOKENS_FOR_FULL_POLICY
                    ),
                    'min_token_recall': _TTS_STT_MIN_TOKEN_RECALL,
                    'min_token_precision': _TTS_STT_MIN_TOKEN_PRECISION,
                    'min_sequence_ratio': _TTS_STT_MIN_SEQUENCE_RATIO,
                    'short_min_token_f1': _TTS_STT_SHORT_MIN_TOKEN_F1,
                    'short_min_sequence_ratio': _TTS_STT_SHORT_MIN_SEQUENCE_RATIO,
                },
            }.items()
            if value not in (None, '', [], {})
        }

