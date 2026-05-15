from __future__ import annotations

from .pdf_extractor import PageText, extract_text_by_page


def parse_pdf_bytes(pdf_bytes: bytes) -> list[PageText]:
    """Parse PDF bytes into page text only. No detection or interpretation here."""
    return extract_text_by_page(pdf_bytes)
