from __future__ import annotations

import json
import logging
import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()

LOGGER = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Eres un asistente técnico para revisión preliminar de neutralidad competitiva en "
    "documentos de contratación pública de Ecuador. Tu función es resumir, contextualizar "
    "y apoyar la priorización de revisión humana. Puedes apoyarte en principios normativos "
    "como concurrencia, igualdad, trato justo, no discriminación, transparencia, mejor valor "
    "por dinero, claridad de especificaciones, proporcionalidad y justificación técnica. "
    "No emites dictámenes legales ni concluyes ilegalidad, corrupción, direccionamiento "
    "contractual o responsabilidad administrativa."
)

DEFAULT_MODEL = "gpt-5.4-mini"
UNAVAILABLE = "No disponible"
MAX_DOCUMENT_CHARS = 12_000

DOCUMENT_BRIEF_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "document_review_brief",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "document_summary": {"type": "string"},
                "main_review_topics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 6,
                },
                "overall_attention_level": {
                    "type": "string",
                    "enum": ["Bajo", "Medio", "Alto"],
                },
                "possible_competition_effects": {"type": "string"},
                "comparative_context": {"type": "string"},
                "top_priorities_rationale": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 5,
                },
                "suggested_human_review_questions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 6,
                },
                "methodological_note": {"type": "string"},
            },
            "required": [
                "document_summary",
                "overall_attention_level",
                "main_review_topics",
                "possible_competition_effects",
                "comparative_context",
                "top_priorities_rationale",
                "suggested_human_review_questions",
                "methodological_note",
            ],
        },
    },
}

FINDING_EXPLANATION_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "finding_review_explanation",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "plain_language_explanation": {"type": "string"},
                "why_it_matters": {"type": "string"},
                "possible_legitimate_justification": {"type": "string"},
                "suggested_review_action": {"type": "string"},
                "questions_for_reviewer": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 4,
                },
            },
            "required": [
                "plain_language_explanation",
                "why_it_matters",
                "possible_legitimate_justification",
                "suggested_review_action",
                "questions_for_reviewer",
            ],
        },
    },
}


def generate_document_brief(
    document_text: str,
    prioritized_findings: list[dict],
    corpus_context: dict | None = None,
    normative_context: dict | None = None,
) -> dict:
    """Generate a cautious executive brief from document text and prior rule findings."""
    if not os.getenv("OPENAI_API_KEY"):
        return _unavailable_document_brief()

    try:
        response = _client().chat.completions.create(
            model=os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": _build_document_brief_prompt(
                        document_text=document_text,
                        findings=prioritized_findings,
                        corpus_context=corpus_context,
                        normative_context=normative_context,
                    ),
                },
            ],
            response_format=DOCUMENT_BRIEF_SCHEMA,
        )
        content = response.choices[0].message.content or "{}"
        return _normalize_document_brief(json.loads(content))
    except Exception as exc:
        LOGGER.warning("Document brief LLM failed: %s", exc)
        return _unavailable_document_brief()


def explain_priority_with_llm(
    priority: dict,
    corpus_context: dict | None = None,
) -> dict:
    """Explain one prioritized signal in plain language."""
    if not os.getenv("OPENAI_API_KEY"):
        return _unavailable_finding_explanation()

    try:
        response = _client().chat.completions.create(
            model=os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": _build_finding_prompt(
                        finding=priority,
                        corpus_context=corpus_context,
                    ),
                },
            ],
            response_format=FINDING_EXPLANATION_SCHEMA,
        )
        content = response.choices[0].message.content or "{}"
        return _normalize_finding_explanation(json.loads(content))
    except Exception as exc:
        LOGGER.warning("Finding explanation LLM failed: %s", exc)
        return _unavailable_finding_explanation()


def explain_finding_with_llm(
    finding: dict,
    corpus_context: dict | None = None,
) -> dict:
    """Backward-compatible wrapper for previous UI paths."""
    return explain_priority_with_llm(finding, corpus_context)


