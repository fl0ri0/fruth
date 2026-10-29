"""Native named saved-text completion controls; guarded offline runner only."""
from copy import deepcopy
import hashlib
import json
import threading
from pathlib import Path

import pytest

from tests.consumer_evidence_model import case, oracle, provider_html, requirements
from tests.test_consumer_evidence_a2 import reserve, dump


def summary(payload):
    closure = payload.get('runtime', {}).get('graph_closure_review', {})
    return {key: closure.get(key) for key in (
        'status', 'content_requirement_policy', 'completion_basis',
        'content_coverage_status', 'content_requirement_count',
        'unresolved_content_requirement_count', 'correctness_basis')}


def run_native(monkeypatch, *, label, fault='none', variant=0, review='passed', producer_fault=False,
               probe=None, witness=None, css=True, reference_case=None, legacy_references=False,
               control_probe=None, prepared_prompt=None):
    c = case(fault=fault, variant=variant, css=css)
    req = requirements(c)
    root, start = reserve('coverage-' + label, c, 'control')
    report = {'start': start, 'interventions': [
        'Synthetic availability and controlled offline artifact/reviewer transport.',
        'No injected criteria or completed reviewer records. Native terminal repair admission and scheduling.',
    ], 'calls': [], 'packets': []}
    import fruth_webserver as web
    import fruth_server.late_fill_runtime as late_module
    from fruth_inference.request_phase_graph import build_request_phase_graph
    from fruth_services.responses import capture_request_intent, restore_request_intent
    from tests.fake_backends import FakeBackendHarness
    from tests.test_saved_file_consumer_path import owner_for, saved

    try:
        with FakeBackendHarness(root=root / 'runtime') as harness, monkeypatch.context() as scoped:
            docs = harness.documents_dir
            resolver = owner_for(docs).resolve_saved_file_input_path
            harness.instances['chat']['runtime_status'].update(process_alive=True, port_listening=True)
            runtime = web._LATE_FILL_RUNTIME
            scoped.setattr(runtime, 'resolve_saved_file_input_path', resolver)
            scoped.setattr(web, '_resolve_saved_viewable_artifact_path', resolver)
            scoped.setattr(web, 'ARTIFACT_OUTPUTS_DOCUMENTS_DIR', docs)
            scoped.setattr(late_module, 'ARTIFACT_OUTPUTS_DOCUMENTS_DIR', docs)
            request = capture_request_intent({'prompt': req['prompt'], 'inference_route': True})
            if legacy_references:
                request = restore_request_intent({'prompt': req['prompt'], 'inference_route': True,
                    'intent_source': 'runtime_caller_capture_v1', 'content_requirement_policy': 'named_saved_text_v1'})
            graph = build_request_phase_graph(req['prompt'], request_payload=request,
                                             response_payload={'output_text': 'Preparation complete.'})
            if prepared_prompt is not None:
                request['prompt'] = prepared_prompt
            assert graph['content_requirement_policy'] == 'named_saved_text_v1'
            assert {r['role'] for r in graph['content_requirements']} == {'producer', 'consumer'}
            for obligation in graph['output_obligations']:
                ar = obligation.get('artifact_request') or {}
                if ar.get('content_requirements'):
                    assert ar['content_requirements'][0]['criterion'] in obligation['review_criteria']
            report['accepted_requirements'] = graph['content_requirements']
            payload = {'id': 'coverage-' + label, 'object': 'response', 'capability': 'chat',
                       'output_text': 'Preparation complete.', 'runtime': {'request_phase_graph': graph},
                       'late_fill': {'status': 'pending', 'pending_branches': graph['downstream_branches'],
                                     'pending_capabilities': ['chat']}}

            def backend(*, payload, upload):
                ar = payload.get('artifact_request') or (payload.get('execution_contract') or {}).get('artifact_request') or {}
                if ar.get('extension'):
                    report['calls'].append(ar['extension'])
                    if ar['extension'] == 'json':
                        data = deepcopy(req['data'])
                        if producer_fault:
                            data['subject'] = 'wrong-producer'
                        body = json.dumps(data, sort_keys=True, separators=(',', ':'))
                    else:
                        raw = payload['prompt'].split('--- SAVED FILE START ---\n')[1].split('\n--- SAVED FILE END ---')[0]
                        body = provider_html(json.loads(raw), c)
                        if review == 'insufficient_packet':
                            body += '<!--' + ('x' * 17_000) + '-->'
                        if review == 'no_capacity':
                            harness.instances['chat']['runtime_status'].update(process_alive=False, port_listening=False)
                    if witness:
                        assert req == witness['request']
                        body = witness['source_text'] if ar['extension'] == 'json' else witness['output_text']
                    path = saved(docs, ar['source_name'], ar['extension'], body)
                    return {'saved_text_path': path, 'content': body,
                            'saved_text_artifacts': [{'path': path, 'text_artifact_request': ar}]}, 200
                report['calls'].append('review')
                prompt = payload['prompt']
                report.setdefault('review_submitted', []).append(deepcopy(payload))
                packet = json.JSONDecoder().raw_decode(prompt.split('Branch runtime evidence:\n', 1)[1])[0]
                report['packets'].append(packet)
                coverage = packet['content_coverage']
                assert coverage['complete'] and coverage['requirements']
                assert all(ref['content_excerpt_mode'] == 'full' for ref in packet['artifact_refs'])
                role = coverage['requirements'][0]['role']
                expected_output = (docs / ('numbers.json' if role == 'producer' else 'result.html')).read_text()
                assert all(ref['content_excerpt'] == expected_output for ref in packet['artifact_refs'])
                if role == 'consumer':
                    assert coverage['source']['content_excerpt'] == (docs / 'numbers.json').read_text()
                    assert json.loads(coverage['source']['content_excerpt'])['values'] == req['data']['values']
                criteria = packet['branch_check']['semantic_review_criteria']
                assert coverage['requirements'][0]['criterion'] in criteria
                negative = (review == 'negative' and (fault == 'none' or role == 'consumer')) or (producer_fault and role == 'producer')
                results = [{'criterion': value, 'status': 'failed' if negative else 'passed',
                            'evidence_refs': ['unrelated-ref' if review == 'wrong_refs' else packet['source_branch_id']]} for value in criteria]
                if review == 'incomplete':
                    results = []
                verdict = {'kind': 'fruth.semantic_review_verdict',
                           'verdict': 'failed' if negative else 'passed',
                           'overall_status': 'blocked' if negative else 'fulfilled',
                           'whole_intent_fit': 'Controlled offline review.',
                           'criterion_results': results, 'evidence_refs': ['unrelated-ref' if review == 'wrong_refs' else packet['source_branch_id']],
                           'defects': ['controlled negative'] if negative else [],
                           'recommended_transition': 'manual_review' if negative else 'truthful_freeze'}
                if reference_case:
                    reference_case(packet, verdict, report)
                report.setdefault('returned_verdicts', []).append(deepcopy(verdict))
                return {'content': json.dumps(verdict)}, 200

            scoped.setattr(web, '_invoke_internal_api_json_route', backend)
            if review == 'misbound':
                original_execute = runtime.execute_prepared_late_fill_branch
                consumer_id = next(r['branch_id'] for r in graph['content_requirements'] if r['role'] == 'consumer')
                def misbind_result(plan):
                    result = original_execute(plan)
                    binding = result.get('infer_result', {}).get('semantic_review_evidence_binding') or {}
                    if binding.get('source_branch_id') == consumer_id:
                        binding['sha256'] = '0' * 64
                    return result
                scoped.setattr(runtime, 'execute_prepared_late_fill_branch', misbind_result)
                report['interventions'].append('Misbind the real consumer reviewer result receipt after transport, before native acceptance.')
            scoped.setitem(web.app.config, 'TESTING', True)
            with web.app.app_context():
                runtime.complete_response_late_fill(
                    response_payload=payload, request_payload=request, assistant_message=payload['output_text'],
                    artifact_gap={'pending_branches': graph['downstream_branches'], 'pending_capabilities': ['chat'],
                                  'expected_capability': 'chat'}, source_route_payload=None)
            initial = runtime.get_response_lookup_record(payload['id'])['response_payload']
            report['before_review'] = summary(initial)
            report['initial_late'] = {k: initial['late_fill'].get(k) for k in ('status', 'terminal_closure_repair_reopen')}
            assert report['before_review']['status'] != 'fulfilled'
            assert report['before_review']['completion_basis'] == 'content_coverage_unresolved'
            assert report['before_review']['content_requirement_count'] == 2
            assert report['before_review']['unresolved_content_requirement_count'] == 2
            assert report['calls'] == ['json', 'html']
            artifact_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in docs.iterdir() if p.is_file()}
            scoped.setitem(web.app.config, 'TESTING', False)
            admitted = harness.freeze_manual_response(initial, request_payload=request)
            runtime.touch_response_lookup(payload['id'], response_payload=admitted)
            if control_probe:
                control_probe(harness, runtime, request, admitted, docs, report, scoped)
                report['status'] = 'passed'
                return
            if review in {'missing', 'no_capacity'}:
                if review == 'no_capacity':
                    assert initial['late_fill']['status'] == 'repair_needed', report
                    assert not initial['late_fill'].get('pending_branches'), report
                    assert initial['runtime']['graph_closure_review']['status'] == 'blocked'
                    assert runtime._terminal_closure_repair_handoff(admitted, request_payload=request,
                        assistant_message=payload['output_text'], source_route_payload=None) is None
                assert_compact_readback(harness, payload['id'], report['before_review'])
                report['status'] = 'passed_unresolved'
                return
            done = threading.Event()
            errors, workers = [], []
            if review == 'capacity_lost':
                harness.instances['chat']['runtime_status'].update(process_alive=False, port_listening=False)

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
                assert handoff is not None, report
                assert runtime.schedule_response_late_fill(**handoff, complete_response_late_fill=worker)
            assert done.wait(60), 'bounded review worker timed out'
            for thread in workers:
                thread.join(5)
                assert not thread.is_alive()
            assert not errors, errors
            final = runtime.get_response_lookup_record(payload['id'])['response_payload']
            report['after_review'] = summary(final)
            report['lifecycle_state'] = final.get('lifecycle_state')
            report['checks'] = [{k: ch.get(k) for k in ('branch_id', 'check_kind', 'status', 'evidence', 'reason', 'branch_semantic_review_status', 'content_coverage_status')}
                                for ch in final.get('runtime', {}).get('graph_closure_review', {}).get('checks', [])]
            assert artifact_hashes == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in docs.iterdir() if p.is_file()}
            review_count = 0 if review == 'capacity_lost' else 1 if review == 'insufficient_packet' else 2
            assert report['calls'] == ['json', 'html'] + ['review'] * review_count, report
            if review == 'capacity_lost':
                assert final['late_fill']['status'] == 'repair_needed'
                assert not final['late_fill'].get('pending_branches')
                assert runtime._terminal_closure_repair_handoff(final, request_payload=request,
                    assistant_message=payload['output_text'], source_route_payload=None) is None
            report['oracle'] = oracle(req, (docs / 'result.html').read_text(), list(artifact_hashes))
            assert report['oracle']['correct'] == (fault == 'none' and not producer_fault)
            # New reference policy deliberately rejects the retained wrong-ref
            # witness. Historical snapshot expectations remain unchanged.
            success = (review == 'passed' or (legacy_references and review == 'wrong_refs')) and not producer_fault
            if reference_case:
                success = reference_case.expected_unresolved == 0
            assert (final.get('lifecycle_state') == 'completed') == success, report
            assert (report['after_review']['status'] == 'fulfilled') == success, report
            assert report['after_review']['completion_basis'] == ('bound_semantic_review' if success else 'content_coverage_unresolved')
            assert report['after_review']['content_coverage_status'] == ('covered' if success else 'unverified')
            assert report['after_review']['content_requirement_count'] == 2
            assert report['after_review']['correctness_basis'] == 'reviewer_soundness_assumption'
            one_uncovered = producer_fault or review in {'insufficient_packet', 'misbound'} or (review == 'negative' and fault != 'none')
            expected_unresolved = (reference_case.expected_unresolved if reference_case
                                   else 0 if success else 1 if one_uncovered else 2)
            assert report['after_review']['unresolved_content_requirement_count'] == expected_unresolved
            if one_uncovered:
                covered_role = 'consumer' if producer_fault else 'producer'
                covered_roles = {r['role'] for ch in final['runtime']['graph_closure_review']['checks']
                                 if ch.get('content_coverage_status') == 'accepted_review'
                                 for r in ch['content_requirements']}
                assert covered_roles == {covered_role}
            harness.clear_response_lookup()
            state = harness.response_state(payload['id'])
            assert state['ok']
            assert state['response_frame']['request']['content_requirement_policy'] == 'named_saved_text_v1'
            assert state['response_payload']['runtime']['request_phase_graph']['content_requirements'] == graph['content_requirements']
            report['readback'] = summary(state['response_payload'])
            assert report['readback'] == report['after_review']
            assert state['response_payload']['lifecycle_state'] == final['lifecycle_state']
            assert_compact_readback(harness, payload['id'], report['after_review'])
            if witness:
                report['retained_witness'] = witness['evidence']
                assert artifact_hashes['numbers.json'] == witness['source_sha256']
                assert artifact_hashes['result.html'] == witness['output_sha256']
            if probe:
                probe(harness, runtime, request, final, docs, report)
            report['status'] = 'passed'
    finally:
        dump(root / 'observation.json', report)


