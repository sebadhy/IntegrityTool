from __future__ import annotations

import ast
import base64
import os
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from src.analyzer.corpus_loader import (
    analyze_corpus_documents,
    load_corpus_documents,
    validate_corpus_state,
)
from src.analyzer.detector import detect_patterns
from src.analyzer.llm_reviewer import (
    explain_priority_with_llm,
    generate_document_brief,
    test_llm_connection,
)
from src.analyzer.normative_reference import NORMATIVE_SOURCES
from src.analyzer.pdf_extractor import extract_text_by_page
from src.analyzer.prioritizer import prioritize_signals, top_priorities
from src.analyzer.review_synthesis import (
    THEME_ORDER,
    build_corpus_context,
    build_executive_brief,
    enrich_review_dataframe,
    theme_summaries,
)


APP_DIR = Path(__file__).parent
STYLE_PATH = APP_DIR / "assets" / "styles.css"

DIMENSION_LABELS = {
    "barrier_to_entry": "Barreras de entrada",
    "vendor_lock_in": "Dependencia de proveedor o fabricante",
    "reduced_market_access": "Acceso reducido al mercado",
    "qualification_restriction": "Restricción de calificación",
    "administrative_burden": "Carga administrativa",
    "geographic_restriction": "Restricción geográfica o presencia local",
    "evaluation_discretion": "Discrecionalidad de evaluación",
    "interoperability_lock_in": "Dependencia por interoperabilidad",
    "timeline_restriction": "Restricción de plazos",
    "financial_restriction": "Restricción financiera",
    "technical_restriction": "Restricción técnica",
    "low_competitive_neutrality": "Baja neutralidad competitiva",
}

LLM_COLUMNS = [
    "llm_explanation",
    "human_review_questions",
    "possible_legitimate_justification",
    "recommended_action",
    "questions_for_reviewer",
]

EXPORT_COLUMNS = [
    "finding_id",
    "title",
    "pattern_id",
    "pattern_name",
    "competition_dimension",
    "dimensión competitiva",
    "document_section",
    "sección documental probable",
    "clause_excerpt",
    "reason_for_review",
    "confidence",
    "review_priority",
    "prioridad de revisión",
    "severity",
    "mitigating_factors",
    "escalation_factors",
    "suggested_questions",
    "human_review_questions",
    "possible_legitimate_justifications",
    "missing_information",
    "suggested_neutral_wording",
    "contextual_notes",
    "prohibited_interpretation",
    "requires_human_review",
    "output_label",
    "signal_id",
    "rule_id",
    "rule_version",
    "timestamp_analisis",
    "engine_version",
    "tipo_señal",
    "frecuencia_corpus",
    "categoria",
    "criterio_normativo",
    "tema de revisión",
    "documento origen",
    "página",
    "categoría de revisión",
    "patrón detectado",
    "atención sugerida",
    "nivel_atencion",
    "relevancia_analitica",
    "criterios_de_priorizacion",
    "explicacion_priorizacion",
    "elementos que favorecen concurrencia",
    "nivel de atención",
    "clasificación histórica",
    "frecuencia en corpus",
    "procesos_con_patron",
    "interpretación_comparativa",
    "número de coincidencias",
    "posible efecto sobre concurrencia",
    "validación sugerida",
    "principio_normativo_relacionado",
    "criterio_normativo_de_revision",
    "pregunta_normativa_sugerida",
    "por qué se sugiere revisar",
    "posible justificación legítima",
    "revisión sugerida",
    "comentario contextual",
    "fragmento textual",
    "observación prudente",
] + LLM_COLUMNS


@st.cache_data(show_spinner=False)
def cached_generate_document_brief(
    document_text: str,
    prioritized_findings: list[dict],
    corpus_context: dict | None,
    normative_context: dict | None,
    model_name: str,
    base_url: str,
) -> dict:
    return generate_document_brief(
        document_text,
        prioritized_findings,
        corpus_context,
        normative_context,
    )


