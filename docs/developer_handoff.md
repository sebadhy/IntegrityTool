# Entrega al desarrollador: preparación para Azure

## Punto de partida

Repositorio: [sebadhy/IntegrityTool, rama fusion](https://github.com/sebadhy/IntegrityTool/tree/fusion). Utilizar un commit revisado de esta rama para construir la imagen. La integración a `main` se realiza después de la validación del equipo.

La aplicación consta de un frontend **React/TypeScript + PDF.js**, una API **Python/FastAPI** y un trabajador Python que procesa los documentos.

**Estado de entrega:** motor documental, persistencia PostgreSQL/Blob, trabajos durables e imagen disponibles. **Acceso HTTP actual: local.** Antes de publicar la URL se requiere integrar autenticación, autorización, identidad verificada del revisor y dominio HTTPS.

## Qué se entrega

- `Dockerfile`: frontend compilado, runtime Python con OCR y ejecución como usuario de aplicación.
- `src/container_start.py`: arranque de API o trabajador con validación del almacenamiento compartido.
- `src/deployment_check.py`: validación de configuración y consulta de servicios existentes.
- [Variables de API](../deploy/azure/api.env.example) y [variables del trabajador](../deploy/azure/worker.env.example), solo con ejemplos.
- [Guía de despliegue y aceptación](azure_deployment.md).
- [Migración de datos existentes](shared_storage.md), verificable y sin reanálisis.

## Qué corresponde al desarrollador y al equipo Azure

1. Seleccionar región y recursos dentro de la suscripción autorizada; estimar y aprobar costos.
2. Configurar tenant, acceso del equipo, autenticación y permisos. Integrar y probar esos controles con la API antes de abrir acceso web.
3. Preparar PostgreSQL, contenedor Blob privado, identidades, secretos, red y registro de imágenes.
4. Configurar en el trabajador el endpoint, deployment, versión de API y credenciales de Azure OpenAI.
5. Definir las revisiones que se importarán y la versión del corpus. Transferir los datos por un canal protegido, separado del código.
6. Ejecutar la lista de aceptación, probar respaldo/restauración y entregar URL, versión de imagen, responsables y limitaciones conocidas.

## Orden recomendado

**Acceso seguro → imagen y servicios privados → esquema y datos → trabajador → validación funcional → URL para el equipo.**

Puede validarse primero el trabajador con los servicios privados mientras se integra el acceso web. PostgreSQL conserva el estado compartido y Blob almacena los originales.

## Entregables de vuelta

- Commit e imagen por digest; región y recursos utilizados.
- URL autenticada y cuentas de prueba autorizadas, sin enviar contraseñas por correo.
- Confirmación de PostgreSQL, Blob, corpus y proveedor configurados; evidencia de las pruebas de aceptación.
- Procedimiento de actualización, recuperación y contacto de soporte.
- Pendientes explícitos y resultados de la evaluación analítica con el equipo institucional.
