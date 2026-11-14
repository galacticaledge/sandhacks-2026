# UI design

Source: Figma file "Test-Website-Wireframes", page **SanD Hacks UI**: frame **Smellcast Forecast** (node 146:142) and the palette image (node 153:237). Pulled with the Figma REST API (`FIGMA_TOKEN` in `.env`, read-only).

## Palette (`web/src/styles.css`)

| Name | Hex | Use |
|---|---|---|
| Vintage Grape | `#5D4A72` | active nav item, primary buttons, selected pill |
| Lavender (from frame) | `#A787CB` | address search field, Risk-level pill, borders/focus, chart median line (dark) |
| Graphite | `#2F2F2F` | sidebar, pill bar, slider bar, dark background family |
| White | `#FFFFFF` | text on dark |
| Grey Olive | `#8F857D` | basis for muted text |
| Stone Brown | `#5C5552` | basis for borders/panels |

The forecast level colors are **not** themed. They stay the SDAPCD green/yellow/orange/purple from `levels.ts`, each with its own shape icon. Font: Poppins (Google Fonts), as in the frame.

## Layout

- **Sidebar** (floating, rounded 30px): Forecast, Live Map, Replay, Accuracy, Alerts, Settings, plus the skyline and "San Diego, CA" at the bottom. Data-freshness chip and DEMO badge sit above the skyline. Below 1100px it collapses to icons. Below 760px it becomes a sticky top icon bar.
- **Disclaimer bar** on every page: experimental forecast, not an official advisory, with links to SDAPCD readings and alert sign-up, plus an EN/ES switch.
- **Forecast** (`#/forecast`, default, matches the frame):
  - Lavender address search.
  - Map card with pill filters. "Risk level" is a dropdown: all / yellow+ / orange+. The kind pills are All areas / Neighborhoods / Schools / Monitors.
  - Hour slider with Median/High-estimate toggle.
  - Detail card: peak median, P90, peak hour, confidence, 24 h chart with P10–P90 band, and the SDAPCD guidance.
  - "Tonight's highest forecasts" list with the level legend.
  - Click a place marker, a list row, any map point, or search an address to change the detail card.
- **Live Map** (`#/live`, old `#/map` redirects here): the previous full map with monitor readings and model inputs.
- **Tonight** full table (`#/tonight`): linked from the Forecast card. **About** (`#/about`): linked from Settings.
- **Settings**: language, theme (Dark default per Figma / Light / System), official links.

## Deviations from the frame

- **Text on the search field and Search button is light, not Graphite.** The frame puts #2F2F2F text on a 30%-lavender field and a grape button, which is barely readable on a dark background (fails WCAG contrast). The field and button shapes, fills and borders match the frame.
- A brand block (logo + tagline) sits at the top of the sidebar, where the frame has empty space. The disclaimer bar above the content is required on every page.

- The frame's **"Cities"** pill became **Schools** and **Monitors**. Receptors in `data/receptors.geojson` are neighborhood / school / monitor, with no city field.
- The frame has no Tonight or About nav item. Tonight is a P0 page, so it's reachable from the Forecast page's "Full table" link, and the top of its table is shown on Forecast.
- The ranked list uses tonight's evening (5 PM) run. The map and chart use the latest run. The page says so ("run note").
