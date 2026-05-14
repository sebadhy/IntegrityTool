from __future__ import annotations

import re
import unicodedata


def clean_page_text(raw_text: str) -> str:
    """Clean raw text extracted from a PDF page for display and export."""
    text = _join_broken_lines(raw_text)
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_for_matching(text: str) -> str:
    """Normalize text for internal pattern comparison.

    Applies: lowercase, whitespace collapse, accent removal via NFD.
    Use this everywhere a string is compared against another — not for display.
    """
    text = re.sub(r"\s+", " ", text).lower().strip()
    text = "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )
    return text


def _join_broken_lines(text: str) -> str:
    # Word split by hyphen at line wrap: reattach
    text = re.sub(r"-\n(\w)", r"\1", text)
    # Line not ending in punctuation that continues on next line
    text = re.sub(r"(?<![.;:!?\n])\n(?!\n)(?!\d+\.)(?![A-Z]{2,})", " ", text)
    return text
