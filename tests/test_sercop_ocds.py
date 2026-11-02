import hashlib
import json
import sqlite3
import csv
import io
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from src.analyzer import sercop_ocds as source, storage_schema as schema
from src.analyzer.review_store import ReviewStore
from src.manage_storage import migrate_sqlite
from test_workbench import pdf, wait_for_case
from test_workbench_api import client

OCID = "ocds-5wno2w-SIE-HCAM-2026-023-54651"


def package():
    return {"publishedDate": "2026-07-06T11:25:25-05:00", "license": "https://creativecommons.org/licenses/by/3.0/ec/",
            "releases": [{"ocid": OCID, "id": "compiled-test", "date": "2026-07-06T11:25:25-05:00",
                "buyer": {"name": "Comprador presupuestario"},
                "tender": {"id": "SIE-HCAM-2026-023", "description": "Adquisición de medicamentos para uso hospitalario",
                    "procuringEntity": {"name": "Hospital de prueba"}, "procurementMethodDetails": "Subasta Inversa Electrónica",
                    "items": [{"unit": {"value": {"amount": 123456, "currency": "USD"}}}],
                    "tenderPeriod": {"startDate": "2026-03-31T19:00:00-05:00"}}}]}


def mock_package(monkeypatch, data=None):
    data = data or package()
    raw = json.dumps(data, ensure_ascii=False).encode()
    calls = []
    def read(route, params):
        calls.append((route, params))
        return data, raw, source.BASE_URL + route + "?ocid=" + OCID
    monkeypatch.setattr(source, "_read_json", read)
    return calls


def test_filters_and_pagination_forwarded(monkeypatch):
    calls = mock_package(monkeypatch, {"total": 1, "page": "2", "pages": 2,
        "data": [{"ocid": OCID, "buyer": "Hospital", "title": None, "description": None}]})
    result = source.search_processes(2026, "medicamentos", "hospital", "proveedor", 2)
    assert calls == [("search_ocds", {"year": 2026, "search": "medicamentos", "page": 2, "buyer": "hospital", "supplier": "proveedor"})]
    assert result["results"][0]["code"] == OCID
    assert result["results"][0]["buyer"] == "Hospital"


def page_data(rows, page=1, total=30):
    return {"total": total, "page": page, "pages": 3, "data": [
        {"ocid": f"ocds-5wno2w-test-{i}", "buyer": buyer, "internal_type": procedure}
        for i, (buyer, procedure) in enumerate(rows)]}


def test_procedure_is_page_local_and_normalized_without_record_calls(monkeypatch):
    calls = mock_package(monkeypatch, page_data([("Comprador A", "Subasta Inversa Electrónica"), ("Comprador B", "Licitación"), ("Comprador C", None)]))
    result = source.search_processes(2026, "equipos", buyer="Comprador", procedure="electronica")
    assert len(calls) == 1 and "procedure" not in calls[0][1]
    assert len(result["results"]) == 1
    assert result["total"] == 30 and result["pages"] == 3
    assert result["page_count_before_filters"] == 3
    assert result["missing_procedure_count"] == 1
    assert result["local_filters"] == ["procedure"]


def test_entity_filter_uses_procuring_entity_not_buyer(monkeypatch):
    calls = mock_package(monkeypatch, page_data([("Ministerio", "Licitación"), ("Hospital Norte", "Licitación")]))
    def detail(ocid):
        return {"metadata": {"entidad": "Hospital Norte" if ocid.endswith("-0") else "Municipio"}}
    monkeypatch.setattr(source, "fetch_process", detail)
    result = source.search_processes(2026, "equipos", procuring_entity="hospital norte", procedure="licitacion")
    row, = result["results"]
    assert row["buyer"] == "Ministerio" and row["procuring_entity"] == "Hospital Norte"
    assert "procuring_entity" not in calls[0][1] and "procedure" not in calls[0][1]
    assert result["unverified_entity_count"] == 0


