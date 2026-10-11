"""Result-boundary evidence through existing artifact owners, fully offline."""
from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

import fruth_webserver as web
from fruth_services.artifact_contracts import sanitize_artifact_record
from fruth_services.artifact_registry import (
    build_output_artifact_registry_records, refresh_text_artifact_record_from_saved_path,
)
from fruth_services.responses import build_canonical_response_artifacts, merge_canonical_response_artifacts
from tests.test_instruction_admission_contract import real_owners


BYTES = b'# The permitted sentence.\n'
CONTRACT = {'extension': 'txt', 'source_name': 'allowed', 'source': 'explicit_extension'}
RESPONSE = 'result-evidence-response'


def output(path, **extra):
    return {'type': 'text', 'path': str(path), 'origin': 'assistant_output',
            'source_response_id': RESPONSE, 'text_artifact_request': deepcopy(CONTRACT),
            'file_sha256': hashlib.sha256(BYTES).hexdigest(), **extra}


def reuse(records):
    return web._LATE_FILL_RUNTIME._canonical_text_artifact_saved_result(
        {'id': RESPONSE, 'artifacts': records}, extension='txt', source_name='allowed')


@pytest.mark.parametrize('fault', ['name', 'extension', 'target', 'digest'])
@pytest.mark.parametrize('clean_first', [False, True])
def test_raw_root_conflicts_survive_canonical_registry_refresh(tmp_path, fault, clean_first):
    with real_owners(tmp_path, 'Unused controlled provider.') as harness:
        path = harness.documents_dir / 'allowed.txt'
        path.write_bytes(BYTES)  # Deliberate result fixture, not a provider write.
        clean = output(path)
        bad = deepcopy(clean)
        if fault == 'name':
            bad['name'] = 'foreign'
        elif fault == 'extension':
            bad['extension'] = 'html'
        elif fault == 'target':
            bad['text_artifact_target_path'] = str(harness.documents_dir / 'foreign.txt')
        else:
            bad['file_sha256'] = '0' * 64
        records = [clean, bad] if clean_first else [bad, clean]
        raw = {'id': RESPONSE, 'saved_text_path': str(path), 'saved_text_artifacts': records,
               'file_sha256': 'input-attachment-digest'}
        captured = web._LATE_FILL_RUNTIME.capture_root_text_artifact_saved_evidence(
            raw, accepted_requests=[deepcopy(CONTRACT)], response_id=RESPONSE, phase_id='root-phase')
        assert captured['text_artifact_binding_errors'][0]['code'] == 'TEXT_ARTIFACT_BINDING_VIOLATION'
        assert not reuse(records)  # Reconcile before any canonical sanitization.
        artifacts = build_canonical_response_artifacts(captured)
        assert artifacts and not reuse(artifacts)
        registry = build_output_artifact_registry_records({'id': RESPONSE, 'artifacts': artifacts})
        assert registry
        for artifact in artifacts:
            sanitized = sanitize_artifact_record(artifact)
            refreshed, _ = refresh_text_artifact_record_from_saved_path(sanitized)
            evidence = refreshed['text_artifact_saved_evidence']
            assert evidence['status'] == 'rejected'
            assert evidence['source'] == 'root_saved_result_validation'
            assert evidence['accepted_request'] == CONTRACT
            assert evidence['error']['code'] == 'TEXT_ARTIFACT_BINDING_VIOLATION'
            assert refreshed['file_sha256'] == hashlib.sha256(BYTES).hexdigest()
            assert not reuse([refreshed])
        assert any(r['artifact'].get('text_artifact_saved_evidence', {}).get('status') == 'rejected'
                   for r in registry)
        assert path.read_bytes() == BYTES
        assert not (harness.documents_dir / 'foreign.txt').exists()
        assert harness.provider_calls == []


@pytest.mark.parametrize('identity', ['source_response', 'frame', 'branch', 'reference', 'aliases'])
@pytest.mark.parametrize('clean_first', [False, True])
def test_distinct_evidence_and_legitimate_aliases_do_not_poison_current_output(tmp_path, identity, clean_first):
    with real_owners(tmp_path, 'Unused controlled provider.') as harness:
        path = harness.documents_dir / 'allowed.txt'
        path.write_bytes(BYTES)
        clean = output(path, phase_id='current-phase', branch_id='current-branch',
                       source_frame_id='current-frame')
        other = {**deepcopy(clean), 'file_sha256': '0' * 64}
        if identity == 'source_response':
            other['source_response_id'] = 'older-response'
        elif identity == 'frame':
            other['source_frame_id'] = 'older-frame'
        elif identity == 'branch':
            other.update(branch_id='older-branch', phase_id='older-phase')
        elif identity == 'reference':
            other.update(origin='selected_reference', source_response_id=None,
                         branch_id=None, phase_id=None)
        else:
            other.update(file_sha256=hashlib.sha256(BYTES).hexdigest(), artifact_ref='artifact:alias')
            clean['artifact_ref'] = 'artifact:original'
        records = [clean, other] if clean_first else [other, clean]
        assert reuse(records)['saved_text_path'] == str(path)
        assert path.read_bytes() == BYTES


