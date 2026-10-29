import csv
from pathlib import Path

import pymupdf as fitz
import pytest

from src.analyzer.boilerplate_filter import classify_clauses
from src.analyzer.clause_extractor import extract_clauses
from src.analyzer.consolidator import consolidate_candidates
from src.analyzer.contextualizer import build_finding_candidates
from src.analyzer.detector import detect_signals
from src.analyzer.document_segmenter import segment_document
from src.analyzer.domain_models import ConsolidatedFinding
from src.analyzer.exporter import ordered_export
from src.analyzer.metadata_extractor import document_metadata_from_name
from src.analyzer.metadata_extractor import validate_metadata
from src.analyzer.corpus_loader import load_process_metadata
from src.analyzer.observation_filter import prepare_visible_review_items
from src.analyzer.pdf_extractor import PageText
from src.analyzer.review_item_builder import build_review_items, review_items_to_dataframe
from src.analyzer.review_pipeline import analyze_document_bytes
from src.analyzer.review_pipeline import DocumentReadError, TaxonomyUnavailableError
from src.analyzer.taxonomy_loader import TaxonomyLoadResult


def _clauses(texts):
    pages = [PageText(index, text) for index, text in enumerate(texts, start=1)]
    return classify_clauses(extract_clauses(pages, segment_document(pages), "test-document"))


def _pdf(texts):
    with fitz.open() as document:
        for text in texts:
            page = document.new_page()
            page.insert_textbox(fitz.Rect(36, 36, 559, 800), text, fontsize=10)
        return document.tobytes()


def _analyze(texts):
    return analyze_document_bytes(_pdf(texts), {}, 0, "test.pdf")


@pytest.mark.parametrize("delimiter", [",", ";"])
def test_header_uses_structured_metadata_with_either_csv_delimiter(tmp_path, delimiter):
    path = tmp_path / "data/raw/metadata/procesos.csv"
    path.parent.mkdir(parents=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, delimiter=delimiter, fieldnames=[
            "process_id", "entidad", "objeto", "fecha", "pliego_file", "especificaciones_file",
        ])
        writer.writeheader()
        writer.writerow({
            "process_id": "SIE-TEST-2026-001",
            "entidad": "Hospital de Prueba",
            "objeto": "Adquisición de equipos, repuestos y soporte para todas las unidades",
            "fecha": "2026-08-01",
            "pliego_file": "TEST_PLIEGO.pdf",
            "especificaciones_file": "TEST_ESPECIFICACIONES.pdf",
        })
    metadata = document_metadata_from_name("TEST_PLIEGO.pdf", tmp_path)
    assert metadata["entidad"] == "Hospital de Prueba"
    assert metadata["objeto"] == "Adquisición de equipos, repuestos y soporte para todas las unidades"
    assert load_process_metadata(path)[0]["entidad"] == metadata["entidad"]


def test_header_does_not_choose_an_arbitrary_duplicate_metadata_row(tmp_path):
    path = tmp_path / "data/raw/metadata/procesos.csv"
    path.parent.mkdir(parents=True)
    path.write_text(
        "process_id;entidad;pliego_file\nA;Hospital A;TEST.pdf\nB;Hospital B;TEST.pdf\n",
        encoding="utf-8",
    )
    assert document_metadata_from_name("TEST.pdf", tmp_path)["entidad"] == "No identificado automáticamente"


@pytest.mark.parametrize("text", [
    "No se requiere distribuidor autorizado ni certificación ISO 9001 para el bien ofertado.",
    "No se exigirá distribuidor autorizado para participar en este procedimiento.",
    "No es obligatorio presentar certificado de distribuidor autorizado para el bien.",
    "La certificación ISO 9001 no será requerida para el bien ofertado.",
    "El certificado de distribuidor autorizado no es obligatorio para participar.",
])
def test_negated_requirements_do_not_generate_positive_requirement_signals(text):
    assert detect_signals(_clauses([text])) == []


