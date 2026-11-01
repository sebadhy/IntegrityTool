# Preparación y despliegue en Azure

Procedimiento para construir la imagen, configurar los procesos y validar el despliegue. El equipo que administra la suscripción prepara los recursos y el acceso institucional.

## 1. Requisitos de acceso compartido

**Acceso actual: local, en `127.0.0.1:8000`.** Antes de publicar la URL se requiere integrar y validar el acceso institucional.

Antes de compartir la URL, el desarrollador debe integrar y probar:

- Autenticación institucional, acceso del equipo autorizado y cierre de sesión.
- Autorización de lectura/escritura y política de acceso a cada expediente, incluido el aislamiento requerido entre usuarios o instituciones.
- Identidad del revisor derivada de la sesión validada. Actualmente, `reviewer` es un campo enviado por el navegador y el historial registra operaciones con una etiqueta local.
- Dominios y origen HTTPS permitidos, protección de operaciones de escritura y rechazo de acceso directo que evada la autenticación.

Implementar la integración en `src/workbench_api.py` y comprobar autenticación, permisos y origen de las solicitudes antes de habilitar el dominio compartido.

Como ruta de referencia, Azure Container Apps permite delegar el inicio de sesión en la plataforma y recibir información de identidad validada. Configurar el proveedor y vincular la identidad con los permisos de la aplicación. [Documentación oficial de autenticación](https://learn.microsoft.com/en-us/azure/container-apps/authentication).

## 2. Arquitectura mínima de referencia

```text
Usuario autorizado
  → acceso HTTPS autenticado y autorizado, pendiente de integración
  → API FastAPI + frontend estático
      → PostgreSQL: expedientes, resultados, revisiones y trabajos
      → Blob privado: originales por SHA-256
  → trabajador Python, sin ingreso público
      → PostgreSQL y Blob del mismo ambiente
      → corpus opcional versionado, montado por separado
      → Azure OpenAI, si está habilitado
```

API y trabajador utilizan la misma imagen y código, con comandos distintos. PostgreSQL conserva la cola de trabajos. Para la primera prueba, comenzar con un trabajador; aumentar concurrencia después de medir memoria, tiempos, conexiones y cuotas del proveedor.

Si se utiliza Container Apps para el trabajador continuo, deshabilitar ingreso y mantener al menos una réplica; sin ingreso ni una regla de activación, reducirlo a cero impediría procesar la cola. Los recursos son un costo a aprobar por el equipo. [Escalamiento oficial](https://learn.microsoft.com/en-us/azure/container-apps/scale-app).

## 3. Construir una imagen trazable

Desde un checkout limpio del commit acordado:

```bash
git rev-parse HEAD
docker buildx build --platform linux/amd64 --build-arg REVISION=COMMIT_SHA -t REGISTRY/integrity:COMMIT_SHA --load .
```

Sustituir `COMMIT_SHA` y `REGISTRY` por los valores del ambiente. Publicar la imagen en el registro autorizado y conservar su digest. Para Container Apps, construir `linux/amd64`, también desde una computadora ARM. [Requisitos de contenedores](https://learn.microsoft.com/en-us/azure/container-apps/containers).

El build usa imágenes base fijadas por digest, lockfile del frontend y dependencias Python declaradas. Los rangos Python y paquetes del sistema pueden resolverse a versiones distintas al reconstruir: conservar la imagen aprobada. `/app/installed-packages.txt` registra los paquetes efectivos y la etiqueta OCI `org.opencontainers.image.revision` identifica el commit. Revisar licencias y vulnerabilidades antes de liberar la imagen.

La imagen incluye OCR español/inglés y se ejecuta como UID/GID `10001`. Los secretos, PDFs, bases y corpus se suministran por separado. Node se utiliza en la fase de construcción del frontend.

Para repetir la prueba aislada de la imagen, sin Azure ni red externa:

```bash
python deploy/verify_container.py REGISTRY/integrity:COMMIT_SHA
```

Comprueba usuario, OCR, configuración y una revisión ficticia con trabajador separado, comentario y exportaciones. Utiliza datos temporales; el acceso institucional se valida en el ambiente de destino.

## 4. Contratos de ejecución

El entrypoint es `python -m src.container_start`. Comandos dentro de la imagen:

| Proceso | Argumentos del entrypoint | Comportamiento |
|---|---|---|
| API | `api` | Sirve frontend y API en `127.0.0.1:8000` |
| Trabajador | `worker` | Procesa trabajos persistentes de PostgreSQL |

Para herramientas administrativas, sustituir el entrypoint por `python` y usar el módulo correspondiente. Para consultar sus opciones:

```bash
docker run --rm --entrypoint python REGISTRY/integrity:COMMIT_SHA -m src.deployment_check --help
```

El trabajador maneja SIGTERM y termina después del trabajo actual. Una terminación forzada se recupera mediante la reserva persistente; una respuesta asistida pendiente de guardar puede perderse. Monitorizar el trabajador mediante el estado del proceso y de la cola. Definir los probes de la API al integrar el acceso compartido, manteniendo protegidos los endpoints de datos.

## 5. Variables y secretos

Configurar cada proceso según su contrato:

- [API](../deploy/azure/api.env.example).
- [Trabajador](../deploy/azure/worker.env.example).

La API usa `INTEGRITY_WORKER_MODE=external`; el procesamiento se configura en el trabajador. API y trabajador deben apuntar a la misma base y contenedor, con credenciales apropiadas para cada proceso.

PostgreSQL remoto exige `sslmode=verify-full`. La imagen proporciona `/etc/ssl/certs/ca-certificates.crt`; si se exige otra CA, montarla y cambiar `sslrootcert`, conservando la verificación TLS. Codificar los caracteres especiales de la contraseña en la URL. Mantener migraciones con permisos separados de los de ejecución.

Blob se conecta con identidad administrada por defecto; una identidad asignada por usuario requiere `AZURE_CLIENT_ID`. Crear un contenedor privado y asignar permisos de datos: la API carga/lee originales y el trabajador los lee. Servir los PDFs mediante la API autorizada. La comprobación de propiedades del contenedor puede necesitar permisos de lectura de contenedor además del acceso a objetos.

Suministrar secretos en tiempo de ejecución mediante la plataforma o su integración con Key Vault. Mantenerlos excluidos del build, del frontend y de Git.

### Azure OpenAI

Comenzar con `INTEGRITY_ASSISTED_ENABLED=false` para verificar documentos y persistencia sin llamadas a modelos. Para activar la asistencia en el trabajador:

```env
INTEGRITY_ASSISTED_ENABLED=true
INTEGRITY_SEMANTIC_ENABLED=true
INTEGRITY_LLM_MAX_CALLS=2
LLM_PROVIDER=azure
OPENAI_API_KEY=SECRET_SUPPLIED_AT_RUNTIME
OPENAI_BASE_URL=https://RESOURCE.openai.azure.com/
OPENAI_API_VERSION=COMPATIBLE_API_VERSION
OPENAI_MODEL=DEPLOYMENT_NAME
```

`OPENAI_MODEL` identifica el deployment configurado en Azure. Azure OpenAI se autentica mediante `OPENAI_API_KEY`; Blob utiliza la identidad administrada indicada en la sección anterior.

Probar compatibilidad con los esquemas estructurados y límites del deployment elegido. La aplicación admite hasta tres solicitudes lógicas por expediente y conserva las solicitudes inciertas para evitar repeticiones automáticas. Configurar cuotas y presupuesto global en el recurso. Ante un fallo del proveedor se conserva la lectura determinística.

## 6. Esquema y datos existentes

Crear base y contenedor privados antes del arranque. Con variables y permisos de migración, ejecutar una sola vez:

```bash
python -m src.manage_storage init
```

En un contenedor administrativo, utilizar `--entrypoint python` y `-m src.manage_storage init`, con acceso privado a los mismos servicios. La inicialización del esquema es un paso administrativo previo al arranque de API y trabajador.

Decidir si el ambiente comienza vacío o conserva revisiones anteriores. Para importar, detener escrituras en el origen, respaldar y utilizar [la migración verificada](shared_storage.md#migración-desde-la-pre-poc). No copiar una SQLite en uso ni adjuntar una base de laptop al repositorio. Conservar el comprobante de migración en almacenamiento protegido.

La migración conserva IDs, resultados, eventos, comentarios, originales y copias de reglas. No vuelve a analizar documentos ni solicita modelos. Un destino con datos se rechaza. Un fallo de objetos revierte filas, pero puede dejar objetos no referenciados; no borrarlos indiscriminadamente porque los hashes pueden compartirse.

## 7. Corpus histórico: entrega separada

El corpus histórico se administra como un conjunto versionado de CSV y PDFs. Las cargas de usuarios se almacenan en expedientes; el equipo publica las versiones del corpus por separado, con validación determinística de correspondencia:

```text
/mnt/corpus/
  metadata/procesos.csv
  pliegos/*.pdf
  especificaciones/*.pdf
```

Utilizar los nombres y columnas de [configuración del corpus](configuration.md#corpus-documental-opcional). Entregar una versión identificable, conservar CSV y hashes, comprobar faltantes/duplicados y respetar la correspondencia exacta normalizada. Montar la versión aprobada en el trabajador, preferentemente de solo lectura. Azure Files permite suministrarla mediante un volumen. [Montajes de almacenamiento](https://learn.microsoft.com/en-us/azure/container-apps/storage-mounts).

La caché de extracción puede ir en `/tmp/integrity/extracted_text`: es regenerable, no el original. Para reproducir un análisis debe conservarse el corpus de referencia, además de la base y los originales de cada expediente. Si no se suministra corpus, la revisión funciona sin comparación y debe indicarlo; no simular procesos comparables.

## 8. Comprobación previa sin análisis ni modelos

En el entorno configurado del proceso correspondiente:

```bash
python -m src.deployment_check --role api
python -m src.deployment_check --role worker --check-services
python -m src.deployment_check --role worker --check-services --require-corpus
```

Sin `--check-services` solo valida variables. Con él consulta el esquema, propiedades del contenedor, taxonomía y OCR. `--require-corpus` agrega validación del CSV y correspondencia de PDFs, no OCR del corpus. Los checks no suben documentos, crean tablas, migran ni invocan modelos. Un código de salida distinto de cero indica configuración o comprobaciones fallidas. Los mensajes no imprimen cadenas de conexión ni secretos.

`ok=true` **no autoriza publicación HTTP** ni valida permisos de escritura, autenticación, red privada, restauración o precisión analítica. La salida mantiene `public_http_ready=false` para reflejar el bloqueo actual.

## 9. Aceptación antes de entregar la URL

- [ ] Commit, digest, recursos, región y costos aprobados y registrados.
- [ ] Autenticación, permisos y dominio integrados; acceso anónimo o con cabeceras de identidad falsificadas rechazado.
- [ ] Intentar consultar un expediente sin permiso, descargar su PDF, exportarlo y modificar comentarios: todos deben rechazarse según la política definida.
- [ ] Actor de los eventos proviene de una identidad validada. No aceptar `Revisor local` como identidad institucional.
- [ ] Cargar pliego y especificaciones públicos de prueba; localizar dos evidencias, cambiar página/zoom, guardar comentario y exportar HTML/CSV/JSON.
- [ ] Reiniciar API y trabajador; verificar conservación de revisiones, originales y trabajos. Navegar no debe solicitar de nuevo modelos.
- [ ] Confirmar procesamiento con y sin Azure OpenAI y probar fallo/timeout del proveedor sin perder la lectura determinística.
- [ ] Verificar corpus validado o ausencia informada; versiones sustituidas y todas las ocurrencias siguen trazables.
- [ ] Probar respaldo y restauración de PostgreSQL y Blob; conservar reglas, código, imagen y corpus de referencia. Definir responsables, retención, RPO y RTO.
- [ ] Revisar memoria/latencia con documentos representativos, conexiones, cola pendiente, OCR y cuota del modelo antes de aumentar réplicas.
- [ ] No publicar claves, texto completo de PDFs, respuestas completas ni comentarios en logs generales. Definir retención y acceso a registros.

Actualizar imagen y esquema como un cambio controlado, con respaldo y plan de reversión. Esta versión solo tiene la migración de esquema actual; una imagen anterior no necesariamente puede abrir una base futura. No hacer downgrade contra la base activa sin verificar compatibilidad.

## 10. Operación y evaluación

Acordar responsables para la gestión del corpus, cuotas, reconciliación y retención de objetos. Validar carga y recuperación en la suscripción real, y evaluar la calidad analítica con especialistas de SERCOP. Registrar resultados y pendientes como parte de la aceptación del ambiente.
