"""
Varsha — Pilot region boundaries -> GeoJSON + database.

    python scripts/load_boundaries.py                # rebuild panchayat polygons + load DB
    python scripts/load_boundaries.py --regenerate   # also regenerate block/district polygons

Real LGD/GADM boundaries are not bundled, so blocks and districts are
SYNTHETIC approximations (hexagons around grid centroids, flagged
is_synthetic). Panchayats are Voronoi cells of their centroids clipped to
their block, so a panchayat-level risk map can be drawn. Each panchayat gets
soil hydraulic properties (red sandy loam / red loam / black cotton soil) and
an irrigated fraction, which drive the panchayat water balance.

Replace data/sample/boundaries/*.geojson with real LGD boundaries (same
property names) and re-run this script to switch to real geography.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import zlib
from pathlib import Path

import numpy as np
import shapely
import yaml
from shapely.geometry import MultiPoint, Point, mapping, shape

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.climate_simulator import synthetic_elevation  # noqa: E402
from impact.water_balance import SOIL_TYPES  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("load_boundaries")

SAMPLE_DIR = ROOT / "data" / "sample" / "boundaries"
FRONTEND_DIR = ROOT / "frontend" / "public" / "boundaries"

# Blocks largely inside the Nagarjuna Sagar left-canal command have more irrigation
CANAL_BLOCKS = {"Miryalaguda", "Haliya", "Huzurnagar", "Kodad", "Nakrekal", "Suryapet"}


def load_config() -> dict:
    with open(ROOT / "config" / "pilot_region.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _seed(name: str) -> int:
    return zlib.crc32(name.encode("utf-8")) % 100_000


# ─── Synthetic district / block polygons (only with --regenerate) ────────────

def generate_synthetic_block_boundaries(config: dict) -> dict:
    features, block_id = [], 1
    for district in config["districts"]:
        lon_min, lat_min, lon_max, lat_max = district["bbox"]
        blocks = district["blocks"]
        n_cols = max(2, int(np.ceil(np.sqrt(len(blocks)))))
        n_rows = max(2, int(np.ceil(len(blocks) / n_cols)))
        grid = [(lo, la) for la in np.linspace(lat_min + 0.1, lat_max - 0.1, n_rows)
                for lo in np.linspace(lon_min + 0.1, lon_max - 0.1, n_cols)]
        rng = np.random.RandomState(42 + _seed(district["name"]) % 1000)
        for i, name in enumerate(blocks):
            cx, cy = grid[i] if i < len(grid) else ((lon_min + lon_max) / 2, (lat_min + lat_max) / 2)
            cx += rng.uniform(-0.05, 0.05)
            cy += rng.uniform(-0.05, 0.05)
            angles = np.linspace(0, 2 * np.pi, 7)[:-1] + rng.uniform(0, np.pi / 6)
            radii = 0.15 * (1 + rng.uniform(-0.15, 0.15, 6))
            coords = [[float(cx + r * np.cos(a)), float(cy + r * np.sin(a))] for a, r in zip(angles, radii)]
            coords.append(coords[0])
            features.append({"type": "Feature", "properties": {
                "id": block_id, "name": name, "district": district["name"],
                "district_lgd_code": district["lgd_code"], "centroid_lat": float(cy),
                "centroid_lon": float(cx), "is_synthetic": True},
                "geometry": {"type": "Polygon", "coordinates": [coords]}})
            block_id += 1
    return {"type": "FeatureCollection", "features": features,
            "_warning": "SYNTHETIC boundaries - not real administrative boundaries"}


def generate_synthetic_district_boundaries(config: dict) -> dict:
    features = []
    for i, d in enumerate(config["districts"]):
        lon_min, lat_min, lon_max, lat_max = d["bbox"]
        m = 0.05
        coords = [[lon_min + m, lat_min + m], [lon_max - m, lat_min + m], [lon_max - m, lat_max - m],
                  [lon_min + m, lat_max - m], [lon_min + m, lat_min + m]]
        features.append({"type": "Feature", "properties": {
            "id": i + 1, "name": d["name"], "lgd_code": d["lgd_code"], "state": config["state"]["name"],
            "is_synthetic": True}, "geometry": {"type": "Polygon", "coordinates": [coords]}})
    return {"type": "FeatureCollection", "features": features, "_warning": "SYNTHETIC boundaries"}


# ─── Panchayats: centroids -> Voronoi polygons + soil ────────────────────────

def soil_for(panchayat_id: int, lat: float, lon: float) -> tuple[str, float, float]:
    rng = np.random.default_rng(1000 + panchayat_id)
    p_black = 1 / (1 + np.exp(-(lat - 17.3) * 3.0))      # black soils more common to the north
    p_red_sandy = 1 / (1 + np.exp((lat - 16.4) * 3.0))   # light red soils to the south
    u = rng.random()
    soil = "black_cotton" if u < p_black else ("red_sandy_loam" if u < p_black + p_red_sandy else "red_loam")
    fc, wp = SOIL_TYPES[soil]
    jitter = rng.normal(0, 0.012)
    return soil, round(fc + jitter, 3), round(wp + jitter / 2, 3)


def build_panchayats(blocks_gj: dict, panch_gj: dict | None, per_block: int = 5) -> dict:
    block_shapes = {f["properties"]["id"]: shape(f["geometry"]) for f in blocks_gj["features"]}
    block_names = {f["properties"]["id"]: f["properties"]["name"] for f in blocks_gj["features"]}
    rng = np.random.RandomState(123)
    if panch_gj is None:  # create centroids inside each block
        panch_gj = {"features": []}
        pid = 1
        for f in blocks_gj["features"]:
            poly = block_shapes[f["properties"]["id"]]
            for j in range(per_block):
                while True:
                    x = f["properties"]["centroid_lon"] + rng.uniform(-0.1, 0.1)
                    y = f["properties"]["centroid_lat"] + rng.uniform(-0.1, 0.1)
                    if poly.contains(Point(x, y)):
                        break
                panch_gj["features"].append({"properties": {
                    "id": pid, "name": f"{f['properties']['name']} GP-{j + 1}", "block_id": f["properties"]["id"],
                    "block_name": f["properties"]["name"], "centroid_lat": y, "centroid_lon": x}})
                pid += 1

    by_block: dict[int, list[dict]] = {}
    for f in panch_gj["features"]:
        by_block.setdefault(int(f["properties"]["block_id"]), []).append(dict(f["properties"]))

    features = []
    for bid, items in by_block.items():
        poly = block_shapes[bid]
        pts = []
        for p in items:
            pt = Point(p["centroid_lon"], p["centroid_lat"])
            if not poly.contains(pt):  # pull outside centroids into the block
                pt = shapely.ops.nearest_points(poly.buffer(-0.01), pt)[0]
                p["centroid_lon"], p["centroid_lat"] = pt.x, pt.y
            pts.append(pt)
        cells = shapely.voronoi_polygons(MultiPoint(pts), extend_to=poly.buffer(0.2))
        cell_list = list(cells.geoms)
        for p, pt in zip(items, pts):
            cell = next((c for c in cell_list if c.contains(pt)), None)
            geom = (cell.intersection(poly) if cell is not None else pt.buffer(0.03).intersection(poly))
            soil, fc, wp = soil_for(int(p["id"]), p["centroid_lat"], p["centroid_lon"])
            irr_rng = np.random.default_rng(5000 + int(p["id"]))
            irr = irr_rng.uniform(0.45, 0.7) if block_names[bid] in CANAL_BLOCKS else irr_rng.uniform(0.1, 0.35)
            features.append({"type": "Feature", "properties": {
                "id": int(p["id"]), "name": p["name"], "block_id": bid, "block_name": block_names[bid],
                "centroid_lat": round(float(p["centroid_lat"]), 5), "centroid_lon": round(float(p["centroid_lon"]), 5),
                "soil_type": soil, "field_capacity": fc, "wilting_point": wp,
                "irrigated_fraction": round(float(irr), 2), "is_synthetic": True},
                "geometry": mapping(geom)})
    features.sort(key=lambda f: f["properties"]["id"])
    return {"type": "FeatureCollection", "features": features,
            "_warning": "SYNTHETIC panchayat names, locations, polygons and soils"}


def add_block_elevation(blocks_gj: dict) -> dict:
    for f in blocks_gj["features"]:
        p = f["properties"]
        p["elevation_m"] = round(synthetic_elevation(p["centroid_lat"], p["centroid_lon"]), 1)
    return blocks_gj


def save_geojson(data: dict, filepath: Path):
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    logger.info("Saved %s (%d features)", filepath.relative_to(ROOT), len(data["features"]))


# ─── Database ────────────────────────────────────────────────────────────────

def load_to_database(config: dict, districts_gj: dict, blocks_gj: dict, panchayats_gj: dict):
    from backend.db.models import Base, Block, District, Panchayat
    from backend.db.session import SyncSession, sync_engine

    Base.metadata.create_all(sync_engine)
    with SyncSession() as s:
        dist_id = {}
        for f in districts_gj["features"]:
            p = f["properties"]
            s.merge(District(id=p["id"], name=p["name"], state=p.get("state", "Telangana"),
                             lgd_code=p["lgd_code"], geometry=f["geometry"], is_synthetic=True))
            dist_id[p["name"]] = p["id"]
        for f in blocks_gj["features"]:
            p = f["properties"]
            s.merge(Block(id=p["id"], name=p["name"], district_id=dist_id[p["district"]],
                          centroid_lat=p["centroid_lat"], centroid_lon=p["centroid_lon"],
                          elevation_m=p.get("elevation_m"), geometry=f["geometry"], is_synthetic=True))
        for f in panchayats_gj["features"]:
            p = f["properties"]
            s.merge(Panchayat(id=p["id"], name=p["name"], block_id=p["block_id"],
                              centroid_lat=p["centroid_lat"], centroid_lon=p["centroid_lon"],
                              geometry=f["geometry"], soil_type=p["soil_type"],
                              field_capacity=p["field_capacity"], wilting_point=p["wilting_point"],
                              irrigated_fraction=p["irrigated_fraction"], is_synthetic=True))
        s.commit()
        if sync_engine.dialect.name == "postgresql":  # explicit ids -> move sequences past them
            from sqlalchemy import text
            for table in ("districts", "blocks", "panchayats"):
                s.execute(text(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                               f"(SELECT COALESCE(MAX(id), 1) FROM {table}))"))
            s.commit()
    logger.info("Loaded %d districts, %d blocks, %d panchayats into the database",
                len(districts_gj["features"]), len(blocks_gj["features"]), len(panchayats_gj["features"]))


def build_all(regenerate: bool = False) -> tuple[dict, dict, dict]:
    config = load_config()
    if regenerate:
        districts_gj = generate_synthetic_district_boundaries(config)
        blocks_gj = generate_synthetic_block_boundaries(config)
        panch_src = None
    else:
        districts_gj = json.loads((SAMPLE_DIR / "districts.geojson").read_text(encoding="utf-8"))
        blocks_gj = json.loads((SAMPLE_DIR / "blocks.geojson").read_text(encoding="utf-8"))
        panch_src = json.loads((SAMPLE_DIR / "panchayats.geojson").read_text(encoding="utf-8"))
    blocks_gj = add_block_elevation(blocks_gj)
    panchayats_gj = build_panchayats(blocks_gj, panch_src)
    for name, gj in (("districts", districts_gj), ("blocks", blocks_gj), ("panchayats", panchayats_gj)):
        save_geojson(gj, SAMPLE_DIR / f"{name}.geojson")
        save_geojson(gj, FRONTEND_DIR / f"{name}.geojson")
    return districts_gj, blocks_gj, panchayats_gj


def main():
    ap = argparse.ArgumentParser(description="Build pilot boundaries and load them into the DB")
    ap.add_argument("--regenerate", action="store_true", help="regenerate synthetic block/district polygons")
    ap.add_argument("--no-db", action="store_true", help="only write GeoJSON files")
    args = ap.parse_args()
    d, b, p = build_all(args.regenerate)
    if not args.no_db:
        load_to_database(load_config(), d, b, p)


if __name__ == "__main__":
    main()
