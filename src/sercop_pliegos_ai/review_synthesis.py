from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd

from .normative_reference import get_normative_reference


THEME_BY_CATEGORY = {
    "Autorizaciones comerciales o de fabricante": "Autorizaciones comerciales o de fabricante",
    "Referencias a marca, origen o fabricante": "Referencias a marca, origen o fabricante",
    "Certificaciones específicas": "Certificaciones específicas",
    "Requisitos técnicos cerrados": "Requisitos técnicos cerrados",
    "Garantías, repuestos y postventa": "Garantías, repuestos y postventa",
    "Restricciones geográficas o de presencia local": "Restricciones geográficas o de presencia local",
    "Experiencia o capacidad excesivamente específica": "Experiencia o capacidad excesivamente específica",
    "Combinaciones de requisitos potencialmente limitantes": "Combinaciones de requisitos potencialmente limitantes",
    "Completitud y trazabilidad documental": "Completitud y trazabilidad documental",
    "Requisitos regulatorios o habituales": "Requisitos regulatorios o habituales",
    "Elementos que favorecen concurrencia": "Elementos que favorecen concurrencia",
}

THEME_ORDER = [
    "Autorizaciones comerciales o de fabricante",
    "Referencias a marca, origen o fabricante",
    "Certificaciones específicas",
    "Requisitos técnicos cerrados",
    "Garantías, repuestos y postventa",
    "Restricciones geográficas o de presencia local",
    "Experiencia o capacidad excesivamente específica",
    "Combinaciones de requisitos potencialmente limitantes",
    "Completitud y trazabilidad documental",
    "Requisitos regulatorios o habituales",
    "Elementos que favorecen concurrencia",
]

ATTENTION_SCORE = {"Bajo": 1, "Medio": 2, "Alto": 3}
RARITY_SCORE = {"Habitual": 0, "Intermedio": 1, "Poco frecuente": 2, "Sin histórico": 1}


def build_corpus_context(corpus_analysis: dict[str, Any], total_processes: int) -> dict[str, dict[str, Any]]:
    context: dict[str, dict[str, Any]] = {}
    for row in corpus_analysis.get("pattern_frequency", []):
        pattern = row["patrón detectado"]
        process_count = int(row.get("procesos con patrón", 0))
        frequency = float(row.get("frecuencia", 0))
        context[pattern] = {
            "process_count": process_count,
            "total_processes": total_processes,
            "frequency": frequency,
            "frequency_label": f"{process_count} de {total_processes} procesos",
            "rarity": _rarity_from_frequency(frequency),
            "comparative_comment": _comparative_comment(frequency),
        }
    return context


def enrich_review_dataframe(
    results_df: pd.DataFrame,
    corpus_context: dict[str, dict[str, Any]],
    total_processes: int,
) -> pd.DataFrame:
    enriched_df = results_df.copy()
    enriched_df["tema de revisión"] = enriched_df["categoría de revisión"].map(
        THEME_BY_CATEGORY
    ).fillna("Combinaciones de requisitos potencialmente limitantes")

    related_counts = enriched_df["tema de revisión"].value_counts().to_dict()
    preliminary_context = _historical_context_columns(enriched_df, corpus_context, total_processes)
    enriched_df = pd.concat([enriched_df, preliminary_context], axis=1)
    combination_context = _combination_context(enriched_df)
    mitigants = _mitigant_context(enriched_df)

    priorities = []
    explanations = []
    legitimate_justifications = []
    combination_notes = []
    normative_references = []

    for _, row in enriched_df.iterrows():
        related_count = int(related_counts.get(row["tema de revisión"], 1))
        combination_note = _combination_note_for_row(row, combination_context)
        priority = _suggested_attention(
            row["nivel de atención"],
            row["clasificación histórica"],
            related_count,
            bool(combination_note),
            row.get("tipo_señal", "señal_revision"),
            mitigants,
        )
        priorities.append(priority)
        explanations.append(_why_review(row, priority, combination_note))
        legitimate_justifications.append(_legitimate_justification(row))
        combination_notes.append(
            combination_note or "No se observa combinación prioritaria con las reglas actuales."
        )
        normative_references.append(get_normative_reference(row.to_dict()))

    enriched_df["atención sugerida"] = priorities
    enriched_df["por qué se sugiere revisar"] = explanations
    enriched_df["posible justificación legítima"] = legitimate_justifications
    enriched_df["combinación relevante"] = combination_notes
    enriched_df["elementos que favorecen concurrencia"] = _mitigant_text(mitigants)
    enriched_df["revisión sugerida"] = enriched_df["validación sugerida"]
    normative_df = pd.DataFrame(normative_references, index=enriched_df.index)
    enriched_df = pd.concat([enriched_df, normative_df], axis=1)

    return enriched_df


