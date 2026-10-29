"""Fail-closed attribution of an opaque Shortcuts Pro eligibility failure.

No inference, account cache, privilege escalation or global log subscription.
Only the owned CLI's execution interval and its native XPC runner may qualify.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import json
import re
import subprocess
import tempfile
import time

from fruth_runtime.child_process_env import sanitized_child_process_env


PCC_DIAGNOSTIC_TIMEOUT_SEC = 5.0
PCC_DIAGNOSTIC_MAX_BYTES = 1024 * 1024
RUNNER_PATH = ('/System/Library/PrivateFrameworks/WorkflowKit.framework/XPCServices/'
               'BackgroundShortcutRunner.xpc/Contents/MacOS/BackgroundShortcutRunner')
ACTION_PATH = '/System/Library/PrivateFrameworks/ActionKit.framework/Versions/A/ActionKit'
WORKFLOW_PATH = '/System/Library/PrivateFrameworks/WorkflowKit.framework/Versions/A/WorkflowKit'
ELIGIBILITY_MESSAGE = ('Throwing iCloudPlusRequired error because the account is not '
                       'eligible for the Cloud Pro model')
PEER = re.compile(r'name=com\.apple\.WorkflowKit\.BackgroundShortcutRunner\.peer\[(\d+)\]\.')
ACTION_ERROR = re.compile(r'finished with error \{domain: WFAskLLMActionErrorDomain, code: (\d+)\}')


def _timestamp(value):
    # Also accept log's +HHMM offsets on older supported framework Pythons.
    if not isinstance(value, str):
        raise ValueError('An absolute timestamp is required')
    for pattern in ('%Y-%m-%d %H:%M:%S.%f%z', '%Y-%m-%d %H:%M:%S%z'):
        try:
            return datetime.strptime(value.replace('T', ' '), pattern)
        except ValueError:
            pass
    raise ValueError('An absolute timestamp is required')


def classify_pro_access(records, *, cli_pid, started_at, finished_at):
    """Require native peer binding, eligibility message and matching action error.

