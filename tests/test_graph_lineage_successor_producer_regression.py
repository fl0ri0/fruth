"""Red contract regressions retained for a read-only runtime pilot.

The direct validated sink has positive controls in the sibling module. The
automatic producer must accept the same accepted duty through normal gates.
No xfail, discarded runtime diagnostics, or changed caller oracle hides C3.
"""
import os

from hypothesis import settings

from tests.test_graph_lineage_stateful_hypothesis import GraphLineageMachine
from tests.test_graph_lineage_stateful_hypothesis import PersistedGraphLineageMachine


class AutomaticSuccessorMachine(GraphLineageMachine):
    automatic = True


TestAutomaticSuccessorComposition = AutomaticSuccessorMachine.TestCase
TestAutomaticSuccessorComposition.settings = settings(
    max_examples=int(os.environ.get('FRUTH_LINEAGE_PRODUCER_EXAMPLES', '16')),
    stateful_step_count=6, deadline=None, print_blob=True, report_multiple_bugs=False)


def test_accepted_duty_survives_automatic_successor_production():
    """Smallest selected sequence: accept fixture -> freeze -> authorized admit."""
    machine = AutomaticSuccessorMachine()
    machine.control = True
    try:
        machine.accepted(False, 0)
        machine.freeze_parent()
        machine.admit()
        machine.conservation()
    except BaseException:
        machine.failed = True
        raise
    finally:
        machine.teardown()


def test_repeated_completed_callback_retains_accepted_result():
    """C4: a repeated same-key terminal callback cannot erase proven work."""
    machine = GraphLineageMachine()
    machine.control = True
    try:
        machine.accepted(False, 0)
        machine.freeze_parent()
        machine.admit()
        machine.result(True)
        machine.conservation()
        machine.stale_callback('completed')
        machine.conservation()
    except BaseException:
        machine.failed = True
        raise
    finally:
        machine.teardown()


def test_real_worker_repeated_callback_retains_accepted_result_after_recovery():
    machine = PersistedGraphLineageMachine()
    machine.control = True
    try:
        machine.accepted(False, 0)
        machine.freeze_parent()
        machine.admit()
        machine.result(True)
        machine.conservation()
        machine.stale_callback('completed')
        machine.freeze_result()
        machine.recover()
        machine.conservation()
    except BaseException:
        machine.failed = True
        raise
    finally:
        machine.teardown()
