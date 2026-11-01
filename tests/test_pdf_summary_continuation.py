"""PDF result evidence cannot create edit authority or change a repair's phase."""
from copy import deepcopy

import pytest

from fruth_inference.request_phase_graph import build_request_phase_graph
from fruth_server.responses_runtime import ResponseMutationConflict, require_response_mutation_target
from fruth_server.terminal_repair_projection import TerminalRepairProjection
from fruth_services.closure_repair_feedback import build_inference_repair_feedback


PROMPT = ('Read every page of the attached PDF in order. Give a short summary for each page, '
          'clearly identifying its page number. Include information visible in scanned pages. '
          'Explicitly identify unreadable or blank pages instead of guessing. '
          'Finish by stating which pages you processed.')


@pytest.mark.parametrize('carrier', ['saved_text_path', 'artifact_path', 'output_text'])
def test_current_pdf_report_does_not_create_a_revision_obligation(tmp_path, carrier):
    report = tmp_path/'ocr-report.md'; report.write_text('[Page 1]\nText\n[Page 2]\nScanned text')
    request = {'prompt': PROMPT, 'inference_route': True,
               'input_artifacts': [{'type': 'document', 'path': str(tmp_path/'input.pdf')}]}
    response = {'capability': 'vision_analysis', 'content': 'Pages 1 and 2 processed.',
                'pdf_processed_pages': 2, 'pdf_total_pages': 2,
                carrier: ('```markdown\nA page summary\n```' if carrier == 'output_text' else str(report))}
    graph = build_request_phase_graph(PROMPT, request_payload=request,
        route_payload={'capability': 'vision_analysis'}, response_payload=response)
    assert not [b for b in graph['downstream_branches'] if b.get('role') == 'text_artifact_output']
    assert not [o for o in graph['intent_obligations'] if o.get('kind') == 'text_artifact']
    assert report.read_text() == '[Page 1]\nText\n[Page 2]\nScanned text'


def test_selected_predecessor_edit_still_has_exact_revision_authority(tmp_path):
    report = tmp_path/'report.md'; report.write_text('Original report')
    prompt = 'Update the selected report.md. Include a summary of the scanned pages.'
    graph = build_request_phase_graph(prompt, request_payload={
        'prompt': prompt, 'selected_reference_artifacts': [{'type': 'text', 'path': str(report)}]},
        route_payload={'capability': 'chat'})
    branches = [b for b in graph['downstream_branches'] if b.get('role') == 'text_artifact_output']
    assert len(branches) == 1
    assert branches[0]['text_artifact_target_path'] == str(report)
    assert branches[0]['text_artifact_revision_required'] is True


def test_explicit_new_report_survives_rebuild_without_becoming_a_revision(tmp_path):
    prompt = 'Summarize the attached PDF and save summary.md. Include all pages.'
    request = {'prompt': prompt, 'input_artifacts': [
        {'type': 'document', 'path': str(tmp_path/'input.pdf')}]}
    route = {'capability': 'vision_analysis'}
    admitted = build_request_phase_graph(prompt, request_payload=request, route_payload=route)
    before = [b for b in admitted['downstream_branches'] if b.get('role') == 'text_artifact_output']
    assert len(before) == 1
    result = {'saved_text_path': str(tmp_path/'summary.md'), 'content': 'All pages summarized.',
              'runtime': {'request_phase_graph': deepcopy(admitted)}}
    rebuilt = build_request_phase_graph(prompt, request_payload=request, route_payload=route,
                                       response_payload=result)
    after = [b for b in rebuilt['downstream_branches'] if b.get('role') == 'text_artifact_output']
    assert len(after) == 1
    assert after[0]['branch_id'] == before[0]['branch_id']
    assert after[0]['artifact_request'] == before[0]['artifact_request']
    assert not after[0].get('text_artifact_revision_required')


def revision_repair():
    branch = {'branch_id': 'branch-text_artifact-1', 'phase_id': 'phase-2',
              'obligation_id': 'obligation-phase-2', 'task_id': 'task-phase-2',
              'capability': 'chat', 'output_type': 'text', 'status': 'pending',
              'role': 'text_artifact_output', 'requires_artifact': True,
              'text_artifact_extension': 'md', 'text_artifact_source_name': 'report',
              'artifact_request': {'extension': 'md', 'source_name': 'report'},
              'content_payload': 'An authorized report body.',
              'content_payload_source': 'accepted_branch', 'repair_action': 'retry_same_branch'}
    check = {**branch, 'evidence': 'text_artifact_revision_write_proof_missing_or_invalid',
             'reason': 'required revision evidence missing', 'materialization_blocked': True}
    graph = {'current_phase_id': 'phase-1', 'current_phase_capability': 'vision_analysis',
             'phases': [deepcopy(branch)], 'downstream_branches': [deepcopy(branch)]}
    feedback = build_inference_repair_feedback(review_status='pending', reason='open work',
                                             checks=[check], request_phase_graph=graph)
    projection = TerminalRepairProjection(lambda value: value, 'chat', 'image_generation', 'speech_to_text')
    gap = projection._inference_repair_feedback_gap({'inference_repair_feedback': feedback})
    assert gap and len(gap['pending_branches']) == 1
    return branch, graph, gap


