import json

import pytest

from src.assistance_check import check_assistance
from src.deployment_check import assistance_configuration_errors


@pytest.fixture
def azure_model(monkeypatch):
    for key, value in {
        "INTEGRITY_ASSISTED_ENABLED": "true", "INTEGRITY_SEMANTIC_ENABLED": "true",
        "INTEGRITY_LLM_MAX_CALLS": "2", "LLM_PROVIDER": "azure",
        "OPENAI_API_KEY": "test-secret-not-a-real-key", "OPENAI_MODEL": "test-deployment",
        "OPENAI_API_VERSION": "test-version", "OPENAI_BASE_URL": "https://example.openai.azure.com/",
    }.items():
        monkeypatch.setenv(key, value)


def test_configuration_only_never_calls_model(azure_model, monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("No implicit calls")
    monkeypatch.setattr("src.analyzer.llm_reviewer._request_json", unexpected)
    result = check_assistance()
    assert result["ok"] and result["configuration_only"]
    assert result["model_calls"] == 0
    assert "test-secret" not in json.dumps(result)


def test_explicit_probe_uses_actual_schemas_and_only_synthetic_content(azure_model, monkeypatch):
    from src.analyzer.llm_reviewer import DOCUMENT_BRIEF_SCHEMA, SEMANTIC_SCHEMA
    calls = []
    def request(prompt, schema):
        calls.append((prompt, schema))
        return {}, {"provider": "Azure OpenAI", "model": "test-deployment", "input_tokens": 10}
    monkeypatch.setattr("src.analyzer.llm_reviewer._request_json", request)
    result = check_assistance(request_model=True)
    assert result["ok"] and result["model_calls"] == 2
    assert [entry[1] for entry in calls] == [SEMANTIC_SCHEMA, DOCUMENT_BRIEF_SCHEMA]
    assert all("ficticio" in entry[0] for entry in calls)
    assert "test-secret" not in json.dumps(result)


def test_probe_failure_is_redacted_and_not_retried(azure_model, monkeypatch):
    calls = []
    def request(*args):
        calls.append(True)
        raise RuntimeError("test-secret-not-a-real-key")
    monkeypatch.setattr("src.analyzer.llm_reviewer._request_json", request)
    result = check_assistance(request_model=True)
    assert not result["ok"] and result["model_calls"] == 1
    assert len(calls) == 1 and "test-secret" not in json.dumps(result)


@pytest.mark.parametrize("key,value", [
    ("INTEGRITY_ASSISTED_ENABLED", "yes"), ("INTEGRITY_SEMANTIC_ENABLED", "tru"),
    ("INTEGRITY_LLM_MAX_CALLS", "4"), ("INTEGRITY_LLM_MAX_CALLS", "many"),
    ("LLM_PROVIDER", "openai"), ("OPENAI_API_KEY", ""),
    ("OPENAI_BASE_URL", "http://example.org/"),
])
def test_invalid_configuration_blocks_probe(azure_model, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    assert assistance_configuration_errors()
    result = check_assistance(request_model=True)
    assert not result["ok"] and result["model_calls"] == 0


@pytest.mark.parametrize("key,value", [("INTEGRITY_ASSISTED_ENABLED", "false"), ("INTEGRITY_LLM_MAX_CALLS", "0")])
def test_disabled_model_cannot_be_called_by_probe(azure_model, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    result = check_assistance(request_model=True)
    assert not result["ok"] and result["model_calls"] == 0


def test_cli_is_offline_by_default(azure_model, monkeypatch, capsys):
    from src import assistance_check
    monkeypatch.setattr("sys.argv", ["assistance_check"])
    with pytest.raises(SystemExit) as stopped:
        assistance_check.main()
    result = json.loads(capsys.readouterr().out)
    assert stopped.value.code == 0 and result["model_calls"] == 0
