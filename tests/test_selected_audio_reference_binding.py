"""Exact retained-source authority at the physical STT handoff, no models."""
import copy
import hashlib
import json
import shutil
import wave
from pathlib import Path
from types import SimpleNamespace
import pytest
from ollmo_server.infer_runtime import InferRuntimeOwner
from ollmo_services.artifact_registry import find_artifact_registry_record_by_artifact_ref
from ollmo_core.transports import resolve_saved_artifact_path
from ollmo_core.inference import InferArtifacts, _run_speech_to_text

@pytest.fixture
def binding(tmp_path):
    root=tmp_path.resolve()
    source=root/'source.wav'
    with wave.open(str(source),'wb') as w:
        w.setparams((1,2,16000,0,'NONE','not compressed'));w.writeframes(b'\x10\x00'*1600)
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    a=dict(type='audio',artifact_id='audio_source',artifact_ref='artifact:audio_source',
           path=str(source),source_response_id='source',branch_id='producer',phase_id='phase-1')
    payload=dict(id='source',artifacts=[copy.deepcopy(a)],response_frame={'frame_id':'source:frame-2','frame_sequence':2},
                 tts_audio_integrity_evidence=dict(kind='ollmo.tts_audio_integrity_evidence',authority='runtime_deterministic_audio_verification',artifact_path=str(source),artifact_sha256=digest,status='passed'))
    registry=dict(artifact_ref=a['artifact_ref'],artifact_id=a['artifact_id'],artifact=copy.deepcopy(a),artifact_alias_refs=[a['artifact_ref']],provenance={'source':{'response_id':'source','branch_id':'producer','phase_id':'phase-1'}})
    ledger=root/'registry.jsonl'
    ledger.write_text(json.dumps(registry)+'\n')
    owner=object.__new__(InferRuntimeOwner)
    owner.hooks=dict(find_artifact_registry_record_by_artifact_ref=lambda ref:find_artifact_registry_record_by_artifact_ref(ref,ledger_path=ledger),
                     get_response_lookup_record=lambda rid:{'response_payload':payload} if rid==payload['id'] else {},
                     resolve_saved_downloadable_artifact_path=lambda path:resolve_saved_artifact_path(path,allowed_roots={root}))
    target=root/'private-input.wav';shutil.copyfile(source,target)
    def verify(ref=None):
        return owner.verify_selected_audio_input([ref or a],source_path=source,temp_path=target)
    return SimpleNamespace(**locals())

def test_exact_authorized_prior_audio_reaches_whisper_boundary(binding):
    b=binding;e=b.verify();seen=[]
    ctx=SimpleNamespace(port=11504,task='transcribe',language=None,model_name='whisper',instance_id='stt',capability='speech_to_text')
    payload,status=_run_speech_to_text(ctx,InferArtifacts(temp_path=b.target,file_kind='audio',file_name='source.wav'),{
        'whisper_transcribe':lambda port,path,**kw:seen.append(hashlib.sha256(path.read_bytes()).hexdigest()) or {'text':'provider result'},
        'persist_transcript_text_locally':lambda *a,**kw:str(b.root/'transcript.txt')})
    assert status==200 and seen==[e['file_sha256']]
    assert e['source_response_id']=='source' and e['artifact_ref']==b.a['artifact_ref']

@pytest.mark.parametrize('mutation', ['missing_source','corrupt_copy','wrong_digest','wrong_ref','wrong_id','wrong_source','wrong_branch','source_removed','source_retargeted','missing_digest'])
def test_invalid_reference_never_reaches_provider(binding,mutation):
    b=binding;r=copy.deepcopy(b.a)
    if mutation=='missing_source':b.source.unlink()
    elif mutation=='corrupt_copy':b.target.write_bytes(b'corrupt')
    elif mutation=='wrong_digest':r['file_sha256']='0'*64
    elif mutation=='wrong_ref':r['artifact_ref']='artifact:foreign'
    elif mutation=='wrong_id':r['artifact_id']='foreign'
    elif mutation=='wrong_source':r['source_response_id']='foreign'
    elif mutation=='wrong_branch':r['branch_id']='other-producer'
    elif mutation=='source_removed':b.payload['artifacts']=[]
    elif mutation=='source_retargeted':b.payload['artifacts'][0]['path']=str(b.root/'other.wav')
    elif mutation=='missing_digest':b.payload.pop('tts_audio_integrity_evidence')
    with pytest.raises(ValueError):b.verify(r)

def test_same_filename_and_same_bytes_do_not_grant_identity(binding):
    b=binding;other=b.root/'other';other.mkdir();p=other/'source.wav';shutil.copyfile(b.source,p)
    r={**b.a,'artifact_ref':'artifact:foreign','path':str(p),'artifact_id':'audio_foreign'}
    with pytest.raises(ValueError):b.owner.verify_selected_audio_input([r],source_path=p,temp_path=b.target)
    with pytest.raises(ValueError):b.owner.verify_selected_audio_input([b.a],source_path=p,temp_path=b.target)

def test_current_successor_preserves_original_producer(binding):
    b=binding;b.payload['response_frame']={'frame_id':'source:frame-3','frame_sequence':3}
    assert b.verify()['source_frame_id']=='source:frame-3'
    b.payload['artifacts']=[]
    with pytest.raises(ValueError):b.verify()

