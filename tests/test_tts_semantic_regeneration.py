"""Isolated policy mechanics using the existing lexical verifier and WAV checks."""
import copy
import hashlib
import json
import math
import struct
import threading
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from fruth_server.late_fill_runtime import LateFillRuntimeOwner
from fruth_server import tts_semantic_regeneration as policy
from fruth_services.tts_audio_integrity import build_tts_semantic_source, build_tts_audio_integrity_evidence
from fruth_services.response_persistence import ResponsePersistenceError, attach_persistence_failure

TEXT = 'The lighthouse is quiet.'
BAD = 'The night house is quiet.'


def wav(path, frequency):
    with wave.open(str(path), 'wb') as f:
        f.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        f.writeframes(b''.join(struct.pack('<h', int(9000 * math.sin(i * frequency / 24000))) for i in range(48000)))


@pytest.fixture
def env(tmp_path):
    o = object.__new__(LateFillRuntimeOwner)
    o.capability_text_to_speech = 'text_to_speech'
    o.normalize_capability = lambda v: v
    o.branch_id = lambda b: b.get('branch_id') or b.get('phase_id')
    o.branch_capability = lambda b: b.get('capability')
    o.parse_bool = lambda v, default=False: default if v is None else bool(v)
    o.late_fill_branch_control_records = lambda p: p.get('controls', {})
    o.late_fill_branch_dependency_ids = lambda b, **kw: b.get('depends_on', [])
    o.late_fill_text_from_result_payload = lambda r: r.get('result_text', '')
    o.saved_file_consumption_error = lambda *a, **kw: None
    o.late_fill_result_has_missing_dependency_evidence = lambda r: False
    o.log_unified_event = lambda **kw: None
    source = build_tts_semantic_source(TEXT, source_authority='final_infer_prompt',
                                     source_text_source='final_infer_prompt', branch_id='tts', phase_id='p-tts')
    paths = [tmp_path / 'original.wav', tmp_path / 'repair.wav']
    for i, p in enumerate(paths): wav(p, 1500 + i * 200)
    def produced(i):
        p = paths[i]
        return dict(capability='text_to_speech', branch_id='tts', phase_id='p-tts',
                    saved_audio_path=str(p), artifact_id=f'a-{i}', artifact_ref=f'artifact:a-{i}',
                    tts_semantic_source=copy.deepcopy(source),
                    tts_audio_integrity_evidence=build_tts_audio_integrity_evidence(p, TEXT))
    original = produced(0)
    original.update(fill_model='VoiceDesign', fill_instance_id='tts-instance', fill_backend='mlx_audio',
                    tts_generation_request=dict(prompt=TEXT, temperature=.9, top_p=1., top_k=50))
    tts = dict(branch_id='tts', phase_id='p-tts', capability='text_to_speech', content_payload=TEXT, status='fulfilled')
    stt = dict(branch_id='stt', phase_id='p-stt', capability='speech_to_text', depends_on=['p-tts'], status='pending')
    payload = dict(id='resp-policy', response_frame=dict(frame_id='resp-policy:frame-1', frame_sequence=1),
                   saved_audio_path=str(paths[0]), artifacts=[{'artifact_id': 'a-0', 'path': str(paths[0]), 'type': 'audio'}],
                   runtime={}, late_fill=dict(status='running', fill_results=[original], completed_branches=[tts],
                                             pending_branches=[stt], failed_branches=[]))
    result = dict(capability='speech_to_text', result_text=BAD)
    result['tts_stt_semantic_evidence'] = o.tts_stt_semantic_evidence_for_branch_result(stt, result, current_payload=payload)
    lock = threading.RLock(); checkpoints=[]; calls=[]
    durable_file = tmp_path/'durable.json'; durable_file.write_text(json.dumps(payload))
    def load(_):
        with lock:
            p=json.loads(durable_file.read_text())
            return dict(ok=True, response_payload=p, response_frame=p['response_frame'])
    def persist(p, **kw):
        with lock:
            previous=load(p['id'])['response_payload']['response_frame']
            if kw['expected_parent_frame_id'] != previous['frame_id']:
                raise RuntimeError('stale parent CAS')
            p=copy.deepcopy(p);number=previous['frame_sequence']+1
            p['response_frame']=dict(frame_id=f"resp-policy:frame-{number}", frame_sequence=number)
            durable_file.write_text(json.dumps(p));checkpoints.append(copy.deepcopy(p));return p
    o.finalize_response_frame_payload=persist;o.load_latest_response_state=load
    o.touch_response_lookup=lambda *a, **kw: None
    o.get_response_lookup_record=lambda rid: dict(response_payload=load(rid)['response_payload'])
    o.build_late_fill_materialization_branch_spec=lambda **kw: dict(prepare_args=kw)
    o.attach_late_fill_result_artifact_identity=lambda r, *a, **kw: r
    o.merge_late_fill_result_fields=lambda p,r: {**p, 'saved_audio_path': r['saved_audio_path'],
                                              'artifacts': [*p.get('artifacts', []), {'artifact_id': r['artifact_id'], 'path': r['saved_audio_path'], 'type':'audio'}]}
    options=dict(transcript=TEXT, technical_failure=False, same_path=False, wrong_stt=False)
    def prepare(**kw):
        branch=kw['branch'];cap=branch['capability'];current=kw['current_payload']
        ip=dict(prompt=TEXT)
        if cap=='speech_to_text':
            ip['file_path']=current['late_fill']['fill_results'][-1]['saved_audio_path']
            if options['wrong_stt']:ip['file_path']=str(paths[0])
        return dict(capability=cap, instance={'model':'VoiceDesign'}, route_info={'instance_id':'tts-instance'},
                    infer_payload=ip, effective_data={}, branch=branch)
    def execute(plan):
        assert load('resp-policy')['response_payload']['runtime'][policy.STATE_KEY]['tts']['remaining']==0
        calls.append(plan['capability'])
        if plan['capability']=='text_to_speech':
            assert plan['infer_payload']['prompt']==TEXT
            assert 'seed' not in plan['infer_payload']
            if options['technical_failure']:raise RuntimeError('transport failed')
            out=produced(0 if options['same_path'] else 1)
        else:out=dict(capability='speech_to_text', result_text=options['transcript'])
        return dict(infer_result=out, execution_contract={})
    args=dict(branch=stt,result=result,payload=payload,consumer_plan={'infer_payload':{'file_path':str(paths[0])}},
              request_payload={'prompt':TEXT},artifact_gap={},source_route_payload={},prepare_plan=prepare,execute_plan=execute)
    return SimpleNamespace(owner=o,args=args,paths=paths,source=source,original=original,produced=produced,
                           payload=payload,options=options,calls=calls,checkpoints=checkpoints,load=load,durable_file=durable_file)


