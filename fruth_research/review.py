#!/usr/bin/env python3
"""Offline evidence review. Binding checks are not correctness adjudication."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
from fruth_services import research_candidates as queue

_spec = importlib.util.spec_from_file_location('research_gold_validate',
                                             Path(__file__).parent / 'gold-core/validate.py')
gold = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gold)
evidence = gold.evidence


def write_json(path, value):
    queue.atomic_write(Path(path), (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode())


def exact_read(path, ref):
    raw = b''.join(evidence.selected_chunks(path, ref))
    if queue.digest(raw) != ref['sha256']:
        raise ValueError(f'changed evidence bytes: {path}')
    return raw


def reference(path, root, ref_id, purpose, **extra):
    relative = path.relative_to(root)
    if relative.parts[0] not in ('state', 'artifacts'):
        raise ValueError('Gold evidence must be under state/ or artifacts/')
    return dict(ref_id=ref_id, root_kind=relative.parts[0],
                path=Path(*relative.parts[1:]).as_posix(), purpose=purpose,
                sha256=evidence.selected_digest(path, extra), **extra)


def audit(root):
    """One ledger scan; qualify eval-row identity and response membership separately."""
    directory = root / 'fruth_research/candidates'
    queue_path = directory / 'candidates.jsonl'
    before_queue = evidence.file_state(queue_path)
    rows = queue.read_queue(directory)
    ledger = root / 'state/response_frames/responses.jsonl'
    queue.no_symlinks(ledger)
    before_ledger = evidence.file_state(ledger)
    lineage, errors, digest, offset = {}, {}, hashlib.sha256(), 0
    with ledger.open('rb') as stream:
        for ordinal, raw in enumerate(stream):
            digest.update(raw)
            if not raw.strip():
                offset += len(raw)
                continue
            frame = gold.parse_json(raw, f'ledger row {ordinal}')
            rid, fid, seq = frame['response_id'], frame['frame_id'], frame['frame_sequence']
            prior = lineage.setdefault(rid, [])
            parent = (frame.get('frame_relation') or {}).get('parent_frame_id')
            if (prior and (seq != prior[-1]['frame_sequence'] + 1 or parent != prior[-1]['frame_id'])) or (not prior and parent):
                errors.setdefault(rid, []).append(f'broken parent/sequence at row {ordinal}')
            if any(p['frame_id'] == fid for p in prior):
                errors.setdefault(rid, []).append(f'duplicate frame id at row {ordinal}')
            prior.append(dict(byte_offset=offset, byte_length=len(raw), sha256=queue.digest(raw),
                              frame_id=fid, frame_sequence=seq, line_ordinal=ordinal))
            offset += len(raw)
    bindings, source_states = [], {}
    for row in rows.values():
        source = row['current_source']
        rid = source.get('response_id')
        refs = [r for r in source['provenance_refs'] if r.get('role') == 'source_eval_annotation']
        status, problem = 'verified', None
        try:
            if len(refs) != 1:
                raise ValueError('expected one exact eval annotation')
            ref = refs[0]
            path = evidence.safe_path(root, ref['path'])
            queue.no_symlinks(path)
            source_states.setdefault(path, evidence.file_state(path))
            item = gold.parse_json(exact_read(path, ref), str(path))
            if (item['case_id'] != row['source_case_id'] or item.get('response_id') != rid or
                    queue.digest(queue.encoded(item)) != source['source_record_sha256']):
                raise ValueError('eval annotation identity/content mismatch')
        except (OSError, ValueError, KeyError) as exc:
            status, problem = 'unverified', str(exc)
        bindings.append(dict(source_case_id=row['source_case_id'], response_id=rid,
            source_record_sha256=source['source_record_sha256'],
            case_kind=source.get('source_annotations', {}).get('case_kind'),
            disposition=row['review']['disposition'], annotation_binding=status,
            annotation_problem=problem, annotation_refs=refs,
            canonical_membership=('absent' if rid not in lineage else
                                  'broken_lineage' if rid in errors else 'present'),
            frame_count=len(lineage.get(rid, []))))
    queue_digest = evidence.selected_digest(queue_path, {})
    if (evidence.file_state(queue_path) != before_queue or evidence.file_state(ledger) != before_ledger or
            any(evidence.file_state(p) != state for p, state in source_states.items())):
        raise ValueError('source changed during audit; rerun on stable inputs')
    return dict(schema_version=1, kind='fruth.research_evidence_audit', root=str(root),
        authority='research_curation_only', runtime_effect='none',
        candidate_queue_sha256=queue_digest,
        ledger_path='state/response_frames/responses.jsonl', ledger_sha256=digest.hexdigest(),
        ledger_size_bytes=offset, ledger_responses=len(lineage),
        candidate_count=len(bindings), annotation_binding_counts=dict(Counter(b['annotation_binding'] for b in bindings)),
        membership_counts=dict(Counter(b['canonical_membership'] for b in bindings)),
        counts_by_kind=dict(Counter(b['case_kind'] for b in bindings)),
        lineage_errors=errors, lineage=lineage, candidates=bindings,
        limitations=['Membership does not rederive an eval label or prove its original frame.',
                     'Sidecars and artifacts are checked only by inspect for selected responses.',
                     'No semantic adjudication or Gold promotion is performed.'])


def inspect_response(root, audit_report, response_id):
    from fruth_services.response_frames import (
        _expand_snapshot_manifests_for_frames, _read_snapshot_ref_payload,
        response_payload_from_frame,
    )
    if str(root) != audit_report['root']:
        raise ValueError('audit belongs to a different root')
    if response_id in audit_report['lineage_errors']:
        raise ValueError('cannot inspect broken lineage')
    coordinates = audit_report['lineage'][response_id]
    ledger = evidence.safe_path(root, audit_report['ledger_path'])
    frames, refs = [], []
    for number, coord in enumerate(coordinates):
        frame = gold.parse_json(exact_read(ledger, coord), str(ledger))
        if frame['response_id'] != response_id or frame['frame_id'] != coord['frame_id']:
            raise ValueError('audit/frame identity mismatch')
        frames.append(frame)
        refs.append(reference(ledger, root, f'frame-{number}', 'Exact canonical lineage row.',
                              byte_offset=coord['byte_offset'], byte_length=coord['byte_length']))
        refs[-1]['sha256'] = coord['sha256']
    frame = _expand_snapshot_manifests_for_frames(frames)[-1]
    frames_dir = ledger.parent
    checked, failures = {}, []

    def check_ref(ref):
        key = (ref.get('path'), ref.get('sha256'))
        if key in checked:
            return
        checked[key] = True
        path = evidence.safe_path(frames_dir, ref['path'])
        queue.no_symlinks(path)
        before = evidence.file_state(path) if path.exists() else None
        payload = _read_snapshot_ref_payload(ref, frames_dir=frames_dir, expand_child_refs=False)
        if payload is None:
            failures.append(ref['path'])
            return
        refs.append(reference(path, root, f'sidecar-{len(checked)}',
                              'Effective canonical sidecar, including nested dependencies.',
                              canonical_sha256=ref['sha256']))
        if evidence.file_state(path) != before:
            raise ValueError('sidecar changed during inspection')
        walk(payload)
        walk(ref.get('sidecar_manifest', {}))

    def walk(value):
        if isinstance(value, dict):
            if value.get('path') and value.get('sha256') and (
                    'snapshot' in str(value.get('kind', '')) or value.get('storage') == 'sidecar_json'
                    or value.get('content_addressed') is True):
                check_ref(value)
            for key, item in value.items():
                if key.endswith('_snapshot_ref') and isinstance(item, dict) and item.get('sha256'):
                    check_ref(item)
                else:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    for ref in frame.get('external_snapshots', {}).get('items', {}).values():
        check_ref(ref)
    walk(frame)
    payload = response_payload_from_frame(frame, frames_dir=frames_dir)
    artifacts = []
    for item in frame.get('artifacts', {}).get('output', []):
        raw_path = item.get('path')
        if not raw_path:
            continue
        path = Path(raw_path)
        if not path.is_absolute():
            path = root / path
        try:
            path.relative_to(root / 'artifacts')
            queue.no_symlinks(path)
            actual = evidence.selected_digest(path, {})
            declared = item.get('file_sha256') or item.get('content_sha256')
            ok = actual == declared if declared else None
            refs.append(reference(path, root, f'artifact-{len(artifacts)}', 'Saved producer artifact bytes.'))
            refs[-1]['sha256'] = actual
            artifacts.append(dict(artifact_id=item.get('artifact_id'), path=str(path),
                                  sha256=actual, declared_sha256=declared, matches_declared=ok,
                                  digest_status=('verified' if ok else 'mismatch' if declared else 'producer_digest_absent')))
        except (OSError, ValueError) as exc:
            artifacts.append(dict(path=str(path), error=str(exc), matches_declared=False))
    candidates = [c for c in audit_report['candidates'] if c['response_id'] == response_id]
    for number, candidate in enumerate(candidates):
        if candidate['annotation_binding'] == 'verified':
            ref = candidate['annotation_refs'][0]
            path = evidence.safe_path(root, ref['path'])
            exact_read(path, ref)
            refs.append(reference(path, root, f'eval-{number}', 'Source eval annotation; not adjudication.',
                                  byte_offset=ref['byte_offset'], byte_length=ref['byte_length']))
            refs[-1]['sha256'] = ref['sha256']
    for ref in refs:
        path = evidence.safe_path(root / ref['root_kind'], ref['path'])
        if evidence.selected_digest(path, ref) != ref['sha256']:
            raise ValueError('source changed during response inspection')
    return dict(schema_version=1, kind='fruth.research_response_inspection', response_id=response_id,
        frame_id=frame['frame_id'], frame_count=len(frames),
        prompt=frame.get('request', {}).get('prompt'), lifecycle=payload.get('lifecycle_state'),
        closure=payload.get('runtime', {}).get('graph_closure_review', {}).get('status'),
        error=payload.get('error'), output_text=payload.get('output_text'),
        sidecars_checked=len(checked), failed_sidecars=failures, artifacts=artifacts,
        evidence_refs=refs, candidates=candidates,
        limitations=['Historical inspected epoch; later appended frames are not included.',
                     'Digest and membership checks do not adjudicate natural-language correctness.'])


def offline_guard(output):
    """Keep canonical reader imports from acquiring execution/write authority."""
    parent = output.resolve().parent

    def guard(event, args):
        if event in ('socket.connect', 'socket.bind', 'subprocess.Popen', 'os.system'):
            raise RuntimeError('offline review rejects ' + event)
        if event == 'open':
            name, mode, flags = args
            writing = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
            if writing and isinstance(name, (str, bytes)) and Path(os.fsdecode(name)).resolve().parent != parent:
                raise RuntimeError('offline review rejects write outside output directory')
    sys.addaudithook(guard)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    commands = parser.add_subparsers(dest='command', required=True)
    a = commands.add_parser('audit', help='Scan candidate bindings and ledger once, without changing dispositions.')
    a.add_argument('--output', type=Path, required=True)
    i = commands.add_parser('inspect', help='Inspect exact audited response lineage and saved evidence.')
    i.add_argument('--audit', type=Path, required=True)
    i.add_argument('--response-id', required=True)
    i.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError('output exists; choose a new audit/inspection filename')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        offline_guard(args.output)
        result = audit(args.root.resolve()) if args.command == 'audit' else inspect_response(
            args.root.resolve(), gold.read_json(args.audit), args.response_id)
        if args.output.exists():
            raise ValueError('output exists; choose a new audit/inspection filename')
        write_json(args.output, result)
        print(json.dumps({k: v for k, v in result.items() if k not in
            ('lineage', 'candidates', 'evidence_refs', 'output_text', 'prompt', 'artifacts')}, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        print(json.dumps({'status': 'failed', 'error': str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
