"""Bounded offline A6 study. Use scripts/run_tests.py before any runtime imports."""
from copy import deepcopy
import hashlib
import inspect
import json
import os
from pathlib import Path
import threading
import time

import pytest
from tests.consumer_evidence_model import case, requirements, provider_html, oracle
from tests.test_consumer_evidence_a2 import reserve, dump
from tests.test_content_requirement_completion import summary
from tests.conditional_progress_model import schedule, expected, violations, sensitivity, model_trace, corpus, SEED


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def run_scenario(monkeypatch, label, s, category='control', injected_stall=False):
    c = case(variant=int(s['reverse']))
    c['schedule'] = s
    root, start = reserve('a6-' + label, c, category)
    req = requirements(c)
    report = dict(start=start, schedule=s, expected=expected(s), events=[], status='running',
                  admitted_roles=[], durable_review_roles=[], covered_roles=[], attempt_budget_changed=False,
                  interventions=['Synthetic inventory/capacity; controlled artifact/reviewer transport.',
                                 'Native admission, promotion, selection, preparation, dispatch, reconciliation and persistence.',
                                 'No review criteria or completed review records injected.'])
    lock = threading.Lock()
    release = threading.Event()
    entered = threading.Event()
    done = threading.Event()
    workers, errors = [], []
    observing = False
    identities = {}
    def event(kind, **data):
        with lock:
            assert len(report['events']) < 32, 'A6 transition budget exceeded'
            report['events'].append(dict(index=len(report['events']) + 1, kind=kind,
                                         monotonic=time.monotonic(), **data))
    try:
        import fruth_webserver as web
        import fruth_server.late_fill_runtime as late_module
        from fruth_inference.request_phase_graph import build_request_phase_graph
        from fruth_services.responses import capture_request_intent
        from tests.fake_backends import FakeBackendHarness
        from tests.test_saved_file_consumer_path import owner_for, saved
        with FakeBackendHarness(root=root / 'runtime') as harness, monkeypatch.context() as scoped:
            docs = harness.documents_dir
            runtime = web._LATE_FILL_RUNTIME
            resolver = owner_for(docs).resolve_saved_file_input_path
            scoped.setattr(runtime, 'resolve_saved_file_input_path', resolver)
            scoped.setattr(web, '_resolve_saved_viewable_artifact_path', resolver)
            scoped.setattr(web, 'ARTIFACT_OUTPUTS_DOCUMENTS_DIR', docs)
            scoped.setattr(late_module, 'ARTIFACT_OUTPUTS_DOCUMENTS_DIR', docs)
            harness.instances['chat']['runtime_status'].update(process_alive=True, port_listening=True)
            if s['capacity'] == 2:
                other = deepcopy(harness.instances['chat'])
                other['instance_id'] = other.get('instance_id', 'fake-chat') + '-a6-second'
                other['id'] = other['instance_id']
                other['port'] = 32999
                harness.instances['chat_a6_second'] = other
            def available(value):
                for key in ('chat', 'chat_a6_second'):
                    if key in harness.instances:
                        harness.instances[key]['runtime_status'].update(process_alive=value, port_listening=value)
            request = capture_request_intent({'prompt': req['prompt'], 'inference_route': True})
            graph = build_request_phase_graph(req['prompt'], request_payload=request,
                                             response_payload={'output_text': 'Preparation complete.'})
            accepted = deepcopy(graph['content_requirements'])
            assert {r['role'] for r in accepted} == {'producer', 'consumer'}
            report['accepted_requirements'] = accepted
            role_for_source = {r['branch_id']: r['role'] for r in accepted}
            payload = dict(id='a6-' + label, object='response', capability='chat', output_text='Preparation complete.',
                           runtime={'request_phase_graph': graph},
                           late_fill={'status': 'pending', 'pending_branches': graph['downstream_branches'],
                                      'pending_capabilities': ['chat']})
            def backend(*, payload, upload):
                ar = payload.get('artifact_request') or (payload.get('execution_contract') or {}).get('artifact_request') or {}
                if ar.get('extension'):
                    if ar['extension'] == 'json':
                        body = json.dumps(req['data'], sort_keys=True, separators=(',', ':'))
                    else:
                        raw = payload['prompt'].split('--- SAVED FILE START ---\n')[1].split('\n--- SAVED FILE END ---')[0]
                        assert json.loads(raw) == req['data']
                        body = provider_html(json.loads(raw), c)
                        if s['mode'] == 'absent_before_promotion':
                            available(False)
                    path = saved(docs, ar['source_name'], ar['extension'], body)
                    return {'saved_text_path': path, 'content': body,
                            'saved_text_artifacts': [{'path': path, 'text_artifact_request': ar}]}, 200
                packet = json.JSONDecoder().raw_decode(payload['prompt'].split('Branch runtime evidence:\n', 1)[1])[0]
                coverage = packet['content_coverage']
                role = coverage['requirements'][0]['role']
                assert coverage['complete']
                assert not observing
                event('transport_dispatch', role=role, review_id=identities[role]['branch_id'], packet_sha256=digest(packet))
                report.setdefault('packets', {})[role] = packet
                if s['mode'] == 'held_call' and role == 'producer':
                    entered.set()
                    assert release.wait(5), 'held fixture call was not released'
                if s['delay'] == role:
                    time.sleep(0.05)
                negative = s['negative'] == role
                criteria = packet['branch_check']['semantic_review_criteria']
                result = {'kind': 'fruth.semantic_review_verdict', 'verdict': 'failed' if negative else 'passed',
                          'overall_status': 'blocked' if negative else 'fulfilled',
                          'whole_intent_fit': 'Controlled offline review; A2 remains an assumption.',
                          'criterion_results': [] if s['incomplete'] == role else [
                              {'criterion': cr, 'status': 'failed' if negative else 'passed',
                               'evidence_refs': [packet['source_branch_id']]} for cr in criteria],
                          'evidence_refs': [packet['source_branch_id']],
                          'defects': ['controlled negative'] if negative else [],
                          'recommended_transition': 'manual_review' if negative else 'truthful_freeze'}
                event('transport_return', role=role, verdict=result['verdict'], incomplete=s['incomplete'] == role)
                return {'content': json.dumps(result)}, 200
            scoped.setattr(web, '_invoke_internal_api_json_route', backend)
            scoped.setitem(web.app.config, 'TESTING', True)
            with web.app.app_context():
                runtime.complete_response_late_fill(response_payload=payload, request_payload=request,
                    assistant_message=payload['output_text'], artifact_gap={
                        'pending_branches': graph['downstream_branches'], 'pending_capabilities': ['chat'],
                        'expected_capability': 'chat'}, source_route_payload=None)
            initial = runtime.get_response_lookup_record(payload['id'])['response_payload']
            assert summary(initial)['unresolved_content_requirement_count'] == 2
            event('native_artifacts_and_promotion', boundary=True)
            pending = deepcopy(initial['late_fill'].get('pending_branches') or [])
            report['admitted_reviews'] = pending
            for b in pending:
                binding = runtime._content_review_binding(b)
                assert binding, b
                role = role_for_source[binding['source_branch_id']]
                identities[role] = dict(branch_id=b['branch_id'], phase_id=b.get('phase_id'), binding=binding,
                                        attempt={k:v for k,v in b.items() if 'attempt' in k or 'retry_count' in k},
                                        max_attempts=runtime.auto_executable_repair_max_attempts(b),
                                        consumed_retries=int(b.get('auto_executable_repair_retry_count') or 0),
                                        execution_contract_sha256=digest(b.get('execution_contract')))
                assert identities[role]['max_attempts'] > identities[role]['consumed_retries']
            report['identities'] = deepcopy(identities)
            report['admitted_roles'] = sorted(identities)
            if s['mode'] == 'absent_before_promotion':
                assert not identities
            else:
                assert set(identities) == {'producer', 'consumer'}
            if s['reverse']:
                initial['late_fill']['pending_branches'].reverse()
                report['interventions'].append('Permute pending order only; exact identities/contracts unchanged.')
            scoped.setitem(web.app.config, 'TESTING', False)
            admitted = harness.freeze_manual_response(initial, request_payload=request)
            runtime.touch_response_lookup(payload['id'], response_payload=admitted)
            report['initial_frame_id'] = admitted['response_frame']['frame_id']
            artifacts = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in docs.iterdir() if p.is_file()}
            scoped.setitem(web.app.config, 'TESTING', False)
            original_select = runtime.select_active_late_fill_branches
            original_execute = runtime.execute_prepared_late_fill_branch
            original_terminal_guard = runtime._payload_has_terminal_closure_repair_execution
            source_lines, first_line = inspect.getsourcelines(type(runtime).complete_response_late_fill)
            selection_line = next(first_line + i for i,line in enumerate(source_lines)
                                  if 'active_branches, scheduling_policy = self.select_active_late_fill_branches(' in line)
            role_for_review = {v['branch_id']: k for k,v in identities.items()}
            def selection(branches, **kw):
                actual = inspect.currentframe().f_back.f_lineno == selection_line
                active, policy = original_select(branches, **kw)
                event('selection_opportunity' if actual else 'selection_projection',
                      eligible_input=[b['branch_id'] for b in branches], selected=[b['branch_id'] for b in active],
                      owner_line=inspect.currentframe().f_back.f_lineno, policy=policy)
                assert not observing
                if injected_stall and actual:
                    raise RuntimeError('isolated deliberate stalled selection sensitivity')
                return active, policy
            def execute(plan):
                role = role_for_review[plan['branch_id']]
                result = original_execute(plan)
                event('execution_settled', role=role, review_id=plan['branch_id'],
                      instance_id=(plan.get('instance') or {}).get('instance_id'),
                      binding=runtime._content_review_binding(result.get('infer_result') or {}))
                return result
            def terminal_guard(value, execution_key):
                decision = original_terminal_guard(value, execution_key)
                late = value.get('late_fill') or {}
                event('terminal_execution_guard', boundary=True, suppress=decision,
                      execution_key=execution_key,
                      pending=[b.get('branch_id') for b in late.get('pending_branches', [])],
                      terminal=[b.get('branch_id') for key in ('completed_branches', 'failed_branches', 'cancelled_branches')
                                for b in late.get(key, []) if b.get('terminal_closure_repair_execution_key') == execution_key])
                return decision
            scoped.setattr(runtime, 'select_active_late_fill_branches', selection)
            scoped.setattr(runtime, 'execute_prepared_late_fill_branch', execute)
            scoped.setattr(runtime, '_payload_has_terminal_closure_repair_execution', terminal_guard)
            def worker(**kwargs):
                workers.append(threading.current_thread())
                try:
                    with web.app.app_context():
                        runtime.complete_response_late_fill(**kwargs)
                except BaseException as exc:
                    errors.append(repr(exc))
                finally:
                    done.set()
            scoped.setattr(web, '_complete_response_late_fill', worker)
            def finish():
                assert done.wait(60), 'worker watchdog: inconclusive until diagnosed'
                for t in workers:
                    t.join(5)
                    assert not t.is_alive()
                assert not web._response_late_fill_is_in_flight(payload['id']), 'unexpected remaining claimed worker'
                if not injected_stall:
                    assert not errors, errors
                report['worker_errors'] = errors[:]
                done.clear()
            def current():
                return runtime.get_response_lookup_record(payload['id'])['response_payload']
            def observe(tag):
                nonlocal observing
                before = len(report['events'])
                ledger = harness.response_frames_dir / 'responses.jsonl'
                ledger_hash = hashlib.sha256(ledger.read_bytes()).hexdigest()
                durable_before = {str(p.relative_to(harness.response_frames_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in harness.response_frames_dir.rglob('*') if p.is_file()}
                state_before = summary(current())
                progress_before = digest(current().get('late_fill'))
                observing = True
                try:
                    for view in ('full', 'status'):
                        response, code = harness.get_response(payload['id'], view=view)
                        assert code == 200
                    assert hashlib.sha256(ledger.read_bytes()).hexdigest() == ledger_hash
                    assert durable_before == {str(p.relative_to(harness.response_frames_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
                                              for p in harness.response_frames_dir.rglob('*') if p.is_file()}
                    assert summary(current()) == state_before
                    assert digest(current().get('late_fill')) == progress_before
                    assert len(report['events']) == before
                finally:
                    observing = False
                event('passive_observation', boundary=True, tag=tag, ledger_sha256=ledger_hash)
            observe('before_activation')
            if s['mode'] in ('cancel', 'supersede'):
                with web.app.test_request_context():
                    reply = web._control_response_late_fill_branch(payload['id'], {
                        'branch_id': identities['consumer']['branch_id'], 'action': s['mode'],
                        'reason': 'A6 declared exact review disposition'})
                response, code = reply if isinstance(reply, tuple) else (reply, reply.status_code)
                report['control'] = {'code': code, 'body': response.get_json()}
                assert code == 200, report['control']
                event('authorized_disposition', role='consumer', action=s['mode'])
            if s['mode'] in ('lost_after_admission', 'retry_after_loss', 'retry_one', 'restored_before_activation'):
                available(False)
                event('capacity_lost')
            if s['mode'] == 'restored_before_activation':
                available(True)
                event('capacity_restored')
                observe('restoration_alone')
            if s['mode'] not in ('no_activation', 'absent_before_promotion'):
                handoff = runtime._terminal_closure_repair_handoff(current(), request_payload=request,
                    assistant_message=payload['output_text'], source_route_payload=None)
                assert handoff is not None
                event('scheduler_activation', action='terminal_closure_repair_handoff')
                with web.app.app_context():
                    assert runtime.schedule_response_late_fill(**handoff, complete_response_late_fill=worker)
                if s['mode'] == 'held_call':
                    assert entered.wait(30)
                    assert not any(e['kind'] == 'transport_return' and e.get('role') == 'producer' for e in report['events'])
                    event('termination_premise_absent', role='producer')
                    release.set()
                    event('fixture_release', role='producer')
                finish()
            if s['mode'] in ('retry_after_loss', 'retry_one'):
                report['capacity_failure'] = deepcopy(current()['late_fill'])
                available(True)
                event('capacity_restored')
                observe('restoration_alone')
                report['retries'] = []
                for role in s['retry_roles']:
                    bid = identities[role]['branch_id']
                    failed = current()['late_fill']['failed_branches']
                    assert any(b['branch_id'] == bid for b in failed), 'Exact owed review lost before scoped retry'
                    event('scheduler_activation', action='explicit_retry_endpoint', role=role, review_id=bid)
                    with web.app.test_request_context():
                        response, code = web._retry_response_late_fill_branch(payload['id'], {'branch_id': bid})
                    report['retries'].append(dict(role=role, code=code, body=response.get_json()))
                    assert code == 202, report['retries'][-1]
                    finish()
            final = current()
            report['final_late'] = deepcopy(final['late_fill'])
            report['summary'] = summary(final)
            report['lifecycle_state'] = final.get('lifecycle_state')
            observe('terminal')
            harness.clear_response_lookup()
            state = harness.response_state(payload['id'])
            assert state['ok']
            durable = state['response_payload']
            assert summary(durable) == report['summary']
            report['final_frame_id'] = state['response_frame']['frame_id']
            completed = {b['branch_id'] for b in durable['late_fill'].get('completed_branches', [])}
            results = {b['branch_id']: b for b in durable['late_fill'].get('fill_results', [])}
            for role, identity in identities.items():
                bid = identity['branch_id']
                for b in [*durable['late_fill'].get('completed_branches', []),
                          *durable['late_fill'].get('failed_branches', []),
                          *durable['late_fill'].get('pending_branches', [])]:
                    if b.get('branch_id') == bid:
                        report['attempt_budget_changed'] |= runtime.auto_executable_repair_max_attempts(b) != identity['max_attempts']
                if bid in completed and bid in results:
                    report['durable_review_roles'].append(role)
                    assert runtime._content_review_binding(results[bid]) == identity['binding']
            checks = durable['runtime']['graph_closure_review']['checks']
            report['covered_roles'] = sorted({r['role'] for ch in checks if ch.get('content_coverage_status') == 'accepted_review'
                                              for r in ch.get('content_requirements', [])})
            report['unresolved'] = summary(durable)['unresolved_content_requirement_count']
            report['content_oracle'] = oracle(req, (docs/'result.html').read_text(), list(artifacts))
            assert report['content_oracle']['correct']
            assert artifacts == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in docs.iterdir() if p.is_file()}
            event('durable_outcome', boundary=True, frame_id=report['final_frame_id'],
                  review_roles=report['durable_review_roles'], covered=report['covered_roles'])
            report['independent_model_trace'] = model_trace(s, report['events'])
            report['violations'] = violations(s, report)
            if injected_stall:
                assert report['violations']
                assert errors or 'isolated deliberate stalled selection sensitivity' in str(final['late_fill'].get('error'))
                report['status'] = 'expected_sensitivity_failure_detected'
            else:
                assert not report['violations'], report['violations']
                assert len([e for e in report['events'] if e['kind'] == 'selection_opportunity']) <= 4
                report['status'] = 'passed'
            if s == schedule() and not injected_stall:
                report['trace_sensitivity'] = sensitivity(s, report)
    except BaseException as exc:
        report.update(status='failed', exception=repr(exc))
        raise
    finally:
        release.set()
        for t in workers:
            t.join(5)
        report['workers_reaped'] = all(not t.is_alive() for t in workers)
        dump(root/'observation.json', report)
    return report


def test_positive(monkeypatch):
    run_scenario(monkeypatch, 'positive', schedule())


def test_stalled_sensitivity(monkeypatch):
    run_scenario(monkeypatch, 'stalled-sensitivity', schedule(), injected_stall=True)


def test_single_retry_scope(monkeypatch):
    run_scenario(monkeypatch, 'retry-one', schedule('retry_one'))


CONTROLS = [schedule(reverse=True, capacity=2, delay='producer'), schedule(negative='consumer'),
            schedule(incomplete='producer'), schedule('lost_after_admission'), schedule('absent_before_promotion'),
            schedule('restored_before_activation'), schedule('retry_after_loss'), schedule('cancel'),
            schedule('supersede'), schedule('no_activation'), schedule('held_call')]


@pytest.mark.parametrize('index', range(len(CONTROLS)))
def test_event_controls(monkeypatch, index):
    run_scenario(monkeypatch, 'event-' + str(index), CONTROLS[index])


def test_one_sealed_campaign(monkeypatch):
    entries = corpus()
    root = Path(os.environ['FRUTH_HYPOTHESIS_EVIDENCE_DIR'])
    sealed = {'seed': SEED, 'seeds': 4, 'generated_examples': 6, 'runtime_shrinks': 0, 'entries': entries}
    dump(root/'a6-corpus.json', sealed)
    dump(root/'a6-corpus-seal.json', {'sha256': hashlib.sha256((root/'a6-corpus.json').read_bytes()).hexdigest()})
    for entry in entries:
        run_scenario(monkeypatch, entry['label'], entry['schedule'], entry['category'])
