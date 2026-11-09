"""
Varsha — Climatological baseline.

For every block, issue day-of-year and horizon: the historical frequency of
each window event (smoothed over +/- 7 days) and the median window rainfall.
It is (1) the reference forecast for Brier Skill Scores, (2) a feature of the
ML model, and (3) the fallback forecast if no trained model is available.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from models import events as ev

DOY_MIN, DOY_MAX = 100, 330


class Climatology:
    def __init__(self, probs: dict, total_med: np.ndarray, block_ids: list[int], horizons: list[int]):
        self.probs = probs              # event -> [n_blocks, n_doy, n_h]
        self.total_med = total_med      # [n_blocks, n_doy, n_h]
        self.block_ids = list(block_ids)
        self.bidx = {b: i for i, b in enumerate(block_ids)}
        self.horizons = list(horizons)
        self.hidx = {h: i for i, h in enumerate(horizons)}

    @classmethod
    def fit(cls, cd, years, blocks, horizons=(7, 14, 21, 30), smooth: int = 7) -> "Climatology":
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # empty windows at season edges
            return cls._fit(cd, years, blocks, horizons, smooth)

    @classmethod
    def _fit(cls, cd, years, blocks, horizons, smooth) -> "Climatology":
        nb, nd, nh = len(blocks), DOY_MAX - DOY_MIN + 1, len(horizons)
        ny = len(years)
        lab = {k: np.full((ny, nb, nd, nh), np.nan, dtype=np.float32) for k in ev.EVENT_KEYS}
        tot = np.full((ny, nb, nd, nh), np.nan, dtype=np.float32)
        col = {b["id"]: cd.block_ids.index(b["id"]) for b in blocks}
        for yi, y in enumerate(years):
            sl = cd.year_slice(y)
            doys = cd.dates[sl].dayofyear.values
            rain = cd.rain[sl]
            n = len(doys)
            for bi, b in enumerate(blocks):
                r = rain[:, col[b["id"]]]
                flags = ev.season_flags(r)
                for hi, h in enumerate(horizons):
                    starts = np.flatnonzero((doys >= DOY_MIN) & (doys <= DOY_MAX) & (np.arange(n) + h <= n))
                    m = ev.window_label_matrix(r, starts, h, flags)
                    di = doys[starts] - DOY_MIN
                    for k in ev.EVENT_KEYS:
                        lab[k][yi, bi, di, hi] = m[k]
                    tot[yi, bi, di, hi] = m["total"]

        def smooth_mean(a):
            out = np.empty(a.shape[1:], dtype=np.float32)
            for d in range(nd):
                lo, hi_ = max(0, d - smooth), min(nd, d + smooth + 1)
                out[:, d, :] = np.nanmean(a[:, :, lo:hi_, :], axis=(0, 2))
            return out

        probs = {k: np.nan_to_num(smooth_mean(lab[k]), nan=0.0) for k in ev.EVENT_KEYS}
        med = np.empty((nb, nd, nh), dtype=np.float32)
        for d in range(nd):
            lo, hi_ = max(0, d - smooth), min(nd, d + smooth + 1)
            med[:, d, :] = np.nanmedian(tot[:, :, lo:hi_, :].transpose(1, 3, 0, 2).reshape(nb, nh, -1), axis=2)
        med = np.nan_to_num(med, nan=0.0)
        return cls(probs, med, [b["id"] for b in blocks], list(horizons))

    def _idx(self, block_id, doy, h):
        return self.bidx[block_id], int(np.clip(doy, DOY_MIN, DOY_MAX)) - DOY_MIN, self.hidx[h]

    def lookup(self, block_id: int, doy: int, h: int) -> dict:
        b, d, hi = self._idx(block_id, doy, h)
        out = {f"clim_{k}": float(self.probs[k][b, d, hi]) for k in ev.EVENT_KEYS}
        out["clim_total_med"] = float(self.total_med[b, d, hi])
        return out

    def lookup_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        """Vectorised clim_* columns for a frame with block_id, doy, horizon."""
        b = df["block_id"].map(self.bidx).values
        d = np.clip(df["doy"].values, DOY_MIN, DOY_MAX) - DOY_MIN
        h = df["horizon"].map(self.hidx).values
        out = {f"clim_{k}": self.probs[k][b, d, h] for k in ev.EVENT_KEYS}
        out["clim_total_med"] = self.total_med[b, d, h]
        return pd.DataFrame(out, index=df.index)
