"""Explicit initialization and offline migration; never invokes analysis or LLM."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import func, select, text
from dotenv import load_dotenv

from .analyzer import storage_schema as s
from .analyzer.document_storage import FileDocumentStorage, verify_content
from .analyzer.review_store import ReviewStore, utc_now

COPY_ORDER = [
    s.cases, s.documents, s.analysis_cache, s.taxonomy_snapshots, s.reviews, s.events,
    s.analysis_runs, s.findings, s.evidence, s.jobs, s.assisted_requests,
]


@contextmanager
def source_snapshot(source: Path, documents_root: Path | None = None):
    source = source.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="integrity-migration-") as directory:
        snapshot = Path(directory) / "source.sqlite3"
        # SQLite backup provides a consistent snapshot, unlike copying a live
        # database file without its journal. The original is opened read-only.
        original = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
        backup = sqlite3.connect(snapshot)
        try:
            original.backup(backup)
            if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("La base de origen no superó la comprobación de integridad.")
        finally:
            backup.close()
            original.close()
        source_digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
        store = ReviewStore(snapshot,
            document_storage=FileDocumentStorage(documents_root or source.parent / "documents", create=False))
        try:
            yield store, source_digest
        finally:
            store.close()


def migrate_sqlite(source: Path, target: ReviewStore | None = None, *, documents_root: Path | None = None) -> dict:
    if target is not None and target.path == source.resolve():
        raise ValueError("El destino debe ser distinto de la base de origen.")
    with source_snapshot(source, documents_root) as (original, digest):
        with original.connection() as db:
            counts = {table.name: db.scalar(select(func.count()).select_from(table)) for table in COPY_ORDER}
        manifest = {"source_snapshot_sha256": digest, "schema_version": s.SCHEMA_VERSION,
                    "created_at": utc_now(), "counts": counts, "documents": [],
                    "applied": False, "model_calls": 0}
        with original.connection() as db:
            identities = list(db.execute(select(s.documents.c.id, s.documents.c.case_id)).mappings())
        for row in identities:
            document = original.document(row["case_id"], row["id"])
            manifest["documents"].append({"id": row["id"], "case_id": row["case_id"],
                "sha256": document["sha256"], "size": len(document["content"])})
        if target is None:
            return manifest
        with original.connection() as source_db, target.connection() as db:
            if target.is_postgres:
                db.execute(text("SELECT pg_advisory_xact_lock(1852400171)"))
                db.execute(text("LOCK TABLE cases IN EXCLUSIVE MODE"))
            if any(db.scalar(select(func.count()).select_from(table)) for table in COPY_ORDER):
                raise ValueError("El destino debe estar vacío. No se sobrescribieron revisiones.")
            imported_cases = []
            for table in COPY_ORDER:
                for source_row in source_db.execute(select(table)).mappings():
                    row = dict(source_row)
                    if table is s.documents:
                        content = (original.documents.read(row["storage_key"], row["sha256"], row["byte_size"])
                            if row["storage_key"] else verify_content(row["content"], row["sha256"], row["byte_size"]))
                        reference = target.documents.put(content)
                        row.update(content=b"", storage_key=reference.key, byte_size=reference.size)
                    elif table is s.cases:
                        if row["status"] in {"queued", "running"}:
                            row.update(status="interrupted",
                                error="Ejecución importada sin reanudación automática.", updated_at=utc_now())
                        imported_cases.append(row)
                        if row["result"] is not None:
                            interrupted = False
                            for section in ("assistance", "semantic_review"):
                                stage = row["result"].get(section, {})
                                if stage.get("status") in {"pending", "running"}:
                                    stage["status"] = "unavailable"
                                    interrupted = True
                            if interrupted:
                                row["result"].setdefault("messages", []).append(
                                    "La lectura adicional quedó inconclusa antes de la importación y no se reanudó automáticamente.")
                    elif table is s.jobs:
                        if row["status"] in {"queued", "running"}:
                            row.update(status="interrupted", owner=None, token=None, lease_until=None,
                                error="Trabajo importado; requiere reintento humano explícito.")
                    db.execute(table.insert().values(**row))
            for case in imported_cases:
                if case["result"] is None:
                    continue
                run_id = case["current_job_id"] or f"legacy-{case['id']}"
                if not db.scalar(select(s.analysis_runs.c.id).where(s.analysis_runs.c.id == run_id)):
                    target._project_result(db, case["id"], run_id, case["result"])
            if target.is_postgres:
                db.execute(text("SELECT setval(pg_get_serial_sequence('events','id'), "
                    "COALESCE((SELECT MAX(id) FROM events),1), EXISTS(SELECT 1 FROM events))"))
            for table in (s.cases, s.documents, s.reviews, s.events, s.analysis_cache, s.taxonomy_snapshots):
                if db.scalar(select(func.count()).select_from(table)) != counts[table.name]:
                    raise ValueError("Los conteos de origen y destino no coinciden; la importación se revirtió.")
            # Verify every referenced destination object before committing rows.
            for document in manifest["documents"]:
                row = db.execute(select(s.documents).where(s.documents.c.id == document["id"])).mappings().one()
                target.documents.read(row["storage_key"], row["sha256"], row["byte_size"])
        manifest["applied"] = True
        return manifest


def main():
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    parser = argparse.ArgumentParser(description="Preparar o migrar persistencia de Integrity Tool.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Inicializar explícitamente el esquema configurado.")
    migration = commands.add_parser("migrate", help="Inspeccionar o importar una base SQLite.")
    migration.add_argument("--source", type=Path, required=True)
    migration.add_argument("--documents-root", type=Path, help="Directorio de originales si no está junto a SQLite.")
    migration.add_argument("--apply", action="store_true", help="Importar a un destino inicializado y vacío.")
    migration.add_argument("--manifest", type=Path, help="Guardar comprobante sin sobrescribir otro archivo.")
    args = parser.parse_args()
    from .analyzer.storage_settings import create_review_store
    try:
        if args.command == "migrate" and args.manifest and args.manifest.exists():
            raise ValueError("El archivo de comprobante ya existe; elija otro nombre antes de importar.")
        if args.command == "init":
            store = create_review_store(root, initialize=True)
            try:
                output = {"schema_version": s.SCHEMA_VERSION,
                          "backend": "postgresql" if store.is_postgres else "sqlite", "initialized": True}
            finally:
                store.close()
        elif not args.apply:
            output = migrate_sqlite(args.source, documents_root=args.documents_root)
        else:
            store = create_review_store(root, initialize=False)
            try:
                output = migrate_sqlite(args.source, store, documents_root=args.documents_root)
            finally:
                store.close()
        content = json.dumps(output, ensure_ascii=False, indent=2)
        if args.command == "migrate" and args.manifest:
            with args.manifest.open("x", encoding="utf-8") as manifest:
                manifest.write(content + "\n")
        print(content)
    except Exception as exc:
        # Connection exceptions can include server details; do not print DSNs.
        message = str(exc) if isinstance(exc, (ValueError, FileExistsError, FileNotFoundError)) else (
            "No se pudo completar la operación de almacenamiento. Compruebe configuración y conectividad.")
        raise SystemExit(message) from None


if __name__ == "__main__":
    main()
