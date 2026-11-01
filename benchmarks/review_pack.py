"""Blind reference material: original pages, never extractor answers or gold labels."""
from __future__ import annotations

import html
from pathlib import Path

import pymupdf as fitz

from .documents import digest, load_run, read_artifact, verified_inputs, write_json
from .extractors import BenchmarkError


def select_pages(document: dict, results: list[dict], limit: int) -> list[tuple[int, str]]:
    pending, tables = set(), {}
    for result in results:
        for page in result["pages"]:
            number = page["page"]
            if not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= document["page_count"]:
                raise BenchmarkError("Una pagina de extraccion esta fuera del documento original.")
            if page["status"] in {"requires_ocr", "ocr_failed"}:
                pending.add(number)
            tables[number] = max(tables.get(number, 0), sum(len(t["cells"]) for t in page["tables"]))
    selected = [(number, "pagina_con_lectura_pendiente") for number in sorted(pending)[:limit]]
    if len(selected) < limit and any(tables.values()):
        number = min(tables, key=lambda number: (-tables[number], number))
        if number not in {page for page, _ in selected}:
            selected.append((number, "pagina_con_estructura_tabular_candidata"))
    remaining = sorted(range(1, document["page_count"] + 1),
        key=lambda number: digest(f'{document["sha256"]}|{number}'.encode()))
    for number in remaining:
        if len(selected) >= limit:
            break
        if number not in {page for page, _ in selected}:
            selected.append((number, "seleccion_deterministica_complementaria"))
    return selected


def build_review_pack(run: Path, root: Path, output: Path, pages_per_document: int = 2) -> dict:
    if not 1 <= pages_per_document <= 4:
        raise BenchmarkError("Seleccione entre una y cuatro paginas por documento.")
    report, manifest = load_run(run)
    inputs = verified_inputs(manifest, root)
    # Validate all retained artifacts before creating the reviewer material.
    results = {}
    for record in report["records"]:
        results.setdefault(record["document_id"], []).append(read_artifact(run, record))
    selected = {doc["document_id"]: select_pages(doc, results[doc["document_id"]], pages_per_document)
                for doc, _, _ in inputs}
    output.mkdir(parents=True, exist_ok=False)
    selection = {"schema_version": 1, "manifest_sha256": report["manifest_sha256"],
                 "source_report_sha256": digest((run / "report.json").read_bytes()),
                 "selection_method": "targeted_diagnostic_with_deterministic_complement",
                 "independent_evaluation": False, "answers_prefilled": False,
                 "status": "pending_human_reference", "pages": []}
    sections, navigation = [], []
    for doc, _, content in inputs:
        identity = doc["document_id"]
        original = f"originals/{identity}.pdf"
        (output / "originals").mkdir(exist_ok=True)
        with (output / original).open("xb") as stream:
            stream.write(content)
        title = html.escape(f'{doc["process_id"]} - {doc["role"]}')
        navigation.append(f'<li><a href="#{identity}">{title}</a></li>')
        sections.append(f'<section id="{identity}"><h2>{title}</h2>'
                        f'<p><a href="{original}">Abrir documento original</a></p>')
        with fitz.open(stream=content, filetype="pdf") as pdf:
            for number, reason in selected[identity]:
                relative = f"pages/{identity}-p{number}.png"
                (output / "pages").mkdir(exist_ok=True)
                page = pdf[number - 1]
                scale = min(2, (4_000_000 / max(1, page.rect.get_area())) ** 0.5)
                page.get_pixmap(matrix=fitz.Matrix(scale, scale)).save(output / relative)
                selection["pages"].append({"document_id": identity, "document_sha256": doc["sha256"],
                    "page": number, "selection_reason": reason, "image": relative,
                    "image_sha256": digest((output / relative).read_bytes()), "original": original})
                sections.append(f'<figure><figcaption>Página {number} de {doc["page_count"]}</figcaption>'
                    f'<a href="{relative}" title="Abrir página a tamaño completo">'
                    f'<img src="{relative}" alt="Página {number} del documento original" loading="lazy"></a></figure>')
        sections.append('</section>')
    template = {"schema_version": 1, "manifest_sha256": report["manifest_sha256"], "documents": [
        {"document_id": doc["document_id"], "document_sha256": doc["sha256"], "review_status": "pending",
         "reviewers": [], "adjudicated_by": "", "fields": []} for doc, _, _ in inputs]}
    for name in ("reviewer-01.json", "reviewer-02.json", "adjudication.template.json"):
        write_json(output / name, template)
    write_json(output / "selection.json", selection)
    index = '''<!doctype html><html lang="es"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cuaderno de validación documental</title>
<style>body{font:16px/1.55 system-ui;margin:0;color:#24332e;background:#f2f5f4}
main{max-width:960px;margin:auto;padding:28px 20px}h1{font-size:26px}h2{font-size:20px}
a{color:#176650}section{margin-top:48px}figure{margin:24px 0}figcaption{margin-bottom:8px}
nav ul{columns:2;column-gap:32px}nav li{break-inside:avoid}
img{display:block;width:100%;height:auto;background:white}li{margin:6px 0}
@media(max-width:600px){nav ul{columns:1}}
@media print{nav{display:none}section{break-before:page}body{background:white}}</style>
<main><h1>Cuaderno de validación documental</h1>
<p>Revise los originales y registre referencias verificables de forma independiente.
Las páginas se seleccionaron para diagnosticar extracción; no representan todo el expediente ni una muestra aleatoria.</p>
<ol><li>Cada revisor utiliza su archivo <code>reviewer-01.json</code> o <code>reviewer-02.json</code>.
Registre fragmento literal, página y, para celdas, referencia de fila y encabezado.</li>
<li>Compare las anotaciones después de ambas revisiones. Resuelva diferencias y complete
<code>adjudication.template.json</code> con dos revisores y quien resolvió la referencia.</li>
<li>Solo las referencias resueltas se marcan <code>adjudicated</code>. No copie respuestas de un extractor como referencia correcta.</li></ol>
<p><a href="reviewer-01.json" download>Plantilla del revisor 1</a> ·
<a href="reviewer-02.json" download>Plantilla del revisor 2</a> ·
<a href="adjudication.template.json" download>Plantilla de referencias resueltas</a></p>
<nav><h2>Documentos</h2><ul>''' + ''.join(navigation) + '</ul></nav>' + ''.join(sections) + '</main></html>'
    (output / "index.html").write_text(index, encoding="utf-8")
    return selection
