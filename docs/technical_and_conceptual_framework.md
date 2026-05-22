# Documento técnico y conceptual

## Herramienta Exploratoria de Análisis Documental y Neutralidad Competitiva en Procesos de Contratación Pública

Versión preliminar de trabajo

# 1. Resumen Ejecutivo

El presente documento describe una propuesta preliminar para explorar el uso de capacidades avanzadas de análisis documental e inteligencia artificial generativa aplicadas a procesos de contratación pública en Ecuador. La iniciativa se concibe como una línea de trabajo exploratoria y prudente orientada a fortalecer capacidades institucionales de revisión documental, particularmente en contextos caracterizados por alto volumen de información, complejidad técnica y necesidad de priorización analítica.

En los últimos años, distintas administraciones públicas, organismos multilaterales y entidades de control han comenzado a evaluar el potencial de nuevas herramientas de analítica documental y procesamiento de lenguaje natural para apoyar tareas de revisión, trazabilidad y análisis preventivo. Sin embargo, la experiencia internacional también demuestra que este tipo de capacidades requieren especial cautela debido a riesgos asociados a falsos positivos, interpretaciones erróneas, opacidad algorítmica y potenciales impactos reputacionales.

En ese contexto, la presente propuesta no plantea el desarrollo de un sistema de fiscalización automática ni una herramienta destinada a determinar corrupción, fraude o direccionamiento contractual. Por el contrario, se propone un enfoque incremental y controlado, orientado a construir una herramienta de apoyo analítico y revisión humana capaz de asistir procesos de lectura, comprensión y contextualización de documentos de contratación pública.

La hipótesis central del proyecto es que una combinación razonable de extracción documental, comparación histórica, reglas trazables, procesamiento de lenguaje natural y capacidades de IA generativa podría contribuir a reducir carga cognitiva, facilitar comprensión documental y apoyar procesos institucionales de revisión preliminar.

La propuesta pone especial énfasis en principios de prudencia analítica, explicabilidad, trazabilidad y supervisión humana. Bajo este enfoque, toda observación generada por la herramienta debe entenderse como una señal preliminar o un aspecto sugerido para revisión adicional, y nunca como una conclusión automática o un dictamen técnico o jurídico.

Asimismo, el valor analítico esperado de la herramienta no radicaría exclusivamente en el uso de modelos generativos, sino principalmente en la posibilidad de combinar:

- análisis documental estructurado;

- comparación respecto de procesos históricos;

- contextualización de requisitos;

- agrupación temática;

- y capacidades de priorización.

En términos institucionales, la iniciativa podría servir como un espacio controlado para explorar aplicaciones futuras de analítica documental e IA en contratación pública bajo un enfoque compatible con principios de transparencia, revisión humana y fortalecimiento institucional.

# 2. Contexto y Justificación

Los procesos de contratación pública suelen involucrar un volumen considerable de documentación técnica, administrativa y jurídica. Los pliegos y especificaciones técnicas frecuentemente contienen múltiples referencias cruzadas, anexos, requisitos específicos, condiciones técnicas, matrices de cumplimiento y criterios especializados que deben ser revisados en plazos limitados y bajo elevados estándares de consistencia.

En la práctica, esto implica que los equipos técnicos y jurídicos deban realizar procesos de revisión altamente intensivos en tiempo y esfuerzo, especialmente cuando se requiere analizar simultáneamente:

- requisitos habilitantes;

- especificaciones técnicas;

- condiciones de soporte y postventa;

- referencias a fabricantes;

- criterios de equivalencia;

- certificaciones;

- y consistencia entre anexos y documentos complementarios.

Adicionalmente, uno de los desafíos más relevantes en procesos de revisión documental consiste en la dificultad de contextualizar determinados requisitos respecto de procesos históricos comparables. En muchos casos, un requisito aislado puede parecer razonable o habitual, mientras que su combinación con otros criterios podría justificar una revisión más detallada. De igual manera, ciertas cláusulas podrían ser técnicamente legítimas dependiendo de la naturaleza del bien o servicio contratado.

Por esta razón, un enfoque basado exclusivamente en detección de palabras clave o reglas simples resulta insuficiente y potencialmente riesgoso desde una perspectiva institucional. Sistemas excesivamente agresivos o con bajo contexto suelen generar altos niveles de falsos positivos, fatiga analítica y pérdida de confianza por parte de los usuarios especializados.

En paralelo, durante los últimos años se ha observado un avance significativo en tecnologías asociadas a:

- procesamiento de lenguaje natural (NLP);

- extracción documental;

- embeddings y búsqueda semántica;

- modelos generativos;

- y analítica comparativa.

Estas capacidades abren oportunidades interesantes para explorar herramientas de apoyo analítico orientadas no a reemplazar procesos institucionales existentes, sino a fortalecer capacidades de lectura, contextualización y priorización.

No obstante, cualquier aproximación en este ámbito requiere una arquitectura prudente y gobernada. Particularmente en contratación pública, resulta crítico evitar:

- conclusiones determinísticas;

