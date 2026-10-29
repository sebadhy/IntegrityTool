import hashlib
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pymupdf as fitz
import pytest

from src.analyzer.case_review import consolidate_case
from src.analyzer.review_pipeline import analyze_document_bytes, analyze_document_pages
from src.analyzer.review_store import ReviewStore
from src.analyzer.workbench_service import WorkbenchService
from src.analyzer.taxonomy_loader import load_taxonomy


def pdf(text="Debe ser distribuidor autorizado exclusivo del fabricante X."):
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_textbox(fitz.Rect(35, 35, 560, 800), text, fontsize=12)
        return doc.tobytes()


@pytest.fixture
def service(tmp_path):
    instance = WorkbenchService(Path.cwd(), tmp_path / "reviews.sqlite3", assisted=False,
                                corpus_provider=lambda hashes: ({}, {"snapshot": "test", "total_processes": 0}))
    yield instance
    instance.close()


def wait_for_case(service, case_id):
    for _ in range(200):
        case = service.store.get_case(case_id)
        if case["status"] in {"ready", "failed"} and case_id not in service.pending:
            return case
        time.sleep(.03)
    raise AssertionError("review did not finish")


def create(service, files=None, key="request-1"):
    case = service.create("Prueba institucional", key, files or [{"name": "pliego.pdf", "content": pdf(), "role": "pliego"}])
    return wait_for_case(service, case["id"])


def test_shared_engine_returns_identical_signal_ids_for_upload_and_corpus_pages():
    content = pdf()
    first = analyze_document_bytes(content, {}, 0, "test.pdf")
    digest = hashlib.sha256(content).hexdigest()
    second = analyze_document_pages(first.pages, {}, "doc-" + digest, "corpus.pdf")
    assert [s.signal_id for s in first.signals] == [s.signal_id for s in second.signals]
    assert [i.title for i in first.review_items] == [i.title for i in second.review_items]


def test_structured_metadata_requires_matching_content_when_hash_is_supplied(tmp_path):
    from src.analyzer.metadata_extractor import document_metadata_from_name
    metadata = tmp_path / "data/raw/metadata/procesos.csv"
    metadata.parent.mkdir(parents=True)
    metadata.write_text("process_id;entidad;pliego_file\nSIE-TEST;Hospital de prueba;test.pdf\n", encoding="utf-8")
    path = tmp_path / "data/raw/pliegos/test.pdf"
    path.parent.mkdir(parents=True)
    content = pdf()
    path.write_bytes(content)
    assert document_metadata_from_name("test.pdf", tmp_path, "wrong-sha")["entidad"] != "Hospital de prueba"
    assert document_metadata_from_name("test.pdf", tmp_path, hashlib.sha256(content).hexdigest())["entidad"] == "Hospital de prueba"


def test_mitigant_in_another_requirement_does_not_neutralize_exclusivity():
    from src.analyzer.pdf_extractor import PageText
    restrictive = "Debe ser distribuidor autorizado exclusivo del fabricante X."
    permissive = "Se solicita marca especifica ACME o equivalente funcional verificable."
    first = analyze_document_pages([PageText(1, restrictive)], {}, "doc-test", "test.pdf")
    mixed = analyze_document_pages([PageText(1, restrictive), PageText(2, permissive)], {}, "doc-test", "test.pdf")
    assert first.review_items[0].review_priority == "alta"
    assert mixed.review_items[0].review_priority == "alta"
    assert len(mixed.review_items) == 1


def test_mandatory_calendar_reference_without_interval_is_not_a_short_deadline():
    from src.analyzer.pdf_extractor import PageText
    result = analyze_document_pages([PageText(1, "La presentacion de ofertas debera realizarse conforme al cronograma del procedimiento.")], {}, "doc-test", "test.pdf")
    assert not any(item.metadata["pattern_id"] == "cn-short-submission-deadline" for item in result.review_items)


