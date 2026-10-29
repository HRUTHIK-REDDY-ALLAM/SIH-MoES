"""
Varsha — Boundaries Router

Serves GeoJSON for districts, blocks, and panchayats for the map layer.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.functions import ST_AsGeoJSON, ST_Centroid

from backend.db.session import get_db
from backend.db.models import District, Block, Panchayat

router = APIRouter()


@router.get("/districts")
async def list_districts(db: AsyncSession = Depends(get_db)):
    """Return all pilot districts as GeoJSON FeatureCollection."""
    result = await db.execute(
        select(
            District.id,
            District.name,
            District.lgd_code,
            ST_AsGeoJSON(District.geometry).label("geojson"),
        )
    )
    features = []
    for row in result.all():
        features.append({
            "type": "Feature",
            "properties": {
                "id": row.id,
                "name": row.name,
                "lgd_code": row.lgd_code,
            },
            "geometry": __import__("json").loads(row.geojson) if row.geojson else None,
        })
    return {"type": "FeatureCollection", "features": features}


@router.get("/blocks")
async def list_blocks(
    district_id: int = Query(None, description="Filter by district ID"),
    db: AsyncSession = Depends(get_db),
):
    """Return blocks as GeoJSON, optionally filtered by district."""
    stmt = select(
        Block.id,
        Block.name,
        Block.district_id,
        Block.lgd_code,
        Block.centroid_lat,
        Block.centroid_lon,
        Block.trust_score,
        ST_AsGeoJSON(Block.geometry).label("geojson"),
    )
    if district_id:
        stmt = stmt.where(Block.district_id == district_id)

    result = await db.execute(stmt)
    features = []
    for row in result.all():
        features.append({
            "type": "Feature",
            "properties": {
                "id": row.id,
                "name": row.name,
                "district_id": row.district_id,
                "lgd_code": row.lgd_code,
                "centroid_lat": row.centroid_lat,
                "centroid_lon": row.centroid_lon,
                "trust_score": row.trust_score,
            },
            "geometry": __import__("json").loads(row.geojson) if row.geojson else None,
        })
    return {"type": "FeatureCollection", "features": features}


@router.get("/blocks/{block_id}")
async def get_block(block_id: int, db: AsyncSession = Depends(get_db)):
    """Return a single block with its panchayats."""
    result = await db.execute(
        select(Block).where(Block.id == block_id)
    )
    block = result.scalar_one_or_none()
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")

    # Get panchayats for this block
    panch_result = await db.execute(
        select(
            Panchayat.id,
            Panchayat.name,
            Panchayat.lgd_code,
            Panchayat.centroid_lat,
            Panchayat.centroid_lon,
        ).where(Panchayat.block_id == block_id)
    )

    return {
        "id": block.id,
        "name": block.name,
        "lgd_code": block.lgd_code,
        "centroid_lat": block.centroid_lat,
        "centroid_lon": block.centroid_lon,
        "trust_score": block.trust_score,
        "panchayats": [
            {
                "id": p.id,
                "name": p.name,
                "lgd_code": p.lgd_code,
                "centroid_lat": p.centroid_lat,
                "centroid_lon": p.centroid_lon,
            }
            for p in panch_result.all()
        ],
    }


@router.get("/panchayats")
async def list_panchayats(
    block_id: int = Query(None, description="Filter by block ID"),
    db: AsyncSession = Depends(get_db),
):
    """Return panchayats, optionally filtered by block."""
    stmt = select(
        Panchayat.id,
        Panchayat.name,
        Panchayat.block_id,
        Panchayat.lgd_code,
        Panchayat.centroid_lat,
        Panchayat.centroid_lon,
        ST_AsGeoJSON(Panchayat.geometry).label("geojson"),
    )
    if block_id:
        stmt = stmt.where(Panchayat.block_id == block_id)

    result = await db.execute(stmt)
    features = []
    for row in result.all():
        features.append({
            "type": "Feature",
            "properties": {
                "id": row.id,
                "name": row.name,
                "block_id": row.block_id,
                "lgd_code": row.lgd_code,
            },
            "geometry": __import__("json").loads(row.geojson) if row.geojson else None,
        })
    return {"type": "FeatureCollection", "features": features}