def review_detection_with_llm(detection: dict) -> dict:
    """Backward-compatible wrapper for older UI paths."""
    explanation = explain_finding_with_llm(detection)
    return {
        "llm_explanation": explanation["plain_language_explanation"],
        "human_review_questions": [explanation["suggested_review_action"]],
        "possible_legitimate_justification": explanation["possible_legitimate_justification"],
        "recommended_action": explanation["suggested_review_action"],
    }


def test_llm_connection() -> tuple[bool, str]:
    """Check API key presence and perform a minimal model call."""
    if not os.getenv("OPENAI_API_KEY"):
        return False, "OPENAI_API_KEY no está configurada."

    try:
        response = _client().chat.completions.create(
            model=os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
            messages=[
                {
                    "role": "system",
                    "content": "Responde de forma breve y técnica.",
                },
                {
                    "role": "user",
                    "content": "Responde exactamente: OK",
                },
            ],
        )
        content = (response.choices[0].message.content or "").strip()
        if content:
            return True, "Conexión LLM OK"
        return False, "La conexión respondió, pero no devolvió contenido."
    except Exception as exc:
        return False, _friendly_llm_error(exc)


def _client() -> OpenAI:
    return OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL") or None,
    )


def _friendly_llm_error(exc: Exception) -> str:
    message = str(exc)
    lower_message = message.lower()
    if "insufficient_quota" in lower_message or "quota" in lower_message:
        return "No hay cuota o crédito disponible para usar el modelo configurado."
    if "authentication" in lower_message or "api key" in lower_message or "401" in lower_message:
        return "La API key no pudo autenticarse. Verifique OPENAI_API_KEY."
    if "connection" in lower_message or "timeout" in lower_message:
        return "No se pudo conectar con el proveedor LLM. Revise red o OPENAI_BASE_URL."
    if "model" in lower_message and ("not found" in lower_message or "does not exist" in lower_message):
        return "El modelo configurado no está disponible. Revise OPENAI_MODEL."
    return f"No se pudo verificar la conexión LLM: {message[:240]}"


def _build_document_brief_prompt(
    document_text: str,
    findings: list[dict],
    corpus_context: dict | None,
    normative_context: dict | None,
) -> str:
    representative_text = _representative_document_excerpt(document_text, findings)
    findings_summary = _findings_summary(findings)
    comparative_summary = _comparative_summary(findings, corpus_context)

    return (
        "Genera una lectura preliminar asistida para revisión humana de un documento de "
        "contratación pública, con foco en neutralidad competitiva.\n\n"
        "Condiciones:\n"
        "- Usa únicamente el extracto documental, las señales sugeridas y el contexto comparativo provisto.\n"
        "- No inventes señales nuevas ni agregues conclusiones no soportadas.\n"
        "- No emitas dictámenes legales ni asignes responsabilidad.\n"
        "- No atribuyas intencionalidad.\n"
        "- Usa la capa normativa solo como referencia orientativa para revisión humana.\n"
        "- Distingue requisitos regulatorios o habituales de señales atípicas o acumuladas.\n"
        "- Reconoce mitigantes como equivalentes funcionales, consorcios, apertura a oferentes "
        "extranjeros, criterios funcionales o pluralidad de marcas.\n"
        "- Si un criterio parece razonable o estándar, dilo expresamente con lenguaje prudente.\n"
        "- Usa lenguaje prudente: señales de restricción competitiva, requisitos potencialmente "
        "limitantes, baja neutralidad competitiva, condiciones que podrían reducir concurrencia, "
        "validación de proporcionalidad, revisión humana sugerida, posible afectación a concurrencia.\n"
        "- Devuelve únicamente JSON estricto con las claves solicitadas.\n\n"
        "Objeto de contratación: No disponible en el documento cargado.\n\n"
        f"Extracto representativo del documento (máximo {MAX_DOCUMENT_CHARS} caracteres):\n"
        f"{representative_text}\n\n"
        "Señales sugeridas para revisión, derivadas del análisis previo:\n"
        f"{json.dumps(findings_summary, ensure_ascii=False, indent=2)}\n\n"
        "Frecuencias comparativas y contexto del corpus, si está disponible:\n"
        f"{json.dumps(comparative_summary, ensure_ascii=False, indent=2)}\n"
        "\nCapa normativa orientativa curada:\n"
        f"{json.dumps(normative_context or _default_normative_context(), ensure_ascii=False, indent=2)}\n"
    )


