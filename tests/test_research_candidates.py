"""All learning and Research writes use synthetic temporary roots."""
import json
from pathlib import Path
import pytest
from ollmo_services import research_candidates as research
from ollmo_services.self_learning import persist_eval_cases, persist_self_learning_outputs


def paths(root):
    return root / 'state/self_learning/eval_cases.jsonl', root / 'ollmo_research/candidates'


def generation(path, cases):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b''.join(research.encoded(c) + b'\n' for c in cases))


def case(sid, prompt='same request'):
    return {'case_id': sid, 'prompt': prompt, 'response_id': 'response-' + sid,
            'frame_status': 'fulfilled', 'case_kind': 'historical_only'}


def indexed(queue):
    return {r['source_case_id']: r for r in research.read_queue(queue).values()}


def test_cross_generation_keeps_reviews_and_gold_exact(tmp_path):
    source, queue = paths(tmp_path)
    gold = tmp_path / 'ollmo_research/gold-core/cases/curated.json'
    gold.parent.mkdir(parents=True)
    gold.write_bytes(b'{"expected_outcome":"curated defect"}')
    generation(source, [case('A'), case('B'), case('C')])
    research.sync_candidates(source, queue, root=tmp_path)
    first = indexed(queue)['A']['first_seen']
    for sid, disposition in [('A', 'promoted'), ('B', 'deferred'), ('C', 'rejected')]:
        research.set_review(queue, sid, disposition=disposition, gold_case_ids=['gc-existing'] if sid == 'A' else [], notes='human adjudication')
    generation(source, [case('A', 'materially changed'), case('B'), case('D')])
    result = research.sync_candidates(source, queue, root=tmp_path)
    rows = indexed(queue)
    assert result['candidate_count'] == 4
    assert result['counts_by_disposition'] == dict(deferred=1, promoted=1, rejected=1, unreviewed=1)
    assert research.digest((queue / 'candidates.jsonl').read_bytes()) == result['candidates_sha256']
    assert rows['A']['first_seen'] == first
    assert rows['A']['last_seen'] != first
    assert rows['A']['review']['gold_case_ids'] == ['gc-existing']
    assert rows['A']['review']['notes'] == 'human adjudication'
    assert rows['A']['review_source_changed'] is True
    assert len(rows['A']['source_versions']) == 2
    assert rows['B']['review']['disposition'] == 'deferred'
    assert rows['C']['review']['disposition'] == 'rejected'
    assert rows['C']['source_present_in_latest_generation'] is False
    assert rows['D']['review']['disposition'] == 'unreviewed'
    assert len(rows) == 4  # matching prompts do not collapse source identities
    research.sync_candidates(source, queue, root=tmp_path)
    assert len(indexed(queue)['A']['source_versions']) == 2
    source.unlink()
    missing = research.refresh_availability(queue, root=tmp_path)
    assert missing['counts_by_provenance_status'] == {'source_missing': 4}
    assert indexed(queue)['A']['review'] == rows['A']['review']
    assert list(gold.parent.iterdir()) == [gold]
    assert gold.read_bytes() == b'{"expected_outcome":"curated defect"}'


def test_successful_persistence_seam_and_secondary_failure(tmp_path, monkeypatch, caplog):
    source, queue = paths(tmp_path)
    report = source.with_name('report.json')
    persist_self_learning_outputs([case('A')], {'ok': True}, eval_case_output_path=source, report_output_path=report)
    assert indexed(queue)['A']['review']['disposition'] == 'unreviewed'
    before = (queue / 'candidates.jsonl').read_bytes()
    def broken(*args, **kwargs):
        raise OSError('injected secondary failure')
    monkeypatch.setattr(research, 'sync_after_learning_persist', broken)
    persist_self_learning_outputs([case('B')], {'updated': True}, eval_case_output_path=source, report_output_path=report)
    assert json.loads(source.read_text())['case_id'] == 'B'
    assert json.loads(report.read_text()) == {'updated': True}
    assert (queue / 'candidates.jsonl').read_bytes() == before
    assert 'Self-learning persisted; research candidate sync failed' in caplog.text


def test_single_persist_and_custom_path_isolation(tmp_path):
    source, queue = paths(tmp_path)
    persist_eval_cases([case('A')], output_path=source)
    assert len(indexed(queue)) == 1
    other = tmp_path / 'custom/outputs.jsonl'
    persist_eval_cases([case('B')], output_path=other)
    assert set(indexed(queue)) == {'A'}


def test_duplicate_source_and_version_limit_preserve_queue(tmp_path, monkeypatch):
    source, queue = paths(tmp_path)
    generation(source, [case('A')])
    research.sync_candidates(source, queue, root=tmp_path)
    before = (queue / 'candidates.jsonl').read_bytes()
    generation(source, [case('A'), case('A')])
    with pytest.raises(ValueError, match='duplicate'):
        research.sync_candidates(source, queue, root=tmp_path)
    monkeypatch.setattr(research, 'MAX_SOURCE_VERSIONS', 1)
    generation(source, [case('A', 'new')])
    with pytest.raises(ValueError, match='version limit'):
        research.sync_candidates(source, queue, root=tmp_path)
    assert (queue / 'candidates.jsonl').read_bytes() == before


def test_manifest_failure_is_repairable_and_source_movement_fails(tmp_path, monkeypatch):
    source, queue = paths(tmp_path)
    generation(source, [case('A')])
    original = research.atomic_write
    def fail_manifest(path, data):
        if path.name == 'manifest.json':
            raise OSError('injected manifest failure')
        original(path, data)
    with monkeypatch.context() as m:
        m.setattr(research, 'atomic_write', fail_manifest)
        with pytest.raises(OSError):
            research.sync_candidates(source, queue, root=tmp_path)
    assert len(indexed(queue)) == 1
    research.sync_candidates(source, queue, root=tmp_path)
    assert json.loads((queue / 'manifest.json').read_text())['candidate_count'] == 1
    with pytest.raises(ValueError, match='source changed'):
        research.sync_candidates(source, queue, root=tmp_path, expected_source_sha256='wrong')


def test_unsafe_destination_and_changed_eval_bytes(tmp_path):
    source, queue = paths(tmp_path)
    generation(source, [case('A')])
    research.sync_candidates(source, queue, root=tmp_path)
    generation(source, [case('A', 'changed bytes')])
    research.refresh_availability(queue, root=tmp_path)
    assert indexed(queue)['A']['provenance']['status'] == 'source_missing'
    linked = tmp_path / 'linked'
    linked.symlink_to(queue, target_is_directory=True)
    with pytest.raises(ValueError, match='symlinks'):
        research.sync_candidates(source, linked, root=tmp_path)
