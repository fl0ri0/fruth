"""Offline scheduling/evidence tests. All transports, manifests and roots are synthetic."""
from copy import deepcopy
import json
from pathlib import Path
import time

import pytest

import scripts.fruth_self_attack as command
from scripts.run_graph_rebase_shadow_corpus import CorpusError, HttpResult, atomic_write_json, stable_digest
from scripts.self_attack_knobs import build_profiles, discover_knobs, select_profiles
from scripts.self_attack_windows import (
    DispatchWindow, campaign_configuration, combine_evidence, final_capture,
    plan_windows, local_full_plan, preview_recovery, quota_evidence, select_cases, sequence_corpora, write_derived,
)
from tests.test_self_attack import truth, sample_corpus, live_budget_command, observed_budget_cases

ROOT = Path(__file__).resolve().parents[1]
BASELINE = dict(id='baseline', settings={}, request={}, environment={})
LIMIT = 'You have reached the usage limit for this model. Please try again later.'


def native_truth(identity, *, quota=False, fallback=False):
    payload = truth()
    payload.update(id=identity, status='failed' if quota else 'completed',
                   lifecycle_state='failed' if quota else 'completed',
                   message_id='message-' + identity, output_text='The lighthouse guides ships.')
    payload['response_frame'].update(status='failed' if quota else 'frozen')
    if quota:
        payload['error'] = LIMIT
        payload['runtime']['provider_failover'] = {'attempts': [dict(
            backend='apple_pcc', model='auto', reason='provider_usage_limit', error_message=LIMIT)]}
        payload['runtime'].pop('graph_closure_review')
    else:
        payload['runtime']['pcc_execution'] = dict(status='completed', model='cloud',
            attempts=[dict(model='cloud-pro', status='shortcut_error',
                          stderr='You must be signed in to an iCloud+ account.')],
            fallback_reason='pro_access_required' if fallback else None)
    return payload


class OfflineTransport:
    def __init__(self, *, quota=False, fallback=False, native_error=None):
        self.quota, self.fallback, self.native_error = quota, fallback, native_error
        self.responses, self.posts, self.gets = {}, [], []

    def get(self, path, *, timeout):
        self.gets.append(path)
        if path == '/api/running_instances':
            return HttpResult(200, [dict(readiness='ready', backend='apple_pcc', model='auto',
                capability='chat', provider_capabilities=['chat'])])
        if path == '/api/inference_preferences':
            return HttpResult(200, {'preferences': {'primary_target': {'backend': 'apple_pcc', 'model': 'auto'}}})
        if '/api/responses/' in path:
            identity = path.split('/api/responses/', 1)[1].split('?')[0]
            return HttpResult(200, self.responses[identity]) if identity in self.responses else HttpResult(404, {})
        return HttpResult(200, {})

    def post(self, path, payload, *, timeout):
        assert path == '/api/responses'
        self.posts.append(deepcopy(payload))
        identity = payload['response_id']
        value = native_truth(identity, quota=self.quota, fallback=self.fallback)
        if self.native_error:
            value.update(error=self.native_error, lifecycle_state='failed', status='failed')
        self.responses[identity] = value
        return HttpResult(200, value)


def run_native_group(tmp_path, monkeypatch, transport, raw=None, *, window=None, key='sequence'):
    raw = raw or sample_corpus()
    window = window or DispatchWindow(tmp_path, cap=10, allocation={'test': True})
    assert window.admit_sequence(key, [c['case_id'] for c in raw['cases']], kind='main') is None
    monkeypatch.setattr(command, 'JsonHttpClient', lambda *a: transport)
    result = command.run_profile(raw, BASELINE, tmp_path / key, mode='live', base_url='offline', cycles=30,
        namespace='window', dispatch_output=tmp_path, sequence_key=key)
    return result, window


def test_explicit_quota_at_post_stops_followups_and_all_diagnostics(tmp_path, monkeypatch):
    transport = OfflineTransport(quota=True)
    result, window = run_native_group(tmp_path, monkeypatch, transport)
    assert len(transport.posts) == 1
    assert window.read()['stop']['provider'] == 'apple_pcc'
    assert window.read()['stop']['tier'] == 'unknown'  # auto is not serving-tier evidence
    assert window.read()['stop']['response_id'] == transport.posts[0]['response_id']
    assert result['cases'][0]['missing']
    assert any('?view=status' in path for path in transport.gets)
    budget = command.LiveBudget(tmp_path, main_seconds=50, confirmation_seconds=10, attempt_cap=4)
    budget.dispatch_window = window
    budget.begin_confirmation()
    command.isolated_profile(sample_corpus(), BASELINE, tmp_path / 'diagnostic', mode='live',
        base_url='offline', cycles=2, namespace='replay', live_budget=budget)
    assert len(transport.posts) == 1
    assert len(window.read()['sequences']) == 1
    args = type('Args', (), dict(minimize_budget=24))()
    summary = dict(runs=[], regressions=[])
    command.confirm_failures(args, sample_corpus(), [BASELINE], tmp_path, 'run', summary, {}, budget)
    assert summary['confirmation_stop_reason'] == 'provider_usage_limit'
    assert budget.state['attempts'] == []


