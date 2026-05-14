from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from .finding_model import (
    Finding,
    REVIEW_GENERAL,
    REVIEW_PRIORITY,
    REVIEW_SUGGESTED,
    SEVERITY_CONTEXTUAL,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
)
from .patterns.competitive_neutrality_patterns import PATTERNS
from .pdf_extractor import PageText
from .taxonomy_loader import TaxonomyPattern, load_taxonomy


SIGNAL_REVIEW = "señal_revision"
SIGNAL_MITIGANT = "mitigante_concurrencia"
SIGNAL_HABITUAL = "requisito_habitual"

GLOBAL_MITIGATING_TERMS = [
    "o equivalente",
    "se aceptarán equivalentes",
    "o superior",
    "personas naturales o jurídicas",
    "consorcios",
    "consorcio",
    "asociaciones",
    "proveedores nacionales o extranjeros",
]

GLOBAL_JUSTIFICATION_TERMS = [
    "según normativa aplicable",
    "debidamente justificado",
    "por razones de interoperabilidad",
    "por compatibilidad con infraestructura existente",
    "por seguridad",
    "por continuidad operativa",
]

SECTION_HINTS = {
    "especificaciones técnicas": ["especificaciones técnicas", "ficha técnica", "requisitos técnicos"],
    "evaluación": ["evaluación", "calificación", "puntaje", "metodología"],
    "cronograma": ["cronograma", "plazo", "fecha", "ofertas"],
    "experiencia": ["experiencia", "contratos", "capacidad técnica"],
    "requisitos administrativos": ["documentación", "administrativo", "rup", "domicilio fiscal"],
    "postventa": ["garantía", "repuestos", "mantenimiento", "servicio técnico"],
}


@dataclass(frozen=True)
class PatternRule:
    pattern: str
    category: str
    attention_level: str
    observation: str
    possible_competition_effect: str
    suggested_validation: str
    signal_type: str = SIGNAL_REVIEW


class Detection(Finding):
    def __init__(
        self,
        page: int,
        detected_pattern: str,
        category: str,
        attention_level: str,
        match_count: int,
        text_fragment: str,
        prudent_observation: str,
        possible_competition_effect: str,
        suggested_validation: str,
        signal_type: str,
    ) -> None:
        super().__init__(
            id=_finding_id(f"legacy-{detected_pattern}", page, text_fragment),
            title=detected_pattern,
            category=category,
            severity=SEVERITY_LOW if attention_level == "Bajo" else SEVERITY_MEDIUM,
            evidence=text_fragment,
            page=page,
            rationale=prudent_observation,
            pattern_id=f"legacy-{_slug(detected_pattern)}",
            mitigating_factors=[],
            escalation_factors=[],
            suggested_questions=[suggested_validation],
            requires_human_review=signal_type == SIGNAL_REVIEW,
            output_label="aspecto a revisar",
            signal_type=signal_type,
            match_count=match_count,
        )


