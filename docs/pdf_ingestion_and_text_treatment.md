# Ingesta de PDF y tratamiento del texto origen

**Fecha:** mayo 2026  
**Estado:** documento de trabajo — próximos pasos

---

## 1. Situación actual en el código

`src/analyzer/pdf_extractor.py` tiene 24 líneas y hace una sola cosa:

```python
text = page.get_text("text").strip()
```

Sin limpieza, sin clasificación del origen, sin OCR, sin detección del tipo de documento. El texto llega tal cual sale de PyMuPDF al detector y, desde ahí, al LLM. Todo el pipeline de análisis asume que el texto es legible, continuo y bien formado. Eso no siempre es verdad.

---

## 2. Tipos de PDF que llegan en contratación pública ecuatoriana

Los pliegos que maneja SERCOP no son uniformes. En la práctica existen al menos cuatro orígenes distintos, y cada uno produce texto con patrones de ruido completamente diferentes.

### 2.1 PDF digital nativo (origen más limpio)

Generado directamente desde Word, Excel o el portal SERCOP. El texto es seleccionable, las columnas están en orden lógico, la estructura es recuperable.

**Características del texto extraído:**
- Flujo de lectura correcto por página
- Números de artículo, ítems y cláusulas preservados
- Tablas pierden estructura pero el contenido está presente
- Headers y footers se repiten en cada página (número de proceso, entidad, fecha)
- Saltos de línea espurios dentro de párrafos (por el wrap visual del PDF)

**Acción necesaria:** limpieza mínima — quitar repetición de headers/footers, unir líneas rotas dentro de párrafos.

### 2.2 PDF escaneado sin OCR (origen más problemático)

El documento fue impreso y vuelto a escanear. PyMuPDF no extrae texto: devuelve cadenas vacías o caracteres basura. La app ya detecta este caso en `validate_extracted_pages()` (líneas 737–755 de `app.py`) y avisa al usuario, pero no hace nada más.

**Qué pasa hoy:** `total_chars == 0` → warning al usuario → el pipeline continúa con detecciones vacías → resultado silenciosamente inútil.

**Acción necesaria:** OCR. La opción más directa para esta arquitectura es `pytesseract` con idioma español (`lang='spa'`) o `easyocr`. Requiere detectar primero si la página tiene texto nativo o es imagen.

Detección sugerida por página:
```python
# Si el texto extraído tiene menos de N chars pero la página tiene imágenes,
# es candidata a OCR
def page_needs_ocr(page: fitz.Page, min_chars: int = 50) -> bool:
    text = page.get_text("text").strip()
    has_images = len(page.get_images()) > 0
    return len(text) < min_chars and has_images
```

### 2.3 PDF mixto (digital + escaneado)

Algunos pliegos tienen páginas digitales (carátula, normativa) y páginas escaneadas (especificaciones técnicas, fichas). Este es el caso más frecuente y el más difícil porque requiere decisión página a página.

**Estrategia:** detectar el origen por página, aplicar PyMuPDF donde hay texto nativo, OCR donde no lo hay, luego unir el resultado en la misma estructura `list[PageText]`.

### 2.4 PDF con tablas estructurales (especificaciones técnicas)

Las especificaciones técnicas frecuentemente vienen en tablas: columna "característica", columna "valor requerido", columna "ofertado". Con `get_text("text")` el texto de todas las columnas se concatena en orden de aparición en el PDF, rompiendo la relación característica-valor.

**Ejemplo del problema:**
```
# Lo que hay en la tabla:
# | Característica | Valor requerido |
# | Potencia       | mínimo 150 HP   |
# | Marca          | referencial     |

# Lo que extrae get_text("text"):
"Característica Valor requerido Potencia mínimo 150 HP Marca referencial"
```

Esto afecta directamente la calidad de los fragmentos textuales que llegan al LLM y al detector de patrones.

**Alternativa:** `page.get_text("dict")` devuelve bloques con coordenadas que permiten reconstruir la estructura de tabla. `page.get_text("html")` también preserva algo de estructura tabular. Ambos requieren un parser adicional.

Para un primer paso pragmático: usar `page.get_text("blocks")` y ordenar bloques por posición Y, luego X, lo que mejora el orden de lectura en documentos multi-columna.

