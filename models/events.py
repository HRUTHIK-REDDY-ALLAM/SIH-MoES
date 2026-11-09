"""
Varsha — Event labelling (reference implementation).

Pure functions over daily rainfall series. Thresholds come from
config/event_thresholds.yaml. These definitions are used for training
labels, hindcast verification and observed-event display, so the forecast
probabilities and the verification always mean the same thing.

Window event definitions (issue date t, horizon h, window = [t, t+h-1]):
  onset         the agronomic onset criterion (>= 20 mm in 3 consecutive days)
                is met by a 3-day spell starting inside the window
  false_onset   an onset spell starts inside the window AND a dry spell of
                >= 7 days begins within 30 days after that spell
  dry_spell_Ld  a run of >= L consecutive days < 2.5 mm begins inside the
                window, counting days from the issue date (a run already under
                way at issue counts from day t; it may extend past the window)
  heavy_rain    any day in the window >= 64.5 mm
  very_heavy    any day in the window >= 115.6 mm
  total         window rainfall total (mm)
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


@lru_cache(maxsize=1)
def thresholds() -> dict:
    with open(CONFIG_DIR / "event_thresholds.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _cfg():
    t = thresholds()
    return {
        "rainy": t["rainfall"]["rainy_day"],
        "heavy": t["rainfall"]["heavy"],
        "very_heavy": t["rainfall"]["very_heavy"],
        "onset_mm": t["onset"]["min_rain_mm"],
        "onset_days": t["onset"]["consecutive_days"],
        "fo_dry_days": t["false_onset"]["dry_spell_threshold_days"],
        "fo_window": t["false_onset"]["verification_window_days"],
    }


# ─── Scalar reference functions (unit-tested) ────────────────────────────────

def detect_onset(rainfall, min_rain=20, consecutive_days=3):
    """Index of the first day whose `consecutive_days` window totals >= min_rain, else None."""
    r = np.asarray(rainfall, dtype=float)
    if len(r) < consecutive_days:
        return None
    sums = np.convolve(r, np.ones(consecutive_days), mode="valid")
    idx = np.flatnonzero(sums >= min_rain - 1e-9)
    return int(idx[0]) if idx.size else None


def detect_false_onset(rainfall, onset_day, dry_threshold=2.5, min_dry_days=7, window=30):
    """
    Is the onset at `onset_day` false, i.e. followed by a dry spell of
    >= min_dry_days starting within `window` days (after the 3 onset days)?

    Returns (is_false_onset, dry_spell_start_index, dry_spell_length).
    """
    if onset_day is None:
        return False, None, 0
    r = np.asarray(rainfall, dtype=float)
    check_start = onset_day + 3
    end = min(onset_day + window, len(r))
    i = check_start
    while i < end:
        if r[i] < dry_threshold:
            j = i
            while j < len(r) and r[j] < dry_threshold:
                j += 1
            if j - i >= min_dry_days:
                return True, i, j - i
            i = j
        else:
            i += 1
    return False, None, 0


def detect_dry_spells(rainfall, threshold=2.5, min_length=7):
    """All runs of >= min_length consecutive days below threshold."""
    r = np.asarray(rainfall, dtype=float)
    spells, i, n = [], 0, len(r)
    while i < n:
        if r[i] < threshold:
            j = i
            while j < n and r[j] < threshold:
                j += 1
            if j - i >= min_length:
                spells.append({"start": i, "end": j - 1, "length": j - i})
            i = j
        else:
            i += 1
    return spells


def classify_rainfall_day(rainfall_mm, thresholds_mm=None):
    t = thresholds_mm or {"rainy_day": 2.5, "heavy": 64.5, "very_heavy": 115.6, "extremely_heavy": 204.5}
    return {
        "is_rainy_day": rainfall_mm >= t["rainy_day"],
        "is_heavy_rain": rainfall_mm >= t["heavy"],
        "is_very_heavy_rain": rainfall_mm >= t["very_heavy"],
        "is_extremely_heavy_rain": rainfall_mm >= t["extremely_heavy"],
    }


# ─── Vectorised helpers for whole seasons ────────────────────────────────────

def dry_run_length_forward(rain: np.ndarray, threshold: float) -> np.ndarray:
    """L[i] = number of consecutive dry days starting at i (0 if day i is wet)."""
    dry = rain < threshold
    out = np.zeros(len(rain), dtype=np.int32)
    run = 0
    for i in range(len(rain) - 1, -1, -1):
        run = run + 1 if dry[i] else 0
        out[i] = run
    return out


def dry_spell_start_flags(rain: np.ndarray, threshold: float, min_len: int) -> np.ndarray:
    """True on days where a dry run of >= min_len starts (first day of the run)."""
    fwd = dry_run_length_forward(rain, threshold)
    prev_wet = np.ones(len(rain), dtype=bool)
    prev_wet[1:] = rain[:-1] >= threshold
    return (fwd >= min_len) & prev_wet


def onset_start_flags(rain: np.ndarray, min_mm: float, days: int) -> np.ndarray:
    """True on day i if rain[i:i+days] totals >= min_mm."""
    out = np.zeros(len(rain), dtype=bool)
    if len(rain) >= days:
        sums = np.convolve(rain, np.ones(days), mode="valid")
        out[: len(sums)] = sums >= min_mm - 1e-9
    return out


def false_onset_flags(rain: np.ndarray, onset_flags: np.ndarray, threshold: float,
                      min_dry: int, window: int) -> np.ndarray:
    """True on onset-spell days that are followed by a >= min_dry dry spell within `window` days."""
    starts = dry_spell_start_flags(rain, threshold, min_dry)
    # Also count a dry run that is already under way at check_start
    fwd = dry_run_length_forward(rain, threshold)
    out = np.zeros(len(rain), dtype=bool)
    n = len(rain)
    for i in np.flatnonzero(onset_flags):
        a, b = i + 3, min(i + window, n)
        if a >= b:
            continue
        if starts[a:b].any() or fwd[a] >= min_dry:
            out[i] = True
    return out


def window_labels(rain: np.ndarray, start: int, horizon: int, pre: dict | None = None) -> dict:
    """
    Event labels for the window rain[start:start+horizon].

    `rain` must extend >= 30 days past the window for false-onset/dry-spell
    look-ahead; callers check availability. `pre` may hold precomputed flag
    arrays (from season_flags) for speed.
    """
    c = _cfg()
    pre = pre or season_flags(rain)
    s, e = start, start + horizon
    w = rain[s:e]
    return {
        "onset": bool(pre["onset"][s:e].any()),
        "false_onset": bool(pre["false_onset"][s:e].any()),
        "dry_spell_7d": bool(pre["dry7"][s + 1:e].any() or pre["fwd"][s] >= 7),
        "dry_spell_14d": bool(pre["dry14"][s + 1:e].any() or pre["fwd"][s] >= 14),
        "heavy_rain": bool((w >= c["heavy"]).any()),
        "very_heavy_rain": bool((w >= c["very_heavy"]).any()),
        "total": float(w.sum()),
    }


def season_flags(rain: np.ndarray) -> dict:
    """Precompute per-day event flags for one block-season."""
    c = _cfg()
    onset = onset_start_flags(rain, c["onset_mm"], c["onset_days"])
    return {
        "onset": onset,
        "false_onset": false_onset_flags(rain, onset, c["rainy"], c["fo_dry_days"], c["fo_window"]),
        "dry7": dry_spell_start_flags(rain, c["rainy"], 7),
        "dry14": dry_spell_start_flags(rain, c["rainy"], 14),
        "fwd": dry_run_length_forward(rain, c["rainy"]),
    }


def window_label_matrix(rain: np.ndarray, starts: np.ndarray, horizon: int, flags: dict | None = None) -> dict:
    """Vectorised window_labels for many start indices (same horizon)."""
    c = _cfg()
    f = flags or season_flags(rain)
    n = len(rain)
    cs = lambda a: np.concatenate([[0], np.cumsum(a.astype(float))])  # noqa: E731
    cum = {k: cs(f[k]) for k in ("onset", "false_onset", "dry7", "dry14")}
    cum_heavy = cs(rain >= c["heavy"])
    cum_vheavy = cs(rain >= c["very_heavy"])
    cum_rain = cs(rain)
    s = np.asarray(starts)
    e = np.minimum(s + horizon, n)
    win = lambda cm: (cm[e] - cm[s]) > 0  # noqa: E731
    s1 = np.minimum(s + 1, n)
    win1 = lambda cm: (cm[e] - cm[s1]) > 0  # noqa: E731
    fwd = f["fwd"][np.minimum(s, n - 1)]
    return {
        "onset": win(cum["onset"]),
        "false_onset": win(cum["false_onset"]),
        "dry_spell_7d": win1(cum["dry7"]) | (fwd >= 7),
        "dry_spell_14d": win1(cum["dry14"]) | (fwd >= 14),
        "heavy_rain": win(cum_heavy),
        "very_heavy_rain": win(cum_vheavy),
        "total": cum_rain[e] - cum_rain[s],
    }


def season_onset(rain: np.ndarray, dates, search_start_doy: int | None = None,
                 search_end_doy: int | None = None) -> dict:
    """
    Observed onset for one block-season.

    Returns first onset (may be false), whether it was false, and the first
    'true' onset (first onset spell not followed by a false-onset dry spell).
    """
    t = thresholds()
    c = _cfg()
    lo = search_start_doy or t["onset"]["search_start_doy"]
    hi = search_end_doy or t["onset"]["search_end_doy"]
    doys = np.array([d.timetuple().tm_yday for d in dates])
    f = season_flags(rain)
    in_search = (doys >= lo) & (doys <= hi)
    cand = np.flatnonzero(f["onset"] & in_search)
    if cand.size == 0:
        return {"onset_idx": None, "is_false": False, "true_onset_idx": None,
                "dry_start_idx": None, "dry_len": 0}
    first = int(cand[0])
    is_false, ds, dl = detect_false_onset(rain, first, c["rainy"], c["fo_dry_days"], c["fo_window"])
    true_idx = None
    for i in cand:
        if not f["false_onset"][i]:
            true_idx = int(i)
            break
    return {"onset_idx": first, "is_false": bool(is_false), "true_onset_idx": true_idx,
            "dry_start_idx": ds, "dry_len": int(dl)}


EVENT_KEYS = ["onset", "false_onset", "dry_spell_7d", "dry_spell_14d", "heavy_rain", "very_heavy_rain"]
