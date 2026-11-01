"""Offline campaign report rendering and explicit verdict scopes.

Consumes collected campaign results without running profiles, changing budgets,
rewriting captures or turning an observation into execution authority.
"""

from __future__ import annotations

from pathlib import Path


PRIORITIES = [
    ('commitment_closure', 'commitment ↔ closure'),
    ('aspiration_promotion', 'aspiration ↔ promotion'),
    ('repair_rebase_intent', 'repair/rebase ↔ anchored intent'),
    ('late_fill_binding', 'Late Fill ↔ exact evidence/source binding'),
    ('lenses_attention_scope', 'lenses/attention ↔ graph scope'),
]


def signatures(result):
    values = {(case['case_id'], f['code'], f.get('signature', '')) for case in result['cases'] for f in case['findings']}
    values |= {(f'@probe:{check["name"]}', f['code'], f.get('signature', ''))
               for check in result.get('probes', {}).get('checks', []) for f in check['findings']}
    return values


def verdict_scopes(result):
    """Report selected coverage separately; never promote the legacy verdict."""
    scopes = dict(deterministic_fake='incomplete', representative_live_gate='incomplete',
                  full_live_conformance='incomplete')
    if result['mode'] == 'fake':
        scopes['deterministic_fake'] = result['verdict']
        live = result.get('live') or {}
        scopes['representative_live_gate'] = (live.get('scoped_verdicts') or {}).get(
            'representative_live_gate', 'incomplete')
        if live.get('status') in {'passed', 'failed', 'incomplete'}:
            scopes['full_live_conformance'] = live['status']
        return scopes

    scopes['deterministic_fake'] = result.get('fake_conformance_verdict', 'incomplete')
    scopes['full_live_conformance'] = result['verdict']
    selected = result.get('selected_live_cases') or result['coverage'].get('case_selection') or {}
    sweep = result['runs'][:result['coverage']['profiles_selected']]
    observed = result['runs'] + result.get('confirmation_runs', [])
    failed = (result['verdict'] == 'failed' or any(signatures(run) for run in observed)
              or any(check.get('status') == 'failed' for run in observed
                     for check in run.get('probes', {}).get('checks', []))
              or any(owner.get('status') == 'failed' for owner in result['owner_tests'].values()))
    complete = (bool(selected) and len(selected) == result['coverage']['profiles_selected'] == len(sweep)
                and len({run['profile']['id'] for run in sweep}) == len(selected)
                and {run['profile']['id'] for run in sweep} == set(selected)
                and all(result['owner_tests'].get(key, {}).get('status') == 'passed' for key, _ in PRIORITIES)
                and not result.get('confirmation_stop_reason'))
    for run in sweep:
        expected = selected.get(run['profile']['id'], [])
        actual = [case['case_id'] for case in run['cases']]
        complete &= (bool(expected) and len(actual) == len(set(actual)) == len(expected)
                     and set(actual) == set(expected))
    for run in observed:
        complete &= (run.get('runner_status') == 0 and all(
            bool(case.get('capture_path')) and not case.get('missing', ['unobserved'])
            and case.get('state') in {'settled_terminal', 'settled_repair_needed'} for case in run['cases']))
    scopes['representative_live_gate'] = 'failed' if failed else 'passed' if complete else 'incomplete'
    return scopes


