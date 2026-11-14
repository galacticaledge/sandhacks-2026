"""What the web reported that night: public news quotes about Tijuana River odor / H2S, via Bright Data.

Pipeline (every network request goes through Bright Data Web Unlocker, REST API, zone BRIGHTDATA_UNLOCKER_ZONE):
  1. search   each allowed news site's own public search for the date window        via brightdata_unlocker
  2. fetch    each candidate article page                                           via brightdata_unlocker
  3. extract  title, publication date (meta tags / JSON-LD, in code) and paragraph text
  4. select   Gemini (JSON mode, pydantic) proposes verbatim sentences + a topic; it writes nothing itself
  5. verify   in code: the sentence must appear verbatim in the article text, else it is dropped
  6. store    one row per article in web_reports

Why site search and not Google: the account has no SERP API zone and the API token is not allowed to create one
(POST /zone -> 403, checked 2026-11-14). Google and Bing robots.txt disallow /search, so we do not send search-engine
URLs through the Unlocker zone. Sites are listed in SITES with the robots.txt result that allowed them.

Rules: public logged-out pages only; at most 1 request/second per site (slower where robots.txt asks); every raw
response cached under data/raw/web_reports/ with its fetch time; a cached URL is never refetched (search pages for
windows that are still open are refetched after SEARCH_TTL so --since 7 stays live).

Manual run only (not in the scheduler, so spend stays under human control):
  python -m collectors.web_reports --since 7
  python -m collectors.web_reports --from 2026-04-17 --to 2026-04-22
"""
from __future__ import annotations

import argparse
import hashlib
import html as htmllib
import json
import logging
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from urllib.parse import quote_plus, urlparse

import httpx
from pydantic import BaseModel, Field, ValidationError

from config import RAW_DIR, TZ
from db import store

log = logging.getLogger("web_reports")
UTC = timezone.utc
BASE = RAW_DIR / "web_reports"
INDEX = BASE / "index.jsonl"        # one line per cached response: url, file, fetched_at, via
REQUESTS = BASE / "requests.jsonl"  # one line per Bright Data request actually sent (the running count)
VIA = "brightdata_unlocker"
USD_PER_REQUEST = 1.5 / 1000        # Web Unlocker pay-as-you-go rate, see docs/credits.md
MAX_REQUESTS = 1500                 # hard stop for this collector: 1500 * $0.0015 = $2.25, under the $5 limit
LAG_DAYS = 2                        # an evening spike is reported the next day or the day after
SEARCH_TTL = timedelta(hours=6)
MAX_ARTICLES_PER_SITE = 8           # per window
TOPICS = ("odor", "h2s_reading", "spill", "closure", "health", "agency_statement", "other")

# robots.txt read 2026-11-14. "wp" = WordPress public REST search (/wp-json/wp/v2/posts), which takes a date range.
SITES: dict[str, dict] = {
    "www.kpbs.org": {"name": "KPBS", "kind": "kpbs", "delay": 1.0},                          # only /venue, /place disallowed
    "timesofsandiego.com": {"name": "Times of San Diego", "kind": "wp", "delay": 1.0},       # only /wp-admin/ disallowed
    "inewsource.org": {"name": "inewsource", "kind": "wp", "delay": 1.0},                    # Disallow: (nothing) + wp-admin
    "voiceofsandiego.org": {"name": "Voice of San Diego", "kind": "wp", "delay": 1.0},       # Disallow: (nothing) + wp-admin
    "coronadotimes.com": {"name": "Coronado Times", "kind": "wp", "delay": 10.0},            # allowed, Crawl-delay: 10
}
RELEVANT = re.compile(r"hydrogen sulfide|\bH2S\b|odou?rs?\b|smell|stench|sewage|sewer gas|air quality", re.I)


# ---------- Bright Data fetch + cache ----------
def _key(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:20]


def _index() -> dict[str, dict]:
    """url -> latest cache entry."""
    out: dict[str, dict] = {}
    if INDEX.exists():
        for line in INDEX.read_text().splitlines():
            if line.strip():
                e = json.loads(line)
                out[e["url"]] = e
    return out


def request_count() -> int:
    return sum(1 for line in REQUESTS.read_text().splitlines() if line.strip()) if REQUESTS.exists() else 0


_last_hit: dict[str, float] = {}


def _throttle(host: str):
    delay = SITES.get(host, {}).get("delay", 1.0)
    wait = _last_hit.get(host, 0) + delay - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_hit[host] = time.monotonic()