RULES = [
    PatternRule(
        pattern="distribuidor autorizado",
        category="Autorizaciones comerciales o de fabricante",
        attention_level="Medio",
        observation=(
            "Se detectó una autorización comercial formal; conviene revisar si reduce "
            "la participación de oferentes no vinculados al fabricante."
        ),
        possible_competition_effect=(
            "Podría limitar oferentes no vinculados formalmente al fabricante."
        ),
        suggested_validation=(
            "Verificar si el requisito está justificado por la naturaleza del bien."
        ),
    ),
    PatternRule(
        pattern="concesionario",
        category="Autorizaciones comerciales o de fabricante",
        attention_level="Medio",
        observation=(
            "Se detectó una condición asociada a canal comercial; conviene validar si "
            "existen alternativas funcionales aceptables."
        ),
        possible_competition_effect=(
            "Podría reducir concurrencia si solo habilita un canal comercial específico."
        ),
        suggested_validation=(
            "Confirmar si se aceptan alternativas equivalentes."
        ),
    ),
    PatternRule(
        pattern="comercializador autorizado",
        category="Autorizaciones comerciales o de fabricante",
        attention_level="Alto",
        observation=(
            "Se detectó una autorización de comercialización; conviene revisar si su "
            "exigencia es proporcional y admite equivalentes."
        ),
        possible_competition_effect=(
            "Podría limitar oferentes sin vínculo formal de comercialización."
        ),
        suggested_validation=(
            "Verificar si el requisito está justificado por la naturaleza del bien."
        ),
    ),
    PatternRule(
        pattern="certificación ISO",
        category="Certificaciones específicas",
        attention_level="Medio",
        observation=(
            "Se detectó una certificación específica; conviene revisar si está vinculada "
            "al objeto contractual y si admite estándares equivalentes."
        ),
        possible_competition_effect=(
            "Podría elevar barreras de entrada si la certificación no es proporcional."
        ),
        suggested_validation=(
            "Revisar proporcionalidad del plazo o certificación exigida."
        ),
    ),
    PatternRule(
        pattern="ficha técnica",
        category="Requisitos técnicos cerrados",
        attention_level="Bajo",
        observation=(
            "Se detectó referencia a ficha técnica; conviene revisar si las condiciones "
            "permiten equivalentes funcionales."
        ),
        possible_competition_effect=(
            "Podría reducir participación si no se aceptan equivalentes funcionales."
        ),
        suggested_validation=(
            "Confirmar si se aceptan alternativas equivalentes."
        ),
    ),
    PatternRule(
        pattern="fabricante",
        category="Referencias a marca, origen o fabricante",
        attention_level="Medio",
        observation=(
            "Se detectó una referencia a fabricante; conviene validar si opera como "
            "referencia técnica abierta o como condición cerrada."
        ),
        possible_competition_effect=(
            "Podría reducir concurrencia si privilegia un origen o fabricante específico."
        ),
        suggested_validation=(
            "Confirmar si se aceptan alternativas equivalentes."
        ),
    ),
    PatternRule(
        pattern="marca",
        category="Referencias a marca, origen o fabricante",
        attention_level="Medio",
        observation=(
            "Se detectó referencia a marca; conviene revisar si la especificación admite "
            "equivalentes funcionales."
        ),
        possible_competition_effect=(
            "Podría reducir participación si se interpreta como preferencia cerrada."
        ),
        suggested_validation=(
            "Confirmar si se aceptan alternativas equivalentes."
        ),
    ),
    PatternRule(
        pattern="repuestos",
        category="Garantías, repuestos y postventa",
        attention_level="Bajo",
        observation=(
            "Se detectó requisito de repuestos; conviene revisar proporcionalidad, plazo "
            "y apertura de proveedores de soporte."
        ),
        possible_competition_effect=(
            "Podría elevar barreras de entrada si exige disponibilidad no proporcional."
        ),
        suggested_validation=(
            "Revisar proporcionalidad del plazo o certificación exigida."
        ),
    ),
    PatternRule(
        pattern="servicio técnico",
        category="Garantías, repuestos y postventa",
        attention_level="Medio",
        observation=(
            "Se detectó requisito de servicio técnico; conviene validar si se exigen "
            "condiciones de presencia, autorización o red de soporte."
        ),
        possible_competition_effect=(
            "Podría elevar barreras de entrada si exige soporte específico sin alternativas."
        ),
        suggested_validation=(
            "Validar si el requisito es habitual respecto del corpus histórico."
        ),
    ),
    PatternRule(
        pattern="garantía técnica",
        category="Garantías, repuestos y postventa",
        attention_level="Bajo",
        observation=(
            "Se detectó garantía técnica; conviene revisar alcance, plazo y relación "
            "con el objeto contractual."
        ),
        possible_competition_effect=(
            "Podría elevar barreras de entrada si el alcance no está justificado."
        ),
        suggested_validation=(
            "Verificar si el requisito está justificado por la naturaleza del bien."
        ),
    ),
    PatternRule(
        pattern="mantenimiento preventivo",
        category="Garantías, repuestos y postventa",
        attention_level="Bajo",
        observation=(
            "Se detectó mantenimiento preventivo; conviene revisar plazos, exclusividad "
            "y condiciones de acreditación."
        ),
        possible_competition_effect=(
            "Podría reducir concurrencia si concentra el servicio en proveedores específicos."
        ),
        suggested_validation=(
            "Revisar proporcionalidad del plazo o certificación exigida."
        ),
    ),
    PatternRule(
        pattern="manuales técnicos",
        category="Requisitos técnicos cerrados",
        attention_level="Bajo",
        observation=(
            "Se detectó solicitud de manuales técnicos; conviene revisar si se combina "
            "con especificaciones cerradas."
        ),
        possible_competition_effect=(
            "Podría reducir participación si se exige documentación exclusiva de un fabricante."
        ),
        suggested_validation=(
            "Confirmar si se aceptan alternativas equivalentes."
        ),
    ),
    PatternRule(
        pattern="domicilio",
        category="Requisitos regulatorios o habituales",
        attention_level="Bajo",
        observation=(
            "Se detectó referencia a domicilio; puede corresponder a información administrativa "
            "habitual y solo requiere atención si opera como presencia local obligatoria."
        ),
        possible_competition_effect=(
            "Por sí solo no constituye una señal relevante de restricción competitiva."
        ),
        suggested_validation=(
            "Verificar si se trata de domicilio fiscal/administrativo o de presencia local exigida."
        ),
        signal_type=SIGNAL_HABITUAL,
    ),
    PatternRule(
        pattern="presencia local",
        category="Restricciones geográficas o de presencia local",
        attention_level="Alto",
        observation=(
            "Se detectó presencia local; conviene revisar necesidad, proporcionalidad y "
            "alternativas de atención remota o logística."
        ),
        possible_competition_effect=(
            "Podría excluir oferentes con capacidad de atención sin presencia local permanente."
        ),
        suggested_validation=(
            "Revisar proporcionalidad del plazo o certificación exigida."
        ),
    ),
    PatternRule(
        pattern="experiencia específica",
        category="Experiencia o capacidad excesivamente específica",
        attention_level="Medio",
        observation=(
            "Se detectó experiencia específica; conviene validar si el alcance exigido "
            "guarda relación directa con el objeto contractual."
        ),
        possible_competition_effect=(
            "Podría elevar barreras de entrada si el requisito no es proporcional."
        ),
        suggested_validation=(
            "Verificar si el requisito está justificado por la naturaleza del bien."
        ),
    ),
    PatternRule(
        pattern="REVISAR CONDICIONES PARTICULARES",
        category="Completitud y trazabilidad documental",
        attention_level="Medio",
        observation=(
            "Se detectó remisión a condiciones particulares; conviene validar que la "
            "información esté disponible y sea trazable."
        ),
        possible_competition_effect=(
            "Podría afectar concurrencia si la información clave no está completa o accesible."
        ),
        suggested_validation=(
            "Validar si el documento contiene información completa o remite a anexos no disponibles."
        ),
    ),
    PatternRule(
        pattern="sin datos",
        category="Completitud y trazabilidad documental",
        attention_level="Alto",
        observation=(
            "Se detectó un campo sin datos; conviene validar si afecta información necesaria "
            "para preparar una oferta."
        ),
        possible_competition_effect=(
            "Podría afectar concurrencia si la falta de datos impide comparar condiciones."
        ),
        suggested_validation=(
            "Validar si el documento contiene información completa o remite a anexos no disponibles."
        ),
    ),
    PatternRule(
        pattern="no requerido por la entidad",
        category="Completitud y trazabilidad documental",
        attention_level="Bajo",
        observation=(
            "Se detectó una condición no requerida; conviene validar si esa omisión es "
            "consistente con el objeto contractual."
        ),
        possible_competition_effect=(
            "Podría afectar concurrencia si omite información relevante para los oferentes."
        ),
        suggested_validation=(
            "Validar si la omisión es consistente con el objeto contractual."
        ),
    ),
    PatternRule(
        pattern="ver más especificaciones técnicas",
        category="Completitud y trazabilidad documental",
        attention_level="Medio",
        observation=(
            "Se detectó una remisión a especificaciones adicionales; conviene validar "
            "acceso, trazabilidad y completitud."
        ),
        possible_competition_effect=(
            "Podría afectar concurrencia si información técnica clave depende de anexos no disponibles."
        ),
        suggested_validation=(
            "Validar si el documento contiene información completa o remite a anexos no disponibles."
        ),
    ),
    PatternRule(
        pattern="adjunto",
        category="Completitud y trazabilidad documental",
        attention_level="Medio",
        observation=(
            "Se detectó referencia a adjunto; conviene comprobar que el documento esté "
            "disponible para todos los oferentes."
        ),
        possible_competition_effect=(
            "Podría afectar concurrencia si un anexo relevante no es accesible o trazable."
        ),
        suggested_validation=(
            "Validar si el documento contiene información completa o remite a anexos no disponibles."
        ),
    ),
    PatternRule(
        pattern="descargar",
        category="Completitud y trazabilidad documental",
        attention_level="Medio",
        observation=(
            "Se detectó referencia a descarga; conviene validar disponibilidad y acceso "
            "uniforme a la información."
        ),
        possible_competition_effect=(
            "Podría afectar concurrencia si la información complementaria no está disponible."
        ),
        suggested_validation=(
            "Validar si el documento contiene información completa o remite a anexos no disponibles."
        ),
    ),
    PatternRule(
        pattern="link",
        category="Completitud y trazabilidad documental",
        attention_level="Medio",
        observation=(
            "Se detectó referencia a enlace; conviene verificar disponibilidad, acceso "
            "y contenido asociado."
        ),
        possible_competition_effect=(
            "Podría afectar concurrencia si el enlace no permite acceso estable a información clave."
        ),
        suggested_validation=(
            "Validar si el documento contiene información completa o remite a anexos no disponibles."
        ),
    ),
    PatternRule(
        pattern="RUP",
        category="Requisitos regulatorios o habituales",
        attention_level="Bajo",
        observation=(
            "La inscripción en RUP constituye un requisito regulatorio habitual y, por sí sola, "
            "no representa una señal relevante de restricción competitiva."
        ),
        possible_competition_effect="No se aprecia efecto limitante por sí solo.",
        suggested_validation=(
            "Validar únicamente si se combina con condiciones adicionales no proporcionales."
        ),
        signal_type=SIGNAL_HABITUAL,
    ),
    PatternRule(
        pattern="capacidad legal",
        category="Requisitos regulatorios o habituales",
        attention_level="Bajo",
        observation=(
            "La capacidad legal suele formar parte de la verificación administrativa estándar."
        ),
        possible_competition_effect="No se aprecia efecto limitante por sí solo.",
        suggested_validation="Revisar solo si se agregan condiciones excesivamente específicas.",
        signal_type=SIGNAL_HABITUAL,
    ),
    PatternRule(
        pattern="domicilio fiscal",
        category="Requisitos regulatorios o habituales",
        attention_level="Bajo",
        observation=(
            "El domicilio fiscal suele ser información administrativa estándar del oferente."
        ),
        possible_competition_effect="No se aprecia efecto limitante por sí solo.",
        suggested_validation=(
            "Distinguir domicilio fiscal de exigencia de presencia local operativa."
        ),
        signal_type=SIGNAL_HABITUAL,
    ),
    PatternRule(
        pattern="asociaciones o consorcios",
        category="Requisitos regulatorios o habituales",
        attention_level="Bajo",
        observation=(
            "La referencia a asociaciones o consorcios puede ser un requisito habitual y también "
            "puede favorecer participación conjunta."
        ),
        possible_competition_effect="No se aprecia efecto limitante por sí solo.",
        suggested_validation="Verificar que las condiciones para consorcios sean proporcionales.",
        signal_type=SIGNAL_HABITUAL,
    ),
    PatternRule(
        pattern="personas naturales o jurídicas",
        category="Requisitos regulatorios o habituales",
        attention_level="Bajo",
        observation=(
            "La apertura a personas naturales o jurídicas es una fórmula administrativa habitual."
        ),
        possible_competition_effect="Puede ampliar participación si no contiene restricciones adicionales.",
        suggested_validation="Confirmar que no existan exclusiones posteriores incompatibles.",
        signal_type=SIGNAL_HABITUAL,
    ),
    PatternRule(
        pattern="equivalente",
        category="Elementos que favorecen concurrencia",
        attention_level="Bajo",
        observation=(
            "Se detectó aceptación de equivalentes; este elemento puede mitigar una especificación cerrada."
        ),
        possible_competition_effect="Favorece concurrencia al admitir alternativas funcionalmente comparables.",
        suggested_validation="Verificar que la equivalencia sea clara, verificable y aplicable en evaluación.",
        signal_type=SIGNAL_MITIGANT,
    ),
    PatternRule(
        pattern="o equivalente",
        category="Elementos que favorecen concurrencia",
        attention_level="Bajo",
        observation=(
            "Se detectó una cláusula de equivalencia funcional."
        ),
        possible_competition_effect="Favorece concurrencia al evitar una lectura cerrada de la especificación.",
        suggested_validation="Validar que los criterios para aceptar equivalentes estén definidos.",
        signal_type=SIGNAL_MITIGANT,
    ),
    PatternRule(
        pattern="consorcio",
        category="Elementos que favorecen concurrencia",
        attention_level="Bajo",
        observation=(
            "La participación mediante consorcio puede ampliar concurrencia cuando permite complementar capacidades."
        ),
        possible_competition_effect="Favorece concurrencia al permitir participación conjunta.",
        suggested_validation="Revisar que los requisitos para consorcios no sean desproporcionados.",
        signal_type=SIGNAL_MITIGANT,
    ),
    PatternRule(
        pattern="oferentes nacionales y extranjeros",
        category="Elementos que favorecen concurrencia",
        attention_level="Bajo",
        observation=(
            "Se detectó apertura a oferentes nacionales y extranjeros."
        ),
        possible_competition_effect="Favorece concurrencia al ampliar el universo potencial de participantes.",
        suggested_validation="Confirmar consistencia con el resto de requisitos del pliego.",
        signal_type=SIGNAL_MITIGANT,
    ),
    PatternRule(
        pattern="marcas equivalentes",
        category="Elementos que favorecen concurrencia",
        attention_level="Bajo",
        observation=(
            "Se detectó referencia a marcas equivalentes."
        ),
        possible_competition_effect="Favorece concurrencia al admitir pluralidad de soluciones.",
        suggested_validation="Validar que los parámetros de equivalencia estén objetivamente definidos.",
        signal_type=SIGNAL_MITIGANT,
    ),
]


