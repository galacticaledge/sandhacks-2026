import { useEffect, useState } from "react";
import { get } from "../api";
import { fmtDate, fmtDateTime } from "../levels";
import type { Lang, Strings } from "../i18n";

export type WebReport = {
  title: string; source_name: string; url: string; published_at: string | null; quote: string;
  topic?: string; fetched_at?: string | null; via?: string | null;
};

// Fetches a reports URL; a 404 (endpoint not there yet) or an empty list both render the "none collected" line.
export function Reports({ url, t, lang, compact }: { url: string; t: Strings; lang: Lang; compact?: boolean }) {
  const [rows, setRows] = useState<WebReport[] | null>(null);
  useEffect(() => {
    let live = true;
    setRows(null);
    get<WebReport[]>(url).then((r) => live && setRows(Array.isArray(r) ? r : [])).catch(() => live && setRows([]));
    return () => { live = false; };
  }, [url]);
  if (rows === null) return null;
  if (!rows.length) return <p className="muted">{t.reports_none}</p>;
  return (
    <ul className={`reports${compact ? " compact" : ""}`}>
      {rows.map((r, i) => (
        <li key={r.url + i}>
          <blockquote>{r.quote}</blockquote>
          <div className="small">
            <a href={r.url} target="_blank" rel="noreferrer">{r.source_name} ↗</a>
            {r.published_at && <span className="muted"> · {t.reports_published} {fmtDate(r.published_at, lang)}</span>}
            {r.title && <span className="muted"> · {r.title}</span>}
            {r.via?.startsWith("brightdata") && <> <span className="chip chip-via">{t.reports_via.replace("{time}", fmtDateTime(r.fetched_at, lang))}</span></>}
          </div>
        </li>
      ))}
    </ul>
  );
}
