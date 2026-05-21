"""
db.py — Conexión y schema SQL Server para el agente de análisis de pliegos.

Crea la base de datos y tablas si no existen.
Configuración via variables de entorno o .env
"""

from __future__ import annotations

import os
import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Generator

import pyodbc
from dotenv import load_dotenv

load_dotenv()

LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuración de conexión
# ---------------------------------------------------------------------------

def get_connection_string() -> str:
    server   = os.getenv("DB_SERVER", "localhost")
    database = os.getenv("DB_NAME", "pliegos_analysis")
    username = os.getenv("DB_USER", "")
    password = os.getenv("DB_PASSWORD", "")
    driver   = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")

    if not username or not password:
        raise ValueError(
            "DB_USER y DB_PASSWORD son requeridos. "
            "Configúralos en .env o como variables de entorno."
        )

    return (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={password};"
        "TrustServerCertificate=yes;"
    )


@contextmanager
def get_connection() -> Generator[pyodbc.Connection, None, None]:
    """Context manager que entrega una conexión y hace commit/rollback automático."""
    conn = pyodbc.connect(get_connection_string())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Inicialización del schema
# ---------------------------------------------------------------------------

DDL_STATEMENTS = [

    # Procesos analizados
    """
    IF NOT EXISTS (
        SELECT 1 FROM sys.tables WHERE name = 'procesos'
    )
    CREATE TABLE procesos (
        id                  INT IDENTITY(1,1) PRIMARY KEY,
        process_id          NVARCHAR(100)  NOT NULL UNIQUE,
        entidad             NVARCHAR(255),
        objeto              NVARCHAR(500),
        tipo_proceso        NVARCHAR(100),
        fecha_publicacion   DATE,
        categoria           NVARCHAR(100),
        monto_referencial   DECIMAL(18,2),
        pliego_file         NVARCHAR(500),
        especificaciones_file NVARCHAR(500),
        created_at          DATETIME2      NOT NULL DEFAULT GETDATE()
    )
    """,

    # Ejecuciones del agente (una por proceso por corrida)
    """
    IF NOT EXISTS (
        SELECT 1 FROM sys.tables WHERE name = 'agent_runs'
    )
    CREATE TABLE agent_runs (
        id              INT IDENTITY(1,1) PRIMARY KEY,
        run_id          NVARCHAR(64)   NOT NULL UNIQUE,
        process_id      NVARCHAR(100)  NOT NULL,
        status          NVARCHAR(20)   NOT NULL DEFAULT 'pending',
        -- pending | running | completed | failed
        model_used      NVARCHAR(100),
        total_tokens    INT,
        tool_calls      INT            DEFAULT 0,
        duration_secs   FLOAT,
        error_message   NVARCHAR(MAX),
        started_at      DATETIME2,
        completed_at    DATETIME2,
        created_at      DATETIME2      NOT NULL DEFAULT GETDATE()
    )
    """,

    # Llamadas a herramientas — trazabilidad de cada decisión del agente
    """
    IF NOT EXISTS (
        SELECT 1 FROM sys.tables WHERE name = 'tool_calls'
    )
    CREATE TABLE tool_calls (
        id          INT IDENTITY(1,1) PRIMARY KEY,
        run_id      NVARCHAR(64)   NOT NULL,
        call_order  INT            NOT NULL,
        tool_name   NVARCHAR(100)  NOT NULL,
        input_json  NVARCHAR(MAX),
        output_json NVARCHAR(MAX),
        duration_ms INT,
        called_at   DATETIME2      NOT NULL DEFAULT GETDATE()
    )
    """,

    # Hallazgos individuales detectados
    """
    IF NOT EXISTS (
        SELECT 1 FROM sys.tables WHERE name = 'findings'
    )
    CREATE TABLE findings (
        id                          INT IDENTITY(1,1) PRIMARY KEY,
        run_id                      NVARCHAR(64)   NOT NULL,
        process_id                  NVARCHAR(100)  NOT NULL,
        finding_id                  NVARCHAR(64)   NOT NULL,
        pattern_id                  NVARCHAR(100),
        pattern_name                NVARCHAR(255),
        category                    NVARCHAR(255),
        signal_type                 NVARCHAR(50),
        -- señal_revision | mitigante_concurrencia | requisito_habitual
        severity                    NVARCHAR(20),
        review_priority             NVARCHAR(20),
        confidence                  NVARCHAR(20),
        competition_dimension       NVARCHAR(255),
        document_section            NVARCHAR(255),
        page_number                 INT,
        evidence_text               NVARCHAR(MAX),
        rationale                   NVARCHAR(MAX),
        mitigating_factors          NVARCHAR(MAX),  -- JSON array
        escalation_factors          NVARCHAR(MAX),  -- JSON array
        suggested_questions         NVARCHAR(MAX),  -- JSON array
        possible_justifications     NVARCHAR(MAX),  -- JSON array
        normative_principle         NVARCHAR(500),
        normative_criterion         NVARCHAR(500),
        normative_question          NVARCHAR(500),
        corpus_frequency            NVARCHAR(50),
        corpus_classification       NVARCHAR(100),
        created_at                  DATETIME2      NOT NULL DEFAULT GETDATE()
    )
    """,

    # Resumen ejecutivo generado por el agente para cada proceso
    """
    IF NOT EXISTS (
        SELECT 1 FROM sys.tables WHERE name = 'agent_briefs'
    )
    CREATE TABLE agent_briefs (
        id                              INT IDENTITY(1,1) PRIMARY KEY,
        run_id                          NVARCHAR(64)   NOT NULL UNIQUE,
        process_id                      NVARCHAR(100)  NOT NULL,
        document_summary                NVARCHAR(MAX),
        overall_attention_level         NVARCHAR(20),
        main_review_topics              NVARCHAR(MAX),  -- JSON array
        possible_competition_effects    NVARCHAR(MAX),
        comparative_context             NVARCHAR(MAX),
        top_priorities_rationale        NVARCHAR(MAX),  -- JSON array
        suggested_review_questions      NVARCHAR(MAX),  -- JSON array
        methodological_note             NVARCHAR(MAX),
        agent_reasoning                 NVARCHAR(MAX),  -- razonamiento del agente
        created_at                      DATETIME2      NOT NULL DEFAULT GETDATE()
    )
    """,

    # Índices útiles para las queries del dashboard
    """
    IF NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'ix_findings_process_id' AND object_id = OBJECT_ID('findings')
    )
    CREATE INDEX ix_findings_process_id ON findings(process_id)
    """,

    """
    IF NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'ix_findings_signal_type' AND object_id = OBJECT_ID('findings')
    )
    CREATE INDEX ix_findings_signal_type ON findings(signal_type)
    """,

    """
    IF NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'ix_agent_runs_process_id' AND object_id = OBJECT_ID('agent_runs')
    )
    CREATE INDEX ix_agent_runs_process_id ON agent_runs(process_id)
    """,

    """
    IF NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'ix_tool_calls_run_id' AND object_id = OBJECT_ID('tool_calls')
    )
    CREATE INDEX ix_tool_calls_run_id ON tool_calls(run_id)
    """,

    # Destinatarios de notificaciones de alertas
    """
    IF NOT EXISTS (
        SELECT 1 FROM sys.tables WHERE name = 'notificacion_destinatarios'
    )
    CREATE TABLE notificacion_destinatarios (
        id         INT IDENTITY(1,1) PRIMARY KEY,
        email      NVARCHAR(255) NOT NULL UNIQUE,
        nombre     NVARCHAR(255),
        activo     BIT           NOT NULL DEFAULT 1,
        created_at DATETIME2     NOT NULL DEFAULT GETDATE()
    )
    """,

    # Corpus histórico — un registro por proceso analizado, para comparación de patrones
    """
    IF NOT EXISTS (
        SELECT 1 FROM sys.tables WHERE name = 'corpus_documentos'
    )
    CREATE TABLE corpus_documentos (
        id                INT IDENTITY(1,1) PRIMARY KEY,
        process_id        NVARCHAR(100) NOT NULL,
        nombre_archivo    NVARCHAR(500),
        entidad           NVARCHAR(255),
        objeto            NVARCHAR(500),
        categoria         NVARCHAR(100),
        fuente            NVARCHAR(50)  NOT NULL DEFAULT 'ui_upload',
        hallazgos_json    NVARCHAR(MAX),
        total_hallazgos   INT           DEFAULT 0,
        nivel_atencion    NVARCHAR(20),
        analizado_en      DATETIME2     NOT NULL DEFAULT GETDATE(),
        CONSTRAINT uq_corpus_process UNIQUE (process_id)
    )
    """,
]


