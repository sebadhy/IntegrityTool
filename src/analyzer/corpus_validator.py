from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_COLUMNS = (
    "process_id",
    "entidad",
    "objeto",
    "fecha",
    "pliego_file",
    "especificaciones_file",
)

DOCUMENT_COLUMNS = {
    "pliego": "pliego_file",
    "especificaciones": "especificaciones_file",
}

VALIDATION_OK = "OK"
VALIDATION_NOT_FOUND = "No encontrado"
VALIDATION_INCONSISTENT = "Nombre inconsistente"
VALIDATION_DUPLICATE = "Duplicado"
VALIDATION_INCOMPLETE = "Metadata incompleta"
VALIDATION_AMBIGUOUS = "Coincidencia ambigua"
VALIDATION_ORPHAN = "Documento sin correspondencia CSV"

CRITICAL_STATES = {
    VALIDATION_NOT_FOUND,
    VALIDATION_DUPLICATE,
    VALIDATION_INCOMPLETE,
    VALIDATION_AMBIGUOUS,
}


@dataclass(frozen=True)
class DocumentTrace:
    document_id: str
    process_id: str
    tipo_documento: str
    path_exacto: Path
    filename_original: str
    filename_normalizado: str
    sha256: str
    timestamp_carga: str
    tamano_archivo: int

    def to_dict(self) -> dict[str, str | int]:
        return {
            "document_id": self.document_id,
            "process_id": self.process_id,
            "tipo_documento": self.tipo_documento,
            "path exacto": str(self.path_exacto),
            "filename original": self.filename_original,
            "filename normalizado": self.filename_normalizado,
            "sha256": self.sha256,
            "timestamp carga": self.timestamp_carga,
            "tamaño archivo": self.tamano_archivo,
        }


def normalize_filename(filename: str) -> str:
    """Normalize a PDF filename for strict deterministic matching."""
    cleaned = _clean_invisible(filename)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned.replace(" ", "_")
    path = Path(cleaned)
    stem = path.stem.upper()
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        suffix = ".pdf"
    elif not suffix and stem:
        suffix = ".pdf"
    return f"{stem}{suffix}"


