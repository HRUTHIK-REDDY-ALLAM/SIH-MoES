"""
Varsha — Indian Ocean Dipole (IOD) DMI Fetcher

Downloads the Dipole Mode Index (DMI) from NOAA PSL or
the Bureau of Meteorology (BoM) Australia.

The IOD is defined as the difference in SST anomaly between
the western (50°E–70°E, 10°S–10°N) and eastern
(90°E–110°E, 10°S–0°) equatorial Indian Ocean.

Positive IOD → enhanced Indian monsoon rainfall
Negative IOD → suppressed Indian monsoon rainfall

Source: https://psl.noaa.gov/gcos_wgsp/Timeseries/DMI/
No credentials required.
"""

import logging
from datetime import date
from pathlib import Path
from typing import Optional

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

DMI_URL = "https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data"
CACHE_DIR = Path("data/cache/iod")


def fetch_dmi(cache_dir: Path = CACHE_DIR) -> Optional[pd.DataFrame]:
    """
    Fetch the monthly DMI time series.

    Returns:
        DataFrame with columns: [year, month, dmi, phase]
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "dmi.csv"

    if cache_file.exists():
        import os
        from datetime import datetime, timedelta
        mtime = datetime.fromtimestamp(os.path.getmtime(cache_file))
        if datetime.now() - mtime < timedelta(days=7):
            return pd.read_csv(cache_file)

    logger.info(f"Fetching DMI from {DMI_URL}")
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(DMI_URL)
            resp.raise_for_status()

        lines = resp.text.strip().split("\n")
        records = []

        for line in lines:
            parts = line.split()
            if len(parts) >= 13:
                try:
                    year = int(parts[0])
                    if year < 1900 or year > 2100:
                        continue
                    for month_idx in range(12):
                        val = float(parts[month_idx + 1])
                        if val > -90:  # Missing data marker
                            phase = "positive" if val > 0.4 else ("negative" if val < -0.4 else "neutral")
                            records.append({
                                "year": year,
                                "month": month_idx + 1,
                                "dmi": val,
                                "phase": phase,
                            })
                except (ValueError, IndexError):
                    continue

        df = pd.DataFrame(records)
        df.to_csv(cache_file, index=False)
        logger.info(f"DMI data: {len(df)} records, {df['year'].min()}-{df['year'].max()}")
        return df

    except Exception as e:
        logger.error(f"Failed to fetch DMI: {e}")
        if cache_file.exists():
            return pd.read_csv(cache_file)
        return None


def get_dmi_for_date(target_date: date, df: pd.DataFrame = None) -> Optional[dict]:
    """Get DMI value and IOD phase for a given date."""
    if df is None:
        df = fetch_dmi()
    if df is None:
        return None

    row = df[(df["year"] == target_date.year) & (df["month"] == target_date.month)]
    if row.empty:
        return None

    row = row.iloc[0]
    return {"dmi": row["dmi"], "phase": row["phase"]}
