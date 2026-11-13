# Buscar procesos en SERCOP

La demostración usa una copia de la descarga oficial de **2026, con corte al
13/11/2026**. Sugerencias, búsqueda paginada y selección de ficha no dependen de
una conexión con SERCOP. La pantalla identifica esta fuente y su fecha. No es
una consulta en tiempo real ni garantiza cobertura de todos los procesos del país.
La [API oficial OCDS](https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/datos-abiertos/api)
se conserva para otros años, sin modelos de lenguaje ni nuevas dependencias.

## Uso

1. Seleccione «Buscar proceso en SERCOP».
2. Seleccione el año. Para 2026 puede buscar por código o palabras clave, solo
   por comprador/proveedor, o consultar la lista sin filtros. Cada filtro no vacío
   requiere al menos tres caracteres.
3. Puede agregar comprador y proveedor mediante desplegables con búsqueda por
   texto sobre el catálogo oficial descargado de 2026 (corte 13/11/2026).
   Código o palabras clave muestra sugerencias de procesos de la misma copia local.
   Puede elegir con el ratón o las flechas y Enter, o escribir texto libre.
4. Revise los resultados paginados y seleccione el proceso correcto.
5. Como alternativa, consulte directamente su OCID.
6. Agregue los originales y confirme que corresponden al proceso antes de iniciar
   la revisión. La vinculación es humana, no un matching documental automático.

Los filtros conservan los nombres año (`year`), palabras clave (`search`),
comprador (`buyer`) y proveedor (`supplier`). `page` controla la paginación.
El frontend indica explícitamente `data_source=snapshot` para 2026. Los totales
y páginas se calculan sobre los **122.264 procesos** de la descarga completa,
no filtrando una página recuperada previamente. Se buscan todas las palabras,
ignorando mayúsculas y acentos, en código/OCID/objeto y nombres según su campo.
Esto no pretende reproducir el algoritmo de búsqueda de la API. Con
`data_source=api` se mantienen los filtros y paginación remotos originales.

La API documenta comprador y proveedor como texto libre, no como catálogos.
Los desplegables usan una instantánea independiente de la descarga masiva oficial,
no opciones extraídas de la página de resultados recuperada. Incluye 4.549 IDs
publicados de comprador y 12.724 de proveedor, con sus variantes de nombre.
Los nombres repetidos se presentan una vez en las sugerencias; esto no fusiona
identidades en la fuente ni cambia la semántica de los filtros de la API.
El catálogo incluye proveedores publicados en adjudicaciones, no todos los
oferentes ni todo el RUP. Para otro año no se presentan estos nombres como si
correspondieran a ese período; sigue disponible la escritura libre. La entidad
contratante y el procedimiento permanecen como datos de la ficha, no como filtros.
Los parámetros de búsqueda no admitidos se rechazan explícitamente.

No se ofrecen CPC, estado o montos como filtros remotos porque el
endpoint utilizado no los documenta. Buscar proveedor puede excluir procesos
que todavía no publican esa información. Cambiar filtros limpia resultados
anteriores; consultar una ficha no inicia un análisis.

### Autocompletado

Las sugerencias se activan desde tres caracteres. Comprador y proveedor se
resuelven localmente, sin salida de red ni modelos de lenguaje. Se admiten
mayúsculas, acentos, partes del nombre e identificadores publicados. La búsqueda
remota recibe siempre el nombre elegido como texto, no un supuesto filtro por ID.

Para 2026, código o palabras clave busca en el archivo local después de 150 ms
sin escribir y devuelve hasta ocho coincidencias, considerando comprador y
proveedor. Buscar y seleccionar una ficha también son operaciones locales.
Para otros años se mantiene la consulta de sugerencias a la API tras 600 ms,
con caché de 60 segundos / 128 consultas y una petición externa simultánea.
Las respuestas antiguas se descartan al cambiar texto, año o filtros. Elegir una
sugerencia no importa fichas ni crea revisiones. La carga de PDF sigue disponible
si falta o no puede abrirse el respaldo.

La instantánea y su procedencia se distribuyen en `src/resources/sercop_catalog_2026.*`:
fecha de publicación, licencia, conteos y SHA256 del ZIP oficial y del catálogo.
No se requiere descargar datos al iniciar ni modificar la configuración del despliegue.
Para actualizarla explícitamente desde el ZIP CSV oficial, sin credenciales:

```bash
python deploy/build_sercop_catalog.py ruta/al/releases_2026.zip --year 2026
python deploy/build_sercop_processes.py ruta/al/releases_2026.zip --year 2026
```

