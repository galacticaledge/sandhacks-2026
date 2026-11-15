import type { Level } from "../api";
import { LEVELS } from "../levels";
import type { Strings } from "../i18n";

const SHORT: Record<Level, string> = { green: "<5", yellow: "5–30", orange: "30+", review: "200+ ppb" };

// Key for the predicted concentration zones (same swatches as the polygons on every map).
// `measured` adds the sample measured-monitor pin; `className` places it (map overlay or inline row).
export function ZoneLegend({ t, pct = "p50", measured, forecastPin, className = "" }: { t: Strings; pct?: "p50" | "p90"; measured?: boolean; forecastPin?: boolean; className?: string }) {
  return (
    <div className={`zone-legend ${className}`}>
      <span className="zl-title">{pct === "p50" ? t.zones_title_p50 : t.zones_title_p90}:</span>
      {LEVELS.map((l) => (
        <span key={l.key}>
          <i className={`zl-sw zl-${l.key}`} aria-hidden="true" />
          <span className="zl-long">{t[`range_${l.key}` as keyof Strings] as string}</span>
          <span className="zl-short">{SHORT[l.key]}</span>
        </span>
      ))}
      {measured && (
        <span className="zl-meas">
          <span className="mon mon-meas inline" aria-hidden="true"><i style={{ background: LEVELS[0].color }} /><b>0.7</b></span>{t.key_measured}
        </span>
      )}
      {forecastPin && (
        <span className="zl-meas">
          <span className="mon mon-fc inline" aria-hidden="true"><i style={{ background: LEVELS[0].color }} /><b>≈0.4</b></span>{t.key_forecast_pin}
        </span>
      )}
    </div>
  );
}
