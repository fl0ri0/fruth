"""Real finalizer/CAS/ledger recovery for semantic-repair reservations; no models."""
import copy
import importlib.util
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from fruth_server import tts_semantic_regeneration as policy
from fruth_services.response_frames import load_latest_response_state


@pytest.fixture
def real_checkpoint(tmp_path, monkeypatch):
    import fruth_webserver as web
    spec = importlib.util.spec_from_file_location('policy_test_fixture', Path(__file__).with_name('test_tts_semantic_regeneration.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    e = module.env.__wrapped__(tmp_path)
    frames = tmp_path / 'frames'
    monkeypatch.setitem(web.app.config, 'TESTING', False)
    monkeypatch.setattr(web, 'RESPONSE_FRAMES_DIR', frames)
    monkeypatch.setattr(web, 'ARTIFACT_REGISTRY_LEDGER', tmp_path / 'registry.jsonl')
    monkeypatch.setattr(web, '_register_durable_graph_rebase_readiness_observation', lambda p: {'status': 'not_applicable'})
    seed = copy.deepcopy(e.payload)
    seed.pop('response_frame')
    with web.app.app_context():
        parent = web._finalize_response_frame_payload(seed, persist=True)
    e.payload.clear()
    e.payload.update(parent)
    e.trace = []
    def load(rid):
        result = load_latest_response_state(rid, frames_dir=frames)
        e.trace.append(('load', copy.deepcopy(result)))
        return result
    def finalize(payload, **kwargs):
        e.trace.append(('before', copy.deepcopy(payload), copy.deepcopy(kwargs)))
        with web.app.app_context():
            result = web._finalize_response_frame_payload(payload, **kwargs)
        e.trace.append(('returned', copy.deepcopy(result)))
        return result
    e.owner.finalize_response_frame_payload = finalize
    e.owner.load_latest_response_state = load
    e.owner.get_response_lookup_record = lambda rid: {'response_payload': load(rid)['response_payload']}
    # The fixture backend's reservation assertion also reads the real ledger.
    original_execute = e.args['execute_plan']
    def execute(plan):
        durable = load(e.payload['id'])
        assert durable['ok'] and policy.states(durable['response_payload'])['tts']['remaining'] == 0
        e.durable_file.write_text(json.dumps(durable['response_payload']))
        return original_execute(plan)
    e.args['execute_plan'] = execute
    e.frames = frames
    return e


def test_real_checkpoint_allows_one_fresh_repair(real_checkpoint):
    e = real_checkpoint
    try:
        result = policy.run(e.owner, **e.args)
    except RuntimeError:
        before = next(t[1] for t in e.trace if t[0] == 'before')
        returned = next(t[1] for t in e.trace if t[0] == 'returned')
        after = e.trace[-1][1]
        print('CHECKPOINT PREDICATES', json.dumps({
            'ok': after.get('ok'), 'returned_frame': returned.get('response_frame', {}).get('frame_id'),
            'recovered_frame': after.get('response_frame', {}).get('frame_id'),
            'expected': policy.states(before), 'recovered': policy.states(after.get('response_payload') or {}),
        }, default=str))
        raise
    assert result['accepted']
    assert e.calls == ['text_to_speech', 'speech_to_text']
    recovered = load_latest_response_state(e.payload['id'], frames_dir=e.frames)
    entry = policy.states(recovered['response_payload'])['tts']
    assert entry['status'] == 'accepted' and entry['remaining'] == 0
    assert entry['original_result']['saved_audio_path'] == str(e.paths[0])
    assert recovered['response_payload']['saved_audio_path'] == str(e.paths[1])
    assert e.paths[0].exists() and e.paths[1].exists()
    assert policy.run(e.owner, **e.args) is None
    assert e.calls == ['text_to_speech', 'speech_to_text']


def test_actual_append_failure_never_calls_backend(real_checkpoint, monkeypatch):
    import fruth_webserver as web
    e = real_checkpoint
    def fail(*a, **kw):
        raise OSError('injected disk append failure')
    monkeypatch.setattr(web, '_append_response_frame_with_parent_cas', fail)
    with pytest.raises(RuntimeError, match='checkpoint not durable'):
        policy.run(e.owner, **e.args)
    assert e.calls == []
    state = load_latest_response_state(e.payload['id'], frames_dir=e.frames)
    assert state['response_frame']['frame_sequence'] == 1
    assert not policy.states(state['response_payload'])


def test_actual_unreadable_ledger_never_calls_backend(real_checkpoint):
    e = real_checkpoint
    original = e.owner.finalize_response_frame_payload
    def corrupt_after_append(*a, **kw):
        result = original(*a, **kw)
        (e.frames / 'responses.jsonl').write_text('corrupt durable ledger\n')
        return result
    e.owner.finalize_response_frame_payload = corrupt_after_append
    with pytest.raises(RuntimeError, match='checkpoint not durable'):
        policy.run(e.owner, **e.args)
    assert e.calls == []
    assert not load_latest_response_state(e.payload['id'], frames_dir=e.frames)['ok']


@pytest.mark.parametrize('mutation', ['unavailable', 'old_frame', 'wrong_frame',
                                     'missing_zero', 'reset_budget', 'changed_attempt',
                                     'changed_source', 'lost_failed_artifact', 'changed_audit_verdict'])
def test_canonical_comparison_keeps_required_durability_checks(real_checkpoint, mutation):
    e = real_checkpoint
    load = e.owner.load_latest_response_state
    def bad_readback(rid):
        result = load(rid)
        if result.get('frame_count', 0) < 2:
            return result
        entry = policy.states(result['response_payload'])['tts']
        if mutation == 'unavailable':
            return {'ok': False}
        if mutation == 'old_frame':
            result['response_frame']['frame_id'] = rid + ':frame-1'
        elif mutation == 'wrong_frame':
            result['response_frame']['frame_id'] = 'foreign:frame-2'
        elif mutation == 'missing_zero':
            entry.pop('remaining')
        elif mutation == 'reset_budget':
            entry['budget_after'] = 0
        elif mutation == 'changed_attempt':
            entry['attempt_id'] = 'foreign'
        elif mutation == 'changed_source':
            entry['original_result']['tts_semantic_source']['tts_source_text'] = 'other words'
        elif mutation == 'lost_failed_artifact':
            entry['original_result'].pop('artifact_ref')
        elif mutation == 'changed_audit_verdict':
            entry['original_semantic_evidence']['status'] = 'matched'
        return result
    e.owner.load_latest_response_state = bad_readback
    with pytest.raises(RuntimeError, match='checkpoint not durable'):
        policy.run(e.owner, **e.args)
    assert e.calls == []
    actual = load_latest_response_state(e.payload['id'], frames_dir=e.frames)
    assert actual['ok'] and policy.states(actual['response_payload'])['tts']['remaining'] == 0


def test_crash_after_real_reservation_recovers_without_duplicate(real_checkpoint):
    e = real_checkpoint
    class Crash(BaseException):
        pass
    original = e.owner.finalize_response_frame_payload
    def crash_after_commit(*a, **kw):
        original(*a, **kw)
        raise Crash('process lost immediately after durable reservation')
    e.owner.finalize_response_frame_payload = crash_after_commit
    with pytest.raises(Crash):
        policy.run(e.owner, **e.args)
    e.owner.finalize_response_frame_payload = original
    recovered = load_latest_response_state(e.payload['id'], frames_dir=e.frames)
    assert recovered['ok'] and recovered['response_frame']['frame_sequence'] == 2
    entry = policy.states(recovered['response_payload'])['tts']
    assert entry['budget_after'] == entry['maximum_semantic_regenerations'] == 1
    assert entry['remaining'] == 0
    before = (e.frames / 'responses.jsonl').read_bytes()
    assert policy.run(e.owner, **e.args) is None
    assert e.calls == [] and (e.frames / 'responses.jsonl').read_bytes() == before


def test_concurrent_real_parent_cas_allows_only_one_reservation(real_checkpoint):
    e = real_checkpoint
    barrier = threading.Barrier(2)
    original = e.owner.finalize_response_frame_payload
    def synchronize(payload, **kwargs):
        if kwargs.get('expected_parent_frame_sequence') == 1:
            barrier.wait(timeout=10)
        return original(payload, **kwargs)
    e.owner.finalize_response_frame_payload = synchronize
    def run():
        try:
            return policy.run(e.owner, **copy.deepcopy(e.args))
        except RuntimeError as exc:
            return exc
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert sum(isinstance(x, dict) and x.get('accepted', False) for x in results) == 1
    assert e.calls == ['text_to_speech', 'speech_to_text']
    state = load_latest_response_state(e.payload['id'], frames_dir=e.frames)
    assert policy.states(state['response_payload'])['tts']['budget_after'] == 1


@pytest.mark.parametrize('failure', ['technical', 'second_mismatch'])
def test_failed_second_attempt_exhausts_real_durable_budget(real_checkpoint, failure):
    e = real_checkpoint
    if failure == 'technical':
        e.options['technical_failure'] = True
    else:
        e.options['transcript'] = 'The night house is quiet.'
    result = policy.run(e.owner, **e.args)
    assert not result['accepted']
    assert e.calls.count('text_to_speech') == 1
    state = load_latest_response_state(e.payload['id'], frames_dir=e.frames)
    entry = policy.states(state['response_payload'])['tts']
    assert entry['status'] == 'exhausted' and entry['remaining'] == 0
    assert entry['original_result']['saved_audio_path'] == str(e.paths[0])
    assert e.paths[0].exists()
    assert state['response_payload'].get('saved_audio_path') != str(e.paths[0])
    assert state['response_payload'].get('runtime', {}).get('graph_closure_review', {}).get('status') != 'fulfilled'
    assert policy.run(e.owner, **e.args) is None
    assert e.calls.count('text_to_speech') == 1


@pytest.mark.parametrize('profile', [
    {'semantic_role_ids': ['possibility_expander', 'materializer', 'quality_reviewer']},
    {'developer_flags': {'planner_timeout_ms': 7200000}},
    {'developer_flags': {'accepted_learning_authority': 'preferred'}},
])
@pytest.mark.parametrize('second_mismatch', [False, True])
def test_checkpoint_lookup_keeps_exact_frozen_representation(
    real_checkpoint, monkeypatch, tmp_path, profile, second_mismatch,
):
    """A read during append followed by checkpoint publication has one frame body."""
    import fruth_webserver as web
    from scripts.self_attack_checks import audit_history
    from scripts.run_graph_rebase_shadow_corpus import stable_digest

    e = real_checkpoint
    e.args['request_payload'].update(profile)
    e.payload['status'] = 'completed'
    if second_mismatch:
        e.options['transcript'] = 'The night house is quiet.'
    observations = []
    parent_bytes = (e.frames / 'responses.jsonl').read_bytes()
    records = {}
    monkeypatch.setattr(web._RESPONSES_RUNTIME, 'get_response_lookup_record',
                        lambda rid: copy.deepcopy(records.get(rid)))
    # Isolated registry; never let this test recover into the production singleton.
    def recover(rid):
        durable = load_latest_response_state(rid, frames_dir=e.frames)
        records[rid] = {'id': rid, 'status': 'in_progress',
                        'response_payload': durable['response_payload']}
        return copy.deepcopy(records[rid]), None, 200
    monkeypatch.setattr(web, '_recover_response_lookup_record_from_frames', recover)
    original_touch = e.owner.touch_response_lookup
    def publish(rid, **kwargs):
        # HTTP can observe the new durable frame while the finalizer is still
        # finishing, before checkpoint() publishes its in-memory return value.
        durable = load_latest_response_state(rid, frames_dir=e.frames)
        observations.append(copy.deepcopy(durable['response_payload']))
        live = copy.deepcopy(kwargs['response_payload'])
        # A recovered parent carries this envelope through successor construction.
        # Its mere presence must not make the successor's expanded body canonical.
        live['durability'] = copy.deepcopy(durable['response_payload']['durability'])
        live['runtime']['observer_transient_probe'] = 'retain top-level progress'
        records[rid] = {'id': rid, 'status': 'in_progress', 'response_payload': live}
        observed = web._get_response_lookup_record(rid)['response_payload']
        assert observed['runtime']['observer_transient_probe'] == 'retain top-level progress'
        observations.append(copy.deepcopy(observed))
        original_touch(rid, **kwargs)
    e.owner.touch_response_lookup = publish
    result = policy.run(e.owner, **e.args)
    assert result['accepted'] is not second_mismatch
    assert (e.frames / 'responses.jsonl').read_bytes().startswith(parent_bytes)
    assert e.calls == ['text_to_speech', 'speech_to_text']
    assert policy.run(e.owner, **e.args) is None
    evidence = {'observations': observations, 'findings': audit_history(observations),
                'hashes': [stable_digest(p['response_frame']) for p in observations]}
    (tmp_path / 'same-frame-observations.json').write_text(json.dumps(evidence, indent=2))
    assert all(p['response_frame'].get('status') == 'completed' for p in observations)
    assert evidence['findings'] == []
    assert [p['response_frame']['frame_sequence'] for p in observations] == [2, 2, 3, 3, 4, 4]
    # The passing control is repeated canonical loading without publication.
    assert audit_history([observations[0], copy.deepcopy(observations[0])]) == []


def test_first_semantic_pass_repeated_durable_observation_is_stable(real_checkpoint):
    from scripts.self_attack_checks import audit_history
    e = real_checkpoint
    e.args['result']['result_text'] = 'The lighthouse is quiet.'
    e.args['result']['tts_stt_semantic_evidence'] = e.owner.tts_stt_semantic_evidence_for_branch_result(
        e.args['branch'], e.args['result'], current_payload=e.payload)
    before = (e.frames / 'responses.jsonl').read_bytes()
    assert policy.run(e.owner, **e.args) is None
    assert e.calls == []
    reads = [load_latest_response_state(e.payload['id'], frames_dir=e.frames)['response_payload']
             for _ in range(3)]
    assert reads[0]['response_frame'] == reads[1]['response_frame'] == reads[2]['response_frame']
    assert audit_history(reads) == []
    assert (e.frames / 'responses.jsonl').read_bytes() == before
