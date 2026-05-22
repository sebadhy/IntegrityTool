# Asistente exploratorio de neutralidad competitiva en pliegos — Branch `fusion`

Aplicación local para apoyar la revisión humana de neutralidad competitiva en pliegos de contratación pública de Ecuador.

> **Branch `fusion`**: integración de lo mejor de los branches `Andres`, `Sebastian` y `Vladimiro`, con correcciones y mejoras adicionales. Los tres branches originales se conservan sin modificación.

---

## Qué aportó cada branch

### Branch `Sebastian`
Base técnica principal adoptada en `fusion`:

- **Pipeline clause-centric**: PDF → parse → segment → extract_clauses → boilerplate_filter → detect_signals → contextualize → consolidate → relevance_filter → prioritize → ReviewItems
- **`observation_filter.py`**: agrupa hallazgos por `(pattern_id + competition_dimension + signal_type)`, cuenta ocurrencias, vincula páginas relacionadas y aplica visibility scoring
- **Suite de 47 tests** que cubre taxonomía, mitigantes, señales contextuales, priorización y control de lenguaje
- Arquitectura modular con separación clara entre detección, consolidación, priorización y renderizado

### Branch `Andres`
Capacidades de modo agente adoptadas en `fusion`:

- **`agent.py` / `agent_runner.py`**: modo batch para procesar múltiples pliegos sin interfaz Streamlit
- **`db.py`**: persistencia en SQL Server vía pyodbc; campo allowlist `_AGENT_RUN_UPDATABLE_FIELDS` para prevenir inyección SQL en UPDATE dinámico
- **`notifier.py`**: envío de alertas por email SMTP con informe HTML de hallazgos
- **`tools.py`**: herramientas de agente para extracción de texto y detección de patrones
- **`pages/Ayuda.py`**: página de ayuda integrada en Streamlit
- **Soporte Groq**: `GROQ_API_KEY` y `GROQ_MODEL` para usar `llama-3.3-70b-versatile` u otros modelos del ecosistema Groq
- **OCR con Tesseract** (`pdf_extractor.py`): extractor enriquecido con fallback OCR para PDFs escaneados; si Tesseract no está instalado marca páginas como `requires_ocr` sin interrumpir el análisis

### Branch `Vladimiro`
Experiencia de usuario y capa LLM adoptadas en `fusion`:

- **Few-shots en el prompt LLM**: `_FEWSHOT_MARCA_SIN_EQUIVALENTE` y `_FEWSHOT_MARCA_CON_EQUIVALENTE` para calibrar la lectura asistida
- **Encabezado de documento con resumen analítico**: señales Alto/Medio/Bajo, temas principales y objeto del proceso visibles desde el primer pantallazo
- **UI en tabs**: organización de la vista de resultados por pestañas
- **CSS limpio y variables definidas**: primera versión con `--surface`, `--shadow-soft`, `--text-muted` en `:root`
- **Configuración flexible por env**: `OPENAI_BASE_URL`, `OPENAI_MODEL` y fallback seguro cuando no hay LLM configurado

---

## Qué se mejoró en `fusion`

