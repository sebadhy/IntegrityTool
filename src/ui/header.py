from __future__ import annotations

import streamlit as st

from src.ui.components import STYLE_PATH


def load_css() -> None:
    if STYLE_PATH.exists():
        st.markdown(
            f"<style>{STYLE_PATH.read_text(encoding='utf-8')}</style>",
            unsafe_allow_html=True,
        )


def render_institutional_header() -> None:
    st.markdown(
        """
        <div class="institutional-shell">
            <div class="top-strip">
                Sistema de análisis preliminar de neutralidad competitiva
            </div>
            <div class="institutional-header">
                <h1>Asistente exploratorio de neutralidad competitiva en pliegos</h1>
                <div class="institutional-subtitle">
                    Identificación preliminar de requisitos potencialmente limitantes en documentos de contratación pública
                </div>
                <div class="method-box">
                    Las señales identificadas son insumos preliminares para revisión humana
                    de neutralidad competitiva. No constituyen dictamen técnico, legal ni
                    determinación de responsabilidad.
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_pipeline() -> None:
    steps = [
        "Extracción documental",
        "Identificación de cláusulas",
        "Comparación histórica",
        "Consolidación analítica",
        "Lectura asistida por IA",
    ]
    html_steps = "".join(f'<div class="pipeline-step">{step}</div>' for step in steps)
    st.markdown(f'<div class="pipeline">{html_steps}</div>', unsafe_allow_html=True)
