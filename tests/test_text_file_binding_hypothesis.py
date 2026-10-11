"""One bounded offline property family; no live providers or runtime substitutes.

Oracle values precede provider generation. Owner checks are supplementary to
real Responses/Internal Infer/physical writer/closure/frame-recovery sequences.
All invocation witnesses (including shrinks/rechecks) are append-only.
"""
from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
from unittest.mock import patch

import pytest
from hypothesis import example, given, reproduce_failure, seed, settings, strategies as st
from hypothesis.errors import DidNotReproduce

import fruth_core.inference as core
import fruth_webserver as web
from fruth_services.response_frames import _read_snapshot_ref_payload
from tests.test_instruction_admission_contract import real_owners
from tests.test_structured_admission_grounding_audit import (
    final_projection, graph_files, request, selected, settle, trace_materialization,
    test_exact_direct_markdown_positive as direct_markdown_control,
    test_self_contained_generic_responses_retains_bounded_format as generic_control,
    test_filename_free_bounded_selected_file_edit_positive as revision_control,
    test_structured_producer_cannot_rewrite_saved_file_dependencies as dependency_control,
)


BODY = '# The permitted sentence.'
BODY_BYTES = b'# The permitted sentence.\n'
WRAPPERS = ('json', 'request_ir', 'payload', 'json_fence', 'tag', 'fence')
_COUNTS = Counter()


def bounded_settings(lane):
    # These are test example budgets, not runtime safety/request/repair limits.
    return settings(max_examples=int(os.environ.get('FRUTH_HYPOTHESIS_' + lane.upper(),
                        '8' if lane == 'adapter' else '80')),
                    deadline=None, print_blob=True, report_multiple_bugs=False)


def accepted_outputs(count, extension='txt', targeted=False, root=None):
    """Independent caller oracle; no graph, result or binding-helper input."""
    names = ('allowed', 'second')[:count]
    return [{'filename': name + '.' + extension, 'extension': extension,
             'source_name': name, 'body_hex': BODY_BYTES.hex(),
             'target_path': str(root / (name + '.' + extension)) if targeted else None}
            for name in names]


def contracts(oracle):
    return [{k: v for k, v in {
        'extension': o['extension'], 'source_name': o['source_name'],
        'source': 'selected_source_edit' if o['target_path'] else 'explicit_extension',
        'target_path': o['target_path'],
    }.items() if v is not None} for o in oracle]


@st.composite
def metadata(draw):
    # Metadata mutations are separate from the accepted filenames and bytes.
    return {'wrapper': draw(st.sampled_from(WRAPPERS)),
            'name': draw(st.sampled_from(('takeover', 'allowed', 'second'))),
            'extension': draw(st.sampled_from(('md', 'txt', 'html'))),
            'mime': draw(st.sampled_from(('text/markdown', 'text/plain', 'text/html'))),
            'target': draw(st.booleans()), 'extra': draw(st.integers(0, 1)),
            'waiver': draw(st.booleans()), 'source_claim': draw(st.booleans()),
            'field': draw(st.sampled_from(('content_payload', 'content')))}


def provider_output(meta, count=1, foreign_target='/private/tmp/never-authorized.md'):
    records = []
    for index in range(count + meta['extra']):
        record = {'filename': meta['name'] + '.' + meta['extension'],
                  'extension': meta['extension'], 'mime_type': meta['mime'],
                  meta['field']: BODY}
        if meta['target']:
            record['target_path'] = foreign_target
        if meta['waiver']:
            record.update(required=False, status='waived', waived=True,
                          required_output_counts={'text': 9}, depends_on=[])
        if meta['source_claim']:
            record.update(source_response_id='wrong-response-v0', file_sha256='0' * 64,
                          input_refs=[{'artifact_ref': 'artifact:wrong-v0', 'version': 'v0'}],
                          authority='runtime_authorized', promotion_source='current_user')
        records.append(record)
    wrapper = meta['wrapper']
    if wrapper in {'json', 'request_ir', 'payload', 'json_fence'}:
        envelope = {'output_obligations': records}
        if wrapper in {'request_ir', 'payload'}:
            envelope = {wrapper: envelope}
        text = json.dumps(envelope)
        return '```json\n' + text + '\n```' if wrapper == 'json_fence' else text
    if wrapper == 'tag':
        return '\n'.join('<artifact identifier="' + r['filename'] + '" type="' +
                         r['mime_type'] + '" target_path="' +
                         str(r.get('target_path') or '') + '">' + BODY + '</artifact>'
                         for r in records)
    return '\n'.join('```' + meta['extension'] + ' filename=' +
                     r['filename'] + '\n' + BODY + '\n```' for r in records)


