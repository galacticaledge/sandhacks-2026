import { lazy, Suspense, useEffect, useState } from "react";
import { get, type Now } from "./api";
import { fmtDateTime, fmtPpb, levelStyle } from "./levels";
import { STRINGS, type Lang } from "./i18n";
import { Icon, Skyline } from "./components/Icons";
import type { Theme } from "./pages/SettingsPage";

// Each page is its own chunk, so the map and chart libraries load only where used.
const AboutPage = lazy(() => import("./pages/AboutPage").then((m) => ({ default: m.AboutPage })));
const AccuracyPage = lazy(() => import("./pages/AccuracyPage").then((m) => ({ default: m.AccuracyPage })));
const AlertsPage = lazy(() => import("./pages/AlertsPage").then((m) => ({ default: m.AlertsPage })));
const EvidencePage = lazy(() => import("./pages/EvidencePage").then((m) => ({ default: m.EvidencePage })));
const ForecastPage = lazy(() => import("./pages/ForecastPage").then((m) => ({ default: m.ForecastPage })));
const MapPage = lazy(() => import("./pages/MapPage").then((m) => ({ default: m.MapPage })));
const ReplayPage = lazy(() => import("./pages/ReplayPage").then((m) => ({ default: m.ReplayPage })));
const SettingsPage = lazy(() => import("./pages/SettingsPage").then((m) => ({ default: m.SettingsPage })));
const TonightPage = lazy(() => import("./pages/TonightPage").then((m) => ({ default: m.TonightPage })));

