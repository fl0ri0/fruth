"""Bare named-file intake, separate from execution permission and fulfillment."""
from copy import deepcopy
import json
import os
from pathlib import Path

import pytest

from fruth_core import inference
from fruth_inference.intent import analyze_prompt_intent, materialization_is_deferred
from fruth_inference.request_phase_graph import build_request_phase_graph
from fruth_services.responses import capture_request_intent, request_intent_payload
from tests.test_generated_image_artifact_routing import semantics
from tests.test_explicit_file_contract_preservation import obligation_identities
from tests.test_relative_file_exclusion import text_branch


BASE = 'Generate exactly two images. Create note.txt. Create status.json.'
REQUEST = BASE + ' Do not create other files.'
FILES = {('note', 'txt'), ('status', 'json')}


def identities(requests):
    return {(r['source_name'], r['extension']) for r in requests}


def test_original_contrast_without_exclusion():
    assert identities(inference.detect_text_artifact_requests(BASE)) == FILES
    assert identities(inference.detect_text_artifact_requests(
        'Create note.txt. Create status.json.')) == FILES


@pytest.mark.parametrize('suffix', [
    ' Do not create other files.',
    ' Do not create additional files.',
    ' Do not create extra files.',
    '; do not save additional files.',
    "\nDon't create extra files.",
    ' Do not create other files. Do not create SVG.',
])
def test_named_commands_survive_relative_exclusions(suffix):
    prompt = BASE.rstrip('.') + ('.' if suffix.startswith(' ') else '') + suffix
    requests = inference.detect_text_artifact_requests(prompt)
    assert identities(requests) == FILES
    assert all(r['source'] == 'explicit_extension' for r in requests)
    intent = analyze_prompt_intent(prompt)
    assert intent['materialization_defer_scope']['files'] is True
    for name, extension in FILES:
        assert not materialization_is_deferred(intent, text_branch(name, extension))
    assert materialization_is_deferred(intent, text_branch('unrequested', 'txt'))
    assert materialization_is_deferred(intent, text_branch('unrequested', 'json'))


@pytest.mark.parametrize('prompt', [
    'Do not create other files.',
    'Do not save additional files.',
    "Don't create extra files.",
    'Plan note.txt and status.json. Do not create other files.',
    'Keep note.txt and status.json as reserved options. Do not create other files.',
    'Explain "Create note.txt. Create status.json." Do not create other files.',
    'Example: `Create note.txt. Create status.json.` Do not create other files.',
    'Example:\n```text\nCreate note.txt. Create status.json.\n```\nDo not create other files.',
    'Generate exactly two images. Example: "Create note.txt. Create status.json." Do not create other files.',
])
def test_exclusions_and_reference_names_supply_no_file_duty(prompt):
    assert inference.detect_text_artifact_requests(prompt) == []


@pytest.mark.parametrize('restriction,expected', [
    ('Do not create files.', set()),
    ('Do not create any files.', set()),
    ('Do not create other files. Do not create any files.', set()),
    ('Plan but do not materialize.', set()),
    ('Do not create the JSON file.', {('note', 'txt')}),
    ('Do not create status.json.', {('note', 'txt')}),
    ('Do not generate the images yet.', FILES),
])
def test_recognized_duties_are_separate_from_execution_restrictions(semantics, restriction, expected):
    prompt = BASE + ' ' + restriction
    assert identities(inference.detect_text_artifact_requests(prompt)) == FILES
    graph = build_request_phase_graph(prompt, request_payload={'prompt': prompt, 'inference_route': True})
    assert obligation_identities(graph) == FILES
    branches = semantics.extract_pending_deferred_branches(
        route_payload={'route_runtime': {'request_phase_graph': graph}})
    assert {(b['text_artifact_source_name'], b['text_artifact_extension'])
            for b in branches if b.get('text_artifact_extension')} == expected


def test_prepared_text_cannot_expand_caller_named_duties():
    request = capture_request_intent({'prompt': REQUEST})
    original = deepcopy(request)
    request['prompt'] = 'Create note.txt. Create status.json. Create unrequested.txt.'
    graph = build_request_phase_graph(request['prompt'], request_payload=request)
    assert graph['prompt'] == REQUEST
    files = graph['prompt_intent']['materialization_defer_scope']['file_exceptions']['text_artifacts']
    assert identities(files) == FILES
    assert not any(o.get('text_artifact_source_name') == 'unrequested'
                   for o in graph['output_obligations'])
    assert request_intent_payload(request) == request_intent_payload(original)


@pytest.mark.parametrize('exception_version', [None, 999])
def test_named_files_cannot_recover_missing_or_unknown_exception_authority(exception_version):
    intent = analyze_prompt_intent(REQUEST)
    scope = intent['materialization_defer_scope']
    if exception_version is None:
        scope.pop('file_exceptions')
    else:
        scope['file_exceptions']['version'] = exception_version
    for name, extension in FILES:
        assert materialization_is_deferred(intent, text_branch(name, extension))


def test_relative_exclusion_preserves_an_explicit_selected_target(tmp_path):
    target = str(tmp_path / 'styles.css')
    requests = inference.detect_text_artifact_requests(
        'Update styles.css for the visualizer. Do not create other files.',
        source_available=True, source_extension='css', source_name='styles', source_path=target)
    assert requests == [{'source_name': 'styles', 'extension': 'css',
                         'source': 'selected_source_edit', 'target_path': target}]


def test_record_intake_trace():
    records = []
    for prompt in (BASE, REQUEST, 'Create two files: note.txt and status.json. Do not create other files.'):
        negations = list(inference._TEXT_ARTIFACT_NEGATION_RE.finditer(prompt))
        records.append({'prompt': prompt,
            'negation_spans': [m.group() for m in negations],
            'positive_outside_negation': inference._text_artifact_prompt_has_positive_request_outside_negation(prompt, negations),
            'early_negated': inference._text_artifact_prompt_is_negated(prompt),
            'files': inference.detect_text_artifact_requests(prompt)})
    (Path(os.environ['FRUTH_A1_EVIDENCE_DIR']) / 'intake-trace.json').write_text(json.dumps(records, indent=2) + '\n')
