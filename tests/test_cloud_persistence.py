"""Real local integration of the server database and object storage together."""
from sqlalchemy import func, select

from src.analyzer import storage_schema as schema
from src.analyzer.review_store import ReviewStore
from src.analyzer.review_worker import ReviewWorker
from src.analyzer.workbench_service import WorkbenchService
from src.manage_storage import migrate_sqlite
from test_document_storage import azure_storage
from test_storage_backends import store
from test_storage_migration import legacy_database
from test_workbench import pdf


def test_migration_and_new_analysis_use_database_with_blob_originals(store, azure_storage, tmp_path):
    cloud = ReviewStore(store.engine.url, document_storage=azure_storage, initialize=False)
    try:
        source = tmp_path / "previous.sqlite3"
        legacy_database(source)
        report = migrate_sqlite(source, cloud)
        assert report["applied"] and report["model_calls"] == 0
        assert cloud.document("case-old", "z-first")["content"] == b"%PDF-first"
        service = WorkbenchService(tmp_path, None, store=cloud, assisted=False, embedded_worker=False,
            corpus_provider=lambda hashes: ({}, {"snapshot": "test", "total_processes": 0}))
        content = pdf()
        case = service.create("Integración", "cloud-case", [
            {"name": "pliego.pdf", "role": "pliego", "content": content}])
        assert ReviewWorker(service).run_once()
        ready = cloud.get_case(case["id"])
        assert ready["status"] == "ready" and ready["result"]["items"]
        assert cloud.document(case["id"], case["documents"][0]["id"])["content"] == content
        item_id = ready["result"]["items"][0]["id"]
        cloud.save_review(case["id"], item_id, "followup", "Validar equivalencias", "Revisor", expected_revision=0)
        assert cloud.events(case["id"])[0]["id"] > 7
        with cloud.connection() as db:
            assert db.scalar(select(func.count()).select_from(schema.findings)) >= 1
            assert all(value == b"" for value in db.scalars(select(schema.documents.c.content)))
    finally:
        # The storage fixture owns its SDK client and deletes its test container.
        cloud.engine.dispose()