def detect_patterns(pages: list[PageText]) -> list[Detection]:
    raw_detections: list[Detection] = []

    for page in pages:
        normalized_text = _normalize_whitespace(page.text)
        taxonomy_terms = _taxonomy_terms_set()
        for rule in RULES:
            if rule.signal_type == SIGNAL_REVIEW and normalize_text(rule.pattern) in taxonomy_terms:
                continue
            for match in re.finditer(_pattern_regex(rule.pattern), normalized_text, re.IGNORECASE):
                fragment = _build_clause_fragment(
                    normalized_text,
                    match.start(),
                    match.end(),
                )
                if _should_skip_match(rule, fragment):
                    continue
                raw_detections.append(
                    Detection(
                        page=page.page_number,
                        detected_pattern=rule.pattern,
                        category=rule.category,
                        attention_level=rule.attention_level,
                        match_count=1,
                        text_fragment=fragment,
                        prudent_observation=rule.observation,
                        possible_competition_effect=rule.possible_competition_effect,
                        suggested_validation=rule.suggested_validation,
                        signal_type=rule.signal_type,
                    )
                )


        active_patterns = _active_taxonomy_patterns()
        page_pattern_ids: set[str] = set()
        for pattern in active_patterns:
            for term, start, end in find_terms(normalized_text, pattern.textual_signals):
                fragment = extract_context_window(normalized_text, start, end)
                mitigating_factors = _contextual_mitigating_factors(fragment, pattern)
                possible_justifications = _contextual_justifications(fragment, pattern)
                escalation_factors = _taxonomy_escalation_factors(
                    fragment=fragment,
                    pattern=pattern,
                    term=term,
                    mitigating_factors=mitigating_factors,
                    possible_justifications=possible_justifications,
                    page_pattern_ids=page_pattern_ids,
                )
                page_pattern_ids.add(pattern.id)
                document_section = _document_section(fragment, pattern)
                missing_information = _missing_information(
                    pattern,
                    mitigating_factors,
                    possible_justifications,
                )
                raw_detections.append(
                    Finding(
                        id=_finding_id(pattern.id, page.page_number, fragment),
                        title=pattern.name,
                        category=_category_from_dimension(pattern.competition_dimension),
                        severity=_taxonomy_severity(pattern, mitigating_factors, escalation_factors),
                        evidence=fragment,
                        page=page.page_number,
                        rationale=_taxonomy_rationale(pattern, term, mitigating_factors, possible_justifications),
                        pattern_id=pattern.id,
                        mitigating_factors=mitigating_factors,
                        escalation_factors=escalation_factors,
                        suggested_questions=pattern.human_review_questions,
                        requires_human_review=True,
                        output_label="aspecto a revisar",
                        signal_type=SIGNAL_REVIEW,
                        pattern_name=pattern.name,
                        competition_dimension=pattern.competition_dimension,
                        document_section=document_section,
                        clause_excerpt=fragment,
                        reason_for_review=_taxonomy_rationale(
                            pattern, term, mitigating_factors, possible_justifications
                        ),
                        possible_legitimate_justifications=pattern.possible_legitimate_justifications
                        + possible_justifications,
                        missing_information=missing_information,
                        suggested_neutral_wording=pattern.recommended_language,
                        confidence=_taxonomy_confidence(pattern, mitigating_factors, escalation_factors),
                        review_priority=_taxonomy_review_priority(
                            pattern, mitigating_factors, escalation_factors
                        ),
                        contextual_notes=_contextual_notes(
                            mitigating_factors, possible_justifications, missing_information
                        ),
                    )
                )

    return _deduplicate(raw_detections)



