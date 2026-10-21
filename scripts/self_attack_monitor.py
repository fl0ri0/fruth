"""Read-only terminal overview for this existing Fruth self-attack run.

Adapted from the per-campaign Ollmo monitor.py: duration formatting, refreshing
terminal display and evidence-only reporting. Reads native manifests directly;
does not need the old campaign's observer.py or write progress.json.
"""
from collections import Counter
from datetime import datetime
from pathlib import Path
import argparse
import json
import sys
import time

CHECKOUT = Path(__file__).resolve().parents[1]
if str(CHECKOUT) not in sys.path:
    sys.path.insert(0, str(CHECKOUT))
from scripts.storage_locations import find as find_storage

ROOT = Path.cwd()
SETTLED = {'settled_terminal', 'settled_repair_needed'}
_cache = {}
_read_errors = set()
_observed_mtimes = []


def epoch(value):
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    except (AttributeError, TypeError, ValueError):
        return None


def duration(value):
    if value is None:
        return 'UNKNOWN'
    minutes, seconds = divmod(max(0, int(value)), 60)
    hours, minutes = divmod(minutes, 60)
    return f'{hours}h {minutes:02}m {seconds:02}s' if hours else f'{minutes}m {seconds:02}s'


def load(path, project=None):
    """Cache unchanged files; retain only projected case fields, not large payloads."""
    try:
        info = path.stat()
        signature = (info.st_mtime_ns, info.st_size)
        _observed_mtimes.append(info.st_mtime)
        previous = _cache.get(path)
        if previous and previous[0] == signature:
            return previous[1]
        data = json.loads(path.read_text())
        if project:
            data = project(data)
        _cache[path] = (signature, data)
        return data
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, TypeError, KeyError):
        _read_errors.add(str(path))
        return _cache.get(path, (None, {}))[1]


def case_projection(manifest):
    fields = ('case_id', 'state', 'submitting_at', 'submitted_at', 'post_finished_at',
              'settled_at', 'updated_at', 'last_lifecycle_state', 'last_observed_at')
    return {'cases': [{key: case.get(key) for key in fields}
                      for case in manifest.get('cases', [])]}


def progress_bar(done, total):
    fraction = min(1, done / total) if total else 0
    filled = int(fraction * 24)
    return '[' + '#' * filled + '-' * (24 - filled) + f'] {done}/{total}'


def case_outcome(case):
    if case.get('findings'):
        return 'FINDING'
    if (case.get('missing') or case.get('incomplete_observations')
            or case.get('state') not in SETTLED):
        return 'INCOMPLETE'
    return 'PASS'


def phase_snapshot(directory, now, *, stopped_at=None):
    manifest = load(directory / 'run.json')
    final = load(directory / 'results.json')
    progress = final or load(directory / 'progress.json')
    profiles = manifest.get('profiles', [])
    runs = progress.get('runs', [])
    returned = {run['profile']['id'] for run in runs}
    oracle = {(run['profile']['id'], case['case_id']): case
              for run in runs for case in run.get('cases', [])}
    case_selection = manifest.get('case_selection') or progress.get('coverage', {}).get('case_selection') or {}
    default_cases = len(manifest.get('corpus', {}).get('cases', []))
    total = sum(len(case_selection.get(profile['id'], [])) if case_selection else default_cases
                for profile in profiles)
    recorded = {}
    for profile in profiles:
        pid = profile['id']
        profile_root = directory / pid
        paths = sorted(profile_root.glob('sequence-*/manifest.json'))
        if not paths and (profile_root / 'manifest.json').is_file():
            paths = [profile_root / 'manifest.json']
        for path in paths:
            for case in load(path, case_projection).get('cases', []):
                recorded[(pid, case['case_id'])] = case
    settled = {key for key, case in recorded.items() if case.get('state') in SETTLED}
    started = {key for key, case in recorded.items()
               if case.get('submitting_at') or case.get('submitted_at')}
    active = [(key, case) for key, case in recorded.items()
              if key in started and key not in settled and key[0] not in returned]
    active.sort(key=lambda pair: pair[1].get('updated_at') or '', reverse=True)
    outcomes = Counter(case_outcome(case) for case in oracle.values())
    recent = sorted(((key, case) for key, case in recorded.items() if key in settled),
                    key=lambda pair: pair[1].get('settled_at') or '', reverse=True)[:6]
    starts = [value for case in recorded.values()
              if (value := epoch(case.get('submitting_at') or case.get('submitted_at'))) is not None]
    phase_end = epoch(final.get('finished_at')) or stopped_at or now
    elapsed = max(0, phase_end - min(starts)) if starts else None
    eta = None
    if elapsed is not None and 2 <= len(returned) < len(profiles) and not final:
        eta = elapsed / len(returned) * (len(profiles) - len(returned))
    budget = load(directory / 'live-budget.json')
    return dict(manifest=manifest, final=final, progress=progress, profiles=profiles,
                returned=returned, oracle=oracle, total=total, recorded=recorded,
                settled=settled, started=started, active=active, outcomes=outcomes,
                recent=recent, elapsed=elapsed, eta=eta, budget=budget)


