#!/usr/bin/env python3
"""Offline curation/index checks. Never imports or executes Fruth runtime owners."""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import sys

_spec = importlib.util.spec_from_file_location('fruth_gold_evidence', Path(__file__).with_name('evidence.py'))
evidence = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(evidence)


class Invalid(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def read_json(path):
    return parse_json(path.read_text(), str(path))


def parse_json(data, name):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"{name}: duplicate JSON key {key}")
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(Invalid(value)))


def check_schema(value, schema, where='$'):
    """Validate the documented JSON Schema subset used by schema.json.

    Fail on unsupported keywords rather than silently ignoring new constraints.
    This is deliberately not a general JSON Schema implementation.
    """
    supported = {'$schema', 'title', 'description', 'type', 'properties', 'required',
                 'additionalProperties', 'items', 'minItems', 'uniqueItems', 'enum',
                 'const', 'minLength', 'pattern', 'minimum'}
    require(not (set(schema) - supported), f'{where}: unsupported schema keywords')
    types = {'object': dict, 'array': list, 'string': str, 'integer': int,
             'boolean': bool, 'null': type(None)}
    if 'type' in schema:
        require(schema['type'] in types, f'{where}: unsupported type')
        require(type(value) is types[schema['type']], f'{where}: expected {schema["type"]}')
    if 'enum' in schema:
        require(value in schema['enum'], f'{where}: invalid enum {value!r}')
    if 'const' in schema:
        require(type(value) is type(schema['const']) and value == schema['const'],
                f'{where}: invalid constant')
    if isinstance(value, dict):
        require(set(schema.get('required', [])) <= value.keys(), f'{where}: missing required fields')
        properties = schema.get('properties', {})
        if schema.get('additionalProperties') is False:
            require(value.keys() <= properties.keys(), f'{where}: unexpected fields')
        for key, child in value.items():
            if key in properties:
                check_schema(child, properties[key], f'{where}/{key}')
            elif isinstance(schema.get('additionalProperties'), dict):
                check_schema(child, schema['additionalProperties'], f'{where}/{key}')
    if isinstance(value, list):
        require(len(value) >= schema.get('minItems', 0), f'{where}: too few items')
        if schema.get('uniqueItems'):
            encoded = [json.dumps(x, sort_keys=True) for x in value]
            require(len(encoded) == len(set(encoded)), f'{where}: duplicate items')
        for index, child in enumerate(value):
            check_schema(child, schema.get('items', {}), f'{where}/{index}')
    if isinstance(value, str):
        require(len(value) >= schema.get('minLength', 0), f'{where}: empty string')
        if 'pattern' in schema:
            require(re.search(schema['pattern'], value) is not None, f'{where}: pattern mismatch')
    if type(value) is int and 'minimum' in schema:
        require(value >= schema['minimum'], f'{where}: below minimum')


def evidence_bytes(path, ref):
    if 'byte_offset' in ref or 'byte_length' in ref:
        require('byte_offset' in ref and 'byte_length' in ref, 'incomplete byte range')
        require(ref['byte_length'] > 0, 'empty byte range')
        with path.open('rb') as handle:
            handle.seek(ref['byte_offset'])
            value = handle.read(ref['byte_length'])
        require(len(value) == ref['byte_length'], 'short evidence range')
        return value
    return None


def digest(path, ref=None):
    selected = evidence_bytes(path, ref or {})
    if selected is not None:
        return hashlib.sha256(selected).hexdigest()
    result = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def pointer(document, path):
    require(path == '' or path.startswith('/'), 'invalid JSON pointer')
    for part in path.split('/')[1:]:
        require(re.search(r'~(?![01])', part) is None, 'invalid pointer escape')
        part = part.replace('~1', '/').replace('~0', '~')
        if isinstance(document, list):
            require(re.fullmatch(r'0|[1-9][0-9]*', part) is not None, 'invalid array pointer')
            document = document[int(part)]
        else:
            document = document[part]
    return document


def semantic_key(case):
    return [case['semantic_dedup']['intent_shape'], sorted(case['boundaries']),
            case['expected_outcome'], case['semantic_dedup']['trajectory_role']]


def counts(cases):
    result = {}
    for label in ('case_role', 'reproducibility', 'evidence_quality'):
        result['counts_by_' + label] = dict(sorted(Counter(c[label] for c in cases).items()))
    result['counts_by_boundary'] = dict(sorted(Counter(
        b for c in cases for b in c['boundaries']).items()))
    result['source_campaigns'] = sorted({c['source']['campaign_id'] for c in cases})
    return result


