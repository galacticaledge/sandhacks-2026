import { useEffect, useMemo, useState } from "react";
import { get, type Meta, type Now } from "../api";
import { ForecastMap, type MapSource } from "../components/ForecastMap";
import { InputsCard } from "../components/InputsCard";
import { Legend } from "../components/Legend";
import { LevelBadge } from "../components/LevelBadge";
import { PointChart } from "../components/PointChart";
import { TonightStrip } from "../components/TonightStrip";
import { Icon } from "../components/Icons";
import { LEVELS, fmtPpb, fmtTime, levelOf, levelStyle } from "../levels";
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
        <div className="map-legend" aria-hidden="true">
          {LEVELS.map((l) => (
            <span key={l.key}><i style={{ background: l.color, color: l.ink }}>{l.icon}</i>{t[`range_${l.key}` as keyof Strings] as string}</span>
          ))}
        </div>
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
        <form className="fc-search side-search" onSubmit={search} role="search">
          <label className="fc-input">
            <Icon name="search" size={18} />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t.search_short} aria-label={t.search_placeholder} />
          </label>
          <button className="btn-grape">{t.search}</button>
        </form>
        {pickErr && <p className="warn small">{pickErr}</p>}
        {point ? (
          <section className="panel">
            <div className="panel-row">
              <h3 className="panel-h">{t.point_title}</h3>
              <button className="link small" onClick={() => setPoint(null)}>{t.close}</button>
            </div>
            <div className="badges">
              <span><span className="muted small">P50</span> <LevelBadge level={levelOf(Math.max(...point.p50))} t={t} small /> <strong>{fmtPpb(Math.max(...point.p50))}</strong> <span className="muted small">ppb</span></span>
              <span><span className="muted small">P90</span> <LevelBadge level={levelOf(Math.max(...point.p90))} t={t} small /> <strong>{fmtPpb(Math.max(...point.p90))}</strong> <span className="muted small">ppb</span></span>
            </div>
            <PointChart times={point.valid_times} s={point} t={t} lang={lang} height={180} />
            <p className="tile-sub">{point.lat.toFixed(4)}, {point.lon.toFixed(4)}</p>
          </section>
        ) : (
          <p className="side-hint"><Icon name="live" size={16} />{t.click_hint}</p>
        )}
        <section className="panel">
          <h3 className="panel-h">{t.monitors} <span>{t.readings}</span></h3>
          <ul className="mon-rows">
            {(now?.monitors ?? []).map((m) => {
              const l = levelStyle(m.level);
              return (
                <li key={m.site_id} title={m.name}>
                  <span className="now-swatch" style={{ background: l?.color ?? "#777", color: l?.ink }}
                    aria-label={l ? (t[`level_${l.key}` as keyof Strings] as string) : "–"}>{l?.icon ?? "○"}</span>
                  <span className="mon-name">{m.name.replace(/ \(.*\)/, "")}<small>{m.observed_at ? fmtTime(m.observed_at, lang, true) : "–"}</small></span>
                  <span className="mon-ppb"><strong>{fmtPpb(m.ppb)}</strong><small>ppb</small></span>
                </li>
              );
            })}
          </ul>
        </section>
        {meta && vt && <InputsCard inputs={meta.inputs} hour={hour} t={t} title={`${t.conditions} · ${fmtTime(vt, lang, true)}`} />}
        <details className="panel fold">
          <summary>{t.map_key}</summary>
          <ul className="key">
            <li><span className="src src-main inline">☣</span> {t.hotspot}</li>
            <li><span className="src inline" /> {t.sources}</li>
            <li><span className="dot inline" /> {t.complaints}</li>
          </ul>
          <Legend t={t} />
        </details>
      </aside>
    </div>
    </>
  );
}
