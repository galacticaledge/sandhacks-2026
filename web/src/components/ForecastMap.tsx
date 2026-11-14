import maplibregl, { type ImageSource, type Map as MLMap, type GeoJSONSource } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef } from "react";
import { fmtPpb, levelStyle, levelOf } from "../levels";

export type MapMonitor = { site_id: string; name: string; lat: number; lon: number; ppb: number | null };
export type MapSource = { id: string; name: string; lat: number; lon: number; main: boolean };

// OpenFreeMap Positron: free, no API key (CARTO raster tiles now require a key).
const STYLE = "https://tiles.openfreemap.org/styles/positron";

export function ForecastMap({ overlayUrl, bounds, monitors, sources, complaints, marker, onPick, height = "100%", label }: {
  overlayUrl: string | null;
  bounds: [number, number][] | null;
  monitors: MapMonitor[];
  sources?: MapSource[];
  complaints?: { lat: number; lon: number }[];
  marker?: { lat: number; lon: number } | null;
  onPick?: (lat: number, lon: number) => void;
  height?: string | number;
  label?: string;
}) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const ready = useRef(false);
  const monMarkers = useRef<Record<string, maplibregl.Marker>>({});
  const pick = useRef<maplibregl.Marker | null>(null);
  const onPickRef = useRef(onPick);
  onPickRef.current = onPick;

  useEffect(() => {
    if (!el.current) return;
    const m = new maplibregl.Map({ container: el.current, style: STYLE, center: [-117.085, 32.567], zoom: 12.3, attributionControl: { compact: true } });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.on("load", () => {
      ready.current = true;
      m.addSource("complaints", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      m.addLayer({ id: "complaints", type: "circle", source: "complaints",
        paint: { "circle-radius": 3, "circle-color": "#1f3b4d", "circle-opacity": 0.55, "circle-stroke-color": "#fff", "circle-stroke-width": 0.8 } });
      m.fire("smellcast:ready");
    });
    m.on("click", (e) => onPickRef.current?.(e.lngLat.lat, e.lngLat.lng));
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
        mk = new maplibregl.Marker({ element: d }).setLngLat([mon.lon, mon.lat]).addTo(m);
        monMarkers.current[mon.site_id] = mk;
      }
      const d = mk.getElement();
      d.style.background = lvl?.color ?? "#ddd";
      d.style.color = lvl?.ink ?? "#333";
      d.title = mon.name;
      d.innerHTML = `<span aria-hidden="true">${lvl?.icon ?? "○"}</span> ${fmtPpb(mon.ppb)}<small>ppb</small>`;
      d.setAttribute("aria-label", `${mon.name}: ${fmtPpb(mon.ppb)} ppb`);
    }
  }, [monitors]);

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

  // picked point
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    pick.current?.remove();
    pick.current = marker ? new maplibregl.Marker({ color: "#1f3b4d" }).setLngLat([marker.lon, marker.lat]).addTo(m) : null;
  }, [marker]);

  return (
    <div className="map-wrap" style={{ height }}>
      <div ref={el} className="map" />
      {label && <div className="map-label">{label}</div>}
    </div>
  );
}
