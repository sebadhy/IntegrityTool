"""Versioned relational schema shared by the local and server deployments."""
from __future__ import annotations

import hashlib

from sqlalchemy import (BigInteger, Column, Float, ForeignKey, ForeignKeyConstraint,
                        Index, Integer, JSON, LargeBinary, MetaData, String, Table,
                        Text, inspect, select, text)
from sqlalchemy.dialects.postgresql import JSONB

SCHEMA_VERSION = 1
SCHEMA_CHECKSUM = hashlib.sha256(b"integrity-storage-v1-2026-10").hexdigest()
metadata = MetaData()
json_type = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")

cases = Table("cases", metadata,
    Column("id", String(100), primary_key=True),
    Column("request_key", String(100), nullable=False, unique=True),
    Column("title", Text, nullable=False), Column("status", String(30), nullable=False),
    Column("created_at", Text, nullable=False), Column("updated_at", Text, nullable=False),
    Column("result", json_type), Column("error", Text),
    Column("request_fingerprint", String(64)), Column("current_job_id", String(100)))
documents = Table("documents", metadata,
    Column("id", String(100), primary_key=True),
    Column("case_id", ForeignKey("cases.id"), nullable=False),
    Column("name", Text, nullable=False), Column("role", String(30), nullable=False),
    Column("version", Text, nullable=False), Column("sha256", String(64), nullable=False),
    Column("supersedes", String(100)),
    # Retained only to read old SQLite originals without rewriting user data.
    Column("content", LargeBinary, nullable=False, default=b""),
    Column("storage_key", Text), Column("byte_size", BigInteger, nullable=False, default=0),
    Column("ordinal", Integer, nullable=False, default=0))
analysis_cache = Table("analysis_cache", metadata,
    Column("cache_key", String(128), primary_key=True),
    Column("result", json_type, nullable=False), Column("created_at", Text, nullable=False))
taxonomy_snapshots = Table("taxonomy_snapshots", metadata,
    Column("sha256", String(64), primary_key=True), Column("source_text", Text, nullable=False),
    Column("created_at", Text, nullable=False))
