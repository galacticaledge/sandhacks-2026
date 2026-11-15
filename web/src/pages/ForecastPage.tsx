import { useEffect, useMemo, useState } from "react";
import { get, type Level, type Meta, type Now, type Series, type TonightItem } from "../api";
import { ForecastMap, type MapPlace, type MapSource } from "../components/ForecastMap";
import { Gauge } from "../components/Gauge";
import { Icon } from "../components/Icons";
import { Legend } from "../components/Legend";
import { LevelBadge } from "../components/LevelBadge";
import { PointChart } from "../components/PointChart";
import { Spark } from "../components/Spark";
import { LEVELS, fmtPpb, fmtTime, levelOf, levelStyle } from "../levels";
import type { Lang, Strings } from "../i18n";

type Tonight = { run_id: string; run_kind: string; issued_at: string; items: TonightItem[] };
type Kind = "all" | "neighborhood" | "school" | "monitor";
type Picked = { id?: string; name: string; lat: number; lon: number; times: string[]; s: Series };

const rank = (l: Level | null | undefined) => LEVELS.findIndex((x) => x.key === l);

// Matches the Figma "Smellcast Forecast" frame: address search, map card with filter pills, detail cards below.
export function ForecastPage({ t, lang, now }: { t: Strings; lang: Lang; now: Now | null }) {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [tonight, setTonight] = useState<Tonight | null>(null);
  const [kind, setKind] = useState<Kind>("all");
  const [minLevel, setMinLevel] = useState<Level>("green");
  const [hour, setHour] = useState(0);
  const [pct, setPct] = useState<"p50" | "p90">("p50");
  const [picked, setPicked] = useState<Picked | null>(null);
  const [q, setQ] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!now?.latest_run_id) return;
    get<Meta>(`/api/forecast/${now.latest_run_id}/meta`).then((m) => {
      setMeta(m);
      const i = m.valid_times.findIndex((v) => new Date(v).toLocaleString("en-US", { hour: "numeric", hour12: false, timeZone: "America/Los_Angeles" }) === "18");
      setHour(i > 0 ? i : 0);
    });
  }, [now?.latest_run_id]);
  useEffect(() => { get<Tonight>(`/api/tonight?lang=${lang}`).then(setTonight).catch(() => setTonight(null)); }, [lang]);

  const items = useMemo(() => (tonight?.items ?? []).filter((r) =>
    (kind === "all" || r.kind === kind) && rank(r.level ?? "green") >= rank(minLevel)), [tonight, kind, minLevel]);

  const selectPlace = (id: string) => {
    const r = tonight?.items.find((x) => x.id === id) ?? meta?.receptors.find((x) => x.id === id);
    const s = meta?.series[id];
    if (!r || !s || !meta) return;
    setMsg(null);
    setPicked({ id, name: r.name, lat: r.lat, lon: r.lon, times: meta.valid_times, s });
  };

  // default selection: tonight's highest place
  useEffect(() => {
    if (!picked && meta && tonight?.items[0]) selectPlace(tonight.items[0].id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta, tonight]);

  const pickAt = async (lat: number, lon: number, name?: string) => {
    setMsg(null);
    try {
      const r = await get<{ valid_times: string[] } & Series>(`/api/forecast/latest/point?lat=${lat.toFixed(5)}&lon=${lon.toFixed(5)}`);
      setPicked({ name: name ?? `${lat.toFixed(4)}, ${lon.toFixed(4)}`, lat, lon, times: r.valid_times, s: r });
    } catch {
      setMsg(t.outside);
    }
  };

  const search = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!q.trim()) return;
    setBusy(true);
    const u = `https://nominatim.openstreetmap.org/search?format=json&limit=1&bounded=1&viewbox=-117.14,32.60,-117.03,32.535&q=${encodeURIComponent(q)}`;
    const r = await fetch(u).then((x) => x.json()).catch(() => []);
    setBusy(false);
    if (r[0]) pickAt(parseFloat(r[0].lat), parseFloat(r[0].lon), r[0].display_name.split(",").slice(0, 2).join(","));
    else setMsg(t.outside);
  };

  const places: MapPlace[] = useMemo(() => items.filter((r) => r.kind !== "monitor")
    .map((r) => ({ id: r.id, name: r.name, lat: r.lat, lon: r.lon, level: r.level ?? null, ppb: r.peak_p50 ?? null })), [items]);
  const showMonitors = kind === "all" || kind === "monitor";
  const vt = meta?.valid_times[hour];
  const met = meta?.inputs.met;
  const pItem = picked?.id ? tonight?.items.find((x) => x.id === picked.id) : undefined;
  const peak50 = picked ? Math.max(...picked.s.p50) : null;
  const peak90 = picked ? Math.max(...picked.s.p90) : null;
  // highest median across all places, per hour: drives the summary strip
  const regionMax = useMemo(() => {
    if (!meta) return [] as number[];
    const ss = Object.values(meta.series);
    return meta.valid_times.map((_, h) => Math.max(0, ...ss.map((x) => x.p50[h] ?? 0)));
  }, [meta]);
  const stripTop = Math.max(5, ...regionMax);
  // same rules as the "Orange tonight?" strip: places only (no monitors), worst level first, then highest median
  const placesTonight = (tonight?.items ?? []).filter((i) => i.kind !== "monitor");
  const worst = [...placesTonight].sort((a, b) => rank(b.level ?? "green") - rank(a.level ?? "green") || (b.peak_p50 ?? 0) - (a.peak_p50 ?? 0))[0];
  const nLikely = placesTonight.filter((i) => i.alert === "likely").length, nPossible = placesTonight.filter((i) => i.alert === "possible").length;
  const lvlName = (l?: Level | null) => (l ? (t[`level_${l}` as keyof Strings] as string) : "–");
  const pills: [Kind, string][] = [["all", t.all_areas], ["neighborhood", t.neighborhoods], ["school", t.schools], ["monitor", t.monitors_f]];

  return (
    <div className="fc">
      {worst && (
        <section className="hero card-xl" aria-label={t.tonight_title}>
          <div className="hero-sec hero-verdict">
            <span className="eyebrow">{t.tonight_title}</span>
            <h1>{t.hero_expect}</h1>
            <span className={`hero-level lvl-${worst.level ?? "green"}`}>{lvlName(worst.level)}</span>
            <p className="hero-orange">
              {nLikely + nPossible > 0
                ? t.strip_orange.replace("{n}", String(nLikely + nPossible)).replace("{m}", String(placesTonight.length)).replace("{a}", String(nLikely)).replace("{b}", String(nPossible))
                : t.strip_none}
            </p>
          </div>

          <div className="hero-sec hero-peak">
            <span className="eyebrow">{t.hero_highest}</span>
            <div className="peak-body">
              <Gauge p50={worst.peak_p50 ?? 0} p90={worst.peak_p90 ?? 0} label={worst.name} compact />
              <dl className="peak-facts">
                <dt>{t.place}</dt><dd><strong>{worst.name}</strong></dd>
                <dt>{t.peak_hour}</dt><dd>{worst.peak_time ? fmtTime(worst.peak_time, lang, true) : "–"}</dd>
                <dt>{t.peak_high}</dt><dd>{fmtPpb(worst.peak_p90)} ppb</dd>
              </dl>
            </div>
          </div>

          {meta && (
            <div className="hero-sec hero-hours">
              <span className="eyebrow">{t.hour_by_hour}</span>
              <div className="hstrip" role="group" aria-label={t.hour}>
                <div className="hstrip-bars">
                  {regionMax.map((v, h) => {
                    const l = levelStyle(levelOf(v));
                    return (
                      <button key={h} className={`bar${h === hour ? " on" : ""}`} onClick={() => setHour(h)}
                        title={`${fmtTime(meta.valid_times[h], lang, true)}: ${fmtPpb(v)} ppb`} aria-label={`${fmtTime(meta.valid_times[h], lang, true)}: ${fmtPpb(v)} ppb`}>
                        <span style={{ height: `${18 + 82 * Math.min(1, v / stripTop)}%`, background: l?.color }} />
                      </button>
                    );
                  })}
                </div>
                <div className="hstrip-axis">
                  {meta.valid_times.map((v, h) => <span key={h}>{h % 6 === 0 ? fmtTime(v, lang) : ""}</span>)}
                </div>
              </div>
              {met && vt && (
                <div className="conds" aria-label={`${t.cond_at} ${fmtTime(vt, lang, true)}`}>
                  <strong className="conds-time">{fmtTime(vt, lang, true)}</strong>
                  <span className="cond" title={t.wind}>
                    <span className="wind-arrow" style={{ transform: `rotate(${(met.wind_dir_deg[hour] ?? 0) + 180}deg)` }} aria-hidden="true"><Icon name="arrow" size={14} /></span>
                    {(met.wind_ms[hour] ?? 0).toFixed(1)} m/s
                  </span>
                  <span className="cond" title={t.temp}><Icon name="temp" size={14} />{(met.temp_c[hour] ?? 0).toFixed(0)} °C</span>
                  <span className={`cond${"EF".includes(met.stability[hour]) ? " cond-still" : ""}`} title={`${t.stability} ${met.stability[hour]}`}>
                    <Icon name="layers" size={14} />{"EF".includes(met.stability[hour]) ? t.air_still : t.air_mixing}
                  </span>
                  <span className="cond" title={t.river_flow}><Icon name="wave" size={14} />{meta.inputs.flow_mgd[hour]} MGD</span>
                </div>
              )}
              <small className="muted">{t.strip_note}</small>
            </div>
          )}
        </section>
      )}
      <section className="fc-map card-xl" aria-label={t.nav_forecast}>
        <div className="map-toolbar">
          <form className="fc-search tb-search" onSubmit={search} role="search">
            <label className="fc-input">
              <Icon name="search" size={18} />
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t.search_placeholder} aria-label={t.search_placeholder} />
            </label>
            <button className="btn-grape" disabled={busy}>{t.search}</button>
          </form>
          <div className="pills tb-pills" role="group" aria-label={t.filters}>
            <label className="pill-select">
              <span className="sr-only">{t.risk_level}</span>
              <select value={minLevel} onChange={(e) => setMinLevel(e.target.value as Level)} aria-label={t.risk_level}>
                <option value="green">{t.risk_level}: {t.lvl_all}</option>
                <option value="yellow">{t.lvl_yellow}</option>
                <option value="orange">{t.lvl_orange}</option>
              </select>
              <Icon name="chevron" size={16} />
            </label>
            {pills.map(([k, label]) => (
              <button key={k} className={`pill-btn${kind === k ? " on" : ""}`} aria-pressed={kind === k} onClick={() => setKind(k)}>{label}</button>
            ))}
          </div>
        </div>
        {msg && <p className="warn small search-msg" role="status">{msg}</p>}
        <div className="fc-map-body">
        <ForecastMap
          overlayUrl={meta ? `/api/forecast/${meta.run_id}/grid/${hour}.png?pct=${pct}` : null}
          bounds={meta?.grid?.bounds ?? null}
          monitors={showMonitors ? now?.monitors ?? [] : []}
          sources={(now as unknown as { sources?: MapSource[] })?.sources}
          places={places}
          selectedId={picked?.id}
          onPlace={selectPlace}
          marker={picked && !picked.id ? picked : null}
          onPick={(la, lo) => pickAt(la, lo)}
        />
        <div className="map-legend" aria-hidden="true">
          {LEVELS.map((l) => (
            <span key={l.key}><i style={{ background: l.color, color: l.ink }}>{l.icon}</i>{t[`range_${l.key}` as keyof Strings] as string}</span>
          ))}
        </div>
        {meta && (
          <div className="slider-bar">
            <div className="slider-col">
              <label htmlFor="fh" className="slider-time">{vt && fmtTime(vt, lang, true)}</label>
              <input id="fh" type="range" min={0} max={meta.valid_times.length - 1} value={hour} onChange={(e) => setHour(+e.target.value)} />
            </div>
            <div className="seg" role="group" aria-label={t.show}>
              <button className={pct === "p50" ? "on" : ""} onClick={() => setPct("p50")}>{t.median}</button>
              <button className={pct === "p90" ? "on" : ""} onClick={() => setPct("p90")}>{t.high_est}</button>
            </div>
          </div>
        )}
        </div>
      </section>

      <div className="fc-bottom">
        <section className="card-xl detail" aria-live="polite">
          {picked ? (
            <>
              <div className="detail-head">
                <div>
                  <h2>{picked.name}</h2>
                  <p className="muted small">{t.point_title}</p>
                </div>
                <div className="badges">
                  <span title={t.median}><span className="muted small">P50</span> <LevelBadge level={pItem?.level ?? levelOf(peak50)} t={t} small /></span>
                  <span title={t.high_est}><span className="muted small">P90</span> <LevelBadge level={pItem?.level_p90 ?? levelOf(peak90)} t={t} small /></span>
                </div>
              </div>
              <div className="stats">
                <div><span><Icon name="peak" size={14} />{t.peak}</span><strong>{fmtPpb(pItem?.peak_p50 ?? peak50)} <small>ppb</small></strong></div>
                <div><span><Icon name="high" size={14} />{t.peak_high}</span><strong>{fmtPpb(pItem?.peak_p90 ?? peak90)} <small>ppb</small></strong></div>
                {pItem?.peak_time && <div><span><Icon name="clock" size={14} />{t.peak_hour}</span><strong>{fmtTime(pItem.peak_time, lang, true)}</strong></div>}
                {pItem?.confidence && <div><span><Icon name="shield" size={14} />{t.confidence}</span><strong>{t[`conf_${pItem.confidence}` as keyof Strings] as string}</strong></div>}
              </div>
              <PointChart times={picked.times} s={picked.s} t={t} lang={lang} height={190} />
              <p className="muted small">{t.uncertainty}</p>
              {pItem?.guidance && (
                <details className="guidance">
                  <summary>{t.sdapcd_says}</summary>
                  <p>{pItem.guidance.expect}</p>
                  <ul>{pItem.guidance.actions.map((a) => <li key={a}>{a}</li>)}</ul>
                </details>
              )}
            </>
          ) : <p className="muted">{t.pick_place}</p>}
        </section>

        <section className="card-xl rank">
          <div className="detail-head">
            <h2>{t.tonight_rank}</h2>
            <a href="#/tonight" className="small">{t.full_table} →</a>
          </div>
          <ul className="rank-list">
            {items.slice(0, 8).map((r) => (
              <li key={r.id}>
                <button className={picked?.id === r.id ? "on" : ""} onClick={() => selectPlace(r.id)}>
                  <span className="rank-name">{r.name}<small>{r.kind === "school" ? t.school : r.kind === "monitor" ? t.monitor : t.neighborhood}</small></span>
                  <LevelBadge level={r.level} t={t} small />
                  <Spark values={meta?.series[r.id]?.p50 ?? []} width={48} />
                  <span className="rank-val"><span>{fmtPpb(r.peak_p50)} <small>ppb</small></span><small>P90 {fmtPpb(r.peak_p90)}</small></span>
                </button>
              </li>
            ))}
            {tonight && items.length === 0 && <li className="muted small">{t.no_match}</li>}
          </ul>
          <p className="muted small">{t.run_note}</p>
          <Legend t={t} />
        </section>
      </div>
      <p className="muted small">{t.never_safe}</p>
    </div>
  );
}
