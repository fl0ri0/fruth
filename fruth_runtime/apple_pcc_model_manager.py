"""Managed loopback PCC bridge; Apple's cloud services remain system-owned."""

from __future__ import annotations

from copy import deepcopy
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from functools import lru_cache
from pathlib import Path

import requests

from fruth_core.registry import read_registry_entries, write_registry_entries, pid_is_running
from fruth_core.start_policy import attach_start_audit, validate_start_source
from fruth_integrations.shortcuts.pcc import list_pcc_shortcuts
from fruth_runtime.apple_fm_model_manager import (
    APPLE_FM_PORT_MAX, process_identity, owns_listener, _terminate_child, _now,
)
from fruth_runtime.child_process_env import sanitized_child_process_env
from fruth_runtime.ollama_model_manager import find_free_port, is_port_listening
from fruth_runtime.runtime_log_hygiene import prepare_clean_runtime_log
from helpers.model_capabilities import build_registry_metadata

CONFIG_FILE = Path('model_ports.json')
LOG_DIR = Path('logs')
APPLE_PCC_START_PORT = APPLE_FM_PORT_MAX + 1
APPLE_PCC_PORT_MAX = APPLE_PCC_START_PORT + 49
APPLE_PCC_START_TIMEOUT_SEC = 30
APPLE_PCC_METADATA_TIMEOUT_SEC = 20
PROJECT_ROOT = Path(__file__).resolve().parents[1]
_shortcut_installation_observation = None


def shortcut_installation():
    """Explicit discovery; passive runtime snapshots must not invoke Shortcuts."""
    global _shortcut_installation_observation
    observation = {**list_pcc_shortcuts(timeout_sec=10), 'observed_at': _now()}
    _shortcut_installation_observation = deepcopy(observation)
    return observation


def describe_apple_pcc_runtime_probe(*, refresh=False):
    """Project installation evidence; only explicit discovery/start may refresh."""
    if refresh:
        installation = shortcut_installation()
    elif _shortcut_installation_observation is not None:
        installation = deepcopy(_shortcut_installation_observation)
    else:
        installation = {'status': 'not_observed', 'observed_at': None, 'models': []}
    ready = installation.get('status') == 'completed' and any(
        item.get('installation') == 'installed' for item in installation.get('models', []))
    unobserved = installation.get('status') == 'not_observed'
    if ready:
        runtime_state, issues = 'runnable', []
    elif unobserved:
        runtime_state = 'degraded'
        issues = ['PCC shortcut installation has not been checked. Discover the model catalog or explicitly start PCC to check it.']
    else:
        runtime_state = 'missing'
        issues = ['Install Fruth PCC and/or Fruth PCC Pro in macOS Shortcuts. '
                  + str(installation.get('stderr') or installation.get('error') or '')]
    return {'runtime_state': runtime_state,
            'detection': {'source': 'shortcuts_cli_list', 'cloud_access': 'checked_on_execution',
                          **installation, 'cached': not refresh},
            'issues': issues,
            'operations': {'discover': True, 'start_instance': ready, 'stop_instance': True,
                           'pull_model': False, 'remove_model': False}}


@lru_cache(maxsize=1)
def pcc_sdk_metadata():
    observation = {'source': 'FoundationModels.PrivateCloudComputeLanguageModel',
                   'scope': 'sdk_default_not_shortcuts_tier', 'observed_at': _now(),
                   'os_version': platform.mac_ver()[0], 'status': 'unsupported_os',
                   'model_variant': None, 'variant_selection': False}
    if platform.system() != 'Darwin' or not shutil.which('xcrun'):
        return observation
    try:
        run = subprocess.run(['xcrun', 'swift', str(Path(__file__).with_name('apple_pcc_metadata.swift'))],
                             capture_output=True, text=True, stdin=subprocess.DEVNULL,
                             timeout=APPLE_PCC_METADATA_TIMEOUT_SEC, env=sanitized_child_process_env())
        if run.returncode:
            raise ValueError(run.stderr.strip())
        data = json.loads(run.stdout)
        if not isinstance(data, dict) or data.get('status') not in {'available', 'unavailable', 'unsupported_os'}:
            raise ValueError('Invalid PCC SDK observation.')
        if data['status'] == 'available' and (type(data.get('context_size')) is not int or data['context_size'] <= 0):
            raise ValueError('A positive SDK context size is required.')
        return {**observation, **data}
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return {**observation, 'status': 'probe_unavailable', 'observation_error': str(exc)}


