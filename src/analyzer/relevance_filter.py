from __future__ import annotations

from .domain_models import ConsolidatedFinding
from .mitigants import has_strong_mitigant
from .text_utils import is_substantive_evidence_text

RELEVANT_FAMILIES = {
    "criterio potencialmente limitante",
    "requisito de autorización o acreditación sujeto a contexto",
    "requisito de certificación o trazabilidad sujeto a contexto",
    "ausencia de mitigante competitivo",
    "requisito de calificación potencialmente limitante",
    "barrera financiera potencial",
    "restricción temporal potencial",
    "dependencia técnica potencial",
    "referencia técnica potencialmente cerrada",
    "especificación técnica potencialmente cerrada",
}


def filter_relevant_findings(findings: list[ConsolidatedFinding]) -> list[ConsolidatedFinding]:
    visible: list[ConsolidatedFinding] = []
    for finding in findings:
        if not finding.evidence_items or not _has_substantive_evidence(finding):
            continue
        if any(clause.exclude_from_detection for clause in finding.clauses):
            continue
        if finding.family not in RELEVANT_FAMILIES and finding.internal_ranking_score < 4:
            continue
        if not _has_review_question(finding):
            continue
        if _neutralized_by_mitigants(finding):
            continue
        if finding.internal_ranking_score < 1:
            continue
        visible.append(finding)
    return visible


def _has_review_question(finding: ConsolidatedFinding) -> bool:
    for signal in finding.signals:
        questions = signal.metadata.get("taxonomy_pattern", {}).get("human_review_questions", [])
        if questions:
            return True
    return bool(finding.missing_mitigants)


def _neutralized_by_mitigants(finding: ConsolidatedFinding) -> bool:
    historical = finding.historical_context or {}
    return (
        has_strong_mitigant(finding.detected_mitigants)
        and not finding.missing_mitigants
        and finding.internal_ranking_score <= 1
        and historical.get("rarity") == "Habitual"
    )


def _has_substantive_evidence(finding: ConsolidatedFinding) -> bool:
    return any(is_substantive_evidence_text(str(item.get("text", ""))) for item in finding.evidence_items)

