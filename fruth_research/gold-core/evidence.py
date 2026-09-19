"""Exact Gold evidence selection, retention and resolution; no runtime imports."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile

MIN_FREE_MARGIN_BYTES = 256 * 1024 * 1024
COPY_MARGIN_PERCENT = 5
IDENTITY_FIELDS = ('root_kind', 'path', 'sha256', 'byte_offset', 'byte_length')


def descriptor(ref):
    if ref.get('root_kind') not in ('state', 'artifacts'):
        raise ValueError('unsupported evidence root kind')
    return {k: ref[k] for k in IDENTITY_FIELDS if k in ref}


def evidence_id(ref):
    return hashlib.sha256(json.dumps(descriptor(ref), sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def safe_path(base, relative):
    rel = PurePosixPath(relative)
    if rel.is_absolute() or '..' in rel.parts or str(rel) != relative or '\\' in relative or not rel.parts:
        raise ValueError('unsafe evidence path')
    target = Path(base).joinpath(*rel.parts)
    if not target.resolve().is_relative_to(Path(base).resolve()):
        raise ValueError('escaping evidence symlink')
    if target.is_symlink():
        raise ValueError('evidence file symlink is not an exact byte source')
    return target


def selected_chunks(path, ref):
    sliced = 'byte_offset' in ref or 'byte_length' in ref
    if sliced and (type(ref.get('byte_offset')) is not int or type(ref.get('byte_length')) is not int
                   or ref['byte_offset'] < 0 or ref['byte_length'] <= 0):
        raise ValueError('incomplete or invalid evidence byte range')
    remaining = ref.get('byte_length')
    with path.open('rb') as stream:
        stream.seek(ref.get('byte_offset', 0))
        while remaining is None or remaining:
            block = stream.read(1024 * 1024 if remaining is None else min(remaining, 1024 * 1024))
            if not block:
                if remaining:
                    raise ValueError('short evidence range')
                break
            if remaining is not None:
                remaining -= len(block)
            yield block


def selected_digest(path, ref):
    value = hashlib.sha256()
    for block in selected_chunks(path, ref):
        value.update(block)
    return value.hexdigest()


def file_state(path):
    s = path.stat()
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def enumerate_dependencies(corpus):
    refs = {}
    for path in sorted((Path(corpus) / 'cases').glob('*.json')):
        case = json.loads(path.read_text())
        for ref in case['source']['evidence_refs']:
            key = evidence_id(ref)
            record = refs.setdefault(key, {'evidence_id': key, 'original': descriptor(ref),
                'retained_path': f'files/{key}.bin', 'retained_sha256': ref['sha256'],
                'gold_case_ids': [], 'purposes': []})
            if ref.get('canonical_sha256'):
                if record.get('canonical_sha256', ref['canonical_sha256']) != ref['canonical_sha256']:
                    raise ValueError('conflicting canonical digest')
                record['canonical_sha256'] = ref['canonical_sha256']
            if case['case_id'] not in record['gold_case_ids']:
                record['gold_case_ids'].append(case['case_id'])
            if ref['purpose'] not in record['purposes']:
                record['purposes'].append(ref['purpose'])
    return [refs[k] for k in sorted(refs)]


def load_store(store):
    if store is None or not Path(store).exists():
        return {}
    manifest = json.loads((Path(store) / 'manifest.json').read_text())
    if manifest.get('status') != 'complete' or manifest.get('schema_version') != 1:
        raise ValueError('retained evidence store is not complete')
    entries = {}
    for entry in manifest['evidence']:
        key = entry['evidence_id']
        if key in entries or key != evidence_id(entry['original']):
            raise ValueError('invalid retained evidence identity')
        entries[key] = entry
    if manifest['dependency_count'] != len(entries):
        raise ValueError('retained evidence manifest count mismatch')
    return entries


def resolve(ref, roots, *, store=None, entries=None, archives=()):
    for root in roots:
        p = safe_path(Path(root) / ref['root_kind'], ref['path'])
        if p.exists():
            return p, ref, 'live'
    entry = (entries if entries is not None else load_store(store)).get(evidence_id(ref))
    if entry is not None:
        if entry['original'] != descriptor(ref) or entry['retained_sha256'] != ref['sha256']:
            raise ValueError('retained binding disagrees with Gold')
        if ref.get('canonical_sha256') and entry.get('canonical_sha256') != ref['canonical_sha256']:
            raise ValueError('retained canonical digest disagrees with Gold')
        p = safe_path(store, entry['retained_path'])
        # A manifest promising absent retained bytes is corruption, not fallback.
        if not p.is_file():
            raise ValueError('missing retained evidence file')
        effective = dict(ref)
        effective.pop('byte_offset', None)
        effective.pop('byte_length', None)
        return p, effective, 'retained'
    for root in archives:
        p = safe_path(Path(root) / ref['root_kind'], ref['path'])
        if p.exists():
            return p, ref, 'archive'
    raise ValueError(f'missing evidence {ref["root_kind"]}/{ref["path"]}')


def inventory(corpus, root):
    entries = enumerate_dependencies(corpus)
    sources = {}
    for entry in entries:
        ref = entry['original']
        p = safe_path(Path(root) / ref['root_kind'], ref['path'])
        if not p.is_file():
            raise ValueError('missing source dependency')
        entry['selected_bytes'] = ref.get('byte_length', p.stat().st_size)
        sources[str(p)] = p.stat().st_size
    return {'dependency_count': len(entries), 'source_file_count': len(sources),
            'selected_bytes': sum(e['selected_bytes'] for e in entries),
            'source_file_bytes_represented': sum(sources.values()), 'evidence': entries}


def retain(corpus, root, destination):
    corpus, root, destination = Path(corpus), Path(root), Path(destination)
    for p in (destination, *destination.parents):
        if p.is_symlink():
            raise ValueError('retention destination cannot contain symlinks')
    if destination.exists():
        raise ValueError('retained destination exists; verify/reuse it, never overwrite')
    identities = {str(p.relative_to(corpus)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in [*sorted((corpus / 'cases').glob('*.json')), corpus / 'schema.json', corpus / 'manifest.json']}
    plan = inventory(corpus, root)
    parent = destination.parent
    ancestor = parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    margin = max(MIN_FREE_MARGIN_BYTES, (plan['selected_bytes'] * COPY_MARGIN_PERCENT + 99) // 100)
    free = shutil.disk_usage(ancestor).free
    if free < plan['selected_bytes'] + margin:
        raise ValueError('insufficient disk space for Gold retention')
    # Verify every source before creating the destination or copying any evidence.
    states = {}
    for e in plan['evidence']:
        ref = e['original']
        p = safe_path(root / ref['root_kind'], ref['path'])
        states.setdefault(p, file_state(p))
        if selected_digest(p, ref) != ref['sha256'] or file_state(p) != states[p]:
            raise ValueError('Gold source changed or digest mismatch before retention')
        if e.get('canonical_sha256') and hashlib.sha256(p.read_bytes().rstrip(b'\n')).hexdigest() != e['canonical_sha256']:
            raise ValueError('canonical source digest mismatch')
    source_digests = {}
    for p, state in states.items():
        source_digests[p] = selected_digest(p, {})
        if file_state(p) != state:
            raise ValueError('Gold source moved during source-file hashing')
    for e in plan['evidence']:
        ref = e['original']
        e['original_source_file_sha256'] = source_digests[safe_path(root / ref['root_kind'], ref['path'])]
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f'.{destination.name}.partial-', dir=parent))
    try:
        for e in plan['evidence']:
            ref = e['original']
            source = safe_path(root / ref['root_kind'], ref['path'])
            target = safe_path(staging, e['retained_path'])
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                for block in selected_chunks(source, ref):
                    stream.write(block)
                stream.flush()
                os.fsync(stream.fileno())
            if selected_digest(target, {}) != ref['sha256'] or file_state(source) != states[source]:
                raise ValueError('Gold source moved or retained byte verification failed')
            e['retained_size_bytes'] = target.stat().st_size
        if any(file_state(p) != s for p, s in states.items()):
            raise ValueError('Gold source moved during retention')
        if any(hashlib.sha256((corpus / p).read_bytes()).hexdigest() != h for p, h in identities.items()):
            raise ValueError('Gold metadata changed during retention')
        manifest = {'schema_version': 1, 'status': 'complete', 'kind': 'fruth.gold_retained_evidence',
                    'internal_only': True, 'corpus_files_sha256': identities,
                    'space_preflight': {'free_bytes': free, 'margin_bytes': margin,
                                        'required_bytes': plan['selected_bytes'] + margin}, **plan}
        with (staging / 'manifest.json').open('x') as stream:
            json.dump(manifest, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        for directory in (staging / 'files', staging):
            fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        if destination.exists():
            raise ValueError('retained destination appeared during copy')
        os.rename(staging, destination)
        fd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return manifest
    except Exception as exc:
        raise ValueError(f'Retention not accepted; partial evidence retained at {staging.name}: {exc}') from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--destination', type=Path)
    parser.add_argument('--materialize', action='store_true')
    args = parser.parse_args()
    destination = args.destination or args.corpus.parent / 'retained-evidence/gold-core-v0'
    result = retain(args.corpus, args.root, destination) if args.materialize else inventory(args.corpus, args.root)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
