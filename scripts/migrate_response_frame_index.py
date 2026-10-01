#!/usr/bin/env python3
"""Explicitly select/rebuild SQLite, or reconstruct a current JSON rollback."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fruth_services.response_index_maintenance import maintain_response_index


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['migrate', 'rebuild', 'rollback', 'check'])
    parser.add_argument('--frames-dir', required=True, type=Path)
    parser.add_argument('--ledger-name', default='responses.jsonl')
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--writers-stopped', action='store_true',
                        help='Assert that the control plane and ALL response writers are quiescent.')
    args = parser.parse_args(argv)
    result = maintain_response_index(frames_dir=args.frames_dir, action=args.action,
                                     ledger_name=args.ledger_name, check_only=args.check_only,
                                     writers_stopped=args.writers_stopped)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get('ok') is True else 1


if __name__ == '__main__':
    raise SystemExit(main())
