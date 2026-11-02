import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Search, X } from "lucide-react";
import { api } from "./api";
import type { SercopSnapshot } from "./types";

type Process = {
  ocid: string;
  code: string;
  buyer: string;
  description: string;
  procedure: string;
};
type Results = {
  total: number;
  page: number;
  pages: number;
  results: Process[];
  omitted_count: number;
};

export function SercopSearch({
  selected,
  onSelect,
}: {
  selected: SercopSnapshot | null;
  onSelect: (value: SercopSnapshot | null) => void;
}) {
  const [method, setMethod] = useState("search");
  const [year, setYear] = useState(new Date().getFullYear());
  const [search, setSearch] = useState("");
  const [buyer, setBuyer] = useState("");
  const [supplier, setSupplier] = useState("");
  const [ocid, setOcid] = useState("");
  const [results, setResults] = useState<Results | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);

  async function run(path: string, init?: RequestInit) {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    setError("");
    try {
      if (path.includes("/search?"))
        setResults(
          await api<Results>(path, { ...init, signal: controller.signal }),
        );
      else
        onSelect(
          await api<SercopSnapshot>(path, {
            ...init,
            signal: controller.signal,
          }),
        );
    } catch (e) {
      if (!controller.signal.aborted) setError((e as Error).message);
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  function load(ocid: string) {
    return run("/sources/sercop/record", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ocid }),
    });
  }
  function find(page = 1) {
    const query = new URLSearchParams({
      year: String(year),
      search,
      page: String(page),
    });
    if (buyer.trim()) query.set("buyer", buyer.trim());
    if (supplier.trim()) query.set("supplier", supplier.trim());
    return run(`/sources/sercop/search?${query}`);
  }
  if (selected)
    return (
      <section
        className="sercop-selection"
        aria-label="Proceso seleccionado en SERCOP"
      >
        <div className="sercop-selection-heading">
          <h2>{selected.code}</h2>
          <button
            className="icon-button"
            title="Cambiar proceso"
            aria-label="Cambiar proceso"
            onClick={() => {
              onSelect(null);
              setBusy(false);
            }}
          >
            <X size={17} />
          </button>
        </div>
        <dl className="sercop-facts">
          <dt>Entidad contratante</dt>
          <dd>{selected.metadata.entidad || "No informada en el registro"}</dd>
          {selected.buyer !== selected.metadata.entidad && (
            <>
              <dt>Comprador</dt>
              <dd>{selected.buyer || "No informado"}</dd>
            </>
          )}
          <dt>Objeto</dt>
          <dd>{selected.metadata.objeto || "No informado en el registro"}</dd>
          <dt>Procedimiento</dt>
          <dd>{selected.metadata.tipo_procedimiento || "No informado"}</dd>
          <dt>Presupuesto referencial</dt>
          <dd>
            {selected.metadata.presupuesto ||
              "No informado; no se estimó con otros montos"}
          </dd>
        </dl>
        <p className="sercop-note">
          {selected.document_reference_count
            ? `La API informa ${selected.document_reference_count} referencias documentales; no se descargaron ni verificaron como PDF.`
            : "El registro consultado no incluye enlaces documentales. Agregue los PDF para revisar su contenido."}
        </p>
        <small>
          Fuente: SERCOP · consulta{" "}
          {new Date(selected.retrieved_at).toLocaleString("es-EC")} ·{" "}
          <a
            href={selected.source_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            Consultar registro oficial
          </a>
        </small>
      </section>
    );

  return (
    <section className="sercop-search" aria-label="Buscar procesos en SERCOP">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void (method === "ocid" ? load(ocid) : find());
        }}
      >
        <fieldset disabled={busy}>
          <label className="field-label">
            Buscar por
            <select
              aria-label="Buscar por"
              value={method}
              onChange={(e) => {
                setMethod(e.target.value);
                setResults(null);
                setError("");
              }}
            >
              <option value="search">Código o palabras clave</option>
              <option value="ocid">Identificador OCID</option>
            </select>
          </label>
          {method === "search" ? (
            <>
              <div className="sercop-search-fields">
                <label className="field-label">
                  Año
                  <select
                  aria-label="Año"
                    value={year}
                    onChange={(e) => {
                      setYear(Number(e.target.value));
                      setResults(null);
                    }}
                  >
                    {Array.from(
                      { length: new Date().getFullYear() - 2014 },
                      (_, i) => new Date().getFullYear() - i,
                    ).map((value) => (
                      <option key={value}>{value}</option>
                    ))}
                  </select>
                </label>
                <label className="field-label">
                  Código o palabras clave
                  <input
                    required
                    minLength={3}
                    maxLength={200}
                    value={search}
                    placeholder="Ej.: SIE-HCAM-2026-023 o medicamentos"
                    onChange={(e) => {
                      setSearch(e.target.value);
                      setResults(null);
                    }}
                  />
                </label>
              </div>
              <details className="sercop-more">
                <summary>Más filtros</summary>
                <div className="sercop-search-fields equal">
                  <label className="field-label">
                    Entidad contratante
                    <input
                      minLength={3}
                      maxLength={200}
                      value={buyer}
                      placeholder="Nombre o parte del nombre"
                      onChange={(e) => {
                        setBuyer(e.target.value);
                        setResults(null);
                      }}
                    />
                  </label>
                  <label className="field-label">
                    Proveedor
                    <input
                      minLength={3}
                      maxLength={200}
                      value={supplier}
                      placeholder="Nombre o parte del nombre"
                      onChange={(e) => {
                        setSupplier(e.target.value);
                        setResults(null);
                      }}
                    />
                  </label>
                </div>
                <small>
                  Los filtros de texto requieren al menos tres caracteres. La
                  búsqueda por proveedor puede no devolver procesos sin
                  proveedor publicado.
                </small>
              </details>
            </>
          ) : (
            <label className="field-label">
              OCID
              <input
                required
                maxLength={200}
                value={ocid}
                placeholder="ocds-5wno2w-…"
                onChange={(e) => setOcid(e.target.value)}
              />
            </label>
          )}
          <button className="primary-button" type="submit">
            <Search size={16} />
            {busy ? "Consultando SERCOP…" : "Buscar proceso"}
          </button>
        </fieldset>
      </form>
      <div aria-live="polite">
        {error && <p role="alert">{error}</p>}
        {results && (
          <>
            <p>
              {results.total} resultados informados por SERCOP · Página{" "}
              {results.page} de {Math.max(1, results.pages)}
            </p>
            {!results.results.length && (
              <p>
                No se encontraron procesos con estos criterios. Cambie las
                palabras o retire algún filtro.
              </p>
            )}
            {!!results.omitted_count && (
              <p>
                Algunos resultados se omitieron porque no contenían un OCID
                verificable.
              </p>
            )}
            <ol className="sercop-results">
              {results.results.map((process, index) => (
                <li key={`${process.ocid}-${index}`}>
                  <div>
                    <strong>{process.code}</strong>
                    <p>{process.buyer || "Entidad no informada"}</p>
                    <p>
                      {process.description ||
                        "Objeto no informado en el resultado; consulte la ficha."}
                    </p>
                    <small>
                      {process.procedure || "Procedimiento no informado"}
                    </small>
                  </div>
                  <button
                    className="secondary-button"
                    disabled={busy}
                    onClick={() => void load(process.ocid)}
                  >
                    Seleccionar proceso <ArrowRight size={15} />
                  </button>
                </li>
              ))}
            </ol>
            <div className="sercop-pagination">
              <button
                className="secondary-button"
                disabled={busy || results.page <= 1}
                onClick={() => void find(results.page - 1)}
              >
                <ArrowLeft size={15} />
                Anterior
              </button>
              <button
                className="secondary-button"
                disabled={busy || results.page >= results.pages}
                onClick={() => void find(results.page + 1)}
              >
                Siguiente
                <ArrowRight size={15} />
              </button>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
