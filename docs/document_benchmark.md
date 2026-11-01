# Benchmark de extracción documental

Herramienta de evaluación para decidir qué capacidades de extracción incorporar a Integrity Tool. Se ejecuta desde la raíz del repositorio, separada de las revisiones de la aplicación. Conserva entradas, resultados y mediciones; no modifica documentos ni bases de revisiones.

## Qué se compara

| Extractor | Capacidad evaluada | Ejecución |
|---|---|---|
| `current` | Texto y estado OCR del extractor actual | Local |
| `pymupdf-layout` | Bloques, coordenadas y asociación de celdas en PDFs nativos | Local |
| `azure-layout` | Document Intelligence `prebuilt-layout`, API `2024-11-30` | Servicio externo, autorización explícita |
| `docling` | Estructura local con modelos preparados y OCR Tesseract | Entorno aislado |

Los dos primeros usan las dependencias habituales del proyecto. Los adaptadores opcionales tienen pruebas con respuestas representativas; su funcionamiento integral requiere validación con el SDK/modelos y el entorno elegidos. No están conectados al análisis de la aplicación.

## 1. Congelar una muestra

Preparar el entorno de desarrollo según el README e instalar `requirements-dev.txt`. El corpus debe cumplir su convención de nombres y correspondencia exacta con el CSV.

```bash
python -m benchmarks.documents prepare --limit 6 --seed piloto-v1 --output data/benchmark/piloto-v1/manifest.json
```

Selecciona hasta seis procesos, manteniendo juntos pliego y especificaciones. Para una selección explícita, repetir `--process-id IDENTIFICADOR_EXACTO`. `--root` permite indicar otra raíz con la misma estructura `data/raw/`; `--metadata` permite elegir el CSV. La ejecución bloquea inconsistencias críticas, PDFs repetidos y documentos que cambien de hash, tamaño o cantidad de páginas.

El manifiesto incluye proceso, rol documental, ruta relativa, SHA-256 y páginas. Por defecto toda selección es **calibración**, no una muestra independiente. Los documentos de un mismo proceso deben permanecer en la misma partición. La categoría queda pendiente de clasificación humana; la selección automática no garantiza representatividad. El CSV es una fuente declarada, no referencia experta: fechas o campos incompletos deben revisarse.

## 2. Ejecutar la comparación local

```bash
python -m benchmarks.documents run --manifest data/benchmark/piloto-v1/manifest.json --output data/benchmark/piloto-v1/local --backends current pymupdf-layout
```

Cada salida debe ser nueva. No se reanuda ni sobrescribe una ejecución. Se procesan los mismos bytes verificados con cada extractor. La comparación local no carga `.env`, no utiliza claves de modelos y no envía PDFs a proveedores.

La salida contiene:

- `manifest.json`: copia exacta de la muestra congelada.
- `report.json`: versión del benchmark, huella de su código, commit del proyecto, entorno, tiempos, fallos y hashes de resultados.
- `metrics.csv` y `report.html`: lectura de las mediciones técnicas.
- `artifacts/`: resultados normalizados; los adaptadores opcionales conservan también la respuesta original.
- `annotations.template.json`: plantilla sin etiquetas para revisión experta.

El comando devuelve código 2 si alguna extracción resulta parcial o fallida, aunque conserva los resultados disponibles. OCR pendiente no equivale a extracción completa. Tesseract y sus idiomas se instalan por separado. Las salidas quedan fuera de Git en `data/benchmark/` y pueden contener texto completo: aplicar los permisos y la retención acordados para los documentos.

## 3. Anotar referencias verificables

Dos especialistas revisan el PDF de forma independiente y resuelven las referencias antes de medir recuperación. Copiar la plantilla a un archivo de anotación y conservar los hashes. Por documento, cambiar `review_status` a `adjudicated`, registrar dos revisores distintos y quien resolvió la anotación. Ejemplo de campos; los valores son ilustrativos, no etiquetas del corpus:

```json
{
  "review_status": "adjudicated",
  "reviewers": ["revisor-01", "revisor-02"],
  "adjudicated_by": "revisor-01",
  "fields": [
    {
      "field_id": "memoria-item-1",
      "kind": "table_cell",
      "page": 3,
      "expected_text": "16 GB",
      "row_anchor": "Computadora portátil",
      "column_header": "Memoria"
    }
  ]
}
```

`kind: text` comprueba un fragmento literal en su página. `table_cell` exige valor exacto, referencia en la misma fila y encabezado previo en la misma columna. No basta con encontrar el número en otra parte del documento. Se normalizan mayúsculas y espacios, preservando cifras y signos.

Opcionalmente agregar `expected_bbox: [x0, y0, x1, y1]`, coordenadas normalizadas entre 0 y 1, con origen superior izquierdo de la página visible. La coincidencia geométrica usa intersección/unión de al menos 0,5; no mide precisión de resaltado carácter por carácter. Geometría ausente cuenta como no recuperada cuando se exige una ubicación.

```bash
python -m benchmarks.documents score --run data/benchmark/piloto-v1/local --annotations data/benchmark/piloto-v1/anotaciones.json --output data/benchmark/piloto-v1/evaluacion.json
```

