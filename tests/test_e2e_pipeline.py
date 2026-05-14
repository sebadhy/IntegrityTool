"""End-to-end pipeline test: synthetic PDF → detection → enrichment → prioritization."""
from __future__ import annotations

import io

import fitz
import pandas as pd
import pytest

from src.analyzer.detector import detect_patterns
from src.analyzer.pdf_extractor import (
    detect_document_type,
    extract_contract_object,
    extract_text_by_page,
)
from src.analyzer.prioritizer import prioritize_signals
from src.analyzer.review_synthesis import build_executive_brief, enrich_review_dataframe
from src.pipeline.coordinator import prepare_results_dataframe


_PLIEGO_TEXT = """
PLIEGO DE CONDICIONES ESPECÍFICAS
PROCESO: SIE-MINEDUC-2024-001

OBJETO DEL CONTRATO:
Adquisición de equipos de laboratorio marca BrandX modelo LX-500.
Los equipos deben contar con certificación ISO 9001 emitida por el fabricante.
El proveedor deberá tener oficina local en Quito previamente a la adjudicación.
Se requiere experiencia mínima de 10 años en el suministro de equipos similares.
El patrimonio mínimo requerido es de USD 500.000.
"""


def _build_pdf_bytes(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), text, fontsize=11)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.fixture(scope="module")
def pipeline_result():
    pdf_bytes = _build_pdf_bytes(_PLIEGO_TEXT)
    pages = extract_text_by_page(pdf_bytes)
    assert pages, "PDF extraction produced no pages"

    doc_type = detect_document_type(pages)
    contract_object = extract_contract_object(pages)
    detections = detect_patterns(pages)

    results_df = prepare_results_dataframe(detections)
    enriched_df = enrich_review_dataframe(results_df, {}, 0)
    enriched_df["documento origen"] = "test_pliego.pdf"
    enriched_df["tipo_documento"] = doc_type
    prioritized_df = prioritize_signals(enriched_df)

    return {
        "pages": pages,
        "doc_type": doc_type,
        "contract_object": contract_object,
        "detections": detections,
        "enriched_df": enriched_df,
        "prioritized_df": prioritized_df,
    }


def test_pdf_extraction_produces_text(pipeline_result):
    pages = pipeline_result["pages"]
    total_chars = sum(len(p.text.strip()) for p in pages)
    assert total_chars > 50, "Expected extracted text from synthetic PDF"


def test_document_type_detected(pipeline_result):
    assert pipeline_result["doc_type"] in {
        "pliego",
        "especificaciones_tecnicas",
        "terminos_referencia",
        "contrato",
        "desconocido",
    }


def test_detections_found(pipeline_result):
    assert len(pipeline_result["detections"]) > 0, "Expected at least one detection in synthetic PDF"


def test_enriched_dataframe_has_required_columns(pipeline_result):
    df = pipeline_result["enriched_df"]
    required = [
        "patrón detectado",
        "página",
        "fragmento textual",
        "tema de revisión",
        "frecuencia en corpus",
        "clasificación histórica",
    ]
    for col in required:
        assert col in df.columns, f"Missing column: {col}"


def test_prioritized_dataframe_has_traceability_fields(pipeline_result):
    df = pipeline_result["prioritized_df"]
    traceability = [
        "signal_id",
        "taxonomy_sha256",
        "nivel_atencion",
        "relevancia_analitica",
        "explicacion_priorizacion",
    ]
    for col in traceability:
        assert col in df.columns, f"Missing traceability column: {col}"


def test_signal_ids_are_unique(pipeline_result):
    df = pipeline_result["prioritized_df"]
    assert df["signal_id"].nunique() == len(df), "signal_id values must be unique per detection"


def test_executive_brief_builds(pipeline_result):
    brief = build_executive_brief(pipeline_result["prioritized_df"])
    assert "total_aspects" in brief
    assert isinstance(brief["total_aspects"], int)
    assert brief["total_aspects"] > 0
    assert "general_attention" in brief
    assert brief["general_attention"] in {"Alto", "Medio", "Bajo"}


def test_no_prohibited_language_in_outputs(pipeline_result):
    df = pipeline_result["prioritized_df"]
    prohibited = ["red flag", "alto riesgo", "hallazgo crítico", "irregularidad detectada"]
    checked = [
        "explicacion_priorizacion",
        "posible efecto sobre concurrencia",
        "validación sugerida",
        "prioridad de revisión",
    ]
    text = " ".join(
        str(v).lower()
        for col in checked
        if col in df.columns
        for v in df[col].tolist()
    )
    for phrase in prohibited:
        assert phrase not in text, f"Prohibited phrase found: '{phrase}'"


def test_page_source_field_present(pipeline_result):
    for page in pipeline_result["pages"]:
        assert hasattr(page, "source")
        assert page.source in {"native", "ocr", "empty"}
