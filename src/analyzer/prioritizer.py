from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from .taxonomy_loader import taxonomy_sha256


ENGINE_VERSION = "0.4.0"
RULE_VERSION = "neutralidad-competitiva-v1"

ATTENTION_SCORE = {"Bajo": 1, "Medio": 2, "Alto": 3}
RELEVANCE_SCORE = {"Bajo": 1, "Medio": 2, "Alto": 3}
REVIEW_PRIORITY_SCORE = {"general": 1, "suggested": 2, "priority": 3}
REVIEW_PRIORITY_LABEL = {
    "general": "revisión general",
    "suggested": "revisión sugerida",
    "priority": "revisión prioritaria",
}
RARE_LABELS = {"Poco frecuente", "Sin histórico"}
COMMON_LABELS = {"Habitual"}
STRUCTURED_SEVERITY_SCORE = {"low": 0, "medium": 1, "contextual": 2}
CRITICAL_SECTION_TERMS = (
    "requisito",
    "especificacion",
    "especificación",
    "ficha técnica",
    "garantía",
    "postventa",
    "experiencia",
    "certificación",
    "autorizado",
    "fabricante",
)
EXTERNAL_REFERENCE_TERMS = (
    "adjunto",
    "descargar",
    "link",
    "anexo",
    "ver más especificaciones",
    "revisar condiciones particulares",
)


def prioritize_signals(enriched_df: pd.DataFrame) -> pd.DataFrame:
    """Add explainable prioritization and traceability fields to review signals."""
    prioritized_df = enriched_df.copy()
    timestamp = datetime.now(timezone.utc).isoformat()
    theme_counts = prioritized_df["tema de revisión"].value_counts().to_dict()

    rows: list[dict[str, Any]] = []
    for _, row in prioritized_df.iterrows():
        criteria = _criteria_for_row(row, int(theme_counts.get(row["tema de revisión"], 1)))
        relevance = _relevance_from_criteria(row, criteria)
        attention = _attention_from_relevance(row, relevance, criteria)
        review_priority = _review_priority_from_context(row, criteria, relevance)
        rows.append(
            {
                "signal_id": _signal_id(row),
                "rule_id": _rule_id(row),
                "rule_version": RULE_VERSION,
                "timestamp_analisis": timestamp,
                "engine_version": ENGINE_VERSION,
                "taxonomy_sha256": taxonomy_sha256(),
                "frecuencia_corpus": row.get("frecuencia en corpus", "No disponible"),
                "categoria": row.get("categoría de revisión", "No disponible"),
                "criterio_normativo": row.get(
                    "criterio_normativo_de_revision",
                    "No disponible",
                ),
                "nivel_atencion": attention,
                "relevancia_analitica": relevance,
                "review_priority": review_priority,
                "prioridad de revisión": REVIEW_PRIORITY_LABEL.get(review_priority, "revisión sugerida"),
                "criterios_de_priorizacion": json.dumps(criteria, ensure_ascii=False),
                "explicacion_priorizacion": _priority_explanation(row, criteria, relevance),
                "interpretación_comparativa": row.get(
                    "comentario contextual",
                    "Comparación histórica no disponible.",
                ),
            }
        )

    priority_df = pd.DataFrame(rows, index=prioritized_df.index)
    overlapping_columns = [column for column in priority_df.columns if column in prioritized_df.columns]
    if overlapping_columns:
        prioritized_df = prioritized_df.drop(columns=overlapping_columns)
    prioritized_df = pd.concat([prioritized_df, priority_df], axis=1)
    prioritized_df["atención sugerida"] = prioritized_df["nivel_atencion"]
    return prioritized_df


def top_priorities(prioritized_df: pd.DataFrame, limit: int = 3) -> pd.DataFrame:
    """Return the highest-priority signals for the executive reading."""
    if prioritized_df.empty:
        return prioritized_df

    sort_df = prioritized_df.copy()
    if "tipo_señal" in sort_df.columns:
        sort_df = sort_df[sort_df["tipo_señal"] == "señal_revision"]
    if sort_df.empty:
        return sort_df
    sort_df["_review_priority_order"] = sort_df.get("review_priority", "suggested")
    sort_df["_review_priority_order"] = sort_df["_review_priority_order"].map(
        {"priority": 0, "suggested": 1, "general": 2}
    ).fillna(1)
    sort_df["_relevance_order"] = sort_df["relevancia_analitica"].map(
        {"Alto": 0, "Medio": 1, "Bajo": 2}
    )
    sort_df["_attention_order"] = sort_df["nivel_atencion"].map(
        {"Alto": 0, "Medio": 1, "Bajo": 2}
    )
    sort_df["_history_order"] = sort_df["clasificación histórica"].map(
        {"Poco frecuente": 0, "Sin histórico": 1, "Intermedio": 2, "Habitual": 3}
    )
    sort_df["_match_order"] = pd.to_numeric(
        sort_df.get("número de coincidencias", 1),
        errors="coerce",
    ).fillna(1)
    sort_df["_escalation_order"] = sort_df.apply(
        lambda row: len(_list_field(row.get("escalation_factors", []))),
        axis=1,
    )
    sort_df["_mitigation_order"] = sort_df.apply(
        lambda row: len(_list_field(row.get("mitigating_factors", []))),
        axis=1,
    )

    return (
        sort_df.sort_values(
            by=[
                "_review_priority_order",
                "_relevance_order",
                "_attention_order",
                "_escalation_order",
                "_mitigation_order",
                "_history_order",
                "_match_order",
            ],
            ascending=[True, True, True, False, True, True, False],
        )
        .drop(columns=[
            "_review_priority_order",
            "_relevance_order",
            "_attention_order",
            "_history_order",
            "_match_order",
            "_escalation_order",
            "_mitigation_order",
        ])
        .head(limit)
    )


