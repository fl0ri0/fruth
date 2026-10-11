"""Public truth-guard corrections must survive canonicalization and recovery."""
import copy
import json

import pytest

from fruth_server.response_semantics_runtime import (
    ResponseSemanticsRuntimeOwner, classify_phase_output_text,
    control_json_envelope_suspected, visible_control_json_envelope,
)
from fruth_services.response_frames import (
    build_response_frame, persist_response_frame, load_latest_response_state,
)
from fruth_services.responses import (
    build_canonical_outputs, build_canonical_response_artifacts,
    hoist_response_output_surfaces, project_truth_guard_text, select_public_output_text,
)


def guard(payload, **kwargs):
    owner = ResponseSemanticsRuntimeOwner(hooks={
        'build_canonical_response_artifacts': build_canonical_response_artifacts,
        'normalize_capability_list': lambda values: values if isinstance(values, list) else [],
    })
    return owner.truth_gate_response_output_claims(payload, **kwargs)


def claim_payload(text):
    slot = {'slot_id': 'output-1', 'phase_id': 'phase-1', 'type': 'text',
            'status': 'fulfilled', 'lifecycle': 'materialized_output', 'value': text}
    return {'id': 'resp_guard_projection', 'status': 'completed',
            'lifecycle_state': 'repair_needed', 'capability': 'chat',
            'output_text': text, 'artifacts': [],
            'outputs': [dict(slot, compatibility_derived=False)], 'output_slots': [slot]}


@pytest.mark.parametrize('text,kind', [
    ('Artifact generated.', 'rewritten'),
    ('Materialized artifacts:\nArtefakt 1: Brief -> fulfilled', 'annotated'),
    ('Artifact created.\n```html\n<h1>Text only</h1>\n```', 'rewritten'),
])
def test_guarded_text_agrees_across_outputs_frame_and_recovery(text, kind, tmp_path):
    original = claim_payload(text)
    before = copy.deepcopy(original)
    updated = guard(original)
    assert original == before
    corrected = updated['output_text']
    assert corrected != text
    assert updated['runtime']['truth_guard']['status'] == kind
    assert updated['outputs'][0]['value'] == corrected
    assert updated['output_slots'][0]['value'] == corrected
    assert guard(updated) == updated
    assert select_public_output_text(updated, original['outputs']) == corrected
    assert build_canonical_outputs(updated, output_slots=original['output_slots'])[0]['value'] == corrected
    hoisted = hoist_response_output_surfaces({**updated, 'outputs': before['outputs']})
    assert hoisted['output_text'] == hoisted['outputs'][0]['value'] == corrected
    frame = build_response_frame({**updated, 'output_slots': before['output_slots']},
                                 request_payload={'prompt': 'Give a short explanation.'})
    assert frame['output']['text'] == corrected
    assert frame['output']['outputs'][0]['value'] == corrected
    assert frame['current_state']['output_slots'][0]['value'] == corrected
    persist_response_frame(frame, frames_dir=tmp_path/'frames')
    state = load_latest_response_state(updated['id'], frames_dir=tmp_path/'frames')
    assert state['ok']
    recovered = state['response_payload']
    assert recovered['output_text'] == recovered['outputs'][0]['value'] == corrected
    assert recovered['lifecycle_state'] == 'repair_needed'
    assert not recovered.get('artifacts')


def test_correction_is_bound_to_selected_output_not_equal_sibling_text():
    p = claim_payload('Artifact generated.')
    second = {**p['outputs'][0], 'slot_id': 'output-phase-2', 'phase_id': 'phase-2',
              'branch_id': 'branch-summary'}
    p['outputs'].append(second)
    p['output_slots'].append(dict(second))
    updated = guard(p)
    assert updated['outputs'][0] == p['outputs'][0]
    assert updated['outputs'][1]['value'] == updated['output_text']
    # A later genuine result, even for the same owner, must not be overwritten.
    later = [{**second, 'value': 'The report is still unavailable.'}]
    assert project_truth_guard_text(updated, later) == later
    assert select_public_output_text(updated, later) == later[0]['value']


@pytest.mark.parametrize('binding', ['artifact_ref', 'saved_text_path', 'path', 'artifact_path'])
def test_projection_does_not_replace_artifact_bound_content(binding):
    p = claim_payload('Artifact generated.')
    updated = guard(p)
    artifact_record = {**p['outputs'][0], binding: 'artifact:report' if binding == 'artifact_ref' else '/synthetic/report.md'}
    assert project_truth_guard_text(updated, [artifact_record]) == [artifact_record]


