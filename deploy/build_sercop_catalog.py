"""Build a reproducible suggestion snapshot from an official SERCOP CSV ZIP."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import zipfile


def build(source: Path, output: Path, year: int):
    with zipfile.ZipFile(source) as archive:
        def rows(name):
            info = archive.getinfo(name)
            if info.file_size > 100 * 1024 * 1024:
                raise ValueError("El CSV supera el tamaño admitido.")
            return csv.DictReader(io.TextIOWrapper(archive.open(name), encoding="utf-8-sig"), strict=True)

        metadata = list(rows(f"metadata_{year}.csv"))
        if len(metadata) != 1:
            raise ValueError("La publicación debe tener metadata única.")
        result, counts = {}, {}
        for kind, filename, id_field, name_field in [
            ("buyer", f"releases_{year}.csv", "buyer_id", "buyer_name"),
            ("supplier", f"suppliers_{year}.csv", "id", "name"),
        ]:
            entries, row_count = set(), 0
            for row in rows(filename):
                identifier, name = row[id_field], row[name_field]
                if not identifier or not name.strip() or len(name) > 200:
                    raise ValueError("La fuente contiene una identidad incompleta o demasiado larga.")
                entries.add((identifier, name))
                row_count += 1
            result[kind] = [{"id": identifier, "name": name} for identifier, name in sorted(entries)]
            counts[kind] = {"source_rows": row_count, "published_ids": len({x[0] for x in entries}),
                            "name_variants": len(entries)}

    payload = json.dumps({"version": 1, "year": year, **result}, ensure_ascii=False, separators=(",", ":")).encode()
    compressed = gzip.compress(payload, mtime=0)
    manifest = {
        "version": 1, "year": year, "published_at": metadata[0]["PublishedDate"],
        "source_url": f"https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/download?type=csv&year={year}&month=0&method=all",
        "source_zip_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "catalog_sha256": hashlib.sha256(compressed).hexdigest(),
        "license": metadata[0]["License"], "counts": counts,
        "scope": "Compradores y proveedores publicados en adjudicaciones; no es un registro completo de oferentes ni del RUP.",
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / f"sercop_catalog_{year}.json.gz").write_bytes(compressed)
    (output / f"sercop_catalog_{year}.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "src/resources")
    parser.add_argument("--year", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output, args.year), ensure_ascii=False, indent=2))
