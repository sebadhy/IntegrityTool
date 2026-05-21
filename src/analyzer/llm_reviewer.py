"""
llm_reviewer.py — Lectura asistida por LLM para revisión de pliegos.

Proveedores soportados (prioridad descendente):
  1. Azure OpenAI  — OPENAI_API_KEY + OPENAI_BASE_URL + OPENAI_API_VERSION
  2. Groq          — GROQ_API_KEY  (modelo: GROQ_MODEL, default: llama-3.3-70b-versatile)
  3. Ollama local  — OLLAMA_BASE_URL (default: http://localhost:11434/v1) + OLLAMA_MODEL
  4. OpenAI directo — OPENAI_API_KEY (sin OPENAI_API_VERSION)

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

from src.config import APP_MAX_DOCUMENT_CHARS, OPENAI_MODEL

from .taxonomy_loader import taxonomy_context


load_dotenv()

LOGGER = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Eres un asistente técnico para revisión preliminar de neutralidad competitiva en "
    "documentos de contratación pública de Ecuador. "
    "Tu lector objetivo es un técnico institucional sin formación legal especializada, "
    "que necesita decidir qué cláusulas del documento merecen revisión más detallada "
    "en los próximos 30 minutos. Escribe de forma concisa, orientada a decisión, "
    "sin adornos ni lenguaje acusatorio. "
    "Tu función es resumir, contextualizar y apoyar la priorización de revisión humana "
    "a partir de señales documentales ya detectadas. Puedes apoyarte en principios normativos "
    "como concurrencia, igualdad, trato justo, no discriminación, transparencia, mejor valor "
    "por dinero, claridad de especificaciones, proporcionalidad y justificación técnica. "
    "No emites dictámenes legales, no atribuyes intencionalidad, no infieres proveedores beneficiados "
    "y no inventas evidencia. Si el fragmento no sustenta una señal documental, responde: "
    "No se identifica una señal documental suficiente en el fragmento revisado."
)

DEFAULT_MODEL = OPENAI_MODEL
UNAVAILABLE = "No disponible"
MAX_DOCUMENT_CHARS = APP_MAX_DOCUMENT_CHARS
MAX_RETRIES = 4
BASE_DELAY = 2.0


# ---------------------------------------------------------------------------
# Detección de proveedor LLM
# ---------------------------------------------------------------------------

def _forced_provider() -> str:
    """LLM_PROVIDER env var fuerza un proveedor específico, ignorando auto-detección."""
    return os.getenv("LLM_PROVIDER", "").lower().strip()


def _use_azure() -> bool:
    if _forced_provider() and _forced_provider() != "azure":
        return False
    return bool(
        os.getenv("OPENAI_API_KEY")
        and os.getenv("OPENAI_BASE_URL")
        and os.getenv("OPENAI_API_VERSION")
    )


def _use_groq() -> bool:
    if _forced_provider() and _forced_provider() != "groq":
        return False
    return bool(os.getenv("GROQ_API_KEY"))


def _use_ollama() -> bool:
    if _forced_provider() == "ollama":
        return True
    if _forced_provider() and _forced_provider() != "ollama":
        return False
    return bool(os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_MODEL"))


def _use_openai() -> bool:
    if _forced_provider() and _forced_provider() != "openai":
        return False
    return bool(os.getenv("OPENAI_API_KEY"))


_NO_LLM_REASON = (
    "Sin LLM configurado. Define OPENAI_API_KEY (Azure/OpenAI), "
    "GROQ_API_KEY (Groq) u OLLAMA_BASE_URL (Ollama) en .env"
)


def _llm_available() -> bool:
    return _use_azure() or _use_groq() or _use_ollama() or _use_openai()


def _provider_name() -> str:
    if _use_azure():
        return "Azure OpenAI"
    if _use_groq():
        return "Groq"
    if _use_ollama():
        return "Ollama"
    return "OpenAI"


def _model() -> str:
    if _use_azure():
        return os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
    if _use_groq():
        return os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    if _use_ollama():
        return os.getenv("OLLAMA_MODEL", "llama3.1")
    return os.getenv("OPENAI_MODEL", DEFAULT_MODEL)


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
    if _use_ollama():
        from openai import OpenAI
        return OpenAI(
            api_key="ollama",
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        )
    from openai import OpenAI
    return OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL") or None,
    )


def _response_format(schema: dict) -> dict:
    """Devuelve response_format apropiado según el proveedor activo.

    Ollama y modelos locales solo soportan json_object; cloud providers soportan json_schema estricto.
    """
    if _use_ollama():
        return {"type": "json_object"}
    return schema


# ---------------------------------------------------------------------------
# Retry con backoff exponencial ante rate limit
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
# Few-shots para guiar respuestas de hallazgos
# ---------------------------------------------------------------------------

_FEWSHOT_MARCA_SIN_EQUIVALENTE = """\
### EJEMPLO 1 — Marca sin equivalente → revisión prioritaria

