from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd

from . import ENGINE_VERSION
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
from .schedule_analyzer import detect_schedule_signals
from .review_item_builder import build_review_items, review_items_to_dataframe
from .taxonomy_loader import TaxonomyLoadResult, load_taxonomy


class DocumentReadError(ValueError):
    """The PDF could not be parsed; distinct from a rule-engine failure."""


class TaxonomyUnavailableError(RuntimeError):
    """A configured taxonomy is required for a meaningful review."""


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
    validation_messages: list[str] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)

    @property
    def detections(self) -> list[Signal]:
        """Backward-compatible alias for older app paths."""
        return self.signals


def analyze_document_bytes(
    pdf_bytes: bytes,
    corpus_context: dict,
    total_processes: int,
    document_name: str,
    taxonomy_snapshot: TaxonomyLoadResult | None = None,
) -> DocumentReviewResult:
    """Run the deterministic, clause-centric review pipeline.

    PDF -> parsing -> section segmentation -> clause extraction -> boilerplate filtering
    -> signal extraction -> contextualization/mitigants -> consolidation -> prioritization
    -> relevance filtering -> ReviewItem generation.
    """
    document_id = _document_id(document_name, pdf_bytes)
    try:
        pages = parse_pdf_bytes(pdf_bytes)
    except Exception as exc:
        raise DocumentReadError("No se pudo leer el PDF. Verifique que el archivo sea válido y no esté protegido.") from exc
    return analyze_document_pages(pages, corpus_context, document_id, document_name, taxonomy_snapshot)


def analyze_document_pages(
    pages: list[PageText],
    corpus_context: dict | None,
    document_id: str,
    document_name: str,
    taxonomy_snapshot: TaxonomyLoadResult | None = None,
) -> DocumentReviewResult:
    """Shared engine for uploaded PDFs, corpus documents and batch reviews."""
    taxonomy = taxonomy_snapshot if taxonomy_snapshot is not None else load_taxonomy()
    if not taxonomy.loaded or not taxonomy.patterns:
        raise TaxonomyUnavailableError(
            "No se pudo cargar la taxonomía de revisión. No es posible completar el análisis con las reglas configuradas."
        )
    sections = segment_document(pages)
    clauses = classify_clauses(extract_clauses(pages, sections, document_id))
    document_text = "\n\n".join(page.text for page in pages)

    active = active_clauses(clauses)
    signals = detect_signals(active, patterns=taxonomy.patterns) + detect_schedule_signals(active, patterns=taxonomy.patterns)
    candidates = build_finding_candidates(signals, clauses, corpus_context, taxonomy_patterns=taxonomy.patterns)
    prioritized, review_items = finalize_candidates(candidates, clauses, document_id)
    analysis_context = {
        "document_id": document_id,
        "document_sha256": document_id.removeprefix("doc-"),
        "taxonomy_sha256": taxonomy.source_sha256 or "unavailable",
        "rule_version": str(taxonomy.metadata.get("version") or "No disponible"),
        "engine_version": ENGINE_VERSION,
        "timestamp_analisis": datetime.now(timezone.utc).isoformat(),
    }
    review_df = review_items_to_dataframe(review_items, document_name, analysis_context)

    # Visibility and consolidation have already been resolved in the domain layer.
    # DataFrames are compatibility adapters, never a second analytical engine.
    visible_df = review_df.copy()

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
        enriched_df=visible_df,
        validation_messages=taxonomy.messages,
        provenance=analysis_context,
    )


def finalize_candidates(candidates: list[FindingCandidate], clauses: list[Clause], document_id: str
                        ) -> tuple[list[ConsolidatedFinding], list[ReviewItem]]:
    """Shared final stages for rule candidates and evidence-validated proposals."""
    consolidated = consolidate_candidates(candidates, clauses, document_id)
    ranked = prioritize_consolidated_findings(consolidated)
    relevant = filter_relevant_findings(ranked)
    return relevant, build_review_items(relevant)


def _document_id(document_name: str, pdf_bytes: bytes) -> str:
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    return f"doc-{digest}"
