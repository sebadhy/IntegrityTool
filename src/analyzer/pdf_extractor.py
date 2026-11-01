"""
pdf_extractor.py — Extracción de texto de PDFs con soporte OCR.

Flujo:
1. Intenta extraer texto con PyMuPDF (rápido, sin dependencias extra)
2. Si una página tiene poco texto e imágenes por leer, intenta OCR con Tesseract
3. Si Tesseract no está instalado, marca la página como requires_ocr

Los logotipos pequeños repetidos en márgenes no convierten por sí solos
una página con texto seleccionable en una página escaneada.
"""

from __future__ import annotations

import logging
import math
import shutil
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum

import pymupdf as fitz

LOGGER = logging.getLogger(__name__)

# Umbral para revisar posibles imágenes de contenido; texto breve no implica escaneo.
MIN_TEXT_CHARS = 100


class PageStatus(str, Enum):
    OK          = "ok"           # texto extraído correctamente
    OCR_OK      = "ocr_ok"       # texto obtenido via Tesseract
    OCR_FAILED  = "ocr_failed"   # Tesseract intentó pero falló
    REQUIRES_OCR = "requires_ocr" # Tesseract no instalado, página pendiente
    EMPTY       = "empty"        # página genuinamente vacía (portada, separador)


@dataclass(frozen=True)
class PageText:
    page_number: int
    text: str
    status: PageStatus = PageStatus.OK
    # Campos adicionales para trazabilidad
    char_count: int = 0
    ocr_attempted: bool = False
    extraction_note: str = ""

    def __post_init__(self) -> None:
        # frozen=True no permite setattr, usamos object.__setattr__
        object.__setattr__(self, "char_count", len(self.text))

    @property
    def has_text(self) -> bool:
        return bool(self.text.strip())

    @property
    def needs_ocr(self) -> bool:
        return self.status == PageStatus.REQUIRES_OCR


@dataclass
class ExtractionResult:
    """Resultado completo de extracción de un PDF."""
    pages: list[PageText]
    total_pages: int
    pages_with_text: int
    pages_requiring_ocr: int
    pages_ocr_ok: int
    tesseract_available: bool
    has_any_text: bool

    @classmethod
    def from_pages(cls, pages: list[PageText], tesseract_available: bool) -> "ExtractionResult":
        return cls(
            pages=pages,
            total_pages=len(pages),
            pages_with_text=sum(1 for p in pages if p.status in {PageStatus.OK, PageStatus.OCR_OK}),
            pages_requiring_ocr=sum(1 for p in pages if p.status == PageStatus.REQUIRES_OCR),
            pages_ocr_ok=sum(1 for p in pages if p.status == PageStatus.OCR_OK),
            tesseract_available=tesseract_available,
            has_any_text=any(p.has_text for p in pages),
        )

    def summary(self) -> dict:
        return {
            "total_pages":          self.total_pages,
            "pages_with_text":      self.pages_with_text,
            "pages_requiring_ocr":  self.pages_requiring_ocr,
            "pages_ocr_ok":         self.pages_ocr_ok,
            "tesseract_available":  self.tesseract_available,
            "has_any_text":         self.has_any_text,
            "ocr_pending":          self.pages_requiring_ocr > 0,
        }


# ---------------------------------------------------------------------------
# API pública principal
# ---------------------------------------------------------------------------

def extract_text_by_page(pdf_bytes: bytes) -> list[PageText]:
    """
    API compatible con el extractor original.
    Retorna lista de PageText, ahora con status y soporte OCR.
    """
    result = extract_pdf(pdf_bytes)
    return result.pages


