"""Bounded real-owner composition: persist/project/readback BEFORE consumption.

Run through scripts/run_tests.py. The corpus is sealed before runtime imports;
each actual start is reserved independently of Hypothesis generation/replay.
"""
from dataclasses import asdict
from datetime import datetime, timezone
import copy
import hashlib
import json
import os
from pathlib import Path
import time
from unittest.mock import patch

import pytest
from scripts.run_tests import storage_snapshot

from tests.runtime_composition_model import (
    Trace, assert_endpoint, canonical, controls, make_corpus, output_text, seal,
    sensitivity_observations, source_text, validate_trace,
)


def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def file_map(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def reserve_start(label, category, trace):
    """Aggregate actual starts, including failed controls/replay, before fixture I/O.

    Jobs are serial: refuse another incomplete runner job. Journals are read from
    the runner's declared disposable aggregate root, never production state.
    Native runner deadlines remain 600 seconds; task policy can be stricter.
    """
    job = Path(os.environ['FRUTH_COLD_PLAN'])
    evidence = Path(os.environ['FRUTH_HYPOTHESIS_EVIDENCE_DIR'])
    config = json.loads((job / 'run.json').read_text())
    storage = Path(config['storage_root'])
    assert job.parent == storage, 'study jobs must be direct aggregate children'
    policy_path = storage / 'budget.json'
    policy = json.loads(policy_path.read_text()) if policy_path.exists() else {}
    for other in storage.glob('*/job.json'):
        assert other.parent == job or (other.parent / 'completion.json').exists(), 'another job remains active'
    prior = []
    for journal in storage.glob('*/01-regression/examples/runtime-composition-starts.jsonl'):
        prior.extend(json.loads(line) for line in journal.read_text().splitlines())
    assert len(prior) < min(128, policy.get('actual_scenario_starts', 128)), 'aggregate scenario cap'
    local = [r for r in prior if r['job'] == job.name]
    assert len(local) < 32, 'local scenario cap'
    if category == 'generated':
        jobs = {r['job'] for r in prior if r['category'] == 'generated'} | {job.name}
        assert len(jobs) <= min(2, policy.get('max_campaigns', 2)), 'campaign cap'
    if policy.get('deadline_utc'):
        assert datetime.now(timezone.utc) < datetime.fromisoformat(policy['deadline_utc'].replace('Z', '+00:00')), 'task deadline'
    capacity = storage_snapshot(storage, stop_bytes=policy.get('stop_bytes'))
    assert capacity['stop_reason'] is None, capacity
    usage = capacity['allocated_bytes']
    record = {'ordinal': len(prior) + 1, 'job': job.name, 'label': label,
              'category': category, 'trace': asdict(trace), 'storage_bytes_before': usage}
    with (evidence / 'runtime-composition-starts.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(canonical(record) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    return evidence, record


def run_trace(label, trace, category):
    validate_trace(trace)
    # Semantic expectation is fixed before graph construction/provider output.
    required_text, required_output = source_text(trace), output_text(trace)
    evidence, start = reserve_start(label, category, trace)
    root = evidence / ('scenario-' + label)
    root.mkdir()
    report = {'start': start, 'trace': asdict(trace), 'transitions': [],
              'expected_source': required_text, 'expected_output': required_output,
              'classification': 'running', 'sensitivity': []}
    write_json(root / 'inputs.json', report.copy())
    def step(name):
        assert len(report['transitions']) < 32, 'actual transition cap'
        report['transitions'].append(name)
    try:
        # Guards were installed by the portable runner before this import.
        import fruth_webserver as web
        from fruth_inference.request_phase_graph import build_request_phase_graph
        from fruth_services.responses import build_canonical_response_artifacts
        from tests.fake_backends import FakeBackendHarness
        from tests.test_saved_file_consumer_path import owner_for, saved

        with FakeBackendHarness(root=root / 'runtime') as harness:
            documents = harness.documents_dir
            owner = owner_for(documents)
            prompt = ('Save numbers.json with values [' + ','.join(map(str, trace.values))
                      + ']. Read the actually saved file again. '
                      'Create result.html from the read data with the sum and embedded CSS.')
            graph = build_request_phase_graph(prompt, response_payload={'output_text': 'Preparation complete.'})
            report['accepted_graph'] = copy.deepcopy(graph)
            consumers = [b for b in graph['downstream_branches']
                         if b.get('artifact_request', {}).get('saved_file_dependency')]
            assert len(consumers) == 1
            consumer = consumers[0]
            producer_id = consumer['artifact_request']['saved_file_dependency']['producer_branch_id']
            producer = next(b for b in graph['downstream_branches'] if b['branch_id'] == producer_id)
            assert producer['artifact_request']['source_name'] == 'numbers'
            assert consumer['artifact_request']['source_name'] == 'result'
            assert consumer['depends_on'] == [producer['phase_id']]
            response_id = 'composition-' + label
            payload = {'id': response_id, 'object': 'response', 'capability': 'chat',
                       'output_text': 'UNTRUSTED ROOT: unrelated subject and values [1,1]',
                       'runtime': {'request_phase_graph': graph},
                       'late_fill': {'status': 'pending', 'fill_results': [],
                                     'pending_branches': [consumer], 'pending_capabilities': ['chat']}}
            step('accept_named_producer_consumer_contract')
            owner.invoke_internal_api_json_route = lambda **kw: ({
                'saved_text_path': saved(documents, 'numbers', 'json', required_text),
                'content': 'UNTRUSTED PROVIDER PROSE'}, 200)
            contract = owner.build_execution_contract(producer, producer, capability='chat')
            result = owner.execute_prepared_late_fill_branch({
                'response_id': response_id, 'capability': 'chat',
                'branch_id': producer['branch_id'], 'phase_id': producer['phase_id'],
                'execution_contract': contract, 'infer_payload': {'prompt': required_text}, 'effective_data': {}})['infer_result']
            step('execute_producer_and_save_actual_file')
            accepted = owner.attach_late_fill_result_artifact_identity(
                {**producer, **result}, payload, result, capability='chat')
            payload['late_fill']['fill_results'].append(accepted)
            payload['late_fill']['completed_branches'] = [{**producer, 'status': 'fulfilled'}]
            payload['artifacts'] = build_canonical_response_artifacts(payload)
            snapshot = copy.deepcopy(accepted['saved_file_output_snapshot'])
            step('attach_accepted_artifact_identity')
            expected = {'mode': 'delivered' if trace.defect in ('none', 'equal_bytes_sibling') and (
                trace.fallback or trace.view in ('truth', 'full')) else 'blocked',
                'defect': trace.defect, 'raw_text': required_text,
                'identity': {'response_id': response_id, 'source_response_id': response_id,
                    'producer_branch_id': producer['branch_id'], 'producer_phase_id': producer['phase_id'],
                    'consumer_branch_id': consumer['branch_id'], 'consumer_phase_id': consumer['phase_id'],
                    'branch_id': producer['branch_id'], 'phase_id': producer['phase_id'],
                    'artifact_ref': snapshot['artifact_ref'], 'artifact_id': snapshot['artifact_id'],
                    'path': str(documents / 'numbers.json')},
                'output_text': required_output, 'output_path': str(documents / 'result.html')}
            report['expected'] = expected
            if trace.defect in ('none', 'equal_bytes_sibling') and not trace.fallback and trace.view not in ('truth', 'full'):
                expected['mode'] = 'either'
                report['partial_view_allowed_outcomes'] = ['exact_delivery', 'explicit_unmet_prerequisite']
            write_json(root / 'accepted.json', {'producer': accepted, 'consumer': consumer, 'expected': expected})
            with patch.object(web, '_resolve_saved_viewable_artifact_path', owner.resolve_saved_file_input_path):
                frozen = harness.freeze_manual_response(payload, request_payload={'prompt': prompt, 'inference_route': True})
                step('finalize_and_persist_producer_frame')
                history = file_map(harness.response_frames_dir)
                artifact_history = file_map(harness.artifacts_dir)
                recovery_calls = []
                # Observation cannot acquire a claim or request execution.
                with patch.object(web, '_schedule_response_late_fill', side_effect=lambda *a, **k: recovery_calls.append('schedule')), \
                     patch.object(web, '_claim_response_late_fill', side_effect=lambda *a, **k: recovery_calls.append('claim')):
                    harness.clear_response_lookup()
                    published, status = harness.get_response(response_id, view=trace.view)
                    assert status == 200, published
                    step('publish_' + trace.view + '_after_lookup_clear')
                    canonical_state = harness.response_state(response_id)
                    assert canonical_state['ok'], canonical_state
                    canonical_payload = canonical_state['response_payload']
                    assert canonical_payload['late_fill']['fill_results'][0]['saved_file_output_snapshot'] == snapshot
                    recovered_branches = canonical_payload['runtime']['request_phase_graph']['downstream_branches']
                    recovered_consumer = next(b for b in recovered_branches if b['branch_id'] == consumer['branch_id'])
                    assert recovered_consumer['artifact_request'] == consumer['artifact_request']
                    assert recovered_consumer['depends_on'] == consumer['depends_on']
                    step('read_canonical_storage_and_verify_contract')
                    selected = copy.deepcopy(published)
                    if trace.fallback:
                        harness.clear_response_lookup()
                        selected, code = harness.get_response(response_id, view='truth')
                        assert code == 200, selected
                        step('select_canonical_truth_fallback')
                obs = {'calls': [], 'error': '', 'unresolved': False, 'final_receipt': {},
                       'canonical_preserved': history == file_map(harness.response_frames_dir),
                       'passive_no_execution': not recovery_calls and not harness.call_records
                           and not web._RESPONSE_LATE_FILL_IN_FLIGHT
                           and artifact_history == file_map(harness.artifacts_dir)}
                report.update(observation=obs, published=published,
                              frame_id=canonical_state['response_frame']['frame_id'],
                              accepted_snapshot=snapshot, history_sha256=history)
                # Mutations affect only the selected readback, or a saved current
                # file version; the accepted frozen history remains unchanged.
                records = selected.get('late_fill', {}).get('fill_results', [])
                record = next((r for r in records if r.get('branch_id') == producer['branch_id']), None)
                if record is not None:
                    if trace.defect == 'missing_snapshot': record.pop('saved_file_output_snapshot', None)
                    elif trace.defect == 'duplicate_producer': records.append(copy.deepcopy(record))
                    elif trace.defect == 'wrong_producer': record['branch_id'] = 'foreign-producer'
                    elif trace.defect == 'wrong_artifact':
                        artifacts = record.get('artifacts') or []
                        if artifacts:
                            artifacts[0]['artifact_ref'] = 'artifact:foreign'
                            report['witness_fault_application'] = 'artifact_ref_changed'
                        else:
                            # An honest partial view can already omit this
                            # witness. Do not invent it just to inject a fault.
                            report['witness_fault_application'] = 'unavailable_in_selected_view'
                if trace.defect in ('equal_bytes_other_artifact', 'equal_bytes_sibling'):
                    sibling_path = saved(documents, 'equal-copy', 'json', required_text)
                    sibling_result = {**copy.deepcopy(result), 'branch_id': 'sibling-producer',
                        'phase_id': 'sibling-phase', 'saved_text_path': sibling_path,
                        'saved_file_output_snapshot': {**snapshot, 'path': sibling_path}}
                    sibling_result.pop('artifacts', None)
                    sibling_result.pop('artifact_ref', None)
                    sibling_result.pop('artifact_id', None)
                    for key in ('artifact_ref', 'artifact_id', 'source_response_id', 'branch_id', 'phase_id'):
                        sibling_result['saved_file_output_snapshot'].pop(key, None)
                    sibling_record = owner.attach_late_fill_result_artifact_identity(
                        sibling_result, payload, sibling_result, capability='chat')
                    sibling_snapshot = sibling_record['saved_file_output_snapshot']
                    assert sibling_snapshot['artifact_ref'] != snapshot['artifact_ref']
                    assert Path(sibling_path).read_bytes() == (documents / 'numbers.json').read_bytes()
                    selected.setdefault('late_fill', {}).setdefault('fill_results', []).append(sibling_record)
                    report['equal_bytes_sibling'] = sibling_record
                    if trace.defect == 'equal_bytes_other_artifact' and record is not None:
                        record['saved_file_output_snapshot'] = copy.deepcopy(sibling_snapshot)
                if trace.defect == 'wrong_response': selected['id'] = 'foreign-response'
                selected_consumer = copy.deepcopy(consumer)
                if trace.defect == 'wrong_consumer': selected_consumer['phase_id'] = 'foreign-consumer-phase'
                source_path = documents / 'numbers.json'
                changed_text = canonical({**json.loads(required_text), 'version': trace.version + 10})
                if trace.defect == 'version_before_read': source_path.write_text(changed_text, encoding='utf-8')
                if trace.defect == 'missing_file': source_path.unlink()
                step('select_readback_witness_' + trace.defect)
                write_json(root / 'selected.json', selected)
                dependency = owner.branch_dependency_payload(selected_consumer, current_payload=selected)
                step('bind_actual_saved_file_dependency')
                report['dependency'] = dependency
                if dependency.get('materialization_blocked'):
                    obs.update(error=dependency.get('branch_contract_error', ''), unresolved=True)
                else:
                    gap = owner.attach_execution_contract_to_gap(consumer, {**consumer, **dependency}, capability='chat')
                    plan = {'response_id': response_id, 'capability': 'chat',
                            'branch_id': consumer['branch_id'], 'phase_id': consumer['phase_id'],
                            'execution_contract': gap['execution_contract'],
                            'infer_payload': {'prompt': owner._text_artifact_materialization_instruction('UNTRUSTED ROOT', gap)},
                            'effective_data': gap}
                    step('prepare_exact_consumer_packet')
                    if trace.defect == 'version_before_dispatch':
                        source_path.write_text(changed_text, encoding='utf-8')
                        step('change_saved_version_after_preparation')
                    if trace.defect == 'scope_before_dispatch':
                        plan['infer_payload']['text_artifact_requests'] = [
                            {'extension': 'html', 'source_name': 'result'},
                            {'extension': 'css', 'source_name': 'unrequested'}]
                    def consume(*, payload, upload):
                        # Provider knows only the submitted packet. It does not
                        # read trace, original source, expectations or source file.
                        call = {'prompt': payload['prompt'],
                                'read': {k: v for k, v in payload['input_refs'][0].items() if k != 'kind'},
                                'requests': copy.deepcopy(payload['text_artifact_requests'])}
                        obs['calls'].append(call)
                        raw = payload['prompt'].split('--- SAVED FILE START ---\n', 1)[1].split('\n--- SAVED FILE END ---', 1)[0]
                        data = json.loads(raw)
                        body = '<html><style>p{{margin:1em}}</style><body><h1>{}</h1><p>version={}</p><p>values={};sum={}</p></body></html>'.format(
                            data['subject'], data['version'], ','.join(map(str, data['values'])), sum(data['values']))
                        path = saved(documents, 'result', 'html', body)
                        call.update(output_path=path, output_text=Path(path).read_text())
                        return {'saved_text_path': path}, 200
                    owner.invoke_internal_api_json_route = consume
                    try:
                        consumed = owner.execute_prepared_late_fill_branch(plan)['infer_result']
                    except ValueError as exc:
                        obs.update(error=str(exc), unresolved=True)
                    else:
                        obs['final_receipt'] = consumed['saved_file_consumption_evidence']
                        assert obs['calls'][0]['requests'] == [{'extension': 'html', 'source_name': 'result'}]
                        report['native_consumption_error'] = owner.saved_file_consumption_error(
                            consumer, consumed, current_payload=selected)
                    step('explicit_separate_consumer_dispatch')
                obs['canonical_preserved'] &= history == file_map(harness.response_frames_dir)
                # Partial views promise bounded observation, not a complete
                # executable witness. Either exact delivery or explicit unmet is
                # legal; truth/fallback controls must positively execute.
                report['outcome'] = 'delivered' if obs['calls'] else 'blocked'
                assert_endpoint(obs, expected)
                for name, bad in sensitivity_observations(obs):
                    with pytest.raises(AssertionError):
                        assert_endpoint(bad, expected)
                    report['sensitivity'].append(name)
                step('independent_endpoint_and_sensitivity_checks')
                report['classification'] = 'passed'
    except BaseException as exc:
        report.update(classification='failed_requires_classification', error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        write_json(root / 'result.json', report)
    return report


@pytest.mark.parametrize('label,trace', controls(), ids=[label for label, _ in controls()])
def test_composition_controls(label, trace):
    run_trace(label, trace, 'control')


def test_retained_partial_witness_fixture_replay():
    # Exact campaign-01 generated-10 input. Original failure remains in its
    # frozen source/job; this is an injector correction, not a product fix.
    run_trace('replay-partial-witness', Trace(view='ui', fallback=False,
        defect='wrong_artifact', values=(19, 40), subject='alpha', version=1), 'replay')


def test_one_sealed_composition_campaign():
    evidence = Path(os.environ['FRUTH_HYPOTHESIS_EVIDENCE_DIR'])
    generated_at = time.monotonic()
    sealed = seal(make_corpus())
    write_json(evidence / 'composition-corpus.json', sealed)
    corpus = json.loads(sealed['content'])
    assert len(corpus['entries']) <= 32
    started = time.monotonic()
    summary = {'corpus_sha256': sealed['sha256'], 'generation_seconds': started - generated_at,
               'seed': corpus['seed'], 'hypothesis_examples': corpus['generated_examples'],
               'sealed_before_runtime_construction': True, 'completed': [], 'classification': 'running'}
    try:
        for entry in corpus['entries']:
            assert time.monotonic() - started < 600, 'campaign deadline'
            data = entry['trace']
            trace = Trace(**{**data, 'values': tuple(data['values'])})
            result = run_trace(entry['identity'], trace, 'generated')
            summary['completed'].append({'identity': entry['identity'], 'origin': entry['origin'],
                'transitions': len(result['transitions']), 'outcome': result['outcome']})
        summary['classification'] = 'passed'
    except BaseException as exc:
        summary.update(classification='failed_requires_classification', error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        summary['execution_seconds'] = time.monotonic() - started
        write_json(evidence / 'composition-campaign.json', summary)
