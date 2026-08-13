from __future__ import annotations

import streamlit as st


st.set_page_config(page_title="Ayuda - Integrity Tool", layout="wide")

st.markdown(
    """
<style>
[data-testid="stSidebarNav"] { display: none; }
section[data-testid="stSidebar"] { display: none; }
.help-shell {
    max-width: 1040px;
    margin: 0 auto;
}
.help-topbar {
    background: #003b70;
    color: #ffffff;
    padding: 14px 18px;
    border-radius: 6px;
    font-weight: 700;
    margin-bottom: 22px;
}
.help-card {
    background: #ffffff;
    border: 1px solid #d6dee6;
    border-radius: 8px;
    padding: 18px 20px;
    margin-bottom: 14px;
}
.help-card h2 {
    color: #003b70;
    font-size: 18px;
    margin: 0 0 10px 0;
}
.help-card p, .help-card li {
    color: #333333;
    font-size: 15px;
    line-height: 1.55;
}
.muted {
    color: #5f6b7a;
    font-size: 14px;
}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown('<div class="help-shell">', unsafe_allow_html=True)
st.markdown('<div class="help-topbar">Integrity Tool - ayuda</div>', unsafe_allow_html=True)

st.markdown(
    """
<div class="help-card">
<h2>Qué hace la herramienta</h2>
<p>
Integrity Tool permite cargar un pliego o especificación técnica en PDF y obtener una lectura preliminar orientada a revisión humana.
La herramienta organiza evidencia documental, consolida observaciones y ayuda a priorizar qué aspectos convendría revisar primero.
</p>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class="help-card">
<h2>Cómo interpretar los resultados</h2>
<ul>
<li>Una observación preliminar no es una conclusión legal, técnica ni administrativa.</li>
<li>La prioridad indica orden sugerido de revisión, no nivel de responsabilidad ni severidad jurídica.</li>
<li>Cada observación debe revisarse junto con su fragmento documental, página, mitigantes y preguntas sugeridas.</li>
<li>Los requisitos habituales o regulatorios pueden aparecer como contexto y no necesariamente elevan prioridad.</li>
</ul>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class="help-card">
<h2>Cómo funciona el análisis</h2>
<p>
La herramienta toma un PDF, extrae el texto, organiza el contenido en cláusulas revisables y aplica una taxonomía de señales documentales.
Luego consolida observaciones similares y las presenta con evidencia, mitigantes y preguntas para revisión humana.
</p>
<ol>
<li>PDF cargado por el usuario.</li>
<li>Extracción y estructuración del texto.</li>
<li>Filtrado de índices, placeholders y texto no sustantivo.</li>
<li>Aplicación de taxonomía documental.</li>
<li>Consolidación y priorización de observaciones.</li>
<li>Presentación de evidencia y preguntas sugeridas.</li>
</ol>
<p>
Si existe procesamiento asistido configurado, se utiliza como apoyo para validar metadata y redactar síntesis contextual.
No decide por sí solo qué observaciones se muestran ni reemplaza la revisión humana.
</p>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class="help-card">
<h2>Dimensiones actuales</h2>
<p class="muted">
Las dimensiones son una propuesta inicial de organización analítica y pueden evolucionar con revisión experta.
</p>
<ul>
<li><strong>Neutralidad competitiva:</strong> condiciones que podrían limitar innecesariamente la participación.</li>
<li><strong>Proporcionalidad:</strong> relación entre requisito, objeto, complejidad y alcance del procedimiento.</li>
<li><strong>Barreras de entrada:</strong> condiciones acumulativas, financieras, geográficas o administrativas que dificultan participación.</li>
<li><strong>Interoperabilidad y compatibilidad:</strong> exigencias vinculadas a continuidad operativa o integración técnica.</li>
<li><strong>Trazabilidad regulatoria:</strong> registros, certificaciones, garantías, seguridad, calidad o control regulatorio.</li>
<li><strong>Relación con el objeto contractual:</strong> coherencia entre las condiciones exigidas y la necesidad pública declarada.</li>
</ul>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class="help-card">
<h2>Corpus documental</h2>
<p>
Si existe un corpus local, la herramienta puede comparar patrones con procesos previamente analizados. La comparación ayuda a
contextualizar requisitos frecuentes, identificar condiciones menos habituales y reducir sobreinterpretación de cláusulas comunes.
</p>
<p>
La presencia frecuente de un patrón no implica validez ni invalidez; debe interpretarse con el contexto específico del procedimiento.
</p>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class="help-card">
<h2>Limitaciones</h2>
<ul>
<li>La calidad del resultado depende de la legibilidad del PDF y del texto extraído.</li>
<li>El OCR es un respaldo para documentos escaneados, pero puede requerir validación manual.</li>
<li>La comparación histórica depende de la calidad y cobertura del corpus disponible.</li>
<li>La herramienta no verifica automáticamente mercado, registros sanitarios, disponibilidad comercial ni proveedores reales.</li>
<li>No determina ilegalidad, no detecta corrupción, no confirma direccionamiento y no reemplaza revisión humana competente.</li>
</ul>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class="help-card">
<h2>Ejecución local</h2>

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m streamlit run app.py
```

Windows PowerShell:

```powershell
py -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

<p class="muted">
La aplicación funciona sin claves de LLM. Para habilitar procesamiento asistido, configure un proveedor en <code>.env</code>.
En Windows, Tesseract OCR es opcional y solo se requiere para PDFs escaneados como imagen.
</p>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown("</div>", unsafe_allow_html=True)
