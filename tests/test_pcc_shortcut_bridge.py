"""Isolated Shortcuts transport checks; never invoke Apple or production state."""

import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from fruth_integrations.shortcuts import pcc


@pytest.fixture
def runner(monkeypatch):
    monkeypatch.setattr(pcc.sys, 'platform', 'darwin')
    fake = Mock()
    monkeypatch.setattr(pcc.subprocess, 'run', fake)
    return fake


def listing(names='Fruth PCC\nFruth PCC Pro\n'):
    return subprocess.CompletedProcess([], 0, names, '')


def test_listing_does_not_claim_access_or_start_inference(runner):
    runner.return_value = listing('Fruth PCC\n')
    result = pcc.list_pcc_shortcuts()
    assert [(m['model'], m['installation'], m['access']) for m in result['models']] == [
        ('cloud', 'installed', 'unknown'), ('cloud-pro', 'missing', 'unknown')]
    assert runner.call_args.args[0] == ['/usr/bin/shortcuts', 'list']
    assert runner.call_count == 1


@pytest.mark.parametrize('model,name', pcc.PCC_SHORTCUTS.items())
def test_exact_selection_private_staging_fresh_unicode_and_cleanup(runner, monkeypatch, model, name):
    monkeypatch.setenv('FRUTH_GRAPH_REBASE_OPERATOR_TOKEN', 'test-secret')
    staged = []
    prompt = 'Preserve this text: Zürich — grüezi\nsecond line\n'

    def invoke(args, **kwargs):
        assert 'FRUTH_GRAPH_REBASE_OPERATOR_TOKEN' not in kwargs['env']
        assert kwargs['stdin'] == subprocess.DEVNULL
        if args[1] == 'list':
            return listing()
        assert args[1:3] == ['run', name]
        source = Path(args[args.index('--input-path') + 1])
        target = Path(args[args.index('--output-path') + 1])
        assert source.read_text() == prompt
        assert source.parent.stat().st_mode & 0o077 == 0
        assert not target.exists()
        assert args[-2:] == ['--output-type', 'public.plain-text']
        staged.append(source.parent)
        target.write_text('Zürich — grüezi\n')
        return subprocess.CompletedProcess(args, 0, 'ignored stdout', '')

    runner.side_effect = invoke
    for _ in range(2):
        result = pcc.run_pcc_text(prompt, model=model)
        assert result['status'] == 'completed'
        assert result['output'] == 'Zürich — grüezi\n'
        assert result['model'] == model
        assert 'stdout' not in result
    assert staged[0] != staged[1]
    assert all(not folder.exists() for folder in staged)


@pytest.mark.parametrize('text,model,timeout', [
    ('', 'cloud', 5), (' \n', 'cloud-pro', 5), ('hi', 'unknown', 5),
    ('hi', 'cloud', 0), ('hi', 'cloud', -1), ('hi', 'cloud', float('nan')),
    ('hi', 'cloud', float('inf')),
])
def test_invalid_or_blank_request_never_launches(runner, text, model, timeout):
    assert pcc.run_pcc_text(text, model=model, timeout_sec=timeout)['status'] == 'invalid_request'
    runner.assert_not_called()


@pytest.mark.parametrize('names,status', [
    ('Fruth PCC\n', 'shortcut_missing'),
    ('Fruth PCC Pro\nFruth PCC Pro\n', 'shortcut_ambiguous'),
])
def test_missing_or_ambiguous_pro_never_falls_back(runner, names, status):
    runner.return_value = listing(names)
    assert pcc.run_pcc_text('hello', model='cloud-pro')['status'] == status
    assert runner.call_count == 1


@pytest.mark.parametrize('fault,status', [
    ('nonzero', 'shortcut_error'), ('timeout', 'timeout'), ('missing', 'invalid_output'),
    ('empty', 'invalid_output'), ('utf8', 'invalid_output'), ('blocked', 'blocked'),
])
def test_failed_partial_missing_and_blocked_outputs_never_succeed(runner, fault, status):
    staged = []
    diagnostic = 'Sign in with an iCloud+ account to use Cloud Pro.'

    def invoke(args, **kwargs):
        if args[1] == 'list':
            return listing()
        target = Path(args[args.index('--output-path') + 1])
        staged.append(target.parent)
        if fault != 'missing':
            target.write_bytes({'empty': b'  ', 'utf8': b'\xff',
                                'blocked': b'BLOCKED: Input required.'}.get(fault, b'partial answer'))
        if fault == 'timeout':
            raise subprocess.TimeoutExpired(args, kwargs['timeout'])
        return subprocess.CompletedProcess(args, 1 if fault == 'nonzero' else 0,
                                           'must not become the answer', diagnostic)

    runner.side_effect = invoke
    result = pcc.run_pcc_text('hello', model='cloud-pro')
    assert result['status'] == status
    assert 'output' not in result
    if fault == 'nonzero':
        assert result['stderr'] == diagnostic
    if fault == 'timeout':
        assert result['system_side_cancellation'] == 'unverified'
    assert runner.call_count == 2  # listing plus one execution, never a retry
    assert all(not folder.exists() for folder in staged)


