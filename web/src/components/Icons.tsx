// Stroke icons matching the Figma sidebar (home, target, history, bars, bell, gear) plus a few extras.
const P: Record<string, JSX.Element> = {
  forecast: <><path d="M3 10.5 12 3l9 7.5" /><path d="M5 9v12h5v-6h4v6h5V9" /></>,
  live: <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="4" /><path d="M16 12v1.5a2.5 2.5 0 0 0 5 0V12" /></>,
  replay: <><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5" /><path d="M12 7v5l3 3" /></>,
  accuracy: <><path d="M5 20V10" /><path d="M10 20V4" /><path d="M15 20v-8" /><path d="M20 20v-4" /></>,
  evidence: <><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" /><path d="M14 3v6h6" /><path d="M8 13h8" /><path d="M8 17h5" /></>,
  alerts: <><path d="M6 16V11a6 6 0 1 1 12 0v5l2 2H4z" /><path d="M10 21h4" /></>,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></>,
  search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></>,
  chevron: <path d="m6 9 6 6 6-6" />,
  warn: <><path d="M12 3 2 20h20z" /><path d="M12 10v4" /><path d="M12 17.5v.01" /></>,
};

export function Icon({ name, size = 22 }: { name: keyof typeof P | string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{P[name]}</svg>
  );
}

// Line-art skyline from the bottom of the Figma sidebar.
export function Skyline() {
  return (
    <svg viewBox="0 0 300 120" className="skyline" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth={4} strokeLinejoin="miter">
      <path d="M2 118v-16h20v16h26V56h40L90 2l26 54v62h16V82h20v36h10V8h28l18 48h20v62h8V72h24v46h10V94h22v24" />
    </svg>
  );
}
