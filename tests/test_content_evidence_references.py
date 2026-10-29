"""Exact packet reference controls; execute with the guarded offline runner."""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from fruth_services.semantic_review_verdict import (
    CONTENT_REVIEW_REFERENCE_POLICY,
    semantic_review_evidence_reference_catalog,
    semantic_review_verdict_freeze_acceptance,
    semantic_review_verdict_from_text,
)


WITNESS = json.loads(Path(__file__).with_name('content_reference_witness.json').read_text())
ACTUAL = 'artifact:text_6d866b3a1ec701d15abae8f5'
TYPO = 'artifact:text_6d86b3a1ec701d15abae8f5'


def test_original_live_typo_acceptance_is_historical():
    """Retain the pre-policy interpretation, including the erroneous citation."""
    producer = next(r for r in WITNESS['reviews'] if r['role'] == 'producer')
    assert producer['packet']['artifact_refs'][0]['ref'] == ACTUAL
    assert producer['verdict']['evidence_refs'] == [TYPO]
    assert all(c['evidence_refs'] == [TYPO] for c in producer['verdict']['criterion_results'])
    for review in WITNESS['reviews']:
        verdict = semantic_review_verdict_from_text(review['result_text'])
        result = semantic_review_verdict_freeze_acceptance(
            verdict, required_criteria=review['packet']['branch_check']['semantic_review_criteria'])
        assert result['accepted'] is True


def inputs(role='producer'):
    review = deepcopy(next(r for r in WITNESS['reviews'] if r['role'] == role))
    packet, raw = review['packet'], review['verdict']
    ref = packet['artifact_refs'][0]['ref']
    raw['evidence_refs'] = [ref]
    for criterion in raw['criterion_results']:
        criterion['evidence_refs'] = [ref]
    packet['evidence_reference_catalog'] = semantic_review_evidence_reference_catalog(packet)
    return packet, raw


def accept(packet, raw, policy=CONTENT_REVIEW_REFERENCE_POLICY):
    return semantic_review_verdict_freeze_acceptance(
        semantic_review_verdict_from_text(raw),
        required_criteria=packet['branch_check']['semantic_review_criteria'],
        evidence_reference_policy=policy, evidence_packet=packet)


@pytest.mark.parametrize('role', ['producer', 'consumer'])
def test_every_supplied_reference_form_order_and_duplicates(role):
    packet, raw = inputs(role)
    refs = packet['evidence_reference_catalog']['allowed_refs']
    assert packet['artifact_refs'][0]['ref'] in refs
    assert packet['source_branch_id'] in refs
    assert packet['source_phase_id'] in refs
    assert packet['content_coverage']['requirements'][0]['requirement_id'] in refs
    if role == 'consumer':
        assert packet['content_coverage']['source']['artifact_ref'] in refs
        assert packet['content_coverage']['source']['path'] in refs
    for ref in refs:
        raw['evidence_refs'] = [ref, ref]
        for index, criterion in enumerate(raw['criterion_results']):
            criterion['evidence_refs'] = [{('ref', 'id', 'name')[index % 3]: ref}]
        assert accept(packet, raw)['accepted'], (role, ref)
    raw['evidence_refs'] = list(reversed(refs)) + refs
    raw['criterion_results'][0]['evidence_refs'] = refs[0]  # Existing single criterion form.
    assert accept(packet, raw)['accepted']
    artifact = packet['artifact_refs'][0]
    raw['evidence_refs'] = [{'ref': artifact['ref'], 'id': artifact['ref'], 'name': artifact['path']}]
    assert accept(packet, raw)['accepted']


BAD_REFS = [None, [], '', 42, {}, [None], [True], [''], [TYPO], ['artifact:unknown'],
            ['branch-other-response'], [{'ref': ACTUAL, 'id': 'foreign'}],
            [ACTUAL, TYPO], [ACTUAL, None], [ACTUAL, {}], [ACTUAL, 'none']]


