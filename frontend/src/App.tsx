import { lazy, Suspense, useEffect, useState } from "react";
import {
  ArrowLeft,
  ChevronDown,
  Download,
  FileText,
  Info,
  X,
} from "lucide-react";
import { api } from "./api";
import { ExecutiveReading, VersionComparison } from "./ExecutiveReading";
import { ObservationQueue, ObservationDetail } from "./ReviewPanels";
import { UploadWorkspace } from "./UploadWorkspace";
import type {
  CaseSummary,
  Review,
  ReviewCase,
  ReviewItem,
  ReviewState,
} from "./types";
const PdfReader = lazy(() =>
  import("./PdfReader").then((module) => ({ default: module.PdfReader })),
);
type View = "overview" | "review" | "versions";
function usable(value?: string) {
  return value && !/^(no ident|no dispon)/i.test(value);
}
export default function App() {
  const [caseId, setCaseId] = useState(
    new URLSearchParams(location.search).get("revision") || "",
  );
  const [activeCase, setActiveCase] = useState<ReviewCase | null>(null);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [error, setError] = useState("");
  const [view, setView] = useState<View>("overview");
  const [selectedId, setSelectedId] = useState("");
  const [evidenceIndex, setEvidenceIndex] = useState(0);
  const [documentId, setDocumentId] = useState("");
  const [saving, setSaving] = useState(false);
  const [announcement, setAnnouncement] = useState("");

  useEffect(() => {
    if (view === "review") {
      requestAnimationFrame(() =>
        document
          .querySelector(".case-navigation")
          ?.scrollIntoView({ block: "start" }),
      );
    }
  }, [view]);

  function openCase(id: string) {
    setCaseId(id);
    setActiveCase(null);
    setView("overview");
    setSelectedId("");
    setEvidenceIndex(0);
    setDocumentId("");
    setError("");
    history.pushState({}, "", id ? `?revision=${id}` : location.pathname);
  }
  useEffect(() => {
    const handler = () => {
      setCaseId(new URLSearchParams(location.search).get("revision") || "");
      setActiveCase(null);
      setView("overview");
      setSelectedId("");
      setEvidenceIndex(0);
      setDocumentId("");
      setError("");
    };
    window.addEventListener("popstate", handler);
    return () => window.removeEventListener("popstate", handler);
  }, []);
  useEffect(() => {
    if (!caseId)
      api<CaseSummary[]>("/cases")
        .then(setCases)
        .catch((e) => setError(e.message));
  }, [caseId]);
  useEffect(() => {
    if (!caseId) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const value = await api<ReviewCase>(`/cases/${caseId}`);
        if (stopped) return;
        setActiveCase(value);
        if (
          value.status === "queued" ||
          value.status === "running" ||
          ["pending", "running"].includes(value.result?.assistance.status || "")
        )
          timer = setTimeout(load, 1800);
      } catch (e) {
        if (!stopped) setError((e as Error).message);
      }
    }
    void load();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [caseId]);

  const result = activeCase?.result;
  const items = result?.items || [];
  const selected = items.find((item) => item.id === selectedId) || items[0];
  const evidence = selected?.evidence[evidenceIndex] || selected?.evidence[0];
  const docs = result?.documents || activeCase?.documents || [];
  const currentDocId = documentId || evidence?.document_id || docs[0]?.id || "";
  const mainDoc =
    docs.find(
      (doc) =>
        doc.role === "pliego" && !docs.some((d) => d.supersedes === doc.id),
    ) ||
    docs.find((doc) => !docs.some((d) => d.supersedes === doc.id)) ||
    docs[0];
  const metadata = mainDoc?.metadata || {};

  function selectItem(item: ReviewItem) {
    setSelectedId(item.id);
    setEvidenceIndex(0);
    setDocumentId(item.evidence[0]?.document_id || "");
    setView("review");
  }
  async function saveReview(state: ReviewState, comment: string) {
    if (!activeCase || !selected || saving) return;
    setSaving(true);
    setError("");
    try {
      const saved = await api<Review>(
        `/cases/${activeCase.id}/items/${selected.id}/review`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ state, comment, reviewer: "Revisor local" }),
        },
      );
      setActiveCase((value) =>
        value
          ? { ...value, reviews: { ...value.reviews, [selected.id]: saved } }
          : value,
      );
      setAnnouncement("Revisión guardada.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <header className="app-header">
        <button
          className="brand"
          onClick={() => openCase("")}
          aria-label="Integrity Tool, ir a revisiones"
        >
          <span className="brand-symbol">
            i<span />
          </span>
          <strong>Integrity</strong>
          <span className="brand-divider" />
          <span className="brand-description">Revisión documental</span>
        </button>
        <span className="environment">Espacio local de trabajo</span>
      </header>
      <div className="announcement" aria-live="polite">
        {announcement}
      </div>
      {error && (
        <div className="global-error" role="alert">
          <Info size={17} />
          <span>{error}</span>
          <button
            className="icon-button"
            onClick={() => setError("")}
            aria-label="Cerrar mensaje"
          >
            <X size={16} />
          </button>
        </div>
      )}
      {!caseId ? (
        <UploadWorkspace cases={cases} onOpen={openCase} onError={setError} />
      ) : (
        <main className={`case-page ${view === "review" ? "is-review" : ""}`}>
          <div className="case-breadcrumb">
            <button onClick={() => openCase("")}>
              <ArrowLeft size={14} /> Revisiones
            </button>
            <span>/</span>
            <span>{activeCase?.title || "Abriendo expediente"}</span>
          </div>
          {!activeCase && !error && (
            <p className="loading-note">Abriendo revisión…</p>
          )}
          {activeCase && ["queued", "running"].includes(activeCase.status) && (
            <div className="processing-state">
              <FileText size={32} strokeWidth={1.3} />
              <h1>Preparando la revisión</h1>
              <p>
                Los documentos se conservan en este espacio. Puede volver a
                abrir esta revisión sin repetir la carga.
              </p>
              <span className="working-indicator">
                {activeCase.status === "queued"
                  ? "En espera"
                  : "Lectura documental en curso"}
              </span>
            </div>
          )}
          {activeCase &&
            ["failed", "interrupted"].includes(activeCase.status) && (
              <div className="processing-state">
                <h1>La revisión no se completó</h1>
                <p>{activeCase.error}</p>
                <button
                  className="primary-button"
                  onClick={async () => {
                    try {
                      await api(`/cases/${caseId}/retry`, { method: "POST" });
                      const id = caseId;
                      setCaseId("");
                      setTimeout(() => setCaseId(id), 0);
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                >
                  Reintentar revisión
                </button>
              </div>
            )}
          {result && (
            <>
              <section className="case-heading">
                <div className="case-heading-top">
                  <span className="eyebrow">EXPEDIENTE DOCUMENTAL</span>
                  <span className="preliminary-state">
                    <span /> Revisión preliminar
                  </span>
                </div>
                <h1>
                  {usable(metadata.entidad)
                    ? metadata.entidad
                    : activeCase?.title}
                </h1>
                <p className="procurement-object">
                  {usable(metadata.objeto)
                    ? metadata.objeto
                    : "Objeto no identificado automáticamente. Consulte el documento original."}
                </p>
                <div className="case-facts">
                  <span>
                    <FileText size={14} />
                    {docs.length}{" "}
                    {docs.length === 1 ? "documento" : "documentos"}
                  </span>
                  {usable(metadata.tipo_procedimiento) && (
                    <span>{metadata.tipo_procedimiento}</span>
                  )}
                  {usable(metadata.presupuesto) && (
                    <span>Presupuesto: {metadata.presupuesto}</span>
                  )}
                  {usable(metadata.fecha) && <span>{metadata.fecha}</span>}
                </div>
              </section>
              <div className="case-navigation">
                <nav aria-label="Vistas de la revisión">
                  <button
                    aria-current={view === "overview" ? "page" : undefined}
                    onClick={() => setView("overview")}
                  >
                    Lectura general
                  </button>
                  <button
                    aria-current={view === "review" ? "page" : undefined}
                    onClick={() => setView("review")}
                  >
                    Revisar documentos
                  </button>
                  {result.version_changes.length > 0 && (
                    <button
                      aria-current={view === "versions" ? "page" : undefined}
                      onClick={() => setView("versions")}
                    >
                      Contrastar versiones{" "}
                      <span>{result.version_changes.length}</span>
                    </button>
                  )}
                </nav>
                <details className="export-menu">
                  <summary>
                    <Download size={16} /> Exportar <ChevronDown size={13} />
                  </summary>
                  <div>
                    <a href={`/api/cases/${caseId}/export?format=html`}>
                      Informe de revisión · HTML
                    </a>
                    <a href={`/api/cases/${caseId}/export?format=csv`}>
                      Evidencias y revisión · CSV
                    </a>
                    <a href={`/api/cases/${caseId}/export?format=json`}>
                      Trazabilidad · JSON
                    </a>
                  </div>
                </details>
              </div>
              {result.messages.length > 0 && (
                <div className="document-notice">
                  <Info size={16} />
                  <span>{result.messages.join(" ")}</span>
                </div>
              )}
              {view === "overview" && (
                <ExecutiveReading
                  reviewCase={activeCase!}
                  onSelect={selectItem}
                  onDocument={(id) => {
                    setDocumentId(id);
                    setView("review");
                  }}
                />
              )}
              {view === "review" && (
                <div className="review-workspace">
                  <ObservationQueue
                    items={items}
                    selectedId={selected?.id || ""}
                    reviews={activeCase!.reviews}
                    onSelect={selectItem}
                  />
                  <Suspense
                    fallback={
                      <div className="pdf-reader">
                        <p className="loading-note">
                          Abriendo visor documental…
                        </p>
                      </div>
                    }
                  >
                    <PdfReader
                      caseId={caseId}
                      documents={docs}
                      evidence={evidence}
                      documentId={currentDocId}
                      onDocumentChange={setDocumentId}
                    />
                  </Suspense>
                  {selected ? (
                    <ObservationDetail
                      key={selected.id}
                      item={selected}
                      evidence={evidence}
                      evidenceIndex={evidenceIndex}
                      review={activeCase!.reviews[selected.id]}
                      assistance={result.assistance}
                      onEvidence={(index) => {
                        setEvidenceIndex(index);
                        setDocumentId(selected.evidence[index].document_id);
                      }}
                      onSave={saveReview}
                      saving={saving}
                    />
                  ) : (
                    <aside className="review-detail">
                      <h2>Lectura manual</h2>
                      <p>
                        No se identificaron aspectos priorizados con el alcance
                        de esta revisión. Puede consultar los documentos completos.
                      </p>
                    </aside>
                  )}
                </div>
              )}
              {view === "versions" && (
                <VersionComparison reviewCase={activeCase!} />
              )}
            </>
          )}
        </main>
      )}
      <footer className="app-footer">
        <span>Insumo preliminar para revisión humana.</span>
        <span>No reemplaza el análisis técnico o jurídico.</span>
      </footer>
    </>
  );
}