@st.cache_data(show_spinner=False)
def cached_explain_priority_with_llm(
    priority: dict,
    corpus_context: dict | None,
    model_name: str,
    base_url: str,
) -> dict:
    return explain_priority_with_llm(priority, corpus_context)


def corpus_cache_signature() -> tuple[tuple[str, int, int], ...]:
    paths = [APP_DIR / "data" / "raw" / "metadata" / "procesos.csv"]
    for folder in (
        APP_DIR / "data" / "raw" / "pliegos",
        APP_DIR / "data" / "raw" / "especificaciones",
    ):
        if folder.exists():
            paths.extend(sorted(path for path in folder.iterdir() if path.is_file() and path.suffix.lower() == ".pdf"))

    signature = []
    for path in paths:
        if not path.exists():
            signature.append((str(path.relative_to(APP_DIR)), 0, 0))
            continue
        stat = path.stat()
        signature.append((str(path.relative_to(APP_DIR)), int(stat.st_mtime_ns), int(stat.st_size)))
    return tuple(signature)


@st.cache_data(show_spinner=False)
def cached_corpus_context(signature: tuple[tuple[str, int, int], ...]) -> dict:
    validation = validate_corpus_state()
    documents, issues = load_corpus_documents(force=False)
    analysis = analyze_corpus_documents(documents)
    total_processes = len({document.process_id for document in documents})
    return {
        "total_processes": total_processes,
        "total_documents": len(documents),
        "issues": issues,
        "validation": validation,
        "analysis": analysis,
        "context": build_corpus_context(analysis, total_processes),
    }


def load_css() -> None:
    if STYLE_PATH.exists():
        st.markdown(
            f"<style>{STYLE_PATH.read_text(encoding='utf-8')}</style>",
            unsafe_allow_html=True,
        )


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


def ordered_export(df: pd.DataFrame) -> pd.DataFrame:
    export_df = df.loc[:, ~df.columns.duplicated()].copy()
    export_order = _unique_columns(EXPORT_COLUMNS)
    existing_columns = [column for column in export_order if column in export_df.columns]
    remaining_columns = [column for column in export_df.columns if column not in existing_columns]
    return export_df[existing_columns + remaining_columns]


def _unique_columns(columns: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for column in columns:
        if column not in seen:
            unique.append(column)
            seen.add(column)
    return unique


def attention_badge(level: str) -> str:
    css_class = {
        "Alto": "badge-high",
        "Medio": "badge-medium",
        "Bajo": "badge-low",
    }.get(level, "badge-low")
    return f'<span class="attention-badge {css_class}">{level}</span>'


def history_badge(label: str) -> str:
    css_class = {
        "Poco frecuente": "history-rare",
        "Habitual": "history-common",
        "Intermedio": "history-mid",
        "Sin histórico": "history-mid",
    }.get(label, "history-mid")
    return f'<span class="history-badge {css_class}">{label}</span>'


def safe_text(value: object) -> str:
    return escape(str(value))


def dimension_label(value: object) -> str:
    raw_value = str(value or "").strip()
    if not raw_value or raw_value == "No disponible":
        return "No disponible"
    return DIMENSION_LABELS.get(raw_value, raw_value.replace("_", " ").capitalize())


def display_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if _is_useful_text(item)]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if _is_useful_text(item)]
    if isinstance(value, str):
        stripped = value.strip()
        if not _is_useful_text(stripped):
            return []
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                parsed = ast.literal_eval(stripped)
            except (SyntaxError, ValueError):
                return [stripped]
            return display_list(parsed)
        return [stripped]
    return [str(value).strip()] if _is_useful_text(value) else []


def display_joined_list(value: object, fallback: str = "No identificado") -> str:
    items = display_list(value)
    return "; ".join(items) if items else fallback


def _is_useful_text(value: object) -> bool:
    text = str(value).strip()
    return bool(text) and text not in {"[]", "No disponible", "None", "nan"}