El script conserva IDs y nombres publicados, elimina únicamente pares exactos
repetidos y produce un archivo comprimido reproducible. No debe reemplazarse
la instantánea sin revisar su fecha, cobertura y pruebas. Para incorporar otro
año se debe actualizar también la selección de catálogo y su etiqueta en la UI.

El segundo script crea `src/resources/sercop_processes_2026.sqlite3.gz` y su
manifiesto, con conteos, fecha y SHA256. El archivo comprimido ocupa unos 27 MiB.
La API verifica su huella y descomprime una única copia de solo lectura en un
directorio temporal privado (unos 258 MiB por proceso de API). No escribe en la
imagen ni en la base de revisiones. Se necesita ese espacio libre en `/tmp`.
No se agregan servicios ni dependencias. La copia temporal se regenera al reiniciar;
la fuente comprimida acompaña a la imagen. Actualizar datos requiere ejecutar
explícitamente los scripts y distribuir una nueva versión, no descargar al iniciar.

## Alcance documental

La ficha utiliza únicamente campos publicados. Distingue comprador de entidad
contratante y no completa presupuesto con montos adjudicados o valores unitarios.
Los datos oficiales se incorporan al encabezado cuando están disponibles; se
conservan por separado los candidatos extraídos del PDF y las rutas JSON de origen.

Las referencias documentales en OCDS no garantizan acceso a PDF. Esta entrega no
descarga documentos: los originales se incorporan mediante la carga existente.
Sin originales no se crea una revisión de cláusulas. La disponibilidad del servicio
o de campos incompletos no afecta la carga manual ni revisiones guardadas.

La documentación y las respuestas reales pueden usar distintos envoltorios:
se admiten `releases`, `records[].releases` y `records[].compiledRelease`. Cuando
hay varias entregas parciales sin una versión consolidada única, se informa la
limitación; no se elige arbitrariamente la última ni se inventa un historial.

## Trazabilidad y datos

Cada selección guarda una instantánea con URL, OCID, entrega, fecha de consulta,
publicación y SHA-256. En la modalidad API conserva la respuesta JSON original.
En la copia local conserva un **extracto estructurado de columnas CSV**, identificado
como `sercop_csv_extract/v1` y proveedor `sercop_bulk_csv`, más el hash del ZIP
oficial. No se presenta ese extracto como una respuesta de la API ni como un
registro OCDS completo. Se preservan comprador y entidad contratante por separado.
La instantánea queda vinculada transaccionalmente a la revisión y su identificador
forma parte de la clave de idempotencia. Navegar, exportar o reintentar la revisión
no vuelve a consultar SERCOP.

HTML y CSV incorporan la procedencia; JSON incluye la respuesta o extracto para
auditoría. Esa respuesta puede contener datos públicos de participantes y contactos;
no se muestran en la ficha, pero requieren controles de acceso y retención para
su almacenamiento y distribución institucional.

Una nueva consulta crea una nueva instantánea y no modifica expedientes anteriores.
Los procesos con metadata no se agregan automáticamente al corpus de PDF analizados.
La fuente informa [actualización nocturna](https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/notas-metodologicas),
no disponibilidad en tiempo real ni completitud garantizada.

## Operación y despliegue

- La demostración 2026 no necesita salida HTTPS para buscar o seleccionar.
  Autorizar `datosabiertos.compraspublicas.gob.ec` para consultas de otros años.
- Las rutas y el dominio están fijados en código; no se admiten URL arbitrarias,
  redirecciones ni descarga de enlaces incluidos en los registros.
- Hasta dos solicitudes externas simultáneas por proceso de API, con timeout de
  socket de 12 segundos y respuesta máxima de 8 MiB. No hay reintentos automáticos.
- Los errores se presentan como mensajes recuperables. Buscar o importar no usa
  la clave de modelos ni consume tokens.
- Endpoints internos: `GET /api/sources/sercop/search` y
  `POST /api/sources/sercop/record`, más `GET /api/sources/sercop/suggestions`.
  Todas estas rutas mantienen los controles de acceso de la aplicación.

El esquema versión 2 agrega `source_snapshots` y `case_sources`, sin reescribir
revisiones ni originales. SQLite local se actualiza al iniciar, previo respaldo.
Para PostgreSQL, detener API y trabajador, respaldar y ejecutar con la nueva imagen:

```bash
python -m src.manage_storage init
```

Luego iniciar ambos con la misma versión. Una imagen anterior no debe abrir la
base actualizada: para revertir, restaurar el respaldo y la imagen correspondiente.
La migración offline a otro almacenamiento conserva instantáneas y vínculos.

## Evaluación pendiente

Validar cobertura con una muestra acordada con SERCOP y confirmar una fuente
documental oficial para descarga de pliegos, anexos y adendas. No se implementa
scraping ni automatización de sesiones del portal como reemplazo implícito.