def test_missing_or_unreadable_entity_not_reported_as_verified_nonmatch(monkeypatch):
    mock_package(monkeypatch, page_data([("Hospital", "Licitación"), ("Hospital", "Licitación")]))
    def detail(ocid):
        if ocid.endswith("-0"):
            return {"metadata": {}}
        raise source.SercopUnavailable("Fuente no disponible")
    monkeypatch.setattr(source, "fetch_process", detail)
    result = source.search_processes(2026, "equipos", procuring_entity="hospital")
    assert result["results"] == [] and result["unverified_entity_count"] == 2
    assert result["total"] == 30 and result["pages"] == 3


def test_entity_lookup_is_bounded_to_ten_records(monkeypatch):
    mock_package(monkeypatch, page_data([("Comprador", "Licitación")] * 14))
    calls = []
    def detail(ocid):
        calls.append(ocid)
        return {"metadata": {"entidad": "Hospital"}}
    monkeypatch.setattr(source, "fetch_process", detail)
    result = source.search_processes(2026, "equipos", procuring_entity="hospital")
    assert len(calls) == 10 and len(result["results"]) == 10
    assert result["unverified_entity_count"] == 4


def test_no_local_filter_does_not_request_records(monkeypatch):
    mock_package(monkeypatch, page_data([("Comprador", "Licitación")]))
    def unexpected(*args): raise AssertionError("No implicit record lookups")
    monkeypatch.setattr(source, "fetch_process", unexpected)
    result = source.search_processes(2026, "equipos")
    assert len(result["results"]) == 1 and not result["local_filters"]


def test_verification_deadline_reports_unknown_instead_of_absence(monkeypatch):
    mock_package(monkeypatch, page_data([("Comprador", "Licitación")]))
    monkeypatch.setattr(source, "fetch_process", lambda ocid: {"metadata": {"entidad": "Hospital"}})
    def elapsed(*args, **kwargs): raise source.FutureTimeout()
    monkeypatch.setattr(source, "as_completed", elapsed)
    result = source.search_processes(2026, "equipos", procuring_entity="hospital")
    assert result["results"] == []
    assert result["unverified_entity_count"] == 1
    assert result["total"] == 30


@pytest.mark.parametrize("kwargs", [{"procuring_entity": "ab"}, {"procedure": "ab"}])
def test_invalid_local_filters_do_not_call_source(monkeypatch, kwargs):
    def unexpected(*args): raise AssertionError("No network call")
    monkeypatch.setattr(source, "_read_json", unexpected)
    with pytest.raises(ValueError): source.search_processes(2026, "equipos", **kwargs)


def test_local_filters_are_forwarded_by_api(client, monkeypatch):
    mock_package(monkeypatch, page_data([("Comprador", "Subasta Inversa Electrónica")]))
    monkeypatch.setattr(source, "fetch_process", lambda ocid: {"metadata": {"entidad": "Hospital"}})
    response = client.get("/api/sources/sercop/search", params={"year": 2026, "search": "equipo", "procuring_entity": "hospital", "procedure": "inversa"})
    assert response.status_code == 200
    assert len(response.json()["results"]) == 1
    assert response.json()["total"] == 30


@pytest.mark.parametrize("kwargs", [{"year": 2014}, {"year": 9999}, {"search": "ab"}, {"buyer": "ab"}, {"supplier": "ab"}, {"page": 0}, {"page": 10001}])
def test_invalid_filters_do_not_call_network(monkeypatch, kwargs):
    def unexpected(*args):
        raise AssertionError("Unexpected network call")
    monkeypatch.setattr(source, "_read_json", unexpected)
    with pytest.raises(ValueError):
        source.search_processes(**({"year": 2026, "search": "medicamentos"} | kwargs))


@pytest.mark.parametrize("ocid", ["https://127.0.0.1/", "file:///etc/passwd", "ocds-other-test", "ocds-5wno2w-abc?url=private"])
def test_arbitrary_urls_rejected(ocid):
    with pytest.raises(ValueError):
        source.fetch_process(ocid)


