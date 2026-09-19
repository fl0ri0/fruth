"""Closed ownership oracles. Deep traversal exists only here, never in reuse guards."""
import ast
import copy
import errno
import inspect
import json
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from fruth_services import response_frames as rf, graph_rebase_readiness_registry as registry
from fruth_services import state_flow as sf, events
from fruth_services.graph_rebase_rollout import project_graph_rebase_readiness_observation as project
from tests.test_readiness_observation_reuse import frame


@pytest.fixture
def stable(tmp_path):
    frames = tmp_path / 'frames'
    value = frame()
    # Nested sidecars exercise manifest-derived borrowed refs, including closure.
    value['runtime']['graph_closure_review'] = {
        'status': 'closed', 'reason': 'x' * 18000,
        'details': {'nested': ['bounded evidence'] * 2000},
    }
    rf.persist_response_frame(value, frames_dir=frames)
    observed = rf.load_latest_response_observation_state('reuse-response', frames_dir=frames)
    assert observed['ok']
    return frames, project(observed['response_payload']), tmp_path / 'registry.jsonl'


@pytest.fixture(autouse=True)
def diagnostics(tmp_path, monkeypatch):
    target = tmp_path / 'diagnostics'
    monkeypatch.setenv('FRUTH_STATE_FLOW_DIAGNOSTICS_DIR', str(target))
    with sf.state_flow_scope(), events.causal_scope(lambda **record: None):
        yield target


def run(stable):
    frames, projection, path = stable
    return registry._register_finalizer_readiness_observation(
        projection, frames_dir=frames, registry_path=path,
    )


def mutable_ids(value, seen=None):
    """Test-only object-graph oracle, following every container child."""
    seen = set() if seen is None else seen
    if id(value) in seen:
        return set()
    seen.add(id(value))
    assert not isinstance(value, (rf._FinalizerMapProof, registry._FinalizerRegistration))
    found = {id(value)} if isinstance(value, (dict, list, set, bytearray)) else set()
    children = list(value.keys()) + list(value.values()) if isinstance(value, dict) else value if isinstance(value, (list, tuple, set)) else ()
    for child in children:
        found |= mutable_ids(child, seen)
    return found


def mutate_containers(value, seen=None):
    seen = set() if seen is None else seen
    if id(value) in seen:
        return
    seen.add(id(value))
    if isinstance(value, dict):
        for child in list(value.values()): mutate_containers(child, seen)
        value['test_output_mutation'] = ['detached']
    elif isinstance(value, list):
        for child in list(value): mutate_containers(child, seen)
        value.append('detached')


def test_one_real_selection_proof_two_reuses_and_registry_bytes(stable):
    frames, projection, path = stable
    epoch = rf.verify_response_frame_epoch(frames_dir=frames)
    registry.append_graph_rebase_readiness_observation(
        projection, source_frame=epoch['source_frame_sha256_by_response']['reuse-response'],
        verified_epoch=epoch, frames_dir=frames, registry_path=path.with_suffix('.ordinary'),
    )
    with patch.object(registry, 'verify_response_frame_epoch', wraps=registry.verify_response_frame_epoch) as verify, \
         patch.object(rf, '_response_map_digest', wraps=rf._response_map_digest) as digest, \
         patch.object(rf, '_read_indexed_response_frame', wraps=rf._read_indexed_response_frame) as row, \
         patch.object(rf, '_read_observation_snapshot_bytes', wraps=rf._read_observation_snapshot_bytes) as cas, \
         patch.object(rf, 'state_flow_note', wraps=rf.state_flow_note) as note:
        result = run(stable)
    assert result['status'] == 'appended'
    assert verify.call_count == 1 and digest.call_count == 2  # Epoch + selection
    assert row.call_count == 2 and cas.call_count > 2
    assert sum(c.kwargs.get('finalizer_map_proof_reuses', 0) for c in note.call_args_list) == 2
    assert path.read_bytes() == path.with_suffix('.ordinary').read_bytes()


