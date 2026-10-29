"""Caller-scoped file exclusions through eligibility and native materialization.

Synthetic providers establish execution, saved bytes and canonical bindings,
not the visual meaning of the PNG fixtures. Run with scripts/run_tests.py.
"""
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

import fruth_webserver as web
from fruth_inference.intent import analyze_prompt_intent, materialization_is_deferred
from fruth_inference.request_phase_graph import build_request_phase_graph
from fruth_services.responses import capture_request_intent
from tests.test_generated_image_artifact_routing import semantics
from tests.test_instruction_admission_contract import real_owners, settle


REQUEST = ('Prepare two separate image prompts, then generate exactly two images: '
           'a cobalt circle and an amber triangle. Do not create other files.')
PROMPTS = [
    'A single cobalt circle centered on a clean white background, crisp flat vector illustration with no words.',
    'A single amber triangle centered on a clean white background, crisp flat vector illustration with no words.',
]


def reply(prompts):
    return '**Image Prompts**\n\n' + '\n\n'.join(
        f'**Image {i + 1} (Shape):** {prompt}' for i, prompt in enumerate(prompts))


@contextmanager
def native_owners(tmp_path, output):
    with real_owners(tmp_path, output) as harness:
        late = replace(web._LATE_FILL_RUNTIME,
            load_running_instances=harness._load_running_instances,
            merge_instances_with_runtime_status=harness._merge_instances_with_runtime_status)
        with patch.object(web, '_LATE_FILL_RUNTIME', late):
            yield harness


def text_branch(name, extension):
    return {'capability': 'chat', 'requires_artifact': True,
            'text_artifact_extension': extension, 'text_artifact_source_name': name}


@pytest.mark.parametrize('suffix', [
    '. Do not create other files.',
    '; do not save additional files.',
    "\nDon't create extra files.",
])
def test_relative_file_scope_preserves_supported_explicit_file_contracts(suffix):
    analysis = analyze_prompt_intent(
        'Generate exactly two images. Create two files: note.txt and status.json' + suffix)
    assert analysis['requested_visual_output_count'] == 2
    for index in (1, 2):
        assert not materialization_is_deferred(analysis,
            {'capability': 'image_generation', 'queue_index': index})
    assert materialization_is_deferred(analysis,
        {'capability': 'image_generation', 'queue_index': 3})
    assert materialization_is_deferred(analysis,
        {'capability': 'image_generation', 'batch_prompt_expected_count': 3})
    assert not materialization_is_deferred(analysis, text_branch('note', 'txt'))
    assert not materialization_is_deferred(analysis, text_branch('status', 'json'))
    assert materialization_is_deferred(analysis, text_branch('takeover', 'txt'))
    assert materialization_is_deferred(analysis, {'capability': 'text_to_speech'})


@pytest.mark.parametrize('ban', [
    'Do not create files.', 'Do not create any files.',
    'Do not create other files. Do not create files.',
    'Do not create files. Do not create additional files.',
    'Plan but do not materialize.',
])
def test_blanket_bans_are_not_relative_exceptions(ban):
    analysis = analyze_prompt_intent('Generate two images. Create note.txt. ' + ban)
    assert materialization_is_deferred(analysis, {'capability': 'image_generation'})
    assert materialization_is_deferred(analysis, text_branch('note', 'txt'))


@pytest.mark.parametrize('restriction,expected', [
    ('Do not create SVG.', {'note.txt', 'status.json', 'image'}),
    ('Do not create the JSON file.', {'note.txt', 'image'}),
    ('Do not create status.json.', {'note.txt', 'image'}),
    ('Do not generate the image yet.', {'note.txt', 'status.json'}),
])
def test_scoped_bans_still_take_precedence_over_relative_exceptions(semantics, restriction, expected):
    prompt = ('Generate one image. Create two files: note.txt and status.json. '
              'Do not create other files. ' + restriction)
    graph = build_request_phase_graph(prompt, request_payload={'prompt': prompt, 'inference_route': True})
    branches = semantics.extract_pending_deferred_branches(
        route_payload={'route_runtime': {'request_phase_graph': graph}})
    actual = {'image' if b['capability'] == 'image_generation' else
              b['text_artifact_source_name'] + '.' + b['text_artifact_extension'] for b in branches}
    assert actual == expected


@pytest.mark.parametrize('prompt', [
    'Do not create other files.',
    'Write two image prompts as text only. Do not generate images. Do not create other files.',
    'Plan an image, keep it as an option. Do not create additional files.',
])
def test_relative_exclusion_does_not_promote_planned_or_absent_work(semantics, prompt):
    assert materialization_is_deferred(analyze_prompt_intent(prompt), {'capability': 'image_generation'})
    graph = build_request_phase_graph(prompt, request_payload={'prompt': prompt, 'inference_route': True})
    assert not semantics.extract_pending_deferred_branches(
        route_payload={'route_runtime': {'request_phase_graph': graph}})
    assert not any(o.get('requires_artifact') and o.get('required')
                   for o in graph.get('output_obligations', []))


def test_missing_historical_exception_evidence_remains_conservative():
    analysis = analyze_prompt_intent(REQUEST)
    scope = analysis['materialization_defer_scope']
    assert scope['files'] is True
    assert scope.pop('file_exceptions')['version'] == 1
    assert materialization_is_deferred(analysis, {'capability': 'image_generation'})
    scope['file_exceptions'] = {'version': 999, 'image_generation': 2}
    assert materialization_is_deferred(analysis, {'capability': 'image_generation'})