_TAXONOMY_CACHE: list[TaxonomyPattern] | None = None


def _active_taxonomy_patterns() -> list[TaxonomyPattern]:
    global _TAXONOMY_CACHE
    if _TAXONOMY_CACHE is not None:
        return _TAXONOMY_CACHE

    result = load_taxonomy()
    if result.patterns:
        _TAXONOMY_CACHE = result.patterns
        return _TAXONOMY_CACHE

    _TAXONOMY_CACHE = [_legacy_pattern_to_taxonomy(pattern) for pattern in PATTERNS]
    return _TAXONOMY_CACHE


def _taxonomy_terms_set() -> set[str]:
    return {
        normalize_text(term)
        for pattern in _active_taxonomy_patterns()
        for term in pattern.textual_signals
    }


def _legacy_pattern_to_taxonomy(pattern: dict) -> TaxonomyPattern:
    return TaxonomyPattern(
        id=str(pattern["id"]),
        name=str(pattern["title"]),
        description=str(pattern["description"]),
        competition_dimension="low_competitive_neutrality",
        risk_type="consideración analítica",
        document_sections=[str(pattern["category"])],
        textual_signals=list(pattern.get("trigger_terms", [])),
        semantic_signals=[],
        possible_indicators=[],
        mitigating_factors=list(pattern.get("mitigating_terms", []))
        + list(pattern.get("non_restrictive_contexts", [])),
        possible_legitimate_justifications=[],
        human_review_questions=list(pattern.get("suggested_questions", [])),
        recommended_language=[str(pattern.get("output_label", "aspecto a revisar"))],
        prohibited_language=[],
        severity_guidance="suggested",
        confidence_guidance="medium",
        related_patterns=[],
    )