def test_frequent_mitigated_requirement_is_context_not_a_main_observation():
    from src.analyzer.pdf_extractor import PageText
    context = {"cn-specific-certification": {"rarity": "Habitual", "frequency_label": "24 de 24 procesos", "frequency": 1}}
    result = analyze_document_pages([PageText(1, "ESPECIFICACIONES TECNICAS. Se requiere certificado BPM o su equivalente para asegurar la calidad del bien.")], context, "doc-test", "test.pdf")
    assert not any(item.metadata["pattern_id"] == "cn-specific-certification" for item in result.review_items)


def test_service_persists_result_and_reuses_versioned_analysis(service, monkeypatch):
    content = pdf()
    case = create(service, [{"name": "first.pdf", "content": content}])
    assert case["status"] == "ready"
    def unexpected(*args, **kwargs):
        raise AssertionError("analysis executed twice")
    monkeypatch.setattr("src.analyzer.workbench_service.analyze_document_bytes", unexpected)
    second = create(service, [{"name": "renamed.pdf", "content": content}], key="request-2")
    assert second["status"] == "ready"
    assert second["result"]["documents"][0]["cache_hit"] is True
    reopened = ReviewStore(service.store.path).get_case(case["id"])
    assert reopened["result"]["items"] == case["result"]["items"]


def test_taxonomy_change_invalidates_analysis_cache(service, monkeypatch, tmp_path):
    content = pdf()
    first = create(service, [{"name": "test.pdf", "content": content}])
    path = tmp_path / "rules.yaml"
    path.write_text(load_taxonomy().source_text + "\n# A new reviewed revision\n", encoding="utf-8")
    snapshot = load_taxonomy(path)
    monkeypatch.setattr("src.analyzer.workbench_service.load_taxonomy", lambda: snapshot)
    second = create(service, [{"name": "test.pdf", "content": content}], "request-2")
    assert first["result"]["documents"][0]["analysis"]["analysis_key"] != second["result"]["documents"][0]["analysis"]["analysis_key"]
    assert second["result"]["documents"][0]["cache_hit"] is False


def test_case_freezes_taxonomy_across_documents_and_archives_exact_source(service, monkeypatch, tmp_path):
    snapshot = load_taxonomy()
    modified_path = tmp_path / "modified.yaml"
    modified_path.write_text(snapshot.source_text + "\n# Later edit\n", encoding="utf-8")
    later = load_taxonomy(modified_path)
    calls = []

    def frozen_analysis(*args, **kwargs):
        calls.append(kwargs["taxonomy_snapshot"])
        # Simulate the file changing after the first document is analyzed.
        monkeypatch.setattr("src.analyzer.workbench_service.load_taxonomy", lambda: later)
        return analyze_document_bytes(*args, **kwargs)

    monkeypatch.setattr("src.analyzer.workbench_service.load_taxonomy", lambda: snapshot)
    monkeypatch.setattr("src.analyzer.workbench_service.analyze_document_bytes", frozen_analysis)
    case = create(service, [
        {"name": "first.pdf", "content": pdf()},
        {"name": "second.pdf", "content": pdf("Debe ser distribuidor autorizado exclusivo del fabricante X para los equipos.")},
    ])
    assert case["status"] == "ready"
    assert calls == [snapshot, snapshot]
    assert case["result"]["provenance"]["taxonomy_sha256"] == snapshot.source_sha256
    assert case["result"]["provenance"]["taxonomy_archived"] is True
    assert all(doc["analysis"]["provenance"]["taxonomy_sha256"] == snapshot.source_sha256
               for doc in case["result"]["documents"])
    reopened = ReviewStore(service.store.path)
    assert reopened.get_taxonomy(snapshot.source_sha256) == snapshot.source_text
    assert reopened.get_taxonomy(later.source_sha256) is None


def test_taxonomy_snapshot_hash_cannot_be_fabricated(service):
    with pytest.raises(ValueError):
        service.store.save_taxonomy("unverified", "patterns: []")


def test_missing_taxonomy_fails_explicitly_without_claiming_success(service, monkeypatch, tmp_path):
    monkeypatch.setattr("src.analyzer.workbench_service.load_taxonomy", lambda: load_taxonomy(tmp_path / "missing.yaml"))
    case = create(service)
    assert case["status"] == "failed"
    assert "reglas" in case["error"]
    assert not case.get("result")


