"""Local Apple Foundation Models CLI lifecycle; no SDK inference or system-service control."""

from __future__ import annotations

import datetime as dt
import json
import os
import platform
import re
import shutil
import subprocess
import time
from functools import lru_cache
from pathlib import Path

import requests

from fruth_core.registry import read_registry_entries, write_registry_entries, pid_is_running
from fruth_core.start_policy import attach_start_audit, validate_start_source
from fruth_runtime.child_process_env import sanitized_child_process_env
from fruth_runtime.llama_cpp_model_manager import LLAMA_CPP_PORT_MAX
from fruth_runtime.ollama_model_manager import find_free_port, is_port_listening
from fruth_runtime.runtime_log_hygiene import prepare_clean_runtime_log
from helpers.model_capabilities import build_registry_metadata

CONFIG_FILE = Path('model_ports.json')
LOG_DIR = Path('logs')
APPLE_FM_START_PORT = LLAMA_CPP_PORT_MAX + 1
APPLE_FM_PORT_MAX = APPLE_FM_START_PORT + 49
APPLE_FM_START_TIMEOUT_SEC = 30
APPLE_FM_CAPABILITIES = ('chat', 'vision_analysis')
APPLE_FM_METADATA_TIMEOUT_SEC = 20


class AppleFMUnavailable(RuntimeError):
    pass


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def resolve_fm_bin():
    return shutil.which('fm') if platform.system() == 'Darwin' else None


def _diagnostic(binary, *args):
    result = subprocess.run([binary, *args], capture_output=True, text=True,
                            stdin=subprocess.DEVNULL, timeout=10,
                            env=sanitized_child_process_env())
    return result.returncode, re.sub(r'\x1b\[[0-9;]*m', '', result.stdout + result.stderr).strip()


@lru_cache(maxsize=1)
def system_model_metadata():
    """Optional host-default observation, cached until this Fruth process exits.

    This is not a query of an fm HTTP instance. Keep it under its own source
    instead of promoting it into the server's context limit or variant fields.
    """
    observation = {'source': 'FoundationModels.SystemLanguageModel.default',
                   'scope': 'host_default_model', 'observed_at': _now(),
                   'os_version': platform.mac_ver()[0], 'status': 'unsupported_os'}
    major_version = observation['os_version'].split('.')[0]
    if platform.system() != 'Darwin' or not major_version.isdigit() or int(major_version) < 27:
        return observation
    binary = shutil.which('xcrun')
    if not binary:
        return {**observation, 'status': 'probe_unavailable',
                'observation_error': 'xcrun is not installed; model metadata requires the macOS 27 SDK.'}
    try:
        # Reuse Swift's normal SDK module cache across Fruth launches. A private
        # empty cache would rebuild the SDK on every startup (~19s on the test Mac).
        result = subprocess.run(
            [binary, 'swift', str(Path(__file__).with_name('apple_fm_metadata.swift'))],
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=APPLE_FM_METADATA_TIMEOUT_SEC,
            env=sanitized_child_process_env(),
        )
        if result.returncode:
            raise ValueError('Swift metadata query failed (macOS 27 SDK and system-service access required): '
                             + result.stderr.strip()[-1000:])
        payload = json.loads(result.stdout)
        if not isinstance(payload, dict) or payload.get('status') not in ('available', 'unavailable', 'unsupported_os'):
            raise ValueError('Invalid Swift model metadata result.')
        observation['status'] = payload['status']
        observation['availability'] = str(payload.get('availability') or '')
        if payload['status'] == 'available':
            context = payload.get('context_size')
            name = payload.get('display_name')
            variant = payload.get('model_variant')
            if (type(context) is not int or context <= 0 or not isinstance(name, str) or not name.strip()
                    or variant not in ('core3', 'coreAdvanced3', 'unknown')):
                # Restricted system-service access can report an available Core 3
                # with zero context. Preserve the diagnostic, not a usable identity.
                observation['reported_model'] = payload
                raise ValueError('Incomplete model metadata; a positive context size and variant display name are required.')
            observation.update(display_name=name.strip(), model_variant=variant, context_size=context)
        return observation
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return {**observation, 'status': 'probe_unavailable', 'observation_error': str(exc)}


def describe_apple_fm_runtime_probe():
    """Read-only CLI diagnostics; never accept a license, launch or download."""
    binary = resolve_fm_bin()
    detection = {'binary': binary, 'observed_at': _now(), 'source': 'fm_cli_diagnostics',
                 'platform': platform.system(), 'license_ready': None, 'model_available': None}
    issues = []
    state = 'missing'
    if platform.system() != 'Darwin':
        issues.append('Apple Foundation Models requires macOS with Apple Intelligence.')
    elif not binary:
        issues.append('fm CLI not found on PATH. Install a macOS version that supplies fm serve.')
    else:
        state = 'degraded'
        try:
            code, message = _diagnostic(binary, 'license', '--status')
            detection['license_status'] = message
            detection['license_ready'] = code == 0 and message.lower().startswith('agreed to license')
            if not detection['license_ready']:
                issues.append('Review and accept the Apple CLI license yourself using fm license. ' + message)
            else:
                code, message = _diagnostic(binary, 'available', '--model', 'system')
                detection['availability_status'] = message
                detection['model_available'] = code == 0 and message.lower() == 'system model available'
                if detection['model_available']:
                    state = 'runnable'
                else:
                    issues.append('Apple system model unavailable: ' + message)
        except (OSError, subprocess.SubprocessError) as exc:
            issues.append(f'fm readiness could not be determined: {exc}')
    return {'runtime_state': state, 'detection': detection, 'issues': issues,
            'operations': {'discover': True, 'start_instance': state == 'runnable',
                           'stop_instance': True, 'pull_model': False, 'remove_model': False}}


