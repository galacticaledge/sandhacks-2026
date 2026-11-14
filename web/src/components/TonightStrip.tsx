import { useEffect, useState } from "react";
import { get, type TonightItem } from "../api";
import { LevelBadge } from "./LevelBadge";
import { fmtPpb, fmtTime } from "../levels";
import type { Lang, Strings } from "../i18n";

type Resp = { items: (TonightItem & { kind: string })[] };
const ORDER = ["green", "yellow", "orange", "review"];

// "Orange tonight?" banner above the map, from /api/tonight (neighborhoods and schools only).
export function TonightStrip({ t, lang }: { t: Strings; lang: Lang }) {
  const [d, setD] = useState<Resp | null | false>(null);
  useEffect(() => { get<Resp>("/api/tonight").then(setD).catch(() => setD(false)); }, []);
  const places = d ? d.items.filter((i) => i.kind !== "monitor") : [];
  const likely = places.filter((i) => i.alert === "likely").length, possible = places.filter((i) => i.alert === "possible").length;
  const worst = [...places].sort((a, b) => ORDER.indexOf(b.level ?? "green") - ORDER.indexOf(a.level ?? "green") || (b.peak_p50 ?? 0) - (a.peak_p50 ?? 0))[0];
  const orange = likely + possible > 0;
  return (
    <div className={`strip${orange ? " strip-orange" : ""}`} role="region" aria-label={t.strip_q}>
      <strong className="strip-q">{t.strip_q}</strong>
      <div className="strip-body">
        {d === null ? null : !worst ? <span>{t.strip_na}</span> : (
          <>
            <span>
              {orange ? t.strip_orange.replace("{n}", String(likely + possible)).replace("{m}", String(places.length)).replace("{a}", String(likely)).replace("{b}", String(possible)) : t.strip_none}
              {" "}{t.strip_worst}: <LevelBadge level={worst.level} t={t} small /> {worst.name}, {fmtPpb(worst.peak_p50)} ppb
              {worst.peak_time && <> {t.strip_peak_at} {fmtTime(worst.peak_time, lang)}</>}.
            </span>
            {!orange && <span className="muted small"> {t.never_safe}</span>}
          </>
        )}
      </div>
      <div className="strip-links">
        <a className="btn primary" href="#/tonight">{t.strip_tonight}</a>
        <a href="#/replay">{t.strip_replay}</a>
      </div>
    </div>
  );
}
