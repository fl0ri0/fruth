"""Verify exact saved text output identity and revision/write evidence.

This saved-byte adapter reads existing paths and accepted result records. It
checks physical naming, target, digest and revision guarantees; it does not write,
repair, dispatch or publish an artifact, or own whole-response Closure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from fruth_services.linked_artifact_materialization import LinkedArtifactMaterialization
from fruth_services import text_artifact_materialization
from fruth_services import branch_result_contracts
from fruth_services.text_artifact_syntax import repair_text_artifact_syntax_content
from fruth_services.artifact_contracts import (
    read_saved_file_snapshot,
    saved_file_dependency_contract,
    saved_file_consumption_artifact_issue,
)
import hashlib
import logging
import re
from pathlib import Path
from typing import Any, Mapping, Optional
from fruth_core.text_artifacts import text_artifact_request_is_generic
from fruth_server.recovery_contract import RECOVERY_ACTION_RETRY_SAME_BRANCH
from fruth_services.artifact_contracts import (
    artifact_authority_rank,
    artifact_is_current_authoritative,
    text_artifact_output_declaration,
    text_artifact_same_output,
    artifact_logical_identities_match,
)


@dataclass(frozen=True)
class TextArtifactResultEvidence:
    build_canonical_response_artifacts: Callable[..., list[dict[str, Any]]]
    branch_requires_text_artifact: Callable[[Mapping[str, Any]], bool]
    saved_file_consumption_error: Callable[..., Optional[dict[str, Any]]]
    resolve_saved_file_input_path: Callable[[str], Any]
    branch_capability: Callable[[Any], str]
    branch_id: Callable[[Any], str]
    chat_capability: Callable[[], str]

    @classmethod
    def _text_artifact_revision_write_proven(
        cls,
        branch: Mapping[str, Any],
        payload: Mapping[str, Any],
    ) -> bool:
        """Require branch-produced write evidence before a revision can fulfill."""

        if not text_artifact_materialization._text_artifact_revision_required(branch):
            return False
        branch_id = str(branch.get('branch_id') or branch.get('phase_id') or '').strip()
        target_path = LinkedArtifactMaterialization._text_artifact_target_path_from_mapping(branch)
        artifact_request = (
            branch.get('artifact_request')
            if isinstance(branch.get('artifact_request'), Mapping)
            else {}
        )
        extension = str(
            branch.get('text_artifact_extension')
            or artifact_request.get('extension')
            or ''
        ).strip().lower().lstrip('.')

        # The synchronous chat path can persist a selected-source edit before
        # Late Fill exists. Its structured request plus saved artifact record
        # is current-response write evidence; a bare predecessor artifact is not.
        direct_records: list[Mapping[str, Any]] = []
        direct_request = (
            payload.get('text_artifact_request')
            if isinstance(payload, Mapping)
            and isinstance(payload.get('text_artifact_request'), Mapping)
            else {}
        )
        direct_saved_path = str(
            payload.get('saved_text_path') if isinstance(payload, Mapping) else ''
            or ''
        ).strip()
        if direct_request and direct_saved_path:
            direct_records.append(
                {
                    'type': 'text',
                    'path': direct_saved_path,
                    'text_artifact_request': direct_request,
                }
            )
        if isinstance(payload, Mapping):
            direct_records.extend(
                item
                for item in (payload.get('saved_text_artifacts') or [])
                if isinstance(item, Mapping)
            )
        for record in direct_records:
            request = (
                record.get('text_artifact_request')
                if isinstance(record.get('text_artifact_request'), Mapping)
                else record.get('artifact_request')
                if isinstance(record.get('artifact_request'), Mapping)
                else {}
            )
            source = str(request.get('source') or '').strip().lower()
            if source not in {'selected_source_edit', 'canonical_predecessor_artifact'}:
                continue
            if not cls._saved_text_artifact_matches_request(record, artifact_request):
                continue
            saved_path = str(record.get('path') or record.get('saved_text_path') or '').strip()
            if target_path and not text_artifact_materialization._text_artifact_path_matches_target(saved_path, target_path):
                continue
            if saved_path and text_artifact_materialization._text_artifact_saved_payload_error(
                saved_path,
                extension=extension,
            ) is None:
                return True

        late_fill = payload.get('late_fill') if isinstance(payload, Mapping) and isinstance(payload.get('late_fill'), Mapping) else {}
        for result in late_fill.get('fill_results') or []:
            if not isinstance(result, Mapping):
                continue
            result_branch_id = str(result.get('branch_id') or result.get('phase_id') or '').strip()
            if branch_id and result_branch_id != branch_id:
                continue
            proof = (
                result.get('text_artifact_revision_write_proof')
                if isinstance(result.get('text_artifact_revision_write_proof'), Mapping)
                else {}
            )
            if str(proof.get('status') or '').strip().lower() != 'applied':
                continue
            saved_path = str(result.get('saved_text_path') or proof.get('target_path') or '').strip()
            if target_path and not text_artifact_materialization._text_artifact_path_matches_target(saved_path, target_path):
                continue
            if saved_path and text_artifact_materialization._text_artifact_saved_payload_error(
                saved_path,
                extension=extension,
            ) is None:
                return True
        return False

    @classmethod
    def _saved_text_artifact_matches_request(cls, artifact: Mapping[str, Any], request: Mapping[str, Any]) -> bool:
        request_target_path = LinkedArtifactMaterialization._text_artifact_target_path_from_mapping(request)
        if request_target_path:
            artifact_path = str(artifact.get('path') or artifact.get('saved_text_path') or '').strip()
            if not text_artifact_materialization._text_artifact_path_matches_target(artifact_path, request_target_path):
                return False
        artifact_request = (
            artifact.get('text_artifact_request')
            if isinstance(artifact.get('text_artifact_request'), Mapping)
            else artifact.get('artifact_request')
            if isinstance(artifact.get('artifact_request'), Mapping)
            else {}
        )
        artifact_extension = str(
            artifact.get('text_artifact_extension')
            or artifact_request.get('extension')
            or Path(str(artifact.get('path') or artifact.get('saved_text_path') or '')).suffix.lstrip('.')
            or ''
        ).strip().lower().lstrip('.')
        request_extension = str(request.get('extension') or '').strip().lower().lstrip('.')
        if request_extension and artifact_extension and artifact_extension != request_extension:
            return False
        artifact_source_name = str(
            artifact.get('text_artifact_source_name')
            or artifact_request.get('source_name')
            or Path(str(artifact.get('path') or artifact.get('saved_text_path') or '')).stem
            or ''
        ).strip().lower()
        request_source_name = str(request.get('source_name') or '').strip().lower()
        return not request_source_name or not artifact_source_name or artifact_source_name == request_source_name

    @staticmethod
    def _read_small_text_artifact(path: Any, *, max_bytes: int = 512_000) -> str:
        token = str(path or '').strip()
        if not token:
            return ''
        try:
            target = Path(token).expanduser()
            if not target.is_file() or target.stat().st_size > max_bytes:
                return ''
            return target.read_text(encoding='utf-8', errors='replace')
        except OSError:
            return ''

    @classmethod
    def _text_artifact_saved_binding_violation(
        cls,
        result: Mapping[str, Any],
        *,
        extension: str,
        source_name: str,
        target_path: str = '',
        generic: bool = False,
    ) -> Optional[dict[str, Any]]:
        """Verify physical identity independently of returned naming claims."""
        paths = text_artifact_materialization._saved_text_paths_from_result(result)
        if not paths:
            return None

        def normalized_extension(value: Any) -> str:
            token = str(value or '').strip().lower().lstrip('.')
            return {'markdown': 'md', 'htm': 'html'}.get(token, token)

        expected_extension = normalized_extension(extension)
        expected_name = LinkedArtifactMaterialization._normalized_text_artifact_source_name_for_match(source_name)

        def name_matches(value: Any) -> bool:
            name = LinkedArtifactMaterialization._normalized_text_artifact_source_name_for_match(value)
            if artifact_logical_identities_match((expected_extension, expected_name), (expected_extension, name)):
                return True
            # The existing writer adds _2, _3, ... only to generated storage
            # names. An arbitrary sibling allowed_2.txt is not allowed.txt.
            if re.match(r'^\d{8}(?:t\d{6}z)?-', name):
                # Retain both timestamped writer names and older date-prefixed
                # canonical names, including the writer's collision suffix.
                return re.sub(r'-\d+$', '', name).endswith('-' + expected_name)
            return False

        def failure(path: str, reason: str) -> dict[str, Any]:
            return {
                'code': 'TEXT_ARTIFACT_BINDING_VIOLATION',
                'message': 'Saved text artifact does not match the accepted output binding: ' + reason,
                'actual_saved_text_path': path,
                'text_artifact_extension': extension or None,
                'text_artifact_source_name': source_name or None,
                'expected_target_path': target_path or None,
                'evidence': 'saved_text_artifact_binding_mismatch',
                'suggested_action': RECOVERY_ACTION_RETRY_SAME_BRANCH,
                'retryable': True,
            }

        records = [result]
        for key in ('saved_text_artifacts', 'artifacts'):
            records.extend(item for item in result.get(key) or [] if isinstance(item, Mapping))
        records.extend(declaration for record in list(records)
            for declaration in record.get('text_artifact_output_declarations') or []
            if isinstance(declaration, Mapping))
        for path in paths:
            physical_path = Path(path).expanduser().resolve()
            actual_extension = normalized_extension(physical_path.suffix)
            if not generic and expected_extension and actual_extension != expected_extension:
                return failure(path, 'physical extension differs')
            if target_path and not text_artifact_materialization._text_artifact_path_matches_target(path, target_path):
                return failure(path, 'physical target differs')
            if not target_path and not generic and expected_name and not name_matches(physical_path.stem):
                return failure(path, 'physical logical filename differs')
            for record in records:
                record_path = str(record.get('saved_text_path') or record.get('path') or '').strip()
                if not record_path or not text_artifact_materialization._text_artifact_path_matches_target(record_path, path):
                    continue
                saved_evidence = record.get('text_artifact_saved_evidence') or {}
                if saved_evidence.get('status') == 'rejected':
                    return dict(saved_evidence.get('error') or failure(path, 'saved result was rejected'))
                declarations = [record]
                for key in ('artifact_request', 'text_artifact_request'):
                    if isinstance(record.get(key), Mapping):
                        declarations.append(record[key])
                for declaration in declarations:
                    for key in ('extension', 'text_artifact_extension'):
                        claimed = normalized_extension(declaration.get(key))
                        if (claimed and claimed != actual_extension
                                and not (generic and text_artifact_request_is_generic(declaration))):
                            return failure(path, 'returned extension conflicts with physical file')
                    for key in ('source_name', 'text_artifact_source_name', 'name'):
                        if not generic and expected_name and declaration.get(key) and not name_matches(declaration[key]):
                            return failure(path, 'returned logical identity conflicts')
                    for key in ('target_path', 'text_artifact_target_path'):
                        claimed = str(declaration.get(key) or '').strip()
                        if claimed and not text_artifact_materialization._text_artifact_path_matches_target(path, claimed):
                            return failure(path, 'returned target conflicts with physical file')
                # Top-level Infer file_sha256 describes its input attachment.
                # Output-record digest evidence must match the saved bytes.
                if record is not result or result.get('type') in {'text', 'document', 'file'}:
                    claimed_digest = str(record.get('file_sha256') or '').strip()
                    if claimed_digest:
                        try:
                            actual_digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
                        except OSError:
                            return failure(path, 'output digest cannot be verified')
                        if claimed_digest != actual_digest:
                            return failure(path, 'output digest differs')
        return None

    def capture_root_text_artifact_saved_evidence(
        self, result: dict[str, Any], *, accepted_requests: list[dict[str, Any]],
        response_id: str, phase_id: str = '',
    ) -> dict[str, Any]:
        """Check the raw root handoff before canonical projection loses claims.

        Requests are captured by the caller/source owners before dispatch. No
        returned request, graph, identity or physical bytes create authority.
        """
        paths = text_artifact_materialization._saved_text_paths_from_result(result)
        if not paths or not accepted_requests:
            return result
        updated = dict(result)
        saved_records = []
        errors = []
        raw_records = [record for key in ('saved_text_artifacts', 'artifacts')
            for record in result.get(key) or [] if isinstance(record, Mapping)
            and (key == 'saved_text_artifacts'
                 or str(record.get('type') or record.get('kind') or 'text').lower() in {'text', 'document', 'file'})]
        # These are declarations returned by this execution, not a historical
        # artifact inventory. A returned source/version claim cannot exempt a
        # conflicting output declaration from validation. Inputs live separately.
        current_records = raw_records
        paths = text_artifact_materialization._saved_text_paths_from_result({
            'saved_text_path': result.get('saved_text_path'), 'saved_text_artifacts': current_records,
        })
        too_many_paths = len({str(Path(path).expanduser().resolve()) for path in paths}) > len(accepted_requests)
        for path in paths:
            contracts = [contract for contract in accepted_requests
                if not self._text_artifact_saved_binding_violation(
                    {'type': 'text', 'path': path}, extension=contract.get('extension') or '',
                    source_name=contract.get('source_name') or '',
                    target_path=contract.get('target_path') or '',
                    generic=text_artifact_request_is_generic(contract),
                )]
            contract = contracts[0] if len(contracts) == 1 else accepted_requests[0]
            records = [record for record in current_records
                if text_artifact_materialization._text_artifact_path_matches_target(
                    record.get('path') or record.get('saved_text_path') or '', path)]
            raw = {'saved_text_artifacts': records}
            if text_artifact_materialization._text_artifact_path_matches_target(result.get('saved_text_path') or '', path):
                raw.update(result)
                raw['saved_text_artifacts'] = records
                raw['artifacts'] = []
            error = self._text_artifact_saved_binding_violation(
                raw, extension=contract.get('extension') or '',
                source_name=contract.get('source_name') or '',
                target_path=contract.get('target_path') or '',
                generic=text_artifact_request_is_generic(contract),
            )
            if len(contracts) != 1 and not error:
                error = {
                    'code': 'TEXT_ARTIFACT_BINDING_VIOLATION',
                    'message': 'Saved text artifact has no unique accepted output binding.',
                    'actual_saved_text_path': path,
                    'evidence': 'saved_text_artifact_binding_mismatch',
                }
            if too_many_paths and not error:
                error = {
                    'code': 'TEXT_ARTIFACT_BINDING_VIOLATION',
                    'message': 'Saved text artifacts exceed the accepted output count.',
                    'actual_saved_text_path': path,
                    'evidence': 'saved_text_artifact_binding_mismatch',
                }
            declarations = [text_artifact_output_declaration(record) for record in records]
            if raw.get('saved_text_path'):
                declarations.insert(0, text_artifact_output_declaration(
                    result, input_attachment_digest=True,
                ))
            evidence = {
                'kind': 'fruth.text_artifact_saved_evidence',
                'status': 'rejected' if error else 'passed',
                'source': 'root_saved_result_validation',
                'source_response_id': response_id,
                'phase_id': phase_id,
                'accepted_request': dict(contract),
                'declarations': declarations,
            }
            if error:
                evidence['error'] = dict(error)
                errors.append(dict(error))
            for record in records or [{'type': 'text', 'path': path}]:
                saved_records.append({
                    **dict(record), 'source_response_id': response_id,
                    'phase_id': phase_id or record.get('phase_id'), 'origin': 'assistant_output',
                    'text_artifact_saved_evidence': evidence,
                    'text_artifact_output_declarations': declarations,
                })
        updated['saved_text_artifacts'] = saved_records
        if errors:
            updated['text_artifact_binding_errors'] = errors
        return updated

    def _matching_canonical_text_artifact_path(
        self,
        payload: Mapping[str, Any],
        *,
        extension: str,
        source_name: str,
        target_path: str = '',
        generic: bool = False,
    ) -> str:
        result = self._canonical_text_artifact_saved_result(
            payload,
            extension=extension,
            source_name=source_name,
            target_path=target_path,
            generic=generic,
        )
        return str(result.get('saved_text_path') or result.get('path') or '').strip()

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
        if not isinstance(payload, Mapping):
            return {}
        records: list[Mapping[str, Any]] = []
        artifacts = payload.get('artifacts') if isinstance(payload.get('artifacts'), list) else []
        records.extend(item for item in artifacts if isinstance(item, Mapping))
        records.extend(
            item for item in self.build_canonical_response_artifacts(dict(payload))
            if isinstance(item, Mapping)
        )
        for artifact in payload.get('saved_text_artifacts') or []:
            if isinstance(artifact, Mapping):
                records.append({'type': 'text', **dict(artifact)})
        saved_text_path = str(payload.get('saved_text_path') or payload.get('savedTextPath') or '').strip()
        if saved_text_path:
            records.append(
                {
                    'type': 'text',
                    'path': saved_text_path,
                    'origin': 'assistant_output',
                    'source_response_id': str(payload.get('id') or '').strip() or None,
                    'text_artifact_extension': payload.get('text_artifact_extension'),
                    'text_artifact_source_name': payload.get('text_artifact_source_name'),
                    'text_artifact_target_path': payload.get('text_artifact_target_path'),
                    'artifact_request': payload.get('text_artifact_request')
                    if isinstance(payload.get('text_artifact_request'), Mapping)
                    else {},
                }
            )
        late_fill = payload.get('late_fill') if isinstance(payload.get('late_fill'), Mapping) else {}
        for result in late_fill.get('fill_results') or []:
            if not isinstance(result, Mapping):
                continue
            result_saved_text_path = str(result.get('saved_text_path') or '').strip()
            if not result_saved_text_path:
                continue
            execution_contract = (
                result.get('execution_contract')
                if isinstance(result.get('execution_contract'), Mapping)
                else {}
            )
            artifact_request = (
                result.get('artifact_request')
                if isinstance(result.get('artifact_request'), Mapping)
                else (
                    execution_contract.get('artifact_request')
                    if isinstance(execution_contract.get('artifact_request'), Mapping)
                    else {}
                )
            )
            records.append(
                {
                    'type': 'text',
                    'path': result_saved_text_path,
                    'text_artifact_extension': (
                        result.get('text_artifact_extension')
                        or execution_contract.get('text_artifact_extension')
                        or artifact_request.get('extension')
                    ),
                    'text_artifact_source_name': (
                        result.get('text_artifact_source_name')
                        or execution_contract.get('text_artifact_source_name')
                        or artifact_request.get('source_name')
                    ),
                    'text_artifact_target_path': (
                        result.get('text_artifact_target_path')
                        or execution_contract.get('text_artifact_target_path')
                        or artifact_request.get('target_path')
                    ),
                    'artifact_request': artifact_request,
                    'branch_id': result.get('branch_id'),
                    'phase_id': result.get('phase_id'),
                    'obligation_id': result.get('obligation_id'),
                    'source_response_id': str(payload.get('id') or '').strip() or None,
                    'origin': 'late_fill_result',
                    'text_artifact_source': result.get('text_artifact_source'),
                }
            )
        expected_extension = str(extension or '').strip().lower().lstrip('.')
        expected_source_name = str(source_name or '').strip().lower()
        expected_target_path = str(target_path or '').strip()
        matching_records_by_path: dict[str, Mapping[str, Any]] = {}
        for record in records:
            if str(record.get('type') or record.get('kind') or 'text').strip().lower() != 'text':
                continue
            if generic and not artifact_is_current_authoritative(
                record, response_id=str(payload.get('id') or '').strip(),
            ):
                # An unspecified save may reuse its one current output, never
                # promote selected/reference-only or stale material to output.
                continue
            path = branch_result_contracts._artifact_record_path(record)
            if not path:
                continue
            # Reconcile raw and canonical aliases of this output *before*
            # ranking/deduplication. A clean record cannot hide a bad sibling.
            related = [item for item in records if text_artifact_same_output(
                record, item, response_id=str(payload.get('id') or ''),
            )]
            if self._text_artifact_saved_binding_violation(
                {'saved_text_artifacts': related}, extension=expected_extension, source_name=source_name,
                target_path=expected_target_path, generic=generic,
            ):
                continue
            if expected_target_path and not text_artifact_materialization._text_artifact_path_matches_target(path, expected_target_path):
                continue
            artifact_extension = branch_result_contracts._artifact_record_extension(record)
            if not generic and expected_extension and artifact_extension and artifact_extension != expected_extension:
                continue
            if not generic and expected_source_name and not LinkedArtifactMaterialization._artifact_record_matches_text_artifact_source_name(
                record,
                expected_source_name,
            ):
                continue
            existing = matching_records_by_path.get(path)
            if (
                existing is None
                or artifact_authority_rank(record, response_id=str(payload.get('id') or '').strip())
                > artifact_authority_rank(existing, response_id=str(payload.get('id') or '').strip())
            ):
                matching_records_by_path[path] = record

        # Filesystem proximity is not current-response authority. One current
        # response-owned candidate may safely beat any number of stale linked
        # siblings, while multiple current candidates remain fail-closed.
        response_id = str(payload.get('id') or '').strip()
        authoritative_paths = {
            path: record
            for path, record in matching_records_by_path.items()
            if artifact_is_current_authoritative(record, response_id=response_id)
        }
        if len(authoritative_paths) > 1:
            return {}
        if len(authoritative_paths) == 1:
            matching_records_by_path = authoritative_paths
        elif len(matching_records_by_path) != 1:
            return {}

        for path, record in matching_records_by_path.items():
            artifact_extension = branch_result_contracts._artifact_record_extension(record)
            artifact_source_name = branch_result_contracts._artifact_record_source_name(record).lower()
            payload_extension = Path(path).suffix.lstrip('.') if generic else expected_extension
            payload_error = text_artifact_materialization._text_artifact_saved_payload_error(path, extension=payload_extension)
            source = 'canonical_text_artifact_evidence'
            repair_payload: dict[str, Any] = {}
            content = ''
            if payload_error:
                if (
                    not allow_deterministic_repair
                    or payload_error.get('code') != 'TEXT_ARTIFACT_SYNTAX_SANITY_FAILED'
                ):
                    continue
                try:
                    target = Path(path).expanduser()
                    original = target.read_text(encoding='utf-8', errors='replace') if target.is_file() else ''
                except OSError:
                    original = ''
                if not original:
                    continue
                repaired, repairs = repair_text_artifact_syntax_content(
                    payload_extension,
                    original,
                )
                if not repairs or repaired == original:
                    continue
                repaired_content, repaired_error = text_artifact_materialization._text_artifact_content_payload_error(
                    repaired,
                    extension=payload_extension,
                    saved_path=path,
                )
                if repaired_error or not repaired_content:
                    continue
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(repaired_content, encoding='utf-8')
                except OSError as exc:
                    logging.warning(
                        'Could not write deterministic canonical text artifact repair to %s: %s',
                        path,
                        exc,
                    )
                    continue
                if text_artifact_materialization._text_artifact_saved_payload_error(path, extension=payload_extension):
                    continue
                source = 'canonical_text_artifact_deterministic_syntax_repair'
                content = repaired_content
                repair_payload = {
                    'status': 'applied',
                    'target_path': path,
                    'target_extension': payload_extension or None,
                    'repair_count': len(repairs),
                    'repairs': repairs,
                    'source': 'deterministic_syntax_repair',
                }
            else:
                content = self._read_small_text_artifact(path)
            artifact_request = (
                record.get('artifact_request')
                if isinstance(record.get('artifact_request'), Mapping)
                else (
                    record.get('text_artifact_request')
                    if isinstance(record.get('text_artifact_request'), Mapping)
                    else {}
                )
            )
            result = {
                'type': 'text',
                'kind': 'text',
                'path': path,
                'saved_text_path': path,
                'text_artifact_target_path': expected_target_path or LinkedArtifactMaterialization._text_artifact_target_path_from_mapping(record),
                'text_artifact_extension': payload_extension or artifact_extension,
                'text_artifact_source_name': artifact_source_name if generic else expected_source_name or artifact_source_name,
                'text_artifact_source': source,
                'artifact_request': dict(artifact_request or {}),
            }
            if content:
                result['content'] = content
                result['content_payload'] = content
                result['result_text'] = content
            if repair_payload:
                result['target_path_authoritative_repair'] = repair_payload
                result['canonical_text_artifact_repair'] = repair_payload
            return result
        return {}

    def _ensure_required_text_artifact_saved_truth(
        self,
        branch: Mapping[str, Any],
        infer_result: dict[str, Any],
        effective_data: Mapping[str, Any],
        current_payload: Mapping[str, Any],
    ) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
        if not self.branch_requires_text_artifact(branch):
            return infer_result, None
        artifact_request = text_artifact_materialization._required_text_artifact_request(
            branch, {}, effective_data, extension='', source_name='', target_path='',
        )
        revision_required = text_artifact_materialization._text_artifact_revision_required(
            branch,
            effective_data,
            infer_result,
            artifact_request,
        )
        effective_request = (
            effective_data.get('artifact_request')
            if isinstance(effective_data.get('artifact_request'), Mapping)
            else {}
        )
        target_path = text_artifact_materialization._required_text_artifact_target_path(branch, {}, effective_data)
        if target_path:
            extension = str(
                branch.get('text_artifact_extension')
                or effective_request.get('extension')
                or artifact_request.get('extension')
                or effective_data.get('text_artifact_extension')
                or Path(target_path).suffix
                or ''
            ).strip().lower().lstrip('.')
            source_name = str(
                branch.get('text_artifact_source_name')
                or effective_request.get('source_name')
                or artifact_request.get('source_name')
                or effective_data.get('text_artifact_source_name')
                or Path(target_path).stem
                or ''
            ).strip()
        else:
            extension = str(
                branch.get('text_artifact_extension')
                or artifact_request.get('extension')
                or effective_data.get('text_artifact_extension')
                or effective_request.get('extension')
                or ''
            ).strip().lower().lstrip('.')
            source_name = str(
                branch.get('text_artifact_source_name')
                or artifact_request.get('source_name')
                or effective_data.get('text_artifact_source_name')
                or effective_request.get('source_name')
                or ''
            ).strip()
        generic = text_artifact_request_is_generic({
            **artifact_request, 'extension': extension, 'source_name': source_name,
            'target_path': target_path,
        })
        if not target_path:
            # A new output's binding comes from the accepted branch. Returned
            # target/name claims cannot authorize a write or repair a mismatch.
            returned_files = {
                **infer_result,
                'saved_text_path': infer_result.get('saved_text_path') or effective_data.get('saved_text_path'),
                'saved_text_artifacts': infer_result.get('saved_text_artifacts') or effective_data.get('saved_text_artifacts') or [],
            }
            binding_error = self._text_artifact_saved_binding_violation(
                returned_files, extension=extension, source_name=source_name, generic=generic,
            )
            if binding_error:
                return infer_result, binding_error
        # An accepted exact target may use a candidate's bytes through the
        # existing target writer/proof owner. Only the saved exact target can
        # pass the checks below; the sibling itself never fulfills the duty.
        bound_saved_repair = (infer_result.get('saved_file_consumption_evidence') or {}).get('syntax_repair')
        if bound_saved_repair:
            # Dispatch already saved and digested this exact repair output. A
            # second candidate write (even stripping a trailing newline) would
            # invalidate consumption. Verify the bytes; do not re-materialize.
            target_materialization_error = self.saved_file_consumption_error(branch, infer_result, current_payload=current_payload)
            try:
                snapshot = infer_result.get('saved_file_output_snapshot') or {}
                physical = read_saved_file_snapshot(snapshot.get('path', ''), self.resolve_saved_file_input_path)
                if any(physical.get(key) != snapshot.get(key) for key in ('path', 'sha256', 'size_bytes')):
                    raise ValueError('saved_file_syntax_repair_output_changed')
            except (OSError, ValueError, KeyError, UnicodeError) as exc:
                target_materialization_error = {'code': 'DEPENDENCY_CHAIN_REPAIR_REQUIRED',
                    'message': str(exc), 'stage': 'saved_file_evidence_gate', 'retryable': False}
        else:
            infer_result, target_materialization_error = text_artifact_materialization._materialize_required_text_artifact_target_path(
                branch,
                infer_result,
                effective_data,
                extension=extension,
                source_name=source_name,
            )
        if target_materialization_error:
            return infer_result, target_materialization_error
        target_binding_error = text_artifact_materialization._text_artifact_target_binding_violation(
            infer_result,
            target_path=target_path,
            extension=extension,
            source_name=source_name,
        )
        if target_binding_error:
            return infer_result, target_binding_error
        binding_error = self._text_artifact_saved_binding_violation(
            infer_result, extension=extension, source_name=source_name,
            target_path=target_path, generic=generic,
        )
        if binding_error:
            return infer_result, binding_error
        saved_text_path = str(
            infer_result.get('saved_text_path')
            or effective_data.get('saved_text_path')
            or ''
        ).strip()
        saved_text_artifacts = [
            item
            for item in (
                infer_result.get('saved_text_artifacts')
                or effective_data.get('saved_text_artifacts')
                or []
            )
            if isinstance(item, Mapping)
        ]
        candidate_paths = [saved_text_path]
        candidate_paths.extend(str(item.get('path') or item.get('saved_text_path') or '').strip() for item in saved_text_artifacts)
        for candidate_path in candidate_paths:
            if not candidate_path:
                continue
            payload_extension = Path(candidate_path).suffix.lstrip('.') if generic else extension
            payload_error = text_artifact_materialization._text_artifact_saved_payload_error(candidate_path, extension=payload_extension)
            if payload_error:
                return infer_result, payload_error
        if saved_text_path or any(str(item.get('path') or item.get('saved_text_path') or '').strip() for item in saved_text_artifacts):
            if revision_required and not isinstance(
                infer_result.get('text_artifact_revision_write_proof'),
                Mapping,
            ):
                return infer_result, {
                    'code': 'TEXT_ARTIFACT_REVISION_WRITE_PROOF_MISSING',
                    'message': (
                        'Required text artifact revision has a path but no current-branch write proof. '
                        'Existing source paths cannot fulfill an edit obligation.'
                    ),
                    'text_artifact_extension': extension or None,
                    'text_artifact_source_name': source_name or None,
                    'suggested_action': RECOVERY_ACTION_RETRY_SAME_BRANCH,
                    'retryable': True,
                }
            return infer_result, None
        canonical_path = ''
        if not revision_required:
            canonical_path = self._matching_canonical_text_artifact_path(
                current_payload,
                extension=extension,
                source_name=source_name,
                target_path=target_path,
                generic=generic,
            )
        if canonical_path:
            updated = dict(infer_result)
            updated['saved_text_path'] = canonical_path
            updated['text_artifact_target_path'] = canonical_path
            updated.setdefault('text_artifact_extension', extension)
            updated.setdefault('text_artifact_source_name', source_name)
            updated.setdefault('text_artifact_source', 'canonical_text_artifact_evidence')
            return updated, None
        return infer_result, {
            'code': 'TEXT_ARTIFACT_NOT_PERSISTED',
            'message': (
                'Required text artifact branch returned without a saved text artifact path. '
                'Chat text alone does not fulfill local file obligations.'
            ),
            'text_artifact_extension': extension or None,
            'text_artifact_source_name': source_name or None,
            'suggested_action': RECOVERY_ACTION_RETRY_SAME_BRANCH,
            'retryable': True,
        }

    def _canonical_text_artifact_branch_fulfillment(
        self,
        branch: Mapping[str, Any],
        *payloads: Mapping[str, Any],
        allow_deterministic_repair: bool = True,
    ) -> dict[str, Any]:
        if not self.branch_requires_text_artifact(branch):
            return {}
        if text_artifact_materialization._artifact_gap_is_authoritative_bounded_text_artifact_repair(branch):
            return {}
        if text_artifact_materialization._text_artifact_revision_required(branch) and not any(
            isinstance(payload, Mapping)
            and self._text_artifact_revision_write_proven(branch, payload)
            for payload in payloads
        ):
            return {}
        artifact_request = branch.get('artifact_request') if isinstance(branch.get('artifact_request'), Mapping) else {}
        if (
            saved_file_dependency_contract(branch)
            or artifact_request.get('saved_file_producer')
            or branch.get('branch_contract_error') == 'saved_file_dependency_unbound'
        ):
            # File presence cannot replace a producer snapshot or a bound read.
            # Reuse Closure's check and retain the complete validated result.
            for payload in payloads:
                if not isinstance(payload, Mapping) or not self._text_artifact_branch_has_canonical_evidence(
                    branch, payload
                ):
                    continue
                for result in (payload.get('late_fill') or {}).get('fill_results') or []:
                    if (
                        isinstance(result, Mapping)
                        and result.get('branch_id') == branch.get('branch_id')
                        and result.get('phase_id') == branch.get('phase_id')
                    ):
                        return dict(result)
            return {}
        extension = str(
            branch.get('text_artifact_extension')
            or artifact_request.get('extension')
            or ''
        ).strip().lower().lstrip('.')
        source_name = str(
            branch.get('text_artifact_source_name')
            or artifact_request.get('source_name')
            or ''
        ).strip()
        target_path = LinkedArtifactMaterialization._text_artifact_target_path_from_mapping(branch) or LinkedArtifactMaterialization._text_artifact_target_path_from_mapping(
            artifact_request
        )
        if not extension or not source_name:
            return {}
        generic = text_artifact_request_is_generic({
            **artifact_request, 'extension': extension, 'source_name': source_name,
            'target_path': target_path,
        })
        canonical_result: dict[str, Any] = {}
        for payload in payloads:
            if not isinstance(payload, Mapping):
                continue
            canonical_result = self._canonical_text_artifact_saved_result(
                payload,
                extension=extension,
                source_name=source_name,
                target_path=target_path,
                allow_deterministic_repair=allow_deterministic_repair,
                generic=generic,
            )
            if canonical_result:
                break
        canonical_path = str(
            canonical_result.get('saved_text_path')
            or canonical_result.get('path')
            or ''
        ).strip()
        if not canonical_path:
            return {}
        text_source = str(
            canonical_result.get('text_artifact_source')
            or 'canonical_text_artifact_evidence'
        ).strip()
        if not text_source:
            text_source = 'canonical_text_artifact_evidence'
        event_message = (
            'Required text artifact satisfied by deterministic canonical saved file repair.'
            if text_source == 'canonical_text_artifact_deterministic_syntax_repair'
            else 'Required text artifact satisfied by canonical saved file evidence.'
        )
        branch_id = self.branch_id(branch)
        if not branch_id:
            return {}
        fill_record: dict[str, Any] = {
            'branch_id': branch_id,
            'phase_id': str(branch.get('phase_id') or branch_id).strip() or branch_id,
            'capability': self.branch_capability(branch) or self.chat_capability(),
            'saved_text_path': canonical_path,
            'text_artifact_extension': (
                canonical_result.get('text_artifact_extension') if generic else extension
            ),
            'text_artifact_source_name': (
                canonical_result.get('text_artifact_source_name') if generic else source_name
            ),
            'text_artifact_source': text_source,
            'result_text': event_message,
        }
        if target_path:
            fill_record['text_artifact_target_path'] = target_path
        if isinstance(artifact_request, Mapping) and artifact_request:
            fill_record['artifact_request'] = dict(artifact_request)
        target_repair = canonical_result.get('target_path_authoritative_repair')
        if isinstance(target_repair, Mapping):
            fill_record['target_path_authoritative_repair'] = dict(target_repair)
        return {
            key: value
            for key, value in fill_record.items()
            if value not in (None, '', [], {})
        }

    def _text_artifact_branch_has_canonical_evidence(
        self,
        branch: Mapping[str, Any],
        payload: Mapping[str, Any],
    ) -> bool:
        if saved_file_dependency_contract(branch):
            return not saved_file_consumption_artifact_issue(
                branch, payload, self.resolve_saved_file_input_path)
        if branch.get('branch_contract_error') == 'saved_file_dependency_unbound':
            return False
        verified_producer_path = ''
        if (branch.get('artifact_request') or {}).get('saved_file_producer'):
            results = [r for r in (payload.get('late_fill') or {}).get('fill_results') or []
                if isinstance(r, Mapping) and r.get('branch_id') == branch.get('branch_id')
                and r.get('phase_id') == branch.get('phase_id')]
            if len(results) != 1:
                return False
            snapshot = results[0].get('saved_file_output_snapshot') or {}
            artifacts = results[0].get('artifacts') or []
            if not any(isinstance(a, Mapping) and all(snapshot.get(key) and a.get(key) == snapshot[key]
                for key in ('artifact_ref', 'artifact_id', 'path', 'source_response_id', 'branch_id', 'phase_id'))
                for a in artifacts):
                return False
            try:
                current = read_saved_file_snapshot(snapshot['path'], self.resolve_saved_file_input_path)
                if (snapshot.get('source_response_id') != payload.get('id') or
                        any(current[key] != snapshot.get(key) for key in ('sha256', 'size_bytes'))):
                    return False
            except (OSError, ValueError, KeyError):
                return False
            verified_producer_path = str(snapshot['path']).strip()

        if text_artifact_materialization._text_artifact_revision_required(branch):
            return self._text_artifact_revision_write_proven(branch, payload)
        if text_artifact_materialization._artifact_gap_is_authoritative_bounded_text_artifact_repair(branch):
            return self._authoritative_bounded_text_artifact_repair_has_write_evidence(
                branch,
                payload,
            )
        artifact_request = branch.get('artifact_request') if isinstance(branch.get('artifact_request'), Mapping) else {}
        extension = str(
            branch.get('text_artifact_extension')
            or artifact_request.get('extension')
            or ''
        ).strip().lower().lstrip('.')
        source_name = str(
            branch.get('text_artifact_source_name')
            or artifact_request.get('source_name')
            or ''
        ).strip()
        target_path = LinkedArtifactMaterialization._text_artifact_target_path_from_mapping(branch) or LinkedArtifactMaterialization._text_artifact_target_path_from_mapping(
            artifact_request
        )
        if not extension or not source_name:
            return False
        if verified_producer_path:
            if target_path and not text_artifact_materialization._text_artifact_path_matches_target(verified_producer_path, target_path):
                return False
            # Keep the proven branch binding through name and syntax checks.
            # Earlier streamed files with the same name are separate evidence.
            target_path = verified_producer_path
        return bool(
            self._matching_canonical_text_artifact_path(
                payload,
                extension=extension,
                source_name=source_name,
                target_path=target_path,
                generic=text_artifact_request_is_generic({
                    **artifact_request, 'extension': extension, 'source_name': source_name,
                    'target_path': target_path,
                }),
            )
        )

    @classmethod
    def _authoritative_bounded_text_artifact_repair_has_write_evidence(
        cls,
        branch: Mapping[str, Any],
        payload: Mapping[str, Any],
    ) -> bool:
        artifact_request = (
            branch.get('artifact_request')
            if isinstance(branch.get('artifact_request'), Mapping)
            else {}
        )
        target_path = (
            LinkedArtifactMaterialization._text_artifact_target_path_from_mapping(branch)
            or LinkedArtifactMaterialization._text_artifact_target_path_from_mapping(artifact_request)
        )
        branch_id = str(branch.get('branch_id') or branch.get('phase_id') or '').strip()
        if not target_path or not branch_id:
            return False
        late_fill = (
            payload.get('late_fill')
            if isinstance(payload.get('late_fill'), Mapping)
            else {}
        )

        def path_matches(record: Mapping[str, Any]) -> bool:
            if str(record.get('branch_id') or record.get('phase_id') or '').strip() != branch_id:
                return False
            candidate = str(
                record.get('target_path')
                or record.get('to_path')
                or record.get('saved_text_path')
                or record.get('path')
                or ''
            ).strip()
            return bool(
                candidate
                and text_artifact_materialization._text_artifact_path_matches_target(candidate, target_path)
            )

        for collection_key in (
            'linked_artifact_rebinds',
            'syntax_sanity_repairs',
            'composed_page_image_representation_repairs',
            'hero_image_composition_repairs',
        ):
            for raw_record in late_fill.get(collection_key) or []:
                if not isinstance(raw_record, Mapping):
                    continue
                if (
                    str(raw_record.get('status') or '').strip().lower() == 'applied'
                    and path_matches(raw_record)
                ):
                    return True

        write_sources = {
            'target_path_authoritative_repair_output',
            'target_path_deterministic_syntax_repair',
            'canonical_text_artifact_deterministic_syntax_repair',
        }
        record_collections = [
            payload.get('artifacts') or [],
            payload.get('saved_text_artifacts') or [],
            late_fill.get('fill_results') or [],
        ]
        for collection in record_collections:
            for raw_record in collection:
                if not isinstance(raw_record, Mapping) or not path_matches(raw_record):
                    continue
                source = str(raw_record.get('text_artifact_source') or '').strip()
                if source in write_sources:
                    return True
                repair = raw_record.get('target_path_authoritative_repair')
                if (
                    isinstance(repair, Mapping)
                    and str(repair.get('status') or '').strip().lower() == 'applied'
                ):
                    return True
        return False