---

## 3. Pipeline de limpieza del texto extraído

Actualmente no existe un módulo de limpieza. El texto sale de `pdf_extractor.py` y entra directamente al `detector.py`. La normalización se hace dentro del detector, de dos formas inconsistentes:

- `detector.py:910`: `normalize_text()` = `_normalize_whitespace().lower()` — sin manejo de acentos
- `prioritizer.py:349`: `_normalized_text()` = reemplazo manual de á→a, é→e, etc. — sin normalizar whitespace

Son dos funciones distintas que hacen cosas distintas sobre el mismo concepto. Cualquier módulo que las llame tiene comportamiento diferente.

### 3.1 Función única de limpieza de texto extraído

Propuesta para `src/analyzer/text_cleaner.py`:

```python
import re
import unicodedata

def clean_page_text(raw_text: str) -> str:
    """Limpieza estándar de texto extraído de PDF.

    Orden de operaciones importa: primero unir líneas rotas,
    luego normalizar unicode, luego whitespace.
    """
    text = _join_broken_lines(raw_text)
    text = _remove_repeated_headers(text)
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_for_matching(text: str) -> str:
    """Normalización para comparación y detección de patrones."""
    text = clean_page_text(text).lower()
    # Quitar acentos pero preservar la ñ para matching en español
    text = "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn" or c == "̃"  # preserve combining tilde
    )
    return text


def _join_broken_lines(text: str) -> str:
    # Línea que termina en guión + salto: palabra cortada por wrap
    text = re.sub(r"-\n(\w)", r"\1", text)
    # Línea que no termina en puntuación + salto: párrafo roto por columna
    text = re.sub(r"(?<![.;:!?\n])\n(?!\n)(?!\d+\.)(?![A-Z]{2,})", " ", text)
    return text


def _remove_repeated_headers(text: str) -> str:
    # Headers/footers que se repiten: detectar líneas idénticas en múltiples páginas
    # (implementación simplificada por ahora — mejora futura con detección por frecuencia)
    return text
```

### 3.2 Artefactos específicos de pliegos ecuatorianos

Los PDFs del SERCOP tienen patrones de ruido predecibles:

| Artefacto | Ejemplo | Efecto en detección |
|-----------|---------|---------------------|
| Número de resolución en cada página | `RESOLUCIÓN-SERCOP-RE-2024-0001` | Falsos positivos de patrón "resolución" |
| Marca de agua "BORRADOR" | `B O R R A D O R` | Interferencia en fragmentos |
| Número de página + fecha | `Página 3 de 47 — 15/03/2024` | Contamina fragmentos textuales |
| Código de ítem de tabla | `1.2.3` al inicio de línea | Se une al párrafo siguiente si no se limpia |
| Texto de tabla partido | columnas concatenadas sin separador | Rompe la semántica del fragmento |

---

## 4. Clasificación del origen del PDF

Hoy el sistema no sabe nada sobre el tipo de documento que está analizando. Un pliego tiene estructura diferente a unas especificaciones técnicas, y ambos son distintos a unos términos de referencia.

### 4.1 Clasificación heurística por contenido

Sin cambiar la arquitectura, se puede inferir el tipo de documento por señales textuales en las primeras páginas:

```python
DOCUMENT_TYPE_SIGNALS = {
    "pliego": [
        "pliego de condiciones", "bases generales", "condiciones particulares",
        "objeto de la contratación", "presupuesto referencial"
    ],
    "especificaciones_tecnicas": [
        "especificaciones técnicas", "ficha técnica", "características técnicas",
        "tabla de especificaciones", "requerimientos técnicos mínimos"
    ],
    "terminos_referencia": [
        "términos de referencia", "tor ", "alcance del servicio",
        "perfil del consultor", "entregables"
    ],
    "contrato": [
        "cláusula primera", "partes contratantes", "objeto del contrato",
        "precio del contrato"
    ],
}
```

Esto permite:
1. Ajustar el tamaño de la ventana de contexto según tipo (especificaciones necesitan más contexto para entender equivalencias)
2. Seleccionar los few-shots del LLM apropiados al tipo
3. Informar al usuario qué tipo de documento se está analizando

