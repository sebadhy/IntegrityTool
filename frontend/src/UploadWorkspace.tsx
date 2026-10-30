import { useRef, useState } from "react";
import {
  ArrowRight,
  ChevronDown,
  ChevronRight,
  FileText,
  FolderOpen,
  Info,
  Plus,
  Upload,
  X,
} from "lucide-react";
import { api } from "./api";
import { ROLES, type CaseSummary, type ReviewCase } from "./types";
type UploadEntry = {
  file: File;
  role: string;
  version: string;
  supersedes_index: number | null;
};
function formatDate(value: string) {
  return new Date(value).toLocaleDateString("es-EC", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}
export function UploadWorkspace({
  cases,
  onOpen,
  onError,
}: {
  cases: CaseSummary[];
  onOpen: (id: string) => void;
  onError: (message: string) => void;
}) {
  const [files, setFiles] = useState<UploadEntry[]>([]);
  const [title, setTitle] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const requestKey = useRef(crypto.randomUUID());

  function addFiles(list: FileList | null) {
    if (!list) return;
    const incoming = Array.from(list);
    if (
      files.length + incoming.length > 8 ||
      incoming.some(
        (file) =>
          !file.name.toLowerCase().endsWith(".pdf") ||
          file.size > 25 * 1024 * 1024,
      )
    ) {
      onError("Seleccione hasta 8 documentos PDF, de máximo 25 MB cada uno.");
      return;
    }
    setFiles((old) => [
      ...old,
      ...incoming.map((file) => ({
        file,
        role: /espec|ficha|tecnic|técnic/i.test(file.name)
          ? "especificaciones"
          : /adenda/i.test(file.name)
            ? "adenda"
            : "pliego",
        version: "1",
        supersedes_index: null,
      })),
    ]);
    requestKey.current = crypto.randomUUID();
    if (input.current) input.current.value = "";
  }
  function changeEntry(index: number, values: Partial<UploadEntry>) {
    setFiles((old) =>
      old.map((entry, i) => (i === index ? { ...entry, ...values } : entry)),
    );
    requestKey.current = crypto.randomUUID();
  }
  async function submit() {
    if (!files.length || submitting) return;
    setSubmitting(true);
    const form = new FormData();
    files.forEach((entry) => form.append("files", entry.file));
    form.append("title", title);
    form.append("request_key", requestKey.current);
    form.append(
      "manifest",
      JSON.stringify(
        files.map(({ role, version, supersedes_index }) => ({
          role,
          version,
          supersedes_index,
        })),
      ),
    );
    try {
      const result = await api<ReviewCase>("/cases", {
        method: "POST",
        body: form,
      });
      onOpen(result.id);
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }
  return (
    <main className="home-page">
      <section className="upload-workflow">
        <div className="section-index">
          01 <span>REVISIÓN DE EXPEDIENTE</span>
        </div>
        <h1>¿Qué documento necesita revisar?</h1>
        <p className="intro">
          Cargue el pliego y sus documentos relacionados. La revisión organiza
          aspectos que conviene validar y los vincula con su evidencia.
        </p>
        <div
          className={`upload-drop ${dragging ? "is-dragging" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            addFiles(e.dataTransfer.files);
          }}
        >
          <div className="upload-icon">
            <Upload size={23} strokeWidth={1.5} />
          </div>
          <div>
            <strong>Arrastre sus documentos PDF</strong>
            <p>Pliego, especificaciones, anexos o adendas.</p>
          </div>
          <button
            className="secondary-button"
            onClick={() => input.current?.click()}
          >
            <Plus size={16} /> Seleccionar archivos
          </button>
          <input
            ref={input}
            type="file"
            accept="application/pdf,.pdf"
            multiple
            hidden
            onChange={(e) => addFiles(e.target.files)}
          />
        </div>
        <p className="file-limits">
          Hasta 8 archivos · 25 MB por documento · 100 MB por expediente
        </p>
        {files.length > 0 && (
          <div className="selected-files">
            <label className="field-label">
              Nombre de la revisión <span>Opcional</span>
              <input
                value={title}
                placeholder="Por ejemplo: adquisición de equipos de laboratorio"
                onChange={(e) => {
                  setTitle(e.target.value);
                  requestKey.current = crypto.randomUUID();
                }}
                maxLength={200}
              />
            </label>
            <div className="upload-row upload-labels">
              <span>Documento</span>
              <span>Tipo documental</span>
              <span>Versión</span>
              <span>Sustituye a</span>
              <span />
            </div>
            {files.map((entry, index) => (
              <div className="upload-row" key={`${entry.file.name}-${index}`}>
                <span className="file-name">
                  <FileText size={17} />
                  <span>
                    {entry.file.name}
                    <small>
                      {(entry.file.size / 1024 / 1024).toFixed(1)} MB
                    </small>
                  </span>
                </span>
                <select
                  aria-label={`Tipo de ${entry.file.name}`}
                  value={entry.role}
                  onChange={(e) => changeEntry(index, { role: e.target.value })}
                >
                  {Object.entries(ROLES).map(([id, label]) => (
                    <option value={id} key={id}>
                      {label}
                    </option>
                  ))}
                </select>
                <input
                  aria-label={`Versión de ${entry.file.name}`}
                  value={entry.version}
                  onChange={(e) =>
                    changeEntry(index, { version: e.target.value })
                  }
                  maxLength={40}
                />
                <select
                  aria-label={`Documento sustituido por ${entry.file.name}`}
                  value={entry.supersedes_index ?? ""}
                  onChange={(e) =>
                    changeEntry(index, {
                      supersedes_index:
                        e.target.value === "" ? null : Number(e.target.value),
                    })
                  }
                >
                  <option value="">No sustituye</option>
                  {files.slice(0, index).map((file, i) => (
                    <option key={i} value={i}>
                      {file.file.name}
                    </option>
                  ))}
                </select>
                <button
                  className="icon-button"
                  aria-label={`Retirar ${entry.file.name}`}
                  title="Retirar documento"
                  onClick={() => {
                    setFiles((old) =>
                      old
                        .filter((_, i) => i !== index)
                        .map((entry) => ({ ...entry, supersedes_index: null })),
                    );
                    requestKey.current = crypto.randomUUID();
                  }}
                >
                  <X size={16} />
                </button>
              </div>
            ))}
            <div className="start-review">
              <span>
                Las versiones sustituidas se conservan para cotejo, no como
                requisitos vigentes.
              </span>
              <button
                className="primary-button"
                disabled={submitting}
                onClick={submit}
              >
                {submitting ? "Guardando documentos…" : "Iniciar revisión"}
                <ArrowRight size={17} />
              </button>
            </div>
          </div>
        )}
        <details className="how-it-works">
          <summary>
            <Info size={15} /> Alcance de la revisión <ChevronDown size={14} />
          </summary>
          <div>
            <p>
              <strong>La evidencia es el punto de partida.</strong> Se extrae y
              estructura el texto; las reglas y una taxonomía inicial organizan
              condiciones que conviene revisar, considerando equivalencias y
              justificaciones cercanas.
            </p>
            <p>
              La comparación con el corpus disponible aporta contexto, no
              acredita que un requisito sea adecuado. Cuando hay un modelo de
              lenguaje configurado, puede proponer aspectos adicionales sobre
              una selección de cláusulas y apoyar su explicación. Las citas se
              comprueban y las propuestas pasan por los mismos criterios de
              consolidación y prioridad; su interpretación requiere revisión humana.
            </p>
            <p>
              Las dimensiones analíticas son una propuesta inicial sujeta a
              validación institucional. La lectura no sustituye el expediente
              completo ni el criterio humano.
            </p>
          </div>
        </details>
      </section>
      <section className="recent-reviews">
        <div className="section-index">
          02 <span>CONTINUAR UNA REVISIÓN</span>
        </div>
        <h2>Revisiones recientes</h2>
        {cases.length ? (
          <div className="review-list">
            {cases.map((review) => (
              <button key={review.id} onClick={() => onOpen(review.id)}>
                <FolderOpen size={19} />
                <span>
                  <strong>{review.title}</strong>
                  <small>{formatDate(review.created_at)}</small>
                </span>
                <span className="recent-state">
                  {review.status === "ready"
                    ? "Disponible"
                    : ["failed", "interrupted"].includes(review.status)
                      ? "Requiere reintento"
                      : "En preparación"}
                </span>
                <ChevronRight size={17} />
              </button>
            ))}
          </div>
        ) : (
          <div className="empty-reviews">
            <FolderOpen size={25} strokeWidth={1.3} />
            <p>Las revisiones guardadas aparecerán aquí.</p>
            <small>
              Puede cerrarlas y retomarlas sin volver a analizar los documentos.
            </small>
          </div>
        )}
      </section>
    </main>
  );
}
