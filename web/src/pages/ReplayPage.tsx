import { useEffect, useMemo, useState } from "react";
import { get, type Meta, type Receptor, type Series } from "../api";
import { ForecastMap } from "../components/ForecastMap";
import { InputsCard } from "../components/InputsCard";
import { PointChart } from "../components/PointChart";
import { Reports } from "../components/Reports";
import { Icon } from "../components/Icons";
import { Select } from "../components/Select";
import { ZoneLegend } from "../components/ZoneLegend";
import { fmtClock, fmtPpb, fmtTime } from "../levels";
import type { Lang, Strings } from "../i18n";

type Night = { night: string; peak_ppb: number | null; has_grid: boolean; featured: boolean; receptor_id: string | null };
type Replay = {
  night: string; run_id: string; issued_at: string; valid_times: string[]; label: string; has_grid: boolean;
  forecast: Record<string, Series>; observed: Record<string, (number | null)[]>;
  inputs: Meta["inputs"]; default_receptor_id: string | null;
};
type Alert = { kind: "likely" | "possible" | "none"; place: string; subject?: string; body?: string; would_send_at?: string };
const MON = [
  { site_id: "ib_civic", name: "Imperial Beach Civic Center", lat: 32.576139, lon: -117.115361 },
  { site_id: "nestor_bes", name: "Nestor (Berry Elementary)", lat: 32.567097, lon: -117.090656 },
  { site_id: "san_ysidro", name: "San Ysidro", lat: 32.552794, lon: -117.047286 },
];
const isNight = (iso: string) => { const h = +new Date(iso).toLocaleString("en-US", { hour: "numeric", hour12: false, timeZone: "America/Los_Angeles" }) % 24; return h >= 18 || h < 9; };
const firstAbove = (times: string[], v: (number | null | undefined)[]) => times.find((x, i) => isNight(x) && (v[i] ?? 0) >= 30);

// One line under each monitor chart: when we first said 30+, versus when the monitor first read 30+.
function Compare({ times, s, obs, t, lang }: { times: string[]; s: Series; obs: (number | null)[]; t: Strings; lang: Lang }) {
  const f50 = firstAbove(times, s.p50), f90 = f50 ? undefined : firstAbove(times, s.p90), o = firstAbove(times, obs);
  const fc = f50 ? t.replay_cmp_fc_p50.replace("{time}", fmtTime(f50, lang, true)) : f90 ? t.replay_cmp_fc_p90.replace("{time}", fmtTime(f90, lang, true)) : t.replay_cmp_fc_none;
  const fa = f50 ?? f90;
  const lead = fa && o ? Math.round((+new Date(o) - +new Date(fa)) / 3.6e6) : null;
  return (
    <p className="small compare">
      {fc} {o ? t.replay_cmp_obs.replace("{time}", fmtTime(o, lang, true)) + " " + t.replay_cmp_county : t.replay_cmp_obs_none}
      {lead !== null && " " + (lead > 0 ? t.replay_lead_early.replace("{n}", String(lead)) : lead < 0 ? t.replay_lead_late.replace("{n}", String(-lead)) : t.replay_lead_same)}
    </p>
  );
}

function AlertCard({ night, receptorId, t, lang }: { night: string; receptorId: string | null; t: Strings; lang: Lang }) {
  const [mailLang, setMailLang] = useState<Lang>(lang);
  const [a, setA] = useState<Alert | null>(null);
  useEffect(() => setMailLang(lang), [lang]);
  useEffect(() => {
    if (!receptorId) { setA(null); return; }
    let live = true;
    setA(null);
    get<Alert>(`/api/replay/alert?night=${night}&receptor_id=${encodeURIComponent(receptorId)}&lang=${mailLang}`).then((r) => live && setA(r)).catch(() => live && setA({ kind: "none", place: "" }));
    return () => { live = false; };
  }, [night, receptorId, mailLang]);
  if (!a) return <p className="muted">{t.alert_loading}</p>;
  if (a.kind === "none" || !a.body) return <p className="card">{t.alert_none_place}</p>;
  const sent = a.would_send_at;
  return (
    <div className="email">
      <div className="email-head">
        <div className="seg" role="group" aria-label={t.alert_lang}>
          <button className={mailLang === "en" ? "on" : ""} onClick={() => setMailLang("en")}>EN</button>
          <button className={mailLang === "es" ? "on" : ""} onClick={() => setMailLang("es")}>ES</button>
        </div>
        <dl>
          <dt>{t.mail_from}</dt><dd>Smellcast</dd>
          <dt>{t.mail_to}</dt><dd>{t.mail_you}</dd>
          <dt>{t.mail_sent}</dt><dd>{sent && `${new Date(sent).toLocaleDateString(lang === "es" ? "es-MX" : "en-US", { weekday: "short", month: "short", day: "numeric", timeZone: "America/Los_Angeles" })}, ${fmtClock(sent, lang)}`}</dd>
          <dt>{t.mail_subject}</dt><dd><strong>{a.subject}</strong></dd>
        </dl>
      </div>
      <pre className="email-body">{a.body}</pre>
    </div>
  );
}

