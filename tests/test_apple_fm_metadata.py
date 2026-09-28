"""Optional native metadata cannot change serving identity or backend readiness."""
import json
import subprocess
from unittest.mock import Mock

import pytest

from fruth_runtime import apple_fm_model_manager as fm
from scripts import startup_model_manager


@pytest.fixture
def native_probe(monkeypatch):
    fm.system_model_metadata.cache_clear()
    monkeypatch.setattr(fm.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(fm.platform, 'mac_ver', lambda: ('27.0', (), 'arm64'))
    monkeypatch.setattr(fm.shutil, 'which', lambda name: '/usr/bin/' + name)
    run = Mock(return_value=Mock(returncode=0, stdout=json.dumps({
        'status': 'available', 'availability': 'available', 'model_variant': 'coreAdvanced3',
        'display_name': 'AFM 3 Core Advanced', 'context_size': 8192}), stderr=''))
    monkeypatch.setattr(fm.subprocess, 'run', run)
    yield run
    fm.system_model_metadata.cache_clear()


@pytest.mark.parametrize('variant,name', [('core3', 'AFM 3 Core'),
    ('coreAdvanced3', 'AFM 3 Core Advanced'), ('unknown', 'A future AFM')])
def test_native_identity_and_context_are_sourced_cached_and_bounded(native_probe, monkeypatch, variant, name):
    monkeypatch.setenv('FRUTH_GRAPH_REBASE_OPERATOR_TOKEN', 'private-test-credential')
    native_probe.return_value.stdout = json.dumps({'status': 'available', 'availability': 'available',
        'display_name': name, 'model_variant': variant, 'context_size': 8192})
    info = fm.system_model_metadata()
    assert info['model_variant'] == variant and info['display_name'] == name
    assert info['context_size'] == 8192 and info['scope'] == 'host_default_model'
    assert info['source'] == 'FoundationModels.SystemLanguageModel.default'
    assert info['observed_at'] and info['os_version'] == '27.0'
    assert fm.system_model_metadata() == info
    native_probe.assert_called_once()
    args, kwargs = native_probe.call_args
    assert args[0][:2] == ['/usr/bin/xcrun', 'swift']
    assert args[0][-1].endswith('apple_fm_metadata.swift')
    assert kwargs['timeout'] == fm.APPLE_FM_METADATA_TIMEOUT_SEC
    assert kwargs['stdin'] == subprocess.DEVNULL
    assert 'FRUTH_GRAPH_REBASE_OPERATOR_TOKEN' not in kwargs['env']


@pytest.mark.parametrize('payload', ['not JSON', '[]', '{"status":{}}',
    '{"status":"available","display_name":"AFM 3 Core","model_variant":"core3","context_size":0}',
    '{"status":"available","display_name":"AFM","model_variant":{},"context_size":8192}',
    '{"status":"available","display_name":"AFM","model_variant":"core3","context_size":true}'])
def test_invalid_or_restricted_metadata_remains_unknown(native_probe, payload):
    native_probe.return_value.stdout = payload
    info = fm.system_model_metadata()
    assert info['status'] == 'probe_unavailable' and info['observation_error']
    assert 'context_size' not in info and 'model_variant' not in info


@pytest.mark.parametrize('failure', ['old_sdk', 'missing_process', 'timeout'])
def test_optional_probe_failure_is_not_backend_unavailability(native_probe, failure):
    if failure == 'old_sdk':
        native_probe.return_value.returncode = 1
        native_probe.return_value.stderr = 'value has no member variant'
    else:
        native_probe.side_effect = (OSError('not found') if failure == 'missing_process'
                                    else subprocess.TimeoutExpired('swift', 20))
    info = fm.system_model_metadata()
    assert info['status'] == 'probe_unavailable' and info['observation_error']


@pytest.mark.parametrize('platform,version,tool', [('Linux', '', True), ('Darwin', '26.5', True),
                                                ('Darwin', '27.0', False)])
def test_unsupported_host_or_missing_tool_does_not_launch(native_probe, monkeypatch, platform, version, tool):
    monkeypatch.setattr(fm.platform, 'system', lambda: platform)
    monkeypatch.setattr(fm.platform, 'mac_ver', lambda: (version, (), 'arm64'))
    if not tool:
        monkeypatch.setattr(fm.shutil, 'which', lambda name: None)
    assert fm.system_model_metadata()['status'] in ('unsupported_os', 'probe_unavailable')
    native_probe.assert_not_called()


def test_unavailable_model_has_no_guessed_variant(native_probe):
    native_probe.return_value.stdout = '{"status":"unavailable","availability":"modelNotReady"}'
    info = fm.system_model_metadata()
    assert info['status'] == 'unavailable' and info['availability'] == 'modelNotReady'
    assert 'model_variant' not in info


@pytest.mark.parametrize('valid', [True, False])
def test_discovery_and_startup_show_host_metadata_without_changing_api_model(native_probe, monkeypatch, valid):
    if not valid:
        native_probe.return_value.returncode = 1
    monkeypatch.setattr(fm, 'resolve_fm_bin', lambda: '/usr/bin/fm')
    monkeypatch.setattr(fm, '_diagnostic', lambda binary, command, *args: (
        0, 'Agreed to license' if command == 'license' else 'system model available'))
    entry = fm.list_available_apple_fm_models()[0]
    startup = startup_model_manager._discover_apple_fm_entries()[0]
    assert entry['runnable'] and startup.model_name == entry['request_model'] == entry['name'] == 'system'
    assert entry['backend_metadata']['context_size'] is None
    assert entry['backend_metadata']['model_variant'] is None
    assert startup.details == 'On-device text + image analysis'
    if valid:
        assert startup.display_label == entry['display_name'] == 'AFM 3 Core Advanced'
        assert 'Mac default: AFM 3 Core Advanced; 8,192-token context' in entry['description']
    else:
        assert startup.display_label == 'AFM' and 'unavailable' in entry['description']
    native_probe.assert_called_once()


def test_http_observation_does_not_query_host_or_claim_its_variant(monkeypatch):
    probe = Mock(side_effect=AssertionError('HTTP observation must remain independent'))
    monkeypatch.setattr(fm, 'system_model_metadata', probe)
    health = Mock()
    health.json.return_value = {'models': [{'name': 'system', 'available': True}]}
    models = Mock()
    models.json.return_value = {'data': [{'id': 'system'}]}
    monkeypatch.setattr(fm.requests, 'get', Mock(side_effect=[health, models]))
    info = fm.server_metadata(11602)
    assert info['model_variant'] is None and info['context_size'] is None
    assert info['source'] == 'fm_serve_http'
    probe.assert_not_called()


def test_readiness_probe_does_not_launch_swift(native_probe, monkeypatch):
    monkeypatch.setattr(fm, 'resolve_fm_bin', lambda: '/usr/bin/fm')
    monkeypatch.setattr(fm, '_diagnostic', lambda binary, command, *args: (
        0, 'Agreed to license' if command == 'license' else 'system model available'))
    assert fm.describe_apple_fm_runtime_probe()['runtime_state'] == 'runnable'
    native_probe.assert_not_called()
