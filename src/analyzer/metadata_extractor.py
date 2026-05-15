from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from src.config import APP_CORPUS_METADATA_PATH


DEFAULT_METADATA = {
    "entidad": "No identificado automáticamente",
    "objeto": "No identificado automáticamente",
    "tipo_procedimiento": "No identificado",
    "presupuesto": "No identificado",
    "fecha": "No identificado",
}

ENTITY_BAD_VERBS = (
    " será ",
    " deberá ",
    " podrá ",
    " corresponde ",
    " responsable ",
    " validación ",
    " firma electrónica",
)


def extract_pliego_metadata(
    document_name: str,
    document_text: str,
    app_dir: Path,
) -> dict[str, str]:
    """Build deterministic pliego metadata before any optional assisted processing."""
    metadata = document_metadata_from_name(document_name, app_dir)
    metadata = enrich_metadata_from_text(metadata, document_text)
    return validate_metadata(metadata)


def document_metadata_from_name(document_name: str, app_dir: Path) -> dict[str, str]:
    metadata = DEFAULT_METADATA.copy()
    metadata_path = app_dir / APP_CORPUS_METADATA_PATH
    if not metadata_path.exists():
        return metadata
    try:
        df = pd.read_csv(metadata_path)
    except Exception:
        return metadata
    normalized_name = _normalize_file_key(document_name)
    candidate_columns = [column for column in ("pliego_file", "especificaciones_file") if column in df.columns]
    if not candidate_columns:
        return metadata
    matches = pd.DataFrame()
    for column in candidate_columns:
        normalized_column = df[column].map(_normalize_file_key)
        column_matches = df[normalized_column == normalized_name]
        if not column_matches.empty:
            matches = column_matches
            break
    if matches.empty:
        return metadata
    row = matches.iloc[0]
    aliases = {
        "entidad": ["entidad", "entidad_contratante", "contratante", "institucion", "institución"],
        "objeto": ["objeto", "objeto_contratacion", "objeto de contratación", "descripcion", "descripción"],
        "tipo_procedimiento": ["tipo_procedimiento", "procedimiento", "tipo", "process_id"],
        "presupuesto": ["presupuesto", "presupuesto_referencial", "monto", "monto_referencial", "valor"],
        "fecha": ["fecha", "fecha_publicacion", "fecha_publicación"],
    }
    lower_columns = {str(column).strip().lower(): column for column in df.columns}
    for target, candidates in aliases.items():
        for candidate in candidates:
            column = lower_columns.get(candidate.lower())
            if column is not None and _is_useful_text(row.get(column)):
                metadata[target] = str(row.get(column)).strip()
                break
    return metadata


def enrich_metadata_from_text(metadata: dict[str, str], document_text: str) -> dict[str, str]:
    enriched = metadata.copy()
    if not _is_useful_text(enriched.get("entidad")) or enriched.get("entidad") in {
        "No disponible",
        "No se pudo identificar automáticamente.",
        "No identificado automáticamente",
    }:
        entity = _extract_field_from_text(
            document_text,
            [
                "Entidad contratante",
                "Entidad Contratante",
                "Nombre de la entidad",
                "Entidad",
                "Institución",
                "Institucion",
            ],
            max_chars=220,
        )
        if entity:
            enriched["entidad"] = entity
    if not _is_useful_text(enriched.get("objeto")) or enriched.get("objeto") in {
        "No disponible",
        "No se pudo identificar automáticamente.",
        "No identificado automáticamente",
    }:
        obj = _extract_field_from_text(
            document_text,
            [
                "Objeto de contratación",
                "Objeto de contratacion",
                "Objeto del proceso",
                "Objeto",
                "Descripción del objeto",
                "Descripcion del objeto",
            ],
            max_chars=650,
        )
        if obj:
            enriched["objeto"] = obj
    if enriched.get("tipo_procedimiento") in {"No disponible", "No identificado"}:
        procedure = _extract_field_from_text(
            document_text,
            ["Tipo de procedimiento", "Procedimiento", "Tipo de contratación", "Tipo de contratacion"],
            max_chars=160,
        )
        if procedure:
            enriched["tipo_procedimiento"] = procedure
    if enriched.get("presupuesto") in {"No disponible", "No identificado"}:
        budget = _extract_field_from_text(
            document_text,
            ["Presupuesto referencial", "Presupuesto", "Monto referencial"],
            max_chars=120,
        )
        if budget:
            enriched["presupuesto"] = budget
    return enriched


def infer_object_from_text(document_text: str) -> str:
    return (
        _extract_field_from_text(
            document_text,
            ["Objeto de contratación", "Objeto de contratacion", "Objeto del proceso", "Objeto"],
            max_chars=650,
        )
        or "No se pudo identificar automáticamente."
    )


