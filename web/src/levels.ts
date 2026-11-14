import type { Level } from "./api";

// SDAPCD Community H2S Guidance levels. Hues match the map overlay; each level also has a distinct shape icon.
export const LEVELS: { key: Level; min: number; color: string; ink: string; icon: string }[] = [
  { key: "green", min: 0, color: "#1a9850", ink: "#fff", icon: "●" },
  { key: "yellow", min: 5, color: "#fee08b", ink: "#3b3000", icon: "▲" },
  { key: "orange", min: 30, color: "#f46d43", ink: "#2b0d00", icon: "◆" },
  { key: "review", min: 200, color: "#762a83", ink: "#fff", icon: "■" },
];

export function levelOf(ppb: number | null | undefined): Level | null {
  if (ppb == null || Number.isNaN(ppb)) return null;
  let l: Level = "green";
  for (const x of LEVELS) if (ppb >= x.min) l = x.key;
  return l;
}

export const levelStyle = (l: Level | null | undefined) => LEVELS.find((x) => x.key === l) ?? null;

// Monitors can report small negative values (instrument noise around zero); display them as 0.
export const fmtPpb = (v: number | null | undefined) => {
  if (v == null || Number.isNaN(v)) return "–";
  const x = Math.max(0, v);
  const s = x < 10 ? x.toFixed(1) : Math.round(x).toString();
  // never show a number that has reached a level threshold the raw value has not (29.96 -> "29.9", not "30")
  if (+s > x && [5, 30, 200].some((th) => x < th && +s >= th)) return (Math.floor(x * 10) / 10).toFixed(1);
  return s;
};

export function fmtTime(iso: string, lang: string, withDay = false) {
  const d = new Date(iso);
  const opts: Intl.DateTimeFormatOptions = { hour: "numeric", timeZone: "America/Los_Angeles" };
  if (withDay) opts.weekday = "short";
  return d.toLocaleString(lang === "es" ? "es-MX" : "en-US", opts);
}

export function fmtDateTime(iso: string | null | undefined, lang: string) {
  if (!iso) return "–";
  return new Date(iso).toLocaleString(lang === "es" ? "es-MX" : "en-US", {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/Los_Angeles",
  });
}

export function fmtDate(iso: string | null | undefined, lang: string) {
  if (!iso) return "–";
  return new Date(iso).toLocaleDateString(lang === "es" ? "es-MX" : "en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "America/Los_Angeles" });
}

// Clock time with minutes ("5:15 PM"), Pacific.
export function fmtClock(iso: string, lang: string) {
  return new Date(iso).toLocaleTimeString(lang === "es" ? "es-MX" : "en-US", { hour: "numeric", minute: "2-digit", timeZone: "America/Los_Angeles" });
}
