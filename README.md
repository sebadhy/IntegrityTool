# Asistente de revisión de neutralidad competitiva en pliegos

Herramienta local de apoyo a la revisión humana de pliegos de contratación pública.
Analiza un PDF, detecta cláusulas que podrían requerir validación de proporcionalidad o
equivalencias, las prioriza por relevancia y las presenta con evidencia textual trazable.

> Las señales identificadas son insumos preliminares para revisión humana. No constituyen
> dictamen técnico, legal ni determinación de responsabilidad.

---

## Para qué sirve

En Ecuador, los revisores institucionales, auditores y analistas de SERCOP necesitan identificar
rápidamente qué cláusulas de un pliego podrían limitar la concurrencia de oferentes —
especificaciones técnicas cerradas, autorizaciones de fabricante, requisitos de presencia local,
plazos restrictivos, requisitos acumulativos, etc.

Esta herramienta:

- **Prioriza** qué revisar primero en 30 minutos, no en 3 horas.
- **Contextualiza** cada señal con evidencia textual, sección del documento y frecuencia histórica en corpus.
- **No acusa**: usa lenguaje prudente orientado a decisión, sin atribuir intencionalidad.
- **Es trazable**: cada hallazgo incluye `pattern_id`, `section_id`, `taxonomy_sha256` y página.
- **Es opcional en IA**: funciona completamente sin API key; el LLM solo agrega narrativa.

---

## Cómo funciona

```
PDF del pliego
     │
     ▼
┌─────────────────────────────────────────┐
│  EXTRACCIÓN (pdf_extractor.py)          │
│  • texto por página (native/ocr/empty)  │
│  • tipo de documento detectado          │
│  • objeto del contrato extraído         │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│  SEGMENTACIÓN (document_segmenter.py)   │
│  • 8 secciones: especificaciones,       │
│    habilitación, formularios, etc.      │
│  • perfil por sección: full/restricted/ │
│    skip (formularios = sin detecciones) │
│  • multiplicador de contexto por sección│
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│  DETECCIÓN (detector.py)                │
│  • taxonomía YAML: 17 patrones          │
│  • reglas deterministas con ventanas    │
│    de contexto dinámicas por patrón     │
│  • mitigantes textuales detectados      │
│    en la misma ventana                  │
└────────┬────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  ENRIQUECIMIENTO (review_synthesis.py)  │
│  • comparación con corpus histórico     │
│  • frecuencia del patrón en corpus      │
│  • clasificación histórica              │
└────────┬────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  PRIORIZACIÓN (prioritizer.py)          │
│  • nivel_atencion, relevancia_analitica │
│  • signal_id, taxonomy_sha256           │
│  • explicación del criterio usado       │
└────────┬────────────────────────────────┘
         │
    ┌────┴─────┐
    │          │
    ▼          ▼
[sin IA]   [con IA — opcional]
    │       llm_reviewer.py
    │       few-shots dinámicos
    │       taxonomía filtrada
    │       contract_object en prompt
    └────┬───┘
         │
         ▼
┌─────────────────────────────────────────┐
│  INTERFAZ (app.py + src/ui/)            │
│  • resumen ejecutivo                    │
│  • top N señales prioritarias           │
│  • señales agrupadas por tema           │
│  • feedback por señal                   │
│  • exportación CSV + Markdown           │
└─────────────────────────────────────────┘
```

---

## Stack

- Python 3.11+
- Streamlit
- PyMuPDF (pymupdf)
- pandas
- OpenAI SDK v2 (OpenAI directo o Azure OpenAI)
- python-dotenv

---

## Instalación

