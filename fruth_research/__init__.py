"""Fresh Research stores and passive observations; no runtime authority."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from fruth_services.research_candidates import atomic_write, no_symlinks, publish, queue_lock, read_queue

ROOT = Path(__file__).resolve().parent.parent


def status(root: Path = ROOT) -> dict:
    directory = Path(root) / 'fruth_research'
    rows = read_queue(directory / 'candidates')
    cases = list((directory / 'gold-core/cases').glob('*.json'))
    retained = directory / 'retained-evidence/gold-core-v0/manifest.json'
    evidence_count = json.loads(retained.read_text())['dependency_count'] if retained.exists() else 0
    return {'kind': 'fruth.research_status', 'root': str(directory.resolve()),
            'candidate_count': len(rows), 'gold_case_count': len(cases),
            'retained_evidence_count': evidence_count,
            'status': 'empty' if not rows and not cases and not evidence_count else 'populated',
            'initialized': (directory / 'gold-core/manifest.json').is_file()
                           and (directory / 'candidates/manifest.json').is_file(),
            'authority': 'research_curation_only', 'runtime_effect': 'none',
            'gold_validation': 'not_run_empty' if not cases else 'requires_explicit_validation'}


def initialize(root: Path = ROOT) -> dict:
    """Create missing empty stores; preserve all existing queues, reviews and Gold."""
    directory = Path(root).absolute() / 'fruth_research'
    no_symlinks(directory)
    corpus = directory / 'gold-core'
    (corpus / 'cases').mkdir(parents=True, exist_ok=True)
    schema = corpus / 'schema.json'
    if not schema.exists():
        atomic_write(schema, (Path(__file__).parent / 'gold-core/schema.json').read_bytes())
    manifest = corpus / 'manifest.json'
    if not manifest.exists():
        if any((corpus / 'cases').glob('*.json')):
            raise ValueError('Existing Gold cases need an explicit curated manifest; initialization cannot adjudicate them.')
        spec = importlib.util.spec_from_file_location('fruth_gold_validator', Path(__file__).parent / 'gold-core/validate.py')
        validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(validator)
        empty = {'schema_version': '1.0.0', 'corpus_version': 'v0',
                 'case_count': 0, 'case_ids': [], **validator.counts([])}
        atomic_write(manifest, json.dumps(empty, indent=2).encode() + b'\n')
    candidates = directory / 'candidates'
    if not (candidates / 'manifest.json').exists() or not (candidates / 'candidates.jsonl').exists():
        with queue_lock(candidates):
            # Startup creates missing stores, without refreshing provenance or
            # rewriting an initialized queue on every launch.
            if not (candidates / 'manifest.json').exists() or not (candidates / 'candidates.jsonl').exists():
                candidate_manifest = candidates / 'manifest.json'
                if candidate_manifest.exists() and not (candidates / 'candidates.jsonl').exists():
                    previous = json.loads(candidate_manifest.read_text())
                    if previous.get('candidate_count') != 0:
                        raise ValueError('Existing Research candidates are missing; restore the queue before startup.')
                publish(candidates, read_queue(candidates), 'initialization')
    # Retained evidence is created only by explicit selection/retention. An absent
    # store is already the resolver's supported empty representation.
    return status(root)
