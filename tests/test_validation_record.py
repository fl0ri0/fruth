"""Disposable evidence/metadata fixtures; no installs or production-state reads."""
from copy import deepcopy
import json
from pathlib import Path

from packaging.markers import default_environment
import pytest

from scripts import build_release_archive as release
from scripts import validation_record as record
from test_release_archive import _make_release_source


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def package(version='1', requirements=(), python='>=3.11'):
    return {'version': version, 'requires_python': python,
            'requires_dist': list(requirements), 'metadata_sha256': 'a' * 64}


def test_conditional_closure_roles_extras_and_incidental_packages():
    packages = {
        'app': package(requirements=['shared>=1', 'optional[feature]>=1', 'winonly; sys_platform == "win32"']),
        'pytest': package(requirements=['shared>=1', 'testhelper; python_version >= "3.11"']),
        'shared': package(), 'testhelper': package(),
        'optional': package(requirements=['extrahelper; extra == "feature"', 'app>=1']),
        'extrahelper': package(), 'incidental': package(), 'pip': package(),
    }
    env = dict(default_environment(), sys_platform='darwin', python_version='3.11', python_full_version='3.11.17')
    result = record.dependency_closure('app\npytest\nwinroot; sys_platform == "win32"', packages, env)
    names = {p['name']: p for p in result['packages']}
    assert set(names) == {'app', 'pytest', 'shared', 'optional', 'extrahelper', 'testhelper'}
    assert names['shared']['roles'] == ['runtime', 'validation']
    assert names['testhelper']['roles'] == ['validation']
    assert any(not e['active'] and 'winonly' in e['requirement'] for e in result['edges'])
    assert result['roots'][-1]['active'] is False


@pytest.mark.parametrize('change', ['missing', 'version', 'python', 'url'])
def test_invalid_dependency_closure_rejected(change):
    packages = {'app': package(requirements=['child>=2']), 'child': package('2')}
    if change == 'missing': del packages['child']
    elif change == 'version': packages['child']['version'] = '1'
    elif change == 'python': packages['child']['requires_python'] = '<2'
    else: packages['app']['requires_dist'] = ['child @ https://invalid.example/fixture.whl']
    with pytest.raises(ValueError):
        record.dependency_closure('app', packages, default_environment())


def test_inventory_separates_tools_and_incidental_packages(tmp_path, monkeypatch):
    (tmp_path / 'requirements.txt').write_text('app\npytest\n')
    installed = {'app': package(), 'pytest': package(), 'pip': package('26'), 'unused': package('9')}
    monkeypatch.setattr(record, 'installed_inventory', lambda: installed)
    env = record.capture_environment(tmp_path)
    assert [p['name'] for p in env['dependencies']['packages']] == ['app', 'pytest']
    assert env['bootstrap_tools']['pip']['version'] == '26'
    assert env['unrelated']['count'] == 1
    assert 'unused' not in json.dumps(env)
    assert env['installation_artifacts'] == record.PROVENANCE
    pins = record.constraints(env)
    assert 'app==1 ; implementation_name' in pins
    assert 'python_version ==' in pins and 'platform_machine ==' in pins
    assert 'pip==' not in pins and 'unused==' not in pins


