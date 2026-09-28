"""Text/image PCC Shortcuts transport used by Fruth's managed PCC adapter.

The user owns and configures the Shortcuts actions. Installed shortcut names
prove installation only, not cloud access or the actual model configuration.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import mimetypes
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from fruth_runtime.child_process_env import sanitized_child_process_env


SHORTCUTS_BINARY = '/usr/bin/shortcuts'
PCC_SHORTCUTS = {'cloud': 'Fruth PCC', 'cloud-pro': 'Fruth PCC Pro'}
PCC_SHORTCUT_TIMEOUT_SEC = 120.0
PCC_MAX_REQUEST_BYTES = 8 * 1024 * 1024  # Transport-memory bound; never truncate.


def decode_image_input(value: str) -> tuple[bytes, str]:
    """Decode the inline transport; leave image interpretation to Use Model."""
    if not isinstance(value, str) or len(value) > PCC_MAX_REQUEST_BYTES:
        raise ValueError('PCC image exceeds PCC_MAX_REQUEST_BYTES or is not an inline image.')
    match = re.fullmatch(r'data:(image/[A-Za-z0-9.+-]+);base64,([A-Za-z0-9+/]+={0,2})', value)
    if not match:
        raise ValueError('PCC requires an inline base64 image data URL.')
    data = base64.b64decode(match[2], validate=True)
    return data, mimetypes.guess_extension(match[1]) or '.bin'


def _command(args: list[str], timeout_sec: float) -> dict[str, Any]:
    started = time.monotonic()
    if sys.platform != 'darwin':
        return {'status': 'unsupported_platform', 'error': 'macOS Shortcuts is required.'}
    try:
        process = subprocess.run(
            [SHORTCUTS_BINARY, *args], stdin=subprocess.DEVNULL,
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=timeout_sec, env=sanitized_child_process_env(),
        )
    except subprocess.TimeoutExpired:
        return {
            'status': 'timeout', 'error': 'Shortcuts CLI timed out; no automatic retry.',
            'elapsed_seconds': time.monotonic() - started,
            'system_side_cancellation': 'unverified',
        }
    except OSError as exc:
        return {'status': 'cli_unavailable', 'error': str(exc)}
    return {
        'status': 'completed' if process.returncode == 0 else 'shortcut_error',
        'exit_code': process.returncode, 'stdout': process.stdout,
        'stderr': process.stderr, 'elapsed_seconds': time.monotonic() - started,
    }


def _valid_timeout(value: float) -> bool:
    return math.isfinite(value) and value > 0


def list_pcc_shortcuts(*, timeout_sec: float = PCC_SHORTCUT_TIMEOUT_SEC) -> dict[str, Any]:
    """Observe installation without making an inference/access probe."""
    if not _valid_timeout(timeout_sec):
        return {'status': 'invalid_request', 'error': 'timeout_sec must be finite and positive.'}
    result = _command(['list'], timeout_sec)
    if result['status'] != 'completed':
        return result
    names = result.pop('stdout').splitlines()
    result['models'] = [
        {
            'model': model, 'shortcut': name,
            'installation': ('installed' if names.count(name) == 1 else
                             'ambiguous' if names.count(name) > 1 else 'missing'),
            'access': 'unknown', 'configuration': 'user_managed',
        }
        for model, name in PCC_SHORTCUTS.items()
    ]
    return result


def _run_selected(text: str, selected: dict[str, Any], *, deadline: float,
                  images: list[tuple[bytes, str]] | tuple = ()) -> dict[str, Any]:
    model = selected['model']
    identity = {'model': model, 'shortcut': PCC_SHORTCUTS[model], 'transport': 'shortcuts_cli'}
    if selected['installation'] != 'installed':
        return {**identity, 'status': 'shortcut_' + selected['installation'],
                'error': 'Install exactly one shortcut with this name using the documented model setting.'}
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return {**identity, 'status': 'timeout', 'stage': 'discovery', 'execution_started': False}
    with tempfile.TemporaryDirectory(prefix='fruth-pcc-') as scratch:
        input_path = Path(scratch) / 'input.txt'
        output_path = Path(scratch) / 'output.txt'
        input_path.write_text(text, encoding='utf-8')
        input_paths = [str(input_path)]
        image_inputs = []
        for index, (data, suffix) in enumerate(images, 1):
            image_path = Path(scratch) / f'image-{index:04d}{suffix}'
            image_path.write_bytes(data)
            input_paths.append(str(image_path))
            image_inputs.append({'attachment': image_path.name, 'sha256': hashlib.sha256(data).hexdigest(),
                                 'size_bytes': len(data), 'index': index})
        result = _command([
            'run', selected['shortcut'], '--input-path', *input_paths,
            '--output-path', str(output_path), '--output-type', 'public.plain-text',
        ], remaining)
        result = {**identity, **result, 'stage': 'execution'}
        if image_inputs:
            result['image_inputs'] = image_inputs
        # stdout and a partial/stale output file are never a success fallback.
        result.pop('stdout', None)
        if result['status'] != 'completed':
            return result
        try:
            output = output_path.read_text(encoding='utf-8')
        except (OSError, UnicodeError) as exc:
            return {**result, 'status': 'invalid_output', 'error': str(exc)}
        if not output.strip():
            return {**result, 'status': 'invalid_output', 'error': 'Shortcut returned no text.'}
        if output.lstrip().startswith('BLOCKED:'):
            return {**result, 'status': 'blocked', 'error': output.strip()}
        return {**result, 'output': output}


def _pro_unavailable_reason(result: dict[str, Any]) -> str | None:
    """Recognize native access/availability errors, never model refusal prose.

