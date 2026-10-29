import { useEffect, useRef, useState } from "react";
import {
  getDocument,
  GlobalWorkerOptions,
  type PDFDocumentProxy,
  type RenderTask,
} from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import {
  ChevronLeft,
  ChevronRight,
  Minus,
  Plus,
  Maximize2,
  Minimize2,
  Download,
  CornerUpLeft,
} from "lucide-react";
import { documentUrl } from "./api";
import type { CaseDocument, Evidence } from "./types";

GlobalWorkerOptions.workerSrc = workerUrl;

export function PdfReader({
  caseId,
  documents,
  evidence,
  documentId,
  onDocumentChange,
}: {
  caseId: string;
  documents: CaseDocument[];
  evidence?: Evidence;
  documentId: string;
  onDocumentChange: (id: string) => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const paper = useRef<HTMLDivElement>(null);
  const viewport = useRef<HTMLDivElement>(null);
  const task = useRef<RenderTask | null>(null);
  const section = useRef<HTMLElement>(null);
  const expandButton = useRef<HTMLButtonElement>(null);
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [page, setPage] = useState(evidence?.page || 1);
  const [zoom, setZoom] = useState(1);
  const [width, setWidth] = useState(700);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [fullscreen, setFullscreen] = useState(false);
  const [rendered, setRendered] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError("");
    setPdf(null);
    setPage(1);
    setRendered(false);
    const loader = getDocument({
      url: documentUrl(caseId, documentId),
      cMapUrl: "/pdf-assets/cmaps/",
      cMapPacked: true,
      standardFontDataUrl: "/pdf-assets/standard_fonts/",
      wasmUrl: "/pdf-assets/wasm/",
    });
    let active = true;
    loader.promise
      .then((doc) => {
        if (active) {
          setPdf(doc);
          setLoading(false);
        }
      })
      .catch(() => {
        if (active) {
          setError(
            "No se pudo abrir el documento. Puede descargar el original.",
          );
          setLoading(false);
        }
      });
    return () => {
      active = false;
      task.current?.cancel();
      void loader.destroy();
    };
  }, [caseId, documentId]);

  useEffect(() => {
    if (evidence?.document_id === documentId) {
      setPage(evidence.page);
      viewport.current?.scrollTo({ top: 0 });
    }
  }, [evidence?.document_id, evidence?.page, evidence?.text, documentId, pdf]);
  useEffect(() => {
    if (!viewport.current) return;
    const observer = new ResizeObserver((entries) =>
      setWidth(Math.max(240, entries[0].contentRect.width - 40)),
    );
    observer.observe(viewport.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!pdf || !canvas.current) return;
    let active = true;
    task.current?.cancel();
    setRendered(false);
    setError("");
    const draw = async () => {
      try {
        const pdfPage = await pdf.getPage(Math.min(page, pdf.numPages));
        if (!active || !canvas.current) return;
        const initial = pdfPage.getViewport({ scale: 1 });
        const view = pdfPage.getViewport({
          scale: (width / initial.width) * zoom,
        });
        const ratio = Math.min(window.devicePixelRatio || 1, 2);
        const element = canvas.current;
        element.width = Math.ceil(view.width * ratio);
        element.height = Math.ceil(view.height * ratio);
        element.style.width = `${view.width}px`;
        element.style.height = `${view.height}px`;
        if (paper.current) paper.current.style.width = `${view.width}px`;
        const rendering = pdfPage.render({
          canvas: element,
          viewport: view,
          transform: [ratio, 0, 0, ratio, 0, 0],
        });
        task.current = rendering;
        await rendering.promise;
        if (active) setRendered(true);
      } catch (e) {
        if (active && (e as Error).name !== "RenderingCancelledException")
          setError("No se pudo visualizar esta página.");
      }
    };
    void draw();
    return () => {
      active = false;
      task.current?.cancel();
    };
  }, [pdf, page, zoom, width]);

  useEffect(() => {
    if (!fullscreen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setFullscreen(false);
      if (event.key === "Tab") {
        const controls = section.current?.querySelectorAll<HTMLElement>(
          "button:not([disabled]), a, select, input",
        );
        if (!controls?.length) return;
        const first = controls[0],
          last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    const old = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    expandButton.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = old;
      expandButton.current?.focus();
    };
  }, [fullscreen]);

  const highlighted =
    rendered && evidence?.document_id === documentId && evidence.page === page;
  const superseded = documents.some((doc) => doc.supersedes === documentId);
  const browsingAway =
    !!evidence &&
    (evidence.document_id !== documentId || evidence.page !== page);
  useEffect(() => {
    if (
      !highlighted ||
      !evidence?.rects?.length ||
      !paper.current ||
      !viewport.current
    )
      return;
    const top =
      Math.min(...evidence.rects.map((rect) => rect[1])) *
      paper.current.clientHeight;
    viewport.current.scrollTop = Math.max(0, top - 70);
  }, [highlighted, evidence?.text, evidence?.page, documentId, rendered]);
  return (
    <section
      ref={section}
      role={fullscreen ? "dialog" : undefined}
      aria-modal={fullscreen || undefined}
      className={`pdf-reader ${fullscreen ? "pdf-fullscreen" : ""}`}
      aria-label="Documento original"
    >
      <div className="document-toolbar">
        <select
          aria-label="Documento del expediente"
          value={documentId}
          onChange={(e) => onDocumentChange(e.target.value)}
        >
          {documents.map((doc) => (
            <option key={doc.id} value={doc.id}>
              {doc.name}
              {documents.some((d) => d.supersedes === doc.id)
                ? " · Sustituido"
                : ""}
            </option>
          ))}
        </select>
        <a
          className="icon-button"
          href={documentUrl(caseId, documentId)}
          download={documents.find((d) => d.id === documentId)?.name}
          title="Descargar documento original"
          aria-label="Descargar documento original"
        >
          <Download size={17} />
        </a>
        <button
          className="icon-button"
          title={
            fullscreen ? "Salir de pantalla completa" : "Ampliar documento"
          }
          aria-label={
            fullscreen ? "Salir de pantalla completa" : "Ampliar documento"
          }
          ref={expandButton}
          onClick={() => setFullscreen((v) => !v)}
        >
          {fullscreen ? <Minimize2 size={17} /> : <Maximize2 size={17} />}
        </button>
      </div>
      <div className="pdf-navigation">
        <div className="page-controls">
          <button
            className="icon-button"
            aria-label="Página anterior"
            title="Página anterior"
            disabled={!pdf || page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            <ChevronLeft size={17} />
          </button>
          <label>
            Pág.{" "}
            <input
              aria-label="Número de página"
              type="number"
              min="1"
              max={pdf?.numPages || 1}
              value={page}
              onChange={(e) =>
                setPage(
                  Math.max(
                    1,
                    Math.min(pdf?.numPages || 1, Number(e.target.value) || 1),
                  ),
                )
              }
            />{" "}
            <span>de {pdf?.numPages || "—"}</span>
          </label>
          <button
            className="icon-button"
            aria-label="Página siguiente"
            title="Página siguiente"
            disabled={!pdf || page >= pdf.numPages}
            onClick={() => setPage((p) => p + 1)}
          >
            <ChevronRight size={17} />
          </button>
        </div>
        <div className="zoom-controls">
          <button
            className="icon-button"
            aria-label="Reducir zoom"
            title="Reducir zoom"
            disabled={zoom <= 0.6}
            onClick={() => setZoom((z) => Math.max(0.6, z - 0.2))}
          >
            <Minus size={15} />
          </button>
          <button
            className="zoom-label"
            title="Ajustar al ancho"
            onClick={() => setZoom(1)}
          >
            {Math.round(zoom * 100)} %
          </button>
          <button
            className="icon-button"
            aria-label="Aumentar zoom"
            title="Aumentar zoom"
            disabled={zoom >= 2}
            onClick={() => setZoom((z) => Math.min(2, z + 0.2))}
          >
            <Plus size={15} />
          </button>
        </div>
      </div>
      {(superseded || browsingAway) && (
        <div className="pdf-context-notice" role="status">
          <span>
            {superseded
              ? "Versión sustituida; conservada para cotejo."
              : "Consulta del documento original."}
            {browsingAway && " Esta página no es la evidencia seleccionada."}
          </span>
          {browsingAway && (
            <button
              className="text-button"
              onClick={() => {
                onDocumentChange(evidence.document_id);
                setPage(evidence.page);
                viewport.current?.scrollTo({ top: 0 });
              }}
            >
              <CornerUpLeft size={15} /> Volver al fragmento
            </button>
          )}
        </div>
      )}
      <div className="pdf-viewport" ref={viewport} aria-busy={loading}>
        {loading && <p className="loading-note">Abriendo documento…</p>}
        {error && (
          <p role="alert" className="error-note">
            {error}
          </p>
        )}
        <div className="pdf-paper" ref={paper} hidden={loading || !!error}>
          <canvas
            ref={canvas}
            aria-label={`Página ${page} del documento original`}
          />
          {highlighted &&
            evidence.rects?.map((rect, i) => (
              <span
                key={i}
                className="pdf-highlight"
                style={{
                  left: `${rect[0] * 100}%`,
                  top: `${rect[1] * 100}%`,
                  width: `${(rect[2] - rect[0]) * 100}%`,
                  height: `${(rect[3] - rect[1]) * 100}%`,
                }}
              />
            ))}
        </div>
      </div>
      <div className="pdf-footer">
        <span>
          {highlighted && evidence.rects?.length
            ? evidence.location_precision === "excerpt"
              ? "Fragmento localizado en el original"
              : evidence.location_precision === "excerpt_prefix"
                ? "Inicio del fragmento localizado; coteje el texto completo"
                : "Término coincidente resaltado; coteje el fragmento"
            : highlighted
              ? "Ubicación exacta no confirmada; coteje la página"
              : "Documento original · sin alteraciones"}
        </span>
        <span>PDF</span>
      </div>
    </section>
  );
}
