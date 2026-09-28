"""Current accepted output truth must precede terminal link repair and freeze."""
import copy
import pytest

from fruth_inference.request_phase_graph import build_request_phase_graph
from fruth_server.late_fill_runtime import LateFillRuntimeOwner
from fruth_services.response_frames import build_response_frame, prepare_response_output_state
from fruth_services.responses import build_canonical_response_artifacts, hoist_response_output_surfaces
from fruth_services.tts_audio_integrity import build_tts_audio_integrity_evidence
from tests.fake_backends.fixtures import tiny_png_bytes, tiny_wav_bytes


PROMPT = ('Create index.html and styles.css. Generate one local image of a moon. '
          'Generate audio saying "Welcome home." Include the image and an audio player in the HTML.')


def scene(root):
    documents = root / 'documents'
    images = root / 'images'
    audio_dir = root / 'audio'
    for directory in (documents, images, audio_dir):
        directory.mkdir(parents=True, exist_ok=True)
    html = documents / 'index.html'
    css = documents / 'styles.css'
    image = images / 'generated-moon.png'
    audio = audio_dir / 'generated-narration.wav'
    html.write_text('<!doctype html><html><head><title>Moon</title>'
        '<link rel="stylesheet" href="styles.css"></head><body><h1>Moon</h1>'
        '<img src="moon.png" alt="Moon"><audio controls>'
        '<source src="narration.wav" type="audio/wav"></audio></body></html>')
    css.write_text('body { color: white; background: black; } img {max-width:100%;height:auto;}')
    image.write_bytes(tiny_png_bytes())
    audio.write_bytes(tiny_wav_bytes())
    request = {'prompt': PROMPT, 'inference_route': True}
    graph = build_request_phase_graph(PROMPT, request_payload=request,
        route_payload={'capability': 'chat', 'route_source': 'inference_carried'})
    branches = graph['downstream_branches']
    image_branch = next(b for b in branches if b['capability'] == 'image_generation')
    audio_branch = next(b for b in branches if b['capability'] == 'text_to_speech')
    text_branches = [b for b in branches if b.get('text_artifact_extension') in ('html', 'css')]
    assert len(text_branches) == 2
    html_branch = next(b for b in text_branches if b['text_artifact_extension'] == 'html')
    assert audio_branch['phase_id'] not in html_branch['depends_on']

    def saved(branch, path, kind):
        return {**copy.deepcopy(branch), 'status': 'fulfilled',
                'saved_' + kind + '_path': str(path),
                **({'result_text': path.read_text()} if kind == 'text' else {})}

    text_results = [saved(b, html if b['text_artifact_extension'] == 'html' else css, 'text')
                    for b in text_branches]
    initial = {'id': 'resp_terminal_output_order', 'object': 'response', 'status': 'completed',
        'capability': 'chat', 'output_text': 'Artifacts prepared.',
        'runtime': {'request_phase_graph': graph},
        'late_fill': {'status': 'pending', 'completed_branches': copy.deepcopy(text_results),
            'completed_capabilities': ['chat'],
            'pending_capabilities': ['image_generation', 'text_to_speech'],
            'pending_branches': [copy.deepcopy(image_branch), copy.deepcopy(audio_branch)],
            'fill_results': copy.deepcopy(text_results)}}
    frame = build_response_frame(initial, request_payload=request)
    initial['response_frame'] = frame
    initial = hoist_response_output_surfaces(initial)
    assert next(o for o in initial['outputs'] if o['type'] == 'audio')['status'] != 'fulfilled'
    image_result = saved(image_branch, image, 'image')
    audio_result = saved(audio_branch, audio, 'audio')
    audio_result['tts_audio_integrity_evidence'] = build_tts_audio_integrity_evidence(audio, 'Welcome home.')
    assert audio_result['tts_audio_integrity_evidence']['status'] == 'passed'
    settled = copy.deepcopy(initial)
    settled['late_fill'].update(status='completed', pending_branches=[],
        pending_capabilities=[], completed_capabilities=['chat', 'image_generation', 'text_to_speech'],
        completed_branches=[*text_results, image_result, audio_result],
        fill_results=[*text_results, image_result, audio_result])
    return request, initial, settled, html, audio, audio_branch


def resolver():
    owner = object.__new__(LateFillRuntimeOwner)
    owner.build_canonical_response_artifacts = build_canonical_response_artifacts
    return owner