def test_discovery_error_is_not_model_unavailability(runner):
    runner.return_value = subprocess.CompletedProcess([], 1, '', "Couldn't communicate with a helper application")
    result = pcc.run_pcc_text('hello', model='cloud')
    assert result['stage'] == 'discovery'
    assert result['status'] == 'shortcut_error'
    assert 'models' not in result
    assert runner.call_count == 1


def test_missing_cli_and_wrong_platform(runner, monkeypatch):
    runner.side_effect = FileNotFoundError('missing shortcuts')
    assert pcc.list_pcc_shortcuts()['status'] == 'cli_unavailable'
    runner.reset_mock()
    monkeypatch.setattr(pcc.sys, 'platform', 'linux')
    assert pcc.list_pcc_shortcuts()['status'] == 'unsupported_platform'
    runner.assert_not_called()


def test_discovery_consumes_same_timeout_budget(runner, monkeypatch):
    # start request, start listing, finish listing, check remaining budget
    moments = iter([0, 0, 2, 2])
    monkeypatch.setattr(pcc.time, 'monotonic', lambda: next(moments))
    runner.return_value = listing()
    result = pcc.run_pcc_text('hello', model='cloud', timeout_sec=1)
    assert result['status'] == 'timeout'
    assert result['execution_started'] is False
    assert runner.call_count == 1


def test_cli_bad_file_exits_without_launching(runner, tmp_path, capsys):
    assert pcc.main(['run', '--model', 'cloud', '--input', str(tmp_path / 'missing')]) == 1
    assert 'input_error' in capsys.readouterr().out
    runner.assert_not_called()


def test_default_uses_pro_when_it_succeeds(runner):
    def invoke(args, **kwargs):
        if args[1] == 'list':
            return listing()
        assert args[1:3] == ['run', 'Fruth PCC Pro']
        Path(args[args.index('--output-path') + 1]).write_text('Pro answer')
        return subprocess.CompletedProcess(args, 0, '', '')

    runner.side_effect = invoke
    result = pcc.run_pcc_text('hello')
    assert result['status'] == 'completed'
    assert result['requested_model'] == 'auto'
    assert result['model'] == 'cloud-pro'
    assert result['output'] == 'Pro answer'
    assert len(result['attempts']) == 1
    assert 'output' not in result['attempts'][0]
    assert runner.call_count == 2


@pytest.mark.parametrize('error,reason', [
    ('Error: Die Aktion konnte nicht ausgeführt werden, da du bei einem iCloud+-Account '
     'angemeldet sein musst, um das Cloud\u00a0Pro-Modell zu verwenden.', 'pro_access_required'),
    ('Sign in with an iCloud+ account to use Cloud Pro.', 'pro_access_required'),
    ('Cloud Pro is currently unavailable.', 'pro_unavailable'),
    ('Das Cloud Pro-Modell ist nicht verfügbar.', 'pro_unavailable'),
    ('Cloud Pro daily limit reached.', 'pro_usage_limit'),
])
def test_auto_falls_back_once_on_pro_access_errors(runner, error, reason):
    paths = []
    payload = 'Exact task text\nZürich — grüezi'

    def invoke(args, **kwargs):
        if args[1] == 'list':
            return listing()
        source = Path(args[args.index('--input-path') + 1])
        target = Path(args[args.index('--output-path') + 1])
        paths.append(target)
        assert source.read_text() == payload
        if args[2] == 'Fruth PCC Pro':
            target.write_text('discard this partial Pro answer')
            return subprocess.CompletedProcess(args, 1, '', error)
        assert not paths[0].parent.exists()
        assert not target.exists()
        target.write_text('Cloud answer')
        return subprocess.CompletedProcess(args, 0, '', '')

    runner.side_effect = invoke
    result = pcc.run_pcc_text(payload)
    assert result['status'] == 'completed'
    assert result['model'] == 'cloud'
    assert result['output'] == 'Cloud answer'
    assert result['fallback_reason'] == reason
    assert [item['model'] for item in result['attempts']] == ['cloud-pro', 'cloud']
    assert result['attempts'][0]['stderr'] == error
    assert all('output' not in item for item in result['attempts'])
    assert runner.call_count == 3
    assert paths[0] != paths[1]
    assert all(not path.parent.exists() for path in paths)


