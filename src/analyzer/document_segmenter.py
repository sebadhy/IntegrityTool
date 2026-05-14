from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Literal

from .pdf_extractor import PageText

DetectionProfile = Literal["full", "restricted", "skip"]


@dataclass(frozen=True)
class DocumentSection:
    section_id: str
    section_label: str
    start_page: int
    end_page: int
    text: str
    detection_profile: DetectionProfile
    context_multiplier: float = 1.0


SECTION_VOCABULARY = {
    "especificaciones_tecnicas": {
        "label": "Especificaciones técnicas",
        "profile": "full",
        "multiplier": 1.8,
        "terms": [
            "especificaciones técnicas",
            "especificaciones tecnicas",
            "descripción técnica del bien",
            "descripcion tecnica del bien",
            "formulario de especificaciones tecnicas",
            "ficha técnica",
            "ficha tecnica",
            "terminos de referencia",
            "términos de referencia",
        ],
    },
    "experiencia_capacidad": {
        "label": "Experiencia y capacidad",
        "profile": "full",
        "multiplier": 1.45,
        "terms": ["experiencia", "capacidad técnica", "capacidad tecnica", "personal técnico"],
    },
    "objeto_contratacion": {
        "label": "Objeto de contratación",
        "profile": "restricted",
        "multiplier": 1.0,
        "terms": [
            "objeto de contratación",
            "objeto de contratacion",
            "descripcion general del requerimiento",
            "descripcion del requerimiento",
        ],
    },
    "condiciones_generales": {
        "label": "Condiciones generales",
        "profile": "restricted",
        "multiplier": 0.8,
        "terms": ["antecedentes", "marco normativo", "disposiciones legales", "condiciones generales"],
    },
    "formularios": {
        "label": "Formularios administrativos",
        "profile": "skip",
        "multiplier": 0.0,
        "terms": ["formulario", "anexo", "declaración", "declaracion", "firma del oferente"],
    },
}


def segment_document(pages: list[PageText]) -> list[DocumentSection]:
    """Segment pages into broad review zones using procurement vocabulary and headings.

    The segmenter is intentionally conservative: it only changes detection intensity;
    it does not create conclusions and never removes the need for human review.
    """
    sections = [_section_for_page(page) for page in pages]
    if not sections:
        return []
    return _merge_adjacent_sections(sections)


def section_for_page(sections: list[DocumentSection], page_number: int) -> DocumentSection | None:
    for section in sections:
        if section.start_page <= page_number <= section.end_page:
            return section
    return None


def _section_for_page(page: PageText) -> DocumentSection:
    normalized = _normalize(page.text[:2500])
    best_key = "desconocido"
    best_score = 0
    for key, spec in SECTION_VOCABULARY.items():
        score = sum(1 for term in spec["terms"] if _normalize(term) in normalized)
        if score > best_score:
            best_key = key
            best_score = score

    if best_score == 0:
        heading = _heading_profile(page.text)
        best_key = heading or "desconocido"

    spec = SECTION_VOCABULARY.get(best_key)
    if spec is None:
        label = "Sección no determinada"
        profile: DetectionProfile = "full"
        multiplier = 1.0
    else:
        label = str(spec["label"])
        profile = spec["profile"]  # type: ignore[assignment]
        multiplier = float(spec["multiplier"])

    digest = hashlib.sha1(f"{best_key}|{page.page_number}".encode("utf-8")).hexdigest()[:8]
    return DocumentSection(
        section_id=f"{best_key}-{digest}",
        section_label=label,
        start_page=page.page_number,
        end_page=page.page_number,
        text=page.text,
        detection_profile=profile,
        context_multiplier=multiplier,
    )


def _merge_adjacent_sections(sections: list[DocumentSection]) -> list[DocumentSection]:
    merged: list[DocumentSection] = []
    for section in sections:
        if not merged or merged[-1].section_label != section.section_label:
            merged.append(section)
            continue
        previous = merged[-1]
        merged[-1] = DocumentSection(
            section_id=previous.section_id,
            section_label=previous.section_label,
            start_page=previous.start_page,
            end_page=section.end_page,
            text=f"{previous.text}\n\n{section.text}",
            detection_profile=previous.detection_profile,
            context_multiplier=max(previous.context_multiplier, section.context_multiplier),
        )
    return merged


def _heading_profile(text: str) -> str | None:
    for line in text.splitlines()[:12]:
        clean = line.strip()
        if not clean or len(clean) > 90:
            continue
        if re.match(r"^(\d+(\.\d+)*\s+)?[A-ZÁÉÍÓÚÑÜ0-9 /,.-]{8,}$", clean):
            normalized = _normalize(clean)
            if "formulario" in normalized or "anexo" in normalized:
                return "formularios"
            if "especific" in normalized or "tecnica" in normalized:
                return "especificaciones_tecnicas"
            if "experiencia" in normalized or "capacidad" in normalized:
                return "experiencia_capacidad"
            if "normativo" in normalized or "antecedente" in normalized:
                return "condiciones_generales"
    return None


def _normalize(text: str) -> str:
    replacements = str.maketrans("áéíóúñü", "aeiounu")
    return re.sub(r"\s+", " ", text.lower().translate(replacements)).strip()
