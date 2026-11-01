"""Extraction adapters for comparing document fidelity with retained evidence."""
from __future__ import annotations

import importlib.metadata
import io
import math
import os
from pathlib import Path
from urllib.parse import urlparse

import pymupdf as fitz

from src.analyzer.pdf_extractor import extract_text_by_page


BACKENDS = ("current", "pymupdf-layout", "azure-layout", "docling")
AZURE_API_VERSION = "2024-11-30"


class BenchmarkError(ValueError):
    """An actionable, credential-free evaluation error."""


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _bbox(values, width: float, height: float) -> list[float] | None:
    if not values or width <= 0 or height <= 0 or not all(math.isfinite(v) for v in (*values, width, height)):
        return None
    x0, y0, x1, y1 = values
    box = [max(0.0, min(1.0, value)) for value in
           (x0 / width, y0 / height, x1 / width, y1 / height)]
    return box if box[0] < box[2] and box[1] < box[3] else None


def _native_box(values, page) -> list[float] | None:
    if values is None:
        return None
    rect = fitz.Rect(values) * page.rotation_matrix
    return _bbox(rect, page.rect.width, page.rect.height)


def extract_current(content: bytes) -> dict:
    pages = extract_text_by_page(content)
    return {"pages": [{"page": p.page_number, "text": p.text, "status": p.status.value,
                       "blocks": [], "tables": []} for p in pages],
            "notes": ["Contrato actual: texto y estado OCR por pagina; sin geometria estructurada."]}


def extract_pymupdf_layout(content: bytes) -> dict:
    baseline = extract_text_by_page(content)
    pages = []
    with fitz.open(stream=content, filetype="pdf") as document:
        for page, source in zip(document, baseline, strict=True):
            # OCR text remains available, but native PDF geometry is not OCR geometry.
            native = source.status.value in {"ok", "empty"} and bool(source.text.strip())
            blocks, tables = [], []
            if native:
                blocks = [{"text": block[4].strip(), "bbox": _native_box(block[:4], page)}
                          for block in page.get_text("blocks", sort=True)
                          if block[6] == 0 and block[4].strip()]
                for table in page.find_tables().tables:
                    cells = []
                    for row_index, row in enumerate(table.extract()):
                        for column_index, text in enumerate(row):
                            cells.append({"row": row_index, "column": column_index,
                                          "text": text or "", "bbox": _native_box(
                                              table.rows[row_index].cells[column_index], page)})
                    tables.append({"rows": table.row_count, "columns": table.col_count,
                                   "cells": cells, "bbox": _native_box(table.bbox, page)})
            pages.append({"page": source.page_number,
                          "text": "\n".join(b["text"] for b in blocks) if blocks else source.text,
                          "status": source.status.value, "blocks": blocks, "tables": tables})
    return {"pages": pages, "notes": [
        "Geometria normalizada sobre la pagina visible, con rotacion aplicada.",
        "El OCR conserva el texto del extractor actual; sus cajas no se reconstruyen.",
        "La deteccion de tablas nativas es una hipotesis a validar, no una garantia de estructura.",
    ]}


