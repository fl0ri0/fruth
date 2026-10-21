"""C9 corrected-source checks; retained study and semantic oracle are unchanged.

Only scheduling adapts: old seams now inside a mutation section are observed but
not paused. Holding such a seam while demanding the other actor acquire that
same lock would test a fixture deadlock. The production synchronization always
runs. Original inputs and assertions remain in their original modules.
"""
from contextlib import contextmanager
from copy import deepcopy
import os
import threading
from unittest.mock import patch

from hypothesis import Phase, given, settings, strategies as st
from hypothesis.errors import DidNotReproduce
import pytest

import fruth_webserver as web
from fruth_server.responses_runtime import ResponseMutationConflict, require_response_mutation_base
from tests import test_late_fill_control_overlap_hypothesis as original
from tests.test_late_fill_control_overlap_regression import ORIGINAL_CHOICES, test_original_overlap_failure_blob as original_blob


@contextmanager
def current_scheduling():
    owner = web._RESPONSES_RUNTIME
    mutation, gate = owner.response_mutation, original.Progress.gate
    local = threading.local()

    @contextmanager
    def section(response_id):
        with mutation(response_id):
            local.depth = getattr(local, 'depth', 0) + 1
            try:
                yield
            finally:
                local.depth -= 1

    def schedule(progress, actor, boundary):
        if getattr(local, 'depth', 0):
            progress.record('test_only_seam_observed_without_pause', actor,
                            boundary=boundary, reason='inside_response_mutation')
            return
        return gate(progress, actor, boundary)

    with patch.object(owner, 'response_mutation', section), patch.object(original.Progress, 'gate', schedule):
        yield
    assert not owner._mutation_locks, 'response mutation lock entries leaked'


def test_original_explicit_schedule():
    with current_scheduling():
        original.run_schedule(ORIGINAL_CHOICES, reverse=True)


def test_original_blob_no_longer_reproduces():
    with current_scheduling(), pytest.raises(DidNotReproduce):
        original_blob()


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('boundary', ['provider_reply', 'materialized_before_acceptance_read', 'post_read_before_gate', 'post_gate_before_acceptance'])
def test_admitted_control_at_original_boundaries(reverse, boundary):
    with current_scheduling():
        study = original.OverlapStudy(reverse)
        try:
            study.source_inputs.update(c9_boundary=boundary, adaptation='atomic_publication_seams_observed')
            study.start()
            study.progress.step('worker')
            assert study.progress.waiting['worker'][0] == 'provider_reply'
            study.progress.step('control')
            assert study.progress.waiting['control'][0] == 'after_lookup'
            while study.progress.waiting['worker'][0] != boundary:
                study.progress.step('worker')
            study.drain('control')
            status = study.control_result['status_code']
            # The current target is revalidated at commit. A provider-completed
            # progress event removed active/pending work, so this stale admission
            # conflicts instead of acknowledging a cancellation it cannot own.
            assert status == (200 if boundary == 'provider_reply' else 409)
            if status == 200:
                study.check_value(study.recover('cancel_ack_before_worker_release'), cancelled=True)
                assert study.control_result['body']['control']['branch_ids'] == [study.target]
            else:
                assert study.control_result['body']['error']['code'] == 'response_mutation_conflict'
            study.drain('worker')
            value = study.check()
            assert len(list(study.engine.harness.images_dir.rglob('*.png'))) == 2, 'diagnostic output removed'
            if status == 200:
                study.check_value(value, cancelled=True)
            else:
                assert any(r.get('branch_id') == study.target for r in value['late_fill']['fill_results'])
        except BaseException:
            study.failed = True
            raise
        finally:
            study.close()


@pytest.mark.parametrize('reverse', [False, True])
def test_completion_wins_against_previously_admitted_control(reverse):
    with current_scheduling():
        study = original.OverlapStudy(reverse)
        try:
            study.source_inputs['c9_order'] = 'accepted_completion_before_stale_control_commit'
            study.start()
            study.progress.step('worker')
            study.progress.step('control')
            study.drain('worker')
            accepted = study.recover('worker_commit_before_control_release')
            assert any(r.get('branch_id') == study.target for r in accepted['late_fill']['fill_results'])
            study.drain('control')
            assert study.control_result['status_code'] == 409
            study.check()
        except BaseException:
            study.failed = True
            raise
        finally:
            study.close()


