from __future__ import annotations

import os

import streamlit as st

from src.analyzer.detector import detect_patterns
from src.analyzer.pdf_extractor import (
    detect_document_type,
    document_type_label,
    extract_contract_object,
    extract_text_by_page,
)
from src.analyzer.prioritizer import prioritize_signals
from src.analyzer.review_synthesis import (
    THEME_ORDER,
    build_executive_brief,
    enrich_review_dataframe,
)
from src.pipeline.coordinator import (
    build_normative_context,
    empty_corpus_payload,
    llm_context_findings,
    prepare_results_dataframe,
    render_corpus_status,
    validate_extracted_pages,
)
from src.ui.briefing import (
    render_analyst_summary,
    render_briefing,
    render_ai_document_brief,
    render_dimension_summary,
    render_review_questions,
)
from src.ui.cache import cached_generate_analyst_summary, cached_generate_document_brief
from src.ui.export import (
    build_executive_report_markdown,
    clean_export_dataframe,
    ordered_export,
)
from src.ui.components import safe_text
from src.ui.findings import render_theme_groups, render_top_priorities
from src.ui.header import load_css, render_institutional_header, render_pipeline
from src.analyzer.llm_reviewer import test_llm_connection


def render_llm_test_button() -> None:
    st.sidebar.title("Configuración técnica")
    st.sidebar.subheader("Prueba LLM")
    if st.sidebar.button("Test LLM"):
        ok, message = test_llm_connection()
        if ok:
            st.sidebar.success(message)
        else:
            st.sidebar.warning(message)


