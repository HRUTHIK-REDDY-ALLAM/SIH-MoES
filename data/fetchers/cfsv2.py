"""
Varsha — CFSv2 Forecast Fetcher (Stub)

Downloads CFSv2 (Climate Forecast System version 2) forecasts from NOAA NOMADS.
CFSv2 provides 16-day deterministic and 45-day ensemble forecasts.

Source: https://nomads.ncep.noaa.gov/pub/data/nccf/com/cfs/prod/
No credentials required.

For the prototype, we pre-cache 2023 season forecasts.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)
CACHE_DIR = Path("data/cache/cfsv2")


def fetch_cfsv2_forecast(issue_date, cache_dir=CACHE_DIR):
    """Fetch CFSv2 forecast for a given issue date. Stub — to be implemented in M2."""
    logger.info(f"CFSv2 fetch for {issue_date}: NOT YET IMPLEMENTED")
    cache_dir.mkdir(parents=True, exist_ok=True)
    return None
