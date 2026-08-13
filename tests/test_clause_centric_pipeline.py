from pathlib import Path

from src.analyzer.boilerplate_filter import active_clauses, classify_clause, classify_clauses
from src.analyzer.clause_extractor import extract_clauses
from src.analyzer.consolidator import consolidate_candidates
from src.analyzer.contextualizer import build_finding_candidates
from src.analyzer.detector import detect_signals
from src.analyzer.document_segmenter import segment_document
from src.analyzer.domain_models import Clause, ConsolidatedFinding
from src.analyzer.pdf_extractor import PageText
from src.analyzer.prioritizer import prioritize_consolidated_findings
from src.analyzer.relevance_filter import filter_relevant_findings
from src.analyzer.review_item_builder import build_review_items, review_items_to_dataframe

PROHIBITED = [
    "corrupción",
    "fraude",
    "ilegal",
    "direccionamiento detectado",
    "colusión",
    "culpable",
    "responsabilidad",
    "irregularidad comprobada",
]


def _run_text_pipeline(texts, corpus_context=None):
    pages = [PageText(page_number=index, text=text) for index, text in enumerate(texts, start=1)]
    sections = segment_document(pages)
    clauses = classify_clauses(extract_clauses(pages, sections, "doc-test"))
    signals = detect_signals(active_clauses(clauses))
    candidates = build_finding_candidates(signals, clauses, corpus_context or {})
    consolidated = consolidate_candidates(candidates, clauses, "doc-test")
    relevant = filter_relevant_findings(consolidated)
    prioritized = prioritize_consolidated_findings(relevant)
    items = build_review_items(prioritized)
    return clauses, signals, candidates, consolidated, items


def test_boilerplate_filter_excludes_empty_placeholders_from_review_items():
    clause = Clause(
        clause_id="c1",
        document_id="d1",
        page=1,
        section_title="Formulario",
        section_type="forms",
        text="No requerido por la entidad",
        normalized_text="no requerido por la entidad",
    )
    classified = classify_clause(clause)
    assert classified.clause_status == "placeholder"
    assert classified.exclude_from_detection is True

    clauses, signals, _, _, items = _run_text_pipeline(["Sin datos", "No requerido por la entidad"])
    assert all(clause.exclude_from_detection for clause in clauses)
    assert signals == []
    assert items == []


def test_deduplicates_same_certification_across_pages_into_one_review_item():
    texts = [
        "ESPECIFICACIONES TÉCNICAS. Se requiere certificación ISO 9001 para el bien ofertado.",
        "ESPECIFICACIONES TÉCNICAS. Se requiere certificación ISO 9001 para el bien ofertado.",
        "ESPECIFICACIONES TÉCNICAS. Se requiere certificación ISO 9001 para el bien ofertado.",
    ]
    _, signals, _, consolidated, items = _run_text_pipeline(texts)
    cert_signals = [signal for signal in signals if signal.pattern_id == "cn-specific-certification"]
    cert_findings = [finding for finding in consolidated if finding.pattern_id == "cn-specific-certification"]
    cert_items = [item for item in items if item.metadata.get("pattern_id") == "cn-specific-certification"]
    assert len(cert_signals) == 3
    assert len(cert_findings) == 1
    assert cert_findings[0].duplicate_count == 3
    assert len(cert_items) == 1
    assert len(cert_items[0].evidence_items) == 3


def test_brand_with_equivalent_is_not_visible_when_mitigated():
    _, signals, candidates, consolidated, items = _run_text_pipeline([
        "ESPECIFICACIONES TÉCNICAS. Se solicita marca específica ACME o equivalente funcional verificable."
    ])
    assert signals
    assert any(candidate.detected_mitigants for candidate in candidates)
    assert consolidated
    assert items == []


def test_mandatory_low_frequency_without_mitigant_gets_medium_or_high_priority():
    corpus_context = {
        "Requisito de autorización comercial o técnica": {
            "frequency_label": "1 de 24 procesos",
            "rarity": "Poco frecuente",
            "comparative_comment": "Requisito poco frecuente en el corpus disponible.",
            "frequency": 0.04,
        }
    }
    _, _, _, _, items = _run_text_pipeline(
        ["ESPECIFICACIONES TÉCNICAS. Debe ser distribuidor autorizado exclusivo del fabricante X."],
        corpus_context=corpus_context,
    )
    assert items
    assert items[0].review_priority in {"alta", "media"}
    assert "score" not in review_items_to_dataframe(items, "doc.pdf").to_string().lower()


def test_visible_review_item_output_avoids_prohibited_language():
    _, _, _, _, items = _run_text_pipeline([
        "ESPECIFICACIONES TÉCNICAS. Debe ser distribuidor autorizado exclusivo del fabricante X."
    ])
    text = review_items_to_dataframe(items, "doc.pdf").to_string().lower()
    for word in PROHIBITED:
        assert word not in text


def test_regression_same_input_same_visible_output():
    texts = ["ESPECIFICACIONES TÉCNICAS. Debe ser distribuidor autorizado exclusivo del fabricante X."]
    first = review_items_to_dataframe(_run_text_pipeline(texts)[4], "doc.pdf").to_dict("records")
    second = review_items_to_dataframe(_run_text_pipeline(texts)[4], "doc.pdf").to_dict("records")
    assert first == second