reviews = Table("reviews", metadata,
    Column("case_id", ForeignKey("cases.id"), primary_key=True),
    Column("item_id", String(100), primary_key=True), Column("state", String(30), nullable=False),
    Column("comment", Text, nullable=False), Column("reviewer", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Column("revision", Integer, nullable=False, default=1))
events = Table("events", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("case_id", ForeignKey("cases.id"), nullable=False), Column("item_id", String(100), nullable=False),
    Column("state", String(30), nullable=False), Column("comment", Text, nullable=False),
    Column("reviewer", Text, nullable=False), Column("created_at", Text, nullable=False))
analysis_runs = Table("analysis_runs", metadata,
    Column("id", String(100), primary_key=True),
    Column("case_id", ForeignKey("cases.id"), nullable=False),
    Column("engine_version", Text), Column("taxonomy_sha256", String(64)),
    Column("created_at", Text, nullable=False), Column("updated_at", Text, nullable=False),
    Column("result", json_type, nullable=False))
findings = Table("review_findings", metadata,
    Column("run_id", ForeignKey("analysis_runs.id"), primary_key=True),
    Column("item_id", String(100), primary_key=True),
    Column("pattern_id", Text, nullable=False), Column("priority", String(20), nullable=False),
    Column("dimension", Text, nullable=False), Column("payload", json_type, nullable=False))
evidence = Table("review_evidence", metadata,
    Column("run_id", String(100), primary_key=True),
    Column("item_id", String(100), primary_key=True), Column("ordinal", Integer, primary_key=True),
    Column("document_id", ForeignKey("documents.id"), nullable=False),
    Column("page", Integer, nullable=False), Column("section", Text),
    Column("text", Text, nullable=False), Column("payload", json_type, nullable=False),
    ForeignKeyConstraint(["run_id", "item_id"], ["review_findings.run_id", "review_findings.item_id"]))
jobs = Table("analysis_jobs", metadata,
    Column("id", String(100), primary_key=True),
    Column("case_id", ForeignKey("cases.id"), nullable=False),
    Column("status", String(30), nullable=False), Column("owner", String(100)),
    Column("token", String(100)), Column("lease_until", Float),
    Column("attempt", Integer, nullable=False, default=0),
    Column("created_at", Text, nullable=False), Column("updated_at", Text, nullable=False),
    Column("error", Text))
assisted_requests = Table("assisted_requests", metadata,
    Column("cache_key", String(64), primary_key=True),
    Column("case_id", ForeignKey("cases.id")), Column("job_id", ForeignKey("analysis_jobs.id")),
    Column("purpose", String(30)),
    Column("status", String(30), nullable=False), Column("payload", json_type),
    Column("created_at", Text, nullable=False), Column("updated_at", Text, nullable=False))
schema_migrations = Table("schema_migrations", metadata,
    Column("version", Integer, primary_key=True), Column("checksum", String(64), nullable=False),
    Column("applied_at", Text, nullable=False))
Index("ix_cases_updated", cases.c.updated_at, cases.c.id)
Index("ix_documents_case", documents.c.case_id, documents.c.ordinal)
Index("ix_jobs_claim", jobs.c.status, jobs.c.lease_until, jobs.c.created_at)
Index("ix_findings_pattern", findings.c.pattern_id, findings.c.priority)
Index("ix_evidence_document", evidence.c.document_id, evidence.c.page)

# Additive upgrade for the previously shipped SQLite schema. Originals and
# result snapshots remain untouched. Future changes require a new migration.
LEGACY_COLUMNS = {
    "cases": {"request_fingerprint": "VARCHAR(64)", "current_job_id": "VARCHAR(100)"},
    "documents": {"storage_key": "TEXT", "byte_size": "BIGINT NOT NULL DEFAULT 0",
                  "ordinal": "INTEGER NOT NULL DEFAULT 0"},
    "reviews": {"revision": "INTEGER NOT NULL DEFAULT 1"},
}


def initialize_schema(engine, timestamp: str) -> None:
    with engine.begin() as db:
        if engine.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(1852400171)"))
        existing = set(inspect(db).get_table_names())
        if "schema_migrations" in existing:
            validate_schema(db)
            return
        old_documents = []
        if "documents" in existing and engine.dialect.name == "sqlite":
            old_documents = list(db.execute(text("SELECT id,case_id,length(content) AS size FROM documents ORDER BY rowid")).mappings())
        for table, columns in LEGACY_COLUMNS.items():
            if table not in existing:
                continue
            present = {column["name"] for column in inspect(db).get_columns(table)}
            for name, definition in columns.items():
                if name not in present:
                    db.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))
        metadata.create_all(db)
        # create_all skips indexes belonging to tables that already existed.
        for table in metadata.sorted_tables:
            for index in table.indexes:
                index.create(db, checkfirst=True)
        counters = {}
        for doc in old_documents:
            ordinal = counters.get(doc["case_id"], 0)
            db.execute(documents.update().where(documents.c.id == doc["id"]).values(byte_size=doc["size"], ordinal=ordinal))
            counters[doc["case_id"]] = ordinal + 1
        if "cases" in existing:
            db.execute(cases.update().where(cases.c.status.in_(["queued", "running"])).values(
                status="interrupted", updated_at=timestamp,
                error="La versión anterior dejó una ejecución inconclusa. Revise antes de reintentar."))
        db.execute(schema_migrations.insert().values(
            version=SCHEMA_VERSION, checksum=SCHEMA_CHECKSUM, applied_at=timestamp))


def validate_schema(db) -> None:
    if "schema_migrations" not in inspect(db).get_table_names():
        raise ValueError("La base no está inicializada. Ejecute python -m src.manage_storage init.")
    versions = list(db.execute(select(schema_migrations)).mappings())
    if len(versions) != 1 or versions[0]["version"] != SCHEMA_VERSION or versions[0]["checksum"] != SCHEMA_CHECKSUM:
        raise ValueError("La versión de la base no corresponde a esta aplicación. No se modificó el esquema.")
    inspector = inspect(db)
    tables = set(inspector.get_table_names())
    for table in metadata.sorted_tables:
        if table.name not in tables or not set(table.c.keys()) <= {
                column["name"] for column in inspector.get_columns(table.name)}:
            raise ValueError("El esquema de almacenamiento está incompleto. Se requiere revisión antes de iniciar.")
