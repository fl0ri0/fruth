"""Recorded AFM failure shapes through shared handoff owners, using temporary files."""
import copy
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from fruth_inference.request_phase_graph import build_request_phase_graph
from fruth_server.late_fill_runtime import LateFillRuntimeOwner
from fruth_server.response_semantics_runtime import (
    ResponseSemanticsRuntimeOwner,
    phase_output_defers_saved_file_materialization,
)


SAVE_READ = ('Save a read-check.json with values [178,684]. Then read the actually saved '
             'read-check.json again. Create read-check.html from the read data with a table '
             'containing both values and their sum. Return exactly these two files.')
ANIMALS = ('Create a playful series of exactly three funny animal selfies. '
           'Choose the animals, settings, poses, and visual style yourself, but make '
           'the three images clearly distinct. Then inspect each generated image separately.')


def owner_fixture():
    from tests.test_response_semantics_runtime import ResponseSemanticsRuntimeTests
    fixture = ResponseSemanticsRuntimeTests()
    fixture.setUp()
    return fixture


def test_indexed_json_image_prompts_preserve_exact_slot_payloads():
    fixture = owner_fixture()
    prompts = ['Raccoon selfie beside a river.', 'Sloth selfie in a library.',
               'Squirrel selfie on a snowy branch.']
    output = json.dumps([{f'prompt_{i}': p} for i, p in enumerate(prompts, 1)])
    semantic = fixture.owner.build_response_semantic_phase_payload(
        output_text=output, request_payload={'prompt': ANIMALS, 'inference_route': True},
        capability='chat',
    )
    assert semantic['batch_prompts'] == prompts
    assert not semantic.get('branch_contract_error')
    assert semantic['batch_prompt_expected_count'] == 3


@pytest.mark.parametrize('batch', [
    [{'prompt_1': 'A'}, {'prompt_3': 'C'}],
    [{'prompt_1': 'A'}, {'prompt_2': 'B'}, {'prompt_3': 'C'}, {'prompt_4': 'D'}],
    [{'prompt_1': 'A'}, {'prompt_2': 'A'}, {'prompt_3': 'C'}],
    [{'prompt_1': 'A'}, {'prompt_2': ''}, {'prompt_3': 'C'}],
    [{'prompt_1': 'A'}, {'prompt_2': {'instructions': 'B'}}, {'prompt_3': 'C'}],
    [{'prompt_1': 'A', 'review': 'I inspected it'}, {'prompt_2': 'B'}, {'prompt_3': 'C'}],
    [{'prompt_2': 'B'}, {'prompt_1': 'A'}, {'prompt_3': 'C'}],
    [{'room': 'A'}, {'room': 'B'}, {'room': 'C'}],
])
def test_indexed_json_image_prompts_reject_incomplete_ambiguous_or_foreign_data(batch):
    assert ResponseSemanticsRuntimeOwner({}).extract_batch_image_prompts(
        json.dumps(batch), expected_count=3,
    ) == []


def test_afm_saved_read_task_is_last_and_names_only_source_file():
    owner = ResponseSemanticsRuntimeOwner({'extract_responses_prompt': lambda p: p['prompt']})
    request = {'prompt': SAVE_READ, 'inference_route': True}
    messages = owner.inject_prepare_phase_contract_into_chat_messages(
        [{'role': 'user', 'content': SAVE_READ}], request_payload=request, backend='apple_fm',
    )
    text = messages[-1]['content']
    assert text.index('<fruth_promoted_context>') < text.index('<fruth_bounded_task>')
    task = text.split('<fruth_bounded_task>')[1]
    assert 'read-check.json' in task and 'read-check.html' not in task
    assert 'only the raw JSON source data' in task
    assert text.endswith('</fruth_bounded_task>')
    assert owner.inject_prepare_phase_contract_into_chat_messages(
        messages, request_payload=request, backend='apple_fm',
    ) == messages
    assert 'Do not add headings' not in messages[0]['content']


def test_saved_read_preparation_defers_files_but_producer_and_consumer_can_write():
    request = {'prompt': SAVE_READ, 'inference_route': True}
    graph = build_request_phase_graph(SAVE_READ, request_payload=request)
    assert phase_output_defers_saved_file_materialization(
        route_payload={'route_runtime': {'request_phase_graph': graph}},
        request_payload=request, capability='chat',
    )
    for phase in graph['phases'][1:]:
        branch_graph = copy.deepcopy(graph)
        branch_graph['current_phase_id'] = phase['phase_id']
        branch_graph['current_phase_capability'] = 'chat'
        branch_graph['current_phase_resolution'] = 'graph_resolved'
        assert not phase_output_defers_saved_file_materialization(
            route_payload={'route_runtime': {'request_phase_graph': branch_graph}},
            request_payload=request, capability='chat',
        )
    assert not phase_output_defers_saved_file_materialization(
        route_payload=None, request_payload={'prompt': 'Create index.html and styles.css.'},
        capability='chat',
    )


