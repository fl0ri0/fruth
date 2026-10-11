"""Bounded diagnostic dispatch and read-only campaign evidence composition.

This module owns no runtime policy. Its ledger counts case POST identities, never
provider invocations. Native evidence is immutable input to previews/aggregation.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import threading

from scripts.run_graph_rebase_shadow_corpus import (
    CorpusError, atomic_write_json, manifest_lock, stable_digest, utc_now,
)
from scripts.self_attack_checks import compare_profiles

SETTLED = {'settled_terminal', 'settled_repair_needed'}
UNDISPATCHED = {'planned', 'unobserved', 'waiting_runtime', 'dependency_blocked'}
QUOTA_MESSAGE = re.compile(
    r'\b(?:you have reached the usage limit for this model|'
    r'(?:usage limit|daily limit|quota) (?:has been )?(?:reached|exceeded|exhausted))\b', re.I)


def sequence_corpora(raw):
    groups = [{c['case_id']} for c in raw['cases']]
    by_id = {c['case_id']: c for c in raw['cases']}
    changed = True
    while changed:
        changed = False
        for i, a in enumerate(groups):
            for j in range(i + 1, len(groups)):
                b = groups[j]
                connected = any(set(by_id[k].get('depends_on', [])) & b for k in a)
                connected |= any(set(by_id[k].get('depends_on', [])) & a for k in b)
                connected |= bool({by_id[k].get('conversation_key', k) for k in a}
                                  & {by_id[k].get('conversation_key', k) for k in b})
                if connected:
                    groups[i] |= groups.pop(j)
                    changed = True
                    break
            if changed:
                break
    return [dict(raw, cases=[c for c in raw['cases'] if c['case_id'] in group]) for group in groups]


def select_cases(raw, profiles, selectors=()):
    """A selector is CASE or PROFILE:CASE; select the entire connected sequence."""
    ids = {c['case_id'] for c in raw['cases']}
    pids = {p['id'] for p in profiles}
    requested = {p: set() for p in pids}
    for value in selectors:
        if ':' in value:
            pid, cid = value.split(':', 1)
            if pid not in pids:
                raise CorpusError(f'Case selector has an unselected profile: {pid}')
            targets = [pid]
        else:
            cid, targets = value, pids
        if cid not in ids:
            raise CorpusError(f'Unknown case/sequence ID: {cid}')
        for pid in targets:
            requested[pid].add(cid)
    selection = {}
    for profile in profiles:
        pid = profile['id']
        wanted = requested[pid] if selectors else ids
        closed = {c['case_id'] for group in sequence_corpora(raw)
                  if wanted & {c['case_id'] for c in group['cases']} for c in group['cases']}
        if closed:
            selection[pid] = [c['case_id'] for c in raw['cases'] if c['case_id'] in closed]
    if not selection:
        raise CorpusError('No cases selected.')
    return selection


def plan_windows(raw, profiles, selection, cap):
    if isinstance(cap, bool) or not isinstance(cap, int) or not 1 <= cap <= 100:
        raise CorpusError('The case cap must be an integer from 1 through 100.')
    windows, current, count = [], {}, 0
    for profile in profiles:
        pid = profile['id']
        for group in sequence_corpora(raw):
            cases = [c['case_id'] for c in group['cases']]
            if not set(cases) & set(selection.get(pid, [])):
                continue
            if not set(cases) <= set(selection[pid]):
                raise CorpusError('Window selection must include the entire dependency-connected sequence.')
            if len(cases) > cap:
                raise CorpusError(f'Sequence {pid}:{cases[0]} cannot fit the case cap {cap}.')
            if count + len(cases) > cap:
                windows.append(current)
                current, count = {}, 0
            current.setdefault(pid, []).extend(cases)
            count += len(cases)
    if current:
        windows.append(current)
    return windows


def local_full_plan(raw, profiles, *, attempt_cap, campaign_id):
    """One local allocation, including the existing bounded diagnostic allowance."""
    if isinstance(attempt_cap, bool) or not isinstance(attempt_cap, int) or attempt_cap < 0:
        raise CorpusError('The extra live attempt cap must be a nonnegative integer.')
    selection = select_cases(raw, profiles)
    main_cases = sum(map(len, selection.values()))
    diagnostic_cases = attempt_cap * len(raw['cases'])
    return dict(number=1, scope='local_full_sweep', case_cap=main_cases + diagnostic_cases,
                main_cases=main_cases, diagnostic_cases=diagnostic_cases,
                windows=[selection], requested=selection, campaign_id=campaign_id)


def require_local_configuration(configuration):
    """A full local sweep must not spend PCC or external-provider quota."""
    local = {'ollama', 'mlx', 'apple_fm'}
    if (not isinstance(configuration, dict) or not configuration.get('models')
            or any(model.get('backend') not in local for model in configuration['models'])):
        raise CorpusError('Full local sweeps require only ready Ollama/MLX/AFM models; PCC uses bounded windows.')
    preferences = configuration.get('preferences')
    if not isinstance(preferences, dict):
        raise CorpusError('Full local sweeps require observed inference preferences.')
    for key in ('primary_target', 'fallback_target', 'embedding_helper'):
        target = preferences.get(key)
        if target is not None and (not isinstance(target, dict) or target.get('backend') not in local):
            raise CorpusError('Full local sweeps cannot target PCC or external providers.')


def pcc_records(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == 'pcc_execution' and isinstance(child, dict):
                yield child
            elif key not in {'response_frame', 'reference', 'reference_artifacts', 'accepted_learning_hints',
                             'input', 'inference_messages', 'output_text'}:
                yield from pcc_records(child)
    elif isinstance(value, list):
        for child in value:
            yield from pcc_records(child)


def quota_evidence(payload, *, response_id=None, transport_error=None):
    """Inspect native diagnostic fields only; HTTP 429 or model prose is insufficient."""
    if not isinstance(payload, dict):
        payload = {}
    runtime = payload.get('runtime') or {}
    failover = runtime.get('provider_failover') or {}
    candidates = []
    for attempt in failover.get('attempts') or []:
        if isinstance(attempt, dict):
            candidates.append((attempt, '/runtime/provider_failover/attempts'))
    for execution in pcc_records(runtime):
        candidates += [(dict(a, backend='apple_pcc'), '/runtime/pcc_execution/attempts')
                       for a in execution.get('attempts', []) if isinstance(a, dict)]
        candidates.append((dict(execution, backend='apple_pcc'), '/runtime/pcc_execution'))
    # Native error/transport diagnostics are not generated assistant text.
    error = payload.get('error')
    if isinstance(error, dict):
        candidates.append((error, '/error'))
    elif isinstance(error, str):
        candidates.append((dict(error_message=error), '/error'))
    if transport_error:
        candidates.append((dict(error_message=transport_error), 'http_transport_error'))
    for diagnostic, path in candidates:
        message = diagnostic.get('error_message') or diagnostic.get('message') or diagnostic.get('stderr') or ''
        reason = diagnostic.get('reason') or diagnostic.get('code') or diagnostic.get('fallback_reason')
        if reason not in {'provider_usage_limit', 'pro_usage_limit'} and not (isinstance(message, str) and QUOTA_MESSAGE.search(message)):
            continue
        backend = diagnostic.get('backend') or diagnostic.get('provider')
        model = diagnostic.get('model')
        return dict(reason='provider_usage_limit', provider=backend or 'unknown',
                    tier='cloud-pro' if reason == 'pro_usage_limit' else model if model in {'cloud', 'cloud-pro'} else 'unknown', requested_model=model,
                    response_id=response_id or payload.get('id') or payload.get('response_id'),
                    evidence_path=path, diagnostic=deepcopy(diagnostic))
    return None


class DispatchWindow:
    """Atomic cross-worker reservations. A consumed reservation is never refunded."""
    def __init__(self, output, *, cap=None, allocation=None):
        self.path = Path(output) / 'dispatch-window.json'
        self.lock = threading.RLock()
        if cap is not None:
            local_full = (allocation or {}).get('scope') == 'local_full_sweep'
            if local_full:
                main_cases = sum(map(len, allocation['requested'].values()))
                if (allocation['number'] != 1 or allocation['windows'] != [allocation['requested']]
                        or allocation['main_cases'] != main_cases or allocation['diagnostic_cases'] < 0
                        or cap != main_cases + allocation['diagnostic_cases'] or cap < 1):
                    raise CorpusError('Invalid full local sweep allocation.')
            elif not 1 <= cap <= 100:
                raise CorpusError('Case cap must be between 1 and 100.')
            with self.lock, manifest_lock(self.path, blocking=True):
                if self.path.exists():
                    state = self.read()
                    if state['case_cap'] != cap or state['allocation'] != allocation:
                        raise CorpusError('Dispatch allocation differs; resume cannot replenish or change its cap.')
                else:
                    atomic_write_json(self.path, dict(schema_version=1, case_cap=cap, allocation=allocation,
                        started_at=utc_now(), sequences={}, dispatches={}, stop=None))
        elif not self.path.is_file():
            raise CorpusError('Missing persisted dispatch window.')

    def read(self):
        return json.loads(self.path.read_text())

    def stop_reason(self):
        stop = self.read()['stop']
        return stop['reason'] if stop else None

    def admit_sequence(self, key, case_ids, *, kind):
        with self.lock, manifest_lock(self.path, blocking=True):
            state = self.read()
            if (state.get('allocation') or {}).get('scope') == 'local_full_sweep':
                require_local_configuration(state.get('configuration'))
            existing = state['sequences'].get(key)
            if existing:
                if existing['case_ids'] != case_ids or existing['kind'] != kind:
                    raise CorpusError('Sequence reservation changed during resume.')
                # Existing allocations may be observed after a quota stop.
                return None
            if state['stop']:
                return state['stop']['reason']
            reserved = sum(len(s['case_ids']) for s in state['sequences'].values())
            if reserved + len(case_ids) > state['case_cap']:
                state['stop'] = dict(reason='case_cap_stop', recorded_at=utc_now(),
                    checkpoint=key, reserved=reserved, next_sequence_cases=len(case_ids),
                    dispatched=len(state['dispatches']))
                atomic_write_json(self.path, state)
                return 'case_cap_stop'
            state['sequences'][key] = dict(case_ids=case_ids, kind=kind, reserved_at=utc_now())
            atomic_write_json(self.path, state)
            return None

    def reserve_dispatch(self, key, case):
        with self.lock, manifest_lock(self.path, blocking=True):
            state = self.read()
            if (state.get('allocation') or {}).get('scope') == 'local_full_sweep':
                require_local_configuration(state.get('configuration'))
            identity = case['response_id']
            # This order preserves an ambiguous reservation even after quota stop.
            if identity in state['dispatches']:
                return 'dispatch_identity_already_reserved'
            if state['stop']:
                return state['stop']['reason']
            sequence = state['sequences'].get(key)
            if not sequence or case['case_id'] not in sequence['case_ids']:
                raise CorpusError('Dispatch has no sequence allocation.')
            if sum(d['sequence'] == key for d in state['dispatches'].values()) >= len(sequence['case_ids']):
                raise CorpusError('Sequence dispatch allocation exhausted.')
            state['dispatches'][identity] = dict(sequence=key, case_id=case['case_id'],
                kind=sequence['kind'], reserved_at=utc_now(), status='submitted_or_ambiguous')
            atomic_write_json(self.path, state)
            return None

    def detect_quota(self, payload, *, response_id=None, transport_error=None, checkpoint=None):
        evidence = quota_evidence(payload, response_id=response_id, transport_error=transport_error)
        if not evidence:
            return
        with self.lock, manifest_lock(self.path, blocking=True):
            state = self.read()
            if state['stop'] and state['stop']['reason'] == 'provider_usage_limit':
                first = state['stop']
                if first.get('response_id') == evidence.get('response_id'):
                    for key in ('provider', 'tier'):
                        if first.get(key) == 'unknown' and evidence.get(key) != 'unknown':
                            first[key] = evidence[key]
                    atomic_write_json(self.path, state)
                return
            state['stop'] = dict(evidence, recorded_at=utc_now(), checkpoint=checkpoint,
                dispatched=len(state['dispatches']),
                reserved=sum(len(s['case_ids']) for s in state['sequences'].values()))
            atomic_write_json(self.path, state)

    def bind_configuration(self, configuration):
        with self.lock, manifest_lock(self.path, blocking=True):
            state = self.read()
            if (state.get('allocation') or {}).get('scope') == 'local_full_sweep':
                require_local_configuration(configuration)
            if state.get('configuration') and state['configuration'] != configuration:
                raise CorpusError('Serving configuration changed during the persisted window.')
            state['configuration'] = configuration
            atomic_write_json(self.path, state)


def read_json(path):
    return json.loads(Path(path).read_text())


def file_receipt(path):
    path = Path(path).resolve()
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def runtime_files(inventory):
    files = inventory.get('source_files')
    if not isinstance(files, dict) or stable_digest(files) != inventory.get('source_digest'):
        raise CorpusError('Source file inventory is missing or inconsistent.')
    result = {k: v for k, v in files.items() if k.endswith('.py') and not k.startswith(('scripts/', 'tests/'))}
    if not result:
        raise CorpusError('Runtime source inventory is empty.')
    return result


def compatible_runtime_inputs(controls, current, attestations=()):
    if runtime_files(controls) != runtime_files(current):
        raise CorpusError('Incompatible runtime source files.')
    expected = current.get('runtime_inputs')
    if not expected:
        raise CorpusError('Current runtime input inventory is missing.')
    if controls.get('runtime_inputs'):
        if controls['runtime_inputs'] != expected:
            raise CorpusError('Runtime prompt/config/static inputs differ.')
        return []
    # Explicit legacy provenance, anchored to native source identity and the
    # original immutable snapshot. An arbitrary new snapshot is not sufficient.
    for path in attestations:
        receipt = read_json(path)
        if receipt.get('native_harness_source_digest') != controls['source_digest']:
            continue
        snapshot = Path(receipt.get('validation_source', ''))
        sources = receipt.get('source_files')
        if not snapshot.is_dir() or not isinstance(sources, dict):
            raise CorpusError('Legacy source attestation has no retained source/files.')
        for name, digest in sources.items():
            relative = Path(name)
            if relative.is_absolute() or '..' in relative.parts:
                raise CorpusError('Unsafe source attestation path.')
            source = snapshot / relative
            if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != digest:
                raise CorpusError('Original validation snapshot no longer matches its source attestation.')
        for name, digest in expected.items():
            if sources.get(name) != digest:
                raise CorpusError('Current runtime inputs differ from the attested original source.')
        for name, digest in runtime_files(controls).items():
            source = snapshot / name
            if not source.is_file() or stable_digest(source.read_text(encoding='utf-8')) != digest:
                raise CorpusError('Source attestation differs from native runtime fingerprint.')
        return [file_receipt(path)]
    raise CorpusError('Legacy evidence lacks runtime-input provenance; supply its original --source-attestation.')


def final_capture(case, evidence_root):
    folder = Path(case.get('capture_path', ''))
    if not folder.is_absolute():
        folder = Path(evidence_root) / folder
    if not folder.is_relative_to(Path(evidence_root).resolve()):
        raise CorpusError('Capture path is outside its evidence window.')
    candidates = []
    for path in folder.glob('*.json'):
        # Native sorted-key JSON puts source at the end; avoid loading huge
        # intermediate captures when only settled truth is needed.
        with path.open('rb') as stream:
            stream.seek(-min(path.stat().st_size, 180), 2)
            tail = stream.read()
        if b'"source": "settled"' not in tail:
            continue
        data = read_json(path)
        if data.get('source') == 'settled':
            candidates.append((data['observed_ns'], path, data))
    if not candidates:
        raise CorpusError(f'No settled capture for {case.get("response_id")}')
    _, path, data = max(candidates, key=lambda x: x[0])
    if data['payload'].get('id') != case['response_id']:
        raise CorpusError('Capture response identity differs from its case.')
    return path, data


def native_cases(directory, config, results):
    """Join native oracle records to native manifests, never infer POST from state."""
    output = {}
    profiles = {p['id']: p for p in config['profiles']}
    for run in results['runs'][:len(config['profiles'])]:
        pid = run['profile']['id']
        if profiles.get(pid) != run['profile']:
            raise CorpusError('Native profile settings differ from the campaign manifest.')
        manifests = {}
        for path in (Path(directory) / pid).glob('sequence-*/manifest.json'):
            for entry in read_json(path)['cases']:
                if entry['case_id'] in manifests:
                    raise CorpusError('Duplicate native case manifest.')
                manifests[entry['case_id']] = (path, entry)
        for case in run['cases']:
            key = (pid, case['case_id'])
            if key in output:
                raise CorpusError('Duplicate native case verdict.')
            path, entry = manifests.get(case['case_id'], (None, {}))
            if entry and (entry['response_id'] != case.get('response_id') or entry['state'] != case['state']):
                raise CorpusError('Native verdict/manifest identity or state conflict.')
            if not entry and case.get('state') != 'unobserved':
                raise CorpusError('Native case manifest is missing.')
            output[key] = dict(case=case, entry=entry, manifest=path)
    return output


def preview_recovery(directory):
    directory = Path(directory).resolve()
    config, result = read_json(directory / 'run.json'), read_json(directory / 'results.json')
    if config.get('mode') != 'live' or result.get('mode') != 'live':
        raise CorpusError('Recovery requires retained native live evidence.')
    native = native_cases(directory, config, result)
    missing, observe, prior = {}, [], {}
    for profile in config['profiles']:
        pid = profile['id']
        for raw_case in config['corpus']['cases']:
            cid = raw_case['case_id']
            if config.get('case_selection') and cid not in config['case_selection'].get(pid, []):
                continue
            record = native.get((pid, cid))
            if not record:
                raise CorpusError('Retained report does not account for its complete requested scope.')
            case, entry = record['case'], record['entry']
            submitted = bool(entry.get('submitting_at') or entry.get('submitted_at'))
            link = dict(response_id=case.get('response_id'), state=case['state'],
                        manifest=file_receipt(record['manifest']) if record['manifest'] else None,
                        submitted=submitted, missing=case.get('missing', []), findings=case.get('findings', []))
            if case.get('capture_path'):
                path, data = final_capture(case, directory)
                link.update(capture=file_receipt(path), lifecycle=data['payload'].get('lifecycle_state'),
                            quota=quota_evidence(data['payload']), error=data['payload'].get('error'))
            prior[f'{pid}:{cid}'] = link
            if case.get('missing') or case.get('findings') or case['state'] not in SETTLED:
                missing.setdefault(pid, []).append(cid)
                if entry and (case['state'] not in SETTLED and
                              (submitted or case['state'] not in UNDISPATCHED)):
                    observe.append(dict(profile_id=pid, case_id=cid, **link))
    selectors = [f'{pid}:{cid}' for pid, ids in missing.items() for cid in ids]
    selection = select_cases(config['corpus'], config['profiles'], selectors) if selectors else {}
    # A connected sequence cannot be rerun fresh while ANY member is unresolved.
    for pid, ids in selection.items():
        for cid in ids:
            record = native[(pid, cid)]
            case, entry = record['case'], record['entry']
            if entry and case['state'] not in SETTLED and (entry.get('submitting_at') or entry.get('submitted_at')
                                                         or case['state'] not in UNDISPATCHED):
                if not any(o['profile_id'] == pid and o['case_id'] == cid for o in observe):
                    observe.append(dict(profile_id=pid, case_id=cid, **prior[f'{pid}:{cid}']))
    repeated = [f'{pid}:{cid}' for pid, ids in selection.items() for cid in ids if cid not in missing.get(pid, [])]
    return dict(schema_version=1, execution_performed=False, evidence_origin=str(directory),
        provenance=[file_receipt(directory / name) for name in ('run.json', 'results.json', 'controls.json')],
        source_digest=config['source_digest'], seed=config['seed'], native_verdict=result['verdict'],
        missing=missing, missing_cells=sum(map(len, missing.values())), selection=selection,
        fresh_case_count=sum(map(len, selection.values())), repeated_predecessors=repeated,
        observe_existing=observe, fresh_attempt_allowed=not observe,
        prior_evidence={key: prior[key] for pid, ids in selection.items() for cid in ids for key in [f'{pid}:{cid}']},
        explanation='Fresh IDs are linked to prior evidence. Connected predecessors are repeated to bind new follow-ups. '
                    'Pending or ambiguous identities require observation; they forbid fresh sequence submission. '
                    'Case counts are not provider-call counts or quota headroom.')


def campaign_configuration(observations):
    by_endpoint = {item['endpoint']: item for item in observations}
    prefs = by_endpoint.get('inference_preferences', {}).get('payload', {}).get('preferences')
    instances = by_endpoint.get('running_instances', {}).get('payload')
    if not isinstance(prefs, dict) or not isinstance(instances, list) or not instances:
        raise CorpusError('Campaign model configuration evidence is missing.')
    models = []
    for item in instances:
        if item.get('readiness') != 'ready':
            continue
        if not all(item.get(k) for k in ('backend', 'model', 'capability')):
            raise CorpusError('Ready model configuration is incomplete.')
        models.append({k: item.get(k) for k in ('backend', 'model', 'capability', 'provider_capabilities')})
    if not models:
        raise CorpusError('Campaign has no recorded ready models.')
    # Preserve instance multiplicity; ports/process IDs and timestamps are volatile.
    return dict(preferences=prefs, models=sorted(models, key=lambda x: json.dumps(x, sort_keys=True)))


def validate_fake_evidence(path, inventory, corpus, seed):
    path = Path(path).resolve()
    result, config = read_json(path), read_json(path.parent / 'run.json')
    if (result.get('mode') != 'fake' or result.get('verdict') != 'passed'
            or config.get('mode') != 'fake' or config.get('source_digest') != inventory['source_digest']
            or (inventory.get('runtime_source_digest') is not None
                and config.get('runtime_source_digest') != inventory['runtime_source_digest'])
            or config.get('corpus') != corpus or config.get('seed') != seed
            or not result.get('owner_tests')
            or len(result['owner_tests']) != 5
            or any(x.get('status') != 'passed' for x in result['owner_tests'].values())
            or result.get('coverage', {}).get('profiles_selected') != result.get('coverage', {}).get('profiles_available')
            or result.get('coverage', {}).get('profiles_completed') != len(config.get('profiles', []))
            or not config.get('profiles')):
        raise CorpusError('Current complete matching fake evidence is required for combined coverage.')
    expected = {(p['id'], c['case_id']) for p in config['profiles'] for c in corpus['cases']}
    observed = [(r['profile']['id'], c['case_id']) for r in result.get('runs', [])[:len(config['profiles'])]
                for c in r['cases'] if not c.get('missing', ['unknown']) and not c.get('findings', ['unknown'])
                and c.get('capture_path') and c.get('state') in SETTLED]
    if len(observed) != len(expected) or set(observed) != expected:
        raise CorpusError('Fake evidence does not cover every required profile/case.')
    return [file_receipt(path), file_receipt(path.parent / 'run.json')]


def combine_evidence(directories, fake_evidence, inventory, *, attestations=()):
    """Compose coverage, not native verdicts. Every attempt and comparison remains visible."""
    from scripts.self_attack_knobs import build_profiles, validate_saved_profile
    directories = [Path(p).resolve() for p in directories]
    if not directories or len(set(directories)) != len(directories):
        raise CorpusError('Provide distinct native evidence windows.')
    first = read_json(directories[0] / 'run.json')
    raw, seed = first['corpus'], first['seed']
    gate = validate_fake_evidence(fake_evidence, inventory, raw, seed)
    catalog = build_profiles(inventory, live=True, seed=seed)
    expected = {(p['id'], c['case_id']) for p in catalog for c in raw['cases']}
    catalog_map = {p['id']: p for p in catalog}
    runtime_identity = runtime_files(inventory)
    configurations, labels, provenance, attempts = [], set(), [], {}
    observation_settings = []
    native_failure, unresolved_diagnostics, unresolved_nonquota = False, False, False
    frames = {}
    for directory in directories:
        config = read_json(directory / 'run.json')
        result = read_json(directory / 'results.json')
        controls = read_json(directory / 'controls.json')
        if (config.get('mode') != 'live' or result.get('mode') != 'live' or config['corpus'] != raw
                or config['seed'] != seed or config['source_digest'] != controls.get('source_digest')
                or runtime_files(controls) != runtime_identity):
            raise CorpusError('Incompatible runtime source, corpus, seed or native mode.')
        attestation_receipts = compatible_runtime_inputs(controls, inventory, attestations)
        # A diagnostic implementation may differ. Its native verdict is preserved;
        # the current exact-source fake gate validates this analysis implementation.
        for profile in config['profiles']:
            rebound = validate_saved_profile(profile, inventory, live=True)
            if profile != rebound or catalog_map.get(profile['id']) != profile:
                raise CorpusError('Incompatible profile ID/settings/request controls.')
        configurations.append(campaign_configuration(read_json(directory / 'live-preflight.json')))
        labels.add(config.get('window_plan', {}).get('campaign_id', 'legacy:' + config['run_id']))
        observation_settings.append({k: v for k, v in config.get('budgets', {}).items()
                                     if k not in {'live_main_budget', 'live_confirmation_budget', 'jobs'}})
        # Every original campaign must have its own matching fake gate, too.
        old_gate_path = Path(result.get('fake_evidence', ''))
        if not old_gate_path.is_file():
            raise CorpusError('Native campaign matching fake gate is missing.')
        validate_fake_evidence(old_gate_path, controls, raw, seed)
        provenance.append(dict(directory=str(directory), native_verdict=result['verdict'],
            source_digest=config['source_digest'], runtime_source_digest=inventory['runtime_source_digest'],
            diagnostic_source_digest=stable_digest({k: v for k, v in controls['source_files'].items()
                                                   if k.startswith(('scripts/', 'tests/'))}),
            receipts=[file_receipt(directory / n) for n in ('run.json', 'results.json', 'controls.json', 'live-preflight.json')],
            fake_gate=[file_receipt(old_gate_path), file_receipt(old_gate_path.parent / 'run.json')],
            source_attestations=attestation_receipts,
            stop=result.get('execution_status'), budgets=result.get('live_budget'),
            dispatch_window=result.get('dispatch_window'),
            completion=read_json(directory / 'completion.json') if (directory / 'completion.json').exists() else None))
        native_failure |= result.get('verdict') == 'failed'
        unresolved_diagnostics |= bool(result.get('confirmation_stop_reason'))
        all_runs = result.get('runs', []) + result.get('confirmation_runs', [])
        native_failure |= any(c.get('findings') for r in all_runs for c in r.get('cases', []))
        # Main scope contributes coverage. Diagnostic attempts cannot silently
        # replace main cells, but their failures/unconfirmed status stay sticky.
        for (pid, cid), record in native_cases(directory, config, result).items():
            if (pid, cid) not in expected:
                raise CorpusError('Native case is outside the matching corpus/profile catalog.')
            case = record['case']
            item = dict(evidence_origin=str(directory), response_id=case.get('response_id'),
                        native_state=case['state'], native_missing=case.get('missing', []),
                        native_findings=case.get('findings', []), native_verdict=result['verdict'],
                        manifest=file_receipt(record['manifest']) if record['manifest'] else None,
                        tiers=[], complete=False)
            if case.get('capture_path'):
                path, capture = final_capture(case, directory)
                payload = capture['payload']
                executions = list(pcc_records(payload.get('runtime', {})))
                tiers = sorted({e.get('model') for e in executions if e.get('status') == 'completed'
                                and e.get('model') in {'cloud', 'cloud-pro'}})
                item.update(capture=file_receipt(path), tiers=tiers,
                            quota=quota_evidence(payload), lifecycle=payload.get('lifecycle_state'))
                unresolved_nonquota |= (payload.get('lifecycle_state') == 'failed' and not item['quota'])
                item['complete'] = (case['state'] in SETTLED and not case.get('missing', ['unknown'])
                                    and not case.get('findings', ['unknown']) and len(tiers) == 1 and not item['quota'])
                frame = payload.get('response_frame') or {}
                if frame.get('frame_id') and frame.get('status') in {'frozen', 'completed', 'failed', 'repair_needed', 'blocked'}:
                    key = (case['response_id'], frame['frame_id'])
                    digest = stable_digest(frame)
                    if key in frames and frames[key] != digest:
                        native_failure = True
                        item['cross_window_frame_conflict'] = 'frozen_frame_mutated'
                    frames[key] = digest
                if item['complete']:
                    # Retain just the actual contract used by the existing comparison.
                    graph = payload.get('runtime', {}).get('request_phase_graph', {})
                    obligations = graph.get('intent_obligations') if isinstance(graph, dict) else None
                    # The native oracle permits an absent ledger when prompt_intent
                    # explicitly reports zero material obligations (chat-only work).
                    if (isinstance(graph, dict) and 'intent_obligations' not in graph
                            and (graph.get('prompt_intent') or {}).get('intent_obligation_count') == 0):
                        obligations = []
                    if not isinstance(obligations, list):
                        raise CorpusError('Complete case lacks anchored intent comparison evidence.')
                    item['_comparison_payload'] = {'runtime': {'request_phase_graph': {
                        'intent_obligations': obligations}}}
            attempts.setdefault((pid, cid), []).append(item)
    if (any(c != configurations[0] for c in configurations[1:]) or len(labels) > 1
            or any(s != observation_settings[0] for s in observation_settings[1:])):
        raise CorpusError('Incompatible serving configuration/account campaign labels.')
    comparisons, conflicts, tier_reports = [], [], {}
    for tier in ('cloud', 'cloud-pro'):
        covered = {key for key, values in attempts.items() if any(v['complete'] and v['tiers'] == [tier] for v in values)}
        comparison_gaps = []
        for pid, cid in sorted(covered):
            values = [v for v in attempts[(pid, cid)] if v['complete'] and v['tiers'] == [tier]]
            bases = [v for v in attempts.get(('baseline', cid), []) if v['complete'] and v['tiers'] == [tier]]
            if pid != 'baseline' and not bases:
                comparison_gaps.append(f'{pid}:{cid}')
            pairs = [(values[0], v, 'repeated_attempt') for v in values[1:]]
            if pid != 'baseline':
                pairs += [(b, v, 'cross_profile') for b in bases for v in values]
            for base, candidate, kind in pairs:
                findings = compare_profiles(base['_comparison_payload'], candidate['_comparison_payload'])
                entry = dict(tier=tier, profile_id=pid, case_id=cid, kind=kind,
                    baseline=base['capture'], candidate=candidate['capture'], findings=findings)
                comparisons.append(entry)
                if findings:
                    conflicts.append(entry)
        tier_reports[tier] = dict(completed=len(covered), required=len(expected),
            missing=[f'{p}:{c}' for p, c in sorted(expected - covered)], comparison_gaps=comparison_gaps,
            verdict='failed' if native_failure or any(x['tier'] == tier for x in conflicts) else
                    'passed' if covered == expected and not comparison_gaps and not unresolved_diagnostics
                    and not unresolved_nonquota else 'incomplete')
    for values in attempts.values():
        for item in values:
            item.pop('_comparison_payload', None)
    verdict = ('failed' if native_failure or conflicts else
               'passed' if any(v['verdict'] == 'passed' for v in tier_reports.values()) else 'incomplete')
    return dict(schema_version=1, execution_performed=False, derived_at=utc_now(), verdict=verdict,
        analysis_source_digest=inventory['source_digest'], fresh_fake_gate=gate,
        runtime_source_digest=inventory['runtime_source_digest'], corpus_digest=stable_digest(raw), seed=seed,
        configuration=configurations[0], campaign_labels=sorted(labels), provenance=provenance,
        tiers=tier_reports, comparisons=comparisons, conflicts=conflicts,
        attempts={f'{p}:{c}': values for (p, c), values in sorted(attempts.items())},
        native_failures_preserved=native_failure, unresolved_diagnostics=unresolved_diagnostics,
        unresolved_nonquota_terminal_failures=unresolved_nonquota,
        note='Derived tier-specific coverage preserves native verdicts and all attempts. Historical incomplete '
             'quota attempts remain visible even when new compatible main observations cover a cell. '
             'Unknown/mixed serving tiers cannot complete coverage. Case counts are not provider-call counts.')


def write_derived(result, output, evidence_roots):
    output = Path(output).resolve()
    if any(output == Path(p).resolve() or output.is_relative_to(Path(p).resolve()) for p in evidence_roots):
        raise CorpusError('Derived output must be outside all native evidence directories.')
    output.mkdir(parents=True, exist_ok=True)
    with manifest_lock(output / 'results.json'):
        if (output / 'results.json').exists():
            raise CorpusError('Derived output already exists; choose a new output to preserve it.')
        atomic_write_json(output / 'results.json', result)
        lines = ['# Bounded conformance evidence', '', 'Offline derived report; no requests executed.', '']
        if 'missing_cells' in result:
            lines += [f"Missing cells: {result['missing_cells']}. Fresh connected cases: {result['fresh_case_count']}.",
                      f"Repeated predecessors: {', '.join(result['repeated_predecessors']) or 'none'}.",
                      f"Fresh attempt allowed: {result['fresh_attempt_allowed']}. Existing work to observe: {len(result['observe_existing'])}.", '']
            lines += [f"- `{p}`: {', '.join(ids)}" for p, ids in result['selection'].items()]
        elif 'tiers' in result:
            lines += [f"Derived verdict: **{result['verdict'].upper()}**.", '']
            lines += [f"- {tier}: {v['completed']}/{v['required']} complete; {v['verdict'].upper()}; "
                      f"comparison gaps {len(v['comparison_gaps'])}." for tier, v in result['tiers'].items()]
            lines += ['', f"Comparisons executed: {len(result['comparisons'])}. Conflicts: {len(result['conflicts'])}.",
                      'All native attempts, failures, budgets, source identities and file hashes are in results.json.']
        else:
            lines += [f"Selected cases: {result['case_count']}. Explicit windows: {len(result['windows'])}."]
        lines += ['', result.get('explanation', result.get('note', '')), '']
        (output / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