def fixture_job(tmp_path):
    """Synthetic successful runner evidence; real flow is exercised separately."""
    job = tmp_path / 'job'
    job.mkdir()
    source = _make_release_source(job)
    node = 'tests/test_smoke.py::test_fixture'
    (source / 'tests/test_smoke.py').write_text('def test_fixture():\n    assert True\n')
    mapping = record.source_identity(source)
    identity = release.source_map_digest(mapping)
    write(job / 'source.json', {'sha256': mapping, 'file_map_sha256': identity})
    config = {'record_validation': True, 'collect_only': False, 'mode': 'regression',
              'selectors': ['tests/test_smoke.py'], 'hashseed': '0',
              'source_manifest_sha256': record.sha(job / 'source.json')}
    write(job / 'run.json', config)
    write(job / 'job.json', {'config_sha256': record.sha(job / 'run.json')})
    env = record.capture_environment(source)
    completion = {'exit_code': 0, 'incomplete': False, 'stop_reason': None,
                  'source_file_map_sha256': identity, 'phases': [],
                  'started_at': '2026-10-31T00:00:00+00:00', 'completed_at': '2026-10-31T00:00:01+00:00'}
    for index, group in enumerate(('collection', 'regression')):
        phase = f'{index:02}-{group}'
        work = job / phase
        work.mkdir()
        selectors = config['selectors'] if index == 0 else [node]
        selection = {'mode': 'regression', 'scope': selectors, 'excluded': [],
                     'selected': [{'nodeid': node, 'group': 'regression', 'category': 'regression'}]}
        write(work / 'selection.json', selection)
        if index == 0: write(job / 'selection.json', selection)
        write(job / (phase + '-input.json'), {'group': group, 'selectors': selectors})
        (job / (phase + '.log')).write_text('Synthetic evidence fixture\n')
        write(work / 'environment-before.json', env)
        write(work / 'environment-after.json', env)
        write(work / 'results.json', [] if index == 0 else [
            {'nodeid': node, 'when': when, 'outcome': 'passed'} for when in ('setup', 'call', 'teardown')])
        (work / 'junit.xml').write_text(f'<testsuites><testsuite tests="{index}" failures="0" errors="0" skipped="0"/></testsuites>')
        worker = {'pytest_exit_code': 0, 'error': None, 'isolation_violations': [], 'route_failures': [],
                  'source_file_map_sha256': identity, 'python': env['interpreter']['version'],
                  'validation_capture': {'before_sha256': record.sha(work / 'environment-before.json'),
                      'after_sha256': record.sha(work / 'environment-after.json'),
                      'results_sha256': record.sha(work / 'results.json'),
                      'junit_sha256': record.sha(work / 'junit.xml'), 'environment_unchanged': True}}
        write(work / 'worker.json', worker)
        completion['phases'].append({'phase': phase, 'group': group, 'exit_code': 0,
            'worker': worker, 'worker_receipt_sha256': record.sha(work / 'worker.json'),
            'log_sha256': record.sha(job / (phase + '.log')), 'termination_signals': []})
    write(job / 'completion.json', completion)
    return source, job, env


def export_fixture(source, job, target):
    receipt, snapshot = record.make_receipt(source, [job])
    target.mkdir()
    write(target / 'receipt.json', receipt)
    (target / 'constraints.txt').write_text(snapshot)
    return receipt


def test_capture_export_verify_and_no_circular_source_identity(tmp_path):
    source, job, env = fixture_job(tmp_path)
    mapping = record.source_identity(source)
    receipt = export_fixture(source, job, source / 'validation')
    assert record.source_identity(source) == mapping
    assert record.verify_pair(source / 'validation', mapping, environment=env, jobs=[job]) == receipt
    assert receipt['kind'] == 'matching_validated_environment'
    assert 'Synthetic evidence fixture' not in json.dumps(receipt)
    assert str(tmp_path) not in json.dumps(receipt)


@pytest.mark.parametrize('target', ['requirements.txt', 'scripts/helper.py', 'tests/added.py'])
def test_source_and_requirements_mismatches(tmp_path, target):
    source, job, env = fixture_job(tmp_path)
    export_fixture(source, job, tmp_path / 'record')
    (source / target).write_text('changed\n')
    with pytest.raises(ValueError): record.make_receipt(source, [job])
    with pytest.raises(ValueError): record.verify_pair(tmp_path / 'record', record.source_identity(source))


