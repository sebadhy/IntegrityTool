"""Loopback-first API for the review workbench; Streamlit remains optional."""
from __future__ import annotations

import csv
import html
import io
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse

from dotenv import load_dotenv

# Environment must be loaded before modules with path configuration.
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .analyzer.workbench_service import MAX_FILE_BYTES, MAX_TOTAL_BYTES, WorkbenchService

LOGGER = logging.getLogger(__name__)


class ReviewUpdate(BaseModel):
    state: Literal["pending", "confirmed", "discarded", "followup"]
    comment: str = Field(default="", max_length=4000)
    reviewer: str = Field(default="Revisor local", min_length=1, max_length=120)


def create_app(storage: Path | None = None, assisted: bool | None = None, corpus_provider=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        service = WorkbenchService(ROOT, storage or Path(os.getenv("INTEGRITY_STORE_PATH", ROOT / "data/workbench/reviews.sqlite3")),
                                   assisted=assisted if assisted is not None else os.getenv("INTEGRITY_ASSISTED_ENABLED", "true").lower() == "true", corpus_provider=corpus_provider)
        service.store.interrupt_unfinished()
        app.state.service = service
        yield
        service.close()

    app = FastAPI(title="Integrity Tool", docs_url=None, redoc_url=None, lifespan=lifespan)

    @app.middleware("http")
    async def local_access(request: Request, call_next):
        # No permissive CORS; reject cross-origin browser mutations / DNS rebinding.
        if request.url.hostname not in {"127.0.0.1", "localhost", "testserver"}:
            return JSONResponse({"detail": "Esta versión está habilitada solo para acceso local."}, status_code=403)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and urlparse(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "Origen de solicitud no autorizado."}, status_code=403)
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > MAX_TOTAL_BYTES + 1024 * 1024):
            return JSONResponse({"detail": "La carga supera el tamaño permitido."}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; font-src 'self' blob: data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        return response

    @app.exception_handler(ValueError)
    async def invalid_request(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        LOGGER.exception("Workbench request failed", exc_info=exc)
        return JSONResponse({"detail": "No se pudo completar la acción. Intente nuevamente."}, status_code=500)

    def get_case(case_id):
        case = app.state.service.store.get_case(case_id)
        if not case:
            raise HTTPException(404, "La revisión no existe.")
        return case

    @app.get("/api/health")
    def health():
        return {"status": "ok", "mode": "local_pilot"}

    @app.get("/api/cases")
    def cases():
        return app.state.service.store.list_cases()

    @app.post("/api/cases", status_code=202)
    async def create_case(files: Annotated[list[UploadFile], File()], manifest: Annotated[str, Form()],
                          request_key: Annotated[str, Form()], title: Annotated[str, Form()] = ""):
        try:
            info = json.loads(manifest)
        except json.JSONDecodeError as exc:
            raise ValueError("La selección documental no es válida.") from exc
        if not isinstance(info, list) or len(info) != len(files) or len(files) > 8 or not all(isinstance(row, dict) for row in info):
            raise ValueError("Los tipos documentales no corresponden a los archivos seleccionados.")
        entries, total = [], 0
        for index, upload in enumerate(files):
            content = await upload.read(MAX_FILE_BYTES + 1)
            total += len(content)
            await upload.close()
            if len(content) > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
                raise HTTPException(413, "Cada PDF admite hasta 25 MB; el expediente completo, hasta 100 MB.")
            entries.append({**info[index], "name": upload.filename or "documento.pdf", "content": content})
        return app.state.service.create(title, request_key, entries)

    @app.get("/api/cases/{case_id}")
    def case_detail(case_id: str):
        return get_case(case_id)

    @app.post("/api/cases/{case_id}/retry", status_code=202)
    def retry(case_id: str):
        get_case(case_id)
        app.state.service.retry(case_id)
        return get_case(case_id)

    @app.get("/api/cases/{case_id}/documents/{document_id}")
    def document(case_id: str, document_id: str):
        doc = app.state.service.store.document(case_id, document_id)
        if not doc:
            raise HTTPException(404, "El documento no pertenece a esta revisión.")
        return Response(content=doc["content"], media_type="application/pdf")

    @app.put("/api/cases/{case_id}/items/{item_id}/review")
    def review(case_id: str, item_id: str, update: ReviewUpdate):
        case = get_case(case_id)
        if not any(item["id"] == item_id for item in (case["result"] or {}).get("items", [])):
            raise HTTPException(404, "La observación no pertenece a esta revisión.")
        app.state.service.store.save_review(case_id, item_id, update.state, update.comment, update.reviewer.strip())
        return get_case(case_id)["reviews"][item_id]

    @app.get("/api/cases/{case_id}/history")
    def history(case_id: str):
        get_case(case_id)
        return app.state.service.store.events(case_id)

    @app.get("/api/cases/{case_id}/taxonomy")
    def taxonomy_snapshot(case_id: str):
        case = get_case(case_id)
        provenance = (case.get("result") or {}).get("provenance", {})
        if not provenance.get("taxonomy_archived"):
            raise HTTPException(409, "Esta revisión no conserva una copia de la taxonomía utilizada.")
        digest = provenance.get("taxonomy_sha256", "")
        source = app.state.service.store.get_taxonomy(digest)
        if source is None:
            raise HTTPException(404, "La copia de la taxonomía no está disponible.")
        return Response(source.encode("utf-8"), media_type="application/yaml",
                        headers={"Content-Disposition": f'attachment; filename="taxonomia-{digest[:12]}.yaml"'})

    @app.get("/api/cases/{case_id}/export")
    def export(case_id: str, format: Literal["html", "csv", "json"] = "html"):
        case = get_case(case_id)
        if not case["result"]:
            raise HTTPException(409, "Espere a que finalice la lectura documental.")
        if format == "json":
            body, media = json.dumps(case, ensure_ascii=False, indent=2), "application/json"
        elif format == "csv":
            out = io.StringIO()
            writer = csv.writer(out)
            writer.writerow(["observacion_id", "patron", "titulo", "prioridad_revision", "documento", "pagina", "fragmento", "mitigantes", "preguntas", "estado_humano", "comentario", "engine_version", "taxonomy_sha256", "fuentes", "metodos_identificacion"])
            for item in case["result"]["items"]:
                for ev in item["evidence"]:
                    review = case["reviews"].get(item["id"], {})
                    cells = [item["id"], item["pattern_id"], item["title"], item["priority"], ev["document_name"], ev["page"], ev["text"], "; ".join(item["mitigants"]), "; ".join(item["questions"]), review.get("state", "pending"), review.get("comment", ""), case["result"]["provenance"]["engine_version"], case["result"]["provenance"]["taxonomy_sha256"], "; ".join(item.get("sources", [])), "; ".join(item.get("analysis_methods", ["deterministic_rules"]))]
                    writer.writerow([_csv_cell(cell) for cell in cells])
            body, media = "\ufeff" + out.getvalue(), "text/csv"
        else:
            body, media = _html_report(case), "text/html"
        return Response(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="revision-{case_id}.{format}"'})

    dist = ROOT / "frontend/dist"
    if dist.is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
        if (dist / "pdf-assets").is_dir():
            app.mount("/pdf-assets", StaticFiles(directory=dist / "pdf-assets"), name="pdf-assets")

        @app.get("/")
        def index():
            return FileResponse(dist / "index.html")
    return app


def _csv_cell(value):
    text = str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else text


def _html_report(case):
    esc = lambda value: html.escape(str(value))
    result = case["result"]
    parts = [f'<!doctype html><html lang="es"><meta charset="utf-8"><title>{esc(case["title"])}</title><style>body{{font:15px/1.6 system-ui;max-width:900px;margin:40px auto;padding:20px;color:#223438}}article{{border-top:1px solid #ccd5d6;margin-top:28px}}blockquote{{border-left:3px solid #297a70;padding-left:16px}}small{{color:#526466}}</style><h1>{esc(case["title"])}</h1><p>Lectura preliminar para revisión humana.</p><p>{esc(result.get("assisted_summary") or result["summary"])}</p>']
    for doc in result["documents"]:
        parts.append(f'<p><strong>{esc(doc["name"])}</strong> · {esc(doc["role"])} · versión {esc(doc["version"])}<br><small>SHA256: {esc(doc["sha256"])}</small></p>')
    semantic = result.get("semantic_review", {})
    coverage = semantic.get("coverage") or {}
    if semantic.get("status") == "completed":
        parts.append(f'<p>Lectura contextual adicional: {esc(coverage.get("selected_clause_count", 0))} de {esc(coverage.get("active_clause_count", 0))} cláusulas activas. Las citas se comprueban; las interpretaciones requieren validación humana. No es una revisión semántica completa.</p>')
    for item in result["items"]:
        review = case["reviews"].get(item["id"], {})
        parts.append(f'<article><h2>{esc(item["title"])}</h2><p>Prioridad de revisión: {esc(item["priority"])} · Estado humano: {esc(review.get("state", "pending"))}</p><p>{esc(item["explanation"])}</p>')
        parts.append(f'<small>Origen: {esc(" + ".join(item.get("sources", ["Taxonomía documental"])))}</small>')
        for ev in item["evidence"]:
            parts.append(f'<small>{esc(ev["document_name"])} · página {ev["page"]}</small><blockquote>{esc(ev["text"])}</blockquote>')
        parts.append(f'<p>Mitigantes: {esc("; ".join(item["mitigants"]) or "No identificados en los fragmentos revisados.")}</p><p>Qué validar: {esc(" ".join(item["questions"]))}</p><p>Comentario: {esc(review.get("comment", ""))}</p></article>')
    parts.append(f'<hr><p>La lectura es preliminar y no reemplaza el análisis técnico o jurídico. Las frecuencias históricas no acreditan validez de requisitos. El procesamiento asistido puede proponer candidatos y redactar contexto; no asigna prioridad final ni valida la interpretación por sí solo.</p><small>{esc(json.dumps(result["provenance"], ensure_ascii=False))}</small></html>')
    return "".join(parts)


app = create_app()
