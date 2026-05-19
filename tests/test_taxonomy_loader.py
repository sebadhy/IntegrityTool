from pathlib import Path

from src.analyzer.taxonomy_loader import load_taxonomy


def test_load_taxonomy_default():
    result = load_taxonomy()
    assert result.loaded
    assert result.patterns
    assert all(pattern.id for pattern in result.patterns)
    assert all(pattern.textual_signals for pattern in result.patterns)
    assert result.metadata.get("version")
    assert result.patterns[0].normative_basis
    assert result.patterns[0].document_signal


def test_load_taxonomy_missing_file(tmp_path):
    result = load_taxonomy(tmp_path / "missing.yaml")
    assert not result.loaded
    assert result.patterns == []
    assert result.messages


def test_load_taxonomy_partial_errors(tmp_path):
    taxonomy = tmp_path / "taxonomy.yaml"
    taxonomy.write_text(
        """
- id: partial
  name: Patrón parcial
  textual_signals:
    - marca
""",
        encoding="utf-8",
    )
    result = load_taxonomy(taxonomy)
    assert result.loaded
    assert result.patterns[0].id == "partial"
    assert result.messages


def test_load_taxonomy_metadata_object_format(tmp_path):
    taxonomy = tmp_path / "taxonomy.yaml"
    taxonomy.write_text(
        """
metadata:
  version: test
  purpose: revisión humana
patterns:
  - id: structured
    name: Patrón estructurado
    description: Patrón de prueba
    competition_dimension: neutralidad_competitiva
    risk_type: consideración analítica
    document_sections: [especificaciones]
    textual_signals: [marca específica]
    semantic_signals: [referencia específica]
    possible_indicators: [condición observable]
    mitigating_factors: [o equivalente]
    possible_legitimate_justifications: [necesidad técnica]
    human_review_questions: ["¿Se aceptan equivalentes?"]
    recommended_language: [revisión humana sugerida]
    prohibited_language: [corrupción]
    severity_guidance: suggested
    confidence_guidance: medium
    related_patterns: []
    normative_basis: [libre concurrencia]
    document_signal: [marca específica]
    possible_competition_effect: [podría limitar alternativas]
    human_validation_required: true
""",
        encoding="utf-8",
    )
    result = load_taxonomy(taxonomy)
    assert result.loaded
    assert result.metadata["version"] == "test"
    assert result.patterns[0].competition_dimension == "neutralidad_competitiva"
    assert result.patterns[0].normative_basis == ["libre concurrencia"]
    assert result.patterns[0].human_validation_required is True
