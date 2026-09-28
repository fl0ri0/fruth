"""First-use assistance is explicit and does not install or start a model."""

import subprocess
from unittest.mock import Mock

import pytest

from fruth_core.lifecycle import StartModelRequestError
from fruth_integrations.shortcuts import setup
from fruth_runtime import apple_pcc_model_manager as pcc
from fruth_server.model_control_runtime import ModelControlRuntimeOwner
from scripts import startup_model_manager as startup


def observation(cloud='missing', pro='missing'):
    return {'status': 'completed', 'models': [
        {'shortcut': name, 'installation': status}
        for name, status in zip(setup.PCC_SHORTCUTS.values(), [cloud, pro])]}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(setup, 'BUNDLED_SHORTCUTS_DIR', tmp_path)
    for name in setup.PCC_SHORTCUTS.values():
        (tmp_path / f'{name}.shortcut').write_bytes(b'test fixture, never opened')
    monkeypatch.setattr(setup.sys, 'platform', 'darwin')
    monkeypatch.setattr(setup, 'list_pcc_shortcuts', Mock(return_value=observation()))
    monkeypatch.setattr(setup.subprocess, 'run', Mock(return_value=Mock(returncode=0, stderr='')))
    monkeypatch.setattr(pcc, '_shortcut_installation_observation', None)
    monkeypatch.setattr(pcc, 'pcc_sdk_metadata', Mock(return_value={'status': 'unsupported_os'}))


@pytest.mark.parametrize('cloud,pro,expected', [
    ('missing', 'missing', ['Fruth PCC', 'Fruth PCC Pro']),
    ('installed', 'missing', ['Fruth PCC Pro']),
    ('missing', 'installed', ['Fruth PCC']),
    ('ambiguous', 'missing', ['Fruth PCC Pro']),
])
def test_explicit_setup_opens_only_missing_bundled_files(cloud, pro, expected):
    setup.list_pcc_shortcuts.return_value = observation(cloud, pro)
    result = setup.open_pcc_shortcut_imports()
    assert result['status'] == 'setup_required'
    assert result['opened_shortcuts'] == expected
    assert 'Add Shortcut' in result['message']
    setup.list_pcc_shortcuts.assert_called_once_with(timeout_sec=setup.PCC_SETUP_TIMEOUT_SEC)
    call = setup.subprocess.run.call_args
    assert call.args[0] == ['/usr/bin/open', '-a', 'Shortcuts', *[
        str(setup.BUNDLED_SHORTCUTS_DIR / f'{name}.shortcut') for name in expected]]
    assert call.kwargs['timeout'] == setup.PCC_SETUP_TIMEOUT_SEC
    assert call.kwargs['stdin'] == subprocess.DEVNULL
    if cloud == 'ambiguous':
        assert 'duplicate' in result['message']


def test_existing_shortcuts_need_no_import():
    setup.list_pcc_shortcuts.return_value = observation('installed', 'installed')
    assert setup.open_pcc_shortcut_imports()['status'] == 'setup_complete'
    setup.subprocess.run.assert_not_called()


@pytest.mark.parametrize('listing', [
    observation('ambiguous', 'installed'), observation('ambiguous', 'ambiguous'),
    {'status': 'timeout', 'error': 'Cannot check shortcuts'},
    {'status': 'completed', 'models': []},
])
def test_uncertain_or_ambiguous_installation_never_claims_completion(listing):
    setup.list_pcc_shortcuts.return_value = listing
    result = setup.open_pcc_shortcut_imports()
    assert result['status'] == 'setup_unavailable' and result['error']
    setup.subprocess.run.assert_not_called()


def test_missing_package_files_leave_manual_recovery():
    (setup.BUNDLED_SHORTCUTS_DIR / 'Fruth PCC.shortcut').unlink()
    assert not setup.pcc_setup_available(observation())
    result = setup.open_pcc_shortcut_imports()
    assert result['status'] == 'setup_unavailable'
    assert 'README.md' in result['error']
    setup.subprocess.run.assert_not_called()


def test_non_mac_does_not_query_or_open_shortcuts(monkeypatch):
    monkeypatch.setattr(setup.sys, 'platform', 'linux')
    assert not setup.pcc_setup_available(observation())
    assert setup.open_pcc_shortcut_imports()['status'] == 'setup_unavailable'
    setup.list_pcc_shortcuts.assert_not_called()
    setup.subprocess.run.assert_not_called()


@pytest.mark.parametrize('failure', [OSError('no desktop'), subprocess.TimeoutExpired('open', 10), None])
def test_native_open_failure_remains_an_error(failure):
    setup.subprocess.run.side_effect = failure
    setup.subprocess.run.return_value = Mock(returncode=1, stderr='Cannot open')
    assert setup.open_pcc_shortcut_imports()['status'] == 'setup_unavailable'


def test_catalog_advertises_setup_without_readiness_or_native_launch(monkeypatch):
    monkeypatch.setattr(pcc, 'list_pcc_shortcuts', Mock(side_effect=[
        observation(), observation('installed', 'installed')]))
    assert setup.pcc_setup_available(observation())
    setup.list_pcc_shortcuts.assert_not_called()
    before = pcc.list_available_apple_pcc_models()[0]
    assert before['setup_available'] is True and before['runnable'] is False
    assert pcc.describe_apple_pcc_runtime_probe()['operations']['start_instance'] is False
    after = pcc.list_available_apple_pcc_models()[0]
    assert after['setup_available'] is False and after['runnable'] is True
    setup.subprocess.run.assert_not_called()