def test_supported_results_events_and_nested_refs_have_no_map_alias(stable):
    captured = {}; outputs = []; records = []
    selection = registry._select_graph_rebase_observation_response_ids
    hydrate = registry._load_latest_response_observation_state
    append = registry.append_graph_rebase_readiness_registry_records
    summary = sf._summary
    def select(**kw):
        context = kw['_finalizer_context']; captured['context'] = context
        mapping = context[3]['index_state']['responses']
        captured['map'] = mapping; captured['before'] = copy.deepcopy(mapping)
        result = selection(**kw); outputs.append(result)
        assert not mutable_ids(mapping) & mutable_ids(result)
        # Mutate the actual supported result while the proof is active.
        result['scan_errors'].append({'test': ['detached']})
        assert mapping == captured['before']
        return result
    def load(*args, **kw):
        result = hydrate(*args, **kw); outputs.append(result)
        assert not mutable_ids(captured['map']) & mutable_ids(result)
        pristine = copy.deepcopy(result)
        mutate_containers(result)
        assert captured['map'] == captured['before']
        # Preserve the operation's intended input after testing output mutation.
        return pristine
    def write(values, **kw):
        assert captured['context'][0]._FinalizerMapProof__phase == 'closed'
        assert not mutable_ids(captured['map']) & mutable_ids(values)
        originals = copy.deepcopy(values); outputs.append(values)
        mutate_containers(values)
        assert captured['map'] == captured['before']
        return append(originals, **kw)
    def summarize(*args, **kw):
        result = summary(*args, **kw); outputs.append(result)
        if 'map' in captured: assert not mutable_ids(captured['map']) & mutable_ids(result)
        return result
    with patch.object(registry, '_select_graph_rebase_observation_response_ids', select), \
         patch.object(registry, '_load_latest_response_observation_state', load), \
         patch.object(registry, 'append_graph_rebase_readiness_registry_records', write), \
         patch.object(sf, '_summary', summarize), \
         events.causal_scope(lambda **record: records.append(record)):
        result = run(stable)
    assert result['status'] == 'appended'
    assert any('snapshot' in str(key) for entry in captured['map'].values() for key in entry)
    for value in outputs + records + [result]:
        assert not mutable_ids(captured['map']) & mutable_ids(value)
    assert captured['map'] == captured['before']
    assert captured['context'][1]._FinalizerRegistration__epoch is None


@pytest.mark.parametrize('mutation', ['foreign_owner', 'foreign_scope', 'foreign_epoch', 'foreign_index',
    'foreign_map', 'arbitrary_mapping', 'forged', 'unadopted', 'closed', 'consumed', 'wrong_phase', 'process', 'thread'])
def test_foreign_or_inactive_context_cannot_reuse(stable, mutation):
    native = registry._load_latest_response_observation_state
    def load(*args, **kw):
        context = kw['_finalizer_context']; proof = context[0]; index = kw['index_state']
        ledger = stable[0] / 'responses.jsonl'
        altered = list(context)
        if mutation == 'foreign_owner': altered[1] = object()
        elif mutation == 'foreign_scope': altered[2] = object()
        elif mutation == 'foreign_epoch': altered[3] = copy.deepcopy(context[3])
        elif mutation == 'foreign_index': index = dict(index)
        elif mutation == 'foreign_map': index = dict(index, responses=dict(index['responses']))
        elif mutation == 'arbitrary_mapping':
            from collections import UserDict
            index = UserDict(index)
        elif mutation == 'forged': altered[0] = object()
        elif mutation == 'unadopted': altered[0] = rf._FinalizerMapProof()
        elif mutation == 'closed': proof.close()
        elif mutation == 'consumed':
            assert rf._finalizer_map_proof_matches(context, index, stable[0], ledger, 'hydration')
            assert rf._finalizer_map_proof_matches(context, index, stable[0], ledger, 'receipt')
        phase = 'receipt' if mutation == 'wrong_phase' else 'hydration'
        def check(): return rf._finalizer_map_proof_matches(tuple(altered), index, stable[0], ledger, phase)
        if mutation == 'process':
            with patch.object(rf.os, 'getpid', return_value=-1): assert not check()
        elif mutation == 'thread':
            with ThreadPoolExecutor(max_workers=1) as pool: assert not pool.submit(check).result()
        else: assert not check()
        return native(*args, **kw)
    with patch.object(registry, '_load_latest_response_observation_state', load):
        assert run(stable)['status'] == 'appended'


