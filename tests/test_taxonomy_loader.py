from pathlib import Path

from src.analyzer.taxonomy_loader import load_taxonomy


def test_load_taxonomy_default():
    result = load_taxonomy()
    assert result.loaded
    assert result.patterns
    assert all(pattern.id for pattern in result.patterns)
    assert all(pattern.textual_signals for pattern in result.patterns)


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
