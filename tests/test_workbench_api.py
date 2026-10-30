import csv
import hashlib
import io
import time

import pytest

from fastapi.testclient import TestClient
from src.workbench_api import create_app
from test_workbench import pdf


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "api.sqlite3", assisted=False, corpus_provider=lambda hashes: ({}, {"snapshot": "test", "total_processes": 0}))
    with TestClient(app) as instance:
        yield instance


def create_case(client):
    response = client.post("/api/cases", data={"manifest": '[{"role":"pliego"}]', "request_key": "api-request"}, files=[("files", ("pliego.pdf", pdf(), "application/pdf"))])
    assert response.status_code == 202, response.text
    case_id = response.json()["id"]
    for _ in range(100):
        case = client.get(f"/api/cases/{case_id}").json()
        if case["status"] in {"ready", "failed"}:
            return case
        time.sleep(.03)
    raise AssertionError("case not ready")


def test_api_upload_review_pdf_and_export(client):
    case = create_case(client)
    assert case["status"] == "ready"
    assert case["result"]["items"]
    doc_id = case["documents"][0]["id"]
    response = client.get(f'/api/cases/{case["id"]}/documents/{doc_id}')
    assert response.content.startswith(b"%PDF-")
    item_id = case["result"]["items"][0]["id"]
    response = client.put(f'/api/cases/{case["id"]}/items/{item_id}/review', json={"state": "followup", "comment": "Verificar soporte"})
    assert response.status_code == 200
    assert response.json()["state"] == "followup"
    for format in ["html", "csv", "json"]:
        export = client.get(f'/api/cases/{case["id"]}/export?format={format}')
        assert export.status_code == 200
        assert "Verificar soporte" in export.text
    assert len(client.get(f'/api/cases/{case["id"]}/history').json()) == 1


def test_csv_exports_unique_columns_evidence_and_analysis_provenance(client):
    case = create_case(client)
    response = client.get(f'/api/cases/{case["id"]}/export?format=csv')
    reader = csv.DictReader(io.StringIO(response.text.lstrip("\ufeff")))
    assert len(reader.fieldnames) == len(set(reader.fieldnames))
    rows = list(reader)
    assert len(rows) == sum(len(item["evidence"]) for item in case["result"]["items"])
    for row in rows:
        for field in ["observacion_id", "patron", "documento", "pagina", "fragmento", "engine_version"]:
            assert row[field]
        assert len(row["taxonomy_sha256"]) == 64
    exported = client.get(f'/api/cases/{case["id"]}/export?format=json').json()
    assert exported["result"]["provenance"] == case["result"]["provenance"]
    assert all(len(doc["sha256"]) == 64 for doc in exported["documents"])


def test_navigation_and_exports_do_not_repeat_analysis_or_call_llm(client, monkeypatch):
    case = create_case(client)
    def unexpected(*args, **kwargs):
        raise AssertionError("Navigation must use the persisted review.")
    monkeypatch.setattr("src.analyzer.workbench_service.analyze_document_bytes", unexpected)
    monkeypatch.setattr("src.analyzer.llm_reviewer._request_json", unexpected)
    document_id = case["documents"][0]["id"]
    for endpoint in [
        "/api/cases", f'/api/cases/{case["id"]}',
        f'/api/cases/{case["id"]}/documents/{document_id}',
        f'/api/cases/{case["id"]}/taxonomy',
        f'/api/cases/{case["id"]}/export?format=html',
        f'/api/cases/{case["id"]}/export?format=csv',
        f'/api/cases/{case["id"]}/export?format=json',
    ]:
        assert client.get(endpoint).status_code == 200


def test_api_reports_missing_taxonomy_without_success_or_export(client, monkeypatch):
    from src.analyzer.taxonomy_loader import TaxonomyLoadResult
    monkeypatch.setattr("src.analyzer.workbench_service.load_taxonomy",
                        lambda: TaxonomyLoadResult([], ["No disponible"], False))
    case = create_case(client)
    assert case["status"] == "failed"
    assert "reglas" in case["error"]
    assert not case["result"]
    assert client.get(f'/api/cases/{case["id"]}/export').status_code == 409


def test_api_does_not_blame_the_document_for_an_engine_error(client, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("Synthetic rule engine failure")
    monkeypatch.setattr("src.analyzer.workbench_service.analyze_document_bytes", fail)
    case = create_case(client)
    assert case["status"] == "failed"
    assert "No se pudo completar la revisión" in case["error"]
    assert "PDF" not in case["error"]
    assert client.get(f'/api/cases/{case["id"]}/export').status_code == 409


def test_api_rejects_cross_origin_mutation_and_unknown_host(client):
    assert client.post("/api/cases", headers={"Origin": "https://untrusted.example"}).status_code == 403
    assert client.get("/api/health", headers={"Host": "untrusted.example"}).status_code == 403


def test_api_rejects_invalid_manifest_and_unrelated_document(client):
    response = client.post("/api/cases", data={"manifest": '{}', "request_key": "bad"}, files=[("files", ("a.pdf", pdf(), "application/pdf"))])
    assert response.status_code == 400
    assert client.get("/api/cases/missing/documents/missing").status_code == 404


def test_api_downloads_exact_taxonomy_used_for_case(client):
    case = create_case(client)
    response = client.get(f'/api/cases/{case["id"]}/taxonomy')
    assert response.status_code == 200
    assert hashlib.sha256(response.content).hexdigest() == case["result"]["provenance"]["taxonomy_sha256"]
    assert "attachment" in response.headers["content-disposition"]


def test_api_does_not_fabricate_snapshot_for_older_case(client):
    case = create_case(client)
    case["result"]["provenance"].pop("taxonomy_archived")
    client.app.state.service.store.update_case(case["id"], "ready", result=case["result"])
    response = client.get(f'/api/cases/{case["id"]}/taxonomy')
    assert response.status_code == 409
    assert "no conserva" in response.json()["detail"]


def test_export_escapes_html_and_neutralizes_csv_formulas():
    from src.workbench_api import _csv_cell, _html_report
    assert _csv_cell("=SUM(A1)").startswith("'")
    report = _html_report({"title": "<script>alert(1)</script>", "reviews": {}, "result": {"summary": "Test", "documents": [], "items": [], "provenance": {}}})
    assert "<script>" not in report
    assert "&lt;script&gt;" in report
