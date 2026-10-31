# Persistencia compartida y trabajos durables

## Estado de esta entrega

Implementado: una capa de datos SQLite/PostgreSQL, originales en archivos o Azure Blob Storage, proyección consultable de observaciones/evidencias, trabajos persistentes, trabajador separado y migración verificable desde SQLite.

Esto no publica la aplicación ni completa su seguridad institucional. Siguen pendientes autenticación y permisos por expediente, catálogo operativo del corpus, límites de proveedor compartidos y dimensionamiento de carga. La API mantiene la restricción de acceso local.

La entrega al desarrollador se organiza en [la guía de responsabilidades](developer_handoff.md) y [el procedimiento Azure](azure_deployment.md); no se debe interpretar el soporte de persistencia como autorización para publicar HTTP.

## Responsabilidades

| Componente | Responsabilidad |
|---|---|
| `review_store.py` | Transacciones y contratos de datos, comunes a SQLite y PostgreSQL |
| `storage_schema.py` | Esquema y migración versionados, sin generar categorías analíticas |
| `document_storage.py` | Originales por SHA-256 en archivos privados o Blob |
| `review_worker.py` | Reserva de trabajo, heartbeat y rechazo de resultados de un trabajador vencido |
| `src/review_worker.py` | Inicio del proceso de análisis independiente |
| `src/manage_storage.py` | Inicialización e importación explícitas, sin motor ni modelos |

SQLAlchemy Core comparte consultas entre los dos motores. No se incorporan ORM de entidades, agentes, colas externas ni otro frontend.

## Datos conservados

- `cases` y `documents`: expediente, versiones, identidad y referencia al original.
- `analysis_runs`: snapshot por ejecución; no reemplaza la evidencia original.
- `review_findings` y `review_evidence`: consultas por ejecución, patrón, prioridad, documento y página.
- `reviews` y `events`: estado humano, comentario, versión de edición e historial.
- `taxonomy_snapshots`: YAML exacto y SHA-256 de las reglas utilizadas.
- `analysis_cache`: resultados reutilizables por contenido y versiones.
- `analysis_jobs`: estado, propietario, token, intento y vencimiento de la reserva.
- `assisted_requests`: reserva previa y respuesta confirmada o incierta de solicitudes asistidas.
- `schema_migrations`: versión y comprobante del esquema esperado.

El resultado JSON completo se conserva junto a la proyección consultable. Esta duplicación es deliberada: permite inspección y compatibilidad sin convertir el snapshot en un esquema rígido para cada atributo analítico.

Los PDFs nuevos no se insertan como BLOB en la base. Los originales internos de la pre-PoC siguen siendo legibles hasta migrarlos explícitamente. Ninguna referencia depende de coincidencias parciales de nombres.

## Inicio local

Se mantiene `python run_workbench.py` con SQLite y un trabajador integrado. Instale primero `requirements.txt`.

Antes de la primera actualización desde la versión anterior, detenga esa versión y respalde la base. El ajuste SQLite es aditivo: agrega tablas/columnas y conserva originales, resultados e historial. No ejecute simultáneamente los binarios anteriores y nuevos sobre la misma base.

Respalde **base y directorio de originales**. El snapshot de la base por sí solo ya no contiene todos los PDFs nuevos.

## PostgreSQL y Blob Storage

Instale los adaptadores de la misma aplicación:

```bash
python -m pip install -r requirements-azure.txt
```

Configure mediante secretos del ambiente, no mediante archivos versionados:

```env
INTEGRITY_DATABASE_URL=postgresql://usuario:clave@servidor:5432/integrity?sslmode=verify-full&sslrootcert=/ruta/ca.pem
INTEGRITY_DOCUMENT_STORAGE=azure
INTEGRITY_BLOB_ACCOUNT_URL=https://cuenta.blob.core.windows.net/
INTEGRITY_BLOB_CONTAINER=integrity-documents
INTEGRITY_WORKER_MODE=external
```

PostgreSQL remoto exige TLS con verificación de servidor. Configure una CA de confianza; no elimine la verificación para evitar un error de conexión. La prueba local en loopback no requiere TLS.

Blob utiliza identidad administrada por defecto. Para una identidad asignada por usuario, configure `AZURE_CLIENT_ID`. El equipo de infraestructura debe crear el contenedor privado y asignar permisos de datos. La aplicación no crea cuentas, contenedores ni permisos de Azure. Se admite una cadena de conexión como secreto mediante `INTEGRITY_BLOB_CONNECTION_STRING`.

Inicialice el esquema con una identidad autorizada para migraciones:

```bash
python -m src.manage_storage init
```