def azure_configuration() -> tuple[str, str]:
    endpoint = os.getenv("INTEGRITY_BENCHMARK_AZURE_ENDPOINT", "").strip()
    key = os.getenv("INTEGRITY_BENCHMARK_AZURE_KEY", "").strip()
    try:
        parsed = urlparse(endpoint)
        port = parsed.port
    except ValueError:
        raise BenchmarkError("El endpoint de Document Intelligence no tiene un formato valido.") from None
    if (parsed.scheme != "https" or not parsed.hostname
            or not parsed.hostname.endswith(".cognitiveservices.azure.com")
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"} or port not in {None, 443} or not key):
        raise BenchmarkError("Configure endpoint HTTPS de Document Intelligence y clave dedicados al benchmark.")
    return endpoint.rstrip("/"), key


def normalize_azure(raw: dict) -> dict:
    pages = []
    for page in raw.get("pages", []):
        width, height = page["width"], page["height"]
        blocks = []
        for line in page.get("lines", []):
            polygon = line.get("polygon", [])
            bounds = ([min(polygon[::2]), min(polygon[1::2]),
                       max(polygon[::2]), max(polygon[1::2])] if polygon else None)
            blocks.append({"text": line.get("content", ""), "bbox": _bbox(bounds, width, height)})
        pages.append({"page": page["pageNumber"], "text": "\n".join(b["text"] for b in blocks),
                      "status": "extracted", "blocks": blocks, "tables": []})
    by_number = {page["page"]: page for page in pages}
    dimensions = {page["pageNumber"]: (page["width"], page["height"]) for page in raw.get("pages", [])}
    for table in raw.get("tables", []):
        cells_by_page = {}
        for cell in table.get("cells", []):
            for region in cell.get("boundingRegions", []):
                number, polygon = region["pageNumber"], region.get("polygon", [])
                if number not in dimensions:
                    continue
                bounds = ([min(polygon[::2]), min(polygon[1::2]),
                           max(polygon[::2]), max(polygon[1::2])] if polygon else None)
                cells_by_page.setdefault(number, []).append({
                    "row": cell["rowIndex"], "column": cell["columnIndex"],
                    "text": cell.get("content", ""), "bbox": _bbox(bounds, *dimensions[number]),
                })
        for number, cells in cells_by_page.items():
            by_number[number]["tables"].append({"rows": table["rowCount"],
                "columns": table["columnCount"], "bbox": None, "cells": cells})
    return {"pages": pages, "raw": raw, "notes": [
        "Document Intelligence prebuilt-layout; conservar modelo, version y respuesta originales.",
    ]}


def extract_azure(content: bytes) -> dict:
    endpoint, key = azure_configuration()
    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.core.credentials import AzureKeyCredential
    with DocumentIntelligenceClient(endpoint, AzureKeyCredential(key),
            api_version=AZURE_API_VERSION, retry_total=0,
            connection_timeout=15, read_timeout=60, polling_interval=2) as client:
        poller = client.begin_analyze_document("prebuilt-layout", body=io.BytesIO(content))
        result = poller.result(timeout=180)
        return normalize_azure(result.as_dict())


def normalize_docling(raw: dict) -> dict:
    pages = []
    dimensions = {int(number): (value["size"]["width"], value["size"]["height"])
                  for number, value in raw.get("pages", {}).items()}
    for number in sorted(dimensions):
        pages.append({"page": number, "text": "", "status": "extracted", "blocks": [], "tables": []})
    by_number = {page["page"]: page for page in pages}

    def locations(item):
        for prov in item.get("prov", []):
            number, box = prov["page_no"], prov.get("bbox")
            if number not in dimensions:
                continue
            width, height = dimensions[number]
            bounds = None
            if box:
                bounds = [box["l"], box["t"], box["r"], box["b"]]
                if box.get("coord_origin") == "BOTTOMLEFT":
                    bounds = [box["l"], height - box["t"], box["r"], height - box["b"]]
            yield number, _bbox(bounds, width, height)

    for item in raw.get("texts", []):
        for prov in item.get("prov", []):
            text = item.get("text", "")
            if len(item["prov"]) > 1:
                span = prov.get("charspan")
                if not span or not 0 <= span[0] <= span[1] <= len(text):
                    continue
                text = text[span[0]:span[1]]
            for number, box in locations({"prov": [prov]}):
                by_number[number]["blocks"].append({"text": text, "bbox": box})
    for table in raw.get("tables", []):
        data = table.get("data", {})
        table_locations = list(locations(table))
        # Cell boxes alone cannot identify their page in a multipage table.
        if len(table_locations) != 1:
            continue
        for number, box in table_locations:
            cells = []
            for cell in data.get("table_cells", []):
                cell_box = cell.get("bbox")
                loc = list(locations({"prov": [{"page_no": number, "bbox": cell_box}]}))
                cells.append({"row": cell["start_row_offset_idx"],
                              "column": cell["start_col_offset_idx"], "text": cell.get("text", ""),
                              "bbox": loc[0][1] if loc else None})
            by_number[number]["tables"].append({"rows": data["num_rows"],
                "columns": data["num_cols"], "bbox": box, "cells": cells})
    for page in pages:
        page["text"] = "\n".join([b["text"] for b in page["blocks"]] +
                                 [c["text"] for t in page["tables"] for c in t["cells"]])
    return {"pages": pages, "raw": raw, "notes": [
        "Docling local con artefactos preparados y OCR Tesseract; sin servicios remotos.",
        "Las tablas multipagina sin ubicacion inequivoca se conservan en raw, sin atribuir celdas a paginas.",
    ]}


def extract_docling(content: bytes, artifacts: Path) -> dict:
    from docling.datamodel.base_models import DocumentStream, InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TesseractCliOcrOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption
    options = PdfPipelineOptions(artifacts_path=str(artifacts), enable_remote_services=False,
                                 allow_external_plugins=False,
                                 ocr_options=TesseractCliOcrOptions(lang=["spa", "eng"]))
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
    source = DocumentStream(name="benchmark.pdf", stream=io.BytesIO(content))
    result = converter.convert(source)
    if str(result.status.value) != "success":
        raise BenchmarkError("Docling no completo el documento; revise artefactos y OCR en su entorno aislado.")
    return normalize_docling(result.document.export_to_dict())