def test_current_results_refresh_without_freezing_or_mutating_parent(tmp_path):
    request, initial, settled, html, audio, _ = scene(tmp_path)
    original = copy.deepcopy(settled)
    stale_records = resolver()._collect_link_rebind_artifact_records(settled)
    assert not any(r.get('_link_rebind_public_output') and r.get('path') == str(audio)
                   for r in stale_records)
    prepared = prepare_response_output_state(settled, request_payload=request)
    updated = {**settled, 'outputs': prepared['outputs']}
    assert settled == original
    assert updated['response_frame'] == initial['response_frame']
    expected = build_response_frame(settled, request_payload=request)
    assert updated['outputs'] == expected['output']['outputs']
    audio_output = next(o for o in updated['outputs'] if o['type'] == 'audio')
    assert audio_output['status'] == 'fulfilled'
    records = resolver()._collect_link_rebind_artifact_records(updated)
    assert any(r.get('_link_rebind_public_output') and r.get('path') == str(audio) for r in records)
    assert 'narration.wav' in html.read_text()  # Preparation itself never writes artifacts.


@pytest.mark.parametrize('outcome', ['failed', 'cancelled', 'waived', 'superseded'])
def test_terminal_controls_do_not_publish_saved_audio(tmp_path, outcome):
    request, _, settled, _, audio, branch = scene(tmp_path)
    lf = settled['late_fill']
    lf['completed_branches'] = [b for b in lf['completed_branches'] if b['branch_id'] != branch['branch_id']]
    lf['fill_results'] = [b for b in lf['fill_results'] if b['branch_id'] != branch['branch_id']]
    key = 'failed_branches' if outcome == 'failed' else 'cancelled_branches'
    lf[key] = [{**branch, 'status': outcome, 'error': {'code': 'TEST_REJECTED'}}]
    # Retain the rejected file as diagnostic evidence; existence cannot publish it.
    settled['artifacts'].append({'type': 'audio', 'path': str(audio),
        'branch_id': branch['branch_id'], 'phase_id': branch['phase_id']})
    prepared = prepare_response_output_state(settled, request_payload=request)
    updated = {**settled, 'outputs': prepared['outputs']}
    records = resolver()._collect_link_rebind_artifact_records(updated)
    assert not any(r.get('_link_rebind_public_output') and r.get('path') == str(audio) for r in records)


@pytest.mark.parametrize('current_status', ['empty', 'pending', 'blocked', 'failed', 'compatibility'])
def test_current_outputs_override_stale_frozen_output_claim(tmp_path, current_status):
    audio = tmp_path / 'old.wav'
    audio.write_bytes(tiny_wav_bytes())
    artifact = {'type': 'audio', 'path': str(audio), 'artifact_ref': 'artifact:old-audio'}
    outputs = [] if current_status == 'empty' else [{**artifact, 'status': current_status}]
    if current_status == 'compatibility':
        outputs[0].update(status='fulfilled', compatibility_derived=True)
    payload = {'id': 'current-output-precedence', 'artifacts': [artifact], 'outputs': outputs,
        'response_frame': {'output': {'outputs': [{**artifact, 'status': 'fulfilled'}]}}}
    records = resolver()._collect_link_rebind_artifact_records(payload)
    assert not any(r.get('_link_rebind_public_output') for r in records)


def test_terminal_contract_rebinds_before_freeze_and_bundle(tmp_path, monkeypatch):
    import fruth_webserver
    from tests.fake_backends import FakeBackendHarness
    from fruth_services.response_artifact_bundles import bundle_response_artifacts

    with FakeBackendHarness(root=tmp_path / 'runtime') as harness:
        request, initial, settled, html, audio, _ = scene(harness.artifacts_dir)
        parent = harness.freeze_manual_response(initial, request_payload=request)
        ledger = harness.response_frames_dir / 'responses.jsonl'
        parent_bytes = ledger.read_bytes()
        settled['response_frame'] = copy.deepcopy(parent['response_frame'])
        original_parent = copy.deepcopy(settled['response_frame'])
        runtime = fruth_webserver._LATE_FILL_RUNTIME
        monkeypatch.setitem(fruth_webserver.app.config, 'TESTING', True)
        with fruth_webserver.app.app_context():
            updated, status = runtime.finalize_terminal_materialization_contract(settled,
                request_payload=request, route_payload=None, artifact_gap=None, terminal_status='completed')
        assert status == 'completed', updated['late_fill']
        assert updated['late_fill']['final_materialization_contract_status'] == 'fulfilled'
        assert updated['response_frame'] == original_parent
        # Saved-text refresh may update HTML content. New media handles remain
        # private to binding until the ordinary frame publishes them.
        assert [o for o in updated['outputs'] if o['type'] in ('audio', 'image')] == [
            o for o in settled['outputs'] if o['type'] in ('audio', 'image')]
        assert ledger.read_bytes() == parent_bytes
        assert f'src="../audio/{audio.name}"' in html.read_text()
        rebinds = copy.deepcopy(updated['late_fill']['linked_artifact_rebinds'])
        before = (html.read_bytes(), html.stat().st_mtime_ns)
        again = runtime.rebind_terminal_linked_artifacts(updated)
        assert again['late_fill']['linked_artifact_rebinds'] == rebinds
        assert (html.read_bytes(), html.stat().st_mtime_ns) == before
        monkeypatch.setitem(fruth_webserver.app.config, 'TESTING', False)
        final = harness.freeze_manual_response(updated, request_payload=request)
        assert final['lifecycle_state'] == 'completed'
        assert final['runtime']['graph_closure_review']['status'] == 'fulfilled'
        assert ledger.read_bytes().startswith(parent_bytes)
        recovered = harness.response_state(final['id'])['response_payload']
        assert recovered['late_fill']['final_materialization_contract_status'] == 'fulfilled'
        bundle = bundle_response_artifacts(recovered, bundle_root=tmp_path / 'bundles')
        assert bundle['link_check']['status'] == 'passed', bundle['link_check']
        assert not fruth_webserver._RESPONSE_LATE_FILL_IN_FLIGHT


