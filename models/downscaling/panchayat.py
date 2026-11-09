"""
Varsha — Block -> panchayat interpolation.

Block forecasts are interpolated to each panchayat centroid with inverse
distance weighting over the nearest blocks (the panchayat's own block is
always included and up-weighted). Local differences in soil water holding
and irrigation are then applied in the panchayat water balance, so two
panchayats in the same block can receive different advice.
"""

from __future__ import annotations

import numpy as np


def idw_weights(panchayats: list[dict], blocks: list[dict], k: int = 4, power: float = 2.0,
                own_boost: float = 2.0) -> np.ndarray:
    """Row-stochastic weight matrix [n_panchayats, n_blocks]."""
    blat = np.array([b["lat"] for b in blocks])
    blon = np.array([b["lon"] for b in blocks])
    bid = [b["id"] for b in blocks]
    W = np.zeros((len(panchayats), len(blocks)))
    coslat = np.cos(np.radians(17.0))
    for i, p in enumerate(panchayats):
        d = np.hypot((blat - p["lat"]) * 111.0, (blon - p["lon"]) * 111.0 * coslat) + 1.0
        nearest = np.argsort(d)[:k]
        w = np.zeros(len(blocks))
        w[nearest] = 1.0 / d[nearest] ** power
        own = bid.index(p["block_id"])
        w[own] = max(w[own], w[nearest].max()) * own_boost
        W[i] = w / w.sum()
    return W
