"""Read-only preparation checks. No provisioning, migration or model requests.

These checks do not authorize public HTTP access. The existing API intentionally
retains its local-only guard until the deployer integrates authenticated access.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]


def _https_endpoint(value: str) -> bool:
    try:
        endpoint = urlsplit(value)
        return bool(endpoint.scheme == "https" and endpoint.hostname and not endpoint.username
            and not endpoint.password and not endpoint.query and not endpoint.fragment)
    except ValueError:
        return False


def configuration_errors(role: str) -> list[str]:
    """Validate the shared storage contract without opening a connection."""
    errors = []
    if role == "api" and os.getenv("INTEGRITY_WORKER_MODE") != "external":
        errors.append("La API del contenedor requiere INTEGRITY_WORKER_MODE=external.")
    try:
        url = make_url(os.getenv("INTEGRITY_DATABASE_URL", ""))
        if (url.get_backend_name() != "postgresql" or not url.host or not url.database
                or url.query.get("sslmode") != "verify-full"):
            raise ValueError("Invalid database settings")
        certificate = url.query.get("sslrootcert")
        if not certificate or (certificate != "system" and not Path(certificate).is_file()):
            errors.append("PostgreSQL requiere una CA disponible mediante sslrootcert.")
    except Exception:
        # A driver URL may contain a password. Report only the configuration key.
        errors.append("Configure INTEGRITY_DATABASE_URL para PostgreSQL con sslmode=verify-full.")
    if os.getenv("INTEGRITY_DOCUMENT_STORAGE") != "azure":
        errors.append("Los originales compartidos requieren INTEGRITY_DOCUMENT_STORAGE=azure.")
    if not _https_endpoint(os.getenv("INTEGRITY_BLOB_ACCOUNT_URL", "")):
        errors.append("Configure INTEGRITY_BLOB_ACCOUNT_URL como endpoint HTTPS de la cuenta.")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{1,61})[a-z0-9]", os.getenv("INTEGRITY_BLOB_CONTAINER", "")):
        errors.append("Configure un nombre válido en INTEGRITY_BLOB_CONTAINER.")
    if os.getenv("INTEGRITY_ALLOW_STORAGE_EMULATOR", "false").lower() == "true":
        errors.append("El emulador no se admite en el perfil de despliegue compartido.")
    if role == "worker" and os.getenv("INTEGRITY_ASSISTED_ENABLED", "false").lower() == "true":
        if os.getenv("LLM_PROVIDER") != "azure":
            errors.append("Seleccione LLM_PROVIDER=azure para este ambiente.")
        for name in ("OPENAI_API_KEY", "OPENAI_API_VERSION", "OPENAI_MODEL"):
            if not os.getenv(name, "").strip():
                errors.append(f"Configure {name} en el trabajador.")
        if not _https_endpoint(os.getenv("OPENAI_BASE_URL", "")):
            errors.append("OPENAI_BASE_URL debe ser el endpoint HTTPS del recurso Azure OpenAI.")
        try:
            if not 0 <= int(os.getenv("INTEGRITY_LLM_MAX_CALLS", "2")) <= 3:
                raise ValueError("Invalid budget")
        except ValueError:
            errors.append("INTEGRITY_LLM_MAX_CALLS debe estar entre 0 y 3.")
    return errors


def verify_services(role: str, root: Path = ROOT, *, require_corpus=False) -> list[dict]:
    """Read schema/container properties; never upload documents or call a model."""
    from .analyzer.storage_settings import create_review_store
    from .analyzer.taxonomy_loader import load_taxonomy
    taxonomy = load_taxonomy()
    results = [{"check": "taxonomy", "ok": bool(taxonomy.loaded and taxonomy.patterns and taxonomy.source_sha256)}]
    store = None
    try:
        store = create_review_store(root, initialize=False)
        with store.connection() as db:
            from sqlalchemy import text
            db.execute(text("SELECT 1"))
        results.append({"check": "database_schema", "ok": True})
        store.documents.container.get_container_properties(timeout=10)
        results.append({"check": "blob_container", "ok": True})
    except Exception:
        results.append({"check": "storage", "ok": False,
            "message": "Compruebe red, identidad, permisos, esquema y contenedor privado."})
    finally:
        if store is not None:
            store.close()
    if role == "worker":
        from .analyzer.pdf_extractor import check_tesseract_setup
        ocr = check_tesseract_setup()
        results.append({"check": "ocr_spanish", "ok": bool(ocr.get("tesseract_installed") and ocr.get("spanish_available"))})
        if require_corpus:
            from .analyzer.corpus_validator import validate_corpus
            from .analyzer.metadata_reader import read_process_metadata
            from .config import APP_CORPUS_METADATA_PATH, APP_CORPUS_PLIEGOS_DIR, APP_CORPUS_ESPECIFICACIONES_DIR
            try:
                rows = read_process_metadata(APP_CORPUS_METADATA_PATH)
                validation = validate_corpus(rows, {"pliego": APP_CORPUS_PLIEGOS_DIR,
                    "especificaciones": APP_CORPUS_ESPECIFICACIONES_DIR})
                valid = bool(rows) and not validation["has_critical_errors"]
            except Exception:
                valid = False
            results.append({"check": "corpus", "ok": valid})
    return results


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Comprobar datos y configuración sin analizar PDFs ni consultar modelos.")
    parser.add_argument("--role", choices=["api", "worker"], required=True)
    parser.add_argument("--check-services", action="store_true", help="Consultar esquema, contenedor y OCR; no crear recursos.")
    parser.add_argument("--require-corpus", action="store_true", help="Exigir corpus válido en el trabajador.")
    args = parser.parse_args()
    if args.require_corpus and (args.role != "worker" or not args.check_services):
        parser.error("--require-corpus requiere --role worker y --check-services.")
    errors = configuration_errors(args.role)
    results = verify_services(args.role, require_corpus=args.require_corpus) if args.check_services and not errors else []
    ok = not errors and all(result["ok"] for result in results)
    print(json.dumps({"ok": ok, "role": args.role, "errors": errors, "checks": results,
        "model_calls": 0, "public_http_ready": False,
        "notice": "La API conserva el acceso local. Integrar autenticación, autorización y dominios antes de publicar HTTP. Esta comprobación no valida esos controles."},
        ensure_ascii=False, indent=2))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
