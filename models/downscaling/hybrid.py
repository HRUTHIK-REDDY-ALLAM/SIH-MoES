"""
Varsha — Hybrid statistical-ML downscaler.

Gradient-boosted trees (LightGBM) map planetary drivers (ENSO, IOD, MJO and
its projected phase), regional atmosphere (850 hPa jet, OLR), the HMM regime
state and local antecedent conditions to block-level outcomes:

  * one calibrated binary classifier per window event
    (onset, false onset, 7/14-day dry spell, heavy, very heavy rain)
  * quantile regressors for window rainfall (q10, q25, q50, q75, q90)

Each classifier starts from the block climatology (its log-odds are the
boosting init_score), so the trees learn how teleconnections and local state
shift the risk away from the climatological prior: with no signal the model
falls back to climatology instead of adding noise.

Horizon is an input feature, so one model serves weeks 1-4. Probabilities are
isotonic-calibrated on out-of-fold hindcasts and then made physically
consistent (nested windows => non-decreasing in horizon, P(14d dry) <= P(7d dry),
P(very heavy) <= P(heavy), P(false onset) <= P(onset)).
Per-forecast explanations come from LightGBM's exact TreeSHAP contributions
(pred_contrib=True), summed into human-readable driver groups.
"""

from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from models import events as ev
from models.features import FEATURE_COLUMNS, FEATURE_GROUPS

QUANTILES = [0.1, 0.25, 0.5, 0.75, 0.9]
Q_NAMES = {0.1: "rainfall_q10", 0.25: "rainfall_q25", 0.5: "rainfall_median", 0.75: "rainfall_q75", 0.9: "rainfall_q90"}

CLF_PARAMS = dict(objective="binary", learning_rate=0.05, num_leaves=15, min_child_samples=300,
                  subsample=0.8, subsample_freq=1, colsample_bytree=0.7, reg_lambda=5.0,
                  max_bin=127, n_estimators=250, verbose=-1, n_jobs=-1)
QR_PARAMS = dict(learning_rate=0.06, num_leaves=31, min_child_samples=80, subsample=0.8, subsample_freq=1,
                 colsample_bytree=0.8, max_bin=127, n_estimators=200, verbose=-1, n_jobs=-1)


def _logit(p):
    p = np.clip(np.asarray(p, dtype=float), 0.005, 0.995)
    return np.log(p / (1 - p))


def _prior(df: pd.DataFrame, event: str) -> np.ndarray:
    col = f"clim_{event}"
    return _logit(df[col].values) if col in df else np.zeros(len(df))


class HybridDownscaler:
    def __init__(self, features: list[str] | None = None):
        self.features = list(features or FEATURE_COLUMNS)
        self.classifiers: dict[str, lgb.LGBMClassifier] = {}
        self.quantile_models: dict[float, lgb.LGBMRegressor] = {}
        self.calibrators: dict[str, IsotonicRegression] = {}

    # ── training ──
    def fit(self, df: pd.DataFrame, events=None, quantiles=None) -> "HybridDownscaler":
        X = df[self.features].astype(float)
        for k in events or ev.EVENT_KEYS:
            y = df[k].values
            if y.min() == y.max():  # degenerate (e.g. no events) -> constant model
                self.classifiers[k] = float(y.mean())
                continue
            m = lgb.LGBMClassifier(**CLF_PARAMS)
            m.fit(X, y, init_score=_prior(df, k))
            self.classifiers[k] = m
        for q in quantiles if quantiles is not None else QUANTILES:
            m = lgb.LGBMRegressor(objective="quantile", alpha=q, **QR_PARAMS)
            m.fit(X, np.log1p(df["total"].values))
            self.quantile_models[q] = m
        return self

    def set_calibration(self, oof: pd.DataFrame):
        """Fit isotonic calibrators from out-of-fold raw predictions (columns raw_<event>, <event>)."""
        for k in ev.EVENT_KEYS:
            col = f"raw_{k}"
            if col in oof and oof[k].nunique() > 1:
                iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
                iso.fit(oof[col].values, oof[k].values)
                self.calibrators[k] = iso

    # ── inference ──
    def predict_raw(self, df: pd.DataFrame) -> pd.DataFrame:
        X = df[self.features].astype(float)
        out = pd.DataFrame(index=df.index)
        for k, m in self.classifiers.items():
            if isinstance(m, float):
                out[f"prob_{k}"] = m
            else:
                margin = m.predict(X, raw_score=True) + _prior(df, k)
                out[f"prob_{k}"] = 1.0 / (1.0 + np.exp(-margin))
        for q, m in self.quantile_models.items():
            out[Q_NAMES[q]] = np.expm1(m.predict(X)).clip(0)
        return out

    def predict(self, df: pd.DataFrame, consistent: bool = True) -> pd.DataFrame:
        out = self.predict_raw(df)
        for k, iso in self.calibrators.items():
            out[f"prob_{k}"] = iso.predict(out[f"prob_{k}"].values)
        if consistent:
            out = enforce_consistency(out, df)
        return out

    def explain(self, df: pd.DataFrame, event: str, top: int = 4) -> list[list[dict]]:
        """Top driver groups (TreeSHAP log-odds shift away from climatology) for each row."""
        m = self.classifiers.get(event)
        if m is None or isinstance(m, float):
            return [[] for _ in range(len(df))]
        X = df[self.features].astype(float)
        contrib = m.booster_.predict(X, pred_contrib=True)[:, :-1]
        groups = sorted(set(FEATURE_GROUPS.get(f, f) for f in self.features))
        gidx = {g: i for i, g in enumerate(groups)}
        G = np.zeros((len(df), len(groups)))
        for j, f in enumerate(self.features):
            G[:, gidx[FEATURE_GROUPS.get(f, f)]] += contrib[:, j]
        results = []
        for i in range(len(df)):
            order = np.argsort(-np.abs(G[i]))[:top]
            results.append([{"group": groups[j], "contribution": round(float(G[i, j]), 3)} for j in order])
        return results


def enforce_consistency(pred: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    """Physical/logical constraints between events, horizons and quantiles."""
    p = pred.copy()
    if "prob_dry_spell_14d" in p and "prob_dry_spell_7d" in p:
        p["prob_dry_spell_14d"] = np.minimum(p["prob_dry_spell_14d"], p["prob_dry_spell_7d"])
    if "prob_very_heavy_rain" in p and "prob_heavy_rain" in p:
        p["prob_very_heavy_rain"] = np.minimum(p["prob_very_heavy_rain"], p["prob_heavy_rain"])
    if "prob_false_onset" in p and "prob_onset" in p:
        p["prob_false_onset"] = np.minimum(p["prob_false_onset"], p["prob_onset"])
    qcols = [Q_NAMES[q] for q in QUANTILES if Q_NAMES[q] in p]
    if qcols:
        p[qcols] = np.sort(p[qcols].values, axis=1)

    # Nested windows: longer horizon can only add events / rain
    key = df[["block_id", "issue_date"]].astype(str).agg("|".join, axis=1)
    order = df["horizon"].values
    tmp = p.copy()
    tmp["_key"] = key.values
    tmp["_h"] = order
    tmp = tmp.sort_values(["_key", "_h"])
    mono_cols = [c for c in p.columns if c.startswith("prob_")] + qcols
    tmp[mono_cols] = tmp.groupby("_key")[mono_cols].cummax()
    return tmp.drop(columns=["_key", "_h"]).loc[p.index]
