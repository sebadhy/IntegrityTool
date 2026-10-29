from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
from html import escape
from pathlib import Path

import pymupdf as fitz

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from src.analyzer.corpus_loader import (
    analyze_corpus_documents,
    load_corpus_documents,
    validate_corpus_state,
)
from src.analyzer.exporter import ordered_export
from src.analyzer.llm_reviewer import (
    generate_document_brief,
    explain_priority_with_llm,
    _llm_available,
    _provider_name,
    _model,
    PROMPT_VERSION,
)
from src.analyzer.metadata_extractor import (
    extract_pliego_metadata,
)
from notifier import send_alert_email
from src.analyzer.review_pipeline import DocumentReadError, TaxonomyUnavailableError, analyze_document_bytes
from src.analyzer.taxonomy_loader import taxonomy_sha256
from src.analyzer import ENGINE_VERSION
from src.config import APP_CORPUS_METADATA_PATH, APP_CORPUS_PLIEGOS_DIR, APP_CORPUS_ESPECIFICACIONES_DIR
from src.analyzer.review_synthesis import (
    build_corpus_context,
    build_executive_brief,
)


APP_DIR = Path(__file__).parent
STYLE_PATH = APP_DIR / "assets" / "styles.css"
LOGGER = logging.getLogger(__name__)

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


@st.cache_data(show_spinner=False, ttl=300)
def cached_llm_connection_status() -> tuple[bool, str]:
    """Configuration check only; never spends a request to test availability."""
    return _llm_available(), "Disponibilidad según configuración local; conexión no probada."


def render_llm_usage_note(message: str, active: bool = True) -> None:
    css_class = "llm-note-active" if active else "llm-note-inactive"
    st.markdown(
        f'<div class="llm-usage-note {css_class}">{safe_text(message)}</div>',
        unsafe_allow_html=True,
    )


def corpus_cache_signature() -> tuple[tuple[str, int, int], ...]:
    paths = [APP_DIR / APP_CORPUS_METADATA_PATH]
    for folder in (
        APP_DIR / APP_CORPUS_PLIEGOS_DIR,
        APP_DIR / APP_CORPUS_ESPECIFICACIONES_DIR,
    ):
        if folder.exists():
            paths.extend(sorted(path for path in folder.iterdir() if path.is_file() and path.suffix.lower() == ".pdf"))

    signature = [("engine:" + ENGINE_VERSION, 0, 0), ("taxonomy:" + taxonomy_sha256(), 0, 0)]
    for path in paths:
        if not path.exists():
            signature.append((str(path.resolve()), 0, 0))
            continue
        stat = path.stat()
        signature.append((str(path.resolve()), int(stat.st_mtime_ns), int(stat.st_size)))
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


def safe_text(value: object) -> str:
    return escape(str(value))


def _highlight_matched(text: str, matched: str) -> str:
    """Devuelve el texto con matched en negrita, escapado para HTML seguro."""
    safe = escape(text.strip())
    if not matched or not matched.strip():
        return f"<p>{safe}</p>"
    safe_match = escape(matched.strip())
    # Búsqueda case-insensitive preservando el texto original
    import re as _re
    highlighted = _re.sub(
        f"({_re.escape(safe_match)})",
        r"<strong>\1</strong>",
        safe,
        count=1,
        flags=_re.IGNORECASE,
    )
    return f"<p>{highlighted}</p>"


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