@pytest.mark.parametrize('stream', [False, True])
def test_saved_read_response_never_persists_a_competing_initial_file(monkeypatch, stream):
    import fruth_webserver
    from tests.fake_backends import FakeBackendHarness

    malformed = '{"read-check.json":[178,684],"read-check.html":"<table>" "</table>"}'

    class Stream:
        def iter_lines(self, **kwargs):
            yield json.dumps({'message': {'content': malformed}})
            yield '{"done":true}'

        def close(self):
            pass

    with FakeBackendHarness() as harness, monkeypatch.context() as scoped:
        # This test inspects preparation only; the harness deliberately does not
        # run deferred branches, so use the existing nonterminal test stream mode.
        scoped.setitem(fruth_webserver.app.config, 'TESTING', True)
        scoped.setattr(fruth_webserver, '_execute_chat_backend_request', lambda **kwargs: malformed)
        scoped.setattr(fruth_webserver, '_open_ollama_chat_stream', lambda **kwargs: (Stream(), 11435))
        persistence = Mock(side_effect=AssertionError('Preparation must not save a competing file'))
        scoped.setattr(fruth_webserver, '_persist_generated_text_artifact_if_requested', persistence)
        response = harness.client.post('/api/responses', json={
            'instance_id': harness.instances['chat']['instance_id'],
            'input': SAVE_READ, 'stream': stream,
            'response_id': f'resp_save_read_prepare_{stream}',
        })
        assert response.status_code == 200
        if stream:
            assert b'response.completed' in response.get_data()
        persistence.assert_not_called()
        assert not list(harness.documents_dir.iterdir())


def test_single_page_composition_rejects_gallery_then_accepts_in_place_roles(tmp_path):
    fixture = owner_fixture()
    html = tmp_path / 'index.html'
    css = tmp_path / 'styles.css'
    images = [tmp_path / 'hero.png', tmp_path / 'listening.png']
    for path in images:
        path.write_bytes(b'fixture')
    html.write_text('<html><head><link rel="stylesheet" href="styles.css"></head>'
                    '<body><div class="hero"><img src="hero.png"></div>'
                    '<section class="listening"></section>'
                    '<section class="fruth-generated-media"><img src="listening.png"></section>'
                    '</body></html>')
    css.write_text('img {max-width:100%;height:auto;}')
    payload = {'artifacts': [
        {'type': 'text', 'path': str(html), 'branch_id': 'html', 'phase_id': 'html'},
        {'type': 'text', 'path': str(css), 'branch_id': 'css', 'phase_id': 'css'},
        *[{'type': 'image', 'path': str(p), 'branch_id': f'image-{i}', 'phase_id': f'image-{i}'}
          for i, p in enumerate(images)],
    ], 'late_fill': {
        'batch_prompts': ['Hero mountain scene.', 'Listening section mountain scene.'],
        'fill_results': [
            {'branch_id': f'image-{i}', 'phase_id': f'image-{i}',
             'capability': 'image_generation', 'saved_image_path': str(p)}
            for i, p in enumerate(images)
        ],
    }}
    checks = fixture.late_fill_owner._terminal_composed_site_image_composition_open_checks(payload)
    assert len(checks) == 2
    assert checks[0]['detached_repair_section_present']
    assert checks[0]['role_binding_defects'] == [{'path': str(images[1]), 'role_label': 'listening'}]
    original = html.read_bytes()
    fixture.late_fill_owner._terminal_composed_page_image_representation_open_checks(payload)
    assert html.read_bytes() == original  # existing bounded repair path, no gallery append
    html.write_text('<html><head><link rel="stylesheet" href="styles.css"></head>'
                    '<body><div class="hero"><img src="hero.png"></div>'
                    '<section class="listening"><img src="listening.png"></section></body></html>')
    assert fixture.late_fill_owner._terminal_composed_site_image_composition_open_checks(payload) == []