def _build_finding_prompt(finding: dict, corpus_context: dict | None) -> str:
    pattern = str(finding.get("patrón detectado", "No disponible"))
    context = (corpus_context or {}).get(pattern, {})

    return (
        "Explica una señal sugerida para revisión humana de forma clara y prudente.\n\n"
        "Condiciones:\n"
        "- La señal ya fue detectada por reglas; no inventes señales adicionales.\n"
        "- No emitas dictámenes legales ni asignes responsabilidad.\n"
        "- Usa la referencia normativa de la señal solo como apoyo orientativo.\n"
        "- Distingue si se trata de un requisito habitual, un mitigante o una señal que requiere revisión.\n"
        "- Reconoce factores que favorecen concurrencia y explica si reducen la atención sugerida.\n"
        "- No atribuyas intencionalidad.\n"
        "- Usa lenguaje técnico, breve y orientado a decisión.\n"
        "- Devuelve únicamente JSON estricto con las claves solicitadas.\n\n"
        f"Señal sugerida:\n{json.dumps(_compact_finding(finding), ensure_ascii=False, indent=2)}\n\n"
        f"Contexto histórico del patrón:\n{json.dumps(context, ensure_ascii=False, indent=2)}\n"
    )


def _representative_document_excerpt(document_text: str, findings: list[dict]) -> str:
    fragments = []
    seen = set()
    for finding in findings:
        fragment = str(finding.get("fragmento textual", "")).strip()
        if fragment and fragment not in seen:
            fragments.append(fragment)
            seen.add(fragment)
        if sum(len(item) for item in fragments) >= 6_000:
            break

    prioritized = "\n\n".join(fragments)
    remaining_budget = max(0, MAX_DOCUMENT_CHARS - len(prioritized))
    document_start = document_text[:remaining_budget]
    excerpt = f"Secciones con señales sugeridas:\n{prioritized}\n\nInicio del documento:\n{document_start}"
    return excerpt[:MAX_DOCUMENT_CHARS]


def _findings_summary(findings: list[dict], max_items: int = 18) -> list[dict[str, Any]]:
    priority = {"Alto": 0, "Medio": 1, "Bajo": 2}
    sorted_findings = sorted(
        findings,
        key=lambda item: (
            priority.get(str(item.get("atención sugerida") or item.get("nivel de atención")), 3),
            str(item.get("clasificación histórica", "")),
        ),
    )
    return [_compact_finding(finding) for finding in sorted_findings[:max_items]]


def _compact_finding(finding: dict) -> dict[str, Any]:
    return {
        "signal_id": finding.get("signal_id", "No disponible"),
        "tipo_senal": finding.get("tipo_señal", "señal_revision"),
        "tema": finding.get("tema de revisión", "No disponible"),
        "pagina": finding.get("página", "No disponible"),
        "patron": finding.get("patrón detectado", "No disponible"),
        "categoria_revision": finding.get("categoría de revisión", "No disponible"),
        "atencion_sugerida": finding.get(
            "atención sugerida",
            finding.get("nivel de atención", "No disponible"),
        ),
        "clasificacion_historica": finding.get("clasificación histórica", "No disponible"),
        "frecuencia_corpus": finding.get("frecuencia en corpus", "No disponible"),
        "comentario_contextual": finding.get("comentario contextual", "No disponible"),
        "criterio_priorizacion": finding.get(
            "explicacion_priorizacion",
            finding.get(
                "por qué se sugiere revisar",
                finding.get("validación sugerida", "No disponible"),
            ),
        ),
        "criterios_de_priorizacion": finding.get(
            "criterios_de_priorizacion",
            finding.get("validación sugerida", "No disponible"),
        ),
        "posible_efecto_sobre_concurrencia": finding.get(
            "posible efecto sobre concurrencia",
            "No disponible",
        ),
        "criterio_normativo": finding.get("criterio_normativo_de_revision", "No disponible"),
        "pregunta_normativa": finding.get("pregunta_normativa_sugerida", "No disponible"),
        "elementos_que_favorecen_concurrencia": finding.get(
            "elementos que favorecen concurrencia",
            "No disponible",
        ),
        "fragmento": finding.get("fragmento textual", "No disponible"),
    }


