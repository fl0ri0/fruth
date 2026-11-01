"""Render a captured run report as the established human-readable text.

Pure presentation over report data. It cannot read ledgers, change tracking
state, repair artifacts or decide runtime completion.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value[:-1] + '+00:00' if value.endswith('Z') else value
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _fmt_time(dt: datetime | None) -> str:
    if not dt:
        return 'unknown'
    return dt.strftime('%H:%M:%SZ')


def _fmt_seconds(seconds: float | None) -> str:
    if seconds is None:
        return 'unknown'
    if seconds < 90:
        return f'{seconds:.1f}s'
    minutes, sec = divmod(int(round(seconds)), 60)
    return f'{minutes}m{sec:02d}s'


def _format_counts(counts: dict[str, int] | None, *, limit: int = 8) -> str:
    if not counts:
        return 'none'
    parts = [
        f'{key}={counts[key]}'
        for key in sorted(counts.keys(), key=str)[:limit]
    ]
    if len(counts) > limit:
        parts.append(f'+{len(counts) - limit} more')
    return ', '.join(parts) if parts else 'none'


def _artifact_kind_token(value: Any) -> str:
    token = re.sub(r'[\s-]+', '_', str(value or '').strip().lower())
    return token or 'unknown'


def _is_audio_kind(value: Any) -> bool:
    token = _artifact_kind_token(value)
    return token in {
        'audio',
        'wav',
        'mp3',
        'm4a',
        'aac',
        'ogg',
        'opus',
        'flac',
        'text_to_speech',
        'speech',
    }


def _fmt_size(bytes_count: int | None) -> str:
    if bytes_count is None:
        return 'unknown'
    units = ['B', 'K', 'M', 'G']
    value = float(bytes_count)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == 'B':
                return f'{int(value):,}B'
            if value >= 100:
                return f'{value:.0f}{unit}'
            if value >= 10:
                return f'{value:.1f}{unit}'
            return f'{value:.2f}{unit}'
        value /= 1024.0
    return f'{bytes_count:,}B'


def _format_duplicate_item(item: dict[str, Any]) -> str:
    ref = item.get('artifact_ref') or 'unknown'
    reason = item.get('reason') or 'unknown'
    paths = ', '.join(item.get('paths') or ['unknown'])
    kinds = ', '.join(item.get('kinds') or ['unknown'])
    return f'{ref} ({reason}; paths {paths}; types {kinds})'


def _duplicate_ref_lines(summary: dict[str, Any]) -> list[str]:
    if not summary:
        return []
    if not (summary.get('final_projection') or summary.get('registry') or summary.get('output')):
        return []
    source_labels = {
        'final_projection': 'duplicate final projection',
        'registry': 'duplicate registry ref',
        'output': 'duplicate output ref',
    }
    source_bits = [
        f"{label} {'yes' if summary.get(key) else 'no'}"
        for key, label in source_labels.items()
    ]
    lines = ['- Artifact identity duplicates: ' + '; '.join(source_bits) + '.']
    source_items = [
        item
        for key in ('final_projection', 'registry', 'output')
        for item in (summary.get(key) or [])
    ]
    canonicalizable = summary.get('canonicalizable') or [
        item for item in source_items
        if item.get('classification') == 'canonicalizable'
    ]
    conflicts = summary.get('conflicts') or [
        item for item in source_items
        if item.get('classification') == 'conflict'
    ]
    if canonicalizable:
        lines.append(
            '- Artifact identity canonicalizable: '
            + '; '.join(_format_duplicate_item(item) for item in canonicalizable[:4])
            + (f'; +{len(canonicalizable) - 4} more' if len(canonicalizable) > 4 else '')
            + '.'
        )
    if conflicts:
        lines.append(
            '- Artifact identity conflicts: '
            + '; '.join(_format_duplicate_item(item) for item in conflicts[:4])
            + (f'; +{len(conflicts) - 4} more' if len(conflicts) > 4 else '')
            + '.'
        )
    return lines


def _format_scheduling_policy(policy: dict[str, Any]) -> str:
    guard = policy.get('gpu_heavy_guard') or 'none recorded'
    reason = policy.get('reason') or 'no reason recorded'
    original = policy.get('original_branch_count')
    scheduled = policy.get('scheduled_branch_count')
    deferred = policy.get('deferred_branch_count')
    parts = [f'gpu-heavy guard {guard}', f'reason {reason}']
    if original is not None and scheduled is not None:
        parts.append(f'scheduled {scheduled}/{original} branches')
    if deferred is not None:
        parts.append(f'deferred {deferred}')
    return '; '.join(parts)


def _format_instance_groups(groups: Any) -> str | None:
    if not isinstance(groups, dict) or not groups:
        return None
    formatted = []
    for instance_id, branch_ids in sorted(groups.items()):
        if not isinstance(branch_ids, list):
            continue
        clipped = [str(branch_id) for branch_id in branch_ids[:3]]
        suffix = '' if len(branch_ids) <= 3 else f', +{len(branch_ids) - 3} more'
        formatted.append(f"{instance_id}: {', '.join(clipped)}{suffix}")
    return '; '.join(formatted) if formatted else None


def _clip_text(value: Any, limit: int = 180) -> str | None:
    if value in (None, '', [], {}):
        return None
    text = re.sub(r'\s+', ' ', str(value)).strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + '...'


def _brief_value(value: Any, limit: int = 180) -> str | None:
    if value in (None, '', [], {}):
        return None
    if isinstance(value, (str, int, float, bool)):
        return _clip_text(value, limit)
    try:
        text = json.dumps(value, sort_keys=True, default=str)
    except TypeError:
        text = str(value)
    return _clip_text(text, limit)


def _brief_counts(value: Any, limit: int = 6) -> str | None:
    if isinstance(value, dict) and value:
        parts = [
            f'{key}={value[key]}'
            for key in sorted(value.keys(), key=str)[:limit]
            if value.get(key) not in (None, '', [], {})
        ]
        if len(value) > limit:
            parts.append(f'+{len(value) - limit} more')
        return ', '.join(parts) if parts else None
    return _brief_value(value)


def _bool_token(value: Any) -> str:
    return 'true' if bool(value) else 'false'


def _join_compact(values: list[str], *, limit: int = 6) -> str:
    cleaned = [value for value in values if value]
    if not cleaned:
        return 'none'
    unique: list[str] = []
    seen: set[str] = set()
    for value in cleaned:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    clipped = unique[:limit]
    if len(unique) > limit:
        clipped.append(f'+{len(unique) - limit} more')
    return ', '.join(clipped)


def _render_learning_healing_lines(info: dict[str, Any]) -> list[str]:
    lines: list[str] = []

    accepted = info.get('accepted_learning_hints') or {}
    if accepted:
        lines.append(
            '- Accepted learning hints: '
            f"{accepted.get('hint_count')} hints, status {accepted.get('status') or 'unknown'}, "
            f"runtime effect {accepted.get('runtime_effect') or 'unknown'}."
        )
        for hint in accepted.get('top_hints') or []:
            target = hint.get('target_area') or 'learning hint'
            details = []
            if hint.get('case_kinds'):
                details.append(f"cases {hint.get('case_kinds')}")
            if hint.get('severity_counts'):
                details.append(f"severity {hint.get('severity_counts')}")
            if hint.get('learning_id'):
                details.append(f"id {hint.get('learning_id')}")
            suffix = f" ({'; '.join(details)})" if details else ''
            hint_text = hint.get('hint') or 'no hint text recorded'
            lines.append(f"  {target}{suffix}: {hint_text}")

    runtime_authority = info.get('runtime_repair_authority') or {}
    if runtime_authority:
        lines.append('- Runtime repair/healing authority:')
        enforced_policy = runtime_authority.get('enforced_policy') or {}
        if enforced_policy:
            lines.append(
                '  Enforced policy: '
                f"mode {enforced_policy.get('mode') or 'unknown'}, "
                f"enabled {_bool_token(enforced_policy.get('enabled'))}, "
                f"default_action {enforced_policy.get('default_action') or 'unknown'}."
            )
        repair = runtime_authority.get('graph_repair_enforcement') or {}
        patch_autonomy = runtime_authority.get('graph_patch_autonomy') or {}
        if repair or patch_autonomy:
            lines.append(
                '  Graph repair enforcement: '
                f"autonomy {patch_autonomy.get('autonomy_level') or 'unknown'}, "
                f"allowed {repair.get('allowed_count', 0)}, "
                f"blocked {repair.get('blocked_count', 0)}, "
                f"classes {_join_compact(repair.get('classes') or [])}, "
                f"blocked reasons {_join_compact(repair.get('blocked_reasons') or [])}, "
                f"authority {_join_compact(repair.get('authorities') or [])}."
            )
        rebase = runtime_authority.get('graph_rebase_enforcement') or {}
        rebase_autonomy = runtime_authority.get('graph_rebase_autonomy') or {}
        if rebase or rebase_autonomy:
            full_blocked = 'yes' if rebase.get('full_successor_rebase_blocked') else 'no'
            partial_blocked = 'yes' if rebase.get('partial_subtree_rebase_audit_only') else 'no'
            lines.append(
                '  Graph rebase enforcement: '
                f"autonomy {rebase_autonomy.get('autonomy_level') or 'unknown'}, "
                f"allowed {rebase.get('allowed_count', 0)}, "
                f"blocked {rebase.get('blocked_count', 0)}, "
                f"full successor rebase blocked {full_blocked}, "
                f"partial subtree rebase audit-only/blocked {partial_blocked}, "
                f"classes {_join_compact(rebase.get('classes') or [])}, "
                f"blocked reasons {_join_compact(rebase.get('blocked_reasons') or [])}, "
                f"authority {_join_compact(rebase.get('authorities') or [])}."
            )
        successor_runtime = runtime_authority.get('successor_runtime') or {}
        if successor_runtime:
            lines.append(
                '  Successor/reopen: '
                f"{successor_runtime.get('reopen_count', 0)} reopen, "
                f"{successor_runtime.get('rebase_count', 0)} rebase, "
                f"parent frozen/unmutated {_bool_token(successor_runtime.get('parent_frozen_unmutated'))}."
            )
            execution_observer = (
                successor_runtime.get('partial_rebase_execution_observer')
                if isinstance(
                    successor_runtime.get('partial_rebase_execution_observer'),
                    dict,
                )
                else {}
            )
            if execution_observer:
                lines.append(
                    '  Partial rebase execution observer: '
                    f"{execution_observer.get('execution_count', 0)} executions, "
                    f"statuses {_brief_counts(execution_observer.get('status_counts')) or 'none'}, "
                    f"scheduled branches {execution_observer.get('scheduled_branch_count', 0)}, "
                    f"root prompt replays {execution_observer.get('root_prompt_replay_count', 0)}, "
                    f"authority {execution_observer.get('authority') or 'observer_only'}, "
                    f"runtime effect {execution_observer.get('runtime_effect') or 'none'}."
                )
        redraw_scope = runtime_authority.get('redraw_scope') or {}
        if redraw_scope.get('selected_scopes') or redraw_scope.get('blocked_reasons'):
            lines.append(
                '  Redraw scope ladder: '
                f"selected {_join_compact(redraw_scope.get('selected_scopes') or [])}, "
                f"blocked reasons {_join_compact(redraw_scope.get('blocked_reasons') or [])}."
            )
        forbidden_labels = runtime_authority.get('forbidden_evidence_labels') or []
        if forbidden_labels:
            lines.append(
                '  Forbidden evidence rejected: '
                f"{_join_compact(forbidden_labels)}."
            )
        if runtime_authority.get('accepted_learning_authority') == 'soft_hint':
            lines.append('  Accepted learning remains soft_hint_only.')

    closure = info.get('closure_review') or {}
    if closure:
        parts = [
            f"status {closure.get('status') or 'unknown'}",
            f"repair_gap_code {closure.get('repair_gap_code') or 'none'}",
            f"repair_gap_trigger {closure.get('repair_gap_trigger') or 'none'}",
        ]
        if closure.get('repair_pending_branch_count') is not None:
            parts.append(f"repair pending branches {closure.get('repair_pending_branch_count')}")
        if closure.get('semantic_review_status'):
            parts.append(f"semantic review {closure.get('semantic_review_status')}")
        if closure.get('semantic_transition'):
            parts.append(f"transition {closure.get('semantic_transition')}")
        lines.append('- Graph closure review: ' + '; '.join(parts) + '.')

    surface = info.get('surface_state') or {}
    if surface:
        parts = [f"state {surface.get('state') or 'unknown'}"]
        if surface.get('category_counts'):
            parts.append(f"categories {surface.get('category_counts')}")
        if surface.get('item_count') is not None:
            parts.append(f"items {surface.get('item_count')}")
        if surface.get('actionability'):
            parts.append(f"actionability {surface.get('actionability')}")
        if surface.get('actionable_categories'):
            parts.append(f"actionable {surface.get('actionable_categories')}")
        if surface.get('advisory_categories'):
            parts.append(f"advisory {surface.get('advisory_categories')}")
        if surface.get('reason'):
            parts.append(f"reason {surface.get('reason')}")
        lines.append('- Surface state: ' + '; '.join(parts) + '.')

    graph_repair = info.get('graph_repair') or {}
    if graph_repair.get('proposal_count') or graph_repair.get('review_count'):
        lines.append(
            '- Graph repair proposals/reviews: '
            f"{graph_repair.get('proposal_count', 0)} proposals, "
            f"{graph_repair.get('review_count', 0)} reviews."
        )
        proposal_review_pairs = graph_repair.get('proposal_review_pairs') or []
        if proposal_review_pairs:
            proposal_items = [
                pair.get('proposal') for pair in proposal_review_pairs
                if isinstance(pair, dict) and isinstance(pair.get('proposal'), dict)
            ]
        else:
            proposal_items = graph_repair.get('proposals') or []
        for proposal in proposal_items:
            parts = [
                f"id {proposal.get('proposal_id') or 'unknown'}",
                f"status {proposal.get('status') or 'unknown'}",
                f"type {proposal.get('repair_type') or 'unknown'}",
                f"gap {proposal.get('repair_gap_code') or 'unknown'}",
            ]
            if proposal.get('branch_addition_count') is not None:
                parts.append(f"branch additions {proposal.get('branch_addition_count')}")
            if proposal.get('repair_actions'):
                parts.append(f"actions {proposal.get('repair_actions')}")
            lines.append('  proposal: ' + '; '.join(parts) + '.')
            for pair in proposal_review_pairs:
                if not isinstance(pair, dict):
                    continue
                paired_proposal = pair.get('proposal') if isinstance(pair.get('proposal'), dict) else {}
                if paired_proposal.get('proposal_id') != proposal.get('proposal_id'):
                    continue
                for review in pair.get('reviews') or []:
                    parts = [
                        f"id {review.get('review_id') or 'unknown'}",
                        f"proposal {review.get('proposal_id') or 'unknown'}",
                        f"status {review.get('status') or 'unknown'}",
                    ]
                    if review.get('reasons'):
                        parts.append(f"reasons {review.get('reasons')}")
                    lines.append('  matched review: ' + '; '.join(parts) + '.')
        review_items = graph_repair.get('unmatched_reviews') if proposal_review_pairs else graph_repair.get('reviews')
        for review in review_items or []:
            parts = [
                f"id {review.get('review_id') or 'unknown'}",
                f"proposal {review.get('proposal_id') or 'unknown'}",
                f"status {review.get('status') or 'unknown'}",
            ]
            if review.get('reasons'):
                parts.append(f"reasons {review.get('reasons')}")
            prefix = '  unmatched review: ' if proposal_review_pairs else '  review: '
            lines.append(prefix + '; '.join(parts) + '.')

    reconsideration = info.get('active_reconsideration') or {}
    if reconsideration:
        parts = [f"status {reconsideration.get('status') or 'unknown'}"]
        if reconsideration.get('decision_count') is not None:
            parts.append(f"decisions {reconsideration.get('decision_count')}")
        if reconsideration.get('category_counts'):
            parts.append(f"categories {reconsideration.get('category_counts')}")
        if reconsideration.get('recommended_actions'):
            parts.append(f"recommended actions {reconsideration.get('recommended_actions')}")
        lines.append('- Active reconsideration: ' + '; '.join(parts) + '.')

    repair_runtime = info.get('repair_runtime') or {}
    if repair_runtime:
        parts = []
        if repair_runtime.get('repair_loop_status'):
            parts.append(f"repair loop {repair_runtime.get('repair_loop_status')}")
        if repair_runtime.get('repair_loop_attempts') is not None:
            parts.append(f"attempts {repair_runtime.get('repair_loop_attempts')}")
        if repair_runtime.get('reconsideration_rebuild_status'):
            parts.append(f"reconsideration rebuild {repair_runtime.get('reconsideration_rebuild_status')}")
        parts.append(f"recovery candidates {repair_runtime.get('recovery_candidate_count', 0)}")
        parts.append(f"repair actions {repair_runtime.get('repair_action_count', 0)}")
        if repair_runtime.get('repair_actions'):
            parts.append(f"actions {repair_runtime.get('repair_actions')}")
        lines.append('- Repair runtime: ' + '; '.join(parts) + '.')

    freeze_guard = info.get('freeze_guard') or {}
    if freeze_guard:
        visible = 'yes' if freeze_guard.get('repair_needed_visible') else 'no'
        weak = 'yes' if freeze_guard.get('weak_freeze_watch') else 'no'
        suffix = f" Evidence: {freeze_guard.get('evidence')}." if freeze_guard.get('evidence') else ''
        lines.append(f'- Repair-needed visibility: {visible}; weak-freeze watch: {weak}.{suffix}')

    if not lines:
        lines.append('- No self-learning/healing diagnostics found in expanded response-frame truth.')
    return lines


def _render_human(report: dict[str, Any]) -> str:
    verdict = report['verdict']
    if verdict == 'clean':
        first = 'Latest run is clean at the runtime truth level.'
    elif verdict == 'running':
        first = 'Latest run is still running at the runtime truth level.'
    else:
        first = 'Latest run needs attention at the runtime truth level.'

    timing = report['timing']
    sizes = report['sizes']
    state_total = sizes['state_total_bytes']
    state_add = sizes['state_add_approx_bytes']
    snap_total = sizes['snapshots_total_bytes']
    snap_add = sizes['snapshots_add_bytes']
    art_total = sizes['artifacts_total_bytes']
    art_add = sizes['artifacts_add_bytes']

    image_models = report.get('image_models') or {}
    model_bits = ', '.join(f'{name} handled {count}' for name, count in sorted(image_models.items())) or 'no image branches'
    notes = '\n'.join(report.get('notes') or ['No notes.'])
    artifact_info = report.get('artifacts') or {}
    html_image_links = artifact_info.get('html_image_links') or []
    all_links_ok = all(item['exists'] for item in html_image_links)
    branch_role_counts = report.get('branch_role_counts') or {}
    branch_capability_counts = report.get('branch_capability_counts') or {}
    output_obligation_counts = report.get('output_obligation_counts') or {}
    artifact_kind_counts = artifact_info.get('artifact_kind_counts') or {}
    artifact_suffix_counts = artifact_info.get('artifact_file_count_by_suffix') or {}
    output_ref_counts = artifact_info.get('output_ref_counts') or {}
    audio_required_count = sum(
        count
        for key, count in output_obligation_counts.items()
        if _is_audio_kind(key)
    )
    audio_artifact_count = artifact_info.get('audio_artifact_count') or 0
    branch_counts = report.get('branch_counts') or {}
    diagnostics = report.get('timing_diagnostics') or {}
    phase_gaps = diagnostics.get('phase_gaps') or {}
    scheduling_policy = diagnostics.get('scheduling_policy') or {}
    waves = diagnostics.get('waves') or []
    branches = diagnostics.get('branches') or []
    backend_finalize = diagnostics.get('backend_finalize') or {}
    learning_healing_lines = _render_learning_healing_lines(report.get('learning_healing') or {})

    diagnostic_lines = []
    if scheduling_policy:
        diagnostic_lines.append(
            '- Late-fill scheduling policy: '
            f"{_format_scheduling_policy(scheduling_policy)}."
        )
    chat_to_image = phase_gaps.get('initial_chat_to_image_start_seconds')
    image_to_text = phase_gaps.get('image_end_to_text_start_seconds')
    terminal_to_hygiene = phase_gaps.get('terminal_to_hygiene_seconds')
    if chat_to_image is not None:
        diagnostic_lines.append(
            f"- Chat finish -> image wave start: {_fmt_seconds(chat_to_image)}; phase handoff/materialization scheduling."
        )
    if image_to_text is not None:
        diagnostic_lines.append(
            f"- Image wave end -> text pass start: {_fmt_seconds(image_to_text)}; dependency evidence handoff into text materialization."
        )
    if terminal_to_hygiene is not None:
        diagnostic_lines.append(
            f"- Terminal output -> hygiene done: {_fmt_seconds(terminal_to_hygiene)}; post-response cleanup/substrate hygiene."
        )
    post_wave_events = backend_finalize.get('post_wave_events') if isinstance(backend_finalize.get('post_wave_events'), list) else []
    post_wave_backends = [
        item for item in post_wave_events if isinstance(item, dict)
    ] or [
        item
        for item in (
            backend_finalize.get('post_wave'),
            backend_finalize.get('latest_event'),
        )
        if isinstance(item, dict) and item
    ]
    response_finalize = backend_finalize.get('response_frame_finalize') or {}
    for index, post_wave_backend in enumerate(post_wave_backends, 1):
        event_prefix = (
            f'#{index} '
            if len(post_wave_backends) > 1
            else ''
        )
        diagnostic_lines.append(
            '- Backend post-wave finalize '
            f"{event_prefix}{post_wave_backend.get('phase') or 'unknown'} status "
            f"{post_wave_backend.get('status') or 'unknown'}, "
            f"finalize {_fmt_seconds(post_wave_backend.get('finalize_seconds'))}, "
            f"lookup touch {_fmt_seconds(post_wave_backend.get('touch_response_lookup_seconds'))}; "
            f"branches pending={post_wave_backend.get('pending_branch_count')}, "
            f"active={post_wave_backend.get('active_branch_count')}, "
            f"completed={post_wave_backend.get('completed_branch_count')}, "
            f"failed={post_wave_backend.get('failed_branch_count')}."
        )
        if isinstance(post_wave_backend.get('response_frame_finalize'), dict):
            response_finalize = post_wave_backend.get('response_frame_finalize')
    if response_finalize:
        step_parts = []
        for step in response_finalize.get('steps') or []:
            name = step.get('name')
            if not name:
                continue
            step_parts.append(f"{name} {_fmt_seconds(step.get('elapsed_seconds'))}")
            if len(step_parts) >= 6:
                break
        step_suffix = f"; steps {', '.join(step_parts)}" if step_parts else ''
        diagnostic_lines.append(
            '- Backend response-frame finalize timing: '
            f"{response_finalize.get('phase') or 'unknown'} total "
            f"{_fmt_seconds(response_finalize.get('total_seconds'))}, "
            f"persist_effective={response_finalize.get('persist_effective')}"
            f"{step_suffix}."
        )
    for index, wave in enumerate(waves, 1):
        worker = wave.get('worker_count')
        max_workers = wave.get('max_parallel_workers')
        worker_text = (
            f'{worker}/{max_workers} max'
            if max_workers is not None
            else str(worker if worker is not None else 'unknown')
        )
        default_workers = wave.get('default_worker_count')
        capacity = wave.get('scheduling_capacity_units')
        default_text = default_workers if default_workers is not None else 'unknown'
        capacity_text = capacity if capacity is not None else 'unknown'
        source = wave.get('worker_count_source') or 'unknown'
        prepared = wave.get('prepared_branch_count')
        instance_count = wave.get('distinct_instance_count')
        guard = wave.get('gpu_heavy_guard') or 'unknown'
        reasons = '; '.join(wave.get('worker_limit_reasons') or ['no worker cap signal recorded'])
        progress_bits = []
        if wave.get('branch_progress_dispatch') is not None:
            progress_bits.append(f"progress dispatch {wave.get('branch_progress_dispatch')}")
        if wave.get('branch_progress_callback_count') is not None:
            progress_bits.append(f"callbacks {wave.get('branch_progress_callback_count')}")
        progress_text = f"{', '.join(progress_bits)}; " if progress_bits else ''
        diagnostic_lines.append(
            '- Wave '
            f"{index}: planning {_fmt_seconds(wave.get('planning_seconds'))}, "
            f"elapsed {_fmt_seconds(wave.get('elapsed_seconds'))}, "
            f"workers {worker_text} "
            f"(default {default_text}, source {source}, capacity {capacity_text}), "
            f"prepared branches {prepared}, selected instances {instance_count}, "
            f"gpu-heavy guard {guard}; {progress_text}{reasons}."
        )
        lock_groups = _format_instance_groups(wave.get('same_instance_lock_groups'))
        if lock_groups:
            diagnostic_lines.append(f'- Wave {index} same-instance lock groups: {lock_groups}.')
    for branch in branches[:8]:
        diagnostic_lines.append(
            '- '
            f"{branch.get('role')} {branch.get('branch_id')} on {branch.get('instance_id')}: "
            f"total {_fmt_seconds(branch.get('elapsed_seconds'))}, "
            f"queue {_fmt_seconds(branch.get('queued_seconds'))}, "
            f"lock {_fmt_seconds(branch.get('lock_wait_seconds'))}, "
            f"execution {_fmt_seconds(branch.get('execution_seconds'))}; "
            f"{branch.get('reason')}."
        )
    if len(branches) > 8:
        diagnostic_lines.append(f"- {len(branches) - 8} additional branch timing rows omitted from human summary; full JSON has them.")

    bad_lines = []
    if verdict == 'running':
        bad_lines.append('- Run is still active; no terminal failure verdict yet.')
    elif verdict != 'clean':
        bad_lines.append(
            '- Terminal state is '
            f"{report.get('lifecycle_state')} with late_fill.{report.get('late_fill_status')} "
            f"and final materialization contract {report.get('final_materialization_contract_status')}."
        )
    if report.get('materialization_contract_unmet'):
        bad_lines.append('- Final materialization contract is unmet.')
    if report.get('failed_branch_count') or branch_counts.get('failed'):
        bad_lines.append(
            '- Failed branches: '
            f"{branch_counts.get('failed', 0)} in final frame; "
            f"failed_branch_count={report.get('failed_branch_count')}."
        )
    if branch_counts.get('pending') and verdict != 'running':
        bad_lines.append(
            f"- Terminal frame still carries {branch_counts.get('pending')} pending branch entries; treated as terminal failure evidence, not live progress."
        )
    if artifact_info.get('missing_files'):
        bad_lines.append('- Missing artifact files: ' + ', '.join(artifact_info.get('missing_files') or []))
    if artifact_info.get('sha_mismatches'):
        bad_lines.append('- SHA mismatches: ' + ', '.join(artifact_info.get('sha_mismatches') or []))
    if artifact_info.get('html_issues') or artifact_info.get('css_issues'):
        bad_lines.append(
            '- Syntax sanity issues: '
            f"{len(artifact_info.get('html_issues') or [])} HTML, "
            f"{len(artifact_info.get('css_issues') or [])} CSS."
        )
        for issue in (artifact_info.get('html_issues') or [])[:2]:
            bad_lines.append(f"  HTML: {issue}")
        for issue in (artifact_info.get('css_issues') or [])[:2]:
            bad_lines.append(f"  CSS: {issue}")
    broken_links = [item.get('src') for item in artifact_info.get('html_image_links') or [] if not item.get('exists')]
    if broken_links:
        bad_lines.append('- Broken HTML image links: ' + ', '.join(str(item) for item in broken_links))
    if artifact_info.get('weak_viewport_tags'):
        bad_lines.append('- Weak viewport tag detected.')
    duplicate_ref_summary = artifact_info.get('duplicate_ref_summary') or {}
    bad_lines.extend(_duplicate_ref_lines(duplicate_ref_summary))
    if audio_required_count and not audio_artifact_count:
        bad_lines.append(
            '- Audio output obligation is present, but no saved audio artifact was detected in final artifacts.'
        )
    if not report.get('registry_parse_clean'):
        bad_lines.append('- Artifact registry did not parse cleanly.')
    if not bad_lines:
        bad_lines.append('- No failed branches, unmet contracts, missing files, SHA mismatches, broken links, or syntax issues detected.')

    lines = [
        first,
        '',
        f"Response: {report['response_id']}",
        f"Final frame: frame-{report.get('frame_sequence')}",
        (
            'State: '
            f"{report.get('lifecycle_state')}, "
            f"late_fill.{report.get('late_fill_status')}, "
            f"final materialization contract {report.get('final_materialization_contract_status')}."
        ),
        '',
        'Timing shape:',
        '',
        f"Start/response id: {_fmt_time(_parse_iso(timing.get('start')))}",
        (
            'Initial chat/graph finished: '
            f"{_fmt_time(_parse_iso(timing.get('initial_chat_finished')))}, "
            f"about {_fmt_seconds(timing.get('initial_chat_seconds'))}"
        ),
        (
            'Image wave: '
            f"{_fmt_time(_parse_iso(timing.get('image_wave_start')))} to "
            f"{_fmt_time(_parse_iso(timing.get('image_wave_end')))}, "
            f"about {_fmt_seconds(timing.get('image_wave_seconds'))}"
        ),
    ]
    if report.get('timing_attribution'):
        lines.append('Timing attribution: response-bound evidence; unattributed phase timings are unknown.')
        for warning in report['timing_attribution'].get('warnings', []):
            lines.append(f'Timing note: {warning}.')
    if 'post_image_chat_seconds' in timing:
        lines.append(f"Post-image chat pass: about {_fmt_seconds(timing.get('post_image_chat_seconds'))}")
    if 'coalesced_text_seconds' in timing:
        lines.append(f"Coalesced text pass: about {_fmt_seconds(timing.get('coalesced_text_seconds'))}")
    lines.extend(
        [
            f"Post-response hygiene finished: {_fmt_time(_parse_iso(timing.get('hygiene_finished')))}",
            (
                'So: about '
                f"{_fmt_seconds(timing.get('terminal_seconds'))} to terminal output, "
                f"{_fmt_seconds(timing.get('hygiene_seconds'))} including hygiene."
            ),
            '',
            'Size growth:',
            '',
            f"state: {_fmt_size(state_total)}, previously about {_fmt_size(state_total - state_add)}, about +{_fmt_size(state_add)}",
            f"snapshots: {_fmt_size(snap_total)}, previously about {_fmt_size(snap_total - snap_add)}, about +{_fmt_size(snap_add)}",
            f"artifacts: {_fmt_size(art_total)}, previously about {_fmt_size(art_total - art_add)}, about +{_fmt_size(art_add)}",
            f"latest response ledger line: {sizes.get('latest_response_line_bytes'):,} bytes",
            f"new snapshots for this run: {sizes.get('new_snapshot_file_count')} files, about {_fmt_size(snap_add)}",
            f"new artifacts: {sizes.get('new_artifact_file_count')} files, about {_fmt_size(art_add)}",
            '',
            'What improved / stayed good:',
            '',
            f"Branch roles: {_format_counts(branch_role_counts)}.",
            f"Capability routing/work: {_format_counts(branch_capability_counts)}.",
            f"Image routing: {model_bits}.",
            f"Output obligations: {_format_counts(output_obligation_counts)}.",
            f"Output artifact refs: {_format_counts(output_ref_counts)}.",
            f"Artifact kinds: {_format_counts(artifact_kind_counts)}.",
            f"Artifact file suffixes: {_format_counts(artifact_suffix_counts)}.",
            f"Audio artifacts: {audio_artifact_count} saved.",
            (
                f"HTML image links resolve: {'yes' if all_links_ok else 'no'}."
                if html_image_links
                else 'HTML image links: not applicable.'
            ),
            f"All artifact files exist: {'yes' if not report['artifacts'].get('missing_files') else 'no'}.",
            f"Registry parses cleanly: {'yes' if report.get('registry_parse_clean') else 'no'}.",
            (
                'Current syntax checker reports '
                f"{len(report['artifacts'].get('html_issues') or [])} HTML issues and "
                f"{len(report['artifacts'].get('css_issues') or [])} CSS issues."
            ),
            '',
            'What went bad / needs attention:',
            '',
            '\n'.join(bad_lines),
            '',
            'Learning / healing diagnostics:',
            '',
            '\n'.join(learning_healing_lines),
            '',
            'Notes:',
            '',
            notes,
            '',
            'Timing diagnostics / waits:',
            '',
            '\n'.join(diagnostic_lines) if diagnostic_lines else 'No detailed wait diagnostics available.',
        ]
    )
    return '\n'.join(lines)