@pytest.mark.parametrize('level', ['verdict', 'criterion'])
@pytest.mark.parametrize('refs', BAD_REFS)
def test_exact_reference_rejections_preserve_original_entries(level, refs):
    packet, raw = inputs()
    target = raw if level == 'verdict' else raw['criterion_results'][0]
    target['evidence_refs'] = deepcopy(refs)
    original = deepcopy(raw)
    result = accept(packet, raw)
    assert result['accepted'] is False
    assert 'invalid_evidence_references' in result['rejection_reasons']
    issues = result['reference_rejections']
    assert issues and all(('criterion_results' in i['location']) == (level == 'criterion') for i in issues)
    assert raw == original
    normalized = semantic_review_verdict_from_text(raw)
    assert normalized['reference_declarations']['evidence_refs'] == raw['evidence_refs']
    assert normalized['reference_declarations']['criterion_results'] == raw['criterion_results']


@pytest.mark.parametrize('level', ['verdict', 'criterion'])
def test_missing_refs_are_not_replaced_with_runtime_citations(level):
    packet, raw = inputs()
    (raw if level == 'verdict' else raw['criterion_results'][0]).pop('evidence_refs')
    result = accept(packet, raw)
    assert not result['accepted']
    assert result['reference_rejections'][0]['reason'] == 'missing_or_malformed_evidence_refs'


@pytest.mark.parametrize('level', ['verdict', 'criterion'])
def test_previous_artifact_reference_is_not_in_the_new_packet(level):
    packet, raw = inputs()
    fresh_ref = 'artifact:text_current_generation'
    packet['artifact_refs'][0]['ref'] = fresh_ref
    packet['evidence_reference_catalog'] = semantic_review_evidence_reference_catalog(packet)
    raw['evidence_refs'] = [fresh_ref]
    for criterion in raw['criterion_results']:
        criterion['evidence_refs'] = [fresh_ref]
    assert accept(packet, raw)['accepted']
    (raw if level == 'verdict' else raw['criterion_results'][0])['evidence_refs'] = [ACTUAL]
    result = accept(packet, raw)
    assert not result['accepted']
    assert result['reference_rejections'][0]['reason'] == 'unsupported_evidence_ref'


def test_duplicate_criterion_cannot_hide_invalid_refs_and_evidence_alias_survives():
    packet, raw = inputs()
    criterion = raw['criterion_results'][0]
    criterion['evidence'] = criterion.pop('evidence_refs')
    assert accept(packet, raw)['accepted']
    duplicate = deepcopy(criterion)
    raw['criterion_results'].append(duplicate)
    assert accept(packet, raw)['accepted']
    duplicate['evidence'] = [TYPO]
    assert not accept(packet, raw)['accepted']


def test_causal_inputs_distinguish_alias_resolution_and_missing_catalog():
    from fruth_services.semantic_review_verdict import _freeze_causal_inputs
    packet, raw = inputs()
    packet['artifact_refs'][0]['name'] = 'first.json'
    packet['artifact_refs'].append({**packet['artifact_refs'][0], 'name': 'second.json',
                                   'ref': 'artifact:second', 'path': '/second.json'})
    packet['evidence_reference_catalog'] = semantic_review_evidence_reference_catalog(packet)
    raw['evidence_refs'] = [{'ref': ACTUAL, 'name': 'first.json'}]
    def causal(value):
        return _freeze_causal_inputs({'verdict': semantic_review_verdict_from_text(raw),
            'required_criteria': value['branch_check']['semantic_review_criteria'],
            'evidence_reference_policy': CONTENT_REVIEW_REFERENCE_POLICY, 'evidence_packet': value})
    original_inputs = causal(packet)
    assert accept(packet, raw)['accepted']
    changed = deepcopy(packet)
    changed['artifact_refs'][0]['name'], changed['artifact_refs'][1]['name'] = 'second.json', 'first.json'
    assert semantic_review_evidence_reference_catalog(changed) == packet['evidence_reference_catalog']
    assert not accept(changed, raw)['accepted']
    assert causal(changed) != original_inputs
    changed = deepcopy(packet)
    changed.pop('evidence_reference_catalog')
    assert not accept(changed, raw)['accepted']
    assert causal(changed) != original_inputs


