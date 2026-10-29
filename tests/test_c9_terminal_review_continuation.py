"""Native C9 regression: real POST/scheduler/acceptance, finite HTTP provider.
No authority, promotion, accepted evidence or continuation context is injected.
"""
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import hashlib
import gzip
import json
from pathlib import Path
import threading
import time
from unittest.mock import patch
import pytest
import fruth_webserver as web
from tests.consumer_evidence_model import case, requirements, provider_html
from tests.test_consumer_evidence_a2 import reserve, dump
from tests.test_content_requirement_completion import summary, assert_compact_readback
from tests.test_instruction_admission_contract import real_owners
from fruth_services.responses import restore_request_intent

REAL_WEB_SCHEDULE = web._schedule_response_late_fill

def sha(data): return hashlib.sha256(data).hexdigest()


def roles(value):
    return sorted({r['role'] for c in value['runtime']['graph_closure_review']['checks']
        if c.get('content_coverage_status') == 'accepted_review' for r in c['content_requirements']})

def run(mode):
    c=case(); req=requirements(c)
    root,start=reserve('c9-'+mode,c,'control')
    response_id='b407-during_cancel_consumer'
    request={'response_id':response_id,'prompt':req['prompt'],'inference_route':True}
    report={'mode':mode,'start':start,'request':request,'events':[],'providers':[],
            'schedules':[],'workers':[],'new_contexts':[],'handoffs':[],'projections':[],
            'controls':[],'dispatch':[],'errors':[],'provider_errors':[],'explicit_activations':0,'continuation_checks':[],
            'review_context_checks':[]}
    contexts=[]; workers=[]; snapshots={}; review_probes=[]; control_prefix=None; before_control=None
    runtime=web._LATE_FILL_RUNTIME; rr=web._RESPONSES_REQUEST_RUNTIME
    schedule=runtime.schedule_response_late_fill; complete=runtime.complete_response_late_fill
    make_context=runtime._new_pending_continuation; prepare=runtime._prepare_pending_control_handoff
    require=runtime._require_pending_continuation
    bound_review=runtime._verified_pending_review_instruction
    project=rr._attach_repair_gap_to_request_phase_graph
    execute=runtime.execute_prepared_late_fill_branch
    claim=runtime.claim_response_late_fill; release=runtime.release_response_late_fill
    log=runtime.log_unified_event
    seq_lock=threading.Lock()
    def event(kind,**data):
        with seq_lock: report['events'].append({'sequence':len(report['events'])+1,'kind':kind,
            'thread':threading.current_thread().name,**deepcopy(data)})
    def current(): return deepcopy(runtime.get_response_lookup_record(response_id)['response_payload'])
    def wait_chain():
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            for worker in list(workers):worker.join(.1)
            if workers and all(not w.is_alive() for w in workers) and not web._RESPONSE_LATE_FILL_IN_FLIGHT:break
            time.sleep(.01)
        assert workers and all(not w.is_alive() for w in workers),'180s native chain observation bound'
        assert not web._RESPONSE_LATE_FILL_IN_FLIGHT
        assert not report['errors'],report['errors']
        assert not report['provider_errors'],report['provider_errors']
        assert all(r.get('returned') for r in report['providers'] if r['kind'].startswith('review:'))
    def observe_worker(**kwargs):
        workers.append(threading.current_thread())
        contexts.append(kwargs.get('pending_continuation'))
        row={'index':len(report['workers']),'context':kwargs.get('pending_continuation') is not None,
             'branch_ids':[b.get('branch_id') for b in kwargs['artifact_gap'].get('pending_branches',[])]}
        report['workers'].append(row);event('worker_entry',**row)
        try:
            with web.app.app_context():return complete(**kwargs)
        except BaseException as e:report['errors'].append(repr(e));raise
        finally:row['returned']=True;event('worker_exit',index=row['index'])
    def observe_schedule(**kwargs):
        row={'testing':web.app.config.get('TESTING'),'context':kwargs.get('pending_continuation') is not None,
             'branch_ids':[b.get('branch_id') for b in kwargs['artifact_gap'].get('pending_branches',[])],
             'execution':deepcopy(kwargs['response_payload'].get('late_fill',{}).get('terminal_closure_repair_reopen'))}
        report['schedules'].append(row);event('schedule',**row)
        row['returned']=schedule(**kwargs);return row['returned']
    def observe_new(payload,req_payload):
        row={'input':deepcopy(payload),'request':deepcopy(req_payload)}
        report['new_contexts'].append(row)
        try:
            result=make_context(payload,req_payload);row['returned_context']=result is not None
            event('new_context',returned_context=result is not None)
            return result
        except BaseException as e:row['error']=repr(e);raise
    def observe_prepare(ctx,**kwargs):
        row={'context':ctx is not None,'input':current()};report['handoffs'].append(row)
        result=prepare(ctx,**kwargs);row['returned']=result is not None
        event('pending_control_handoff',context=ctx is not None,returned=result is not None)
        return result
    def observe_require(ctx,current,**kwargs):
        try:return require(ctx,current,**kwargs)
        except BaseException as exc:
            report['continuation_checks'].append({'error':repr(exc),
                'admission_request':deepcopy(ctx.chain.admission.get('response_frame',{}).get('request')),
                'current_request':deepcopy(current.get('response_frame',{}).get('request')),
                'canonical_current_request':deepcopy(runtime.load_latest_response_state(response_id).get('response_frame',{}).get('request'))})
            raise
    def observe_bound_review(gap,current,request):
        result=bound_review(gap,current,request)
        row={'branch_id':gap.get('branch_id'),'verified':bool(result),'gap':deepcopy(gap)}
        report['review_context_checks'].append(row)
        if result and mode == 'automatic':
            review_probes.append((row, deepcopy((gap,current,request))))
        if not result and runtime._content_review_binding(gap):
            fresh=runtime.build_graph_closure_review(str(current.get('output_text') or ''),
                request_payload=request,artifact_payload=current)
            row['fresh_bindings']=[deepcopy(c.get('branch_semantic_review_evidence_binding'))
                for c in fresh.get('checks',[]) if c.get('branch_semantic_review_evidence_binding')]
        return result
    def observe_project(payload,gap):
        row={'before_graph':deepcopy(payload.get('runtime',{}).get('request_phase_graph')),'gap':deepcopy(gap)}
        report['projections'].append(row)
        result=project(payload,gap);row['after_graph']=deepcopy(result.get('runtime',{}).get('request_phase_graph'))
        event('repair_projection');return result
    def observe_execute(plan):
        row={'plan':deepcopy(plan)};report['dispatch'].append(row);event('dispatch',branch_id=plan.get('branch_id'))
        result=execute(plan);row['returned']=deepcopy(result);event('dispatch_return',branch_id=plan.get('branch_id'));return result
    def observe_claim(rid):
        result=claim(rid);event('claim',response_id=rid,result=result);return result
    def observe_release(rid):
        event('release',response_id=rid);return release(rid)
    def observe_log(**kwargs):event('runtime_log',value=kwargs);return log(**kwargs)
    def reply_body(call,index):
        nonlocal control_prefix,before_control
        text='\n'.join(str(m.get('content') or '') for m in call['request'].get('messages',[]))
        if 'Branch runtime evidence:\n' not in text:
            if index==1:kind='preparation';result='Preparation complete.'
            elif '--- SAVED FILE START ---\n' in text:
                raw=text.split('--- SAVED FILE START ---\n',1)[1].split('\n--- SAVED FILE END ---',1)[0]
                assert json.loads(raw)==req['data'];kind='html';result='```html\n'+provider_html(json.loads(raw),c)+'\n```'
            else:kind='json';result='```json\n'+json.dumps(req['data'],sort_keys=True,separators=(',',':'))+'\n```'
            report['providers'].append({'kind':kind,'prompt':text,'reply':result});event('provider',kind_name=kind);return result
        packet=json.JSONDecoder().raw_decode(text.split('Branch runtime evidence:\n',1)[1])[0]
        coverage=packet['content_coverage'];role=coverage['requirements'][0]['role']
        assert coverage['complete'];assert packet['artifact_refs']
        for ref in packet['artifact_refs']:
            assert ref['content_excerpt_mode']=='full'
            assert ref['content_excerpt'].encode()==Path(ref['path']).read_bytes()
            assert ref['current_file_sha256']==sha(Path(ref['path']).read_bytes())
        if role=='consumer':assert json.loads(coverage['source']['content_excerpt'])==req['data']
        ref=packet['artifact_refs'][0]['ref'];assert ref in packet['evidence_reference_catalog']['allowed_refs']
        verdict={'kind':'fruth.semantic_review_verdict','verdict':'passed','overall_status':'fulfilled',
          'whole_intent_fit':'Controlled offline passing review.',
          'criterion_results':[{'criterion':v,'status':'passed','evidence_refs':[ref]} for v in packet['branch_check']['semantic_review_criteria']],
          'evidence_refs':[ref],'defects':[],'recommended_transition':'truthful_freeze'}
        row={'kind':'review:'+role,'prompt':text,'packet':packet,'verdict':verdict};report['providers'].append(row)
        event('provider_review_entry',role=role)
        target_role='producer' if mode=='accepted-sibling' else 'consumer'
        if mode!='positive' and role==target_role:
            assert not report['controls']
            before_control=current()
            canonical_request_before=deepcopy(harness.response_state(response_id)['response_frame']['request'])
            target=next(b for b in before_control['late_fill']['pending_branches']+before_control['late_fill'].get('active_branches',[])
                if runtime._content_review_binding(b).get('source_branch_id')==packet['source_branch_id'])
            # Same exact review and provider-before-return cut as retained W3.
            for p in (harness.response_frames_dir/'snapshots').rglob('*'):
                if p.is_file():snapshots[str(p)]=sha(p.read_bytes())
            ledger=harness.response_frames_dir/'responses.jsonl';prefix=ledger.read_bytes()
            artifacts={str(p):sha(p.read_bytes()) for p in harness.documents_dir.iterdir() if p.is_file()}
            event('control_begin',branch_id=target['branch_id'])
            result=harness.client.post(f'/api/responses/{response_id}/late_fill/control',json={
                'action':'cancel','scope':'branch','branch_id':target['branch_id'],
                'reason':'Bounded source-contract exact-target control.'})
            assert result.status_code==200,result.get_json()
            controlled=current();control_prefix=ledger.read_bytes()
            assert control_prefix.startswith(prefix)
            assert controlled['late_fill']['fill_results']==before_control['late_fill']['fill_results']
            report['controls'].append({'target':deepcopy(target),'before':before_control,'after':controlled,
                'reply':result.get_json(),'artifact_sha256':artifacts,
                'canonical_request_before':canonical_request_before,
                'live_request_equal':controlled['response_frame']['request']==before_control['response_frame']['request']})
            assert harness.response_state(response_id)['response_frame']['request']==canonical_request_before
            event('control_committed',frame=controlled['response_frame']['frame_id'])
        row['returned']=True
        event('provider_review_return',role=role)
        return json.dumps(verdict)
    def reply(call,index):
        try:return reply_body(call,index)
        except BaseException as exc:
            report['provider_errors'].append(repr(exc));raise
    try:
        with real_owners(root/'runtime',reply) as harness,ExitStack() as stack:
            for obj,name,fn in [(web,'_schedule_response_late_fill',REAL_WEB_SCHEDULE),
                (runtime,'schedule_response_late_fill',observe_schedule),(runtime,'complete_response_late_fill',observe_worker),
                (runtime,'_new_pending_continuation',observe_new),(runtime,'_prepare_pending_control_handoff',observe_prepare),
                (rr,'_attach_repair_gap_to_request_phase_graph',observe_project),
                (runtime,'_require_pending_continuation',observe_require),
                (runtime,'_verified_pending_review_instruction',observe_bound_review),
                (runtime,'execute_prepared_late_fill_branch',observe_execute),
                (runtime,'claim_response_late_fill',observe_claim),(runtime,'release_response_late_fill',observe_release),
                (runtime,'log_unified_event',observe_log)]:stack.enter_context(patch.object(obj,name,fn))
            result,status=harness.post_response(request);report['post']={'status':status,'payload':deepcopy(result)}
            assert status==200,result;wait_chain();assert not harness.scheduled
            for row, probe in review_probes:
                from tests.test_c9_review_context_boundaries import check_native_review_context
                row['boundary_controls'] = check_native_review_context(runtime,*probe,verify=bound_review)
            automatic=current();report['automatic']=automatic
            ledger=harness.response_frames_dir/'responses.jsonl'
            if mode!='positive':
                assert ledger.read_bytes().startswith(control_prefix),'winning control history changed'
                assert all(r in automatic['late_fill']['fill_results'] for r in before_control['late_fill']['fill_results'])
                assert roles(automatic)==(['consumer'] if mode=='accepted-sibling' else ['producer'])
                assert summary(automatic)['unresolved_content_requirement_count']==1
                assert automatic['lifecycle_state']!='completed'
                assert any(x['kind']=='runtime_log' and x['value'].get('status')=='stale_result_rejected' for x in report['events'])
                assert report['handoffs'] and report['handoffs'][-1]['context']
                assert report['handoffs'][-1]['returned'] is (mode in {'automatic','explicit'})
                target_id=report['controls'][0]['target']['branch_id']
                assert not any(r.get('branch_id')==target_id for r in automatic['late_fill']['fill_results'])
                assert any(b['branch_id']==target_id and b['status']=='cancelled' for b in automatic['late_fill']['cancelled_branches'])
                for path,digest in report['controls'][0]['artifact_sha256'].items():assert sha(Path(path).read_bytes())==digest
            if mode=='explicit':
                # Explicit activation after automatic completion must be inert.
                restored=restore_request_intent(automatic['response_frame']['request'])
                handoff=runtime._terminal_closure_repair_handoff(automatic,request_payload=restored,
                    assistant_message=automatic.get('output_text',''),source_route_payload=None)
                assert handoff is None
                report['explicit_activations']+=1;event('explicit_activation_inert')
            final=current();report['final']=final
            expected={'positive':['consumer','producer'],'explicit':['producer'],'automatic':['producer'],'accepted-sibling':['consumer']}[mode]
            assert roles(final)==expected
            assert summary(final)['unresolved_content_requirement_count']==2-len(expected)
            assert (final['lifecycle_state']=='completed')==(mode=='positive')
            assert len(report['workers'])==(3 if mode in {'automatic','explicit'} else 2)
            assert all(not r['testing'] for r in report['schedules'])
            assert [r['kind'] for r in report['providers']]==['preparation','json','html','review:consumer']+(
                ['review:producer'] if mode in {'automatic','positive','explicit','accepted-sibling'} else [])
            assert contexts[1] is not None, 'review scheduler must create its context'
            if mode in {'automatic','explicit'}:
                assert contexts[2] is not None and contexts[2].chain is contexts[1].chain
                assert contexts[2].scope == frozenset(report['workers'][2]['branch_ids'])
                assert len(contexts[2].scope)==1 and contexts[2].chain.attempts==1
                assert sum(r['context'] for r in report['schedules'])==1
            for projection in report['projections']:
                graph=projection['after_graph']
                for branch in projection['gap']['pending_branches']:
                    matches=[o for o in graph['output_obligations'] if o['obligation_id']==branch['obligation_id']]
                    assert len(matches)==1
                    obligation=matches[0];contract=branch['repair_contract']
                    assert obligation['contract_state']==branch['contract_state']==contract['status']=='promoted'
                    assert obligation['promotion_source']==branch['promotion_source']==contract['promotion_source']
                    assert obligation['repair_contract_id']==contract['contract_id']
                    review=next(v for v in graph['graph_repair_reviews'] if v['review_id']==obligation['graph_repair_review_id'])
                    assert review['status']=='accepted' and review['proposal_id']==obligation['graph_repair_proposal_id']
                    assert any(v['branch_id']==branch['branch_id'] and v['phase_id']==branch['phase_id']
                        and v['obligation_id']==branch['obligation_id'] for v in review['accepted_patch']['add_phases'])
            for dispatch in report['dispatch']:
                p=dispatch['plan'];assert p['infer_payload']['prompt']!=req['prompt']
                admitted=[b for row in report['new_contexts']
                    for b in row['input'].get('late_fill',{}).get('pending_branches',[])
                    if b.get('branch_id')==p['branch_id'] and b.get('branch_semantic_review')]
                if admitted:
                    assert len(admitted)==1
                    assert p['infer_payload']['prompt']==admitted[0]['content_payload']
                    provider=next(r for r in report['providers'] if r['kind'].startswith('review:')
                        and r['packet']['source_branch_id']==admitted[0]['branch_semantic_review_source_branch_id'])
                    assert p['infer_payload']['prompt'] in provider['prompt'] and provider['returned']
            for check in final['runtime']['graph_closure_review']['checks']:
                if check.get('content_coverage_status')!='accepted_review':continue
                binding=check['branch_semantic_review_evidence_binding']
                accepted=next(r for r in final['late_fill']['fill_results'] if r.get('branch_id')==binding['branch_id'])
                dispatch=next(r['plan'] for r in report['dispatch'] if r['plan']['branch_id']==binding['branch_id'])
                provider=next(r for r in report['providers'] if r['kind'].startswith('review:')
                    and r['packet']['source_branch_id']==check['branch_id'])
                assert sha(dispatch['infer_payload']['prompt'].encode())==binding['instruction_sha256']
                generation=sha((binding['policy']+'\0'+binding['logical_review_id']+'\0'+dispatch['infer_payload']['prompt']).encode())
                assert generation==binding['sha256'] and binding['generation_id'].endswith('-'+generation)
                assert binding['branch_id']=='branch-'+binding['generation_id']
                assert binding['obligation_id']=='obligation-'+binding['generation_id']
                assert binding['phase_id']=='phase-'+binding['generation_id']
                assert accepted['semantic_review_evidence_binding']==binding
                assert json.loads(accepted['result_text'])==provider['verdict']
                assert check['semantic_review_freeze_acceptance']['accepted'] is True
                assert check['semantic_review_freeze_acceptance']['evidence_reference_policy']=='packet_exact_v1'
            prefix=ledger.read_bytes();harness.clear_response_lookup();recovered=harness.response_state(response_id)
            assert recovered['ok'];report['recovery']=deepcopy(recovered)
            assert recovered['response_payload']['late_fill']['fill_results']==final['late_fill']['fill_results']
            assert summary(recovered['response_payload'])==summary(final)
            report['final_live_request_equal_canonical']=recovered['response_frame']['request']==final['response_frame']['request']
            if report['controls']:
                report['recovered_request_exact_equal']=recovered['response_frame']['request']==report['controls'][0]['canonical_request_before']
                assert recovered['response_frame']['request']==report['controls'][0]['canonical_request_before']
            assert recovered['response_frame']['request']['prompt']==req['prompt']
            assert recovered['response_frame']['request']['content_review_reference_policy']=='packet_exact_v1'
            assert_compact_readback(harness,response_id,summary(final));assert ledger.read_bytes()==prefix
            assert all(sha(Path(p).read_bytes())==digest for p,digest in snapshots.items())
            assert not web._RESPONSES_RUNTIME._mutation_locks
            report['preserved']={'passive_unchanged':True,'frozen_snapshots':len(snapshots),
                'no_duplicate_dispatch':len({p['plan']['branch_id'] for p in report['dispatch']})==len(report['dispatch']),
                'accepted_roles':expected,'remaining_content_duties':2-len(expected)}
            assert report['preserved']['no_duplicate_dispatch'];report['status']='passed'
    except BaseException as e:report['status']='failed';report['error']=repr(e);raise
    finally:
        for w in workers:w.join(5)
        report['workers_settled']=all(not w.is_alive() for w in workers)
        with gzip.open(root/'trace.json.gz','xt',encoding='utf-8',compresslevel=6) as stream:
            json.dump(report,stream,indent=2,default=str)

@pytest.mark.parametrize('mode',['automatic','positive','explicit','accepted-sibling'])
def test_native_terminal_review_continuation(mode): run(mode)
