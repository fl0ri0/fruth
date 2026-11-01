"""Acceptance of prepared phase text and control envelopes.

Classification and repair instructions are pure payload decisions. Callers own
the single retry, persistence, current-branch checks and response publication.
"""

from __future__ import annotations

from fruth_services.text_artifact_syntax import _strip_fenced_json_boundary
import hashlib
import json
import re
from typing import Any, Mapping, Optional
from helpers.model_capabilities import CAPABILITY_CHAT, normalize_capability
from fruth_inference.request_phase_graph import build_request_phase_graph
from fruth_inference.phase_graph_queries import (
    current_phase_capability,
    current_phase_is_graph_resolved,
    downstream_phase_capabilities,
)
from fruth_server.recovery_contract import RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT
from fruth_services.responses import extract_responses_current_turn_prompt


_JSON_BOUNDARY_START_RE = re.compile(r'(?is)^\s*(?:```[a-z0-9_-]*\s*)?[\[{]')


_JSON_BOUNDARY_TOKEN_RE = re.compile(
    r'"(?:[^"\\]|\\.)*(?:"|$)|'
    r"'(?:[^'\\]|\\.)*(?:'|$)|"
    r'[{}\[\],:]|[A-Za-z_][A-Za-z_0-9]*'
)


_INTERNAL_CONTROL_ENVELOPE_KEYS = frozenset(
    {
        'candidate_graph',
        'decision_contract',
        'output_obligations',
        'promotion_review',
        'request_ir',
        'request_phase_graph',
        'user_facing_response',
        'workload_graph',
    }
)


_EXPLICIT_CONTROL_DIAGNOSTIC_RE = re.compile(
    r'(?is)\b(?:show|display|print|return|inspect|debug|explain|dump|zeige|zeig|anzeigen|'
    r'ausgeben|prüf(?:e|en)?|pruef(?:e|en)?|debugg(?:e|en)?|erklär(?:e|en)?|erklaer(?:e|en)?)\b'
    r'[^.!?\n]{0,160}\b(?:request[_ -]?ir|request[_ -]?phase[_ -]?graph|decision[_ -]?contract|'
    r'candidate[_ -]?graph|promotion[_ -]?review|workload[_ -]?graph|control[_ -]?plane|planner[_ -]?json)\b'
)


_PHASE_OUTPUT_REPAIR_SYSTEM_MESSAGE = (
    'Fruth phase-output repair: the previous attempt returned an internal planner/control envelope. '
    'Retry this same current phase once. Return only the substantive user-facing content required by '
    'the current phase. Do not return JSON, request IR, decision contracts, candidate graphs, route '
    'metadata, process narration, headings, or capability commentary.'
)


_PHASE_OUTPUT_REPAIR_NOTICE = (
    'Runtime truth: the current preparation phase did not produce accepted substantive user-facing '
    'content. Internal planner/control data, if any, was withheld. Downstream materialization is '
    'blocked until the branch contract is repaired.'
)


def _parse_visible_json_boundary(text: str) -> Any:
    candidate = _strip_fenced_json_boundary(text)
    if not candidate or candidate[0:1] not in {'{', '['}:
        return None
    try:
        return json.loads(candidate)
    except (TypeError, ValueError):
        return None


def _control_envelope_mapping(value: Any) -> bool:
    # A sole response object is a transparent envelope wrapper. Arbitrary
    # example/data children are not recursively classified as control work.
    while isinstance(value, Mapping) and len(value) == 1:
        key, child = next(iter(value.items()))
        if str(key).strip().lower() != 'response' or not isinstance(child, Mapping):
            break
        value = child
    if not isinstance(value, Mapping):
        return False
    normalized_keys = {
        str(key or '').strip().lower()
        for key in value.keys()
        if str(key or '').strip()
    }
    return bool(normalized_keys.intersection(_INTERNAL_CONTROL_ENVELOPE_KEYS))


