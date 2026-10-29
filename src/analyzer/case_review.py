"""Evidence-preserving case aggregation. Differences are not legal conclusions."""
from __future__ import annotations

import hashlib
from collections import defaultdict

from .text_utils import normalize_text_es, unique_strings

PRIORITY_ORDER = {"alta": 0, "media": 1, "baja": 2}


def consolidate_case(documents: list[dict]) -> tuple[list[dict], list[dict]]:
    superseded = {doc["supersedes"] for doc in documents if doc.get("supersedes")}
    grouped = defaultdict(list)
    for doc in documents:
        if doc["id"] in superseded:
            continue
        for item in doc.get("analysis", {}).get("items", []):
            key = (item["metadata"]["pattern_id"], item["competition_dimension"])
            grouped[key].append((doc, item))
    output = []
    for (pattern_id, dimension), entries in grouped.items():
        entries.sort(key=lambda entry: PRIORITY_ORDER[entry[1]["review_priority"]])
        base = entries[0][1]
        evidence = []
        seen = set()
        for doc, item in entries:
            for ev in item["evidence_items"]:
                key = (doc["id"], ev["page"], ev["text"])
                if key in seen:
                    continue
                seen.add(key)
                evidence.append({**ev, "document_id": doc["id"], "document_name": doc["name"], "role": doc["role"], "version": doc["version"]})
        output.append({
            "id": "aspect-" + hashlib.sha256(f"{pattern_id}|{dimension}".encode()).hexdigest()[:16],
            "title": base["title"], "pattern_id": pattern_id, "dimension": dimension,
            "dimension_label": base["display_group"], "priority": base["review_priority"],
            "explanation": base["why_it_matters"], "evidence": evidence,
            "occurrence_count": len(evidence),
            "mitigants": unique_strings([m for _, item in entries for m in item["metadata"].get("detected_mitigants", [])]),
            "questions": unique_strings([q for _, item in entries for q in item["suggested_human_review_question"]]),
            "limitations": unique_strings([q for _, item in entries for q in item["limitations"]]),
            "priority_factors": unique_strings([q for _, item in entries for q in item["metadata"].get("ranking_factors", [])]),
            "sources": unique_strings([q for _, item in entries for q in item["metadata"].get("aggregated_sources", [])]),
            "historical_context": base["metadata"].get("historical_context", {}),
            "source_finding_ids": unique_strings([q for _, item in entries for q in item["source_finding_ids"]]),
        })
    output.sort(key=lambda item: (PRIORITY_ORDER[item["priority"]], item["title"]))
    return output, compare_document_versions(documents)


def compare_document_versions(documents: list[dict]) -> list[dict]:
    """Report only verifiable differences between explicitly related documents."""
    by_id = {doc["id"]: doc for doc in documents}
    comparisons = []
    for doc in documents:
        previous = by_id.get(doc.get("supersedes"))
        if not previous:
            continue
        old = _version_references(previous)
        new = _version_references(doc)
        for key in sorted(old.keys() | new.keys()):
            left, right = old.get(key), new.get(key)
            before = _evidence_by_text(left)
            after = _evidence_by_text(right)
            # Moving or repeating a clause is not a substantive textual change.
            if before.keys() == after.keys():
                continue
            comparisons.append({
                "pattern_id": key[0], "dimension": key[1], "title": (right or left)["title"],
                "previous_document_id": previous["id"], "current_document_id": doc["id"],
                "previous_document": previous["name"], "current_document": doc["name"],
                "previous_version": previous["version"], "current_version": doc["version"],
                "previous_evidence": left["evidence_items"] if left else [],
                "current_evidence": right["evidence_items"] if right else [],
                "removed_evidence": [ev for text, ev in before.items() if text not in after],
                "added_evidence": [ev for text, ev in after.items() if text not in before],
                "unchanged_reference_count": len(before.keys() & after.keys()),
                "change": "Referencia textual modificada" if left and right else "Referencia identificada solo en la nueva versión" if right else "Referencia no identificada en la nueva versión",
                "limitation": "Contraste de texto extraído. No confirma modificación jurídica, equivalencia ni contradicción; requiere cotejo humano.",
            })
    return comparisons


def _version_references(document: dict) -> dict:
    grouped = {}
    for item in document.get("analysis", {}).get("items", []):
        key = (item["metadata"]["pattern_id"], item["competition_dimension"])
        if key not in grouped:
            grouped[key] = {"title": item["title"], "evidence_items": []}
        grouped[key]["evidence_items"].extend(item["evidence_items"])
    return grouped


def _evidence_by_text(item: dict | None) -> dict:
    evidence = {}
    for ev in (item or {}).get("evidence_items", []):
        normalized = normalize_text_es(ev.get("text", ""))
        if normalized:
            evidence.setdefault(normalized, ev)
    return evidence
