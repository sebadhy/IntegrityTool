import ast
import csv
import json
from pathlib import Path

import pymupdf as fitz
import pytest

from benchmarks import documents, extractors, metrics


def pdf_bytes(label="Documento tecnico", rotation=0):
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((40, 40), label + ": requisitos y condiciones para la compra de equipos.")
        page.insert_text((40, 60), "Se admiten equivalentes. La memoria se expresa en GB y requiere revision humana.")
        for x in (40, 200, 360):
            page.draw_line((x, 100), (x, 190))
        for y in (100, 130, 160, 190):
            page.draw_line((40, y), (360, y))
        for row, values in enumerate((("Item", "Memoria"), ("Laptop", "16 GB"), ("Monitor", "8 GB"))):
            for column, value in enumerate(values):
                page.insert_text((50 + column * 160, 120 + row * 30), value)
        page.set_rotation(rotation)
        return pdf.tobytes()


@pytest.fixture
def sample(tmp_path):
    root = tmp_path / "repo"
    for folder in ("metadata", "pliegos", "especificaciones"):
        (root / "data/raw" / folder).mkdir(parents=True)
    metadata = root / "data/raw/metadata/procesos.csv"
    with metadata.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, delimiter=";", fieldnames=[
            "process_id", "entidad", "objeto", "fecha", "pliego_file", "especificaciones_file"])
        writer.writeheader()
        for number in range(2):
            process = f"TEST-{number}"
            for role, folder in (("pliego", "pliegos"), ("especificaciones", "especificaciones")):
                (root / "data/raw" / folder / f"{process}-{role}.pdf").write_bytes(pdf_bytes(process + role))
            writer.writerow({"process_id": process, "entidad": "Entidad de prueba",
                "objeto": "Equipos", "fecha": "2026-01-01", "pliego_file": f"{process}-pliego.pdf",
                "especificaciones_file": f"{process}-especificaciones.pdf"})
    manifest = documents.prepare_manifest(root, metadata, ["TEST-0"], 1, "seed")
    path = tmp_path / "manifest.json"
    # Deliberately use a different format from the report's JSON writer.
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return root, path, manifest


def test_manifest_selection_is_repeatable_and_keeps_process_pairs(sample):
    root, _, manifest = sample
    metadata = root / "data/raw/metadata/procesos.csv"
    one = documents.prepare_manifest(root, metadata, [], 1, "same-seed")
    two = documents.prepare_manifest(root, metadata, [], 1, "same-seed")
    assert one["documents"] == two["documents"]
    assert len({doc["process_id"] for doc in one["documents"]}) == 1
    assert len(manifest["documents"]) == 2
    assert all(doc["split"] == "calibration" for doc in manifest["documents"])
    assert manifest["selection"]["independent_evaluation"] is False


def test_missing_exact_document_blocks_sample(sample):
    root, _, _ = sample
    (root / "data/raw/pliegos/TEST-0-pliego.pdf").rename(root / "data/raw/pliegos/TEST-0-other.pdf")
    with pytest.raises(extractors.BenchmarkError, match="criticas"):
        documents.prepare_manifest(root, root / "data/raw/metadata/procesos.csv", ["TEST-0"], 1, "seed")


def test_changed_hash_blocks_entire_run_before_outputs(sample, tmp_path):
    root, path, manifest = sample
    (root / manifest["documents"][0]["path"]).write_bytes(pdf_bytes("Documento cambiado"))
    output = tmp_path / "run"
    with pytest.raises(extractors.BenchmarkError, match="cambio"):
        documents.run_benchmark(path, root, output, ["current"])
    assert not output.exists()


def test_process_cannot_be_split_between_calibration_and_evaluation(sample):
    root, _, manifest = sample
    manifest["documents"][1]["split"] = "evaluation"
    with pytest.raises(extractors.BenchmarkError, match="particion"):
        documents.verified_inputs(manifest, root)


def test_source_outside_declared_root_is_rejected(sample, tmp_path):
    root, _, manifest = sample
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(pdf_bytes())
    manifest["documents"][0]["path"] = str(outside)
    with pytest.raises(extractors.BenchmarkError, match="raiz"):
        documents.verified_inputs(manifest, root)


def test_structured_pymupdf_preserves_cell_association_and_geometry():
    result = extractors.extract_pymupdf_layout(pdf_bytes())
    page = result["pages"][0]
    assert page["blocks"]
    assert all(metrics.valid_bbox(block["bbox"]) for block in page["blocks"])
    table = page["tables"][0]
    assert table["rows"] == 3 and table["columns"] == 2
    assert any(cell["row"] == 1 and cell["column"] == 1 and cell["text"] == "16 GB"
               and metrics.valid_bbox(cell["bbox"]) for cell in table["cells"])


