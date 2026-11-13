import hashlib
import json
import zipfile

import pytest

from src import sercop_local as local, sercop_suggestions
from src.analyzer import sercop_ocds
from test_workbench_api import client
from test_workbench import pdf, wait_for_case


def test_official_snapshot_counts_and_search_without_network(monkeypatch):
    monkeypatch.setattr(sercop_ocds, "_read_json", lambda *args: pytest.fail("Must be offline"))
    data = local.search_processes(2026)
    assert data["total"] == 122264 and len(data["results"]) == 10
    assert data["data_source"] == "snapshot"
    assert data["published_at"] == "2026-11-13T08:24:54.127Z"


def test_code_words_accents_and_local_filters():
    result = local.search_processes(2026, "medicamentos")
    assert result["total"] > 0
    ocid = result["results"][0]["ocid"]
    code = result["results"][0]["code"]
    assert ocid in {r["ocid"] for r in local.search_processes(2026, code)["results"]}
    assert local.search_processes(2026, "adquisicion")["total"] == local.search_processes(2026, "ADQUISICIÓN")["total"]
    filtered = local.search_processes(2026, supplier="pfizer")
    assert filtered["total"] == 16
    for row in filtered["results"]:
        raw = json.loads(local.fetch_process(row["ocid"])["raw_json"])
        assert any("pfizer" in p["name"].lower() for p in raw["suppliers"])
    assert local.search_processes(2026, buyer="ministerio salud")["total"] > 0
    assert not local.search_processes(2026, "medicamentos", supplier="Proveedor que no existe 123456")["results"]


def test_no_duplicate_processes_with_multiple_suppliers_and_pagination():
    first, second = local.search_processes(2026), local.search_processes(2026, page=2)
    assert {r["ocid"] for r in first["results"]}.isdisjoint({r["ocid"] for r in second["results"]})
    assert first["total"] == second["total"]
    assert len({r["ocid"] for r in first["results"]}) == 10


@pytest.mark.parametrize("kwargs", [{"year": 2025}, {"page": 0}, {"page": 10001}, {"buyer": "ab"}, {"search": "x"*201}])
def test_invalid_local_queries(kwargs):
    with pytest.raises(ValueError):
        local.search_processes(**({"year": 2026} | kwargs))


def test_quotes_wildcards_and_sql_are_literal_values():
    assert not local.search_processes(2026, "' OR 1=1 --")["results"]
    assert not local.search_processes(2026, "___%")["results"]


def test_local_suggestions_are_read_only_and_do_not_call_api(monkeypatch):
    monkeypatch.setattr(sercop_ocds, "search_processes", lambda *args: pytest.fail("Must not query SERCOP"))
    data = sercop_suggestions.suggestions("search", 2026, "medicamentos", data_source="snapshot")
    assert data["source"] == "snapshot" and 1 <= len(data["options"]) <= 8
    assert all(item["id"].startswith("ocds-5wno2w-") for item in data["options"])


def test_local_record_has_truthful_provenance_and_no_pdf_claim():
    item = local.search_processes(2026, supplier="pfizer")["results"][0]
    record = local.fetch_process(item["ocid"])
    assert record["provider"] == "sercop_bulk_csv"
    assert record["document_reference_count"] == 0
    assert record["source_zip_sha256"] == "dcf8bf260cc0d2352c51ab8c801f4fb513395cef0ac3e6948e9821f8423ffa1f"
    assert record["sha256"] == hashlib.sha256(record["raw_json"].encode()).hexdigest()
    raw = json.loads(record["raw_json"])
    assert raw["format"] == "sercop_csv_extract/v1"
    assert record["metadata"]["objeto"] == raw["tender"]["description"]
    assert "extracto" in record["limitation"] and "no una respuesta" in record["limitation"]
    assert local.fetch_process(item["ocid"])["snapshot_id"] != record["snapshot_id"]


def test_missing_process_does_not_fallback_to_network(monkeypatch):
    monkeypatch.setattr(sercop_ocds, "fetch_process", lambda *args: pytest.fail("No network fallback"))
    with pytest.raises(ValueError, match="no figura"):
        local.fetch_process("ocds-5wno2w-no-existe-2026")


def test_missing_snapshot_is_recoverable(tmp_path, monkeypatch):
    def missing(): raise FileNotFoundError()
    monkeypatch.setattr(local, "_database", missing)
    with pytest.raises(sercop_ocds.SercopUnavailable, match="respaldo local"):
        local.search_processes(2026, "equipos")


def test_search_selection_and_analysis_api_work_with_external_network_blocked(client, monkeypatch):
    monkeypatch.setattr(sercop_ocds, "_read_json", lambda *args: pytest.fail("No external network"))
    response = client.get("/api/sources/sercop/search", params={"year": 2026, "supplier": "pfizer", "data_source": "snapshot"})
    assert response.status_code == 200 and response.json()["total"] == 16
    chosen = response.json()["results"][0]
    response = client.post("/api/sources/sercop/record", json={"ocid": chosen["ocid"], "data_source": "snapshot"})
    assert response.status_code == 200 and response.json()["provider"] == "sercop_bulk_csv"
    snapshot = response.json()
    assert "raw_json" not in snapshot
    response = client.post("/api/cases", data={"manifest": '[{"role":"pliego"}]', "request_key": "offline",
        "source_snapshot_id": snapshot["snapshot_id"], "source_confirmed": "true"},
        files=[("files", ("prueba.pdf", pdf(), "application/pdf"))])
    assert response.status_code == 202
    case = wait_for_case(client.app.state.service, response.json()["id"])
    assert case["status"] == "ready"
    exported = client.get(f'/api/cases/{case["id"]}/export?format=json').json()
    assert json.loads(exported["source"]["raw_json"])["format"] == "sercop_csv_extract/v1"
    assert exported["source"]["source_zip_sha256"] == snapshot["source_zip_sha256"]


def test_database_builder_rejects_orphan_rows_and_preserves_roles(tmp_path):
    from deploy.build_sercop_processes import build
    source = tmp_path / "source.zip"
    with zipfile.ZipFile(source, "w") as z:
        z.writestr("metadata_2026.csv", 'PublishedDate,License\n2026-11-13T00:00:00Z,CC\n')
        z.writestr("releases_2026.csv", 'ocid,id,buyer_name,buyer_id\nocds-5wno2w-prueba-2026,release-1,Comprador,comprador-1\n')
        z.writestr("tender_2026.csv", 'ocid,release_id,id,description,procuringEntity_name\nocds-5wno2w-prueba-2026,release-1,CODIGO-1,Objeto completo,Entidad distinta\n')
        z.writestr("suppliers_2026.csv", 'ocid,release_id,id,name,award_id\nocds-5wno2w-prueba-2026,release-1,proveedor-1,Proveedor,award-1\n')
    manifest = build(source, tmp_path / "output", 2026)
    assert manifest["process_count"] == 1 and manifest["supplier_rows"] == 1
    with zipfile.ZipFile(source) as z:
        files = {name: z.read(name) for name in z.namelist()}
    files["suppliers_2026.csv"] = b'ocid,release_id,id,name\nocds-5wno2w-huerfano,release-2,p,Proveedor\n'
    with zipfile.ZipFile(source, "w") as z:
        for name, contents in files.items():
            z.writestr(name, contents)
    with pytest.raises(ValueError, match="sin una entrega"):
        build(source, tmp_path / "orphan", 2026)
