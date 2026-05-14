from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import (
    CORPUS_ESPECIFICACIONES_DIR,
    CORPUS_METADATA_PATH,
    CORPUS_PLIEGOS_DIR,
    CORPUS_PROCESSED_DIR,
)
from .corpus_validator import (
    DocumentTrace,
    VALIDATION_INCONSISTENT,
    VALIDATION_OK,
    validate_corpus,
    validation_issues,
)
from .detector import detect_patterns
from .pdf_extractor import PageText, extract_text_by_page


RAW_METADATA_PATH = CORPUS_METADATA_PATH
RAW_PLIEGOS_DIR = CORPUS_PLIEGOS_DIR
RAW_ESPECIFICACIONES_DIR = CORPUS_ESPECIFICACIONES_DIR
PROCESSED_TEXT_DIR = CORPUS_PROCESSED_DIR


@dataclass(frozen=True)
class CorpusDocument:
    document_id: str
    process_id: str
    tipo_documento: str
    path: Path
    filename_original: str
    filename_normalizado: str
    sha256: str
    timestamp_carga: str
    tamano_archivo: int
    texto_extraido: str
    paginas: list[PageText]
    metadata_proceso: dict[str, str]


def load_process_metadata(metadata_path: Path = RAW_METADATA_PATH) -> list[dict[str, str]]:
    """Read and normalize process metadata from procesos.csv."""
    if not metadata_path.exists():
        return []

    with metadata_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        sample = csv_file.read(4096)
        csv_file.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=";,")
        reader = csv.DictReader(csv_file, dialect=dialect)
        rows = []
        for raw_row in reader:
            row = {
                _clean_text(key): _clean_text(value)
                for key, value in raw_row.items()
                if key and _clean_text(key)
            }
            row = {key: value for key, value in row.items() if not key.startswith("Unnamed")}
            if row.get("process_id"):
                rows.append(row)

    return rows


def load_corpus_documents(force: bool = False) -> tuple[list[CorpusDocument], list[dict[str, str]]]:
    """Load only strictly validated corpus documents."""
    metadata_rows = load_process_metadata()
    documents: list[CorpusDocument] = []
    validation = validate_corpus(
        metadata_rows,
        {
            "pliego": RAW_PLIEGOS_DIR,
            "especificaciones": RAW_ESPECIFICACIONES_DIR,
        },
    )
    issues = validation_issues(validation["rows"])
    if validation["has_critical_errors"]:
        return [], issues

    for metadata in metadata_rows:
        for tipo_documento, folder, file_column in (
            ("pliego", RAW_PLIEGOS_DIR, "pliego_file"),
            ("especificaciones", RAW_ESPECIFICACIONES_DIR, "especificaciones_file"),
        ):
            trace = validation["traces"].get((metadata.get("process_id", ""), tipo_documento))
            validation_state = _validation_state(
                validation["rows"],
                metadata.get("process_id", ""),
                tipo_documento,
            )
            if validation_state not in {VALIDATION_OK, VALIDATION_INCONSISTENT} or trace is None:
                continue

            documents.append(
                _load_or_extract_document(
                    process_metadata=metadata,
                    tipo_documento=tipo_documento,
                    document_path=trace.path_exacto,
                    trace=trace,
                    force=force,
                )
            )

    return documents, issues


def validate_corpus_state() -> dict[str, Any]:
    """Return deterministic corpus validation data for UI and audits."""
    metadata_rows = load_process_metadata()
    return validate_corpus(
        metadata_rows,
        {
            "pliego": RAW_PLIEGOS_DIR,
            "especificaciones": RAW_ESPECIFICACIONES_DIR,
        },
    )


def analyze_corpus_documents(documents: list[CorpusDocument]) -> dict[str, Any]:
    findings = _detect_corpus_findings(documents)
    total_processes = len({document.process_id for document in documents})

    return {
        "findings": findings,
        "pattern_frequency": _pattern_frequency(findings, total_processes),
        "category_frequency": _category_frequency(findings),
        "process_frequency": _process_frequency(findings),
        "similar_documents": calculate_document_similarity(documents),
    }