def visible_control_json_envelope(text: str) -> bool:
    """Return whether *text* is one complete internal control JSON envelope.

    Parsing the outer JSON boundary avoids treating ordinary prose that merely
    mentions an internal field name as control data. A sole response object is
    transparent. A list is control-shaped only when a direct member is such an
    envelope; arbitrary nested documentation/data fields remain opaque.
    """

    parsed = _parse_visible_json_boundary(text)
    if _control_envelope_mapping(parsed):
        return True
    return bool(
        isinstance(parsed, list)
        and any(_control_envelope_mapping(item) for item in parsed)
    )


def control_json_envelope_suspected(text: str) -> bool:
    """Catch complete and truncated JSON-like internal control boundaries."""

    # Successful parsing owns classification. A token inside an ordinary JSON
    # value is not evidence of a malformed internal envelope. Keep the lexical
    # fallback for genuinely incomplete/unparseable control-shaped text.
    parsed = _parse_visible_json_boundary(text)
    if isinstance(parsed, (Mapping, list)):
        return _control_envelope_mapping(parsed) or bool(
            isinstance(parsed, list) and any(_control_envelope_mapping(item) for item in parsed)
        )
    source = str(text or '')
    if not _JSON_BOUNDARY_START_RE.match(source):
        return False
    # Treat quoted strings as whole tokens: a control name in a value, or in
    # bracketed prose, is not an object key. Keep incomplete and nonstandard
    # control objects blocked when their actual key position is still visible.
    tokens = _JSON_BOUNDARY_TOKEN_RE.findall(source)
    for index in range(1, len(tokens) - 1):
        if tokens[index - 1] not in {'{', ','} or tokens[index + 1] != ':':
            continue
        key = tokens[index]
        if key.startswith('"'):
            try:
                key = json.loads(key)
            except ValueError:
                continue
        elif key.startswith("'") and key.endswith("'"):
            key = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), key[1:-1])
        if str(key).strip().lower() in _INTERNAL_CONTROL_ENVELOPE_KEYS:
            return True
    return False


def _collect_control_json_content_payloads(value: Any) -> list[str]:
    payloads: list[str] = []
    if isinstance(value, Mapping):
        raw_payload = value.get('content_payload')
        if isinstance(raw_payload, str) and raw_payload.strip():
            payloads.append(raw_payload.strip())
        for child in value.values():
            payloads.extend(_collect_control_json_content_payloads(child))
    elif isinstance(value, list):
        for child in value:
            payloads.extend(_collect_control_json_content_payloads(child))
    return payloads


def _visible_control_json_substantive_payload(text: str) -> str:
    parsed = _parse_visible_json_boundary(text)
    if not visible_control_json_envelope(text):
        return ''
    payloads = [
        payload.strip()
        for payload in _collect_control_json_content_payloads(parsed)
        if payload.strip()
    ]
    if len(payloads) != 1:
        return ''
    substantive = payloads[0]
    if visible_control_json_envelope(substantive):
        return ''
    return substantive


def classify_phase_output_text(text: str) -> dict[str, Any]:
    """Classify one complete model phase result without retaining its bytes."""

    source_text = str(text or '').strip()
    source_bytes = source_text.encode('utf-8')
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    if not source_text:
        return {
            'status': 'repair_required',
            'accepted_text': '',
            'source_sha256': source_sha256,
            'source_bytes': 0,
            'reason': 'current phase did not return substantive text',
        }
    if control_json_envelope_suspected(source_text) and not visible_control_json_envelope(source_text):
        return {
            'status': 'repair_required',
            'accepted_text': '',
            'source_sha256': source_sha256,
            'source_bytes': len(source_bytes),
            'reason': 'malformed or truncated internal control envelope is not substantive phase text',
        }
    if not visible_control_json_envelope(source_text):
        return {
            'status': 'accepted',
            'accepted_text': source_text,
            'source_sha256': source_sha256,
            'source_bytes': len(source_bytes),
            'reason': 'phase output is not an internal control envelope',
        }
    substantive_payload = _visible_control_json_substantive_payload(source_text)
    if substantive_payload:
        return {
            'status': 'unwrapped',
            'accepted_text': substantive_payload,
            'source_sha256': source_sha256,
            'source_bytes': len(source_bytes),
            'accepted_sha256': hashlib.sha256(substantive_payload.encode('utf-8')).hexdigest(),
            'accepted_bytes': len(substantive_payload.encode('utf-8')),
            'reason': 'one safe substantive content_payload was extracted from the control envelope',
        }
    return {
        'status': 'repair_required',
        'accepted_text': '',
        'source_sha256': source_sha256,
        'source_bytes': len(source_bytes),
        'reason': 'internal control envelope did not contain exactly one safe substantive content_payload',
    }


