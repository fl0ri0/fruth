"""Link duties are consumer contracts; candidate assets do not create duties."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

import pytest

import fruth_webserver as web
from tests.fake_backends.fixtures import tiny_png_bytes
from tests.test_instruction_admission_contract import settle
from tests.test_relative_file_exclusion import native_owners, reply, PROMPTS


def linked_payload(tmp_path, extension='html', *, contract='local_visual_asset_binding'):
    image = tmp_path / 'accepted.png'
    image.write_bytes(tiny_png_bytes())
    consumer = tmp_path / ('consumer.' + extension)
    consumer.write_text('{"status":"ok"}' if extension == 'json' else '<html>Complete.</html>')
    source = {'branch_id': 'branch-image', 'phase_id': 'phase-image',
              'capability': 'image_generation', 'output_type': 'image'}
    target = {'branch_id': 'branch-consumer', 'phase_id': 'phase-consumer',
              'capability': 'chat', 'output_type': 'text', 'requires_artifact': True,
              'depends_on': ['phase-image'], 'dependency_contract': contract}
    artifacts = [
        {**source, 'type': 'image', 'path': str(image), 'artifact_ref': 'artifact:image'},
        {**target, 'type': 'text', 'path': str(consumer), 'artifact_ref': 'artifact:consumer'},
    ]
    for artifact in artifacts:
        artifact.update(source_response_id='response-links', status='fulfilled')
    payload = {'id': 'response-links', 'artifacts': artifacts,
               'outputs': [dict(a, status='fulfilled') for a in artifacts],
               'runtime': {'request_phase_graph': {'phases': [source, target]}}}
    return payload, image, consumer


@pytest.mark.parametrize('extension', ['html', 'json'])
@pytest.mark.parametrize('dependency_kind', ['none', 'preparation', 'ordering', 'saved_file_read_required'])
def test_independent_ordered_and_read_consumers_do_not_owe_links(tmp_path, extension, dependency_kind):
    payload, _, consumer = linked_payload(tmp_path, extension, contract=dependency_kind)
    if dependency_kind == 'preparation':
        for item in [payload['artifacts'][1], payload['runtime']['request_phase_graph']['phases'][1]]:
            item['depends_on'] = ['phase-preparation']
        payload['runtime']['request_phase_graph']['phases'].append(
            {'phase_id': 'phase-preparation', 'capability': 'chat', 'output_type': 'text'})
    before = consumer.read_bytes()
    assert not web._LATE_FILL_RUNTIME._terminal_linked_artifact_contract_required(payload)
    assert web._LATE_FILL_RUNTIME._terminal_linked_artifact_contract_is_fulfilled(payload)
    assert consumer.read_bytes() == before


@pytest.mark.parametrize('extension', ['html', 'json'])
@pytest.mark.parametrize('link', ['exact', 'omitted', 'empty', 'broken', 'foreign_path', 'sibling_only', 'prose_only'])
def test_declared_link_is_owed_and_bound_to_its_consumer(tmp_path, extension, link):
    payload, image, consumer = linked_payload(tmp_path, extension)
    foreign = tmp_path / 'foreign'
    foreign.mkdir()
    (foreign / image.name).write_bytes(image.read_bytes())
    url = {'exact': image.name, 'broken': 'missing.png',
           'foreign_path': 'foreign/' + image.name}.get(link)
    if url:
        consumer.write_text(json.dumps({'imagePath': url}) if extension == 'json'
                            else '<html><img src="' + url + '"></html>')
    if link == 'prose_only':
        consumer.write_text(json.dumps({'description': image.name}) if extension == 'json'
                            else '<html><p>' + image.name + '</p></html>')
    if link == 'sibling_only':
        sibling = tmp_path / 'sibling.html'
        sibling.write_text('<img src="accepted.png">')
        payload['artifacts'].append({'type': 'text', 'path': str(sibling)})
    if link == 'empty':
        consumer.write_text('')
        sibling = tmp_path / 'independent.html'
        sibling.write_text('<p>Independent result.</p>')
        payload['artifacts'].append({'type': 'text', 'path': str(sibling)})
    assert web._LATE_FILL_RUNTIME._terminal_linked_artifact_contract_required(payload)
    assert web._LATE_FILL_RUNTIME._terminal_linked_artifact_contract_is_fulfilled(payload) == (link == 'exact')


@pytest.mark.parametrize('fault', ['foreign_response', 'wrong_branch', 'wrong_phase', 'missing', 'unpublished'])
def test_declared_link_requires_the_accepted_producer(tmp_path, fault):
    payload, image, consumer = linked_payload(tmp_path)
    consumer.write_text('<img src="accepted.png">')
    producer = payload['artifacts'][0]
    if fault == 'foreign_response':
        producer['source_response_id'] = 'other-response'
    elif fault == 'wrong_branch':
        producer['branch_id'] = 'wrong-branch'
    elif fault == 'wrong_phase':
        producer['phase_id'] = 'wrong-phase'
    elif fault == 'missing':
        image.unlink()
    else:
        payload['outputs'] = payload['outputs'][1:]
    # Do not leave a clean duplicate of the faulted record on the public surface.
    if fault != 'unpublished':
        payload['outputs'][0] = deepcopy(producer)
    assert not web._LATE_FILL_RUNTIME._terminal_linked_artifact_contract_is_fulfilled(payload)


@pytest.mark.parametrize('extension', ['html', 'json'])
def test_unrelated_sibling_is_not_another_link_dependency(tmp_path, extension):
    payload, image, consumer = linked_payload(tmp_path, extension)
    consumer.write_text(json.dumps({'imagePath': image.name}) if extension == 'json'
                        else '<img src="accepted.png">')
    sibling = tmp_path / 'independent.png'
    sibling.write_bytes(image.read_bytes())
    payload['artifacts'].append({'type': 'image', 'path': str(sibling),
                                'branch_id': 'other', 'phase_id': 'other-phase'})
    assert web._LATE_FILL_RUNTIME._terminal_linked_artifact_contract_is_fulfilled(payload)


@pytest.mark.parametrize('extension', ['html', 'json'])
@pytest.mark.parametrize('exists', [True, False])
def test_actual_local_reference_is_checked_without_a_declared_link_duty(tmp_path, extension, exists):
    payload, image, consumer = linked_payload(tmp_path, extension, contract='ordering')
    consumer.write_text(json.dumps({'imagePath': image.name}) if extension == 'json'
                        else '<img src="accepted.png">')
    if not exists:
        image.unlink()
    assert web._LATE_FILL_RUNTIME._terminal_linked_artifact_contract_required(payload)
    assert web._LATE_FILL_RUNTIME._terminal_linked_artifact_contract_is_fulfilled(payload) == exists


def test_saved_stylesheet_can_expose_the_pages_declared_image(tmp_path):
    payload, image, consumer = linked_payload(tmp_path)
    stylesheet = tmp_path / 'style.css'
    stylesheet.write_text('body { background-image: url(accepted.png); }')
    consumer.write_text('<link rel="stylesheet" href="style.css">')
    payload['artifacts'].append({'type': 'text', 'path': str(stylesheet)})
    assert web._LATE_FILL_RUNTIME._terminal_linked_artifact_contract_is_fulfilled(payload)


@pytest.mark.parametrize('linked', [True, False])
def test_stylesheet_visual_cohort_uses_only_its_linked_page(tmp_path, linked):
    payload, image, consumer = linked_payload(tmp_path)
    stylesheet = tmp_path / 'style.css'
    stylesheet.write_text('img { max-width: 100%; }')
    consumer.write_text(('<link rel="stylesheet" href="style.css">' if linked else '')
                        + '<img src="accepted.png">')
    css = {'type': 'text', 'path': str(stylesheet), 'branch_id': 'branch-css',
           'phase_id': 'phase-css', 'dependency_contract': 'local_visual_asset_binding',
           'depends_on': ['phase-image']}
    payload['artifacts'].append(css)
    payload['runtime']['request_phase_graph']['phases'].append(css)
    assert web._LATE_FILL_RUNTIME._terminal_linked_artifact_contract_is_fulfilled(payload) == linked


def test_native_linked_html_completes_and_recovers(tmp_path):
    extension = 'html'
    name = 'linked.html'
    prompt = ('Generate exactly two images. Create ' + name
              + ' referencing both generated images by their local image paths.')
    generated_body = []

    def provider(call, index):
        if index == 1:
            return reply(PROMPTS)
        images = sorted((tmp_path / 'artifacts/images').glob('*.png'))
        assert len(images) == 2
        paths = ['../images/' + p.name for p in images]
        body = ('<!doctype html><html><head><style>img{max-width:100%;height:auto;}</style></head><body>' + ''.join(
                    '<img src="' + path + '">' for path in paths) + '</body></html>')
        generated_body.append(body.encode() + b'\n')
        return '```' + extension + '\n' + body + '\n```'

    evidence = {'prompt': prompt, 'extension': extension}
    try:
        with native_owners(tmp_path, provider) as harness:
            request = {'prompt': prompt, 'inference_route': True,
                       'developer_flags': {'embedding_signals_enabled': False}}
            initial, status = harness.post_response(request)
            assert status == 200
            final = settle(harness, initial, request)
            graph = final['runtime']['request_phase_graph']
            consumer = next(b for b in graph['downstream_branches'] if b.get('requires_artifact'))
            assert consumer['dependency_contract'] == 'local_visual_asset_binding'
            assert len(consumer['depends_on']) == 2
            files = [p for p in harness.documents_dir.rglob('*') if p.is_file()]
            images = list(harness.images_dir.rglob('*.png'))
            evidence.update(lifecycle=final['lifecycle_state'],
                            closure=final['runtime']['graph_closure_review']['status'],
                            terminal=final['late_fill'].get('final_materialization_contract_status'),
                            consumer=consumer, outputs=final['outputs'],
                            checks=final['late_fill'].get('materialization_contract_open_checks'),
                            pending=[{k:b.get(k) for k in ('branch_id','content_payload_source','status')}
                                     for b in final['late_fill'].get('pending_branches',[])])
            assert len(files) == 1 and len(images) == 2
            assert files[0].read_bytes() == generated_body[-1]
            assert all(p.read_bytes() == tiny_png_bytes() for p in images)
            assert [c['request']['prompt'] for c in harness.provider_calls
                    if c['url'].endswith(('/api/generate','/v1/images/generations'))] == PROMPTS
            outputs = [o for o in final['outputs'] if o.get('artifact_ref')]
            assert len(outputs) == len({o['artifact_ref'] for o in outputs}) == 3
            assert all(o['status'] == 'fulfilled' for o in outputs)
            assert final['lifecycle_state'] == 'completed'
            assert evidence['closure'] == 'fulfilled' and evidence['terminal'] == 'fulfilled'
            harness.clear_response_lookup()
            recovered = harness.response_state(final['id'])['response_payload']
            assert recovered['outputs'] == final['outputs']
            assert recovered['lifecycle_state'] == 'completed'
            assert recovered['runtime']['graph_closure_review']['status'] == 'fulfilled'
            assert recovered['late_fill']['final_materialization_contract_status'] == 'fulfilled'
            evidence['recovered'] = 'completed'
            evidence['files'] = [{'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                                 for p in files + images]
    finally:
        destination = Path(os.environ['FRUTH_A1_EVIDENCE_DIR']) / ('link-consumer-' + extension + '.json')
        destination.write_text(json.dumps(evidence, indent=2, sort_keys=True) + '\n')


@pytest.mark.parametrize('omit_manifest_links', [False, True])
def test_native_html_and_manifest_link_contracts_recover(tmp_path, omit_manifest_links):
    prompt = ('Generate exactly two local images. Create linked.html and manifest.json. '
              'The HTML and JSON must link both saved local images.')
    bodies = {}

    def provider(call, index):
        if index == 1:
            return reply(PROMPTS)
        images = sorted((tmp_path / 'artifacts/images').glob('*.png'))
        assert len(images) == 2
        paths = ['../images/' + p.name for p in images]
        html = ('<!doctype html><html><head><style>img{max-width:100%;height:auto;}</style>'
                '</head><body>' + ''.join('<img src="' + path + '">' for path in paths)
                + '</body></html>')
        manifest = json.dumps({'status': 'ok'} if omit_manifest_links else {'imagePaths': paths})
        bodies.update(html=html.encode() + b'\n', json=manifest.encode() + b'\n')
        return '```html\n' + html + '\n```\n\n```json\n' + manifest + '\n```'

    evidence = {'prompt': prompt, 'omit_manifest_links': omit_manifest_links}
    try:
        with native_owners(tmp_path, provider) as harness:
            request = {'prompt': prompt, 'inference_route': True,
                       'developer_flags': {'embedding_signals_enabled': False}}
            initial, status = harness.post_response(request)
            assert status == 200
            final = settle(harness, initial, request)
            consumers = [b for b in final['runtime']['request_phase_graph']['downstream_branches']
                         if b.get('requires_artifact')]
            assert len(consumers) == 2
            assert all(b['dependency_contract'] == 'local_visual_asset_binding'
                       and len(b['depends_on']) == 2 for b in consumers)
            files = [p for p in harness.documents_dir.rglob('*') if p.is_file()]
            images = list(harness.images_dir.rglob('*.png'))
            assert len(files) == 2 and len(images) == 2
            assert all(p.read_bytes() == bodies[p.suffix[1:]] for p in files)
            assert all(p.read_bytes() == tiny_png_bytes() for p in images)
            assert [c['request']['prompt'] for c in harness.provider_calls
                    if c['url'].endswith(('/api/generate','/v1/images/generations'))] == PROMPTS
            outputs = [o for o in final['outputs'] if o.get('artifact_ref')]
            assert len(outputs) == len({o['artifact_ref'] for o in outputs}) == 4
            assert web._LATE_FILL_RUNTIME._terminal_linked_artifact_contract_required(final)
            assert web._LATE_FILL_RUNTIME._terminal_linked_artifact_contract_is_fulfilled(final) is not omit_manifest_links
            expected_terminal = 'unmet' if omit_manifest_links else 'fulfilled'
            evidence.update(lifecycle=final['lifecycle_state'],
                            closure=final['runtime']['graph_closure_review']['status'],
                            terminal=final['late_fill'].get('final_materialization_contract_status'),
                            checks=final['late_fill'].get('materialization_contract_open_checks'),
                            outputs=outputs)
            assert evidence['terminal'] == expected_terminal
            if omit_manifest_links:
                assert final['lifecycle_state'] != 'completed'
                assert any(c.get('evidence') == 'unresolved_linked_artifact_binding'
                           for c in evidence['checks'])
            else:
                assert final['lifecycle_state'] == 'completed'
                assert evidence['closure'] == 'fulfilled'
                assert all(o['status'] == 'fulfilled' for o in outputs)
            harness.clear_response_lookup()
            recovered = harness.response_state(final['id'])['response_payload']
            assert recovered['outputs'] == final['outputs']
            assert recovered['lifecycle_state'] == final['lifecycle_state']
            assert recovered['runtime']['graph_closure_review']['status'] == evidence['closure']
            assert recovered['late_fill']['final_materialization_contract_status'] == expected_terminal
            assert all(p.read_bytes() == bodies[p.suffix[1:]] for p in files)
            evidence['recovered_lifecycle'] = recovered['lifecycle_state']
            evidence['files'] = [{'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                                 for p in files + images]
    finally:
        destination = Path(os.environ['FRUTH_A1_EVIDENCE_DIR']) / (
            'html-manifest-' + ('omitted' if omit_manifest_links else 'linked') + '.json')
        destination.write_text(json.dumps(evidence, indent=2, sort_keys=True) + '\n')