def test_packet_membership_not_registry_prose_or_another_branch():
    packet, raw = inputs()
    foreign = next(r for r in WITNESS['reviews'] if r['role'] == 'consumer')['packet']['artifact_refs'][0]['ref']
    packet['branch_output_text'] = foreign
    raw['evidence_refs'] = [foreign]
    assert not accept(packet, raw)['accepted']
    # Same visible name for two distinct saved artifacts is not an exact alias.
    first = packet['artifact_refs'][0]
    first['name'] = 'ambiguous.json'
    second = {**first, 'ref': 'artifact:other', 'path': '/different/saved.json'}
    packet['artifact_refs'].append(second)
    packet['evidence_reference_catalog'] = semantic_review_evidence_reference_catalog(packet)
    assert 'ambiguous.json' in packet['evidence_reference_catalog']['ambiguous_refs']
    raw['evidence_refs'] = ['ambiguous.json']
    assert accept(packet, raw)['reference_rejections'][0]['reason'] == 'ambiguous_evidence_ref'


@pytest.mark.parametrize('fault', ['missing_catalog', 'forged_catalog', 'unknown_policy', 'missing_declarations'])
def test_governed_metadata_fails_closed(fault):
    packet, raw = inputs()
    normalized = semantic_review_verdict_from_text(raw)
    if fault == 'missing_catalog':
        packet.pop('evidence_reference_catalog')
    if fault == 'forged_catalog':
        packet['evidence_reference_catalog']['allowed_refs'].append(TYPO)
    if fault == 'missing_declarations':
        normalized.pop('reference_declarations')
    result = semantic_review_verdict_freeze_acceptance(normalized,
        required_criteria=packet['branch_check']['semantic_review_criteria'], evidence_packet=packet,
        evidence_reference_policy='unknown' if fault == 'unknown_policy' else CONTENT_REVIEW_REFERENCE_POLICY)
    assert not result['accepted']


def test_model_provenance_cannot_hide_a_bad_original_reference():
    packet, raw = inputs()
    raw['reference_declarations'] = {'evidence_refs': [ACTUAL], 'criterion_results': deepcopy(raw['criterion_results'])}
    raw['evidence_refs'] = [ACTUAL, None]
    assert not accept(packet, raw)['accepted']


@pytest.mark.parametrize('criteria', [None, 42, {}, 'passed'])
def test_malformed_original_criteria_cannot_crash_or_pass(criteria):
    packet, raw = inputs()
    raw['criterion_results'] = criteria
    assert not accept(packet, raw)['accepted']


@pytest.mark.parametrize('verdict,status', [('failed', 'blocked'), ('uncertain', 'pending')])
def test_negative_uncertain_meaning_is_preserved(verdict, status):
    packet, raw = inputs()
    raw.update(verdict=verdict, recommended_transition='manual_review', defects=['controlled review'])
    for criterion in raw['criterion_results']:
        criterion.update(status=verdict, evidence_refs=[])
    normalized = semantic_review_verdict_from_text(raw)
    assert normalized['verdict'] == verdict and normalized['status'] == status
    result = accept(packet, raw)
    assert not result['accepted']
    assert not result.get('reference_rejections')  # No passed required criterion lost its meaning.


def native_reference_case(mode):
    def change(packet, raw, report):
        role = packet['content_coverage']['requirements'][0]['role']
        if mode == 'all_valid':
            refs = packet['evidence_reference_catalog']['allowed_refs']
            raw['evidence_refs'] = list(reversed(refs)) + refs
            for criterion in raw['criterion_results']:
                criterion['evidence_refs'] = list(refs)
        elif mode == 'uncertain':
            raw.update(verdict='uncertain', overall_status='pending', recommended_transition='manual_review')
            for criterion in raw['criterion_results']:
                criterion['status'] = 'uncertain'
        elif role == 'producer':
            target = raw['criterion_results'][0] if mode.endswith('criterion') else raw
            ref = packet['artifact_refs'][0]['ref']
            if mode.startswith('typo'):
                target['evidence_refs'] = [TYPO]
            elif mode.startswith('mixed'):
                target['evidence_refs'] = [ref, TYPO]
            elif mode.startswith('malformed'):
                target['evidence_refs'] = [ref, None]
            elif mode.startswith('missing'):
                target.pop('evidence_refs')
            elif mode == 'wrong_branch':
                target['evidence_refs'] = [next(r['branch_id'] for r in report['accepted_requirements'] if r['role'] == 'consumer')]
    change.expected_unresolved = 0 if mode == 'all_valid' else 2 if mode == 'uncertain' else 1
    return change


