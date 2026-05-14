"""Central configuration module.

All tunable parameters live here. Values are read from environment variables
(loaded from .env) with typed defaults. Import from this module instead of
scattering os.getenv() calls or magic numbers across the codebase.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

LLM_DEFAULT_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
LLM_MAX_DOCUMENT_CHARS: int = int(os.getenv("APP_MAX_DOCUMENT_CHARS", "12000"))

# ---------------------------------------------------------------------------
# Corpus paths
# ---------------------------------------------------------------------------

CORPUS_METADATA_PATH: Path = Path(
    os.getenv("APP_CORPUS_METADATA_PATH", "data/raw/metadata/procesos.csv")
)
CORPUS_PLIEGOS_DIR: Path = Path(
    os.getenv("APP_CORPUS_PLIEGOS_DIR", "data/raw/pliegos")
)
CORPUS_ESPECIFICACIONES_DIR: Path = Path(
    os.getenv("APP_CORPUS_ESPECIFICACIONES_DIR", "data/raw/especificaciones")
)
CORPUS_PROCESSED_DIR: Path = Path(
    os.getenv("APP_CORPUS_PROCESSED_DIR", "data/processed/extracted_text")
)

# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

DETECTION_DEFAULT_CONTEXT_CHARS: int = int(
    os.getenv("APP_DEFAULT_CONTEXT_CHARS", "260")
)

# ---------------------------------------------------------------------------
# UI / report behavior
# ---------------------------------------------------------------------------

UI_REPORT_TOP_PRIORITIES: int = int(os.getenv("APP_REPORT_TOP_PRIORITIES", "3"))
UI_LLM_TOP_FINDINGS: int = int(os.getenv("APP_LLM_TOP_FINDINGS", "5"))
UI_LLM_BALANCE_ROWS: int = int(os.getenv("APP_LLM_BALANCE_ROWS", "8"))
