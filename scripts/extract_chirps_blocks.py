"""
Varsha — Build the real-rainfall cache from CHIRPS v2.0 (optional).

    pip install rasterio
    python scripts/extract_chirps_blocks.py --start 1991 --end 2023

Downloads CHIRPS daily GeoTIFFs (0.05 deg, ~5 km) for Apr 1 - Nov 30 of each
year, averages the pixels inside every block polygon and writes
data/processed/chirps_blocks.parquet (date, block_id, rainfall_mm).
When that file exists, data/sources.load_climate() uses it instead of the
simulator and all outputs are flagged is_synthetic = False.

Note: ~240 files (~1 MB each) per season; a 33-year archive is ~8 GB of
downloads. Start with a few seasons to try it out. Requires rasterio, which
is not installed by default.
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.fetchers.chirps import fetch_daily  # noqa: E402
from data.sources import BOUNDARY_DIR, CHIRPS_BLOCKS  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("chirps_blocks")
BBOX = (76.9, 15.4, 80.1, 18.6)


def block_masks(transform, shape, blocks_gj):
    from rasterio.features import geometry_mask

    return {f["properties"]["id"]: ~geometry_mask([f["geometry"]], out_shape=shape, transform=transform, all_touched=True)
            for f in blocks_gj["features"]}


def read_window(path: Path):
    import rasterio
    from rasterio.windows import from_bounds

    with gzip.open(path, "rb") as gz, tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp.write(gz.read())
        tif = Path(tmp.name)
    try:
        with rasterio.open(tif) as src:
            win = from_bounds(*BBOX, transform=src.transform)
            data = src.read(1, window=win).astype(float)
            transform = src.window_transform(win)
        data[data < 0] = np.nan
        return data, transform
    finally:
        tif.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=2019)
    ap.add_argument("--end", type=int, default=2023)
    args = ap.parse_args()
    blocks_gj = json.loads((BOUNDARY_DIR / "blocks.geojson").read_text(encoding="utf-8"))
    rows, masks = [], None
    for year in range(args.start, args.end + 1):
        d = date(year, 4, 1)
        while d <= date(year, 11, 30):
            f = fetch_daily(d)
            if f is not None:
                data, transform = read_window(f)
                if masks is None:
                    masks = block_masks(transform, data.shape, blocks_gj)
                for bid, m in masks.items():
                    rows.append({"date": d, "block_id": bid, "rainfall_mm": float(np.nanmean(data[m]))})
            d += timedelta(days=1)
        logger.info("Season %s done (%d rows so far)", year, len(rows))
    CHIRPS_BLOCKS.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(CHIRPS_BLOCKS, index=False)
    logger.info("Wrote %s", CHIRPS_BLOCKS)


if __name__ == "__main__":
    main()
