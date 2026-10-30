"""Contract and evidence tests, not a benchmark of institutional accuracy."""
import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from src.analyzer.contextualizer import build_finding_candidates
from src.analyzer.domain_models import Clause
from src.analyzer.review_pipeline import analyze_document_pages, finalize_candidates
from src.analyzer.pdf_extractor import PageText
from src.analyzer.review_store import ReviewStore
from src.analyzer.semantic_analyzer import select_semantic_context, validate_semantic_proposals
from src.analyzer.taxonomy_loader import load_taxonomy
from src.analyzer.workbench_service import WorkbenchService
from test_workbench import pdf, wait_for_case

TEXT = ("Para recibir la oferta es indispensable adjuntar una constancia emitida por la casa "
        "que produjo el equipo, y no se admitirán documentos expedidos por otras entidades.")
PATTERN = "cn-brand-model-provider-reference"


def clause(text=TEXT, identity="clause-1", page=1, **kwargs):
    return Clause(identity, "doc-test", page, "Condiciones", "qualification", text, text.lower(), **kwargs)


def document(clauses, identity="document-1", **kwargs):
    return {"id": identity, "name": identity + ".pdf", "role": "pliego", "version": "1",
            "analysis": {"clauses": [asdict(c) for c in clauses]}, **kwargs}


def selection(clauses=None):
    return select_semantic_context([document(clauses or [clause()])], load_taxonomy())


def proposal(source=None, **kwargs):
    source = source or clause()
    return {"pattern_id": PATTERN, "clause_id": source.clause_id, "quote": source.text,
            "review_note": "Convendría verificar si se admiten otras formas de acreditar el respaldo del equipo.",
            "confidence": "medium", **kwargs}


def test_selection_excludes_templates_superseded_and_keeps_exact_clauses():
    active = clause()
    excluded = clause("Sin datos", "empty", clause_status="empty_or_no_data", exclude_from_detection=True)
    docs = [document([clause(identity="old")], "old"),
            document([active, excluded], "new", supersedes="old")]
    chosen = select_semantic_context(docs, load_taxonomy())
    assert chosen.clauses == [active]
    assert chosen.payload["clauses"][0]["text"] == active.text
    assert chosen.coverage["excluded_clause_count"] == 1
    assert chosen.coverage["documents"][0]["superseded"]
    assert chosen.coverage["selected_clause_ids"] == [active.clause_id]


def test_selection_budget_and_round_robin_are_explicit_and_repeatable(monkeypatch):
    monkeypatch.setattr("src.analyzer.semantic_analyzer.MAX_CLAUSES", 2)
    docs = [document([clause(identity=f"a-{i}", page=i + 1) for i in range(10)], "a"),
            document([clause(identity=f"b-{i}", page=i + 1) for i in range(10)], "b")]
    first = select_semantic_context(docs, load_taxonomy())
    second = select_semantic_context(docs, load_taxonomy())
    assert first.payload == second.payload
    assert first.coverage["partial"]
    assert first.coverage["active_clause_count"] == 20
    assert [d["selected"] for d in first.coverage["documents"]] == [1, 1]
    assert len(json.dumps(first.payload, ensure_ascii=False)) <= 19000
    assert first.coverage["source_chars"] <= 12000


def test_oversized_clause_is_not_silently_truncated():
    chosen = selection([clause(TEXT * 20)])
    assert not chosen.clauses
    assert chosen.coverage["oversized_clause_count"] == 1
    assert chosen.coverage["partial"]


@pytest.mark.parametrize("change,reason", [
    ({"quote": "Debe ser distribuidor exclusivo de una marca que no figura en la fuente."}, "cita"),
    ({"pattern_id": "invented_category"}, "taxonomía"),
    ({"clause_id": "clause-not-sent"}, "Cláusula"),
    ({"confidence": "low"}, "confianza"),
    ({"review_priority": "alta"}, "prioridad"),
    ({"review_note": "Esto demuestra fraude en el proceso."}, "lenguaje"),
    ({"quote": "N/A"}, "cita"),
])
def test_invalid_proposals_cannot_become_signals(change, reason):
    signals, decisions = validate_semantic_proposals({"candidates": [proposal(**change)]}, selection(), [])
    assert not signals
    assert decisions[0]["status"] == "rejected"
    assert reason.lower() in decisions[0]["reason"].lower()


