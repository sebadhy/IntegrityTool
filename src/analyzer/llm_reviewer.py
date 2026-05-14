from __future__ import annotations

import json
import logging
import os
from typing import Any

from dotenv import load_dotenv
from openai import AzureOpenAI, OpenAI

from .taxonomy_loader import load_taxonomy, taxonomy_context


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

DEFAULT_MODEL = "gpt-4o-mini"
UNAVAILABLE = "No disponible"
MAX_DOCUMENT_CHARS = 12_000

FEWSHOT_MARCA_SIN_EQUIVALENTE = """\
### EJEMPLO 1 — Marca sin equivalente → revisión prioritaria

Señal detectada:
{
  "patron": "marca",
  "pattern_id": "cn-brand-model-provider-reference",
  "fragmento": "... Las luminarias deberán ser marca PHILIPS modelo CorePro LEDBulb ...",
  "pagina": 12,
  "mitigating_factors": [],
  "escalation_factors": ["No se observa mitigante de equivalencia cerca del fragmento."]
}
Contexto histórico: { "frecuencia": 0.12, "rarity": "Poco frecuente" }

Output esperado:
{
  "plain_language_explanation": "La especificación nombra una marca comercial específica sin indicar que se aceptan productos equivalentes. En ausencia de una cláusula de equivalencia funcional, la mayoría de oferentes que no distribuyan esa marca quedarían excluidos de facto.",
  "why_it_matters": "Este requisito aparece en el 12% del corpus histórico de procesos comparables, lo que lo hace poco frecuente. La combinación de referencia de marca cerrada con baja frecuencia histórica justifica revisión prioritaria de proporcionalidad.",
  "possible_legitimate_justification": "La exigencia podría estar justificada si existe infraestructura instalada de esa marca que requiera compatibilidad, o si hay razones de estandarización documentadas. Convendría verificar si el expediente incluye esa justificación.",
  "suggested_review_action": "Revisar si el documento incluye una cláusula de equivalencia funcional en otro punto del pliego. Si no existe, solicitar justificación técnica de la restricción.",
  "questions_for_reviewer": [
    "¿El pliego incluye en algún punto una cláusula de aceptación de equivalentes funcionales?",
    "¿Existe en el expediente una justificación técnica de la exigencia de esta marca específica?",
    "¿La entidad tiene infraestructura instalada de esta marca que requiera compatibilidad?"
  ]
}"""

FEWSHOT_MARCA_CON_EQUIVALENTE = """\
### EJEMPLO 2 — Marca con equivalente funcional → atención baja

Señal detectada:
{
  "patron": "marca",
  "pattern_id": "cn-brand-model-provider-reference",
  "fragmento": "... Las luminarias deberán ser marca PHILIPS o equivalente funcional que cumpla las mismas especificaciones de potencia y eficiencia luminosa ...",
  "pagina": 12,
  "mitigating_factors": ["o equivalente funcional"],
  "escalation_factors": []
}
Contexto histórico: { "frecuencia": 0.65, "rarity": "Habitual" }

Output esperado:
{
  "plain_language_explanation": "La especificación nombra una marca pero incluye una cláusula de equivalencia funcional. El documento establece que se aceptarán productos que cumplan las mismas especificaciones técnicas, lo que mantiene la apertura competitiva.",
  "why_it_matters": "Este tipo de referencia es habitual en el corpus histórico y la presencia de la cláusula de equivalencia mitiga el riesgo competitivo. La atención sugerida es baja.",
  "possible_legitimate_justification": "La referencia a marca parece usarse como referencia técnica orientativa, no como requisito cerrado. Esto es una práctica aceptada cuando se acompaña de criterios de equivalencia verificables.",
  "suggested_review_action": "Verificar que los criterios de equivalencia mencionados sean objetivamente verificables durante la evaluación de ofertas.",
  "questions_for_reviewer": [
    "¿Los criterios de equivalencia están suficientemente definidos para ser verificables en evaluación?",
    "¿Los criterios de aceptación de equivalentes son aplicables a oferentes nacionales e internacionales?"
  ]
}"""