def _category_from_dimension(dimension: str) -> str:
    return {
        "barrier_to_entry": "Combinaciones de requisitos potencialmente limitantes",
        "vendor_lock_in": "Referencias a marca, origen o fabricante",
        "reduced_market_access": "Autorizaciones comerciales o de fabricante",
        "qualification_restriction": "Experiencia o capacidad excesivamente específica",
        "administrative_burden": "Completitud y trazabilidad documental",
        "geographic_restriction": "Restricciones geográficas o de presencia local",
        "evaluation_discretion": "Combinaciones de requisitos potencialmente limitantes",
        "interoperability_lock_in": "Requisitos técnicos cerrados",
        "timeline_restriction": "Combinaciones de requisitos potencialmente limitantes",
        "financial_restriction": "Experiencia o capacidad excesivamente específica",
        "technical_restriction": "Requisitos técnicos cerrados",
        "low_competitive_neutrality": "Combinaciones de requisitos potencialmente limitantes",
    }.get(dimension, "Combinaciones de requisitos potencialmente limitantes")


def _contextual_mitigating_factors(fragment: str, pattern: TaxonomyPattern) -> list[str]:
    return _unique(
        _matched_terms(fragment, pattern.mitigating_factors)
        + _matched_terms(fragment, GLOBAL_MITIGATING_TERMS)
    )