### Soporte multi-proveedor LLM
- Cadena de detección automática: **Azure OpenAI → Groq → Ollama → OpenAI directo**
- Variable `LLM_PROVIDER` para forzar proveedor: `groq`, `azure`, `ollama`, `openai`
- `_forced_provider()` correctamente conectado a `_use_azure/groq/ollama/openai()`
- `_response_format()`: esquema `json_schema` (strict) para cloud, `json_object` para Ollama
- `_call_with_retry()`: backoff exponencial, MAX_RETRIES=4, BASE_DELAY=2.0 para rate limit 429
- `test_llm_connection()` usado consistentemente (antes solo se chequeaba `OPENAI_API_KEY`)
- `src/config.py` con `GROQ_MODEL`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`

### Pipeline correctamente cableado
- `observation_filter.prepare_visible_review_items()` existía en Sebastian pero **nunca se llamaba**; ahora está integrado en `review_pipeline.py` y se retorna como `enriched_df`
- `tools.py` (Andres): `detect_patterns()` ahora usa el pipeline clause-centric completo igual que la UI, en vez de una función separada que fue removida

### Refactor de utilidades duplicadas
- **`src/analyzer/text_utils.py`** (nuevo): `unique_strings`, `list_field`, `normalize_text_es`, `is_substantive_evidence_text`, `has_concrete_requirement_detail`, `looks_like_structural_text` — antes duplicadas en 6+ módulos del pipeline
- **`src/analyzer/review_row_schema.py`** (nuevo): constantes para todos los nombres de campo del row (`SIGNAL_ID`, `PATTERN_NAME`, `REVIEW_PRIORITY_LABELS`, `HISTORY_ORDER`, etc.) con fuente única
- Eliminadas `_unique()`, `_escalation_factors()`, `_catalog_severity()` locales de `detector.py` y equivalentes en `consolidator`, `prioritizer`, `observation_filter`, `mitigants`

### CSS consolidado
- Eliminadas 2 definiciones duplicadas de `:root` → 1 bloque unificado con todas las variables
- Eliminadas 3 definiciones de `.block-container` → 1 definitiva: `max-width: 1180px; padding: 0.85rem 2rem 3rem`
- Eliminadas 2 definiciones de `h2, h3` → 1 sin border-bottom (limpia; `.section-heading` maneja sus separadores)
- Eliminadas 2 definiciones de `.document-header-simple` → 1 consolidada con `border-radius: 6px` y `box-shadow`
- Eliminada segunda definición de `.top-finding-card` que sobreescribía el borde de color azul
- Eliminada segunda definición de `.evidence-snippet` que destruía la paleta dorada de evidencia
- Añadidas variables `--surface-muted: #F8FAFC` y `--text-muted: #5F6B76` al `:root` principal

### OCR para PDFs escaneados
- `pdf_extractor.py` reemplazado por la versión de Andres con soporte Tesseract
- Flujo: PyMuPDF primero → si página < 100 chars intenta OCR (español + inglés, 300 DPI) → si Tesseract no está instalado marca `requires_ocr` y sigue sin crashear
- `PageStatus` enum: `OK`, `OCR_OK`, `OCR_FAILED`, `REQUIRES_OCR`, `EMPTY`
- `ExtractionResult`: metadata completa de extracción (totales, páginas con OCR, disponibilidad de Tesseract)
- `check_tesseract_setup()`: diagnóstico con instrucciones de instalación por OS
- API 100% compatible: `extract_text_by_page()` sigue retornando `list[PageText]`; los campos nuevos tienen defaults
- Instalación: `pip install pytesseract Pillow` + binario del sistema (`brew install tesseract tesseract-lang` / `apt install tesseract-ocr tesseract-ocr-spa`)

### Envío de informe por email desde la UI
- Panel **"Compartir por email"** al pie de los resultados, junto al export CSV
- Campo de destinatarios (uno o varios separados por coma) + botón "Enviar informe"
- Si `SMTP_USER`/`SMTP_PASSWORD` no están en `.env`: muestra hint amigable con instrucciones, no bloquea
- Si están configurados: envía informe HTML con nivel de atención, resumen, temas y top 3 hallazgos
- Usa `notifier.send_alert_email()` — compatible con Gmail (contraseña de app) y cualquier servidor SMTP con TLS
- También disponible en modo batch desde `agent.py`

### UX y experiencia de uso
- **Barra de navegación integrada** (`render_review_nav`): reemplaza el botón "Nueva revisión" flotante y desconectado por una barra horizontal con nombre del documento y botón `← Nueva revisión` a la derecha
- `render_methodological_limitations()` se mueve **antes** de los hallazgos (entre resumen y aspectos sugeridos) para que el usuario vea el alcance antes de los resultados
- Expander "Qué revisa la herramienta" abre `expanded=True` por defecto
- Resultado vacío cambia de `st.success` a `st.info` (semánticamente correcto)
- Explicación de **Alto / Medio / Bajo** visible en el encabezado de la sección de hallazgos
- Texto "PoC" eliminado → "herramienta exploratoria"
- Negrita en `matched_text` dentro de ocurrencias relacionadas (`_highlight_matched`)
- Hover de expanders y file uploader con fondo claro (override `!important` sobre dark mode de Streamlit)

