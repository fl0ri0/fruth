"""Materialize a declared text artifact at its exact accepted target.

Owns payload validation, preservation checks and the concrete target write.
Returned saved-file records are candidates: branch result acceptance, cancellation
and terminal Closure remain with their respective runtime owners.
"""

from __future__ import annotations

from fruth_server.late_fill_selection import LateFillSelection
from fruth_services import branch_result_contracts
from fruth_services.text_artifact_syntax import repair_text_artifact_syntax_content
from fruth_services.text_artifact_syntax import text_artifact_syntax_sanity_issues_for_extension
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any, Mapping, Optional
from fruth_core.text_artifacts import TEXT_ARTIFACT_EXTENSIONS, extract_text_artifact_payloads
from fruth_core.transports import (
    strip_enclosing_text_artifact_fence,
    text_artifact_content_is_materializer_instruction_echo,
)
from fruth_server.recovery_contract import RECOVERY_ACTION_RETRY_SAME_BRANCH


def _text_artifact_revision_required(*payloads: Mapping[str, Any]) -> bool:
    """Return whether existing text bytes are an edit input, not output proof."""

    revision_sources = {
        'canonical_predecessor_artifact',
        'history_source_edit',
        'selected_source_edit',
        'selected_text_source_edit',
    }
    for payload in payloads:
        if not isinstance(payload, Mapping):
            continue
        sources: list[Mapping[str, Any]] = [payload]
        for key in ('artifact_request', 'text_artifact_request', 'execution_contract'):
            nested = payload.get(key)
            if isinstance(nested, Mapping):
                sources.append(nested)
        for source in sources:
            if (
                source.get('text_artifact_revision_required') is True
                or source.get('text_artifact_source_is_input') is True
            ):
                return True
            provenance = str(
                source.get('text_artifact_revision_source')
                or source.get('text_artifact_source')
                or source.get('source')
                or ''
            ).strip().lower()
            if provenance in revision_sources:
                return True
    return False


