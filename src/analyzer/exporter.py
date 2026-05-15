from __future__ import annotations

import pandas as pd


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
    "related_pages",
    "páginas relacionadas",
    "occurrence_count",
    "occurrencias relacionadas",
    "representative_excerpt",
    "rule_id",
    "rule_version",
    "timestamp_analisis",
    "engine_version",
    "taxonomy_sha256",
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


def prepare_results_dataframe(detections: list) -> pd.DataFrame:
    results_df = pd.DataFrame([detection.to_dict() for detection in detections])
    results_df = results_df.rename(columns={"categoría": "categoría de revisión"})
    for column in LLM_COLUMNS:
        if column not in results_df.columns:
            results_df[column] = "No disponible"
    return results_df


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
