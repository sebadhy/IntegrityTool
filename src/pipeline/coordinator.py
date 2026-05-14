from __future__ import annotations

import pandas as pd
import streamlit as st

from src.analyzer.corpus_loader import (
    analyze_corpus_documents,
    load_corpus_documents,
    validate_corpus_state,
)
from src.analyzer.normative_reference import NORMATIVE_SOURCES
from src.analyzer.prioritizer import top_priorities
from src.analyzer.review_synthesis import build_corpus_context
from src.config import UI_LLM_BALANCE_ROWS, UI_LLM_TOP_FINDINGS
from src.ui.cache import cached_corpus_context
from src.ui.components import LLM_COLUMNS


def prepare_results_dataframe(detections: list) -> pd.DataFrame:
    results_df = pd.DataFrame([detection.to_dict() for detection in detections])
    results_df = results_df.rename(columns={"categoría": "categoría de revisión"})
    for column in LLM_COLUMNS:
        if column not in results_df.columns:
            results_df[column] = "No disponible"
    return results_df


def empty_corpus_payload() -> dict:
    return {
        "total_processes": 0,
        "total_documents": 0,
        "issues": [],
        "validation": {
            "rows": [],
            "summary": {
                "total_documentos_esperados": 0,
                "encontrados": 0,
                "faltantes": 0,
                "inconsistencias": 0,
                "duplicados": 0,
                "coincidencias_ambiguas": 0,
                "metadata_incompleta": 0,
                "errores_naming": 0,
            },
            "has_critical_errors": False,
        },
        "analysis": {},
        "context": {},
    }


def build_normative_context() -> dict:
    return {
        "principios": [
            "concurrencia",
            "igualdad y no discriminación",
            "trato justo",
            "transparencia",
            "mejor valor por dinero",
            "claridad de especificaciones",
            "proporcionalidad",
            "justificación técnica",
            "consistencia documental",
            "uso adecuado de CPC",
        ],
        "fuentes_orientativas": NORMATIVE_SOURCES,
    }


def llm_context_findings(enriched_df: pd.DataFrame) -> list[dict]:
    priority_rows = top_priorities(enriched_df, limit=UI_LLM_TOP_FINDINGS)
    balance_rows = pd.DataFrame()
    if "tipo_señal" in enriched_df.columns:
        balance_rows = enriched_df[
            enriched_df["tipo_señal"].isin(["mitigante_concurrencia", "requisito_habitual"])
        ].drop_duplicates("patrón detectado").head(UI_LLM_BALANCE_ROWS)
    return pd.concat([priority_rows, balance_rows], ignore_index=True).to_dict("records")


def validate_extracted_pages(pages: list) -> None:
    if not pages:
        st.error("No se pudieron leer páginas del PDF. Verifique que el archivo no esté dañado.")
        return

    total_chars = sum(len(page.text.strip()) for page in pages)
    ocr_candidates = [page.page_number for page in pages if getattr(page, "source", "native") == "empty"]
    empty_no_images = [
        page.page_number for page in pages
        if not page.text.strip() and page.page_number not in ocr_candidates
    ]

    if total_chars == 0:
        st.warning(
            (
                "No se extrajo texto seleccionable del PDF. "
                f"{len(ocr_candidates)} página(s) detectadas como imagen sin texto. "
                "Activar OCR en la barra lateral para procesar estas páginas."
            )
            if ocr_candidates else
            "No se extrajo texto seleccionable del PDF. Verifique que el archivo no esté dañado o protegido."
        )
    elif ocr_candidates:
        preview = ", ".join(str(p) for p in ocr_candidates[:8])
        st.info(
            f"{len(ocr_candidates)} página(s) con imágenes sin texto extraído (páginas {preview}). "
            "Activa OCR en la barra lateral para incluirlas en el análisis."
        )
    elif empty_no_images:
        preview = ", ".join(str(p) for p in empty_no_images[:8])
        st.info(f"Páginas sin contenido detectado: {preview}.")


def render_corpus_status() -> dict:
    with st.spinner("Cargando corpus histórico para comparación..."):
        corpus_payload = cached_corpus_context()

    validation = corpus_payload["validation"]
    summary = validation["summary"]

    st.subheader("Estado del corpus documental")
    status_cols = st.columns(5)
    status_cols[0].metric("Documentos esperados", summary["total_documentos_esperados"])
    status_cols[1].metric("Encontrados", summary["encontrados"])
    status_cols[2].metric("Faltantes", summary["faltantes"])
    status_cols[3].metric("Duplicados", summary["duplicados"])
    status_cols[4].metric("Errores de naming", summary["errores_naming"])

    secondary_cols = st.columns(4)
    secondary_cols[0].metric("Procesos cargados", corpus_payload["total_processes"])
    secondary_cols[1].metric("Documentos cargados", corpus_payload["total_documents"])
    secondary_cols[2].metric("Inconsistencias", summary["inconsistencias"])
    secondary_cols[3].metric("Coincidencias ambiguas", summary["coincidencias_ambiguas"])

    if validation["has_critical_errors"]:
        st.warning(
            "El corpus presenta inconsistencias documentales que podrían afectar la "
            "trazabilidad y confiabilidad del análisis."
        )

    with st.expander("Tabla de validación documental", expanded=validation["has_critical_errors"]):
        validation_df = pd.DataFrame(
            validation["rows"],
            columns=[
                "process_id",
                "tipo_documento",
                "archivo_esperado",
                "archivo_encontrado",
                "estado_validacion",
                "observacion",
            ],
        )
        st.dataframe(validation_df, width="stretch", hide_index=True)

    return corpus_payload
