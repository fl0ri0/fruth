#!/usr/bin/env python3
"""Stage and supervise offline tests using the existing study isolation design.

Only stdlib and the release selector are used before staging. No runtime imports,
private plans, production configuration, dependency setup or service operations.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
import traceback


CAP_BYTES = 10 * 1024**3
STOP_BYTES = 9 * 1024**3
MAX_SECONDS = 600
INTERRUPT_GRACE_SECONDS = 5
TERMINATE_GRACE_SECONDS = 5
SOURCE = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def allocated(root):
    total = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [name for name in dirs if not (Path(directory) / name).is_symlink()]
        for name in files:
            try:
                info = (Path(directory) / name).lstat()
                total += max(info.st_size, getattr(info, 'st_blocks', 0) * 512)
            except FileNotFoundError:
                pass
    return total


def clean_environment(job, *, hashseed):
    # Do not inherit runtime knobs, credentials, plugin paths or study overrides.
    # Named family defaults stay in their original test source.
    env = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL', 'SYSTEMROOT') if key in os.environ}
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONHASHSEED=str(hashseed),
               PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', TMPDIR=str(job / 'temporary'),
               XDG_CACHE_HOME=str(job / 'cache'))
    return env


def validate_selectors(selectors, source):
    if not isinstance(selectors, list) or not selectors:
        raise ValueError('Runner selectors must be a nonempty list')
    for selector in selectors:
        if not isinstance(selector, str) or not selector:
            raise ValueError('Runner selectors must be nonempty strings')
        path = Path(selector.split('::')[0])
        target = source / path
        if (path.is_absolute() or '..' in path.parts or not path.parts
                or path.parts[0] not in {'tests', 'fruth_research'} or not target.exists()
                or target.resolve() != target):
            raise ValueError(f'Invalid relative test selector: {selector}')


def prepare(args):
    source = Path(args.source).resolve()
    output = Path(args.output).absolute()
    storage = Path(args.storage_root).resolve()
    if output != output.resolve() or output == storage or not output.is_relative_to(storage):
        raise ValueError('Output must be a new physical child of the aggregate storage root')
    if not storage.is_dir() or output.exists():
        raise ValueError('Storage root must exist; output must not exist (exclusive evidence)')
    if not 0 < args.seconds <= MAX_SECONDS:
        raise ValueError('Deadline must be positive and at most 600 seconds')
    sys.path.insert(0, str(SOURCE))
    from scripts.test_isolation import PROTECTED
    if any(output.is_relative_to(source / name) or storage.is_relative_to(source / name) for name in PROTECTED):
        raise ValueError('Evidence/storage root cannot be production state/configuration')
    if args.mode != 'regression' and not args.tests:
        raise ValueError('Research/historical routes require explicit test selectors')
    selectors = args.tests or ['tests']
    validate_selectors(selectors, source)
    # Reuse the public packaging owner; it never copies private/runtime state.
    from scripts import build_release_archive as release
    selected = release.discover_release_files(source)
    mapping = {str(path): sha(origin) for path, origin in sorted(selected.items())}
    usage = allocated(storage)
    if usage + sum(max(p.stat().st_size, p.stat().st_blocks * 512) for p in selected.values()) >= STOP_BYTES:
        raise ValueError('Aggregate storage stop threshold reached before staging')
    output.mkdir()
    release.stage_release_tree(source, output / 'source', selected)
    if mapping != {str(path): sha(origin) for path, origin in sorted(selected.items())}:
        raise ValueError('Source changed while staging; retain incomplete output and use a new label')
    for name, digest in mapping.items():
        if sha(output / 'source' / name) != digest:
            raise ValueError(f'Staged source mismatch: {name}')
    for name in ('temporary', 'cache'):
        (output / name).mkdir()
    manifest = {'sha256': mapping,
                'file_map_sha256': hashlib.sha256(json.dumps(mapping, sort_keys=True).encode()).hexdigest()}
    save(output / 'source.json', manifest)
    config = {'schema': 1, 'source': str(output / 'source'), 'production': str(source),
              'job': str(output), 'storage_root': str(storage), 'seconds': args.seconds,
              'mode': args.mode, 'collect_only': args.collect_only, 'selectors': selectors,
              'hashseed': args.hashseed, 'storage_cap_bytes': CAP_BYTES, 'storage_stop_bytes': STOP_BYTES,
              'source_manifest_sha256': sha(output / 'source.json')}
    save(output / 'run.json', config)
    return output, config


def load_config(job):
    job = Path(job).resolve()
    config = json.loads((job / 'run.json').read_text())
    if (config.get('schema') != 1 or config.get('job') != str(job)
            or config.get('source') != str(job / 'source')
            or not job.is_relative_to(Path(config['storage_root']).resolve())
            or job == Path(config['storage_root']).resolve()
            or config.get('storage_cap_bytes') != CAP_BYTES or config.get('storage_stop_bytes') != STOP_BYTES
            or type(config['seconds']) is not int or not 0 < config['seconds'] <= MAX_SECONDS
            or config.get('hashseed') not in {'0', '1'}
            or config['mode'] not in {'regression', 'research', 'historical'}
            or not isinstance(config['collect_only'], bool)
            or sha(job / 'source.json') != config['source_manifest_sha256']):
        raise ValueError('Invalid runner configuration; collection not started')
    if Path(config['production']).resolve() == job / 'source':
        raise ValueError('Disposable source and production exclusion must differ')
    production = Path(config['production'])
    if not production.is_absolute() or production.resolve() != production or not production.is_dir():
        raise ValueError('Invalid production exclusion root')
    from scripts.test_isolation import PROTECTED
    if any(job.is_relative_to(production / name) for name in PROTECTED):
        raise ValueError('Evidence cannot be production state/configuration')
    validate_selectors(config['selectors'], job / 'source')
    verify_source(job)
    return config


def verify_source(job):
    manifest = json.loads((job / 'source.json').read_text())
    expected = hashlib.sha256(json.dumps(manifest['sha256'], sort_keys=True).encode()).hexdigest()
    if manifest['file_map_sha256'] != expected:
        raise ValueError('Invalid source map identity')
    for name, digest in manifest['sha256'].items():
        relative = Path(name)
        target = job / 'source' / relative
        if (relative.is_absolute() or '..' in relative.parts or target.resolve() != target
                or sha(target) != digest):
            raise ValueError(f'Frozen source drift: {name}')
    return manifest['file_map_sha256']


def worker(job, phase):
    if not re.fullmatch(r'[0-9]{2}-(collection|regression|pure-adapter|pure-cold-profile)', phase):
        raise ValueError('Invalid worker phase path')
    config = load_config(job)  # fail before importing pytest or any runtime owner
    phase_config = json.loads((job / (phase + '-input.json')).read_text())
    if phase_config['group'] not in {'collection', 'regression', 'pure-adapter', 'pure-cold-profile'}:
        raise ValueError('Invalid worker group')
    if phase.split('-', 1)[1] != phase_config['group']:
        raise ValueError('Worker phase/group mismatch')
    validate_selectors(phase_config['selectors'], job / 'source')
    source = job / 'source'
    work = job / phase
    work.mkdir()  # exclusive phase evidence; never resume/overwrite a partial run
    for name in ('temporary', 'examples', 'witnesses', 'hypothesis'):
        (work / name).mkdir()
    os.chdir(source)
    sys.dont_write_bytecode = True
    sys.path = [str(source), str(source / 'tests')] + [p for p in sys.path if p not in ('', str(SOURCE), str(SOURCE / 'scripts'))]
    env = clean_environment(job, hashseed=config['hashseed'])
    env.update(TMPDIR=str(work / 'temporary'), FRUTH_A1_EVIDENCE_DIR=str(work / 'witnesses'),
               FRUTH_HYPOTHESIS_EVIDENCE_DIR=str(work / 'examples'),
               HYPOTHESIS_STORAGE_DIRECTORY=str(work / 'hypothesis'),
               FRUTH_COLD_PLAN=str(job), FRUTH_COLD_PRODUCTION=config['production'])
    os.environ.clear()
    os.environ.update(env)
    tempfile.tempdir = env['TMPDIR']
    from scripts.test_isolation import install_guard
    routes = None
    if phase_config['group'] == 'regression':
        from scripts.test_process_routes import ProcessRoutes
        routes = ProcessRoutes(source=source, work=work, environment=env,
                               manifest=json.loads((job / 'source.json').read_text())['sha256'])
        routes.install()
    violations = install_guard(source=source, evidence=work / 'examples', job=job,
                               production=config['production'], environment=dict(env),
                               routes=routes, cold=phase_config['group'] == 'regression' and any(
                                   p.startswith('tests/test_cold_process_recovery.py::') for p in phase_config['selectors']))
    # Match the established harmless IPv6 capability observation before requests.
    # Pure workers intentionally import neither requests nor runtime modules.
    if phase_config['group'] in {'collection', 'regression'}:
        import socket
        previous = socket.has_ipv6
        socket.has_ipv6 = False
        try:
            import requests  # noqa: F401
        finally:
            socket.has_ipv6 = previous
    import pytest
    selection = {}
    class Reporter:
        @pytest.hookimpl(tryfirst=True)
        def pytest_configure(self, config):
            config._fruth_runner = {'group': phase_config['group'], 'job': str(job)}
        def pytest_runtest_setup(self, item):
            if routes is not None:
                routes.active = item.nodeid
        def pytest_runtest_teardown(self, item):
            if routes is not None:
                routes.reap_item()
                routes.active = None
        def pytest_sessionfinish(self, session, exitstatus):
            selection.update(getattr(session.config, '_fruth_selection', {}))
    started = time.monotonic()
    code, error = 4, None
    try:
        argv = [*phase_config['selectors'], '--fruth-selection=' + config['mode'],
                '-p', 'scripts.test_selection', '-p', 'no:cacheprovider',
                '-p', 'hypothesis.extra.pytestplugin', '--hypothesis-show-statistics',
                '--import-mode=importlib', '-q', '-x', '--tb=short',
                '--basetemp=' + str(work / 'temporary' / 'pytest'),
                '--junitxml=' + str(work / 'junit.xml')]
        if phase_config['group'] == 'collection':
            argv.append('--collect-only')
        code = int(pytest.main(argv, plugins=[Reporter()]))
    except BaseException:
        error = traceback.format_exc()
    finally:
        if routes is not None:
            routes.finish()
        save(work / 'selection.json', selection)
        save(work / 'worker.json', {'pytest_exit_code': code, 'error': error,
             'isolation_violations': violations, 'process_events': routes.events if routes else [],
             'route_failures': [e for e in routes.events if e['event'] in {'rejected', 'launch_error', 'child_deadline', 'cleanup'}] if routes else [],
             'pid': os.getpid(),
             'elapsed_seconds': time.monotonic() - started, 'group': phase_config['group'],
             'runtime_modules': sorted(name for name in sys.modules if name.startswith('fruth_')),
             'python': sys.version, 'hashseed': os.environ.get('PYTHONHASHSEED'),
             'source_file_map_sha256': verify_source(job)})
    route_failures = routes and any(e['event'] in {'rejected', 'launch_error', 'child_deadline', 'cleanup'} for e in routes.events)
    return code or (3 if violations or route_failures else 0)


def stop_group(process, events):
    for sig, grace in ((signal.SIGINT, INTERRUPT_GRACE_SECONDS),
                       (signal.SIGTERM, TERMINATE_GRACE_SECONDS), (signal.SIGKILL, 1)):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            break
        events.append({'signal': sig.name, 'epoch': time.time()})
        until = time.monotonic() + grace
        while time.monotonic() < until:
            process.poll()  # reap the direct worker, even if descendants remain
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                return
            time.sleep(.1)
    process.wait(timeout=5)


def supervise(job):
    config = load_config(job)
    started = time.monotonic()
    receipt = {'started_at': datetime.now(timezone.utc).isoformat(), 'pid': os.getpid(),
               'seconds': config['seconds'], 'phases': [], 'stop_reason': None,
               'storage_cap_bytes': CAP_BYTES, 'storage_stop_bytes': STOP_BYTES,
               'peak_observed_bytes': allocated(Path(config['storage_root'])),
               'source_file_map_sha256': verify_source(job), 'incomplete': True}
    code = 2
    try:
        queue = [('collection', config['selectors'])]
        for group, selectors in queue:
            phase = f'{len(receipt["phases"]):02}-{group}'
            save(job / (phase + '-input.json'), {'group': group, 'selectors': selectors})
            info = {'phase': phase, 'group': group, 'termination_signals': []}
            receipt['phases'].append(info)
            with (job / (phase + '.log')).open('xb', buffering=0) as log:
                process = subprocess.Popen([sys.executable, '-B', str(job / 'source/scripts/run_tests.py'),
                    '_worker', str(job), phase], cwd=job / 'source',
                    env=clean_environment(job, hashseed=config['hashseed']), stdin=subprocess.DEVNULL,
                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
                info.update(pid=process.pid, process_group=os.getpgid(process.pid), session_id=os.getsid(process.pid))
                save(job / (phase + '-started.json'), info)
                next_storage = 0
                try:
                    while process.poll() is None:
                        now = time.monotonic()
                        if now >= next_storage:
                            usage = allocated(Path(config['storage_root']))
                            receipt['peak_observed_bytes'] = max(receipt['peak_observed_bytes'], usage)
                            next_storage = now + 2
                            if usage >= STOP_BYTES:
                                receipt['stop_reason'] = 'storage_budget'
                        if now - started >= config['seconds']:
                            receipt['stop_reason'] = receipt['stop_reason'] or 'job_deadline'
                        if receipt['stop_reason']:
                            stop_group(process, info['termination_signals'])
                            break
                        time.sleep(.1)
                finally:
                    # No phase, failure or interrupted supervisor may leave its
                    # worker process group running. Cold fixture reaps each child.
                    try:
                        os.killpg(process.pid, 0)
                    except ProcessLookupError:
                        pass
                    else:
                        stop_group(process, info['termination_signals'])
                code = process.wait()
                info['exit_code'] = code
            worker_path = job / phase / 'worker.json'
            if worker_path.exists():
                info['worker'] = json.loads(worker_path.read_text())
                info['worker_receipt_sha256'] = sha(worker_path)
            else:
                receipt['stop_reason'] = receipt['stop_reason'] or 'missing_worker_receipt'
            info['log_sha256'] = sha(job / (phase + '.log'))
            if code or receipt['stop_reason']:
                break
            if group == 'collection':
                selection = json.loads((job / phase / 'selection.json').read_text())
                save(job / 'selection.json', selection)
                if not config['collect_only']:
                    if config['mode'] == 'research' and len(selection['selected']) != 1:
                        raise ValueError('Execute one explicitly selected campaign entrypoint per job')
                    groups = {}
                    for item in selection['selected']:
                        groups.setdefault(item['group'], []).append(item['nodeid'])
                    # Purity-sensitive groups each get their own collection and
                    # new OS interpreter. No module deletion/reset substitutes.
                    queue.extend(sorted(groups.items()))
        receipt['incomplete'] = bool(receipt['stop_reason'])
        verify_source(job)
    except BaseException:
        receipt['error'] = traceback.format_exc()
        code = 2
    finally:
        receipt.update(exit_code=2 if receipt['incomplete'] else code,
                       elapsed_seconds=time.monotonic() - started,
                       completed_at=datetime.now(timezone.utc).isoformat())
        receipt['peak_observed_bytes'] = max(receipt['peak_observed_bytes'], allocated(Path(config['storage_root'])))
        save(job / 'completion.json', receipt)
    return receipt['exit_code']


def launch(args):
    job, config = prepare(args)
    command = [sys.executable, '-B', str(job / 'source/scripts/run_tests.py'), '_supervise', str(job)]
    with (job / 'supervisor.log').open('xb', buffering=0) as log:
        process = subprocess.Popen(command, cwd=job / 'source',
            env=clean_environment(job, hashseed=config['hashseed']), stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
    record = {'pid': process.pid, 'session_id': os.getsid(process.pid), 'process_group': os.getpgid(process.pid),
              'detached': args.detach, 'command': command, 'config_sha256': sha(job / 'run.json'),
              'completion_receipt': str(job / 'completion.json'), 'log_path': str(job / 'supervisor.log')}
    save(job / 'job.json', record)
    print(json.dumps(record, indent=2), flush=True)
    return 0 if args.detach else process.wait()


def monitor(root):
    paths = [root] if (root / 'job.json').exists() else sorted(p.parent for p in root.glob('*/job.json'))
    for job in paths:
        launch_record = json.loads((job / 'job.json').read_text())
        complete = job / 'completion.json'
        if complete.exists():
            data = json.loads(complete.read_text())
            status = 'INCOMPLETE' if data['incomplete'] else 'PASS' if data['exit_code'] == 0 else 'FAIL'
            print(f"{job.name}: {status}; exit={data['exit_code']}; seconds={data['elapsed_seconds']:.3f}; "
                  f"peak_GiB={data['peak_observed_bytes']/1024**3:.3f}")
        else:
            print(f"{job.name}: launched supervisor={launch_record['pid']}; completion unconfirmed")
        selection = job / 'selection.json'
        if selection.exists():
            data = json.loads(selection.read_text())
            print(f"  {data['mode']}: selected={len(data['selected'])}, excluded={len(data['excluded'])}")
        for journal in job.glob('*/examples/subprocesses.jsonl'):
            events = []
            for line in journal.read_text().splitlines():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass  # A live writer may be between write and flush.
            print(f"  cold children: starts={sum(e['event']=='start' for e in events)}, "
                  f"exits={sum(e['event']=='exit' for e in events)}")


def main():
    sys.path.insert(0, str(SOURCE))
    # Internal commands validate their complete saved configuration before pytest.
    if len(sys.argv) >= 2 and sys.argv[1] in {'_worker', '_supervise'}:
        if len(sys.argv) != (4 if sys.argv[1] == '_worker' else 3):
            raise ValueError('Missing internal runner configuration')
        job = Path(sys.argv[2]).resolve()
        return worker(job, sys.argv[3]) if sys.argv[1] == '_worker' else supervise(job)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    run = sub.add_parser('run', help='Stage disposable release source and supervise selection/execution')
    run.add_argument('--source', default=str(SOURCE))
    run.add_argument('--output', required=True, help='New exclusive job directory')
    run.add_argument('--storage-root', required=True, help='Existing aggregate task evidence directory')
    run.add_argument('--seconds', type=int, default=600)
    run.add_argument('--hashseed', choices=('0', '1'), default='0')
    run.add_argument('--mode', choices=('regression', 'research', 'historical'), default='regression')
    run.add_argument('--collect-only', action='store_true')
    run.add_argument('--detach', action='store_true')
    run.add_argument('tests', nargs='*')
    watch = sub.add_parser('monitor', help='Read job receipts without starting/stopping work')
    watch.add_argument('root', type=Path)
    watch.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    if args.command == 'run':
        return launch(args)
    while True:
        monitor(args.root.resolve())
        if not args.watch:
            return 0
        time.sleep(5)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'Runner configuration/error: {exc}', file=sys.stderr)
        raise SystemExit(2)
