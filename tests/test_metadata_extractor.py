from src.analyzer.metadata_extractor import (
    apply_assisted_metadata,
    is_invalid_entity,
    normalize_budget,
    normalize_procedure,
    validate_metadata,
    extract_pliego_metadata,
)


def test_invalid_entity_clause_is_rejected():
    metadata = validate_metadata({
        "entidad": "será responsable de la validación de la firma electrónica del oferente",
        "objeto": "Adquisición de bienes",
        "tipo_procedimiento": "Subasta inversa electrónica",
        "presupuesto": "123.45",
        "fecha": "2026-05-01",
    })
    assert metadata["entidad"] == "No identificado automáticamente"
    assert is_invalid_entity("será responsable de la validación de la firma electrónica")


def test_plural_entity_word_in_requirement_is_not_a_metadata_heading(tmp_path):
    text = "Para recibir la oferta es indispensable una constancia; no se admitirán documentos de otras entidades."
    metadata = extract_pliego_metadata("prueba.pdf", text, tmp_path)
    assert metadata["entidad"] == "No identificado automáticamente"
    assert is_invalid_entity("es")


def test_numbered_and_multiline_entity_headings_still_work(tmp_path):
    for text in ["1. Entidad contratante: Hospital de prueba",
                 "Entidad contratante\nHospital de prueba"]:
        metadata = extract_pliego_metadata("prueba.pdf", text, tmp_path)
        assert metadata["entidad"] == "Hospital de prueba"


def test_procedure_and_budget_are_normalized():
    assert normalize_procedure("DE SUBASTA INVERSA ELECTRÓNICA DE") == "Subasta Inversa Electrónica"
    assert normalize_budget(",") == "No identificado"
    assert normalize_budget(".") == "No identificado"
    assert normalize_budget("sin valor") == "No identificado"


def test_assisted_metadata_only_applies_supported_values():
    base = validate_metadata({
        "entidad": "No identificado automáticamente",
        "objeto": "Objeto base",
        "tipo_procedimiento": "No identificado",
        "presupuesto": "No identificado",
        "fecha": "No identificado",
    })
    assisted = {
        "llm_available": True,
        "entidad_contratante": {"value": "Gobierno Autónomo Descentralizado Municipal", "confidence": "media"},
        "objeto_contratacion": {"value": "Objeto completo asistido", "confidence": "baja"},
        "tipo_procedimiento": {"value": "Subasta inversa electrónica", "confidence": "alta"},
        "presupuesto_referencial": {"value": ",", "confidence": "alta"},
        "fecha": {"value": "2026-05-01", "confidence": "media"},
        "resumen_pliego": ["Resumen breve"],
    }
    updated, summary = apply_assisted_metadata(base, assisted)
    assert updated["entidad"] == "Gobierno Autónomo Descentralizado Municipal"
    assert updated["objeto"] == "Objeto base"
    assert updated["tipo_procedimiento"] == "Subasta Inversa Electrónica"
    assert updated["presupuesto"] == "No identificado"
    assert summary == ["Resumen breve"]
