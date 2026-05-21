"""
agent.py — Loop del agente con Groq y tool use.

El agente recibe un proceso, decide qué herramientas llamar,
itera hasta completar el análisis y retorna hallazgos + brief.

No hay orden fijo de pasos. El agente razona en cada iteración.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime
from typing import Any

from groq import Groq
from dotenv import load_dotenv

from src.config import GROQ_MODEL
from tools import TOOL_DEFINITIONS, dispatch_tool

load_dotenv()

LOGGER = logging.getLogger(__name__)

MODEL = GROQ_MODEL
MAX_ITERATIONS = int(os.getenv("AGENT_MAX_ITERATIONS", "20"))
TEMPERATURE = 0.1  # bajo para análisis documental consistente

SYSTEM_PROMPT = """Eres un asistente especializado en revisión preliminar de neutralidad competitiva \
en pliegos de contratación pública de Ecuador.

Tu función es analizar documentos de contratación e identificar aspectos que podrían \
requerir revisión humana adicional, con foco en:
- Neutralidad competitiva y proporcionalidad de requisitos
- Referencias a marcas, fabricantes o proveedores específicos
- Certificaciones o autorizaciones que podrían limitar concurrencia
- Consistencia entre secciones del documento

PROCESO DE ANÁLISIS:
1. Empieza llamando get_document_structure para entender la estructura del PDF
2. Usa extract_pdf_pages para leer secciones relevantes (especificaciones técnicas, \
   requisitos habilitantes, evaluación)
3. Para cada sección, llama detect_patterns para identificar patrones documentales
4. Para hallazgos relevantes, llama search_corpus para contextualizar si son habituales
5. Llama get_normative_context para enriquecer hallazgos con referencia normativa
6. Registra hallazgos confirmados con flag_finding
7. Cuando hayas revisado todas las secciones relevantes, termina con un JSON de cierre

PRINCIPIOS:
- No emitas conclusiones jurídicas ni atribuyas intencionalidad
- Distingue señales_revision, mitigantes_concurrencia y requisitos_habituales
- Un requisito habitual o con mitigantes claros no es señal prioritaria
- Preserva evidencia textual exacta, no parafrasees
- Si el documento no tiene texto seleccionable, indícalo