def validate_corpus(
    metadata_rows: list[dict[str, str]],
    folders_by_type: dict[str, Path],
) -> dict[str, Any]:
    validation_rows: list[dict[str, str]] = []
    traces: dict[tuple[str, str], DocumentTrace] = {}

    duplicate_process_ids = {
        process_id
        for process_id, count in Counter(
            _clean_text(row.get("process_id", "")) for row in metadata_rows
        ).items()
        if process_id and count > 1
    }
    referenced_by_folder: dict[Path, set[str]] = defaultdict(set)
    referenced_documents = _referenced_document_counts(metadata_rows, folders_by_type)

    for row in metadata_rows:
        process_id = _clean_text(row.get("process_id", ""))
        missing_columns = [
            column for column in REQUIRED_COLUMNS if not _clean_text(row.get(column, ""))
        ]

        for tipo_documento, column in DOCUMENT_COLUMNS.items():
            expected_file = _clean_text(row.get(column, ""))
            folder = folders_by_type[tipo_documento]
            normalized_expected = normalize_filename(expected_file) if expected_file else ""
            duplicate_key = (tipo_documento, str(folder.resolve()), normalized_expected)

            base_validation = {
                "process_id": process_id,
                "tipo_documento": tipo_documento,
                "archivo_esperado": expected_file,
                "archivo_encontrado": "",
                "estado_validacion": VALIDATION_OK,
                "observacion": "",
            }

            if missing_columns:
                validation_rows.append(
                    {
                        **base_validation,
                        "estado_validacion": VALIDATION_INCOMPLETE,
                        "observacion": (
                            "Metadata incompleta: " + ", ".join(missing_columns)
                        ),
                    }
                )
                continue

            if process_id in duplicate_process_ids:
                validation_rows.append(
                    {
                        **base_validation,
                        "estado_validacion": VALIDATION_DUPLICATE,
                        "observacion": "process_id duplicado en metadata.",
                    }
                )
                continue

            if not expected_file:
                validation_rows.append(
                    {
                        **base_validation,
                        "estado_validacion": VALIDATION_INCOMPLETE,
                        "observacion": f"Campo {column} vacío.",
                    }
                )
                continue

            if Path(expected_file).suffix.lower() != ".pdf":
                validation_rows.append(
                    {
                        **base_validation,
                        "estado_validacion": VALIDATION_INCONSISTENT,
                        "observacion": "La extensión declarada debe ser .pdf.",
                    }
                )
                continue

            matches = _exact_normalized_matches(folder, normalized_expected)
            if len(matches) > 1:
                validation_rows.append(
                    {
                        **base_validation,
                        "archivo_encontrado": "; ".join(match.name for match in matches),
                        "estado_validacion": VALIDATION_AMBIGUOUS,
                        "observacion": (
                            "Más de un archivo coincide con el nombre normalizado exacto."
                        ),
                    }
                )
                continue

            if not matches:
                validation_rows.append(
                    {
                        **base_validation,
                        "estado_validacion": VALIDATION_NOT_FOUND,
                        "observacion": (
                            "No existe un PDF con nombre normalizado exacto en la carpeta esperada."
                        ),
                    }
                )
                continue

            found = matches[0]
            referenced_by_folder[folder.resolve()].add(found.name)
            if referenced_documents[duplicate_key] > 1:
                validation_rows.append(
                    {
                        **base_validation,
                        "archivo_encontrado": found.name,
                        "estado_validacion": VALIDATION_DUPLICATE,
                        "observacion": "El mismo documento está referenciado más de una vez.",
                    }
                )
                continue

            state = VALIDATION_OK
            observation = "Documento encontrado por coincidencia exacta normalizada."
            if found.name != expected_file:
                state = VALIDATION_INCONSISTENT
                observation = (
                    "El archivo existe solo luego de normalización estricta; conviene alinear "
                    "metadata y nombre físico."
                )

            trace = build_document_trace(process_id, tipo_documento, found, expected_file)
            traces[(process_id, tipo_documento)] = trace
            validation_rows.append(
                {
                    **base_validation,
                    "archivo_encontrado": found.name,
                    "estado_validacion": state,
                    "observacion": observation,
                }
            )

    validation_rows.extend(_orphan_rows(folders_by_type, referenced_by_folder))
    summary = _validation_summary(validation_rows)
    return {
        "rows": validation_rows,
        "summary": summary,
        "traces": traces,
        "has_critical_errors": any(
            row["estado_validacion"] in CRITICAL_STATES for row in validation_rows
        ),
    }


def build_document_trace(
    process_id: str,
    tipo_documento: str,
    path: Path,
    filename_original: str | None = None,
) -> DocumentTrace:
    normalized = normalize_filename(path.name)
    digest = sha256_file(path)
    document_id = hashlib.sha1(
        f"{process_id}|{tipo_documento}|{normalized}|{digest}".encode("utf-8")
    ).hexdigest()[:16]
    return DocumentTrace(
        document_id=f"doc-{document_id}",
        process_id=process_id,
        tipo_documento=tipo_documento,
        path_exacto=path.resolve(),
        filename_original=filename_original or path.name,
        filename_normalizado=normalized,
        sha256=digest,
        timestamp_carga=datetime.now(timezone.utc).isoformat(),
        tamano_archivo=path.stat().st_size,
    )


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def validation_issues(validation_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "process_id": row["process_id"],
            "tipo_documento": row["tipo_documento"],
            "archivo": row["archivo_esperado"] or row["archivo_encontrado"],
            "estado": row["estado_validacion"],
            "observacion": row["observacion"],
        }
        for row in validation_rows
        if row["estado_validacion"] != VALIDATION_OK
    ]