def test_original_pass_no_repair(env):
    env.args['result']['result_text']=TEXT
    env.args['result']['tts_stt_semantic_evidence']=env.owner.tts_stt_semantic_evidence_for_branch_result(
        env.args['branch'], env.args['result'], current_payload=env.payload)
    assert policy.run(env.owner,**env.args) is None
    assert env.calls==[]


def test_repair_pass_replaces_only_authority_and_preserves_failed_evidence(env):
    old_bytes=env.paths[0].read_bytes()
    out=policy.run(env.owner,**env.args)
    assert out['accepted'] and env.calls==['text_to_speech','speech_to_text']
    p=out['payload'];state=policy.states(p)['tts']
    assert state['status']=='accepted' and state['remaining']==0
    assert state['attempt_id']!=state['repairs_attempt']
    assert state['original_result']['artifact_id']=='a-0'
    assert state['repair_result']['artifact_id']=='a-1'
    assert p['saved_audio_path']==str(env.paths[1])
    assert [a['artifact_id'] for a in p['artifacts']]==['a-1']
    assert env.paths[0].read_bytes()==old_bytes
    assert env.checkpoints[0]['runtime'][policy.STATE_KEY]['tts']['status']=='consumed'
    assert not env.checkpoints[0]['late_fill']['completed_branches']
    assert not env.checkpoints[1]['late_fill']['fill_results']  # B not authoritative before STT PASS
    assert out['infer_result']['tts_stt_semantic_evidence']['status']=='matched'