def test_record_has_literal_provenance_without_inventing_budget_or_dates(monkeypatch):
    calls = mock_package(monkeypatch)
    snapshot = source.fetch_process(OCID)
    assert calls == [("record", {"ocid": OCID})]
    assert snapshot["metadata"]["entidad"] == "Hospital de prueba"
    assert snapshot["buyer"] == "Comprador presupuestario"
    assert "presupuesto" not in snapshot["metadata"]
    assert "fecha" not in snapshot["metadata"]
    assert snapshot["tender_period"]["endDate"] == ""
    assert snapshot["document_reference_count"] == 0
    assert snapshot["field_sources"]["objeto"] == "/releases/0/tender/description"
    assert hashlib.sha256(snapshot["raw_json"].encode()).hexdigest() == snapshot["sha256"]
    assert "raw_json" not in source.public_snapshot(snapshot)


def test_distinct_consultations_do_not_depend_on_clock_precision(monkeypatch):
    mock_package(monkeypatch)
    class FrozenClock:
        @staticmethod
        def now(tz):
            return datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(source, "datetime", FrozenClock)
    first, second = source.fetch_process(OCID), source.fetch_process(OCID)
    assert first["retrieved_at"] == second["retrieved_at"]
    assert first["sha256"] == second["sha256"]
    assert first["snapshot_id"] != second["snapshot_id"]


def test_compiled_record_envelope_and_planning_budget(monkeypatch):
    data = package()
    release = data.pop("releases")[0]
    release["planning"] = {"budget": {"amount": {"amount": 1000, "currency": "USD"}}}
    data["records"] = [{"ocid": OCID, "compiledRelease": release}]
    mock_package(monkeypatch, data)
    snapshot = source.fetch_process(OCID)
    assert snapshot["metadata"]["presupuesto"] == "USD 1,000.00"
    assert snapshot["field_sources"]["presupuesto"] == "/records/0/compiledRelease/planning/budget/amount"


def test_multiple_partial_releases_not_combined_arbitrarily(monkeypatch):
    data = package()
    data["releases"].append({"ocid": OCID, "id": "new", "tender": {}})
    mock_package(monkeypatch, data)
    with pytest.raises(source.SercopUnavailable, match="versión única"):
        source.fetch_process(OCID)


def test_no_buyer_to_entity_substitution(monkeypatch):
    data = package()
    del data["releases"][0]["tender"]["procuringEntity"]
    mock_package(monkeypatch, data)
    snapshot = source.fetch_process(OCID)
    assert "entidad" not in snapshot["metadata"]
    assert snapshot["buyer"] == "Comprador presupuestario"


@pytest.mark.parametrize("payload", [b'<html>Unavailable</html>', b'{"x":NaN}', b'[]'])
def test_invalid_response_and_html_are_friendly(monkeypatch, payload):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit): return payload
    class Opener:
        def open(self, request, timeout): return Response()
    monkeypatch.setattr(source.urllib.request, "build_opener", lambda *args: Opener())
    with pytest.raises(source.SercopUnavailable):
        source._read_json("record", {"ocid": OCID})


def test_timeout_is_friendly(monkeypatch):
    class Opener:
        def open(self, *args, **kwargs): raise TimeoutError("upstream")
    monkeypatch.setattr(source.urllib.request, "build_opener", lambda *args: Opener())
    with pytest.raises(source.SercopUnavailable, match="continúe cargando"):
        source.fetch_process(OCID)


def test_source_import_and_pdf_link_require_confirmation(client, monkeypatch):
    mock_package(monkeypatch)
    imported = client.post("/api/sources/sercop/record", json={"ocid": OCID})
    assert imported.status_code == 200
    snapshot = imported.json()
    assert "raw_json" not in snapshot
    data = {"manifest": '[{"role":"pliego"}]', "request_key": "linked", "source_snapshot_id": snapshot["snapshot_id"]}
    response = client.post("/api/cases", data=data, files=[("files", ("pliego.pdf", pdf(), "application/pdf"))])
    assert response.status_code == 400
    data["source_confirmed"] = "true"
    response = client.post("/api/cases", data=data, files=[("files", ("pliego.pdf", pdf(), "application/pdf"))])
    assert response.status_code == 202
    case_id = response.json()["id"]
    case = wait_for_case(client.app.state.service, case_id)
    assert case["status"] == "ready"
    assert case["result"]["documents"][0]["metadata"]["entidad"] == "Hospital de prueba"
    assert case["result"]["documents"][0]["metadata_from_document"]
    public = client.get(f"/api/cases/{case_id}").json()
    assert "raw_json" not in public["source"]
    audit = client.get(f"/api/cases/{case_id}/export?format=json").json()
    assert audit["source"]["raw_json"] == case["source"]["raw_json"]
    assert OCID in client.get(f"/api/cases/{case_id}/export?format=html").text
    rows = list(csv.DictReader(io.StringIO(client.get(f"/api/cases/{case_id}/export?format=csv").text.lstrip("\ufeff"))))
    assert rows and all(row["ocid"] == OCID and row["sha256_registro"] == snapshot["sha256"] for row in rows)
    monkeypatch.setattr(source, "fetch_process", lambda *args: (_ for _ in ()).throw(AssertionError("No refetch")))
    assert client.get(f"/api/cases/{case_id}").status_code == 200