def test_a_positive_requirement_after_a_contrast_is_still_detected():
    clauses = _clauses([
        "No se requiere experiencia previa, pero se requiere certificación ISO 9001 para el equipo."
    ])
    assert any(signal.pattern_id == "cn-specific-certification" for signal in detect_signals(clauses))


def test_a_later_optional_requirement_does_not_negate_an_earlier_certificate():
    clauses = _clauses(["Se requiere certificación ISO 9001, la garantía no es obligatoria para este bien."])
    assert any(signal.pattern_id == "cn-specific-certification" for signal in detect_signals(clauses))


@pytest.mark.parametrize("acceptance, expected", [
    ("se aceptarán alternativas equivalentes", True),
    ("no se aceptarán alternativas equivalentes", False),
    ("no se admiten alternativas equivalentes", False),
    ("sin alternativas equivalentes", False),
])
def test_equivalence_mitigant_respects_negation(acceptance, expected):
    clauses = _clauses([f"El equipo debe ser marca específica ACME, {acceptance} para esta plataforma."])
    candidates = build_finding_candidates(detect_signals(clauses), clauses, {})
    assert candidates
    mitigants = [factor for candidate in candidates for factor in candidate.detected_mitigants]
    assert ("alternativas equivalentes" in mitigants) is expected


@pytest.mark.parametrize("text", [
    "Debe tener una oficina y personal de campo en Quito antes de participar.",
    "No aplica experiencia previa, pero se requiere certificación ISO 9001 exclusiva del fabricante X.",
    "El sistema debe ser compatible con la plataforma instalada en version 4 y aceptar interoperabilidad.",
])
def test_substantive_content_is_not_removed_by_a_template_word(text):
    assert any(not clause.exclude_from_detection for clause in _clauses([text]))


@pytest.mark.parametrize("text", [
    "Sin datos", "No requerido por la entidad", "No aplica", "N/A", "[●]",
    "Complete aquí", "Especificar si corresponde", "Campo no diligenciado",
])
def test_actual_placeholders_still_remain_excluded(text):
    assert all(clause.exclude_from_detection for clause in _clauses([text]))


def test_repetition_keeps_every_page_without_increasing_priority():
    text = "ESPECIFICACIONES TECNICAS. Se requiere certificacion ISO 9001 para el bien ofertado."
    single = _analyze([text])
    repeated = _analyze([text] * 3)
    pattern = "cn-specific-certification"
    first = next(finding for finding in single.consolidated_findings if finding.pattern_id == pattern)
    second = next(finding for finding in repeated.consolidated_findings if finding.pattern_id == pattern)
    assert first.internal_ranking_score == second.internal_ranking_score
    row = repeated.enriched_df.loc[repeated.enriched_df.pattern_id == pattern].iloc[0]
    assert row["related_pages"] == [1, 2, 3]
    assert row["occurrence_count"] == 3
    assert sorted(item["page"] for item in row["additional_excerpts"]) == [2, 3]


def test_representative_excerpt_keeps_its_own_page_section_and_match():
    finding = ConsolidatedFinding(
        finding_id="finding-test", family="dependencia técnica potencial",
        competition_dimension="interoperability_lock_in", normalized_issue="plataforma",
        signals=[], clauses=[], detected_mitigants=[], historical_context={},
        consolidation_key="test", duplicate_count=2, internal_ranking_score=5,
        ranking_factors=[], pattern_id="cn-interoperability-lock-in", title="Compatibilidad",
        evidence_items=[
            {"page": 2, "section": "Antecedentes", "matched_text": "plataforma",
             "text": "La unidad dispone actualmente de una plataforma para sus actividades."},
            {"page": 26, "section": "Especificaciones técnicas", "matched_text": "compatible con",
             "text": "El equipo debe ser compatible con la plataforma existente de la entidad."},
        ],
    )
    df = prepare_visible_review_items(review_items_to_dataframe(build_review_items([finding]), "doc.pdf"))
    row = df.iloc[0]
    assert row["página"] == 26
    assert row["document_section"] == "Especificaciones técnicas"
    assert row["matched_text"] == "compatible con"
    assert row["related_pages"] == [2, 26]
    assert row["additional_excerpts"][0]["page"] == 2


