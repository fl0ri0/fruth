"""C7 qualification precedes binding, explicit refs, fallback and recovery."""
from copy import deepcopy
from itertools import permutations
from pathlib import Path

import pytest

from fruth_services.response_frames import (
    _late_fill_artifacts_by_binding,
    build_response_frame, load_latest_response_wire_state, persist_response_frame,
    prepare_response_output_state, response_payload_from_frame,
)
from fruth_services.responses import build_canonical_outputs, hoist_response_output_surfaces, output_artifact_is_qualified
from fruth_services.response_wire import late_fill_handle
from tests.fake_backends.fixtures import tiny_png_bytes
from tests.test_artifact_reference_continuity import assert_saved_identity, identity
from tests.test_graph_lineage_two_successors_hypothesis import TwoSuccessorMachine


def evidence(path, branch='image-duty', ref='artifact:accepted'):
    return dict(type='image', output_type='image', capability='image_generation',
                status='completed', path=str(path), saved_image_path=str(path),
                branch_id=branch, phase_id=branch, obligation_id='obligation-' + branch,
                artifact_ref=ref, artifact_id=ref.removeprefix('artifact:'),
                source_response_id='qualification', provenance_id='producer-' + branch)


def case(tmp_path):
    paths = [tmp_path / (name + '.png') for name in ('accepted', 'foreign', 'conflicting')]
    for path in paths:
        path.write_bytes(tiny_png_bytes())
    accepted = evidence(paths[0])
    foreign = {**evidence(paths[1], ref='artifact:foreign'), 'source_response_id': 'foreign-response'}
    conflict = {**evidence(paths[2], ref='artifact:conflict'), 'obligation_id': 'different-obligation'}
    slot = dict(slot_id='output-image-duty', type='image', status='fulfilled',
                branch_id='image-duty', phase_id='image-duty', obligation_id='obligation-image-duty',
                artifact_ref=foreign['artifact_ref'])
    payload = dict(id='qualification', status='completed', saved_image_path=accepted['path'],
                   late_fill=dict(status='completed', fill_results=[accepted], completed_branches=[deepcopy(accepted)]),
                   output_slots=[slot])
    return payload, (accepted, foreign, conflict)


@pytest.mark.parametrize('order', list(permutations(range(3))))
@pytest.mark.parametrize('explicit', ['foreign', 'conflict', 'accepted', 'none'])
def test_candidate_permutations_and_explicit_refs_use_only_accepted_result(tmp_path, order, explicit):
    payload, records = case(tmp_path)
    payload['artifacts'] = [deepcopy(records[index]) for index in order]
    if explicit == 'none':
        payload['output_slots'][0].pop('artifact_ref')
    else:
        payload['output_slots'][0]['artifact_ref'] = 'artifact:' + explicit
    original = deepcopy(payload)
    # Exercise the Responses owner directly, before frame reconciliation.
    outputs = build_canonical_outputs(payload, output_slots=payload['output_slots'], artifacts=payload['artifacts'])
    assert outputs[0]['artifact_ref'] == records[0]['artifact_ref']
    state = prepare_response_output_state(payload)
    assert state['output_slots'][0]['artifact_ref'] == records[0]['artifact_ref']
    assert state['outputs'][0]['artifact_ref'] == records[0]['artifact_ref']
    assert [(a['artifact_ref'], a['path']) for a in state['public_output_artifacts']] == [(records[0]['artifact_ref'], records[0]['path'])]
    frame = build_response_frame(payload)
    for rejected in records[1:]:
        dossier = frame['artifacts']['dossiers'][rejected['artifact_ref']]
        assert dossier['output_qualification'] == 'rejected'
        assert rejected in dossier['rejected_output_candidates']
    recovered = response_payload_from_frame(frame)
    assert recovered['outputs'][0]['artifact_ref'] == records[0]['artifact_ref']
    assert [(a['artifact_ref'], a['path']) for a in recovered['artifacts']] == [(records[0]['artifact_ref'], records[0]['path'])]
    assert payload == original
    assert len({Path(a['path']).read_bytes() for a in records}) == 1


