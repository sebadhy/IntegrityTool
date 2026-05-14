from __future__ import annotations

import ast
from html import escape
from pathlib import Path


APP_DIR = Path(__file__).parent.parent.parent
STYLE_PATH = APP_DIR / "assets" / "styles.css"
FEEDBACK_PATH = APP_DIR / "data" / "feedback" / "cases.jsonl"

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
    "section_id",
    "section_label",
    "rule_id",
    "rule_version",
    "taxonomy_sha256",
    "timestamp_analisis",
    "engine_version",
    "tipo_señal",
    "frecuencia_corpus",
    "categoria",
    "criterio_normativo",
    "tema de revisión",
    "documento origen",
    "tipo_documento",
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


def safe_text(value: object) -> str:
    return escape(str(value))


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


def dimension_label(value: object) -> str:
    raw_value = str(value or "").strip()
    if not raw_value or raw_value == "No disponible":
        return "No disponible"
    return DIMENSION_LABELS.get(raw_value, raw_value.replace("_", " ").capitalize())


def display_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
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
