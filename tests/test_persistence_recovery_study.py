"""Bounded composition study. Expectations precede runtime observations.

See plans/hypothesis-persistence-recovery-2026-10-15/model.md. No production
classification helper determines expected outcomes. All writes use real owners.
"""
from contextlib import ExitStack
from copy import deepcopy
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
import time
import uuid
from unittest.mock import patch

import pytest

import fruth_webserver as web
from fruth_services import response_frames as rf, response_index_sqlite as sqlite
from fruth_services.response_persistence import ResponsePersistenceError
from tests.http_client import api_client
from tests.test_c9_pending_handoff_contract import PendingHandoffStudy
from tests.test_c9_continuation_hypothesis import PROMPTS
from tests.test_graph_lineage_c3_c4_corrections import durable_evidence
from tests.test_graph_lineage_stateful_hypothesis import stable
from tests.test_late_fill_control_overlap_hypothesis import RESPONSE_ID, WAIT_SECONDS


SEAMS = ('success', 'prepare', 'partial', 'flush', 'fsync', 'index_transaction', 'index_selector')
EXPECTED = {'success': ('committed', 'published'), 'prepare': ('not_committed', 'not_attempted'),
            'partial': ('uncertain', 'not_attempted'), 'flush': ('uncertain', 'not_attempted'),
            'fsync': ('uncertain', 'not_attempted'),
            'index_transaction': ('committed', 'failed'), 'index_selector': ('committed', 'failed')}
VIEWS = ('default', 'ui', 'status', 'debug', 'truth', 'full')
READERS = ('active', 'cold_selected', 'cold_old_index', 'cold_missing_selector', 'cold_missing_db')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def files(root):
    return {str(p.relative_to(root)): digest(p.read_bytes())
            for p in sorted(root.rglob('*')) if p.is_file()}


def semantic(value):
    late = value.get('late_fill') or {}
    return {'results': {r['branch_id']: durable_evidence(r) for r in late.get('fill_results', [])},
            'cancelled': [r['branch_id'] for r in late.get('cancelled_branches', [])],
            'failed': [r['branch_id'] for r in late.get('failed_branches', [])]}


def assert_oracle(o):
    """Plain independent assertions over copied observations, never owner predicates."""
    status, index = EXPECTED[o['seam']]
    assert o['reached'] == (0 if o['seam'] == 'success' else 1), 'wrong fault multiplicity'
    assert o['receipt']['status'] == status, 'persistence certainty changed'
    assert o['receipt']['index_status'] == index, 'Index outcome changed'
    assert o['finalizer_raised'] == (status != 'committed'), 'finalizer boundary changed'
    assert o['sibling_kept'] and o['cancel_kept'], 'accepted or cancelled evidence lost'
    assert o['prefix_kept'], 'frozen history changed'
    assert o['physical_p'] and o['semantic_p'], 'P evidence lost'
    assert o['exact_identity'], 'frame/execution/branch/artifact identity changed'
    assert o['pending_calls'] == 1 and o['entries'] == [0, 1] and o['submissions'] == 2, 'execution duplicated or missing'
    assert o['worker_clean'], 'worker exception or claim leak'
    assert o['model_failed'] is False, 'storage became model failure'
    assert o['passive_unchanged'], 'passive observation mutated/executed'
    if status != 'committed':
        assert o['outer_status'] == 'incomplete' and o['lifecycle'] == 'blocked', 'outer storage failure erased'
        assert o['error_code'] == 'response_persistence_failed', 'storage error lost'
        assert o['retryable'] is False, 'storage acquired retry permission'
    if o['seam'].startswith('index_'):
        assert o['ledger_fsync_returned'], 'Index failure preceded confirmed Ledger commit'
    if o['seam'] in {'prepare', 'partial'}:
        assert o['recovered_frame'] == o['parent_frame'], 'uncommitted row acquired recovery authority'
    else:
        assert o['recovered_frame'] == o['receipt']['frame_id'], 'readable result identity lost'


