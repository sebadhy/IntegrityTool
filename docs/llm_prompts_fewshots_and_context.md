# Prompts, few-shots y ventanas de contexto para el LLM

**Fecha:** mayo 2026  
**Estado:** documento de trabajo — próximos pasos

---

## 1. Situación actual en el código

`llm_reviewer.py` tiene dos funciones de construcción de prompts:

- `_build_document_brief_prompt()` (línea 246): genera la lectura ejecutiva del documento completo
- `_build_finding_prompt()` (línea 289): explica una señal individual

Ambos tienen el mismo patrón estructural: una lista de condiciones negativas ("no hagas esto"), contexto serializado en JSON, y ningún ejemplo de lo que sí se espera. Sin few-shots.

Además:
- `DEFAULT_MODEL = "gpt-5.4-mini"` (línea 29) — este modelo no existe; cualquier deployment sin `.env` falla silenciosamente
- El objeto de contratación llega siempre como `"No disponible en el documento cargado."` (línea 275)
- La taxonomía completa (hasta 12 patrones en JSON) se inyecta en cada llamada de señal individual (línea 307)

---

## 2. Qué falta en los prompts actuales

### 2.1 Ausencia de descripción del lector objetivo

Los prompts saben lo que el modelo no debe hacer, pero no le dicen para quién está escribiendo. Un auditor del SERCOP, un técnico institucional sin formación legal, y un abogado especialista necesitan tres outputs distintos.

Adición sugerida al SYSTEM_PROMPT:

```python
SYSTEM_PROMPT = (
    "Eres un asistente técnico para revisión preliminar de neutralidad competitiva "
    "en documentos de contratación pública de Ecuador. "
    "Tu lector objetivo es un técnico institucional sin formación legal especializada, "
    "que necesita decidir qué cláusulas del documento merecen revisión más detallada "
    "en los próximos 30 minutos. Escribe de forma concisa, orientada a decisión, "
    "sin adornos ni lenguaje acusatorio. "
    # ... resto igual
)
```

### 2.2 Ausencia de formato positivo antes de las restricciones

Los prompts tienen 10 condiciones negativas y 3–4 positivas. Los modelos responden mejor cuando el formato esperado del output se describe antes de las restricciones. Estructura recomendada:

```
[1] Quién eres y para qué
[2] Qué se espera del output (formato, tono, longitud)  
[3] Qué NO hacer (restricciones)
[4] Few-shots
[5] Datos del caso actual
```

### 2.3 Taxonomía completa en cada llamada de señal individual

`_build_finding_prompt()` inyecta `taxonomy_context(limit=6)` en cada llamada individual de explicación de señal. Eso son potencialmente 1.500–2.000 tokens de taxonomía para explicar una señal donde el modelo solo necesita el patrón específico y sus vecinos relacionados.

Reemplazo sugerido: filtrar al patrón relevante + sus `related_patterns`:

```python
def _relevant_taxonomy_context(finding: dict) -> dict:
    pattern_id = finding.get("pattern_id", "")
    result = load_taxonomy()
    for pattern in result.patterns:
        if pattern.id == pattern_id:
            related_ids = set(pattern.related_patterns)
            related = [p.to_dict() for p in result.patterns if p.id in related_ids]
            return {
                "pattern": {
                    "id": pattern.id,
                    "name": pattern.name,
                    "description": pattern.description,
                    "competition_dimension": pattern.competition_dimension,
                    "human_review_questions": pattern.human_review_questions,
                    "possible_legitimate_justifications": pattern.possible_legitimate_justifications,
                },
                "related_patterns": [
                    {"id": p["id"], "name": p["name"]} for p in related
                ],
            }
    return {}
```

Esto reduce el contexto de taxonomía de ~2.000 tokens a ~300 tokens por llamada de señal individual.

---

## 3. Few-shots recomendados

Cuatro casos canónicos para el sistema ecuatoriano. Cubren las cuatro situaciones de priorización más frecuentes.

### Few-shot 1: Marca sin equivalente → prioridad alta

