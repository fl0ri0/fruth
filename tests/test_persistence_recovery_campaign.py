"""Execute one immutable corpus outside Hypothesis's draw/replay machinery."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import time

from tests.persistence_trace_adapter import (
    ExecutionCoordinator, PUBLIC_VIEWS, make_corpus, planned_transitions, seal,
)


def execute_trace(entry):
    # Import/construction follows complete generation, corpus sealing and slot
    # reservation. The semantic fixture and all its assertions remain unchanged.
    from tests.test_persistence_recovery_study import PersistenceStudy
    trace = entry.trace
    study = PersistenceStudy(trace.seam, trace.reverse)
    study.source_inputs.update(corpus_identity=entry.identity, corpus_origin=entry.origin,
                               immutable_trace=asdict(trace), planned_transitions=planned_transitions(trace))
    try:
        study.prepare()
        for view in PUBLIC_VIEWS:
            study.observe(view)
        study.retry_and_tail()
        for operation in trace.operations:
            if operation.kind == 'public':
                study.observe(operation.value)
            else:
                study.observe('truth', operation.value)
        return study.transition_count
    except BaseException as exc:
        study.failed = True
        study.problem = repr(exc)
        raise
    finally:
        study.close()


def test_one_bounded_immutable_corpus():
    generated_started = time.monotonic()
    corpus = make_corpus()
    sealed = seal(corpus)
    generation_seconds = time.monotonic() - generated_started
    evidence = Path(os.environ['FRUTH_HYPOTHESIS_EVIDENCE_DIR'])
    # Exclusive creation prevents a rerun from overwriting or reusing evidence.
    with (evidence / 'corpus.json').open('x') as stream:
        json.dump(asdict(sealed), stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    coordinator = ExecutionCoordinator()
    record = {'corpus_sha256': sealed.sha256, 'generation_completed_before_execution': True,
        'generation_seconds': generation_seconds, 'hypothesis_examples': corpus.generated_examples,
        'hypothesis_seed': corpus.seed, 'corpus_entries': len(corpus.entries),
        'seeded_entries': sum(e.origin == 'seeded' for e in corpus.entries),
        'generated_entries': sum(e.origin == 'generated' for e in corpus.entries),
        'scenario_limit': 32, 'transition_limit': 32, 'external_deadline_seconds': 600,
        'classification': 'running'}
    started = time.monotonic()
    try:
        with (evidence / 'execution-journal.jsonl').open('x') as journal:
            def emit(event):
                journal.write(json.dumps(event, sort_keys=True) + '\n')
                journal.flush()
                os.fsync(journal.fileno())
            record['results'] = coordinator.execute(sealed, execute_trace, emit)
        record['classification'] = 'passed'
    except BaseException as exc:
        record.update(classification='failed_requires_classification', error=repr(exc))
        raise
    finally:
        record.update(started=coordinator.started, completed=coordinator.completed,
                      halted=coordinator.halted, execution_seconds=time.monotonic() - started)
        with (evidence / 'coordinator.json').open('x') as stream:
            json.dump(record, stream, indent=2)
            stream.write('\n')
