#!/usr/bin/env python3
"""Measure derived-index costs on increasing disposable synthetic histories."""

from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fruth_services import response_frames as frames
from fruth_services import response_index_sqlite as storage
from fruth_services.response_index_maintenance import rebuild_sqlite_locked


def frame(response_id):
    return dict(kind='fruth.response_frame', frame_version=9, response_id=response_id,
                status='completed', current_state=dict(id=response_id, status='completed',
                                                      lifecycle_state='completed', output_text='Synthetic work.'))


def fixture(root, size, backend, legacy):
    root.mkdir()
    ledger = root / 'responses.jsonl'
    with ledger.open('wb') as handle:
        for i in range(size):
            value = frames.enrich_response_frame_metadata(frame(f'response-{i:08}'))
            handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True).encode() + b'\n')
        handle.flush()
        os.fsync(handle.fileno())
    if backend == 'sqlite':
        with storage.writer_lock(root):
            rebuild_sqlite_locked(root, ledger)
    else:
        scan = frames._scan_response_frame_ledger_index_truth(ledger, include_entries=True)
        # The retained JSON writer predates source-row hashes. Do not inflate
        # its baseline with SQLite's additive verification fields.
        entries = frames._json_safe({
            key: {field: value for field, value in entry.items() if field != 'source_frame_sha256'}
            for key, entry in scan['entries'].items()
        })
        payload = dict(kind='fruth.response_frame_current_index', version=2, responses=entries,
                       ledger_path=str(ledger), ledger_name=ledger.name, ledger_line_count=size,
                       ledger_size_bytes=ledger.stat().st_size,
                       ledger_line_count_verified_size_bytes=ledger.stat().st_size,
                       response_map_verified_size_bytes=ledger.stat().st_size,
                       response_map_entry_count=size, response_map_digest=legacy._response_map_digest(entries))
        legacy._atomic_replace_file_bytes(root / 'current_index.json', storage.encode(payload) + b'\n')
    return ledger


def milliseconds(operation):
    start = time.perf_counter_ns()
    result = operation()
    return (time.perf_counter_ns() - start) / 1_000_000, result


def measure(root, size, backend, repetitions, legacy):
    owner = frames if backend == 'sqlite' else legacy
    ledger = fixture(root, size, backend, legacy)
    hits, misses, writes, counts_by_write = [], [], [], []
    for _ in range(repetitions):
        duration, result = milliseconds(lambda: owner.load_latest_response_state('response-00000000', frames_dir=root))
        assert result['ok'] and result['index_used']
        hits.append(duration)
        duration, result = milliseconds(lambda: owner.load_latest_response_state('missing-response', frames_dir=root))
        assert result['status_code'] == 404 and result['error']['index_used']
        misses.append(duration)
    for i in range(repetitions):
        # Ledger preparation and fsync are intentionally outside the Index timer.
        value = frames.enrich_response_frame_metadata(
            frame('response-00000000'), previous_frames=[dict(
                response_id='response-00000000', frame_id=f'response-00000000:frame-{i + 1}', frame_sequence=i + 1)],
            force_append_sequence=True,
        )
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True).encode() + b'\n'
        prior = frames._response_frame_file_state(ledger)
        offset = ledger.stat().st_size
        with ledger.open('ab') as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        kwargs = dict(ledger_path=ledger, frames_dir=root, line_offset=size + i,
                      byte_offset=offset, line_length=len(raw), ledger_size_bytes=offset + len(raw),
                      effective_snapshot_manifest={})
        if backend == 'sqlite':
            kwargs.update(prior_ledger_state=prior, source_frame_sha256=hashlib.sha256(raw).hexdigest())
        counts = collections.Counter()
        with patch.object(owner, 'state_flow_note', lambda **kw: counts.update(kw)), \
                patch.object(storage, 'state_flow_note', lambda **kw: counts.update(kw)):
            duration, _ = milliseconds(lambda: owner._write_response_frame_index(value, **kwargs))
        writes.append(duration)
        counts_by_write.append(dict(counts))
    index_path = frames._index_path(frames_dir=root)
    assert frames.verify_response_frame_epoch(frames_dir=root, allow_legacy_index=backend == 'json')['ok']
    return dict(history_responses=size, backend=backend, repetitions=repetitions,
                update_ms_median=statistics.median(writes),
                update_ms_min=min(writes), update_ms_max=max(writes),
                hit_ms_median=statistics.median(hits), absence_ms_median=statistics.median(misses),
                index_bytes=index_path.stat().st_size,
                selector_bytes=(root / storage.SELECTOR_NAME).stat().st_size if backend == 'sqlite' else 0,
                publication_counters=counts_by_write)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sizes', type=int, nargs='+', default=[100, 1000, 10000])
    parser.add_argument('--repetitions', type=int, default=7)
    parser.add_argument('--legacy-source', type=Path,
                        required=True,
                        help='Saved pre-SQLite response_frames.py for explicit old-owner measurement; normal runtime is SQLite only.')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    if min(args.sizes) < 1 or args.repetitions < 1:
        parser.error('Sizes and repetitions must be positive.')
    spec = importlib.util.spec_from_file_location('fruth_response_index_benchmark_legacy', args.legacy_source)
    legacy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy)
    with tempfile.TemporaryDirectory(prefix='fruth-index-benchmark-') as temporary:
        results = [measure(Path(temporary) / f'{backend}-{size}', size, backend, args.repetitions, legacy)
                   for size in args.sizes for backend in ('json', 'sqlite')]
    report = dict(kind='fruth.response_index_benchmark', python=sys.version.split()[0],
                  sqlite=sqlite_version(), fixture='synthetic compact frames, no sidecars or inference',
                  timer='Index publication after Ledger fsync; hit/absence canonical lookup',
                  legacy_source=str(args.legacy_source),
                  results=results,
                  limitations='Warm local filesystem; small entries; no end-to-end speedup claim. '
                  'Node-byte counters are logical encoded work, not SQLite physical page IO.')
    encoded = json.dumps(report, indent=2, sort_keys=True) + '\n'
    if args.output:
        args.output.write_text(encoded)
    print(encoded, end='')


def sqlite_version():
    return storage.sqlite3.sqlite_version


if __name__ == '__main__':
    main()