@pytest.mark.parametrize('mode', ['all_valid', 'typo_verdict', 'typo_criterion', 'mixed_verdict',
    'mixed_criterion', 'malformed_verdict', 'missing_criterion', 'wrong_branch', 'uncertain'])
def test_native_reference_transport_closure_and_readback(monkeypatch, mode):
    from tests.test_content_requirement_completion import run_native, summary

    def probe(harness, runtime, request, final, docs, report):
        checks = [c for c in final['runtime']['graph_closure_review']['checks'] if c.get('content_requirements')]
        assert len(checks) == 2
        for check in checks:
            verdict = check['semantic_review_verdict']
            acceptance = check['semantic_review_freeze_acceptance']
            assert acceptance['evidence_reference_policy'] == CONTENT_REVIEW_REFERENCE_POLICY
            role = check['content_requirements'][0]['role']
            if role == 'producer' and mode not in {'all_valid', 'uncertain'}:
                assert 'invalid_evidence_references' in acceptance['rejection_reasons']
                assert acceptance['reference_rejections']
                assert check['repair_action'] == 'manual_review'
                assert check['content_coverage_status'] == 'unverified'
            if mode == 'uncertain':
                assert verdict['verdict'] == 'uncertain' and verdict['status'] == 'pending'
        returned = report['returned_verdicts']
        for result in final['late_fill']['fill_results']:
            if result.get('semantic_review_evidence_binding'):
                assert json.loads(result['result_text']) in returned
        harness.clear_response_lookup()
        state = harness.response_state(final['id'])
        assert summary(state['response_payload']) == summary(final)
        assert state['response_payload']['late_fill']['fill_results'] == final['late_fill']['fill_results']

    run_native(monkeypatch, label='refs-' + mode, reference_case=native_reference_case(mode), probe=probe)


def test_pre_reference_policy_native_wrong_refs_remain_historical(monkeypatch):
    from tests.test_content_requirement_completion import run_native
    from fruth_services.responses import request_intent_payload, restore_request_intent

    def probe(harness, runtime, request, final, docs, report):
        harness.clear_response_lookup()
        durable = harness.response_state(final['id'])
        assert durable['ok']
        frame_request = durable['response_frame']['request']
        restored = request_intent_payload(restore_request_intent(frame_request))
        assert frame_request['content_requirement_policy'] == 'named_saved_text_v1'
        assert 'content_review_reference_policy' not in frame_request
        assert 'content_review_reference_policy' not in restored
        report['historical_request_policy_absent_after_canonical_roundtrip'] = True

    run_native(monkeypatch, label='refs-historical', review='wrong_refs',
               legacy_references=True, probe=probe)


def test_valid_reference_false_positive_remains_a2_soundness_limit(monkeypatch):
    from tests.test_content_requirement_completion import run_native
    run_native(monkeypatch, label='refs-false-positive', fault='wrong_sum', reference_case=native_reference_case('all_valid'))


