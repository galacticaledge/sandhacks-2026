"""Evening alerts (spec 7): fixed EN/ES templates, no AI-written text, max 2 alerts per subscriber per night."""
from __future__ import annotations

import logging
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from string import Template

import httpx

from alerts.guidance import GUIDANCE
from alerts.rules import evaluate
from api.runs import load_meta, valid_run_id
from config import SDAPCD_ALERTS_URL, SDAPCD_H2S_URL, TZ
from db import store

log = logging.getLogger("alerts")
UTC = timezone.utc
TPL = Path(__file__).with_name("templates")
WORDS = {
    "en": {"likely": "LIKELY ORANGE", "possible": "POSSIBLE ORANGE",
           "likely_s": "Our experimental forecast says H2S at your place will likely reach the orange level (30 ppb or more) tonight.",
           "possible_s": "Our experimental forecast says H2S at your place could reach the orange level (30 ppb or more) tonight. This is a low-confidence, possible alert.",
           "conf": {"high": "high", "medium": "medium", "low": "low"}},
    "es": {"likely": "PROBABLE NARANJA", "possible": "POSIBLE NARANJA",
           "likely_s": "Nuestro pronóstico experimental indica que el H2S en su zona probablemente alcanzará el nivel naranja (30 ppb o más) esta noche.",
           "possible_s": "Nuestro pronóstico experimental indica que el H2S en su zona podría alcanzar el nivel naranja (30 ppb o más) esta noche. Es una alerta posible, de baja confianza.",
           "conf": {"high": "alta", "medium": "media", "low": "baja"}},
}


def _fmt_time(iso: str, lang: str) -> str:
    t = datetime.fromisoformat(iso).astimezone(TZ)
    return t.strftime("%-I %p") if lang == "en" else t.strftime("%H:%M")


def render(lang: str, place: str, ev: dict, unsubscribe_url: str) -> tuple[str, str]:
    w = WORDS[lang]
    # Likely: guidance for the median's level, so a 200+ ppb median gets the multi-agency text.
    # Possible: always orange. A high estimate alone must not print "SDAPCD will activate review".
    lvl = "review" if ev["kind"] == "likely" and ev.get("level") == "review" else "orange"
    g = GUIDANCE[lang][lvl]
    win = ev.get("orange_window") or ev["window"]
    text = Template((TPL / lang / "alert.txt").read_text()).substitute(
        kind_label=w[ev["kind"]], kind_sentence=w[ev["kind"] + "_s"], place=place,
        window=f"{_fmt_time(win[0], lang)} - {_fmt_time(win[1], lang)}",
        level_label=g["label"], level_range=g["range"], peak_p50=ev["peak_p50"], peak_p90=ev["peak_p90"],
        confidence=w["conf"][ev["confidence"]], expect=g["expect"], actions="\n".join("- " + a for a in g["actions"]),
        official_url=SDAPCD_H2S_URL, official_alerts_url=SDAPCD_ALERTS_URL, unsubscribe_url=unsubscribe_url)
    subject, body = text.split("\n", 1)
    return subject.removeprefix("Subject: ").strip(), body.strip()


def send_email(to: str, subject: str, body: str) -> str:
    """Resend when RESEND_API_KEY is set; otherwise SMTP (Mailpit in docker compose) when SMTP_HOST is set."""
    key, sender, smtp_host = os.getenv("RESEND_API_KEY"), os.getenv("ALERT_FROM_EMAIL"), os.getenv("SMTP_HOST")
    if not sender or not (key or smtp_host):
        log.warning("email not configured; would send to %s: %s", to[:3] + "***", subject)
        return "not_configured"
    if key:
        r = httpx.post("https://api.resend.com/emails", headers={"Authorization": f"Bearer {key}"},
                       json={"from": sender, "to": [to], "subject": subject, "text": body}, timeout=30)
        return "sent" if r.status_code < 300 else f"error {r.status_code}"
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender, to, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(smtp_host, int(os.getenv("SMTP_PORT", "1025")), timeout=30) as s:
            s.send_message(msg)
    except (OSError, smtplib.SMTPException) as e:
        log.error("smtp send failed: %s", e)
        return "error smtp"
    return "sent"


def send_for_hour(hour: int, update: bool = False) -> int:
    issued = datetime.now(TZ).replace(hour=hour, minute=0, second=0, microsecond=0)
    run_id = issued.astimezone(UTC).strftime("%Y%m%dT%H%MZ")
    if not valid_run_id(run_id):
        log.error("alert run %s missing; no alerts sent", run_id)
        return 0
    return send_evening_alerts(load_meta(run_id), update=update)


def send_evening_alerts(meta: dict, update: bool = False) -> int:
    night = datetime.fromisoformat(meta["issued_at"]).astimezone(TZ).date()
    if datetime.fromisoformat(meta["issued_at"]).astimezone(TZ).hour < 12:
        night -= timedelta(days=1)
    vt = [datetime.fromisoformat(t) for t in meta["valid_times"]]
    names = {r["id"]: r["name"] for r in meta["receptors"]}
    sent_tonight: dict[str, list[dict]] = {}
    for a in store.alerts_sent_for(night):
        if a.get("status") == "sent":  # a failed send is retried by the next run and does not use up the cap
            sent_tonight.setdefault(a["subscription_id"], []).append(a)
    base = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    n = 0
    for sub in store.subscriptions():
        s = meta["series"].get(sub["receptor_id"])
        if not s:
            continue
        ev = evaluate(vt, s["p10"], s["p50"], s["p90"])
        prior = sent_tonight.get(sub["id"], [])
        if ev["kind"] == "none" or len(prior) >= 2:
            continue
        if update and (ev["kind"] != "likely" or any(p["kind"] == "likely" for p in prior)):
            continue  # 11 PM only sends a new "likely" that hasn't gone out yet
        if not update and prior:
            continue
        subject, body = render(sub["language"], names[sub["receptor_id"]], ev, f"{base}/api/unsubscribe/{sub['token']}")
        try:
            status = send_email(sub["contact"], subject, body) if sub["channel"] == "email" else "unsupported_channel"
        except Exception as e:  # one bad address must not stop everyone else's alert
            log.exception("alert to subscription %s failed", sub["id"])
            status = f"error {type(e).__name__}"
        store.record_alert(sub["id"], night, meta["run_id"], ev["kind"], status)
        n += status == "sent"
    log.info("alerts for run %s (update=%s): %d", meta["run_id"], update, n)
    return n
