from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


TAXONOMY_PATH = Path(__file__).parent / "patterns" / "risk_taxonomy.yaml"

REQUIRED_FIELDS = {
    "id",
    "name",
    "description",
    "competition_dimension",
    "risk_type",
    "document_sections",
    "textual_signals",
    "semantic_signals",
    "possible_indicators",
    "mitigating_factors",
    "possible_legitimate_justifications",
    "human_review_questions",
    "recommended_language",
    "prohibited_language",
    "severity_guidance",
    "confidence_guidance",
    "related_patterns",
}

ALLOWED_PRIORITY = {"general", "suggested", "priority"}
ALLOWED_CONFIDENCE = {"low", "medium", "high"}


@dataclass(frozen=True)
class TaxonomyPattern:
    """Editable analytical pattern for preliminary human review.

    The taxonomy supports contextual review and traceability. It is not a legal
    opinion, does not replace human judgment, and must not be interpreted as an
    accusation about the document or its authors.
    """

    id: str
    name: str
    description: str
    competition_dimension: str
    risk_type: str
    document_sections: list[str]
    textual_signals: list[str]
    semantic_signals: list[str]
    possible_indicators: list[str]
    mitigating_factors: list[str]
    possible_legitimate_justifications: list[str]
    human_review_questions: list[str]
    recommended_language: list[str]
    prohibited_language: list[str]
    severity_guidance: str
    confidence_guidance: str
    related_patterns: list[str]
    validation_messages: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw_pattern: dict[str, Any]) -> "TaxonomyPattern":
        messages: list[str] = []
        normalized = dict(raw_pattern)

        for field_name in REQUIRED_FIELDS:
            if field_name not in normalized:
                messages.append(f"Campo obligatorio faltante: {field_name}")

        severity = str(normalized.get("severity_guidance") or "suggested").strip()
        if severity not in ALLOWED_PRIORITY:
            messages.append(
                f"severity_guidance inválido '{severity}', se usa 'suggested'."
            )
            severity = "suggested"

        confidence = str(normalized.get("confidence_guidance") or "medium").strip()
        if confidence not in ALLOWED_CONFIDENCE:
            messages.append(
                f"confidence_guidance inválido '{confidence}', se usa 'medium'."
            )
            confidence = "medium"

        pattern_id = str(normalized.get("id") or "uncategorized_review_signal").strip()
        name = str(normalized.get("name") or "Señal preliminar no categorizada").strip()

        return cls(
            id=pattern_id,
            name=name,
            description=str(normalized.get("description") or "").strip(),
            competition_dimension=str(
                normalized.get("competition_dimension") or "low_competitive_neutrality"
            ).strip(),
            risk_type=str(normalized.get("risk_type") or "consideración analítica").strip(),
            document_sections=_as_list(normalized.get("document_sections")),
            textual_signals=_as_list(normalized.get("textual_signals")),
            semantic_signals=_as_list(normalized.get("semantic_signals")),
            possible_indicators=_as_list(normalized.get("possible_indicators")),
            mitigating_factors=_as_list(normalized.get("mitigating_factors")),
            possible_legitimate_justifications=_as_list(
                normalized.get("possible_legitimate_justifications")
            ),
            human_review_questions=_as_list(normalized.get("human_review_questions")),
            recommended_language=_as_list(normalized.get("recommended_language")),
            prohibited_language=_as_list(normalized.get("prohibited_language")),
            severity_guidance=severity,
            confidence_guidance=confidence,
            related_patterns=_as_list(normalized.get("related_patterns")),
            validation_messages=messages,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "competition_dimension": self.competition_dimension,
            "risk_type": self.risk_type,
            "document_sections": self.document_sections,
            "textual_signals": self.textual_signals,
            "semantic_signals": self.semantic_signals,
            "possible_indicators": self.possible_indicators,
            "mitigating_factors": self.mitigating_factors,
            "possible_legitimate_justifications": self.possible_legitimate_justifications,
            "human_review_questions": self.human_review_questions,
            "recommended_language": self.recommended_language,
            "prohibited_language": self.prohibited_language,
            "severity_guidance": self.severity_guidance,
            "confidence_guidance": self.confidence_guidance,
            "related_patterns": self.related_patterns,
            "validation_messages": self.validation_messages,
        }


@dataclass(frozen=True)
class TaxonomyLoadResult:
    patterns: list[TaxonomyPattern]
    messages: list[str]
    loaded: bool


def load_taxonomy(path: Path | None = None) -> TaxonomyLoadResult:
    """Load editable taxonomy with safe fallback behavior.

    Partial errors are returned as messages instead of raising, so Streamlit can
    continue running with the built-in fallback catalogue.
    """

    taxonomy_path = path or TAXONOMY_PATH
    messages: list[str] = []
    if not taxonomy_path.exists():
        return TaxonomyLoadResult(
            patterns=[],
            messages=[f"No se encontró taxonomía editable en {taxonomy_path}."],
            loaded=False,
        )

    try:
        raw_data = yaml.safe_load(taxonomy_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return TaxonomyLoadResult(
            patterns=[],
            messages=[f"No se pudo cargar la taxonomía: {exc}"],
            loaded=False,
        )

    if not isinstance(raw_data, list):
        return TaxonomyLoadResult(
            patterns=[],
            messages=["La taxonomía debe ser una lista de patrones."],
            loaded=False,
        )

    patterns: list[TaxonomyPattern] = []
    seen_ids: set[str] = set()
    for index, raw_pattern in enumerate(raw_data, start=1):
        if not isinstance(raw_pattern, dict):
            messages.append(f"Patrón #{index}: formato inválido, se omite.")
            continue
        pattern = TaxonomyPattern.from_dict(raw_pattern)
        if not pattern.textual_signals:
            messages.append(f"{pattern.id}: sin textual_signals, se omite.")
            continue
        if pattern.id in seen_ids:
            messages.append(f"{pattern.id}: id duplicado, se omite duplicado.")
            continue
        seen_ids.add(pattern.id)
        messages.extend(f"{pattern.id}: {message}" for message in pattern.validation_messages)
        patterns.append(pattern)

    return TaxonomyLoadResult(patterns=patterns, messages=messages, loaded=bool(patterns))


def taxonomy_context(limit: int = 12) -> dict[str, Any]:
    result = load_taxonomy()
    return {
        "loaded": result.loaded,
        "messages": result.messages[:8],
        "patterns": [pattern.to_dict() for pattern in result.patterns[:limit]],
    }


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []
