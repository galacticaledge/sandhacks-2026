import { Icon } from "./Icons";

// Shared header for the Live Map / Replay side cards: icon tile, title, optional quiet meta text.
export function PanelHead({ icon, title, meta }: { icon: string; title: string; meta?: string }) {
  return (
    <header className="panel-head">
      <span className="panel-icon"><Icon name={icon} size={15} /></span>
      <h3>{title}</h3>
      {meta && <span className="panel-meta">{meta}</span>}
    </header>
  );
}
