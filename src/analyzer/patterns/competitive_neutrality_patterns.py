from __future__ import annotations


# Initial curated catalogue for preliminary competitive-neutrality review.
# These patterns are only analytical aids. They do not constitute a legal opinion,
# do not replace human review, and must not be interpreted as accusations.
PATTERNS = [
    {
        "id": "cn-technical-prescriptive",
        "title": "Especificación técnica excesivamente prescriptiva",
        "category": "Requisitos técnicos cerrados",
        "description": (
            "Identifica especificaciones redactadas con rasgos cerrados que podrían "
            "requerir revisión de equivalencias funcionales."
        ),
        "trigger_terms": [
            "características exactas",
            "medidas exactas",
            "modelo exacto",
            "deberá ser exactamente",
            "ficha técnica",
        ],
        "non_restrictive_contexts": [
            "o equivalente",
            "equivalente funcional",
            "mínimo requerido",
        ],
        "escalation_conditions": [
            "ausencia de equivalentes",
            "combinación con fabricante específico",
            "baja frecuencia histórica",
        ],
        "mitigating_terms": ["o equivalente", "equivalente funcional", "mínimo"],
        "suggested_questions": [
            "¿La especificación describe una necesidad funcional verificable?",
            "¿Se aceptan alternativas técnicamente equivalentes?",
        ],
        "output_label": "posible restricción técnica acumulativa",
    },
    {
        "id": "cn-brand-manufacturer-reference",
        "title": "Referencia a marca, fabricante o tecnología específica",
        "category": "Referencias a marca, origen o fabricante",
        "description": (
            "Identifica referencias a marcas, fabricantes o tecnologías que requieren "
            "validar si se usan como referencia abierta."
        ),
        "trigger_terms": ["marca", "fabricante", "tecnología propietaria", "modelo"],
        "non_restrictive_contexts": ["referencial", "o equivalente", "marcas equivalentes"],
        "escalation_conditions": [
            "marca sin equivalentes",
            "fabricante específico",
            "dependencia de soporte exclusivo",
        ],
        "mitigating_terms": ["referencial", "o equivalente", "marcas equivalentes"],
        "suggested_questions": [
            "¿La referencia admite equivalentes funcionales?",
            "¿La mención a marca o fabricante es solo referencial?",
        ],
        "output_label": "aspecto a revisar",
    },
    {
        "id": "cn-specific-experience",
        "title": "Experiencia excesivamente específica",
        "category": "Experiencia o capacidad excesivamente específica",
        "description": "Identifica experiencia formulada de manera muy acotada al objeto o tecnología.",
        "trigger_terms": [
            "experiencia específica",
            "experiencia en el mismo objeto",
            "contratos idénticos",
            "experiencia exclusiva",
        ],
        "non_restrictive_contexts": ["experiencia similar", "experiencia relacionada"],
        "escalation_conditions": [
            "mismo objeto exacto",
            "plazo o monto elevado",
            "pocos oferentes potenciales",
        ],
        "mitigating_terms": ["similar", "relacionada", "equivalente"],
        "suggested_questions": [
            "¿La experiencia solicitada mide capacidad técnica real o replica el objeto exacto?",
            "¿Se aceptan experiencias similares o funcionalmente relacionadas?",
        ],
        "output_label": "consideración analítica",
    },
    {
        "id": "cn-financial-disproportionate",
        "title": "Requisito financiero potencialmente desproporcionado",
        "category": "Experiencia o capacidad excesivamente específica",
        "description": "Identifica requisitos financieros que podrían elevar barreras de entrada.",
        "trigger_terms": ["patrimonio mínimo", "capital mínimo", "índice financiero", "liquidez"],
        "non_restrictive_contexts": ["proporcional", "según presupuesto referencial"],
        "escalation_conditions": ["monto elevado", "sin justificación", "acumulado con experiencia específica"],
        "mitigating_terms": ["proporcional", "justificado", "según presupuesto"],
        "suggested_questions": [
            "¿El requisito financiero guarda relación proporcional con el objeto contractual?",
            "¿Existe justificación técnica o económica para el umbral exigido?",
        ],
        "output_label": "aspecto a revisar",
    },
    {
        "id": "cn-short-deadline",
        "title": "Plazo de presentación potencialmente restrictivo",
        "category": "Combinaciones de requisitos potencialmente limitantes",
        "description": "Identifica plazos que podrían requerir revisión si resultan breves o acumulados.",
        "trigger_terms": ["plazo de presentación", "entrega de ofertas", "término de"],
        "non_restrictive_contexts": ["prórroga", "ampliación de plazo"],
        "escalation_conditions": ["plazo breve", "documentación compleja", "visita obligatoria"],
        "mitigating_terms": ["prórroga", "ampliación", "cronograma actualizado"],
        "suggested_questions": [
            "¿El plazo permite preparar una oferta razonablemente completa?",
            "¿El cronograma considera la complejidad documental del proceso?",
        ],
        "output_label": "consideración analítica",
    },
    {
        "id": "cn-mandatory-site-visit",
        "title": "Visita técnica obligatoria potencialmente restrictiva",
        "category": "Restricciones geográficas o de presencia local",
        "description": "Identifica visitas técnicas obligatorias que podrían limitar participación.",
        "trigger_terms": ["visita técnica obligatoria", "visita obligatoria", "asistencia obligatoria"],
        "non_restrictive_contexts": ["visita opcional", "acta disponible", "registro virtual"],
        "escalation_conditions": ["plazo breve", "presencia física obligatoria", "única fecha"],
        "mitigating_terms": ["opcional", "virtual", "más de una fecha", "acta disponible"],
        "suggested_questions": [
            "¿La visita obligatoria está justificada por la naturaleza del objeto?",
            "¿Existen alternativas documentales o virtuales para participar?",
        ],
        "output_label": "aspecto a revisar",
    },
    {
        "id": "cn-ambiguous-evaluation",
        "title": "Criterio de evaluación ambiguo o discrecional",
        "category": "Combinaciones de requisitos potencialmente limitantes",
        "description": "Identifica criterios de evaluación que requieren trazabilidad objetiva.",
        "trigger_terms": ["a criterio de la entidad", "a satisfacción", "mejor criterio", "idoneidad"],
        "non_restrictive_contexts": ["matriz objetiva", "parámetros verificables", "metodología"],
        "escalation_conditions": ["sin metodología", "sin parámetros", "ponderación discrecional"],
        "mitigating_terms": ["matriz objetiva", "parámetros", "metodología", "verificable"],
        "suggested_questions": [
            "¿El criterio cuenta con parámetros verificables?",
            "¿La evaluación permite trazabilidad y comparación objetiva?",
        ],
        "output_label": "aspecto a revisar",
    },
    {
        "id": "cn-consortium-subcontracting-restriction",
        "title": "Restricción a consorcios o subcontratación",
        "category": "Requisitos regulatorios o habituales",
        "description": "Identifica restricciones de participación conjunta que podrían requerir justificación.",
        "trigger_terms": ["no se permite consorcio", "prohibida la subcontratación", "no se permite subcontratar"],
        "non_restrictive_contexts": ["se permite consorcio", "asociaciones o consorcios"],
        "escalation_conditions": ["sin justificación", "capacidad concentrada", "objeto complejo"],
        "mitigating_terms": ["se permite consorcio", "asociaciones", "subcontratación permitida"],
        "suggested_questions": [
            "¿La restricción a participación conjunta está justificada por el objeto?",
            "¿La regla reduce innecesariamente capacidades complementarias?",
        ],
        "output_label": "consideración analítica",
    },
    {
        "id": "cn-local-presence",
        "title": "Requisito territorial o presencia local previa",
        "category": "Restricciones geográficas o de presencia local",
        "description": "Identifica presencia local previa o domicilio operativo exigido.",
        "trigger_terms": ["presencia local", "domicilio en", "oficina local", "sucursal en"],
        "non_restrictive_contexts": ["atención remota", "cobertura nacional", "instalar durante ejecución"],
        "escalation_conditions": ["presencia previa", "oficina antes de adjudicación", "sin alternativa remota"],
        "mitigating_terms": ["cobertura nacional", "atención remota", "durante ejecución"],
        "suggested_questions": [
            "¿La presencia local previa es necesaria o basta con capacidad de atención?",
            "¿Puede cumplirse la prestación mediante cobertura logística o remota?",
        ],
        "output_label": "aspecto a revisar",
    },
    {
        "id": "cn-frequent-substantive-amendments",
        "title": "Modificaciones frecuentes o sustantivas del pliego",
        "category": "Completitud y trazabilidad documental",
        "description": "Identifica lenguaje asociado a cambios sustantivos que pueden afectar trazabilidad.",
        "trigger_terms": ["modificación del pliego", "reforma al pliego", "alcance modificado", "adenda"],
        "non_restrictive_contexts": ["ampliación de plazo", "publicado para todos"],
        "escalation_conditions": ["cambio sustantivo", "sin ampliación de plazo", "múltiples adendas"],
        "mitigating_terms": ["ampliación de plazo", "publicado", "notificado"],
        "suggested_questions": [
            "¿La modificación fue comunicada de forma clara y accesible?",
            "¿El cambio sustantivo vino acompañado de plazo suficiente?",
        ],
        "output_label": "consideración analítica",
    },
]
