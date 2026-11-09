"""
Varsha — Data source layer.

Single entry point the models and pipeline use to get inputs:

  load_blocks()        pilot blocks (id, name, district, lat, lon, elevation)
  load_panchayats()    panchayats with soil properties
  load_drivers(a, b)   daily teleconnection drivers (ONI, DMI, MJO RMM)
  load_climate(years)  block-level daily rainfall/temperature + drivers

Real data is used wherever it is reachable and falls back gracefully:
  ONI   NOAA CPC (monthly)          -> synthetic AR process
  DMI   NOAA PSL HadISST (monthly)  -> synthetic AR process
  RMM   BoM MJO RMM (daily)         -> synthetic AR process
  Rain  data/processed/chirps_blocks.parquet (CHIRPS block means)
        -> teleconnection-driven simulator (data/climate_simulator.py)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import date
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from data import climate_simulator as sim

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
BOUNDARY_DIR = ROOT / "data" / "sample" / "boundaries"
PROCESSED_DIR = ROOT / "data" / "processed"
CHIRPS_BLOCKS = PROCESSED_DIR / "chirps_blocks.parquet"

FIRST_YEAR = 1991
DEMO_YEAR = 2023


def offline_mode() -> bool:
    return os.getenv("VARSHA_OFFLINE", "0") == "1"


# ─── Geography ───────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def load_blocks() -> list[dict]:
    with open(BOUNDARY_DIR / "blocks.geojson", encoding="utf-8") as f:
        gj = json.load(f)
    blocks = []
    for feat in gj["features"]:
        p = feat["properties"]
        blocks.append({
            "id": int(p["id"]),
            "name": p["name"],
            "district": p["district"],
            "lat": float(p["centroid_lat"]),
            "lon": float(p["centroid_lon"]),
            "elevation": p.get("elevation_m") or sim.synthetic_elevation(p["centroid_lat"], p["centroid_lon"]),
        })
    return blocks


@lru_cache(maxsize=1)
def load_panchayats() -> list[dict]:
    with open(BOUNDARY_DIR / "panchayats.geojson", encoding="utf-8") as f:
        gj = json.load(f)
    out = []
    for feat in gj["features"]:
        p = feat["properties"]
        out.append({
            "id": int(p["id"]),
            "name": p["name"],
            "block_id": int(p["block_id"]),
            "lat": float(p["centroid_lat"]),
            "lon": float(p["centroid_lon"]),
            "soil_type": p.get("soil_type", "red_sandy_loam"),
            "field_capacity": float(p.get("field_capacity", 0.30)),
            "wilting_point": float(p.get("wilting_point", 0.15)),
            "irrigated_fraction": float(p.get("irrigated_fraction", 0.3)),
        })
    return out


# ─── Teleconnection drivers ──────────────────────────────────────────────────

def _monthly_to_daily(df: pd.DataFrame, col: str, full: pd.DatetimeIndex) -> pd.Series:
    idx = pd.to_datetime(dict(year=df["year"], month=df["month"], day=15))
    s = pd.Series(df[col].values, index=idx).sort_index()
    s = s[~s.index.duplicated()]
    return s.reindex(s.index.union(full)).interpolate("time").reindex(full)


def load_drivers(start: date, end: date) -> tuple[pd.DataFrame, dict]:
    """Daily drivers between start and end. Returns (frame, {index: source})."""
    full = pd.date_range(start, end, freq="D")
    synth = sim.synthetic_drivers(full)
    out = pd.DataFrame(index=full)
    sources = {}

    oni = dmi = rmm = None
    if not offline_mode():
        try:
            from data.fetchers.enso_oni import fetch_oni
            from data.fetchers.iod_dmi import fetch_dmi
            from data.fetchers.mjo_bsiso import fetch_rmm
            oni, dmi, rmm = fetch_oni(), fetch_dmi(), fetch_rmm()
        except Exception as exc:  # network or parse failure -> synthetic
            logger.warning("Teleconnection fetch failed: %s", exc)

    if oni is not None and len(oni) and oni["year"].min() <= start.year:
        out["oni"] = _monthly_to_daily(oni, "oni", full)
        sources["oni"] = "NOAA CPC ONI"
    else:
        out["oni"] = synth["oni"]
        sources["oni"] = "synthetic"

    if dmi is not None and len(dmi) and dmi["year"].min() <= start.year:
        out["dmi"] = _monthly_to_daily(dmi, "dmi", full)
        sources["dmi"] = "NOAA PSL DMI (HadISST)"
    else:
        out["dmi"] = synth["dmi"]
        sources["dmi"] = "synthetic"

    if rmm is not None and len(rmm):
        r = rmm.copy()
        r["date"] = pd.to_datetime(r["date"])
        r = r.drop_duplicates("date").set_index("date").sort_index()
        last_real = r.index.max()
        r = r.reindex(full)
        out["rmm1"] = r["rmm1"]
        out["rmm2"] = r["rmm2"]
        missing = out["rmm1"].isna() & (out.index <= last_real)
        future = out.index > last_real
        out.loc[missing, "rmm1"] = synth.loc[missing, "rmm1"]
        out.loc[missing, "rmm2"] = synth.loc[missing, "rmm2"]
        # Dates after the latest published value: synthetic continuation
        out.loc[future, "rmm1"] = synth.loc[future, "rmm1"]
        out.loc[future, "rmm2"] = synth.loc[future, "rmm2"]
        sources["mjo"] = "BoM MJO RMM" + (" (gaps filled synthetically)" if missing.any() else "")
    else:
        out["rmm1"] = synth["rmm1"]
        out["rmm2"] = synth["rmm2"]
        sources["mjo"] = "synthetic"

    # Months not yet published (current season) -> persist last known value
    out = out.ffill().bfill()
    out = sim.add_mjo_phase(out)
    return out, sources


# ─── Climate (rain + temperature) ────────────────────────────────────────────

def _cache_key(years: list[int], sources: dict) -> str:
    raw = json.dumps({"years": years, "sources": sources, "v": 4}, sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()[:12]


_CLIMATE_CACHE: dict = {}


def load_climate(years: list[int] | None = None) -> sim.ClimateData:
    """Block-level daily climate for the requested Kharif seasons."""
    if years is None:
        years = list(range(FIRST_YEAR, max(DEMO_YEAR, date.today().year) + 1))
    years = sorted(set(years))
    mem_key = tuple(years)
    if mem_key in _CLIMATE_CACHE:
        return _CLIMATE_CACHE[mem_key]

    blocks = load_blocks()
    drivers, sources = load_drivers(date(years[0] - 2, 1, 1), date(years[-1], 12, 31))
    if DEMO_YEAR in years and not CHIRPS_BLOCKS.exists():
        # The demo season's rainfall is a scripted scenario; keep the MJO consistent with it
        drivers = sim.apply_scenario_drivers(drivers)
        sources["mjo"] = sources["mjo"] + f"; {DEMO_YEAR} Kharif: scripted scenario"

    key = _cache_key(years, sources)
    cache_file = PROCESSED_DIR / f"climate_{key}.joblib"
    if cache_file.exists():
        cd = joblib.load(cache_file)
    else:
        logger.info("Simulating block climate for %d seasons (%s-%s)", len(years), years[0], years[-1])
        cd = sim.simulate(blocks, years, drivers)
        cd.sources = dict(sources)
        cd.sources["rainfall"] = "synthetic (teleconnection-driven simulator)"
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(cd, cache_file, compress=3)

    if CHIRPS_BLOCKS.exists():
        cd = _overlay_chirps(cd)

    _CLIMATE_CACHE[mem_key] = cd
    return cd


def _overlay_chirps(cd: sim.ClimateData) -> sim.ClimateData:
    """Replace simulated rain with real CHIRPS block means for every season the cache covers."""
    real = pd.read_parquet(CHIRPS_BLOCKS)  # columns: date, block_id, rainfall_mm
    real["date"] = pd.to_datetime(real["date"])
    wide = real.pivot_table(index="date", columns="block_id", values="rainfall_mm")
    wide = wide.reindex(index=cd.dates, columns=cd.block_ids)
    have = wide.notna().all(axis=1).values
    rain = cd.rain.copy()
    real_years = []
    for y in sorted(set(cd.dates.year)):
        m = cd.dates.year == y
        if have[m].mean() >= 0.9:
            idx = m & have
            rain[idx] = wide.values[idx]
            real_years.append(int(y))
    if not real_years:
        logger.warning("CHIRPS cache covers no complete season; keeping the simulator")
        return cd
    cd.rain = np.round(rain, 1)
    all_years = sorted(set(cd.dates.year))
    cd.is_synthetic = len(real_years) < len(all_years)
    cd.sources["rainfall"] = (f"CHIRPS v2.0 block means for {real_years[0]}-{real_years[-1]} "
                              f"({len(real_years)} seasons)" + ("; simulator elsewhere" if cd.is_synthetic else ""))
    return cd


def driver_snapshot(drivers: pd.DataFrame, d: date) -> dict:
    """Teleconnection state as known on date d (with publication lags)."""
    from data.fetchers.mjo_bsiso import classify_indian_monsoon_impact

    ts = pd.Timestamp(d)

    def at(col, lag_days):
        s = drivers[col].dropna()
        pos = s.index.get_indexer([ts - pd.Timedelta(days=lag_days)], method="pad")[0]
        return float(s.iloc[max(pos, 0)])

    oni = at("oni", 45)
    dmi = at("dmi", 30)
    rmm1, rmm2 = at("rmm1", 1), at("rmm2", 1)
    amp = float(np.hypot(rmm1, rmm2))
    angle = np.degrees(np.arctan2(rmm2, rmm1))
    phase = int(((angle + 180.0) // 45.0) % 8) + 1
    impact = classify_indian_monsoon_impact(phase, amp)
    return {
        "date": str(d),
        "oni": round(oni, 2),
        "enso_phase": "El Niño" if oni >= 0.5 else ("La Niña" if oni <= -0.5 else "Neutral"),
        "dmi": round(dmi, 2),
        "iod_phase": "Positive" if dmi > 0.4 else ("Negative" if dmi < -0.4 else "Neutral"),
        "mjo_phase": phase,
        "mjo_amplitude": round(amp, 2),
        "mjo_active": amp >= 1.0,
        "mjo_impact": impact["monsoon_impact"],
        "mjo_description": impact["description"],
        "u850_anomaly": round(at("u850", 1), 1) if "u850" in drivers else None,
        "olr_anomaly": round(at("olr", 1), 1) if "olr" in drivers else None,
    }
