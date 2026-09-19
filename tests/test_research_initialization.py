"""Fresh Research startup and observation, with all state in temporary roots."""
import json

import pytest

from fruth_research import initialize, status
from fruth_services.research_candidates import set_review, sync_candidates


def contents(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob('*') if p.is_file()}


def test_observation_does_not_initialize_missing_stores(tmp_path):
    before = contents(tmp_path)
    result = status(tmp_path)
    assert result['status'] == 'empty'
    assert result['initialized'] is False
    assert result['runtime_effect'] == 'none'
    assert contents(tmp_path) == before


def test_startup_creates_empty_stores_and_is_idempotent(tmp_path):
    result = initialize(tmp_path)
    assert result['initialized'] is True
    assert result['status'] == 'empty'
    assert [result[key] for key in ('candidate_count', 'gold_case_count', 'retained_evidence_count')] == [0, 0, 0]
    assert result['gold_validation'] == 'not_run_empty'
    assert result['authority'] == 'research_curation_only'
    assert not (tmp_path / 'state').exists()
    assert not (tmp_path / 'fruth_research/retained-evidence').exists()
    before = contents(tmp_path)
    assert initialize(tmp_path) == result
    assert contents(tmp_path) == before


def test_startup_preserves_existing_candidates_reviews_and_gold(tmp_path):
    initialize(tmp_path)
    source = tmp_path / 'state/self_learning/eval_cases.jsonl'
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps({'case_id': 'synthetic', 'prompt': 'test-only candidate'}) + '\n')
    queue = tmp_path / 'fruth_research/candidates'
    sync_candidates(source, queue, root=tmp_path)
    set_review(queue, 'synthetic', disposition='deferred', notes='Keep this explicit review.')
    case = tmp_path / 'fruth_research/gold-core/cases/synthetic.json'
    case.write_text('{"case_id":"synthetic","requires_explicit_curation":true}\n')
    before = contents(tmp_path)
    result = initialize(tmp_path)
    assert result['candidate_count'] == 1
    assert result['gold_case_count'] == 1
    assert result['gold_validation'] == 'requires_explicit_validation'
    assert contents(tmp_path) == before


def test_missing_populated_queue_is_not_replaced_with_empty(tmp_path):
    initialize(tmp_path)
    queue = tmp_path / 'fruth_research/candidates'
    manifest = queue / 'manifest.json'
    data = json.loads(manifest.read_text())
    data['candidate_count'] = 1
    manifest.write_text(json.dumps(data))
    (queue / 'candidates.jsonl').unlink()
    before = contents(tmp_path)
    with pytest.raises(ValueError, match='restore the queue'):
        initialize(tmp_path)
    assert contents(tmp_path) == before


def test_unmanifested_gold_is_not_implicitly_adjudicated(tmp_path):
    cases = tmp_path / 'fruth_research/gold-core/cases'
    cases.mkdir(parents=True)
    (cases / 'unreviewed.json').write_text('{}')
    with pytest.raises(ValueError, match='explicit curated manifest'):
        initialize(tmp_path)
    assert not (cases.parent / 'manifest.json').exists()
    assert (cases / 'unreviewed.json').read_text() == '{}'


def test_http_observation_is_passive(tmp_path, monkeypatch):
    import fruth_webserver
    monkeypatch.setattr(fruth_webserver, '__file__', str(tmp_path / 'fruth_webserver.py'))
    before = contents(tmp_path)
    with fruth_webserver.app.test_client() as client:
        response = client.get('/api/research')
    assert response.status_code == 200
    assert response.get_json()['initialized'] is False
    assert contents(tmp_path) == before