- lenguaje acusatorio;

- opacidad analítica;

- automatización de decisiones;

- y usos que puedan interpretarse como sustitución de criterios técnicos o jurídicos.

La propuesta presentada en este documento se construye precisamente sobre esa premisa: explorar capacidades de apoyo documental e IA bajo un marco de control, revisión humana y trazabilidad.

# 3. Objetivo General

Explorar la viabilidad técnica y operativa de una herramienta de apoyo analítico para revisión preliminar de neutralidad competitiva en documentos de contratación pública mediante técnicas de:

- extracción documental;

- procesamiento de lenguaje natural;

- análisis comparativo;

- priorización contextual;

- y capacidades de inteligencia artificial generativa.

# 4. Objetivos Específicos

## 4.1 Lectura y comprensión documental

Facilitar la comprensión de pliegos y especificaciones técnicas mediante:

- extracción automatizada de texto;

- organización temática;

- resúmenes ejecutivos;

- y navegación contextual.

## 4.2 Identificación de señales preliminares

Identificar aspectos documentales que podrían requerir revisión humana adicional en materia de:

- neutralidad competitiva;

- proporcionalidad;

- consistencia documental;

- y completitud.

## 4.3 Contextualización histórica

Comparar cláusulas y requisitos respecto de procesos históricos comparables para:

- contextualizar frecuencia;

- detectar criterios poco frecuentes;

- identificar variaciones relevantes;

- y reducir interpretaciones aisladas.

## 4.4 Priorización analítica

Apoyar procesos de priorización mediante:

- agrupación temática;

- consolidación de señales;

- y generación de criterios de revisión sugeridos.

## 4.5 Fortalecimiento institucional

Explorar aplicaciones futuras de capacidades analíticas e IA en procesos de revisión documental y fortalecimiento institucional.

# 5. Alcance de la Prueba de Concepto

La PoC tendría un alcance exploratorio, acotado y no productivo.

## 5.1 Alcance documental

La herramienta analizaría inicialmente:

- pliegos;

- especificaciones técnicas;

- anexos documentales relevantes;

- y corpus históricos comparables.

## 5.2 Alcance funcional

La PoC permitiría:

- cargar documentos PDF;

- extraer texto automáticamente;

- estructurar información documental;

- aplicar reglas y patrones exploratorios;

- comparar documentos respecto de corpus históricos;

- consolidar señales preliminares;

- generar resúmenes ejecutivos;

- y apoyar procesos de revisión humana.

## 5.3 Alcance analítico

El análisis se enfocaría en:

- neutralidad competitiva;

- proporcionalidad de requisitos;

- consistencia documental;

- completitud documental;

- y contextualización comparativa.

## 5.4 Exclusiones explícitas

La PoC no contempla:

- scoring de corrupción;

- determinaciones automáticas de ilegalidad;

- conclusiones sobre direccionamiento contractual;

- automatización de decisiones;

- reemplazo de revisión humana;

- ni sistemas de fiscalización automática.

# 6. Enfoque Conceptual

La herramienta se concibe como un:

## “Asistente exploratorio de revisión documental y neutralidad competitiva”

No como:

- un sistema sancionatorio;

- un detector automático de corrupción;

- ni una herramienta de determinación jurídica.

El enfoque propuesto se basa en cinco principios:

## 6.1 Prudencia analítica

Los resultados deben formularse como:

- señales preliminares;

- aspectos sugeridos para revisión;

- criterios potencialmente limitantes;

- o elementos que podrían requerir validación adicional.

## 6.2 Explicabilidad

Toda señal debe poder explicarse mediante:

- evidencia textual;

- contexto documental;

- reglas aplicadas;

- y comparación histórica.

## 6.3 Revisión humana

La herramienta debe asistir, no reemplazar, procesos institucionales de revisión.

## 6.4 Trazabilidad

Cada resultado debe preservar:

- documento origen;

- página;

- fragmento;

- regla aplicada;

- versión analítica;

- timestamp;

- y contexto comparativo.

## 6.5 Balance analítico

La herramienta debe reconocer:

- requisitos habituales;

- factores mitigantes;

- criterios que favorecen concurrencia;

- y contexto normativo.

# 7. Arquitectura Conceptual

## Flujo general de procesamiento

PDF → extracción documental → limpieza y estructuración → identificación de patrones → análisis contextual → comparación histórica → consolidación analítica → contextualización IA → revisión humana

## Componentes principales

### A. Motor documental

Responsable de:

- carga PDF;

- OCR futuro;

- parsing;

- extracción por páginas;

- estructuración documental.

### B. Motor analítico

Responsable de:

- reglas;

- clasificación;

- agrupación temática;

- consolidación de señales;

- priorización.

### C. Motor comparativo

Responsable de:

- análisis de frecuencia;

- comparación histórica;

- similitud documental;

- contextualización.

### D. Capa IA generativa

Responsable de:

- resúmenes ejecutivos;

- explicación contextual;

- apoyo a comprensión;

- formulación de preguntas sugeridas.

