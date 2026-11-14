import { LEVELS } from "../levels";
import type { Strings } from "../i18n";

export function Legend({ t }: { t: Strings }) {
  return (
    <div className="legend" aria-label={t.legend}>
      <div className="legend-title">{t.legend}</div>
      {LEVELS.map((l) => (
        <div key={l.key} className="legend-row">
          <span className="swatch" style={{ background: l.color, color: l.ink }} aria-hidden="true">{l.icon}</span>
          <span>{t[`level_${l.key}` as keyof Strings] as string}</span>
          <span className="muted">{t[`range_${l.key}` as keyof Strings] as string}</span>
        </div>
      ))}
    </div>
  );
}
