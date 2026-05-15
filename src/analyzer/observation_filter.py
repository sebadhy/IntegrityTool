from __future__ import annotations

import ast
import re
from typing import Any

import pandas as pd


BOILERPLATE_EXPRESSIONS = [
    "no requerido por la entidad",
    "sin datos",
    "no aplica",
    "n/a",
    "información no disponible",
    "informacion no disponible",
    "versión",
    "version",
    "índice",
    "indice",
]

LOW_INFORMATION_TERMS = {
    "no requerido",
    "sin datos",
    "no aplica",
    "n/a",
    "ver anexo",
    "adjunto",
}

REVIEW_PRIORITY_ORDER = {"priority": 0, "suggested": 1, "general": 2}
REVIEW_PRIORITY_LABEL = {
    "general": "revisión general",
    "suggested": "revisión sugerida",
    "priority": "revisión prioritaria",
}
HISTORY_ORDER = {"Poco frecuente": 0, "Sin histórico": 1, "Intermedio": 2, "Habitual": 3}


def prepare_visible_review_items(enriched_df: pd.DataFrame, max_items: int = 18) -> pd.DataFrame:
    """Return user-visible review items after filtering, scoring and consolidation.

    This layer is deliberately deterministic: textual detections remain available upstream,
    but only useful, differentiated and actionable observations should reach the UI.
    """
    if enriched_df.empty:
        return enriched_df.copy()

    working = enriched_df.copy()
    if "tipo_señal" in working.columns:
        working = working[working["tipo_señal"] == "señal_revision"].copy()
    if working.empty:
        return working

    working["_boilerplate"] = working.apply(_is_boilerplate_row, axis=1)
    working["_visibility_score"] = working.apply(_visibility_score, axis=1)
    working["_display_mode"] = working.apply(_display_mode, axis=1)
    working = working[(~working["_boilerplate"]) & (working["_display_mode"] == "visible")].copy()
    if working.empty:
        return working.drop(columns=[column for column in working.columns if column.startswith("_")], errors="ignore")

    consolidated = [_consolidate_group(group) for _, group in working.groupby(_semantic_group_key(working), sort=False)]
    visible = pd.DataFrame(consolidated)
    if visible.empty:
        return visible

    visible["_sort_priority"] = visible["review_priority"].map(REVIEW_PRIORITY_ORDER).fillna(1)
    visible["_sort_history"] = visible["clasificación histórica"].map(HISTORY_ORDER).fillna(2)
    visible = visible.sort_values(
        by=["_sort_priority", "_visibility_score", "_sort_history", "occurrence_count"],
        ascending=[True, False, True, False],
    ).head(max_items)
    return visible.drop(columns=[column for column in visible.columns if column.startswith("_")], errors="ignore").reset_index(drop=True)


def _semantic_group_key(df: pd.DataFrame) -> pd.Series:
    pattern = df.get("pattern_id", df.get("patrón detectado", "")).astype(str)
    dimension = df.get("competition_dimension", df.get("dimensión competitiva", "")).astype(str)
    signal_type = df.get("signal_type", df.get("tipo_señal", "")).astype(str)
    return pattern + "|" + dimension + "|" + signal_type


def _consolidate_group(group: pd.DataFrame) -> dict[str, Any]:
    group = group.copy()
    representative = group.sort_values("_visibility_score", ascending=False).iloc[0].copy()
    pages = _sorted_pages(group["página"].tolist())
    representative_excerpt = _representative_excerpt(group)
    occurrence_count = int(group.get("número de coincidencias", pd.Series([1] * len(group))).apply(_safe_int).sum())
    if occurrence_count < len(group):
        occurrence_count = len(group)

    representative["related_pages"] = pages
    representative["páginas relacionadas"] = ", ".join(str(page) for page in pages)
    representative["occurrence_count"] = occurrence_count
    representative["occurrencias relacionadas"] = occurrence_count
    representative["representative_excerpt"] = representative_excerpt
    representative["fragmento textual"] = representative_excerpt
    representative["clause_excerpt"] = representative_excerpt
    representative["número de coincidencias"] = occurrence_count

    if len(group) > 1:
        title = _consolidated_title(str(representative.get("patrón detectado", "Aspecto sugerido para revisión")))
        representative["patrón detectado"] = title
        representative["pattern_name"] = title
        representative["title"] = title
        representative["por qué se sugiere revisar"] = _consolidated_rationale(representative, pages, occurrence_count)
        representative["observación prudente"] = representative["por qué se sugiere revisar"]
        representative["explicacion_priorizacion"] = representative["por qué se sugiere revisar"]

    return representative.to_dict()