@pytest.fixture
def owner(monkeypatch):
    hooks = {name: Mock() for name in (
        'start_instance', 'record_instance_started', 'runtime_status_path_getter',
        'log_unified_event', 'log_runtime_status_transition', 'load_running_instances',
        'merge_instances_with_runtime_status', 'instance_supports_capability')}
    hooks.update(canonical_model_name=lambda data: data['model'], normalize_backend=lambda v: v,
                 normalize_capability=lambda v: v, start_model_request_error=StartModelRequestError,
                 infer_capability=lambda *args: 'chat')
    hooks['start_instance'].return_value = {'model': 'auto', 'backend': 'apple_pcc', 'capability': 'chat'}
    hooks['record_instance_started'].return_value = (None, {})
    monkeypatch.setattr(setup, 'open_pcc_shortcut_imports', Mock(return_value={
        'status': 'setup_required', 'message': 'Add Shortcut on this Mac.'}))
    return ModelControlRuntimeOwner(hooks)


@pytest.mark.parametrize('result,code', [
    ({'status': 'setup_required', 'message': 'Add Shortcut.'}, 200),
    ({'status': 'setup_complete', 'message': 'Already installed. Select Start.'}, 200),
    ({'status': 'setup_unavailable', 'error': 'No desktop session.'}, 409),
])
def test_setup_api_returns_truth_without_runtime_mutation(owner, result, code):
    setup.open_pcc_shortcut_imports.return_value = result
    data, status = owner.start_model_response({
        'model': 'auto', 'backend': 'apple_pcc', 'setup_shortcuts': True, 'start_source': 'frontend_button'})
    assert status == code and data['status'] == result['status']
    assert 'instance' not in data and 'start_audit' not in data
    setup.open_pcc_shortcut_imports.assert_called_once_with()
    for name in ('start_instance', 'record_instance_started', 'load_running_instances',
                 'merge_instances_with_runtime_status', 'log_runtime_status_transition'):
        owner.hooks[name].assert_not_called()


@pytest.mark.parametrize('overrides', [
    {'start_source': 'api_start_model'}, {'start_source': 'startup_policy'},
    {'start_source': 'inference_route'}, {'backend': 'apple_fm'},
    {'model': 'system'}, {'setup_shortcuts': 'true'}, {'setup_shortcuts': False},
])
def test_setup_requires_explicit_pcc_button_intent(owner, overrides):
    data, status = owner.start_model_response({
        'model': 'auto', 'backend': 'apple_pcc', 'setup_shortcuts': True,
        'start_source': 'frontend_button', **overrides})
    assert status == 400 and data['error']
    setup.open_pcc_shortcut_imports.assert_not_called()
    owner.hooks['start_instance'].assert_not_called()


def test_ordinary_start_does_not_open_imports(owner):
    data, status = owner.start_model_response({
        'model': 'auto', 'backend': 'apple_pcc', 'force_start': True, 'start_source': 'frontend_button'})
    assert status == 200 and data['status'] == 'started'
    setup.open_pcc_shortcut_imports.assert_not_called()
    owner.hooks['start_instance'].assert_called_once()


def test_startup_catalog_keeps_setup_candidate_distinct_from_runnable(monkeypatch):
    monkeypatch.setattr(pcc, 'list_available_apple_pcc_models', Mock(return_value=[
        {'runnable': False, 'setup_available': True}]))
    entries = startup._discover_apple_pcc_entries()
    assert len(entries) == 1 and entries[0].setup_required
    pcc.list_available_apple_pcc_models.return_value = [{'runnable': False, 'setup_available': False}]
    assert startup._discover_apple_pcc_entries() == []


@pytest.mark.parametrize('interactive,answer,ready', [
    (False, '', False), (True, '', True), (True, 'skip', False), (True, EOFError(), False),
])
def test_terminal_setup_needs_interactive_acknowledgment(monkeypatch, interactive, answer, ready):
    monkeypatch.setattr(startup.sys.stdin, 'isatty', lambda: interactive)
    open_imports = Mock(return_value={'status': 'setup_required', 'opened_shortcuts': ['Fruth PCC']})
    monkeypatch.setattr(setup, 'open_pcc_shortcut_imports', open_imports)
    user_input = Mock(side_effect=answer) if isinstance(answer, Exception) else Mock(return_value=answer)
    monkeypatch.setattr('builtins.input', user_input)
    assert startup._prepare_pcc_shortcuts() is ready
    assert open_imports.call_count == int(interactive)
    assert user_input.call_count == int(interactive)


@pytest.mark.parametrize('proceed', [True, False])
def test_selected_startup_setup_uses_existing_lifecycle_recheck(monkeypatch, proceed):
    from fruth_core import lifecycle
    entry = startup.CatalogEntry('apple_pcc', 'auto', 'Apple PCC', 'chat', 'Chat', 'cloud', setup_required=True)
    monkeypatch.setattr(startup, '_read_active_runtime_entries', lambda: ([], False))
    monkeypatch.setattr(startup, 'initialize_instance_counters', Mock())
    monkeypatch.setattr(startup, '_discover_catalog', lambda: [entry])
    monkeypatch.setattr(startup, '_prompt_selection', lambda _: [entry])
    monkeypatch.setattr(startup, '_prepare_pcc_shortcuts', Mock(return_value=proceed))
    monkeypatch.setattr(startup, '_write_registry_once', Mock())
    monkeypatch.setattr(startup, 'cleanup_runtime_hygiene', Mock(return_value={}))
    monkeypatch.setattr(startup, 'is_port_listening', lambda _: False)
    start = Mock(side_effect=RuntimeError('Shortcut still missing after user dismissed preview'))
    monkeypatch.setattr(lifecycle, 'start_instance', start)
    assert startup.main() == 0
    if proceed:
        start.assert_called_once_with('auto', 'apple_pcc', 'chat', start_source='startup_policy')
    else:
        start.assert_not_called()
