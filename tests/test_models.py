"""Tests for event windows, onset status, water balance, the regime HMM and the analog generator."""

import numpy as np
import pandas as pd
import pytest

from impact.water_balance import bucket, crop_stage, seedling_survival, total_available_water
from models import events as ev
from models.hmm.regime import RegimeHMM, regime_obs
from models.onset.status import onset_status


# ─── Window labels ───────────────────────────────────────────────────────────

def random_season(seed=0, n=200):
    rng = np.random.default_rng(seed)
    wet = rng.random(n) < 0.45
    return np.where(wet, rng.gamma(0.8, 12, n), 0.0).round(1)


@pytest.mark.parametrize("h", [7, 14, 21, 30])
def test_vectorised_window_labels_match_scalar(h):
    r = random_season(1)
    starts = np.arange(0, len(r) - h - 30)
    mat = ev.window_label_matrix(r, starts, h)
    for i, s in enumerate(starts):
        scalar = ev.window_labels(r, int(s), h)
        for k in ev.EVENT_KEYS:
            assert bool(mat[k][i]) == scalar[k], (k, s)
        assert mat["total"][i] == pytest.approx(scalar["total"])


def test_dry_spell_counted_from_issue_day():
    r = np.array([5.0] * 3 + [0.0] * 10 + [5.0] * 20)
    # issued in the middle of the dry run: 7 dry days remain from day 5 -> event
    assert ev.window_labels(r, 5, 7)["dry_spell_7d"]
    # only 4 dry days remain from day 9 -> no 7-day spell
    assert not ev.window_labels(r, 9, 7)["dry_spell_7d"]


def test_false_onset_window_label():
    r = np.array([0.0] * 5 + [10, 8, 6] + [0.0] * 12 + [8.0] * 30)
    lab = ev.window_labels(r, 0, 7)
    assert lab["onset"] and lab["false_onset"]
    r2 = np.array([0.0] * 5 + [10, 8, 6] + [4.0] * 40)
    lab2 = ev.window_labels(r2, 0, 7)
    assert lab2["onset"] and not lab2["false_onset"]


# ─── Onset status ────────────────────────────────────────────────────────────

def _doys(n, start=140):
    return np.arange(start, start + n)


def test_onset_status_progression():
    rain = np.array([0.0] * 10 + [12, 9, 6] + [4.0] * 50)
    doys = _doys(len(rain))
    assert onset_status(rain, doys, 10)["status"] == "not_yet"
    assert onset_status(rain, doys, 20)["status"] == "provisional"
    assert onset_status(rain, doys, 50)["status"] == "established"


def test_onset_status_false_onset():
    rain = np.array([0.0] * 10 + [12, 9, 6] + [0.0] * 12 + [1.0] * 10)
    assert onset_status(rain, _doys(len(rain)), 30)["status"] == "false_onset"


# ─── Water balance ───────────────────────────────────────────────────────────

def test_bucket_mass_balance_and_bounds():
    rng = np.random.default_rng(3)
    rain = rng.gamma(0.6, 8, (60, 4))
    taw = np.array([40.0, 60.0, 80.0, 100.0])
    sw, ks = bucket(rain, 5.0, taw, kc=0.8, p_depletion=0.5, sw0=taw / 2)
    assert (sw >= 0).all() and (sw <= taw + 1e-9).all()
    assert ((ks >= 0) & (ks <= 1)).all()


def test_seedling_survival_more_rain_is_better():
    dry = np.zeros((30, 50))
    wet = np.full((30, 50), 6.0)
    fc, wp = 0.30, 0.15
    assert not seedling_survival(dry, 5.0, 0.3, "cotton", fc, wp).any()
    assert seedling_survival(wet, 5.0, 0.3, "cotton", fc, wp).all()


def test_crop_stage_sequence():
    assert crop_stage("cotton", -1) == "not_sown"
    assert crop_stage("cotton", 0) == "initial"
    assert crop_stage("cotton", 40) == "development"
    assert crop_stage("cotton", 500) == "harvested"
    assert total_available_water(0.3, 0.15, 1.0) == pytest.approx(150.0)


# ─── Regime HMM ──────────────────────────────────────────────────────────────

def test_hmm_separates_active_and_break():
    rng = np.random.default_rng(7)
    seqs = []
    for _ in range(30):
        state, rain = 1, []
        for _ in range(120):
            if rng.random() < (0.08 if state == 1 else 0.15):
                state = 1 - state
            rain.append(rng.gamma(0.9, 14) if (state == 1 and rng.random() < 0.7) else (rng.gamma(0.6, 3) if rng.random() < 0.1 else 0.0))
        seqs.append(np.array(rain))
    X = np.column_stack([regime_obs(s[:, None])[:, 0] for s in seqs])
    m = RegimeHMM.fit(X)
    assert m.means[0] < m.means[1]  # state 0 = break
    pb = m.filter_break_probability(np.column_stack([np.zeros(30), np.full(30, 15.0)]))
    assert pb[-1, 0] > 0.8 and pb[-1, 1] < 0.2
    d = m.expected_durations()
    assert d["active_days"] > 3 and d["break_days"] > 2