```
### EJEMPLO 1

Señal detectada:
{
  "patron": "marca",
  "pattern_id": "cn-brand-model-provider-reference",
  "fragmento": "... Las luminarias deberán ser marca PHILIPS modelo CorePro LEDBulb ...",
  "pagina": 12,
  "mitigating_factors": [],
  "missing_information": ["No se identifica equivalencia funcional cercana."],
  "escalation_factors": ["No se observa mitigante de equivalencia cerca del fragmento."]
}
Contexto histórico: { "frecuencia": 0.12, "rarity": "Poco frecuente" }

Output esperado:
{
  "plain_language_explanation": "La especificación nombra una marca comercial específica sin indicar que se aceptan productos equivalentes. En ausencia de una cláusula de equivalencia funcional, la mayoría de oferentes que no distribuyan esa marca quedarían excluidos de facto.",
  "why_it_matters": "Este requisito aparece en el 12% del corpus histórico de procesos comparables, lo que lo hace poco frecuente. La combinación de referencia de marca cerrada con baja frecuencia histórica justifica revisión prioritaria de proporcionalidad.",
  "possible_legitimate_justification": "La exigencia podría estar justificada si existe infraestructura instalada de esa marca que requiera compatibilidad, o si hay razones de estandarización documentadas. Convendría verificar si el expediente incluye esa justificación.",
  "suggested_review_action": "Revisar si el documento incluye una cláusula de equivalencia funcional en otro punto del pliego. Si no existe, solicitar justificación técnica de la restricción.",
  "questions_for_reviewer": [
    "¿El pliego incluye en algún punto una cláusula de aceptación de equivalentes funcionales?",
    "¿Existe en el expediente una justificación técnica de la exigencia de esta marca específica?",
    "¿La entidad tiene infraestructura instalada de esta marca que requiera compatibilidad?"
  ]
}
```

### Few-shot 2: Marca con equivalente funcional → prioridad media/baja

```
### EJEMPLO 2

Señal detectada:
{
  "patron": "marca",
  "pattern_id": "cn-brand-model-provider-reference",
  "fragmento": "... Las luminarias deberán ser marca PHILIPS o equivalente funcional que cumpla las mismas especificaciones de potencia y eficiencia luminosa ...",
  "pagina": 12,
  "mitigating_factors": ["o equivalente funcional"],
  "missing_information": [],
  "escalation_factors": []
}
Contexto histórico: { "frecuencia": 0.65, "rarity": "Habitual" }

Output esperado:
{
  "plain_language_explanation": "La especificación nombra una marca pero incluye una cláusula de equivalencia funcional. El documento establece que se aceptarán productos que cumplan las mismas especificaciones técnicas, lo que mantiene la apertura competitiva.",
  "why_it_matters": "Este tipo de referencia es habitual en el corpus histórico y la presencia de la cláusula de equivalencia mitiga el riesgo competitivo. La atención sugerida es baja.",
  "possible_legitimate_justification": "La referencia a marca parece usarse como referencia técnica orientativa, no como requisito cerrado. Esto es una práctica aceptada cuando se acompaña de criterios de equivalencia verificables.",
  "suggested_review_action": "Verificar que los criterios de equivalencia mencionados sean objetivamente verificables durante la evaluación de ofertas.",
  "questions_for_reviewer": [
    "¿Los criterios de equivalencia (potencia, eficiencia luminosa) están suficientemente definidos para ser verificables en evaluación?",
    "¿Los criterios de aceptación de equivalentes son aplicables a oferentes nacionales e internacionales?"
  ]
}
```

### Few-shot 3: Requisito regulatorio habitual → no priorizar por sí solo

```
### EJEMPLO 3

Señal detectada:
{
  "patron": "RUP",
  "pattern_id": "legacy-rup",
  "fragmento": "... El oferente deberá estar inscrito en el Registro Único de Proveedores (RUP) y habilitado al momento de la presentación de la oferta ...",
  "pagina": 3,
  "tipo_senal": "requisito_habitual",
  "mitigating_factors": [],
  "escalation_factors": []
}
Contexto histórico: { "frecuencia": 0.97, "rarity": "Habitual" }

Output esperado:
{
  "plain_language_explanation": "La inscripción en el RUP es un requisito legal habitual para participar en contratación pública ecuatoriana. Su presencia en el pliego no constituye una señal de restricción competitiva.",
  "why_it_matters": "Este requisito aparece en el 97% de los procesos del corpus histórico y está establecido por ley. No requiere priorización como señal de restricción. Solo convendría revisarlo si se combina con condiciones adicionales que lo hagan discriminatorio.",
  "possible_legitimate_justification": "Es un requisito de habilitación legal estándar.",
  "suggested_review_action": "No se sugiere revisión adicional de este requisito de forma aislada.",
  "questions_for_reviewer": [
    "¿El requisito de RUP aparece combinado con condiciones adicionales de habilitación que puedan ser discriminatorias?"
  ]
}
```

### Few-shot 4: Presencia local con justificación técnica → contextual

