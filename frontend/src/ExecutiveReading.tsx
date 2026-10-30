import { ArrowRight, ChevronDown, FileText } from "lucide-react";
import { PRIORITIES, ROLES, type ReviewCase, type ReviewItem } from "./types";
export function ExecutiveReading({
  reviewCase,
  onSelect,
  onDocument,
}: {
  reviewCase: ReviewCase;
  onSelect: (item: ReviewItem) => void;
  onDocument: (id: string) => void;
}) {
  const result = reviewCase.result!;
  const reviewed = Object.values(reviewCase.reviews).filter(
    (review) => review.state !== "pending",
  ).length;
  return (
    <div className="executive-reading">
      <section className="reading-intro">
        <div className="section-index">LECTURA PRELIMINAR</div>
        <h2>Por dónde comenzar la revisión</h2>
        <p>{result.assisted_summary || result.summary}</p>
        <span className="reading-provenance">
          {result.assisted_summary
            ? "Síntesis redactada con apoyo de un modelo de lenguaje, sobre aspectos sustentados en evidencia."
            : "Síntesis estructurada a partir de los aspectos y la evidencia documental."}
        </span>
        {result.semantic_review?.coverage && result.semantic_review.status === "completed" && (
          <span className="reading-provenance">
            Lectura contextual adicional sobre {result.semantic_review.coverage.selected_clause_count}
            {" de "}{result.semantic_review.coverage.active_clause_count} cláusulas activas.
            {" "}Las propuestas requieren validación humana; no es una revisión semántica completa.
          </span>
        )}
      </section>
      <section className="priorities-section">
        <div className="section-heading">
          <div>
            <h2>
              Aspectos sugeridos para revisión{" "}
              <span>{result.items.length}</span>
            </h2>
            <p>
              El orden orienta qué mirar primero; no expresa una conclusión
              sobre el procedimiento.
            </p>
          </div>
          {reviewed > 0 && <small>{reviewed} con revisión registrada</small>}
        </div>
        {result.items.length ? (
          <div className="overview-observations">
            {result.items.slice(0, 5).map((item, index) => (
              <div className="overview-row" key={item.id}>
                <span className="row-index">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div>
                  <span className={`priority-text priority-${item.priority}`}>
                    {PRIORITIES[item.priority]}
                  </span>
                  <h3>{item.title}</h3>
                  <p>{item.evidence[0]?.text}</p>
                  <small>
                    {item.evidence[0]?.document_name} · pág.{" "}
                    {item.evidence[0]?.page}{" "}
                    {item.evidence.length > 1 &&
                      `· ${item.evidence.length} referencias`}
                  </small>
                </div>
                <button className="text-button" onClick={() => onSelect(item)}>
                  Revisar evidencia <ArrowRight size={16} />
                </button>
              </div>
            ))}
          </div>
        ) : (
          <p className="neutral-empty">
            No hay aspectos priorizados con el alcance de esta revisión. Puede
            continuar con la lectura de los originales.
          </p>
        )}
        {result.items.length > 5 && (
          <button
            className="text-button additional-link"
            onClick={() => onSelect(result.items[5])}
          >
            Consultar {result.items.length - 5} aspectos adicionales{" "}
            <ArrowRight size={16} />
          </button>
        )}
      </section>
      <section className="case-documents">
        <div className="section-heading">
          <h2>Documentos del expediente</h2>
          <small>Originales conservados sin modificación</small>
        </div>
        {result.documents.map((doc) => (
          <button key={doc.id} onClick={() => onDocument(doc.id)}>
            <FileText size={20} />
            <span>
              <strong>{doc.name}</strong>
              <small>
                {ROLES[doc.role]} · versión {doc.version} ·{" "}
                {doc.analysis?.page_count} páginas{" "}
                {result.documents.some((d) => d.supersedes === doc.id) &&
                  "· Sustituido"}
              </small>
            </span>
            <span>Abrir documento</span>
            <ArrowRight size={15} />
          </button>
        ))}
      </section>
      <details className="audit-details">
        <summary>
          Alcance y trazabilidad de esta lectura <ChevronDown size={14} />
        </summary>
        <p>
          Se revisó texto extraído de los archivos cargados. No se verificó el
          mercado completo ni la justificación que pudiera existir fuera del
          expediente. La ausencia de observaciones no acredita cumplimiento.
        </p>
        <p>
          La priorización aplica criterios explícitos sobre contenido sustantivo, obligatoriedad,
          mitigantes y contexto histórico disponible; la repetición no aumenta
          la prioridad.
        </p>
        <p>
          {result.corpus.total_processes
            ? `Comparación con ${result.corpus.total_processes} procesos del corpus disponible. ${result.corpus.scope}`
            : "Sin comparación histórica utilizable en esta revisión."}
        </p>
        <dl>
          <dt>Motor</dt>
          <dd>{result.provenance.engine_version}</dd>
          <dt>Huella de la taxonomía</dt>
          <dd className="mono">{result.provenance.taxonomy_sha256}</dd>
          <dt>Copia de las reglas</dt>
          <dd>
            {result.provenance.taxonomy_archived ? (
              <a href={`/api/cases/${reviewCase.id}/taxonomy`} download>
                Descargar taxonomía utilizada
              </a>
            ) : (
              "Esta revisión anterior no conserva una copia de las reglas."
            )}
          </dd>
          <dt>Procesamiento asistido</dt>
          <dd>
            {
              result.assistance.calls.filter(
                (call) => call.status === "completed",
              ).length
            }{" "}
            solicitudes completadas. Puede proponer candidatos con citas verificadas;
            no asigna la prioridad final ni reemplaza la revisión humana.
          </dd>
        </dl>
      </details>
    </div>
  );
}
export function VersionComparison({ reviewCase }: { reviewCase: ReviewCase }) {
  return (
    <section className="version-comparison">
      <div className="section-index">COTEJO DOCUMENTAL</div>
      <h2>Cambios entre versiones relacionadas</h2>
      <p>
        Se comparan únicamente documentos que usted marcó como versiones
        sustituidas. Las diferencias de texto no confirman una contradicción ni
        su alcance jurídico.
      </p>
      {reviewCase.result!.version_changes.map((change, i) => (
        <article key={`${change.pattern_id}-${i}`}>
          <div className="version-change-heading">
            <h3>{change.title}</h3>
            <span>{change.change}</span>
          </div>
          <div className="version-columns">
            <div>
              <h4>Versión anterior</h4>
              <small>
                {change.previous_document}
                {change.previous_version &&
                  ` · versión ${change.previous_version}`}
              </small>
              {(change.removed_evidence ?? change.previous_evidence).map(
                (ev, j) => (
                  <blockquote key={j}>
                    <span>Pág. {ev.page}</span>
                    {ev.text}
                  </blockquote>
                ),
              )}
              {!(change.removed_evidence ?? change.previous_evidence)
                .length && (
                <p>
                  {change.previous_evidence.length
                    ? "No se retiraron referencias de esta observación."
                    : "No se identificó esta referencia con las reglas disponibles."}
                </p>
              )}
            </div>
            <div>
              <h4>Versión nueva</h4>
              <small>
                {change.current_document}
                {change.current_version &&
                  ` · versión ${change.current_version}`}
              </small>
              {(change.added_evidence ?? change.current_evidence).map(
                (ev, j) => (
                  <blockquote key={j}>
                    <span>Pág. {ev.page}</span>
                    {ev.text}
                  </blockquote>
                ),
              )}
              {!(change.added_evidence ?? change.current_evidence).length && (
                <p>
                  {change.current_evidence.length
                    ? "No se añadieron referencias a esta observación."
                    : "No se identificó esta referencia con las reglas disponibles."}
                </p>
              )}
            </div>
          </div>
          {!!change.unchanged_reference_count && (
            <p>
              {change.unchanged_reference_count} referencia(s) sin cambios; se
              muestran solo las diferencias.
            </p>
          )}
          <small>{change.limitation}</small>
        </article>
      ))}
    </section>
  );
}
