import { useEffect, useState } from "react";
import { get, type Now } from "./api";
import { fmtDateTime } from "./levels";
import { STRINGS, type Lang } from "./i18n";
import { Icon, Skyline } from "./components/Icons";
import { AboutPage } from "./pages/AboutPage";
import { AccuracyPage } from "./pages/AccuracyPage";
import { AlertsPage } from "./pages/AlertsPage";
import { ForecastPage } from "./pages/ForecastPage";
import { MapPage } from "./pages/MapPage";
import { ReplayPage } from "./pages/ReplayPage";
import { SettingsPage, type Theme } from "./pages/SettingsPage";
import { TonightPage } from "./pages/TonightPage";

// Sidebar order follows the Figma frame. Tonight and About are reachable from Forecast and Settings.
const NAV = ["forecast", "live", "replay", "accuracy", "alerts", "settings"] as const;
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
          <img src="/favicon.svg" alt="" width={34} height={34} />
          <span><strong>Smellcast</strong><small>{t.tagline}</small></span>
        </a>
        <nav aria-label="Main">
          {NAV.map((r) => (
            <a key={r} href={`#/${r}`} className={active === r ? "active" : ""} aria-current={active === r ? "page" : undefined}>
              <Icon name={r} size={36} />
              <span>{t[`nav_${r}` as keyof typeof t] as string}</span>
            </a>
          ))}
        </nav>
        <div className="side-foot">
          <span className={`chip${stale ? " chip-stale" : ""}`} title={t.readings}>● {t.updated} {fmtDateTime(h2sOk, lang)}</span>
          {now?.demo_mode && <span className="chip chip-demo">DEMO</span>}
          <Skyline />
          <strong className="city">{t.city}</strong>
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
          <div className="seg lang" role="group" aria-label="Language">
            <button className={lang === "en" ? "on" : ""} onClick={() => setLang("en")}>EN</button>
            <button className={lang === "es" ? "on" : ""} onClick={() => setLang("es")}>ES</button>
          </div>
        </div>
        <main>
          {route === "forecast" && <ForecastPage t={t} lang={lang} now={now} />}
          {route === "live" && <MapPage t={t} lang={lang} now={now} />}
          {route === "tonight" && <TonightPage t={t} lang={lang} />}
          {route === "replay" && <ReplayPage t={t} lang={lang} />}
          {route === "accuracy" && <AccuracyPage t={t} lang={lang} />}
          {route === "alerts" && <AlertsPage t={t} lang={lang} official={official} />}
          {route === "settings" && <SettingsPage t={t} lang={lang} setLang={setLang} theme={theme} setTheme={setTheme} official={official} />}
          {route === "about" && <AboutPage t={t} lang={lang} official={official} />}
        </main>
        <footer className="foot">
          <span>{t.credits_data}</span>
          <span>{t.disclaimer} <a href={official.sdapcd_h2s} target="_blank" rel="noreferrer">SDAPCD ↗</a></span>
        </footer>
      </div>
    </div>
  );
}
