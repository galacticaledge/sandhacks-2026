import type { Meta } from "../api";
import type { Strings } from "../i18n";
import { Icon } from "./Icons";
import { PanelHead } from "./PanelHead";

// Model inputs at one forecast hour, as a 2x2 tile grid; calibration details fold away.
// Used by the Live Map page (latest run) and the Replay page (replayed run).
export function InputsCard({ inputs, hour, t, title }: { inputs: Meta["inputs"]; hour: number; t: Strings; title?: string }) {
  const met = inputs.met;
  const flowSrc = inputs.flow_source === "assumed default" ? t.flow_assumed : inputs.flow_source.replace(/^gauge/, t.flow_gauge);
  const stab = met.stability[hour] ?? "";
  const still = "EF".includes(stab) && stab !== "";
  const dir = met.wind_dir_deg[hour] ?? 0;
  return (
    <section className="panel">
      <PanelHead icon="wave" title={title ?? t.inputs} />
      <div className="tiles">
        <div className="tile">
          <span className="tile-k"><span className="wind-arrow" style={{ transform: `rotate(${dir + 180}deg)` }}><Icon name="arrow" size={14} /></span>{t.wind}</span>
          <strong>{(met.wind_ms[hour] ?? 0).toFixed(1)} <small>m/s</small></strong>
          <span className="tile-sub">{t.from_dir} {Math.round(dir)}°</span>
        </div>
        <div className={`tile${still ? " tile-hi" : ""}`}>
          <span className="tile-k"><Icon name="layers" size={14} />{t.stability}</span>
          <strong>{still ? t.air_still : t.air_mixing}</strong>
          <span className="tile-sub">{t.class_word} {stab}{still ? ` · ${t.gas_pools}` : ""}</span>
        </div>
        <div className="tile">
          <span className="tile-k"><Icon name="temp" size={14} />{t.temp}</span>
          <strong>{(met.temp_c[hour] ?? 0).toFixed(1)} <small>°C</small></strong>
        </div>
        <div className="tile">
          <span className="tile-k"><Icon name="wave" size={14} />{t.river_flow}</span>
          <strong>{inputs.flow_mgd[hour]} <small>MGD</small></strong>
          <span className="tile-sub">{flowSrc}</span>
        </div>
      </div>
      <details className="fold">
        <summary>{t.model_details}</summary>
        <dl>
          <dt>{t.calibration}</dt><dd>log k {inputs.log_k_now.toFixed(2)} ± {Math.sqrt(inputs.log_k_var).toFixed(2)}<span className="tile-sub">{inputs.filter_obs_used} {t.monitor_hours}</span></dd>
          <dt>{t.ensemble}</dt><dd>{inputs.members} {t.members}</dd>
        </dl>
      </details>
    </section>
  );
}