PID, boot and process image identify one runner within the exact CLI interval.
Any multiple-client runner or conflicting action outcome stays unclassified.
Returned receipts contain only matching diagnostic metadata, never log payloads.
"""
    unknown = {'status': 'unconfirmed', 'source': 'macos_unified_log_xpc_peer'}
    try:
        start, end = _timestamp(started_at), _timestamp(finished_at)
        if type(cli_pid) is not int or cli_pid <= 0 or end < start:
            return unknown
        groups = {}
        for row in records:
            if not isinstance(row, dict) or row.get('processImagePath') != RUNNER_PATH:
                continue
            if not start <= _timestamp(row['timestamp']) <= end:
                continue
            if not isinstance(row.get('eventMessage'), str) or not isinstance(row.get('formatString'), str):
                return unknown
            key = (row.get('bootUUID'), row.get('processID'), row.get('processImageUUID'))
            if (not key[0] or type(key[1]) is not int or key[1] <= 0 or not key[2]):
                continue
            groups.setdefault(key, []).append(row)
    except (KeyError, TypeError, ValueError):
        return unknown
    candidates = []
    for key, rows in groups.items():
        peers = []
        for row in rows:
            message = row.get('eventMessage', '')
            if (row.get('subsystem') == 'com.apple.xpc'
                    and row.get('category') == 'connection'
                    and row.get('senderImagePath') == '/usr/lib/system/libxpc.dylib'
                    and 'activating connection:' in message and 'peer=true' in message):
                match = PEER.search(message)
                if match:
                    peers.append((int(match[1]), _timestamp(row['timestamp'])))
        if cli_pid not in {pid for pid, _ in peers}:
            continue
        # An ambiguous runner must not be ignored in favour of another candidate.
        if {pid for pid, _ in peers} != {cli_pid}:
            return unknown
        candidates.append((key, rows, min(at for _, at in peers)))
    if len(candidates) != 1:
        return unknown
    key, rows, bound_at = candidates[0]
    eligibility, failures = [], []
    for row in rows:
        at = _timestamp(row['timestamp'])
        if at < bound_at or row.get('subsystem') != 'com.apple.shortcuts':
            continue
        message = row.get('eventMessage', '')
        if (row.get('category') == 'Actions' and row.get('senderImagePath') == ACTION_PATH
                and row.get('formatString') == ELIGIBILITY_MESSAGE
                and message == ELIGIBILITY_MESSAGE and row.get('messageType') == 'Error'):
            eligibility.append(row['timestamp'])
        if (row.get('category') == 'WorkflowExecution'
                and row.get('senderImagePath') == WORKFLOW_PATH
                and row.get('formatString') == '%s Action %{public}@ finished with error {domain: %{public}@, code: %ld}. %@'):
            # Preserve unknown action failures as conflicts, not just recognized codes.
            match = ACTION_ERROR.search(message)
            failures.append((int(match[1]) if match else None, row['timestamp']))
    if (not eligibility or not failures or {code for code, _ in failures} != {1511}
            or min(_timestamp(at) for _, at in failures) < min(map(_timestamp, eligibility))):
        return unknown
    return {
        'status': 'confirmed', 'source': 'macos_unified_log_xpc_peer',
        'cli_pid': cli_pid, 'runner_pid': key[1], 'boot_uuid': key[0],
        'runner_image_uuid': key[2], 'error_domain': 'WFAskLLMActionErrorDomain',
        'error_code': 1511, 'reason': 'iCloudPlusRequired',
        'peer_bound_at': bound_at.isoformat(), 'eligibility_at': eligibility[0],
        'action_error_at': failures[0][1],
    }


def pro_access_diagnostic(execution, *, deadline):
    unavailable = {'status': 'unavailable', 'source': 'macos_unified_log_xpc_peer'}
    try:
        start = _timestamp(execution['started_at'])
        end = _timestamp(execution['finished_at'])
        pid = execution['process_id']
        if type(pid) is not int or pid <= 0 or end < start:
            return unavailable
    except (KeyError, TypeError, ValueError):
        return unavailable
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return {**unavailable, 'reason': 'deadline_exhausted'}
    # Native messages only; prompts/model output cannot create eligibility evidence.
    predicate = ('process == "BackgroundShortcutRunner" AND '
                 '((subsystem == "com.apple.xpc" AND category == "connection") OR '
                 '(subsystem == "com.apple.shortcuts" AND '
                 '(category == "Actions" OR category == "WorkflowExecution")))')
    args = ['/usr/bin/log', 'show', '--style', 'ndjson', '--info',
            '--start', start.astimezone().strftime('%Y-%m-%d %H:%M:%S'),
            '--end', (end + timedelta(seconds=1)).astimezone().strftime('%Y-%m-%d %H:%M:%S'),
            '--predicate', predicate]
    try:
        # Spool rather than retaining unrestricted system output in memory.
        with tempfile.TemporaryFile() as output:
            process = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=output,
                                     stderr=subprocess.DEVNULL,
                                     timeout=min(remaining, PCC_DIAGNOSTIC_TIMEOUT_SEC),
                                     env=sanitized_child_process_env())
            if process.returncode:
                return {**unavailable, 'reason': 'log_query_failed'}
            output.seek(0)
            raw = output.read(PCC_DIAGNOSTIC_MAX_BYTES + 1)
        if len(raw) > PCC_DIAGNOSTIC_MAX_BYTES:
            return {**unavailable, 'reason': 'diagnostic_size_exceeded'}
        records = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
        return classify_pro_access(records, cli_pid=pid,
                                   started_at=execution['started_at'],
                                   finished_at=execution['finished_at'])
    except (OSError, subprocess.TimeoutExpired, UnicodeError, ValueError, TypeError):
        return {**unavailable, 'reason': 'diagnostic_unreadable'}
