"""Colored PNG overlays per forecast hour (SDAPCD levels, colorblind-safe ramp, transparent below 1 ppb)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

# (ppb, RGBA). Levels match SDAPCD guidance; hues chosen to stay distinct under common color-vision deficiencies.
STOPS = [
    (0.8, (26, 152, 80, 0)),
    (2.0, (26, 152, 80, 70)),
    (5.0, (254, 224, 139, 150)),
    (15.0, (253, 174, 97, 175)),
    (30.0, (244, 109, 67, 195)),
    (100.0, (215, 48, 39, 210)),
    (200.0, (118, 42, 131, 220)),
]


def colorize(ppb: np.ndarray) -> np.ndarray:
    x = np.log(np.clip(ppb, 1e-3, None))
    xs = np.log([s[0] for s in STOPS])
    rgba = np.stack([np.interp(x, xs, [s[1][c] for s in STOPS]) for c in range(4)], axis=-1)
    rgba[ppb < STOPS[0][0]] = 0
    return rgba.astype(np.uint8)


def write_png(ppb2d: np.ndarray, path: Path):
    Image.fromarray(colorize(ppb2d), "RGBA").save(path, optimize=True)
