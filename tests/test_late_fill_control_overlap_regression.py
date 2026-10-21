"""Retained red witness and bounded schedule reduction for the overlap pilot.

Runtime is intentionally unchanged. Diagnostic reduction catches the known
assertion; the exact replay and deterministic regression retain real failures.
"""
from hypothesis import reproduce_failure
import pytest

from tests.test_late_fill_control_overlap_hypothesis import (
    OverlapStudy, run_schedule, test_bounded_control_worker_schedules as generated,
)


# Exactly 32 choices, as printed by the original Hypothesis failure.
ORIGINAL_CHOICES = (
    True, False, True, False, False, True, True, False,
    True, True, False, True, False, True, False, False,
    True, True, True, False, False, True, False, False,
    False, False, False, False, False, False, True, False,
)


def test_original_overlap_failure_blob():
    reproduce_failure('6.168.5', b'AXicY2RgZGBgZAQjCBNEMEABUAgAATMADw==')(generated)()


def test_original_explicit_schedule():
    run_schedule(ORIGINAL_CHOICES, reverse=True)


def test_original_consumed_prefix_reduction():
    # The original actors completed after eleven releases. The remaining 21
    # generated choices were never consumed; preserve that fact explicitly.
    with pytest.raises(AssertionError) as failure:
        run_schedule(ORIGINAL_CHOICES[:11], reverse=True)
    assert str(failure.value).splitlines()[0] == 'committed cancellation silently undone'


def execute_reduced(study, boundary):
    study.source_inputs.update(reduction='control_reads_active_worker_before_materialization', boundary=boundary)
    study.start()
    study.progress.step('worker')
    assert study.progress.waiting['worker'][0] == 'provider_reply'
    study.progress.step('control')
    assert study.progress.waiting['control'][0] == 'after_lookup'
    for _ in range(7):
        if study.progress.waiting['worker'][0] == boundary:
            break
        study.progress.step('worker')
    assert study.progress.waiting['worker'][0] == boundary
    # Control reads active work during the provider call. It commits at the
    # selected later seam. Starting a new request after materialization instead
    # legitimately returns 404 because progress has removed pending/active work;
    # that attempted reduction is not a reachable admitted cancellation.
    study.drain('control')
    assert study.control_result['status_code'] == 200
    assert study.commits[-1]['actor'] == 'control'
    study.check_value(study.commits[-1]['payload'], cancelled=True)
    study.drain('worker')


@pytest.mark.parametrize('reverse', [False, True])
def test_committed_cancel_after_worker_read_cannot_be_undone(reverse):
    study = OverlapStudy(reverse)
    try:
        execute_reduced(study, 'post_read_before_gate')
        study.check()
    except BaseException:
        study.failed = True
        raise
    finally:
        study.close()


@pytest.mark.parametrize('boundary,expected_red', [
    ('provider_reply', False),
    ('materialized_before_acceptance_read', False),
    ('post_read_before_gate', True),
])
def test_bounded_boundary_reduction(boundary, expected_red):
    study = OverlapStudy(reverse=True)
    detected = False
    try:
        execute_reduced(study, boundary)
        try:
            study.check()
        except AssertionError as exc:
            assert str(exc).splitlines()[0] == 'committed cancellation silently undone', 'different reduction failure'
            detected = True
            study.failed = True  # preserve complete red evidence, despite diagnostic catch
        study.source_inputs['known_failure_detected'] = detected
        assert detected == expected_red
    finally:
        study.close()
