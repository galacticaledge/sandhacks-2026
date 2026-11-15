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

- **Built on `main` at d77e4f5.** Includes everything main added: Evidence page, "Orange tonight?" strip (Live Map), Replay alert preview and markers, Accuracy orange-tonight table, P50/P90 level badges, lazy-loaded pages, translated labels.
- **Sidebar** (floating, rounded 30px, subtle grape-to-graphite gradient so it stands apart from the page):
  - Brand header and a "Menu" label.
  - Nav items with icon tiles. The active item is grape with a lavender icon tile and a lavender edge marker.
  - A "Monitors now" card: the three SDAPCD monitors with level swatch and ppb, last-update time, and a pulsing live dot that turns red if readings are more than 90 minutes old. It links to Live Map.
  - Lavender skyline and "San Diego, CA" at the bottom.
  - Responsive: below 1100px wide it collapses to icons; below 760px it becomes a sticky top icon bar; on screens under 820px tall the skyline is hidden.
- **Disclaimer bar** on every page: experimental forecast, not an official advisory, with links to SDAPCD readings and alert sign-up, plus an EN/ES switch.
- **Forecast** (`#/forecast`, default, matches the frame):
  - Lavender address search.
  - Map card with pill filters. "Risk level" is a dropdown: all / yellow+ / orange+. The kind pills are All areas / Neighborhoods / Schools / Monitors.
  - Hour slider with Median/High-estimate toggle.
  - Detail card: peak median, P90, peak hour, confidence, 24 h chart with P10–P90 band, and the SDAPCD guidance.
  - "Tonight's highest forecasts" list with the level legend.
  - Click a place marker, a list row, any map point, or search an address to change the detail card.
- **Forecast extras:**
  - "Tonight" summary banner: expected peak level, the same orange count as the "Orange tonight?" strip (places only, likely + possible), and the highest place with median, high estimate and time.
  - Detail card shows both the P50 and P90 level badges.
  - Clickable 24-hour strip of the highest median across all places, colored by SDAPCD level. Clicking a bar moves the map to that hour.
  - A median sparkline next to each place in the ranking.
- **Polish:** soft grape/stone background glow, frosted (blurred) pills and slider over the map, cards fade in and lift on hover, all disabled under `prefers-reduced-motion`.
- **Live Map** (`#/live`, old `#/map` redirects here): the previous full map with monitor readings and model inputs.
- **Tonight** full table (`#/tonight`): linked from the Forecast card. **About** (`#/about`): linked from Settings.
- **Settings**: language, theme (Dark default per Figma / Light / System), official links.

## Deviations from the frame

- Sidebar nav text is 17px with icon tiles instead of the frame's 28px labels (requested refinement). The structure, order, grape/lavender active state, skyline and city label are kept.
- The map card keeps the light OpenFreeMap Positron basemap and has a light base color (#E8E6E3), so it never blends into the dark page while tiles load.

- **Text on the search field and Search button is light, not Graphite.** The frame puts #2F2F2F text on a 30%-lavender field and a grape button, which is barely readable on a dark background (fails WCAG contrast). The field and button shapes, fills and borders match the frame.
- A brand block (logo + tagline) sits at the top of the sidebar, where the frame has empty space. The disclaimer bar above the content is required on every page.

- The frame's **"Cities"** pill became **Schools** and **Monitors**. Receptors in `data/receptors.geojson` are neighborhood / school / monitor, with no city field.
- The frame has no Tonight or About nav item. Tonight is a P0 page, so it's reachable from the Forecast page's "Full table" link, and the top of its table is shown on Forecast.
- The ranked list uses tonight's evening (5 PM) run. The map and chart use the latest run. The page says so ("run note").