def init_db() -> None:
    """Crea la base de datos y todas las tablas si no existen. Idempotente."""
    LOGGER.info("Inicializando schema SQL Server...")
    with get_connection() as conn:
        cursor = conn.cursor()
        for statement in DDL_STATEMENTS:
            cursor.execute(statement)
        conn.commit()
    LOGGER.info("Schema listo.")


# ---------------------------------------------------------------------------
# Operaciones de escritura
# ---------------------------------------------------------------------------

def upsert_proceso(conn: pyodbc.Connection, proceso: dict) -> None:
    """Inserta o actualiza un proceso en la tabla procesos."""
    cursor = conn.cursor()
    cursor.execute("""
        MERGE procesos AS target
        USING (SELECT ? AS process_id) AS source
        ON target.process_id = source.process_id
        WHEN MATCHED THEN UPDATE SET
            entidad               = ?,
            objeto                = ?,
            tipo_proceso          = ?,
            fecha_publicacion     = ?,
            categoria             = ?,
            monto_referencial     = ?,
            pliego_file           = ?,
            especificaciones_file = ?
        WHEN NOT MATCHED THEN INSERT (
            process_id, entidad, objeto, tipo_proceso,
            fecha_publicacion, categoria, monto_referencial,
            pliego_file, especificaciones_file
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
    """,
        proceso["process_id"],
        proceso.get("entidad"), proceso.get("objeto"),
        proceso.get("tipo_proceso"), proceso.get("fecha_publicacion"),
        proceso.get("categoria"), proceso.get("monto_referencial"),
        proceso.get("pliego_file"), proceso.get("especificaciones_file"),
        # WHEN NOT MATCHED values
        proceso["process_id"],
        proceso.get("entidad"), proceso.get("objeto"),
        proceso.get("tipo_proceso"), proceso.get("fecha_publicacion"),
        proceso.get("categoria"), proceso.get("monto_referencial"),
        proceso.get("pliego_file"), proceso.get("especificaciones_file"),
    )


