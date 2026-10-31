# Entrega al desarrollador: preparación para Azure

## Punto de partida

Repositorio: [sebadhy/IntegrityTool, rama fusion](https://github.com/sebadhy/IntegrityTool/tree/fusion). Utilizar un commit revisado, no una copia de la laptop ni una rama personal. No modificar `main` durante esta preparación.

La aplicación es **React/TypeScript + PDF.js y Python/FastAPI**, con un trabajador Python del mismo proyecto. No hay una aplicación Streamlit que desplegar.

**Estado real:** el motor, la persistencia PostgreSQL/Blob y los trabajos durables están implementados. El acceso HTTP continúa siendo local. La integración de autenticación, autorización, identidad del revisor y dominio compartido está pendiente y debe resolverse antes de publicar la URL. Tener un contenedor no elimina ese bloqueo.

## Qué se entrega

- `Dockerfile`: frontend construido y runtime Python con OCR, sin usuario root ni datos locales.
- `src/container_start.py`: arranque de API o trabajador; rechaza almacenamiento compartido incompleto. No configura Azure ni autenticación.
- `src/deployment_check.py`: comprobación de configuración y, opcionalmente, servicios existentes; no crea recursos ni solicita contenido a modelos.
- [Variables de API](../deploy/azure/api.env.example) y [variables del trabajador](../deploy/azure/worker.env.example), solo con ejemplos.
- [Guía de despliegue y aceptación](azure_deployment.md), con el bloqueo HTTP explícito.
- [Migración de datos existentes](shared_storage.md), verificable y sin reanálisis.

## Qué corresponde al desarrollador y al equipo Azure

1. Seleccionar región y recursos dentro de la suscripción autorizada; estimar y aprobar costos.
2. Configurar tenant, acceso del equipo, autenticación y permisos. Integrar esos controles con la API antes de abrir acceso web; no quitar simplemente la restricción de host.
3. Preparar PostgreSQL, contenedor Blob privado, identidades, secretos, red y registro de imágenes.
4. Configurar el deployment existente de Azure OpenAI en el trabajador. Una licencia no equivale a un endpoint, deployment y permisos ya disponibles.
5. Decidir si se trasladan revisiones anteriores y qué corpus versionado se utilizará. Los datos no viajan dentro de Git ni de la imagen.
6. Ejecutar la lista de aceptación, probar respaldo/restauración y entregar URL, versión de imagen, responsables y limitaciones conocidas.

## Orden recomendado

**Acceso seguro → imagen y servicios privados → esquema y datos → trabajador → validación funcional → URL para el equipo.**

Puede validarse primero el trabajador con el ambiente privado mientras se integra el acceso web. No compartir una URL sin autenticación ni utilizar una carpeta de red como sustituto de PostgreSQL.

## Entregables de vuelta

- Commit e imagen por digest; región y recursos utilizados.
- URL autenticada y cuentas de prueba autorizadas, sin enviar contraseñas por correo.
- Confirmación de PostgreSQL, Blob, corpus y proveedor configurados; evidencia de las pruebas de aceptación.
- Procedimiento de actualización, recuperación y contacto de soporte.
- Pendientes explícitos. Esta base no acredita precisión institucional ni operación multiinstitucional.
