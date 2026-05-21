from __future__ import annotations

import ast
import base64
import os
from datetime import datetime
from html import escape
from pathlib import Path

import fitz

import pandas as pd
import streamlit as st

from src.analyzer.corpus_loader import (
    analyze_corpus_documents,
    load_corpus_documents,
    validate_corpus_state,
)
from src.analyzer.exporter import ordered_export
from src.analyzer.feedback_store import save_reviewer_feedback
from src.analyzer.llm_reviewer import (
    extract_pliego_metadata_assisted,
    explain_priority_with_llm,
    test_llm_connection,
)
from src.analyzer.metadata_extractor import (
    apply_assisted_metadata,
    extract_pliego_metadata,
    first_pages_text,
)
from src.analyzer.review_pipeline import analyze_document_bytes
from src.analyzer.review_synthesis import (
    THEME_ORDER,
    build_corpus_context,
    build_executive_brief,
    theme_summaries,
)


APP_DIR = Path(__file__).parent
STYLE_PATH = APP_DIR / "assets" / "styles.css"

DIMENSION_LABELS = {
    "neutralidad_competitiva": "Neutralidad competitiva",
    "proporcionalidad_de_requisitos": "Proporcionalidad de requisitos",
    "barreras_de_entrada": "Barreras de entrada",
    "interoperabilidad_y_compatibilidad": "Interoperabilidad y compatibilidad",
    "relacion_con_objeto_contractual": "Relación con el objeto contractual",
    "trazabilidad_documental": "Trazabilidad documental",
    "transparencia_y_trazabilidad": "Transparencia y trazabilidad",
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


def load_css() -> None:
    if STYLE_PATH.exists():
        st.markdown(
            f"<style>{STYLE_PATH.read_text(encoding='utf-8')}</style>",
            unsafe_allow_html=True,
        )


def attention_badge(level: str) -> str:
    css_class = {
        "Alto": "badge-high",
        "Medio": "badge-medium",
        "Bajo": "badge-low",
    }.get(level, "badge-low")
    return f'<span class="attention-badge {css_class}">{level}</span>'


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
        <div class="top-strip app-strip">Integrity Tool · revisión preliminar de pliegos</div>
        """,
        unsafe_allow_html=True,
    )



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


def render_briefing(brief: dict) -> None:
    st.subheader("Resumen ejecutivo")
    first_row = st.columns(3)
    with first_row[0]:
        render_executive_card(
            "Aspectos sugeridos para revisión",
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


def render_executive_summary(brief: dict) -> None:
    st.subheader("Resumen ejecutivo de la lectura preliminar")
    st.caption("Síntesis breve para orientar qué conviene revisar primero y por qué.")
    themes = ", ".join(brief.get("top_themes", [])[:3]) or "condiciones documentales diversas"
    rare = ", ".join(brief.get("rare_patterns", [])[:3]) or "sin patrones poco frecuentes destacados"
    bullets = [
        f"Se consolidaron {brief.get('total_aspects', 0)} aspectos preliminares para revisión humana.",
        f"Los temas más visibles son: {themes}.",
        f"Respecto del corpus histórico: {rare}.",
        brief.get("document_quality_note", "La lectura es preliminar y depende del texto extraído del documento."),
    ]
    st.markdown(
        "<div class='executive-summary-box'><ul>"
        + "".join(f"<li>{safe_text(item)}</li>" for item in bullets if str(item).strip())
        + "</ul></div>",
        unsafe_allow_html=True,
    )



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
    st.subheader("Observaciones por dimensión de revisión")
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
                "Observaciones asociadas",
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




def review_timeline_key() -> str:
    return "review_timeline"


def append_review_event(action: str, detail: str = "") -> None:
    events = st.session_state.setdefault(review_timeline_key(), [])
    events.append(
        {
            "time": datetime.now().strftime("%H:%M"),
            "action": action,
            "detail": detail,
        }
    )


def render_review_timeline() -> None:
    st.subheader("Historial de revisión")
    events = st.session_state.get(review_timeline_key(), [])
    if not events:
        st.markdown(
            '<div class="timeline-empty">Aún no hay acciones registradas en esta revisión.</div>',
            unsafe_allow_html=True,
        )
        return
    items = "".join(
        f"<li><strong>{safe_text(event['time'])}</strong> — {safe_text(event['action'])} <span>{safe_text(event.get('detail', ''))}</span></li>"
        for event in events[-8:]
    )
    st.markdown(f'<ul class="review-timeline">{items}</ul>', unsafe_allow_html=True)


def set_review_status(row: pd.Series, status: str, note: str = "") -> None:
    signal_id = str(row["signal_id"])
    st.session_state[f"review_status_{signal_id}"] = status
    append_review_event(f"Observación {status.lower()}", str(row.get("patrón detectado", "")))
    save_reviewer_feedback(
        signal=row.to_dict(),
        action=status,
        note=note,
        document_name=str(row.get("documento origen", "")),
    )



def render_document_header(document_name: str, metadata: dict[str, str], signal_count: int) -> object:
    st.markdown(
        f"""
        <div class="document-header-simple">
            <div>
                <div class="doc-label">Documento</div>
                <div class="doc-title">{safe_text(document_name)}</div>
            </div>
            <div>
                <div class="doc-label">Entidad contratante</div>
                <div class="doc-value">{safe_text(metadata.get('entidad', 'No disponible'))}</div>
            </div>
            <div class="doc-object-full">
                <div class="doc-label">Objeto de contratación</div>
                <div class="doc-value">{safe_text(metadata.get('objeto', 'No disponible'))}</div>
            </div>
            <div>
                <div class="doc-label">Procedimiento</div>
                <div class="doc-value">{safe_text(metadata.get('tipo_procedimiento', 'No disponible'))}</div>
            </div>
            <div>
                <div class="doc-label">Presupuesto / fecha</div>
                <div class="doc-value">{safe_text(metadata.get('presupuesto', 'No disponible'))} · {safe_text(metadata.get('fecha', 'No disponible'))}</div>
            </div>
            <div>
                <div class="doc-label">Estado</div>
                <div class="doc-value">Revisión preliminar · {signal_count} observaciones</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    actions = st.columns([0.78, 0.12, 0.10])
    with actions[1]:
        if st.button("Nueva revisión", width="stretch"):
            for key in ["document_processed", "uploaded_file_bytes", "uploaded_file_name", "selected_signal_id", "review_workspace_open", review_timeline_key()]:
                st.session_state.pop(key, None)
            st.rerun()
    return actions[2]


def render_original_document(pdf_bytes: bytes | None) -> None:
    if not pdf_bytes:
        return
    with st.expander("Ver documento original", expanded=False):
        st.caption("Consulta integral del PDF cargado. Se muestra una página a la vez para mantener lectura legible y navegación estable.")
        render_original_pdf_page_viewer(pdf_bytes)



def pdf_page_count(pdf_bytes: bytes) -> int:
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
            return int(document.page_count)
    except Exception:
        return 0


def render_pdf_page_image_bytes(pdf_bytes: bytes, page_number: int, zoom: float = 1.8) -> bytes | None:
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
            if document.page_count == 0:
                return None
            page_index = max(0, min(int(page_number) - 1, document.page_count - 1))
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(float(zoom), float(zoom)), alpha=False)
            return pixmap.tobytes("png")
    except Exception:
        return None


