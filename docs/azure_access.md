# Acceso institucional en Azure: configuración sin cambios de código

Perfil soportado: **Azure Container Apps + Microsoft Entra ID (Easy Auth)**,
con ID tokens v2 y token store habilitado. El código de acceso, roles y protección
de documentos ya está incluido. El administrador configura recursos y usuarios;
no necesita editar Python ni React.

## Política del espacio

Esta PoC utiliza **un espacio compartido por un equipo autorizado en un tenant**.
Todos sus miembros autorizados pueden consultar todos los expedientes, incluidos
los importados. No implementa espacios privados por funcionario ni aislamiento
entre instituciones dentro de la misma base. Para otro equipo que no deba ver
estos datos, desplegar otra instancia con base y contenedores separados.

| Rol de aplicación | Permisos |
|---|---|
| `Integrity.Reader` | Consultar expedientes, originales, evidencia, historial, taxonomía y exportaciones. |
| `Integrity.Reviewer` | Lo anterior, cargar documentos, importar una ficha SERCOP, iniciar/reintentar análisis y guardar revisiones/comentarios. |
| Sin uno de esos roles | Sin acceso a datos, aunque la cuenta pertenezca al tenant. |

El consentimiento explícito de esta política es
`INTEGRITY_ACCESS_POLICY=shared_team`. No se conceden permisos por correo,
dominio del correo ni rol de administrador general del tenant.

## 1. Registrar la aplicación de acceso

1. En Microsoft Entra, crear una **App registration de un solo tenant**, dedicada
   a este ambiente. Registrar su Directory/Tenant ID y Application/Client ID.
2. Configurar el proveedor con emisor
   `https://login.microsoftonline.com/TENANT_ID/v2.0`.
3. Agregar como redirect URI de tipo Web:
   `https://FQDN/.auth/login/aad/callback`. Habilitar emisión de ID tokens para
   el flujo de Easy Auth. No usar una aplicación de Graph u otro servicio.
4. Crear los dos App roles indicados arriba, con miembros permitidos **Users/Groups**.
   [El catálogo JSON](../deploy/azure/entra-app-roles.json) contiene sus valores e IDs.
   Puede aplicarse a la nueva App registration o reproducirse desde el portal.
   No sobrescribir roles existentes de una aplicación compartida.
5. En Enterprise applications, exigir asignación y asignar usuarios/grupos al
   rol de consulta o revisión. Los invitados se autorizan explícitamente en este
   tenant. No otorgar permisos de aplicación a servicios sin usuario.

El Client ID de acceso es distinto del deployment de Azure OpenAI y de la
identidad administrada que lee Blob. Ninguno sustituye a los otros.

## 2. Configurar Easy Auth en Container Apps

En **Authentication**, agregar Microsoft como proveedor utilizando la misma App
registration. Suministrar su secreto o certificado mediante la plataforma, no
como variable de React ni dentro de la imagen.

- Proveedor Microsoft habilitado, tenant y emisor v2 explícitos, audiencia igual
  al Client ID de la aplicación. No utilizar `common`, ni admitir otros tenants.
- Configurar **Allow unauthenticated access / AllowAnonymous** en la validación
  global de Easy Auth. Esto permite cargar la pantalla de inicio de sesión y los
  probes. **No abre los expedientes:** la API realiza autenticación y autorización
  en todas sus rutas de datos. No usar redirecciones HTML como respuesta a APIs.
- Habilitar **token store** con un contenedor Blob privado dedicado, separado
  de los documentos. Configurar la identidad o secreto que requiera la plataforma
  y su renovación. La sesión debe entregar `X-MS-TOKEN-AAD-ID-TOKEN` al backend.
- Usar HTTPS exclusivamente: en el ingreso, `allowInsecure=false`, puerto destino
  **8000**, sin otro puerto de datos público. No exponer el trabajador.
- No agregar un proxy que elimine el Host original. El único origen admitido debe
  coincidir con `INTEGRITY_PUBLIC_ORIGIN`, sin barra final. Si se usa un dominio
  propio, configurar su certificado y cambiar también la redirect URI.

El código no confía en `X-MS-CLIENT-PRINCIPAL` ni en nombres/roles enviados por el
navegador. Valida criptográficamente el ID token (RS256), tenant, emisor, audiencia,
vigencia, sujeto y roles. Las claves públicas se consultan en una URL fija de
Microsoft derivada del tenant y se almacenan temporalmente en caché.

