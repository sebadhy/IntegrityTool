"""Canonical field names for the review row dictionary.

The review pipeline produces a dict with these keys. Using constants avoids
silent typos and enables IDE autocomplete in pipeline modules.

The UI (app.py) still accesses them as raw strings — this file bridges the gap.
When a field name needs to change, update the constant here and the pipeline
modules will follow; the UI can be updated separately.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

FINDING_ID = "finding_id"
SIGNAL_ID = "signal_id"
PATTERN_ID = "pattern_id"
PATTERN_NAME = "pattern_name"
TITLE = "title"

# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

PAGE = "página"
FRAGMENT = "fragmento textual"
MATCHED_TEXT = "matched_text"
REPRESENTATIVE_EXCERPT = "representative_excerpt"
ADDITIONAL_EXCERPTS = "additional_excerpts"
RELATED_PAGES = "páginas relacionadas"
OCCURRENCE_COUNT = "occurrence_count"
CLAUSE_EXCERPT = "clause_excerpt"
VISUAL_SEARCH_TEXT = "visual_search_text"
DOCUMENT_SOURCE = "documento origen"

# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

REVIEW_CATEGORY = "categoría de revisión"
REVIEW_THEME = "tema de revisión"
SIGNAL_TYPE_FIELD = "tipo_señal"
COMPETITION_DIMENSION = "competition_dimension"
COMPETITION_DIMENSION_ES = "dimensión competitiva"
DOCUMENT_SECTION = "document_section"
DOCUMENT_SECTION_ES = "sección documental probable"

# ---------------------------------------------------------------------------
# Priority and attention
# ---------------------------------------------------------------------------

ATTENTION_LEVEL = "atención sugerida"
ATTENTION_LEVEL_INTERNAL = "nivel_atencion"
REVIEW_PRIORITY = "review_priority"
REVIEW_PRIORITY_LABEL = "prioridad de revisión"
RELEVANCE = "relevancia_analitica"
ATTENTION_LEVEL_LEGACY = "nivel de atención"

# ---------------------------------------------------------------------------
# Analytical content
# ---------------------------------------------------------------------------

PATTERN_DETECTED = "patrón detectado"
WHY_REVIEW = "por qué se sugiere revisar"
PRUDENT_OBS = "observación prudente"
SUGGESTED_VALIDATION = "validación sugerida"
LEGITIMATE_JUSTIFICATION = "posible justificación legítima"
SUGGESTED_REVIEW = "revisión sugerida"
CONTEXTUAL_COMMENT = "comentario contextual"
COMPETITION_EFFECT = "posible efecto sobre concurrencia"
COMBINATION_NOTE = "combinación relevante"
CONCURRENCE_ELEMENTS = "elementos que favorecen concurrencia"
PRIORITIZATION_EXPLANATION = "explicacion_priorizacion"
PRIORITIZATION_CRITERIA = "criterios_de_priorizacion"

# ---------------------------------------------------------------------------
# Factors
# ---------------------------------------------------------------------------

MITIGATING_FACTORS = "mitigating_factors"
ESCALATION_FACTORS = "escalation_factors"
MISSING_INFORMATION = "missing_information"

# ---------------------------------------------------------------------------
# Corpus / historical
# ---------------------------------------------------------------------------

HISTORICAL_CLASS = "clasificación histórica"
CORPUS_FREQUENCY = "frecuencia en corpus"
CORPUS_FREQUENCY_INTERNAL = "frecuencia_corpus"
COMPARATIVE_INTERPRETATION = "interpretación_comparativa"

# ---------------------------------------------------------------------------
# Normative
# ---------------------------------------------------------------------------

NORMATIVE_PRINCIPLE = "principio_normativo_relacionado"
NORMATIVE_CRITERIA = "criterio_normativo_de_revision"
NORMATIVE_QUESTION = "pregunta_normativa_sugerida"

# ---------------------------------------------------------------------------
# Review priority labels and order (previously duplicated in prioritizer.py
# and observation_filter.py)
# ---------------------------------------------------------------------------

REVIEW_PRIORITY_ORDER = {"priority": 0, "suggested": 1, "general": 2}
REVIEW_PRIORITY_LABELS = {
    "general": "revisión general",
    "suggested": "revisión sugerida",
    "priority": "revisión prioritaria",
}
HISTORY_ORDER = {"Poco frecuente": 0, "Sin histórico": 1, "Intermedio": 2, "Habitual": 3}
