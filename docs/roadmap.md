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
Fase 0 — Arranca y corre        ~1 hora        Capa 1 completa
Fase 1 — Calidad de reglas      ~1 jornada     Capa 2: items 7 y 8
Fase 2 — Calidad del LLM        ~1 jornada     Capa 2: items 4, 5 y 6
Fase 3 — Robustez operativa     ~2 jornadas    Capa 3 seleccionada
Fase 4 — Arquitectura           ongoing        Capa 3 resto
```

Fase 1 y Fase 2 son independientes entre sí y se pueden trabajar en paralelo.

---

## Fase 0 — Arranca y corre

**Objetivo:** cualquier persona puede clonar, configurar y ejecutar la app con LLM funcionando en menos de 10 minutos.

**Condición de salida:** `test_llm_connection()` retorna `True` en un entorno limpio con solo `OPENAI_API_KEY` configurada.

### Tareas

- [ ] **0.1** Corregir `DEFAULT_MODEL = "gpt-4o-mini"` en `llm_reviewer.py:29`
- [ ] **0.2** Completar `.env.example` con las tres variables:
  ```
  OPENAI_API_KEY=sk-...
  OPENAI_MODEL=gpt-4o-mini
  OPENAI_BASE_URL=   # vacío para OpenAI directo; URL del proveedor alternativo si aplica
  ```
- [ ] **0.3** Mejorar `test_llm_connection()` para verificar que el modelo responde exactamente "OK", no cualquier texto no vacío
- [ ] **0.4** Crear estructura de corpus de muestra con datos ficticios:
  - `data/corpus/pdfs/` — carpeta vacía con `.gitkeep`
  - `data/corpus/metadata/procesos.csv` — 5 procesos ficticios con todos los campos requeridos (process_id, entidad, año, tipo_proceso, objeto, categoria, pliego_file, especificaciones_file)

---

## Fase 1 — Calidad del análisis de reglas

**Objetivo:** el análisis sin LLM (reglas + taxonomía + corpus) produce fragmentos textuales limpios, detecta mitigantes que hoy pierde por acentos o ventana corta, y prioriza de forma consistente entre módulos.

**Condición de salida:** un pliego con "marca X o equivalente funcional" detecta el mitigante correctamente; los fragmentos exportados al CSV son legibles en Excel sin caracteres raros.

### Tareas

- [ ] **1.1** Crear `src/analyzer/text_cleaner.py` con:
  - `clean_page_text(raw_text: str) -> str` — une líneas rotas por guión, quita whitespace múltiple, normaliza unicode NFKC
  - `normalize_for_matching(text: str) -> str` — para uso interno del detector; maneja acentos + lowercase + whitespace
  - Reemplazar `normalize_text()` en `detector.py:910` por llamada a `text_cleaner.normalize_for_matching()`
  - Reemplazar `_normalized_text()` en `prioritizer.py:349` por la misma función

- [ ] **1.2** Ajustar `context_chars` por tipo de patrón en `detector.py`:
  - Patrones de marca/equivalencia: 500 chars (hoy 260)
  - Patrones de presencia local/experiencia: 420 chars
  - Patrones de completitud documental: 180 chars (son señales puntuales)
  - Default: 260 chars sin cambio

- [ ] **1.3** Agregar `extract_contract_object(pages: list[PageText]) -> str` en `pdf_extractor.py`:
  - Buscar en las primeras 3 páginas con patrones como "objeto de la contratación", "adquisición de", "contratación de"
  - Retornar el fragmento extraído (máx 300 chars) o `"No identificado en las primeras páginas"`
  - No inyectar aún en el LLM — eso es Fase 2

- [ ] **1.4** Limpiar texto antes de exportar a CSV: un paso de `clean_page_text()` sobre el campo `fragmento textual` al construir el export (no alterar el dato original en el DataFrame, solo en la exportación)

---

## Fase 2 — Calidad del LLM

**Objetivo:** el análisis asistido produce outputs útiles, consistentes y calibrados al dominio ecuatoriano. El modelo sabe para quién escribe y tiene ejemplos de lo que se espera.

**Condición de salida:** la explicación de una señal "marca sin equivalente" en un pliego de equipos incluye una pregunta sobre el expediente técnico y no usa lenguaje acusatorio.

### Tareas

- [ ] **2.1** Agregar descripción del lector objetivo al `SYSTEM_PROMPT`:
  - "El lector es un técnico institucional sin formación legal que necesita decidir qué cláusulas revisar en los próximos 30 minutos. Escribe de forma concisa y orientada a decisión."

- [ ] **2.2** Implementar `_relevant_taxonomy_context(finding: dict) -> dict` que filtra la taxonomía al patrón relevante + sus `related_patterns` (ver `docs/llm_prompts_fewshots_and_context.md` sección 2.3). Reemplazar `taxonomy_context(limit=6)` en `_build_finding_prompt()`.

- [ ] **2.3** Agregar los 4 few-shots como constantes en `llm_reviewer.py` (están escritos en `docs/llm_prompts_fewshots_and_context.md` sección 3):
  - `FEWSHOT_MARCA_SIN_EQUIVALENTE`
  - `FEWSHOT_MARCA_CON_EQUIVALENTE`
  - `FEWSHOT_REQUISITO_HABITUAL`
  - `FEWSHOT_PRESENCIA_LOCAL`

- [ ] **2.4** Implementar `_select_few_shots(finding: dict) -> str` — selección dinámica:
  - `requisito_habitual` → `FEWSHOT_REQUISITO_HABITUAL`
  - `brand` en pattern_id + sin mitigantes → `FEWSHOT_MARCA_SIN_EQUIVALENTE`
  - `brand` en pattern_id + con mitigantes → `FEWSHOT_MARCA_CON_EQUIVALENTE`
  - `local` en pattern_id → `FEWSHOT_PRESENCIA_LOCAL`
  - default → `FEWSHOT_MARCA_SIN_EQUIVALENTE`

- [ ] **2.5** Conectar `extract_contract_object()` (de Fase 1) al prompt del brief — reemplaza la línea hardcodeada en `llm_reviewer.py:275`. Requiere pasar el objeto como parámetro a `generate_document_brief()` y a `cached_generate_document_brief()` en `app.py`.

---

## Fase 3 — Robustez operativa

**Objetivo:** la app se comporta bien con los PDFs reales que llegan del SERCOP, incluyendo los casos problemáticos más frecuentes.

### Tareas

- [ ] **3.1** Detección de páginas que necesitan OCR:
  - Agregar `page_needs_ocr(page) -> bool` en `pdf_extractor.py` — detecta páginas con imágenes pero sin texto
  - Exponer el conteo de páginas sin texto en `validate_extracted_pages()` con mensaje más preciso
  - Por ahora: solo detectar y avisar. La integración de OCR real es 3.2.

- [ ] **3.2** Integración OCR opcional con `pytesseract` (idioma `spa`):
  - Agregar como dependencia opcional en `requirements-dev.txt`
  - Si `pytesseract` no está instalado, degradar gracefully con warning
  - Aplicar solo a páginas donde `page_needs_ocr()` es True

- [ ] **3.3** Detección del tipo de documento:
  - Agregar `detect_document_type(pages: list[PageText]) -> str` — heurística por señales textuales en primeras páginas
  - Tipos: `"pliego"`, `"especificaciones_tecnicas"`, `"terminos_referencia"`, `"contrato"`, `"desconocido"`
  - Incluir el tipo detectado en los metadatos del análisis y en el CSV exportado

- [ ] **3.4** Feedback loop — capturar juicio del revisor:
  - Agregar tres botones en `render_finding_explanation()`: "Señal confirmada / Descartada / Necesita más contexto"
  - Grabar en `data/feedback/cases.jsonl`: pattern_id, signal_type, has_mitigants, rarity, fragment (anonimizado), verdict, timestamp
  - No procesar automáticamente los casos aún — el valor está en acumularlos para revisión manual y selección de nuevos few-shots

- [ ] **3.5** Hash SHA256 de taxonomía activa en los hallazgos exportados:
  - Calcular al cargar la taxonomía en `taxonomy_loader.py`
  - Incluir en los campos de trazabilidad del `prioritizer.py` junto a `engine_version` y `rule_version`

---

## Fase 4 — Arquitectura

**Objetivo:** el código soporta crecimiento sin deuda acumulada. Esta fase no cambia funcionalidad.

### Tareas

- [ ] **4.1** Separar `app.py` en módulos:
  - `src/ui/header.py` — `render_institutional_header()`, `render_pipeline()`
  - `src/ui/findings.py` — `render_aspect_card()`, `render_top_priorities()`, `render_theme_groups()`
  - `src/ui/briefing.py` — `render_briefing()`, `render_ai_document_brief()`, `render_analytical_balance()`
  - `src/ui/export.py` — `ordered_export()`, `build_executive_report_markdown()`
  - `src/pipeline/coordinator.py` — la lógica de `render_review_flow()` sin el renderizado

- [ ] **4.2** Reemplazar `_TAXONOMY_CACHE` global mutable por `@st.cache_resource` en `detector.py`

- [ ] **4.3** Separar dependencias:
  - Mover `pytest` de `requirements.txt` a `requirements-dev.txt`
  - Agregar `pyproject.toml` con configuración mínima de pytest y rutas de importación

- [ ] **4.4** Test de integración end-to-end:
  - Un PDF de muestra (texto embebido, sin OCR necesario) en `tests/fixtures/`
  - Test que corre el pipeline completo: extracción → detección → enriquecimiento → priorización → assert que hay al menos un hallazgo con los campos de trazabilidad completos

---

## Estado del roadmap

| Fase | Estado | Bloqueantes |
|------|--------|-------------|
| Fase 0 | Pendiente | — |
| Fase 1 | Pendiente | Fase 0 |
| Fase 2 | Pendiente | Fase 1 (item 2.5 depende de 1.3) |
| Fase 3 | Pendiente | Fase 1 y Fase 2 |
| Fase 4 | Pendiente | Fase 3 |