def render_document_header(document_name: str, metadata: dict[str, str]) -> None:
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
                <div class="doc-value">Revisión preliminar</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_review_nav(document_name: str, signal_count: int) -> None:
    """Horizontal nav bar shown during document review — includes the 'Nueva revisión' action."""
    nav_col, btn_col = st.columns([0.80, 0.20])
    with nav_col:
        st.markdown(
            f'<div class="review-nav-bar">'
            f'<div class="review-nav-title">{safe_text(short_fragment(document_name, 70))}</div>'
            f'<div class="review-nav-sub">Revisión preliminar · {signal_count} observaciones</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with btn_col:
        if st.button("← Nueva revisión", key="nav_new_review", use_container_width=True, type="secondary"):
            for key in ["document_processed", "uploaded_file_bytes", "uploaded_file_name", "selected_signal_id", "review_workspace_open", review_timeline_key()]:
                st.session_state.pop(key, None)
            st.rerun()


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
    assisted_summary: list[str] | None = None,
) -> None:
    st.subheader("Lectura para decisión")
    st.caption("Síntesis breve para entender qué tipo de revisión conviene hacer. Los datos formales están arriba.")
    assisted_summary = [item for item in assisted_summary or [] if _is_contextual_summary_item(item, metadata)]
    if assisted_summary:
        render_llm_usage_note("Modelo LLM utilizado solo para redactar la síntesis contextual. La metadata y las observaciones provienen de extracción, reglas y taxonomía.")
    elif cached_llm_connection_status()[0]:
        render_llm_usage_note("Modelo LLM configurado, pero esta síntesis se muestra con lectura determinística porque no hubo salida asistida aplicable.", active=False)
    else:
        render_llm_usage_note("Sin modelo LLM en esta etapa: la síntesis se generó con reglas, taxonomía y evidencia textual.", active=False)
    top_themes = brief.get("top_themes", [])[:3]
    theme_text = ", ".join(top_themes) if top_themes else "condiciones documentales del proceso"
    condition_count = len(reviewable_signals(filtered_df))
    mitigant_count = sum(1 for _, row in filtered_df.iterrows() if display_list(row.get("mitigating_factors", []))) if not filtered_df.empty else 0
    if assisted_summary:
        bullets = contextual_summary_bullets(assisted_summary, metadata, brief, filtered_df)
    else:
        bullets = [
            f"Se consolidaron {condition_count} aspectos sugeridos para revisión, principalmente vinculados con {theme_text}.",
            f"La lectura preliminar orienta una revisión contextual de proporcionalidad, equivalencias y posible impacto sobre concurrencia.",
            f"Se identificaron mitigantes textuales en {mitigant_count} aspecto(s), cuando el documento incluye equivalencias, justificaciones o condiciones de apertura.",
            "Esta síntesis prioriza el tipo de revisión sugerida, sin repetir datos formales ya visibles en el encabezado.",
        ]
    html = "".join(f"<li>{safe_text(item)}</li>" for item in bullets[:4] if _is_useful_text(item))
    st.markdown(
        f'<div class="pliego-summary"><div class="summary-label">Qué indica la revisión preliminar</div><ul>{html}</ul></div>',
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
    if filtered:
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
        "entidad contratante:",
        "entidad:",
        "objeto:",
        "objeto de contratación:",
        "procedimiento:",
        "presupuesto:",
        "modalidad:",
        "fecha:",
    ]
    if any(lower.startswith(marker) for marker in metadata_markers):
        return False
    for value in metadata.values():
        clean = " ".join(str(value or "").split()).lower()
        if len(clean) > 18 and clean in lower:
            return False
    return True

def observation_priority(row: pd.Series) -> str:
    return str(row.get("prioridad de revisión") or "revisión sugerida")


def priority_css_class(priority: str) -> str:
    normalized = str(priority).lower()
    if "prioritaria" in normalized or "alta" in normalized:
        return "priority-high"
    if "sugerida" in normalized or "media" in normalized:
        return "priority-medium"
    return "priority-low"


def decision_guidance(row: pd.Series) -> str:
    priority = observation_priority(row).lower()
    if "prioritaria" in priority or "alta" in priority:
        return "Revisar primero y solicitar validación técnica o documental si la evidencia se confirma."
    if "sugerida" in priority or "media" in priority:
        return "Revisar después de las prioridades principales y confirmar proporcionalidad, equivalencias o justificación."
    return "Mantener como contexto de revisión; no debería desplazar aspectos con mayor prioridad salvo nueva evidencia."


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
    signal_id = str(row.get("signal_id", ""))
    if not cached_llm_connection_status()[0] or signal_id not in st.session_state.get("llm_allowed_signal_ids", []):
        return fallback
    priority = row.to_dict()
    # Audit timestamps must not invalidate an otherwise identical explanation.
    priority.pop("timestamp_analisis", None)
    explanation = cached_explain_priority_with_llm(
        priority,
        corpus_context,
        f"{_provider_name()}|{_model()}|{PROMPT_VERSION}",
        "|".join(os.getenv(name, "") for name in ("OPENAI_BASE_URL", "OPENAI_API_VERSION", "OLLAMA_BASE_URL")),
    )
    if explanation.get("llm_available") is False or explanation.get("llm_error"):
        return fallback
    st.session_state.setdefault("assisted_signal_ids", set()).add(signal_id)
    plain = str(explanation.get("plain_language_explanation") or "").strip()
    why = str(explanation.get("why_it_matters") or "").strip()
    parts = [part for part in [plain, why] if _is_useful_text(part) and "no disponible" not in part.lower()]
    return " ".join(parts) if parts else fallback


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
    ai_active = cached_llm_connection_status()[0]

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