@pytest.mark.parametrize('change', ['version', 'interpreter', 'tls', 'tool', 'unrelated', 'markers'])
def test_current_environment_must_match(tmp_path, change):
    source, job, env = fixture_job(tmp_path)
    export_fixture(source, job, tmp_path / 'record')
    altered = deepcopy(env)
    if change == 'version': altered['dependencies']['packages'][0]['version'] = '99'
    elif change == 'interpreter': altered['interpreter']['executable_sha256'] = 'b' * 64
    elif change == 'tls': altered['interpreter']['tls'] = 'different TLS'
    elif change == 'tool': altered['bootstrap_tools']['pip']['version'] = '99'
    elif change == 'unrelated': altered['unrelated']['count'] += 1
    else: altered['markers']['python_version'] = '3.12'
    with pytest.raises(ValueError, match='Current interpreter/environment'):
        record.verify_pair(tmp_path / 'record', record.source_identity(source), environment=altered)


@pytest.mark.parametrize('target', ['run.json', 'source.json', 'completion.json', 'selection.json',
    '01-regression/worker.json', '01-regression/environment-before.json', '01-regression/environment-after.json',
    '01-regression/results.json', '01-regression/selection.json', '01-regression/junit.xml', '01-regression.log',
    '01-regression-input.json'])
def test_supplied_validation_evidence_mismatch(tmp_path, target):
    source, job, env = fixture_job(tmp_path)
    export_fixture(source, job, tmp_path / 'record')
    path = job / target
    if target.endswith('.json'):
        data = record.read(path)
        if isinstance(data, dict): data['foreign_evidence'] = True
        else: data.append({'nodeid': 'foreign', 'when': 'call', 'outcome': 'passed'})
        write(path, data)
    else: path.write_text(path.read_text() + '\nchanged\n')
    with pytest.raises((ValueError, KeyError, record.ET.ParseError)):
        record.verify_pair(tmp_path / 'record', record.source_identity(source), jobs=[job])


@pytest.mark.parametrize('change', ['inventory_only', 'failed', 'collection_only', 'missing_worker', 'missing_results', 'junit_failure'])
def test_inapplicable_job_cannot_be_exported(tmp_path, change):
    source, job, env = fixture_job(tmp_path)
    if change in {'inventory_only', 'collection_only'}:
        cfg = record.read(job / 'run.json')
        cfg['record_validation' if change == 'inventory_only' else 'collect_only'] = change != 'inventory_only'
        write(job / 'run.json', cfg)
        write(job / 'job.json', {'config_sha256': record.sha(job / 'run.json')})
    elif change == 'failed':
        data = record.read(job / 'completion.json'); data['exit_code'] = 1; write(job / 'completion.json', data)
    elif change == 'missing_worker': (job / '01-regression/worker.json').unlink()
    elif change == 'missing_results': write(job / '01-regression/results.json', [])
    else: (job / '01-regression/junit.xml').write_text('<testsuites><testsuite failures="1"/></testsuites>')
    with pytest.raises((ValueError, OSError)):
        record.make_receipt(source, [job])


@pytest.mark.parametrize('change', ['environment_drift', 'worker_python', 'missing_outcome', 'missing_phase', 'junit_failure'])
def test_inconsistent_evidence_rejected_even_after_rehash(tmp_path, change):
    source, job, env = fixture_job(tmp_path)
    complete = record.read(job / 'completion.json')
    phase = complete['phases'][1]
    work = job / phase['phase']
    worker = phase['worker']
    if change == 'environment_drift':
        changed = deepcopy(env)
        changed['bootstrap_tools']['pip']['version'] = '99'
        write(work / 'environment-after.json', changed)
        worker['validation_capture']['after_sha256'] = record.sha(work / 'environment-after.json')
        worker['validation_capture']['environment_unchanged'] = False
    elif change == 'worker_python': worker['python'] = 'different Python'
    elif change == 'missing_outcome':
        write(work / 'results.json', [])
        worker['validation_capture']['results_sha256'] = record.sha(work / 'results.json')
    elif change == 'missing_phase': complete['phases'].pop()
    else:
        (work / 'junit.xml').write_text('<testsuites><testsuite failures="1"/></testsuites>')
        worker['validation_capture']['junit_sha256'] = record.sha(work / 'junit.xml')
    write(work / 'worker.json', worker)
    phase['worker_receipt_sha256'] = record.sha(work / 'worker.json')
    write(job / 'completion.json', complete)
    with pytest.raises(ValueError):
        record.make_receipt(source, [job])


