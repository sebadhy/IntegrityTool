from __future__ import annotations

import hashlib
import re

from .document_segmenter import DocumentSection, section_for_page
from .domain_models import Clause
from .pdf_extractor import PageText


def extract_clauses(
    pages: list[PageText],
    sections: list[DocumentSection],
    document_id: str,
) -> list[Clause]:
    clauses: list[Clause] = []
    for page in pages:
        section = section_for_page(sections, page.page_number)
        section_title = section.section_label if section else "Sección no determinada"
        section_type = _section_type(section_title)
        for index, text in enumerate(_split_page_into_clauses(page.text), start=1):
            normalized = normalize_text(text)
            digest = hashlib.sha1(f"{document_id}|{page.page_number}|{index}|{normalized[:120]}".encode("utf-8")).hexdigest()[:12]
            clauses.append(
                Clause(
                    clause_id=f"clause-{digest}",
                    document_id=document_id,
                    page=page.page_number,
                    section_title=section_title,
                    section_type=section_type,
                    text=text.strip(),
                    normalized_text=normalized,
                )
            )
    return clauses


def normalize_text(text: str) -> str:
    replacements = str.maketrans("áéíóúñü", "aeiounu")
    return re.sub(r"\s+", " ", text.lower().translate(replacements)).strip()


def _split_page_into_clauses(text: str) -> list[str]:
    blocks = [block.strip() for block in re.split(r"\n\s*\n|(?<=[.;:])\s+(?=[A-ZÁÉÍÓÚÑ0-9])", text) if block.strip()]
    if not blocks and text.strip():
        blocks = [text.strip()]
    merged: list[str] = []
    buffer = ""
    for block in blocks:
        if len(block) < 35 and buffer:
            buffer = f"{buffer} {block}".strip()
            continue
        if buffer:
            merged.append(buffer)
        buffer = block
    if buffer:
        merged.append(buffer)
    return merged


def _section_type(section_title: str) -> str:
    text = normalize_text(section_title)
    if "especific" in text or "ficha" in text:
        return "technical_requirements"
    if "experiencia" in text or "capacidad" in text:
        return "qualification"
    if "formulario" in text or "anexo" in text:
        return "forms"
    if "objeto" in text:
        return "object"
    if "condiciones" in text:
        return "general_conditions"
    return "unknown"
