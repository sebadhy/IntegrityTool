from __future__ import annotations

import logging
import os
import re
import tempfile
from dataclasses import dataclass

import fitz

from .text_cleaner import normalize_for_matching


LOGGER = logging.getLogger(__name__)

try:
    import pytesseract
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False


@dataclass(frozen=True)
class PageText:
    page_number: int
    text: str
    source: str = "native"  # "native", "ocr", "empty"


def extract_text_by_page(pdf_bytes: bytes, attempt_ocr: bool = False) -> list[PageText]:
    """Extract text from every page. If attempt_ocr=True and pytesseract is installed,
    pages with images but no native text are OCR'd."""
    pages: list[PageText] = []

    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        for page_index, page in enumerate(document, start=1):
            text = page.get_text("text").strip()
            if text:
                pages.append(PageText(page_number=page_index, text=text, source="native"))
            elif _page_needs_ocr(page):
                if attempt_ocr and _OCR_AVAILABLE:
                    ocr_text = _ocr_page(page)
                    source = "ocr" if ocr_text else "empty"
                    pages.append(PageText(page_number=page_index, text=ocr_text, source=source))
                else:
                    pages.append(PageText(page_number=page_index, text="", source="empty"))
            else:
                pages.append(PageText(page_number=page_index, text="", source="empty"))

    return pages


def count_ocr_candidates(pdf_bytes: bytes) -> int:
    """Return the number of pages that have images but no native text (OCR candidates)."""
    count = 0
    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        for page in document:
            if _page_needs_ocr(page):
                count += 1
    return count


def _page_needs_ocr(page: fitz.Page, min_chars: int = 50) -> bool:
    text = page.get_text("text").strip()
    has_images = len(page.get_images()) > 0
    return len(text) < min_chars and has_images


def _ocr_page(page: fitz.Page) -> str:
    if not _OCR_AVAILABLE:
        return ""
    try:
        mat = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=mat)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
        pix.save(tmp_path)
        text = pytesseract.image_to_string(tmp_path, lang="spa")
        os.unlink(tmp_path)
        return text.strip()
    except Exception as exc:
        LOGGER.warning("OCR failed on page: %s", exc)
        return ""


_OBJECT_PATTERNS = [
    r"objeto\s+de\s+(?:la\s+)?contrataci[oó]n[:\s]+([^\n]{20,300})",
    r"descripci[oó]n\s+del\s+objeto[:\s]+([^\n]{20,300})",
    r"adquisici[oó]n\s+de\s+([^\n]{20,200})",
    r"contrataci[oó]n\s+de\s+(?:servicios?\s+de\s+)?([^\n]{20,200})",
    r"objeto\s*:[:\s]+([^\n]{20,300})",
]


def extract_contract_object(pages: list[PageText], max_pages: int = 3) -> str:
    """Try to extract the contract object from the first pages using heuristics."""
    for page in pages[:max_pages]:
        for pattern in _OBJECT_PATTERNS:
            match = re.search(pattern, page.text, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                value = re.sub(r"\s+", " ", value)
                return value[:300]
    return "No identificado en las primeras páginas"


_DOCUMENT_TYPE_SIGNALS: dict[str, list[str]] = {
    "pliego": [
        "pliego de condiciones",
        "bases generales",
        "condiciones particulares",
        "objeto de la contratacion",
        "presupuesto referencial",
        "pliego de clausulas",
    ],
    "especificaciones_tecnicas": [
        "especificaciones tecnicas",
        "ficha tecnica",
        "caracteristicas tecnicas",
        "tabla de especificaciones",
        "requerimientos tecnicos minimos",
        "especificaciones generales",
    ],
    "terminos_referencia": [
        "terminos de referencia",
        "alcance del servicio",
        "perfil del consultor",
        "entregables",
        "productos esperados",
    ],
    "contrato": [
        "clausula primera",
        "partes contratantes",
        "objeto del contrato",
        "precio del contrato",
        "clausulas del contrato",
    ],
}

_DOCUMENT_TYPE_LABELS: dict[str, str] = {
    "pliego": "Pliego de condiciones",
    "especificaciones_tecnicas": "Especificaciones técnicas",
    "terminos_referencia": "Términos de referencia",
    "contrato": "Contrato",
    "desconocido": "Tipo no determinado",
}


def detect_document_type(pages: list[PageText], max_pages: int = 5) -> str:
    """Detect the document type from textual signals in the first pages.

    Returns one of: 'pliego', 'especificaciones_tecnicas', 'terminos_referencia',
    'contrato', 'desconocido'.
    """
    scores: dict[str, int] = {doc_type: 0 for doc_type in _DOCUMENT_TYPE_SIGNALS}
    for page in pages[:max_pages]:
        normalized = normalize_for_matching(page.text)
        for doc_type, signals in _DOCUMENT_TYPE_SIGNALS.items():
            for signal in signals:
                if signal in normalized:
                    scores[doc_type] += 1
    best_type = max(scores, key=lambda t: scores[t])
    return best_type if scores[best_type] > 0 else "desconocido"


def document_type_label(doc_type: str) -> str:
    """Human-readable label for a document type key."""
    return _DOCUMENT_TYPE_LABELS.get(doc_type, "Tipo no determinado")