def validate_metadata(metadata: dict[str, str]) -> dict[str, str]:
    clean = metadata.copy()
    clean["entidad"] = clean_metadata_value(clean.get("entidad"), "No identificado automáticamente")
    if is_invalid_entity(clean["entidad"]):
        clean["entidad"] = "No identificado automáticamente"
    clean["objeto"] = clean_metadata_value(clean.get("objeto"), "No identificado automáticamente")
    clean["tipo_procedimiento"] = normalize_procedure(clean.get("tipo_procedimiento"))
    clean["presupuesto"] = normalize_budget(clean.get("presupuesto"))
    clean["fecha"] = clean_metadata_value(clean.get("fecha"), "No identificado")
    return clean


def apply_assisted_metadata(metadata: dict[str, str], assisted: dict | None) -> tuple[dict[str, str], list[str]]:
    if not assisted or assisted.get("llm_available") is False:
        return metadata, []
    updated = metadata.copy()
    mapping = {
        "entidad": "entidad_contratante",
        "objeto": "objeto_contratacion",
        "tipo_procedimiento": "tipo_procedimiento",
        "presupuesto": "presupuesto_referencial",
        "fecha": "fecha",
    }
    for local_key, assisted_key in mapping.items():
        field = assisted.get(assisted_key, {})
        value = clean_metadata_value(field.get("value"), "") if isinstance(field, dict) else ""
        confidence = field.get("confidence") if isinstance(field, dict) else "baja"
        if value and value != "No identificado" and confidence in {"alta", "media"}:
            updated[local_key] = value
    return validate_metadata(updated), _display_list(assisted.get("resumen_pliego", []))[:4]


def first_pages_text(pages: list, limit: int = 4) -> str:
    return "\n\n".join(page.text for page in pages[:limit])


def clean_metadata_value(value: object, fallback: str = "No identificado") -> str:
    text = " ".join(str(value or "").replace("\n", " ").split()).strip(" ,.;:-")
    if not text or text.lower() in {"nan", "none", "no disponible", "no identificado"}:
        return fallback
    return text


def is_invalid_entity(value: object) -> bool:
    text = clean_metadata_value(value, "")
    lower = f" {text.lower()} "
    if not text or len(text) > 120:
        return True
    if any(verb in lower for verb in ENTITY_BAD_VERBS):
        return True
    institution_tokens = ("gobierno", "municip", "hospital", "ministerio", "empresa", "universidad", "dirección", "direccion")
    if text.count(" ") > 14 and not any(token in lower for token in institution_tokens):
        return True
    return False


def normalize_procedure(value: object) -> str:
    text = clean_metadata_value(value, "")
    if not text:
        return "No identificado"
    normalized = re.sub(r"\b(DE|DEL|PROCEDIMIENTO|PROCESO)\b", " ", text, flags=re.IGNORECASE)
    normalized = " ".join(normalized.split()).strip(" -:")
    lower = normalized.lower()
    known = {
        "subasta inversa electronica": "Subasta Inversa Electrónica",
        "subasta inversa electrónica": "Subasta Inversa Electrónica",
        "licitacion": "Licitación",
        "licitación": "Licitación",
        "cotizacion": "Cotización",
        "cotización": "Cotización",
        "menor cuantia": "Menor Cuantía",
        "menor cuantía": "Menor Cuantía",
        "catalogo electronico": "Catálogo Electrónico",
        "catálogo electrónico": "Catálogo Electrónico",
    }
    for key, label in known.items():
        if key in lower:
            return label
    return normalized[:120] if normalized else "No identificado"


def normalize_budget(value: object) -> str:
    text = clean_metadata_value(value, "")
    if not text or text in {",", "."}:
        return "No identificado"
    if not re.search(r"\d", text):
        return "No identificado"
    return text[:120]


def _normalize_file_key(value: object) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"_+", "_", text)
    return text


def _extract_field_from_text(document_text: str, labels: list[str], max_chars: int = 420) -> str:
    lines = [" ".join(line.split()) for line in document_text.splitlines()[:220]]
    for index, line in enumerate(lines):
        clean = line.strip(" :-\t")
        if not clean:
            continue
        lower = clean.lower()
        for label in labels:
            label_lower = label.lower()
            if label_lower in lower:
                pattern = re.compile(rf"{re.escape(label)}\s*[:\-]?\s*(.+)$", re.IGNORECASE)
                match = pattern.search(clean)
                if match and _is_useful_text(match.group(1)):
                    return match.group(1).strip()[:max_chars]
                for following in lines[index + 1 : index + 4]:
                    if _is_useful_text(following) and len(following) > 4:
                        return following.strip()[:max_chars]
    return ""


def _is_useful_text(value: object) -> bool:
    text = str(value or "").strip()
    return bool(text and text.lower() not in {"nan", "none", "no disponible", "no identificado"})


def _display_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []
