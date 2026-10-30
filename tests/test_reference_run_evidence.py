from __future__ import annotations

import base64
import copy
import hashlib
import json

import pytest

from scripts import reference_run_evidence as evidence
from scripts import export_reference_run as exporter


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fixture():
    data = {'artifacts/source.json': b'[7,77]\n', 'artifacts/result.html': b'<p>84</p>',
            'artifacts/image.png': b'image bytes'}
    artifacts = [dict(artifact_ref='artifact:' + name, published_path=path,
                      sha256=sha(data[path]), size_bytes=len(data[path]), branch_id=name, phase_id='phase-' + name)
                 for name, path in zip(('producer', 'consumer', 'image'), data)]
    def snapshot(a):
        return {**{k: v for k, v in a.items() if k != 'published_path'},
                'artifact_id': a['artifact_ref'].split(':')[1], 'source_response_id': 'response',
                'path': '/Users/private/' + a['published_path']}
    producer, consumer, image = artifacts
    binding = {k: k for k in evidence.BINDING_KEYS}
    binding.update(source_branch_id='consumer', source_phase_id='phase-consumer',
                   branch_id='review', phase_id='phase-review', sha256='a'*64, instruction_sha256='b'*64)
    report = 'A small blue object.'
    results = [
        dict(branch_id='producer', phase_id='phase-producer', saved_file_output_snapshot=snapshot(producer)),
        dict(branch_id='consumer', phase_id='phase-consumer', saved_file_output_snapshot=snapshot(consumer),
             saved_file_consumption_evidence=dict(status='consumed', input_sha256='c'*64,
                 contract=dict(producer_branch_id='producer', producer_phase_id='phase-producer',
                               consumer_branch_id='consumer', consumer_phase_id='phase-consumer',
                               consumer_instruction='private model instructions'),
                 read={**snapshot(producer), 'producer_branch_id': 'producer', 'producer_phase_id': 'phase-producer',
                       'consumer_branch_id': 'consumer', 'consumer_phase_id': 'phase-consumer', 'encoding': 'utf-8',
                       'utf8_base64': base64.b64encode(data[producer['published_path']]).decode()},
                 output=dict(sha256=consumer['sha256'], size_bytes=consumer['size_bytes'],
                             path=snapshot(consumer)['path']))),
        dict(branch_id='review', phase_id='review', semantic_review_evidence_binding=binding),
        dict(branch_id='vision', phase_id='phase-vision', result_text=report,
             vision_input_evidence=dict(branch_id='vision', phase_id='phase-vision', response_id='response',
                                        image_sha256=image['sha256'], size_bytes=image['size_bytes'], status='supplied')),
        dict(branch_id='delivery', phase_id='phase-delivery', result_text='Image 1\n' + report,
             report_delivery_evidence=dict(kind='fruth.separate_image_report_delivery', branch_id='delivery',
                 phase_id='phase-delivery', response_id='response', contributions=[dict(
                     artifact_ref=image['artifact_ref'], image_sha256=image['sha256'],
                     producer_branch_id='image', producer_phase_id='phase-image', source_branch_id='vision',
                     source_phase_id='phase-vision', report_text=report, report_sha256=sha(report.encode()))])),
    ]
    checks = [dict(branch_id='consumer', phase_id='phase-consumer', branch_semantic_review_evidence_binding=copy.deepcopy(binding),
                   semantic_review_freeze_acceptance=dict(accepted=True, status='accepted', required_criteria=['accepted_consumer_content']),
                   completion_basis='bound_semantic_review', content_coverage_status='accepted_review')]
    outputs = [dict(slot_id='output-delivery', branch_id='delivery', phase_id='phase-delivery', text='Image 1\n' + report)]
    return dict(results=results, checks=checks, response_id='response', artifacts=artifacts, outputs=outputs, read_public=data.__getitem__)


def test_saved_bindings_are_portable_and_allowlisted():
    f = fixture()
    f['checks'].extend([{'branch_id': 'consumer', 'obligation_id': 'another-obligation'},
                        {'branch_id': 'consumer', 'obligation_id': 'third-obligation'}])
    f['results'][2]['semantic_review_evidence_binding']['private_future_field'] = {'secret': '/Users/private/token'}
    f['checks'][0]['branch_semantic_review_evidence_binding']['private_future_field'] = {'secret': '/Users/private/token'}
    projection = evidence.project_evidence(**f)
    evidence.verify_projection(projection, artifacts=f['artifacts'], outputs=f['outputs'], read_public=f['read_public'])
    assert projection['semantic_reviews'][0]['source_artifact']['artifact_ref'] == 'artifact:consumer'
    assert projection['semantic_reviews'][0]['recorded_result_phase_id'] == 'review'
    assert projection['semantic_reviews'][0]['binding']['phase_id'] == 'phase-review'
    assert projection['saved_file_reads'][0]['producer']['artifact_ref'] == 'artifact:producer'
    assert projection['image_reports'][0]['image']['artifact_ref'] == 'artifact:image'
    assert projection['image_reports'][0]['report_text'] == 'A small blue object.'
    assert projection['model_judgments_independently_proven'] is False
    assert projection['saved_file_reads'][0]['consumer_input_digest_recomputed'] is False
    text = json.dumps(projection)
    assert all(s not in text for s in ('/Users/', 'private_future_field', 'private model instructions', 'utf8_base64'))