### E. Interfaz UX/UI

Responsable de:

- lectura narrativa;

- priorización;

- navegación integrada;

- experiencia institucional.

# 8. Enfoque Analítico de Neutralidad Competitiva

Uno de los aspectos más sensibles de cualquier iniciativa vinculada a analítica aplicada a contratación pública consiste en la forma en que se conceptualiza el problema analítico a abordar.

En múltiples jurisdicciones se han observado aproximaciones excesivamente simplificadas que intentan utilizar inteligencia artificial para “detectar corrupción”, “identificar direccionamiento” o “calificar riesgos” de manera automática a partir de documentos contractuales. Este tipo de enfoques suele presentar limitaciones importantes desde el punto de vista técnico, metodológico, jurídico e institucional.

En particular, existen riesgos asociados a:

- generación de falsos positivos;

- ausencia de contexto técnico;

- interpretaciones erróneas de requisitos legítimos;

- sesgos derivados de datasets incompletos;

- opacidad algorítmica;

- y potenciales impactos reputacionales.

Por esta razón, la presente propuesta evita deliberadamente cualquier aproximación basada en determinaciones automáticas o lenguaje acusatorio. La iniciativa no busca “detectar direccionamiento” ni inferir corrupción a partir de un documento.

El enfoque conceptual propuesto es significativamente más prudente y se centra en la identificación y contextualización de señales preliminares que podrían justificar revisión humana adicional desde la perspectiva de neutralidad competitiva, proporcionalidad y consistencia documental.

Bajo este enfoque, la herramienta no evalúa únicamente palabras o frases aisladas. El análisis propuesto busca incorporar contexto documental, frecuencia histórica y relaciones entre requisitos para evitar interpretaciones simplistas.

Por ejemplo, la sola presencia de referencias a fabricantes, garantías o soporte especializado no constituye necesariamente una señal relevante. En numerosos casos, estos requisitos podrían responder legítimamente a:

- necesidades operativas;

- complejidad tecnológica;

- soporte postventa;

- interoperabilidad;

- continuidad de servicio;

- garantía de calidad;

- o estándares regulatorios sectoriales.

El mismo criterio aplica a familias sectoriales más específicas. En adquisiciones farmacéuticas, por ejemplo, una combinación de principio activo, concentración exacta, volumen, vía de administración, forma farmacéutica o presentación comercial puede constituir una señal documental para revisión humana cuando aparenta alinearse con una presentación comercial muy granular. Esta observación no implica una conclusión sobre validez del requisito; únicamente sugiere revisar proporcionalidad, equivalencias terapéuticas o técnicas, registro sanitario aplicable y justificación clínica, regulatoria u operativa.

En consecuencia, la lógica analítica de la herramienta debe orientarse hacia una evaluación contextual y balanceada, considerando simultáneamente:

- requisitos potencialmente limitantes;

- criterios habituales o regulatorios;

- factores mitigantes;

- y elementos que favorecen concurrencia.

En términos metodológicos, el sistema se estructuraría alrededor de tres grandes capas analíticas.

La primera corresponde a una capa de extracción y estructuración documental, encargada de transformar documentos PDF heterogéneos en información procesable. Esta capa incluye parsing, organización por páginas, normalización y consolidación textual.

La segunda corresponde a una capa de análisis contextual y comparación histórica. Aquí el objetivo principal consiste en contextualizar requisitos respecto de procesos comparables y evitar interpretaciones aisladas. Conceptualmente, esta capa constituye uno de los principales diferenciales de la propuesta, dado que permite desplazar el foco desde la mera detección de keywords hacia análisis comparativos y contextualizados.

La tercera corresponde a una capa de asistencia analítica e inteligencia artificial generativa. Esta capa tendría un rol estrictamente subordinado al análisis documental y reglas trazables, utilizándose principalmente para:

- resumir documentos;

- explicar hallazgos;

- consolidar observaciones;

- formular preguntas sugeridas;

- y facilitar comprensión.

Bajo ninguna circunstancia la IA generativa debería actuar como mecanismo autónomo de determinación, clasificación de corrupción o generación automática de conclusiones jurídicas.

Desde una perspectiva institucional, este enfoque resulta particularmente relevante porque permite mantener:

- supervisión humana;

- trazabilidad analítica;

- explicabilidad;

- y gobernanza del proceso.

Asimismo, reduce significativamente riesgos asociados a interpretaciones erróneas o usos inapropiados de outputs generados por modelos generativos.

En términos operativos, la herramienta buscaría responder una pregunta relativamente acotada pero de alto valor práctico:

“¿Qué aspectos de este documento podrían justificar una revisión más detallada y por qué?”

La intención no es reemplazar la experiencia de especialistas técnicos, jurídicos o de contratación pública, sino contribuir a priorizar lectura y contextualizar información en escenarios de alta carga documental.

Finalmente, es importante destacar que la utilidad potencial de una herramienta de este tipo depende mucho más de:

- calidad del corpus histórico;

- trazabilidad documental;

