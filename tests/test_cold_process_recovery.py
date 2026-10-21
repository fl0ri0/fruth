"""Bounded cold-process composition using the existing fixture and coordinator."""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
import time

import pytest

from tests.cold_process_oracle import assert_recovery, assert_corrupt, sensitivity
from tests.cold_process_trace import SEAMS, READERS, corpus, transitions, validate
from tests.persistence_trace_adapter import ExecutionCoordinator, Entry, Trace, Operation

SOURCE = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, default=str)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())


def append(path, value):
    with path.open('a') as stream:
        stream.write(json.dumps(value, sort_keys=True, default=str) + '\n')
        stream.flush(); os.fsync(stream.fileno())


def child(role, config, directory, label, *, kill=False):
    input_path, output = directory / (label + '-input.json'), directory / (label + '.json')
    save(input_path, config)
    env = dict(os.environ, TMPDIR=str(directory / 'temporary'), PYTHONDONTWRITEBYTECODE='1')
    env['FRUTH_HYPOTHESIS_EVIDENCE_DIR'] = str(directory / 'writer-fixture')
    argv = [sys.executable, '-B', str(SOURCE / 'tests/cold_process_child.py'), role, str(input_path), str(output)]
    journal = directory.parent / 'subprocesses.jsonl'
    started = time.monotonic()
    with (directory / (label + '.stderr')).open('wb') as err:
        process = subprocess.Popen(argv, cwd=SOURCE, env=env, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=err, close_fds=True)
        append(journal, {'event': 'start', 'role': role, 'pid': process.pid,
                         'label': label, 'scenario': directory.name, 'argv': argv})
        lines, killed = [], False
        try:
            if kill:
                # Select waits on actual child IPC, never on an estimated sleep.
                deadline = time.monotonic() + 35
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not select.select([process.stdout], [], [], remaining)[0]:
                        raise TimeoutError('writer did not reach selected operation')
                    line = process.stdout.readline()
                    lines.append(line.decode(errors='replace'))
                    if line.strip() == b'COLD_BOUNDARY_READY':
                        checkpoint = json.loads(output.read_text())
                        assert checkpoint['boundary'], 'handshake without durable checkpoint'
                        process.kill(); killed = True
                        break
                    if not line:
                        raise AssertionError('writer exited before operation boundary')
            stdout, _ = process.communicate(timeout=40)
            lines.append(stdout.decode(errors='replace'))
        finally:
            if process.poll() is None:
                process.kill()
            code = process.wait(timeout=5)
            append(journal, {'event': 'exit', 'role': role, 'pid': process.pid,
                'scenario': directory.name, 'label': label, 'exit_code': code,
                'selected_boundary_kill': killed, 'seconds': time.monotonic() - started})
            (directory / (label + '.stdout')).write_text(''.join(lines))
    assert code == (-signal.SIGKILL if kill else 0), (role, code, str(output.with_suffix('.error.json')))
    result = json.loads(output.read_text())
    assert not result['violations'], 'child isolation violation'
    return result


