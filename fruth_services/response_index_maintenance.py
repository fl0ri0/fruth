"""Explicit generation migration, reconstruction and rollback from Ledger truth.

These operations never alter Ledger rows, sidecars, outputs or execution state.
Publication selects a fully built generation last; abandoned generations are
inert. An active writer may also reconstruct an uncertain SQLite index while
holding the same append lock, before performing its requested append.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from fruth_services import response_frames as frames
from fruth_services import response_index_sqlite as storage


def _scan(ledger: Path) -> dict:
    if not ledger.exists():
        if (ledger.is_symlink() or (ledger.parent / storage.SELECTOR_NAME).is_symlink()
                or (ledger.parent / storage.SELECTOR_NAME).exists()
                or (ledger.parent / storage.LEGACY_NAME).exists()
                or (ledger.parent / storage.LEGACY_NAME).is_symlink()
                or any(ledger.parent.glob('current_index.*.sqlite3'))
                or any(p.is_file() for p in (ledger.parent / 'snapshots').rglob('*'))):
            raise storage.IndexInvalid('Canonical Ledger is missing from an existing Index root; restore it before reconstruction.')
        return dict(ok=True, entries={}, latest_by_response={}, ledger_state=None,
                    ledger_line_count=0, ledger_chain_digest=storage.CHAIN_SEED)
    if ledger.stat().st_size == 0:
        # Existing history cannot become empty genesis through a truncated
        # Ledger. Retained generations are contrary evidence, not authority to
        # restore rows: require canonical recovery rather than reset lineage.
        selected = storage.selection(ledger.parent) if (ledger.parent / storage.SELECTOR_NAME).exists() else None
        if selected and not (ledger.parent / selected['filename']).exists():
            raise storage.IndexInvalid('Cannot establish empty genesis with a missing selected Index; restore canonical history.')
        for path in ledger.parent.glob('current_index.*.sqlite3'):
            with storage.connection(path) as conn:
                metadata = storage._read_metadata(conn)
                if (metadata['ledger_size_bytes'] or metadata['ledger_line_count']
                        or storage._complete_map(conn, metadata['root'])):
                    raise storage.IndexInvalid('Canonical Ledger is empty but retained Index history is nonempty; restore it before reconstruction.')
        legacy = ledger.parent / storage.LEGACY_NAME
        if legacy.exists():
            attested = frames.attest_response_frame_index(frames_dir=ledger.parent,
                                                          index_name='./' + storage.LEGACY_NAME, write=False)
            if attested.get('ok') is not True:
                raise storage.IndexInvalid('Cannot establish empty genesis from uncertain retained history; restore the Ledger.')
    scan = frames._scan_response_frame_ledger_index_truth(ledger, include_entries=True)
    if scan.get('ok') is not True:
        raise storage.IndexInvalid(str(scan.get('error')))
    return scan


def _publish_sqlite(root: Path, ledger: Path, scan: dict, expected_selector_state,
                    expected_source=None) -> dict:
    initialized = scan['ledger_state'] is None
    if initialized:
        # Only _scan's proven new/unselected empty directory reaches this path.
        # An existing generation with a missing Ledger is never reset to empty.
        with ledger.open('xb') as handle:
            os.fsync(handle.fileno())
        descriptor = os.open(ledger.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        scan = {**scan, 'ledger_state': storage.file_state(ledger)}
    generation = uuid.uuid4().hex
    selected = storage.selector_payload(generation, 'sqlite')
    selected['ledger_name'] = ledger.name
    path = root / selected['filename']
    selected['metadata_sha256'] = storage.build(
        path, generation=generation, entries=scan['entries'], ledger_path=ledger,
        ledger_state=scan['ledger_state'], line_count=scan['ledger_line_count'],
        chain_digest=scan['ledger_chain_digest'],
    )
    selected['index_state'] = storage.file_state(path)
    # Independently read/verify the staged tree and exact reconstructed map.
    verified = storage.read(path, ledger_path=ledger, selected=selected)
    if storage.encode(verified['responses']) != storage.encode(scan['entries']):
        raise storage.IndexInvalid('Staged generation changed reconstructed entries.')
    selector = root / storage.SELECTOR_NAME
    if (storage.file_state(ledger) != scan['ledger_state']
            or storage.file_state(selector) != expected_selector_state
            or (expected_source is not None and storage.file_state(expected_source[0]) != expected_source[1])):
        raise storage.IndexInvalid('Ledger/selector changed before SQLite activation.')
    frames._atomic_replace_file_bytes(selector, storage.encode(selected) + b'\n')
    return dict(ok=True, changed=True, backend='sqlite', index_path=str(path),
                generation=generation, response_count=len(scan['entries']),
                ledger_line_count=scan['ledger_line_count'], ledger_unchanged=True,
                ledger_initialized=initialized)


def rebuild_sqlite_locked(root: Path, ledger: Path) -> dict:
    """Caller owns the thread and process append locks; never append a frame."""
    selector_state = storage.file_state(root / storage.SELECTOR_NAME)
    return _publish_sqlite(root, ledger, _scan(ledger), selector_state)


def _rollback_payload(ledger: Path, scan: dict) -> dict:
    # Check legacy compatibility during read-only preflight as well as publish.
    payload = frames._json_safe(dict(
        kind='fruth.response_frame_current_index', version=2,
        ledger_path=str(ledger), ledger_name=ledger.name,
        ledger_size_bytes=scan['ledger_state']['size_bytes'] if scan['ledger_state'] else 0,
        ledger_line_count=scan['ledger_line_count'], responses=scan['entries'],
    ))
    payload['responses'] = payload.get('responses', {})
    if set(payload['responses']) != set(scan['entries']):
        raise storage.IndexInvalid('Legacy JSON normalization cannot preserve these response IDs; keep SQLite selected.')
    size = payload['ledger_size_bytes']
    payload.update(ledger_line_count_verified_size_bytes=size,
                   response_map_verified_size_bytes=size,
                   response_map_entry_count=len(payload.get('responses', {})),
                   response_map_digest=frames._response_map_digest(payload.get('responses', {})))
    return payload


def _rollback_locked(root: Path, ledger: Path, scan: dict, selector_state) -> dict:
    # Reconstruct CURRENT truth, not the inert pre-migration JSON file.
    payload = _rollback_payload(ledger, scan)
    path = root / storage.LEGACY_NAME
    selector = root / storage.SELECTOR_NAME
    if (storage.file_state(ledger) != scan['ledger_state']
            or storage.file_state(selector) != selector_state):
        raise storage.IndexInvalid('Ledger/selector moved before rollback publication.')
    frames._atomic_replace_file_bytes(path, storage.encode(payload) + b'\n')
    if (storage.file_state(ledger) != scan['ledger_state']
            or storage.file_state(selector) != selector_state):
        raise storage.IndexInvalid('Ledger/selector moved before rollback activation.')
    selected = storage.selector_payload(uuid.uuid4().hex, 'json')
    selected['ledger_name'] = ledger.name
    frames._atomic_replace_file_bytes(selector, storage.encode(selected) + b'\n')
    return dict(ok=True, changed=True, backend='json', index_path=str(path),
                response_count=len(scan['entries']), ledger_line_count=scan['ledger_line_count'],
                ledger_unchanged=True)


def maintain_response_index(*, frames_dir: Path, action: str, ledger_name='responses.jsonl',
                            check_only=False, writers_stopped=False) -> dict:
    """Operator boundary; callers must separately authorize operational use."""
    root = Path(frames_dir)
    ledger = root / ledger_name
    if action not in {'migrate', 'rebuild', 'rollback', 'check'}:
        raise ValueError('Unknown response index maintenance action.')
    if action == 'check':
        return frames.attest_response_frame_index(frames_dir=root, ledger_name=ledger_name, write=False)
    if not check_only and not writers_stopped:
        return dict(ok=False, changed=False, error={
            'code': 'response_frame_writers_not_confirmed_stopped',
            'message': 'Migration/reconstruction/rollback requires quiescent writers.',
        })

    def prepare():
        selector_state = storage.file_state(root / storage.SELECTOR_NAME)
        source_path = frames._index_path(frames_dir=root)
        source_state = storage.file_state(source_path)
        if action == 'migrate' and (source_path.exists() or selector_state is not None):
            preflight = frames.attest_response_frame_index(
                frames_dir=root, ledger_name=ledger_name, write=False,
            )
            if preflight.get('ok') is not True:
                raise storage.IndexInvalid('Source index is uncertain; use explicit rebuild from the Ledger. '
                                           + str(preflight.get('error')))
        scan = _scan(ledger)
        if action == 'rollback':
            _rollback_payload(ledger, scan)
        if (storage.file_state(source_path) != source_state
                or storage.file_state(root / storage.SELECTOR_NAME) != selector_state):
            raise storage.IndexInvalid('Source index/selector changed during migration preflight.')
        return scan, selector_state, (source_path, source_state)

    selector_before = storage.file_state(root / storage.SELECTOR_NAME)
    legacy_before = storage.file_state(root / storage.LEGACY_NAME)
    generations_before = set(root.glob('current_index.*.sqlite3'))
    try:
        if check_only:
            with frames._RESPONSE_FRAME_APPEND_LOCK:
                scan, _, source = prepare()
                return dict(ok=True, changed=False, action=action, source_index_path=str(source[0]),
                            response_count=len(scan['entries']), ledger_line_count=scan['ledger_line_count'],
                            ledger_unchanged=True, prospective_backend='json' if action == 'rollback' else 'sqlite')
        with frames._RESPONSE_FRAME_APPEND_LOCK, storage.writer_lock(root):
            scan, selector_state, source = prepare()
            if action == 'migrate' and selector_state is not None:
                selected = storage.selection(root)
                if selected and selected['backend'] == 'sqlite':
                    return dict(ok=True, changed=False, status='already_sqlite',
                                index_path=str(root / selected['filename']))
            if action == 'rollback':
                return _rollback_locked(root, ledger, scan, selector_state)
            return _publish_sqlite(root, ledger, scan, selector_state, source)
    except (OSError, ValueError, KeyError, TypeError, storage.sqlite3.Error) as exc:
        inactive = sorted(str(p) for p in set(root.glob('current_index.*.sqlite3')) - generations_before)
        activated = storage.file_state(root / storage.SELECTOR_NAME) != selector_before
        legacy_changed = storage.file_state(root / storage.LEGACY_NAME) != legacy_before
        return dict(ok=False, changed=bool(inactive or activated or legacy_changed), action=action,
                    active_generation_changed=activated, inactive_generation_paths=inactive,
                    legacy_index_changed=legacy_changed,
                    error={'code': 'response_frame_index_maintenance_failed', 'message': str(exc)})
