import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import type { Series } from "../api";
import { fmtPpb, fmtTime } from "../levels";
import type { Strings } from "../i18n";

export function PointChart({ times, s, observed, t, lang, height = 220 }: {
  times: string[]; s: Series; observed?: (number | null)[]; t: Strings; lang: string; height?: number;
}) {
  const data = times.map((time, i) => ({
    time, label: fmtTime(time, lang), band: [s.p10[i], s.p90[i]] as [number, number], p50: s.p50[i],
    obs: observed?.[i] ?? undefined,
  }));
  const max = Math.max(35, ...s.p90.map((v) => v * 1.1), ...(observed ?? []).map((v) => (v ?? 0) * 1.1));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
        <CartesianGrid stroke="var(--grid)" vertical={false} />
        <XAxis dataKey="label" interval={3} tick={{ fontSize: 11, fill: "var(--muted)" }} tickLine={false} axisLine={{ stroke: "var(--grid)" }} />
        <YAxis domain={[0, Math.ceil(max)]} tick={{ fontSize: 11, fill: "var(--muted)" }} tickLine={false} axisLine={false} unit="" />
        <Tooltip
          formatter={(v: unknown, name: string) => {
            if (Array.isArray(v)) return [`${fmtPpb(v[0])} – ${fmtPpb(v[1])} ppb`, t.band];
            return [`${fmtPpb(v as number)} ppb`, name === "p50" ? t.median : t.observed];
          }}
          contentStyle={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
        />
        <Area dataKey="band" stroke="none" fill="var(--band)" isAnimationActive={false} />
        <Line dataKey="p50" stroke="var(--accent)" strokeWidth={2.5} dot={false} isAnimationActive={false} />
        {observed && <Scatter dataKey="obs" fill="var(--obs)" shape="circle" isAnimationActive={false} />}
        <ReferenceLine y={30} stroke="#f46d43" strokeDasharray="5 4" label={{ value: t.orange_line, position: "insideTopRight", fontSize: 11, fill: "#c2410c" }} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
