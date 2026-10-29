"""Independent literal family, support policy and assertions; no Fruth imports."""
import base64
from copy import deepcopy
import hashlib
import json

from hypothesis import strategies as st
from tests.persistence_trace_adapter import collect_traces


def family(subject='alpha',version=1,values=(7,11),wording=0,css=True):
    data={'subject':subject,'version':version,'values':list(values)}
    literal=json.dumps(data,sort_keys=True,separators=(',',':'))
    source=[f'Save numbers.json containing {literal}.',f'Write numbers.json containing {literal}.',f'Store numbers.json containing {literal}.'][wording]
    read=['Read the actually saved file again.','Reread the saved numbers.json file.','Re-read the stored JSON file.'][wording]
    consumer=['Create result.html from the read data','Build result.html using the read data','Write result.html based on the saved data'][wording]
    consumer+=' with the subject, version, values and sum'+(' and embedded CSS.' if css else '.')
    return {'prompt':' '.join([source,read,consumer]),'data':data,'source_clause':source,'consumer_clause':consumer,'read_clause':read,
            'css':css,'image':False,'must_support':True,'wording':wording}


def controls():
    base=family()
    known={'prompt':'Save numbers.json with values [7,11]. Read the actually saved file again. Create result.html from the read data with the sum and embedded CSS.',
           'data':{'values':[7,11]},'source_clause':'Save numbers.json with values [7,11].','read_clause':'Read the actually saved file again.',
           'consumer_clause':'Create result.html from the read data with the sum and embedded CSS.','css':True,'image':False,'must_support':True}
    return [('known-supported',known),('original-full',family(css=False)),('explicit-fields',base),
            ('paraphrase-reread',family('beta',2,(0,40),1)),('paraphrase-re-read',family('image',3,(40,0),2))]


def _admitted_outputs(report):
    graph=report['graph']
    obligations=graph['request_ir']['output_obligations']
    active=[o for o in obligations if o.get('required') is True and o.get('status') not in ('waived','superseded','cancelled')]
    branches={b['branch_id']:b for b in graph.get('downstream_branches',[])}
    files=[];images=[];other=[]
    for obligation in active:
        b=branches.get(obligation.get('branch_id'),{})
        req=b.get('artifact_request',{})
        if req.get('extension'):
            files.append((req.get('source_name'),req['extension']))
        elif obligation.get('output_type')=='image':images.append(obligation)
        elif obligation.get('output_type') not in ('text',None):other.append(obligation)
        elif (obligation.get('output_type')=='text' and obligation.get('role') not in
              ('preparation_output','evidence_output','review_output','semantic_review')):
            other.append(obligation)
    return files,images,other


def _contains_literal_data(text, expected):
    """Recognize the declared JSON object independently of production parsing."""
    decoder=json.JSONDecoder()
    for index,char in enumerate(text):
        if char!='{':continue
        try:value,_=decoder.raw_decode(text[index:])
        except ValueError:continue
        if value==expected:return True
    return False


