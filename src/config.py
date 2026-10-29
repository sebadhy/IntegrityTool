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
