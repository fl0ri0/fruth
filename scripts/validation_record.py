#!/usr/bin/env python3
"""Exact declared-closure inventories and contemporaneous runner receipts.

No installation, network, runtime imports, or inferred wheel provenance. Packaging
is already a pytest dependency; archive-only verification uses only the stdlib.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
from pathlib import Path
import re
import ssl
import sys
import sysconfig
import xml.etree.ElementTree as ET

if __package__:
    from . import build_release_archive as release
else:
    import build_release_archive as release

VALIDATION_ROOTS = frozenset({'pytest', 'hypothesis', 'pyyaml'})
BOOTSTRAP_TOOLS = ('pip', 'setuptools', 'wheel')
PROVENANCE = {'status': 'unavailable', 'reason': 'No contemporaneous installation-artifact evidence captured.'}
SOURCE_RULE = 'release-allowlist-minus-validation-pair-manifest-and-generated-registry-v1'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def sha(path):
    return release.sha256_file(path)


def save(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write('\n')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def installed_inventory():
    """Read distribution metadata, never import dependency modules or direct URLs."""
    from packaging.utils import canonicalize_name
    packages = {}
    for dist in metadata.distributions():
        name = canonicalize_name(dist.metadata['Name'])
        if name in packages:
            raise ValueError(f'Ambiguous installed distribution: {name}')
        packages[name] = {
            'version': dist.version,
            'requires_python': dist.metadata.get('Requires-Python', ''),
            'requires_dist': sorted(dist.requires or []),
            'metadata_sha256': hashlib.sha256((dist.read_text('METADATA') or '').encode()).hexdigest(),
        }
    return packages


def dependency_closure(requirements, packages, markers):
    """Traverse active metadata edges per root role, including requested extras."""
    from packaging.requirements import Requirement
    from packaging.specifiers import SpecifierSet
    from packaging.utils import canonicalize_name
    from packaging.version import Version

    def parse(raw):
        req = Requirement(raw)
        if req.url:
            raise ValueError('URL dependency evidence is unsupported; no URLs are exported')
        return req

    def active(req, extras):
        return req.marker is None or any(req.marker.evaluate(dict(markers, extra=e)) for e in [''] + sorted(extras))

    roots, queue, roles, extras_seen, edges = [], [], {}, {}, {}
    for line in requirements.splitlines():
        req = parse(line)
        name = canonicalize_name(req.name)
        role = 'validation' if name in VALIDATION_ROOTS else 'runtime'
        enabled = active(req, set())
        roots.append({'requirement': str(req), 'role': role, 'active': enabled})
        if enabled:
            queue.append((req, role))
    while queue:
        req, role = queue.pop(0)
        name = canonicalize_name(req.name)
        if name not in packages:
            raise ValueError(f'Missing declared dependency: {name}')
        pkg = packages[name]
        version = Version(pkg['version'])
        if not req.specifier.contains(version, prereleases=True):
            raise ValueError(f'Unsatisfied declared dependency: {name}')
        if not SpecifierSet(pkg['requires_python']).contains(markers['python_full_version'], prereleases=True):
            raise ValueError(f'Incompatible Requires-Python: {name}')
        key = (name, role)
        extras = set(req.extras) | extras_seen.get(key, set())
        if key in extras_seen and extras == extras_seen[key]:
            continue
        extras_seen[key] = extras
        roles.setdefault(name, set()).add(role)
        for raw in pkg['requires_dist']:
            child = parse(raw)
            enabled = active(child, extras)
            edge_key = (name, str(child), role)
            edges[edge_key] = {'parent': name, 'requirement': str(child), 'role': role, 'active': enabled}
            if enabled:
                queue.append((child, role))
    closure = [{'name': name, **packages[name], 'roles': sorted(role)} for name, role in sorted(roles.items())]
    # Keep normalized edges, not a second copy of unreviewed raw metadata strings.
    for package in closure:
        package.pop('requires_dist')
    return {'roots': roots, 'packages': closure, 'edges': [edges[k] for k in sorted(edges)]}


def capture_environment(source):
    from packaging.markers import default_environment
    if __package__:
        from .bootstrap_preflight import read_requirements
    else:
        from bootstrap_preflight import read_requirements
    requirements = source / 'requirements.txt'
    content = requirements.read_bytes()
    declared = read_requirements(requirements)
    markers = default_environment()
    packages = installed_inventory()
    closure = dependency_closure(declared, packages, markers)
    included = {p['name'] for p in closure['packages']}
    tools = {name: packages.get(name) for name in BOOTSTRAP_TOOLS}
    # Bootstrap metadata identities suffice; their dependency graph is not a
    # runtime requirement. An actual declared tool still remains in the closure.
    tools = {name: ({k: p[k] for k in ('version', 'metadata_sha256')} if p else None) for name, p in tools.items()}
    unrelated = {n: p for n, p in packages.items() if n not in included and n not in BOOTSTRAP_TOOLS}
    if content != requirements.read_bytes():
        raise ValueError('Requirements changed during capture')
    return {
        'schema': 1, 'kind': 'environment_inventory',
        'requirements_sha256': hashlib.sha256(content).hexdigest(),
        'interpreter': {'version': sys.version, 'implementation': sys.implementation.name,
                        'executable_sha256': sha(Path(sys.executable)),
                        'cache_tag': sys.implementation.cache_tag,
                        'soabi': sysconfig.get_config_var('SOABI'),
                        'tls': ssl.OPENSSL_VERSION},
        'markers': markers, 'dependencies': closure, 'dependency_sha256': digest(closure),
        'bootstrap_tools': tools,
        'unrelated': {'count': len(unrelated), 'metadata_sha256': digest(unrelated)},
        'installation_artifacts': dict(PROVENANCE),
    }


def constraints(environment):
    # This is a single target environment, not a cross-platform lock. Preserve
    # source/edge markers in the receipt; guard every pin with the target marker.
    m = environment['markers']
    target = ' and '.join(f'{key} == {json.dumps(m[key])}' for key in (
        'implementation_name', 'python_version', 'sys_platform', 'platform_machine'))
    return '# Active declared closure only; target-specific validation constraints.\n' + ''.join(
        f'{p["name"]}=={p["version"]} ; {target}\n' for p in environment['dependencies']['packages'])


def source_identity(source):
    return release.source_file_map(release.discover_release_files(source))


def keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected.split()):
        raise ValueError('Unexpected validation record fields')


def hex_digest(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{64}', value):
        raise ValueError('Invalid SHA-256 identity')


def strings(values):
    if not all(isinstance(value, str) and '\n' not in value and '\r' not in value for value in values):
        raise ValueError('Invalid portable string field')


def node_ids(values):
    if not isinstance(values, list) or len(set(values)) != len(values):
        raise ValueError('Invalid selected node identities')
    strings(values)
    for value in values:
        path = Path(value.split('::')[0])
        if not path.parts or path.is_absolute() or '..' in path.parts or path.parts[0] not in {'tests', 'fruth_research'}:
            raise ValueError('Non-public test selector')


def file_json_digest(value):
    return hashlib.sha256((json.dumps(value, indent=2, sort_keys=True) + '\n').encode()).hexdigest()


def validate_environment(env):
    keys(env, 'schema kind requirements_sha256 interpreter markers dependencies dependency_sha256 bootstrap_tools unrelated installation_artifacts')
    if env['schema'] != 1 or env['kind'] != 'environment_inventory' or env['installation_artifacts'] != PROVENANCE:
        raise ValueError('Unsupported environment/provenance record')
    keys(env['interpreter'], 'version implementation executable_sha256 cache_tag soabi tls')
    strings(env['interpreter'].values())
    hex_digest(env['interpreter']['executable_sha256'])
    keys(env['markers'], 'implementation_name implementation_version os_name platform_machine platform_release platform_system platform_version python_full_version platform_python_implementation python_version sys_platform')
    strings(env['markers'].values())
    hex_digest(env['requirements_sha256'])
    keys(env['dependencies'], 'roots packages edges')
    for root in env['dependencies']['roots']:
        keys(root, 'requirement role active')
    for edge in env['dependencies']['edges']:
        keys(edge, 'parent requirement role active')
        strings([edge['parent']])
    for edge in env['dependencies']['roots'] + env['dependencies']['edges']:
        strings([edge['requirement']])
        if edge['role'] not in {'runtime', 'validation'} or type(edge['active']) is not bool:
            raise ValueError('Invalid dependency role/marker evaluation')
    names = []
    for package in env['dependencies']['packages']:
        keys(package, 'name version requires_python metadata_sha256 roles')
        strings([package['name'], package['version'], package['requires_python']])
        hex_digest(package['metadata_sha256'])
        if package['roles'] not in [['runtime'], ['validation'], ['runtime', 'validation']]:
            raise ValueError('Invalid dependency roles')
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', package['name']) or not re.fullmatch(r'[A-Za-z0-9.!+_-]+', package['version']):
            raise ValueError('Invalid dependency pin')
        names.append(package['name'])
    if not names or names != sorted(set(names)) or digest(env['dependencies']) != env['dependency_sha256']:
        raise ValueError('Invalid dependency snapshot identity')
    keys(env['bootstrap_tools'], ' '.join(BOOTSTRAP_TOOLS))
    for tool in env['bootstrap_tools'].values():
        if tool is not None:
            keys(tool, 'version metadata_sha256')
            strings(tool.values())
            hex_digest(tool['metadata_sha256'])
    keys(env['unrelated'], 'count metadata_sha256')
    if type(env['unrelated']['count']) is not int or env['unrelated']['count'] < 0:
        raise ValueError('Invalid incidental package count')
    hex_digest(env['unrelated']['metadata_sha256'])


def public_safety(value):
    # Export structured outcomes and identities only, never tracebacks, commands,
    # environment variables, raw logs, URLs or installation reports.
    data = json.dumps(value, sort_keys=True)
    release._scan_release_file(Path('validation/receipt.json'), data.encode())
    if re.search(r'https?://|file://|(?:^|[\s"=])/(?:Users|home|private|tmp|var)/|[A-Za-z]:\\\\', data):
        raise ValueError('Private path or URL in public validation record')


def validate_outcomes(nodeids, results):
    node_ids(nodeids)
    for result in results:
        keys(result, 'nodeid when outcome')
        if result['nodeid'] not in nodeids or result['when'] not in {'setup', 'call', 'teardown'} or result['outcome'] not in {'passed', 'skipped'}:
            raise ValueError('Invalid test outcome evidence')
    for nodeid in nodeids:
        reports = [r for r in results if r['nodeid'] == nodeid]
        if not any(r['when'] == 'setup' for r in reports) or not any(r['when'] == 'teardown' for r in reports) or not any(r['when'] == 'call' or r['outcome'] == 'skipped' for r in reports):
            raise ValueError('Missing test outcome')


def job_evidence(job):
    """Verify existing runner evidence, returning only a portable projection."""
    job = Path(job).resolve()
    if __package__:
        from . import run_tests as runner
    else:
        import run_tests as runner
    config = read(job / 'run.json')
    complete = read(job / 'completion.json')
    launch = read(job / 'job.json')
    mapping = read(job / 'source.json')['sha256']
    source_hash = runner.verify_source(job)
    if (not config.get('record_validation') or config['collect_only'] or complete['incomplete']
            or complete['exit_code'] != 0 or complete.get('error') or complete['stop_reason']
            or config['source_manifest_sha256'] != sha(job / 'source.json')
            or launch['config_sha256'] != sha(job / 'run.json')
            or complete['source_file_map_sha256'] != source_hash
            or source_identity(job / 'source') != {k: v for k, v in mapping.items() if Path(k) not in release.PUBLIC_VALIDATION_FILES}):
        raise ValueError('Incomplete, historical, changed or unsuccessful validation evidence')
    phases, environment, expected_groups = [], None, None
    evidence = {name: sha(job / name) for name in ('run.json', 'source.json', 'job.json', 'completion.json', 'selection.json')}
    for index, phase in enumerate(complete['phases']):
        name = phase['phase']
        if not re.fullmatch(r'[0-9]{2}-(collection|regression|pure-adapter|pure-cold-profile)', name) or name != f'{index:02}-{phase["group"]}':
            raise ValueError('Invalid evidence phase')
        work = job / name
        worker = read(work / 'worker.json')
        before, after = read(work / 'environment-before.json'), read(work / 'environment-after.json')
        results = read(work / 'results.json')
        selection = read(work / 'selection.json')
        inputs = read(job / (name + '-input.json'))
        if (phase['exit_code'] or worker['pytest_exit_code'] or worker['error']
                or worker['isolation_violations'] or worker['route_failures'] or phase['termination_signals']
                or phase['worker'] != worker or phase['worker_receipt_sha256'] != sha(work / 'worker.json')
                or phase['log_sha256'] != sha(job / (name + '.log'))
                or worker['source_file_map_sha256'] != source_hash
                or worker['python'] != before['interpreter']['version']
                or worker['validation_capture'] != {
                    'before_sha256': sha(work / 'environment-before.json'),
                    'after_sha256': sha(work / 'environment-after.json'),
                    'results_sha256': sha(work / 'results.json'),
                    'junit_sha256': sha(work / 'junit.xml'),
                    'environment_unchanged': before == after}
                or before != after or (environment is not None and environment != before)):
            raise ValueError('Mismatched worker/environment/test evidence')
        validate_environment(before)
        environment = before
        selected = selection['selected']
        if inputs['group'] != phase['group'] or selection['mode'] != config['mode'] or selection['scope'] != inputs['selectors']:
            raise ValueError('Mismatched selection evidence')
        nodeids = [item['nodeid'] for item in selected]
        if index == 0:
            if phase['group'] != 'collection' or inputs['selectors'] != config['selectors'] or results:
                raise ValueError('Invalid collection evidence')
            if read(job / 'selection.json') != selection or not selected:
                raise ValueError('Missing complete selection')
            expected_groups = {}
            for item in selected:
                expected_groups.setdefault(item['group'], []).append(item['nodeid'])
        else:
            if inputs['selectors'] != expected_groups.pop(phase['group'], None) or nodeids != inputs['selectors']:
                raise ValueError('Incomplete or foreign execution scope')
            validate_outcomes(nodeids, results)
        suites = ET.parse(work / 'junit.xml').getroot()
        counts = {key: sum(int(s.get(key, 0)) for s in suites.iter('testsuite')) for key in ('tests', 'failures', 'errors', 'skipped')}
        if counts['failures'] or counts['errors']:
            raise ValueError('Unsuccessful JUnit evidence')
        phases.append({'group': phase['group'], 'selected': nodeids, 'results': results, 'junit_counts': counts})
        for leaf in ('worker.json', 'environment-before.json', 'environment-after.json', 'results.json', 'selection.json', 'junit.xml'):
            evidence[f'{name}/{leaf}'] = sha(work / leaf)
        for leaf in (name + '-input.json', name + '.log'):
            evidence[leaf] = sha(job / leaf)
    if environment is None or expected_groups:
        raise ValueError('Missing execution phases')
    if environment['requirements_sha256'] != mapping['requirements.txt']:
        raise ValueError('Mismatched captured requirements')
    return environment, {k: v for k, v in mapping.items() if Path(k) not in release.PUBLIC_VALIDATION_FILES}, {
        'evidence_sha256': evidence, 'started_at': complete['started_at'], 'completed_at': complete['completed_at'],
        'mode': config['mode'], 'selectors': config['selectors'], 'hashseed': config['hashseed'],
        'exit_code': complete['exit_code'], 'phases': phases,
    }


def make_receipt(source, jobs):
    mapping = source_identity(source)
    environment, validations = None, []
    for job in jobs:
        current, tested, validation = job_evidence(job)
        if mapping != tested or environment is not None and environment != current:
            raise ValueError('Source or environment differs between validation and export')
        environment = current
        validations.append(validation)
    if not validations:
        raise ValueError('Contemporaneous runner evidence required; inventory is not validation')
    snapshot = constraints(environment)
    receipt = {
        'schema': 1, 'kind': 'matching_validated_environment', 'source_rule': SOURCE_RULE,
        'source': {'sha256': mapping, 'file_map_sha256': release.source_map_digest(mapping)},
        'environment': environment, 'environment_sha256': digest(environment),
        'constraints_sha256': hashlib.sha256(snapshot.encode()).hexdigest(),
        'validation': validations,
    }
    validate_receipt(receipt, snapshot, mapping)
    return receipt, snapshot


def validate_receipt(receipt, snapshot, mapping):
    keys(receipt, 'schema kind source_rule source environment environment_sha256 constraints_sha256 validation')
    if receipt['schema'] != 1 or receipt['kind'] != 'matching_validated_environment' or receipt['source_rule'] != SOURCE_RULE:
        raise ValueError('Unsupported validation receipt')
    keys(receipt['source'], 'sha256 file_map_sha256')
    if receipt['source'] != {'sha256': mapping, 'file_map_sha256': release.source_map_digest(mapping)}:
        raise ValueError('Mismatched source identity')
    env = receipt['environment']
    validate_environment(env)
    if env['requirements_sha256'] != mapping['requirements.txt'] or digest(env) != receipt['environment_sha256']:
        raise ValueError('Mismatched requirements or environment identity')
    if snapshot != constraints(env) or hashlib.sha256(snapshot.encode()).hexdigest() != receipt['constraints_sha256']:
        raise ValueError('Mismatched dependency constraints')
    if not receipt['validation']:
        raise ValueError('Missing validation scope')
    completion_ids = set()
    for job in receipt['validation']:
        keys(job, 'evidence_sha256 started_at completed_at mode selectors hashseed exit_code phases')
        if (job['exit_code'] != 0 or len(job['phases']) < 2
                or job['mode'] not in {'regression', 'research', 'historical'} or job['hashseed'] not in {'0', '1'}):
            raise ValueError('Unsuccessful validation')
        node_ids(job['selectors'])
        for field in ('started_at', 'completed_at'):
            datetime.fromisoformat(job[field])
        names = {'run.json', 'source.json', 'job.json', 'completion.json', 'selection.json'}
        selected, executed, groups = [], [], set()
        for index, phase in enumerate(job['phases']):
            keys(phase, 'group selected results junit_counts')
            keys(phase['junit_counts'], 'tests failures errors skipped')
            counts = phase['junit_counts']
            if any(type(n) is not int or n < 0 for n in counts.values()) or counts['failures'] or counts['errors']:
                raise ValueError('Invalid JUnit summary')
            group = phase['group']
            if group not in {'collection', 'regression', 'pure-adapter', 'pure-cold-profile'} or group in groups:
                raise ValueError('Invalid validation execution group')
            groups.add(group)
            node_ids(phase['selected'])
            if index == 0:
                if group != 'collection' or phase['results'] or not phase['selected']:
                    raise ValueError('Invalid public collection scope')
                selected = phase['selected']
            else:
                validate_outcomes(phase['selected'], phase['results'])
                executed.extend(phase['selected'])
            name = f'{index:02}-{group}'
            names.update(f'{name}/{leaf}' for leaf in ('worker.json', 'environment-before.json', 'environment-after.json', 'results.json', 'selection.json', 'junit.xml'))
            names.update((name + '-input.json', name + '.log'))
            if job['evidence_sha256'].get(f'{name}/results.json') != file_json_digest(phase['results']):
                raise ValueError('Public results do not match recorded evidence identity')
        if sorted(selected) != sorted(executed) or set(job['evidence_sha256']) != names:
            raise ValueError('Incomplete public validation scope/evidence')
        for value in job['evidence_sha256'].values():
            hex_digest(value)
        identity = job['evidence_sha256']['completion.json']
        if identity in completion_ids:
            raise ValueError('Duplicate validation job')
        completion_ids.add(identity)
    public_safety(receipt)


def verify_pair(directory, mapping, *, environment=None, jobs=None):
    receipt = read(directory / 'receipt.json')
    snapshot = (directory / 'constraints.txt').read_text(encoding='utf-8')
    validate_receipt(receipt, snapshot, mapping)
    if environment is not None and receipt['environment'] != environment:
        raise ValueError('Current interpreter/environment does not match validation')
    if jobs is not None:
        evidence = [job_evidence(job) for job in jobs]
        if ([e[2] for e in evidence] != receipt['validation'] or
                any(e[0] != receipt['environment'] or e[1] != mapping for e in evidence)):
            raise ValueError('Supplied validation evidence does not match receipt')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('inventory', 'export', 'verify'):
        p = sub.add_parser(name)
        p.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
        if name != 'inventory':
            p.add_argument('--job', type=Path, action='append', required=name == 'export')
        if name == 'verify':
            p.add_argument('--record', type=Path, required=True)
            p.add_argument('--environment', action='store_true', help='Also compare the current interpreter/environment')
        else:
            p.add_argument('--output', type=Path, required=True, help='New exclusive output path')
    args = parser.parse_args()
    if args.command == 'inventory':
        save(args.output, {'captured_at': datetime.now(timezone.utc).isoformat(), 'environment': capture_environment(args.source)})
    elif args.command == 'export':
        receipt, snapshot = make_receipt(args.source, args.job)
        args.output.mkdir()  # never overwrite evidence
        save(args.output / 'receipt.json', receipt)
        with (args.output / 'constraints.txt').open('x', encoding='utf-8') as stream:
            stream.write(snapshot)
    else:
        verify_pair(args.record, source_identity(args.source), jobs=args.job,
                    environment=capture_environment(args.source) if args.environment else None)
        print(json.dumps({'record_integrity': 'matched', 'current_environment': 'matched' if args.environment else 'not_checked',
                          'private_validation_evidence': 'matched' if args.job else 'not_supplied',
                          'installation_artifacts': 'unavailable'}))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as exc:
        print(f'Validation record rejected: {exc}', file=sys.stderr)
        raise SystemExit(2)
