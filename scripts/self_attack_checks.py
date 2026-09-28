"""Deterministic negative-evidence oracle over canonical Fruth response truth.

This does not decide runtime fulfillment. It detects contradictory runtime
records and reports absent evidence, rather than accepting assistant claims.
"""
from __future__ import annotations

import hashlib

from scripts.run_graph_rebase_shadow_corpus import stable_digest
from fruth_services.graph_rebase import _semantic_record_payload

OPEN = {'pending', 'blocked', 'failed', 'repair_needed', 'repair_required', 'unmet',
        'semantic_review_pending', 'running', 'queued', 'in_progress'}
SUCCESS = {'completed', 'fulfilled', 'passed', 'frozen', 'late_fill_completed'}
STOPPED = {'cancelled', 'canceled', 'waived', 'superseded'}


def records(value):
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def walk(value, path=''):
    if isinstance(value, dict):
        yield path, value
        for key, item in value.items():
            yield from walk(item, f'{path}/{key}')
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from walk(item, f'{path}/{i}')


def finding(code, path, detail):
    return dict(code=code, path=path, detail=detail,
                signature=stable_digest({'code': code, 'path': path})[:20])


def rejected_audio_mismatch_evidence(payload: dict) -> list[dict]:
    """Recognize a saved rejection for reporting, without satisfying coverage.

    This observes the runtime gate, not the audio itself. A generic failed TTS,
    an error string, or a mismatch on a sibling cannot prove correct rejection.
    """
    def mapping(value):
        return value if isinstance(value, dict) else {}

    def identifiers(value):
        return value if isinstance(value, list) and all(isinstance(v, str) for v in value) else []

    payload = mapping(payload)
    runtime = mapping(payload.get('runtime'))
    graph = mapping(runtime.get('request_phase_graph'))
    closure = mapping(runtime.get('graph_closure_review'))
    frame = mapping(payload.get('response_frame'))
    late = mapping(payload.get('late_fill'))
    if (payload.get('lifecycle_state') not in ('repair_needed', 'failed')
            or closure.get('status') != 'blocked' or late.get('status') != 'failed'
            or records(late.get('active_branches')) or records(late.get('pending_branches'))
            or frame.get('status') not in ('completed', 'frozen')
            or not all(isinstance(v, str) and v for v in (payload.get('id'), frame.get('frame_id')))):
        return []
    phases = records(graph.get('phases'))
    failed = records(late.get('failed_branches'))
    checks = records(closure.get('checks'))
    possible_acceptances = (phases + records(graph.get('downstream_branches'))
                            + records(payload.get('outputs')) + checks
                            + records(late.get('fill_results')) + records(late.get('completed_branches')))
    observations = []
    for index, consumer in enumerate(failed):
        error = mapping(consumer.get('error'))
        evidence = mapping(error.get('semantic_evidence'))
        if (consumer.get('capability') != 'speech_to_text' or consumer.get('status') != 'failed'
                or error.get('stage') != 'semantic_evidence_gate'
                or error.get('materialization_blocked') is not True
                or error.get('reason_code') != 'TTS_STT_SEMANTIC_MISMATCH'
                or evidence.get('kind') != 'fruth.tts_stt_semantic_evidence'
                or evidence.get('authority') != 'runtime_deterministic_verification'
                or evidence.get('status') != 'mismatched'
                or evidence.get('semantic_match') is not False
                or evidence.get('reason_code') != 'TTS_STT_SEMANTIC_MISMATCH'):
            continue
        source_digest, transcript_digest = evidence.get('source_sha256'), evidence.get('transcript_sha256')
        transcript = evidence.get('transcript_text')
        if (not all(isinstance(d, str) and len(d) == 64 and all(c in '0123456789abcdef' for c in d)
                    for d in (source_digest, transcript_digest))
                or not isinstance(transcript, str) or not transcript
                or hashlib.sha256(transcript.encode('utf-8')).hexdigest() != transcript_digest
                or source_digest == transcript_digest):
            continue
        producer_id, consumer_id = evidence.get('producer_phase_id'), evidence.get('consumer_phase_id')
        if (not all(isinstance(value, str) and value for value in (producer_id, consumer_id))
                or producer_id == consumer_id):
            continue
        producer_phases = [p for p in phases if p.get('phase_id') == producer_id and p.get('capability') == 'text_to_speech']
        consumer_phases = [p for p in phases if p.get('phase_id') == consumer_id and p.get('capability') == 'speech_to_text']
        producers = [p for p in failed if p.get('phase_id') == producer_id and p.get('capability') == 'text_to_speech']
        if (len(producer_phases) != 1 or len(consumer_phases) != 1 or len(producers) != 1
                or len([b for b in failed if b.get('phase_id') == consumer_id]) != 1):
            continue
        producer = producers[0]
        if (consumer.get('phase_id') != consumer_id
                or not all(isinstance(b.get('branch_id'), str) and b['branch_id'] for b in (consumer, producer))
                or consumer.get('branch_id') != evidence.get('consumer_branch_id')
                or producer.get('branch_id') != evidence.get('producer_branch_id')
                or producer.get('branch_id') == consumer.get('branch_id')
                or consumer_phases[0].get('branch_id') != consumer.get('branch_id')
                or producer_phases[0].get('branch_id') != producer.get('branch_id')
                or producer_id not in identifiers(consumer.get('depends_on'))
                or producer_id not in identifiers(consumer_phases[0].get('depends_on'))
                or producer_id not in identifiers(error.get('failed_dependency_ids'))
                or producer.get('status') != 'failed'
                or mapping(producer.get('error')).get('code') != 'TTS_STT_SEMANTIC_MISMATCH'):
            continue
        if not all(any(c.get('phase_id') == phase_id and c.get('status') == 'blocked' for c in checks)
                   for phase_id in (producer_id, consumer_id)):
            continue
        ids = {producer_id, consumer_id, producer['branch_id'], consumer['branch_id']}
        if any(isinstance(r.get('status'), str) and r['status'] in SUCCESS
               and any(r.get(k) == identity for k in ('phase_id', 'branch_id') for identity in ids)
               for r in possible_acceptances):
            continue
        observations.append(dict(
            response_id=payload['id'], frame_id=frame['frame_id'],
            producer_phase_id=producer_id, consumer_phase_id=consumer_id,
            source_sha256=source_digest, transcript_sha256=transcript_digest,
            evidence_path=f'/late_fill/failed_branches/{index}/error/semantic_evidence',
        ))
    return observations


