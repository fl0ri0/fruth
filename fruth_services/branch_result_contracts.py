"""Branch result records, dependency aliases and artifact identity joins.

These transformations consume explicit runtime records and preserve their
identities. They neither read storage nor admit, execute or publish work.
"""

from __future__ import annotations

import re
from dataclasses import field
from pathlib import Path
from typing import Any, Mapping, Optional
from fruth_services.artifact_contracts import sanitize_artifact_record


_PATH_ONLY_DEPENDENCY_EVIDENCE_RE = re.compile(
    r'^\s*(?:/[^ \t\r\n]+|[A-Za-z]:[\\/][^\r\n]+)\s*$'
)


_DEPENDENCY_EVIDENCE_MISSING_CLAIM_RE = re.compile(
    r'\b('
    r'(?:i\s+)?(?:do\s+not|don[\'’]?t|cannot|can[\'’]?t)\s+(?:directly\s+)?(?:access|see|hear|inspect|analy[sz]e)|'
    r'no\s+(?:direct\s+)?access\s+to\s+(?:the\s+)?(?:generated\s+)?(?:audio|image|file|artifact)|'
    r'need\s+(?:a\s+)?(?:description|context|the\s+)?(?:generated\s+)?(?:audio|image|file|artifact)|'
    r'(?:please\s+)?(?:provide|upload|attach|send)\s+(?:an?\s+|the\s+)?(?:generated\s+)?(?:audio|image|file|artifact)[^.!?\n]{0,120}(?:transcribe|compare|analy[sz]e|inspect|process|use|review)?|'
    r'(?:audio|image|file|artifact)\s+(?:file\s+)?you\s+would\s+like\s+me\s+to\s+(?:transcribe|compare|analy[sz]e|inspect|process)|'
    r'keinen?\s+(?:direkten\s+)?zugriff|'
    r'kann\s+(?:ich\s+)?(?:das\s+)?(?:audio|bild|datei|artefakt|die\s+aufnahme|die\s+audiodatei|die\s+bilddatei)?[^.!?\n]{0,80}\b(?:nicht\s+)?(?:beurteilen|analysieren|sehen|hoeren|hören|verarbeiten)|'
    r'ben[oö]tige\s+(?:eine\s+)?(?:beschreibung|kontext|audiodatei|audioaufnahme|bildbeschreibung|bilddatei|datei|artefakt)|'
    r'kein(?:e[nsrm]?)?\s+(?:audio|audiodatei|audioaufnahme|bild|bilddatei|datei|artefakt|transkript)[^.!?\n]{0,120}(?:zur\s+verf[uü]gung\s+gestellt|bereitgestellt|vorhanden|verf[uü]gbar|hochgeladen|erhalten|erstellen)|'
    r'(?:stellen|lade|laden)\s+sie\s+mir\s+(?:das\s+|die\s+)?(?:audio|audiodatei|audioaufnahme|bild|bilddatei|datei|artefakt)[^.!?\n]{0,80}(?:zur\s+verf[uü]gung|hoch|bereit)|'
    r'kein(?:e[nsrm]?)?\s+(?:transkript|analyse|vergleich)[^.!?\n]{0,80}(?:erstellen|liefern|anfertigen|durchf[uü]hren)'
    r')\b',
    re.IGNORECASE,
)


_VISION_GENERATION_REFUSAL_RE = re.compile(
    r'^(?:as\s+[^\n.!?]+,\s*)?i\s+(?:'
    r'generate\s+(?:only\s+text|text\s+only)\b|'
    r'(?:cannot|can[\'’]?t|am\s+unable\s+to)\s+(?:create|generate|produce)\s+(?:any\s+)?images?\b)',
    re.IGNORECASE,
)


def _artifact_record_merge_key(item: Mapping[str, Any]) -> tuple[str, str, str]:
    path = str(item.get('path') or '').strip()
    source_path = str(item.get('source_path') or '').strip()
    if path or source_path:
        return ('path', path, source_path)
    artifact_ref = str(item.get('artifact_ref') or item.get('ref') or '').strip()
    artifact_id = str(item.get('artifact_id') or '').strip()
    if artifact_ref or artifact_id:
        return ('ref', artifact_ref, artifact_id)
    return (
        'fallback',
        str(item.get('type') or item.get('kind') or '').strip().lower(),
        str(item.get('name') or item.get('source_name') or '').strip(),
    )


def _merge_artifact_record_fields(
    existing: dict[str, Any],
    incoming: Mapping[str, Any],
) -> dict[str, Any]:
    for key, value in dict(incoming or {}).items():
        if value in (None, '', [], {}):
            continue
        if existing.get(key) in (None, '', [], {}):
            existing[key] = value
    artifact_ref = str(existing.get('artifact_ref') or '').strip()
    ref = str(existing.get('ref') or '').strip()
    if artifact_ref and not ref:
        existing['ref'] = artifact_ref
    elif ref and not artifact_ref:
        existing['artifact_ref'] = ref
    return existing


def _artifact_record_identity_signature(item: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(item.get('type') or item.get('kind') or '').strip().lower(),
        _artifact_record_path(item),
        str(item.get('source_path') or '').strip(),
        _artifact_record_extension(item),
    )


