from __future__ import annotations
import streamlit as st

st.set_page_config(page_title="Documentación — Neutralidad Competitiva", layout="wide")

# Ocultar la navegación automática de páginas
st.markdown("""
<style>
[data-testid="stSidebarNav"] { display: none; }
section[data-testid="stSidebar"] { display: none; }

.doc-header {
    background: linear-gradient(135deg, #1e3a5f 0%, #2d5282 100%);
    color: white; padding: 28px 36px; border-radius: 8px; margin-bottom: 28px;
}
.doc-header h1 { margin: 0; font-size: 22px; font-weight: 700; }
.doc-header p  { margin: 6px 0 0; opacity: .8; font-size: 14px; }

.section-card {
    background: #f8fafc; border: 1px solid #e2e8f0;
    border-radius: 8px; padding: 20px 24px; margin-bottom: 16px;
}
.section-card h3 { margin-top: 0; color: #1e3a5f; font-size: 15px; }

.badge-req  { background:#dbeafe; color:#1e40af; padding:3px 10px; border-radius:12px; font-size:12px; font-weight:600; }
.badge-opt  { background:#dcfce7; color:#166534; padding:3px 10px; border-radius:12px; font-size:12px; font-weight:600; }
.badge-warn { background:#fef9c3; color:#854d0e; padding:3px 10px; border-radius:12px; font-size:12px; font-weight:600; }

.env-block {
    background:#1e293b; color:#e2e8f0; font-family:monospace;
    font-size:13px; padding:16px 20px; border-radius:6px;
    white-space:pre; overflow-x:auto; line-height:1.6;
}
.ui-item { border-left: 3px solid #3b82f6; padding: 10px 16px; margin: 10px 0; background:#f0f7ff; border-radius:0 6px 6px 0; }
.ui-item strong { color: #1e40af; }
.ui-item p { margin: 4px 0 0; font-size:14px; color:#334155; }
.high-badge  { background:#dc2626; color:white; padding:2px 10px; border-radius:12px; font-size:12px; }
.med-badge   { background:#d97706; color:white; padding:2px 10px; border-radius:12px; font-size:12px; }
.low-badge   { background:#16a34a; color:white; padding:2px 10px; border-radius:12px; font-size:12px; }
.step-num { background:#1e3a5f; color:white; border-radius:50%; width:24px; height:24px; display:inline-flex; align-items:center; justify-content:center; font-size:12px; font-weight:700; margin-right:8px; }

a { color: #2563eb; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="doc-header">
    <h1>Documentación — Sistema de análisis de neutralidad competitiva en pliegos</h1>
    <p>Referencia técnica y guía de usuario · Versión PoC · Ecuador</p>
</div>
""", unsafe_allow_html=True)

tab_tech, tab_user = st.tabs(["🔧  Requisitos técnicos e instalación", "📋  Guía de usuario"])


# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — TÉCNICO
# ─────────────────────────────────────────────────────────────────────────────
with tab_tech:

    st.markdown("## Visión general del sistema")
    st.markdown("""
La aplicación es un **pipeline de análisis en 5 pasos** orquestado por Python + Streamlit.
No usa un loop agéntico: cada paso corre en orden fijo, lo que minimiza llamadas al LLM y
evita errores de rate limit.

```
PDF → Extracción de texto → Detección de patrones → Contexto histórico (BD)
    → Lectura LLM (opcional) → Resultados en UI → Notificación por email (si nivel Alto)
```
""")

    # ── Requisitos del sistema ────────────────────────────────────────────────
    st.markdown("## Requisitos del sistema")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("""
<div class="section-card">
<h3>Sistema operativo</h3>
<p>Windows 10/11, Linux o macOS.<br>
Probado principalmente en <strong>Windows 10</strong>.</p>
</div>
""", unsafe_allow_html=True)
    with col2:
        st.markdown("""
<div class="section-card">
<h3>Python</h3>
<p><strong>3.10 o superior</strong> requerido.<br>
Se recomienda usar un entorno virtual (<code>venv</code> o <code>conda</code>).</p>
</div>
""", unsafe_allow_html=True)
    with col3:
        st.markdown("""
<div class="section-card">
<h3>Conectividad</h3>
<p>Acceso a internet para las APIs de LLM.<br>
Acceso a la red donde está SQL Server.</p>
</div>
""", unsafe_allow_html=True)

    # ── Dependencias Python ───────────────────────────────────────────────────
    st.markdown("## Dependencias Python")
    st.markdown("""
Instale con:
```bash
pip install -r requirements.txt
pip install pyodbc
```
""")

    dep_col1, dep_col2 = st.columns(2)
    with dep_col1:
        st.markdown("""
| Paquete | Versión mín. | Uso |
|---------|-------------|-----|
| `streamlit` | 1.35 | Interfaz web |
| `PyMuPDF` | 1.24 | Extracción de texto de PDFs |
| `pandas` | 2.2 | Manejo de datos tabulares |
| `openai` | 1.109 | Cliente para Azure OpenAI y Groq |
| `python-dotenv` | 1.0 | Variables de entorno desde `.env` |
| `PyYAML` | 6.0 | Lectura de taxonomías |
""")
    with dep_col2:
        st.markdown("""
| Paquete | Tipo | Uso |
|---------|------|-----|
| `pyodbc` | <span class="badge-req">Requerido</span> | Conexión SQL Server |
| `pytesseract` | <span class="badge-opt">Opcional</span> | OCR en PDFs escaneados |
| `Pillow` | <span class="badge-opt">Opcional</span> | Imágenes para OCR |
| `Tesseract` | <span class="badge-opt">Opcional</span> | Motor OCR (binario del sistema) |
""", unsafe_allow_html=True)

    st.info("**Tesseract OCR**: solo necesario si sus PDFs son documentos escaneados (imagen, no texto seleccionable). "
            "Descarga para Windows: https://github.com/UB-Mannheim/tesseract/wiki")

    # ── SQL Server ────────────────────────────────────────────────────────────
    st.markdown("## Base de datos — SQL Server")
    col_db1, col_db2 = st.columns([1.2, 1])
    with col_db1:
        st.markdown("""
<div class="section-card">
<h3>Requisitos de la BD</h3>
<ul>
<li>SQL Server 2016 o superior</li>
<li>ODBC Driver 17 (o 18) for SQL Server instalado en el equipo donde corre la app</li>
<li>Usuario con permisos de CREATE TABLE, INSERT, UPDATE, SELECT en la base de datos</li>
<li>La BD <code>pliegos_analysis</code> debe existir (o el usuario debe poder crearla)</li>
</ul>
</div>
""", unsafe_allow_html=True)
    with col_db2:
        st.markdown("""
<div class="section-card">
<h3>Tablas que crea la app</h3>
<ul>
<li><code>corpus_documentos</code> — histórico de análisis</li>
<li><code>notificacion_destinatarios</code> — lista de emails</li>
<li><code>procesos</code> — metadata de procesos</li>
<li><code>agent_runs</code> — ejecuciones</li>
<li><code>findings</code> — hallazgos individuales</li>
<li><code>agent_briefs</code> — resúmenes ejecutivos</li>
</ul>
</div>
""", unsafe_allow_html=True)

    st.markdown("**Crear/actualizar tablas** (solo necesario la primera vez o tras actualizar el código):")
    st.code("python db.py", language="bash")

    st.markdown("**Driver ODBC**: descargue e instale desde "
                "[Microsoft ODBC Driver for SQL Server]"
                "(https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)")

    # ── LLMs ─────────────────────────────────────────────────────────────────
    st.markdown("## Proveedores LLM")
    st.markdown("La app intenta usar **Azure OpenAI primero**, y si no está configurado usa **Groq**. "
                "Al menos uno de los dos debe estar configurado.")

    llm_col1, llm_col2 = st.columns(2)
    with llm_col1:
        st.markdown("""
<div class="section-card">
<h3>Azure OpenAI <span class="badge-opt">Prioridad 1</span></h3>
<p>Requiere:</p>
<ul>
<li>Endpoint del recurso Azure OpenAI</li>
<li>API Key del recurso</li>
<li>Deployment name (ej: <code>gpt-4o-mini</code>)</li>
<li>API Version: <code>2024-06-01</code></li>
</ul>
<p>Variables: <code>OPENAI_API_KEY</code>, <code>OPENAI_BASE_URL</code>,
<code>OPENAI_API_VERSION</code>, <code>OPENAI_MODEL</code></p>
</div>
""", unsafe_allow_html=True)
    with llm_col2:
        st.markdown("""
<div class="section-card">
<h3>Groq <span class="badge-opt">Fallback gratuito</span></h3>
<p>Requiere:</p>
<ul>
<li>API Key de <a href="https://console.groq.com">console.groq.com</a> (gratis)</li>
<li>Modelo recomendado: <code>llama-3.3-70b-versatile</code></li>
</ul>
<p>Límite gratuito: ~30 req/min, 6000 tokens/min.<br>
Con máximo 2 llamadas por análisis esto es suficiente.</p>
<p>Variable: <code>GROQ_API_KEY</code>, <code>GROQ_MODEL</code></p>
</div>
""", unsafe_allow_html=True)

    # ── Email ─────────────────────────────────────────────────────────────────
    st.markdown("## Email — Gmail SMTP")
    st.markdown("""
<div class="section-card">
<h3>Configuración Gmail</h3>
<p><span class="badge-warn">IMPORTANTE</span> Gmail requiere una <strong>Contraseña de Aplicación</strong>,
no la contraseña normal de la cuenta.</p>
<p><strong>Cómo obtenerla:</strong> Cuenta Google → Seguridad → Verificación en 2 pasos
→ Contraseñas de app → Crear → copiar las 16 letras (formato <code>xxxx xxxx xxxx xxxx</code>)</p>
</div>
""", unsafe_allow_html=True)

    # ── .env completo ─────────────────────────────────────────────────────────
    st.markdown("## Archivo `.env` completo")
    st.markdown("Cree este archivo en la raíz del proyecto (`tenderdocsreview-main/`) con sus valores:")
    st.markdown("""
<div class="env-block"># ── Groq (fallback gratuito) ──────────────────────────────────────────
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.3-70b-versatile

# ── Azure OpenAI (prioridad si está configurado) ──────────────────────
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://su-recurso.openai.azure.com/
OPENAI_API_VERSION=2024-06-01
OPENAI_MODEL=gpt-4o-mini

# ── SQL Server ────────────────────────────────────────────────────────
DB_SERVER=servidor,puerto
DB_NAME=pliegos_analysis
DB_USER=usuario
DB_PASSWORD=contraseña
DB_DRIVER=ODBC Driver 17 for SQL Server

# ── Email / SMTP (Gmail) ──────────────────────────────────────────────
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=su_correo@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx
SMTP_FROM=su_correo@gmail.com</div>
""", unsafe_allow_html=True)

    # ── Instalación y ejecución ───────────────────────────────────────────────
    st.markdown("## Instalación y ejecución")
    st.markdown("""
```bash
# 1. Clonar / descomprimir el proyecto
cd tenderdocsreview-main

# 2. Instalar dependencias
pip install -r requirements.txt
pip install pyodbc

# 3. Crear el archivo .env con sus credenciales

# 4. Crear tablas en SQL Server (solo la primera vez)
python db.py

# 5. Correr la aplicación
streamlit run app.py
```

La app abre automáticamente en **http://localhost:8501**
""")

    # ── Estructura de archivos ────────────────────────────────────────────────
    st.markdown("## Estructura de archivos")
    st.markdown("""
```
tenderdocsreview-main/
│
├── app.py                      ← Aplicación principal Streamlit
├── db.py                       ← Conexión y schema SQL Server
├── notifier.py                 ← Envío de alertas por email
├── agent.py                    ← Agente con tool-use (reservado para batch)
├── tools.py                    ← Herramientas del agente
├── requirements.txt
├── .env                        ← Sus credenciales (NO subir al repo)
│
├── pages/
│   └── Ayuda.py                ← Esta página de documentación
│
├── src/analyzer/
│   ├── pdf_extractor.py        ← Extracción de texto de PDFs + OCR
│   ├── detector.py             ← Detección de patrones por reglas
│   ├── corpus_loader.py        ← Carga de corpus histórico (CSV fallback)
│   ├── llm_reviewer.py         ← Integración LLM (Azure/Groq) con retry
│   ├── review_synthesis.py     ← Enriquecimiento y síntesis de hallazgos
│   ├── prioritizer.py          ← Priorización de señales
│   └── patterns/               ← Reglas de detección en YAML
│
└── data/
    └── raw/
        ├── metadata/procesos.csv  ← Metadata de corpus (fallback sin BD)
        ├── pliegos/               ← PDFs de pliegos para corpus (fallback)
        └── especificaciones/      ← PDFs de especificaciones (fallback)
```
""")

    st.info("La carpeta `data/raw/` solo se usa como **fallback** si SQL Server no está disponible. "
            "Con la BD configurada, el corpus histórico se gestiona automáticamente desde la app.")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — GUÍA DE USUARIO