def test_same_medical_platform_pattern_across_pages_is_one_visible_review_item():
    texts = [
        "ESPECIFICACIONES TÉCNICAS. El insumo debe ser compatible con el generador ultrasónico instalado.",
        "FICHA TÉCNICA. Consumible para utilizar con plataforma compatible de energía existente en el hospital.",
    ]
    _, signals, _, consolidated, items = _run_text_pipeline(texts)
    platform_signals = [signal for signal in signals if signal.pattern_id == "cn-medical-device-platform-lock-in"]
    platform_findings = [finding for finding in consolidated if finding.pattern_id == "cn-medical-device-platform-lock-in"]
    platform_items = [item for item in items if item.metadata.get("pattern_id") == "cn-medical-device-platform-lock-in"]

    assert len(platform_signals) == 2
    assert len(platform_findings) == 1
    assert len(platform_items) == 1

    item = platform_items[0]
    assert item.metadata["duplicate_count"] == 2
    assert len(item.evidence_items) == 2

    df = review_items_to_dataframe(platform_items, "doc.pdf")
    assert len(df) == 1
    assert df.iloc[0]["related_pages"] == [1, 2]
    assert df.iloc[0]["occurrence_count"] == 2
    assert df.iloc[0]["patrón detectado"] == "Compatibilidad con plataforma médica instalada"


def test_representative_excerpt_prefers_direct_requirement_over_structural_text():
    finding = ConsolidatedFinding(
        finding_id="finding-platform",
        family="dependencia técnica potencial",
        competition_dimension="interoperability_lock_in",
        normalized_issue="compatibilidad plataforma médica",
        signals=[],
        clauses=[],
        evidence_items=[
            {
                "page": 1,
                "section": "Índice",
                "pattern_id": "cn-medical-device-platform-lock-in",
                "pattern_name": "Compatibilidad con plataforma médica instalada",
                "matched_text": "compatible con el generador",
                "text": "Índice de compatibilidad: compatible con el generador ultrasónico.",
            },
            {
                "page": 2,
                "section": "Especificaciones técnicas",
                "pattern_id": "cn-medical-device-platform-lock-in",
                "pattern_name": "Compatibilidad con plataforma médica instalada",
                "matched_text": "compatible con el generador",
                "text": "El consumible debe ser compatible con el generador ultrasónico instalado en la unidad médica.",
            },
        ],
        detected_mitigants=[],
        historical_context={},
        consolidation_key="doc|platform|interoperability",
        duplicate_count=2,
        internal_ranking_score=3,
        ranking_factors=["Múltiples señales relacionadas consolidadas."],
        pattern_id="cn-medical-device-platform-lock-in",
        title="Compatibilidad con plataforma médica instalada",
        missing_mitigants=["No se identificó mitigante textual cercano."],
        candidate_rationale="Convendría revisar compatibilidad y alternativas equivalentes.",
    )
    df = review_items_to_dataframe(build_review_items([finding]), "doc.pdf")
    representative = df.iloc[0]["representative_excerpt"]
    assert "debe ser compatible" in representative.lower()
    assert "índice" not in representative.lower()
    assert df.iloc[0]["additional_excerpts"]

def test_review_item_dataframe_contains_legacy_summary_columns():
    _, _, _, _, items = _run_text_pipeline([
        "ESPECIFICACIONES TÉCNICAS. Debe ser distribuidor autorizado exclusivo del fabricante X."
    ])
    df = review_items_to_dataframe(items, "doc.pdf")
    assert "combinación relevante" in df.columns
    assert "atención sugerida" in df.columns
    assert "clasificación histórica" in df.columns

def test_streamlit_app_does_not_import_internal_detection_pipeline_modules():
    app_source = Path("app.py").read_text(encoding="utf-8")
    forbidden = [
        "src.analyzer.detector",
        "src.analyzer.mitigants",
        "src.analyzer.consolidator",
        "src.analyzer.relevance_filter",
        "src.analyzer.prioritizer",
        "src.analyzer.observation_filter",
    ]
    for import_path in forbidden:
        assert import_path not in app_source


def test_pipeline_does_not_create_review_item_from_index_only_timeline_reference():
    texts = ["Índice\n1. Convocatoria 3\n2. Cronograma del procedimiento 4\n3. Presentación de ofertas 5"]
    _, signals, _, _, items = _run_text_pipeline(texts)
    assert signals == []
    assert items == []


def test_standard_pharmaceutical_catalogue_description_is_not_commercial_presentation_signal():
    texts = [
        "ESPECIFICACIONES TÉCNICAS. 2.1 Lenalidomida, Sólido oral, 10 mg, Caja x blíster/ristra 23450 u."
    ]
    _, signals, _, _, items = _run_text_pipeline(texts)
    assert not any(signal.pattern_id == "cn-pharma-commercial-presentation-specificity" for signal in signals)
    assert not any(item.metadata.get("pattern_id") == "cn-pharma-commercial-presentation-specificity" for item in items)


def test_exact_pharmaceutical_dose_and_volume_can_trigger_commercial_presentation_signal():
    texts = [
        "ESPECIFICACIONES TÉCNICAS. Rituximab líquido parenteral 1400mg / 11,7ml sin equivalentes terapéuticos visibles."
    ]
    _, signals, _, _, items = _run_text_pipeline(texts)
    assert any(signal.pattern_id == "cn-pharma-commercial-presentation-specificity" for signal in signals)
    assert any(item.metadata.get("pattern_id") == "cn-pharma-commercial-presentation-specificity" for item in items)
