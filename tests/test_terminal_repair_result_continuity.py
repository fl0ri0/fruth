"""Accepted result history must not become a fresh repair submission."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import threading

import pytest

import fruth_webserver as web
from fruth_server.responses_runtime import ResponseMutationConflict


def site_fixture(tmp_path):
    from tests.test_responses_api import ResponsesApiTests as _SiteFixtures
    return _SiteFixtures()._terminal_materialization_contract_payload_with_stale_open_checks(tmp_path)


def retained_fields(value):
    """Persisted frames omit empty optional fields; every nonempty field matters."""
    if isinstance(value, dict):
        return {k: retained_fields(v) for k, v in value.items() if v not in (None, '', [], {})}
    if isinstance(value, list):
        return [retained_fields(v) for v in value]
    return value


def test_historical_result_survives_terminal_materialization(tmp_path):
    prompt, graph, candidate, target, _, _ = site_fixture(tmp_path)
    old_text = '<html><body>Earlier accepted version.</body></html>'
    historical = {
        'branch_id': 'repair-chat', 'phase_id': 'repair-chat', 'capability': 'chat',
        'saved_text_path': str(target), 'path': str(target), 'type': 'text',
        'artifact_ref': 'artifact:index', 'text_artifact_extension': 'html',
        'content': old_text, 'result_text': old_text,
        'file_sha256': hashlib.sha256(old_text.encode()).hexdigest(),
    }
    candidate['late_fill']['fill_results'].insert(0, deepcopy(historical))
    # The current file and current branch result belong to the later repair.
    # The historical branch is deliberately absent from the current graph.
    current = deepcopy(candidate)
    current['late_fill']['status'] = 'pending'
    current['late_fill']['fill_results'] = [deepcopy(historical)]
    owner = replace(web._LATE_FILL_RUNTIME,
                    get_response_lookup_record=lambda _: {'response_payload': current})
    final, status = owner.finalize_terminal_materialization_contract(
        candidate, request_payload={'inference_route': True, 'prompt': prompt},
        route_payload={'route_runtime': {'request_phase_graph': graph}},
        artifact_gap={'expected_capability': 'chat'}, terminal_status='completed',
        accepted_fill_results=current['late_fill']['fill_results'])
    with owner._late_fill_publication(final, expected_payload=current):
        pass
    assert final['late_fill']['fill_results'][0] == historical
    assert final['late_fill']['final_materialization_contract_status'] == 'fulfilled'
    assert status == 'completed'
    assert current['late_fill']['fill_results'] == [historical]


@pytest.mark.parametrize('fault', ['absent', 'phase', 'cancelled'])
def test_new_result_still_requires_current_target(fault):
    branch = {'branch_id': 'repair-new', 'phase_id': 'phase-new', 'capability': 'chat'}
    current = {'id': 'target-fixture', 'late_fill': {'active_branches': [deepcopy(branch)]}}
    candidate = deepcopy(current)
    result = {**branch, 'result_text': 'New work.'}
    if fault == 'absent':
        result['branch_id'] = 'historical-only'
    elif fault == 'phase':
        result['phase_id'] = 'wrong-phase'
    else:
        current['late_fill']['branch_controls'] = [
            {**branch, 'status': 'cancelled', 'action': 'cancel'}]
        current['late_fill']['cancelled_branches'] = [{**branch, 'status': 'cancelled'}]
        candidate = deepcopy(current)
    candidate['late_fill']['fill_results'] = [result]
    owner = replace(web._LATE_FILL_RUNTIME,
                    get_response_lookup_record=lambda _: {'response_payload': current})
    with pytest.raises(ResponseMutationConflict):
        with owner._late_fill_publication(candidate, expected_payload=current):
            pytest.fail('foreign/stale result reached publication')


def missing_image_fixture(tmp_path):
    prompt, graph, payload, html, css, images = site_fixture(tmp_path)
    original = html.read_text()
    html.write_text(original.replace(f'<img src="../images/{images[0].name}" alt="Nocturne 1">', ''))
    return prompt, graph, payload, html, css, original


def test_replaced_repair_contract_is_not_left_executable(tmp_path):
    prompt, graph, payload, _, _, _ = missing_image_fixture(tmp_path)
    owner = web._LATE_FILL_RUNTIME
    queued, status = owner.finalize_terminal_materialization_contract(
        payload, request_payload={'inference_route': True, 'prompt': prompt},
        route_payload={'route_runtime': {'request_phase_graph': graph}},
        artifact_gap={'expected_capability': 'chat'}, terminal_status='completed')
    assert status == 'pending'
    late = queued['late_fill']
    current_contracts = {b['repair_contract_id'] for b in late['pending_branches']}
    promoted = late['repair_loop']['promoted_contracts']
    assert {c['contract_id'] for c in promoted} == current_contracts
    retired = late['repair_loop']['superseded_contracts']
    assert len(retired) == 1
    assert retired[0]['contract_id'] == 'repair-contract-branch-text_artifact-1'
    assert retired[0]['status'] == 'superseded'
    assert retired[0]['supersession_evidence']['replacement_contract_id'] in current_contracts
    assert retired[0]['content_payload'], 'original obligation text must remain inspectable'


def test_same_path_unrelated_contract_is_not_retired(tmp_path, monkeypatch):
    prompt, graph, payload, _, _, _ = missing_image_fixture(tmp_path)
    requests = web._RESPONSES_REQUEST_RUNTIME
    original = requests._inference_repair_feedback_gap

    def with_extra_contract(*args, **kwargs):
        gap = original(*args, **kwargs)
        if gap and (gap.get('repair_loop') or {}).get('promoted_contracts'):
            foreign = deepcopy(gap['repair_loop']['promoted_contracts'][0])
            foreign['contract_id'] = 'unrelated-same-path-contract'
            gap['repair_loop']['promoted_contracts'].append(foreign)
        return gap

    monkeypatch.setattr(requests, '_inference_repair_feedback_gap', with_extra_contract)
    queued, _ = web._LATE_FILL_RUNTIME.finalize_terminal_materialization_contract(
        payload, request_payload={'inference_route': True, 'prompt': prompt},
        route_payload={'route_runtime': {'request_phase_graph': graph}},
        artifact_gap={'expected_capability': 'chat'}, terminal_status='completed')
    loop = queued['late_fill']['repair_loop']
    assert 'unrelated-same-path-contract' in {c['contract_id'] for c in loop['promoted_contracts']}
    assert 'unrelated-same-path-contract' not in {c['contract_id'] for c in loop.get('superseded_contracts', [])}


@pytest.mark.parametrize('complete_coalesced', [True, False])
def test_scheduled_saved_repair_closes_with_historical_result(tmp_path, monkeypatch, complete_coalesced):
    """Real projection -> claimed worker -> writes -> freeze -> recovery."""
    from tests.fake_backends import FakeBackendHarness

    with FakeBackendHarness() as harness:
        site_root = harness.artifacts_dir / 'site'
        site_root.mkdir()
        prompt, graph, payload, html, css, repaired_html = missing_image_fixture(site_root)
        repaired_css = css.read_text()
        request = {'inference_route': True, 'prompt': prompt}
        old_text = html.read_text()
        historical = {
            'branch_id': 'repair-chat', 'phase_id': 'repair-chat', 'capability': 'chat',
            'saved_text_path': str(html), 'path': str(html), 'type': 'text',
            'artifact_ref': 'artifact:index', 'text_artifact_extension': 'html',
            'content': old_text, 'result_text': old_text,
            'file_sha256': hashlib.sha256(old_text.encode()).hexdigest(),
        }
        payload['late_fill']['fill_results'].insert(0, historical)
        events, calls, errors, workers = [], [], [], []
        runtime = replace(web._LATE_FILL_RUNTIME, log_unified_event=lambda **e: events.append(e))
        for instance in harness.instances.values():
            instance['runtime_status'].update(process_alive=True, port_listening=True)
        monkeypatch.setattr(runtime, 'load_running_instances', lambda: list(harness.instances.values()))
        monkeypatch.setattr(runtime, 'merge_instances_with_runtime_status', lambda entries, **kw: entries)

        def provider(**kwargs):
            data = kwargs['payload']
            calls.append(deepcopy(data))
            target = data.get('text_artifact_target_path') or (data.get('artifact_request') or {}).get('target_path')
            # Target contract is produced by the actual planner/adapter.
            assert target in {str(html), str(css)}, data
            if complete_coalesced and data.get('branch_id', '').startswith('coalesced-text-artifacts-'):
                saved = []
                for branch in queued['late_fill']['pending_branches']:
                    binding = branch['artifact_request']
                    body = repaired_css if binding['extension'] == 'css' else repaired_html
                    result, error = runtime._materialize_required_text_artifact_target_path(
                        branch, {'result_text': body}, {}, extension=binding['extension'],
                        source_name=binding['source_name'])
                    assert error is None, error
                    saved.append({'path': result['saved_text_path'], 'text_artifact_request': binding})
                return {'content': f'```html\n{repaired_html}\n```\n\n```css\n{repaired_css}\n```',
                        'saved_text_artifacts': saved}, 200
            return {'content': repaired_css if target == str(css) else repaired_html}, 200

        monkeypatch.setattr(web, '_invoke_internal_api_json_route', provider)
        with web.app.app_context():
            queued, status = runtime.finalize_terminal_materialization_contract(
                payload, request_payload=request, route_payload={'route_runtime': {'request_phase_graph': graph}},
                artifact_gap={'expected_capability': 'chat'}, terminal_status='completed')
            assert status == 'pending'
            admitted = harness.freeze_manual_response(queued, request_payload=request)
            runtime.touch_response_lookup(payload['id'], response_payload=admitted)
            saved_history = deepcopy(admitted['late_fill']['fill_results'][0])
        parent = harness.response_frames_dir.joinpath('responses.jsonl').read_bytes()
        done = threading.Event()

        def worker(**kwargs):
            workers.append(threading.current_thread())
            try:
                with web.app.app_context():
                    runtime.complete_response_late_fill(**kwargs)
            except BaseException as exc:
                errors.append(exc)
            finally:
                done.set()

        with web.app.app_context():
            handoff = runtime._terminal_closure_repair_handoff(
                admitted, request_payload=request, assistant_message=payload['output_text'], source_route_payload=None)
            assert handoff is not None
            assert runtime.schedule_response_late_fill(**handoff, complete_response_late_fill=worker)
        assert done.wait(60), 'repair worker did not complete within the test deadline'
        for thread in workers:
            thread.join(30)
            assert not thread.is_alive()
        assert not errors, errors
        rejected = [e for e in events if e.get('status') == 'stale_result_rejected']
        assert not rejected, rejected
        print(json.dumps({'calls': [{k: c.get(k) for k in ('branch_id', 'text_artifact_target_path')}
                                    for c in calls],
                          'events': [{k: e.get(k) for k in ('status', 'message')}
                                     for e in events if e.get('message')]}, indent=2))
        assert len(calls) == (1 if complete_coalesced else 3), {
            'calls': [{k: c.get(k) for k in ('branch_id', 'text_artifact_target_path', 'artifact_request')}
                      for c in calls],
            'events': [{k: e.get(k) for k in ('status', 'message')} for e in events],
        }
        assert calls[0]['branch_id'].startswith('coalesced-text-artifacts-')
        retries = [e for e in events if e.get('message') ==
                   'Retryable auto-executable repair branch requeued after failed materialization attempt.']
        assert len(retries) == (0 if complete_coalesced else 2)
        if not complete_coalesced:
            assert {c['text_artifact_target_path'] for c in calls[1:]} == {str(html), str(css)}
        final = runtime.get_response_lookup_record(payload['id'])['response_payload']
        assert final['lifecycle_state'] == 'completed', final['late_fill']
        assert final['late_fill']['fill_results'][0] == saved_history
        assert final['late_fill']['final_materialization_contract_status'] == 'fulfilled'
        assert final['late_fill']['repair_loop']['status'] == 'completed'
        assert not final['late_fill']['repair_loop']['promoted_contracts']
        assert final['late_fill']['repair_loop']['superseded_contracts']
        assert not final['late_fill'].get('pending_branches')
        assert not final['late_fill'].get('failed_branches')
        assert html.read_text() == repaired_html.strip()
        assert css.read_text() == repaired_css.strip()
        assert harness.response_frames_dir.joinpath('responses.jsonl').read_bytes().startswith(parent)
        harness.clear_response_lookup()
        recovered = harness.response_state(payload['id'])
        assert recovered['ok']
        assert recovered['response_payload']['lifecycle_state'] == 'completed'
        assert recovered['response_payload']['late_fill']['fill_results'][0]['file_sha256'] == saved_history['file_sha256']
        assert retained_fields(recovered['response_payload']['late_fill']['repair_loop']['superseded_contracts']) == \
            retained_fields(final['late_fill']['repair_loop']['superseded_contracts'])
        # A completed handoff cannot redispatch the same terminal repair.
        before = len(calls)
        with web.app.app_context():
            runtime.complete_response_late_fill(**handoff)
        assert len(calls) == before