def insert_run(conn: pyodbc.Connection, run: dict) -> None:
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO agent_runs (
            run_id, process_id, status, model_used, started_at
        ) VALUES (?, ?, ?, ?, ?)
    """,
        run["run_id"], run["process_id"],
        run.get("status", "running"),
        run.get("model_used"), run.get("started_at", datetime.utcnow()),
    )


def update_run(conn: pyodbc.Connection, run_id: str, update: dict) -> None:
    fields = ", ".join(f"{k} = ?" for k in update)
    values = list(update.values()) + [run_id]
    conn.cursor().execute(
        f"UPDATE agent_runs SET {fields} WHERE run_id = ?", values
    )


def insert_tool_call(conn: pyodbc.Connection, call: dict) -> None:
    import json
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO tool_calls (
            run_id, call_order, tool_name,
            input_json, output_json, duration_ms
        ) VALUES (?, ?, ?, ?, ?, ?)
    """,
        call["run_id"], call["call_order"], call["tool_name"],
        json.dumps(call.get("input"), ensure_ascii=False),
        json.dumps(call.get("output"), ensure_ascii=False),
        call.get("duration_ms"),
    )


def insert_finding(conn: pyodbc.Connection, run_id: str, process_id: str, finding: dict) -> None:
    import json
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO findings (
            run_id, process_id, finding_id, pattern_id, pattern_name,
            category, signal_type, severity, review_priority, confidence,
            competition_dimension, document_section, page_number,
            evidence_text, rationale,
            mitigating_factors, escalation_factors, suggested_questions,
            possible_justifications,
            normative_principle, normative_criterion, normative_question,
            corpus_frequency, corpus_classification
        ) VALUES (
            ?,?,?,?,?,  ?,?,?,?,?,  ?,?,?,  ?,?,  ?,?,?,?,  ?,?,?,  ?,?
        )
    """,
        run_id, process_id,
        finding.get("finding_id"), finding.get("pattern_id"), finding.get("pattern_name"),
        finding.get("categoría") or finding.get("category"),
        finding.get("tipo_señal") or finding.get("signal_type"),
        finding.get("severity"), finding.get("review_priority"), finding.get("confidence"),
        finding.get("competition_dimension"), finding.get("document_section"),
        finding.get("página") or finding.get("page"),
        finding.get("fragmento textual") or finding.get("evidence"),
        finding.get("observación prudente") or finding.get("rationale"),
        json.dumps(finding.get("mitigating_factors", []), ensure_ascii=False),
        json.dumps(finding.get("escalation_factors", []), ensure_ascii=False),
        json.dumps(finding.get("suggested_questions", []), ensure_ascii=False),
        json.dumps(finding.get("possible_legitimate_justifications", []), ensure_ascii=False),
        finding.get("principio_normativo_relacionado"),
        finding.get("criterio_normativo_de_revision"),
        finding.get("pregunta_normativa_sugerida"),
        finding.get("frecuencia en corpus"), finding.get("clasificación histórica"),
    )


def insert_brief(conn: pyodbc.Connection, run_id: str, process_id: str, brief: dict) -> None:
    import json
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO agent_briefs (
            run_id, process_id, document_summary, overall_attention_level,
            main_review_topics, possible_competition_effects, comparative_context,
            top_priorities_rationale, suggested_review_questions,
            methodological_note, agent_reasoning
        ) VALUES (?,?,?,?,  ?,?,?,  ?,?,  ?,?)
    """,
        run_id, process_id,
        brief.get("document_summary"), brief.get("overall_attention_level"),
        json.dumps(brief.get("main_review_topics", []), ensure_ascii=False),
        brief.get("possible_competition_effects"), brief.get("comparative_context"),
        json.dumps(brief.get("top_priorities_rationale", []), ensure_ascii=False),
        json.dumps(brief.get("suggested_human_review_questions", []), ensure_ascii=False),
        brief.get("methodological_note"), brief.get("agent_reasoning"),
    )


