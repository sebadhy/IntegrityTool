from __future__ import annotations

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