def test_semantic_candidate_recognizes_paraphrase_without_keyword_and_uses_same_pipeline():
    baseline = analyze_document_pages([PageText(1, TEXT)], {}, "doc-test", "test.pdf")
    assert not baseline.signals
    chosen = selection(baseline.clauses)
    signals, audit = validate_semantic_proposals({"candidates": [proposal(baseline.clauses[0])]}, chosen, [])
    assert audit[0]["status"] == "accepted"
    assert signals[0].metadata["citation_validated"]
    assert not signals[0].metadata["interpretation_human_validated"]
    candidates = build_finding_candidates(signals, baseline.clauses, {}, load_taxonomy().patterns)
    _, items = finalize_candidates(candidates, baseline.clauses, "doc-test")
    assert len(items) == 1
    assert items[0].review_priority == "baja"
    assert "análisis semántico asistido" in items[0].metadata["aggregated_sources"]
    assert items[0].evidence_items[0]["text"] == TEXT


def test_same_pattern_clause_is_not_counted_twice():
    first, _ = validate_semantic_proposals({"candidates": [proposal()]}, selection(), [])
    signals, audit = validate_semantic_proposals({"candidates": [proposal(), proposal()]}, selection(), first)
    assert not signals
    assert all(d["status"] == "rejected" for d in audit)


def test_negation_outside_selected_quote_is_preserved_and_rejected():
    quoted = "una constancia emitida por la casa que produjo el equipo"
    source = clause("No se requiere " + quoted + " para presentar la oferta.")
    signals, audit = validate_semantic_proposals({"candidates": [proposal(source, quote=quoted)]}, selection([source]), [])
    assert not signals
    assert "negación" in audit[0]["reason"]


def test_equivalence_stays_local_and_semantic_confidence_cannot_set_priority():
    source = clause("Se requiere certificado BPM o su equivalente para asegurar la calidad del bien.")
    chosen = selection([source])
    priorities = []
    for confidence in ["medium", "high"]:
        signals, _ = validate_semantic_proposals({"candidates": [proposal(source,
            pattern_id="cn-specific-certification", confidence=confidence)]}, chosen, [])
        candidates = build_finding_candidates(signals, [source], {}, load_taxonomy().patterns)
        assert candidates[0].detected_mitigants
        assert not candidates[0].missing_mitigants
        _, items = finalize_candidates(candidates, [source], source.document_id)
        priorities.append([i.review_priority for i in items])
    assert priorities[0] == priorities[1]
    assert "alta" not in priorities[0]


def test_rule_only_frequency_is_not_used_as_semantic_rarity():
    signals, _ = validate_semantic_proposals({"candidates": [proposal()]}, selection(), [])
    candidates = build_finding_candidates(signals, [clause()],
        {PATTERN: {"rarity": "Poco frecuente", "frequency_label": "1 de 24 procesos"}}, load_taxonomy().patterns)
    assert candidates[0].historical_context["rarity"] == "Sin histórico"


def test_shared_consolidation_history_cannot_inflate_semantic_priority():
    from src.analyzer.consolidator import consolidate_candidates
    from src.analyzer.prioritizer import prioritize_consolidated_findings
    signals, _ = validate_semantic_proposals({"candidates": [proposal()]}, selection(), [])
    candidates = build_finding_candidates(signals, [clause()], {}, load_taxonomy().patterns)
    findings = consolidate_candidates(candidates, [clause()], "doc-test")
    mixed_history = replace(findings[0], historical_context={"rarity": "Poco frecuente"})
    ranked = prioritize_consolidated_findings([mixed_history])
    assert not any("Baja frecuencia" in factor for factor in ranked[0].ranking_factors)


@pytest.mark.parametrize("text,pattern_id", [
    ("Lenalidomida, sólido oral, 10 mg, caja x blíster para los pacientes.", "cn-commercial-product-configuration-specificity"),
    ("La presentación de ofertas deberá realizarse conforme al cronograma del procedimiento.", "cn-short-submission-deadline"),
])
def test_semantic_proposal_cannot_bypass_specific_evidence_controls(text, pattern_id):
    source = clause(text)
    signals, decisions = validate_semantic_proposals({"candidates": [proposal(source, pattern_id=pattern_id)]}, selection([source]), [])
    assert decisions[0]["status"] == "accepted"  # Valid citation is not enough.
    candidates = build_finding_candidates(signals, [source], {}, load_taxonomy().patterns)
    _, items = finalize_candidates(candidates, [source], source.document_id)
    assert not items