def test_taxonomy_snapshot_retains_exact_utf8_bytes(tmp_path):
    path = tmp_path / "taxonomy.yaml"
    source = b"\xef\xbb\xbf" + load_taxonomy().source_text.lstrip("\ufeff").encode("utf-8")
    path.write_bytes(source)
    snapshot = load_taxonomy(path)
    assert snapshot.loaded
    assert snapshot.source_text.encode("utf-8") == source
    assert snapshot.source_sha256 == hashlib.sha256(source).hexdigest()


def test_llm_context_uses_archived_pattern_not_live_taxonomy(service, monkeypatch):
    from src.analyzer.llm_reviewer import _build_finding_prompt
    from src.analyzer.workbench_service import _llm_row
    case = create(service)
    item = case["result"]["items"][0]
    context = case["result"]["taxonomy_context"]
    context[item["pattern_id"]]["description"] = "Descripción congelada para esta revisión"
    def unexpected():
        raise AssertionError("Live taxonomy must not be read for an archived review")
    monkeypatch.setattr("src.analyzer.llm_reviewer.load_taxonomy", unexpected)
    prompt = _build_finding_prompt(_llm_row(item, context), {})
    assert "Descripción congelada para esta revisión" in prompt


def test_case_consolidates_across_documents_without_losing_evidence(service):
    case = create(service, [
        {"name": "pliego.pdf", "role": "pliego", "content": pdf()},
        {"name": "especificaciones.pdf", "role": "especificaciones", "content": pdf("Debe ser distribuidor autorizado exclusivo del fabricante X para estos equipos.")},
    ])
    items = [item for item in case["result"]["items"] if item["pattern_id"] == "cn-brand-model-provider-reference"]
    assert len(items) == 1
    assert len({ev["document_id"] for ev in items[0]["evidence"]}) == 2
    assert len(items[0]["evidence"]) == 2
    assert all(ev["rects"] for ev in items[0]["evidence"])


def test_explicit_supersession_excludes_old_requirement_and_keeps_contrast(service):
    case = create(service, [
        {"name": "v1.pdf", "content": pdf(), "role": "pliego", "version": "1"},
        {"name": "v2.pdf", "content": pdf("No se requiere distribuidor autorizado ni certificacion ISO 9001 para participar."), "role": "pliego", "version": "2", "supersedes_index": 0},
    ])
    assert case["status"] == "ready"
    assert case["result"]["items"] == []
    assert case["result"]["version_changes"]
    assert "no identificada" in case["result"]["version_changes"][0]["change"].lower()


def test_documents_are_not_implicitly_superseded_by_filename(service):
    case = create(service, [
        {"name": "pliego-antiguo.pdf", "content": pdf()},
        {"name": "pliego-final-v99.pdf", "content": pdf("No se requiere distribuidor autorizado para participar.")},
    ])
    assert case["result"]["items"]
    assert case["result"]["version_changes"] == []


def version_pair(before, after):
    def document(identity, references, supersedes=None):
        return {"id": identity, "name": identity + ".pdf", "version": identity,
                "supersedes": supersedes, "analysis": {"items": [{
                    "metadata": {"pattern_id": "cn-specific-certification"},
                    "title": "Certificación específica", "competition_dimension": "proporcionalidad",
                    "evidence_summary": references[0][1],
                    "evidence_items": [{"page": page, "text": text} for page, text in references],
                }]}}
    return [document("1", before), document("2", after, "1")]


def test_version_comparison_includes_changes_outside_representative_excerpt():
    from src.analyzer.case_review import compare_document_versions
    shared = "Se exige certificado ISO 9001."
    removed = "El certificado solo sera emitido por el fabricante X."
    added = "Se admiten certificaciones equivalentes."
    changes = compare_document_versions(version_pair([(1, shared), (2, removed)], [(1, shared), (2, added)]))
    assert len(changes) == 1
    assert changes[0]["removed_evidence"][0]["text"] == removed
    assert changes[0]["added_evidence"][0]["text"] == added
    assert changes[0]["unchanged_reference_count"] == 1
    assert len(changes[0]["previous_evidence"]) == 2


