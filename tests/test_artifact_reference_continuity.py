"""Canonical identity continuity; the original two-successor oracle is unchanged."""
from copy import deepcopy
import hashlib
from pathlib import Path

import pytest
from hypothesis import reproduce_failure, settings
from hypothesis.errors import DidNotReproduce
from hypothesis.stateful import get_state_machine_test

from fruth_services.artifact_registry import find_artifact_registry_record_by_artifact_ref
from fruth_services.response_frames import (
    _read_snapshot_ref_payload, build_response_frame, load_latest_response_state,
)
from fruth_services.responses import build_canonical_response_artifacts, merge_canonical_response_artifacts
from tests.fake_backends.fixtures import tiny_png_bytes

from tests.test_graph_lineage_two_successors_hypothesis import TwoSuccessorMachine


def test_retained_c6_failure_blob_no_longer_reproduces():
    machines = []

    def factory():
        machine = TwoSuccessorMachine()
        machine.control = True
        machines.append(machine)
        return machine

    replay = reproduce_failure('6.168.5', b'AXicY2BwBEIIASYhXEZkNgA/rAOR')(
        get_state_machine_test(factory, settings=settings(
            TwoSuccessorMachine.TestCase.settings, stateful_step_count=32)))
    try:
        replay()
    except DidNotReproduce:
        pass
    else:
        raise AssertionError('retained input was not executed')
    assert len(machines) == 1 and not machines[0].failed
    assert machines[0].index == 1 and machines[0].stage == 'frozen'
    assert len(machines[0].executed) == 1


IDENTITY = ('artifact_id', 'artifact_ref', 'ref', 'path', 'source_response_id',
            'provenance_id', 'branch_id', 'phase_id', 'obligation_id')


def identity(record):
    return {key: record[key] for key in IDENTITY if key in record}


def assert_saved_identity(machine, accepted):
    engine = machine.engine
    recovered = load_latest_response_state('stateful-lineage', frames_dir=engine.harness.response_frames_dir)
    assert recovered['ok']
    engine.counts['durable_recovery_reads'] += 1
    payload = recovered['response_payload']
    machine.check_payload(payload)
    frame = payload['response_frame']
    dossiers = frame['artifacts'].get('dossiers') or {}
    if not dossiers and frame['artifacts'].get('dossiers_snapshot_ref'):
        dossiers = _read_snapshot_ref_payload(frame['artifacts']['dossiers_snapshot_ref'],
            frames_dir=engine.harness.response_frames_dir, strict_child_refs=True)
        engine.counts['diagnostic_snapshot_reads'] += 1
    for ref, expected in accepted.items():
        artifact = next(a for a in frame['artifacts']['output'] if a['artifact_ref'] == ref)
        assert identity(artifact) == expected
        assert Path(artifact['path']).read_bytes() == engine.model.png
        output = next(o for o in frame['output']['outputs'] if o.get('artifact_ref') == ref)
        assert output['branch_id'] == expected['branch_id']
        assert output['phase_id'] == expected['phase_id']
        assert identity(dossiers[ref]['artifact']) == expected
        record = find_artifact_registry_record_by_artifact_ref(ref, ledger_path=engine.harness.registry_path)
        assert record['artifact_ref'] == ref
        # Generated-image Registry keeps richer producer provenance in artifact,
        # and canonical response bindings in metadata/linked_response_ids.
        for key in ('artifact_id', 'artifact_ref', 'ref', 'path', 'provenance_id'):
            if key in expected:
                assert record['artifact'][key] == expected[key]
        for key in ('branch_id', 'phase_id', 'obligation_id'):
            assert record['metadata'][key] == expected[key]
        assert expected['source_response_id'] in record['linked_response_ids']
        digest = hashlib.sha256(Path(record['artifact']['path']).read_bytes()).hexdigest()
        assert digest == hashlib.sha256(engine.model.png).hexdigest()
        engine.observations.append({'kind': 'canonical_registry_dossier_identity',
            'identity': expected, 'registry': deepcopy(record), 'dossier': deepcopy(dossiers[ref]),
            'file_sha256': digest})
        engine.counts['registry_identity_reads'] += 1


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('reuse', [False, True])
def test_carried_identity_matches_frames_dossiers_registry_and_reloads(reverse, reuse):
    machine = TwoSuccessorMachine()
    machine.control = True
    try:
        machine.accepted(reverse, 0)
        machine.admit()
        machine.execute()
        machine.conservation()
        accepted = {a['artifact_ref']: identity(a)
                    for a in machine.engine.payload['response_frame']['artifacts']['output']}
        assert_saved_identity(machine, accepted)
        machine.next_parent()
        machine.conservation()
        assert_saved_identity(machine, accepted)
        machine.admit()
        if reuse:
            machine.seed_image('valid')
        machine.execute()
        machine.repeat_worker()
        machine.duplicate()
        for status in ('queued', 'running', 'completed', 'failed'):
            for key in ('current', 'old', 'foreign'):
                machine.stale_callback(status, key)
        machine.conservation()
        all_accepted = {a['artifact_ref']: identity(a)
                        for a in machine.engine.payload['response_frame']['artifacts']['output']}
        assert len(all_accepted) == 2 and all(all_accepted[ref] == value for ref, value in accepted.items())
        assert_saved_identity(machine, all_accepted)
        # Repeated finalization appends frames. Admit the second successor from
        # its actual frozen parent first; a stale test parent is not authority.
        for _ in range(3):
            machine.publish(machine.engine.finalize(deepcopy(machine.engine.payload)))
            machine.record('repeated_finalization')
            machine.conservation()
            assert_saved_identity(machine, all_accepted)
        assert len(machine.executed) == (1 if reuse else 2)
    except BaseException:
        machine.failed = True
        raise
    finally:
        machine.teardown()