def assert_intake(case,report):
    """Literal coverage plus actual admission/read/prepare evidence, not a native verdict.

    These assertions accept branch-local carriage, arbitrary extra internal tasks,
    and arbitrary phase/branch identifiers. They do not decide general paraphrase
    equivalence: the three prompt templates are independently declared equivalent.
    """
    assert report['caller_intent']['prompt']==case['prompt'], 'caller intent changed'
    files,images,other=_admitted_outputs(report)
    assert set(files)=={('numbers','json'),('result','html')}, ('file scope',files)
    assert len(images)==int(case.get('image',False)), ('image scope',len(images))
    assert not other, ('other output work',other)
    graph=report['graph']
    branches=graph['downstream_branches']
    producers=[b for b in branches if b.get('artifact_request',{}).get('source_name')=='numbers' and b.get('artifact_request',{}).get('extension')=='json']
    consumers=[b for b in branches if b.get('artifact_request',{}).get('source_name')=='result' and b.get('artifact_request',{}).get('extension')=='html']
    # Follow actual saved-file identity instead of extension/branch order.
    deps=[(b,b.get('artifact_request',{}).get('saved_file_dependency')) for b in consumers]
    deps=[(b,d) for b,d in deps if d]
    assert deps, 'required saved-file meaning missing/unbound'
    consumer,dep=deps[0]
    producer=next((b for b in producers if b['branch_id']==dep.get('producer_branch_id')),None)
    assert producer, 'saved-file producer identity lost'
    assert dep['producer_phase_id']==producer['phase_id'] and dep['consumer_branch_id']==consumer['branch_id'] and dep['consumer_phase_id']==consumer['phase_id'], 'dependency identities changed'
    assert producer['phase_id'] in consumer.get('depends_on',[]), 'source-consumer execution edge missing'
    assert dep['producer_request']=={'extension':'json','source_name':'numbers'} and dep['consumer_request']=={'extension':'html','source_name':'result'}, 'named dependency scope changed'
    assert case['consumer_clause'] in dep['consumer_instruction'], 'consumer meaning narrowed'
    prep=next((p for p in report['preparations'] if p['branch_id']==producer['branch_id']),{})
    producer_plan=prep.get('plan',{})
    assert [(r.get('source_name'),r.get('extension')) for r in producer_plan.get('infer_payload',{}).get('text_artifact_requests',[])]==[('numbers','json')], 'prepared producer output scope changed'
    producer_text=producer_plan.get('infer_payload',{}).get('prompt','')
    accepted_text='\n'.join(str(producer.get(k,'')) for k in ('content_payload','artifact_prompt','stage_direction'))
    assert (case['source_clause'] in producer_text or case['source_clause'] in accepted_text
            or _contains_literal_data(producer_text,case['data'])
            or _contains_literal_data(accepted_text,case['data'])), 'source data requirements lost'
    after=report.get('consumer_after_saved',{})
    assert after.get('ready') is True, 'consumer not ready after source evidence'
    assert consumer['branch_id'] not in report['ready_before'], 'consumer ready before source'
    plan=after.get('plan',{})
    assert plan and not after.get('blocked'), 'consumer preparation failed'
    assert not plan.get('effective_data',{}).get('materialization_blocked'), 'consumer remains blocked'
    sent=plan['infer_payload']
    assert [(r.get('source_name'),r.get('extension')) for r in sent['text_artifact_requests']]==[('result','html')], 'prepared consumer output scope changed'
    assert case['consumer_clause'] in sent['prompt'], 'prepared consumer meaning narrowed'
    assert case['source_clause'] not in sent['prompt'], 'root producer task replayed into consumer'
    body=sent['prompt'].split('--- SAVED FILE START ---\n',1)[1].split('\n--- SAVED FILE END ---',1)[0]
    assert json.loads(body)==case['data'], 'saved data not delivered'
    ev=plan['execution_contract']['saved_file_read_evidence']
    raw=base64.b64decode(ev['utf8_base64'])
    assert json.loads(raw)==case['data'] and body==raw.decode(), 'saved bytes differ from prepared packet'
    assert hashlib.sha256(raw).hexdigest()==ev['sha256'], 'read digest changed'
    snapshot=report['controlled_saved_producer']['saved_file_output_snapshot']
    assert ev['path']==snapshot['path'] and ev['artifact_ref']==snapshot['artifact_ref'] and ev['sha256']==snapshot['sha256'], 'read not bound to actual saved source'
    assert ev['producer_branch_id']==producer['branch_id'] and ev['consumer_branch_id']==consumer['branch_id'], 'prepared binding changed'


