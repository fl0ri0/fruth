"""Pure protocol/admission/cleanup checks; no PDF native imports or subprocesses."""
from dataclasses import asdict, replace
import hashlib
import io
import json
from pathlib import Path
import struct
import threading
import zlib
from unittest.mock import Mock

import pytest

from fruth_core import pdf_preparation as pdf
from fruth_core import file_inputs


def png(width=2, height=3):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress((b'\0' + b'\xff' * width * 3) * height)) + chunk(b'IEND', b''))


def result(root, *, operation='render', count=2):
    limits = pdf.PdfLimits()
    controls = {'max_pages': None, 'dpi': 72, 'max_image_side_px': 2400}
    if operation == 'text':
        controls = {'max_chars': None}
    request = dict(protocol=pdf.PROTOCOL, version=pdf.VERSION, invocation_id='fixture',
                   source_sha256='a' * 64, source_bytes=1, operation=operation, controls=controls,
                   limits=asdict(limits), deadline=123.0)
    directory = root / 'results'
    directory.mkdir()
    files = []
    for index in range(1 if operation == 'text' else count):
        name = 'text.txt' if operation == 'text' else f'page-{index:08d}.png'
        raw = 'héllo'.encode() if operation == 'text' else png()
        (directory / name).write_bytes(raw)
        files.append(dict(name=name, size_bytes=len(raw), sha256=pdf.digest_bytes(raw),
            page_index=None if operation == 'text' else index,
            width=None if operation == 'text' else 2, height=None if operation == 'text' else 3))
    manifest = {k: request[k] for k in ('protocol', 'version', 'invocation_id', 'source_sha256', 'operation', 'controls')}
    manifest.update(request_sha256=pdf.digest_bytes(pdf.json_bytes(request)), status='complete',
                    total_pages=count, selected_pages=list(range(count)), warnings=[], files=files)
    (directory / 'manifest.json').write_bytes(pdf.json_bytes(manifest))
    return request, limits, manifest


def publish(root, manifest):
    (root / 'results/manifest.json').write_bytes(pdf.json_bytes(manifest))


def test_complete_all_pages_and_empty_text_are_explicit(tmp_path):
    request, limits, manifest = result(tmp_path)
    loaded, total, warnings = pdf.accept_result(tmp_path, request, limits)
    assert len(loaded) == total == 2 and not warnings
    manifest.update(status='unreadable', selected_pages=[], files=[], warnings=['locked'])
    for path in (tmp_path/'results').glob('*.png'):
        path.unlink()
    publish(tmp_path, manifest)
    assert pdf.accept_result(tmp_path, request, limits) == ([], 2, ['locked'])


