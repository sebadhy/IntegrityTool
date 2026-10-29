from __future__ import annotations

from .domain_models import Clause, Signal
from .taxonomy_loader import TaxonomyPattern
from .text_utils import affirmed_terms, normalize_text_es

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
    terms = GLOBAL_MITIGANTS + pattern.mitigating_factors
    return affirmed_terms(signal.evidence_text, terms)


def missing_mitigants(signal: Signal, detected: list[str]) -> list[str]:
    if signal.metadata.get("is_common_in_goods_procurement") and not signal.metadata.get("restriction_factors"):
        return []
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
    normalized = [normalize_text_es(item) for item in mitigants]
    return any(normalize_text_es(term) in normalized for term in STRONG_MITIGANTS)