def test_repair_mismatch_no_third_and_restart_budget_preserved(env):
    env.options['transcript']=BAD
    out=policy.run(env.owner,**env.args)
    assert not out['accepted'] and env.calls==['text_to_speech','speech_to_text']
    state=policy.states(out['payload'])['tts']
    assert state['status']=='exhausted' and state['repair_semantic_evidence']['status']=='mismatched'
    assert not out['payload']['late_fill']['fill_results']
    assert policy.run(env.owner,**env.args) is None  # stale duplicate review sees durable state
    assert len(env.calls)==2


@pytest.mark.parametrize('failure',['missing','corrupt','wrong_binding','stt_unavailable','stt_error','cancel','defer','ambiguous','source_drift','seeded','opt_out'])
def test_noneligible_classes_do_not_regenerate(env,failure):
    if failure=='missing':env.paths[0].unlink()
    elif failure=='corrupt':env.paths[0].write_bytes(b'not a WAV')
    elif failure=='wrong_binding':env.args['consumer_plan']['infer_payload']['file_path']=str(env.paths[1])
    elif failure in ('stt_unavailable','stt_error'):env.args['result']['tts_stt_semantic_evidence']['status']='unavailable'
    elif failure=='cancel':env.args['branch']['cancel_requested']=True
    elif failure=='defer':env.args['branch']['status']='deferred'
    elif failure=='ambiguous':env.payload['late_fill']['fill_results'].append(copy.deepcopy(env.original))
    elif failure=='source_drift':env.original['tts_semantic_source']['tts_source_text']='Other words'
    elif failure=='seeded':env.original.pop('tts_generation_request')
    elif failure=='opt_out':env.args['branch']['automatic_follow_up_allowed']=False
    assert policy.run(env.owner,**env.args) is None
    assert env.calls==[]


@pytest.mark.parametrize('option',['technical_failure','same_path','wrong_stt'])
def test_failed_repair_preserves_exhaustion_and_cannot_resubmit(env,option):
    env.options[option]=True
    out=policy.run(env.owner,**env.args)
    assert not out['accepted'] and policy.states(out['payload'])['tts']['status']=='exhausted'
    assert policy.run(env.owner,**env.args) is None
    assert env.calls.count('text_to_speech')==1


def test_checkpoint_failure_executes_nothing(env):
    env.owner.finalize_response_frame_payload=lambda p,**kw:p
    with pytest.raises(RuntimeError,match='not durable'):policy.run(env.owner,**env.args)
    assert env.calls==[]


@pytest.mark.parametrize('checkpoint_number', [1, 2, 3])
def test_uncertain_checkpoint_stops_without_failure_checkpoint_or_repeated_work(env, checkpoint_number):
    persist = env.owner.finalize_response_frame_payload
    attempts = []
    failures = []
    def uncertain(p, **kw):
        attempts.append(copy.deepcopy(p))
        if len(attempts) == checkpoint_number:
            failure = ResponsePersistenceError(attach_persistence_failure(p, {
                'status': 'uncertain', 'stage': 'ledger_fsync', 'automatic_retry': False,
            }))
            failures.append(failure)
            raise failure
        return persist(p, **kw)
    env.owner.finalize_response_frame_payload = uncertain
    with pytest.raises(ResponsePersistenceError) as raised:
        policy.run(env.owner, **env.args)
    assert raised.value is failures[0]
    assert len(attempts) == checkpoint_number
    assert len(env.checkpoints) == checkpoint_number - 1
    assert env.calls == ['text_to_speech', 'speech_to_text'][:checkpoint_number - 1]
    assert 'repair_exhausted' not in policy.states(raised.value.response_payload)['tts']['events']


def test_restart_after_consumed_checkpoint_never_reexecutes(env):
    original=env.owner.finalize_response_frame_payload
    def crash(p,**kw):
        saved=original(p,**kw)
        raise SystemExit('simulated process death after durable budget consumption')
    env.owner.finalize_response_frame_payload=crash
    with pytest.raises(SystemExit):policy.run(env.owner,**env.args)
    env.owner.finalize_response_frame_payload=original
    assert policy.run(env.owner,**env.args) is None
    assert env.calls==[]