def test_native_review_completion(monkeypatch):
    run_native(monkeypatch, label='native')


def control_closure_checkpoint(harness, runtime, request, admitted, docs, report, scoped,
                               *, accepted_consumer, action, assessment_failure=False):
    """Hold the producer provider return until the real control has committed."""
    import fruth_webserver as web
    from tests.http_client import api_client

    response_id = admitted['id']
    source_ids = {r['role']: r['branch_id'] for r in report['accepted_requirements']}
    identities = {runtime._content_review_binding(b)['source_branch_id']: b['branch_id']
                  for b in admitted['late_fill']['pending_branches']}
    producer = identities[source_ids['producer']]
    consumer = identities[source_ids['consumer']]
    expected_roles = {'consumer'} if accepted_consumer else set()
    expected_unresolved = 1 if accepted_consumer else 2
    ledger = harness.response_frames_dir / 'responses.jsonl'
    initial_prefix = ledger.read_bytes()
    # Compare canonical graph representations on both sides of persistence;
    # the expanded finalizer return still contains optional empty fields.
    graph = deepcopy(harness.response_state(response_id)['response_payload']['runtime']['request_phase_graph'])
    saved_request = deepcopy(admitted['response_frame']['request'])
    artifacts = {p: p.read_bytes() for p in docs.iterdir() if p.is_file()}
    snapshots = {}
    entered, release, done = threading.Event(), threading.Event(), threading.Event()
    workers, errors, controls = [], [], []
    original_transport = web._invoke_internal_api_json_route

    def current():
        return web._get_response_lookup_record(response_id)['response_payload']

    def preserve_snapshots():
        for p in (harness.response_frames_dir / 'snapshots').rglob('*'):
            if p.is_file():
                snapshots.setdefault(p, hashlib.sha256(p.read_bytes()).hexdigest())

    def control(target, control_action, expected=200):
        before = deepcopy(current())
        prefix = ledger.read_bytes()
        calls = list(report['calls'])
        preserve_snapshots()
        with api_client(web.app) as client:
            reply = client.post(f'/api/responses/{response_id}/late_fill/control', json={
                'action': control_action, 'scope': 'branch', 'branch_id': target,
                'reason': 'Deterministic control Closure accounting regression.'})
        assert reply.status_code == expected, reply.get_json()
        assert report['calls'] == calls, 'control must not dispatch provider work'
        after = current()
        assert after['late_fill']['fill_results'] == before['late_fill']['fill_results']
        if expected != 200:
            assert ledger.read_bytes() == prefix
            assert after == before
            return after
        assert ledger.read_bytes().startswith(prefix)
        frame = after['response_frame']
        assert frame['frame_sequence'] == before['response_frame']['frame_sequence'] + 1
        assert frame['frame_relation']['parent_frame_id'] == before['response_frame']['frame_id']
        assert frame['request'] == saved_request
        assert after['runtime']['request_phase_graph'] == graph
        controls.append({'target': target, 'action': control_action, 'frame_id': frame['frame_id'],
                         'parent_frame_id': before['response_frame']['frame_id'], 'summary': summary(after)})
        canonical = harness.response_state(response_id)
        assert canonical['ok']
        assert summary(canonical['response_payload']) == summary(after)
        if target == producer:
            assert_assessment(after)
        return deepcopy(canonical['response_payload'])

    def assert_assessment(payload):
        closure = payload['runtime']['graph_closure_review']
        checks = [ch for ch in closure['checks'] if ch.get('content_requirements')]
        assert {r['role'] for ch in checks for r in ch['content_requirements']} == {'producer', 'consumer'}
        reviewed = {r['role'] for ch in checks if ch.get('content_coverage_status') == 'accepted_review'
                    for r in ch['content_requirements']}
        assert reviewed == expected_roles
        assert not any(ch.get('content_coverage_status') == 'authorized_disposition' for ch in checks)
        assert closure['unresolved_content_requirement_count'] == expected_unresolved
        assert closure['content_requirement_count'] == 2
        assert closure['completion_basis'] == 'content_coverage_unresolved'
        assert closure['status'] != 'fulfilled' and payload['lifecycle_state'] != 'completed'
        assert closure['late_fill_status'] == payload['late_fill']['status']
        assert closure == payload['runtime']['developer_diagnostics']['graph_closure_review']
        assert closure['surface_state'] == payload['runtime']['surface_state']
        # Canonical current_state deliberately saves a compact top-level handle;
        # all of its assessment fields must agree with the full runtime review.
        for key in ('status', 'active_categories', 'category_counts', 'content_requirement_policy',
                    'content_requirement_count', 'unresolved_content_requirement_count',
                    'content_coverage_status', 'completion_basis', 'correctness_basis'):
            assert payload['surface_state'][key] == closure['surface_state'][key]
        assert closure['surface_state']['unresolved_content_requirement_count'] == expected_unresolved
        return closure

    def readback(expected):
        prefix = ledger.read_bytes()
        harness.clear_response_lookup()
        durable = harness.response_state(response_id)
        assert durable['ok']
        assert durable['response_frame']['frame_id'] == expected['response_frame']['frame_id']
        assert durable['response_frame']['request'] == saved_request
        restored = durable['response_payload']
        assert restored['late_fill']['fill_results'] == expected['late_fill']['fill_results']
        assert restored['runtime']['request_phase_graph'] == graph
        assert assert_assessment(restored) == assert_assessment(expected)
        assert_compact_readback(harness, response_id, summary(expected))
        assert ledger.read_bytes() == prefix, 'passive reads must not refresh or publish'

    def transport(*, payload, upload):
        if 'Branch runtime evidence:\n' in payload.get('prompt', ''):
            packet = json.JSONDecoder().raw_decode(payload['prompt'].split('Branch runtime evidence:\n', 1)[1])[0]
            if packet['content_coverage']['requirements'][0]['role'] == 'producer':
                entered.set()
                assert release.wait(60), 'producer return barrier timed out'
        return original_transport(payload=payload, upload=upload)

    def worker(**kwargs):
        workers.append(threading.current_thread())
        try:
            with web.app.app_context():
                runtime.complete_response_late_fill(**kwargs)
        except BaseException as exc:
            errors.append(exc)
        finally:
            done.set()

    scoped.setattr(web, '_invoke_internal_api_json_route', transport)
    scoped.setattr(web, '_complete_response_late_fill', worker)
    try:
        if not accepted_consumer:
            # Supported negative control: dispose the consumer review before it
            # executes. Its distinct content duty remains unresolved.
            control(consumer, 'cancel')
        with web.app.app_context():
            handoff = runtime._terminal_closure_repair_handoff(current(), request_payload=request,
                assistant_message=admitted['output_text'], source_route_payload=None)
            assert handoff is not None
            assert runtime.schedule_response_late_fill(**handoff, complete_response_late_fill=worker)
        assert entered.wait(60), 'producer provider entry barrier timed out'
        before = deepcopy(current())
        accepted = before['late_fill']['fill_results']
        assert any(r.get('branch_id') == consumer for r in accepted) == accepted_consumer
        assert not any(r.get('branch_id') == producer for r in accepted)
        if assessment_failure:
            report['interventions'].append('Negative owner fault: assessment raises before control publication.')
            with scoped.context() as fault:
                def fail_assessment(*args, **kwargs):
                    raise RuntimeError('controlled assessment failure')
                fault.setattr(web, '_build_graph_closure_review', fail_assessment)
                control(producer, action, expected=500)
        controlled = control(producer, action)
        assert_assessment(controlled)
        readback(controlled)  # Durable winning control while provider is still held.
        control_prefix = ledger.read_bytes()
        release.set()
        assert done.wait(60), 'controlled review worker timed out'
        for thread in workers:
            thread.join(5)
            assert not thread.is_alive()
        assert not errors, errors
        final = deepcopy(current())
        assert final['response_frame']['frame_id'] == controlled['response_frame']['frame_id']
        assert ledger.read_bytes() == control_prefix, 'rejected worker must not publish over control'
        assert final['late_fill']['fill_results'] == accepted
        assert not any(r.get('branch_id') == producer for r in final['late_fill']['fill_results'])
        assert report['calls'] == ['json', 'html'] + ['review'] * (2 if accepted_consumer else 1)
        assert report['packets'][-1]['content_coverage']['requirements'][0]['role'] == 'producer'
        assert report['returned_verdicts'][-1]['verdict'] == 'passed', 'delayed successful result was actually returned'
        status = {'cancel': 'cancelled', 'waive': 'waived', 'supersede': 'superseded'}[action]
        assert any(b['branch_id'] == producer and b['status'] == status for b in final['late_fill']['cancelled_branches'])
        control(producer, action, expected=404)
        readback(final)
        assert ledger.read_bytes().startswith(initial_prefix)
        assert artifacts == {p: p.read_bytes() for p in docs.iterdir() if p.is_file()}
        assert all(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in snapshots.items())
        report['control_closure'] = {'controls': controls, 'expected_reviewed_roles': sorted(expected_roles),
            'summary': summary(final), 'review': assert_assessment(final), 'delayed_result_rejected': True,
            'artifact_sha256': {p.name: hashlib.sha256(data).hexdigest() for p, data in artifacts.items()},
            'immutable_snapshot_count': len(snapshots), 'ledger_prefix_preserved': True,
            'request_preserved': saved_request, 'passive_readback_unchanged': True}
    finally:
        release.set()
        for thread in workers:
            thread.join(5)
        report['control_closure_workers_settled'] = all(not thread.is_alive() for thread in workers)