def test_registered_alias_keeps_canonical_identity(binding):
    b=binding;b.registry['artifact_alias_refs'].append('legacy:audio-source')
    b.ledger.write_text(json.dumps(b.registry)+'\n')
    e=b.verify({**b.a,'artifact_ref':'legacy:audio-source'})
    assert e['artifact_ref']==b.a['artifact_ref'] and e['requested_artifact_ref']=='legacy:audio-source'

def test_symlink_replacement_cannot_retarget_identity(binding):
    b=binding;other=b.root/'other.wav';shutil.copyfile(b.source,other);b.source.unlink();b.source.symlink_to(other)
    with pytest.raises(ValueError):b.verify()

def test_copy_race_checks_actual_provider_bytes(binding):
    b=binding;b.target.write_bytes(b'other recording')
    with pytest.raises(ValueError,match='digest'):b.verify()

def test_no_audio_authorization_or_non_audio_reference(binding):
    b=binding
    for refs in ([],[{**b.a,'type':'text'}]):
        with pytest.raises(ValueError):b.owner.verify_selected_audio_input(refs,source_path=b.source,temp_path=b.target)

def test_same_response_direct_stt_does_not_require_retained_lookup(binding):
    b=binding;seen=[]
    ctx=SimpleNamespace(port=1,task='transcribe',language=None,model_name='whisper',instance_id='stt',capability='speech_to_text')
    _,status=_run_speech_to_text(ctx,InferArtifacts(temp_path=b.target,file_kind='audio'),{
        'whisper_transcribe':lambda port,path,**kw:seen.append(path) or {'text':'direct'},
        'persist_transcript_text_locally':lambda *a,**kw:'transcript'})
    assert status==200 and seen==[b.target]

@pytest.mark.parametrize('corrupt', [False, True])
@pytest.mark.parametrize('other_audio_count', [0, 4])
def test_responses_preparation_and_infer_api_use_verified_copy(binding,monkeypatch,corrupt,other_audio_count):
    import ollmo_webserver as web
    b=binding
    web.app.config['TESTING']=True
    monkeypatch.setattr(web,'ARTIFACT_REGISTRY_LEDGER',b.ledger)
    monkeypatch.setattr(web,'_get_response_lookup_record',b.owner.hooks['get_response_lookup_record'])
    monkeypatch.setattr(web,'_resolve_saved_downloadable_artifact_path',b.owner.hooks['resolve_saved_downloadable_artifact_path'])
    instance=dict(instance_id='whisper-fixture',port=11504,model='whisper',backend='mlx',capability='speech_to_text')
    monkeypatch.setattr(web,'_lookup_instance',lambda _:instance)
    monkeypatch.setattr(web,'record_instance_activity',lambda *a,**kw:({},{}))
    monkeypatch.setattr(web,'record_instance_success',lambda *a,**kw:({},{}))
    monkeypatch.setattr(web,'record_instance_failure',lambda *a,**kw:({},{}))
    monkeypatch.setattr(web,'_persist_transcript_text_locally',lambda *a,**kw:str(b.root/'transcript.txt'))
    calls=[]
    monkeypatch.setattr(web,'_whisper_transcribe',lambda port,path,**kw:calls.append(hashlib.sha256(path.read_bytes()).hexdigest()) or {'text':'provider transcript'})
    text=b.root/'source.txt';text.write_text('sibling transcript')
    request=dict(instance_id=instance['instance_id'],prompt='Refer to the previous audio and transcript.',reference_artifacts=[b.a,dict(type='text',path=str(text))])
    for i in range(other_audio_count):
        sibling=b.root/f'sibling-{i}.wav';shutil.copyfile(b.source,sibling)
        request['reference_artifacts'].insert(0,{**b.a,'artifact_ref':f'artifact:other-{i}','artifact_id':f'audio_other_{i}','path':str(sibling)})
    if other_audio_count:
        request['execution_contract']={'input_refs':[{'kind':'artifact','artifact_ref':b.a['artifact_ref']}]}
    with web.app.test_request_context('/api/responses',method='POST'):
        infer_payload,_,has_file,_=web._INFER_RUNTIME.build_responses_infer_execution_payload(request,route_info=None,instance=instance,instance_id=instance['instance_id'],backend='mlx',capability='speech_to_text',request_model_override=None)
    assert has_file and infer_payload['file_path']==str(b.source)
    assert len(infer_payload['reference_artifacts'])==2+other_audio_count
    if corrupt:b.source.write_bytes(b'changed since canonical source')
    response=web.app.test_client().post('/api/infer',json=infer_payload)
    assert response.status_code==(400 if corrupt else 200),response.get_json()
    assert calls==([] if corrupt else [b.digest])
    if not corrupt:
        assert response.get_json()['audio_reference_input_evidence']['artifact_ref']==b.a['artifact_ref']

def test_source_changed_after_copy_is_rejected(binding):
    b=binding;b.source.write_bytes(b'changed after private copy')
    with pytest.raises(ValueError,match='source changed'):b.verify()