def _text_artifact_revision_anchor_tokens(
    content: Any,
    extension: str,
) -> set[str]:
    """Return stable structural anchors suitable for truncation detection."""

    text = str(content or '')
    normalized_extension = str(extension or '').strip().lower().lstrip('.')
    anchors: set[str] = set()
    if normalized_extension in {'html', 'htm'}:
        for match in re.finditer(
            r'\b(?P<kind>id|class)\s*=\s*(?P<quote>["\'])(?P<value>.*?)(?P=quote)',
            text,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            kind = str(match.group('kind') or '').lower()
            for token in re.split(r'\s+', str(match.group('value') or '').strip()):
                normalized = token.strip().lower()
                if normalized:
                    anchors.add(f'{kind}:{normalized}')
        return anchors
    if normalized_extension == 'css':
        without_comments = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
        for match in re.finditer(r'(?P<selectors>[^{}]+)\{', without_comments, flags=re.DOTALL):
            selectors = str(match.group('selectors') or '').strip()
            if not selectors:
                continue
            for token_match in re.finditer(
                r'(?<![\w-])(?P<token>[.#][A-Za-z_][A-Za-z0-9_-]*)',
                selectors,
            ):
                anchors.add(f'selector:{token_match.group("token").lower()}')
        return anchors
    if normalized_extension == 'json':
        try:
            decoded = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            return anchors

        def visit(value: Any, path: tuple[str, ...]) -> None:
            if isinstance(value, Mapping):
                for raw_key, child in value.items():
                    key = str(raw_key)
                    child_path = (*path, key)
                    anchors.add(f'json:{".".join(child_path)}')
                    visit(child, child_path)
            elif isinstance(value, list):
                for child in value:
                    visit(child, (*path, '[]'))

        visit(decoded, ())
    return anchors


def _text_artifact_revision_preservation_review(
    source_content: Any,
    candidate_content: Any,
    *,
    extension: str,
    target_path: str,
) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
    """Fail closed when a preserve-scoped revision drops unrelated structure."""

    source = strip_enclosing_text_artifact_fence(
        str(source_content or ''),
        extension,
    ).strip()
    candidate = strip_enclosing_text_artifact_fence(
        str(candidate_content or ''),
        extension,
    ).strip()
    source_anchors = _text_artifact_revision_anchor_tokens(source, extension)
    candidate_anchors = _text_artifact_revision_anchor_tokens(candidate, extension)
    retained_anchors = source_anchors.intersection(candidate_anchors)
    missing_anchors = sorted(source_anchors.difference(candidate_anchors))
    anchor_retention = (
        len(retained_anchors) / len(source_anchors)
        if source_anchors
        else 1.0
    )
    size_retention = len(candidate) / len(source) if source else 1.0
    source_failure = not source
    anchor_failure = len(source_anchors) >= 5 and anchor_retention < 0.78
    size_failure = len(source) >= 800 and size_retention < 0.50
    evidence = {
        'kind': 'fruth.text_artifact_revision_preservation_evidence',
        'version': 1,
        'policy': 'structural_anchor_retention_v1',
        'status': 'failed' if source_failure or anchor_failure or size_failure else 'passed',
        'target_path': target_path,
        'text_artifact_extension': str(extension or '').strip().lower().lstrip('.') or None,
        'source_size_chars': len(source),
        'candidate_size_chars': len(candidate),
        'size_retention_ratio': round(size_retention, 6),
        'source_anchor_count': len(source_anchors),
        'retained_anchor_count': len(retained_anchors),
        'anchor_retention_ratio': round(anchor_retention, 6),
        'missing_anchors': missing_anchors[:24],
        'failure_reason': (
            'source_snapshot_unavailable'
            if source_failure
            else 'structural_anchor_loss'
            if anchor_failure
            else 'severe_size_loss'
            if size_failure
            else None
        ),
    }
    if evidence['status'] == 'passed':
        return evidence, None
    return evidence, {
        'code': 'TEXT_ARTIFACT_REVISION_PRESERVATION_FAILED',
        'message': (
            'Required text artifact revision removed too much pre-existing structure despite an '
            'explicit preservation instruction. The source file remains authoritative until a '
            'complete branch-produced revision passes structural retention.'
        ),
        'target_path': target_path,
        'text_artifact_extension': evidence['text_artifact_extension'],
        'text_artifact_revision_preservation_evidence': evidence,
        'suggested_action': RECOVERY_ACTION_RETRY_SAME_BRANCH,
        'retryable': True,
    }


def _artifact_gap_is_authoritative_bounded_text_artifact_repair(
    artifact_gap: Optional[Mapping[str, Any]],
) -> bool:
    gap = artifact_gap if isinstance(artifact_gap, Mapping) else {}
    artifact_request = (
        gap.get('artifact_request')
        if isinstance(gap.get('artifact_request'), Mapping)
        else {}
    )
    target_path = str(
        gap.get('text_artifact_target_path')
        or artifact_request.get('target_path')
        or ''
    ).strip()
    if not target_path:
        return False
    # Repair identity survives retry-action changes and compact projections.
    # Execution permission is checked separately by the execution gate.
    content_payload_source = str(gap.get('content_payload_source') or '').strip()
    text_artifact_source = str(
        gap.get('text_artifact_source')
        or artifact_request.get('source')
        or ''
    ).strip()
    authoritative_source = (
        content_payload_source in {
            'closure_html_css_selector_binding_review',
            'closure_linked_artifact_binding_review',
            'closure_local_dependency_link_review',
            'closure_composed_page_image_representation',
            'closure_composed_site_image_composition',
            'closure_hero_image_composition',
            'closure_text_artifact_syntax_sanity',
            'terminal_web_runtime_binding_review',
        }
        or text_artifact_source in {
            'closure_link_rebind',
            'closure_local_dependency_link',
            'closure_composed_page_image_representation',
            'closure_composed_site_image_composition',
            'closure_hero_image_composition',
            'closure_selector_binding_repair',
            'closure_syntax_repair',
            'closure_web_binding_repair',
        }
    )
    if not authoritative_source:
        return False
    if LateFillSelection._artifact_gap_is_required_text_materialization(gap):
        return True
    # Persisted pending branches are intentionally compact and may omit
    # stage_direction/requires_artifact.  A target-bound Closure repair
    # remains authoritative when its artifact request preserves the file
    # identity, extension, recovery action, and repair provenance.
    extension = str(
        gap.get('text_artifact_extension')
        or artifact_request.get('extension')
        or Path(target_path).suffix
        or ''
    ).strip().lower().lstrip('.')
    return extension in TEXT_ARTIFACT_EXTENSIONS


def _normalized_text_artifact_path_for_match(path: Any) -> str:
    token = str(path or '').strip()
    if not token:
        return ''
    try:
        return str(Path(token).expanduser().resolve(strict=False))
    except OSError:
        return str(Path(token).expanduser())


def _text_artifact_path_matches_target(path: Any, target_path: Any) -> bool:
    normalized_path = _normalized_text_artifact_path_for_match(path)
    normalized_target = _normalized_text_artifact_path_for_match(target_path)
    return bool(normalized_path and normalized_target and normalized_path == normalized_target)


def _text_artifact_candidate_content(record: Mapping[str, Any]) -> str:
    for key in ('result_text', 'content', 'content_payload', 'output_text'):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ''


def _text_artifact_nested_mapping(source: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = source.get(key) if isinstance(source, Mapping) else {}
    return value if isinstance(value, Mapping) else {}


def _required_text_artifact_target_path(
    branch: Mapping[str, Any],
    infer_result: Mapping[str, Any],
    effective_data: Mapping[str, Any],
) -> str:
    mappings: list[Mapping[str, Any]] = [
        source
        for source in (branch, effective_data, infer_result)
        if isinstance(source, Mapping)
    ]

    def target_from_mapping(source: Mapping[str, Any]) -> str:
        direct = str(source.get('text_artifact_target_path') or source.get('target_path') or '').strip()
        if direct:
            return direct
        for request_key in ('artifact_request', 'text_artifact_request'):
            request_payload = _text_artifact_nested_mapping(source, request_key)
            request_target = str(
                request_payload.get('target_path')
                or request_payload.get('text_artifact_target_path')
                or ''
            ).strip()
            if request_target:
                return request_target
        execution_contract = _text_artifact_nested_mapping(source, 'execution_contract')
        if execution_contract:
            nested_target = target_from_mapping(execution_contract)
            if nested_target:
                return nested_target
        return ''

    for source in mappings:
        target_path = target_from_mapping(source)
        if target_path:
            return target_path
    return ''


def _required_text_artifact_request(
    branch: Mapping[str, Any],
    infer_result: Mapping[str, Any],
    effective_data: Mapping[str, Any],
    *,
    extension: str,
    source_name: str,
    target_path: str,
) -> dict[str, Any]:
    for source in (branch, effective_data, infer_result):
        if not isinstance(source, Mapping):
            continue
        for key in ('artifact_request', 'text_artifact_request'):
            request_payload = source.get(key)
            if isinstance(request_payload, Mapping):
                request = dict(request_payload)
                if extension and not request.get('extension'):
                    request['extension'] = extension
                if source_name and not request.get('source_name'):
                    request['source_name'] = source_name
                if target_path and not request.get('target_path'):
                    request['target_path'] = target_path
                return request
        execution_contract = source.get('execution_contract')
        if isinstance(execution_contract, Mapping):
            request = _required_text_artifact_request(
                execution_contract,
                {},
                {},
                extension=extension,
                source_name=source_name,
                target_path=target_path,
            )
            if request:
                return request
    request: dict[str, Any] = {}
    if extension:
        request['extension'] = extension
    if source_name:
        request['source_name'] = source_name
    if target_path:
        request['target_path'] = target_path
    return request


def _text_artifact_content_payload_error(
    content: Any,
    *,
    extension: str = '',
    saved_path: str = '',
) -> tuple[str, Optional[dict[str, Any]]]:
    raw_content = str(content or '').strip()
    normalized_extension = re.sub(
        r'[^a-zA-Z0-9]+',
        '',
        str(extension or Path(str(saved_path or '')).suffix).strip().lower().lstrip('.'),
    )
    unwrapped = strip_enclosing_text_artifact_fence(raw_content, normalized_extension).strip()
    if not unwrapped:
        return '', None
    if text_artifact_content_is_materializer_instruction_echo(unwrapped):
        return unwrapped, {
            'code': 'TEXT_ARTIFACT_INSTRUCTION_ECHO',
            'message': (
                'Required text artifact branch returned internal materializer instructions instead of a file payload. '
                'The branch remains repairable; instruction echoes do not fulfill local artifact obligations.'
            ),
            'saved_text_path': saved_path or None,
            'text_artifact_extension': normalized_extension or None,
            'suggested_action': RECOVERY_ACTION_RETRY_SAME_BRANCH,
            'retryable': True,
        }
    if not _text_artifact_candidate_looks_like_payload(unwrapped, normalized_extension):
        return '', None
    syntax_issues = text_artifact_syntax_sanity_issues_for_extension(
        normalized_extension,
        unwrapped,
    )
    if syntax_issues:
        return unwrapped, {
            'code': 'TEXT_ARTIFACT_SYNTAX_SANITY_FAILED',
            'message': (
                'Required text artifact repair content still fails syntax sanity. '
                'The target file is not fulfilled until saved artifact bytes pass syntax checks.'
            ),
            'saved_text_path': saved_path or None,
            'text_artifact_extension': normalized_extension or None,
            'syntax_sanity_status': 'issues',
            'syntax_sanity_issue_count': len(syntax_issues),
            'syntax_sanity_issues': syntax_issues[:12],
            'suggested_action': RECOVERY_ACTION_RETRY_SAME_BRANCH,
            'retryable': True,
        }
    return unwrapped, None


def _text_artifact_candidate_looks_like_payload(content: str, extension: str) -> bool:
    text = str(content or '').lstrip()
    if not text:
        return False
    ext = str(extension or '').strip().lower().lstrip('.')
    if ext in {'html', 'htm'}:
        return bool(re.match(r'(?is)^(?:<!doctype\s+html\b|<html\b|<[A-Za-z][\w:.-]*(?:\s|>|/))', text))
    if ext == 'css':
        return bool(re.search(r'[{};]', text)) and not re.match(
            r'(?is)^(?:here\s+is|this\s+is|the\s+(?:fixed|repaired)|i\s+(?:fixed|updated))\b',
            text,
        )
    if ext == 'json':
        return text.startswith(('{', '['))
    if ext in {'js', 'mjs', 'cjs', 'ts', 'tsx', 'jsx'}:
        return bool(re.match(r'(?m)^\s*(?:import|export|const|let|var|function|class|interface|type)\b', text))
    return True


def _required_text_artifact_candidate_payloads(
    branch: Mapping[str, Any],
    infer_result: Mapping[str, Any],
    effective_data: Mapping[str, Any],
    *,
    extension: str,
    source_name: str,
    target_path: str,
    revision_required: bool = False,
    authoritative_bounded_repair: bool = False,
) -> list[str]:
    request = _required_text_artifact_request(
        branch,
        infer_result,
        effective_data,
        extension=extension,
        source_name=source_name,
        target_path=target_path,
    )
    candidates: list[str] = []
    seen: set[str] = set()

    def append_candidate(value: Any) -> None:
        if not isinstance(value, str) or not value.strip():
            return
        text = value.strip()
        if text in seen:
            return
        seen.add(text)
        candidates.append(text)

    def append_file_candidate(path_value: Any) -> None:
        path = str(path_value or '').strip()
        if not path:
            return
        if (
            (revision_required or authoritative_bounded_repair)
            and _text_artifact_path_matches_target(path, target_path)
        ):
            # The target already existed before this branch. Its bytes are
            # source evidence, not proof that the backend produced output.
            return
        try:
            target = Path(path).expanduser()
            if not target.is_file() or target.stat().st_size > 512_000:
                return
            append_candidate(target.read_text(encoding='utf-8', errors='replace'))
        except OSError:
            return

    def append_source_candidates(source: Mapping[str, Any]) -> None:
        append_file_candidate(source.get('saved_text_path'))
        for raw_record in source.get('saved_text_artifacts') or []:
            if not isinstance(raw_record, Mapping):
                continue
            append_file_candidate(raw_record.get('path') or raw_record.get('saved_text_path'))
            append_candidate(_text_artifact_candidate_content(raw_record))
        for key in ('content', 'content_payload', 'result_text', 'output_text'):
            append_candidate(source.get(key))

    candidate_sources = (
        (infer_result,)
        if revision_required or authoritative_bounded_repair
        else (infer_result, effective_data, branch)
    )
    for source in candidate_sources:
        if isinstance(source, Mapping):
            append_source_candidates(source)

    payloads: list[str] = []
    for candidate in candidates:
        extracted_payloads = extract_text_artifact_payloads(candidate, [request] if request else [])
        extracted = [
            str(item.get('content') or '').strip()
            for item in extracted_payloads
            if isinstance(item, Mapping) and str(item.get('content') or '').strip()
        ]
        if extracted:
            payloads.extend(extracted)
            continue
        payloads.append(candidate)
    return payloads


def _with_required_text_artifact_saved_result(
    infer_result: Mapping[str, Any],
    *,
    target_path: str,
    content: str,
    extension: str,
    source_name: str,
    artifact_request: Mapping[str, Any],
    evidence: str,
) -> dict[str, Any]:
    updated = dict(infer_result)
    record = {
        'type': 'text',
        'kind': 'text',
        'path': target_path,
        'saved_text_path': target_path,
        'content': content,
        'content_payload': content,
        'text_artifact_extension': extension or Path(target_path).suffix.lstrip('.'),
        'text_artifact_source_name': source_name or Path(target_path).stem,
        'text_artifact_source': evidence,
        'artifact_request': dict(artifact_request or {}),
        'evidence': evidence,
    }
    updated['saved_text_path'] = target_path
    updated['text_artifact_target_path'] = target_path
    updated['text_artifact_extension'] = extension or record['text_artifact_extension']
    updated['text_artifact_source_name'] = source_name or record['text_artifact_source_name']
    updated['text_artifact_source'] = evidence
    updated['content'] = content
    updated['content_payload'] = content
    updated['result_text'] = content
    existing_records = []
    for item in updated.get('saved_text_artifacts') or []:
        if not isinstance(item, dict):
            continue
        item_path = str(item.get('path') or item.get('saved_text_path') or '').strip()
        if item_path and _text_artifact_path_matches_target(item_path, target_path):
            existing_records.append(item)
    updated['saved_text_artifacts'] = branch_result_contracts.merge_unique_artifact_records(existing_records, [record])
    return updated


def _materialize_required_text_artifact_target_path(
    branch: Mapping[str, Any],
    infer_result: dict[str, Any],
    effective_data: Mapping[str, Any],
    *,
    extension: str,
    source_name: str,
) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
    target_path = _required_text_artifact_target_path(branch, {}, effective_data)
    if not target_path:
        return infer_result, None
    normalized_extension = re.sub(
        r'[^a-zA-Z0-9]+',
        '',
        str(extension or Path(target_path).suffix).strip().lower().lstrip('.'),
    )
    artifact_request = _required_text_artifact_request(
        branch,
        {},
        effective_data,
        extension=normalized_extension,
        source_name=source_name,
        target_path=target_path,
    )
    target_binding_error = _text_artifact_target_binding_violation(
        infer_result,
        target_path=target_path,
        extension=normalized_extension,
        source_name=source_name,
    )
    revision_required = _text_artifact_revision_required(
        branch,
        effective_data,
        infer_result,
        artifact_request,
    )
    authoritative_bounded_repair = any(
        _artifact_gap_is_authoritative_bounded_text_artifact_repair(source)
        for source in (branch, effective_data, infer_result)
        if isinstance(source, Mapping)
    )
    revision_preservation_required = bool(
        revision_required
        and (
            branch.get('text_artifact_revision_preservation_required') is True
            or effective_data.get('text_artifact_revision_preservation_required') is True
        )
    )

    target = Path(target_path).expanduser()
    revision_source_content = ''
    if revision_preservation_required:
        for source in (effective_data, branch):
            if not isinstance(source, Mapping):
                continue
            if str(source.get('content_payload_source') or '').strip() != (
                'canonical_predecessor_text_artifact_snapshot'
            ):
                continue
            revision_source_content = str(source.get('content_payload') or '')
            if revision_source_content:
                break
        if not revision_source_content and target.is_file():
            try:
                revision_source_content = target.read_text(
                    encoding='utf-8',
                    errors='replace',
                )
            except OSError:
                revision_source_content = ''
    existing_payload_error = _text_artifact_saved_payload_error(
        target_path,
        extension=normalized_extension,
    )
    if (
        not revision_required
        and not authoritative_bounded_repair
        and existing_payload_error is None
        and target.is_file()
    ):
        try:
            content = target.read_text(encoding='utf-8', errors='replace')
        except OSError:
            content = ''
        if content and not target_binding_error:
            return _with_required_text_artifact_saved_result(
                infer_result,
                target_path=target_path,
                content=strip_enclosing_text_artifact_fence(content, normalized_extension).strip(),
                extension=normalized_extension,
                source_name=source_name,
                artifact_request=artifact_request,
                evidence='target_path_saved_text_artifact_evidence',
            ), None

    syntax_repair_source = str(
        branch.get('text_artifact_source')
        or artifact_request.get('source')
        or effective_data.get('text_artifact_source')
        or ''
    ).strip() in {'closure_syntax_repair'} or str(
        branch.get('content_payload_source')
        or effective_data.get('content_payload_source')
        or ''
    ).strip() in {'closure_text_artifact_syntax_sanity'}
    if (
        not revision_required
        and (not authoritative_bounded_repair or syntax_repair_source)
        and
        existing_payload_error
        and existing_payload_error.get('code') == 'TEXT_ARTIFACT_SYNTAX_SANITY_FAILED'
        and target.is_file()
    ):
        try:
            original = target.read_text(encoding='utf-8', errors='replace')
        except OSError:
            original = ''
        if original:
            repaired, repairs = repair_text_artifact_syntax_content(
                normalized_extension,
                original,
            )
            if repairs and repaired != original:
                repaired_content, repaired_error = _text_artifact_content_payload_error(
                    repaired,
                    extension=normalized_extension,
                    saved_path=target_path,
                )
                if not repaired_error and repaired_content:
                    try:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(repaired_content, encoding='utf-8')
                    except OSError as exc:
                        logging.warning(
                            'Could not write deterministic text artifact repair to %s: %s',
                            target_path,
                            exc,
                        )
                    else:
                        saved_error = _text_artifact_saved_payload_error(
                            target_path,
                            extension=normalized_extension,
                        )
                        if not saved_error:
                            updated = _with_required_text_artifact_saved_result(
                                infer_result,
                                target_path=target_path,
                                content=repaired_content,
                                extension=normalized_extension,
                                source_name=source_name,
                                artifact_request=artifact_request,
                                evidence='target_path_deterministic_syntax_repair',
                            )
                            updated['target_path_authoritative_repair'] = {
                                'status': 'applied',
                                'target_path': target_path,
                                'target_extension': normalized_extension or None,
                                'repair_count': len(repairs),
                                'repairs': repairs,
                                'source': 'deterministic_syntax_repair',
                            }
                            return updated, None

    first_candidate_error: Optional[dict[str, Any]] = None
    for candidate in _required_text_artifact_candidate_payloads(
        branch,
        infer_result,
        effective_data,
        extension=normalized_extension,
        source_name=source_name,
        target_path=target_path,
        revision_required=revision_required,
        authoritative_bounded_repair=authoritative_bounded_repair,
    ):
        candidate_content, candidate_error = _text_artifact_content_payload_error(
            candidate,
            extension=normalized_extension,
            saved_path=target_path,
        )
        if candidate_error:
            first_candidate_error = first_candidate_error or candidate_error
            continue
        if not candidate_content:
            continue
        preservation_evidence: dict[str, Any] = {}
        if revision_preservation_required:
            preservation_evidence, preservation_error = (
                _text_artifact_revision_preservation_review(
                    revision_source_content,
                    candidate_content,
                    extension=normalized_extension,
                    target_path=target_path,
                )
            )
            if preservation_error:
                first_candidate_error = first_candidate_error or preservation_error
                continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(candidate_content, encoding='utf-8')
        except OSError as exc:
            logging.warning('Could not write text artifact repair output to %s: %s', target_path, exc)
            continue
        saved_error = _text_artifact_saved_payload_error(target_path, extension=normalized_extension)
        if saved_error:
            first_candidate_error = first_candidate_error or saved_error
            continue
        updated = _with_required_text_artifact_saved_result(
            infer_result,
            target_path=target_path,
            content=candidate_content,
            extension=normalized_extension,
            source_name=source_name,
            artifact_request=artifact_request,
            evidence=(
                'target_path_revision_output'
                if revision_required
                else 'target_path_authoritative_repair_output'
            ),
        )
        if revision_required:
            source_sha256 = str(
                branch.get('text_artifact_revision_source_sha256')
                or effective_data.get('text_artifact_revision_source_sha256')
                or ''
            ).strip()
            write_proof = {
                'kind': 'fruth.text_artifact_revision_write_proof',
                'version': 1,
                'status': 'applied',
                'target_path': target_path,
                'source_sha256': source_sha256 or None,
                'output_sha256': hashlib.sha256(
                    candidate_content.encode('utf-8')
                ).hexdigest(),
                'evidence': 'current_branch_output_written_to_target',
            }
            updated['text_artifact_revision_required'] = True
            updated['text_artifact_source_is_input'] = True
            updated['text_artifact_revision_write_proof'] = {
                key: value
                for key, value in write_proof.items()
                if value not in (None, '')
            }
            if preservation_evidence:
                updated['text_artifact_revision_preservation_evidence'] = (
                    preservation_evidence
                )
        return updated, None

    if first_candidate_error:
        return infer_result, first_candidate_error
    if existing_payload_error:
        return infer_result, existing_payload_error
    if target_binding_error:
        return infer_result, target_binding_error
    if revision_required:
        return infer_result, {
            'code': 'TEXT_ARTIFACT_REVISION_OUTPUT_MISSING',
            'message': (
                'Required text artifact revision returned without a valid branch-produced file body. '
                'The existing source bytes are edit input only and cannot fulfill the revision.'
            ),
            'target_path': target_path,
            'text_artifact_extension': normalized_extension or None,
            'text_artifact_source_name': source_name or None,
            'suggested_action': RECOVERY_ACTION_RETRY_SAME_BRANCH,
            'retryable': True,
        }
    if authoritative_bounded_repair:
        return infer_result, {
            'code': 'TEXT_ARTIFACT_REPAIR_OUTPUT_MISSING',
            'message': (
                'Required bounded text artifact repair returned without a valid '
                'branch-produced file body. Existing target bytes are repair input '
                'only and cannot fulfill the repair obligation.'
            ),
            'target_path': target_path,
            'text_artifact_extension': normalized_extension or None,
            'text_artifact_source_name': source_name or None,
            'suggested_action': RECOVERY_ACTION_RETRY_SAME_BRANCH,
            'retryable': True,
        }
    return infer_result, None


def _text_artifact_saved_payload_error(
    saved_path: str,
    *,
    extension: str = '',
) -> Optional[dict[str, Any]]:
    path = str(saved_path or '').strip()
    if not path:
        return None
    try:
        target = Path(path).expanduser()
        if not target.is_file() or target.stat().st_size > 512_000:
            return None
        content = target.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return None
    normalized_extension = re.sub(
        r'[^a-zA-Z0-9]+',
        '',
        str(extension or target.suffix).strip().lower().lstrip('.'),
    )
    unwrapped = strip_enclosing_text_artifact_fence(content, normalized_extension)
    if text_artifact_content_is_materializer_instruction_echo(unwrapped):
        return {
            'code': 'TEXT_ARTIFACT_INSTRUCTION_ECHO',
            'message': (
                'Required text artifact branch saved internal materializer instructions instead of a file payload. '
                'The branch remains repairable; instruction echoes do not fulfill local artifact obligations.'
            ),
            'saved_text_path': path,
            'text_artifact_extension': normalized_extension or None,
            'suggested_action': RECOVERY_ACTION_RETRY_SAME_BRANCH,
            'retryable': True,
        }
    syntax_issues = text_artifact_syntax_sanity_issues_for_extension(
        normalized_extension,
        unwrapped,
    )
    if syntax_issues:
        return {
            'code': 'TEXT_ARTIFACT_SYNTAX_SANITY_FAILED',
            'message': (
                'Required text artifact branch saved a local file that still fails syntax sanity. '
                'Existing saved paths do not fulfill repair or materialization obligations until the '
                'saved artifact bytes pass syntax checks.'
            ),
            'saved_text_path': path,
            'text_artifact_target_path': path,
            'text_artifact_extension': normalized_extension or None,
            'text_artifact_source_name': target.stem or None,
            'saved_file_syntax_failure': True,
            'syntax_sanity_status': 'issues',
            'syntax_sanity_issue_count': len(syntax_issues),
            'syntax_sanity_issues': syntax_issues[:12],
            'suggested_action': RECOVERY_ACTION_RETRY_SAME_BRANCH,
            'retryable': True,
        }
    return None


def _saved_text_paths_from_result(result: Mapping[str, Any]) -> list[str]:
    if not isinstance(result, Mapping):
        return []
    paths: list[str] = []

    def append_path(value: Any) -> None:
        token = str(value or '').strip()
        if token and token not in paths:
            paths.append(token)

    append_path(result.get('saved_text_path'))
    append_path(result.get('path') if str(result.get('type') or result.get('kind') or '').lower() == 'text' else '')
    for key in ('saved_text_artifacts', 'artifacts'):
        for artifact in result.get(key) or []:
            if not isinstance(artifact, Mapping):
                continue
            if key == 'artifacts' and str(artifact.get('type') or artifact.get('kind') or 'text').lower() != 'text':
                continue
            append_path(artifact.get('path') or artifact.get('saved_text_path'))
    late_fill = result.get('late_fill') if isinstance(result.get('late_fill'), Mapping) else {}
    for fill_result in late_fill.get('fill_results') or []:
        if not isinstance(fill_result, Mapping):
            continue
        append_path(fill_result.get('saved_text_path'))
    return paths


def _text_artifact_target_binding_violation(
    result: Mapping[str, Any],
    *,
    target_path: str,
    extension: str,
    source_name: str,
) -> Optional[dict[str, Any]]:
    target = str(target_path or '').strip()
    if not target:
        return None
    saved_paths = _saved_text_paths_from_result(result)
    if not saved_paths:
        return None
    if any(_text_artifact_path_matches_target(path, target) for path in saved_paths):
        return None
    return {
        'code': 'TEXT_ARTIFACT_TARGET_BINDING_VIOLATION',
        'message': (
            'Required text artifact repair saved or returned a different text artifact path. '
            'Target-bound repairs must update the requested target file; a sibling artifact does not fulfill '
            'the repair or final materialization contract.'
        ),
        'target_path': target,
        'expected_target_path': target,
        'actual_saved_text_path': saved_paths[0],
        'actual_saved_text_paths': saved_paths,
        'text_artifact_extension': extension or None,
        'text_artifact_source_name': source_name or None,
        'evidence': 'text_artifact_target_path_mismatch',
        'suggested_action': RECOVERY_ACTION_RETRY_SAME_BRANCH,
        'retryable': True,
    }