```
### EJEMPLO 4

Señal detectada:
{
  "patron": "presencia local",
  "pattern_id": "cn-local-presence-requirement",
  "fragmento": "... El proveedor deberá contar con un centro de servicio técnico en la ciudad de Quito o en un radio máximo de 30 km, con capacidad de atención en un plazo máximo de 4 horas para equipos críticos ...",
  "pagina": 18,
  "mitigating_factors": [],
  "possible_justifications": ["por continuidad operativa"],
  "escalation_factors": ["No se observa justificación técnica cercana en el fragmento."]
}
Contexto histórico: { "frecuencia": 0.08, "rarity": "Poco frecuente" }

Output esperado:
{
  "plain_language_explanation": "El documento exige que el proveedor tenga un centro de servicio en un radio de 30 km. El requisito incluye un tiempo de respuesta de 4 horas para equipos críticos, lo que sugiere una justificación operativa.",
  "why_it_matters": "Este tipo de requisito es poco frecuente en el corpus histórico (8% de procesos). Sin embargo, el contexto operativo (equipos críticos, tiempo de respuesta de 4 horas) puede justificarlo. La clave es si la distancia de 30 km es proporcional a esa necesidad o si podría cumplirse con acuerdos de servicio sin presencia física permanente.",
  "possible_legitimate_justification": "Si los equipos son críticos para la operación institucional y requieren atención de emergencia, el requisito podría ser proporcionado. La justificación debe estar documentada en el expediente técnico.",
  "suggested_review_action": "Revisar si el expediente técnico justifica por qué la distancia de 30 km es necesaria para los tiempos de respuesta exigidos, y si se permite cumplir el requisito mediante acuerdos de servicio en lugar de presencia física permanente.",
  "questions_for_reviewer": [
    "¿El expediente técnico documenta por qué se requiere presencia dentro de 30 km específicamente?",
    "¿Se permite cumplir con el tiempo de respuesta de 4 horas mediante acuerdos con servicios técnicos locales, sin requerir oficina propia?",
    "¿Este mismo tiempo de respuesta es exigido en procesos similares del corpus histórico?"
  ]
}
```

---

## 4. Cómo integrar los few-shots en el código

Los few-shots van en el prompt de usuario, no en el system prompt. Se incluyen antes del caso actual.

En `_build_finding_prompt()` (llm_reviewer.py:289), la estructura sería:

```python
def _build_finding_prompt(finding: dict, corpus_context: dict | None) -> str:
    few_shots = _select_few_shots(finding)  # selecciona los 1-2 más relevantes
    
    return (
        "Explica una señal sugerida para revisión humana.\n\n"
        "El lector es un técnico institucional sin formación legal. "
        "Escribe de forma concisa y orientada a decisión.\n\n"
        "Restricciones:\n"
        "- No emitas dictámenes legales ni asignes responsabilidad.\n"
        "- No infieras intención ni proveedor beneficiado.\n"
        "- Distingue requisitos habituales de señales que requieren revisión.\n"
        "- Devuelve únicamente JSON estricto con las claves solicitadas.\n\n"
        f"--- EJEMPLOS ---\n{few_shots}\n--- FIN EJEMPLOS ---\n\n"
        f"--- CASO ACTUAL ---\n"
        f"Señal sugerida:\n{json.dumps(_compact_finding(finding), ensure_ascii=False, indent=2)}\n\n"
        f"Contexto histórico del patrón:\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
        f"Taxonomía del patrón:\n{json.dumps(_relevant_taxonomy_context(finding), ensure_ascii=False, indent=2)}\n"
    )
```

### 4.1 Selección dinámica de few-shots

No incluir siempre los cuatro ejemplos. Seleccionar 1–2 según el tipo de señal del caso actual:

```python
def _select_few_shots(finding: dict) -> str:
    signal_type = finding.get("tipo_señal", "señal_revision")
    pattern_id = finding.get("pattern_id", "")
    has_mitigants = bool(finding.get("mitigating_factors"))
    
    if signal_type == "requisito_habitual":
        return FEWSHOT_3  # regulatorio habitual
    if signal_type == "mitigante_concurrencia":
        return ""  # no necesita few-shot específico
    if "brand" in pattern_id or "marca" in str(finding.get("patrón detectado", "")):
        if has_mitigants:
            return FEWSHOT_2  # marca con equivalente
        return FEWSHOT_1  # marca sin equivalente
    if "local" in pattern_id or "presencia" in str(finding.get("patrón detectado", "")):
        return FEWSHOT_4  # presencia local
    # Default: usar el few-shot más cercano por competition_dimension
    return FEWSHOT_1
```

---

## 5. Guardar casos de éxito como few-shots

Hoy no existe ningún mecanismo para capturar el juicio del revisor y retroalimentar el sistema. Esto es el hueco más importante para mejorar la calidad del LLM a lo largo del tiempo.

### 5.1 Estructura de un caso guardado

```json
{
  "case_id": "case-a3f2b1",
  "timestamp": "2026-05-14T10:23:00Z",
  "pattern_id": "cn-brand-model-provider-reference",
  "signal_type": "señal_revision",
  "has_mitigants": false,
  "rarity": "Poco frecuente",
  "fragment_anonymized": "... deberán ser marca [MARCA_REDACTADA] modelo [MODELO] ...",
  "verdict": "confirmed",
  "reviewer_note": "Marca sin equivalente en pliego de equipos hospitalarios. No había justificación en el expediente.",
  "llm_output_used": { ... },
  "outcome_quality": "high"
}
```

