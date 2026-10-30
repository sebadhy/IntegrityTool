"""One local worker, archived clauses and bounded optional semantic assistance.

No agents or external queues. Models propose; domain rules control final items.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

import pymupdf as fitz

from . import ENGINE_VERSION
from .case_review import consolidate_case
from .contextualizer import build_finding_candidates
from .domain_models import Clause, Signal
from .metadata_extractor import extract_pliego_metadata
from .review_pipeline import TaxonomyUnavailableError, analyze_document_bytes, finalize_candidates
from .review_store import ReviewStore, utc_now
from .taxonomy_loader import TaxonomyLoadResult, load_taxonomy
from .semantic_analyzer import SEMANTIC_VERSION, select_semantic_context, validate_semantic_proposals

LOGGER = logging.getLogger(__name__)
SERVICE_VERSION = "2026.10.workbench-v3"
ROLES = {"pliego", "especificaciones", "adenda", "anexo"}
MAX_DOCUMENTS, MAX_FILE_BYTES, MAX_TOTAL_BYTES, MAX_PAGES = 8, 25 * 1024**2, 100 * 1024**2, 400


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


class WorkbenchService:
    def __init__(self, root: Path, storage: Path, assisted: bool = True, corpus_provider=None):
        self.root = root
        self.store = ReviewStore(storage)
        self.assisted = assisted
        self.corpus_provider = corpus_provider
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="integrity-review")
        self.lock = threading.Lock()
        self.pending: set[str] = set()

    def close(self):
        self.executor.shutdown(wait=True, cancel_futures=True)

    def create(self, title: str, request_key: str, files: list[dict]) -> dict:
        if not request_key or len(request_key) > 100:
            raise ValueError("La solicitud de revisión no es válida.")
        if not 1 <= len(files) <= MAX_DOCUMENTS:
            raise ValueError(f"Seleccione entre 1 y {MAX_DOCUMENTS} documentos PDF.")
        if sum(len(file["content"]) for file in files) > MAX_TOTAL_BYTES:
            raise ValueError("El expediente supera el límite de 100 MB.")
        documents, hashes = [], set()
        for index, file in enumerate(files):
            content = file["content"]
            name = Path(file["name"].replace("\\", "/")).name
            if not name.lower().endswith(".pdf") or b"%PDF-" not in content[:1024] or len(content) > MAX_FILE_BYTES:
                raise ValueError("Cada archivo debe ser un PDF válido de hasta 25 MB.")
            digest = hashlib.sha256(content).hexdigest()
            if digest in hashes:
                raise ValueError("Hay documentos idénticos en la selección. Retire la copia repetida.")
            hashes.add(digest)
            role = file.get("role", "pliego")
            if role not in ROLES:
                raise ValueError("Seleccione un tipo documental válido.")
            supersedes_index = file.get("supersedes_index")
            if supersedes_index is not None and (not isinstance(supersedes_index, int) or not 0 <= supersedes_index < index):
                raise ValueError("La versión sustituida debe corresponder a un documento anterior de esta selección.")
            previous = documents[supersedes_index]["id"] if supersedes_index is not None else None
            if previous and any(doc.get("supersedes") == previous for doc in documents):
                raise ValueError("Una versión no puede ser sustituida por dos documentos a la vez.")
            documents.append({"id": str(uuid.uuid4()), "name": name[:240], "role": role,
                              "version": str(file.get("version") or "1")[:40], "sha256": digest,
                              "supersedes": previous, "content": content})
        with self.lock:
            if len(self.pending) >= 4:
                raise ValueError("Hay varias revisiones en curso. Espere a que termine una antes de iniciar otra.")
            case_id = self.store.create_case(str(uuid.uuid4()), request_key, title.strip()[:200] or documents[0]["name"], documents)
            case = self.store.get_case(case_id)
            if case["status"] == "queued" and case_id not in self.pending:
                self.pending.add(case_id)
                self.executor.submit(self.run, case_id)
        return self.store.get_case(case_id)

    def retry(self, case_id: str):
        with self.lock:
            case = self.store.get_case(case_id)
            if not case or case["status"] not in {"failed", "interrupted"} or case_id in self.pending:
                raise ValueError("Esta revisión no puede reintentarse en su estado actual.")
            if len(self.pending) >= 4:
                raise ValueError("Espere a que termine una revisión en curso.")
            self.store.update_case(case_id, "queued")
            self.pending.add(case_id)
            self.executor.submit(self.run, case_id)

    def run(self, case_id: str):
        self.store.update_case(case_id, "running")
        try:
            case = self.store.get_case(case_id)
            taxonomy = load_taxonomy()
            if not taxonomy.loaded or not taxonomy.patterns or not taxonomy.source_sha256:
                raise TaxonomyUnavailableError("No se pudo cargar una copia verificable de las reglas. No se completó la revisión.")
            self.store.save_taxonomy(taxonomy.source_sha256, taxonomy.source_text)
            excluded = {doc["sha256"] for doc in case["documents"]}
            context, corpus_info = (self.corpus_provider(excluded) if self.corpus_provider
                                    else self._corpus_context(excluded, taxonomy))
            documents, messages = [], []
            for info in case["documents"]:
                doc = self.store.document(case_id, info["id"])
                key = fingerprint([doc["sha256"], ENGINE_VERSION, taxonomy.source_sha256, SERVICE_VERSION, corpus_info])
                analysis = self.store.cache_get(key)
                cache_hit = analysis is not None
                if analysis is None:
                    with fitz.open(stream=doc["content"], filetype="pdf") as pdf:
                        if pdf.needs_pass or len(pdf) > MAX_PAGES:
                            raise ValueError(f"{doc['name']}: el PDF está protegido o supera las {MAX_PAGES} páginas.")
                    result = analyze_document_bytes(doc["content"], context, corpus_info.get("total_processes", 0), doc["name"], taxonomy_snapshot=taxonomy)
                    if not result.document_text.strip():
                        raise ValueError(f"{doc['name']}: no se pudo extraer texto. Se requiere una versión con texto u OCR disponible.")
                    analysis = {
                        "items": [asdict(item) for item in result.review_items],
                        "clauses": [asdict(clause) for clause in result.clauses],
                        "signals": [asdict(signal) for signal in result.signals],
                        "document_text": result.document_text,
                        "page_count": len(result.pages),
                        "page_statuses": [{"page": p.page_number, "status": p.status.value} for p in result.pages],
                        "signal_count": len(result.signals), "clause_count": len(result.clauses),
                        "excluded_clauses": sum(c.exclude_from_detection for c in result.clauses),
                        "validation_messages": result.validation_messages,
                        "analysis_key": key, "analyzed_at": utc_now(),
                        "provenance": result.provenance,
                    }
                    _attach_evidence_coordinates(analysis, doc["content"])
                    self.store.cache_put(key, analysis)
                metadata = extract_pliego_metadata(doc["name"], analysis["document_text"], self.root, doc["sha256"])
                analysis = {k: v for k, v in analysis.items() if k != "document_text"}
                documents.append({**info, "metadata": metadata, "analysis": analysis, "cache_hit": cache_hit})
                if any(p["status"] in {"requires_ocr", "ocr_failed"} for p in analysis["page_statuses"]):
                    messages.append(f"{doc['name']}: algunas páginas no pudieron leerse por completo; la revisión es parcial.")
            items, changes = consolidate_case(documents)
            result = {
                "documents": documents, "items": items, "version_changes": changes,
                "summary": _deterministic_summary(items, documents),
                "messages": messages + corpus_info.get("messages", []),
                "corpus": corpus_info,
                "provenance": {"engine_version": ENGINE_VERSION, "taxonomy_sha256": taxonomy.source_sha256,
                               "rule_version": str(taxonomy.metadata.get("version") or "No disponible"),
                               "taxonomy_archived": True, "service_version": SERVICE_VERSION, "finished_at": utc_now()},
                "taxonomy_context": {p.id: p.to_dict() for p in taxonomy.patterns},
                "semantic_review": {"version": SEMANTIC_VERSION, "status": "pending" if self.assisted else "disabled",
                                    "decisions": [], "coverage": None},
                "assistance": {"status": "pending" if self.assisted else "disabled", "calls": []},
            }
            # Rules and evidence are committed before optional language generation.
            self.store.update_case(case_id, "ready", result)
            if self.assisted:
                try:
                    self._analyze_semantics(case_id, result, taxonomy, context)
                except Exception:
                    LOGGER.exception("Semantic stage failed; deterministic result retained")
                    result["semantic_review"]["status"] = "unavailable"
                    result["messages"].append("El análisis contextual adicional no se completó; se conserva la lectura basada en reglas.")
                try:
                    self._narrate(case_id, result)
                except Exception:
                    LOGGER.exception("Optional narration did not complete; deterministic review retained")
                    result["assistance"]["status"] = "unavailable"
                    self.store.update_case(case_id, "ready", result)
        except Exception as exc:
            LOGGER.exception("Review failed for case %s", case_id)
            message = str(exc) if isinstance(exc, (ValueError, TaxonomyUnavailableError)) else "No se pudo completar la revisión. Los documentos se conservaron para reintentar."
            self.store.update_case(case_id, "failed", error=message)
        finally:
            with self.lock:
                self.pending.discard(case_id)

    def _narrate(self, case_id: str, result: dict):
        from .llm_reviewer import PROMPT_VERSION, _llm_available, _model, _provider_name, explain_priority_with_llm, generate_document_brief
        if not _llm_available():
            result["assistance"]["status"] = "not_configured"
            self.store.update_case(case_id, "ready", result)
            return
        limit = _llm_call_limit() - len(result["assistance"]["calls"])
        if limit <= 0:
            result["assistance"]["status"] = _assistance_status(result)
            self.store.update_case(case_id, "ready", result)
            return
        if not result["items"]:
            result["assistance"]["status"] = _assistance_status(result)
            self.store.update_case(case_id, "ready", result)
            return
        result["assistance"]["status"] = "running"
        self.store.update_case(case_id, "ready", result)
        taxonomy_context = result.get("taxonomy_context", {})
        rows = [_llm_row(item, taxonomy_context) for item in result["items"][:3]]
        actions = [("summary", lambda: generate_document_brief("", rows), None)]
        for item in result["items"][:limit - 1]:
            actions.append(("explanation", lambda item=item: explain_priority_with_llm(_llm_row(item, taxonomy_context)), item))
        for purpose, callback, item in actions[:limit]:
            cache_key = fingerprint(["llm", PROMPT_VERSION, ENGINE_VERSION, result["provenance"]["taxonomy_sha256"], _provider_name(), _model(),
                                     os.getenv("OPENAI_BASE_URL", ""), os.getenv("OLLAMA_BASE_URL", ""),
                                     os.getenv("OPENAI_API_VERSION", ""), rows if item is None else _llm_row(item, taxonomy_context)])
            payload = self.store.cache_get(cache_key)
            cached = payload is not None
            if payload is None:
                try:
                    payload = callback()
                except Exception:
                    LOGGER.exception("Optional narration failed")
                    payload = {"llm_available": False, "llm_error": "La explicación adicional no está disponible."}
                # Persist failures as well: navigation/reopening must never retry billing.
                self.store.cache_put(cache_key, payload)
            record = {"purpose": purpose, "item_id": item["id"] if item else None, "cached": cached,
                      "status": "completed" if payload.get("llm_available") else "unavailable",
                      **payload.get("provenance", {})}
            result["assistance"]["calls"].append(record)
            if payload.get("llm_available"):
                if item:
                    item["assisted_explanation"] = payload["plain_language_explanation"]
                else:
                    result["assisted_summary"] = payload["document_summary"]
        result["assistance"]["status"] = _assistance_status(result)
        self.store.update_case(case_id, "ready", result)

    def _analyze_semantics(self, case_id: str, result: dict, taxonomy: TaxonomyLoadResult, corpus_context: dict):
        from .llm_reviewer import _llm_available, _model, _provider_name, analyze_clauses_with_llm
        semantic = result["semantic_review"]
        if os.getenv("INTEGRITY_SEMANTIC_ENABLED", "true").lower() != "true" or _llm_call_limit() == 0:
            semantic["status"] = "disabled"
            return
        if not _llm_available():
            semantic["status"] = "not_configured"
            return
        selection = select_semantic_context(result["documents"], taxonomy)
        semantic["coverage"] = selection.coverage
        if not selection.clauses or not selection.patterns:
            semantic["status"] = "no_eligible_context"
            return
        result["assistance"]["status"] = "running"
        semantic["status"] = "running"
        self.store.update_case(case_id, "ready", result)
        cache_key = fingerprint([SEMANTIC_VERSION, taxonomy.source_sha256, _provider_name(), _model(),
                                 os.getenv("OPENAI_BASE_URL", ""), os.getenv("OLLAMA_BASE_URL", ""),
                                 os.getenv("OPENAI_API_VERSION", ""), selection.payload])
        payload = self.store.cache_get(cache_key)
        cached = payload is not None
        if payload is None:
            try:
                payload = analyze_clauses_with_llm(selection.payload)
            except Exception:
                LOGGER.exception("Semantic request unavailable")
                payload = {"llm_available": False, "candidates": []}
            self.store.cache_put(cache_key, payload)
        result["assistance"]["calls"].append({**payload.get("provenance", {}),
            "purpose": "semantic_analysis", "item_id": None, "cached": cached,
            "status": "completed" if payload.get("llm_available") else "unavailable",
            "semantic_version": SEMANTIC_VERSION})
        if not payload.get("llm_available"):
            semantic["status"] = "unavailable"
            result["messages"].append("El análisis contextual adicional no está disponible; se conserva la lectura basada en reglas.")
            return
        existing = [Signal(**raw) for doc in result["documents"] for raw in doc["analysis"].get("signals", [])]
        signals, semantic["decisions"] = validate_semantic_proposals(payload, selection, existing)
        semantic["accepted_count"] = sum(d["status"] == "accepted" for d in semantic["decisions"])
        semantic["rejected_count"] = sum(d["status"] == "rejected" for d in semantic["decisions"])
        # Prepare all results before replacing the baseline, so a failure is atomic.
        updated_documents = []
        for doc in result["documents"]:
            clauses = [Clause(**raw) for raw in doc["analysis"].get("clauses", [])]
            clause_ids = {c.clause_id for c in clauses}
            added = [s for s in signals if s.clause_id in clause_ids]
            if not added:
                updated_documents.append(doc)
                continue
            base_signals = [Signal(**raw) for raw in doc["analysis"]["signals"]]
            candidates = build_finding_candidates(base_signals, clauses, corpus_context, taxonomy.patterns)
            semantic_candidates = build_finding_candidates(added, clauses, {}, taxonomy.patterns)
            _, items = finalize_candidates(candidates + semantic_candidates, clauses, clauses[0].document_id)
            analysis = {**doc["analysis"], "items": [asdict(item) for item in items],
                        "semantic_signals": [asdict(signal) for signal in added],
                        "semantic_signal_count": len(added)}
            original = self.store.document(case_id, doc["id"])
            _attach_evidence_coordinates(analysis, original["content"])
            updated_documents.append({**doc, "analysis": analysis})
        items, changes = consolidate_case(updated_documents)
        for decision in semantic["decisions"]:
            if decision["status"] == "accepted":
                visible = next((item for item in items if item["pattern_id"] == decision["pattern_id"]
                                and any(ev.get("clause_id") == decision["clause_id"] for ev in item["evidence"])), None)
                decision["review_item_id"] = visible["id"] if visible else None
                decision["integration_status"] = "visible" if visible else "filtered_by_domain_rules"
        semantic.update(status="completed", visible_semantic_item_count=sum(
            "análisis semántico asistido" in item["sources"] for item in items))
        result.update(documents=updated_documents, items=items, version_changes=changes,
                      summary=_deterministic_summary(items, updated_documents))
        self.store.update_case(case_id, "ready", result)

    def _corpus_context(self, excluded_hashes: set[str], taxonomy_snapshot: TaxonomyLoadResult | None = None) -> tuple[dict, dict]:
        from .corpus_loader import build_corpus_reference_context, load_corpus_documents
        try:
            taxonomy = taxonomy_snapshot if taxonomy_snapshot is not None else load_taxonomy()
            documents, issues = load_corpus_documents()
            excluded_processes = {d.process_id for d in documents if d.sha256 in excluded_hashes}
            documents = [d for d in documents if d.process_id not in excluded_processes]
            total = len({d.process_id for d in documents})
            snapshot = fingerprint([ENGINE_VERSION, taxonomy.source_sha256, sorted((d.process_id, d.tipo_documento, d.sha256) for d in documents)])
            context = self.store.cache_get("corpus-" + snapshot)
            if context is None:
                context = build_corpus_reference_context(documents, taxonomy)
                self.store.cache_put("corpus-" + snapshot, context)
            return context, {"snapshot": snapshot, "total_processes": total, "excluded_self_processes": len(excluded_processes),
                             "scope": "Corpus disponible; no se garantiza homogeneidad entre procedimientos.",
                             "messages": ["El corpus no está disponible o presenta inconsistencias; se mantiene la revisión documental."] if issues or not documents else []}
        except Exception:
            LOGGER.exception("Optional corpus comparison unavailable")
            return {}, {"snapshot": "unavailable", "total_processes": 0, "messages": ["Comparación documental no disponible en este entorno."]}


def _llm_call_limit() -> int:
    try:
        return max(0, min(3, int(os.getenv("INTEGRITY_LLM_MAX_CALLS", "2"))))
    except ValueError:
        return 0


def _assistance_status(result: dict) -> str:
    calls = result["assistance"]["calls"]
    if not calls:
        return "disabled"
    return "completed" if any(call["status"] == "completed" for call in calls) else "unavailable"


def _attach_evidence_coordinates(analysis: dict, content: bytes):
    with fitz.open(stream=content, filetype="pdf") as pdf:
        for item in analysis["items"]:
            for ev in item["evidence_items"]:
                page = pdf[int(ev["page"]) - 1]
                exact = " ".join(ev["text"].replace("...", " ").split())
                rects = page.search_for(exact) if exact else []
                precision = "excerpt" if rects else "matched_term"
                if not rects and len(exact) > 240:
                    rects = page.search_for(exact[:240])
                    if rects:
                        precision = "excerpt_prefix"
                if not rects and ev.get("matched_text"):
                    rects = page.search_for(ev["matched_text"])
                ev["rects"] = [[r.x0 / page.rect.width, r.y0 / page.rect.height, r.x1 / page.rect.width, r.y1 / page.rect.height] for r in rects[:12]]
                ev["location_precision"] = precision if rects else "unlocated"


def _llm_row(item: dict, taxonomy_context: dict | None = None) -> dict:
    return {"pattern_id": item["pattern_id"], "pattern_name": item["title"], "patrón detectado": item["title"],
            "competition_dimension": item["dimension"], "fragmento textual": item["evidence"][0]["text"],
            "página": item["evidence"][0]["page"], "mitigating_factors": item["mitigants"],
            "review_priority": item["priority"], "por qué se sugiere revisar": item["explanation"],
            "frecuencia en corpus": item["historical_context"].get("frequency_label", "No disponible"),
            "taxonomy_reference": (taxonomy_context or {}).get(item["pattern_id"])}


def _deterministic_summary(items: list[dict], documents: list[dict]) -> str:
    if not items:
        return "La lectura no identificó aspectos priorizados con las reglas disponibles. Esto no acredita completitud ni sustituye el cotejo del expediente."
    themes = list(dict.fromkeys(item["dimension_label"] for item in items))[:3]
    text = "La revisión se concentra en " + ", ".join(themes).lower() + ". Conviene contrastar los requisitos con su justificación y las alternativas admitidas."
    if any(item["mitigants"] for item in items):
        text += " Se identificaron factores que pueden atenuar algunas observaciones; su aplicación efectiva requiere revisión humana."
    return text
