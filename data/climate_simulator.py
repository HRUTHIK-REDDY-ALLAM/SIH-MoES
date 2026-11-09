"""
Varsha — Teleconnection-driven stochastic climate simulator.

Why this exists
---------------
Block-level daily rainfall for 30+ years (CHIRPS/IMD) is large and, for IMD,
not openly downloadable. So that the full system can be trained, verified and
demonstrated offline, this module generates a physically structured synthetic
rainfall record for every pilot block. Everything it produces is flagged
`is_synthetic=True` downstream. When real block rainfall is available
(data/processed/chirps_blocks.parquet, see scripts/extract_chirps_blocks.py)
the pipeline uses that instead and this module is not used for rain.

Structure of the simulated world
--------------------------------
* Large-scale drivers: ONI and DMI (monthly, real NOAA values when reachable)
  and MJO RMM1/RMM2 (daily, real BoM values when reachable). Synthetic AR
  processes are used as a fallback.
* Regional monsoon regime: a Markov chain over {pre_onset, burst, active,
  break, withdrawn}. Regional onset date depends on ENSO/IOD. After onset,
  active->break transitions are modulated by MJO phase/amplitude and ENSO,
  so MJO gives genuine 1-4 week predictability.
* Pre-onset convective bursts produce realistic false onsets.
* Monsoon depressions (Jul-Sep) produce heavy / very heavy rain.
* Block rainfall: Gaussian-copula occurrence and gamma amounts, driven by a
  spatially correlated daily noise field plus a persistent (AR) local anomaly
  field, with latitude/elevation-dependent climatology.
* Regional atmospheric fields u850 (low-level jet) and OLR anomaly that lead
  regime changes by 1-3 days (stand-ins for ERA5 predictors).
* 2023 follows a scripted scenario mirroring the observed season (early-June
  false onset in the west, late-June onset, wet late July, August break).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy.stats import gamma as gamma_dist
from scipy.stats import norm

SEASON_START = (4, 1)    # simulate Apr 1 ...
SEASON_END = (11, 30)    # ... to Nov 30 of each year

STATES = ["pre_onset", "burst", "active", "break", "withdrawn", "depression", "weak_active"]
S = {name: i for i, name in enumerate(STATES)}

# MJO phase -> effect on Indian monsoon convection (+ wet, - dry), consistent
# with data/fetchers/mjo_bsiso.classify_indian_monsoon_impact
MJO_EFFECT = {1: 0.6, 2: 0.8, 3: 0.2, 4: -0.4, 5: -0.8, 6: -0.7, 7: -0.1, 8: 0.4}


@dataclass
class ClimateData:
    """Block-level daily climate for a set of seasons."""
    dates: pd.DatetimeIndex
    block_ids: list[int]
    rain: np.ndarray            # [n_days, n_blocks] mm/day
    tmax: np.ndarray            # [n_days, n_blocks] degC
    tmin: np.ndarray            # [n_days, n_blocks] degC
    drivers: pd.DataFrame       # index=dates; oni, dmi, rmm1, rmm2, mjo_phase, mjo_amp, u850, olr
    regime: np.ndarray          # [n_days] regional true regime label (diagnostic only)
    is_synthetic: bool = True
    sources: dict = field(default_factory=dict)

    def year_slice(self, year: int) -> slice:
        idx = np.flatnonzero(self.dates.year == year)
        return slice(int(idx[0]), int(idx[-1]) + 1)

    def date_index(self, d) -> int | None:
        loc = self.dates.get_indexer([pd.Timestamp(d)])[0]
        return None if loc < 0 else int(loc)


def season_dates(year: int) -> pd.DatetimeIndex:
    return pd.date_range(date(year, *SEASON_START), date(year, *SEASON_END), freq="D")


# ─── Synthetic driver fallback ───────────────────────────────────────────────

def synthetic_drivers(dates: pd.DatetimeIndex, seed: int = 7) -> pd.DataFrame:
    """AR-process stand-ins for ONI, DMI and MJO RMM when real data is unavailable."""
    rng = np.random.default_rng(seed)
    months = pd.period_range(dates.min().to_period("M") - 24, dates.max().to_period("M") + 1, freq="M")
    oni = np.zeros(len(months))
    dmi = np.zeros(len(months))
    for i in range(1, len(months)):
        oni[i] = np.clip(0.93 * oni[i - 1] + rng.normal(0, 0.28), -2.5, 2.8)
        amp = 1.4 if months[i].month in (7, 8, 9, 10, 11) else 0.8
        dmi[i] = np.clip(0.75 * dmi[i - 1] + rng.normal(0, 0.18 * amp), -1.5, 1.8)
    monthly = pd.DataFrame({"oni": oni, "dmi": dmi}, index=months.to_timestamp() + pd.Timedelta(days=14))
    full = pd.date_range(dates.min(), dates.max(), freq="D")
    daily = monthly.reindex(monthly.index.union(full)).interpolate("time").reindex(full)

    n = len(full)
    theta = np.zeros(n)
    logamp = np.zeros(n)
    theta[0] = rng.uniform(-np.pi, np.pi)
    for t in range(1, n):
        theta[t] = theta[t - 1] + 2 * np.pi / 45 + rng.normal(0, 0.07)
        logamp[t] = 0.96 * logamp[t - 1] + rng.normal(0, 0.11)
    amp = np.exp(logamp) * 1.05
    daily["rmm1"] = amp * np.cos(theta)
    daily["rmm2"] = amp * np.sin(theta)
    return add_mjo_phase(daily)


def add_mjo_phase(df: pd.DataFrame) -> pd.DataFrame:
    angle = np.degrees(np.arctan2(df["rmm2"].values, df["rmm1"].values))
    df["mjo_phase"] = (((angle + 180.0) // 45.0).astype(int) % 8) + 1
    df["mjo_amp"] = np.hypot(df["rmm1"].values, df["rmm2"].values)
    return df


# ─── Block geography ─────────────────────────────────────────────────────────

def block_climate_factors(blocks: list[dict]) -> dict:
    lat = np.array([b["lat"] for b in blocks])
    lon = np.array([b["lon"] for b in blocks])
    elev = np.array([b.get("elevation") or synthetic_elevation(b["lat"], b["lon"]) for b in blocks])
    # Wetter to the north (Medak) and slightly with elevation; drier rain-shadow south-west
    rain_mult = 1.0 + 0.11 * (lat - 16.6) + 0.0002 * (elev - 400)
    # Monsoon advances from the south-west: later onset to the north and east
    onset_lag = 2.4 * (lat - 15.5) + 0.6 * (lon - 77.0)
    return {"lat": lat, "lon": lon, "elev": elev, "rain_mult": rain_mult, "onset_lag": onset_lag}


def synthetic_elevation(lat: float, lon: float) -> float:
    """Smooth stand-in for SRTM mean block elevation (m) on the Deccan plateau."""
    return float(330 + 85 * (lat - 15.5) - 40 * (lon - 78.0) + 35 * np.sin(3.1 * lon) * np.cos(2.3 * lat))


def _spatial_cholesky(lat, lon, length_km: float) -> np.ndarray:
    dy = (lat[:, None] - lat[None, :]) * 111.0
    dx = (lon[:, None] - lon[None, :]) * 111.0 * np.cos(np.radians(17.0))
    d = np.hypot(dx, dy)
    cov = np.exp(-d / length_km) + 1e-6 * np.eye(len(lat))
    return np.linalg.cholesky(cov)


# ─── State-dependent rainfall parameters ─────────────────────────────────────

def _state_params(state: int, doy: int) -> tuple[float, float]:
    """(wet-day probability, mean wet-day amount mm) for a regime state."""
    if state == S["pre_onset"]:
        p = 0.04 + 0.08 * np.clip((doy - 130) / 40, 0, 1)
        return p, 5.0
    if state == S["burst"]:
        return 0.82, 13.0
    if state == S["active"]:
        return 0.70, 9.6
    if state == S["weak_active"]:
        return 0.38, 6.5
    if state == S["break"]:
        return 0.09, 3.5
    if state == S["depression"]:
        return 0.95, 52.0
    return 0.10, 7.0  # withdrawn


def _regime_chain(year: int, drv: pd.DataFrame, dates: pd.DatetimeIndex, rng) -> tuple[np.ndarray, int]:
    """Simulate the regional regime sequence and regional onset doy for one season."""
    doys = dates.dayofyear.values
    jja = drv.loc[(drv.index.month >= 5) & (drv.index.month <= 8)]
    oni_s = float(jja["oni"].mean()) if len(jja) else 0.0
    dmi_s = float(jja["dmi"].mean()) if len(jja) else 0.0
    onset_doy = int(np.clip(rng.normal(161 + 3.5 * oni_s - 2.5 * dmi_s, 6.5), 146, 192))
    withdraw_doy = int(np.clip(rng.normal(282 - 3 * oni_s, 6), 265, 300))

    mjo_eff = np.array([MJO_EFFECT[int(p)] for p in drv["mjo_phase"].values]) * np.clip(drv["mjo_amp"].values, 0, 2.5) / 1.5
    states = np.zeros(len(dates), dtype=np.int32)
    state = S["pre_onset"]
    burst_left = 0
    dep_left = 0
    for t, doy in enumerate(doys):
        if doy < onset_doy:
            if burst_left > 0:
                state, burst_left = S["burst"], burst_left - 1
            elif 145 <= doy and rng.random() < 0.012 + 0.012 * max(mjo_eff[t], 0):
                burst_left = int(rng.integers(1, 3))
                state = S["burst"]
            else:
                state = S["pre_onset"]
        elif doy >= withdraw_doy:
            state = S["withdrawn"]
        else:
            if dep_left > 0:
                state, dep_left = S["depression"], dep_left - 1
            elif doy == onset_doy:
                state = S["active"]
            else:
                prev = states[t - 1]
                if prev in (S["active"], S["depression"]):
                    p_ab = 1 / (1 + np.exp(-(-2.45 - 1.5 * mjo_eff[t] + 0.30 * oni_s - 0.15 * dmi_s)))
                    if doy - onset_doy < 30:
                        p_ab *= 0.35  # monsoon establishing: breaks less likely in the first month
                    state = S["break"] if rng.random() < p_ab else S["active"]
                elif prev == S["break"]:
                    p_ba = 1 / (1 + np.exp(-(-1.75 + 1.5 * mjo_eff[t] - 0.25 * oni_s)))
                    state = S["active"] if rng.random() < p_ba else S["break"]
                else:
                    state = S["active"]
                if state == S["active"] and 185 <= doy <= 270 and rng.random() < 0.02:
                    dep_left = int(rng.integers(1, 3))
                    state = S["depression"]
        states[t] = state
    return states, onset_doy


def _scenario_2023(dates: pd.DatetimeIndex) -> tuple[np.ndarray, dict]:
    """Scripted regional regimes for the 2023 demo season (mirrors the observed season)."""
    def d(m, dd):
        return pd.Timestamp(2023, m, dd)

    plan = [
        (d(4, 1), d(6, 6), "pre_onset"),
        (d(6, 7), d(6, 10), "burst"),         # first significant rain -> onset criterion met
        (d(6, 11), d(6, 23), "break"),        # dry gap -> false onset (west)
        (d(6, 24), d(7, 6), "active"),        # real onset
        (d(7, 7), d(7, 13), "weak_active"),
        (d(7, 14), d(7, 18), "active"),
        (d(7, 19), d(7, 20), "depression"),   # very wet late July
        (d(7, 21), d(7, 24), "active"),
        (d(7, 25), d(7, 27), "depression"),
        (d(7, 28), d(8, 5), "active"),
        (d(8, 6), d(8, 24), "break"),         # August 2023 break
        (d(8, 25), d(8, 26), "depression"),   # revival with heavy rain
        (d(8, 27), d(9, 9), "active"),
        (d(9, 10), d(9, 16), "break"),
        (d(9, 17), d(9, 30), "active"),
        (d(10, 1), d(10, 4), "weak_active"),
        (d(10, 5), d(11, 30), "withdrawn"),
    ]
    states = np.full(len(dates), S["pre_onset"], dtype=np.int32)
    for a, b, name in plan:
        states[(dates >= a) & (dates <= b)] = S[name]
    # Eastern/northern blocks keep showery weak-active weather in the June gap,
    # so the false onset is confined to the western (Mahbubnagar) blocks.
    overrides = {"east_june_gap": ((dates >= d(6, 11)) & (dates <= d(6, 23)))}
    return states, overrides


# MJO path for the 2023 scenario (unwrapped RMM angle in degrees, amplitude),
# consistent with the scripted regimes: phases 1-2 (enhanced convection over
# India) at the June burst, onset and late-August revival; a stall in phases
# 5-6 (suppressed convection) during the June gap and the August break.
def _c(phase: int, cycle: int) -> float:
    return -180.0 + 45.0 * (phase - 1) + 22.5 + 360.0 * cycle


SCENARIO_MJO_2023 = [
    ("2023-05-01", _c(5, 0), 0.6), ("2023-05-15", _c(6, 0), 0.7), ("2023-06-01", _c(8, 0), 0.9),
    ("2023-06-07", _c(1, 1), 1.4), ("2023-06-10", _c(2, 1), 1.5), ("2023-06-13", _c(4, 1), 1.6),
    ("2023-06-16", _c(5, 1), 1.7), ("2023-06-20", _c(6, 1), 1.6), ("2023-06-22", _c(7, 1), 1.5),
    ("2023-06-25", _c(8, 1), 1.4), ("2023-06-30", _c(1, 2), 1.5), ("2023-07-05", _c(2, 2), 1.2),
    ("2023-07-12", _c(3, 2), 0.8), ("2023-07-16", _c(4, 2), 0.7), ("2023-07-22", _c(6, 2), 0.6),
    ("2023-07-28", _c(8, 2), 0.9), ("2023-08-02", _c(1, 3), 1.1), ("2023-08-05", _c(3, 3), 1.3),
    ("2023-08-07", _c(4, 3), 1.6), ("2023-08-10", _c(5, 3), 1.8), ("2023-08-20", _c(6, 3), 1.9),
    ("2023-08-24", _c(7, 3), 1.6), ("2023-08-27", _c(8, 3), 1.5), ("2023-09-01", _c(1, 4), 1.4),
    ("2023-09-04", _c(2, 4), 1.3), ("2023-09-09", _c(4, 4), 1.3), ("2023-09-13", _c(5, 4), 1.3),
    ("2023-09-17", _c(7, 4), 1.1), ("2023-09-23", _c(1, 5), 0.9), ("2023-10-31", _c(6, 5), 0.6),
]


def apply_scenario_drivers(drivers: pd.DataFrame) -> pd.DataFrame:
    """Replace RMM1/RMM2 during the 2023 Kharif season with the scripted scenario path."""
    out = drivers.copy()
    kf = pd.DataFrame(SCENARIO_MJO_2023, columns=["date", "angle", "amp"])
    kf["date"] = pd.to_datetime(kf["date"])
    days = pd.date_range(kf["date"].min(), kf["date"].max(), freq="D")
    days = days[(days >= out.index.min()) & (days <= out.index.max())]
    if len(days) == 0:
        return out
    x = (kf["date"] - kf["date"].min()).dt.days.values
    xi = (days - kf["date"].min()).days.values
    ang = np.radians(np.interp(xi, x, kf["angle"].values))
    amp = np.interp(xi, x, kf["amp"].values)
    out.loc[days, "rmm1"] = amp * np.cos(ang)
    out.loc[days, "rmm2"] = amp * np.sin(ang)
    return add_mjo_phase(out)


# ─── Main simulation ─────────────────────────────────────────────────────────

def simulate(blocks: list[dict], years: list[int], drivers: pd.DataFrame, seed: int = 2026,
             scenario_years: tuple[int, ...] = (2023,)) -> ClimateData:
    """
    Generate block-level daily rain/temperature for the given years.

    `drivers` must cover the season days of every year with columns
    oni, dmi, rmm1, rmm2, mjo_phase, mjo_amp.
    """
    geo = block_climate_factors(blocks)
    nb = len(blocks)
    chol_fast = _spatial_cholesky(geo["lat"], geo["lon"], 70.0)
    chol_slow = _spatial_cholesky(geo["lat"], geo["lon"], 140.0)
    west = geo["lon"] < 78.45

    all_dates, rain_l, tmax_l, tmin_l, reg_l, drv_l = [], [], [], [], [], []
    for year in years:
        rng = np.random.default_rng(seed * 1000 + year)
        dates = season_dates(year)
        drv = drivers.reindex(dates).interpolate(limit_direction="both")
        if year in scenario_years:
            states, ov = _scenario_2023(dates)
            onset_doy = 175
        else:
            states, onset_doy = _regime_chain(year, drv, dates, rng)
            ov = {}
        n = len(dates)
        doys = dates.dayofyear.values

        # Block onset offsets: blocks lag the regional onset by geography
        block_onset = onset_doy + geo["onset_lag"] - geo["onset_lag"].mean() + rng.normal(0, 2.0, nb)
        if year in scenario_years:
            block_onset = onset_doy + 0.5 * (geo["onset_lag"] - geo["onset_lag"].mean())

        # Persistent local anomaly field (multi-day local wet/dry spells)
        slow = np.zeros((n, nb))
        for t in range(1, n):
            slow[t] = 0.86 * slow[t - 1] + np.sqrt(1 - 0.86 ** 2) * (chol_slow @ rng.standard_normal(nb))
        fast = rng.standard_normal((n, nb)) @ chol_fast.T
        u = 0.55 * slow + np.sqrt(1 - 0.55 ** 2) * fast
        v = norm.cdf(rng.standard_normal((n, nb)) @ chol_fast.T)

        rain = np.zeros((n, nb))
        oni_t = drv["oni"].values
        for t in range(n):
            st = states[t]
            p, mu = _state_params(st, doys[t])
            p_b = np.full(nb, p)
            mu_b = np.full(nb, mu)
            # Before a block's own onset, regional active weather is still patchy there
            if st in (S["active"], S["depression"]) and year not in scenario_years:
                not_yet = doys[t] < block_onset
                p_b[not_yet] *= 0.45
            if ov.get("east_june_gap") is not None and ov["east_june_gap"][t]:
                pe, mue = _state_params(S["weak_active"], doys[t])
                p_b[~west], mu_b[~west] = pe, mue
            p_b = np.clip(p_b * np.sqrt(geo["rain_mult"]), 0.01, 0.97)
            mu_b = mu_b * np.sqrt(geo["rain_mult"]) * (1 - 0.05 * np.clip(oni_t[t], -2, 2))
            wet = u[t] < norm.ppf(p_b)
            shape = 0.75 if st != S["depression"] else 1.1
            amt = gamma_dist.ppf(np.clip(v[t], 1e-6, 1 - 1e-6), shape, scale=mu_b / shape)
            rain[t] = np.where(wet, np.maximum(amt, 0.3), 0.0)
        rain = np.round(rain, 1)

        # Temperatures (degC): seasonal cycle, cooler on wet days and at elevation
        seas_tmax = 39.5 - 8.0 * np.clip((doys - 150) / 40, 0, 1) + 1.0 * np.clip((doys - 270) / 30, 0, 1)
        seas_tmin = 27.5 - 4.0 * np.clip((doys - 150) / 60, 0, 1) - 4.0 * np.clip((doys - 285) / 40, 0, 1)
        wet_cool = np.where(rain > 2.5, -2.6, 0.0)
        elev_adj = -0.0055 * (geo["elev"] - 400)
        tmax = seas_tmax[:, None] + wet_cool + elev_adj + rng.normal(0, 1.1, (n, nb))
        tmin = seas_tmin[:, None] + 0.4 * wet_cool + elev_adj + rng.normal(0, 0.8, (n, nb))

        # Regional atmospheric fields that lead regime changes by 1-3 days
        conv = np.isin(states, [S["active"], S["depression"], S["burst"]]).astype(float)
        conv_lead = np.concatenate([conv[2:], conv[-2:]])
        brk_lead = np.concatenate([(states == S["break"]).astype(float)[1:], [0.0]])
        u850 = 3.2 * conv_lead - 1.5 * brk_lead + 1.2 * np.sin(2 * np.pi * (doys - 150) / 365) + rng.normal(0, 1.1, n)
        olr = -22 * conv_lead + 12 * brk_lead + rng.normal(0, 7.0, n)
        drv = drv.copy()
        drv["u850"] = u850
        drv["olr"] = olr

        all_dates.append(dates)
        rain_l.append(rain)
        tmax_l.append(np.round(tmax, 1))
        tmin_l.append(np.round(tmin, 1))
        reg_l.append(states)
        drv_l.append(drv)

    dates = all_dates[0].append(all_dates[1:]) if len(all_dates) > 1 else all_dates[0]
    # Continuous daily drivers (lagged indices need dates before each season starts)
    full = drivers.loc[f"{years[0] - 1}-01-01":f"{years[-1]}-12-31"].copy()
    season_drv = pd.concat(drv_l)
    for col in ("u850", "olr"):
        full[col] = 0.0
        full.loc[season_drv.index, col] = season_drv[col].values
    return ClimateData(
        dates=dates,
        block_ids=[b["id"] for b in blocks],
        rain=np.vstack(rain_l),
        tmax=np.vstack(tmax_l),
        tmin=np.vstack(tmin_l),
        drivers=full,
        regime=np.concatenate(reg_l),
        is_synthetic=True,
    )


def regime_name(code: int) -> str:
    return STATES[int(code)]