def test_worker_links_new_audio_after_lightweight_progress(tmp_path, monkeypatch):
    import fruth_webserver
    from tests.fake_backends import FakeBackendHarness
    from fruth_services.response_artifact_bundles import bundle_response_artifacts

    with FakeBackendHarness(root=tmp_path / 'runtime') as harness:
        request, initial, _, html, _, audio_branch = scene(harness.artifacts_dir)
        parent = harness.freeze_manual_response(initial, request_payload=request)
        parent_bytes = (harness.response_frames_dir / 'responses.jsonl').read_bytes()
        settled = copy.deepcopy(initial)
        settled['response_frame'] = copy.deepcopy(parent['response_frame'])
        original_parent = copy.deepcopy(settled['response_frame'])
        branch = {**audio_branch, 'content_payload': 'Welcome home.',
                  'content_payload_source': 'current_turn_direct_spoken_clause'}
        image_branch = next(b for b in settled['late_fill']['pending_branches']
                            if b['capability'] == 'image_generation')
        image_branch = {**image_branch, 'content_payload': 'A moon over an empty landscape.',
                        'artifact_prompt': 'A moon over an empty landscape.',
                        'content_payload_source': 'current_turn_explicit_image_prompt'}
        pending = [image_branch, branch]
        lf = settled['late_fill']
        lf.update(status='pending', pending_branches=pending,
                  pending_capabilities=['image_generation', 'text_to_speech'])
        runtime = fruth_webserver._LATE_FILL_RUNTIME
        for instance in harness.instances.values():
            instance['runtime_status'].update(process_alive=True, port_listening=True)
        monkeypatch.setattr(runtime, 'load_running_instances', lambda: list(harness.instances.values()))
        monkeypatch.setattr(runtime, 'merge_instances_with_runtime_status', lambda entries, **kw: entries)
        monkeypatch.setitem(fruth_webserver.app.config, 'TESTING', True)
        with fruth_webserver.app.app_context():
            runtime.complete_response_late_fill(response_payload=settled, request_payload=request,
                assistant_message=settled['output_text'], artifact_gap={
                    'trigger': 'execution_planner_deferred_follow_up',
                    'pending_branches': pending,
                    'pending_capabilities': ['image_generation', 'text_to_speech'],
                    'expected_capability': 'text_to_speech'}, source_route_payload=None)
        final = runtime.get_response_lookup_record(settled['id'])['response_payload']
        assert harness.calls['text_to_speech'] == 1
        assert harness.calls['chat'] == 0 and harness.calls['image_generation'] == 1
        assert final['lifecycle_state'] == 'completed', final['late_fill']
        assert final['late_fill']['final_materialization_contract_status'] == 'fulfilled'
        assert final['runtime']['graph_closure_review']['status'] == 'fulfilled'
        assert 'src="../audio/speech.wav"' in html.read_text()
        assert settled['response_frame'] == original_parent
        assert (harness.response_frames_dir / 'responses.jsonl').read_bytes() == parent_bytes
        monkeypatch.setitem(fruth_webserver.app.config, 'TESTING', False)
        persisted = harness.freeze_manual_response(final, request_payload=request)
        recovered = harness.response_state(persisted['id'])['response_payload']
        assert recovered['late_fill']['final_materialization_contract_status'] == 'fulfilled'
        bundle = bundle_response_artifacts(recovered, bundle_root=tmp_path / 'bundles')
        assert bundle['link_check']['status'] == 'passed', bundle['link_check']
        assert not fruth_webserver._RESPONSE_LATE_FILL_IN_FLIGHT
