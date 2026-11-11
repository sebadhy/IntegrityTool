"""Read-only validation of deployment configuration and existing services."""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path, PurePosixPath
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


def assistance_configuration_errors() -> list[str]:
    """Azure worker contract; never contact a provider or echo secret values."""
    errors = []
    for name, default in (("INTEGRITY_ASSISTED_ENABLED", "false"), ("INTEGRITY_SEMANTIC_ENABLED", "true")):
        if os.getenv(name, default).lower() not in {"true", "false"}:
            errors.append(f"{name} debe ser true o false.")
    if os.getenv("INTEGRITY_ASSISTED_ENABLED", "false").lower() != "true":
        return errors
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    portable = os.getenv("INTEGRITY_DEPLOYMENT_PROFILE") == "onprem"
    if portable and provider in {"openai", "groq", "ollama"}:
        required_key = {"openai": "OPENAI_API_KEY", "groq": "GROQ_API_KEY"}.get(provider)
        if required_key and not os.getenv(required_key, "").strip():
            errors.append(f"Configure {required_key} en el trabajador.")
        if provider == "openai" and os.getenv("OPENAI_BASE_URL") and not _https_endpoint(os.environ["OPENAI_BASE_URL"]):
            errors.append("OPENAI_BASE_URL requiere HTTPS.")
        if provider == "ollama":
            try:
                endpoint = urlsplit(os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"))
                if endpoint.scheme not in {"http", "https"} or not endpoint.hostname or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
                    raise ValueError()
            except ValueError:
                errors.append("Configure OLLAMA_BASE_URL como endpoint HTTP interno o HTTPS.")
    else:
        if provider != "azure":
            errors.append("Seleccione LLM_PROVIDER=azure para este ambiente." if not portable else "Seleccione LLM_PROVIDER=azure, openai, groq u ollama.")
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


def configuration_errors(role: str) -> list[str]:
    """Validate the shared storage contract without opening a connection."""
    errors = []
    profile = os.getenv("INTEGRITY_DEPLOYMENT_PROFILE", "azure")
    if profile not in {"azure", "onprem"}:
        return ["INTEGRITY_DEPLOYMENT_PROFILE debe ser azure o onprem."]
    if role == "api":
        from .web_access import web_configuration_errors
        if os.getenv("INTEGRITY_WEB_MODE") not in {"entra", "password"}:
            errors.append("La API institucional requiere INTEGRITY_WEB_MODE=entra o password.")
        errors.extend(web_configuration_errors())
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
    if profile == "onprem":
        if os.getenv("INTEGRITY_DOCUMENT_STORAGE") != "filesystem":
            errors.append("El perfil on-premise requiere INTEGRITY_DOCUMENT_STORAGE=filesystem.")
        # This profile describes an OCI Linux path, not the admin host's OS.
        path = PurePosixPath(os.getenv("INTEGRITY_DOCUMENTS_PATH", ""))
        if not os.getenv("INTEGRITY_DOCUMENTS_PATH") or not path.is_absolute():
            errors.append("Configure INTEGRITY_DOCUMENTS_PATH como ruta persistente absoluta.")
        if role == "worker":
            errors.extend(assistance_configuration_errors())
        return errors
    if os.getenv("INTEGRITY_DOCUMENT_STORAGE") != "azure":
        errors.append("Los originales compartidos requieren INTEGRITY_DOCUMENT_STORAGE=azure.")
    if not _https_endpoint(os.getenv("INTEGRITY_BLOB_ACCOUNT_URL", "")):
        errors.append("Configure INTEGRITY_BLOB_ACCOUNT_URL como endpoint HTTPS de la cuenta.")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{1,61})[a-z0-9]", os.getenv("INTEGRITY_BLOB_CONTAINER", "")):
        errors.append("Configure un nombre válido en INTEGRITY_BLOB_CONTAINER.")
    if os.getenv("INTEGRITY_ALLOW_STORAGE_EMULATOR", "false").lower() == "true":
        errors.append("El emulador no se admite en el perfil de despliegue compartido.")
    if role == "worker":
        errors.extend(assistance_configuration_errors())
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
        if hasattr(store.documents, "container"):
            store.documents.container.get_container_properties(timeout=10)
            results.append({"check": "blob_container", "ok": True})
        else:
            results.append({"check": "documents_directory", "ok": store.documents.root.is_dir() and os.access(store.documents.root, os.R_OK | os.W_OK)})
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
    from .runtime_secrets import load_secret_files
    load_secret_files()
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
        "model_calls": 0, "access_controls_configured": args.role == "api" and not errors,
        "deployment_validated": False,
        "notice": "La comprobación valida configuración y servicios solicitados, no el inicio de sesión real ni la aceptación del ambiente."},
        ensure_ascii=False, indent=2))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
