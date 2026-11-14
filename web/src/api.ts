export type Level = "green" | "yellow" | "orange" | "review";
export type Series = { p10: number[]; p50: number[]; p90: number[] };
export type Receptor = { id: string; name: string; kind: "neighborhood" | "school" | "monitor"; lat: number; lon: number };

export type Now = {
  monitors: { site_id: string; name: string; lat: number; lon: number; ppb: number | null; level: Level | null; observed_at: string | null }[];
  latest_run_id: string | null;
  latest_run_issued_at: string | null;
  freshness: Record<string, { last_attempt: string; last_ok: string | null; status: string; detail: string }>;
  demo_mode: boolean;
  official: Record<string, string>;
};

export type Meta = {
  run_id: string;
  issued_at: string;
  valid_times: string[];
  grid: { bounds: [number, number][]; shape: [number, number] } | null;
  inputs: {
    met: { times: string[]; wind_ms: number[]; wind_dir_deg: number[]; temp_c: number[]; cloud_frac: number[]; stability: string[] };
    met_hour_sources: string[];
    flow_mgd: number[];
    flow_source: string;
    flow_events: { id: string; event_type: string; quote: string }[];
    log_k_now: number;
    log_k_var: number;
    log_k_median_30d: number;
    filter_obs_used: number;
    members: number;
    shares: Record<string, number>;
  };
  receptors: Receptor[];
  series: Record<string, Series>;
};

export type TonightItem = Receptor & {
  kind: Receptor["kind"];
  alert?: "likely" | "possible" | "none";
  peak_p50?: number;
  peak_p90?: number;
  peak_time?: string;
  level?: Level;
  level_p90?: Level;
  confidence?: "high" | "medium" | "low";
  window?: [string, string];
  guidance: { label: string; range: string; expect: string; actions: string[] };
} & { [k: string]: unknown };

export async function get<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

export async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail ? (typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail)) : `${r.status}`);
  return j as T;
}