FEWSHOT_REQUISITO_HABITUAL = """\
### EJEMPLO 3 — Requisito regulatorio habitual → no priorizar por sí solo

Señal detectada:
{
  "patron": "RUP",
  "pattern_id": "legacy-rup",
  "fragmento": "... El oferente deberá estar inscrito en el Registro Único de Proveedores (RUP) y habilitado al momento de la presentación de la oferta ...",
  "pagina": 3,
  "tipo_senal": "requisito_habitual",
  "mitigating_factors": [],
  "escalation_factors": []
}
Contexto histórico: { "frecuencia": 0.97, "rarity": "Habitual" }

Output esperado:
{
  "plain_language_explanation": "La inscripción en el RUP es un requisito legal habitual para participar en contratación pública ecuatoriana. Su presencia en el pliego no constituye una señal de restricción competitiva.",
  "why_it_matters": "Este requisito aparece en el 97% de los procesos del corpus histórico y está establecido por ley. No requiere priorización como señal de restricción. Solo convendría revisarlo si se combina con condiciones adicionales que lo hagan discriminatorio.",
  "possible_legitimate_justification": "Es un requisito de habilitación legal estándar.",
  "suggested_review_action": "No se sugiere revisión adicional de este requisito de forma aislada.",
  "questions_for_reviewer": [
    "¿El requisito de RUP aparece combinado con condiciones adicionales de habilitación que puedan ser discriminatorias?"
  ]
}"""

FEWSHOT_PRESENCIA_LOCAL = """\
### EJEMPLO 4 — Presencia local con posible justificación operativa → contextual

Señal detectada:
{
  "patron": "presencia local",
  "pattern_id": "cn-local-presence-requirement",
  "fragmento": "... El proveedor deberá contar con un centro de servicio técnico en la ciudad de Quito o en un radio máximo de 30 km, con capacidad de atención en un plazo máximo de 4 horas para equipos críticos ...",
  "pagina": 18,
  "mitigating_factors": [],
  "escalation_factors": ["No se observa justificación técnica cercana en el fragmento."]
}
Contexto histórico: { "frecuencia": 0.08, "rarity": "Poco frecuente" }

Output esperado:
{
  "plain_language_explanation": "El documento exige que el proveedor tenga un centro de servicio en un radio de 30 km. El requisito incluye un tiempo de respuesta de 4 horas para equipos críticos, lo que sugiere una justificación operativa.",
  "why_it_matters": "Este tipo de requisito es poco frecuente en el corpus histórico (8% de procesos). El contexto operativo puede justificarlo, pero la clave es si la distancia de 30 km es proporcional o si podría cumplirse con acuerdos de servicio sin presencia física permanente.",
  "possible_legitimate_justification": "Si los equipos son críticos para la operación institucional y requieren atención de emergencia, el requisito podría ser proporcionado. La justificación debe estar documentada en el expediente técnico.",
  "suggested_review_action": "Revisar si el expediente técnico justifica por qué la distancia de 30 km es necesaria y si se permite cumplir el requisito mediante acuerdos de servicio.",
  "questions_for_reviewer": [
    "¿El expediente técnico documenta por qué se requiere presencia dentro de 30 km específicamente?",
    "¿Se permite cumplir con el tiempo de respuesta mediante acuerdos con servicios técnicos locales, sin requerir oficina propia?",
    "¿Este mismo tiempo de respuesta es exigido en procesos similares del corpus histórico?"
  ]
}"""

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
    contract_object: str = "No identificado en las primeras páginas",
) -> dict:
    """Generate a cautious executive brief from document text and prior rule findings."""
    if not os.getenv("OPENAI_API_KEY"):
        return _unavailable_document_brief("OPENAI_API_KEY no está configurada.")

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
                        contract_object=contract_object,
                    ),
                },
            ],
            response_format=DOCUMENT_BRIEF_SCHEMA,
        )
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
    if not os.getenv("OPENAI_API_KEY"):
        return _unavailable_finding_explanation("OPENAI_API_KEY no está configurada.")

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
        if content.upper() == "OK":
            return True, "Conexión LLM OK"
        if content:
            return False, f"El modelo respondió pero no siguió la instrucción. Respuesta: '{content[:60]}'"
        return False, "La conexión respondió, pero no devolvió contenido."
    except Exception as exc:
        return False, _friendly_llm_error(exc)


