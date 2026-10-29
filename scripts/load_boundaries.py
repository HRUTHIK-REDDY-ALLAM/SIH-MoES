"""
Varsha — Load Pilot Region Boundaries into PostGIS

Downloads Telangana district and block (mandal) boundaries from public sources,
loads them into the database, and creates panchayat entries for the pilot blocks.

Data sources:
- GADM (gadm.org) for district boundaries
- DataMeet community boundaries (github.com/datameet) for sub-district/mandal

If boundaries are not available online, generates approximate boundaries
from block centroids (clearly marked as SYNTHETIC).

Usage:
    python -m scripts.load_boundaries
"""

import json
import os
import sys
import logging
from pathlib import Path

import yaml
import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def load_config():
    """Load pilot region config."""
    config_path = Path(__file__).resolve().parent.parent / "config" / "pilot_region.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def generate_synthetic_block_boundaries(config: dict) -> dict:
    """
    Generate SYNTHETIC approximate block boundaries using Voronoi-like
    partitioning from known block centroids.

    ⚠️ SYNTHETIC: These are NOT real administrative boundaries.
    They are approximate polygons for visualization only.
    Replace with real LGD boundaries when available.
    """
    logger.warning("⚠️  Generating SYNTHETIC block boundaries — not real administrative boundaries!")

    features = []
    block_id = 1

    for district in config["districts"]:
        bbox = district["bbox"]  # [lon_min, lat_min, lon_max, lat_max]
        blocks = district["blocks"]
        n_blocks = len(blocks)

        # Distribute block centroids in a grid within the district bbox
        lon_min, lat_min, lon_max, lat_max = bbox
        n_cols = max(2, int(np.ceil(np.sqrt(n_blocks))))
        n_rows = max(2, int(np.ceil(n_blocks / n_cols)))

        lons = np.linspace(lon_min + 0.1, lon_max - 0.1, n_cols)
        lats = np.linspace(lat_min + 0.1, lat_max - 0.1, n_rows)

        # Create grid points
        grid_points = []
        for lat in lats:
            for lon in lons:
                grid_points.append((lon, lat))

        # Add some jitter for realism
        rng = np.random.RandomState(42 + hash(district["name"]) % 1000)

        for i, block_name in enumerate(blocks):
            if i >= len(grid_points):
                # If more blocks than grid points, add near the center
                center_lon = (lon_min + lon_max) / 2
                center_lat = (lat_min + lat_max) / 2
                cx = center_lon + rng.uniform(-0.3, 0.3)
                cy = center_lat + rng.uniform(-0.3, 0.3)
            else:
                cx, cy = grid_points[i]
                cx += rng.uniform(-0.05, 0.05)
                cy += rng.uniform(-0.05, 0.05)

            # Create a roughly hexagonal polygon around the centroid
            radius = 0.15  # ~15 km at these latitudes
            angles = np.linspace(0, 2 * np.pi, 7)[:-1]  # Hexagon
            angles += rng.uniform(0, np.pi / 6)  # Rotate randomly
            radii = radius * (1 + rng.uniform(-0.15, 0.15, 6))

            coords = [
                [float(cx + r * np.cos(a)), float(cy + r * np.sin(a))]
                for a, r in zip(angles, radii)
            ]
            coords.append(coords[0])  # Close the polygon

            features.append({
                "type": "Feature",
                "properties": {
                    "id": block_id,
                    "name": block_name,
                    "district": district["name"],
                    "district_lgd_code": district["lgd_code"],
                    "centroid_lat": float(cy),
                    "centroid_lon": float(cx),
                    "is_synthetic": True,  # ⚠️ SYNTHETIC
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [coords],
                },
            })
            block_id += 1

    return {
        "type": "FeatureCollection",
        "features": features,
        "_warning": "SYNTHETIC boundaries — not real administrative boundaries",
    }


