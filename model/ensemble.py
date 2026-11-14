"""20-member ensemble: wind direction +/-15 deg, speed +/-30 %, log k from the filter variance (spec 5.6)."""
from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

import numpy as np

from model import puff
from model.emission import emission_factor
from model.met import Met
from model.sources import SourceConfig

N_MEMBERS = 20
MAX_WORKERS = int(os.getenv('MODEL_WORKERS', '8'))


@dataclass
class EnsembleResult:
    p10: np.ndarray  # [H, N] ppb
    p50: np.ndarray
    p90: np.ndarray
    members: np.ndarray | None = None


def confidence_label(p50: float, p90: float) -> str:
    ratio = (p90 + 0.5) / (p50 + 0.5)
    return "high" if ratio < 2 else "low" if ratio > 4 else "medium"


def run(met: Met, flow_mgd: np.ndarray, log_k: np.ndarray, log_k_var: float, src: SourceConfig,
        rx: np.ndarray, ry: np.ndarray, background_ppb: np.ndarray | float, n: int = N_MEMBERS,
        seed: int = 7, keep_members: bool = False, simulate=puff.simulate) -> EnsembleResult:
    rng = np.random.default_rng(seed)
    factor = emission_factor(flow_mgd, met.temp_c, src.alpha, src.beta, src.t_ref)
    jobs = []
    for i in range(n):
        if i == 0:
            ddir, sf, dk = 0.0, 1.0, 0.0  # member 0 = control
        else:
            ddir, sf = rng.uniform(-15, 15), rng.uniform(0.7, 1.3)
            dk = rng.normal(0, np.sqrt(max(log_k_var, 1e-6)))
        emis = np.exp(np.asarray(log_k) + dk) * factor
        jobs.append((met.perturbed(ddir, sf), emis))
    members = np.empty((n, len(met), len(rx)), dtype=np.float32)
    workers = min(n, os.cpu_count() or 1, MAX_WORKERS)
    if workers > 1 and len(rx) > 2000 and simulate is puff.simulate:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(simulate, m, e, src, rx, ry) for m, e in jobs]
            for i, f in enumerate(futs):
                members[i] = f.result()
    else:
        for i, (m, e) in enumerate(jobs):
            members[i] = simulate(m, e, src, rx, ry)
    members += np.asarray(background_ppb, dtype=np.float32)
    p10, p50, p90 = np.percentile(members, [10, 50, 90], axis=0).astype(np.float32)
    return EnsembleResult(p10, p50, p90, members if keep_members else None)