def render_original_pdf_page_viewer(pdf_bytes: bytes) -> None:
    total_pages = pdf_page_count(pdf_bytes)
    if total_pages <= 0:
        st.warning("No se pudo preparar la vista del documento original. La evidencia textual sigue disponible en cada observación.")
        return

    controls = st.columns([0.28, 0.28, 0.44])
    with controls[0]:
        page_number = st.number_input(
            "Página",
            min_value=1,
            max_value=total_pages,
            value=1,
            step=1,
            key="original_pdf_page_number",
        )
    with controls[1]:
        zoom_label = st.selectbox(
            "Zoom",
            options=["Cómodo", "Grande", "Muy grande"],
            index=1,
            key="original_pdf_zoom_label",
        )
    with controls[2]:
        st.caption(f"Documento original · {total_pages} página(s)")

    zoom = {"Cómodo": 1.45, "Grande": 1.9, "Muy grande": 2.35}[zoom_label]
    image_bytes = render_pdf_page_image_bytes(pdf_bytes, int(page_number), zoom)
    if image_bytes:
        st.image(image_bytes, use_container_width=True)
    else:
        st.warning("No se pudo renderizar esta página del PDF.")


def render_pliego_summary(
    metadata: dict[str, str],
    brief: dict,
    filtered_df: pd.DataFrame,
    document_text: str,
    ai_brief: dict | None = None,
    assisted_summary: list[str] | None = None,
) -> None:
    st.subheader("Resumen del pliego")
    st.caption("Lectura breve para orientar la revisión; los datos formales del procedimiento se muestran solo en el encabezado.")
    top_themes = brief.get("top_themes", [])[:3]
    theme_text = ", ".join(top_themes) if top_themes else "condiciones documentales del proceso"
    condition_count = len(reviewable_signals(filtered_df))
    mitigant_count = sum(1 for _, row in filtered_df.iterrows() if display_list(row.get("mitigating_factors", []))) if not filtered_df.empty else 0
    if assisted_summary:
        bullets = contextual_summary_bullets(assisted_summary, metadata, brief, filtered_df)
    elif ai_brief and ai_brief.get("document_summary") != "No disponible":
        ai_topics = display_list(ai_brief.get("main_review_topics", []))[:2]
        bullets = [
            f"La lectura preliminar concentra la revisión en {', '.join(ai_topics) if ai_topics else theme_text}.",
            short_fragment(ai_brief.get("possible_competition_effects", "Algunas condiciones podrían requerir validación de proporcionalidad y necesidad técnica."), 180),
            f"Se identificaron mitigantes textuales en {mitigant_count} aspecto(s), cuando el documento incluye equivalencias, justificaciones o condiciones de apertura.",
            "Las observaciones son insumos preliminares y deben confirmarse con revisión humana.",
        ]
    else:
        bullets = [
            f"Se consolidaron {condition_count} aspectos sugeridos para revisión, principalmente vinculados con {theme_text}.",
            f"La lectura preliminar orienta una revisión contextual de proporcionalidad, equivalencias y posible impacto sobre concurrencia.",
            f"Se identificaron mitigantes textuales en {mitigant_count} aspecto(s), cuando el documento incluye equivalencias, justificaciones o condiciones de apertura.",
            "Esta síntesis prioriza el tipo de revisión sugerida, sin repetir datos formales ya visibles en el encabezado.",
        ]
    html = "".join(f"<li>{safe_text(item)}</li>" for item in bullets[:4] if _is_useful_text(item))
    st.markdown(
        f'<div class="pliego-summary"><div class="summary-label">Lectura preliminar</div><ul>{html}</ul></div>',
        unsafe_allow_html=True,
    )


def contextual_summary_bullets(
    assisted_summary: list[str],
    metadata: dict[str, str],
    brief: dict,
    filtered_df: pd.DataFrame,
) -> list[str]:
    filtered = [
        item
        for item in assisted_summary
        if _is_contextual_summary_item(item, metadata)
    ]
    if len(filtered) >= 2:
        return filtered[:4]
    top_themes = brief.get("top_themes", [])[:3]
    theme_text = ", ".join(top_themes) if top_themes else "condiciones documentales del proceso"
    condition_count = len(reviewable_signals(filtered_df))
    mitigant_count = sum(1 for _, row in filtered_df.iterrows() if display_list(row.get("mitigating_factors", []))) if not filtered_df.empty else 0
    return [
        f"Se consolidaron {condition_count} aspectos sugeridos para revisión, principalmente vinculados con {theme_text}.",
        "La lectura preliminar se enfoca en proporcionalidad, equivalencias, mitigantes y posible impacto sobre concurrencia.",
        f"Se identificaron mitigantes textuales en {mitigant_count} aspecto(s), cuando existen referencias a equivalencias, justificaciones o condiciones de apertura.",
        "La síntesis evita repetir metadata administrativa y se concentra en el tipo de revisión documental sugerida.",
    ]


