# Parsing estructural de PDFs: segmentación por secciones

**Fecha:** mayo 2026  
**Estado:** documento de diseño — pendiente de implementación

---

## 1. El problema actual

Hoy `extract_text_by_page()` devuelve una lista plana de páginas. El detector corre los mismos patrones con la misma ventana de contexto sobre todas las páginas por igual. Esto produce tres problemas concretos:

| Problema | Ejemplo |
|----------|---------|
| Falsos positivos por contexto incorrecto | Una mención a "marca" en la sección de antecedentes históricos tiene el mismo peso que en especificaciones técnicas |
| Ventana de contexto insuficiente en secciones densas | En una tabla de especificaciones, la cláusula de equivalencia global puede estar 10 páginas antes de la especificación de marca |
| Contexto LLM sin ancla estructural | El brief del LLM recibe texto plano sin saber si un fragmento viene de requisitos de habilitación o de condiciones generales |

Los pliegos ecuatorianos son heterogéneos en origen (digital nativo, escaneado, mixto) pero son **relativamente homogéneos en estructura temática**. El SERCOP impone plantillas. Esa homogeneidad estructural es aprovechable.

---

## 2. Tipos de PDFs heterogéneos que pueden llegar

### 2.1 Por origen de extracción

| Tipo | Descripción | Señal de identificación |
|------|-------------|------------------------|
| Digital nativo SERCOP | Exportado del portal, texto seleccionable, estructura uniforme | Texto limpio, headers con código de proceso |
| Digital nativo Word | Generado desde Word por la entidad, sin usar la plantilla del portal | Texto seleccionable pero con estructura variable |
| Escaneado completo | Impreso y re-escaneado, sin texto nativo | `page.get_text()` vacío + imágenes en todas las páginas |
| Mixto digital+escaneado | Carátula digital + especificaciones escaneadas | Texto en primeras páginas, vacío después |
| PDF con tablas estructurales | Especificaciones técnicas en tabla columnar | Texto concatenado sin separadores de columna |
| PDF multi-columna | Layout a dos columnas (pliego + especificaciones lado a lado) | Orden de lectura roto con `get_text("text")` |
| PDF protegido con OCR embedded | Escaneado + OCR interno del escáner (baja calidad) | Texto seleccionable pero con caracteres erróneos |

### 2.2 Por estructura del documento

| Tipo | Descripción |
|------|-------------|
| Pliego con TOC explícito | Tabla de contenidos en primeras páginas, secciones numeradas |
| Pliego sin TOC | Sin índice formal, secciones por títulos en mayúsculas |
| Especificaciones como documento separado | Documento autónomo con su propia estructura |
| Términos de referencia | Estructura de consultoría: alcance, entregables, perfil |
| Pliego integrado | Todo en un solo PDF: condiciones generales + técnicas + formularios |
| Addendum o fe de erratas | Modificaciones sobre un pliego base, sin estructura completa |

---

## 3. Diseño del modelo `DocumentSection`

```python
@dataclass(frozen=True)
class DocumentSection:
    section_id: str           # slug interno: "habilitacion", "especificaciones", etc.
    section_label: str        # etiqueta legible: "Requisitos de habilitación"
    start_page: int
    end_page: int
    text: str                 # texto concatenado de las páginas de esta sección
    detection_profile: str    # "full", "restricted", "skip" — qué patrones correr aquí
    context_multiplier: float # modificador de context_chars para esta sección
```

### 3.1 `detection_profile`

No todas las secciones merecen los mismos patrones:

| `detection_profile` | Cuándo usarlo | Patrones activos |
|--------------------|---------------|-----------------|
| `"full"` | Especificaciones técnicas, requisitos de habilitación | Todos los patrones |
| `"restricted"` | Condiciones generales, marco legal, antecedentes | Solo marca, experiencia, combinaciones |
| `"skip"` | Formularios, declaraciones juramentadas, firmas | Ninguno — ruido puro |

### 3.2 `context_multiplier`

Escalar el `context_chars` base según la densidad estructural de la sección:

