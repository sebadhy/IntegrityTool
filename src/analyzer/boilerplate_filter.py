from __future__ import annotations

import re

from .domain_models import Clause, ClauseStatus

IGNORED_EXPRESSIONS = [
    "sin datos",
    "no requerido por la entidad",
    "n/a",
    "no aplica",
    "información no disponible",
    "informacion no disponible",
    "complete aquí",
    "complete aqui",
    "[●]",
    "especificar si corresponde",
    "campo no diligenciado",
]

TEMPLATE_HINTS = ["complete", "especificar", "seleccione", "llenar", "campo"]
INDEX_HINTS = ["índice", "indice", "tabla de contenido", "contenido", "sumario"]
METADATA_HINTS = ["versión", "version", "fecha de impresión", "codigo", "código"]
LEGAL_STANDARD_HINTS = ["ley orgánica", "losncp", "reglamento", "normativa aplicable"]


def classify_clause(clause: Clause) -> Clause:
    text = clause.normalized_text
    status: ClauseStatus = "active_clause"
    reason = ""

    if not text:
        status = "empty_or_no_data"
        reason = "Cláusula vacía o sin texto extraído."
    elif any(expr in text for expr in IGNORED_EXPRESSIONS):
        status = "placeholder"
        reason = "Placeholder o campo sin información sustantiva."
    elif _is_index_or_toc(text):
        status = "index_or_toc"
        reason = "Índice o tabla de contenido."
    elif any(hint in text for hint in TEMPLATE_HINTS):
        status = "template_text"
        reason = "Instrucción de plantilla sin contenido específico."
    elif any(hint in text for hint in METADATA_HINTS) and len(text.split()) <= 12:
        status = "metadata"
        reason = "Metadata administrativa no sustantiva."
    elif any(hint in text for hint in LEGAL_STANDARD_HINTS) and len(text.split()) <= 28:
        status = "legal_standard_clause"
        reason = "Referencia normativa estándar sin requisito específico."
    elif _low_information(text):
        status = "non_substantive_instruction"
        reason = "Texto de baja información para revisión documental."

    return Clause(
        clause_id=clause.clause_id,
        document_id=clause.document_id,
        page=clause.page,
        section_title=clause.section_title,
        section_type=clause.section_type,
        text=clause.text,
        normalized_text=clause.normalized_text,
        clause_status=status,
        exclude_from_detection=status != "active_clause",
        exclusion_reason=reason,
    )


def classify_clauses(clauses: list[Clause]) -> list[Clause]:
    return [classify_clause(clause) for clause in clauses]


def active_clauses(clauses: list[Clause]) -> list[Clause]:
    return [clause for clause in clauses if not clause.exclude_from_detection]



def _has_index_heading(text: str) -> bool:
    if any(hint in text for hint in ["tabla de contenido", "sumario"]):
        return True
    if "indice financiero" in text or "índice financiero" in text:
        return False
    return bool(re.match(r"^(indice|índice|contenido)(\s|:|$)", text))


def _is_index_or_toc(text: str) -> bool:
    if _has_index_heading(text) and len(text.split()) <= 45:
        return True
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    numbered = sum(1 for line in lines if re.match(r"^\d+(\.\d+)*\s+", line))
    dotted_leaders = sum(1 for line in lines if re.search(r"\.{2,}\s*\d+\s*$", line))
    section_references = sum(
        1
        for line in lines
        if re.match(r"^\d+(\.\d+)*[.)]?\s+[a-záéíóúñü]", line) or re.search(r"\s\d{1,3}\s*$", line)
    )
    return bool(
        lines
        and (
            numbered >= max(3, len(lines) // 2)
            or dotted_leaders >= 2
            or (section_references >= 4 and len(text.split()) <= 140)
        )
    )


def _low_information(text: str) -> bool:
    words = re.findall(r"[a-záéíóúñü0-9]+", text)
    return len(set(words)) <= 2 and len(words) <= 5