@pytest.mark.parametrize('order', ['worker_first', 'control_first', 'no_control', 'overlap_before_read'])
def test_retained_serial_controls(order):
    with current_scheduling():
        original.test_serial_and_overlap_controls(order)


def test_retained_oracle_sensitivity():
    with current_scheduling():
        original.test_oracle_detects_observed_sibling_loss()


@settings(max_examples=min(32, int(os.environ.get('FRUTH_HYPOTHESIS_ADAPTER', '32'))),
          phases=(Phase.generate,), deadline=None, print_blob=True, report_multiple_bugs=False)
@given(choices=st.lists(st.booleans(), min_size=32, max_size=32), reverse=st.booleans())
def test_bounded_corrected_control_worker_schedules(choices, reverse):
    with current_scheduling():
        original.run_schedule(choices, reverse)


def test_response_lock_is_independent_reentrant_and_released_after_error():
    owner = web._RESPONSES_RUNTIME
    finished = threading.Event()
    errors = []
    def other():
        try:
            with owner.response_mutation('c9-independent'):
                finished.set()
        except BaseException as exc:
            errors.append(exc)
    with pytest.raises(RuntimeError, match='test-only'):
        with owner.response_mutation('c9-held'):
            with owner.response_mutation('c9-held'):
                worker = threading.Thread(target=other)
                worker.start()
                assert finished.wait(5), 'unrelated response serialized'
                worker.join(5)
                assert not worker.is_alive() and not errors
            raise RuntimeError('test-only')
    assert not owner._mutation_locks


@pytest.mark.parametrize('change', ['frame_id', 'frame_sequence', 'execution', 'control', 'terminal'])
def test_current_version_and_disposition_reject_stale_candidates(change):
    before = {'id': 'c9', 'response_frame': {'frame_id': 'c9:frame-1', 'frame_sequence': 1},
              'late_fill': {'successor_reopen_execution': {'successor_execution_key': 'one'}}}
    after = deepcopy(before)
    if change in {'frame_id', 'frame_sequence'}:
        after['response_frame'][change] = 'c9:frame-2' if change == 'frame_id' else 2
    elif change == 'execution':
        after['late_fill']['successor_reopen_execution']['successor_execution_key'] = 'two'
    else:
        after['late_fill']['branch_controls' if change == 'control' else 'cancelled_branches'] = [
            {'branch_id': 'target', 'status': 'cancelled'}]
    with pytest.raises(ResponseMutationConflict):
        require_response_mutation_base(before, after)


@pytest.mark.parametrize('field,value', [('branch_id', 'foreign'), ('phase_id', 'foreign'),
                                        ('phase_id', None), ('obligation_id', 'foreign')])
def test_publication_rechecks_exact_target(field, value):
    from fruth_server.responses_runtime import require_response_mutation_target
    target = {'branch_id': 'target', 'phase_id': 'phase-target', 'capability': 'image_generation',
              'obligation_id': 'owed-target'}
    current = {'late_fill': {'pending_branches': [deepcopy(target)]}}
    require_response_mutation_target(target, current)
    target[field] = value
    with pytest.raises(ResponseMutationConflict):
        require_response_mutation_target(target, current)


def test_cancellation_oracle_remains_sensitive():
    with current_scheduling():
        study = original.OverlapStudy()
        try:
            study.start()
            study.drain('control')
            study.drain('worker')
            final = study.check()
            bad = deepcopy(final)
            bad['late_fill']['cancelled_branches'] = []
            with pytest.raises(AssertionError, match='committed cancellation silently undone'):
                study.check_value(bad, cancelled=True)
            study.progress.record('test_only_fault_detected', fault='drop_cancellation')
        except BaseException:
            study.failed = True
            raise
        finally:
            study.close()