- calidad de reglas;

- gobernanza analítica;

- y experiencia institucional,

que de la complejidad del modelo generativo utilizado.

En este sentido, la propuesta se alinea con un enfoque de adopción prudente y gradual de capacidades analíticas e IA en el sector público.

# 9. Enfoque Normativo

La herramienta podría apoyarse orientativamente en principios contenidos en la Ley Orgánica del Sistema Nacional de Contratación Pública en Ecuador, su Reglamento General, y normativa complementario.

## Principios relevantes

- concurrencia;

- igualdad;

- trato justo;

- no discriminación;

- transparencia;

- mejor valor por dinero;

- proporcionalidad;

- claridad de especificaciones;

- justificación técnica;

- consistencia documental.

## Importante

La referencia normativa tendría carácter exclusivamente orientativo.

La herramienta:

- no constituye interpretación legal oficial;

- no reemplaza análisis jurídico;

- ni genera conclusiones regulatorias.

# 10. Estrategia de Datos y Corpus Histórico

Uno de los principales componentes analíticos de la propuesta consiste en la construcción progresiva de un corpus documental histórico estructurado.

Desde una perspectiva metodológica, el valor potencial de la herramienta no depende únicamente del uso de modelos generativos o capacidades de NLP. En la práctica, uno de los principales diferenciales analíticos proviene de la posibilidad de contextualizar documentos respecto de procesos históricos comparables.

En otras palabras, la herramienta no busca analizar un pliego de manera aislada, sino interpretarlo dentro de un contexto documental más amplio.

Esto permite:

- contextualizar requisitos;

- identificar criterios poco frecuentes;

- reducir falsos positivos;

- comparar patrones entre procesos similares;

- y fortalecer procesos de priorización.

## 10.1 Rol estratégico del corpus histórico

El corpus histórico constituye la principal fuente de contexto comparativo del sistema.

Conceptualmente, el corpus funciona como una biblioteca documental estructurada sobre la cual la herramienta puede:

- calcular frecuencia de requisitos;

- detectar diferencias relevantes;

- identificar combinaciones atípicas;

- y contextualizar criterios respecto de procesos comparables.

Por ejemplo, una cláusula determinada podría:

- resultar habitual en determinados tipos de contratación;

- ser estándar en ciertos sectores;

- o aparecer con frecuencia extremadamente baja respecto de procesos similares.

Sin un corpus histórico adecuado, cualquier análisis documental tendería a generar interpretaciones aisladas y mayor riesgo de falsos positivos.

En consecuencia, la calidad, cobertura y trazabilidad del corpus representan uno de los principales factores críticos de éxito de la iniciativa.

## 10.2 Tipos de documentos considerados

La arquitectura propuesta contempla inicialmente la incorporación de:

- pliegos;

- especificaciones técnicas;

- anexos relevantes;

- términos de referencia;

- matrices técnicas;

- y metadata de procesos.

En etapas posteriores podrían evaluarse otros componentes documentales como:

- respuestas a preguntas y aclaraciones;

- resoluciones;

- informes técnicos;

- contratos;

- o documentación complementaria.

## 10.3 Estructura documental propuesta

Para garantizar trazabilidad y procesamiento consistente, la documentación debería organizarse bajo una estructura estándar.

### **Estructura sugerida**

/data

/raw

/pdfs

PROCESO_001_PLIEGO.pdf

PROCESO_001_ESPECIFICACIONES.pdf

PROCESO_002_PLIEGO.pdf

**Código**

/metadata

procesos.csv

## 10.4 Metadata mínima requerida

La herramienta requiere una base mínima de metadata para asociar correctamente documentos y permitir análisis comparativos.

La estructura sugerida para el archivo de metadata (CSV o equivalente) incluiría al menos:

| **Campo**             | **Descripción**                           |
|-----------------------|-------------------------------------------|
| process_id            | Identificador único del proceso           |
| entidad               | Entidad contratante                       |
| año                   | Año del proceso                           |
| tipo_proceso          | Tipo de contratación                      |
| objeto                | Objeto resumido                           |
| categoria             | Categoría o rubro                         |
| pliego_file           | Nombre exacto del PDF del pliego          |
| especificaciones_file | Nombre exacto del PDF de especificaciones |

La metadata constituye un componente fundamental para:

- trazabilidad;

- matching documental;

- agrupación;

- comparación histórica;

- y clasificación.

## 10.5 Matching documental y trazabilidad

Uno de los riesgos más relevantes en arquitecturas de analítica documental consiste en errores de asociación entre metadata y documentos.

Por esta razón, la propuesta prioriza un enfoque de matching determinístico y auditable.

El sistema debería:

- evitar coincidencias ambiguas;

- validar nombres exactos;

- detectar documentos faltantes;

- identificar duplicados;

- y registrar trazabilidad completa.

Cada documento debería registrar:

- document_id;

- process_id;

- nombre original;

- nombre normalizado;

- path;

- hash documental opcional;

- timestamp;

- y estado de validación.