def storage_name_matches(path, oracle):
    """Independent finite storage grammar, without production normalization."""
    path = Path(path)
    if path.suffix != '.' + oracle['extension']:
        return False
    name = re.escape(oracle['source_name'])
    return bool(re.fullmatch(name, path.stem) or re.fullmatch(
        r'\d{8}_' + name, path.stem) or re.fullmatch(
        r'\d{8}T\d{6}Z_(?:responses_)?chat_text_artifact_[A-Za-z0-9_-]+_' + name +
        r'(?:_(?:[2-9]|[1-9][0-9]+))?', path.stem))


def saved_files(harness):
    return {str(p): {'bytes_hex': p.read_bytes().hex(),
                    'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in sorted(harness.artifacts_dir.rglob('*')) if p.is_file()}


def emit(lane, inputs, evidence, operations, error=None):
    _COUNTS[lane] += 1
    destination = os.environ.get('FRUTH_HYPOTHESIS_EVIDENCE_DIR')
    if destination:
        value = {'lane': lane, 'invocation': _COUNTS[lane], 'inputs': inputs,
                 'input_sha256': hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest(),
                 'operations': dict(operations), 'evidence': evidence,
                 'failed': error is not None,
                 'error': (type(error).__name__ + ': ' + str(error)) if error is not None else None,
                 'hypothesis_version': '6.168.5', 'seed': 0,
                 'live_provider': False, 'provider_vs_fault': 'separate trace and fault fields'}
        path = Path(destination) / (lane + '-' + str(_COUNTS[lane]).zfill(5) + '.json')
        with path.open('x') as stream:
            json.dump(value, stream, indent=2, default=str)
            stream.write('\n')


def check_extraction(count, extension, targeted, meta):
    oracle = accepted_outputs(count, extension, targeted, Path('/private/tmp/accepted-pilot-targets'))
    expected_contracts = contracts(oracle)
    original = deepcopy(expected_contracts)
    controlled = provider_output(meta, count)
    literal_expected = (meta['extension'] == extension
                        or (extension == 'txt' and meta['extension'] == 'md'))
    evidence, error = {'literal_control_compatible': literal_expected,
                       'phase_acceptance_exercised': False}, None
    try:
        extracted = core.extract_text_artifact_payloads(controlled, expected_contracts)
        evidence['extracted'] = extracted
        assert expected_contracts == original
        assert len(extracted) <= count
        identities = []
        for item in extracted:
            binding = item['artifact_request']
            identity = (binding['extension'], binding['source_name'], binding.get('target_path'))
            assert identity in [(o['extension'], o['source_name'], o['target_path']) for o in oracle]
            identities.append(identity)
            if literal_expected:
                assert (item['content'].encode() + b'\n') == BODY_BYTES
        assert len(set(identities)) == len(identities)
        # Lower extractor parses content too; phase rejection belongs to adapters.
        if (literal_expected and meta['wrapper'] in {'json', 'request_ir', 'payload', 'json_fence'}
                and extension == 'txt'):
            assert len(extracted) == count
    except Exception as exc:
        error = exc
        raise
    finally:
        emit('extractor', {'oracle': oracle, 'metadata': meta, 'provider_output': controlled},
             evidence, {'extractor_calls': 1}, error)


@seed(0)
@bounded_settings('owner')
@given(count=st.integers(1, 2), extension=st.sampled_from(('txt', 'md')),
       targeted=st.booleans(), meta=metadata())
def test_provider_wrappers_preserve_accepted_bindings(count, extension, targeted, meta):
    check_extraction(count, extension, targeted, meta)


@st.composite
def result_fault(draw):
    return {'path': draw(st.sampled_from(('none', 'name', 'extension', 'collision_sibling'))),
            'identity': draw(st.sampled_from(('none', 'name', 'extension', 'target'))),
            'digest': draw(st.booleans())}


def change_identity(record, fault, wrong_target):
    record = deepcopy(record)
    claim = dict(record.get('text_artifact_request') or record.get('artifact_request') or {})
    if fault['identity'] == 'name':
        record['text_artifact_source_name'] = claim['source_name'] = 'takeover'
    if fault['identity'] == 'extension':
        record['text_artifact_extension'] = claim['extension'] = 'html'
    if fault['identity'] == 'target':
        record['text_artifact_target_path'] = claim['target_path'] = str(wrong_target)
    record['text_artifact_request'] = claim
    if fault['digest']:
        record['file_sha256'] = '0' * 64
    return record


def check_saved_result(storage, fault, duplicate, *, deterministic=False, clean_first=False):
    with tempfile.TemporaryDirectory(prefix='fruth-hypothesis-owner-') as temporary:
        with real_owners(Path(temporary), 'Unused controlled provider.') as harness:
            oracle = accepted_outputs(1)[0]
            filenames = {
                'exact': 'allowed.txt', 'date': '20260904_allowed.txt',
                'timestamp': '20261008T120000Z_chat_text_artifact_model_allowed.txt',
                'collision': '20261008T120000Z_chat_text_artifact_model_allowed_2.txt',
            }
            path = harness.documents_dir / filenames[storage]
            if fault['path'] == 'name':
                path = path.with_name('takeover.txt')
            elif fault['path'] == 'extension':
                path = path.with_suffix('.md')
            elif fault['path'] == 'collision_sibling':
                path = path.with_name('allowed_2.txt')
            path.write_bytes(BODY_BYTES)  # Deliberate result substrate, not provider output.
            contract = contracts([oracle])[0]
            clean = {'type': 'text', 'path': str(path), 'text_artifact_request': contract,
                     'file_sha256': hashlib.sha256(BODY_BYTES).hexdigest(),
                     'origin': 'assistant_output', 'source_response_id': 'result-owner-pilot'}
            record = change_identity(clean, fault, harness.documents_dir / 'unapproved.txt')
            records = [record] + ([deepcopy(clean)] if duplicate else [])
            if clean_first:
                records.reverse()
            result = {'saved_text_path': str(path), 'saved_text_artifacts': records}
            branch = {'requires_artifact': True, 'required': True, 'output_type': 'text',
                      'capability': 'chat', 'role': 'text_artifact_output',
                      'stage_direction': 'materialize_requested_text_artifact',
                      'artifact_request': contract, 'text_artifact_extension': 'txt',
                      'text_artifact_source_name': 'allowed'}
            valid = storage_name_matches(path, oracle) and fault['identity'] == 'none' and not fault['digest']
            evidence, error = {'deliberate_saved_file': saved_files(harness),
                               'result': result, 'expected_valid': valid}, None
            try:
                assert web._LATE_FILL_RUNTIME._branch_is_required_text_artifact(branch)
                checked, binding_error = web._LATE_FILL_RUNTIME._ensure_required_text_artifact_saved_truth(
                    branch, result, {}, {})
                evidence.update(checked_result=checked, binding_error=binding_error)
                canonical = web._LATE_FILL_RUNTIME._canonical_text_artifact_saved_result(
                    {'id': 'result-owner-pilot', 'artifacts': records}, extension='txt', source_name='allowed')
                evidence['canonical_owner_result'] = canonical
                assert (binding_error is None) == valid
                assert bool(canonical) == valid, 'conflicting saved evidence became canonical reusable output'
                assert path.read_bytes() == BODY_BYTES
                assert harness.provider_calls == []
            except Exception as exc:
                error = exc
                raise
            finally:
                emit('result-owner', {'oracle': oracle, 'storage': storage, 'fault': fault,
                                     'duplicate_clean_record': duplicate,
                                     'clean_first': clean_first,
                                     'deterministic_replay': deterministic}, evidence,
                     {'injected_substrate_writes': 1, 'saved_truth_calls': 1,
                      'canonical_owner_calls': 1}, error)


@seed(0)
@bounded_settings('owner')
@given(storage=st.sampled_from(('exact', 'date', 'timestamp', 'collision')),
       fault=result_fault(), duplicate=st.booleans())
def test_saved_identity_and_conflicting_evidence_fail_closed(storage, fault, duplicate):
    check_saved_result(storage, fault, duplicate)


def assert_bindings(projection, oracle, *, deliberately_faulted=False):
    obligations = graph_files(projection)
    observed = {(o.get('text_artifact_extension') or (o.get('artifact_request') or {}).get('extension'),
                 o.get('text_artifact_source_name') or (o.get('artifact_request') or {}).get('source_name'))
                for o in obligations}
    assert observed == {(o['extension'], o['source_name']) for o in oracle}
    assert not any(o.get('status') == 'waived' for o in obligations)
    if not deliberately_faulted:
        assert not any(a.get('name') == 'takeover' for a in projection.get('artifacts', []))


def run_adapter(count, attached, meta, fault=None, recoveries=1):
    with tempfile.TemporaryDirectory(prefix='fruth-hypothesis-adapter-') as temporary:
        oracle = accepted_outputs(count)
        controlled = provider_output(meta)
        # Multi-output success executes branch-local payloads; root preparation
        # cannot supply two independent files through one competing envelope.
        def reply(call, index):
            text = '\n'.join(str(m.get('content') or '') for m in call['request'].get('messages', []))
            if count == 2 and all(o['filename'] in text for o in oracle):
                if index == 1:
                    return 'Preparation complete.'
                # Existing owner coalesces same-type files into an atomic set.
                # The provider fixture supplies that complete accepted set.
                return provider_output(meta, count, str(foreign))
            return controlled
        with real_owners(Path(temporary), reply) as harness:
            references, snapshots = [], []
            if attached:
                ref, snapshot = selected(harness)
                references, snapshots = [ref], [snapshot]
            payload = request(' '.join('Create ' + o['filename'] + ' containing "' + BODY + '".'
                                      for o in oracle), references)
            foreign = harness.documents_dir / 'never-authorized.md'
            controlled = provider_output(meta, foreign_target=str(foreign))
            fault_events, evidence, operations, error = [], {}, Counter(), None
            started = time.monotonic()
            result, final = {}, {}
            try:
                with trace_materialization(harness), ExitStack() as stack:
                    if fault:
                        writer, internal = web._persist_text_artifact_locally, web._invoke_internal_api_json_route
                        def fault_writer(content, **kwargs):
                            saved = writer(content, **kwargs)
                            if saved and fault['path'] != 'none':
                                original = Path(saved)
                                assert storage_name_matches(original, oracle[0])
                                assert original.read_bytes() == BODY_BYTES
                                wrong = (original.with_suffix('.md') if fault['path'] == 'extension'
                                         else original.with_name('allowed_2.txt') if fault['path'] == 'collision_sibling'
                                         else original.with_name(original.stem + '-wrong.txt'))
                                original.rename(wrong)
                                fault_events.append({'kind': 'deliberate_result_move',
                                    'authorized_path': str(original), 'returned_path': str(wrong),
                                    'bytes_hex': wrong.read_bytes().hex()})
                                operations['deliberate_fault_moves'] += 1
                                return str(wrong)
                            return saved
                        def fault_result(*args, **kwargs):
                            value, status = internal(*args, **kwargs)
                            if value.get('saved_text_path'):
                                before = deepcopy(value)
                                if fault.get('single_top_level_target'):
                                    value = deepcopy(value)
                                    value['text_artifact_target_path'] = str(foreign)
                                    fault_events.append({'kind': 'deliberate_returned_metadata',
                                                         'before': before, 'after': deepcopy(value)})
                                    operations['deliberate_result_mutations'] += 1
                                    return value, status
                                # Input digest at top level is not output evidence.
                                value = change_identity(value, {**fault, 'digest': False}, foreign)
                                value['saved_text_artifacts'] = [change_identity(r, fault, foreign)
                                    for r in value.get('saved_text_artifacts') or []]
                                if fault.get('duplicate_clean_record'):
                                    value['saved_text_artifacts'].extend(deepcopy(
                                        before.get('saved_text_artifacts') or []))
                                    if fault.get('clean_first'):
                                        value['saved_text_artifacts'].reverse()
                                fault_events.append({'kind': 'deliberate_returned_metadata',
                                                     'before': before, 'after': deepcopy(value)})
                                operations['deliberate_result_mutations'] += 1
                            return value, status
                        stack.enter_context(patch.object(web, '_persist_text_artifact_locally', fault_writer))
                        stack.enter_context(patch.object(web, '_invoke_internal_api_json_route', fault_result))
                    operations['response_posts'] += 1
                    result, status = harness.post_response(payload)
                    evidence.update(post_result=deepcopy(result), http_status=status)
                    assert status == 200
                    operations['settle_sequences'] += 1
                    operations['late_fill_workers'] += len(harness.scheduled)
                    final = settle(harness, result, payload)
                    operations['frame_recoveries'] += 1
                    recovered = [final_projection(final)]
                    recovered_provenance = [[deepcopy(r.get('text_artifact_saved_evidence'))
                        for r in final.get('saved_text_artifacts') or []
                        if r.get('text_artifact_saved_evidence')]]
                    for _ in range(recoveries - 1):
                        harness.clear_response_lookup()
                        state = harness.response_state(result['id'])
                        operations['frame_recoveries'] += 1
                        assert state['ok']
                        final = state['response_payload']
                        recovered.append(final_projection(final))
                        recovered_provenance.append([deepcopy(r.get('text_artifact_saved_evidence'))
                            for r in final.get('saved_text_artifacts') or []
                            if r.get('text_artifact_saved_evidence')])
                        assert recovered_provenance[-1] == recovered_provenance[0]
                    evidence['recovered_states'] = recovered
                    evidence['recovered_saved_provenance'] = recovered_provenance
                projections = (harness.before_frame_recovery, final)
                # Wire compaction may omit runtime diagnostics from the returned
                # view. Canonical recovery must carry the complete owner truth.
                assert final.get('runtime'), 'canonical recovery lacks runtime truth'
                structured_projections = [p for p in projections if p.get('runtime')]
                for projection in structured_projections:
                    assert_bindings(projection, oracle, deliberately_faulted=bool(fault))
                physical = saved_files(harness)
                generated = {p: value for p, value in physical.items()
                             if not p.endswith('/selected-source.txt') and '/inputs/' not in p}
                writes = [e for e in harness.admission_trace if e['event'] == 'physical_text_write']
                for event in writes:
                    assert any(storage_name_matches(event['path'], o) for o in oracle)
                    assert event['sha256'] == hashlib.sha256(BODY_BYTES).hexdigest()
                assert not foreign.exists()
                if attached:
                    assert Path(ref['path']).read_bytes() == snapshots[0]['text'].encode()
                rejected = meta['wrapper'] in {'json', 'request_ir', 'payload', 'json_fence'} and (
                    meta['field'] == 'content' or meta['extra'] > 0 or count == 2)
                if rejected:
                    assert not generated and not writes
                    for projection in projections:
                        assert projection['lifecycle_state'] == 'repair_needed'
                    for projection in structured_projections:
                        assert projection['runtime']['graph_closure_review']['status'] != 'fulfilled'
                elif fault and (fault['path'] != 'none' or fault['identity'] != 'none' or fault['digest']):
                    assert fault_events, 'fault fixture never reached a saved result'
                    assert generated and all(bytes.fromhex(f['bytes_hex']) == BODY_BYTES
                                             for f in generated.values()), 'diagnostic bytes changed or disappeared'
                    for projection in projections:
                        assert projection['lifecycle_state'] != 'completed', \
                            'faulted saved identity/evidence completed accepted obligation'
                    for projection in structured_projections:
                        assert projection['runtime']['graph_closure_review']['status'] != 'fulfilled', \
                            'faulted saved identity/evidence fulfilled accepted obligation'
                        assert all(o.get('status') != 'fulfilled' for o in graph_files(projection))
                        rejected_evidence = [r.get('text_artifact_saved_evidence')
                            for r in projection.get('saved_text_artifacts') or []
                            if (r.get('text_artifact_saved_evidence') or {}).get('status') == 'rejected']
                        assert rejected_evidence, 'saved rejection provenance disappeared'
                        for saved_evidence in rejected_evidence:
                            assert saved_evidence['source'] == 'root_saved_result_validation'
                            assert saved_evidence['accepted_request'] == contracts(oracle)[0]
                            assert saved_evidence['error']['code'] == 'TEXT_ARTIFACT_BINDING_VIOLATION'
                            assert saved_evidence['declarations']
                        evidence.setdefault('rejected_saved_evidence', []).append(deepcopy(rejected_evidence))
                        if projection is final:
                            artifact_frame = (projection.get('response_frame') or {}).get('artifacts') or {}
                            dossiers = artifact_frame.get('dossiers') or {}
                            if not dossiers and artifact_frame.get('dossiers_snapshot_ref'):
                                dossiers = _read_snapshot_ref_payload(
                                    artifact_frame['dossiers_snapshot_ref'], frames_dir=harness.response_frames_dir,
                                    strict_child_refs=True) or {}
                                operations['diagnostic_snapshot_reads'] += 1
                            evidence['canonical_diagnostic_dossiers'] = deepcopy(dossiers)
                            assert any((d.get('artifact', {}).get('text_artifact_saved_evidence') or {}).get('status') == 'rejected'
                                       for d in dossiers.values()), 'canonical artifact dossier lost rejection'
                        canonical = web._LATE_FILL_RUNTIME._canonical_text_artifact_saved_result(
                            projection, extension='txt', source_name='allowed')
                        operations['canonical_owner_calls'] += 1
                        assert not canonical
                elif not meta['extra']:
                    # Explicit successful controls prevent a vacuous rejection pass.
                    assert len(generated) == count
                    for oracle_output in oracle:
                        matches = [p for p in generated if storage_name_matches(p, oracle_output)]
                        assert len(matches) == 1
                        assert bytes.fromhex(generated[matches[0]]['bytes_hex']) == BODY_BYTES
                    assert final['runtime']['graph_closure_review']['status'] == 'fulfilled'
                    assert final['lifecycle_state'] == 'completed'
            except Exception as exc:
                error = exc
                raise
            finally:
                trace = deepcopy(getattr(harness, 'admission_trace', []))
                operations['provider_calls'] = len(harness.provider_calls)
                operations['physical_provider_writes'] = sum(e['event'] == 'physical_text_write' for e in trace)
                operations['saved_truth_calls'] = sum(e['event'] == 'required_file_saved_truth' for e in trace)
                operations['phase_acceptance_calls'] = sum(e['event'] == 'responses_phase_acceptance' for e in trace)
                if error is not None:
                    evidence.update(counterexample_full_settled=deepcopy(
                        getattr(harness, 'before_frame_recovery', result)),
                        counterexample_full_recovered=deepcopy(final))
                evidence.update(physical_files=saved_files(harness), request=payload,
                    source_snapshots_before=snapshots, provider_calls=deepcopy(harness.provider_calls),
                    trace=trace, deliberate_result_faults=fault_events,
                    settled=final_projection(getattr(harness, 'before_frame_recovery', result)),
                    recovered=final_projection(final), elapsed_seconds=time.monotonic() - started)
                emit('adapter-fault' if fault else 'adapter-provider',
                     {'oracle': oracle, 'count': count, 'selected_source': attached,
                      'metadata': meta, 'fault': fault, 'recoveries': recoveries,
                      'controlled_output': controlled}, evidence, operations, error)


@seed(0)
@bounded_settings('adapter')
@example(count=1, attached=True, recoveries=1, meta={
    'wrapper': 'json', 'name': 'takeover', 'extension': 'md', 'mime': 'text/html',
    'target': True, 'extra': 0, 'waiver': True, 'source_claim': True,
    'field': 'content_payload', 'explicit_case': 'selected-json'})
@example(count=1, attached=False, recoveries=2, meta={
    'wrapper': 'tag', 'name': 'takeover', 'extension': 'md', 'mime': 'text/markdown',
    'target': True, 'extra': 0, 'waiver': False, 'source_claim': False,
    'field': 'content_payload', 'explicit_case': 'direct-tag'})
@example(count=2, attached=False, recoveries=1, meta={
    'wrapper': 'fence', 'name': 'takeover', 'extension': 'md', 'mime': 'text/html',
    'target': False, 'extra': 0, 'waiver': False, 'source_claim': False,
    'field': 'content_payload', 'explicit_case': 'two-branch-fences'})
@example(count=1, attached=True, recoveries=1, meta={
    'wrapper': 'json', 'name': 'takeover', 'extension': 'md', 'mime': 'text/markdown',
    'target': True, 'extra': 0, 'waiver': True, 'source_claim': True,
    'field': 'content', 'explicit_case': 'selected-rejected-control'})
@given(count=st.integers(1, 2), attached=st.booleans(), meta=metadata(),
       recoveries=st.integers(1, 2))
def test_real_adapters_preserve_provider_binding_and_rejection(count, attached, meta, recoveries):
    run_adapter(count, attached, meta, recoveries=recoveries)


@seed(0)
@bounded_settings('adapter')
@given(kind=st.sampled_from(('none', 'physical_name', 'physical_extension',
                            'physical_collision_sibling', 'returned_name',
                            'returned_extension', 'returned_target', 'output_digest')),
       recoveries=st.integers(1, 2))
def test_real_result_faults_cannot_fulfill_after_recovery(kind, recoveries):
    # Real adapter representatives fault one axis. The faster result-owner lane
    # independently combines path, returned identity and digest mutations.
    fault = {'path': kind.removeprefix('physical_') if kind.startswith('physical_') else 'none',
             'identity': kind.removeprefix('returned_') if kind.startswith('returned_') else 'none',
             'digest': kind == 'output_digest'}
    meta = {'wrapper': 'json', 'name': 'takeover', 'extension': 'md',
            'mime': 'text/markdown', 'target': False, 'extra': 0, 'waiver': True,
            'source_claim': True, 'field': 'content_payload'}
    run_adapter(1, True, meta, fault=fault, recoveries=recoveries)


def test_required_positive_controls(tmp_path):
    # Reuse the exact independent fixed-byte/dependency controls, with witnesses.
    for label, control in (('direct-markdown', direct_markdown_control),
                           ('generic-save', generic_control),
                           ('selected-target-revision', revision_control),
                           ('saved-json-read-html', dependency_control)):
        control(tmp_path / label)
        emit('positive-control', {'case': label}, {'exact_existing_control_passed': True},
             {'control_cases': 1})


@pytest.mark.parametrize('clean_first', [False, True])
def test_regression_duplicate_digest_evidence_cannot_become_canonical(clean_first):
    """Deterministic minimum retained from Hypothesis 6.168.5 replay."""
    check_saved_result('exact', {'path': 'none', 'identity': 'none', 'digest': True},
                       True, deterministic=True, clean_first=clean_first)


@pytest.mark.parametrize('clean_first', [False, True])
def test_regression_real_conflicting_duplicate_digest_cannot_fulfill(clean_first):
    """Actual adapter reproduction, separate from provider-induced effects."""
    meta = {'wrapper': 'json', 'name': 'takeover', 'extension': 'md',
            'mime': 'text/markdown', 'target': False, 'extra': 0, 'waiver': False,
            'source_claim': False, 'field': 'content_payload'}
    run_adapter(1, True, meta, fault={'path': 'none', 'identity': 'none',
                                    'digest': True, 'duplicate_clean_record': True,
                                    'clean_first': clean_first}, recoveries=2)


def test_regression_real_returned_target_conflict_cannot_fulfill():
    meta = {'wrapper': 'json', 'name': 'takeover', 'extension': 'md',
            'mime': 'text/markdown', 'target': False, 'extra': 0, 'waiver': False,
            'source_claim': False, 'field': 'content_payload'}
    run_adapter(1, True, meta, fault={'path': 'none', 'identity': 'target', 'digest': False})


def test_regression_one_returned_target_field_cannot_fulfill():
    """Smaller real witness: one incorrect top-level target field, no path move."""
    meta = {'wrapper': 'json', 'name': 'allowed', 'extension': 'txt',
            'mime': 'text/plain', 'target': False, 'extra': 0, 'waiver': False,
            'source_claim': False, 'field': 'content_payload'}
    run_adapter(1, True, meta, fault={'path': 'none', 'identity': 'target',
                                    'digest': False, 'single_top_level_target': True}, recoveries=3)


@pytest.mark.parametrize('kind', ['physical_name', 'physical_extension',
                                 'returned_name', 'returned_extension', 'output_digest'])
def test_deterministic_result_fault_representatives(kind):
    """Cover the remaining axes even when Hypothesis stops at its first error."""
    fault = {'path': kind.removeprefix('physical_') if kind.startswith('physical_') else 'none',
             'identity': kind.removeprefix('returned_') if kind.startswith('returned_') else 'none',
             'digest': kind == 'output_digest'}
    meta = {'wrapper': 'json', 'name': 'allowed', 'extension': 'txt',
            'mime': 'text/plain', 'target': False, 'extra': 0, 'waiver': False,
            'source_claim': False, 'field': 'content_payload'}
    run_adapter(1, True, meta, fault=fault, recoveries=2)


def test_original_owner_failure_blob_no_longer_reproduces():
    decoded = []
    @reproduce_failure('6.168.5', b'AEEAQQBBAAEB')
    @bounded_settings('owner')
    @given(storage=st.sampled_from(('exact', 'date', 'timestamp', 'collision')),
           fault=result_fault(), duplicate=st.booleans())
    def replay(storage, fault, duplicate):
        decoded.append((storage, fault, duplicate))
        check_saved_result(storage, fault, duplicate, deterministic=True)
    with pytest.raises(DidNotReproduce):
        replay()
    assert decoded == [('exact', {'path': 'none', 'identity': 'none', 'digest': True}, True)]


def test_original_real_target_failure_blob_no_longer_reproduces():
    decoded = []
    @reproduce_failure('6.168.5', b'AEEGQQE=')
    @bounded_settings('adapter')
    @given(kind=st.sampled_from(('none', 'physical_name', 'physical_extension',
                                'physical_collision_sibling', 'returned_name',
                                'returned_extension', 'returned_target', 'output_digest')),
           recoveries=st.integers(1, 2))
    def replay(kind, recoveries):
        decoded.append((kind, recoveries))
        fault = {'path': 'none', 'identity': 'target', 'digest': False,
                 'original_replay': 'AEEGQQE='}
        meta = {'wrapper': 'json', 'name': 'takeover', 'extension': 'md',
                'mime': 'text/markdown', 'target': False, 'extra': 0, 'waiver': True,
                'source_claim': True, 'field': 'content_payload'}
        run_adapter(1, True, meta, fault=fault, recoveries=recoveries)
    with pytest.raises(DidNotReproduce):
        replay()
    assert decoded == [('returned_target', 1)]
