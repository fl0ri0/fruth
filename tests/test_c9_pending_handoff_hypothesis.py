"""One bounded actual-child family; deterministic contract controls run first."""
from hypothesis import Phase, given, settings, strategies as st
from tests.test_c9_pending_handoff_contract import exercise_handoff

# Do not execute additional schedules during Hypothesis failure confirmation.
# The first reached witness is retained by the fixture; replay is a separate job.
_first_failure = None
_reached_examples = 0


@settings(max_examples=32, phases=(Phase.generate,), deadline=None,
          print_blob=True, report_multiple_bugs=False)
@given(control_wins=st.booleans(), reverse=st.booleans(),
       child_mode=st.sampled_from(['run', 'cancel', 'start_failure']),
       probes=st.integers(min_value=0, max_value=3), duplicate=st.booleans())
def test_bounded_actual_child_continuation(control_wins, reverse, child_mode, probes, duplicate):
    global _first_failure, _reached_examples
    if _first_failure is not None:
        raise _first_failure
    assert _reached_examples < 32
    _reached_examples += 1
    try:
        exercise_handoff(control_wins, reverse, child_mode, probes=probes, duplicate=duplicate)
    except BaseException as error:
        _first_failure = error
        raise
