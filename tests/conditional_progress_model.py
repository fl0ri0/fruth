"""Independent finite A6 event expectations; no Fruth imports or classifiers."""
from copy import deepcopy
from hypothesis import strategies as st
from tests.persistence_trace_adapter import collect_traces

SEED = 2026102406
MODES = ('ready', 'no_activation', 'absent_before_promotion', 'lost_after_admission',
         'restored_before_activation', 'retry_after_loss', 'cancel', 'supersede', 'held_call')
ROLES = {'producer', 'consumer'}


def schedule(mode='ready', reverse=False, capacity=1, negative='none', incomplete='none', delay='none'):
    return dict(mode=mode, reverse=reverse, capacity=capacity, negative=negative,
                incomplete=incomplete, delay=delay,
                retry_roles=(['producer', 'consumer'] if reverse else ['consumer', 'producer']) if mode == 'retry_after_loss'
                            else ['consumer'] if mode == 'retry_one' else [],
                premise=('breaking' if mode in ('no_activation', 'absent_before_promotion',
                         'lost_after_admission', 'held_call', 'retry_one') else 'satisfying_after_declared_events'))


def expected(s):
    # Derived solely from declared events. Observed missing runtime records cannot
    # redefine eligibility or discharge an admitted obligation.
    eligible = ROLES - ({'consumer'} if s['mode'] in ('cancel', 'supersede') else set())
    dispatch = set() if s['mode'] in ('no_activation', 'absent_before_promotion', 'lost_after_admission') else eligible
    if s['mode'] in ('retry_after_loss', 'retry_one'):
        dispatch = set(s['retry_roles'])
    covered = dispatch - {s['negative'], s['incomplete']}
    return dict(eligible=sorted(eligible), dispatch=sorted(dispatch), covered=sorted(covered))


def model_trace(s, events):
    """Derive duty only from accepted roles and declared external/control events.

    Never use selected/pending/completed runtime lists to release a duty.
    An attempt takes a role out of the never-attempted set; settlement remains
    a separate duty even for a negative or incomplete verdict.
    """
    owed, attempted, returned, settled = set(ROLES), set(), set(), set()
    capacity, activated = s['mode'] != 'absent_before_promotion', False
    trace = []
    for e in events:
        kind, role = e['kind'], e.get('role')
        if kind == 'authorized_disposition':
            assert role == 'consumer' and s['mode'] in ('cancel', 'supersede')
            owed.remove(role)
        elif kind == 'capacity_lost':
            capacity = False
        elif kind == 'capacity_restored':
            capacity = True
        elif kind == 'scheduler_activation':
            activated = True
        elif kind == 'transport_dispatch':
            attempted.add(role)
        elif kind == 'transport_return':
            returned.add(role)
        elif kind == 'execution_settled':
            settled.add(role)
        trace.append(dict(event_index=e['index'], kind=kind,
                          remaining_attempt_duty=sorted(owed-attempted),
                          returned_awaiting_settlement=sorted(returned-settled),
                          capacity=capacity, activation_seen=activated))
    return trace


def violations(s, observation):
    exp = expected(s)
    errors = []
    calls = [e['role'] for e in observation['events'] if e['kind'] == 'transport_dispatch']
    returns = [e['role'] for e in observation['events'] if e['kind'] == 'transport_return']
    settled = [e['role'] for e in observation['events'] if e['kind'] == 'execution_settled']
    for e in observation['events']:
        if e['kind'] in ('transport_dispatch', 'execution_settled'):
            identity = observation.get('identities', {}).get(e['role'])
            if identity and e['review_id'] != identity['branch_id']:
                errors.append('review_identity_mismatch')
    for kind, actual in [('dispatch', calls), ('return', returns), ('settlement', settled)]:
        if sorted(actual) != exp['dispatch']:
            errors.append(kind + '_mismatch')
    for role in exp['dispatch']:
        positions = {kind: [i for i,e in enumerate(observation['events'])
                            if e['kind'] == kind and e.get('role') == role]
                     for kind in ('transport_dispatch', 'transport_return', 'execution_settled')}
        if all(len(v) == 1 for v in positions.values()):
            if not (positions['transport_dispatch'][0] < positions['transport_return'][0]
                    < positions['execution_settled'][0]):
                errors.append('causal_order_mismatch')
    if sorted(observation['durable_review_roles']) != exp['dispatch']:
        errors.append('durable_outcome_mismatch')
    if sorted(observation['covered_roles']) != exp['covered']:
        errors.append('coverage_mismatch')
    if s['mode'] != 'absent_before_promotion' and set(observation['admitted_roles']) != ROLES:
        errors.append('admission_lost')
    if observation['unresolved'] != 2 - len(exp['covered']):
        errors.append('unresolved_mismatch')
    if exp['dispatch'] and not any(e['kind'] == 'selection_opportunity' for e in observation['events']):
        errors.append('no_selection_opportunity')
    if observation['attempt_budget_changed']:
        errors.append('attempt_budget_changed')
    return errors


def corpus():
    seeds = [schedule(), schedule(reverse=True, capacity=2, delay='producer'),
             schedule('lost_after_admission'), schedule('retry_after_loss')]
    strategy = st.builds(schedule, mode=st.sampled_from(MODES), reverse=st.booleans(),
                         capacity=st.integers(1, 2), negative=st.sampled_from(['none', 'producer', 'consumer']),
                         incomplete=st.sampled_from(['none', 'producer', 'consumer']),
                         delay=st.sampled_from(['none', 'producer', 'consumer']))
    draws = collect_traces(seed_value=SEED, examples=6, strategy=strategy, validator=lambda _: None)
    assert len(draws) == 6
    return [{'label':f'seed-{i:02}', 'category':'seeded', 'schedule':s} for i,s in enumerate(seeds)] + [
            {'label':f'generated-{i:02}', 'category':'generated', 'schedule':s} for i,s in enumerate(draws)]


def sensitivity(s, observed):
    outcomes = {}
    for fault in ('stalled', 'dropped_dispatch', 'dropped_settlement', 'dropped_durable'):
        o = deepcopy(observed)
        if fault == 'stalled':
            o['events'] = [e for e in o['events'] if e['kind'] not in
                           ('transport_dispatch', 'transport_return', 'execution_settled')]
            o['durable_review_roles'] = []
        elif fault == 'dropped_durable':
            o['durable_review_roles'].remove('consumer')
        else:
            kind = 'transport_dispatch' if fault == 'dropped_dispatch' else 'execution_settled'
            o['events'] = [e for e in o['events'] if not (e['kind'] == kind and e.get('role') == 'consumer')]
        outcomes[fault] = violations(s, o)
        assert outcomes[fault], fault
    # Equivalent orders preserve counts and identities, not an expected winner.
    o = deepcopy(observed)
    slots = [i for i,e in enumerate(o['events']) if e['kind'] in
             ('transport_dispatch', 'transport_return', 'execution_settled')]
    # Swap complete per-role event chains, preserving dispatch -> return ->
    # settlement. This changes the winner, not each obligation's causal order.
    reordered = sorted((o['events'][i] for i in slots), key=lambda e:e['role'], reverse=True)
    for i,e in zip(slots, reordered):
        o['events'][i] = e
    assert not violations(s, o)
    return outcomes
