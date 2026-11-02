# Requisitos verificables y cotejo documental

El motor extrae condiciones cuantificables de cláusulas activas sin depender de
modelos de lenguaje. Un `Requirement` conserva identificadores estables, documento,
cláusula, página, sección, referencia de ítem/lote, atributo, valor decimal, unidad,
condición (mínimo, máximo, exacto o no especificado) y cita literal.

## Alcance inicial

- Memoria RAM y almacenamiento con unidades GB o MB.
- Peso en kg o g.
- Plazos de entrega, ejecución y garantía en días, diferenciando hábiles y calendario.

Solo se reconoce un valor contiguo a una etiqueta explícita. No se reconstruyen
tablas a partir de posiciones, no se convierten unidades ni se interpretan rangos
o alternativas numéricas ambiguas. La extracción no presupone que una condición
sea restrictiva ni la convierte en una observación priorizada.

## Comparación conservadora

Se comparan documentos activos del expediente con la misma referencia explícita
de ítem o lote, atributo y unidad. Los plazos requieren además un mismo hito de
inicio reconocido: firma del contrato, notificación de la orden o pago/recepción
del anticipo. Se omiten documentos marcados como sustituidos.

Las repeticiones preservan sus evidencias sin generar diferencias adicionales.
Si un documento contiene varias condiciones distintas para el mismo grupo, no se
elige una arbitrariamente. La cobertura registra abstenciones por contexto,
condición o hito insuficientes y por falta de otra fuente comparable.

Una diferencia significa **condiciones explícitas distintas**, no contradicción:
dos mínimos distintos, por ejemplo, pueden ser compatibles. La coincidencia de
numeración entre documentos necesita validación humana de que corresponde al
mismo bien; esta etapa no acredita equivalencia de ítems ni prevalencia jurídica.
La ausencia de diferencias no acredita consistencia o revisión integral.

## Trazabilidad y persistencia

Los requisitos se conservan en el análisis versionado y el resultado del cotejo
en el expediente persistido. Los expedientes existentes no se recalculan ni se
modifican sus identificadores o revisiones humanas. La interfaz admite resultados
anteriores que no incluyen estos campos.

La vista «Contrastar condiciones» presenta ambas fuentes y permite consultar cada
página. JSON conserva la estructura completa; CSV distingue requisitos de
observaciones y enlaza los cotejos; HTML incorpora ambas evidencias comparadas.

## Evaluación pendiente

Ampliar atributos y formas de expresión solo después de validar ejemplos reales
con el equipo. Quedan fuera la extracción semántica abierta, la reconstrucción de
tablas complejas, el emparejamiento automático de ítems renumerados y la decisión
sobre qué condición debería aplicar.
