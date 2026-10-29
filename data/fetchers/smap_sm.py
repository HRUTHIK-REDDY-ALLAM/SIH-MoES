"""
Varsha — SMAP Soil Moisture Fetcher (Stub)

Downloads NASA SMAP L3 soil moisture from Earthdata.
Requires NASA Earthdata login: https://urs.earthdata.nasa.gov/
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)
CACHE_DIR = Path("data/cache/smap")


def fetch_smap(target_date, cache_dir=CACHE_DIR):
    """Fetch SMAP soil moisture. Stub — to be implemented in M2."""
    logger.info(f"SMAP fetch for {target_date}: NOT YET IMPLEMENTED")
    cache_dir.mkdir(parents=True, exist_ok=True)
    return None