# ---------------------------------------------------------------------------
# Operaciones de lectura (para el dashboard)
# ---------------------------------------------------------------------------

def get_all_runs(conn: pyodbc.Connection) -> list[dict]:
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            r.run_id, r.process_id, r.status, r.model_used,
            r.tool_calls, r.duration_secs, r.started_at, r.completed_at,
            r.error_message,
            p.entidad, p.objeto, p.categoria,
            b.overall_attention_level,
            COUNT(f.id) AS total_findings,
            SUM(CASE WHEN f.signal_type = 'señal_revision'
                     AND f.review_priority = 'priority' THEN 1 ELSE 0 END) AS priority_findings
        FROM agent_runs r
        LEFT JOIN procesos p ON r.process_id = p.process_id
        LEFT JOIN agent_briefs b ON r.run_id = b.run_id
        LEFT JOIN findings f ON r.run_id = f.run_id
        GROUP BY
            r.run_id, r.process_id, r.status, r.model_used,
            r.tool_calls, r.duration_secs, r.started_at, r.completed_at,
            r.error_message,
            p.entidad, p.objeto, p.categoria,
            b.overall_attention_level
        ORDER BY r.started_at DESC
    """)
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_findings_for_run(conn: pyodbc.Connection, run_id: str) -> list[dict]:
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM findings
        WHERE run_id = ?
        ORDER BY
            CASE review_priority
                WHEN 'priority'  THEN 1
                WHEN 'suggested' THEN 2
                ELSE 3
            END,
            page_number
    """, run_id)
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_brief_for_run(conn: pyodbc.Connection, run_id: str) -> dict | None:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM agent_briefs WHERE run_id = ?", run_id)
    row = cursor.fetchone()
    if not row:
        return None
    columns = [col[0] for col in cursor.description]
    return dict(zip(columns, row))


def get_tool_calls_for_run(conn: pyodbc.Connection, run_id: str) -> list[dict]:
    """Trazabilidad completa de decisiones del agente para un run."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT call_order, tool_name, input_json, output_json, duration_ms, called_at
        FROM tool_calls
        WHERE run_id = ?
        ORDER BY call_order
    """, run_id)
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def process_already_analyzed(conn: pyodbc.Connection, process_id: str) -> bool:
    """Retorna True si el proceso ya tiene un run completado exitosamente."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(1) FROM agent_runs
        WHERE process_id = ? AND status = 'completed'
    """, process_id)
    return cursor.fetchone()[0] > 0


# ---------------------------------------------------------------------------
# Destinatarios de notificaciones
# ---------------------------------------------------------------------------

def get_active_recipients(conn: pyodbc.Connection) -> list[str]:
    """Retorna lista de emails activos para notificaciones."""
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM notificacion_destinatarios WHERE activo = 1 ORDER BY email")
    return [row[0] for row in cursor.fetchall()]