| Sección | Multiplicador | Razón |
|---------|--------------|-------|
| `especificaciones_tecnicas` | 1.8× | Tablas largas, equivalencias lejos del match |
| `requisitos_habilitacion` | 1.4× | Cláusulas densas, mitigantes al final del bloque |
| `condiciones_generales` | 1.0× | Baseline |
| `garantias_postventa` | 1.3× | Condiciones técnicas extensas |
| `formularios` | 0.5× | Señales puntuales, poco contexto útil |

---

## 4. Estrategias de detección de secciones

Ordenadas de más simple a más robusta. Para PDFs heterogéneos se recomienda un pipeline en cascada: intentar la estrategia más precisa y degradar si no funciona.

### 4.1 Estrategia A — Título por ALL-CAPS + numeración (más simple)

Detectar líneas candidatas a título en el texto extraído:

```python
import re

_TITLE_PATTERNS = [
    r"^[IVX]+\.\s+[A-ZÁÉÍÓÚÑ\s]{5,80}$",        # I. OBJETO DEL CONTRATO
    r"^\d+(\.\d+)*\s+[A-ZÁÉÍÓÚÑ\s]{5,80}$",      # 3.2 ESPECIFICACIONES TÉCNICAS
    r"^[A-ZÁÉÍÓÚÑ\s]{8,80}$",                     # REQUISITOS DE HABILITACIÓN (línea sola)
    r"^CLÁUSULA\s+(PRIMERA|SEGUNDA|\w+)",          # CLÁUSULA PRIMERA
    r"^SECCIÓN\s+\w+",                             # SECCIÓN III
    r"^CAPÍTULO\s+\w+",                            # CAPÍTULO II
]

def _is_title_candidate(line: str) -> bool:
    stripped = line.strip()
    if len(stripped) < 5 or len(stripped) > 100:
        return False
    return any(re.match(pattern, stripped) for pattern in _TITLE_PATTERNS)
```

**Limitaciones:** requiere texto digital nativo. Falla en PDFs escaneados y en PDFs donde los títulos no siguen convención.

### 4.2 Estrategia B — Vocabulario de secciones conocidas (más robusto)

Buscar en el texto normalizado señales del vocabulario de secciones estándar de los pliegos SERCOP. No requiere formato específico — funciona en texto OCR degradado:

```python
SECTION_VOCABULARY: dict[str, list[str]] = {
    "objeto_contratacion": [
        "objeto de la contratacion",
        "objeto del contrato",
        "descripcion del objeto",
        "naturaleza y objeto",
    ],
    "requisitos_habilitacion": [
        "requisitos de habilitacion",
        "capacidad legal",
        "requisitos minimos",
        "condiciones de participacion",
        "habilitacion del oferente",
    ],
    "especificaciones_tecnicas": [
        "especificaciones tecnicas",
        "ficha tecnica",
        "caracteristicas tecnicas",
        "requerimientos tecnicos",
        "tabla de especificaciones",
        "especificaciones generales y particulares",
    ],
    "experiencia_capacidad": [
        "experiencia minima",
        "experiencia del oferente",
        "capacidad tecnica",
        "trabajos similares",
        "experiencia especifica",
    ],
    "garantias_postventa": [
        "garantia tecnica",
        "garantia de fiel cumplimiento",
        "servicio postventa",
        "repuestos y mantenimiento",
        "garantia del fabricante",
    ],
    "criterios_evaluacion": [
        "criterios de evaluacion",
        "metodologia de evaluacion",
        "puntaje",
        "tabla de calificacion",
        "parametros de evaluacion",
    ],
    "condiciones_generales": [
        "condiciones generales",
        "marco legal",
        "normativa aplicable",
        "base legal",
    ],
    "formularios": [
        "formulario",
        "declaracion juramentada",
        "carta de presentacion",
        "oferta economica",
    ],
}
```

**Ventaja:** funciona en texto OCR degradado, no depende de formato visual. La detección es por presencia de señales, no por estructura visual.

### 4.3 Estrategia C — PyMuPDF blocks mode (más precisa para estructura visual)

`page.get_text("dict")` devuelve bloques con coordenadas y atributos de fuente. Esto permite detectar títulos por **tamaño de fuente** y **posición**, no solo por contenido:

