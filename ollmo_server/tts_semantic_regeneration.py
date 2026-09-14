"""One durable, producer-bound regeneration after affirmative TTS semantic failure.

This module consumes the existing verifier's verdict. It does not transcribe,
compare words, change obligations, or own Closure/Registry truth.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any, Mapping
from uuid import NAMESPACE_URL, uuid5

from ollmo_services.response_frames import _json_safe as _canonical_frame_value

POLICY_ID = 'tts_semantic_regeneration_v1'
MAX_SEMANTIC_REGENERATIONS = 1
STATE_KEY = 'tts_semantic_regeneration'
# This is a replay of authorized request controls, never provider results/state.
GENERATION_FIELDS = (
    'capability', 'model', 'instance_id', 'backend', 'prompt', 'lang_code',
    'voice', 'instruct', 'response_format', 'output_format', 'speed', 'pitch',
    'temperature', 'top_p', 'top_k', 'min_p', 'repetition_penalty', 'max_tokens',
)


def states(payload: Mapping[str, Any]) -> dict[str, Any]:
    return dict((payload.get('runtime') or {}).get(STATE_KEY) or {})


def request_snapshot(plan: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    """Retain the exact final authorized text and ordinary generation controls."""
    infer = plan.get('infer_payload') or {}
    source = result.get('tts_semantic_source') or {}
    if not isinstance(infer, Mapping) or not source.get('tts_source_text'):
        return {}
    # A caller-selected seed/ref/generator lifecycle is outside this first policy.
    if any(infer.get(k) not in (None, '', [], {}) for k in
           ('seed', 'random_seed', 'rng_state', 'generator', 'ref_audio', 'ref_text')):
        return {}
    snapshot = {k: copy.deepcopy(infer[k]) for k in GENERATION_FIELDS if k in infer}
    snapshot['prompt'] = source['tts_source_text']
    return snapshot


def _digest(path: str) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _ids(record: Mapping[str, Any]) -> set[str]:
    return {str(record.get(k) or '') for k in ('branch_id', 'phase_id')} - {''}


def execution_allowed(owner, branch, payload):
    """Honor explicit deferral/opt-out as well as the existing terminal gate."""
    controls = (payload.get('late_fill') or {}).get('branch_controls') or []
    records = [branch, *(r for r in controls
                         if isinstance(r, Mapping) and _ids(r).intersection(_ids(branch)))]
    for record in records:
        status = str(record.get('status') or record.get('action') or record.get('control_action') or '').lower()
        if (status in {'deferred', 'defer', 'blocked', 'cancelled', 'waived', 'superseded'}
                or record.get('automatic_follow_up_allowed') is False
                or record.get('needs_external_input') is True
                or record.get('materialization_blocked') is True):
            return False
    return owner.semantic_execution_gate_decision(branch, payload).get('action') == 'execute'


def eligibility(owner, branch, result, payload, consumer_plan) -> dict[str, Any]:
    evidence = result.get('tts_stt_semantic_evidence') or {}
    denied = {'eligible': False, 'policy_id': POLICY_ID}
    if (result.get('error') or result.get('blocked') is True
            or branch.get('capability') != 'speech_to_text'
            or evidence.get('authority') != 'runtime_deterministic_verification'
            or evidence.get('status') != 'mismatched'
            or evidence.get('reason_code') != 'TTS_STT_SEMANTIC_MISMATCH'
            or evidence.get('semantic_match') is not False):
        return {**denied, 'reason': 'affirmative_mismatch_required'}
    # Reuse the verifier, including exact source/dependency/authority checks.
    verified = owner.tts_stt_semantic_evidence_for_branch_result(
        branch, result, current_payload=payload)
    if verified != evidence:
        return {**denied, 'reason': 'stale_or_untrusted_semantic_evidence'}
    producer_id = str(evidence.get('producer_branch_id') or '')
    records = [r for r in (payload.get('late_fill') or {}).get('fill_results', [])
               if isinstance(r, Mapping) and r.get('branch_id') == producer_id
               and r.get('capability') == 'text_to_speech']
    if len(records) != 1:
        return {**denied, 'reason': 'unique_producer_required'}
    producer = records[0]
    producer_branches = [r for r in (payload.get('late_fill') or {}).get('completed_branches', [])
                         if r.get('branch_id') == producer_id]
    if len(producer_branches) != 1:
        return {**denied, 'reason': 'completed_authorized_producer_required'}
    producer_branch = producer_branches[0]
    if producer_id in states(payload):
        return {**denied, 'reason': 'semantic_repair_budget_consumed', 'producer_branch_id': producer_id}
    for record in (branch, producer_branch):
        if not execution_allowed(owner, record, payload):
            return {**denied, 'reason': 'execution_authority_not_current'}
    source = producer.get('tts_semantic_source') or {}
    snapshot = producer.get('tts_generation_request') or {}
    if not snapshot or snapshot.get('prompt') != source.get('tts_source_text'):
        return {**denied, 'reason': 'exact_generation_request_unavailable'}
    integrity = owner.tts_audio_integrity_evidence_for_branch_result(producer_branch, producer)
    if integrity.get('status') != 'passed' or integrity.get('materialization_eligible') is not True:
        return {**denied, 'reason': 'physical_audio_not_verified'}
    path = str(producer.get('saved_audio_path') or '')
    # Actual prepared STT input must select this exact file. No inference from prose.
    infer = consumer_plan.get('infer_payload') or {}
    selected = str(infer.get('file_path') or '')
    if not path or not selected or Path(selected).resolve() != Path(path).resolve():
        return {**denied, 'reason': 'consumer_file_binding_not_proven'}
    try:
        digest = _digest(path)
    except OSError:
        return {**denied, 'reason': 'audio_file_unavailable'}
    expected_digest = integrity.get('artifact_sha256') or integrity.get('audio_sha256')
    if not expected_digest or digest != expected_digest:
        return {**denied, 'reason': 'audio_digest_binding_not_proven'}
    attempt_id = 'tts-attempt-' + uuid5(NAMESPACE_URL, f"{payload['id']}:{producer_id}:{digest}").hex
    repair_id = 'tts-attempt-' + uuid5(NAMESPACE_URL, f'{POLICY_ID}:{attempt_id}').hex
    return dict(eligible=True, policy_id=POLICY_ID, producer_branch_id=producer_id,
                producer=copy.deepcopy(producer), producer_branch=copy.deepcopy(producer_branch),
                source=copy.deepcopy(source), generation_request=copy.deepcopy(snapshot),
                failed_attempt_id=attempt_id, repair_attempt_id=repair_id,
                failed_audio_sha256=digest, budget_before=0, budget_after=1)


def withdraw_audio(payload, producer):
    """Remove this attempt's publication; retain it in repair evidence, not outputs."""
    updated = copy.deepcopy(payload)
    path = str(producer.get('saved_audio_path') or '')
    refs = {str(producer.get(k) or '') for k in ('artifact_id', 'artifact_ref', 'ref')} - {''}
    def matches(record):
        return isinstance(record, Mapping) and (
            any(str(record.get(k) or '') == path for k in ('path', 'saved_audio_path', 'local_path'))
            or bool(refs.intersection(str(record.get(k) or '') for k in ('artifact_id', 'artifact_ref', 'ref'))))
    # Frozen response_frame is never edited. Current projections are rebuilt by
    # the existing finalizer from current fields and Late Fill truth.
    for key in ('artifacts', 'outputs', 'output'):
        if isinstance(updated.get(key), list):
            updated[key] = [r for r in updated[key] if not matches(r)]
    if updated.get('saved_audio_path') == path:
        for key in ('saved_audio_path', 'tts_semantic_source', 'tts_audio_integrity_evidence',
                    'tts_generation_budget', 'tts_sampling_profile'):
            updated.pop(key, None)
    if matches(updated.get('result')):
        updated.pop('result', None)
    late = updated.setdefault('late_fill', {})
    pid = producer['branch_id']
    for key in ('fill_results', 'completed_branches'):
        late[key] = [r for r in late.get(key, []) if r.get('branch_id') != pid]
    if late.get('saved_audio_path') == path:
        late.pop('saved_audio_path', None)
    return updated


