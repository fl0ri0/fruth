"""Explicit, user-confirmed import assistance for the bundled PCC shortcuts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from fruth_integrations.shortcuts.pcc import PCC_SHORTCUTS, list_pcc_shortcuts
from fruth_runtime.child_process_env import sanitized_child_process_env

BUNDLED_SHORTCUTS_DIR = Path(__file__).resolve().parent
PCC_SETUP_TIMEOUT_SEC = 10


def _missing_shortcuts(observation: dict[str, Any]) -> list[str]:
    if observation.get('status') != 'completed':
        return []
    return [name for name in PCC_SHORTCUTS.values()
            if any(item.get('shortcut') == name and item.get('installation') == 'missing'
                   for item in observation.get('models', []))]


def pcc_setup_available(observation: dict[str, Any]) -> bool:
    """Project an existing observation; never query or open the Shortcuts app."""
    missing = _missing_shortcuts(observation)
    return sys.platform == 'darwin' and bool(missing) and all(
        (BUNDLED_SHORTCUTS_DIR / f'{name}.shortcut').is_file() for name in missing)


def open_pcc_shortcut_imports() -> dict[str, Any]:
    """Open missing bundled files only after an explicit user setup action."""
    if sys.platform != 'darwin':
        return {'status': 'setup_unavailable', 'error': 'PCC setup requires macOS Shortcuts.'}
    observation = list_pcc_shortcuts(timeout_sec=PCC_SETUP_TIMEOUT_SEC)
    if observation.get('status') != 'completed':
        return {'status': 'setup_unavailable',
                'error': observation.get('error') or observation.get('stderr') or
                         'Could not check installed shortcuts. Retry setup after opening Shortcuts.'}
    missing = _missing_shortcuts(observation)
    ambiguous = [item['shortcut'] for item in observation.get('models', [])
                 if item.get('installation') == 'ambiguous']
    if not missing:
        if ambiguous:
            return {'status': 'setup_unavailable',
                    'error': 'Resolve duplicate shortcut names in Shortcuts: ' + ', '.join(ambiguous)}
        if not all(any(item.get('shortcut') == name and item.get('installation') == 'installed'
                       for item in observation.get('models', [])) for name in PCC_SHORTCUTS.values()):
            return {'status': 'setup_unavailable', 'error': 'Shortcut installation could not be established.'}
        return {'status': 'setup_complete',
                'message': 'PCC shortcuts are already installed. Select Start to start PCC.'}
    if not pcc_setup_available(observation):
        return {'status': 'setup_unavailable',
                'error': 'Bundled PCC shortcuts are missing. Follow fruth_integrations/shortcuts/README.md to import them.'}
    paths = [str(BUNDLED_SHORTCUTS_DIR / f'{name}.shortcut') for name in missing]
    try:
        result = subprocess.run(
            ['/usr/bin/open', '-a', 'Shortcuts', *paths],
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
            timeout=PCC_SETUP_TIMEOUT_SEC, env=sanitized_child_process_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'status': 'setup_unavailable', 'error': f'Could not open Shortcuts import: {exc}'}
    if result.returncode:
        return {'status': 'setup_unavailable',
                'error': result.stderr.strip() or 'Could not open Shortcuts import.'}
    message = ('On this Mac, review and click Add Shortcut in Shortcuts for: '
               + ', '.join(missing) + '. Then refresh Models and select Start.')
    if ambiguous:
        message += ' Resolve duplicate names separately: ' + ', '.join(ambiguous) + '.'
    return {'status': 'setup_required', 'opened_shortcuts': missing, 'message': message}
