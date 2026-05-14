from src.analyzer.detector import detect_patterns
from src.analyzer.document_segmenter import segment_document
from src.analyzer.pdf_extractor import PageText


def test_segmenter_identifies_technical_specifications_profile():
    pages = [
        PageText(page_number=1, text="CONDICIONES GENERALES\nMarco normativo aplicable."),
        PageText(
            page_number=2,
            text="ESPECIFICACIONES TECNICAS\nSe solicita plataforma compatible de energia.",
        ),
    ]

    sections = segment_document(pages)

    assert any(
        section.section_label == "Especificaciones técnicas"
        and section.detection_profile == "full"
        for section in sections
    )


def test_detector_skips_form_pages_when_sections_are_provided():
    pages = [
        PageText(
            page_number=1,
            text="FORMULARIO DE LA OFERTA\nCampo marca: completar por el oferente.",
        )
    ]

    findings = detect_patterns(pages, sections=segment_document(pages))

    assert not findings


def test_detector_keeps_context_for_medical_platform_lock_in():
    pages = [
        PageText(
            page_number=1,
            text=(
                "ESPECIFICACIONES TECNICAS\n"
                "Los insumos deberán ser para utilizar con plataforma compatible de energía "
                "y generador ultrasónico instalado en la institución."
            ),
        )
    ]

    findings = detect_patterns(pages, sections=segment_document(pages))

    assert any(
        finding.pattern_id == "cn-medical-device-platform-lock-in"
        for finding in findings
    )