def checkpoint(owner, payload, request_payload, producer_id):
    """CAS append + read-back; a successful finalizer return alone is not durability."""
    loader = getattr(owner, 'load_latest_response_state', None)
    frame = payload.get('response_frame') or {}
    if not callable(loader) or not frame.get('frame_id'):
        raise RuntimeError('TTS semantic repair requires durable frame identity')
    # Compare the complete reservation in its actual durable representation.
    # Frame encoding omits empty optional fields (e.g. defect_codes: []);
    # raw in-memory equality falsely rejects a successfully recovered checkpoint.
    expected = _canonical_frame_value(states(payload)[producer_id])
    framed = owner.finalize_response_frame_payload(
        payload, request_payload=request_payload, persist=True,
        expected_parent_frame_id=frame['frame_id'],
        expected_parent_frame_sequence=frame.get('frame_sequence'))
    durable = loader(payload['id'])
    recovered = durable.get('response_payload') or {}
    if (durable.get('ok') is not True
            or (durable.get('response_frame') or {}).get('frame_id') != (framed.get('response_frame') or {}).get('frame_id')
            or _canonical_frame_value(states(recovered).get(producer_id)) != expected):
        raise RuntimeError('TTS semantic repair checkpoint not durable')
    owner.touch_response_lookup(payload['id'], status='in_progress', response_payload=framed)
    return framed


