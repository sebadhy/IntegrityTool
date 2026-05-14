"""Structural segmentation of procurement PDF documents into named sections.

Cascade strategy:
  1. Vocabulary detection (Strategy B) — works on all PDF types including OCR text
  2. Title-pattern detection (Strategy A) — ALL-CAPS / numbered headings
  3. Fallback — single "desconocido" section covering the whole document
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .pdf_extractor import PageText
from .text_cleaner import normalize_for_matching


SECTION_VOCABULARY: dict[str, list[str]] = {
    "objeto_contratacion": [
        "objeto de la contratacion",
        "objeto del contrato",
        "descripcion del objeto",
        "naturaleza y objeto",
        "objeto de contratacion",
    ],
    "requisitos_habilitacion": [
        "requisitos de habilitacion",
        "condiciones de participacion",
        "habilitacion del oferente",
        "participacion de oferentes",
        "participantes habilitados",
        "capacidad legal",
        "requisitos minimos del oferente",
    ],
    "especificaciones_tecnicas": [
        "especificaciones tecnicas",
        "ficha tecnica",
        "caracteristicas tecnicas",
        "requerimientos tecnicos",
        "tabla de especificaciones",
        "especificaciones generales y particulares",
        "especificaciones particulares",
        "especificaciones generales",
    ],
    "experiencia_capacidad": [
        "experiencia minima",
        "experiencia del oferente",
        "capacidad tecnica",
        "trabajos similares",
        "experiencia especifica",
        "experiencia en trabajos",
        "capacidad financiera",
    ],
    "garantias_postventa": [
        "garantia tecnica",
        "garantia de fiel cumplimiento",
        "servicio postventa",
        "repuestos y mantenimiento",
        "garantia del fabricante",
        "garantia de fabricante",
        "servicio de garantia",
    ],
    "criterios_evaluacion": [
        "criterios de evaluacion",
        "metodologia de evaluacion",
        "tabla de calificacion",
        "parametros de evaluacion",
        "puntaje tecnico",
        "calificacion de ofertas",
    ],
    "condiciones_generales": [
        "condiciones generales",
        "disposiciones generales",
        "clausulas generales",
        "marco legal",
        "normativa aplicable",
        "base legal",
    ],
    "formularios": [
        "formularios de la oferta",
        "declaracion juramentada",
        "carta de presentacion",
        "oferta economica",
        "formulario de oferta",
    ],
}

_SECTION_CONFIG: dict[str, dict] = {
    "objeto_contratacion": {
        "label": "Objeto de contratación",
        "detection_profile": "restricted",
        "context_multiplier": 1.0,
    },
    "requisitos_habilitacion": {
        "label": "Requisitos de habilitación",
        "detection_profile": "full",
        "context_multiplier": 1.4,
    },
    "especificaciones_tecnicas": {
        "label": "Especificaciones técnicas",
        "detection_profile": "full",
        "context_multiplier": 1.8,
    },
    "experiencia_capacidad": {
        "label": "Experiencia y capacidad",
        "detection_profile": "full",
        "context_multiplier": 1.4,
    },
    "garantias_postventa": {
        "label": "Garantías y postventa",
        "detection_profile": "full",
        "context_multiplier": 1.3,
    },
    "criterios_evaluacion": {
        "label": "Criterios de evaluación",
        "detection_profile": "full",
        "context_multiplier": 1.2,
    },
    "condiciones_generales": {
        "label": "Condiciones generales",
        "detection_profile": "restricted",
        "context_multiplier": 1.0,
    },
    "formularios": {
        "label": "Formularios",
        "detection_profile": "skip",
        "context_multiplier": 0.5,
    },
    "desconocido": {
        "label": "Sección no identificada",
        "detection_profile": "full",
        "context_multiplier": 1.0,
    },
}

_TITLE_PATTERNS = [
    re.compile(r"^[IVX]{1,5}\.\s+[\w\s]{5,80}$", re.MULTILINE),
    re.compile(r"^\d+(?:\.\d+)*\.?\s+[\w\s]{5,80}$", re.MULTILINE),
    re.compile(r"^[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s]{7,79}$", re.MULTILINE),
    re.compile(r"^CL[ÁA]USULA\s+\w+", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^SECCI[ÓO]N\s+\w+", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^CAP[ÍI]TULO\s+\w+", re.MULTILINE | re.IGNORECASE),
]


@dataclass(frozen=True)
class DocumentSection:
    section_id: str
    section_label: str
    start_page: int
    end_page: int
    text: str
    detection_profile: str
    context_multiplier: float


def segment_document(pages: list[PageText]) -> list[DocumentSection]:
    """Segment document pages into structural sections using cascade detection."""
    if not pages:
        return []

    sections = _segment_by_vocabulary(pages)
    if not sections:
        sections = _segment_by_title_patterns(pages)
    if not sections:
        return [_fallback_section(pages)]
    return sections


def _segment_by_vocabulary(pages: list[PageText]) -> list[DocumentSection]:
    """Detect section boundaries by vocabulary signals in page headers."""
    boundaries: list[tuple[int, str]] = []

    for i, page in enumerate(pages):
        sid = _detect_section_for_page(page)
        if sid is not None and (not boundaries or boundaries[-1][1] != sid):
            boundaries.append((i, sid))

    if not boundaries:
        return []

    sections: list[DocumentSection] = []
    if boundaries[0][0] > 0:
        sections.append(_make_section("desconocido", pages[:boundaries[0][0]]))

    for j, (start_idx, sid) in enumerate(boundaries):
        end_idx = boundaries[j + 1][0] if j + 1 < len(boundaries) else len(pages)
        section_pages = pages[start_idx:end_idx]
        if section_pages:
            sections.append(_make_section(sid, section_pages))

    return sections


def _segment_by_title_patterns(pages: list[PageText]) -> list[DocumentSection]:
    """Detect section boundaries from formatted title lines mapped to vocabulary."""
    boundaries: list[tuple[int, str]] = []

    for i, page in enumerate(pages):
        sid = _detect_section_by_title(page)
        if sid is not None and (not boundaries or boundaries[-1][1] != sid):
            boundaries.append((i, sid))

    if not boundaries:
        return []

    sections: list[DocumentSection] = []
    if boundaries[0][0] > 0:
        sections.append(_make_section("desconocido", pages[:boundaries[0][0]]))

    for j, (start_idx, sid) in enumerate(boundaries):
        end_idx = boundaries[j + 1][0] if j + 1 < len(boundaries) else len(pages)
        section_pages = pages[start_idx:end_idx]
        if section_pages:
            sections.append(_make_section(sid, section_pages))

    return sections


def _detect_section_for_page(page: PageText) -> str | None:
    """Return section_id if this page's header contains a known vocabulary signal."""
    text = normalize_for_matching(page.text)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    header = " \n ".join(lines[:8])

    best: tuple[int, str] | None = None
    for sid, signals in SECTION_VOCABULARY.items():
        for signal in signals:
            if signal in header and (best is None or len(signal) > best[0]):
                best = (len(signal), sid)

    return best[1] if best else None