@pytest.mark.parametrize('action', ['cancel', 'waive', 'supersede'])
@pytest.mark.parametrize('accepted_consumer', [True, False], ids=['accepted-consumer', 'no-consumer-review'])
def test_control_refreshes_accepted_content_accounting(monkeypatch, action, accepted_consumer):
    def checkpoint(*args):
        control_closure_checkpoint(*args, action=action, accepted_consumer=accepted_consumer)
    run_native(monkeypatch, label=f'control-closure-{action}-{accepted_consumer}', control_probe=checkpoint,
        prepared_prompt='Prepared execution text; original caller intent remains separate.')


def test_control_assessment_failure_does_not_publish(monkeypatch):
    def checkpoint(*args):
        control_closure_checkpoint(*args, action='cancel', accepted_consumer=True, assessment_failure=True)
    run_native(monkeypatch, label='control-closure-assessment-failure', control_probe=checkpoint)


def control_request_checkpoint(harness, runtime, request, admitted, docs, report, scoped,
                               *, carrier, action, cut='before', role='consumer'):
    """Real control checkpoints; synthetic transport remains owned by run_native.

    Live and recovered carriers are reachable owner paths. Conflicting projections
    and historical fixtures below are explicitly negative/compatibility owner tests.
    No control invents replacement work; Closure assesses the accepted evidence.
    """
    import time
    import fruth_webserver as web
    from tests.http_client import api_client
    from fruth_services.responses import (extract_responses_current_turn_prompt,
        extract_responses_prompt, request_intent_payload, restore_request_intent)

    response_id = admitted['id']
    ledger = harness.response_frames_dir / 'responses.jsonl'
    caller = extract_responses_current_turn_prompt(request)
    execution = extract_responses_prompt(request)
    source_request = deepcopy(admitted['response_frame']['request'])
    report['control_source_request'] = source_request
    identities = {runtime._content_review_binding(b)['source_branch_id']: b
                  for b in admitted['late_fill']['pending_branches']}
    source_ids = {r['role']: r['branch_id'] for r in report['accepted_requirements']}
    target = identities[source_ids[role]]['branch_id']
    snapshots = {str(p.relative_to(harness.response_frames_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in (harness.response_frames_dir / 'snapshots').rglob('*') if p.is_file()}
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in docs.iterdir() if p.is_file()}
    prefix = ledger.read_bytes()
    controls, workers, errors = [], [], []

    def current():
        return web._get_response_lookup_record(response_id)['response_payload']

    def control():
        if carrier == 'recovered':
            harness.clear_response_lookup()
        elif carrier == 'plain-owner':
            # Negative owner test, not a claimed public operation: provide a
            # plain copy of the actual canonical request as a competing carrier.
            projected = deepcopy(current())
            projected['request'] = deepcopy(source_request)
            runtime.touch_response_lookup(response_id, response_payload=projected)
            report['interventions'].append('Negative owner test: plain canonical-request projection added to live lookup.')
        before = deepcopy(current())
        if carrier in {'live', 'recovered'}:
            assert not before.get('request'), 'native live/full-recovery fixture has no top-level request'
        elif carrier == 'plain-owner':
            assert type(before.get('request')) is dict
            assert before['request']['intent_source'] == 'runtime_caller_capture_v1'
        report['control_carrier'] = {'mode': carrier, 'top_level_request': before.get('request'),
                                     'frame_id': before['response_frame']['frame_id']}
        with api_client(web.app) as client:
            reply = client.post(f'/api/responses/{response_id}/late_fill/control', json={
                'action': action, 'scope': 'branch', 'branch_id': target,
                'reason': 'Exact native request-carriage regression.'})
        assert reply.status_code == 200, reply.get_json()
        after = current()
        assert after['late_fill']['fill_results'] == before['late_fill']['fill_results']
        frame = after['response_frame']
        assert frame['frame_sequence'] == before['response_frame']['frame_sequence'] + 1
        assert frame['frame_relation']['parent_frame_id'] == before['response_frame']['frame_id']
        controls.append(deepcopy(after))
        report['control_request_roundtrip'] = {
            'source': source_request, 'successor': frame.get('request'),
            'parent_frame_id': before['response_frame']['frame_id'], 'frame_id': frame['frame_id'],
            'accepted_results_preserved': True,
        }

    def recovered_request():
        harness.clear_response_lookup()
        durable = harness.response_state(response_id)
        assert durable['ok']
        frame_request = durable['response_frame'].get('request') or {}
        restored = restore_request_intent(frame_request)
        report['control_request_roundtrip'].update(
            canonical=frame_request, restored=request_intent_payload(restored),
            caller=extract_responses_current_turn_prompt(restored),
            execution=extract_responses_prompt(restored))
        # These expectations remain byte-identical in baseline and fixed replays.
        assert frame_request == source_request, report['control_request_roundtrip']
        assert extract_responses_current_turn_prompt(restored) == caller
        assert extract_responses_prompt(restored) == execution
        return restored

    def worker(**kwargs):
        workers.append(threading.current_thread())
        try:
            with web.app.app_context():
                runtime.complete_response_late_fill(**kwargs)
        except BaseException as exc:
            errors.append(exc)

    def activate(continuation_request):
        with web.app.app_context():
            handoff = runtime._terminal_closure_repair_handoff(current(), request_payload=continuation_request,
                assistant_message=admitted['output_text'], source_route_payload=None)
            assert handoff is not None
            assert runtime.schedule_response_late_fill(**handoff, complete_response_late_fill=worker)
        deadline = time.monotonic() + 60
        while web._response_late_fill_is_in_flight(response_id):
            assert time.monotonic() < deadline, 'bounded control worker watchdog'
            for thread in list(workers):
                thread.join(.1)
            time.sleep(.01)
        for thread in list(workers):
            thread.join(5)
            assert not thread.is_alive()
        assert not errors, errors

    try:
        if cut == 'before':
            control()
            restored = recovered_request()
        else:
            original_transport = web._invoke_internal_api_json_route
            original_execute = runtime.execute_prepared_late_fill_branch

            def transport(*, payload, upload):
                if cut == 'transport' and 'Branch runtime evidence:\n' in payload.get('prompt', ''):
                    packet = json.JSONDecoder().raw_decode(payload['prompt'].split('Branch runtime evidence:\n', 1)[1])[0]
                    if packet['content_coverage']['requirements'][0]['role'] == role:
                        control()
                return original_transport(payload=payload, upload=upload)

            def execute(plan):
                result = original_execute(plan)
                if cut == 'returned' and plan['branch_id'] == target:
                    control()
                return result

            scoped.setattr(web, '_invoke_internal_api_json_route', transport)
            scoped.setattr(runtime, 'execute_prepared_late_fill_branch', execute)
            scoped.setattr(web, '_complete_response_late_fill', worker)
            activate(request)
            assert len(controls) == 1
            restored = recovered_request()
        # Explicit normal activation of the surviving review uses only restored
        # caller context and its already-admitted local contract. No C9 promise.
        if current()['late_fill'].get('pending_branches'):
            activate(restored)
        final = current()
        assert not any(r.get('branch_id') == target for r in final['late_fill'].get('fill_results', []))
        sibling = identities[source_ids['producer' if role == 'consumer' else 'consumer']]['branch_id']
        assert any(r.get('branch_id') == sibling for r in final['late_fill']['fill_results'])
        for result in controls[0]['late_fill']['fill_results']:
            assert result in final['late_fill']['fill_results']
        assert ledger.read_bytes().startswith(prefix)
        for rel, digest in snapshots.items():
            assert hashlib.sha256((harness.response_frames_dir / rel).read_bytes()).hexdigest() == digest
        assert files == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in docs.iterdir() if p.is_file()}
        recovered_request()
        report['control_continuation'] = {'sibling': sibling, 'cancelled_target': target,
            'final_summary': summary(final), 'artifacts_unchanged': files,
            'frozen_snapshots_unchanged': len(snapshots), 'ledger_prefix_unchanged': True}
        assert_compact_readback(harness, response_id, summary(final))
        return final
    finally:
        for thread in list(workers):
            thread.join(5)
        report['control_workers_settled'] = all(not thread.is_alive() for thread in workers)


