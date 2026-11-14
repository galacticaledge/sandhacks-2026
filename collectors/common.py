"""Shared fetch helper: every raw response is cached on disk with its fetch time and logged."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from config import RAW_DIR, USER_AGENT
from db import store

log = logging.getLogger("collectors")
UTC = timezone.utc


def raw_path(source: str, ext: str, when: datetime | None = None) -> Path:
    when = when or datetime.now(UTC)
    d = RAW_DIR / source
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{when.strftime('%Y%m%dT%H%M%SZ')}.{ext}"


def latest_raw(source: str) -> Path | None:
    d = RAW_DIR / source
    files = sorted(d.glob("*")) if d.exists() else []
    return files[-1] if files else None


def save_raw(source: str, content: bytes, ext: str) -> Path:
    p = raw_path(source, ext)
    p.write_bytes(content)
    return p


def fresh_cache(source: str, max_age: timedelta) -> Path | None:
    """Most recent cached file if it is younger than max_age (polite-polling guard)."""
    p = latest_raw(source)
    if not p:
        return None
    try:
        t = datetime.strptime(p.stem, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None
    return p if datetime.now(UTC) - t < max_age else None


def fetch(source: str, url: str, ext: str = "json", params: dict | None = None,
          headers: dict | None = None, min_interval: timedelta | None = None, timeout: float = 60) -> bytes:
    if min_interval:
        cached = fresh_cache(source, min_interval)
        if cached:
            log.info("%s: using cache %s (min interval %s)", source, cached.name, min_interval)
            return cached.read_bytes()
    try:
        r = httpx.get(url, params=params, headers={"User-Agent": USER_AGENT, **(headers or {})},
                      timeout=timeout, follow_redirects=True)
        r.raise_for_status()
    except Exception as e:
        store.log_fetch(source, "error", None, str(e))
        raise
    p = save_raw(source, r.content, ext)
    store.log_fetch(source, "ok", str(p))
    return r.content


def brightdata_unlocker(source: str, url: str, ext: str) -> bytes:
    """Fetch a URL through Bright Data Web Unlocker (REST API). Cost is logged in docs/credits.md by caller."""
    token, zone = os.getenv("BRIGHTDATA_API_TOKEN"), os.getenv("BRIGHTDATA_UNLOCKER_ZONE")
    if not token or not zone:
        store.log_fetch(source, "error", None, "Bright Data credentials missing")
        raise RuntimeError("BRIGHTDATA_API_TOKEN / BRIGHTDATA_UNLOCKER_ZONE not set")
    try:
        r = httpx.post("https://api.brightdata.com/request", json={"zone": zone, "url": url, "format": "raw"},
                       headers={"Authorization": f"Bearer {token}"}, timeout=120)
        r.raise_for_status()
    except Exception as e:
        store.log_fetch(source, "error", None, str(e))
        raise
    p = save_raw(source, r.content, ext)
    store.log_fetch(source, "ok", str(p), f"brightdata unlocker {url}")
    return r.content
