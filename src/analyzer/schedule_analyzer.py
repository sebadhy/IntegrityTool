from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache

from .domain_models import Clause, Signal
from .taxonomy_loader import load_taxonomy
from .text_utils import normalize_text_es

SCHEDULE_PATTERN_ID = "cn-short-submission-deadline"
VISIT_PATTERN_ID = "cn-mandatory-technical-visit"

MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

PUBLICATION_TERMS = (
    "publicacion",
    "publicación",
    "convocatoria",
    "invitacion",
    "invitación",
    "fecha de publicacion",
    "fecha de publicación",
)
OFFER_TERMS = (
    "presentacion de ofertas",
    "presentación de ofertas",
    "entrega de ofertas",
    "recepcion de ofertas",
    "recepción de ofertas",
    "fecha limite",
    "fecha límite",
    "limite de entrega",
    "límite de entrega",
    "cierre de ofertas",
)
VISIT_TERMS = (
    "visita tecnica",
    "visita técnica",
    "visita obligatoria",
    "visita al sitio",
    "inspeccion tecnica",
    "inspección técnica",
)
MANDATORY_VISIT_TERMS = ("obligatoria", "obligatorio", "asistencia obligatoria", "debera asistir", "deberá asistir")


@dataclass(frozen=True)
class ScheduleEvent:
    event_type: str
    event_label: str
    event_date: date
    clause: Clause
    evidence_text: str


def detect_schedule_signals(clauses: list[Clause]) -> list[Signal]:
    """Detect concrete schedule intervals that may merit human review.

    This module is deterministic and evidence-first: it does not emit a signal for
    generic references to cronograma/plazo unless it can associate concrete dates
    with procurement events such as publication, offer submission, or technical
    visit.
    """
    events = _extract_events(clauses)
    if not events:
        return []

    signals: list[Signal] = []
    signals.extend(_submission_interval_signals(events))
    signals.extend(_technical_visit_interval_signals(events))
    return _dedupe_signals(signals)


def _extract_events(clauses: list[Clause]) -> list[ScheduleEvent]:
    events: list[ScheduleEvent] = []
    for clause in clauses:
        if clause.exclude_from_detection:
            continue
        for chunk in _candidate_chunks(clause.text):
            if not _has_schedule_language(chunk):
                continue
            dates = _dates_in_text(chunk)
            if not dates:
                continue
            event_type, label = _event_type(chunk)
            if not event_type:
                continue
            for event_date in dates:
                events.append(
                    ScheduleEvent(
                        event_type=event_type,
                        event_label=label,
                        event_date=event_date,
                        clause=clause,
                        evidence_text=_clean_evidence(chunk),
                    )
                )
    return events


def _candidate_chunks(text: str) -> list[str]:
    chunks = [line.strip() for line in re.split(r"[\n\r]+", text) if line.strip()]
    if len(chunks) <= 1:
        chunks = [part.strip() for part in re.split(r"(?<=[.;])\s+", text) if part.strip()]
    output: list[str] = []
    for chunk in chunks:
        if len(chunk) > 420:
            output.extend(_date_windows(chunk))
        else:
            output.append(chunk)
    return output


def _date_windows(text: str, window: int = 170) -> list[str]:
    spans = [match.span() for match in _date_matches(text)]
    if not spans:
        return [text[:420]]
    windows = []
    for start, end in spans:
        windows.append(text[max(0, start - window): min(len(text), end + window)])
    return windows


def _date_matches(text: str) -> list[re.Match[str]]:
    patterns = [
        r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b",
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
        r"\b\d{1,2}\s+de\s+[a-záéíóúñ]+\s+de\s+\d{4}\b",
    ]
    matches: list[re.Match[str]] = []
    for pattern in patterns:
        matches.extend(re.finditer(pattern, text, flags=re.IGNORECASE))
    return sorted(matches, key=lambda match: match.start())


def _dates_in_text(text: str) -> list[date]:
    dates: list[date] = []
    for match in _date_matches(text):
        parsed = _parse_date(match.group(0))
        if parsed and parsed not in dates:
            dates.append(parsed)
    return dates


