# Instalación para SERCOP en una VM Linux

Modalidad portable de la pre-PoC: **HTTPS → API e interfaz → PostgreSQL + archivos persistentes**, con un trabajador independiente. Utiliza usuarios locales; no requiere cuentas Microsoft. Azure OpenAI y el despliegue con Entra siguen siendo opciones independientes.

Esta receta puede ejecutarse en una VM del centro de datos de SERCOP o en una
nube elegida por la institución. No exige Azure Container Apps, Entra ID ni Blob
Storage. `onprem` es el nombre del **perfil portable de configuración**, no una
restricción sobre dónde se aloja la VM. El perfil específico `azure` mantiene
requisitos distintos; no utilizarlo para configurar proveedores alternativos.
Entregar y construir la rama `fusion`, registrando el commit y digest de imagen.

**Antes de compartir:** completar la aceptación en la VM asignada. El [registro de pruebas](onprem_validation.md) distingue lo comprobado en laboratorio de lo pendiente. No presupone disponibilidad de Docker, Podman, certificados ni credenciales de SERCOP.

## 1. Requisitos y decisiones de TI

- Linux con un motor OCI y Docker Compose v2 compatible. La receta principal se prueba con Docker Compose; Podman requiere validación específica del proveedor Compose disponible.
- Python 3 y OpenSSL en el puesto/servidor administrador; Git o una copia revisada del repositorio. El runtime de la aplicación y OCR vienen en la imagen.
- Referencia inicial: 4 vCPU, 8 GB RAM y 30 GB libres, **no un dimensionamiento certificado**. Ajustar tras medir los expedientes reales y la retención.
- Nombre DNS, certificado TLS institucional y acceso de red restringido al equipo. El servicio se publica en la raíz de un dominio, no en una subruta.
- PostgreSQL incluido para la prueba, o una base institucional con usuario propietario **sin privilegios de superusuario** y TLS verificado.
- Espacio compartido para un equipo autorizado: todos sus usuarios pueden consultar todos sus expedientes. No es aislamiento multiinstitucional.

Solicitar a TI: versión de RHEL/otro Linux, arquitectura CPU, motor y versión, Compose/proveedor, rootless o rootful, SELinux, DNS/certificados, proxy, PostgreSQL y política de respaldo. No es necesario decidir un proveedor cloud.

La carga y revisión de PDFs funciona sin Internet ni modelos externos una vez
disponibles las imágenes. La demostración de búsqueda 2026 usa la descarga oficial
incluida, con corte al 13/11/2026; otros años requieren salida HTTPS desde la API.
No descarga automáticamente los PDF. Un proveedor de modelos externo requiere
conectividad desde el trabajador y autorización para enviar fragmentos seleccionados.
Un modelo institucional puede mantenerse en la red interna. Confirmar proxy,
certificados de confianza y sincronización de reloj con TI.

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

### Alcance de la portabilidad

La instalación base analiza sin un proveedor de modelos: el Compose tiene
`INTEGRITY_ASSISTED_ENABLED=false`. No se necesita una cuenta ni una licencia de
Azure para usar las reglas, taxonomía, OCR, revisión y exportaciones existentes.
Habilitar asistencia no cambia el proveedor de identidad ni obliga a usar Entra.

| Proveedor seleccionado | Configuración del cliente existente | Condición de uso |
|---|---|---|
| `azure` | Azure OpenAI: endpoint, versión de API, deployment y clave. | Acceso y deployment autorizados, contrato JSON compatible. |
| `openai` | OpenAI o endpoint HTTPS compatible con su API, modelo y clave. | Chat Completions y los parámetros indicados abajo. |
| `groq` | Endpoint Groq fijado en el cliente, modelo y clave. | El modelo seleccionado debe aceptar el contrato enviado. |
| `ollama` | Servicio HTTP interno o HTTPS con endpoint `/v1` y modelo instalado. | Compatibilidad con JSON y validación de la respuesta. |

El servicio del modelo se instala o contrata **por separado**. Este Compose no
descarga modelos ni levanta Ollama, no aprovisiona GPU ni garantiza cuota. Las
referencias de CPU/RAM del apartado 1 corresponden a la aplicación, no al servidor
de inferencia. Dimensionar este último según el modelo y las pruebas acordadas.

La receta base ya fija `INTEGRITY_DEPLOYMENT_PROFILE=onprem`. En este perfil el
validador admite los cuatro proveedores; el perfil `azure` exige Azure OpenAI.
Seleccionar un único proveedor y un único override de modelos. **Solo el trabajador
recibe la configuración y la clave del modelo**, nunca React ni la API.

