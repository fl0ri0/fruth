"""Secondary, one-way research metadata queue. Never reads or writes Gold/runtime truth."""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile

DISPOSITIONS = {'unreviewed', 'promoted', 'deferred', 'rejected', 'superseded'}
MAX_SOURCE_VERSIONS = 32
INTENT_PREVIEW_CHARACTERS = 500


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def no_symlinks(path):
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError(f'research paths cannot contain symlinks: {part}')


def atomic_write(path, data):
    no_symlinks(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextmanager
def queue_lock(directory):
    no_symlinks(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / '.sync.lock'
    no_symlinks(path)
    with path.open('a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def read_queue(directory):
    path = directory / 'candidates.jsonl'
    no_symlinks(path)
    rows = {}
    if path.exists():
        for line in path.read_text().splitlines():
            row = json.loads(line)
            cid = row['candidate_id']
            if cid in rows or row['review']['disposition'] not in DISPOSITIONS:
                raise ValueError('invalid or duplicate research candidate')
            if cid != candidate_id(row['source_case_id']):
                raise ValueError('candidate/source identity mismatch')
            rows[cid] = row
    return rows


def candidate_id(source_id):
    return 'research-' + digest(source_id.encode())


def availability(row, root):
    """Availability only, not canonical reconstruction or correctness adjudication."""
    refs = row['current_source']['provenance_refs']
    available = 0
    missing = []
    for ref in refs:
        p = Path(ref['path'])
        if p.is_absolute() or '..' in p.parts:
            missing.append('unsafe_reference')
            continue
        target = root / p
        no_symlinks(target)
        good = target.is_file()
        if good and ref.get('sha256'):
            with target.open('rb') as f:
                f.seek(ref.get('byte_offset', 0))
                data = f.read(ref['byte_length']) if 'byte_length' in ref else f.read()
            good = digest(data) == ref['sha256']
        if good:
            available += 1
        else:
            missing.append(ref['path'])
    status = 'provenance_available' if available == len(refs) and refs else 'provenance_partial' if available else 'source_missing'
    return {'status': status, 'available_reference_count': available,
            'missing_or_changed_references': missing,
            'meaning': 'Referenced bytes/paths available; does not verify response membership or canonical semantics.'}


def publish(directory, rows, generation):
    ordered = [rows[k] for k in sorted(rows)]
    data = b''.join(encoded(row) + b'\n' for row in ordered)
    manifest = {'schema_version': 1, 'kind': 'ollmo.research_candidate_manifest',
                'candidate_count': len(ordered), 'source_generation': generation,
                'candidates_sha256': digest(data),
                'counts_by_disposition': dict(sorted(Counter(r['review']['disposition'] for r in ordered).items())),
                'counts_by_provenance_status': dict(sorted(Counter(r['provenance']['status'] for r in ordered).items())),
                'authority': 'research_curation_only', 'runtime_effect': 'none'}
    # Primary ledger is atomic. Manifest is derived and can be repaired by resync.
    atomic_write(directory / 'candidates.jsonl', data)
    atomic_write(directory / 'manifest.json', json.dumps(manifest, indent=2).encode() + b'\n')
    return manifest


def sync_candidates(source, directory, *, root, expected_source_sha256=None):
    source, directory, root = Path(source).absolute(), Path(directory).absolute(), Path(root).absolute()
    no_symlinks(source)
    relative = str(source.relative_to(root))
    raw = source.read_bytes()
    generation = digest(raw)
    if expected_source_sha256 and generation != expected_source_sha256:
        raise ValueError('self-learning source changed before secondary sync')
    source_rows, offset, seen = [], 0, set()
    for line in raw.splitlines(keepends=True):
        if line.strip():
            item = json.loads(line)
            sid = item.get('case_id')
            if not isinstance(sid, str) or not sid or sid in seen:
                raise ValueError('missing or duplicate source case id')
            seen.add(sid)
            source_rows.append((item, offset, line))
        offset += len(line)
    with queue_lock(directory):
        rows = read_queue(directory)
        for row in rows.values():
            row['source_present_in_latest_generation'] = False
        for item, offset, line in source_rows:
            sid = item['case_id']
            cid = candidate_id(sid)
            source_sha = digest(encoded(item))
            prompt = item.get('prompt') if isinstance(item.get('prompt'), str) else ''
            bindings = item.get('metadata', {}).get('graph_rebase_corpus', {}).get('bindings', [])
            binding_ids = [{k: b[k] for k in ('response_id', 'frame_id', 'frame_sequence', 'corpus_id', 'case_id') if k in b}
                           for b in bindings if isinstance(b, dict)]
            provenance = [{'path': relative, 'byte_offset': offset, 'byte_length': len(line),
                           'sha256': digest(line), 'role': 'source_eval_annotation'}]
            if item.get('response_id'):
                provenance.append({'path': 'state/response_frames/responses.jsonl',
                                   'role': 'possible_canonical_source_not_membership_proof'})
            current = {'source_record_sha256': source_sha, 'source_generation': generation,
                       'response_id': item.get('response_id'), 'annotated_frame_bindings': binding_ids,
                       'canonical_binding_status': 'historical_annotation_unverified' if binding_ids else 'not_verified',
                       'intent_hint': {'preview': prompt[:INTENT_PREVIEW_CHARACTERS],
                                       'full_character_count': len(prompt), 'preview_truncated': len(prompt) > INTENT_PREVIEW_CHARACTERS,
                                       'sha256': digest(prompt.encode()), 'authority': 'source_prompt_only'},
                       'source_tags': [item[k] for k in ('layer', 'case_kind', 'target_area') if item.get(k)],
                       'source_annotations': {k: item[k] for k in ('case_kind', 'severity', 'frame_status', 'evidence', 'summary') if k in item},
                       'provenance_refs': provenance}
            row = rows.setdefault(cid, {'schema_version': 1, 'candidate_id': cid,
                'source_case_id': sid, 'first_seen': generation, 'source_versions': [],
                'review_history': [],
                'review': {'disposition': 'unreviewed', 'gold_case_ids': [], 'notes': '', 'reviewed_source_sha256': None},
                'external_share_status': 'review_required', 'authority': 'research_curation_only', 'runtime_effect': 'none'})
            previous = row.get('current_source')
            if previous and row['review']['disposition'] != 'unreviewed' and not row['review'].get('reviewed_source_sha256'):
                row['review']['reviewed_source_sha256'] = previous['source_record_sha256']
            if not any(v['source_record_sha256'] == source_sha for v in row['source_versions']):
                if len(row['source_versions']) >= MAX_SOURCE_VERSIONS:
                    raise ValueError('research source version limit reached; explicit history maintenance required')
                row['source_versions'].append(current)
            row.update(current_source=current, last_seen=generation, source_present_in_latest_generation=True)
            row['review_source_changed'] = bool(row['review'].get('reviewed_source_sha256') and row['review']['reviewed_source_sha256'] != source_sha)
        for row in rows.values():
            row['provenance'] = availability(row, root)
        if source.read_bytes() != raw:
            raise ValueError('self-learning source moved during research sync')
        return publish(directory, rows, generation)


def refresh_availability(directory, *, root):
    directory = Path(directory)
    with queue_lock(directory):
        rows = read_queue(directory)
        for row in rows.values():
            row['provenance'] = availability(row, Path(root))
        return publish(directory, rows, 'availability-refresh')


def set_review(directory, source_case_id, *, disposition, gold_case_ids=(), notes=''):
    if disposition not in DISPOSITIONS:
        raise ValueError('invalid research disposition')
    directory = Path(directory)
    with queue_lock(directory):
        rows = read_queue(directory)
        row = rows[candidate_id(source_case_id)]
        row.setdefault('review_history', []).append(dict(row['review']))
        row['review'] = {'disposition': disposition, 'gold_case_ids': list(gold_case_ids),
                         'notes': notes, 'reviewed_source_sha256': row['current_source']['source_record_sha256']}
        row['review_source_changed'] = False
        return publish(directory, rows, row['last_seen'])


def sync_after_learning_persist(target, payload):
    """Only the conventional path has an implicit Research destination.

    Custom paths remain opt-in through the explicit sync CLI; no hard-coded
    checkout lookup can redirect a temporary learning writer into production.
    """
    target = Path(target).absolute()
    if target.name != 'eval_cases.jsonl' or target.parent.name != 'self_learning' or target.parent.parent.name != 'state':
        return
    root = target.parent.parent.parent
    sync_candidates(target, root / 'ollmo_research/candidates', root=root,
                    expected_source_sha256=digest(payload))