def render():
    _read_errors.clear()
    _observed_mtimes.clear()
    now = time.time()
    process = load(ROOT / 'process.json')
    completion = load(ROOT / 'completion.json')
    stopped_at = epoch(completion.get('finished_at'))
    own_manifest = load(ROOT / 'run.json')
    standalone_live = own_manifest.get('mode') == 'live'
    if standalone_live:
        argv = process.get('argv', [])
        proof_name = (own_manifest.get('fake_gate') or {}).get('path') or (live_result.get('fake_evidence') if (live_result := load(ROOT / 'results.json')) else None)
        if not proof_name and '--fake-evidence' in argv:
            proof_name = argv[argv.index('--fake-evidence') + 1]
        proof = Path(proof_name) if proof_name else ROOT / 'missing-fake-evidence/results.json'
        if proof_name and not proof.exists():
            try:
                proof = find_storage(CHECKOUT, 'self_attack', proof)
            except (OSError, ValueError) as exc:
                _read_errors.add(str(exc))
        fake = phase_snapshot(proof.parent, now)
        live = phase_snapshot(ROOT, now, stopped_at=stopped_at)
    else:
        fake = phase_snapshot(ROOT, now, stopped_at=stopped_at)
        live = phase_snapshot(ROOT / 'live', now, stopped_at=stopped_at) if (ROOT / 'live/run.json').is_file() else None
    current = live or fake
    window = load((ROOT if standalone_live else ROOT / 'live') / 'dispatch-window.json')
    mode = 'LIVE' if live else 'DETERMINISTIC / FAKE'
    start = epoch(process.get('started_at') or fake['progress'].get('started_at'))
    end = epoch(completion.get('finished_at')) or now
    status = f"FINISHED — exit {completion.get('exit_code', 'UNKNOWN')}" if completion else 'OBSERVING — no completion record yet'
    gate = fake['final'].get('verdict', 'pending').upper()
    owners = fake['progress'].get('owner_tests', {})
    out = ['FRUTH SELF-ATTACK', '=' * 76, ROOT.name,
           f'Status: {status}', f'Stage: {mode} | Total elapsed: {duration(end - start if start else None)}',
           f'Offline gate: {gate} | Owner groups: {sum(v.get("status") == "passed" for v in owners.values())}/{len(owners)} passed',
           f'Offline profiles returned: {len(fake["returned"])}/{len(fake["profiles"])}', '']
    if standalone_live:
        out.append(f'Matching offline gate reused from: {proof.parent.name}')
    if not live and '--live-after-fake' in process.get('argv', []):
        out.append('Live stage: not started (requires the native offline PASS)')
    out += [f'Profiles returned  {progress_bar(len(current["returned"]), len(current["profiles"]))}',
            f'Cases settled      {progress_bar(len(current["settled"]), current["total"])}',
            f'Cases started: {len(current["started"])} | Oracle records: {len(current["oracle"])}',
            f'Case checks: PASS {current["outcomes"]["PASS"]} | INCOMPLETE {current["outcomes"]["INCOMPLETE"]} | with findings {current["outcomes"]["FINDING"]}',
            f'Settled cases awaiting oracle: {len(current["settled"] - current["oracle"].keys())}']
    if window:
        coverage = current['final'].get('coverage', {}).get('window', {})
        reason = (window.get('stop') or {}).get('reason') or current['final'].get('execution_status', 'running')
        dispatched = len(window.get('dispatches', {}))
        reserved = sum(len(s['case_ids']) for s in window.get('sequences', {}).values())
        completed = coverage.get('completed', current['outcomes']['PASS'])
        out += [f'Dispatch state: {reason}',
                f"Window: selected {current['total']} | dispatched/reserved identities {dispatched}/{reserved} | completed {completed} | selected remaining {current['total'] - completed}",
                f"Full-matrix remaining: {coverage.get('remaining', 'UNKNOWN')} | case cap {window.get('case_cap')} (diagnostics included)",
                'Case counts are not provider-call counts or quota headroom. No next window starts automatically.']
        if window.get('stop'):
            stop = window['stop']
            out.append(f"Stop witness: provider={stop.get('provider', 'n/a')} tier={stop.get('tier', 'n/a')} response={stop.get('response_id', 'n/a')} checkpoint={stop.get('checkpoint', 'n/a')}")
    if completion:
        eta = 'finished'
    elif current['budget'].get('stage') == 'confirmation' or (current['profiles'] and len(current['returned']) == len(current['profiles'])):
        eta = 'main sweep returned; confirmation/reporting or stage transition — ETA unknown'
    elif current['eta'] is not None:
        finish = datetime.fromtimestamp(now + current['eta']).astimezone().strftime('%H:%M:%S')
        eta = f'~{duration(current["eta"])} (rough, stage sweep only; ~{finish})'
    else:
        eta = 'warming up'
    out += [f'Sweep elapsed: {duration(current["elapsed"])} | ETA: {eta}', '', 'Current recorded work:']
    if completion:
        out.append('  Test controller finished. Any incomplete cases remain in the final report.')
    elif current['active']:
        for (profile, cid), case in current['active'][:6]:
            began = epoch(case.get('submitting_at') or case.get('submitted_at'))
            out += [f'  {profile} / {cid}',
                    f'    {case.get("state", "UNKNOWN")} | lifecycle {case.get("last_lifecycle_state") or "UNKNOWN"} | elapsed {duration(now - began if began else None)}']
    else:
        out.append('  No active case recorded; may be between cases or checking evidence.')
    out += ['', 'Recent settled cases:']
    for key, case in current['recent']:
        outcome = case_outcome(current['oracle'][key]) if key in current['oracle'] else 'AWAITING ORACLE'
        begin, stop = epoch(case.get('submitting_at') or case.get('submitted_at')), epoch(case.get('settled_at'))
        out.append(f'  {key[0]} / {key[1]:<20} {outcome:<15} {duration(stop - begin if begin and stop else None)}')
    if current['final']:
        out += ['', f'Native stage verdict: {current["final"].get("verdict", "UNKNOWN").upper()}']
        for scope, verdict in current['final'].get('scoped_verdicts', {}).items():
            value = verdict.get('verdict', verdict.get('status', 'UNKNOWN')) if isinstance(verdict, dict) else verdict
            out.append(f'  {scope}: {value}')
    age = now - max(_observed_mtimes) if _observed_mtimes else None
    out += ['', f'Latest progress evidence: {duration(age)} ago | refreshed {datetime.now().astimezone():%H:%M:%S}',
            'Evidence-only view; controller health is not probed. The harness owns verdicts.',
            'ETA excludes later stages and confirmation. Ctrl-C stops this display only.']
    if _read_errors:
        out.append(f'Partial read: {len(_read_errors)} changing/unreadable file(s); retrying on next refresh.')
    return '\n'.join(out)


def main(argv=None):
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='Existing native campaign path or registered run name (read-only).')
    parser.add_argument('--once', action='store_true', help='Print one snapshot and exit.')
    args = parser.parse_args(argv)
    try:
        ROOT = (args.output.resolve() if args.output.is_dir()
                else find_storage(CHECKOUT, 'self_attack', args.output))
        if not ROOT.is_dir():
            raise ValueError(f'Campaign is not a directory: {ROOT}')
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    _cache.clear()
    try:
        while True:
            output = render()
            print(('\033[2J\033[H' if sys.stdout.isatty() else '') + output, flush=True)
            if args.once:
                return
            time.sleep(5)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
