"""Semantic role profile builder for route/runtime orientation."""

from __future__ import annotations

from typing import Any, Optional

from fruth_inference.semantic_roles import normalize_semantic_role_ids, semantic_role
from fruth_inference.intent import analyze_prompt_intent

# Internal intent/runtime orientation.
DEFAULT_ORIENTATION = 'worker'
_ORIENTATION_ROLE_IDS = {
    'repair': ('repairer', 'evidence_reasoner', 'doubt_challenger'),
    'worker': ('materializer', 'quality_reviewer', 'transition_committer'),
    'explorer': ('possibility_expander', 'structural_planner', 'integrator'),
    'improviser': ('possibility_expander', 'materializer', 'quality_reviewer'),
}


# Existing intent-hint vocabulary; independent of the public role-list input.
_ORIENTATION_HINTS = {'build': 'worker', 'builder': 'worker', 'creative': 'improviser', 'execute': 'worker', 'fix': 'repair', 'healer': 'repair', 'improvise': 'improviser', 'investigate': 'explorer', 'research': 'explorer'}

def _normalize_orientation(value: Any) -> str | None:
    token = str(value or '').strip().lower().replace('-', '_').replace(' ', '_')
    return token if token in _ORIENTATION_ROLE_IDS else _ORIENTATION_HINTS.get(token)


def _orientation_roles(mode: str) -> list[dict[str, Any]]:
    return [role for role_id in _ORIENTATION_ROLE_IDS.get(mode, ())
            if (role := semantic_role(role_id))]


SELF_MODIFICATION_ALLOWED_SURFACES = (
    'policies',
    'prompts',
    'routing_preferences',
    'artifact_plans',
)
SELF_MODIFICATION_GATED_SURFACES = (
    'runtime_code',
    'operator_scripts',
    'external_integrations',
)


def build_self_modification_contract() -> dict[str, Any]:
    return {
        'allowed_surfaces': list(SELF_MODIFICATION_ALLOWED_SURFACES),
        'evaluation_required_surfaces': list(SELF_MODIFICATION_ALLOWED_SURFACES),
        'gated_surfaces': list(SELF_MODIFICATION_GATED_SURFACES),
        'silent_runtime_code_rewrites_allowed': False,
        'summary': (
            'The interpretive inference layer may rewrite policies, prompts, routing preferences, and artifact plans. '
            'Core runtime code and operator surfaces remain gated.'
        ),
    }


def _orientation_lenses_for_roles(roles: list[dict[str, Any]]) -> list[str]:
    lenses: list[str] = []
    for role in roles:
        role_id = str(role.get('role_id') or '').strip()
        if role_id:
            lenses.append(role_id)
    for role in roles:
        for lens in role.get('related_lenses') or ():
            text = str(lens or '').strip()
            if text:
                lenses.append(text)
    deduped: list[str] = []
    for lens in lenses:
        if lens not in deduped:
            deduped.append(lens)
    return deduped[:8]


def _orientation_reason(
    *,
    mode: str,
    runtime_issue_count: int,
    retry_failure_active: bool,
    self_healing_hints: tuple[str, ...],
) -> str:
    if runtime_issue_count or retry_failure_active:
        return 'Runtime issues are visible; use semantic roles to preserve truth and select repair/review.'
    if self_healing_hints:
        return 'Self-healing hints exist; keep them advisory and verify against runtime truth.'
    if mode == 'explicit_roles':
        return 'Explicit semantic role ids orient advisory attention only.'
    if mode == 'explorer':
        return 'Intent-derived explorer orientation selects possibility and structure lenses.'
    if mode == 'improviser':
        return 'Intent-derived improviser orientation selects possibility plus materialization checks.'
    if mode == 'repair':
        return 'Intent-derived repair orientation selects repair and evidence lenses.'
    return 'Intent-derived worker orientation selects materialization, quality, and commitment lenses.'


def build_role_orientation(
    roles: list[dict[str, Any]],
    *,
    mode: str,
    mode_source: str = 'default',
    runtime_issue_count: int = 0,
    retry_failure_active: bool = False,
    self_healing_hints: tuple[str, ...] = (),
    preview_mode: bool = False,
) -> dict[str, Any]:
    actions: list[str] = []
    for role in roles:
        for action in role.get('allowed_advisory_actions') or ():
            if action not in actions:
                actions.append(action)
    if runtime_issue_count or retry_failure_active:
        for action in ('repair_dependency_chain', 'repair_branch_contract'):
            if action not in actions:
                actions.append(action)
    return {
        'kind': 'fruth.semantic_role_orientation',
        'authority': 'advisory_read_model_only',
        'mode': mode,
        'mode_source': mode_source,
        'preview_mode': bool(preview_mode),
        'semantic_role_ids': [role['role_id'] for role in roles],
        'semantic_roles': roles,
        'suggested_semantic_review_lenses': _orientation_lenses_for_roles(roles),
        'allowed_advisory_actions': actions,
        'reason': _orientation_reason(
            mode=mode,
            runtime_issue_count=runtime_issue_count,
            retry_failure_active=retry_failure_active,
            self_healing_hints=self_healing_hints,
        ),
        'non_authority_boundary': (
            'Semantic roles may suggest; Runtime/Contracts/Closure decide truth, execution, '
            'waiver, supersession, and freeze.'
        ),
    }


def _effective_request_meta(route_context: dict[str, Any], request_meta: Optional[dict[str, Any]]) -> dict[str, Any]:
    if isinstance(request_meta, dict) and request_meta:
        return request_meta
    context_meta = route_context.get('request_meta')
    return context_meta if isinstance(context_meta, dict) else {}


