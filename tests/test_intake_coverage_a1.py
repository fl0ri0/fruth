"""Bounded A1 owner study. Use the guarded run_tests.py route only."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest


def dump(path, value):
    with path.open('x') as out:
        json.dump(value, out, indent=2, ensure_ascii=False, default=str)
        out.write('\n')
        out.flush()
        os.fsync(out.fileno())


def reserve(label, case, category):
    job = Path(os.environ['FRUTH_COLD_PLAN'])
    evidence = Path(os.environ['FRUTH_HYPOTHESIS_EVIDENCE_DIR'])
    storage = Path(json.loads((job/'run.json').read_text())['storage_root'])
    policy = json.loads((storage/'budget.json').read_text()) if (storage/'budget.json').exists() else {}
    if policy.get('deadline_utc'):
        assert datetime.now(timezone.utc) < datetime.fromisoformat(policy['deadline_utc'].replace('Z', '+00:00'))
    assert all(p.parent == job or (p.parent/'completion.json').exists() for p in storage.glob('*/job.json'))
    prior = [json.loads(line) for p in storage.glob('*/01-regression/examples/intake-starts.jsonl') for line in p.read_text().splitlines()]
    assert len(prior) < 128
    assert sum(p['job'] == job.name for p in prior) < 32
    if category == 'generated':
        assert len({p['job'] for p in prior if p['category'] == 'generated'} | {job.name}) <= 2
    usage = sum(max(p.stat().st_size, p.stat().st_blocks*512) for p in storage.rglob('*') if p.is_file() and not p.is_symlink())
    assert usage < min(policy.get('stop_bytes',4*1024**3),4*1024**3)
    start = {'ordinal':len(prior)+1, 'job':job.name, 'label':label, 'category':category, 'case':case, 'storage_bytes_before':usage}
    with (evidence/'intake-starts.jsonl').open('a') as f:
        f.write(json.dumps(start,sort_keys=True)+'\n'); f.flush(); os.fsync(f.fileno())
    root = evidence/label
    root.mkdir()
    dump(root/'input.json', start)
    return root, start


def observe(label, case, category='control'):
    root, start = reserve(label, case, category)
    report = {'start':start, 'transitions':[], 'classification':4, 'preparations':[]}
    def step(name):
        assert len(report['transitions']) < 32
        report['transitions'].append(name)
    try:
        # The established runner installs production/network/process guards before imports.
        import fruth_webserver as web
        from fruth_services.responses import capture_request_intent, request_intent_payload
        from fruth_inference.request_phase_graph import build_request_phase_graph, next_executable_downstream_branches, _explicit_downstream_branches
        from tests.fake_backends import FakeBackendHarness
        from tests.test_saved_file_consumer_path import owner_for, saved
        prompt = case['prompt']
        request = capture_request_intent({'prompt':prompt, 'inference_route':True})
        if case.get('prepared_prompt'):
            request['prompt'] = case['prepared_prompt']
        report['caller_intent'] = request_intent_payload(request)
        report['effective_prompt'] = request['prompt']
        step('capture_caller_before_preparation')
        response = deepcopy(case.get('planner', {'output_text':'Preparation complete.'}))
        report['normalized_planner_candidates'] = _explicit_downstream_branches(request_intent_payload(request),{},response)
        graph = build_request_phase_graph(request['prompt'], request_payload=request, response_payload=response)
        report['graph'] = deepcopy(graph)
        step('interpret_build_admit_graph')
        payload = {'id':'intake-'+label, 'output_text':response.get('output_text',''),
                   'runtime':{'request_phase_graph':graph}, 'late_fill':{'status':'pending','fill_results':[]}}
        with FakeBackendHarness(root=root/'runtime') as harness:
            for inst in harness.instances.values():
                inst['runtime_status'].update(process_alive=True,port_listening=True)
            runtime = web._LATE_FILL_RUNTIME
            owner = owner_for(harness.documents_dir)
            with patch.object(runtime, 'resolve_saved_file_input_path', owner.resolve_saved_file_input_path):
                def ready():
                    return [b['branch_id'] for b in next_executable_downstream_branches(graph, completed_branches=payload['late_fill'].get('completed_branches',[]))]
                report['ready_before'] = ready()
                step('native_ready_selection_before_saved_source')
                branches = graph.get('downstream_branches',[])
                for branch in branches:
                    item = {'branch_id':branch['branch_id'], 'capability':branch.get('capability'), 'ready':branch['branch_id'] in report['ready_before']}
                    report['preparations'].append(item)
                    try:
                        spec = runtime.build_late_fill_materialization_branch_spec(branch=branch, artifact_gap={}, current_payload=payload,
                            request_payload=request,assistant_message=response.get('output_text',''),source_route_payload=None,failed_instance_id=None)
                        item['spec'] = deepcopy(spec)
                        step('spec:'+branch['branch_id'])
                        if spec:
                            plan = runtime.prepare_late_fill_branch_plan(**spec['prepare_args'])
                            item['plan'] = deepcopy(plan)
                            step('prepare:'+branch['branch_id'])
                    except (RuntimeError, ValueError) as exc:
                        item['blocked'] = str(exc)
                        step('preparation_block:'+branch['branch_id'])
                # Explicit fixture intervention: actual writer and snapshot owner,
                # controlled producer output. This does not claim generation accuracy.
                producers = [b for b in branches if b.get('artifact_request',{}).get('source_name')=='numbers' and b.get('artifact_request',{}).get('extension')=='json']
                if len(producers)==1 and case.get('data') is not None:
                    producer = producers[0]
                    owner.invoke_internal_api_json_route = lambda **kw: ({'saved_text_path':saved(harness.documents_dir,'numbers','json',json.dumps(case['data'],sort_keys=True,separators=(',',':')))},200)
                    contract = owner.build_execution_contract(producer,producer,capability='chat')
                    result = owner.execute_prepared_late_fill_branch({'response_id':payload['id'],'capability':'chat','branch_id':producer['branch_id'],
                        'phase_id':producer['phase_id'],'execution_contract':contract,'infer_payload':{'prompt':'controlled fixture source'},'effective_data':{}})['infer_result']
                    record = owner.attach_late_fill_result_artifact_identity({**producer,**result},payload,result,capability='chat')
                    payload['late_fill']['fill_results']=[record]
                    payload['late_fill']['completed_branches']=[{**producer,'status':'fulfilled'}]
                    report['controlled_saved_producer']=deepcopy(record)
                    step('controlled_real_writer_snapshot_fixture')
                    report['ready_after'] = ready()
                    for branch in branches:
                        if branch.get('artifact_request',{}).get('source_name')!='result':continue
                        item={'branch_id':branch['branch_id'],'ready':branch['branch_id'] in report['ready_after']}
                        report['consumer_after_saved']=item
                        item['dependency']=runtime.branch_dependency_payload(branch,current_payload=payload)
                        step('dependency_after_saved_source')
                        try:
                            spec=runtime.build_late_fill_materialization_branch_spec(branch=branch,artifact_gap={},current_payload=payload,request_payload=request,
                                assistant_message=response.get('output_text',''),source_route_payload=None,failed_instance_id=None)
                            item['spec']=deepcopy(spec)
                            if spec:item['plan']=runtime.prepare_late_fill_branch_plan(**spec['prepare_args'])
                            step('consumer_prepare_after_saved_source')
                        except (RuntimeError, ValueError) as exc:
                            item['blocked']=str(exc)
                            step('consumer_block_after_saved_source')
                assert not harness.call_records, 'unexpected fake provider execution'
                assert not web._RESPONSE_LATE_FILL_IN_FLIGHT
        report['classification']='observed_pending_independent_assessment'
    except BaseException as exc:
        report['error']=repr(exc)
        raise
    finally:
        dump(root/'result.json',report)
    return report


DATA={'subject':'alpha','values':[7,11],'version':1}
SOURCE=json.dumps(DATA,sort_keys=True,separators=(',',':'))
EARLIER='Save numbers.json containing '+SOURCE+'. Read the actually saved file again. Create result.html from the read data with the subject, version, values and sum.'
UNDERSPECIFIED='Save numbers.json. Read the actually saved file again. Create result.html from the read data with the subject, version, values and sum.'
SUPPORTED='Save numbers.json with values [7,11]. Read the actually saved file again. Create result.html from the read data with the sum and embedded CSS.'

@pytest.mark.parametrize('label,case',[
    ('positive-01',{'prompt':EARLIER,'data':DATA}),
    ('positive-02',{'prompt':EARLIER,'data':DATA}),
    ('positive-03',{'prompt':UNDERSPECIFIED,'data':None}),
    ('known-supported',{'prompt':SUPPORTED,'data':{'values':[7,11]}}),
])
def test_original_observation(label,case):
    observe(label,case,'reproduction')

from tests.intake_coverage_model import controls, assert_intake, sensitivity, corpus


def evaluate(label,case,category='control'):
    report=observe(label,case,category)
    root=Path(os.environ['FRUTH_HYPOTHESIS_EVIDENCE_DIR'])/label
    assessment={'classification':3,'passed':False}
    try:
        assert_intake(case,report)
        assessment.update(classification=1,passed=True,sensitivity=sensitivity(case,report))
    except (AssertionError,KeyError,IndexError) as exc:
        assessment['finding']=str(exc)
        # Classification does not turn an unmet must-support expectation into
        # a pass. A correctly scoped, visibly blocked join is distinct from a
        # silent omission or an extra admitted output.
        from tests.intake_coverage_model import _admitted_outputs
        files,images,other=_admitted_outputs(report)
        consumers=[b for b in report['graph']['downstream_branches'] if b.get('artifact_request',{}).get('source_name')=='result']
        if (set(files)=={('numbers','json'),('result','html')} and len(images)==int(case.get('image',False))
                and not other and consumers and all(b.get('materialization_blocked') is True
                    and b.get('branch_contract_error')=='saved_file_dependency_unbound' for b in consumers)):
            assessment['classification']=2
    dump(root/'assessment.json',assessment)
    return assessment


@pytest.mark.parametrize('label,case',controls())
def test_intake_controls(label,case):
    result=evaluate(label,case)
    assert result['passed'],result


def test_one_sealed_intake_campaign():
    entries=corpus()
    evidence=Path(os.environ['FRUTH_HYPOTHESIS_EVIDENCE_DIR'])
    dump(evidence/'sealed-corpus.json',entries)
    results=[]
    for entry in entries:
        results.append(evaluate(entry['label'],entry['case'],'generated'))
    dump(evidence/'campaign-results.json',results)
    assert all(r['passed'] for r in results),[r for r in results if not r['passed']]

from tests.intake_coverage_model import family
BOUNDARY_CASES = [
    ('store-beta',family('beta',2,(7,11),2)),
    ('save-literal-image',family('image',1,(7,11),0)),
    ('planner-narrows',{**family(),'prepared_prompt':'Create result.html.'}),
    ('planner-widens',{**family(),'prepared_prompt':family()['prompt']+' Generate one image of a mountain.'}),
    ('requested-image',{**family(),'prompt':family()['prompt']+' Generate one image of a mountain.','image':True}),
    ('reserved-image',{**family(),'planner':{'output_text':'Preparation complete.','runtime':{'downstream_branches':[
        {'branch_id':'suggested-image','phase_id':'suggested-phase','capability':'image_generation','output_type':'image',
         'contract_state':'reserved','required':False,'artifact_prompt':'A mountain.','depends_on':['phase-1']}]}}}),
]

@pytest.mark.parametrize('label,case',BOUNDARY_CASES)
def test_boundary_observation(label,case):
    result=evaluate(label,case)
    # Observation receipt is not a conformance pass. Assessment retains failures.
    assert result['classification'] in (1,2,3)
