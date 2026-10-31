# Configuración de Integrity Tool

La aplicación se inicia con `python run_workbench.py`. Estas opciones no agregan interfaces ni servicios de ejecución alternativos.

Para la entrega al equipo Azure, consultar primero [las responsabilidades y el orden de trabajo](developer_handoff.md) y [la guía operativa](azure_deployment.md). Los ejemplos de API/trabajador no configuran un tenant ni habilitan acceso público.

## Variables y secretos

Copie `.env.example` a `.env` solo si no existe una configuración propia. Las variables del proceso tienen precedencia sobre el archivo. No publique `.env`, claves, bases de revisión ni documentos locales en Git.

Sin proveedor configurado, la aplicación mantiene el análisis determinístico. El corpus es opcional y se valida por separado.

## Proveedor de procesamiento asistido

Seleccione un único proveedor con `LLM_PROVIDER`. Sin selección explícita se conserva la detección automática: Azure, Groq, Ollama y OpenAI.

### Azure OpenAI

```env
LLM_PROVIDER=azure
OPENAI_API_KEY=<clave del recurso>
OPENAI_BASE_URL=https://<recurso>.openai.azure.com/
OPENAI_API_VERSION=<version de API compatible con el deployment>
OPENAI_MODEL=<nombre del deployment>
```

`OPENAI_MODEL` es el nombre del despliegue Azure. La configuración por clave está implementada; identidad administrada no está integrada todavía. Antes de publicar, valide los contratos de salida estructurada con la versión y modelo elegidos. No se debe asumir compatibilidad solo por obtener una respuesta a una llamada simple.

### OpenAI

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=<clave>
OPENAI_MODEL=<modelo compatible con salidas estructuradas>
```

### Groq

```env
LLM_PROVIDER=groq
GROQ_API_KEY=<clave>
GROQ_MODEL=llama-3.3-70b-versatile
```

Utiliza el cliente compatible con OpenAI; no requiere otro SDK.

### Ollama local

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=llama3.1
```

El servicio y el modelo se instalan por separado. La disponibilidad de un proveedor no acredita la calidad de sus respuestas; se deben evaluar los modelos en documentos representativos.

## Presupuesto y cobertura

```env
INTEGRITY_ASSISTED_ENABLED=true
INTEGRITY_SEMANTIC_ENABLED=true
INTEGRITY_LLM_MAX_CALLS=2
```

- `INTEGRITY_ASSISTED_ENABLED=false`: desactiva todas las solicitudes asistidas.
- `INTEGRITY_SEMANTIC_ENABLED=false`: conserva solo síntesis y explicación.
- El presupuesto compartido admite de cero a tres solicitudes lógicas por expediente. Por defecto son dos: una propuesta semántica y una síntesis si hay observaciones visibles. Con tres puede agregarse una explicación.
- La selección semántica incluye hasta 24 cláusulas activas, 12.000 caracteres de texto y cuatro propuestas. Las cláusulas de más de 1.600 caracteres quedan fuera de esa selección, sin truncarlas. Se conserva la cobertura efectiva.
- Cada solicitud tiene timeout y límite de salida; no hay reintentos implícitos. Éxitos y fallos se guardan para evitar nuevas solicitudes al navegar.
- Se registra el consumo reportado por el proveedor, no una estimación monetaria. Una solicitud fallida o interrumpida puede tener costo.

Los candidatos deben pertenecer a la taxonomía archivada y citar una cláusula enviada. La validación comprueba estructura, citas y reglas de integración, no la corrección definitiva de la interpretación. La asistencia no es lectura exhaustiva, búsqueda de mercado ni contraste semántico integral entre documentos.

## Persistencia

```env
INTEGRITY_STORE_PATH=data/workbench/reviews.sqlite3
```

La base conserva resultados, cláusulas, copias de taxonomía, caché, revisiones humanas y trabajos persistentes. Los originales nuevos se guardan en archivos por SHA-256 junto a la base; los PDFs internos de revisiones anteriores se siguen leyendo sin reanalizarlos. Base y originales están excluidos de Git: respalde ambos.

Para PostgreSQL y Azure Blob Storage, consulte [persistencia compartida y migración](shared_storage.md). No es suficiente apuntar una ruta SQLite a una carpeta de red.

## Corpus documental opcional

```text
data/raw/
  metadata/procesos.csv
  pliegos/
  especificaciones/
data/processed/
  extracted_text/
```

Columnas del CSV: `process_id`, `entidad`, `objeto`, `fecha`, `pliego_file` y `especificaciones_file`. Se aceptan separadores coma o punto y coma y UTF-8 con BOM.

Los nombres de archivo y la carpeta deben corresponder exactamente después de la normalización de nombres. No se seleccionan PDFs por parecido, prefijo ni identificador parcial. Los faltantes, ambigüedades y duplicados se informan; no se completa silenciosamente una comparación con documentos inciertos. No incluya archivos del sistema como documentos del corpus.

Puede modificar las rutas mediante:

```env
APP_CORPUS_METADATA_PATH=data/raw/metadata/procesos.csv
APP_CORPUS_PLIEGOS_DIR=data/raw/pliegos
APP_CORPUS_ESPECIFICACIONES_DIR=data/raw/especificaciones
APP_CORPUS_PROCESSED_DIR=data/processed/extracted_text
```

El corpus utiliza el mismo motor determinístico que los documentos cargados y excluye el proceso del documento en revisión para evitar autocomparación. La frecuencia es contexto: no demuestra validez de un requisito ni exclusividad comercial. No se utiliza la frecuencia de reglas para declarar rara una propuesta semántica nueva.

## OCR y ajustes del motor

Para PDFs escaneados, instale Tesseract con el idioma español en el sistema. Sin OCR disponible, las páginas sin texto se informan como lectura parcial.

`APP_MAX_DOCUMENT_CHARS` y `APP_DEFAULT_CONTEXT_CHARS` mantienen los límites de texto del adaptador asistido y las ventanas del detector. No los cambie para simular lectura completa; las restricciones de selección semántica y los controles de evidencia siguen aplicando.

## Despliegue compartido

El inicio local escucha en `127.0.0.1:8000`. La API rechaza hosts externos y no tiene identidad institucional integrada. Configurar Azure OpenAI no publica la aplicación. La autenticación, autorización, almacenamiento persistente y operación segura deben resolverse antes de exponerla.
