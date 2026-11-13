# Instalación institucional en una VM Linux

Modalidad portable de la pre-PoC: **HTTPS → API e interfaz → PostgreSQL + archivos persistentes**, con un trabajador independiente. Utiliza usuarios locales; no requiere cuentas Microsoft. Azure OpenAI y el despliegue con Entra siguen siendo opciones independientes.

**Antes de compartir:** completar la aceptación en la VM asignada. El [registro de pruebas](onprem_validation.md) distingue lo comprobado en laboratorio de lo pendiente. No presupone disponibilidad de Docker, Podman, certificados ni credenciales de SERCOP.

## 1. Requisitos y decisiones de TI

- Linux con un motor OCI y Docker Compose v2 compatible. La receta principal se prueba con Docker Compose; Podman requiere validación específica del proveedor Compose disponible.
- Python 3 y OpenSSL en el puesto/servidor administrador; Git o una copia revisada del repositorio. El runtime de la aplicación y OCR vienen en la imagen.
- Referencia inicial: 4 vCPU, 8 GB RAM y 30 GB libres, **no un dimensionamiento certificado**. Ajustar tras medir los expedientes reales y la retención.
- Nombre DNS, certificado TLS institucional y acceso de red restringido al equipo. El servicio se publica en la raíz de un dominio, no en una subruta.
- PostgreSQL incluido para la prueba, o una base institucional con usuario propietario **sin privilegios de superusuario** y TLS verificado.
- Espacio compartido para un equipo autorizado: todos sus usuarios pueden consultar todos sus expedientes. No es aislamiento multiinstitucional.

Solicitar a TI: versión de RHEL/otro Linux, arquitectura CPU, motor y versión, Compose/proveedor, rootless o rootful, SELinux, DNS/certificados, proxy, PostgreSQL y política de respaldo. No es necesario decidir un proveedor cloud.

La carga y revisión de PDFs funciona sin Internet ni modelos externos una vez disponibles las imágenes. La búsqueda de procesos en SERCOP requiere salida HTTPS desde la API a su fuente oficial; no descarga automáticamente los documentos. El procesamiento con Azure OpenAI requiere salida HTTPS desde el trabajador y autorización para enviar fragmentos seleccionados. Confirmar proxy de salida, certificados de confianza y sincronización de reloj con TI.

## 2. Preparar una instalación nueva

En una carpeta nueva, sin sobrescribir configuraciones ni datos existentes:

```bash
git clone --branch fusion --single-branch https://github.com/sebadhy/IntegrityTool.git
cd IntegrityTool
git rev-parse HEAD
cp .env.example .env
```

Editar `.env`: origen HTTPS exacto, puerto, dirección de escucha y etiqueta de imagen. No escribir claves allí. El valor de ejemplo `integrity.example` debe sustituirse por el DNS real. Mantener `127.0.0.1` hasta validar acceso y firewall.

```bash
python3 deploy/onprem/prepare.py --origin https://SU-DNS:8443
docker compose config --quiet
docker compose build --build-arg REVISION="$(git rev-parse HEAD)" api
docker compose run --rm --no-deps storage-init
docker compose up -d --wait db
docker compose run --rm admin -m src.manage_storage init
docker compose run --rm admin -m src.manage_users init-admin SU-USUARIO --name "Nombre del administrador"
docker compose up -d --wait api worker proxy
docker compose ps
```

La contraseña se solicita de forma interactiva (15–256 caracteres); **no hay credenciales predeterminadas**. `storage-init` es una operación puntual para asignar el volumen de originales al UID/GID 10001; API y trabajador se ejecutan sin root.

`prepare.py` genera secretos propios de la instalación y certificados de laboratorio. **El certificado web dura 30 días y no es de confianza pública.** Antes de abrir el servicio al equipo, reemplazar `.secrets/web.crt` (cadena completa) y `.secrets/web.key` por el certificado institucional correspondiente al DNS. No instruir al usuario a ignorar advertencias TLS. Conservar y renovar también la CA/certificado de PostgreSQL antes de 365 días.

El certificado de laboratorio permite pruebas explícitas con `--ca .secrets/web.crt`; el navegador necesita confiar en esa CA/certificado de laboratorio a través de un procedimiento aprobado, o un certificado institucional válido.

Mientras el servicio escucha solo en loopback, ejecutar **desde la VM**:

```bash
python3 deploy/onprem/verify_installation.py --url https://SU-DNS:8443 --connect-address 127.0.0.1 --ca .secrets/web.crt --username SU-USUARIO --exercise
```

La opción de conexión cambia solo la ruta de red: conserva la verificación del hostname y del certificado. Tras instalar el certificado institucional, configurar `INTEGRITY_BIND_ADDRESS` con la IP autorizada de la VM, aplicar el firewall y ejecutar `docker compose up -d --wait proxy`. Repetir la verificación desde un puesto del equipo, sin `--connect-address` ni `--ca` cuando la CA ya sea de confianza. No abrir el acceso antes de validar cuentas y TLS.

## 3. Acceso y usuarios

