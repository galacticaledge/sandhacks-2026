import { useEffect, useState } from "react";
import { get } from "../api";
import { Reports } from "../components/Reports";
import { fmtDate } from "../levels";
import type { Lang, Strings } from "../i18n";

type Ev = {
  id: string; event_type: string; location_text?: string; published_at: string | null; starts_at: string | null; ends_at: string | null;
  expected_flow_mgd: number | null; flow_delta_mgd: number | null; peak_flow_mgd: number | null; quote: string; source_url: string; used_in_model: boolean;
};
const PAGE = 15;

export function EvidencePage({ t, lang }: { t: Strings; lang: Lang }) {
  const [ev, setEv] = useState<Ev[] | null>(null);
  const [shown, setShown] = useState(PAGE);
  useEffect(() => { get<Ev[]>("/api/events").then(setEv).catch(() => setEv([])); }, []);
  const num = (label: string, v: number | null) => (v == null ? null : <span key={label}><span className="muted">{label}:</span> {v} MGD</span>);
  return (
    <div className="page narrow">
      <h1>{t.ev_title}</h1>
      <p className="lede">{t.ev_sub}</p>

      <h2>{t.ev_flow_h}</h2>
      <p className="muted">{t.ev_flow_note}</p>
      {ev && <p className="muted small">{t.ev_count.replace("{n}", String(ev.length))}</p>}
      {ev && !ev.length && <p className="muted">{t.ev_none}</p>}
      <ul className="ev-list">
        {(ev ?? []).slice(0, shown).map((e) => (
          <li key={e.id} className="card">
            <div className="ev-head">
              <strong>{t.ev_types[e.event_type] ?? e.event_type}</strong>
              <span className="muted small">
                {fmtDate(e.starts_at ?? e.published_at, lang)}{e.ends_at && ` ${t.ev_until} ${fmtDate(e.ends_at, lang)}`}
              </span>
              <span className={`chip ${e.used_in_model ? "chip-used" : "chip-shown"}`}>{e.used_in_model ? t.ev_used : t.ev_shown}</span>
            </div>
            <blockquote>{e.quote}</blockquote>
            {(e.expected_flow_mgd != null || e.flow_delta_mgd != null || e.peak_flow_mgd != null) && (
              <div className="ev-nums">{num(t.ev_expected, e.expected_flow_mgd)}{num(t.ev_delta, e.flow_delta_mgd)}{num(t.ev_peak, e.peak_flow_mgd)}</div>
            )}
            {e.source_url && <a className="small" href={e.source_url} target="_blank" rel="noreferrer">{t.ev_source} ↗</a>}
          </li>
        ))}
      </ul>
      {ev && shown < ev.length && <button className="btn" onClick={() => setShown(shown + PAGE)}>{t.ev_more}</button>}

      <h2>{t.reports_title}</h2>
      <p className="muted small">{t.reports_sub} {t.ev_recent_sub}</p>
      <Reports url="/api/reports/recent?days=7" t={t} lang={lang} />
    </div>
  );
}
