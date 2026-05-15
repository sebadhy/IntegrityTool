from __future__ import annotations

import hashlib
import re
from typing import Any

from .domain_models import Clause, FindingCandidate, Signal
from .mitigants import detect_mitigants, missing_mitigants
from .taxonomy_loader import TaxonomyPattern, load_taxonomy


def build_finding_candidates(
    signals: list[Signal],
    clauses: list[Clause],
    corpus_context: dict[str, dict[str, Any]] | None = None,
) -> list[FindingCandidate]:
    pattern_lookup = {pattern.id: pattern for pattern in load_taxonomy().patterns}
    clause_lookup = {clause.clause_id: clause for clause in clauses}
    candidates: list[FindingCandidate] = []
    for signal in signals:
        pattern = pattern_lookup.get(signal.pattern_id)
        clause = clause_lookup.get(signal.clause_id)
        if not pattern or not clause or clause.exclude_from_detection:
            continue
        mitigants = detect_mitigants(signal, clause, pattern)
        missing = missing_mitigants(signal, mitigants)
        historical = _historical_context(pattern, corpus_context or {})
        normalized_requirement = _normalize(signal.evidence_text)
        candidate_id = hashlib.sha1(f"{signal.signal_id}|{normalized_requirement[:160]}".encode("utf-8")).hexdigest()[:12]
        candidates.append(
            FindingCandidate(
                candidate_id=f"cand-{candidate_id}",
                signals=[signal],
                pattern_id=signal.pattern_id,
                family=signal.family,
                competition_dimension=signal.competition_dimension,
                requirement_text=signal.evidence_text,
                normalized_requirement=normalized_requirement,
                evidence=[_evidence_item(signal, clause, pattern)],
                detected_mitigants=mitigants,
                missing_mitigants=missing,
                historical_context=historical,
                candidate_rationale=_candidate_rationale(signal, pattern, mitigants, missing, historical),
                limitations=_limitations(clause, historical),
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
    return corpus_context.get(pattern.name) or corpus_context.get(pattern.id) or {
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


def _normalize(text: str) -> str:
    replacements = str.maketrans("áéíóúñü", "aeiounu")
    return re.sub(r"\s+", " ", text.lower().translate(replacements)).strip()