def test_unrelated_sibling_artifact_and_budget_are_not_replaced(env):
    sibling={**env.produced(1),'branch_id':'sibling','phase_id':'p-sibling','artifact_id':'sibling-a'}
    env.payload['late_fill']['fill_results'].append(sibling)
    env.payload['late_fill']['completed_branches'].append(dict(branch_id='sibling',phase_id='p-sibling',capability='text_to_speech'))
    env.payload['artifacts'].append(dict(artifact_id='sibling-a',path=sibling['saved_audio_path'],type='audio'))
    env.payload['runtime'][policy.STATE_KEY]={'sibling': {'status':'accepted','remaining':0}}
    # Full independent sibling state is included in this response's CAS checkpoint.
    out=policy.run(env.owner,**env.args)
    assert out['accepted']
    assert policy.states(out['payload'])['sibling']==env.payload['runtime'][policy.STATE_KEY]['sibling']
    assert any(a['artifact_id']=='sibling-a' for a in out['payload']['artifacts'])


def test_request_snapshot_never_recovers_a_provider_rng(env):
    assert policy.request_snapshot({'infer_payload':{'prompt':TEXT,'seed':123}},env.original)=={}
    assert policy.request_snapshot({'infer_payload':{'prompt':'wrapper','temperature':.9}},env.original)['prompt']==TEXT


def test_real_frame_roundtrip_keeps_budget_attempts_and_accepted_output(env,tmp_path):
    from fruth_services.response_frames import build_response_frame, persist_response_frame, load_latest_response_state
    from fruth_services.responses import build_canonical_response_artifacts
    out=policy.run(env.owner,**env.args)
    frame=build_response_frame(out['payload'],request_payload={'prompt':TEXT})
    frames=tmp_path/'frames'
    persist_response_frame(frame,frames_dir=frames)
    restored=load_latest_response_state(env.payload['id'],frames_dir=frames)
    assert restored['ok']
    recovered=restored['response_payload']
    assert policy.states(recovered)['tts']['remaining']==0
    assert policy.states(recovered)['tts']['original_result']['artifact_id']=='a-0'
    artifacts=build_canonical_response_artifacts(recovered)
    assert any(a.get('path')==str(env.paths[1]) for a in artifacts)
    assert not any(a.get('path')==str(env.paths[0]) for a in artifacts)


def test_concurrent_duplicate_review_only_one_backend_attempt(env):
    from concurrent.futures import ThreadPoolExecutor
    barrier=threading.Barrier(2)
    persist=env.owner.finalize_response_frame_payload
    def competing(p,**kw):
        if policy.states(p)['tts']['status']=='consumed':barrier.wait(timeout=5)
        return persist(p,**kw)
    env.owner.finalize_response_frame_payload=competing
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(policy.run,env.owner,**copy.copy(env.args)) for _ in range(2)]
        outcomes=[]
        for f in futures:
            try:outcomes.append(f.result())
            except RuntimeError as exc:assert 'stale parent CAS' in str(exc)
    assert len(outcomes)==1 and outcomes[0]['accepted']
    assert env.calls.count('text_to_speech')==1


