"""Pure trace generation and a separate, fail-closed execution coordinator.

This module intentionally imports no Fruth owner or fixture. Hypothesis finishes
all draws before a trace reaches the collector; execution state is never an input
to generation. A sealed corpus can be replayed without invoking Hypothesis.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import time

from hypothesis import Phase, given, seed, settings, strategies as st


FAILURE_SEAMS = ('prepare', 'partial', 'flush', 'fsync', 'index_transaction', 'index_selector')
PUBLIC_VIEWS = ('default', 'ui', 'status', 'debug', 'truth', 'full')
COLD_READERS = ('cold_selected', 'cold_old_index', 'cold_missing_selector', 'cold_missing_db')
MAX_SCENARIOS = 32
MAX_TRANSITIONS = 32
CAMPAIGN_SECONDS = 600


@dataclass(frozen=True)
class Operation:
    kind: str
    value: str


@dataclass(frozen=True)
class Trace:
    seam: str
    reverse: bool
    operations: tuple[Operation, ...]


@dataclass(frozen=True)
class Entry:
    identity: str
    origin: str
    trace: Trace


@dataclass(frozen=True)
class Corpus:
    seed: int
    generated_examples: int
    entries: tuple[Entry, ...]


@dataclass(frozen=True)
class SealedCorpus:
    content: str
    sha256: str


class ExecutionBudgetError(RuntimeError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def trace_document(trace):
    return asdict(trace)


def planned_transitions(trace):
    """10 preparation/worker transitions, 6 public probes, retry, optional tail.

    Each additional read costs one; first access to each copied cold root costs
    one more. This preflight is separate from actual runtime transition counting.
    """
    copies = {op.value for op in trace.operations
              if op.kind == 'cold' and op.value != 'cold_selected'}
    return 17 + int(trace.seam == 'partial') + len(trace.operations) + len(copies)


def validate_trace(trace):
    if not isinstance(trace, Trace) or trace.seam not in FAILURE_SEAMS or type(trace.reverse) is not bool:
        raise ValueError('invalid trace identity')
    if not isinstance(trace.operations, tuple) or not 1 <= len(trace.operations) <= 8:
        raise ValueError('trace requires 1..8 complete operations')
    for op in trace.operations:
        if not isinstance(op, Operation) or not (
            op.kind == 'public' and op.value in PUBLIC_VIEWS or
            op.kind == 'cold' and op.value in COLD_READERS
        ):
            raise ValueError('unsupported operation')
    if planned_transitions(trace) > MAX_TRANSITIONS:
        raise ExecutionBudgetError('planned transition cap exceeded')


def trace_strategy():
    operations = st.one_of(st.builds(Operation, st.just('public'), st.sampled_from(PUBLIC_VIEWS)),
                           st.builds(Operation, st.just('cold'), st.sampled_from(COLD_READERS)))
    return st.builds(Trace, st.sampled_from(FAILURE_SEAMS), st.booleans(),
                     st.lists(operations, min_size=1, max_size=8).map(tuple))


def collect_traces(*, seed_value, examples, strategy=None, validator=validate_trace):
    """Collect complete valid bodies only; collection never drives later draws.

    Rejected/overrun draws occur before this body and cannot start a scenario.
    No database, shrinking, execution counter or exception latch is involved.
    A generation error propagates; it is never suppressed or labeled a pass.
    """
    if type(examples) is not int or not 1 <= examples <= MAX_SCENARIOS:
        raise ValueError('invalid pure-generation example budget')
    collected = []

    @seed(seed_value)
    @settings(max_examples=examples, database=None, phases=(Phase.generate,), deadline=None,
              report_multiple_bugs=False)
    @given(trace=trace_strategy() if strategy is None else strategy)
    def collect(trace):
        validator(trace)
        collected.append(trace)

    collect()
    return tuple(collected)


def make_corpus(seed_value=20261015):
    generated = collect_traces(seed_value=seed_value, examples=26)
    if len(generated) != 26:
        raise ValueError('generation did not supply the declared 26 complete examples')
    # Explicit seeded coverage is labeled separately, never attributed to draws.
    seed_ops = tuple(Operation('cold', reader) for reader in COLD_READERS) * 2
    seeded = tuple(Trace(seam, bool(i % 2), seed_ops) for i, seam in enumerate(FAILURE_SEAMS))
    entries = tuple(Entry(f'seed-{i:02}', 'seeded', trace) for i, trace in enumerate(seeded))
    entries += tuple(Entry(f'generated-{i:02}', 'generated', trace) for i, trace in enumerate(generated))
    return Corpus(seed_value, len(generated), entries)


def seal(corpus, *, validator=None):
    validate_corpus(corpus, validator=validator)
    content = canonical(asdict(corpus))
    return SealedCorpus(content, hashlib.sha256(content.encode()).hexdigest())


def unseal(sealed, *, validator=None):
    if hashlib.sha256(sealed.content.encode()).hexdigest() != sealed.sha256:
        raise ValueError('corpus digest mismatch')
    value = json.loads(sealed.content)
    entries = []
    for item in value['entries']:
        trace = item['trace']
        entries.append(Entry(item['identity'], item['origin'], Trace(trace['seam'], trace['reverse'],
            tuple(Operation(**op) for op in trace['operations']))))
    corpus = Corpus(value['seed'], value['generated_examples'], tuple(entries))
    # Canonical roundtrip also rejects added or ignored fields.
    if canonical(asdict(corpus)) != sealed.content:
        raise ValueError('noncanonical or unsupported corpus schema')
    validate_corpus(corpus, validator=validator)
    return corpus


def validate_corpus(corpus, *, validator=None):
    if not isinstance(corpus, Corpus) or not isinstance(corpus.entries, tuple):
        raise ValueError('corpus must be immutable')
    if not 1 <= len(corpus.entries) <= MAX_SCENARIOS:
        raise ExecutionBudgetError('corpus scenario cap exceeded')
    if len({entry.identity for entry in corpus.entries}) != len(corpus.entries):
        raise ValueError('duplicate corpus identity')
    if corpus.generated_examples != sum(entry.origin == 'generated' for entry in corpus.entries):
        raise ValueError('generated-example accounting mismatch')
    for entry in corpus.entries:
        if entry.origin not in {'generated', 'seeded'} or not entry.identity:
            raise ValueError('invalid corpus provenance')
        (validator or validate_trace)(entry.trace)


class ExecutionCoordinator:
    """Execution-only state. No call from a Hypothesis body or strategy."""
    def __init__(self, *, limit=MAX_SCENARIOS, seconds=CAMPAIGN_SECONDS, clock=time.monotonic):
        if type(limit) is not int or not 1 <= limit <= MAX_SCENARIOS:
            raise ValueError('scenario limit cannot exceed 32')
        if not 0 < seconds <= CAMPAIGN_SECONDS:
            raise ValueError('campaign deadline cannot exceed 600 seconds')
        self.limit, self.clock = limit, clock
        self.deadline = clock() + seconds
        self.started = 0
        self.completed = 0
        self.halted = False
        self.used = False

    def execute(self, sealed, run, emit=lambda event: None, *, validator=None,
                transition_counter=planned_transitions):
        if self.used or self.halted:
            raise ExecutionBudgetError('coordinator already consumed or halted')
        corpus = unseal(sealed, validator=validator)
        if len(corpus.entries) > self.limit:
            raise ExecutionBudgetError('corpus exceeds remaining execution allowance')
        self.used = True
        results = []
        for entry in corpus.entries:
            if self.started >= self.limit or self.clock() >= self.deadline:
                self.halted = True
                raise ExecutionBudgetError('execution allowance or deadline exhausted')
            self.started += 1  # Reserve before any runtime construction or side effect.
            emit({'event': 'scenario_start', 'entry': asdict(entry), 'ordinal': self.started,
                  'corpus_sha256': sealed.sha256})
            try:
                transitions = run(entry)
                if type(transitions) is not int or not 0 < transitions <= MAX_TRANSITIONS:
                    raise ExecutionBudgetError('actual transition cap exceeded')
                if transitions != transition_counter(entry.trace):
                    raise ExecutionBudgetError('actual/planned transition accounting mismatch')
                if self.clock() >= self.deadline:
                    raise ExecutionBudgetError('scenario returned after campaign deadline')
            except BaseException as exc:
                self.halted = True
                emit({'event': 'scenario_failed', 'identity': entry.identity,
                      'error_type': type(exc).__name__, 'error': str(exc)})
                raise
            self.completed += 1
            result = {'identity': entry.identity, 'origin': entry.origin, 'transitions': transitions}
            results.append(result)
            emit({'event': 'scenario_completed', **result})
        return tuple(results)