def build_executive_brief(enriched_df: pd.DataFrame) -> dict[str, Any]:
    review_df = _reviewable_df(enriched_df)
    total_aspects = len(review_df)
    attention = _general_attention(review_df)
    top_themes = review_df["tema de revisión"].value_counts().head(3).index.tolist()
    rare_patterns = (
        review_df[review_df["clasificación histórica"] == "Poco frecuente"][
            "patrón detectado"
        ]
        .drop_duplicates()
        .head(4)
        .tolist()
    )
    document_quality = review_df[
        review_df["tema de revisión"] == "Completitud y trazabilidad documental"
    ]
    validation_areas = _validation_areas(review_df)
    mitigants = _mitigant_items(enriched_df)
    habituals = _habitual_items(enriched_df)

    return {
        "total_aspects": total_aspects,
        "general_attention": attention,
        "top_themes": top_themes,
        "rare_patterns": rare_patterns,
        "validation_areas": validation_areas,
        "mitigants": mitigants,
        "habituals": habituals,
        "document_quality_note": _document_quality_note(document_quality),
        "general_reading": build_general_reading(review_df, top_themes, rare_patterns),
    }


def theme_summaries(enriched_df: pd.DataFrame) -> list[dict[str, Any]]:
    summaries = []
    signal_filter = (
        enriched_df["tipo_señal"] == "señal_revision"
        if "tipo_señal" in enriched_df.columns
        else pd.Series(True, index=enriched_df.index)
    )
    for theme in THEME_ORDER:
        theme_df = enriched_df[
            (enriched_df["tema de revisión"] == theme)
            & signal_filter
        ]
        if theme_df.empty:
            continue
        summaries.append(
            {
                "theme": theme,
                "count": len(theme_df),
                "attention": _general_attention(theme_df),
                "rare_count": int((theme_df["clasificación histórica"] == "Poco frecuente").sum()),
                "habitual_count": int((theme_df["clasificación histórica"] == "Habitual").sum()),
                "dataframe": theme_df,
                "priority_comment": _theme_priority_comment(theme, theme_df),
            }
        )
    return summaries


def build_general_reading(
    enriched_df: pd.DataFrame,
    top_themes: list[str],
    rare_patterns: list[str],
) -> str:
    if enriched_df.empty:
        return (
            "El documento no presenta señales sugeridas por las reglas actuales. "
            "Esto no descarta la necesidad de revisión documental."
        )

    theme_text = _join_items(top_themes) if top_themes else "condiciones documentales diversas"
    rare_text = _join_items(rare_patterns) if rare_patterns else "no se observan patrones poco frecuentes"
    quality_count = int(
        (enriched_df["tema de revisión"] == "Completitud y trazabilidad documental").sum()
    )

    quality_sentence = (
        "También se identifican señales de completitud y trazabilidad documental que convendría validar."
        if quality_count
        else "No se observan señales relevantes de completitud documental con las reglas actuales."
    )

    return (
        f"El documento presenta señales de restricción competitiva asociadas a {theme_text}. "
        f"Respecto del corpus histórico analizado, destacan {rare_text}. "
        "Estos elementos podrían requerir validación de proporcionalidad, necesidad técnica "
        "y condiciones que podrían reducir concurrencia. "
        f"{quality_sentence}"
    )


def _historical_context_columns(
    enriched_df: pd.DataFrame,
    corpus_context: dict[str, dict[str, Any]],
    total_processes: int,
) -> pd.DataFrame:
    rows = []
    for _, row in enriched_df.iterrows():
        context = corpus_context.get(row["patrón detectado"]) or _missing_context(total_processes)
        rows.append(
            {
                "frecuencia en corpus": context["frequency_label"],
                "procesos_con_patron": context.get("process_count", 0),
                "clasificación histórica": context["rarity"],
                "comentario contextual": context["comparative_comment"],
            }
        )
    return pd.DataFrame(rows, index=enriched_df.index)