@pytest.mark.parametrize('repair_pass', [True, False])
def test_late_fill_integration_reenters_existing_semantic_gate(env,monkeypatch,repair_pass):
    # Reuse the Responses test isolation setup; no production inference/registry.
    from test_responses_api import ResponsesApiTests
    import fruth_webserver as web
    harness=ResponsesApiTests(methodName='runTest');harness.setUp()
    try:
        payload=copy.deepcopy(env.payload)
        tts=copy.deepcopy(payload['late_fill']['completed_branches'][0]);tts.update(output_type='audio',requires_artifact=True)
        stt=copy.deepcopy(env.args['branch']);stt.update(output_type='text')
        graph=dict(current_phase_id='root', phases=[dict(phase_id='root',branch_id='root',capability='chat',output_type='text',status='completed'),tts,stt],downstream_branches=[tts,stt])
        payload['runtime']['request_phase_graph']=graph
        payload['late_fill'].update(expected_capability='speech_to_text',pending_branches=[stt],pending_capabilities=['speech_to_text'],completed_capabilities=['text_to_speech'])
        payload.update(mode='chat',status='completed',output_text='Audio verification pending.')
        env.durable_file.write_text(json.dumps(payload))
        calls=[]
        def prepare(**kw):
            gap=kw['artifact_gap'];cap=kw['expected_capability'];pid=gap.get('branch_id') or gap.get('expected_branch_id')
            ip=dict(prompt=TEXT)
            if cap=='speech_to_text':
                producers=[r for r in kw['current_payload']['late_fill']['fill_results'] if r.get('branch_id')=='tts']
                ip['file_path']=producers[0]['saved_audio_path']
            return dict(branch_id=pid,phase_id=gap.get('phase_id') or gap.get('expected_phase_id'),capability=cap,infer_payload=ip,effective_data={},instance={'model':'VoiceDesign'},route_info={'instance_id':'tts-instance'},execution_contract=gap.get('execution_contract') or {})
        def execute(plan):
            calls.append(plan['capability'])
            result=env.produced(1) if plan['capability']=='text_to_speech' else dict(capability='speech_to_text',result_text=BAD if calls.count('speech_to_text')==1 or not repair_pass else TEXT)
            return dict(infer_result=result,route_info=plan['route_info'],instance=plan['instance'],effective_data=plan['effective_data'],execution_contract=plan['execution_contract'])
        original_finalize=web._LATE_FILL_RUNTIME.finalize_response_frame_payload
        def finalize(p,**kw):
            if kw.get('expected_parent_frame_id'):return env.owner.finalize_response_frame_payload(p,**kw)
            return original_finalize(p,**kw)
        monkeypatch.setattr(web._LATE_FILL_RUNTIME,'finalize_response_frame_payload',finalize)
        monkeypatch.setattr(web._LATE_FILL_RUNTIME,'load_latest_response_state',env.load)
        monkeypatch.setattr(web,'_prepare_late_fill_branch_plan',prepare)
        monkeypatch.setattr(web,'_execute_prepared_late_fill_branch',execute)
        monkeypatch.setattr(web._LATE_FILL_RUNTIME,'schedule_terminal_substrate_hygiene',lambda *a,**kw:None)
        # The scheduler observes TESTING only inside Flask's app context. Keep
        # successor work from escaping this fixture into another test's store.
        with web.app.app_context():
            web._complete_response_late_fill(response_payload=payload,request_payload={'prompt':'Speak and check the exact sentence.'},assistant_message='',artifact_gap={'expected_capability':'speech_to_text','pending_branches':[stt],'pending_capabilities':['speech_to_text']},source_route_payload={'route_runtime':{'request_phase_graph':graph}})
        assert not web._RESPONSE_LATE_FILL_IN_FLIGHT
        final=web._RESPONSE_LOOKUP[payload['id']]['response_payload']
        assert calls==['speech_to_text','text_to_speech','speech_to_text'], (calls, final.get('late_fill'))
        if not repair_pass:
            assert policy.states(final)['tts']['status']=='exhausted'
            assert final['late_fill']['failed_branches']
            assert final['runtime']['graph_closure_review']['status']!='fulfilled'
            assert not any(a.get('path') in map(str, env.paths) for a in final.get('artifacts', []))
            return
        assert policy.states(final)['tts']['status']=='accepted'
        assert any(r.get('tts_stt_semantic_evidence',{}).get('status')=='matched' for r in final['late_fill']['fill_results'])
        assert not final['late_fill']['failed_branches']
        assert final['late_fill']['status']=='completed'
        assert final['runtime']['graph_closure_review']['status']=='fulfilled'
        assert not any(a.get('path')==str(env.paths[0]) for a in final.get('artifacts', []))
        assert any(a.get('path')==str(env.paths[1]) for a in final.get('artifacts', []))
    finally:harness.tearDown()


def test_recovered_or_reprojected_producer_cannot_execute_again(env):
    out=policy.run(env.owner,**env.args)
    for branch in [dict(branch_id='tts',capability='text_to_speech'),
                   dict(branch_id='repair-renamed',phase_id='p-tts',capability='text_to_speech')]:
        error=policy.consumed_execution_error(branch,out['payload'])
        assert error['code']=='TTS_SEMANTIC_REGENERATION_EXHAUSTED' and not error['retryable']
    assert policy.consumed_execution_error(dict(branch_id='other',capability='text_to_speech'),out['payload']) is None


