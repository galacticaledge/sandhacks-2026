import { levelOf, levelStyle } from "../levels";

// Tiny median trend line, colored by the level of its peak.
export function Spark({ values, width = 64, height = 22 }: { values: number[]; width?: number; height?: number }) {
  if (!values.length) return null;
  const max = Math.max(1, ...values);
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * width},${height - 2 - (Math.max(0, v) / max) * (height - 4)}`).join(" ");
  const color = levelStyle(levelOf(Math.max(...values)))?.color ?? "#999";
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="spark" aria-hidden="true">
      <polyline points={`0,${height} ${pts} ${width},${height}`} fill={color} opacity={0.18} stroke="none" />
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.8} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}
