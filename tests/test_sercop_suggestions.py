import gzip
import hashlib
import json
import zipfile

import pytest

from src import sercop_suggestions as suggestions
from src.analyzer import sercop_ocds
from test_workbench_api import client


@pytest.fixture(autouse=True)
def clean_caches():
    loader = suggestions._catalog
    loader.cache_clear()
    suggestions._cache.clear()
    yield
    loader.cache_clear()
    suggestions._cache.clear()


def test_published_catalog_integrity_and_counts():
    manifest, index = suggestions._catalog()
    assert manifest["source_zip_sha256"] == "dcf8bf260cc0d2352c51ab8c801f4fb513395cef0ac3e6948e9821f8423ffa1f"
    assert manifest["counts"]["buyer"]["published_ids"] == 4549
    assert manifest["counts"]["supplier"]["published_ids"] == 12724
    for field in ("buyer", "supplier"):
        assert len({identifier for item in index[field] for identifier in item["ids"]}) == manifest["counts"][field]["published_ids"]


@pytest.mark.parametrize("field,query,expected", [("buyer", "SALUD PUBLICA", "SALUD"),
    ("supplier", "pfizer", "PFIZER"), ("buyer", "ministerio de salud", "SALUD")])
def test_names_are_suggested_without_external_requests(field, query, expected, monkeypatch):
    monkeypatch.setattr(sercop_ocds, "search_processes", lambda *args: pytest.fail("Catalog must be offline"))
    data = suggestions.suggestions(field, 2026, query)
    assert data["options"] and len(data["options"]) <= 8
    assert data["source"] == "catalog" and data["catalog_year"] == 2026
    assert all(expected in item["label"].upper() for item in data["options"])
    assert len({item["value"] for item in data["options"]}) == len(data["options"])


def test_catalog_accents_case_and_published_identifier():
    plain = suggestions.suggestions("buyer", 2026, "policia")
    accented = suggestions.suggestions("buyer", 2026, "POLICÍA")
    assert plain["options"] == accented["options"] and plain["options"]
    by_id = suggestions.suggestions("supplier", 2026, "1792569397001")
    assert "PFIZER" in by_id["options"][0]["value"]


@pytest.mark.parametrize("field", ["buyer", "supplier"])
def test_catalog_does_not_misrepresent_other_years(field):
    data = suggestions.suggestions(field, 2025, "hospital")
    assert not data["options"]
    assert "2026" in data["message"] and "libremente" in data["message"]


@pytest.mark.parametrize("query", ["", "a", "ab", "   "])
def test_short_queries_do_not_load_catalog_or_call_network(query, monkeypatch):
    monkeypatch.setattr(suggestions, "_catalog", lambda: pytest.fail("No catalog read"))
    monkeypatch.setattr(sercop_ocds, "search_processes", lambda *args: pytest.fail("No network"))
    for field in ("buyer", "supplier", "search"):
        assert not suggestions.suggestions(field, 2026, query)["options"]


@pytest.mark.parametrize("field,year,query", [("unknown", 2026, "abc"), ("buyer", 2014, "abc"),
    ("buyer", 9999, "abc"), ("search", 2026, "x" * 201)])
def test_invalid_parameters(field, year, query):
    with pytest.raises(ValueError):
        suggestions.suggestions(field, year, query)


def test_missing_and_corrupt_catalogs_are_recoverable(tmp_path, monkeypatch):
    monkeypatch.setattr(suggestions, "RESOURCES", tmp_path)
    assert "no está disponible" in suggestions.suggestions("buyer", 2026, "hospital")["message"]
    (tmp_path / "sercop_catalog_2026.json").write_text(json.dumps({"catalog_sha256": "wrong"}))
    (tmp_path / "sercop_catalog_2026.json.gz").write_bytes(b"not gzip")
    assert not suggestions.suggestions("supplier", 2026, "hospital")["options"]


