"""One explicit selection of database and document storage; no cloud fallback."""
from __future__ import annotations

import os
from pathlib import Path

from .document_storage import AzureDocumentStorage, FileDocumentStorage
from .review_store import ReviewStore


def create_review_store(root: Path, storage: Path | str | None = None, *, initialize=None) -> ReviewStore:
    # Explicit paths (including tests) are isolated from developer cloud settings.
    explicit_local = storage is not None and "://" not in str(storage)
    database = storage if storage is not None else (
        os.getenv("INTEGRITY_DATABASE_URL") or os.getenv("INTEGRITY_STORE_PATH")
        or root / "data/workbench/reviews.sqlite3")
    postgres = str(database).startswith(("postgresql://", "postgresql+psycopg://"))
    backend = "filesystem" if explicit_local else os.getenv("INTEGRITY_DOCUMENT_STORAGE", "azure" if postgres else "filesystem")
    if backend == "azure":
        container = os.getenv("INTEGRITY_BLOB_CONTAINER", "")
        if not container:
            raise ValueError("Configure INTEGRITY_BLOB_CONTAINER para los originales.")
        documents = AzureDocumentStorage(
            account_url=os.getenv("INTEGRITY_BLOB_ACCOUNT_URL", ""),
            connection_string=os.getenv("INTEGRITY_BLOB_CONNECTION_STRING", ""),
            container=container,
            allow_emulator=os.getenv("INTEGRITY_ALLOW_STORAGE_EMULATOR", "false").lower() == "true")
    elif backend == "filesystem":
        if explicit_local:
            directory = Path(storage).resolve().parent / "documents"
        else:
            directory = Path(os.getenv("INTEGRITY_DOCUMENTS_PATH", root / "data/workbench/documents"))
            if postgres and not os.getenv("INTEGRITY_DOCUMENTS_PATH"):
                raise ValueError("PostgreSQL con archivos locales requiere INTEGRITY_DOCUMENTS_PATH explícita.")
        documents = FileDocumentStorage(directory)
    else:
        raise ValueError("Seleccione filesystem o azure como almacenamiento documental.")
    try:
        return ReviewStore(database, document_storage=documents, initialize=initialize)
    except Exception:
        close = getattr(documents, "close", None)
        if close:
            close()
        raise
