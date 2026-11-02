"""Read-only SERCOP adapter. Metadata is context, never PDF evidence."""
from __future__ import annotations

import hashlib
import json
import re
import threading
import uuid
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


BASE_URL = "https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/api/"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
_SLOTS = threading.BoundedSemaphore(2)


class SercopUnavailable(ValueError):
    """A public source could not be read safely; existing reviews are unaffected."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_ocid(value: str) -> str:
    value = value.strip()
    if not re.fullmatch(r"ocds-5wno2w-[A-Za-z0-9._-]{3,180}", value):
        raise ValueError("Ingrese un OCID de SERCOP válido, comenzando por ocds-5wno2w-.")
    return value


def _text(value, limit=2000):
    return value.strip()[:limit] if isinstance(value, str) else ""


def _object(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    return value if isinstance(value, list) else []


def _integer(value):
    if isinstance(value, bool) or not re.fullmatch(r"\d{1,9}", str(value)):
        raise SercopUnavailable("La fuente devolvió una paginación no reconocida.")
    return int(value)


def _invalid_constant(value):
    raise ValueError("Non-finite JSON value")


def _read_json(route: str, params: dict) -> tuple[dict, bytes, str]:
    # No caller-controlled host/path and no redirects or document downloads.
    if route not in {"search_ocds", "record"}:
        raise ValueError("Consulta no permitida.")
    url = BASE_URL + route + "?" + urllib.parse.urlencode(params)
    if not _SLOTS.acquire(blocking=False):
        raise SercopUnavailable("Hay consultas a SERCOP en curso. Espere unos segundos e intente nuevamente.")
    try:
        opener = urllib.request.build_opener(_NoRedirect())
        request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "IntegrityTool-PoC/1.0"})
        with opener.open(request, timeout=12) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise SercopUnavailable("La respuesta de SERCOP supera el tamaño admitido para esta consulta.")
        data = json.loads(raw.decode("utf-8-sig"), parse_constant=_invalid_constant)
        if not isinstance(data, dict):
            raise ValueError("Expected an object")
        return data, raw, url
    except SercopUnavailable:
        raise
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        raise SercopUnavailable("No se pudo consultar SERCOP. Intente nuevamente o continúe cargando sus PDF.") from exc
    finally:
        _SLOTS.release()


def search_processes(year: int, search: str, buyer: str = "", supplier: str = "", page: int = 1) -> dict:
    if not 2015 <= year <= datetime.now(timezone.utc).year or not 1 <= page <= 10000:
        raise ValueError("Verifique el año y la página de la búsqueda.")
    params = {"year": year, "search": search.strip(), "page": page}
    for field, value, label in [("search", search, "La búsqueda"), ("buyer", buyer, "La entidad"), ("supplier", supplier, "El proveedor")]:
        value = value.strip()
        if (field == "search" or value) and not 3 <= len(value) <= 200:
            raise ValueError(f"{label} debe contener entre 3 y 200 caracteres.")
        if value:
            params[field] = value
    data, _, _ = _read_json("search_ocds", params)
    if not isinstance(data.get("data"), list):
        raise SercopUnavailable("La fuente devolvió una lista de procesos no reconocida.")
    total, pages = _integer(data.get("total")), _integer(data.get("pages"))
    if _integer(data.get("page")) != page:
        raise SercopUnavailable("SERCOP devolvió una página distinta de la solicitada. Repita la búsqueda.")
    results = []
    for row in data["data"]:
        row = _object(row)
        try:
            ocid = validate_ocid(_text(row.get("ocid")))
        except ValueError:
            continue
        results.append({"ocid": ocid, "code": _text(row.get("title"), 240) or ocid,
                        "buyer": _text(row.get("buyerName") or row.get("buyer")),
                        "description": _text(row.get("description"), 5000),
                        "procedure": _text(row.get("internal_type")), "date": _text(row.get("date"), 60)})
    if data["data"] and not results:
        raise SercopUnavailable("La fuente devolvió procesos sin identificadores verificables.")
    return {"total": total, "page": page, "pages": pages, "results": results,
            "omitted_count": len(data["data"]) - len(results)}


def _release(package: dict, ocid: str) -> tuple[dict, str]:
    compiled = [(record["compiledRelease"], f"/records/{i}/compiledRelease") for i, record in enumerate(_list(package.get("records")))
                if isinstance(record, dict) and record.get("ocid") == ocid and isinstance(record.get("compiledRelease"), dict)]
    if len(compiled) == 1:
        release, pointer = compiled[0]
    else:
        releases = [(r, f"/releases/{i}") for i, r in enumerate(_list(package.get("releases"))) if isinstance(r, dict) and r.get("ocid") == ocid]
        releases += [(r, f"/records/{i}/releases/{j}") for i, record in enumerate(_list(package.get("records")))
                     if isinstance(record, dict) and record.get("ocid") == ocid
                     for j, r in enumerate(_list(record.get("releases"))) if isinstance(r, dict) and r.get("ocid") == ocid]
        if len(compiled) > 1 or len(releases) != 1:
            raise SercopUnavailable("No se identificó una versión única del proceso. Consulte el registro oficial; no se combinaron entregas automáticamente.")
        release, pointer = releases[0]
    if release.get("ocid") != ocid:
        raise SercopUnavailable("El registro recibido no corresponde al OCID solicitado.")
    return release, pointer


def _money(value: dict) -> str:
    try:
        amount = Decimal(str(value.get("amount")))
        currency = value.get("currency")
        if not amount.is_finite() or amount <= 0 or amount.adjusted() > 16 or not re.fullmatch(r"[A-Z]{3}", str(currency)):
            return ""
        return f"{currency} {amount:,.2f}"
    except (InvalidOperation, ValueError):
        return ""


def fetch_process(ocid: str) -> dict:
    ocid = validate_ocid(ocid)
    package, raw, url = _read_json("record", {"ocid": ocid})
    release, pointer = _release(package, ocid)
    tender = _object(release.get("tender"))
    buyer = _object(release.get("buyer"))
    entity = _object(tender.get("procuringEntity"))
    budget = _object(_object(release.get("planning")).get("budget"))
    metadata, fields = {}, {}
    for key, value, path in [
        ("entidad", entity.get("name"), "/tender/procuringEntity/name"),
        ("objeto", tender.get("description"), "/tender/description"),
        ("tipo_procedimiento", tender.get("procurementMethodDetails"), "/tender/procurementMethodDetails"),
    ]:
        if _text(value, 20000):
            metadata[key], fields[key] = _text(value, 20000), pointer + path
    # Buyer and procuring entity are distinct roles. Never substitute silently.
    money = _money(_object(tender.get("value")))
    money_path = "/tender/value"
    if not money:
        money = _money(_object(budget.get("amount")))
        money_path = "/planning/budget/amount"
    if money:
        metadata["presupuesto"], fields["presupuesto"] = money, pointer + money_path
    containers = [tender, _object(release.get("planning"))]
    containers += [_object(obj) for key in ("awards", "contracts") for obj in _list(release.get(key))]
    containers += [_object(obj.get("implementation")) for obj in containers[:]]
    documents = [doc for container in containers for doc in _list(container.get("documents")) if isinstance(doc, dict)]
    sha = hashlib.sha256(raw).hexdigest()
    retrieved = datetime.now(timezone.utc).isoformat()
    snapshot_id = hashlib.sha256(f"{url}|{sha}|{retrieved}|{uuid.uuid4().hex}".encode()).hexdigest()
    return {"snapshot_id": snapshot_id, "provider": "sercop_ocds", "ocid": ocid,
            "source_url": url, "sha256": sha, "retrieved_at": retrieved,
            "published_at": _text(package.get("publishedDate"), 60), "release_id": _text(release.get("id"), 240),
            "release_date": _text(release.get("date"), 60), "release_pointer": pointer,
            "code": _text(tender.get("id"), 240) or ocid, "buyer": _text(buyer.get("name")),
            "metadata": metadata, "field_sources": fields,
            "tender_period": {key: _text(_object(tender.get("tenderPeriod")).get(key), 60) for key in ("startDate", "endDate")},
            "item_count": len(_list(tender.get("items"))), "document_reference_count": len(documents),
            "license": _text(package.get("license")), "raw_json": raw.decode("utf-8"),
            "limitation": "La ficha no acredita completitud del expediente. No se descargaron documentos ni se verificó automáticamente su correspondencia con los PDF."}


def public_snapshot(snapshot: dict) -> dict:
    return {key: value for key, value in snapshot.items() if key != "raw_json"}
