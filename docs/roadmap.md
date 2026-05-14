# Roadmap de mejoras

**Fecha:** mayo 2026  
**Estado:** documento vivo — actualizar a medida que avanza el trabajo

---

## Diagnóstico de partida

El proyecto tiene tres capas de problemas independientes con distinta urgencia.

### Capa 1 — Roto

| # | Problema | Archivo | Línea |
|---|----------|---------|-------|
| 1 | `DEFAULT_MODEL = "gpt-5.4-mini"` no existe — LLM falla silenciosamente | llm_reviewer.py | 29 |
| 2 | `.env.example` solo tiene `OPENAI_API_KEY` — faltan `OPENAI_MODEL` y `OPENAI_BASE_URL` | .env.example | — |
| 3 | No hay corpus de muestra — la comparación histórica siempre muestra "Sin histórico" | data/ | — |

### Capa 2 — Funciona pero produce output de baja calidad

| # | Problema | Archivo | Línea |
|---|----------|---------|-------|
| 4 | Objeto de contratación hardcodeado como "No disponible" en el prompt del LLM | llm_reviewer.py | 275 |
| 5 | Sin few-shots — varianza alta en outputs del LLM | llm_reviewer.py | 289, 246 |
| 6 | Taxonomía completa (~2000 tokens, 12 patrones) inyectada en cada llamada de señal individual | llm_reviewer.py | 307 |
| 7 | Dos funciones de normalización inconsistentes — `normalize_text()` sin acentos, `_normalized_text()` sin whitespace | detector.py:910, prioritizer.py:349 | — |
| 8 | Ventana de contexto fija en 260 chars — pierde mitigantes que aparecen 400+ chars después | detector.py | 922 |

### Capa 3 — Deuda técnica

| # | Problema | Archivo |
|---|----------|---------|
| 9 | `_TAXONOMY_CACHE` global mutable — rompe en tests paralelos | detector.py:647 |
| 10 | `app.py` de 1090 líneas mezcla renderizado, coordinación y exportación | app.py |
| 11 | Sin hash SHA256 de taxonomía activa en los hallazgos exportados | prioritizer.py |
| 12 | Sin loop de feedback para capturar juicio del revisor | — |
| 13 | Sin OCR para PDFs escaneados — la app avisa pero no hace nada | pdf_extractor.py |
| 14 | `pytest` en requirements.txt en vez de requirements-dev.txt | requirements.txt |

---

## Fases

```
Fase 0 — Arranca y corre        ✅  ~1 hora        Capa 1 completa
Fase 1 — Calidad de reglas      ✅  ~1 jornada     Capa 2: normalización, ventanas, extracción
Fase 2 — Calidad del LLM        ✅  ~1 jornada     Capa 2: few-shots, taxonomía filtrada, objeto
Fase 3 — Robustez operativa     ✅  ~2 jornadas    Capa 3: OCR, tipo doc, feedback, SHA256
Fase 4 — Arquitectura           ✅  ~1 jornada     Capa 3 resto: split app.py, cache, tests E2E
Fase 5 — Parsing estructural    ✅  ~1 jornada     Segmentación por secciones del documento
```

Fase 1 y Fase 2 son independientes entre sí. Fase 5 depende de Fase 4.

---

## Fase 0 — Arranca y corre

**Objetivo:** cualquier persona puede clonar, configurar y ejecutar la app con LLM funcionando en menos de 10 minutos.

**Condición de salida:** `test_llm_connection()` retorna `True` en un entorno limpio con solo `OPENAI_API_KEY` configurada.

### Tareas

- [x] **0.1** Corregir `DEFAULT_MODEL = "gpt-4o-mini"` en `llm_reviewer.py:29`
- [x] **0.2** Completar `.env.example` con las cuatro variables (OpenAI directo + Azure OpenAI):
  ```
  OPENAI_API_KEY=sk-...
  OPENAI_MODEL=gpt-4o-mini
  OPENAI_BASE_URL=   # vacío para OpenAI directo; endpoint Azure si aplica
  OPENAI_API_VERSION=   # vacío para OpenAI directo; "2024-06-01" para Azure
  ```