def get_all_recipients(conn: pyodbc.Connection) -> list[dict]:
    """Retorna todos los destinatarios (activos e inactivos) con su info."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, email, nombre, activo, created_at
        FROM notificacion_destinatarios
        ORDER BY activo DESC, email
    """)
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def add_recipient(conn: pyodbc.Connection, email: str, nombre: str = "") -> None:
    """Agrega un destinatario. Si ya existe, lo reactiva."""
    cursor = conn.cursor()
    cursor.execute("""
        MERGE notificacion_destinatarios AS target
        USING (SELECT ? AS email) AS source ON target.email = source.email
        WHEN MATCHED THEN UPDATE SET activo = 1, nombre = ?
        WHEN NOT MATCHED THEN INSERT (email, nombre, activo) VALUES (?, ?, 1);
    """, email, nombre or "", email, nombre or "")


def remove_recipient(conn: pyodbc.Connection, email: str) -> None:
    """Desactiva un destinatario (soft delete)."""
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE notificacion_destinatarios SET activo = 0 WHERE email = ?",
        email,
    )


# ---------------------------------------------------------------------------
# Guardar resultados del pipeline desde la UI
# ---------------------------------------------------------------------------

def save_pipeline_results(
    document_name: str,
    brief: dict | None,
    enriched_df,  # pd.DataFrame — no importamos pandas aquí para no crear dependencia circular
    model_used: str = "",
) -> tuple[bool, str]:
    """
    Guarda los resultados del análisis de la UI en SQL Server.
    Retorna (success, message). Falla de forma silenciosa si la BD no está disponible.
    """
    import uuid
    import re
    from datetime import datetime

    run_id = str(uuid.uuid4())
    safe_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", document_name.replace(".pdf", ""))[:80]
    process_id = f"ui_{safe_name}"

    try:
        with get_connection() as conn:
            # Registro del proceso
            upsert_proceso(conn, {
                "process_id": process_id,
                "entidad": None,
                "objeto": document_name,
                "tipo_proceso": "ui_upload",
                "fecha_publicacion": None,
                "categoria": None,
                "monto_referencial": None,
                "pliego_file": document_name,
                "especificaciones_file": None,
            })

            # Registro de la ejecución
            insert_run(conn, {
                "run_id": run_id,
                "process_id": process_id,
                "status": "completed",
                "model_used": model_used,
                "started_at": datetime.utcnow(),
            })
            update_run(conn, run_id, {
                "status": "completed",
                "completed_at": datetime.utcnow(),
                "tool_calls": 0,
            })

            # Hallazgos
            for _, row in enriched_df.iterrows():
                finding = _normalize_pipeline_finding(row.to_dict())
                try:
                    insert_finding(conn, run_id, process_id, finding)
                except Exception as exc:
                    LOGGER.warning("No se pudo guardar hallazgo: %s", exc)

            # Brief ejecutivo
            if brief and brief.get("document_summary") not in (None, "No disponible"):
                try:
                    insert_brief(conn, run_id, process_id, brief)
                except Exception as exc:
                    LOGGER.warning("No se pudo guardar brief: %s", exc)

        total = len(enriched_df)
        return True, f"Resultados guardados en BD: {total} hallazgo(s), run {run_id[:8]}…"

    except Exception as exc:
        LOGGER.error("Error guardando resultados en BD: %s", exc)
        return False, f"No se pudo guardar en BD: {exc}"


def _normalize_pipeline_finding(row: dict) -> dict:
    """Mapea columnas del enriched_df a las claves que espera insert_finding."""
    return {
        **row,
        "finding_id":       row.get("signal_id") or row.get("finding_id"),
        "pattern_name":     row.get("patrón detectado") or row.get("pattern_name"),
        "categoría":        row.get("categoría de revisión") or row.get("categoría"),
        "observación prudente": (
            row.get("observación prudente")
            or row.get("por qué se sugiere revisar")
            or row.get("rationale")
        ),
        "página": row.get("página") or row.get("page_number"),
    }


# ---------------------------------------------------------------------------
# Corpus histórico — escritura y lectura
# ---------------------------------------------------------------------------