// Sidebar order follows the Figma frame. Tonight and About are reachable from Forecast and Settings.
const NAV = ["forecast", "live", "replay", "accuracy", "evidence", "alerts", "settings"] as const;
const ROUTES = [...NAV, "tonight", "about"] as const;
type Route = (typeof ROUTES)[number];
const routeFromHash = (): Route => {
  const r = window.location.hash.replace(/^#\/?/, "");
  if (r === "map") return "live"; // old links
  return (ROUTES as readonly string[]).includes(r) ? (r as Route) : "forecast";
};
const FALLBACK_OFFICIAL = {
  sdapcd_h2s: "https://www.sdapcd.org/content/sdapcd/about/tj-river-valley/tjrv-air-quality-monitoring.html",
  sdapcd_alerts_signup: "https://public.govdelivery.com/accounts/CASDCAPCD/subscriber/new",
  guidance_en: "https://www.sdapcd.org/content/dam/sdapcd/documents/tjrv/Community%20H2S%20Guidance_11.13.24_ENGLISH.pdf",
  guidance_es: "https://www.sdapcd.org/content/dam/sdapcd/documents/tjrv/Community%20H2S%20Guidance_11.13.24_SPANISH.pdf",
};
const stored = <T extends string>(k: string, d: T): T => { try { return (localStorage.getItem(k) as T) || d; } catch { return d; } };
const store = (k: string, v: string) => { try { localStorage.setItem(k, v); } catch { /* private mode */ } };

export default function App() {
  const [route, setRoute] = useState<Route>(routeFromHash());
  const [lang, setLang] = useState<Lang>(() => stored("lang", navigator.language.startsWith("es") ? "es" : "en"));
  const [theme, setTheme] = useState<Theme>(() => stored<Theme>("theme", "dark"));
  const [now, setNow] = useState<Now | null>(null);
  const t = STRINGS[lang];

  useEffect(() => {
    const f = () => { setRoute(routeFromHash()); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  useEffect(() => { store("lang", lang); document.documentElement.lang = lang; }, [lang]);
  useEffect(() => {
    store("theme", theme);
    const mq = window.matchMedia("(prefers-color-scheme: light)");
    const apply = () => { document.documentElement.dataset.theme = theme === "system" ? (mq.matches ? "light" : "dark") : theme; };
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [theme]);
  useEffect(() => {
    const load = () => get<Now>("/api/now").then(setNow).catch(() => {});
    load();
    const id = setInterval(load, 5 * 60 * 1000);
    return () => clearInterval(id);
  }, []);

  const official = { ...FALLBACK_OFFICIAL, ...(now?.official ?? {}) };
  const h2sOk = now?.freshness?.h2s_feed?.last_ok;
  const stale = h2sOk ? Date.now() - new Date(h2sOk).getTime() > 90 * 60 * 1000 : true;
  const active = route === "tonight" ? "forecast" : route === "about" ? "settings" : route;

  return (
    <div className="shell">
      <aside className="sidebar">
        <a className="brand" href="#/forecast">
          <img src="/favicon.svg" alt="" width={40} height={40} />
          <span><strong>Smellcast</strong><small>{t.tagline}</small></span>
        </a>
        <nav aria-label={t.aria_main}>
          <span className="nav-label">{t.menu}</span>
          {NAV.map((r) => (
            <a key={r} href={`#/${r}`} className={active === r ? "active" : ""} aria-current={active === r ? "page" : undefined}>
              <span className="nav-icon"><Icon name={r} size={22} /></span>
              <span className="nav-text">{t[`nav_${r}` as keyof typeof t] as string}</span>
            </a>
          ))}
        </nav>
        <div className="side-foot">
          <a className="now-card" href="#/live">
            <div className="now-head">
              <span>{t.monitors_now}</span>
              <span className={`live-dot${stale ? " stale" : ""}`} title={stale ? t.stale : t.readings} />
            </div>
            {(now?.monitors ?? []).map((m) => {
              const l = levelStyle(m.level);
              return (
                <div className="now-row" key={m.site_id}>
                  <span className="now-swatch" style={{ background: l?.color ?? "#777", color: l?.ink }} aria-hidden="true">{l?.icon ?? "○"}</span>
                  <span className="now-name">{m.name.replace(/ \(.*\)/, "")}</span>
                  <strong>{fmtPpb(m.ppb)}</strong>
                </div>
              );
            })}
            <small>{t.updated} {fmtDateTime(h2sOk, lang)}{now?.demo_mode ? " · DEMO" : ""}</small>
          </a>
          <div className="city-block">
            <Skyline />
            <strong className="city">{t.city}</strong>
          </div>
        </div>
      </aside>

      <div className="content">
        <div className="disclaimer" role="note">
          <Icon name="warn" size={16} />
          <span>
            <strong>{t.disclaimer}</strong>{" "}
            <a href={official.sdapcd_h2s} target="_blank" rel="noreferrer">{t.official_link} ↗</a>
            {" · "}
            <a href={official.sdapcd_alerts_signup} target="_blank" rel="noreferrer">{t.official_signup} ↗</a>
          </span>
          <div className="seg lang" role="group" aria-label={t.language}>
            <button className={lang === "en" ? "on" : ""} onClick={() => setLang("en")}>EN</button>
            <button className={lang === "es" ? "on" : ""} onClick={() => setLang("es")}>ES</button>
          </div>
        </div>
        <main>
          <Suspense fallback={null}>
          {route === "forecast" && <ForecastPage t={t} lang={lang} now={now} />}
          {route === "live" && <MapPage t={t} lang={lang} now={now} />}
          {route === "tonight" && <TonightPage t={t} lang={lang} />}
          {route === "replay" && <ReplayPage t={t} lang={lang} />}
          {route === "accuracy" && <AccuracyPage t={t} lang={lang} />}
          {route === "alerts" && <AlertsPage t={t} lang={lang} official={official} />}
          {route === "settings" && <SettingsPage t={t} lang={lang} setLang={setLang} theme={theme} setTheme={setTheme} official={official} />}
          {route === "evidence" && <EvidencePage t={t} lang={lang} />}
          {route === "about" && <AboutPage t={t} lang={lang} official={official} />}
          </Suspense>
        </main>
        <footer className="foot">
          <span>{t.credits_data}</span>
          <span>{t.disclaimer} <a href={official.sdapcd_h2s} target="_blank" rel="noreferrer">SDAPCD ↗</a></span>
        </footer>
      </div>
    </div>
  );
}
