import pandas as pd

from src.analyzer.observation_filter import prepare_visible_review_items
from src.analyzer.prioritizer import prioritize_signals


def _row(**overrides):
    base = {
        "finding_id": "f1",
        "pattern_id": "cn-short-submission-deadline",
        "pattern_name": "Plazo reducido de presentación",
        "competition_dimension": "timeline_restriction",
        "signal_type": "contextual_review_signal",
        "tipo_señal": "señal_revision",
        "página": 1,
        "patrón detectado": "Plazo reducido de presentación",
        "fragmento textual": "El plazo de presentación de ofertas será conforme al cronograma del procedimiento.",
        "clause_excerpt": "El plazo de presentación de ofertas será conforme al cronograma del procedimiento.",
        "por qué se sugiere revisar": "Conviene revisar si el plazo es proporcional a la complejidad documental.",
        "observación prudente": "Conviene revisar si el plazo es proporcional a la complejidad documental.",
        "validación sugerida": "Validar proporcionalidad del plazo.",
        "categoría de revisión": "Combinaciones de requisitos potencialmente limitantes",
        "tema de revisión": "Combinaciones de requisitos potencialmente limitantes",
        "clasificación histórica": "Intermedio",
        "frecuencia en corpus": "3 de 10 procesos",
        "comentario contextual": "Comparación disponible.",
        "número de coincidencias": 1,
        "mitigating_factors": [],
        "escalation_factors": [],
        "missing_information": [],
        "human_review_questions": ["¿El plazo es proporcional?"],
        "nivel de atención": "Medio",
        "atención sugerida": "Medio",
        "review_priority": "suggested",
        "prioridad de revisión": "revisión sugerida",
        "relevancia_analitica": "Medio",
        "combinación relevante": "No se observa combinación relevante.",
        "principio_normativo_relacionado": "concurrencia",
        "criterio_normativo_de_revision": "Validar proporcionalidad.",
        "elementos que favorecen concurrencia": "",
        "severity": "medium",
    }
    base.update(overrides)
    return base


def test_semantic_deduplication_consolidates_same_pattern_across_pages():
    df = pd.DataFrame([
        _row(finding_id="f1", **{"página": 3}),
        _row(finding_id="f2", **{"página": 4, "fragmento textual": "El plazo de presentación consta en el cronograma del procedimiento."}),
        _row(finding_id="f3", **{"página": 6, "fragmento textual": "El plazo de presentación será el establecido en el cronograma."}),
    ])
    visible = prepare_visible_review_items(df)
    assert len(visible) == 1
    row = visible.iloc[0]
    assert row["occurrence_count"] == 3
    assert row["related_pages"] == [3, 4, 6]
    assert "cronograma" in row["patrón detectado"].lower() or "plazo" in row["patrón detectado"].lower()
    assert row["representative_excerpt"]


def test_boilerplate_and_placeholders_are_hidden():
    df = pd.DataFrame([
        _row(pattern_id="placeholder", pattern_name="Sin datos", **{"patrón detectado": "Sin datos", "fragmento textual": "Sin datos"}),
        _row(pattern_id="placeholder2", pattern_name="No requerido por la entidad", **{"patrón detectado": "No requerido por la entidad", "fragmento textual": "No requerido por la entidad"}),
    ])
    visible = prepare_visible_review_items(df)
    assert visible.empty


def test_frequent_corpus_general_signal_is_degraded_from_main_list():
    df = pd.DataFrame([
        _row(
            pattern_id="cn-short-submission-deadline",
            review_priority="general",
            escalation_factors=[],
            **{
                "clasificación histórica": "Habitual",
                "frecuencia en corpus": "24 de 24 procesos",
                "prioridad de revisión": "revisión general",
                "nivel de atención": "Bajo",
                "atención sugerida": "Bajo",
            },
        )
    ])
    visible = prepare_visible_review_items(df)
    assert visible.empty


def test_frequent_corpus_with_escalation_remains_visible():
    df = pd.DataFrame([
        _row(
            review_priority="priority",
            escalation_factors=["Lenguaje de exclusividad."],
            **{
                "clasificación histórica": "Habitual",
                "frecuencia en corpus": "24 de 24 procesos",
                "prioridad de revisión": "revisión prioritaria",
            },
        )
    ])
    visible = prepare_visible_review_items(df)
    assert len(visible) == 1


def test_prioritizer_degrades_habitual_without_escalation():
    df = pd.DataFrame([
        _row(
            review_priority="suggested",
            escalation_factors=[],
            **{
                "clasificación histórica": "Habitual",
                "frecuencia en corpus": "24 de 24 procesos",
                "nivel de atención": "Medio",
                "atención sugerida": "Medio",
            },
        )
    ])
    prioritized = prioritize_signals(df)
    assert prioritized.iloc[0]["review_priority"] == "general"
    assert prioritized.iloc[0]["nivel_atencion"] == "Bajo"


def test_empty_or_low_information_observations_are_not_visible():
    df = pd.DataFrame([_row(pattern_id="x", **{"fragmento textual": "N/A", "patrón detectado": "No aplica"})])
    assert prepare_visible_review_items(df).empty
