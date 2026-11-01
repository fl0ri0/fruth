"""Branch and whole-turn semantic review evidence and verdict accounting.

Consumes exact accepted records, canonical artifact projections, a scoped saved-
artifact reader and capability observations. No provider invocation, promotion,
worker claim, persistence or HTTP context is available to this review owner.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from fruth_services import intent_coverage
from fruth_services.artifact_contracts import saved_file_dependency_contract
from fruth_services.events import observe_call, judgment_summary
import copy
import hashlib
import json
import re
from typing import Any, Mapping, Optional, Sequence
from helpers.model_capabilities import CAPABILITY_CHAT
from fruth_server.recovery_contract import (
    RECOVERY_ACTION_MANUAL_REVIEW,
    RECOVERY_ACTION_REBIND_DEPENDENCY_EVIDENCE,
    RECOVERY_ACTION_REBUILD_FROM_PROMOTED_OBLIGATIONS,
    RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT,
    RECOVERY_ACTION_REPAIR_DEPENDENCY_CHAIN,
    RECOVERY_ACTION_SEMANTIC_REVIEW,
    normalize_recovery_suggested_action,
)
from fruth_services.semantic_review_verdict import (
    CONTENT_REVIEW_REFERENCE_POLICY,
    semantic_review_evidence_reference_catalog,
    semantic_review_verdict_freeze_acceptance,
    semantic_review_verdict_from_text,
)


_GLOBAL_SEMANTIC_TEXT_CARRIER_LIMIT = 16_000


_GLOBAL_SEMANTIC_ARTIFACT_EXCERPT_LIMIT = 16_000


_GLOBAL_SEMANTIC_ARTIFACT_EXCERPT_TOTAL_LIMIT = 64_000


_GLOBAL_SEMANTIC_LATE_FILL_BRANCH_LIMIT = 128


_GLOBAL_SEMANTIC_REVIEW_EVIDENCE_POLICY = (
    'global_semantic_review_instruction_sha256_v1'
)


_BRANCH_SEMANTIC_REVIEW_EVIDENCE_POLICY = (
    'branch_semantic_review_instruction_sha256_v1'
)


_SEMANTIC_REVIEW_VISIBILITY = 'internal'


_SEMANTIC_REVIEW_SURFACE_ROLE = 'closure_evidence'


_DETERMINISTIC_REVIEW_CRITERIA = {
    'consumes_declared_input_refs',
    'does_not_restart_root_request',
    'output_contract_matches_capability',
    'preparation_text_is_bounded_to_downstream_inputs',
    'runtime_artifact_exists_when_fulfilled',
    'runtime_evidence_text_exists_when_fulfilled',
    'runtime_status_reaches_fulfilled_blocked_failed_waived_or_pending',
    'runtime_status_reaches_fulfilled_blocked_failed_waived_superseded_or_pending',
    'runtime_text_artifact_exists_when_fulfilled',
    'runtime_text_artifact_revision_preservation_passed_when_required',
    'runtime_text_artifact_revision_write_proven_when_fulfilled',
    'runtime_text_exists_when_fulfilled',
    'uses_dependency_evidence',
}

@dataclass(frozen=True)
class SemanticClosureReview:
    artifact_file_identity: Callable[[Any], dict[str, Any]]
    text_artifact_excerpt: Callable[..., dict[str, Any]]
    build_canonical_response_artifacts: Callable[[dict[str, Any]], list[dict[str, Any]]]
    runtime_capability_availability: Callable[..., dict[str, Any]]

    @staticmethod
    def _json_for_semantic_review_prompt(value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=str)
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _semantic_manifest_sha256(records: Sequence[Mapping[str, Any]]) -> str:
        canonical_records = sorted(
            (
                {
                    str(key): value
                    for key, value in record.items()
                    if value not in (None, '', [], {})
                }
                for record in records
                if isinstance(record, Mapping)
            ),
            key=lambda record: json.dumps(
                record,
                ensure_ascii=False,
                sort_keys=True,
                separators=(',', ':'),
                default=str,
            ),
        )
        encoded = json.dumps(
            canonical_records,
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
            default=str,
        ).encode('utf-8')
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _semantic_review_evidence_sha256_from_record(record: Mapping[str, Any]) -> str:
        if not isinstance(record, Mapping):
            return ''
        binding = (
            record.get('semantic_review_evidence_binding')
            if isinstance(record.get('semantic_review_evidence_binding'), Mapping)
            else {}
        )
        execution_contract = (
            record.get('execution_contract')
            if isinstance(record.get('execution_contract'), Mapping)
            else {}
        )
        contract_binding = (
            execution_contract.get('semantic_review_evidence_binding')
            if isinstance(
                execution_contract.get('semantic_review_evidence_binding'),
                Mapping,
            )
            else {}
        )
        for value in (
            binding.get('sha256'),
            record.get('semantic_review_evidence_sha256'),
            contract_binding.get('sha256'),
            execution_contract.get('semantic_review_evidence_sha256'),
        ):
            digest = str(value or '').strip().lower()
            if re.fullmatch(r'[0-9a-f]{64}', digest):
                return digest
        return ''

    @staticmethod
    def _late_fill_branch_record(
        artifact_payload: Optional[dict[str, Any]],
        branch_id: str,
    ) -> tuple[dict[str, Any], str]:
        if not isinstance(artifact_payload, Mapping) or not branch_id:
            return {}, ''
        late_fill = artifact_payload.get('late_fill') if isinstance(artifact_payload.get('late_fill'), Mapping) else {}
        for key, status in (
            ('completed_branches', 'fulfilled'),
            ('failed_branches', 'blocked'),
            ('pending_branches', 'pending'),
        ):
            for item in late_fill.get(key) or []:
                if not isinstance(item, Mapping):
                    continue
                if str(item.get('branch_id') or item.get('phase_id') or '').strip() == branch_id:
                    return dict(item), status
        return {}, ''

    @classmethod
    def _semantic_review_verdict_from_late_fill(
        cls,
        artifact_payload: Optional[dict[str, Any]],
        branch_id: str,
        *,
        review_id: str = 'global-semantic-closure-review',
        expected_evidence_sha256: str = '',
        require_content_review_result: bool = False,
        evidence_reference_policy: str = '',
    ) -> dict[str, Any]:
        record, status = cls._late_fill_branch_record(artifact_payload, branch_id)
        if not record or status != 'fulfilled':
            return {}
        contract = record.get('execution_contract') if isinstance(record.get('execution_contract'), Mapping) else {}
        binding = record.get('semantic_review_evidence_binding') or contract.get('semantic_review_evidence_binding') or {}
        if require_content_review_result:
            if not isinstance(binding, Mapping) or binding.get('content_requirement_policy') != 'named_saved_text_v1':
                return {}
            if evidence_reference_policy and binding.get('evidence_reference_policy') != evidence_reference_policy:
                return {}
            # Branch summaries prove settlement; accepted fill results carry
            # the actual dispatched verdict. Neither substitutes for the other.
            results = [item for item in (artifact_payload.get('late_fill') or {}).get('fill_results', [])
                       if isinstance(item, Mapping) and item.get('branch_id') == branch_id
                       and item.get('phase_id') == record.get('phase_id')]
            if (len(results) != 1 or results[0].get('semantic_review_evidence_binding') != binding):
                return {}
            record = {**record, **results[0]}
        expected_digest = str(expected_evidence_sha256 or '').strip().lower()
        if expected_digest:
            completed_digest = cls._semantic_review_evidence_sha256_from_record(record)
            if completed_digest != expected_digest:
                return {}
        # Governed reviews inspect the actual returned declarations, before any
        # normalization can drop malformed references or duplicate entries.
        raw_verdict = None if evidence_reference_policy else record.get('semantic_review_verdict')
        if isinstance(raw_verdict, Mapping):
            if (
                str(raw_verdict.get('kind') or '').strip()
                == 'fruth.semantic_review_verdict'
                and raw_verdict.get('parse_status')
                and isinstance(raw_verdict.get('declared_schema'), Mapping)
            ):
                # This is an already-normalized runtime envelope. Preserve its
                # original declared-schema provenance; re-normalizing it would
                # make runtime-added defaults look model-declared.
                verdict = dict(raw_verdict)
                verdict['review_id'] = review_id
                verdict['branch_id'] = branch_id
                verdict['phase_id'] = str(record.get('phase_id') or '').strip()
            else:
                verdict = semantic_review_verdict_from_text(
                    raw_verdict,
                    review_id=review_id,
                    branch_id=branch_id,
                    phase_id=str(record.get('phase_id') or '').strip(),
                )
        else:
            result_text = ''
            for key in ('result_text', 'output_text', 'text', 'transcript', 'content'):
                value = record.get(key)
                if isinstance(value, str) and value.strip():
                    result_text = value
                    break
            verdict = semantic_review_verdict_from_text(
                result_text,
                review_id=review_id,
                branch_id=branch_id,
                phase_id=str(record.get('phase_id') or '').strip(),
            )
        verdict['completed_branch_status'] = status
        if expected_digest:
            verdict['reviewed_evidence_sha256'] = expected_digest
        return intent_coverage._compact_mapping(verdict)

    @classmethod
    def _global_semantic_review_evidence_summary(
        cls,
        review: Any,
    ) -> dict[str, Any]:
        """Project recursive decision reviews into bounded reviewer evidence."""
        if not isinstance(review, Mapping):
            return {}

        def _bounded_text(value: Any, limit: int = 800) -> str:
            text = str(value or '').strip()
            if len(text) <= limit:
                return text
            return f'{text[:limit]}…'

        summary: dict[str, Any] = {}
        for key in (
            'kind',
            'status',
            'reason',
            'policy',
            'review_id',
            'frame_count',
            'proposal_count',
            'contract_count',
            'required_count',
            'pending_count',
            'failed_count',
            'fulfilled_count',
            'semantic_review_required_count',
            'decision_count',
        ):
            value = review.get(key)
            if isinstance(value, str):
                value = _bounded_text(value)
            if isinstance(value, (str, int, float, bool)) and value not in ('', None):
                summary[key] = value

        record_limit = 32
        for list_key in ('proposals', 'contracts'):
            raw_records = review.get(list_key) if isinstance(review.get(list_key), list) else []
            records: list[dict[str, Any]] = []
            for raw_record in raw_records[:record_limit]:
                if not isinstance(raw_record, Mapping):
                    continue
                record: dict[str, Any] = {}
                for key in (
                    'kind',
                    'id',
                    'proposal_id',
                    'contract_id',
                    'review_id',
                    'status',
                    'branch_id',
                    'phase_id',
                    'obligation_id',
                    'task_id',
                    'decision_action',
                    'recommended_transition',
                    'reason',
                    'confidence',
                    'semantic_review_lens',
                    'semantic_review_lens_id',
                ):
                    value = raw_record.get(key)
                    if isinstance(value, str):
                        value = _bounded_text(value)
                    if isinstance(value, (str, int, float, bool)) and value not in ('', None):
                        record[key] = value
                for key in (
                    'evidence_refs',
                    'review_criteria',
                    'semantic_review_criteria',
                    'allowed_transitions',
                ):
                    values = [
                        _bounded_text(item, 320)
                        for item in cls._string_list(raw_record.get(key))[:32]
                    ]
                    if values:
                        record[key] = values
                if record:
                    records.append(record)
            if records:
                summary[list_key] = records
            summary[f'{list_key[:-1]}_count'] = len(raw_records)
            if len(raw_records) > record_limit:
                summary[f'{list_key}_truncated'] = True
        return intent_coverage._compact_mapping(summary)

    @staticmethod
    def _bounded_global_semantic_text(
        value: Any,
        *,
        limit: int = _GLOBAL_SEMANTIC_TEXT_CARRIER_LIMIT,
    ) -> str:
        text = str(value or '').strip()
        if len(text) <= limit:
            return text
        marker = '\n[… middle omitted from bounded semantic-review evidence …]\n'
        available = max(0, limit - len(marker))
        head_size = (available * 3) // 4
        tail_size = available - head_size
        return f'{text[:head_size]}{marker}{text[-tail_size:] if tail_size else ""}'

    @classmethod
    def _bounded_semantic_value(cls, value: Any, *, limit: int) -> Any:
        if isinstance(value, str):
            return cls._bounded_global_semantic_text(value, limit=limit)
        if isinstance(value, (int, float, bool)) or value is None:
            return value
        return cls._bounded_global_semantic_text(
            cls._json_for_semantic_review_prompt(value),
            limit=limit,
        )

    @classmethod
    def _global_semantic_late_fill_summary(
        cls,
        late_fill: Any,
    ) -> dict[str, Any]:
        if not isinstance(late_fill, Mapping):
            return {}
        summary: dict[str, Any] = {}

        def _is_global_review_record(record: Mapping[str, Any]) -> bool:
            execution_contract = (
                record.get('execution_contract')
                if isinstance(record.get('execution_contract'), Mapping)
                else {}
            )
            stage_direction = str(
                record.get('stage_direction')
                or execution_contract.get('stage_direction')
                or ''
            ).strip()
            identity = ' '.join(
                str(record.get(field) or '').strip().lower()
                for field in ('branch_id', 'phase_id')
            )
            return (
                stage_direction == 'run_global_semantic_closure_review'
                or 'global-semantic-closure-review' in identity
            )

        for key in ('completed_branches', 'failed_branches', 'pending_branches'):
            source_records = late_fill.get(key) if isinstance(late_fill.get(key), list) else []
            raw_records = [
                item
                for item in source_records
                if not isinstance(item, Mapping) or not _is_global_review_record(item)
            ]
            records: list[dict[str, Any]] = []
            for raw_record in raw_records[:_GLOBAL_SEMANTIC_LATE_FILL_BRANCH_LIMIT]:
                if isinstance(raw_record, Mapping):
                    error = raw_record.get('error') if isinstance(raw_record.get('error'), Mapping) else {}
                    record = {
                        field: raw_record.get(field)
                        for field in (
                            'branch_id',
                            'phase_id',
                            'obligation_id',
                            'capability',
                            'output_type',
                            'status',
                            'saved_text_path',
                            'saved_audio_path',
                            'saved_image_path',
                            'artifact_ref',
                            'content_payload_source',
                            'code',
                            'stage',
                            'reason',
                            'repair_action',
                            'retryable',
                        )
                        if raw_record.get(field) not in (None, '', [], {})
                    }
                    for field in ('code', 'stage', 'message'):
                        value = error.get(field)
                        if value not in (None, '', [], {}) and field not in record:
                            record[f'error_{field}'] = value
                    depends_on = [
                        cls._bounded_global_semantic_text(item, limit=160)
                        for item in cls._string_list(raw_record.get('depends_on'))[:32]
                    ]
                    if depends_on:
                        record['depends_on'] = depends_on
                    record = {
                        field: cls._bounded_global_semantic_text(value, limit=600)
                        if isinstance(value, str)
                        else value
                        for field, value in record.items()
                    }
                else:
                    record = {
                        'branch_id': cls._bounded_global_semantic_text(raw_record, limit=600),
                    }
                records.append(intent_coverage._compact_mapping(record))
            if records:
                summary[key] = records
            branch_count_key = {
                'completed_branches': 'completed_branch_count',
                'failed_branches': 'failed_branch_count',
                'pending_branches': 'pending_branch_count',
            }[key]
            summary[branch_count_key] = len(raw_records)
            if len(raw_records) > _GLOBAL_SEMANTIC_LATE_FILL_BRANCH_LIMIT:
                summary[f'{key}_truncated'] = True
        if int(summary.get('failed_branch_count') or 0) > 0:
            summary['status'] = 'failed'
        elif int(summary.get('pending_branch_count') or 0) > 0:
            summary['status'] = 'pending'
        elif int(summary.get('completed_branch_count') or 0) > 0:
            summary['status'] = 'completed'
        for capability_key, branch_key in (
            ('completed_capabilities', 'completed_branches'),
            ('failed_capabilities', 'failed_branches'),
        ):
            capabilities = list(
                dict.fromkeys(
                    str(record.get('capability') or '').strip()
                    for record in summary.get(branch_key) or []
                    if isinstance(record, Mapping)
                    and str(record.get('capability') or '').strip()
                )
            )
            if capabilities:
                summary[capability_key] = capabilities[:32]
            if len(capabilities) > 32:
                summary[f'{capability_key}_truncated'] = True
        return intent_coverage._compact_mapping(summary)

    def _global_semantic_evidence_payload(
        self,
        *,
        artifact_payload: Optional[dict[str, Any]],
        checks: Sequence[Mapping[str, Any]],
        intent_graph_adequacy: Mapping[str, Any],
        decision_contract: Mapping[str, Any],
    ) -> dict[str, Any]:
        payload = artifact_payload if isinstance(artifact_payload, dict) else {}
        late_fill = payload.get('late_fill') if isinstance(payload.get('late_fill'), Mapping) else {}
        artifacts = self.build_canonical_response_artifacts(payload) if payload else []
        artifact_records = [
            item
            for item in (artifacts or [])
            if isinstance(item, Mapping)
        ]
        artifact_refs: list[dict[str, Any]] = []
        artifact_manifest_records: list[dict[str, Any]] = []
        artifact_limit = 128
        artifact_excerpt_bytes_remaining = _GLOBAL_SEMANTIC_ARTIFACT_EXCERPT_TOTAL_LIMIT
        for index, item in enumerate(artifact_records):
            artifact_path = item.get('path') or item.get('source_path')
            artifact_ref = {
                'type': item.get('type'),
                'path': artifact_path,
                'name': item.get('name'),
                'ref': item.get('ref') or item.get('artifact_ref'),
                'branch_id': item.get('branch_id'),
                'phase_id': item.get('phase_id'),
                'status': item.get('status'),
                'sha256': item.get('sha256') or item.get('content_sha256'),
                'size_bytes': item.get('size_bytes'),
            }
            artifact_ref.update(
                self.artifact_file_identity(artifact_path)
            )
            artifact_manifest_records.append(intent_coverage._compact_mapping(artifact_ref))
            if index >= artifact_limit:
                continue
            display_ref = dict(artifact_ref)
            if str(item.get('type') or '').strip().lower() == 'text':
                excerpt_budget = min(
                    _GLOBAL_SEMANTIC_ARTIFACT_EXCERPT_LIMIT,
                    artifact_excerpt_bytes_remaining,
                )
                excerpt = self.text_artifact_excerpt(
                    artifact_path,
                    byte_limit=excerpt_budget,
                )
                if excerpt:
                    display_ref.update(excerpt)
                    excerpt_bytes_used = len(
                        str(excerpt.get('content_excerpt') or '').encode(
                            'utf-8',
                            errors='replace',
                        )
                    )
                    artifact_excerpt_bytes_remaining = max(
                        0,
                        artifact_excerpt_bytes_remaining - excerpt_bytes_used,
                    )
            artifact_refs.append(
                intent_coverage._compact_mapping(display_ref)
            )
        artifact_dependency_ids = list(
            dict.fromkeys(
                str(item.get('phase_id') or item.get('branch_id') or '').strip()
                for item in artifact_manifest_records
                if str(item.get('phase_id') or item.get('branch_id') or '').strip()
            )
        )
        artifact_manifest_sha256 = self._semantic_manifest_sha256(
            artifact_manifest_records
        )
        closure_check_limit = 128
        closure_check_records: list[dict[str, Any]] = []
        for check in checks:
            if not isinstance(check, Mapping):
                continue
            check_kind = str(check.get('check_kind') or '').strip()
            branch_id = str(check.get('branch_id') or check.get('phase_id') or '').strip()
            stage_direction = str(check.get('stage_direction') or '').strip()
            if (
                check_kind == 'global_semantic_closure'
                or stage_direction == 'run_global_semantic_closure_review'
                or 'global-semantic-closure-review' in branch_id.lower()
            ):
                continue
            closure_check_records.append(
                intent_coverage._compact_mapping(
                    {
                        key: check.get(key)
                        for key in (
                            'check_kind',
                            'status',
                            'evidence',
                            'reason',
                            'obligation_id',
                            'phase_id',
                            'branch_id',
                            'capability',
                            'output_type',
                            'role',
                            'depends_on',
                            'review_criteria',
                            'review_criteria_status',
                            'semantic_review_required',
                            'semantic_review_criteria',
                            'repair_action',
                            'saved_artifact_state',
                        )
                    }
                )
            )
        closure_check_manifest_sha256 = self._semantic_manifest_sha256(
            closure_check_records
        )
        return intent_coverage._compact_mapping(
            {
                'artifact_refs': artifact_refs,
                'artifact_ref_count': len(artifact_records),
                'artifact_refs_truncated': len(artifact_records) > artifact_limit,
                'artifact_manifest_sha256': artifact_manifest_sha256,
                'artifact_manifest_policy': 'canonical_artifact_current_bytes_sha256_v1',
                'artifact_dependency_ids': artifact_dependency_ids,
                'late_fill': self._global_semantic_late_fill_summary(late_fill),
                'closure_checks': closure_check_records[:closure_check_limit],
                'closure_check_count': len(closure_check_records),
                'closure_checks_truncated': len(closure_check_records) > closure_check_limit,
                'closure_check_manifest_sha256': closure_check_manifest_sha256,
                'closure_check_manifest_policy': 'closure_check_projection_sha256_v1',
                'intent_graph_adequacy': self._global_semantic_intent_graph_adequacy_summary(
                    intent_graph_adequacy
                ),
                'semantic_decision_review': self._global_semantic_review_evidence_summary(
                    decision_contract.get('semantic_decision_review')
                    if isinstance(decision_contract, Mapping)
                    else None
                ),
                'controlled_attention_review': self._global_semantic_review_evidence_summary(
                    decision_contract.get('controlled_attention_review')
                    if isinstance(decision_contract, Mapping)
                    else None
                ),
                'aspiration_review': self._global_semantic_review_evidence_summary(
                    decision_contract.get('aspiration_review')
                    if isinstance(decision_contract, Mapping)
                    else None
                ),
                'commitment_review': self._global_semantic_review_evidence_summary(
                    decision_contract.get('commitment_review')
                    if isinstance(decision_contract, Mapping)
                    else None
                ),
                'semantic_quality_review': self._global_semantic_review_evidence_summary(
                    decision_contract.get('semantic_quality_review')
                    if isinstance(decision_contract, Mapping)
                    else None
                ),
            }
        )

    @classmethod
    def _global_semantic_intent_graph_adequacy_summary(
        cls,
        review: Any,
    ) -> dict[str, Any]:
        if not isinstance(review, Mapping):
            return {}
        summary: dict[str, Any] = {}
        for key in (
            'status',
            'reason',
            'intent_obligation_count',
            'required_intent_obligation_count',
        ):
            value = review.get(key)
            if isinstance(value, str):
                value = cls._bounded_global_semantic_text(value, limit=800)
            if value not in (None, '', [], {}):
                summary[key] = value
        for key in (
            'expected_output_counts',
            'graph_output_counts',
            'expected_capability_counts',
            'graph_capability_counts',
        ):
            raw_counts = review.get(key) if isinstance(review.get(key), Mapping) else {}
            records = [
                {
                    'key': cls._bounded_global_semantic_text(raw_key, limit=160),
                    'value': cls._bounded_semantic_value(raw_value, limit=600),
                }
                for raw_key, raw_value in raw_counts.items()
            ]
            if records:
                summary[key] = {
                    record['key']: record['value']
                    for record in records[:64]
                }
                summary[f'{key}_count'] = len(records)
                summary[f'{key}_sha256'] = cls._semantic_manifest_sha256(records)
                if len(records) > 64:
                    summary[f'{key}_truncated'] = True
        for key in ('required_intent_capabilities', 'intent_obligation_kinds'):
            values = [
                cls._bounded_global_semantic_text(item, limit=320)
                for item in cls._string_list(review.get(key))[:64]
            ]
            if values:
                summary[key] = values
        raw_checks = review.get('checks') if isinstance(review.get('checks'), list) else []
        check_records: list[dict[str, Any]] = []
        for raw_check in raw_checks:
            if not isinstance(raw_check, Mapping):
                continue
            record = {
                key: raw_check.get(key)
                for key in (
                    'check_kind',
                    'status',
                    'evidence',
                    'reason',
                    'obligation_id',
                    'phase_id',
                    'branch_id',
                    'capability',
                    'output_type',
                    'repair_action',
                )
                if raw_check.get(key) not in (None, '', [], {})
            }
            record = {
                key: cls._bounded_semantic_value(value, limit=600)
                for key, value in record.items()
            }
            check_records.append(intent_coverage._compact_mapping(record))
        if check_records:
            summary['checks'] = check_records[:128]
            summary['check_count'] = len(check_records)
            summary['check_manifest_sha256'] = cls._semantic_manifest_sha256(
                check_records
            )
            summary['check_manifest_policy'] = 'intent_graph_adequacy_check_projection_sha256_v1'
            if len(check_records) > 128:
                summary['checks_truncated'] = True
        return intent_coverage._compact_mapping(summary)

    def _global_semantic_review_instruction(
        self,
        *,
        prompt: str,
        output_text: str,
        evidence_payload: Mapping[str, Any],
    ) -> str:
        bounded_prompt = self._bounded_global_semantic_text(prompt)
        bounded_output_text = self._bounded_global_semantic_text(output_text)
        return (
            'Run a whole-turn semantic closure review for the current Fruth response.\n'
            '\n'
            'Authority boundary:\n'
            '- You are a semantic reviewer, not runtime truth.\n'
            '- Do not claim artifacts exist unless runtime evidence below proves them.\n'
            '- Decide whether local branch outputs fulfill their role in the whole user intent.\n'
            '- Preserve the current intent; do not invent a different request.\n'
            '- If a block exists, propose the right-sized verified transition that resolves the block without under-scoping the work.\n'
            '\n'
            'Return exactly one JSON object and no markdown, no prose outside JSON, no chain-of-thought.\n'
            'Required schema:\n'
            '{\n'
            '  "kind": "fruth.semantic_review_verdict",\n'
            '  "verdict": "passed | failed | uncertain",\n'
            '  "overall_status": "fulfilled | blocked | pending",\n'
            '  "whole_intent_fit": "short evidence-grounded explanation",\n'
            '  "criterion_results": [\n'
            '    {"criterion": "criterion text", "status": "passed | failed | uncertain", '
            '"reason": "short reason", "evidence_refs": ["runtime evidence ref"]}\n'
            '  ],\n'
            '  "evidence_refs": ["runtime evidence ref"],\n'
            '  "defects": ["missing or wrong work, or empty list"],\n'
            '  "confidence": 0.0,\n'
            '  "recommended_transition": "truthful_freeze | semantic_review | repair_dependency_chain | '
            'repair_branch_contract | rebuild_from_promoted_obligations | waive_with_evidence | '
            'supersede_with_replacement_truth | clarify | manual_review",\n'
            '  "authority_boundary": "advisory_review_only_runtime_contracts_closure_decide_truth"\n'
            '}\n'
            'Use verdict "passed" only when runtime evidence proves all relevant semantic criteria and whole-intent fit.\n'
            'Use verdict "failed" when evidence proves missing or wrong work.\n'
            'Use verdict "uncertain" when evidence is insufficient or ambiguous.\n'
            '\n'
            f'Current user intent:\n{bounded_prompt}\n\n'
            f'Current response text:\n{bounded_output_text}\n\n'
            'Runtime evidence:\n'
            f'{self._json_for_semantic_review_prompt(evidence_payload)}'
        )

    @staticmethod
    def _global_semantic_review_generation(content_payload: str) -> dict[str, Any]:
        digest_input = (
            f'{_GLOBAL_SEMANTIC_REVIEW_EVIDENCE_POLICY}\0'
            f'{str(content_payload or "")}'
        ).encode('utf-8')
        digest = hashlib.sha256(digest_input).hexdigest()
        generation_id = f'global-semantic-closure-review-{digest}'
        return {
            'kind': 'fruth.semantic_review_evidence_binding',
            'policy': _GLOBAL_SEMANTIC_REVIEW_EVIDENCE_POLICY,
            'logical_review_id': 'global-semantic-closure-review',
            'generation_id': generation_id,
            'sha256': digest,
            'branch_id': f'branch-{generation_id}',
            'phase_id': f'phase-{generation_id}',
            'obligation_id': f'obligation-{generation_id}',
            'task_id': f'task-{generation_id}',
        }

    @staticmethod
    def _semantic_review_branch_slug(value: Any) -> str:
        token = re.sub(r'[^a-z0-9_]+', '-', str(value or '').strip().lower())
        token = re.sub(r'-+', '-', token).strip('-')
        return token or 'unknown-branch'

    @classmethod
    def _branch_semantic_review_generation(
        cls,
        check: Mapping[str, Any],
        content_payload: str,
    ) -> dict[str, Any]:
        source_branch_id = str(check.get('branch_id') or check.get('phase_id') or check.get('obligation_id') or '').strip()
        source_phase_id = str(check.get('phase_id') or source_branch_id or '').strip()
        slug = cls._semantic_review_branch_slug(source_branch_id or source_phase_id or check.get('obligation_id'))
        logical_review_id = f'branch-semantic-review:{source_branch_id or source_phase_id}'
        digest = hashlib.sha256(
            (
                f'{_BRANCH_SEMANTIC_REVIEW_EVIDENCE_POLICY}\0'
                f'{logical_review_id}\0{str(content_payload or "")}'
            ).encode('utf-8')
        ).hexdigest()
        generation_id = f'branch-semantic-review-{slug}-{digest}'
        return {
            'kind': 'fruth.semantic_review_evidence_binding',
            'policy': _BRANCH_SEMANTIC_REVIEW_EVIDENCE_POLICY,
            'logical_review_id': logical_review_id,
            'generation_id': generation_id,
            'source_branch_id': source_branch_id,
            'source_phase_id': source_phase_id,
            'sha256': digest,
            'branch_id': f'branch-{generation_id}',
            'phase_id': f'phase-{generation_id}',
            'obligation_id': f'obligation-{generation_id}',
            'task_id': f'task-{generation_id}',
        }

    @classmethod
    def _branch_semantic_check_projection(
        cls,
        check: Mapping[str, Any],
    ) -> dict[str, Any]:
        projection = {
            key: check.get(key)
            for key in (
                'check_kind',
                'status',
                'evidence',
                'reason',
                'obligation_id',
                'phase_id',
                'branch_id',
                'capability',
                'output_type',
                'role',
                'review_criteria_status',
                'semantic_review_required',
                'semantic_review_lens',
                'success_definition',
                'content_payload_source',
            )
            if check.get(key) not in (None, '', [], {})
        }
        projection = {
            key: cls._bounded_semantic_value(value, limit=1_200)
            for key, value in projection.items()
        }
        for key in (
            'depends_on',
            'review_criteria',
            'semantic_review_criteria',
            'failure_modes',
            'semantic_lens_evidence_requirements',
            'evidence_requirements',
        ):
            values = [
                cls._bounded_global_semantic_text(item, limit=600)
                for item in cls._string_list(check.get(key))[:64]
            ]
            if values:
                projection[key] = values
        input_refs: list[dict[str, Any]] = []
        for raw_ref in check.get('input_refs') or []:
            if not isinstance(raw_ref, Mapping):
                continue
            ref = {
                key: raw_ref.get(key)
                for key in (
                    'kind',
                    'ref',
                    'phase_id',
                    'branch_id',
                    'obligation_id',
                    'role',
                    'path',
                    'name',
                )
                if raw_ref.get(key) not in (None, '', [], {})
            }
            input_refs.append(
                intent_coverage._compact_mapping(
                    {
                        key: cls._bounded_semantic_value(value, limit=600)
                        for key, value in ref.items()
                    }
                )
            )
            if len(input_refs) >= 64:
                break
        if input_refs:
            projection['input_refs'] = input_refs
        return intent_coverage._compact_mapping(projection)

    @classmethod
    def _check_is_branch_semantic_review_target(cls, check: Mapping[str, Any]) -> bool:
        if not isinstance(check, Mapping):
            return False
        if check.get('semantic_review_required') is not True:
            return False
        if str(check.get('check_kind') or '').strip() in {
            'global_semantic_closure',
            'branch_semantic_review',
            'intent_graph_adequacy',
        }:
            return False
        if str(check.get('status') or '').strip().lower() != 'fulfilled':
            return False
        review_branch_id = str(check.get('branch_semantic_review_branch_id') or '').strip()
        source_branch_id = str(check.get('branch_id') or check.get('phase_id') or '').strip()
        criteria = cls._string_list(check.get('semantic_review_criteria')) or cls._string_list(check.get('review_criteria'))
        if not any(not cls._review_criterion_is_deterministic(item) for item in criteria):
            return False
        return bool(source_branch_id) and review_branch_id != source_branch_id

    @classmethod
    def _branch_semantic_accepted_scope(cls, payload: Mapping[str, Any], check: Mapping[str, Any]) -> dict[str, Any]:
        """Present accepted duties by branch identity, independent of saved filenames.

        Only stable contract fields participate: review admission/completion must
        not itself change this evidence generation by adding reviewer siblings.
        """
        graph = (payload.get('runtime') or {}).get('request_phase_graph') or {}
        records = [b for b in graph.get('downstream_branches') or [] if isinstance(b, Mapping)]
        branch_id = check.get('branch_id') or check.get('phase_id')
        phase_id = check.get('phase_id') or branch_id
        matches = [b for b in records if b.get('branch_id') == branch_id and b.get('phase_id') == phase_id]
        accepted = matches[0] if len(matches) == 1 else check

        def duties(record):
            request = record.get('artifact_request') or {}
            dependency = saved_file_dependency_contract(record)
            logical_request = dependency.get('consumer_request') or request
            return intent_coverage._compact_mapping({
                'branch_id': record.get('branch_id'), 'phase_id': record.get('phase_id'),
                'capability': record.get('capability'), 'output_type': record.get('output_type'),
                'required_output': {key: logical_request[key] for key in ('extension', 'source_name', 'target_path') if logical_request.get(key)},
                'content_requirements': copy.deepcopy(request.get('content_requirements') or record.get('content_requirements') or []),
                'depends_on': list(record.get('depends_on') or []),
            })

        reviewed = duties(accepted)
        reviewed['required_semantic_criteria'] = list(check.get('semantic_review_criteria') or check.get('review_criteria') or [])
        reviewed['applicable_review_criteria'] = list(check.get('review_criteria') or [])
        if not reviewed.get('content_requirements'):
            reviewed['content_requirements'] = copy.deepcopy(check.get('content_requirements') or [])
        siblings = []
        for record in records:
            if (record.get('branch_id') == branch_id or record.get('phase_id') == phase_id
                    or record.get('stage_direction') == 'run_branch_semantic_review'
                    or record.get('visibility') == 'internal' or record.get('surface_role') == 'closure_evidence'):
                continue
            siblings.append(duties(record))
        return {'source': 'accepted_branch_contracts', 'reviewed_branch': reviewed,
                'sibling_duties_context_only': siblings,
                'shared_constraints_policy': 'retain_every_constraint_applicable_to_the_reviewed_branch'}

    def _branch_semantic_evidence_payload(
        self,
        *,
        artifact_payload: Optional[dict[str, Any]],
        check: Mapping[str, Any],
        output_text: str,
    ) -> dict[str, Any]:
        payload = artifact_payload if isinstance(artifact_payload, dict) else {}
        source_branch_id = str(check.get('branch_id') or check.get('phase_id') or '').strip()
        source_phase_id = str(check.get('phase_id') or source_branch_id or '').strip()
        branch_record, branch_status = self._late_fill_branch_record(payload, source_branch_id)
        artifacts = self.build_canonical_response_artifacts(payload) if payload else []
        artifact_refs: list[dict[str, Any]] = []
        artifact_manifest_digest = hashlib.sha256()
        artifact_manifest_count = 0
        artifact_excerpt_bytes_remaining = _GLOBAL_SEMANTIC_ARTIFACT_EXCERPT_LIMIT
        for item in artifacts or []:
            if not isinstance(item, Mapping):
                continue
            item_branch = str(item.get('branch_id') or item.get('phase_id') or '').strip()
            if item_branch not in {source_branch_id, source_phase_id}:
                continue
            artifact_path = item.get('path') or item.get('source_path')
            artifact_ref = {
                'type': item.get('type'),
                'path': artifact_path,
                'name': item.get('name'),
                'ref': item.get('ref') or item.get('artifact_ref'),
                'branch_id': item.get('branch_id'),
                'phase_id': item.get('phase_id'),
                'status': item.get('status'),
                'sha256': item.get('sha256') or item.get('content_sha256'),
                'size_bytes': item.get('size_bytes'),
            }
            artifact_ref.update(
                self.artifact_file_identity(artifact_path)
            )
            artifact_ref = intent_coverage._compact_mapping(artifact_ref)
            encoded_manifest_record = json.dumps(
                artifact_ref,
                ensure_ascii=False,
                sort_keys=True,
                separators=(',', ':'),
                default=str,
            ).encode('utf-8', errors='replace')
            artifact_manifest_digest.update(
                len(encoded_manifest_record).to_bytes(8, byteorder='big')
            )
            artifact_manifest_digest.update(encoded_manifest_record)
            artifact_manifest_count += 1
            if len(artifact_refs) >= 64:
                continue
            display_ref = {
                key: self._bounded_semantic_value(value, limit=1_200)
                for key, value in artifact_ref.items()
            }
            if str(item.get('type') or '').strip().lower() == 'text':
                excerpt = self.text_artifact_excerpt(
                    artifact_path,
                    byte_limit=artifact_excerpt_bytes_remaining,
                )
                if excerpt:
                    display_ref.update(excerpt)
                    artifact_excerpt_bytes_remaining = max(
                        0,
                        artifact_excerpt_bytes_remaining
                        - len(
                            str(excerpt.get('content_excerpt') or '').encode(
                                'utf-8', errors='replace'
                            )
                        ),
                    )
            artifact_refs.append(intent_coverage._compact_mapping(display_ref))
        branch_output_text = ''
        for key in ('result_text', 'output_text', 'content_payload', 'text', 'transcript'):
            value = branch_record.get(key) if isinstance(branch_record, Mapping) else None
            if isinstance(value, str) and value.strip():
                branch_output_text = value.strip()
                break
        if not branch_output_text and str(check.get('evidence') or '').strip() == 'current_phase_output_text':
            branch_output_text = str(output_text or '').strip()
        bounded_branch_output = self._bounded_global_semantic_text(branch_output_text)
        branch_check = self._branch_semantic_check_projection(check)
        branch_record_projection = {
            key: branch_record.get(key)
            for key in (
                'branch_id',
                'phase_id',
                'capability',
                'output_type',
                'status',
                'content_payload_source',
                'saved_text_path',
                'saved_audio_path',
                'saved_image_path',
            )
            if isinstance(branch_record, Mapping) and branch_record.get(key) not in (None, '', [], {})
        }
        content_coverage = {}
        requirements = check.get('content_requirements')
        if requirements:
            # Reuse the existing bounded artifact packet. A hash of bytes the
            # reviewer never saw is binding evidence, not semantic coverage.
            complete = bool(artifact_refs) and artifact_manifest_count == len(artifact_refs)
            complete = complete and all(
                ref.get('content_excerpt_mode') == 'full'
                and not ref.get('content_excerpt_truncated')
                and ref.get('content_excerpt')
                for ref in artifact_refs
            )
            source = {}
            dependency = saved_file_dependency_contract(check)
            if dependency:
                results = [item for item in (payload.get('late_fill') or {}).get('fill_results', [])
                           if isinstance(item, Mapping) and item.get('branch_id') == source_branch_id]
                read = ((results[0].get('saved_file_consumption_evidence') or {}).get('read') or {}) if len(results) == 1 else {}
                source = {key: read.get(key) for key in (
                    'path', 'sha256', 'size_bytes', 'artifact_ref', 'artifact_id',
                    'response_id', 'source_response_id', 'branch_id', 'phase_id',
                    'producer_branch_id', 'consumer_branch_id',
                )}
                source.update(self.text_artifact_excerpt(
                    read.get('path'), byte_limit=artifact_excerpt_bytes_remaining))
                complete = bool(complete and source.get('content_excerpt_mode') == 'full'
                    and source.get('current_content_sha256') == read.get('sha256'))
            requirement_bytes = len(json.dumps(requirements, ensure_ascii=False).encode('utf-8'))
            content_bytes = sum(len(str(ref.get('content_excerpt') or '').encode('utf-8')) for ref in artifact_refs)
            content_bytes += len(str(source.get('content_excerpt') or '').encode('utf-8'))
            complete = bool(complete and requirement_bytes + content_bytes <= _GLOBAL_SEMANTIC_ARTIFACT_EXCERPT_LIMIT)
            content_coverage = {
                'policy': 'named_saved_text_v1',
                'requirements': requirements if complete else None,
                'requirements_sha256': self._semantic_manifest_sha256(requirements),
                'source': source,
                'complete': complete,
                'reason': 'complete_actual_content' if complete else 'content_review_packet_insufficient',
                'byte_limit': _GLOBAL_SEMANTIC_ARTIFACT_EXCERPT_LIMIT,
            }
        return intent_coverage._compact_mapping(
            {
                'accepted_branch_scope': self._branch_semantic_accepted_scope(payload, check),
                'review_scope': 'branch_only',
                'source_branch_id': source_branch_id,
                'source_phase_id': source_phase_id,
                'branch_late_fill_status': branch_status or None,
                'branch_record': branch_record_projection,
                'branch_output_text': bounded_branch_output or None,
                'branch_output_size_chars': len(branch_output_text),
                'branch_output_sha256': (
                    hashlib.sha256(
                        branch_output_text.encode('utf-8', errors='replace')
                    ).hexdigest()
                    if branch_output_text
                    else None
                ),
                'artifact_refs': artifact_refs,
                'artifact_ref_count': artifact_manifest_count,
                'artifact_refs_truncated': artifact_manifest_count > 64,
                'artifact_manifest_sha256': artifact_manifest_digest.hexdigest(),
                'artifact_manifest_policy': 'branch_artifact_ordered_length_prefixed_sha256_v2',
                'branch_check': branch_check,
                'branch_check_sha256': self._semantic_manifest_sha256([branch_check]),
                # Runtime-owned readback, never client assertions. Including it
                # in this generation invalidates a verdict if the source/file
                # evidence changes, even when the answer text stays the same.
                'saved_artifact_state': check.get('saved_artifact_state'),
                'content_coverage': content_coverage,
            }
        )

    def _branch_semantic_review_instruction(
        self,
        *,
        prompt: str,
        check: Mapping[str, Any],
        evidence_payload: Mapping[str, Any],
    ) -> str:
        bounded_prompt = self._bounded_global_semantic_text(prompt)
        bounded_check = self._branch_semantic_check_projection(check)
        accepted_scope = evidence_payload.get('accepted_branch_scope') or {}
        reviewed_duties = accepted_scope.get('reviewed_branch') or bounded_check
        reference_instruction = ''
        if check.get('content_review_reference_policy'):
            reference_instruction = (
                'Evidence reference policy packet_exact_v1:\n'
                '- Copy exact values from evidence_reference_catalog.allowed_refs in this packet only.\n'
                '- These name the supplied branch/phase, saved artifact ref/path/name, bound source identity, '
                'or accepted requirement; no other response, registry entry, guessed alias or identifier is allowed.\n'
                '- Include nonempty evidence_refs on the verdict and every passed required criterion. '
                'Use arrays of exact strings; ref/id/name envelopes are also supported when all fields resolve to the same evidence. '
                'A criterion may also use one exact string.\n'
                '- Ordering and duplicate references are allowed. Any invalid entry rejects the whole review for completion.\n'
                '- Reference validity does not establish that a semantic judgment is correct.\n\n'
            )
        return (
            'Run a branch-local semantic review for the current Fruth response graph.\n'
            '\n'
            'Accepted duties and required criteria for this reviewed branch:\n'
            f'{self._json_for_semantic_review_prompt(reviewed_duties)}\n\n'
            'Evaluate every required semantic criterion for this exact branch. '
            'Keep every shared constraint that applies to it.\n'
            'Sibling duties in accepted_branch_scope.sibling_duties_context_only are attributed context: '
            'their outputs belong to their own branch identities. '
            'A missing sibling output is not a defect of this branch unless its accepted contract requires it.\n'
            '\n'
            'Authority boundary:\n'
            '- You are a semantic reviewer for one branch, not runtime truth.\n'
            '- Review only the branch named in the evidence payload.\n'
            '- Use the current user intent only as bounded context for that branch role.\n'
            '- Do not review the whole turn and do not invent different work.\n'
            '- Do not claim artifacts exist unless branch evidence proves them.\n'
            '- If the branch is blocked, propose the right-sized verified transition that resolves this branch without under-scoping the work.\n'
            '\n'
            'Return exactly one JSON object and no markdown, no prose outside JSON, no chain-of-thought.\n'
            'Required schema:\n'
            '{\n'
            '  "kind": "fruth.semantic_review_verdict",\n'
            '  "verdict": "passed | failed | uncertain",\n'
            '  "overall_status": "fulfilled | blocked | pending",\n'
            '  "whole_intent_fit": "short explanation of whether this branch fulfills its declared role",\n'
            '  "criterion_results": [\n'
            '    {"criterion": "criterion text", "status": "passed | failed | uncertain", '
            '"reason": "short reason", "evidence_refs": ["branch evidence ref"]}\n'
            '  ],\n'
            '  "evidence_refs": ["branch evidence ref"],\n'
            '  "defects": ["missing or wrong branch work, or empty list"],\n'
            '  "confidence": 0.0,\n'
            '  "recommended_transition": "truthful_freeze | semantic_review | repair_dependency_chain | '
            'repair_branch_contract | rebuild_from_promoted_obligations | waive_with_evidence | '
            'supersede_with_replacement_truth | clarify | manual_review",\n'
            '  "authority_boundary": "advisory_branch_review_only_runtime_contracts_closure_decide_truth"\n'
            '}\n'
            'Use verdict "passed" only when branch evidence proves all branch-local criteria.\n'
            'Use verdict "failed" when evidence proves missing or wrong branch work.\n'
            'Use verdict "uncertain" when branch evidence is insufficient or ambiguous.\n'
            'Use the provided semantic_review_lens and success_definition as the review posture for this branch. '
            'They are advisory only, but they define what kind of success should be checked and which failure modes matter.\n'
            '\n'
            f'{reference_instruction}'
            f'Current user intent for context only:\n{bounded_prompt}\n\n'
            'Branch under review:\n'
            f'{self._json_for_semantic_review_prompt(bounded_check)}\n\n'
            'Branch runtime evidence:\n'
            f'{self._json_for_semantic_review_prompt(evidence_payload)}'
        )

    def _branch_semantic_review_contract(
        self,
        *,
        artifact_payload: Optional[dict[str, Any]],
        check: Mapping[str, Any],
        prompt: str,
        output_text: str,
    ) -> tuple[dict[str, Any], str, dict[str, Any]]:
        evidence_payload = self._branch_semantic_evidence_payload(
            artifact_payload=artifact_payload,
            check=check,
            output_text=output_text,
        )
        if check.get('content_review_reference_policy'):
            evidence_payload['evidence_reference_catalog'] = semantic_review_evidence_reference_catalog(evidence_payload)
        content_payload = self._branch_semantic_review_instruction(
            prompt=prompt,
            check=check,
            evidence_payload=evidence_payload,
        )
        evidence_binding = self._branch_semantic_review_generation(
            check,
            content_payload,
        )
        if evidence_payload.get('content_coverage'):
            evidence_binding['content_requirement_policy'] = 'named_saved_text_v1'
            evidence_binding['instruction_sha256'] = hashlib.sha256(content_payload.encode('utf-8')).hexdigest()
            if check.get('content_review_reference_policy'):
                evidence_binding['evidence_reference_policy'] = check['content_review_reference_policy']
        return evidence_payload, content_payload, evidence_binding

    def _apply_branch_semantic_verdict_to_check(
        self,
        check: Mapping[str, Any],
        *,
        artifact_payload: Optional[dict[str, Any]],
        prompt: str,
        output_text: str,
    ) -> dict[str, Any]:
        updated = dict(check)
        if not self._check_is_branch_semantic_review_target(updated):
            return updated
        if (updated.get('content_review_reference_policy')
                and updated['content_review_reference_policy'] != CONTENT_REVIEW_REFERENCE_POLICY):
            updated.update(status='blocked', content_coverage_status='unverified',
                           completion_basis='technical_evidence_only', semantic_review_required=False,
                           repair_action=RECOVERY_ACTION_MANUAL_REVIEW,
                           recovery_action=RECOVERY_ACTION_MANUAL_REVIEW,
                           reason='content_review_reference_policy_invalid')
            return updated
        evidence_payload, _, evidence_binding = self._branch_semantic_review_contract(
            artifact_payload=artifact_payload,
            check=updated,
            prompt=prompt,
            output_text=output_text,
        )
        coverage = evidence_payload.get('content_coverage') or {}
        if coverage and not coverage.get('complete'):
            updated.update(status='blocked', content_coverage_status='unverified',
                           completion_basis='technical_evidence_only',
                           semantic_review_required=False,
                           repair_action=RECOVERY_ACTION_MANUAL_REVIEW,
                           recovery_action=RECOVERY_ACTION_MANUAL_REVIEW,
                           reason='content_review_packet_insufficient')
            return updated
        review_branch_id = str(evidence_binding.get('branch_id') or '').strip()
        review_phase_id = str(evidence_binding.get('phase_id') or '').strip()
        evidence_sha256 = str(evidence_binding.get('sha256') or '').strip().lower()
        logical_review_id = str(evidence_binding.get('logical_review_id') or '').strip()
        verdict = self._semantic_review_verdict_from_late_fill(
            artifact_payload,
            review_branch_id,
            review_id=logical_review_id,
            expected_evidence_sha256=evidence_sha256,
            require_content_review_result=bool(updated.get('content_requirements')),
            evidence_reference_policy=updated.get('content_review_reference_policy', ''),
        )
        previous_evidence_binding = (
            dict(updated.get('branch_semantic_review_evidence_binding'))
            if isinstance(
                updated.get('branch_semantic_review_evidence_binding'),
                Mapping,
            )
            else {}
        )
        updated['branch_semantic_review_branch_id'] = review_branch_id
        updated['branch_semantic_review_phase_id'] = review_phase_id
        updated['branch_semantic_review_source_branch_id'] = str(updated.get('branch_id') or '').strip() or None
        updated['branch_semantic_review_source_phase_id'] = str(updated.get('phase_id') or '').strip() or None
        updated['branch_semantic_review_evidence_binding'] = evidence_binding
        if not verdict:
            stale_verdict = (
                updated.get('semantic_review_verdict')
                if isinstance(updated.get('semantic_review_verdict'), Mapping)
                else {}
            )
            if stale_verdict:
                updated['ignored_stale_branch_semantic_review'] = intent_coverage._compact_mapping(
                    {
                        'kind': 'fruth.ignored_stale_branch_semantic_review',
                        'reason': 'no completed branch review matches the current evidence generation',
                        'stale_evidence_sha256': previous_evidence_binding.get('sha256'),
                        'current_evidence_sha256': evidence_sha256,
                    }
                )
            for key in (
                'semantic_review_verdict',
                'semantic_review_verdict_status',
                'semantic_review_recommended_transition',
                'semantic_review_freeze_acceptance',
                'branch_semantic_review',
            ):
                updated.pop(key, None)
            updated['branch_semantic_review_status'] = 'pending'
            return updated
        required_criteria = [
            item
            for item in (
                self._string_list(updated.get('semantic_review_criteria'))
                or self._string_list(updated.get('review_criteria'))
            )
            if not self._review_criterion_is_deterministic(item)
        ]
        freeze_acceptance = semantic_review_verdict_freeze_acceptance(
            verdict,
            required_criteria=required_criteria,
            evidence_reference_policy=updated.get('content_review_reference_policy', ''),
            evidence_packet=evidence_payload,
        )
        verdict = dict(verdict)
        verdict['freeze_acceptance'] = freeze_acceptance
        accepted = freeze_acceptance.get('accepted') is True
        branch_review_status = (
            'fulfilled'
            if accepted
            else 'blocked'
            if str(verdict.get('status') or '').strip().lower() == 'blocked'
            else 'pending'
        )
        updated['semantic_review_verdict'] = verdict
        updated['semantic_review_verdict_status'] = verdict.get('status')
        updated['semantic_review_recommended_transition'] = verdict.get('recommended_transition')
        updated['semantic_review_freeze_acceptance'] = freeze_acceptance
        updated['branch_semantic_review'] = {
            'kind': 'fruth.branch_semantic_review',
            'status': branch_review_status,
            'review_branch_id': review_branch_id,
            'review_phase_id': review_phase_id,
            'source_branch_id': updated.get('branch_id'),
            'source_phase_id': updated.get('phase_id'),
            'semantic_review_evidence_binding': evidence_binding,
            'semantic_review_freeze_acceptance': freeze_acceptance,
            'semantic_review_verdict': verdict,
            'authority': 'advisory_branch_review_runtime_closure_decides_truth',
        }
        updated['branch_semantic_review_status'] = branch_review_status
        rejected_pass = (
            str(verdict.get('verdict') or '').strip().lower() == 'passed'
            and not accepted
        )
        transition_action = (
            RECOVERY_ACTION_MANUAL_REVIEW
            if rejected_pass
            else self._recovery_action_for_semantic_review_transition(
                verdict.get('recommended_transition')
            )
        )
        if accepted:
            if updated.get('content_requirements'):
                updated['content_coverage_status'] = 'accepted_review'
                updated['completion_basis'] = 'bound_semantic_review'
            updated['semantic_review_required'] = False
            updated['review_criteria_status'] = 'passed_semantic_review'
            updated['semantic_review_action'] = None
            updated['repair_action'] = None
            updated['recovery_action'] = None
            updated['repair_action_reason'] = None
            return updated
        updated['status'] = 'blocked' if str(verdict.get('status') or '').strip() == 'blocked' else 'pending'
        updated['evidence'] = 'branch_semantic_review_verdict'
        updated['semantic_review_required'] = transition_action == RECOVERY_ACTION_SEMANTIC_REVIEW
        updated['semantic_review_action'] = transition_action or RECOVERY_ACTION_MANUAL_REVIEW
        updated['repair_required'] = True
        updated['repair_action'] = transition_action or RECOVERY_ACTION_MANUAL_REVIEW
        updated['recovery_action'] = transition_action or RECOVERY_ACTION_MANUAL_REVIEW
        rejection_reasons = self._string_list(freeze_acceptance.get('rejection_reasons'))
        updated['repair_action_reason'] = (
            (
                'branch semantic review verdict did not satisfy the strict truthful-freeze contract'
                + (f': {", ".join(rejection_reasons)}' if rejection_reasons else '')
            )
            if rejected_pass
            else str(verdict.get('whole_intent_fit') or verdict.get('reason') or '').strip()
            or 'branch semantic review did not pass'
        )
        updated['branch_semantic_review_reason'] = updated['repair_action_reason']
        if updated['repair_action'] == RECOVERY_ACTION_REPAIR_DEPENDENCY_CHAIN:
            updated['blocked_by_dependency_input'] = True
        if updated['repair_action'] == RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT:
            updated['blocked_by_branch_contract'] = True
        return updated

    def _branch_semantic_review_checks(
        self,
        *,
        checks: Sequence[Mapping[str, Any]],
        request_payload: Optional[dict[str, Any]],
        request_phase_graph: Mapping[str, Any],
        artifact_payload: Optional[dict[str, Any]],
        output_text: str,
    ) -> list[dict[str, Any]]:
        prompt = intent_coverage._current_request_prompt_for_review(request_payload, request_phase_graph)
        review_checks: list[dict[str, Any]] = []
        existing_review_branch_ids = {
            str(item.get('branch_id') or item.get('phase_id') or '').strip()
            for item in checks
            if isinstance(item, Mapping)
            and str(item.get('check_kind') or '').strip() == 'branch_semantic_review'
            and str(item.get('branch_id') or item.get('phase_id') or '').strip()
        }
        for source_check in checks:
            if not isinstance(source_check, Mapping):
                continue
            if not self._check_is_branch_semantic_review_target(source_check):
                continue
            evidence_payload, content_payload, evidence_binding = (
                self._branch_semantic_review_contract(
                    artifact_payload=artifact_payload,
                    check=source_check,
                    prompt=prompt,
                    output_text=output_text,
                )
            )
            if source_check.get('content_requirements') and self.runtime_capability_availability(CAPABILITY_CHAT).get('available') is not True:
                review_checks.append({
                    'check_kind': 'branch_semantic_review', 'status': 'blocked',
                    'branch_id': evidence_binding.get('branch_id'),
                    'source_branch_id': source_check.get('branch_id'),
                    'reason': 'content_review_capacity_unavailable',
                    'content_coverage_status': 'unverified',
                    'completion_basis': 'technical_evidence_only',
                    'repair_action': RECOVERY_ACTION_MANUAL_REVIEW,
                    'recovery_action': RECOVERY_ACTION_MANUAL_REVIEW,
                })
                continue
            review_branch_id = str(evidence_binding.get('branch_id') or '').strip()
            review_phase_id = str(evidence_binding.get('phase_id') or '').strip()
            review_obligation_id = str(evidence_binding.get('obligation_id') or '').strip()
            review_task_id = str(evidence_binding.get('task_id') or '').strip()
            evidence_sha256 = str(evidence_binding.get('sha256') or '').strip().lower()
            projected_check = (
                evidence_payload.get('branch_check')
                if isinstance(evidence_payload.get('branch_check'), Mapping)
                else {}
            )
            if review_branch_id in existing_review_branch_ids:
                continue
            execution_contract = {
                'kind': 'fruth.execution_contract',
                'branch_id': review_branch_id,
                'phase_id': review_phase_id,
                'capability': CAPABILITY_CHAT,
                'output_type': 'text',
                'visibility': _SEMANTIC_REVIEW_VISIBILITY,
                'surface_role': _SEMANTIC_REVIEW_SURFACE_ROLE,
                'workload_task_ref': {
                    'task_id': review_task_id,
                    'phase_id': review_phase_id,
                    'branch_id': review_branch_id,
                },
                'output_obligation_ref': {
                    'obligation_id': review_obligation_id,
                    'phase_id': review_phase_id,
                    'branch_id': review_branch_id,
                    'output_type': 'text',
                },
                'output_contract': {
                    'output_type': 'text',
                    'required': True,
                    'fulfillment_policy': 'branch_semantic_review_verdict_required',
                    'visibility': _SEMANTIC_REVIEW_VISIBILITY,
                    'surface_role': _SEMANTIC_REVIEW_SURFACE_ROLE,
                    'semantic_review_lens': projected_check.get('semantic_review_lens'),
                    'success_definition': projected_check.get('success_definition'),
                },
                'input_refs': [
                    {'kind': 'branch_under_review', 'ref': str(source_check.get('branch_id') or source_check.get('phase_id') or '')},
                    {'kind': 'branch_review_criteria', 'ref': 'source_check.review_criteria'},
                    {'kind': 'runtime_evidence', 'ref': 'source_branch_evidence'},
                    {
                        'kind': 'semantic_review_evidence_sha256',
                        'ref': evidence_sha256,
                    },
                ],
                'semantic_review_evidence_binding': evidence_binding,
            }
            review_checks.append(
                intent_coverage._compact_mapping(
                    {
                        'check_kind': 'branch_semantic_review',
                        'status': 'pending',
                        'evidence': 'branch_semantic_review_required',
                        'reason': 'branch has qualitative review criteria that require branch-local semantic verdict before branch freeze',
                        'obligation_id': review_obligation_id,
                        'phase_id': review_phase_id,
                        'branch_id': review_branch_id,
                        'task_id': review_task_id,
                        'capability': CAPABILITY_CHAT,
                        'output_type': 'text',
                        'visibility': _SEMANTIC_REVIEW_VISIBILITY,
                        'surface_role': _SEMANTIC_REVIEW_SURFACE_ROLE,
                        'role': 'branch_semantic_review_output',
                        'depends_on': [str(source_check.get('branch_id') or source_check.get('phase_id') or '').strip()],
                        'repair_action': RECOVERY_ACTION_SEMANTIC_REVIEW,
                        'recovery_action': RECOVERY_ACTION_SEMANTIC_REVIEW,
                        'repair_action_reason': 'branch-local qualitative criteria need semantic review verdict',
                        'semantic_review_required': True,
                        'semantic_review_action': RECOVERY_ACTION_SEMANTIC_REVIEW,
                        'semantic_review_authority': 'closure_promoted_branch_semantic_review',
                        'semantic_review_criteria': projected_check.get('semantic_review_criteria') or projected_check.get('review_criteria'),
                        'semantic_review_lens': projected_check.get('semantic_review_lens'),
                        'success_definition': projected_check.get('success_definition'),
                        'failure_modes': projected_check.get('failure_modes'),
                        'semantic_lens_evidence_requirements': projected_check.get('semantic_lens_evidence_requirements') or projected_check.get('evidence_requirements'),
                        'review_criteria': [
                            'runtime_text_exists_when_fulfilled',
                            *(self._string_list(projected_check.get('semantic_review_criteria')) or self._string_list(projected_check.get('review_criteria'))),
                        ],
                        'branch_semantic_review': {
                            'kind': 'fruth.branch_semantic_review',
                            'status': 'pending',
                            'review_branch_id': review_branch_id,
                            'review_phase_id': review_phase_id,
                            'source_branch_id': source_check.get('branch_id'),
                            'source_phase_id': source_check.get('phase_id'),
                            'semantic_review_evidence_binding': evidence_binding,
                            'authority': 'advisory_branch_review_runtime_closure_decides_truth',
                        },
                        'branch_semantic_review_branch_id': review_branch_id,
                        'branch_semantic_review_phase_id': review_phase_id,
                        'branch_semantic_review_status': 'pending',
                        'branch_semantic_review_source_branch_id': source_check.get('branch_id'),
                        'branch_semantic_review_source_phase_id': source_check.get('phase_id'),
                        'branch_semantic_review_evidence_binding': evidence_binding,
                        'semantic_review_evidence_binding': evidence_binding,
                        'content_payload': content_payload,
                        'content_payload_source': evidence_binding.get('logical_review_id'),
                        'stage_direction': 'run_branch_semantic_review',
                        'execution_contract': execution_contract,
                        'input_refs': execution_contract['input_refs'],
                    }
                )
            )
        return review_checks

    @staticmethod
    def _recovery_action_for_semantic_review_transition(value: Any) -> str:
        transition = str(value or '').strip().lower()
        if transition == 'truthful_freeze':
            return ''
        if transition in {'clarify', 'waive_with_evidence', 'supersede_with_replacement_truth'}:
            return RECOVERY_ACTION_MANUAL_REVIEW
        return normalize_recovery_suggested_action(transition, default=RECOVERY_ACTION_SEMANTIC_REVIEW)

    @classmethod
    def _global_semantic_required_criteria(
        cls,
        checks: Sequence[Mapping[str, Any]],
        semantic_quality_contracts: Sequence[Mapping[str, Any]],
    ) -> list[str]:
        required: list[str] = []
        identities: set[str] = set()

        def _add(values: Any) -> None:
            for value in cls._string_list(values):
                if cls._review_criterion_is_deterministic(value):
                    continue
                identity = cls._normalized_review_criterion(value)
                if not identity or identity in identities:
                    continue
                identities.add(identity)
                required.append(value)

        for check in checks:
            if not isinstance(check, Mapping):
                continue
            _add(check.get('semantic_review_criteria') or check.get('review_criteria'))
        for contract in semantic_quality_contracts:
            if not isinstance(contract, Mapping):
                continue
            _add(contract.get('semantic_review_criteria') or contract.get('review_criteria'))
        return required

    @classmethod
    def _global_semantic_verdict_proposal(cls, verdict: Mapping[str, Any]) -> dict[str, Any]:
        transition = str(verdict.get('recommended_transition') or '').strip().lower()
        freeze_acceptance = (
            verdict.get('freeze_acceptance')
            if isinstance(verdict.get('freeze_acceptance'), Mapping)
            else {}
        )
        rejected_pass = bool(
            freeze_acceptance
            and freeze_acceptance.get('accepted') is not True
            and str(verdict.get('verdict') or '').strip().lower() == 'passed'
            and transition == 'truthful_freeze'
        )
        if rejected_pass:
            transition = RECOVERY_ACTION_MANUAL_REVIEW
        action = cls._recovery_action_for_semantic_review_transition(transition)
        defects = verdict.get('defects') if isinstance(verdict.get('defects'), list) else []
        if rejected_pass:
            rejection_reasons = cls._string_list(freeze_acceptance.get('rejection_reasons'))
            reason = 'semantic review verdict did not satisfy the strict truthful-freeze contract'
            if rejection_reasons:
                reason = f'{reason}: {", ".join(rejection_reasons)}'
        else:
            reason = (
                str(verdict.get('whole_intent_fit') or '').strip()
                or str(verdict.get('reason') or '').strip()
                or 'semantic review verdict did not pass'
            )
        if defects:
            reason = f'{reason}; defects: {", ".join(str(item) for item in defects)}'
        return intent_coverage._compact_mapping(
            {
                'kind': 'fruth.global_semantic_closure_proposal',
                'proposal_id': f"global-semantic-closure-verdict-{str(verdict.get('verdict') or 'uncertain').strip()}",
                'status': 'advisory',
                'authority': 'advisory_verdict_until_closure_confirms_transition',
                'decision_action': action or None,
                'recommended_transition': transition or None,
                'confidence': verdict.get('confidence'),
                'reason': reason,
                'allowed_transitions': [
                    RECOVERY_ACTION_SEMANTIC_REVIEW,
                    RECOVERY_ACTION_REPAIR_DEPENDENCY_CHAIN,
                    RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT,
                    RECOVERY_ACTION_REBUILD_FROM_PROMOTED_OBLIGATIONS,
                    'clarify',
                    'waive_with_evidence',
                    'supersede_with_replacement_truth',
                    'manual_review',
                    'truthful_freeze_after_review',
                ],
                'evidence_refs': verdict.get('evidence_refs'),
                'semantic_review_verdict': verdict,
            }
        )

    @observe_call('response_semantics.build_global_semantic_closure_review',
                  result=judgment_summary)
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
        prompt = intent_coverage._current_request_prompt_for_review(request_payload, request_phase_graph)
        def _check_needs_global_semantic_review(check: Mapping[str, Any]) -> bool:
            if check.get('semantic_review_required') is not True:
                return False
            if str(check.get('review_criteria_status') or '').strip().lower() == 'semantic_review_required':
                return True
            criteria = self._string_list(check.get('semantic_review_criteria')) or self._string_list(check.get('review_criteria'))
            return any(not self._review_criterion_is_deterministic(item) for item in criteria)

        semantic_checks = [
            check for check in checks
            if isinstance(check, Mapping) and _check_needs_global_semantic_review(check)
        ]
        semantic_decision_review = (
            decision_contract.get('semantic_decision_review')
            if isinstance(decision_contract, Mapping) and isinstance(decision_contract.get('semantic_decision_review'), Mapping)
            else {}
        )
        semantic_decision_proposals = (
            semantic_decision_review.get('proposals')
            if isinstance(semantic_decision_review.get('proposals'), list)
            else []
        )
        semantic_quality_review = (
            decision_contract.get('semantic_quality_review')
            if isinstance(decision_contract, Mapping) and isinstance(decision_contract.get('semantic_quality_review'), Mapping)
            else {}
        )
        semantic_quality_contracts = (
            semantic_quality_review.get('contracts')
            if isinstance(semantic_quality_review.get('contracts'), list)
            else []
        )
        # This admission policy asks one review per accepted branch group.
        # Its advisory IR quality projection must not manufacture a second,
        # whole-turn review after those same exact criteria were discharged.
        covered_content = {
            (check.get('branch_id'), requirement.get('criterion'))
            for check in checks if isinstance(check, Mapping)
            and check.get('content_coverage_status') in {'accepted_review', 'authorized_disposition'}
            for requirement in check.get('content_requirements', [])
        }
        if covered_content:
            semantic_quality_contracts = [
                {**contract, 'review_criteria': [criterion for criterion in self._string_list(contract.get('review_criteria'))
                    if (contract.get('branch_id'), criterion) not in covered_content]}
                if isinstance(contract, Mapping) else contract
                for contract in semantic_quality_contracts
            ]
        required_semantic_criteria = self._global_semantic_required_criteria(
            checks,
            semantic_quality_contracts,
        )
        controlled_attention_review = (
            decision_contract.get('controlled_attention_review')
            if isinstance(decision_contract, Mapping) and isinstance(decision_contract.get('controlled_attention_review'), Mapping)
            else {}
        )
        aspiration_review = (
            decision_contract.get('aspiration_review')
            if isinstance(decision_contract, Mapping) and isinstance(decision_contract.get('aspiration_review'), Mapping)
            else {}
        )
        commitment_review = (
            decision_contract.get('commitment_review')
            if isinstance(decision_contract, Mapping) and isinstance(decision_contract.get('commitment_review'), Mapping)
            else {}
        )
        semantic_quality_required = any(
            isinstance(contract, Mapping)
            and any(
                not self._review_criterion_is_deterministic(item)
                for item in self._string_list(contract.get('review_criteria'))
            )
            for contract in semantic_quality_contracts
        )
        structural_pending = (
            isinstance(intent_graph_adequacy, Mapping)
            and str(intent_graph_adequacy.get('status') or '').strip().lower() == 'pending'
        )
        semantic_pending = bool(
            semantic_checks
            or semantic_quality_required
        )
        local_unresolved = any(
            isinstance(check, Mapping)
            and str(check.get('status') or '').strip().lower() in {'pending', 'planned', 'active', 'deferred', 'blocked'}
            and str(check.get('check_kind') or '').strip() not in {
                'intent_graph_adequacy',
                'global_semantic_closure',
            }
            for check in checks
        )
        if not structural_pending and not semantic_pending:
            return intent_coverage._compact_mapping(
                {
                    'kind': 'fruth.global_semantic_closure_review',
                    'status': 'not_applicable',
                    'authority': 'advisory_read_model_only',
                    'policy': 'whole_turn_semantic_fit_checked_after_runtime_materialization',
                    'reason': 'no structural or semantic whole-graph closure signal requires review',
                }
            )
        if semantic_pending and local_unresolved and not structural_pending:
            return intent_coverage._compact_mapping(
                {
                    'kind': 'fruth.global_semantic_closure_review',
                    'status': 'waiting_on_local_closure',
                    'authority': 'advisory_read_model_only',
                    'policy': 'local_branch_truth_must_fit_whole_current_intent_before_freeze',
                    'reason': 'whole-turn semantic review waits until local promoted obligations are fulfilled or repaired',
                    'intent_anchor': prompt or None,
                    'proposal_count': 0,
                    'semantic_check_count': len(semantic_checks),
                    'semantic_decision_proposal_count': len(semantic_decision_proposals),
                    'controlled_attention_frame_count': int(controlled_attention_review.get('frame_count') or 0),
                    'aspiration_frame_count': int(aspiration_review.get('frame_count') or 0),
                    'commitment_frame_count': int(commitment_review.get('frame_count') or 0),
                    'semantic_quality_status': str(semantic_quality_review.get('status') or '').strip() or None,
                }
            )

        evidence_payload = self._global_semantic_evidence_payload(
            artifact_payload=artifact_payload,
            checks=checks,
            intent_graph_adequacy=intent_graph_adequacy,
            decision_contract=decision_contract,
        )
        content_payload = self._global_semantic_review_instruction(
            prompt=prompt,
            output_text=output_text,
            evidence_payload=evidence_payload,
        )
        evidence_binding = self._global_semantic_review_generation(content_payload)
        review_branch_id = str(evidence_binding.get('branch_id') or '').strip()
        review_phase_id = str(evidence_binding.get('phase_id') or '').strip()
        review_obligation_id = str(evidence_binding.get('obligation_id') or '').strip()
        review_task_id = str(evidence_binding.get('task_id') or '').strip()
        evidence_sha256 = str(evidence_binding.get('sha256') or '').strip()
        completed_record, completed_status = self._late_fill_branch_record(
            artifact_payload,
            review_branch_id,
        )
        if (
            completed_status == 'fulfilled'
            and self._semantic_review_evidence_sha256_from_record(completed_record)
            != evidence_sha256
        ):
            completed_status = ''
        completed_semantic_review_verdict = (
            self._semantic_review_verdict_from_late_fill(
                artifact_payload,
                review_branch_id,
                review_id='global-semantic-closure-review',
                expected_evidence_sha256=evidence_sha256,
            )
            if completed_status == 'fulfilled'
            else {}
        )
        completed_freeze_acceptance = (
            semantic_review_verdict_freeze_acceptance(
                completed_semantic_review_verdict,
                required_criteria=required_semantic_criteria,
            )
            if completed_semantic_review_verdict
            else {}
        )
        if completed_semantic_review_verdict:
            completed_semantic_review_verdict = dict(completed_semantic_review_verdict)
            completed_semantic_review_verdict['freeze_acceptance'] = completed_freeze_acceptance
        if completed_status == 'fulfilled' and completed_freeze_acceptance.get('accepted') is True:
            return intent_coverage._compact_mapping(
                {
                    'kind': 'fruth.global_semantic_closure_review',
                    'status': 'fulfilled',
                    'authority': 'advisory_review_output_runtime_evidence',
                    'policy': 'whole_turn_semantic_fit_checked_after_runtime_materialization',
                    'reason': 'global semantic review branch returned a passed verdict for the current evidence generation',
                    'proposal_count': 0,
                    'completed_branch_id': review_branch_id,
                    'review_branch_id': review_branch_id,
                    'review_phase_id': review_phase_id,
                    'review_obligation_id': review_obligation_id,
                    'review_task_id': review_task_id,
                    'semantic_review_evidence_binding': evidence_binding,
                    'required_semantic_criteria': required_semantic_criteria,
                    'semantic_review_freeze_acceptance': completed_freeze_acceptance,
                    'semantic_review_verdict': completed_semantic_review_verdict,
                    'semantic_review_verdict_status': completed_semantic_review_verdict.get('status'),
                    'semantic_review_recommended_transition': completed_semantic_review_verdict.get('recommended_transition'),
                }
            )
        if completed_status == 'fulfilled':
            proposal = self._global_semantic_verdict_proposal(completed_semantic_review_verdict)
            verdict_status = str(completed_semantic_review_verdict.get('status') or '').strip().lower()
            status = 'blocked' if verdict_status == 'blocked' else 'pending'
            return intent_coverage._compact_mapping(
                {
                    'kind': 'fruth.global_semantic_closure_review',
                    'status': status,
                    'authority': 'advisory_until_closure_confirms_verdict_transition',
                    'policy': 'semantic_review_completion_requires_strict_truthful_freeze_contract',
                    'reason': (
                        'global semantic review branch completed but did not satisfy the strict truthful-freeze contract'
                    ),
                    'intent_anchor': prompt or None,
                    'proposal_count': 1 if proposal else 0,
                    'semantic_check_count': len(semantic_checks),
                    'structural_adequacy_status': (
                        str(intent_graph_adequacy.get('status') or '').strip().lower()
                        if isinstance(intent_graph_adequacy, Mapping)
                        else None
                    ),
                    'semantic_decision_proposal_count': len(semantic_decision_proposals),
                    'controlled_attention_frame_count': int(controlled_attention_review.get('frame_count') or 0),
                    'aspiration_frame_count': int(aspiration_review.get('frame_count') or 0),
                    'commitment_frame_count': int(commitment_review.get('frame_count') or 0),
                    'semantic_quality_status': str(semantic_quality_review.get('status') or '').strip() or None,
                    'completed_branch_id': review_branch_id,
                    'required_semantic_criteria': required_semantic_criteria,
                    'semantic_review_freeze_acceptance': completed_freeze_acceptance,
                    'semantic_review_verdict': completed_semantic_review_verdict,
                    'semantic_review_verdict_status': completed_semantic_review_verdict.get('status'),
                    'semantic_review_recommended_transition': completed_semantic_review_verdict.get('recommended_transition'),
                    'proposals': [proposal] if proposal else [],
                    'review_branch_id': review_branch_id,
                    'review_phase_id': review_phase_id,
                    'review_obligation_id': review_obligation_id,
                    'review_task_id': review_task_id,
                    'semantic_review_evidence_binding': evidence_binding,
                    'dependency_phase_ids': evidence_payload.get('artifact_dependency_ids'),
                    'content_payload': content_payload,
                    'content_payload_source': 'global_semantic_closure_review',
                    'stage_direction': 'run_global_semantic_closure_review',
                }
            )
        proposals: list[dict[str, Any]] = []
        if structural_pending:
            proposals.append(
                intent_coverage._compact_mapping(
                    {
                        'kind': 'fruth.global_semantic_closure_proposal',
                        'proposal_id': 'global-semantic-closure-structural-adequacy',
                        'status': 'advisory',
                        'authority': 'advisory_until_closure_confirms_promoted_obligation_gap',
                        'decision_action': RECOVERY_ACTION_REBUILD_FROM_PROMOTED_OBLIGATIONS,
                        'recommended_transition': RECOVERY_ACTION_REBUILD_FROM_PROMOTED_OBLIGATIONS,
                        'confidence': 0.82,
                        'reason': 'structural graph adequacy is pending before whole-turn semantic closure can freeze',
                        'allowed_transitions': [
                            RECOVERY_ACTION_REBUILD_FROM_PROMOTED_OBLIGATIONS,
                            RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT,
                            'clarify',
                            'waive_with_evidence',
                            'truthful_freeze_after_repair',
                        ],
                        'evidence_refs': ['intent_graph_adequacy', 'graph_output_counts', 'expected_output_counts'],
                    }
                )
            )
        if semantic_pending:
            semantic_refs: list[str] = []
            for check in semantic_checks:
                for key in ('branch_id', 'phase_id', 'obligation_id', 'task_id'):
                    value = str(check.get(key) or '').strip()
                    if value and value not in semantic_refs:
                        semantic_refs.append(value)
            proposals.append(
                intent_coverage._compact_mapping(
                    {
                        'kind': 'fruth.global_semantic_closure_proposal',
                        'proposal_id': 'global-semantic-closure-whole-intent-fit',
                        'status': 'advisory',
                        'authority': 'advisory_until_promoted_semantic_review_branch_completes',
                        'decision_action': RECOVERY_ACTION_SEMANTIC_REVIEW,
                        'recommended_transition': RECOVERY_ACTION_SEMANTIC_REVIEW,
                        'confidence': 0.76,
                        'reason': 'local output existence does not prove the generated work fits the whole current intent',
                        'allowed_transitions': [
                            RECOVERY_ACTION_SEMANTIC_REVIEW,
                            RECOVERY_ACTION_REPAIR_DEPENDENCY_CHAIN,
                            RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT,
                            RECOVERY_ACTION_REBUILD_FROM_PROMOTED_OBLIGATIONS,
                            'waive_with_evidence',
                            'supersede_with_replacement_truth',
                            'truthful_freeze_after_review',
                        ],
                        'evidence_refs': [
                            'semantic_quality_review',
                            'semantic_decision_review',
                            'controlled_attention_review',
                            'aspiration_review',
                            'commitment_review',
                            *semantic_refs,
                        ],
                    }
                )
            )
        status = 'blocked' if completed_status == 'blocked' else 'pending'
        reason = (
            'global semantic review branch failed'
            if completed_status == 'blocked'
            else 'whole-turn semantic closure requires review before truthful freeze'
        )
        return intent_coverage._compact_mapping(
            {
                'kind': 'fruth.global_semantic_closure_review',
                'status': status,
                'authority': 'advisory_until_closure_promotes_review_or_repair',
                'policy': 'local_branch_truth_must_fit_whole_current_intent_before_freeze',
                'reason': reason,
                'intent_anchor': prompt or None,
                'proposal_count': len(proposals),
                'semantic_check_count': len(semantic_checks),
                'structural_adequacy_status': (
                    str(intent_graph_adequacy.get('status') or '').strip().lower()
                    if isinstance(intent_graph_adequacy, Mapping)
                    else None
                ),
                'semantic_decision_proposal_count': len(semantic_decision_proposals),
                'controlled_attention_frame_count': int(controlled_attention_review.get('frame_count') or 0),
                'aspiration_frame_count': int(aspiration_review.get('frame_count') or 0),
                'commitment_frame_count': int(commitment_review.get('frame_count') or 0),
                'semantic_quality_status': str(semantic_quality_review.get('status') or '').strip() or None,
                'proposals': proposals,
                'review_branch_id': review_branch_id,
                'review_phase_id': review_phase_id,
                'review_obligation_id': review_obligation_id,
                'review_task_id': review_task_id,
                'semantic_review_evidence_binding': evidence_binding,
                'dependency_phase_ids': evidence_payload.get('artifact_dependency_ids'),
                'content_payload': content_payload,
                'content_payload_source': 'global_semantic_closure_review',
                'stage_direction': 'run_global_semantic_closure_review',
            }
        )

    def _global_semantic_closure_checks(
        self,
        global_review: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        if not isinstance(global_review, Mapping):
            return []
        if str(global_review.get('status') or '').strip().lower() not in {'pending', 'blocked'}:
            return []
        proposals = global_review.get('proposals') if isinstance(global_review.get('proposals'), list) else []
        dependency_phase_ids = self._string_list(global_review.get('dependency_phase_ids'))
        checks: list[dict[str, Any]] = []
        for proposal in proposals:
            if not isinstance(proposal, Mapping):
                continue
            verdict_payload = (
                proposal.get('semantic_review_verdict')
                if isinstance(proposal.get('semantic_review_verdict'), Mapping)
                else {}
            )
            if verdict_payload:
                action = self._recovery_action_for_semantic_review_transition(
                    proposal.get('recommended_transition') or proposal.get('decision_action')
                )
                if not action:
                    continue
            else:
                action = normalize_recovery_suggested_action(proposal.get('decision_action'), default='')
                if action == RECOVERY_ACTION_REBUILD_FROM_PROMOTED_OBLIGATIONS:
                    continue
                if action != RECOVERY_ACTION_SEMANTIC_REVIEW:
                    continue
            branch_id = str(global_review.get('review_branch_id') or 'branch-global-semantic-closure-review').strip()
            phase_id = str(global_review.get('review_phase_id') or 'phase-global-semantic-closure-review').strip()
            obligation_id = str(
                global_review.get('review_obligation_id')
                or 'obligation-global-semantic-closure-review'
            ).strip()
            task_id = str(global_review.get('review_task_id') or 'task-global-semantic-closure-review').strip()
            evidence_binding = (
                dict(global_review.get('semantic_review_evidence_binding'))
                if isinstance(global_review.get('semantic_review_evidence_binding'), Mapping)
                else {}
            )
            evidence_sha256 = str(evidence_binding.get('sha256') or '').strip().lower()
            execution_contract = {
                'kind': 'fruth.execution_contract',
                'branch_id': branch_id,
                'phase_id': phase_id,
                'capability': CAPABILITY_CHAT,
                'output_type': 'text',
                'visibility': _SEMANTIC_REVIEW_VISIBILITY,
                'surface_role': _SEMANTIC_REVIEW_SURFACE_ROLE,
                'workload_task_ref': {
                    'task_id': task_id,
                    'phase_id': phase_id,
                    'branch_id': branch_id,
                },
                'output_obligation_ref': {
                    'obligation_id': obligation_id,
                    'phase_id': phase_id,
                    'branch_id': branch_id,
                    'output_type': 'text',
                },
                'output_contract': {
                    'output_type': 'text',
                    'required': True,
                    'fulfillment_policy': 'semantic_review_text_required',
                    'visibility': _SEMANTIC_REVIEW_VISIBILITY,
                    'surface_role': _SEMANTIC_REVIEW_SURFACE_ROLE,
                },
                'input_refs': [
                    {'kind': 'intent_anchor', 'ref': 'current_user_intent'},
                    {'kind': 'closure_checks', 'ref': 'runtime.graph_closure_review.checks'},
                    {'kind': 'runtime_evidence', 'ref': 'artifacts_and_late_fill'},
                    *(
                        [
                            {
                                'kind': 'semantic_review_evidence_sha256',
                                'ref': evidence_sha256,
                            }
                        ]
                        if evidence_sha256
                        else []
                    ),
                    *[
                        {'kind': 'runtime_artifact_phase', 'ref': phase_id}
                        for phase_id in dependency_phase_ids
                    ],
                ],
                'semantic_review_evidence_binding': evidence_binding,
            }
            checks.append(
                intent_coverage._compact_mapping(
                    {
                        'check_kind': 'global_semantic_closure',
                        'status': str(global_review.get('status') or '').strip().lower() or 'pending',
                        'evidence': 'global_semantic_closure_review',
                        'reason': str(proposal.get('reason') or global_review.get('reason') or '').strip(),
                        'obligation_id': obligation_id,
                        'phase_id': phase_id,
                        'branch_id': branch_id,
                        'task_id': task_id,
                        'depends_on': dependency_phase_ids,
                        'capability': CAPABILITY_CHAT,
                        'output_type': 'text',
                        'visibility': _SEMANTIC_REVIEW_VISIBILITY,
                        'surface_role': _SEMANTIC_REVIEW_SURFACE_ROLE,
                        'role': 'semantic_review_transition',
                        'repair_action': action,
                        'recovery_action': action,
                        'repair_action_reason': str(proposal.get('reason') or '').strip(),
                        'semantic_review_required': action == RECOVERY_ACTION_SEMANTIC_REVIEW,
                        'semantic_review_action': action,
                        'semantic_review_authority': (
                            'closure_promoted_semantic_review_branch'
                            if action == RECOVERY_ACTION_SEMANTIC_REVIEW
                            else 'semantic_verdict_advisory_transition'
                        ),
                        'semantic_review_criteria': [
                            'whole_turn_output_fits_current_user_intent',
                            'local_branch_outputs_are_used_in_their_declared_roles',
                            'missing_or_wrong_work_is_reported_as_repair_waiver_or_supersession',
                        ],
                        'review_criteria': [
                            'runtime_text_exists_when_fulfilled',
                            'whole_turn_output_fits_current_user_intent',
                            'local_branch_outputs_are_used_in_their_declared_roles',
                        ],
                        'global_semantic_closure_review': {
                            key: global_review.get(key)
                            for key in (
                                'kind',
                                'status',
                                'authority',
                                'policy',
                                'reason',
                                'proposal_count',
                                'semantic_check_count',
                                'structural_adequacy_status',
                                'semantic_decision_proposal_count',
                                'semantic_quality_status',
                                'semantic_review_verdict_status',
                                'semantic_review_recommended_transition',
                                'semantic_review_evidence_binding',
                            )
                            if global_review.get(key) not in (None, '', [], {})
                        },
                        'global_semantic_closure_proposal': proposal,
                        'global_semantic_closure_status': str(global_review.get('status') or '').strip().lower(),
                        'global_semantic_closure_reason': str(global_review.get('reason') or '').strip(),
                        'global_semantic_closure_confidence': proposal.get('confidence'),
                        'semantic_review_verdict': verdict_payload,
                        'semantic_review_verdict_status': (
                            str(verdict_payload.get('status') or '').strip().lower()
                            if verdict_payload
                            else None
                        ),
                        'semantic_review_recommended_transition': (
                            str(verdict_payload.get('recommended_transition') or '').strip()
                            if verdict_payload
                            else None
                        ),
                        'blocked_by_dependency_input': action in {
                            RECOVERY_ACTION_REPAIR_DEPENDENCY_CHAIN,
                            RECOVERY_ACTION_REBIND_DEPENDENCY_EVIDENCE,
                        },
                        'blocked_by_branch_contract': action == RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT,
                        'content_payload': global_review.get('content_payload'),
                        'content_payload_source': global_review.get('content_payload_source'),
                        'stage_direction': global_review.get('stage_direction'),
                        'semantic_review_evidence_binding': evidence_binding,
                        'execution_contract': execution_contract,
                        'input_refs': execution_contract['input_refs'],
                    }
                )
            )
        return checks

    @staticmethod
    def _normalized_review_criterion(value: Any) -> str:
        return re.sub(r'[^a-z0-9_]+', '_', str(value or '').lower()).strip('_')

    @classmethod
    def _review_criterion_is_deterministic(cls, value: Any) -> bool:
        return cls._normalized_review_criterion(value) in _DETERMINISTIC_REVIEW_CRITERIA

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if isinstance(value, str):
            raw_items = [value]
        elif isinstance(value, list):
            raw_items = value
        else:
            return []
        values: list[str] = []
        for raw_item in raw_items:
            text = str(raw_item or '').strip()
            if text and text not in values:
                values.append(text)
        return values

