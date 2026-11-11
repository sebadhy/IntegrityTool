# Validación del despliegue portable

## Auditoría y decisiones

Base auditada: `fusion`, commit `2ca05e3`. No se reemplaza el motor documental ni la interfaz.

| Área | Estado encontrado | Decisión |
|---|---|---|
| Aplicación | React/PDF.js servido por FastAPI | Conservar una sola aplicación y origen web. |
| Arranque | `src.container_start` exige contrato Azure/Entra | Añadir perfil `onprem`; conservar `azure` y el modo local loopback. |
| Identidad | JWT Entra firmado, Reader/Reviewer; sin cuentas locales web | Añadir sesiones locales persistentes y administración explícita por consola. |
| Datos | SQLAlchemy, PostgreSQL/SQLite, esquema versionado | Conservar; acceso local en tablas adicionales con versión propia, sin reescribir revisiones existentes. |
| Trabajos | PostgreSQL, reserva con vencimiento y heartbeat, resultados protegidos contra worker obsoleto | Conservar; no añadir broker ni Redis. |
| Originales | SHA256, archivos o Azure Blob | Volumen de archivos compartido por API/worker; Blob sigue disponible. |
| Secretos | Variables de entorno | Admitir archivos montados mediante una lista explícita de variables `_FILE`. Nunca copiar secretos en la imagen. |
| TLS | PostgreSQL remoto `verify-full` | Mantener esa exigencia incluso dentro de Compose; proxy HTTPS configurable. |
| IA | Proveedores existentes, solicitudes acotadas, caché y modo sin asistencia | Conservar; Azure OpenAI opcional solo en worker, sin llamadas en health checks. |
| Runtime | Imagen no root, OCR, frontend compilado; dependencias Azure instaladas | Reutilizar la imagen OCI para ambos perfiles; no duplicar builds ni frameworks. |

Entradas: `src.container_start api|worker`, `src.manage_storage`, `src.manage_users`, `src.deployment_check` y `src.assistance_check`. La cola y las evidencias estructuradas residen en PostgreSQL; no hay un servicio de cola independiente. El corpus es opcional y debe montarse/versionarse por separado.

## Alcance de seguridad

Equipo compartido, no aislamiento por expediente o institución. Las cuentas locales no sustituyen una evaluación de seguridad, MFA o políticas institucionales de identidad. Quien controla el motor de contenedores o la consola de base posee privilegios administrativos: el rol web no limita esos accesos.

Las contraseñas no se almacenan en claro; las sesiones se almacenan por digest. Los datos documentales y el dump requieren protección de disco, respaldos y retención a cargo de TI. No se afirma cifrado de disco por el hecho de usar TLS.

## Resultados reales

Ejecución del 11 de noviembre de 2026. Laboratorio: Docker Engine 29.7.2 (kernel Linux/arm64 de Docker Desktop sobre macOS), Compose 5.5.0; imagen de aplicación `linux/amd64` ejecutada con la compatibilidad del motor. No se presenta esto como una VM RHEL o un reinicio físico. `NOT TESTED` no equivale a aprobado.

Imagen validada: `integrity-tool:onprem-release`, ID `sha256:21dea1b634f3395f5295da979761ad2f905eb1a15aab42cb5435ce615e3d7309`. [Salida real del ciclo completo](onprem_validation_results.json). El código publicado debe reconstruirse con su SHA de Git como `REVISION`; este identificador corresponde a la imagen de laboratorio, no a un despliegue institucional.

