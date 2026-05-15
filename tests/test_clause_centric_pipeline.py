from pathlib import Path

from src.analyzer.boilerplate_filter import active_clauses, classify_clause, classify_clauses
from src.analyzer.clause_extractor import extract_clauses
from src.analyzer.consolidator import consolidate_candidates
from src.analyzer.contextualizer import build_finding_candidates
from src.analyzer.detector import detect_signals
from src.analyzer.document_segmenter import segment_document
from src.analyzer.domain_models import Clause
from src.analyzer.pdf_extractor import PageText
from src.analyzer.prioritizer import prioritize_consolidated_findings
from src.analyzer.relevance_filter import filter_relevant_findings
from src.analyzer.review_item_builder import build_review_items, review_items_to_dataframe

PROHIBITED = [
    "corrupción",
    "fraude",
    "ilegal",
    "direccionamiento detectado",
    "colusión",
    "culpable",
    "responsabilidad",
    "irregularidad comprobada",
]


def _run_text_pipeline(texts, corpus_context=None):
    pages = [PageText(page_number=index, text=text) for index, text in enumerate(texts, start=1)]
    sections = segment_document(pages)
    clauses = classify_clauses(extract_clauses(pages, sections, "doc-test"))
    signals = detect_signals(active_clauses(clauses))
    candidates = build_finding_candidates(signals, clauses, corpus_context or {})
    consolidated = consolidate_candidates(candidates, clauses, "doc-test")
    relevant = filter_relevant_findings(consolidated)
    prioritized = prioritize_consolidated_findings(relevant)
    items = build_review_items(prioritized)
    return clauses, signals, candidates, consolidated, items


def test_boilerplate_filter_excludes_empty_placeholders_from_review_items():
    clause = Clause(
        clause_id="c1",
        document_id="d1",
        page=1,
        section_title="Formulario",
        section_type="forms",
        text="No requerido por la entidad",
        normalized_text="no requerido por la entidad",
    )
    classified = classify_clause(clause)
    assert classified.clause_status == "placeholder"
    assert classified.exclude_from_detection is True

    clauses, signals, _, _, items = _run_text_pipeline(["Sin datos", "No requerido por la entidad"])
    assert all(clause.exclude_from_detection for clause in clauses)
    assert signals == []
    assert items == []


def test_deduplicates_same_certification_across_pages_into_one_review_item():
    texts = [
        "ESPECIFICACIONES TÉCNICAS. Se requiere certificación ISO 9001 para el bien ofertado.",
        "ESPECIFICACIONES TÉCNICAS. Se requiere certificación ISO 9001 para el bien ofertado.",
        "ESPECIFICACIONES TÉCNICAS. Se requiere certificación ISO 9001 para el bien ofertado.",
    ]
    _, signals, _, consolidated, items = _run_text_pipeline(texts)
    cert_signals = [signal for signal in signals if signal.pattern_id == "cn-specific-certification"]
    cert_findings = [finding for finding in consolidated if finding.pattern_id == "cn-specific-certification"]
    cert_items = [item for item in items if item.metadata.get("pattern_id") == "cn-specific-certification"]
    assert len(cert_signals) == 3
    assert len(cert_findings) == 1
    assert cert_findings[0].duplicate_count == 3
    assert len(cert_items) == 1
    assert len(cert_items[0].evidence_items) == 3


def test_brand_with_equivalent_is_not_visible_when_mitigated():
    _, signals, candidates, consolidated, items = _run_text_pipeline([
        "ESPECIFICACIONES TÉCNICAS. Se solicita marca específica ACME o equivalente funcional verificable."
    ])
    assert signals
    assert any(candidate.detected_mitigants for candidate in candidates)
    assert consolidated
    assert items == []


def test_mandatory_low_frequency_without_mitigant_gets_medium_or_high_priority():
    corpus_context = {
        "Requisito de autorización comercial o técnica": {
            "frequency_label": "1 de 24 procesos",
            "rarity": "Poco frecuente",
            "comparative_comment": "Requisito poco frecuente en el corpus disponible.",
            "frequency": 0.04,
        }
    }
    _, _, _, _, items = _run_text_pipeline(
        ["ESPECIFICACIONES TÉCNICAS. Debe ser distribuidor autorizado exclusivo del fabricante X."],
        corpus_context=corpus_context,
    )
    assert items
    assert items[0].review_priority in {"alta", "media"}
    assert "score" not in review_items_to_dataframe(items, "doc.pdf").to_string().lower()


def test_visible_review_item_output_avoids_prohibited_language():
    _, _, _, _, items = _run_text_pipeline([
        "ESPECIFICACIONES TÉCNICAS. Debe ser distribuidor autorizado exclusivo del fabricante X."
    ])
    text = review_items_to_dataframe(items, "doc.pdf").to_string().lower()
    for word in PROHIBITED:
        assert word not in text


def test_regression_same_input_same_visible_output():
    texts = ["ESPECIFICACIONES TÉCNICAS. Debe ser distribuidor autorizado exclusivo del fabricante X."]
    first = review_items_to_dataframe(_run_text_pipeline(texts)[4], "doc.pdf").to_dict("records")
    second = review_items_to_dataframe(_run_text_pipeline(texts)[4], "doc.pdf").to_dict("records")
    assert first == second


def test_streamlit_app_does_not_import_internal_detection_pipeline_modules():
    app_source = Path("app.py").read_text(encoding="utf-8")
    forbidden = [
        "src.analyzer.detector",
        "src.analyzer.mitigants",
        "src.analyzer.consolidator",
        "src.analyzer.relevance_filter",
        "src.analyzer.prioritizer",
        "src.analyzer.observation_filter",
    ]
    for import_path in forbidden:
        assert import_path not in app_source