```bash
git clone <repo>
cd tenderdocsreview-main

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## Configuración

Copia `.env.example` como `.env` y completa las variables:

```bash
cp .env.example .env
```

### LLM (obligatorio solo para lectura asistida por IA)

**Opción A — OpenAI directo**
```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=
OPENAI_API_VERSION=
```

**Opción B — Azure OpenAI**
```env
OPENAI_API_KEY=<tu-azure-key>
OPENAI_MODEL=gpt-4o-mini          # nombre del deployment
OPENAI_BASE_URL=https://<recurso>.openai.azure.com/
OPENAI_API_VERSION=2024-06-01
```

### Rutas del corpus (opcional — defecto indicado)

```env
APP_CORPUS_METADATA_PATH=data/raw/metadata/procesos.csv
APP_CORPUS_PLIEGOS_DIR=data/raw/pliegos
APP_CORPUS_ESPECIFICACIONES_DIR=data/raw/especificaciones
APP_CORPUS_PROCESSED_DIR=data/processed/extracted_text
```

### Comportamiento de la aplicación (opcional — defecto indicado)

```env
APP_MAX_DOCUMENT_CHARS=12000       # máx. chars que recibe el LLM por documento
APP_DEFAULT_CONTEXT_CHARS=260      # ventana de contexto por defecto por señal
APP_REPORT_TOP_PRIORITIES=3        # señales prioritarias en UI y reporte
APP_LLM_TOP_FINDINGS=5             # hallazgos enviados al LLM para el brief
APP_LLM_BALANCE_ROWS=8             # mitigantes enviados al LLM como contexto
```

Toda la configuración vive en `src/config.py`, que lee estas variables con los valores por defecto como fallback.

---

## Ejecución

```bash
streamlit run app.py
```

Abre `http://localhost:8501`.

---

## Cómo usar la aplicación

1. **Carga un PDF** — pliego, especificaciones técnicas o términos de referencia.
2. **Activa comparación histórica** si tienes corpus cargado (ver sección siguiente).
3. **Activa lectura asistida por IA** si configuraste credenciales (opcional).
4. Presiona **Iniciar revisión asistida**.
5. Lee el **resumen ejecutivo** y el **balance analítico**.
6. Revisa el **Top N señales prioritarias** — cada una incluye evidencia textual, sección del documento y clasificación histórica.
7. Explora **señales por tema** para contexto adicional.
8. Descarga el **reporte CSV** o el **reporte ejecutivo en Markdown**.

Usa **Confirmar / Descartar / Más contexto** en cada tarjeta para registrar tu juicio en `data/feedback/cases.jsonl`.

---

## Corpus histórico

El corpus habilita la comparación de frecuencias: cuántos procesos anteriores contienen el mismo patrón.

### Estructura esperada

```
data/
  raw/
    metadata/
      procesos.csv          ← índice de procesos
    pliegos/                ← PDFs de pliegos
    especificaciones/       ← PDFs de especificaciones técnicas
  processed/
    extracted_text/         ← cache de texto extraído (generado automáticamente)
```

### `procesos.csv` — campos obligatorios

```
process_id,entidad,objeto,fecha,pliego_file,especificaciones_file
```

`pliego_file` y `especificaciones_file` son solo el nombre del archivo (sin ruta).
El archivo debe estar físicamente en la carpeta correspondiente.

### Convención de nombres

```
SIE-EMASEO-EP-2026-006_PLIEGO.pdf
SIE-EMASEO-EP-2026-006_ESPECIFICACIONES.pdf
```

### Agregar nuevos procesos

1. Copia el PDF del pliego en `data/raw/pliegos/`.
2. Copia el PDF de especificaciones en `data/raw/especificaciones/` (opcional).
3. Agrega una fila en `data/raw/metadata/procesos.csv`.
4. Reinicia la app o recarga en la UI.

La ingesta es incremental y usa SHA256 para evitar reprocesar archivos sin cambios.

---

## Taxonomía de patrones

Los patrones de detección viven en `src/analyzer/patterns/risk_taxonomy.yaml`.
Se pueden editar sin tocar código Python. Cada patrón define:

- `textual_signals` — frases que activan la detección
- `mitigating_factors` — frases que reducen la prioridad si aparecen en el contexto
- `human_review_questions` — preguntas sugeridas para el revisor
- `severity_guidance` — orientación de severidad

El loader valida el YAML y aplica fallback seguro si hay errores parciales.
El campo `taxonomy_sha256` en cada hallazgo exportado identifica la versión activa de la taxonomía.

---

## Módulos principales