def bd_get(url: str, ext: str = "html", max_age: timedelta | None = None) -> tuple[bytes, datetime]:
    """Return (body, fetched_at) for url. Cache first; otherwise one Bright Data Web Unlocker request."""
    host = urlparse(url).hostname or ""
    if host not in SITES:
        raise ValueError(f"{host} is not an allowed source")
    hit = _index().get(url)
    if hit and (BASE / hit["file"]).exists():
        at = datetime.fromisoformat(hit["fetched_at"])
        if max_age is None or datetime.now(UTC) - at < max_age:
            return (BASE / hit["file"]).read_bytes(), at
    token, zone = os.getenv("BRIGHTDATA_API_TOKEN"), os.getenv("BRIGHTDATA_UNLOCKER_ZONE")
    if not token or not zone:
        raise RuntimeError("BRIGHTDATA_API_TOKEN / BRIGHTDATA_UNLOCKER_ZONE not set")
    if request_count() >= MAX_REQUESTS:
        raise RuntimeError(f"request budget reached ({MAX_REQUESTS}); raise MAX_REQUESTS deliberately")
    _throttle(host)
    now = datetime.now(UTC)
    BASE.mkdir(parents=True, exist_ok=True)
    status, err, body = 0, "", b""
    try:
        r = httpx.post("https://api.brightdata.com/request", json={"zone": zone, "url": url, "format": "raw"},
                       headers={"Authorization": f"Bearer {token}"}, timeout=120)
        status, body, err = r.status_code, r.content, r.headers.get("x-brd-error", "")
    except httpx.HTTPError as e:
        err = f"{type(e).__name__}: {e}"
    with REQUESTS.open("a") as f:
        f.write(json.dumps({"at": now.isoformat(), "url": url, "status": status, "error": err[:200],
                            "bytes": len(body)}) + "\n")
    if status != 200 or err or not body:
        raise RuntimeError(f"Bright Data fetch failed for {url}: {status} {err[:200]}")
    name = f"pages/{now.strftime('%Y%m%dT%H%M%SZ')}_{_key(url)}.{ext}"
    (BASE / "pages").mkdir(parents=True, exist_ok=True)
    (BASE / name).write_bytes(body)
    with INDEX.open("a") as f:
        f.write(json.dumps({"url": url, "file": name, "fetched_at": now.isoformat(), "via": VIA}) + "\n")
    return body, now


# ---------- step 1: search (each site's own public listing, date-bounded) ----------
SLUG_HINT = re.compile(r"tijuana|tj-river|sewage|sewer|odor|hydrogen|stench|smell|imperial-beach|south-bay|"
                       r"cross-border|air-quality", re.I)
_KPBS_URL = re.compile(r"<loc>(https://www\.kpbs\.org/[^<]*?/(\d{4})/(\d{2})/(\d{2})/[^<]+)</loc>")
# Times of San Diego has no server-side search (Jetpack instant search runs in the browser), so we list posts by
# tag instead. Tag ids looked up 2026-11-14 at /wp-json/wp/v2/tags?search=tijuana|sewage|hydrogen:
# Tijuana, Tijuana River, Tijuana River Valley, tijuana river pollution, Tijuana River valley sewage crisis,
# sewage, hydrogen sulfide, south bay sewage crisis.
WP_TAGS = {"timesofsandiego.com": "703,5789,16165,311792,312053,309286,310709,312054"}
WP_SEARCH_TERM = "Tijuana"