def transport_metadata():
    # This is the observed CLI transport contract, not an independently queried framework model.
    return {'source': 'fm_serve_http_contract', 'contract_observed_at': '2026-09-20',
            'backend_package': 'fm', 'backend_contract': 'fm.serve.chat_completions',
            'api_model': 'system', 'model_variant': None, 'model_revision': None,
            'context_size': None, 'variant_selection': False, 'stream_content': 'delta',
            'supported_parameters': ['temperature', 'top_p', 'max_completion_tokens'],
            'input_modalities': ['text', 'image'], 'output_modalities': ['text'],
            'image_transport': 'inline_image_url',
            'roles': ['system', 'user', 'assistant'], 'inference_cancellation': 'unverified'}


def list_available_apple_fm_models():
    probe = describe_apple_fm_runtime_probe()
    metadata = transport_metadata()
    system_model = system_model_metadata() if probe['runtime_state'] == 'runnable' else None
    display_name = 'AFM'
    description = 'On-device text generation and image analysis. Variant and context size unavailable.'
    if system_model:
        probe['detection']['system_model'] = system_model
        metadata['system_model'] = system_model
        if system_model.get('status') == 'available':
            display_name = system_model['display_name']
            description = (f"On-device text + image analysis. Mac default: {display_name}; "
                           f"{system_model['context_size']:,}-token context.")
    item = {'name': 'system', 'display_name': display_name, 'model': 'system', 'request_model': 'system',
            'model_source': 'apple_system', 'runnable': probe['runtime_state'] == 'runnable',
            'disabled_reason': '; '.join(probe['issues']) or None,
            'description': description,
            'provider_capabilities': list(APPLE_FM_CAPABILITIES), 'inputs': ['text', 'image'], 'outputs': ['text'],
            'backend_package': 'fm', 'backend_contract': 'fm.serve.chat_completions',
            'backend_metadata': metadata, 'availability': probe['detection'],
            'removable': False}
    item.update(build_registry_metadata('system', 'apple_fm', 'chat', metadata=item))
    return [item]


def server_metadata(port):
    """Attribute only information obtained from this exact server's endpoints."""
    base = f'http://127.0.0.1:{port}'
    health = requests.get(base + '/health', timeout=2)
    health.raise_for_status()
    payload = health.json()
    if not any(m.get('name') == 'system' and m.get('available') is True
               for m in payload.get('models', []) if isinstance(m, dict)):
        raise AppleFMUnavailable('fm server reports system model unavailable.')
    response = requests.get(base + '/v1/models', timeout=2)
    response.raise_for_status()
    models = response.json().get('data', [])
    model = next((m for m in models if isinstance(m, dict) and m.get('id') == 'system'), None)
    if model is None:
        raise RuntimeError('fm server does not advertise the system API model.')
    return {**transport_metadata(), 'source': 'fm_serve_http', 'observed_at': _now(),
            'models_url': base + '/v1/models', 'health_url': base + '/health',
            'reported_model': model, 'model_available': True}


def process_identity(pid):
    """Birth time and full command protect against stale/reused PIDs after reload."""
    result = subprocess.run(['ps', '-ww', '-p', str(pid), '-o', 'lstart=', '-o', 'command='],
                            capture_output=True, text=True, timeout=5,
                            env=sanitized_child_process_env())
    return result.stdout.strip() if result.returncode == 0 else ''


def owns_listener(pid, port):
    result = subprocess.run(['/usr/sbin/lsof', '-nP', '-a', '-p', str(pid),
                             '-iTCP:' + str(port), '-sTCP:LISTEN', '-Fp'],
                            capture_output=True, text=True, timeout=5,
                            env=sanitized_child_process_env())
    return result.returncode == 0 and f'p{pid}' in result.stdout.splitlines()


def _next_free_port(preferred_port=None):
    used = {int(e['port']) for e in read_registry_entries(CONFIG_FILE) if str(e.get('port', '')).isdigit()}
    if preferred_port is not None:
        if not APPLE_FM_START_PORT <= preferred_port <= APPLE_FM_PORT_MAX:
            raise ValueError(f'AFM port must be in {APPLE_FM_START_PORT}–{APPLE_FM_PORT_MAX}.')
        if preferred_port in used or is_port_listening(preferred_port):
            raise RuntimeError(f'AFM port {preferred_port} is occupied or reserved.')
        return preferred_port
    # The existing allocator has an exclusive end; lifecycle.start_instance_lock
    # holds the shared reservation from selection through registry publication.
    return find_free_port(APPLE_FM_START_PORT, APPLE_FM_PORT_MAX + 1, used)