Shortcuts exposes localized stderr, not a structured eligibility API. Unknown
errors stay failures; do not turn guardrails or an uncertain timeout into a
second-model attempt.
    """
    if result['status'] in {'shortcut_missing', 'shortcut_ambiguous'}:
        return 'pro_' + result['status']
    if result['status'] != 'shortcut_error' or result.get('stage') != 'execution':
        return None
    diagnostic = ' '.join(result.get('stderr', '').casefold().split())
    if re.search(r'\b(guardrails?|safety|refusal|refused|sicherheitsrichtlinie)\b', diagnostic):
        return None
    if 'cloud pro' not in diagnostic:
        return None
    if ('icloud+' in diagnostic and
            re.search(r'\b(must|required|requires|sign in|signed in|musst|benötigt|erforderlich)\b', diagnostic)):
        return 'pro_access_required'
    if re.search(r'\b(unavailable|not available|nicht verfügbar)\b', diagnostic):
        return 'pro_unavailable'
    if re.search(r'\b(daily limit|usage limit|quota|tageslimit|nutzungslimit|kontingent)\b', diagnostic) and re.search(
            r'\b(exceeded|reached|exhausted|überschritten|erreicht|ausgeschöpft)\b', diagnostic):
        return 'pro_usage_limit'
    return None


def run_pcc_text(
    text: str, *, model: str = 'auto', timeout_sec: float = PCC_SHORTCUT_TIMEOUT_SEC,
    images: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    """Prefer Pro, then Cloud on a confirmed Pro availability/access failure.

Explicit cloud/cloud-pro overrides remain available for diagnostics. All attempts
share one deadline; there is no local-model fallback or same-model retry.
    """
    if model not in {'auto', *PCC_SHORTCUTS} or not isinstance(text, str) or not text.strip():
        return {'status': 'invalid_request', 'error': 'Provide nonempty task text and a valid PCC model selection.'}
    if not _valid_timeout(timeout_sec):
        return {'status': 'invalid_request', 'error': 'timeout_sec must be finite and positive.'}
    try:
        if not isinstance(images, (list, tuple)):
            raise ValueError('PCC images must be an ordered list of inline image data URLs.')
        if len(text.encode('utf-8')) + sum(len(value) for value in images if isinstance(value, str)) > PCC_MAX_REQUEST_BYTES:
            raise ValueError(f'PCC_MAX_REQUEST_BYTES={PCC_MAX_REQUEST_BYTES} exceeded.')
        decoded_images = [decode_image_input(value) for value in images]
    except ValueError as exc:
        return {'status': 'invalid_request', 'error': str(exc)}
    deadline = time.monotonic() + timeout_sec
    listing = list_pcc_shortcuts(timeout_sec=timeout_sec)
    if listing['status'] != 'completed':
        return {**listing, 'requested_model': model, 'stage': 'discovery'}
    installed = {item['model']: item for item in listing['models']}
    selected_model = 'cloud-pro' if model == 'auto' else model
    result = _run_selected(text, installed[selected_model], deadline=deadline, images=decoded_images)
    result['requested_model'] = model
    if model != 'auto':
        return result
    result['attempts'] = [{key: value for key, value in result.items() if key != 'output'}]
    reason = _pro_unavailable_reason(result)
    if reason is None:
        return result
    cloud_result = _run_selected(text, installed['cloud'], deadline=deadline, images=decoded_images)
    return {
        **cloud_result, 'requested_model': model, 'fallback_reason': reason,
        'attempts': [*result['attempts'],
                     {key: value for key, value in cloud_result.items() if key != 'output'}],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    listing = commands.add_parser('list', help='List installation; does not test cloud access.')
    run = commands.add_parser('run', help='Use Cloud Pro when available, otherwise Cloud.')
    run.add_argument('--model', choices=['auto', *PCC_SHORTCUTS], default='auto',
                     help='Default: auto (Pro preferred). Explicit models are diagnostic overrides.')
    run.add_argument('--input', type=Path, required=True, help='UTF-8 task file (required; no interactive input).')
    run.add_argument('--image', type=Path, action='append', default=[],
                     help='Image file to attach (repeat for ordered images).')
    for command in (listing, run):
        command.add_argument('--timeout', type=float, default=PCC_SHORTCUT_TIMEOUT_SEC,
                             help='Total CLI budget in seconds (default: %(default)s).')
    args = parser.parse_args(argv)
    try:
        if args.command == 'list':
            result = list_pcc_shortcuts(timeout_sec=args.timeout)
        else:
            images = []
            for path in args.image:
                if path.stat().st_size > PCC_MAX_REQUEST_BYTES:
                    raise ValueError(f'Image exceeds PCC_MAX_REQUEST_BYTES={PCC_MAX_REQUEST_BYTES}.')
                mime_type = mimetypes.guess_type(str(path))[0] or 'image/unknown'
                images.append(f'data:{mime_type};base64,' + base64.b64encode(path.read_bytes()).decode('ascii'))
            result = run_pcc_text(args.input.read_text(encoding='utf-8'),
                                  model=args.model, timeout_sec=args.timeout,
                                  **({'images': images} if images else {}))
    except (OSError, UnicodeError, ValueError) as exc:
        result = {'status': 'input_error', 'error': str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
