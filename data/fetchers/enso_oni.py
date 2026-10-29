"""
Varsha — NOAA CPC ENSO/ONI Index Fetcher

Downloads the Oceanic Niño Index (ONI) and Niño 3.4 SST data
from NOAA Climate Prediction Center (CPC).

Source: https://www.cpc.ncep.noaa.gov/data/indices/
No credentials required — fully open.

ONI: 3-month running mean of Niño 3.4 SST anomalies
- El Niño: ONI >= +0.5 for 5 consecutive overlapping 3-month periods
- La Niña: ONI <= -0.5 for 5 consecutive overlapping 3-month periods
"""

import logging
from datetime import date
from pathlib import Path
from typing import Optional

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

# NOAA CPC data URLs
ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
NINO34_URL = "https://www.cpc.ncep.noaa.gov/data/indices/sstoi.indices"

CACHE_DIR = Path("data/cache/enso")


def fetch_oni(cache_dir: Path = CACHE_DIR) -> Optional[pd.DataFrame]:
    """
    Fetch the ONI (Oceanic Niño Index) time series.

    Returns:
        DataFrame with columns: [year, month, oni, phase]
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "oni.csv"

    # Re-download if older than 7 days or missing
    if cache_file.exists():
        import os
        from datetime import datetime, timedelta
        mtime = datetime.fromtimestamp(os.path.getmtime(cache_file))
        if datetime.now() - mtime < timedelta(days=7):
            logger.debug("ONI cache hit")
            return pd.read_csv(cache_file)

    logger.info(f"Fetching ONI from {ONI_URL}")
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(ONI_URL)
            resp.raise_for_status()

        # Parse the fixed-width format
        lines = resp.text.strip().split("\n")
        records = []

        # Map 3-letter season codes to month numbers
        season_to_month = {
            "DJF": 1, "JFM": 2, "FMA": 3, "MAM": 4,
            "AMJ": 5, "MJJ": 6, "JJA": 7, "JAS": 8,
            "ASO": 9, "SON": 10, "OND": 11, "NDJ": 12,
        }

        for line in lines[1:]:  # Skip header
            parts = line.split()
            if len(parts) >= 4:
                try:
                    season = parts[0]
                    year = int(parts[1])
                    oni = float(parts[3])  # ANOM column

                    month = season_to_month.get(season, None)
                    if month is None:
                        continue

                    # Classify phase
                    if oni >= 0.5:
                        phase = "el_nino"
                    elif oni <= -0.5:
                        phase = "la_nina"
                    else:
                        phase = "neutral"

                    records.append({
                        "year": year,
                        "month": month,
                        "season": season,
                        "oni": oni,
                        "phase": phase,
                    })
                except (ValueError, IndexError):
                    continue

        df = pd.DataFrame(records)
        df.to_csv(cache_file, index=False)
        logger.info(f"ONI data: {len(df)} records, {df['year'].min()}-{df['year'].max()}")
        return df

    except Exception as e:
        logger.error(f"Failed to fetch ONI: {e}")
        if cache_file.exists():
            logger.info("Using cached ONI data")
            return pd.read_csv(cache_file)
        return None


def get_oni_for_date(target_date: date, df: pd.DataFrame = None) -> Optional[dict]:
    """
    Get the ONI value and ENSO phase for a given date.

    Returns:
        dict with keys: oni, phase, season
    """
    if df is None:
        df = fetch_oni()
    if df is None:
        return None

    # Find the closest 3-month season for this date
    row = df[(df["year"] == target_date.year) & (df["month"] == target_date.month)]
    if row.empty:
        # Try previous month
        row = df[(df["year"] == target_date.year) & (df["month"] == target_date.month - 1)]
    if row.empty:
        return None

    row = row.iloc[0]
    return {
        "oni": row["oni"],
        "phase": row["phase"],
        "season": row.get("season", ""),
    }