def _contextual_justifications(fragment: str, pattern: TaxonomyPattern) -> list[str]:
    return _unique(
        _matched_terms(fragment, GLOBAL_JUSTIFICATION_TERMS)
        + [
            justification
            for justification in pattern.possible_legitimate_justifications
            if normalize_text(justification) in normalize_text(fragment)
        ]
    )


def _taxonomy_escalation_factors(
    fragment: str,
    pattern: TaxonomyPattern,
    term: str,
    mitigating_factors: list[str],
    possible_justifications: list[str],
    page_pattern_ids: set[str],
) -> list[str]:
    factors: list[str] = []
    normalized_fragment = normalize_text(fragment)
    if not mitigating_factors and pattern.id in {
        "cn-brand-model-provider-reference",
        "cn-weak-equivalence-clause",
        "cn-technical-closed-requirement",
        "cn-specific-certification",
    }:
        factors.append("No se observa mitigante de equivalencia cerca del fragmento.")
    if not possible_justifications and pattern.competition_dimension in {
        "interoperability_lock_in",
        "geographic_restriction",
        "timeline_restriction",
        "financial_restriction",
    }:
        factors.append("No se observa justificación técnica cercana en el fragmento.")
    for indicator in pattern.possible_indicators + pattern.semantic_signals:
        indicator_text = normalize_text(indicator)
        if indicator_text and indicator_text in normalized_fragment:
            factors.append(indicator)
    related_seen = sorted(set(pattern.related_patterns).intersection(page_pattern_ids))
    if related_seen:
        factors.append("Coexistencia con patrones relacionados en la misma página.")
    if normalize_text(term) in {"adicionalmente", "además deberá", "conjuntamente"}:
        factors.append("Lenguaje acumulativo de requisitos.")
    return _unique(factors)


def _document_section(fragment: str, pattern: TaxonomyPattern) -> str:
    normalized_fragment = normalize_text(fragment)
    for section, hints in SECTION_HINTS.items():
        if any(hint in normalized_fragment for hint in hints):
            return section
    if pattern.document_sections:
        return pattern.document_sections[0]
    return "No determinada"


