import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Icon } from "./Icons";

export type Opt = { value: string; label: string };
export type OptGroup = { label?: string; options: Opt[] };

// Dropdown that always opens directly below its button (a native <select> with a long list
// can pop up over the page). Listbox pattern: arrows, Home/End, Enter/Space, Escape, type-ahead.
export function Select({ value, onChange, groups, ariaLabel, id }: {
  value: string; onChange: (v: string) => void; groups: OptGroup[]; ariaLabel: string; id?: string;
}) {
  const [open, setOpen] = useState(false);
  const flat = useMemo(() => groups.flatMap((g) => g.options), [groups]);
  const [active, setActive] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const typed = useRef({ s: "", t: 0 });
  const uid = useId();
  const listId = `${id ?? uid}-list`;
  const current = flat.find((o) => o.value === value);

  useEffect(() => {
    if (!open) return;
    setActive(Math.max(0, flat.findIndex((o) => o.value === value)));
    const close = (e: MouseEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open, flat, value]);

  // if the list would run past the bottom of the screen, scroll the page just enough to show it
  useEffect(() => { if (open) list.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }, [open]);

  useEffect(() => {
    if (open) list.current?.querySelector<HTMLElement>(`[data-i="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [open, active]);

  const pick = (i: number) => { const o = flat[i]; if (o) onChange(o.value); setOpen(false); btn.current?.focus(); };

  const onKey = (e: React.KeyboardEvent) => {
    if (!open) {
      if (["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) { e.preventDefault(); setOpen(true); }
      return;
    }
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(flat.length - 1, a + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
    else if (e.key === "Home") { e.preventDefault(); setActive(0); }
    else if (e.key === "End") { e.preventDefault(); setActive(flat.length - 1); }
    else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(active); }
    else if (e.key === "Escape" || e.key === "Tab") { setOpen(false); }
    else if (e.key.length === 1) {
      const now = Date.now();
      typed.current = { s: (now - typed.current.t < 700 ? typed.current.s : "") + e.key.toLowerCase(), t: now };
      const i = flat.findIndex((o) => o.label.toLowerCase().startsWith(typed.current.s));
      if (i >= 0) setActive(i);
    }
  };

  let i = -1;
  return (
    <div className={`dd${open ? " open" : ""}`} ref={root}>
      <button ref={btn} type="button" id={id} className="dd-btn" aria-haspopup="listbox" aria-expanded={open} aria-controls={listId}
        aria-label={ariaLabel} onClick={() => setOpen(!open)} onKeyDown={onKey}
        aria-activedescendant={open ? `${listId}-${active}` : undefined}>
        <span>{current?.label ?? "–"}</span>
        <Icon name="chevron" size={16} />
      </button>
      {open && (
        <ul className="dd-list" role="listbox" id={listId} ref={list} aria-label={ariaLabel} tabIndex={-1}>
          {groups.map((g, gi) => (
            <li key={gi} role="presentation">
              {g.label && <div className="dd-group" role="presentation">{g.label}</div>}
              <ul role="group" aria-label={g.label}>
                {g.options.map((o) => {
                  i++;
                  const idx = i;
                  return (
                    <li key={o.value} id={`${listId}-${idx}`} data-i={idx} role="option" aria-selected={o.value === value}
                      className={`dd-opt${idx === active ? " active" : ""}${o.value === value ? " selected" : ""}`}
                      onMouseEnter={() => setActive(idx)} onMouseDown={(e) => { e.preventDefault(); pick(idx); }}>
                      {o.label}
                    </li>
                  );
                })}
              </ul>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
