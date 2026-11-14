"""USIBWC press releases (Bright Data Web Unlocker) -> text -> Gemini -> flow_events. Every 6 hours.

Status: list-page URL and link pattern TO VERIFY. Each release is fetched once and cached raw.
"""
from __future__ import annotations

import io
import logging
import os
import re
from urllib.parse import urljoin

from collectors.common import RAW_DIR, brightdata_unlocker
from db import store
from extract.gemini_events import extract

log = logging.getLogger("announcements")
LIST_URL = os.getenv("USIBWC_NEWS_URL", "https://www.ibwc.gov/news-releases/")
KEYWORDS = re.compile(r"tijuana|south bay|san diego|sewage|wastewater|pump|collector|diversion", re.I)
SEEN = RAW_DIR / "announcements" / "seen.txt"


def _text(body: bytes, url: str) -> str:
    if url.lower().endswith(".pdf") or body[:4] == b"%PDF":
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(body)).pages)
    html = body.decode(errors="replace")
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", html))


def fetch_announcements(limit: int = 10) -> int:
    try:
        listing = brightdata_unlocker("announcements_list", LIST_URL, "html").decode(errors="replace")
    except RuntimeError as e:
        log.warning("announcements skipped: %s", e)
        return 0
    SEEN.parent.mkdir(parents=True, exist_ok=True)
    seen = set(SEEN.read_text().split()) if SEEN.exists() else set()
    links = []
    for href, label in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', listing, re.S):
        url = urljoin(LIST_URL, href)
        if url not in seen and KEYWORDS.search(label + href) and ("news" in url or url.lower().endswith(".pdf")):
            links.append(url)
    n = 0
    for url in links[:limit]:
        try:
            body = brightdata_unlocker("announcements", url, "pdf" if url.lower().endswith(".pdf") else "html")
            for ev in extract(_text(body, url), url):
                store.upsert_flow_event(ev); n += 1
        except Exception:
            log.exception("announcement %s failed", url)
            continue
        seen.add(url)
    SEEN.write_text("\n".join(sorted(seen)))
    return n


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    store.init_db(); print("events", fetch_announcements())
