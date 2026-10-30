# Arquitectura del pipeline documental

Integrity Tool conserva un pipeline determinístico primero. En la mesa React puede complementarse con propuestas semánticas acotadas que deben superar validación documental y las mismas etapas de consolidación, relevancia y prioridad. La herramienta no determina irregularidades, responsabilidades ni conclusiones legales.

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
→ API FastAPI y React + PDF.js
→ export
```

## Objetos intermedios

- `Clause`: unidad documental mínima revisable. Puede quedar excluida de detección si es placeholder, índice, metadata o texto de plantilla.
- `Signal`: indicio textual detectado por taxonomía en una cláusula activa.
- `FindingCandidate`: señal enriquecida con contexto, mitigantes y contexto histórico.
- `ConsolidatedFinding`: agrupación determinística de señales equivalentes o relacionadas.
- `ReviewItem`: objeto visible para el usuario. La API agrega estos objetos al expediente y la interfaz los muestra con sus evidencias.

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
- `review_item_builder.py`: construye `ReviewItem[]` y el adaptador tabular del motor.
- `workbench_service.py`: coordina el análisis, la asistencia opcional y la persistencia del expediente.
- `src/workbench_api.py`: recibe solicitudes y sirve resultados, originales y exportaciones. No importa detector, mitigantes, consolidator, relevance filter ni prioritizer.
- `frontend/src/`: renderiza el resultado guardado y permite revisar evidencia; no calcula detección ni prioridad.

## Principios

- `Signal != FindingCandidate != ConsolidatedFinding != ReviewItem`.
- No todo indicio textual se muestra al usuario.
- Boilerplate y placeholders se conservan para auditoría pero se excluyen de observaciones visibles.
- La frecuencia alta en corpus funciona como contexto mitigante, no como observación independiente.
- El LLM puede proponer candidatos, pero no asigna prioridad ni determina visibilidad final o conclusiones. Una cita comprobada no demuestra que la interpretación sea correcta.
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

`consolidator.py` agrupa y conserva evidencia; no calcula prioridad. `prioritizer.py` es la etapa de ranking, con mitigantes locales por requisito y máximo contextual entre sus ocurrencias. Una aceptación de equivalentes en otra cláusula no neutraliza una exigencia exclusiva. El motor no vuelve a pasar por una segunda consolidación tabular. `observation_filter.py` y `detect_patterns()` conservan contratos tabulares con pruebas de regresión; no deciden la salida del pipeline activo. La síntesis y el exportador exclusivos de la interfaz retirada se eliminaron.

Los agrupamientos por patrón son temas de revisión, no prueba de que dos exigencias sean idénticas. Se conservan todos los fragmentos para distinguir requisitos dentro del tema. Los aliases de DataFrame quedan como adaptador interno de compatibilidad del motor y sus pruebas, no como una segunda interfaz. La API y sus exportaciones usan el resultado del expediente.

## Ejecución local y persistencia

`workbench_service.py` coordina la misma secuencia fija. `review_store.py` utiliza SQLAlchemy Core con SQLite o PostgreSQL; `document_storage.py` conserva los originales nuevos fuera de la base, en archivos o Azure Blob Storage por SHA-256. Los originales binarios de la pre-PoC siguen siendo legibles. No se introducen agentes ni microservicios.

`analysis_jobs` es la cola persistente. `review_worker.py` reserva un trabajo mediante transacción, propietario, token de reserva y vencimiento. PostgreSQL utiliza bloqueo de fila con SKIP LOCKED; SQLite serializa las transacciones locales. Un heartbeat renueva la reserva y un trabajador vencido no puede publicar resultados. El arranque de la API no interrumpe trabajos de otras instancias.

Las reservas vencidas se recuperan con un máximo de tres intentos. Si ya existe un resultado determinístico comprometido, se conserva y no se repiten solicitudes asistidas inciertas. Una ejecución sin resultado puede reanudarse desde cachés verificables. No hay cancelación fuerte de extracción ni promesa de entrega exactamente una vez.

En local se integra un trabajador. Con `INTEGRITY_WORKER_MODE=external`, la API solo registra trabajo y `python -m src.review_worker` lo procesa. El límite de admisión de la aplicación es preventivo, no un mecanismo de cuotas distribuido. Detalles operativos y límites: [persistencia compartida](shared_storage.md).

La clave del análisis incluye SHA-256 completo, versión de motor/servicio, huella de taxonomía y snapshot del corpus. El nombre de archivo no identifica el contenido. La metadata estructurada por nombre solo se reutiliza si el hash del original coincide. El cache de extracción del corpus conserva estado OCR y versión del extractor. El OCR tiene tiempo máximo por página y límite de píxeles; no hay certificación de exactitud OCR.

Al comenzar una revisión se lee una única copia del YAML y se conserva su contenido exacto y SHA-256 en `taxonomy_snapshots`. Detección, cronograma, corpus y contexto enviado al modelo reciben esa misma copia. El cotejo y las descargas posteriores no vuelven a leer el YAML actual. Las revisiones creadas antes de esta funcionalidad no se completan retroactivamente con reglas de otra fecha. La copia permite inspeccionar el catálogo usado, pero no archiva el código del motor ni el entorno Python: la reproducción íntegra exige conservar también esos componentes y el corpus de referencia.

Las acciones de navegación, PDF, revisión y exportación usan el resultado guardado. No ejecutan de nuevo el motor ni solicitan contenido al modelo. La respuesta de navegación omite el catálogo y las cláusulas/señales internas completas; la exportación JSON conserva el anexo técnico. La base todavía lee un snapshot completo para armar esa respuesta: la optimización de consultas de detalle por demanda queda pendiente.

`analysis_runs`, `review_findings` y `review_evidence` permiten consultar resultados por ejecución, patrón, prioridad y documento, conservando el snapshot. Comentarios y eventos se guardan en una transacción; el cliente envía la revisión esperada para evitar sobrescritura silenciosa. La identidad del actor sigue siendo local, no autenticada.

## Expediente y versiones

`case_review.py` agrega referencias entre documentos por patrón y dimensión, conserva documento, página, tipo, versión y evidencias, y mantiene la mayor prioridad sin sumar menciones. Los mitigantes agregados son contexto; no rebajan automáticamente exigencias de otro documento.

La persona indica rol y sustitución de versiones al cargar. Los originales sustituidos permanecen disponibles, pero sus requisitos no se presentan como vigentes. El cotejo entre versiones muestra referencias identificadas, no identificadas o modificadas con ambos fragmentos. No infiere vigencia jurídica, contradicción ni cambio material. El contraste funcional profundo entre cláusulas diferentes de pliego y anexos sigue pendiente de un conjunto validado por especialistas.

El cotejo compara el conjunto de textos de todas las evidencias por patrón y dimensión. No se limita al ejemplo representativo ni considera una repetición o cambio de página como cambio textual. Conserva las referencias anteriores y nuevas para auditoría y distingue las añadidas y retiradas. No detecta modificaciones fuera de los requisitos identificados por las reglas; una referencia no identificada no demuestra que haya sido eliminada del documento.

## Procesamiento asistido acotado

El resultado determinístico se guarda antes del procesamiento asistido. En la mesa hay por defecto una solicitud semántica y una síntesis; el máximo configurable es tres solicitudes lógicas compartidas. El tercer cupo puede usarse para una explicación. Desactivar la semántica conserva la ruta de narración anterior. El encabezado no se reescribe mediante LLM. La salida se valida por estructura, completitud y lenguaje; no es un verificador factual independiente.

Cada solicitud tiene timeout y máximo de tokens de salida. El SDK no reintenta implícitamente. Éxitos y fallos se guardan por contenido, configuración de proveedor/modelo y versión de prompt/reglas. `assisted_requests` reserva la solicitud antes de contactar al proveedor: otra ejecución no repite una respuesta incierta. Se registra uso reportado por el proveedor; un error de transporte no permite asegurar que no haya facturación. No se realiza una llamada adicional para probar conexión. La interfaz distingue redacción efectivamente utilizada de configuración meramente disponible.

### Propuestas semánticas: primera entrega

`semantic_analyzer.py` selecciona cláusulas activas por documento/sección, excluye versiones sustituidas y limita texto a 12.000 caracteres, 24 cláusulas y 19.000 caracteres de contexto serializado. Las cláusulas mayores de 1.600 caracteres no se truncan: quedan fuera de esta selección y se contabilizan. El catálogo resumido también tiene límite; cualquier patrón no enviado queda registrado. Selección, IDs, cobertura y límites se conservan en `semantic_review.coverage`.

`analyze_clauses_with_llm()` devuelve hasta cuatro propuestas con patrón, cláusula, cita, explicación breve y confianza. El prompt trata el documento como datos no confiables como instrucciones. Esto es una salvaguarda, no una garantía contra inyección de instrucciones. No hay herramientas de ejecución ni navegación habilitadas para el modelo.

`validate_semantic_proposals()` comprueba el contrato, identidad de cláusula enviada/activa, patrón permitido, cita literal con normalización de espacios, negación textual explícita, lenguaje y duplicados patrón/cláusula. La comprobación no demuestra pertinencia semántica; esa calidad debe evaluarse con especialistas. Confianza no se convierte en prioridad. Los mitigantes se calculan con las funciones existentes desde la cláusula completa, no desde el fragmento que el modelo elija omitir ni de mitigantes que afirme libremente.

Los Signals validados pasan a `build_finding_candidates()` y `finalize_candidates()`, compartidos con las reglas. Se reconstruye el resultado antes de reemplazar la base: un fallo no elimina la revisión determinística. La fuente se conserva en Signals, ReviewItems y agregación del expediente. Se registran tanto decisiones aceptadas/rechazadas como integración visible o filtrado posterior por las reglas del dominio.

El análisis básico cacheado guarda `Clause[]` y `Signal[]`, incluidos estados de exclusión, dentro del JSON transaccional existente. No requiere migrar resultados anteriores. La versión del servicio cambia para no confundir cachés anteriores sin cláusulas. Los originales y revisiones previas no se reinterpretan al abrirlos.

El corpus sigue evaluándose con reglas; una propuesta semántica nueva no recibe un aumento por rareza de un detector distinto. Esta entrega no implementa inferencia de contradicciones entre documentos, búsqueda comercial ni lectura exhaustiva. La identidad institucional y el despliegue compartido siguen pendientes.

## Interfaz y despliegue

`src/workbench_api.py` expone una API local con carga acotada, estados, originales, revisión y exportación HTML/CSV/JSON. `frontend/` contiene React/TypeScript y PDF.js; el PDF se carga al entrar en lectura detallada, solo se rasteriza la página consultada y el navegador reutiliza el documento. Los resaltados diferencian fragmento localizado de término coincidente; una ubicación no confirmada no se inventa.

El servidor se enlaza a loopback, rechaza hosts y mutaciones de origen ajeno y no habilita CORS abierto. Esto no sustituye autenticación. Los archivos y comentarios son locales, sin identidad institucional verificada, cifrado de base ni administración de retención. No publicar esta API en Internet sin diseñar control de acceso y operación. La configuración de proveedores no equivale a habilitar un despliegue compartido.

## Evaluación pendiente

Las pruebas sintéticas verifican contratos, no precisión de revisión institucional. Quedan pendientes benchmark etiquetado, prueba real en Windows, accesibilidad con tecnología asistiva, concurrencia, recuperación/respaldos, aislamiento de PDFs no confiables, licenciamiento de PyMuPDF y selección normativa vigente. La revisión comercial no consulta un mercado exhaustivo ni demuestra exclusividad.

## Mantenimiento de la base pre-PoC

Se retiraron los experimentos de agentes, SQL Server y feedback JSONL sin conexión con la interfaz activa. También se retiró la interfaz anterior completa: entrada, ayuda, estilos, correo SMTP y síntesis/exportador exclusivos de esa ruta. El historial Git conserva su código; no se eliminaron corpus, originales, configuración privada ni revisiones locales.

Existe una sola aplicación. `requirements.txt` instala su ejecución local; `requirements-dev.txt` agrega pytest y httpx. `requirements-azure.txt` incluye la misma base y únicamente los adaptadores de PostgreSQL y almacenamiento Azure. SQLAlchemy Core permite compartir consultas sin mantener dos motores de persistencia. El motor analítico no depende de la base elegida ni del SDK de Groq, que continúa disponible mediante el cliente compatible con OpenAI.

Las pruebas verifican estos límites, la ausencia de las entradas retiradas y que los recorridos documentados apunten a la aplicación activa. Las comprobaciones de exportación, navegación sin reprocesamiento y errores de motor/taxonomía cubren la API actual. TypeScript rechaza variables e imports sin uso.

Las acciones oficiales de CI se fijan por commit, con la versión de referencia anotada, y usan Node 24. La descarga del repositorio no conserva credenciales Git en el entorno de las pruebas. Las actualizaciones de estas acciones deben ser explícitas y volver a pasar validación.

Las APIs tabulares del detector y del filtro anterior se conservan temporalmente porque todavía tienen pruebas de regresión específicas. Retirarlas exige migrar esos casos al contrato `ReviewItem` y comprobar equivalencia. Esta limpieza no cambia reglas, prioridades, claves de caché ni resultados existentes, no amplía el catálogo y no constituye calibración de precisión con SERCOP.