def test_idempotency_includes_source_and_snapshot_is_not_overwritten(tmp_path, monkeypatch):
    mock_package(monkeypatch)
    first, second = source.fetch_process(OCID), source.fetch_process(OCID)
    store = ReviewStore(tmp_path / "store.sqlite3")
    try:
        store.save_source_snapshot(first)
        store.save_source_snapshot(second)
        content = pdf()
        documents = [{"id": "d1", "name": "p.pdf", "role": "pliego", "version": "1", "sha256": hashlib.sha256(content).hexdigest(), "content": content}]
        assert store.create_case("c1", "k1", "Prueba", documents, first["snapshot_id"]) == "c1"
        assert store.create_case("c2", "k1", "Prueba", documents, first["snapshot_id"]) == "c1"
        from src.analyzer.review_store import StorageConflict
        with pytest.raises(StorageConflict):
            store.create_case("c3", "k1", "Prueba", documents, second["snapshot_id"])
        assert store.get_case("c1")["source"] == first
    finally: store.close()


def test_search_api_forwards_documented_filters(client, monkeypatch):
    calls = mock_package(monkeypatch, {"total": 0, "page": 1, "pages": 0, "data": []})
    response = client.get("/api/sources/sercop/search", params={"year": 2026, "search": "equipo", "buyer": "hospital", "supplier": "proveedor"})
    assert response.status_code == 200 and not response.json()["results"]
    assert calls[0][1]["supplier"] == "proveedor"


def test_source_outage_does_not_affect_manual_upload(client, monkeypatch):
    def fail(*args): raise source.SercopUnavailable("Fuente no disponible")
    monkeypatch.setattr(source, "fetch_process", fail)
    assert client.post("/api/sources/sercop/record", json={"ocid": OCID}).status_code == 503
    response = client.post("/api/cases", data={"manifest": '[{"role":"pliego"}]', "request_key": "manual"}, files=[("files", ("pliego.pdf", pdf(), "application/pdf"))])
    assert response.status_code == 202


def test_version_one_upgrade_is_additive_and_idempotent(tmp_path):
    path = tmp_path / "v1.sqlite3"
    store = ReviewStore(path)
    store.close()
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE case_sources")
        db.execute("DROP TABLE source_snapshots")
        db.execute("DELETE FROM schema_migrations WHERE version=2")
    upgraded = ReviewStore(path)
    with upgraded.connection() as db:
        assert set(db.scalars(select(schema.schema_migrations.c.version))) == {1, 2}
    upgraded.close()
    ReviewStore(path).close()


def test_snapshot_and_binding_survive_offline_migration(tmp_path, monkeypatch):
    mock_package(monkeypatch)
    snapshot = source.fetch_process(OCID)
    original = ReviewStore(tmp_path / "original.sqlite3")
    original.save_source_snapshot(snapshot)
    content = pdf()
    original.create_case("linked-case", "linked-request", "Prueba", [{"id": "pdf-1", "name": "pliego.pdf", "role": "pliego", "version": "1", "sha256": hashlib.sha256(content).hexdigest(), "content": content}], source_snapshot_id=snapshot["snapshot_id"])
    original.close()
    target = ReviewStore(tmp_path / "target.sqlite3")
    try:
        report = migrate_sqlite(tmp_path / "original.sqlite3", target)
        assert report["applied"]
        assert target.get_case("linked-case")["source"] == snapshot
    finally: target.close()