def test_section_role_binding_rejects_nearby_sibling_and_accepts_css(tmp_path):
    image = str(tmp_path / 'listening.png')
    check = LateFillRuntimeOwner._terminal_composed_site_role_is_bound
    assert not check(role_label='listening', image_path=image, content_by_path={
        str(tmp_path / 'index.html'): '<section class="listening"></section><img src="listening.png">',
    })
    assert check(role_label='listening', image_path=image, content_by_path={
        str(tmp_path / 'styles.css'): '.listening-section {background-image:url("listening.png");}',
    })


def test_indexed_json_image_prompts_reject_duplicate_object_keys():
    assert ResponseSemanticsRuntimeOwner({}).extract_batch_image_prompts(
        '[{"prompt_1":"A","prompt_1":"B"},{"prompt_2":"C"},{"prompt_3":"D"}]',
        expected_count=3,
    ) == []


@pytest.mark.parametrize('image_count', [1, 2])
@pytest.mark.parametrize('style_kind', ['external', 'embedded', 'inline', 'missing'])
def test_all_html_sites_share_exact_target_composition_checks(tmp_path, image_count, style_kind):
    owner = owner_fixture().late_fill_owner
    html = tmp_path / 'index.html'
    css = tmp_path / 'styles.css'
    images = [tmp_path / f'image-{i}.png' for i in range(image_count)]
    for path in images:
        path.write_bytes(b'fixture')
    style = 'img {max-width:100%;height:auto;object-fit:cover;}'
    head = '<style>' + style + '</style>' if style_kind == 'embedded' else ''
    records = [{'type': 'text', 'path': str(html), 'branch_id': 'page'}]
    if style_kind == 'external':
        css.write_text(style)
        head = '<link rel="stylesheet" href="styles.css">'
        records.append({'type': 'text', 'path': str(css), 'branch_id': 'style'})
    records.extend({'type': 'image', 'path': str(p), 'branch_id': f'image-{i}'}
                   for i, p in enumerate(images))
    payload = {'artifacts': records, 'late_fill': {'fill_results': [
        {'capability': 'image_generation', 'branch_id': f'image-{i}', 'saved_image_path': str(p)}
        for i, p in enumerate(images)
    ]}}
    missing_source = f'<html><head>{head}</head><body><section class="gallery"></section></body></html>'
    html.write_text(missing_source)
    checks = owner._terminal_composed_page_image_representation_open_checks(payload)
    assert checks and checks[0]['missing_image_paths'] == [str(p) for p in images]
    for check in checks:
        contract = check['execution_contract']
        assert contract['repair_mode'] == 'composed_site_image_cohort_target'
        assert contract['root_prompt_replay_allowed'] is False
        assert contract['sibling_write_allowed'] is False
        assert contract['target_path'] in {str(html), str(css)}
    assert html.read_text() == missing_source
    attrs = ' style="max-width:100%;height:auto"' if style_kind == 'inline' else ''
    markup = ''.join(f'<img src="{p.name}"{attrs}>' for p in images)
    html.write_text(f'<html><head>{head}</head><body><section class="gallery">{markup}</section></body></html>')
    final_checks = owner._terminal_composed_page_image_representation_open_checks(payload)
    if style_kind == 'missing':
        assert final_checks and final_checks[0]['layout_binding_defect']
        assert not final_checks[0]['missing_image_paths']
    else:
        assert final_checks == []


@pytest.mark.parametrize('selector', ['.listening + .gallery', '.listening ~ img', ':not(.listening)', '.listeningroom'])
def test_section_role_css_does_not_bind_siblings_or_negated_roles(tmp_path, selector):
    assert not LateFillRuntimeOwner._terminal_composed_site_role_is_bound(
        role_label='listening', image_path=str(tmp_path / 'image.png'),
        content_by_path={str(tmp_path / 'styles.css'): selector + '{background:url(image.png)}'},
    )


def test_embedded_css_section_role_is_bound(tmp_path):
    assert LateFillRuntimeOwner._terminal_composed_site_role_is_bound(
        role_label='listening', image_path=str(tmp_path / 'image.png'),
        content_by_path={str(tmp_path / 'index.html'):
                        '<style>.listening {background:url(image.png)}</style><section class="listening"></section>'},
    )


def test_selfie_preparation_preserves_framing_without_leaking_to_other_workflows():
    owner = owner_fixture().owner
    for prompt, expected in [(ANIMALS, True), ('Create exactly three mountain images.', False)]:
        messages = owner.inject_prepare_phase_contract_into_chat_messages(
            [{'role': 'user', 'content': prompt}], request_payload={'prompt': prompt}, backend='apple_fm',
        )
        assert ('Every prompt must explicitly describe a selfie' in messages[-1]['content']) is expected