def test_several_concrete_schedule_intervals_do_not_raise():
    result = _analyze([
        "CRONOGRAMA. Fecha de publicacion: 01/08/2026. Presentacion de ofertas: 03/08/2026.",
        "CRONOGRAMA. Fecha de publicacion: 11/08/2026. Presentacion de ofertas: 13/08/2026.",
    ])
    assert result.signals
    assert all(finding.title for finding in result.consolidated_findings)


def test_optional_technical_visit_is_not_classified_as_mandatory():
    result = _analyze([
        "CRONOGRAMA. Visita tecnica no obligatoria: 02/08/2026. Presentacion de ofertas: 03/08/2026."
    ])
    assert not any(signal.detector_name == "schedule_interval_detector_v1" for signal in result.signals)


def test_goods_authorization_is_general_until_supported_by_restrictive_conditions():
    result = _analyze(["Garantia del fabricante o distribuidor autorizado para los equipos ofertados."])
    row = result.enriched_df.loc[result.enriched_df.pattern_id == "cn-brand-model-provider-reference"].iloc[0]
    assert row["review_priority"] == "general"
    assert "habitual" in row["reason_for_review"].lower()


def test_export_contains_populated_document_and_analysis_provenance():
    result = _analyze(["Debe ser distribuidor autorizado exclusivo del fabricante X."])
    row = ordered_export(result.enriched_df).iloc[0]
    for key in ["rule_id", "rule_version", "timestamp_analisis", "engine_version", "taxonomy_sha256", "document_sha256"]:
        assert row[key] and row[key] != "No disponible"
    assert len(row["document_sha256"]) == 64
    assert len(row["taxonomy_sha256"]) == 64


def test_schedule_evidence_preserves_both_source_pages_and_literal_text():
    texts = ["CRONOGRAMA. Fecha de publicacion: 01/08/2026.",
             "Presentacion de ofertas: 03/08/2026."]
    result = _analyze(texts)
    signals = [signal for signal in result.signals if signal.detector_name == "schedule_interval_detector_v1"]
    assert signals
    assert all(signal.evidence_text in texts[1] for signal in signals)
    item = next(item for item in result.review_items if item.metadata["pattern_id"] == "cn-short-submission-deadline")
    assert {evidence["page"] for evidence in item.evidence_items} == {1, 2}
    assert all(evidence["text"] in texts[evidence["page"] - 1] for evidence in item.evidence_items)


def test_missing_taxonomy_is_not_a_successful_review_without_observations(monkeypatch):
    monkeypatch.setattr("src.analyzer.review_pipeline.load_taxonomy", lambda: TaxonomyLoadResult([], ["No disponible"], False))
    with pytest.raises(TaxonomyUnavailableError, match="taxonomía"):
        _analyze(["Se requiere certificacion ISO 9001 para participar."])


def test_unreadable_pdf_is_distinct_from_an_engine_error():
    with pytest.raises(DocumentReadError, match="PDF"):
        analyze_document_bytes(b"not a PDF", {}, 0, "invalid.pdf")


def test_document_identity_covers_content_after_the_first_2048_bytes():
    from src.analyzer.review_pipeline import _document_id

    prefix = b"A" * 2048
    assert _document_id("same.pdf", prefix + b"one") != _document_id("same.pdf", prefix + b"two")


def test_substantive_software_version_requirement_can_reach_the_visible_result():
    result = _analyze(["El sistema debe ser compatible con plataforma instalada en version 4 y se requiere interoperabilidad."])
    assert not result.enriched_df.empty


def test_explicit_exclusivity_remains_prioritized():
    result = _analyze(["Debe ser distribuidor autorizado exclusivo del fabricante X."])
    row = result.enriched_df.loc[result.enriched_df.pattern_id == "cn-brand-model-provider-reference"].iloc[0]
    assert row["review_priority"] == "priority"


def test_spreadsheet_date_placeholder_is_not_displayed_as_valid_metadata():
    assert validate_metadata({"fecha": "##########"})["fecha"] == "No identificado"
