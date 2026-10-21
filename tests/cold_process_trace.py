"""Cold process profile of the existing pure trace adapter; no runtime imports."""
from hypothesis import strategies as st
from tests.persistence_trace_adapter import (
    Corpus, Entry, Operation, Trace, collect_traces, seal, MAX_TRANSITIONS,
)

SEAMS = ('success', 'reported_prepare', 'reported_partial', 'reported_flush',
         'reported_fsync', 'reported_index_transaction', 'reported_index_selector',
         'kill_partial', 'kill_fsync', 'kill_index_selector')
READERS = ('selected', 'old_index', 'missing_selector', 'missing_db')


def transitions(trace):
    # Existing writer: 10 transitions; killed writer stops after child start (8).
    # One reap, then each exec-started reader is a bounded recovery transaction.
    # Count individual GETs/retries/canonical loads separately in its receipt.
    return (8 if trace.seam.startswith('kill_') else 10) + 1 + len(trace.operations)


def validate(trace):
    if (not isinstance(trace, Trace) or trace.seam not in SEAMS or
            type(trace.reverse) is not bool or not isinstance(trace.operations, tuple) or
            not 1 <= len(trace.operations) <= 4):
        raise ValueError('invalid cold trace')
    if trace.operations[0] != Operation('read', 'selected'):
        raise ValueError('cold historical positive read must come first')
    if any(op.kind != 'read' or op.value not in READERS for op in trace.operations):
        raise ValueError('unsupported cold reader')
    if transitions(trace) > MAX_TRANSITIONS:
        raise ValueError('cold transition budget')


def strategy():
    return st.builds(Trace, st.sampled_from(SEAMS), st.booleans(),
        st.lists(st.sampled_from(READERS), min_size=0, max_size=3).map(
            lambda values: (Operation('read', 'selected'),) +
            tuple(Operation('read', value) for value in values)))


def corpus():
    generated = collect_traces(seed_value=2026101502, examples=22,
                               strategy=strategy(), validator=validate)
    if len(generated) != 22:
        raise ValueError('expected 22 completed pure draws')
    seeds = tuple(Entry(f'seed-{i:02}', 'seeded', Trace(seam, bool(i % 2),
        tuple(Operation('read', mode) for mode in READERS))) for i, seam in enumerate(SEAMS))
    entries = seeds + tuple(Entry(f'generated-{i:02}', 'generated', trace)
                            for i, trace in enumerate(generated))
    return seal(Corpus(2026101502, len(generated), entries), validator=validate)