def _missing_information(
    pattern: TaxonomyPattern,
    mitigating_factors: list[str],
    possible_justifications: list[str],
) -> list[str]:
    missing: list[str] = []
    if not mitigating_factors and pattern.id in {
        "cn-brand-model-provider-reference",
        "cn-technical-closed-requirement",
        "cn-specific-certification",
    }:
        missing.append("No se identifica equivalencia funcional cercana.")
    if not possible_justifications and pattern.competition_dimension in {
        "geographic_restriction",
        "interoperability_lock_in",
        "financial_restriction",
        "timeline_restriction",
    }:
        missing.append("No se identifica justificación técnica cercana.")
    return missing


def _taxonomy_rationale(
    pattern: TaxonomyPattern,
    term: str,
    mitigating_factors: list[str],
    possible_justifications: list[str],
) -> str:
    parts = [
        f"Se identificó una señal preliminar asociada a '{pattern.name}' por la expresión '{term}'.",
        "Convendría revisar si el requisito es proporcional, verificable y compatible con concurrencia.",
    ]
    if mitigating_factors:
        parts.append(
            "Se identificó un factor mitigante asociado a apertura competitiva; conviene validar si opera de forma efectiva."
        )
    if possible_justifications:
        parts.append(
            "También aparece una posible justificación técnica cercana que debería ser revisada en contexto."
        )
    if not mitigating_factors:
        parts.append("No se observa mitigante cercano en el fragmento revisado.")
    return " ".join(parts)


def _taxonomy_severity(
    pattern: TaxonomyPattern,
    mitigating_factors: list[str],
    escalation_factors: list[str],
) -> str:
    if mitigating_factors and not escalation_factors:
        return SEVERITY_LOW
    if pattern.severity_guidance == REVIEW_PRIORITY or len(escalation_factors) >= 2:
        return SEVERITY_CONTEXTUAL
    return SEVERITY_MEDIUM


def _taxonomy_confidence(
    pattern: TaxonomyPattern,
    mitigating_factors: list[str],
    escalation_factors: list[str],
) -> str:
    if mitigating_factors and not escalation_factors:
        return "medium"
    if escalation_factors:
        return pattern.confidence_guidance
    return "low" if pattern.confidence_guidance == "low" else "medium"


def _taxonomy_review_priority(
    pattern: TaxonomyPattern,
    mitigating_factors: list[str],
    escalation_factors: list[str],
) -> str:
    if mitigating_factors and not escalation_factors:
        return REVIEW_GENERAL
    if pattern.severity_guidance == REVIEW_PRIORITY or len(escalation_factors) >= 2:
        return REVIEW_PRIORITY
    if pattern.severity_guidance == REVIEW_GENERAL and not escalation_factors:
        return REVIEW_GENERAL
    return REVIEW_SUGGESTED


def _contextual_notes(
    mitigating_factors: list[str],
    possible_justifications: list[str],
    missing_information: list[str],
) -> list[str]:
    notes: list[str] = []
    if mitigating_factors:
        notes.append("Factor mitigante identificado; revisar si la equivalencia o apertura es efectiva.")
    if possible_justifications:
        notes.append("Posible justificación legítima cercana; revisar soporte técnico o documental.")
    if missing_information:
        notes.append("Información faltante o no visible en el fragmento requiere validación humana.")
    return notes


def _deduplicate(detections: list[Detection], similarity_threshold: float = 0.82) -> list[Detection]:
    consolidated: list[Detection] = []

    for detection in detections:
        duplicate = _find_similar_detection(
            detection,
            consolidated,
            similarity_threshold,
        )
        if duplicate is None:
            consolidated.append(detection)
            continue

        duplicate.match_count += 1
        if _fragment_score(detection.text_fragment) > _fragment_score(duplicate.text_fragment):
            duplicate.text_fragment = detection.text_fragment

    return consolidated


def _find_similar_detection(
    detection: Detection,
    candidates: list[Detection],
    similarity_threshold: float,
) -> Detection | None:
    for candidate in candidates:
        if detection.page != candidate.page:
            continue
        if detection.detected_pattern != candidate.detected_pattern:
            continue
        if _text_similarity(detection.text_fragment, candidate.text_fragment) >= similarity_threshold:
            return candidate

    return None


def normalize_text(text: str) -> str:
    return _normalize_whitespace(text).lower()


def find_terms(text: str, terms: list[str]) -> list[tuple[str, int, int]]:
    matches: list[tuple[str, int, int]] = []
    for term in terms:
        for match in re.finditer(_pattern_regex(term), text, re.IGNORECASE):
            matches.append((term, match.start(), match.end()))
    return matches