@pytest.mark.parametrize('fault', [
    'protocol', 'version', 'invocation_id', 'source_sha256', 'request_sha256', 'operation', 'controls',
    'incomplete', 'missing_field', 'extra_field', 'duplicate', 'missing_file', 'extra_file', 'path',
    'symlink', 'hardlink', 'directory', 'digest', 'length', 'dimension', 'page_binding',
    'page_order', 'omitted_page', 'huge_count', 'extra_page', 'corrupt_png', 'partial_png', 'extra_png',
    'result_limit', 'aggregate_limit', 'manifest_limit',
])
def test_reject_inconsistent_or_partial_result(tmp_path, fault):
    request, limits, m = result(tmp_path)
    path = tmp_path/'results/page-00000000.png'
    if fault in {'protocol', 'version', 'invocation_id', 'source_sha256', 'request_sha256', 'operation'}:
        m[fault] = 'wrong'
    elif fault == 'controls': m['controls'] = dict(m['controls'], dpi=73)
    elif fault == 'incomplete': m['status'] = 'partial'
    elif fault == 'missing_field': del m['warnings']
    elif fault == 'extra_field': m['extra'] = True
    elif fault == 'missing_file': path.unlink()
    elif fault == 'extra_file': (tmp_path/'results/extra').touch()
    elif fault == 'path': m['files'][0]['name'] = '../source.pdf'
    elif fault == 'symlink':
        path.unlink(); path.symlink_to(tmp_path/'results/page-00000001.png')
    elif fault == 'hardlink':
        path.unlink(); path.hardlink_to(tmp_path/'results/page-00000001.png')
    elif fault == 'directory': path.unlink(); path.mkdir()
    elif fault == 'digest': m['files'][0]['sha256'] = 'f' * 64
    elif fault == 'length': m['files'][0]['size_bytes'] += 1
    elif fault == 'dimension': m['files'][0]['width'] += 1
    elif fault == 'page_binding': m['files'][0]['page_index'] = 1
    elif fault == 'page_order': m['selected_pages'].reverse()
    elif fault == 'omitted_page': m['selected_pages'].pop()
    elif fault == 'huge_count': m['total_pages'] = 10**30
    elif fault == 'extra_page': m['selected_pages'].append(2)
    elif fault in {'corrupt_png', 'partial_png', 'extra_png'}:
        raw = path.read_bytes()
        raw = raw[:35] + b'X' + raw[36:] if fault == 'corrupt_png' else raw[:-3] if fault == 'partial_png' else raw + b'X'
        path.write_bytes(raw)
        m['files'][0].update(size_bytes=len(raw), sha256=pdf.digest_bytes(raw))
    elif fault == 'result_limit': limits = replace(limits, result_bytes=1)
    elif fault == 'aggregate_limit': limits = replace(limits, output_bytes=path.stat().st_size)
    publish(tmp_path, m)
    if fault == 'duplicate':
        raw = (tmp_path/'results/manifest.json').read_text()
        (tmp_path/'results/manifest.json').write_text(raw[:-1] + ',"version":1}')
    if fault == 'manifest_limit':
        (tmp_path/'results/manifest.json').write_bytes(b' ' * (pdf.MAX_MANIFEST_BYTES + 1))
    with pytest.raises((ValueError, OSError, TypeError)):
        pdf.accept_result(tmp_path, request, limits)


def test_text_character_and_byte_limits_and_utf8(tmp_path):
    request, limits, m = result(tmp_path, operation='text')
    assert pdf.accept_result(tmp_path, request, limits)[0] == ['héllo']
    with pytest.raises(ValueError):
        pdf.accept_result(tmp_path, request, replace(limits, text_bytes=2))
    request['controls']['max_chars'] = 2
    m['controls'] = request['controls']; m['request_sha256'] = pdf.digest_bytes(pdf.json_bytes(request))
    publish(tmp_path, m)
    with pytest.raises(ValueError, match='character'):
        pdf.accept_result(tmp_path, request, limits)


def test_cancel_before_admission_and_before_acceptance(tmp_path, monkeypatch):
    launch = Mock(side_effect=AssertionError('must not launch'))
    monkeypatch.setattr(pdf.subprocess, 'Popen', launch)
    worker = pdf.PdfPreparation(pdf.PdfLimits(admission_timeout_sec=.02))
    with pdf.pdf_cancellation_scope(lambda: True), pytest.raises(pdf.PdfPreparationError, match='cancelled'):
        worker.run(tmp_path/'unused', 'text', {'max_chars': None})
    request, limits, _ = result(tmp_path)
    with pdf.pdf_cancellation_scope(lambda: True), pytest.raises(pdf.PdfPreparationError, match='cancelled'):
        pdf.accept_result(tmp_path, request, limits)
    assert worker.capacity.acquire(blocking=False)
    with pytest.raises(pdf.PdfPreparationError) as failure:
        worker.run(tmp_path/'unused', 'text', {'max_chars': None})
    assert failure.value.code == 'PDF_PREPARATION_BUSY'
    worker.capacity.release()
    launch.assert_not_called()


def test_input_limit_before_launch_and_capacity_recovery(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf.tempfile, 'tempdir', str(tmp_path))
    launch = Mock(side_effect=AssertionError('must not parse'))
    monkeypatch.setattr(pdf.subprocess, 'Popen', launch)
    source = tmp_path/'source.pdf'; source.write_bytes(b'two')
    worker = pdf.PdfPreparation(pdf.PdfLimits(input_bytes=2))
    with pytest.raises(pdf.PdfPreparationError) as failure:
        worker.run(source, 'text', {'max_chars': None})
    assert failure.value.code == 'PDF_PREPARATION_LIMIT'
    assert not list(tmp_path.glob('fruth-pdf-*'))
    assert worker.capacity.acquire(blocking=False)
    launch.assert_not_called()