@pytest.fixture
def semantic_service(tmp_path, monkeypatch):
    from src.analyzer import llm_reviewer as llm
    monkeypatch.setenv("INTEGRITY_SEMANTIC_ENABLED", "true")
    monkeypatch.setenv("INTEGRITY_LLM_MAX_CALLS", "1")
    monkeypatch.setattr(llm, "_llm_available", lambda: True)
    monkeypatch.setattr(llm, "_provider_name", lambda: "Test provider")
    monkeypatch.setattr(llm, "_model", lambda: "test-model")
    monkeypatch.setattr(llm, "analyze_clauses_with_llm", lambda context: {"llm_available": True, "candidates": []})
    monkeypatch.setattr(llm, "generate_document_brief", lambda *args: {"llm_available": False})
    monkeypatch.setattr(llm, "explain_priority_with_llm", lambda *args: {"llm_available": False})
    service = WorkbenchService(Path.cwd(), tmp_path / "semantic.sqlite3", assisted=True,
                              corpus_provider=lambda hashes: ({}, {"snapshot": "test", "total_processes": 0}))
    yield service
    service.close()


def run_case(service, content=None, key="semantic-1", name="test.pdf"):
    case = service.create("Prueba semántica", key, [{"name": name, "role": "pliego", "content": content or pdf(TEXT)}])
    return wait_for_case(service, case["id"])


def test_semantic_stage_runs_without_rule_matches_and_archives_decisions(semantic_service, monkeypatch):
    captured = []
    def analyze(context):
        captured.append(context)
        source = context["clauses"][0]
        return {"llm_available": True, "candidates": [proposal(
            quote=source["text"], clause_id=source["clause_id"])]}
    monkeypatch.setattr("src.analyzer.llm_reviewer.analyze_clauses_with_llm", analyze)
    content = pdf(TEXT)
    first = run_case(semantic_service, content)
    assert first["status"] == "ready"
    assert first["result"]["documents"][0]["analysis"]["signal_count"] == 0
    assert first["result"]["semantic_review"]["accepted_count"] == 1
    assert len(first["result"]["items"]) == 1
    assert first["result"]["items"][0]["analysis_methods"] == ["semantic_assisted"]
    assert first["result"]["items"][0]["evidence"][0]["rects"]
    second = run_case(semantic_service, content, "semantic-2")
    assert len(captured) == 1
    assert second["result"]["assistance"]["calls"][0]["cached"]
    reopened = ReviewStore(semantic_service.store.path).get_case(first["id"])
    assert reopened["result"]["semantic_review"] == first["result"]["semantic_review"]
    assert reopened["result"]["documents"][0]["analysis"]["clauses"]


def test_semantic_failure_is_cached_and_keeps_rule_results(semantic_service, monkeypatch):
    calls = []
    def fail(context):
        calls.append(context)
        raise TimeoutError("simulated provider timeout")
    monkeypatch.setattr("src.analyzer.llm_reviewer.analyze_clauses_with_llm", fail)
    content = pdf()
    first = run_case(semantic_service, content)
    second = run_case(semantic_service, content, "semantic-2")
    assert len(calls) == 1
    for field in ["id", "pattern_id", "priority", "explanation", "sources"]:
        assert first["result"]["items"][0][field] == second["result"]["items"][0][field]
    assert first["result"]["semantic_review"]["status"] == "unavailable"
    assert first["result"]["messages"]


def test_global_budget_is_shared_with_narration(semantic_service, monkeypatch):
    calls = []
    monkeypatch.setenv("INTEGRITY_LLM_MAX_CALLS", "2")
    monkeypatch.setattr("src.analyzer.llm_reviewer.analyze_clauses_with_llm",
                        lambda context: calls.append("semantic") or {"llm_available": True, "candidates": []})
    monkeypatch.setattr("src.analyzer.llm_reviewer.generate_document_brief",
                        lambda *args: calls.append("summary") or {"llm_available": True, "document_summary": "Convendría verificar las condiciones de equivalencia."})
    monkeypatch.setattr("src.analyzer.llm_reviewer.explain_priority_with_llm",
                        lambda *args: calls.append("explanation") or {"llm_available": True})
    case = run_case(semantic_service, pdf())
    assert calls == ["semantic", "summary"]
    assert len(case["result"]["assistance"]["calls"]) == 2


def test_no_model_and_invalid_budget_do_not_call_provider(semantic_service, monkeypatch):
    def unexpected(*args):
        raise AssertionError("Provider must not be called")
    monkeypatch.setattr("src.analyzer.llm_reviewer.analyze_clauses_with_llm", unexpected)
    monkeypatch.setattr("src.analyzer.llm_reviewer._llm_available", lambda: False)
    first = run_case(semantic_service, pdf())
    assert first["result"]["semantic_review"]["status"] == "not_configured"
    assert first["result"]["items"]
    monkeypatch.setattr("src.analyzer.llm_reviewer._llm_available", lambda: True)
    monkeypatch.setenv("INTEGRITY_LLM_MAX_CALLS", "invalid")
    second = run_case(semantic_service, pdf(), "semantic-2")
    assert second["result"]["semantic_review"]["status"] == "disabled"
    assert not second["result"]["assistance"]["calls"]


