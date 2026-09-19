"""Exact durable identity binding without replacing live progress or another frame."""
import copy

import pytest


@pytest.mark.parametrize('identity', ['same', 'older', 'foreign', 'missing', 'unavailable'])
def test_detailed_lookup_binds_only_matching_durable_frame(monkeypatch, identity):
    import fruth_webserver as web
    live = {'id': 'lookup-test', 'status': 'in_progress', 'response_payload': {
        'id': 'lookup-test', 'response_frame': {'frame_id': 'lookup-test:frame-2',
            'frame_sequence': 2, 'runtime': {'expanded': True}},
        'runtime': {'progress': 'running'},
        'durability': {'source': 'response_frame_ledger', 'frame_sequence': 1}}}
    durable = {'response_frame': {'frame_id': 'lookup-test:frame-2', 'frame_sequence': 2,
                                  'runtime_snapshot_ref': {'sha256': 'durable'}},
               'durability': {'source': 'response_frame_ledger', 'frame_sequence': 2}}
    if identity == 'older':
        durable['response_frame'].update(frame_id='lookup-test:frame-1', frame_sequence=1)
    if identity == 'foreign':
        durable['response_frame']['frame_id'] = 'foreign:frame-2'
    if identity == 'missing':
        live['response_payload'].pop('response_frame')
        live['response_payload'].pop('durability')
    before = copy.deepcopy(live)
    monkeypatch.setattr(web._RESPONSES_RUNTIME, 'get_response_lookup_record', lambda rid: live)
    monkeypatch.setattr(web, '_load_latest_response_state', lambda *a, **kw: {
        'ok': identity != 'unavailable', 'response_payload': durable})
    # Exercise representation binding after the existing freshness arbitration.
    monkeypatch.setattr(web, '_response_lookup_record_should_refresh_from_frame', lambda *a: False)
    result = web._get_response_lookup_record('lookup-test')
    assert live == before
    if identity == 'same':
        assert result['response_payload']['response_frame'] == durable['response_frame']
        assert result['response_payload']['durability'] == durable['durability']
        assert result['response_payload']['runtime'] == {'progress': 'running'}
        result['response_payload']['response_frame']['runtime_snapshot_ref']['sha256'] = 'local mutation'
        assert durable['response_frame']['runtime_snapshot_ref']['sha256'] == 'durable'
    else:
        assert result == before