### Azure OpenAI

Guardar la clave autorizada en `.secrets/model_key`; endpoint, versión y nombre
de deployment van en `.env`, según su ejemplo. No escribir la clave en `.env`,
YAML, comandos de consola ni repositorio. Mantener los permisos de secretos
descritos en el apartado 8. Utilizar el override ya incluido:

```bash
docker compose -f compose.yaml -f deploy/onprem/compose.azure-openai.yaml config --quiet
docker compose -f compose.yaml -f deploy/onprem/compose.azure-openai.yaml up -d --wait api worker proxy
docker compose -f compose.yaml -f deploy/onprem/compose.azure-openai.yaml exec worker python -m src.assistance_check
```

### OpenAI o un endpoint institucional compatible

Después de preparar la instalación, crear el archivo local
`.secrets/compose.model.yaml` con el siguiente contenido. Es configuración del
despliegue, no un cambio al motor Python. No combinarlo con el override de Azure:

```yaml
services:
  worker:
    environment:
      INTEGRITY_ASSISTED_ENABLED: "true"
      INTEGRITY_SEMANTIC_ENABLED: "true"
      INTEGRITY_LLM_MAX_CALLS: ${INTEGRITY_LLM_MAX_CALLS:-2}
      LLM_PROVIDER: openai
      OPENAI_API_KEY_FILE: /run/secrets/model_key
      OPENAI_BASE_URL: ${OPENAI_BASE_URL:-https://api.openai.com/v1}
      OPENAI_MODEL: ${OPENAI_MODEL:?Configure el modelo autorizado}
    secrets:
      - model_key
secrets:
  model_key: {file: "${INTEGRITY_SECRETS_DIR:-./.secrets}/model_key"}
```

Guardar la credencial en `.secrets/model_key`. En `.env`, definir
`OPENAI_MODEL` con el nombre exacto del modelo autorizado y, para un servidor
institucional compatible, `OPENAI_BASE_URL=https://SU-SERVIDOR/ruta/v1` con su
ruta real. El perfil portable exige HTTPS para este endpoint. La autenticación
del conector usa una clave; un servicio con autenticación o protocolo diferentes
puede requerir adaptación. El servidor debe ser alcanzable y su certificado
de confianza para el trabajador; no desactivar la verificación TLS.

### Groq

Usar el mismo archivo local del ejemplo anterior, conservando `secrets` y las
tres variables `INTEGRITY_*`, pero **reemplazar** las variables del proveedor por:

```yaml
      LLM_PROVIDER: groq
      GROQ_API_KEY_FILE: /run/secrets/model_key
      GROQ_MODEL: ${GROQ_MODEL:?Configure el modelo autorizado}
```

La credencial Groq va en `.secrets/model_key`; `GROQ_MODEL` va en `.env`.
No dejar `OPENAI_API_KEY_FILE`, `OPENAI_BASE_URL` ni `OPENAI_MODEL` en este
override. El cliente utiliza el endpoint Groq configurado en código; no es una
variable para conectar otro proveedor.

### Ollama en la red institucional

Usar este contenido alternativo completo en `.secrets/compose.model.yaml`:

```yaml
services:
  worker:
    environment:
      INTEGRITY_ASSISTED_ENABLED: "true"
      INTEGRITY_SEMANTIC_ENABLED: "true"
      INTEGRITY_LLM_MAX_CALLS: ${INTEGRITY_LLM_MAX_CALLS:-2}
      LLM_PROVIDER: ollama
      OLLAMA_BASE_URL: ${OLLAMA_BASE_URL:?Configure el endpoint interno con /v1}
      OLLAMA_MODEL: ${OLLAMA_MODEL:?Configure el modelo instalado}
```

En `.env`, definir por ejemplo
`OLLAMA_BASE_URL=http://servidor-modelos.interno:11434/v1` y
`OLLAMA_MODEL=NOMBRE-EXACTO-INSTALADO`, sustituyendo ambos valores por los reales.
El servicio y el modelo deben existir previamente. **`localhost` dentro del
trabajador es el propio contenedor**, no la VM ni la computadora del administrador.
TI debe proporcionar una dirección de red alcanzable y restringida; si el modelo
está en otro contenedor, acordar su red y DNS. No exponer un servidor de inferencia
sin protección a Internet. Este conector no configura autenticación personalizada
del servicio; evaluar proxy, controles de red y eventual adaptación según TI.

### Aplicar, comprobar y cambiar de proveedor

