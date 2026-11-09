"""
Varsha — Soil water balance (FAO-56 single-coefficient bucket).

Used for
  * the soil-moisture feature of the forecast model (default soil, block level)
  * panchayat soil moisture at issue time (panchayat soil properties)
  * seedling survival: run the bucket over forecast-conditioned rainfall
    ensembles and count members where the seedling is not killed by stress

Units: rain, ET and water depths in mm; soil water content in m3/m3.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"

SOIL_TYPES = {
    # field capacity, wilting point (m3/m3) — typical Telangana soils
    "red_sandy_loam": (0.24, 0.11),   # Alfisols (chalka): low water holding
    "red_loam": (0.30, 0.15),
    "black_cotton": (0.40, 0.21),     # Vertisols (regur): high water holding
}

SEEDLING_ROOT_DEPTH_M = 0.30   # effective rooting depth during establishment
DEFAULT_ROOT_DEPTH_M = 0.60    # for the generic soil-moisture predictor


@lru_cache(maxsize=1)
def crop_params() -> dict:
    with open(CONFIG_DIR / "crop_params.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def extraterrestrial_radiation(doy, lat_deg):
    """Ra in MJ m-2 day-1 (FAO-56 eq. 21)."""
    lat = np.radians(lat_deg)
    dr = 1 + 0.033 * np.cos(2 * np.pi * doy / 365)
    decl = 0.409 * np.sin(2 * np.pi * doy / 365 - 1.39)
    ws = np.arccos(np.clip(-np.tan(lat) * np.tan(decl), -1, 1))
    return (24 * 60 / np.pi) * 0.0820 * dr * (
        ws * np.sin(lat) * np.sin(decl) + np.cos(lat) * np.cos(decl) * np.sin(ws)
    )


def hargreaves_eto(tmax, tmin, doy, lat_deg):
    """Reference evapotranspiration (mm/day), Hargreaves-Samani."""
    tmean = (tmax + tmin) / 2
    ra_mm = 0.408 * extraterrestrial_radiation(doy, lat_deg)
    return np.clip(0.0023 * (tmean + 17.8) * np.sqrt(np.clip(tmax - tmin, 0.5, None)) * ra_mm, 0.5, 12.0)


def effective_rain(rain):
    """Rain minus a simple runoff loss that grows with intensity."""
    rc = crop_params()["soil_defaults"]["runoff_coefficient"]
    return rain - rc * np.clip(rain - 5.0, 0, None) - 0.25 * np.clip(rain - 60.0, 0, None)


def total_available_water(fc, wp, root_depth_m):
    return (np.asarray(fc) - np.asarray(wp)) * root_depth_m * 1000.0


def bucket(rain: np.ndarray, eto: np.ndarray, taw, kc=1.0, p_depletion=0.5, sw0=None):
    """
    Daily bucket over axis 0.

    rain, eto : [T, ...] arrays (broadcastable)
    taw       : total available water (mm), broadcastable to rain[0]
    Returns (sw [T, ...] end-of-day available water mm, ks [T, ...] stress coefficient).
    """
    rain = np.asarray(rain, dtype=float)
    eto = np.broadcast_to(np.asarray(eto, dtype=float), rain.shape)
    taw = np.broadcast_to(np.asarray(taw, dtype=float), rain.shape[1:])
    kc = np.broadcast_to(np.asarray(kc, dtype=float), (rain.shape[0],) + (1,) * (rain.ndim - 1))
    raw = (1 - p_depletion) * taw
    sw = np.array(taw * 0.5 if sw0 is None else np.broadcast_to(sw0, rain.shape[1:]), dtype=float)
    sw_out = np.empty_like(rain)
    ks_out = np.empty_like(rain)
    peff = effective_rain(rain)
    for t in range(rain.shape[0]):
        sw = np.minimum(sw + peff[t], taw)
        ks = np.clip(sw / np.maximum(raw, 1e-6), 0, 1)
        sw = np.maximum(sw - kc[t] * eto[t] * ks, 0)
        sw_out[t] = sw
        ks_out[t] = ks
    return sw_out, ks_out


def relative_soil_moisture_series(rain: np.ndarray, eto: np.ndarray, fc=0.30, wp=0.15,
                                  root_depth_m=DEFAULT_ROOT_DEPTH_M, sw0_frac=0.15) -> np.ndarray:
    """Relative available water (0-1) for each day, generic soil and Kc=0.8."""
    taw = total_available_water(fc, wp, root_depth_m)
    sw, _ = bucket(rain, eto, taw, kc=0.8, p_depletion=0.5, sw0=taw * sw0_frac)
    return sw / taw


def seedling_survival(rain_members: np.ndarray, eto: float | np.ndarray, sw0_rel: float, crop: str,
                      fc: float, wp: float, days: int | None = None) -> np.ndarray:
    """
    Survival indicator for each rainfall member if the crop is sown today.

    rain_members : [T, M] daily rain for M ensemble members (T >= establishment days)
    sw0_rel      : relative available water in the seedling root zone at sowing (0-1)
    A seedling is lost when stress (Ks < 0.4) lasts for more than the crop's
    critical dry-spell length during the initial stage.
    Returns bool array [M].
    """
    cp = crop_params()["crops"][crop]
    init = cp["growth_stages"]["initial"]
    days = min(days or init["duration_days"], rain_members.shape[0])
    critical = int(init.get("critical_dry_spell_days", 5))
    p = cp["soil"]["depletion_fraction"]
    taw = total_available_water(fc, wp, SEEDLING_ROOT_DEPTH_M)
    r = rain_members[:days]
    _, ks = bucket(r, eto, taw, kc=init["kc"] + 0.25, p_depletion=p, sw0=taw * sw0_rel)
    stressed = ks < 0.4
    run = np.zeros(r.shape[1], dtype=int)
    worst = np.zeros(r.shape[1], dtype=int)
    for t in range(days):
        run = np.where(stressed[t], run + 1, 0)
        worst = np.maximum(worst, run)
    return worst <= critical


def crop_stage(crop: str, days_since_sowing: int) -> str:
    if days_since_sowing < 0:
        return "not_sown"
    acc = 0
    for name, st in crop_params()["crops"][crop]["growth_stages"].items():
        acc += st["duration_days"]
        if days_since_sowing < acc:
            return name
    return "harvested"


def stage_kc(crop: str, stage: str) -> float:
    st = crop_params()["crops"][crop]["growth_stages"].get(stage)
    return float(st["kc"]) if st else 0.5
