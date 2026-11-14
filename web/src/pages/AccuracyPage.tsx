import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { get, type Receptor } from "../api";
import type { Lang, Strings } from "../i18n";

type Sum = { n_nights: number; n_orange_nights?: number; hit_rate?: number | null; false_alarm_ratio?: number | null; category_accuracy?: number; mae_log?: number };
type Skill = {
  computed_at?: string; nights: string[]; label?: string;
  history?: { start: string | null; end: string | null; hours: number };
  summary: Record<string, Record<string, Sum>>;
  leave_one_monitor_out?: Record<string, { mae_log: number; r_log: number | null; n_hours: number }>;
  binary?: Record<string, Record<string, unknown>>;  // optional, shape not final: read defensively (see binaryRow)
  spatial?: { n_complaints: number; mean_percentile?: number; share_in_top20pct_area?: number; chance_share?: number };
};
const pct = (v: number | null | undefined) => (v == null ? "–" : `${Math.round(v * 100)}%`);

// "Orange tonight or not?" numbers for one method. Prefers the top-level `binary` block when present, else summary.<m>.all.
const pick = (o: Record<string, unknown> | undefined, ...keys: string[]) => {
  for (const k of keys) { const v = o?.[k]; if (typeof v === "number" && Number.isFinite(v)) return v; }
  return null;
};
function binaryRow(s: Skill | null, key: string) {
  const b = s?.binary?.[key] ?? (key === "model" ? s?.binary?.smellcast : undefined);
  const raw = ((b?.all as Record<string, unknown> | undefined) ?? b ?? (s?.summary?.[key]?.all as unknown as Record<string, unknown> | undefined));
  const n = pick(raw, "n_nights", "n") ?? 0, nOrange = pick(raw, "n_orange_nights", "n_orange", "n_events") ?? 0;
  const hitRate = pick(raw, "hit_rate"), far = pick(raw, "false_alarm_ratio");
  const hits = pick(raw, "hits", "tp", "caught") ?? (hitRate != null && nOrange ? Math.round(hitRate * nOrange) : null);
  let falseN = pick(raw, "false_alarms", "fp"), alerts = pick(raw, "n_alerts", "n_alarms", "alerts");
  // counts that the file does not give but arithmetic does: FAR = FP / (TP + FP)
  if (alerts == null && falseN != null && hits != null) alerts = hits + falseN;
  if (falseN == null && alerts != null && far != null) falseN = Math.round(alerts * far);
  if (alerts == null && far != null && far < 1 && hits != null) {
    const fp = (far * hits) / (1 - far);
    if (Math.abs(fp - Math.round(fp)) < 0.02) { falseN = Math.round(fp); alerts = hits + falseN; }
  }
  return { n, nOrange, hitRate, far, hits, falseN, alerts };
}