def sensitivity(case,report):
    """Independent observation faults; none calls runtime or starts a scenario."""
    # Legitimate alternative carriage must pass too: file scope is already
    # declared in the branch/request, so a literal JSON payload need not repeat
    # the source instruction sentence. This is an oracle control, not a claim
    # that a model produced this alternate representation.
    equivalent=deepcopy(report)
    producer=next(b for b in equivalent['graph']['downstream_branches']
                  if b.get('artifact_request',{}).get('source_name')=='numbers')
    prep=next(p for p in equivalent['preparations'] if p['branch_id']==producer['branch_id'])
    prep['plan']['infer_payload']['prompt']=json.dumps(case['data'])
    for key in ('content_payload','artifact_prompt','stage_direction'):
        producer.pop(key,None)
    assert_intake(case,equivalent)
    producer['content_payload']=json.dumps(case['data'])
    prep['plan']['infer_payload']['prompt']='Materialize the accepted branch payload.'
    assert_intake(case,equivalent)
    mutations=[]
    def add(name,fn):
        value=deepcopy(report);fn(value);mutations.append((name,value))
    add('caller_narrowed',lambda r:r['caller_intent'].update(prompt='Create result.html.'))
    add('reject_everything',lambda r:r['graph']['request_ir'].update(output_obligations=[]))
    def file_scope(r):
        b=next(b for b in r['graph']['downstream_branches'] if b.get('artifact_request',{}).get('source_name')=='result')
        b['artifact_request']['source_name']='wrong'
    add('wrong_html_target',file_scope)
    def extra(r):
        r['graph']['request_ir']['output_obligations'].append({'required':True,'status':'pending','output_type':'image','branch_id':'invented-image'})
    add('unrequested_image',extra)
    def extra_css(r):
        r['graph']['downstream_branches'].append({'branch_id':'invented-css','artifact_request':{'source_name':'styles','extension':'css'}})
        r['graph']['request_ir']['output_obligations'].append({'required':True,'status':'pending','output_type':'text','branch_id':'invented-css'})
    add('unrequested_css_file',extra_css)
    add('unrequested_text_output',lambda r:r['graph']['request_ir']['output_obligations'].append(
        {'required':True,'status':'pending','output_type':'text','role':'final_output','branch_id':'unrelated-poem'}))
    def dep_fault(r):
        b=next(b for b in r['graph']['downstream_branches'] if b.get('artifact_request',{}).get('saved_file_dependency'))
        b['artifact_request'].pop('saved_file_dependency')
    add('missing_saved_read',dep_fault)
    def edge_fault(r):
        b=next(b for b in r['graph']['downstream_branches'] if b.get('artifact_request',{}).get('saved_file_dependency'))
        b['depends_on']=[]
    add('missing_edge',edge_fault)
    add('prepared_missing_data',lambda r:r['consumer_after_saved']['plan']['infer_payload'].update(prompt='Create result.html.'))
    def changed_data(r):
        sent=r['consumer_after_saved']['plan']['infer_payload']
        prefix,rest=sent['prompt'].split('--- SAVED FILE START ---\n',1)
        _,suffix=rest.split('\n--- SAVED FILE END ---',1)
        wrong=deepcopy(case['data']);wrong['values']=[99,99]
        sent['prompt']=prefix+'--- SAVED FILE START ---\n'+json.dumps(wrong)+'\n--- SAVED FILE END ---'+suffix
    add('wrong_saved_values',changed_data)
    add('wrong_prepared_binding',lambda r:r['consumer_after_saved']['plan']['execution_contract']['saved_file_read_evidence'].update(consumer_branch_id='foreign'))
    def lost_source(r):
        b=next(b for b in r['graph']['downstream_branches'] if b.get('artifact_request',{}).get('source_name')=='numbers')
        p=next(p for p in r['preparations'] if p['branch_id']==b['branch_id'])
        p['plan']['infer_payload']['prompt']='Save numbers.json.'
        b.pop('content_payload',None);b.pop('artifact_prompt',None)
    add('source_values_omitted',lost_source)
    def extra_producer_scope(r):
        b=next(b for b in r['graph']['downstream_branches'] if b.get('artifact_request',{}).get('source_name')=='numbers')
        p=next(p for p in r['preparations'] if p['branch_id']==b['branch_id'])
        p['plan']['infer_payload']['text_artifact_requests'].append({'source_name':'extra','extension':'txt'})
    add('producer_scope_expanded',extra_producer_scope)
    if case.get('css'):
        def lost_css(r):
            b=next(b for b in r['graph']['downstream_branches'] if b.get('artifact_request',{}).get('saved_file_dependency'))
            b['artifact_request']['saved_file_dependency']['consumer_instruction']=b['artifact_request']['saved_file_dependency']['consumer_instruction'].replace(' and embedded CSS','')
        add('embedded_css_omitted',lost_css)
    for name,value in mutations:
        try:assert_intake(case,value)
        except (AssertionError,KeyError,IndexError):continue
        raise AssertionError('insensitive oracle: '+name)
    return [name for name,_ in mutations]


def corpus():
    strategy=st.tuples(st.sampled_from(('alpha','beta','image')),st.integers(1,3),st.tuples(st.integers(0,40),st.integers(0,40)),st.integers(0,2))
    draws=collect_traces(seed_value=2026102402,examples=26,strategy=strategy,validator=lambda value:None)
    entries=[{'label':'seed-'+str(i),'origin':'seeded','case':family(subject,1,(7,11),wording)} for i,(subject,wording) in enumerate((('alpha',0),('beta',1),('image',2),('beta',0),('image',1),('alpha',2)))]
    entries += [{'label':'generated-'+str(i),'origin':'hypothesis','case':family(*args)} for i,args in enumerate(draws)]
    assert len(entries)==32
    return entries
