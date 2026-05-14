from __future__ import annotations

import pandas as pd

from src.analyzer.prioritizer import top_priorities
from src.analyzer.review_synthesis import theme_summaries
from src.analyzer.text_cleaner import clean_page_text
from src.ui.components import EXPORT_COLUMNS, LLM_COLUMNS


def clean_export_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Clean text fields for CSV export without altering the original DataFrame."""
    export_df = df.copy()
    if "fragmento textual" in export_df.columns:
        export_df["fragmento textual"] = export_df["fragmento textual"].apply(
            lambda v: clean_page_text(str(v)) if v and str(v) not in {"nan", "None", "No disponible"} else v
        )
    return export_df


def ordered_export(df: pd.DataFrame) -> pd.DataFrame:
    export_df = df.loc[:, ~df.columns.duplicated()].copy()
    export_order = _unique_columns(EXPORT_COLUMNS)
    present = [col for col in export_order if col in export_df.columns]
    remaining = [col for col in export_df.columns if col not in set(present)]
    return export_df[present + remaining]


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


def _unique_columns(columns: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for column in columns:
        if column not in seen:
            unique.append(column)
            seen.add(column)
    return unique


def _markdown_list(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items]