def calculate_document_similarity(
    documents: list[CorpusDocument],
    top_n: int = 20,
) -> list[dict[str, Any]]:
    tokenized_documents = [_tokenize(document.texto_extraido) for document in documents]
    document_frequency: Counter[str] = Counter()

    for tokens in tokenized_documents:
        document_frequency.update(set(tokens))

    total_documents = len(documents)
    vectors = [
        _tf_idf_vector(tokens, document_frequency, total_documents)
        for tokens in tokenized_documents
    ]

    similarities: list[dict[str, Any]] = []
    for left_index in range(total_documents):
        for right_index in range(left_index + 1, total_documents):
            score = _cosine_similarity(vectors[left_index], vectors[right_index])
            if score <= 0:
                continue

            left = documents[left_index]
            right = documents[right_index]
            similarities.append(
                {
                    "process_id_a": left.process_id,
                    "tipo_documento_a": left.tipo_documento,
                    "path_a": str(left.path),
                    "process_id_b": right.process_id,
                    "tipo_documento_b": right.tipo_documento,
                    "path_b": str(right.path),
                    "similitud_coseno": round(score, 4),
                    "comentario_comparativo": _similarity_comment(score),
                }
            )

    return sorted(similarities, key=lambda item: item["similitud_coseno"], reverse=True)[:top_n]


