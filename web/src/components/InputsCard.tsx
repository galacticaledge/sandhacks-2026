import type { Meta } from "../api";
import type { Strings } from "../i18n";

// Model inputs at one forecast hour. Used by the Map page (latest run) and the Replay page (replayed run).
export function InputsCard({ inputs, hour, t, title }: { inputs: Meta["inputs"]; hour: number; t: Strings; title?: string }) {
  const met = inputs.met;
  const flowSrc = inputs.flow_source === "assumed default" ? t.flow_assumed : inputs.flow_source.replace(/^gauge/, t.flow_gauge);
  return (
    <div className="card inputs">
      <h3>{title ?? t.inputs}</h3>
      <dl>
        <dt>{t.wind}</dt><dd>{(met.wind_ms[hour] ?? 0).toFixed(1)} {t.wind_from} {Math.round(met.wind_dir_deg[hour] ?? 0)}°</dd>
        <dt>{t.stability}</dt><dd>{t.class_word} {met.stability[hour]} {"EF".includes(met.stability[hour]) ? t.stab_still : ""}</dd>
        <dt>{t.temp}</dt><dd>{(met.temp_c[hour] ?? 0).toFixed(1)} °C</dd>
        <dt>{t.river_flow}</dt><dd>{inputs.flow_mgd[hour]} MGD <span className="muted">({flowSrc})</span></dd>
        <dt>{t.calibration}</dt><dd>log k {inputs.log_k_now.toFixed(2)} ± {Math.sqrt(inputs.log_k_var).toFixed(2)} <span className="muted">({inputs.filter_obs_used} {t.monitor_hours})</span></dd>
        <dt>{t.ensemble}</dt><dd>{inputs.members} {t.members}</dd>
      </dl>
    </div>
  );
}