def _infer_mode_from_intent(route_context: dict[str, Any]) -> str | None:
    intent = route_context.get('intent') if isinstance(route_context.get('intent'), dict) else {}
    hinted_mode = _normalize_orientation(intent.get('temperament_hint'))
    if hinted_mode:
        return hinted_mode
    prompt = str(route_context.get('prompt') or '').strip()
    if not prompt:
        return None
    analysis = analyze_prompt_intent(prompt)
    return _normalize_orientation(analysis.get('temperament_hint'))


def _runtime_issue_count(route_context: dict[str, Any]) -> int:
    runtime = route_context.get('runtime') if isinstance(route_context.get('runtime'), dict) else {}
    issues = runtime.get('inference_issues') if isinstance(runtime.get('inference_issues'), list) else []
    return sum(1 for item in issues if str(item or '').strip())


def _retry_failure_present(route_context: dict[str, Any], retry_failure: Optional[dict[str, Any]]) -> bool:
    if isinstance(retry_failure, dict) and retry_failure:
        return True
    runtime = route_context.get('runtime') if isinstance(route_context.get('runtime'), dict) else {}
    stored = runtime.get('retry_failure')
    return bool(stored) if isinstance(stored, dict) else False


def _semantic_loop(*, preview_mode: bool) -> dict[str, Any]:
    return {
        'max_passes': 1,
        'critic_passes': 1 if not preview_mode else 0,
        'phases': [
            {'id': 'orient', 'goal': 'Read runtime truth, promoted contracts, selected context, and semantic role hints.'},
            {'id': 'contract', 'goal': 'Choose the right contract, evidence, or repair transition before acting.'},
            {'id': 'act', 'goal': 'Execute only promoted branch-local work.'},
            {'id': 'review', 'goal': 'Check result against intent, evidence, and closure truth.', 'enabled': not preview_mode},
        ],
    }


def build_semantic_role_profile(
    route_context: dict[str, Any],
    *,
    request_meta: Optional[dict[str, Any]] = None,
    preview_mode: bool = False,
    retry_failure: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    effective_request_meta = _effective_request_meta(route_context, request_meta)
    explicit_roles = normalize_semantic_role_ids(effective_request_meta.get('semantic_role_ids'))
    intent_mode = _infer_mode_from_intent(route_context)
    runtime_issue_count = _runtime_issue_count(route_context)
    retry_failure_active = _retry_failure_present(route_context, retry_failure)
    if explicit_roles:
        mode = 'explicit_roles'
        mode_source = 'request'
    elif retry_failure_active:
        mode = 'repair'
        mode_source = 'retry_failure'
    elif runtime_issue_count:
        mode = 'repair'
        mode_source = 'runtime_issue'
    elif intent_mode:
        mode = intent_mode
        mode_source = 'intent'
    else:
        mode = DEFAULT_ORIENTATION
        mode_source = 'default'

    runtime = route_context.get('runtime') if isinstance(route_context.get('runtime'), dict) else {}
    self_healing_hints = runtime.get('inference_self_healing_hints') if isinstance(runtime.get('inference_self_healing_hints'), list) else []
    routing_scope = runtime.get('routing_scope') if isinstance(runtime.get('routing_scope'), dict) else {}
    runtime_orientation = {
        'disable_fast_path': False,
        'planner_timeout_bonus_sec': 0,
        'allow_branching': False,
        'authority': 'semantic_role_metadata_only',
        'runtime_effect': 'none',
    }
    if routing_scope.get('routing_preferences'):
        runtime_orientation['learned_routing_preference_present'] = True
    if retry_failure_active:
        runtime_orientation['prioritize_recovery'] = 'advisory_orientation_only'

    roles = ([semantic_role(role_id) for role_id in explicit_roles]
             if explicit_roles else _orientation_roles(mode))
    return {
        'kind': 'fruth.semantic_role_profile',
        'mode': mode,
        'mode_source': mode_source,
        'label': 'Semantic Role Profile',
        'summary': 'Advisory semantic role orientation for this route.',
        'semantic_role_ids': [role['role_id'] for role in roles],
        'semantic_roles': roles,
        'planner_orientation': {
            'style': 'semantic_contract_first',
            'instruction': 'Use semantic roles as advisory lenses only.',
            'authority': 'semantic_role_metadata_only',
            'runtime_effect': 'none',
        },
        'runtime_orientation': runtime_orientation,
        'authority_boundary': {
            'planner_timeout': 'explicit_developer_flags_only',
            'branch_topology': 'runtime_contracts_only',
            'payload_authority': 'branch_local_contracts_only',
            'promotion': 'promotion_review_only',
            'waiver': 'closure_or_contract_truth_only',
            'supersession': 'closure_or_contract_truth_only',
            'execution': 'runtime_contracts_only',
            'freeze': 'closure_truth_only',
            'runtime_effect': 'none',
        },
        'loop': _semantic_loop(preview_mode=preview_mode),
        'semantic_role_orientation': build_role_orientation(
            roles,
            mode=mode,
            mode_source=mode_source,
            runtime_issue_count=runtime_issue_count,
            retry_failure_active=retry_failure_active,
            self_healing_hints=tuple(str(item) for item in self_healing_hints if str(item or '').strip()),
            preview_mode=preview_mode,
        ),
        'self_modification': build_self_modification_contract(),
        'signals': {
            'requested_semantic_role_ids': explicit_roles,
            'intent_mode': intent_mode,
            'runtime_issue_count': runtime_issue_count,
            'self_healing_hint_count': len(self_healing_hints),
            'retry_failure_active': retry_failure_active,
            'preview_mode': bool(preview_mode),
        },
        'non_authority_boundary': (
            'Semantic roles are advisory lenses. Runtime/Contracts/Closure own truth, '
            'promotion, execution, waiver, supersession, and freeze.'
        ),
    }