Sin referencias resueltas devuelve `pending_human_reference`, no una estimación de precisión. Mantiene extracciones fallidas en el denominador y verifica integridad de manifiesto y artefactos. El registro de revisores documenta una declaración: el comando no autentica sus identidades ni sustituye la revisión independiente.

## Interpretación y límites

- Más caracteres, tablas o celdas no demuestran mayor calidad. Un extractor puede fragmentar una tabla o asociar una cifra a otro requisito.
- El tiempo es una pasada por documento, incluye inicialización y escritura; no es una prueba de concurrencia ni un percentil de producción.
- La recuperación de referencias anotadas no equivale a precisión global, cobertura exhaustiva ni calidad de observaciones competitivas. Registrar también errores y omisiones mediante el protocolo de la PoC.
- La geometría nativa de PyMuPDF no se atribuye al texto obtenido por OCR. Docling conserva tablas multipágina en la respuesta original cuando no puede asociar inequívocamente cada celda a su página; no inventa ubicaciones.
- Celdas combinadas, encabezados multinivel y tablas partidas requieren referencias y análisis específicos. Una prueba fallida puede revelar también una limitación del comparador.
- No se calcula un precio monetario: `cost_estimate` queda en `null`. Las páginas enviadas a Azure son un indicador de exposición al consumo, no una factura. El benchmark no llama a modelos de lenguaje.

## Adaptadores opcionales

Preparar entornos de evaluación separados; mantener las restricciones del proyecto al instalar. Registrar versiones y revisar licencias, requisitos de hardware y política de datos antes de probar un servicio o descargar modelos.

### Azure Document Intelligence

```bash
python -m pip install -r requirements-dev.txt -r benchmarks/requirements-azure.txt
```

Configurar en el entorno `INTEGRITY_BENCHMARK_AZURE_ENDPOINT` y `INTEGRITY_BENCHMARK_AZURE_KEY`, exclusivos de esta prueba. Se admite un endpoint HTTPS `https://RECURSO.cognitiveservices.azure.com`. La clave de modelos de la aplicación no se reutiliza. Document Intelligence requiere su propio recurso/configuración; la disponibilidad de Azure OpenAI no lo habilita por sí sola.

```bash
python -m benchmarks.documents run --manifest data/benchmark/piloto-v1/manifest.json --output data/benchmark/piloto-v1/azure --backends azure-layout --allow-cloud --cloud-page-limit 100
```

El límite debe cubrir todas las páginas seleccionadas; no autoriza nuevas ejecuciones ni limita el gasto monetario. Se envía el PDF completo del manifiesto. Sin ambas opciones no se crea la ejecución ni se envían documentos. Una solicitud que falle o expire puede haber sido procesada y facturada; verificar el consumo antes de repetir. Los reintentos HTTP están desactivados y se acota la espera de respuesta, pero no se garantiza cancelar el procesamiento remoto.

Contrato de integración: [SDK oficial de Document Intelligence](https://learn.microsoft.com/en-us/python/api/overview/azure/ai-documentintelligence-readme?view=azure-python).

### Docling local

```bash
python -m pip install -r requirements-dev.txt -r benchmarks/requirements-docling.txt
docling-tools models download --output-dir data/benchmark/models/docling
python -m benchmarks.documents run --manifest data/benchmark/piloto-v1/manifest.json --output data/benchmark/piloto-v1/docling --backends docling --docling-artifacts data/benchmark/models/docling
```

La descarga es un paso explícito con acceso a Internet, fuera de la medición. Durante la conversión se deshabilitan servicios remotos, complementos externos y descargas de Hugging Face. Requiere Tesseract con español e inglés. Preparar todos los artefactos antes de una ejecución aislada; si faltan, se registra el fallo y no se adopta automáticamente otro motor.

Configuración y preparación: [opciones avanzadas oficiales de Docling](https://docling-project.github.io/docling/usage/advanced_options/).

## Decisión de adopción

Elegir extractores solo después de comparar referencias expertas, errores, geometría, latencia, recursos, licencias y costos sobre una muestra acordada. Conservar la ruta actual hasta que una mejora demuestre valor. El paso posterior es evaluar extracción de requisitos por cláusula y consistencia entre documentos; este benchmark aporta la base documental para esa decisión.

### Primer piloto local: 1 de noviembre de 2026

Se compararon los dos extractores locales en ocho procesos del corpus de desarrollo: 16 PDFs y 288 páginas. Ambos identificaron cuatro documentos con una página pendiente de OCR cada uno; el entorno de esta corrida no tenía Tesseract disponible. El adaptador estructurado detectó 474 regiones tabulares candidatas y 11.647 celdas: estos conteos requieren validación y no representan tablas correctas verificadas. El extractor actual no devuelve tablas estructuradas en su contrato.

No se realizaron llamadas a modelos ni servicios externos. Las referencias expertas permanecen pendientes; no se declara un extractor ganador. El siguiente paso es anotar una selección de celdas y fragmentos, resolver los pendientes de OCR y comparar los adaptadores opcionales solo con configuración y autorización del equipo. Este piloto diagnostica limitaciones técnicas, no valida precisión institucional.