def _months(a: date, b: date) -> list[str]:
    out, y, m = [], a.year, a.month
    while (y, m) <= (b.year, b.month):
        out.append(f"{y}{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def parse_kpbs_sitemap(xml: str, start: date, end: date) -> list[dict]:
    """Article URLs from a KPBS monthly sitemap whose URL date is in [start, end] and whose slug looks on-topic."""
    out = []
    for m in _KPBS_URL.finditer(xml):
        try:
            d = date(int(m[2]), int(m[3]), int(m[4]))
        except ValueError:
            continue
        slug = m[1].rsplit("/", 1)[-1]
        if start <= d <= end and SLUG_HINT.search(slug):
            out.append({"url": htmllib.unescape(m[1]), "listed_date": d})
    return out


def parse_wp_posts(body: str, start: date, end: date) -> list[dict]:
    """Post links from a WordPress REST /wp/v2/posts response, kept if the listed date is in [start, end]."""
    try:
        posts = json.loads(body)
    except json.JSONDecodeError:
        return []
    out = []
    for p in posts if isinstance(posts, list) else []:
        try:
            d = date.fromisoformat(str(p["date"])[:10])
            url = str(p["link"])
        except (KeyError, ValueError, TypeError):
            continue
        if start <= d <= end:
            out.append({"url": url, "listed_date": d})
    return out


def search_urls(host: str, start: date, end: date) -> list[tuple[str, str, str]]:
    """[(listing_url, ext, human-readable search_query)] to fetch for one site and one publication window."""
    kind = SITES[host]["kind"]
    if kind == "kpbs":
        return [(f"https://{host}/sitemap-{ym}.xml", "xml", f"KPBS monthly sitemap {ym}, slug filter")
                for ym in _months(start, end)]
    rng = (f"after={start.isoformat()}T00:00:00&before={(end + timedelta(days=1)).isoformat()}T00:00:00"
           "&per_page=50&_fields=date,link,title")
    if host in WP_TAGS:
        return [(f"https://{host}/wp-json/wp/v2/posts?tags={WP_TAGS[host]}&{rng}", "json",
                 f"{host} posts tagged Tijuana River / sewage / hydrogen sulfide, {start}..{end}")]
    return [(f"https://{host}/wp-json/wp/v2/posts?search={quote_plus(WP_SEARCH_TERM)}&{rng}", "json",
             f'{host} site search "{WP_SEARCH_TERM}", {start}..{end}')]


def search_site(host: str, start: date, end: date) -> list[dict]:
    """Candidate article URLs published in [start, end] on one site. Dates here are hints; step 3 verifies."""
    open_window = end >= datetime.now(TZ).date() - timedelta(days=1)
    found: dict[str, dict] = {}
    for url, ext, label in search_urls(host, start, end):
        try:
            body, _ = bd_get(url, ext, max_age=SEARCH_TTL if open_window else None)
        except RuntimeError as e:
            log.warning("search failed: %s", e)
            continue
        text = body.decode(errors="replace")
        hits = parse_kpbs_sitemap(text, start, end) if ext == "xml" else parse_wp_posts(text, start, end)
        for h in hits:
            if urlparse(h["url"]).hostname == host:
                found.setdefault(h["url"], {**h, "host": host, "search_query": label})
    return sorted(found.values(), key=lambda h: h["listed_date"])[:MAX_ARTICLES_PER_SITE]


# ---------- step 3: article parsing (title, publication date and text come from the page, in code) ----------
_DROP = re.compile(r"(?is)<(script|style|noscript|svg|figure|figcaption|nav|footer|header|aside|form|template)\b.*?</\1>")
_P = re.compile(r"(?is)<p\b[^>]*>(.*?)</p>")
_DATE_PATTERNS = [
    re.compile(r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)', re.I),
    re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']article:published_time', re.I),
    re.compile(r'"datePublished"\s*:\s*"([^"]+)"'),
    re.compile(r'<meta[^>]+itemprop=["\']datePublished["\'][^>]+content=["\']([^"\']+)', re.I),
    re.compile(r'<meta[^>]+name=["\'](?:date|pubdate|parsely-pub-date)["\'][^>]+content=["\']([^"\']+)', re.I),
]
_TITLE_PATTERNS = [
    re.compile(r'<meta[^>]+property=["\']og:title["\'][^>]+content="([^"]+)"', re.I),
    re.compile(r'<meta[^>]+content="([^"]+)"[^>]+property=["\']og:title', re.I),
    re.compile(r"(?is)<title[^>]*>(.*?)</title>"),
]


def _clean(s: str) -> str:
    return " ".join(htmllib.unescape(re.sub(r"(?s)<[^>]+>", "", s)).replace("\xa0", " ").split())


def parse_published(page: str) -> datetime | None:
    """Publication time from meta tags or JSON-LD.

    A value with an explicit UTC offset wins (KPBS's meta tag has none and disagrees with its JSON-LD, which has
    one). If no value carries an offset, the first one is read as Pacific time.
    """
    naive = None
    for pat in _DATE_PATTERNS:
        for m in pat.finditer(page):
            raw = htmllib.unescape(m[1]).strip().replace("Z", "+00:00")
            raw = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", raw)  # -0700 -> -07:00
            raw = re.sub(r"\.\d+", "", raw)
            try:
                d = datetime.fromisoformat(raw)
            except ValueError:
                continue
            if d.tzinfo:
                return d
            naive = naive or d
    return naive.replace(tzinfo=TZ) if naive else None


