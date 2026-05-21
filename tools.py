"""
tools.py — Herramientas que el agente puede invocar.

Cada función wrappea un módulo existente del proyecto.
El agente decide cuándo y con qué argumentos llamar cada una.

Las definiciones en TOOL_DEFINITIONS se pasan directamente a la API de Groq.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Definiciones de herramientas para la API (formato OpenAI/Groq tool use)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "extract_pdf_pages",
            "description": (
                "Extrae el texto de páginas específicas de un PDF. "
                "Úsala para leer secciones concretas del pliego en lugar de procesar "
                "todo el documento de una vez. Empieza por las primeras páginas para "
                "entender la estructura, luego profundiza en secciones relevantes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pdf_path": {
                        "type": "string",
                        "description": "Ruta absoluta al archivo PDF.",
                    },
                    "pages": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": (
                            "Lista de números de página (base 1) a extraer. "
                            "Máximo 10 páginas por llamada. "
                            "Si es null extrae todas las páginas."
                        ),
                    },
                },
                "required": ["pdf_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_patterns",
            "description": (
                "Aplica el motor de detección de patrones sobre un fragmento de texto. "
                "Retorna hallazgos con tipo de señal, evidencia textual, mitigantes y "
                "preguntas sugeridas. Úsala después de leer una sección del documento."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Texto a analizar.",
                    },
                    "page_number": {
                        "type": "integer",
                        "description": "Número de página de origen del texto.",
                    },
                },
                "required": ["text", "page_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_corpus",
            "description": (
                "Busca en el corpus histórico cuán frecuente es un patrón o cláusula "
                "en procesos similares. Úsala para contextualizar si un requisito es "
                "habitual o atípico antes de marcarlo como señal prioritaria."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern_id": {
                        "type": "string",
                        "description": "ID del patrón a buscar (ej: 'distribuidor_autorizado').",
                    },
                    "category": {
                        "type": "string",
                        "description": "Categoría del proceso para filtrar comparaciones.",
                    },
                },
                "required": ["pattern_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_document_structure",
            "description": (
                "Retorna un mapa rápido de la estructura del PDF: número de páginas, "
                "primeras líneas de cada página y secciones detectadas. "
                "Úsala al inicio para planificar qué páginas revisar en detalle."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pdf_path": {
                        "type": "string",
                        "description": "Ruta absoluta al archivo PDF.",
                    },
                },
                "required": ["pdf_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "flag_finding",
            "description": (
                "Registra un hallazgo final con trazabilidad completa. "
                "Úsala cuando hayas analizado una sección y confirmado que hay "
                "un aspecto que merece revisión humana. No la uses para hallazgos "
                "sin evidencia textual suficiente."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern_id": {"type": "string"},
                    "pattern_name": {"type": "string"},
                    "category": {"type": "string"},
                    "signal_type": {
                        "type": "string",
                        "enum": [
                            "señal_revision",
                            "mitigante_concurrencia",
                            "requisito_habitual",
                        ],
                    },
                    "review_priority": {
                        "type": "string",
                        "enum": ["priority", "suggested", "general"],
                    },
                    "evidence_text": {
                        "type": "string",
                        "description": "Fragmento textual exacto del documento.",
                    },
                    "page_number": {"type": "integer"},
                    "rationale": {
                        "type": "string",
                        "description": "Por qué este aspecto merece revisión.",
                    },
                    "mitigating_factors": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "suggested_questions": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    "pattern_id", "pattern_name", "category",
                    "signal_type", "review_priority",
                    "evidence_text", "page_number", "rationale",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_normative_context",
            "description": (
                "Retorna los principios normativos de la LOSNCP relevantes para "
                "una categoría de análisis. Úsala para enriquecer el rationale "
                "de un hallazgo con referencia normativa orientativa."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Categoría del hallazgo.",
                    },
                },
                "required": ["category"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Implementaciones
# ---------------------------------------------------------------------------

def extract_pdf_pages(pdf_path: str, pages: list[int] | None = None) -> dict:
    """Extrae texto de páginas específicas de un PDF, con OCR si es necesario."""
    try:
        from src.analyzer.pdf_extractor import extract_pdf, PageStatus

        path = Path(pdf_path)
        if not path.exists():
            return {"error": f"PDF no encontrado: {pdf_path}"}

        pdf_bytes = path.read_bytes()
        result = extract_pdf(pdf_bytes)

        if not result.has_any_text:
            return {
                "error": "no_text",
                "message": (
                    "El PDF no tiene texto extraíble. "
                    "Puede ser un documento completamente escaneado."
                ),
                "ocr_summary": result.summary(),
            }

        # Filtrar páginas solicitadas
        all_pages = result.pages
        selected = [p for p in all_pages if p.page_number in pages] if pages else all_pages

        # Separar páginas con texto de las que requieren OCR
        pages_ok = [p for p in selected if p.status in {PageStatus.OK, PageStatus.OCR_OK}]
        pages_pending_ocr = [p for p in selected if p.status == PageStatus.REQUIRES_OCR]
        pages_empty = [p for p in selected if p.status == PageStatus.EMPTY]

        output = {
            "total_pages":    result.total_pages,
            "extracted_pages": len(pages_ok),
            "ocr_summary":    result.summary(),
            "pages": [
                {
                    "page":         p.page_number,
                    "text":         p.text[:3000],
                    "truncated":    len(p.text) > 3000,
                    "status":       p.status.value,
                    "via_ocr":      p.status == PageStatus.OCR_OK,
                }
                for p in pages_ok
            ],
        }

        # Avisar al agente sobre páginas escaneadas pendientes
        if pages_pending_ocr:
            output["ocr_pending_pages"] = [p.page_number for p in pages_pending_ocr]
            output["ocr_warning"] = (
                f"{len(pages_pending_ocr)} página(s) escaneadas no pudieron procesarse "
                f"porque Tesseract no está instalado. "
                f"Páginas afectadas: {[p.page_number for p in pages_pending_ocr]}. "
                f"El análisis continúa con las páginas disponibles."
            )

        return output

    except Exception as exc:
        LOGGER.error("extract_pdf_pages error: %s", exc)
        return {"error": str(exc)}


def detect_patterns(text: str, page_number: int) -> dict:
    """Aplica el motor de detección clause-centric sobre un fragmento.

    Uses the same detect_signals pipeline as the Streamlit UI, ensuring
    consistent results between agent and interactive analysis.
    """
    try:
        from src.analyzer.pdf_extractor import PageText
        from src.analyzer.document_segmenter import segment_document
        from src.analyzer.clause_extractor import extract_clauses
        from src.analyzer.boilerplate_filter import active_clauses, classify_clauses
        from src.analyzer.detector import detect_signals

        pages = [PageText(page_number=page_number, text=text)]
        sections = segment_document(pages)
        document_id = f"agent-page-{page_number}"
        clauses = classify_clauses(extract_clauses(pages, sections, document_id))
        signals = detect_signals(active_clauses(clauses))

        return {
            "total_findings": len(signals),
            "findings": [
                {
                    "signal_id": signal.signal_id,
                    "pattern_id": signal.pattern_id,
                    "pattern_name": signal.metadata.get("pattern_name", ""),
                    "matched_text": signal.matched_text,
                    "evidence_text": signal.evidence_text,
                    "page": signal.page,
                    "section": signal.section_title,
                    "competition_dimension": signal.competition_dimension,
                    "confidence": signal.confidence,
                    "family": signal.family,
                }
                for signal in signals
            ],
        }
    except Exception as exc:
        LOGGER.error("detect_patterns error: %s", exc)
        return {"error": str(exc)}


def search_corpus(pattern_id: str, category: str | None = None) -> dict:
    """Busca frecuencia histórica de un patrón en el corpus."""
    try:
        from src.analyzer.corpus_loader import load_corpus_documents as load_corpus
        from src.analyzer.detector import normalize_text

        corpus = load_corpus()
        if not corpus:
            return {
                "pattern_id": pattern_id,
                "status": "corpus_empty",
                "message": "No hay documentos en el corpus histórico todavía.",
            }

        # Filtrar por categoría si se especifica
        if category:
            filtered = [
                doc for doc in corpus
                if normalize_text(doc.get("categoria", "")) == normalize_text(category)
            ]
        else:
            filtered = corpus

        # Contar apariciones del patrón
        total = len(filtered)
        with_pattern = sum(
            1 for doc in filtered
            if pattern_id in doc.get("detected_patterns", [])
        )

        frequency = (with_pattern / total * 100) if total > 0 else 0

        classification = (
            "muy_frecuente" if frequency >= 60
            else "frecuente"   if frequency >= 30
            else "ocasional"   if frequency >= 10
            else "poco_frecuente"
        )

        return {
            "pattern_id": pattern_id,
            "category_filter": category,
            "total_comparable_processes": total,
            "processes_with_pattern": with_pattern,
            "frequency_pct": round(frequency, 1),
            "classification": classification,
            "interpretation": _frequency_interpretation(classification),
        }
    except Exception as exc:
        LOGGER.error("search_corpus error: %s", exc)
        return {"error": str(exc)}


def get_document_structure(pdf_path: str) -> dict:
    """Retorna un mapa rápido de la estructura del documento."""
    try:
        from src.analyzer.pdf_extractor import extract_pdf, PageStatus

        path = Path(pdf_path)
        if not path.exists():
            return {"error": f"PDF no encontrado: {pdf_path}"}

        pdf_bytes = path.read_bytes()
        result = extract_pdf(pdf_bytes)
        pages = result.pages

        # Detectar secciones por palabras clave en primeras líneas
        section_hints = {
            "especificaciones técnicas": ["especificaciones técnicas", "ficha técnica"],
            "requisitos habilitantes": ["requisito habilitante", "documentos habilitantes"],
            "evaluación": ["evaluación", "calificación", "puntaje"],
            "experiencia": ["experiencia mínima", "capacidad técnica"],
            "garantías": ["garantía", "mantenimiento", "postventa"],
            "cronograma": ["cronograma", "plazo de entrega"],
        }

        detected_sections = []
        for page in pages:
            first_lines = page.text[:300].lower()
            for section, keywords in section_hints.items():
                if any(kw in first_lines for kw in keywords):
                    detected_sections.append({
                        "section": section,
                        "page": page.page_number,
                        "status": page.status.value,
                    })

        return {
            "total_pages":      result.total_pages,
            "has_text":         result.has_any_text,
            "ocr_summary":      result.summary(),
            "detected_sections": detected_sections,
            "page_previews": [
                {
                    "page":             p.page_number,
                    "first_100_chars":  p.text[:100].strip(),
                    "has_text":         p.has_text,
                    "status":           p.status.value,
                }
                for p in pages[:5]
            ],
        }
    except Exception as exc:
        LOGGER.error("get_document_structure error: %s", exc)
        return {"error": str(exc)}


def flag_finding(
    pattern_id: str,
    pattern_name: str,
    category: str,
    signal_type: str,
    review_priority: str,
    evidence_text: str,
    page_number: int,
    rationale: str,
    mitigating_factors: list[str] | None = None,
    suggested_questions: list[str] | None = None,
) -> dict:
    """Registra un hallazgo confirmado por el agente."""
    import hashlib

    finding_id = "agent-" + hashlib.sha1(
        f"{pattern_id}|{page_number}|{evidence_text[:120]}".encode()
    ).hexdigest()[:12]

    return {
        "finding_id": finding_id,
        "pattern_id": pattern_id,
        "pattern_name": pattern_name,
        "category": category,
        "signal_type": signal_type,
        "review_priority": review_priority,
        "evidence_text": evidence_text,
        "page_number": page_number,
        "rationale": rationale,
        "mitigating_factors": mitigating_factors or [],
        "suggested_questions": suggested_questions or [],
        "registered": True,
    }


def get_normative_context(category: str) -> dict:
    """Retorna principios normativos relevantes para una categoría."""
    NORMATIVE_MAP = {
        "Autorizaciones comerciales o de fabricante": {
            "principio": "concurrencia e igualdad",
            "criterio": (
                "Las especificaciones no deben estar orientadas a un proveedor específico. "
                "LOSNCP Art. 6 num. 19 y Art. 22."
            ),
            "pregunta": (
                "¿El requisito de autorización está justificado por la naturaleza "
                "técnica del bien o servicio, o podría eliminarse sin afectar la calidad?"
            ),
        },
        "Referencias a marca, origen o fabricante": {
            "principio": "no discriminación y trato justo",
            "criterio": (
                "Las especificaciones técnicas deben referirse a características "
                "funcionales, no a marcas o fabricantes específicos. LOSNCP Art. 22."
            ),
            "pregunta": (
                "¿La referencia a marca incluye 'o equivalente'? "
                "¿La equivalencia es verificable y efectiva?"
            ),
        },
        "Certificaciones específicas": {
            "principio": "proporcionalidad",
            "criterio": (
                "Las certificaciones exigidas deben ser proporcionales al objeto "
                "contractual y admitir estándares equivalentes reconocidos."
            ),
            "pregunta": (
                "¿La certificación exigida es proporcional al riesgo o complejidad "
                "del contrato? ¿Se aceptan certificaciones equivalentes internacionales?"
            ),
        },
        "Garantías, repuestos y postventa": {
            "principio": "mejor valor por dinero y proporcionalidad",
            "criterio": (
                "Los requisitos de postventa deben ser proporcionales a la vida útil "
                "y criticidad del bien contratado."
            ),
            "pregunta": (
                "¿El plazo de garantía y disponibilidad de repuestos es proporcional "
                "al tipo de bien? ¿Se permiten proveedores de soporte alternativos?"
            ),
        },
        "Requisitos técnicos cerrados": {
            "principio": "claridad y no ambigüedad de especificaciones",
            "criterio": (
                "Las especificaciones técnicas deben permitir la participación del "
                "mayor número posible de oferentes que cumplan el objeto contractual."
            ),
            "pregunta": (
                "¿Las especificaciones técnicas admiten soluciones equivalentes "
                "que satisfagan la misma necesidad funcional?"
            ),
        },
    }

    context = NORMATIVE_MAP.get(category, {
        "principio": "concurrencia, igualdad y proporcionalidad",
        "criterio": "Revisar proporcionalidad y justificación técnica del requisito.",
        "pregunta": "¿El requisito está justificado por la naturaleza del objeto contractual?",
    })

    return {
        "category": category,
        "principio_normativo_relacionado": context["principio"],
        "criterio_normativo_de_revision": context["criterio"],
        "pregunta_normativa_sugerida": context["pregunta"],
        "fuente_referencial": "LOSNCP / RLOSNCP — referencia orientativa, no dictamen legal.",
    }


# ---------------------------------------------------------------------------
# Dispatcher — el agente llama esto con el nombre y args de la herramienta
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, Any] = {
    "extract_pdf_pages":    extract_pdf_pages,
    "detect_patterns":      detect_patterns,
    "search_corpus":        search_corpus,
    "get_document_structure": get_document_structure,
    "flag_finding":         flag_finding,
    "get_normative_context": get_normative_context,
}


def dispatch_tool(tool_name: str, tool_args: dict) -> dict:
    """Ejecuta una herramienta por nombre y retorna el resultado como dict."""
    fn = TOOL_REGISTRY.get(tool_name)
    if fn is None:
        return {"error": f"Herramienta desconocida: {tool_name}"}
    try:
        result = fn(**tool_args)
        return result if isinstance(result, dict) else {"result": result}
    except TypeError as exc:
        return {"error": f"Argumentos inválidos para {tool_name}: {exc}"}


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _frequency_interpretation(classification: str) -> str:
    return {
        "muy_frecuente":   "Este requisito aparece en la mayoría de procesos comparables. Considerar como habitual.",
        "frecuente":       "Este requisito es frecuente en procesos similares. Revisar si el contexto es comparable.",
        "ocasional":       "Este requisito aparece ocasionalmente. Revisar proporcionalidad y justificación.",
        "poco_frecuente":  "Este requisito es poco frecuente en procesos similares. Merece revisión detallada.",
    }.get(classification, "Frecuencia no determinada.")