def transport_metadata(*, vision=True):
    return {'source': 'fruth_shortcuts_bridge', 'backend_package': 'macos_shortcuts',
            'backend_contract': 'shortcuts.pcc.chat_completions', 'api_model': 'auto',
            'model_selection': 'cloud_pro_then_cloud', 'model_variant': None,
            'model_revision': None, 'context_size': None, 'stream_content': 'buffered_final',
            'supported_parameters': [], 'input_modalities': ['text', 'image'] if vision else ['text'],
            'output_modalities': ['text'],
            'message_transport': 'text_role_envelope', 'inference_cancellation': 'unverified',
            'execution_location': 'apple_private_cloud_compute'}


def list_available_apple_pcc_models():
    probe = describe_apple_pcc_runtime_probe(refresh=True)
    metadata = transport_metadata()
    description = 'Apple Private Cloud Compute. Text + image analysis. Pro preferred; Cloud fallback. Sends task text, attached images and selected context to Apple.'
    if probe['runtime_state'] == 'runnable':
        sdk = pcc_sdk_metadata()
        metadata['sdk_model'] = sdk
        if sdk.get('status') == 'available':
            description += f" SDK reports {sdk['context_size']:,} tokens; Shortcuts limit unreported."
    item = {'name': 'auto', 'model': 'auto', 'display_name': 'Apple PCC', 'request_model': 'auto',
            'model_source': 'apple_private_cloud_compute', 'runnable': probe['runtime_state'] == 'runnable',
            'disabled_reason': '; '.join(probe['issues']) or None, 'description': description,
            'removable': False, 'provider_capabilities': ['chat', 'vision_analysis'],
            'inputs': ['text', 'image'], 'outputs': ['text'],
            'backend_metadata': metadata}
    return [{**item, **build_registry_metadata('auto', 'apple_pcc', 'chat', metadata=item)}]


def server_metadata(port):
    base = f'http://127.0.0.1:{port}'
    response = requests.get(base + '/health', timeout=2)
    response.raise_for_status()
    health = response.json()
    if health.get('backend') != 'apple_pcc' or health.get('transport_ready') is not True:
        raise RuntimeError('Listener is not a ready Fruth PCC bridge.')
    response = requests.get(base + '/v1/models', timeout=2)
    response.raise_for_status()
    models = response.json().get('data', [])
    if not any(m.get('id') == 'auto' and m.get('owned_by') == 'apple_pcc' for m in models if isinstance(m, dict)):
        raise RuntimeError('PCC bridge model identity mismatch.')
    # An already-running text-only adapter must not inherit new code's vision claim.
    return {**transport_metadata(vision='image' in (health.get('input_modalities') or [])),
            'observed_at': _now(), 'transport_ready': True,
            'cloud_access': health.get('cloud_access'), 'last_execution': health.get('last_execution')}


def _next_free_port(preferred_port=None):
    used = {int(e['port']) for e in read_registry_entries(CONFIG_FILE) if str(e.get('port', '')).isdigit()}
    if preferred_port is not None:
        if not APPLE_PCC_START_PORT <= preferred_port <= APPLE_PCC_PORT_MAX:
            raise ValueError(f'PCC port must be in {APPLE_PCC_START_PORT}–{APPLE_PCC_PORT_MAX}.')
        if preferred_port in used or is_port_listening(preferred_port):
            raise RuntimeError(f'PCC port {preferred_port} is occupied or reserved.')
        return preferred_port
    return find_free_port(APPLE_PCC_START_PORT, APPLE_PCC_PORT_MAX + 1, used)


def _server_command(port):
    return [sys.executable, '-m', 'fruth_integrations.shortcuts.server', '--port', str(port)]