def validate(corpus, roots, *, retained=None, archives=()):
    retained = Path(retained) if retained is not None else corpus.parent / 'retained-evidence/gold-core-v0'
    try:
        retained_entries = evidence.load_store(retained)
    except (OSError, ValueError, KeyError) as exc:
        raise Invalid(str(exc)) from exc
    resolution_counts = Counter()
    schema = read_json(corpus / 'schema.json')
    paths = sorted((corpus / 'cases').glob('*.json'))
    require(paths, 'empty corpus')
    cases = [read_json(path) for path in paths]
    ids, keys, checked, decoded = set(), {}, {}, {}
    fact_count = 0
    for path, case in zip(paths, cases):
        check_schema(case, schema, path.name)
        cid = case['case_id']
        require(cid not in ids, f'duplicate case id: {cid}')
        ids.add(cid)
        require(path.stem == cid, f'{cid}: filename mismatch')
        key = json.dumps(semantic_key(case))
        keys.setdefault(key, []).append(case)
        refs = {}
        for ref in case['source']['evidence_refs']:
            rid = ref['ref_id']
            require(rid not in refs, f'{cid}: duplicate evidence id {rid}')
            rel = PurePosixPath(ref['path'])
            require(not rel.is_absolute() and '..' not in rel.parts and str(rel) == ref['path']
                    and '\\' not in ref['path'] and rel.parts, f'{cid}: unsafe evidence path')
            try:
                resolved, effective_ref, origin = evidence.resolve(
                    ref, roots, store=retained, entries=retained_entries, archives=archives)
            except (OSError, ValueError, KeyError) as exc:
                raise Invalid(f'{cid}: {exc}') from exc
            require(resolved is not None and resolved.is_file(), f'{cid}: missing evidence {ref["path"]}')
            binding = (resolved, effective_ref.get('byte_offset'), effective_ref.get('byte_length'))
            resolution_counts[origin] += 1
            if binding not in checked:
                checked[binding] = digest(resolved, effective_ref)
            require(checked[binding] == ref['sha256'], f'{cid}: digest mismatch {rid}')
            if 'canonical_sha256' in ref:
                require(hashlib.sha256(resolved.read_bytes().rstrip(b'\n')).hexdigest()
                        == ref['canonical_sha256'], f'{cid}: canonical CAS digest mismatch {rid}')
            refs[rid] = (resolved, effective_ref, binding)
        for fact in case['evidence_assertions']:
            require(fact['ref_id'] in refs, f'{cid}: unknown assertion ref')
            target, ref, binding = refs[fact['ref_id']]
            if binding not in decoded:
                selected = evidence_bytes(target, ref)
                decoded[binding] = parse_json(selected, str(target)) if selected is not None else read_json(target)
            actual = pointer(decoded[binding], fact['pointer'])
            require(json.dumps(actual, sort_keys=True) == json.dumps(fact['equals'], sort_keys=True),
                    f'{cid}: evidence assertion mismatch {fact["pointer"]}')
            fact_count += 1
        for section in ('adjudication', 'corrected_outcome'):
            for rid in case.get(section, {}).get('evidence_refs', []):
                require(rid in refs, f'{cid}: unknown {section} evidence ref')
        contract = case['contract']
        if case['historical_result'] == 'defect':
            require(case['case_role'] == 'defect_regression', f'{cid}: defect role mismatch')
        if case['case_role'] == 'defect_regression':
            require(case['historical_result'] == 'defect', f'{cid}: missing historical defect')
            require(bool(case['historical_observation'].get('violation')) and
                    bool(case['historical_observation'].get('causal_classification')),
                    f'{cid}: defect needs violation and causal classification')
            require(contract['desired_behavior'] != case['historical_observation']['violation'],
                    f'{cid}: historical defect used as gold contract')
            require('corrected_outcome' in case and case['corrected_outcome']['evidence_refs'],
                    f'{cid}: selected defect lacks fix evidence')
        if case['case_role'] == 'correct_negative':
            require(case['historical_result'] == 'correct' and
                    case['expected_outcome'] != 'fulfilled' and not contract['requires_fulfillment'],
                    f'{cid}: correct negative requires fulfillment or is a defect')
        require(case['adjudication']['status'] != 'unresolved' and
                case['evidence_quality'] != 'incomplete', f'{cid}: uncertain case promoted')
    for group in keys.values():
        if len(group) > 1:
            require(all(c['semantic_dedup'].get('duplicate_rationale', '').strip() for c in group),
                    'duplicate semantic key without explicit rationale on every case')
    manifest = read_json(corpus / 'manifest.json')
    require(manifest['schema_version'] == '1.0.0' and manifest['corpus_version'] == 'v0',
            'manifest version mismatch')
    require(manifest['case_count'] == len(cases), 'manifest case count mismatch')
    require(manifest['case_ids'] == sorted(ids), 'manifest case ids mismatch')
    for field, expected in counts(cases).items():
        require(manifest[field] == expected, f'manifest {field} mismatch')
    return {'status': 'passed', 'case_count': len(cases),
            'unique_evidence_files': len({key[0] for key in checked}),
            'evidence_assertions_checked': fact_count, 'historical_cases_executed': 0,
            'evidence_digests_checked': len(checked), 'resolution_counts': dict(resolution_counts)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--evidence-root', type=Path, action='append',
                        help='Explicit topology root containing state/; repeat for ordered fallback. '
                             'Defaults to this checkout. No archive search is automatic.')
    parser.add_argument('--retained-only', action='store_true',
                        help='Explicit historical audit using only the selected retained store.')
    parser.add_argument('--retained-store', type=Path, help='Defaults to sibling retained-evidence/gold-core-v0.')
    parser.add_argument('--archive-root', type=Path, action='append', default=[],
                        help='Explicit snapshot topology, tried after live roots and retained store.')
    args = parser.parse_args()
    if args.retained_only and (args.evidence_root or args.archive_root):
        parser.error('--retained-only cannot be combined with live/archive roots')
    roots = [] if args.retained_only else args.evidence_root or [Path(__file__).resolve().parents[2]]
    try:
        print(json.dumps(validate(args.corpus, roots, retained=args.retained_store, archives=args.archive_root), indent=2))
    except (Invalid, OSError, ValueError, KeyError, IndexError, TypeError) as error:
        print(json.dumps({'status': 'failed', 'error': str(error)}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