Esto resulta particularmente importante en escenarios donde el corpus evoluciona progresivamente.

## 10.6 Integración de nuevos documentos

La arquitectura propuesta busca facilitar la incorporación incremental de nueva documentación.

El flujo conceptual sería:

1.  Incorporación de PDFs a carpeta estructurada.

2.  Registro de metadata correspondiente.

3.  Validación automática de integridad documental.

4.  Extracción y procesamiento.

5.  Indexación y consolidación.

6.  Disponibilización para análisis comparativo.

La herramienta podría incorporar módulos de validación capaces de detectar:

- PDFs faltantes;

- nombres inconsistentes;

- metadata incompleta;

- duplicados;

- referencias inválidas;

- y errores de estructura.

## 10.7 Estrategia de crecimiento del corpus

La utilidad analítica del sistema tendería a mejorar progresivamente a medida que aumente:

- volumen documental;

- diversidad de procesos;

- cobertura histórica;

- calidad de metadata;

- y consistencia documental.

No obstante, el crecimiento del corpus también introduce desafíos asociados a:

- almacenamiento;

- gobernanza;

- versionamiento;

- calidad de datos;

- y trazabilidad.

En consecuencia, se recomienda que cualquier expansión futura del corpus se realice bajo criterios de:

- normalización;

- validación;

- control de calidad;

- y gobierno de datos.

## 10.8 Evolución futura del componente analítico

En etapas futuras, un corpus documental suficientemente robusto podría habilitar capacidades adicionales como:

- embeddings y búsqueda semántica;

- clustering documental;

- comparación semántica avanzada;

- detección de similitudes;

- grafos documentales;

- y analítica comparativa más sofisticada.

Sin embargo, la propuesta actual prioriza inicialmente:

- simplicidad;

- trazabilidad;

- explicabilidad;

- y robustez operativa.

## 10.9 Requerimientos para disponibilización documental y metadata

La efectividad y sostenibilidad de la herramienta dependen significativamente de la calidad, estructura y accesibilidad de la documentación utilizada como fuente de análisis.

En consecuencia, uno de los componentes críticos de la iniciativa consiste en definir mecanismos estandarizados para disponibilizar documentación y metadata de procesos de contratación de manera consistente, trazable y procesable por sistemas analíticos.

Desde una perspectiva técnica y operativa, el objetivo no es únicamente acceder a documentos PDF, sino contar con una arquitectura documental mínimamente estructurada que permita:

- asociar correctamente documentos y procesos;

- mantener trazabilidad;

- facilitar procesamiento automatizado;

- reducir errores de matching;

- habilitar análisis comparativos;

- y soportar crecimiento progresivo del corpus histórico.

### **A. Principios recomendados de disponibilización**

Se recomienda que la documentación sea disponibilizada bajo principios de:

- estructura consistente;

- nomenclatura estandarizada;

- metadata asociada;

- identificadores únicos;

- y persistencia estable de documentos.

Idealmente, los documentos deberían poder consumirse mediante:

- carpetas estructuradas;

- repositorios documentales;

- endpoints;

- APIs;

- o mecanismos equivalentes de acceso controlado.

### **B. Estructura documental sugerida**

La propuesta recomienda organizar los documentos bajo una estructura consistente y fácilmente procesable.

Ejemplo conceptual:

/contratacion_publica

/2025

/SIE-001

PLIEGO.pdf

ESPECIFICACIONES.pdf

ANEXOS.pdf

/SIE-002

PLIEGO.pdf

ESPECIFICACIONES.pdf

Alternativamente, podrían utilizarse repositorios centralizados con URLs persistentes.

### **C. Metadata mínima requerida**

Además de los documentos PDF, resulta fundamental disponibilizar metadata estructurada asociada a cada proceso.

La metadata mínima sugerida incluye:

| **Campo**             | **Descripción**                  |
|-----------------------|----------------------------------|
| process_id            | Identificador único del proceso  |
| codigo_proceso        | Código oficial del procedimiento |
| entidad               | Entidad contratante              |
| objeto                | Objeto resumido del proceso      |
| tipo_proceso          | Tipo de contratación             |
| fecha_publicacion     | Fecha de publicación             |
| estado                | Estado del proceso               |
| categoria             | Rubro o categoría                |
| monto_referencial     | Monto estimado                   |
| url_proceso           | URL oficial                      |
| pliego_file           | Nombre o URL del pliego          |
| especificaciones_file | Nombre o URL de especificaciones |

Idealmente, esta información debería estar disponible en formatos estructurados como:

- CSV;

- JSON;

- API REST;

- o bases consultables.

### **D. Recomendaciones de integración técnica**

Para una PoC inicial, la integración podría realizarse mediante mecanismos relativamente simples como:

- carpetas compartidas;

- repositorios documentales;

- exportaciones CSV periódicas;

- o dumps controlados.

Sin embargo, para escenarios de evolución futura, se recomienda evaluar arquitecturas más robustas basadas en:

- APIs documentales;

- servicios de consulta;

- feeds automatizados;

- almacenamiento cloud;

