"""Bounded B13.03 audit: lineage is not the repair admission/authority source.

No runtime fixes. The generated oracle and persisted adapter lane are inherited
unchanged from the established native one-successor contract harness. Sink
mutations below are explicitly malformed fixtures, not public-path witnesses.
"""
from copy import deepcopy

import pytest
from hypothesis import Phase, settings
import tests.test_graph_lineage_stateful_hypothesis as lineage


@pytest.mark.parametrize('missing', ['lifecycle', 'review', 'contract', 'scope'])
def test_lineage_present_without_repair_admission_is_inert(missing):
    machine = lineage.PersistedGraphLineageMachine()
    machine.control = True
    try:
        machine.accepted(True, 0)
        machine.freeze_parent()
        before = machine.ledger_bytes()
        parent = deepcopy(machine.reviewed)
        candidate = deepcopy(machine.candidate)
        relation = deepcopy(candidate['frame_relation'])
        graph = lineage.graph_of(parent)
        if missing == 'lifecycle':
            graph['graph_patch_lifecycle'] = []
        elif missing == 'review':
            for record in graph['graph_patch_lifecycle']:
                record['validation_review'] = {}
        elif missing == 'contract':
            candidate['execution_contract'] = {}
        else:
            candidate['owed_branch_ids'] = ['unrequested-foreign-duty']
        result = machine.request_owner._prepare_graph_patch_successor_reopen(parent, candidate)
        assert result['status'] == 'blocked', result
        assert result['blocked_reasons'], result
        assert candidate['frame_relation'] == relation
        assert machine.ledger_bytes() == before
        assert not machine.harness.provider_calls
        machine.record('lineage_without_admission', missing=missing,
                       blocked_reasons=result['blocked_reasons'])
        machine.conservation()
    except BaseException:
        machine.failed = True
        raise
    finally:
        machine.teardown()


class B1303BoundedMachine(lineage.PersistedGraphLineageMachine):
    """Generate native proposal/freeze/admit/dispatch/recovery orderings.

    Fault probes vary admission/authority contracts while retaining lineage;
    valid admit/result rules remain available, preventing an always-reject test.
    No shrink or database replay phase; failures retain full native witnesses.
    """


TestB1303BoundedSuccessor = B1303BoundedMachine.TestCase
TestB1303BoundedSuccessor.settings = settings(
    max_examples=16, stateful_step_count=16, deadline=None,
    derandomize=True, database=None, phases=(Phase.generate,),
    report_multiple_bugs=False, print_blob=True,
)


def test_automatic_additive_successor_reaches_real_adapter():
    """Bridge the automatic producer, validated sink, worker and durable readback."""
    class AutomaticPersisted(lineage.PersistedGraphLineageMachine):
        automatic = True

    machine = AutomaticPersisted()
    machine.control = True
    try:
        machine.accepted(True, 0)
        machine.freeze_parent()
        machine.admit()
        machine.result(True)
        machine.freeze_result()
        machine.recover()
        machine.duplicate()
        machine.conservation()
    except BaseException:
        machine.failed = True
        raise
    finally:
        machine.teardown()
