from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ClauseStatus = Literal[
    "active_clause",
    "placeholder",
    "template_text",
    "metadata",
    "index_or_toc",
    "legal_standard_clause",
    "empty_or_no_data",
    "non_substantive_instruction",
]

ReviewPriority = Literal["alta", "media", "baja"]


@dataclass(frozen=True)
class Clause:
    clause_id: str
    document_id: str
    page: int
    section_title: str
    section_type: str
    text: str
    normalized_text: str
    clause_status: ClauseStatus = "active_clause"
    exclude_from_detection: bool = False
    exclusion_reason: str = ""


@dataclass(frozen=True)
class Signal:
    signal_id: str
    clause_id: str
    pattern_id: str
    family: str
    competition_dimension: str
    signal_type: str
    matched_text: str
    evidence_text: str
    page: int
    section_title: str
    detector_name: str
    confidence: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FindingCandidate:
    candidate_id: str
    signals: list[Signal]
    pattern_id: str
    family: str
    competition_dimension: str
    requirement_text: str
    normalized_requirement: str
    evidence: list[dict[str, Any]]
    detected_mitigants: list[str] = field(default_factory=list)
    missing_mitigants: list[str] = field(default_factory=list)
    historical_context: dict[str, Any] = field(default_factory=dict)
    candidate_rationale: str = ""
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ConsolidatedFinding:
    finding_id: str
    family: str
    competition_dimension: str
    normalized_issue: str
    signals: list[Signal]
    clauses: list[Clause]
    evidence_items: list[dict[str, Any]]
    detected_mitigants: list[str]
    historical_context: dict[str, Any]
    consolidation_key: str
    duplicate_count: int
    internal_ranking_score: int
    ranking_factors: list[str]
    pattern_id: str = ""
    title: str = ""
    missing_mitigants: list[str] = field(default_factory=list)
    candidate_rationale: str = ""
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReviewItem:
    review_item_id: str
    title: str
    review_priority: ReviewPriority
    competition_dimension: str
    why_it_matters: str
    evidence_summary: str
    evidence_items: list[dict[str, Any]]
    mitigants_summary: str
    suggested_human_review_question: list[str]
    limitations: list[str]
    source_finding_ids: list[str]
    display_group: str
    allowed_language_only: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