@pytest.mark.parametrize('carrier,action,cut,role', [
    ('live', 'cancel', 'before', 'consumer'),
    ('recovered', 'waive', 'before', 'consumer'),
    ('live', 'supersede', 'before', 'consumer'),
    ('recovered', 'cancel', 'before', 'consumer'),
    ('live', 'waive', 'before', 'consumer'),
    ('recovered', 'supersede', 'before', 'consumer'),
    ('live', 'cancel', 'transport', 'consumer'),
    ('live', 'waive', 'transport', 'consumer'),
    ('live', 'supersede', 'transport', 'producer'),
    ('live', 'cancel', 'returned', 'consumer'),
    ('plain-owner', 'waive', 'before', 'consumer'),
])
def test_supported_control_preserves_canonical_request(monkeypatch, carrier, action, cut, role):
    def checkpoint(*args):
        control_request_checkpoint(*args, carrier=carrier, action=action, cut=cut, role=role)
    run_native(monkeypatch, label=f'control-request-{carrier}-{action}-{cut}-{role}',
        control_probe=checkpoint, prepared_prompt='Prepared backend text; not a new caller instruction.')


def test_control_preserves_historical_reference_policy_absence(monkeypatch):
    def checkpoint(*args):
        final = control_request_checkpoint(*args, carrier='recovered', action='supersede')
        assert 'content_review_reference_policy' not in final['response_frame']['request']
    run_native(monkeypatch, label='control-historical-refs', control_probe=checkpoint,
        legacy_references=True, prepared_prompt='Historical separate preparation.')


