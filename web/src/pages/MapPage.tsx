import { useEffect, useMemo, useState } from "react";
import { get, type Meta, type Now } from "../api";
import { ForecastMap, type MapSource } from "../components/ForecastMap";
import { InputsCard } from "../components/InputsCard";
import { LevelBadge } from "../components/LevelBadge";
import { PointChart } from "../components/PointChart";
import { TonightStrip } from "../components/TonightStrip";
import { Icon } from "../components/Icons";
import { PanelHead } from "../components/PanelHead";
import { ZoneLegend } from "../components/ZoneLegend";
import { PlayButton, usePlayback, usePrefetchZones } from "../playback";
import { LEVELS, fmtPpb, fmtTime, levelOf, levelStyle } from "../levels";
import type { Lang, Strings } from "../i18n";

type Point = { lat: number; lon: number; valid_times: string[]; p10: number[]; p50: number[]; p90: number[] };

export function MapPage({ t, lang, now }: { t: Strings; lang: Lang; now: Now | null }) {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [hour, setHour] = useState(0);
  const [pct, setPct] = useState<"p50" | "p90">("p50");
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

  const [playing, setPlaying] = usePlayback(meta?.valid_times.length ?? 0, setHour, meta?.run_id);
  usePrefetchZones(meta?.run_id, meta?.valid_times.length ?? 0, pct);

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
    const u = `https://nominatim.openstreetmap.org/search?format=json&limit=1&bounded=1&viewbox=-117.25,32.72,-116.93,32.534&q=${encodeURIComponent(q)}`;
    const r = await fetch(u).then((x) => x.json()).catch(() => []);
    if (Array.isArray(r) && r[0]) pickAt(parseFloat(r[0].lat), parseFloat(r[0].lon));
    else { setPoint(null); setPickErr(t.outside); }
  };

  const monitors = useMemo(() => (now?.monitors ?? []).map((m) => ({ ...m })), [now]);
  const vt = meta?.valid_times[hour];

  return (
    <>
    <TonightStrip t={t} lang={lang} />
    <div className="map-page live">
      <section className="map-main live-card" aria-label={t.nav_map}>
        <div className="live-map">
          <ForecastMap
            overlayUrl={null}
            zonesUrl={meta ? `/api/forecast/${meta.run_id}/zones/${hour}.geojson?pct=${pct}` : null}
            bounds={meta?.grid?.bounds ?? null}
            monitors={monitors}
            sources={(now as unknown as { sources?: MapSource[] })?.sources}
            complaints={complaints}
            marker={point}
            onPick={pickAt}
          />
          {vt && <span className="map-tag"><span>{t.forecast_word}</span>{fmtTime(vt, lang, true)} · {pct === "p50" ? t.median : t.high_est}</span>}
        </div>
        <footer className="map-foot">
          {meta && (
            <div className="play-row">
              <PlayButton playing={playing} setPlaying={setPlaying} t={t} />
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
          <div className="key-row">
            <ZoneLegend t={t} pct={pct} className="key-group zl-inline" />
            <div className="key-group">
              <span className="key-k">{t.key_measured}</span>
              <span className="mon mon-meas inline"><i style={{ background: LEVELS[0].color, color: LEVELS[0].ink }}>{LEVELS[0].icon}</i><b>0.7</b><small>ppb</small></span>
            </div>
            <div className="key-group key-sources">
              <span><span className="src src-main inline">☣</span>{t.hotspot}</span>
              <span><span className="src inline" />{t.sources}</span>
              <span><span className="dot inline" />{t.complaints}</span>
            </div>
          </div>
        </footer>
      </section>

      <aside className="side">
        <section className="panel">
          <PanelHead icon="search" title={t.panel_location} />
          <form className="fc-search side-search" onSubmit={search} role="search">
            <label className="fc-input">
              <Icon name="search" size={18} />
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t.search_short} aria-label={t.search_placeholder} />
            </label>
            <button className="btn-grape">{t.search}</button>
          </form>
          {pickErr && <p className="warn small">{pickErr}</p>}
          {point ? (
            <div className="spot">
              <div className="panel-row">
                <span className="small muted">{t.point_title} · {point.lat.toFixed(4)}, {point.lon.toFixed(4)}</span>
                <button className="link small" onClick={() => setPoint(null)}>{t.close}</button>
              </div>
              <div className="spot-vals">
                <div><span className="small muted">{t.median}</span><LevelBadge level={levelOf(Math.max(...point.p50))} t={t} small /><strong>{fmtPpb(Math.max(...point.p50))} <small>ppb</small></strong></div>
                <div><span className="small muted">{t.high_est}</span><LevelBadge level={levelOf(Math.max(...point.p90))} t={t} small /><strong>{fmtPpb(Math.max(...point.p90))} <small>ppb</small></strong></div>
              </div>
              <PointChart times={point.valid_times} s={point} t={t} lang={lang} height={170} />
            </div>
          ) : (
            <p className="side-hint">{t.click_hint}</p>
          )}
        </section>

        <section className="panel">
          <PanelHead icon="live" title={t.monitors} meta={t.key_measured} />
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
      </aside>
    </div>
    </>
  );
}