### 4.2 Extracción del objeto de contratación

Hoy el prompt del LLM incluye esta línea hardcodeada (llm_reviewer.py:275):

```python
"Objeto de contratación: No disponible en el documento cargado.\n\n"
```

El objeto del contrato casi siempre está en las primeras 2–3 páginas bajo rótulos predecibles. Extraerlo mejora dramáticamente la calidad del análisis LLM:

```python
OBJECT_PATTERNS = [
    r"objeto(?:\s+de\s+(?:la\s+)?contrataci[oó]n)?[:\s]+([^\n]{20,300})",
    r"descripci[oó]n(?:\s+del\s+objeto)?[:\s]+([^\n]{20,300})",
    r"adquisici[oó]n\s+de\s+([^\n]{20,200})",
    r"contrataci[oó]n\s+de\s+(?:servicios\s+de\s+)?([^\n]{20,200})",
]

def extract_contract_object(pages: list[PageText], max_pages: int = 3) -> str:
    """Intenta extraer el objeto de contratación de las primeras páginas."""
    for page in pages[:max_pages]:
        for pattern in OBJECT_PATTERNS:
            match = re.search(pattern, page.text, re.IGNORECASE)
            if match:
                return match.group(1).strip()[:300]
    return "No identificado en las primeras páginas"
```

---

## 5. Ventanas de contexto dinámicas según tipo de PDF y patrón

Hoy `extract_context_window()` usa `context_chars=260` fijo para todos los patrones. El problema:

- Para "marca" necesitás ver si hay una cláusula de equivalencia que puede estar 400+ chars después
- Para "presencia local" necesitás ver la justificación técnica que puede estar en el párrafo anterior
- Para "adjunto" o "link" la señal está completa en 80 chars

### 5.1 Context chars por tipo de señal

```python
CONTEXT_CHARS_BY_PATTERN = {
    # Patrones que requieren ver la justificación o equivalencia cercana
    "cn-brand-model-provider-reference": 500,
    "cn-weak-equivalence-clause": 400,
    "cn-technical-closed-requirement": 450,
    "cn-specific-certification": 380,
    "cn-local-presence-requirement": 420,
    "cn-specific-experience": 380,
    # Patrones de completitud: la señal es puntual
    "cn-incomplete-technical-reference": 180,
    "cn-missing-annex-reference": 180,
    # Default
    "_default": 260,
}
```

### 5.2 Context chars por tipo de documento

Los pliegos tienen cláusulas largas. Los términos de referencia tienen párrafos cortos. El contexto útil varía:

| Tipo documento | Multiplicador recomendado |
|----------------|---------------------------|
| especificaciones_tecnicas | 1.5× (tablas, fichas largas) |
| pliego | 1.0× (baseline) |
| terminos_referencia | 0.8× (párrafos cortos) |
| contrato | 1.2× (cláusulas extensas) |

---

## 6. Próximos pasos priorizados

### Prioridad 1 — Sin cambios de arquitectura, impacto inmediato

1. Crear `src/analyzer/text_cleaner.py` con `clean_page_text()` y `normalize_for_matching()`
2. Reemplazar los dos `normalize_text` / `_normalized_text` existentes por llamadas a `text_cleaner`
3. Agregar `extract_contract_object()` e inyectarlo en `_build_document_brief_prompt()` (reemplaza el "No disponible" en llm_reviewer.py:275)
4. Crear `CONTEXT_CHARS_BY_PATTERN` y usarlo en `extract_context_window()` del detector

### Prioridad 2 — Mejoras de ingesta

5. Agregar detección de tipo de documento en `pdf_extractor.py` — devolver `DocumentType` junto con `list[PageText]`
6. Agregar detección de páginas que necesitan OCR + integración con `pytesseract` o `easyocr`
7. Explorar `page.get_text("blocks")` para mejorar el orden de lectura en documentos con tablas

### Prioridad 3 — Trazabilidad de origen

8. Registrar el tipo de extracción por página (nativo/OCR/vacío) en `PageText`
9. Incluir el hash SHA256 del YAML de taxonomía activo en los campos de trazabilidad de cada hallazgo
10. Agregar el tipo de documento detectado a los metadatos del análisis exportado
