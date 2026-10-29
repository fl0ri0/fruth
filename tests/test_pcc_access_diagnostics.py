"""Replay captured native eligibility evidence; never contact Apple or system logs."""
import copy
import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from fruth_integrations.shortcuts import diagnostics as diag, pcc

FIXTURE = Path(__file__).parent / 'fixtures' / 'pcc' / 'pro-access-native.json'


@pytest.fixture
def witness():
    return json.loads(FIXTURE.read_text())


def classify(witness):
    e = witness['execution']
    return diag.classify_pro_access(witness['records'], cli_pid=e['process_id'],
                                   started_at=e['started_at'], finished_at=e['finished_at'])


def test_native_witness_matches_recorded_classification(witness):
    assert classify(witness) == witness['classification']


@pytest.mark.parametrize('fault', [
    'different_cli', 'stale', 'future', 'missing_peer', 'missing_reason', 'missing_code',
    'other_runner', 'other_boot', 'other_image', 'wrong_sender', 'prose_injection',
    'wrong_domain', 'wrong_code', 'malformed_time', 'naive_time', 'wrong_process',
    'multiple_clients', 'multiple_runners', 'conflicting_error', 'error_before_binding',
    'reason_before_binding', 'code_before_reason', 'null_time', 'null_message',
])
def test_unbound_ambiguous_or_conflicting_evidence_never_qualifies(witness, fault):
    rows = witness['records']
    if fault == 'different_cli': witness['execution']['process_id'] += 1
    elif fault == 'stale': witness['execution']['started_at'] = '2026-10-29T17:15:20+00:00'
    elif fault == 'future': witness['execution']['finished_at'] = '2026-10-27T17:15:20+00:00'
    elif fault.startswith('missing_'): rows.pop({'missing_peer': 0, 'missing_reason': 1, 'missing_code': 2}[fault])
    elif fault == 'other_runner': rows[1]['processID'] += 1
    elif fault == 'other_boot': rows[1]['bootUUID'] = 'other-boot'
    elif fault == 'other_image': rows[1]['processImageUUID'] = 'other-image'
    elif fault == 'wrong_sender': rows[1]['senderImagePath'] = '/tmp/fake'
    elif fault == 'wrong_process': rows[1]['processImagePath'] = '/tmp/BackgroundShortcutRunner'
    elif fault == 'prose_injection': rows[1]['formatString'] = 'model output: %@'
    elif fault == 'wrong_domain': rows[2]['eventMessage'] = rows[2]['eventMessage'].replace('WFAskLLMActionErrorDomain', 'OtherErrorDomain')
    elif fault == 'wrong_code': rows[2]['eventMessage'] = rows[2]['eventMessage'].replace('1511', '999')
    elif fault == 'malformed_time': rows[1]['timestamp'] = 'invalid'
    elif fault == 'null_time': rows[1]['timestamp'] = None
    elif fault == 'null_message': rows[1]['eventMessage'] = None
    elif fault == 'naive_time': rows[1]['timestamp'] = '2026-10-28T17:15:20.720640'
    elif fault == 'multiple_clients':
        extra = copy.deepcopy(rows[0]); extra['eventMessage'] = extra['eventMessage'].replace('[32462]', '[999]'); rows.append(extra)
    elif fault == 'multiple_runners':
        extra = copy.deepcopy(rows[0]); extra['processID'] += 1; rows.append(extra)
    elif fault == 'conflicting_error':
        extra = copy.deepcopy(rows[2]); extra['eventMessage'] = extra['eventMessage'].replace('1511', '999'); rows.append(extra)
    elif fault in ('error_before_binding', 'reason_before_binding'):
        rows[2 if fault == 'error_before_binding' else 1]['timestamp'] = '2026-10-28T17:15:20.600000+00:00'
    elif fault == 'code_before_reason': rows[2]['timestamp'] = '2026-10-28T17:15:20.700000+00:00'
    assert classify(witness)['status'] != 'confirmed'