export function AccuracyPage({ t, lang }: { t: Strings; lang: Lang }) {
  const [s, setS] = useState<Skill | null>(null);
  const [names, setNames] = useState<Record<string, string>>({});
  useEffect(() => { get<Skill>("/api/skill").then(setS); }, []);
  useEffect(() => { get<Receptor[]>("/api/receptors").then((r) => setNames(Object.fromEntries(r.map((x) => [x.id, x.name])))).catch(() => {}); }, []);
  const methods: [string, string][] = [["model", t.model], ["persistence", t.persistence], ["climatology", t.climatology]];
  const all = (m: string) => s?.summary?.[m]?.all;
  const chart = methods.map(([k, label]) => ({ label, mae: all(k)?.mae_log ?? null }));
  const hist = s?.history;
  const days = hist?.hours ? (hist.hours / 3 / 24).toFixed(1) : "0";
  const nNights = s?.nights?.length ?? 0, nOrange = all("model")?.n_orange_nights ?? 0;
  const small = !!s && (nNights < 30 || nOrange === 0);

  const rows: [string, string][] = [["model", t.acc_m_model], ["persistence", t.acc_m_persist], ["climatology", t.acc_m_clim]];
  return (
    <div className="page">
      <h1>{t.acc_q}</h1>
      <p className="lede">{t.acc_q_sub}</p>
      <p><span className="pill warn-pill">{t.replay_label}</span></p>
      {small && <p className="card notice sample-line"><strong>{t.acc_small.replace("{n}", String(nNights)).replace("{m}", String(nOrange))}</strong></p>}
      <div className="table-wrap">
        <table className="acc-table">
          <thead><tr><th>{t.acc_col_method}</th><th>{t.acc_col_caught}</th><th>{t.acc_col_false}</th><th>{t.acc_col_n}</th></tr></thead>
          <tbody>
            {rows.map(([k, label]) => {
              const r = binaryRow(s, k);
              return (
                <tr key={k}>
                  <td>{label}</td>
                  <td className="acc-big">{!s ? "–" : !r.nOrange ? <span className="muted">{t.acc_no_orange}</span> : r.hits != null ? t.acc_caught.replace("{h}", String(r.hits)).replace("{n}", String(r.nOrange)).replace("{p}", pct(r.hitRate)) : pct(r.hitRate)}</td>
                  <td className="acc-big">{!s || !r.n ? "–" : r.far == null ? <span className="muted">{t.acc_no_alerts}</span> : r.falseN != null && r.alerts ? t.acc_false_n.replace("{x}", String(r.falseN)).replace("{y}", String(r.alerts)).replace("{p}", pct(r.far)) : t.acc_false_p.replace("{p}", pct(r.far))}</td>
                  <td className="acc-big">{r.n || t.na}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="muted small">{t.acc_foot}</p>
      <details className="more">
        <summary>{t.acc_more}</summary>
      <p className="lede">{t.acc_sub}</p>
      <div className="card notice">
        <h3>{t.data_status}</h3>
        <p>
          {hist?.start ? t.acc_hist.replace("{a}", hist.start.slice(0, 10)).replace("{b}", hist.end?.slice(0, 10) ?? "").replace("{d}", days).replace("{h}", String(hist.hours)) + " " : null}
          {t.acc_nights.replace("{n}", String(nNights))} {s?.label ? (t.api_labels[s.label] ?? s.label) : null}
        </p>
      </div>
      <div className="grid3">
        {methods.map(([k, label]) => {
          const a = all(k);
          return (
            <div className="card metric" key={k}>
              <h3>{label}</h3>
              <dl>
                <dt>{t.hit_rate}</dt><dd>{a?.n_orange_nights ? pct(a.hit_rate) : t.na}</dd>
                <dt>{t.far}</dt><dd>{a?.false_alarm_ratio != null ? pct(a.false_alarm_ratio) : t.na}</dd>
                <dt>{t.cat_acc}</dt><dd>{a?.n_nights ? pct(a.category_accuracy) : t.na}</dd>
                <dt>{t.mae_log} <span className="muted small">({t.lower_better})</span></dt><dd>{a?.mae_log != null ? a.mae_log.toFixed(2) : t.na}</dd>
              </dl>
              <p className="muted small">{a?.n_nights ?? 0} {t.monitor_nights} · {a?.n_orange_nights ?? 0} {t.orange_nights}</p>
            </div>
          );
        })}
      </div>
      <div className="card">
        <h3>{t.mae_log} <span className="muted small">({t.lower_better})</span></h3>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={chart} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 12, fill: "var(--muted)" }} tickLine={false} />
            <YAxis tick={{ fontSize: 11, fill: "var(--muted)" }} tickLine={false} axisLine={false} />
            <Tooltip contentStyle={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8 }} />
            <Bar dataKey="mae" fill="var(--accent)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="grid2">
        <div className="card">
          <h3>{t.lomo}</h3>
          <p className="muted small">{t.lomo_sub}</p>
          <table className="simple">
            <thead><tr><th>{t.monitor}</th><th>MAE (log)</th><th>r (log)</th><th>{t.hours}</th></tr></thead>
            <tbody>
              {Object.entries(s?.leave_one_monitor_out ?? {}).map(([k, v]) => (
                <tr key={k}><td>{names[k] ?? k}</td><td>{v.mae_log.toFixed(2)}</td><td>{v.r_log == null ? "–" : v.r_log.toFixed(2)}</td><td>{v.n_hours}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card">
          <h3>{t.spatial}</h3>
          {s?.spatial?.n_complaints ? (
            <p>{t.acc_spatial.replace("{n}", String(s.spatial.n_complaints)).replace("{a}", pct(s.spatial.share_in_top20pct_area)).replace("{b}", pct(s.spatial.chance_share)).replace("{c}", pct(s.spatial.mean_percentile))}</p>
          ) : <p className="muted">{t.na}</p>}
        </div>
      </div>
      {s?.computed_at && <p className="muted small">{t.scored} {new Date(s.computed_at).toLocaleString(lang === "es" ? "es-MX" : "en-US")}</p>}
      </details>
    </div>
  );
}