def start_apple_pcc_instance(model_name, *, preferred_port=None, capability='chat', start_source=None):
    source = validate_start_source(start_source, context='apple_pcc_start_model')
    if model_name != 'auto' or capability not in (None, 'chat', 'vision_analysis'):
        raise ValueError('Apple PCC supports auto with chat and vision_analysis.')
    probe = describe_apple_pcc_runtime_probe(refresh=True)
    if probe['runtime_state'] != 'runnable':
        raise RuntimeError('; '.join(probe['issues']))
    sdk = pcc_sdk_metadata()
    port = _next_free_port(preferred_port)
    instance_id = f'apple_pcc:auto:{port}'
    log = LOG_DIR / f'apple_pcc_auto_{port}.log'
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    prepare_clean_runtime_log(log, metadata={'backend': 'apple_pcc', 'instance_id': instance_id, 'port': port})
    cmd = _server_command(port)
    child = None
    try:
        with log.open('wb') as handle:
            child = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=handle, stderr=subprocess.STDOUT,
                                     start_new_session=True, cwd=PROJECT_ROOT, env=sanitized_child_process_env())
        identity = process_identity(child.pid)
        if not identity:
            raise RuntimeError('Could not establish ownership of the PCC bridge process.')
        deadline = time.monotonic() + APPLE_PCC_START_TIMEOUT_SEC
        while child.poll() is None and time.monotonic() < deadline:
            try:
                if not owns_listener(child.pid, port):
                    time.sleep(.1)
                    continue
                metadata = {**server_metadata(port), 'sdk_model': sdk}
                # Framework Python can re-exec after Popen. Record its final
                # identity only once this child owns the ready bridge listener.
                identity = process_identity(child.pid)
                if not identity or child.poll() is not None:
                    raise RuntimeError('PCC bridge exited before registry publication.')
                instance = {'instance_id': instance_id, 'model': 'auto', 'request_model': 'auto',
                            'display_name': 'Apple PCC', 'port': port, 'pid': child.pid, 'log': str(log),
                            'process_identity': identity, 'server_command': cmd, 'backend_metadata': metadata,
                            'provider_capabilities': ['chat', 'vision_analysis'] if 'image' in metadata['input_modalities'] else ['chat'],
                            'inputs': metadata['input_modalities'], 'outputs': ['text']}
                instance.update(build_registry_metadata('auto', 'apple_pcc', capability or 'chat', metadata=instance))
                instance = attach_start_audit(instance, start_source=source, context='apple_pcc_start_model')
                write_registry_entries([*read_registry_entries(CONFIG_FILE), instance], path=CONFIG_FILE)
                if not any(e.get('instance_id') == instance_id and e.get('pid') == child.pid
                           for e in read_registry_entries(CONFIG_FILE)):
                    raise RuntimeError('PCC registry publication failed.')
                return instance
            except requests.RequestException:
                time.sleep(.1)
        raise RuntimeError(f'PCC bridge failed to start. See {log}.')
    except BaseException:
        if child is not None:
            _terminate_child(child)
            current = read_registry_entries(CONFIG_FILE)
            kept = [e for e in current if not (e.get('instance_id') == instance_id and e.get('pid') == child.pid)]
            if kept != current:
                write_registry_entries(kept, path=CONFIG_FILE)
        raise


def stop_apple_pcc_instance(instance_id, *, config_path=None):
    path = config_path or CONFIG_FILE
    target = next((e for e in read_registry_entries(path)
                   if e.get('instance_id') == instance_id and e.get('backend') == 'apple_pcc'), None)
    if target is None:
        return False, None
    pid = target.get('pid')
    if pid and pid_is_running(pid):
        expected, command = target.get('process_identity'), target.get('server_command')
        if (not expected or process_identity(pid) != expected or not isinstance(command, list)
                or len(command) != 5 or command[1:] != _server_command(target.get('port'))[1:]
                # macOS may report the framework executable instead of the
                # venv symlink. The complete recorded identity must still match;
                # independently verify this bridge's exact module/port arguments.
                or not expected.endswith(' ' + ' '.join(command[1:]))):
            raise RuntimeError('PCC process ownership cannot be verified; no process was stopped.')
        os.kill(pid, 15)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and process_identity(pid) == expected:
            try:
                if os.waitpid(pid, os.WNOHANG)[0]:
                    break
            except ChildProcessError:
                pass
            time.sleep(.1)
        if process_identity(pid) == expected:
            return False, target
    current = read_registry_entries(path)
    write_registry_entries([e for e in current if not (e.get('instance_id') == instance_id and e.get('pid') == pid)], path=path)
    return not any(e.get('instance_id') == instance_id for e in read_registry_entries(path)), target