def test_issuance_requires_real_owner_verifier_and_first_proof(stable):
    for fn in (registry._FinalizerRegistration, registry._register_finalizer_readiness_observation):
        parameters = inspect.signature(fn).parameters
        assert set(parameters) == {'projection', 'frames_dir', 'registry_path'}
        for bad in ('verified_epoch', 'index_state', 'responses', 'proof', 'callback'):
            with pytest.raises(TypeError):
                fn(stable[1], frames_dir=stable[0], registry_path=stable[2], **{bad: {}})
    native = registry._select_graph_rebase_observation_response_ids; captured = []
    def select(**kw):
        context = kw['_finalizer_context']; captured.append(context)
        assert context[0]._FinalizerMapProof__phase == 'selection'
        with patch.object(rf, '_response_frame_index_has_verified_response_map', return_value=False):
            return native(**kw)
    with patch.object(registry, '_select_graph_rebase_observation_response_ids', select):
        assert run(stable)['status'] == 'selection_failed'
    assert captured[0][0]._FinalizerMapProof__phase == 'closed'
    captured[0][0]._bind(*captured[0][1:3], captured[0][3], stable[0], stable[2])
    assert captured[0][0]._FinalizerMapProof__phase == 'closed'


@pytest.mark.parametrize('entries', [1, 10000])
def test_guard_is_fixed_cost_without_map_access_io_or_digest(stable, entries):
    native = registry._load_latest_response_observation_state
    def load(*args, **kw):
        context = kw['_finalizer_context']; index = kw['index_state']; proof = context[0]
        # An adversarial test container detects iteration or structural comparison.
        class Map(dict):
            def __iter__(self): raise AssertionError('map iteration')
            def items(self): raise AssertionError('map items')
            def values(self): raise AssertionError('map values')
            def __eq__(self, other): raise AssertionError('map comparison')
            def __getitem__(self, key): raise AssertionError('map lookup')
        mapping = Map.fromkeys(range(entries), None)
        # Test-only transplant preserves the already validated fixed header shape;
        # production has no map injection or this escape hatch.
        original = index['responses']; count = index['response_map_entry_count']
        index['responses'] = mapping; index['response_map_entry_count'] = entries
        proof._FinalizerMapProof__responses = mapping
        header = proof._FinalizerMapProof__header
        proof._FinalizerMapProof__header = proof._header()
        try:
            with patch.object(rf, '_response_map_digest', side_effect=AssertionError('digest')), \
                 patch.object(rf, '_json_safe', side_effect=AssertionError('normalize')), \
                 patch.object(json, 'dumps', side_effect=AssertionError('serialize')), \
                 patch.object(json, 'loads', side_effect=AssertionError('parse')), \
                 patch.object(copy, 'deepcopy', side_effect=AssertionError('copy')), \
                 patch.object(Path, 'open', side_effect=AssertionError('open')), \
                 patch.object(rf, '_response_frame_file_state', wraps=rf._response_frame_file_state) as stat:
                assert proof._matches(context, index, stable[0], stable[0]/'responses.jsonl', 'hydration')
                assert stat.call_count == 3
        finally:
            index['responses'] = original; index['response_map_entry_count'] = count
            proof._FinalizerMapProof__responses = original; proof._FinalizerMapProof__header = header
        return native(*args, **kw)
    with patch.object(registry, '_load_latest_response_observation_state', load):
        assert run(stable)['status'] == 'appended'


