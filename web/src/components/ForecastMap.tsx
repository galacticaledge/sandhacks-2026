import maplibregl, { type ImageSource, type Map as MLMap, type GeoJSONSource } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef } from "react";
import type { Level } from "../api";
import { fmtPpb, levelStyle, levelOf } from "../levels";

export type MapMonitor = { site_id: string; name: string; lat: number; lon: number; ppb: number | null };
export type MapSource = { id: string; name: string; lat: number; lon: number; main: boolean };
export type MapPlace = { id: string; name: string; lat: number; lon: number; level: Level | null; ppb: number | null };

// OpenFreeMap Positron: free, no API key (CARTO raster tiles now require a key).
const STYLE = "https://tiles.openfreemap.org/styles/positron";

export function ForecastMap({ overlayUrl, zonesUrl, bounds, monitors, sources, complaints, marker, onPick, places, selectedId, onPlace, height = "100%", label, monitorKind = "measured" }: {
  overlayUrl: string | null;
  // predicted concentration zones (GeoJSON from /api/forecast/{run}/zones/{h}.geojson); drawn as translucent polygons
  zonesUrl?: string | null;
  bounds: [number, number][] | null;
  monitors: MapMonitor[];
  sources?: MapSource[];
  complaints?: { lat: number; lon: number }[];
  marker?: { lat: number; lon: number } | null;
  onPick?: (lat: number, lon: number) => void;
  places?: MapPlace[];
  selectedId?: string | null;
  onPlace?: (id: string) => void;
  height?: string | number;
  label?: string;
  // "measured": real monitor readings (solid dark pin). "forecast": model values at monitor sites (dashed, "≈").
  monitorKind?: "measured" | "forecast";
}) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const ready = useRef(false);
  const monMarkers = useRef<Record<string, maplibregl.Marker>>({});
  const pick = useRef<maplibregl.Marker | null>(null);
  const onPickRef = useRef(onPick);
  onPickRef.current = onPick;
  const onPlaceRef = useRef(onPlace);
  onPlaceRef.current = onPlace;

  useEffect(() => {
    if (!el.current) return;
    const m = new maplibregl.Map({
      container: el.current, style: STYLE, center: [-117.085, 32.567], zoom: 12.3, attributionControl: { compact: true },
      // keep the view on San Diego County (the county's extent plus a little margin), never the whole world
      maxBounds: [[-117.75, 32.42], [-115.95, 33.6]], minZoom: 9,
    });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.on("load", () => {
      // basemap is context, not data: fade it so the forecast overlay and readings stand out
      for (const l of m.getStyle().layers ?? []) {
        const set = (k: string, v: number) => { try { m.setPaintProperty(l.id, k, v); } catch { /* not supported for this layer */ } };
        if (l.type === "fill") set("fill-opacity", 0.55);
        else if (l.type === "line") set("line-opacity", 0.5);
        else if (l.type === "symbol") { set("text-opacity", 0.7); set("icon-opacity", 0.5); }
      }
      // keep the attribution as the small (i) button; it still opens on click
      el.current?.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show");
      ready.current = true;
      const empty = { type: "FeatureCollection" as const, features: [] };
      m.addSource("zones", { type: "geojson", data: empty });
      const byLevel = (g: string, y: string, o: string, r: string) =>
        ["match", ["get", "level"], "green", g, "yellow", y, "orange", o, "review", r, g] as unknown as maplibregl.ExpressionSpecification;
      m.addLayer({ id: "zones-fill", type: "fill", source: "zones",
        paint: { "fill-color": byLevel("#1a9850", "#fee08b", "#f46d43", "#762a83"), "fill-opacity": ["match", ["get", "level"], "green", 0.16, "yellow", 0.34, "orange", 0.42, "review", 0.5, 0.2] } });
      m.addLayer({ id: "zones-line", type: "line", source: "zones",
        paint: { "line-color": byLevel("#15803d", "#ca8a04", "#c2410c", "#5b2167"), "line-width": ["match", ["get", "level"], "green", 0.8, 1.4], "line-opacity": 0.85 } });
      // everything outside San Diego County is washed out; the county line is drawn thin and quiet
      m.addSource("county-mask", { type: "geojson", data: empty });
      m.addLayer({ id: "county-mask", type: "fill", source: "county-mask", paint: { "fill-color": "#3a3533", "fill-opacity": 0.55 } });
      m.addLayer({ id: "county-line", type: "line", source: "county-mask",
        paint: { "line-color": "#5c5552", "line-width": 1.6, "line-dasharray": [3, 2], "line-opacity": 0.9 } });
      fetch("/sd-county.geojson").then((r) => r.json()).then((fc) => {
        const g = fc.features?.[0]?.geometry;
        const holes: number[][][] = g?.type === "Polygon" ? g.coordinates : g?.type === "MultiPolygon" ? g.coordinates.map((p: number[][][]) => p[0]) : [];
        const world = [[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]];
        (m.getSource("county-mask") as GeoJSONSource | undefined)?.setData({
          type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [world, ...holes] },
        });
      }).catch(() => { /* map still works without the mask */ });
      m.addSource("complaints", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      m.addLayer({ id: "complaints", type: "circle", source: "complaints",
        paint: { "circle-radius": 3, "circle-color": "#5d4a72", "circle-opacity": 0.55, "circle-stroke-color": "#fff", "circle-stroke-width": 0.8 } });
      m.addSource("places", { type: "geojson", data: empty });
      m.addLayer({ id: "places-dot", type: "circle", source: "places",
        paint: { "circle-radius": ["case", ["get", "sel"], 7.5, 5.5], "circle-color": "#ffffff",
          "circle-stroke-color": ["case", ["get", "sel"], "#5d4a72", ["get", "color"]], "circle-stroke-width": ["case", ["get", "sel"], 4, 2.5] } });
      m.addLayer({ id: "places-label", type: "symbol", source: "places",
        layout: { "text-field": ["get", "name"], "text-font": ["Noto Sans Regular"], "text-size": ["case", ["get", "sel"], 13, 11],
          "text-offset": [0, 0.9], "text-anchor": "top", "text-optional": true, "text-max-width": 9 },
        paint: { "text-color": ["case", ["get", "sel"], "#3b2d4d", "#3a3532"], "text-halo-color": "rgba(255,255,255,0.9)", "text-halo-width": 1.4 } });
      m.on("mouseenter", "places-dot", () => { m.getCanvas().style.cursor = "pointer"; });
      m.on("mouseleave", "places-dot", () => { m.getCanvas().style.cursor = ""; });
      m.fire("smellcast:ready");
    });
    m.on("click", (e) => {
      const hit = ready.current && m.getLayer("places-dot")
        ? m.queryRenderedFeatures([[e.point.x - 6, e.point.y - 6], [e.point.x + 6, e.point.y + 6]], { layers: ["places-dot"] })[0] : undefined;
      if (hit && onPlaceRef.current) onPlaceRef.current(String(hit.properties?.id));
      else onPickRef.current?.(e.lngLat.lat, e.lngLat.lng);
    });
    map.current = m;
    return () => { m.remove(); map.current = null; ready.current = false; };
  }, []);

  // forecast overlay
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const apply = () => {
      if (!overlayUrl || !bounds) {
        if (m.getLayer("fc")) m.setLayoutProperty("fc", "visibility", "none");
        return;
      }
      const coords = bounds as unknown as [[number, number], [number, number], [number, number], [number, number]];
      const src = m.getSource("fc") as ImageSource | undefined;
      if (src) src.updateImage({ url: overlayUrl, coordinates: coords });
      else {
        m.addSource("fc", { type: "image", url: overlayUrl, coordinates: coords });
        m.addLayer({ id: "fc", type: "raster", source: "fc", paint: { "raster-opacity": 0.9, "raster-fade-duration": 0, "raster-resampling": "linear" } },
          m.getLayer("complaints") ? "complaints" : undefined);
      }
      m.setLayoutProperty("fc", "visibility", "visible");
    };
    if (ready.current) apply(); else m.once("smellcast:ready", apply);
  }, [overlayUrl, bounds]);

  // complaints
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const apply = () => (m.getSource("complaints") as GeoJSONSource | undefined)?.setData({
      type: "FeatureCollection",
      features: (complaints ?? []).map((c) => ({ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [c.lon, c.lat] } })),
    });
    if (ready.current) apply(); else m.once("smellcast:ready", apply);
  }, [complaints]);

  // monitors
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    for (const mon of monitors) {
      const lvl = levelStyle(levelOf(mon.ppb));
      let mk = monMarkers.current[mon.site_id];
      if (!mk) {
        const d = document.createElement("div");
        d.className = "mon";
        // pin tip on the monitor's exact spot, body above it, so it doesn't cover nearby place markers
        mk = new maplibregl.Marker({ element: d, anchor: "bottom", offset: [0, -6] }).setLngLat([mon.lon, mon.lat]).addTo(m);
        monMarkers.current[mon.site_id] = mk;
      }
      const d = mk.getElement();
      const fc = monitorKind === "forecast";
      d.classList.remove("mon-fc", "mon-meas");
      d.classList.add("mon", fc ? "mon-fc" : "mon-meas");
      d.title = mon.name;
      d.innerHTML = `<i style="background:${lvl?.color ?? "#999"};color:${lvl?.ink ?? "#333"}" aria-hidden="true">${lvl?.icon ?? "○"}</i>`
        + `<b>${fc ? "≈" : ""}${fmtPpb(mon.ppb)}</b><small>ppb</small>`;
      d.setAttribute("aria-label", `${mon.name}: ${fc ? "forecast" : "measured"} ${fmtPpb(mon.ppb)} ppb`);
    }
  }, [monitors, monitorKind]);

  // river sources (static)
  useEffect(() => {
    const m = map.current;
    if (!m || !sources) return;
    const made = sources.map((s) => {
      const d = document.createElement("div");
      d.className = s.main ? "src src-main" : "src";
      d.title = s.name;
      d.innerHTML = s.main ? "<span>☣</span>" : "";
      return new maplibregl.Marker({ element: d }).setLngLat([s.lon, s.lat]).addTo(m);
    });
    return () => made.forEach((x) => x.remove());
  }, [sources]);

  // neighborhoods / schools: small labelled points on the map itself, so the zones stay the main thing
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const apply = () => (m.getSource("places") as GeoJSONSource | undefined)?.setData({
      type: "FeatureCollection",
      features: (places ?? []).map((p) => ({ type: "Feature", properties: { id: p.id, name: p.name, sel: p.id === selectedId, color: levelStyle(p.level)?.color ?? "#8f857d" },
        geometry: { type: "Point", coordinates: [p.lon, p.lat] } })),
    });
    if (ready.current) apply(); else m.once("smellcast:ready", apply);
  }, [places, selectedId]);

  // predicted concentration zones
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    let live = true;
    const apply = () => {
      const src = m.getSource("zones") as GeoJSONSource | undefined;
      if (!zonesUrl) { src?.setData({ type: "FeatureCollection", features: [] }); return; }
      fetch(zonesUrl).then((r) => (r.ok ? r.json() : null)).then((fc) => { if (live && fc) (m.getSource("zones") as GeoJSONSource | undefined)?.setData(fc); }).catch(() => {});
    };
    if (ready.current) apply(); else m.once("smellcast:ready", apply);
    return () => { live = false; };
  }, [zonesUrl]);

  // picked point
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    pick.current?.remove();
    pick.current = marker ? new maplibregl.Marker({ color: "#5d4a72" }).setLngLat([marker.lon, marker.lat]).addTo(m) : null;
    if (marker && !m.getBounds().contains([marker.lon, marker.lat])) m.easeTo({ center: [marker.lon, marker.lat], duration: 600 });
  }, [marker]);

  return (
    <div className="map-wrap" style={{ height }}>
      <div ref={el} className="map" />
      {label && <div className="map-label">{label}</div>}
    </div>
  );
}
