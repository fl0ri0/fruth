#!/usr/bin/env python3
"""Sync existing eval metadata only; never extract, adjudicate or mutate Gold."""
import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from fruth_services.research_candidates import refresh_availability, sync_candidates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=REPO_ROOT)
    parser.add_argument('--source', type=Path, help='Existing eval JSONL inside root; defaults to state/self_learning/eval_cases.jsonl')
    parser.add_argument('--refresh-availability', action='store_true', help='Refresh existing provenance status without requiring source eval ledger')
    args = parser.parse_args()
    root = args.root.absolute()
    directory = root / 'fruth_research/candidates'
    if args.refresh_availability and args.source:
        parser.error('--source and --refresh-availability are mutually exclusive')
    result = (refresh_availability(directory, root=root) if args.refresh_availability else
              sync_candidates(args.source or root / 'state/self_learning/eval_cases.jsonl', directory, root=root))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