def _is_contextual_summary_item(item: object, metadata: dict[str, str]) -> bool:
    text = " ".join(str(item or "").split())
    if not _is_useful_text(text):
        return False
    lower = text.lower()
    metadata_markers = [
        "entidad contratante",
        "objeto",
        "procedimiento",
        "presupuesto",
        "modalidad",
        "fecha",
        "corresponde a",
    ]
    if any(marker in lower for marker in metadata_markers):
        return False
    for value in metadata.values():
        clean = " ".join(str(value or "").split()).lower()
        if len(clean) > 18 and clean in lower:
            return False
    return True

def render_explanation_tooltip(text: str) -> None:
    st.caption(text)


def observation_attention(row: pd.Series) -> str:
    return str(row.get("nivel_atencion") or row.get("atención sugerida") or "Media")


def observation_priority(row: pd.Series) -> str:
    return str(row.get("prioridad de revisión") or "revisión sugerida")


def priority_css_class(priority: str) -> str:
    normalized = str(priority).lower()
    if "prioritaria" in normalized or "alta" in normalized:
        return "priority-high"
    if "sugerida" in normalized or "media" in normalized:
        return "priority-medium"
    return "priority-low"


def observation_source(row: pd.Series) -> str:
    aggregated = display_list(row.get("fuentes agregadas", []))
    if aggregated:
        return " + ".join(aggregated)
    has_corpus = str(row.get("frecuencia en corpus", "")).strip() not in {"", "No disponible", "0 de 0 procesos"}
    has_context = str(row.get("signal_type", "")).strip() == "contextual_review_signal"
    if has_corpus and has_context:
        return "Taxonomía documental + corpus histórico"
    if has_corpus:
        return "Taxonomía documental + comparación con corpus"
    if has_context:
        return "Taxonomía documental + revisión contextual"
    return "Taxonomía documental + fragmento del pliego"


def display_bullets(value: object, fallback: str = "No identificado") -> str:
    items = display_list(value)
    if not items:
        items = [fallback]
    return "<ul>" + "".join(f"<li>{safe_text(item)}</li>" for item in items[:4]) + "</ul>"


def corpus_context_sentence(row: pd.Series) -> str:
    classification = str(row.get("clasificación histórica", "No disponible"))
    frequency = str(row.get("frecuencia en corpus", "No disponible"))
    if classification == "Habitual":
        return f"Este patrón aparece frecuentemente en procesos comparables ({frequency}); su presencia aislada no debería elevar la prioridad de revisión."
    if classification == "Poco frecuente":
        return f"Este patrón aparece con baja frecuencia en el corpus disponible ({frequency}); conviene revisar su proporcionalidad en contexto."
    return str(row.get("comentario contextual") or row.get("interpretación_comparativa") or "Contexto comparativo no disponible.")


def integrated_contextual_explanation(row: pd.Series, corpus_context: dict | None = None) -> str:
    fallback = _deterministic_contextual_explanation(row)
    if not os.getenv("OPENAI_API_KEY"):
        return fallback
    explanation = cached_explain_priority_with_llm(
        row.to_dict(),
        corpus_context,
        os.getenv("OPENAI_MODEL", ""),
        os.getenv("OPENAI_BASE_URL", ""),
    )
    if explanation.get("llm_available") is False or explanation.get("llm_error"):
        return fallback
    plain = str(explanation.get("plain_language_explanation") or "").strip()
    why = str(explanation.get("why_it_matters") or "").strip()
    parts = [part for part in [plain, why] if _is_useful_text(part) and "no disponible" not in part.lower()]
    return short_fragment(" ".join(parts), 520) if parts else fallback


def _deterministic_contextual_explanation(row: pd.Series) -> str:
    priority = observation_priority(row)
    dimension = dimension_label(row.get("competition_dimension", row.get("dimensión competitiva", "No disponible")))
    context = corpus_context_sentence(row)
    mitigants = display_list(row.get("mitigating_factors", []))
    mitigation_text = (
        " Se identificaron mitigantes textuales que conviene valorar en contexto."
        if mitigants
        else " No se identificaron mitigantes textuales suficientes en el fragmento representativo."
    )
    return (
        f"Esta observación se presenta como {priority} porque puede requerir validar proporcionalidad "
        f"dentro de la dimensión {dimension}. {context}{mitigation_text}"
    )


def render_human_actions(row: pd.Series, key_prefix: str = "detail") -> None:
    signal_id = str(row["signal_id"])
    note_key = f"review_note_{signal_id}"
    cols = st.columns([0.22, 0.18, 0.22, 0.38])
    if cols[0].button("Confirmar revisión", key=f"{key_prefix}_confirm_{signal_id}", width="stretch"):
        set_review_status(row, "Confirmada", st.session_state.get(note_key, ""))
        st.rerun()
    if cols[1].button("Descartar", key=f"{key_prefix}_dismiss_{signal_id}", width="stretch"):
        set_review_status(row, "Descartada", st.session_state.get(note_key, ""))
        st.rerun()
    if cols[2].button("Marcar seguimiento", key=f"{key_prefix}_follow_{signal_id}", width="stretch"):
        set_review_status(row, "Seguimiento", st.session_state.get(note_key, ""))
        st.rerun()
    with st.expander("Agregar comentario", expanded=False):
        st.text_area("Comentario de revisión", key=note_key, height=90, label_visibility="collapsed")


@st.cache_data(show_spinner=False)
def render_pdf_fragment_bytes(
    pdf_bytes: bytes,
    page_number: int,
    search_text: str,
    fallback_text: str,
) -> bytes | None:
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
            if page_number < 1 or page_number > len(document):
                return None
            page = document[page_number - 1]
            rect = _find_fragment_rect(page, search_text, fallback_text)
            if rect is None:
                return None
            clip = _expanded_clip(rect, page.rect)
            page.draw_rect(rect, color=(0, 0.35, 0.61), width=1.2)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2.6, 2.6), clip=clip, alpha=False)
            return pixmap.tobytes("png")
    except Exception:
        return None


def _find_fragment_rect(page: fitz.Page, search_text: str, fallback_text: str) -> fitz.Rect | None:
    for candidate in _visual_search_candidates(search_text, fallback_text):
        rects = page.search_for(candidate, quads=False)
        if rects:
            return _union_rects(rects[:4])
    return None


