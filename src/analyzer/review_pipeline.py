from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .detector import detect_patterns
from .document_segmenter import segment_document
from .exporter import prepare_results_dataframe
from .pdf_extractor import PageText, extract_text_by_page
from .prioritizer import prioritize_signals
from .review_synthesis import enrich_review_dataframe


@dataclass
class DocumentReviewResult:
    pages: list[PageText]
    sections: list
    detections: list
    document_text: str
    results_df: pd.DataFrame
    enriched_df: pd.DataFrame


def analyze_document_bytes(
    pdf_bytes: bytes,
    corpus_context: dict,
    total_processes: int,
    document_name: str,
) -> DocumentReviewResult:
    """Run the deterministic review pipeline before any optional LLM enrichment."""
    pages = extract_text_by_page(pdf_bytes)
    sections = segment_document(pages)
    detections = detect_patterns(pages, sections=sections)
    document_text = "\n\n".join(page.text for page in pages)

    if not detections:
        return DocumentReviewResult(
            pages=pages,
            sections=sections,
            detections=[],
            document_text=document_text,
            results_df=pd.DataFrame(),
            enriched_df=pd.DataFrame(),
        )

    results_df = prepare_results_dataframe(detections)
    enriched_df = enrich_review_dataframe(results_df, corpus_context, total_processes)
    enriched_df["documento origen"] = document_name
    enriched_df = prioritize_signals(enriched_df)

    return DocumentReviewResult(
        pages=pages,
        sections=sections,
        detections=detections,
        document_text=document_text,
        results_df=results_df,
        enriched_df=enriched_df,
    )