@pytest.mark.parametrize('names', ['Fruth PCC\n', 'Fruth PCC\nFruth PCC Pro\nFruth PCC Pro\n'])
def test_auto_skips_unusable_pro_installation(runner, names):
    def invoke(args, **kwargs):
        if args[1] == 'list':
            return listing(names)
        assert args[2] == 'Fruth PCC'
        Path(args[args.index('--output-path') + 1]).write_text('Cloud answer')
        return subprocess.CompletedProcess(args, 0, '', '')

    runner.side_effect = invoke
    result = pcc.run_pcc_text('hello')
    assert result['status'] == 'completed'
    assert result['model'] == 'cloud'
    assert runner.call_count == 2


@pytest.mark.parametrize('fault', ['timeout', 'invalid_output', 'blocked', 'unknown_error', 'guardrail'])
def test_auto_does_not_fallback_for_non_availability_failures(runner, fault):
    def invoke(args, **kwargs):
        if args[1] == 'list':
            return listing()
        assert args[2] == 'Fruth PCC Pro'
        if fault == 'timeout':
            raise subprocess.TimeoutExpired(args, kwargs['timeout'])
        if fault == 'blocked':
            Path(args[args.index('--output-path') + 1]).write_text('BLOCKED: cannot fulfill this task')
        diagnostic = {'guardrail': 'Cloud Pro unavailable: safety guardrail refusal.',
                      'unknown_error': 'Your request could not be completed.'}.get(fault, '')
        return subprocess.CompletedProcess(args, int(bool(diagnostic)), '', diagnostic)

    runner.side_effect = invoke
    result = pcc.run_pcc_text('hello')
    assert result['status'] != 'completed'
    assert 'fallback_reason' not in result
    assert 'output' not in result
    assert len(result['attempts']) == 1
    assert runner.call_count == 2


def test_auto_reports_both_failures_without_looping(runner):
    runner.side_effect = [listing(),
        subprocess.CompletedProcess([], 1, '', 'Cloud Pro requires iCloud+.'),
        subprocess.CompletedProcess([], 1, '', 'Cloud daily limit reached.')]
    result = pcc.run_pcc_text('hello')
    assert result['status'] == 'shortcut_error'
    assert result['stderr'] == 'Cloud daily limit reached.'
    assert len(result['attempts']) == 2
    assert runner.call_count == 3


def test_auto_fallback_shares_original_deadline(runner, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(pcc.time, 'monotonic', lambda: now[0])

    def invoke(args, **kwargs):
        if args[1] == 'list':
            now[0] += 1
            return listing()
        if args[2] == 'Fruth PCC Pro':
            assert kwargs['timeout'] == 9
            now[0] += 3
            return subprocess.CompletedProcess(args, 1, '', 'Cloud Pro requires iCloud+.')
        assert kwargs['timeout'] == 6
        Path(args[args.index('--output-path') + 1]).write_text('Cloud answer')
        return subprocess.CompletedProcess(args, 0, '', '')

    runner.side_effect = invoke
    assert pcc.run_pcc_text('hello', timeout_sec=10)['status'] == 'completed'
    assert runner.call_count == 3


def test_cli_defaults_to_auto_without_model_flag(monkeypatch, tmp_path, capsys):
    task = tmp_path / 'task.txt'
    task.write_text('hello')
    execute = Mock(return_value={'status': 'completed', 'model': 'cloud', 'output': 'answer'})
    monkeypatch.setattr(pcc, 'run_pcc_text', execute)
    assert pcc.main(['run', '--input', str(task)]) == 0
    execute.assert_called_once_with('hello', model='auto', timeout_sec=pcc.PCC_SHORTCUT_TIMEOUT_SEC)
    assert 'answer' in capsys.readouterr().out
