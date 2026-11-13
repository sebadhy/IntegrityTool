# Configuración de Integrity Tool

El inicio local es `python run_workbench.py`. Las variables del ambiente configuran proveedor, almacenamiento y corpus.

Para el equipo Azure, consultar [las responsabilidades y el orden de trabajo](developer_handoff.md) y [la guía operativa](azure_deployment.md), con los requisitos para habilitar el acceso compartido.

## Variables y secretos

Copie `.env.example` a `.env` solo si no existe una configuración propia. Las variables del proceso tienen precedencia sobre el archivo. No publique `.env`, claves, bases de revisión ni documentos locales en Git.

Sin proveedor configurado, la aplicación mantiene el análisis determinístico. El corpus es opcional y se valida por separado.

El [contrato del motor de IA](ai_engine.md) explica qué etapas usan modelos,
qué datos reciben y cómo comprobar su intervención. En Azure, las variables del
modelo se configuran únicamente en el trabajador; la API registra los trabajos.

## Proveedor de procesamiento asistido

Seleccione un único proveedor con `LLM_PROVIDER`. Sin selección explícita se conserva la detección automática: Azure, Groq, Ollama y OpenAI.

Para SERCOP o cualquier VM independiente, usar el perfil portable `onprem`, que
admite estos proveedores. El perfil específico `azure` conserva validaciones de
Azure OpenAI. Las variables `.env` no se entregan automáticamente al trabajador
de Compose: aplicar el override correspondiente, como muestran los
[ejemplos de instalación](onprem_installation.md#5-procesamiento-asistido-opcional).

Si ejecuta Python sin Compose, definir `INTEGRITY_DEPLOYMENT_PROFILE=onprem`
también en su ambiente o `.env` para validar proveedores distintos de Azure con
`src.assistance_check`. El Compose portable ya suministra esa variable.

Esta configuración selecciona conectores existentes, no garantiza compatibilidad
con cualquier API o modelo. El contrato requiere Chat Completions, JSON validable
y `max_completion_tokens`; una API distinta necesita un adaptador. Probar el
modelo autorizado antes de aceptar el ambiente. El repositorio no instala ni
dimensiona el servidor de inferencia.

### Azure OpenAI

```env
LLM_PROVIDER=azure
OPENAI_API_KEY=<clave del recurso>
OPENAI_BASE_URL=https://<recurso>.openai.azure.com/
OPENAI_API_VERSION=<version de API compatible con el deployment>
OPENAI_MODEL=<nombre del deployment>
```

`OPENAI_MODEL` es el nombre del despliegue Azure. Este proveedor se autentica mediante `OPENAI_API_KEY`. Antes de publicar, valide los contratos de salida estructurada con la versión y modelo elegidos.

Para comprobar únicamente las variables: `python -m src.assistance_check`.
Para probar explícitamente el cliente y los esquemas con hasta dos solicitudes
facturables de contenido ficticio: `python -m src.assistance_check --request-model`.
Estos comandos se ejecutan con las variables del trabajador; no necesitan PDFs
ni una base de revisiones. No utilizar la prueba de modelos como health check.

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
GROQ_MODEL=<modelo autorizado y validado>
```

Utiliza el cliente compatible con OpenAI incluido en las dependencias.

### Ollama local

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=<modelo instalado y validado>
```

El servicio y el modelo se instalan por separado. El ejemplo `localhost` solo
aplica cuando el proceso Python y el servicio comparten ese host; dentro de un
contenedor apunta al propio contenedor. En Compose, configurar una dirección
interna alcanzable desde el trabajador. La disponibilidad de un proveedor no
acredita la calidad de sus respuestas; se deben evaluar los modelos en documentos
representativos.

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

Para almacenamiento compartido, configure PostgreSQL y Azure Blob Storage según [la guía de persistencia y migración](shared_storage.md).

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

El texto seleccionable breve se conserva como lectura nativa. Una imagen pequeña que se repite en el mismo margen en varias páginas no activa OCR por sí sola cuando ya existe texto seleccionable. Las imágenes de contenido y los casos de ubicación incierta mantienen el control de OCR. Cada página registra una nota de extracción; esta clasificación no certifica exactitud ni cobertura completa.

`APP_MAX_DOCUMENT_CHARS` y `APP_DEFAULT_CONTEXT_CHARS` mantienen los límites de texto del adaptador asistido y las ventanas del detector. No los cambie para simular lectura completa; las restricciones de selección semántica y los controles de evidencia siguen aplicando.

## Despliegue compartido

El inicio local escucha en `127.0.0.1:8000` y rechaza conexiones externas. El perfil Azure `INTEGRITY_WEB_MODE=entra` implementa validación de identidad, roles y origen, y el contenedor escucha en `0.0.0.0:8000`. Aplicar [las variables de API](../deploy/azure/api.env.example) y configurar Easy Auth, token store, usuarios y HTTPS según [la guía de acceso](azure_access.md). No se modifican archivos fuente ni se agrega una clave de modelo al frontend.

## Despliegue portable

El [perfil on-premise](onprem_installation.md) usa `INTEGRITY_DEPLOYMENT_PROFILE=onprem`, `INTEGRITY_WEB_MODE=password`, PostgreSQL y `INTEGRITY_DOCUMENT_STORAGE=filesystem`. Entra (`entra`) y el modo local de desarrollo (`local`, solo loopback) siguen disponibles.

Los secretos `INTEGRITY_DATABASE_URL`, `OPENAI_API_KEY`, `GROQ_API_KEY` e `INTEGRITY_BLOB_CONNECTION_STRING` admiten el sufijo `_FILE`. El archivo se lee al iniciar; valores directos y de archivo distintos provocan un error sin imprimirlos. Rotar requiere recrear el proceso. El Compose base no entrega ninguna credencial de modelos a la API.
