from __future__ import annotations

from dataclasses import dataclass, field


SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_CONTEXTUAL = "contextual"


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
            "title": self.title,
            "severity": self.severity,
            "pattern_id": self.pattern_id,
            "mitigating_factors": self.mitigating_factors,
            "escalation_factors": self.escalation_factors,
            "suggested_questions": self.suggested_questions,
            "requires_human_review": self.requires_human_review,
            "output_label": self.output_label,
            "tipo_señal": self.signal_type,
            "página": self.page,
            "categoría": self.category,
            "patrón detectado": self.title,
            "nivel de atención": _legacy_attention(self.severity, self.requires_human_review),
            "número de coincidencias": self.match_count,
            "fragmento textual": self.evidence,
            "observación prudente": self.rationale,
            "posible efecto sobre concurrencia": _competition_effect(
                self.signal_type,
                self.mitigating_factors,
            ),
            "validación sugerida": _suggested_validation(self.suggested_questions),
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


def _suggested_validation(questions: list[str]) -> str:
    if questions:
        return questions[0]
    return "Validar proporcionalidad, necesidad técnica y contexto documental."