def test_version_comparison_does_not_treat_page_moves_or_repetition_as_text_changes():
    from src.analyzer.case_review import compare_document_versions
    requirement = "Se exige certificado ISO 9001."
    changes = compare_document_versions(version_pair([(1, requirement)], [(5, requirement), (7, requirement)]))
    assert changes == []


def test_version_comparison_detects_removed_secondary_requirement():
    from src.analyzer.case_review import compare_document_versions
    main = "Se exige certificado ISO 9001."
    removed = "Debe incluir certificacion del fabricante X."
    changes = compare_document_versions(version_pair([(1, main), (2, removed)], [(1, main)]))
    assert len(changes) == 1
    assert not changes[0]["added_evidence"]
    assert changes[0]["removed_evidence"][0]["text"] == removed


def test_schedule_detector_respects_frozen_catalogue(monkeypatch):
    from dataclasses import replace
    from src.analyzer.domain_models import Clause
    from src.analyzer.schedule_analyzer import detect_schedule_signals
    text = "CRONOGRAMA. Fecha de publicacion: 01/08/2026. Presentacion de ofertas: 03/08/2026."
    clauses = [Clause("clause-1", "doc-test", 1, "CRONOGRAMA", "schedule", text, text.lower())]
    patterns = [replace(pattern, name="Nombre de la copia utilizada") for pattern in load_taxonomy().patterns
                if pattern.id == "cn-short-submission-deadline"]
    def unexpected():
        raise AssertionError("Schedule detector must use the supplied catalogue")
    monkeypatch.setattr("src.analyzer.schedule_analyzer.load_taxonomy", unexpected)
    signals = detect_schedule_signals(clauses, patterns)
    assert signals
    assert signals[0].metadata["taxonomy_pattern"]["name"] == "Nombre de la copia utilizada"
    assert not detect_schedule_signals(clauses, [])


def test_partial_pdf_match_is_not_labeled_as_complete_excerpt():
    from src.analyzer.workbench_service import _attach_evidence_coordinates
    original = "Se requiere un certificado especifico para los equipos. " * 9
    content = pdf(original)
    analysis = {"items": [{"evidence_items": [{"page": 1, "text": original + "Texto que no existe en la pagina."}]}]}
    _attach_evidence_coordinates(analysis, content)
    evidence = analysis["items"][0]["evidence_items"][0]
    assert evidence["rects"]
    assert evidence["location_precision"] == "excerpt_prefix"


def test_duplicate_pdf_content_is_rejected(service):
    content = pdf()
    with pytest.raises(ValueError, match="idénticos"):
        create(service, [{"name": "a.pdf", "content": content}, {"name": "b.pdf", "content": content}])


def test_idempotent_creation_does_not_duplicate_cases(service):
    first = create(service)
    second = create(service)
    assert second["id"] == first["id"]
    assert len(service.store.list_cases()) == 1


def test_review_state_and_comment_have_transactional_history(service):
    case = create(service)
    item_id = case["result"]["items"][0]["id"]
    service.store.save_review(case["id"], item_id, "followup", "Validar equivalencias", "Revisor local")
    service.store.save_review(case["id"], item_id, "confirmed", "Validación registrada", "Revisor local")
    assert service.store.get_case(case["id"])["reviews"][item_id]["state"] == "confirmed"
    assert len(service.store.events(case["id"])) == 2


def test_failed_narration_does_not_remove_deterministic_review(service, monkeypatch):
    service.assisted = True
    monkeypatch.setattr(service, "_narrate", lambda *args: (_ for _ in ()).throw(RuntimeError("provider unavailable")))
    case = create(service)
    assert case["status"] == "ready"
    assert case["result"]["items"]
    assert case["result"]["assistance"]["status"] == "unavailable"