def audit_truth(payload: dict, *, artifact_evidence=None) -> dict:
    failures, missing, exercised = [], [], []
    runtime = payload.get('runtime') or {}
    graph = runtime.get('request_phase_graph') or {}
    closure = runtime.get('graph_closure_review') or {}
    frame = payload.get('response_frame') or {}
    for key, value in [('runtime.request_phase_graph', graph),
                       ('runtime.graph_closure_review', closure), ('response_frame', frame)]:
        if not value:
            missing.append(key)
    if 'outputs' not in payload:
        missing.append('outputs')
    for key in ('intent_obligations', 'output_obligations', 'phases'):
        if key not in graph:
            if key == 'intent_obligations' and (graph.get('prompt_intent') or {}).get('intent_obligation_count') == 0:
                continue
            missing.append(f'runtime.request_phase_graph.{key}')
    def fail(code, path, detail):
        failures.append(finding(code, path, detail))
    branches = records(graph.get('downstream_branches'))
    phases = records(graph.get('phases'))
    obligations = records(graph.get('output_obligations'))
    ids = [p.get('phase_id') for p in phases if p.get('phase_id')]
    if len(ids) != len(set(ids)):
        fail('duplicate_phase_identity', '/runtime/request_phase_graph/phases', 'Phase identities are not unique.')
    by_id = {p.get('phase_id'): p for p in phases}
    edges = {p.get('phase_id'): list(p.get('depends_on') or []) for p in phases + branches}
    for target, dependencies in edges.items():
        if any(d not in by_id for d in dependencies):
            fail('dangling_dependency', '/runtime/request_phase_graph/phases', f'{target} has an absent producer.')
    def cyclic(node, active, done):
        if node in active:
            return True
        if node in done:
            return False
        active.add(node)
        if any(cyclic(d, active, done) for d in edges.get(node, []) if d in edges):
            return True
        active.remove(node)
        done.add(node)
        return False
    if any(cyclic(node, set(), set()) for node in edges):
        fail('dependency_cycle', '/runtime/request_phase_graph', 'Executable dependencies contain a cycle.')
    exercised.append('graph_identity_and_dependencies')
    promoted = {o.get('phase_id') for o in obligations
                if o.get('status') not in {'reserved', 'candidate', 'omitted', 'rejected'}
                and o.get('contract_state') not in {'reserved', 'candidate'}}
    for branch in branches:
        state = branch.get('contract_state') or branch.get('status')
        if state in {'reserved', 'candidate', 'omitted', 'rejected'}:
            if branch.get('status') in {'running', 'fulfilled', 'completed'}:
                fail('unpromoted_execution', '/runtime/request_phase_graph/downstream_branches', 'Reserved work executed.')
        elif branch.get('phase_id') not in promoted and obligations:
            fail('branch_without_obligation', '/runtime/request_phase_graph/downstream_branches',
                 f"Branch {branch.get('phase_id')} has no output obligation.")
    exercised.append('promotion_boundary')
    late = payload.get('late_fill') or {}
    stopped = {b.get('branch_id') or b.get('phase_id')
               for b in records(late.get('cancelled_branches'))}
    controls = late.get('branch_controls') or {}
    if isinstance(controls, dict):
        stopped |= {key for key, value in controls.items() if isinstance(value, dict)
                    and (value.get('status') or value.get('action')) in STOPPED}
    for result in records(late.get('fill_results')):
        identity = result.get('branch_id') or result.get('phase_id')
        branch = next((b for b in branches + phases if identity in {b.get('branch_id'), b.get('phase_id')}
                       or result.get('phase_id') == b.get('phase_id')), {})
        identities = {identity, result.get('phase_id')} - {None, ''}
        # Graph phases can remain planned in a frozen response. Canonical
        # outputs and closure checks own fulfillment; fill results need not
        # repeat a status field at all.
        accepted = (result.get('status') in SUCCESS or any(
            item.get('status') in SUCCESS
            and bool(identities & {item.get('branch_id'), item.get('phase_id')})
            for item in phases + branches + records(payload.get('outputs')) + records(closure.get('checks'))))
        if identity in stopped and accepted and not result.get('stale'):
            fail('stale_result_accepted', '/late_fill/fill_results', 'Stopped branch result was accepted as successful.')
        evidence = result.get('tts_stt_semantic_evidence') or {}
        if evidence:
            exercised.append('exact_source_binding')
            if accepted and evidence.get('status') in {'mismatched', 'unavailable', 'failed'}:
                fail('invalid_source_evidence_accepted', '/late_fill/fill_results', 'Unbound or mismatched audio evidence was accepted.')
            if evidence.get('status') == 'matched':
                deps = branch.get('depends_on') or (branch.get('execution_contract') or {}).get('dependencies') or []
                if evidence.get('producer_phase_id') not in deps:
                    fail('sibling_evidence_substituted', '/late_fill/fill_results', 'Evidence was bound to an undeclared producer.')
                producer = next((p for p in records(late.get('fill_results'))
                                 if p.get('phase_id') == evidence.get('producer_phase_id')
                                 and p.get('capability') == 'text_to_speech'), {})
                source = producer.get('tts_semantic_source') or {}
                text = source.get('tts_source_text')
                digest = hashlib.sha256(text.encode('utf-8')).hexdigest() if isinstance(text, str) else None
                if not digest or digest != source.get('tts_source_text_sha256') or digest != evidence.get('source_sha256'):
                    fail('source_digest_mismatch', '/late_fill/fill_results', 'Accepted semantic evidence does not bind the exact saved producer source.')
        elif result.get('capability') == 'speech_to_text' and any(
                p.get('capability') == 'text_to_speech' and p.get('phase_id') in branch.get('depends_on', [])
                for p in phases):
            missing.append(f'late_fill.fill_results.{identity}.tts_stt_semantic_evidence')
    if stopped:
        exercised.append('stale_result_gate')
    completed = payload.get('lifecycle_state') in SUCCESS
    open_checks = [check for check in records(closure.get('checks'))
                   if check.get('status') in OPEN and check.get('required', True)]
    if completed and (closure.get('status') in OPEN or open_checks):
        fail('false_closure', '/runtime/graph_closure_review', 'Successful lifecycle retains required open closure checks.')
    if completed and (late.get('status') in {'pending', 'running', 'queued'}
                      or records(late.get('active_branches'))):
        fail('active_work_frozen_successfully', '/late_fill', 'Successful closure still has active Late Fill work.')
    if closure:
        exercised.append('closure_before_success')
    for path, record in walk(closure):
        if record.get('check_kind') in {'branch_semantic_review', 'global_semantic_closure'}:
            exercised.append('semantic_review_gate')
            verdict = record.get('semantic_review_verdict') or {}
            if record.get('status') in SUCCESS and isinstance(verdict, dict) and verdict.get('status') in {'failed', 'uncertain', 'unparseable'}:
                fail('failed_review_claimed_passed', path, 'Failed semantic verdict was projected as fulfilled.')
    for path, record in walk(runtime):
        if record.get('kind') in {'fruth.commitment_review', 'fruth.aspiration_review', 'fruth.controlled_attention_review'}:
            exercised.append('advisory_authority')
            if record.get('authority') and record['authority'] != 'advisory_read_model_only':
                fail('advisory_runtime_authority', path, 'Advisory movement claims promotion/closure authority.')
        if record.get('kind') == 'fruth.semantic_role_profile':
            exercised.append('advisory_authority')
            effect = (record.get('runtime_orientation') or {}).get('runtime_effect') or (record.get('authority_boundary') or {}).get('runtime_effect')
            if effect and effect != 'none':
                fail('advisory_runtime_authority', path, 'Semantic role claims runtime effect.')
        if ('autonomy_level' in record and isinstance(record.get('outcome'), str)
                and record['outcome'] in {'applied', 'applied_safe'}):
            exercised.append('repair_authority')
            if record['autonomy_level'] in {'off', 'shadow', 'stage'}:
                fail('nonexecuting_profile_mutated_graph', path, 'Off/shadow/stage cannot apply a graph mutation.')
            if not record.get('evidence_refs'):
                fail('mutation_without_evidence', path, 'Applied graph mutation has no evidence refs.')
    artifacts = {a.get('artifact_ref'): a for a in records(payload.get('artifacts')) if a.get('artifact_ref')}
    for index, output in enumerate(records(payload.get('outputs'))):
        ref = output.get('artifact_ref')
        if output.get('status') != 'fulfilled' or not ref:
            continue
        exercised.append('artifact_fulfillment')
        artifact = artifacts.get(ref)
        if not artifact:
            fail('unbacked_artifact_output', f'/outputs/{index}', 'Fulfilled output has no canonical artifact record.')
        elif artifact_evidence is not None:
            evidence = artifact_evidence.get(ref)
            if not evidence or not evidence.get('exists'):
                fail('missing_saved_artifact', f'/outputs/{index}', 'Fulfilled artifact is absent on disk.')
            elif evidence.get('stable_during_capture') is False:
                missing.append(f'outputs.{index}.stable_artifact_snapshot')
    return dict(findings=failures, missing=missing, exercised=sorted(set(exercised)))


