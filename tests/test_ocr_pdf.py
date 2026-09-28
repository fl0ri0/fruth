"""Synthetic PDF checks: no inference, user documents or persistent artifacts."""

import base64
import struct
import sys
from unittest.mock import patch

import pytest
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject, DecodedStreamObject, DictionaryObject, FloatObject,
    NameObject, NumberObject, RectangleObject,
)

from fruth_core import ocr_pdf


def write_pdf(path, *, rotations=(0,), scanned=False, mixed=False,
              crop=(40, 60, 240, 360), media=(-20, -10, 300, 420), annotation=False):
    writer = PdfWriter()
    for index, rotation in enumerate(rotations):
        page = writer.add_blank_page(width=300, height=400)
        page.mediabox = RectangleObject(media)
        page.cropbox = RectangleObject(crop)
        page.rotation = rotation
        x, y, right, top = crop
        width, height = right - x, top - y
        contents = (
            f'1 0 0 rg {x} {y} 40 40 re f '
            f'0 1 0 rg {right - 40} {y} 40 40 re f '
            f'0 0 1 rg {x} {top - 40} 40 40 re f '
            f'1 1 0 rg {right - 40} {top - 40} 40 40 re f '
        )
        if scanned or (mixed and index == 1):
            # A real image XObject without any text layer.
            image = DecodedStreamObject()
            image.set_data(bytes([32, 64, 128] * 4))
            image.update({
                NameObject('/Type'): NameObject('/XObject'),
                NameObject('/Subtype'): NameObject('/Image'),
                NameObject('/Width'): NumberObject(2),
                NameObject('/Height'): NumberObject(2),
                NameObject('/BitsPerComponent'): NumberObject(8),
                NameObject('/ColorSpace'): NameObject('/DeviceRGB'),
            })
            page[NameObject('/Resources')] = DictionaryObject({
                NameObject('/XObject'): DictionaryObject({NameObject('/Scan'): writer._add_object(image)}),
            })
            contents += f'q 40 0 0 40 {x + width / 2 - 20} {y + height / 2 - 20} cm /Scan Do Q'
        else:
            font = DictionaryObject({
                NameObject('/Type'): NameObject('/Font'),
                NameObject('/Subtype'): NameObject('/Type1'),
                NameObject('/BaseFont'): NameObject('/Helvetica'),
            })
            page[NameObject('/Resources')] = DictionaryObject({
                NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)}),
            })
            contents += f'0 0 0 rg BT /F1 16 Tf {x + 50} {y + 80} Td (Page {index + 1}) Tj ET'
        stream = DecodedStreamObject()
        stream.set_data(contents.encode('ascii'))
        page[NameObject('/Contents')] = writer._add_object(stream)
        if annotation:
            appearance = DecodedStreamObject()
            appearance.set_data(b'1 0 1 rg 0 0 30 30 re f')
            appearance.update({
                NameObject('/Type'): NameObject('/XObject'),
                NameObject('/Subtype'): NameObject('/Form'),
                NameObject('/BBox'): RectangleObject((0, 0, 30, 30)),
                NameObject('/Resources'): DictionaryObject(),
            })
            annot = DictionaryObject({
                NameObject('/Type'): NameObject('/Annot'),
                NameObject('/Subtype'): NameObject('/Square'),
                NameObject('/Rect'): RectangleObject((x + 85, y + 135, x + 115, y + 165)),
                NameObject('/F'): NumberObject(4),
                NameObject('/C'): ArrayObject([FloatObject(1), FloatObject(0), FloatObject(1)]),
                NameObject('/IC'): ArrayObject([FloatObject(1), FloatObject(0), FloatObject(1)]),
                NameObject('/AP'): DictionaryObject({NameObject('/N'): writer._add_object(appearance)}),
            })
            page[NameObject('/Annots')] = ArrayObject([writer._add_object(annot)])
    writer.write(path)
    return path


@pytest.fixture
def native():
    if sys.platform != 'darwin':
        pytest.skip('Native PDF rendering requires macOS')
    # A supported-platform test must fail if its declared dependency is missing.
    import Quartz
    return Quartz


def png_size(encoded):
    raw = base64.b64decode(encoded, validate=True)
    assert raw[:8] == b'\x89PNG\r\n\x1a\n'
    return struct.unpack('>II', raw[16:24])


def pixel(encoded, x, y):
    from AppKit import NSBitmapImageRep
    from Foundation import NSData
    raw = base64.b64decode(encoded)
    bitmap = NSBitmapImageRep.imageRepWithData_(NSData.dataWithBytes_length_(raw, len(raw)))
    color = bitmap.colorAtX_y_(x, y)
    return tuple(round(v, 2) for v in (color.redComponent(), color.greenComponent(), color.blueComponent()))


def test_text_extraction_keeps_digital_text_and_exposes_mixed_coverage(tmp_path):
    path = write_pdf(tmp_path / 'mixed.pdf', rotations=(0, 0, 0), mixed=True)
    warnings = []
    assert ocr_pdf.extract_pdf_text_content(path, warnings=warnings) == 'Page 1\n\nPage 3'
    assert len(warnings) == 1
    assert '1 PDF page(s)' in warnings[0]
    assert 'absent' in warnings[0]
    assert ocr_pdf.extract_pdf_text_content(path, max_chars=4) == 'Page'
    scan = write_pdf(tmp_path / 'scan.pdf', scanned=True)
    assert ocr_pdf.extract_pdf_text_content(scan) == ''