def render_evidence_panel(row: pd.Series, pdf_bytes: bytes | None = None) -> None:
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
                    st.markdown(_highlight_matched(item.get("text", ""), item.get("matched_text", "")), unsafe_allow_html=True)
            else:
                for index, item in enumerate(display_list(raw_items), start=1):
                    st.markdown(f"**Ocurrencia {index}**")
                    st.write(safe_text(item))
    render_visual_fragment(row, pdf_bytes)


def render_suggested_aspects(
    priority_df: pd.DataFrame,
    pdf_bytes: bytes | None = None,
    corpus_context: dict | None = None,
) -> None:
    st.markdown(
        """
        <div class="section-heading">
            <div>
                <div class="section-eyebrow">Qué mirar primero</div>
                <h2>Aspectos sugeridos para revisión</h2>
            </div>
            <p>Lista consolidada y priorizada. La prioridad solo ordena la revisión humana; no representa una conclusión automática.</p>
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
    _render_aspect_rows(visible_df, pdf_bytes, corpus_context)
    if not hidden_df.empty:
        with st.expander(f"Ver {len(hidden_df)} aspectos adicionales", expanded=False):
            _render_aspect_rows(hidden_df, pdf_bytes, corpus_context)


def _render_aspect_rows(
    rows_df: pd.DataFrame,
    pdf_bytes: bytes | None,
    corpus_context: dict | None,
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
                <div class="review-item-dimension">Dimensión: {safe_text(dimension)}</div>
                <div class="decision-guidance"><strong>Decisión sugerida:</strong> {safe_text(decision_guidance(row))}</div>
                <div class="review-item-summary"><strong>Por qué conviene revisar:</strong> {safe_text(short_fragment(row.get('por qué se sugiere revisar', row.get('observación prudente', 'Requiere validación humana.')), 300))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown('<div class="review-item-body">', unsafe_allow_html=True)
        st.markdown("**Lectura contextual**")
        contextual_text = integrated_contextual_explanation(row, corpus_context)
        if str(row.get("signal_id", "")) in st.session_state.get("assisted_signal_ids", set()):
            render_llm_usage_note("Modelo LLM usado aquí: redacta una explicación breve a partir del fragmento, la taxonomía y mitigantes ya detectados. No agrega ni elimina observaciones.")
        else:
            render_llm_usage_note("Sin modelo LLM aquí: la explicación proviene de reglas, taxonomía y contexto documental.", active=False)
        st.write(contextual_text)
        mitigants = display_list(row.get("mitigating_factors", []))
        if mitigants:
            st.markdown('<div class="mitigant-strip"><strong>Mitigantes identificados:</strong> ' + safe_text("; ".join(mitigants[:3])) + '</div>', unsafe_allow_html=True)
        questions = row.get("human_review_questions") or row.get("suggested_questions") or row.get("pregunta_normativa_sugerida")
        st.markdown("**Preguntas para el revisor**")
        st.markdown(display_bullets(questions, row.get("validación sugerida", "Validar proporcionalidad y necesidad técnica.")), unsafe_allow_html=True)
        render_evidence_panel(row, pdf_bytes=pdf_bytes)
        render_reasoning_expander(row)
        st.caption(f"Fuente: {safe_text(observation_source(row))}")
        st.markdown('</div>', unsafe_allow_html=True)

# Backward-compatible name used by older flow sections.
def render_executive_overview(
    *,
    document_name: str,
    metadata: dict[str, str],
    signal_count: int,
    brief: dict,
    priority_df: pd.DataFrame,
    pdf_bytes: bytes | None = None,
    corpus_context: dict | None = None,
    assisted_summary: list[str] | None = None,
    validation_messages: list[str] | None = None,
) -> None:
    render_review_nav(document_name, signal_count)
    render_document_header(document_name, metadata)
    render_original_document(pdf_bytes)
    render_pliego_summary(metadata, brief, priority_df, assisted_summary=assisted_summary)
    render_methodological_limitations(validation_messages or [])
    render_suggested_aspects(priority_df, pdf_bytes=pdf_bytes, corpus_context=corpus_context)


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


def render_methodological_limitations(validation_messages: list[str]) -> None:
    limitations = [
        "Los resultados orientan revisión humana y no reemplazan análisis técnico, jurídico o institucional.",
        "La extracción de texto puede omitir información si el PDF contiene imágenes, escaneos o anexos no legibles.",
        "La comparación histórica depende del corpus local disponible y de su trazabilidad documental.",
    ] + validation_messages
    with st.expander("Alcance y límites de esta lectura", expanded=False):
        st.markdown("<ul>" + "".join(f"<li>{safe_text(item)}</li>" for item in limitations if str(item).strip()) + "</ul>", unsafe_allow_html=True)



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
        <div class="setup-hero decision-setup">
            <div class="setup-kicker">Inicio</div>
            <h1>Revisar documento</h1>
            <p>Suba el PDF del pliego o especificación técnica. La herramienta preparará una lectura preliminar con observaciones, evidencia y preguntas de validación.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="decision-explain">
            <div><strong>Resultado esperado</strong><span>Una lista corta de aspectos que conviene revisar primero.</span></div>
            <div><strong>Base de la lectura</strong><span>Reglas documentales, taxonomía, evidencia textual y corpus disponible.</span></div>
            <div><strong>Uso de modelo</strong><span>Si está configurado, apoya metadata, síntesis y lectura contextual; no decide observaciones.</span></div>
            <div><strong>Alcance</strong><span>Insumo preliminar para revisión humana; no es dictamen técnico ni jurídico.</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.expander("Cómo funciona el análisis", expanded=False):
        st.markdown(
            """
La herramienta toma un pliego o especificación técnica en PDF y combina tres capas de lectura:

1. **Extracción y estructuración documental:** extrae texto, páginas, secciones y fragmentos verificables.
2. **Taxonomía de señales:** organiza qué condiciones conviene revisar, como requisitos técnicos, experiencia, plazos, certificaciones, equivalencias, interoperabilidad o trazabilidad.
3. **Modelos de IA/LLM:** cuando están configurados, ayudan a interpretar esas condiciones dentro del contexto del documento y a redactar síntesis más claras. No agregan conclusiones ni reemplazan la revisión humana.

Las dimensiones usadas actualmente —neutralidad competitiva, proporcionalidad, barreras de entrada, relación con el objeto contractual, interoperabilidad y trazabilidad regulatoria— son una **propuesta inicial de organización analítica**. Pueden ajustarse, ampliarse o depurarse con revisión institucional y validación experta.

Las observaciones generadas son insumos preliminares. Deben verificarse contra el documento, anexos, aclaraciones, expediente completo y criterio técnico o jurídico de la entidad competente.
            """
        )
    st.markdown('<div class="upload-panel"><div class="upload-panel-title">Archivo PDF</div><div class="upload-panel-help">Seleccione el documento y luego inicie la revisión.</div>', unsafe_allow_html=True)
    uploaded_file = st.file_uploader("Documento PDF", type=["pdf"], label_visibility="collapsed")
    process_document = st.button("Iniciar revisión", type="primary", width="stretch")
    st.markdown('</div>', unsafe_allow_html=True)
    return uploaded_file, True, llm_configured_by_env(), process_document

def _smtp_configured() -> bool:
    return bool(os.getenv("SMTP_USER") and os.getenv("SMTP_PASSWORD"))


def _build_email_brief(brief: dict) -> dict:
    return {
        "overall_attention_level": brief.get("general_attention", "No disponible"),
        "document_summary": brief.get("general_reading", "No disponible"),
        "main_review_topics": brief.get("top_themes", []),
        "suggested_human_review_questions": brief.get("validation_areas", []),
        "methodological_note": (
            "Las señales son insumos preliminares para revisión humana. "
            "No constituyen dictamen técnico, legal ni determinación de responsabilidad."
        ),
    }


def render_email_report_panel(
    document_name: str,
    brief: dict,
    visible_df: pd.DataFrame,
) -> None:
    with st.expander("Compartir por email", expanded=False):
        if not _smtp_configured():
            st.markdown(
                '<div class="methodology-limits">'
                "<strong>Envío por email no configurado.</strong> "
                "Agregá en tu <code>.env</code>:<br><br>"
                "<code>SMTP_USER=cuenta@gmail.com</code><br>"
                "<code>SMTP_PASSWORD=xxxx_xxxx_xxxx_xxxx</code>"
                " &nbsp;← contraseña de app Gmail, no la normal"
                "</div>",
                unsafe_allow_html=True,
            )
            return

        st.caption("Enviá un informe HTML con los hallazgos principales. Separá múltiples destinatarios con coma.")
        recipients_raw = st.text_input(
            "Destinatarios",
            placeholder="analista@entidad.gob.ec, supervisor@entidad.gob.ec",
            label_visibility="collapsed",
            key="email_recipients_input",
        )
        if st.button("Enviar informe", type="primary", key="email_send_btn"):
            recipients = [r.strip() for r in recipients_raw.split(",") if r.strip() and "@" in r.strip()]
            if not recipients:
                st.warning("Ingresá al menos un email válido.")
                return
            top_findings = reviewable_signals(visible_df).head(3).to_dict(orient="records")
            with st.spinner("Enviando..."):
                ok, msg = send_alert_email(
                    document_name=document_name,
                    brief=_build_email_brief(brief),
                    top_findings=top_findings,
                    recipients=recipients,
                )
            if ok:
                st.success(msg)
            else:
                st.error(msg)


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
            analysis_key = hashlib.sha256(uploaded_file_bytes + json.dumps(
                [ENGINE_VERSION, taxonomy_sha256(), uploaded_file_name, corpus_payload["context"]],
                sort_keys=True, default=str,
            ).encode()).hexdigest()
            if st.session_state.get("analysis_key") != analysis_key:
                review_result = analyze_document_bytes(
                    uploaded_file_bytes, corpus_context=corpus_payload["context"],
                    total_processes=corpus_payload["total_processes"], document_name=uploaded_file_name,
                )
                st.session_state["analysis_result"] = review_result
                st.session_state["analysis_key"] = analysis_key
                st.session_state["assisted_signal_ids"] = set()
            review_result = st.session_state["analysis_result"]
        except (DocumentReadError, TaxonomyUnavailableError) as exc:
            st.error(str(exc))
            st.stop()
        except Exception:
            LOGGER.exception("Error al preparar la revisión documental.")
            st.error("No se pudo completar la revisión documental. Se produjo un error de análisis; el archivo no necesariamente está dañado.")
            st.stop()

    pages = review_result.pages
    validation_messages.extend(review_result.validation_messages)
    document_text = review_result.document_text
    enriched_df = review_result.enriched_df
    visible_df = enriched_df

    validate_extracted_pages(pages)
    if not document_text.strip():
        st.stop()

    metadata = extract_pliego_metadata(uploaded_file_name, document_text, APP_DIR, hashlib.sha256(uploaded_file_bytes).hexdigest())

    if review_result.results_df.empty or visible_df.empty:
        render_document_header(uploaded_file_name, metadata)
        render_pliego_summary(metadata, {"top_themes": []}, pd.DataFrame())
        st.info("No se identificaron observaciones preliminares priorizadas con las reglas actuales. Puede continuar con revisión manual del documento.")
        render_technical_details(corpus_payload, validation_messages)
        return

    signal_count = len(reviewable_signals(visible_df))
    assisted_summary: list[str] = []
    st.session_state["llm_allowed_signal_ids"] = visible_df.head(1)["signal_id"].astype(str).tolist() if enable_ai_reading else []
    if enable_ai_reading:
        if not cached_llm_connection_status()[0]:
            validation_messages.append("Análisis asistido no configurado en este entorno.")
        else:
            summary_key = f"summary:{analysis_key}:{_provider_name()}:{_model()}:{PROMPT_VERSION}"
            if summary_key not in st.session_state:
                with st.spinner("Preparando síntesis contextual..."):
                    st.session_state[summary_key] = generate_document_brief("", visible_df.head(3).to_dict("records"), corpus_payload["context"])
            assisted_brief = st.session_state[summary_key]
            if assisted_brief.get("llm_available"):
                assisted_summary = [assisted_brief["document_summary"]]

    overview_brief = build_executive_brief(visible_df)
    render_executive_overview(
        document_name=uploaded_file_name,
        metadata=metadata,
        signal_count=signal_count,
        brief=overview_brief,
        priority_df=visible_df,
        pdf_bytes=uploaded_file_bytes,
        corpus_context=corpus_payload["context"],
        assisted_summary=assisted_summary,
        validation_messages=validation_messages,
    )

    filtered_df = visible_df

    export_col, email_col = st.columns(2)
    with export_col:
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
    with email_col:
        render_email_report_panel(uploaded_file_name, overview_brief, visible_df)

st.set_page_config(
    page_title="Integrity Tool - revisión de pliegos",
    layout="wide",
)
load_css()
render_institutional_header()

render_review_flow()
