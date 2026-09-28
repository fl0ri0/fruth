"""Execute the real UI selection owners and their backend intake boundary offline."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from fruth_core.transports import resolve_saved_artifact_path
from fruth_server.request_intake_runtime import RequestIntakeRuntimeOwner
from fruth_server.response_semantics_runtime import ResponseSemanticsRuntimeOwner
from fruth_services.artifact_contracts import sanitize_artifact_record


ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(shutil.which('node') is None, reason='node required for UI owner tests')


def run_ui(body, fixture=None):
    script = r"""
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const fixture = JSON.parse(process.argv[1]);
const context = {
  console, fixture, window: {}, elements: {},
  state: {conversations: {}, responsesWorkbench: {}, arena: {enabled: false}, settings: {}},
  getActiveConversationId: () => 'conversation',
  isConversationVisible: () => false,
  normalizeCapability: value => String(value || '').toLowerCase(),
  normalizeBackend: value => String(value || '').toLowerCase(),
  basenameFromPath: value => String(value || '').split('/').pop(),
  sanitizeSettingsObject: value => value,
  updatePromptPlaceholder() {}, updateGlobalModelStatus() {},
  setTimeout: () => 1, clearTimeout() {},
};
vm.createContext(context);
for (const name of ['message-state', 'messages', 'request-lifecycle', 'request-transport']) {
  vm.runInContext(fs.readFileSync(`static/ui/${name}.js`, 'utf8'), context);
}
context.renderSelectedReferenceArtifact = () => {};
const api = context;
const plain = value => JSON.parse(JSON.stringify(value));
const ref = (n, source='resp-a') => ({
  type: ['audio','text','image'][n % 3], path: `/fixture/${n}`,
  artifact_id: `id-${n}`, artifact_ref: `artifact:${n}`, source_response_id: source,
  branch_id: `branch-${n}`, phase_id: `phase-${n}`, slot_id: `slot-${n}`,
  obligation_id: `obligation-${n}`,
});
(async () => {
""" + body + r"""
})().catch(error => { console.error(error); process.exit(1); });
"""
    result = subprocess.run(['node', '-e', script, json.dumps(fixture or {})], cwd=ROOT,
                            check=False, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout or '{}')


def test_artifact_selections_accumulate_deduplicate_and_roundtrip():
    run_ui(r"""
const references = Array.from({length:20}, (_, i) => ref(i));
references.forEach(item => api.setSelectedReferenceArtifact(item, {quiet:true}));
api.setSelectedReferenceArtifact(references[0], {quiet:true});
assert.strictEqual(api.getSelectedReferenceArtifacts().length, 20);
assert.deepStrictEqual(plain(api.buildSelectedReferenceArtifactPayload()).map(r => r.artifact_ref), references.map(r => r.artifact_ref));
const snapshot = api.compactRequestSnapshotReferenceArtifacts(api.buildSelectedReferenceArtifactPayload());
context.state.responsesWorkbench.selectedReferenceArtifactsByConversation.conversation = plain(snapshot);
const restored = plain(api.buildSelectedReferenceArtifactPayload());
for (let i=0; i<20; i++) {
  for (const key of ['artifact_id','artifact_ref','source_response_id','branch_id','phase_id','slot_id','obligation_id']) {
    assert.strictEqual(restored[i][key], references[i][key]);
  }
}
api.setSelectedReferenceArtifact(ref(0, 'resp-other'), {quiet:true});
assert.strictEqual(api.getSelectedReferenceArtifacts().length, 21);
assert.strictEqual(api.isSelectedArtifactReference(ref(0, 'resp-third')), false);
api.removeSelectedReferenceArtifactByPath('/fixture/1', {quiet:true});
assert.strictEqual(api.getSelectedReferenceArtifacts().length, 20);
assert(!api.getSelectedReferenceArtifacts().some(r => r.path === '/fixture/1'));
api.setSelectedReferenceArtifact(ref(99), {quiet:true, conversationId:'other'});
api.clearSelectedReferenceArtifact({quiet:true});
assert.strictEqual(api.getSelectedReferenceArtifacts().length, 0);
assert.strictEqual(api.getSelectedReferenceArtifacts('other').length, 1);
context.state.responsesWorkbench.selectedReferenceArtifactsByConversation.conversation = ref(42);
assert.strictEqual(api.buildSelectedReferenceArtifactPayload().artifact_ref, 'artifact:42');
process.stdout.write('{}');
""")


def test_reference_reply_includes_public_text_and_all_artifacts():
    run_ui(r"""