@pytest.mark.parametrize('source', ['current_index.json', 'responses.jsonl'])
@pytest.mark.parametrize('mutation', ['append', 'replace', 'same_size', 'move'])
@pytest.mark.parametrize('seam', ['hydration', 'retention'])
def test_physical_mutations_disable_reuse_and_preserve_rejection(stable, source, mutation, seam):
    name = '_load_latest_response_observation_state' if seam == 'hydration' else '_append_graph_rebase_readiness_observation'
    native = getattr(registry, name); captured = []
    def changed(*args, **kw):
        context = kw['_finalizer_context']; captured.append(context)
        path = stable[0] / source
        if mutation == 'append':
            with path.open('ab') as handle: handle.write(b'\n')
        elif mutation == 'move': path.rename(path.with_suffix('.moved'))
        else:
            data = path.read_bytes()
            if mutation == 'replace': data += b'\n'
            new = path.with_suffix('.replacement'); new.write_bytes(data); new.replace(path)
        with patch.object(rf, 'state_flow_note', wraps=rf.state_flow_note) as note:
            try: return native(*args, **kw)
            finally: assert not any(c.kwargs.get('finalizer_map_proof_reuses') for c in note.call_args_list)
    with patch.object(registry, name, changed):
        try:
            result = run(stable)
            assert result['status'] != 'appended'
        except registry.GraphRebaseReadinessRegistryError as exc:
            assert exc.code == 'readiness_epoch_moved'
    assert captured[0][0]._FinalizerMapProof__phase == 'closed'
    assert not stable[2].exists()


@pytest.mark.parametrize('mutation', ['missing_coverage', 'malformed_coverage', 'stale_digest', 'wrong_index_path',
    'relocated', 'frame_id', 'sequence', 'superseded', 'source_epoch', 'projection'])
def test_authority_changes_keep_existing_rejection(stable, mutation):
    native = registry._append_graph_rebase_readiness_observation
    def changed(*args, **kw):
        epoch = kw['verified_epoch']; index = epoch['index_state']
        if mutation == 'missing_coverage': del index['response_map_verified_size_bytes']
        elif mutation == 'malformed_coverage': index['response_map_entry_count'] = 'bad'
        elif mutation == 'stale_digest': index['response_map_digest'] = '0'*64
        elif mutation == 'wrong_index_path': epoch['index_path'] = str(stable[0]/'other.json')
        elif mutation == 'relocated': epoch['relocated'] = True
        elif mutation == 'frame_id': index['responses']['reuse-response']['latest_frame_id'] = 'other'
        elif mutation == 'sequence': index['responses']['reuse-response']['latest_frame_sequence'] += 1
        elif mutation == 'superseded': rf.persist_response_frame(frame(), frames_dir=stable[0])
        elif mutation == 'source_epoch': kw['source_epoch'] = dict(kw['source_epoch'], source_epoch_id='wrong')
        elif mutation == 'projection': args = (dict(args[0], frame_id='wrong'),)
        return native(*args, **kw)
    with patch.object(registry, '_append_graph_rebase_readiness_observation', changed):
        with pytest.raises(registry.GraphRebaseReadinessRegistryError): run(stable)
    assert not stable[2].exists()