- o pipelines ETL.

Esto permitiría:

- automatizar actualización del corpus;

- reducir trabajo manual;

- mejorar consistencia;

- y fortalecer sostenibilidad operativa.

### **E. Calidad y gobierno de datos**

Uno de los principales riesgos en herramientas de analítica documental consiste en inconsistencias entre documentos y metadata.

Por esta razón, resulta recomendable establecer criterios mínimos de calidad y gobierno de datos asociados a:

- nomenclatura documental;

- completitud de metadata;

- persistencia de identificadores;

- versionamiento;

- trazabilidad;

- y validación de integridad.

La herramienta podría incorporar validaciones automáticas para detectar:

- documentos faltantes;

- referencias inválidas;

- duplicados;

- metadata incompleta;

- y errores de estructura.

### **F. Evolución futura hacia interoperabilidad**

En etapas posteriores, una arquitectura documental más madura podría habilitar capacidades adicionales de interoperabilidad y automatización.

Entre ellas:

- actualización incremental automática;

- indexación continua;

- búsqueda semántica;

- sincronización documental;

- y pipelines analíticos más avanzados.

No obstante, para la etapa exploratoria actual, se recomienda priorizar inicialmente:

- simplicidad;

- trazabilidad;

- consistencia documental;

- y facilidad de integración.

## 

# 11. Enfoque UX/UI

La experiencia de usuario se plantea bajo una lógica de:

## “briefing analítico institucional”

No de dashboard técnico.

## Objetivos UX

- reducir carga cognitiva;

- facilitar comprensión;

- apoyar priorización;

- mejorar navegabilidad;

- fortalecer interpretabilidad.

## Componentes UX previstos

- lectura preliminar asistida por IA;

- resumen ejecutivo;

- top prioridades sugeridas;

- agrupación temática;

- comparación histórica integrada;

- evidencia textual contextualizada;

- preguntas sugeridas.

## Principios visuales

- diseño institucional;

- claridad;

- navegación integrada;

- trazabilidad visible;

- explicabilidad.

# 12. Enfoque de IA Generativa

La IA generativa tendría un rol subordinado al análisis documental y reglas trazables.

## Funciones previstas

- resumir documentos;

- contextualizar señales;

- generar preguntas sugeridas;

- apoyar lectura analítica.

## Restricciones explícitas

La IA no debería:

- generar conclusiones jurídicas;

- inferir corrupción;

- detectar direccionamiento automáticamente;

- emitir dictámenes.

## Principio de control

Toda salida IA debe estar:

- anclada a evidencia documental;

- subordinada a reglas;

- contextualizada;

- y sujeta a revisión humana.

# 13. Riesgos y Mitigaciones

## 13.1 Riesgo de falsos positivos

Mitigación:

- contextualización histórica;

- factores mitigantes;

- reducción de alert fatigue;

- revisión humana.

## 13.2 Riesgo reputacional

Mitigación:

- lenguaje prudente;

- disclaimers;

- enfoque exploratorio;

- gobernanza clara.

## 13.3 Riesgo de alucinaciones IA

Mitigación:

- outputs estructurados;

- prompts controlados;

- IA subordinada a evidencia.

## 13.4 Riesgo documental

Mitigación:

- matching determinístico;

- validación corpus;

- trazabilidad completa.

## 13.5 Riesgo operativo

Mitigación:

- alcance acotado;

- despliegue incremental;

- validación institucional.

# 14. Gobernanza y Control

La herramienta debería operar bajo principios de:

- revisión humana;

- auditabilidad;

- trazabilidad;

- prudencia;

- explicabilidad;

- mejora continua.

Toda señal debería registrar:

- documento origen;

- regla aplicada;

- evidencia textual;

- contexto histórico;

- criterios utilizados.

La taxonomía de señales debería mantenerse como un instrumento versionado y gobernado. La incorporación de patrones sectoriales, como presentaciones farmacéuticas altamente específicas, debe exigir evidencia observable, mitigantes, controles de falsos positivos, preguntas de revisión humana y lenguaje prudente. Su finalidad es orientar revisión preventiva, no producir determinaciones automáticas.

# 15. Roadmap Exploratorio

## Etapa 1 – PoC inicial

- extracción documental;

- reglas básicas;

- corpus histórico;

- UX institucional;

- IA contextual.

## Etapa 2 – Consolidación analítica

- reducción falsos positivos;

- análisis contextual;

- priorización avanzada;

- trazabilidad robusta.

## Etapa 3 – Capacidades avanzadas

Posibles líneas futuras:

- embeddings;

- grafos;

- análisis semántico;

- consistencia documental;

- analítica avanzada.

# 17. Arquitectura de IA Generativa, Servicios y Consideraciones de Costos

## 16.1 Rol de la IA dentro de la arquitectura

La arquitectura propuesta contempla el uso de inteligencia artificial generativa exclusivamente como una capa de asistencia analítica y contextualización. La IA no constituye el núcleo principal del sistema ni reemplaza los mecanismos trazables de extracción documental, comparación histórica y reglas analíticas.