def _visual_search_candidates(search_text: str, fallback_text: str) -> list[str]:
    candidates: list[str] = []
    for value in [search_text, fallback_text]:
        clean = " ".join(str(value or "").split())
        if not clean:
            continue
        candidates.append(clean[:120])
        words = [word.strip('.,;:()[]{}"') for word in clean.split() if len(word.strip('.,;:()[]{}"')) > 3]
        for size in (8, 6, 4):
            for start in range(0, max(len(words) - size + 1, 0)):
                phrase = " ".join(words[start:start + size])
                if phrase and phrase not in candidates:
                    candidates.append(phrase)
                if len(candidates) >= 18:
                    return candidates
    return candidates


def _union_rects(rects: list[fitz.Rect]) -> fitz.Rect:
    rect = fitz.Rect(rects[0])
    for item in rects[1:]:
        rect |= item
    return rect


def _expanded_clip(rect: fitz.Rect, page_rect: fitz.Rect) -> fitz.Rect:
    width_padding = max(80, rect.width * 1.2)
    height_padding = max(70, rect.height * 5)
    clip = fitz.Rect(
        rect.x0 - width_padding,
        rect.y0 - height_padding,
        rect.x1 + width_padding,
        rect.y1 + height_padding,
    )
    return clip & page_rect


def render_visual_fragment(row: pd.Series, pdf_bytes: bytes | None) -> None:
    if not pdf_bytes:
        return
    visual_items = visual_fragment_items(row)
    with st.expander("Ver fragmento visual asociado", expanded=False):
        rendered = 0
        for index, item in enumerate(visual_items, start=1):
            page_number = int(item.get("page", 1) or 1)
            label = "Fragmento representativo" if index == 1 else f"Ocurrencia relacionada {index - 1}"
            st.markdown(f"**{label} · página {safe_text(page_number)}**")
            image_bytes = render_pdf_fragment_bytes(
                pdf_bytes,
                page_number,
                str(item.get("search_text") or ""),
                str(item.get("text") or ""),
            )
            if image_bytes:
                st.image(image_bytes, use_container_width=True)
                rendered += 1
            else:
                st.caption("No se pudo ubicar visualmente este fragmento; se conserva la evidencia textual asociada.")
                st.caption(short_fragment(item.get("text", ""), 260))
        if rendered == 0:
            st.caption("No se pudo ubicar automáticamente ningún fragmento dentro del PDF; se conserva la evidencia textual como referencia principal.")


def visual_fragment_items(row: pd.Series) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()

    def add_item(page: object, text: object, search_text: object = "") -> None:
        clean_text = " ".join(str(text or "").split())
        clean_search = " ".join(str(search_text or "").split())
        if not clean_text and not clean_search:
            return
        key = (str(page or ""), clean_text[:220] or clean_search[:220])
        if key in seen:
            return
        seen.add(key)
        items.append({"page": page or 1, "text": clean_text, "search_text": clean_search})

    add_item(
        row.get("página", 1),
        row.get("fragmento textual") or row.get("representative_excerpt"),
        row.get("visual_search_text") or row.get("matched_text"),
    )

    raw_items = row.get("additional_excerpts", row.get("fragmentos adicionales", []))
    if isinstance(raw_items, str):
        try:
            raw_items = ast.literal_eval(raw_items)
        except (ValueError, SyntaxError):
            raw_items = display_list(raw_items)
    if isinstance(raw_items, list):
        for item in raw_items:
            if isinstance(item, dict):
                add_item(item.get("page", row.get("página", 1)), item.get("text", ""), item.get("matched_text", ""))
            else:
                add_item(row.get("página", 1), item, "")

    return items[:6]


def render_reasoning_expander(row: pd.Series) -> None:
    with st.expander("Cómo se generó esta observación", expanded=False):
        for title, items in _methodology_sections(row):
            st.markdown(f"**{safe_text(title)}**")
            st.markdown(
                "<ul>" + "".join(f"<li>{safe_text(item)}</li>" for item in items if str(item).strip()) + "</ul>",
                unsafe_allow_html=True,
            )
        st.caption(
            "Transparencia: esta sección resume reglas, señales y contexto utilizados. "
            "No muestra prompts, trazas internas ni razonamiento libre del modelo."
        )


def _methodology_sections(row: pd.Series) -> list[tuple[str, list[str]]]:
    matched = str(row.get("matched_text") or row.get("patrón detectado") or "No disponible").strip()
    pattern = str(row.get("pattern_name") or row.get("patrón detectado") or "No disponible").strip()
    dimension = dimension_label(row.get("competition_dimension", row.get("dimensión competitiva", "No disponible")))
    priority = observation_priority(row)
    occurrences = row.get("occurrence_count", row.get("número de coincidencias", 1))
    pages = row.get("páginas relacionadas", row.get("página", "No disponible"))
    mitigants = display_list(row.get("mitigating_factors", []))
    missing = display_list(row.get("missing_information", []))
    evidence = short_fragment(row.get("fragmento textual", row.get("representative_excerpt", "No disponible")), 240)
    ai_active = bool(os.getenv("OPENAI_API_KEY"))

    basis = [
        f"Patrón aplicado: {pattern}.",
        f"Dimensión considerada: {dimension}.",
        f"Se consolidaron {occurrences} ocurrencia(s) en la(s) página(s) {pages}.",
    ]
    if matched and matched != "No disponible":
        basis.insert(0, f"Señal textual: {matched}.")

    context = [
        f"Prioridad visible: {priority}. Sirve para ordenar revisión humana, no como conclusión automática.",
        "La observación se evalúa con criterios de proporcionalidad, equivalencias y relación con el objeto contractual.",
    ]
    if mitigants:
        context.append("Mitigantes identificados: " + "; ".join(mitigants[:3]) + ".")
    else:
        context.append("No se identificaron mitigantes textuales suficientes en el fragmento representativo.")

    assisted = (
        "Procesamiento asistido disponible: puede apoyar síntesis o redacción contextual; la señal primaria proviene de reglas, taxonomía y evidencia textual."
        if ai_active
        else "Procesamiento asistido no configurado en este entorno; la observación se generó con reglas, taxonomía y evidencia textual."
    )

    limits = [
        "La lectura depende de la calidad del texto extraído, anexos disponibles, taxonomía configurada y corpus local.",
        "La ausencia de mitigantes textuales no descarta justificaciones técnicas fuera del fragmento analizado.",
        "No constituye dictamen técnico o jurídico ni determinación de ilegalidad, corrupción o direccionamiento.",
    ]
    if missing:
        limits.append("Información a validar: " + "; ".join(missing[:3]) + ".")

    return [
        ("Base documental", basis + [f"Fragmento usado: {evidence}"]),
        ("Contexto aplicado", context),
        ("Uso de procesamiento asistido", [assisted]),
        ("Límites de interpretación", limits),
    ]


