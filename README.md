# Asistente exploratorio de neutralidad competitiva en pliegos

Aplicación exploratoria local para apoyar la revisión humana de neutralidad competitiva en pliegos de contratación pública.

La herramienta ayuda a priorizar y contextualizar señales preliminares de restricción competitiva, requisitos potencialmente limitantes, baja neutralidad competitiva y condiciones que podrían reducir concurrencia.

Las señales identificadas son insumos preliminares para revisión humana de neutralidad competitiva. No constituyen dictamen técnico, legal ni determinación de responsabilidad.

## Stack

- Python
- Streamlit
- PyMuPDF
- pandas
- OpenAI API compatible
- python-dotenv

## Estructura

```text
.
├── assets
│   └── styles.css
├── app.py
├── data
│   ├── raw
│   │   ├── metadata
│   │   │   └── procesos.csv
│   │   ├── pliegos
│   │   └── especificaciones
│   └── processed
│       └── extracted_text
├── requirements.txt
├── README.md
└── src
    └── analyzer
        ├── corpus_loader.py
        ├── corpus_validator.py
        ├── __init__.py
        ├── detector.py
        ├── llm_reviewer.py
        ├── normative_reference.py
        ├── pdf_extractor.py
        ├── prioritizer.py
        └── review_synthesis.py
```

## Instalación local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Ejecución

```bash
streamlit run app.py
```

Luego abre:

```text
http://localhost:8501
```

## Enfoque analítico

La interfaz se presenta como:

```text
Asistente exploratorio de neutralidad competitiva en pliegos
```

Subtítulo:

```text
Identificación preliminar de requisitos potencialmente limitantes en documentos de contratación pública
```

La herramienta ayuda a responder:

```text
¿Qué condiciones del pliego podrían requerir validación de proporcionalidad o revisión humana sugerida por posible efecto sobre concurrencia?
```

La experiencia principal está organizada como una lectura vertical tipo briefing institucional. Los controles analíticos principales se mantienen en la vista central:

- carga del documento
- selección de comparación con corpus histórico
- activación de lectura asistida por IA
- pipeline visual
- lectura preliminar
- criterios de lectura
- temas sugeridos para revisión
- evidencia documental

La barra lateral queda reservada para configuración técnica opcional, como `Test LLM`.

## Flujo de briefing institucional

Al cargar un PDF, la app muestra un pipeline visual:

1. Extracción documental
2. Identificación de cláusulas
3. Comparación histórica
4. Consolidación analítica
5. Lectura asistida por IA

La vista principal prioriza comprensión antes que tabla técnica:

- lectura preliminar asistida por IA, si está configurada
- resumen ejecutivo basado en reglas y comparación documental
- balance analítico entre factores de revisión, mitigantes y requisitos habituales
- Top 3 aspectos prioritarios sugeridos para revisión
- temas agrupados en bloques expandibles
- evidencia textual y criterios normativos por señal
- exportación CSV y reporte ejecutivo en Markdown

## Categorías de revisión

- Autorizaciones comerciales o de fabricante
- Referencias a marca, origen o fabricante
- Certificaciones específicas
- Requisitos técnicos cerrados
- Garantías, repuestos y postventa
- Restricciones geográficas o de presencia local
- Experiencia o capacidad excesivamente específica
- Combinaciones de requisitos potencialmente limitantes
- Completitud y trazabilidad documental
- Requisitos regulatorios o habituales
- Elementos que favorecen concurrencia

## Evaluación contextual

El motor ya no trata toda coincidencia textual como señal prioritaria. Cada detección se clasifica con `tipo_señal`:

- `señal_revision`: aspecto que podría requerir revisión humana por posible impacto sobre concurrencia.
- `mitigante_concurrencia`: elemento que favorece apertura competitiva o reduce una lectura cerrada.
- `requisito_habitual`: requisito regulatorio, administrativo o estándar que no se prioriza por sí solo.

Ejemplos de requisitos regulatorios o habituales:

- RUP
- capacidad legal
- domicilio fiscal
- asociaciones y consorcios
- personas naturales o jurídicas
- documentación administrativa estándar

Estos requisitos no suben atención automáticamente y no aparecen en el Top 3 salvo que una combinación contextual específica justifique revisión.

Ejemplos de mitigantes:

- aceptación de equivalentes funcionales
- participación mediante consorcios
- apertura a oferentes nacionales y extranjeros
- marcas equivalentes
- criterios funcionales en vez de referencias cerradas

Los mitigantes reducen la atención contextual de señales relacionadas y se muestran como aspectos que favorecen apertura competitiva.

## Capa normativa orientativa

La herramienta incluye una capa simple de referencia normativa para alinear las observaciones con principios y reglas relevantes de contratación pública en Ecuador.

Principios y criterios considerados:

- concurrencia
- igualdad y no discriminación
- trato justo
- transparencia
- mejor valor por dinero
- claridad, completitud y no ambigüedad de especificaciones
- especificaciones relacionadas con bienes/rubros y no con proveedores
- necesidad de justificación técnica o jurídica cuando un requisito pueda limitar competencia
- consistencia entre pliego y anexos
- uso adecuado de CPC

