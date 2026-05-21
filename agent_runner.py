"""
agent_runner.py — Procesador batch de pliegos.

El analista corre esto desde la terminal para analizar
todos los procesos pendientes en la carpeta de entrada.

Uso:
    python agent_runner.py
    python agent_runner.py --force          # re-analiza aunque ya estén procesados
    python agent_runner.py --process SIE-001  # analiza solo ese proceso
    python agent_runner.py --dry-run        # muestra qué procesaría sin ejecutar
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

from agent import PligoAgent
from db import (
    get_connection,
    init_db,
    insert_brief,
    insert_finding,
    insert_run,
    insert_tool_call,
    process_already_analyzed,
    update_run,
    upsert_proceso,
)

# ---------------------------------------------------------------------------
# Configuración de rutas (igual que el proyecto actual)
# ---------------------------------------------------------------------------

DATA_DIR        = Path("data/raw")
PLIEGOS_DIR     = DATA_DIR / "pliegos"
SPECS_DIR       = DATA_DIR / "especificaciones"
METADATA_FILE   = DATA_DIR / "metadata" / "procesos.csv"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("agent_runner.log", encoding="utf-8"),
    ],
)
LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Carga de metadata
# ---------------------------------------------------------------------------

def load_metadata(force_process_id: str | None = None) -> list[dict]:
    """Carga procesos.csv y construye las rutas de los PDFs."""
    if not METADATA_FILE.exists():
        LOGGER.error("No se encontró %s", METADATA_FILE)
        sys.exit(1)

    df = pd.read_csv(METADATA_FILE, dtype=str).fillna("")

    required_cols = {"process_id", "pliego_file"}
    missing = required_cols - set(df.columns)
    if missing:
        LOGGER.error("Columnas faltantes en procesos.csv: %s", missing)
        sys.exit(1)

    if force_process_id:
        df = df[df["process_id"] == force_process_id]
        if df.empty:
            LOGGER.error("process_id '%s' no encontrado en metadata", force_process_id)
            sys.exit(1)

    procesos = []
    for _, row in df.iterrows():
        pliego_path = PLIEGOS_DIR / row["pliego_file"]
        specs_file  = row.get("especificaciones_file", "").strip()
        specs_path  = SPECS_DIR / specs_file if specs_file else None

        procesos.append({
            "process_id":             row["process_id"].strip(),
            "entidad":                row.get("entidad", ""),
            "objeto":                 row.get("objeto", ""),
            "tipo_proceso":           row.get("tipo_proceso", ""),
            "fecha_publicacion":      row.get("fecha_publicacion") or None,
            "categoria":              row.get("categoria", ""),
            "monto_referencial":      _parse_float(row.get("monto_referencial")),
            "pliego_file":            row["pliego_file"],
            "especificaciones_file":  specs_file or None,
            "pliego_path":            str(pliego_path.resolve()),
            "especificaciones_path":  str(specs_path.resolve()) if specs_path else None,
            "_pliego_exists":         pliego_path.exists(),
            "_specs_exists":          specs_path.exists() if specs_path else None,
        })

    return procesos


# ---------------------------------------------------------------------------
# Runner principal
# ---------------------------------------------------------------------------

def run_batch(
    force: bool = False,
    force_process_id: str | None = None,
    dry_run: bool = False,
) -> None:

    LOGGER.info("=" * 60)
    LOGGER.info("Agente de análisis de pliegos — inicio batch")
    LOGGER.info("=" * 60)

    # Inicializar base de datos
    init_db()

    # Cargar metadata
    procesos = load_metadata(force_process_id)
    LOGGER.info("Procesos en metadata: %d", len(procesos))

    # Filtrar los que tienen PDF disponible
    disponibles = [p for p in procesos if p["_pliego_exists"]]
    sin_pdf     = [p for p in procesos if not p["_pliego_exists"]]

    if sin_pdf:
        LOGGER.warning(
            "Procesos sin PDF disponible (%d): %s",
            len(sin_pdf), [p["process_id"] for p in sin_pdf],
        )

    if not disponibles:
        LOGGER.error("No hay PDFs disponibles para procesar.")
        return

    # Filtrar ya analizados (a menos que --force)
    if not force:
        with get_connection() as conn:
            pendientes = [
                p for p in disponibles
                if not process_already_analyzed(conn, p["process_id"])
            ]
        ya_analizados = len(disponibles) - len(pendientes)
        if ya_analizados:
            LOGGER.info(
                "Procesos ya analizados (omitidos): %d. Usa --force para re-analizar.",
                ya_analizados,
            )
    else:
        pendientes = disponibles

    LOGGER.info("Procesos a analizar: %d", len(pendientes))

    if dry_run:
        LOGGER.info("DRY RUN — no se ejecutará el análisis")
        for p in pendientes:
            LOGGER.info("  → %s | %s | %s", p["process_id"], p["entidad"], p["objeto"])
        return

    if not pendientes:
        LOGGER.info("No hay procesos pendientes. Fin.")
        return

    # Procesar cada uno
    agent   = PligoAgent()
    summary = {"completed": 0, "failed": 0, "total_findings": 0}
    batch_start = time.time()

    for idx, proceso in enumerate(pendientes, 1):
        pid = proceso["process_id"]
        LOGGER.info(
            "[%d/%d] Analizando %s — %s",
            idx, len(pendientes), pid, proceso.get("objeto", "")[:60],
        )

        # Persistir metadata del proceso
        with get_connection() as conn:
            upsert_proceso(conn, proceso)

        # Correr el agente
        result = agent.analyze(proceso)

        # Persistir resultados
        _persist_result(result, proceso)

        # Acumular resumen
        if result["status"] == "completed":
            summary["completed"] += 1
            summary["total_findings"] += len(result.get("findings", []))
        else:
            summary["failed"] += 1

        # Pequeña pausa entre documentos para no saturar la API de Groq
        if idx < len(pendientes):
            time.sleep(1.5)

    # Resumen final
    total_time = time.time() - batch_start
    LOGGER.info("=" * 60)
    LOGGER.info("Batch completado en %.1fs", total_time)
    LOGGER.info(
        "Completados: %d | Fallidos: %d | Hallazgos totales: %d",
        summary["completed"], summary["failed"], summary["total_findings"],
    )
    LOGGER.info("=" * 60)


# ---------------------------------------------------------------------------
# Persistencia de un resultado completo
# ---------------------------------------------------------------------------

def _persist_result(result: dict, proceso: dict) -> None:
    """Guarda run, tool calls, findings y brief en SQL Server."""
    run_id     = result["run_id"]
    process_id = result["process_id"]
    meta       = result.get("metadata", {})

    with get_connection() as conn:

        # Insertar run
        insert_run(conn, {
            "run_id":     run_id,
            "process_id": process_id,
            "status":     result["status"],
            "model_used": meta.get("model"),
            "started_at": meta.get("started_at"),
        })

        # Tool calls (trazabilidad de decisiones del agente)
        for tc in result.get("tool_calls", []):
            insert_tool_call(conn, tc)

        # Hallazgos individuales
        for finding in result.get("findings", []):
            insert_finding(conn, run_id, process_id, finding)

        # Brief ejecutivo
        if result.get("brief"):
            brief = result["brief"]
            brief["agent_reasoning"] = _extract_reasoning(result)
            insert_brief(conn, run_id, process_id, brief)

        # Actualizar estado final del run
        update_run(conn, run_id, {
            "status":       result["status"],
            "tool_calls":   len(result.get("tool_calls", [])),
            "total_tokens": meta.get("total_tokens"),
            "duration_secs": meta.get("duration_secs"),
            "completed_at": meta.get("completed_at"),
            "error_message": result.get("error"),
        })

    LOGGER.info(
        "[%s] Persistido: %d hallazgos, %d tool calls",
        process_id,
        len(result.get("findings", [])),
        len(result.get("tool_calls", [])),
    )


def _extract_reasoning(result: dict) -> str:
    """Extrae un resumen del razonamiento del agente de los tool calls."""
    calls = result.get("tool_calls", [])
    if not calls:
        return ""
    lines = []
    for tc in calls:
        lines.append(f"[{tc['call_order']}] {tc['tool_name']}({list(tc.get('input', {}).keys())})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_float(value: str | None) -> float | None:
    if not value or not str(value).strip():
        return None
    try:
        return float(str(value).replace(",", ".").replace(" ", ""))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Agente batch de análisis de neutralidad competitiva en pliegos."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-analiza procesos aunque ya tengan un run completado.",
    )
    parser.add_argument(
        "--process",
        metavar="PROCESS_ID",
        help="Analiza solo el proceso con este ID.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra qué procesaría sin ejecutar el análisis.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_batch(
        force=args.force,
        force_process_id=args.process,
        dry_run=args.dry_run,
    )
