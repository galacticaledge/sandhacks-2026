import { useEffect, useState } from "react";
import { get, type TonightItem } from "../api";
import { Icon } from "./Icons";
import { LevelBadge } from "./LevelBadge";
import { fmtPpb, fmtTime } from "../levels";
import type { Lang, Strings } from "../i18n";

type Resp = { items: (TonightItem & { kind: string })[] };
const ORDER = ["green", "yellow", "orange", "review"];

// "Orange tonight?" summary above the Live Map, from /api/tonight (neighborhoods and schools only).
// Three sections: the answer, the highest forecast place, and where to go next.
export function TonightStrip({ t, lang }: { t: Strings; lang: Lang }) {
  const [d, setD] = useState<Resp | null | false>(null);
  useEffect(() => { get<Resp>("/api/tonight").then(setD).catch(() => setD(false)); }, []);
  const places = d ? d.items.filter((i) => i.kind !== "monitor") : [];
  const likely = places.filter((i) => i.alert === "likely").length, possible = places.filter((i) => i.alert === "possible").length;
  const worst = [...places].sort((a, b) => ORDER.indexOf(b.level ?? "green") - ORDER.indexOf(a.level ?? "green") || (b.peak_p50 ?? 0) - (a.peak_p50 ?? 0))[0];
  const orange = likely + possible > 0;
  return (
    <section className={`summary${orange ? " summary-orange" : ""}`} aria-label={t.strip_q}>
      <div className="sum-sec sum-answer">
        <span className="sum-k">{t.strip_q}</span>
        {d === null ? <strong className="sum-big">…</strong> : !worst ? <p>{t.strip_na}</p> : (
          <>
            <strong className="sum-big"><span className={`sum-dot${orange ? " on" : ""}`} aria-hidden="true" />{orange ? t.strip_yes : t.strip_no}</strong>
            <p>{orange
              ? t.strip_orange.replace("{n}", String(likely + possible)).replace("{m}", String(places.length)).replace("{a}", String(likely)).replace("{b}", String(possible))
              : t.strip_none}</p>
          </>
        )}
      </div>
      <div className="sum-sec sum-worst">
        <span className="sum-k">{t.strip_worst}</span>
        {worst && (
          <>
            <div className="sum-place"><LevelBadge level={worst.level} t={t} small /><strong>{worst.name}</strong></div>
            <p>
              <strong className="sum-num">{fmtPpb(worst.peak_p50)}</strong> ppb
              {worst.peak_time && <> · {t.strip_peak_at} {fmtTime(worst.peak_time, lang)}</>}
              <span className="sum-p90"> · {t.peak_high} {fmtPpb(worst.peak_p90)} ppb</span>
            </p>
          </>
        )}
      </div>
      <div className="sum-sec sum-actions">
        <a className="btn primary" href="#/tonight">{t.strip_tonight} <Icon name="arrow" size={14} /></a>
        <a className="sum-link" href="#/replay">{t.strip_replay} ↗</a>
        {!orange && <p className="sum-note">{t.never_safe}</p>}
      </div>
    </section>
  );
}
