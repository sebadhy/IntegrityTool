"""Reproducible extraction pilot with immutable inputs and explicit cloud use."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pymupdf as fitz

from src.analyzer.corpus_validator import validate_corpus
from src.analyzer.metadata_reader import read_process_metadata

from . import extractors
from .extractors import BenchmarkError
from .metrics import score_reference, technical_metrics, validate_annotations


VERSION = "2026.11.extraction-pilot-v1"
MAX_BYTES = 25 * 1024 * 1024
MAX_PAGES = 500


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise BenchmarkError("Se esperaba un objeto JSON.")
    return value


def _local_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve(strict=True)
    if not path.is_relative_to(root.resolve()) or not path.is_file() or path.suffix.lower() != ".pdf":
        raise BenchmarkError("El PDF debe pertenecer a la raiz documental declarada.")
    return path


def inspect_pdf(content: bytes) -> int:
    if not content or len(content) > MAX_BYTES:
        raise BenchmarkError("El PDF esta vacio o supera 25 MB.")
    try:
        with fitz.open(stream=content, filetype="pdf") as pdf:
            if pdf.needs_pass or not 1 <= len(pdf) <= MAX_PAGES:
                raise BenchmarkError("El PDF requiere clave o supera el limite de 500 paginas.")
            return len(pdf)
    except (fitz.FileDataError, RuntimeError):
        raise BenchmarkError("El PDF no se pudo abrir; verifique su integridad.") from None


def prepare_manifest(root: Path, metadata: Path, process_ids: list[str], limit: int, seed: str) -> dict:
    rows = read_process_metadata(metadata)
    if not rows:
        raise BenchmarkError("El CSV del corpus esta vacio o no esta disponible.")
    validation = validate_corpus(rows, {role: root / "data/raw" / folder for role, folder in (
        ("pliego", "pliegos"), ("especificaciones", "especificaciones"))})
    if validation["has_critical_errors"]:
        raise BenchmarkError("Resuelva las inconsistencias criticas del corpus antes de congelar la muestra.")
    by_id = {row["process_id"].strip(): row for row in rows}
    if process_ids:
        if len(process_ids) != len(set(process_ids)) or any(value not in by_id for value in process_ids):
            raise BenchmarkError("Los identificadores solicitados deben ser exactos, conocidos y unicos.")
        selected = sorted(process_ids)
    else:
        if limit < 1:
            raise BenchmarkError("El limite de procesos debe ser positivo.")
        selected = sorted(by_id, key=lambda value: digest(f"{seed}|{value}".encode()))[:limit]
    documents, hashes = [], set()
    for process_id in selected:
        for role in ("pliego", "especificaciones"):
            trace = validation["traces"].get((process_id, role))
            if trace is None:
                raise BenchmarkError("Falta un documento del proceso seleccionado.")
            relative = str(trace.path_exacto.relative_to(root.resolve()))
            path = _local_path(root, relative)
            if path.stat().st_size > MAX_BYTES:
                raise BenchmarkError("El PDF supera el limite de tamano del benchmark.")
            content = path.read_bytes()
            if trace.sha256 in hashes:
                raise BenchmarkError("La muestra contiene PDFs identicos; revise su asociacion documental.")
            hashes.add(trace.sha256)
            documents.append({"document_id": "doc-" + trace.sha256[:20], "process_id": process_id,
                "role": role, "path": Path(relative).as_posix(), "sha256": trace.sha256,
                "byte_size": len(content), "page_count": inspect_pdf(content),
                "split": "calibration", "category": "pending_human_classification",
                "source_metadata": by_id[process_id]})
    return {"schema_version": 1, "benchmark_version": VERSION,
            "metadata_sha256": digest(metadata.read_bytes()),
            "selection": {"method": "explicit_process_ids" if process_ids else "seeded_process_order",
                          "seed": seed, "process_count": len(selected), "independent_evaluation": False},
            "notes": ["Muestra de calibracion: los documentos ya estaban disponibles durante el desarrollo.",
                      "La metadata del corpus es una fuente declarada, no una anotacion experta.",
                      "La seleccion no acredita representatividad por categoria ni precision institucional."],
            "validation_notes": [row for row in validation["rows"] if row["estado_validacion"] != "OK"],
            "documents": documents}


def verified_inputs(manifest: dict, root: Path) -> list[tuple[dict, Path, bytes]]:
    if (not isinstance(manifest, dict) or manifest.get("schema_version") != 1
            or not isinstance(manifest.get("documents"), list) or not manifest["documents"]):
        raise BenchmarkError("Manifiesto vacio o con version no admitida.")
    result, identities, hashes, splits = [], set(), set(), {}
    for doc in manifest["documents"]:
        if not isinstance(doc, dict):
            raise BenchmarkError("Cada documento del manifiesto debe ser un objeto JSON.")
        identity, sha = doc.get("document_id", ""), doc.get("sha256", "")
        if (not isinstance(identity, str) or not identity.startswith("doc-")
                or not identity[4:].isalnum() or identity in identities
                or not isinstance(sha, str) or len(sha) != 64
                or any(char not in "0123456789abcdef" for char in sha) or sha in hashes
                or doc.get("split") not in ("calibration", "evaluation")
                or not isinstance(doc.get("process_id"), str) or not doc["process_id"].strip()
                or not isinstance(doc.get("path"), str) or not doc["path"].strip()):
            raise BenchmarkError("Identidad, hash, proceso o particion documental no validos.")
        process_id = doc["process_id"]
        if process_id in splits and splits[process_id] != doc["split"]:
            raise BenchmarkError("Los documentos de un proceso deben permanecer en la misma particion.")
        splits[process_id] = doc["split"]
        identities.add(identity)
        hashes.add(sha)
        path = _local_path(root, doc["path"])
        if path.stat().st_size > MAX_BYTES:
            raise BenchmarkError("El PDF supera el limite de tamano del benchmark.")
        content = path.read_bytes()
        if (digest(content) != sha or len(content) != doc.get("byte_size")
                or inspect_pdf(content) != doc.get("page_count")):
            raise BenchmarkError("Un PDF cambio respecto del manifiesto; prepare otra muestra.")
        result.append((doc, path, content))
    return result


def _dependency(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False


def preflight(backends: list[str], inputs: list, allow_cloud: bool, cloud_page_limit: int,
              artifacts: Path | None) -> None:
    if not backends or len(backends) != len(set(backends)) or any(b not in extractors.BACKENDS for b in backends):
        raise BenchmarkError("Seleccione extractores conocidos sin duplicarlos.")
    if "azure-layout" in backends:
        if not allow_cloud or cloud_page_limit < 1:
            raise BenchmarkError("Azure requiere --allow-cloud y --cloud-page-limit positivos.")
        if sum(doc["page_count"] for doc, _, _ in inputs) > cloud_page_limit:
            raise BenchmarkError("La muestra supera el limite autorizado de paginas para Azure.")
        extractors.azure_configuration()
        if not _dependency("azure.ai.documentintelligence"):
            raise BenchmarkError("Instale benchmarks/requirements-azure.txt en el entorno de evaluacion.")
    if "docling" in backends:
        if not _dependency("docling"):
            raise BenchmarkError("Instale benchmarks/requirements-docling.txt en un entorno aislado.")
        if artifacts is None or not artifacts.is_dir():
            raise BenchmarkError("Docling requiere --docling-artifacts con modelos preparados localmente.")


def _git(root: Path, *args: str) -> str | None:
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                              text=True, timeout=10, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def provenance(root: Path) -> dict:
    files = sorted(Path(__file__).parent.glob("*.py"))
    return {"application_commit": _git(root, "rev-parse", "HEAD"),
            "working_tree_status": _git(root, "status", "--porcelain"),
            "benchmark_source_sha256": digest(b"".join(p.name.encode() + p.read_bytes() for p in files)),
            "python": sys.version, "platform": platform.platform(),
            "tesseract_available": shutil.which("tesseract") is not None,
            "packages": {name: extractors.package_version(name) for name in
                         ("PyMuPDF", "pytesseract", "docling", "docling-core", "azure-ai-documentintelligence")}}


def _csv_cell(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def write_reports(output: Path, report: dict) -> None:
    write_json(output / "report.json", report)
    columns = ["document_id", "process_id", "backend", "status", "elapsed_seconds", "page_count",
               "pages_with_text", "characters", "blocks", "tables", "cells", "incomplete_pages",
               "cloud_pages_attempted", "cost_estimate", "error"]
    with (output / "metrics.csv").open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for record in report["records"]:
            flat = {**record, **record.get("metrics", {})}
            writer.writerow({key: _csv_cell(flat.get(key, "")) for key in columns})
    rows = []
    for record in report["records"]:
        metrics = record.get("metrics", {})
        values = [record["process_id"], record["role"], record["backend"], record["status"],
                  record["page_count"], metrics.get("pages_with_text", ""), metrics.get("tables", ""),
                  f'{record["elapsed_seconds"]:.3f}', record.get("error", "")]
        rows.append("<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in values) + "</tr>")
    page = ('<!doctype html><html lang="es"><meta charset="utf-8"><title>Benchmark documental</title>'
            '<style>body{font:15px system-ui;margin:32px;color:#24312d}table{border-collapse:collapse}'
            'th,td{padding:8px;text-align:left;border-bottom:1px solid #ddd}p{max-width:900px}</style>'
            '<h1>Benchmark de extraccion documental</h1><p>Mediciones tecnicas de calibracion. '
            'Mas texto o tablas no demuestra mejor precision. Las referencias expertas se evaluan por separado. '
            'El costo monetario no se ha estimado; las llamadas externas pueden tener costo.</p>'
            '<table><thead><tr>' + ''.join(f'<th>{name}</th>' for name in
                ('Proceso', 'Documento', 'Extractor', 'Estado', 'Paginas', 'Con texto', 'Tablas', 'Segundos', 'Detalle'))
            + '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></html>')
    (output / "report.html").write_text(page, encoding="utf-8")


def run_benchmark(manifest_path: Path, root: Path, output: Path, backends: list[str], *,
                  allow_cloud: bool = False, cloud_page_limit: int = 0,
                  artifacts: Path | None = None) -> dict:
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    inputs = verified_inputs(manifest, root)
    preflight(backends, inputs, allow_cloud, cloud_page_limit, artifacts)
    output.mkdir(parents=True, exist_ok=False)
    with (output / "manifest.json").open("xb") as stream:
        stream.write(manifest_bytes)
    report = {"schema_version": 1, "benchmark_version": VERSION,
              "manifest_sha256": digest(manifest_bytes),
              "started_at": datetime.now(timezone.utc).isoformat(), "provenance": provenance(root),
              "llm_calls": 0, "cloud_authorized": allow_cloud, "cloud_page_limit": cloud_page_limit,
              "backends": backends, "accuracy": None, "records": []}
    for doc, _, content in inputs:
        for backend in backends:
            start = time.perf_counter()
            record = {"document_id": doc["document_id"], "document_sha256": doc["sha256"],
                      "process_id": doc["process_id"], "role": doc["role"], "split": doc["split"],
                      "backend": backend, "page_count": doc["page_count"], "status": "failed",
                      "cloud_pages_attempted": doc["page_count"] if backend == "azure-layout" else 0,
                      "cost_estimate": None, "error": ""}
            try:
                if backend == "current":
                    result = extractors.extract_current(content)
                elif backend == "pymupdf-layout":
                    result = extractors.extract_pymupdf_layout(content)
                elif backend == "azure-layout":
                    result = extractors.extract_azure(content)
                else:
                    saved = {key: os.environ.get(key) for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")}
                    try:
                        os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
                        result = extractors.extract_docling(content, artifacts)
                    finally:
                        for key, value in saved.items():
                            if value is None:
                                os.environ.pop(key, None)
                            else:
                                os.environ[key] = value
                numbers = [page["page"] for page in result["pages"]]
                if len(set(numbers)) != len(numbers) or any(not 1 <= n <= doc["page_count"] for n in numbers):
                    raise BenchmarkError("El extractor devolvio paginas duplicadas o fuera del documento.")
                record["metrics"] = technical_metrics(result)
                record["status"] = ("completed" if len(numbers) == doc["page_count"]
                                     and not record["metrics"]["incomplete_pages"] else "partial")
                if record["status"] == "partial":
                    record["error"] = "Lectura parcial: faltan paginas o hay OCR pendiente o fallido."
                relative = f'artifacts/{doc["document_id"]}.{backend}.json'
                write_json(output / relative, result)
                record.update(artifact=relative, artifact_sha256=digest((output / relative).read_bytes()))
            except Exception as exc:
                record["error"] = (str(exc) if isinstance(exc, BenchmarkError) else
                    f"El extractor no completo el documento ({type(exc).__name__}). Revise el entorno aislado.")
            record["elapsed_seconds"] = round(time.perf_counter() - start, 6)
            report["records"].append(record)
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_reports(output, report)
    write_json(output / "annotations.template.json", {"schema_version": 1,
        "manifest_sha256": report["manifest_sha256"], "documents": [
            {"document_id": doc["document_id"], "document_sha256": doc["sha256"],
             "review_status": "pending", "reviewers": [], "adjudicated_by": "", "fields": []}
            for doc, _, _ in inputs]})
    return report


def evaluate_run(run: Path, annotations: Path) -> dict:
    report = read_json(run / "report.json")
    manifest = read_json(run / "manifest.json")
    if digest((run / "manifest.json").read_bytes()) != report["manifest_sha256"]:
        raise BenchmarkError("El manifiesto guardado fue modificado.")
    references = validate_annotations(read_json(annotations), manifest, report["manifest_sha256"])
    by_id = {doc["document_id"]: doc for doc in references}
    documents = {doc["document_id"]: doc for doc in manifest["documents"]}
    expected = {(identity, backend) for identity in documents for backend in report["backends"]}
    actual = [(record["document_id"], record["backend"]) for record in report["records"]]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise BenchmarkError("El reporte contiene mediciones repetidas o faltantes.")
    totals = {}
    details = []
    for record in report["records"]:
        if record.get("document_sha256") != documents[record["document_id"]]["sha256"]:
            raise BenchmarkError("La medicion no corresponde al hash documental del manifiesto.")
        reference = by_id.get(record["document_id"])
        if reference is None:
            continue
        result = {"pages": []}
        if record.get("artifact"):
            path = (run / record["artifact"]).resolve(strict=True)
            if not path.is_relative_to(run.resolve()) or digest(path.read_bytes()) != record["artifact_sha256"]:
                raise BenchmarkError("El artefacto de extraccion fue modificado o esta fuera de la ejecucion.")
            result = read_json(path)
        score = score_reference(result, reference)
        details.append({"document_id": record["document_id"], "backend": record["backend"], **score})
        total = totals.setdefault(record["backend"], {key: 0 for key in
            ("reference_checks", "recovered_checks", "location_checks", "matched_locations")})
        for key in total:
            total[key] += score[key]
    for total in totals.values():
        total["reference_recovery_rate"] = total["recovered_checks"] / total["reference_checks"]
        total["source_location_rate"] = (total["matched_locations"] / total["location_checks"]
                                         if total["location_checks"] else None)
    return {"schema_version": 1, "manifest_sha256": report["manifest_sha256"],
            "annotations_sha256": digest(annotations.read_bytes()), "adjudicated_documents": len(references),
            "status": "evaluated" if references else "pending_human_reference", "backends": totals,
            "checks": details, "limitation": "Recuperacion de referencias anotadas, no precision institucional ni recall exhaustivo."}


def main():
    parser = argparse.ArgumentParser(description="Benchmark de fidelidad documental de Integrity Tool.")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Congelar muestra local por proceso y SHA-256.")
    prepare.add_argument("--root", type=Path, default=Path.cwd())
    prepare.add_argument("--metadata", type=Path)
    prepare.add_argument("--process-id", action="append", default=[])
    prepare.add_argument("--limit", type=int, default=6)
    prepare.add_argument("--seed", default="integrity-extraction-pilot-v1")
    prepare.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run", help="Comparar extractores sin modificar revisiones existentes.")
    run.add_argument("--root", type=Path, default=Path.cwd())
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--backends", nargs="+", choices=extractors.BACKENDS, default=["current", "pymupdf-layout"])
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--allow-cloud", action="store_true")
    run.add_argument("--cloud-page-limit", type=int, default=0)
    run.add_argument("--docling-artifacts", type=Path)
    score = commands.add_parser("score", help="Medir referencias expertas resueltas, separadas de la extraccion.")
    score.add_argument("--run", type=Path, required=True)
    score.add_argument("--annotations", type=Path, required=True)
    score.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            value = prepare_manifest(args.root.resolve(), args.metadata or args.root / "data/raw/metadata/procesos.csv",
                                     args.process_id, args.limit, args.seed)
            write_json(args.output, value)
            print(f'Muestra preparada: {len(value["documents"])} documentos. Anotacion experta pendiente.')
        elif args.command == "run":
            value = run_benchmark(args.manifest, args.root.resolve(), args.output, args.backends,
                                  allow_cloud=args.allow_cloud, cloud_page_limit=args.cloud_page_limit,
                                  artifacts=args.docling_artifacts)
            failures = sum(record["status"] != "completed" for record in value["records"])
            print(f'Benchmark terminado: {len(value["records"])} mediciones, {failures} parciales o fallidas.')
            if failures:
                raise SystemExit(2)
        else:
            value = evaluate_run(args.run, args.annotations)
            write_json(args.output, value)
            print(f'Evaluacion: {value["status"]}; documentos resueltos: {value["adjudicated_documents"]}.')
    except (BenchmarkError, FileExistsError, FileNotFoundError, json.JSONDecodeError) as exc:
        message = str(exc) if isinstance(exc, BenchmarkError) else "Revise archivos de entrada y use una salida nueva."
        parser.exit(2, message + "\n")


if __name__ == "__main__":
    main()
