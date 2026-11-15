import { useState } from "react";
import type { Lang, Strings } from "../i18n";
import { autoplayPref, setAutoplayPref } from "../playback";

export type Theme = "dark" | "light" | "system";

export function SettingsPage({ t, lang, setLang, theme, setTheme, official }: {
  t: Strings; lang: Lang; setLang: (l: Lang) => void; theme: Theme; setTheme: (x: Theme) => void; official: Record<string, string>;
}) {
  const themes: [Theme, string][] = [["dark", t.theme_dark], ["light", t.theme_light], ["system", t.theme_system]];
  const [autoplay, setAutoplay] = useState(autoplayPref);
  const pickAutoplay = (on: boolean) => { setAutoplayPref(on); setAutoplay(on); };
  return (
    <div className="page narrow">
      <h1>{t.settings_title}</h1>
      <div className="card-xl form">
        <div className="setting">
          <span>{t.language}</span>
          <div className="seg" role="group" aria-label={t.language}>
            <button className={lang === "en" ? "on" : ""} onClick={() => setLang("en")}>English</button>
            <button className={lang === "es" ? "on" : ""} onClick={() => setLang("es")}>Español</button>
          </div>
        </div>
        <div className="setting">
          <span>{t.theme}</span>
          <div className="seg" role="group" aria-label={t.theme}>
            {themes.map(([k, label]) => <button key={k} className={theme === k ? "on" : ""} onClick={() => setTheme(k)}>{label}</button>)}
          </div>
        </div>
        <div className="setting">
          <span>{t.autoplay}<br /><span className="muted small">{t.autoplay_sub}</span></span>
          <div className="seg" role="group" aria-label={t.autoplay}>
            <button className={autoplay ? "on" : ""} aria-pressed={autoplay} onClick={() => pickAutoplay(true)}>{t.autoplay_on}</button>
            <button className={!autoplay ? "on" : ""} aria-pressed={!autoplay} onClick={() => pickAutoplay(false)}>{t.autoplay_off}</button>
          </div>
        </div>
      </div>
      <div className="card-xl links">
        <a href="#/about">{t.about_link} →</a>
        <a href={official.sdapcd_h2s} target="_blank" rel="noreferrer">{t.official_link} ↗</a>
        <a href={official.sdapcd_alerts_signup} target="_blank" rel="noreferrer">{t.official_signup} ↗</a>
      </div>
    </div>
  );
}