def saved_result(path, branch, ref):
    return {'branch_id': branch, 'phase_id': branch, 'obligation_id': 'obligation-' + branch,
            'capability': 'image_generation', 'output_type': 'image', 'status': 'completed',
            'saved_image_path': str(path), 'source_response_id': 'image-continuity',
            'artifact_id': ref.removeprefix('artifact:'), 'artifact_ref': ref,
            'provenance_id': 'producer-' + branch}


@pytest.mark.parametrize('root_claim', [None, 'artifact:unverified', 'artifact:accepted-first'])
def test_saved_path_shortcut_cannot_compete_with_accepted_branch_identity(tmp_path, root_claim):
    path = tmp_path / 'first.png'
    path.write_bytes(tiny_png_bytes())
    result = saved_result(path, 'first-image', 'artifact:accepted-first')
    payload = {'id': 'image-continuity', 'saved_image_path': str(path),
               'artifact_ref': root_claim, 'artifact_id': 'unverified-root-id',
               'late_fill': {'fill_results': [result], 'completed_branches': [deepcopy(result)]}}
    original = deepcopy(payload)
    canonical = build_canonical_response_artifacts(payload)
    assert payload == original
    assert len(canonical) == 1
    assert canonical[0]['artifact_ref'] == result['artifact_ref']
    assert canonical[0]['artifact_id'] == result['artifact_id']
    assert canonical[0]['branch_id'] == result['branch_id']
    assert canonical[0]['provenance_id'] == result['provenance_id']


def test_distinct_equal_bytes_do_not_validate_a_shared_ref_claim(tmp_path):
    paths = [tmp_path / 'first.png', tmp_path / 'second.png']
    for path in paths:
        path.write_bytes(tiny_png_bytes())
    results = [saved_result(path, branch, 'artifact:claimed-shared')
               for path, branch in zip(paths, ('first-image', 'second-image'))]
    payload = {'id': 'image-continuity', 'status': 'completed',
               'saved_image_path': str(paths[-1]), 'late_fill': {'status': 'completed', 'fill_results': results},
               'output_slots': [{'slot_id': 'slot-' + r['branch_id'], 'branch_id': r['branch_id'],
                   'phase_id': r['phase_id'], 'type': 'image', 'status': 'fulfilled',
                   'artifact_ref': r['artifact_ref']} for r in results]}
    frame = build_response_frame(payload, request_payload={'prompt': 'Create both accepted images.'})
    assert frame['artifacts']['identity']['final_projection_blocked']
    assert frame['artifacts']['identity']['conflicts']
    assert not any(o['status'] == 'fulfilled' for o in frame['output']['outputs'])
    assert all(path.read_bytes() == tiny_png_bytes() for path in paths)


def test_new_generation_keeps_its_new_identity_without_reusing_previous_ref(tmp_path):
    path = tmp_path / 'version.png'
    path.write_bytes(tiny_png_bytes())
    prior = saved_result(path, 'first-version', 'artifact:version-1')
    current = saved_result(path, 'second-version', 'artifact:version-2')
    frames = []
    for result in (prior, current):
        payload = {'id': 'image-continuity', 'saved_image_path': str(path),
                   'response_frame': deepcopy(frames[-1]) if frames else {},
                   'late_fill': {'fill_results': [result]}}
        canonical = build_canonical_response_artifacts(payload)
        merged = merge_canonical_response_artifacts([], canonical)
        assert len(merged) == 1 and merged[0]['artifact_ref'] == result['artifact_ref']
        assert merged[0]['provenance_id'] == result['provenance_id']
        frames.append(build_response_frame({**payload, 'artifacts': merged}))
    assert frames[0]['artifacts']['output'][0]['artifact_ref'] == 'artifact:version-1'
    assert frames[1]['artifacts']['output'][0]['artifact_ref'] == 'artifact:version-2'


def test_unowned_root_image_retains_normal_identity_construction(tmp_path):
    path = tmp_path / 'direct.png'
    path.write_bytes(tiny_png_bytes())
    payload = {'id': 'image-continuity', 'saved_image_path': str(path),
               'artifact_id': 'direct-image', 'artifact_ref': 'artifact:direct-image',
               'provenance_id': 'direct-producer'}
    canonical = build_canonical_response_artifacts(payload)
    assert len(canonical) == 1
    assert canonical[0]['artifact_ref'] == 'artifact:direct-image'
    assert canonical[0]['provenance_id'] == 'direct-producer'
