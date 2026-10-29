# Arquitectura del pipeline documental

Integrity Tool usa un pipeline determinístico primero y procesamiento asistido solo como apoyo de redacción/contexto. La herramienta no determina irregularidades, responsabilidades ni conclusiones legales.

## Flujo principal

```text
PDF
→ parsing
→ section segmentation
→ clause extraction
→ boilerplate filtering
→ signal extraction
→ taxonomy classification
→ contextualization
→ mitigant detection
→ consolidation
→ prioritization
→ relevance filtering
→ ReviewItem generation
→ expediente / resultado versionado
→ React + PDF.js o adaptador Streamlit
→ export
```

## Objetos intermedios

- `Clause`: unidad documental mínima revisable. Puede quedar excluida de detección si es placeholder, índice, metadata o texto de plantilla.
- `Signal`: indicio textual detectado por taxonomía en una cláusula activa.
- `FindingCandidate`: señal enriquecida con contexto, mitigantes y contexto histórico.
- `ConsolidatedFinding`: agrupación determinística de señales equivalentes o relacionadas.
- `ReviewItem`: objeto visible para el usuario. Es lo único que debería renderizar Streamlit como observación principal.

## Responsabilidades

- `parser.py`: extrae texto por página.
- `document_segmenter.py`: segmenta páginas en zonas documentales amplias.
- `clause_extractor.py`: genera `Clause[]`.
- `boilerplate_filter.py`: clasifica placeholders, texto de plantilla, índice, metadata o cláusulas no sustantivas.
- `detector.py`: genera `Signal[]` desde cláusulas activas usando la taxonomía YAML.
- `schedule_analyzer.py`: analiza fechas y cronogramas concretos cuando existe evidencia suficiente; no genera observaciones visibles sobre índices o referencias genéricas.
- `taxonomy_loader.py` y `patterns/risk_taxonomy.yaml`: cargan patrones editables, dimensiones y lenguaje permitido.
- `mitigants.py`: detecta equivalencias, justificaciones y mitigantes textuales.
- `contextualizer.py`: construye `FindingCandidate[]`.
- `consolidator.py`: deduplica y agrupa señales en `ConsolidatedFinding[]`.
- `relevance_filter.py`: decide qué findings pasan a revisión visible.
- `prioritizer.py`: ordena internamente sin exponer scores de riesgo.
- `review_item_builder.py`: construye `ReviewItem[]` y DataFrame compatible con UI/export.
- `app.py`: renderiza resultados. No debe importar detector, mitigantes, consolidator, relevance filter ni prioritizer.

## Principios

- `Signal != FindingCandidate != ConsolidatedFinding != ReviewItem`.
- No todo indicio textual se muestra al usuario.
- Boilerplate y placeholders se conservan para auditoría pero se excluyen de observaciones visibles.
- La frecuencia alta en corpus funciona como contexto mitigante, no como observación independiente.
- El LLM no decide visibilidad, prioridad ni conclusiones.
- El usuario ve pocos aspectos accionables, con evidencia, mitigantes, preguntas y limitaciones.

## Controles de confiabilidad

- `metadata_reader.py` comparte la lectura CSV entre encabezados y corpus; admite coma, punto y coma y archivos UTF-8 con BOM. Una asociación ambigua no selecciona un proceso arbitrario.
- Las negaciones explícitas se verifican antes de aceptar requisitos o equivalencias. Esta comprobación es textual y local; no constituye interpretación semántica completa.
- El fragmento representativo conserva su página, sección y texto coincidente. Repeticiones en otras páginas permanecen como evidencias adicionales, aunque el texto sea idéntico.
- Repetir una cláusula no aumenta la prioridad. Los requisitos de autorización o respaldo habituales en compras de bienes mantienen revisión general salvo condiciones adicionales explícitas.
- Los intervalos de cronograma conservan ambas evidencias de origen; el cálculo se explica por separado. Los días hábiles son estimados sin feriados y no representan una validación normativa del plazo.
- Una taxonomía ausente detiene el análisis con un mensaje específico. Los errores del motor no se presentan como si el PDF estuviera dañado.
- La exportación conserva `document_id`, `document_sha256`, `rule_id`, `rule_version`, `taxonomy_sha256`, `engine_version`, `timestamp_analisis` y las evidencias.

