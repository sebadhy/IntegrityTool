"""Bounded semantic proposals, grounded in archived clauses and taxonomy.

Citation validation is not validation of the interpretation. All outputs remain
preliminary inputs for human review, not technical or legal determinations.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict, deque
from dataclasses import dataclass

from .detector import GOODS_COMMON_PATTERN_IDS, STRONG_RESTRICTIVE_TERMS
from .domain_models import Clause, Signal
from .taxonomy_loader import TaxonomyLoadResult, TaxonomyPattern
from .text_utils import affirmed_terms, is_negated_match, is_substantive_evidence_text, normalize_text_es

SEMANTIC_VERSION = "2026.10.semantic-v1"
MAX_SOURCE_CHARS = 12000
MAX_CONTEXT_CHARS = 19000
MAX_CLAUSES = 24
MAX_CLAUSE_CHARS = 1600
MAX_CANDIDATES = 4


@dataclass
class SemanticSelection:
    clauses: list[Clause]
    patterns: list[TaxonomyPattern]
    payload: dict
    coverage: dict


def select_semantic_context(documents: list[dict], taxonomy: TaxonomyLoadResult) -> SemanticSelection:
    """Sample sections/documents round-robin; never truncate a source clause."""
    superseded = {doc["supersedes"] for doc in documents if doc.get("supersedes")}
    catalogue, patterns = [], []
    for pattern in taxonomy.patterns:
        entry = {"id": pattern.id, "name": pattern.name, "description": pattern.description[:180],
                 "semantic_signals": [s[:120] for s in pattern.semantic_signals[:2]],
                 "mitigants": [s[:85] for s in pattern.mitigating_factors[:2]]}
        if len(json.dumps(catalogue + [entry], ensure_ascii=False)) > 9000:
            continue
        catalogue.append(entry)
        patterns.append(pattern)
    payload = {"patterns": catalogue, "clauses": []}
    queues = defaultdict(deque)
    coverage = {"status": "selected", "strategy": "document_section_round_robin",
                "active_clause_count": 0, "selected_clause_count": 0, "excluded_clause_count": 0,
                "oversized_clause_count": 0, "selected_clause_ids": [], "documents": [],
                "pattern_ids": [p.id for p in patterns],
                "omitted_pattern_ids": [p.id for p in taxonomy.patterns if p not in patterns],
                "limitation": "Selección acotada de cláusulas. No constituye una revisión semántica completa del expediente."}
    for doc in documents:
        record = {"document_id": doc["id"], "name": doc["name"], "active": 0, "selected": 0,
                  "superseded": doc["id"] in superseded}
        coverage["documents"].append(record)
        if record["superseded"]:
            continue
        for raw in doc.get("analysis", {}).get("clauses", []):
            clause = Clause(**raw)
            if clause.exclude_from_detection or clause.clause_status != "active_clause":
                coverage["excluded_clause_count"] += 1
                continue
            coverage["active_clause_count"] += 1
            record["active"] += 1
            if len(clause.text) > MAX_CLAUSE_CHARS:
                coverage["oversized_clause_count"] += 1
                continue
            if is_substantive_evidence_text(clause.text):
                queues[(doc["id"], clause.section_type)].append((clause, doc, record))
    chosen, text_chars = [], 0
    while any(queues.values()) and len(chosen) < MAX_CLAUSES:
        for queue in queues.values():
            if not queue or len(chosen) >= MAX_CLAUSES:
                continue
            clause, doc, record = queue.popleft()
            entry = {"clause_id": clause.clause_id, "document_ref": clause.document_id,
                     "document_name": doc["name"], "role": doc["role"], "version": doc["version"],
                     "page": clause.page, "section": clause.section_title, "text": clause.text}
            proposed = {**payload, "clauses": payload["clauses"] + [entry]}
            if (text_chars + len(clause.text) > MAX_SOURCE_CHARS
                    or len(json.dumps(proposed, ensure_ascii=False)) > MAX_CONTEXT_CHARS):
                continue
            payload = proposed
            chosen.append(clause)
            record["selected"] += 1
            text_chars += len(clause.text)
    coverage.update(selected_clause_count=len(chosen), selected_clause_ids=[c.clause_id for c in chosen],
                    source_chars=text_chars, partial=(len(chosen) < coverage["active_clause_count"]
                                                     or bool(coverage["omitted_pattern_ids"])))
    return SemanticSelection(chosen, patterns, payload, coverage)


def validate_semantic_proposals(payload: dict, selection: SemanticSelection,
                                existing_signals: list[Signal]) -> tuple[list[Signal], list[dict]]:
    """Validate identity, quotation, substantive source and permitted taxonomy.

    Models cannot supply ranking factors or neutralize another requirement.
    The full source clause is retained to avoid dropping local negations.
    """
    patterns = {p.id: p for p in selection.patterns}
    clauses = {c.clause_id: c for c in selection.clauses}
    seen = {(s.pattern_id, s.clause_id) for s in existing_signals}
    if not isinstance(payload, dict) or "candidates" not in payload:
        raise ValueError("Respuesta semántica con formato no válido.")
    proposals = payload.get("candidates", [])
    if not isinstance(proposals, list) or len(proposals) > MAX_CANDIDATES:
        raise ValueError("La respuesta semántica excede el contrato de candidatos.")
    signals, decisions = [], []
    for index, proposal in enumerate(proposals):
        reason = ""
        if not isinstance(proposal, dict):
            decisions.append({"index": index, "status": "rejected", "reason": "Formato no válido."})
            continue
        pattern_id, clause_id = proposal.get("pattern_id"), proposal.get("clause_id")
        pattern = patterns.get(pattern_id) if isinstance(pattern_id, str) else None
        clause = clauses.get(clause_id) if isinstance(clause_id, str) else None
        quote = proposal.get("quote", "")
        note = proposal.get("review_note", "")
        confidence = proposal.get("confidence")
        if set(proposal) != {"pattern_id", "clause_id", "quote", "review_note", "confidence"}:
            reason = "Campos no admitidos o incompletos; el modelo no asigna prioridad."
        elif not pattern:
            reason = "Patrón fuera de la copia de taxonomía enviada."
        elif not clause or clause.exclude_from_detection or clause.clause_status != "active_clause":
            reason = "Cláusula no enviada, excluida o no activa."
        elif not isinstance(quote, str) or not 25 <= len(quote.strip()) <= 700 or _space(quote) not in _space(clause.text):
            reason = "La cita no corresponde al texto de la cláusula."
        elif not is_substantive_evidence_text(quote):
            reason = "Fragmento sin contenido sustantivo suficiente."
        elif not isinstance(note, str) or not 20 <= len(note.strip()) <= 700:
            reason = "Explicación vacía o fuera de los límites permitidos."
        elif re.search(r"corrupcion|fraude|ilegal|direccionamiento|direccionad[oa]|colusion|culpable|responsabil|irregularidad|red flag|alto riesgo", normalize_text_es(note)):
            reason = "La explicación no cumple el lenguaje institucional."
        elif not isinstance(confidence, str) or confidence not in {"medium", "high"}:
            reason = "La propuesta no tiene confianza suficiente para integrarse."
        elif (pattern.id, clause.clause_id) in seen:
            reason = "El mismo patrón y cláusula ya fueron identificados."
        elif _negated_requirement(clause.text, quote):
            reason = "La evidencia contiene una negación explícita del requisito."
        decision = {"index": index, "pattern_id": proposal.get("pattern_id"),
                    "clause_id": proposal.get("clause_id"), "quote": quote,
                    "review_note": note, "confidence": confidence,
                    "status": "rejected" if reason else "accepted",
                    "reason": reason or "Cita y origen comprobados; interpretación pendiente de revisión humana."}
        decisions.append(decision)
        if reason:
            continue
        seen.add((pattern.id, clause.clause_id))
        identity = hashlib.sha256(f"{SEMANTIC_VERSION}|{pattern.id}|{clause.clause_id}".encode()).hexdigest()[:20]
        restrictions = affirmed_terms(clause.text, STRONG_RESTRICTIVE_TERMS)
        signals.append(Signal(
            signal_id=f"semantic-{identity}", clause_id=clause.clause_id, pattern_id=pattern.id,
            family=pattern.risk_type, competition_dimension=pattern.competition_dimension,
            signal_type="contextual_review_signal", matched_text=quote, evidence_text=clause.text,
            page=clause.page, section_title=clause.section_title, detector_name=SEMANTIC_VERSION,
            confidence=confidence,
            metadata={"pattern_name": pattern.name, "taxonomy_pattern": pattern.to_dict(),
                      "analysis_source": "semantic_assisted", "semantic_review_note": note,
                      "citation_validated": True, "interpretation_human_validated": False,
                      "restriction_factors": restrictions,
                      "is_common_in_goods_procurement": pattern.id in GOODS_COMMON_PATTERN_IDS},
        ))
    return signals, decisions


def _space(text: str) -> str:
    return " ".join(text.split())


def _negated_requirement(text: str, quote: str) -> bool:
    source, fragment = _space(text), _space(quote)
    start = source.find(fragment)
    if is_negated_match(source, start, start + len(fragment)):
        return True
    return bool(re.match(r"^(?:no|nunca|tampoco)\s+(?:se\s+)?(?:exige|requiere|solicita|es obligatorio|debe)",
                         normalize_text_es(fragment)))
