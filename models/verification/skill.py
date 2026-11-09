"""
Varsha — Probabilistic forecast verification.

Brier score, Brier Skill Score against block climatology, ROC AUC,
reliability diagrams, and quantile (pinball) loss / interval coverage for
rainfall totals. Used for leave-years-out hindcasts and for the held-out
demo season.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from models import events as ev


def brier(p, y) -> float:
    p, y = np.asarray(p, float), np.asarray(y, float)
    return float(np.mean((p - y) ** 2)) if len(p) else float("nan")


def brier_skill(p, y, p_ref) -> float:
    bs, bs_ref = brier(p, y), brier(p_ref, y)
    if not np.isfinite(bs_ref) or bs_ref <= 1e-9:
        return float("nan")
    return 1.0 - bs / bs_ref


def auc(p, y) -> float:
    y = np.asarray(y)
    if y.min() == y.max():
        return float("nan")
    return float(roc_auc_score(y, p))


def reliability(p, y, bins: int = 10) -> list[dict]:
    p, y = np.asarray(p, float), np.asarray(y, float)
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    out = []
    for b in range(bins):
        m = idx == b
        if m.sum() >= 20:
            out.append({"bin_center": round(float((edges[b] + edges[b + 1]) / 2), 3),
                        "forecast": round(float(p[m].mean()), 4),
                        "observed": round(float(y[m].mean()), 4),
                        "count": int(m.sum())})
    return out


def pinball(q_pred, y, q) -> float:
    d = np.asarray(y, float) - np.asarray(q_pred, float)
    return float(np.mean(np.maximum(q * d, (q - 1) * d)))


def summarise(df: pd.DataFrame, prob_prefix: str = "prob_", clim_prefix: str = "clim_") -> dict:
    """
    Skill tables from a frame with labels, prob_<event>, clim_<event>, horizon.
    Returns {"by_event": {event: {horizon: metrics}}, "rainfall": {...}}.
    """
    res = {"by_event": {}, "rainfall": {}, "n": int(len(df))}
    for k in ev.EVENT_KEYS:
        pc, cc = f"{prob_prefix}{k}", f"{clim_prefix}{k}"
        if pc not in df:
            continue
        res["by_event"][k] = {}
        for h, g in df.groupby("horizon"):
            res["by_event"][k][int(h)] = {
                "base_rate": round(float(g[k].mean()), 4),
                "brier": round(brier(g[pc], g[k]), 4),
                "brier_clim": round(brier(g[cc], g[k]), 4),
                "bss": round(brier_skill(g[pc], g[k], g[cc]), 4),
                "auc": round(auc(g[pc], g[k]), 4),
                "reliability": reliability(g[pc], g[k]),
            }
    if "rainfall_median" in df:
        for h, g in df.groupby("horizon"):
            inside = (g["total"] >= g["rainfall_q10"]) & (g["total"] <= g["rainfall_q90"])
            med_ref = g["clim_total_med"] if "clim_total_med" in g else g["total"].median()
            res["rainfall"][int(h)] = {
                "pinball_median": round(pinball(g["rainfall_median"], g["total"], 0.5), 2),
                "pinball_median_clim": round(pinball(med_ref, g["total"], 0.5), 2),
                "coverage_q10_q90": round(float(inside.mean()), 3),
                "corr_median": round(float(np.corrcoef(g["rainfall_median"], g["total"])[0, 1]), 3),
            }
    return res


def block_skill(df: pd.DataFrame, events=("onset", "dry_spell_7d", "heavy_rain")) -> dict:
    """Per-block BSS (pooled over horizons) and a 0-1 trust score."""
    out = {}
    for b, g in df.groupby("block_id"):
        row = {}
        for k in events:
            row[f"bss_{k}"] = round(brier_skill(g[f"prob_{k}"], g[k], g[f"clim_{k}"]), 4)
        vals = [v for v in row.values() if np.isfinite(v)]
        mean_bss = float(np.mean(vals)) if vals else 0.0
        row["trust_score"] = round(float(np.clip(0.5 + 1.5 * mean_bss, 0, 1)), 3)
        out[int(b)] = row
    return out


def confidence_label(bss: float, cfg: dict | None = None) -> str:
    cfg = cfg or {"high": 0.20, "moderate": 0.05}
    if bss is None or not np.isfinite(bss):
        return "low"
    if bss >= cfg["high"]:
        return "high"
    if bss >= cfg["moderate"]:
        return "moderate"
    return "low"