def phase_output_acceptance_metadata(
    attempts: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build bounded response metadata from one or two classification attempts."""

    normalized_attempts: list[dict[str, Any]] = []
    for index, attempt in enumerate(attempts, start=1):
        if not isinstance(attempt, Mapping):
            continue
        normalized_attempts.append(
            {
                key: value
                for key, value in {
                    'attempt': index,
                    'status': str(attempt.get('status') or '').strip() or 'repair_required',
                    'source_sha256': str(attempt.get('source_sha256') or '').strip() or None,
                    'source_bytes': int(attempt.get('source_bytes') or 0),
                    'accepted_sha256': str(attempt.get('accepted_sha256') or '').strip() or None,
                    'accepted_bytes': int(attempt.get('accepted_bytes') or 0),
                    'reason': str(attempt.get('reason') or '').strip() or None,
                }.items()
                if value not in (None, '', [], {})
            }
        )
    final_attempt = attempts[-1] if attempts else {}
    final_status = str(final_attempt.get('status') or '').strip() or 'repair_required'
    status = (
        'accepted_after_retry'
        if len(normalized_attempts) > 1 and final_status in {'accepted', 'unwrapped'}
        else final_status
    )
    accepted_text = str(final_attempt.get('accepted_text') or '')
    accepted_bytes = accepted_text.encode('utf-8')
    return {
        key: value
        for key, value in {
            'kind': 'fruth.phase_output_acceptance',
            'version': 1,
            'status': status,
            'attempt_count': len(normalized_attempts),
            'attempts': normalized_attempts,
            'accepted_sha256': (
                hashlib.sha256(accepted_bytes).hexdigest()
                if accepted_text
                else None
            ),
            'accepted_bytes': len(accepted_bytes) if accepted_text else None,
            'runtime_effect': (
                'materialization_blocked'
                if final_status == 'repair_required'
                else 'canonical_phase_text'
            ),
        }.items()
        if value not in (None, '', [], {})
    }


def phase_output_repair_system_message() -> dict[str, str]:
    return {'role': 'system', 'content': _PHASE_OUTPUT_REPAIR_SYSTEM_MESSAGE}


def phase_output_repair_notice() -> str:
    return _PHASE_OUTPUT_REPAIR_NOTICE


def attach_phase_output_acceptance(
    payload: Optional[dict[str, Any]],
    attempts: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Attach bounded acceptance truth and a fail-closed guard to a response."""

    updated = dict(payload or {})
    runtime = dict(updated.get('runtime') or {}) if isinstance(updated.get('runtime'), Mapping) else {}
    metadata = phase_output_acceptance_metadata(attempts)
    runtime['phase_output_acceptance'] = metadata
    final_status = str((attempts[-1] if attempts else {}).get('status') or '').strip()
    if final_status == 'repair_required':
        guard_reason = str((attempts[-1] if attempts else {}).get('reason') or '').strip()
        runtime['truth_guard'] = {
            'kind': (
                'control_json_boundary'
                if 'control envelope' in guard_reason
                else 'phase_output_boundary'
            ),
            'status': 'repair_required',
            'reason': guard_reason
            or 'current phase did not return accepted substantive content',
            'repair_action': RECOVERY_ACTION_REPAIR_BRANCH_CONTRACT,
            'runtime_effect': 'materialization_blocked',
        }
    updated['runtime'] = runtime
    return updated


def _phase_graph_from_runtime_payload(route_payload: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    route = route_payload if isinstance(route_payload, Mapping) else {}
    runtime = route.get('route_runtime') if isinstance(route.get('route_runtime'), Mapping) else {}
    graph = runtime.get('request_phase_graph') if isinstance(runtime.get('request_phase_graph'), Mapping) else {}
    return dict(graph)


def _phase_output_graph(
    *,
    route_payload: Optional[Mapping[str, Any]],
    request_payload: Optional[Mapping[str, Any]],
) -> dict[str, Any]:
    request_info = request_payload if isinstance(request_payload, Mapping) else {}
    graph = _phase_graph_from_runtime_payload(route_payload)
    if not graph:
        prompt = str(
            extract_responses_current_turn_prompt(request_info)
            or request_info.get('prompt')
            or request_info.get('input')
            or ''
        ).strip()
        graph = build_request_phase_graph(
            prompt,
            intent_prompt=extract_responses_current_turn_prompt(request_info),
            request_payload=dict(request_info),
            route_payload=dict(route_payload or {}),
        )
    return graph


def phase_output_is_graph_preparation(
    *,
    route_payload: Optional[Mapping[str, Any]],
    request_payload: Optional[Mapping[str, Any]],
    capability: Optional[str],
) -> bool:
    """Return whether the current chat phase directly prepares downstream work."""

    if normalize_capability(capability) != CAPABILITY_CHAT:
        return False
    graph = _phase_output_graph(route_payload=route_payload, request_payload=request_payload)
    if not current_phase_is_graph_resolved(graph) or current_phase_capability(graph) != CAPABILITY_CHAT:
        return False
    current_phase_id = str(graph.get('current_phase_id') or '').strip()
    current_phase = next(
        (
            item
            for item in (graph.get('phases') or [])
            if isinstance(item, Mapping)
            and str(item.get('phase_id') or '').strip() == current_phase_id
        ),
        {},
    )
    phase_kind = str(current_phase.get('kind') or '').strip().lower()
    phase_role = str(current_phase.get('role') or '').strip().lower()
    return bool(
        downstream_phase_capabilities(graph)
        and (phase_kind == 'prepare' or phase_role == 'text_preparation')
    )


def phase_output_defers_saved_file_materialization(
    *,
    route_payload: Optional[Mapping[str, Any]],
    request_payload: Optional[Mapping[str, Any]],
    capability: Optional[str],
) -> bool:
    """Keep save/read preparation as text; its producer branch owns the file."""

    if normalize_capability(capability) != CAPABILITY_CHAT:
        return False
    graph = _phase_output_graph(route_payload=route_payload, request_payload=request_payload)
    graph_route = {'route_runtime': {'request_phase_graph': graph}}
    if not phase_output_is_graph_preparation(
        route_payload=graph_route, request_payload=request_payload, capability=capability,
    ):
        return False
    return any(
        isinstance(phase, Mapping)
        and phase.get('dependency_contract') == 'saved_file_read_required'
        for phase in (graph.get('phases') or [])
    )


def request_explicitly_allows_control_diagnostics(
    *,
    request_payload: Optional[Mapping[str, Any]],
    route_payload: Optional[Mapping[str, Any]],
    capability: Optional[str],
) -> bool:
    """Allow explicitly requested diagnostics only when no materializer consumes them."""

    if phase_output_is_graph_preparation(
        route_payload=route_payload,
        request_payload=request_payload,
        capability=capability,
    ):
        return False
    request_info = request_payload if isinstance(request_payload, Mapping) else {}
    prompt = str(
        extract_responses_current_turn_prompt(request_info)
        or request_info.get('prompt')
        or request_info.get('input')
        or ''
    ).strip()
    return bool(prompt and _EXPLICIT_CONTROL_DIAGNOSTIC_RE.search(prompt))


