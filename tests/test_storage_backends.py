"""Persistence contracts run against SQLite and an explicitly local PostgreSQL."""
import hashlib
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import make_url

from src.analyzer import storage_schema as schema
from src.analyzer.document_storage import FileDocumentStorage
from src.analyzer.review_store import JobLeaseLost, ReviewStore, StorageConflict
from src.analyzer.workbench_service import WorkbenchService
from src.analyzer.review_worker import ReviewWorker
from src.manage_storage import migrate_sqlite
from test_workbench import pdf


@pytest.fixture(params=["sqlite", "postgres"])
def store(request, tmp_path):
    if request.param == "sqlite":
        instance = ReviewStore(tmp_path / "reviews.sqlite3")
        try:
            yield instance
        finally:
            instance.close()
        return
    url = os.getenv("INTEGRITY_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set INTEGRITY_TEST_POSTGRES_URL for local PostgreSQL integration.")
    parsed = make_url(url)
    if parsed.host not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("Integration tests only accept a local PostgreSQL, never a remote database.")
    import psycopg
    from psycopg import sql
    name = "integrity_test_" + uuid.uuid4().hex
    admin = psycopg.connect(url, autocommit=True)
    admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)))
    isolated = parsed.update_query_dict({"options": "-csearch_path=" + name})
    instance = ReviewStore(isolated, document_storage=FileDocumentStorage(tmp_path / "objects"), initialize=True)
    try:
        yield instance
    finally:
        instance.close()
        admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name)))
        admin.close()


def create_case(store, *, key=None, content=b"%PDF-local-test-document"):
    identity = str(uuid.uuid4())
    document = {"id": str(uuid.uuid4()), "name": "pliego.pdf", "role": "pliego", "version": "1",
                "sha256": hashlib.sha256(content).hexdigest(), "supersedes": None, "content": content}
    case_id = store.create_case(identity, key or str(uuid.uuid4()), "Prueba de persistencia", [document])
    return case_id, document


def peer(store):
    return ReviewStore(store.engine.url, document_storage=FileDocumentStorage(store.documents.root))


def count(store, table):
    with store.connection() as db:
        return db.scalar(select(func.count()).select_from(table))


def test_originals_are_external_and_verified(store):
    case_id, document = create_case(store)
    with store.connection() as db:
        row = db.execute(select(schema.documents)).mappings().one()
        assert row["content"] == b""
        assert row["storage_key"]
    assert store.document(case_id, document["id"])["content"] == document["content"]
    assert store.get_case(case_id)["documents"][0]["size"] == len(document["content"])


def test_changed_content_cannot_reuse_a_request_key(store):
    create_case(store, key="same-request")
    with pytest.raises(StorageConflict):
        create_case(store, key="same-request", content=b"%PDF-different-document")
    assert count(store, schema.cases) == 1
    assert count(store, schema.jobs) == 1


def test_concurrent_identical_requests_have_one_case_and_one_job(store):
    other = peer(store)
    try:
        with ThreadPoolExecutor(2) as executor:
            results = list(executor.map(lambda instance: create_case(instance, key="same")[0], [store, other]))
        assert results[0] == results[1]
        assert count(store, schema.cases) == count(store, schema.jobs) == 1
    finally:
        other.close()


def test_two_workers_cannot_claim_the_same_job(store):
    create_case(store)
    other = peer(store)
    try:
        with ThreadPoolExecutor(2) as executor:
            leases = list(executor.map(lambda value: value[0].claim_job(value[1]), [(store, "a"), (other, "b")]))
        assert sum(lease is not None for lease in leases) == 1
    finally:
        other.close()


def test_new_store_does_not_interrupt_an_owned_job(store):
    case_id, _ = create_case(store)
    lease = store.claim_job("worker-a")
    other = peer(store)
    try:
        assert other.get_case(case_id)["status"] == "running"
        assert other.claim_job("worker-b") is None
        assert store.heartbeat(lease)
    finally:
        other.close()


def test_expired_worker_cannot_write_after_recovery(store):
    case_id, _ = create_case(store)
    old = store.claim_job("worker-old")
    with store.connection() as db:
        db.execute(schema.jobs.update().values(lease_until=0))
    current = store.claim_job("worker-new")
    assert current.id == old.id and current.token != old.token and current.attempt == 2
    assert not store.heartbeat(old)
    with store.job_context(old), pytest.raises(JobLeaseLost):
        store.update_case(case_id, "failed", error="Stale worker")
    with store.job_context(current):
        store.update_case(case_id, "ready", {"items": []})
        store.complete_job(current)
    assert store.get_case(case_id)["status"] == "ready"


def test_lease_attempts_are_bounded(store):
    case_id, _ = create_case(store)
    store.claim_job("old")
    with store.connection() as db:
        db.execute(schema.jobs.update().values(lease_until=0))
    assert store.claim_job("new", max_attempts=1) is None
    assert store.get_case(case_id)["status"] == "interrupted"


