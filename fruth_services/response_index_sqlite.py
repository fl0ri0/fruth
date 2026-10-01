"""Storage for the derived response index; the JSONL Ledger remains canonical.

An authenticated AVL tree commits complete entry bytes, keys, child identities,
counts and heights. A lookup verifies an inclusion/non-inclusion path from its
root. Only reconstruction/full audit traverses every response. Coverage is
established from the Ledger, then advanced by the Ledger-first writer, never by
assuming that SQLite transactions imply correspondence with another file.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fruth_services.state_flow import note as state_flow_note

SELECTOR_NAME = 'current_index.active.json'
LEGACY_NAME = 'current_index.json'
LOCK_NAME = '.response_frame_append.lock'
KIND = 'fruth.response_frame_sqlite_index'
ALGORITHM = 'sha256-avl-v1'
EMPTY_DIGEST = hashlib.sha256(b'fruth.response_index.empty.v1').hexdigest()
EMPTY = {'key': None, 'digest': EMPTY_DIGEST, 'count': 0, 'height': 0}
CHAIN_SEED = hashlib.sha256(b'fruth.response_ledger.chain.v1').hexdigest()
# Lock contention fails storage publication explicitly; it never drops work.
SQLITE_BUSY_TIMEOUT_SECONDS = 30.0
FILE_STATE_KEYS = {'device', 'inode', 'size_bytes', 'mtime_ns', 'ctime_ns'}


class IndexInvalid(ValueError):
    """Uncertain storage must retain canonical Ledger fallback."""


def encode(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')


def file_state(path: Path) -> dict[str, int] | None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return dict(device=stat.st_dev, inode=stat.st_ino, size_bytes=stat.st_size,
                mtime_ns=stat.st_mtime_ns, ctime_ns=stat.st_ctime_ns)


def identity(state: dict | None) -> dict | None:
    return {k: state[k] for k in ('device', 'inode')} if state else None


def selection(root: Path) -> dict | None:
    path = root / SELECTOR_NAME
    if not path.exists() and not path.is_symlink():
        if any(root.glob('current_index.*.sqlite3')):
            raise IndexInvalid('SQLite generations exist but their selector is missing; reconstruct explicitly.')
        return None
    try:
        value = json.loads(path.read_bytes())
        backend, name, generation = value['backend'], value['filename'], value['generation']
        if (value.get('kind') != 'fruth.response_frame_index_selection'
                or type(value.get('version')) is not int or value['version'] != 1
                or backend not in ('sqlite', 'json')
                or not isinstance(generation, str) or len(generation) != 32
                or any(c not in '0123456789abcdef' for c in generation)
                or name != (f'current_index.{generation}.sqlite3' if backend == 'sqlite'
                            else LEGACY_NAME)
                or (backend == 'sqlite' and
                    (not isinstance(value.get('metadata_sha256'), str)
                     or len(value['metadata_sha256']) != 64
                     or any(c not in '0123456789abcdef' for c in value['metadata_sha256'])
                     or not isinstance(value.get('index_state'), dict)
                     or set(value['index_state']) != FILE_STATE_KEYS
                     or any(type(v) is not int for v in value['index_state'].values())))):
            raise IndexInvalid('Invalid response index generation selector.')
        return value
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise IndexInvalid('Invalid response index generation selector.') from exc


def selected_path(root: Path, index_name: str = LEGACY_NAME) -> Path:
    if index_name != LEGACY_NAME:
        return root / index_name
    try:
        selected = selection(root)
    except IndexInvalid:
        # Physical guards can still observe a broken selector; readers/writers
        # reject it separately. Never implicitly reactivate the old JSON map.
        return root / SELECTOR_NAME
    return root / (selected['filename'] if selected else LEGACY_NAME)


@contextmanager
def writer_lock(root: Path):
    """Cooperating processes serialize parent CAS through index publication."""
    missing = []
    ancestor = root
    while not ancestor.exists():
        missing.append(ancestor)
        ancestor = ancestor.parent
    root.mkdir(parents=True, exist_ok=True)
    # The lock must exist before parent selection. Retain newly created path
    # names now so moving mkdir outside the Ledger writer loses no durability.
    for directory in dict.fromkeys(p.parent for p in missing):
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    with (root / LOCK_NAME).open('a+b') as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def connection(path: Path, *, write: bool = False):
    # DELETE journal + FULL sync deliberately keep physical Epoch guards bound
    # to one DB file. A WAL cannot be silently omitted from those guards.
    mode = 'rw' if write else 'ro'
    conn = sqlite3.connect(f'{path.resolve().as_uri()}?mode={mode}', uri=True,
                           timeout=SQLITE_BUSY_TIMEOUT_SECONDS, isolation_level=None)
    try:
        if conn.execute('PRAGMA journal_mode').fetchone()[0].lower() != 'delete':
            raise IndexInvalid('Response index requires DELETE journal mode.')
        if write:
            conn.execute('PRAGMA synchronous=FULL')
            conn.execute('BEGIN IMMEDIATE')
        else:
            conn.execute('PRAGMA query_only=ON')
            conn.execute('BEGIN')
        yield conn
        if write:
            conn.execute('COMMIT')
    finally:
        conn.close()


def _commitment(value: Any) -> dict:
    if (not isinstance(value, dict) or set(value) != set(EMPTY)
            or type(value['count']) is not int or type(value['height']) is not int):
        raise IndexInvalid('Malformed authenticated child commitment.')
    if value['key'] is None:
        if value != EMPTY:
            raise IndexInvalid('Invalid empty child commitment.')
    elif (not isinstance(value['key'], str) or not value['key']
          or type(value['count']) is not int or value['count'] <= 0
          or type(value['height']) is not int or value['height'] <= 0
          or not isinstance(value['digest'], str) or len(value['digest']) != 64
          or any(c not in '0123456789abcdef' for c in value['digest'])):
        raise IndexInvalid('Invalid authenticated child commitment.')
    return value


def _node_commitment(node: dict) -> dict:
    key, left, right = node['key'], _commitment(node['left']), _commitment(node['right'])
    if not isinstance(key, str) or not key or not isinstance(node['entry'], dict):
        raise IndexInvalid('Malformed authenticated index entry.')
    if node['entry'].get('response_id') != key:
        raise IndexInvalid('Authenticated key/entry identity mismatch.')
    if ((left['key'] is not None and left['key'] >= key)
            or (right['key'] is not None and right['key'] <= key)):
        raise IndexInvalid('Invalid authenticated search order.')
    return dict(key=key,
                digest=hashlib.sha256(b'fruth.response_index.node.v1\0' + encode(node)).hexdigest(),
                count=1 + left['count'] + right['count'],
                height=1 + max(left['height'], right['height']))


def _read_node(conn, expected: dict, lower=None, upper=None) -> dict:
    expected = _commitment(expected)
    if expected['key'] is None:
        raise IndexInvalid('An empty commitment cannot be read as a node.')
    row = conn.execute('SELECT body FROM nodes WHERE response_id=?', (expected['key'],)).fetchone()
    if row is None:
        raise IndexInvalid('An authenticated index child is missing.')
    try:
        node = json.loads(row[0])
        if (set(node) != {'key', 'entry', 'left', 'right'}
                or _node_commitment(node) != expected
                or abs(node['left']['height'] - node['right']['height']) > 1
                or (lower is not None and node['key'] <= lower)
                or (upper is not None and node['key'] >= upper)):
            raise IndexInvalid('Authenticated response index digest/order mismatch.')
    except (ValueError, KeyError, TypeError) as exc:
        raise IndexInvalid('Corrupt authenticated index node.') from exc
    state_flow_note(sqlite_index_node_reads=1, sqlite_index_read_bytes=len(row[0]))
    return node


def _save_node(conn, key, entry, left, right) -> dict:
    node = dict(key=key, entry=entry, left=left, right=right)
    body = encode(node)
    commitment = _node_commitment(node)
    conn.execute('INSERT INTO nodes(response_id,body) VALUES(?,?) '
                 'ON CONFLICT(response_id) DO UPDATE SET body=excluded.body', (key, body))
    state_flow_note(sqlite_index_node_writes=1, sqlite_index_written_bytes=len(body))
    return commitment


def _balance(conn, key, entry, left, right) -> dict:
    if left['height'] > right['height'] + 1:
        child = _read_node(conn, left, upper=key)
        if child['left']['height'] < child['right']['height']:
            pivot = _read_node(conn, child['right'], lower=child['key'], upper=key)
            a = _save_node(conn, child['key'], child['entry'], child['left'], pivot['left'])
            b = _save_node(conn, key, entry, pivot['right'], right)
            return _save_node(conn, pivot['key'], pivot['entry'], a, b)
        b = _save_node(conn, key, entry, child['right'], right)
        return _save_node(conn, child['key'], child['entry'], child['left'], b)
    if right['height'] > left['height'] + 1:
        child = _read_node(conn, right, lower=key)
        if child['right']['height'] < child['left']['height']:
            pivot = _read_node(conn, child['left'], lower=key, upper=child['key'])
            a = _save_node(conn, key, entry, left, pivot['left'])
            b = _save_node(conn, child['key'], child['entry'], pivot['right'], child['right'])
            return _save_node(conn, pivot['key'], pivot['entry'], a, b)
        a = _save_node(conn, key, entry, left, child['left'])
        return _save_node(conn, child['key'], child['entry'], a, child['right'])
    return _save_node(conn, key, entry, left, right)


def _update(conn, root, key, entry, lower=None, upper=None) -> dict:
    if root['key'] is None:
        if conn.execute('SELECT 1 FROM nodes WHERE response_id=?', (key,)).fetchone():
            raise IndexInvalid('Unreachable response index row already exists.')
        return _save_node(conn, key, entry, EMPTY, EMPTY)
    node = _read_node(conn, root, lower, upper)
    if key == node['key']:
        return _save_node(conn, key, entry, node['left'], node['right'])
    if key < node['key']:
        left = _update(conn, node['left'], key, entry, lower, node['key'])
        return _balance(conn, node['key'], node['entry'], left, node['right'])
    right = _update(conn, node['right'], key, entry, node['key'], upper)
    return _balance(conn, node['key'], node['entry'], node['left'], right)


def _lookup(conn, root, key) -> dict | None:
    lower = upper = None
    seen = set()
    while root['key'] is not None:
        if root['key'] in seen:
            raise IndexInvalid('Cycle in authenticated response index.')
        seen.add(root['key'])
        node = _read_node(conn, root, lower, upper)
        if key == node['key']:
            return node['entry']
        if key < node['key']:
            upper, root = node['key'], node['left']
        else:
            lower, root = node['key'], node['right']
    # An inserted orphan is corruption, not an absence proof for that key.
    if conn.execute('SELECT 1 FROM nodes WHERE response_id=?', (key,)).fetchone():
        raise IndexInvalid('Unreachable response index row.')
    return None


def _complete_map(conn, root) -> dict:
    responses, seen = {}, set()

    def visit(commitment, lower=None, upper=None):
        if commitment['key'] is None:
            return
        if commitment['key'] in seen:
            raise IndexInvalid('Cycle or duplicated authenticated child.')
        seen.add(commitment['key'])
        node = _read_node(conn, commitment, lower, upper)
        visit(node['left'], lower, node['key'])
        responses[node['key']] = node['entry']
        visit(node['right'], node['key'], upper)

    if conn.execute('PRAGMA quick_check').fetchone() != ('ok',):
        raise IndexInvalid('SQLite response index integrity check failed.')
    visit(root)
    stored_keys = {row[0] for row in conn.execute('SELECT response_id FROM nodes')}
    if stored_keys != seen or len(seen) != root['count']:
        raise IndexInvalid('Incomplete authenticated response index map.')
    state_flow_note(sqlite_index_full_map_passes=1)
    return responses


def _read_metadata(conn) -> dict:
    rows = conn.execute('SELECT singleton,payload,sha256 FROM metadata').fetchall()
    if len(rows) != 1 or rows[0][0] != 1 or hashlib.sha256(rows[0][1]).hexdigest() != rows[0][2]:
        raise IndexInvalid('Corrupt response index coverage metadata.')
    metadata = json.loads(rows[0][1])
    if not isinstance(metadata, dict):
        raise IndexInvalid('SQLite coverage metadata is not an object.')
    if (metadata.get('kind') != KIND or type(metadata.get('version')) is not int or metadata['version'] != 1
            or metadata.get('algorithm') != ALGORITHM
            or type(metadata.get('ledger_line_count')) is not int
            or metadata['ledger_line_count'] < 0
            or type(metadata.get('ledger_size_bytes')) is not int
            or metadata['ledger_size_bytes'] < 0):
        raise IndexInvalid('Unsupported/incomplete SQLite response index metadata.')
    _commitment(metadata['root'])
    return metadata


def _write_metadata(conn, metadata):
    raw = encode(metadata)
    conn.execute('INSERT OR REPLACE INTO metadata(singleton,payload,sha256) VALUES(1,?,?)',
                 (raw, hashlib.sha256(raw).hexdigest()))


def advance_chain(previous: str, source_row_sha256: str) -> str:
    return hashlib.sha256(b'fruth.response_ledger.chain.row.v1\0'
                          + bytes.fromhex(previous) + bytes.fromhex(source_row_sha256)).hexdigest()


class _LookupProof:
    """Private, immutable-binding witness for one loaded lookup, never persisted.

    It is not a public token or caller-authored authority. Copies of a result
    must still match its exact headers/entry and current physical sources.
    """

    def __init__(self, result, path, ledger_path, selector_path, states, response_id):
        self._header = encode({k: v for k, v in result.items() if k != 'responses'})
        self._responses = encode(result['responses'])
        self._paths = (path, ledger_path, selector_path)
        self._states = states
        self._response_id = response_id

    def matches(self, result, ledger_path):
        return (Path(ledger_path).resolve() == self._paths[1].resolve()
                and self._header == encode({k: v for k, v in result.items()
                                            if k not in ('responses', '_sqlite_lookup_proof')})
                and self._responses == encode(result['responses'])
                and tuple(file_state(p) for p in self._paths) == self._states)


def lookup_proof_matches(result, ledger_path, response_id=None) -> bool:
    proof = result.get('_sqlite_lookup_proof')
    try:
        return (type(proof) is _LookupProof
                and (response_id is None or response_id == proof._response_id)
                and proof.matches(result, ledger_path))
    except (ValueError, TypeError, KeyError, OSError):
        return False


def read(path: Path, *, ledger_path: Path, selected: dict | None,
         response_id: str | None = None, require_binding: bool = True) -> dict:
    """Read one authenticated path, or deliberately verify/enumerate the map."""
    selector_path = path.parent / SELECTOR_NAME
    states = tuple(file_state(p) for p in (path, ledger_path, selector_path))
    if states[0] is None:
        raise IndexInvalid('Selected SQLite response index is missing.')
    try:
        active_selection = selection(path.parent)
    except IndexInvalid:
        active_selection = None
    active_generation = active_selection is not None and active_selection == selected
    if response_id is not None and not active_generation:
        raise IndexInvalid('A staged/unselected generation cannot issue a current lookup proof.')
    with connection(path) as conn:
        metadata = _read_metadata(conn)
        if selected and (selected.get('backend') != 'sqlite'
                         or selected.get('generation') != metadata['generation']
                         or selected.get('filename') != path.name
                         or selected.get('metadata_sha256') != hashlib.sha256(encode(metadata)).hexdigest()):
            raise IndexInvalid('Selected response index generation mismatch.')
        if require_binding:
            if (selected is None or selected.get('index_state') != states[0]
                    or metadata['database_identity'] != identity(states[0])
                    or metadata['ledger_state'] != states[1]
                    or Path(metadata['ledger_path']).resolve() != ledger_path.resolve()
                    or metadata['ledger_name'] != ledger_path.name
                    or metadata['ledger_size_bytes'] != (states[1]['size_bytes'] if states[1] else 0)):
                raise IndexInvalid('SQLite response index is stale, relocated or replaced.')
        root = metadata['root']
        if response_id is None:
            responses = _complete_map(conn, root)
        else:
            entry = _lookup(conn, root, response_id)
            responses = {response_id: entry} if entry is not None else {}
    if tuple(file_state(p) for p in (path, ledger_path, selector_path)) != states:
        raise IndexInvalid('Response index/Ledger moved during SQLite read.')
    size = metadata['ledger_size_bytes']
    result = dict(kind='fruth.response_frame_current_index', version=2, ok=True,
                  index_path=str(path), storage_backend='sqlite',
                  ledger_path=metadata['ledger_path'], ledger_name=metadata['ledger_name'],
                  ledger_size_bytes=size, ledger_line_count=metadata['ledger_line_count'],
                  ledger_line_count_verified_size_bytes=size,
                  response_map_verified_size_bytes=size, response_map_entry_count=root['count'],
                  response_map_digest=(root['digest'] if response_id is not None
                                       else hashlib.sha256(encode(responses)).hexdigest()),
                  responses=responses, sqlite_root_digest=root['digest'],
                  sqlite_generation=metadata['generation'], sqlite_algorithm=ALGORITHM,
                  sqlite_active_generation=active_generation,
                  sqlite_database_identity=metadata['database_identity'],
                  sqlite_ledger_state=metadata['ledger_state'],
                  sqlite_index_state=states[0], sqlite_selector_state=states[2],
                  sqlite_checkpoint_index_state=(selected or {}).get('index_state'),
                  ledger_chain_digest=metadata['ledger_chain_digest'])
    if response_id is not None:
        result['_sqlite_lookup_proof'] = _LookupProof(result, path, ledger_path, selector_path, states, response_id)
    # Observe the already-verified complete-map commitment, without hashing or
    # enumerating the map again. This diagnostic identity is never authority.
    state_flow_note(identity_kind='mapping_digests', identity=root['digest'])
    return result


def update(path: Path, *, selected: dict, entry: dict, ledger_path: Path,
           prior_ledger_state: dict | None, ledger_state: dict, line_count: int):
    """Advance verified coverage, accepting the same resolved path as read()."""
    before = file_state(path)
    selector_before = file_state(path.parent / SELECTOR_NAME)
    if before is None:
        raise IndexInvalid('Selected SQLite index disappeared before publication.')
    with connection(path, write=True) as conn:
        metadata = _read_metadata(conn)
        if (selected.get('index_state') != before
                or metadata['database_identity'] != identity(before)
                or metadata['generation'] != selected['generation']
                or selected.get('metadata_sha256') != hashlib.sha256(encode(metadata)).hexdigest()
                or metadata['ledger_state'] != prior_ledger_state
                or Path(metadata['ledger_path']).resolve() != ledger_path.resolve()
                or metadata['ledger_size_bytes'] != entry['byte_offset']
                or metadata['ledger_line_count'] + 1 != line_count
                or entry['byte_offset'] + entry['line_length'] != ledger_state['size_bytes']):
            raise IndexInvalid('Cannot advance uncertain SQLite index coverage.')
        root = _update(conn, metadata['root'], entry['response_id'], entry)
        metadata.update(root=root, ledger_state=ledger_state,
                        ledger_size_bytes=ledger_state['size_bytes'], ledger_line_count=line_count,
                        ledger_chain_digest=advance_chain(metadata['ledger_chain_digest'],
                                                         entry['source_frame_sha256']))
        _write_metadata(conn, metadata)
        if (file_state(ledger_path) != ledger_state
                or identity(file_state(path)) != identity(before)
                or file_state(path.parent / SELECTOR_NAME) != selector_before):
            raise IndexInvalid('SQLite index/Ledger moved before transaction commit.')
    state_flow_note(sqlite_index_transactions=1)
    return hashlib.sha256(encode(metadata)).hexdigest()


def build(path: Path, *, generation: str, entries: dict, ledger_path: Path,
          ledger_state: dict | None, line_count: int, chain_digest: str):
    """Build an inactive generation in linear tree work, then audit it."""
    if path.exists():
        raise IndexInvalid('Staged SQLite generation already exists.')
    path.touch(mode=0o600, exist_ok=False)
    conn = sqlite3.connect(str(path), isolation_level=None)
    try:
        conn.execute('PRAGMA journal_mode=DELETE')
        conn.execute('PRAGMA synchronous=FULL')
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('CREATE TABLE nodes(response_id TEXT PRIMARY KEY, body BLOB NOT NULL) WITHOUT ROWID')
        conn.execute('CREATE TABLE metadata(singleton INTEGER PRIMARY KEY CHECK(singleton=1), '
                     'payload BLOB NOT NULL, sha256 TEXT NOT NULL)')
        keys = sorted(entries)

        def balanced(start, end):
            if start == end:
                return EMPTY
            middle = (start + end) // 2
            left, right = balanced(start, middle), balanced(middle + 1, end)
            key = keys[middle]
            return _save_node(conn, key, entries[key], left, right)

        root = balanced(0, len(keys))
        _write_metadata(conn, dict(kind=KIND, version=1, algorithm=ALGORITHM,
                                  generation=generation, database_identity=identity(file_state(path)),
                                  root=root, ledger_path=str(ledger_path), ledger_name=ledger_path.name,
                                  ledger_state=ledger_state,
                                  ledger_size_bytes=ledger_state['size_bytes'] if ledger_state else 0,
                                  ledger_line_count=line_count, ledger_chain_digest=chain_digest))
        if encode(_complete_map(conn, root)) != encode(entries):
            raise IndexInvalid('Staged SQLite map differs from canonical reconstruction.')
        conn.execute('COMMIT')
    finally:
        conn.close()
    with path.open('rb') as handle:
        os.fsync(handle.fileno())
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return hashlib.sha256(encode(_read_metadata_from_file(path))).hexdigest()


def _read_metadata_from_file(path):
    with connection(path) as conn:
        return _read_metadata(conn)


def selector_payload(generation: str, backend: str) -> dict:
    return dict(kind='fruth.response_frame_index_selection', version=1,
                backend=backend, generation=generation,
                filename=f'current_index.{generation}.sqlite3' if backend == 'sqlite' else LEGACY_NAME)
