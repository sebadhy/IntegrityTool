# Asistente de revisión de neutralidad competitiva en pliegos

Herramienta local para revisores institucionales de contratación pública en Ecuador.
Carga un PDF, detecta cláusulas que podrían limitar concurrencia, las prioriza y las presenta
con evidencia textual. Funciona sin API key; el LLM agrega narrativa cuando está disponible.

> Las señales son insumos preliminares para revisión humana. No constituyen dictamen técnico ni legal.

---

## Instalación

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # editar con credenciales LLM si se desea IA
streamlit run app.py
```

Abre `http://localhost:8501`.

---

## Uso

1. Sube un PDF (pliego, especificaciones técnicas o TDR).
2. Activa **Comparar con corpus histórico** si tienes documentos en `data/raw/`.
3. Activa **Lectura asistida por IA** si configuraste `OPENAI_API_KEY`.
4. Presiona **Iniciar revisión asistida**.
5. Navega por tres pestañas:
   - **Resumen** — métricas, top señales, síntesis IA con áreas de atención y posibles falsos positivos/negativos.
   - **Señales** — señales agrupadas por tema, dimensión competitiva y preguntas sugeridas.
   - **Exportar** — tabla completa, CSV y reporte Markdown.

---

## Configuración `.env`

```env
# LLM (opcional — OpenAI directo o Azure)
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=               # Azure: https://<recurso>.openai.azure.com/
OPENAI_API_VERSION=            # Azure: 2024-06-01

# Corpus histórico (rutas por defecto — no tocar salvo cambio de ubicación)
APP_CORPUS_METADATA_PATH=data/raw/metadata/procesos.csv
APP_CORPUS_PLIEGOS_DIR=data/raw/pliegos
APP_CORPUS_ESPECIFICACIONES_DIR=data/raw/especificaciones
APP_CORPUS_PROCESSED_DIR=data/processed/extracted_text

# Parámetros (valores por defecto)
APP_MAX_DOCUMENT_CHARS=12000
APP_DEFAULT_CONTEXT_CHARS=260
APP_REPORT_TOP_PRIORITIES=3
APP_LLM_TOP_FINDINGS=5
APP_LLM_BALANCE_ROWS=8
```

---

## Corpus histórico

```
data/raw/
  metadata/procesos.csv          ← índice: process_id, entidad, objeto, fecha, pliego_file, especificaciones_file
  pliegos/                       ← PDFs de pliegos (*_PLIEGO.pdf)
  especificaciones/              ← PDFs de especificaciones (*_ESPECIFICACIONES.pdf)
```

Para agregar un proceso: copia los PDFs en sus carpetas y agrega una fila en `procesos.csv`.

---

## Cómo funciona

```
PDF → extracción por página → segmentación en secciones → detección por taxonomía YAML
    → comparación con corpus → priorización → síntesis IA (opcional) → UI + exportación
```

La taxonomía vive en `src/analyzer/patterns/risk_taxonomy.yaml` — editable sin tocar Python.
17 patrones: especificaciones cerradas, presencia local, plazos restrictivos, requisitos acumulativos, etc.

---

## Tests

```bash
pytest
```

33 tests: taxonomía, detección contextual, priorización, segmentación, pipeline E2E.