def _criteria_for_row(row: pd.Series, related_count: int) -> list[str]:
    criteria: list[str] = []
    signal_type = str(row.get("tipo_señal", "señal_revision"))
    if signal_type == "requisito_habitual":
        return [
            "Requisito regulatorio o administrativo habitual; no se prioriza por sí solo."
        ]
    if signal_type == "mitigante_concurrencia":
        return [
            "Elemento que favorece concurrencia y reduce atención contextual sobre requisitos cerrados."
        ]

    mitigating_factors = _list_field(row.get("mitigating_factors", []))
    escalation_factors = _list_field(row.get("escalation_factors", []))

    for factor in escalation_factors:
        criteria.append(f"Condición de escalamiento contextual: {factor}.")
    for factor in mitigating_factors:
        criteria.append(f"Factor mitigante identificado: {factor}.")

    if str(row.get("clasificación histórica")) in COMMON_LABELS and not escalation_factors:
        criteria.append("Patrón frecuente en corpus; su presencia aislada no eleva la prioridad de revisión.")

    dimension = str(row.get("competition_dimension") or row.get("dimensión competitiva", "")).strip()
    if dimension:
        criteria.append(f"Dimensión competitiva asociada: {dimension}.")

    missing_information = _list_field(row.get("missing_information", []))
    for item in missing_information:
        criteria.append(f"Información faltante para validar contexto: {item}.")

    text = _normalized_text(
        " ".join(
            [
                str(row.get("fragmento textual", "")),
                str(row.get("patrón detectado", "")),
                str(row.get("categoría de revisión", "")),
            ]
        )
    )

    if str(row.get("clasificación histórica")) in RARE_LABELS:
        criteria.append("Baja frecuencia respecto del corpus histórico disponible.")

    if not str(row.get("combinación relevante", "")).startswith("No se observa"):
        criteria.append(str(row.get("combinación relevante")))

    if related_count >= 3:
        criteria.append(
            "Concentración de señales relacionadas dentro del mismo tema de revisión."
        )

    match_count = int(row.get("número de coincidencias", 1) or 1)
    if match_count >= 3:
        criteria.append("Repetición de la condición en la misma página o cláusula.")

    if any(term in text for term in CRITICAL_SECTION_TERMS):
        criteria.append("Presencia en lenguaje asociado a requisitos o secciones técnicas.")

    if any(term in text for term in EXTERNAL_REFERENCE_TERMS):
        criteria.append("Referencia a anexos, enlaces o información externa que conviene verificar.")

    if str(row.get("tema de revisión")) == "Completitud y trazabilidad documental":
        criteria.append("Señal de completitud o trazabilidad documental para revisión.")

    normative = str(row.get("principio_normativo_relacionado", "")).strip()
    if normative:
        criteria.append(f"Criterio normativo orientativo asociado: {normative}.")

    mitigants = str(row.get("elementos que favorecen concurrencia", "")).strip()
    if mitigants:
        criteria.append(f"Mitigantes identificados en el documento: {mitigants}.")

    return _unique(criteria) or ["Señal consolidada por reglas textuales para revisión humana."]


def _relevance_from_criteria(row: pd.Series, criteria: list[str]) -> str:
    if str(row.get("tipo_señal", "señal_revision")) in {
        "requisito_habitual",
        "mitigante_concurrencia",
    }:
        return "Bajo"

    if str(row.get("clasificación histórica")) in COMMON_LABELS and not _list_field(row.get("escalation_factors", [])):
        return "Bajo"

    score = 0
    score += STRUCTURED_SEVERITY_SCORE.get(str(row.get("severity", "")).lower(), 0)
    score += ATTENTION_SCORE.get(str(row.get("atención sugerida") or row.get("nivel de atención")), 1)
    score += min(len(_list_field(row.get("escalation_factors", []))), 3)
    score -= min(len(_list_field(row.get("mitigating_factors", []))), 2)
    if str(row.get("clasificación histórica")) in RARE_LABELS:
        score += 2
    if any("combinación" in item.lower() for item in criteria):
        score += 2
    if any("Concentración" in item for item in criteria):
        score += 1
    if any("Repetición" in item for item in criteria):
        score += 1
    if any("anexos" in item.lower() or "trazabilidad" in item.lower() for item in criteria):
        score += 1
    if any("Mitigantes identificados" in item for item in criteria):
        score -= 1
    score += REVIEW_PRIORITY_SCORE.get(str(row.get("review_priority", "suggested")), 2) - 1

    if score >= 6:
        return "Alto"
    if score >= 4:
        return "Medio"
    return "Bajo"


