import { useEffect, useMemo, useState } from "react";
import { get, type Meta, type Now } from "../api";
import { ForecastMap, type MapSource } from "../components/ForecastMap";
import { InputsCard } from "../components/InputsCard";
import { Legend } from "../components/Legend";
import { LevelBadge } from "../components/LevelBadge";
import { PointChart } from "../components/PointChart";
import { TonightStrip } from "../components/TonightStrip";
import { fmtPpb, fmtTime, levelOf } from "../levels";
import type { Lang, Strings } from "../i18n";

type Point = { lat: number; lon: number; valid_times: string[]; p10: number[]; p50: number[]; p90: number[] };

export function MapPage({ t, lang, now }: { t: Strings; lang: Lang; now: Now | null }) {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [hour, setHour] = useState(0);
  const [pct, setPct] = useState<"p50" | "p90">("p50");
  const [playing, setPlaying] = useState(false);
  const [complaints, setComplaints] = useState<{ lat: number; lon: number }[]>([]);
  const [point, setPoint] = useState<Point | null>(null);
  const [pickErr, setPickErr] = useState<string | null>(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    if (!now?.latest_run_id) return;
    get<Meta>(`/api/forecast/${now.latest_run_id}/meta`).then((m) => {
      setMeta(m);
      // start the slider at the first night hour (6 PM) if it is ahead, else at the current hour
      const i = m.valid_times.findIndex((v) => new Date(v).toLocaleString("en-US", { hour: "numeric", hour12: false, timeZone: "America/Los_Angeles" }) === "18");
      setHour(i > 0 ? i : 0);
    });
    get<{ lat: number; lon: number }[]>("/api/complaints?days=7").then(setComplaints).catch(() => {});
  }, [now?.latest_run_id]);

  useEffect(() => {
    if (!playing || !meta) return;
    const id = setInterval(() => setHour((h) => (h + 1) % meta.valid_times.length), 700);
    return () => clearInterval(id);
  }, [playing, meta]);

  // preload overlays so the slider is smooth
  useEffect(() => {
    if (!meta) return;
    meta.valid_times.forEach((_, h) => { const i = new Image(); i.src = `/api/forecast/${meta.run_id}/grid/${h}.png?pct=${pct}`; });
  }, [meta, pct]);

  const pickAt = async (lat: number, lon: number) => {
    setPickErr(null);
    try {
      const r = await get<Point>(`/api/forecast/latest/point?lat=${lat.toFixed(5)}&lon=${lon.toFixed(5)}`);
      setPoint({ ...r, lat, lon });
    } catch {
      setPoint(null);
      setPickErr(t.outside);
    }
  };

  const search = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!q.trim()) return;
    const u = `https://nominatim.openstreetmap.org/search?format=json&limit=1&bounded=1&viewbox=-117.14,32.60,-117.03,32.535&q=${encodeURIComponent(q)}`;
    const r = await fetch(u).then((x) => x.json()).catch(() => []);
    if (Array.isArray(r) && r[0]) pickAt(parseFloat(r[0].lat), parseFloat(r[0].lon));
    else { setPoint(null); setPickErr(t.outside); }
  };

  const monitors = useMemo(() => (now?.monitors ?? []).map((m) => ({ ...m })), [now]);
  const vt = meta?.valid_times[hour];

  return (
    <>
    <TonightStrip t={t} lang={lang} />
    <div className="map-page">
      <section className="map-main" aria-label={t.nav_map}>
        <ForecastMap
          overlayUrl={meta ? `/api/forecast/${meta.run_id}/grid/${hour}.png?pct=${pct}` : null}
          bounds={meta?.grid?.bounds ?? null}
          monitors={monitors}
          sources={(now as unknown as { sources?: MapSource[] })?.sources}
          complaints={complaints}
          marker={point}
          onPick={pickAt}
        />
        {meta && (
          <div className="slider-bar">
            <button className="btn" onClick={() => setPlaying(!playing)} aria-pressed={playing}>{playing ? "❚❚ " + t.pause : "▶ " + t.play}</button>
            <div className="slider-col">
              <label htmlFor="hour" className="slider-time">{vt && fmtTime(vt, lang, true)}</label>
              <input id="hour" type="range" min={0} max={meta.valid_times.length - 1} value={hour}
                onChange={(e) => { setPlaying(false); setHour(+e.target.value); }} />
            </div>
            <div className="seg" role="group" aria-label={t.show}>
              <button className={pct === "p50" ? "on" : ""} onClick={() => setPct("p50")}>{t.median}</button>
              <button className={pct === "p90" ? "on" : ""} onClick={() => setPct("p90")}>{t.high_est}</button>
            </div>
          </div>
        )}
      </section>
      <aside className="side">
        <form className="search" onSubmit={search}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t.search_placeholder} aria-label={t.search_placeholder} />
          <button className="btn">{t.search}</button>
        </form>
        {pickErr && <p className="warn">{pickErr}</p>}
        {point ? (
          <div className="card">
            <div className="card-head">
              <h3>{t.point_title}</h3>
              <button className="link" onClick={() => setPoint(null)}>{t.close}</button>
            </div>
            <p className="muted small">{point.lat.toFixed(4)}, {point.lon.toFixed(4)} · {t.peak}: {fmtPpb(Math.max(...point.p50))} ppb · {t.peak_high}: {fmtPpb(Math.max(...point.p90))} ppb</p>
            <PointChart times={point.valid_times} s={point} t={t} lang={lang} />
            <div className="badges">
              <span>{t.median}: <LevelBadge level={levelOf(Math.max(...point.p50))} t={t} /></span>
              <span>{t.high_est}: <LevelBadge level={levelOf(Math.max(...point.p90))} t={t} /></span>
            </div>
          </div>
        ) : (
          <p className="hint">{t.click_hint}</p>
        )}
        <div className="card">
          <h3>{t.monitors} <span className="muted small">({t.readings})</span></h3>
          <ul className="mon-list">
            {(now?.monitors ?? []).map((m) => (
              <li key={m.site_id}>
                <span>{m.name}</span>
                <span className="mon-val"><LevelBadge level={m.level} t={t} small /> {fmtPpb(m.ppb)} ppb</span>
                <span className="muted small">{m.observed_at && fmtTime(m.observed_at, lang, true)}</span>
              </li>
            ))}
          </ul>
        </div>
        {meta && <InputsCard inputs={meta.inputs} hour={hour} t={t} />}
        <Legend t={t} />
        <ul className="key">
          <li><span className="src src-main inline">☣</span> {t.hotspot}</li>
          <li><span className="src inline" /> {t.sources}</li>
          <li><span className="dot inline" /> {t.complaints}</li>
        </ul>
      </aside>
    </div>
    </>
  );
}
