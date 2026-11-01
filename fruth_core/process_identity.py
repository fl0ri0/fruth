"""Shared C-locale process birth/command identity; preserves Apple record formats."""

import datetime as dt
import re
import subprocess

from fruth_runtime.child_process_env import sanitized_child_process_env


def _parsed_process_identity(value):
    """Recognize only the two historical English ps layouts; never guess dates.

    Keep the complete command unchanged. Locale-free parsing also validates the
    calendar date and weekday, so equal malformed strings cannot prove ownership.
    lstart has second precision and no timezone; do not infer timezone conversions.
    """
    if not isinstance(value, str) or any(c in value for c in '\r\n\t\x00'):
        return None
    match = re.fullmatch(
        r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun) +([A-Za-z]{3}|[0-9]{1,2}) +'
        r'([A-Za-z]{3}|[0-9]{1,2}) +([0-9]{2}):([0-9]{2}):([0-9]{2}) +'
        r'([0-9]{4}) +(/\S.*)', value.strip())
    if not match:
        return None
    weekday, first, second, hour, minute, second_time, year, command = match.groups()
    months = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
              'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')
    if first in months and second.isascii() and second.isdigit():
        month, day = first, second
    elif second in months and first.isascii() and first.isdigit():
        month, day = second, first
    else:
        return None
    try:
        birth = dt.datetime(int(year), months.index(month) + 1, int(day),
                            int(hour), int(minute), int(second_time))
    except ValueError:
        return None
    if ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')[birth.weekday()] != weekday:
        return None
    return birth, command


def process_identity_matches(observed, expected):
    """Require valid start-time AND exact executable/command evidence."""
    parsed = _parsed_process_identity(expected)
    return parsed is not None and _parsed_process_identity(observed) == parsed


def process_identity(pid):
    """Capture C-locale birth time/full command, retaining the persisted ps format."""
    env = sanitized_child_process_env()
    env.update(LC_ALL='C', LANG='C')
    result = subprocess.run(['ps', '-ww', '-p', str(pid), '-o', 'lstart=', '-o', 'command='],
                            capture_output=True, text=True, timeout=5, env=env)
    identity = result.stdout.strip() if result.returncode == 0 else ''
    return identity if _parsed_process_identity(identity) is not None else ''

