"""
Varsha — MJO RMM and BSISO Index Fetcher

Downloads:
1. MJO Real-time Multivariate MJO (RMM) index from BoM Australia
2. BSISO (Boreal Summer Intraseasonal Oscillation) indices

MJO/BSISO phase strongly modulates Indian monsoon active/break spells.

Sources:
- RMM: http://www.bom.gov.au/climate/mjo/graphics/rmm.74toRealtime.txt
- BSISO: from APCC or calculated from OLR/U850 fields

No credentials required for RMM.
"""

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import httpx
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

RMM_URL = "http://www.bom.gov.au/climate/mjo/graphics/rmm.74toRealtime.txt"
CACHE_DIR = Path("data/cache/mjo")


def fetch_rmm(cache_dir: Path = CACHE_DIR) -> Optional[pd.DataFrame]:
    """
    Fetch the MJO RMM index time series.

    Returns:
        DataFrame with columns: [date, rmm1, rmm2, phase, amplitude]
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "rmm.csv"

    if cache_file.exists():
        import os
        mtime = datetime.fromtimestamp(os.path.getmtime(cache_file))
        if datetime.now() - mtime < pd.Timedelta(days=3):
            return pd.read_csv(cache_file, parse_dates=["date"])

    logger.info(f"Fetching RMM from {RMM_URL}")
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(RMM_URL)
            resp.raise_for_status()

        lines = resp.text.strip().split("\n")
        records = []

        for line in lines[2:]:  # Skip header lines
            parts = line.split()
            if len(parts) >= 7:
                try:
                    year = int(parts[0])
                    month = int(parts[1])
                    day = int(parts[2])
                    rmm1 = float(parts[3])
                    rmm2 = float(parts[4])
                    phase = int(parts[5])
                    amplitude = float(parts[6])

                    # Skip missing values
                    if rmm1 > 90 or rmm2 > 90:
                        continue

                    records.append({
                        "date": date(year, month, day),
                        "rmm1": rmm1,
                        "rmm2": rmm2,
                        "phase": phase,
                        "amplitude": amplitude,
                    })
                except (ValueError, IndexError):
                    continue

        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"])
        df.to_csv(cache_file, index=False)
        logger.info(f"RMM data: {len(df)} days, {df['date'].min()} to {df['date'].max()}")
        return df

    except Exception as e:
        logger.error(f"Failed to fetch RMM: {e}")
        if cache_file.exists():
            return pd.read_csv(cache_file, parse_dates=["date"])
        return None


def get_mjo_for_date(target_date: date, df: pd.DataFrame = None) -> Optional[dict]:
    """Get MJO RMM values for a given date."""
    if df is None:
        df = fetch_rmm()
    if df is None:
        return None

    target_dt = pd.Timestamp(target_date)
    row = df[df["date"] == target_dt]
    if row.empty:
        # Try nearest date within 3 days
        df["diff"] = abs(df["date"] - target_dt)
        nearest = df.loc[df["diff"].idxmin()]
        if nearest["diff"].days <= 3:
            row = nearest
        else:
            return None
    else:
        row = row.iloc[0]

    return {
        "rmm1": float(row["rmm1"]),
        "rmm2": float(row["rmm2"]),
        "phase": int(row["phase"]),
        "amplitude": float(row["amplitude"]),
        "is_active": float(row["amplitude"]) >= 1.0,
    }


def classify_indian_monsoon_impact(phase: int, amplitude: float) -> dict:
    """
    Classify MJO impact on Indian monsoon based on phase.

    Phases 1-2: Enhanced convection over Indian Ocean → active monsoon
    Phases 3-4: Convection over Maritime Continent → transition
    Phases 5-6: Convection over W Pacific → break phase
    Phases 7-8: Convection over W Hemisphere / Africa → return to active

    Returns:
        dict with monsoon_impact and description
    """
    if amplitude < 1.0:
        return {
            "monsoon_impact": "weak_mjo",
            "description": "MJO is weak — limited influence on monsoon",
        }

    impact_map = {
        1: ("active_likely", "Enhanced convection approaching India — active spell likely"),
        2: ("active_likely", "Active MJO over Indian Ocean — wet conditions favoured"),
        3: ("transition", "Convection moving east — transition period"),
        4: ("break_risk", "Convection east of India — drying tendency"),
        5: ("break_likely", "Suppressed convection over India — break spell likely"),
        6: ("break_likely", "Suppressed phase — dry conditions favoured"),
        7: ("recovery", "Convection returning west — monsoon recovery beginning"),
        8: ("active_approaching", "Active phase approaching India from west"),
    }

    impact, desc = impact_map.get(phase, ("unknown", "Unknown phase"))
    return {"monsoon_impact": impact, "description": desc}