## Motor compartido y fronteras

`analyze_document_pages()` es la entrada común para corpus y documentos cargados. `analyze_document_bytes()` agrega únicamente lectura del PDF e identidad por SHA-256. El corpus calcula presencia por `pattern_id` a partir de las señales del mismo motor, no de un detector alternativo ni de la visibilidad final. La frecuencia cuenta procesos distintos, no matches. El workbench excluye del histórico el proceso cuyo documento ya está cargado, para evitar autocomparación.

`consolidator.py` agrupa y conserva evidencia; no calcula prioridad. `prioritizer.py` es la etapa de ranking, con mitigantes locales por requisito y máximo contextual entre sus ocurrencias. Una aceptación de equivalentes en otra cláusula no neutraliza una exigencia exclusiva. El motor ya no vuelve a pasar por una segunda consolidación tabular. `observation_filter.py`, `detect_patterns()` y la síntesis tabular anterior quedan como compatibilidad para consumidores antiguos; no deciden la salida de las rutas principales.

Los agrupamientos por patrón son temas de revisión, no prueba de que dos exigencias sean idénticas. Se conservan todos los fragmentos para distinguir requisitos dentro del tema. Los aliases de DataFrame siguen existiendo solo para la interfaz/exportación anterior; su retirada puede hacerse después de validar la mesa nueva.

## Ejecución local y persistencia

`workbench_service.py` coordina una secuencia fija, con un trabajador y hasta cuatro revisiones en curso o espera. No utiliza agentes ni colas externas. `review_store.py` conserva SQLite transaccional: originales, casos, resultados, caché y eventos de revisión. Un reinicio marca los trabajos incompletos como interrumpidos, sin fingir que terminaron. No hay recuperación automática ni cancelación fuerte del proceso de extracción.

La clave del análisis incluye SHA-256 completo, versión de motor/servicio, huella de taxonomía y snapshot del corpus. El nombre de archivo no identifica el contenido. La metadata estructurada por nombre solo se reutiliza si el hash del original coincide. El cache de extracción del corpus conserva estado OCR y versión del extractor. El OCR tiene tiempo máximo por página y límite de píxeles; no hay certificación de exactitud OCR.

Al comenzar una revisión se lee una única copia del YAML y se conserva su contenido exacto y SHA-256 en `taxonomy_snapshots`. Detección, cronograma, corpus y contexto enviado al modelo reciben esa misma copia. El cotejo y las descargas posteriores no vuelven a leer el YAML actual. Las revisiones creadas antes de esta funcionalidad no se completan retroactivamente con reglas de otra fecha. La copia permite inspeccionar el catálogo usado, pero no archiva el código del motor ni el entorno Python: la reproducción íntegra exige conservar también esos componentes y el corpus de referencia.

Las acciones de navegación, PDF, revisión y exportación usan el resultado guardado. Streamlit también conserva el resultado de la ejecución en sesión; sus widgets ya no vuelven a ejecutar el motor completo.

## Expediente y versiones

`case_review.py` agrega referencias entre documentos por patrón y dimensión, conserva documento, página, tipo, versión y evidencias, y mantiene la mayor prioridad sin sumar menciones. Los mitigantes agregados son contexto; no rebajan automáticamente exigencias de otro documento.

La persona indica rol y sustitución de versiones al cargar. Los originales sustituidos permanecen disponibles, pero sus requisitos no se presentan como vigentes. El cotejo entre versiones muestra referencias identificadas, no identificadas o modificadas con ambos fragmentos. No infiere vigencia jurídica, contradicción ni cambio material. El contraste funcional profundo entre cláusulas diferentes de pliego y anexos sigue pendiente de un conjunto validado por especialistas.