def extract_pdf(pdf_bytes: bytes) -> ExtractionResult:
    """
    Extracción completa con metadata de resultado.
    Usar esta función cuando necesites saber si hubo páginas escaneadas.
    """
    tesseract_ok = _tesseract_available()
    pages: list[PageText] = []

    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        decorative_images = _recurring_margin_images(document)
        for page_index, page in enumerate(document, start=1):
            page_text = _extract_page(page, page_index, tesseract_ok, decorative_images)
            pages.append(page_text)

    result = ExtractionResult.from_pages(pages, tesseract_ok)

    # Log resumen si hay páginas problemáticas
    if result.pages_requiring_ocr > 0:
        LOGGER.warning(
            "PDF tiene %d página(s) escaneadas sin OCR disponible. "
            "Instala Tesseract para procesarlas automáticamente.",
            result.pages_requiring_ocr,
        )
    elif result.pages_ocr_ok > 0:
        LOGGER.info(
            "OCR aplicado en %d página(s).",
            result.pages_ocr_ok,
        )

    return result


# ---------------------------------------------------------------------------
# Lógica por página
# ---------------------------------------------------------------------------

def _extract_page(page: fitz.Page, page_number: int, tesseract_ok: bool,
                  decorative_images: set | None = None) -> PageText:
    """Extrae texto de una página, con fallback a OCR si es necesario."""

    # Intento 1: extracción directa con PyMuPDF
    raw_text = page.get_text("text").strip()

    if len(raw_text) >= MIN_TEXT_CHARS:
        return PageText(
            page_number=page_number,
            text=raw_text,
            status=PageStatus.OK,
            extraction_note="Texto seleccionable extraído directamente del PDF.",
        )

    # Página con poco texto — puede ser escaneada o genuinamente vacía
    # Verificar si hay contenido visual (imágenes) que sugiera que es escaneada
    is_likely_scanned = _page_has_images(page, decorative_images if raw_text else None)

    if not is_likely_scanned:
        return PageText(
            page_number=page_number,
            text=raw_text,
            status=PageStatus.OK if raw_text else PageStatus.EMPTY,
            extraction_note=("Texto breve conservado; sin imágenes pendientes salvo elementos repetidos en márgenes."
                             if raw_text else "No se detectó texto ni imagen de contenido en la página."),
        )

    # Es escaneada — intentar OCR
    if not tesseract_ok:
        LOGGER.debug("Página %d escaneada, Tesseract no disponible.", page_number)
        return PageText(
            page_number=page_number,
            text=raw_text,  # lo poco que haya
            status=PageStatus.REQUIRES_OCR,
            ocr_attempted=False,
            extraction_note="La página contiene imágenes por leer y no hay OCR disponible.",
        )

    # Intentar OCR con Tesseract
    ocr_text = _ocr_page(page, page_number)
    if ocr_text and len(ocr_text) >= MIN_TEXT_CHARS:
        return PageText(
            page_number=page_number,
            text=ocr_text,
            status=PageStatus.OCR_OK,
            ocr_attempted=True,
            extraction_note="Texto recuperado mediante OCR; requiere comprobación contra el original.",
        )

    # OCR intentado pero sin resultado útil
    LOGGER.warning("OCR en página %d no produjo texto suficiente.", page_number)
    return PageText(
        page_number=page_number,
        text=raw_text,
        status=PageStatus.OCR_FAILED,
        ocr_attempted=True,
        extraction_note="El OCR no recuperó texto suficiente; se conserva el texto seleccionable disponible.",
    )


def _margin_image_signature(page: fitz.Page, image: dict) -> tuple | None:
    bounds = page.rect * page.derotation_matrix
    box = fitz.Rect(image["bbox"]) & bounds
    if box.is_empty or box.is_infinite or not image.get("digest"):
        return None
    x0, y0, x1, y1 = ((box.x0 - bounds.x0) / bounds.width, (box.y0 - bounds.y0) / bounds.height,
                       (box.x1 - bounds.x0) / bounds.width, (box.y1 - bounds.y0) / bounds.height)
    if (x1 - x0 > 0.60 or y1 - y0 > 0.08 or not (y1 <= 0.12 or y0 >= 0.90)):
        return None
    return (image["digest"], *(round(value, 3) for value in (x0, y0, x1, y1)))