@pytest.mark.parametrize('fault', ['missing_result', 'source', 'phase', 'obligation', 'provenance', 'artifact_id', 'path', 'failed_result'])
def test_no_qualifying_candidate_stays_unresolved_even_with_explicit_ref(tmp_path, fault):
    payload, records = case(tmp_path)
    accepted = records[0]
    candidate = deepcopy(accepted)
    if fault == 'missing_result':
        payload['late_fill'] = dict(pending_branches=[dict(branch_id='image-duty', phase_id='image-duty',
            obligation_id='obligation-image-duty', output_type='image', capability='image_generation')])
    elif fault == 'source':
        candidate['source_response_id'] = 'foreign-response'
    elif fault == 'path':
        candidate.update(path=records[1]['path'], saved_image_path=records[1]['path'])
    elif fault == 'failed_result':
        for result in payload['late_fill']['fill_results'] + payload['late_fill']['completed_branches']:
            result['status'] = 'failed'
    else:
        candidate[{'phase': 'phase_id', 'obligation': 'obligation_id', 'provenance': 'provenance_id',
                   'artifact_id': 'artifact_id'}[fault]] = 'conflicting-identity'
    payload['output_slots'][0]['artifact_ref'] = candidate['artifact_ref']
    # Direct selection cannot construct a result on behalf of its caller.
    outputs = build_canonical_outputs(payload, output_slots=payload['output_slots'], artifacts=[candidate])
    assert outputs[0]['status'] == 'pending' and not outputs[0].get('artifact_ref')
    assert not output_artifact_is_qualified(payload, candidate, slot=payload['output_slots'][0])
    if fault in {'missing_result', 'failed_result'}:
        payload['artifacts'] = [candidate]
        state = prepare_response_output_state(payload)
        assert state['output_slots'][0]['status'] == 'pending'
        assert not state['output_slots'][0].get('artifact_ref')
        assert not state['public_output_artifacts']
        recovered = response_payload_from_frame(build_response_frame(payload))
        assert not any(o.get('status') == 'fulfilled' for o in recovered['outputs'])
        assert not recovered.get('artifacts')


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('fault', ['source_response_id', 'obligation_id', 'provenance_id', 'artifact_id', 'phase_id'])
def test_rejected_shared_ref_claim_cannot_win_merge_or_identity_gate(tmp_path, reverse, fault):
    payload, records = case(tmp_path)
    rejected = {**records[0], fault: 'conflicting-claim'}
    candidates = [rejected, deepcopy(records[0])]
    if reverse:
        candidates.reverse()
    payload['artifacts'] = candidates
    payload['output_slots'][0]['artifact_ref'] = records[0]['artifact_ref']
    outputs = build_canonical_outputs(payload, output_slots=payload['output_slots'], artifacts=candidates)
    assert outputs[0]['artifact_ref'] == records[0]['artifact_ref']
    frame = build_response_frame(payload)
    assert frame['artifacts']['output'][0]['artifact_id'] == records[0]['artifact_id']
    assert frame['artifacts']['output'][0]['source_response_id'] == payload['id']
    dossier = frame['artifacts']['dossiers'][records[0]['artifact_ref']]
    assert dossier['artifact']['artifact_id'] == records[0]['artifact_id']
    assert dossier['output_qualification'] == 'accepted_with_rejected_candidates'
    assert dossier['rejected_output_candidates'] == [rejected]
    assert response_payload_from_frame(frame)['outputs'][0]['artifact_ref'] == records[0]['artifact_ref']


@pytest.mark.parametrize('same_ref', [False, True])
def test_two_accepted_conflicting_results_are_unresolved(tmp_path, same_ref):
    payload, records = case(tmp_path)
    second = evidence(Path(records[1]['path']), ref=records[0]['artifact_ref'] if same_ref else 'artifact:second')
    payload['late_fill']['fill_results'].append(second)
    payload['late_fill']['completed_branches'].append(deepcopy(second))
    payload['artifacts'] = [records[0], second]
    state = prepare_response_output_state(payload)
    assert not any(o.get('status') == 'fulfilled' for o in state['outputs'])
    assert not state['public_output_artifacts']
    assert not state['output_slots'][0].get('artifact_ref')