def _visibility_score(row: pd.Series) -> int:
    score = 0
    review_priority = str(row.get("review_priority", "suggested"))
    score += {"priority": 8, "suggested": 5, "general": 2}.get(review_priority, 4)
    score += min(len(_list_field(row.get("escalation_factors", []))) * 3, 6)
    score -= min(len(_list_field(row.get("mitigating_factors", []))) * 2, 4)

    classification = str(row.get("clasificación histórica", ""))
    if classification == "Poco frecuente":
        score += 3
    elif classification == "Sin histórico":
        score += 1
    elif classification == "Habitual":
        score -= 3

    score += min(_specificity_score(str(row.get("fragmento textual", ""))), 4)
    if _is_low_information_fragment(str(row.get("fragmento textual", ""))):
        score -= 6
    if _is_common_context_only(row):
        score -= 6
    return score


def _display_mode(row: pd.Series) -> str:
    if _is_boilerplate_row(row):
        return "hidden"
    if _is_common_context_only(row):
        return "context_only"
    if _visibility_score(row) <= 0:
        return "hidden"
    return "visible"


def _is_common_context_only(row: pd.Series) -> bool:
    return (
        str(row.get("clasificación histórica", "")) == "Habitual"
        and not _list_field(row.get("escalation_factors", []))
        and str(row.get("review_priority", "general")) == "general"
    )


def _is_boilerplate_row(row: pd.Series) -> bool:
    fragment = _normalize(str(row.get("fragmento textual", row.get("clause_excerpt", ""))))
    pattern = _normalize(str(row.get("patrón detectado", row.get("pattern_name", ""))))
    if not fragment and not pattern:
        return True
    if any(expr in fragment for expr in BOILERPLATE_EXPRESSIONS):
        return True
    if pattern in {_normalize(expr) for expr in BOILERPLATE_EXPRESSIONS}:
        return True
    return _is_low_information_fragment(fragment)


def _is_low_information_fragment(fragment: str) -> bool:
    text = _normalize(fragment)
    if not text:
        return True
    if text in LOW_INFORMATION_TERMS:
        return True
    words = [word for word in re.findall(r"[a-záéíóúñü0-9]+", text) if len(word) > 1]
    if len(words) <= 2 and any(term in text for term in LOW_INFORMATION_TERMS):
        return True
    if len(set(words)) <= 2 and len(words) <= 5:
        return True
    return False


def _specificity_score(fragment: str) -> int:
    text = _normalize(fragment)
    score = 0
    if any(char.isdigit() for char in text):
        score += 1
    for term in ("deberá", "debera", "requisito", "certificado", "plazo", "marca", "exclusivo", "experiencia", "índice", "indice"):
        if term in text:
            score += 1
    if len(text) > 180:
        score += 1
    return score


def _representative_excerpt(group: pd.DataFrame) -> str:
    excerpts = []
    for _, row in group.sort_values("_visibility_score", ascending=False).head(3).iterrows():
        excerpt = str(row.get("fragmento textual") or row.get("clause_excerpt") or "").strip()
        if excerpt and excerpt not in excerpts:
            excerpts.append(excerpt)
    return " / ".join(excerpts[:2])


def _consolidated_title(title: str) -> str:
    normalized = _normalize(title)
    if "plazo" in normalized or "cronograma" in normalized:
        return "Consideraciones sobre cronograma y plazos"
    if "certificación" in normalized or "certificacion" in normalized or "autorización" in normalized or "autorizacion" in normalized:
        return "Requisito de autorización, certificación o respaldo del bien"
    return title


def _consolidated_rationale(row: pd.Series, pages: list[int], occurrence_count: int) -> str:
    classification = str(row.get("clasificación histórica", "No disponible"))
    frequency = str(row.get("frecuencia en corpus", "No disponible"))
    if classification == "Habitual":
        context = f"El patrón aparece frecuentemente en procesos comparables ({frequency}) y, de forma aislada, no incrementa la prioridad de revisión."
    else:
        context = str(row.get("por qué se sugiere revisar") or row.get("observación prudente") or "Requiere revisión humana contextual.")
    page_text = ", ".join(str(page) for page in pages)
    return (
        f"Se identificaron {occurrence_count} referencias relacionadas en las páginas {page_text}. "
        f"{context} Conviene validar proporcionalidad, contenido sustantivo y condiciones de participación."
    )


def _sorted_pages(values: list[Any]) -> list[int]:
    pages = []
    for value in values:
        try:
            pages.append(int(value))
        except (TypeError, ValueError):
            continue
    return sorted(set(pages))


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1


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
            parsed = ast.literal_eval(stripped)
        except (ValueError, SyntaxError):
            return [stripped]
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
        return [str(parsed).strip()] if str(parsed).strip() else []
    return []


def _normalize(value: str) -> str:
    replacements = str.maketrans("áéíóúñü", "aeiounu")
    return re.sub(r"\s+", " ", value.lower().translate(replacements)).strip(" .,:;-")