def test_rotated_page_geometry_stays_in_display_coordinate_space():
    result = extractors.extract_pymupdf_layout(pdf_bytes(rotation=90))
    assert result["pages"][0]["blocks"]
    assert all(metrics.valid_bbox(block["bbox"]) for block in result["pages"][0]["blocks"])


def test_ocr_text_is_not_claimed_as_native_geometry(monkeypatch):
    from src.analyzer.pdf_extractor import PageStatus, PageText
    monkeypatch.setattr(extractors, "extract_text_by_page", lambda _: [PageText(1, "Texto OCR", PageStatus.OCR_OK)])
    page = extractors.extract_pymupdf_layout(pdf_bytes())["pages"][0]
    assert page["text"] == "Texto OCR" and page["blocks"] == [] and page["tables"] == []


def test_default_run_is_local_and_preserves_exact_manifest(sample, tmp_path, monkeypatch):
    root, path, _ = sample
    monkeypatch.setenv("OPENAI_API_KEY", "not-for-benchmark")
    monkeypatch.setattr(extractors, "extract_azure", lambda _: pytest.fail("Unexpected cloud submission"))
    output = tmp_path / "run"
    report = documents.run_benchmark(path, root, output, ["current", "pymupdf-layout"])
    assert all(row["status"] == "completed" for row in report["records"])
    assert len(report["records"]) == 4
    assert report["llm_calls"] == 0 and report["accuracy"] is None
    assert sum(row["cloud_pages_attempted"] for row in report["records"]) == 0
    assert all(row["cost_estimate"] is None for row in report["records"])
    assert (output / "manifest.json").read_bytes() == path.read_bytes()
    annotations = documents.read_json(output / "annotations.template.json")
    assert all(row["review_status"] == "pending" and row["fields"] == [] for row in annotations["documents"])
    assert documents.evaluate_run(output, output / "annotations.template.json")["status"] == "pending_human_reference"
    with pytest.raises(FileExistsError):
        documents.run_benchmark(path, root, output, ["current"])


@pytest.mark.parametrize("allow,limit", [(False, 10), (True, 0), (True, 1)])
def test_cloud_requires_authorization_and_a_sufficient_page_budget(sample, tmp_path, allow, limit):
    root, path, _ = sample
    with pytest.raises(extractors.BenchmarkError):
        documents.run_benchmark(path, root, tmp_path / "run", ["azure-layout"],
                                allow_cloud=allow, cloud_page_limit=limit)
    assert not (tmp_path / "run").exists()


def test_llm_credentials_are_not_reused_for_document_intelligence(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "llm-secret")
    monkeypatch.delenv("INTEGRITY_BENCHMARK_AZURE_KEY", raising=False)
    monkeypatch.setenv("INTEGRITY_BENCHMARK_AZURE_ENDPOINT", "https://demo.cognitiveservices.azure.com")
    with pytest.raises(extractors.BenchmarkError):
        extractors.azure_configuration()


@pytest.mark.parametrize("endpoint", ["http://demo.cognitiveservices.azure.com", "https://evil.example",
    "https://demo.cognitiveservices.azure.com.evil.example", "https://key@demo.cognitiveservices.azure.com",
    "https://demo.cognitiveservices.azure.com/?key=secret", "https://demo.cognitiveservices.azure.com:bad"])
def test_cloud_endpoint_validation_does_not_disclose_credentials(monkeypatch, endpoint):
    monkeypatch.setenv("INTEGRITY_BENCHMARK_AZURE_KEY", "private-secret")
    monkeypatch.setenv("INTEGRITY_BENCHMARK_AZURE_ENDPOINT", endpoint)
    with pytest.raises(extractors.BenchmarkError) as exc:
        extractors.azure_configuration()
    assert "private-secret" not in str(exc.value) and endpoint not in str(exc.value)


def test_backend_failure_is_recorded_without_hiding_other_results(sample, tmp_path, monkeypatch):
    root, path, _ = sample
    def fail(_):
        raise RuntimeError("secret-key text must not be exported")
    monkeypatch.setattr(extractors, "extract_pymupdf_layout", fail)
    output = tmp_path / "run"
    report = documents.run_benchmark(path, root, output, ["current", "pymupdf-layout"])
    assert len([row for row in report["records"] if row["status"] == "failed"]) == 2
    assert len([row for row in report["records"] if row["status"] == "completed"]) == 2
    assert "secret-key" not in (output / "report.json").read_text()


