"""Pure bounded inputs and endpoint oracle for the runtime composition study.

No Fruth owners, fixture construction or I/O occur here. Generation completes
before the runner reserves any actual runtime scenario. The endpoint demand is
declared from literal source data, never from a generated graph, runtime verdict
or projected response. Native validators are observations, not this oracle.
"""
from dataclasses import asdict, dataclass
import base64
import copy
import hashlib
import json

from hypothesis import strategies as st

from tests.persistence_trace_adapter import collect_traces


VIEWS = ('truth', 'full', 'ui', 'status', 'debug')
DEFECTS = (
    'none', 'missing_snapshot', 'duplicate_producer', 'wrong_response',
    'wrong_producer', 'wrong_artifact', 'equal_bytes_other_artifact',
    'version_before_read', 'version_before_dispatch', 'missing_file',
    'wrong_consumer', 'scope_before_dispatch', 'equal_bytes_sibling',
)
SEED = 2026102401
MAX_SCENARIOS = 32
MAX_TRANSITIONS = 32
GENERATED_EXAMPLES = 22


@dataclass(frozen=True)
class Trace:
    view: str = 'truth'
    fallback: bool = False
    defect: str = 'none'
    values: tuple[int, int] = (7, 11)
    subject: str = 'alpha'
    version: int = 1


def validate_trace(trace):
    if not isinstance(trace, Trace) or trace.view not in VIEWS:
        raise ValueError('invalid trace or publication view')
    if type(trace.fallback) is not bool or trace.defect not in DEFECTS:
        raise ValueError('invalid recovery choice or defect')
    if (type(trace.values) is not tuple or len(trace.values) != 2
            or any(type(n) is not int or not 1 <= n <= 40 for n in trace.values)):
        raise ValueError('values must be two bounded integers')
    if trace.subject not in ('alpha', 'beta') or type(trace.version) is not int or trace.version not in (1, 2):
        raise ValueError('invalid source subject or version')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def source_text(trace):
    validate_trace(trace)
    # The existing text writer strips outer whitespace and terminates one line.
    # Declare that physical representation independently before calling it.
    return canonical({'subject': trace.subject, 'version': trace.version, 'values': trace.values}) + '\n'


def output_text(trace):
    """Independent exact endpoint requirement, not the provider implementation."""
    validate_trace(trace)
    a, b = trace.values
    return (f'<html><style>p{{margin:1em}}</style><body><h1>{trace.subject}</h1><p>version={trace.version}</p>'
            f'<p>values={a},{b};sum={a + b}</p></body></html>\n')


def trace_strategy():
    return st.builds(
        Trace, view=st.sampled_from(VIEWS), fallback=st.booleans(),
        defect=st.sampled_from(DEFECTS),
        values=st.tuples(st.integers(1, 40), st.integers(1, 40)),
        subject=st.sampled_from(('alpha', 'beta')), version=st.integers(1, 2),
    )


def controls():
    """Twenty labeled controls; expectation modes belong to the sealed plan.

    Direct bounded views deliberately remain legal observations even when they
    cannot provide the consumer's required producer witness. Their test outcome
    must distinguish a visible unresolved prerequisite from fulfilled delivery.
    """
    positives = (
        ('truth-positive', Trace()),
        ('full-positive', Trace(view='full', values=(13, 17), subject='beta', version=2)),
        ('ui-canonical-fallback', Trace(view='ui', fallback=True)),
        ('status-canonical-fallback', Trace(view='status', fallback=True, version=2)),
        ('debug-canonical-fallback', Trace(view='debug', fallback=True, subject='beta')),
        ('equal-bytes-sibling-positive', Trace(defect='equal_bytes_sibling')),
    )
    partial = tuple((f'{view}-direct', Trace(view=view)) for view in ('ui', 'status', 'debug'))
    negatives = tuple((defect, Trace(defect=defect)) for defect in DEFECTS
                      if defect not in ('none', 'equal_bytes_sibling'))
    return positives + partial + negatives