def test_native_policy_metadata_loss_and_raw_verdict_authority(monkeypatch):
    from tests.test_content_requirement_completion import run_native, summary, assert_compact_readback
    from tests.test_consumer_evidence_a2 import reserve, dump
    from tests.consumer_evidence_model import case

    def probe(harness, runtime, request, final, docs, report):
        import fruth_webserver as web
        from fruth_services.responses import request_intent_frame_source, restore_request_intent

        def walk(value, change):
            if isinstance(value, dict):
                change(value)
                for child in list(value.values()):
                    walk(child, change)
            elif isinstance(value, list):
                for child in value:
                    walk(child, change)

        original_files = {p: p.read_bytes() for p in docs.iterdir() if p.is_file()}
        ledger = harness.response_frames_dir / 'responses.jsonl'
        prefix = ledger.read_bytes()
        parent = final['response_frame']
        for mode in ('graph_policy_missing', 'capture_dictionary_policy_missing', 'result_policy_missing',
                     'wrong_policy', 'normalized_verdict_laundering', 'restored_request'):
            root, _ = reserve('refs-metadata-' + mode, case(), 'replay')
            candidate = deepcopy(final)
            candidate['response_frame'] = parent
            local_request = deepcopy(request)
            if mode == 'restored_request':
                local_request = restore_request_intent(request_intent_frame_source(request))
            if mode == 'graph_policy_missing':
                walk(candidate['runtime']['request_phase_graph'], lambda value: value.pop('content_review_reference_policy', None))
            elif mode == 'capture_dictionary_policy_missing':
                local_request['_request_intent'].request.pop('content_review_reference_policy')
            elif mode == 'wrong_policy':
                candidate['runtime']['request_phase_graph']['content_review_reference_policy'] = 'legacy'
            for result in candidate['late_fill']['fill_results']:
                if not result.get('semantic_review_evidence_binding'):
                    continue
                raw = json.loads(result['result_text'])
                if mode == 'normalized_verdict_laundering':
                    result['semantic_review_verdict'] = semantic_review_verdict_from_text(raw)
                raw['evidence_refs'] = [raw['evidence_refs'][0], TYPO]
                result['result_text'] = json.dumps(raw)
            if mode == 'result_policy_missing':
                walk(candidate['late_fill'], lambda value: value.pop('evidence_reference_policy', None))
            settled, status = runtime.finalize_terminal_materialization_contract(
                candidate, request_payload=local_request, route_payload=None, artifact_gap=None,
                terminal_status='completed', accepted_fill_results=deepcopy(candidate['late_fill']['fill_results']))
            assert status != 'completed', mode
            assert summary(settled)['unresolved_content_requirement_count'] == 2, mode
            frozen = harness.freeze_manual_response(settled, request_payload=local_request)
            parent = frozen['response_frame']
            assert ledger.read_bytes().startswith(prefix)
            assert original_files == {p: p.read_bytes() for p in original_files}
            assert_compact_readback(harness, final['id'], summary(settled))
            dump(root / 'observation.json', {'mode': mode, 'summary': summary(settled), 'status': status})
    run_native(monkeypatch, label='refs-metadata', reference_case=native_reference_case('all_valid'), probe=probe)


def test_frozen_request_reference_policy_roundtrip(monkeypatch):
    from tests.test_content_requirement_completion import run_native, summary
    from fruth_services.responses import request_intent_payload, restore_request_intent

    def probe(harness, runtime, request, final, docs, report):
        captured = request_intent_payload(request)
        assert captured['content_review_reference_policy'] == 'packet_exact_v1'
        harness.clear_response_lookup()
        durable = harness.response_state(final['id'])
        assert durable['ok']
        frame_request = durable['response_frame'].get('request') or {}
        restored = request_intent_payload(restore_request_intent(frame_request))
        graph = durable['response_payload']['runtime']['request_phase_graph']
        report['policy_roundtrip'] = {
            'expected_reference_policy': 'packet_exact_v1',
            'captured': captured.get('content_review_reference_policy'),
            'canonical_request': frame_request.get('content_review_reference_policy'),
            'restored_request': restored.get('content_review_reference_policy'),
            'graph': graph.get('content_review_reference_policy'),
            'content_policy_in_request': frame_request.get('content_requirement_policy'),
            'intent_source': frame_request.get('intent_source'),
            'frame_id': durable['response_frame']['frame_id'],
            'readback_summary': summary(durable['response_payload']),
            'graph_and_result_metadata_untouched': True,
        }
        # Retained W2 expectation, now traversing the permanent suite's native fixture.
        assert restored.get('content_review_reference_policy') == 'packet_exact_v1', report['policy_roundtrip']
    run_native(monkeypatch, label='actual-frame-policy-roundtrip', probe=probe)


