"""
Varsha — SRTM DEM Fetcher (Stub)

Downloads SRTM (Shuttle Radar Topography Mission) DEM data.
Used for elevation-based features (orographic rainfall enhancement).

Source: https://dwtkns.com/srtm30m/ or OpenTopography
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)
CACHE_DIR = Path("data/cache/srtm")


def fetch_srtm(bbox, cache_dir=CACHE_DIR):
    """Fetch SRTM DEM tiles. Stub — to be implemented in M2."""
    logger.info(f"SRTM fetch for bbox {bbox}: NOT YET IMPLEMENTED")
    cache_dir.mkdir(parents=True, exist_ok=True)
    return None