def extract_context_window(text: str, start: int, end: int, context_chars: int = 260) -> str:
    fragment_start = max(0, start - context_chars)
    fragment_end = min(len(text), end + context_chars)
    prefix = "... " if fragment_start > 0 else ""
    suffix = " ..." if fragment_end < len(text) else ""
    return f"{prefix}{text[fragment_start:fragment_end].strip()}{suffix}"


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _pattern_regex(pattern: str) -> str:
    escaped = re.escape(pattern)
    if pattern and pattern[0].isalnum() and pattern[-1].isalnum():
        return rf"(?<!\w){escaped}(?!\w)"
    return escaped


def _should_skip_match(rule: PatternRule, fragment: str) -> bool:
    normalized_fragment = _normalize_for_similarity(fragment)
    if rule.pattern.lower() == "domicilio" and "domicilio fiscal" in normalized_fragment:
        return True
    if rule.signal_type == SIGNAL_MITIGANT and _has_negated_equivalence(normalized_fragment):
        return True
    return False


def _build_clause_fragment(text: str, start: int, end: int) -> str:
    sentence_start = _nearest_left_boundary(text, start)
    sentence_end = _nearest_right_boundary(text, end)

    fragment = text[sentence_start:sentence_end].strip()

    if len(fragment) > 520:
        return _trim_fragment_around_match(text, start, end)

    prefix = "... " if sentence_start > 0 else ""
    suffix = " ..." if sentence_end < len(text) else ""

    return f"{prefix}{fragment}{suffix}"


def _nearest_left_boundary(text: str, start: int) -> int:
    boundary_chars = ".;:!?|"
    candidates = [text.rfind(char, 0, start) for char in boundary_chars]
    boundary = max(candidates)
    return 0 if boundary == -1 else boundary + 1


def _nearest_right_boundary(text: str, end: int) -> int:
    boundary_positions = [
        position for position in (text.find(char, end) for char in ".;:!?|") if position != -1
    ]
    return len(text) if not boundary_positions else min(boundary_positions) + 1


def _trim_fragment_around_match(text: str, start: int, end: int, context_chars: int = 220) -> str:
    fragment_start = max(0, start - context_chars)
    fragment_end = min(len(text), end + context_chars)
    prefix = "... " if fragment_start > 0 else ""
    suffix = " ..." if fragment_end < len(text) else ""

    return f"{prefix}{text[fragment_start:fragment_end].strip()}{suffix}"


def _fragment_score(fragment: str) -> tuple[int, int]:
    has_sentence_end = int(any(marker in fragment for marker in ".;:!?"))
    useful_length = min(len(fragment), 520)
    return has_sentence_end, useful_length


def _text_similarity(left: str, right: str) -> float:
    left_normalized = _normalize_for_similarity(left)
    right_normalized = _normalize_for_similarity(right)
    return SequenceMatcher(None, left_normalized, right_normalized).ratio()


def _normalize_for_similarity(text: str) -> str:
    text = re.sub(r"\W+", " ", text.lower())
    return _normalize_whitespace(text)


def _matched_terms(text: str, terms: list[str]) -> list[str]:
    matched = []
    for term, start, end in find_terms(text, terms):
        window = normalize_text(text[max(0, start - 35): min(len(text), end + 35)])
        if "equivalent" in normalize_text(term) or "equivalente" in normalize_text(term):
            if _has_negated_equivalence(window):
                continue
        matched.append(term)
    return matched


def _has_negated_equivalence(text: str) -> bool:
    negated_patterns = (
        "no se menciona equivalente",
        "no se aceptan equivalentes",
        "sin equivalente",
        "sin equivalentes",
        "no admite equivalente",
        "no admite equivalentes",
    )
    return any(pattern in text for pattern in negated_patterns)


def _escalation_factors(fragment: str, pattern: dict, mitigating_factors: list[str]) -> list[str]:
    normalized_fragment = normalize_text(fragment)
    factors = []
    for condition in pattern["escalation_conditions"]:
        condition_text = normalize_text(condition)
        if "ausencia" in condition_text and not mitigating_factors:
            factors.append(condition)
        elif condition_text in normalized_fragment:
            factors.append(condition)
    return factors


def _catalog_severity(mitigating_factors: list[str], escalation_factors: list[str]) -> str:
    if len(escalation_factors) >= 2:
        return "contextual"
    if escalation_factors:
        return "medium"
    if mitigating_factors:
        return "low"
    return "medium"


def _finding_id(pattern_id: str, page: int, fragment: str) -> str:
    digest = hashlib.sha1(f"{pattern_id}|{page}|{fragment[:240]}".encode("utf-8")).hexdigest()
    return f"finding-{digest[:12]}"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalize_text(value)).strip("-")


def _unique(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        clean_value = value.strip()
        if clean_value and clean_value not in seen:
            result.append(clean_value)
            seen.add(clean_value)
    return result