class PersistenceStudy(PendingHandoffStudy):
    def __init__(self, seam, reverse=False):
        self.seam = seam
        self.ops, self.writes, self.finishes, self.reads = [], [], [], []
        self.fault_count = 0
        self.target_write = False
        self.observed = None
        self.cold_roots = {}
        self.problem = None
        self.sensitivity = []
        super().__init__(reverse)
        # The historical race adapter takes one argument; public truth/full
        # reads pass recover_missing. Forward that supported read option intact.
        race_lookup = web._get_response_lookup_record
        def lookup(rid, **kwargs):
            return self.original_lookup(rid, **kwargs) if kwargs else race_lookup(rid)
        self.stack.enter_context(patch.object(web, '_get_response_lookup_record', lookup))
        self.source_inputs.update(family='persistence_recovery', seam=seam)
        self.root = self.engine.harness.root
        self.frames_root = self.engine.harness.response_frames_dir
        self.ledger = self.frames_root / 'responses.jsonl'

    def op(self, name, **data):
        self.ops.append({'operation': name, 'thread': threading.current_thread().name, **data})

    def fail(self, seam):
        if self.target_write and self.seam == seam and not self.fault_count:
            self.fault_count += 1
            self.op('injected_failure', seam=seam)
            raise OSError(errno.ENOSPC if seam in {'prepare', 'partial'} else errno.EIO,
                          'bounded study ' + seam)

    def prepare(self):
        self.start_parent()
        self.finish_race(True)
        assert self.child_arrived.wait(WAIT_SECONDS)
        self.parent_ledger = self.ledger.read_bytes()
        state = rf.load_latest_response_state(RESPONSE_ID, frames_dir=self.frames_root)
        self.parent = deepcopy(state['response_payload'])
        self.parent_frame = state['response_frame']['frame_id']
        self.check_value(self.parent, True)
        confirmed = [c for c in self.commits if c['frame']['frame_id'] == self.parent_frame]
        assert confirmed and confirmed[-1]['receipt']['status'] == 'committed', 'fixture lacks confirmed parent'
        assert sqlite.selection(self.frames_root)['backend'] == 'sqlite'
        self.saved_index = {p.name: p.read_bytes() for p in self.frames_root.iterdir()
                            if p.is_file() and (p.suffix == '.sqlite3' or p.name == sqlite.SELECTOR_NAME)}
        self.install_storage_observers()
        web._register_response_stream(RESPONSE_ID)
        self.run_child()
        self.transition('observe_finalizer_and_worker')
        self.live = deepcopy(self.original_lookup(RESPONSE_ID)['response_payload'])
        self.canonical = rf.load_latest_response_state(RESPONSE_ID, frames_dir=self.frames_root)
        assert self.canonical['ok'], 'canonical fixture read failed'
        self.final_bytes = self.ledger.read_bytes()
        events, done = web._wait_for_response_stream_events(RESPONSE_ID, 0)
        self.stream = {'events': events, 'done': done}
        # The target candidate carries P even when its append was rejected.
        targets = [f for f in self.finishes if f['target']]
        assert targets, 'P finalizer seam not reached'
        self.target_finish = targets[0]
        candidate = self.target_finish['payload']
        self.candidate = candidate
        receipt = candidate['persistence']
        p = next(r for r in candidate['late_fill']['fill_results'] if r['branch_id'] == self.pending)
        frame = candidate['response_frame']
        public_p = [o for o in frame['output']['outputs'] if o.get('branch_id') == self.pending]
        artifact_exact = (len(public_p) == 1 and public_p[0].get('artifact_ref') == p.get('artifact_ref')
                          and p.get('artifact_ref') != self.sibling_result.get('artifact_ref')
                          and all(a.get('artifact_ref') == p.get('artifact_ref') and
                                  a.get('branch_id') == self.pending for a in p.get('artifacts', [])))
        self.observed = {
            'seam': self.seam, 'reached': self.fault_count, 'receipt': deepcopy(receipt),
            'finalizer_raised': self.target_finish['raised'],
            'sibling_kept': semantic(candidate)['results'].get(self.sibling) == self.sibling_result,
            'cancel_kept': self.target in semantic(candidate)['cancelled'] and self.target not in semantic(candidate)['results'],
            'prefix_kept': self.final_bytes.startswith(self.parent_ledger),
            'physical_p': Path(p['saved_image_path']).read_bytes() == self.engine.model.png,
            'semantic_p': self.pending in semantic(candidate)['results'],
            'exact_identity': (p['branch_id'] == p['phase_id'] == self.pending
                and p['obligation_id'] == 'obligation-' + self.pending
                and frame['frame_id'] == receipt['frame_id']
                and artifact_exact and candidate['id'] == self.parent['id'] == RESPONSE_ID
                and all(candidate['late_fill'].get(key) == self.parent['late_fill'].get(key)
                        for key in ('successor_reopen_execution', 'terminal_closure_repair_reopen',
                                    'partial_rebase_execution'))),
            'pending_calls': sum(PROMPTS[self.pending] in stable(c['request']) for c in self.engine.harness.provider_calls),
            'entries': list(self.entries), 'submissions': len(self.submissions),
            'worker_clean': not self.errors and not web._response_late_fill_is_in_flight(RESPONSE_ID)
                and not web._RESPONSES_RUNTIME._mutation_locks,
            'model_failed': self.pending in semantic(self.live)['failed'],
            'passive_unchanged': True, 'outer_status': self.live.get('status'),
            'lifecycle': self.live.get('lifecycle_state'), 'error_code': self.live.get('error', {}).get('code'),
            'retryable': self.live.get('error', {}).get('retryable'),
            'ledger_fsync_returned': any(o['operation'] == 'ledger_fsync_returned' for o in self.ops),
            'recovered_frame': self.canonical['response_frame']['frame_id'], 'parent_frame': self.parent_frame,
        }
        assert_oracle(self.observed)
        # A readable candidate is exact semantic evidence, not a commit receipt.
        if self.seam not in {'prepare', 'partial'}:
            assert semantic(self.canonical['response_payload'])['results'][self.pending] == durable_evidence(p)
        assert len(self.writes) == 1, 'same P publication appended again'
        if self.seam not in {'prepare', 'partial'}:
            row = bytes.fromhex(self.writes[0]['appended_hex'])
            assert len(row) == receipt['line_length'] and digest(row) == receipt['source_frame_sha256']
            assert json.loads(row)['frame_id'] == receipt['frame_id']
        self.check_value(self.canonical['response_payload'], True)
        self.check_dispatch()
        # A failed delivery must not become a successful SSE completion.
        if EXPECTED[self.seam][0] != 'committed':
            assert done and any('event: response.failed' in e for e in events)
            assert not any('event: response.completed' in e for e in events)
        self.fingerprint = self.passive_fingerprint()

    def install_storage_observers(self):
        native_compact, native_open, native_fsync = rf.compact_response_frame_for_ledger, Path.open, os.fsync
        native_update, native_atomic = sqlite.update, rf._atomic_replace_file_bytes
        native_finalize = web._finalize_response_frame_payload
        owner = self

        def compact(value, **kw):
            owner.op('snapshot_prepare_enter', frame_id=value.get('frame_id'))
            owner.fail('prepare')
            result = native_compact(value, **kw)
            owner.op('snapshot_prepare_returned')
            return result

        class LedgerHandle:
            def __init__(self, handle): self.handle = handle
            def __enter__(self): return self
            def __exit__(self, *args):
                self.handle.close()
                owner.op('ledger_close_returned')
            def fileno(self): return self.handle.fileno()
            def write(self, data):
                owner.op('append_enter', length=len(data), sha256=digest(data))
                if owner.target_write and owner.seam == 'partial' and not owner.fault_count:
                    self.handle.write(data[:31])
                    self.handle.flush()
                    owner.op('partial_prefix_flushed', length=31)
                    owner.fail('partial')
                result = self.handle.write(data)
                owner.op('append_returned', length=result)
                return result
            def flush(self):
                owner.op('ledger_flush_enter')
                owner.fail('flush')
                result = self.handle.flush()
                owner.op('ledger_flush_returned')
                return result

        def opened(path, mode='r', *args, **kwargs):
            handle = native_open(path, mode, *args, **kwargs)
            return LedgerHandle(handle) if path == owner.ledger and mode == 'ab' else handle

        def fsync(fd):
            is_ledger = (owner.ledger.exists() and os.fstat(fd).st_ino == owner.ledger.stat().st_ino
                         and os.fstat(fd).st_dev == owner.ledger.stat().st_dev)
            if is_ledger:
                owner.op('ledger_fsync_enter')
                owner.fail('fsync')
            result = native_fsync(fd)
            if is_ledger: owner.op('ledger_fsync_returned')
            return result

        def update(*args, **kwargs):
            owner.op('sqlite_update_enter')
            owner.fail('index_transaction')
            result = native_update(*args, **kwargs)
            owner.op('sqlite_update_returned')
            return result

        def atomic(path, data):
            if path.name == sqlite.SELECTOR_NAME:
                owner.op('selector_publish_enter')
                owner.fail('index_selector')
            result = native_atomic(path, data)
            if path.name == sqlite.SELECTOR_NAME: owner.op('selector_publish_returned')
            return result

        def finalize(value, *args, **kwargs):
            target = any(r.get('branch_id') == owner.pending for r in value.get('late_fill', {}).get('fill_results', []))
            owner.target_write = target
            try:
                result = native_finalize(value, *args, **kwargs)
            except ResponsePersistenceError as exc:
                owner.finishes.append({'target': target, 'raised': True, 'payload': deepcopy(exc.response_payload)})
                raise
            else:
                owner.finishes.append({'target': target, 'raised': False, 'payload': deepcopy(result)})
                return result
            finally:
                owner.target_write = False

        for obj, name, fn in ((rf, 'compact_response_frame_for_ledger', compact), (Path, 'open', opened),
                              (rf.os, 'fsync', fsync), (sqlite, 'update', update),
                              (rf, '_atomic_replace_file_bytes', atomic),
                              (web, '_finalize_response_frame_payload', finalize)):
            self.stack.enter_context(patch.object(obj, name, fn))
        for name in ('_persist_response_frame', '_append_response_frame_with_parent_cas'):
            native = getattr(web, name)
            def writer(*args, _native=native, _name=name, **kwargs):
                before = self.ledger.read_bytes()
                raised = None
                try:
                    return _native(*args, **kwargs)
                except BaseException as exc:
                    raised = type(exc).__name__
                    raise
                finally:
                    after = self.ledger.read_bytes()
                    self.writes.append({'writer': _name, 'raised': raised,
                        'receipt': deepcopy(kwargs.get('receipt')), 'before_length': len(before),
                        'before_sha256': digest(before), 'after_length': len(after),
                        'after_sha256': digest(after), 'prefix_preserved': after.startswith(before),
                        'appended_hex': after[len(before):].hex()})
            self.stack.enter_context(patch.object(web, name, writer))

    def passive_fingerprint(self):
        # Full content digests include Ledger, SQLite, selector, CAS, registry and artifacts.
        return (files(self.engine.harness.state_dir), files(self.engine.harness.artifacts_dir),
                len(self.submissions), len(self.engine.harness.provider_calls), list(self.claim_events), len(self.writes))

    def cold_root(self, mode):
        if mode == 'cold_selected':
            # Canonical reader receives only the original files, no live record.
            # Keeping physical identity permits the valid selected SQLite path.
            return self.frames_root
        if mode in self.cold_roots:
            return self.cold_roots[mode]
        root = self.root / ('reader-' + mode)
        shutil.copytree(self.frames_root, root)
        if mode == 'cold_old_index':
            for name, data in self.saved_index.items(): (root / name).write_bytes(data)
        elif mode == 'cold_missing_selector':
            (root / sqlite.SELECTOR_NAME).unlink()
        elif mode == 'cold_missing_db':
            for path in root.glob('*.sqlite3'): path.unlink()
        self.cold_roots[mode] = root
        self.transition('prepare_evidence_only_' + mode)
        return root

    def observe(self, view='truth', mode='active'):
        before = self.passive_fingerprint()
        if mode == 'active':
            with api_client(web.app) as client:
                response = client.get(f'/api/responses/{RESPONSE_ID}',
                    query_string={} if view == 'default' else {'view': view})
            assert response.status_code == 200, (view, response.get_json())
            value = response.get_json()
            record = {'view': view, 'reader': mode, 'status_code': response.status_code,
                      'lifecycle_state': value.get('lifecycle_state'), 'persistence': value.get('persistence'),
                      'frame_id': value.get('frame_id') or value.get('response_frame', {}).get('frame_id')}
            self.reads.append(record)
            if EXPECTED[self.seam][0] != 'committed':
                assert value.get('lifecycle_state') == 'blocked', ('public failure erased', record)
                assert value.get('persistence') == self.candidate['persistence'], ('public receipt erased', record)
            if view in {'truth', 'full'}:
                self.check_value(value, True)
        else:
            root = self.cold_root(mode)
            original = files(root)
            result = rf.load_latest_response_state(RESPONSE_ID, frames_dir=root)
            self.reads.append({'reader': mode, 'ok': result.get('ok'),
                'frame_id': result.get('response_frame', {}).get('frame_id'),
                'ledger_fallback_used': result.get('ledger_fallback_used'),
                'receipt': result.get('response_payload', {}).get('persistence')})
            assert result['ok'], result
            assert result['response_frame']['frame_id'] == self.observed['recovered_frame']
            self.check_value(result['response_payload'], True)
            assert files(root) == original, 'cold reader repaired storage'
        self.transition('passive_' + mode + '_' + view)
        assert before == self.passive_fingerprint(), 'passive read mutated/executed'
        self.observed['passive_unchanged'] = before == self.passive_fingerprint()
        assert_oracle(self.observed)

    def retry_and_tail(self):
        before = self.passive_fingerprint()
        with api_client(web.app) as client:
            response = client.post(f'/api/responses/{RESPONSE_ID}/late_fill/retry', json={'branch_id': self.pending})
        self.reads.append({'operation': 'explicit_retry', 'status_code': response.status_code})
        assert response.status_code == 409, response.get_json()
        assert self.passive_fingerprint() == before
        self.transition('retry_rejected')
        if self.seam == 'partial':
            original = files(self.frames_root)
            with pytest.raises(rf.ResponseFramePersistenceError) as raised:
                rf.persist_response_frame(deepcopy(self.candidate['response_frame']), frames_dir=self.frames_root)
            assert raised.value.receipt['status'] == 'not_committed'
            assert raised.value.receipt['error']['code'] == 'response_frame_ledger_unterminated_tail'
            assert files(self.frames_root) == original
            self.reads.append({'operation': 'tail_append_rejected', 'receipt': raised.value.receipt})
            self.transition('tail_append_rejected')

    def sensitivity_check(self):
        for key, bad_value in {'reached': 2, 'finalizer_raised': not self.observed['finalizer_raised'],
                'sibling_kept': False, 'cancel_kept': False, 'prefix_kept': False, 'physical_p': False,
                'semantic_p': False, 'exact_identity': False, 'pending_calls': 2, 'entries': [0],
                'submissions': 3, 'worker_clean': False, 'model_failed': True,
                'passive_unchanged': False, 'recovered_frame': 'foreign'}.items():
            bad = deepcopy(self.observed)
            bad[key] = bad_value
            with pytest.raises(AssertionError): assert_oracle(bad)
            self.sensitivity.append(key)
        for key in ('status', 'index_status'):
            bad = deepcopy(self.observed)
            bad['receipt'][key] = 'invented'
            with pytest.raises(AssertionError): assert_oracle(bad)
            self.sensitivity.append('receipt.' + key)
        if EXPECTED[self.seam][0] != 'committed':
            for key, value in {'outer_status': 'completed', 'lifecycle': 'completed',
                               'error_code': None, 'retryable': True}.items():
                bad = deepcopy(self.observed); bad[key] = value
                with pytest.raises(AssertionError): assert_oracle(bad)
                self.sensitivity.append(key)

    def close(self):
        self.release_target.set(); self.release_pending.set(); self.release_control.set(); self.release_child.set()
        for thread in self.threads: thread.join(WAIT_SECONDS)
        try:
            assert not any(t.is_alive() for t in self.threads), 'fixture thread leaked'
            destination = Path(os.environ['FRUTH_HYPOTHESIS_EVIDENCE_DIR'])
            identity = 'persistence-' + uuid.uuid4().hex
            record = {'kind': 'fruth.persistence_recovery_study', 'inputs': self.source_inputs,
                'actual_transitions': self.transition_count, 'transitions': [e for e in self.progress.events if e['kind'] == 'transition'],
                'fault_operations': self.ops, 'writes': self.writes, 'observation': self.observed,
                'reads': self.reads, 'sensitivity': self.sensitivity, 'failed': self.failed, 'problem': self.problem,
                'control_status': self.control_result and self.control_result['status_code'],
                'claim_events': self.claim_events, 'entries': self.entries,
                'finalizers': [{'target': f['target'], 'raised': f['raised'],
                    'receipt': f['payload'].get('persistence'), 'semantic': semantic(f['payload'])} for f in self.finishes],
                'commits': [{'frame_id': c['frame']['frame_id'], 'receipt': c['receipt']} for c in self.commits],
                'provider_calls': self.engine.harness.provider_calls,
                'stream': getattr(self, 'stream', None), 'tree_sha256': files(self.frames_root)}
            if self.failed:
                # One complete execution root, not duplicate generated read roots. Exact
                # bytes include the selector/DB, Ledger/tail, all CAS and physical outputs.
                import tarfile
                archive = destination / (identity + '-bytes.tar.gz')
                with tarfile.open(archive, 'w:gz') as tar:
                    for p in sorted(self.root.iterdir()):
                        if not p.name.startswith('reader-'): tar.add(p, arcname=p.name)
                record.update(bytes_archive=archive.name, bytes_archive_sha256=digest(archive.read_bytes()),
                    original_root=str(self.root), original_events=self.progress.events,
                    original_finalizers=self.finishes, original_control=self.control_result,
                    original_parent=getattr(self, 'parent', None),
                    original_live=deepcopy((self.original_lookup(RESPONSE_ID) or {}).get('response_payload')))
            (destination / (identity + '.json')).write_text(json.dumps(record, indent=2, default=str) + '\n')
        finally:
            web._close_response_stream(RESPONSE_ID)
            self.stack.close()


def exercise(seam, reverse=False, readers=READERS, sensitivity=False):
    study = PersistenceStudy(seam, reverse)
    try:
        study.prepare()
        if sensitivity: study.sensitivity_check()
        for view in VIEWS: study.observe(view)
        for reader in readers:
            if reader != 'active': study.observe(mode=reader)
        study.retry_and_tail()
        return study.observed
    except BaseException as exc:
        study.failed = True; study.problem = repr(exc)
        raise
    finally:
        study.close()


@pytest.mark.parametrize('seam', SEAMS)
def test_deterministic_composition(seam):
    exercise(seam, sensitivity=True)