def test_deadline_during_result_validation(tmp_path):
    request, limits, _ = result(tmp_path)
    with pytest.raises(pdf.PdfPreparationError) as failure:
        pdf.accept_result(tmp_path, request, limits, deadline=0)
    assert failure.value.code == 'PDF_PREPARATION_TIMEOUT'


@pytest.mark.parametrize('kind', ['upload', 'local'])
def test_failed_copy_unlinks_only_owned_temporary(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(file_inputs.tempfile, 'tempdir', str(tmp_path))
    original = tmp_path/'original.pdf'; original.write_bytes(b'original')
    def partial(source, target):
        Path(target).write_bytes(b'partial')
        raise OSError('controlled copy failure')
    with pytest.raises(OSError, match='controlled'):
        if kind == 'local':
            monkeypatch.setattr(file_inputs.shutil, 'copy2', partial)
            file_inputs.save_local_path_to_temp(str(original))
        else:
            upload = Mock(filename='upload.pdf', save=lambda target: partial(None, target))
            file_inputs.save_upload_to_temp(upload)
    assert original.read_bytes() == b'original'
    assert sorted(p.name for p in tmp_path.iterdir()) == ['original.pdf']


def test_bounded_scanline_validation_and_invalid_compressed_bytes(tmp_path):
    request, limits, m = result(tmp_path, count=1)
    path = tmp_path/'results/page-00000000.png'
    raw = png(width=900, height=900)  # > 1 MiB expanded, small compressed fixture.
    path.write_bytes(raw)
    m['files'][0].update(size_bytes=len(raw), sha256=pdf.digest_bytes(raw), width=900, height=900)
    publish(tmp_path, m)
    assert len(pdf.accept_result(tmp_path, request, limits)[0]) == 1
    # CRC/digest-consistent garbage must still not count as complete PNG data.
    raw = bytearray(raw)
    length = struct.unpack('>I', raw[33:37])[0]
    raw[41:41+length] = b'X' * length
    raw[41+length:45+length] = struct.pack('>I', zlib.crc32(raw[37:41+length]))
    path.write_bytes(raw)
    m['files'][0]['sha256'] = pdf.digest_bytes(raw); publish(tmp_path, m)
    with pytest.raises((ValueError, zlib.error)):
        pdf.accept_result(tmp_path, request, limits)


def test_unconfirmed_cleanup_retains_capacity_and_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf.tempfile, 'tempdir', str(tmp_path))
    source = tmp_path/'source.pdf'; source.write_bytes(b'synthetic')
    process = Mock(returncode=1, stdin=io.BytesIO())
    process.poll.return_value = 1
    process.wait.return_value = 1
    monkeypatch.setattr(pdf.subprocess, 'Popen', Mock(return_value=process))
    worker = pdf.PdfPreparation(pdf.PdfLimits(admission_timeout_sec=.01))
    with pytest.raises(pdf.PdfPreparationError) as failure:
        worker.run(source, 'text', {'max_chars': None})
    assert failure.value.code == 'PDF_PREPARATION_CLEANUP_UNCONFIRMED'
    assert len(list(tmp_path.glob('fruth-pdf-*'))) == 1
    assert not worker.capacity.acquire(blocking=False)


@pytest.mark.parametrize('role', ['supervise', 'worker', 'anchor'])
def test_child_entrypoints_still_reject_aliased_workspaces(tmp_path, monkeypatch, role):
    from fruth_core import pdf_worker
    physical = tmp_path/'physical'; physical.mkdir()
    alias = tmp_path/'alias'; alias.symlink_to(physical, target_is_directory=True)
    monkeypatch.setattr(pdf_worker.sys, 'argv', ['pdf_worker.py', role, str(alias)])
    with pytest.raises(SystemExit, match='physical absolute directory'):
        pdf_worker.main()
    assert not list(physical.iterdir())


