"""Pytest routing only; isolation is installed by run_tests before collection.

Keep this module free of runtime imports. Historical wrappers retain their exact
source/oracles; classification never changes a test outcome into skip or xfail.
"""
from __future__ import annotations

import os

import pytest


CAMPAIGNS = {
    'test_text_file_binding_hypothesis.py': {
        'test_provider_wrappers_preserve_accepted_bindings',
        'test_saved_identity_and_conflicting_evidence_fail_closed',
        'test_real_adapters_preserve_provider_binding_and_rejection',
        'test_real_result_faults_cannot_fulfill_after_recovery',
    },
    'test_graph_lineage_stateful_hypothesis.py': {
        'TestGraphLineageOwners', 'TestGraphLineageAdapters',
    },
    'test_graph_lineage_successor_producer_regression.py': {'TestAutomaticSuccessorComposition'},
    'test_graph_lineage_two_successors_hypothesis.py': {'TestTwoSuccessorImages'},
    'test_late_cancel_lineage_hypothesis.py': {'TestLateCancelLineage'},
    'test_late_fill_c9_correction.py': {'test_bounded_corrected_control_worker_schedules'},
    'test_c9_continuation_hypothesis.py': {'test_bounded_continuation'},
    'test_c9_pending_handoff_hypothesis.py': {'test_bounded_actual_child_continuation'},
    'test_persistence_recovery_campaign.py': {'test_one_bounded_immutable_corpus'},
    'test_cold_process_recovery.py': {'test_one_cold_campaign'},
}

# These original overlap seams can pause while holding the now-required runtime
# lock. Maintained equivalents use current_scheduling in the C9 correction suite.
# Do not exclude the module's fixtures from import by those maintained controls.
HISTORICAL = {
    'test_late_cancel_lineage_hypothesis.py': {
        'test_retained_cancellation_failure_blob', 'test_bounded_original_prefix_reduction',
    },
    'test_late_fill_control_overlap_hypothesis.py': {
        'test_bounded_control_worker_schedules', 'test_serial_and_overlap_controls',
        'test_oracle_detects_observed_sibling_loss',
    },
    'test_late_fill_control_overlap_regression.py': {
        'test_original_overlap_failure_blob', 'test_original_explicit_schedule',
        'test_original_consumed_prefix_reduction',
        'test_committed_cancel_after_worker_read_cannot_be_undone',
        'test_bounded_boundary_reduction',
    },
}


def identity(nodeid):
    parts = nodeid.split('::')
    return parts[0].rsplit('/', 1)[-1], parts[1].split('[', 1)[0] if len(parts) > 1 else ''


def category(nodeid, *, generated=False):
    module, entry = identity(nodeid)
    if entry in HISTORICAL.get(module, ()):
        return 'historical'
    if entry in CAMPAIGNS.get(module, ()) or generated:
        return 'research'
    return 'regression'


def execution_group(nodeid):
    module, entry = identity(nodeid)
    if module == 'test_persistence_trace_adapter.py':
        return 'pure-adapter'
    if module == 'test_cold_process_recovery.py' and entry == 'test_cold_profile_is_pure_and_bounded':
        return 'pure-cold-profile'
    return 'regression'


def pytest_addoption(parser):
    parser.addoption('--fruth-selection', choices=('regression', 'research', 'historical'),
                     default='regression', help='Select one explicit test category (default: regression).')


def pytest_configure(config):
    for name, description in (
        ('research', 'explicit generated research campaign'),
        ('historical', 'retained diagnostic entrypoint, not corrected-source pass criteria'),
        ('fresh_process', 'requires separate interpreter collection and execution'),
    ):
        config.addinivalue_line('markers', f'{name}: {description}')
    # This is an execution context, not a credential. Only the pre-import runner
    # creates it in memory; inherited environment flags cannot enable research.
    if config.getoption('--fruth-selection') != 'regression' and not hasattr(config, '_fruth_runner'):
        raise pytest.UsageError('Research/historical selection requires scripts/run_tests.py; '
                                'guards must be installed before collection.')


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config, items):
    mode = config.getoption('--fruth-selection')
    selected, excluded = [], []
    for item in items:
        kind = category(item.nodeid, generated=bool(getattr(item.obj, 'is_hypothesis_test', False)))
        group = execution_group(item.nodeid)
        if kind != 'regression':
            item.add_marker(getattr(pytest.mark, kind))
        if group != 'regression':
            item.add_marker(pytest.mark.fresh_process)
        record = {'nodeid': item.nodeid, 'category': kind, 'group': group}
        (selected if kind == mode else excluded).append((item, record))
    items[:] = [item for item, _ in selected]
    config._fruth_selection = {
        'mode': mode, 'selected': [record for _, record in selected],
        'excluded': [record for _, record in excluded],
        'scope': list(config.args),
    }
    if excluded:
        config.hook.pytest_deselected(items=[item for item, _ in excluded])


def pytest_runtest_setup(item):
    os.environ['FRUTH_LINEAGE_CONTEXT'] = item.nodeid
    group = execution_group(item.nodeid)
    context = getattr(item.config, '_fruth_runner', {})
    if group != 'regression' and context.get('group') != group:
        pytest.fail('This test requires fresh collection via scripts/run_tests.py; '
                    'it cannot share an interpreter with runtime tests.', pytrace=False)
    module, _ = identity(item.nodeid)
    if module in {'test_cold_process_recovery.py', 'test_persistence_recovery_study.py', 'test_native_process_routes.py'} and not context:
        pytest.fail('Use scripts/run_tests.py for exclusive evidence and pre-import isolation.', pytrace=False)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    selection = getattr(config, '_fruth_selection', None)
    if selection:
        counts = {kind: sum(r['category'] == kind for r in selection['excluded'])
                  for kind in ('regression', 'research', 'historical')}
        terminalreporter.write_line(
            f"Fruth {selection['mode']}: {len(selection['selected'])} selected; "
            + ', '.join(f'{count} {kind} excluded' for kind, count in counts.items()))
        for record in selection['excluded']:
            terminalreporter.write_line(f"  excluded [{record['category']}] {record['nodeid']}")
