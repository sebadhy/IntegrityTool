"""Offline demo queries over a dated official SERCOP download, never PDF evidence."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import uuid

from .analyzer import sercop_ocds
from .sercop_suggestions import _normalize

YEAR = 2026
PAGE_SIZE = 10
RESOURCES = Path(__file__).resolve().parent / "resources"
MAX_DATABASE_BYTES = 300 * 1024 * 1024
_load_lock = threading.Lock()


@lru_cache(maxsize=1)
def _database():
    manifest = json.loads((RESOURCES / f"sercop_processes_{YEAR}.json").read_text(encoding="utf-8"))
    compressed = RESOURCES / f"sercop_processes_{YEAR}.sqlite3.gz"
    if manifest["version"] != 1 or manifest["year"] != YEAR or manifest["database_bytes"] > MAX_DATABASE_BYTES:
        raise ValueError("La versión o el tamaño del respaldo de procesos no es válido.")
    if hashlib.sha256(compressed.read_bytes()).hexdigest() != manifest["file_sha256"]:
        raise ValueError("El respaldo de procesos no coincide con su huella de integridad.")
    temporary = tempfile.TemporaryDirectory(prefix="integrity-sercop-")
    try:
        target = Path(temporary.name) / "processes.sqlite3"
        with gzip.open(compressed, "rb") as source, target.open("wb") as destination:
            total = 0
            while chunk := source.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_DATABASE_BYTES:
                    raise ValueError("El respaldo supera el tamaño admitido.")
                destination.write(chunk)
        if total != manifest["database_bytes"]:
            raise ValueError("El respaldo de procesos está incompleto.")
        target.chmod(0o400)
        return manifest, temporary, target
    except Exception:
        temporary.cleanup()
        raise


@contextmanager
def _connection():
    try:
        # One unpacked copy per API process, even with concurrent first requests.
        with _load_lock:
            manifest, temporary, path = _database()
        db = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, EOFError) as exc:
        raise sercop_ocds.SercopUnavailable("El respaldo local de procesos no está disponible. Puede continuar cargando sus PDF.") from exc
    try:
        db.row_factory = sqlite3.Row
        yield db, manifest
    finally:
        db.close()


def _like(value):
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _conditions(search, buyer, supplier):
    conditions, params = [], []
    for token in _normalize(search).split():
        conditions.append("p.search_key LIKE ? ESCAPE '\\'")
        params.append(_like(token))
    for token in _normalize(buyer).split():
        conditions.append("p.buyer_key LIKE ? ESCAPE '\\'")
        params.append(_like(token))
    if supplier.strip():
        supplier_conditions = ["s.ocid=p.ocid"]
        for token in _normalize(supplier).split():
            supplier_conditions.append("s.search_key LIKE ? ESCAPE '\\'")
            params.append(_like(token))
        conditions.append("EXISTS(SELECT 1 FROM suppliers s WHERE " + " AND ".join(supplier_conditions) + ")")
    return " AND ".join(conditions) or "1=1", params


def _validate(year, search, buyer, supplier, page):
    if year != YEAR:
        raise ValueError(f"El respaldo de demostración cubre únicamente {YEAR}.")
    if not 1 <= page <= 10000:
        raise ValueError("Verifique la página de búsqueda.")
    for value in (search, buyer, supplier):
        if len(value.strip()) > 200 or value.strip() and len(value.strip()) < 3:
            raise ValueError("Cada filtro debe contener al menos tres caracteres o quedar vacío.")


def _result(row):
    original = json.loads(row["raw_json"])
    return {"ocid": row["ocid"], "code": row["code"], "buyer": row["buyer"],
            "description": original["tender"].get("description", ""),
            "procedure": original["tender"].get("procurementMethodDetails", ""),
            "date": original["release"].get("date", "")}


def search_processes(year, search="", buyer="", supplier="", page=1, *, suggestions=False):
    _validate(year, search, buyer, supplier, page)
    condition, params = _conditions(search, buyer, supplier)
    with _connection() as (db, manifest):
        total = None if suggestions else db.execute("SELECT COUNT(*) FROM processes p WHERE " + condition, params).fetchone()[0]
        rows = db.execute("SELECT p.* FROM processes p WHERE " + condition + " ORDER BY p.code, p.ocid LIMIT ? OFFSET ?",
                          [*params, 8 if suggestions else PAGE_SIZE, 0 if suggestions else (page - 1) * PAGE_SIZE]).fetchall()
        return {"total": total, "page": page, "pages": (total + PAGE_SIZE - 1) // PAGE_SIZE if total is not None else 0,
                "results": [_result(row) for row in rows], "omitted_count": 0,
                "data_source": "snapshot", "published_at": manifest["published_at"], "source_url": manifest["source_url"]}


def fetch_process(ocid):
    ocid = sercop_ocds.validate_ocid(ocid)
    with _connection() as (db, manifest):
        row = db.execute("SELECT * FROM processes WHERE ocid=?", (ocid,)).fetchone()
        if row is None:
            raise ValueError("El proceso no figura en la descarga local de 2026. Puede cargar sus PDF directamente.")
        original = json.loads(row["raw_json"])
        release, tender = original["release"], original["tender"]
        metadata, paths = {}, {}
        for field, column in [("entidad", "procuringEntity_name"), ("objeto", "description"), ("tipo_procedimiento", "procurementMethodDetails")]:
            if tender.get(column, "").strip():
                metadata[field], paths[field] = tender[column], f"/tender/{column}"
        money = sercop_ocds._money({"amount": tender.get("value_amount"), "currency": tender.get("value_currency")})
        if money:
            metadata["presupuesto"], paths["presupuesto"] = money, "/tender/value_amount"
        raw = row["raw_json"]
        digest = hashlib.sha256(raw.encode()).hexdigest()
        retrieved = datetime.now(timezone.utc).isoformat()
        return {"snapshot_id": hashlib.sha256((digest + retrieved + uuid.uuid4().hex).encode()).hexdigest(),
                "provider": "sercop_bulk_csv", "ocid": ocid, "source_url": manifest["source_url"],
                "source_zip_sha256": manifest["source_zip_sha256"], "sha256": digest, "retrieved_at": retrieved,
                "published_at": manifest["published_at"], "release_id": release["id"], "release_date": release.get("date", ""),
                "release_pointer": "/release", "code": row["code"], "buyer": row["buyer"], "metadata": metadata,
                "field_sources": paths, "tender_period": {"startDate": tender.get("tenderPeriod_startDate", ""), "endDate": tender.get("tenderPeriod_endDate", "")},
                "item_count": 0, "document_reference_count": 0, "license": manifest["license"], "raw_json": raw,
                "limitation": "Ficha de demostración tomada de la descarga CSV oficial de 2026. El JSON exportado es un extracto estructurado de columnas, no una respuesta de la API. No incluye los PDF ni acredita completitud del expediente. No se actualiza en tiempo real."}