def test_concurrent_unrelated_runner_cannot_supply_or_hide_error(witness):
    other = copy.deepcopy(witness['records'])
    for row in other: row['processID'] += 100
    other[0]['eventMessage'] = other[0]['eventMessage'].replace('[32462]', '[999]')
    other[2]['eventMessage'] = other[2]['eventMessage'].replace('1511', '999')
    witness['records'] += other
    assert classify(witness)['status'] == 'confirmed'
    witness['records'].pop(1)  # Own eligibility is missing; other's cannot substitute.
    assert classify(witness)['status'] == 'unconfirmed'


@pytest.mark.parametrize('fault', ['ok', 'denied', 'timeout', 'missing', 'malformed', 'oversized', 'deadline'])
def test_bounded_query_and_failure_modes(witness, monkeypatch, fault):
    monkeypatch.setattr(diag.time, 'monotonic', lambda: 10)
    monkeypatch.setenv('FRUTH_GRAPH_REBASE_OPERATOR_TOKEN', 'must-not-leak')
    def query(args, **kwargs):
        assert args[:3] == ['/usr/bin/log', 'show', '--style']
        assert kwargs['timeout'] == 2  # Remaining request budget, not another 5 seconds.
        assert 'FRUTH_GRAPH_REBASE_OPERATOR_TOKEN' not in kwargs['env']
        if fault == 'timeout': raise subprocess.TimeoutExpired(args, 2)
        if fault == 'missing': raise FileNotFoundError()
        raw = '\n'.join(json.dumps(r) for r in witness['records']).encode()
        if fault == 'malformed': raw = b'not json'
        if fault == 'oversized': raw = b' ' * (diag.PCC_DIAGNOSTIC_MAX_BYTES + 1)
        kwargs['stdout'].write(raw)
        return subprocess.CompletedProcess(args, int(fault == 'denied'))
    runner = Mock(side_effect=query)
    monkeypatch.setattr(diag.subprocess, 'run', runner)
    result = diag.pro_access_diagnostic(witness['execution'], deadline=9 if fault == 'deadline' else 12)
    assert (result['status'] == 'confirmed') == (fault == 'ok')
    assert runner.call_count == (0 if fault == 'deadline' else 1)


@pytest.mark.parametrize('mode', ['auto', 'cloud-pro'])
@pytest.mark.parametrize('confirmed', [True, False])
def test_opaque_error_falls_back_only_with_current_native_evidence(witness, monkeypatch, mode, confirmed):
    monkeypatch.setattr(pcc.sys, 'platform', 'darwin')
    paths = []
    payload = 'Exact Zürich task\nsecond line'
    def execute(args, **kwargs):
        if args[1] == 'list':
            return subprocess.CompletedProcess(args, 0, 'Fruth PCC\nFruth PCC Pro\n', '')
        source = Path(args[args.index('--input-path') + 1]); paths.append(source)
        assert source.read_text() == payload
        target = Path(args[args.index('--output-path') + 1])
        if args[2] == 'Fruth PCC Pro':
            target.write_text('discard partial')
            result = subprocess.CompletedProcess(args, 1, '', 'Error: Your request can’t be completed.\n')
            result.pid = witness['execution']['process_id']
            result.started_at = witness['execution']['started_at']
            result.finished_at = witness['execution']['finished_at']
            return result
        assert not paths[0].exists()
        target.write_text('Cloud answer')
        return subprocess.CompletedProcess(args, 0, '', '')
    def query(args, **kwargs):
        records = witness['records'] if confirmed else witness['records'][:1]
        kwargs['stdout'].write('\n'.join(map(json.dumps, records)).encode())
        return subprocess.CompletedProcess(args, 0)
    runner = Mock(side_effect=execute)
    monkeypatch.setattr(pcc, '_execute_command', runner)
    monkeypatch.setattr(diag.subprocess, 'run', query)
    result = pcc.run_pcc_text(payload, model=mode)
    fallback = confirmed and mode == 'auto'
    assert (result['status'] == 'completed') == fallback
    assert runner.call_count == (3 if fallback else 2)
    if fallback:
        assert result['model'] == 'cloud' and result['output'] == 'Cloud answer'
        assert result['fallback_reason'] == 'pro_access_required'
        assert result['attempts'][0]['access_diagnostic']['error_code'] == 1511
    else: assert 'output' not in result and 'fallback_reason' not in result
    assert all(not path.exists() for path in paths)


