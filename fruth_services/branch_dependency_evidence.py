"""Bind accepted producer results and selected references to branch-local inputs.

Saved bytes are read only through the existing scoped artifact reader. Exact
producer/consumer identities and content-review packets remain binding. The
owner neither routes or dispatches work nor publishes or closes a response.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from fruth_services import branch_result_contracts
from fruth_services.state_flow import observe_state
from fruth_services.artifact_contracts import (
    read_saved_file_snapshot,
    saved_file_dependency_contract,
    saved_file_read_text,
    saved_file_read_issue,
    saved_file_consumption_issue,
    separate_image_report_contract,
    assemble_separate_image_reports,
    render_separate_image_reports,
)
import logging
import re
from typing import Any, Mapping, Optional
from fruth_server.recovery_contract import (
    RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT,
    RECOVERY_ACTION_REPAIR_DEPENDENCY_CHAIN,
)
from fruth_services.structured_dependency_review import _bounded_visual_evidence_from_selected_message as _extract_bounded_visual_evidence_from_selected_message
from fruth_services.phase_output import control_json_envelope_suspected
from fruth_services.responses import (
    extract_responses_current_turn_prompt,
    has_captured_request_intent,
)


_BRANCH_LOCAL_STRUCTURED_JOIN_RE = re.compile(
    r'\bjson\s*(?:[-_/]\s*|\s+)(?:list(?:e)?|array)\b',
    re.IGNORECASE,
)


_BRANCH_LOCAL_ARTIFACT_IDENTITY_FIELD_RE = re.compile(
    r'\b(?:artifact_ref|artifact\s+(?:ref(?:erence)?|path)|'
    r'artefakt[_\s-]*(?:ref(?:erenz)?|pfad))\b',
    re.IGNORECASE,
)

@dataclass(frozen=True)
class BranchDependencyEvidence:
    artifact_type_for_capability: Callable[[Any], Optional[str]]
    branch_capability: Callable[[Any], str]
    build_canonical_response_artifacts: Callable[..., list[dict[str, Any]]]
    image_generation_capability: Callable[[], str]
    text_to_speech_capability: Callable[[], str]
    normalize_capability: Callable[[Any], Optional[str]]
    resolve_saved_file_input_path: Callable[[str], Any]

    def _branch_has_current_turn_direct_media_payload(
        self,
        branch: Mapping[str, Any],
    ) -> bool:
        dependencies = {
            str(item or '').strip()
            for item in (branch.get('depends_on') or [])
            if str(item or '').strip()
        }
        if dependencies != {'phase-1'}:
            return False
        capability = self.branch_capability(branch)
        if capability == self.text_to_speech_capability():
            return bool(
                str(branch.get('content_payload') or '').strip()
                and str(branch.get('content_payload_source') or '').strip()
                == 'current_turn_direct_spoken_clause'
            )
        if capability == self.image_generation_capability():
            return bool(
                str(branch.get('artifact_prompt') or '').strip()
                and str(branch.get('artifact_prompt_source') or '').strip()
                == 'current_turn_direct_image_clause'
            )
        return False

    @staticmethod
    def _content_review_binding(payload: Mapping[str, Any]) -> dict[str, Any]:
        """The existing review contract carries this opt-in admission policy."""
        contract = payload.get('execution_contract') if isinstance(payload.get('execution_contract'), Mapping) else {}
        for source in (payload, contract):
            review = source.get('branch_semantic_review') if isinstance(source.get('branch_semantic_review'), Mapping) else {}
            binding = source.get('semantic_review_evidence_binding') or review.get('semantic_review_evidence_binding') or {}
            if isinstance(binding, Mapping) and binding.get('content_requirement_policy') == 'named_saved_text_v1':
                return dict(binding)
        return {}

    @staticmethod
    def _request_payload_prompt_text(payload: Any) -> str:
        if not isinstance(payload, Mapping):
            return ''
        if has_captured_request_intent(payload):
            return extract_responses_current_turn_prompt(dict(payload))
        for key in ('prompt', 'input_text'):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        value = payload.get('input')
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if not isinstance(item, Mapping):
                    if str(item or '').strip():
                        parts.append(str(item).strip())
                    continue
                content = item.get('content')
                if isinstance(content, str):
                    parts.append(content.strip())
                elif isinstance(content, list):
                    for content_item in content:
                        if isinstance(content_item, Mapping):
                            text = str(content_item.get('text') or '').strip()
                            if text:
                                parts.append(text)
                        elif str(content_item or '').strip():
                            parts.append(str(content_item).strip())
            return '\n\n'.join(part for part in parts if part).strip()
        return ''

    @staticmethod
    def _artifact_evidence_text(result: Mapping[str, Any]) -> str:
        artifacts = result.get('artifacts') if isinstance(result.get('artifacts'), list) else []

        def _matching_artifact(path: str) -> Mapping[str, Any]:
            exact = next(
                (
                    artifact
                    for artifact in artifacts
                    if isinstance(artifact, Mapping)
                    and str(artifact.get('path') or artifact.get('source_path') or '').strip()
                    == path
                ),
                None,
            )
            if isinstance(exact, Mapping):
                return exact
            return next(
                (artifact for artifact in artifacts if isinstance(artifact, Mapping)),
                {},
            )

        def _evidence(label: str, path: str, artifact: Mapping[str, Any]) -> str:
            artifact_ref = str(
                artifact.get('artifact_ref')
                or artifact.get('ref')
                or result.get('artifact_ref')
                or result.get('ref')
                or ''
            ).strip()
            lines = [f'{label}: {path}']
            if artifact_ref:
                lines.append(f'artifact_ref: {artifact_ref}')
            return '\n'.join(lines)

        for key, label in (
            ('saved_image_path', 'image artifact'),
            ('saved_audio_path', 'audio artifact'),
            ('saved_text_path', 'text artifact'),
        ):
            value = str(result.get(key) or '').strip()
            if value:
                return _evidence(label, value, _matching_artifact(value))
        for artifact in artifacts:
            if not isinstance(artifact, Mapping):
                continue
            path = str(artifact.get('path') or artifact.get('source_path') or '').strip()
            artifact_type = str(artifact.get('type') or artifact.get('kind') or 'artifact').strip()
            if path:
                return _evidence(f'{artifact_type} artifact', path, artifact)
        return ''

    @staticmethod
    def _branch_local_vision_requires_identity_handoff(original_prompt: str) -> bool:
        prompt_text = str(original_prompt or '')
        return bool(
            _BRANCH_LOCAL_STRUCTURED_JOIN_RE.search(prompt_text)
            and _BRANCH_LOCAL_ARTIFACT_IDENTITY_FIELD_RE.search(prompt_text)
        )

    def _dependency_result_artifact_identity_evidence(
        self,
        result: Mapping[str, Any],
        *,
        fill_results: list[Any],
        current_payload: Mapping[str, Any],
    ) -> str:
        """Carry producer identity through an evidence consumer into a terminal join."""

        consumer_capability = self.normalize_capability(result.get('capability'))
        expected_producer_capability = {
            'vision_analysis': self.image_generation_capability(),
            'speech_to_text': self.text_to_speech_capability(),
        }.get(consumer_capability)
        if not expected_producer_capability:
            return ''

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
        graph_records = [
            item
            for key in ('phases', 'downstream_branches')
            for item in (phase_graph.get(key) if isinstance(phase_graph.get(key), list) else [])
            if isinstance(item, Mapping)
        ]
        result_tokens = {
            str(result.get('phase_id') or '').strip(),
            str(result.get('branch_id') or '').strip(),
        }
        consumer_record = next(
            (
                item
                for item in graph_records
                if result_tokens.intersection(
                    {
                        str(item.get('phase_id') or '').strip(),
                        str(item.get('branch_id') or '').strip(),
                    }
                )
            ),
            {},
        )
        execution_contract = (
            result.get('execution_contract')
            if isinstance(result.get('execution_contract'), Mapping)
            else {}
        )
        dependency_ids: list[str] = []
        for raw_values in (
            result.get('depends_on'),
            execution_contract.get('depends_on'),
            consumer_record.get('depends_on') if isinstance(consumer_record, Mapping) else None,
        ):
            if not isinstance(raw_values, list):
                continue
            for value in raw_values:
                token = str(value or '').strip()
                if token and token not in dependency_ids:
                    dependency_ids.append(token)
        if not dependency_ids:
            return ''

        producer_results = [
            item
            for item in fill_results
            if isinstance(item, Mapping)
            and self.normalize_capability(item.get('capability'))
            == expected_producer_capability
            and {
                str(item.get('phase_id') or '').strip(),
                str(item.get('branch_id') or '').strip(),
            }.intersection(dependency_ids)
        ]
        if len(producer_results) != 1:
            return ''
        producer_result = producer_results[0]
        producer_artifacts = branch_result_contracts._artifact_records_from_late_fill_result(producer_result)
        if not producer_artifacts:
            return ''

        canonical_artifacts: list[Mapping[str, Any]] = []
        try:
            canonical_artifacts = [
                item
                for item in self.build_canonical_response_artifacts(dict(current_payload))
                if isinstance(item, Mapping)
            ]
        except Exception:
            logging.getLogger(__name__).debug(
                'failed to build canonical artifacts for dependency identity evidence',
                exc_info=True,
            )
        evidence_blocks: list[str] = []
        producer_phase_id = str(producer_result.get('phase_id') or '').strip()
        producer_branch_id = str(producer_result.get('branch_id') or '').strip()
        for artifact in producer_artifacts:
            path = branch_result_contracts._artifact_record_path(artifact)
            if not path:
                continue
            canonical = next(
                (
                    item
                    for item in canonical_artifacts
                    if branch_result_contracts._artifact_record_path(item) == path
                ),
                {},
            )
            artifact_ref = str(
                canonical.get('artifact_ref')
                or canonical.get('ref')
                or artifact.get('artifact_ref')
                or artifact.get('ref')
                or ''
            ).strip()
            lines = [
                'Branch dependency artifact identity (runtime evidence):',
                f'- producer_phase_id: {producer_phase_id}' if producer_phase_id else '',
                f'- producer_branch_id: {producer_branch_id}' if producer_branch_id else '',
                f'- artifact_ref: {artifact_ref}' if artifact_ref else '',
                f'- artifact_path: {path}',
            ]
            block = '\n'.join(line for line in lines if line)
            if block and block not in evidence_blocks:
                evidence_blocks.append(block)
        return '\n\n'.join(evidence_blocks).strip()

    @staticmethod
    def _bounded_visual_evidence_from_selected_message(content: Any) -> str:
        """Extract only preserved visual evidence from a carried message."""
        return _extract_bounded_visual_evidence_from_selected_message(content)

    @staticmethod
    def _selected_reference_records_from_payload(
        current_payload: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        sources = [current_payload]
        request = current_payload.get('request')
        if isinstance(request, Mapping):
            sources.append(request)
        for source in sources:
            for key in (
                'selected_reference_artifacts',
                'selectedReferenceArtifacts',
                'reference_artifacts',
                'input_artifacts',
            ):
                for item in source.get(key) or []:
                    if isinstance(item, Mapping) and dict(item) not in records:
                        records.append(dict(item))
        return records

    @classmethod
    def _selected_reference_dependency_payload(
        cls,
        branch: Mapping[str, Any],
        *,
        current_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        selected_refs = [
            dict(item)
            for item in (branch.get('input_refs') or [])
            if isinstance(item, Mapping)
            and str(item.get('kind') or '').strip()
            in {
                'selected_reference',
                'selected_reference_artifact',
                'selected_reference_evidence',
            }
        ]
        if not selected_refs:
            return {}
        available = cls._selected_reference_records_from_payload(current_payload)
        evidence_blocks: list[str] = []
        reference_artifacts: list[dict[str, Any]] = []
        for selected in selected_refs:
            selected_kind = str(selected.get('kind') or '').strip()
            selected_role = str(selected.get('role') or '').strip()
            is_artifact_reference = (
                selected_kind == 'selected_reference_artifact'
                or selected_role == 'preserved_visual_artifact'
            )
            match_keys = (
                ('artifact_ref', 'ref', 'path')
                if is_artifact_reference
                else ('message_id', 'source_response_id')
            )
            authoritative_values = {
                key: str(selected.get(key) or '').strip()
                for key in match_keys
                if str(selected.get(key) or '').strip()
            }
            if not authoritative_values:
                return {
                    'branch_contract_error': 'selected_reference_unavailable',
                    'materialization_blocked': True,
                    'repair_action': RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT,
                }
            matches: list[dict[str, Any]] = []
            matched_identities: set[tuple[str, ...]] = set()
            for record in available:
                record_ref = str(record.get('artifact_ref') or record.get('ref') or '').strip()
                record_values = {
                    'artifact_ref': record_ref,
                    'ref': record_ref,
                    'path': str(record.get('path') or record.get('artifact_path') or '').strip(),
                    'message_id': str(record.get('message_id') or '').strip(),
                    'source_response_id': str(record.get('source_response_id') or '').strip(),
                }
                if all(record_values.get(key) == value for key, value in authoritative_values.items()):
                    if is_artifact_reference:
                        identity = (
                            'artifact',
                            record_ref,
                            record_values['path'],
                            str(record.get('type') or record.get('kind') or '').strip().lower(),
                            str(record.get('source_response_id') or '').strip(),
                            str(
                                record.get('source_message_id')
                                or record.get('message_id')
                                or ''
                            ).strip(),
                        )
                    else:
                        identity = (
                            'message',
                            record_values['message_id'],
                            record_values['source_response_id'],
                            str(record.get('content') or record.get('text') or '').strip(),
                        )
                    if identity not in matched_identities:
                        matched_identities.add(identity)
                        matches.append(record)
            if len(matches) != 1:
                return {
                    'branch_contract_error': (
                        'selected_reference_unavailable'
                        if not matches
                        else 'selected_reference_ambiguous'
                    ),
                    'materialization_blocked': True,
                    'repair_action': RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT,
                }
            record = matches[0]
            if is_artifact_reference:
                artifact_ref = str(
                    record.get('artifact_ref') or record.get('ref') or ''
                ).strip()
                path = str(record.get('path') or record.get('artifact_path') or '').strip()
                artifact = {
                    key: value
                    for key, value in {
                        'type': record.get('type') or record.get('kind'),
                        'kind': record.get('kind') or record.get('type'),
                        'artifact_ref': artifact_ref or None,
                        'ref': artifact_ref or None,
                        'path': path or None,
                        'source_response_id': record.get('source_response_id'),
                        'source_message_id': record.get('source_message_id') or record.get('message_id'),
                    }.items()
                    if value not in (None, '')
                }
                reference_artifacts.append(artifact)
                evidence_blocks.append(
                    '\n'.join(
                        line
                        for line in (
                            'Selected preserved visual artifact (runtime-bound; do not regenerate):',
                            f'- artifact_ref: {artifact_ref}' if artifact_ref else '',
                            f'- artifact_path: {path}' if path else '',
                        )
                        if line
                    )
                )
                continue
            visual_evidence = cls._bounded_visual_evidence_from_selected_message(
                record.get('content') or record.get('text')
            )
            if not visual_evidence:
                return {
                    'branch_contract_error': 'selected_reference_evidence_unavailable',
                    'materialization_blocked': True,
                    'repair_action': RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT,
                }
            evidence_blocks.append(
                'Selected preserved visual evidence (runtime-bound; do not reanalyze):\n'
                + visual_evidence
            )
        return {
            'evidence_blocks': evidence_blocks,
            'reference_artifacts': reference_artifacts,
            'selected_reference_evidence_bound': True,
        }

    def _saved_file_dependency_payload(self, branch, current_payload):
        contract = saved_file_dependency_contract(branch)
        try:
            if (any(branch.get(key) != contract.get('consumer_' + key)
                    for key in ('branch_id', 'phase_id'))
                    or branch.get('depends_on') != [contract.get('producer_phase_id')]):
                raise ValueError('saved_file_read_consumer_contract_mismatch')
            results = (current_payload.get('late_fill') or {}).get('fill_results') or []
            producers = [r for r in results if isinstance(r, Mapping)
                and r.get('branch_id') == contract['producer_branch_id']
                and r.get('phase_id') == contract['producer_phase_id']]
            if len(producers) != 1:
                raise ValueError('saved_file_read_producer_missing_or_ambiguous')
            snapshot = producers[0].get('saved_file_output_snapshot') or {}
            if not snapshot.get('sha256'):
                raise ValueError('saved_file_read_saved_version_missing')
            read = read_saved_file_snapshot(snapshot['path'], self.resolve_saved_file_input_path)
            read.update({key: snapshot.get(key) for key in
                ('artifact_ref', 'artifact_id', 'source_response_id', 'branch_id', 'phase_id')})
            read.update({key: contract[key] for key in
                ('producer_branch_id', 'producer_phase_id', 'consumer_branch_id', 'consumer_phase_id')})
            read['response_id'] = current_payload.get('id')
            issue = saved_file_read_issue(contract, read, current_payload)
            if issue:
                raise ValueError(issue)
            return {'saved_file_read_evidence': read,
                    'content_payload': saved_file_read_text(read), 'content_payload_source': 'saved_file_read',
                    'input_refs': [{'kind': 'saved_file_read', **{key: value for key, value in read.items() if key != 'utf8_base64'}}],
                    'suppress_reference_file_context': True}
        except (OSError, ValueError, KeyError, TypeError, AttributeError, UnicodeError) as exc:
            return {'branch_contract_error': str(exc), 'materialization_blocked': True,
                    'repair_action': RECOVERY_ACTION_REPAIR_DEPENDENCY_CHAIN}

    def saved_file_consumption_error(self, branch, infer_result, *, current_payload):
        issue = saved_file_consumption_issue(branch, infer_result, current_payload or {})
        if issue:
            return {'code': 'DEPENDENCY_CHAIN_REPAIR_REQUIRED', 'reason_code': issue,
                    'message': issue, 'stage': 'saved_file_evidence_gate', 'retryable': False,
                    'materialization_blocked': True}
        return None

    @observe_state('late_fill.dependency_binding', 'saved_dependency_evidence', 'bound_branch_dependency', labels=('NEW_AUTHORITY_BOUNDARY',), new_authority_boundary=True)
    def branch_dependency_payload(
        self,
        branch: Mapping[str, Any],
        *,
        current_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        if self._content_review_binding(branch):
            # Closure already gathered the exact source/output packet. Replacing
            # it with a dependency's answer would remove the review task itself.
            return {'dependency_payload_policy': 'preserve_bound_content_review_packet'}
        if separate_image_report_contract(branch):
            try:
                evidence = assemble_separate_image_reports(branch, current_payload, self.resolve_saved_file_input_path)
                return {'content_payload': render_separate_image_reports(evidence),
                        'content_payload_source': 'prior_artifact_result',
                        'dependency_payload_policy': 'deliver_accepted_separate_image_reports'}
            except (OSError, AttributeError, KeyError, TypeError, ValueError, UnicodeError) as exc:
                return {'branch_contract_error': str(exc), 'materialization_blocked': True,
                        'repair_action': RECOVERY_ACTION_REPAIR_DEPENDENCY_CHAIN}
        if saved_file_dependency_contract(branch):
            return self._saved_file_dependency_payload(branch, current_payload)
        depends_on = [
            str(item or '').strip()
            for item in (branch.get('depends_on') or [])
            if str(item or '').strip()
        ]
        selected_reference_payload = self._selected_reference_dependency_payload(
            branch,
            current_payload=current_payload,
        )
        if selected_reference_payload.get('branch_contract_error'):
            return selected_reference_payload
        if self._branch_has_current_turn_direct_media_payload(branch):
            return {
                'dependency_payload_policy': (
                    'preserve_current_turn_direct_media_payload'
                )
            }
        if not depends_on and not selected_reference_payload:
            return {}
        target_capability = self.normalize_capability(branch.get('capability'))
        runtime_payload = (
            current_payload.get('runtime')
            if isinstance(current_payload.get('runtime'), Mapping)
            else {}
        )
        phase_graph_payload = (
            runtime_payload.get('request_phase_graph')
            if isinstance(runtime_payload.get('request_phase_graph'), Mapping)
            else {}
        )
        request_payload = (
            current_payload.get('request')
            if isinstance(current_payload.get('request'), Mapping)
            else {}
        )
        identity_handoff_prompt = str(
            phase_graph_payload.get('prompt')
            or self._request_payload_prompt_text(request_payload)
            or self._request_payload_prompt_text(current_payload)
            or ''
        ).strip()
        structured_identity_handoff = bool(
            target_capability == 'chat'
            and self._branch_local_vision_requires_identity_handoff(
                identity_handoff_prompt
            )
        )
        matched_result_payloads: list[tuple[str, str]] = [
            ('selected_reference', block)
            for block in (selected_reference_payload.get('evidence_blocks') or [])
            if str(block or '').strip()
        ]
        if 'phase-1' in depends_on:
            output_text = str((current_payload or {}).get('output_text') or '').strip()
            if output_text:
                if control_json_envelope_suspected(output_text):
                    return {
                        'branch_contract_error': 'control_envelope_not_speakable',
                        'materialization_blocked': True,
                        'repair_action': RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT,
                        'content_payload_source': 'rejected_current_phase_output',
                    }
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
                current_capability = self.normalize_capability(
                    phase_graph.get('current_phase_capability')
                )
                declared_source = str(branch.get('content_payload_source') or '').strip()
                if current_capability and current_capability != 'chat':
                    allowed_sources = {
                        'current_phase_output',
                        f'{current_capability}_branch_result',
                    }
                    if current_capability == 'speech_to_text':
                        allowed_sources.add('speech_to_text_branch_result')
                    if declared_source not in allowed_sources:
                        output_text = ''
                if output_text:
                    if len(depends_on) == 1:
                        return {
                            'content_payload': output_text,
                            'content_payload_source': 'current_phase_output',
                        }
                    matched_result_payloads.append(('phase-1', output_text))
        late_fill = (
            current_payload.get('late_fill')
            if isinstance(current_payload.get('late_fill'), Mapping)
            else {}
        )
        fill_results = (
            late_fill.get('fill_results')
            if isinstance(late_fill.get('fill_results'), list)
            else []
        )
        dependency_input_artifacts: list[dict[str, Any]] = []
        for result in fill_results:
            if not isinstance(result, Mapping):
                continue
            result_tokens = {
                str(result.get('branch_id') or '').strip(),
                str(result.get('phase_id') or '').strip(),
            }
            if not any(token and token in depends_on for token in result_tokens):
                continue
            if branch_result_contracts.late_fill_result_has_missing_dependency_evidence(result):
                continue
            result_id = str(result.get('branch_id') or result.get('phase_id') or '').strip()
            if target_capability in {'vision_analysis', 'speech_to_text'}:
                for artifact in branch_result_contracts._artifact_records_from_late_fill_result(result):
                    artifact_type = str(artifact.get('type') or artifact.get('kind') or '').strip().lower()
                    if (
                        target_capability == 'vision_analysis'
                        and artifact_type in {'image', 'png', 'jpg', 'jpeg', 'webp'}
                    ) or (
                        target_capability == 'speech_to_text'
                        and artifact_type in {'audio', 'wav', 'mp3', 'm4a', 'flac', 'aac', 'ogg', 'opus'}
                    ):
                        dependency_input_artifacts.append(artifact)
            result_text = branch_result_contracts.late_fill_text_from_result_payload(result)
            if result_text:
                if structured_identity_handoff:
                    identity_evidence = self._dependency_result_artifact_identity_evidence(
                        result,
                        fill_results=fill_results,
                        current_payload=current_payload,
                    )
                    if identity_evidence:
                        result_text = f'{result_text}\n\n{identity_evidence}'.strip()
                matched_result_payloads.append(
                    (
                        result_id,
                        result_text,
                    )
                )
                continue
            artifact_evidence = self._artifact_evidence_text(result)
            if artifact_evidence:
                matched_result_payloads.append(
                    (
                        result_id,
                        artifact_evidence,
                    )
                )
        if dependency_input_artifacts and target_capability in {'vision_analysis', 'speech_to_text'}:
            if target_capability == 'speech_to_text':
                contract = branch.get('execution_contract') or branch
                input_refs = contract.get('input_refs') or []
                exact_refs = {item.get('artifact_ref') or item.get('ref') for item in input_refs
                              if isinstance(item, Mapping) and (item.get('artifact_ref') or item.get('ref'))}
                exact_phases = {item.get('phase_id') for item in input_refs
                                if isinstance(item, Mapping) and item.get('kind') == 'phase_output'
                                and item.get('phase_id')}
                if exact_refs:
                    dependency_input_artifacts = [a for a in dependency_input_artifacts
                                                  if a.get('artifact_ref') in exact_refs]
                elif exact_phases:
                    dependency_input_artifacts = [a for a in dependency_input_artifacts
                                                  if a.get('phase_id') in exact_phases]
                if not dependency_input_artifacts:
                    raise ValueError('Direct audio dependency identity unavailable for accepted input refs.')
            first_path = str(dependency_input_artifacts[0].get('path') or '').strip()
            evidence = '\n'.join(
                f"{str(item.get('type') or item.get('kind') or 'artifact').strip() or 'artifact'} artifact: {str(item.get('path') or '').strip()}"
                for item in dependency_input_artifacts
                if str(item.get('path') or '').strip()
            ).strip()
            payload: dict[str, Any] = {
                'input_artifacts': dependency_input_artifacts,
                'reference_artifacts': dependency_input_artifacts,
            }
            if first_path:
                payload['file_path'] = first_path
            if evidence:
                payload['content_payload'] = evidence
                payload['content_payload_source'] = 'late_fill_dependency_artifacts'
            return payload
        selected_reference_artifacts = [
            dict(item)
            for item in (selected_reference_payload.get('reference_artifacts') or [])
            if isinstance(item, Mapping)
        ]
        if len(matched_result_payloads) == 1:
            result_id, result_text = matched_result_payloads[0]
            if result_text:
                payload = {
                    'content_payload': result_text,
                    'content_payload_source': f'late_fill_result:{result_id}',
                }
                if selected_reference_artifacts:
                    payload['reference_artifacts'] = selected_reference_artifacts
                    payload['selected_reference_evidence_bound'] = True
                return payload
        if matched_result_payloads:
            combined = '\n\n'.join(
                f'{result_id}: {result_text}' if result_id else result_text
                for result_id, result_text in matched_result_payloads
                if result_text
            ).strip()
            if combined:
                payload = {
                    'content_payload': combined,
                    'content_payload_source': 'late_fill_results:' + ','.join(
                        result_id for result_id, _text in matched_result_payloads if result_id
                    ),
                }
                if selected_reference_artifacts:
                    payload['reference_artifacts'] = selected_reference_artifacts
                    payload['selected_reference_evidence_bound'] = True
                return payload
        return {}

    def merge_late_fill_result_fields(
        self,
        response_payload: dict[str, Any],
        infer_result: dict[str, Any],
    ) -> dict[str, Any]:
        updated = dict(response_payload or {})
        existing_output_artifacts = branch_result_contracts.merge_unique_artifact_records(
            updated.get('artifacts'),
            [],
        )
        identified_existing_paths = {
            branch_result_contracts._artifact_record_path(item)
            for item in existing_output_artifacts
            if branch_result_contracts._artifact_record_path(item)
            and str(
                item.get('artifact_id')
                or item.get('artifact_ref')
                or item.get('ref')
                or ''
            ).strip()
        }
        existing_refs = {
            str(item.get('artifact_ref') or item.get('ref') or '').strip()
            for item in existing_output_artifacts
            if str(item.get('artifact_ref') or item.get('ref') or '').strip()
        }
        missing_existing_artifacts = [
            item
            for item in self.build_canonical_response_artifacts(updated)
            if (
                (
                    not branch_result_contracts._artifact_record_path(item)
                    or branch_result_contracts._artifact_record_path(item) not in identified_existing_paths
                )
                and (
                    not str(item.get('artifact_ref') or item.get('ref') or '').strip()
                    or str(item.get('artifact_ref') or item.get('ref') or '').strip() not in existing_refs
                )
            )
        ]
        existing_output_artifacts = branch_result_contracts.merge_unique_artifact_records(
            existing_output_artifacts,
            missing_existing_artifacts,
        )
        for key in (
            'saved_text_path',
            'saved_text_artifacts',
            'text_artifact_requests',
            'text_artifact_revision_required',
            'text_artifact_source_is_input',
            'text_artifact_revision_write_proof',
            'text_artifact_revision_preservation_evidence',
            'saved_audio_path',
            'saved_image_path',
            'image_data_url',
            'seed',
            'image_state',
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
            'reference_image_count',
            'reference_image_kind',
            'cached',
            'cache_id',
            'result',
            'image_artifact_persisted_from_raw_late_fill',
            'retained_input_alias_required',
            'retained_input_binding_state',
            'retained_input_source_path',
            'retained_input_source_name',
            'retained_input_target_name',
            'retained_input_source_sha256',
            'retained_input_target_sha256',
            'retained_input_byte_identical',
            'provenance_id',
            'derived_from',
        ):
            if key in infer_result and infer_result.get(key) not in (None, ''):
                updated[key] = infer_result.get(key)
        for key in ('input_artifacts', 'reference_artifacts'):
            if key not in infer_result:
                continue
            merged_artifacts = branch_result_contracts.merge_unique_artifact_records(
                updated.get(key),
                infer_result.get(key),
            )
            if merged_artifacts:
                updated[key] = merged_artifacts
        existing_warnings = [
            str(item).strip()
            for item in (updated.get('warnings') or [])
            if str(item).strip()
        ]
        new_warnings = [
            str(item).strip()
            for item in (infer_result.get('warnings') or [])
            if str(item).strip()
        ]
        if existing_warnings or new_warnings:
            updated['warnings'] = list(dict.fromkeys(existing_warnings + new_warnings))
        incoming_output_artifacts = self.build_branch_local_late_fill_artifacts(
            updated,
            infer_result,
        )
        merged_output_artifacts = branch_result_contracts.merge_unique_artifact_records(
            existing_output_artifacts,
            incoming_output_artifacts,
        )
        updated['artifacts'] = merged_output_artifacts
        return updated

    def build_branch_local_late_fill_artifacts(
        self,
        response_payload: Mapping[str, Any],
        infer_result: Mapping[str, Any],
        *,
        capability: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Canonicalize only one producer result without aggregate identity leakage."""
        branch_payload = dict(infer_result or {})
        response_id = str(
            response_payload.get('id')
            or response_payload.get('response_id')
            or ''
        ).strip()
        if response_id:
            branch_payload['id'] = response_id
            branch_payload['response_id'] = response_id
        artifacts = branch_result_contracts.merge_unique_artifact_records(
            infer_result.get('artifacts'),
            self.build_canonical_response_artifacts(branch_payload),
        )

        normalized_capability = self.normalize_capability(
            capability
            or infer_result.get('capability')
            or infer_result.get('mode')
        )
        artifact_type = self.artifact_type_for_capability(normalized_capability)
        path_key_by_type = {
            'audio': 'saved_audio_path',
            'image': 'saved_image_path',
            'text': 'saved_text_path',
        }
        primary_path = str(
            infer_result.get(path_key_by_type.get(str(artifact_type or ''), ''))
            or ''
        ).strip()
        if not primary_path:
            for path_key in ('saved_image_path', 'saved_audio_path', 'saved_text_path'):
                candidate = str(infer_result.get(path_key) or '').strip()
                if candidate:
                    primary_path = candidate
                    break
        primary_artifact = next(
            (
                item
                for item in artifacts
                if (
                    (not primary_path or branch_result_contracts._artifact_record_path(item) == primary_path)
                    and (
                        not artifact_type
                        or str(item.get('type') or item.get('kind') or '').strip().lower()
                        == artifact_type
                    )
                )
            ),
            None,
        )
        if primary_artifact is None and len(artifacts) == 1:
            primary_artifact = artifacts[0]

        if primary_artifact is not None:
            explicit_artifact_id = str(infer_result.get('artifact_id') or '').strip()
            explicit_artifact_ref = str(
                infer_result.get('artifact_ref')
                or infer_result.get('ref')
                or ''
            ).strip()
            if explicit_artifact_id:
                primary_artifact['artifact_id'] = explicit_artifact_id
            if explicit_artifact_ref:
                primary_artifact['artifact_ref'] = explicit_artifact_ref
                primary_artifact['ref'] = explicit_artifact_ref
            elif explicit_artifact_id:
                primary_artifact['artifact_ref'] = f'artifact:{explicit_artifact_id}'
                primary_artifact['ref'] = primary_artifact['artifact_ref']
        return artifacts

    def attach_late_fill_result_artifact_identity(
        self,
        fill_record: Mapping[str, Any],
        response_payload: Mapping[str, Any],
        infer_result: Mapping[str, Any],
        *,
        capability: Optional[str] = None,
    ) -> dict[str, Any]:
        """Persist a branch's own artifact identity on its durable fill result."""
        updated = dict(fill_record or {})
        artifacts = self.build_branch_local_late_fill_artifacts(
            response_payload,
            infer_result,
            capability=capability,
        )
        if not artifacts:
            return updated

        binding_keys = ('branch_id', 'phase_id', 'slot_id', 'obligation_id', 'output_type')
        bound_artifacts: list[dict[str, Any]] = []
        for raw_artifact in artifacts:
            artifact = dict(raw_artifact)
            for key in binding_keys:
                if updated.get(key) not in (None, '', [], {}):
                    artifact.setdefault(key, updated.get(key))
            bound_artifacts.append(artifact)
        updated['artifacts'] = branch_result_contracts.merge_unique_artifact_records(
            updated.get('artifacts'),
            bound_artifacts,
        )

        artifact_type = self.artifact_type_for_capability(
            self.normalize_capability(
                capability
                or infer_result.get('capability')
                or infer_result.get('mode')
            )
        )
        path_key_by_type = {
            'audio': 'saved_audio_path',
            'image': 'saved_image_path',
            'text': 'saved_text_path',
        }
        primary_path = str(
            infer_result.get(path_key_by_type.get(str(artifact_type or ''), ''))
            or ''
        ).strip()
        primary_artifact = next(
            (
                item
                for item in updated['artifacts']
                if (
                    (not primary_path or branch_result_contracts._artifact_record_path(item) == primary_path)
                    and (
                        not artifact_type
                        or str(item.get('type') or item.get('kind') or '').strip().lower()
                        == artifact_type
                    )
                )
            ),
            None,
        )
        if primary_artifact is None and len(updated['artifacts']) == 1:
            primary_artifact = updated['artifacts'][0]
        snapshot = updated.get('saved_file_output_snapshot')
        if isinstance(snapshot, Mapping) and primary_artifact is not None:
            if primary_artifact.get('path') != snapshot.get('path'):
                raise ValueError('saved_file_output_identity_mismatch')
            updated['saved_file_output_snapshot'] = {**dict(snapshot), **{
                key: primary_artifact.get(key) for key in
                ('artifact_ref', 'artifact_id', 'source_response_id', 'branch_id', 'phase_id')}}
        if primary_artifact is not None:
            for key in (
                'artifact_id',
                'artifact_ref',
                'ref',
                'provenance_id',
                'derived_from',
                'source_response_id',
            ):
                if updated.get(key) in (None, '', [], {}) and primary_artifact.get(key) not in (None, '', [], {}):
                    updated[key] = primary_artifact.get(key)
        return updated

