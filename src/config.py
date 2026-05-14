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


OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
APP_MAX_DOCUMENT_CHARS = _int_env("APP_MAX_DOCUMENT_CHARS", 12_000)
APP_CORPUS_METADATA_PATH = Path(os.getenv("APP_CORPUS_METADATA_PATH", "data/raw/metadata/procesos.csv"))
APP_CORPUS_PLIEGOS_DIR = Path(os.getenv("APP_CORPUS_PLIEGOS_DIR", "data/raw/pliegos"))
APP_CORPUS_ESPECIFICACIONES_DIR = Path(os.getenv("APP_CORPUS_ESPECIFICACIONES_DIR", "data/raw/especificaciones"))
APP_CORPUS_PROCESSED_DIR = Path(os.getenv("APP_CORPUS_PROCESSED_DIR", "data/processed/extracted_text"))
APP_DEFAULT_CONTEXT_CHARS = _int_env("APP_DEFAULT_CONTEXT_CHARS", 260)
APP_REPORT_TOP_PRIORITIES = _int_env("APP_REPORT_TOP_PRIORITIES", 3)
APP_LLM_TOP_FINDINGS = _int_env("APP_LLM_TOP_FINDINGS", 5)
APP_LLM_BALANCE_ROWS = _int_env("APP_LLM_BALANCE_ROWS", 8)
APP_FEEDBACK_PATH = Path(os.getenv("APP_FEEDBACK_PATH", "data/feedback/cases.jsonl"))
