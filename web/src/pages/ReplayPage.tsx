import { useEffect, useState } from "react";
import { get, type Series } from "../api";
import { ForecastMap } from "../components/ForecastMap";
import { PointChart } from "../components/PointChart";
import { fmtPpb, fmtTime } from "../levels";
import type { Lang, Strings } from "../i18n";

type Night = { night: string; peak_ppb: number | null };
type Replay = {
  night: string; run_id: string; issued_at: string; valid_times: string[]; label: string;
  forecast: Record<string, Series>; observed: Record<string, (number | null)[]>;
};
const MON = [
  { site_id: "ib_civic", name: "Imperial Beach Civic Center", lat: 32.576139, lon: -117.115361 },
  { site_id: "nestor_bes", name: "Nestor (Berry Elementary)", lat: 32.567097, lon: -117.090656 },
  { site_id: "san_ysidro", name: "San Ysidro", lat: 32.552794, lon: -117.047286 },
];

export function ReplayPage({ t, lang }: { t: Strings; lang: Lang }) {
  const [nights, setNights] = useState<Night[]>([]);
  const [night, setNight] = useState<string>("");
  const [rep, setRep] = useState<Replay | null>(null);
  const [bounds, setBounds] = useState<[number, number][] | null>(null);
  const [hour, setHour] = useState(5);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    get<Night[]>("/api/replay/nights").then((n) => {
      setNights(n);
      const top = [...n].sort((a, b) => (b.peak_ppb ?? 0) - (a.peak_ppb ?? 0))[0];
      if (top) setNight(top.night);
    });
  }, []);

  useEffect(() => {
    if (!night) return;
    setLoading(true); setErr(null);
    get<Replay>(`/api/replay?night=${night}`)
      .then(async (r) => {
        setRep(r);
        const m = await get<{ grid: { bounds: [number, number][] } | null }>(`/api/forecast/${r.run_id}/meta`);
        setBounds(m.grid?.bounds ?? null);
        setHour(Math.max(0, r.valid_times.findIndex((v) => fmtTime(v, "en") === "12 AM")));
      })
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, [night]);

  const fcMon = rep ? MON.map((m) => ({ ...m, ppb: rep.forecast[m.site_id]?.p50[hour] ?? null })) : [];
  const obsMon = rep ? MON.map((m) => ({ ...m, ppb: rep.observed[m.site_id]?.[hour] ?? null })) : [];

  return (
    <div className="page">
      <h1>{t.replay_title}</h1>
      <p className="lede">{t.replay_sub}</p>
      <div className="row">
        <label>{t.night_of}{" "}
          <select value={night} onChange={(e) => setNight(e.target.value)}>
            {nights.map((n) => <option key={n.night} value={n.night}>{n.night} · {t.peak_word} {fmtPpb(n.peak_ppb)} ppb</option>)}
          </select>
        </label>
        <span className="pill warn-pill">{t.replay_label}</span>
      </div>
      {loading && <p className="muted">{t.computing}</p>}
      {err && <p className="warn">{err}</p>}
      {rep && (
        <>
          <div className="slider-bar static">
            <div className="slider-col">
              <label htmlFor="rh" className="slider-time">{fmtTime(rep.valid_times[hour], lang, true)}</label>
              <input id="rh" type="range" min={0} max={rep.valid_times.length - 1} value={hour} onChange={(e) => setHour(+e.target.value)} />
            </div>
          </div>
          <div className="split">
            <ForecastMap height={380} label={`${t.forecast} (5 PM)`} overlayUrl={bounds ? `/api/forecast/${rep.run_id}/grid/${hour}.png?pct=p50` : null} bounds={bounds} monitors={fcMon} />
            <ForecastMap height={380} label={t.observed} overlayUrl={null} bounds={null} monitors={obsMon} />
          </div>
          <div className="grid3">
            {MON.map((m) => (
              <div className="card" key={m.site_id}>
                <h3>{m.name}</h3>
                <PointChart times={rep.valid_times} s={rep.forecast[m.site_id]} observed={rep.observed[m.site_id]} t={t} lang={lang} height={200} />
                <p className="muted small"><span className="line-key" /> {t.forecast} · <span className="obs-key" /> {t.observed}</p>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