const audio = ref(0), transcript = ref(1);
const message = {role:'assistant', clientMessageId:'msg-a', responseId:'resp-a',
  content:'A short UI preview', artifacts:[audio, transcript],
  outputs:[
    {type:'text', value:'First public paragraph.', status:'fulfilled'},
    {type:'audio', artifact_ref:audio.artifact_ref, artifacts:[audio], status:'fulfilled'},
    {type:'text', value:'Second public paragraph.', status:'fulfilled'},
    {type:'text', artifact_ref:transcript.artifact_ref, artifacts:[transcript], status:'fulfilled'},
  ]};
context.state.conversations.conversation = [message];
const selection = api.buildMessageReplyReferencePayload(message);
assert.strictEqual(selection.length, 3);
assert.strictEqual(selection[0].content, 'First public paragraph.\n\nSecond public paragraph.');
assert.strictEqual(selection[0].source_response_id, 'resp-a');
assert.deepStrictEqual(plain(selection.slice(1)).map(r => r.artifact_ref), ['artifact:0','artifact:1']);
assert.strictEqual(selection[1].branch_id, 'branch-0');
assert.strictEqual(selection[2].phase_id, 'phase-1');
api.setSelectedReferenceArtifact(ref(2, 'another-source'), {quiet:true});
api.setSelectedReferenceArtifact(selection, {quiet:true});
api.setSelectedReferenceArtifact(selection, {quiet:true});
assert.strictEqual(api.getSelectedReferenceArtifacts().length, 4);
const snapshot = api.compactRequestSnapshotReferenceArtifacts(api.buildSelectedReferenceArtifactPayload());
context.state.responsesWorkbench.selectedReferenceArtifactsByConversation.conversation = plain(snapshot);
const restored = api.buildSelectedReferenceArtifactPayload();
assert.strictEqual(restored[0].content, selection[0].content);
assert.strictEqual(restored.length, 4);
const artifactOnly = api.buildMessageReplyReferencePayload({role:'assistant',clientMessageId:'msg-b',responseId:'resp-b',artifacts:[audio,transcript]});
assert.strictEqual(artifactOnly.filter(r => r.type !== 'message').length, 2);
assert.strictEqual(artifactOnly[1].source_response_id, 'resp-a');
assert.strictEqual(api.buildMessageReplyReferenceText({content:'Done.', outputs:[{type:'audio',status:'fulfilled',artifacts:[audio]}]}), 'Done.');
const legacy = api.buildMessageReplyReferencePayload({role:'assistant',clientMessageId:'msg-c',responseId:'resp-c',content:'Legacy reply',artifacts:[{type:'audio',path:'/fixture/legacy',artifact_ref:'artifact:legacy'}]});
assert.strictEqual(legacy[1].source_response_id, 'resp-c');
const blocked = ref(8);
const withInternalWork = {...message, artifacts:[audio,transcript,blocked],
  outputs:[...message.outputs, {type:'image',status:'blocked',artifact_ref:blocked.artifact_ref,artifacts:[blocked]}]};
assert(!api.buildMessageReplyReferencePayload(withInternalWork).some(r => r.artifact_ref === blocked.artifact_ref));
api.setSelectedReferenceArtifact({type:'message',message_id:'new-message',content:'Another reply'}, {quiet:true});
assert.strictEqual(api.getSelectedReferenceArtifacts().filter(r => r.type !== 'message').length, 3);
process.stdout.write('{}');
""")


def test_stream_json_and_multipart_keep_the_complete_reference_selection():
    run_ui(r"""