export function ReplayPage({ t, lang }: { t: Strings; lang: Lang }) {
  const [nights, setNights] = useState<Night[]>([]);
  const [night, setNight] = useState<string>("");
  const [rep, setRep] = useState<Replay | null>(null);
  const [bounds, setBounds] = useState<[number, number][] | null>(null);
  const [hour, setHour] = useState(5);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [recs, setRecs] = useState<Receptor[]>([]);
  const [rec, setRec] = useState<string | null>(null);

  useEffect(() => {
    get<Night[]>("/api/replay/nights").then((n) => {
      setNights(n);
      const f = n.find((x) => x.featured) ?? n[0];
      if (f) setNight(f.night);
    }).catch((e) => setErr(String(e)));
    get<Receptor[]>("/api/receptors").then((r) => setRecs(r.filter((x) => x.kind !== "monitor"))).catch(() => {});
  }, []);

  useEffect(() => {
    if (!night) return;
    setLoading(true); setErr(null); setRec(null); setRep(null); setBounds(null);
    get<Replay>(`/api/replay?date=${night}`)
      .then(async (r) => {
        setRep(r);
        setHour(Math.max(0, r.valid_times.findIndex((v) => fmtTime(v, "en") === "12 AM")));
        if (r.has_grid) {
          const m = await get<{ grid: { bounds: [number, number][] } | null }>(`/api/forecast/${r.run_id}/meta`);
          setBounds(m.grid?.bounds ?? null);
        }
      })
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, [night]);

  const cur = nights.find((n) => n.night === night);
  const recId = rec ?? (cur?.featured ? cur.receptor_id : null) ?? rep?.default_receptor_id ?? null;
  const fcMon = rep ? MON.map((m) => ({ ...m, ppb: rep.forecast[m.site_id]?.p50[hour] ?? null })) : [];
  const obsMon = rep ? MON.map((m) => ({ ...m, ppb: rep.observed[m.site_id]?.[hour] ?? null })) : [];
  // the alert job runs 15 minutes after the 5 PM run is issued
  const alertTime = useMemo(() => (rep ? fmtClock(new Date(new Date(rep.issued_at).getTime() + 15 * 60000).toISOString(), lang) : ""), [rep, lang]);

  return (
    <div className="page">
      <h1>{t.replay_title}</h1>
      <p className="lede">{t.replay_sub}</p>
      <div className="replay-bar">
        <div className="field">
          <span className="field-k" id="night-k">{t.night_of}</span>
          <Select id="night" value={night} onChange={setNight} ariaLabel={t.night_of}
            groups={[{ options: nights.map((n) => ({ value: n.night, label: `${n.night} · ${t.peak_word} ${fmtPpb(n.peak_ppb)} ppb${n.featured ? ` ★ ${t.replay_featured}` : ""}` })) }]} />
        </div>
        <p className="replay-note"><Icon name="warn" size={15} /><span>{t.replay_label}</span></p>
      </div>
      {loading && <p className="muted">{t.computing}</p>}
      {err && <p className="warn">{err}</p>}
      {rep && (
        <>
          <section className="replay-alert">
            <div className="replay-alert-head">
              <h2>{t.alert_card_title.replace("{time}", alertTime)}</h2>
              <div className="field field-inline">
                <span className="field-k">{t.alert_place_label}</span>
                <Select id="alert-place" value={recId ?? ""} onChange={setRec} ariaLabel={t.alert_place_label}
                  groups={(["neighborhood", "school"] as const).map((k) => ({
                    label: k === "school" ? t.school : t.neighborhood,
                    options: recs.filter((r) => r.kind === k).map((r) => ({ value: r.id, label: r.name })),
                  }))} />
              </div>
            </div>
            <AlertCard night={night} receptorId={recId} t={t} lang={lang} />
            <p className="muted small">{t.alert_preview_note}</p>
          </section>
          <div className="slider-bar static">
            <div className="slider-col">
              <label htmlFor="rh" className="slider-time">{fmtTime(rep.valid_times[hour], lang, true)}</label>
              <input id="rh" type="range" min={0} max={rep.valid_times.length - 1} value={hour} onChange={(e) => setHour(+e.target.value)} />
            </div>
          </div>
          {rep.has_grid ? (
            <>
            <div className="split">
              <ForecastMap height={380} label={`${t.forecast} (${fmtTime(rep.issued_at, lang)})`} overlayUrl={null} zonesUrl={`/api/forecast/${rep.run_id}/zones/${hour}.geojson?pct=p50`} bounds={bounds} monitors={fcMon} monitorKind="forecast" />
              <ForecastMap height={380} label={t.observed} overlayUrl={null} bounds={null} monitors={obsMon} />
            </div>
            <ZoneLegend t={t} pct="p50" measured forecastPin className="zl-inline replay-key" />
            </>
          ) : <p className="muted">{t.replay_no_map}</p>}
          <h2>{t.replay_monitors_h}</h2>
          <div className="chart-grid">
            {MON.map((m) => {
              const o = rep.observed[m.site_id];
              return (
                <article className="chart-card" key={m.site_id}>
                  <h3>{m.name}</h3>
                  <Compare times={rep.valid_times} s={rep.forecast[m.site_id]} obs={o} t={t} lang={lang} />
                  <PointChart times={rep.valid_times} s={rep.forecast[m.site_id]} observed={o} t={t} lang={lang} height={280}
                    issued={rep.issued_at} firstObs={firstAbove(rep.valid_times, o)} />
                  <p className="chart-key"><span className="line-key" /> {t.forecast} <span className="obs-key" /> {t.observed} <span className="thr-key" /> {t.orange_line}</p>
                </article>
              );
            })}
          </div>
          <div className="grid2">
            <InputsCard inputs={rep.inputs} hour={hour} t={t} title={`${t.replay_inputs} (${t.replay_inputs_hour})`} />
            <div className="card">
              <h3>{t.reports_title}</h3>
              <p className="muted small">{t.reports_sub}</p>
              <Reports url={`/api/reports?night=${night}&days=2`} t={t} lang={lang} compact />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