def test_control_unavailable_intent_retains_branch_local_continuation(monkeypatch):
    def checkpoint(harness, runtime, request, admitted, docs, report, scoped):
        from fruth_services.responses import restore_request_intent, request_intent_evidence_missing
        # Compatibility owner fixture: historical serialization has only an
        # effective prompt, while its previously admitted branches remain exact.
        # This is not a public operation that removes newly captured authority.
        saved_request = deepcopy(admitted['response_frame']['request'])
        saved_request.pop('intent_source')
        legacy = restore_request_intent(saved_request)
        report['interventions'].append('Historical owner fixture: persist already-admitted work without original-intent evidence.')
        historical = harness.freeze_manual_response(admitted, request_payload=legacy)
        runtime.touch_response_lookup(admitted['id'], response_payload=historical)
        final = control_request_checkpoint(harness, runtime, legacy, historical, docs, report, scoped,
            carrier='recovered', action='cancel')
        restored = restore_request_intent(final['response_frame']['request'])
        assert request_intent_evidence_missing(restored)
    run_native(monkeypatch, label='control-unavailable-intent', control_probe=checkpoint)


def assert_compact_readback(harness, response_id, expected):
    for view in ('full', 'status', 'ui', 'debug'):
        harness.clear_response_lookup()
        payload, status = harness.get_response(response_id, view=view)
        assert status == 200, (view, payload)
        # Public envelopes may place the indexed surface on the response or frame.
        candidates = []
        def visit(value):
            if isinstance(value, dict):
                if value.get('content_requirement_policy') == 'named_saved_text_v1' and 'completion_basis' in value:
                    candidates.append(value)
                for item in value.values():
                    visit(item)
            elif isinstance(value, list):
                for item in value:
                    visit(item)
        visit(payload)
        assert any(all(value.get(k) == expected[k] for k in (
            'completion_basis', 'content_coverage_status', 'content_requirement_count',
            'unresolved_content_requirement_count', 'correctness_basis'))
            for value in candidates), (view, expected, candidates)


