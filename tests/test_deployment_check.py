import json
from types import SimpleNamespace

import pytest

from src.deployment_check import configuration_errors, verify_services


@pytest.fixture
def shared_environment(tmp_path, monkeypatch):
    certificate = tmp_path / "ca.pem"
    certificate.write_text("Test file; not used to establish a connection.")
    values = {
        "INTEGRITY_WORKER_MODE": "external", "INTEGRITY_DOCUMENT_STORAGE": "azure",
        "INTEGRITY_DATABASE_URL": f"postgresql://user:test-secret@database.example.org/integrity?sslmode=verify-full&sslrootcert={certificate}",
        "INTEGRITY_BLOB_ACCOUNT_URL": "https://storage.blob.core.windows.net",
        "INTEGRITY_BLOB_CONTAINER": "integrity-documents", "INTEGRITY_ASSISTED_ENABLED": "false",
        "INTEGRITY_ALLOW_STORAGE_EMULATOR": "false",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_configuration_check_opens_no_connection_or_model(shared_environment, monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("Configuration check must not contact a service")
    monkeypatch.setattr("src.analyzer.storage_settings.create_review_store", unexpected)
    monkeypatch.setattr("src.analyzer.llm_reviewer._client", unexpected)
    assert configuration_errors("api") == []
    assert configuration_errors("worker") == []


def test_shared_profile_rejects_local_storage_and_redacts_dsn(shared_environment, monkeypatch):
    monkeypatch.setenv("INTEGRITY_DATABASE_URL", "postgresql://user:test-secret@database.example.org/db?sslmode=require")
    monkeypatch.setenv("INTEGRITY_DOCUMENT_STORAGE", "filesystem")
    monkeypatch.setenv("INTEGRITY_ALLOW_STORAGE_EMULATOR", "true")
    errors = configuration_errors("api")
    assert len(errors) >= 3
    assert "test-secret" not in json.dumps(errors)
    assert "database.example.org" not in json.dumps(errors)


def test_shared_profile_requires_ca_and_external_worker(shared_environment, monkeypatch):
    monkeypatch.setenv("INTEGRITY_DATABASE_URL", "postgresql://user:secret@database.example.org/db?sslmode=verify-full")
    monkeypatch.setenv("INTEGRITY_WORKER_MODE", "embedded")
    assert len(configuration_errors("api")) == 2


@pytest.mark.parametrize("endpoint", ["http://storage.example.org", "https://user:secret@storage.example.org",
    "https://storage.example.org/?sig=secret", "https://storage.example.org/#fragment", "http://[broken"])
def test_shared_profile_rejects_invalid_blob_endpoints(shared_environment, monkeypatch, endpoint):
    monkeypatch.setenv("INTEGRITY_BLOB_ACCOUNT_URL", endpoint)
    assert any("INTEGRITY_BLOB_ACCOUNT_URL" in message for message in configuration_errors("worker"))


def test_model_settings_only_required_when_enabled(shared_environment, monkeypatch):
    monkeypatch.setenv("INTEGRITY_ASSISTED_ENABLED", "true")
    monkeypatch.setenv("LLM_PROVIDER", "azure")
    for name in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_VERSION", "OPENAI_MODEL"):
        monkeypatch.delenv(name, raising=False)
    assert len(configuration_errors("worker")) == 4
    assert configuration_errors("api") == []


def test_service_check_reads_existing_resources_without_model_calls(shared_environment, monkeypatch):
    calls = []
    class Database:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def execute(self, statement):
            assert str(statement) == "SELECT 1"
            calls.append("database_read")
    class Store:
        documents = SimpleNamespace(container=SimpleNamespace(
            get_container_properties=lambda **kwargs: calls.append("container_read")))
        def connection(self):
            return Database()
        def close(self):
            calls.append("closed")
    def factory(root, initialize):
        assert initialize is False
        return Store()
    def unexpected(*args, **kwargs):
        raise AssertionError("Checks must not invoke a model")
    monkeypatch.setattr("src.analyzer.storage_settings.create_review_store", factory)
    monkeypatch.setattr("src.analyzer.llm_reviewer._client", unexpected)
    results = verify_services("api")
    assert all(result["ok"] for result in results)
    assert calls == ["database_read", "container_read", "closed"]


def test_service_failure_does_not_print_driver_details(shared_environment, monkeypatch):
    def unavailable(*args, **kwargs):
        raise RuntimeError("Driver failed with test-secret")
    monkeypatch.setattr("src.analyzer.storage_settings.create_review_store", unavailable)
    results = verify_services("api")
    assert not all(result["ok"] for result in results)
    assert "test-secret" not in json.dumps(results)


def test_worker_can_require_valid_corpus(shared_environment, monkeypatch):
    monkeypatch.setattr("src.analyzer.storage_settings.create_review_store", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("not connected")))
    monkeypatch.setattr("src.analyzer.pdf_extractor.check_tesseract_setup", lambda: {
        "tesseract_installed": True, "spanish_available": True})
    monkeypatch.setattr("src.analyzer.metadata_reader.read_process_metadata", lambda path: [])
    results = verify_services("worker", require_corpus=True)
    assert next(result for result in results if result["check"] == "ocr_spanish")["ok"]
    assert not next(result for result in results if result["check"] == "corpus")["ok"]


def test_container_entrypoint_preserves_loopback_binding(shared_environment, monkeypatch):
    from src import container_start
    commands = []
    monkeypatch.setattr("sys.argv", ["container_start", "api"])
    monkeypatch.setattr(container_start.os, "execv", lambda executable, args: commands.append(args))
    container_start.main()
    assert commands[0][commands[0].index("--host") + 1] == "127.0.0.1"
    assert "src.workbench_api:app" in commands[0]


def test_container_worker_uses_same_worker_command(shared_environment, monkeypatch):
    from src import container_start
    commands = []
    monkeypatch.setattr("sys.argv", ["container_start", "worker"])
    monkeypatch.setattr(container_start.os, "execv", lambda executable, args: commands.append(args))
    container_start.main()
    assert commands[0][1:] == ["-m", "src.review_worker"]


def test_preflight_ok_does_not_claim_publication_readiness(shared_environment, monkeypatch, capsys):
    from src import deployment_check
    monkeypatch.setattr("sys.argv", ["deployment_check", "--role", "api"])
    with pytest.raises(SystemExit) as result:
        deployment_check.main()
    assert result.value.code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] and output["model_calls"] == 0
    assert output["public_http_ready"] is False
    assert "test-secret" not in json.dumps(output)
