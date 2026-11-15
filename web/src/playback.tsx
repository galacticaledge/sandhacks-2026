import { useEffect, useState, type Dispatch, type SetStateAction } from "react";
import type { Strings } from "./i18n";

const KEY = "autoplay";
export const autoplayPref = () => { try { return localStorage.getItem(KEY) === "1"; } catch { return false; } };
export const setAutoplayPref = (on: boolean) => { try { localStorage.setItem(KEY, on ? "1" : "0"); } catch { /* private mode */ } };

/** Steps the hour through `n` hours while playing, looping back to the first.
 *  Starts by itself each time `runKey` changes (a new forecast or night loads) when the Autoplay setting is on.
 *  Skips ticks while the tab is hidden. */
export function usePlayback(n: number, setHour: Dispatch<SetStateAction<number>>, runKey: string | null | undefined, ms = 700) {
  const [playing, setPlaying] = useState(false);
  useEffect(() => { setPlaying(!!runKey && autoplayPref()); }, [runKey]);
  useEffect(() => {
    if (!playing || n < 2) return;
    const id = setInterval(() => { if (!document.hidden) setHour((h) => (h + 1) % n); }, ms);
    return () => clearInterval(id);
  }, [playing, n, ms, setHour]);
  return [playing, setPlaying] as const;
}

/** Warm the browser cache with every hour's zones so playback does not stall on the network. */
export function usePrefetchZones(runId: string | null | undefined, n: number, pct: string) {
  useEffect(() => {
    if (!runId) return;
    for (let h = 0; h < n; h++) fetch(`/api/forecast/${runId}/zones/${h}.geojson?pct=${pct}`).catch(() => {});
  }, [runId, n, pct]);
}

export function PlayButton({ playing, setPlaying, t }: { playing: boolean; setPlaying: (p: boolean) => void; t: Strings }) {
  return (
    <button type="button" className="play-btn" onClick={() => setPlaying(!playing)} aria-pressed={playing} aria-label={playing ? t.pause : t.play} title={playing ? t.pause : t.play}>
      {playing ? "❚❚" : "▶"}
    </button>
  );
}