@pytest.mark.parametrize('identity_key', ['artifact_id', 'provenance_id'])
def test_same_path_and_ref_do_not_hide_conflicting_accepted_producer_identity(tmp_path, identity_key):
    payload, records = case(tmp_path)
    payload['late_fill']['fill_results'].append({**records[0], identity_key: 'different-producer-identity'})
    payload['artifacts'] = [records[0]]
    state = prepare_response_output_state(payload)
    assert not state['public_output_artifacts']
    assert state['outputs'][0]['status'] == 'pending'
    assert not state['outputs'][0].get('artifact_ref')


def test_same_result_path_alias_passes_existing_identity_gate(tmp_path):
    payload, records = case(tmp_path)
    alias = {**records[0], 'path': str(tmp_path / '.' / 'accepted.png')}
    # A symlink is a physical path alias, not an equal-byte sibling.
    link = tmp_path / 'alias.png'
    link.symlink_to(Path(records[0]['path']))
    alias['path'] = str(link)
    payload['artifacts'] = [alias, records[0]]
    assert output_artifact_is_qualified(payload, alias)
    state = prepare_response_output_state(payload)
    assert len(state['public_output_artifacts']) == 1
    assert state['outputs'][0]['artifact_ref'] == records[0]['artifact_ref']
    assert Path(state['public_output_artifacts'][0]['path']).resolve() == Path(records[0]['path'])
    assert state['artifact_identity']['final_projection_blocked'] is False


def test_cross_response_reference_projection_keeps_existing_owner():
    # Existing verified reference/reuse owners publish their own outputs. The
    # Late Fill result qualifier must not globally ban those foreign identities.
    artifact = dict(type='image', artifact_ref='artifact:retained', artifact_id='retained',
                    source_response_id='original-response', path='artifacts/images/retained.png')
    payload = dict(id='consumer-response')
    assert output_artifact_is_qualified(payload, artifact)
    outputs = build_canonical_outputs(payload, output_slots=[dict(type='image', status='fulfilled',
        slot_id='reference-output', artifact_ref=artifact['artifact_ref'])], artifacts=[artifact])
    assert outputs[0]['artifact_ref'] == artifact['artifact_ref']


@pytest.mark.parametrize('kind', ['image', 'png', 'jpg', 'jpeg', 'webp', 'output_type_only'])
@pytest.mark.parametrize('reverse', [False, True])
def test_existing_image_type_aliases_share_exact_qualification_before_indexing(tmp_path, kind, reverse):
    payload, records = case(tmp_path)
    accepted_alias, rejected = deepcopy(records[0]), deepcopy(records[1])
    for artifact in (accepted_alias, rejected):
        if kind == 'output_type_only':
            artifact.pop('type')
        else:
            artifact['type'] = kind
    assert output_artifact_is_qualified(payload, accepted_alias)
    assert not output_artifact_is_qualified(payload, rejected)
    assert _late_fill_artifacts_by_binding(payload, [accepted_alias])[('image-duty', 'image')]['artifact_ref'] == records[0]['artifact_ref']
    candidates = [rejected, records[0]]
    if reverse:
        candidates.reverse()
    index = _late_fill_artifacts_by_binding(payload, candidates)
    assert index[('image-duty', 'image')]['artifact_ref'] == records[0]['artifact_ref']
    payload['artifacts'] = candidates
    state = prepare_response_output_state(payload)
    assert state['outputs'][0]['artifact_ref'] == records[0]['artifact_ref']
    assert [artifact['artifact_ref'] for artifact in state['public_output_artifacts']] == [records[0]['artifact_ref']]


