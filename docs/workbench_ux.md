# Mesa de revisión documental

## Organización de la experiencia

La interfaz separa dos tareas: comprender el procedimiento mediante una lectura general y cotejar requisitos en una mesa de revisión detallada. Cada vista presenta la densidad de información adecuada para su tarea y mantiene el vínculo entre observación, documento y evidencia.

La navegación consulta resultados guardados. Abrir un documento, recorrer páginas o revisar comentarios conserva el análisis de la ejecución seleccionada.

## Componentes

- **Entrada operativa:** carga del expediente y continuación de revisiones guardadas.
- **Orientación:** entidad, objeto y procedimiento aparecen una sola vez. La lectura general explica qué conviene validar, sin parafrasear el encabezado.
- **Revisión por evidencia:** cola compacta, PDF dominante y anotación contextual. El aspecto seleccionado, sus referencias y la página consultada permanecen vinculados.
- **Consulta documental:** PDF.js, zoom, páginas, selección de documento, ampliación y descarga del original. Se renderiza una página por vez para limitar memoria y latencia.
- **Menos observaciones, más referencias:** repetición y documentos relacionados se muestran como evidencia de un tema, no como cards duplicadas. Los mitigantes y el corpus se integran en la observación.
- **Revisión humana:** confirmar revisión, descartar, seguimiento y comentario persisten en la base configurada con historial. Confirmar indica que se revisó el aspecto, no que se confirma una conclusión automática. La etiqueta del revisor local no autentica a una persona.
- **Transparencia bajo demanda:** patrón, prioridad, fuentes, mitigantes, límites y uso efectivo del modelo. No se muestran prompts ni razonamiento libre del LLM.
- **Cotejo explícito:** las versiones se relacionan por decisión del usuario. Las diferencias no se presentan como contradicciones comprobadas.
- **Reglas conservadas:** cada revisión nueva permite descargar la taxonomía exacta utilizada, sin sustituirla por el YAML actual.
- **Consulta sin confusión de versiones:** el visor identifica documentos sustituidos y avisa al consultar una página distinta de la evidencia seleccionada. «Volver al fragmento» recupera documento y página; un resaltado parcial no se describe como localización completa.

## Dirección visual

Tipografía de lectura, encabezados serif contenidos, superficies blancas/gris claro, verde institucional reservado a acciones y una referencia dorada discreta. El espacio y la alineación distinguen expediente, documento y anotación. La prioridad se comunica mediante etiquetas de revisión y contexto textual.

La vista general es deliberadamente distinta de la mesa de trabajo. La primera permite orientación; la segunda ofrece densidad útil y regiones de scroll para cotejo prolongado. En pantallas pequeñas las regiones pasan a una secuencia vertical y la cola puede recorrerse horizontalmente, sin comprimir el PDF a una miniatura.

## Tradeoffs y límites

- React/PDF.js permiten controlar la interacción documental y requieren una compilación frontend y una API Python. Ambos componentes utilizan el motor y la taxonomía del repositorio.
- El visor navega por páginas individuales. El fragmento textual está disponible junto al original; el PDF renderizado carece de capa de texto seleccionable.
- Los resaltados por texto extraído no son coordenadas OCR verificadas. Si solo se localiza un término, la interfaz lo indica; no se presenta como ubicación exacta de toda la cláusula.
- El modo de desarrollo usa una etiqueta local. Los perfiles institucionales usan cuentas locales o Entra y muestran identidad y permisos sobre el espacio compartido; la API verifica esos permisos independientemente de los controles visuales. Configurar acceso, conservación y respaldos antes de compartir el ambiente.
- La redacción asistida sigue siendo falible. Se mantiene separada del resultado determinístico y no decide observaciones ni prioridad.

## Verificación y siguiente validación

Se verificaron carga de pliego y especificaciones reales, PDF no blanco, resaltados, zoom, registro de revisión/comentario y ausencia de desbordamiento horizontal en escritorio y móvil. La suite Python cubre motor, caché, versiones, API y exportación; el frontend tiene comprobación TypeScript y build de producción.

La evaluación de comprensión y uso prolongado requiere pruebas con revisores reales: identificar objeto/entidad, abrir dos evidencias, distinguir mitigante de conclusión y registrar una validación pendiente. Se deben medir tiempo, errores de asociación documental y observaciones descartadas por falta de sustento.
