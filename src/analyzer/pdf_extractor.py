from __future__ import annotations

import re
from dataclasses import dataclass

import fitz


@dataclass(frozen=True)
class PageText:
    page_number: int
    text: str


def extract_text_by_page(pdf_bytes: bytes) -> list[PageText]:
    """Extract plain text from every page of a PDF document."""
    pages: list[PageText] = []

    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        for page_index, page in enumerate(document, start=1):
            text = page.get_text("text").strip()
            pages.append(PageText(page_number=page_index, text=text))

    return pages


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