const references = Array.from({length:9}, (_, i) => ref(i));
api.setSelectedReferenceArtifact(references, {quiet:true});
context.getRequestExecutionInstance = value => value;
context.buildHistoryForApi = () => [];
context.buildInferenceRoutingConversationSnapshot = () => [];
context.buildSessionControlRequestFields = () => ({});
context.buildInferenceExecutionPreviewPayload = () => null;
context.getResponsesInferencePreferencesPayload = () => null;
context.getResponsesInferenceRequestMetaPayload = () => null;
context.parseExplicitBatchPrompts = () => [];
context.getInferTimeoutForRequest = () => 30000;
let streamPayload;
const stop = new Error('fixture transport boundary');
context.fetch = async (url, options) => { streamPayload = JSON.parse(options.body); throw stop; };
try {
  await api.sendViaResponsesStream({inferenceAuto:true,capability:'chat'}, 'auto', 'conversation', '', null,
    'Explain the saved runtime evidence without generating media.', 'resp-stream');
  assert.fail('fixture transport must stop');
} catch (error) { assert.strictEqual(error, stop); }
assert.deepStrictEqual(streamPayload.reference_artifacts.map(r => r.artifact_ref), references.map(r => r.artifact_ref));
assert.strictEqual(streamPayload.input.at(-1).type, 'message');
assert.strictEqual(streamPayload.input.at(-1).role, 'user');
const posts = [];
context.FormData = class { constructor(){this.entries={};} append(key,value){this.entries[key]=value;} };
context.axios = {post:async (url,payload) => {posts.push(payload); return {data:{}};}};
const target = {instance_id:'fixture', capability:'vision_analysis', inferenceAuto:true};
await api.sendViaResponsesTransport(target,'fixture','conversation','Explain saved state',null,'/fixture/input');
await api.sendViaResponsesTransport(target,'fixture','conversation','Explain saved state',{name:'input.png'});
const jsonRefs = plain(posts[0].reference_artifacts);
const multipartRefs = JSON.parse(posts[1].entries.reference_artifacts);
assert.deepStrictEqual(jsonRefs, streamPayload.reference_artifacts);
assert.deepStrictEqual(multipartRefs, streamPayload.reference_artifacts);
process.stdout.write('{}');
""")


def test_ui_generated_audio_references_reach_canonical_saved_evidence(tmp_path):
    audio = tmp_path / 'audio.wav'
    audio.write_bytes(b'fixture recorded bytes')
    transcript = tmp_path / 'transcript.txt'
    transcript.write_text('The Bine House is quiet.')
    digest = hashlib.sha256(audio.read_bytes()).hexdigest()
    artifacts = [dict(type=kind, path=str(path), artifact_ref=f'artifact:{kind}',
                      artifact_id=kind, source_response_id='resp-root',
                      branch_id=f'branch-{kind}', phase_id=f'phase-{kind}')
                 for kind, path in [('audio', audio), ('text', transcript)]]
    message = dict(role='assistant', clientMessageId='msg-root', responseId='resp-root',
                   content='Full reply. ' * 1400 + 'END OF REPLY', artifacts=artifacts)
    selected = run_ui(r"""
api.setSelectedReferenceArtifact(api.buildMessageReplyReferencePayload(fixture), {quiet:true});
process.stdout.write(JSON.stringify(api.buildSelectedReferenceArtifactPayload()));
""", message)
    intake = RequestIntakeRuntimeOwner(hooks={
        'resolve_saved_downloadable_artifact_path': lambda raw: resolve_saved_artifact_path(raw, allowed_roots={tmp_path}),
        'sanitize_artifact_record': sanitize_artifact_record,
        'get_cached_generated_image_state': lambda path: None,
    })
    refs = intake._extract_selected_reference_artifacts({'reference_artifacts': selected})
    refs = intake._sanitize_selected_reference_artifacts(refs)
    assert len(refs) == 3
    assert refs[0]['content'] == message['content']
    for ref, artifact in zip(refs[1:], artifacts):
        for key in ('artifact_ref', 'artifact_id', 'source_response_id', 'branch_id', 'phase_id'):
            assert ref[key] == artifact[key]
    source = {'id': 'resp-root', 'lifecycle_state': 'repair_needed', 'artifacts': artifacts,
              'runtime': {'graph_closure_review': {'status': 'blocked'}},
              'late_fill': {'fill_results': [{
                  'branch_id': 'branch-text', 'phase_id': 'phase-text',
                  'audio_reference_input_evidence': {
                      'artifact_ref': 'artifact:audio', 'path': str(audio),
                      'source_response_id': 'resp-root', 'file_sha256': digest,
                      'provider_input_sha256': digest, 'status': 'verified'},
                  'tts_stt_semantic_evidence': {'status': 'mismatch', 'semantic_match': False,
                                              'transcript_text': transcript.read_text(),
                                              'producer_branch_id': 'branch-audio',
                                              'consumer_branch_id': 'branch-text'},
              }]}}
    owner = ResponseSemanticsRuntimeOwner(hooks={
        'sanitize_selected_reference_artifacts': intake._sanitize_selected_reference_artifacts,
        'get_response_lookup_record': lambda response_id: {'id': 'resp-root', 'response_payload': source},
        'build_canonical_response_artifacts': lambda payload: payload['artifacts'],
        'resolve_semantic_review_artifact_path': lambda path: Path(path) if Path(path).parent == tmp_path else None,
    })
    note = owner._selected_artifact_state_readback(refs)
    projection = json.loads(note.split('\n', 1)[1])
    assert len(projection['artifacts']) == 2
    assert projection['sources'][0]['source_response_id'] == 'resp-root'
    assert projection['artifacts'][0]['file_binding_status'] == 'matched'
    assert any(e.get('status') == 'mismatch' and e.get('semantic_match') is False for e in projection['evidence'])
    prefix = owner.build_selected_reference_prompt_prefix(refs, 'chat')
    assert message['content'] in prefix
    assert 'current user request remains the live instruction' in prefix
    forged = [{**refs[1], 'source_response_id': 'wrong-response'}]
    unavailable = json.loads(owner._selected_artifact_state_readback(forged).split('\n', 1)[1])
    assert unavailable['artifacts'][0]['status'] == 'unavailable'
