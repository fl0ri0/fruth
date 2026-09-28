#!/usr/bin/env python3
"""Add explicitly adjudicated Gold cases and retain their exact evidence offline."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fruth_research.review import ROOT, evidence, exact_read, gold, queue, write_json


def file_digest(path):
    queue.no_symlinks(path)
    return evidence.selected_digest(path, {}) if path.exists() else None


def update_manifest(corpus, previous):
    cases = [gold.read_json(p) for p in sorted((corpus / 'cases').glob('*.json'))]
    manifest = dict(previous, schema_version='1.0.0', corpus_version='v0',
                    last_curated_on=date.today().isoformat(), comprehensive=False,
                    case_count=len(cases), case_ids=sorted(c['case_id'] for c in cases),
                    **gold.counts(cases))
    write_json(corpus / 'manifest.json', manifest)
    return manifest


def candidate_reviews(rows, cases, root):
    """Only explicit case references can mark an exact source version promoted."""
    rows = deepcopy(rows)
    links = {}
    for case in cases:
        for sid in case['source']['eval_case_ids']:
            row = rows[queue.candidate_id(sid)]
            source = row['current_source']
            if source['response_id'] not in case['source']['response_ids']:
                raise ValueError('candidate/Gold response identity mismatch')
            bound = False
            for annotation in source['provenance_refs']:
                if annotation.get('role') != 'source_eval_annotation':
                    continue
                item = gold.parse_json(exact_read(evidence.safe_path(root, annotation['path']), annotation), sid)
                if (item['case_id'] != sid or item.get('response_id') != source['response_id'] or
                        queue.digest(queue.encoded(item)) != source['source_record_sha256']):
                    raise ValueError('candidate source content changed')
                for ref in case['source']['evidence_refs']:
                    if (f"{ref['root_kind']}/{ref['path']}" == annotation['path'] and
                            all(ref.get(k) == annotation.get(k) for k in ('sha256', 'byte_offset', 'byte_length'))):
                        bound = True
            if not bound:
                raise ValueError('Gold case must retain the exact reviewed candidate annotation')
            links.setdefault(sid, []).append(case['case_id'])
    for sid, ids in links.items():
        row = rows[queue.candidate_id(sid)]
        old = row['review']
        new = dict(disposition='promoted', gold_case_ids=sorted(set(old['gold_case_ids'] + ids)),
                   notes='Explicit Gold adjudication; see linked cases for scope and limitations.',
                   reviewed_source_sha256=row['current_source']['source_record_sha256'])
        if new != old:
            row.setdefault('review_history', []).append(dict(old))
            row['review'] = new
            row['review_source_changed'] = False
    return rows


def stage(root, case_paths, work):
    research = root / 'fruth_research'
    corpus, store = research / 'gold-core', research / 'retained-evidence/gold-core-v0'
    observed = {p: file_digest(p) for p in [corpus / 'schema.json', corpus / 'manifest.json',
        store / 'manifest.json', research / 'candidates/candidates.jsonl',
        research / 'candidates/manifest.json', *sorted((corpus / 'cases').glob('*.json'))]}
    original = {p.name: p.read_bytes() for p in sorted((corpus / 'cases').glob('*.json'))}
    if original:
        gold.validate(corpus, [], retained=store)
    schema = gold.read_json(corpus / 'schema.json')
    incoming = {}
    for path in case_paths:
        raw = path.read_bytes()
        case = gold.parse_json(raw, str(path))
        gold.check_schema(case, schema)
        name = case['case_id'] + '.json'
        if name in incoming and incoming[name] != raw:
            raise ValueError('conflicting input case id')
        if name in original and original[name] != raw:
            raise ValueError('existing Gold case is immutable; conflicting case id')
        incoming[name] = raw
    added = {name: raw for name, raw in incoming.items() if name not in original}
    if not added:
        return {'status': 'unchanged', 'added_case_ids': []}
    fresh = work / 'fresh'
    (fresh / 'cases').mkdir(parents=True)
    shutil.copyfile(corpus / 'schema.json', fresh / 'schema.json')
    for name, raw in added.items():
        (fresh / 'cases' / name).write_bytes(raw)
    update_manifest(fresh, {})
    gold.validate(fresh, [root], retained=work / 'no-store')
    cases = [gold.parse_json(raw, name) for name, raw in added.items()]
    directory = research / 'candidates'
    rows = candidate_reviews(queue.read_queue(directory), cases, root)
    # Existing retention owner performs disk preflight, source stability/digest
    # checks and exact range copies. No full ledger copy is required for slices.
    evidence.retain(fresh, root, work / 'new-store')
    staged_corpus, staged_store = work / 'combined', work / 'combined-store'
    (staged_corpus / 'cases').mkdir(parents=True)
    shutil.copyfile(corpus / 'schema.json', staged_corpus / 'schema.json')
    for name, raw in {**original, **added}.items():
        (staged_corpus / 'cases' / name).write_bytes(raw)
    update_manifest(staged_corpus, gold.read_json(corpus / 'manifest.json'))
    entries = evidence.load_store(store)
    new_entries = evidence.load_store(work / 'new-store')
    (staged_store / 'files').mkdir(parents=True)
    combined = []
    for dependency in evidence.enumerate_dependencies(staged_corpus):
        key = dependency['evidence_id']
        source_store = store if key in entries else work / 'new-store'
        entry = deepcopy(entries[key] if key in entries else new_entries[key])
        entry.update(gold_case_ids=dependency['gold_case_ids'], purposes=dependency['purposes'])
        target = evidence.safe_path(staged_store, entry['retained_path'])
        os.link(evidence.safe_path(source_store, entry['retained_path']), target)
        combined.append(entry)
    retained_manifest = dict(schema_version=1, status='complete', kind='fruth.gold_retained_evidence',
        internal_only=True, dependency_count=len(combined),
        selected_bytes=sum(e['retained_size_bytes'] for e in combined), evidence=combined,
        corpus_files_sha256={str(p.relative_to(staged_corpus)): file_digest(p)
            for p in [*sorted((staged_corpus / 'cases').glob('*.json')),
                      staged_corpus / 'schema.json', staged_corpus / 'manifest.json']},
        retention_policy='Additive curation; existing retained bytes are reused unchanged.')
    write_json(staged_store / 'manifest.json', retained_manifest)
    validation = gold.validate(staged_corpus, [], retained=staged_store)
    candidate_manifest = gold.read_json(directory / 'manifest.json')
    queue.publish(work / 'queue', rows, candidate_manifest['source_generation'])
    operations = []

    def publish_file(source, target):
        before, after = file_digest(target), file_digest(source)
        if before == after:
            return
        index = len(operations)
        publication = work / 'publish' / str(index)
        publication.parent.mkdir(exist_ok=True)
        os.link(source, publication)
        if before is not None:
            backup = work / 'before' / str(index)
            backup.parent.mkdir(exist_ok=True)
            shutil.copyfile(target, backup)
        operations.append(dict(target=str(target.relative_to(research)),
                               source=str(publication.relative_to(work)), before=before, after=after))

    # Bytes first, then retained manifest, cases, Gold manifest, and finally queue.
    # Publication is recoverable, not a multi-file atomic transaction.
    for key, entry in new_entries.items():
        if key not in entries:
            publish_file(evidence.safe_path(staged_store, entry['retained_path']),
                         evidence.safe_path(store, entry['retained_path']))
    publish_file(staged_store / 'manifest.json', store / 'manifest.json')
    for name in sorted(added):
        publish_file(staged_corpus / 'cases' / name, corpus / 'cases' / name)
    publish_file(staged_corpus / 'manifest.json', corpus / 'manifest.json')
    for name in ('candidates.jsonl', 'manifest.json'):
        publish_file(work / 'queue' / name, directory / name)
    journal = dict(schema_version=1, status='prepared', operations=operations,
        added_case_ids=sorted(c['case_id'] for c in cases), validation=validation,
        added_evidence_bytes=sum(e['retained_size_bytes'] for k, e in new_entries.items() if k not in entries))
    if any(file_digest(p) != digest for p, digest in observed.items()) or set(original) != {
            p.name for p in (corpus / 'cases').glob('*.json')}:
        raise ValueError('Research source changed during curation preparation')
    write_json(work / 'journal.json', journal)
    for p in work.rglob('*'):
        if p.is_file():
            with p.open('rb') as stream:
                os.fsync(stream.fileno())
    for p in sorted((p for p in work.rglob('*') if p.is_dir()), reverse=True):
        sync_directory(p)
    sync_directory(work)
    return journal


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def finish(research, pending):
    journal = gold.read_json(pending / 'journal.json')
    allowed = ('gold-core/cases/', 'retained-evidence/gold-core-v0/files/')
    metadata = {'gold-core/manifest.json', 'retained-evidence/gold-core-v0/manifest.json',
                'candidates/candidates.jsonl', 'candidates/manifest.json'}
    # Check every conflict before resuming any write. Never overwrite unrelated
    # changes, including a queue synced after an interrupted publication.
    for op in journal['operations']:
        if op['target'] not in metadata and not op['target'].startswith(allowed):
            raise ValueError('invalid curation publication target')
        target, source = evidence.safe_path(research, op['target']), evidence.safe_path(pending, op['source'])
        if file_digest(target) not in (op['before'], op['after']) or file_digest(source) != op['after']:
            raise ValueError(f'curation recovery conflict: {op["target"]}')
    for op in journal['operations']:
        target, source = research / op['target'], pending / op['source']
        if file_digest(target) == op['after']:
            continue
        if file_digest(target) != op['before']:
            raise ValueError('target changed during publication')
        if op['before'] is None:
            target.parent.mkdir(parents=True, exist_ok=True)
            os.link(source, target)
            sync_directory(target.parent)
        else:
            queue.atomic_write(target, source.read_bytes())
    result = dict(status='completed', added_case_ids=journal['added_case_ids'],
                  added_evidence_bytes=journal['added_evidence_bytes'],
                  validation=gold.validate(research / 'gold-core', [],
                      retained=research / 'retained-evidence/gold-core-v0'))
    receipt = research / 'curation-receipts' / queue.digest(queue.encoded(journal))
    receipt.mkdir(parents=True, exist_ok=True)
    write_json(receipt / 'result.json', result)
    shutil.copyfile(pending / 'journal.json', receipt / 'journal.json')
    if (pending / 'before').exists() and not (receipt / 'before').exists():
        shutil.copytree(pending / 'before', receipt / 'before')
    shutil.rmtree(pending)
    return result


def curate(root, case_paths=(), *, apply=False, resume=False):
    research = root / 'fruth_research'
    queue.no_symlinks(research)
    pending = research / '.curation-pending'
    with queue.queue_lock(research / 'gold-core'), queue.queue_lock(research / 'candidates'):
        if resume:
            return finish(research, pending)
        if pending.exists():
            raise ValueError('unfinished curation exists; inspect .curation-pending and use --resume')
        with tempfile.TemporaryDirectory(prefix='.curation-stage-', dir=research) as temp:
            work = Path(temp)
            journal = stage(root, case_paths, work)
            if journal['status'] == 'unchanged':
                return journal
            if not apply:
                return {k: v for k, v in journal.items() if k != 'operations'}
            os.rename(work, pending)
            sync_directory(research)
            return finish(research, pending)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--case', type=Path, action='append', default=[])
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--apply', action='store_true', help='Publish the validated additive curation.')
    action.add_argument('--resume', action='store_true', help='Finish the exact pending publication after interruption.')
    args = parser.parse_args()
    if bool(args.case) == args.resume:
        parser.error('provide --case (repeatable), or --resume without cases')
    try:
        print(json.dumps(curate(args.root.resolve(), args.case, apply=args.apply, resume=args.resume), indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'failed', 'error': str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
