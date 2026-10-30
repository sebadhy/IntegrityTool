# Protocolo inicial de evaluación de la PoC

Propuesta de trabajo para acordar con SERCOP. No implica validación ni aceptación institucional.

## Hipótesis

1. La revisión documental estructurada ayuda a localizar aspectos útiles con menos trabajo manual.
2. Las propuestas semánticas identifican condiciones relevantes que las reglas omiten, sin agregar ruido desproporcionado.
3. La contextualización mejora comprensión sin inducir sobreconfianza ni sustituir el criterio humano.

## Comparaciones

- A: revisión manual, sin mostrar resultados de la herramienta.
- B: motor de reglas con `INTEGRITY_ASSISTED_ENABLED=false`.
- C: reglas más propuestas y síntesis asistidas, con presupuesto y cobertura registrados.

Congelar commit, taxonomía, documentos, corpus y configuración de modelo por ronda. Conservar resultados anteriores; no compararlos como si se hubieran generado con reglas nuevas. Comparar tareas/documentos equivalentes y alternar asignaciones para reducir el efecto de aprendizaje.

## Conjunto de referencia

Proponer 30-40 expedientes históricos, con muestra y categorías por acordar. Separar calibración y evaluación reservada. Incluir requisitos habituales de bienes, equivalencias negadas y aceptadas, justificaciones, índices, escaneos incompletos y versiones sustituidas. La distribución de casos debe documentarse.

Dos especialistas revisan independientemente qué aspectos merecen validación, con fragmento, página, patrón y justificación. Registrar desacuerdos y resolverlos antes de usar el conjunto como referencia. No asumir que ausencia de observaciones significa ausencia de condiciones revisables.

## Medición

- Utilidad de cada observación, sustentación documental y pertinencia del patrón.
- Falsos positivos, aspectos relevantes omitidos y duplicados.
- Aporte incremental de candidatos semánticos frente al motor sin modelo.
- Errores de negación, equivalencia, alcance de justificativos e interpretación de requisitos habituales.
- Tiempo de revisión y capacidad de localizar/comprobar evidencia.
- Errores inducidos por explicaciones convincentes pero incorrectas.
- Cobertura efectiva, solicitudes, fallos, latencia y consumo reportado por el proveedor.

Reportar por categoría y método, con denominadores y límites de la muestra. Un candidato con cita válida no cuenta automáticamente como acierto. Un candidato rechazado por cita falsa no se muestra como observación, pero sí cuenta al evaluar la calidad del modelo.

## Estado de esta primera entrega

Hay pruebas unitarias e integradas con respuestas simuladas para contratos y fallos. No hay una evaluación institucional anotada ni una afirmación de precisión del proveedor real. El análisis semántico selecciona cláusulas; no revisa todo el expediente ni determina contradicciones entre documentos.

Antes de un acceso compartido se requieren identidad, permisos, retención, respaldo y un entorno aprobado. La identidad local no autentica al funcionario. Acordar el tratamiento de los fragmentos enviados al proveedor y revisar licencias de distribución.

## Decisión de cierre

Acordar metas antes de evaluar. Decidir ampliar, restringir alcance o corregir/repetir según resultados y limitaciones, no por cantidad de observaciones ni calidad aparente de la redacción. Mantener el modelo deshabilitable y una ruta de revisión basada en reglas disponible.