Conceptualmente, la herramienta se apoya sobre una arquitectura híbrida compuesta por:

- extracción documental;

- reglas trazables;

- análisis contextual;

- comparación histórica;

- y capacidades generativas acotadas.

En este esquema, la IA se utiliza principalmente para:

- resumir documentos;

- consolidar información;

- explicar hallazgos en lenguaje natural;

- contextualizar señales;

- formular preguntas sugeridas;

- y facilitar lectura analítica.

Esto permite mantener:

- trazabilidad;

- explicabilidad;

- gobernanza;

- y control humano.

La arquitectura evita deliberadamente enfoques donde el modelo generativo actúe como único mecanismo de análisis o como motor autónomo de determinación.

## 16.2 Servicios y modelos potenciales

La PoC actual explora el uso de APIs comerciales de modelos fundacionales (LLMs) bajo esquemas de consumo por demanda. La arquitectura propuesta busca mantener flexibilidad tecnológica y evitar dependencia estructural de un único proveedor.

Entre las alternativas técnicamente viables se encuentran:

### **A. OpenAI API**

Posibles modelos:

- GPT-4.1

- GPT-4.1-mini

- GPT-4o

- GPT-4o-mini

Fortalezas:

- muy buen desempeño en resumen y comprensión documental;

- outputs estructurados;

- ecosistema maduro;

- integración sencilla vía API;

- amplia adopción empresarial.

Consideraciones:

- costos variables por consumo;

- dependencia de proveedor externo;

- necesidad de gobernanza de datos.

### **B. Azure OpenAI Service**

Alternativa particularmente relevante para entornos institucionales y gubernamentales.

Fortalezas:

- despliegue bajo infraestructura Azure;

- controles empresariales;

- capacidades avanzadas de seguridad y compliance;

- integración corporativa;

- potencial alineación con arquitecturas cloud institucionales.

Consideraciones:

- complejidad operativa ligeramente mayor;

- dependencia de infraestructura Azure;

- costos cloud asociados.

### **C. Anthropic Claude**

Posibles modelos:

- Claude Sonnet

- Claude Opus

Fortalezas:

- muy buen desempeño en lectura y síntesis documental extensa;

- buena capacidad de razonamiento contextual;

- outputs generalmente prudentes y menos agresivos;

- ventanas de contexto amplias.

Potenciales aplicaciones:

- análisis documental complejo;

- consolidación de hallazgos;

- generación de resúmenes ejecutivos;

- contextualización narrativa.

Consideraciones:

- ecosistema empresarial todavía en expansión;

- integración y tooling menos maduro que OpenAI en algunos entornos;

- costos variables según contexto utilizado.

### **D. Google Gemini**

Posibles modelos:

- Gemini 1.5 Pro

- Gemini 1.5 Flash

Fortalezas:

- ventanas de contexto extensas;

- potencial integración futura con ecosistemas Google Cloud;

- capacidades multimodales;

- costos competitivos en algunos escenarios.

Potenciales aplicaciones:

- procesamiento documental masivo;

- análisis comparativo;

- workflows de búsqueda semántica.

Consideraciones:

- madurez variable según caso de uso;

- evolución rápida de APIs y modelos;

- necesidad de validación institucional adicional.

### **E. Modelos open source**

Posibles alternativas futuras:

- Llama

- Mistral

- Gemma

- Qwen

- DeepSeek

Estas opciones podrían explorarse en escenarios donde:

- existan restricciones regulatorias;

- se requiera despliegue local;

- se busque reducir dependencia de APIs comerciales;

- o se priorice soberanía tecnológica.

No obstante, implican mayores requerimientos asociados a:

- infraestructura;

- tuning;

- MLOps;

- mantenimiento;

- observabilidad;

- y gobernanza técnica.

En términos generales, para una PoC inicial controlada, las APIs comerciales suelen ofrecer una relación favorable entre:

- velocidad de implementación;

- estabilidad;

- calidad de outputs;

- y simplicidad operativa.

## 16.3 Arquitectura operacional propuesta

La arquitectura propuesta para la PoC prioriza simplicidad, trazabilidad y control de costos.

El flujo conceptual sería:

Documento PDF  
→ extracción local de texto  
→ identificación de señales mediante taxonomía editable y reglas trazables  
→ consolidación analítica  
→ envío de contexto reducido al LLM cuando corresponda  
→ generación de resumen/contextualización  
→ revisión humana

Importante:

El diseño propuesto evita enviar documentos completos al modelo generativo.

En su lugar, la arquitectura prioriza:

- fragmentos relevantes;

- secciones asociadas a señales;

- resúmenes estructurados;

- y contexto acotado.

Esto permite:

- reducir costos;

- disminuir riesgos de alucinación;

- mejorar control;

- y optimizar desempeño.

## 16.4 Consideraciones de tokens y costos

El principal componente de costo asociado a IA generativa corresponde al consumo de tokens.

Un token representa aproximadamente fragmentos de texto utilizados por el modelo para:

