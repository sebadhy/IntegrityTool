"""Tests for structural document segmentation (Phase 5)."""
from __future__ import annotations

from src.analyzer.document_segmenter import segment_document
from src.analyzer.pdf_extractor import PageText


def _pages(*texts: str) -> list[PageText]:
    return [PageText(page_number=i + 1, text=text) for i, text in enumerate(texts)]


def test_segment_pliego_con_secciones_estandar():
    pages = _pages(
        "OBJETO DE LA CONTRATACIÓN\nAdquisición de equipos informáticos para el MINEDUC.",
        "REQUISITOS DE HABILITACIÓN\nEl oferente deberá acreditar experiencia mínima de 3 años.",
        "ESPECIFICACIONES TÉCNICAS\nEquipo marca ACME modelo X100 o equivalente funcional.",
    )
    sections = segment_document(pages)
    section_ids = [s.section_id for s in sections]
    assert "objeto_contratacion" in section_ids
    assert "requisitos_habilitacion" in section_ids
    assert "especificaciones_tecnicas" in section_ids


def test_segment_sin_estructura_devuelve_fallback():
    pages = _pages("Texto sin títulos ni estructura formal. Contenido genérico.")
    sections = segment_document(pages)
    assert len(sections) == 1
    assert sections[0].section_id == "desconocido"
    assert sections[0].detection_profile == "full"


def test_formulario_tiene_perfil_skip():
    pages = _pages(
        "ESPECIFICACIONES TÉCNICAS\nRequisitos del equipo.",
        "FORMULARIOS DE LA OFERTA\nDeclaración juramentada del oferente.",
    )
    sections = segment_document(pages)
    form_sections = [s for s in sections if s.section_id == "formularios"]
    assert form_sections, "Formularios section not detected"
    assert form_sections[0].detection_profile == "skip"


def test_especificaciones_tiene_context_multiplier_mayor():
    pages = _pages(
        "ESPECIFICACIONES TÉCNICAS\nCaracterísticas del equipo requerido.",
    )
    sections = segment_document(pages)
    spec_sections = [s for s in sections if s.section_id == "especificaciones_tecnicas"]
    assert spec_sections
    assert spec_sections[0].context_multiplier > 1.0


def test_pages_vacio_devuelve_lista_vacia():
    assert segment_document([]) == []


def test_seccion_tiene_texto_de_paginas():
    pages = _pages(
        "REQUISITOS DE HABILITACIÓN\nAcreditar experiencia.",
        "Continuación de los requisitos de habilitación.",
    )
    sections = segment_document(pages)
    hab = next((s for s in sections if s.section_id == "requisitos_habilitacion"), None)
    assert hab is not None
    assert "Acreditar experiencia" in hab.text
    assert "Continuación" in hab.text


def test_seccion_start_end_page():
    pages = _pages(
        "OBJETO DE LA CONTRATACIÓN\nTexto de objeto.",
        "ESPECIFICACIONES TÉCNICAS\nTexto de specs.",
        "Más especificaciones técnicas.",
    )
    sections = segment_document(pages)
    spec = next((s for s in sections if s.section_id == "especificaciones_tecnicas"), None)
    assert spec is not None
    assert spec.start_page == 2
    assert spec.end_page == 3


def test_paginas_sin_seccion_al_inicio_van_a_desconocido():
    pages = _pages(
        "Portada y carátula del proceso SIE-2024-001.",
        "ESPECIFICACIONES TÉCNICAS\nRequisito A: equipo certificado.",
    )
    sections = segment_document(pages)
    section_ids = [s.section_id for s in sections]
    assert "desconocido" in section_ids
    assert "especificaciones_tecnicas" in section_ids


def test_detect_patterns_respeta_skip():
    """Formularios pages produce no detections when detect_patterns uses sections."""
    from src.analyzer.detector import detect_patterns

    pages = _pages(
        "FORMULARIOS DE LA OFERTA\nDistribuidor autorizado marca ACME. Formulario 1.",
    )
    detections = detect_patterns(pages)
    assert len(detections) == 0, (
        "Expected no detections on skip-profile page, got: "
        + str([d.title for d in detections])
    )


def test_detect_patterns_restricted_omite_mitigantes():
    """Restricted sections skip SIGNAL_MITIGANT rules (o equivalente, etc.)."""
    from src.analyzer.detector import detect_patterns

    pages = _pages(
        "OBJETO DE LA CONTRATACIÓN\nSe aceptan equivalentes y productos o equivalente.",
    )
    detections = detect_patterns(pages)
    mitigant_detections = [d for d in detections if d.signal_type == "mitigante_concurrencia"]
    assert len(mitigant_detections) == 0, (
        "Restricted section should not produce mitigant detections"
    )


def test_detect_patterns_full_detecta_senales():
    """Full sections detect signals normally."""
    from src.analyzer.detector import detect_patterns

    pages = _pages(
        "ESPECIFICACIONES TÉCNICAS\nDistribuidor autorizado marca ACME modelo X100.",
    )
    detections = detect_patterns(pages)
    assert len(detections) > 0


def test_finding_tiene_section_id():
    """Findings from sectioned pages carry section_id and section_label."""
    from src.analyzer.detector import detect_patterns

    pages = _pages(
        "ESPECIFICACIONES TÉCNICAS\nDistribuidor autorizado marca ACME modelo X100.",
    )
    detections = detect_patterns(pages)
    assert detections, "Expected at least one detection"
    for det in detections:
        row = det.to_dict()
        assert "section_id" in row
        assert "section_label" in row
        assert row["section_id"] == "especificaciones_tecnicas"