def test_two_tts_branches_have_independent_one_attempt_budgets(env,tmp_path):
    second_a=tmp_path/'second-original.wav';second_b=tmp_path/'second-repair.wav'
    wav(second_a,2100);wav(second_b,2200)
    source2={**env.source,'branch_id':'tts2','phase_id':'p-tts2'}
    original2={**copy.deepcopy(env.original),'branch_id':'tts2','phase_id':'p-tts2',
               'saved_audio_path':str(second_a),'artifact_id':'a2-0','artifact_ref':'artifact:a2-0',
               'tts_semantic_source':source2,
               'tts_audio_integrity_evidence':build_tts_audio_integrity_evidence(second_a,TEXT)}
    branch2=dict(branch_id='tts2',phase_id='p-tts2',capability='text_to_speech',status='fulfilled',content_payload=TEXT)
    consumer2=dict(branch_id='stt2',phase_id='p-stt2',capability='speech_to_text',depends_on=['p-tts2'],status='pending')
    env.payload['late_fill']['fill_results'].append(original2)
    env.payload['late_fill']['completed_branches'].append(branch2)
    env.payload['late_fill']['pending_branches'].append(consumer2)
    env.payload['artifacts'].append(dict(path=str(second_a),artifact_id='a2-0',type='audio'))
    first=policy.run(env.owner,**env.args)
    assert first['accepted']
    result2=dict(capability='speech_to_text',result_text=BAD)
    result2['tts_stt_semantic_evidence']=env.owner.tts_stt_semantic_evidence_for_branch_result(consumer2,result2,current_payload=first['payload'])
    calls=[]
    def execute_second(plan):
        calls.append(plan['capability'])
        if plan['capability']=='speech_to_text':return dict(infer_result=dict(capability='speech_to_text',result_text=TEXT))
        return dict(infer_result={**copy.deepcopy(original2),'saved_audio_path':str(second_b),
                                  'artifact_id':'a2-1','artifact_ref':'artifact:a2-1',
                                  'tts_audio_integrity_evidence':build_tts_audio_integrity_evidence(second_b,TEXT)})
    second=policy.run(env.owner,**{**env.args,'payload':first['payload'],'branch':consumer2,'result':result2,
                                  'consumer_plan':{'infer_payload':{'file_path':str(second_a)}},'execute_plan':execute_second})
    assert second['accepted'] and calls==['text_to_speech','speech_to_text']
    state=policy.states(second['payload'])
    assert state['tts']['remaining']==state['tts2']['remaining']==0
    assert state['tts']['attempt_id']!=state['tts2']['attempt_id']
    assert state['tts']['repair_result']['saved_audio_path']==str(env.paths[1])
    assert state['tts2']['repair_result']['saved_audio_path']==str(second_b)
    assert {a['path'] for a in second['payload']['artifacts']}=={str(env.paths[1]),str(second_b)}


def test_registry_records_accept_repair_without_rewriting_original(env,tmp_path):
    from fruth_services.artifact_registry import persist_output_artifact_registry_records
    ledger=tmp_path/'registry.jsonl'
    persist_output_artifact_registry_records(env.payload,ledger_path=ledger)
    old_lines=ledger.read_bytes()
    out=policy.run(env.owner,**env.args)
    records=persist_output_artifact_registry_records(out['payload'],ledger_path=ledger)
    assert records and all(r['artifact']['path']==str(env.paths[1]) for r in records)
    assert ledger.read_bytes().startswith(old_lines)
    assert policy.states(out['payload'])['tts']['original_result']['saved_audio_path']==str(env.paths[0])


def test_copied_failed_audio_under_fresh_path_is_not_accepted(env):
    env.paths[1].write_bytes(env.paths[0].read_bytes())
    out=policy.run(env.owner,**env.args)
    assert not out['accepted']
    assert env.calls==['text_to_speech']
    assert 'failed audio bytes' in policy.states(out['payload'])['tts']['error']


@pytest.mark.parametrize('moment', ['before', 'during_prepare'])
def test_explicit_defer_control_prevents_generation(env,moment):
    def defer():
        p=env.load('resp-policy')['response_payload']
        p['late_fill']['branch_controls']=[{'branch_id':'tts','action':'defer'}]
        env.durable_file.write_text(json.dumps(p))
    if moment=='before':
        env.payload['late_fill']['branch_controls']=[{'branch_id':'tts','action':'defer'}]
    else:
        prepare=env.args['prepare_plan']
        def deferred_prepare(**kw):
            p=prepare(**kw);defer();return p
        env.args['prepare_plan']=deferred_prepare
    out=policy.run(env.owner,**env.args)
    assert out is None or not out['accepted']
    assert env.calls==[]
