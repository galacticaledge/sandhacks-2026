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
- **Disclaimer bar** on every page (44px tall at all widths, from 320px phones up; the warning text is never truncated: below 1100px it uses a short form, below 520px the links shorten to "SDAPCD" and "Alerts", below 370px the EN/ES switch moves to Settings only): experimental forecast, not an official advisory, with links to SDAPCD readings and alert sign-up, plus an EN/ES switch.
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
- **Tonight card extras:** a half-dial gauge on the SDAPCD scale (thresholds 5/30/200 ppb spaced evenly, so it is not linear in ppb): the needle is the highest place's median and the outer tick is its P90. Condition chips for the selected hour: wind arrow (direction the wind blows toward) and speed, temperature, still versus mixing air (stability classes E/F count as still), and river flow.
- **Map legend** overlay (SDAPCD ranges) at the bottom-left of the map. It is hidden on phones.
- **Search field:** lighter, smaller placeholder (400 weight, 45% opacity, 16px).
- **Polish:** soft grape/stone background glow, frosted (blurred) pills and slider over the map, cards fade in and lift on hover, all disabled under `prefers-reduced-motion`.
- **Live Map** (`#/live`, old `#/map` redirects here): full map with the same level legend overlay as Forecast. The side panel is split into quiet sections with small uppercase headers:
  - Search (same style as Forecast).
  - Spot forecast: P50/P90 badges with values, then the chart.
  - Monitors: shape-coded level swatch, name with time underneath, big ppb value.
  - Conditions at the slider hour: a 2x2 grid of wind, air (still or mixing), temperature and river flow. Calibration and ensemble sit under a "Model details" fold.
  - Map key fold: river sources, complaints and the full SDAPCD legend.
  - The conditions card (`InputsCard`) is shared with Replay.
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

## Replay page layout

- One controls bar: night picker and the "replayed with observed weather" note on the same row.
- Alert section: heading, then "Show the alert for" directly underneath, then the email preview.
- Monitor charts: 2-column grid at desktop widths (third monitor wraps to the next row), 1 column below 900px. Each card has aligned rows (title, one-line comparison, 280px chart, key).
- All charts share round y-axis ticks (0, 10, 20, 30, ...) and a fixed axis width, so axes line up card to card. Small negative monitor readings (instrument noise) are plotted at 0, matching how they are displayed elsewhere.
- The 30 ppb line is a 2px dashed orange line with a bold label, and it appears in each card's key.

## Type scale

Defined once at the end of `web/src/styles.css` (it overrides earlier sizes):

| Role | Size | Weight | Notes |
|---|---|---|---|
| Page title (`.page > h1`, Forecast hero title) | 28px | 600 | uppercase, +0.02em tracking |
| Section heading (`h2`) | 17px | 600 | |
| Card title (`h3`, card `h2`, panel headers, legend title) | 15px | 600 | |
| Body (`p`, `li`, `td`, lede, form labels) | 14px | 400 | |
| Supporting (`.small`, captions, keys, table headers, chips, badges, field labels, sidebar card) | 12px | 400 | |

Data numbers (stat tiles, monitor ppb, gauge value) and navigation keep their own sizes.

## Dropdowns

`components/Select.tsx`: a listbox that always opens directly below its button (max 320px, scrolls, and scrolls the page into view on small screens). Keyboard: arrows, Home/End, Enter/Space, Escape, type-ahead. Used for Replay's "Night of" and "Show the alert for". Classes use the `dd-` prefix (`.sel` is the selected map marker).

## Live Map (current layout)

- **Summary** (`TonightStrip`), three sections: (1) "Orange tonight?" with a big Yes/No and the likely/possible count; (2) highest forecast place with level, median ppb, time and P90; (3) actions (Tonight list, past spike) and the "low is not safe" note. Same rules as before: places only, worst level first.
- **Map card**: the map sits inset with a "Forecast · time · P50/P90" tag. The basemap is faded (fill 0.55, lines 0.5, labels 0.7) on every map so the forecast and readings stand out. Zoom buttons are small, dark and tucked into the corner.
- **Controls under the map, two layers**: (1) playback (round play button, time, slider, P50/P90); (2) key: shaded forecast ramp with 0/5/30/200 ppb, the measured-pin sample, river sources and complaints.
- **Measured vs forecast markers** (`ForecastMap monitorKind`):
  - "measured" (default): solid graphite pin with a white border and pointer, a level-shaped dot and the ppb.
  - "forecast": translucent lavender, dashed grape border, italic, "≈" before the value. The Replay "Forecast (5 PM)" map uses this.
- **Right panel**, same order: Any location (search + spot forecast), Monitors (measured), Conditions. Every card shares `PanelHead`: a Stone Brown icon tile, a 15px title and Grey Olive meta text. Tiles use a stone tint, and lavender stays for interactive and highlighted states.

## Forecast page (current layout)

- **Summary card, three sections**: (1) Tonight: "Expected peak level" with the level badge and the orange line, nothing else; (2) Highest forecast: compact gauge (median needle, P90 tick) beside stacked facts for place, peak hour and high estimate, each shown once; (3) Hour by hour: the clickable strip, then the condition chips for the selected hour (wind, temperature, still/mixing air, river flow) and a one-line explanation. On tablets section 3 drops to a full-width row; on phones all three stack.
- **Map toolbar**: the address search and the filters (risk level, area type) are a header strip inside the map card, directly above the map, instead of a separate bar between the summary and the map. On phones the search is full width and the filter pills scroll sideways.