- [x] **0.3** Mejorar `test_llm_connection()` para verificar que el modelo responde exactamente "OK", no cualquier texto no vacío
- [x] **0.4** Crear `data/raw/metadata/procesos.csv` con 5 procesos ficticios (process_id, entidad, objeto, fecha, pliego_file, especificaciones_file)

---

## Fase 1 — Calidad del análisis de reglas

**Objetivo:** el análisis sin LLM (reglas + taxonomía + corpus) produce fragmentos textuales limpios, detecta mitigantes que hoy pierde por acentos o ventana corta, y prioriza de forma consistente entre módulos.

**Condición de salida:** un pliego con "marca X o equivalente funcional" detecta el mitigante correctamente; los fragmentos exportados al CSV son legibles en Excel sin caracteres raros.

### Tareas

- [x] **1.1** Crear `src/analyzer/text_cleaner.py` con:
  - `clean_page_text(raw_text: str) -> str` — une líneas rotas por guión, quita whitespace múltiple, normaliza unicode NFKC
  - `normalize_for_matching(text: str) -> str` — para uso interno del detector; maneja acentos (NFD) + lowercase + whitespace
  - Reemplazó `normalize_text()` en `detector.py` por llamada a `text_cleaner.normalize_for_matching()`
  - Reemplazó `_normalized_text()` en `prioritizer.py` por la misma función

- [x] **1.2** Ajustar `context_chars` por tipo de patrón en `detector.py` (`CONTEXT_CHARS_BY_PATTERN`):
  - Patrones de marca/equivalencia: 500 chars
  - Patrones de presencia local/experiencia: 420 chars
  - Patrones de completitud documental: 180 chars
  - Default: 260 chars

- [x] **1.3** Agregar `extract_contract_object(pages: list[PageText]) -> str` en `pdf_extractor.py`:
  - Busca en las primeras 3 páginas con 5 patrones regex (objeto de contratación, adquisición de, etc.)
  - Retorna el fragmento extraído (máx 300 chars) o `"No identificado en las primeras páginas"`

- [x] **1.4** Limpiar texto antes de exportar a CSV: `clean_export_dataframe()` en `app.py` aplica `clean_page_text()` sobre `fragmento textual` en el export sin alterar el DataFrame original

---

## Fase 2 — Calidad del LLM

**Objetivo:** el análisis asistido produce outputs útiles, consistentes y calibrados al dominio ecuatoriano. El modelo sabe para quién escribe y tiene ejemplos de lo que se espera.

**Condición de salida:** la explicación de una señal "marca sin equivalente" en un pliego de equipos incluye una pregunta sobre el expediente técnico y no usa lenguaje acusatorio.

### Tareas

- [x] **2.1** Agregar descripción del lector objetivo al `SYSTEM_PROMPT`: técnico institucional sin formación legal, 30 minutos, orientado a decisión

- [x] **2.2** Implementar `_relevant_taxonomy_context(finding: dict) -> dict` que filtra la taxonomía al patrón relevante + sus `related_patterns`. Reemplazó `taxonomy_context(limit=6)` en `_build_finding_prompt()` — reduce de ~2000 tokens a ~300 tokens por llamada individual

- [x] **2.3** Agregar los 4 few-shots como constantes en `llm_reviewer.py`:
  - `FEWSHOT_MARCA_SIN_EQUIVALENTE`
  - `FEWSHOT_MARCA_CON_EQUIVALENTE`
  - `FEWSHOT_REQUISITO_HABITUAL`
  - `FEWSHOT_PRESENCIA_LOCAL`

- [x] **2.4** Implementar `_select_few_shots(finding: dict) -> str` — selección dinámica por tipo de señal y presencia de mitigantes

- [x] **2.5** Conectar `extract_contract_object()` al prompt del brief: `generate_document_brief()` y `cached_generate_document_brief()` aceptan `contract_object`; `app.py` lo extrae y lo pasa