def _render_document_header(filename: str, doc_type: str, contract_object: str) -> None:
    label = document_type_label(doc_type)
    obj = contract_object if contract_object and contract_object != "No identificado en las primeras páginas" else "—"
    st.markdown(
        f"""
        <div style="background:#FFFFFF;border:1px solid #D6DEE6;border-left:4px solid #003B70;
                    border-radius:4px;padding:0.85rem 1.1rem;margin-bottom:1rem;">
            <div style="font-size:0.8rem;color:#52606D;text-transform:uppercase;font-weight:700;margin-bottom:0.3rem;">
                Documento analizado
            </div>
            <div style="font-size:1.05rem;font-weight:700;color:#003B70;">{safe_text(filename)}</div>
            <div style="color:#52606D;font-size:0.9rem;margin-top:0.2rem;">
                {safe_text(label)} &nbsp;·&nbsp; {safe_text(obj)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_review_flow() -> None:
    st.subheader("Carga del documento")
    st.markdown(
        '<div class="section-note">Seleccione un PDF para obtener una lectura preliminar '
        "de neutralidad competitiva, priorización temática y comparación histórica integrada.</div>",
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        upload_col, options_col = st.columns([1.4, 1])
        with upload_col:
            uploaded_file = st.file_uploader("Archivo PDF del pliego", type=["pdf"])
        with options_col:
            use_historical_corpus = st.checkbox("Comparar con corpus histórico local", value=True)
            enable_ai_reading = st.checkbox("Activar lectura asistida por IA", value=False)
        process_document = st.button("Iniciar revisión asistida", type="primary")

    if uploaded_file is None:
        st.info("Cargue un archivo PDF para iniciar la revisión de neutralidad competitiva.")
        return

    uploaded_file_bytes = uploaded_file.getvalue()
    upload_signature = (uploaded_file.name, len(uploaded_file_bytes))
    if st.session_state.get("upload_signature") != upload_signature:
        st.session_state["upload_signature"] = upload_signature
        st.session_state["document_processed"] = False

    if process_document:
        st.session_state["document_processed"] = True

    if not st.session_state.get("document_processed", False):
        st.info("Presione Iniciar revisión asistida para procesar el documento.")
        return

    render_pipeline()
    if use_historical_corpus:
        corpus_payload = render_corpus_status()
        if corpus_payload["validation"]["has_critical_errors"]:
            st.stop()
    else:
        corpus_payload = empty_corpus_payload()
        st.info("Comparación histórica desactivada para esta revisión.")

    with st.spinner("Ejecutando flujo de revisión analítica..."):
        try:
            pages = extract_text_by_page(uploaded_file_bytes)
        except Exception:
            st.error(
                "No se pudo leer el PDF. Verifique que el archivo sea válido y no esté protegido."
            )
            st.stop()
        validate_extracted_pages(pages)
        doc_type = detect_document_type(pages)
        detections = detect_patterns(pages)
        document_text = "\n\n".join(page.text for page in pages)
        contract_object = extract_contract_object(pages)

    if not document_text.strip():
        st.stop()

    _render_document_header(uploaded_file.name, doc_type, contract_object)

    if not detections:
        st.success(
            "No se identificaron señales sugeridas por las reglas actuales. "
            "Esto no descarta la necesidad de revisión documental."
        )
        return

    results_df = prepare_results_dataframe(detections)
    enriched_df = enrich_review_dataframe(
        results_df,
        corpus_payload["context"],
        corpus_payload["total_processes"],
    )
    enriched_df["documento origen"] = uploaded_file.name
    enriched_df["tipo_documento"] = doc_type
    enriched_df = prioritize_signals(enriched_df)
    ai_brief = None
    analyst_summary = None

    if enable_ai_reading and not os.getenv("OPENAI_API_KEY"):
        st.warning(
            "IA generativa no configurada. Se muestran resultados basados en reglas "
            "y comparación documental."
        )
    elif enable_ai_reading:
        with st.spinner("Generando lectura preliminar asistida por IA..."):
            ai_brief = cached_generate_document_brief(
                document_text=document_text,
                prioritized_findings=llm_context_findings(enriched_df),
                corpus_context=corpus_payload["context"],
                normative_context=build_normative_context(),
                model_name=os.getenv("OPENAI_MODEL", ""),
                base_url=os.getenv("OPENAI_BASE_URL", ""),
                contract_object=contract_object,
            )
        if ai_brief["document_summary"] == "No disponible":
            st.warning(
                "La lectura asistida por IA no estuvo disponible. "
                "Se mantiene el análisis basado en reglas y comparación documental."
            )
        else:
            render_ai_document_brief(ai_brief)

    with st.container(border=True):
        filter_cols = st.columns(3)
        available_themes = [theme for theme in THEME_ORDER if theme in set(enriched_df["tema de revisión"])]
        with filter_cols[0]:
            selected_themes = st.multiselect("Tema", options=available_themes, default=available_themes)
        with filter_cols[1]:
            selected_attention = st.multiselect(
                "Atención sugerida",
                options=["Alto", "Medio", "Bajo"],
                default=["Alto", "Medio", "Bajo"],
            )
        with filter_cols[2]:
            selected_history = st.multiselect(
                "Clasificación histórica",
                options=sorted(enriched_df["clasificación histórica"].unique()),
                default=sorted(enriched_df["clasificación histórica"].unique()),
            )

    filtered_df = enriched_df[
        enriched_df["tema de revisión"].isin(selected_themes)
        & enriched_df["atención sugerida"].isin(selected_attention)
        & enriched_df["clasificación histórica"].isin(selected_history)
    ]

    brief = build_executive_brief(filtered_df)

    if enable_ai_reading and os.getenv("OPENAI_API_KEY") and not filtered_df.empty:
        with st.spinner("Generando síntesis analítica asistida..."):
            analyst_summary = cached_generate_analyst_summary(
                all_findings=enriched_df.to_dict("records"),
                corpus_context=corpus_payload["context"],
                document_text=document_text,
                contract_object=contract_object,
                model_name=os.getenv("OPENAI_MODEL", ""),
                base_url=os.getenv("OPENAI_BASE_URL", ""),
            )

    tab_resumen, tab_señales, tab_exportar = st.tabs(["Resumen", "Señales", "Exportar"])

    with tab_resumen:
        render_briefing(brief)
        if filtered_df.empty:
            st.warning("No hay señales para los filtros seleccionados.")
        else:
            render_top_priorities(filtered_df, corpus_payload["context"])
        if analyst_summary:
            render_analyst_summary(analyst_summary)

    with tab_señales:
        if filtered_df.empty:
            st.warning("No hay señales para los filtros seleccionados.")
        else:
            render_dimension_summary(filtered_df)
            render_review_questions(filtered_df)
            render_theme_groups(filtered_df, corpus_payload["context"])

    with tab_exportar:
        st.dataframe(ordered_export(filtered_df), use_container_width=True, hide_index=True)
        csv_data = clean_export_dataframe(ordered_export(enriched_df)).to_csv(index=False).encode("utf-8")
        report_markdown = build_executive_report_markdown(
            brief=brief,
            priority_df=filtered_df,
            theme_df=filtered_df,
            ai_brief=ai_brief,
            analyst_summary=analyst_summary,
        )
        dl_cols = st.columns(2)
        dl_cols[0].download_button(
            "Descargar reporte de revisión (CSV)",
            data=csv_data,
            file_name="reporte_revision_asistida.csv",
            mime="text/csv",
        )
        dl_cols[1].download_button(
            "Descargar reporte ejecutivo (Markdown)",
            data=report_markdown.encode("utf-8"),
            file_name="reporte_ejecutivo_neutralidad.md",
            mime="text/markdown",
        )
        with st.expander("Texto extraído por página", expanded=False):
            page_options = [page.page_number for page in pages]
            selected_page = st.selectbox("Seleccionar página", page_options)
            selected_text = next(page.text for page in pages if page.page_number == selected_page)
            st.text_area("Texto extraído", value=selected_text, height=320)


st.set_page_config(
    page_title="Asistente exploratorio de neutralidad competitiva en pliegos",
    layout="wide",
)
load_css()
render_institutional_header()
render_llm_test_button()
render_review_flow()
