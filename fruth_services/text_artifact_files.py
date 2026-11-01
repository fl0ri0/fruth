"""Concrete saved-text revision reads, retained aliases and syntax repair writes.

Exact existing paths and accepted artifact records delimit each operation. The
adapter preserves byte limits, atomic alias replacement and frozen accepted
results. Its receipts do not independently establish runtime acceptance or Closure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from fruth_services import text_artifact_syntax
from fruth_services.linked_artifact_materialization import LinkedArtifactMaterialization
from fruth_services import text_artifact_materialization
from fruth_services import branch_result_contracts
from fruth_services.text_artifact_syntax import repair_text_artifact_syntax_content
from fruth_services.text_artifact_syntax import text_artifact_syntax_sanity_issues_for_extension
import copy
import hashlib
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping, Optional
from fruth_core.transports import strip_enclosing_text_artifact_fence
from fruth_server.recovery_contract import RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT


_TERMINAL_SYNTAX_REPAIR_EXTENSIONS = {'html', 'htm', 'css', 'json'}

@dataclass(frozen=True)
class TextArtifactFiles:
    collect_artifact_records: Callable[[Mapping[str, Any]], list[dict[str, Any]]]
    artifact_outputs_documents_dir: Path

    @classmethod
    def _text_artifact_revision_source_payload(
        cls,
        branch: Mapping[str, Any],
        artifact_gap: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Build one bounded, complete source snapshot for an explicit edit."""

        if not text_artifact_materialization._text_artifact_revision_required(branch, artifact_gap):
            return {}
        target_path = (
            LinkedArtifactMaterialization._text_artifact_target_path_from_mapping(branch)
            or LinkedArtifactMaterialization._text_artifact_target_path_from_mapping(artifact_gap)
        )
        if not target_path:
            return {
                'branch_contract_error': 'text_revision_source_unavailable',
                'materialization_blocked': True,
                'repair_action': RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT,
                'text_artifact_revision_binding_state': 'missing_target_path',
            }
        try:
            target = Path(target_path).expanduser()
            size_bytes = target.stat().st_size if target.is_file() else -1
            if size_bytes < 0:
                raise OSError('revision source is not a file')
            # A partial source packet cannot uphold "keep the rest intact".
            # Fail closed instead of truncating large files in the model prompt.
            if size_bytes > 90_000:
                return {
                    'branch_contract_error': 'text_revision_source_exceeds_prompt_bound',
                    'materialization_blocked': True,
                    'repair_action': RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT,
                    'text_artifact_revision_binding_state': 'source_too_large',
                    'text_artifact_revision_source_size_bytes': size_bytes,
                }
            source_content = target.read_text(encoding='utf-8', errors='replace')
        except OSError:
            return {
                'branch_contract_error': 'text_revision_source_unavailable',
                'materialization_blocked': True,
                'repair_action': RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT,
                'text_artifact_revision_binding_state': 'source_unreadable',
            }
        if not source_content:
            return {
                'branch_contract_error': 'text_revision_source_unavailable',
                'materialization_blocked': True,
                'repair_action': RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT,
                'text_artifact_revision_binding_state': 'source_empty',
            }
        return {
            'content_payload': source_content,
            'content_payload_source': 'canonical_predecessor_text_artifact_snapshot',
            'text_artifact_revision_required': True,
            'text_artifact_source_is_input': True,
            'text_artifact_revision_binding_state': 'bound',
            'text_artifact_revision_source_path': target_path,
            'text_artifact_revision_source_size_bytes': size_bytes,
            'text_artifact_revision_source_sha256': hashlib.sha256(
                source_content.encode('utf-8')
            ).hexdigest(),
            'dependency_payload_policy': 'preserve_text_artifact_revision_source',
            'suppress_reference_file_context': True,
        }

    @classmethod
    def _target_bound_saved_text_syntax_repair_evidence(
        cls,
        recovery_context: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(recovery_context, Mapping):
            return {}
        if str(recovery_context.get('error_code') or '').strip().upper() != (
            'TEXT_ARTIFACT_SYNTAX_SANITY_FAILED'
        ):
            return {}
        if recovery_context.get('target_bound_syntax_repair') is not True:
            return {}
        target_path = str(
            recovery_context.get('saved_text_path')
            or recovery_context.get('text_artifact_target_path')
            or ''
        ).strip()
        if not target_path:
            return {}
        target = Path(target_path).expanduser()
        try:
            if not target.is_file() or target.stat().st_size > 512_000:
                return {}
            current_content = target.read_text(
                encoding='utf-8',
                errors='replace',
            )
        except OSError:
            return {}
        extension = re.sub(
            r'[^a-zA-Z0-9]+',
            '',
            str(
                recovery_context.get('text_artifact_extension')
                or target.suffix
                or ''
            ).strip().lower().lstrip('.'),
        )
        current_issues = (
            text_artifact_syntax_sanity_issues_for_extension(
                extension,
                strip_enclosing_text_artifact_fence(
                    current_content,
                    extension,
                ),
            )
        )
        if not current_issues:
            return {}
        reported_issues = [
            str(issue).strip()
            for issue in (recovery_context.get('syntax_sanity_issues') or [])
            if str(issue).strip()
        ] if isinstance(recovery_context.get('syntax_sanity_issues'), list) else []
        if not reported_issues:
            return {}
        source_name = str(
            recovery_context.get('text_artifact_source_name')
            or target.stem
            or ''
        ).strip()
        content_payload = '\n'.join(
            [
                f'Target text artifact: {target_path}',
                'Deterministic syntax sanity issues:',
                *[f'- {issue}' for issue in reported_issues],
                *text_artifact_syntax._bounded_repair_content_block(
                    'Current saved target file content',
                    current_content,
                ),
                (
                    'Update only the target text artifact. Preserve valid runtime '
                    'artifact links, copy, and layout intent. Fix the syntax defects '
                    'above before closure.'
                ),
            ]
        ).strip()
        if not content_payload:
            return {}
        return {
            'target_path': target_path,
            'extension': extension,
            'source_name': source_name,
            'syntax_sanity_issues': reported_issues,
            'current_syntax_sanity_issues': current_issues,
            'content_payload': content_payload,
        }

    @staticmethod
    def _sha256_for_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open('rb') as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                digest.update(chunk)
        return digest.hexdigest()

    def _materialize_retained_input_alias(
        self,
        plan: Mapping[str, Any],
        contract: Mapping[str, Any],
    ) -> dict[str, Any]:
        binding_state = str(contract.get('retained_input_binding_state') or '').strip().lower()
        source_path = str(contract.get('retained_input_source_path') or '').strip()
        source_name = str(contract.get('retained_input_source_name') or '').strip()
        target_name = Path(
            str(contract.get('retained_input_target_name') or '').strip()
        ).name
        extension = re.sub(
            r'[^a-zA-Z0-9]+',
            '',
            str(
                contract.get('text_artifact_extension')
                or Path(target_name).suffix
                or ''
            ).strip().lower().lstrip('.'),
        )
        logical_source_name = str(
            contract.get('text_artifact_source_name')
            or Path(target_name).stem
            or 'retained-input'
        ).strip()
        if binding_state != 'bound' or not source_path:
            raise RuntimeError(
                'RETAINED_INPUT_ALIAS_UNBOUND: the requested retained input '
                'does not resolve to exactly one current input artifact.'
            )
        if (
            not target_name
            or target_name != str(contract.get('retained_input_target_name') or '').strip()
            or not extension
            or Path(target_name).suffix.lower().lstrip('.') != extension
        ):
            raise RuntimeError(
                'RETAINED_INPUT_ALIAS_TARGET_INVALID: retained input target '
                'must be one safe filename whose extension matches the contract.'
            )
        source = Path(source_path).expanduser()
        try:
            source = source.resolve(strict=True)
        except OSError as exc:
            raise RuntimeError(
                'RETAINED_INPUT_ALIAS_SOURCE_MISSING: retained input source is unavailable.'
            ) from exc
        if not source.is_file():
            raise RuntimeError(
                'RETAINED_INPUT_ALIAS_SOURCE_MISSING: retained input source is not a file.'
            )
        admitted_source_paths: set[Path] = set()
        branch_wrapper = plan.get('branch') if isinstance(plan.get('branch'), Mapping) else {}
        branch_payload = (
            branch_wrapper.get('branch')
            if isinstance(branch_wrapper.get('branch'), Mapping)
            else branch_wrapper
        )
        for carrier in (plan.get('effective_data'), branch_payload):
            if not isinstance(carrier, Mapping):
                continue
            for record in carrier.get('input_artifacts') or []:
                if not isinstance(record, Mapping):
                    continue
                admitted_path = str(
                    record.get('path')
                    or record.get('source_path')
                    or record.get('saved_text_path')
                    or ''
                ).strip()
                if not admitted_path:
                    continue
                try:
                    admitted_source_paths.add(
                        Path(admitted_path).expanduser().resolve(strict=False)
                    )
                except (OSError, ValueError):
                    continue
            for key in ('file_path', 'route_artifact_path'):
                admitted_path = str(carrier.get(key) or '').strip()
                if not admitted_path:
                    continue
                try:
                    admitted_source_paths.add(
                        Path(admitted_path).expanduser().resolve(strict=False)
                    )
                except (OSError, ValueError):
                    continue
        if source not in admitted_source_paths:
            raise RuntimeError(
                'RETAINED_INPUT_ALIAS_SOURCE_NOT_ADMITTED: retained input source '
                'must be one exact current input artifact.'
            )
        if source_name and Path(source_name).suffix.lower().lstrip('.') != extension:
            raise RuntimeError(
                'RETAINED_INPUT_ALIAS_EXTENSION_MISMATCH: retained input source '
                'and requested target have different text-artifact extensions.'
            )

        try:
            source_content = source.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError) as exc:
            raise RuntimeError(
                'RETAINED_INPUT_ALIAS_SOURCE_INVALID: retained input must be a readable text artifact.'
            ) from exc
        _canonical_content, content_error = text_artifact_materialization._text_artifact_content_payload_error(
            source_content,
            extension=extension,
            saved_path=str(source),
        )
        if content_error:
            raise RuntimeError(
                f"{content_error.get('code') or 'RETAINED_INPUT_ALIAS_SOURCE_INVALID'}: "
                f"{content_error.get('message') or 'retained input source failed validation'}"
            )

        source_sha256 = self._sha256_for_file(source)
        allocation_digest = hashlib.sha256(
            ('\0'.join((str(source), target_name, source_sha256))).encode('utf-8')
        ).hexdigest()[:16]
        target_dir = self.artifact_outputs_documents_dir / (
            f'retained_input_{allocation_digest}'
        )
        target = target_dir / target_name
        target_dir.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if not target.is_file() or self._sha256_for_file(target) != source_sha256:
                raise RuntimeError(
                    'RETAINED_INPUT_ALIAS_TARGET_COLLISION: allocated target '
                    'already exists with different bytes.'
                )
        else:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f'.{target_name}.',
                suffix='.tmp',
                dir=str(target_dir),
            )
            os.close(descriptor)
            temporary = Path(temporary_name)
            try:
                shutil.copyfile(source, temporary)
                if self._sha256_for_file(temporary) != source_sha256:
                    raise RuntimeError(
                        'RETAINED_INPUT_ALIAS_COPY_MISMATCH: copied bytes do not match the input.'
                    )
                os.replace(temporary, target)
            finally:
                try:
                    if temporary.exists():
                        temporary.unlink()
                except OSError:
                    pass

        target_sha256 = self._sha256_for_file(target)
        if target_sha256 != source_sha256:
            raise RuntimeError(
                'RETAINED_INPUT_ALIAS_COPY_MISMATCH: materialized target is not byte-identical.'
            )
        saved_error = text_artifact_materialization._text_artifact_saved_payload_error(
            str(target),
            extension=extension,
        )
        if saved_error:
            raise RuntimeError(
                f"{saved_error.get('code') or 'RETAINED_INPUT_ALIAS_TARGET_INVALID'}: "
                f"{saved_error.get('message') or 'retained input target failed validation'}"
            )

        artifact_request = text_artifact_materialization._required_text_artifact_request(
            contract,
            {},
            {},
            extension=extension,
            source_name=logical_source_name,
            target_path=str(target),
        )
        artifact_request.update(
            {
                'source': 'retained_input_alias',
                'target_path': str(target),
                'retained_input_alias_required': True,
                'retained_input_binding_state': 'bound',
                'retained_input_source_path': str(source),
                'retained_input_source_name': source_name or source.name,
                'retained_input_target_name': target_name,
            }
        )
        result = text_artifact_materialization._with_required_text_artifact_saved_result(
            {},
            target_path=str(target),
            content=source_content,
            extension=extension,
            source_name=logical_source_name,
            artifact_request=artifact_request,
            evidence='retained_input_alias_byte_copy',
        )
        result.update(
            {
                'retained_input_alias_required': True,
                'retained_input_binding_state': 'bound',
                'retained_input_source_path': str(source),
                'retained_input_source_name': source_name or source.name,
                'retained_input_target_name': target_name,
                'retained_input_source_sha256': source_sha256,
                'retained_input_target_sha256': target_sha256,
                'retained_input_byte_identical': True,
            }
        )
        for record in result.get('saved_text_artifacts') or []:
            if not isinstance(record, dict):
                continue
            record.update(
                {
                    'retained_input_source_path': str(source),
                    'retained_input_source_name': source_name or source.name,
                    'retained_input_target_name': target_name,
                    'retained_input_source_sha256': source_sha256,
                    'retained_input_target_sha256': target_sha256,
                    'retained_input_byte_identical': True,
                }
            )
        return result

    def _repair_terminal_text_artifact_syntax(
        self,
        payload: dict[str, Any],
        *,
        accepted_fill_results: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return payload
        records = self.collect_artifact_records(payload)
        text_records = LinkedArtifactMaterialization._unique_artifact_records_by_path(
            [
                record
                for record in records
                if str(record.get('type') or record.get('kind') or '').strip().lower() == 'text'
                and branch_result_contracts._artifact_record_extension(record) in _TERMINAL_SYNTAX_REPAIR_EXTENSIONS
                and branch_result_contracts._artifact_record_path(record)
            ]
        )
        if not text_records:
            return payload

        updated_payload = dict(payload or {})
        updated_content_by_path: dict[str, str] = {}
        repair_entries: list[dict[str, Any]] = []
        for record in text_records:
            target_path = branch_result_contracts._artifact_record_path(record)
            extension = branch_result_contracts._artifact_record_extension(record)
            try:
                target = Path(target_path).expanduser()
                if not target.is_file() or target.stat().st_size > 512_000:
                    continue
                original = target.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            repaired, repairs = repair_text_artifact_syntax_content(
                extension,
                original,
            )
            if not repairs or repaired == original:
                continue
            try:
                target.write_text(repaired, encoding='utf-8')
            except OSError as exc:
                logging.warning('Could not repair syntax in %s artifact %s: %s', extension, target_path, exc)
                continue
            updated_content_by_path[target_path] = repaired
            repair_entries.append(
                {
                    'kind': 'fruth.text_artifact_syntax_repair',
                    'target_path': target_path,
                    'target_extension': extension,
                    'target_source_name': branch_result_contracts._artifact_record_source_name(record),
                    'repair_count': len(repairs),
                    'repairs': repairs,
                    'status': 'applied',
                    'source': 'terminal_late_fill_syntax_repair',
                }
            )

        if not repair_entries:
            return updated_payload

        def update_text_record_content(raw_record: Any) -> Any:
            if not isinstance(raw_record, dict):
                return raw_record
            record = dict(raw_record)
            path = branch_result_contracts._artifact_record_path(record)
            if path in updated_content_by_path:
                record['content'] = updated_content_by_path[path]
                if 'result_text' in record:
                    record['result_text'] = updated_content_by_path[path]
                if 'content_payload' in record:
                    record['content_payload'] = updated_content_by_path[path]
            return record

        if isinstance(updated_payload.get('artifacts'), list):
            updated_payload['artifacts'] = [
                update_text_record_content(item)
                for item in updated_payload.get('artifacts') or []
            ]
        if isinstance(updated_payload.get('saved_text_artifacts'), list):
            updated_payload['saved_text_artifacts'] = [
                update_text_record_content(item)
                for item in updated_payload.get('saved_text_artifacts') or []
            ]
        late_fill = (
            dict(updated_payload.get('late_fill') or {})
            if isinstance(updated_payload.get('late_fill'), Mapping)
            else {}
        )
        if isinstance(late_fill.get('fill_results'), list):
            late_fill['fill_results'] = [
                copy.deepcopy(item) if item in (accepted_fill_results or [])
                else update_text_record_content(item)
                for item in late_fill.get('fill_results') or []
            ]
        existing_repairs = [
            dict(item)
            for item in (late_fill.get('syntax_sanity_repairs') or [])
            if isinstance(item, Mapping)
        ]
        late_fill['syntax_sanity_repairs'] = [*existing_repairs, *repair_entries]
        late_fill['syntax_sanity_repair_status'] = 'applied'
        late_fill['syntax_sanity_repaired_paths'] = [
            entry.get('target_path')
            for entry in repair_entries
            if entry.get('target_path')
        ]
        updated_payload['late_fill'] = late_fill
        return updated_payload

