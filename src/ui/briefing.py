from __future__ import annotations

import pandas as pd
import streamlit as st

from src.ui.components import dimension_label, display_list, safe_text


def render_executive_card(title: str, value: str, detail: str = "") -> None:
    st.markdown(
        f"""
            <div class="executive-card">
            <div class="executive-card-title">{safe_text(title)}</div>
            <div class="executive-card-value">{safe_text(value)}</div>
            <div class="executive-card-detail">{safe_text(detail)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_ai_brief_card(title: str, content: object) -> None:
    if isinstance(content, list):
        body = "<ul>" + "".join(f"<li>{safe_text(item)}</li>" for item in content) + "</ul>"
    else:
        body = f"<p>{safe_text(content)}</p>"
    st.markdown(
        f"""
        <div class="ai-card">
            <div class="ai-card-title">{safe_text(title)}</div>
            <div class="ai-card-body">{body}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_ai_document_brief(brief: dict) -> None:
    st.subheader("Lectura preliminar asistida por IA")
    st.markdown(
        '<div class="ai-disclaimer">Los resultados asistidos por IA son insumos preliminares '
        "para revisión humana de neutralidad competitiva. No constituyen dictamen técnico, "
        "legal ni determinación de responsabilidad.</div>",
        unsafe_allow_html=True,
    )
    top_row = st.columns(2)
    with top_row[0]:
        render_ai_brief_card("Resumen del documento", brief["document_summary"])
    with top_row[1]:
        render_ai_brief_card("Nivel general de atención", brief["overall_attention_level"])

    middle_row = st.columns(2)
    with middle_row[0]:
        render_ai_brief_card("Principales temas para revisión", brief["main_review_topics"])
    with middle_row[1]:
        render_ai_brief_card("Contexto comparativo", brief["comparative_context"])

    bottom_row = st.columns(2)
    with bottom_row[0]:
        render_ai_brief_card("Preguntas sugeridas", brief["suggested_human_review_questions"])
    with bottom_row[1]:
        render_ai_brief_card("Nota metodológica", brief["methodological_note"])

    render_ai_brief_card("Posibles efectos sobre concurrencia", brief["possible_competition_effects"])
    render_ai_brief_card("Criterios de priorización destacados", brief["top_priorities_rationale"])


def render_briefing(brief: dict) -> None:
    st.subheader("Resumen ejecutivo")
    first_row = st.columns(3)
    with first_row[0]:
        render_executive_card(
            "Señales sugeridas para revisión",
            str(brief["total_aspects"]),
            "Señales consolidadas y priorizadas",
        )
    with first_row[1]:
        render_executive_card(
            "Nivel general de atención",
            brief["general_attention"],
            "Calculado por rareza, concentración y atención base",
        )
    with first_row[2]:
        rare_text = ", ".join(brief["rare_patterns"]) or "Sin patrones poco frecuentes"
        render_executive_card(
            "Requisitos poco frecuentes",
            str(len(brief["rare_patterns"])),
            rare_text,
        )

    second_row = st.columns(3)
    with second_row[0]:
        render_executive_card(
            "Principales temas",
            str(len(brief["top_themes"])),
            ", ".join(brief["top_themes"]) or "Sin temas predominantes",
        )
    with second_row[1]:
        render_executive_card(
            "Áreas a validar",
            str(len(brief["validation_areas"])),
            "Revisión manual sugerida",
        )
    with second_row[2]:
        render_executive_card(
            "Completitud documental",
            "Revisión documental",
            brief["document_quality_note"],
        )

    st.subheader("Lectura preliminar del documento")
    st.markdown(
        f'<div class="reading-box">{safe_text(brief["general_reading"])}</div>',
        unsafe_allow_html=True,
    )

    if brief["validation_areas"]:
        st.markdown("**Posibles áreas que convendría validar manualmente**")
        for area in brief["validation_areas"]:
            st.markdown(f"- {area}")

    render_analytical_balance(brief)


def render_analytical_balance(brief: dict) -> None:
    st.subheader("Balance analítico")
    cols = st.columns(3)
    with cols[0]:
        render_ai_brief_card(
            "Factores que podrían requerir revisión",
            brief["validation_areas"] or ["Sin factores priorizados con los filtros actuales."],
        )
    with cols[1]:
        mitigants = [
            f"{item['patrón detectado']} (página {item['página']})"
            for item in brief.get("mitigants", [])
        ]
        render_ai_brief_card(
            "Aspectos del documento que favorecen apertura competitiva",
            mitigants or ["No se identificaron mitigantes explícitos con las reglas actuales."],
        )
    with cols[2]:
        habituals = [
            f"{item['patrón detectado']} (página {item['página']})"
            for item in brief.get("habituals", [])
        ]
        render_ai_brief_card(
            "Factores neutros o habituales",
            habituals or ["No se identificaron requisitos habituales con las reglas actuales."],
        )


def render_dimension_summary(enriched_df: pd.DataFrame) -> None:
    st.subheader("Señales por dimensión de competencia")
    if "competition_dimension" not in enriched_df.columns or enriched_df.empty:
        st.info("No hay dimensiones competitivas disponibles para los filtros actuales.")
        return
    review_df = enriched_df[enriched_df.get("tipo_señal", "señal_revision") == "señal_revision"]
    if review_df.empty:
        st.info("No hay señales de revisión para resumir por dimensión competitiva.")
        return
    dimension_counts = review_df["competition_dimension"].fillna("No disponible").value_counts()
    cols = st.columns(min(3, max(1, len(dimension_counts))))
    for index, (dimension, count) in enumerate(dimension_counts.items()):
        with cols[index % len(cols)]:
            render_executive_card(
                dimension_label(dimension),
                str(count),
                "Señales consolidadas asociadas",
            )


def render_analyst_summary(summary: dict) -> None:
    st.subheader("Síntesis del análisis asistido")
    st.markdown(
        '<div class="ai-disclaimer">Esta síntesis es un insumo orientativo para revisión humana. '
        "No constituye dictamen técnico, legal ni determinación de responsabilidad.</div>",
        unsafe_allow_html=True,
    )

    if summary.get("llm_available") is False:
        st.warning(
            f"La síntesis asistida no pudo generarse. Detalle: {summary.get('llm_error', 'No disponible')}"
        )
        return

    render_ai_brief_card("Síntesis general", summary["overall_synthesis"])

    st.markdown("**Áreas que merecen más atención**")
    for item in summary["focus_areas"]:
        st.markdown(
            f"""<div class="reading-box" style="margin-bottom:0.5rem">
            <strong>{safe_text(item['area'])}</strong><br>{safe_text(item['reason'])}
            </div>""",
            unsafe_allow_html=True,
        )

    cols = st.columns(2)
    with cols[0]:
        fp_items = [
            f"**{safe_text(item['signal'])}**: {safe_text(item['reason'])}"
            for item in summary["likely_false_positives"]
        ]
        render_ai_brief_card("Señales que probablemente son ruido (posibles falsos positivos)", fp_items)
    with cols[1]:
        render_ai_brief_card(
            "Qué buscar manualmente (posibles falsos negativos)", summary["possible_false_negatives"]
        )

    render_ai_brief_card("Primeras acciones sugeridas", summary["suggested_first_actions"])


def render_review_questions(enriched_df: pd.DataFrame) -> None:
    questions: list[str] = []
    for column in ("human_review_questions", "suggested_questions", "pregunta_normativa_sugerida"):
        if column not in enriched_df.columns:
            continue
        for value in enriched_df[column]:
            questions.extend(display_list(value))

    unique_questions: list[str] = []
    seen: set[str] = set()
    for question in questions:
        clean = str(question).strip()
        if clean and clean not in seen:
            unique_questions.append(clean)
            seen.add(clean)

    if not unique_questions:
        return

    st.subheader("Preguntas sugeridas para revisión humana")
    for question in unique_questions[:8]:
        st.markdown(f"- {safe_text(question)}")