| Módulo | Qué hace |
|--------|----------|
| `src/config.py` | Fuente única de configuración — lee `.env` con fallbacks tipados |
| `src/analyzer/pdf_extractor.py` | Extrae texto por página; detecta tipo de documento y objeto del contrato; soporte OCR opcional |
| `src/analyzer/document_segmenter.py` | Segmenta el documento en secciones (especificaciones, habilitación, formularios, etc.); asigna perfil de detección y multiplicador de contexto por sección |
| `src/analyzer/detector.py` | Aplica taxonomía YAML + reglas deterministas; ventanas de contexto dinámicas; respeta perfil de sección (skip/restricted/full) |
| `src/analyzer/prioritizer.py` | Priorización explicable con trazabilidad completa |
| `src/analyzer/llm_reviewer.py` | Cliente LLM (OpenAI/Azure); few-shots dinámicos; taxonomía filtrada por señal; contract_object en prompt |
| `src/analyzer/corpus_loader.py` | Ingesta incremental del corpus con SHA256 y trazabilidad |
| `src/analyzer/taxonomy_loader.py` | Carga y valida `risk_taxonomy.yaml`; calcula `taxonomy_sha256` |
| `src/pipeline/coordinator.py` | Orquesta DataFrame, estado del corpus y contexto para el LLM |
| `src/ui/components.py` | Constantes compartidas y helpers de presentación |
| `src/ui/briefing.py` | Resumen ejecutivo, balance analítico, dimensiones competitivas |
| `src/ui/findings.py` | Tarjetas de señal, Top N prioridades, botones de feedback |
| `src/ui/export.py` | Export CSV ordenado y reporte ejecutivo Markdown |
| `src/ui/cache.py` | Wrappers `@st.cache_data` para LLM y corpus |

---

## Tests

```bash
pytest
```

33 tests cubren: carga de taxonomía, fallback seguro, normalización de texto, detección contextual,
priorización, segmentación por secciones y pipeline E2E (PDF sintético → hallazgos → exportación).

---

## Consideraciones metodológicas

- **El motor detecta señales, no infracciones.** Una cláusula marcada requiere validación humana, no una conclusión automática.
- **Los mitigantes no eliminan una señal, la contextualizan.** "Marca específica o equivalente funcional" sigue marcándose, pero con menor prioridad y con la pregunta sobre si la equivalencia es verificable.
- **Requisitos regulatorios estándar** (RUP, capacidad legal, domicilio fiscal, homologación ANT, normas INEN) se clasifican como `requisito_habitual` y no suben la prioridad salvo combinación contextual específica.
- **Trazabilidad completa**: cada hallazgo exportado incluye `signal_id`, `pattern_id`, `section_id`, `taxonomy_sha256`, `engine_version` y `timestamp_analisis`.

---

## Estructura del proyecto

```
.
├── app.py                          ← orquestador principal (~165 líneas)
├── .env.example                    ← plantilla de configuración
├── src/
│   ├── config.py                   ← fuente única de parámetros
│   ├── analyzer/
│   │   ├── pdf_extractor.py
│   │   ├── document_segmenter.py
│   │   ├── detector.py
│   │   ├── finding_model.py
│   │   ├── text_cleaner.py
│   │   ├── llm_reviewer.py
│   │   ├── prioritizer.py
│   │   ├── review_synthesis.py
│   │   ├── corpus_loader.py
│   │   ├── corpus_validator.py
│   │   ├── taxonomy_loader.py
│   │   ├── normative_reference.py
│   │   └── patterns/
│   │       └── risk_taxonomy.yaml  ← editar aquí para ajustar patrones
│   ├── pipeline/
│   │   └── coordinator.py
│   └── ui/
│       ├── components.py
│       ├── cache.py
│       ├── header.py
│       ├── briefing.py
│       ├── findings.py
│       └── export.py
├── data/
│   ├── raw/
│   │   ├── metadata/procesos.csv
│   │   ├── pliegos/
│   │   └── especificaciones/
│   └── processed/extracted_text/
├── tests/
├── docs/
│   └── roadmap.md
└── assets/styles.css
```

---

## Advertencia institucional

Las señales identificadas son insumos preliminares para revisión humana de neutralidad competitiva.
No constituyen dictamen técnico, legal ni determinación de responsabilidad.
