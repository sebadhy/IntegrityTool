from __future__ import annotations

import hashlib
import re
from collections import defaultdict

from .domain_models import Clause, ConsolidatedFinding, FindingCandidate, Signal


def consolidate_candidates(
    candidates: list[FindingCandidate],
    clauses: list[Clause],
    document_id: str,
) -> list[ConsolidatedFinding]:
    clause_lookup = {clause.clause_id: clause for clause in clauses}
    grouped: dict[str, list[FindingCandidate]] = defaultdict(list)
    for candidate in candidates:
        grouped[_consolidation_key(candidate, document_id)].append(candidate)

    findings: list[ConsolidatedFinding] = []
    for key, group in grouped.items():
        signals = [signal for candidate in group for signal in candidate.signals]
        group_clauses = [clause_lookup[signal.clause_id] for signal in signals if signal.clause_id in clause_lookup]
        evidence_items = _dedupe_evidence([item for candidate in group for item in candidate.evidence])
        mitigants = _unique([item for candidate in group for item in candidate.detected_mitigants])
        missing = _unique([item for candidate in group for item in candidate.missing_mitigants])
        historical = _choose_historical(group)
        score, factors = _ranking_score(group, mitigants, missing, historical, group_clauses)
        representative = group[0]
        finding_id = hashlib.sha1(f"finding|{key}".encode("utf-8")).hexdigest()[:12]
        findings.append(
            ConsolidatedFinding(
                finding_id=f"finding-{finding_id}",
                family=representative.family,
                competition_dimension=representative.competition_dimension,
                normalized_issue=representative.normalized_requirement[:240],
                signals=signals,
                clauses=group_clauses,
                evidence_items=evidence_items,
                detected_mitigants=mitigants,
                historical_context=historical,
                consolidation_key=key,
                duplicate_count=len(signals),
                internal_ranking_score=score,
                ranking_factors=factors,
                pattern_id=representative.pattern_id,
                title=_finding_title(representative, len(signals)),
                missing_mitigants=missing,
                candidate_rationale=representative.candidate_rationale,
                limitations=_unique([item for candidate in group for item in candidate.limitations]),
            )
        )
    return findings


def _consolidation_key(candidate: FindingCandidate, document_id: str) -> str:
    section_group = _section_group(candidate.evidence[0].get("section", "")) if candidate.evidence else "unknown"
    normalized = _requirement_signature(candidate.normalized_requirement)
    return "|".join([
        document_id,
        candidate.family,
        candidate.competition_dimension,
        candidate.pattern_id,
        section_group,
        normalized,
    ])


def _requirement_signature(text: str) -> str:
    tokens = [token for token in re.findall(r"[a-z0-9áéíóúñü]+", text.lower()) if len(token) > 3]
    stop = {"para", "como", "deber", "debera", "deberá", "sera", "será", "este", "esta", "procedimiento", "contratacion"}
    useful = [token for token in tokens if token not in stop]
    return "-".join(useful[:10]) or "general"


def _section_group(section: str) -> str:
    text = section.lower()
    if "técn" in text or "tecn" in text or "ficha" in text:
        return "technical"
    if "experiencia" in text or "capacidad" in text:
        return "qualification"
    if "cronograma" in text or "plazo" in text:
        return "timeline"
    return "general"


def _dedupe_evidence(items: list[dict]) -> list[dict]:
    seen = set()
    output = []
    for item in items:
        key = (item.get("page"), item.get("clause_id"), item.get("text"))
        if key not in seen:
            output.append(item)
            seen.add(key)
    return output


def _ranking_score(
    group: list[FindingCandidate],
    mitigants: list[str],
    missing: list[str],
    historical: dict,
    clauses: list[Clause],
) -> tuple[int, list[str]]:
    score = 0
    factors: list[str] = []
    if missing:
        score += 3
        factors.append("No se identificó mitigante textual.")
    if mitigants:
        score -= 2
        factors.append("Mitigantes textuales identificados.")
    if historical.get("rarity") == "Poco frecuente":
        score += 3
        factors.append("Baja frecuencia histórica disponible.")
    elif historical.get("rarity") == "Habitual":
        score -= 3
        factors.append("Patrón frecuente en corpus histórico.")
    if any(clause.section_type in {"technical_requirements", "qualification"} for clause in clauses):
        score += 2
        factors.append("Ubicación en sección sustantiva del pliego.")
    if len(group) > 1:
        score += min(len(group), 3)
        factors.append("Múltiples señales relacionadas consolidadas.")
    if any(_mandatory_language(candidate.requirement_text) for candidate in group):
        score += 2
        factors.append("Lenguaje obligatorio en el requisito.")
    return score, factors


def _mandatory_language(text: str) -> bool:
    normalized = text.lower()
    return any(term in normalized for term in ["deberá", "debera", "obligatorio", "se requiere", "debe ser", "solo se acept"])


def _choose_historical(group: list[FindingCandidate]) -> dict:
    return next((candidate.historical_context for candidate in group if candidate.historical_context), {})


def _finding_title(candidate: FindingCandidate, count: int) -> str:
    name = candidate.signals[0].metadata.get("pattern_name") if candidate.signals else "Aspecto sugerido para revisión"
    if count > 1 and ("plazo" in name.lower() or "cronograma" in candidate.family.lower()):
        return "Consideraciones sobre cronograma y plazos"
    return str(name or "Aspecto sugerido para revisión")


def _unique(values: list[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        if value and value not in seen:
            output.append(value)
            seen.add(value)
    return output
