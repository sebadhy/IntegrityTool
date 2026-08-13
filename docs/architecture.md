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
→ relevance filtering
→ prioritization
→ ReviewItem generation
→ Streamlit rendering
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