def test_relative_job_paths_and_supplied_foreign_job(tmp_path, monkeypatch):
    source, job, env = fixture_job(tmp_path)
    monkeypatch.chdir(tmp_path)
    receipt = export_fixture(source, Path('job'), tmp_path / 'record')
    assert record.verify_pair(tmp_path / 'record', record.source_identity(source), jobs=[Path('job')]) == receipt
    complete = record.read(job / 'completion.json')
    complete['completed_at'] = '2026-10-31T00:00:02+00:00'
    write(job / 'completion.json', complete)
    with pytest.raises(ValueError, match='Supplied validation evidence'):
        record.verify_pair(tmp_path / 'record', record.source_identity(source), jobs=[job])


def test_public_outcome_and_private_nested_fields_rejected(tmp_path):
    source, job, env = fixture_job(tmp_path)
    receipt = export_fixture(source, job, tmp_path / 'record')
    receipt['validation'][0]['phases'][1]['results'][1]['outcome'] = 'skipped'
    write(tmp_path / 'record/receipt.json', receipt)
    with pytest.raises(ValueError, match='Public results'):
        record.verify_pair(tmp_path / 'record', record.source_identity(source))
    receipt['environment']['markers']['platform_machine'] = {'raw_log': 'private'}
    write(tmp_path / 'record/receipt.json', receipt)
    with pytest.raises(ValueError, match='portable string'):
        record.verify_pair(tmp_path / 'record', record.source_identity(source))


def test_packaged_pair_exact_manifest_and_private_exclusion(tmp_path):
    source, job, env = fixture_job(tmp_path)
    receipt = export_fixture(source, job, source / 'validation')
    (source / 'validation/raw.log').write_text('private log')
    (source / 'validation/private.json').write_text('{"private": true}')
    result = release.build_release_archive(source_root=source, output_dir=tmp_path / 'dist')
    staged = Path(result['staging_root'])
    assert {p.name for p in (staged / 'validation').iterdir()} == {'constraints.txt', 'receipt.json'}
    assert record.read(staged / 'validation/receipt.json') == receipt
    assert release._parse_manifest(staged / release.MANIFEST_NAME)[Path('validation/receipt.json')] == record.sha(staged / 'validation/receipt.json')
    release.verify_archive(Path(result['archive']))
    assert not (staged / 'plans').exists() and not (staged / 'logs').exists()
    (staged / 'validation/private.json').write_text('{}')
    with pytest.raises(release.ReleaseArchiveError, match='Non-public validation'):
        release.validate_release_tree(staged, version='0.1.0')


@pytest.mark.parametrize('change', ['partial', 'stale_source', 'constraints', 'private_field', 'provenance', 'path'])
def test_packager_rejects_invalid_pair(tmp_path, change):
    source, job, env = fixture_job(tmp_path)
    receipt = export_fixture(source, job, source / 'validation')
    if change == 'partial': (source / 'validation/constraints.txt').unlink()
    elif change == 'stale_source': (source / 'scripts/helper.py').write_text('changed\n')
    elif change == 'constraints': (source / 'validation/constraints.txt').write_text('incidental==1\n')
    else:
        if change == 'private_field': receipt['raw_log'] = 'do not export'
        elif change == 'provenance': receipt['environment']['installation_artifacts'] = {'status': 'known', 'wheel_sha256': 'a' * 64}
        else: receipt['validation'][0]['selectors'] = ['/home/example/private.py']
        write(source / 'validation/receipt.json', receipt)
    with pytest.raises((release.ReleaseArchiveError, ValueError)):
        release.build_release_archive(source_root=source, output_dir=tmp_path / 'dist')