@pytest.mark.parametrize('message', ['Timeout', 'HTTP 429', 'iCloud+ account required',
    'Cloud Pro model not available', 'Connection reset', 'Something failed'])
def test_nonquota_diagnostics_never_latch(message, tmp_path):
    window = DispatchWindow(tmp_path, cap=10, allocation={})
    window.detect_quota({'error': message, 'runtime': {'provider_failover': {'attempts': [
        dict(reason='provider_error', error_message=message)]}}})
    assert window.stop_reason() is None
    assert quota_evidence({'output_text': LIMIT, 'runtime': {'request_phase_graph': {'prompt': LIMIT}}}) is None


def test_structured_pro_usage_limit_retains_affected_tier_even_when_cloud_served():
    value = native_truth('served-cloud')
    value['runtime']['pcc_execution']['fallback_reason'] = 'pro_usage_limit'
    evidence = quota_evidence(value)
    assert evidence['provider'] == 'apple_pcc' and evidence['tier'] == 'cloud-pro'
    assert evidence['response_id'] == 'served-cloud'


def test_ordinary_pro_access_rejection_and_cloud_fallback_dispatch_followup(tmp_path, monkeypatch):
    transport = OfflineTransport(fallback=True)
    result, window = run_native_group(tmp_path, monkeypatch, transport)
    assert len(transport.posts) == 2
    assert window.stop_reason() is None
    assert result['runner_status'] == 0
    assert not any(c['missing'] for c in result['cases'])
    assert len(window.read()['dispatches']) == 2


def test_quota_on_first_status_read_stops_before_another_post(tmp_path, monkeypatch):
    class DelayedQuota(OfflineTransport):
        def post(self, path, payload, *, timeout):
            self.posts.append(deepcopy(payload))
            self.responses[payload['response_id']] = native_truth(payload['response_id'], quota=True)
            return HttpResult(200, {'id': payload['response_id'], 'status': 'in_progress'})
    transport = DelayedQuota()
    _, window = run_native_group(tmp_path, monkeypatch, transport)
    assert len(transport.posts) == 1
    assert window.read()['stop']['checkpoint'].endswith('view=status')


def test_windows_preserve_stable_ids_and_dependency_boundaries():
    raw = json.loads((ROOT / 'config/self_attack_corpus.json').read_text())
    profiles = build_profiles(discover_knobs(ROOT), live=True, seed=0)
    chosen = select_profiles(profiles, [profiles[-1]['id'], profiles[0]['id']])
    assert chosen == [profiles[0], profiles[-1]]
    selection = select_cases(raw, profiles)
    windows = plan_windows(raw, profiles, selection, 100)
    assert [sum(map(len, w.values())) for w in windows] == [100, 70]
    windows = plan_windows(raw, profiles[:1], select_cases(raw, profiles[:1]), 3)
    assert [sum(map(len, w.values())) for w in windows] == [2] * 5
    assert select_cases(raw, profiles[:1], ['evidence-follow']) == {'baseline': ['evidence-root', 'evidence-follow']}
    assert select_cases(raw, profiles[:1], ['attention-root']) == {'baseline': ['attention-root', 'attention-follow']}
    with pytest.raises(CorpusError, match='cannot fit'):
        plan_windows(raw, profiles, selection, 1)
    with pytest.raises(CorpusError, match='Unknown profile'):
        select_profiles(profiles, ['made-up'])
    with pytest.raises(CorpusError, match='Unknown case'):
        select_cases(raw, profiles, ['made-up'])


def test_case_cap_counts_main_diagnostics_and_ambiguous_reservations_once(tmp_path):
    window = DispatchWindow(tmp_path, cap=5, allocation={'number': 1})
    assert window.admit_sequence('main', ['root', 'follow'], kind='main') is None
    for cid in ['root', 'follow']:
        assert window.reserve_dispatch('main', {'case_id': cid, 'response_id': cid}) is None
    assert window.admit_sequence('confirmation', ['root', 'follow'], kind='confirmation') is None
    assert window.reserve_dispatch('confirmation', {'case_id': 'root', 'response_id': 'root-new'}) is None
    assert window.admit_sequence('reference', ['root', 'follow'], kind='confirmation') == 'case_cap_stop'
    assert len(window.read()['dispatches']) == 3
    assert sum(len(s['case_ids']) for s in window.read()['sequences'].values()) == 4
    restarted = DispatchWindow(tmp_path, cap=5, allocation={'number': 1})
    assert restarted.reserve_dispatch('main', {'case_id': 'root', 'response_id': 'root'}) == 'dispatch_identity_already_reserved'
    with pytest.raises(CorpusError, match='cannot replenish'):
        DispatchWindow(tmp_path, cap=6, allocation={'number': 1})


