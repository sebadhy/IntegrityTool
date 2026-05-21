from __future__ import annotations

import os
from pathlib import Path


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# LLM — proveedor y modelo
# Prioridad: Azure OpenAI → Groq → Ollama → OpenAI directo
# ---------------------------------------------------------------------------

# Proveedor 1 y 4: Azure OpenAI / OpenAI directo
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Proveedor 2: Groq (gratis, llama-3.3-70b-versatile por defecto)
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Proveedor 3: Ollama local
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")

APP_MAX_DOCUMENT_CHARS = _int_env("APP_MAX_DOCUMENT_CHARS", 12_000)

# ---------------------------------------------------------------------------
# Corpus paths
# ---------------------------------------------------------------------------

APP_CORPUS_METADATA_PATH = Path(os.getenv("APP_CORPUS_METADATA_PATH", "data/raw/metadata/procesos.csv"))
APP_CORPUS_PLIEGOS_DIR = Path(os.getenv("APP_CORPUS_PLIEGOS_DIR", "data/raw/pliegos"))
APP_CORPUS_ESPECIFICACIONES_DIR = Path(os.getenv("APP_CORPUS_ESPECIFICACIONES_DIR", "data/raw/especificaciones"))
APP_CORPUS_PROCESSED_DIR = Path(os.getenv("APP_CORPUS_PROCESSED_DIR", "data/processed/extracted_text"))

# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

APP_DEFAULT_CONTEXT_CHARS = _int_env("APP_DEFAULT_CONTEXT_CHARS", 260)

# ---------------------------------------------------------------------------
# UI / report behavior
# ---------------------------------------------------------------------------

APP_REPORT_TOP_PRIORITIES = _int_env("APP_REPORT_TOP_PRIORITIES", 3)
APP_LLM_TOP_FINDINGS = _int_env("APP_LLM_TOP_FINDINGS", 5)
APP_LLM_BALANCE_ROWS = _int_env("APP_LLM_BALANCE_ROWS", 8)
APP_FEEDBACK_PATH = Path(os.getenv("APP_FEEDBACK_PATH", "data/feedback/cases.jsonl"))