@pytest.mark.parametrize('fault', [None, 'source_response_id', 'obligation_id', 'provenance_id', 'artifact_id', 'phase_id', 'frame_id'])
def test_bounded_lookup_qualifies_from_same_frozen_accepted_result(tmp_path, fault):
    payload, records = case(tmp_path)
    payload['artifacts'] = [records[0]]
    payload['output_slots'][0]['artifact_ref'] = records[0]['artifact_ref']
    frames_dir = tmp_path / 'frames'
    persist_response_frame(build_response_frame(payload), frames_dir=frames_dir)
    wire = load_latest_response_wire_state(payload['id'], frames_dir=frames_dir)
    assert wire['ok']
    projected = wire['response_payload']
    projected['late_fill'] = late_fill_handle(projected)
    assert not projected['late_fill'].get('fill_results')
    projected['wire_projection']['live_state_overlay'] = 'same_frozen_frame_bounded_status_late_fill_surface_only'
    if fault == 'frame_id':
        projected['response_frame']['frame_id'] = 'different-frame'
    elif fault:
        projected['artifacts'][0][fault] = 'conflicting-identity'
        # Check raw candidate selection; canonicalization cannot supply a
        # replacement candidate to this direct owner call.
    outputs = build_canonical_outputs(projected, output_slots=projected['output_slots'], artifacts=projected['artifacts'])
    if fault:
        assert outputs[0]['status'] == 'pending' and not outputs[0].get('artifact_ref')
    else:
        assert outputs[0]['artifact_ref'] == records[0]['artifact_ref']
        hoisted = hoist_response_output_surfaces(projected)
        assert hoisted['artifacts'][0]['path'] == records[0]['path']
        assert hoisted['outputs'][0]['artifact_ref'] == records[0]['artifact_ref']


def test_rejected_candidate_cannot_reenter_through_no_slot_fallback(tmp_path):
    payload, records = case(tmp_path)
    outputs = build_canonical_outputs(payload, artifacts=[records[1]])
    assert not any(output.get('artifact_ref') for output in outputs)


@pytest.mark.parametrize('with_slot', [False, True])
def test_hoist_does_not_restore_rejected_existing_output_ref(tmp_path, with_slot):
    payload, records = case(tmp_path)
    payload['late_fill'] = dict(pending_branches=[dict(branch_id='image-duty', phase_id='image-duty',
        obligation_id='obligation-image-duty', output_type='image', capability='image_generation')])
    payload['artifacts'] = [records[1]]
    payload['outputs'] = [dict(payload['output_slots'][0], compatibility_derived=False, path=records[1]['path'])]
    if not with_slot:
        payload.pop('output_slots')
    hoisted = hoist_response_output_surfaces(payload)
    assert not hoisted.get('artifacts')
    assert not any(output.get('artifact_ref') for output in hoisted['outputs'])
    assert not any(output.get('status') == 'fulfilled' for output in hoisted['outputs'])


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('fault', ['wrong_response', 'wrong_obligation'])
@pytest.mark.parametrize('reverse_candidates', [False, True])
def test_immediate_projection_then_repeated_finalize_and_durable_reload(reverse, fault, reverse_candidates):
    machine = TwoSuccessorMachine()
    machine.control = True
    try:
        machine.accepted(reverse, 1)
        machine.admit()
        machine.execute()
        machine.conservation()
        first = {a['artifact_ref']: identity(a) for a in machine.engine.payload['response_frame']['artifacts']['output']}
        machine.next_parent()
        machine.admit()
        machine.seed_image(fault)
        if reverse_candidates:
            machine.engine.payload['artifacts'].reverse()
        machine.execute()
        # The independent original oracle runs immediately, before any repeat.
        machine.conservation()
        accepted = {a['artifact_ref']: identity(a) for a in machine.engine.payload['response_frame']['artifacts']['output']}
        assert len(accepted) == 2 and all(accepted[ref] == value for ref, value in first.items())
        assert_saved_identity(machine, accepted)
        for _ in range(2):
            machine.publish(machine.engine.finalize(deepcopy(machine.engine.payload)))
            machine.record('c7_repeated_finalization', fault=fault, reverse_candidates=reverse_candidates)
            machine.conservation()
            assert_saved_identity(machine, accepted)
        machine.repeat_worker()
        machine.recover()
        machine.conservation()
        assert len(machine.engine.harness.provider_calls) == 2
    except BaseException:
        machine.failed = True
        raise
    finally:
        machine.teardown()
