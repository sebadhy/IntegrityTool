import fitz
import pytest
import streamlit as st

from streamlit.testing.v1 import AppTest

from src.analyzer.taxonomy_loader import TaxonomyLoadResult


@pytest.fixture(autouse=True)
def isolated_view_cache():
    st.cache_data.clear()
    yield
    st.cache_data.clear()


def _pdf():
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((36, 50), "Debe ser distribuidor autorizado exclusivo del fabricante X.")
        return document.tobytes()


def _processed_app(monkeypatch):
    monkeypatch.setattr("src.analyzer.llm_reviewer._llm_available", lambda: False)
    app = AppTest.from_file("app.py", default_timeout=30)
    app.session_state["document_processed"] = True
    app.session_state["uploaded_file_bytes"] = _pdf()
    app.session_state["uploaded_file_name"] = "prueba.pdf"
    app.session_state["use_historical_corpus"] = False
    app.session_state["enable_ai_reading"] = False
    return app


def test_streamlit_renders_an_exportable_review_without_llm(monkeypatch):
    app = _processed_app(monkeypatch).run()
    assert not app.exception
    assert app.get("download_button")


def test_streamlit_reports_missing_taxonomy_instead_of_an_empty_success(monkeypatch):
    monkeypatch.setattr("src.analyzer.review_pipeline.load_taxonomy", lambda: TaxonomyLoadResult([], ["No disponible"], False))
    app = _processed_app(monkeypatch).run()
    assert not app.exception
    assert any("taxonomía" in error.value for error in app.error)
    assert not app.get("download_button")


def test_streamlit_does_not_blame_the_pdf_for_a_rule_engine_failure(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("Error de motor de prueba")

    monkeypatch.setattr("src.analyzer.review_pipeline.analyze_document_bytes", fail)
    app = _processed_app(monkeypatch).run()
    assert not app.exception
    assert any("error de análisis" in error.value for error in app.error)
    assert not any("archivo sea válido" in error.value for error in app.error)


def test_audit_timestamp_does_not_repeat_a_cached_model_explanation(monkeypatch):
    calls = []

    def explain(*args, **kwargs):
        calls.append(True)
        return {"plain_language_explanation": "Conviene validar este requisito.", "why_it_matters": "Se conserva la evidencia documental."}

    monkeypatch.setattr("src.analyzer.llm_reviewer.explain_priority_with_llm", explain)
    app = _processed_app(monkeypatch)
    app.session_state["enable_ai_reading"] = True
    monkeypatch.setattr("src.analyzer.llm_reviewer._llm_available", lambda: True)
    monkeypatch.setattr("src.analyzer.llm_reviewer.generate_document_brief", lambda *args: {"llm_available": False})
    app.run()
    assert not app.exception
    initial_calls = len(calls)
    assert initial_calls > 0
    app.selectbox(key="original_pdf_zoom_label").select("Muy grande").run()
    assert not app.exception
    assert len(calls) == initial_calls


def test_streamlit_navigation_reuses_analysis_without_reprocessing(monkeypatch):
    from src.analyzer.review_pipeline import analyze_document_bytes
    calls = []
    def analyze(*args, **kwargs):
        calls.append(True)
        return analyze_document_bytes(*args, **kwargs)
    monkeypatch.setattr("src.analyzer.review_pipeline.analyze_document_bytes", analyze)
    app = _processed_app(monkeypatch).run()
    assert not app.exception
    app.selectbox(key="original_pdf_zoom_label").select("Muy grande").run()
    assert not app.exception
    assert len(calls) == 1