def test_live_processes_are_bounded_deduplicated_and_cached(monkeypatch):
    calls = []
    rows = [{"ocid": f"ocds-5wno2w-demo-{i}", "code": f"SIE-2026-{i}", "description": "Equipos para hospital", "buyer": "Hospital"} for i in range(20)]
    def search(*args):
        calls.append(args)
        return {"results": [rows[0], *rows]}
    monkeypatch.setattr(sercop_ocds, "search_processes", search)
    data = suggestions.suggestions("search", 2026, "equipo", "hospital", "proveedor")
    assert calls == [(2026, "equipo", "hospital", "proveedor")]
    assert len(data["options"]) == 8
    assert len({item["id"] for item in data["options"]}) == 8
    assert data["options"][0]["value"] == "SIE-2026-0"
    assert suggestions.suggestions("search", 2026, "equipo", "hospital", "proveedor") == data
    assert len(calls) == 1
    suggestions.suggestions("search", 2025, "equipo")
    assert len(calls) == 2
    suggestions.suggestions("search", 2026, "equipo", "otro hospital", "proveedor")
    assert len(calls) == 3


def test_cache_expiry_and_capacity(monkeypatch):
    clock, calls = [0.0], []
    monkeypatch.setattr(suggestions.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(suggestions, "MAX_CACHE_ENTRIES", 2)
    def search(*args):
        calls.append(args)
        return {"results": []}
    monkeypatch.setattr(sercop_ocds, "search_processes", search)
    suggestions.suggestions("search", 2026, "uno")
    clock[0] = 61
    suggestions.suggestions("search", 2026, "uno")
    assert len(calls) == 2
    suggestions.suggestions("search", 2026, "dos")
    suggestions.suggestions("search", 2026, "tres")
    assert len(suggestions._cache) == 2


def test_remote_outage_and_invalid_optional_filters_do_not_prevent_free_text(monkeypatch):
    def fail(*args):
        raise sercop_ocds.SercopUnavailable("Unavailable")
    monkeypatch.setattr(sercop_ocds, "search_processes", fail)
    data = suggestions.suggestions("search", 2026, "medicamentos")
    assert not data["options"] and "directamente" in data["message"]
    assert not suggestions.suggestions("search", 2026, "medicamentos", "ab")["options"]


def test_only_one_live_suggestion_query_is_admitted():
    assert suggestions._query_slots.acquire(blocking=False)
    try:
        assert "en curso" in suggestions.suggestions("search", 2026, "equipo")["message"]
    finally:
        suggestions._query_slots.release()


def test_api_returns_suggestions_but_does_not_import_records(client, monkeypatch):
    monkeypatch.setattr(sercop_ocds, "fetch_process", lambda *args: pytest.fail("No record import"))
    response = client.get("/api/sources/sercop/suggestions", params={"year": 2026, "field": "buyer", "q": "hospital"})
    assert response.status_code == 200 and response.json()["options"]
    assert client.get("/api/cases").json() == []
    assert client.get("/api/sources/sercop/suggestions", params={"year": 2026, "field": "url", "q": "abc"}).status_code == 422


def test_catalog_build_is_reproducible(tmp_path):
    from deploy.build_sercop_catalog import build
    source = tmp_path / "source.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("metadata_2026.csv", 'PublishedDate,License\n2026-11-13T08:00:00Z,https://example.test/license\n')
        archive.writestr("releases_2026.csv", 'buyer_id,buyer_name\na,Hospital\na,HOSPITAL\na,Hospital\n')
        archive.writestr("suppliers_2026.csv", 'id,name\nb,Proveedor\n')
    first = build(source, tmp_path / "one", 2026)
    second = build(source, tmp_path / "two", 2026)
    assert first == second
    raw = (tmp_path / "one/sercop_catalog_2026.json.gz").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == first["catalog_sha256"]
    assert len(json.loads(gzip.decompress(raw))["buyer"]) == 2