def execute(entry, *, check_sensitivity=False, corrupt_controls=False):
    trace = entry.trace
    validate(trace)
    directory = Path(os.environ['FRUTH_HYPOTHESIS_EVIDENCE_DIR']) / entry.identity
    directory.mkdir()
    (directory / 'temporary').mkdir()
    (directory / 'writer-fixture').mkdir()
    save(directory / 'input.json', asdict(entry))
    record = {'identity': entry.identity, 'origin': entry.origin, 'seam': trace.seam,
              'reverse': trace.reverse, 'reads': [], 'classification': 'running'}
    started = time.monotonic()
    try:
        writer = child('writer', {'seam': trace.seam, 'reverse': trace.reverse}, directory,
                       'writer', kill=trace.seam.startswith('kill_'))
        root, frames = Path(writer['root']), Path(writer['frames_root'])
        assert root.is_relative_to(directory / 'temporary')
        assert writer['control_status'] == 200 and len(writer['provider_calls']) == 3
        assert writer['entries'] == [0, 1]
        assert writer['transitions'] == (8 if trace.seam.startswith('kill_') else 10)
        operations = [op['operation'] for op in writer['operations']]
        if trace.seam.endswith(('index_transaction', 'index_selector')):
            assert operations.index('ledger_fsync_returned') < operations.index('sqlite_update_enter')
        if trace.seam.endswith('index_selector'):
            assert operations.index('sqlite_update_returned') < operations.index('selector_publish_enter')
        if trace.seam == 'kill_fsync':
            assert 'ledger_flush_returned' in operations and 'ledger_fsync_returned' not in operations
        partial = trace.seam.endswith('partial')
        expected = dict(writer['parent' if partial or trace.seam == 'reported_prepare' else 'candidate'],
                        response_id=writer['response_id'], partial=partial)
        save(directory / 'expected.json', expected)
        ledger_path = frames / 'responses.jsonl'
        original_ledger = ledger_path.read_bytes()
        assert sha(original_ledger[:writer['parent_length']]) == writer['parent_sha256']
        if partial:
            assert len(original_ledger) - writer['parent_length'] == 31
        index = {p.name: (p.read_bytes(), p.stat().st_atime_ns, p.stat().st_mtime_ns) for p in frames.iterdir()
                 if p.name == 'current_index.active.json' or p.suffix == '.sqlite3'}
        def restore_index():
            for name, (data, atime, mtime) in index.items():
                target = frames / name
                if not target.exists() or target.read_bytes() != data:
                    target.write_bytes(data)
                    os.utime(target, ns=(atime, mtime))
        def read(mode, ordinal):
            restore_index()
            if mode == 'old_index':
                for name, data in writer['saved_index'].items():
                    (frames / name).write_bytes(bytes.fromhex(data))
            elif mode == 'missing_selector':
                (frames / 'current_index.active.json').unlink()
            elif mode == 'missing_db':
                for path in frames.glob('*.sqlite3'):
                    path.unlink()
            result = child('reader', {'root': str(root), 'response_id': writer['response_id'],
                'branches': writer['branches']}, directory, f'reader-{ordinal:02}-{mode}')
            # These independent facts are computed outside the reader: its input
            # cannot contain the supervisor's expected frame, receipt or evidence.
            result['ledger_prefix_kept'] = sha(ledger_path.read_bytes()[:writer['parent_length']]) == writer['parent_sha256']
            result['all_artifacts_valid'] = bool(result['artifacts']) and all(
                item['sha256'] == writer['expected_png_sha256'] and item['bindings_valid']
                for item in result['artifacts'])
            assert_recovery(expected, result)
            checks = sensitivity(expected, result) if check_sensitivity else []
            record['reads'].append({'mode': mode, 'pid': result['pid'], 'index_used': result['index_used'],
                'ledger_fallback_used': result['ledger_fallback_used'], 'frame_id': result['frame_id'],
                'sensitivity': checks, 'canonical_loads': 1, 'public_gets': 6, 'explicit_retries': 3})
            assert ledger_path.read_bytes() == original_ledger
        for i, op in enumerate(trace.operations):
            read(op.value, i)
        if corrupt_controls:
            restore_index()
            latest = json.loads(original_ledger.splitlines()[-1])
            # This fixture's canonical Late Fill evidence is an authoritative
            # sidecar. Remove that exact ref, not an arbitrary unrelated CAS file.
            snapshot_path = frames / latest['late_fill_snapshot_ref']['path']
            snapshot_bytes = snapshot_path.read_bytes()
            snapshot_path.unlink()
            missing = child('reader', {'root': str(root), 'response_id': writer['response_id'],
                'branches': writer['branches']}, directory, 'reader-missing-cas')
            assert_corrupt(missing, snapshot=True)
            save(directory / 'missing-cas-input-evidence.json', {
                'path': str(snapshot_path), 'sha256': sha(snapshot_bytes),
                'ref': latest['late_fill_snapshot_ref']})
            snapshot_path.write_bytes(snapshot_bytes)
            # Deliberately damaged isolated input, after positive controls. No
            # production repair or reader mutation is permitted.
            ledger_path.write_bytes(b'{not valid json}\n')
            (frames / 'current_index.active.json').unlink(missing_ok=True)
            broken = child('reader', {'root': str(root), 'response_id': writer['response_id'],
                'branches': writer['branches']}, directory, 'reader-corrupt-ledger')
            assert_corrupt(broken)
            from copy import deepcopy
            for observation, snapshot in ((missing, True), (broken, False)):
                bad = deepcopy(observation); bad['ok'] = True
                with pytest.raises(AssertionError):
                    assert_corrupt(bad, snapshot=snapshot)
            record['corrupt_controls'] = [
                {'pid': missing['pid'], 'error': missing['error']},
                {'pid': broken['pid'], 'error': broken['error']}]
            ledger_path.write_bytes(original_ledger)
            read('selected', len(trace.operations))
        record.update(classification='passed', writer_pid=writer['pid'],
                      transitions=writer['transitions'] + 1 + len(trace.operations) + 3 * bool(corrupt_controls))
        assert record['transitions'] == transitions(trace) + 3 * bool(corrupt_controls) <= 32
        return record['transitions']
    except BaseException as exc:
        record.update(classification='failed_requires_classification', error=repr(exc))
        raise
    finally:
        record['seconds'] = time.monotonic() - started
        save(directory / 'scenario.json', record)
        if record['classification'] == 'passed':
            shutil.rmtree(directory / 'temporary')


@pytest.mark.parametrize('seam', SEAMS)
def test_deterministic_cold_recovery(seam):
    execute(Entry('control-' + seam, 'seeded', Trace(seam, bool(SEAMS.index(seam) % 2),
        tuple(Operation('read', mode) for mode in READERS))), check_sensitivity=True,
        corrupt_controls=seam == 'success')


def test_one_cold_campaign():
    # Pure generation and seal must finish before any child or runtime import.
    sealed = corpus()
    destination = Path(os.environ['FRUTH_HYPOTHESIS_EVIDENCE_DIR'])
    save(destination / 'corpus.json', asdict(sealed))
    coordinator = ExecutionCoordinator()
    result = {'corpus_sha256': sealed.sha256, 'classification': 'running',
              'generation_completed_before_runtime': True}
    try:
        result['results'] = coordinator.execute(sealed, execute,
            lambda e: append(destination / 'execution-journal.jsonl', e),
            validator=validate, transition_counter=transitions)
        result['classification'] = 'passed'
    finally:
        result.update(started=coordinator.started, completed=coordinator.completed, halted=coordinator.halted)
        save(destination / 'coordinator.json', result)


def test_cold_profile_is_pure_and_bounded():
    from tests.persistence_trace_adapter import unseal
    first = corpus()
    assert first == corpus()
    decoded = unseal(first, validator=validate)
    assert len(decoded.entries) == 32 and decoded.generated_examples == 22
    assert not any(name.startswith('fruth_') for name in sys.modules)
    assert all(transitions(e.trace) <= 32 for e in decoded.entries)
    with pytest.raises(ValueError):
        validate(Trace('kill_fsync', False, (Operation('read', 'unknown'),)))
