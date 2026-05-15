from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import pandas as pd

from .boilerplate_filter import active_clauses, classify_clauses
from .clause_extractor import extract_clauses
from .consolidator import consolidate_candidates
from .contextualizer import build_finding_candidates
from .detector import detect_signals
from .document_segmenter import DocumentSection, segment_document
from .domain_models import Clause, ConsolidatedFinding, FindingCandidate, ReviewItem, Signal
from .parser import parse_pdf_bytes
from .pdf_extractor import PageText
from .prioritizer import prioritize_consolidated_findings
from .relevance_filter import filter_relevant_findings
from .review_item_builder import build_review_items, review_items_to_dataframe


@dataclass
class DocumentReviewResult:
    pages: list[PageText]
    sections: list[DocumentSection]
    clauses: list[Clause] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)
    candidates: list[FindingCandidate] = field(default_factory=list)
    consolidated_findings: list[ConsolidatedFinding] = field(default_factory=list)
    review_items: list[ReviewItem] = field(default_factory=list)
    document_text: str = ""
    results_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    enriched_df: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def detections(self) -> list[Signal]:
        """Backward-compatible alias for older app paths."""
        return self.signals


def analyze_document_bytes(
    pdf_bytes: bytes,
    corpus_context: dict,
    total_processes: int,
    document_name: str,
) -> DocumentReviewResult:
    """Run the deterministic, clause-centric review pipeline.

    PDF -> parsing -> section segmentation -> clause extraction -> boilerplate filtering
    -> signal extraction -> contextualization/mitigants -> consolidation -> relevance
    filtering -> prioritization -> ReviewItem generation.
    """
    document_id = _document_id(document_name, pdf_bytes)
    pages = parse_pdf_bytes(pdf_bytes)
    sections = segment_document(pages)
    clauses = classify_clauses(extract_clauses(pages, sections, document_id))
    document_text = "\n\n".join(page.text for page in pages)

    signals = detect_signals(active_clauses(clauses))
    candidates = build_finding_candidates(signals, clauses, corpus_context)
    consolidated = consolidate_candidates(candidates, clauses, document_id)
    relevant = filter_relevant_findings(consolidated)
    prioritized = prioritize_consolidated_findings(relevant)
    review_items = build_review_items(prioritized)
    review_df = review_items_to_dataframe(review_items, document_name)

    return DocumentReviewResult(
        pages=pages,
        sections=sections,
        clauses=clauses,
        signals=signals,
        candidates=candidates,
        consolidated_findings=prioritized,
        review_items=review_items,
        document_text=document_text,
        results_df=review_df,
        enriched_df=review_df.copy(),
    )


def _document_id(document_name: str, pdf_bytes: bytes) -> str:
    digest = hashlib.sha1(document_name.encode("utf-8") + pdf_bytes[:2048]).hexdigest()[:12]
    return f"doc-{digest}"
