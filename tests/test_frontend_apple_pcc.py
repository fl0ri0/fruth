"""Existing card/tab/preference controls expose the PCC instance identity."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which('node') is None, reason='node is required')
def test_pcc_tab_and_preferred_ii_use_normal_instance_controls():
    script = r'''
    const fs = require('fs'), vm = require('vm');
    const html = fs.readFileSync('fruth_webUI.html', 'utf8');
    const models = fs.readFileSync('static/ui/models.js', 'utf8');
    function extract(source, name) {
      const start = source.indexOf('function ' + name + '(');
      const next = source.slice(start + 1).search(/\n\s*(?:async )?function /);
      return source.slice(start, next < 0 ? undefined : start + 1 + next);
    }
    const instance = {instance_id:'apple_pcc:auto:11651', model:'auto', backend:'apple_pcc',
      capability:'chat', inputs:['text','image'], outputs:['text'], supported_capabilities:['chat','vision_analysis']};
    const tabs = [], select = {innerHTML:'', options:[], appendChild(o){this.options.push(o);}};
    const ctx = {
      state:{currentInstanceId:instance.instance_id, runningInstances:[instance]},
      isUserFacingInstance:()=>true, frontendInstanceSupportsCapability:(i,c)=>i.supported_capabilities.includes(c),
      isTextCapableInstance:()=>true, isOcrSpecialistInstance:()=>false, isEmbeddingInstance:()=>false,
      isSpeechToTextInstance:()=>false, isTtsInstance:()=>false, isImageGenerationInstance:()=>false,
      getCodexExternalTarget:()=>null, escapeHtml:x=>x, escapeHtmlAttribute:x=>x,
      elements:{modelTabs:{appendChild:t=>tabs.push(t)}},
      switchToInstance:id=>{ctx.selected=id;},
      document:{createElement:()=>({dataset:{},classList:{add(){}},setAttribute(k,v){this[k]=v;},
                                    addEventListener(k,v){this[k]=v;}})}
    };
    vm.createContext(ctx);
    const functions = ['normalizeBackend','normalizeCapability','formatBackendLabel','formatModelDisplayName',
      'formatTabLabel','sanitizeResponsesInferencePreferenceTarget','serializeResponsesInferencePreferenceTarget',
      'isInferenceChatPreferenceCandidate','isInferenceRoutingPreferenceCandidate',
      'getResponsesInferenceRoutingInstances','formatInferencePreferenceInstanceLabel',
      'populateResponsesInferencePreferenceSelect'];
    vm.runInContext(functions.map(n=>extract(html,n)).join('\n')+'\n'+extract(models,'createModelTab'),ctx);
    ctx.createModelTab(instance.instance_id,instance.model,instance.backend);
    tabs[0].click();
    ctx.populateResponsesInferencePreferenceSelect(select,ctx.getResponsesInferenceRoutingInstances(),
      {model:'auto',backend:'apple_pcc'},'Auto');
    console.log(JSON.stringify({label:tabs[0]['aria-label'],selected:ctx.selected,
      options:select.options.map(o=>({value:o.value,label:o.textContent})),
      sourceLabel:ctx.formatBackendLabel('apple_pcc')}));
    '''
    run = subprocess.run(['node', '-e', script], cwd=ROOT, capture_output=True, text=True, check=True)
    result = json.loads(run.stdout)
    assert result['label'] == 'Apple PCC · 11651'
    assert result['selected'] == 'apple_pcc:auto:11651'
    assert result['sourceLabel'] == 'Apple PCC'
    assert result['options'][1]['label'] == 'Apple PCC'
    assert json.loads(result['options'][1]['value']) == {'model': 'auto', 'backend': 'apple_pcc'}
