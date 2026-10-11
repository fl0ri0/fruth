"""Retained distinct projection defect reached after C6; keep this oracle red."""
from pathlib import Path

import pytest
from hypothesis import reproduce_failure, settings
from hypothesis.errors import DidNotReproduce
from hypothesis.stateful import get_state_machine_test

from tests.test_graph_lineage_two_successors_hypothesis import TwoSuccessorMachine


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('fault', ['wrong_response', 'wrong_obligation'])
def test_new_second_result_cannot_be_replaced_by_foreign_response_image(reverse, fault):
    machine = TwoSuccessorMachine()
    machine.control = True
    try:
        machine.accepted(reverse, 1)
        machine.admit()
        machine.execute()
        machine.next_parent()
        machine.admit()
        machine.seed_image(fault)
        machine.execute()
        engine = machine.engine
        assert len(engine.harness.provider_calls) == 2
        result = next(r for r in engine.payload['late_fill']['fill_results']
                      if r['branch_id'] == machine.branch)
        assert Path(result['saved_image_path']).read_bytes() == engine.model.png
        frame = engine.payload['response_frame']
        output = next(o for o in frame['output']['outputs'] if o.get('branch_id') == machine.branch)
        artifact = next(a for a in frame['artifacts']['output'] if a['artifact_ref'] == output['artifact_ref'])
        # Separate second-result oracle permits attribution on pre-C6 source,
        # where the original first-artifact continuity oracle still fails.
        assert artifact['path'] == result['saved_image_path'], 'canonical second output selected foreign evidence'
        assert artifact['source_response_id'] == engine.payload['id']
    except BaseException:
        machine.failed = True
        raise
    finally:
        machine.teardown()


@pytest.mark.parametrize('steps,blob', [
    (24, b'AXicPYzbDYBAEAJBz+fZ1Nh/B9eMrCbuBwkDi4SRbg1W05FZJELFHt/KO/chcZnNTPpRi4izmoeZ33KN9jwmegD1JwlK'),
    (32, b'AXicJYyJDYAwDAMvLVBKWco7sb/qBEWyovNDKAT6dFnf0q6mWwNIM9DSYYxxSxxpNEeNpp40C5HZs27yA9eWe2io+8/1YAObugrB'),
])
def test_retained_foreign_projection_failure_blob(steps, blob):
    machines = []

    def factory():
        machine = TwoSuccessorMachine()
        machine.control = True
        machines.append(machine)
        return machine

    replay = reproduce_failure('6.168.5', blob)(
        get_state_machine_test(factory, settings=settings(
            TwoSuccessorMachine.TestCase.settings, stateful_step_count=steps)))
    try:
        replay()
    except DidNotReproduce:
        assert len(machines) == 1 and not machines[0].failed
