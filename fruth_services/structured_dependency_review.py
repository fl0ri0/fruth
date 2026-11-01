"""Structured output and producer/consumer join verification.

Uses explicit graph/results and one canonical artifact projection operation.
Cardinality, required fields, labels and exact reference bindings remain checks;
a well-shaped object alone does not fulfill the accepted output contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from fruth_services import intent_coverage
from fruth_services.text_artifact_syntax import (
    _normalize_text_artifact_extension,
    _strip_fenced_json_boundary,
)
import json
import logging
import re
from pathlib import Path
from typing import Any, Mapping, Optional
from helpers.model_capabilities import (
    CAPABILITY_CHAT,
    CAPABILITY_IMAGE_GENERATION,
    CAPABILITY_SPEECH_TO_TEXT,
    CAPABILITY_TEXT_TO_SPEECH,
    CAPABILITY_VISION_ANALYSIS,
    normalize_capability,
)
from fruth_inference.request_ir import output_obligations_from_graph
from fruth_server.recovery_contract import (
    RECOVERY_ACTION_REBIND_DEPENDENCY_EVIDENCE,
    RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT,
)


_STRUCTURED_JSON_LIST_CONTRACT_RE = re.compile(
    r'\bjson\s*(?:[-_/]\s*|\s+)(?:list(?:e)?|array)\b',
    re.IGNORECASE,
)


_STRUCTURED_JOIN_ENUMERATED_LABEL_RE = re.compile(
    r'(?<![A-Za-z0-9_])(?P<label>[A-Za-z]|[0-9]+)\s*[-–—]\s*(?=\S)'
)


_STRUCTURED_JOIN_FOR_LABELS_RE = re.compile(
    r'\b(?:(?i:für|for))\s+'
    r'(?P<body>(?:[A-Za-z]|[0-9]+)'
    r'(?:\s*(?:,|/)\s*(?:[A-Za-z]|[0-9]+))*'
    r'(?:\s*,?\s*(?:(?i:und|and)|&)\s*(?:[A-Za-z]|[0-9]+))?)\b'
)


_STRUCTURED_JOIN_FIELDS_RE = re.compile(
    r'\b(?:fields?|felder(?:n)?)\b(?P<body>[^.;!\n]{0,180})',
    re.IGNORECASE,
)


_STRUCTURED_JOIN_FIELD_STOP_WORDS = {
    'and',
    'are',
    'den',
    'die',
    'mit',
    'oder',
    'or',
    'sind',
    'the',
    'und',
    'with',
}


_STRUCTURED_JOIN_ARTIFACT_REF_FIELDS = {
    'artifact_path',
    'artifact_ref',
    'path',
    'ref',
}


_STRUCTURED_JOIN_CONSUMER_PRODUCER_TYPES = {
    CAPABILITY_VISION_ANALYSIS: (CAPABILITY_IMAGE_GENERATION, 'image'),
    CAPABILITY_SPEECH_TO_TEXT: (CAPABILITY_TEXT_TO_SPEECH, 'audio'),
}


_STRUCTURED_JOIN_DIRECT_PRODUCER_TYPES = {
    CAPABILITY_IMAGE_GENERATION: 'image',
    CAPABILITY_TEXT_TO_SPEECH: 'audio',
}


def _bounded_visual_evidence_from_selected_message(content: Any) -> str:
    """Extract only the bounded visual-evidence section from a carried message."""

    text = str(content or '').strip()
    if not text:
        return ''

    evidence_values: list[str] = []

    def collect_json_evidence(value: Any) -> None:
        if isinstance(value, Mapping):
            for raw_key, child in value.items():
                key = re.sub(
                    r'[^a-z0-9]+',
                    '_',
                    str(raw_key or '').casefold(),
                ).strip('_')
                is_visual = any(
                    token in key
                    for token in ('image', 'visual', 'bild', 'sichtbar')
                )
                is_evidence = any(
                    token in key
                    for token in ('evidence', 'analysis', 'analyse', 'detail')
                )
                if (
                    is_visual
                    and is_evidence
                    and isinstance(child, str)
                    and child.strip()
                ):
                    normalized = re.sub(r'\s+', ' ', child).strip()
                    if normalized not in evidence_values:
                        evidence_values.append(normalized)
                collect_json_evidence(child)
        elif isinstance(value, list):
            for child in value:
                collect_json_evidence(child)

    for match in re.finditer(r'(?is)```(?:json)?\s*(\{.*?\})\s*```', text):
        try:
            collect_json_evidence(json.loads(match.group(1)))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    if evidence_values:
        return '\n'.join(evidence_values)[:6000].rstrip()

    heading_match = re.search(
        r'(?ims)^\s*(?:#{1,6}\s*)?(?:\*\*)?'
        r'(?:visible\s+(?:image\s+)?(?:evidence|details?)|image\s+(?:evidence|analysis)|'
        r'sichtbar\w*\s+(?:bild)?(?:evidenz|details?)|bildevidenz|bildanalyse)'
        r'(?:\*\*)?\s*:\s*(?P<body>.*?)'
        r'(?=^\s*(?:#{1,6}\s+|\*\*)[^\n]{1,100}(?:\*\*)?\s*:?\s*$|\Z)',
        text,
    )
    if not heading_match:
        return ''
    body = re.sub(
        r'^\s*(?:\*\*|__)\s*',
        '',
        str(heading_match.group('body') or ''),
    )
    return re.sub(r'\s+', ' ', body).strip()[:6000].rstrip()


def _extension_from_path_like(value: Any) -> str:
    token = str(value or '').strip().split('?', 1)[0].split('#', 1)[0]
    if not token or '.' not in token.rsplit('/', 1)[-1]:
        return ''
    return _normalize_text_artifact_extension(token.rsplit('/', 1)[-1].rsplit('.', 1)[-1])


def _artifact_path(record: Mapping[str, Any]) -> str:
    return str(record.get('path') or record.get('source_path') or record.get('saved_text_path') or '').strip()

@dataclass(frozen=True)
class StructuredDependencyReview:
    build_canonical_response_artifacts: Callable[[dict[str, Any]], list[dict[str, Any]]]

    @staticmethod
    def _sequential_structured_join_labels(values: list[str]) -> list[str]:
        labels: list[str] = []
        for value in values:
            label = str(value or '').strip()
            if label and label not in labels:
                labels.append(label)
        if len(labels) < 2:
            return []
        if all(len(label) == 1 and label.isalpha() for label in labels):
            if not (all(label.isupper() for label in labels) or all(label.islower() for label in labels)):
                return []
            first = ord(labels[0])
            return labels if all(
                ord(label) == first + index
                for index, label in enumerate(labels)
            ) else []
        if all(label.isdecimal() for label in labels):
            numeric_labels = [int(label) for label in labels]
            first = numeric_labels[0]
            return labels if all(
                label == first + index
                for index, label in enumerate(numeric_labels)
            ) else []
        return []

    @classmethod
    def _structured_dependency_join_prompt_contract(cls, prompt: str) -> dict[str, Any]:
        text = str(prompt or '').strip()
        if not text or not _STRUCTURED_JSON_LIST_CONTRACT_RE.search(text):
            return {}

        label_candidates: list[list[str]] = []
        enumerated = [
            str(match.group('label') or '').strip()
            for match in _STRUCTURED_JOIN_ENUMERATED_LABEL_RE.finditer(text)
        ]
        if enumerated:
            label_candidates.append(enumerated)
        for match in _STRUCTURED_JOIN_FOR_LABELS_RE.finditer(text):
            label_candidates.append(
                re.findall(
                    r'(?<![A-Za-z0-9_])([A-Za-z]|[0-9]+)(?![A-Za-z0-9_])',
                    str(match.group('body') or ''),
                )
            )
        sequential_candidates = [
            labels
            for labels in (
                cls._sequential_structured_join_labels(candidate)
                for candidate in label_candidates
            )
            if labels
        ]
        if not sequential_candidates:
            return {}
        labels = max(sequential_candidates, key=len)

        field_candidates: list[list[str]] = []
        for match in _STRUCTURED_JOIN_FIELDS_RE.finditer(text):
            body = re.split(
                r'\b(?:(?i:für|for))\b',
                str(match.group('body') or ''),
                maxsplit=1,
            )[0]
            body = re.sub(
                r'^\s*(?::|=)?\s*(?:(?i:are|sind)\s+)?',
                '',
                body,
            )
            body = re.sub(r'[`\'\"]', '', body)
            field_list_match = re.match(
                r'(?P<fields>[A-Za-z_][A-Za-z0-9_]*'
                r'(?:\s*,\s*[A-Za-z_][A-Za-z0-9_]*)*'
                r'(?:\s*,?\s*(?:(?i:und|and)|&)\s*[A-Za-z_][A-Za-z0-9_]*)?)',
                body,
            )
            field_text = (
                str(field_list_match.group('fields') or '')
                if field_list_match
                else ''
            )
            fields: list[str] = []
            for token in re.findall(
                r'(?<![A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_]*)(?![A-Za-z0-9_])',
                field_text,
            ):
                if token.lower() in _STRUCTURED_JOIN_FIELD_STOP_WORDS:
                    continue
                if token not in fields:
                    fields.append(token)
            if fields:
                field_candidates.append(fields)
        required_fields = next(
            (
                fields
                for fields in field_candidates
                if any(field.lower() == 'label' for field in fields)
                and any(field.lower() in _STRUCTURED_JOIN_ARTIFACT_REF_FIELDS for field in fields)
            ),
            [],
        )
        if not required_fields:
            return {}
        label_field = next(field for field in required_fields if field.lower() == 'label')
        artifact_ref_field = next(
            field
            for field in required_fields
            if field.lower() in _STRUCTURED_JOIN_ARTIFACT_REF_FIELDS
        )
        return {
            'format': 'json_list',
            'labels': labels,
            'required_fields': required_fields,
            'label_field': label_field,
            'artifact_ref_field': artifact_ref_field,
        }

    @staticmethod
    def _structured_join_graph_records(
        request_phase_graph: Mapping[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        ordered_records: list[dict[str, Any]] = []
        records_by_identity: dict[str, dict[str, Any]] = {}
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
        collections = (
            request_phase_graph.get('phases'),
            workload_graph.get('tasks'),
            request_phase_graph.get('downstream_branches'),
            output_obligations_from_graph(request_phase_graph),
        )
        for collection in collections:
            if not isinstance(collection, list):
                continue
            for raw_record in collection:
                if not isinstance(raw_record, Mapping):
                    continue
                phase_id = str(raw_record.get('phase_id') or '').strip()
                branch_id = str(raw_record.get('branch_id') or '').strip()
                identity = phase_id or branch_id
                if not identity:
                    continue
                record = records_by_identity.get(identity)
                if record is None:
                    record = dict(raw_record)
                    records_by_identity[identity] = record
                    ordered_records.append(record)
                else:
                    for key, value in raw_record.items():
                        if value not in (None, '', [], {}) and record.get(key) in (None, '', [], {}):
                            record[key] = value

        by_phase: dict[str, dict[str, Any]] = {}
        by_branch: dict[str, dict[str, Any]] = {}
        for record in ordered_records:
            phase_id = str(record.get('phase_id') or '').strip()
            branch_id = str(record.get('branch_id') or '').strip()
            if phase_id:
                by_phase[phase_id] = record
            if branch_id:
                by_branch[branch_id] = record
        return ordered_records, by_phase, by_branch

    @staticmethod
    def _structured_join_fill_result_for_record(
        fill_results: list[Any],
        record: Mapping[str, Any],
    ) -> dict[str, Any]:
        branch_id = str(record.get('branch_id') or '').strip()
        phase_id = str(record.get('phase_id') or '').strip()
        if branch_id:
            for result in reversed(fill_results):
                if (
                    isinstance(result, Mapping)
                    and str(result.get('branch_id') or '').strip() == branch_id
                ):
                    return dict(result)
        if phase_id:
            for result in reversed(fill_results):
                if (
                    isinstance(result, Mapping)
                    and str(result.get('phase_id') or '').strip() == phase_id
                ):
                    return dict(result)
        return {}

    @staticmethod
    def _structured_join_terminal_result_text(result: Mapping[str, Any]) -> str:
        for key in ('result_text', 'content', 'output_text', 'text'):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        raw_result = result.get('result') if isinstance(result.get('result'), Mapping) else {}
        choices = raw_result.get('choices') if isinstance(raw_result.get('choices'), list) else []
        for choice in choices:
            if not isinstance(choice, Mapping):
                continue
            message = choice.get('message') if isinstance(choice.get('message'), Mapping) else {}
            content = message.get('content')
            if isinstance(content, str) and content.strip():
                return content.strip()
        return ''

    @staticmethod
    def _structured_join_alias_tokens(value: Any) -> set[str]:
        raw = str(value or '').strip()
        if not raw:
            return set()
        tokens = {raw}
        path_value = raw[7:] if raw.startswith('file://') else raw
        if '/' in path_value or '\\' in path_value or path_value.startswith('.'):
            try:
                tokens.add(str(Path(path_value).expanduser().resolve(strict=False)))
            except (OSError, RuntimeError, ValueError):
                pass
        return tokens

    @classmethod
    def _structured_join_artifact_aliases(cls, record: Mapping[str, Any]) -> set[str]:
        aliases: set[str] = set()
        for key in (
            'artifact_ref',
            'ref',
            'path',
            'source_path',
            'saved_image_path',
            'saved_audio_path',
            'saved_text_path',
            'saved_video_path',
            'resolved_path',
            'url',
        ):
            aliases.update(cls._structured_join_alias_tokens(record.get(key)))
        for key in ('artifacts', 'input_artifacts', 'reference_artifacts'):
            values = record.get(key) if isinstance(record.get(key), list) else []
            for value in values:
                if isinstance(value, Mapping):
                    aliases.update(cls._structured_join_artifact_aliases(value))
        raw_result = record.get('result') if isinstance(record.get('result'), Mapping) else {}
        for artifact_key in ('image', 'audio'):
            raw_artifact = (
                raw_result.get(artifact_key)
                if isinstance(raw_result.get(artifact_key), Mapping)
                else {}
            )
            if raw_artifact:
                aliases.update(cls._structured_join_artifact_aliases(raw_artifact))
        return aliases

    @classmethod
    def _structured_join_artifact_path_aliases(cls, record: Mapping[str, Any]) -> set[str]:
        aliases: set[str] = set()
        for key in (
            'path',
            'source_path',
            'saved_image_path',
            'saved_audio_path',
            'saved_text_path',
            'saved_video_path',
            'resolved_path',
            'url',
        ):
            aliases.update(cls._structured_join_alias_tokens(record.get(key)))
        for key in ('artifacts', 'input_artifacts', 'reference_artifacts'):
            values = record.get(key) if isinstance(record.get(key), list) else []
            for value in values:
                if isinstance(value, Mapping):
                    aliases.update(cls._structured_join_artifact_path_aliases(value))
        raw_result = record.get('result') if isinstance(record.get('result'), Mapping) else {}
        for artifact_key in ('image', 'audio'):
            raw_artifact = (
                raw_result.get(artifact_key)
                if isinstance(raw_result.get(artifact_key), Mapping)
                else {}
            )
            if raw_artifact:
                aliases.update(cls._structured_join_artifact_path_aliases(raw_artifact))
        return aliases

    @staticmethod
    def _structured_join_artifact_matches_type(
        record: Mapping[str, Any],
        expected_type: str,
    ) -> bool:
        normalized_type = str(expected_type or '').strip().lower()
        artifact_type = str(record.get('type') or record.get('kind') or '').strip().lower()
        extension = _extension_from_path_like(_artifact_path(record))
        aliases = {
            'image': {'image', 'png', 'jpg', 'jpeg', 'webp'},
            'audio': {'audio', 'wav', 'mp3', 'm4a', 'flac', 'ogg', 'opus'},
        }.get(normalized_type, {normalized_type})
        return artifact_type in aliases or extension in aliases

    @staticmethod
    def _structured_object_reference_records(
        *payloads: Optional[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        seen: set[tuple[str, ...]] = set()
        for payload in payloads:
            if not isinstance(payload, Mapping):
                continue
            sources: list[Mapping[str, Any]] = [payload]
            request = payload.get('request')
            if isinstance(request, Mapping):
                sources.append(request)
            frame = payload.get('response_frame')
            frame_request = frame.get('request') if isinstance(frame, Mapping) else None
            if isinstance(frame_request, Mapping):
                sources.append(frame_request)
            for source in sources:
                for key in (
                    'selected_reference_artifacts',
                    'selectedReferenceArtifacts',
                    'reference_artifacts',
                    'input_artifacts',
                ):
                    values = source.get(key) if isinstance(source.get(key), list) else []
                    for value in values:
                        if not isinstance(value, Mapping):
                            continue
                        record = dict(value)
                        identity = (
                            str(record.get('type') or record.get('kind') or '').strip().lower(),
                            str(record.get('artifact_ref') or record.get('ref') or '').strip(),
                            str(record.get('path') or record.get('artifact_path') or '').strip(),
                            str(record.get('message_id') or '').strip(),
                            str(record.get('source_message_id') or '').strip(),
                            str(record.get('source_response_id') or '').strip(),
                            str(record.get('content') or record.get('text') or '').strip(),
                        )
                        if identity in seen:
                            continue
                        seen.add(identity)
                        records.append(record)
        return records

    @classmethod
    def _structured_object_source_artifact_refs(
        cls,
        source_result: Mapping[str, Any],
        source_record: Mapping[str, Any],
        artifact_payload: Mapping[str, Any],
    ) -> set[str]:
        source_phase_id = str(source_record.get('phase_id') or '').strip()
        source_branch_id = str(source_record.get('branch_id') or '').strip()
        source_path_aliases = cls._structured_join_artifact_path_aliases(source_result)

        def artifact_records(value: Any) -> list[Mapping[str, Any]]:
            records: list[Mapping[str, Any]] = []
            if isinstance(value, list):
                records.extend(item for item in value if isinstance(item, Mapping))
            elif isinstance(value, Mapping):
                if value.get('artifact_ref') or value.get('ref') or _artifact_path(value):
                    records.append(value)
                for key in ('output', 'input', 'reference', 'artifacts'):
                    nested = value.get(key)
                    if isinstance(nested, list):
                        records.extend(item for item in nested if isinstance(item, Mapping))
            return records

        source_candidates = artifact_records(source_result.get('artifacts'))
        raw_result = source_result.get('result')
        if isinstance(raw_result, Mapping):
            for key in ('audio', 'image', 'artifact'):
                candidate = raw_result.get(key)
                if isinstance(candidate, Mapping):
                    source_candidates.append(candidate)
        direct_source_ref = str(
            source_result.get('artifact_ref') or source_result.get('ref') or ''
        ).strip()

        canonical_candidates = artifact_records(artifact_payload.get('artifacts'))
        canonical_refs: set[str] = set()
        for candidate in canonical_candidates:
            candidate_phase_id = str(candidate.get('phase_id') or '').strip()
            candidate_branch_id = str(candidate.get('branch_id') or '').strip()
            identity_match = bool(
                (source_phase_id and candidate_phase_id == source_phase_id)
                or (source_branch_id and candidate_branch_id == source_branch_id)
            )
            path_match = bool(
                source_path_aliases.intersection(
                    cls._structured_join_artifact_path_aliases(candidate)
                )
            )
            if not identity_match and not path_match:
                continue
            artifact_ref = str(
                candidate.get('artifact_ref') or candidate.get('ref') or ''
            ).strip()
            if artifact_ref:
                canonical_refs.add(artifact_ref)
        if canonical_refs:
            return canonical_refs

        source_refs = {
            str(candidate.get('artifact_ref') or candidate.get('ref') or '').strip()
            for candidate in source_candidates
            if str(candidate.get('artifact_ref') or candidate.get('ref') or '').strip()
        }
        if direct_source_ref:
            source_refs.add(direct_source_ref)
        return source_refs

    def _structured_output_object_contract_checks(
        self,
        *,
        request_payload: Optional[Mapping[str, Any]],
        artifact_payload: Optional[Mapping[str, Any]],
        request_phase_graph: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        ordered_records, records_by_phase, records_by_branch = (
            self._structured_join_graph_records(request_phase_graph)
        )
        terminal_contracts: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for record in ordered_records:
            contract = (
                record.get('structured_output_contract')
                if isinstance(record.get('structured_output_contract'), Mapping)
                else {}
            )
            if (
                normalize_capability(record.get('capability')) == CAPABILITY_CHAT
                and str(record.get('dependency_contract') or '').strip()
                == 'structured_multi_evidence_join'
                and str(contract.get('format') or '').strip().lower() == 'json_object'
                and str(contract.get('cardinality') or '').strip().lower() == 'exactly_one'
            ):
                terminal_contracts.append((record, dict(contract)))
        if not terminal_contracts:
            return []

        payload = artifact_payload if isinstance(artifact_payload, Mapping) else {}
        late_fill = payload.get('late_fill') if isinstance(payload.get('late_fill'), Mapping) else {}
        fill_results = late_fill.get('fill_results') if isinstance(late_fill.get('fill_results'), list) else []
        terminal, contract = terminal_contracts[0]
        terminal_result = self._structured_join_fill_result_for_record(fill_results, terminal)
        terminal_status = str(terminal.get('status') or '').strip().lower()
        if not terminal_result and terminal_status not in {'completed', 'fulfilled'}:
            return []

        terminal_branch_id = str(terminal.get('branch_id') or '').strip()
        terminal_phase_id = str(terminal.get('phase_id') or '').strip()
        bindings = [
            dict(item)
            for item in (contract.get('required_bindings') or [])
            if isinstance(item, Mapping)
        ]
        required_fields = [
            str(binding.get('field_name') or '').strip()
            for binding in bindings
            if str(binding.get('field_name') or '').strip()
        ]
        base_check: dict[str, Any] = {
            'check_kind': 'structured_dependency_join',
            'phase_id': terminal_phase_id or None,
            'branch_id': terminal_branch_id or None,
            'capability': CAPABILITY_CHAT,
            'output_type': 'text',
            'role': str(terminal.get('role') or '').strip() or None,
            'depends_on': list(terminal.get('depends_on') or []),
            'stage_direction': str(terminal.get('stage_direction') or '').strip() or None,
            'content_payload_source': str(
                terminal_result.get('content_payload_source')
                or terminal.get('content_payload_source')
                or f'late_fill_result:{terminal_branch_id or terminal_phase_id}'
            ).strip(),
            'terminal_result_source': 'late_fill.fill_results',
            'structured_output_contract': contract,
            'expected_count': 1,
            'required_fields': required_fields,
        }
        issues: list[dict[str, Any]] = []

        def add_issue(code: str, reason: str, **details: Any) -> None:
            issue = {'code': code, 'reason': reason}
            issue.update(
                {
                    key: value
                    for key, value in details.items()
                    if value not in (None, '', [], {})
                }
            )
            issues.append(issue)

        if len(terminal_contracts) != 1:
            add_issue(
                'ambiguous_structured_output_contract',
                'more than one terminal exactly-one JSON object contract is active',
                contract_count=len(terminal_contracts),
            )
        if len(required_fields) != len(set(required_fields)):
            add_issue(
                'duplicate_required_binding',
                'structured output contract repeats a required JSON field binding',
                fields=required_fields,
            )

        terminal_text = self._structured_join_terminal_result_text(terminal_result)
        parsed: Any = None
        duplicate_json_keys: list[str] = []

        def reject_nonstandard_json_constant(value: str) -> Any:
            raise ValueError(f'non-standard JSON constant: {value}')

        def capture_unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            parsed_object: dict[str, Any] = {}
            for key, value in pairs:
                if key in parsed_object and key not in duplicate_json_keys:
                    duplicate_json_keys.append(key)
                parsed_object[key] = value
            return parsed_object

        if not terminal_text:
            add_issue(
                'terminal_result_missing',
                'terminal late-fill result does not contain structured result text',
            )
        else:
            try:
                parsed = json.loads(
                    terminal_text,
                    object_pairs_hook=capture_unique_json_object,
                    parse_constant=reject_nonstandard_json_constant,
                )
            except (TypeError, ValueError) as exc:
                add_issue(
                    'json_parse_error',
                    'terminal late-fill result is not exactly one standalone JSON value',
                    detail=str(exc),
                )
        if duplicate_json_keys:
            add_issue(
                'duplicate_json_key',
                'terminal JSON object contains duplicate keys',
                keys=duplicate_json_keys,
            )
        if terminal_text and not isinstance(parsed, Mapping):
            add_issue(
                'json_object_required',
                'structured output contract requires exactly one JSON object',
                actual_type=type(parsed).__name__,
            )

        parsed_object = dict(parsed) if isinstance(parsed, Mapping) else {}
        missing_fields = [field for field in required_fields if field not in parsed_object]
        invalid_fields = [
            field
            for field in required_fields
            if field in parsed_object
            and (
                not isinstance(parsed_object.get(field), str)
                or not str(parsed_object.get(field) or '').strip()
            )
        ]
        if missing_fields:
            add_issue(
                'missing_required_field',
                'terminal JSON object omits required runtime evidence bindings',
                fields=missing_fields,
            )
        if invalid_fields:
            add_issue(
                'invalid_required_field_value',
                'required runtime evidence fields must contain non-empty strings',
                fields=invalid_fields,
            )

        reference_records = self._structured_object_reference_records(
            request_payload,
            payload,
        )
        for binding in bindings:
            field_name = str(binding.get('field_name') or '').strip()
            field_role = str(binding.get('field_role') or '').strip()
            field_value = parsed_object.get(field_name) if field_name else None
            source_phase_id = str(binding.get('source_phase_id') or '').strip()
            source_branch_id = str(binding.get('source_branch_id') or '').strip()
            source_record = (
                records_by_phase.get(source_phase_id)
                or records_by_branch.get(source_branch_id)
                or {}
            )

            if field_role == 'audio_artifact_ref':
                source_result = self._structured_join_fill_result_for_record(
                    fill_results,
                    source_record,
                ) if source_record else {}
                artifact_refs = self._structured_object_source_artifact_refs(
                    source_result,
                    source_record,
                    payload,
                ) if source_result and source_record else set()
                if len(artifact_refs) != 1:
                    add_issue(
                        'artifact_ref_source_unresolved',
                        'audio artifact binding does not resolve to exactly one canonical artifact_ref',
                        field=field_name,
                        source_phase_id=source_phase_id,
                        artifact_refs=sorted(artifact_refs),
                    )
                elif isinstance(field_value, str) and field_value.strip() not in artifact_refs:
                    add_issue(
                        'artifact_ref_binding_mismatch',
                        'terminal JSON artifact_ref does not match its named producer',
                        field=field_name,
                        actual=field_value.strip(),
                        expected=next(iter(artifact_refs)),
                    )
                continue

            if field_role == 'real_transcript':
                source_result = self._structured_join_fill_result_for_record(
                    fill_results,
                    source_record,
                ) if source_record else {}
                transcript = self._structured_join_terminal_result_text(source_result)
                if not transcript:
                    add_issue(
                        'transcript_source_unresolved',
                        'transcript binding does not resolve to runtime STT evidence',
                        field=field_name,
                        source_phase_id=source_phase_id,
                    )
                elif isinstance(field_value, str) and re.sub(
                    r'\s+', ' ', field_value
                ).strip() != re.sub(r'\s+', ' ', transcript).strip():
                    add_issue(
                        'transcript_binding_mismatch',
                        'terminal JSON transcript does not match its named STT result',
                        field=field_name,
                        source_phase_id=source_phase_id,
                    )
                continue

            if field_role == 'preserved_visual_evidence':
                message_id = str(binding.get('message_id') or '').strip()
                source_response_id = str(binding.get('source_response_id') or '').strip()
                matched_messages: dict[tuple[str, str, str], Mapping[str, Any]] = {}
                for record in reference_records:
                    record_type = str(record.get('type') or record.get('kind') or '').strip().lower()
                    if record_type != 'message':
                        continue
                    if message_id and str(record.get('message_id') or '').strip() != message_id:
                        continue
                    if (
                        source_response_id
                        and str(record.get('source_response_id') or '').strip()
                        != source_response_id
                    ):
                        continue
                    content = str(record.get('content') or record.get('text') or '').strip()
                    identity = (
                        str(record.get('message_id') or '').strip(),
                        str(record.get('source_response_id') or '').strip(),
                        content,
                    )
                    matched_messages[identity] = record
                if len(matched_messages) != 1:
                    add_issue(
                        'preserved_visual_evidence_source_unresolved',
                        'preserved visual evidence does not resolve to exactly one carried message',
                        field=field_name,
                        match_count=len(matched_messages),
                    )
                else:
                    message = next(iter(matched_messages.values()))
                    bounded_evidence = _bounded_visual_evidence_from_selected_message(
                        message.get('content') or message.get('text')
                    )
                    if not bounded_evidence:
                        add_issue(
                            'preserved_visual_evidence_source_unresolved',
                            'carried message has no bounded visual-evidence section',
                            field=field_name,
                        )
                    elif isinstance(field_value, str) and re.sub(
                        r'\s+', ' ', field_value
                    ).strip() != re.sub(r'\s+', ' ', bounded_evidence).strip():
                        add_issue(
                            'preserved_visual_evidence_binding_mismatch',
                            'terminal JSON visual evidence does not equal the bounded preserved evidence',
                            field=field_name,
                        )
                continue

            if field_role == 'preserved_visual_artifact':
                artifact_ref = str(binding.get('artifact_ref') or '').strip()
                matching_artifacts = {
                    (
                        str(record.get('artifact_ref') or record.get('ref') or '').strip(),
                        str(record.get('path') or record.get('artifact_path') or '').strip(),
                        str(record.get('source_response_id') or '').strip(),
                    )
                    for record in reference_records
                    if artifact_ref
                    and str(record.get('artifact_ref') or record.get('ref') or '').strip()
                    == artifact_ref
                }
                if len(matching_artifacts) != 1:
                    add_issue(
                        'preserved_visual_artifact_source_unresolved',
                        'preserved visual artifact does not resolve to exactly one carried identity',
                        artifact_ref=artifact_ref,
                        match_count=len(matching_artifacts),
                    )

        if not issues:
            return [
                {
                    key: value
                    for key, value in {
                        **base_check,
                        'status': 'fulfilled',
                        'evidence': 'structured_object_contract_satisfied',
                        'reason': (
                            'terminal late-fill result satisfies the exactly-one JSON object '
                            'and named runtime evidence binding contract'
                        ),
                        'actual_count': 1,
                    }.items()
                    if value not in (None, '', [], {})
                }
            ]

        issue_codes = list(dict.fromkeys(str(issue.get('code') or '') for issue in issues))
        return [
            {
                key: value
                for key, value in {
                    **base_check,
                    'status': 'pending',
                    'evidence': 'structured_dependency_join_contract_unmet',
                    'reason': (
                        'terminal late-fill result violates its exactly-one JSON object '
                        f'contract: {", ".join(issue_codes)}'
                    ),
                    'actual_count': 1 if isinstance(parsed, Mapping) else 0,
                    'issue_codes': issue_codes,
                    'issues': issues,
                    'repair_required': True,
                    'repair_action': RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT,
                    'recovery_action': RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT,
                    'repair_action_reason': (
                        'terminal branch must rerun under its exact structured output and '
                        'runtime evidence binding contract'
                    ),
                    'blocked_by_branch_contract': True,
                }.items()
                if value not in (None, '', [], {})
            }
        ]

    def _structured_dependency_join_checks(
        self,
        *,
        request_payload: Optional[Mapping[str, Any]],
        artifact_payload: Optional[Mapping[str, Any]],
        request_phase_graph: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        object_contract_checks = self._structured_output_object_contract_checks(
            request_payload=request_payload,
            artifact_payload=artifact_payload,
            request_phase_graph=request_phase_graph,
        )
        if object_contract_checks:
            return object_contract_checks
        prompt = intent_coverage._current_request_prompt_for_review(
            dict(request_payload) if isinstance(request_payload, Mapping) else None,
            request_phase_graph,
        )
        contract = self._structured_dependency_join_prompt_contract(prompt)
        if not contract:
            return []
        payload = artifact_payload if isinstance(artifact_payload, Mapping) else {}
        late_fill = payload.get('late_fill') if isinstance(payload.get('late_fill'), Mapping) else {}
        fill_results = late_fill.get('fill_results') if isinstance(late_fill.get('fill_results'), list) else []
        completed_branch_ids = {
            str(item.get('branch_id') or item.get('phase_id') or '').strip()
            for item in (late_fill.get('completed_branches') or [])
            if isinstance(item, Mapping)
            and str(item.get('branch_id') or item.get('phase_id') or '').strip()
        }
        completed_phase_ids = {
            str(item.get('phase_id') or '').strip()
            for item in (late_fill.get('completed_branches') or [])
            if isinstance(item, Mapping) and str(item.get('phase_id') or '').strip()
        }

        ordered_records, records_by_phase, records_by_branch = self._structured_join_graph_records(
            request_phase_graph
        )
        terminal_candidates: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
        for index, record in enumerate(ordered_records):
            fill_result = self._structured_join_fill_result_for_record(fill_results, record)
            execution_contract = (
                fill_result.get('execution_contract')
                if isinstance(fill_result.get('execution_contract'), Mapping)
                else {}
            )
            candidate = dict(record)
            for key, value in execution_contract.items():
                if value in (None, '', [], {}):
                    continue
                if key in {
                    'branch_id',
                    'capability',
                    'depends_on',
                    'phase_id',
                    'role',
                    'stage_direction',
                } or candidate.get(key) in (None, '', [], {}):
                    candidate[key] = value
            capability = normalize_capability(candidate.get('capability'))
            role = str(candidate.get('role') or '').strip().lower()
            stage_direction = str(candidate.get('stage_direction') or '').strip().lower()
            depends_on = [
                str(item or '').strip()
                for item in (candidate.get('depends_on') or [])
                if str(item or '').strip()
            ] if isinstance(candidate.get('depends_on'), list) else []
            candidate_branch_id = str(candidate.get('branch_id') or '').strip()
            candidate_phase_id = str(candidate.get('phase_id') or '').strip()
            candidate_completed = bool(
                fill_result
                or candidate_branch_id in completed_branch_ids
                or candidate_phase_id in completed_phase_ids
                or str(candidate.get('status') or '').strip().lower() in {'completed', 'fulfilled'}
            )
            if (
                capability == CAPABILITY_CHAT
                and candidate_completed
                and len(depends_on) >= 2
                and (
                    role == 'post_artifact_text_follow_up'
                    or stage_direction == 'write_text_after_artifact_generation'
                )
            ):
                score = (
                    (4 if role == 'post_artifact_text_follow_up' else 0)
                    + (2 if stage_direction == 'write_text_after_artifact_generation' else 0)
                    + len(depends_on)
                )
                terminal_candidates.append((score * 1000 + index, candidate, fill_result))
        if not terminal_candidates:
            return []
        _score, terminal, terminal_result = max(terminal_candidates, key=lambda item: item[0])
        terminal_depends_on = [
            str(item or '').strip()
            for item in (terminal.get('depends_on') or [])
            if str(item or '').strip()
        ]

        lineages: list[dict[str, Any]] = []
        lineage_validation_issues: list[dict[str, Any]] = []
        for dependency_id in terminal_depends_on:
            consumer_record = records_by_phase.get(dependency_id) or records_by_branch.get(dependency_id)
            consumer_capability = normalize_capability(
                consumer_record.get('capability')
                if isinstance(consumer_record, Mapping)
                else None
            )
            lineage_type = _STRUCTURED_JOIN_CONSUMER_PRODUCER_TYPES.get(consumer_capability)
            direct_producer_artifact_type = _STRUCTURED_JOIN_DIRECT_PRODUCER_TYPES.get(
                consumer_capability
            )
            if (
                not isinstance(consumer_record, Mapping)
                or (not lineage_type and not direct_producer_artifact_type)
            ):
                lineage_validation_issues.append(
                    {
                        'code': 'dependency_lineage_unresolved',
                        'reason': (
                            'terminal dependency does not resolve to a supported declared '
                            'artifact-evidence consumer phase'
                        ),
                        'terminal_dependency_id': dependency_id,
                        'consumer_capability': consumer_capability or None,
                    }
                )
                lineages.append(
                    {
                        'terminal_dependency_id': dependency_id,
                        'consumer_capability': consumer_capability or None,
                        'producer_identity': '',
                        'queue_index': None,
                        'aliases': set(),
                        'path_aliases': set(),
                    }
                )
                continue
            if lineage_type:
                expected_producer_capability, producer_artifact_type = lineage_type
                consumer_dependencies = [
                    str(item or '').strip()
                    for item in (consumer_record.get('depends_on') or [])
                    if str(item or '').strip()
                ] if isinstance(consumer_record.get('depends_on'), list) else []
                producer_records = [
                    records_by_phase.get(item) or records_by_branch.get(item)
                    for item in consumer_dependencies
                ]
                producer_records = [
                    record
                    for record in producer_records
                    if isinstance(record, Mapping)
                    and normalize_capability(record.get('capability'))
                    == expected_producer_capability
                ]
                lineage_relation = 'consumer_to_producer'
            else:
                expected_producer_capability = consumer_capability
                producer_artifact_type = str(direct_producer_artifact_type or '')
                producer_records = [consumer_record]
                lineage_relation = 'direct_producer'
            if len(producer_records) != 1:
                consumer_phase_id = str(consumer_record.get('phase_id') or '').strip()
                lineage_validation_issues.append(
                    {
                        'code': (
                            'dependency_lineage_ambiguous'
                            if len(producer_records) > 1
                            else 'dependency_lineage_unresolved'
                        ),
                        'reason': (
                            'artifact-evidence consumer dependency must resolve to exactly one '
                            f'{expected_producer_capability} producer phase'
                        ),
                        'terminal_dependency_id': dependency_id,
                        'consumer_phase_id': consumer_phase_id,
                        'consumer_capability': consumer_capability,
                        'expected_producer_capability': expected_producer_capability,
                        'vision_phase_id': (
                            consumer_phase_id
                            if consumer_capability == CAPABILITY_VISION_ANALYSIS
                            else None
                        ),
                        'producer_phase_ids': [
                            str(record.get('phase_id') or record.get('branch_id') or '').strip()
                            for record in producer_records
                        ],
                    }
                )
                lineages.append(
                    {
                        'terminal_dependency_id': dependency_id,
                        'consumer_phase_id': consumer_phase_id,
                        'consumer_branch_id': str(consumer_record.get('branch_id') or '').strip(),
                        'consumer_capability': consumer_capability,
                        'expected_producer_capability': expected_producer_capability,
                        'producer_artifact_type': producer_artifact_type,
                        'lineage_relation': lineage_relation,
                        'vision_phase_id': (
                            consumer_phase_id
                            if consumer_capability == CAPABILITY_VISION_ANALYSIS
                            else None
                        ),
                        'vision_branch_id': (
                            str(consumer_record.get('branch_id') or '').strip()
                            if consumer_capability == CAPABILITY_VISION_ANALYSIS
                            else None
                        ),
                        'producer_identity': '',
                        'queue_index': None,
                        'aliases': set(),
                        'path_aliases': set(),
                    }
                )
                continue
            producer_record = dict(producer_records[0])
            producer_result = self._structured_join_fill_result_for_record(
                fill_results,
                producer_record,
            )
            producer_identity = str(
                producer_record.get('phase_id')
                or producer_record.get('branch_id')
                or dependency_id
            ).strip()
            raw_queue_index = consumer_record.get('queue_index')
            if raw_queue_index in (None, ''):
                raw_queue_index = producer_record.get('queue_index')
            branch_ordinals = {
                int(match.group('ordinal'))
                for branch_id in (
                    str(consumer_record.get('branch_id') or '').strip(),
                    str(producer_record.get('branch_id') or '').strip(),
                )
                for match in [re.search(r'(?:-|_)(?P<ordinal>[1-9][0-9]*)$', branch_id)]
                if match
            }
            queue_index = 0
            queue_index_source = ''
            if raw_queue_index not in (None, ''):
                try:
                    queue_index = int(raw_queue_index)
                except (TypeError, ValueError):
                    queue_index = 0
                queue_index_source = 'queue_index'
            elif len(branch_ordinals) == 1:
                queue_index = next(iter(branch_ordinals))
                queue_index_source = 'branch_ordinal'
            elif len(branch_ordinals) > 1:
                lineage_validation_issues.append(
                    {
                        'code': 'dependency_label_identity_ambiguous',
                        'reason': (
                            'consumer and producer branch ordinals disagree on sequential label identity'
                        ),
                        'terminal_dependency_id': dependency_id,
                        'branch_ordinals': sorted(branch_ordinals),
                    }
                )
            if (
                queue_index > 0
                and branch_ordinals
                and any(ordinal != queue_index for ordinal in branch_ordinals)
            ):
                lineage_validation_issues.append(
                    {
                        'code': 'dependency_label_identity_ambiguous',
                        'reason': (
                            'queue index conflicts with a stable producer or consumer branch ordinal'
                        ),
                        'terminal_dependency_id': dependency_id,
                        'queue_index': queue_index,
                        'branch_ordinals': sorted(branch_ordinals),
                    }
                )
            if queue_index < 1 or queue_index > len(contract['labels']):
                lineage_validation_issues.append(
                    {
                        'code': 'dependency_label_identity_unresolved',
                        'reason': (
                            'consumer/producer lineage lacks a valid queue index for sequential label identity'
                        ),
                        'terminal_dependency_id': dependency_id,
                        'consumer_phase_id': str(consumer_record.get('phase_id') or '').strip(),
                        'consumer_capability': consumer_capability,
                        'expected_producer_capability': expected_producer_capability,
                        'vision_phase_id': (
                            str(consumer_record.get('phase_id') or '').strip()
                            if consumer_capability == CAPABILITY_VISION_ANALYSIS
                            else None
                        ),
                        'producer_phase_id': str(producer_record.get('phase_id') or '').strip(),
                        'queue_index': raw_queue_index,
                    }
                )
            lineages.append(
                {
                    'terminal_dependency_id': dependency_id,
                    'consumer_phase_id': str(consumer_record.get('phase_id') or '').strip(),
                    'consumer_branch_id': str(consumer_record.get('branch_id') or '').strip(),
                    'consumer_capability': consumer_capability,
                    'expected_producer_capability': expected_producer_capability,
                    'producer_artifact_type': producer_artifact_type,
                    'lineage_relation': lineage_relation,
                    'vision_phase_id': (
                        str(consumer_record.get('phase_id') or '').strip()
                        if consumer_capability == CAPABILITY_VISION_ANALYSIS
                        else None
                    ),
                    'vision_branch_id': (
                        str(consumer_record.get('branch_id') or '').strip()
                        if consumer_capability == CAPABILITY_VISION_ANALYSIS
                        else None
                    ),
                    'producer_phase_id': str(producer_record.get('phase_id') or '').strip(),
                    'producer_branch_id': str(producer_record.get('branch_id') or '').strip(),
                    'producer_identity': producer_identity,
                    'queue_index': queue_index if queue_index > 0 else None,
                    'queue_index_source': queue_index_source or None,
                    'aliases': self._structured_join_artifact_aliases(producer_result),
                    'path_aliases': self._structured_join_artifact_path_aliases(producer_result),
                }
            )

        # Queue indexes and branch ordinals are capability-local in the phase
        # graph.  A mixed image/audio join therefore legitimately has both an
        # image producer `-1` and an audio producer `-1`.  For mixed producer
        # capabilities only, derive the cross-capability label ordinal from the
        # stable declared producer order in graph truth.  This remains
        # independent of terminal `depends_on` order and does not relax missing
        # or duplicate identity for same-capability image joins.
        producer_capabilities = {
            str(lineage.get('expected_producer_capability') or '').strip()
            for lineage in lineages
            if str(lineage.get('expected_producer_capability') or '').strip()
        }
        producer_identities = [
            str(lineage.get('producer_identity') or '').strip()
            for lineage in lineages
        ]
        if (
            len(producer_capabilities) > 1
            and len(lineages) == len(contract['labels'])
            and all(producer_identities)
            and len(set(producer_identities)) == len(producer_identities)
        ):
            producer_graph_order: dict[str, int] = {}
            for record_index, record in enumerate(ordered_records):
                for identity in (
                    str(record.get('phase_id') or '').strip(),
                    str(record.get('branch_id') or '').strip(),
                ):
                    if identity:
                        producer_graph_order.setdefault(identity, record_index)
            ordered_lineages = sorted(
                lineages,
                key=lambda lineage: producer_graph_order.get(
                    str(lineage.get('producer_identity') or '').strip(),
                    len(ordered_records),
                ),
            )
            if all(
                str(lineage.get('producer_identity') or '').strip()
                in producer_graph_order
                for lineage in ordered_lineages
            ):
                for label_ordinal, lineage in enumerate(ordered_lineages, start=1):
                    lineage['capability_queue_index'] = lineage.get('queue_index')
                    lineage['queue_index'] = label_ordinal
                    lineage['queue_index_source'] = 'stable_mixed_producer_graph_order'

        queue_index_lineages: dict[int, list[dict[str, Any]]] = {}
        for lineage in lineages:
            queue_index = lineage.get('queue_index')
            if isinstance(queue_index, int) and queue_index > 0:
                queue_index_lineages.setdefault(queue_index, []).append(lineage)
        for queue_index, matches in queue_index_lineages.items():
            if len(matches) <= 1:
                continue
            lineage_validation_issues.append(
                {
                    'code': 'dependency_label_identity_ambiguous',
                    'reason': 'multiple terminal dependencies claim the same sequential label ordinal',
                    'queue_index': queue_index,
                    'terminal_dependency_ids': [
                        str(item.get('terminal_dependency_id') or '').strip()
                        for item in matches
                    ],
                }
            )

        canonical_artifacts: list[Mapping[str, Any]] = [
            item
            for item in (payload.get('artifacts') or [])
            if isinstance(item, Mapping)
        ]
        try:
            canonical_artifacts.extend(
                item
                for item in self.build_canonical_response_artifacts(dict(payload))
                if isinstance(item, Mapping)
            )
        except Exception:
            logging.getLogger(__name__).debug(
                'failed to build canonical artifacts for structured dependency join review',
                exc_info=True,
            )
        for lineage in lineages:
            seed_aliases = set(lineage['aliases'])
            seed_path_aliases = set(lineage.get('path_aliases') or set())
            producer_artifact_type = str(
                lineage.get('producer_artifact_type') or ''
            ).strip().lower()
            for artifact in canonical_artifacts:
                if not self._structured_join_artifact_matches_type(
                    artifact,
                    producer_artifact_type,
                ):
                    continue
                artifact_status = str(
                    artifact.get('artifact_status')
                    or artifact.get('lifecycle_state')
                    or artifact.get('status')
                    or ''
                ).strip().lower()
                if artifact_status and artifact_status not in {
                    'available',
                    'completed',
                    'fulfilled',
                    'materialized',
                    'ready',
                }:
                    continue
                artifact_aliases = self._structured_join_artifact_aliases(artifact)
                artifact_path_aliases = self._structured_join_artifact_path_aliases(artifact)
                aliases_match_current_fill = bool(
                    seed_path_aliases.intersection(artifact_path_aliases)
                    if seed_path_aliases
                    else seed_aliases.intersection(artifact_aliases)
                )
                if aliases_match_current_fill:
                    lineage['aliases'].update(artifact_aliases)
                    lineage['path_aliases'].update(artifact_path_aliases)

        alias_to_producers: dict[str, set[str]] = {}
        for lineage in lineages:
            producer_identity = str(lineage.get('producer_identity') or '').strip()
            for alias in lineage.get('aliases') or set():
                alias_to_producers.setdefault(alias, set()).add(producer_identity)

        expected_labels = list(contract['labels'])
        required_fields = list(contract['required_fields'])
        label_field = str(contract['label_field'])
        artifact_ref_field = str(contract['artifact_ref_field'])
        terminal_branch_id = str(terminal.get('branch_id') or terminal_result.get('branch_id') or '').strip()
        terminal_phase_id = str(terminal.get('phase_id') or terminal_result.get('phase_id') or '').strip()
        execution_contract = (
            terminal_result.get('execution_contract')
            if isinstance(terminal_result.get('execution_contract'), Mapping)
            else {}
        )
        base_check: dict[str, Any] = {
            'check_kind': 'structured_dependency_join',
            'phase_id': terminal_phase_id or None,
            'branch_id': terminal_branch_id or None,
            'capability': CAPABILITY_CHAT,
            'output_type': 'text',
            'role': str(terminal.get('role') or '').strip() or None,
            'depends_on': terminal_depends_on,
            'stage_direction': str(terminal.get('stage_direction') or '').strip() or None,
            'content_payload_source': str(
                execution_contract.get('content_payload_source')
                or terminal.get('content_payload_source')
                or f'late_fill_result:{terminal_branch_id or terminal_phase_id}'
            ).strip(),
            'terminal_result_source': 'late_fill.fill_results',
            'expected_count': len(expected_labels),
            'expected_labels': expected_labels,
            'required_fields': required_fields,
            'label_field': label_field,
            'artifact_ref_field': artifact_ref_field,
            'execution_contract': dict(execution_contract) if execution_contract else None,
        }
        issues: list[dict[str, Any]] = [
            dict(item) for item in lineage_validation_issues
        ]

        def add_issue(code: str, reason: str, **details: Any) -> None:
            issue = {'code': code, 'reason': reason}
            issue.update(
                {
                    key: value
                    for key, value in details.items()
                    if value not in (None, '', [], {})
                }
            )
            issues.append(issue)

        if len(expected_labels) != len(lineages):
            add_issue(
                'dependency_label_count_mismatch',
                'explicit labels do not map one-to-one to terminal dependencies',
                dependency_count=len(lineages),
                label_count=len(expected_labels),
            )

        terminal_text = self._structured_join_terminal_result_text(terminal_result)
        parsed: Any = None
        parsed_successfully = False
        duplicate_json_keys: list[str] = []

        def reject_nonstandard_json_constant(value: str) -> Any:
            raise ValueError(f'non-standard JSON constant: {value}')

        def capture_unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            payload_object: dict[str, Any] = {}
            for key, value in pairs:
                if key in payload_object and key not in duplicate_json_keys:
                    duplicate_json_keys.append(key)
                payload_object[key] = value
            return payload_object

        if not terminal_text:
            add_issue(
                'terminal_result_missing',
                'terminal late-fill result does not contain structured result text',
            )
        else:
            try:
                parsed = json.loads(
                    _strip_fenced_json_boundary(terminal_text),
                    object_pairs_hook=capture_unique_json_object,
                    parse_constant=reject_nonstandard_json_constant,
                )
                parsed_successfully = True
            except (TypeError, ValueError) as exc:
                add_issue(
                    'json_parse_error',
                    'terminal late-fill result is not valid JSON or a fenced JSON payload',
                    detail=str(exc),
                )
        if duplicate_json_keys:
            add_issue(
                'duplicate_json_key',
                'terminal JSON contains duplicate object keys with ambiguous last-value semantics',
                keys=duplicate_json_keys,
            )
        if parsed_successfully and not isinstance(parsed, list):
            add_issue(
                'json_list_required',
                'explicit current-turn contract requires a JSON list',
                actual_type=type(parsed).__name__,
            )
            parsed = None

        rows = parsed if isinstance(parsed, list) else []
        if isinstance(parsed, list) and len(rows) != len(expected_labels):
            add_issue(
                'exact_count_mismatch',
                'terminal JSON list does not have exactly one row per requested label',
                actual_count=len(rows),
                expected_count=len(expected_labels),
            )
        row_objects: list[tuple[int, Mapping[str, Any]]] = []
        invalid_row_indexes: list[int] = []
        missing_fields: list[dict[str, Any]] = []
        invalid_fields: list[dict[str, Any]] = []
        unexpected_fields: list[dict[str, Any]] = []

        def required_field_value_is_valid(field: str, value: Any) -> bool:
            if value is None or isinstance(value, (Mapping, list, tuple, set)):
                return False
            normalized_field = str(field or '').strip().lower()
            requires_text_value = bool(
                normalized_field == 'label'
                or normalized_field in _STRUCTURED_JOIN_ARTIFACT_REF_FIELDS
                or normalized_field == 'evidence'
                or normalized_field.endswith('_evidence')
            )
            if requires_text_value and not isinstance(value, str):
                return False
            if isinstance(value, str):
                return bool(value.strip())
            return True

        for index, row in enumerate(rows):
            if not isinstance(row, Mapping):
                invalid_row_indexes.append(index)
                continue
            row_objects.append((index, row))
            missing = [
                field
                for field in required_fields
                if field not in row
            ]
            if missing:
                missing_fields.append({'row_index': index, 'fields': missing})
            invalid = [
                field
                for field in required_fields
                if field in row and not required_field_value_is_valid(field, row.get(field))
            ]
            if invalid:
                invalid_fields.append({'row_index': index, 'fields': invalid})
            unexpected = [
                str(field)
                for field in row
                if str(field) not in required_fields
            ]
            if unexpected:
                unexpected_fields.append({'row_index': index, 'fields': unexpected})
        if invalid_row_indexes:
            add_issue(
                'item_not_object',
                'each structured terminal join item must be a JSON object',
                row_indexes=invalid_row_indexes,
            )
        if missing_fields:
            add_issue(
                'missing_required_field',
                'one or more terminal join rows omit requested fields',
                rows=missing_fields,
            )
        if invalid_fields:
            add_issue(
                'invalid_required_field_value',
                'one or more requested fields contain empty, non-scalar, or invalid values',
                rows=invalid_fields,
            )
        if unexpected_fields:
            add_issue(
                'unexpected_field',
                'terminal join rows contain fields outside the explicit current-turn contract',
                rows=unexpected_fields,
            )

        labels_by_value: dict[str, list[int]] = {}
        for row_index, row in row_objects:
            value = str(row.get(label_field) or '').strip()
            if value:
                labels_by_value.setdefault(value, []).append(row_index)
        duplicate_labels = {
            label: indexes
            for label, indexes in labels_by_value.items()
            if len(indexes) > 1
        }
        if duplicate_labels:
            add_issue(
                'duplicate_label',
                'requested labels must occur exactly once',
                labels=duplicate_labels,
            )
        missing_labels = [label for label in expected_labels if label not in labels_by_value]
        if missing_labels:
            add_issue(
                'missing_label',
                'one or more requested labels are absent from the terminal join',
                labels=missing_labels,
            )
        unexpected_labels = [
            label for label in labels_by_value
            if label not in expected_labels
        ]
        if unexpected_labels:
            add_issue(
                'unexpected_label',
                'terminal join contains labels outside the explicit current-turn contract',
                labels=unexpected_labels,
            )

        resolved_ref_rows: dict[tuple[str, str], list[int]] = {}
        row_ref_resolution: dict[int, set[str]] = {}
        for row_index, row in row_objects:
            raw_ref = str(row.get(artifact_ref_field) or '').strip()
            if not raw_ref:
                continue
            aliases = self._structured_join_alias_tokens(raw_ref)
            resolved = {
                producer
                for alias in aliases
                for producer in alias_to_producers.get(alias, set())
            }
            row_ref_resolution[row_index] = resolved
            if len(resolved) == 1:
                ref_key = ('producer', next(iter(resolved)))
            else:
                ref_key = ('artifact_ref', min(aliases) if aliases else raw_ref)
            resolved_ref_rows.setdefault(ref_key, []).append(row_index)
        duplicate_refs = [
            {
                'resolved_kind': ref_key[0],
                'resolved_value': ref_key[1],
                'row_indexes': indexes,
            }
            for ref_key, indexes in resolved_ref_rows.items()
            if len(indexes) > 1
        ]
        if duplicate_refs:
            add_issue(
                'duplicate_artifact_ref',
                'artifact refs or paths must resolve one-to-one across terminal join rows',
                duplicates=duplicate_refs,
            )

        producer_for_label: dict[str, str] = {}
        for queue_index, label in enumerate(expected_labels, start=1):
            matches = queue_index_lineages.get(queue_index) or []
            if len(matches) != 1:
                continue
            producer_identity = str(matches[0].get('producer_identity') or '').strip()
            if producer_identity:
                producer_for_label[label] = producer_identity
        label_ref_mismatches: list[dict[str, Any]] = []
        for row_index, row in row_objects:
            label = str(row.get(label_field) or '').strip()
            raw_ref = str(row.get(artifact_ref_field) or '').strip()
            expected_producer = producer_for_label.get(label)
            if not label or not raw_ref or not expected_producer:
                continue
            resolved = row_ref_resolution.get(row_index, set())
            if resolved != {expected_producer}:
                label_ref_mismatches.append(
                    {
                        'row_index': row_index,
                        'label': label,
                        'artifact_ref': raw_ref,
                        'expected_producer': expected_producer,
                        'resolved_producers': sorted(resolved),
                    }
                )
        if label_ref_mismatches:
            add_issue(
                'label_ref_dependency_mismatch',
                'label/artifact mapping does not match terminal dependency to vision to producer lineage',
                rows=label_ref_mismatches,
            )

        if not issues:
            return [
                {
                    key: value
                    for key, value in {
                        **base_check,
                        'status': 'fulfilled',
                        'evidence': 'structured_join_contract_satisfied',
                        'reason': (
                            'terminal late-fill result satisfies the explicit structured '
                            'dependency join contract'
                        ),
                        'actual_count': len(rows),
                    }.items()
                    if value not in (None, '', [], {})
                }
            ]

        issue_codes = list(dict.fromkeys(str(issue.get('code') or '') for issue in issues))
        identity_issue_codes = {
            'duplicate_artifact_ref',
            'label_ref_dependency_mismatch',
        }
        repair_action = (
            RECOVERY_ACTION_REBIND_DEPENDENCY_EVIDENCE
            if issue_codes and set(issue_codes).issubset(identity_issue_codes)
            else RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT
        )
        pending_check = {
            **base_check,
            'status': 'pending',
            'evidence': 'structured_dependency_join_contract_unmet',
            'reason': (
                'terminal late-fill result violates the explicit structured dependency '
                f'join contract: {", ".join(issue_codes)}'
            ),
            'actual_count': len(rows) if isinstance(parsed, list) else None,
            'issue_codes': issue_codes,
            'issues': issues,
            'repair_required': True,
            'repair_action': repair_action,
            'recovery_action': repair_action,
            'repair_action_reason': (
                'terminal artifact identities must be rebound to declared dependency lineage'
                if repair_action == RECOVERY_ACTION_REBIND_DEPENDENCY_EVIDENCE
                else 'terminal branch must rerun under its explicit structured output contract'
            ),
            'blocked_by_dependency_input': (
                repair_action == RECOVERY_ACTION_REBIND_DEPENDENCY_EVIDENCE
            ),
            'blocked_by_branch_contract': (
                repair_action == RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT
            ),
        }
        return [
            {
                key: value
                for key, value in pending_check.items()
                if value not in (None, '', [], {})
            }
        ]