---

## Fase 3 — Robustez operativa

**Objetivo:** la app se comporta bien con los PDFs reales que llegan del SERCOP, incluyendo los casos problemáticos más frecuentes.

### Tareas

- [x] **3.1** Detección de páginas que necesitan OCR:
  - `_page_needs_ocr(fitz.Page) -> bool` en `pdf_extractor.py` — detecta páginas con imágenes pero sin texto
  - `validate_extracted_pages()` distingue ahora páginas OCR-candidatas (`source="empty"`) de páginas vacías sin imágenes
  - Mensaje diferenciado: cuántas páginas necesitan OCR y cómo activarlo

- [x] **3.2** Integración OCR opcional con `pytesseract` (idioma `spa`):
  - `extract_text_by_page(pdf_bytes, attempt_ocr=True)` aplica OCR si pytesseract está instalado
  - Si no está instalado, degrada gracefully (páginas con `source="empty"`)
  - `PageText.source` registra `"native"`, `"ocr"` o `"empty"` por página
  - `count_ocr_candidates(pdf_bytes) -> int` para uso futuro en UI

- [x] **3.3** Detección del tipo de documento:
  - `detect_document_type(pages) -> str` — heurística por señales textuales en primeras 5 páginas
  - Tipos: `"pliego"`, `"especificaciones_tecnicas"`, `"terminos_referencia"`, `"contrato"`, `"desconocido"`
  - Se muestra en la UI post-extracción y se agrega al DataFrame como `tipo_documento`

- [x] **3.4** Feedback loop — capturar juicio del revisor:
  - `render_feedback_buttons(row)` con 3 botones: Confirmar / Descartar / Más contexto
  - Aparece en cada tarjeta de señal (Top 3 prioridades y cards de temas)
  - Graba en `data/feedback/cases.jsonl`: signal_id, pattern_id, signal_type, has_mitigants, rarity, fragment_preview, verdict, timestamp
  - `data/feedback/cases.jsonl` está en `.gitignore` (puede contener fragmentos de pliegos reales)

- [x] **3.5** Hash SHA256 de taxonomía activa en los hallazgos exportados:
  - `taxonomy_sha256()` en `taxonomy_loader.py` — primeros 16 hex del SHA256 del YAML activo
  - Campo `taxonomy_sha256` en cada fila de `prioritizer.py` junto a `engine_version` y `rule_version`

---

## Fase 4 — Arquitectura

**Objetivo:** el código soporta crecimiento sin deuda acumulada. Esta fase no cambia funcionalidad.

### Tareas

- [x] **4.1** Separar `app.py` en módulos:
  - `src/ui/components.py` — constantes, helpers compartidos (`safe_text`, `attention_badge`, etc.)
  - `src/ui/cache.py` — wrappers `@st.cache_data`
  - `src/ui/header.py` — `render_institutional_header()`, `render_pipeline()`
  - `src/ui/findings.py` — `render_aspect_card()`, `render_top_priorities()`, `render_theme_groups()`, `render_feedback_buttons()`
  - `src/ui/briefing.py` — `render_briefing()`, `render_ai_document_brief()`, `render_analytical_balance()`
  - `src/ui/export.py` — `ordered_export()`, `build_executive_report_markdown()`
  - `src/pipeline/coordinator.py` — `prepare_results_dataframe()`, `render_corpus_status()`, `validate_extracted_pages()`
  - `app.py` reducido a ~165 líneas (solo orquestación)

- [x] **4.2** Reemplazar `_TAXONOMY_CACHE` global mutable por `@lru_cache(maxsize=1)` en `detector.py`
  - Retorna `tuple[TaxonomyPattern, ...]` (inmutable, cache-safe)

- [x] **4.3** Separar dependencias:
  - `pytest` movido a `requirements-dev.txt`
  - `pyproject.toml` con `[tool.pytest.ini_options]` (testpaths, pythonpath)

