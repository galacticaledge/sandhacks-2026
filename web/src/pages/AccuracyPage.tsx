import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { get, type Receptor } from "../api";
import type { Lang, Strings } from "../i18n";

type Sum = { n_nights: number; n_orange_nights?: number; hit_rate?: number | null; false_alarm_ratio?: number | null; category_accuracy?: number; mae_log?: number };
type Counts = { hits: number; misses: number; false_alarms: number; correct_quiet: number; n: number; hit_rate: number | null; false_alarm_ratio: number | null };
// periods -> subset (all_nights | after_quiet_night) -> site | "all" -> rule (model_likely, model_possible, persistence, climatology)
type Binary = { threshold_ppb?: number; periods?: Record<string, Record<string, Record<string, Record<string, Counts>>>> };
type Rank = { n: number; alarms_matched_to_persistence?: number; model_hit_rate_at_persistence_alarm_count?: number };
type Skill = {
  computed_at?: string; nights: string[]; label?: string; held_out_from?: string; n_skipped_other_calibration?: number;
  history?: { start: string | null; end: string | null; hours: number };
  summary: Record<string, Record<string, Sum>>;
  summary_by_period?: Record<string, Record<string, Record<string, Sum>>>;
  binary?: Binary;
  coverage?: Record<string, { night_peak_under_p90: number | null; n_monitor_nights: number }>;
  ranking?: Record<string, Record<string, Rank>>;
  leave_one_monitor_out?: Record<string, { mae_log: number; r_log: number | null; n_hours: number }>;
  spatial?: { n_complaints: number; n_locations?: number; min_locations?: number; mean_percentile?: number; share_in_top20pct_area?: number; chance_share?: number };
};
const pct = (v: number | null | undefined) => (v == null ? "–" : `${Math.round(v * 100)}%`);

// Score on the held-out nights when the file has them: nights the model was fitted on flatter it.
function periodOf(s: Skill | null): "held_out" | "all" {
  return (s?.binary?.periods?.held_out?.all_nights?.all?.model_likely?.n ?? 0) > 0 ? "held_out" : "all";
}

// Exact yes/no counts for one rule. Older skill files have only rates, so counts are rebuilt where arithmetic allows.
function countsFor(s: Skill | null, rule: string, period: string, subset = "all_nights"): Counts | null {
  const c = s?.binary?.periods?.[period]?.[subset]?.all?.[rule];
  if (c) return c;
  if (subset !== "all_nights") return null;
  const a = s?.summary?.[rule === "model_likely" ? "model" : rule]?.all;
  if (!a?.n_nights) return null;
  const nOrange = a.n_orange_nights ?? 0, hits = a.hit_rate != null ? Math.round(a.hit_rate * nOrange) : 0;
  const far = a.false_alarm_ratio ?? null;
  const fa = far != null && far < 1 ? Math.round((far * hits) / (1 - far)) : 0;
  return { hits, misses: nOrange - hits, false_alarms: fa, correct_quiet: a.n_nights - nOrange - fa, n: a.n_nights, hit_rate: a.hit_rate ?? null, false_alarm_ratio: far };
}