def _suggested_attention(
    attention_level: str,
    rarity: str,
    related_count: int,
    has_combination: bool,
    signal_type: str,
    mitigants: list[str],
) -> str:
    if signal_type in {"requisito_habitual", "mitigante_concurrencia"}:
        return "Bajo"

    score = ATTENTION_SCORE.get(attention_level, 1)
    score += RARITY_SCORE.get(rarity, 0)
    if related_count >= 4:
        score += 1
    if has_combination:
        score += 2
    if mitigants:
        score -= 1

    if score >= 5:
        return "Alto"
    if score >= 3:
        return "Medio"
    return "Bajo"


def _general_attention(df: pd.DataFrame) -> str:
    if df.empty:
        return "Bajo"
    priority_score = df["atención sugerida"].map(ATTENTION_SCORE).max()
    rare_count = int((df["clasificación histórica"] == "Poco frecuente").sum())
    high_count = int((df["atención sugerida"] == "Alto").sum())
    combination_count = int(
        (~df["combinación relevante"].str.startswith("No se observa", na=False)).sum()
    )

    if priority_score >= 3 or rare_count >= 2 or high_count or combination_count:
        return "Alto"
    if priority_score == 2 or rare_count == 1:
        return "Medio"
    return "Bajo"


def _validation_areas(enriched_df: pd.DataFrame) -> list[str]:
    areas = []
    theme_counts = Counter(enriched_df["tema de revisión"])
    if theme_counts.get("Autorizaciones comerciales o de fabricante", 0):
        areas.append("Autorizaciones comerciales o de fabricante solicitadas.")
    if theme_counts.get("Referencias a marca, origen o fabricante", 0):
        areas.append("Referencias a marca, origen o fabricante y aceptación de equivalentes.")
    if theme_counts.get("Certificaciones específicas", 0):
        areas.append("Proporcionalidad de certificaciones específicas requeridas.")
    if theme_counts.get("Requisitos técnicos cerrados", 0):
        areas.append("Apertura de requisitos técnicos frente a alternativas equivalentes.")
    if theme_counts.get("Garantías, repuestos y postventa", 0):
        areas.append("Alcance de garantías, repuestos, mantenimiento y soporte.")
    if theme_counts.get("Completitud y trazabilidad documental", 0):
        areas.append("Disponibilidad de anexos, enlaces y campos documentales completos.")
    return areas[:5]


def _document_quality_note(document_quality: pd.DataFrame) -> str:
    if document_quality.empty:
        return "No se identifican señales relevantes de completitud documental con las reglas actuales."
    return (
        f"Se identifican {len(document_quality)} señales asociadas a completitud y trazabilidad "
        "documental. Convendría validar anexos, enlaces o campos referenciados."
    )


def _why_review(row: pd.Series, priority: str, combination_note: str) -> str:
    signal_type = row.get("tipo_señal", "señal_revision")
    if signal_type == "requisito_habitual":
        return (
            f"Se identificó '{row['patrón detectado']}' como requisito regulatorio o habitual. "
            "Por sí solo no se prioriza como señal de restricción competitiva; conviene revisarlo "
            "solo si aparece combinado con condiciones adicionales no proporcionales."
        )
    if signal_type == "mitigante_concurrencia":
        return (
            f"Se identificó '{row['patrón detectado']}' como elemento que puede favorecer apertura "
            "competitiva. Se considera mitigante contextual frente a requisitos que podrían tener "
            "lectura cerrada."
        )

    combination_text = f" {combination_note}" if combination_note else ""
    mitigant_text = ""
    if row.get("elementos que favorecen concurrencia"):
        mitigant_text = (
            f" También se observan mitigantes: {row['elementos que favorecen concurrencia']}."
        )
    return (
        f"Se identificó '{row['patrón detectado']}' en una cláusula del documento. "
        f"El patrón aparece en {row['frecuencia en corpus']} del corpus analizado. "
        f"{row['comentario contextual']} La atención sugerida es {priority.lower()} "
        "por su posible efecto sobre concurrencia, su contexto histórico y la concentración "
        f"de requisitos relacionados.{combination_text}{mitigant_text}"
    )