def _analytical_dimensions_for_row(row: pd.Series) -> list[str]:
    dimension = dimension_label(row.get("competition_dimension", row.get("dimensión competitiva", "No disponible")))
    base = [
        "Neutralidad competitiva y posible impacto sobre concurrencia.",
        "Proporcionalidad y relación del requisito con el objeto contractual.",
        "Condiciones de equivalencia, apertura o mitigantes textuales.",
    ]
    if dimension != "No disponible":
        base.insert(0, dimension + ".")
    text = " ".join(str(row.get(field, "")) for field in ["patrón detectado", "fragmento textual", "por qué se sugiere revisar"]).lower()
    if "interoper" in text or "compatible" in text or "plataforma" in text:
        base.append("Interoperabilidad, compatibilidad y dependencia técnica.")
    if "certific" in text or "registro" in text or "trazabilidad" in text:
        base.append("Requisitos regulatorios, certificación, trazabilidad o calidad del bien.")
    if "experiencia" in text or "capacidad" in text:
        base.append("Criterios de participación, experiencia o capacidad técnica.")
    return unique_texts(base)


def unique_texts(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        clean = str(value).strip()
        if clean and clean not in seen:
            output.append(clean)
            seen.add(clean)
    return output


def render_evidence_panel(row: pd.Series, pages: list | None = None, pdf_bytes: bytes | None = None) -> None:
    page_number = int(row.get("página", 1) or 1)
    additional_count = len(display_list(row.get("additional_excerpts", row.get("fragmentos adicionales", []))))
    st.markdown(
        f"""
        <div class="evidence-detail-box">
            <div><strong>Evidencia documental</strong><span>Páginas {safe_text(row.get('páginas relacionadas', page_number))}</span></div>
            <div class="evidence-detail-fragment"><strong>Fragmento representativo</strong><p>{safe_text(row['fragmento textual'])}</p></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    raw_items = row.get("additional_excerpts", row.get("fragmentos adicionales", []))
    if additional_count:
        with st.expander(f"Ocurrencias relacionadas ({additional_count})", expanded=False):
            if isinstance(raw_items, list) and raw_items and isinstance(raw_items[0], dict):
                for index, item in enumerate(raw_items, start=1):
                    st.markdown(f"**Ocurrencia {index} · página {safe_text(item.get('page', 'No disponible'))}**")
                    st.write(safe_text(item.get("text", "")))
            else:
                for index, item in enumerate(display_list(raw_items), start=1):
                    st.markdown(f"**Ocurrencia {index}**")
                    st.write(safe_text(item))
    render_visual_fragment(row, pdf_bytes)


def render_observation_detail(
    row: pd.Series,
    pages: list | None = None,
    pdf_bytes: bytes | None = None,
    corpus_context: dict | None = None,
) -> None:
    st.markdown('<div class="observation-detail-panel">', unsafe_allow_html=True)
    render_evidence_panel(row, pages, pdf_bytes)
    st.markdown("**Explicación contextual**")
    st.write(integrated_contextual_explanation(row, corpus_context))
    mitigants = display_list(row.get("mitigating_factors", []))
    if mitigants:
        st.markdown("**Mitigantes identificados**")
        st.markdown(display_bullets(mitigants, "No se identificaron mitigantes cercanos."), unsafe_allow_html=True)
    st.markdown("**Qué conviene validar**")
    questions = row.get("human_review_questions") or row.get("suggested_questions") or row.get("pregunta_normativa_sugerida")
    st.markdown(display_bullets(questions, row.get("validación sugerida", "Validar proporcionalidad y necesidad técnica.")), unsafe_allow_html=True)
    render_reasoning_expander(row)
    st.caption(f"Fuente: {safe_text(observation_source(row))}")
    st.markdown('</div>', unsafe_allow_html=True)

def render_suggested_aspects(
    priority_df: pd.DataFrame,
    pages: list | None = None,
    pdf_bytes: bytes | None = None,
    corpus_context: dict | None = None,
) -> None:
    st.markdown(
        """
        <div class="section-heading">
            <div>
                <div class="section-eyebrow">Revisión humana</div>
                <h2>Aspectos sugeridos para revisión</h2>
            </div>
            <p>Observaciones consolidadas, ordenadas para revisar primero lo más accionable.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    signal_df = reviewable_signals(priority_df)
    if signal_df.empty:
        st.info("No hay aspectos sugeridos para revisión con las reglas actuales.")
        return

    visible_df = signal_df.head(5)
    hidden_df = signal_df.iloc[5:]
    _render_aspect_rows(visible_df, pages, pdf_bytes, corpus_context)
    if not hidden_df.empty:
        with st.expander(f"Ver {len(hidden_df)} aspectos adicionales", expanded=False):
            _render_aspect_rows(hidden_df, pages, pdf_bytes, corpus_context, key_prefix="extra")


def _render_aspect_rows(
    rows_df: pd.DataFrame,
    pages: list | None,
    pdf_bytes: bytes | None,
    corpus_context: dict | None,
    key_prefix: str = "main",
) -> None:
    for position, (_, row) in enumerate(rows_df.iterrows(), start=1):
        priority = observation_priority(row)
        priority_class = priority_css_class(priority)
        pages_label = row.get('páginas relacionadas', row['página'])
        occurrence_label = row.get('occurrence_count', row.get('número de coincidencias', 1))
        dimension = dimension_label(row.get('competition_dimension', row.get('dimensión competitiva', 'No disponible')))
        st.markdown(
            f"""
            <div class="review-item-card">
                <div class="review-item-topline">
                    <span class="review-item-number">{position}</span>
                    <span class="priority-pill {priority_class}">{safe_text(priority)}</span>
                    <span class="review-item-meta">Páginas {safe_text(pages_label)} · {safe_text(occurrence_label)} ocurrencia(s)</span>
                </div>
                <div class="review-item-title">{safe_text(str(row['patrón detectado']))}</div>
                <div class="review-item-dimension">{safe_text(dimension)}</div>
                <div class="review-item-summary">{safe_text(short_fragment(row.get('por qué se sugiere revisar', row.get('observación prudente', 'Requiere validación humana.')), 320))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown('<div class="review-item-body">', unsafe_allow_html=True)
        st.markdown("**Explicación contextual**")
        st.write(integrated_contextual_explanation(row, corpus_context))
        mitigants = display_list(row.get("mitigating_factors", []))
        if mitigants:
            st.markdown('<div class="mitigant-strip"><strong>Mitigantes identificados:</strong> ' + safe_text("; ".join(mitigants[:3])) + '</div>', unsafe_allow_html=True)
        questions = row.get("human_review_questions") or row.get("suggested_questions") or row.get("pregunta_normativa_sugerida")
        st.markdown("**Qué conviene validar**")
        st.markdown(display_bullets(questions, row.get("validación sugerida", "Validar proporcionalidad y necesidad técnica.")), unsafe_allow_html=True)
        render_evidence_panel(row, pages=pages, pdf_bytes=pdf_bytes)
        render_reasoning_expander(row)
        st.caption(f"Fuente: {safe_text(observation_source(row))}")
        st.markdown('</div>', unsafe_allow_html=True)

# Backward-compatible name used by older flow sections.
def render_top_findings(priority_df: pd.DataFrame) -> None:
    render_suggested_aspects(priority_df)

def render_executive_overview(
    *,
    document_name: str,
    metadata: dict[str, str],
    signal_count: int,
    brief: dict,
    priority_df: pd.DataFrame,
    document_text: str,
    ai_brief: dict | None,
    pages: list | None = None,
    pdf_bytes: bytes | None = None,
    corpus_context: dict | None = None,
    assisted_summary: list[str] | None = None,
) -> None:
    render_document_header(document_name, metadata, signal_count)
    render_original_document(pdf_bytes)
    render_pliego_summary(metadata, brief, priority_df, document_text, ai_brief=ai_brief, assisted_summary=assisted_summary)
    render_suggested_aspects(priority_df, pages=pages, pdf_bytes=pdf_bytes, corpus_context=corpus_context)


def render_review_filters(enriched_df: pd.DataFrame) -> pd.DataFrame:
    st.markdown("**Filtrar observaciones**")
    available_themes = [theme for theme in THEME_ORDER if theme in set(enriched_df["tema de revisión"])]
    page_options = sorted(pd.to_numeric(enriched_df["página"], errors="coerce").dropna().astype(int).unique().tolist())
    status_options = ["Pendiente", "Confirmada", "Descartada", "Seguimiento"]
    with st.expander("Filtrar observaciones", expanded=False):
        filter_cols = st.columns(4)
        with filter_cols[0]:
            selected_attention = st.multiselect("Atención sugerida", options=["Alto", "Medio", "Bajo"], default=["Alto", "Medio", "Bajo"])
        with filter_cols[1]:
            selected_themes = st.multiselect("Tema", options=available_themes, default=available_themes)
        with filter_cols[2]:
            selected_status = st.multiselect("Estado de revisión", options=status_options, default=status_options)
        with filter_cols[3]:
            selected_pages = st.multiselect("Página", options=page_options, default=page_options)
    filtered = enriched_df[
        enriched_df["tema de revisión"].isin(selected_themes)
        & enriched_df["atención sugerida"].isin(selected_attention)
    ].copy()
    if selected_pages:
        filtered = filtered[pd.to_numeric(filtered["página"], errors="coerce").astype("Int64").isin(selected_pages)]
    if not filtered.empty:
        filtered["_human_status"] = filtered["signal_id"].astype(str).map(
            lambda signal_id: st.session_state.get(f"review_status_{signal_id}", "Pendiente")
        )
        filtered = filtered[filtered["_human_status"].isin(selected_status)].drop(columns=["_human_status"])
    return filtered


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
    st.markdown('<div class="workbench-panel-title">Observaciones</div>', unsafe_allow_html=True)
    st.caption("Observaciones priorizadas para revisión documental.")
    if signal_df.empty:
        st.info("No hay observaciones con los filtros actuales.")
        return

    visible = signal_df.head(3)
    hidden = signal_df.iloc[3:]
    for _, row in visible.iterrows():
        render_signal_queue_item(row)

    if not hidden.empty:
        with st.expander(f"Ver {len(hidden)} observaciones adicionales", expanded=False):
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
    if st.button("Abrir observación", key=f"select_{signal_id}", width="stretch"):
        st.session_state["selected_signal_id"] = signal_id
        st.rerun()


def render_pdf_viewer(
    pdf_bytes: bytes,
    page_number: int = 1,
    *,
    height: int = 760,
    viewer_class: str = "pdf-frame",
) -> None:
    encoded_pdf = base64.b64encode(pdf_bytes).decode("utf-8")
    pdf_url = f"data:application/pdf;base64,{encoded_pdf}#page={int(page_number)}&zoom=page-width&toolbar=1&navpanes=0"
    st.markdown(
        f"""
        <div class="pdf-viewer-shell" style="height: {int(height)}px;">
            <object
                class="{safe_text(viewer_class)}"
                data="{pdf_url}"
                type="application/pdf"
                aria-label="Documento PDF original"
            >
                <iframe
                    class="{safe_text(viewer_class)}"
                    src="{pdf_url}"
                    title="Documento PDF original"
                ></iframe>
                <p class="pdf-fallback-text">
                    El visor PDF del navegador no está disponible en este entorno.
                    Use la descarga del navegador o revise los fragmentos textuales asociados.
                </p>
            </object>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_document_workspace(row: pd.Series, pages: list, pdf_bytes: bytes) -> None:
    page_number = int(row.get("página", 1) or 1)
    st.markdown('<div class="workbench-panel-title">Evidencia documental</div>', unsafe_allow_html=True)
    st.caption(f"Página {page_number}")
    render_pdf_viewer(pdf_bytes, page_number)
    st.markdown(
        f"""
        <div class="evidence-snippet evidence-primary">
            <div class="evidence-label">Fragmento relacionado</div>
            <p>{safe_text(row["fragmento textual"])}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.expander("Ver texto extraído de la página", expanded=False):
        selected_text = next(
            (page.text for page in pages if page.page_number == page_number),
            "No se encontró texto extraído para esta página.",
        )
        st.text_area("Texto de página", value=selected_text, height=220, label_visibility="collapsed")

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
            <strong>Contexto adicional</strong>
            <p>{safe_text(corpus_context_sentence(row))}</p>
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

    st.caption("La revisión humana se registra fuera de esta PoC. Esta pantalla solo orienta lectura y validación documental.")


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
        '<div class="section-note">Revise el documento y registre una decisión de revisión.</div>',
        unsafe_allow_html=True,
    )
    left, center, right = st.columns([0.18, 0.58, 0.24], gap="medium")
    with left:
        render_signal_queue(signal_df)
    with center:
        if selected_row is None:
            st.info("Seleccione una observación para ver evidencia documental.")
        else:
            render_document_workspace(selected_row, pages, pdf_bytes)
    with right:
        if selected_row is None:
            st.info("Seleccione una observación para revisar su detalle.")
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


def render_aspect_card(row: pd.Series, corpus_context: dict | None = None) -> None:
    st.markdown(
        f"""
        <div class="aspect-card">
            <div class="aspect-card-head">
                <div>
                    <div class="aspect-title">{safe_text(row["patrón detectado"])}</div>
                    <div class="aspect-subtitle">Página {safe_text(row["página"])} · {safe_text(row["categoría de revisión"])}</div>
                </div>
                <div>{attention_badge(row["atención sugerida"])}</div>
            </div>
            <div class="aspect-grid">
                <div><strong>Dimensión competitiva</strong><br>{safe_text(dimension_label(row.get("competition_dimension", "No disponible")))}</div>
                <div><strong>Prioridad de revisión</strong><br>{safe_text(row.get("prioridad de revisión", "revisión sugerida"))}</div>
                <div><strong>Sección probable</strong><br>{safe_text(row.get("document_section", "No determinada"))}</div>
            </div>
            <div class="aspect-section">
                <strong>Por qué se sugiere revisar</strong>
                <p>{safe_text(row["por qué se sugiere revisar"])}</p>
                <p>{safe_text(corpus_context_sentence(row))}</p>
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

def render_theme_groups(enriched_df: pd.DataFrame, corpus_context: dict | None = None) -> None:
    st.subheader("Aspectos sugeridos para revisión")
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



def render_methodological_limitations(validation_messages: list[str]) -> None:
    st.subheader("Limitaciones metodológicas")
    st.caption("La lectura es preliminar y depende de reglas documentales, texto extraído y corpus disponible.")
    limitations = [
        "Los resultados orientan revisión humana y no reemplazan análisis técnico, jurídico o institucional.",
        "La extracción de texto puede omitir información si el PDF contiene imágenes, escaneos o anexos no legibles.",
        "La comparación histórica depende del corpus local disponible y de su trazabilidad documental.",
    ] + validation_messages
    st.markdown("<ul>" + "".join(f"<li>{safe_text(item)}</li>" for item in limitations if str(item).strip()) + "</ul>", unsafe_allow_html=True)



def render_corpus_status(compact: bool = False) -> dict:
    with st.spinner("Cargando corpus histórico para comparación..."):
        corpus_payload = cached_corpus_context(corpus_cache_signature())

    validation = corpus_payload["validation"]
    summary = validation["summary"]

    if compact:
        st.markdown(
            f"Corpus: {corpus_payload['total_processes']} procesos · "
            f"{summary['encontrados']} de {summary['total_documentos_esperados']} documentos encontrados"
        )
        if validation["has_critical_errors"]:
            st.warning(
                "El corpus presenta inconsistencias documentales que podrían afectar la trazabilidad."
            )
        return corpus_payload

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




def render_setup_panel() -> tuple[object | None, bool, bool, bool]:
    st.markdown(
        """
        <div class="setup-hero">
            <div class="setup-kicker">Inicio de revisión</div>
            <h1>Revisar pliego</h1>
            <p>Suba el PDF del pliego y presione Iniciar revisión.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.expander("Qué revisa la herramienta", expanded=False):
        st.markdown(
            """
<div class="methodology-brief">
    <div class="methodology-brief-item">
        <strong>Qué revisa</strong>
        <p>Identifica observaciones preliminares sobre requisitos técnicos, participación, experiencia, plazos, certificaciones, interoperabilidad y condiciones que podrían requerir validación adicional.</p>
    </div>
    <div class="methodology-brief-item">
        <strong>Cómo organiza evidencia</strong>
        <p>Extrae texto del PDF, agrupa fragmentos relacionados, consolida ocurrencias y vincula cada observación con páginas y evidencia verificable.</p>
    </div>
    <div class="methodology-brief-item">
        <strong>Cómo contextualiza</strong>
        <p>Aplica reglas y taxonomías configuradas. Cuando hay corpus disponible, compara patrones para distinguir condiciones habituales de aspectos menos frecuentes.</p>
    </div>
    <div class="methodology-brief-item">
        <strong>Qué dimensiones considera</strong>
        <p>Neutralidad competitiva, proporcionalidad, equivalencias, barreras de entrada, trazabilidad regulatoria, interoperabilidad y relación con el objeto contractual.</p>
    </div>
</div>

<div class="methodology-limits">
    Las observaciones son insumos preliminares para revisión humana. La herramienta no determina ilegalidad, no detecta corrupción, no confirma direccionamiento y no reemplaza análisis técnico o jurídico.
</div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown('<div class="upload-panel"><div class="upload-panel-title">Archivo PDF</div>', unsafe_allow_html=True)
    uploaded_file = st.file_uploader("Documento PDF", type=["pdf"], label_visibility="collapsed")
    process_document = st.button("Iniciar revisión", type="primary", width="stretch")
    st.markdown('</div>', unsafe_allow_html=True)
    return uploaded_file, True, bool(os.getenv("OPENAI_API_KEY")), process_document

def render_review_top_bar(document_name: str, signal_count: int) -> None:
    st.markdown(
        f"""
        <div class="review-topbar">
            <div>
                <div class="review-topbar-label">Documento</div>
                <div class="review-topbar-title">{safe_text(document_name)}</div>
            </div>
            <div>
                <div class="review-topbar-label">Estado</div>
                <div class="review-topbar-value">Revisión preliminar</div>
            </div>
            <div>
                <div class="review-topbar-label">Observaciones priorizadas</div>
                <div class="review-topbar-value">{signal_count}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    actions = st.columns([0.68, 0.16, 0.16])
    with actions[1]:
        if st.button("Nueva revisión", width="stretch"):
            for key in ["document_processed", "uploaded_file_bytes", "uploaded_file_name", "selected_signal_id", "review_workspace_open", review_timeline_key()]:
                st.session_state.pop(key, None)
            st.rerun()
    return actions[2]


def render_technical_details(corpus_payload: dict, validation_messages: list[str]) -> None:
    with st.expander("Detalles técnicos", expanded=False):
        st.markdown("**Etapas:** Lectura del documento · Observaciones preliminares · Detalle técnico")
        if validation_messages:
            for message in validation_messages:
                st.info(message)
        validation = corpus_payload.get("validation", {})
        summary = validation.get("summary", {})
        if summary:
            st.markdown(
                f"Documentos esperados: {summary.get('total_documentos_esperados', 0)} · "
                f"Encontrados: {summary.get('encontrados', 0)} · "
                f"Faltantes: {summary.get('faltantes', 0)} · "
                f"Inconsistencias: {summary.get('inconsistencias', 0)}"
            )
            with st.expander("Tabla de validación documental", expanded=False):
                validation_df = pd.DataFrame(validation.get("rows", []))
                st.dataframe(validation_df, width="stretch", hide_index=True)

def render_review_flow() -> None:
    if not st.session_state.get("document_processed", False):
        uploaded_file, use_historical_corpus, enable_ai_reading, process_document = render_setup_panel()
        if uploaded_file is None:
            return
        if not process_document:
            return

        uploaded_file_bytes = uploaded_file.getvalue()
        st.session_state["uploaded_file_bytes"] = uploaded_file_bytes
        st.session_state["uploaded_file_name"] = uploaded_file.name
        st.session_state["use_historical_corpus"] = use_historical_corpus
        st.session_state["enable_ai_reading"] = enable_ai_reading
        st.session_state["document_processed"] = True
        st.session_state["review_workspace_open"] = False
        st.session_state[review_timeline_key()] = [
            {"time": datetime.now().strftime("%H:%M"), "action": "Revisión preliminar iniciada", "detail": uploaded_file.name}
        ]
        st.session_state.pop("selected_signal_id", None)
        st.rerun()

    uploaded_file_bytes = st.session_state.get("uploaded_file_bytes")
    uploaded_file_name = st.session_state.get("uploaded_file_name", "Documento cargado")
    use_historical_corpus = bool(st.session_state.get("use_historical_corpus", True))
    enable_ai_reading = bool(st.session_state.get("enable_ai_reading", False))
    if not uploaded_file_bytes:
        st.session_state["document_processed"] = False
        st.rerun()

    validation_messages: list[str] = []
    if use_historical_corpus:
        with st.spinner("Preparando procesos comparables..."):
            corpus_payload = cached_corpus_context(corpus_cache_signature())
        if corpus_payload["validation"]["has_critical_errors"]:
            validation_messages.append(
                "El corpus presenta inconsistencias documentales. La comparación histórica puede verse afectada."
            )
    else:
        corpus_payload = empty_corpus_payload()
        validation_messages.append("Comparación con procesos anteriores desactivada para esta revisión.")

    with st.spinner("Preparando mesa de revisión..."):
        try:
            review_result = analyze_document_bytes(
                uploaded_file_bytes,
                corpus_context=corpus_payload["context"],
                total_processes=corpus_payload["total_processes"],
                document_name=uploaded_file_name,
            )
        except Exception:
            st.error("No se pudo leer el PDF. Verifique que el archivo sea válido y no esté protegido.")
            st.stop()

    pages = review_result.pages
    document_text = review_result.document_text
    enriched_df = review_result.enriched_df
    visible_df = enriched_df

    validate_extracted_pages(pages)
    if not document_text.strip():
        st.stop()

    metadata = extract_pliego_metadata(uploaded_file_name, document_text, APP_DIR)

    if review_result.results_df.empty or visible_df.empty:
        render_document_header(uploaded_file_name, metadata, 0)
        render_pliego_summary(metadata, {"top_themes": []}, pd.DataFrame(), document_text)
        st.success("No se identificaron observaciones preliminares priorizadas con las reglas actuales. Puede continuar con revisión manual del documento.")
        render_technical_details(corpus_payload, validation_messages)
        return

    signal_count = len(reviewable_signals(visible_df))
    assisted_summary: list[str] = []
    if enable_ai_reading:
        if not test_llm_connection()[0]:
            validation_messages.append("Análisis asistido no configurado en este entorno.")
        else:
            with st.spinner("Validando metadata y resumen preliminar..."):
                assisted_metadata = extract_pliego_metadata_assisted(
                    document_text=document_text,
                    heuristic_candidates=metadata,
                    first_pages=first_pages_text(pages),
                )
            metadata, assisted_summary = apply_assisted_metadata(metadata, assisted_metadata)

    ai_brief = None

    overview_brief = build_executive_brief(visible_df)
    render_executive_overview(
        document_name=uploaded_file_name,
        metadata=metadata,
        signal_count=signal_count,
        brief=overview_brief,
        priority_df=visible_df,
        document_text=document_text,
        ai_brief=ai_brief,
        pages=pages,
        pdf_bytes=uploaded_file_bytes,
        corpus_context=corpus_payload["context"],
        assisted_summary=assisted_summary,
    )

    filtered_df = visible_df

    render_methodological_limitations(validation_messages)

    with st.expander("Exportar resultados", expanded=False):
        st.caption("Exporta los aspectos sugeridos para revisión en formato tabular.")
        st.dataframe(ordered_export(filtered_df), width="stretch", hide_index=True)
        csv_data = ordered_export(filtered_df).to_csv(index=False).encode("utf-8")
        st.download_button(
            "Descargar CSV",
            data=csv_data,
            file_name="observaciones_preliminares.csv",
            mime="text/csv",
        )

st.set_page_config(
    page_title="Integrity Tool - revisión de pliegos",
    layout="wide",
)
load_css()
render_institutional_header()

render_review_flow()
