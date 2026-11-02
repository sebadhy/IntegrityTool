from dataclasses import asdict

import pytest

from src.analyzer.domain_models import Clause
from src.analyzer.requirements import compare_requirements, extract_requirements


def clause(text, page=1, **kwargs):
    return Clause(f"c-{page}", "doc-test", page, "Condiciones técnicas", "technical", text, text.lower(), **kwargs)


def document(id, text, **kwargs):
    return {"id": id, "name": id + ".pdf", "role": "pliego", **kwargs,
            "analysis": {"requirements": [asdict(r) for r in extract_requirements([clause(text)])]}}


@pytest.mark.parametrize("text,attribute,value,unit,operator", [
    ("Ítem 1. Memoria RAM mínima: 16 GB", "ram", "16", "gb", "min"),
    ("Ítem 2. Peso máximo 1,24 kg", "weight", "1.24", "kg", "max"),
    ("Ítem 1. Almacenamiento exactamente 512 GB", "storage", "512", "gb", "eq"),
    ("Ítem 1. Plazo de entrega máximo 30 días calendario desde la firma del contrato", "delivery_period", "30", "calendar_days", "max"),
])
def test_extract_literal_requirement(text, attribute, value, unit, operator):
    req, = extract_requirements([clause(text)])
    assert (req.attribute, req.value, req.unit, req.comparator) == (attribute, value, unit, operator)
    assert req.matched_text in text
    assert req.evidence_text == text


@pytest.mark.parametrize("text", ["Sin datos", "No aplica", "RAM de 16 a 32 GB", "RAM 16 GB o 32 GB", "Peso máximo 1,240 kg", "RAM máxima 16 GB/s", "No se exige RAM mínima 16 GB"])
def test_ambiguous_or_empty_not_extracted(text):
    assert extract_requirements([clause(text)]) == []


def test_excluded_clause_not_extracted():
    assert extract_requirements([clause("Ítem 1 RAM mínima 16 GB", exclude_from_detection=True)]) == []


def test_distinct_conditions_preserve_sources():
    result = compare_requirements([document("a", "Ítem 1 RAM mínima 16 GB"), document("b", "Ítem 1 RAM mínima 32 GB")])
    group, = result["comparisons"]
    assert group["status"] == "different_conditions"
    assert {r["value"] for r in group["sources"]} == {"16", "32"}
    assert {r["document_name"] for r in group["sources"]} == {"a.pdf", "b.pdf"}
    assert "priority" not in group


@pytest.mark.parametrize("left,right", [
    ("Ítem 1 RAM mínima 16 GB", "Ítem 2 RAM mínima 32 GB"),
    ("RAM mínima 16 GB", "RAM mínima 32 GB"),
    ("Ítem 1 RAM mínima 16 GB", "Ítem 1 RAM mínima 16000 MB"),
    ("Ítem 1 RAM 16 GB", "Ítem 1 RAM 32 GB"),
    ("Ítem 1 Plazo de entrega máximo 30 días", "Ítem 1 Plazo de entrega máximo 15 días"),
    ("Ítem 1 Plazo de entrega máximo 30 días calendario desde la firma del contrato", "Ítem 1 Plazo de entrega máximo 15 días calendario desde la notificación de la orden"),
    ("Ítem 1 Plazo de entrega máximo 30 días calendario desde la firma del contrato", "Ítem 1 Plazo de ejecución máximo 15 días calendario desde la firma del contrato"),
    ("Ítem 1 e ítem 2 RAM mínima 16 GB", "Ítem 1 RAM mínima 32 GB"),
])
def test_abstain_when_scope_unit_operator_or_milestone_differ(left, right):
    assert compare_requirements([document("a", left), document("b", right)])["comparisons"] == []


def test_repeated_conditions_preserve_evidence_without_duplicate_group():
    a = document("a", "Ítem 1 RAM mínima 16 GB")
    a["analysis"]["requirements"].extend(asdict(r) for r in extract_requirements([clause("Ítem 1 RAM mínima 16 GB", page=2)]))
    result = compare_requirements([a, document("b", "Ítem 1 RAM mínima 16 GB")])
    group, = result["comparisons"]
    assert group["status"] == "same_explicit_condition"
    assert len(group["sources"]) == 3


def test_multiple_conditions_in_one_source_abstains():
    a = document("a", "Ítem 1 RAM mínima 16 GB; RAM mínima 32 GB")
    result = compare_requirements([a, document("b", "Ítem 1 RAM mínima 16 GB")])
    assert not result["comparisons"]
    assert result["abstentions"]["multiple_conditions"] == 3


def test_superseded_document_not_compared():
    docs = [document("old", "Ítem 1 RAM mínima 16 GB"), document("new", "Ítem 1 RAM mínima 32 GB", supersedes="old"), document("spec", "Ítem 1 RAM mínima 32 GB")]
    group, = compare_requirements(docs)["comparisons"]
    assert group["status"] == "same_explicit_condition"
    assert "old" not in {source["source_document_id"] for source in group["sources"]}


def test_same_input_same_result():
    docs = [document("a", "Ítem 1 RAM mínima 16 GB"), document("b", "Ítem 1 RAM mínima 32 GB")]
    assert compare_requirements(docs) == compare_requirements(docs)


def test_equivalence_recorded_without_changing_value():
    req, = extract_requirements([clause("Ítem 1 RAM mínima 16 GB o equivalente")])
    assert req.equivalence and req.value == "16"


def test_matching_deadline_milestones_can_be_compared():
    docs = [document("a", "Ítem 1 Plazo de entrega máximo 30 días calendario desde la firma del contrato"),
            document("b", "Ítem 01 Plazo de entrega máximo 15 días calendario desde la firma del contrato")]
    group, = compare_requirements(docs)["comparisons"]
    assert group["status"] == "different_conditions"


def test_event_mention_is_not_automatically_a_start_milestone():
    doc = document("a", "Ítem 1 Plazo de entrega máximo 30 días calendario; firma del contrato")
    assert doc["analysis"]["requirements"][0]["milestone"] == ""
