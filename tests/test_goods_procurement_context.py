from src.analyzer.detector import detect_patterns
from src.analyzer.pdf_extractor import PageText

PROHIBITED = [
    "corrupción",
    "fraude",
    "direccionamiento",
    "irregularidad",
    "red flag",
    "alto riesgo",
    "hallazgo crítico",
]


def _findings(text):
    return detect_patterns([PageText(page_number=1, text=text)])


def _by_pattern(findings, pattern_id):
    return [finding for finding in findings if finding.pattern_id == pattern_id]


def _main_output_text(findings):
    fields = []
    for finding in findings:
        data = finding.to_dict()
        for key in [
            "patrón detectado",
            "observación prudente",
            "posible efecto sobre concurrencia",
            "validación sugerida",
            "prioridad de revisión",
            "why_not_automatically_restrictive",
        ]:
            fields.append(str(data.get(key, "")))
    return " ".join(fields).lower()


def test_authorized_distributor_certificate_is_textual_general_signal():
    findings = _findings("Certificado de distribuidor autorizado otorgado por el fabricante para el bien ofertado.")
    authorization = _by_pattern(findings, "cn-brand-model-provider-reference")
    assert authorization
    finding = authorization[0]
    assert finding.pattern_name == "Requisito de autorización comercial o técnica"
    assert finding.review_priority == "general"
    assert finding.analytical_signal_type == "textual_signal"
    assert finding.is_common_in_goods_procurement is True
    assert finding.possible_legitimate_justifications
    assert "habitual" in finding.rationale.lower()


def test_bpm_or_equivalent_registers_mitigant_and_general_priority():
    findings = _findings("Certificado BPM o su equivalente para garantizar calidad del bien.")
    certification = _by_pattern(findings, "cn-specific-certification")
    assert certification
    finding = certification[0]
    assert finding.review_priority == "general"
    assert any("equivalente" in item.lower() for item in finding.mitigating_factors)
    assert any("calidad" in item.lower() for item in finding.mitigating_factors + finding.possible_legitimate_justifications)


def test_exclusive_authorized_distributor_escalates_priority():
    findings = _findings("Debe ser distribuidor autorizado exclusivo del fabricante X.")
    authorization = _by_pattern(findings, "cn-brand-model-provider-reference")
    assert authorization
    finding = authorization[0]
    assert finding.review_priority == "priority"
    assert finding.analytical_signal_type == "contextual_review_signal"
    assert finding.escalation_factors


def test_single_brand_without_equivalents_is_priority_closed_specification():
    findings = _findings("Solo se aceptará marca X, sin equivalentes.")
    equivalence = _by_pattern(findings, "cn-weak-equivalence-clause")
    assert equivalence
    finding = equivalence[0]
    assert finding.review_priority == "priority"
    assert finding.escalation_factors
    assert "equivalente" in finding.rationale.lower() or "concurrencia" in finding.rationale.lower()


def test_manufacturer_or_authorized_distributor_warranty_is_general_for_goods():
    findings = _findings("Garantía del fabricante o distribuidor autorizado para los equipos ofertados.")
    authorization = _by_pattern(findings, "cn-brand-model-provider-reference")
    assert authorization
    finding = authorization[0]
    assert finding.review_priority == "general"
    assert finding.is_common_in_goods_procurement is True
    assert finding.escalation_factors == []


def test_goods_procurement_outputs_avoid_prohibited_language():
    findings = _findings("Certificado BPM o su equivalente para garantizar calidad del bien.")
    text = _main_output_text(findings)
    for word in PROHIBITED:
        assert word not in text
