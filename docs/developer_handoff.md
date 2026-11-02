# Entrega al desarrollador: preparación para Azure

## Punto de partida

Repositorio: [sebadhy/IntegrityTool, rama fusion](https://github.com/sebadhy/IntegrityTool/tree/fusion). Utilizar un commit revisado de esta rama para construir la imagen. La integración a `main` se realiza después de la validación del equipo.

La aplicación consta de un frontend **React/TypeScript + PDF.js**, una API **Python/FastAPI** y un trabajador Python que procesa los documentos.

| Componente | Datos/conexiones | Configuración |
|---|---|---|
| Navegador | API del mismo dominio; PDF servido mediante API | Sin claves de modelos ni acceso directo a Blob/PostgreSQL. |
| API | PostgreSQL, Blob privado y API pública SERCOP por HTTPS | `deploy/azure/api.env.example`; trabajador externo. |
| Trabajador | Misma base y contenedor, Azure OpenAI por HTTPS, corpus opcional | `deploy/azure/worker.env.example`; deployment y clave del modelo. |
| Administración | Esquema, migración, respaldos y pruebas de aceptación | Ejecutar comandos con permisos específicos; no exponer como endpoints públicos. |

**Estado de entrega:** motor documental, persistencia PostgreSQL/Blob, trabajos durables e imagen disponibles. **Acceso HTTP actual: local.** Antes de publicar la URL se requiere integrar autenticación, autorización, identidad verificada del revisor y dominio HTTPS.

El contenedor también escucha en loopback y el middleware rechaza hosts externos.
Para un ingreso de Container Apps, el desarrollador debe integrar los controles
anteriores y adaptar conjuntamente `src/container_start.py` y
`src/workbench_api.py`; cambiar solamente a `0.0.0.0` no habilita una publicación
segura. Este pendiente requiere implementación y pruebas, no solo variables Azure.

## Qué se entrega

- `Dockerfile`: frontend compilado, runtime Python con OCR y ejecución como usuario de aplicación.
- `src/container_start.py`: arranque de API o trabajador con validación del almacenamiento compartido.
- `src/deployment_check.py`: validación de configuración y consulta de servicios existentes.
- [Variables de API](../deploy/azure/api.env.example) y [variables del trabajador](../deploy/azure/worker.env.example), solo con ejemplos.
- [Guía de despliegue y aceptación](azure_deployment.md).
- [Contrato del motor de IA](ai_engine.md): dónde/cuándo interviene, qué recibe, qué valida, costo y evidencias de uso.
- [Migración de datos existentes](shared_storage.md), verificable y sin reanálisis.

## Qué corresponde al desarrollador y al equipo Azure

1. Seleccionar región y recursos dentro de la suscripción autorizada; estimar y aprobar costos.
2. Configurar tenant, acceso del equipo, autenticación y permisos. Integrar y probar esos controles con la API antes de abrir acceso web.
3. Preparar PostgreSQL, contenedor Blob privado, identidades, secretos, red y registro de imágenes.
4. Configurar **solo en el trabajador** el endpoint, deployment, versión de API y credenciales de Azure OpenAI. El ejemplo del trabajador deja activa la asistencia; sustituir marcadores y aprobar cuota/costos antes de ejecutarlo. Comprobar primero configuración y luego los contratos con datos ficticios.
5. Definir las revisiones que se importarán y la versión del corpus. Transferir los datos por un canal protegido, separado del código.
6. Ejecutar la lista de aceptación, probar respaldo/restauración y entregar URL, versión de imagen, responsables y limitaciones conocidas.

## Orden recomendado

**Acceso seguro → imagen y servicios privados → esquema y datos → trabajador → validación funcional → URL para el equipo.**

Puede validarse primero el trabajador con los servicios privados mientras se integra el acceso web. PostgreSQL conserva el estado compartido y Blob almacena los originales.

## Ruta de validación

Ejecutar cada paso con las variables del rol correspondiente; los comandos no
crean recursos en la suscripción. En la imagen, sustituir el entrypoint por
`python` para las comprobaciones administrativas.

| Paso | Comando o comprobación | Evidencia |
|---|---|---|
| Configuración de API | `python -m src.deployment_check --role api` | Variables válidas; no implica acceso web listo. |
| Datos y trabajador | `python -m src.deployment_check --role worker --check-services` | Esquema, acceso a contenedor, taxonomía y OCR. |
| Configuración IA | `python -m src.assistance_check` | Cero solicitudes a modelos. |
| Compatibilidad Azure OpenAI | `python -m src.assistance_check --request-model` | Hasta dos solicitudes facturables con contenido ficticio y salida validada. |
| Expediente público acordado | Cargar originales, iniciar revisión y comprobar citas | Procedencia de `semantic_analysis` y `summary`, cobertura y uso de caché. |
| Persistencia y fallback | Reiniciar; navegar y exportar; probar asistencia desactivada/fallo | Originales y resultados conservados, sin llamadas por navegación. |
| Seguridad del ambiente | Probar acceso anónimo, permisos, identidad y descarga/exportación | Rechazos efectivos antes de compartir URL. |

Leer [cómo verificar el uso real](ai_engine.md#7-cómo-comprobar-que-intervino).
No ejecutar la prueba de modelos como probe periódico. El corpus histórico y las
revisiones locales son datos separados del código: acordar qué se transfiere y
por qué canal; el repositorio no los incluye.

## Entregables de vuelta

- Commit e imagen por digest; región y recursos utilizados.
- URL autenticada y cuentas de prueba autorizadas, sin enviar contraseñas por correo.
- Confirmación de PostgreSQL, Blob, corpus y proveedor configurados; evidencia de las pruebas de aceptación.
- Deployment y versión de API aprobados, prueba sintética y un expediente con procedencia verificable. No adjuntar claves ni respuestas documentales completas al correo de entrega.
- Procedimiento de actualización, recuperación y contacto de soporte.
- Pendientes explícitos y resultados de la evaluación analítica con el equipo institucional.