def _detect_section_by_title(page: PageText) -> str | None:
    """Return section_id if a formatted title line in this page matches vocabulary."""
    for pattern in _TITLE_PATTERNS:
        for match in pattern.finditer(page.text):
            line = match.group().strip()
            if 5 <= len(line) <= 100:
                sid = _match_vocabulary(normalize_for_matching(line))
                if sid:
                    return sid
    return None


def _match_vocabulary(normalized_text: str) -> str | None:
    """Return section_id for the longest vocabulary signal found in normalized_text."""
    best: tuple[int, str] | None = None
    for sid, signals in SECTION_VOCABULARY.items():
        for signal in signals:
            if signal in normalized_text and (best is None or len(signal) > best[0]):
                best = (len(signal), sid)
    return best[1] if best else None


def _make_section(section_id: str, pages: list[PageText]) -> DocumentSection:
    config = _SECTION_CONFIG.get(section_id, _SECTION_CONFIG["desconocido"])
    return DocumentSection(
        section_id=section_id,
        section_label=config["label"],
        start_page=pages[0].page_number,
        end_page=pages[-1].page_number,
        text="\n\n".join(p.text for p in pages),
        detection_profile=config["detection_profile"],
        context_multiplier=config["context_multiplier"],
    )


def _fallback_section(pages: list[PageText]) -> DocumentSection:
    config = _SECTION_CONFIG["desconocido"]
    return DocumentSection(
        section_id="desconocido",
        section_label=config["label"],
        start_page=pages[0].page_number,
        end_page=pages[-1].page_number,
        text="\n\n".join(p.text for p in pages),
        detection_profile=config["detection_profile"],
        context_multiplier=config["context_multiplier"],
    )