def make_corpus():
    """One 32-entry sealed-corpus candidate: ten labeled seeds + 22 draws.

    Pure Hypothesis draws are collected first. Seeded coverage is never credited
    to generation; no runtime exception, counter or failure latch affects draws.
    """
    generated = collect_traces(
        seed_value=SEED, examples=GENERATED_EXAMPLES,
        strategy=trace_strategy(), validator=validate_trace,
    )
    if len(generated) != GENERATED_EXAMPLES:
        raise ValueError('generation did not supply 22 complete examples')
    # The original ten domain choices each get an explicitly labeled seed.
    # Added scope/consumer/sibling choices have deterministic controls and remain
    # in the generation domain; they do not silently enlarge the campaign.
    # The first seed is successful, preventing a campaign of negatives alone.
    seeds = tuple(Trace(view=VIEWS[i % len(VIEWS)], fallback=True, defect=defect,
                        values=(7 + i, 11 + i), subject=('alpha', 'beta')[i % 2],
                        version=1 + i % 2)
                  for i, defect in enumerate(DEFECTS[:10]))
    entries = [
        {'identity': f'seed-{i:02}', 'origin': 'seeded', 'trace': asdict(trace)}
        for i, trace in enumerate(seeds)
    ] + [
        {'identity': f'generated-{i:02}', 'origin': 'generated', 'trace': asdict(trace)}
        for i, trace in enumerate(generated)
    ]
    if len(entries) != MAX_SCENARIOS:
        raise ValueError('corpus entry cap/count mismatch')
    return {'schema': 1, 'seed': SEED, 'generated_examples': GENERATED_EXAMPLES,
            'scenario_limit': MAX_SCENARIOS, 'transition_limit': MAX_TRANSITIONS,
            'entries': entries}


def seal(corpus):
    """Return an immutable canonical JSON string and its SHA-256."""
    content = canonical(corpus)
    return {'content': content, 'sha256': hashlib.sha256(content.encode('utf-8')).hexdigest()}


def assert_endpoint(observation, expected):
    """Judge actual endpoint observations independently of product classifiers.

    expected: mode ('delivered'/'blocked'/'either'), defect, raw_text, identity mapping
      containing exact response/producer/consumer/artifact/path coordinates,
      output_text and output_path. Identity values are frozen at producer
      acceptance, before publication; semantic raw_text is fixed before planning.
    observation: canonical_preserved, passive_no_execution, unresolved, error,
      calls (list of {prompt, read, output_path, output_text}), final_receipt.
      A call's read is the actual provider input_refs[0] without its 'kind'.
      final_receipt is the native saved_file_consumption_evidence dictionary.

    This checks the named output scope by its exact path. The adapter separately
    records and checks the one allowed transport text_artifact_requests entry.
    No writer receipt or recovered scheduling permit is required or inferred.
    'either' is a predeclared partial-view contract: either exact delivery or an
    explicit unmet prerequisite is legal. This never changes the expectation
    after observing the result; both alternatives retain all strict checks.
    """
    assert observation['canonical_preserved'] is True, 'canonical history changed'
    assert observation['passive_no_execution'] is True, 'passive read executed work'
    assert expected['mode'] in ('delivered', 'blocked', 'either'), 'unknown endpoint expectation'
    calls = observation['calls']
    mode = expected['mode']
    if mode == 'either':
        mode = 'delivered' if calls else 'blocked'
    if mode == 'blocked':
        assert calls == [], 'unmet prerequisite reached consumer'
        assert observation['unresolved'] is True, 'unmet prerequisite disappeared'
        error = observation.get('error', '')
        assert isinstance(error, str) and (
            'saved_file_' in error
            or (expected.get('defect') == 'missing_file' and error.startswith('[Errno 2]'))
        ), 'blocked result lacks an explicit recognized prerequisite error'
        assert not observation.get('final_receipt'), 'blocked result claimed consumption'
        return

    assert len(calls) == 1, 'compatible route must invoke exactly one consumer'
    assert observation['unresolved'] is False, 'compatible route stayed unresolved'
    assert not observation.get('error'), 'compatible route reported an error'
    call = calls[0]
    prompt = call['prompt']
    start, end = '--- SAVED FILE START ---\n', '\n--- SAVED FILE END ---'
    assert prompt.count(start) == prompt.count(end) == 1, 'saved input framing changed'
    actual_text = prompt.split(start, 1)[1].split(end, 1)[0]
    assert actual_text == expected['raw_text'], 'required source meaning/bytes not delivered'
    raw = expected['raw_text'].encode('utf-8')
    digest = hashlib.sha256(raw).hexdigest()
    read = call['read']
    for key, value in expected['identity'].items():
        assert read.get(key) == value, f'delivered identity changed: {key}'
    assert read.get('sha256') == digest, 'delivered version digest changed'
    assert read.get('size_bytes') == len(raw), 'delivered source size changed'
    assert call['output_path'] == expected['output_path'], 'consumer output target changed'
    assert call['output_text'] == expected['output_text'], 'consumer output meaning changed'

    receipt = observation['final_receipt']
    assert receipt.get('status') == 'consumed', 'missing consumption evidence'
    retained_read = receipt.get('read', {})
    for key, value in expected['identity'].items():
        assert retained_read.get(key) == value, f'receipt identity changed: {key}'
    assert retained_read.get('sha256') == digest, 'receipt source version changed'
    assert retained_read.get('size_bytes') == len(raw), 'receipt source size changed'
    assert base64.b64decode(retained_read.get('utf8_base64', ''), validate=True) == raw, 'receipt source bytes changed'
    contract = receipt.get('contract', {})
    assert contract.get('kind') == 'fruth.saved_file_dependency' and contract.get('version') == 1, 'receipt contract type changed'
    for key in ('producer_branch_id', 'producer_phase_id', 'consumer_branch_id', 'consumer_phase_id'):
        assert contract.get(key) == expected['identity'][key], f'receipt contract scope changed: {key}'
    assert receipt.get('input_sha256') == hashlib.sha256(prompt.encode('utf-8')).hexdigest(), 'receipt input claim changed'
    output = receipt.get('output', {})
    output_raw = expected['output_text'].encode('utf-8')
    assert output == {'path': expected['output_path'],
                      'sha256': hashlib.sha256(output_raw).hexdigest(),
                      'size_bytes': len(output_raw)}, 'receipt output claim changed'