def test_late_fill_scope_uses_current_exact_branch_controls(tmp_path, monkeypatch):
    from fruth_webserver import _LATE_FILL_RUNTIME as owner
    state = {'late_fill': {'branch_controls': []}}
    monkeypatch.setattr(owner, 'get_response_lookup_record', lambda rid: {'response_payload': state})
    checked = []
    class Finished(Exception):
        pass
    def invoke(**kwargs):
        pdf.check_cancelled(); checked.append('allowed')
        state['late_fill']['branch_controls'] = [dict(branch_id='different', action='cancelled')]
        pdf.check_cancelled(); checked.append('sibling allowed')
        state['late_fill']['branch_controls'] = [dict(branch_id='pdf-branch', action='cancelled', authority='user')]
        with pytest.raises(pdf.PdfPreparationError) as failure:
            pdf.check_cancelled()
        assert failure.value.code == 'PDF_PREPARATION_CANCELLED'
        checked.append('cancelled')
        raise Finished()
    monkeypatch.setattr(owner, 'invoke_internal_api_json_route', invoke)
    with pytest.raises(Finished):
        owner.execute_prepared_late_fill_branch(dict(response_id='fixture', branch_id='pdf-branch',
            phase_id='pdf-phase', capability='chat', instance={'instance_id': 'fake', 'model': 'fake'},
            infer_payload={'prompt': 'read synthetic PDF'}))
    assert checked == ['allowed', 'sibling allowed', 'cancelled']
    pdf.check_cancelled()  # No authority leaks out of the trusted dynamic scope.


def test_many_pages_do_not_hold_one_open_descriptor_per_page(tmp_path, monkeypatch):
    from contextlib import contextmanager
    request, limits, _ = result(tmp_path, count=300)
    original = pdf.open_regular
    live = peak = 0
    @contextmanager
    def tracked(path):
        nonlocal live, peak
        with original(path) as stream:
            live += 1; peak = max(peak, live)
            try:
                yield stream
            finally:
                live -= 1
    monkeypatch.setattr(pdf, 'open_regular', tracked)
    assert len(pdf.accept_result(tmp_path, request, limits)[0]) == 300
    assert peak == 1 and live == 0


def test_output_change_between_validation_and_loading_is_rejected(tmp_path, monkeypatch):
    request, limits, _ = result(tmp_path, count=1)
    original = pdf.open_regular
    calls = 0
    def changed(path):
        nonlocal calls
        if path.suffix == '.png':
            calls += 1
            if calls == 2:
                path.write_bytes(png(width=3, height=2))
        return original(path)
    monkeypatch.setattr(pdf, 'open_regular', changed)
    with pytest.raises(ValueError, match='changed after validation'):
        pdf.accept_result(tmp_path, request, limits)


@pytest.mark.parametrize('late_fill', [False, True])
def test_preparation_error_survives_materialization_without_provider_repair(monkeypatch, late_fill):
    import fruth_webserver as web
    from fruth_server.multi_materialization_runtime import _exception_error_payload
    payload = dict(error='PDF deadline exceeded', pdf_preparation=dict(status='failed',
        code='PDF_PREPARATION_TIMEOUT', operation='render'), pdf_total_pages=3, pdf_processed_pages=1)
    monkeypatch.setattr(web, '_invoke_internal_api_json_route', lambda **kw: (payload, 504))
    owner = web._LATE_FILL_RUNTIME if late_fill else web._RESPONSES_REQUEST_RUNTIME
    function = owner.execute_prepared_late_fill_branch if late_fill else owner.execute_prepared_materialization_branch
    with pytest.raises(pdf.PdfPreparationError) as failure:
        function(dict(branch_id='pdf', phase_id='pdf', capability='vision_analysis',
            instance={'instance_id': 'fake'}, infer_payload={'prompt': 'read'}, response_id='fixture'))
    error = _exception_error_payload(failure.value, stage='execute_prepared_branch')
    assert error['code'] == 'PDF_PREPARATION_TIMEOUT' and error['retryable'] is False
    assert error['status_code'] == 504 and error['pdf_processed_pages'] == 1
    normalized = web._LATE_FILL_RUNTIME.normalize_late_fill_error_payload(error)
    assert normalized['pdf_preparation'] == payload['pdf_preparation']
    recovery = web._LATE_FILL_RUNTIME.late_fill_recovery_context(error=normalized, attempt={})
    assert recovery['can_retry'] is False
