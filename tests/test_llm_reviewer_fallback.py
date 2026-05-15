from src.analyzer.llm_reviewer import extract_pliego_metadata_assisted


def test_assisted_metadata_without_api_key_does_not_raise(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    payload = extract_pliego_metadata_assisted("texto", {}, "primeras paginas")
    assert payload["llm_available"] is False
    assert payload["entidad_contratante"]["value"] == "No identificado"