@pytest.mark.parametrize('variant', [1, 2])
def test_equivalent_content(monkeypatch, variant):
    run_native(monkeypatch, label=f'equivalent-{variant}', variant=variant)


def test_css_not_requested(monkeypatch):
    run_native(monkeypatch, label='css-not-requested', css=False)


@pytest.mark.parametrize('review', ['missing', 'no_capacity', 'capacity_lost', 'negative', 'incomplete', 'insufficient_packet'])
def test_review_controls(monkeypatch, review):
    run_native(monkeypatch, label=review, review=review)


def test_producer_content_is_separate(monkeypatch):
    run_native(monkeypatch, label='producer-fault', producer_fault=True)


WITNESSES = json.loads(Path(__file__).with_name('content_requirement_witnesses.json').read_text())


@pytest.mark.parametrize('index', range(len(WITNESSES)))
def test_retained_a2_witness(monkeypatch, index):
    witness = WITNESSES[index]
    fault = 'omit_css' if 'omit_css' in witness['evidence'] else 'none' if witness['oracle']['correct'] else 'wrong_sum'
    # Replay identical requested and produced bytes through new native policy.
    # Positive false reviews remain intentionally unsound controls.
    review = ('wrong_refs' if 'wrong_refs' in witness['evidence'] else
              'misbound' if 'wrong_binding' in witness['evidence'] else 'passed')
    run_native(monkeypatch, label=f'witness-{index}', fault=fault, review=review, witness=witness)