@pytest.mark.parametrize('mode', ['all_valid', 'typo_verdict', 'mixed_verdict', 'stale_packet'])
def test_restored_control_request_governs_surviving_review(monkeypatch, mode):
    from tests.test_content_requirement_completion import run_native, control_request_checkpoint, summary

    change = native_reference_case(mode)
    def verdict(packet, raw, report):
        change(packet, raw, report)
        if mode == 'stale_packet':
            assert ACTUAL not in packet['evidence_reference_catalog']['allowed_refs']
            raw['evidence_refs'] = [ACTUAL]  # Real alias in the retained older packet.

    def checkpoint(*args):
        final = control_request_checkpoint(*args, carrier='recovered', action='cancel')
        checks = [c for c in final['runtime']['graph_closure_review']['checks']
                  if c.get('content_requirements') and c['content_requirements'][0]['role'] == 'producer']
        assert len(checks) == 1
        accepted = checks[0]['semantic_review_freeze_acceptance']
        assert accepted['evidence_reference_policy'] == CONTENT_REVIEW_REFERENCE_POLICY
        assert accepted['accepted'] == (mode == 'all_valid')
        if mode != 'all_valid':
            assert 'invalid_evidence_references' in accepted['rejection_reasons']
            assert accepted['reference_rejections']
        assert summary(final)['unresolved_content_requirement_count'] == (1 if mode == 'all_valid' else 2)

    run_native(monkeypatch, label='refs-control-restored-' + mode,
        reference_case=verdict, control_probe=checkpoint,
        prepared_prompt='Separate prepared execution; caller scope stays canonical.')