def _client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL") or None
    api_version = os.getenv("OPENAI_API_VERSION") or None

    if api_version and base_url:
        return AzureOpenAI(
            api_key=api_key,
            azure_endpoint=base_url,
            api_version=api_version,
        )
    return OpenAI(api_key=api_key, base_url=base_url)


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
    contract_object: str = "No identificado en las primeras páginas",
) -> str:
    representative_text = _representative_document_excerpt(document_text, findings)
    findings_summary = _findings_summary(findings)
    comparative_summary = _comparative_summary(findings, corpus_context)

    return (
        "Genera una lectura preliminar asistida para revisión humana de un documento de "
        "contratación pública, con foco en neutralidad competitiva.\n\n"
        "Restricciones:\n"
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
        f"Objeto de contratación: {contract_object}\n\n"
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
    few_shots = _select_few_shots(finding)
    taxonomy = _relevant_taxonomy_context(finding)

    prompt = (
        "Explica una señal sugerida para revisión humana.\n\n"
        "El lector es un técnico institucional sin formación legal. "
        "Escribe de forma concisa y orientada a decisión.\n\n"
        "Restricciones:\n"
        "- La señal ya fue detectada por reglas; no inventes señales adicionales.\n"
        "- No emitas dictámenes legales ni asignes responsabilidad.\n"
        "- No infieras intención ni proveedor beneficiado.\n"
        "- Distingue si se trata de un requisito habitual, un mitigante o una señal que requiere revisión.\n"
        "- Reconoce factores que favorecen concurrencia y explica si reducen la atención sugerida.\n"
        "- Devuelve únicamente JSON estricto con las claves solicitadas.\n\n"
    )
    if few_shots:
        prompt += f"--- EJEMPLOS ---\n{few_shots}\n--- FIN EJEMPLOS ---\n\n"
    prompt += (
        f"--- CASO ACTUAL ---\n"
        f"Señal sugerida:\n{json.dumps(_compact_finding(finding), ensure_ascii=False, indent=2)}\n\n"
        f"Contexto histórico del patrón:\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
        f"Taxonomía del patrón relevante:\n{json.dumps(taxonomy, ensure_ascii=False, indent=2)}\n"
    )
    return prompt


def _select_few_shots(finding: dict) -> str:
    signal_type = str(finding.get("tipo_señal", "señal_revision"))
    pattern_id = str(finding.get("pattern_id", ""))
    has_mitigants = bool(finding.get("mitigating_factors"))

    if signal_type == "requisito_habitual":
        return FEWSHOT_REQUISITO_HABITUAL
    if signal_type == "mitigante_concurrencia":
        return ""
    if "brand" in pattern_id or "marca" in str(finding.get("patrón detectado", "")).lower():
        return FEWSHOT_MARCA_CON_EQUIVALENTE if has_mitigants else FEWSHOT_MARCA_SIN_EQUIVALENTE
    if "local" in pattern_id or "presencia" in str(finding.get("patrón detectado", "")).lower():
        return FEWSHOT_PRESENCIA_LOCAL
    return FEWSHOT_MARCA_SIN_EQUIVALENTE


def _relevant_taxonomy_context(finding: dict) -> dict:
    pattern_id = str(finding.get("pattern_id", ""))
    result = load_taxonomy()
    for pattern in result.patterns:
        if pattern.id == pattern_id:
            related_ids = set(pattern.related_patterns)
            related = [p for p in result.patterns if p.id in related_ids]
            return {
                "pattern": {
                    "id": pattern.id,
                    "name": pattern.name,
                    "description": pattern.description,
                    "competition_dimension": pattern.competition_dimension,
                    "human_review_questions": pattern.human_review_questions,
                    "possible_legitimate_justifications": pattern.possible_legitimate_justifications,
                },
                "related_patterns": [{"id": p.id, "name": p.name} for p in related],
            }
    return {}


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
        "seccion_id": finding.get("section_id", "desconocido"),
        "seccion_label": finding.get("section_label", "No determinada"),
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
