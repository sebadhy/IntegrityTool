from pathlib import Path

import pytest
import yaml

from src.deployment_check import configuration_errors
from src.web_access import web_configuration_errors

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def onprem(tmp_path, monkeypatch):
    ca = tmp_path / "ca.crt"
    ca.write_text("fixture")
    for name, value in {
        "INTEGRITY_DEPLOYMENT_PROFILE": "onprem", "INTEGRITY_WEB_MODE": "password",
        "INTEGRITY_PUBLIC_ORIGIN": "https://integrity.example:8443", "INTEGRITY_ACCESS_POLICY": "shared_team",
        "INTEGRITY_WORKER_MODE": "external", "INTEGRITY_DOCUMENT_STORAGE": "filesystem",
        "INTEGRITY_DOCUMENTS_PATH": "/var/lib/integrity/documents",
        "INTEGRITY_DATABASE_URL": f"postgresql://owner:fixture-password@db/integrity?sslmode=verify-full&sslrootcert={ca}",
        "INTEGRITY_ASSISTED_ENABLED": "false",
    }.items():
        monkeypatch.setenv(name, value)
    for key in ("INTEGRITY_ENTRA_TENANT_ID", "INTEGRITY_ENTRA_CLIENT_ID", "INTEGRITY_BLOB_ACCOUNT_URL", "INTEGRITY_BLOB_CONTAINER"):
        monkeypatch.delenv(key, raising=False)


def test_portable_start_does_not_require_azure_resources(onprem):
    assert configuration_errors("api") == []
    assert configuration_errors("worker") == []


@pytest.mark.parametrize("provider", ["openai", "groq", "ollama"])
def test_portable_profile_preserves_other_existing_providers(onprem, monkeypatch, provider):
    monkeypatch.setenv("INTEGRITY_ASSISTED_ENABLED", "true")
    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-only")
    monkeypatch.setenv("GROQ_API_KEY", "fixture-only")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_VERSION", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    assert configuration_errors("worker") == []


def test_portable_start_keeps_database_tls_and_external_worker(onprem, monkeypatch):
    monkeypatch.setenv("INTEGRITY_DATABASE_URL", "postgresql://user:secret@db/integrity?sslmode=disable")
    monkeypatch.setenv("INTEGRITY_WORKER_MODE", "embedded")
    errors = configuration_errors("api")
    assert len(errors) >= 2 and "secret" not in str(errors)


@pytest.mark.parametrize("origin", ["http://integrity.example", "https://integrity.example/path",
    "https://integrity.example:443", "https://integrity.example:0", "https://user:pass@integrity.example", "https://integrity.example/"])
def test_portable_origin_must_be_exact_https(onprem, monkeypatch, origin):
    monkeypatch.setenv("INTEGRITY_PUBLIC_ORIGIN", origin)
    assert web_configuration_errors()


def test_compose_persists_documents_and_jobs_without_new_broker():
    config = yaml.safe_load((ROOT / "compose.yaml").read_text())
    services = config["services"]
    assert {"db", "api", "worker", "proxy", "admin", "storage-init"} == set(services)
    assert services["api"]["secrets"] == ["database_url", "db_ca"]
    for role in ("api", "worker"):
        service = services[role]
        assert service["user"] == "10001:10001"
        assert service["restart"] == "unless-stopped"
        assert service["read_only"] is True
        assert service["tmpfs"] == ["/tmp:rw,nosuid,nodev,size=512m"]
        assert "ports" not in service
        assert service["environment"]["INTEGRITY_ASSISTED_ENABLED"] == "false"
        assert "documents:/var/lib/integrity/documents" in service["volumes"]
    assert "ports" not in services["db"]
    overlay = yaml.safe_load((ROOT / "deploy/onprem/compose.azure-openai.yaml").read_text())
    assert set(overlay["services"]) == {"worker"}
    assert overlay["services"]["worker"]["secrets"] == ["model_key"]


def test_fixture_pdf_has_selectable_requirement():
    import importlib.util
    import pymupdf
    path = ROOT / "deploy/onprem/verify_installation.py"
    spec = importlib.util.spec_from_file_location("verify_onprem", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pymupdf.open(stream=module.fixture_pdf(), filetype="pdf") as document:
        assert "distribuidor autorizado exclusivo" in document[0].get_text()