def test_same_branch_repair_retains_phase_through_acceptance():
    original, graph, gap = revision_repair()
    branch = gap['pending_branches'][0]
    current = {'runtime': {'request_phase_graph': graph},
               'late_fill': {'active_branches': [deepcopy(branch)]}}
    # Unchanged strict production gate: a repair may not invent another phase.
    require_response_mutation_target(branch, current)
    assert branch['branch_id'] == original['branch_id']
    assert branch['phase_id'] == original['phase_id']
    assert branch['repair_contract']['execution_binding']['phase_id'] == original['phase_id']
    assert gap['repair_loop']['promoted_contracts'][0]['execution_binding']['phase_id'] == original['phase_id']


@pytest.mark.parametrize('key', ['phase_id', 'capability', 'obligation_id', 'repair_contract_id'])
def test_changed_repair_result_still_rejected(key):
    _, graph, gap = revision_repair()
    branch = gap['pending_branches'][0]
    # Use the accepted graph phase even on the broken baseline, so this is an
    # independent negative control rather than another copy of the positive.
    branch['phase_id'] = 'phase-2'
    current = {'runtime': {'request_phase_graph': graph},
               'late_fill': {'active_branches': [deepcopy(branch)]}}
    result = deepcopy(branch); result[key] = 'foreign'
    with pytest.raises(ResponseMutationConflict, match='target binding changed'):
        require_response_mutation_target(result, current)


def test_pdf_summary_post_freezes_without_invented_file_repair(tmp_path, monkeypatch):
    """Full Responses intake/finalization/recovery; finite PDF provider boundary."""
    import fruth_webserver as web
    from tests.test_instruction_admission_contract import real_owners

    original_invoke = web._invoke_internal_api_json_route
    original_schedule = web._schedule_response_late_fill
    # Restore these overrides before real_owners tears down its own patches.
    with real_owners(tmp_path, 'Read the supplied PDF pages.') as harness, monkeypatch.context() as overrides:
        pdf = harness.documents_dir/'input.pdf'; pdf.write_bytes(b'synthetic transport input')
        saved = harness.documents_dir/'ocr-report.md'
        body = '[Page 1]\nFirst page.\n[Page 2]\nScanned page.\n[Page 3]\nThird page.'
        calls, scheduled = [], []

        def provider(**kwargs):
            calls.append(deepcopy(kwargs['payload']))
            saved.write_text(body)
            return {'content': body, 'saved_text_path': str(saved),
                    'mode': 'vision_analysis_pdf_scan', 'pdf_source': 'rendered_pages',
                    'pdf_total_pages': 3, 'pdf_processed_pages': 3,
                    'input_artifacts': [{'type': 'document', 'path': str(pdf)}]}, 200

        overrides.setattr(web, '_invoke_internal_api_json_route', provider)
        overrides.setattr(web, '_schedule_response_late_fill', lambda **kw: scheduled.append(deepcopy(kw)))
        response, status = harness.post_response({'prompt': PROMPT, 'inference_route': True,
            'capability': 'vision_analysis', 'file_path': str(pdf)})
        assert status == 200
        assert len(calls) == 1 and not scheduled
        truth, status = harness.get_response(response['id'], view='truth')
        assert status == 200 and truth['lifecycle_state'] == 'completed'
        assert truth['runtime']['graph_closure_review']['status'] == 'fulfilled'
        assert saved.read_text() == body
        assert not [b for b in truth['runtime']['request_phase_graph'].get('downstream_branches', [])
                    if b.get('role') == 'text_artifact_output']
        harness.clear_response_lookup()
        recovered = harness.response_state(response['id'])
        assert recovered['ok'] and recovered['response_payload']['lifecycle_state'] == 'completed'
        assert len(calls) == 1 and not scheduled, 'passive readback executed work'
    assert web._invoke_internal_api_json_route is original_invoke
    assert web._schedule_response_late_fill is original_schedule
