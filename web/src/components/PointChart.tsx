import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import type { Series } from "../api";
import { fmtPpb, fmtTime } from "../levels";
import type { Strings } from "../i18n";

// issued / firstObs: ISO times (must be in `times`) drawn as vertical markers, e.g. the 5 PM issue time on a replay.
export function PointChart({ times, s, observed, t, lang, height = 220, issued, firstObs }: {
  times: string[]; s: Series; observed?: (number | null)[]; t: Strings; lang: string; height?: number; issued?: string; firstObs?: string;
}) {
  const at = (iso?: string) => { const i = iso ? times.findIndex((x) => new Date(x).getTime() === new Date(iso).getTime()) : -1; return i < 0 ? undefined : times[i]; };
  const xi = at(issued), xo = at(firstObs);
  const data = times.map((time, i) => ({
    time, label: fmtTime(time, lang), band: [s.p10[i], s.p90[i]] as [number, number], p50: s.p50[i],
    // monitors report small negative values (instrument noise around zero); plot them at 0, as fmtPpb displays them
    obs: observed?.[i] == null ? undefined : Math.max(0, observed[i] as number),
  }));
  const max = Math.max(35, ...s.p90.map((v) => v * 1.1), ...(observed ?? []).map((v) => (v ?? 0) * 1.1));
  // round ticks shared by every chart (0, 10, 20, 30 ...) so axes line up card to card
  const step = max <= 40 ? 10 : max <= 100 ? 20 : max <= 250 ? 50 : 100;
  const top = Math.ceil(max / step) * step;
  const ticks = Array.from({ length: top / step + 1 }, (_, i) => i * step);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 16, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="var(--grid)" vertical={false} />
        <XAxis dataKey="time" tickFormatter={(v: string) => fmtTime(v, lang)} interval={3} tick={{ fontSize: 11, fill: "var(--muted)" }} tickLine={false} axisLine={{ stroke: "var(--grid)" }} />
        <YAxis width={36} domain={[0, top]} ticks={ticks} allowDataOverflow tick={{ fontSize: 11, fill: "var(--muted)" }} tickLine={false} axisLine={false} unit="" />
        <Tooltip
          formatter={(v: unknown, name: string) => {
            if (Array.isArray(v)) return [`${fmtPpb(v[0])} – ${fmtPpb(v[1])} ppb`, t.band];
            return [`${fmtPpb(v as number)} ppb`, name === "p50" ? t.median : t.observed];
          }}
          labelFormatter={(v) => fmtTime(String(v), lang, true)}
          contentStyle={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
        />
        <Area dataKey="band" stroke="none" fill="var(--band)" isAnimationActive={false} />
        <Line dataKey="p50" stroke="var(--accent)" strokeWidth={2.5} dot={false} isAnimationActive={false} />
        {observed && <Scatter dataKey="obs" fill="var(--obs)" shape="circle" isAnimationActive={false} />}
        {xi && <ReferenceLine x={xi} stroke="var(--ink)" strokeWidth={1.5} label={{ value: `${t.issued_marker} ${fmtTime(xi, lang)}`, position: "insideTopLeft", fontSize: 11, fill: "var(--ink)" }} />}
        {xo && <ReferenceLine x={xo} stroke="var(--obs)" strokeDasharray="2 3" strokeWidth={1.5} label={{ value: t.first_obs_marker, position: "insideTopRight", fontSize: 11, fill: "var(--obs)" }} />}
        <ReferenceLine y={30} stroke="#f97316" strokeWidth={2} strokeDasharray="8 5" ifOverflow="extendDomain" label={{ value: t.orange_line, position: "insideTopRight", fontSize: 12, fontWeight: 600, fill: "#fb923c" }} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
