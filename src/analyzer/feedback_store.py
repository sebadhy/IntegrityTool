from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from src.config import APP_FEEDBACK_PATH


def save_reviewer_feedback(
    *,
    signal: dict[str, Any],
    action: str,
    note: str = "",
    document_name: str = "",
) -> None:
    """Append human review feedback locally for audit and calibration.

    Feedback is evidence about the review workflow, not a conclusion about the
    procurement document. The JSONL file is intentionally local/gitignored.
    """
    APP_FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "document_name": document_name,
        "signal_id": signal.get("signal_id"),
        "pattern_id": signal.get("pattern_id"),
        "pattern_name": signal.get("pattern_name") or signal.get("patrón detectado"),
        "page": signal.get("página"),
        "action": action,
        "note": note.strip(),
        "fragment": signal.get("fragmento textual"),
    }
    with APP_FEEDBACK_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")