Señal detectada:
{
  "patron": "marca",
  "pattern_id": "cn-brand-model-provider-reference",
  "fragmento": "Las luminarias deberán ser marca PHILIPS modelo CorePro LEDBulb",
  "mitigating_factors": [],
  "escalation_factors": ["No se observa mitigante de equivalencia cerca del fragmento."]
}

Output esperado:
{
  "plain_language_explanation": "La especificación nombra una marca comercial específica sin indicar que se aceptan productos equivalentes. En ausencia de una cláusula de equivalencia funcional, la mayoría de oferentes que no distribuyan esa marca quedarían excluidos de facto.",
  "why_it_matters": "La combinación de referencia de marca cerrada sin mitigante justifica revisión prioritaria de proporcionalidad.",
  "possible_legitimate_justification": "La exigencia podría estar justificada si existe infraestructura instalada que requiera compatibilidad, o si hay razones de estandarización documentadas.",
  "suggested_review_action": "Verificar si el documento incluye cláusula de equivalencia funcional. Si no existe, solicitar justificación técnica.",
  "questions_for_reviewer": [
    "¿El pliego incluye en algún punto una cláusula de aceptación de equivalentes funcionales?",
    "¿Existe justificación técnica de la exigencia de esta marca específica?"
  ]
}"""

_FEWSHOT_MARCA_CON_EQUIVALENTE = """\
### EJEMPLO 2 — Marca con equivalente funcional → atención baja

Señal detectada:
{
  "patron": "marca",
  "pattern_id": "cn-brand-model-provider-reference",
  "fragmento": "Las luminarias deberán ser marca PHILIPS o equivalente funcional que cumpla las mismas especificaciones",
  "mitigating_factors": ["o equivalente funcional"],
  "escalation_factors": []
}

