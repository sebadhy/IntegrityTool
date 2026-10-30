"""Upgrade the actual pre-PoC SQLite layout without modifying its input."""
import hashlib
import json
import sqlite3

import pytest

from src.analyzer.review_store import ReviewStore
from src.manage_storage import migrate_sqlite
from src.analyzer import storage_schema as schema
from sqlalchemy import func, inspect, select


def legacy_database(path):
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE cases(id TEXT PRIMARY KEY,request_key TEXT UNIQUE NOT NULL,title TEXT NOT NULL,
                status TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,result TEXT,error TEXT);
            CREATE TABLE documents(id TEXT PRIMARY KEY,case_id TEXT NOT NULL,name TEXT NOT NULL,role TEXT NOT NULL,
                version TEXT NOT NULL,sha256 TEXT NOT NULL,supersedes TEXT,content BLOB NOT NULL);
            CREATE TABLE analysis_cache(cache_key TEXT PRIMARY KEY,result TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE taxonomy_snapshots(sha256 TEXT PRIMARY KEY,source_text TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE reviews(case_id TEXT NOT NULL,item_id TEXT NOT NULL,state TEXT NOT NULL,comment TEXT NOT NULL,
                reviewer TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(case_id,item_id));
            CREATE TABLE events(id INTEGER PRIMARY KEY AUTOINCREMENT,case_id TEXT NOT NULL,item_id TEXT NOT NULL,
                state TEXT NOT NULL,comment TEXT NOT NULL,reviewer TEXT NOT NULL,created_at TEXT NOT NULL);
        """)
        result = {"summary": "Lectura anterior que debe conservarse.", "items": []}
        db.execute("INSERT INTO cases VALUES(?,?,?,?,?,?,?,?)",
            ("case-old", "request-old", "Expediente anterior", "ready", "2026-01-01", "2026-01-01", json.dumps(result), None))
        for identity, content in [("z-first", b"%PDF-first"), ("a-second", b"%PDF-second")]:
            db.execute("INSERT INTO documents VALUES(?,?,?,?,?,?,?,?)",
                (identity, "case-old", identity + ".pdf", "pliego", "1", hashlib.sha256(content).hexdigest(), None, content))
        db.execute("INSERT INTO reviews VALUES(?,?,?,?,?,?)",
            ("case-old", "item-old", "followup", "Comentario conservado", "Revisor local", "2026-01-01"))
        db.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?)",
            (7, "case-old", "item-old", "followup", "Comentario conservado", "Revisor local", "2026-01-01"))
        return result


def test_legacy_upgrade_preserves_order_originals_and_snapshots(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    result = legacy_database(path)
    store = ReviewStore(path)
    try:
        assert store.get_case("case-old")["result"] == result
        assert [doc["id"] for doc in store.get_case("case-old")["documents"]] == ["z-first", "a-second"]
        assert store.document("case-old", "z-first")["content"] == b"%PDF-first"
        assert store.events("case-old")[0]["id"] == 7
        assert store.get_case("case-old")["reviews"]["item-old"]["revision"] == 1
        with store.connection() as db:
            for table in schema.metadata.sorted_tables:
                expected = {index.name for index in table.indexes}
                actual = {index["name"] for index in inspect(db).get_indexes(table.name)}
                assert expected <= actual
    finally:
        store.close()
    reopened = ReviewStore(path)
    assert reopened.get_case("case-old")["result"] == result
    reopened.close()


def test_legacy_migration_changes_neither_input_nor_evidence(tmp_path):
    source = tmp_path / "legacy.sqlite3"
    result = legacy_database(source)
    before = source.read_bytes()
    target = ReviewStore(tmp_path / "destination.sqlite3")
    try:
        report = migrate_sqlite(source, target)
        assert report["applied"] and report["model_calls"] == 0
        assert source.read_bytes() == before
        assert target.get_case("case-old")["result"] == result
        assert target.document("case-old", "z-first")["content"] == b"%PDF-first"
        assert target.events("case-old")[0]["id"] == 7
        assert target.get_case("case-old")["reviews"]["item-old"]["comment"] == "Comentario conservado"
    finally:
        target.close()


def test_schema_version_mismatch_is_rejected_without_reinitialization(tmp_path):
    path = tmp_path / "future.sqlite3"
    store = ReviewStore(path)
    store.close()
    with sqlite3.connect(path) as db:
        db.execute("UPDATE schema_migrations SET version=99")
    with pytest.raises(ValueError, match="versión"):
        ReviewStore(path)


def test_failed_original_upload_rolls_back_all_imported_rows(tmp_path, monkeypatch):
    source = tmp_path / "legacy.sqlite3"
    legacy_database(source)
    before = source.read_bytes()
    target = ReviewStore(tmp_path / "destination.sqlite3")
    original_put = target.documents.put
    calls = []
    def fail_second(content):
        calls.append(True)
        if len(calls) == 2:
            raise OSError("Simulated storage interruption")
        return original_put(content)
    monkeypatch.setattr(target.documents, "put", fail_second)
    try:
        with pytest.raises(OSError):
            migrate_sqlite(source, target)
        with target.connection() as db:
            for table in (schema.cases, schema.documents, schema.reviews, schema.events):
                assert db.scalar(select(func.count()).select_from(table)) == 0
        assert source.read_bytes() == before
    finally:
        target.close()


def test_import_does_not_leave_assisted_processing_running_forever(tmp_path):
    source = tmp_path / "legacy.sqlite3"
    result = legacy_database(source)
    result["assistance"] = {"status": "running", "calls": []}
    result["semantic_review"] = {"status": "pending"}
    with sqlite3.connect(source) as db:
        db.execute("UPDATE cases SET result=?", (json.dumps(result),))
    before = source.read_bytes()
    target = ReviewStore(tmp_path / "destination.sqlite3")
    try:
        migrate_sqlite(source, target)
        result = target.get_case("case-old")["result"]
        assert result["assistance"]["status"] == result["semantic_review"]["status"] == "unavailable"
        assert result["messages"]
        assert source.read_bytes() == before
    finally:
        target.close()
