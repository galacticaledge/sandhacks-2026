import { useEffect, useState } from "react";
import { get, post, type Receptor } from "../api";
import type { Lang, Strings } from "../i18n";

export function AlertsPage({ t, lang, official }: { t: Strings; lang: Lang; official: Record<string, string> }) {
  const [recs, setRecs] = useState<Receptor[]>([]);
  const [receptor, setReceptor] = useState("nb_nestor");
  const [language, setLanguage] = useState<Lang>(lang);
  const [email, setEmail] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => setLanguage(lang), [lang]);
  useEffect(() => { get<Receptor[]>("/api/receptors").then((r) => setRecs(r.filter((x) => x.kind !== "monitor"))); }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await post("/api/subscribe", { contact: email, channel: "email", language, receptor_id: receptor });
      setMsg({ ok: true, text: t.subscribed }); setEmail("");
    } catch (err) { setMsg({ ok: false, text: String((err as Error).message) }); }
  };
  const group = (k: string) => recs.filter((r) => r.kind === k);

  return (
    <div className="page narrow">
      <h1>{t.alerts_title}</h1>
      <p className="lede">{t.alerts_sub}</p>
      <form className="card form" onSubmit={submit}>
        <label>{t.your_place}
          <select value={receptor} onChange={(e) => setReceptor(e.target.value)}>
            <optgroup label={t.neighborhood}>{group("neighborhood").map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</optgroup>
            <optgroup label={t.school}>{group("school").map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</optgroup>
          </select>
        </label>
        <label>{t.language}
          <select value={language} onChange={(e) => setLanguage(e.target.value as Lang)}>
            <option value="en">English</option><option value="es">Español</option>
          </select>
        </label>
        <label>{t.email}
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
        </label>
        <button className="btn primary">{t.subscribe}</button>
        {msg && <p className={msg.ok ? "ok" : "warn"} role="status">{msg.text}</p>}
        <p className="muted small">{t.privacy}</p>
      </form>
      <p><a href={official.sdapcd_alerts_signup} target="_blank" rel="noreferrer">{t.official_signup} ↗</a></p>
    </div>
  );
}