def local_configuration(backend='ollama'):
    model = 'system' if backend == 'apple_fm' else 'fixture'
    return dict(models=[dict(backend=backend, model=model)],
                preferences=dict(primary_target=dict(backend=backend, model=model)))


def test_full_local_reserves_all_170_cases_and_only_existing_diagnostic_allowance(tmp_path):
    raw = json.loads((ROOT / 'config/self_attack_corpus.json').read_text())
    profiles = build_profiles(discover_knobs(ROOT), live=True, seed=0)
    plan = local_full_plan(raw, profiles, attempt_cap=4, campaign_id='local-fixture')
    assert plan['main_cases'] == 170 and plan['diagnostic_cases'] == 40
    assert len(plan['windows']) == 1 and plan['case_cap'] == 210
    window = DispatchWindow(tmp_path, cap=210, allocation=plan)
    with pytest.raises(CorpusError, match='only ready'):
        window.admit_sequence('unobserved', ['root'], kind='main')
    window.bind_configuration(local_configuration())
    for pid, cases in plan['requested'].items():
        assert window.admit_sequence(pid, cases, kind='main') is None
        for cid in cases:
            assert window.reserve_dispatch(pid, dict(case_id=cid, response_id=pid + cid)) is None
    assert len(window.read()['dispatches']) == 170
    for i in range(4):
        assert window.admit_sequence(f'extra-{i}', plan['requested']['baseline'], kind='confirmation') is None
    resumed = DispatchWindow(tmp_path, cap=210, allocation=plan)
    assert resumed.admit_sequence('one-too-many', ['root'], kind='confirmation') == 'case_cap_stop'
    assert len(resumed.read()['sequences']) == 21
    with pytest.raises(CorpusError, match='cannot replenish'):
        DispatchWindow(tmp_path, cap=220, allocation=local_full_plan(raw, profiles, attempt_cap=5, campaign_id='local-fixture'))
    with pytest.raises(CorpusError, match='between 1 and 100'):
        DispatchWindow(tmp_path / 'pcc', cap=170, allocation={})


@pytest.mark.parametrize('configuration', [None, {},
    dict(models=[dict(backend='apple_pcc')], preferences={}),
    dict(models=[dict(backend='ollama'), dict(backend='apple_pcc')], preferences={}),
    dict(models=[dict(backend='apple_fm'), dict(backend='apple_pcc')], preferences={}),
    dict(models=[dict(backend='mlx')], preferences={'fallback_target': dict(backend='apple_pcc')}),
    dict(models=[dict(backend='mlx')], preferences={'embedding_helper': dict(backend='external')}),
    dict(models=[dict(backend='unknown')], preferences={})])
def test_full_local_rejects_nonlocal_or_missing_configuration_before_dispatch(tmp_path, monkeypatch, configuration):
    cmd, args, _ = live_budget_command(tmp_path, monkeypatch)
    transport = OfflineTransport()
    monkeypatch.setattr(cmd, 'JsonHttpClient', lambda *a: transport)
    monkeypatch.setattr(cmd, 'campaign_configuration', lambda observations: configuration)
    monkeypatch.setattr(cmd, 'isolated_profile', lambda *a, **kw: pytest.fail('Rejected local configuration started worker'))
    with pytest.raises(CorpusError, match='Full local sweeps'):
        cmd.main([*args, '--local-full-sweep'])
    assert not transport.posts
    assert not json.loads((tmp_path / 'live/dispatch-window.json').read_text())['dispatches']


