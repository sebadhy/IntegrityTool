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
        return
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
            head_cols = st.columns([0.75, 0.25])
            with head_cols[0]:
                st.markdown(f"**{position}. {safe_text(row['patrón detectado'])}**")
                st.caption(f"{row['tema de revisión']} · Página {row['página']}")
            with head_cols[1]:
                st.markdown(attention_badge(row["nivel_atencion"]), unsafe_allow_html=True)
                st.caption(row["frecuencia en corpus"])

            fragment = str(row.get("fragmento textual", "")).strip()
            if fragment and fragment not in ("No disponible", "nan", "None"):
                st.markdown(f"> *{safe_text(fragment[:500])}*")

            st.markdown(f"**¿Qué revisar?** {safe_text(row['validación sugerida'])}")

            render_feedback_buttons(row, context="top")

            with st.expander("Ver análisis completo"):
                if row.get("explicacion_priorizacion"):
                    st.caption(safe_text(row["explicacion_priorizacion"]))
                detail_cols = st.columns(2)
                detail_cols[0].markdown(
                    f"**Posible efecto sobre concurrencia**  \n{safe_text(row['posible efecto sobre concurrencia'])}"
                )
                detail_cols[1].markdown(
                    f"**Justificación legítima posible**  \n{safe_text(row['posible justificación legítima'])}"
                )
                mitigants = display_joined_list(row.get("mitigating_factors"), fallback="")
                if mitigants:
                    st.markdown(f"**Mitigantes identificados:** {safe_text(mitigants)}")
                missing = display_joined_list(row.get("missing_information"), fallback="")
                if missing:
                    st.markdown(f"**Información faltante para validar:** {safe_text(missing)}")
                dim = dimension_label(row.get("competition_dimension", ""))
                if dim and dim != "No disponible":
                    st.markdown(f"**Dimensión competitiva:** {safe_text(dim)}")
                norm = str(row.get("principio_normativo_relacionado", "")).strip()
                if norm and norm not in ("No disponible", "nan"):
                    st.markdown(f"**Principio normativo:** {safe_text(norm)}")
                st.markdown(f"**Pregunta normativa:** {safe_text(row.get('pregunta_normativa_sugerida', ''))}")

                button_key = f"priority_explain_{row['signal_id']}"
                if not os.getenv("OPENAI_API_KEY"):
                    st.caption("IA no configurada — activa lectura asistida para obtener explicación narrativa.")
                elif st.button("Generar explicación asistida por IA", key=button_key):
                    explanation = cached_explain_priority_with_llm(
                        row.to_dict(),
                        corpus_context,
                        os.getenv("OPENAI_MODEL", ""),
                        os.getenv("OPENAI_BASE_URL", ""),
                    )
                    render_finding_explanation(explanation)


def render_aspect_card(row: pd.Series, corpus_context: dict | None = None) -> None:
    with st.container(border=True):
        head_cols = st.columns([0.75, 0.25])
        with head_cols[0]:
            st.markdown(f"**{safe_text(row['patrón detectado'])}**")
            st.caption(f"Página {safe_text(row['página'])} · {safe_text(row['categoría de revisión'])}")
        with head_cols[1]:
            st.markdown(
                attention_badge(row["atención sugerida"]) + "&nbsp;" + history_badge(row["clasificación histórica"]),
                unsafe_allow_html=True,
            )

        fragment = str(row.get("fragmento textual", "")).strip()
        if fragment and fragment not in ("No disponible", "nan", "None"):
            st.markdown(f"> *{safe_text(fragment[:500])}*")

        st.markdown(f"**¿Qué revisar?** {safe_text(row.get('validación sugerida', row.get('revisión sugerida', '')))}")

        render_feedback_buttons(row, context="card")

        with st.expander("Ver análisis completo"):
            exp = str(row.get("explicacion_priorizacion", "")).strip()
            if exp and exp not in ("No disponible", "nan"):
                st.caption(safe_text(exp))

            detail_cols = st.columns(2)
            detail_cols[0].markdown(
                f"**Frecuencia en corpus**  \n{safe_text(row['frecuencia en corpus'])}"
            )
            detail_cols[1].markdown(
                f"**Posible efecto**  \n{safe_text(row['posible efecto sobre concurrencia'])}"
            )

            why = str(row.get("por qué se sugiere revisar", "")).strip()
            if why and why not in ("No disponible", "nan"):
                st.markdown(f"**Por qué se sugiere revisar**  \n{safe_text(why)}")

            st.markdown(
                f"**Posible justificación legítima**  \n{safe_text(row['posible justificación legítima'])}"
            )

            mitigants = display_joined_list(row.get("mitigating_factors"), fallback="")
            if mitigants:
                st.markdown(f"**Mitigantes:** {safe_text(mitigants)}")
            missing = display_joined_list(row.get("missing_information"), fallback="")
            if missing:
                st.markdown(f"**Información faltante:** {safe_text(missing)}")

            dim = dimension_label(row.get("competition_dimension", ""))
            if dim and dim != "No disponible":
                st.markdown(f"**Dimensión competitiva:** {safe_text(dim)}")

            sec = str(row.get("document_section", row.get("sección documental probable", ""))).strip()
            if sec and sec not in ("No disponible", "nan", "No determinada"):
                st.markdown(f"**Sección:** {safe_text(sec)}")

            norm_cols = st.columns(2)
            norm_cols[0].markdown(
                f"**Principio normativo**  \n{safe_text(row.get('principio_normativo_relacionado', ''))}"
            )
            norm_cols[1].markdown(
                f"**Pregunta sugerida**  \n{safe_text(row.get('pregunta_normativa_sugerida', ''))}"
            )

            button_key = f"explain_{row.name}_{row['página']}_{row['patrón detectado']}"
            if not os.getenv("OPENAI_API_KEY"):
                st.caption("IA no configurada — activa lectura asistida para obtener explicación narrativa.")
            elif st.button("Generar explicación asistida por IA", key=button_key):
                explanation = cached_explain_priority_with_llm(
                    row.to_dict(),
                    corpus_context,
                    os.getenv("OPENAI_MODEL", ""),
                    os.getenv("OPENAI_BASE_URL", ""),
                )
                render_finding_explanation(explanation)


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
    fb_state_key = f"fb_state_{signal_id}_{row_idx}"
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
