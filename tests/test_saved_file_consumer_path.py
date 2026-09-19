"""Isolated save/read/consume owner chain; deterministic transport, no models."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from fruth_core.transports import persist_text_artifact_locally
from fruth_inference.request_phase_graph import build_request_phase_graph
from fruth_server.late_fill_runtime import LateFillRuntimeOwner
from fruth_services.responses import build_canonical_response_artifacts
from fruth_inference.request_meta import extract_request_meta
from fruth_server.response_semantics_runtime import ResponseSemanticsRuntimeOwner

PROMPT = ('Save numbers.json with values [7,11]. Read the actually saved file again. '
          'Create result.html from the read data with the sum and embedded CSS.')


def owner_for(root):
    owner = object.__new__(LateFillRuntimeOwner)
    owner.normalize_capability = lambda value: value
    owner.branch_capability = lambda branch: branch.get('capability')
    owner.branch_id = lambda branch: str(branch.get('branch_id') or '')
    owner.capability_chat = 'chat'
    owner.artifact_type_for_capability = lambda capability: 'text'
    owner.capability_text_to_speech = 'text_to_speech'
    owner.build_canonical_response_artifacts = build_canonical_response_artifacts
    owner.filter_responses_infer_result = lambda result, **kw: result
    owner.resolve_saved_file_input_path = lambda value: (
        Path(value).resolve() if Path(value).resolve().is_relative_to(root) else None)
    return owner


def saved(root, name, extension, text):
    return persist_text_artifact_locally(text, model_name='offline-fixture', source_name=name,
        mode='isolated', extension=extension, output_dir=root,
        target_path=str(root / f'{name}.{extension}'))


def setup_producer(root):
    graph = build_request_phase_graph(PROMPT, response_payload={'output_text':'Preparation complete.'})
    branches = {b.get('text_artifact_extension'): b for b in graph['downstream_branches']}
    producer, consumer = branches['json'], branches['html']
    assert consumer['artifact_request'].get('saved_file_dependency'), 'positive contract missing'
    assert consumer['depends_on'] == [producer['phase_id']]
    owner = owner_for(root)
    payload = {'id': 'response-isolated', 'output_text': 'WRONG PREPARATION [1,1]',
               'runtime': {'request_phase_graph': graph}, 'late_fill': {'fill_results': []}}
    owner.invoke_internal_api_json_route = lambda **kw: ({'saved_text_path': saved(
        root, 'numbers', 'json', '{"values":[7,11]}'), 'content': 'WRONG MODEL PROSE'}, 200)
    contract = owner.build_execution_contract(producer, producer, capability='chat')
    plan = {'response_id': payload['id'], 'capability': 'chat', 'branch_id': producer['branch_id'], 'phase_id': producer['phase_id'],
            'execution_contract': contract, 'infer_payload': {'prompt': 'producer'}, 'effective_data': {}}
    result = owner.execute_prepared_late_fill_branch(plan)['infer_result']
    record = owner.attach_late_fill_result_artifact_identity(
        {**producer, **result}, payload, result, capability='chat')
    payload['late_fill']['fill_results'].append(record)
    return owner, graph, producer, consumer, payload


def run_consumer(root, owner, consumer, payload, *, mutate_transport=False):
    dependency = owner.branch_dependency_payload(consumer, current_payload=payload)
    assert not dependency.get('branch_contract_error'), dependency
    gap = owner.attach_execution_contract_to_gap(consumer, {**consumer, **dependency}, capability='chat')
    captured = []
    def consume(*, payload, upload):
        captured.append(copy.deepcopy(payload))
        # Parse only the bytes-derived packet actually handed to the consumer.
        text = payload['prompt'].split('--- SAVED FILE START ---\n', 1)[1].split('\n--- SAVED FILE END ---')[0]
        values = json.loads(text)['values']
        if mutate_transport:
            payload['prompt'] = 'transport mutated its request after consuming it'
        return {'saved_text_path': saved(root, 'result', 'html',
            '<html><style>td{padding:1px}</style><table>' + ''.join(
                f'<tr><td>{n}</td></tr>' for n in [*values, sum(values)]) + '</table></html>')}, 200
    owner.invoke_internal_api_json_route = consume
    plan = {'response_id': payload['id'], 'capability': 'chat', 'branch_id': consumer['branch_id'], 'phase_id': consumer['phase_id'],
            'execution_contract': gap['execution_contract'],
            'infer_payload': {'prompt': owner._text_artifact_materialization_instruction('WRONG ROOT PREPARATION', gap)}, 'effective_data': gap}
    result = owner.execute_prepared_late_fill_branch(plan)['infer_result']
    record = owner.attach_late_fill_result_artifact_identity(
        {**consumer, **result}, payload, result, capability='chat')
    payload['late_fill']['fill_results'].append(record)
    assert 'WRONG' not in captured[0]['prompt']
    return result, captured[0], dependency


def test_saved_file_positive_owner_chain(tmp_path):
    owner, graph, producer, consumer, payload = setup_producer(tmp_path)
    result, sent, dependency = run_consumer(tmp_path, owner, consumer, payload)
    evidence = result['saved_file_consumption_evidence']
    assert evidence['read']['sha256'] == hashlib.sha256((tmp_path/'numbers.json').read_bytes()).hexdigest()
    assert evidence['read']['artifact_ref'] == payload['late_fill']['fill_results'][0]['artifact_ref']
    assert evidence['read']['consumer_branch_id'] == consumer['branch_id']
    assert '<td>18</td>' in Path(result['saved_text_path']).read_text()
    assert owner.saved_file_consumption_error(consumer, result, current_payload=payload) is None
    semantics = ResponseSemanticsRuntimeOwner(hooks={
        'build_canonical_response_artifacts': build_canonical_response_artifacts,
        'normalize_capability_list': lambda values: values if isinstance(values, list) else [],
        'extract_request_meta': extract_request_meta,
        'extract_responses_prompt': lambda data: data.get('prompt', ''),
        'resolve_semantic_review_artifact_path': lambda path: Path(path),
        'load_running_instances': lambda: [],
        'merge_instances_with_runtime_status': lambda instances, **kw: instances,
    })
    payload['late_fill'].update(status='completed', final_materialization_contract_status='fulfilled',
        completed_branches=[{**b, 'status':'fulfilled'} for b in graph['downstream_branches']])
    review = semantics.build_graph_closure_review('done',
        request_payload={'prompt': PROMPT, 'inference_route': True}, artifact_payload=payload)
    check = next(c for c in review['checks'] if c.get('text_artifact_extension') == 'html')
    assert check['status'] == 'fulfilled', check
    assert check['evidence'] == 'saved_file_consumption_verified'
    assert review['status'] == 'fulfilled', review


@pytest.mark.parametrize('defect', ['missing', 'version', 'unauthorized', 'producer', 'phase', 'response', 'artifact', 'oversize', 'encoding'])
def test_saved_file_read_fails_closed(tmp_path, defect):
    owner, graph, producer, consumer, payload = setup_producer(tmp_path)
    record = payload['late_fill']['fill_results'][0]
    path = tmp_path/'numbers.json'
    if defect == 'missing': path.unlink()
    elif defect == 'version': path.write_text('{"values":[1,1]}')
    elif defect == 'unauthorized': owner.resolve_saved_file_input_path = lambda value: None
    elif defect == 'producer': record['branch_id'] = 'another'
    elif defect == 'phase': record['phase_id'] = 'another'
    elif defect == 'response': payload['id'] = 'another'
    elif defect == 'artifact': record['artifacts'][0]['artifact_ref'] = 'artifact:other'
    elif defect == 'oversize': path.write_bytes(b'x' * 90_001)
    elif defect == 'encoding': path.write_bytes(b'\xff')
    original = copy.deepcopy(payload)
    dependency = owner.branch_dependency_payload(consumer, current_payload=payload)
    assert dependency.get('materialization_blocked') is True, dependency
    assert 'content_payload' not in dependency
    assert payload == original


def test_regular_spec_and_plan_preserve_saved_input(tmp_path, monkeypatch):
    # The existing harness isolates all ledgers, logs and model transports.
    import fruth_webserver
    from tests.fake_backends import FakeBackendHarness
    owner, graph, producer, consumer, payload = setup_producer(tmp_path)
    original_transport = fruth_webserver._invoke_internal_api_json_route
    # Restore nested overrides before the harness restores the real transport.
    with FakeBackendHarness() as harness, monkeypatch.context() as scoped_patch:
        # This test routes through Late Fill to an injected fake transport.
        # Supply positive fake liveness so the real start gate can admit it.
        harness.instances['chat']['runtime_status'].update(process_alive=True, port_listening=True)
        runtime = fruth_webserver._LATE_FILL_RUNTIME
        scoped_patch.setattr(runtime, 'resolve_saved_file_input_path', owner.resolve_saved_file_input_path)
        spec = runtime.build_late_fill_materialization_branch_spec(
            branch=consumer, artifact_gap={}, current_payload=payload,
            request_payload={'prompt': PROMPT, 'inference_route': True}, assistant_message='WRONG PREPARATION',
            source_route_payload=None, failed_instance_id=None)
        assert spec
        plan = runtime.prepare_late_fill_branch_plan(**spec['prepare_args'])
        from fruth_services.artifact_contracts import saved_file_consumer_prompt
        assert plan['infer_payload']['prompt'] == saved_file_consumer_prompt(
            consumer['artifact_request']['saved_file_dependency'], plan['execution_contract']['saved_file_read_evidence'])
        assert plan['execution_contract']['saved_file_read_evidence']['sha256']
        assert plan['execution_contract']['input_refs'][0]['kind'] == 'saved_file_read'
        captured = []
        def consume(*, payload, upload):
            captured.append(payload)
            assert '--- SAVED FILE START ---' in payload['prompt']
            assert 'WRONG PREPARATION' not in payload['prompt']
            assert payload['text_artifact_requests'] == [{'extension':'html', 'source_name':'result'}]
            return {'saved_text_path': saved(tmp_path, 'result', 'html', '<html>7 11 18</html>')}, 200
        scoped_patch.setattr(fruth_webserver, '_invoke_internal_api_json_route', consume)
        result = runtime.execute_prepared_late_fill_branch(plan)['infer_result']
        assert len(captured) == 1
        assert runtime.dependency_evidence_error_for_branch_result(consumer, result, current_payload=payload) is None

    assert fruth_webserver._invoke_internal_api_json_route is original_transport


@pytest.mark.parametrize('field', ['artifact_ref', 'artifact_id', 'consumer_branch_id', 'consumer_phase_id', 'producer_branch_id', 'producer_phase_id', 'response_id'])
def test_packet_identity_mutation_never_reaches_consumer(tmp_path, field):
    owner, graph, producer, consumer, payload = setup_producer(tmp_path)
    dependency = owner.branch_dependency_payload(consumer, current_payload=payload)
    gap = owner.attach_execution_contract_to_gap(consumer, {**consumer, **dependency}, capability='chat')
    gap['execution_contract']['saved_file_read_evidence'][field] = 'wrong'
    owner.invoke_internal_api_json_route = lambda **kw: pytest.fail('misbound input executed')
    with pytest.raises(ValueError, match='saved_file_read_'):
        owner.execute_prepared_late_fill_branch({'response_id': payload['id'], 'capability': 'chat',
            'branch_id': consumer['branch_id'], 'phase_id': consumer['phase_id'],
            'execution_contract': gap['execution_contract'], 'infer_payload': {'prompt':'fallback'}})


def test_version_change_between_preparation_and_execution_is_rejected(tmp_path):
    owner, graph, producer, consumer, payload = setup_producer(tmp_path)
    dependency = owner.branch_dependency_payload(consumer, current_payload=payload)
    gap = owner.attach_execution_contract_to_gap(consumer, {**consumer, **dependency}, capability='chat')
    (tmp_path/'numbers.json').write_text('{"values":[2,2]}')
    owner.invoke_internal_api_json_route = lambda **kw: pytest.fail('changed input executed')
    with pytest.raises(ValueError, match='version_changed_before_consumption'):
        owner.execute_prepared_late_fill_branch({'response_id': payload['id'], 'capability': 'chat',
            'branch_id': consumer['branch_id'], 'phase_id': consumer['phase_id'],
            'execution_contract': gap['execution_contract'], 'infer_payload': {'prompt':'fallback'}})


@pytest.mark.parametrize('defect', ['missing', 'consumer', 'phase', 'target', 'digest', 'same_bytes_other_artifact', 'read_bytes', 'output'])
def test_consumption_evidence_must_match_exact_contract(tmp_path, defect):
    owner, graph, producer, consumer, payload = setup_producer(tmp_path)
    result, sent, dependency = run_consumer(tmp_path, owner, consumer, payload)
    bad = copy.deepcopy(result)
    if defect == 'missing': bad.pop('saved_file_consumption_evidence')
    elif defect == 'consumer': bad['branch_id'] = 'other'
    elif defect == 'phase': bad['phase_id'] = 'other'
    elif defect == 'target': bad['artifact_request']['source_name'] = 'other'
    elif defect == 'digest': bad['saved_file_consumption_evidence']['input_sha256'] = '0' * 64
    elif defect == 'same_bytes_other_artifact': bad['saved_file_consumption_evidence']['read']['artifact_ref'] = 'artifact:other'
    elif defect == 'read_bytes': bad['saved_file_consumption_evidence']['read']['utf8_base64'] = 'e30='
    elif defect == 'output': bad['saved_text_path'] = str(tmp_path/'other.html')
    assert owner.saved_file_consumption_error(consumer, bad, current_payload=payload)


@pytest.mark.parametrize('prompt', [
    'Save first.json and second.json. Read the saved file. Create page.html from the read data.',
    'Save first.json. Read the saved other.json. Create page.html from the read data.',
    'Save first.json. Read the saved CSV file. Create page.html from the read data.',
])
def test_ambiguous_or_wrong_named_read_stays_blocked(prompt):
    graph = build_request_phase_graph(prompt)
    consumer = next(b for b in graph['downstream_branches'] if b.get('text_artifact_extension') == 'html')
    assert consumer.get('branch_contract_error') == 'saved_file_dependency_unbound'
    assert not consumer['artifact_request'].get('saved_file_dependency')


def test_producer_is_not_coalesced_with_independent_outputs(tmp_path):
    owner, graph, producer, consumer, payload = setup_producer(tmp_path)
    assert owner._branch_spec_disables_required_text_artifact_coalescing({'branch': producer}, producer)
    assert owner._branch_spec_disables_required_text_artifact_coalescing({'branch': consumer}, consumer)


def test_exact_utf8_bytes_survive_contract_normalization(tmp_path):
    from fruth_services.artifact_contracts import read_saved_file_snapshot, saved_file_read_text
    owner = owner_for(tmp_path)
    path = tmp_path/'data.txt'
    raw = '  Größer\r\n\t7\n\n'.encode('utf-8')
    path.write_bytes(raw)
    read = read_saved_file_snapshot(str(path), owner.resolve_saved_file_input_path)
    contract = owner.build_execution_contract({'branch_id':'b', 'phase_id':'p'},
        {'saved_file_read_evidence':read}, capability='chat')
    assert saved_file_read_text(contract['saved_file_read_evidence']).encode('utf-8') == raw


def test_terminal_reconciliation_cannot_replace_read_evidence_by_file_existence(tmp_path):
    owner, graph, producer, consumer, payload = setup_producer(tmp_path)
    saved(tmp_path, 'result', 'html', '<html>7 11 18</html>')
    payload['artifacts'] = [{'type':'text', 'path':str(tmp_path/'result.html'), 'name':'result'}]
    assert not owner._text_artifact_branch_has_canonical_evidence(consumer, payload)


@pytest.mark.parametrize('extension', ['json', 'html'])
def test_preexecution_existing_files_require_saved_file_evidence(tmp_path, extension):
    owner, graph, producer, consumer, payload = setup_producer(tmp_path)
    html_path = saved(tmp_path, 'result', 'html', '<html><body>7 11 18</body></html>')
    payload['artifacts'] = [
        {'type': 'text', 'path': str(tmp_path/'numbers.json'), 'name': 'numbers', 'extension': 'json'},
        {'type': 'text', 'path': html_path, 'name': 'result', 'extension': 'html'},
    ]
    if extension == 'json':
        payload['late_fill']['fill_results'] = []
    branch = producer if extension == 'json' else consumer
    before = {p: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    assert owner._canonical_text_artifact_branch_fulfillment(branch, payload) == {}
    assert all(p.read_bytes() == data for p, data in before.items())


@pytest.mark.parametrize('extension', ['json', 'html'])
def test_preexecution_reuses_complete_proven_saved_file_result(tmp_path, extension):
    owner, graph, producer, consumer, payload = setup_producer(tmp_path)
    run_consumer(tmp_path, owner, consumer, payload)
    branch = producer if extension == 'json' else consumer
    original = next(r for r in payload['late_fill']['fill_results'] if r['branch_id'] == branch['branch_id'])
    unproven = copy.deepcopy(payload)
    unproven['late_fill']['fill_results'] = []
    reused = owner._canonical_text_artifact_branch_fulfillment(branch, unproven, payload)
    assert reused == original
    assert reused is not original
    recovered = copy.deepcopy(payload)
    recovered['late_fill']['fill_results'] = [
        reused if r['branch_id'] == branch['branch_id'] else r
        for r in recovered['late_fill']['fill_results']]
    assert owner._text_artifact_branch_has_canonical_evidence(branch, recovered)


def streamed_producer_draft(root, payload, content='{"values":[7,11]}'):
    draft_root = root / 'streamed'
    draft_root.mkdir()
    path = saved(draft_root, 'numbers', 'json', content)
    payload.setdefault('artifacts', []).append({
        'type': 'text', 'path': path, 'name': 'numbers', 'extension': 'json',
        'source_response_id': payload['id'], 'origin': 'assistant_output',
    })
    return Path(path)


@pytest.mark.parametrize('draft_content', ['{"values":[7,11]}', '{"values":[99]}'])
def test_producer_closure_uses_proven_file_among_streamed_drafts(tmp_path, draft_content):
    owner, graph, producer, consumer, payload = setup_producer(tmp_path)
    draft = streamed_producer_draft(tmp_path, payload, draft_content)
    before = copy.deepcopy(payload)
    files_before = {p: (p.read_bytes(), p.stat().st_mtime_ns)
                    for p in (draft, tmp_path / 'numbers.json')}
    assert owner._text_artifact_branch_has_canonical_evidence(producer, payload)
    reused = owner._canonical_text_artifact_branch_fulfillment(producer, payload)
    assert reused == payload['late_fill']['fill_results'][0]
    assert reused['saved_text_path'] == str(tmp_path / 'numbers.json')
    assert payload == before
    assert all((p.read_bytes(), p.stat().st_mtime_ns) == data for p, data in files_before.items())
    # Without a proven branch binding, multiple current files remain ambiguous.
    unbound = copy.deepcopy(producer)
    unbound['artifact_request'].pop('saved_file_producer')
    assert not owner._text_artifact_branch_has_canonical_evidence(unbound, payload)


@pytest.mark.parametrize('defect', [
    'changed_bytes', 'missing_file', 'wrong_identity', 'duplicate_result',
    'wrong_name', 'wrong_extension', 'wrong_target', 'invalid_syntax',
])
def test_producer_closure_does_not_substitute_draft_for_invalid_proof(tmp_path, defect):
    owner, graph, producer, consumer, payload = setup_producer(tmp_path)
    draft = streamed_producer_draft(tmp_path, payload)
    record = payload['late_fill']['fill_results'][0]
    target = tmp_path / 'numbers.json'
    if defect == 'changed_bytes':
        target.write_text('{"values":[0]}')
    elif defect == 'missing_file':
        target.unlink()
    elif defect == 'wrong_identity':
        record['artifacts'][0]['artifact_ref'] = 'artifact:wrong'
    elif defect == 'duplicate_result':
        payload['late_fill']['fill_results'].append(copy.deepcopy(record))
    elif defect == 'wrong_name':
        producer['text_artifact_source_name'] = 'other'
        producer['artifact_request']['source_name'] = 'other'
    elif defect == 'wrong_extension':
        producer['text_artifact_extension'] = 'csv'
        producer['artifact_request']['extension'] = 'csv'
    elif defect == 'wrong_target':
        producer['artifact_request']['target_path'] = str(draft)
    elif defect == 'invalid_syntax':
        target.write_text('{"values":')
        record['saved_file_output_snapshot'].update(
            sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            size_bytes=target.stat().st_size)
    assert not owner._text_artifact_branch_has_canonical_evidence(producer, payload)
    assert owner._canonical_text_artifact_branch_fulfillment(producer, payload) == {}


@pytest.mark.parametrize('defect', ['missing_snapshot', 'foreign_response', 'changed_bytes', 'ambiguous_result'])
def test_preexecution_rejects_unproven_saved_file_producer(tmp_path, defect):
    owner, graph, producer, consumer, payload = setup_producer(tmp_path)
    record = payload['late_fill']['fill_results'][0]
    if defect == 'missing_snapshot':
        record.pop('saved_file_output_snapshot')
    elif defect == 'foreign_response':
        payload['id'] = 'another-response'
    elif defect == 'changed_bytes':
        (tmp_path/'numbers.json').write_text('{"values":[0]}')
    else:
        payload['late_fill']['fill_results'].append(copy.deepcopy(record))
    assert owner._canonical_text_artifact_branch_fulfillment(producer, payload) == {}


def test_preexecution_unbound_saved_read_contract_stays_open(tmp_path):
    owner, graph, producer, consumer, payload = setup_producer(tmp_path)
    path = saved(tmp_path, 'result', 'html', '<html><body>7 11 18</body></html>')
    payload['artifacts'] = [{'type': 'text', 'path': path, 'name': 'result', 'extension': 'html'}]
    consumer['artifact_request'].pop('saved_file_dependency')
    consumer.pop('dependency_contract', None)
    consumer['branch_contract_error'] = 'saved_file_dependency_unbound'
    assert owner._canonical_text_artifact_branch_fulfillment(consumer, payload) == {}


@pytest.mark.parametrize('extension', ['json', 'html'])
def test_preexecution_ordinary_file_reuse_remains_available(tmp_path, extension):
    owner, graph, producer, consumer, payload = setup_producer(tmp_path)
    path = saved(tmp_path, 'result', 'html', '<html><body>ordinary output</body></html>')
    payload['artifacts'] = [
        {'type': 'text', 'path': str(tmp_path/'numbers.json'), 'name': 'numbers', 'extension': 'json'},
        {'type': 'text', 'path': path, 'name': 'result', 'extension': 'html'},
    ]
    branch = copy.deepcopy(producer if extension == 'json' else consumer)
    branch['artifact_request'].pop('saved_file_producer', None)
    branch['artifact_request'].pop('saved_file_dependency', None)
    branch.pop('dependency_contract', None)
    branch['content_payload_source'] = 'current_phase_output'
    result = owner._canonical_text_artifact_branch_fulfillment(branch, payload)
    assert result['saved_text_path'] == str(tmp_path/('numbers.json' if extension == 'json' else 'result.html'))
    assert owner._text_artifact_branch_has_canonical_evidence(branch, payload)


@pytest.mark.parametrize('defect', ['prompt', 'scope', 'backend_error', 'wrong_output'])
def test_handoff_and_consumer_failures_are_explicit(tmp_path, defect):
    owner, graph, producer, consumer, payload = setup_producer(tmp_path)
    dependency = owner.branch_dependency_payload(consumer, current_payload=payload)
    gap = owner.attach_execution_contract_to_gap(consumer, {**consumer, **dependency}, capability='chat')
    prompt = owner._text_artifact_materialization_instruction(PROMPT, gap)
    plan = {'response_id':payload['id'], 'capability':'chat', 'branch_id':consumer['branch_id'],
        'phase_id':consumer['phase_id'], 'execution_contract':gap['execution_contract'],
        'infer_payload':{'prompt':prompt}, 'effective_data':gap}
    if defect == 'prompt': plan['infer_payload']['prompt'] = 'truncated or root replacement'
    if defect == 'scope': plan['infer_payload']['text_artifact_requests'] = [
        {'extension':'html', 'source_name':'result'}, {'extension':'css', 'source_name':'extra'}]
    def backend(**kw):
        if defect in {'prompt', 'scope'}: pytest.fail('invalid handoff invoked')
        if defect == 'backend_error': return {'error':'isolated transport error'}, 503
        return {'saved_text_path':saved(tmp_path, 'wrong', 'html', '<html>wrong target</html>')}, 200
    owner.invoke_internal_api_json_route = backend
    with pytest.raises((ValueError, RuntimeError)):
        owner.execute_prepared_late_fill_branch(plan)
    assert 'saved_file_consumption_evidence' not in plan


@pytest.mark.parametrize('defect', ['missing_contract', 'missing_read', 'malformed', 'modified_output', 'modified_source', 'wrong_output_identity'])
def test_terminal_evidence_controls(tmp_path, defect):
    from fruth_services.artifact_contracts import saved_file_consumption_artifact_issue
    owner, graph, producer, consumer, payload = setup_producer(tmp_path)
    result, sent, dependency = run_consumer(tmp_path, owner, consumer, payload)
    record = payload['late_fill']['fill_results'][-1]
    if defect == 'missing_contract': consumer['artifact_request'].pop('saved_file_dependency')
    elif defect == 'missing_read': record['saved_file_consumption_evidence'].pop('read')
    elif defect == 'malformed': record['saved_file_consumption_evidence'] = 'claim only'
    elif defect == 'modified_output': (tmp_path/'result.html').write_text('<html>changed</html>')
    elif defect == 'modified_source': (tmp_path/'numbers.json').write_text('{"values":[0]}')
    elif defect == 'wrong_output_identity': record['artifacts'][0]['artifact_id'] = 'other'
    assert saved_file_consumption_artifact_issue(consumer, payload, owner.resolve_saved_file_input_path)
    assert not owner._text_artifact_branch_has_canonical_evidence(consumer, payload)

    assert owner._canonical_text_artifact_branch_fulfillment(consumer, payload) == {}


def test_saved_read_evidence_survives_isolated_frame_storage(tmp_path, monkeypatch):
    import fruth_webserver
    from tests.fake_backends import FakeBackendHarness
    from fruth_services.artifact_contracts import saved_file_consumption_artifact_issue
    owner, graph, producer, consumer, payload = setup_producer(tmp_path)
    result, sent, dependency = run_consumer(tmp_path, owner, consumer, payload)
    payload['artifacts'] = build_canonical_response_artifacts(payload)
    payload['late_fill'].update(status='completed', final_materialization_contract_status='fulfilled',
        completed_branches=[{**b, 'status':'fulfilled'} for b in graph['downstream_branches']])
    hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.iterdir()}
    with FakeBackendHarness() as harness:
        monkeypatch.setattr(fruth_webserver, '_resolve_saved_viewable_artifact_path', owner.resolve_saved_file_input_path)
        frozen = harness.freeze_manual_response(payload, request_payload={'prompt':PROMPT, 'inference_route':True})
        state = harness.response_state(payload['id'])
        assert state['ok'] is True
        hydrated = state['response_payload']
        assert not saved_file_consumption_artifact_issue(consumer, hydrated, owner.resolve_saved_file_input_path)
        assert hydrated['late_fill']['fill_results'][-1]['saved_file_consumption_evidence'] == result['saved_file_consumption_evidence']
    assert hashes == {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in hashes}


def test_scheduler_preserves_producer_before_consumer():
    from fruth_inference.request_phase_graph import downstream_phase_branch_batches
    graph = build_request_phase_graph(PROMPT, response_payload={'output_text':'Preparation complete.'})
    batches = downstream_phase_branch_batches(graph)
    branches = {b['text_artifact_extension']:b for b in graph['downstream_branches']}
    batch_for = {b['branch_id']: index for index, batch in enumerate(batches) for b in batch}
    assert batch_for[branches['json']['branch_id']] < batch_for[branches['html']['branch_id']]


def test_later_consumer_constraints_are_preserved():
    graph = build_request_phase_graph(
        'Save input.json. Read the saved input.json. Create output.html from the read data. '
        'Self-contained with embedded CSS; no external resources.')
    consumer = next(b for b in graph['downstream_branches'] if b.get('text_artifact_extension') == 'html')
    assert 'no external resources' in consumer['artifact_request']['saved_file_dependency']['consumer_instruction']


def test_standalone_prior_output_constraints_are_not_root_replay():
    graph = build_request_phase_graph(
        'Self-contained HTML with embedded CSS; no external resources. '
        'Save input.json with values [19,23]. Read the saved file. '
        'Create output.html from the read data.')
    consumer = next(b for b in graph['downstream_branches'] if b.get('text_artifact_extension') == 'html')
    instruction = consumer['artifact_request']['saved_file_dependency']['consumer_instruction']
    assert 'Self-contained HTML with embedded CSS' in instruction
    assert 'no external resources' in instruction
    assert '19,23' not in instruction
    assert 'Save input.json' not in instruction


@pytest.mark.parametrize('producer_verb,early_files,missing_result', [
    ('Save', False, False), ('Create', False, False),
    ('Save', True, False), ('Create', True, False),
    ('Save', 'distinct_paths', False), ('Create', 'distinct_paths', False),
    ('Save', False, True),
])
def test_complete_late_fill_executes_save_then_read_consumer(
    tmp_path, monkeypatch, producer_verb, early_files, missing_result
):
    import fruth_webserver
    import fruth_server.late_fill_runtime as late_module
    from tests.fake_backends import FakeBackendHarness
    from fruth_services.artifact_contracts import saved_file_consumption_artifact_issue
    prompt = PROMPT.replace('Save', producer_verb, 1)
    graph = build_request_phase_graph(prompt, response_payload={'output_text':'Preparation complete.'})
    branches = graph['downstream_branches']
    consumer = next(b for b in branches if b.get('text_artifact_extension') == 'html')
    payload = {'id':'isolated-complete-save-read', 'object':'response', 'capability':'chat',
        'output_text':'Preparation complete.', 'runtime':{'request_phase_graph':graph},
        'late_fill':{'status':'pending', 'pending_branches':branches, 'pending_capabilities':['chat']}}
    if early_files:
        early_root = tmp_path / 'streamed' if early_files == 'distinct_paths' else tmp_path
        early_root.mkdir(exist_ok=True)
        payload['output_text'] = '```json\n{"values":[7,11]}\n```\n```html\n<html><body>Unverified early output</body></html>\n```'
        payload['artifacts'] = [
            {'type': 'text', 'path': saved(early_root, name, extension, content),
             'name': name, 'extension': extension,
             'source_response_id': payload['id'], 'origin': 'assistant_output'}
            for name, extension, content in (
                ('numbers', 'json', '{"values":[7,11]}'),
                ('result', 'html', '<html><body>Unverified early output</body></html>'))]
    early_bytes = {Path(a['path']): Path(a['path']).read_bytes() for a in payload.get('artifacts', [])}
    calls = []
    original_transport = fruth_webserver._invoke_internal_api_json_route
    # Restore nested overrides before the harness restores the real transport.
    with FakeBackendHarness() as harness, monkeypatch.context() as scoped_patch:
        # This test routes through Late Fill to an injected fake transport.
        # Supply positive fake liveness so the real start gate can admit it.
        harness.instances['chat']['runtime_status'].update(process_alive=True, port_listening=True)
        runtime = fruth_webserver._LATE_FILL_RUNTIME
        resolver = owner_for(tmp_path).resolve_saved_file_input_path
        scoped_patch.setattr(runtime, 'resolve_saved_file_input_path', resolver)
        scoped_patch.setattr(fruth_webserver, '_resolve_saved_viewable_artifact_path', resolver)
        scoped_patch.setattr(fruth_webserver, 'ARTIFACT_OUTPUTS_DOCUMENTS_DIR', tmp_path)
        scoped_patch.setattr(late_module, 'ARTIFACT_OUTPUTS_DOCUMENTS_DIR', tmp_path)
        def backend(*, payload, upload):
            request = payload.get('artifact_request') or payload['execution_contract']['artifact_request']
            extension = request['extension']
            calls.append(extension)
            if extension == 'json':
                content = '{"values":[7,11]}'
            else:
                assert extension == 'html'
                raw = payload['prompt'].split('--- SAVED FILE START ---\n',1)[1].split('\n--- SAVED FILE END ---')[0]
                values = json.loads(raw)['values']
                content = '<html><style>td{padding:1px}</style><table>' + ''.join(
                    f'<tr><td>{n}</td></tr>' for n in [*values,sum(values)]) + '</table></html>'
            path = saved(tmp_path, request['source_name'], extension, content)
            return {'saved_text_path':path, 'content':content,
                'saved_text_artifacts':[{'path':path, 'text_artifact_request':request}]}, 200
        scoped_patch.setattr(fruth_webserver, '_invoke_internal_api_json_route', backend)
        if missing_result:
            execute = runtime.execute_materialization_branches
            lookup = runtime.get_response_lookup_record
            lost_consumer_result = []

            def execute_without_consumer_receipt(*args, **kwargs):
                materialized = execute(*args, **kwargs)
                result = materialized['branch_results'].pop(consumer['branch_id'], None)
                if result is not None:
                    lost_consumer_result.append(result)
                    materialized['branch_errors'][consumer['branch_id']] = {
                        'code': 'SAVED_FILE_CONSUMPTION_EVIDENCE_MISSING',
                        'message': 'Isolated consumer receipt loss after file creation.',
                        'retryable': False,
                    }
                return materialized

            def lookup_with_unproven_file(*args, **kwargs):
                record = copy.deepcopy(lookup(*args, **kwargs))
                if record and lost_consumer_result:
                    record['response_payload'].setdefault('artifacts', []).append({
                        'type': 'text', 'path': str(tmp_path/'result.html'),
                        'name': 'result', 'extension': 'html',
                    })
                return record

            scoped_patch.setattr(runtime, 'execute_materialization_branches', execute_without_consumer_receipt)
            scoped_patch.setattr(runtime, 'get_response_lookup_record', lookup_with_unproven_file)
        scoped_patch.setitem(fruth_webserver.app.config, 'TESTING', True)
        request = {'prompt':prompt, 'inference_route':True}
        with fruth_webserver.app.app_context():
            runtime.complete_response_late_fill(response_payload=payload, request_payload=request,
                assistant_message=payload['output_text'], artifact_gap={
                    'pending_branches':branches, 'pending_capabilities':['chat'], 'expected_capability':'chat'},
                source_route_payload=None)
        assert not fruth_webserver._RESPONSE_LATE_FILL_IN_FLIGHT
        record = runtime.get_response_lookup_record(payload['id'])
        assert record and record.get('response_payload'), record
        final = record['response_payload']
        assert calls == ['json', 'html'], final.get('late_fill')
        if missing_result:
            assert lost_consumer_result
            assert all(r['branch_id'] != consumer['branch_id'] for r in final['late_fill']['fill_results'])
            assert saved_file_consumption_artifact_issue(consumer, final, resolver)
            assert final['lifecycle_state'] != 'completed'
        else:
            assert not saved_file_consumption_artifact_issue(consumer, final, resolver), final.get('late_fill')
            assert final['late_fill']['status'] == 'completed', final.get('late_fill')
            assert final['lifecycle_state'] == 'completed', final.get('runtime', {}).get('graph_closure_review')
        assert '<td>18</td>' in (tmp_path/'result.html').read_text()
        # TESTING suppresses automatic persistence as well as background workers.
        # Round-trip the actual settled worker result explicitly in the temp store.
        scoped_patch.setitem(fruth_webserver.app.config, 'TESTING', False)
        harness.freeze_manual_response(final, request_payload=request)
        state = harness.response_state(payload['id'])
        assert state['ok'], state
        hydrated = state['response_payload']
        assert hydrated['lifecycle_state'] == final['lifecycle_state']
        assert [r.get('saved_file_consumption_evidence') for r in hydrated['late_fill']['fill_results']] == [
            r.get('saved_file_consumption_evidence') for r in final['late_fill']['fill_results']]
        if early_files == 'distinct_paths':
            assert all(path.read_bytes() == content for path, content in early_bytes.items())
            assert {a['path'] for a in hydrated['artifacts']} == {
                str(tmp_path / 'numbers.json'), str(tmp_path / 'result.html')}
            assert hydrated['late_fill']['final_materialization_contract_status'] == 'fulfilled'
            assert hydrated['runtime']['graph_closure_review']['status'] == 'fulfilled'
        assert not fruth_webserver._RESPONSE_LATE_FILL_IN_FLIGHT
    assert fruth_webserver._invoke_internal_api_json_route is original_transport



def test_input_digest_is_captured_before_transport_invocation(tmp_path):
    owner, graph, producer, consumer, payload = setup_producer(tmp_path)
    result, sent, dependency = run_consumer(tmp_path, owner, consumer, payload, mutate_transport=True)
    assert result['saved_file_consumption_evidence']['input_sha256'] == hashlib.sha256(sent['prompt'].encode('utf-8')).hexdigest()
    assert owner.saved_file_consumption_error(consumer, result, current_payload=payload) is None
