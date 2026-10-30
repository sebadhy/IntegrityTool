from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import Any

from .domain_models import Clause, FindingCandidate, Signal
from .mitigants import detect_mitigants, missing_mitigants
from .taxonomy_loader import TaxonomyPattern, load_taxonomy
from .text_utils import normalize_text_es


def build_finding_candidates(
    signals: list[Signal],
    clauses: list[Clause],
    corpus_context: dict[str, dict[str, Any]] | None = None,
    taxonomy_patterns: list[TaxonomyPattern] | None = None,
) -> list[FindingCandidate]:
    patterns = load_taxonomy().patterns if taxonomy_patterns is None else taxonomy_patterns
    pattern_lookup = {pattern.id: pattern for pattern in patterns}
    clause_lookup = {clause.clause_id: clause for clause in clauses}
    candidates: list[FindingCandidate] = []
    for signal in signals:
        pattern = pattern_lookup.get(signal.pattern_id)
        clause = clause_lookup.get(signal.clause_id)
        if not pattern or not clause or clause.exclude_from_detection:
            continue
        mitigants = detect_mitigants(signal, clause, pattern)
        missing = missing_mitigants(signal, mitigants)
        signal = replace(signal, metadata={**signal.metadata,
                         "local_mitigants": mitigants, "local_missing_mitigants": missing})
        historical = _historical_context(pattern, corpus_context or {})
        semantic = signal.metadata.get("analysis_source") == "semantic_assisted"
        if semantic:
            # Rule-only frequencies are not a semantic prevalence benchmark.
            historical = {"frequency_label": "No disponible", "rarity": "Sin histórico",
                          "comparative_comment": "El corpus se examinó con reglas; no se atribuye rareza a esta propuesta semántica."}
        normalized_requirement = normalize_text_es(signal.evidence_text)
        candidate_id = hashlib.sha1(f"{signal.signal_id}|{normalized_requirement[:160]}".encode("utf-8")).hexdigest()[:12]
        evidence = signal.metadata.get("evidence_items") or [_evidence_item(signal, clause, pattern)]
        candidates.append(
            FindingCandidate(
                candidate_id=f"cand-{candidate_id}",
                signals=[signal],
                pattern_id=signal.pattern_id,
                family=signal.family,
                competition_dimension=signal.competition_dimension,
                requirement_text=signal.evidence_text,
                normalized_requirement=normalized_requirement,
                evidence=evidence,
                detected_mitigants=mitigants,
                missing_mitigants=missing,
                historical_context=historical,
                candidate_rationale=("Propuesta de lectura contextual: " + signal.metadata["semantic_review_note"]
                                     if semantic else _candidate_rationale(signal, pattern, mitigants, missing, historical)),
                limitations=_limitations(clause, historical) + ([
                    "Propuesta semántica con cita comprobada; la interpretación requiere validación humana.",
                    "El modelo no revisó todas las cláusulas ni determina que falten justificaciones fuera del fragmento.",
                ] if semantic else []),
            )
        )
    return candidates


def _evidence_item(signal: Signal, clause: Clause, pattern: TaxonomyPattern) -> dict[str, Any]:
    return {
        "signal_id": signal.signal_id,
        "clause_id": clause.clause_id,
        "page": clause.page,
        "section": clause.section_title,
        "pattern_id": pattern.id,
        "pattern_name": pattern.name,
        "matched_text": signal.matched_text,
        "text": signal.evidence_text,
    }


def _historical_context(pattern: TaxonomyPattern, corpus_context: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return corpus_context.get(pattern.id) or corpus_context.get(pattern.name) or {
        "frequency_label": "No disponible",
        "rarity": "Sin histórico",
        "comparative_comment": "Comparación histórica no disponible.",
        "frequency": 0,
    }


def _candidate_rationale(
    signal: Signal,
    pattern: TaxonomyPattern,
    mitigants: list[str],
    missing: list[str],
    historical: dict[str, Any],
) -> str:
    parts = [
        f"Se identificó una señal preliminar asociada a {pattern.name}.",
        "Convendría verificar proporcionalidad, relación con el objeto y condiciones de participación.",
    ]
    if signal.metadata.get("is_common_in_goods_procurement") and not signal.metadata.get("restriction_factors"):
        parts = [
            "Se identificó un requisito de autorización, certificación o respaldo del bien.",
            "Este tipo de exigencia puede ser habitual en compras de bienes con necesidades de calidad, garantía, regulación o soporte.",
            "Su presencia aislada no indica una limitación competitiva; conviene verificar proporcionalidad y equivalencias aplicables.",
        ]
    schedule_note = signal.metadata.get("schedule_analysis_note")
    if schedule_note:
        parts.append(str(schedule_note))
    if mitigants:
        parts.append("Se identificaron mitigantes textuales que pueden reducir la prioridad de revisión.")
    if missing:
        parts.append("No se identificó mitigante textual suficiente en el fragmento revisado.")
    if historical.get("rarity") == "Habitual":
        parts.append("El patrón es frecuente en procesos comparables; aislado no debería elevar prioridad.")
    return " ".join(parts)


def _limitations(clause: Clause, historical: dict[str, Any]) -> list[str]:
    limitations = ["Lectura preliminar basada en texto extraído y taxonomía documental."]
    if historical.get("frequency_label") == "No disponible":
        limitations.append("No se cuenta con contexto histórico específico para este patrón.")
    if clause.section_type == "unknown":
        limitations.append("La sección documental no pudo clasificarse con alta precisión.")
    return limitations