def test_findings_evidence_and_snapshot_commit_together(store):
    case_id, document = create_case(store)
    result = {"provenance": {"engine_version": "test", "taxonomy_sha256": "a" * 64},
        "items": [{"id": "item-1", "pattern_id": "pattern-1", "priority": "media", "dimension": "competencia",
            "evidence": [{"document_id": document["id"], "page": 3, "section": "Condiciones",
                          "text": "Se requiere validar la condición."}]}]}
    store.update_case(case_id, "ready", result)
    assert count(store, schema.findings) == count(store, schema.evidence) == count(store, schema.analysis_runs) == 1
    with store.connection() as db:
        assert db.scalar(select(schema.analysis_runs.c.result)) == result
    invalid = {**result, "items": [{**result["items"][0], "evidence": [
        {"document_id": "unrelated", "page": 1, "text": "Wrong document"}]}]}
    with pytest.raises(ValueError):
        store.update_case(case_id, "ready", invalid)
    assert store.get_case(case_id)["result"] == result
    assert count(store, schema.evidence) == 1


def test_review_revision_prevents_lost_comments(store):
    case_id, _ = create_case(store)
    store.save_review(case_id, "item-1", "followup", "Primera", "Revisor", expected_revision=0)
    store.save_review(case_id, "item-1", "confirmed", "Segunda", "Revisor", expected_revision=1)
    with pytest.raises(StorageConflict):
        store.save_review(case_id, "item-1", "discarded", "Desactualizada", "Otro", expected_revision=1)
    assert store.get_case(case_id)["reviews"]["item-1"]["comment"] == "Segunda"
    assert len(store.events(case_id)) == 2


def test_unknown_assisted_request_is_not_automatically_repeated(store):
    key = "a" * 64
    assert store.reserve_assisted_request(key)
    assert not store.reserve_assisted_request(key)
    calls = []
    service = WorkbenchService(store.documents.root, None, store=store, assisted=False, embedded_worker=False)
    payload, cached = service._assisted_payload(key, lambda: calls.append(True), "summary")
    assert cached and not payload["llm_available"] and not calls
    store.finish_assisted_request(key, {"llm_available": False})
    assert store.cache_get(key) == {"llm_available": False}


def test_external_worker_processes_persisted_work_without_api_executor(store):
    service = WorkbenchService(store.documents.root, None, store=store, assisted=False, embedded_worker=False,
        corpus_provider=lambda hashes: ({}, {"snapshot": "test", "total_processes": 0}))
    case = service.create("Prueba", "external", [{"name": "pliego.pdf", "content": pdf(), "role": "pliego"}])
    assert case["status"] == "queued"
    assert ReviewWorker(service).run_once()
    result = store.get_case(case["id"])
    assert result["status"] == "ready" and result["result"]["items"]
    assert not store.pending_cases()
    assert count(store, schema.findings) >= 1


def test_recovery_keeps_baseline_without_repeating_uncertain_assistance(store, monkeypatch):
    case_id, _ = create_case(store)
    baseline = {"items": [], "assistance": {"status": "running", "calls": []},
                "semantic_review": {"status": "pending"}, "messages": []}
    store.update_case(case_id, "ready", baseline)
    service = WorkbenchService(store.documents.root, None, store=store, assisted=True, embedded_worker=False)
    monkeypatch.setattr("src.analyzer.llm_reviewer._request_json",
                        lambda *args: pytest.fail("Recovery must not call the model."))
    assert ReviewWorker(service).run_once()
    result = store.get_case(case_id)["result"]
    assert result["assistance"]["status"] == "unavailable"
    assert result["messages"] and result["items"] == []


def test_sqlite_migration_preserves_ids_documents_reviews_and_events(store, tmp_path):
    source_path = tmp_path / "source" / "reviews.sqlite3"
    source = ReviewStore(source_path)
    case_id, document = create_case(source)
    source.update_case(case_id, "ready", {"items": []})
    source.save_review(case_id, "item-1", "followup", "Conservar comentario", "Revisor")
    source.cache_put("corpus-" + "a" * 64, {"frequency": 1})
    before = source_path.read_bytes()
    preview = migrate_sqlite(source_path)
    assert not preview["applied"] and preview["model_calls"] == 0
    assert source_path.read_bytes() == before
    imported = migrate_sqlite(source_path, store)
    assert imported["applied"]
    assert store.document(case_id, document["id"])["content"] == document["content"]
    assert store.get_case(case_id)["reviews"] == source.get_case(case_id)["reviews"]
    assert store.events(case_id) == source.events(case_id)
    assert store.cache_get("corpus-" + "a" * 64) == {"frequency": 1}
    store.save_review(case_id, "item-1", "confirmed", "Validado después de importar", "Revisor", expected_revision=1)
    assert store.events(case_id)[0]["id"] > source.events(case_id)[0]["id"]
    assert source_path.read_bytes() == before
    with pytest.raises(ValueError, match="vacío"):
        migrate_sqlite(source_path, store)
    source.close()


def test_remote_postgres_cannot_silently_use_unverified_transport(tmp_path):
    with pytest.raises(ValueError, match="verify-full"):
        ReviewStore("postgresql://test:unused@not-a-real-server.example/integrity",
                    document_storage=FileDocumentStorage(tmp_path / "objects"))