def parse_article(page: str) -> dict:
    """{title, published_at, text}. text is the page's paragraphs, one per line, whitespace collapsed."""
    title = ""
    for pat in _TITLE_PATTERNS:
        m = pat.search(page)
        if m and _clean(m[1]):
            title = re.sub(r"\s+[|\-–]\s+(KPBS.*|Times of San Diego|inewsource|Voice of San Diego|Coronado Times.*)$",
                           "", _clean(m[1]))
            break
    body = _DROP.sub(" ", page)
    a, b = body.find("<article"), body.rfind("</article>")
    if 0 <= a < b:
        body = body[a:b]
    paras = [p for p in (_clean(x) for x in _P.findall(body)) if len(p) >= 40]
    return {"title": title, "published_at": parse_published(page), "text": "\n".join(paras)}


def is_relevant(text: str) -> bool:
    return bool(re.search(r"tijuana", text, re.I) and RELEVANT.search(text))


# ---------- steps 4-5: Gemini proposes sentences, code verifies them ----------
class Candidate(BaseModel):
    quote: str = Field(min_length=20)
    topic: Literal["odor", "h2s_reading", "spill", "closure", "health", "agency_statement", "other"]


class Selection(BaseModel):
    candidates: list[Candidate]


PROMPT_VERSION = "v2"
PROMPT = """You are given the text of one news article. Your only job is to COPY sentences out of it.

Pick up to 3 sentences that report on Tijuana River sewage pollution and its odor or hydrogen sulfide (H2S, "sewer
gas") in the South Bay of San Diego (Imperial Beach, Nestor, San Ysidro, Tijuana River Valley), best first. Each
sentence must itself mention the odor, the air, hydrogen sulfide, the sewage or a closure. Prefer, in order:
1. a measured hydrogen sulfide level or an exceedance of a standard,
2. a description of the odor in the neighborhoods (when, where, how strong),
3. a sewage spill or flow, a closure (beach, school, road), a health effect, or a statement by a public agency.

Rules:
- Each quote must be ONE complete sentence copied character for character from the text. Do not fix, shorten, merge,
  translate or paraphrase. Do not add or change any number.
- Prefer sentences that stand on their own and do not name a private individual. Statements by agencies and
  officials acting in their role are fine.
- topic is one of: odor, h2s_reading (the sentence itself states a measured level), spill, closure, health,
  agency_statement, other.
- If the article does not report on Tijuana River sewage pollution, return {"candidates": []}.

ARTICLE TEXT:
"""

_NORM = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
                       "\xa0": " "})


def verbatim(quote: str, text: str) -> str | None:
    """The exact slice of `text` matching `quote`, or None. Only whitespace runs and curly/straight punctuation may
    differ; every letter and digit must match. The returned string is always the page's own characters."""
    flat = " ".join(text.split())
    q = " ".join(quote.split())
    if len(q) < 20:
        return None
    i = flat.translate(_NORM).find(q.translate(_NORM))  # translate is 1:1, so indexes line up with `flat`
    return flat[i:i + len(q)] if i >= 0 else None


# The sentence itself must be about the subject, so an off-topic line from an on-topic article is not shown.
QUOTE_TERMS = re.compile(r"hydrogen sulfide|\bH2S\b|\bppb\b|parts per billion|odou?rs?\b|smell|stench|sewage|sewer|"
                         r"wastewater|air quality|\bair\b|clos(?:ed|ure|ing)|pollut", re.I)


def pick_quote(candidates: list[dict], text: str) -> dict | None:
    """Best candidate that is found verbatim in the article text (max 500 chars) and names the subject.

    A sentence that states a measured level (digits + ppb) wins; otherwise Gemini's order is kept.
    """
    ok = []
    for c in candidates:
        q = verbatim(c.get("quote", ""), text)
        if not q or len(q) > 500 or not QUOTE_TERMS.search(q):
            continue
        if q.count("\u201c") != q.count("\u201d"):  # half of a quotation: not a complete sentence
            continue
        topic = c.get("topic") if c.get("topic") in TOPICS else "other"
        if topic == "h2s_reading" and not re.search(r"\d", q):  # a "reading" must show its number
            topic = "odor" if re.search(r"odou?r|smell|stench", q, re.I) else "other"
        ok.append({"quote": q, "topic": topic})
    measured = [c for c in ok if re.search(r"\d[\d,.]*\s*(ppb|parts per billion)", c["quote"], re.I)]
    return (measured or ok or [None])[0]


