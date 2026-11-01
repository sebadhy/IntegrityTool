import pymupdf as fitz
import pytest

from src.analyzer import pdf_extractor
from src.analyzer.pdf_extractor import PageStatus, extract_text_by_page


def image_bytes():
    with fitz.open() as document:
        page = document.new_page(width=80, height=30)
        page.insert_text((5, 18), "IMAGEN", fontsize=8)
        return page.get_pixmap().tobytes("png")


def make_pdf(rect, *, pages=2, text="Texto breve seleccionable.", extra_image=None, rotation=0):
    image = image_bytes()
    with fitz.open() as document:
        for _ in range(pages):
            page = document.new_page()
            page.insert_text((40, 110), text)
            page.insert_image(rect, stream=image, keep_proportion=False)
            if extra_image:
                page.insert_image(extra_image, stream=image, keep_proportion=False)
            page.set_rotation(rotation)
        return document.tobytes()


@pytest.fixture(autouse=True)
def no_system_ocr(monkeypatch):
    monkeypatch.setattr(pdf_extractor, "_tesseract_available", lambda: False)
    monkeypatch.setattr(pdf_extractor, "_ocr_page", lambda *args: pytest.fail("Unexpected OCR"))


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_short_native_text_and_repeated_header_do_not_require_ocr(rotation):
    content = make_pdf(fitz.Rect(40, 28, 300, 70), rotation=rotation)
    pages = extract_text_by_page(content)
    assert all(page.status == PageStatus.OK for page in pages)
    assert all("Texto breve seleccionable" in page.text and page.extraction_note for page in pages)
    assert all(not page.ocr_attempted for page in pages)


def test_repeated_footer_does_not_discard_short_native_text():
    pages = extract_text_by_page(make_pdf(fitz.Rect(40, 790, 240, 825)))
    assert all(page.status == PageStatus.OK and page.text for page in pages)


@pytest.mark.parametrize("rect", [fitz.Rect(40, 150, 200, 190), fitz.Rect(0, 0, 595, 842),
                                  fitz.Rect(10, 10, 580, 70)])
def test_body_full_page_and_wide_header_images_still_require_ocr(rect):
    pages = extract_text_by_page(make_pdf(rect))
    assert all(page.status == PageStatus.REQUIRES_OCR for page in pages)


def test_a_single_small_header_image_remains_conservative():
    page = extract_text_by_page(make_pdf(fitz.Rect(40, 28, 300, 70), pages=1))[0]
    assert page.status == PageStatus.REQUIRES_OCR


def test_body_image_is_not_ignored_when_a_repeated_logo_is_present():
    pages = extract_text_by_page(make_pdf(fitz.Rect(40, 28, 300, 70),
                                        extra_image=fitz.Rect(40, 200, 500, 500)))
    assert all(page.status == PageStatus.REQUIRES_OCR for page in pages)


def test_an_image_only_page_is_not_declared_readable_from_a_repeated_logo():
    pages = extract_text_by_page(make_pdf(fitz.Rect(40, 28, 300, 70), text=""))
    assert all(page.status == PageStatus.REQUIRES_OCR for page in pages)


def test_real_raster_ocr_retains_success_status_and_provenance(monkeypatch):
    monkeypatch.setattr(pdf_extractor, "_tesseract_available", lambda: True)
    monkeypatch.setattr(pdf_extractor, "_ocr_page", lambda *args: "Texto recuperado para prueba. " * 8)
    pages = extract_text_by_page(make_pdf(fitz.Rect(0, 0, 595, 842), text=""))
    assert all(page.status == PageStatus.OCR_OK and page.ocr_attempted for page in pages)
    assert all("OCR" in page.extraction_note for page in pages)


def test_ocr_failure_does_not_become_a_complete_extraction(monkeypatch):
    monkeypatch.setattr(pdf_extractor, "_tesseract_available", lambda: True)
    monkeypatch.setattr(pdf_extractor, "_ocr_page", lambda *args: "")
    pages = extract_text_by_page(make_pdf(fitz.Rect(0, 0, 595, 842)))
    assert all(page.status == PageStatus.OCR_FAILED and page.text for page in pages)


def test_unknown_image_geometry_is_not_treated_as_a_readable_page():
    class UnknownPage:
        def get_image_info(self, **kwargs):
            raise RuntimeError("Unknown image geometry")
    assert pdf_extractor._page_has_images(UnknownPage())


def test_short_native_page_and_empty_page_remain_distinct():
    with fitz.open() as document:
        document.new_page().insert_text((40, 40), "Texto breve")
        document.new_page()
        pages = extract_text_by_page(document.tobytes())
    assert pages[0].status == PageStatus.OK and pages[0].has_text
    assert pages[1].status == PageStatus.EMPTY and not pages[1].has_text