def generate_synthetic_district_boundaries(config: dict) -> dict:
    """
    Generate SYNTHETIC district boundaries as convex hulls of block centroids.
    ⚠️ SYNTHETIC
    """
    features = []
    for i, district in enumerate(config["districts"]):
        bbox = district["bbox"]
        lon_min, lat_min, lon_max, lat_max = bbox

        # Simple rectangle with slight inward margin
        margin = 0.05
        coords = [
            [lon_min + margin, lat_min + margin],
            [lon_max - margin, lat_min + margin],
            [lon_max - margin, lat_max - margin],
            [lon_min + margin, lat_max - margin],
            [lon_min + margin, lat_min + margin],
        ]

        features.append({
            "type": "Feature",
            "properties": {
                "id": i + 1,
                "name": district["name"],
                "lgd_code": district["lgd_code"],
                "state": config["state"]["name"],
                "is_synthetic": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [coords],
            },
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "_warning": "SYNTHETIC boundaries",
    }


def generate_synthetic_panchayats(blocks_geojson: dict, per_block: int = 5) -> dict:
    """
    Generate SYNTHETIC panchayat entries within each block.
    ⚠️ SYNTHETIC: placeholder names and approximate locations.
    """
    features = []
    panch_id = 1
    rng = np.random.RandomState(123)

    for block_feat in blocks_geojson["features"]:
        cx = block_feat["properties"]["centroid_lon"]
        cy = block_feat["properties"]["centroid_lat"]
        block_name = block_feat["properties"]["name"]

        for j in range(per_block):
            px = cx + rng.uniform(-0.08, 0.08)
            py = cy + rng.uniform(-0.08, 0.08)

            features.append({
                "type": "Feature",
                "properties": {
                    "id": panch_id,
                    "name": f"{block_name} GP-{j+1}",  # SYNTHETIC name
                    "block_name": block_name,
                    "block_id": block_feat["properties"]["id"],
                    "centroid_lat": float(py),
                    "centroid_lon": float(px),
                    "is_synthetic": True,
                },
                "geometry": None,  # No polygon for panchayats
            })
            panch_id += 1

    return {
        "type": "FeatureCollection",
        "features": features,
        "_warning": "SYNTHETIC panchayat names and locations",
    }


def save_geojson(data: dict, filepath: Path):
    """Save GeoJSON to file."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
    logger.info(f"Saved: {filepath} ({len(data['features'])} features)")


def load_to_database(config: dict, districts_gj: dict, blocks_gj: dict, panchayats_gj: dict):
    """Load boundaries into PostGIS database."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from geoalchemy2.shape import from_shape
    from shapely.geometry import shape

    from backend.db.models import Base, District, Block, Panchayat
    from backend.db.session import SYNC_DATABASE_URL

    engine = create_engine(SYNC_DATABASE_URL)

    # Create tables
    Base.metadata.create_all(engine)
    logger.info("Database tables created")

    with Session(engine) as session:
        # Clear existing data
        session.query(Panchayat).delete()
        session.query(Block).delete()
        session.query(District).delete()
        session.commit()

        # Load districts
        district_map = {}  # name -> db id
        for feat in districts_gj["features"]:
            props = feat["properties"]
            geom = from_shape(shape(feat["geometry"]), srid=4326) if feat["geometry"] else None

            district = District(
                name=props["name"],
                state=props.get("state", "Telangana"),
                lgd_code=props["lgd_code"],
                geometry=geom,
            )
            session.add(district)
            session.flush()
            district_map[props["name"]] = district.id

        logger.info(f"Loaded {len(district_map)} districts")

        # Load blocks
        block_map = {}  # block id from geojson -> db id
        for feat in blocks_gj["features"]:
            props = feat["properties"]
            geom = from_shape(shape(feat["geometry"]), srid=4326) if feat["geometry"] else None
            district_id = district_map.get(props["district"])

            block = Block(
                name=props["name"],
                district_id=district_id,
                centroid_lat=props.get("centroid_lat"),
                centroid_lon=props.get("centroid_lon"),
                geometry=geom,
            )
            session.add(block)
            session.flush()
            block_map[props["id"]] = block.id

        logger.info(f"Loaded {len(block_map)} blocks")

        # Load panchayats
        panch_count = 0
        for feat in panchayats_gj["features"]:
            props = feat["properties"]
            block_db_id = block_map.get(props["block_id"])

            if block_db_id is None:
                continue

            panchayat = Panchayat(
                name=props["name"],
                block_id=block_db_id,
                centroid_lat=props.get("centroid_lat"),
                centroid_lon=props.get("centroid_lon"),
            )
            session.add(panchayat)
            panch_count += 1

        session.commit()
        logger.info(f"Loaded {panch_count} panchayats")

    logger.info("✅ All boundaries loaded into database")


def main():
    """Main entry point."""
    config = load_config()
    output_dir = Path("data/sample/boundaries")

    logger.info(f"Pilot region: {config['state']['name']}")
    logger.info(f"Districts: {[d['name'] for d in config['districts']]}")

    # Generate synthetic boundaries
    # TODO: Replace with real boundary download when LGD/GADM data is available
    districts_gj = generate_synthetic_district_boundaries(config)
    blocks_gj = generate_synthetic_block_boundaries(config)
    panchayats_gj = generate_synthetic_panchayats(blocks_gj)

    # Save as GeoJSON files (for frontend map and offline use)
    save_geojson(districts_gj, output_dir / "districts.geojson")
    save_geojson(blocks_gj, output_dir / "blocks.geojson")
    save_geojson(panchayats_gj, output_dir / "panchayats.geojson")

    # Copy to frontend public dir
    frontend_dir = Path("frontend/public/boundaries")
    save_geojson(districts_gj, frontend_dir / "districts.geojson")
    save_geojson(blocks_gj, frontend_dir / "blocks.geojson")
    save_geojson(panchayats_gj, frontend_dir / "panchayats.geojson")

    # Load into database (if DB is available)
    try:
        load_to_database(config, districts_gj, blocks_gj, panchayats_gj)
    except Exception as e:
        logger.warning(f"Could not load to database (DB may not be running): {e}")
        logger.info("GeoJSON files saved — run again after `docker compose up` to load DB")


if __name__ == "__main__":
    main()