def _exact_normalized_matches(folder: Path, normalized_expected: str) -> list[Path]:
    if not folder.exists():
        return []

    return [
        candidate
        for candidate in folder.iterdir()
        if candidate.is_file()
        and not _is_ignored_filesystem_entry(candidate)
        and candidate.suffix.lower() == ".pdf"
        and normalize_filename(candidate.name) == normalized_expected
    ]


def _referenced_document_counts(
    metadata_rows: list[dict[str, str]],
    folders_by_type: dict[str, Path],
) -> Counter[tuple[str, str, str]]:
    counts: Counter[tuple[str, str, str]] = Counter()
    for row in metadata_rows:
        for tipo_documento, column in DOCUMENT_COLUMNS.items():
            filename = _clean_text(row.get(column, ""))
            if not filename:
                continue
            folder = folders_by_type[tipo_documento]
            counts[(tipo_documento, str(folder.resolve()), normalize_filename(filename))] += 1
    return counts


def _orphan_rows(
    folders_by_type: dict[str, Path],
    referenced_by_folder: dict[Path, set[str]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for tipo_documento, folder in folders_by_type.items():
        if not folder.exists():
            continue
        referenced_names = referenced_by_folder.get(folder.resolve(), set())
        for candidate in sorted(folder.iterdir()):
            if not candidate.is_file() or _is_ignored_filesystem_entry(candidate):
                continue
            if candidate.name in referenced_names:
                continue
            if candidate.suffix.lower() != ".pdf":
                rows.append(
                    {
                        "process_id": "",
                        "tipo_documento": tipo_documento,
                        "archivo_esperado": "",
                        "archivo_encontrado": candidate.name,
                        "estado_validacion": VALIDATION_INCONSISTENT,
                        "observacion": "Archivo con extensión inválida en carpeta documental.",
                    }
                )
            else:
                rows.append(
                    {
                        "process_id": "",
                        "tipo_documento": tipo_documento,
                        "archivo_esperado": "",
                        "archivo_encontrado": candidate.name,
                        "estado_validacion": VALIDATION_ORPHAN,
                        "observacion": "PDF no referenciado por procesos.csv; no se carga al corpus.",
                    }
                )
    return rows


def _validation_summary(validation_rows: list[dict[str, str]]) -> dict[str, int]:
    total_expected = sum(1 for row in validation_rows if row["archivo_esperado"])
    found = sum(
        1
        for row in validation_rows
        if row["archivo_esperado"]
        and row["archivo_encontrado"]
        and row["estado_validacion"] in {VALIDATION_OK, VALIDATION_INCONSISTENT}
    )
    missing = sum(1 for row in validation_rows if row["estado_validacion"] == VALIDATION_NOT_FOUND)
    inconsistencies = sum(
        1
        for row in validation_rows
        if row["estado_validacion"] in {VALIDATION_INCONSISTENT, VALIDATION_ORPHAN}
    )
    duplicates = sum(1 for row in validation_rows if row["estado_validacion"] == VALIDATION_DUPLICATE)
    ambiguous = sum(1 for row in validation_rows if row["estado_validacion"] == VALIDATION_AMBIGUOUS)
    incomplete = sum(1 for row in validation_rows if row["estado_validacion"] == VALIDATION_INCOMPLETE)
    return {
        "total_documentos_esperados": total_expected,
        "encontrados": found,
        "faltantes": missing,
        "inconsistencias": inconsistencies,
        "duplicados": duplicates,
        "coincidencias_ambiguas": ambiguous,
        "metadata_incompleta": incomplete,
        "errores_naming": inconsistencies,
    }


def _is_ignored_filesystem_entry(path: Path) -> bool:
    ignored_names = {".DS_Store", "Thumbs.db", "desktop.ini"}
    return path.name.startswith(".") or path.name in ignored_names


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return _clean_invisible(str(value)).replace("\xa0", " ").strip()


def _clean_invisible(value: str) -> str:
    return "".join(
        character
        for character in value.replace("\ufeff", "")
        if character.isprintable()
    )
