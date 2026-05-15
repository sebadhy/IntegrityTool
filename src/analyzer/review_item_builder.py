from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd

from .domain_models import ConsolidatedFinding, ReviewItem
from .prioritizer import review_priority_from_score

PROHIBITED_VISIBLE_TERMS = [
    "corrupción",
    "fraude",
    "ilegal",
    "direccionamiento detectado",
    "colusión",
    "culpable",
    "responsabilidad",
    "irregularidad comprobada",
]

PRIORITY_DISPLAY = {"alta": "revisión prioritaria", "media": "revisión sugerida", "baja": "revisión general"}
ATTENTION_DISPLAY = {"alta": "Alto", "media": "Medio", "baja": "Bajo"}


def build_review_items(findings: list[ConsolidatedFinding], max_items: int = 18) -> list[ReviewItem]:
    items = [_build_item(finding) for finding in findings]
    items = [item for item in items if item.allowed_language_only]
    return items[:max_items]


def review_items_to_dataframe(items: list[ReviewItem], document_name: str) -> pd.DataFrame:
    rows = [_item_to_row(item, document_name) for item in items]
    return pd.DataFrame(rows)


def _build_item(finding: ConsolidatedFinding) -> ReviewItem:
    priority = review_priority_from_score(finding.internal_ranking_score)
    evidence_summary = _evidence_summary(finding)
    questions = _questions(finding)
    why = _safe_visible_text(_why_it_matters(finding))
    title = _safe_visible_text(finding.title or "Aspecto sugerido para revisión")
    item_id = hashlib.sha1(f"review|{finding.finding_id}".encode("utf-8")).hexdigest()[:12]
    return ReviewItem(
        review_item_id=f"review-{item_id}",
        title=title,
        review_priority=priority,  # type: ignore[arg-type]
        competition_dimension=finding.competition_dimension,
        why_it_matters=why,
        evidence_summary=_safe_visible_text(evidence_summary),
        evidence_items=finding.evidence_items,
        mitigants_summary=_mitigants_summary(finding),
        suggested_human_review_question=questions,
        limitations=finding.limitations,
        source_finding_ids=[finding.finding_id],
        display_group=_display_group(finding.competition_dimension),
        allowed_language_only=_allowed_language(title, why, evidence_summary),
        metadata={
            "pattern_id": finding.pattern_id,
            "family": finding.family,
            "duplicate_count": finding.duplicate_count,
            "internal_ranking_score": finding.internal_ranking_score,
            "ranking_factors": finding.ranking_factors,
            "historical_context": finding.historical_context,
            "detected_mitigants": finding.detected_mitigants,
            "missing_mitigants": finding.missing_mitigants,
            "consolidation_key": finding.consolidation_key,
        },
    )


def _item_to_row(item: ReviewItem, document_name: str) -> dict[str, Any]:
    evidence = item.evidence_items[0] if item.evidence_items else {}
    pages = sorted({int(ev.get("page", 0)) for ev in item.evidence_items if ev.get("page")})
    frequency = item.metadata.get("historical_context", {}).get("frequency_label", "No disponible")
    rarity = item.metadata.get("historical_context", {}).get("rarity", "Sin histórico")
    comparative = item.metadata.get("historical_context", {}).get("comparative_comment", "Comparación histórica no disponible.")
    priority_label = PRIORITY_DISPLAY[item.review_priority]
    attention = ATTENTION_DISPLAY[item.review_priority]
    questions = item.suggested_human_review_question
    return {
        "finding_id": item.review_item_id,
        "id": item.review_item_id,
        "signal_id": item.review_item_id,
        "pattern_id": item.metadata.get("pattern_id", "No disponible"),
        "pattern_name": item.title,
        "title": item.title,
        "competition_dimension": item.competition_dimension,
        "dimensión competitiva": item.competition_dimension,
        "document_section": evidence.get("section", "No determinada"),
        "sección documental probable": evidence.get("section", "No determinada"),
        "clause_excerpt": item.evidence_summary,
        "reason_for_review": item.why_it_matters,
        "confidence": "medium",
        "review_priority": {"alta": "priority", "media": "suggested", "baja": "general"}[item.review_priority],
        "prioridad de revisión": priority_label,
        "severity": "contextual" if item.review_priority == "alta" else "low" if item.review_priority == "baja" else "medium",
        "mitigating_factors": item.metadata.get("detected_mitigants", []),
        "escalation_factors": item.metadata.get("ranking_factors", []),
        "suggested_questions": questions,
        "human_review_questions": questions,
        "possible_legitimate_justifications": [],
        "missing_information": item.metadata.get("missing_mitigants", []),
        "contextual_notes": item.limitations,
        "requires_human_review": True,
        "output_label": "aspecto a revisar",
        "signal_type": "contextual_observation",
        "tipo_señal": "señal_revision",
        "frecuencia_corpus": frequency,
        "categoria": item.display_group,
        "tema de revisión": item.display_group,
        "documento origen": document_name,
        "página": pages[0] if pages else evidence.get("page", ""),
        "related_pages": pages,
        "páginas relacionadas": ", ".join(str(page) for page in pages),
        "occurrence_count": item.metadata.get("duplicate_count", len(item.evidence_items)),
        "occurrencias relacionadas": item.metadata.get("duplicate_count", len(item.evidence_items)),
        "representative_excerpt": item.evidence_summary,
        "categoría de revisión": item.display_group,
        "patrón detectado": item.title,
        "atención sugerida": attention,
        "nivel_atencion": attention,
        "relevancia_analitica": attention,
        "criterios_de_priorizacion": item.metadata.get("ranking_factors", []),
        "explicacion_priorizacion": item.why_it_matters,
        "elementos que favorecen concurrencia": item.mitigants_summary,
        "nivel de atención": attention,
        "clasificación histórica": rarity,
        "frecuencia en corpus": frequency,
        "procesos_con_patron": frequency,
        "interpretación_comparativa": comparative,
        "número de coincidencias": item.metadata.get("duplicate_count", len(item.evidence_items)),
        "posible efecto sobre concurrencia": item.why_it_matters,
        "validación sugerida": questions[0] if questions else "Revisar proporcionalidad y existencia de equivalentes.",
        "principio_normativo_relacionado": "concurrencia / igualdad / proporcionalidad",
        "criterio_normativo_de_revision": "Validar proporcionalidad, equivalencias y relación con el objeto contractual.",
        "pregunta_normativa_sugerida": questions[0] if questions else "¿El requisito es proporcional al objeto contractual?",
        "por qué se sugiere revisar": item.why_it_matters,
        "posible justificación legítima": item.mitigants_summary or "Puede responder a necesidades técnicas, calidad, garantía o trazabilidad del bien si está justificado.",
        "revisión sugerida": questions[0] if questions else "Revisar proporcionalidad y mitigantes textuales.",
        "comentario contextual": comparative,
        "fragmento textual": item.evidence_summary,
        "observación prudente": item.why_it_matters,
        "llm_explanation": "No disponible",
        "human_review_questions": questions,
        "possible_legitimate_justification": item.mitigants_summary or "No disponible",
        "recommended_action": questions[0] if questions else "Revisión humana sugerida.",
        "questions_for_reviewer": questions,
    }


