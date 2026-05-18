"""
llm_reviewer.py — Lectura asistida por LLM para revisión de pliegos.

Proveedores soportados (prioridad descendente):
  1. Azure OpenAI  — OPENAI_API_KEY + OPENAI_BASE_URL
  2. Groq          — GROQ_API_KEY  (llama-3.3-70b-versatile)

Máximo 2 llamadas LLM por documento: un brief + explicaciones individuales on-demand.
Reintentos automáticos con backoff exponencial para errores 429 de rate limit.
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
from typing import Any

from dotenv import load_dotenv

load_dotenv()

LOGGER = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Eres un asistente técnico para revisión preliminar de neutralidad competitiva en "
    "documentos de contratación pública de Ecuador. Tu función es resumir, contextualizar "
    "y apoyar la priorización de revisión humana a partir de señales documentales ya detectadas. "
    "Puedes apoyarte en principios normativos como concurrencia, igualdad, trato justo, "
    "no discriminación, transparencia, mejor valor por dinero, claridad de especificaciones, "
    "proporcionalidad y justificación técnica. "
    "No emites dictámenes legales, no atribuyes intencionalidad, no infieres proveedores "
    "beneficiados y no inventas evidencia. Si el fragmento no sustenta una señal documental, "
    "responde: No se identifica una señal documental suficiente en el fragmento revisado."
)

UNAVAILABLE = "No disponible"
MAX_DOCUMENT_CHARS = 12_000
MAX_RETRIES = 4
BASE_DELAY = 2.0  # segundos base para backoff


# ---------------------------------------------------------------------------
# Retry con backoff exponencial
# ---------------------------------------------------------------------------

def _is_rate_limit(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "rate_limit" in msg or "ratelimit" in msg or "too many requests" in msg


def _call_with_retry(fn):
    """Ejecuta fn() con hasta MAX_RETRIES reintentos ante rate limit (429)."""
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if _is_rate_limit(exc) and attempt < MAX_RETRIES - 1:
                delay = BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                LOGGER.warning(
                    "Rate limit detectado. Reintentando en %.1fs (intento %d/%d).",
                    delay, attempt + 1, MAX_RETRIES,
                )
                time.sleep(delay)
            else:
                raise
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Factory de cliente LLM
# ---------------------------------------------------------------------------

def _use_azure() -> bool:
    return bool(os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_BASE_URL"))


def _use_groq() -> bool:
    return bool(os.getenv("GROQ_API_KEY"))


def _llm_available() -> bool:
    return _use_azure() or _use_groq()


def _client():
    """Retorna cliente OpenAI-compatible según las variables de entorno disponibles."""
    if _use_azure():
        from openai import AzureOpenAI
        return AzureOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            azure_endpoint=os.getenv("OPENAI_BASE_URL"),
            api_version=os.getenv("OPENAI_API_VERSION", "2024-06-01"),
        )
    if _use_groq():
        from openai import OpenAI
        return OpenAI(
            api_key=os.getenv("GROQ_API_KEY"),
            base_url="https://api.groq.com/openai/v1",
        )
    raise ValueError("Sin LLM configurado. Define OPENAI_API_KEY o GROQ_API_KEY en .env")


def _model() -> str:
    if _use_azure():
        return os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    return os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


def _provider_name() -> str:
    return "Azure OpenAI" if _use_azure() else "Groq"


# ---------------------------------------------------------------------------
# Llamadas principales
# ---------------------------------------------------------------------------

def generate_document_brief(
    document_text: str,
    prioritized_findings: list[dict],
    corpus_context: dict | None = None,
    normative_context: dict | None = None,
) -> dict:
    """Genera un brief ejecutivo a partir del texto del documento y los hallazgos."""
    if not _llm_available():
        return _unavailable_document_brief("Sin API key configurada (OPENAI_API_KEY o GROQ_API_KEY).")

    prompt = _build_document_brief_prompt(
        document_text=document_text,
        findings=prioritized_findings,
        corpus_context=corpus_context,
        normative_context=normative_context,
    )

    try:
        def _call():
            return _client().chat.completions.create(
                model=_model(),
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=1500,
            )

        response = _call_with_retry(_call)
        content = response.choices[0].message.content or "{}"
        return _normalize_document_brief(json.loads(content))
    except Exception as exc:
        LOGGER.warning("Document brief LLM (%s) falló: %s", _provider_name(), exc)
        return _unavailable_document_brief(_friendly_llm_error(exc))


def explain_priority_with_llm(
    priority: dict,
    corpus_context: dict | None = None,
) -> dict:
    """Explica un hallazgo prioritario en lenguaje claro."""
    if not _llm_available():
        return _unavailable_finding_explanation("Sin API key configurada (OPENAI_API_KEY o GROQ_API_KEY).")

    prompt = _build_finding_prompt(finding=priority, corpus_context=corpus_context)

    try:
        def _call():
            return _client().chat.completions.create(
                model=_model(),
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=800,
            )

        response = _call_with_retry(_call)
        content = response.choices[0].message.content or "{}"
        return _normalize_finding_explanation(json.loads(content))
    except Exception as exc:
        LOGGER.warning("Finding explanation LLM (%s) falló: %s", _provider_name(), exc)
        return _unavailable_finding_explanation(_friendly_llm_error(exc))


def explain_finding_with_llm(
    finding: dict,
    corpus_context: dict | None = None,
) -> dict:
    return explain_priority_with_llm(finding, corpus_context)


def review_detection_with_llm(detection: dict) -> dict:
    explanation = explain_finding_with_llm(detection)
    return {
        "llm_explanation": explanation["plain_language_explanation"],
        "human_review_questions": [explanation["suggested_review_action"]],
        "possible_legitimate_justification": explanation["possible_legitimate_justification"],
        "recommended_action": explanation["suggested_review_action"],
    }


def test_llm_connection() -> tuple[bool, str]:
    """Verifica la conexión con el proveedor LLM activo."""
    if not _llm_available():
        return False, "Sin API key configurada. Define OPENAI_API_KEY (Azure) o GROQ_API_KEY (Groq)."

    try:
        def _call():
            return _client().chat.completions.create(
                model=_model(),
                messages=[
                    {"role": "system", "content": "Responde de forma breve y técnica."},
                    {"role": "user", "content": "Responde exactamente: OK"},
                ],
                max_tokens=10,
            )

        response = _call_with_retry(_call)
        content = (response.choices[0].message.content or "").strip()
        if content:
            return True, f"Conexión {_provider_name()} OK — modelo: {_model()}"
        return False, "La conexión respondió pero no devolvió contenido."
    except Exception as exc:
        return False, _friendly_llm_error(exc)


# ---------------------------------------------------------------------------
# Construcción de prompts
# ---------------------------------------------------------------------------

def _build_document_brief_prompt(
    document_text: str,
    findings: list[dict],
    corpus_context: dict | None,
    normative_context: dict | None,
) -> str:
    from .taxonomy_loader import taxonomy_context

    representative_text = _representative_document_excerpt(document_text, findings)
    findings_summary = _findings_summary(findings)
    comparative_summary = _comparative_summary(findings, corpus_context)

    return (
        "Genera una lectura preliminar asistida para revisión humana de neutralidad competitiva.\n\n"
        "Condiciones:\n"
        "- Usa únicamente el extracto documental, las señales sugeridas y el contexto comparativo provisto.\n"
        "- No inventes señales nuevas ni concluyas sin evidencia.\n"
        "- No emitas dictámenes legales ni atribuyas intencionalidad.\n"
        "- Distingue requisitos habituales de señales atípicas.\n"
        "- Reconoce mitigantes como equivalentes funcionales, consorcios, apertura a extranjeros.\n"
        "- Usa lenguaje prudente: señales preliminares, posible restricción, revisión humana sugerida.\n\n"
        "Devuelve ÚNICAMENTE un JSON con estas claves exactas:\n"
        "{\n"
        '  "document_summary": "...",\n'
        '  "overall_attention_level": "Bajo|Medio|Alto",\n'
        '  "main_review_topics": ["...", "..."],\n'
        '  "possible_competition_effects": "...",\n'
        '  "comparative_context": "...",\n'
        '  "top_priorities_rationale": ["...", "..."],\n'
        '  "suggested_human_review_questions": ["...", "..."],\n'
        '  "methodological_note": "..."\n'
        "}\n\n"
        f"Extracto representativo del documento (máx {MAX_DOCUMENT_CHARS} caracteres):\n"
        f"{representative_text}\n\n"
        "Señales sugeridas para revisión:\n"
        f"{json.dumps(findings_summary, ensure_ascii=False, indent=2)}\n\n"
        "Contexto comparativo del corpus:\n"
        f"{json.dumps(comparative_summary, ensure_ascii=False, indent=2)}\n\n"
        "Capa normativa orientativa:\n"
        f"{json.dumps(normative_context or _default_normative_context(), ensure_ascii=False, indent=2)}\n\n"
        "Taxonomía documental:\n"
        f"{json.dumps(taxonomy_context(), ensure_ascii=False, indent=2)}\n"
    )


def _build_finding_prompt(finding: dict, corpus_context: dict | None) -> str:
    from .taxonomy_loader import taxonomy_context

    pattern = str(finding.get("patrón detectado", "No disponible"))
    context = (corpus_context or {}).get(pattern, {})

    return (
        "Explica una señal sugerida para revisión humana de forma clara y prudente.\n\n"
        "Condiciones:\n"
        "- La señal fue detectada por reglas; no inventes señales adicionales.\n"
        "- No emitas dictámenes legales ni atribuyas intencionalidad.\n"
        "- Distingue si es requisito habitual, mitigante o señal que requiere revisión.\n"
        "- Usa lenguaje técnico, breve y orientado a decisión.\n\n"
        "Devuelve ÚNICAMENTE un JSON con estas claves exactas:\n"
        "{\n"
        '  "plain_language_explanation": "...",\n'
        '  "why_it_matters": "...",\n'
        '  "possible_legitimate_justification": "...",\n'
        '  "suggested_review_action": "...",\n'
        '  "questions_for_reviewer": ["...", "..."]\n'
        "}\n\n"
        f"Señal:\n{json.dumps(_compact_finding(finding), ensure_ascii=False, indent=2)}\n\n"
        f"Contexto histórico del patrón:\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
        f"Taxonomía de referencia:\n{json.dumps(taxonomy_context(limit=6), ensure_ascii=False, indent=2)}\n"
    )


# ---------------------------------------------------------------------------
# Helpers de datos
# ---------------------------------------------------------------------------

def _representative_document_excerpt(document_text: str, findings: list[dict]) -> str:
    fragments = []
    seen: set[str] = set()
    for finding in findings:
        fragment = str(finding.get("fragmento textual", "")).strip()
        if fragment and fragment not in seen:
            fragments.append(fragment)
            seen.add(fragment)
        if sum(len(f) for f in fragments) >= 6_000:
            break

    prioritized = "\n\n".join(fragments)
    remaining = max(0, MAX_DOCUMENT_CHARS - len(prioritized))
    excerpt = f"Secciones con señales:\n{prioritized}\n\nInicio del documento:\n{document_text[:remaining]}"
    return excerpt[:MAX_DOCUMENT_CHARS]


def _findings_summary(findings: list[dict], max_items: int = 18) -> list[dict[str, Any]]:
    priority_map = {"Alto": 0, "Medio": 1, "Bajo": 2}
    sorted_findings = sorted(
        findings,
        key=lambda item: (
            priority_map.get(str(item.get("atención sugerida") or item.get("nivel de atención")), 3),
            str(item.get("clasificación histórica", "")),
        ),
    )
    return [_compact_finding(f) for f in sorted_findings[:max_items]]


def _compact_finding(finding: dict) -> dict[str, Any]:
    return {
        "signal_id": finding.get("signal_id", UNAVAILABLE),
        "tipo_senal": finding.get("tipo_señal", "señal_revision"),
        "tema": finding.get("tema de revisión", UNAVAILABLE),
        "pagina": finding.get("página", UNAVAILABLE),
        "patron": finding.get("patrón detectado", UNAVAILABLE),
        "pattern_id": finding.get("pattern_id", UNAVAILABLE),
        "pattern_name": finding.get("pattern_name", finding.get("patrón detectado", UNAVAILABLE)),
        "dimension_competitiva": finding.get("competition_dimension", finding.get("dimensión competitiva", UNAVAILABLE)),
        "seccion_documental": finding.get("document_section", finding.get("sección documental probable", UNAVAILABLE)),
        "categoria_revision": finding.get("categoría de revisión", UNAVAILABLE),
        "atencion_sugerida": finding.get("atención sugerida", finding.get("nivel de atención", UNAVAILABLE)),
        "clasificacion_historica": finding.get("clasificación histórica", UNAVAILABLE),
        "frecuencia_corpus": finding.get("frecuencia en corpus", UNAVAILABLE),
        "comentario_contextual": finding.get("comentario contextual", UNAVAILABLE),
        "criterio_priorizacion": finding.get("explicacion_priorizacion", finding.get("por qué se sugiere revisar", UNAVAILABLE)),
        "prioridad_revision": finding.get("prioridad de revisión", finding.get("review_priority", UNAVAILABLE)),
        "factores_mitigantes": finding.get("mitigating_factors", []),
        "justificaciones_posibles": finding.get("possible_legitimate_justifications", []),
        "informacion_faltante": finding.get("missing_information", []),
        "posible_efecto_concurrencia": finding.get("posible efecto sobre concurrencia", UNAVAILABLE),
        "criterio_normativo": finding.get("criterio_normativo_de_revision", UNAVAILABLE),
        "pregunta_normativa": finding.get("pregunta_normativa_sugerida", UNAVAILABLE),
        "fragmento": finding.get("fragmento textual", UNAVAILABLE),
    }


def _comparative_summary(findings: list[dict], corpus_context: dict | None) -> dict[str, Any]:
    if not corpus_context:
        return {"estado": UNAVAILABLE}
    patterns = sorted({str(f.get("patrón detectado", "")) for f in findings})
    return {p: corpus_context.get(p, {}) for p in patterns if p}


# ---------------------------------------------------------------------------
# Normalización de respuestas LLM
# ---------------------------------------------------------------------------

def _normalize_document_brief(brief: dict[str, Any]) -> dict:
    return {
        "document_summary": str(brief.get("document_summary") or UNAVAILABLE),
        "overall_attention_level": _normalize_attention(brief.get("overall_attention_level")),
        "main_review_topics": _normalize_list(brief.get("main_review_topics")),
        "possible_competition_effects": str(brief.get("possible_competition_effects") or UNAVAILABLE),
        "comparative_context": str(brief.get("comparative_context") or UNAVAILABLE),
        "top_priorities_rationale": _normalize_list(brief.get("top_priorities_rationale")),
        "suggested_human_review_questions": _normalize_list(brief.get("suggested_human_review_questions")),
        "methodological_note": str(brief.get("methodological_note") or UNAVAILABLE),
    }


def _normalize_finding_explanation(explanation: dict[str, Any]) -> dict:
    return {
        "plain_language_explanation": str(explanation.get("plain_language_explanation") or UNAVAILABLE),
        "why_it_matters": str(explanation.get("why_it_matters") or UNAVAILABLE),
        "possible_legitimate_justification": str(explanation.get("possible_legitimate_justification") or UNAVAILABLE),
        "suggested_review_action": str(explanation.get("suggested_review_action") or UNAVAILABLE),
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
    v = str(value or "").strip()
    return v if v in {"Bajo", "Medio", "Alto"} else UNAVAILABLE


# ---------------------------------------------------------------------------
# Fallbacks cuando el LLM no está disponible
# ---------------------------------------------------------------------------

def _unavailable_document_brief(reason: str = UNAVAILABLE) -> dict:
    return {
        "document_summary": UNAVAILABLE,
        "overall_attention_level": UNAVAILABLE,
        "main_review_topics": [UNAVAILABLE],
        "possible_competition_effects": UNAVAILABLE,
        "comparative_context": UNAVAILABLE,
        "top_priorities_rationale": [UNAVAILABLE],
        "suggested_human_review_questions": [UNAVAILABLE],
        "methodological_note": UNAVAILABLE,
        "llm_available": False,
        "llm_error": reason,
    }


def _unavailable_finding_explanation(reason: str = UNAVAILABLE) -> dict:
    return {
        "plain_language_explanation": "La explicación asistida por IA no está disponible.",
        "why_it_matters": "Se mantiene el análisis basado en reglas y contexto comparativo.",
        "possible_legitimate_justification": "Revise la justificación legítima del análisis estructurado.",
        "suggested_review_action": "Use la evidencia textual, mitigantes y preguntas ya mostradas.",
        "questions_for_reviewer": [
            "¿La señal tiene justificación técnica proporcional en el documento?",
            "¿Existen mitigantes o equivalencias aplicables en la práctica?",
        ],
        "llm_available": False,
        "llm_error": reason,
    }


def _friendly_llm_error(exc: Exception) -> str:
    msg = str(exc)
    lower = msg.lower()
    if "insufficient_quota" in lower or "quota" in lower:
        return "Sin cuota o crédito disponible para el modelo configurado."
    if "authentication" in lower or "api key" in lower or "401" in lower:
        return "API key no autenticada. Verifique OPENAI_API_KEY o GROQ_API_KEY."
    if "connection" in lower or "timeout" in lower:
        return "No se pudo conectar con el proveedor LLM. Revise red o OPENAI_BASE_URL."
    if "model" in lower and ("not found" in lower or "does not exist" in lower):
        return "El modelo configurado no está disponible. Revise OPENAI_MODEL o GROQ_MODEL."
    if "429" in msg or "rate_limit" in lower:
        return f"Rate limit agotado después de {MAX_RETRIES} reintentos. Intente más tarde."
    return f"Error LLM: {msg[:240]}"


def _default_normative_context() -> dict[str, list[str]]:
    return {
        "principios": [
            "concurrencia",
            "igualdad y no discriminación",
            "trato justo",
            "transparencia",
            "mejor valor por dinero",
            "claridad y no ambigüedad de especificaciones",
            "proporcionalidad",
            "justificación técnica",
            "consistencia documental",
            "uso adecuado de CPC",
        ]
    }