def _terminate_child(child):
    if child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)


def start_apple_fm_instance(model_name, *, preferred_port=None, capability='chat', start_source=None):
    source = validate_start_source(start_source, context='apple_fm_start_model')
    if model_name != 'system' or capability not in (None, *APPLE_FM_CAPABILITIES):
        raise ValueError('Apple Foundation Models supports system with chat and vision_analysis; audio is unsupported.')
    probe = describe_apple_fm_runtime_probe()
    if probe['runtime_state'] != 'runnable':
        raise RuntimeError('; '.join(probe['issues']))
    system_model = system_model_metadata()
    port = _next_free_port(preferred_port)
    instance_id = f'apple_fm:system:{port}'
    log = LOG_DIR / f'apple_fm_system_{port}.log'
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    prepare_clean_runtime_log(log, metadata={'backend': 'apple_fm', 'instance_id': instance_id, 'port': port})
    cmd = [probe['detection']['binary'], 'serve', '--host', '127.0.0.1', '--port', str(port)]
    child = None
    try:
        with log.open('wb') as handle:
            child = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=handle,
                                     stderr=subprocess.STDOUT, start_new_session=True,
                                     env=sanitized_child_process_env())
        identity = process_identity(child.pid)
        if not identity:
            raise RuntimeError('Could not establish ownership of the AFM server process.')
        deadline = time.monotonic() + APPLE_FM_START_TIMEOUT_SEC
        last_error = 'server exited'
        while child.poll() is None and time.monotonic() < deadline:
            try:
                if not owns_listener(child.pid, port):
                    time.sleep(.1)
                    continue
                metadata = server_metadata(port)
                if system_model:
                    metadata['system_model'] = system_model
                if child.poll() is not None:
                    break
                instance = {'instance_id': instance_id, 'model': 'system', 'request_model': 'system',
                            'port': port, 'pid': child.pid, 'log': str(log), 'process_identity': identity,
                            'server_command': cmd, 'backend_metadata': metadata,
                            'backend_package': 'fm', 'backend_contract': 'fm.serve.chat_completions',
                            'provider_capabilities': list(APPLE_FM_CAPABILITIES),
                            'inputs': ['text', 'image'], 'outputs': ['text']}
                instance.update(build_registry_metadata('system', 'apple_fm', 'chat', metadata=instance))
                instance = attach_start_audit(instance, start_source=source, context='apple_fm_start_model')
                entries = read_registry_entries(CONFIG_FILE)
                write_registry_entries([*entries, instance], path=CONFIG_FILE)
                if not any(e.get('instance_id') == instance_id and e.get('pid') == child.pid
                           for e in read_registry_entries(CONFIG_FILE)):
                    raise RuntimeError('AFM registry publication failed.')
                return instance
            except requests.RequestException as exc:
                last_error = str(exc)
                time.sleep(.1)
        raise RuntimeError(f'AFM failed to start on port {port}: {last_error}. See {log}.')
    except BaseException:
        if child is not None:
            _terminate_child(child)
            entries = read_registry_entries(CONFIG_FILE)
            kept = [e for e in entries if not (e.get('instance_id') == instance_id and e.get('pid') == child.pid)]
            if kept != entries:
                write_registry_entries(kept, path=CONFIG_FILE)
        raise


def stop_apple_fm_instance(instance_id, *, config_path=None):
    path = config_path or CONFIG_FILE
    entries = read_registry_entries(path)
    target = next((e for e in entries if e.get('instance_id') == instance_id and e.get('backend') == 'apple_fm'), None)
    if target is None:
        return False, None
    pid = target.get('pid')
    if pid and pid_is_running(pid):
        expected = target.get('process_identity')
        command = target.get('server_command')
        if (not expected or process_identity(pid) != expected or not isinstance(command, list)
                or command[1:] != ['serve', '--host', '127.0.0.1', '--port', str(target.get('port'))]
                or not expected.endswith(' '.join(command))):
            raise RuntimeError('AFM process ownership cannot be verified; no process was stopped.')
        os.kill(pid, 15)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and process_identity(pid) == expected:
            # Reap if it is our child; a reloaded control plane need not be its parent.
            try:
                if os.waitpid(pid, os.WNOHANG)[0]:
                    break
            except ChildProcessError:
                pass
            time.sleep(.1)
        if process_identity(pid) == expected:
            return False, target
    # Read again so concurrent changes to other backend records are preserved.
    current = read_registry_entries(path)
    write_registry_entries([e for e in current if not (e.get('instance_id') == instance_id
                           and e.get('pid') == pid)], path=path)
    return not any(e.get('instance_id') == instance_id for e in read_registry_entries(path)), target