@pytest.mark.parametrize('mutation', ['missing', 'corrupt', 'cas_digest', 'same_bytes', 'witness', 'row_digest', 'receipt_binding', 'receipt_bytes'])
def test_snapshot_row_witness_and_observation_receipt_validation(stable, mutation):
    native = registry._append_graph_rebase_readiness_observation
    def changed(*args, **kw):
        candidate = kw['_observation_candidate']; binding, observed, digests, reads = candidate._receipt
        assert reads
        path = stable[0] / json.loads(reads[0][0])['path']
        if mutation == 'missing': path.unlink()
        elif mutation == 'corrupt': path.write_bytes(b'corrupt')
        elif mutation == 'cas_digest': path.write_bytes(path.read_bytes()[:-2] + b'XX')
        elif mutation == 'same_bytes':
            replacement = path.with_suffix('.replacement'); replacement.write_bytes(path.read_bytes()); replacement.replace(path)
        elif mutation == 'witness':
            reads = ((reads[0][0], '0'*64, reads[0][2]),) + reads[1:]
        elif mutation == 'row_digest': digests = ('0'*64,)
        elif mutation == 'receipt_binding': binding = b'wrong'
        else: observed = b'{invalid'
        candidate._receipt = binding, observed, digests, reads
        with patch.object(registry, 'load_latest_response_observation_state', wraps=rf.load_latest_response_observation_state) as fallback:
            if mutation in ('missing', 'corrupt', 'cas_digest'):
                with pytest.raises(registry.GraphRebaseReadinessRegistryError): native(*args, **kw)
                assert fallback.call_count == 1
                return {'ok': False, 'error': {'code': 'expected_test_rejection'}}
            if mutation == 'receipt_bytes':
                with pytest.raises(json.JSONDecodeError): native(*args, **kw)
                return {'ok': False}
            result = native(*args, **kw)
            assert fallback.call_count == 1
            assert kw['_finalizer_context'][0]._FinalizerMapProof__phase == 'closed'
            return result
    with patch.object(registry, '_append_graph_rebase_readiness_observation', changed):
        result = run(stable)
    assert result['status'] == ('append_failed' if mutation in ('missing','corrupt','cas_digest','receipt_bytes') else 'appended')


@pytest.mark.parametrize('mutation', ['replace', 'move', 'duplicate', 'collision', 'append_failure'])
def test_registry_is_independent_and_proof_revoked_before_mutation(stable, mutation):
    frames, projection, path = stable
    if mutation in ('replace','move','duplicate','collision'): assert run(stable)['status'] == 'appended'
    native = registry._append_graph_rebase_readiness_observation
    writer = registry.append_graph_rebase_readiness_registry_records
    def retain(*args, **kw):
        context = kw['_finalizer_context']
        if mutation == 'replace':
            new = path.with_suffix('.new'); new.write_bytes(path.read_bytes()); new.replace(path)
        elif mutation == 'move': path.rename(path.with_suffix('.old'))
        def write(*a, **k):
            assert context[0]._FinalizerMapProof__phase == 'closed'
            if mutation == 'append_failure':
                with patch.object(registry.os, 'fsync', side_effect=OSError(errno.ENOSPC, 'test full')):
                    return writer(*a, **k)
            if mutation == 'collision':
                parse = registry._parse_registry_bytes
                def collision(*x, **y):
                    current = parse(*x, **y)
                    # Simulate a hash collision after real schema/digest parsing.
                    current['record_bytes_by_id'] = {key: raw + b' ' for key, raw in current['record_bytes_by_id'].items()}
                    return current
                with patch.object(registry, '_parse_registry_bytes', collision): return writer(*a, **k)
            return writer(*a, **k)
        with patch.object(registry, 'append_graph_rebase_readiness_registry_records', write):
            return native(*args, **kw)
    with patch.object(registry, '_append_graph_rebase_readiness_observation', retain):
        result = run(stable)
    if mutation in ('collision','append_failure'):
        assert result['status'] == 'append_failed'
        assert result['error']['code'] == ('readiness_registry_record_id_collision' if mutation == 'collision' else 'readiness_registry_write_failed')
    else:
        assert result['status'] == ('appended' if mutation == 'move' else 'unchanged')