def _recurring_margin_images(document: fitz.Document) -> set:
    occurrences = defaultdict(set)
    for number, page in enumerate(document):
        try:
            for image in page.get_image_info(hashes=True):
                signature = _margin_image_signature(page, image)
                if signature:
                    occurrences[signature].add(number)
        except Exception:
            # Unknown image placement is never evidence that OCR can be skipped.
            continue
    return {signature for signature, pages in occurrences.items() if len(pages) >= 2}


def _page_has_images(page: fitz.Page, decorative_images: set | None = None) -> bool:
    """Consider displayed images, retaining uncertain or non-recurring content."""
    try:
        return any(_margin_image_signature(page, image) not in (decorative_images or set())
                   for image in page.get_image_info(hashes=True))
    except Exception:
        return True


# ---------------------------------------------------------------------------
# OCR con Tesseract
# ---------------------------------------------------------------------------

def _tesseract_available() -> bool:
    """Verifica si Tesseract está instalado en el sistema."""
    return shutil.which("tesseract") is not None


def _ocr_page(page: fitz.Page, page_number: int) -> str:
    """
    Aplica OCR a una página usando Tesseract vía pytesseract.

    Requiere:
      - tesseract instalado en el sistema
      - pip install pytesseract pillow
    """
    try:
        import pytesseract
        from PIL import Image
        import io

        # Renderizar la página como imagen (300 DPI para buena calidad OCR)
        scale = min(300 / 72, math.sqrt(16_000_000 / max(1, page.rect.width * page.rect.height)))
        matrix = fitz.Matrix(scale, scale)
        pixmap = page.get_pixmap(matrix=matrix)

        # Convertir pixmap a imagen PIL
        img_bytes = pixmap.tobytes("png")
        image = Image.open(io.BytesIO(img_bytes))

        # OCR con Tesseract (español + inglés para documentos técnicos)
        text = pytesseract.image_to_string(
            image,
            lang="spa+eng",
            config="--psm 3",  # modo automático de segmentación de página
            timeout=20,
        )

        return text.strip()

    except ImportError:
        LOGGER.error(
            "pytesseract o Pillow no están instalados. "
            "Ejecuta: pip install pytesseract pillow"
        )
        return ""
    except Exception as exc:
        LOGGER.error("Error en OCR página %d: %s", page_number, exc)
        return ""


# ---------------------------------------------------------------------------
# Utilidad para instalar datos de idioma de Tesseract
# ---------------------------------------------------------------------------

def check_tesseract_setup() -> dict:
    """
    Verifica el estado de Tesseract e idiomas disponibles.
    Útil para mostrar en la interfaz si hay problemas.
    """
    available = _tesseract_available()
    result = {
        "tesseract_installed": available,
        "spanish_available": False,
        "install_instructions": "",
    }

    if not available:
        result["install_instructions"] = (
            "Tesseract no está instalado.\n"
            "Windows: descarga desde https://github.com/UB-Mannheim/tesseract/wiki\n"
            "Mac:     brew install tesseract tesseract-lang\n"
            "Linux:   sudo apt install tesseract-ocr tesseract-ocr-spa"
        )
        return result

    # Verificar si el idioma español está disponible
    try:
        import pytesseract
        langs = pytesseract.get_languages()
        result["spanish_available"] = "spa" in langs
        result["available_languages"] = langs

        if not result["spanish_available"]:
            result["install_instructions"] = (
                "Tesseract está instalado pero falta el idioma español.\n"
                "Windows: descarga spa.traineddata desde "
                "https://github.com/tesseract-ocr/tessdata\n"
                "Mac:     brew install tesseract-lang\n"
                "Linux:   sudo apt install tesseract-ocr-spa"
            )
    except Exception as exc:
        LOGGER.warning("No se pudo verificar idiomas de Tesseract: %s", exc)

    return result
