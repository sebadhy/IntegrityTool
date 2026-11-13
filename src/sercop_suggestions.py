"""Verified catalog suggestions and bounded, read-only official process lookups."""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
import threading
import time
import unicodedata

from .analyzer import sercop_ocds

CATALOG_YEAR = 2026
RESOURCES = Path(__file__).resolve().parent / "resources"
MAX_OPTIONS = 8
CACHE_SECONDS = 60
MAX_CACHE_ENTRIES = 128
_cache = OrderedDict()
_lock = threading.Lock()
_query_slots = threading.BoundedSemaphore(1)


def _normalize(value):
    return " ".join("".join(c for c in unicodedata.normalize("NFKD", value.casefold())
                            if not unicodedata.combining(c)).split())


@lru_cache(maxsize=1)
def _catalog():
    manifest = json.loads((RESOURCES / f"sercop_catalog_{CATALOG_YEAR}.json").read_text(encoding="utf-8"))
    content = (RESOURCES / f"sercop_catalog_{CATALOG_YEAR}.json.gz").read_bytes()
    if hashlib.sha256(content).hexdigest() != manifest["catalog_sha256"]:
        raise ValueError("El catálogo no coincide con su registro de integridad.")
    with gzip.open(RESOURCES / f"sercop_catalog_{CATALOG_YEAR}.json.gz", "rb") as stream:
        raw = stream.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError("El catálogo supera el tamaño admitido.")
    data = json.loads(raw)
    if data["version"] != 1 or data["year"] != CATALOG_YEAR or manifest["year"] != CATALOG_YEAR:
        raise ValueError("La versión del catálogo no es compatible.")
    index = {}
    for field in ("buyer", "supplier"):
        entries = {}
        for item in data[field]:
            if not isinstance(item["id"], str) or not isinstance(item["name"], str) or not 1 <= len(item["name"]) <= 200:
                raise ValueError("El catálogo contiene una identidad no válida.")
            name = item["name"].strip()
            key = _normalize(name)
            entry = entries.setdefault(key, {"name": name, "ids": set(), "normalized": key})
            entry["ids"].add(item["id"])
        index[field] = sorted(entries.values(), key=lambda item: item["normalized"])
    return manifest, index


def suggestions(field: str, year: int, query: str, buyer: str = "", supplier: str = "", data_source: str = "api") -> dict:
    if field not in {"buyer", "supplier", "search"}:
        raise ValueError("El campo de sugerencias no es válido.")
    if not 2015 <= year <= datetime.now(timezone.utc).year:
        raise ValueError("Verifique el año de la búsqueda.")
    query = query.strip()
    if len(query) > 200:
        raise ValueError("La búsqueda admite hasta 200 caracteres.")
    if len(query) < 3:
        return {"options": [], "source": "", "message": "Escriba al menos tres caracteres."}
    if field == "search":
        if data_source == "snapshot":
            from .sercop_local import search_processes
            try:
                result = search_processes(year, query, buyer, supplier, suggestions=True)
                return {"options": [{"id": row["ocid"], "value": row["code"], "label": row["code"],
                                     "detail": row["description"] or row["buyer"]} for row in result["results"]],
                        "source": "snapshot", "published_at": result["published_at"],
                        "message": "" if result["results"] else "Sin coincidencias en la descarga local. Puede cambiar el texto o los filtros."}
            except sercop_ocds.SercopUnavailable as exc:
                return {"options": [], "source": "snapshot", "message": str(exc)}
        return _process_suggestions(year, query, buyer, supplier)
    if year != CATALOG_YEAR:
        return {"options": [], "source": "catalog", "catalog_year": CATALOG_YEAR,
                "message": f"El catálogo disponible es de {CATALOG_YEAR}. Para este año puede escribir libremente."}
    try:
        manifest, index = _catalog()
    except (OSError, ValueError, KeyError, TypeError, EOFError):
        return {"options": [], "source": "catalog", "message": "El catálogo no está disponible. Puede escribir libremente."}
    normalized = _normalize(query)
    terms = normalized.split()
    matched = [entry for entry in index[field] if all(term in entry["normalized"] for term in terms)
               or any(normalized in identifier.casefold() for identifier in entry["ids"])]
    matched.sort(key=lambda entry: (not entry["normalized"].startswith(normalized), entry["normalized"]))
    options = [{"id": hashlib.sha256(entry["normalized"].encode()).hexdigest()[:20],
                "value": entry["name"], "label": entry["name"], "detail": "",
                "published_id_count": len(entry["ids"])} for entry in matched[:MAX_OPTIONS]]
    return {"options": options, "source": "catalog", "catalog_year": CATALOG_YEAR,
            "published_at": manifest["published_at"], "source_url": manifest["source_url"],
            "message": "" if options else "Sin coincidencias en el catálogo. Puede escribir otro nombre."}


def _process_suggestions(year, query, buyer, supplier):
    for value in (buyer, supplier):
        if value.strip() and not 3 <= len(value.strip()) <= 200:
            return {"options": [], "source": "sercop_api", "message": "Complete los filtros opcionales con al menos tres caracteres."}
    # Preserve exact query text in the key: no assumptions about remote matching.
    key = (year, query, buyer.strip(), supplier.strip())
    with _lock:
        cached = _cache.get(key)
        if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
            _cache.move_to_end(key)
            return cached[1]
    if not _query_slots.acquire(blocking=False):
        return {"options": [], "source": "sercop_api", "message": "Hay una consulta en curso. Puede seguir escribiendo o buscar directamente."}
    try:
        result = sercop_ocds.search_processes(year, query, buyer, supplier)
        seen, options = set(), []
        for row in result["results"]:
            if row["ocid"] in seen:
                continue
            seen.add(row["ocid"])
            options.append({"id": row["ocid"], "value": row["code"], "label": row["code"],
                            "detail": row["description"] or row["buyer"]})
            if len(options) == MAX_OPTIONS:
                break
        response = {"options": options, "source": "sercop_api", "message": "" if options else "Sin sugerencias. Puede buscar el texto ingresado."}
        with _lock:
            _cache[key] = (time.monotonic(), response)
            _cache.move_to_end(key)
            while len(_cache) > MAX_CACHE_ENTRIES:
                _cache.popitem(last=False)
        return response
    except sercop_ocds.SercopUnavailable:
        return {"options": [], "source": "sercop_api", "message": "No se pudieron consultar las sugerencias de SERCOP. Puede buscar directamente."}
    finally:
        _query_slots.release()
