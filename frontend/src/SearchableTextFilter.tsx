import { useId, useState } from "react";
import { ChevronDown } from "lucide-react";

/** Free-text API filter, not an entity catalog or a filter on downloaded rows. */
export function SearchableTextFilter({
  label,
  value,
  onChange,
  recent,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  recent: string[];
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const options = recent.filter((item) =>
    item.toLocaleLowerCase("es").includes(value.trim().toLocaleLowerCase("es")),
  );
  function choose(option: string) {
    onChange(option);
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
          aria-controls={`${id}-options`}
          aria-activedescendant={
            open && active >= 0 ? `${id}-${active}` : undefined
          }
          autoComplete="off"
          minLength={3}
          maxLength={200}
          value={value}
          placeholder="Escriba para buscar en SERCOP"
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
                  ? Math.max(
                      0,
                      Math.min(
                        options.length - 1,
                        index + (event.key === "ArrowDown" ? 1 : -1),
                      ),
                    )
                  : -1,
              );
            }
            if (event.key === "Enter" && open && active >= 0) {
              event.preventDefault();
              choose(options[active]);
            }
          }}
        />
        <button
          type="button"
          className="icon-button"
          aria-label={`Mostrar búsquedas recientes de ${label.toLowerCase()}`}
          title="Mostrar búsquedas recientes"
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
          <small>Búsquedas recientes de esta sesión</small>
          <ul id={`${id}-options`} role="listbox" aria-label={label}>
            {options.map((option, index) => (
              <li
                key={option}
                id={`${id}-${index}`}
                role="option"
                aria-selected={index === active}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => choose(option)}
              >
                {option}
              </li>
            ))}
          </ul>
          {!options.length && (
            <p>Escriba un nombre o parte de él y pulse Buscar proceso.</p>
          )}
        </div>
      )}
    </div>
  );
}
