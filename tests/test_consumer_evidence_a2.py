"""Offline bounded A2 owner study; execute only through scripts/run_tests.py."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from tests.consumer_evidence_model import CRITERIA, FAULTS, case, controls, corpus, oracle, provider_html, requirements


def legacy_request(payload):
    """Replay the retained pre-policy admission format, without upgrading it.

    New captured-request behavior is exercised by test_content_requirement_completion.
    Original A2 source and observations remain in their immutable study snapshots.
    """
    from fruth_services.responses import restore_request_intent
    return restore_request_intent({**payload, 'intent_source': 'runtime_caller_capture_v1'})


def dump(path,value):
    with path.open('x') as f:
        json.dump(value,f,indent=2,ensure_ascii=False,default=str); f.write('\n'); f.flush(); os.fsync(f.fileno())


def reserve(label,c,category):
    job=Path(os.environ['FRUTH_COLD_PLAN']); ev=Path(os.environ['FRUTH_HYPOTHESIS_EVIDENCE_DIR'])
    storage=Path(json.loads((job/'run.json').read_text())['storage_root'])
    assert job.parent==storage
    policy_path=storage/'budget.json'
    policy=json.loads(policy_path.read_text()) if policy_path.exists() else {}
    if policy.get('deadline_utc'):
        assert datetime.now(timezone.utc)<datetime.fromisoformat(policy['deadline_utc'].replace('Z','+00:00'))
    assert all(p.parent==job or (p.parent/'completion.json').exists() for p in storage.glob('*/job.json'))
    prior=[json.loads(line) for p in storage.glob('*/01-regression/examples/a2-starts.jsonl') for line in p.read_text().splitlines()]
    assert len(prior)<min(128,policy.get('actual_scenario_starts',128))
    assert sum(r['job']==job.name for r in prior)<32
    if category in ('seeded','generated'):
        assert len({r['job'] for r in prior if r['category'] in ('seeded','generated')}|{job.name})<=min(2,policy.get('max_campaigns',2))
    usage=sum(max(p.stat().st_size,p.stat().st_blocks*512) for p in storage.rglob('*') if p.is_file() and not p.is_symlink())
    assert usage<min(4*1024**3,policy.get('stop_bytes',4*1024**3))
    start=dict(ordinal=len(prior)+1,job=job.name,label=label,case=c,category=category,storage_bytes_before=usage)
    with (ev/'a2-starts.jsonl').open('a') as f:
        f.write(json.dumps(start,sort_keys=True)+'\n'); f.flush(); os.fsync(f.fileno())
    root=ev/label; root.mkdir(); dump(root/'input.json',dict(start=start,requirements=requirements(c)))
    return root,start


def explicit_criteria(graph,consumer,css):
    """Controlled graph fixture: same caller demand, explicit reviewer criteria.

    Does not claim the ordinary intake automatically supplies these criteria.
    """
    criteria=list(CRITERIA if css else CRITERIA[:2])
    def visit(value):
        if isinstance(value,dict):
            if value.get('branch_id')==consumer['branch_id']:
                value['review_criteria']=list(dict.fromkeys(value.get('review_criteria',[])+criteria))
            for child in list(value.values()): visit(child)
        elif isinstance(value,list):
            for child in value: visit(child)
    visit(graph)


def verdict(check,mode):
    criteria=check.get('semantic_review_criteria') or check.get('review_criteria',[])
    criteria=[s for s in criteria if s!='runtime_text_exists_when_fulfilled']
    if mode=='missing_criterion': criteria=criteria[1:]
    refs=['foreign-unrelated-reference'] if mode=='wrong_refs' else [check.get('branch_semantic_review_source_branch_id') or 'current-runtime-evidence']
    return {'kind':'fruth.semantic_review_verdict','verdict':'failed' if mode=='negative' else 'passed',
            'overall_status':'blocked' if mode=='negative' else 'fulfilled',
            'whole_intent_fit':'Controlled offline verdict; no live reviewer was used.',
            'criterion_results':[{'criterion':s,'status':'failed' if mode=='negative' else 'passed','evidence_refs':refs} for s in criteria],
            'evidence_refs':refs,'defects':['controlled negative'] if mode=='negative' else [],
            'recommended_transition':'manual_review' if mode=='negative' else 'truthful_freeze'}


def run_case(label,c,category='control'):
    req=requirements(c) # Fixed independently before runtime imports/construction.
    root,start=reserve(label,c,category)
    report={'start':start,'requirements':req,'transitions':[],'interventions':[], 'status':'running'}
    def step(name):
        assert len(report['transitions'])<32
        report['transitions'].append(name)
    try:
        import fruth_webserver as web
        from fruth_inference.request_phase_graph import build_request_phase_graph
        from fruth_services.responses import build_canonical_response_artifacts
        from fruth_services.artifact_contracts import saved_file_consumption_artifact_issue
        from tests.fake_backends import FakeBackendHarness
        from tests.test_saved_file_consumer_path import owner_for,saved
        with FakeBackendHarness(root=root/'runtime') as harness:
            docs=harness.documents_dir; owner=owner_for(docs)
            request=legacy_request({'prompt':req['prompt'],'inference_route':True})
            graph=build_request_phase_graph(req['prompt'],request_payload=request,response_payload={'output_text':'Preparation complete.'})
            report['native_graph']=deepcopy(graph)
            consumer=next(b for b in graph['downstream_branches'] if b.get('artifact_request',{}).get('saved_file_dependency'))
            producer=next(b for b in graph['downstream_branches'] if b['branch_id']==consumer['artifact_request']['saved_file_dependency']['producer_branch_id'])
            if c['review']!='native':
                explicit_criteria(graph,consumer,c['css'])
                report['interventions'].append('Explicit semantic criteria added to matching graph records before execution; same caller requirements.')
            report['execution_graph']=deepcopy(graph); step('capture_and_admit_named_contract')
            payload={'id':'a2-'+label,'object':'response','capability':'chat','output_text':'Preparation complete.',
                     'runtime':{'request_phase_graph':graph},'late_fill':{'status':'pending','fill_results':[]}}
            source=json.dumps(req['data'],sort_keys=True,separators=(',',':'))
            owner.invoke_internal_api_json_route=lambda **kw:({'saved_text_path':saved(docs,'numbers','json',source)},200)
            pc=owner.build_execution_contract(producer,producer,capability='chat')
            pr=owner.execute_prepared_late_fill_branch({'response_id':payload['id'],'capability':'chat',
                 'branch_id':producer['branch_id'],'phase_id':producer['phase_id'],'execution_contract':pc,
                 'infer_payload':{'prompt':source},'effective_data':{}})['infer_result']
            pr=owner.attach_late_fill_result_artifact_identity({**producer,**pr},payload,pr,capability='chat')
            payload['late_fill']['fill_results'].append(pr); step('execute_save_and_bind_producer')
            report['source_snapshot']=deepcopy(pr['saved_file_output_snapshot'])
            dep=owner.branch_dependency_payload(consumer,current_payload=payload)
            assert not dep.get('materialization_blocked'),dep
            gap=owner.attach_execution_contract_to_gap(consumer,{**consumer,**dep},capability='chat'); step('read_and_prepare_actual_saved_input')
            calls=[]
            def consume(*,payload,upload):
                calls.append(deepcopy(payload))
                raw=payload['prompt'].split('--- SAVED FILE START ---\n',1)[1].split('\n--- SAVED FILE END ---',1)[0]
                data=json.loads(raw)
                body=provider_html(data,c)
                path=saved(docs,'result','html',body)
                if c['fault']=='separate_css': saved(docs,'extra','css','body { color: navy; }')
                return {'saved_text_path':path},200
            owner.invoke_internal_api_json_route=consume
            cr=owner.execute_prepared_late_fill_branch({'response_id':payload['id'],'capability':'chat',
                'branch_id':consumer['branch_id'],'phase_id':consumer['phase_id'],'execution_contract':gap['execution_contract'],
                'infer_payload':{'prompt':owner._text_artifact_materialization_instruction('UNTRUSTED ROOT',gap)},'effective_data':gap})['infer_result']
            cr=owner.attach_late_fill_result_artifact_identity({**consumer,**cr},payload,cr,capability='chat')
            payload['late_fill']['fill_results'].append(cr)
            report['submitted']=calls; report['original_result']=deepcopy(cr); step('execute_controlled_consumer_and_bind_output')
            assert len(calls)==1
            assert json.loads(calls[0]['prompt'].split('--- SAVED FILE START ---\n')[1].split('\n--- SAVED FILE END ---')[0])==req['data']
            assert (docs/'numbers.json').read_text()==source+'\n'
            if c['binding']=='read_identity': cr['saved_file_consumption_evidence']['read']['artifact_ref']='artifact:foreign'
            if c['binding']=='source_digest': (docs/'numbers.json').write_text(source+' \n')
            if c['binding']=='output_digest': (docs/'result.html').write_text((docs/'result.html').read_text()+'\n')
            report['interventions'].extend(['Controlled producer bytes; real writer and snapshot owner.',
                'Consumer parses only submitted saved-file packet; content mutation='+c['fault'],
                'Post-result binding mutation='+c['binding']])
            payload['late_fill'].update(status='completed',completed_branches=[{**b,'status':'fulfilled'} for b in graph['downstream_branches']])
            payload['artifacts']=build_canonical_response_artifacts(payload)
            report['oracle']=oracle(req,(docs/'result.html').read_text(),[p.name for p in docs.iterdir() if p.is_file()])
            report['native_consumption_issue']=saved_file_consumption_artifact_issue(consumer,payload,owner.resolve_saved_file_input_path)
            report['file_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in docs.iterdir() if p.is_file()}
            step('independent_content_and_native_binding_observations')
            with patch.object(web,'_resolve_saved_viewable_artifact_path',owner.resolve_saved_file_input_path):
                semantics=web._RESPONSE_SEMANTICS_RUNTIME
                closure=semantics.build_graph_closure_review(payload['output_text'],request_payload=request,artifact_payload=payload)
                report['closure_before_review']=deepcopy(closure); step('native_graph_closure_before_review')
                report['review_injections']=[]
                if c['review'] not in ('native','missing') and c['binding']=='none':
                    # At most two real owner review rounds; never manufacture a review target.
                    for round_index in range(2):
                        targets=[ch for ch in closure['checks'] if ch.get('check_kind') in ('branch_semantic_review','global_semantic_closure') and ch.get('status') in ('pending','blocked')]
                        if not targets: break
                        for check in targets:
                            v=verdict(check,c['review']); record=deepcopy(check)
                            record.update(status='fulfilled',result_text=json.dumps(v))
                            if c['review']=='wrong_binding':
                                record['semantic_review_evidence_binding']['sha256']='0'*64
                                if record.get('execution_contract',{}).get('semantic_review_evidence_binding'):
                                    record['execution_contract']['semantic_review_evidence_binding']['sha256']='0'*64
                            payload['late_fill']['completed_branches'].append(record)
                            report['review_injections'].append({'check':check,'verdict':v,'record':deepcopy(record)})
                        step('inject_controlled_completed_review_'+str(round_index))
                        closure=semantics.build_graph_closure_review(payload['output_text'],request_payload=request,artifact_payload=payload)
                        if c['review']!='passed' and c['review']!='wrong_refs': break
                report['closure_after_review']=deepcopy(closure)
                dump(root/'before-finalize.json',payload)
                payload,terminal_status=web._LATE_FILL_RUNTIME.finalize_terminal_materialization_contract(
                    payload,request_payload=request,route_payload=None,artifact_gap=None,
                    terminal_status='completed',accepted_fill_results=deepcopy(payload['late_fill']['fill_results']))
                report['terminal_status']=terminal_status
                step('native_terminal_materialization_and_closure_reconciliation')
                final=harness.freeze_manual_response(payload,request_payload=request)
                # Full state already lives in the native immutable ledger/CAS.
                # Avoid serializing its many overlapping projections again.
                report['final']={k:deepcopy(final.get(k)) for k in ('status','lifecycle_state','surface_state','outputs')}
                report['final']['closure']=deepcopy(final.get('runtime',{}).get('graph_closure_review'))
                report['final']['frame_id']=final.get('response_frame',{}).get('frame_id')
                step('native_finalize_and_persist')
                state=harness.response_state(payload['id']); assert state['ok'],state
                report['persisted']={'lifecycle_state':state['response_payload'].get('lifecycle_state'),
                    'closure':state['response_payload'].get('runtime',{}).get('graph_closure_review'),
                    'frame_id':state['response_frame']['frame_id']}
                report['oracle_after_terminal']=oracle(req,(docs/'result.html').read_text(),
                    [p.name for p in docs.iterdir() if p.is_file()])
                report['file_sha256_after_terminal']={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in docs.iterdir() if p.is_file()}
                step('canonical_readback')
            report['status']='observed'
            # Established technical evidence property, independent of content score.
            if c['binding']!='none':
                assert report['native_consumption_issue']
                assert report['closure_after_review']['status']!='fulfilled'
            else: assert not report['native_consumption_issue']
            if c['review'] in ('missing','negative','wrong_binding','missing_criterion') and c['binding']=='none':
                assert report['closure_after_review']['status']!='fulfilled',report['closure_after_review']
                assert report['persisted']['closure']['status']!='fulfilled'
                assert report['persisted']['lifecycle_state']!='completed'
            if c['fault']=='none' and c['binding']=='none' and c['review']=='native':
                assert report['oracle']['correct']
                assert report['closure_after_review']['status']=='fulfilled',report['closure_after_review']
            report['status']='passed_claim_specific_property'
    except BaseException as exc:
        report.update(status='failed',exception=repr(exc)); raise
    finally: dump(root/'observation.json',report)
    return report


def test_oracle_controls():
    req=requirements(case()); positive=provider_html(req['data'],case())
    for variant in range(3):
        assert oracle(req,provider_html(req['data'],case(variant=variant)),req['outputs'])['correct']
    for fault in FAULTS[1:]:
        c=case(fault=fault); outputs=req['outputs']+(['extra.css'] if fault=='separate_css' else [])
        assert not oracle(req,provider_html(req['data'],c),outputs)['correct'],fault
    assert oracle(requirements(case(css=False)),provider_html(req['data'],case(css=False)),req['outputs'])['correct']
    # Literal positives independent of provider renderer, order and markup.
    assert oracle(req,'<html><style>p {color:red}</style><body><p>sum = 18</p><p>values 7 / 11</p><p>version 1</p><p>subject alpha</p></body></html>',req['outputs'])['correct']
    assert oracle(req,'<html><body style="color:red"><p>Subject alpha</p><p>Version 1</p><p>Values 11 and 7</p><p>Sum 18</p></body></html>',req['outputs'])['correct']
    assert not oracle(req,'<html><body>Nothing requested is present.</body></html>',req['outputs'])['correct']


def test_pilot():
    for label,c in [('pilot-positive',case()),('pilot-wrong-sum',case(fault='wrong_sum')),
                    ('pilot-missing-review',case(review='missing')),('pilot-false-pass',case(review='passed',fault='wrong_sum'))]:
        run_case(label,c)


# Content-only variants are maintained by the stronger fixed-identity matrix.
# This keeps the ordinary module route at 31 actual starts, below the job cap.
MAINTAINED_CONTROLS=[x for x in controls() if x[1]['fault']=='none' or x[1]['review']!='native']


@pytest.mark.parametrize('label,c',MAINTAINED_CONTROLS,ids=[x[0] for x in MAINTAINED_CONTROLS])
def test_controls(label,c): run_case(label,c)


def test_one_sealed_campaign():
    ev=Path(os.environ['FRUTH_HYPOTHESIS_EVIDENCE_DIR'])
    value=corpus(); raw=json.dumps(value,sort_keys=True,separators=(',',':'))
    dump(ev/'corpus.json',value); dump(ev/'corpus-receipt.json',{'sha256':hashlib.sha256(raw.encode()).hexdigest(),'seed':value['seed'],'generated_examples':24,'runtime_shrinking':0})
    assert len(value['entries'])==32
    # Deserialize the sealed canonical value; generation is complete before any
    # owner construction. No mutation or shrinking can change the execution set.
    sealed=json.loads(raw)
    for entry in sealed['entries']:
        assert json.dumps(sealed,sort_keys=True,separators=(',',':'))==raw
        run_case(entry['label'],entry['case'],entry['origin'])


def test_fixed_identity_content_matrix():
    """Vary consumer bytes with ONE exact producer/source/response/consumer identity.

    Each consumer invocation reserves an actual study start. Native terminal
    Closure is reached; persisted completion is separately checked by controls.
    """
    variants=[('equivalent-'+str(i),case(variant=i)) for i in range(3)]+[(f,case(fault=f)) for f in FAULTS[1:]]
    first_root,first_start=reserve('fixed-'+variants[0][0],variants[0][1],'fixed-identity-control')
    import fruth_webserver as web
    from fruth_inference.request_phase_graph import build_request_phase_graph
    from fruth_services.responses import build_canonical_response_artifacts
    from fruth_services.artifact_contracts import saved_file_consumption_artifact_issue
    from tests.fake_backends import FakeBackendHarness
    from tests.test_saved_file_consumer_path import owner_for,saved
    req=requirements(case()); source=json.dumps(req['data'],sort_keys=True,separators=(',',':'))
    with FakeBackendHarness(root=first_root/'runtime') as harness:
        docs=harness.documents_dir; owner=owner_for(docs)
        request=legacy_request({'prompt':req['prompt'],'inference_route':True})
        graph=build_request_phase_graph(req['prompt'],request_payload=request,response_payload={'output_text':'Preparation complete.'})
        consumer=next(b for b in graph['downstream_branches'] if b.get('artifact_request',{}).get('saved_file_dependency'))
        producer=next(b for b in graph['downstream_branches'] if b['branch_id']==consumer['artifact_request']['saved_file_dependency']['producer_branch_id'])
        base={'id':'a2-fixed-source','object':'response','capability':'chat','output_text':'Preparation complete.',
              'runtime':{'request_phase_graph':graph},'late_fill':{'status':'pending','fill_results':[]}}
        pc=owner.build_execution_contract(producer,producer,capability='chat')
        owner.invoke_internal_api_json_route=lambda **kw:({'saved_text_path':saved(docs,'numbers','json',source)},200)
        pr=owner.execute_prepared_late_fill_branch({'response_id':base['id'],'capability':'chat','branch_id':producer['branch_id'],
            'phase_id':producer['phase_id'],'execution_contract':pc,'infer_payload':{'prompt':source},'effective_data':{}})['infer_result']
        pr=owner.attach_late_fill_result_artifact_identity({**producer,**pr},base,pr,capability='chat')
        base['late_fill']['fill_results'].append(pr)
        fixed=deepcopy(pr['saved_file_output_snapshot']); prior_source=(docs/'numbers.json').read_bytes()
        dump(first_root/'producer.json',dict(source_snapshot=fixed,accepted_producer=pr,request=request,consumer=consumer))
        for i,(label,c) in enumerate(variants):
            root,start=(first_root,first_start) if i==0 else reserve('fixed-'+label,c,'fixed-identity-control')
            report={'start':start,'source_snapshot':fixed,'requirements':req,'status':'running','transitions':[]}
            def step(name):
                assert len(report['transitions'])<32; report['transitions'].append(name)
            try:
                payload=deepcopy(base); step('select_same_exact_accepted_source')
                dep=owner.branch_dependency_payload(consumer,current_payload=payload)
                gap=owner.attach_execution_contract_to_gap(consumer,{**consumer,**dep},capability='chat')
                step('bind_same_source_to_same_consumer')
                submitted=[]
                def consume(*,payload,upload):
                    submitted.append(deepcopy(payload))
                    raw=payload['prompt'].split('--- SAVED FILE START ---\n')[1].split('\n--- SAVED FILE END ---')[0]
                    body=provider_html(json.loads(raw),c)
                    path=saved(docs,'result','html',body)
                    if c['fault']=='separate_css': saved(docs,'extra','css','body { color: navy; }')
                    return {'saved_text_path':path},200
                owner.invoke_internal_api_json_route=consume
                cr=owner.execute_prepared_late_fill_branch({'response_id':base['id'],'capability':'chat','branch_id':consumer['branch_id'],
                    'phase_id':consumer['phase_id'],'execution_contract':gap['execution_contract'],
                    'infer_payload':{'prompt':owner._text_artifact_materialization_instruction('UNTRUSTED ROOT',gap)},'effective_data':gap})['infer_result']
                cr=owner.attach_late_fill_result_artifact_identity({**consumer,**cr},payload,cr,capability='chat')
                payload['late_fill']['fill_results'].append(cr); step('execute_content_variant_with_consistent_digest')
                body=(docs/'result.html').read_text(); (root/'output.html').write_text(body)
                report.update(oracle=oracle(req,body,[p.name for p in docs.iterdir() if p.is_file()]),
                    consumer_result=cr,submitted=submitted,native_consumption_issue=saved_file_consumption_artifact_issue(consumer,payload,owner.resolve_saved_file_input_path))
                assert not report['native_consumption_issue']
                assert (docs/'numbers.json').read_bytes()==prior_source
                assert pr['saved_file_output_snapshot']==fixed
                assert cr['saved_file_consumption_evidence']['read']['artifact_ref']==fixed['artifact_ref']
                payload['late_fill'].update(status='completed',completed_branches=[{**b,'status':'fulfilled'} for b in graph['downstream_branches']])
                payload['artifacts']=build_canonical_response_artifacts(payload)
                with patch.object(web,'_resolve_saved_viewable_artifact_path',owner.resolve_saved_file_input_path):
                    report['closure']=web._RESPONSE_SEMANTICS_RUNTIME.build_graph_closure_review(payload['output_text'],request_payload=request,artifact_payload=payload)
                step('native_graph_closure')
                assert report['oracle']['correct']==(c['fault']=='none')
                # Characterization, not a desired semantic acceptance promise.
                report['status']='observed_fixed_identity'
            except BaseException as exc:
                report.update(status='failed',exception=repr(exc)); raise
            finally: dump(root/'observation.json',report)


@pytest.mark.parametrize('fault',['none','wrong_sum','omit_css'])
def test_complete_worker_confirmation(fault,monkeypatch):
    c=case(fault=fault); req=requirements(c)
    root,start=reserve('worker-'+fault,c,'full-worker-control')
    report={'start':start,'requirements':req,'status':'running','transitions':[]}
    def step(name):
        assert len(report['transitions'])<32; report['transitions'].append(name)
    try:
        import fruth_webserver as web
        import fruth_server.late_fill_runtime as late_module
        from fruth_inference.request_phase_graph import build_request_phase_graph
        from fruth_services.artifact_contracts import saved_file_consumption_artifact_issue
        from tests.fake_backends import FakeBackendHarness
        from tests.test_saved_file_consumer_path import owner_for,saved
        with FakeBackendHarness(root=root/'runtime') as harness,monkeypatch.context() as scoped:
            docs=harness.documents_dir; resolver=owner_for(docs).resolve_saved_file_input_path
            harness.instances['chat']['runtime_status'].update(process_alive=True,port_listening=True)
            runtime=web._LATE_FILL_RUNTIME
            scoped.setattr(runtime,'resolve_saved_file_input_path',resolver)
            scoped.setattr(web,'_resolve_saved_viewable_artifact_path',resolver)
            scoped.setattr(web,'ARTIFACT_OUTPUTS_DOCUMENTS_DIR',docs)
            scoped.setattr(late_module,'ARTIFACT_OUTPUTS_DOCUMENTS_DIR',docs)
            request=legacy_request({'prompt':req['prompt'],'inference_route':True})
            graph=build_request_phase_graph(req['prompt'],request_payload=request,response_payload={'output_text':'Preparation complete.'})
            consumer=next(b for b in graph['downstream_branches'] if b.get('artifact_request',{}).get('saved_file_dependency'))
            payload={'id':'a2-worker-'+fault,'object':'response','capability':'chat','output_text':'Preparation complete.',
                     'runtime':{'request_phase_graph':graph},'late_fill':{'status':'pending','pending_branches':graph['downstream_branches'],'pending_capabilities':['chat']}}
            calls=[]; step('capture_and_build_native_graph')
            def backend(*,payload,upload):
                artifact_request=payload.get('artifact_request') or payload['execution_contract']['artifact_request']
                extension=artifact_request['extension']; calls.append(deepcopy(payload))
                if extension=='json': content=json.dumps(req['data'],sort_keys=True,separators=(',',':'))
                else:
                    assert extension=='html'
                    raw=payload['prompt'].split('--- SAVED FILE START ---\n')[1].split('\n--- SAVED FILE END ---')[0]
                    content=provider_html(json.loads(raw),c)
                path=saved(docs,artifact_request['source_name'],extension,content)
                return {'saved_text_path':path,'content':content,'saved_text_artifacts':[{'path':path,'text_artifact_request':artifact_request}]},200
            scoped.setattr(web,'_invoke_internal_api_json_route',backend)
            scoped.setitem(web.app.config,'TESTING',True)
            with web.app.app_context():
                runtime.complete_response_late_fill(response_payload=payload,request_payload=request,assistant_message=payload['output_text'],
                    artifact_gap={'pending_branches':graph['downstream_branches'],'pending_capabilities':['chat'],'expected_capability':'chat'},source_route_payload=None)
            step('complete_actual_late_fill_worker')
            final=runtime.get_response_lookup_record(payload['id'])['response_payload']
            report['calls']=calls; report['closure']=final.get('runtime',{}).get('graph_closure_review')
            report['lifecycle_state']=final.get('lifecycle_state')
            report['native_consumption_issue']=saved_file_consumption_artifact_issue(consumer,final,resolver)
            report['accepted_results']=final['late_fill']['fill_results']
            report['oracle']=oracle(req,(docs/'result.html').read_text(),[p.name for p in docs.iterdir() if p.is_file()])
            assert len(calls)==2 and not report['native_consumption_issue']
            assert report['oracle']['correct']==(fault=='none')
            scoped.setitem(web.app.config,'TESTING',False)
            harness.freeze_manual_response(final,request_payload=request)
            state=harness.response_state(payload['id']); assert state['ok']
            report['persisted']={'frame_id':state['response_frame']['frame_id'],'closure':state['response_payload']['runtime']['graph_closure_review'],
                                 'lifecycle_state':state['response_payload']['lifecycle_state']}
            step('native_freeze_and_canonical_readback')
            assert not web._RESPONSE_LATE_FILL_IN_FLIGHT
            report['status']='observed_full_worker'
    except BaseException as exc:
        report.update(status='failed',exception=repr(exc)); raise
    finally: dump(root/'observation.json',report)
