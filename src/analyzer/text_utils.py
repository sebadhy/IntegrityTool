"""Shared text-processing utilities for the review pipeline.

This module consolidates functions that were previously duplicated across
detector.py, consolidator.py, prioritizer.py, observation_filter.py,
relevance_filter.py, review_item_builder.py, mitigants.py, and contextualizer.py.

Centralizing these utilities avoids silent drift between copies and provides
a single source of truth for text normalization, deduplication, and field parsing.
"""

from __future__ import annotations

import ast
import re
from typing import Any


def unique_strings(values: list[str]) -> list[str]:
    """Return deduplicated list preserving order. Strips whitespace."""
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        clean = value.strip()
        if clean and clean not in seen:
            output.append(clean)
            seen.add(clean)
    return output


def list_field(value: Any) -> list[str]:
    """Coerce a value (list, tuple, JSON string, plain string) to list[str].

    Handles the common case where a DataFrame cell may be a Python list,
    a JSON-encoded list string, or a bare string.
    """
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = ast.literal_eval(stripped)
        except (ValueError, SyntaxError):
            return [stripped]
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
        return [str(parsed).strip()] if str(parsed).strip() else []
    return []


def normalize_text_es(value: str) -> str:
    """Lowercase, strip accents (á→a), collapse whitespace, strip punctuation edges.

    This is the general-purpose Spanish text normalizer used across detection,
    filtering, and observation modules.
    """
    replacements = str.maketrans("áéíóúñü", "aeiounu")
    return re.sub(r"\s+", " ", value.lower().translate(replacements)).strip(" .,:;-")


def is_negated_match(text: str, start: int, end: int | None = None) -> bool:
    """Identify explicit local negation, resetting scope at contrastive clauses.

    This is a conservative textual check, not a semantic or legal conclusion.
    Lists joined by 'ni' retain the negation; 'pero' starts a new scope.
    """
    normalized = text.lower().translate(str.maketrans("áéíóúñü", "aeiounu"))
    if end is not None:
        suffix = re.sub(r"[,:-]\s*(?=no\b)", " ", normalized[end:end + 140])
        if re.match(
            r"^\s*(?:(?!no\b|y\b|se\b|pero\b|debe\b)[\w./()-]+\s+){0,5}"
            r"no\s+(?:(?:sera|seran|es|son)\s+)?"
            r"(?:requerid[oa]s?|exigid[oa]s?|obligatori[oa]s?|necesari[oa]s?|aceptad[oa]s?|admitid[oa]s?)\b",
            suffix,
        ):
            return True
    prefix = normalized[:start]
    prefix = re.split(r"[.;!?]|\b(?:pero|sin embargo|no obstante|aunque|excepto|salvo)\b", prefix)[-1]
    prefix = " ".join(prefix.split())[-220:]
    if re.search(r"\b(?:no|nunca|tampoco)\s*$", prefix):
        return True
    if re.search(r"\bsin\s*$", prefix):
        return True
    if re.search(r"\bsin\s+(?!(?:perjuicio|embargo)\b)(?:\w+\s+){0,3}$", prefix):
        return True
    return bool(re.search(
        r"\b(?:no|nunca|tampoco)\s+(?:se\s+)?(?:"
        r"requ\w*|exig\w*|solicit\w*|necesit\w*|acept\w*|admit\w*|permit\w*|"
        r"es\b|son\b|sera\b|seran\b|debe\w*|resulta\w*|tiene\w*)\b",
        prefix,
    ))


def affirmed_terms(text: str, terms: list[str]) -> list[str]:
    """Return terms with at least one non-negated occurrence in local context."""
    normalized = text.lower().translate(str.maketrans("áéíóúñü", "aeiounu"))
    found = []
    for term in terms:
        term_text = normalize_text_es(term)
        expression = re.escape(term_text).replace(r"\ ", r"\s+")
        if any(not is_negated_match(normalized, match.start(), match.end()) for match in re.finditer(
            rf"(?<!\w){expression}(?!\w)", normalized,
        )):
            found.append(term)
    return unique_strings(found)


def has_concrete_requirement_detail(text: str) -> bool:
    """Check if text contains concrete dates, durations, or mandatory language."""
    if re.search(r"\b\d+\s*(dias|dia|horas|hora|calendario|laborables|habiles|hábiles)\b", text):
        return True
    if re.search(r"\b\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}\b", text):
        return True
    return any(
        term in text
        for term in ["no se aceptan", "solo se acept", "obligatorio", "debera", "deberá", "se requiere"]
    )


def looks_like_structural_text(text: str) -> bool:
    """Detect table-of-contents, index pages, or metadata headers."""
    if "indice financiero" in text:
        return False
    text = normalize_text_es(text)
    if re.fullmatch(r"(?:version|codigo|fecha de impresion)\s*:?\s*[\w./-]+", text):
        return True
    return bool(
        re.match(r"^(?:indice|contenido|tabla de contenido|sumario|portada)(\s|:|$)", text)
        and not has_concrete_requirement_detail(text)
    )


def is_substantive_evidence_text(text: str) -> bool:
    """Check if a text fragment contains enough substance to be review-worthy."""
    normalized = text.lower().translate(str.maketrans("áéíóúñü", "aeiounu"))
    normalized = " ".join(normalized.split())
    if not normalized:
        return False
    if looks_like_structural_text(normalized):
        return False
    generic_timeline = [
        "segun cronograma",
        "conforme al cronograma",
        "consta en el cronograma",
        "establecido en el cronograma",
        "cronograma del procedimiento",
    ]
    if any(term in normalized for term in generic_timeline) and not has_concrete_requirement_detail(normalized):
        return False
    if len(normalized.split()) <= 4 and not has_concrete_requirement_detail(normalized):
        return False
    return True
