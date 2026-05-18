from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_CONTEXTUAL = "contextual"

CONFIDENCE_LOW = "low"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_HIGH = "high"

REVIEW_GENERAL = "general"
REVIEW_SUGGESTED = "suggested"
REVIEW_PRIORITY = "priority"

PROHIBITED_INTERPRETATION = (
    "No debe interpretarse como evidencia de corrupción, fraude, ilegalidad ni direccionamiento."
)


@dataclass
class Finding:
    """Preliminary analytical output for human review.

    Findings are not legal conclusions, do not assign responsibility, and should not be
    interpreted as accusations. They only preserve textual evidence and contextual review
    criteria for a human reviewer.
    """

    id: str
    title: str
    category: str
    severity: str
    evidence: str
    page: int
    rationale: str
    pattern_id: str
    mitigating_factors: list[str] = field(default_factory=list)
    escalation_factors: list[str] = field(default_factory=list)
    suggested_questions: list[str] = field(default_factory=list)
    requires_human_review: bool = True
    output_label: str = "aspecto a revisar"
    signal_type: str = "señal_revision"
    match_count: int = 1
    pattern_name: str = ""
    competition_dimension: str = "low_competitive_neutrality"
    document_section: str = "No determinada"
    clause_excerpt: str = ""
    reason_for_review: str = ""
    possible_legitimate_justifications: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    suggested_neutral_wording: list[str] = field(default_factory=list)
    confidence: str = CONFIDENCE_MEDIUM
    review_priority: str = REVIEW_SUGGESTED
    contextual_notes: list[str] = field(default_factory=list)
    prohibited_interpretation: str = PROHIBITED_INTERPRETATION

    def __post_init__(self) -> None:
        if not self.pattern_name:
            self.pattern_name = self.title
        if not self.clause_excerpt:
            self.clause_excerpt = self.evidence
        if not self.reason_for_review:
            self.reason_for_review = self.rationale
        if self.confidence not in {CONFIDENCE_LOW, CONFIDENCE_MEDIUM, CONFIDENCE_HIGH}:
            self.confidence = CONFIDENCE_MEDIUM
        if self.review_priority not in {REVIEW_GENERAL, REVIEW_SUGGESTED, REVIEW_PRIORITY}:
            self.review_priority = REVIEW_SUGGESTED

    @property
    def finding_id(self) -> str:
        return self.id

    @property
    def detected_pattern(self) -> str:
        return self.title

    @property
    def text_fragment(self) -> str:
        return self.evidence

    @text_fragment.setter
    def text_fragment(self, value: str) -> None:
        self.evidence = value

    def to_dict(self) -> dict[str, str | int | bool]:
        """Return the current app-compatible shape plus structured finding fields."""
        return {
            "finding_id": self.id,
            "id": self.id,
            "title": self.title,
            "severity": self.severity,
            "pattern_id": self.pattern_id,
            "pattern_name": self.pattern_name,
            "competition_dimension": self.competition_dimension,
            "document_section": self.document_section,
            "clause_excerpt": self.clause_excerpt,
            "reason_for_review": self.reason_for_review,
            "mitigating_factors": self.mitigating_factors,
            "escalation_factors": self.escalation_factors,
            "possible_legitimate_justifications": self.possible_legitimate_justifications,
            "missing_information": self.missing_information,
            "human_review_questions": self.suggested_questions,
            "suggested_questions": self.suggested_questions,
            "suggested_neutral_wording": self.suggested_neutral_wording,
            "confidence": self.confidence,
            "review_priority": self.review_priority,
            "contextual_notes": self.contextual_notes,
            "prohibited_interpretation": self.prohibited_interpretation,
            "requires_human_review": self.requires_human_review,
            "output_label": self.output_label,
            "tipo_señal": self.signal_type,
            "página": self.page,
            "categoría": self.category,
            "patrón detectado": self.pattern_name,
            "dimensión competitiva": self.competition_dimension,
            "sección documental probable": self.document_section,
            "nivel de atención": _legacy_attention(self.severity, self.requires_human_review),
            "prioridad de revisión": _display_review_priority(self.review_priority),
            "número de coincidencias": self.match_count,
            "fragmento textual": self.evidence,
            "observación prudente": self.rationale,
            "posible efecto sobre concurrencia": _competition_effect(
                self.signal_type,
                self.mitigating_factors,
            ),
            "validación sugerida": _suggested_validation(self.suggested_questions),
            "lenguaje recomendado": _join_list(self.suggested_neutral_wording),
            "advertencia metodológica": self.prohibited_interpretation,
        }


def _legacy_attention(severity: str, requires_human_review: bool) -> str:
    if not requires_human_review or severity == SEVERITY_LOW:
        return "Bajo"
    if severity == SEVERITY_CONTEXTUAL:
        return "Medio"
    return "Medio"


def _competition_effect(signal_type: str, mitigating_factors: list[str]) -> str:
    if signal_type == "mitigante_concurrencia":
        return "Factor mitigante identificado que puede favorecer concurrencia."
    if signal_type == "requisito_habitual":
        return "No se aprecia efecto limitante por sí solo."
    if mitigating_factors:
        return (
            "Aspecto a revisar con factores mitigantes identificados; conviene valorar "
            "el efecto acumulado en contexto."
        )
    return "Aspecto a revisar por posible efecto sobre concurrencia, sujeto a revisión humana."


def _display_review_priority(priority: str) -> str:
    return {
        REVIEW_GENERAL: "revisión general",
        REVIEW_SUGGESTED: "revisión sugerida",
        REVIEW_PRIORITY: "revisión prioritaria",
    }.get(priority, "revisión sugerida")


def _suggested_validation(questions: list[str]) -> str:
    if questions:
        return questions[0]
    return "Validar proporcionalidad, necesidad técnica y contexto documental."


def _join_list(values: list[Any]) -> str:
    return "; ".join(str(value) for value in values if str(value).strip())