@pytest.mark.parametrize('seam', ['selection','hydration','retention'])
def test_exception_traceback_early_return_and_reentry_close(stable, seam):
    name = {'selection':'_select_graph_rebase_observation_response_ids', 'hydration':'_load_latest_response_observation_state', 'retention':'_append_graph_rebase_readiness_observation'}[seam]
    captured = []
    def failure(*a, **kw):
        captured.append(kw['_finalizer_context']); raise ValueError('test retained traceback')
    with patch.object(registry, name, failure):
        with pytest.raises(ValueError) as error: run(stable)
    assert error.value.__traceback__ is not None
    context = captured[0]
    assert context[0]._FinalizerMapProof__phase == 'closed'
    assert context[1]._FinalizerRegistration__epoch is None
    with pytest.raises(RuntimeError): context[1].run()


def test_reentrant_registration_cannot_borrow_foreign_proof(stable):
    native = registry._load_latest_response_observation_state; outer = []; inner = []
    def load(*a, **kw):
        context = kw['_finalizer_context']
        if not outer:
            outer.append(context)
            assert run((stable[0], stable[1], stable[2].with_suffix('.inner')))['status'] == 'appended'
        else:
            inner.append(context)
            assert not rf._finalizer_map_proof_matches(
                (outer[0][0], context[1], context[2], context[3]), kw['index_state'],
                stable[0], stable[0]/'responses.jsonl', 'hydration',
            )
        return native(*a, **kw)
    with patch.object(registry, '_load_latest_response_observation_state', load): assert run(stable)['status'] == 'appended'
    assert outer[0][1] is not inner[0][1]


def test_ordinary_wrappers_never_accept_finalizer_proof(stable):
    epoch = rf.verify_response_frame_epoch(frames_dir=stable[0]); index = epoch['index_state']
    with patch.object(rf, '_response_map_digest', wraps=rf._response_map_digest) as digest:
        rf.select_graph_rebase_observation_response_ids(frames_dir=stable[0], index_state=index)
        assert digest.call_count == 1
        rf.load_latest_response_observation_state('reuse-response', frames_dir=stable[0], index_state=index)
        assert digest.call_count == 2
        registry.append_graph_rebase_readiness_observation(stable[1], source_frame=epoch['source_frame_sha256_by_response']['reuse-response'], verified_epoch=epoch, frames_dir=stable[0], registry_path=stable[2])
        assert digest.call_count == 3
    for fn in (rf.select_graph_rebase_observation_response_ids, rf.load_latest_response_observation_state, registry.append_graph_rebase_readiness_observation):
        assert '_finalizer_context' not in inspect.signature(fn).parameters


def test_public_signatures_and_single_private_bind_callsite():
    # No public API expansion; bind is an internal audited loan, not an issuer API.
    source = inspect.getsource(registry)
    tree = ast.parse(source)
    binds = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == '_bind']
    assert len(binds) == 1
    proof = rf._FinalizerMapProof()
    assert not rf._finalizer_map_proof_matches((proof, object(), object(), {}), {}, Path('.'), Path('responses.jsonl'), 'hydration')

@pytest.mark.parametrize('mutation', ['missing_coverage','bad_count','bad_digest','malformed_index'])
def test_real_verifier_rejects_malformed_index_before_proof(stable, mutation):
    path = stable[0] / 'current_index.json'
    value = json.loads(path.read_text())
    if mutation == 'missing_coverage': value.pop('response_map_verified_size_bytes', None)
    elif mutation == 'bad_count': value['response_map_entry_count'] = 'bad'
    elif mutation == 'bad_digest': value['response_map_digest'] = '0'*64
    if mutation == 'malformed_index': path.write_text('{')
    else: path.write_text(json.dumps(value))
    with patch.object(registry, '_select_graph_rebase_observation_response_ids', wraps=registry._select_graph_rebase_observation_response_ids) as selection:
        assert run(stable)['status'] == 'verification_failed'
    assert selection.call_count == 0