export function AccuracyPage({ t, lang }: { t: Strings; lang: Lang }) {
  const [s, setS] = useState<Skill | null>(null);
  const [names, setNames] = useState<Record<string, string>>({});
  useEffect(() => { get<Skill>("/api/skill").then(setS); }, []);
  useEffect(() => { get<Receptor[]>("/api/receptors").then((r) => setNames(Object.fromEntries(r.map((x) => [x.id, x.name])))).catch(() => {}); }, []);
  const period = periodOf(s);
  const sums = s?.summary_by_period?.[period] ?? s?.summary;
  const methods: [string, string][] = [["model", t.model], ["persistence", t.persistence], ["climatology", t.climatology]];
  const all = (m: string) => sums?.[m]?.all;
  const chart = methods.map(([k, label]) => ({ label, mae: all(k)?.mae_log ?? null }));
  const hist = s?.history;
  const days = hist?.hours ? (hist.hours / 3 / 24).toFixed(1) : "0";
  const nNights = s?.nights?.length ?? 0;
  const likely = countsFor(s, "model_likely", period);
  const nScored = likely?.n ?? 0, nOrange = likely ? likely.hits + likely.misses : 0;
  const small = !!s && (nScored < 30 || nOrange === 0);
  const quiet = (r: string) => countsFor(s, r, period, "after_quiet_night");
  const qLikely = quiet("model_likely"), qPossible = quiet("model_possible");
  const nQuiet = qLikely ? qLikely.hits + qLikely.misses : 0;
  const rank = s?.ranking?.[period]?.all;
  const cover = s?.coverage?.[period]?.night_peak_under_p90;
  const tuning = period === "held_out" ? countsFor(s, "model_likely", "tuning") : null;
  const sp = s?.spatial;
  const caught = (c: Counts) => t.acc_caught.replace("{h}", String(c.hits)).replace("{n}", String(c.hits + c.misses)).replace("{p}", pct(c.hit_rate));
  const falseN = (c: Counts) => t.acc_false_n.replace("{x}", String(c.false_alarms)).replace("{y}", String(c.hits + c.false_alarms)).replace("{p}", pct(c.false_alarm_ratio));

  const rows: [string, string][] = [["model_likely", t.acc_m_model], ["model_possible", t.acc_m_possible], ["persistence", t.acc_m_persist], ["climatology", t.acc_m_clim]];
  return (
    <div className="page">
      <h1>{t.acc_q}</h1>
      <p className="lede">{t.acc_q_sub}</p>
      <p><span className="pill warn-pill">{t.replay_label}</span></p>
      {s && <p className="muted">{period === "held_out" ? t.acc_period_held.replace("{n}", String(nScored)).replace("{d}", s.held_out_from ?? "") : t.acc_period_all}</p>}
      {small && <p className="card notice sample-line"><strong>{t.acc_small.replace("{n}", String(nScored)).replace("{m}", String(nOrange))}</strong></p>}
      <div className="table-wrap">
        <table className="acc-table">
          <thead><tr><th>{t.acc_col_method}</th><th>{t.acc_col_caught}</th><th>{t.acc_col_false}</th><th>{t.acc_col_n}</th></tr></thead>
          <tbody>
            {rows.map(([k, label]) => {
              const c = countsFor(s, k, period);
              if (s && !c) return null;   // e.g. no P90 rule in an older skill file
              return (
                <tr key={k}>
                  <td>{label}</td>
                  <td className="acc-big">{!c ? "–" : !(c.hits + c.misses) ? <span className="muted">{t.acc_no_orange}</span> : caught(c)}</td>
                  <td className="acc-big">{!c || !c.n ? "–" : !(c.hits + c.false_alarms) ? <span className="muted">{t.acc_no_alerts}</span> : falseN(c)}</td>
                  <td className="acc-big">{c?.n || t.na}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="muted small">{t.acc_foot}</p>
      {nQuiet > 0 && qLikely && qPossible && <p>{t.acc_quiet.replace("{n}", String(nQuiet)).replace("{a}", caught(qLikely)).replace("{b}", caught(qPossible))}</p>}
      {rank?.model_hit_rate_at_persistence_alarm_count != null && (
        <p>{t.acc_matched.replace("{k}", String(rank.alarms_matched_to_persistence)).replace("{p}", pct(rank.model_hit_rate_at_persistence_alarm_count)).replace("{q}", pct(countsFor(s, "persistence", period)?.hit_rate))}</p>
      )}
      {cover != null && <p>{t.acc_cover.replace("{p}", pct(cover))}</p>}
      <details className="more">
        <summary>{t.acc_more}</summary>
      <p className="lede">{t.acc_sub}</p>
      <div className="card notice">
        <h3>{t.data_status}</h3>
        <p>
          {hist?.start ? t.acc_hist.replace("{a}", hist.start.slice(0, 10)).replace("{b}", hist.end?.slice(0, 10) ?? "").replace("{d}", days).replace("{h}", String(hist.hours)) + " " : null}
          {t.acc_nights.replace("{n}", String(nNights))} {s?.label ? (t.api_labels[s.label] ?? s.label) : null}
          {s?.n_skipped_other_calibration ? " " + t.acc_skipped.replace("{n}", String(s.n_skipped_other_calibration)) : null}
        </p>
        {tuning && (tuning.hits + tuning.misses) > 0 && <p className="muted small">{t.acc_tuning.replace("{h}", caught(tuning)).replace("{f}", falseN(tuning))}</p>}
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
          {sp?.n_complaints ? (
            <p>{t.acc_spatial.replace("{n}", String(sp.n_complaints)).replace("{l}", String(sp.n_locations ?? "–")).replace("{a}", pct(sp.share_in_top20pct_area)).replace("{b}", pct(sp.chance_share)).replace("{c}", pct(sp.mean_percentile))}</p>
          ) : sp?.min_locations != null ? (
            <p className="muted">{t.acc_spatial_few.replace("{l}", String(sp.n_locations ?? 0)).replace("{m}", String(sp.min_locations))}</p>
          ) : <p className="muted">{t.na}</p>}
        </div>
      </div>
      {s?.computed_at && <p className="muted small">{t.scored} {new Date(s.computed_at).toLocaleString(lang === "es" ? "es-MX" : "en-US")}</p>}
      </details>
    </div>
  );
}