```python
def _extract_blocks_ordered(fitz_page) -> list[dict]:
    """Extract text blocks sorted by reading order (top-to-bottom, left-to-right)."""
    blocks = fitz_page.get_text("dict")["blocks"]
    text_blocks = []
    for block in blocks:
        if block.get("type") != 0:  # skip image blocks
            continue
        y0 = block["bbox"][1]
        x0 = block["bbox"][0]
        lines_text = []
        max_font_size = 0
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                lines_text.append(span["text"])
                max_font_size = max(max_font_size, span.get("size", 0))
        text_blocks.append({
            "text": " ".join(lines_text),
            "y0": y0,
            "x0": x0,
            "font_size": max_font_size,
            "is_bold": any(
                "Bold" in span.get("font", "") or span.get("flags", 0) & 2**4
                for line in block.get("lines", [])
                for span in line.get("spans", [])
            ),
        })
    return sorted(text_blocks, key=lambda b: (b["y0"], b["x0"]))


def _is_title_by_format(block: dict, body_font_size: float) -> bool:
    """A block is a title candidate if its font is significantly larger or bold."""
    return block["font_size"] > body_font_size * 1.15 or (
        block["is_bold"] and len(block["text"].strip()) < 120
    )
```

**Ventaja:** más precisa para PDFs con estructura visual clara. Detecta títulos incluso sin mayúsculas o numeración. **Limitación:** requiere PDF digital nativo; no funciona en PDFs escaneados.

### 4.4 Pipeline en cascada (recomendado)

Para PDFs heterogéneos, usar las estrategias en cascada con degradación controlada:

```python
def segment_document(pages: list[PageText], fitz_doc=None) -> list[DocumentSection]:
    """
    Intenta segmentar el documento en secciones estructuradas.
    Pipeline de cascada:
    1. Si fitz_doc disponible y PDF nativo: usar Estrategia C (blocks + fuente)
    2. Si hay texto nativo pero sin estructura visual clara: usar Estrategia A + B
    3. Si texto de baja calidad (OCR) o sin estructura: usar Estrategia B sola
    4. Si no se detectan secciones: devolver una sola sección "desconocido" con todo el doc
    """
    sections = []

    # Intentar Estrategia C (más precisa)
    if fitz_doc and _is_native_text_pdf(pages):
        sections = _segment_by_visual_blocks(pages, fitz_doc)

    # Fallback a Estrategia A+B
    if not sections:
        sections = _segment_by_title_patterns(pages)

    # Fallback a Estrategia B sola
    if not sections:
        sections = _segment_by_vocabulary(pages)

    # Fallback total: todo el documento como una sola sección
    if not sections:
        all_text = "\n\n".join(p.text for p in pages)
        sections = [DocumentSection(
            section_id="desconocido",
            section_label="Documento completo (sin estructura detectada)",
            start_page=pages[0].page_number if pages else 1,
            end_page=pages[-1].page_number if pages else 1,
            text=all_text,
            detection_profile="full",
            context_multiplier=1.0,
        )]

    return sections
```

---

## 5. Vocabulario de secciones por tipo de documento

Las secciones más relevantes para detección de restricción competitiva, por tipo de documento:

### 5.1 Pliego de condiciones

| Sección | `section_id` | `detection_profile` | Señales típicas de restricción |
|---------|-------------|--------------------|---------------------------------|
| Objeto de contratación | `objeto_contratacion` | `restricted` | Define el alcance; ancla el análisis de proporcionalidad |
| Requisitos de habilitación | `requisitos_habilitacion` | `full` | Experiencia, certificaciones, presencia local |
| Especificaciones técnicas | `especificaciones_tecnicas` | `full` | Marca, modelo, equivalencias, fichas técnicas |
| Criterios de evaluación | `criterios_evaluacion` | `full` | Criterios subjetivos, ponderaciones arbitrarias |
| Garantías y postventa | `garantias_postventa` | `full` | Autorización de fabricante, repuestos, asistencia técnica |
| Condiciones generales | `condiciones_generales` | `restricted` | Fórmulas de participación, cláusulas estándar |
| Formularios | `formularios` | `skip` | Ruido puro para la detección |

