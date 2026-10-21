"""Cheap generation/coordinator tests: no Fruth imports, storage or fixtures."""
from dataclasses import FrozenInstanceError, replace
import sys

import pytest
from hypothesis import Phase, assume, given, seed, settings, strategies as st

from tests.persistence_trace_adapter import (
    COLD_READERS, FAILURE_SEAMS, Corpus, Entry, ExecutionBudgetError, ExecutionCoordinator,
    Operation, SealedCorpus, Trace, collect_traces, make_corpus, planned_transitions, seal,
    trace_strategy, unseal,
)


def one_trace():
    return Trace('fsync', False, (Operation('cold', 'cold_selected'),))


def corpus_of(count):
    return Corpus(1, count, tuple(Entry(str(i), 'generated', one_trace()) for i in range(count)))


@pytest.fixture(autouse=True)
def no_fruth_fixture_imports():
    assert 'fruth_webserver' not in sys.modules
    assert 'tests.test_persistence_recovery_study' not in sys.modules
    yield
    assert 'fruth_webserver' not in sys.modules
    assert 'tests.test_persistence_recovery_study' not in sys.modules


def test_repeated_complete_generation_is_byte_reproducible():
    first = seal(make_corpus())
    second = seal(make_corpus())
    assert first == second
    corpus = unseal(first)
    assert corpus.generated_examples == 26 and len(corpus.entries) == 32
    assert [e.trace.seam for e in corpus.entries[:6]] == list(FAILURE_SEAMS)
    assert all(e.origin == 'seeded' for e in corpus.entries[:6])
    assert all(e.origin == 'generated' for e in corpus.entries[6:])
    assert all(planned_transitions(e.trace) <= 32 for e in corpus.entries)


def test_rejected_draws_never_enter_execution_and_replay_identically():
    draws = []
    @st.composite
    def rejected(draw):
        token = draw(st.integers(min_value=0, max_value=100))
        draws.append(token)  # observation only, never consulted by the strategy
        assume(token % 3 == 0)
        return draw(trace_strategy())
    first = collect_traces(seed_value=7301, examples=12, strategy=rejected())
    first_draws = tuple(draws)
    assert len(first) == 12 and any(token % 3 for token in draws)
    draws.clear()
    second = collect_traces(seed_value=7301, examples=12, strategy=rejected())
    assert first == second and tuple(draws) == first_draws
    assert len(draws) > len(first)


def test_hypothesis_failure_confirmation_has_no_cross_example_latch():
    calls = []
    class ConstantFailure(Exception): pass
    @seed(72)
    @settings(max_examples=3, database=None, phases=(Phase.generate,), deadline=None)
    @given(trace=st.just(one_trace()))
    def fail_identically(trace):
        calls.append(trace)
        raise ConstantFailure('same complete trace, same failure')
    with pytest.raises(ConstantFailure, match='same complete trace'):
        fail_identically()
    assert len(calls) >= 2
    assert all(trace == one_trace() for trace in calls)


def test_coordinator_failure_does_not_change_later_generation():
    before = collect_traces(seed_value=22, examples=8)
    coordinator = ExecutionCoordinator()
    with pytest.raises(RuntimeError, match='callback failure'):
        coordinator.execute(seal(corpus_of(1)), lambda entry: (_ for _ in ()).throw(RuntimeError('callback failure')))
    assert coordinator.started == 1 and coordinator.completed == 0 and coordinator.halted
    assert collect_traces(seed_value=22, examples=8) == before


def test_immutable_trace_corpus_and_digest_tampering():
    trace = one_trace()
    with pytest.raises(FrozenInstanceError): trace.seam = 'partial'
    with pytest.raises(TypeError): trace.operations[0] = Operation('public', 'ui')
    sealed = seal(corpus_of(1))
    with pytest.raises(ValueError, match='digest mismatch'):
        unseal(SealedCorpus(sealed.content + ' ', sealed.sha256))
    assert unseal(sealed) == corpus_of(1)


def test_invalid_corpus_rejected_before_any_callback():
    called = []
    with pytest.raises(ExecutionBudgetError): seal(corpus_of(33))
    with pytest.raises(ValueError, match='unsupported operation'):
        seal(Corpus(1, 1, (Entry('x', 'generated', replace(one_trace(),
            operations=(Operation('repair_storage', 'yes'),))),)))
    coordinator = ExecutionCoordinator(limit=1)
    with pytest.raises(ExecutionBudgetError, match='remaining execution allowance'):
        coordinator.execute(seal(corpus_of(2)), lambda entry: called.append(entry))
    assert coordinator.started == 0 and not called


def test_duplicates_are_executed_and_never_silently_skipped():
    called = []
    coordinator = ExecutionCoordinator()
    results = coordinator.execute(seal(corpus_of(32)),
        lambda entry: (called.append(entry), planned_transitions(entry.trace))[1])
    assert len(called) == len(results) == coordinator.started == coordinator.completed == 32
    with pytest.raises(ExecutionBudgetError, match='already consumed'):
        coordinator.execute(seal(corpus_of(1)), lambda entry: called.append(entry))
    assert len(called) == 32


def test_same_corpus_replays_with_a_fresh_explicit_coordinator():
    sealed = seal(corpus_of(3))
    first = ExecutionCoordinator().execute(sealed, lambda entry: planned_transitions(entry.trace))
    second = ExecutionCoordinator().execute(sealed, lambda entry: planned_transitions(entry.trace))
    assert first == second


def test_first_failure_halts_without_calling_later_entries():
    calls, events = [], []
    def run(entry):
        calls.append(entry.identity)
        if entry.identity == '1': raise AssertionError('sentinel counterexample')
        return planned_transitions(entry.trace)
    coordinator = ExecutionCoordinator()
    with pytest.raises(AssertionError, match='sentinel counterexample'):
        coordinator.execute(seal(corpus_of(4)), run, events.append)
    assert calls == ['0', '1'] and coordinator.started == 2 and coordinator.completed == 1
    assert coordinator.halted and events[-1]['event'] == 'scenario_failed'
    with pytest.raises(ExecutionBudgetError): coordinator.execute(seal(corpus_of(1)), run)
    assert calls == ['0', '1']


@pytest.mark.parametrize('transitions', [0, 33, 17])
def test_actual_transition_limit_and_accounting_are_enforced(transitions):
    with pytest.raises(ExecutionBudgetError):
        ExecutionCoordinator().execute(seal(corpus_of(1)), lambda entry: transitions)


def test_expired_deadline_prevents_construction_and_postreturn_is_checked():
    now = [0]
    called = []
    coordinator = ExecutionCoordinator(seconds=1, clock=lambda: now[0])
    now[0] = 1
    with pytest.raises(ExecutionBudgetError, match='deadline exhausted'):
        coordinator.execute(seal(corpus_of(1)), lambda entry: called.append(entry))
    assert not called and coordinator.started == 0
    now[0] = 0
    coordinator = ExecutionCoordinator(seconds=1, clock=lambda: now[0])
    def late(entry):
        now[0] = 2
        return planned_transitions(entry.trace)
    with pytest.raises(ExecutionBudgetError, match='after campaign deadline'):
        coordinator.execute(seal(corpus_of(1)), late)
    assert coordinator.started == 1 and coordinator.completed == 0


@pytest.mark.parametrize('kwargs', [{'limit': 33}, {'seconds': 601}])
def test_named_limits_cannot_be_increased(kwargs):
    with pytest.raises(ValueError): ExecutionCoordinator(**kwargs)
