import { useEffect, useId, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { api } from "./api";

type Suggestion = { id: string; value: string; label: string; detail: string };
type Suggestions = { options: Suggestion[]; source: string; message: string };

/** Suggestions complete text filters; they never select or analyze a process. */
export function SearchableTextFilter({
  label,
  value,
  onChange,
  field,
  year,
  buyer = "",
  supplier = "",
  required = false,
  placeholder = "Escriba un nombre o parte de él",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  field: "buyer" | "supplier" | "search";
  year: number;
  buyer?: string;
  supplier?: string;
  required?: boolean;
  placeholder?: string;
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [busy, setBusy] = useState(false);
  const [data, setData] = useState<{ key: string; result: Suggestions } | null>(
    null,
  );
  const list = useRef<HTMLUListElement>(null);
  const key = JSON.stringify([field, year, value, buyer, supplier]);
  const result = data?.key === key ? data.result : null;
  const options = result?.options ?? [];

  useEffect(() => {
    setActive(-1);
    if (!open || value.trim().length < 3) {
      setBusy(false);
      return;
    }
    const controller = new AbortController();
    setBusy(true);
    const timer = window.setTimeout(
      async () => {
        const query = new URLSearchParams({
          field,
          year: String(year),
          q: value,
        });
        if (field === "search") {
          if (year === 2026) query.set("data_source", "snapshot");
          if (buyer.trim()) query.set("buyer", buyer.trim());
          if (supplier.trim()) query.set("supplier", supplier.trim());
        }
        try {
          const result = await api<Suggestions>(
            `/sources/sercop/suggestions?${query}`,
            { signal: controller.signal },
          );
          if (!controller.signal.aborted) setData({ key, result });
        } catch {
          if (!controller.signal.aborted)
            setData({
              key,
              result: {
                options: [],
                source: "",
                message:
                  "No se pudieron cargar las sugerencias. Puede escribir y buscar igualmente.",
              },
            });
        } finally {
          if (!controller.signal.aborted) setBusy(false);
        }
      },
      field === "search" && year !== 2026 ? 600 : 150,
    );
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [open, value, field, year, buyer, supplier, key]);

  useEffect(() => {
    if (active >= 0)
      list.current?.children[active]?.scrollIntoView({ block: "nearest" });
  }, [active]);

  function choose(option: Suggestion) {
    onChange(option.value);
    setOpen(false);
    setActive(-1);
  }

  return (
    <div
      className="field-label searchable-filter"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null))
          setOpen(false);
      }}
    >
      <label htmlFor={id}>{label}</label>
      <div className="searchable-filter-input">
        <input
          id={id}
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={open}
          aria-controls={open ? `${id}-options` : undefined}
          aria-activedescendant={
            open && active >= 0 && active < options.length
              ? `${id}-${active}`
              : undefined
          }
          autoComplete="off"
          minLength={3}
          maxLength={200}
          required={required}
          value={value}
          placeholder={placeholder}
          onFocus={() => setOpen(true)}
          onChange={(event) => {
            onChange(event.target.value);
            setOpen(true);
            setActive(-1);
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              setOpen(false);
              setActive(-1);
            }
            if (event.key === "ArrowDown" || event.key === "ArrowUp") {
              event.preventDefault();
              setOpen(true);
              setActive((index) =>
                options.length
                  ? index < 0
                    ? event.key === "ArrowDown"
                      ? 0
                      : options.length - 1
                    : (index +
                        (event.key === "ArrowDown" ? 1 : -1) +
                        options.length) %
                      options.length
                  : -1,
              );
            }
            if (
              event.key === "Enter" &&
              open &&
              active >= 0 &&
              active < options.length
            ) {
              event.preventDefault();
              choose(options[active]);
            }
          }}
        />
        <button
          type="button"
          className="icon-button"
          aria-label={`Mostrar sugerencias de ${label.toLowerCase()}`}
          title="Mostrar sugerencias"
          onClick={() => {
            setOpen(!open);
            setActive(-1);
          }}
        >
          <ChevronDown size={16} />
        </button>
      </div>
      {open && (
        <div className="searchable-filter-menu">
          <small>
            {field === "search"
              ? year === 2026
                ? "Descarga SERCOP 2026 · corte 13/11/2026"
                : `Procesos publicados en SERCOP · ${year}`
              : `Catálogo SERCOP 2026 · corte 13/11/2026`}
          </small>
          <ul
            ref={list}
            id={`${id}-options`}
            role="listbox"
            aria-label={label}
            aria-busy={busy}
          >
            {options.map((option, index) => (
              <li
                key={option.id}
                id={`${id}-${index}`}
                role="option"
                aria-selected={index === active}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => choose(option)}
              >
                <span>{option.label}</span>
                {option.detail && (
                  <small className="searchable-filter-detail">
                    {option.detail}
                  </small>
                )}
              </li>
            ))}
          </ul>
          <p role="status">
            {value.trim().length < 3
              ? "Escriba al menos tres caracteres para ver sugerencias."
              : busy
                ? "Buscando sugerencias…"
                : result?.message}
          </p>
        </div>
      )}
    </div>
  );
}
