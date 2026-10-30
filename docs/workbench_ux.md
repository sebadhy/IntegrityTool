# Mesa documental: diagnóstico y decisiones de interfaz

## Diagnóstico aplicado

El problema no era solamente la paleta de Streamlit. La experiencia mostraba etapas del sistema, repetía contexto entre bloques y obligaba a leer interpretaciones antes de consultar una evidencia legible. La navegación de widgets podía repetir trabajo de análisis; un cambio visual sin corregir esa relación habría conservado el problema operacional.

También había dos tareas mezcladas: comprender un procedimiento en pocos minutos y cotejar un requisito durante una revisión detallada. Ambas necesitan evidencia, pero no la misma densidad de información.

## Cambios implementados

- **Entrada operativa:** carga del expediente y continuación de revisiones guardadas. Sin métricas promocionales, configuración de modelos ni pipeline como pantalla principal.
- **Orientación:** entidad, objeto y procedimiento aparecen una sola vez. La lectura general explica qué conviene validar, sin parafrasear el encabezado.
- **Revisión por evidencia:** cola compacta, PDF dominante y anotación contextual. El aspecto seleccionado, sus referencias y la página consultada permanecen vinculados.
- **Documento real:** PDF.js, zoom, páginas, selección de documento, ampliación y descarga del original. Se renderiza una página por vez; no una imagen concatenada del PDF.
- **Menos observaciones, más referencias:** repetición y documentos relacionados se muestran como evidencia de un tema, no como cards duplicadas. Los mitigantes y el corpus se integran en la observación.
- **Revisión humana real:** confirmar revisión, descartar, seguimiento y comentario persisten en SQLite con historial. Confirmar indica que se revisó el aspecto, no que se confirma una conclusión automática. La etiqueta del revisor local no autentica a una persona.
- **Transparencia bajo demanda:** patrón, prioridad, fuentes, mitigantes, límites y uso efectivo del modelo. No se muestran prompts ni razonamiento libre del LLM.
- **Cotejo explícito:** las versiones se relacionan por decisión del usuario. Las diferencias no se presentan como contradicciones comprobadas.
- **Reglas conservadas:** cada revisión nueva permite descargar la taxonomía exacta utilizada, sin sustituirla por el YAML actual.
- **Consulta sin confusión de versiones:** el visor identifica documentos sustituidos y avisa al consultar una página distinta de la evidencia seleccionada. «Volver al fragmento» recupera documento y página; un resaltado parcial no se describe como localización completa.

## Dirección visual

Tipografía de lectura, encabezados serif contenidos, superficies blancas/gris claro, verde institucional reservado a acciones y una referencia dorada discreta. Sin gradientes, orbes, gráficas de severidad ni cards anidadas. La estructura distingue expediente, documento y anotación mediante espacio y alineación, no una colección de paneles equivalentes.

La vista general es deliberadamente distinta de la mesa de trabajo. La primera permite orientación; la segunda ofrece densidad útil y regiones de scroll para cotejo prolongado. En pantallas pequeñas las regiones pasan a una secuencia vertical y la cola puede recorrerse horizontalmente, sin comprimir el PDF a una miniatura.

## Tradeoffs y límites

- React/PDF.js permiten controlar la interacción documental, a cambio de una compilación frontend y una API. El motor y la taxonomía no se reescriben. La interfaz anterior se retiró; la mesa documental es la única aplicación soportada.
- La consulta por páginas limita memoria y latencia. No se implementó scroll continuo virtualizado ni capa de texto seleccionable; el fragmento textual sí está disponible junto al original.
- Los resaltados por texto extraído no son coordenadas OCR verificadas. Si solo se localiza un término, la interfaz lo indica; no se presenta como ubicación exacta de toda la cláusula.
- Persistencia local no equivale a gestión institucional multiusuario. Antes de compartir el servidor hacen falta identidad, permisos, política de conservación y respaldo.
- La redacción asistida sigue siendo falible. Se mantiene separada del resultado determinístico y no decide observaciones ni prioridad.

## Verificación y siguiente validación

Se verificaron carga de pliego y especificaciones reales, PDF no blanco, resaltados, zoom, registro de revisión/comentario y ausencia de desbordamiento horizontal en escritorio y móvil. La suite Python cubre motor, caché, versiones, API y exportación; el frontend tiene comprobación TypeScript y build de producción.

Esto no demuestra todavía comprensión en menos de diez segundos ni usabilidad durante ocho horas. La siguiente validación debe pedir a revisores reales identificar objeto/entidad, abrir dos evidencias, distinguir mitigante de conclusión y registrar una validación pendiente. Medir tiempo, errores de asociación documental y observaciones descartadas por falta de sustento.