def _detect_corpus_findings(documents: list[CorpusDocument]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    for document in documents:
        detections = detect_patterns(document.paginas)
        for detection in detections:
            item = detection.to_dict()
            item.update(
                {
                    "process_id": document.process_id,
                    "document_id": document.document_id,
                    "tipo_documento": document.tipo_documento,
                    "documento_path": str(document.path),
                    "filename_original": document.filename_original,
                    "filename_normalizado": document.filename_normalizado,
                    "sha256": document.sha256,
                    "entidad": document.metadata_proceso.get("entidad", ""),
                    "objeto": document.metadata_proceso.get("objeto", ""),
                    "fecha": document.metadata_proceso.get("fecha", ""),
                }
            )
            findings.append(item)

    return _add_comparative_context(findings, documents)


def _add_comparative_context(
    findings: list[dict[str, Any]],
    documents: list[CorpusDocument],
) -> list[dict[str, Any]]:
    total_processes = len({document.process_id for document in documents})
    processes_by_pattern: dict[str, set[str]] = defaultdict(set)

    for finding in findings:
        processes_by_pattern[finding["patrón detectado"]].add(finding["process_id"])

    for finding in findings:
        pattern = finding["patrón detectado"]
        process_count = len(processes_by_pattern[pattern])
        frequency = process_count / total_processes if total_processes else 0
        finding["frecuencia_corpus"] = (
            f"{pattern} aparece en {process_count} de {total_processes} procesos"
        )
        finding["rareza"] = _rarity_label(frequency)
        finding["comentario_comparativo"] = _rarity_comment(frequency)

    return findings


def _pattern_frequency(
    findings: list[dict[str, Any]],
    total_processes: int,
) -> list[dict[str, Any]]:
    processes_by_pattern: dict[str, set[str]] = defaultdict(set)
    occurrences_by_pattern: Counter[str] = Counter()

    for finding in findings:
        pattern = finding["patrón detectado"]
        processes_by_pattern[pattern].add(finding["process_id"])
        occurrences_by_pattern[pattern] += int(finding.get("número de coincidencias", 1))

    rows = []
    for pattern, processes in processes_by_pattern.items():
        process_count = len(processes)
        frequency = process_count / total_processes if total_processes else 0
        rows.append(
            {
                "patrón detectado": pattern,
                "procesos con patrón": process_count,
                "total procesos": total_processes,
                "frecuencia": round(frequency, 4),
                "coincidencias": occurrences_by_pattern[pattern],
                "rareza": _rarity_label(frequency),
                "comentario_comparativo": _rarity_comment(frequency),
            }
        )

    return sorted(rows, key=lambda row: (row["procesos con patrón"], row["coincidencias"]), reverse=True)


def _category_frequency(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter(finding["categoría"] for finding in findings)
    return [
        {"categoría": category, "señales": count}
        for category, count in counts.most_common()
    ]


def _process_frequency(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}

    for finding in findings:
        process_id = finding["process_id"]
        if process_id not in grouped:
            grouped[process_id] = {
                "process_id": process_id,
                "entidad": finding.get("entidad", ""),
                "objeto": finding.get("objeto", ""),
                "señales": 0,
            }
        grouped[process_id]["señales"] += 1

    return sorted(grouped.values(), key=lambda row: row["señales"], reverse=True)


def _load_or_extract_document(
    process_metadata: dict[str, str],
    tipo_documento: str,
    document_path: Path,
    trace: DocumentTrace,
    force: bool,
) -> CorpusDocument:
    cache_path = _cache_path(process_metadata["process_id"], tipo_documento)
    if cache_path.exists() and not force:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        if payload.get("sha256") == trace.sha256:
            pages = [
                PageText(page_number=int(page["pagina"]), text=str(page["texto"]))
                for page in payload.get("paginas", [])
            ]
            return CorpusDocument(
                document_id=payload.get("document_id", trace.document_id),
                process_id=payload["process_id"],
                tipo_documento=payload["tipo_documento"],
                path=document_path,
                filename_original=payload.get("filename_original", trace.filename_original),
                filename_normalizado=payload.get("filename_normalizado", trace.filename_normalizado),
                sha256=payload.get("sha256", trace.sha256),
                timestamp_carga=payload.get("timestamp_carga", trace.timestamp_carga),
                tamano_archivo=int(payload.get("tamano_archivo", trace.tamano_archivo)),
                texto_extraido=payload.get("texto", ""),
                paginas=pages,
                metadata_proceso=process_metadata,
            )

    pages = extract_text_by_page(document_path.read_bytes())
    extracted_text = "\n\n".join(page.text for page in pages)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {
                "document_id": trace.document_id,
                "process_id": process_metadata["process_id"],
                "tipo_documento": tipo_documento,
                "path": str(trace.path_exacto),
                "filename_original": trace.filename_original,
                "filename_normalizado": trace.filename_normalizado,
                "sha256": trace.sha256,
                "timestamp_carga": trace.timestamp_carga,
                "tamano_archivo": trace.tamano_archivo,
                "texto": extracted_text,
                "paginas": [
                    {"pagina": page.page_number, "texto": page.text}
                    for page in pages
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return CorpusDocument(
        document_id=trace.document_id,
        process_id=process_metadata["process_id"],
        tipo_documento=tipo_documento,
        path=document_path,
        filename_original=trace.filename_original,
        filename_normalizado=trace.filename_normalizado,
        sha256=trace.sha256,
        timestamp_carga=trace.timestamp_carga,
        tamano_archivo=trace.tamano_archivo,
        texto_extraido=extracted_text,
        paginas=pages,
        metadata_proceso=process_metadata,
    )


def _cache_path(process_id: str, tipo_documento: str) -> Path:
    safe_process_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", process_id)
    return PROCESSED_TEXT_DIR / f"{safe_process_id}_{tipo_documento}.json"


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\ufeff", "").replace("\xa0", " ").strip()


def _validation_state(
    validation_rows: list[dict[str, str]],
    process_id: str,
    tipo_documento: str,
) -> str:
    for row in validation_rows:
        if row["process_id"] == process_id and row["tipo_documento"] == tipo_documento:
            return row["estado_validacion"]
    return ""


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-záéíóúñü]{3,}", text.lower())
    stopwords = {
        "del",
        "los",
        "las",
        "para",
        "con",
        "por",
        "una",
        "que",
        "como",
        "este",
        "esta",
        "ser",
        "son",
        "sus",
        "más",
        "sin",
        "entre",
        "sobre",
        "debe",
        "deberá",
        "entidad",
    }
    return [token for token in tokens if token not in stopwords]


def _tf_idf_vector(
    tokens: list[str],
    document_frequency: Counter[str],
    total_documents: int,
) -> dict[str, float]:
    term_frequency = Counter(tokens)
    total_terms = sum(term_frequency.values()) or 1
    vector = {}

    for term, count in term_frequency.items():
        tf = count / total_terms
        idf = math.log((1 + total_documents) / (1 + document_frequency[term])) + 1
        vector[term] = tf * idf

    return vector


def _cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    shared_terms = set(left).intersection(right)
    numerator = sum(left[term] * right[term] for term in shared_terms)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    denominator = left_norm * right_norm
    return numerator / denominator if denominator else 0.0


def _rarity_label(frequency: float) -> str:
    if frequency <= 0.2:
        return "Poco frecuente"
    if frequency >= 0.7:
        return "Frecuente"
    return "Intermedio"


def _rarity_comment(frequency: float) -> str:
    if frequency <= 0.2:
        return "Requisito poco frecuente en el corpus analizado; revisión humana sugerida."
    if frequency >= 0.7:
        return "Señal presente en la mayoría de procesos similares."
    return "Presencia intermedia respecto del histórico analizado."


def _similarity_comment(score: float) -> str:
    if score >= 0.9:
        return "Similitud documental muy alta; revisar posible reutilización extrema."
    if score >= 0.75:
        return "Similitud documental alta; revisar posible reutilización de especificaciones."
    return "Similitud documental moderada respecto del corpus."