def _comparative_summary(
    findings: list[dict],
    corpus_context: dict | None,
) -> dict[str, Any]:
    if not corpus_context:
        return {"estado": "No disponible"}

    patterns = sorted({str(finding.get("patrón detectado", "")) for finding in findings})
    return {
        pattern: corpus_context.get(pattern, {})
        for pattern in patterns
        if pattern
    }


def _normalize_document_brief(brief: dict[str, Any]) -> dict:
    return {
        "document_summary": str(brief.get("document_summary") or UNAVAILABLE),
        "overall_attention_level": _normalize_attention(brief.get("overall_attention_level")),
        "main_review_topics": _normalize_list(brief.get("main_review_topics")),
        "possible_competition_effects": str(
            brief.get("possible_competition_effects") or UNAVAILABLE
        ),
        "comparative_context": str(brief.get("comparative_context") or UNAVAILABLE),
        "top_priorities_rationale": _normalize_list(brief.get("top_priorities_rationale")),
        "suggested_human_review_questions": _normalize_list(
            brief.get("suggested_human_review_questions")
        ),
        "methodological_note": str(brief.get("methodological_note") or UNAVAILABLE),
    }


def _normalize_finding_explanation(explanation: dict[str, Any]) -> dict:
    return {
        "plain_language_explanation": str(
            explanation.get("plain_language_explanation") or UNAVAILABLE
        ),
        "why_it_matters": str(explanation.get("why_it_matters") or UNAVAILABLE),
        "possible_legitimate_justification": str(
            explanation.get("possible_legitimate_justification") or UNAVAILABLE
        ),
        "suggested_review_action": str(
            explanation.get("suggested_review_action") or UNAVAILABLE
        ),
        "questions_for_reviewer": _normalize_list(explanation.get("questions_for_reviewer")),
    }


def _normalize_list(value: Any) -> list[str]:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return items or [UNAVAILABLE]
    if value:
        return [str(value)]
    return [UNAVAILABLE]


def _normalize_attention(value: Any) -> str:
    value_text = str(value or "").strip()
    if value_text in {"Bajo", "Medio", "Alto"}:
        return value_text
    return UNAVAILABLE


def _unavailable_document_brief() -> dict:
    return {
        "document_summary": UNAVAILABLE,
        "overall_attention_level": UNAVAILABLE,
        "main_review_topics": [UNAVAILABLE],
        "possible_competition_effects": UNAVAILABLE,
        "comparative_context": UNAVAILABLE,
        "top_priorities_rationale": [UNAVAILABLE],
        "suggested_human_review_questions": [UNAVAILABLE],
        "methodological_note": UNAVAILABLE,
    }


def _unavailable_finding_explanation() -> dict:
    return {
        "plain_language_explanation": UNAVAILABLE,
        "why_it_matters": UNAVAILABLE,
        "possible_legitimate_justification": UNAVAILABLE,
        "suggested_review_action": UNAVAILABLE,
        "questions_for_reviewer": [UNAVAILABLE],
    }


def _default_normative_context() -> dict[str, list[str]]:
    return {
        "principios": [
            "concurrencia",
            "igualdad y no discriminación",
            "trato justo",
            "transparencia",
            "mejor valor por dinero",
            "claridad, completitud y no ambigüedad de especificaciones",
            "especificaciones relacionadas con bienes/rubros y no con proveedores",
            "necesidad de justificación técnica o jurídica cuando un requisito pueda limitar competencia",
            "proporcionalidad",
            "consistencia entre pliego y anexos",
            "uso adecuado de CPC",
        ]
    }