def test_llm_is_bounded_cached_and_does_not_change_priority(service, monkeypatch):
    calls = []
    monkeypatch.setattr("src.analyzer.llm_reviewer._llm_available", lambda: True)
    monkeypatch.setattr("src.analyzer.llm_reviewer.generate_document_brief", lambda *args: calls.append("summary") or {"llm_available": True, "document_summary": "Conviene validar las equivalencias."})
    monkeypatch.setattr("src.analyzer.llm_reviewer.explain_priority_with_llm", lambda *args: calls.append("explanation") or {"llm_available": True, "plain_language_explanation": "Revisar la justificación técnica."})
    monkeypatch.setenv("INTEGRITY_LLM_MAX_CALLS", "2")
    service.assisted = True
    content = pdf()
    first = create(service, [{"name": "a.pdf", "content": content}])
    second = create(service, [{"name": "b.pdf", "content": content}], "request-2")
    assert calls == ["summary", "explanation"]
    assert all(record["cached"] for record in second["result"]["assistance"]["calls"])
    assert first["result"]["items"][0]["priority"] == second["result"]["items"][0]["priority"]
    assert first["result"]["assisted_summary"]


def test_invalid_or_empty_pdf_does_not_return_success(service):
    with pytest.raises(ValueError, match="PDF"):
        create(service, [{"name": "a.pdf", "content": b"not a pdf"}])
    case = create(service, [{"name": "empty.pdf", "content": pdf("")}])
    assert case["status"] == "failed"
    assert "extraer texto" in case["error"]


def test_application_restart_marks_pending_review_interrupted(tmp_path):
    store = ReviewStore(tmp_path / "test.sqlite3")
    store.create_case("case-1", "request-1", "Test", [])
    store.interrupt_unfinished()
    assert store.get_case("case-1")["status"] == "interrupted"


def test_prompts_use_only_relevant_taxonomy_and_bounded_document_text():
    from src.analyzer.llm_reviewer import _build_document_brief_prompt, _build_finding_prompt
    item = {"pattern_id": "cn-specific-certification", "fragmento textual": "Se requiere certificación ISO 9001."}
    prompt = _build_finding_prompt(item, {})
    assert "cn-specific-certification" in prompt
    assert "cn-medical-device-platform-lock-in" not in prompt
    assert len(prompt) < 16000
    brief = _build_document_brief_prompt("A" * 100000, [item], {}, None)
    assert len(brief) < 22000
    assert "A" * 1000 not in brief


def test_llm_rejects_truncated_or_prohibited_responses(monkeypatch):
    from src.analyzer import llm_reviewer as llm
    response = SimpleNamespace(choices=[SimpleNamespace(finish_reason="length", message=SimpleNamespace(content='{}', refusal=None))])
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: response)))
    monkeypatch.setattr(llm, "_client", lambda: SimpleNamespace(with_options=lambda **kwargs: fake))
    with pytest.raises(ValueError, match="completó"):
        llm._request_json("Texto", {})
    response.choices[0].finish_reason = "stop"
    response.choices[0].message.content = json.dumps({"text": "fraude"})
    with pytest.raises(ValueError, match="lenguaje"):
        llm._request_json("Texto", {})


def test_llm_rate_limit_does_not_trigger_hidden_retries(monkeypatch):
    from src.analyzer import llm_reviewer as llm
    calls = []
    def fail(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("429 rate_limit")
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fail)))
    options = []
    def configure(**kwargs):
        options.append(kwargs)
        return fake
    monkeypatch.setattr(llm, "_client", lambda: SimpleNamespace(with_options=configure))
    with pytest.raises(RuntimeError, match="429"):
        llm._request_json("Texto de prueba", {})
    assert len(calls) == 1
    assert options == [{"timeout": llm.REQUEST_TIMEOUT, "max_retries": 0}]


def test_groq_provider_uses_the_existing_openai_client(monkeypatch):
    import openai
    from src.analyzer import llm_reviewer as llm
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-a-secret")
    parameters = []
    fake = object()
    def client(**kwargs):
        parameters.append(kwargs)
        return fake
    monkeypatch.setattr(openai, "OpenAI", client)
    assert llm._client() is fake
    assert parameters == [{"api_key": "test-key-not-a-secret", "base_url": "https://api.groq.com/openai/v1"}]
