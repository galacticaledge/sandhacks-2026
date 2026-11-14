import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { get } from "../api";
import type { Lang, Strings } from "../i18n";

type Sum = { n_nights: number; n_orange_nights?: number; hit_rate?: number | null; false_alarm_ratio?: number | null; category_accuracy?: number; mae_log?: number };
type Skill = {
  computed_at?: string; nights: string[]; label?: string;
  history?: { start: string | null; end: string | null; hours: number };
  summary: Record<string, Record<string, Sum>>;
  leave_one_monitor_out?: Record<string, { mae_log: number; r_log: number | null; n_hours: number }>;
  spatial?: { n_complaints: number; mean_percentile?: number; share_in_top20pct_area?: number; chance_share?: number };
};
const pct = (v: number | null | undefined) => (v == null ? "–" : `${Math.round(v * 100)}%`);

export function AccuracyPage({ t }: { t: Strings; lang: Lang }) {
  const [s, setS] = useState<Skill | null>(null);
  useEffect(() => { get<Skill>("/api/skill").then(setS); }, []);
  const methods: [string, string][] = [["model", t.model], ["persistence", t.persistence], ["climatology", t.climatology]];
  const all = (m: string) => s?.summary?.[m]?.all;
  const chart = methods.map(([k, label]) => ({ label, mae: all(k)?.mae_log ?? null }));
  const hist = s?.history;
  const days = hist?.hours ? (hist.hours / 3 / 24).toFixed(1) : "0";

  return (
    <div className="page">
      <h1>{t.acc_title}</h1>
      <p className="lede">{t.acc_sub}</p>
      <div className="card notice">
        <h3>{t.data_status}</h3>
        <p>
          {hist?.start ? <>Monitor history: {hist.start.slice(0, 10)} → {hist.end?.slice(0, 10)} (~{days} days per monitor, {hist.hours} readings). </> : null}
          {s?.nights?.length ?? 0} nights replayed. {s?.label}
        </p>
        <p className="small muted">
          Historical SDAPCD data (months of hourly readings, including real spikes) is pending; see docs/data_status.md. Until it lands,
          these scores cover only the days we have captured from the live feed, which have no orange nights, so hit rate and false alarms can't be measured yet. We report this as it is.
        </p>
      </div>
      <div className="grid3">
        {methods.map(([k, label]) => {
          const a = all(k);
          return (
            <div className={`card metric${k === "model" ? " primary" : ""}`} key={k}>
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
            <thead><tr><th>Monitor</th><th>MAE (log)</th><th>r (log)</th><th>hours</th></tr></thead>
            <tbody>
              {Object.entries(s?.leave_one_monitor_out ?? {}).map(([k, v]) => (
                <tr key={k}><td>{k}</td><td>{v.mae_log.toFixed(2)}</td><td>{v.r_log == null ? "–" : v.r_log.toFixed(2)}</td><td>{v.n_hours}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card">
          <h3>{t.spatial}</h3>
          {s?.spatial?.n_complaints ? (
            <p>{s.spatial.n_complaints} odor complaints during forecast windows. {pct(s.spatial.share_in_top20pct_area)} fell in the top-20% forecast area (chance: {pct(s.spatial.chance_share)}). Mean percentile: {pct(s.spatial.mean_percentile)}.</p>
          ) : <p className="muted">{t.na}</p>}
        </div>
      </div>
      {s?.computed_at && <p className="muted small">Scored {new Date(s.computed_at).toLocaleString()}</p>}
    </div>
  );
}