def reference(doc, kind="text"):
    field = {"field_id": "memory", "page": 1, "kind": kind, "expected_text": "16 GB"}
    if kind == "table_cell":
        field.update(row_anchor="Laptop", column_header="Memoria")
    return {"document_id": doc["document_id"], "document_sha256": doc["sha256"],
            "review_status": "adjudicated", "reviewers": ["Reviewer A", "Reviewer B"],
            "adjudicated_by": "Reviewer A", "fields": [field]}


def test_reference_cannot_be_scored_until_adjudicated_by_two_reviewers(sample):
    _, path, manifest = sample
    doc = reference(manifest["documents"][0])
    annotations = {"schema_version": 1, "manifest_sha256": documents.digest(path.read_bytes()), "documents": [doc]}
    assert len(metrics.validate_annotations(annotations, manifest, annotations["manifest_sha256"])) == 1
    for reviewers in (["Reviewer A"], ["Reviewer A", "reviewer a "]):
        doc["reviewers"] = reviewers
        with pytest.raises(extractors.BenchmarkError, match="dos revisores"):
            metrics.validate_annotations(annotations, manifest, annotations["manifest_sha256"])


def test_table_recovery_requires_correct_row_and_column():
    result = extractors.extract_pymupdf_layout(pdf_bytes())
    doc = reference({"document_id": "doc-1", "sha256": "x"}, "table_cell")
    assert metrics.score_reference(result, doc)["recovered_checks"] == 1
    doc["fields"][0]["row_anchor"] = "Monitor"
    assert metrics.score_reference(result, doc)["recovered_checks"] == 0
    doc["fields"][0]["row_anchor"] = "Laptop"
    doc["fields"][0]["column_header"] = "Capacidad"
    assert metrics.score_reference(result, doc)["recovered_checks"] == 0


def test_geometry_is_not_scored_as_correct_when_unavailable():
    result = {"pages": [{"page": 1, "text": "16 GB", "blocks": [], "tables": []}]}
    doc = reference({"document_id": "doc-1", "sha256": "x"})
    doc["fields"][0]["expected_bbox"] = [0.1, 0.2, 0.4, 0.3]
    check = metrics.score_reference(result, doc)
    assert check["recovered_checks"] == 1 and check["matched_locations"] == 0


def test_text_recovery_does_not_confuse_a_number_with_a_longer_number():
    result = {"pages": [{"page": 1, "text": "Memoria: 116 GB", "blocks": [], "tables": []}]}
    doc = reference({"document_id": "doc-1", "sha256": "x"})
    assert metrics.score_reference(result, doc)["recovered_checks"] == 0
    result["pages"][0]["text"] = "Memoria: 16\nGB."
    assert metrics.score_reference(result, doc)["recovered_checks"] == 1


def test_scoring_preserves_failures_in_reference_denominator(sample, tmp_path, monkeypatch):
    root, path, manifest = sample
    monkeypatch.setattr(extractors, "extract_current", lambda _: (_ for _ in ()).throw(RuntimeError()))
    output = tmp_path / "run"
    report = documents.run_benchmark(path, root, output, ["current", "pymupdf-layout"])
    labels = tmp_path / "labels.json"
    documents.write_json(labels, {"schema_version": 1, "manifest_sha256": report["manifest_sha256"],
                                  "documents": [reference(doc) for doc in manifest["documents"]]})
    score = documents.evaluate_run(output, labels)
    assert score["backends"]["current"]["reference_checks"] == 2
    assert score["backends"]["current"]["reference_recovery_rate"] == 0
    assert score["backends"]["pymupdf-layout"]["reference_recovery_rate"] == 1
    artifact = output / report["records"][1]["artifact"]
    artifact.write_text("{}")
    with pytest.raises(extractors.BenchmarkError, match="modificado"):
        documents.evaluate_run(output, labels)


def test_azure_fixture_retains_geometry_and_cell_indexes():
    raw = {"pages": [{"pageNumber": 1, "width": 10, "height": 20,
                      "lines": [{"content": "16 GB", "polygon": [1, 2, 4, 2, 4, 3, 1, 3]}]}],
           "tables": [{"rowCount": 2, "columnCount": 2, "cells": [
               {"rowIndex": 1, "columnIndex": 1, "content": "16 GB",
                "boundingRegions": [{"pageNumber": 1, "polygon": [1, 2, 4, 2, 4, 3, 1, 3]}]}]}]}
    result = extractors.normalize_azure(raw)
    assert result["raw"] == raw
    assert result["pages"][0]["tables"][0]["cells"][0]["bbox"] == [0.1, 0.1, 0.4, 0.15]