def test_missing_evidence_is_not_a_success_claim():
    projection = evidence.project_evidence([], [], response_id='old', artifacts=[], outputs=[], read_public=lambda _: pytest.fail())
    assert set(projection['availability'].values()) == {'not_recorded'}
    assert projection['semantic_reviews'] == projection['saved_file_reads'] == projection['image_reports'] == []


@pytest.mark.parametrize('mutation', [
    lambda f: f['checks'][0]['branch_semantic_review_evidence_binding'].update(generation_id='stale'),
    lambda f: f['results'][1]['saved_file_output_snapshot'].update(sha256='d'*64),
    lambda f: f['results'][1]['saved_file_consumption_evidence']['read'].update(source_response_id='foreign'),
    lambda f: f['results'][1]['saved_file_consumption_evidence']['read'].update(artifact_id='other'),
    lambda f: f['results'][1]['saved_file_consumption_evidence']['read'].update(consumer_branch_id='wrong'),
    lambda f: f['results'][1]['saved_file_consumption_evidence']['read'].update(utf8_base64='WzFd'),
    lambda f: f['results'][1]['saved_file_consumption_evidence']['output'].update(sha256='e'*64),
    lambda f: f['results'][1]['saved_file_consumption_evidence']['read'].update(path='/Users/private/another.json'),
    lambda f: f['results'][1]['saved_file_consumption_evidence']['output'].update(path='/Users/private/another.html'),
    lambda f: f['results'][3]['vision_input_evidence'].update(image_sha256='f'*64),
    lambda f: f['results'][3].update(result_text='another report'),
    lambda f: f['results'][4]['report_delivery_evidence'].update(response_id='foreign'),
    lambda f: f['outputs'][0].update(text='omitted report'),
    lambda f: f['results'].append(copy.deepcopy(f['results'][2])),
    lambda f: f['results'].pop(2),
    lambda f: f['results'][2]['semantic_review_evidence_binding'].update(instruction_sha256={'private': 'secret'}),
])
def test_conflicting_saved_evidence_rejects(mutation):
    f = fixture()
    mutation(f)
    with pytest.raises(ValueError, match='Reference evidence'):
        evidence.project_evidence(**f)


@pytest.mark.parametrize('mutation', [
    lambda p: p['semantic_reviews'][0]['source_artifact'].update(sha256='f'*64),
    lambda p: p['semantic_reviews'][0]['binding'].update(source_branch_id='producer'),
    lambda p: p['saved_file_reads'][0]['consumer'].update(artifact_ref='artifact:producer'),
    lambda p: p['saved_file_reads'][0].update(consumer_input_digest_recomputed=True),
    lambda p: p['image_reports'][0].update(report_text='changed'),
    lambda p: p['image_reports'][0].update(output_slot_id='another-slot'),
    lambda p: p['availability'].update(semantic_reviews='not_recorded'),
])
def test_portable_verifier_detects_conflicts_even_with_rehashed_manifest(mutation):
    f = fixture()
    projection = evidence.project_evidence(**f)
    mutation(projection)
    with pytest.raises(ValueError, match='Reference evidence'):
        evidence.verify_projection(projection, artifacts=f['artifacts'], outputs=f['outputs'], read_public=f['read_public'])


def test_selected_sidecar_reader_is_exact_and_read_only(tmp_path):
    f = fixture()
    def sidecar(name, value):
        payload = json.dumps(value).encode()
        (tmp_path / name).write_bytes(payload + b'\n')
        return dict(path=name, sha256=sha(payload), size_bytes=len(payload))
    stored_results = copy.deepcopy(f['results'])
    stored_results[2]['semantic_review_evidence_binding_snapshot_ref'] = sidecar(
        'binding.json', stored_results[2].pop('semantic_review_evidence_binding'))
    results_ref = sidecar('results.json', stored_results)
    checks_ref = sidecar('checks.json', f['checks'])
    runtime = {'late_fill': {'fill_results_snapshot_ref': results_ref},
               'graph_closure_review': {'checks_snapshot_ref': checks_ref},
               'unrelated_snapshot_ref': {'path': 'DO-NOT-READ.json'}}
    record = {'runtime_snapshot_ref': sidecar('runtime.json', runtime),
              'runtime': {'compact_preview': True}}
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    loaded_results, loaded_checks = exporter._reference_evidence_sources(record, frames_dir=tmp_path)
    assert loaded_results[2]['semantic_review_evidence_binding'] == f['results'][2]['semantic_review_evidence_binding']
    assert loaded_checks == f['checks']
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    (tmp_path / 'results.json').write_text('[]\n')
    with pytest.raises(exporter.ReferenceExportError, match='verification failed'):
        exporter._reference_evidence_sources(record, frames_dir=tmp_path)


@pytest.mark.parametrize('ref', [
    {'path': '../outside.json', 'sha256': 'a'*64},
    {'path': '/tmp/outside.json', 'sha256': 'a'*64},
    {'path': 'missing.json'},
])
def test_selected_sidecar_reader_refuses_unsafe_or_unbound_sources(tmp_path, ref):
    with pytest.raises(exporter.ReferenceExportError):
        exporter._reference_evidence_sources({'runtime_snapshot_ref': ref}, frames_dir=tmp_path)