- [x] **4.4** Test de integración end-to-end (`tests/test_e2e_pipeline.py`):
  - PDF sintético generado en memoria con `fitz` — texto con señales reales de pliego
  - 9 tests: extracción, tipo documento, detecciones, columnas requeridas, trazabilidad, signal_ids únicos, brief ejecutivo, lenguaje no acusatorio, campo `source`
  - **21 tests totales pasan** (12 previos + 9 nuevos)

---

## Fase 5 — Parsing estructural del documento

**Objetivo:** el sistema entiende qué sección del documento contiene cada señal detectada. Esto reduce falsos positivos, mejora las ventanas de contexto y enriquece el prompt del LLM con contexto estructural.

**Condición de salida:** una señal de "marca" en la sección de especificaciones técnicas tiene `section_id="especificaciones_tecnicas"` en el Finding y el CSV exportado. Una señal en un formulario no genera hallazgo.

**Referencia de diseño:** `docs/structural_parsing.md` — arquitectura completa, estrategias de detección, vocabulario de secciones, casos de degradación y tests mínimos.

**Dependencia:** Fase 4 (separación de `app.py` facilita la integración sin mezclar UI y pipeline).

### Tareas

- [x] **5.1** Crear `src/analyzer/document_segmenter.py`:
  - `@dataclass(frozen=True) DocumentSection`: `section_id`, `section_label`, `start_page`, `end_page`, `text`, `detection_profile`, `context_multiplier`
  - `segment_document(pages)` con cascada: Estrategia B (vocabulario) → Estrategia A (títulos) → fallback sección única
  - `SECTION_VOCABULARY` con 8 tipos de sección (objeto, habilitación, especificaciones, experiencia, garantías, evaluación, condiciones, formularios)
  - `_SECTION_CONFIG` con detection_profile y context_multiplier por sección

- [x] **5.2** Integrar segmentación en `detector.py`:
  - `detect_patterns(pages, sections=None)` — segmenta automáticamente si no se pasan secciones
  - Secciones `"skip"` omitidas completamente (cero detecciones en formularios)
  - Secciones `"restricted"` saltan SIGNAL_MITIGANT y SIGNAL_HABITUAL
  - `context_multiplier` aplicado a `context_chars` por sección (hasta 1.8× en specs técnicas)
  - `section_id` y `section_label` en `Finding` y `Detection`

- [x] **5.3** Incluir sección en outputs y LLM:
  - `section_id` y `section_label` en `to_dict()` → exportados en CSV
  - `section_id`/`section_label` en `_compact_finding()` → llegan al LLM como contexto
  - `Finding` y `Detection` tienen ambos campos con defaults backward-compatible

- [ ] **5.4** Estrategia C opcional (blocks mode) — futura, requiere `PageText.blocks`:
  - `extract_text_by_page()` captura `get_text("dict")["blocks"]` por página
  - `_segment_by_visual_blocks()` usa tamaño de fuente + bold para detectar títulos

- [x] **5.5** Tests (`tests/test_document_segmenter.py`):
  - 12 tests: segmentación estándar, fallback, formulario skip, context_multiplier,
    pages vacías, texto en sección, start/end page, preamble desconocido,
    detección nula en skip, mitigantes omitidos en restricted,
    detección activa en full, section_id en to_dict()

---

## Estado del roadmap

| Fase | Estado | Notas |
|------|--------|-------|
| Fase 0 | ✅ Completa | Azure OpenAI soportado además de OpenAI directo |
| Fase 1 | ✅ Completa | 12 tests pasan; text_cleaner unificado, ventanas dinámicas, objeto extraído |
| Fase 2 | ✅ Completa | Few-shots, taxonomía filtrada, objeto de contratación en prompt |
| Fase 3 | ✅ Completa | OCR detection, tipo doc, feedback loop, SHA256 taxonomía |
| Fase 4 | ✅ Completa | 8 módulos nuevos, lru_cache, pyproject.toml, 21 tests pasan |
| Fase 5 | ✅ Completa | Segmentador, integración en detector, section_id en outputs, 33 tests pasan |
