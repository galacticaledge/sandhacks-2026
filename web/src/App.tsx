import { lazy, Suspense, useEffect, useState } from "react";
import { get, type Now } from "./api";
import { fmtDateTime } from "./levels";
import { STRINGS, type Lang } from "./i18n";

// Each page is its own chunk, so the map and chart libraries load only where used.
const AboutPage = lazy(() => import("./pages/AboutPage").then((m) => ({ default: m.AboutPage })));
const AccuracyPage = lazy(() => import("./pages/AccuracyPage").then((m) => ({ default: m.AccuracyPage })));
const AlertsPage = lazy(() => import("./pages/AlertsPage").then((m) => ({ default: m.AlertsPage })));
const MapPage = lazy(() => import("./pages/MapPage").then((m) => ({ default: m.MapPage })));
const ReplayPage = lazy(() => import("./pages/ReplayPage").then((m) => ({ default: m.ReplayPage })));
const TonightPage = lazy(() => import("./pages/TonightPage").then((m) => ({ default: m.TonightPage })));

const ROUTES = ["map", "tonight", "replay", "accuracy", "alerts", "about"] as const;
type Route = (typeof ROUTES)[number];
const routeFromHash = (): Route => {
  const r = window.location.hash.replace(/^#\/?/, "") as Route;
  return ROUTES.includes(r) ? r : "map";
};
const FALLBACK_OFFICIAL = {
  sdapcd_h2s: "https://www.sdapcd.org/content/sdapcd/about/tj-river-valley/tjrv-air-quality-monitoring.html",
  sdapcd_alerts_signup: "https://public.govdelivery.com/accounts/CASDCAPCD/subscriber/new",
};

export default function App() {
  const [route, setRoute] = useState<Route>(routeFromHash());
  const [lang, setLang] = useState<Lang>(() => {
    try { return (localStorage.getItem("lang") as Lang) || (navigator.language.startsWith("es") ? "es" : "en"); } catch { return "en"; }
  });
  const [now, setNow] = useState<Now | null>(null);
  const t = STRINGS[lang];

  useEffect(() => {
    const f = () => setRoute(routeFromHash());
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  useEffect(() => {
    try { localStorage.setItem("lang", lang); } catch { /* private mode */ }
    document.documentElement.lang = lang;
  }, [lang]);
  useEffect(() => {
    const load = () => get<Now>("/api/now").then(setNow).catch(() => {});
    load();
    const id = setInterval(load, 5 * 60 * 1000);
    return () => clearInterval(id);
  }, []);

  const official = { ...FALLBACK_OFFICIAL, ...(now?.official ?? {}) };
  const h2sOk = now?.freshness?.h2s_feed?.last_ok;
  const stale = h2sOk ? Date.now() - new Date(h2sOk).getTime() > 90 * 60 * 1000 : true;

  return (
    <div className="app">
      <header className="top">
        <a className="brand" href="#/map">
          <img src="/favicon.svg" alt="" width={28} height={28} />
          <span><strong>Smellcast</strong><small>{t.tagline}</small></span>
        </a>
        <nav aria-label="Main">
          {ROUTES.map((r) => (
            <a key={r} href={`#/${r}`} className={route === r ? "active" : ""} aria-current={route === r ? "page" : undefined}>
              {t[`nav_${r}` as keyof typeof t] as string}
            </a>
          ))}
        </nav>
        <div className="top-right">
          <span className={`chip${stale ? " chip-stale" : ""}`} title={t.readings}>
            ● {t.updated} {fmtDateTime(h2sOk, lang)}
          </span>
          {now?.demo_mode && <span className="chip chip-demo">DEMO</span>}
          <div className="seg" role="group" aria-label="Language">
            <button className={lang === "en" ? "on" : ""} onClick={() => setLang("en")}>EN</button>
            <button className={lang === "es" ? "on" : ""} onClick={() => setLang("es")}>ES</button>
          </div>
        </div>
      </header>
      <div className="disclaimer" role="note">
        <strong>⚠ {t.disclaimer}</strong>{" "}
        <a href={official.sdapcd_h2s} target="_blank" rel="noreferrer">{t.official_link} ↗</a>
        {" · "}
        <a href={official.sdapcd_alerts_signup} target="_blank" rel="noreferrer">{t.official_signup} ↗</a>
      </div>
      <main>
        <Suspense fallback={null}>
        {route === "map" && <MapPage t={t} lang={lang} now={now} />}
        {route === "tonight" && <TonightPage t={t} lang={lang} />}
        {route === "replay" && <ReplayPage t={t} lang={lang} />}
        {route === "accuracy" && <AccuracyPage t={t} lang={lang} />}
        {route === "alerts" && <AlertsPage t={t} lang={lang} official={official} />}
        {route === "about" && <AboutPage t={t} lang={lang} official={official} />}
        </Suspense>
      </main>
      <footer className="foot">
        <span>{t.credits_data}</span>
        <span>{t.disclaimer} <a href={official.sdapcd_h2s} target="_blank" rel="noreferrer">SDAPCD ↗</a></span>
      </footer>
    </div>
  );
}