Los campos `verdict` y `outcome_quality` los llena el revisor humano. Los demás se generan automáticamente.

### 5.2 Cómo capturar el juicio en la UI

En `render_finding_explanation()` (app.py:517) o en `render_aspect_card()` (app.py:596), agregar tres botones discretos después de mostrar la explicación:

- ✓ Señal confirmada — el revisor va a investigar esta cláusula
- ✗ Descartada — falso positivo o requisito justificado
- ~ Requiere más contexto — no puede decidir con la información disponible

El clic graba el caso en `data/feedback/cases.jsonl` con el campo `verdict` correspondiente.

### 5.3 Cómo usar los casos guardados como few-shots

Los casos guardados con `verdict = "confirmed"` y `outcome_quality = "high"` son candidatos a few-shots futuros. La selección se puede hacer por:

1. Similaridad de `pattern_id` con el caso actual
2. Presencia/ausencia de mitigantes (misma situación contextual)
3. Rareza histórica similar
4. `rarity` label matching

En el corto plazo: usar manualmente los mejores casos para reemplazar los ejemplos hardcodeados de esta guía. En el mediano plazo: selección automática por los criterios anteriores.

---

## 6. Extracción dinámica del objeto de contratación

Hoy (llm_reviewer.py:275):
```python
"Objeto de contratación: No disponible en el documento cargado.\n\n"
```

El objeto cambia completamente el análisis del LLM. "Adquisición de ambulancias" genera un análisis muy diferente al de "Consultoría para diseño de sistema informático". El modelo necesita este contexto para calibrar qué es proporcional y qué no.

La extracción heurística está descrita en `pdf_ingestion_and_text_treatment.md`, sección 4. Una vez implementada, se conecta así en `_build_document_brief_prompt()`:

```python
def _build_document_brief_prompt(
    document_text: str,
    findings: list[dict],
    corpus_context: dict | None,
    normative_context: dict | None,
    contract_object: str = "No identificado",  # nuevo parámetro
) -> str:
    # ...
    f"Objeto de contratación: {contract_object}\n\n"
    # reemplaza la línea hardcodeada
```

---

## 7. Corrección del modelo por defecto

`DEFAULT_MODEL = "gpt-5.4-mini"` (llm_reviewer.py:29) no es un modelo real. El modelo válido es `gpt-4o-mini`. Cualquier deployment sin la variable `OPENAI_MODEL` en `.env` falla con error de modelo no encontrado.

Corrección inmediata:
```python
DEFAULT_MODEL = "gpt-4o-mini"
```

Y en `.env.example`, agregar todas las variables documentadas:
```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=          # Dejar vacío para OpenAI directo. Para Azure u otro proveedor: https://...
```

---

## 8. Validación real de la conexión LLM

`test_llm_connection()` (llm_reviewer.py:198) retorna True si el modelo devuelve cualquier texto no vacío, aunque no sea "OK". El test no verifica que el modelo responda correctamente a una instrucción concreta.

Mejora mínima:
```python
content = (response.choices[0].message.content or "").strip().upper()
if content == "OK":
    return True, "Conexión LLM OK"
return False, f"La conexión respondió pero con contenido inesperado: '{content[:60]}'"
```

Esto convierte el test en una verificación real de que el modelo sigue instrucciones, no solo que responde.

---

## 9. Resumen de próximos pasos priorizados

### Prioridad 1 — Correcciones sin riesgo, impacto inmediato

1. Corregir `DEFAULT_MODEL = "gpt-4o-mini"` en llm_reviewer.py:29
2. Completar `.env.example` con `OPENAI_MODEL` y `OPENAI_BASE_URL`
3. Mejorar `test_llm_connection()` para verificar "OK" exacto
4. Agregar `extract_contract_object()` e inyectarlo en el prompt (reemplaza "No disponible")

### Prioridad 2 — Few-shots y calidad del LLM

5. Agregar los 4 few-shots de esta guía como constantes en llm_reviewer.py
6. Implementar `_select_few_shots()` para selección dinámica según tipo de señal
7. Reemplazar `taxonomy_context(limit=6)` en `_build_finding_prompt()` por `_relevant_taxonomy_context()`

### Prioridad 3 — Feedback loop y corpus de casos

8. Agregar botones de juicio del revisor en `render_finding_explanation()`
9. Implementar guardado de casos en `data/feedback/cases.jsonl`
10. Documentar proceso manual para convertir casos confirmados en nuevos few-shots