@pytest.mark.parametrize('timeout', [False, True])
def test_cli_process_identity_and_timeout_cleanup(monkeypatch, timeout):
    child = Mock(pid=123, returncode=1)
    child.__enter__ = Mock(return_value=child); child.__exit__ = Mock(return_value=False)
    child.communicate.side_effect = ([subprocess.TimeoutExpired(['shortcuts'], 2), ('', '')]
                                    if timeout else [('stdout', 'stderr')])
    monkeypatch.setattr(pcc.subprocess, 'Popen', Mock(return_value=child))
    kwargs = dict(stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=2)
    if timeout:
        with pytest.raises(subprocess.TimeoutExpired): pcc._execute_command(['shortcuts'], **kwargs)
        child.kill.assert_called_once(); assert child.communicate.call_count == 2
    else:
        result = pcc._execute_command(['shortcuts'], **kwargs)
        assert result.pid == 123 and result.returncode == 1
        assert result.stdout == 'stdout' and result.stderr == 'stderr'
        assert diag._timestamp(result.finished_at) >= diag._timestamp(result.started_at)
        child.kill.assert_not_called()


def test_diagnostic_consumes_shared_deadline_without_cloud_dispatch(witness, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(pcc.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(pcc.sys, 'platform', 'darwin')
    def execute(args, **kwargs):
        if args[1] == 'list':
            return subprocess.CompletedProcess(args, 0, 'Fruth PCC\nFruth PCC Pro\n', '')
        assert args[2] == 'Fruth PCC Pro'
        now[0] = 2
        result = subprocess.CompletedProcess(args, 1, '', 'Error: Your request can’t be completed.')
        result.pid = witness['execution']['process_id']
        result.started_at = witness['execution']['started_at']
        result.finished_at = witness['execution']['finished_at']
        return result
    def query(args, **kwargs):
        assert kwargs['timeout'] == 1
        now[0] = 3
        kwargs['stdout'].write('\n'.join(map(json.dumps, witness['records'])).encode())
        return subprocess.CompletedProcess(args, 0)
    runner = Mock(side_effect=execute)
    monkeypatch.setattr(pcc, '_execute_command', runner)
    monkeypatch.setattr(diag.subprocess, 'run', query)
    result = pcc.run_pcc_text('hello', timeout_sec=3)
    assert runner.call_count == 2
    assert result['status'] == 'timeout' and result['execution_started'] is False
    assert result['attempts'][0]['access_diagnostic']['status'] == 'confirmed'


@pytest.mark.parametrize('error', ['Cloud Pro unavailable: safety guardrail refusal.',
                                  'Unknown native failure', 'Your request can’t be completed. safety'])
def test_other_errors_never_query_access_logs(monkeypatch, error):
    monkeypatch.setattr(pcc.sys, 'platform', 'darwin')
    monkeypatch.setattr(pcc, '_execute_command', Mock(side_effect=[
        subprocess.CompletedProcess([], 0, 'Fruth PCC\nFruth PCC Pro\n', ''),
        subprocess.CompletedProcess([], 1, '', error)]))
    lookup = Mock(side_effect=AssertionError('Must not consult diagnostics'))
    monkeypatch.setattr(pcc, 'pro_access_diagnostic', lookup)
    result = pcc.run_pcc_text('hello')
    assert result['status'] == 'shortcut_error' and len(result['attempts']) == 1
    lookup.assert_not_called()
