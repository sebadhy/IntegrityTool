"""Local, transactional storage. Not an identity or multi-tenant access system."""
from __future__ import annotations

import json
import hashlib
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReviewStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS cases (
                    id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, title TEXT NOT NULL,
                    status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    result TEXT, error TEXT);
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, case_id TEXT NOT NULL, name TEXT NOT NULL,
                    role TEXT NOT NULL, version TEXT NOT NULL, sha256 TEXT NOT NULL,
                    supersedes TEXT, content BLOB NOT NULL,
                    FOREIGN KEY(case_id) REFERENCES cases(id));
                CREATE TABLE IF NOT EXISTS analysis_cache (
                    cache_key TEXT PRIMARY KEY, result TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS taxonomy_snapshots (
                    sha256 TEXT PRIMARY KEY, source_text TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reviews (
                    case_id TEXT NOT NULL, item_id TEXT NOT NULL, state TEXT NOT NULL,
                    comment TEXT NOT NULL, reviewer TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY(case_id, item_id));
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL,
                    item_id TEXT NOT NULL, state TEXT NOT NULL, comment TEXT NOT NULL,
                    reviewer TEXT NOT NULL, created_at TEXT NOT NULL);
            """)
        if os.name != "nt":
            path.chmod(0o600)

    @contextmanager
    def connection(self):
        with sqlite3.connect(self.path, timeout=15) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            yield db

    def interrupt_unfinished(self):
        with self.connection() as db:
            db.execute("UPDATE cases SET status='interrupted', error=?, updated_at=? WHERE status IN ('queued','running')",
                       ("La ejecución se interrumpió al cerrar el servidor. Puede reintentarla.", utc_now()))

    def create_case(self, case_id: str, request_key: str, title: str, documents: list[dict]) -> str:
        with self.connection() as db:
            existing = db.execute("SELECT id FROM cases WHERE request_key=?", (request_key,)).fetchone()
            if existing:
                return existing["id"]
            now = utc_now()
            db.execute("INSERT INTO cases VALUES(?,?,?,?,?,?,NULL,NULL)", (case_id, request_key, title, "queued", now, now))
            for doc in documents:
                db.execute("INSERT INTO documents VALUES(?,?,?,?,?,?,?,?)", (
                    doc["id"], case_id, doc["name"], doc["role"], doc["version"], doc["sha256"], doc.get("supersedes"), doc["content"],
                ))
        return case_id

    def get_case(self, case_id: str) -> dict | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
            if not row:
                return None
            case = dict(row)
            case.pop("request_key", None)
            case["result"] = json.loads(case["result"]) if case["result"] else None
            case["documents"] = [dict(doc) for doc in db.execute(
                "SELECT id,name,role,version,sha256,supersedes,length(content) AS size FROM documents WHERE case_id=? ORDER BY rowid", (case_id,))]
            case["reviews"] = {row["item_id"]: dict(row) for row in db.execute("SELECT * FROM reviews WHERE case_id=?", (case_id,))}
            return case

    def list_cases(self) -> list[dict]:
        with self.connection() as db:
            return [dict(row) for row in db.execute("SELECT id,title,status,created_at,updated_at FROM cases ORDER BY created_at DESC LIMIT 50")]

    def document(self, case_id: str, document_id: str) -> dict | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM documents WHERE case_id=? AND id=?", (case_id, document_id)).fetchone()
            return dict(row) if row else None

    def update_case(self, case_id: str, status: str, result: dict | None = None, error: str | None = None):
        with self.connection() as db:
            db.execute("UPDATE cases SET status=?,result=?,error=?,updated_at=? WHERE id=?",
                       (status, json.dumps(result, ensure_ascii=False) if result is not None else None, error, utc_now(), case_id))

    def cache_get(self, key: str) -> dict | None:
        with self.connection() as db:
            row = db.execute("SELECT result FROM analysis_cache WHERE cache_key=?", (key,)).fetchone()
            return json.loads(row["result"]) if row else None

    def cache_put(self, key: str, result: dict):
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO analysis_cache VALUES(?,?,?)", (key, json.dumps(result, ensure_ascii=False), utc_now()))

    def save_taxonomy(self, sha256: str, source_text: str):
        if not source_text or hashlib.sha256(source_text.encode("utf-8")).hexdigest() != sha256:
            raise ValueError("La copia de reglas no coincide con su huella documental.")
        with self.connection() as db:
            db.execute("INSERT OR IGNORE INTO taxonomy_snapshots VALUES(?,?,?)", (sha256, source_text, utc_now()))

    def get_taxonomy(self, sha256: str) -> str | None:
        with self.connection() as db:
            row = db.execute("SELECT source_text FROM taxonomy_snapshots WHERE sha256=?", (sha256,)).fetchone()
            return row["source_text"] if row else None

    def save_review(self, case_id: str, item_id: str, state: str, comment: str, reviewer: str):
        with self.connection() as db:
            now = utc_now()
            db.execute("INSERT OR REPLACE INTO reviews VALUES(?,?,?,?,?,?)", (case_id, item_id, state, comment, reviewer, now))
            db.execute("INSERT INTO events(case_id,item_id,state,comment,reviewer,created_at) VALUES(?,?,?,?,?,?)", (case_id, item_id, state, comment, reviewer, now))

    def events(self, case_id: str) -> list[dict]:
        with self.connection() as db:
            return [dict(row) for row in db.execute("SELECT * FROM events WHERE case_id=? ORDER BY id DESC", (case_id,))]
