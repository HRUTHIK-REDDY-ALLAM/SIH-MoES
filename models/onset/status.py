"""
Varsha — Observed onset status of a block as of a given day.

Uses only observations up to t-1:

  not_yet      no onset spell (>= 20 mm in 3 days after May 15) yet
  provisional  an onset spell happened < 30 days ago and no 7-day dry spell
               has followed it yet (the false-onset risk window)
  established  an onset spell survived 30 days without a 7-day dry spell
  false_onset  every onset spell so far was followed by a 7-day dry spell
"""

from __future__ import annotations

import numpy as np

from models import events as ev


def onset_status(rain: np.ndarray, doys: np.ndarray, t: int) -> dict:
    th = ev.thresholds()
    rainy = th["rainfall"]["rainy_day"]
    min_dry = th["false_onset"]["dry_spell_threshold_days"]
    window = th["false_onset"]["verification_window_days"]
    obs = rain[:t]
    if len(obs) < 3:
        return {"status": "not_yet", "onset_idx": None, "invalidated": []}
    flags = ev.onset_start_flags(obs, th["onset"]["min_rain_mm"], th["onset"]["consecutive_days"])
    flags &= (doys[:t] >= th["onset"]["search_start_doy"]) & (doys[:t] <= th["onset"]["search_end_doy"])
    spells = [int(i) for i in np.flatnonzero(flags) if i + 3 <= t]
    if not spells:
        return {"status": "not_yet", "onset_idx": None, "invalidated": []}
    fwd = ev.dry_run_length_forward(obs, rainy)
    invalid, provisional, confirmed = [], [], []
    for s in spells:
        lo, hi = s + 3, min(s + window, t)
        bad = False
        j = lo
        while j < hi:
            if obs[j] < rainy and (j == 0 or obs[j - 1] >= rainy or j == lo):
                if fwd[j] >= min_dry:
                    bad = True
                    break
            j += 1
        if bad:
            invalid.append(s)
        elif s + window <= t:
            confirmed.append(s)
        else:
            provisional.append(s)
    if confirmed:
        return {"status": "established", "onset_idx": confirmed[0], "invalidated": invalid}
    if provisional:
        return {"status": "provisional", "onset_idx": provisional[0], "invalidated": invalid}
    return {"status": "false_onset", "onset_idx": invalid[-1], "invalidated": invalid}