El cotejo compara el conjunto de textos de todas las evidencias por patrón y dimensión. No se limita al ejemplo representativo ni considera una repetición o cambio de página como cambio textual. Conserva las referencias anteriores y nuevas para auditoría y distingue las añadidas y retiradas. No detecta modificaciones fuera de los requisitos identificados por las reglas; una referencia no identificada no demuestra que haya sido eliminada del documento.

## Procesamiento asistido acotado

El resultado determinístico se guarda antes de la redacción asistida. Por defecto hay una síntesis y una explicación; el máximo configurable es tres solicitudes lógicas por expediente. Solo se envían fragmentos y patrones pertinentes, no el documento completo ni el catálogo entero. El encabezado no se reescribe mediante LLM. La salida se valida por estructura, completitud y lenguaje; no es un verificador factual independiente.

Cada solicitud tiene timeout y máximo de tokens de salida. El SDK no reintenta implícitamente. Éxitos y fallos se guardan por contenido, configuración de proveedor/modelo y versión de prompt/reglas. Se registra uso reportado por el proveedor; un error de transporte no permite asegurar que no haya facturación. No se realiza una llamada adicional para probar conexión. La interfaz distingue redacción efectivamente utilizada de configuración meramente disponible.

## Interfaz y despliegue

`src/workbench_api.py` expone una API local con carga acotada, estados, originales, revisión y exportación HTML/CSV/JSON. `frontend/` contiene React/TypeScript y PDF.js; el PDF se carga al entrar en lectura detallada, solo se rasteriza la página consultada y el navegador reutiliza el documento. Los resaltados diferencian fragmento localizado de término coincidente; una ubicación no confirmada no se inventa.

El servidor se enlaza a loopback, rechaza hosts y mutaciones de origen ajeno y no habilita CORS abierto. Esto no sustituye autenticación. Los archivos y comentarios son locales, sin identidad institucional verificada, cifrado de base ni administración de retención. No publicar esta API en Internet sin diseñar control de acceso y operación. Streamlit Community Cloud conserva la ruta existente; la mesa nueva necesita otro despliegue.

## Evaluación pendiente

Las pruebas sintéticas verifican contratos, no precisión de revisión institucional. Quedan pendientes benchmark etiquetado, prueba real en Windows, accesibilidad con tecnología asistiva, concurrencia, recuperación/respaldos, aislamiento de PDFs no confiables, licenciamiento de PyMuPDF y selección normativa vigente. La revisión comercial no consulta un mercado exhaustivo ni demuestra exclusividad.

## Mantenimiento de la base pre-PoC

Se retiraron los experimentos de agentes, SQL Server y feedback JSONL sin conexión con la interfaz activa, junto con las vistas Streamlit no alcanzables. El historial Git conserva su código; no se eliminaron corpus, originales ni revisiones locales. La función de correo de Streamlit se conserva porque tiene una ruta activa.

El motor no importa Streamlit ni el SDK de Groq. La mesa instala solo dependencias comunes y de API; Streamlit y pytest se incorporan al instalar sus requisitos específicos. Groq continúa disponible mediante el cliente compatible con OpenAI. No hay bucle de reintentos alrededor del modelo ni reintentos implícitos del SDK.

Las pruebas verifican estos límites y que las funciones de la interfaz Streamlit tengan una ruta de ejecución. TypeScript rechaza variables e imports sin uso. La prueba de Streamlit identifica `app.py` con una ruta absoluta derivada del archivo de prueba, sin depender de cómo una versión del framework resuelva rutas relativas.

Las APIs tabulares anteriores se conservan temporalmente porque todavía tienen pruebas de regresión específicas. Retirarlas exige migrar esos casos al contrato `ReviewItem` y comprobar equivalencia; no se eliminaron pruebas para reducir artificialmente la superficie mantenida. Esta limpieza no amplía el catálogo de detección ni constituye calibración de precisión con SERCOP.
