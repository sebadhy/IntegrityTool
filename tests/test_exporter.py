import pandas as pd

from src.analyzer.exporter import ordered_export


def test_ordered_export_drops_duplicate_columns():
    df = pd.DataFrame([["a", "b", "c"]], columns=["finding_id", "finding_id", "otra_columna"])
    exported = ordered_export(df)
    assert exported.columns.tolist().count("finding_id") == 1
    assert "otra_columna" in exported.columns