### Seguridad
- `db.py`: `_AGENT_RUN_UPDATABLE_FIELDS` (frozenset) valida nombres de columna antes de UPDATE dinámico
- `agent.py`: usa `GROQ_MODEL` desde `src/config` en vez de hardcoded
- `.env.example` documenta los 4 proveedores con instrucciones comentadas

---

## Stack

- Python 3.11+
- Streamlit
- PyMuPDF (fitz)
- pandas
- openai (compatible con Azure, Groq, Ollama y OpenAI directo)
- groq >= 0.11.0
- python-dotenv
- pytesseract + Pillow (OCR opcional, requiere binario `tesseract` en el sistema)
- pyodbc (modo agente batch, opcional)

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# editar .env con las credenciales del proveedor LLM elegido
```

## Ejecución

```bash
streamlit run app.py
```

Con proveedor específico:

```bash
LLM_PROVIDER=groq streamlit run app.py
LLM_PROVIDER=ollama streamlit run app.py
LLM_PROVIDER=azure streamlit run app.py
```

## Proveedores LLM soportados

| Proveedor | Variables requeridas | Modelo por defecto |
|-----------|---------------------|-------------------|
| Azure OpenAI | `OPENAI_API_KEY` + `OPENAI_BASE_URL` + `OPENAI_API_VERSION` | `gpt-4o` |
| Groq | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |
| Ollama | `OLLAMA_BASE_URL` o `OLLAMA_MODEL` | `llama3.1` |
| OpenAI directo | `OPENAI_API_KEY` | `gpt-4o` |

Forzar proveedor: `LLM_PROVIDER=groq` (o `azure`, `ollama`, `openai`).

## Tests

```bash
pytest
# 47 tests — todos deben pasar
```

## Envío de informe por email

Configurar en `.env`:

```text
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=tu_cuenta@gmail.com
SMTP_PASSWORD=xxxx_xxxx_xxxx_xxxx   # contraseña de app Gmail, no la normal
SMTP_FROM=tu_cuenta@gmail.com
```

Desde la UI: al pie de los resultados, expander **"Compartir por email"** → ingresar destinatarios → "Enviar informe".

Desde modo batch: `agent.py` envía alertas automáticamente cuando detecta señales de alta atención.

## OCR para PDFs escaneados

Instalar Tesseract en el sistema:

```bash
# Mac
brew install tesseract tesseract-lang

# Linux
sudo apt install tesseract-ocr tesseract-ocr-spa

# Windows
# https://github.com/UB-Mannheim/tesseract/wiki
```

Sin Tesseract la app funciona igual; las páginas escaneadas se marcan como `requires_ocr` y el resto se analiza normalmente.

## Modo agente (batch)

```bash
python agent_runner.py
```

Procesa lotes de pliegos sin interfaz Streamlit. Requiere SQL Server configurado en `.env`:

```text
DB_SERVER=servidor\instancia
DB_NAME=nombre_base_datos
DB_USER=usuario
DB_PASSWORD=contraseña
```

## Estructura de módulos clave

```text
src/analyzer/
  review_pipeline.py       # orquestador principal
  text_utils.py            # utilidades de texto compartidas (nuevo en fusion)
  review_row_schema.py     # constantes de campos del row (nuevo en fusion)
  detector.py              # detección de señales clause-centric
  observation_filter.py    # deduplicación y visibility scoring
  prioritizer.py           # priorización explicable
  relevance_filter.py      # filtrado de hallazgos relevantes
  consolidator.py          # consolidación de candidatos
  contextualizer.py        # mitigantes y contexto
  llm_reviewer.py          # capa LLM multi-proveedor
  patterns/
    risk_taxonomy.yaml     # taxonomía editable de patrones
```

## Advertencia institucional

Las señales identificadas son insumos preliminares para revisión humana. No constituyen dictamen técnico, legal ni determinación de responsabilidad administrativa.