def semantic_contract(payload: dict) -> list:
    """An identity-independent multiset of anchored intent, not execution topology.

    Only runtime's intent ledger is compared: repair strategies can legitimately
    add phases and review branches. Cardinality and semantic content survive.
    """
    graph = (payload.get('runtime') or {}).get('request_phase_graph') or {}
    obligations = records(graph.get('intent_obligations'))
    identity_keys = {'obligation_id', 'phase_id', 'branch_id', 'task_id', 'queue_index', 'evidence'}
    dependency_keys = {'depends_on_obligation_ids', 'dependency_obligation_ids'}
    def meaning(item):
        # Use rebase's existing definition of stable record meaning. Retain new
        # semantic fields automatically, including cardinality and constraints.
        return {key: value for key, value in _semantic_record_payload(item, exclude_dependencies=True).items()
                if key not in identity_keys | dependency_keys}
    names = {item.get('obligation_id'): stable_digest(meaning(item)) for item in obligations}
    contracts = []
    for item in obligations:
        contract = meaning(item)
        for key in dependency_keys:
            if key in item:
                contract[key] = sorted(names.get(ref, ref) for ref in item[key])
        contracts.append(stable_digest(contract))
    return sorted(contracts)


def compare_profiles(baseline: dict, candidate: dict) -> list:
    if semantic_contract(baseline) != semantic_contract(candidate):
        return [finding('forbidden_semantic_divergence', '/runtime/request_phase_graph/intent_obligations',
                        'The same user turn produced a different anchored intent contract across controls.')]
    return []