Por cada señal sugerida para revisión, la app agrega:

- `principio_normativo_relacionado`
- `criterio_normativo_de_revision`
- `pregunta_normativa_sugerida`

La referencia normativa incluida es orientativa y sirve para apoyar revisión humana. No constituye interpretación legal oficial ni reemplaza el análisis jurídico o técnico de la entidad competente.

Fuentes de referencia:

- LOSNCP, disponible en el portal normativo del SERCOP: https://portal.compraspublicas.gob.ec/sercop/normativa/
- RLOSNCP, disponible en el portal normativo del SERCOP: https://portal.compraspublicas.gob.ec/sercop/normativa/
- Resoluciones SERCOP vigentes y régimen de transición, cuando aplique: https://portal.compraspublicas.gob.ec/sercop/cat_normativas/nor_res_ext

## Salida principal

Cada señal sugerida para revisión incluye:

- `signal_id`
- `rule_id`
- `rule_version`
- `timestamp_analisis`
- `engine_version`
- `tipo_señal`
- tema de revisión
- página
- categoría de revisión
- patrón detectado
- atención sugerida
- relevancia analítica
- criterios de priorización
- explicación de priorización
- clasificación histórica
- frecuencia en corpus
- procesos con patrón
- posible efecto sobre concurrencia
- validación sugerida
- principio normativo relacionado
- criterio normativo de revisión
- pregunta normativa sugerida
- por qué se sugiere revisar
- posible justificación legítima
- fragmento textual

## Priorización

El módulo `src/analyzer/prioritizer.py` agrega una priorización explicable. No calcula un indicador acusatorio; organiza señales para responder qué revisar primero y por qué.

Campos principales:

- `nivel_atencion`: Bajo, Medio o Alto
- `relevancia_analitica`: Bajo, Medio o Alto
- `criterios_de_priorizacion`: razones concretas usadas por el motor
- `explicacion_priorizacion`: síntesis prudente para revisión humana

La atención sugerida combina:

- frecuencia histórica del patrón
- concentración de señales relacionadas
- nivel de atención base de la regla
- presencia de combinaciones potencialmente limitantes
- presencia en secciones críticas
- número de coincidencias
- completitud documental y referencias a anexos externos
- criterios normativos asociados
- factores mitigantes identificados en el documento

No se priorizan requisitos regulatorios estándar como RUP, domicilio fiscal, capacidad legal o fórmulas generales de participación, salvo combinación contextual específica.

La atención sube cuando aparecen combinaciones como:

- autorización comercial o de fabricante + certificación específica
- marca/fabricante + requisito técnico cerrado
- distribuidor autorizado + garantía/postventa
- certificación específica + baja frecuencia en corpus
- requisito técnico cerrado + baja frecuencia histórica

## Niveles de atención

- **Alto:** conviene revisar primero por baja frecuencia, acumulación de condiciones, combinación de requisitos o posible impacto relevante sobre concurrencia.
- **Medio:** requiere validación de proporcionalidad, justificación técnica o equivalencias disponibles.
- **Bajo:** señal habitual o de menor concentración; se mantiene como apoyo documental y puede adquirir relevancia si aparece combinada con otros requisitos.

## Corpus histórico integrado

La comparación histórica se integra automáticamente en cada señal sugerida para revisión.

La herramienta prioriza trazabilidad documental, reproducibilidad y auditabilidad por encima de conveniencia automática. Por defecto no realiza matching por similitud, coincidencias parciales ni inferencias por `process_id`.

Estructura esperada:

```text
data/
  raw/
    metadata/
      procesos.csv
    pliegos/
    especificaciones/
  processed/
    extracted_text/
```

`data/raw/metadata/procesos.csv` debe incluir:

```text
process_id
entidad
objeto
fecha
pliego_file
especificaciones_file
```

## Convención obligatoria de nombres

Los campos `pliego_file` y `especificaciones_file` deben apuntar al nombre del PDF ubicado en la carpeta exacta correspondiente:

- `pliego_file` se busca solo en `data/raw/pliegos/`
- `especificaciones_file` se busca solo en `data/raw/especificaciones/`

Normalización estricta aplicada por `normalize_filename()`:

- elimina espacios iniciales y finales
- elimina dobles espacios
- reemplaza espacios por `_`
- elimina caracteres invisibles
- convierte el nombre base a mayúsculas de forma consistente
- normaliza la extensión como `.pdf`

Ejemplos válidos:

```text
process_id,pliego_file,especificaciones_file
SIE-EMASEO-EP-2026-006,SIE-EMASEO-EP-2026-006_PLIEGO.pdf,SIE-EMASEO-EP-2026-006_ESPECIFICACIONES.pdf
LICB-EMASEO-EP-2025-001,LICB-EMASEO-EP-2025-001_PLIEGO.pdf,LICB-EMASEO-EP-2025-001_ESPECIFICACIONES.pdf
```

Errores comunes:

- declarar un PDF en `procesos.csv` que no existe físicamente
- ubicar especificaciones en la carpeta de pliegos o al revés
- usar extensión distinta de `.pdf`
- repetir `process_id`
- referenciar el mismo PDF en más de un proceso
- dejar campos obligatorios vacíos
- dejar PDFs en carpetas del corpus sin correspondencia en `procesos.csv`

## Validación documental del corpus

El módulo `src/analyzer/corpus_validator.py` valida antes de cargar documentos:

- PDFs faltantes
- nombres inconsistentes
- `process_id` duplicados
- documentos repetidos
- extensiones inválidas
- metadata incompleta
- archivos huérfanos
- documentos sin correspondencia CSV

La app muestra la sección `Estado del corpus documental` con:

- total de documentos esperados
- encontrados
- faltantes
- inconsistencias
- duplicados
- errores de naming

La tabla de validación incluye:

- `process_id`
- `tipo_documento`
- `archivo_esperado`
- `archivo_encontrado`
- `estado_validacion`
- `observacion`

Estados posibles:

- `OK`
- `No encontrado`
- `Nombre inconsistente`
- `Duplicado`
- `Metadata incompleta`
- `Coincidencia ambigua`
- `Documento sin correspondencia CSV`

Si el corpus tiene errores críticos como PDF faltante, coincidencia ambigua, duplicados graves o metadata incompleta, la app bloquea la comparación histórica y muestra:

```text
El corpus presenta inconsistencias documentales que podrían afectar la trazabilidad y confiabilidad del análisis.
```

Los PDFs huérfanos se reportan, pero no se cargan automáticamente.

Cada documento cargado guarda trazabilidad:

- `document_id`
- `process_id`
- path exacto
- filename original
- filename normalizado
- SHA256
- timestamp de carga
- tamaño del archivo

El cache incremental se reutiliza solo si el SHA256 del PDF coincide con el registro procesado.

Para agregar nuevos procesos:

1. Copia el PDF del pliego en `data/raw/pliegos/`.
2. Copia el PDF de especificaciones técnicas en `data/raw/especificaciones/`, si existe.
3. Actualiza `data/raw/metadata/procesos.csv`.
4. Ejecuta nuevamente la revisión desde la app.

La ingesta es incremental. Por cada documento procesado se crea un JSON en:

```text
data/processed/extracted_text/
```

## Lectura asistida por IA

La capa de IA generativa es opcional. Si no configuras una API key, la app sigue funcionando con reglas, comparación documental, filtros y exportación CSV.

Para configurarla:

```bash
export OPENAI_API_KEY="tu_api_key"
streamlit run app.py
```

También puedes crear un archivo `.env`:

```text
OPENAI_API_KEY=tu_api_key
OPENAI_MODEL=gpt-5.4-mini
```

Si usas un proveedor compatible:

```text
OPENAI_BASE_URL=https://tu-proveedor-compatible.example/v1
OPENAI_MODEL=nombre-del-modelo
```

En la app:

- usa `Test LLM` para verificar conexión
- marca `Activar lectura asistida por IA` para generar la lectura preliminar
- usa `Generar explicación asistida por IA` en una señal puntual si necesitas una explicación adicional

La lectura asistida por IA:

- usa máximo 12.000 caracteres del documento
- prioriza fragmentos vinculados a señales sugeridas
- recibe señales priorizadas, categorías, atención sugerida y frecuencias comparativas
- recibe mitigantes y requisitos habituales como contexto de balance
- recibe criterios normativos orientativos curados
- no debe proponer señales nuevas sin soporte en el análisis previo
- usa la capa normativa como referencia prudente, sin emitir dictámenes legales
- debe distinguir requisitos habituales, señales atípicas y elementos que favorecen concurrencia

Funciones principales:

- `generate_document_brief(document_text, prioritized_findings, corpus_context, normative_context)`
- `explain_priority_with_llm(priority)`

La salida del brief incluye:

- resumen del documento
- nivel general de atención
- principales temas de revisión
- posibles efectos sobre concurrencia
- contexto comparativo
- razones de las prioridades principales
- preguntas sugeridas para revisión humana
- nota metodológica

## Exportaciones

La app permite descargar:

- CSV con señales consolidadas, priorización, trazabilidad, contexto histórico y criterios normativos.
- Reporte ejecutivo en Markdown con lectura preliminar, Top 3 prioridades, señales agrupadas, evidencia textual, nota metodológica y advertencia institucional.

## Validaciones y control

La app muestra mensajes comprensibles cuando detecta:

- PDF sin texto seleccionable
- páginas sin texto extraído
- OCR requerido, no disponible en esta versión
- metadata de corpus faltante
- PDFs del corpus no encontrados
- API key no configurada
- error o timeout del proveedor LLM

## Advertencia institucional

Las señales identificadas son insumos preliminares para revisión humana de neutralidad competitiva. No constituyen dictamen técnico, legal ni determinación de responsabilidad.

## Limitaciones

- Usa reglas textuales y comparación documental exploratoria.
- No reemplaza análisis técnico, jurídico ni operativo.
- La capa IA puede fallar por falta de credenciales, red, cuota o respuesta inválida.
- PDFs escaneados podrían requerir OCR en una versión posterior.
