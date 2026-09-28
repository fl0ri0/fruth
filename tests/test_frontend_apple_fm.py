"""Exercise display labels without changing transport identities or target selection."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which('node') is None, reason='node is required')
@pytest.mark.parametrize('metadata_source,expected', [
    ('missing', 'AFM'), ('catalog', 'AFM 3 Core Advanced'),
    ('instance', 'AFM 3 Core'), ('unavailable', 'AFM'),
])
def test_apple_fm_display_and_exact_tab_selection(metadata_source, expected):
    script = r'''
    const fs = require('fs');
    const vm = require('vm');
    const html = fs.readFileSync('fruth_webUI.html', 'utf8');
    const models = fs.readFileSync('static/ui/models.js', 'utf8');
    const messages = fs.readFileSync('static/ui/message-state.js', 'utf8');
    const rendering = fs.readFileSync('static/ui/messages.js', 'utf8');
    const metadataSource = METADATA_SOURCE;
    const catalog = {name: 'system', backend: 'apple_fm', backend_metadata: {
      system_model: {status:'available', display_name:'AFM 3 Core Advanced', context_size:8192}
    }};
    const instance = {backend_metadata: {system_model: {
      status: metadataSource === 'unavailable' ? 'probe_unavailable' : 'available',
      display_name:'AFM 3 Core', context_size:8192
    }}};
    function extract(source, name) {
      const start = source.indexOf('function ' + name + '(');
      const next = source.slice(start + 1).search(/\n\s*function /);
      return source.slice(start, next < 0 ? undefined : start + 1 + next);
    }
    const tabs = [];
    const context = {
      state: {currentInstanceId: 'apple_fm:system:11602',
        availableModels: metadataSource === 'missing' ? [] : [catalog]},
      normalizeBackend: b => b || 'ollama',
      getInstanceMeta: () => ['instance', 'unavailable'].includes(metadataSource) ? instance : null,
      getConversationInstanceMeta: () => null,
      isResponsesWorkbenchConversationId: () => true,
      elements: {modelTabs: {appendChild: tab => tabs.push(tab)}},
      switchToInstance: id => {context.selected = id;},
      document: {createElement: () => ({
        dataset: {}, classList: {add() {}},
        setAttribute(key, value) { this[key] = value; },
        addEventListener(key, handler) { this[key] = handler; }
      })},
    };
    vm.createContext(context);
    vm.runInContext(extract(html, 'formatModelDisplayName') + '\n' +
      extract(rendering, 'escapeHtml') + '\n' +
      extract(rendering, 'escapeHtmlAttribute') + '\n' +
      extract(html, 'getAvailableModelTruthSummary') + '\n' +
      extract(html, 'formatTabLabel') + '\n' +
      extract(models, 'createModelTab') + '\n' +
      extract(messages, 'buildAssistantMessageProvenance'), context);
    vm.runInContext(`
      createModelTab('apple_fm:system:11601','system','apple_fm');
      createModelTab('apple_fm:system:11602','system','apple_fm');
    `, context);
    tabs[1].click();
    console.log(JSON.stringify({
      label: context.formatModelDisplayName('system','apple_fm'),
      catalogLabel: context.formatModelDisplayName('system','apple_fm',catalog),
      otherWithMetadata: context.formatModelDisplayName('system','ollama',catalog),
      other: context.formatModelDisplayName('system','ollama'),
      alias: context.formatModelDisplayName('apple_fm:system:11602'),
      metadata: context.getAvailableModelTruthSummary({backend:'apple_fm',
        description:'Mac default: AFM 3 Core Advanced; 8,192-token context.'}),
      fallback: context.getAvailableModelTruthSummary({backend:'apple_fm'}),
      unknownBackend: context.buildAssistantMessageProvenance({}, 'responses').backend,
      explicitBackend: context.buildAssistantMessageProvenance({responseModel:'system', responseBackend:'apple_fm'}, 'responses').backend,
      ids: tabs.map(t => t.dataset.instanceId),
      labels: tabs.map(t => t['aria-label']), selected: context.selected
    }));
    '''
    script = script.replace('METADATA_SOURCE', json.dumps(metadata_source))
    run = subprocess.run(['node', '-e', script], cwd=ROOT, check=True, capture_output=True, text=True)
    result = json.loads(run.stdout)
    assert result['unknownBackend'] is None
    assert result['explicitBackend'] == 'apple_fm'
    assert result['label'] == 'AFM'
    assert result['other'] == 'system'
    assert result['catalogLabel'] == 'AFM 3 Core Advanced'
    assert result['otherWithMetadata'] == 'system'
    assert result['alias'] == 'AFM · 11602'
    assert result['metadata'] == 'On-device text + image analysis'
    assert result['fallback'] == 'On-device text + image analysis'
    assert result['ids'] == ['apple_fm:system:11601', 'apple_fm:system:11602']
    assert result['selected'] == result['ids'][1]
    assert result['labels'] == [f'{expected} · 11601 (Apple AI)',
                                f'{expected} · 11602 (Apple AI)']