def _attention_from_relevance(row: pd.Series, relevance: str, criteria: list[str]) -> str:
    if str(row.get("tipo_señal", "señal_revision")) in {
        "requisito_habitual",
        "mitigante_concurrencia",
    }:
        return "Bajo"

    if str(row.get("clasificación histórica")) in COMMON_LABELS and not _list_field(row.get("escalation_factors", [])):
        return "Bajo"

    score = ATTENTION_SCORE.get(str(row.get("nivel de atención")), 1)
    score = max(score, RELEVANCE_SCORE.get(relevance, 1))
    score += min(len(_list_field(row.get("escalation_factors", []))), 2)
    score -= min(len(_list_field(row.get("mitigating_factors", []))), 2)
    if str(row.get("clasificación histórica")) == "Poco frecuente":
        score += 1
    if any("combinación" in item.lower() for item in criteria):
        score += 1
    if any("Mitigantes identificados" in item for item in criteria):
        score -= 1

    if score >= 4:
        return "Alto"
    if score >= 2:
        return "Medio"
    return "Bajo"


def _review_priority_from_context(row: pd.Series, criteria: list[str], relevance: str) -> str:
    if str(row.get("tipo_señal", "señal_revision")) in {
        "requisito_habitual",
        "mitigante_concurrencia",
    }:
        return "general"
    if str(row.get("clasificación histórica")) in COMMON_LABELS and not _list_field(row.get("escalation_factors", [])):
        return "general"

    existing = str(row.get("review_priority", "")).strip()
    if existing in REVIEW_PRIORITY_SCORE:
        base = REVIEW_PRIORITY_SCORE[existing]
    else:
        base = 2
    base += min(len(_list_field(row.get("escalation_factors", []))), 2)
    base -= min(len(_list_field(row.get("mitigating_factors", []))), 1)
    if str(row.get("clasificación histórica")) in RARE_LABELS:
        base += 1
    if relevance == "Alto":
        base += 1
    if base >= 4:
        return "priority"
    if base >= 2:
        return "suggested"
    return "general"


def _priority_explanation(row: pd.Series, criteria: list[str], relevance: str) -> str:
    if str(row.get("tipo_señal", "señal_revision")) == "requisito_habitual":
        return (
            "Requisito habitual identificado: se mantiene como contexto documental y no se "
            "prioriza salvo combinación con condiciones adicionales."
        )
    if str(row.get("tipo_señal", "señal_revision")) == "mitigante_concurrencia":
        return (
            "Elemento favorable a concurrencia: reduce la lectura restrictiva de requisitos "
            "relacionados si se aplica de forma clara y verificable."
        )

    main_criteria = " ".join(criteria[:3])
    return (
        f"Relevancia analítica {relevance.lower()}: se prioriza por {main_criteria} "
        "Conviene revisar proporcionalidad, necesidad técnica y posible impacto sobre concurrencia."
    )


def _signal_id(row: pd.Series) -> str:
    raw_value = "|".join(
        [
            str(row.get("documento origen", "Documento cargado")),
            str(row.get("página", "")),
            str(row.get("patrón detectado", "")),
            str(row.get("fragmento textual", ""))[:220],
        ]
    )
    digest = hashlib.sha1(raw_value.encode("utf-8")).hexdigest()[:12]
    return f"sig-{digest}"


def _rule_id(row: pd.Series) -> str:
    raw_value = f"{row.get('categoría de revisión', '')}-{row.get('patrón detectado', '')}"
    slug = _normalized_text(raw_value).replace(" ", "-")
    slug = "".join(character for character in slug if character.isalnum() or character == "-")
    return f"rule-{slug[:80].strip('-')}"


def _normalized_text(value: str) -> str:
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ñ": "n",
    }
    text = value.lower()
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _list_field(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return [stripped]
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
        return [str(parsed).strip()] if str(parsed).strip() else []
    return []


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in seen:
            unique_values.append(normalized)
            seen.add(normalized)
    return unique_values


def prioritize_consolidated_findings(findings: list) -> list:
    """Order ConsolidatedFinding objects and keep internal ranking hidden from UI."""
    return sorted(
        findings,
        key=lambda finding: (
            -int(getattr(finding, "internal_ranking_score", 0)),
            -int(getattr(finding, "duplicate_count", 1)),
            str(getattr(finding, "title", "")),
        ),
    )


def review_priority_from_score(score: int) -> str:
    if score >= 6:
        return "alta"
    if score >= 3:
        return "media"
    return "baja"
