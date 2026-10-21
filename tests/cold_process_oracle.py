"""Independent comparisons over observations, with no Fruth imports."""
from copy import deepcopy


def evidence(value):
    # Same established test normalization, not a runtime acceptance helper.
    if isinstance(value, dict):
        return {k: evidence(v) for k, v in value.items()
                if k not in {'created_at', 'updated_at', 'started_at', 'completed_at',
                             'failed_at', 'image_data_url'} and v not in (None, '', [], {})}
    if isinstance(value, list):
        return [evidence(v) for v in value]
    return value


def semantic(value):
    late = value.get('late_fill') or {}
    return {'results': {r['branch_id']: evidence(r) for r in late.get('fill_results', [])},
            'cancelled': evidence(late.get('cancelled_branches', [])),
            'pending': [r['branch_id'] for r in late.get('pending_branches', [])],
            'execution': {k: evidence(late.get(k)) for k in
                ('successor_reopen_execution', 'terminal_closure_repair_reopen', 'partial_rebase_execution')}}


def assert_recovery(expected, observed):
    assert observed['fresh'], 'reader inherited live context'
    assert observed['storage_unchanged'], 'passive recovery/retry changed storage'
    assert observed['effects'] == [], 'passive recovery created operational authority'
    assert observed['claims_after'] == 0, 'recovery acquired a worker claim'
    assert observed['ledger_prefix_kept'], 'frozen parent history changed'
    assert observed['all_artifacts_valid'], 'saved artifact bytes/bindings lost'
    assert observed['ok'], 'valid historical recovery rejected'
    assert observed['frame_id'] == expected['frame_id'], 'exact frame identity lost'
    assert observed['frame_sequence'] == expected['frame_sequence'], 'frame sequence changed'
    assert observed['response_id'] == expected['response_id'], 'response identity changed'
    assert observed['semantic'] == expected['semantic'], 'accepted/cancelled/pending/execution evidence changed'
    assert observed['outputs'] == expected['outputs'], 'output/artifact identity changed'
    assert not (observed['persistence'] or {}).get('status') == 'committed', 'reader invented original write confirmation'
    if expected['partial']:
        assert observed['errors'], 'malformed tail hidden by canonical recovery'
    for public in observed['public']:
        assert public['status_code'] == 200, 'valid public historical view rejected'
        assert not (public['persistence'] or {}).get('status') == 'committed', 'public view invented original write confirmation'
        assert public['frame_id'] == expected['frame_id'], 'public frame identity changed'
        if public['view'] in {'truth', 'full'}:
            assert public['semantic'] == expected['semantic'], 'full public evidence changed'
    assert len(observed['public']) == 6, 'missing public view'
    assert observed['retry_codes'] == [409, 409, 409], 'retry duplicated accepted or revived cancelled work'


def sensitivity(expected, observed):
    mutations = {
        'fresh': False, 'storage_unchanged': False, 'effects': ['schedule'],
        'claims_after': 1, 'ledger_prefix_kept': False, 'all_artifacts_valid': False,
        'ok': False, 'frame_id': 'foreign', 'frame_sequence': -1,
        'response_id': 'foreign', 'semantic': {}, 'outputs': [],
        'persistence': {'status': 'committed'}, 'retry_codes': [200, 409, 409],
        'public': [],
    }
    if expected['partial']:
        mutations['errors'] = []
    rejected = []
    for key, value in mutations.items():
        bad = deepcopy(observed); bad[key] = value
        try:
            assert_recovery(expected, bad)
        except AssertionError:
            rejected.append(key)
        else:
            raise AssertionError('oracle insensitive to ' + key)
    for field in ('persistence', 'frame_id'):
        bad = deepcopy(observed)
        bad['public'][0][field] = {'status': 'committed'} if field == 'persistence' else 'foreign'
        try:
            assert_recovery(expected, bad)
        except AssertionError:
            rejected.append('public.' + field)
        else:
            raise AssertionError('public oracle insensitive to ' + field)
    for field in ('results', 'cancelled', 'execution'):
        bad = deepcopy(observed)
        bad['semantic'][field] = {} if field != 'cancelled' else []
        try:
            assert_recovery(expected, bad)
        except AssertionError:
            rejected.append('semantic.' + field)
        else:
            raise AssertionError('semantic oracle insensitive to ' + field)
    return rejected


def assert_corrupt(observed, *, snapshot=False):
    assert not observed['ok'], 'corrupt authoritative truth accepted'
    allowed = {'response_frame_snapshot_unavailable', 'response_frame_public_body_snapshot_unavailable'}
    assert observed['error']['code'] in (allowed if snapshot else {'response_frame_ledger_corrupt'})
    assert observed['storage_unchanged'] and not observed['effects'] and not observed['claims_after']
    for view in observed['public']:
        if not snapshot or view['view'] in {'truth', 'full'}:
            assert view['status_code'] == 409, 'corrupt full truth invented'
        assert not (view['persistence'] or {}).get('status') == 'committed', 'corrupt data invented write confirmation'
