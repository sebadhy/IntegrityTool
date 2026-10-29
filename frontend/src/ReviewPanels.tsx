import { useEffect, useState } from "react";
import {
  Check,
  CheckCheck,
  ChevronDown,
  Clock3,
  MessageSquare,
  Search,
  X,
} from "lucide-react";
import {
  PRIORITIES,
  STATES,
  type Evidence,
  type Review,
  type ReviewCase,
  type ReviewItem,
  type ReviewState,
} from "./types";
export function ObservationQueue({
  items,
  selectedId,
  reviews,
  onSelect,
}: {
  items: ReviewItem[];
  selectedId: string;
  reviews: Record<string, Review>;
  onSelect: (item: ReviewItem) => void;
}) {
  const [query, setQuery] = useState("");
  const [all, setAll] = useState(false);
  useEffect(() => {
    if (items.findIndex((item) => item.id === selectedId) >= 5) setAll(true);
  }, [selectedId, items]);
  const filtered = items.filter((item) =>
    `${item.title} ${item.dimension_label}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  return (
    <aside className="observation-queue">
      <div className="queue-heading">
        <h2>Aspectos a revisar</h2>
        <span>{items.length}</span>
      </div>
      <label className="search-field">
        <Search size={15} />
        <input
          placeholder="Buscar observación"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Buscar observación"
        />
      </label>
      <div className="queue-items">
        {filtered.slice(0, all || query ? undefined : 5).map((item, i) => (
          <button
            className={`queue-item ${selectedId === item.id ? "selected" : ""}`}
            key={item.id}
            onClick={() => onSelect(item)}
            aria-current={selectedId === item.id ? "true" : undefined}
          >
            <span className="queue-number">
              {String(i + 1).padStart(2, "0")}
            </span>
            <span>
              <span className={`priority-text priority-${item.priority}`}>
                {PRIORITIES[item.priority]}
              </span>
              <strong>{item.title}</strong>
              <small>
                Pág.{" "}
                {Array.from(new Set(item.evidence.map((e) => e.page))).join(
                  ", ",
                )}{" "}
                · {STATES[reviews[item.id]?.state || "pending"]}
              </small>
            </span>
          </button>
        ))}
      </div>
      {!query && items.length > 5 && (
        <button className="queue-more" onClick={() => setAll((v) => !v)}>
          {all ? "Mostrar principales" : `Ver ${items.length - 5} adicionales`}
          <ChevronDown size={15} />
        </button>
      )}
      {filtered.length === 0 && (
        <p className="queue-empty">
          No hay observaciones que coincidan con la búsqueda.
        </p>
      )}
      <div className="queue-footnote">
        Prioridad de revisión, no nivel de riesgo.
      </div>
    </aside>
  );
}
export function ObservationDetail({
  item,
  evidence,
  evidenceIndex,
  review,
  assistance,
  onEvidence,
  onSave,
  saving,
}: {
  item: ReviewItem;
  evidence?: Evidence;
  evidenceIndex: number;
  review?: Review;
  assistance: NonNullable<ReviewCase["result"]>["assistance"];
  onEvidence: (index: number) => void;
  onSave: (state: ReviewState, comment: string) => void;
  saving: boolean;
}) {
  const [comment, setComment] = useState(review?.comment || "");
  const status = review?.state || "pending";
  const generated = assistance.calls.find(
    (call) => call.item_id === item.id && call.status === "completed",
  );
  return (
    <aside className="review-detail">
      <div className="detail-heading">
        <span className={`priority-text priority-${item.priority}`}>
          {PRIORITIES[item.priority]}
        </span>
        <h2>{item.title}</h2>
        <span className="dimension-label">{item.dimension_label}</span>
      </div>
      <section className="context-note">
        <h3>Por qué conviene revisar</h3>
        <p>{item.assisted_explanation || item.explanation}</p>
        {item.assisted_explanation && (
          <small className="assisted-note">
            Explicación redactada con apoyo de un modelo de lenguaje.
          </small>
        )}
      </section>
      <section className="evidence-note">
        <div className="detail-section-heading">
          <h3>Evidencia documental</h3>
          <span>
            {evidenceIndex + 1}/{item.evidence.length}
          </span>
        </div>
        {item.evidence.length > 1 && (
          <select
            className="evidence-select"
            aria-label="Seleccionar ocurrencia documental"
            value={evidenceIndex}
            onChange={(e) => onEvidence(Number(e.target.value))}
          >
            {item.evidence.map((ev, i) => (
              <option key={i} value={i}>
                Pág. {ev.page} · {ev.document_name}
              </option>
            ))}
          </select>
        )}
        <blockquote>{evidence?.text}</blockquote>
        <small>
          {evidence?.document_name} · página {evidence?.page}
        </small>
      </section>
      {item.mitigants.length > 0 && (
        <section className="mitigants-note">
          <h3>Factores que matizan la lectura</h3>
          <ul>
            {item.mitigants.map((factor) => (
              <li key={factor}>
                <Check size={13} />
                <span>{factor}</span>
              </li>
            ))}
          </ul>
          <small>Su presencia textual no garantiza aplicación efectiva.</small>
        </section>
      )}
      <section className="review-questions">
        <h3>Qué conviene validar</h3>
        <ul>
          {item.questions.slice(0, 3).map((question) => (
            <li key={question}>{question}</li>
          ))}
        </ul>
      </section>
      {item.historical_context.frequency_label &&
        item.historical_context.frequency_label !== "No disponible" && (
          <p className="historical-note">
            {item.historical_context.frequency_label}.{" "}
            {item.historical_context.comparative_comment} La frecuencia no
            acredita adecuación del requisito.
          </p>
        )}
      <section className="human-review">
        <div className="detail-section-heading">
          <h3>Su revisión</h3>
          <span className={`review-state state-${status}`}>
            {STATES[status]}
          </span>
        </div>
        <div className="human-actions">
          <button
            title="Registra que revisó el aspecto; no confirma una conclusión automática"
            className={status === "confirmed" ? "action-selected" : ""}
            disabled={saving}
            onClick={() => onSave("confirmed", comment)}
          >
            <CheckCheck size={15} /> Confirmar revisión
          </button>
          <button
            title="Descartar este aspecto en esta revisión"
            className={status === "discarded" ? "action-selected" : ""}
            disabled={saving}
            onClick={() => onSave("discarded", comment)}
          >
            <X size={15} /> Descartar
          </button>
          <button
            title="Dejar pendiente de seguimiento"
            className={status === "followup" ? "action-selected" : ""}
            disabled={saving}
            onClick={() => onSave("followup", comment)}
          >
            <Clock3 size={15} /> Seguimiento
          </button>
        </div>
        <details className="comment-details">
          <summary>
            <MessageSquare size={14} />
            {review?.comment ? "Ver o editar comentario" : "Agregar comentario"}
            <ChevronDown size={13} />
          </summary>
          <label>
            Nota de revisión
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              rows={3}
              maxLength={4000}
              placeholder="Registre lo verificado o la validación pendiente."
            />
          </label>
          <button
            className="secondary-button"
            disabled={saving}
            onClick={() => onSave(status, comment)}
          >
            Guardar comentario
          </button>
        </details>
        {review?.updated_at && (
          <small className="saved-note">
            Guardado el {new Date(review.updated_at).toLocaleString("es-EC")} ·
            Revisor local
          </small>
        )}
      </section>
      <details className="methodology-details">
        <summary>
          Cómo se generó esta observación <ChevronDown size={14} />
        </summary>
        <dl>
          <dt>Identificación</dt>
          <dd>Taxonomía documental · {item.pattern_id}</dd>
          <dt>Dimensión</dt>
          <dd>
            {item.dimension_label}. Organización analítica inicial, sujeta a
            validación.
          </dd>
          <dt>Consolidación</dt>
          <dd>
            {item.evidence.length} referencias documentales agrupadas. Repetir
            una referencia no aumenta prioridad.
          </dd>
          <dt>Prioridad</dt>
          <dd>
            <ul>
              {item.priority_factors.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
          </dd>
          <dt>Uso de modelo de lenguaje</dt>
          <dd>
            {generated
              ? `Intervino ${generated.provider} (${generated.model}) solo para redactar contexto. La detección y prioridad son determinísticas.`
              : "No se utilizó una explicación de modelo de lenguaje para esta observación."}
          </dd>
          <dt>Límites</dt>
          <dd>
            {item.limitations.join(" ")} Requiere cotejo humano; no es un
            dictamen técnico o jurídico.
          </dd>
        </dl>
      </details>
    </aside>
  );
}
