"""
Varsha — ERA5 Reanalysis Fetcher (Stub)

Downloads ERA5 reanalysis fields from the Copernicus Climate Data Store (CDS).

Requires CDS API key: register at https://cds.climate.copernicus.eu/
Set CDS_API_KEY in .env

Variables of interest:
- 2m temperature (t2m) → for Hargreaves ET₀
- Total precipitation (tp)
- Mean sea level pressure (msl)
- U/V wind at 850 hPa (u850, v850)
- OLR → for BSISO calculation

Usage:
    CDS_API_KEY must be set, or create ~/.cdsapirc
    python -c "from data.fetchers.era5 import fetch_era5; fetch_era5(2023)"
"""

import logging
from datetime import date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CACHE_DIR = Path("data/cache/era5")


def fetch_era5(
    year: int,
    months: list[int] = None,
    variables: list[str] = None,
    bbox: tuple = (77.0, 15.5, 80.0, 18.5),
    cache_dir: Path = CACHE_DIR,
) -> Optional[Path]:
    """
    Download ERA5 reanalysis data for the pilot region.

    Args:
        year: Year to download
        months: List of months (default: May–October)
        variables: List of ERA5 variable names
        bbox: (lon_min, lat_min, lon_max, lat_max)
        cache_dir: Local cache directory

    Returns:
        Path to downloaded NetCDF file, or None
    """
    if months is None:
        months = [5, 6, 7, 8, 9, 10]
    if variables is None:
        variables = [
            "2m_temperature",
            "total_precipitation",
            "mean_sea_level_pressure",
        ]

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"era5_{year}_{'_'.join(str(m) for m in months)}.nc"

    if cache_file.exists():
        logger.debug(f"ERA5 cache hit: {cache_file}")
        return cache_file

    try:
        import cdsapi
        c = cdsapi.Client()

        # North, West, South, East for CDS API
        area = [bbox[3], bbox[0], bbox[1], bbox[2]]

        c.retrieve(
            "reanalysis-era5-single-levels",
            {
                "product_type": "reanalysis",
                "format": "netcdf",
                "variable": variables,
                "year": str(year),
                "month": [f"{m:02d}" for m in months],
                "day": [f"{d:02d}" for d in range(1, 32)],
                "time": ["00:00", "06:00", "12:00", "18:00"],
                "area": area,
            },
            str(cache_file),
        )
        logger.info(f"Downloaded ERA5: {cache_file}")
        return cache_file

    except ImportError:
        logger.warning("cdsapi not installed. Install with: pip install cdsapi")
        return None
    except Exception as e:
        logger.error(f"ERA5 download failed: {e}")
        logger.info("Ensure CDS_API_KEY is set and ~/.cdsapirc exists")
        return None
