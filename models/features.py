"""
Varsha — Feature engineering for the hybrid downscaling model.

One row = (block, issue date t, horizon h). Everything is computed from data
available on the morning of t (observations up to t-1, indices with their
real publication lags), so hindcasts are honest.

Feature groups
  planetary   ONI (45-day lag), DMI (30-day lag), MJO RMM1/2, amplitude,
              phase, and the MJO phase projected to the middle of the
              forecast window (MJO propagates ~8 deg/day: physics-based lead)
  regional    850 hPa low-level jet (u850) and OLR anomalies, regional rain
  local       antecedent block rain (3/7/14/30 day), current dry run, season
              total, soil moisture (water balance), onset state
  regime      HMM filtered probability of being in a break
  static      lat, lon, elevation, day of year, horizon
  climatology block climatological probability of each event for this window
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from data.climate_simulator import MJO_EFFECT, ClimateData
from impact.water_balance import hargreaves_eto, relative_soil_moisture_series
from models import events as ev

HORIZONS = [7, 14, 21, 30]
ISSUE_DOY_START = 135   # May 15
ISSUE_DOY_END = 288     # Oct 15

MJO_EFFECT_ARR = np.array([0.0] + [MJO_EFFECT[p] for p in range(1, 9)])

FEATURE_GROUPS = {
    "oni": "ENSO (Niño 3.4)",
    "dmi": "Indian Ocean Dipole",
    "rmm1": "MJO", "rmm2": "MJO", "mjo_amp": "MJO", "mjo_eff_now": "MJO",
    "mjo_eff_proj": "MJO (projected)", "mjo_proj_sin": "MJO (projected)", "mjo_proj_cos": "MJO (projected)",
    "u850": "Low-level jet (850 hPa)", "u850_3d": "Low-level jet (850 hPa)",
    "olr": "Convection (OLR)", "olr_3d": "Convection (OLR)",
    "reg_rain_7d": "Regional rainfall", "reg_wet_frac_3d": "Regional rainfall",
    "rain_3d": "Recent local rain", "rain_7d": "Recent local rain", "rain_14d": "Recent local rain",
    "rain_30d": "Recent local rain", "max_rain_7d": "Recent local rain", "wet_days_14d": "Recent local rain",
    "dry_run": "Current dry run", "season_rain": "Season rainfall so far",
    "soil_moisture": "Soil moisture",
    "onset_occurred": "Onset status", "days_since_onset": "Onset status",
    "p_break": "Monsoon regime (HMM)",
    "doy": "Time of season", "doy_sin": "Time of season", "doy_cos": "Time of season",
    "horizon": "Forecast lead", "lat": "Location", "lon": "Location", "elevation": "Location",
}
CLIM_COLS = [f"clim_{k}" for k in ev.EVENT_KEYS] + ["clim_total_med"]
for _c in CLIM_COLS:
    FEATURE_GROUPS[_c] = "Seasonal climatology"

FEATURE_COLUMNS = [
    "horizon", "doy", "doy_sin", "doy_cos", "lat", "lon", "elevation",
    "oni", "dmi", "rmm1", "rmm2", "mjo_amp", "mjo_eff_now", "mjo_eff_proj", "mjo_proj_sin", "mjo_proj_cos",
    "u850", "u850_3d", "olr", "olr_3d", "reg_rain_7d", "reg_wet_frac_3d",
    "rain_3d", "rain_7d", "rain_14d", "rain_30d", "max_rain_7d", "wet_days_14d", "dry_run", "season_rain",
    "soil_moisture", "onset_occurred", "days_since_onset", "p_break",
] + CLIM_COLS

LABEL_COLUMNS = ev.EVENT_KEYS + ["total"]


def _trailing_sum(x: np.ndarray, w: int) -> np.ndarray:
    """Sum of x[t-w : t] (excludes day t) along axis 0."""
    c = np.vstack([np.zeros((1,) + x.shape[1:]), np.cumsum(x, axis=0)])
    t = np.arange(x.shape[0])
    lo = np.maximum(t - w, 0)
    return c[t] - c[lo]


def _trailing_max(x: np.ndarray, w: int) -> np.ndarray:
    out = np.zeros_like(x)
    for t in range(1, x.shape[0]):
        out[t] = x[max(0, t - w):t].max(axis=0)
    return out


def _current_dry_run(rain: np.ndarray, thr: float) -> np.ndarray:
    """Consecutive dry days ending at t-1, per block."""
    out = np.zeros(rain.shape, dtype=float)
    run = np.zeros(rain.shape[1])
    for t in range(rain.shape[0]):
        out[t] = run
        run = np.where(rain[t] < thr, run + 1, 0)
    return out


class SeasonState:
    """Per-season precomputed arrays (observations up to each day)."""

    def __init__(self, cd: ClimateData, year: int, blocks: list[dict], hmm=None):
        sl = cd.year_slice(year)
        self.year = year
        self.dates = cd.dates[sl]
        self.doys = self.dates.dayofyear.values
        self.rain = cd.rain[sl]
        self.tmax = cd.tmax[sl]
        self.tmin = cd.tmin[sl]
        self.drv = cd.drivers.loc[self.dates[0] - pd.Timedelta(days=60): self.dates[-1]]
        thr = ev.thresholds()["rainfall"]["rainy_day"]
        n, nb = self.rain.shape

        self.rain_3d = _trailing_sum(self.rain, 3)
        self.rain_7d = _trailing_sum(self.rain, 7)
        self.rain_14d = _trailing_sum(self.rain, 14)
        self.rain_30d = _trailing_sum(self.rain, 30)
        self.max_7d = _trailing_max(self.rain, 7)
        self.wet_14d = _trailing_sum((self.rain >= thr).astype(float), 14)
        self.dry_run = _current_dry_run(self.rain, thr)
        may1 = int(np.searchsorted(self.doys, 121))
        cum = np.vstack([np.zeros((1, nb)), np.cumsum(self.rain, axis=0)])
        self.season_rain = np.maximum(cum[:-1] - cum[may1], 0)

        reg = self.rain.mean(axis=1)
        self.reg_rain_7d = _trailing_sum(reg[:, None], 7)[:, 0]
        self.reg_wet_3d = _trailing_sum((self.rain >= thr).mean(axis=1)[:, None], 3)[:, 0] / 3.0

        # Soil moisture (default soil) from the FAO-56 bucket, value at start of day t
        lat = np.array([b["lat"] for b in blocks])
        eto = hargreaves_eto(self.tmax, self.tmin, self.doys[:, None], lat[None, :])
        self.eto = eto
        sm = relative_soil_moisture_series(self.rain, eto)
        self.soil = np.vstack([sm[:1], sm[:-1]])

        # Onset state: first onset spell completed before t (spell start + 3 <= t)
        self.onset_idx = np.full(nb, -1)
        lo = ev.thresholds()["onset"]["search_start_doy"]
        for b in range(nb):
            f = ev.onset_start_flags(self.rain[:, b], ev.thresholds()["onset"]["min_rain_mm"],
                                     ev.thresholds()["onset"]["consecutive_days"])
            cand = np.flatnonzero(f & (self.doys >= lo))
            if cand.size:
                self.onset_idx[b] = cand[0]

        # HMM regime probability (filtered, uses obs up to t-1)
        if hmm is not None:
            pb = hmm.filter_break_probability(self.rain)
            self.p_break = np.vstack([np.full((1, nb), 0.5), pb[:-1]])
        else:
            self.p_break = np.full((n, nb), 0.5)

        self.flags = [ev.season_flags(self.rain[:, b]) for b in range(nb)]

    def onset_features(self, t: int) -> tuple[np.ndarray, np.ndarray]:
        done = (self.onset_idx >= 0) & (self.onset_idx + 3 <= t)
        since = np.where(done, np.minimum(t - self.onset_idx, 90), -1)
        return done.astype(float), since.astype(float)


def _driver_row(drv: pd.DataFrame, d: pd.Timestamp) -> dict:
    def at(col, lag):
        pos = drv.index.get_indexer([d - pd.Timedelta(days=lag)], method="pad")[0]
        return float(drv[col].iloc[max(pos, 0)])
    rmm1, rmm2 = at("rmm1", 1), at("rmm2", 1)
    amp = float(np.hypot(rmm1, rmm2))
    ang = np.arctan2(rmm2, rmm1)
    phase = int(((np.degrees(ang) + 180.0) // 45.0) % 8) + 1
    u3 = float(np.mean([at("u850", k) for k in (1, 2, 3)])) if "u850" in drv else 0.0
    o3 = float(np.mean([at("olr", k) for k in (1, 2, 3)])) if "olr" in drv else 0.0
    return {
        "oni": at("oni", 45), "dmi": at("dmi", 30), "rmm1": rmm1, "rmm2": rmm2,
        "mjo_amp": amp, "mjo_angle": ang, "mjo_phase": phase,
        "mjo_eff_now": MJO_EFFECT_ARR[phase] * min(amp, 2.5),
        "u850": at("u850", 1) if "u850" in drv else 0.0, "u850_3d": u3,
        "olr": at("olr", 1) if "olr" in drv else 0.0, "olr_3d": o3,
    }


def _projected_mjo(angle: float, amp: float, h: int) -> tuple[float, float, float]:
    """MJO state projected to the window centre (eastward propagation, damped amplitude)."""
    lead = h / 2.0
    a = angle + lead * 2 * np.pi / 45.0
    amp_p = amp * (0.965 ** lead)
    phase = int(((np.degrees(a) + 180.0) // 45.0) % 8) + 1
    return MJO_EFFECT_ARR[phase] * min(amp_p, 2.5), np.sin(a), np.cos(a)


def rows_for_day(state: SeasonState, t: int, blocks: list[dict], clim, horizons=HORIZONS,
                 with_labels: bool = False) -> list[dict]:
    """Feature rows for all blocks and horizons on season-day index t."""
    d = state.dates[t]
    doy = int(state.doys[t])
    dr = _driver_row(state.drv, d)
    done, since = state.onset_features(t)
    rows = []
    n = len(state.dates)
    for h in horizons:
        eff_p, ps, pc = _projected_mjo(dr["mjo_angle"], dr["mjo_amp"], h)
        if with_labels and t + h > n:
            continue
        for bi, b in enumerate(blocks):
            row = {
                "block_id": b["id"], "issue_date": d, "year": state.year, "horizon": h,
                "doy": doy, "doy_sin": np.sin(2 * np.pi * doy / 365.25), "doy_cos": np.cos(2 * np.pi * doy / 365.25),
                "lat": b["lat"], "lon": b["lon"], "elevation": b["elevation"],
                "oni": dr["oni"], "dmi": dr["dmi"], "rmm1": dr["rmm1"], "rmm2": dr["rmm2"],
                "mjo_amp": dr["mjo_amp"], "mjo_eff_now": dr["mjo_eff_now"], "mjo_eff_proj": eff_p,
                "mjo_proj_sin": ps, "mjo_proj_cos": pc, "mjo_phase": dr["mjo_phase"],
                "u850": dr["u850"], "u850_3d": dr["u850_3d"], "olr": dr["olr"], "olr_3d": dr["olr_3d"],
                "reg_rain_7d": state.reg_rain_7d[t], "reg_wet_frac_3d": state.reg_wet_3d[t],
                "rain_3d": state.rain_3d[t, bi], "rain_7d": state.rain_7d[t, bi],
                "rain_14d": state.rain_14d[t, bi], "rain_30d": state.rain_30d[t, bi],
                "max_rain_7d": state.max_7d[t, bi], "wet_days_14d": state.wet_14d[t, bi],
                "dry_run": state.dry_run[t, bi], "season_rain": state.season_rain[t, bi],
                "soil_moisture": state.soil[t, bi], "onset_occurred": done[bi], "days_since_onset": since[bi],
                "p_break": state.p_break[t, bi],
            }
            if clim is not None:
                row.update(clim.lookup(b["id"], doy, h))
            if with_labels:
                lab = ev.window_labels(state.rain[:, bi], t, h, pre=state.flags[bi])
                row.update(lab)
            rows.append(row)
    return rows


def build_training_frame(cd: ClimateData, years: list[int], blocks: list[dict], clim=None, hmm=None,
                         issue_step: int = 3, horizons=HORIZONS) -> pd.DataFrame:
    """Labelled feature rows for all blocks over the given seasons."""
    frames = []
    for y in years:
        st = SeasonState(cd, y, blocks, hmm=hmm)
        idx = np.flatnonzero((st.doys >= ISSUE_DOY_START) & (st.doys <= ISSUE_DOY_END))[::issue_step]
        rows = []
        for t in idx:
            rows.extend(rows_for_day(st, int(t), blocks, clim, horizons, with_labels=True))
        frames.append(pd.DataFrame(rows))
    df = pd.concat(frames, ignore_index=True)
    for k in ev.EVENT_KEYS:
        df[k] = df[k].astype(int)
    return df
