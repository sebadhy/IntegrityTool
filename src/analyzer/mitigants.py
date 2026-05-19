from __future__ import annotations

import re

from .domain_models import Clause, Signal
from .taxonomy_loader import TaxonomyPattern

GLOBAL_MITIGANTS = [
    "o equivalente",
    "o superior",
    "se aceptarán equivalentes",
    "se aceptaran equivalentes",
    "equivalente funcional",
    "certificación equivalente",
    "certificacion equivalente",
    "registro sanitario o equivalente",
    "alternativas equivalentes",
    "debidamente justificado",
    "según normativa aplicable",
    "segun normativa aplicable",
    "por razones de interoperabilidad",
    "por compatibilidad con infraestructura existente",
    "por seguridad",
    "por continuidad operativa",
]

STRONG_MITIGANTS = [
    "o equivalente",
    "se aceptarán equivalentes",
    "se aceptaran equivalentes",
    "equivalente funcional",
    "alternativas equivalentes",
]


def detect_mitigants(signal: Signal, clause: Clause, pattern: TaxonomyPattern) -> list[str]:
    text = f"{clause.normalized_text} {signal.evidence_text.lower()}"
    terms = GLOBAL_MITIGANTS + pattern.mitigating_factors
    return _unique([term for term in terms if _contains(text, term)])


def missing_mitigants(signal: Signal, detected: list[str]) -> list[str]:
    if has_strong_mitigant(detected):
        return []
    if signal.competition_dimension in {
        "neutralidad_competitiva",
        "proporcionalidad_de_requisitos",
        "interoperabilidad_y_compatibilidad",
        "relacion_con_objeto_contractual",
        "vendor_lock_in",
        "technical_restriction",
        "qualification_restriction",
        "interoperability_lock_in",
        "low_competitive_neutrality",
    }:
        return ["No se identificó mitigante textual de equivalencia o justificación cercana."]
    return []


def has_strong_mitigant(mitigants: list[str]) -> bool:
    normalized = [_normalize(item) for item in mitigants]
    return any(_normalize(term) in normalized for term in STRONG_MITIGANTS)


def _contains(text: str, term: str) -> bool:
    return _normalize(term) in _normalize(text)


def _normalize(text: str) -> str:
    replacements = str.maketrans("áéíóúñü", "aeiounu")
    return re.sub(r"\s+", " ", text.lower().translate(replacements)).strip()


def _unique(values: list[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        if value not in seen:
            output.append(value)
            seen.add(value)
    return output