def test_fresh_validated_evidence_keeps_old_rejection_diagnostic(tmp_path):
    with real_owners(tmp_path, 'Unused controlled provider.') as harness:
        path = harness.documents_dir / 'allowed.txt'
        path.write_bytes(BYTES)
        rejected = web._LATE_FILL_RUNTIME.capture_root_text_artifact_saved_evidence(
            {'saved_text_path': str(path), 'text_artifact_target_path': str(path.with_name('foreign.txt')),
             'saved_text_artifacts': [output(path)]}, accepted_requests=[deepcopy(CONTRACT)],
            response_id=RESPONSE, phase_id='original-phase')
        old = build_canonical_response_artifacts(rejected)
        assert not reuse(old)
        fresh = output(path, branch_id='validated-branch', phase_id='validated-phase')
        branch = {'requires_artifact': True, 'required': True, 'output_type': 'text',
                  'capability': 'chat', 'role': 'text_artifact_output',
                  'stage_direction': 'materialize_requested_text_artifact', 'artifact_request': CONTRACT}
        checked, error = web._LATE_FILL_RUNTIME._ensure_required_text_artifact_saved_truth(
            branch, {'saved_text_path': str(path), 'saved_text_artifacts': [fresh]}, {}, {})
        assert not error and checked['saved_text_path'] == str(path)
        merged = merge_canonical_response_artifacts(old, [fresh])
        assert len(merged) == 2
        assert reuse(merged)['saved_text_path'] == str(path)
        assert old[0]['text_artifact_saved_evidence']['status'] == 'rejected'
        assert path.read_bytes() == BYTES


def test_input_attachment_digest_is_not_output_digest(tmp_path):
    with real_owners(tmp_path, 'Unused controlled provider.') as harness:
        path = harness.documents_dir / 'allowed.txt'
        path.write_bytes(BYTES)
        raw = {'saved_text_path': str(path), 'saved_text_artifacts': [output(path)],
               'file_sha256': '0' * 64}
        captured = web._LATE_FILL_RUNTIME.capture_root_text_artifact_saved_evidence(
            raw, accepted_requests=[deepcopy(CONTRACT)], response_id=RESPONSE)
        assert 'text_artifact_binding_errors' not in captured
        assert reuse(build_canonical_response_artifacts(captured))['saved_text_path'] == str(path)


def test_returned_source_claim_cannot_exempt_conflicting_root_declaration(tmp_path):
    with real_owners(tmp_path, 'Unused controlled provider.') as harness:
        path = harness.documents_dir / 'allowed.txt'
        path.write_bytes(BYTES)
        old = output(path, source_response_id='old-response', file_sha256='0' * 64)
        raw = {'id': RESPONSE, 'saved_text_path': str(path), 'saved_text_artifacts': [old, output(path)]}
        captured = web._LATE_FILL_RUNTIME.capture_root_text_artifact_saved_evidence(
            raw, accepted_requests=[deepcopy(CONTRACT)], response_id=RESPONSE)
        assert captured['text_artifact_binding_errors']
        assert not reuse(build_canonical_response_artifacts(captured))
        assert captured['saved_text_artifacts'][0]['text_artifact_saved_evidence']['declarations'][1] == old


def test_extra_current_physical_output_exceeds_captured_count(tmp_path):
    with real_owners(tmp_path, 'Unused controlled provider.') as harness:
        paths = [harness.documents_dir / name for name in (
            'allowed.txt', '20261009T120000Z_chat_text_artifact_model_allowed_2.txt')]
        for path in paths:
            path.write_bytes(BYTES)
        raw = {'id': RESPONSE, 'saved_text_path': str(paths[0]),
               'saved_text_artifacts': [output(path) for path in paths]}
        captured = web._LATE_FILL_RUNTIME.capture_root_text_artifact_saved_evidence(
            raw, accepted_requests=[deepcopy(CONTRACT)], response_id=RESPONSE)
        assert captured['text_artifact_binding_errors']
        assert not reuse(build_canonical_response_artifacts(captured))
        assert all(path.read_bytes() == BYTES for path in paths)


def test_canonical_projection_cannot_claim_a_new_write_version(tmp_path):
    with real_owners(tmp_path, 'Unused controlled provider.') as harness:
        path = harness.documents_dir / 'allowed.txt'
        path.write_bytes(BYTES)
        captured = web._LATE_FILL_RUNTIME.capture_root_text_artifact_saved_evidence(
            {'saved_text_path': str(path), 'text_artifact_target_path': str(path.with_name('foreign.txt')),
             'saved_text_artifacts': [output(path)]}, accepted_requests=[deepcopy(CONTRACT)],
            response_id=RESPONSE, phase_id='root-phase')
        canonical = build_canonical_response_artifacts(captured)
        projection = output(path, phase_id='downstream-phase', branch_id='downstream-branch',
                            text_artifact_source='canonical_text_artifact_evidence')
        assert not reuse([*canonical, projection])