def test_correction_cannot_be_recovered_from_an_unrelated_output():
    p = claim_payload('Artifact generated.')
    updated = guard(p)
    corrected = updated['output_text']
    updated['output_text'] = 'New independent summary.'
    updated['outputs'] = [{**p['outputs'][0], 'slot_id': 'unrelated', 'value': corrected}]
    assert project_truth_guard_text(updated, p['outputs']) == p['outputs']


def test_prior_correction_does_not_bypass_current_source_grounding():
    updated = guard(claim_payload('Artifact generated.'))
    regrounded = guard(updated, request_payload={'prompt': 'Turn this text into a local HTML file.'})
    assert regrounded['runtime']['truth_guard']['status'] == 'clarification_required'


def test_shared_phase_without_selected_slot_identity_is_not_a_mirror():
    p = claim_payload('Artifact generated.')
    updated = guard(p)
    other_branch = {'branch_id': 'branch-other', 'phase_id': 'phase-1', 'type': 'text',
                    'value': p['output_text'], 'status': 'fulfilled'}
    assert project_truth_guard_text(updated, [other_branch]) == [other_branch]


@pytest.mark.parametrize('field,value', [
    ('type', 'image'), ('type', 'audio'),
    ('phase_id', 'another-phase'), ('branch_id', 'another-branch'),
])
def test_same_slot_does_not_override_type_or_conflicting_secondary_identity(field, value):
    original = claim_payload('Artifact generated.')
    for collection in ('outputs', 'output_slots'):
        original[collection][0]['branch_id'] = 'original-branch'
    corrected = guard(original)
    record = {**original['outputs'][0], field: value}
    assert project_truth_guard_text(corrected, [record]) == [record]


@pytest.mark.parametrize('source', [
    '{"description":"The request_ir field describes requested work."}',
    '["request_ir", {"description":"output_obligations"}]',
    '```json\n{"description":"decision_contract"}\n```',
    '{"example":{"request_ir":{"note":"nested documentation example"}}}',
    '```json\n{"description":"request_ir"}\n```\nThis describes the field.',
    '{"description":"request_ir",}',
    '[Draft] The decision_contract field describes the decision.',
    '{"description":"An example: \\"request_ir\\": []",}',
    '{"response":{"message":"The request_ir field describes work."}}',
    '{"response":{"example":{"request_ir":{"output_obligations":[]}}}}',
])
def test_valid_ordinary_json_does_not_trigger_control_guard(source):
    assert not control_json_envelope_suspected(source)
    assert not visible_control_json_envelope(source)
    assert classify_phase_output_text(source)['accepted_text'] == source
    assert guard({'output_text': source}) == {'output_text': source}


@pytest.mark.parametrize('source', [
    '{"request_ir":{"output_obligations":[]}}',
    '[{"decision_contract":{"status":"ready"}}]',
    '{"request\\u005fir":{"output_obligations":[]}}',
    '```json\n{"request_ir":{"output_obligations":[]}}\n```',
    '{"request_ir":{"output_obligations":[',
    '{"request_ir":{"output_obligations":[{"content_payload":"A"},{"content_payload":"B"}]}}',
    '{"request\\u005fir":{"output_obligations":[',
    '{request_ir: {output_obligations: [',
    "{'request_ir': {'output_obligations': [",
    '{"response":{"request_ir":{"output_obligations":[]}}}',
    '[{"response":{"request_ir":{"output_obligations":[]}}}]',
    '{"response":{"response":{"request_ir":{"output_obligations":[]}}}}',
    '```json\n{"request_ir":{"output_obligations":[]}}\n```\nDone.',
])
def test_actual_or_truncated_control_envelopes_remain_rejected(source):
    assert control_json_envelope_suspected(source)
    assert classify_phase_output_text(source)['status'] == 'repair_required'


def test_escaped_control_key_with_one_safe_payload_can_be_unwrapped():
    source = '{"request\\u005fir":{"content_payload":"A lighthouse marks dangerous rocks."}}'
    assert visible_control_json_envelope(source)
    result = classify_phase_output_text(source)
    assert result['status'] == 'unwrapped'
    assert result['accepted_text'] == 'A lighthouse marks dangerous rocks.'


def test_response_wrapper_retains_single_payload_and_nested_control_guards():
    wrapped = json.dumps({'response': {'request_ir': {'content_payload': 'A factual sentence.'}}})
    assert classify_phase_output_text(wrapped)['accepted_text'] == 'A factual sentence.'
    nested_control = json.dumps({'response': {'request_ir': {'output_obligations': []}}})
    unsafe = json.dumps({'request_ir': {'content_payload': nested_control}})
    assert classify_phase_output_text(unsafe)['status'] == 'repair_required'
