"""USIBWC press releases -> cached PDF/text -> Gemini -> flow_events. Every 6 hours.

Verified 2026-11-14: https://www.ibwc.gov/press-releases/ is one static WordPress page listing every release
(217 items back to 2022), each with a datePublished meta tag and a link to a PDF under /wp-content/uploads/.
Plain httpx with a generic User-Agent gets 200 on the list and the PDFs, so Bright Data is only a fallback.

Cache under data/raw/announcements/: list/<ts>.html, pdf/<name>.pdf (or html/), text/<name>.txt.
Fetched text is cached even when GEMINI_API_KEY is empty, so extraction can run later.
"""
from __future__ import annotations

import html as htmllib
import io
import logging
import os
import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import httpx

from collectors.common import RAW_DIR, brightdata_unlocker, save_raw
from config import USER_AGENT
from db import store

log = logging.getLogger("announcements")
LIST_URL = os.getenv("USIBWC_NEWS_URL", "https://www.ibwc.gov/press-releases/")
SINCE = date(2025, 1, 1)
KEYWORDS = re.compile(r"tijuana|south bay|sbiwtp|san diego|sewage|wastewater|pump|gravity line|collector|"
                      r"diversion|transboundary|stewart|pb1|pbcila|border", re.I)
BASE = RAW_DIR / "announcements"
SEEN = BASE / "seen.txt"  # urls already sent through extraction (not merely fetched)
HOST_OK = {"www.ibwc.gov", "ibwc.gov"}
_POST = re.compile(r'<div class="uabb-blog-posts-col-\d+ uabb-post-wrapper')
_DATE = re.compile(r'itemprop="datePublished" content="(\d{4}-\d{2}-\d{2})"')
_LINK = re.compile(r'<h3 class="uabb-post-heading[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S)


def parse_list(listing: str, base_url: str = LIST_URL) -> list[dict]:
    """Return [{url, title, published}] for every post card on the press-release list page."""
    out = []
    for card in _POST.split(listing)[1:]:
        d, a = _DATE.search(card), _LINK.search(card)
        if not (d and a):
            continue
        title = htmllib.unescape(re.sub(r"<[^>]+>", "", a[2])).strip()
        out.append({"url": urljoin(base_url, htmllib.unescape(a[1])), "title": title,
                    "published": date.fromisoformat(d[1])})
    return out


def select(items: list[dict], since: date = SINCE) -> list[dict]:
    """Keep ibwc.gov-hosted items since `since` whose title matches the flow keywords."""
    return [i for i in items if i["published"] >= since and urlparse(i["url"]).hostname in HOST_OK
            and KEYWORDS.search(i["title"])]


def _text(body: bytes, url: str) -> str:
    if url.lower().endswith(".pdf") or body[:4] == b"%PDF":
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(body)).pages)
    page = re.sub(r"(?is)<(script|style).*?</\1>", " ", body.decode(errors="replace"))
    return re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", page))


def _get(source: str, url: str, ext: str) -> bytes:
    """Plain httpx first (generic UA); Bright Data only if that fails and credentials exist."""
    try:
        r = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True)
        r.raise_for_status()
        store.log_fetch(source, "ok", None, f"plain {r.status_code} {url}")
        return r.content
    except Exception as e:
        log.warning("plain fetch failed for %s (%s); trying Bright Data", url, e)
        store.log_fetch(source, "error", None, f"plain {url}: {e}")
        return brightdata_unlocker(source, url, ext)


def _name(url: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", Path(unquote(urlparse(url).path)).stem)[:150]


def fetch_announcements(limit: int = 100, since: date = SINCE) -> int:
    """Fetch + cache releases; run Gemini only if GEMINI_API_KEY is set. Returns events stored."""
    try:
        listing = _get("announcements_list", LIST_URL, "html")
    except RuntimeError as e:
        log.warning("announcements skipped: %s", e)
        return 0
    (BASE / "list").mkdir(parents=True, exist_ok=True)
    save_raw("announcements/list", listing, "html")
    items = select(parse_list(listing.decode(errors="replace")), since)
    log.info("list page: %d matching releases since %s", len(items), since)
    SEEN.parent.mkdir(parents=True, exist_ok=True)
    seen = set(SEEN.read_text().split()) if SEEN.exists() else set()
    have_key = bool(os.getenv("GEMINI_API_KEY"))
    n = 0
    for it in items[:limit]:
        url, name = it["url"], _name(it["url"])
        is_pdf = url.lower().endswith(".pdf")
        raw_f = BASE / ("pdf" if is_pdf else "html") / f"{name}{'.pdf' if is_pdf else '.html'}"
        txt_f = BASE / "text" / f"{name}.txt"
        try:
            if not txt_f.exists():
                if not raw_f.exists():
                    raw_f.parent.mkdir(parents=True, exist_ok=True)
                    raw_f.write_bytes(_get("announcements", url, "pdf" if is_pdf else "html"))
                    time.sleep(1.0)  # at most 1 request/second per host
                txt_f.parent.mkdir(parents=True, exist_ok=True)
                txt_f.write_text(f"TITLE: {it['title']}\nPUBLISHED: {it['published']}\nURL: {url}\n\n"
                                 + _text(raw_f.read_bytes(), url))
            if not have_key or url in seen:
                continue
            from extract.gemini_events import extract
            for ev in extract(txt_f.read_text(), url):
                store.upsert_flow_event(ev); n += 1
            seen.add(url)
        except Exception:
            log.exception("announcement %s failed", url)
    if not have_key:
        log.info("GEMINI_API_KEY empty: text cached under %s, extraction skipped", BASE / "text")
    SEEN.write_text("\n".join(sorted(seen)))
    return n


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    store.init_db(); print("events", fetch_announcements())
