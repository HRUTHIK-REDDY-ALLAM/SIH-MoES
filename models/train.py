"""
Varsha — Model training, hindcast verification and artifact export.

    python -m models.train                # train on 1991-2022, verify, save
    python -m models.train --folds 4      # number of leave-years-out folds

Steps
  1. Load block climate (real indices; real or simulated rainfall)
  2. Fit the active/break HMM (unsupervised)
  3. Build labelled feature rows (block x issue date x horizon)
  4. Leave-years-out cross-validation -> out-of-fold hindcasts
     (climatology reference is refit without the test years each fold)
  5. Cross-fitted isotonic calibration -> honest skill scores
  6. Final model on all training years + calibrators from all OOF hindcasts
  7. Independent check on the held-out demo season (2023)
  8. Save artifacts/models/varsha_model.joblib (+ skill_report.json)
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from data.sources import DEMO_YEAR, FIRST_YEAR, load_blocks, load_climate
from models import events as ev
from models.baselines.climatology import Climatology
from models.downscaling.hybrid import HybridDownscaler, enforce_consistency
from models.features import CLIM_COLS, build_training_frame
from models.hmm.regime import RegimeHMM
from models.verification import skill as sk

logger = logging.getLogger("varsha.train")

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "artifacts" / "models"
BUNDLE_PATH = ARTIFACT_DIR / "varsha_model.joblib"
MODEL_VERSION = "varsha-hybrid-1.0"


def _with_clim(df: pd.DataFrame, clim: Climatology) -> pd.DataFrame:
    out = df.drop(columns=[c for c in CLIM_COLS if c in df], errors="ignore")
    return pd.concat([out, clim.lookup_frame(out)], axis=1)


def train(train_years: list[int] | None = None, folds: int = 4, issue_step: int = 3,
          save: bool = True) -> dict:
    t0 = time.time()
    train_years = train_years or list(range(FIRST_YEAR, DEMO_YEAR))
    cd = load_climate()
    blocks = load_blocks()
    logger.info("Climate loaded: %s seasons, sources=%s", len(set(cd.dates.year)), cd.sources)

    hmm = RegimeHMM.fit_climate(cd, train_years)
    logger.info("HMM fitted: mean active spell %.1f d, break spell %.1f d",
                hmm.expected_durations()["active_days"], hmm.expected_durations()["break_days"])

    base = build_training_frame(cd, train_years, blocks, clim=None, hmm=hmm, issue_step=issue_step)
    logger.info("Training rows: %d (%.0fs)", len(base), time.time() - t0)

    # ── Leave-years-out cross-validation ──
    fold_of = {y: i % folds for i, y in enumerate(train_years)}
    base["fold"] = base["year"].map(fold_of)
    oof_parts = []
    for k in range(folds):
        tr_years = [y for y in train_years if fold_of[y] != k]
        clim_k = Climatology.fit(cd, tr_years, blocks)
        tr = _with_clim(base[base["fold"] != k], clim_k)
        te = _with_clim(base[base["fold"] == k], clim_k)
        m = HybridDownscaler().fit(tr, quantiles=[0.1, 0.5, 0.9])
        raw = m.predict_raw(te)
        part = te[["block_id", "issue_date", "year", "horizon", "doy", "fold", "total"] + ev.EVENT_KEYS + CLIM_COLS].copy()
        for c in raw.columns:
            part[c.replace("prob_", "raw_") if c.startswith("prob_") else c] = raw[c].values
        oof_parts.append(part)
        logger.info("Fold %d/%d done (%.0fs)", k + 1, folds, time.time() - t0)
    oof = pd.concat(oof_parts, ignore_index=True)

    # Cross-fitted calibration for honest skill numbers
    cal = []
    for k in range(folds):
        helper = HybridDownscaler()
        helper.set_calibration(oof[oof["fold"] != k])
        part = oof[oof["fold"] == k].copy()
        for e in ev.EVENT_KEYS:
            iso = helper.calibrators.get(e)
            part[f"prob_{e}"] = iso.predict(part[f"raw_{e}"]) if iso is not None else part[f"raw_{e}"]
        cal.append(part)
    oof_cal = pd.concat(cal, ignore_index=True)
    oof_cal["rainfall_q10"] = oof_cal["rainfall_q10"]
    cons = enforce_consistency(oof_cal[[c for c in oof_cal.columns if c.startswith("prob_")] +
                                       ["rainfall_q10", "rainfall_median", "rainfall_q90"]], oof_cal)
    oof_cal[cons.columns] = cons
    hindcast = sk.summarise(oof_cal)
    blocks_skill = sk.block_skill(oof_cal)

    # ── Final model ──
    clim = Climatology.fit(cd, train_years, blocks)
    full = _with_clim(base, clim)
    model = HybridDownscaler().fit(full)
    model.set_calibration(oof)

    # ── Held-out demo season ──
    holdout = {}
    if DEMO_YEAR in set(cd.dates.year):
        te = build_training_frame(cd, [DEMO_YEAR], blocks, clim=clim, hmm=hmm, issue_step=1)
        pred = model.predict(te)
        hold = pd.concat([te.reset_index(drop=True), pred.reset_index(drop=True)], axis=1)
        holdout = sk.summarise(hold)

    bundle = {
        "model": model,
        "climatology": clim,
        "hmm": hmm.to_dict(),
        "skill": {"hindcast": hindcast, "blocks": blocks_skill, f"holdout_{DEMO_YEAR}": holdout},
        "train_years": train_years,
        "model_version": f"{MODEL_VERSION}+{datetime.now(timezone.utc):%Y%m%d}",
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": cd.sources,
        "is_synthetic": bool(cd.is_synthetic),
        "features": model.features,
        "n_training_rows": int(len(base)),
    }
    if save:
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(bundle, BUNDLE_PATH, compress=3)
        with open(ARTIFACT_DIR / "skill_report.json", "w", encoding="utf-8") as f:
            json.dump({k: v for k, v in bundle.items() if k in ("skill", "model_version", "trained_at",
                                                                  "train_years", "sources", "n_training_rows")},
                      f, indent=1, default=float)
        logger.info("Saved %s (%.0fs total)", BUNDLE_PATH, time.time() - t0)
    _log_summary(hindcast, holdout)
    return bundle


def _log_summary(hindcast: dict, holdout: dict):
    logger.info("Hindcast skill (leave-years-out, BSS vs block climatology / AUC):")
    for e, by_h in hindcast["by_event"].items():
        cells = "  ".join(f"w{h // 7 if h < 30 else 4}: {m['bss']:+.2f}/{m['auc']:.2f}" for h, m in by_h.items())
        logger.info("  %-16s %s", e, cells)
    if holdout:
        logger.info("Held-out %s season:", DEMO_YEAR)
        for e, by_h in holdout["by_event"].items():
            cells = "  ".join(f"{h}d: {m['bss']:+.2f}" for h, m in by_h.items())
            logger.info("  %-16s %s", e, cells)


def load_bundle(path: Path = BUNDLE_PATH) -> dict | None:
    if not path.exists():
        return None
    return joblib.load(path)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    ap = argparse.ArgumentParser(description="Train the Varsha hybrid model")
    ap.add_argument("--folds", type=int, default=4)
    ap.add_argument("--issue-step", type=int, default=3)
    args = ap.parse_args()
    train(folds=args.folds, issue_step=args.issue_step)


if __name__ == "__main__":
    np.seterr(all="ignore")
    main()
