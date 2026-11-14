import type { Level } from "../api";
import { levelStyle } from "../levels";
import type { Strings } from "../i18n";

export function LevelBadge({ level, t, small }: { level: Level | null | undefined; t: Strings; small?: boolean }) {
  const s = levelStyle(level);
  if (!s) return <span className="badge badge-none">–</span>;
  const label = t[`level_${s.key}` as keyof Strings] as string;
  return (
    <span className={`badge${small ? " badge-sm" : ""}`} style={{ background: s.color, color: s.ink }}>
      <span aria-hidden="true">{s.icon}</span> {label}
    </span>
  );
}