def test_docling_fixture_does_not_attribute_multipage_cells_to_every_page():
    raw = {"pages": {"1": {"size": {"width": 100, "height": 200}},
                     "2": {"size": {"width": 100, "height": 200}}},
           "texts": [{"text": "FirstSecond", "prov": [
               {"page_no": 1, "charspan": [0, 5]}, {"page_no": 2, "charspan": [5, 11]}]}],
           "tables": [{"prov": [{"page_no": 1}, {"page_no": 2}],
                       "data": {"num_rows": 1, "num_cols": 1, "table_cells": [
                           {"start_row_offset_idx": 0, "start_col_offset_idx": 0, "text": "16 GB"}]}}]}
    result = extractors.normalize_docling(raw)
    assert result["pages"][0]["text"] == "First"
    assert result["pages"][1]["text"] == "Second"
    assert all(page["tables"] == [] for page in result["pages"])
    assert result["raw"]["tables"]


def test_application_does_not_import_benchmark_tools():
    root = Path(__file__).resolve().parents[1]
    for path in (root / "src").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                assert all(not alias.name.startswith("benchmarks") for alias in node.names), path
            elif isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("benchmarks"), path


@pytest.mark.parametrize("value", [[], {"schema_version": 1, "documents": [None]},
    {"schema_version": 1, "documents": [{"document_id": "doc-1", "sha256": []}]}])
def test_malformed_manifest_returns_a_clear_error(sample, value):
    root, _, _ = sample
    with pytest.raises(extractors.BenchmarkError):
        documents.verified_inputs(value, root)


@pytest.mark.parametrize("malformed", [None, {}, [None]])
def test_malformed_annotations_return_a_clear_error(sample, malformed):
    _, path, manifest = sample
    with pytest.raises(extractors.BenchmarkError):
        metrics.validate_annotations({"schema_version": 1,
            "manifest_sha256": documents.digest(path.read_bytes()), "documents": malformed},
            manifest, documents.digest(path.read_bytes()))


@pytest.mark.parametrize("content", [b"", b"not a PDF"])
def test_empty_or_invalid_pdf_is_rejected(content):
    with pytest.raises(extractors.BenchmarkError):
        documents.inspect_pdf(content)


def test_missing_optional_docling_dependency_blocks_before_output(sample, tmp_path, monkeypatch):
    root, path, _ = sample
    monkeypatch.setattr(documents, "_dependency", lambda _: False)
    with pytest.raises(extractors.BenchmarkError, match="requirements-docling"):
        documents.run_benchmark(path, root, tmp_path / "run", ["docling"])
    assert not (tmp_path / "run").exists()


def test_partial_extraction_is_not_reported_as_complete(sample, tmp_path, monkeypatch):
    root, path, _ = sample
    monkeypatch.setattr(extractors, "extract_current", lambda _: {"pages": []})
    report = documents.run_benchmark(path, root, tmp_path / "run", ["current"])
    assert all(record["status"] == "partial" and record["error"] for record in report["records"])


def test_report_rejects_removed_records_instead_of_inflating_recovery(sample, tmp_path):
    root, path, _ = sample
    output = tmp_path / "run"
    documents.run_benchmark(path, root, output, ["current"])
    report = documents.read_json(output / "report.json")
    report["records"].pop()
    (output / "report.json").write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(extractors.BenchmarkError, match="faltantes"):
        documents.evaluate_run(output, output / "annotations.template.json")


def test_report_escapes_markup_and_spreadsheet_formulas(sample, tmp_path):
    root, path, _ = sample
    output = tmp_path / "original"
    report = documents.run_benchmark(path, root, output, ["current"])
    report["records"][0]["process_id"] = '=HYPERLINK("https://example.invalid")'
    report["records"][0]["error"] = '<script>alert("example")</script>'
    exported = tmp_path / "exported"
    exported.mkdir()
    documents.write_reports(exported, report)
    assert "<script>" not in (exported / "report.html").read_text(encoding="utf-8")
    with (exported / "metrics.csv").open(encoding="utf-8-sig", newline="") as stream:
        assert next(csv.DictReader(stream))["process_id"].startswith("'=")