def _parse_date(value: str) -> date | None:
    raw = value.strip().lower()
    if re.match(r"^\d{4}[/-]\d{1,2}[/-]\d{1,2}$", raw):
        year, month, day = [int(part) for part in re.split(r"[/-]", raw)]
        return _safe_date(year, month, day)
    if re.match(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$", raw):
        day, month, year = [int(part) for part in re.split(r"[/-]", raw)]
        if year < 100:
            year += 2000
        return _safe_date(year, month, day)
    match = re.match(r"^(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+de\s+(\d{4})$", raw)
    if match:
        day = int(match.group(1))
        month = MONTHS.get(normalize_text_es(match.group(2)))
        year = int(match.group(3))
        if month:
            return _safe_date(year, month, day)
    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        if year < 2000 or year > 2100:
            return None
        return date(year, month, day)
    except ValueError:
        return None


def _has_schedule_language(text: str) -> bool:
    normalized = normalize_text_es(text)
    return any(term in normalized for term in [
        "cronograma",
        "publicacion",
        "convocatoria",
        "invitacion",
        "presentacion de ofertas",
        "entrega de ofertas",
        "recepcion de ofertas",
        "fecha limite",
        "visita tecnica",
        "visita obligatoria",
        "cierre de ofertas",
    ])


def _event_type(text: str) -> tuple[str, str]:
    normalized = normalize_text_es(text)
    if any(normalize_text_es(term) in normalized for term in VISIT_TERMS):
        return "technical_visit", "visita técnica"
    if any(normalize_text_es(term) in normalized for term in OFFER_TERMS):
        return "offer_submission", "presentación de ofertas"
    if any(normalize_text_es(term) in normalized for term in PUBLICATION_TERMS):
        return "publication", "publicación o convocatoria"
    return "", ""


def _submission_interval_signals(events: list[ScheduleEvent]) -> list[Signal]:
    publications = sorted([event for event in events if event.event_type == "publication"], key=lambda item: item.event_date)
    offers = sorted([event for event in events if event.event_type == "offer_submission"], key=lambda item: item.event_date)
    signals: list[Signal] = []
    for offer in offers:
        previous_publications = [event for event in publications if event.event_date <= offer.event_date]
        if not previous_publications:
            continue
        publication = previous_publications[-1]
        calendar_days = (offer.event_date - publication.event_date).days
        business_days = _business_days_between(publication.event_date, offer.event_date)
        if calendar_days <= 3 or business_days <= 2:
            signals.append(
                _build_signal(
                    pattern_id=SCHEDULE_PATTERN_ID,
                    event=offer,
                    counterpart=publication,
                    matched_text="intervalo corto de cronograma",
                    evidence_text=(
                        f"Se identificó un intervalo de {calendar_days} día(s) calendario "
                        f"({business_days} día(s) hábil(es) estimados) entre "
                        f"{publication.event_label} ({_format_date(publication.event_date)}) y "
                        f"{offer.event_label} ({_format_date(offer.event_date)}). "
                        f"Evidencia: {publication.evidence_text} / {offer.evidence_text}"
                    ),
                    semantic_group="schedule-submission-interval",
                )
            )
    return signals


def _technical_visit_interval_signals(events: list[ScheduleEvent]) -> list[Signal]:
    visits = sorted([event for event in events if event.event_type == "technical_visit"], key=lambda item: item.event_date)
    offers = sorted([event for event in events if event.event_type == "offer_submission"], key=lambda item: item.event_date)
    signals: list[Signal] = []
    for visit in visits:
        future_offers = [event for event in offers if event.event_date >= visit.event_date]
        if not future_offers:
            continue
        offer = future_offers[0]
        calendar_days = (offer.event_date - visit.event_date).days
        mandatory = _is_mandatory_visit(visit.evidence_text)
        if mandatory and calendar_days <= 2:
            signals.append(
                _build_signal(
                    pattern_id=VISIT_PATTERN_ID,
                    event=visit,
                    counterpart=offer,
                    matched_text="visita técnica cercana al cierre",
                    evidence_text=(
                        f"Se identificó visita técnica obligatoria {_format_date(visit.event_date)} "
                        f"con presentación de ofertas {_format_date(offer.event_date)}, separadas por "
                        f"{calendar_days} día(s) calendario. Evidencia: {visit.evidence_text} / {offer.evidence_text}"
                    ),
                    semantic_group="mandatory-visit-near-submission",
                )
            )
    return signals


def _build_signal(
    *,
    pattern_id: str,
    event: ScheduleEvent,
    counterpart: ScheduleEvent,
    matched_text: str,
    evidence_text: str,
    semantic_group: str,
) -> Signal:
    digest = hashlib.sha1(f"{pattern_id}|{event.clause.clause_id}|{counterpart.clause.clause_id}|{evidence_text}".encode("utf-8")).hexdigest()[:12]
    return Signal(
        signal_id=f"signal-schedule-{digest}",
        clause_id=event.clause.clause_id,
        pattern_id=pattern_id,
        family="restricción temporal potencial",
        competition_dimension="barreras_de_entrada",
        signal_type="contextual_schedule_signal",
        matched_text=matched_text,
        evidence_text=evidence_text,
        page=event.clause.page,
        section_title=event.clause.section_title,
        detector_name="schedule_interval_detector_v1",
        confidence="medium",
        metadata={
            "semantic_group_key": semantic_group,
            "schedule_analysis_note": "Intervalo calculado a partir de fechas concretas del cronograma extraído.",
            "taxonomy_pattern": _taxonomy_payload(pattern_id),
        },
    )


@lru_cache(maxsize=8)
def _taxonomy_payload(pattern_id: str) -> dict:
    for pattern in load_taxonomy().patterns:
        if pattern.id == pattern_id:
            return pattern.to_dict()
    return {
        "id": pattern_id,
        "name": "Consideración sobre cronograma y plazos",
        "human_review_questions": [
            "¿El intervalo del cronograma permite preparar ofertas de forma razonable?",
            "¿El plazo es proporcional a la complejidad documental y logística del procedimiento?",
        ],
    }


def _business_days_between(start: date, end: date) -> int:
    if end < start:
        return 0
    current = start + timedelta(days=1)
    count = 0
    while current <= end:
        if current.weekday() < 5:
            count += 1
        current += timedelta(days=1)
    return count


def _is_mandatory_visit(text: str) -> bool:
    normalized = normalize_text_es(text)
    return any(normalize_text_es(term) in normalized for term in MANDATORY_VISIT_TERMS)


def _clean_evidence(text: str) -> str:
    return " ".join(text.split())[:360]


def _format_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def _dedupe_signals(signals: list[Signal]) -> list[Signal]:
    seen: set[tuple[str, str]] = set()
    output: list[Signal] = []
    for signal in signals:
        key = (signal.pattern_id, signal.evidence_text)
        if key in seen:
            continue
        seen.add(key)
        output.append(signal)
    return output
