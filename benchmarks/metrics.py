"""Technical measurements and recovery checks against adjudicated references.

These checks assess document extraction, not the relevance or legal meaning of
an observation. Unlabelled documents never receive an accuracy estimate.
"""
from __future__ import annotations

import math
import re
import unicodedata

from .extractors import BenchmarkError


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).casefold()).strip()


def contains_reference(text: str, expected: str) -> bool:
    needle = normalized(expected)
    if not needle:
        return False
    pattern = (r"(?<!\w)" if needle[0].isalnum() else "") + re.escape(needle)
    pattern += r"(?!\w)" if needle[-1].isalnum() else ""
    return re.search(pattern, normalized(text)) is not None


def valid_bbox(value) -> bool:
    return (isinstance(value, list) and len(value) == 4
            and all(isinstance(v, (float, int)) and not isinstance(v, bool) and math.isfinite(v)
                    and 0 <= v <= 1 for v in value)
            and value[0] < value[2] and value[1] < value[3])


def technical_metrics(result: dict) -> dict:
    pages = result["pages"]
    blocks = [block for page in pages for block in page["blocks"]]
    tables = [table for page in pages for table in page["tables"]]
    return {"pages_returned": len(pages), "pages_with_text": sum(bool(p["text"].strip()) for p in pages),
            "characters": sum(len(p["text"]) for p in pages), "blocks": len(blocks),
            "blocks_with_geometry": sum(valid_bbox(b.get("bbox")) for b in blocks),
            "tables": len(tables), "cells": sum(len(t["cells"]) for t in tables),
            "ocr_pages": sum(p["status"] == "ocr_ok" for p in pages),
            "incomplete_pages": sum(p["status"] in {"ocr_failed", "requires_ocr"} for p in pages)}


def validate_annotations(annotations: dict, manifest: dict, digest: str) -> list[dict]:
    if annotations.get("schema_version") != 1 or annotations.get("manifest_sha256") != digest:
        raise BenchmarkError("Las anotaciones no corresponden al manifiesto de esta ejecucion.")
    if not isinstance(annotations.get("documents"), list):
        raise BenchmarkError("Las anotaciones deben incluir una lista de documentos.")
    documents = {doc["document_id"]: doc for doc in manifest["documents"]}
    seen, ready = set(), []
    for doc in annotations.get("documents", []):
        if not isinstance(doc, dict) or not isinstance(doc.get("document_id"), str):
            raise BenchmarkError("Cada anotacion debe identificar un documento.")
        identity = doc.get("document_id")
        if identity not in documents or identity in seen:
            raise BenchmarkError("Documento desconocido o repetido en las anotaciones.")
        seen.add(identity)
        if doc.get("document_sha256") != documents[identity]["sha256"]:
            raise BenchmarkError("El hash del documento anotado no coincide.")
        if doc.get("review_status") not in ("pending", "adjudicated"):
            raise BenchmarkError("Estado de anotacion no valido.")
        if doc["review_status"] != "adjudicated":
            continue
        reviewers = doc.get("reviewers", [])
        if (not isinstance(reviewers, list)
                or any(not isinstance(value, str) or not value.strip() for value in reviewers)
                or len({value.strip().casefold() for value in reviewers}) < 2
                or not isinstance(doc.get("adjudicated_by"), str) or not doc["adjudicated_by"].strip()):
            raise BenchmarkError("Registre dos revisores y quien resolvio la anotacion.")
        if not isinstance(doc.get("fields"), list) or not doc["fields"]:
            raise BenchmarkError("Una anotacion resuelta debe contener referencias verificables.")
        field_ids = set()
        for field in doc["fields"]:
            if not isinstance(field, dict):
                raise BenchmarkError("Cada referencia anotada debe ser un objeto JSON.")
            page = field.get("page")
            if (not isinstance(field.get("field_id"), str) or not field["field_id"].strip()
                    or field["field_id"] in field_ids or not isinstance(page, int) or isinstance(page, bool)
                    or not 1 <= page <= documents[identity]["page_count"]
                    or not isinstance(field.get("expected_text"), str) or not field["expected_text"].strip()
                    or field.get("kind") not in ("text", "table_cell")):
                raise BenchmarkError("Referencia anotada incompleta, repetida o fuera de pagina.")
            field_ids.add(field["field_id"])
            if field.get("expected_bbox") is not None and not valid_bbox(field["expected_bbox"]):
                raise BenchmarkError("Las coordenadas anotadas deben estar normalizadas entre cero y uno.")
            if field["kind"] == "table_cell" and any(
                    not isinstance(field.get(key), str) or not field[key].strip()
                    for key in ("row_anchor", "column_header")):
                raise BenchmarkError("Una celda anotada necesita referencia de fila y encabezado de columna.")
        ready.append(doc)
    return ready


def _intersection_over_union(left: list, right: list) -> float:
    width = max(0, min(left[2], right[2]) - max(left[0], right[0]))
    height = max(0, min(left[3], right[3]) - max(left[1], right[1]))
    intersection = width * height
    union = ((left[2] - left[0]) * (left[3] - left[1])
             + (right[2] - right[0]) * (right[3] - right[1]) - intersection)
    return intersection / union if union else 0.0


def score_reference(result: dict, reference: dict) -> dict:
    pages = {page["page"]: page for page in result.get("pages", [])}
    checks = []
    for field in reference["fields"]:
        page = pages.get(field["page"], {"text": "", "blocks": [], "tables": []})
        expected = normalized(field["expected_text"])
        candidates = []
        if field["kind"] == "table_cell":
            for table in page["tables"]:
                cells = table["cells"]
                for cell in cells:
                    if normalized(cell["text"]) != expected:
                        continue
                    row_found = any(other["row"] == cell["row"]
                                    and contains_reference(other["text"], field["row_anchor"])
                                    for other in cells)
                    header_found = any(other["column"] == cell["column"] and other["row"] < cell["row"]
                                       and normalized(field["column_header"]) == normalized(other["text"])
                                       for other in cells)
                    if row_found and header_found:
                        candidates.append(cell)
            recovered = bool(candidates)
        else:
            recovered = contains_reference(page["text"], expected)
            candidates = [block for block in page["blocks"] if contains_reference(block["text"], expected)]
        target_box = field.get("expected_bbox")
        location = (any(valid_bbox(item.get("bbox")) and
                        _intersection_over_union(item["bbox"], target_box) >= 0.5 for item in candidates)
                    if target_box is not None else None)
        checks.append({"field_id": field["field_id"], "kind": field["kind"], "page": field["page"],
                       "recovered": recovered, "location_matches": location})
    return {"checks": checks, "reference_checks": len(checks),
            "recovered_checks": sum(check["recovered"] for check in checks),
            "location_checks": sum(check["location_matches"] is not None for check in checks),
            "matched_locations": sum(check["location_matches"] is True for check in checks)}