def test_planner_text_cannot_expand_captured_count_targets_or_exception_scope():
    request = capture_request_intent({'prompt': REQUEST})
    request.update(prompt='Generate three images. Create takeover.md.',
                   batch_prompts=[*PROMPTS, 'An unrelated green square.'])
    graph = build_request_phase_graph(request['prompt'], request_payload=request)
    assert graph['prompt'] == REQUEST
    intent = graph['prompt_intent']
    assert intent['requested_visual_output_count'] == 2
    assert intent['materialization_defer_scope']['file_exceptions']['image_generation'] == 2
    assert materialization_is_deferred(intent, text_branch('takeover', 'md'))
    assert materialization_is_deferred(intent, {'capability': 'image_generation', 'queue_index': 3})
    assert not any(o.get('text_artifact_source_name') == 'takeover'
                   for o in graph['output_obligations'])


def test_relative_exclusion_saves_only_supported_named_files(tmp_path):
    from tests.test_downstream_deferral_scope import test_request_schedules_only_executable_files
    test_request_schedules_only_executable_files(
        tmp_path, 'Do not create additional files.', {'note.txt', 'status.json'}, True)


@pytest.mark.parametrize('mode', ['blanket', 'reserved', 'reserved_action'])
def test_native_blanket_or_reserved_outputs_have_no_effects(tmp_path, mode):
    prompt = (REQUEST.replace('other files', 'any files') if mode == 'blanket' else
              'Sketch a poster image idea, keep it as an option. Do not create other files.' if mode == 'reserved_action' else
              'Plan an image, keep it as an option. Do not create other files.')
    request = {'response_id': 'relative-stop-' + mode, 'prompt': prompt,
               'inference_route': True, 'developer_flags': {'embedding_signals_enabled': False}}
    record = {'request': request}
    try:
        with native_owners(tmp_path, reply(PROMPTS)) as harness:
            result, status = harness.post_response(request)
            assert status == 200
            final = settle(harness, result, request)
            calls = [c for c in harness.provider_calls if c['url'].endswith(('/api/generate', '/v1/images/generations'))]
            files = [p for folder in (harness.images_dir, harness.documents_dir, harness.audio_dir)
                     for p in folder.rglob('*') if p.is_file()]
            record.update(lifecycle=final['lifecycle_state'], image_dispatches=len(calls), files=[str(p) for p in files])
            assert not calls and not files
            if mode == 'blanket':
                assert final['lifecycle_state'] != 'completed'
    finally:
        path = Path(os.environ['FRUTH_A1_EVIDENCE_DIR']) / ('relative-stop-' + mode + '.json')
        path.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')


@pytest.mark.parametrize('extra_proposal', [False, True])
def test_native_relative_exclusion_effects_and_canonical_bindings(tmp_path, extra_proposal):
    proposed = [*PROMPTS, 'An unrelated green square centered on a white background.'] if extra_proposal else PROMPTS
    output = reply(proposed)
    if extra_proposal:
        output += '\n\nCreate takeover.md containing an additional deliverable.'
    request = {'response_id': 'relative-scope-' + str(extra_proposal), 'prompt': REQUEST,
               'inference_route': True, 'developer_flags': {'embedding_signals_enabled': False}}
    record = {'request': request, 'extra_provider_proposal': extra_proposal}
    try:
        with native_owners(tmp_path, output) as harness:
            result, status = harness.post_response(request)
            assert status == 200
            final = settle(harness, result, request)
            calls = [c for c in harness.provider_calls if c['url'].endswith(('/api/generate', '/v1/images/generations'))]
            images = list(harness.images_dir.rglob('*.png'))
            graph = final['runtime']['request_phase_graph']
            outputs = final['outputs']
            record.update(lifecycle=final['lifecycle_state'], image_prompts=[c['request']['prompt'] for c in calls],
                outputs=[{k:o.get(k) for k in ('slot_id','branch_id','phase_id','status','artifact_ref')} for o in outputs],
                images=[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in images])
            assert graph['prompt'] == REQUEST
            assert graph['prompt_intent']['requested_visual_output_count'] == 2
            assert len(calls) <= 2 and len(images) <= 2
            assert all(c['request']['prompt'] in PROMPTS for c in calls)
            assert not [p for p in harness.documents_dir.rglob('*') if p.is_file()]
            assert not [p for p in harness.audio_dir.rglob('*') if p.is_file()]
            # Extra provider prose may be discarded while both authorized
            # images complete. Its presence must not expand the saved set.
            assert [c['request']['prompt'] for c in calls] == PROMPTS
            assert len(images) == 2
            assert final['lifecycle_state'] == 'completed'
            assert len(outputs) == 3 and all(o['status'] == 'fulfilled' for o in outputs)
            materialized = [o for o in outputs if o.get('artifact_ref')]
            assert len(materialized) == 2
            assert len({o['artifact_ref'] for o in materialized}) == 2
            assert {(o['branch_id'],o['phase_id']) for o in materialized} == {
                ('branch-image_generation-1','phase-2'), ('branch-image_generation-2','phase-3')}
            artifacts = {a['artifact_ref']:a for a in final['artifacts'] if a.get('artifact_ref')}
            assert {Path(artifacts[o['artifact_ref']]['path']) for o in materialized} == set(images)
            assert all(b['depends_on'] == ['phase-1'] for b in graph['downstream_branches'])
            harness.clear_response_lookup()
            recovered = harness.response_state(final['id'])
            assert recovered['ok'] and recovered['response_payload']['outputs'] == outputs
            assert recovered['response_payload']['lifecycle_state'] == 'completed'
    finally:
        path = Path(os.environ['FRUTH_A1_EVIDENCE_DIR']) / ('relative-native-' + str(extra_proposal) + '.json')
        path.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
