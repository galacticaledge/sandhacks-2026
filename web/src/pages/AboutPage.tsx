import type { Lang, Strings } from "../i18n";

export function AboutPage({ t, lang, official }: { t: Strings; lang: Lang; official: Record<string, string> }) {
  const L = t.ab_how_lead, B = t.ab_how_body;
  const [g1, g2] = lang === "es" ? [official.guidance_es, official.guidance_en] : [official.guidance_en, official.guidance_es];
  return (
    <div className="page narrow prose">
      <h1>{t.about_title}</h1>
      <p><strong>Smellcast</strong> {t.ab_p1a}
        <strong> {t.ab_p1b}</strong> {t.ab_p1c}
        <a href={official.sdapcd_h2s} target="_blank" rel="noreferrer"> {t.ab_sdapcd}</a>.</p>

      <h2>{t.ab_how}</h2>
      <ol>
        <li><strong>{L[0]}</strong> {B[0]} <code>E = k · Q^α · e^(β(T−15 °C))</code>{t.ab_release_end}</li>
        {[1, 2, 3, 4, 5].map((i) => <li key={i}><strong>{L[i]}</strong> {B[i]}</li>)}
      </ol>

      <h2>{t.ab_src}</h2>
      <ul>
        <li>{t.ab_src1a} <strong>UCSD Resilient Shield</strong> {t.ab_and} <strong>{t.ab_sdapcd}</strong>. {t.ab_src1b}</li>
        <li>{t.ab_src2a} <em>Science</em> {t.ab_src2b}</li>
        <li>{t.ab_src3}</li>
        <li>{t.ab_src4}</li>
        <li>{t.ab_src5a} <a href={g1} target="_blank" rel="noreferrer">{t.ab_guidance}</a> (<a href={g2} target="_blank" rel="noreferrer">{t.ab_other_lang}</a>).</li>
        <li>{t.ab_src6}</li>
      </ul>

      <h2>{t.ab_limits_h}</h2>
      <ul>{t.ab_limits.map((x) => <li key={x}>{x}</li>)}</ul>

      <h2>{t.ab_links_h}</h2>
      <ul>
        <li><a href={official.sdapcd_h2s} target="_blank" rel="noreferrer">{t.ab_link1}</a></li>
        <li><a href={official.sdapcd_alerts_signup} target="_blank" rel="noreferrer">{t.ab_link2}</a></li>
        <li><a href="https://www.alertsandiego.org/" target="_blank" rel="noreferrer">{t.ab_link3}</a></li>
      </ul>
    </div>
  );
}