@pytest.mark.parametrize('fault', ['omit_subject', 'wrong_subject', 'omit_version', 'wrong_version',
                                  'omit_values', 'wrong_values', 'omit_sum', 'wrong_sum', 'omit_css'])
def test_content_fault_with_negative_review(monkeypatch, fault):
    run_native(monkeypatch, label=f'negative-{fault}', fault=fault, review='negative')


def test_current_evidence_and_accounting_controls(monkeypatch):
    def probe(harness, runtime, request, final, docs, report):
        import fruth_webserver as web
        semantics = web._RESPONSE_SEMANTICS_RUNTIME
        source = docs / 'numbers.json'
        output = docs / 'result.html'
        originals = {p: p.read_bytes() for p in (source, output)}
        parent_frame = final['response_frame']
        ledger = harness.response_frames_dir / 'responses.jsonl'
        original_ledger = ledger.read_bytes()
        report['controls'] = []

        def walk(value, transform):
            if isinstance(value, dict):
                transform(value)
                for child in list(value.values()):
                    walk(child, transform)
            elif isinstance(value, list):
                for child in value:
                    walk(child, transform)

        controls = ['consumer_review_missing', 'producer_review_missing', 'review_result_missing',
                    'misbound_review', 'review_policy_missing', 'requirement_version', 'source_version', 'output_version',
                    'accounting_missing', 'obligation_accounting_missing', 'insufficient_packet',
                    'criteria_removed', 'malformed_accounting', 'malformed_requirement_id']
        review_result = next(r for r in final['late_fill']['fill_results'] if r.get('semantic_review_evidence_binding'))
        with pytest.raises(ValueError, match='content_review_prepared_packet_changed'):
            runtime.execute_prepared_late_fill_branch({'capability': 'chat',
                'execution_contract': review_result['execution_contract'],
                'infer_payload': {'prompt': 'Artifact exists, so approve it.'}})
        for name in controls:
            control_root, _ = reserve('coverage-control-' + name, case(), 'replay')
            candidate = deepcopy(final)
            candidate['response_frame'] = parent_frame
            graph = candidate['runtime']['request_phase_graph']
            late = candidate['late_fill']
            if name.endswith('_review_missing'):
                role = name.split('_')[0]
                branch_id = next(r['branch_id'] for r in graph['content_requirements'] if r['role'] == role)
                for key in ('completed_branches', 'fill_results'):
                    late[key] = [r for r in late[key] if not (r.get('semantic_review_evidence_binding') or
                        (r.get('execution_contract') or {}).get('semantic_review_evidence_binding') or {}).get('source_branch_id') == branch_id]
            elif name == 'review_result_missing':
                late['fill_results'] = [r for r in late['fill_results'] if not r.get('semantic_review_evidence_binding')]
            elif name == 'misbound_review':
                for r in late['fill_results']:
                    if r.get('semantic_review_evidence_binding'):
                        r['semantic_review_evidence_binding']['sha256'] = '0' * 64
            elif name == 'review_policy_missing':
                walk(late, lambda value: value.pop('content_requirement_policy', None)
                     if value.get('kind') == 'fruth.semantic_review_evidence_binding' else None)
            elif name == 'requirement_version':
                revised_text = next(r['text'] for r in graph['content_requirements'] if r['role'] == 'consumer') + ' Include the value twice.'
                def change(value):
                    if value.get('requirement_id') and value.get('role') == 'consumer':
                        value['text'] = revised_text
                        value['sha256'] = hashlib.sha256(value['text'].encode()).hexdigest()
                walk(graph, change)
            elif name in {'source_version', 'output_version'}:
                target = source if name == 'source_version' else output
                target.write_bytes(originals[target] + b'\n')
            elif name == 'accounting_missing':
                def strip(value):
                    value.pop('content_requirements', None)
                    value.pop('content_requirement_policy', None)
                walk(graph, strip)
            elif name == 'obligation_accounting_missing':
                for r in graph['request_ir']['output_obligations']:
                    (r.get('artifact_request') or {}).pop('content_requirements', None)
            elif name == 'malformed_accounting':
                graph['content_requirements'] = {'unexpected': 'mapping'}
            elif name == 'malformed_requirement_id':
                graph['content_requirements'][0]['branch_id'] = {'unexpected': 'mapping'}
            elif name == 'criteria_removed':
                walk(graph, lambda value: (value.pop('review_criteria', None), value.pop('semantic_review_criteria', None)))
            with monkeypatch.context() as scoped:
                if name == 'insufficient_packet':
                    original_excerpt = semantics._global_semantic_text_artifact_excerpt
                    scoped.setattr(semantics, '_global_semantic_text_artifact_excerpt',
                        lambda path, *, byte_limit: original_excerpt(path, byte_limit=1))
                closure = semantics.build_graph_closure_review(candidate['output_text'],
                    request_payload=request, artifact_payload=candidate)
                if name in {'requirement_version', 'output_version'}:
                    old_checks = {check['branch_id']: check
                                  for check in final['runtime']['graph_closure_review']['checks']
                                  if check.get('content_requirements')}
                    current_checks = {check['branch_id']: check for check in closure['checks']
                                      if check.get('content_requirements')}
                    assert current_checks.keys() == old_checks.keys()
                    binding_key = 'branch_semantic_review_evidence_binding'
                    if name == 'requirement_version':
                        # Accepted sibling duties are context in the exact review
                        # packet. Changing that contract invalidates both old
                        # generations, without making it the producer's own duty.
                        assert closure['unresolved_content_requirement_count'] == 2
                        for branch_id, current_check in current_checks.items():
                            previous = old_checks[branch_id]
                            assert current_check[binding_key]['sha256'] != previous[binding_key]['sha256']
                            assert current_check['content_coverage_status'] == 'unverified'
                            roles = {item['role'] for item in current_check['content_requirements']}
                            assert roles in ({'producer'}, {'consumer'})
                            same_requirements = current_check['content_requirements'] == previous['content_requirements']
                            assert same_requirements == (roles == {'producer'})
                    else:
                        # Output bytes are consumer evidence, not a change to
                        # accepted sibling duties: the producer review survives.
                        assert closure['unresolved_content_requirement_count'] == 1
                        for branch_id, current_check in current_checks.items():
                            previous = old_checks[branch_id]
                            producer = current_check['content_requirements'][0]['role'] == 'producer'
                            assert current_check['content_requirements'] == previous['content_requirements']
                            if producer:
                                assert current_check[binding_key]['sha256'] == previous[binding_key]['sha256']
                                assert current_check['content_coverage_status'] == 'accepted_review'
                            else:
                                # Invalid physical output is rejected before a
                                # fresh semantic review binding can be issued.
                                assert binding_key not in current_check
                                assert current_check['content_coverage_status'] == 'unverified'
                                assert current_check['status'] != 'fulfilled'
                    assert not any(ch.get('reason') == 'content_requirement_accounting_missing_or_invalid'
                                   for ch in closure['checks'])
                if name == 'source_version':
                    assert closure['unresolved_content_requirement_count'] == 2
                expected_pass = False
                assert (closure['status'] == 'fulfilled') == expected_pass, (name, closure)
                if not expected_pass:
                    assert closure['unresolved_content_requirement_count'] > 0, name
                # Reconciliation and freeze may append successors; they must not
                # erase uncovered clauses or re-materialize a valid output.
                before = {p: p.read_bytes() for p in originals}
                settled, status = runtime.finalize_terminal_materialization_contract(
                    candidate, request_payload=request, route_payload=None, artifact_gap=None,
                    terminal_status='completed', accepted_fill_results=deepcopy(late['fill_results']))
                assert (status == 'completed') == expected_pass, (name, status)
                assert before == {p: p.read_bytes() for p in originals}, name
                frozen = harness.freeze_manual_response(settled, request_payload=request)
                parent_frame = frozen['response_frame']
                assert ledger.read_bytes().startswith(original_ledger)
                if not expected_pass:
                    assert frozen['lifecycle_state'] != 'completed', name
                assert_compact_readback(harness, final['id'], summary(settled))
                report['controls'].append({'name': name, 'closure': summary(settled), 'terminal_status': status})
                dump(control_root / 'observation.json', report['controls'][-1])
            for p, raw in originals.items():
                p.write_bytes(raw)
    run_native(monkeypatch, label='current-evidence', probe=probe)


