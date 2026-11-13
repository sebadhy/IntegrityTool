"""Create a portable, read-only process snapshot from the official CSV download."""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import unicodedata
import zipfile


def normalize(value):
    return " ".join("".join(c for c in unicodedata.normalize("NFKD", value.casefold())
                            if not unicodedata.combining(c)).split())


def build(source: Path, output: Path, year: int):
    with zipfile.ZipFile(source) as archive:
        def rows(name):
            if archive.getinfo(name).file_size > 100 * 1024 * 1024:
                raise ValueError("El CSV supera el tamaño admitido.")
            return csv.DictReader(io.TextIOWrapper(archive.open(name), encoding="utf-8-sig"), strict=True)
        metadata, = list(rows(f"metadata_{year}.csv"))
        tender_fields = ["id", "description", "status", "procuringEntity_id", "procuringEntity_name",
                         "value_amount", "value_currency", "procurementMethodDetails", "tenderPeriod_startDate", "tenderPeriod_endDate"]
        tenders = {}
        for row in rows(f"tender_{year}.csv"):
            key = (row["ocid"], row["release_id"])
            if key in tenders:
                raise ValueError("El proceso tiene más de una ficha para la misma entrega.")
            tenders[key] = {field: row.get(field, "") for field in tender_fields}
        suppliers = defaultdict(list)
        for row in rows(f"suppliers_{year}.csv"):
            suppliers[(row["ocid"], row["release_id"])].append(row)

        with tempfile.TemporaryDirectory(prefix="sercop-build-") as temporary:
            database = Path(temporary) / "processes.sqlite3"
            with sqlite3.connect(database) as db:
                db.executescript("""
                    PRAGMA user_version=1;
                    CREATE TABLE processes(ocid TEXT PRIMARY KEY, code TEXT NOT NULL, buyer TEXT NOT NULL,
                        buyer_key TEXT NOT NULL, search_key TEXT NOT NULL, raw_json TEXT NOT NULL);
                    CREATE TABLE suppliers(ocid TEXT NOT NULL REFERENCES processes(ocid), identifier TEXT NOT NULL,
                        name TEXT NOT NULL, search_key TEXT NOT NULL);
                    CREATE INDEX suppliers_process ON suppliers(ocid);
                """)
                count = 0
                for row in rows(f"releases_{year}.csv"):
                    ocid = row["ocid"]
                    if not re.fullmatch(r"ocds-5wno2w-[A-Za-z0-9._-]{3,180}", ocid):
                        raise ValueError("El archivo contiene un OCID no válido.")
                    key = (ocid, row["id"])
                    tender = tenders.pop(key, {})
                    participants = suppliers.pop(key, [])
                    code = tender.get("id") or ocid
                    extract = {"format": "sercop_csv_extract/v1", "release": row, "tender": tender, "suppliers": participants}
                    db.execute("INSERT INTO processes VALUES (?,?,?,?,?,?)", (ocid, code, row["buyer_name"],
                               normalize(row["buyer_name"]), normalize(code + " " + ocid + " " + tender.get("description", "")),
                               json.dumps(extract, ensure_ascii=False, separators=(",", ":"))))
                    db.executemany("INSERT INTO suppliers VALUES (?,?,?,?)", [(ocid, p["id"], p["name"], normalize(p["name"])) for p in participants])
                    count += 1
                if tenders or suppliers:
                    raise ValueError("Hay fichas o proveedores sin una entrega correspondiente.")
                assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                supplier_count = db.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0]
            output.mkdir(parents=True, exist_ok=True)
            target = output / f"sercop_processes_{year}.sqlite3.gz"
            with database.open("rb") as handle, target.open("wb") as destination:
                with gzip.GzipFile(fileobj=destination, mode="wb", mtime=0, filename="") as zipped:
                    shutil.copyfileobj(handle, zipped)
            manifest = {"version": 1, "year": year, "process_count": count, "supplier_rows": supplier_count,
                        "published_at": metadata["PublishedDate"], "license": metadata["License"],
                        "source_url": f"https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/download?type=csv&year={year}&month=0&method=all",
                        "source_zip_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                        "file_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                        "database_bytes": database.stat().st_size,
                        "scope": "Extracto de columnas CSV publicadas. No es una respuesta de la API ni incluye los PDF."}
            (output / f"sercop_processes_{year}.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "src/resources")
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output, args.year), ensure_ascii=False, indent=2))