def test_restored_request_policy_governs_without_downstream_labels(monkeypatch):
    from tests.test_content_requirement_completion import run_native, summary, assert_compact_readback
    from tests.test_consumer_evidence_a2 import reserve, dump
    from tests.consumer_evidence_model import case
    from fruth_services.responses import request_intent_payload, restore_request_intent
    import hashlib

    def probe(harness, runtime, request, final, docs, report):
        harness.clear_response_lookup()
        durable = harness.response_state(final['id'])
        assert durable['ok']
        restored = restore_request_intent(durable['response_frame']['request'])
        assert request_intent_payload(restored)['content_review_reference_policy'] == CONTENT_REVIEW_REFERENCE_POLICY
        original = durable['response_payload']
        parent = durable['response_frame']
        ledger = harness.response_frames_dir / 'responses.jsonl'
        prefix = ledger.read_bytes()
        snapshots = {p: hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in (harness.response_frames_dir / 'snapshots').rglob('*') if p.is_file()}
        artifacts = {p: p.read_bytes() for p in docs.iterdir() if p.is_file()}
        assert all(ACTUAL not in packet['evidence_reference_catalog']['allowed_refs']
                   for packet in report['packets'])
        report['restored_policy_controls'] = []
        report['interventions'].append(
            'Isolated post-native metadata/verdict mutations; no public operation or new review execution is claimed.')

        def walk(value, key):
            if isinstance(value, dict):
                value.pop(key, None)
                for child in value.values():
                    walk(child, key)
            elif isinstance(value, list):
                for child in value:
                    walk(child, key)

        for mode in ('valid', 'invalid_verdict', 'mixed_verdict', 'mixed_criterion',
                     'malformed_verdict', 'stale_packet', 'missing_binding_policy',
                     'normalized_verdict_laundering'):
            control_root, _ = reserve('refs-restored-' + mode, case(), 'replay')
            candidate = deepcopy(original)
            candidate['response_frame'] = parent
            # Optional graph/result projections cannot substitute for caller policy.
            walk(candidate['runtime'], 'content_review_reference_policy')
            walk(candidate['late_fill'], 'content_review_reference_policy')
            raw_results = []
            for result in candidate['late_fill']['fill_results']:
                if not result.get('semantic_review_evidence_binding'):
                    continue
                raw = json.loads(result['result_text'])
                if mode == 'normalized_verdict_laundering':
                    result['semantic_review_verdict'] = semantic_review_verdict_from_text(raw)
                if mode in {'invalid_verdict', 'normalized_verdict_laundering'}:
                    raw['evidence_refs'] = [TYPO]
                elif mode == 'mixed_verdict':
                    raw['evidence_refs'].append(TYPO)
                elif mode == 'mixed_criterion':
                    raw['criterion_results'][0]['evidence_refs'].append(TYPO)
                elif mode == 'malformed_verdict':
                    raw['evidence_refs'] = [None]
                elif mode == 'stale_packet':
                    # ACTUAL is valid in the retained older packet, not this one.
                    raw['evidence_refs'] = [ACTUAL]
                result['result_text'] = json.dumps(raw)
                raw_results.append(raw)
            if mode == 'missing_binding_policy':
                # Result-binding policy is required evidence, not an optional label.
                walk(candidate['late_fill'], 'evidence_reference_policy')
            settled, status = runtime.finalize_terminal_materialization_contract(
                candidate, request_payload=restored, route_payload=None, artifact_gap=None,
                terminal_status='completed', accepted_fill_results=deepcopy(candidate['late_fill']['fill_results']))
            expected_unresolved = 0 if mode == 'valid' else 2
            assert (status == 'completed') == (mode == 'valid'), mode
            assert summary(settled)['unresolved_content_requirement_count'] == expected_unresolved, mode
            checks = [c for c in settled['runtime']['graph_closure_review']['checks']
                      if c.get('content_requirements')]
            assert len(checks) == 2
            if mode != 'missing_binding_policy':
                for check in checks:
                    acceptance = check['semantic_review_freeze_acceptance']
                    assert acceptance['evidence_reference_policy'] == CONTENT_REVIEW_REFERENCE_POLICY
                    assert acceptance['accepted'] == (mode == 'valid'), (mode, acceptance)
                    if mode != 'valid':
                        assert 'invalid_evidence_references' in acceptance['rejection_reasons']
                        assert acceptance['reference_rejections']
            frozen = harness.freeze_manual_response(settled, request_payload=restored)
            parent = frozen['response_frame']
            assert ledger.read_bytes().startswith(prefix)
            assert all(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in snapshots.items())
            assert artifacts == {p: p.read_bytes() for p in artifacts}
            harness.clear_response_lookup()
            recovered = harness.response_state(final['id'])
            assert recovered['ok']
            restored = restore_request_intent(recovered['response_frame']['request'])
            assert request_intent_payload(restored)['content_review_reference_policy'] == CONTENT_REVIEW_REFERENCE_POLICY
            assert summary(recovered['response_payload']) == summary(settled)
            expected_results = deepcopy(settled['late_fill']['fill_results'])
            for result in expected_results:
                if mode == 'normalized_verdict_laundering' and result.get('semantic_review_evidence_binding'):
                    # Canonical mappings omit empty arrays; the raw verdict text
                    # (including every invalid reference) must remain exact.
                    assert result['semantic_review_verdict'].pop('defects') == []
            assert recovered['response_payload']['late_fill']['fill_results'] == expected_results
            assert_compact_readback(harness, final['id'], summary(settled))
            observation = {'mode': mode, 'summary': summary(settled), 'terminal_status': status,
                           'raw_review_verdicts': raw_results, 'restored_reference_policy':
                           request_intent_payload(restored)['content_review_reference_policy']}
            report['restored_policy_controls'].append(observation)
            dump(control_root / 'observation.json', observation)
            prefix = ledger.read_bytes()
            snapshots.update({p: hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in (harness.response_frames_dir / 'snapshots').rglob('*') if p.is_file()})

    run_native(monkeypatch, label='refs-actual-restored-policy', probe=probe)