| Comprobación | Resultado | Alcance |
|---|---|---|
| Suite Python y contratos existentes | PASS | 450 pruebas aprobadas, 17 omitidas por fixtures/servicios opcionales; bloquea HTTP externo. |
| Compilación Python, TypeScript y build de frontend | PASS | `compileall`, `tsc --noEmit` y build del Dockerfile. |
| Instalación Compose Linux, administrador y login | PASS | Proyectos nuevos y volúmenes vacíos en el motor Linux descrito; contraseña no predeterminada. |
| Roles, revocación y limitación de intentos | PASS | Reader no modifica; logout revoca; bloqueo persiste después de reiniciar API. |
| PDF, trabajo, evidencias y exportaciones | PASS | PDF sintético procesado por worker; original SHA256, comentario, HTML/CSV/JSON. |
| Persistencia y reinicio de servicios | PASS | Reinicio de servicios y recreación completa de contenedores conservan originales, resultados, sesiones y comentarios. |
| Recuperación tras caída y restauración | PASS | Reserva abandonada, salida fatal/reinicio automático del worker, caída de PostgreSQL y reconexión; dump + archivos restaurados en volúmenes nuevos y sesiones revocadas. |
| Navegador escritorio y móvil | PASS | Chrome headless, 1440 y 390 px; ingreso/salida y permisos sin errores JS ni desbordamiento. Certificado de laboratorio aceptado solo en ese contexto de navegador. |
| HTTPS y script del administrador | PASS | `verify_installation.py --exercise`, con certificado y hostname verificados; sin omitir validación TLS. |
| Imagen y conservación del perfil Azure | PASS | No root, OCR, sin secretos/Git/datos en imagen; smoke de API/worker local y JWT Entra firmados sintéticos, sin red ni modelos. |
| Instalación limpia y ciclo Compose en Ubuntu CI | PASS | [Job Linux del commit 642792c](https://github.com/sebadhy/IntegrityTool/actions/runs/43033923523/job/130567706967): imagen construida desde checkout limpio, acceso y ciclo completo, incluida restauración. No certifica RHEL. |
| VM Linux independiente de SERCOP | NOT TESTED | Aún no hay servidor asignado confirmado. |
| Reinicio físico de máquina | NOT TESTED | Requiere VM y coordinación de TI. |
| RHEL con SELinux enforcing | NOT TESTED | Requiere entorno institucional. |
| Podman y su proveedor Compose | NOT TESTED | Binario no disponible en el entorno actual. |
| Azure OpenAI con credencial autorizada real | NOT TESTED | No se dispone de una credencial de prueba autorizada para esta tarea. |
| Login Entra en tenant real | NOT TESTED | Se conservan pruebas criptográficas sintéticas; no sustituyen aceptación Azure. |

Los fallos iniciales de la receta se corrigieron antes de esta pasada: partición accidental de opciones tmpfs en YAML, ejecución del inicializador PostgreSQL en un montaje de solo lectura y temporales Nginx fuera de `/tmp`. El inicializador ahora es SQL y el proxy funciona con raíz de solo lectura. La inyección de falla del worker utiliza un error de permisos en su heartbeat temporal; se comprobó el contador de reinicios del motor, no solo un reinicio solicitado manualmente.

CI detectó además que la comprobación de una ruta del contenedor dependía del sistema operativo del administrador. Se corrigió usando semántica POSIX explícita para el perfil OCI Linux, con pruebas que rechazan rutas relativas y rutas Windows. No se retiraron pruebas ni se desactivó la matriz Windows para resolverlo.

No se enviaron solicitudes al proveedor real ni se expusieron credenciales de la demo. Todas las credenciales del laboratorio y los PDFs fueron ficticios. No se modificó la base de revisiones existente ni el servidor de pruebas del equipo.

## Archivos entregados

- `compose.yaml` y `deploy/onprem/`: aplicación, trabajador, PostgreSQL, proxy HTTPS, secretos y scripts de preparación/verificación. Se reutiliza el `Dockerfile` existente.
- `src/local_auth.py` y `src/manage_users.py`: usuarios, hash, sesiones, limitación de intentos y administración por consola.
- `src/runtime_secrets.py` y `src/healthcheck.py`: secretos montados y comprobaciones sin proveedor de modelos.
- `src/web_access.py`, `src/workbench_api.py`, `src/container_start.py` y `src/deployment_check.py`: selección de perfil, permisos y arranque desacoplado.
- `src/review_worker.py`, `src/analyzer/review_worker.py`, `src/manage_storage.py` y `src/assistance_check.py`: lectura de secretos y heartbeat operacional; se conserva la cola y el pipeline de análisis.
- `frontend/src/LoginPanel.tsx`, `App.tsx`, `types.ts` y `styles.css`: ingreso/salida local y permisos, sin rehacer la interfaz documental.
- `tests/test_local_auth.py`, `test_runtime_secrets.py`, `test_onprem_contract.py` y CI: regresión y ciclo Compose reproducible.
- README, `.env.example` y guías operativas: selección del entorno y separación explícita de resultados PASS/NOT TESTED.

## Aceptación de TI pendiente

1. Confirmar VM, CPU, motor, versión, privilegios, SELinux y arranque del servicio tras reinicio.
2. Instalar certificado/DNS institucional, firewall y protección de secretos/volúmenes.
3. Confirmar PostgreSQL local/institucional, política de backup y restauración con responsables.
4. Ejecutar PDF público acordado y verificar citas, exportación y recuperación tras reinicio físico.
5. Si se habilita Azure OpenAI, autorizar endpoint, deployment, datos y costo; ejecutar prueba sintética y después expediente acordado.
6. Registrar versión de imagen/commit y resultados; compartir la URL solo cuando esa aceptación esté completa.