def run(owner, *, branch, result, payload, consumer_plan, request_payload,
        artifact_gap, source_route_payload, prepare_plan, execute_plan):
    """Execute at most one new producer attempt, then its existing STT verifier.

    Called by the already claimed response worker, not by review callbacks.
    Durable parent CAS makes competing stale workers lose before backend work.
    A recovered consumed reservation is never re-executed (uncertain => blocked).
    """
    decision = eligibility(owner, branch, result, payload, consumer_plan)
    if not decision['eligible']:
        return None
    if not callable(getattr(owner, 'load_latest_response_state', None)):
        return None
    pid = decision['producer_branch_id']
    durable = owner.load_latest_response_state(payload['id'])
    durable_payload = durable.get('response_payload') or {}
    if durable.get('ok') is not True or pid in states(durable_payload):
        return None
    original = decision['producer']
    repaired = withdraw_audio(payload, original)
    entry = {
        'policy_id': POLICY_ID, 'status': 'consumed',
        'semantic_tts_repair_count': MAX_SEMANTIC_REGENERATIONS,
        'maximum_semantic_regenerations': MAX_SEMANTIC_REGENERATIONS,
        'budget_before': 0, 'budget_after': 1, 'remaining': 0,
        'failed_attempt_id': decision['failed_attempt_id'],
        'attempt_id': decision['repair_attempt_id'],
        'repairs_attempt': decision['failed_attempt_id'],
        'producer_branch_id': pid, 'producer_phase_id': original.get('phase_id'),
        'consumer_branch_id': branch.get('branch_id'),
        'original_result': copy.deepcopy(original),
        'original_semantic_evidence': copy.deepcopy(result['tts_stt_semantic_evidence']),
        'events': ['semantic_mismatch_established', 'eligible', 'budget_consumed'],
    }
    repaired.setdefault('runtime', {}).setdefault(STATE_KEY, {})[pid] = entry
    failed_producer = {**decision['producer_branch'], 'status': 'blocked',
                       'automatic_follow_up_allowed': False,
                       'error': {'code': 'TTS_STT_SEMANTIC_MISMATCH',
                                 'message': 'TTS semantic obligation remains unfulfilled.'},
                       'recovery_attempt': {'policy_id': POLICY_ID, 'attempt_id': entry['attempt_id'],
                                            'repairs_attempt': entry['repairs_attempt'], 'remaining': 0}}
    repaired['late_fill'].setdefault('failed_branches', []).append(failed_producer)
    # A crash after this point must retain both rejection and consumed budget.
    repaired = checkpoint(owner, repaired, request_payload, pid)
    entry = repaired['runtime'][STATE_KEY][pid]
    owner.log_unified_event(category='responses', action='tts_semantic_regeneration',
                            status='scheduled', response_id=payload['id'],
                            branch_id=pid, attempt_id=entry['attempt_id'],
                            repairs_attempt=entry['repairs_attempt'], maximum_attempts=1)
    new_result = None
    try:
        producer_branch = copy.deepcopy(decision['producer_branch'])
        producer_branch.update(status='pending', content_payload=decision['source']['tts_source_text'],
                               content_payload_source='tts_semantic_regeneration_exact_source')
        producer_branch['recovery_attempt'] = copy.deepcopy(failed_producer['recovery_attempt'])
        for key in ('error', 'attempt', 'recovery_context', 'saved_audio_path', 'artifacts',
                    'artifact_id', 'artifact_ref', 'result', 'tts_semantic_source'):
            producer_branch.pop(key, None)
        def execute_branch(target, current, *, generation=False):
            latest = owner.get_response_lookup_record(payload['id']) or {}
            gate_payload = latest.get('response_payload') or current
            if not execution_allowed(owner, target, gate_payload):
                raise RuntimeError('TTS semantic repair execution cancelled or deferred')
            spec = owner.build_late_fill_materialization_branch_spec(
                branch=target, artifact_gap=artifact_gap, current_payload=current,
                request_payload=request_payload, assistant_message='',
                source_route_payload=source_route_payload, failed_instance_id=None)
            if not spec:
                raise RuntimeError('TTS semantic repair branch contract unavailable')
            plan = prepare_plan(**spec['prepare_args'])
            if generation:
                # Keep the same model/route and exact authorized lexical payload;
                # do not replay a root request, RNG seed, cached output or result.
                instance = plan.get('instance') or {}
                if (str(instance.get('model') or '') != str(original.get('fill_model') or '')
                        or str((plan.get('route_info') or {}).get('instance_id') or '') != str(original.get('fill_instance_id') or '')):
                    raise RuntimeError('TTS semantic repair provider identity changed')
                infer = plan.setdefault('infer_payload', {})
                for key in ('seed', 'random_seed', 'rng_state', 'generator', 'saved_audio_path',
                            'route_reuse_last_artifact', 'route_artifact_path', 'route_artifact_ref',
                            'file_path', 'file_paths', 'files', 'reference_artifacts',
                            'selected_reference_artifacts', 'selected_reference_artifact'):
                    infer.pop(key, None)
                infer.update(copy.deepcopy(decision['generation_request']))
                infer['prompt'] = decision['source']['tts_source_text']
                plan['effective_data']['content_payload'] = infer['prompt']
                plan['effective_data']['content_payload_source'] = 'tts_semantic_regeneration_exact_source'
            # Plan preparation is not execution authority if controls changed.
            latest = owner.get_response_lookup_record(payload['id']) or {}
            if not execution_allowed(owner, target, latest.get('response_payload') or current):
                raise RuntimeError('TTS semantic repair cancelled before invocation')
            executed = execute_plan(plan)
            latest = owner.get_response_lookup_record(payload['id']) or {}
            if not execution_allowed(owner, target, latest.get('response_payload') or current):
                raise RuntimeError('TTS semantic repair result superseded or cancelled')
            return executed, plan

        produced, producer_plan = execute_branch(producer_branch, repaired, generation=True)
        audio_result = copy.deepcopy(produced.get('infer_result') or {})
        new_result = {**audio_result, 'branch_id': pid, 'phase_id': original.get('phase_id'),
                      'capability': 'text_to_speech',
                      'fill_model': original.get('fill_model'), 'fill_backend': original.get('fill_backend'),
                      'fill_instance_id': original.get('fill_instance_id'),
                      'execution_contract': copy.deepcopy(produced.get('execution_contract') or original.get('execution_contract') or {}),
                      'recovery_attempt': copy.deepcopy(producer_branch['recovery_attempt']),
                      'tts_generation_request': copy.deepcopy(decision['generation_request'])}
        entry['repair_result'] = copy.deepcopy(new_result)
        if new_result.get('cached') is True or new_result.get('route_reuse_last_artifact') is True:
            raise RuntimeError('TTS semantic repair returned a cached artifact')
        new_path = str(new_result.get('saved_audio_path') or '')
        if (not new_path or Path(new_path).resolve() == Path(original['saved_audio_path']).resolve()
                or _digest(original['saved_audio_path']) != decision['failed_audio_sha256']):
            raise RuntimeError('TTS semantic repair did not preserve distinct artifact paths')
        if _digest(new_path) == decision['failed_audio_sha256']:
            raise RuntimeError('TTS semantic repair returned the failed audio bytes')
        for key in ('artifact_id', 'artifact_ref'):
            if original.get(key) and new_result.get(key) == original[key]:
                raise RuntimeError('TTS semantic repair reused failed artifact identity')
        if (new_result.get('tts_semantic_source') or {}).get('tts_source_text_sha256') != decision['source']['tts_source_text_sha256']:
            raise RuntimeError('TTS semantic repair changed authorized source')
        if owner.dependency_evidence_error_for_branch_result(producer_branch, new_result, current_payload=repaired):
            raise RuntimeError('TTS semantic repair failed technical verification')
        new_result = owner.attach_late_fill_result_artifact_identity(
            new_result, repaired, audio_result, capability='text_to_speech')
        entry['repair_result'] = copy.deepcopy(new_result)
        entry['status'] = 'verification_pending'
        entry['events'].append('fresh_artifact_created')
        repaired = checkpoint(owner, repaired, request_payload, pid)
        entry = repaired['runtime'][STATE_KEY][pid]
        # B is evidence for STT here, not yet public fulfillment.
        candidate = copy.deepcopy(repaired)
        candidate['late_fill']['fill_results'].append(copy.deepcopy(new_result))
        candidate['late_fill']['completed_branches'].append({**producer_branch, 'status': 'fulfilled'})
        candidate['late_fill']['failed_branches'] = [r for r in candidate['late_fill']['failed_branches'] if r.get('branch_id') != pid]
        observed, stt_plan = execute_branch(branch, candidate)
        verified_result = copy.deepcopy(observed.get('infer_result') or {})
        selected = str((stt_plan.get('infer_payload') or {}).get('file_path') or '')
        if not selected or Path(selected).resolve() != Path(new_path).resolve():
            raise RuntimeError('TTS semantic repair verification bound to wrong audio')
        evidence = owner.tts_stt_semantic_evidence_for_branch_result(branch, verified_result, current_payload=candidate)
        verified_result['tts_stt_semantic_evidence'] = evidence
        entry['repair_semantic_evidence'] = copy.deepcopy(evidence)
        error = owner.dependency_evidence_error_for_branch_result(branch, verified_result, current_payload=candidate)
        if error or evidence.get('status') != 'matched':
            raise RuntimeError('TTS semantic repair did not pass existing semantic verifier')
        entry['status'] = 'accepted'
        entry['events'].append('repair_semantic_pass')
        candidate['runtime'][STATE_KEY][pid] = entry
        accepted = owner.merge_late_fill_result_fields(candidate, new_result)
        accepted = checkpoint(owner, accepted, request_payload, pid)
        return {'payload': accepted, 'infer_result': verified_result, 'accepted': True,
                'producer_branch_id': pid, 'attempt_id': entry['attempt_id']}
    except Exception as exc:
        # Once consumed, all failure classes stay blocked. Never recursively repair.
        entry['status'] = 'exhausted'
        entry['events'].append('repair_exhausted')
        entry['error'] = str(exc)
        repaired['runtime'][STATE_KEY][pid] = entry
        repaired = checkpoint(owner, repaired, request_payload, pid)
        return {'payload': repaired, 'infer_result': result, 'accepted': False,
                'producer_branch_id': pid, 'attempt_id': entry['attempt_id']}


def consumed_execution_error(branch, payload):
    """A recovered/Closure-projected producer cannot replay a consumed repair."""
    if branch.get('capability') != 'text_to_speech':
        return None
    tokens = _ids(branch)
    for entry in states(payload).values():
        if tokens.intersection({str(entry.get('producer_branch_id') or ''), str(entry.get('producer_phase_id') or '')} - {''}):
            return {'code': 'TTS_SEMANTIC_REGENERATION_EXHAUSTED',
                    'stage': 'semantic_regeneration_budget', 'retryable': False,
                    'materialization_blocked': True, 'repair_action': 'manual_review',
                    'message': 'The one durable semantic TTS regeneration was already consumed; it cannot be resubmitted.'}
    return None
