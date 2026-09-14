"""Real intake/consumer regression fixtures; never access production artifacts."""
import copy
import json
from pathlib import Path
import pytest
from ollmo_core.transports import resolve_saved_artifact_path
from ollmo_server.request_intake_runtime import RequestIntakeRuntimeOwner
from ollmo_server.response_semantics_runtime import ResponseSemanticsRuntimeOwner
from ollmo_services.artifact_contracts import sanitize_artifact_record

@pytest.fixture
def owners(tmp_path):
    intake = RequestIntakeRuntimeOwner(hooks={
        'resolve_saved_downloadable_artifact_path': lambda raw: resolve_saved_artifact_path(raw, allowed_roots={tmp_path.resolve()}),
        'sanitize_artifact_record': sanitize_artifact_record,
        'get_cached_generated_image_state': lambda path: None,
    })
    semantics = ResponseSemanticsRuntimeOwner(hooks={
        'sanitize_selected_reference_artifacts': intake._sanitize_selected_reference_artifacts,
        'build_instance_trait_summary': lambda instance: {},
    })
    return intake, semantics

def artifact(tmp_path, i, kind='audio'):
    p=tmp_path / f'{i}.{dict(audio="wav",text="txt",image="png")[kind]}'
    p.write_bytes(f'fixture-{i}'.encode())
    return dict(type=kind, artifact_id=f'{kind}_{i}', artifact_ref=f'artifact:{kind}_{i}',
                path=str(p), source_response_id='source-response', branch_id=f'producer-{i}', phase_id=f'phase-{i}')

@pytest.mark.parametrize('count', [2, 3, 9, 20])
def test_n_references_survive_every_normalization(owners,tmp_path,count):
    intake,_=owners
    refs=[artifact(tmp_path,i,['audio','text','image'][i%3]) for i in range(count)]
    original=copy.deepcopy(refs)
    kept=intake._extract_selected_reference_artifacts({'reference_artifacts':json.dumps(refs)})
    kept=intake._sanitize_selected_reference_artifacts(kept)
    assert [r['artifact_ref'] for r in kept] == [r['artifact_ref'] for r in refs]
    assert [r['branch_id'] for r in kept] == [r['branch_id'] for r in refs]
    assert refs==original

def test_audio_and_transcript_reaches_existing_consumer(owners,tmp_path):
    intake,semantics=owners
    refs=[artifact(tmp_path,1),artifact(tmp_path,2,'text')]
    kept=intake._extract_selected_reference_artifacts({'reference_artifacts':refs})
    chosen=semantics.select_matching_selected_reference_artifact(kept,'speech_to_text')
    assert chosen and chosen['artifact_ref']==refs[0]['artifact_ref']
    assert chosen['path']==refs[0]['path']

@pytest.mark.parametrize('kind,capability', [('audio','speech_to_text'),('image','image_generation'),('text','text_to_speech')])
def test_n_exact_consumer_handoffs_without_order_selection(owners,tmp_path,kind,capability):
    intake,semantics=owners
    refs=[artifact(tmp_path,i,kind) for i in range(7)]
    kept=intake._extract_selected_reference_artifacts({'reference_artifacts':refs})
    assert semantics.select_matching_selected_reference_artifact(kept,capability) is None
    handed=[]
    for ref in reversed(refs):
        selected=semantics.select_matching_selected_reference_artifact(kept,capability,artifact_ref=ref['artifact_ref'])
        assert selected['path']==ref['path']
        assert selected['source_response_id']==ref['source_response_id']
        assert selected['branch_id']==ref['branch_id']
        handed.append(selected['artifact_ref'])
    assert handed==[r['artifact_ref'] for r in reversed(refs)]
    assert semantics.select_matching_selected_reference_artifact(kept,capability,artifact_ref='artifact:unauthorized') is None