### 5.2 Especificaciones técnicas (documento separado)

| Sección | `section_id` | Nota |
|---------|-------------|------|
| Tabla de especificaciones | `tabla_especificaciones` | Alta densidad de marcas y modelos |
| Requisitos mínimos | `requisitos_minimos` | Umbrales técnicos, certificaciones requeridas |
| Condiciones de garantía | `condiciones_garantia` | Postventa, repuestos, tiempo de respuesta |
| Instalación y capacitación | `instalacion_capacitacion` | Presencia local implícita |

### 5.3 Términos de referencia

| Sección | `section_id` | Nota |
|---------|-------------|------|
| Alcance del servicio | `alcance_servicio` | Experiencia específica, perfil del consultor |
| Perfil del equipo | `perfil_equipo` | Formación, certificaciones, años de experiencia |
| Entregables | `entregables` | Requisitos técnicos de output |

---

## 6. Cómo cambia el pipeline de detección con secciones

### 6.1 Antes (pipeline actual)

```
pdf_bytes
    → extract_text_by_page() → list[PageText]
    → detect_patterns(pages) → list[Finding]  ← mismo proceso para todas las páginas
```

### 6.2 Con segmentación

```
pdf_bytes
    → extract_text_by_page() → list[PageText]
    → segment_document(pages) → list[DocumentSection]
    → detect_patterns_in_section(section) → list[Finding]  ← profile + context por sección
        - detection_profile filtra patrones activos
        - context_multiplier ajusta context_chars
        - section_id se incluye en el Finding para trazabilidad
```

Cambios en `Finding`:
```python
@dataclass
class Finding:
    # campos actuales...
    section_id: str = "desconocido"       # nuevo
    section_label: str = "No determinada" # nuevo
```

Cambios en `detect_patterns()`:
```python
def detect_patterns(
    pages: list[PageText],
    sections: list[DocumentSection] | None = None,
) -> list[Finding]:
    if sections is None:
        # compatibilidad backward: segmentar con fallback total
        sections = segment_document(pages)
    
    findings = []
    for section in sections:
        if section.detection_profile == "skip":
            continue
        active_patterns = _filter_patterns_for_profile(section.detection_profile)
        for pattern in active_patterns:
            context_chars = _context_chars_for_pattern(pattern.id) * section.context_multiplier
            # ... detección existente con context_chars ajustado
    return findings
```

---

## 7. Impacto en el LLM

Con secciones, el prompt del brief puede incluir la sección de origen de cada señal:

```json
{
  "patron": "marca",
  "section_id": "especificaciones_tecnicas",
  "section_label": "Especificaciones técnicas",
  "fragmento": "... marca ACME modelo X100 ..."
}
```

El LLM puede calibrar mejor: una marca en especificaciones técnicas con tabla columnar tiene más peso que una mención casual en antecedentes. También permite few-shot selection por sección:

- Marca en `especificaciones_tecnicas` → `FEWSHOT_MARCA_SIN_EQUIVALENTE`
- Experiencia en `requisitos_habilitacion` → `FEWSHOT_EXPERIENCIA_ESPECIFICA` (pendiente)
- Presencia local en `requisitos_habilitacion` → `FEWSHOT_PRESENCIA_LOCAL`

---

## 8. Casos de degradación controlada

Para PDFs que no tienen estructura detectable, el sistema no debe fallar. Degradación en cascada:

| Situación | Comportamiento |
|-----------|----------------|
| PDF digital con TOC y títulos claros | Segmentación completa por Estrategia C |
| PDF digital sin títulos formateados | Segmentación por vocabulario (Estrategia B) |
| PDF escaneado con OCR | Segmentación por vocabulario sobre texto OCR |
| PDF escaneado sin OCR activado | Una sola sección "desconocido", detección completa |
| PDF mixto (algunas páginas sin texto) | Seccionar las páginas con texto, marcar las vacías como `skip` |
| Documento sin secciones conocidas | Una sola sección `"desconocido"` con `detection_profile="full"` |

