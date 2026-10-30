"""Small public projections of saved reference evidence; no runtime execution.

These are exporter consistency checks, not a replacement for runtime admission
or a proof that a model's review is correct. Unknown/private fields are omitted.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import re
from typing import Any, Callable, Mapping


SCHEMA = 'fruth.public_reference_evidence.v1'
BINDING_KEYS = (
    'kind', 'policy', 'content_requirement_policy', 'evidence_reference_policy',
    'logical_review_id', 'generation_id', 'sha256', 'instruction_sha256',
    'source_branch_id', 'source_phase_id', 'branch_id', 'phase_id',
    'task_id', 'obligation_id',
)
ARTIFACT_KEYS = ('artifact_ref', 'published_path', 'sha256', 'size_bytes', 'branch_id', 'phase_id')


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError('Reference evidence: ' + message)


def _text(value: Any) -> str:
    _require(isinstance(value, str) and bool(value), 'missing or malformed text field')
    return value


def _digest(value: Any) -> str:
    _require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None,
             'missing or malformed digest')
    return value


def _strings(source: Mapping, keys: tuple[str, ...]) -> dict:
    return {key: _text(source[key]) for key in keys if key in source}


def _identity(record: Mapping, branch: str, phase: str) -> None:
    _require(record.get('branch_id') == branch and record.get('phase_id') == phase,
             'branch/phase identity conflict')


def _unique(records: list, key: str) -> dict:
    result = {}
    for record in records:
        _require(isinstance(record, Mapping), 'malformed record')
        identity = _text(record.get(key))
        _require(identity not in result, 'duplicate ' + key)
        result[identity] = record
    return result


def project_evidence(
    results: list, checks: list, *, response_id: str, artifacts: list,
    outputs: list, read_public: Callable[[str], bytes],
) -> dict:
    """Project three supported evidence families from one exact saved frame."""
    result_by_branch = _unique(results, 'branch_id')
    # Closure contains separate obligations for the same branch. Only the
    # selected named-content review records participate in this projection.
    check_by_branch = _unique([c for c in checks if isinstance(c, Mapping)
                               and c.get('branch_semantic_review_evidence_binding')], 'branch_id')
    artifact_by_ref = _unique(artifacts, 'artifact_ref')

    def artifact(ref: str) -> dict:
        _require(ref in artifact_by_ref, 'artifact is not in this response export')
        a = artifact_by_ref[ref]
        data = read_public(_text(a.get('published_path')))
        _require(type(a.get('size_bytes')) is int and len(data) == a['size_bytes']
                 and hashlib.sha256(data).hexdigest() == _digest(a.get('sha256')),
                 'artifact bytes/digest conflict')
        return {key: a[key] for key in ARTIFACT_KEYS}

    def snapshot(source: Mapping) -> dict:
        _require(isinstance(source, Mapping), 'missing saved-file snapshot')
        a = artifact(_text(source.get('artifact_ref')))
        _identity(source, a['branch_id'], a['phase_id'])
        _require(source.get('sha256') == a['sha256'] and source.get('size_bytes') == a['size_bytes'],
                 'saved snapshot version conflict')
        for key in ('response_id', 'source_response_id'):
            _require(key not in source or source[key] == response_id, 'foreign response identity')
        if source.get('artifact_id'):
            _require('artifact:' + source['artifact_id'] == a['artifact_ref'], 'artifact identity conflict')
        return a

    reviews, reads, reports = [], [], []
    for result in results:
        branch, phase = _text(result.get('branch_id')), _text(result.get('phase_id'))
        _require('source_response_id' not in result or result['source_response_id'] == response_id,
                 'foreign result response identity')
        binding = result.get('semantic_review_evidence_binding')
        if binding is not None:
            _require(isinstance(binding, Mapping), 'malformed review binding')
            source_branch = _text(binding.get('source_branch_id'))
            source_phase = _text(binding.get('source_phase_id'))
            # The saved execution phase may use the branch ID; the logical
            # review phase remains in the binding. Do not conflate the two.
            _require(binding.get('branch_id') == branch, 'review result branch conflict')
            check = check_by_branch.get(source_branch, {})
            _require(check.get('branch_semantic_review_evidence_binding') == binding,
                     'review generation differs between result and Closure')
            _identity(check, source_branch, source_phase)
            source = result_by_branch.get(source_branch, {})
            _identity(source, source_branch, source_phase)
            saved = snapshot(source.get('saved_file_output_snapshot'))
            public_binding = _strings(binding, BINDING_KEYS)
            _digest(public_binding.get('sha256'))
            _digest(public_binding.get('instruction_sha256'))
            acceptance = check.get('semantic_review_freeze_acceptance')
            _require(isinstance(acceptance, Mapping) and type(acceptance.get('accepted')) is bool,
                     'missing recorded review acceptance')
            criteria = acceptance.get('required_criteria')
            _require(isinstance(criteria, list) and all(isinstance(x, str) for x in criteria),
                     'malformed review criteria')
            reviews.append({
                'binding': public_binding, 'source_artifact': saved,
                'recorded_result_phase_id': phase,
                'recorded_acceptance': {
                    **_strings(acceptance, ('kind', 'status', 'evidence_reference_policy')),
                    'accepted': acceptance['accepted'], 'required_criteria': list(criteria),
                },
                **_strings(check, ('completion_basis', 'content_coverage_status')),
                'result_and_closure_binding_equal': True,
            })

        consumption = result.get('saved_file_consumption_evidence')
        if consumption is not None:
            _require(isinstance(consumption, Mapping), 'malformed saved read evidence')
            contract, read, out = (consumption.get(k) for k in ('contract', 'read', 'output'))
            _require(all(isinstance(x, Mapping) for x in (contract, read, out)), 'incomplete saved read evidence')
            producer, producer_phase = _text(contract.get('producer_branch_id')), _text(contract.get('producer_phase_id'))
            for record in (contract, read):
                _require(record.get('consumer_branch_id') == branch and record.get('consumer_phase_id') == phase
                         and record.get('producer_branch_id') == producer and record.get('producer_phase_id') == producer_phase,
                         'saved read dependency identity conflict')
            source_artifact = snapshot(read)
            _identity(source_artifact, producer, producer_phase)
            producer_result = result_by_branch.get(producer, {})
            _require(snapshot(producer_result.get('saved_file_output_snapshot')) == source_artifact,
                     'saved read differs from producer result')
            _require(read.get('path') == producer_result['saved_file_output_snapshot'].get('path'),
                     'saved read path identity conflict')
            output_artifact = snapshot(result.get('saved_file_output_snapshot'))
            _identity(output_artifact, branch, phase)
            _require(out.get('sha256') == output_artifact['sha256'] and out.get('size_bytes') == output_artifact['size_bytes'],
                     'consumer output version conflict')
            _require(out.get('path') == result['saved_file_output_snapshot'].get('path'),
                     'consumer output path identity conflict')
            try:
                decoded = base64.b64decode(_text(read.get('utf8_base64')), validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ValueError('Reference evidence: malformed saved read bytes') from exc
            _require(decoded == read_public(source_artifact['published_path']), 'saved read bytes differ from published source')
            reads.append({
                'recorded_status': _text(consumption.get('status')),
                'producer': source_artifact, 'consumer': output_artifact,
                'encoding': _text(read.get('encoding')),
                'recorded_consumer_input_sha256': _digest(consumption.get('input_sha256')),
                'consumer_input_digest_recomputed': False,
                'decoded_read_equals_published_source': True,
            })

        delivery = result.get('report_delivery_evidence')
        if delivery is not None:
            _require(isinstance(delivery, Mapping) and delivery.get('kind') == 'fruth.separate_image_report_delivery',
                     'unsupported report delivery evidence')
            _identity(delivery, branch, phase)
            _require(delivery.get('response_id') == response_id, 'foreign report delivery')
            published = [o for o in outputs if o.get('branch_id') == branch and o.get('phase_id') == phase and 'text' in o]
            _require(len(published) == 1 and published[0]['text'] == result.get('result_text'),
                     'combined report differs from published output')
            contributions = delivery.get('contributions')
            _require(isinstance(contributions, list), 'missing image contributions')
            _unique(contributions, 'source_branch_id')
            for contribution in contributions:
                a = artifact(_text(contribution.get('artifact_ref')))
                _identity(a, contribution.get('producer_branch_id'), contribution.get('producer_phase_id'))
                _require(contribution.get('image_sha256') == a['sha256'], 'report image version conflict')
                source_branch = _text(contribution.get('source_branch_id'))
                source_phase = _text(contribution.get('source_phase_id'))
                vision = result_by_branch.get(source_branch, {})
                _identity(vision, source_branch, source_phase)
                supplied = vision.get('vision_input_evidence') or {}
                _identity(supplied, source_branch, source_phase)
                _require(supplied.get('response_id') == response_id and supplied.get('image_sha256') == a['sha256']
                         and supplied.get('size_bytes') == a['size_bytes'], 'vision dispatch version conflict')
                report_text = _text(contribution.get('report_text'))
                report_sha = _digest(contribution.get('report_sha256'))
                _require(hashlib.sha256(report_text.encode('utf-8')).hexdigest() == report_sha
                         and vision.get('result_text') == report_text
                         and published[0]['text'].count(report_text) == 1, 'image report text binding conflict')
                reports.append({
                    'image': a, 'source_branch_id': source_branch, 'source_phase_id': source_phase,
                    'delivery_branch_id': branch, 'delivery_phase_id': phase,
                    'output_slot_id': _text(published[0].get('slot_id')),
                    'recorded_dispatch_status': _text(supplied.get('status')),
                    'report_text': report_text, 'report_sha256': report_sha,
                    'individual_report_equals_published_contribution': True,
                })

    # A Closure-only binding is missing its matching result, not a successful review.
    recorded_reviews = {r['binding']['source_branch_id'] for r in reviews}
    _require(all(c['branch_id'] in recorded_reviews for c in checks if c.get('branch_semantic_review_evidence_binding')),
             'Closure review has no matching saved result')
    families = {'semantic_reviews': reviews, 'saved_file_reads': reads, 'image_reports': reports}
    return {
        'schema': SCHEMA, 'version': 1,
        'scope': 'selected_saved_bindings',
        'availability': {key: 'recorded' if value else 'not_recorded' for key, value in families.items()},
        **families,
        'model_judgments_independently_proven': False,
    }


def verify_projection(projection: Mapping, *, artifacts: list, outputs: list,
                      read_public: Callable[[str], bytes]) -> None:
    """Verify portable byte links; cannot authenticate omitted raw runtime state."""
    _require(isinstance(projection, Mapping) and projection.get('schema') == SCHEMA and projection.get('version') == 1,
             'unsupported public projection')
    _require(projection.get('model_judgments_independently_proven') is False, 'unsupported proof claim')
    artifact_by_ref = _unique(artifacts, 'artifact_ref')

    def linked(a: Mapping) -> None:
        _require(isinstance(a, Mapping), 'malformed artifact link')
        expected = artifact_by_ref.get(a.get('artifact_ref'), {})
        _require(all(key in a and a[key] == expected.get(key) for key in ARTIFACT_KEYS), 'public artifact binding conflict')
        data = read_public(_text(a.get('published_path')))
        _require(hashlib.sha256(data).hexdigest() == _digest(a.get('sha256')) and len(data) == a.get('size_bytes'),
                 'public artifact bytes conflict')

    for key in ('semantic_reviews', 'saved_file_reads', 'image_reports'):
        items = projection.get(key)
        _require(isinstance(items, list), 'missing evidence family')
        _require(projection.get('availability', {}).get(key) == ('recorded' if items else 'not_recorded'),
                 'evidence availability mismatch')
        for item in items:
            if key == 'semantic_reviews':
                linked(item['source_artifact'])
                binding = item['binding']
                _identity(item['source_artifact'], binding.get('source_branch_id'), binding.get('source_phase_id'))
                _digest(binding.get('sha256'))
                _digest(binding.get('instruction_sha256'))
            elif key == 'saved_file_reads':
                linked(item['producer'])
                linked(item['consumer'])
                _digest(item.get('recorded_consumer_input_sha256'))
                _require(item.get('consumer_input_digest_recomputed') is False, 'unsupported input digest claim')
            else:
                linked(item['image'])
                text = _text(item.get('report_text'))
                _require(hashlib.sha256(text.encode('utf-8')).hexdigest() == _digest(item.get('report_sha256')),
                         'public report digest conflict')
                matches = [o for o in outputs if o.get('slot_id') == item.get('output_slot_id')
                           and o.get('branch_id') == item.get('delivery_branch_id')
                           and o.get('phase_id') == item.get('delivery_phase_id')]
                _require(len(matches) == 1 and matches[0].get('text', '').count(text) == 1,
                         'public report is not present exactly once in its output')
