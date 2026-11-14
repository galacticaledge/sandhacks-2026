import type { Lang, Strings } from "../i18n";

export function AboutPage({ t, official }: { t: Strings; lang: Lang; official: Record<string, string> }) {
  return (
    <div className="page narrow prose">
      <h1>{t.about_title}</h1>
      <p><strong>Smellcast</strong> is “a weather forecast for sewer gas”: an experimental, street-level forecast of hydrogen sulfide (H₂S)
        across the South Bay for the next 24 hours, made so neighbors and schools can prepare the evening before a spike.
        <strong> It is not an official advisory.</strong> For official readings, advisories and guidance, use the
        <a href={official.sdapcd_h2s} target="_blank" rel="noreferrer"> San Diego County Air Pollution Control District (SDAPCD)</a>.</p>

      <h2>How it works</h2>
      <ol>
        <li><strong>Release.</strong> The Tijuana River is treated like a smokestack. The main source is the turbulent hotspot at the Saturn Boulevard river crossing, with two smaller sources along the channel. The hourly release rate is <code>E = k · Q^α · e^(β(T−15 °C))</code>, where Q is river flow (MGD) and T is air temperature.</li>
        <li><strong>Spread.</strong> A Gaussian puff model releases a puff from each source every 10 minutes, moves it with the hourly wind, and spreads it according to Pasquill–Gifford stability classes. Calm, clear nights (classes E and F) spread gas slowly, which is when peaks happen. Output is a 50 m grid at 1.5 m above ground.</li>
        <li><strong>Keeping it honest.</strong> A Kalman filter adjusts the release rate every hour using the three SDAPCD monitors, which absorbs things we can't see, like an unannounced pump failure. Offline least-squares calibration fits the other parameters.</li>
        <li><strong>Uncertainty.</strong> 20 ensemble members vary wind direction (±15°), wind speed (±30%) and the release rate. We show the median (P50) and a high estimate (P90). Confidence is high when P90/P50 &lt; 2 and low when it is &gt; 4.</li>
        <li><strong>Announcements.</strong> Google Gemini reads USIBWC press releases and turns them into structured flow events (pump shutdowns, repairs), each with the exact quote it came from. Gemini never produces a concentration.</li>
        <li><strong>Proof.</strong> Every night is replayed from 5 PM using only data available then and scored against the monitors, next to persistence and climatology baselines. See Accuracy.</li>
      </ol>

      <h2>Data sources and credits</h2>
      <ul>
        <li>Live H₂S readings: <strong>UCSD Resilient Shield</strong> and the <strong>San Diego County Air Pollution Control District (SDAPCD)</strong>. Odor complaints and spill events via Resilient Shield.</li>
        <li>Scientific basis: Rico et al., <em>Science</em> (2025), Scripps Institution of Oceanography / Prather lab: an air-trajectory model reproduced observed H₂S only when both meteorology and river flows were represented.</li>
        <li>Weather forecast: National Weather Service (api.weather.gov). Past weather: KNRS (Imperial Beach NOLF) via the Iowa Environmental Mesonet.</li>
        <li>River flow and announcements: U.S. Section, International Boundary and Water Commission (USIBWC), collected with Bright Data.</li>
        <li>Health guidance quoted verbatim from SDAPCD's <a href={official.guidance_en} target="_blank" rel="noreferrer">Community H₂S Guidance</a> (<a href={official.guidance_es} target="_blank" rel="noreferrer">español</a>).</li>
        <li>Basemap © OpenStreetMap contributors © CARTO.</li>
      </ul>

      <h2>Limitations</h2>
      <ul>
        <li>The model is simple physics tuned to three monitors. It cannot see terrain-channelled drainage flows in detail, every source along the river, or unreported events.</li>
        <li>Forecast weather is the NWS gridpoint forecast for Nestor. When the wind forecast is wrong, the plume goes to the wrong place.</li>
        <li>River flow falls back to an assumed constant when the gauge feed is unavailable; every forecast says which it used.</li>
        <li>A low forecast never means a place is safe. Always check official readings.</li>
      </ul>

      <h2>Official links</h2>
      <ul>
        <li><a href={official.sdapcd_h2s} target="_blank" rel="noreferrer">SDAPCD Tijuana River Valley air-quality monitoring (official H₂S readings)</a></li>
        <li><a href={official.sdapcd_alerts_signup} target="_blank" rel="noreferrer">SDAPCD email alerts sign-up</a></li>
        <li><a href="https://www.alertsandiego.org/" target="_blank" rel="noreferrer">Alert San Diego (emergency notifications)</a></li>
      </ul>
    </div>
  );
}