def _legitimate_justification(row: pd.Series) -> str:
    theme = row["tema de revisión"]
    if theme == "Autorizaciones comerciales o de fabricante":
        return (
            "Puede ser legítimo cuando responde a necesidades verificables de disponibilidad, "
            "garantía, soporte o trazabilidad del bien."
        )
    if theme == "Referencias a marca, origen o fabricante":
        return (
            "Puede ser legítimo cuando se usa como referencia técnica y se aceptan alternativas "
            "funcionalmente equivalentes."
        )
    if theme == "Certificaciones específicas":
        return (
            "Puede ser legítimo cuando la certificación se relaciona con seguridad, calidad, "
            "compatibilidad o desempeño requerido por el objeto contractual."
        )
    if theme == "Requisitos técnicos cerrados":
        return (
            "Puede ser legítimo cuando la especificación responde a una necesidad técnica "
            "y admite equivalencias funcionales razonables."
        )
    if theme == "Garantías, repuestos y postventa":
        return (
            "Puede ser legítimo cuando busca continuidad operativa, mantenimiento oportuno "
            "o disponibilidad razonable de repuestos."
        )
    if theme == "Completitud y trazabilidad documental":
        return (
            "Puede ser legítimo si la información complementaria está disponible, es accesible "
            "y forma parte clara del expediente de contratación."
        )
    return (
        "Puede ser legítimo cuando guarda relación proporcional con el objeto contractual "
        "y se encuentra suficientemente justificado."
    )


def _theme_priority_comment(theme: str, theme_df: pd.DataFrame) -> str:
    rare_count = int((theme_df["clasificación histórica"] == "Poco frecuente").sum())
    high_count = int((theme_df["atención sugerida"] == "Alto").sum())
    combo_count = int(
        (~theme_df["combinación relevante"].str.startswith("No se observa", na=False)).sum()
    )
    if combo_count:
        return (
            "Alta atención sugerida: combinación de requisitos potencialmente limitantes "
            "que podría requerir validación de proporcionalidad."
        )
    if rare_count and high_count:
        return (
            f"Alta atención sugerida: señales poco frecuentes relacionadas con {theme.lower()}."
        )
    if rare_count:
        return "Revisión humana sugerida: contiene requisitos poco frecuentes respecto del corpus histórico."
    return (
        "Revisión de rutina sugerida: las señales identificadas parecen más habituales "
        "dentro del corpus analizado."
    )


def _combination_context(enriched_df: pd.DataFrame) -> set[str]:
    review_df = _reviewable_df(enriched_df)
    categories = set(review_df["categoría de revisión"])
    patterns = {str(pattern).lower() for pattern in review_df["patrón detectado"]}
    combinations = set()

    if (
        "Autorizaciones comerciales o de fabricante" in categories
        and "Certificaciones específicas" in categories
    ):
        combinations.add("autorización comercial + certificación específica")
    if (
        "Referencias a marca, origen o fabricante" in categories
        and "Requisitos técnicos cerrados" in categories
    ):
        combinations.add("marca/fabricante + requisito técnico cerrado")
    if (
        "distribuidor autorizado" in patterns
        and "Garantías, repuestos y postventa" in categories
    ):
        combinations.add("distribuidor autorizado + garantía/postventa")
    if (
        "Certificaciones específicas" in categories
        and any(
            review_df.loc[
                review_df["categoría de revisión"] == "Certificaciones específicas",
                "clasificación histórica",
            ]
            == "Poco frecuente"
        )
    ):
        combinations.add("certificación específica + baja frecuencia histórica")
    if (
        "Requisitos técnicos cerrados" in categories
        and any(
            review_df.loc[
                review_df["categoría de revisión"] == "Requisitos técnicos cerrados",
                "clasificación histórica",
            ]
            == "Poco frecuente"
        )
    ):
        combinations.add("requisito técnico cerrado + baja frecuencia histórica")
    return combinations


def _mitigant_context(enriched_df: pd.DataFrame) -> list[str]:
    if "tipo_señal" not in enriched_df.columns:
        return []
    mitigants = enriched_df[enriched_df["tipo_señal"] == "mitigante_concurrencia"]
    return mitigants["patrón detectado"].drop_duplicates().head(6).tolist()


