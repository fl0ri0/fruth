"""Routing/isolation contracts; no runtime imports, providers or real processes."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys

import pytest

from scripts import run_tests as runner
from scripts.test_isolation import cold_child_allowed, make_guard
from scripts.test_selection import CAMPAIGNS, HISTORICAL, category, execution_group


@pytest.mark.parametrize('table,kind', [(CAMPAIGNS, 'research'), (HISTORICAL, 'historical')])
def test_explicit_entrypoint_routing(table, kind):
    for module, entries in table.items():
        for entry in entries:
            assert category(f'tests/{module}::{entry}[example]') == kind


@pytest.mark.parametrize('node', [
    'test_text_file_binding_hypothesis.py::test_required_positive_controls',
    'test_graph_lineage_stateful_hypothesis.py::test_exact_successor_control[True-True]',
    'test_graph_lineage_successor_producer_regression.py::test_accepted_duty_survives_automatic_successor_production',
    'test_graph_lineage_two_successors_hypothesis.py::test_failed_second_duty_keeps_first_result_and_blocker[True]',
    'test_late_cancel_lineage_hypothesis.py::test_cancel_timing_controls[False-base64-before_dispatch]',
    'test_c9_continuation_hypothesis.py::test_positive_orders[True-False]',
    'test_late_fill_c9_correction.py::test_retained_serial_controls[worker_first]',
    'test_cold_process_recovery.py::test_deterministic_cold_recovery[success]',
])
def test_mixed_modules_keep_deterministic_regressions(node):
    assert category('tests/' + node) == 'regression'


def test_purity_is_a_separate_execution_group_and_unlisted_generated_is_opt_in():
    assert execution_group('tests/test_persistence_trace_adapter.py::test_named_limits_cannot_be_increased[kwargs0]') == 'pure-adapter'
    assert execution_group('tests/test_cold_process_recovery.py::test_cold_profile_is_pure_and_bounded') == 'pure-cold-profile'
    assert execution_group('tests/test_cold_process_recovery.py::test_one_cold_campaign') == 'regression'
    assert category('tests/test_future_property.py::test_generated', generated=True) == 'research'


def child_inputs(tmp_path, monkeypatch):
    job, production = tmp_path / 'job', tmp_path / 'production'
    source, evidence = job / 'source', job / 'examples'
    scenario = evidence / 'control-success'
    scenario.mkdir(parents=True)
    input_path, output = scenario / 'writer-input.json', scenario / 'writer.json'
    input_path.write_text('{}')
    environment = {'FRUTH_COLD_PLAN': str(job), 'FRUTH_COLD_PRODUCTION': str(production)}
    monkeypatch.setenv('FRUTH_LINEAGE_CONTEXT', 'tests/test_cold_process_recovery.py::control')
    env = dict(environment, TMPDIR=str(scenario / 'temporary'), PYTHONDONTWRITEBYTECODE='1',
               FRUTH_HYPOTHESIS_EVIDENCE_DIR=str(scenario / 'writer-fixture'),
               FRUTH_LINEAGE_CONTEXT=os.environ['FRUTH_LINEAGE_CONTEXT'])
    for key in ('PYTEST_CURRENT_TEST', 'PYTEST_VERSION'):
        if key in os.environ:
            env[key] = os.environ[key]
    values = [sys.executable, [sys.executable, '-B', str(source / 'tests/cold_process_child.py'),
                             'writer', str(input_path), str(output)], str(source), env]
    context = dict(source=source, evidence=evidence, job=job, production=production,
                   environment=environment, enabled=True)
    return values, context


def test_exact_cold_command_and_environment(tmp_path, monkeypatch):
    values, context = child_inputs(tmp_path, monkeypatch)
    assert cold_child_allowed(*values, **context)
    for change in ('executable', 'argv0', 'script', 'role', 'input', 'output', 'cwd', 'env', 'pythonpath', 'reuse'):
        altered = deepcopy(values)
        if change == 'executable': altered[0] = '/different/python'
        elif change == 'argv0': altered[1][0] = '/different/python'
        elif change == 'script': altered[1][2] = str(context['source'] / 'other.py')
        elif change == 'role': altered[1][3] = 'shell'
        elif change == 'input': altered[1][4] = str(tmp_path / 'foreign-input.json')
        elif change == 'output': altered[1][5] = str(tmp_path / 'foreign.json')
        elif change == 'cwd': altered[2] = str(tmp_path)
        elif change == 'env': altered[3]['FRUTH_COLD_PLAN'] = str(tmp_path)
        elif change == 'pythonpath': altered[3]['PYTHONPATH'] = '/foreign'
        elif change == 'reuse': Path(altered[1][5]).write_text('{}')
        assert not cold_child_allowed(*altered, **context), change
    assert not cold_child_allowed(*values, **dict(context, enabled=False))


def test_guard_denies_network_process_production_and_outside_writes(tmp_path, monkeypatch):
    values, context = child_inputs(tmp_path, monkeypatch)
    context['cold'] = context.pop('enabled')
    audit, violations = make_guard(**context)
    audit('subprocess.Popen', tuple(values))
    for event, args in (
        ('socket.connect', (None, ('localhost', 1))),
        ('socket.bind', (None, ('localhost', 1))),
        ('os.fork', ()), ('os.system', ('never executed',)),
        ('subprocess.Popen', (sys.executable, [sys.executable, '-c', 'pass'], str(tmp_path), {})),
        ('open', (str(context['production'] / 'state/ledger'), 'r', 0)),
        ('os.scandir', (str(context['production'] / 'artifacts'),)),
        ('open', (str(tmp_path / 'outside'), 'w', os.O_WRONLY)),
        ('sqlite3.connect', (str(context['production'] / 'state/index.sqlite3'),)),
    ):
        with pytest.raises(PermissionError):
            audit(event, args)
    assert len(violations) == 9


def test_missing_and_invalid_configuration_fail_before_runtime_imports(tmp_path):
    prior = {name for name in sys.modules if name.startswith('fruth_')}
    with pytest.raises(FileNotFoundError):
        runner.load_config(tmp_path)
    (tmp_path / 'run.json').write_text('{')
    with pytest.raises(json.JSONDecodeError):
        runner.load_config(tmp_path)
    (tmp_path / 'run.json').write_text('{"schema": 0}')
    with pytest.raises(ValueError, match='Invalid runner configuration'):
        runner.load_config(tmp_path)
    assert prior == {name for name in sys.modules if name.startswith('fruth_')}


def test_environment_does_not_inherit_study_budgets_or_runtime_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv('FRUTH_HYPOTHESIS_ADAPTER', '1')
    monkeypatch.setenv('FRUTH_LINEAGE_STEPS', '1')
    monkeypatch.setenv('FRUTH_GRAPH_REBASE_OPERATOR_TOKEN', 'synthetic')
    monkeypatch.setenv('PYTHONPATH', '/foreign')
    env = runner.clean_environment(tmp_path, hashseed='1')
    assert not any(key.startswith('FRUTH_') for key in env)
    assert 'PYTHONPATH' not in env and env['PYTHONHASHSEED'] == '1'


def test_source_drift_fails_closed(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'owner.py').write_text('before')
    mapping = {'owner.py': runner.sha(source / 'owner.py')}
    identity = hashlib.sha256(json.dumps(mapping, sort_keys=True).encode()).hexdigest()
    runner.save(tmp_path / 'source.json', {'file_map_sha256': identity, 'sha256': mapping})
    assert runner.verify_source(tmp_path) == identity
    (source / 'owner.py').write_text('after')
    with pytest.raises(ValueError, match='Frozen source drift'):
        runner.verify_source(tmp_path)


@pytest.mark.parametrize('selectors', [None, 'tests', [], [''], [None], ['--collect-only'],
                                      ['/tests'], ['tests/../state'], ['tests/missing.py']])
def test_invalid_saved_selectors_are_rejected_before_collection(tmp_path, selectors):
    (tmp_path / 'tests').mkdir()
    with pytest.raises(ValueError):
        runner.validate_selectors(selectors, tmp_path)


def test_invalid_worker_phase_cannot_read_configuration(tmp_path):
    with pytest.raises(ValueError, match='phase path'):
        runner.worker(tmp_path, '../foreign')