def test_normalized_relative_path_and_escape(owners,tmp_path,monkeypatch):
    intake,_=owners
    root=tmp_path.resolve();ref=artifact(root,1)
    monkeypatch.chdir(root)
    relative={**ref,'path':'./1.wav'}
    got=intake._sanitize_selected_reference_artifact(relative)
    assert got['path']==str(root/'1.wav') and got['artifact_ref']==ref['artifact_ref']
    outside=root.parent/'outside-reference.wav';outside.write_bytes(b'outside')
    try:
        assert intake._sanitize_selected_reference_artifact({**ref,'path':'../outside-reference.wav'}) is None
        assert intake._sanitize_selected_reference_artifact({**ref,'path':str(outside)}) is None
    finally:outside.unlink()

def test_multi_audio_selects_each_exact_identity_before_verification(owners,tmp_path):
    _,semantics=owners
    refs=[artifact(tmp_path,i) for i in range(4)]
    assert semantics.select_matching_selected_reference_artifact(refs,'speech_to_text') is None
    for ref in refs:
        got=semantics.select_matching_selected_reference_artifact(refs,'speech_to_text',artifact_ref=ref['artifact_ref'])
        assert got['path']==ref['path']

def test_repeated_normalization_preserves_named_predecessor_and_other_files(owners,tmp_path):
    intake,_=owners
    refs=[{**artifact(tmp_path,1,'text'),'origin':'current_predecessor_named_text_edit'},artifact(tmp_path,2,'image'),artifact(tmp_path,3)]
    kept=intake._sanitize_selected_reference_artifacts(refs)
    assert [r['artifact_ref'] for r in kept]==[r['artifact_ref'] for r in refs]

def test_all_file_references_reach_model_visible_context(owners,tmp_path):
    from ollmo_g.router import sanitize_ghost_messages, _merge_ghost_messages
    intake,_=owners
    intake.hooks['sanitize_ghost_messages']=sanitize_ghost_messages
    refs=[artifact(tmp_path,i,['audio','text','image'][i%3]) for i in range(9)]
    messages=intake._inject_selected_reference_message([],refs)
    merged=_merge_ghost_messages(messages)
    carried=[a['path'] for m in merged for a in m.get('artifacts',[])]
    assert carried==[r['path'] for r in refs]
    # Ghost has a path/type view; canonical runtime references remain separate.
    assert len(intake._sanitize_selected_reference_artifacts(refs))==len(refs)

def test_late_fill_n_selected_consumers_bind_their_own_reference(owners,tmp_path,monkeypatch):
    import ollmo_webserver as web
    intake,_=owners
    monkeypatch.setattr(web,'_resolve_saved_downloadable_artifact_path',intake.hooks['resolve_saved_downloadable_artifact_path'])
    refs=[artifact(tmp_path,i) for i in range(3)]
    request={'prompt':'Use the retained recordings.', 'reference_artifacts':refs}
    for ref in refs:
        prepared=web._LATE_FILL_RUNTIME.prepare_late_fill_request_payload(
            request,expected_capability='speech_to_text',assistant_message='',
            artifact_gap={'content_payload_source':'selected_reference_audio_artifact','content_payload':'Transcribe the bound recording.',
                          'execution_contract':{'input_refs':[{'kind':'artifact','artifact_ref':ref['artifact_ref']}]}})
        assert prepared['file_path']==ref['path']
        assert len(prepared['reference_artifacts'])==3

def test_history_merge_cannot_replace_current_collection_with_old_attachment(owners,tmp_path):
    from ollmo_g.router import sanitize_ghost_messages, _merge_ghost_messages
    intake,_=owners;intake.hooks['sanitize_ghost_messages']=sanitize_ghost_messages
    refs=[artifact(tmp_path,i) for i in range(4)]
    old=intake._inject_selected_reference_message([],refs[:1])
    current=intake._inject_selected_reference_message([],refs)
    merged=_merge_ghost_messages(old,current)
    assert any([a['path'] for a in m.get('artifacts',[])]==[r['path'] for r in refs] for m in merged)