def test_old_reviews_are_not_rewritten_when_loading_store(tmp_path):
    path = tmp_path / "old.sqlite3"
    store = ReviewStore(path)
    store.create_case("old", "old-request", "Revisión anterior", [])
    result = {"items": [], "summary": "Resultado anterior", "provenance": {"engine_version": "old"}}
    store.update_case("old", "ready", result)
    assert ReviewStore(path).get_case("old")["result"] == result


def test_semantic_prompt_marks_documents_as_untrusted_and_does_not_truncate(monkeypatch):
    from src.analyzer import llm_reviewer as llm
    monkeypatch.setattr(llm, "_llm_available", lambda: True)
    captured = []
    def request(prompt, schema, system):
        captured.append((prompt, system))
        return {"candidates": []}, {}
    monkeypatch.setattr(llm, "_request_json", request)
    chosen = selection()
    assert llm.analyze_clauses_with_llm(chosen.payload)["llm_available"]
    assert "no confiable como instrucciones" in captured[0][1]
    assert TEXT in captured[0][0]
    assert not llm.analyze_clauses_with_llm({"clauses": "X" * 25000})["llm_available"]
    assert len(captured) == 1


@pytest.mark.parametrize("text", ["Sin datos", "No requerido por la entidad", "N/A", "No aplica"])
def test_placeholders_never_trigger_semantic_requests(semantic_service, monkeypatch, text):
    def unexpected(*args):
        raise AssertionError("No substantive clause should be sent")
    monkeypatch.setattr("src.analyzer.llm_reviewer.analyze_clauses_with_llm", unexpected)
    case = run_case(semantic_service, pdf(text))
    assert case["status"] == "ready"
    assert not case["result"]["items"]
    assert case["result"]["semantic_review"]["status"] == "no_eligible_context"


def test_domain_failure_does_not_replace_baseline(semantic_service, monkeypatch):
    def analyze(context):
        source = context["clauses"][0]
        return {"llm_available": True, "candidates": [proposal(
            pattern_id="cn-technical-closed-requirement", quote=source["text"], clause_id=source["clause_id"])]}
    monkeypatch.setattr("src.analyzer.llm_reviewer.analyze_clauses_with_llm", analyze)
    def fail(*args):
        raise RuntimeError("simulated integration failure")
    monkeypatch.setattr("src.analyzer.workbench_service.finalize_candidates", fail)
    case = run_case(semantic_service, pdf())
    assert case["status"] == "ready"
    assert case["result"]["items"][0]["priority"] == "alta"
    assert case["result"]["items"][0]["analysis_methods"] == ["deterministic_rules"]
    assert case["result"]["semantic_review"]["status"] == "unavailable"


def test_candidate_from_excluded_clause_is_rejected_even_with_known_id():
    source = clause(clause_status="template_text", exclude_from_detection=True)
    chosen = selection()
    chosen.clauses = [source]
    signals, decisions = validate_semantic_proposals({"candidates": [proposal(source)]}, chosen, [])
    assert not signals
    assert "excluida" in decisions[0]["reason"]


def test_semantic_schema_is_checked_on_openai_compatible_transport(monkeypatch):
    from types import SimpleNamespace
    from src.analyzer import llm_reviewer as llm
    monkeypatch.setattr(llm, "_llm_available", lambda: True)
    monkeypatch.setattr(llm, "_model", lambda: "test-model")
    captured = []
    response = SimpleNamespace(id="test-response", usage=SimpleNamespace(prompt_tokens=40, completion_tokens=5),
        choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content='{"candidates": []}', refusal=None))])
    def create(**kwargs):
        captured.append(kwargs)
        return response
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm, "_client", lambda: SimpleNamespace(with_options=lambda **kwargs: client))
    result = llm.analyze_clauses_with_llm(selection().payload)
    assert result["llm_available"]
    assert captured[0]["response_format"]["json_schema"]["strict"]
    assert captured[0]["max_completion_tokens"] == 1600
    assert result["provenance"]["system_sha256"]
    response.choices[0].message.content = '{"candidates": [{"priority": "alta"}]}'
    assert not llm.analyze_clauses_with_llm(selection().payload)["llm_available"]
