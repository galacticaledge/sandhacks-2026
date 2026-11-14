import { Fragment, useEffect, useMemo, useState } from "react";
import { get, type TonightItem } from "../api";
import { LevelBadge } from "../components/LevelBadge";
import { fmtPpb, fmtTime } from "../levels";
import type { Lang, Strings } from "../i18n";

type Resp = { run_id: string; run_kind: string; issued_at: string; items: (TonightItem & { kind: string })[]; disclaimer: string };
type Key = "name" | "peak_p50" | "peak_p90" | "peak_time";

export function TonightPage({ t, lang }: { t: Strings; lang: Lang }) {
  const [data, setData] = useState<Resp | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sort, setSort] = useState<{ k: Key; dir: 1 | -1 }>({ k: "peak_p50", dir: -1 });
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => { get<Resp>(`/api/tonight?lang=${lang}`).then(setData).catch((e) => setErr(String(e))); }, [lang]);

  const rows = useMemo(() => {
    const items = data?.items ?? [];
    return [...items].sort((a, b) => {
      const av = a[sort.k] as string | number | undefined, bv = b[sort.k] as string | number | undefined;
      return (av ?? 0) > (bv ?? 0) ? sort.dir : (av ?? 0) < (bv ?? 0) ? -sort.dir : 0;
    });
  }, [data, sort]);

  const th = (k: Key, label: string) => (
    <th aria-sort={sort.k === k ? (sort.dir > 0 ? "ascending" : "descending") : "none"}>
      <button className="th-btn" onClick={() => setSort({ k, dir: sort.k === k ? (-sort.dir as 1 | -1) : -1 })}>
        {label} {sort.k === k ? (sort.dir > 0 ? "↑" : "↓") : ""}
      </button>
    </th>
  );
  const kindLabel = (k: string) => (k === "school" ? t.school : k === "monitor" ? t.monitor : t.neighborhood);
  const alertLabel = (k?: string) => (k === "likely" ? t.alert_likely : k === "possible" ? t.alert_possible : t.alert_none);

  return (
    <div className="page">
      <h1>{t.tonight_title}</h1>
      <p className="lede">{t.tonight_sub}</p>
      {data && <p className="muted small">{t.forecast_issued}: {new Date(data.issued_at).toLocaleString(lang === "es" ? "es-MX" : "en-US", { timeZone: "America/Los_Angeles", dateStyle: "medium", timeStyle: "short" })} · {t.api_labels[data.run_kind] ?? data.run_kind}</p>}
      {err && <p className="warn">{err}</p>}
      <div className="table-wrap">
        <table className="tonight">
          <thead>
            <tr>
              {th("name", t.place)}
              <th>{t.type}</th>
              <th>{t.level}</th>
              {th("peak_p50", t.peak)}
              {th("peak_p90", t.peak_high)}
              {th("peak_time", t.peak_hour)}
              <th>{t.confidence}</th>
              <th>{t.alert}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const alertKind = (r as unknown as { alert?: string }).alert;
              const k = (r as unknown as { kind: string }).kind;
              return (
                <Fragment key={r.id}>
                  <tr className="clickable" onClick={() => setOpen(open === r.id ? null : r.id)}>
                    <td><button className="row-btn" aria-expanded={open === r.id} onClick={(e) => { e.stopPropagation(); setOpen(open === r.id ? null : r.id); }}>{r.name}</button></td>
                    <td className="muted">{kindLabel(k)}</td>
                    <td><span title={t.median}><span className="muted small">P50</span> <LevelBadge level={r.level} t={t} small /></span> <span title={t.high_est}><span className="muted small">P90</span> <LevelBadge level={r.level_p90} t={t} small /></span></td>
                    <td>{fmtPpb(r.peak_p50)} ppb</td>
                    <td>{fmtPpb(r.peak_p90)} ppb</td>
                    <td>{r.peak_time ? fmtTime(r.peak_time, lang, true) : "–"}</td>
                    <td>{r.confidence ? t[`conf_${r.confidence}` as keyof Strings] as string : "–"}</td>
                    <td>{alertLabel(alertKind)}</td>
                  </tr>
                  {open === r.id && (
                    <tr className="guidance-row">
                      <td colSpan={8}>
                        <strong>{t.sdapcd_says}:</strong> {r.guidance.expect}
                        <ul>{r.guidance.actions.map((a) => <li key={a}>{a}</li>)}</ul>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="muted small">{t.never_safe}</p>
    </div>
  );
}