- leer inputs;

- procesar contexto;

- y generar outputs.

### **Consumo esperado por documento**

En una arquitectura prudente y optimizada, el sistema no enviaría el PDF completo al modelo.

Una corrida típica podría incluir:

- fragmentos relevantes del documento;

- resumen de señales detectadas;

- contexto comparativo;

- instrucciones del sistema.

Estimación preliminar por corrida:

| **Componente**          | **Tokens aproximados** |
|-------------------------|------------------------|
| Prompt sistema          | 500 – 1.000            |
| Fragmentos relevantes   | 4.000 – 8.000          |
| Hallazgos estructurados | 1.000 – 2.000          |
| Respuesta generada      | 1.000 – 2.000          |
| Total estimado          | 6.500 – 13.000         |

Dependiendo del modelo utilizado, esto representa costos relativamente bajos para una PoC controlada.

### **Estimación preliminar de costos**

Utilizando modelos ligeros/intermedios (por ejemplo GPT-4o-mini, GPT-4.1-mini, Claude Sonnet o Gemini Flash), el costo estimado por análisis documental podría ubicarse aproximadamente entre:

- USD 0,01 y USD 0,15 por documento,

dependiendo de:

- longitud del documento;

- cantidad de contexto enviado;

- número de llamadas al modelo;

- y tamaño de outputs.

Para una PoC acotada, los costos de inferencia se consideran relativamente manejables.

No obstante, para despliegues institucionales de escala mayor sería necesario evaluar:

- volumen documental;

- concurrencia;

- frecuencia de uso;

- arquitectura cloud;

- almacenamiento;

- observabilidad;

- y políticas de gobernanza.

## 16.5 Licenciamiento y gobernanza

El uso de modelos fundacionales requiere considerar aspectos asociados a:

- licenciamiento;

- protección de datos;

- gobernanza;

- privacidad;

- retención de información;

- y compliance institucional.

Entre los principales temas a evaluar se encuentran:

### **A. Uso de APIs comerciales**

Consideraciones:

- términos de servicio;

- residencia de datos;

- retención temporal;

- controles empresariales;

- acuerdos institucionales.

### **B. Protección de información**

La arquitectura debería minimizar:

- exposición innecesaria de documentos;

- envío de información sensible;

- transferencia de datos no requeridos;

- y persistencia innecesaria de contexto.

### **C. Gobernanza institucional**

La implementación futura de capacidades IA requeriría definir:

- políticas de uso;

- controles de acceso;

- logging;

- trazabilidad;

- revisión humana;

- monitoreo;

- y mecanismos de validación.

### **D. Transparencia y explicabilidad**

Toda salida IA debería:

- poder explicarse;

- estar respaldada por evidencia;

- mantener trazabilidad documental;

- y permitir revisión posterior.

## 16.6 Consideraciones estratégicas

Desde una perspectiva estratégica, el principal valor potencial de la iniciativa no reside únicamente en incorporar IA generativa, sino en construir una arquitectura institucional capaz de combinar:

- datos históricos;

- trazabilidad documental;

- comparación contextual;

- reglas explicables;

- y capacidades de asistencia analítica.

La IA generativa debe entenderse como una capa complementaria dentro de un sistema más amplio de apoyo a revisión documental y fortalecimiento institucional.

En consecuencia, la propuesta prioriza:

- prudencia;

- gobernanza;

- trazabilidad;

- modularidad;

- y escalabilidad gradual.

# 17. Infraestructura y Tecnología

## Stack actual exploratorio

- Python;

- Streamlit;

- OpenAI API;

- PyMuPDF;

- análisis comparativo.

## Posibles evoluciones futuras

- Reflex/FastAPI;

- APIs desacopladas;

- almacenamiento vectorial;

- pipelines automatizados.

## Principios tecnológicos

- modularidad;

- trazabilidad;

- auditabilidad;

- simplicidad inicial;

- escalabilidad futura.

# 18. Conclusión

La propuesta busca explorar capacidades emergentes de análisis documental e IA aplicadas a contratación pública bajo un enfoque:

- prudente;

- explicable;

- trazable;

- incremental;

- y orientado a revisión humana.

El valor potencial de la iniciativa radica principalmente en:

- facilitar lectura documental;

- apoyar priorización;

- contextualizar requisitos;

- reducir carga cognitiva;

- fortalecer capacidades institucionales;

- y explorar nuevas herramientas preventivas y analíticas.

La propuesta no pretende reemplazar procesos institucionales existentes ni emitir conclusiones automáticas.

Se plantea como una línea exploratoria para evaluar el potencial uso responsable de analítica documental e inteligencia artificial en contextos de contratación pública.

# 19. Disclaimer

La herramienta y sus resultados constituyen un ejercicio exploratorio de apoyo analítico.

Los outputs generados:

- no constituyen dictamen técnico o legal;

- no determinan ilegalidad;

- no implican responsabilidad;

- no reemplazan revisión humana;

- y no representan interpretación oficial de normativa aplicable.