def audit_history(snapshots: list[dict]) -> list:
    """Same frozen frame identity may not change its canonical frozen payload."""
    seen, findings = {}, []
    for snapshot in snapshots:
        frame = snapshot.get('response_frame') or {}
        frame_id = frame.get('frame_id')
        if not frame_id:
            continue
        # Frozen frame is the persisted unit; changing top-level projections is allowed.
        digest = stable_digest(frame)
        if frame_id in seen and seen[frame_id] != digest:
            findings.append(finding('frozen_frame_mutated', '/response_frame',
                                    'The same frozen frame identity changed during observation.'))
        # Working projections can legitimately update before the first freeze.
        # Once frozen, even a later projection back to working state is a fault.
        if frame.get('status') in SUCCESS | {'failed', 'incomplete', 'repair_needed', 'blocked', 'cancelled'}:
            seen[frame_id] = digest
    return findings


def audit_provider_bindings(call_records):
    """Check the actual fake-provider handoff against declared graph producers."""
    producers = {}
    results = []
    for call in call_records:
        request, response = call.get('payload') or {}, call.get('result') or {}
        identity = request.get('response_id')
        phase = request.get('phase_id')
        if call.get('capability') == 'text_to_speech':
            producers[(identity, phase)] = call
        if call.get('capability') != 'speech_to_text':
            continue
        dependencies = (request.get('execution_contract') or {}).get('depends_on') or []
        sources = [producers[(identity, p)] for p in dependencies if (identity, p) in producers]
        if len(sources) != 1:
            results.append(dict(response_id=identity, missing='exact_provider_source_handoff', findings=[]))
            continue
        source = sources[0]
        bound = (request.get('file_path') == (source.get('result') or {}).get('saved_audio_path')
                 and bool(call.get('input_sha256')) and call['input_sha256'] == source.get('output_sha256'))
        results.append(dict(response_id=identity, missing=None, findings=[] if bound else [finding(
            'consumer_artifact_binding_mismatch', '/provider_handoff/file_path',
            'Consumer input path/bytes differ from its exact declared producer artifact.')]))
    return results