def gemini_candidates(text: str, url: str) -> list[dict]:
    """Ask Gemini for candidate sentences. Result cached per url so reruns cost nothing and stay identical."""
    cache = BASE / "llm" / f"{_key(url)}_{PROMPT_VERSION}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=key)  # keep a reference: the client closes when garbage-collected
    resp = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
        contents=PROMPT + text[:40_000],
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=Selection,
                                           temperature=0),
    )
    try:
        out = [c.model_dump() for c in Selection.model_validate_json(resp.text or "").candidates]
    except ValidationError as e:
        log.warning("gemini output failed validation for %s: %s", url, str(e)[:200])
        return []
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out, ensure_ascii=False))
    return out


# ---------- orchestration ----------
def report_id(url: str) -> str:
    return "wr-" + hashlib.sha1(url.encode()).hexdigest()[:16]


def fetch_reports(start_date: date, end_date: date) -> dict:
    """Find, verify and store reports for nights start_date..end_date.

    Articles published from start_date to end_date + LAG_DAYS are considered. Idempotent: cached pages and cached
    Gemini answers are reused and rows are upserted by url. Returns counts for the run.
    """
    pub_end = min(end_date + timedelta(days=LAG_DAYS), datetime.now(TZ).date())
    before = request_count()
    stats = {"window": f"{start_date}..{end_date}", "candidates": 0, "fetched": 0, "wrong_date": 0, "no_date": 0,
             "off_topic": 0, "no_verbatim_quote": 0, "errors": 0, "stored": 0}
    for host in SITES:
        for cand in search_site(host, start_date, pub_end):
            stats["candidates"] += 1
            url = cand["url"]
            try:
                body, fetched_at = bd_get(url, "html")
                stats["fetched"] += 1
                art = parse_article(body.decode(errors="replace"))
                pub = art["published_at"]
                if pub is None:
                    stats["no_date"] += 1
                    continue
                if not (start_date <= pub.astimezone(TZ).date() <= pub_end):
                    stats["wrong_date"] += 1
                    continue
                if not is_relevant(art["text"]):
                    stats["off_topic"] += 1
                    continue
                picked = pick_quote(gemini_candidates(art["text"], url), art["text"])
                if not picked:
                    stats["no_verbatim_quote"] += 1
                    continue
                store.upsert_web_report({"id": report_id(url), "url": url, "source_name": SITES[host]["name"],
                                         "title": art["title"], "published_at": pub, "quote": picked["quote"],
                                         "topic": picked["topic"], "fetched_at": fetched_at, "via": VIA,
                                         "search_query": cand["search_query"]})
                stats["stored"] += 1
            except Exception as e:
                stats["errors"] += 1
                log.warning("report %s failed: %s", url, str(e)[:300])
    stats["brightdata_requests"] = request_count() - before
    stats["brightdata_requests_total"] = request_count()
    store.log_fetch("web_reports", "ok" if not stats["errors"] else "error", str(BASE),
                    f"brightdata unlocker {json.dumps(stats)}")
    return stats


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(description="News quotes about Tijuana River odor / H2S, fetched via Bright Data")
    ap.add_argument("--since", type=int, help="last N days (live)")
    ap.add_argument("--from", dest="start", type=date.fromisoformat, help="first night, YYYY-MM-DD")
    ap.add_argument("--to", dest="end", type=date.fromisoformat, help="last night, YYYY-MM-DD")
    a = ap.parse_args(argv)
    today = datetime.now(TZ).date()
    if a.since is not None:
        start, end = today - timedelta(days=a.since), today
    elif a.start and a.end and a.start <= a.end:
        start, end = a.start, a.end
    else:
        ap.error("use --since N, or --from YYYY-MM-DD --to YYYY-MM-DD")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    store.init_db()
    stats = fetch_reports(start, end)
    print(json.dumps(stats, indent=2))
    print(f"estimated Bright Data cost so far: ${stats['brightdata_requests_total'] * USD_PER_REQUEST:.3f} "
          f"({stats['brightdata_requests_total']} requests incl. failed ones, which are not billed)")


if __name__ == "__main__":
    main()