def _why_it_matters(finding: ConsolidatedFinding) -> str:
    if finding.duplicate_count > 1:
        prefix = f"Se consolidaron {finding.duplicate_count} señales relacionadas. "
    else:
        prefix = "Se identificó una señal preliminar. "
    context = finding.candidate_rationale or "Convendría verificar proporcionalidad y relación con el objeto contractual."
    if finding.historical_context.get("rarity") == "Habitual":
        context += " El patrón aparece frecuentemente en procesos comparables; aislado no debería elevar prioridad."
    return prefix + context


def _evidence_summary(finding: ConsolidatedFinding) -> str:
    excerpts = []
    for evidence in finding.evidence_items[:3]:
        text = str(evidence.get("text", "")).strip()
        if text and text not in excerpts:
            excerpts.append(text)
    return " / ".join(excerpts)


def _mitigants_summary(finding: ConsolidatedFinding) -> str:
    if finding.detected_mitigants:
        return "; ".join(finding.detected_mitigants[:5])
    if finding.missing_mitigants:
        return "No se identificó mitigante textual cercano."
    return "Sin mitigantes explícitos identificados."


def _questions(finding: ConsolidatedFinding) -> list[str]:
    questions: list[str] = []
    for signal in finding.signals:
        questions.extend(signal.metadata.get("taxonomy_pattern", {}).get("human_review_questions", []))
    if not questions:
        questions = ["¿El requisito es proporcional al objeto contractual?", "¿Se admiten alternativas equivalentes?"]
    return _unique(questions)[:4]


def _display_group(dimension: str) -> str:
    return {
        "vendor_lock_in": "Autorizaciones, marca u origen",
        "technical_restriction": "Requisitos técnicos",
        "qualification_restriction": "Experiencia o capacidad",
        "financial_restriction": "Requisitos financieros",
        "timeline_restriction": "Cronograma y plazos",
        "geographic_restriction": "Presencia local o cobertura",
        "interoperability_lock_in": "Compatibilidad e interoperabilidad",
        "low_competitive_neutrality": "Condiciones potencialmente limitantes",
    }.get(dimension, "Condiciones potencialmente limitantes")


def _safe_visible_text(text: str) -> str:
    safe = text
    replacements = {
        "direccionamiento detectado": "aspecto a revisar",
        "irregularidad comprobada": "aspecto a revisar",
        "corrupción": "conducta no evaluada por la herramienta",
        "fraude": "conducta no evaluada por la herramienta",
        "colusión": "conducta no evaluada por la herramienta",
        "culpable": "responsable no determinado",
    }
    for source, target in replacements.items():
        safe = safe.replace(source, target).replace(source.capitalize(), target)
    return safe


def _allowed_language(*values: str) -> bool:
    text = " ".join(values).lower()
    return not any(term in text for term in PROHIBITED_VISIBLE_TERMS)


def _unique(values: list[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        if value and value not in seen:
            output.append(value)
            seen.add(value)
    return output
