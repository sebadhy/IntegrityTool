import pytest

from src.runtime_secrets import load_secret_files


def test_mounted_secret_and_idempotent_loading(tmp_path, monkeypatch):
    path = tmp_path / "key"
    path.write_text("fixture-secret\n")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY_FILE", str(path))
    load_secret_files()
    load_secret_files()
    import os
    assert os.environ["OPENAI_API_KEY"] == "fixture-secret"


def test_conflicting_secret_fails_without_echo(tmp_path, monkeypatch):
    path = tmp_path / "key"
    path.write_text("different-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "current-secret")
    monkeypatch.setenv("OPENAI_API_KEY_FILE", str(path))
    with pytest.raises(ValueError) as error:
        load_secret_files()
    assert "current-secret" not in str(error.value) and "different-secret" not in str(error.value)


@pytest.mark.parametrize("content", ["", "a\nb", "x" * 16385])
def test_empty_multiline_or_oversized_secret_rejected(tmp_path, monkeypatch, content):
    path = tmp_path / "key"
    path.write_text(content)
    monkeypatch.setenv("OPENAI_API_KEY_FILE", str(path))
    with pytest.raises(ValueError):
        load_secret_files()