CIERRE:
Cuando termines, devuelve ÚNICAMENTE este JSON (sin markdown, sin texto adicional):
{
  "analysis_complete": true,
  "document_summary": "...",
  "overall_attention_level": "Bajo|Medio|Alto",
  "main_review_topics": ["...", "..."],
  "possible_competition_effects": "...",
  "comparative_context": "...",
  "top_priorities_rationale": ["...", "..."],
  "suggested_human_review_questions": ["...", "..."],
  "methodological_note": "Señales preliminares para revisión humana. No constituyen dictamen legal."
}"""


# ---------------------------------------------------------------------------
# Clase principal del agente
# ---------------------------------------------------------------------------

class PligoAgent:
    """Agente que analiza un proceso de contratación usando tool use con Groq."""

    def __init__(self) -> None:
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.run_id = str(uuid.uuid4())

    def analyze(self, proceso: dict) -> dict:
        """
        Analiza un proceso completo.

        proceso debe incluir:
          - process_id
          - pliego_path (ruta absoluta al PDF del pliego)
          - especificaciones_path (opcional)
          - entidad, objeto, categoria (metadata)

        Retorna:
          - run_id
          - findings: lista de hallazgos registrados por el agente
          - brief: resumen ejecutivo
          - tool_calls: trazabilidad de decisiones
          - status: completed | failed
          - metadata: tokens, duración, iteraciones
        """
        started_at = datetime.utcnow()
        start_time = time.time()

        LOGGER.info("[%s] Iniciando análisis de %s", self.run_id, proceso["process_id"])

        # Estado mutable del agente durante el análisis
        state: dict[str, Any] = {
            "run_id":       self.run_id,
            "process_id":   proceso["process_id"],
            "findings":     [],
            "tool_calls":   [],
            "messages":     [],
            "iterations":   0,
            "total_tokens": 0,
        }

        # Mensaje inicial al agente
        user_message = self._build_initial_message(proceso)
        state["messages"].append({"role": "user", "content": user_message})

        try:
            brief = self._run_loop(state)
            duration = time.time() - start_time

            LOGGER.info(
                "[%s] Análisis completado: %d hallazgos, %d tool calls, %.1fs",
                self.run_id, len(state["findings"]), len(state["tool_calls"]), duration,
            )

            return {
                "run_id":       self.run_id,
                "process_id":   proceso["process_id"],
                "status":       "completed",
                "findings":     state["findings"],
                "brief":        brief,
                "tool_calls":   state["tool_calls"],
                "metadata": {
                    "model":        MODEL,
                    "iterations":   state["iterations"],
                    "total_tokens": state["total_tokens"],
                    "duration_secs": round(duration, 2),
                    "started_at":   started_at.isoformat(),
                    "completed_at": datetime.utcnow().isoformat(),
                },
            }

        except Exception as exc:
            duration = time.time() - start_time
            LOGGER.error("[%s] Análisis fallido: %s", self.run_id, exc, exc_info=True)
            return {
                "run_id":     self.run_id,
                "process_id": proceso["process_id"],
                "status":     "failed",
                "error":      str(exc),
                "findings":   state["findings"],  # los que alcanzó a registrar
                "tool_calls": state["tool_calls"],
                "metadata": {
                    "model":        MODEL,
                    "iterations":   state["iterations"],
                    "duration_secs": round(duration, 2),
                },
            }

    # -----------------------------------------------------------------------
    # Loop principal
    # -----------------------------------------------------------------------

    def _run_loop(self, state: dict) -> dict:
        """Loop de razonamiento: llama al LLM, ejecuta herramientas, repite."""

        while state["iterations"] < MAX_ITERATIONS:
            state["iterations"] += 1
            LOGGER.debug("[%s] Iteración %d", self.run_id, state["iterations"])

            # Llamar al LLM
            response = self.client.chat.completions.create(
                model=MODEL,
                messages=state["messages"],
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
                temperature=TEMPERATURE,
                max_tokens=4096,
            )

            # Acumular tokens
            if response.usage:
                state["total_tokens"] += response.usage.total_tokens

            message = response.choices[0].message
            state["messages"].append(message)  # Groq acepta el objeto directamente

            # ¿El agente quiere usar herramientas?
            if message.tool_calls:
                self._execute_tool_calls(message.tool_calls, state)
                continue

            # ¿El agente terminó? Intentar parsear el brief de cierre
            content = (message.content or "").strip()
            brief = self._try_parse_brief(content)
            if brief:
                return brief

            # El agente dijo algo pero no terminó ni llamó herramientas
            # Agregar su mensaje y pedirle que continúe o cierre
            if state["iterations"] >= MAX_ITERATIONS - 2:
                state["messages"].append({
                    "role": "user",
                    "content": (
                        "Has alcanzado el límite de iteraciones. "
                        "Registra los hallazgos pendientes con flag_finding si los tienes "
                        "y devuelve el JSON de cierre ahora."
                    ),
                })

        # Si agotó iteraciones sin cerrar, construir brief de emergencia
        LOGGER.warning("[%s] Agotó iteraciones sin cierre limpio", self.run_id)
        return self._fallback_brief(state)

    # -----------------------------------------------------------------------
    # Ejecución de herramientas
    # -----------------------------------------------------------------------

    def _execute_tool_calls(self, tool_calls: list, state: dict) -> None:
        """Ejecuta todas las herramientas solicitadas y agrega resultados al estado."""

        for tc in tool_calls:
            call_start = time.time()
            tool_name = tc.function.name
            call_order = len(state["tool_calls"]) + 1

            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}

            LOGGER.debug("[%s] Tool call %d: %s(%s)", self.run_id, call_order, tool_name, args)

            result = dispatch_tool(tool_name, args)
            duration_ms = int((time.time() - call_start) * 1000)

            # Si el agente registró un hallazgo, guardarlo en el estado
            if tool_name == "flag_finding" and result.get("registered"):
                state["findings"].append(result)
                LOGGER.info(
                    "[%s] Hallazgo registrado: %s (pág. %s)",
                    self.run_id, result.get("pattern_name"), result.get("page_number"),
                )

            # Guardar trazabilidad del tool call
            state["tool_calls"].append({
                "run_id":      self.run_id,
                "call_order":  call_order,
                "tool_name":   tool_name,
                "input":       args,
                "output":      result,
                "duration_ms": duration_ms,
            })

            # Agregar resultado al historial de mensajes
            state["messages"].append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      json.dumps(result, ensure_ascii=False),
            })

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _build_initial_message(self, proceso: dict) -> str:
        lines = [
            "Analiza el siguiente proceso de contratación:",
            f"- process_id: {proceso['process_id']}",
            f"- entidad: {proceso.get('entidad', 'No especificada')}",
            f"- objeto: {proceso.get('objeto', 'No especificado')}",
            f"- categoría: {proceso.get('categoria', 'No especificada')}",
            f"- pliego: {proceso.get('pliego_path', 'No disponible')}",
        ]

        if proceso.get("especificaciones_path"):
            lines.append(f"- especificaciones: {proceso['especificaciones_path']}")

        lines += [
            "",
            "Sigue el proceso de análisis descrito en tus instrucciones.",
            "Empieza por entender la estructura del documento principal.",
        ]

        return "\n".join(lines)

    def _try_parse_brief(self, content: str) -> dict | None:
        """Intenta parsear el JSON de cierre del agente."""
        if not content:
            return None

        # Buscar JSON en el contenido (puede venir con texto alrededor)
        start = content.find("{")
        end = content.rfind("}") + 1
        if start == -1 or end == 0:
            return None

        try:
            data = json.loads(content[start:end])
            if data.get("analysis_complete"):
                return data
        except json.JSONDecodeError:
            pass

        return None

    def _fallback_brief(self, state: dict) -> dict:
        """Brief mínimo cuando el agente no cerró limpiamente."""
        n = len(state["findings"])
        priority = sum(
            1 for f in state["findings"]
            if f.get("review_priority") == "priority"
        )
        return {
            "analysis_complete": True,
            "document_summary": f"Análisis parcial. Se registraron {n} hallazgos.",
            "overall_attention_level": "Medio" if priority > 0 else "Bajo",
            "main_review_topics": list({
                f.get("category", "Sin categoría")
                for f in state["findings"]
            }),
            "possible_competition_effects": "Ver hallazgos individuales.",
            "comparative_context": "No disponible.",
            "top_priorities_rationale": [
                f.get("rationale", "")
                for f in state["findings"]
                if f.get("review_priority") == "priority"
            ][:3],
            "suggested_human_review_questions": [],
            "methodological_note": (
                "Análisis incompleto por límite de iteraciones. "
                "Señales preliminares para revisión humana. No constituyen dictamen legal."
            ),
        }