La API y el trabajador PostgreSQL validan la versión del esquema; no ejecutan DDL automáticamente. No hay fallback silencioso a SQLite cuando falla el servidor.

Ejecute el trabajador en un proceso separado, con la misma configuración:

```bash
python -m src.review_worker
```

Para procesar solo un trabajo disponible: `python -m src.review_worker --once`. El proceso web sigue siendo `src.workbench_api:app`; habilitar un dominio público requiere completar primero autenticación y autorización.

## Recuperación y solicitudes asistidas

Un trabajo se reserva durante 90 segundos y renueva su reserva mientras se ejecuta. La reserva se comprueba antes de publicar datos. Un segundo trabajador no puede tomar el mismo trabajo vigente; tampoco el arranque de otra API lo marca como interrumpido.

Tras un vencimiento se admiten como máximo tres intentos. Si ya hay una lectura determinística guardada, se conserva y no se repite una solicitud asistida incierta. Sin resultado, el trabajo puede reanudar el pipeline utilizando cachés verificables. No se promete ejecución exactamente una vez ni cancelación fuerte de un extractor bloqueado.

La solicitud al proveedor se reserva antes de contactar con él. Si el proceso termina sin confirmar respuesta, no se vuelve a llamar automáticamente con la misma clave. Esto puede dejar contextualización sin completar: la interfaz debe indicarlo, no fingir éxito. Una respuesta tardía puede quedar registrada para reutilización sin permitir que un trabajador vencido sobrescriba la revisión.

El presupuesto actual sigue siendo por expediente. Esta entrega no implementa un limitador de cuota global de Azure OpenAI ni una estimación monetaria.

## Migración desde la pre-PoC

Detenga escrituras y conserve un respaldo independiente. Configure e inicialice un destino **vacío**. Para comenzar, inspeccione sin modificar el origen ni importar:

```bash
python -m src.manage_storage migrate --source /ruta/reviews.sqlite3 --manifest comprobante-previo.json
```

Luego importe explícitamente:

```bash
python -m src.manage_storage migrate --source /ruta/reviews.sqlite3 --apply --manifest comprobante-importacion.json
```

En Windows, use una ruta válida de PowerShell. Si los originales están en un directorio distinto al vecino `documents/`, agregue `--documents-root`.

La herramienta utiliza la API de backup de SQLite para leer un snapshot consistente. Comprueba integridad, documentos por SHA-256, conteos y originales de destino antes de confirmar las filas. Conserva IDs, snapshots, comentarios, eventos y copias de reglas. No ejecuta análisis ni contacta modelos.

Los trabajos importados incompletos quedan interrumpidos, no se ponen en ejecución automáticamente. Las solicitudes asistidas pendientes no se presentan como terminadas. Un destino con datos o un comprobante ya existente se rechazan para evitar sobrescritura.

Base y Blob no comparten una transacción distribuida. Un fallo puede dejar objetos sin referencia, pero revierte las filas de la importación. No se borran objetos en línea, porque otro expediente podría usarlos. La reconciliación y limpieza con retención quedan pendientes.

La utilidad admite SQLite con originales internos o archivos locales. No es un exportador universal entre cuentas Blob. El corpus histórico CSV/PDF se traslada y valida por separado; no se incorpora automáticamente a las tablas de revisión.

## Pruebas reproducibles

Se necesitan Docker y los adaptadores. Estos servicios y sus credenciales son exclusivamente locales:

```bash
docker compose -f compose.storage-test.yml up -d --wait
python -m pip install -r requirements-dev.txt -r requirements-azure.txt
```

En macOS/Linux:

```bash
export INTEGRITY_TEST_POSTGRES_URL=postgresql://integrity_test:local-test-only@127.0.0.1:55432/integrity_test
export INTEGRITY_TEST_AZURITE_URL=http://127.0.0.1:11000/integritytest
python -m pytest -q
```

En PowerShell, establezca las mismas variables con `$env:NOMBRE="valor"`. Las pruebas de integración rechazan destinos remotos. Los demás clientes HTTP quedan bloqueados, incluidos los proveedores asistidos.

Al terminar:

```bash
docker compose -f compose.storage-test.yml down
```

CI repite los contratos con PostgreSQL y Azurite. Esto verifica integración local, no identidad administrada, red privada, restauración de Azure ni rendimiento con volumen institucional.

## Siguiente etapa

Antes de compartir el ambiente: identidad verificada y permisos, catálogo y versiones del corpus, consultas de detalle por demanda, políticas de retención, límites de procesamiento globales y pruebas de recuperación/carga. No se debe interpretar esta base técnica como aprobación para exponer la API actual.
