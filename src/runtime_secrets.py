"""Load an explicit allowlist of mounted secrets; never log their contents."""
from __future__ import annotations

import os
from pathlib import Path

SECRET_NAMES = ("INTEGRITY_DATABASE_URL", "OPENAI_API_KEY", "GROQ_API_KEY",
                "INTEGRITY_BLOB_CONNECTION_STRING")


def load_secret_files():
    for name in SECRET_NAMES:
        filename = os.getenv(name + "_FILE")
        if not filename:
            continue
        try:
            path = Path(filename)
            if not path.is_file() or path.stat().st_size > 16384:
                raise ValueError()
            value = path.read_text(encoding="utf-8").strip()
            if not value or "\n" in value or "\r" in value:
                raise ValueError()
        except (OSError, UnicodeError, ValueError):
            raise ValueError(f"No se pudo leer el secreto {name}_FILE.") from None
        if os.getenv(name) and os.environ[name] != value:
            raise ValueError(f"Configure solo {name} o {name}_FILE, sin valores distintos.")
        os.environ[name] = value