El campo `section_id="desconocido"` en un `Finding` indica al revisor que la señal se encontró en texto sin estructura identificable — eso es información útil en sí misma.

---

## 9. Consideraciones de implementación

### 9.1 Dónde implementar

`src/analyzer/pdf_extractor.py` o un nuevo módulo `src/analyzer/document_segmenter.py`. Se recomienda módulo separado porque:
- El extractor maneja bytes → PageText (bajo nivel)
- El segmentador transforma PageText → DocumentSection (nivel semántico)
- Mantiene responsabilidades claras

### 9.2 Qué requiere fitz.Document abierto

Para la Estrategia C se necesita el objeto `fitz.Document` con las páginas originales, no solo el texto extraído. Dos opciones:

**Opción 1:** Pasar `fitz_doc` al segmentador como parámetro opcional. El caller (`app.py`) mantiene el documento abierto para el segmentador y luego lo cierra. Requiere refactor de `extract_text_by_page()`.

**Opción 2:** Hacer que `extract_text_by_page()` devuelva también los metadatos de bloque como campo adicional en `PageText`:
```python
@dataclass(frozen=True)
class PageText:
    page_number: int
    text: str
    source: str = "native"
    blocks: list[dict] = field(default_factory=list)  # bloques de get_text("dict")
```

La **Opción 2** es más simple: toda la información necesaria viaja en `PageText`, sin necesidad de mantener el documento abierto.

### 9.3 Límite de páginas para segmentación

Para documentos muy largos (> 100 páginas), segmentar todo el documento puede ser lento. Estrategia de optimización: segmentar solo las primeras N páginas (donde N = min(total, 40)) para construir el mapa de secciones, y extender la última sección detectada hasta el final del documento.

### 9.4 Tests mínimos necesarios

```python
# Test: PDF digital con secciones estándar
def test_segment_pliego_con_secciones():
    pages = [
        PageText(1, "OBJETO DE LA CONTRATACIÓN\nAdquisición de equipos informáticos..."),
        PageText(2, "REQUISITOS DE HABILITACIÓN\nEl oferente deberá acreditar experiencia..."),
        PageText(3, "ESPECIFICACIONES TÉCNICAS\nEquipo marca ACME modelo X100 o equivalente..."),
    ]
    sections = segment_document(pages)
    section_ids = [s.section_id for s in sections]
    assert "objeto_contratacion" in section_ids
    assert "requisitos_habilitacion" in section_ids
    assert "especificaciones_tecnicas" in section_ids

# Test: PDF sin estructura → fallback a sección única
def test_segment_sin_estructura_devuelve_fallback():
    pages = [PageText(1, "Texto sin títulos ni estructura formal.")]
    sections = segment_document(pages)
    assert len(sections) == 1
    assert sections[0].section_id == "desconocido"
    assert sections[0].detection_profile == "full"

# Test: sección formulario se marca como skip
def test_formulario_se_omite_en_deteccion():
    pages = [PageText(1, "FORMULARIO 1\nDeclaración juramentada del oferente...")]
    sections = segment_document(pages)
    formulario = next((s for s in sections if s.section_id == "formularios"), None)
    if formulario:
        assert formulario.detection_profile == "skip"
```

---

## 10. Priorización e integración con el roadmap

Esta función no está en las fases actuales porque requiere refactor del pipeline de detección. Se recomienda como primera tarea de **Fase 5** (después de Fase 4 — arquitectura).

**Dependencias:** Fase 4 (split de `app.py` y separación de coordinación) facilita mucho integrar esto sin enredar la lógica de UI.

**Impacto esperado:**
- Reducción de falsos positivos: patrones en secciones `"skip"` ya no se detectan
- Mejor contexto para el LLM: cada señal llega con su sección de origen
- Ventanas de contexto más precisas: multiplicador por sección
- Few-shot selection más precisa: tipo de señal + sección

**Esfuerzo estimado:** 2-3 jornadas para Estrategia B (vocabulario) + tests. Estrategia C (blocks mode) requiere 1 jornada adicional y refactor de `PageText`.