# ─────────────────────────────────────────────────────────────────────────────
with tab_user:

    st.markdown("## ¿Qué hace esta aplicación?")
    st.markdown("""
Analiza PDFs de pliegos de contratación pública de Ecuador e identifica **señales preliminares
que podrían indicar requisitos diseñados para favorecer a un solo proponente** (amañamiento).

> Las señales son insumos para **revisión humana**. No constituyen dictamen técnico ni legal,
> ni determinan responsabilidad.
""")

    # ── Panel lateral (sidebar) ───────────────────────────────────────────────
    st.markdown("---")
    st.markdown("## Panel lateral (sidebar)")

    st.markdown("""
<div class="ui-item">
<strong>Test LLM</strong>
<p>Verifica que la conexión con el proveedor de inteligencia artificial (Azure OpenAI o Groq) esté
funcionando. Si muestra error, la lectura asistida por IA no estará disponible pero el análisis
por reglas sí funciona.</p>
</div>

<div class="ui-item">
<strong>Destinatarios de alertas</strong>
<p>Lista de correos electrónicos que recibirán la notificación cuando se detecta un nivel de atención Alto.
Puede agregar o quitar destinatarios desde aquí, sin necesidad de acceder a la base de datos directamente.</p>
</div>

<div class="ui-item">
<strong>📖 Documentación y ayuda</strong>
<p>Enlace a esta página. Se abre en una pestaña nueva del navegador.</p>
</div>
""", unsafe_allow_html=True)

    # ── Pantalla principal ────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("## Pantalla principal")

    st.markdown("### 1. Carga del documento")
    st.markdown("""
<div class="ui-item">
<strong>Archivo PDF del pliego</strong>
<p>Suba aquí el PDF del pliego de contratación que desea analizar. Solo admite archivos .pdf.
Si el PDF es un documento escaneado (imagen), se requiere Tesseract OCR instalado para extraer
el texto; de lo contrario se analizarán solo las páginas con texto seleccionable.</p>
</div>

<div class="ui-item">
<strong>Comparar con corpus histórico local</strong>
<p>Cuando está marcado, el sistema compara los patrones encontrados en el documento actual contra
todos los documentos analizados anteriormente (guardados en la BD). Esto permite saber si un
requisito es <em>habitual</em> (aparece en muchos procesos) o <em>poco frecuente</em> (atípico).
Si es la primera vez que usa la app, el corpus estará vacío y todos los patrones aparecerán como
"Sin histórico".</p>
</div>

<div class="ui-item">
<strong>Activar lectura asistida por IA</strong>
<p>Cuando está marcado, se realizan hasta 2 llamadas al LLM configurado (Azure/Groq) para generar:
(1) un resumen ejecutivo del documento con el nivel de atención general y preguntas sugeridas,
y (2) explicaciones individuales por hallazgo al hacer click en "Generar explicación asistida por IA".
Si está desmarcado, el análisis funciona completamente por reglas sin costo de API.</p>
</div>

<div class="ui-item">
<strong>Botón "Iniciar revisión asistida"</strong>
<p>Lanza el análisis. Debe presionarlo cada vez que suba un nuevo PDF o quiera re-analizar el mismo documento.</p>
</div>
""", unsafe_allow_html=True)

    st.markdown("### 2. Pipeline de análisis")
    st.markdown("""
Los 5 pasos que muestra la barra de progreso:

| Paso | Nombre | Qué hace |
|------|--------|----------|
| 1 | **Extracción documental** | Lee el texto del PDF página por página. Si una página es escaneada y Tesseract está instalado, aplica OCR. |
| 2 | **Identificación de cláusulas** | Aplica reglas textuales (patrones YAML) para detectar cláusulas potencialmente restrictivas. |
| 3 | **Comparación histórica** | Consulta la BD para saber en cuántos procesos anteriores apareció cada patrón detectado. |
| 4 | **Consolidación analítica** | Combina los hallazgos con el contexto histórico, las dimensiones competitivas y los criterios normativos. |
| 5 | **Lectura asistida por IA** | (Solo si está activada) El LLM genera el resumen ejecutivo. |
""")

    st.markdown("### 3. Nivel de atención")
    st.markdown("""
Aparece como un badge de color en varios lugares de la pantalla:
""")
    col_b1, col_b2, col_b3 = st.columns(3)
    with col_b1:
        st.markdown('<div style="text-align:center"><span class="high-badge">Alto</span><p style="font-size:13px;margin-top:8px;">El documento presenta combinaciones o patrones poco frecuentes que sugieren revisión prioritaria por un experto.</p></div>', unsafe_allow_html=True)
    with col_b2:
        st.markdown('<div style="text-align:center"><span class="med-badge">Medio</span><p style="font-size:13px;margin-top:8px;">Hay señales que merecen revisión, pero sin la acumulación o rareza que caracteriza el nivel Alto.</p></div>', unsafe_allow_html=True)
    with col_b3:
        st.markdown('<div style="text-align:center"><span class="low-badge">Bajo</span><p style="font-size:13px;margin-top:8px;">Las señales encontradas parecen habituales o cuentan con mitigantes claros. Revisión de rutina.</p></div>', unsafe_allow_html=True)

    st.markdown("### 4. Resumen ejecutivo")
    st.markdown("""
<div class="ui-item">
<strong>Señales sugeridas para revisión</strong>
<p>Total de cláusulas o requisitos identificados que cumplen con los criterios de los patrones de detección.
No todos son igualmente relevantes — los filtros y la priorización ayudan a enfocarse en los más importantes.</p>
</div>

<div class="ui-item">
<strong>Nivel general de atención</strong>
<p>Calculado combinando: rareza histórica de los patrones, nivel de atención de cada señal individual,
concentración de señales por tema y presencia de combinaciones conocidas de requisitos potencialmente limitantes.</p>
</div>

<div class="ui-item">
<strong>Requisitos poco frecuentes</strong>
<p>Patrones que aparecen en menos del 20% de los procesos históricos comparables. Son los que más merecen
atención porque se desvían de la práctica habitual.</p>
</div>

<div class="ui-item">
<strong>Balance analítico</strong>
<p>Divide los hallazgos en tres grupos: (1) factores que <em>podrían</em> requerir revisión,
(2) aspectos que <em>favorecen</em> apertura competitiva (mitigantes), y (3) requisitos neutros o habituales.
Los mitigantes reducen la urgencia de revisión de otros hallazgos relacionados.</p>
</div>
""", unsafe_allow_html=True)

    st.markdown("### 5. Lectura preliminar asistida por IA")
    st.markdown("""
Solo aparece si activó el checkbox de IA y hay conexión al LLM. Muestra:
- **Resumen del documento**: síntesis de qué contrata y qué señales generales presenta
- **Nivel general de atención**: evaluación del LLM (puede diferir ligeramente del nivel por reglas)
- **Principales temas para revisión**: categorías donde se concentran las señales
- **Posibles efectos sobre concurrencia**: cómo los requisitos detectados podrían afectar el número de oferentes
- **Contexto comparativo**: si los requisitos son usuales o atípicos según el historial
- **Preguntas sugeridas para el revisor**: preguntas concretas que un experto debería responder

> Esta sección consume 1 llamada al LLM por análisis. Con Groq gratuito, hay límites de velocidad.
""")

    st.markdown("### 6. Panel de notificación")
    st.markdown("""
<div class="ui-item">
<strong>Banner rojo "Nivel de atención Alto detectado"</strong>
<p>Aparece automáticamente cuando hay 2 o más señales de atención Alta o cuando el AI brief califica
el nivel como Alto. Es un indicador visual para que el revisor actúe rápidamente.</p>
</div>

<div class="ui-item">
<strong>Expander "Notificar a revisores"</strong>
<p>Se abre automáticamente cuando el nivel es Alto. Muestra los destinatarios activos configurados
en el sidebar y tiene el botón <strong>"Enviar alerta"</strong>.
Al hacer click: guarda el análisis en la BD y envía un email HTML con el resumen a todos los destinatarios.</p>
</div>
""", unsafe_allow_html=True)

    st.markdown("### 7. Filtros de lectura")
    st.markdown("""
Permiten concentrar la vista en un subconjunto de señales:

| Filtro | Descripción |
|--------|-------------|
| **Tema** | Categoría del requisito (ej: Autorizaciones comerciales, Referencias a marca, Certificaciones específicas...) |
| **Atención sugerida** | Alto / Medio / Bajo según el puntaje combinado de rareza y concentración |
| **Clasificación histórica** | Poco frecuente / Intermedio / Habitual / Sin histórico según frecuencia en corpus |

Los filtros afectan el resumen ejecutivo, la priorización y los grupos temáticos — pero el corpus
histórico se actualiza con el documento completo independientemente de los filtros.
""")

    st.markdown("### 8. Aspectos prioritarios sugeridos para revisión")
    st.markdown("""
Los 3 hallazgos con mayor puntaje combinado (rareza + atención + combinación de requisitos).
Para cada uno se muestra:
- Nombre del patrón y página del documento
- Frecuencia en corpus histórico
- Posible efecto sobre concurrencia
- Validación sugerida
- Factores mitigantes (si los hay)
- Posible justificación legítima
- Fragmento textual exacto del documento

El botón **"Generar explicación asistida por IA"** hace una llamada al LLM para explicar ese
hallazgo específico en lenguaje claro (cuesta 1 llamada por hallazgo, on-demand).
""")

    st.markdown("### 9. Señales agrupadas por tema")
    st.markdown("""
Todos los hallazgos organizados por categoría, en acordeones (expanders). Los temas con nivel Alto
aparecen expandidos por defecto. Dentro de cada tema, cada señal muestra:

- Página, categoría y dimensión competitiva afectada
- Por qué se sugiere revisar (criterio normativo orientativo)
- Posible justificación legítima
- Fragmento textual exacto del documento
- Factores mitigantes e información faltante
- Criterios normativos de la LOSNCP relacionados (orientativos, no dictamen)
""")

    st.markdown("### 10. Detalle tabular y exportación")
    st.markdown("""
En el expander "Detalle tabular y exportación":

- **Tabla completa**: todos los hallazgos con todas las columnas, descargable
- **Descargar reporte de revisión asistida** (CSV): todos los datos para análisis posterior en Excel
- **Descargar reporte ejecutivo** (Markdown): documento formateado con resumen, prioridades y señales
""")

    st.markdown("### 11. Texto extraído por página")
    st.markdown("""
En el expander "Texto extraído por página" puede verificar el texto que la app leyó del PDF
para cada página. Útil para detectar si hay páginas escaneadas sin texto o si la extracción
tuvo problemas. Si una página aparece vacía y usted sabe que tiene contenido, es probable que
sea una imagen escaneada y requiera Tesseract OCR instalado.
""")

    # ── Dimensiones competitivas ──────────────────────────────────────────────
    st.markdown("---")
    st.markdown("## Dimensiones de análisis competitivo")
    st.markdown("Cada señal se clasifica en una de estas dimensiones:")

    dims = [
        ("Barreras de entrada", "Requisitos que elevan el costo o dificultad de participar, más allá de lo necesario para el objeto contractual."),
        ("Dependencia de proveedor o fabricante", "Exigencia de marcas, fabricantes o distribuidores específicos sin posibilidad de equivalentes."),
        ("Acceso reducido al mercado", "Condiciones que limitan estructuralmente quién puede participar."),
        ("Restricción de calificación", "Requisitos de experiencia, capacidad técnica o financiera desproporcionados."),
        ("Carga administrativa", "Documentación o procedimientos excesivos que desincentivan la participación."),
        ("Restricción geográfica o de presencia local", "Exigencia de oficinas, bodegas o presencia física en lugares específicos."),
        ("Discrecionalidad de evaluación", "Criterios de evaluación vagos o que dan margen amplio al evaluador."),
        ("Dependencia por interoperabilidad", "Requisitos de compatibilidad con sistemas existentes que favorecen al proveedor actual."),
        ("Restricción de plazos", "Plazos de entrega o ejecución que solo puede cumplir un proveedor con stocks previos."),
        ("Restricción financiera", "Garantías, pólizas o respaldos financieros desproporcionados al monto o riesgo."),
        ("Restricción técnica", "Especificaciones técnicas tan cerradas que solo un producto o familia los cumple."),
        ("Baja neutralidad competitiva", "Combinación de requisitos que en conjunto reducen significativamente la concurrencia."),
    ]
    for dim, desc in dims:
        st.markdown(f"""
<div class="ui-item">
<strong>{dim}</strong>
<p>{desc}</p>
</div>
""", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("""
<div style="background:#f1f5f9; border-radius:6px; padding:14px 18px; font-size:13px; color:#475569; margin-top:16px;">
<strong>Nota metodológica:</strong> Las señales identificadas por este sistema son insumos preliminares
para revisión humana de neutralidad competitiva. La referencia a normas (LOSNCP/RLOSNCP) es orientativa
y no constituye interpretación legal oficial. El sistema no emite dictámenes técnicos ni legales,
no atribuye intencionalidad y no infiere beneficiarios. Todo resultado requiere validación por
un experto en contratación pública.
</div>
""", unsafe_allow_html=True)