def test_native_admission_rebuild_and_historical_policy(monkeypatch):
    from fruth_services.responses import capture_request_intent, restore_request_intent, request_intent_frame_source
    import fruth_inference.request_phase_graph as graph_owner
    prompt = requirements(case())['prompt']
    request = capture_request_intent({'prompt': prompt})
    graph = graph_owner.build_request_phase_graph(prompt, request_payload=request)
    accepted = deepcopy(graph['content_requirements'])
    monkeypatch.setattr(graph_owner, 'detect_text_artifact_requests', lambda *a, **kw: [])
    rebuilt = graph_owner.build_request_phase_graph('Reduced preparation.', request_payload=request,
        response_payload={'output_text': 'Only result.html is needed.', 'runtime': {'request_phase_graph': graph}})
    assert rebuilt['content_requirements'] == accepted
    assert {r['role'] for o in rebuilt['output_obligations']
            for r in (o.get('artifact_request') or {}).get('content_requirements', [])} == {'producer', 'consumer'}
    restored = restore_request_intent(request_intent_frame_source(request))
    assert graph_owner.build_request_phase_graph(prompt, request_payload=restored,
        response_payload={'runtime': {'request_phase_graph': graph}})['content_requirements'] == accepted
    monkeypatch.undo()
    legacy = restore_request_intent({'prompt': prompt, 'intent_source': 'runtime_caller_capture_v1'})
    historical = graph_owner.build_request_phase_graph(prompt, request_payload=legacy)
    assert historical['downstream_branches']
    assert 'content_requirement_policy' not in historical
    assert not any((o.get('artifact_request') or {}).get('content_requirements') for o in historical['output_obligations'])


def test_unaffected_ordinary_response():
    root, _ = reserve('coverage-ordinary', case(), 'control')
    from tests.fake_backends import FakeBackendHarness
    with FakeBackendHarness(root=root / 'runtime') as harness:
        payload, status = harness.post_response({'prompt': 'Say hello briefly.', 'inference_route': True})
        assert status == 200
        response_id = payload.get('id') or payload.get('response_id')
        state = harness.response_state(response_id)
        assert state['ok']
        assert state['response_payload']['lifecycle_state'] == 'completed'
        closure = state['response_payload'].get('runtime', {}).get('graph_closure_review', {})
        assert not closure.get('content_requirement_policy')
        assert not closure.get('semantic_review_required_count')
        assert harness.snapshot_counts()['backend_calls'] == 1