def render_institutional_header() -> None:
    st.markdown(
        """
        <div class="institutional-shell">
            <div class="top-strip">
                Sistema de análisis preliminar de neutralidad competitiva
            </div>
            <div class="institutional-header">
                <h1>Asistente exploratorio de neutralidad competitiva en pliegos</h1>
                <div class="institutional-subtitle">
                    Identificación preliminar de requisitos potencialmente limitantes en documentos de contratación pública
                </div>
                <div class="method-box">
                    Las señales identificadas son insumos preliminares para revisión humana
                    de neutralidad competitiva. No constituyen dictamen técnico, legal ni
                    determinación de responsabilidad.
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_pipeline() -> None:
    steps = [
        "Extracción documental",
        "Identificación de cláusulas",
        "Comparación histórica",
        "Consolidación analítica",
        "Lectura asistida por IA",
    ]
    html_steps = "".join(f'<div class="pipeline-step">{step}</div>' for step in steps)
    st.markdown(f'<div class="pipeline">{html_steps}</div>', unsafe_allow_html=True)


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
        render_ai_brief_card(
            "Principales temas para revisión",
            brief["main_review_topics"],
        )
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


def render_review_questions(enriched_df: pd.DataFrame) -> None:
    questions: list[str] = []
    for column in ("human_review_questions", "suggested_questions", "pregunta_normativa_sugerida"):
        if column not in enriched_df.columns:
            continue
        for value in enriched_df[column]:
            questions.extend(display_list(value))

    unique_questions = []
    seen = set()
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




def priority_rank(row: pd.Series) -> tuple[int, int, int]:
    review_order = {"priority": 0, "suggested": 1, "general": 2}
    attention_order = {"Alto": 0, "Medio": 1, "Bajo": 2}
    history_order = {"Poco frecuente": 0, "Sin histórico": 1, "Intermedio": 2, "Habitual": 3}
    return (
        review_order.get(str(row.get("review_priority", "suggested")), 1),
        attention_order.get(str(row.get("atención sugerida", "Medio")), 1),
        history_order.get(str(row.get("clasificación histórica", "Intermedio")), 2),
    )


def reviewable_signals(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    signal_df = df.copy()
    if "tipo_señal" in signal_df.columns:
        signal_df = signal_df[signal_df["tipo_señal"] == "señal_revision"]
    if signal_df.empty:
        return signal_df
    signal_df = signal_df.copy()
    signal_df["_rank"] = signal_df.apply(priority_rank, axis=1)
    return signal_df.sort_values(by="_rank").drop(columns=["_rank"])


def short_fragment(value: object, limit: int = 220) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def selected_signal_id(signal_df: pd.DataFrame) -> str | None:
    if signal_df.empty:
        return None
    current = st.session_state.get("selected_signal_id")
    valid_ids = set(signal_df["signal_id"].astype(str))
    if current in valid_ids:
        return current
    first_id = str(signal_df.iloc[0]["signal_id"])
    st.session_state["selected_signal_id"] = first_id
    return first_id


def selected_signal_row(signal_df: pd.DataFrame) -> pd.Series | None:
    signal_id = selected_signal_id(signal_df)
    if not signal_id:
        return None
    selected = signal_df[signal_df["signal_id"].astype(str) == signal_id]
    if selected.empty:
        return None
    return selected.iloc[0]


def render_signal_queue(signal_df: pd.DataFrame) -> None:
    st.markdown('<div class="workbench-panel-title">Señales</div>', unsafe_allow_html=True)
    st.caption("Top señales para revisar primero")
    if signal_df.empty:
        st.info("No hay señales con los filtros actuales.")
        return

    visible = signal_df.head(5)
    hidden = signal_df.iloc[5:]
    for _, row in visible.iterrows():
        render_signal_queue_item(row)

    if not hidden.empty:
        with st.expander(f"Ver {len(hidden)} señales adicionales", expanded=False):
            for _, row in hidden.iterrows():
                render_signal_queue_item(row)


def render_signal_queue_item(row: pd.Series) -> None:
    signal_id = str(row["signal_id"])
    status = st.session_state.get(f"review_status_{signal_id}", "Pendiente")
    selected = st.session_state.get("selected_signal_id") == signal_id
    css_class = "signal-item selected" if selected else "signal-item"
    st.markdown(
        f"""
        <div class="{css_class}">
            <div class="signal-item-meta">{safe_text(row.get("prioridad de revisión", "revisión sugerida"))} · pág. {safe_text(row["página"])} · {safe_text(status)}</div>
            <div class="signal-item-title">{safe_text(row["patrón detectado"])}</div>
            <div class="signal-item-fragment">{safe_text(short_fragment(row["fragmento textual"], 125))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Abrir señal", key=f"select_{signal_id}", width="stretch"):
        st.session_state["selected_signal_id"] = signal_id
        st.rerun()


def render_pdf_viewer(pdf_bytes: bytes, page_number: int) -> None:
    encoded_pdf = base64.b64encode(pdf_bytes).decode("utf-8")
    st.markdown(
        f"""
        <iframe
            class="pdf-frame"
            src="data:application/pdf;base64,{encoded_pdf}#page={int(page_number)}&zoom=page-width"
            title="Documento PDF"
        ></iframe>
        """,
        unsafe_allow_html=True,
    )


def render_document_workspace(row: pd.Series, pages: list, pdf_bytes: bytes) -> None:
    page_number = int(row.get("página", 1) or 1)
    st.markdown('<div class="workbench-panel-title">Documento</div>', unsafe_allow_html=True)
    st.caption(f"Página {page_number} · evidencia anclada al documento")
    render_pdf_viewer(pdf_bytes, page_number)
    st.markdown(
        f"""
        <div class="evidence-snippet">
            <div class="evidence-label">Fragmento detectado</div>
            <p>{safe_text(row["fragmento textual"])}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.expander("Ver texto extraído de esta página", expanded=False):
        selected_text = next(
            (page.text for page in pages if page.page_number == page_number),
            "No se encontró texto extraído para esta página.",
        )
        st.text_area("Texto de página", value=selected_text, height=260, label_visibility="collapsed")


def render_signal_inspector(row: pd.Series, corpus_context: dict | None = None) -> None:
    signal_id = str(row["signal_id"])
    st.markdown('<div class="workbench-panel-title">Detalle</div>', unsafe_allow_html=True)
    st.markdown(f"**{row['patrón detectado']}**")
    st.caption(
        f"{row.get('prioridad de revisión', 'revisión sugerida')} · "
        f"{dimension_label(row.get('competition_dimension', 'No disponible'))}"
    )

    st.markdown(
        f"""
        <div class="inspector-section compact">
            <strong>Por qué revisar</strong>
            <p>{safe_text(short_fragment(row["por qué se sugiere revisar"], 360))}</p>
        </div>
        <div class="inspector-section compact">
            <strong>Validación sugerida</strong>
            <p>{safe_text(row["validación sugerida"])}</p>
        </div>
        <div class="inspector-section compact">
            <strong>Contexto</strong>
            <p>{safe_text(row["frecuencia en corpus"])} · {safe_text(row["clasificación histórica"])}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("Mitigantes y trazabilidad", expanded=False):
        st.markdown(f"**Mitigantes:** {display_joined_list(row.get('mitigating_factors', []))}")
        st.markdown(f"**Información faltante:** {display_joined_list(row.get('missing_information', []))}")
        st.markdown(f"**Sección probable:** {safe_text(row.get('document_section', 'No determinada'))}")
        st.markdown(f"**ID señal:** `{safe_text(signal_id)}`")

    with st.expander("Criterio normativo orientativo", expanded=False):
        st.markdown(f"**Principio:** {safe_text(row['principio_normativo_relacionado'])}")
        st.markdown(f"**Criterio:** {safe_text(row['criterio_normativo_de_revision'])}")
        st.markdown(f"**Pregunta:** {safe_text(row['pregunta_normativa_sugerida'])}")

    st.markdown("**Acción humana**")
    action_cols = st.columns(2)
    if action_cols[0].button("Confirmar revisión", key=f"confirm_{signal_id}", width="stretch"):
        st.session_state[f"review_status_{signal_id}"] = "Confirmada"
        st.rerun()
    if action_cols[1].button("Descartar", key=f"dismiss_{signal_id}", width="stretch"):
        st.session_state[f"review_status_{signal_id}"] = "Descartada"
        st.rerun()
    if st.button("Marcar seguimiento", key=f"follow_{signal_id}", width="stretch"):
        st.session_state[f"review_status_{signal_id}"] = "Seguimiento"
        st.rerun()
    st.text_area("Comentario de revisión", key=f"review_note_{signal_id}", height=90)

    with st.expander("Explicación asistida por IA", expanded=False):
        if st.button("Generar explicación", key=f"workbench_explain_{signal_id}"):
            if not os.getenv("OPENAI_API_KEY"):
                st.warning(
                    "IA generativa no configurada. La revisión basada en reglas sigue disponible."
                )
            else:
                explanation = cached_explain_priority_with_llm(
                    row.to_dict(),
                    corpus_context,
                    os.getenv("OPENAI_MODEL", ""),
                    os.getenv("OPENAI_BASE_URL", ""),
                )
                render_finding_explanation(explanation)


def render_review_workbench(
    filtered_df: pd.DataFrame,
    pages: list,
    pdf_bytes: bytes,
    corpus_context: dict | None = None,
) -> None:
    signal_df = reviewable_signals(filtered_df)
    selected_row = selected_signal_row(signal_df)
    st.subheader("Mesa de revisión documental")
    st.markdown(
        '<div class="section-note">Revise señales priorizadas, navegue evidencia y deje trazabilidad humana.</div>',
        unsafe_allow_html=True,
    )
    left, center, right = st.columns([0.28, 0.44, 0.28], gap="medium")
    with left:
        render_signal_queue(signal_df)
    with center:
        if selected_row is None:
            st.info("Seleccione una señal para ver evidencia documental.")
        else:
            render_document_workspace(selected_row, pages, pdf_bytes)
    with right:
        if selected_row is None:
            st.info("Seleccione una señal para revisar su detalle.")
        else:
            render_signal_inspector(selected_row, corpus_context)

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
    top_df = top_priorities(priority_df, limit=3)
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


def render_theme_groups(enriched_df: pd.DataFrame, corpus_context: dict | None = None) -> None:
    st.subheader("Señales sugeridas para revisión")
    has_groups = False
    for summary in theme_summaries(enriched_df):
        has_groups = True
        label = (
            f"{summary['theme']} · {summary['count']} señales · "
            f"atención {summary['attention'].lower()}"
        )
        with st.expander(label, expanded=summary["attention"] == "Alto"):
            st.markdown(
                f'<div class="theme-note">{safe_text(summary["priority_comment"])}</div>',
                unsafe_allow_html=True,
            )
            theme_df = summary["dataframe"].copy()
            theme_df["_priority_order"] = theme_df["atención sugerida"].map(
                {"Alto": 0, "Medio": 1, "Bajo": 2}
            )
            theme_df["_history_order"] = theme_df["clasificación histórica"].map(
                {"Poco frecuente": 0, "Sin histórico": 1, "Intermedio": 2, "Habitual": 3}
            )
            theme_df = theme_df.sort_values(by=["_priority_order", "_history_order"])
            for _, row in theme_df.iterrows():
                render_aspect_card(row, corpus_context)
    if not has_groups:
        st.info("No hay señales de revisión en los filtros actuales. Revise el balance analítico para mitigantes o requisitos habituales.")


def render_corpus_status() -> dict:
    with st.spinner("Cargando corpus histórico para comparación..."):
        corpus_payload = cached_corpus_context(corpus_cache_signature())

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


def validate_extracted_pages(pages: list) -> None:
    if not pages:
        st.error("No se pudieron leer páginas del PDF. Verifique que el archivo no esté dañado.")
        return

    empty_pages = [page.page_number for page in pages if not page.text.strip()]
    total_chars = sum(len(page.text.strip()) for page in pages)
    if total_chars == 0:
        st.warning(
            "No se extrajo texto seleccionable del PDF. Es posible que el documento sea escaneado; "
            "OCR no está disponible en esta versión."
        )
    elif empty_pages:
        preview = ", ".join(str(page) for page in empty_pages[:8])
        st.info(
            f"Se detectaron páginas sin texto extraído ({preview}). "
            "Si el PDF contiene imágenes escaneadas, podrían requerir OCR en una versión posterior."
        )


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
    priority_rows = top_priorities(enriched_df, limit=5)
    balance_rows = pd.DataFrame()
    if "tipo_señal" in enriched_df.columns:
        balance_rows = enriched_df[
            enriched_df["tipo_señal"].isin(["mitigante_concurrencia", "requisito_habitual"])
        ].drop_duplicates("patrón detectado").head(8)
    return pd.concat([priority_rows, balance_rows], ignore_index=True).to_dict("records")


def build_executive_report_markdown(
    brief: dict,
    priority_df: pd.DataFrame,
    theme_df: pd.DataFrame,
    ai_brief: dict | None,
) -> str:
    lines = [
        "# Reporte ejecutivo de revisión asistida",
        "",
        "## Advertencia institucional",
        (
            "Las señales identificadas son insumos preliminares para revisión humana de "
            "neutralidad competitiva. No constituyen dictamen técnico, legal ni determinación "
            "de responsabilidad."
        ),
        "",
    ]

    if ai_brief and ai_brief.get("document_summary") != "No disponible":
        lines.extend(
            [
                "## Lectura preliminar asistida por IA",
                ai_brief["document_summary"],
                "",
                f"**Nivel general de atención:** {ai_brief['overall_attention_level']}",
                "",
                "**Temas principales:**",
                *_markdown_list(ai_brief.get("main_review_topics", [])),
                "",
                "**Posibles efectos sobre concurrencia:**",
                ai_brief.get("possible_competition_effects", "No disponible"),
                "",
                "**Contexto comparativo:**",
                ai_brief.get("comparative_context", "No disponible"),
                "",
                "**Preguntas sugeridas:**",
                *_markdown_list(ai_brief.get("suggested_human_review_questions", [])),
                "",
            ]
        )
    else:
        lines.extend(
            [
                "## Resumen ejecutivo",
                brief["general_reading"],
                "",
                f"**Nivel general de atención:** {brief['general_attention']}",
                "",
            ]
        )

    lines.extend(["## Top 3 aspectos prioritarios sugeridos para revisión", ""])
    for index, (_, row) in enumerate(top_priorities(priority_df, limit=3).iterrows(), start=1):
        lines.extend(
            [
                f"### {index}. {row['patrón detectado']}",
                f"- Tema: {row['tema de revisión']}",
                f"- Página: {row['página']}",
                f"- Frecuencia en corpus: {row['frecuencia en corpus']}",
                f"- Por qué se prioriza: {row['explicacion_priorizacion']}",
                f"- Posible efecto sobre concurrencia: {row['posible efecto sobre concurrencia']}",
                f"- Validación sugerida: {row['validación sugerida']}",
                f"- Posible justificación legítima: {row['posible justificación legítima']}",
                f"- Principio normativo relacionado: {row['principio_normativo_relacionado']}",
                f"- Evidencia textual: {row['fragmento textual']}",
                "",
            ]
        )

    lines.extend(["## Balance analítico", ""])
    lines.extend(["### Factores que favorecen apertura competitiva"])
    mitigants = brief.get("mitigants", [])
    if mitigants:
        for item in mitigants:
            lines.append(
                f"- {item['patrón detectado']} (página {item['página']}): {item['observación prudente']}"
            )
    else:
        lines.append("- No se identificaron mitigantes explícitos con las reglas actuales.")

    lines.extend(["", "### Factores neutros o habituales"])
    habituals = brief.get("habituals", [])
    if habituals:
        for item in habituals:
            lines.append(
                f"- {item['patrón detectado']} (página {item['página']}): {item['observación prudente']}"
            )
    else:
        lines.append("- No se identificaron requisitos habituales con las reglas actuales.")
    lines.append("")

    lines.extend(["## Señales agrupadas", ""])
    for summary in theme_summaries(theme_df):
        lines.extend(
            [
                f"### {summary['theme']}",
                f"- Señales: {summary['count']}",
                f"- Nivel general de atención: {summary['attention']}",
                f"- Resumen: {summary['priority_comment']}",
                "",
            ]
        )

    lines.extend(
        [
            "## Nota metodológica",
            (
                "El análisis combina reglas textuales, consolidación de coincidencias, comparación "
                "con corpus histórico local, criterios normativos orientativos y, cuando está activada, "
                "lectura asistida por IA subordinada a las señales ya detectadas."
            ),
            "",
            "La referencia normativa es orientativa y no constituye interpretación legal oficial ni "
            "reemplaza análisis jurídico o técnico.",
        ]
    )
    return "\n".join(lines)


def _markdown_list(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items if str(item).strip()]


def render_llm_test_button() -> None:
    st.sidebar.title("Configuración técnica")
    st.sidebar.subheader("Prueba LLM")
    if st.sidebar.button("Test LLM"):
        ok, message = test_llm_connection()
        if ok:
            st.sidebar.success(message)
        else:
            st.sidebar.warning(message)


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
        detections = detect_patterns(pages)
        document_text = "\n\n".join(page.text for page in pages)

    if not document_text.strip():
        st.stop()

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
    enriched_df = prioritize_signals(enriched_df)
    ai_brief = None

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
            )
        if ai_brief["document_summary"] == "No disponible":
            st.warning(
                "La lectura asistida por IA no estuvo disponible. "
                "Se mantiene el análisis basado en reglas y comparación documental."
            )
        else:
            with st.expander("Lectura asistida por IA", expanded=False):
                render_ai_document_brief(ai_brief)

    st.subheader("Criterios de lectura")
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

    if filtered_df.empty:
        st.warning("No hay señales para los filtros seleccionados.")
    else:
        render_review_workbench(
            filtered_df=filtered_df,
            pages=pages,
            pdf_bytes=uploaded_file_bytes,
            corpus_context=corpus_payload["context"],
        )

    with st.expander("Resumen, metodología y señales agrupadas", expanded=False):
        render_briefing(brief)
        render_dimension_summary(filtered_df)
        render_review_questions(filtered_df)
        if not filtered_df.empty:
            render_theme_groups(filtered_df, corpus_payload["context"])

    with st.expander("Detalle tabular y exportación", expanded=False):
        st.dataframe(ordered_export(filtered_df), width="stretch", hide_index=True)
        csv_data = ordered_export(enriched_df).to_csv(index=False).encode("utf-8")
        st.download_button(
            "Descargar reporte de revisión asistida",
            data=csv_data,
            file_name="reporte_revision_asistida.csv",
            mime="text/csv",
        )
        report_markdown = build_executive_report_markdown(
            brief=brief,
            priority_df=filtered_df,
            theme_df=filtered_df,
            ai_brief=ai_brief,
        )
        st.download_button(
            "Descargar reporte ejecutivo",
            data=report_markdown.encode("utf-8"),
            file_name="reporte_ejecutivo_neutralidad.md",
            mime="text/markdown",
        )


st.set_page_config(
    page_title="Asistente exploratorio de neutralidad competitiva en pliegos",
    layout="wide",
)
load_css()
render_institutional_header()

render_llm_test_button()
render_review_flow()
