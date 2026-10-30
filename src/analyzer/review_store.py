"""Transactional review data and durable work, backed by SQLite or PostgreSQL.

Documents are evidence, not instructions. Stored observations remain preliminary
and do not replace human review or constitute a legal opinion.
"""
from __future__ import annotations

import hashlib
import json
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import and_, create_engine, delete, event, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import URL, make_url
from sqlalchemy.pool import NullPool

from . import storage_schema as s
from .document_storage import FileDocumentStorage, verify_content


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StorageConflict(ValueError):
    """A request key or review revision does not match its persisted contents."""


class JobLeaseLost(RuntimeError):
    """A stale worker must not publish results after losing ownership."""


@dataclass(frozen=True)
class JobLease:
    id: str
    case_id: str
    owner: str
    token: str
    attempt: int


class ReviewStore:
    def __init__(self, path: Path | str, *, document_storage=None, initialize: bool | None = None):
        raw = str(path)
        self.path = None
        if "://" not in raw:
            self.path = Path(path).resolve()
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            url = URL.create("sqlite", database=str(self.path))
        else:
            url = path if isinstance(path, URL) else make_url(raw)
            if url.get_backend_name() == "postgresql":
                url = url.set(drivername="postgresql+psycopg")
            elif url.get_backend_name() == "sqlite" and url.database:
                self.path = Path(url.database).resolve()
                self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                url = url.set(database=str(self.path))
            else:
                raise ValueError("Seleccione una base SQLite local o PostgreSQL.")
        self.is_postgres = url.get_backend_name() == "postgresql"
        if self.is_postgres and url.host not in {None, "localhost", "127.0.0.1", "::1"}:
            if url.query.get("sslmode") != "verify-full":
                raise ValueError("PostgreSQL remoto requiere sslmode=verify-full y una autoridad de confianza configurada.")
        if document_storage is None and self.is_postgres:
            raise ValueError("PostgreSQL requiere configurar almacenamiento de originales por separado.")
        self.documents = document_storage or FileDocumentStorage(self.path.parent / "documents")
        options = {"pool_pre_ping": True, "hide_parameters": True}
        if self.is_postgres:
            options.update(pool_size=5, max_overflow=5, connect_args={"connect_timeout": 10})
        else:
            options.update(connect_args={"check_same_thread": False, "timeout": 15}, poolclass=NullPool)
        self.engine = create_engine(url, **options)
        self._local = threading.local()
        if not self.is_postgres:
            @event.listens_for(self.engine, "connect")
            def configure_sqlite(connection, record):
                connection.isolation_level = None
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA busy_timeout=15000")

            @event.listens_for(self.engine, "begin")
            def begin_sqlite(connection):
                connection.exec_driver_sql("BEGIN IMMEDIATE")
        should_initialize = initialize if initialize is not None else not self.is_postgres
        try:
            if should_initialize:
                s.initialize_schema(self.engine, utc_now())
            else:
                with self.engine.connect() as db:
                    s.validate_schema(db)
        except Exception:
            self.engine.dispose()
            raise
        if self.path is not None:
            import os
            if os.name != "nt":
                self.path.chmod(0o600)

    def close(self):
        self.engine.dispose()
        close = getattr(self.documents, "close", None)
        if close:
            close()

    @contextmanager
    def connection(self):
        with self.engine.begin() as db:
            lease = getattr(self._local, "lease", None)
            if lease is not None:
                row = db.execute(select(s.jobs).where(s.jobs.c.id == lease.id).with_for_update()).mappings().first()
                if (not row or row["status"] != "running" or row["token"] != lease.token
                        or row["owner"] != lease.owner or row["lease_until"] <= self._clock(db)):
                    raise JobLeaseLost("La ejecución ya no posee la reserva del trabajo.")
            yield db

    @contextmanager
    def job_context(self, lease: JobLease):
        previous = getattr(self._local, "lease", None)
        self._local.lease = lease
        try:
            yield
        finally:
            self._local.lease = previous

    @staticmethod
    def _clock(db) -> float:
        return float(db.scalar(select(func.extract("epoch", func.current_timestamp()))))

    def _insert(self, table, values, keys, *, update=False):
        statement = (pg_insert if self.is_postgres else sqlite_insert)(table).values(**values)
        if update:
            return statement.on_conflict_do_update(index_elements=keys, set_={
                name: value for name, value in values.items() if name not in keys})
        return statement.on_conflict_do_nothing(index_elements=keys)

    def create_case(self, case_id: str, request_key: str, title: str, documents: list[dict]) -> str:
        indices = {doc["id"]: index for index, doc in enumerate(documents)}
        request_data = [title, [{key: doc.get(key) for key in
            ("name", "role", "version", "sha256")} | {
                "supersedes_index": indices.get(doc.get("supersedes"))
            } for doc in documents]]
        fingerprint = hashlib.sha256(json.dumps(request_data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        # Storage precedes the DB transaction. A crash may leave an unreferenced
        # object; never delete it inline because another request may reference it.
        prepared = []
        for ordinal, doc in enumerate(documents):
            reference = self.documents.put(doc["content"])
            if reference.sha256 != doc["sha256"]:
                raise ValueError("La huella del original no coincide con la selección.")
            prepared.append({key: doc.get(key) for key in
                ("id", "name", "role", "version", "sha256", "supersedes")} | {
                "case_id": case_id, "content": b"", "storage_key": reference.key,
                "byte_size": reference.size, "ordinal": ordinal})
        now = utc_now()
        job_id = str(uuid.uuid4())
        with self.connection() as db:
            created = db.execute(self._insert(s.cases, {
                "id": case_id, "request_key": request_key, "title": title, "status": "queued",
                "created_at": now, "updated_at": now, "result": None, "error": None,
                "request_fingerprint": fingerprint, "current_job_id": job_id},
                ["request_key"]).returning(s.cases.c.id)).scalar_one_or_none()
            if not created:
                existing = db.execute(select(s.cases).where(s.cases.c.request_key == request_key)).mappings().one()
                if existing["request_fingerprint"] != fingerprint:
                    raise StorageConflict("La solicitud ya existe con documentos o condiciones diferentes.")
                return existing["id"]
            for doc in prepared:
                db.execute(s.documents.insert().values(**doc))
            db.execute(s.jobs.insert().values(id=job_id, case_id=case_id, status="queued", attempt=0,
                                             created_at=now, updated_at=now))
        return case_id

    def get_case(self, case_id: str) -> dict | None:
        with self.connection() as db:
            row = db.execute(select(s.cases).where(s.cases.c.id == case_id)).mappings().first()
            if row is None:
                return None
            case = dict(row)
            case.pop("request_key", None)
            case.pop("request_fingerprint", None)
            case["documents"] = [dict(doc) for doc in db.execute(select(
                s.documents.c.id, s.documents.c.name, s.documents.c.role, s.documents.c.version,
                s.documents.c.sha256, s.documents.c.supersedes, s.documents.c.byte_size.label("size")
            ).where(s.documents.c.case_id == case_id).order_by(s.documents.c.ordinal)).mappings()]
            case["reviews"] = {row["item_id"]: dict(row) for row in db.execute(
                select(s.reviews).where(s.reviews.c.case_id == case_id)).mappings()}
            return case

    def list_cases(self, limit: int = 50, before: tuple[str, str] | None = None) -> list[dict]:
        query = select(s.cases.c.id, s.cases.c.title, s.cases.c.status, s.cases.c.created_at, s.cases.c.updated_at)
        if before:
            timestamp, identity = before
            query = query.where(or_(s.cases.c.updated_at < timestamp,
                and_(s.cases.c.updated_at == timestamp, s.cases.c.id < identity)))
        query = query.order_by(s.cases.c.updated_at.desc(), s.cases.c.id.desc()).limit(max(1, min(100, limit)))
        with self.connection() as db:
            return [dict(row) for row in db.execute(query).mappings()]

    def document(self, case_id: str, document_id: str) -> dict | None:
        with self.connection() as db:
            row = db.execute(select(s.documents).where(
                s.documents.c.case_id == case_id, s.documents.c.id == document_id)).mappings().first()
        if row is None:
            return None
        document = dict(row)
        if document["storage_key"]:
            document["content"] = self.documents.read(document["storage_key"], document["sha256"], document["byte_size"])
        else:
            document["content"] = verify_content(document["content"], document["sha256"], document["byte_size"])
        return document

    def update_case(self, case_id: str, status: str, result: dict | None = None, error: str | None = None):
        with self.connection() as db:
            case = db.execute(select(s.cases).where(s.cases.c.id == case_id).with_for_update()).mappings().one()
            db.execute(s.cases.update().where(s.cases.c.id == case_id).values(
                status=status, result=result, error=error, updated_at=utc_now()))
            if result is not None:
                self._project_result(db, case_id, case["current_job_id"] or f"legacy-{case_id}", result)

    def _project_result(self, db, case_id: str, run_id: str, result: dict):
        now = utc_now()
        provenance = result.get("provenance", {})
        values = {"id": run_id, "case_id": case_id, "created_at": now, "updated_at": now,
                  "engine_version": provenance.get("engine_version"),
                  "taxonomy_sha256": provenance.get("taxonomy_sha256"), "result": result}
        previous = db.execute(select(s.analysis_runs.c.created_at, s.analysis_runs.c.result).where(
            s.analysis_runs.c.id == run_id)).mappings().first()
        existing = previous["created_at"] if previous else None
        if existing:
            values["created_at"] = existing
        db.execute(self._insert(s.analysis_runs, values, ["id"], update=True))
        if previous and previous["result"].get("items", []) == result.get("items", []):
            return
        db.execute(delete(s.evidence).where(s.evidence.c.run_id == run_id))
        db.execute(delete(s.findings).where(s.findings.c.run_id == run_id))
        document_ids = set(db.scalars(select(s.documents.c.id).where(s.documents.c.case_id == case_id)))
        for item in result.get("items", []):
            db.execute(s.findings.insert().values(run_id=run_id, item_id=item["id"],
                pattern_id=item["pattern_id"], priority=item["priority"],
                dimension=item["dimension"], payload=item))
            for ordinal, evidence in enumerate(item.get("evidence", [])):
                if evidence["document_id"] not in document_ids:
                    raise ValueError("La evidencia no pertenece al expediente.")
                db.execute(s.evidence.insert().values(run_id=run_id, item_id=item["id"], ordinal=ordinal,
                    document_id=evidence["document_id"], page=evidence["page"],
                    section=evidence.get("section", ""), text=evidence["text"], payload=evidence))

    def cache_get(self, key: str) -> dict | None:
        with self.connection() as db:
            return db.scalar(select(s.analysis_cache.c.result).where(s.analysis_cache.c.cache_key == key))

    def cache_put(self, key: str, result: dict):
        with self.connection() as db:
            db.execute(self._insert(s.analysis_cache,
                {"cache_key": key, "result": result, "created_at": utc_now()}, ["cache_key"], update=True))

    def reserve_assisted_request(self, key: str, purpose: str = "") -> bool:
        now = utc_now()
        lease = getattr(self._local, "lease", None)
        with self.connection() as db:
            return db.execute(self._insert(s.assisted_requests, {
                "cache_key": key, "status": "started", "payload": None,
                "case_id": lease.case_id if lease else None, "job_id": lease.id if lease else None,
                "purpose": purpose,
                "created_at": now, "updated_at": now}, ["cache_key"])
                .returning(s.assisted_requests.c.cache_key)).scalar_one_or_none() is not None

    def finish_assisted_request(self, key: str, payload: dict):
        # A response can still be recorded after a worker lease expires, so a
        # recovered job can reuse it instead of repeating a potentially paid call.
        with self.engine.begin() as db:
            db.execute(s.assisted_requests.update().where(s.assisted_requests.c.cache_key == key).values(
                status="completed" if payload.get("llm_available") else "unavailable",
                payload=payload, updated_at=utc_now()))
            db.execute(self._insert(s.analysis_cache, {
                "cache_key": key, "result": payload, "created_at": utc_now()}, ["cache_key"], update=True))

    def save_taxonomy(self, sha256: str, source_text: str):
        if not source_text or hashlib.sha256(source_text.encode("utf-8")).hexdigest() != sha256:
            raise ValueError("La copia de reglas no coincide con su huella documental.")
        with self.connection() as db:
            db.execute(self._insert(s.taxonomy_snapshots,
                {"sha256": sha256, "source_text": source_text, "created_at": utc_now()}, ["sha256"]))

    def get_taxonomy(self, sha256: str) -> str | None:
        with self.connection() as db:
            return db.scalar(select(s.taxonomy_snapshots.c.source_text).where(s.taxonomy_snapshots.c.sha256 == sha256))

    def save_review(self, case_id: str, item_id: str, state: str, comment: str, reviewer: str,
                    expected_revision: int | None = None):
        with self.connection() as db:
            # Serialize edits even before the first review row exists.
            db.execute(select(s.cases.c.id).where(s.cases.c.id == case_id).with_for_update()).scalar_one()
            old = db.execute(select(s.reviews).where(
                s.reviews.c.case_id == case_id, s.reviews.c.item_id == item_id)).mappings().first()
            revision = old["revision"] if old else 0
            if expected_revision is not None and expected_revision != revision:
                raise StorageConflict("Otra persona actualizó esta revisión. Recargue antes de guardar.")
            now = utc_now()
            values = {"case_id": case_id, "item_id": item_id, "state": state, "comment": comment,
                      "reviewer": reviewer, "updated_at": now, "revision": revision + 1}
            db.execute(self._insert(s.reviews, values, ["case_id", "item_id"], update=True))
            db.execute(s.events.insert().values(
                case_id=case_id, item_id=item_id, state=state, comment=comment, reviewer=reviewer, created_at=now))

    def events(self, case_id: str) -> list[dict]:
        with self.connection() as db:
            return [dict(row) for row in db.execute(select(s.events).where(
                s.events.c.case_id == case_id).order_by(s.events.c.id.desc())).mappings()]

    def pending_cases(self) -> set[str]:
        with self.connection() as db:
            return set(db.scalars(select(s.jobs.c.case_id).where(s.jobs.c.status.in_(["queued", "running"]))))

    def retry_case(self, case_id: str):
        with self.connection() as db:
            case = db.execute(select(s.cases).where(s.cases.c.id == case_id).with_for_update()).mappings().first()
            if not case or case["status"] not in {"failed", "interrupted"}:
                raise StorageConflict("Esta revisión no puede reintentarse en su estado actual.")
            active = db.scalar(select(s.jobs.c.id).where(
                s.jobs.c.case_id == case_id, s.jobs.c.status.in_(["queued", "running"])).limit(1))
            if active:
                raise StorageConflict("La revisión ya tiene un trabajo pendiente o en ejecución.")
            now, identity = utc_now(), str(uuid.uuid4())
            db.execute(s.jobs.insert().values(id=identity, case_id=case_id, status="queued",
                attempt=0, created_at=now, updated_at=now))
            db.execute(s.cases.update().where(s.cases.c.id == case_id).values(
                current_job_id=identity, status="queued", result=None, error=None, updated_at=now))

    def claim_job(self, owner: str, lease_seconds: int = 90, max_attempts: int = 3) -> JobLease | None:
        with self.connection() as db:
            now = self._clock(db)
            expired = and_(s.jobs.c.status == "running", s.jobs.c.lease_until <= now)
            query = select(s.jobs).where(or_(s.jobs.c.status == "queued", expired)).order_by(
                s.jobs.c.created_at, s.jobs.c.id).limit(1).with_for_update(skip_locked=True)
            row = db.execute(query).mappings().first()
            if row is None:
                return None
            if row["attempt"] >= max_attempts:
                message = "El trabajo se interrumpió repetidamente. Revise el entorno antes de reintentar."
                db.execute(s.jobs.update().where(s.jobs.c.id == row["id"]).values(status="interrupted", error=message))
                db.execute(s.cases.update().where(s.cases.c.id == row["case_id"]).values(
                    status="interrupted", error=message, updated_at=utc_now()))
                return None
            token = str(uuid.uuid4())
            db.execute(s.jobs.update().where(s.jobs.c.id == row["id"]).values(
                status="running", owner=owner, token=token, lease_until=now + lease_seconds,
                attempt=row["attempt"] + 1, updated_at=utc_now()))
            db.execute(s.cases.update().where(s.cases.c.id == row["case_id"]).values(
                status="running", updated_at=utc_now()))
            return JobLease(row["id"], row["case_id"], owner, token, row["attempt"] + 1)

    def heartbeat(self, lease: JobLease, lease_seconds: int = 90) -> bool:
        with self.connection() as db:
            now = self._clock(db)
            result = db.execute(s.jobs.update().where(s.jobs.c.id == lease.id,
                s.jobs.c.token == lease.token, s.jobs.c.owner == lease.owner,
                s.jobs.c.status == "running", s.jobs.c.lease_until > now
            ).values(lease_until=now + lease_seconds, updated_at=utc_now()))
            return result.rowcount == 1

    def complete_job(self, lease: JobLease):
        with self.job_context(lease), self.connection() as db:
            status = db.scalar(select(s.cases.c.status).where(s.cases.c.id == lease.case_id))
            db.execute(s.jobs.update().where(s.jobs.c.id == lease.id).values(
                status="completed" if status == "ready" else "failed",
                lease_until=None, updated_at=utc_now()))
