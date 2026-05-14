from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from src.analyzer.prioritizer import top_priorities
from src.analyzer.review_synthesis import THEME_ORDER, theme_summaries
from src.config import UI_REPORT_TOP_PRIORITIES
from src.ui.cache import cached_explain_priority_with_llm
from src.ui.components import (
    FEEDBACK_PATH,
    attention_badge,
    dimension_label,
    display_joined_list,
    display_list,
    history_badge,
    safe_text,
)


def render_finding_explanation(explanation: dict) -> None:
    if explanation.get("llm_available") is False:
        st.warning(
            "La explicación asistida por IA no se pudo generar. "
            f"Detalle: {explanation.get('llm_error', 'No disponible')}"
        )

    questions = display_list(explanation.get("questions_for_reviewer", []))
    questions_html = "<ul>" + "".join(f"<li>{safe_text(item)}</li>" for item in questions) + "</ul>"
    st.markdown(
        f"""
        <div class="ai-finding-box">
            <strong>Explicación en lenguaje claro</strong>
            <p>{safe_text(explanation["plain_language_explanation"])}</p>
            <strong>Por qué importa</strong>
            <p>{safe_text(explanation["why_it_matters"])}</p>
            <strong>Posible justificación legítima</strong>
            <p>{safe_text(explanation["possible_legitimate_justification"])}</p>
            <strong>Acción de revisión sugerida</strong>
            <p>{safe_text(explanation["suggested_review_action"])}</p>
            <strong>Preguntas para revisión humana</strong>
            {questions_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_top_priorities(priority_df: pd.DataFrame, corpus_context: dict | None = None) -> None:
    st.subheader("Aspectos prioritarios sugeridos para revisión")
    top_df = top_priorities(priority_df, limit=UI_REPORT_TOP_PRIORITIES)
    if top_df.empty:
        st.info("No hay prioridades para mostrar con los filtros actuales.")
        return

    for position, (_, row) in enumerate(top_df.iterrows(), start=1):
        with st.container(border=True):
            header_cols = st.columns([0.75, 0.25])
            with header_cols[0]:
                st.markdown(f"**{position}. {row['patrón detectado']}**")
                st.caption(f"{row['tema de revisión']} · página {row['página']}")
                st.caption(f"{safe_text(row.get('prioridad de revisión', 'revisión sugerida'))} · {safe_text(dimension_label(row.get('competition_dimension', 'No disponible')))}")
            with header_cols[1]:
                st.markdown(attention_badge(row["nivel_atencion"]), unsafe_allow_html=True)
                st.caption(f"Relevancia {row['relevancia_analitica']}")

            st.markdown(safe_text(row["explicacion_priorizacion"]))
            detail_cols = st.columns(3)
            detail_cols[0].markdown(f"**Frecuencia en corpus**  \n{safe_text(row['frecuencia en corpus'])}")
            detail_cols[1].markdown(
                f"**Posible efecto sobre concurrencia**  \n{safe_text(row['posible efecto sobre concurrencia'])}"
            )
            detail_cols[2].markdown(
                f"**Validación sugerida**  \n{safe_text(row['validación sugerida'])}"
            )
            if row.get("mitigating_factors"):
                st.markdown(f"**Factores mitigantes identificados**  \n{safe_text(row['mitigating_factors'])}")
            if row.get("missing_information"):
                st.markdown(f"**Información faltante para validar**  \n{safe_text(row['missing_information'])}")
            st.markdown(f"**Posible justificación legítima**  \n{safe_text(row['posible justificación legítima'])}")
            st.markdown(f"**Evidencia textual breve**  \n> {safe_text(row['fragmento textual'])}")

            button_key = f"priority_explain_{row['signal_id']}"
            if st.button("Generar explicación asistida por IA", key=button_key):
                if not os.getenv("OPENAI_API_KEY"):
                    st.warning(
                        "IA generativa no configurada. Se muestran resultados basados en reglas "
                        "y comparación documental."
                    )
                else:
                    explanation = cached_explain_priority_with_llm(
                        row.to_dict(),
                        corpus_context,
                        os.getenv("OPENAI_MODEL", ""),
                        os.getenv("OPENAI_BASE_URL", ""),
                    )
                    render_finding_explanation(explanation)
            render_feedback_buttons(row, context="top")


def render_aspect_card(row: pd.Series, corpus_context: dict | None = None) -> None:
    st.markdown(
        f"""
        <div class="aspect-card">
            <div class="aspect-card-head">
                <div>
                    <div class="aspect-title">{safe_text(row["patrón detectado"])}</div>
                    <div class="aspect-subtitle">Página {safe_text(row["página"])} · {safe_text(row["categoría de revisión"])}</div>
                </div>
                <div>{attention_badge(row["atención sugerida"])} {history_badge(row["clasificación histórica"])}</div>
            </div>
            <div class="aspect-grid">
                <div><strong>Frecuencia histórica</strong><br>{safe_text(row["frecuencia en corpus"])}</div>
                <div><strong>Dimensión competitiva</strong><br>{safe_text(dimension_label(row.get("competition_dimension", "No disponible")))}</div>
                <div><strong>Prioridad de revisión</strong><br>{safe_text(row.get("prioridad de revisión", "revisión sugerida"))}</div>
                <div><strong>Comparación histórica</strong><br>{safe_text(row["comentario contextual"])}</div>
                <div><strong>Posible efecto sobre concurrencia</strong><br>{safe_text(row["posible efecto sobre concurrencia"])}</div>
                <div><strong>Sección probable</strong><br>{safe_text(row.get("document_section", "No determinada"))}</div>
            </div>
            <div class="aspect-section">
                <strong>Por qué se sugiere revisar</strong>
                <p>{safe_text(row["por qué se sugiere revisar"])}</p>
            </div>
            <div class="aspect-section">
                <strong>Posible justificación legítima</strong>
                <p>{safe_text(row["posible justificación legítima"])}</p>
            </div>
            <div class="aspect-section">
                <strong>Fragmento documental</strong>
                <p>{safe_text(row["fragmento textual"])}</p>
                <p><strong>Documento origen:</strong> {safe_text(row.get("documento origen", "Documento cargado"))}</p>
                <p><strong>Página:</strong> {safe_text(row["página"])}</p>
            </div>
            <div class="aspect-section">
                <strong>Factores mitigantes e información faltante</strong>
                <p><strong>Mitigantes:</strong> {safe_text(display_joined_list(row.get("mitigating_factors", [])))}</p>
                <p><strong>Información faltante:</strong> {safe_text(display_joined_list(row.get("missing_information", [])))}</p>
            </div>
            <div class="aspect-section">
                <strong>Revisión sugerida</strong>
                <p>{safe_text(row["revisión sugerida"])}</p>
            </div>
            <div class="aspect-section normative-section">
                <strong>Criterios de revisión normativa</strong>
                <p><strong>Principio relacionado:</strong> {safe_text(row["principio_normativo_relacionado"])}</p>
                <p><strong>Criterio de revisión:</strong> {safe_text(row["criterio_normativo_de_revision"])}</p>
                <p><strong>Pregunta sugerida:</strong> {safe_text(row["pregunta_normativa_sugerida"])}</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    button_key = f"explain_{row.name}_{row['página']}_{row['patrón detectado']}"
    if st.button("Generar explicación asistida por IA", key=button_key):
        if not os.getenv("OPENAI_API_KEY"):
            st.warning(
                "IA generativa no configurada. Se muestran resultados basados en reglas "
                "y comparación documental."
            )
        else:
            explanation = cached_explain_priority_with_llm(
                row.to_dict(),
                corpus_context,
                os.getenv("OPENAI_MODEL", ""),
                os.getenv("OPENAI_BASE_URL", ""),
            )
            render_finding_explanation(explanation)
    render_feedback_buttons(row, context="card")


def render_theme_groups(enriched_df: pd.DataFrame, corpus_context: dict | None = None) -> None:
    st.subheader("Señales sugeridas para revisión")
    has_groups = False
    for summary in theme_summaries(enriched_df):
        has_groups = True
        label = (
            f"{summary['theme']} · {summary['count']} señales · "
            f"Atención {summary['attention']}"
        )
        with st.expander(label, expanded=False):
            theme_df = enriched_df[enriched_df["tema de revisión"] == summary["theme"]]
            for _, row in theme_df.iterrows():
                render_aspect_card(row, corpus_context)
    if not has_groups:
        st.info("No hay señales sugeridas para los filtros seleccionados.")


def render_feedback_buttons(row: pd.Series, context: str = "") -> None:
    signal_id = str(row.get("signal_id", str(row.name)))
    row_idx = str(row.name)
    # State key is stable per signal (shared across render locations for the same signal).
    fb_state_key = f"fb_state_{signal_id}_{row_idx}"
    # Widget key must be globally unique — context differentiates top-priorities vs. theme cards.
    widget_prefix = f"fb_{context}_{signal_id}_{row_idx}"

    if st.session_state.get(fb_state_key):
        st.caption(f"Feedback registrado: {st.session_state[fb_state_key]}")
        return

    st.caption("¿Esta señal requiere revisión?")
    fb_cols = st.columns([1, 1, 1, 3])
    options = [
        (fb_cols[0], "Confirmar", "confirmed", "Voy a revisar esta cláusula"),
        (fb_cols[1], "Descartar", "discarded", "Falso positivo o requisito justificado"),
        (fb_cols[2], "Más contexto", "needs_context", "No puedo decidir con la información disponible"),
    ]
    for col, label, verdict, help_text in options:
        if col.button(label, key=f"{widget_prefix}_{verdict}", help=help_text):
            _save_feedback_case(row, verdict)
            st.session_state[fb_state_key] = label


def _save_feedback_case(row: pd.Series, verdict: str) -> None:
    fragment = str(row.get("fragmento textual", ""))[:200]
    case = {
        "case_id": f"case-{hashlib.sha1(fragment.encode()).hexdigest()[:8]}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "signal_id": str(row.get("signal_id", "")),
        "pattern_id": str(row.get("pattern_id", "")),
        "signal_type": str(row.get("tipo_señal", "señal_revision")),
        "has_mitigants": bool(row.get("mitigating_factors")),
        "rarity": str(row.get("clasificación histórica", "")),
        "attention": str(row.get("nivel_atencion", "")),
        "fragment_preview": fragment,
        "verdict": verdict,
    }
    FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with FEEDBACK_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(case, ensure_ascii=False) + "\n")
