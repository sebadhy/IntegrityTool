from src.analyzer.detector import detect_patterns
from src.analyzer.pdf_extractor import PageText


def _findings(text):
    return detect_patterns([PageText(page_number=1, text=text)])


def _by_pattern(findings, pattern_id):
    return [finding for finding in findings if finding.pattern_id == pattern_id]


def test_brand_without_equivalence_has_missing_equivalence():
    findings = _findings(
        "Las especificaciones técnicas exigen distribuidor exclusivo del fabricante para todos los equipos."
    )
    brand = _by_pattern(findings, "cn-brand-model-provider-reference")
    assert brand
    assert any("equivalencia" in item.lower() for item in brand[0].missing_information)


def test_brand_with_equivalence_registers_mitigant():
    findings = _findings(
        "Se solicita representante autorizado del fabricante o equivalente funcional, con parámetros verificables."
    )
    brand = _by_pattern(findings, "cn-brand-model-provider-reference")
    assert brand
    assert brand[0].mitigating_factors
    assert brand[0].review_priority in {"general", "suggested"}


def test_specific_experience_detected():
    findings = _findings("El oferente deberá acreditar experiencia específica en contratos idénticos al mismo objeto.")
    assert _by_pattern(findings, "cn-specific-experience")


def test_financial_requirement_detected():
    findings = _findings("Se requiere patrimonio mínimo y liquidez según índice financiero definido por la entidad.")
    assert _by_pattern(findings, "cn-financial-restrictive")


def test_local_presence_with_and_without_justification():
    without = _by_pattern(_findings("El proveedor deberá contar con oficina local antes de la adjudicación."), "cn-local-presence-requirement")
    with_justification = _by_pattern(_findings("Se requiere presencia local por continuidad operativa y atención de soporte."), "cn-local-presence-requirement")
    assert without
    assert any("justificación" in item.lower() for item in without[0].missing_information)
    assert with_justification
    assert with_justification[0].possible_legitimate_justifications


def test_subjective_criteria_detected():
    findings = _findings("La entidad evaluará la idoneidad a criterio de la entidad y a satisfacción del área técnica.")
    assert _by_pattern(findings, "cn-subjective-evaluation-criteria")


def test_interoperability_justification_context():
    findings = _findings("La solución debe ser compatible con infraestructura existente por razones de interoperabilidad.")
    interoperability = _by_pattern(findings, "cn-interoperability-lock-in")
    assert interoperability
    assert interoperability[0].possible_legitimate_justifications
