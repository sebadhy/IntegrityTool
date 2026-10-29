"""Shared CSV reader for document headers and corpus metadata."""

from __future__ import annotations

import csv
from pathlib import Path


def read_process_metadata(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        sample = file.read(4096)
        file.seek(0)
        if not sample.strip():
            return []
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,")
            reader = csv.DictReader(file, dialect=dialect)
        except csv.Error:
            delimiter = ";" if sample.splitlines()[0].count(";") > sample.splitlines()[0].count(",") else ","
            reader = csv.DictReader(file, delimiter=delimiter)
        rows = []
        for raw in reader:
            rows.append({
                str(key).strip().lstrip("\ufeff"): str(value or "").strip()
                for key, value in raw.items()
                if key and str(key).strip() and not str(key).strip().startswith("Unnamed")
            })
    return rows
