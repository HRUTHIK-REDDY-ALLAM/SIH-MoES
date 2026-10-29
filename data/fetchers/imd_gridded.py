"""
Varsha — IMD 0.25° Gridded Rainfall Fetcher (Stub)

IMD gridded data requires institutional access or manual download from:
https://www.imdpune.gov.in/cmpg/Griddata/Rainfall_25_Bin.html

Steps to acquire:
1. Register at IMD Pune data portal
2. Request 0.25° daily gridded rainfall (binary format)
3. Download and place in data/cache/imd/
4. Run this script to convert binary → NetCDF

Binary format: 0.25° × 0.25° grid over India (31×31 for each day)
Each record: 4-byte float, little-endian

For the prototype, we use CHIRPS as the primary rainfall source.
IMD is documented here for upgrade path.
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

CACHE_DIR = Path("data/cache/imd")

# IMD 0.25° grid specifications
IMD_LAT_MIN, IMD_LAT_MAX = 6.5, 38.5
IMD_LON_MIN, IMD_LON_MAX = 66.5, 100.0
IMD_RESOLUTION = 0.25
IMD_NLAT = int((IMD_LAT_MAX - IMD_LAT_MIN) / IMD_RESOLUTION) + 1  # 129
IMD_NLON = int((IMD_LON_MAX - IMD_LON_MIN) / IMD_RESOLUTION) + 1  # 135


def load_imd_binary(filepath: Path, year: int) -> Optional[np.ndarray]:
    """
    Load IMD 0.25° binary rainfall data for a year.

    The binary file contains 365 (or 366) days × NLAT × NLON float32 values.

    Args:
        filepath: Path to the binary file (e.g., Rainfall_ind2023_rfp25.grd)
        year: Year of data

    Returns:
        3D array (days, lat, lon) of rainfall in mm, or None
    """
    if not filepath.exists():
        logger.warning(f"IMD file not found: {filepath}")
        logger.info("Download from https://www.imdpune.gov.in/cmpg/Griddata/Rainfall_25_Bin.html")
        return None

    import calendar
    n_days = 366 if calendar.isleap(year) else 365

    try:
        data = np.fromfile(filepath, dtype="<f4")
        expected = n_days * IMD_NLAT * IMD_NLON
        if data.size != expected:
            logger.error(f"IMD file size mismatch: {data.size} vs expected {expected}")
            return None

        data = data.reshape(n_days, IMD_NLAT, IMD_NLON)
        data[data < 0] = np.nan  # Missing value
        logger.info(f"Loaded IMD data: {year}, shape={data.shape}")
        return data

    except Exception as e:
        logger.error(f"Error loading IMD binary: {e}")
        return None


def extract_pilot_region(data: np.ndarray, bbox: tuple) -> np.ndarray:
    """
    Extract data for the pilot region from the full India grid.

    Args:
        data: Full IMD grid (days, lat, lon)
        bbox: (lon_min, lat_min, lon_max, lat_max)
    """
    lon_min, lat_min, lon_max, lat_max = bbox

    lat_idx_start = int((lat_min - IMD_LAT_MIN) / IMD_RESOLUTION)
    lat_idx_end = int((lat_max - IMD_LAT_MIN) / IMD_RESOLUTION) + 1
    lon_idx_start = int((lon_min - IMD_LON_MIN) / IMD_RESOLUTION)
    lon_idx_end = int((lon_max - IMD_LON_MIN) / IMD_RESOLUTION) + 1

    return data[:, lat_idx_start:lat_idx_end, lon_idx_start:lon_idx_end]
