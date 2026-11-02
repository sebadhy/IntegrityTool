# Buscar procesos en SERCOP

La búsqueda consulta la [API oficial OCDS](https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/datos-abiertos/api)
desde el backend, sin modelos de lenguaje ni nuevas dependencias.

## Uso

1. Seleccione «Buscar proceso en SERCOP».
2. Indique año y código o palabras clave (mínimo tres caracteres).
3. Puede agregar comprador y proveedor mediante desplegables con búsqueda por
   texto y términos recientes de la sesión.
4. Revise los resultados paginados y seleccione el proceso correcto.
5. Como alternativa, consulte directamente su OCID.
6. Agregue los originales y confirme que corresponden al proceso antes de iniciar
   la revisión. La vinculación es humana, no un matching documental automático.

Todos los filtros se envían a la API: año (`year`), palabras clave (`search`),
comprador (`buyer`) y proveedor (`supplier`). `page` controla la paginación.
No se filtran localmente las páginas recibidas ni se consultan fichas adicionales
durante la búsqueda. El total y las páginas son los informados por SERCOP.

La API documenta comprador y proveedor como texto libre, no como catálogos.
Los desplegables muestran términos ya utilizados en esta sesión, sin extraer
opciones de la página recuperada ni impedir nuevos términos. La entidad
contratante y el procedimiento permanecen como datos de la ficha, no como filtros.
Los parámetros de búsqueda no admitidos se rechazan explícitamente.

No se ofrecen CPC, estado o montos como filtros remotos porque el
endpoint utilizado no los documenta. Buscar proveedor puede excluir procesos
que todavía no publican esa información. Cambiar filtros limpia resultados
anteriores; consultar una ficha no inicia un análisis.

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

Cada selección guarda una instantánea con el JSON original, URL, OCID, entrega,
fecha de consulta, fecha de publicación si existe y SHA-256 de los bytes recibidos.
La instantánea queda vinculada transaccionalmente a la revisión y su identificador
forma parte de la clave de idempotencia. Navegar, exportar o reintentar la revisión
no vuelve a consultar SERCOP.

HTML y CSV incorporan la procedencia; JSON incluye la respuesta original para
auditoría. Esa respuesta puede contener datos públicos de participantes y contactos;
no se muestran en la ficha, pero requieren controles de acceso y retención para
su almacenamiento y distribución institucional.

Una nueva consulta crea una nueva instantánea y no modifica expedientes anteriores.
Los procesos con metadata no se agregan automáticamente al corpus de PDF analizados.
La fuente informa [actualización nocturna](https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/notas-metodologicas),
no disponibilidad en tiempo real ni completitud garantizada.

## Operación y despliegue

- Autorizar salida HTTPS a `datosabiertos.compraspublicas.gob.ec` desde la API.
- Las rutas y el dominio están fijados en código; no se admiten URL arbitrarias,
  redirecciones ni descarga de enlaces incluidos en los registros.
- Hasta dos solicitudes externas simultáneas por proceso de API, con timeout de
  socket de 12 segundos y respuesta máxima de 8 MiB. No hay reintentos automáticos.
- Los errores se presentan como mensajes recuperables. Buscar o importar no usa
  la clave de modelos ni consume tokens.
- Endpoints internos: `GET /api/sources/sercop/search` y
  `POST /api/sources/sercop/record`.

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
