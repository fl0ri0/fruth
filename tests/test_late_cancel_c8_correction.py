"""C8 correction controls; historical cancellation models and blobs stay intact."""
from copy import deepcopy
from unittest.mock import patch

from hypothesis.errors import DidNotReproduce
import pytest

import fruth_webserver as web
from fruth_services.response_frames import load_latest_response_state
from tests import test_late_cancel_lineage_hypothesis as original
from tests.test_graph_lineage_c3_c4_corrections import durable_evidence
from tests.test_graph_lineage_stateful_hypothesis import PREPARATION


def test_original_c8_blob_no_longer_reproduces():
    # Invoke the retained function itself, including its exact original blob.
    machines = []
    initialize = original.LateCancelMachine.__init__

    def capture(machine):
        initialize(machine)
        machines.append(machine)

    with patch.object(original.LateCancelMachine, '__init__', capture), pytest.raises(DidNotReproduce):
        original.test_retained_cancellation_failure_blob()
    # A blob ending at the former failure may exhaust its choices after the
    # corrected step. Require the complete original trace, not just the exception.
    assert len(machines) == 1
    machine = machines[0]
    assert not machine.failed and machine.settled and machine.steps == 6
    assert machine.timing == 'before_dispatch' and machine.representation == 'base64'
    assert machine.control_requests == [200] and not machine.boundary_errors
    results = machine.engine.payload['late_fill']['fill_results']
    assert len(results) == 1 and durable_evidence(results[0]) == machine.sibling_result


@pytest.mark.parametrize('prefix', range(6))
def test_original_c8_prefixes_preserve_evidence(prefix):
    machine = original.LateCancelMachine()
    try:
        machine.accepted(False, 'base64', 'before_dispatch')
        machine.engine.inputs.update(correction='original_prefix', prefix=prefix)
        for _ in range(prefix):
            machine.advance()
            machine.conservation()
    except BaseException:
        machine.failed = True
        raise
    finally:
        machine.teardown()


@pytest.mark.parametrize('action,status', [('cancel', 'cancelled'), ('waive', 'waived'),
                                         ('supersede', 'superseded')])
@pytest.mark.parametrize('scope', ['branch', 'batch', 'all'])
@pytest.mark.parametrize('timing', ['before_dispatch', 'during_provider'])
def test_shared_controls_preserve_accepted_sibling(action, status, scope, timing):
    machine = original.LateCancelMachine()
    try:
        machine.accepted(False, 'base64', timing)
        for _ in range(4):
            machine.advance()
        engine, sequence = machine.engine, machine.sequence
        engine.inputs.update(correction='shared_control', action=action, scope=scope)
        calls_before = len(engine.harness.provider_calls)

        def check(value):
            # Retain the independent sibling, canonical binding and duty oracle.
            machine.check(value)
            late = value['late_fill']
            assert not any(r.get('branch_id') == machine.target for r in late.get('fill_results', []))
            stopped = [b for b in late['cancelled_branches'] if b['branch_id'] == machine.target]
            assert len(stopped) == 1 and stopped[0]['status'] == status
            assert stopped[0]['execution_gate']['authority'] == 'user_control'
            assert not any(b['branch_id'] == machine.target
                           for key in ('pending_branches', 'active_branches') for b in late.get(key, []))
            assert not any(o.get('branch_id') == machine.target and o.get('status') == 'fulfilled'
                           for o in value['response_frame']['output']['outputs'])

        def control():
            before = deepcopy(engine.store['response_payload']['late_fill']['fill_results'])
            if timing == 'during_provider':
                assert any(b['branch_id'] == machine.target
                           for b in engine.store['response_payload']['late_fill']['active_branches'])
            with patch.object(web, '_get_response_lookup_record', engine.late.get_response_lookup_record), \
                 patch.object(web, '_touch_response_lookup', engine.late.touch_response_lookup):
                response = engine.harness.client.post('/api/responses/stateful-lineage/late_fill/control',
                    json={'action': action, 'scope': scope, 'branch_id': machine.target,
                          'reason': 'Retain accepted sibling evidence.',
                          # Incoming claims are never a source of accepted results.
                          'fill_results': [{'branch_id': machine.target, 'status': 'completed'}]})
            engine.counts['control_endpoint_calls'] += 1
            assert response.status_code == 200, response.get_json()
            body = response.get_json()
            assert body['control']['branch_ids'] == [machine.target]
            assert body['control']['status'] == status and body['control']['scope'] == scope
            # Wire responses intentionally omit runtime/full result records.
            # Check their canonical public output, then the complete saved state.
            public = body['response']['outputs']
            sibling = next(o for o in public if o.get('branch_id') == machine.sibling)
            assert sibling['status'] == 'fulfilled'
            assert not any(o.get('branch_id') == machine.target and o.get('status') == 'fulfilled'
                           for o in public)
            assert body['response']['response_frame']['frame_id'] == \
                engine.store['response_payload']['response_frame']['frame_id']
            check(engine.store['response_payload'])
            assert durable_evidence(engine.store['response_payload']['late_fill']['fill_results']) == \
                durable_evidence(before)
            recovered = load_latest_response_state('stateful-lineage',
                frames_dir=engine.harness.response_frames_dir)
            engine.counts['durable_recovery_reads'] += 1
            assert recovered['ok']
            check(recovered['response_payload'])
            machine.check_history()

        if timing == 'before_dispatch':
            control()
            sequence.publish(engine.store['response_payload'])
        provider, callback_errors = web.requests.post, []

        def delayed_provider(url, **kwargs):
            reply = provider(url, **kwargs)
            if timing == 'during_provider':
                try:
                    control()
                except BaseException as exc:
                    callback_errors.append(exc)
            return reply

        with patch.object(web.requests, 'post', delayed_provider):
            engine.late.complete_response_late_fill(response_payload=deepcopy(engine.payload),
                request_payload=engine.request, assistant_message=PREPARATION,
                artifact_gap=deepcopy(sequence.handoff['artifact_gap']), source_route_payload=None)
        engine.counts['worker_calls'] += 1
        if callback_errors:
            raise callback_errors[0]
        assert len(engine.harness.provider_calls) == calls_before + (timing == 'during_provider')
        sequence.publish(engine.store['response_payload'])
        check(engine.payload)
        machine.recover()
        before_calls = len(engine.harness.provider_calls)
        engine.late.complete_response_late_fill(response_payload=deepcopy(engine.payload),
            request_payload=engine.request, assistant_message=PREPARATION,
            artifact_gap=deepcopy(sequence.handoff['artifact_gap']), source_route_payload=None)
        engine.counts['worker_calls'] += 1
        assert len(engine.harness.provider_calls) == before_calls
        sequence.publish(engine.store['response_payload'])
        check(engine.payload)
        machine.recover()
    except BaseException:
        machine.failed = True
        raise
    finally:
        machine.teardown()
