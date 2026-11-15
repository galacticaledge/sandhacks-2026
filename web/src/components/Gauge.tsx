import { LEVELS, fmtPpb } from "../levels";

// Half-dial on the SDAPCD scale. Thresholds 5 / 30 / 200 ppb are spaced evenly (not linear in ppb)
// so a 2 ppb night and a 60 ppb night are both readable. Needle = median, outer tick = high estimate.
const STOPS = [0, 5, 30, 200, 400];
const FRAC = [0, 0.25, 0.5, 0.85, 1];
export function gaugeFrac(v: number) {
  const x = Math.max(0, v);
  for (let i = 1; i < STOPS.length; i++) {
    if (x <= STOPS[i]) return FRAC[i - 1] + ((x - STOPS[i - 1]) / (STOPS[i] - STOPS[i - 1])) * (FRAC[i] - FRAC[i - 1]);
  }
  return 1;
}

const R = 64, CX = 80, CY = 76;
const pt = (f: number, r = R) => {
  const a = Math.PI * (1 - f);
  return [CX + r * Math.cos(a), CY - r * Math.sin(a)];
};
const arc = (f0: number, f1: number) => {
  const [x0, y0] = pt(f0), [x1, y1] = pt(f1);
  return `M ${x0} ${y0} A ${R} ${R} 0 0 1 ${x1} ${y1}`;
};

export function Gauge({ p50, p90, label, compact }: { p50: number; p90: number; label: string; compact?: boolean }) {
  const f = gaugeFrac(p50), f90 = gaugeFrac(p90);
  const [nx, ny] = pt(f, R - 14);
  const [tx0, ty0] = pt(f90, R + 6), [tx1, ty1] = pt(f90, R - 6);
  return (
    <figure className={`gauge${compact ? " gauge-compact" : ""}`} aria-label={`${label}: ${fmtPpb(p50)} ppb (P90 ${fmtPpb(p90)} ppb)`}>
      <svg viewBox="0 0 160 92" aria-hidden="true">
        <path d={arc(0, 1)} stroke="rgba(255,255,255,.08)" strokeWidth={14} fill="none" />
        {LEVELS.map((l, i) => (
          <path key={l.key} d={arc(FRAC[i] + 0.006, FRAC[i + 1] - 0.006)} stroke={l.color} strokeWidth={12} fill="none" opacity={0.9} />
        ))}
        <path d={arc(Math.min(f, f90), f90)} stroke="#fff" strokeOpacity={0.35} strokeWidth={4} fill="none" />
        <line x1={tx0} y1={ty0} x2={tx1} y2={ty1} stroke="#fff" strokeWidth={2.5} strokeLinecap="round" />
        <line className="needle" x1={CX} y1={CY} x2={nx} y2={ny} stroke="#fff" strokeWidth={3.5} strokeLinecap="round" />
        <circle cx={CX} cy={CY} r={6} fill="var(--grape)" stroke="#fff" strokeWidth={2} />
      </svg>
      <figcaption>
        <strong>{fmtPpb(p50)}</strong> <small>ppb</small>
        {!compact && <><span>{label}</span><span>P90 {fmtPpb(p90)} ppb</span></>}
      </figcaption>
    </figure>
  );
}
