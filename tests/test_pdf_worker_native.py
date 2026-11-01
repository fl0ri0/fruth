"""Real owned-process checks. Run via tests/pdf_native_runner.py only."""
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from fruth_core import pdf_preparation as pdf
from tests.pdf_worker_fixture import FixturePreparation, command
from tests.test_ocr_pdf import write_pdf


def until(predicate, seconds=5):
    deadline = time.monotonic() + seconds
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError('Disposable process condition did not complete')
        time.sleep(.02)


def absent(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


def assert_reaped(evidence):
    identity = json.loads((evidence/'identity.json').read_text())
    receipt = json.loads((evidence/'supervisor.json').read_text())
    assert receipt['invocation_id'] == identity['invocation_id']
    assert receipt['reaped'] and receipt['group_cleaned']
    for key in ('supervisor', 'anchor', 'worker'):
        until(lambda: absent(identity[key]))
    if (evidence/'descendant.json').exists():
        pid = json.loads((evidence/'descendant.json').read_text())['pid']
        until(lambda: absent(pid))
        path = evidence/'writes.txt'
        length = path.stat().st_size if path.exists() else 0
        time.sleep(.06)
        assert (path.stat().st_size if path.exists() else 0) == length
    if (evidence/'scratch.json').exists():
        path = Path(json.loads((evidence/'scratch.json').read_text())['path'])
        workspace = Path((evidence/'workspace.txt').read_text())
        assert path.parent == workspace/'scratch'
        until(lambda: not path.exists())
    return receipt


@pytest.mark.parametrize('mode,code', [('exception', 'PDF_PREPARATION_FAILED'),
    ('exit', 'PDF_PREPARATION_FAILED'), ('partial', 'PDF_PREPARATION_INVALID_RESULT'),
    ('hang', 'PDF_PREPARATION_TIMEOUT'), ('descendant', 'PDF_PREPARATION_TIMEOUT')])
def test_controlled_faults_are_contained_reaped_and_never_accepted(tmp_path, mode, code):
    source = tmp_path/'source.pdf'; source.write_bytes(b'synthetic')
    evidence = tmp_path/'evidence'; evidence.mkdir()
    worker = FixturePreparation(pdf.PdfLimits(timeout_sec=.8), mode, evidence)
    started = time.monotonic()
    with pytest.raises(pdf.PdfPreparationError) as failure:
        worker.run(source, 'text', {'max_chars': None})
    assert failure.value.code == code
    assert time.monotonic() - started < 5
    receipt = assert_reaped(evidence)
    if mode in {'hang', 'descendant'}:
        assert receipt['signals'] == ['TERM', 'KILL'] and receipt['worker_exit'] == -9
    workspace = Path((evidence/'workspace.txt').read_text())
    assert not workspace.exists()
    assert worker.capacity.acquire(blocking=False)
    worker.capacity.release()


def test_cancel_during_gil_held_work_and_shared_saturation(tmp_path):
    source = tmp_path/'source.pdf'; source.write_bytes(b'synthetic')
    evidence = tmp_path/'evidence'; evidence.mkdir()
    worker = FixturePreparation(pdf.PdfLimits(timeout_sec=5, admission_timeout_sec=.08), 'hang', evidence)
    cancelled = threading.Event()
    failures = []
    def run():
        with pdf.pdf_cancellation_scope(cancelled.is_set):
            try:
                worker.run(source, 'text', {'max_chars': None})
            except BaseException as exc:
                failures.append(exc)
    thread = threading.Thread(target=run)
    thread.start()
    until(lambda: (evidence/'ready').exists())
    with pytest.raises(pdf.PdfPreparationError) as failure:
        worker.run(source, 'text', {'max_chars': None})
    assert failure.value.code == 'PDF_PREPARATION_BUSY'
    cancelled.set()
    thread.join(timeout=5)
    assert not thread.is_alive() and len(failures) == 1
    assert failures[0].code == 'PDF_PREPARATION_CANCELLED'
    assert_reaped(evidence)
    assert worker.capacity.acquire(blocking=False)
    worker.capacity.release()
    # Same owner's capacity can execute a fresh, real native job after cleanup.
    worker._supervisor_command = pdf.PdfPreparation._supervisor_command.__get__(worker)
    path = write_pdf(tmp_path/'recovery.pdf')
    assert worker.run(path, 'text', {'max_chars': None})[0] == ['Page 1']


def test_actual_parent_exit_stops_owned_descendant_and_preserves_foreign(tmp_path):
    evidence = tmp_path/'caller'; evidence.mkdir()
    foreign_dir = tmp_path/'foreign'; foreign_dir.mkdir()
    foreign = subprocess.Popen(command('foreign', foreign_dir, 'foreign'), stdin=subprocess.DEVNULL)
    caller = subprocess.Popen(command('caller', evidence, 'descendant'), stdin=subprocess.DEVNULL)
    try:
        until(lambda: (evidence/'descendant.json').exists() and (evidence/'ready').exists())
        caller.kill()
        assert caller.wait(timeout=3) == -9
        until(lambda: (evidence/'supervisor.json').exists())
        receipt = assert_reaped(evidence)
        assert receipt['reason'] == 'parent_disappeared'
        workspace = Path((evidence/'workspace.txt').read_text())
        until(lambda: not workspace.exists())
        assert foreign.poll() is None
    finally:
        if caller.poll() is None:
            caller.kill()
        caller.wait(timeout=3)
        foreign.terminate(); foreign.wait(timeout=3)


@pytest.mark.parametrize('limits,operation,controls', [
    (pdf.PdfLimits(text_bytes=2), 'text', {'max_chars': None}),
    (pdf.PdfLimits(result_bytes=8), 'render', {'max_pages': None, 'dpi': 72, 'max_image_side_px': 2400}),
    (pdf.PdfLimits(output_bytes=8), 'render', {'max_pages': None, 'dpi': 72, 'max_image_side_px': 2400}),
])
def test_tiny_real_production_output_budgets_fail_without_partial_acceptance(tmp_path, limits, operation, controls):
    path = write_pdf(tmp_path/'source.pdf', rotations=(0, 90))
    worker = pdf.PdfPreparation(replace(limits, timeout_sec=5))
    with pytest.raises(pdf.PdfPreparationError) as failure:
        worker.run(path, operation, controls)
    assert failure.value.code == 'PDF_PREPARATION_LIMIT'
    assert worker.capacity.acquire(blocking=False)


def test_cancel_after_real_worker_exit_before_acceptance(tmp_path):
    path = write_pdf(tmp_path/'source.pdf')
    cancelled = threading.Event()
    worker = pdf.PdfPreparation(pdf.PdfLimits(timeout_sec=5))
    finish = worker._finish
    def cancel_after_exit(*args):
        receipt = finish(*args)
        cancelled.set()
        return receipt
    worker._finish = cancel_after_exit
    with pdf.pdf_cancellation_scope(cancelled.is_set), pytest.raises(pdf.PdfPreparationError) as failure:
        worker.run(path, 'text', {'max_chars': None})
    assert failure.value.code == 'PDF_PREPARATION_CANCELLED'
    assert worker.capacity.acquire(blocking=False)


@pytest.mark.parametrize('operation,controls', [
    ('text', {'max_chars': None}),
    ('render', {'max_pages': None, 'dpi': 72, 'max_image_side_px': 2400}),
    ('page', {'page_index': 1, 'dpi': 72, 'max_image_side_px': 2400, 'crop_margin_ratio': .04}),
])
def test_fresh_native_worker_identity_imports_and_small_fixture_measurement(tmp_path, operation, controls):
    source = write_pdf(tmp_path/'source.pdf', rotations=(0, 90), mixed=True)
    evidence = tmp_path/'evidence'; evidence.mkdir()
    worker = FixturePreparation(pdf.PdfLimits(timeout_sec=5), 'native-proof', evidence)
    started = time.monotonic()
    loaded, total, warnings = worker.run(source, operation, controls)
    elapsed = time.monotonic() - started
    assert total == 2 and len(loaded) == (2 if operation == 'render' else 1)
    imports = json.loads((evidence/'imports.json').read_text())
    workspace = Path((evidence/'workspace.txt').read_text())
    assert imports == {'webserver_imported': False, 'pdf_library_imported': True,
                       'cwd': str(workspace), 'temporary': str(workspace/'scratch')}
    receipt = assert_reaped(evidence)
    assert receipt['child_max_rss_bytes'] > 0
    (evidence/'measurement.json').write_text(json.dumps(dict(operation=operation,
        elapsed_seconds=elapsed, child_max_rss_bytes=receipt['child_max_rss_bytes'],
        source_bytes=source.stat().st_size, accepted_string_lengths=list(map(len, loaded)))))


@pytest.mark.parametrize('operation,controls', [
    ('text', {'max_chars': None}),
    ('render', {'max_pages': None, 'dpi': 72, 'max_image_side_px': 2400}),
    ('page', {'page_index': 1, 'dpi': 72, 'max_image_side_px': 2400, 'crop_margin_ratio': 0}),
])
def test_aliased_temporary_root_runs_real_worker_and_reuses_capacity(tmp_path, monkeypatch, operation, controls):
    physical = tmp_path/'physical'; physical.mkdir()
    alias = tmp_path/'temporary-alias'; alias.symlink_to(physical, target_is_directory=True)
    monkeypatch.setattr(pdf.tempfile, 'tempdir', str(alias))
    source = write_pdf(tmp_path/'source.pdf', rotations=(0, 90), mixed=True)

    class ObservedPreparation(pdf.PdfPreparation):
        def _supervisor_command(self, directory):
            (self.evidence/'workspace.txt').write_text(str(directory))
            return super()._supervisor_command(directory)

        def _finish(self, process, directory, invocation):
            receipt = super()._finish(process, directory, invocation)
            for name in ('identity.json', 'supervisor.json'):
                (self.evidence/name).write_bytes((directory/name).read_bytes())
            return receipt

    worker = ObservedPreparation(pdf.PdfLimits(timeout_sec=5, admission_timeout_sec=.08))
    for attempt in range(2):
        worker.evidence = tmp_path/f'evidence-{attempt}'; worker.evidence.mkdir()
        loaded, total, warnings = worker.run(source, operation, controls)
        assert total == 2 and len(loaded) == (2 if operation == 'render' else 1)
        if operation == 'text':
            assert loaded == ['Page 1'] and warnings
        else:
            assert all(loaded) and not warnings
        workspace = Path((worker.evidence/'workspace.txt').read_text())
        assert workspace == workspace.resolve() and workspace.parent == physical.resolve()
        receipt = assert_reaped(worker.evidence)
        assert receipt['reason'] == 'worker_exit' and receipt['worker_exit'] == 0
        assert not workspace.exists() and not list(physical.iterdir())
        assert worker.capacity.acquire(blocking=False)
        worker.capacity.release()
    assert alias.is_symlink() and source.is_file()
