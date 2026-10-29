"""
Varsha — CHIRPS Daily Rainfall Fetcher

Downloads CHIRPS 2.0 daily gridded rainfall (0.05° resolution) from the
Climate Hazards Center (CHC), UCSB.

Source: https://data.chc.ucsb.edu/products/CHIRPS-2.0/
Format: GeoTIFF (daily) or NetCDF
Coverage: 50°S–50°N, quasi-global
Resolution: 0.05° (~5.5 km)
Latency: ~3 weeks for final; ~2 days for preliminary

No credentials required — fully open.
"""

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import httpx
import numpy as np

logger = logging.getLogger(__name__)

CHIRPS_BASE = "https://data.chc.ucsb.edu/products/CHIRPS-2.0"
CACHE_DIR = Path("data/cache/chirps")


def get_daily_url(target_date: date, fmt: str = "tifs") -> str:
    """
    Construct the download URL for a CHIRPS daily file.

    Args:
        target_date: Date to fetch
        fmt: 'tifs' for GeoTIFF, 'netcdf' for NetCDF

    Returns:
        URL string
    """
    year = target_date.year
    month = target_date.month
    day = target_date.day

    if fmt == "tifs":
        # CHIRPS daily GeoTIFF: /global_daily/tifs/p05/2023/chirps-v2.0.2023.08.10.tif.gz
        filename = f"chirps-v2.0.{year}.{month:02d}.{day:02d}.tif.gz"
        return f"{CHIRPS_BASE}/global_daily/{fmt}/p05/{year}/{filename}"
    else:
        raise ValueError(f"Unknown format: {fmt}")


def get_monthly_url(year: int, month: int) -> str:
    """Construct URL for CHIRPS monthly totals (NetCDF)."""
    filename = f"chirps-v2.0.{year}.{month:02d}.tif.gz"
    return f"{CHIRPS_BASE}/global_monthly/tifs/{filename}"


def fetch_daily(
    target_date: date,
    bbox: tuple = (77.0, 15.5, 80.0, 18.5),
    cache_dir: Path = CACHE_DIR,
) -> Optional[Path]:
    """
    Download CHIRPS daily rainfall for the pilot region.

    Args:
        target_date: Date to fetch
        bbox: (lon_min, lat_min, lon_max, lat_max) for clipping
        cache_dir: Local cache directory

    Returns:
        Path to cached file, or None if download fails
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"chirps_{target_date.isoformat()}.tif.gz"

    if cache_file.exists():
        logger.debug(f"CHIRPS cache hit: {cache_file}")
        return cache_file

    url = get_daily_url(target_date)
    logger.info(f"Fetching CHIRPS: {url}")

    try:
        with httpx.Client(timeout=60) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                cache_file.write_bytes(resp.content)
                logger.info(f"Downloaded: {cache_file} ({len(resp.content)} bytes)")
                return cache_file
            elif resp.status_code == 404:
                logger.warning(f"CHIRPS data not available for {target_date} (404)")
                return None
            else:
                logger.error(f"CHIRPS download failed: HTTP {resp.status_code}")
                return None
    except Exception as e:
        logger.error(f"CHIRPS download error: {e}")
        return None


def fetch_date_range(
    start_date: date,
    end_date: date,
    bbox: tuple = (77.0, 15.5, 80.0, 18.5),
) -> list[Path]:
    """Download CHIRPS data for a date range."""
    files = []
    current = start_date
    while current <= end_date:
        f = fetch_daily(current, bbox)
        if f:
            files.append(f)
        current += timedelta(days=1)
    logger.info(f"Downloaded {len(files)} CHIRPS files for {start_date} to {end_date}")
    return files


def load_to_array(filepath: Path, bbox: tuple = None) -> Optional[np.ndarray]:
    """
    Load a CHIRPS GeoTIFF into a numpy array, optionally clipped to bbox.

    Returns:
        2D numpy array of rainfall in mm, or None
    """
    try:
        import rasterio
        import gzip

        # Decompress if gzipped
        if filepath.suffix == ".gz":
            import tempfile
            with gzip.open(filepath, "rb") as gz:
                tmp = Path(tempfile.mktemp(suffix=".tif"))
                tmp.write_bytes(gz.read())
            filepath = tmp

        with rasterio.open(filepath) as src:
            if bbox:
                from rasterio.windows import from_bounds
                window = from_bounds(*bbox, transform=src.transform)
                data = src.read(1, window=window)
            else:
                data = src.read(1)

            # CHIRPS uses -9999 as nodata
            data = np.where(data < 0, np.nan, data)
            return data

    except ImportError:
        logger.warning("rasterio not installed — cannot load CHIRPS GeoTIFF")
        return None
    except Exception as e:
        logger.error(f"Error loading CHIRPS file: {e}")
        return None