def sensitivity_observations(observation):
    """Pure deliberately wrong observations; none starts a runtime scenario."""
    variants = []
    for field in ('canonical_preserved', 'passive_no_execution'):
        changed = copy.deepcopy(observation)
        changed[field] = False
        variants.append((field, changed))
    changed = copy.deepcopy(observation)
    changed['unresolved'] = not observation['unresolved']
    variants.append(('unresolved', changed))
    if observation['calls']:
        changed = copy.deepcopy(observation)
        changed['calls'] = []
        variants.append(('reject-all', changed))
        for key in ('response_id', 'producer_branch_id', 'consumer_branch_id', 'artifact_ref', 'path', 'sha256'):
            changed = copy.deepcopy(observation)
            changed['calls'][0]['read'][key] = 'deliberately-wrong'
            variants.append((key, changed))
        changed = copy.deepcopy(observation)
        changed['calls'][0]['output_text'] = '<html>wrong subject and result</html>'
        variants.append(('output-meaning', changed))
        changed = copy.deepcopy(observation)
        prompt = changed['calls'][0]['prompt']
        before, remainder = prompt.split('--- SAVED FILE START ---\n', 1)
        _, after = remainder.split('\n--- SAVED FILE END ---', 1)
        changed['calls'][0]['prompt'] = before + '--- SAVED FILE START ---\n{"subject":"wrong"}\n--- SAVED FILE END ---' + after
        variants.append(('source-input', changed))
        changed = copy.deepcopy(observation)
        changed['final_receipt']['input_sha256'] = '0' * 64
        variants.append(('evidence-scope', changed))
        changed = copy.deepcopy(observation)
        changed['final_receipt']['read']['utf8_base64'] = 'e30='
        variants.append(('receipt-bytes', changed))
        changed = copy.deepcopy(observation)
        changed['final_receipt']['contract']['consumer_phase_id'] = 'deliberately-wrong'
        variants.append(('receipt-contract', changed))
    else:
        changed = copy.deepcopy(observation)
        changed['calls'] = [{'unexpected': 'provider invocation'}]
        variants.append(('blocked-executed', changed))
        changed = copy.deepcopy(observation)
        changed['error'] = ''
        variants.append(('missing-prerequisite', changed))
    return tuple(variants)