def upsert_corpus_documento(
    conn: pyodbc.Connection,
    process_id: str,
    document_name: str,
    hallazgos_df,           # pd.DataFrame con el enriched_df del pipeline
    nivel_atencion: str | None = None,
    entidad: str | None = None,
    objeto: str | None = None,
    categoria: str | None = None,
) -> None:
    """
    Inserta o actualiza un documento en el corpus histórico.
    Guarda solo los campos mínimos necesarios para comparación de patrones.
    """
    import json

    # Compactar hallazgos: solo lo necesario para frecuencia de patrones
    hallazgos: list[dict] = []
    if hallazgos_df is not None and not hallazgos_df.empty:
        for _, row in hallazgos_df.iterrows():
            hallazgos.append({
                "p": str(row.get("patrón detectado", "")),
                "c": str(row.get("categoría de revisión", row.get("categoría", ""))),
                "t": str(row.get("tipo_señal", "señal_revision")),
            })

    hallazgos_json = json.dumps(hallazgos, ensure_ascii=False)
    total = len(hallazgos)

    cursor = conn.cursor()
    cursor.execute("""
        MERGE corpus_documentos AS target
        USING (SELECT ? AS process_id) AS source ON target.process_id = source.process_id
        WHEN MATCHED THEN UPDATE SET
            nombre_archivo  = ?,
            hallazgos_json  = ?,
            total_hallazgos = ?,
            nivel_atencion  = ?,
            entidad         = ?,
            objeto          = ?,
            categoria       = ?,
            analizado_en    = GETDATE()
        WHEN NOT MATCHED THEN INSERT (
            process_id, nombre_archivo, hallazgos_json, total_hallazgos,
            nivel_atencion, entidad, objeto, categoria, fuente
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ui_upload');
    """,
        process_id,
        # WHEN MATCHED
        document_name, hallazgos_json, total, nivel_atencion, entidad, objeto, categoria,
        # WHEN NOT MATCHED
        process_id, document_name, hallazgos_json, total, nivel_atencion, entidad, objeto, categoria,
    )


def get_corpus_analysis_from_db(conn: pyodbc.Connection) -> dict:
    """
    Lee el corpus histórico desde corpus_documentos y devuelve la estructura
    que espera build_corpus_context() de review_synthesis.py:
      {
        "total_processes": int,
        "analysis": { "pattern_frequency": [...], ... },
        "source": "db",
      }
    """
    import json
    from collections import Counter

    cursor = conn.cursor()
    cursor.execute("""
        SELECT process_id, hallazgos_json
        FROM corpus_documentos
        ORDER BY analizado_en DESC
    """)
    rows = cursor.fetchall()

    if not rows:
        return _empty_corpus_analysis()

    total_processes = len(rows)

    # Contar en cuántos procesos aparece cada patrón (sin duplicar por proceso)
    pattern_process_count: Counter[str] = Counter()
    pattern_total_count: Counter[str] = Counter()

    for _, hallazgos_json in rows:
        try:
            hallazgos = json.loads(hallazgos_json or "[]")
        except Exception:
            hallazgos = []

        seen_in_process: set[str] = set()
        for h in hallazgos:
            p = h.get("p", "")
            if not p:
                continue
            if p not in seen_in_process:
                pattern_process_count[p] += 1
                seen_in_process.add(p)
            pattern_total_count[p] += 1

    pattern_frequency = []
    for pattern, proc_count in pattern_process_count.most_common():
        freq = proc_count / total_processes
        pattern_frequency.append({
            "patrón detectado":  pattern,
            "procesos con patrón": proc_count,
            "total procesos":    total_processes,
            "frecuencia":        round(freq, 4),
            "coincidencias":     pattern_total_count[pattern],
            "rareza":            _rarity_label(freq),
            "comentario_comparativo": _rarity_comment(freq),
        })

    return {
        "total_processes": total_processes,
        "analysis": {
            "pattern_frequency": pattern_frequency,
            "category_frequency": [],
            "process_frequency": [],
            "similar_documents": [],
        },
        "source": "db",
    }


def _empty_corpus_analysis() -> dict:
    return {
        "total_processes": 0,
        "analysis": {
            "pattern_frequency": [],
            "category_frequency": [],
            "process_frequency": [],
            "similar_documents": [],
        },
        "source": "db",
    }


def _rarity_label(frequency: float) -> str:
    if frequency <= 0.2:
        return "Poco frecuente"
    if frequency >= 0.7:
        return "Habitual"
    return "Intermedio"


def _rarity_comment(frequency: float) -> str:
    if frequency <= 0.2:
        return "Requisito poco frecuente respecto de procesos comparables analizados."
    if frequency >= 0.7:
        return "Patrón presente en la mayoría de procesos similares analizados."
    return "Presencia intermedia respecto del histórico analizado."


# ---------------------------------------------------------------------------
# Punto de entrada para crear el schema manualmente
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    print("Base de datos inicializada correctamente.")