def _repair_artifact_record_identity(item: Mapping[str, Any]) -> dict[str, Any]:
    repaired = dict(item or {})
    identity_payload = dict(repaired)
    for key in ('artifact_id', 'artifactId', 'id', 'artifact_ref', 'artifactRef', 'ref'):
        identity_payload.pop(key, None)
    canonical = sanitize_artifact_record(
        identity_payload,
        default_kind=str(repaired.get('type') or repaired.get('kind') or '').strip().lower() or None,
        default_origin=str(repaired.get('origin') or '').strip().lower() or None,
    )
    if not canonical:
        return repaired
    for key in ('artifact_id', 'artifact_ref', 'ref'):
        if canonical.get(key):
            repaired[key] = canonical[key]
    return repaired


def _repair_colliding_artifact_record_identities(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    token_to_indexes: dict[tuple[str, str], list[int]] = {}
    for index, item in enumerate(records):
        if not isinstance(item, Mapping):
            continue
        if not _artifact_record_path(item):
            continue
        for field in ('artifact_id', 'artifact_ref', 'ref'):
            token = str(item.get(field) or '').strip()
            if token:
                token_to_indexes.setdefault((field, token), []).append(index)

    indexes_to_repair: set[int] = set()
    for indexes in token_to_indexes.values():
        if len(indexes) < 2:
            continue
        signatures = {
            _artifact_record_identity_signature(records[index])
            for index in indexes
        }
        if len(signatures) > 1:
            indexes_to_repair.update(indexes)
    if not indexes_to_repair:
        return records
    return [
        _repair_artifact_record_identity(item)
        if index in indexes_to_repair
        else item
        for index, item in enumerate(records)
    ]


def merge_unique_artifact_records(
    existing_values: Any,
    incoming_values: Any,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    index_by_key: dict[tuple[str, str, str], int] = {}
    for raw_item in (existing_values or []):
        if not isinstance(raw_item, dict):
            continue
        item = dict(raw_item)
        key = _artifact_record_merge_key(item)
        if key in index_by_key:
            _merge_artifact_record_fields(merged[index_by_key[key]], item)
            continue
        index_by_key[key] = len(merged)
        merged.append(item)
    for raw_item in (incoming_values or []):
        if not isinstance(raw_item, dict):
            continue
        item = dict(raw_item)
        key = _artifact_record_merge_key(item)
        if key in index_by_key:
            _merge_artifact_record_fields(merged[index_by_key[key]], item)
            continue
        index_by_key[key] = len(merged)
        merged.append(item)
    return _repair_colliding_artifact_record_identities(merged)


def artifact_records_from_payload(
    payload: Any,
    key: str,
) -> list[dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return []
    records: list[dict[str, Any]] = []

    def add_records(raw_value: Any) -> None:
        if not isinstance(raw_value, list):
            return
        for raw_item in raw_value:
            if isinstance(raw_item, dict):
                records.append(dict(raw_item))

    add_records(payload.get(key))
    request_payload = payload.get('request') if isinstance(payload.get('request'), Mapping) else {}
    add_records(request_payload.get(key))
    frame_payload = payload.get('response_frame') if isinstance(payload.get('response_frame'), Mapping) else {}
    frame_request = frame_payload.get('request') if isinstance(frame_payload.get('request'), Mapping) else {}
    add_records(frame_request.get(key))
    artifacts_payload = payload.get('artifacts') if isinstance(payload.get('artifacts'), Mapping) else {}
    if key == 'input_artifacts':
        add_records(artifacts_payload.get('input'))
    elif key == 'reference_artifacts':
        add_records(artifacts_payload.get('reference'))
    return records


def merge_late_fill_payload_artifacts(
    late_fill_payload: dict[str, Any],
    *sources: Any,
) -> dict[str, Any]:
    updated = dict(late_fill_payload or {})
    for key in ('input_artifacts', 'reference_artifacts'):
        merged_records = merge_unique_artifact_records(updated.get(key), [])
        for source in sources:
            merged_records = merge_unique_artifact_records(
                merged_records,
                artifact_records_from_payload(source, key),
            )
        if merged_records:
            updated[key] = merged_records
    return updated


def late_fill_text_from_result_payload(payload: Any) -> str:
    if not isinstance(payload, Mapping):
        return ''
    for key in (
        'content_payload',
        'content',
        'output_text',
        'result_text',
        'result',
        'text',
        'transcript',
    ):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    result = payload.get('result')
    if isinstance(result, Mapping):
        for key in ('content', 'output_text', 'text', 'transcript'):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ''


def late_fill_result_has_missing_dependency_evidence(payload: Any) -> bool:
    if not isinstance(payload, Mapping):
        return False
    capability = str(payload.get('capability') or payload.get('expected_capability') or '').strip().lower()
    text = late_fill_text_from_result_payload(payload)
    if capability in {'vision_analysis', 'speech_to_text'} and _PATH_ONLY_DEPENDENCY_EVIDENCE_RE.match(text):
        return True
    if not text:
        return False
    if capability == 'vision_analysis' and _VISION_GENERATION_REFUSAL_RE.search(text):
        return True
    if capability in {'vision_analysis', 'speech_to_text'}:
        return bool(_DEPENDENCY_EVIDENCE_MISSING_CLAIM_RE.search(text))
    if capability == 'chat':
        depends_on = [
            str(item or '').strip()
            for item in (payload.get('depends_on') or payload.get('dependsOn') or [])
            if str(item or '').strip()
        ]
        depends_on_non_root = any(item != 'phase-1' for item in depends_on)
        return depends_on_non_root and bool(_DEPENDENCY_EVIDENCE_MISSING_CLAIM_RE.search(text))
    return False


def late_fill_branch_dependency_ids(
    branch: Mapping[str, Any],
    *,
    current_payload: Optional[Mapping[str, Any]] = None,
) -> list[str]:
    """Collect one branch's dependency aliases from contract and graph truth."""

    dependency_ids: list[str] = []

    def _add(raw_values: Any) -> None:
        values = (
            raw_values
            if isinstance(raw_values, (list, tuple, set))
            else [raw_values]
        )
        for value in values:
            token = str(value or '').strip()
            if token and token not in dependency_ids:
                dependency_ids.append(token)

    _add(branch.get('depends_on') or branch.get('dependsOn'))
    execution_contract = (
        branch.get('execution_contract')
        if isinstance(branch.get('execution_contract'), Mapping)
        else {}
    )
    _add(
        execution_contract.get('depends_on')
        or execution_contract.get('dependencies')
    )
    if not isinstance(current_payload, Mapping):
        return dependency_ids

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
    branch_tokens = {
        str(branch.get('branch_id') or '').strip(),
        str(branch.get('phase_id') or '').strip(),
        str(execution_contract.get('branch_id') or '').strip(),
        str(execution_contract.get('phase_id') or '').strip(),
    }
    branch_tokens.discard('')
    if not branch_tokens:
        return dependency_ids
    for key in ('phases', 'downstream_branches'):
        records = phase_graph.get(key) if isinstance(phase_graph.get(key), list) else []
        for record in records:
            if not isinstance(record, Mapping):
                continue
            record_tokens = {
                str(record.get('branch_id') or '').strip(),
                str(record.get('phase_id') or '').strip(),
            }
            record_tokens.discard('')
            if branch_tokens and not branch_tokens.intersection(record_tokens):
                continue
            _add(record.get('depends_on') or record.get('dependsOn'))
    return dependency_ids


def _artifact_record_path(record: Mapping[str, Any]) -> str:
    return str(
        record.get('path')
        or record.get('source_path')
        or record.get('saved_text_path')
        or record.get('saved_image_path')
        or record.get('saved_audio_path')
        or ''
    ).strip()


def _artifact_record_extension(record: Mapping[str, Any]) -> str:
    path = _artifact_record_path(record)
    for value in (
        record.get('text_artifact_extension'),
        (record.get('artifact_request') or {}).get('extension')
        if isinstance(record.get('artifact_request'), Mapping)
        else '',
        record.get('extension'),
        Path(path).suffix.lstrip('.') if path else '',
        Path(str(record.get('name') or '')).suffix.lstrip('.'),
    ):
        extension = str(value or '').strip().lower().lstrip('.')
        if extension:
            return extension
    return ''


def _artifact_record_source_name(record: Mapping[str, Any]) -> str:
    request_payload = record.get('artifact_request') if isinstance(record.get('artifact_request'), Mapping) else {}
    path = _artifact_record_path(record)
    return str(
        record.get('text_artifact_source_name')
        or record.get('source_name')
        or request_payload.get('source_name')
        or record.get('name')
        or (Path(path).stem if path else '')
        or ''
    ).strip()


def _artifact_records_from_late_fill_result(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for key, artifact_type in (
        ('saved_image_path', 'image'),
        ('saved_audio_path', 'audio'),
        ('saved_text_path', 'text'),
    ):
        path = str(result.get(key) or '').strip()
        if path:
            records.append({'type': artifact_type, 'kind': artifact_type, 'path': path})
    artifacts = result.get('artifacts') if isinstance(result.get('artifacts'), list) else []
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            continue
        path = str(artifact.get('path') or artifact.get('source_path') or '').strip()
        if not path:
            continue
        artifact_type = str(artifact.get('type') or artifact.get('kind') or '').strip().lower() or 'artifact'
        record = dict(artifact)
        record['type'] = artifact_type
        record.setdefault('kind', artifact_type)
        record['path'] = path
        records.append(record)
    # A saved-path shortcut must not erase the producer's canonical identity.
    canonical_paths = {record['path'] for record in records
                       if record.get('artifact_ref') or record.get('artifact_id')}
    deduped: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for record in records:
        path = str(record.get('path') or '').strip()
        if record.get('artifact_ref') or record.get('artifact_id'):
            if record not in deduped:
                deduped.append(record)
            continue
        if path in canonical_paths:
            continue
        if not path or path in seen_paths:
            continue
        seen_paths.add(path)
        deduped.append(record)
    return deduped