@pytest.mark.parametrize('mutation', ['frame_id','sequence','not_selected','missing_row','corrupt_row'])
def test_early_results_close_and_row_reads_are_not_suppressed(stable, mutation):
    native = registry._select_graph_rebase_observation_response_ids; contexts = []
    def select(**kw):
        context = kw['_finalizer_context']; contexts.append(context)
        result = native(**kw)
        if mutation == 'not_selected': result['selected_response_ids'] = []
        elif mutation in ('missing_row','corrupt_row'):
            # Isolate the exact row authority after a valid map proof. A mocked
            # source reader returns its established failure; no digest bypass.
            pass
        return result
    if mutation == 'frame_id': stable[1]['frame_id'] = 'wrong'
    elif mutation == 'sequence': stable[1]['ledger_sequence'] += 1
    with patch.object(registry, '_select_graph_rebase_observation_response_ids', select):
        if mutation in ('missing_row','corrupt_row'):
            code = 'response_frame_index_missing_line' if mutation == 'missing_row' else 'response_frame_index_corrupt_line'
            with patch.object(rf, '_read_indexed_response_frame', return_value=(None, {'code':code})) as row:
                result = run(stable)
                assert row.call_count == 1
            assert result['status'] == 'hydration_failed'
        else:
            result = run(stable)
            assert result['status'] == ('not_relevant' if mutation == 'not_selected' else 'superseded_before_registration')
    assert contexts[0][0]._FinalizerMapProof__phase == 'closed'


@pytest.mark.parametrize("rebound", [False, True])
def test_relative_paths_preserve_reuse_or_existing_rebound_fallback(stable, monkeypatch, rebound):
    monkeypatch.chdir(stable[0].parent)
    frames = Path('frames')
    if not rebound:
        frames = Path('relative_frames')
        rf.persist_response_frame(frame(), frames_dir=frames)
    with patch.object(rf, '_response_map_digest', wraps=rf._response_map_digest) as digest:
        assert run((frames, stable[1], Path('registry.jsonl')))['status'] == 'appended'
    assert digest.call_count == (5 if rebound else 2)


def test_moved_epoch_diagnostics_are_detached_and_proof_closed(stable):
    native = registry._append_graph_rebase_readiness_observation; captured = []; records = []
    def retain(*a, **kw):
        captured.append(kw['_finalizer_context'])
        (stable[0]/'responses.jsonl').touch()
        return native(*a, **kw)
    with patch.object(registry, '_append_graph_rebase_readiness_observation', retain), \
         events.causal_scope(lambda **record: records.append(record)):
        with pytest.raises(registry.GraphRebaseReadinessRegistryError) as exc: run(stable)
    context = captured[0]; mapping = context[3]['index_state']['responses']
    assert 'epoch_retention' in exc.value.details
    assert not mutable_ids(mapping) & mutable_ids(exc.value.as_dict())
    assert records
    assert not mutable_ids(mapping) & mutable_ids(records)
    assert context[0]._FinalizerMapProof__phase == 'closed'


def test_nested_manifest_loan_is_detached_before_observation_returns(stable):
    native_load = registry._load_latest_response_observation_state
    native_ref = rf._observation_snapshot_ref
    loans = []
    def load(*args, **kw):
        mapping = kw['index_state']['responses']; before = copy.deepcopy(mapping)
        def ref(frame_value, manifest, *paths):
            # Force the supported manifest fallback using the real owned manifest.
            value = native_ref({}, manifest, *paths)
            if mutable_ids(value) & mutable_ids(mapping): loans.append(paths)
            return value
        with patch.object(rf, '_observation_snapshot_ref', ref): result = native_load(*args, **kw)
        assert loans and not mutable_ids(result) & mutable_ids(mapping)
        saved = copy.deepcopy(result); mutate_containers(result)
        assert mapping == before
        return saved
    with patch.object(registry, '_load_latest_response_observation_state', load):
        assert run(stable)['status'] == 'appended'