Abrir el origen HTTPS configurado. Crear cuentas desde consola, no desde un formulario público:

```bash
docker compose run --rm admin -m src.manage_users create USUARIO --name "Nombre" --role reviewer
docker compose run --rm admin -m src.manage_users create CONSULTA --name "Nombre" --role reader
docker compose run --rm admin -m src.manage_users reset-password USUARIO
docker compose run --rm admin -m src.manage_users disable USUARIO
docker compose run --rm admin -m src.manage_users unlock USUARIO
```

- `reader`: consulta originales, resultados y exportaciones; no modifica.
- `reviewer` y `admin`: además cargan y registran revisiones. `admin` es el rol reservado para responsables; **la administración de cuentas es solo por consola del servidor**, no una pantalla web ni una API pública. No se puede deshabilitar al último administrador.
- Hash scrypt (`N=32768, r=8, p=3`) con salt independiente; cookie `Secure`, `HttpOnly`, `SameSite=Strict`; sesión revocable, máximo 8 horas y 30 minutos de inactividad. El factor de trabajo sigue una de las [configuraciones de referencia OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#scrypt); no constituye una certificación de seguridad.
- Cinco intentos fallidos por cuenta en 15 minutos bloquean temporalmente nuevos intentos; límite global adicional de 100. Se conserva en PostgreSQL, incluso si se reinicia la API. El límite global puede afectar a todo el equipo durante un ataque; monitorizar y restringir red.
- Cambio de contraseña o deshabilitación revocan las sesiones del usuario. Para revocar todas: `docker compose run --rm admin -m src.manage_users revoke-all`.
- No incluye MFA, recuperación por correo ni federación LDAP. Evaluar esos requisitos, política de contraseñas comprometidas y eventuales exigencias FIPS antes de producción; Entra permanece disponible como alternativa.

## 4. HTTPS y proxy institucional

La receta incluye Nginx sin privilegios y publica solo HTTPS. API y PostgreSQL no publican puertos al host. El proxy conserva `Host`; la aplicación verifica dominio y origen de las escrituras y no confía en cabeceras de identidad o proxy enviadas por el cliente.

Los enlaces recibidos por correo, WhatsApp, Teams u otros sitios pueden abrir la
página inicial, también con `?revision=...`. Esta excepción solo permite navegación
GET/HEAD a `/` con destino de documento principal: no abre datos, exportaciones,
peticiones desde otros sitios ni documentos embebidos. La sesión y los permisos
siguen siendo obligatorios. No eliminar globalmente `Sec-Fetch-Site` en el proxy
ni desactivar los controles de origen como solución a un error de acceso.

Si TI ya termina TLS en un proxy de **la misma VM**:

```bash
docker compose stop proxy
docker compose -f compose.yaml -f deploy/onprem/compose.institutional-proxy.yaml up -d db api worker
```

Configurar ese proxy para reenviar a `127.0.0.1:8000`, conservar el `Host` original y admitir cargas de hasta 101 MB. El dominio externo debe coincidir exactamente con `INTEGRITY_PUBLIC_ORIGIN`; no usar HTTP para usuarios. Si el proxy es remoto, acordar un canal privado cifrado y una regla de red específica; esta receta no expone automáticamente la API a la LAN.

## 5. Procesamiento asistido opcional

La instalación base analiza sin un proveedor de modelos. Para Azure OpenAI, guardar la clave autorizada en `.secrets/model_key`; endpoint, versión y nombre de deployment van en `.env`, según su ejemplo. **Solo el trabajador recibe la clave**.

```bash
docker compose -f compose.yaml -f deploy/onprem/compose.azure-openai.yaml config --quiet
docker compose -f compose.yaml -f deploy/onprem/compose.azure-openai.yaml up -d --wait api worker proxy
docker compose -f compose.yaml -f deploy/onprem/compose.azure-openai.yaml exec worker python -m src.assistance_check
```

La comprobación anterior no consume solicitudes al modelo. Solo con autorización de costo y uso de la credencial:

```bash
docker compose -f compose.yaml -f deploy/onprem/compose.azure-openai.yaml exec worker python -m src.assistance_check --request-model
```

Después cargar un PDF público acordado y comprobar procedencia y uso efectivo en el resultado. El presupuesto predeterminado es de dos solicitudes lógicas por expediente. Consultar [qué recibe y qué hace el motor](ai_engine.md). Los demás proveedores existentes se configuran mediante un override del trabajador siguiendo [configuración](configuration.md); no requieren cambios al motor. No montar claves de proveedores en la API.

## 6. Persistencia, reinicio y respaldo

Los volúmenes nombrados `database` y `documents` conservan resultados, evidencias, originales, usuarios y sesiones. La cola es una tabla transaccional de PostgreSQL: no requiere Redis. Mantener el mismo nombre de proyecto Compose; cambiarlo crea volúmenes distintos y puede parecer una pérdida de datos.

El corpus histórico es opcional y no viene incluido en la imagen ni en Git. Si se proporciona, montar sus PDFs y CSV de metadata como solo lectura en el trabajador y configurar las rutas `APP_CORPUS_*` descritas en [configuración](configuration.md). No confundir ese corpus con los expedientes cargados por usuarios, que sí se conservan en los volúmenes y la base de esta instalación.

```bash
docker compose restart
docker compose up -d --wait
```

`restart: unless-stopped` recupera procesos que terminan y el arranque del motor. **Un estado unhealthy no provoca por sí solo reinicio automático**: monitorizar `/readyz`, estado del worker y trabajos pendientes. Habilitar el arranque del motor con el administrador del sistema. El reinicio físico debe probarse en la VM asignada.

Para un respaldo consistente de prueba, detener escritores y conservar ambos componentes:

```bash
umask 077
mkdir -p backups
docker compose stop api worker proxy
docker compose exec -T db pg_dump -U postgres -d integrity -Fc > backups/reviews.dump
docker compose run --rm -T --no-deps --entrypoint tar admin -C /var/lib/integrity/documents -czf - . > backups/documents.tgz
docker compose up -d --wait api worker proxy
```

Respaldar también la configuración y los secretos por un canal cifrado institucional, separado de Git; el dump contiene hashes, sesiones y contenido documental. No copiar el directorio de PostgreSQL en caliente.

Restaurar **en otra instalación vacía**, conservando la versión de imagen/esquema y las credenciales de base correspondientes. Inicializar el volumen y arrancar solo `db`; antes de ejecutar migraciones:

```bash
docker compose exec -T db pg_restore -U postgres -d integrity --no-owner --role=integrity < backups/reviews.dump
docker compose run --rm -T --no-deps --entrypoint tar admin -C /var/lib/integrity/documents -xzf - < backups/documents.tgz
docker compose run --rm admin -m src.manage_users revoke-all
docker compose up -d --wait api worker proxy
```

Verificar acceso, originales por SHA256, resultados y comentarios antes de cambiar la URL. Nunca ejecutar `down --volumes` en una instalación con datos que se deban conservar.

## 7. Verificación y aceptación

```bash
python3 deploy/onprem/verify_installation.py --url https://SU-DNS:8443
python3 deploy/onprem/verify_installation.py --url https://SU-DNS:8443 --username SU-USUARIO --exercise
```

La segunda prueba crea un expediente sintético y un comentario; si se habilitó asistencia puede usar el proveedor. Para comprobarlo después de reiniciar, repetir con `--case-id ID` en lugar de `--exercise`. No borrar revisiones para probar persistencia.

El laboratorio automatizado completo usa **dos proyectos nuevos descartables** y no la instalación del administrador:

```bash
python3 deploy/onprem/validate_stack.py --image integrity-tool:onprem --output installation-results.json
```

Comprueba instalación, roles, PDF, worker, originales, exportación, reinicio, recreación, recuperación de reserva y restauración. No certifica RHEL/Podman ni realiza una llamada real al modelo. Registrar PASS, FAIL o NOT TESTED y completar los pendientes de [aceptación](onprem_validation.md).

## 8. Red Hat, SELinux y Podman

- No requiere Windows ni características de un kernel Azure. Las imágenes son OCI Linux. Confirmar CPU, políticas institucionales y acceso al registro; puede transportar imágenes mediante `save/load` o un registro interno sin compilar en la VM.
- Mantener SELinux **enforcing**. Los archivos de configuración montados usan `:ro,Z`; el directorio de secretos es compartido por varios contenedores y requiere etiqueta compartida `container_file_t` en una ruta dedicada. TI debe registrar el contexto con `semanage fcontext` y aplicarlo con `restorecon`; no deshabilitar SELinux ni etiquetar directorios generales del sistema.
- Compose con secretos basados en archivos no cambia UID/GID/modo del archivo. Por eso `.secrets` tiene modo 0700 y los archivos específicamente montados son legibles por el usuario no privilegiado del contenedor. Proteger la carpeta anfitriona y las copias; no usar `chmod 777`. Verificar que solo los servicios declarados reciban cada secreto.
- `podman compose` utiliza un proveedor externo. Confirmar soporte de secretos de archivo, health checks, perfiles, condiciones de dependencia y volúmenes; **OCI no garantiza por sí solo compatibilidad Compose**. No se declara probado si Podman no está disponible.
- Para rootless, conservar puerto alto (8443), revisar mapeo del UID 10001, permisos y etiquetas de volúmenes. Habilitar el servicio de usuario/linger o el mecanismo aprobado por TI para volver a arrancar tras reinicio. No asumir equivalencia de políticas de restart entre proveedores.
- PostgreSQL institucional: montar su CA y ajustar únicamente el archivo `database_url` con `sslmode=verify-full`. Omitir el servicio `db` usando operaciones `--no-deps`, inicializar el esquema con el usuario autorizado y probar conectividad. La receta integrada no exige utilizar su PostgreSQL si TI ya proporciona uno.

Referencias operativas: [secretos Compose](https://docs.docker.com/compose/how-tos/use-secrets/), [proveedor Compose de Podman](https://docs.podman.io/en/latest/markdown/podman-compose.1.html), [sesiones web OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).