Para los tres ejemplos locales anteriores:

```bash
docker compose -f compose.yaml -f .secrets/compose.model.yaml config --quiet
docker compose -f compose.yaml -f .secrets/compose.model.yaml up -d --wait worker
docker compose -f compose.yaml -f .secrets/compose.model.yaml exec worker python -m src.assistance_check
```

Crear el archivo y suministrar valores en `.env` no basta: el override debe
aplicarse para entregar esas variables al trabajador. Conservar la misma
combinación de archivos `-f` en las siguientes operaciones. Cambiar proveedor,
endpoint, clave o modelo requiere recrear el trabajador, no reconstruir el motor
de la aplicación. Hacerlo sin trabajos activos; no borrar resultados, caché ni
reservas para forzar nuevas llamadas. Retirar configuraciones de modelos que
ya no se utilicen. No incrustar claves en imágenes ni guardarlas en los volúmenes
de documentos o resultados.

La comprobación anterior es **solo de configuración**: no llama al modelo ni
demuestra conectividad, compatibilidad o calidad. Solo con autorización de uso
de la credencial, tratamiento de datos y eventual costo:

```bash
docker compose -f compose.yaml -f .secrets/compose.model.yaml exec worker python -m src.assistance_check --request-model
```

Para Azure, ejecutar la misma prueba con su propio override:

```bash
docker compose -f compose.yaml -f deploy/onprem/compose.azure-openai.yaml exec worker python -m src.assistance_check --request-model
```

La prueba hace **hasta dos solicitudes con contenido ficticio**, independientes
del presupuesto por expediente; puede tener costo incluso ante un fallo. No se
debe ejecutar en health checks, cada arranque ni CI con credenciales reales.
Después cargar PDFs públicos acordados y comprobar citas, mitigantes, cobertura,
lenguaje, prioridad y procedencia del modelo en resultados/exportación. Comparar
con y sin asistencia, registrar falsos positivos y probar fallo del proveedor.
El presupuesto predeterminado es de dos solicitudes lógicas por expediente, no
un límite monetario global. Configurar cuotas y alertas por separado.

### Contrato técnico y límites

- El cliente envía **Chat Completions** (`model`, `messages`, `response_format`,
  `max_completion_tokens`), con timeout de 20 segundos y sin reintentos del SDK.
  Para Azure/OpenAI/Groq solicita JSON Schema; con Ollama solicita `json_object`
  y valida luego el mismo esquema en Python. Cambiar solo el nombre del modelo
  no asegura que estos parámetros o formatos estén soportados.
- Una respuesta debe ser JSON válido, cumplir los campos y categorías esperados
  y finalizar correctamente. También se comprueban citas y lenguaje. Pasar la
  prueba sintética no demuestra precisión analítica ni ausencia de errores.
- Otro servicio compatible puede usar el conector `openai` si cumple ese contrato.
  Una API nativa distinta, nuevos mecanismos de autenticación o modelos que no lo
  admitan requieren un adaptador y pruebas; no hay compatibilidad universal ni
  conversión automática de protocolos. No hay conectores nativos de Gemini o
  Anthropic en esta entrega.
- La asistencia puede proponer candidatos acotados y redactar explicaciones;
  no decide la prioridad final ni emite conclusiones jurídicas. Sin modelo o si
  falla su respuesta, se conserva la lectura basada en reglas y se informa el estado.
  No hay lectura semántica exhaustiva, búsqueda automática de mercado ni garantía
  de detección completa. Mantener revisión humana.
- Fragmentos y nombres seleccionados pueden salir hacia el proveedor; no se
  anonimizan automáticamente. Incluso con un modelo local, verificar ubicación,
  acceso, registros y retención. Revisar [qué datos recibe y qué hace el motor](ai_engine.md)
  y la [configuración detallada](configuration.md).
- La aceptación en la VM, con el proveedor y modelo elegidos por SERCOP, sigue
  pendiente hasta probar el circuito funcional, persistencia, reinicio y calidad
  con expedientes representativos. RHEL/SELinux y Podman requieren sus pruebas
  específicas; la pre-PoC no equivale a una certificación de producción.

## 6. Persistencia, reinicio y respaldo

Los comandos de este apartado muestran la receta base. Si habilitó un proveedor,
agregar a **cada comando Compose** la misma combinación `-f compose.yaml -f ...`
usada para configurarlo; de lo contrario puede recrear el trabajador con asistencia
desactivada. No cambiar el nombre del proyecto ni eliminar sus volúmenes.

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
