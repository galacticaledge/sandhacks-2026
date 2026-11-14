"""Skill metrics (spec 5.7)."""
from __future__ import annotations

import numpy as np

from config import ORANGE_PPB

CATS = [(0, "green"), (5, "yellow"), (30, "orange")]


def cat(v):
    c = "green"
    for lo, name in CATS:
        if v >= lo:
            c = name
    return c


def night_scores(fc: np.ndarray, obs: np.ndarray) -> list[dict]:
    """fc, obs: [nights, hours] for one monitor. Returns per-night dicts (NaN obs hours ignored)."""
    out = []
    for f, o in zip(fc, obs):
        ok = np.isfinite(o) & np.isfinite(f)
        if ok.sum() < 6:
            continue
        out.append({"obs_peak": float(o[ok].max()), "fc_peak": float(f[ok].max()),
                    "obs_event": bool(o[ok].max() >= ORANGE_PPB), "fc_event": bool(f[ok].max() >= ORANGE_PPB),
                    "cat_hit": cat(o[ok].max()) == cat(f[ok].max()),
                    "mae_log": float(np.mean(np.abs(np.log1p(np.clip(f[ok], 0, None)) - np.log1p(np.clip(o[ok], 0, None)))))})
    return out


def summarize(scores: list[dict]) -> dict:
    n = len(scores)
    if n == 0:
        return {"n_nights": 0}
    ev = [s for s in scores if s["obs_event"]]
    fc_ev = [s for s in scores if s["fc_event"]]
    return {
        "n_nights": n,
        "n_orange_nights": len(ev),
        "hit_rate": (sum(s["fc_event"] for s in ev) / len(ev)) if ev else None,
        "false_alarm_ratio": (sum(not s["obs_event"] for s in fc_ev) / len(fc_ev)) if fc_ev else None,
        "category_accuracy": sum(s["cat_hit"] for s in scores) / n,
        "mae_log": float(np.mean([s["mae_log"] for s in scores])),
    }


# ---------- array scoring shared by the replay scorer and the fast hindcast ----------
def binary_counts(fc_event: np.ndarray, obs_event: np.ndarray) -> dict:
    """Orange tonight yes/no: the 2x2 table and the two headline rates."""
    fc_event = np.asarray(fc_event, bool); obs_event = np.asarray(obs_event, bool)
    hits = int((fc_event & obs_event).sum()); misses = int((~fc_event & obs_event).sum())
    fa = int((fc_event & ~obs_event).sum()); quiet = int((~fc_event & ~obs_event).sum())
    return {"hits": hits, "misses": misses, "false_alarms": fa, "correct_quiet": quiet, "n": hits + misses + fa + quiet,
            "hit_rate": hits / (hits + misses) if hits + misses else None,
            "false_alarm_ratio": fa / (hits + fa) if hits + fa else None}


def _peaks(fc: np.ndarray, obs: np.ndarray):
    """fc, obs [N, H, M] -> paired-hour count, forecast peak, observed peak, log MAE, each [N, M]."""
    ok = np.isfinite(fc) & np.isfinite(obs)
    n = ok.sum(axis=1)
    fp = np.where(ok, fc, -np.inf).max(axis=1); op = np.where(ok, obs, -np.inf).max(axis=1)
    err = np.abs(np.log1p(np.clip(np.where(ok, fc, 0), 0, None)) - np.log1p(np.clip(np.where(ok, obs, 0), 0, None)))
    mae = np.where(ok, err, 0).sum(axis=1) / np.maximum(n, 1)
    return n, fp, op, mae


def _cat_idx(v: np.ndarray) -> np.ndarray:
    return (v >= 5).astype(int) + (v >= ORANGE_PPB).astype(int)


def evaluate(obs: np.ndarray, hourly: dict[str, np.ndarray], prev_peak: np.ndarray, site_ids: list[str],
             sel: np.ndarray | None = None, event_only: dict[str, np.ndarray] | None = None,
             min_hours: int = 6) -> dict:
    """Score methods on exactly the same monitor-nights.

    obs [N, H, M]; hourly: method -> [N, H, M] forecast (the model's is its P50); event_only: extra yes/no
    rules scored from an hourly series but only in the binary table (the model's P90 = "possible" rule).
    prev_peak [N, M]: last night's observed peak, for the "orange after a quiet night" subset.
    A monitor-night counts only if every method has >= min_hours paired hours.
    Returns {"summary": method -> site -> metrics, "binary": subset -> site -> method -> counts,
             "eligible": [N, M] bool}.
    """
    parts = {m: _peaks(f, obs) for m, f in hourly.items()}
    extra = {m: _peaks(f, obs) for m, f in (event_only or {}).items()}
    elig = np.all([p[0] >= min_hours for p in list(parts.values()) + list(extra.values())], axis=0)
    if sel is not None:
        elig = elig & np.asarray(sel, bool)[:, None]
    sites = {s: np.arange(len(site_ids)) == j for j, s in enumerate(site_ids)}
    sites["all"] = np.ones(len(site_ids), bool)
    summary = {}
    for m, (n, fp, op, mae) in parts.items():
        summary[m] = {}
        for s, cols in sites.items():
            e = elig & cols[None, :]
            if not e.any():
                summary[m][s] = {"n_nights": 0}
                continue
            b = binary_counts(fp[e] >= ORANGE_PPB, op[e] >= ORANGE_PPB)
            summary[m][s] = {"n_nights": int(e.sum()), "n_orange_nights": b["hits"] + b["misses"],
                             "hit_rate": b["hit_rate"], "false_alarm_ratio": b["false_alarm_ratio"],
                             "category_accuracy": float((_cat_idx(fp[e]) == _cat_idx(op[e])).mean()),
                             "mae_log": float(mae[e].mean())}
    rules = {("model_likely" if m == "model" else m): p for m, p in parts.items()}
    rules.update(extra)
    order = [r for r in ("model_likely", "model_possible", "persistence", "climatology") if r in rules]
    order += [r for r in rules if r not in order]
    quiet_before = np.isfinite(prev_peak) & (prev_peak < ORANGE_PPB)
    binary = {}
    for subset, mask in (("all_nights", elig), ("after_quiet_night", elig & quiet_before)):
        binary[subset] = {}
        for s, cols in sites.items():
            e = mask & cols[None, :]
            binary[subset][s] = {r: binary_counts(rules[r][1][e] >= ORANGE_PPB, rules[r][2][e] >= ORANGE_PPB) for r in order}
    return {"summary": summary, "binary": binary, "eligible": elig}


def coverage(obs: np.ndarray, p90: np.ndarray, elig: np.ndarray) -> dict:
    """How often the observation falls at or under P90 (honest target: about 0.9)."""
    _, fp, op, _ = _peaks(p90, obs)
    ok = np.isfinite(obs) & np.isfinite(p90) & elig[:, None, :]
    return {"night_peak_under_p90": float((op[elig] <= fp[elig]).mean()) if elig.any() else None,
            "hourly_under_p90": float((obs[ok] <= p90[ok]).mean()) if ok.any() else None,
            "n_monitor_nights": int(elig.sum()), "n_hours": int(ok.sum())}


def auc(score: np.ndarray, event: np.ndarray) -> float | None:
    """Chance a random orange night gets a higher score than a random quiet night (0.5 = no skill)."""
    from scipy.stats import rankdata
    event = np.asarray(event, bool)
    n1, n0 = int(event.sum()), int((~event).sum())
    if not n1 or not n0:
        return None
    r = rankdata(score)
    return float((r[event].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))
