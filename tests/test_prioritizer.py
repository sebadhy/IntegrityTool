import pandas as pd

from src.analyzer.detector import detect_patterns
from src.analyzer.pdf_extractor import PageText
from src.analyzer.prioritizer import prioritize_signals, top_priorities

PROHIBITED = ["red flag", "alto riesgo", "hallazgo crítico", "irregularidad detectada"]


def _df(text):
    findings = detect_patterns([PageText(page_number=1, text=text)])
    rows = [finding.to_dict() for finding in findings]
    df = pd.DataFrame(rows).rename(columns={"categoría": "categoría de revisión"})
    df["tema de revisión"] = df["categoría de revisión"]
    df["frecuencia en corpus"] = "0 de 10 procesos"
    df["clasificación histórica"] = "Poco frecuente"
    df["comentario contextual"] = "Requisito poco frecuente respecto del corpus disponible."
    df["combinación relevante"] = "Se observa combinación de requisitos potencialmente limitantes."
    df["principio_normativo_relacionado"] = "concurrencia"
    df["criterio_normativo_de_revision"] = "Validar proporcionalidad."
    df["elementos que favorecen concurrencia"] = ""
    return prioritize_signals(df)


def test_prioritization_with_accumulated_signals():
    df = _df("Marca ACME sin equivalente, certificación ISO 9001, presencia local y patrimonio mínimo.")
    assert not top_priorities(df).empty
    assert set(df["review_priority"]).issubset({"general", "suggested", "priority"})
    assert "revisión prioritaria" in set(df["prioridad de revisión"]) or "revisión sugerida" in set(df["prioridad de revisión"])


def test_outputs_avoid_prohibited_main_language():
    df = _df("Marca ACME sin equivalente y oficina local antes de adjudicación.")
    checked_columns = [
        "explicacion_priorizacion",
        "posible efecto sobre concurrencia",
        "validación sugerida",
        "prioridad de revisión",
    ]
    text = " ".join(str(value).lower() for column in checked_columns for value in df[column].tolist())
    for word in PROHIBITED:
        assert word not in text