Easy Auth gestiona el intercambio OIDC, nonce y cookie de sesión. La aplicación
no entrega tokens a React ni los guarda en su base. El token store sí contiene
credenciales de sesión: restringir acceso, respaldos y retención. Permitir salida
HTTPS de la API a `login.microsoftonline.com` para comprobar firmas.

## 3. Variables de la API

Aplicar [api.env.example](../deploy/azure/api.env.example), reemplazando los marcadores:

```env
INTEGRITY_WEB_MODE=entra
INTEGRITY_WORKER_MODE=external
INTEGRITY_PUBLIC_ORIGIN=https://FQDN
INTEGRITY_ENTRA_TENANT_ID=tenant-uuid-en-minusculas
INTEGRITY_ENTRA_CLIENT_ID=client-uuid-en-minusculas
INTEGRITY_ACCESS_POLICY=shared_team
```

Agregar PostgreSQL y Blob según el mismo archivo. La API no recibe la clave del
modelo. El entrypoint valida estas variables y escucha en `0.0.0.0:8000`; rechaza
configuraciones incompletas. El inicio local conserva loopback y no requiere Entra.

La imagen incluye `INTEGRITY_BUILD_REVISION` a partir de `--build-arg REVISION`.
No sobrescribirlo: se muestra al usuario y en `/api/health` autenticado para
comprobar qué commit se publicó. Conservar también el digest de la imagen.

## 4. Inicio, cierre y expiración de sesión

La pantalla ofrece inicio institucional en `/.auth/login/aad`. Una sesión válida
sin rol muestra denegación, no datos. El encabezado identifica al usuario y su
permiso; el rol Reader no muestra acciones de escritura. El backend aplica los
mismos permisos aunque se envíen solicitudes fuera de la interfaz.

Cerrar sesión utiliza `/.auth/logout`; limpiar también la sesión de Entra cuando
corresponda según la política del equipo. Si el ID token vence, la API rechaza la
solicitud y pide iniciar sesión de nuevo. Si persiste, cerrar sesión y volver a
ingresar. Los cambios de roles requieren renovar los tokens; no son revocación
instantánea de un token aún vigente.

Las escrituras exigen el `Origin` HTTPS configurado. No hay CORS abierto ni una
API de automatización sin usuario en este perfil. La identidad registrada en los
eventos es `entra:TENANT_ID:OBJECT_ID`, estable y obtenida del token verificado;
el nombre enviado desde el navegador no puede reemplazarla. Los eventos locales
anteriores se conservan y no se convierten retroactivamente en identidades verificadas.

## 5. Probes y aceptación

- Liveness/startup: `GET /healthz`, puerto 8000. Respuesta mínima `{"status":"ok"}`,
  sin autenticación y sin documentos ni metadatos. No llama a modelos.
- `/api/health` y `/api/session`: requieren rol. Permiten verificar modo, identidad
  y commit desde una sesión válida. No utilizarlos como probes anónimos.
- `python -m src.deployment_check --role api`: configuración, no login real.
- Desde un checkout, ejecutar `python deploy/check_web.py https://FQDN` para
  comprobar frontend, liveness y rechazo anónimo/identidad falsificada, sin escrituras.

Antes de entregar la URL, probar con tres cuentas: Reviewer, Reader y sin rol.
Verificar lectura y exportación de un expediente real de prueba, bloqueo de
escritura para Reader y rechazo de todos los datos para la cuenta sin rol. Cerrar
sesión y verificar que no se pueden volver a leer datos por URLs guardadas.
Repetir después de reiniciar servicios y registrar el commit y digest probados.

## Referencias de configuración

- [Autenticación y comportamiento de acceso de Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/authentication).
- [Proveedor Microsoft Entra y redirect URI](https://learn.microsoft.com/en-us/azure/container-apps/authentication-entra).
- [Token store de Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/token-store).
- [Validación de claims y permisos](https://learn.microsoft.com/en-us/entra/identity-platform/claims-validation).

La suite usa tokens firmados con claves de prueba y servicios aislados. La
configuración del tenant, certificados, políticas de acceso condicional y sesión
de la plataforma se validan en la suscripción real antes de compartir el ambiente.
