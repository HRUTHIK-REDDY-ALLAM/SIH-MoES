"""
Varsha — Forecast-conditioned analog weather generator.

Turns a probabilistic outlook into an ensemble of plausible 30-day daily
rainfall sequences for a block, which the water balance then uses to estimate
seedling survival ("if you sow today, what is the chance the seedlings live?").

Method: every historical 30-day sequence for the same block starting within
+/- 10 days of the issue day-of-year is a candidate (~650 per block). Each
candidate gets an importance weight so the weighted ensemble reproduces the
forecast: event likelihood ratios for the 14-day dry-spell / heavy-rain /
onset probabilities, then a bin correction so the 30-day rainfall total
follows the forecast quantiles. Sequences stay physically realistic (real
day-to-day structure) while their statistics follow the forecast.
"""

from __future__ import annotations

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from models import events as ev

LENGTH = 30
DOY_LO, DOY_HI = 120, 300
COND_EVENTS = ("dry_spell_7d", "heavy_rain", "onset")


class AnalogLibrary:
    def __init__(self, cd, years: list[int], block_ids: list[int], doy_window: int = 10):
        self.doy_window = doy_window
        self.block_ids = list(block_ids)
        self.bidx = {b: i for i, b in enumerate(block_ids)}
        nd = DOY_HI - DOY_LO + 1
        ny, nb = len(years), len(block_ids)
        self.seq = np.full((nb, ny, nd, LENGTH), np.nan, dtype=np.float32)
        self.lab = {k: np.zeros((nb, ny, nd), dtype=bool) for k in COND_EVENTS}
        self.total = np.full((nb, ny, nd), np.nan, dtype=np.float32)
        for yi, y in enumerate(years):
            sl = cd.year_slice(y)
            doys = cd.dates[sl].dayofyear.values
            rain = cd.rain[sl]
            n = len(doys)
            starts = np.flatnonzero((doys >= DOY_LO) & (doys <= DOY_HI) & (np.arange(n) + LENGTH <= n))
            di = doys[starts] - DOY_LO
            for bi, b in enumerate(block_ids):
                r = rain[:, cd.block_ids.index(b)]
                win = sliding_window_view(r, LENGTH)
                self.seq[bi, yi, di] = win[starts]
                m14 = ev.window_label_matrix(r, starts, 14)
                for k in COND_EVENTS:
                    self.lab[k][bi, yi, di] = m14[k]
                self.total[bi, yi, di] = win[starts].sum(axis=1)

    def ensemble(self, block_id: int, doy: int, probs14: dict, quantiles30: dict):
        """Return (sequences [30, M], weights [M]) conditioned on the forecast."""
        bi = self.bidx[block_id]
        lo = max(DOY_LO, doy - self.doy_window) - DOY_LO
        hi = min(DOY_HI, doy + self.doy_window) - DOY_LO + 1
        seq = self.seq[bi, :, lo:hi].reshape(-1, LENGTH)
        tot = self.total[bi, :, lo:hi].reshape(-1)
        ok = np.isfinite(tot)
        seq, tot = seq[ok], tot[ok]
        w = np.ones(len(tot))
        for k in COND_EVENTS:
            p = probs14.get(k)
            if p is None:
                continue
            y = self.lab[k][bi, :, lo:hi].reshape(-1)[ok]
            q = np.clip(y.mean(), 0.02, 0.98)
            p = float(np.clip(p, 0.02, 0.98))
            w *= np.where(y, p / q, (1 - p) / (1 - q))
        # Match the forecast distribution of the 30-day total via quantile bins
        qs = [quantiles30.get(k) for k in ("rainfall_q10", "rainfall_q25", "rainfall_median", "rainfall_q75", "rainfall_q90")]
        if all(v is not None for v in qs):
            edges = np.maximum.accumulate(np.asarray(qs, float))
            target = np.array([0.10, 0.15, 0.25, 0.25, 0.15, 0.10])
            b = np.digitize(tot, edges)
            mass = np.array([w[b == i].sum() for i in range(6)])
            mass = mass / max(mass.sum(), 1e-9)
            scale = np.where(mass > 1e-6, target / np.maximum(mass, 1e-6), 0.0)
            w = w * scale[b]
        if w.sum() <= 0:
            w = np.ones(len(tot))
        # temper extreme weights so the effective sample size stays reasonable
        w = w / w.sum()
        ess = 1.0 / np.sum(w ** 2)
        if ess < 30:
            w = np.sqrt(w)
            w = w / w.sum()
        return seq.T.astype(float), w