Output esperado:
{
  "plain_language_explanation": "La especificación nombra una marca pero incluye una cláusula de equivalencia funcional. El documento establece que se aceptarán productos que cumplan las mismas especificaciones técnicas, lo que mantiene la apertura competitiva.",
  "why_it_matters": "La presencia de la cláusula de equivalencia mitiga el riesgo competitivo. La atención sugerida es baja.",
  "possible_legitimate_justification": "La referencia a marca parece usarse como referencia técnica orientativa, no como requisito cerrado. Esto es práctica aceptada cuando se acompaña de criterios de equivalencia verificables.",
  "suggested_review_action": "Verificar que los criterios de equivalencia mencionados sean objetivamente verificables durante la evaluación de ofertas.",
  "questions_for_reviewer": [
    "¿Los criterios de equivalencia están suficientemente definidos para ser verificables en evaluación?"
  ]
}"""


# ---------------------------------------------------------------------------
# Schemas JSON para respuestas estructuradas
# ---------------------------------------------------------------------------

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


PLIEGO_METADATA_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "pliego_metadata_assisted",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "entidad_contratante": {"$ref": "#/$defs/metadata_field"},
                "objeto_contratacion": {"$ref": "#/$defs/metadata_field"},
                "tipo_procedimiento": {"$ref": "#/$defs/metadata_field"},
                "presupuesto_referencial": {"$ref": "#/$defs/metadata_field"},
                "fecha": {"$ref": "#/$defs/metadata_field"},
                "resumen_pliego": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 4,
                },
            },
            "required": [
                "entidad_contratante",
                "objeto_contratacion",
                "tipo_procedimiento",
                "presupuesto_referencial",
                "fecha",
                "resumen_pliego",
            ],
            "$defs": {
                "metadata_field": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "value": {"type": "string"},
                        "confidence": {"type": "string", "enum": ["alta", "media", "baja"]},
                        "source": {"type": "string"},
                        "evidence": {"type": "string"},
                    },
                    "required": ["value", "confidence", "source", "evidence"],
                }
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Funciones públicas
# ---------------------------------------------------------------------------

def extract_pliego_metadata_assisted(
    document_text: str,
    heuristic_candidates: dict,
    first_pages: str,
) -> dict:
    """Validate and complete pliego metadata using optional assisted processing."""
    if not _llm_available():
        return _unavailable_pliego_metadata(_NO_LLM_REASON)

    try:
        client = _client()
        model = _model()
        fmt = _response_format(PLIEGO_METADATA_SCHEMA)
        prompt = _build_pliego_metadata_prompt(document_text, heuristic_candidates, first_pages)

        def _call():
            return client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Eres un asistente técnico para extracción preliminar de metadata de pliegos "
                            "de contratación pública de Ecuador. Debes validar campos con evidencia textual, "
                            "corregir truncamientos obvios y no inventar datos. Si un campo no está sustentado, "
                            "usa 'No identificado'. Responde solo JSON estricto."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format=fmt,
            )
        response = _call_with_retry(_call)
        content = response.choices[0].message.content or "{}"
        return _normalize_pliego_metadata(json.loads(content))
    except Exception as exc:
        LOGGER.warning("Pliego metadata assisted extraction failed: %s", exc)
        return _unavailable_pliego_metadata(_friendly_llm_error(exc))


def generate_document_brief(
    document_text: str,
    prioritized_findings: list[dict],
    corpus_context: dict | None = None,
    normative_context: dict | None = None,
) -> dict:
    """Generate a cautious executive brief from document text and prior rule findings."""
    if not _llm_available():
        return _unavailable_document_brief(_NO_LLM_REASON)

    try:
        client = _client()
        model = _model()
        fmt = _response_format(DOCUMENT_BRIEF_SCHEMA)
        prompt = _build_document_brief_prompt(
            document_text=document_text,
            findings=prioritized_findings,
            corpus_context=corpus_context,
            normative_context=normative_context,
        )

        def _call():
            return client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                response_format=fmt,
            )
        response = _call_with_retry(_call)
        content = response.choices[0].message.content or "{}"
        return _normalize_document_brief(json.loads(content))
    except Exception as exc:
        LOGGER.warning("Document brief LLM failed: %s", exc)
        return _unavailable_document_brief(_friendly_llm_error(exc))


def explain_priority_with_llm(
    priority: dict,
    corpus_context: dict | None = None,
) -> dict:
    """Explain one prioritized signal in plain language."""
    if not _llm_available():
        return _unavailable_finding_explanation(_NO_LLM_REASON)

    try:
        client = _client()
        model = _model()
        fmt = _response_format(FINDING_EXPLANATION_SCHEMA)
        prompt = _build_finding_prompt(finding=priority, corpus_context=corpus_context)

        def _call():
            return client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                response_format=fmt,
            )
        response = _call_with_retry(_call)
        content = response.choices[0].message.content or "{}"
        return _normalize_finding_explanation(json.loads(content))
    except Exception as exc:
        LOGGER.warning("Finding explanation LLM failed: %s", exc)
        return _unavailable_finding_explanation(_friendly_llm_error(exc))


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
    """Check LLM availability and perform a minimal model call."""
    if not _llm_available():
        return False, _NO_LLM_REASON

    try:
        client = _client()
        model = _model()

        def _call():
            return client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Responde de forma breve y técnica."},
                    {"role": "user", "content": "Responde exactamente: OK"},
                ],
            )
        response = _call_with_retry(_call)
        content = (response.choices[0].message.content or "").strip()
        if content:
            return True, f"Conexión LLM OK ({_provider_name()} · {_model()})"
        return False, "La conexión respondió, pero no devolvió contenido."
    except Exception as exc:
        return False, _friendly_llm_error(exc)


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------

def _friendly_llm_error(exc: Exception) -> str:
    message = str(exc)
    lower_message = message.lower()
    if "insufficient_quota" in lower_message or "quota" in lower_message:
        return "No hay cuota o crédito disponible para usar el modelo configurado."
    if "authentication" in lower_message or "api key" in lower_message or "401" in lower_message:
        return f"La API key no pudo autenticarse. Verifique la clave de {_provider_name()}."
    if "connection" in lower_message or "timeout" in lower_message:
        return f"No se pudo conectar con {_provider_name()}. Revise red o URL de endpoint."
    if "model" in lower_message and ("not found" in lower_message or "does not exist" in lower_message):
        return f"El modelo '{_model()}' no está disponible en {_provider_name()}."
    return f"No se pudo verificar la conexión LLM: {message[:240]}"


def _build_pliego_metadata_prompt(document_text: str, heuristic_candidates: dict, first_pages: str) -> str:
    return (
        "Extrae y valida metadata administrativa del pliego. Prioriza valores completos y verificables.\n\n"
        "Reglas:\n"
        "- Entidad contratante debe ser nombre institucional, no una cláusula.\n"
        "- No aceptes entidad si contiene verbos como será, deberá, podrá o corresponde.\n"
        "- Objeto de contratación debe conservarse completo, sin truncarlo.\n"
        "- Normaliza tipo de procedimiento, por ejemplo: Subasta Inversa Electrónica.\n"
        "- Presupuesto solo si hay valor monetario claro; si no existe, usa No identificado.\n"
        "- Resumen del pliego: máximo 4 bullets de síntesis interpretativa y contextual.\n"
        "- El resumen NO debe repetir entidad, objeto, procedimiento, presupuesto, modalidad ni fecha.\n"
        "- El resumen debe enfocarse en dimensiones predominantes observadas, naturaleza general de señales, mitigantes, complejidad documental y tipo de revisión sugerida.\n"
        "- No emitas conclusiones legales.\n\n"
        f"Candidatos heurísticos actuales:\n{json.dumps(heuristic_candidates, ensure_ascii=False, indent=2)}\n\n"
        f"Primeras páginas / encabezado:\n{first_pages[:8000]}\n\n"
        f"Texto adicional del documento:\n{document_text[:MAX_DOCUMENT_CHARS]}\n"
    )


def _normalize_pliego_metadata(payload: dict[str, Any]) -> dict:
    return {
        "entidad_contratante": _normalize_metadata_field(payload.get("entidad_contratante")),
        "objeto_contratacion": _normalize_metadata_field(payload.get("objeto_contratacion")),
        "tipo_procedimiento": _normalize_metadata_field(payload.get("tipo_procedimiento")),
        "presupuesto_referencial": _normalize_metadata_field(payload.get("presupuesto_referencial")),
        "fecha": _normalize_metadata_field(payload.get("fecha")),
        "resumen_pliego": _normalize_list(payload.get("resumen_pliego"))[:4],
        "llm_available": True,
    }


def _normalize_metadata_field(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {"value": "No identificado", "confidence": "baja", "source": UNAVAILABLE, "evidence": UNAVAILABLE}
    confidence = str(value.get("confidence") or "baja").lower()
    if confidence not in {"alta", "media", "baja"}:
        confidence = "baja"
    return {
        "value": str(value.get("value") or "No identificado").strip() or "No identificado",
        "confidence": confidence,
        "source": str(value.get("source") or UNAVAILABLE),
        "evidence": str(value.get("evidence") or UNAVAILABLE),
    }


def _unavailable_pliego_metadata(reason: str = UNAVAILABLE) -> dict:
    field = {"value": "No identificado", "confidence": "baja", "source": UNAVAILABLE, "evidence": UNAVAILABLE}
    return {
        "entidad_contratante": dict(field),
        "objeto_contratacion": dict(field),
        "tipo_procedimiento": dict(field),
        "presupuesto_referencial": dict(field),
        "fecha": dict(field),
        "resumen_pliego": [UNAVAILABLE],
        "llm_available": False,
        "llm_error": reason,
    }


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
        "- No atribuyas intencionalidad ni infieras proveedores beneficiados.\n"
        "- Usa la taxonomía únicamente como marco de explicación y no como conclusión automática.\n"
        "- Usa la capa normativa solo como referencia orientativa para revisión humana.\n"
        "- Distingue requisitos regulatorios o habituales de señales atípicas o acumuladas.\n"
        "- Reconoce mitigantes como equivalentes funcionales, consorcios, apertura a oferentes "
        "extranjeros, criterios funcionales o pluralidad de marcas.\n"
        "- Si un criterio parece razonable o estándar, dilo expresamente con lenguaje prudente.\n"
        "- Usa lenguaje prudente: señales de restricción competitiva, requisitos potencialmente "
        "limitantes, baja neutralidad competitiva, condiciones que podrían reducir concurrencia, "
        "validación de proporcionalidad, revisión humana sugerida, posible afectación a concurrencia.\n"
        "- Si no hay evidencia suficiente, indícalo de forma explícita y prudente.\n"
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
        "\nTaxonomía documental de referencia:\n"
        f"{json.dumps(taxonomy_context(), ensure_ascii=False, indent=2)}\n"
    )


def _build_finding_prompt(finding: dict, corpus_context: dict | None) -> str:
    pattern = str(finding.get("patrón detectado", "No disponible"))
    context = (corpus_context or {}).get(pattern, {})

    # Seleccionar few-shot más relevante según el tipo de señal
    mitigants = finding.get("mitigating_factors", [])
    has_mitigant = bool(mitigants) if isinstance(mitigants, list) else bool(mitigants)
    fewshot = _FEWSHOT_MARCA_CON_EQUIVALENTE if has_mitigant else _FEWSHOT_MARCA_SIN_EQUIVALENTE

    return (
        "Explica una señal sugerida para revisión humana de forma clara y prudente.\n\n"
        "Condiciones:\n"
        "- La señal ya fue detectada por reglas; no inventes señales adicionales.\n"
        "- No emitas dictámenes legales ni asignes responsabilidad.\n"
        "- No infieras intención ni proveedor beneficiado.\n"
        "- Usa la referencia normativa de la señal solo como apoyo orientativo.\n"
        "- Distingue si se trata de un requisito habitual, un mitigante o una señal que requiere revisión.\n"
        "- Reconoce factores que favorecen concurrencia y explica si reducen la atención sugerida.\n"
        "- No atribuyas intencionalidad.\n"
        "- Usa lenguaje técnico, breve y orientado a decisión.\n"
        "- Devuelve únicamente JSON estricto con las claves solicitadas.\n\n"
        f"{fewshot}\n\n"
        "---\n"
        f"Señal sugerida:\n{json.dumps(_compact_finding(finding), ensure_ascii=False, indent=2)}\n\n"
        f"Contexto histórico del patrón:\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
        f"Taxonomía documental de referencia:\n{json.dumps(taxonomy_context(limit=6), ensure_ascii=False, indent=2)}\n"
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
        "pattern_id": finding.get("pattern_id", "No disponible"),
        "pattern_name": finding.get("pattern_name", finding.get("patrón detectado", "No disponible")),
        "dimension_competitiva": finding.get("competition_dimension", finding.get("dimensión competitiva", "No disponible")),
        "seccion_documental_probable": finding.get("document_section", finding.get("sección documental probable", "No disponible")),
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
        "prioridad_revision": finding.get("prioridad de revisión", finding.get("review_priority", "No disponible")),
        "criterios_de_priorizacion": finding.get(
            "criterios_de_priorizacion",
            finding.get("validación sugerida", "No disponible"),
        ),
        "factores_mitigantes": finding.get("mitigating_factors", []),
        "justificaciones_posibles": finding.get("possible_legitimate_justifications", []),
        "informacion_faltante": finding.get("missing_information", []),
        "lenguaje_recomendado": finding.get("suggested_neutral_wording", finding.get("lenguaje recomendado", "No disponible")),
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
        "plain_language_explanation": "La explicación asistida por IA no está disponible en este momento.",
        "why_it_matters": "Se mantiene la revisión basada en reglas, taxonomía documental y contexto comparativo.",
        "possible_legitimate_justification": "Revise la posible justificación legítima indicada por el análisis estructurado de la señal.",
        "suggested_review_action": "Use la evidencia textual, mitigantes y preguntas de revisión ya mostradas para continuar la revisión humana.",
        "questions_for_reviewer": [
            "¿La señal cuenta con justificación técnica proporcional en el documento?",
            "¿Existen mitigantes o equivalencias aplicables en la práctica?",
        ],
        "llm_available": False,
        "llm_error": reason,
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
