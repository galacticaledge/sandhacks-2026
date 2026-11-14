"""Load source configuration (model/sources.yaml)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from model.geo import to_xy

PATH = Path(__file__).with_name("sources.yaml")


@dataclass
class SourceConfig:
    ids: list[str]
    names: list[str]
    lats: np.ndarray
    lons: np.ndarray
    x: np.ndarray
    y: np.ndarray
    shares: np.ndarray
    alpha: float
    beta: float
    log_k: float
    t_ref: float
    sigma_y0: float
    sigma_z0: float
    sigma_v: float = 0.0        # m/s, lateral meander speed (0 = textbook Pasquill-Gifford only)
    max_age_s: float = 4 * 3600.0
    q_dil: float = 0.0          # MGD above which storm water dilutes the sewage (0 = off)
    dil_gamma: float = 2.0

    def factor(self, flow_mgd, temp_c) -> np.ndarray:
        """Emission per unit k for this configuration: Q^alpha * exp(beta dT) / dilution."""
        from model.emission import emission_factor
        return emission_factor(flow_mgd, temp_c, self.alpha, self.beta, self.t_ref, self.q_dil, self.dil_gamma)

    def with_params(self, **kw) -> "SourceConfig":
        d = dict(self.__dict__)
        d.update(kw)
        if "shares" in kw:
            s = np.asarray(kw["shares"], dtype=float)
            d["shares"] = s / s.sum()
        return SourceConfig(**d)


def load_sources(path: Path = PATH) -> SourceConfig:
    cfg = yaml.safe_load(path.read_text())
    src = cfg["sources"][:3]
    lats = np.array([s["lat"] for s in src])
    lons = np.array([s["lon"] for s in src])
    x, y = to_xy(lats, lons)
    shares = np.array([s["share"] for s in src], dtype=float)
    return SourceConfig(
        ids=[s["id"] for s in src], names=[s["name"] for s in src], lats=lats, lons=lons,
        x=x, y=y, shares=shares / shares.sum(), alpha=cfg["alpha"], beta=cfg["beta"],
        log_k=cfg["log_k"], t_ref=cfg["t_ref_c"], sigma_y0=cfg["initial_sigma_y_m"],
        sigma_z0=cfg["initial_sigma_z_m"], sigma_v=float(cfg.get("sigma_v_ms", 0.0)),
        max_age_s=float(cfg.get("max_puff_age_h", 4.0)) * 3600.0,
        q_dil=float(cfg.get("q_dil_mgd", 0.0)), dil_gamma=float(cfg.get("dil_gamma", 2.0)),
    )