@pytest.mark.parametrize('rotation,expected', [
    (0, ((0, 0, 1), (1, 1, 0), (1, 0, 0), (0, 1, 0))),
    (90, ((1, 0, 0), (0, 0, 1), (0, 1, 0), (1, 1, 0))),
    (180, ((0, 1, 0), (1, 0, 0), (1, 1, 0), (0, 0, 1))),
    (270, ((1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 0))),
])
def test_native_rotation_crop_origin_and_white_background(native, tmp_path, rotation, expected):
    path = write_pdf(tmp_path / 'geometry.pdf', rotations=(rotation,))
    pages, total, warnings = ocr_pdf.render_pdf_pages_to_base64(path, dpi=72)
    assert total == 1 and len(pages) == 1 and warnings == []
    width, height = png_size(pages[0])
    assert (width, height) == ((300, 200) if rotation % 180 else (200, 300))
    actual = [pixel(pages[0], x, y) for x, y in ((10, 10), (width-10, 10), (10, height-10), (width-10, height-10))]
    assert actual == list(expected)
    assert pixel(pages[0], width // 2, height // 2) == (1, 1, 1)


@pytest.mark.parametrize('scanned,mixed', [(True, False), (False, True)])
def test_all_pages_limit_and_exact_retry_identity(native, tmp_path, scanned, mixed):
    path = write_pdf(tmp_path / 'multipage.pdf', rotations=(0, 90, 180), scanned=scanned, mixed=mixed)
    before = path.read_bytes()
    pages, total, warnings = ocr_pdf.render_pdf_pages_to_base64(path, dpi=72)
    assert total == len(pages) == 3 and not warnings
    limited, total, warnings = ocr_pdf.render_pdf_pages_to_base64(path, max_pages=2, dpi=72)
    assert total == 3 and limited == pages[:2]
    assert 'first 2' in warnings[0]
    assert ocr_pdf.render_single_pdf_page_to_base64(path, page_index=1, dpi=72) == pages[1]
    assert ocr_pdf.render_single_pdf_page_to_base64(path, page_index=-1, dpi=72) is None
    assert ocr_pdf.render_single_pdf_page_to_base64(path, page_index=3, dpi=72) is None
    assert path.read_bytes() == before


def test_dpi_crop_retry_and_large_page_pixel_ceiling(native, tmp_path):
    path = write_pdf(tmp_path / 'retry.pdf', rotations=(90,))
    full = ocr_pdf.render_single_pdf_page_to_base64(path, page_index=0, dpi=144)
    cropped = ocr_pdf.render_single_pdf_page_to_base64(path, page_index=0, dpi=144, crop_margin_ratio=0.04)
    assert png_size(full) == (600, 400)
    assert png_size(cropped) == (552, 368)
    assert pixel(cropped, 10, 10) == (1, 0, 0)
    huge = write_pdf(tmp_path / 'huge.pdf', crop=(0, 0, 20000, 10000), media=(0, 0, 20000, 10000))
    pages, total, warnings = ocr_pdf.render_pdf_pages_to_base64(huge, dpi=600, max_image_side_px=1200)
    assert total == 1 and png_size(pages[0]) == (1200, 600)
    assert '1200px' in warnings[0]


def test_visible_annotations_render(native, tmp_path):
    path = write_pdf(tmp_path / 'annotated.pdf', annotation=True)
    pages, _, warnings = ocr_pdf.render_pdf_pages_to_base64(path, dpi=72)
    assert not warnings
    assert pixel(pages[0], 100, 150) == (1, 0, 1)


def test_pdf_user_unit_preserves_physical_page_size(native, tmp_path):
    path = write_pdf(tmp_path / 'user-unit.pdf')
    writer = PdfWriter(clone_from=path)
    writer.pages[0][NameObject('/UserUnit')] = FloatObject(2)
    writer.write(path)
    pages, _, warnings = ocr_pdf.render_pdf_pages_to_base64(path, dpi=72)
    assert not warnings
    assert png_size(pages[0]) == (400, 600)
    assert pixel(pages[0], 20, 20) == (0, 0, 1)


def test_missing_native_dependency_and_unsupported_platform_fail_explicitly(tmp_path):
    with patch.dict(sys.modules, {'Quartz': None}), patch.object(ocr_pdf.sys, 'platform', 'darwin'):
        pages, total, warnings = ocr_pdf.render_pdf_pages_to_base64(tmp_path / 'unused.pdf')
        assert pages == [] and total == 0
        assert 'requirements.txt' in warnings[0]
    with patch.object(ocr_pdf.sys, 'platform', 'linux'):
        pages, total, warnings = ocr_pdf.render_pdf_pages_to_base64(tmp_path / 'unused.pdf')
        assert pages == [] and total == 0
        assert 'requires macOS' in warnings[0]


def test_unreadable_empty_and_locked_pdfs(native, tmp_path):
    bad = tmp_path / 'broken.pdf'
    bad.write_bytes(b'not a PDF')
    empty = tmp_path / 'empty.pdf'
    PdfWriter().write(empty)
    locked = tmp_path / 'locked.pdf'
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=300)
    writer.encrypt('test-password', algorithm='RC4-128')
    writer.write(locked)
    for path in (bad, empty, locked):
        pages, total, warnings = ocr_pdf.render_pdf_pages_to_base64(path)
        assert pages == [] and total == 0 and warnings
        assert ocr_pdf.render_single_pdf_page_to_base64(path, page_index=0, dpi=180) is None


def test_failed_page_never_renumbers_remaining_pages(native, tmp_path):
    path = write_pdf(tmp_path / 'failed-page.pdf', rotations=(0, 0, 0))
    with patch.object(ocr_pdf, '_render_native_pdf_page', side_effect=[('first', False), ValueError('page 2 failed')]):
        pages, total, warnings = ocr_pdf.render_pdf_pages_to_base64(path)
    assert pages == [] and total == 3
    assert 'page 2 failed' in warnings[0]