def render_report(result):
    sweep = result['runs'][:result['coverage']['profiles_selected']]
    observed = list({r.get('output', str(i)): r for i, r in enumerate(
        result['runs'] + result.get('confirmation_runs', []))}.values())
    lines = ['# Fruth self-attack conformance', '', '**Knobs may change strategy, never truth.**', '',
             f"Verdict: **{result['verdict']}** · mode: {result['mode']} · profiles: {len(sweep)}", '',
             'Pass/fail comes from deterministic runtime assertions. LLM prose has no vote.', '',
             (f"Offline recheck of `{result['recheck']['evidence_origin']}`; no requests were executed."
              if result.get('recheck') else ''), '',
             '| Priority | Boundary | Full captures / cases | Findings | Incomplete cases | Profile probes | Owner tests |',
             '|---|---|---:|---:|---:|---:|---|']
    labels = dict(passed='PASS', failed='FAIL', incomplete='INCOMPLETE')
    scopes = verdict_scopes(result)
    lines[6:6] = [
        f"Deterministic/fake conformance: **{labels[scopes['deterministic_fake']]}**",
        f"Representative live gate: **{labels[scopes['representative_live_gate']]}**",
        f"Full live conformance: **{labels[scopes['full_live_conformance']]}**", '',
        'Representative PASS covers only the selected profiles/cases. Full live PASS requires the complete intended live scope.',
        'A scope without sufficient recorded evidence remains INCOMPLETE.', '',
    ]
    if result.get('live'):
        lines[6:6] = [f"Live interpretive inference: **{result['live']['status']}** (separate observation; fake invariants remain authoritative).",
                      f"Combined observation verdict: **{result.get('overall_verdict', 'incomplete')}**.", '']
    for i, (key, label) in enumerate(PRIORITIES, 1):
        cases = [c for run in sweep for c in run['cases'] if c['category'] == key]
        owner = result['owner_tests'].get(key) or {}
        probes = [p for run in sweep for p in run.get('probes', {}).get('checks', []) if p['category'] == key]
        lines.append(f"| {i} | {label} | {sum(bool(c.get('capture_path')) and not c['missing'] for c in cases)}/{len(cases)} | {sum(len(c['findings']) for c in cases)} | "
                     f"{sum(bool(c['missing']) for c in cases)} | {sum(p['status'] == 'passed' for p in probes)}/{len(probes)} | {owner.get('status', 'not run')} |")
    lines += ['', '## Controls and coverage', '',
              f"Planned design: {result['coverage']['design']}. Profiles selected: {result['coverage']['profiles_selected']}/{result['coverage']['profiles_available']}.",
              f"Profiles with complete captures: {sum(not r['runner_status'] and not any(c['missing'] for c in r['cases']) for r in sweep)}/{result['coverage']['profiles_available']}. Regression replays are reported separately.",
              'Finite controls are derived from runtime catalogs and bounds; unobserved profiles are not counted as tested.',
              f"Inventory-only controls: {result['coverage']['inventory_only']}. See controls.json for exact sources and exclusions.",
              'Live runs change request controls only. Environment controls require the isolated fake-provider run.',
              'Fake runs exercise runtime owners with deterministic model/routing substitutes; they do not certify live interpretive inference interpretation.',
              '', '## Findings', '']
    if result['coverage'].get('case_selection'):
        selection = result['coverage']['case_selection']
        insert = lines.index('## Findings')
        lines[insert:insert] = [
            f"Explicit subset/window: {sum(map(len, selection.values()))} planned case executions across {len(selection)} profiles.",
            'Omitted profile/case combinations remain unobserved. Cross-profile comparisons apply only where the same case has captured baseline truth.',
            *[f"- `{profile}`: {', '.join(cases)}" for profile, cases in selection.items()], '',
        ]
    for run in observed:
        for check in run.get('probes', {}).get('checks', []):
            for f in check['findings']:
                lines.append(f"- `{run['profile']['id']}` / `{check['name']}`: **{f['code']}**")
        for case in run['cases']:
            for f in case['findings']:
                lines.append(f"- `{case['case_id']}` / `{run['profile']['id']}`: **{f['code']}** — {f['detail']}")
    if not any(signatures(r) for r in observed):
        lines.append('No deterministic invariant failures found in observed cases.')
    lines += ['', '## Incomplete observations', '']
    incomplete_cases = [c for r in observed for c in r['cases'] if c['missing']]
    for run in observed:
        for case in run['cases']:
            for item in case.get('incomplete_observations', []):
                lines.append(f"- `{run['profile']['id']}` / `{case['case_id']}`: **{item['classification']}** — {item['detail']}")
    if not incomplete_cases:
        lines.append('None in executed cases.')
    if result['coverage']['profiles_selected'] < result['coverage']['profiles_available']:
        lines.append('Missing scenario coverage: the selected profile limit excluded part of the planned sweep.')
    if result['coverage'].get('case_selection'):
        lines.append('Missing scenario coverage: the high-risk selection omits other profile/case combinations; it cannot establish full live conformance.')
    for key, label in PRIORITIES:
        if result['owner_tests'].get(key, {}).get('status') != 'passed':
            lines.append(f'Missing observability: {label} owner checks did not complete successfully.')
    lines += ['', '## Regressions', '']
    for regression in result['regressions']:
        lines.append(f"- {regression['status']}: {regression.get('path', regression.get('target'))}")
    if not result['regressions']:
        lines.append('No new reproducible failures persisted.')
    for replay in result.get('regression_replays', []):
        lines.append(f"- Existing regression **{replay['status']}**: `{replay['path']}`")
    if result.get('live_budget'):
        budget = result['live_budget']
        limits = budget['limits']
        lines += ['', '## Hard live limits', '',
                  f"Sequence observation ceiling: {limits['sequence_seconds']:g}s. Main sweep including preflight: {limits['main_seconds']:g}s. All confirmation work: {limits['confirmation_seconds']:g}s.",
                  f"Each additional profile replay: at most {limits['replay_seconds']:g}s. Total live execution: at most {limits['main_seconds'] + limits['confirmation_seconds']:g}s plus evidence/report finalization.",
                  f"Additional profile attempts consumed: {len(budget['attempts'])}/{limits['attempt_cap']} (saved regressions and paired baseline replays included).",
                  f"Exhausted limits: {', '.join(budget['exhausted']) or 'none'}.",
                  'Deadlines and attempts persist across resume. An exhausted limit cannot schedule more live work. Final report writing occurs with dispatch disabled; already submitted Fruth responses may continue.', '']
    if result.get('dispatch_window'):
        window = result['dispatch_window']
        counts = result['coverage']['window']
        lines += ['', '## Bounded dispatch window', '',
                  f"Execution status: **{result['execution_status']}**.",
                  f"Selected {counts['selected']}; dispatched identities {counts['dispatched']}; completed {counts['completed']}; selected remaining {counts['selected_remaining']}; full-matrix remaining {counts['remaining']}.",
                  f"Case cap {counts['case_cap']}; reserved slots {counts['reserved']}. All diagnostic retries, confirmations and reference cases share this allocation; observation GETs do not consume dispatch slots.",
                  'Reservations survive interruption. An ambiguous reservation is GET-only even if no POST result was retained. Unused reserved sequence slots are not refunded.',
                  'Case counts are not provider-call counts or guaranteed quota headroom. No reset time is assumed and no next window starts automatically.', '']
        if window.get('stop'):
            stop = window['stop']
            lines += [f"Stop reason: {stop['reason']}; provider {stop.get('provider', 'n/a')}; tier {stop.get('tier', 'n/a')}; response {stop.get('response_id', 'n/a')}; checkpoint {stop.get('checkpoint', 'n/a')}.", '']
    if result.get('manual_review'):
        lines += ['', '## Manual review required', '',
                  'These records preserve unresolved observations or unconfirmed findings. They are not automatically replayed.']
        for item in result['manual_review']:
            lines.append(f"- `{item['profile']}` / `{item.get('case_id') or item['kind']}`: {item['reason']} — [{Path(item['path']).name}]({item['path']})")
    if result.get('capture_validations'):
        lines += ['', '## Supplemental capture validation', '',
                  'These are newly fetched, read-only canonical captures of existing responses after the original run. '
                  'They supplement selected-case evidence; they do not relabel historical snapshots, rerun model work, '
                  'or claim that the original sequence captured the missing evidence within its deadline.']
        for validation in result['capture_validations']:
            lines.append(f"- `{validation['profile']}` / `{validation['case_id']}`: **{validation['status']}**; "
                         f"captured {validation['finished_at']}; unchanged oracle checked the affected case and its retained history. "
                         f"[Validation evidence]({validation['path']}).")
    lines += ['', '## Evidence', '',
              'results.json contains verdicts, settings, findings, reproduction records and coverage. Each profile directory contains the original shadow manifest, full captures, retained artifact bytes and (fake mode) the isolated runtime ledger/sidecars.',
              'Missing or unfinished observations make the result incomplete. A blocked runtime obligation can be truthful and is not by itself a conformance failure.', '']
    return '\n'.join(lines)