def _mitigant_text(mitigants: list[str]) -> str:
    if not mitigants:
        return ""
    return ", ".join(mitigants)


def _reviewable_df(enriched_df: pd.DataFrame) -> pd.DataFrame:
    if "tipo_señal" not in enriched_df.columns:
        return enriched_df
    return enriched_df[enriched_df["tipo_señal"] == "señal_revision"]


def _mitigant_items(enriched_df: pd.DataFrame) -> list[dict[str, Any]]:
    if "tipo_señal" not in enriched_df.columns:
        return []
    rows = enriched_df[enriched_df["tipo_señal"] == "mitigante_concurrencia"]
    return rows[
        ["patrón detectado", "página", "fragmento textual", "observación prudente"]
    ].drop_duplicates("patrón detectado").head(8).to_dict("records")


def _habitual_items(enriched_df: pd.DataFrame) -> list[dict[str, Any]]:
    if "tipo_señal" not in enriched_df.columns:
        return []
    rows = enriched_df[enriched_df["tipo_señal"] == "requisito_habitual"]
    return rows[
        ["patrón detectado", "página", "fragmento textual", "observación prudente"]
    ].drop_duplicates("patrón detectado").head(8).to_dict("records")


def _combination_note_for_row(row: pd.Series, combinations: set[str]) -> str:
    category = row["categoría de revisión"]
    pattern = str(row["patrón detectado"]).lower()
    relevant = []

    if category in {
        "Autorizaciones comerciales o de fabricante",
        "Certificaciones específicas",
    } and "autorización comercial + certificación específica" in combinations:
        relevant.append("Se observa combinación de autorización comercial y certificación específica.")
    if category in {
        "Referencias a marca, origen o fabricante",
        "Requisitos técnicos cerrados",
    } and "marca/fabricante + requisito técnico cerrado" in combinations:
        relevant.append("Se observa combinación de marca/fabricante y requisito técnico cerrado.")
    if (
        pattern == "distribuidor autorizado"
        or category == "Garantías, repuestos y postventa"
    ) and "distribuidor autorizado + garantía/postventa" in combinations:
        relevant.append("Se observa combinación de distribuidor autorizado y postventa.")
    if category == "Certificaciones específicas" and "certificación específica + baja frecuencia histórica" in combinations:
        relevant.append("La certificación específica presenta baja frecuencia histórica.")
    if category == "Requisitos técnicos cerrados" and "requisito técnico cerrado + baja frecuencia histórica" in combinations:
        relevant.append("El requisito técnico cerrado presenta baja frecuencia histórica.")

    return " ".join(relevant)


def _rarity_from_frequency(frequency: float) -> str:
    if frequency <= 0:
        return "Sin histórico"
    if frequency <= 0.2:
        return "Poco frecuente"
    if frequency >= 0.7:
        return "Habitual"
    return "Intermedio"


def _comparative_comment(frequency: float) -> str:
    if frequency <= 0:
        return "No se observa este patrón en el corpus histórico cargado; revisión humana sugerida."
    if frequency <= 0.2:
        return "Requisito poco frecuente respecto de procesos comparables analizados."
    if frequency >= 0.7:
        return "Patrón presente en la mayoría de procesos similares analizados."
    return "Presencia intermedia respecto del histórico analizado."


def _missing_context(total_processes: int) -> dict[str, Any]:
    return {
        "process_count": 0,
        "total_processes": total_processes,
        "frequency": 0,
        "frequency_label": f"0 de {total_processes} procesos",
        "rarity": "Sin histórico",
        "comparative_comment": "No se observa este patrón en el corpus histórico cargado; revisión humana sugerida.",
    }


def _join_items(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + f" y {items[-1]}"
    if theme == "Requisitos regulatorios o habituales":
        return (
            "Puede ser un requisito administrativo normal del proceso y no requiere priorización "
            "salvo que se combine con restricciones adicionales."
        )
    if theme == "Elementos que favorecen concurrencia":
        return (
            "Favorece concurrencia cuando se aplica efectivamente durante evaluación y no queda "
            "neutralizado por otros requisitos cerrados."
        )
