"""Conservative extraction and comparison of explicit measurable requirements.

Only local, labelled values are extracted. Unknown scope, units, milestones or
operators cause abstention; repetition never increases review priority.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from decimal import Decimal

from .domain_models import Clause, Requirement


VERSION = "explicit_requirement_v1"
LIMITATION = (
    "Cotejo parcial de condiciones explícitas: no resuelve prevalencia documental, "
    "equivalencia funcional ni alcance jurídico. Una diferencia no confirma incompatibilidad."
)
LABELS = {
    "ram": r"(?:memoria\s+ram|ram)",
    "storage": r"(?:almacenamiento|capacidad\s+de\s+almacenamiento)",
    "weight": r"peso",
    "delivery_period": r"plazo\s+de\s+entrega",
    "execution_period": r"plazo\s+de\s+ejecucion",
    "warranty_period": r"(?:plazo\s+de\s+garantia|garantia)",
}
TITLES = {
    "ram": "Memoria RAM", "storage": "Almacenamiento", "weight": "Peso",
    "delivery_period": "Plazo de entrega", "execution_period": "Plazo de ejecución",
    "warranty_period": "Duración de garantía",
}
NUMBER = r"\d+(?:[.,]\d+)?"
OP = r"(?:como\s+)?(?:minim[oa]|maxim[oa]|al\s+menos|hasta|exactamente|igual\s+a|no\s+mayor\s+a|no\s+menor\s+a)"
VALUE = re.compile(
    rf"\s*(?:(?:sera|debera\s+ser|debe\s+ser|es|de|del|:|=)\s*)*"
    rf"(?P<op>{OP})?\s*[:=]?\s*(?P<value>{NUMBER})\s*"
    r"(?P<unit>gb|mb|kg|g|dias?(?:\s+(?:calendario|calendarios|habiles|laborables))?)(?!\w)",
)


def _normalize(text: str) -> str:
    # Keep character offsets so evidence is always sliced from the original text.
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(c))


def _id(prefix: str, value: str) -> str:
    return prefix + hashlib.sha256(value.encode()).hexdigest()[:24]


def extract_requirements(clauses: list[Clause]) -> list[Requirement]:
    requirements = []
    for clause in clauses:
        if clause.exclude_from_detection or clause.clause_status != "active_clause":
            continue
        text = _normalize(clause.text)
        if len(text) != len(clause.text):
            # Do not emit an incorrect literal span for decomposed Unicode text.
            continue
        # Scope must occur in this clause. Never inherit an item from another page.
        scopes = set(re.findall(r"\b(item|lote)\s*(?:n[ro.°º]*\s*)?(\d+)\b", text))
        scope = next(iter(scopes)) if len(scopes) == 1 else None
        item_ref = f"{scope[0]}:{int(scope[1])}" if scope else ""
        for attribute, label in LABELS.items():
            for match in re.finditer(rf"\b{label}\b", text):
                if re.search(r"(?:no\s+se\s+(?:exige|requiere)|no\s+aplica|sin\s+exigencia\s+de)\s*$", text[max(0, match.start() - 45):match.start()]):
                    continue
                value = VALUE.match(text, match.end())
                if not value:
                    continue
                unit = value["unit"]
                is_time = attribute.endswith("_period")
                if is_time != unit.startswith("dia"):
                    continue
                if attribute in {"ram", "storage"} and unit not in {"gb", "mb"}:
                    continue
                if attribute == "weight" and unit not in {"kg", "g"}:
                    continue
                # Do not select one value from ranges, alternatives or compound units.
                tail = text[value.end():value.end() + 24]
                if re.match(r"\s*(?:/|a\s+\d|o\s+\d|y\s+\d|[-–]\s*\d)", tail):
                    continue
                number = Decimal(value["value"].replace(",", "."))
                if number <= 0:
                    continue
                # A three-digit fractional part may be a thousands separator.
                if re.fullmatch(r"\d+[.,]\d{3}", value["value"]):
                    continue
                operator = value["op"] or ""
                comparator = (
                    "min" if re.search(r"minim|al menos|no menor", operator) else
                    "max" if re.search(r"maxim|hasta|no mayor", operator) else
                    "eq" if operator else "unspecified"
                )
                canonical_unit = ("business_days" if re.search(r"habil|laborable", unit) else
                                  "calendar_days" if "calendario" in unit else
                                  "unspecified_days" if is_time else unit)
                end = value.end()
                # Equivalents are recorded only in the local requirement sentence.
                local = re.split(r"[;\n]", text[match.start():end + 100])[0]
                start_context = re.search(r"\b(?:desde|a partir de)\s+(?:(?:la|el|de|del)\s+)*(.*)", local)
                milestones = [name for name, expression in {
                    "contract_signature": r"(?:firma|suscripcion)\s+del\s+contrato",
                    "order_notification": r"notificacion\s+de\s+la\s+orden",
                    "advance_payment": r"(?:pago|recepcion)\s+del\s+anticipo",
                }.items() if start_context and re.search(expression, start_context[1])]
                requirements.append(Requirement(
                    requirement_id=_id("req-", f"{clause.clause_id}|{match.start()}|{end}"),
                    document_id=clause.document_id, clause_id=clause.clause_id,
                    page=clause.page, section_title=clause.section_title,
                    item_ref=item_ref, attribute=attribute, value=format(number.normalize(), "f"),
                    unit=canonical_unit, comparator=comparator,
                    evidence_text=clause.text, matched_text=clause.text[match.start():end],
                    milestone=milestones[0] if len(milestones) == 1 else "",
                    mandatory=bool(re.search(r"\b(debera|debe|obligatorio|se exige)\b", text)),
                    equivalence=bool(re.search(r"\b(?:o equivalente|se aceptan equivalentes)\b", local)),
                ))
    return requirements


def compare_requirements(documents: list[dict]) -> dict:
    superseded = {doc.get("supersedes") for doc in documents if doc.get("supersedes")}
    groups: dict[tuple, dict[str, list[dict]]] = {}
    count = 0
    excluded = {"unknown_scope": 0, "unspecified_condition": 0, "unknown_milestone": 0, "multiple_conditions": 0,
                "no_comparable_document": 0}
    for doc in documents:
        if doc["id"] in superseded:
            continue
        for requirement in doc.get("analysis", {}).get("requirements", []):
            count += 1
            if not requirement["item_ref"]:
                excluded["unknown_scope"] += 1
                continue
            if requirement["comparator"] == "unspecified" or requirement["unit"] == "unspecified_days":
                excluded["unspecified_condition"] += 1
                continue
            if requirement["attribute"].endswith("_period") and not requirement.get("milestone"):
                excluded["unknown_milestone"] += 1
                continue
            key = (requirement["item_ref"], requirement["attribute"], requirement["unit"], requirement.get("milestone", ""))
            source = {**requirement, "source_document_id": doc["id"], "document_name": doc["name"],
                      "document_role": doc["role"], "document_version": doc.get("version", "")}
            groups.setdefault(key, {}).setdefault(doc["id"], []).append(source)
    comparisons = []
    for key, sources in sorted(groups.items()):
        if len(sources) < 2:
            excluded["no_comparable_document"] += sum(map(len, sources.values()))
            continue
        if any(len({(r["value"], r["comparator"]) for r in records}) > 1 for records in sources.values()):
            excluded["multiple_conditions"] += sum(map(len, sources.values()))
            continue
        conditions = {(r["value"], r["comparator"]) for records in sources.values() for r in records}
        evidence = [r for records in sources.values() for r in records]
        comparisons.append({
            "comparison_id": _id("cmp-", repr((key, sorted(r["requirement_id"] for r in evidence)))),
            "item_ref": key[0], "attribute": key[1], "title": TITLES[key[1]], "unit": key[2],
            "status": "different_conditions" if len(conditions) > 1 else "same_explicit_condition",
            "sources": evidence, "limitation": LIMITATION,
            "question": "¿Qué condición corresponde al mismo ítem y debe quedar aclarada antes de aplicar el requisito?",
        })
    return {"version": VERSION, "extracted_count": count, "comparisons": comparisons,
            "abstentions": excluded, "limitation": LIMITATION}