@pytest.mark.parametrize('backend', ['ollama', 'apple_fm'])
def test_full_local_main_selects_all_cases_and_preserves_budgets(tmp_path, monkeypatch, backend):
    raw = json.loads((ROOT / 'config/self_attack_corpus.json').read_text())
    cmd, args, _ = live_budget_command(tmp_path, monkeypatch, corpus=raw)
    profiles = build_profiles(discover_knobs(ROOT), live=True, seed=0)
    monkeypatch.setattr(cmd, 'build_profiles', lambda *a, **kw: profiles)
    monkeypatch.setattr(cmd, 'campaign_configuration', lambda observations: local_configuration(backend))
    monkeypatch.setattr(cmd, 'isolated_profile', observed_budget_cases)
    assert cmd.main([*args, '--local-full-sweep']) == 0
    result = json.loads((tmp_path / 'live/results.json').read_text())
    assert result['coverage']['window']['selected'] == result['coverage']['window']['completed'] == 170
    assert result['coverage']['window']['remaining'] == 0
    assert result['coverage']['window']['case_cap'] == 210
    assert result['execution_status'] == 'full_complete'
    assert result['live_budget']['limits']['main_seconds'] == 3600
    assert result['live_budget']['limits']['attempt_cap'] == 4


def test_full_local_preview_is_offline_and_cannot_mix_selectors(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(command, 'JsonHttpClient', lambda *a: pytest.fail('Preview contacted runtime'))
    assert command.main(['--preview-window', '--local-full-sweep']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['case_count'] == 170 and len(result['windows']) == 1
    assert result['case_cap'] == 210 and not result['execution_performed']
    for extra in (['--case-cap', '170'], ['--window-number', '2'], ['--profile-limit', '1'],
                  ['--case-id', 'evidence-root'], ['--live-high-risk']):
        with pytest.raises(SystemExit):
            command.main(['--preview-window', '--local-full-sweep', *extra])


def test_reservation_crash_before_manifest_write_is_get_only(tmp_path, monkeypatch):
    transport = OfflineTransport()
    raw = sample_corpus()
    window = DispatchWindow(tmp_path, cap=2, allocation={})
    window.admit_sequence('sequence', ['root', 'follow'], kind='main')
    output = tmp_path / 'sequence'
    output.mkdir()
    corpus = command.materialize_corpus(raw, 'window', output / 'corpus.json')
    manifest = command.build_manifest(corpus, output / 'manifest.json')
    atomic_write_json(output / 'manifest.json', manifest)
    window.reserve_dispatch('sequence', manifest['cases'][0])
    before = window.read()
    result, _ = run_native_group(tmp_path, monkeypatch, transport, window=window)
    assert not transport.posts
    saved = json.loads((output / 'manifest.json').read_text())
    assert saved['cases'][0]['state'] == 'dispatch_unknown'
    assert window.read()['dispatches'] == before['dispatches']
    assert result['runner_status'] == 2


def test_expired_sequence_and_shared_budgets_never_renew_on_resume(tmp_path, monkeypatch):
    window = DispatchWindow(tmp_path, cap=2, allocation={})
    budget = command.LiveBudget(tmp_path, main_seconds=1, confirmation_seconds=1, attempt_cap=1)
    budget.dispatch_window = window
    budget.state['main_deadline'] = time.time() - 1
    budget.state['whole_deadline'] = time.time() - 1
    budget.save()
    resumed = command.LiveBudget(tmp_path, main_seconds=1, confirmation_seconds=1, attempt_cap=1)
    resumed.dispatch_window = DispatchWindow(tmp_path, cap=2, allocation={})
    monkeypatch.setattr(command.subprocess, 'run', lambda *a, **kw: pytest.fail('Expired sequence started worker'))
    result = command.isolated_profile(sample_corpus(), BASELINE, tmp_path / 'main', mode='live',
        base_url='offline', cycles=2, namespace='expired', live_budget=resumed)
    assert result['runner_status'] == 2
    assert resumed.remaining() == 0
    assert resumed.state['main_deadline'] == budget.state['main_deadline']


@pytest.mark.parametrize('name', ['live-budget.json', 'dispatch-window.json'])
def test_lost_budget_or_dispatch_ledger_fails_closed_instead_of_renewing(tmp_path, monkeypatch, name):
    cmd, args, _ = live_budget_command(tmp_path, monkeypatch)
    monkeypatch.setattr(cmd, 'isolated_profile', observed_budget_cases)
    assert cmd.main(args) == 0
    root = tmp_path / 'live'
    (root / 'results.json').unlink()
    (root / name).unlink()
    monkeypatch.setattr(cmd, 'isolated_profile', lambda *a, **kw: pytest.fail('Lost counters dispatched'))
    with pytest.raises(CorpusError, match='replacement limits'):
        cmd.main(args)
    assert not (root / name).exists()


def test_lost_sequence_budget_cannot_be_recreated(tmp_path, monkeypatch):
    atomic_write_json(tmp_path / 'manifest.json', {'cases': []})
    monkeypatch.setattr(command.subprocess, 'run', lambda *a, **kw: pytest.fail('Lost sequence budget started worker'))
    with pytest.raises(CorpusError, match='cannot be renewed'):
        command.isolated_group(sample_corpus(), BASELINE, tmp_path, mode='live', base_url='offline',
            cycles=2, namespace='same', dispatch_output=tmp_path, sequence_key='s')


def synthetic_campaign(tmp_path, *, name='old', incomplete=False, tier='cloud', inventory=None, raw=None):
    inventory = inventory or discover_knobs(ROOT)
    profiles = build_profiles(inventory, live=True, seed=0)
    raw = raw or sample_corpus()
    root = tmp_path / name
    root.mkdir()
    gate = tmp_path / ('fake-' + name)
    gate.mkdir()
    fake_profiles = build_profiles(inventory, seed=0)
    fake_config = dict(mode='fake', source_digest=inventory['source_digest'],
        runtime_source_digest=inventory['runtime_source_digest'], corpus=raw, seed=0, profiles=fake_profiles)
    atomic_write_json(gate / 'run.json', fake_config)
    fake = dict(mode='fake', verdict='passed', owner_tests={k: {'status': 'passed'} for k, _ in command.PRIORITIES},
        coverage=dict(profiles_selected=len(fake_profiles), profiles_available=len(fake_profiles), profiles_completed=len(fake_profiles)),
        runs=[dict(profile=p, cases=[dict(case_id=c['case_id'], state='settled_terminal', missing=[], findings=[],
                                       capture_path='synthetic-gate') for c in raw['cases']]) for p in fake_profiles])
    atomic_write_json(gate / 'results.json', fake)
    config = dict(mode='live', run_id=name, source_digest=inventory['source_digest'], corpus=raw,
        profiles=profiles, seed=0, budgets={}, window_plan={'campaign_id': 'same-account'})
    atomic_write_json(root / 'run.json', config)
    atomic_write_json(root / 'controls.json', inventory)
    client = OfflineTransport()
    preflight = [dict(endpoint=e, status=200, payload=client.get('/api/' + e, timeout=1).payload)
                 for e in ['running_instances', 'inference_preferences']]
    atomic_write_json(root / 'live-preflight.json', preflight)
    results = dict(mode='live', verdict='incomplete' if incomplete else 'passed', fake_evidence=str(gate / 'results.json'), runs=[])
    for profile in profiles:
        cases, entries = [], []
        for c in raw['cases']:
            identity = f'{name}-{profile["id"]}-{c["case_id"]}'
            quota = incomplete and profile == profiles[-1] and c['case_id'] == 'follow'
            payload = native_truth(identity, quota=quota)
            if not quota:
                payload['runtime']['pcc_execution']['model'] = tier
            folder = root / profile['id'] / 'sequence-1/captures' / identity
            folder.mkdir(parents=True)
            atomic_write_json(folder / 'settled.json', dict(payload=payload, source='settled', observed_ns=1))
            case = dict(case_id=c['case_id'], response_id=identity, state='settled_terminal', capture_path=str(folder),
                        missing=['runtime.graph_closure_review'] if quota else [], findings=[])
            cases.append(case)
            entries.append(dict(c, response_id=identity, state='settled_terminal', submitting_at='2026-01-01T00:00:00Z'))
        atomic_write_json(root / profile['id'] / 'sequence-1/manifest.json', {'cases': entries})
        results['runs'].append(dict(profile=profile, cases=cases))
    atomic_write_json(root / 'results.json', results)
    return root, gate / 'results.json', inventory


def test_preview_dependency_scope_and_prior_identity_links_without_mutation(tmp_path):
    root, _, _ = synthetic_campaign(tmp_path, incomplete=True)
    before = (root / 'results.json').read_bytes()
    preview = preview_recovery(root)
    assert preview['missing_cells'] == 1 and preview['fresh_case_count'] == 2
    assert preview['repeated_predecessors'] == ['750ce3471f8c:root']
    assert preview['fresh_attempt_allowed'] and not preview['observe_existing']
    assert preview['prior_evidence']['750ce3471f8c:follow']['quota']['reason'] == 'provider_usage_limit'
    assert (root / 'results.json').read_bytes() == before


def test_exact_pcc_missing_scope_is_43_cells_and_44_fresh_cases(tmp_path):
    raw = json.loads((ROOT / 'config/self_attack_corpus.json').read_text())
    root, _, _ = synthetic_campaign(tmp_path, raw=raw)
    result = json.loads((root / 'results.json').read_text())
    suffix = {'a8cdaeeec572', '65140ef35b27', '83d390a8764c', '750ce3471f8c'}
    for run in result['runs']:
        pid = run['profile']['id']
        manifest_path = root / pid / 'sequence-1/manifest.json'
        manifest = json.loads(manifest_path.read_text())
        for case, entry in zip(run['cases'], manifest['cases']):
            missing = pid in suffix or (pid == '5f35191afc15' and case['case_id'] in
                {'evidence-follow', 'attention-root', 'attention-follow'})
            if not missing:
                continue
            case['missing'] = ['runtime.graph_closure_review']
            if case['case_id'].endswith('follow') and not (pid == '5f35191afc15' and case['case_id'] == 'evidence-follow'):
                case.update(state='dependency_blocked')
                entry.update(state='dependency_blocked')
                entry.pop('submitting_at')
                case.pop('capture_path')
            else:
                path, data = final_capture(case, root)
                data['payload'] = native_truth(case['response_id'], quota=True)
                atomic_write_json(path, data)
        atomic_write_json(manifest_path, manifest)
    result.update(verdict='incomplete')
    atomic_write_json(root / 'results.json', result)
    preview = preview_recovery(root)
    assert preview['missing_cells'] == 43 and preview['fresh_case_count'] == 44
    assert preview['missing']['5f35191afc15'] == ['evidence-follow', 'attention-root', 'attention-follow']
    assert all(len(preview['missing'][pid]) == 10 for pid in suffix)
    assert preview['repeated_predecessors'] == ['5f35191afc15:evidence-root']
    assert sum(bool(v.get('quota')) for v in preview['prior_evidence'].values()) == 22
    assert sum(v['state'] == 'dependency_blocked' for v in preview['prior_evidence'].values()) == 21


def test_reservations_are_atomic_across_dispatch_threads(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    window = DispatchWindow(tmp_path, cap=100, allocation={})
    window.admit_sequence('s', ['root', 'follow'], kind='main')
    def reserve(_):
        return window.reserve_dispatch('s', {'case_id': 'root', 'response_id': 'one'})
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(reserve, range(8)))
    assert results.count(None) == 1
    assert results.count('dispatch_identity_already_reserved') == 7
    assert len(window.read()['dispatches']) == 1


def test_dependency_boundary_stops_worker_before_sequence_that_cannot_fit(tmp_path, monkeypatch):
    raw = sample_corpus()
    raw['cases'] += [dict(c, case_id='next-' + c['case_id'], conversation_key='next',
        **({'depends_on': ['next-root']} if c.get('depends_on') else {})) for c in deepcopy(raw['cases'])]
    budget = command.LiveBudget(tmp_path, main_seconds=100, confirmation_seconds=100, attempt_cap=4)
    budget.dispatch_window = DispatchWindow(tmp_path, cap=3, allocation={})
    executions = []
    def execute(corpus, profile, output, **kwargs):
        executions.append([c['case_id'] for c in corpus['cases']])
        for c in corpus['cases']:
            budget.dispatch_window.reserve_dispatch(kwargs['sequence_key'],
                dict(case_id=c['case_id'], response_id=c['case_id']))
        return observed_budget_cases(corpus, profile, output)
    monkeypatch.setattr(command, 'isolated_group', execute)
    result = command.isolated_profile(raw, BASELINE, tmp_path / 'main', mode='live',
        base_url='offline', cycles=2, namespace='bounded', live_budget=budget)
    assert executions == [['root', 'follow']]
    assert result['runner_status'] == 2
    assert budget.dispatch_window.stop_reason() == 'case_cap_stop'
    assert len(budget.dispatch_window.read()['dispatches']) == 2


def test_pending_and_ambiguous_members_forbid_fresh_recovery(tmp_path):
    root, _, _ = synthetic_campaign(tmp_path, incomplete=True)
    config = json.loads((root / 'run.json').read_text())
    pid = config['profiles'][-1]['id']
    path = root / pid / 'sequence-1/manifest.json'
    manifest = json.loads(path.read_text())
    manifest['cases'][1]['state'] = 'dispatch_unknown'
    atomic_write_json(path, manifest)
    result = json.loads((root / 'results.json').read_text())
    case = result['runs'][-1]['cases'][1]
    case.update(state='dispatch_unknown')
    case.pop('capture_path')
    atomic_write_json(root / 'results.json', result)
    preview = preview_recovery(root)
    assert not preview['fresh_attempt_allowed']
    assert preview['observe_existing'][0]['response_id'] == case['response_id']


def test_compatible_aggregation_runs_comparisons_and_preserves_quota_history(tmp_path):
    old, gate, inventory = synthetic_campaign(tmp_path, incomplete=True)
    new, _, _ = synthetic_campaign(tmp_path, name='new', inventory=inventory)
    originals = [(p, p.read_bytes()) for d in [old, new] for p in [d / 'results.json', d / 'run.json']]
    result = combine_evidence([old, new], gate, inventory)
    assert result['verdict'] == 'passed'
    assert result['tiers']['cloud']['completed'] == 34
    assert result['tiers']['cloud-pro']['verdict'] == 'incomplete'
    assert len(result['comparisons']) >= 32
    assert any(a['quota'] for a in result['attempts']['750ce3471f8c:follow'])
    assert all(p.read_bytes() == data for p, data in originals)


def test_partial_coverage_and_different_tiers_never_form_full_pass(tmp_path):
    old, gate, inventory = synthetic_campaign(tmp_path, incomplete=True)
    result = combine_evidence([old], gate, inventory)
    assert result['verdict'] == 'incomplete'
    pro, _, _ = synthetic_campaign(tmp_path, name='pro', inventory=inventory, tier='cloud-pro', incomplete=True)
    result = combine_evidence([old, pro], gate, inventory)
    assert result['verdict'] == 'incomplete'
    assert result['tiers']['cloud']['completed'] == result['tiers']['cloud-pro']['completed'] == 33


def test_chat_only_native_intent_compares_absent_zero_and_empty_ledgers(tmp_path):
    root, gate, inventory = synthetic_campaign(tmp_path)
    result = json.loads((root / 'results.json').read_text())
    for run in result['runs']:
        path, data = final_capture(run['cases'][0], root)
        graph = data['payload']['runtime']['request_phase_graph']
        graph['prompt_intent'] = {'intent_obligation_count': 0}
        if run['profile']['id'] == 'baseline':
            graph.pop('intent_obligations')
        else:
            graph['intent_obligations'] = []
        atomic_write_json(path, data)
    derived = combine_evidence([root], gate, inventory)
    assert derived['verdict'] == 'passed'
    assert len(derived['comparisons']) == 32 and not derived['conflicts']
    # A material obligation in one profile still conflicts with chat-only intent.
    path, data = final_capture(result['runs'][-1]['cases'][0], root)
    data['payload']['runtime']['request_phase_graph']['intent_obligations'] = [{'required': True}]
    atomic_write_json(path, data)
    assert combine_evidence([root], gate, inventory)['verdict'] == 'failed'


@pytest.mark.parametrize('count', [None, 1])
def test_absent_intent_ledger_without_explicit_zero_fails_closed(tmp_path, count):
    root, gate, inventory = synthetic_campaign(tmp_path)
    case = json.loads((root / 'results.json').read_text())['runs'][0]['cases'][0]
    path, data = final_capture(case, root)
    graph = data['payload']['runtime']['request_phase_graph']
    graph.pop('intent_obligations')
    graph['prompt_intent'] = {'intent_obligation_count': count}
    atomic_write_json(path, data)
    with pytest.raises(CorpusError, match='intent comparison evidence'):
        combine_evidence([root], gate, inventory)


@pytest.mark.parametrize('mutation', ['runtime', 'missing_runtime', 'seed', 'incomplete'])
def test_live_requires_current_complete_fake_gate_before_preflight(tmp_path, monkeypatch, mutation):
    cmd, args, _ = live_budget_command(tmp_path, monkeypatch)
    gate = tmp_path / 'proof'
    config = json.loads((gate / 'run.json').read_text())
    result = json.loads((gate / 'results.json').read_text())
    if mutation == 'runtime':
        config['runtime_source_digest'] = 'different-runtime-inputs'
    elif mutation == 'missing_runtime':
        config.pop('runtime_source_digest')
    elif mutation == 'seed':
        config['seed'] = 123
    else:
        result['coverage']['profiles_completed'] = 0
    atomic_write_json(gate / 'run.json', config)
    atomic_write_json(gate / 'results.json', result)
    monkeypatch.setattr(cmd, 'JsonHttpClient', lambda *a, **kw: pytest.fail('Gate failure reached live preflight'))
    with pytest.raises(CorpusError, match='complete matching fake evidence'):
        cmd.main(args)


@pytest.mark.parametrize('mutation', ['seed', 'source', 'corpus', 'profile', 'preferences', 'account', 'budgets', 'gate'])
def test_incompatible_aggregation_fails_closed(tmp_path, mutation):
    old, gate, inventory = synthetic_campaign(tmp_path)
    new, _, _ = synthetic_campaign(tmp_path, name='new', inventory=inventory)
    config = json.loads((new / 'run.json').read_text())
    if mutation == 'seed':
        config['seed'] = 99
    elif mutation == 'source':
        config['source_digest'] = 'unknown'
    elif mutation == 'corpus':
        config['corpus']['cases'][0]['prompt'] = 'Different intent'
    elif mutation == 'profile':
        config['profiles'][0]['request'] = {'hidden': True}
    elif mutation == 'account':
        config['window_plan']['campaign_id'] = 'new-account'
    elif mutation == 'budgets':
        config['budgets']['live_sequence_timeout'] = 999
    elif mutation == 'preferences':
        p = new / 'live-preflight.json'
        data = json.loads(p.read_text())
        data[1]['payload']['preferences']['primary_target']['model'] = 'cloud-pro'
        atomic_write_json(p, data)
    elif mutation == 'gate':
        p = gate
        data = json.loads(p.read_text())
        data['coverage']['profiles_completed'] = 1
        atomic_write_json(p, data)
    atomic_write_json(new / 'run.json', config)
    with pytest.raises(CorpusError):
        combine_evidence([old, new], gate, inventory)


def test_repeated_success_conflict_and_native_failure_are_not_cherry_picked(tmp_path):
    old, gate, inventory = synthetic_campaign(tmp_path)
    new, _, _ = synthetic_campaign(tmp_path, name='new', inventory=inventory)
    case = json.loads((new / 'results.json').read_text())['runs'][-1]['cases'][0]
    path, data = final_capture(case, new)
    data['payload']['runtime']['request_phase_graph']['intent_obligations'][0]['required'] = False
    atomic_write_json(path, data)
    result = combine_evidence([old, new], gate, inventory)
    assert result['verdict'] == 'failed' and result['conflicts']
    data['payload']['runtime']['request_phase_graph']['intent_obligations'][0]['required'] = True
    atomic_write_json(path, data)
    summary = json.loads((old / 'results.json').read_text())
    summary.update(verdict='failed')
    summary['runs'][0]['cases'][0]['findings'] = [{'code': 'frozen_frame_mutated'}]
    atomic_write_json(old / 'results.json', summary)
    result = combine_evidence([old, new], gate, inventory)
    assert result['verdict'] == 'failed' and result['native_failures_preserved']


def test_missing_baseline_comparison_prevents_full_pass(tmp_path):
    root, gate, inventory = synthetic_campaign(tmp_path)
    result = json.loads((root / 'results.json').read_text())
    result['runs'][0]['cases'][0]['missing'] = ['settled_full_truth']
    result.update(verdict='incomplete')
    atomic_write_json(root / 'results.json', result)
    derived = combine_evidence([root], gate, inventory)
    assert derived['tiers']['cloud']['comparison_gaps']
    assert derived['verdict'] == 'incomplete'


def test_derived_output_never_overwrites_native_or_earlier_derived_evidence(tmp_path):
    native = tmp_path / 'native'
    native.mkdir()
    with pytest.raises(CorpusError, match='outside'):
        write_derived({}, native / 'derived', [native])
    output = tmp_path / 'derived'
    write_derived({'case_count': 2, 'windows': []}, output, [native])
    with pytest.raises(CorpusError, match='already exists'):
        write_derived({}, output, [native])


def test_main_window_selection_and_remaining_are_honest(tmp_path, monkeypatch):
    raw = json.loads((ROOT / 'config/self_attack_corpus.json').read_text())
    cmd, args, _ = live_budget_command(tmp_path, monkeypatch, corpus=raw)
    profiles = build_profiles(discover_knobs(ROOT), live=True, seed=0)
    monkeypatch.setattr(cmd, 'build_profiles', lambda *a, **kw: profiles)
    monkeypatch.setattr(cmd, 'isolated_profile', observed_budget_cases)
    assert cmd.main([*args, '--window-number', '2']) == 2
    result = json.loads((tmp_path / 'live/results.json').read_text())
    assert result['coverage']['window']['selected'] == 70
    assert result['coverage']['window']['completed'] == 70
    assert result['coverage']['window']['remaining'] == 100
    assert result['execution_status'] == 'window_complete'
    assert result['scoped_verdicts']['full_live_conformance'] == 'incomplete'


def test_existing_campaign_monitor_reads_quota_cap_and_completion(tmp_path, monkeypatch):
    import scripts.self_attack_monitor as monitor
    config = dict(mode='live', profiles=[], corpus={'cases': []}, case_selection={}, fake_gate={})
    atomic_write_json(tmp_path / 'run.json', config)
    atomic_write_json(tmp_path / 'dispatch-window.json', dict(case_cap=100, sequences={}, dispatches={},
        stop={'reason': 'provider_usage_limit', 'provider': 'apple_pcc', 'tier': 'cloud', 'response_id': 'exact'}))
    atomic_write_json(tmp_path / 'completion.json', {'exit_code': 2})
    monkeypatch.setattr(monitor, 'ROOT', tmp_path)
    output = monitor.render()
    assert 'FINISHED' in output and 'provider_usage_limit' in output
    assert 'quota headroom' in output and 'exact' in output
