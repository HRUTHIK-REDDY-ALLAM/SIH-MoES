"""
Varsha — Boundaries Router

GeoJSON for districts, blocks and panchayats (map layers).
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Block, District, Panchayat
from backend.db.session import get_db

router = APIRouter()


def _fc(features):
    return {"type": "FeatureCollection", "features": features}


@router.get("/districts")
async def list_districts(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(District))).scalars().all()
    return _fc([{"type": "Feature", "geometry": d.geometry,
                 "properties": {"id": d.id, "name": d.name, "lgd_code": d.lgd_code, "is_synthetic": d.is_synthetic}}
                for d in rows])


@router.get("/blocks")
async def list_blocks(district_id: int | None = Query(None), db: AsyncSession = Depends(get_db)):
    stmt = select(Block)
    if district_id:
        stmt = stmt.where(Block.district_id == district_id)
    rows = (await db.execute(stmt)).scalars().all()
    return _fc([{"type": "Feature", "geometry": b.geometry, "properties": {
        "id": b.id, "name": b.name, "district_id": b.district_id, "lgd_code": b.lgd_code,
        "centroid_lat": b.centroid_lat, "centroid_lon": b.centroid_lon, "elevation_m": b.elevation_m,
        "trust_score": b.trust_score, "is_synthetic": b.is_synthetic}} for b in rows])


@router.get("/blocks/{block_id}")
async def get_block(block_id: int, db: AsyncSession = Depends(get_db)):
    block = await db.get(Block, block_id)
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")
    panchs = (await db.execute(select(Panchayat).where(Panchayat.block_id == block_id))).scalars().all()
    return {
        "id": block.id, "name": block.name, "district_id": block.district_id, "lgd_code": block.lgd_code,
        "centroid_lat": block.centroid_lat, "centroid_lon": block.centroid_lon, "elevation_m": block.elevation_m,
        "trust_score": block.trust_score, "is_synthetic": block.is_synthetic,
        "panchayats": [{"id": p.id, "name": p.name, "lgd_code": p.lgd_code, "centroid_lat": p.centroid_lat,
                        "centroid_lon": p.centroid_lon, "soil_type": p.soil_type} for p in panchs],
    }


@router.get("/panchayats")
async def list_panchayats(block_id: int | None = Query(None), db: AsyncSession = Depends(get_db)):
    stmt = select(Panchayat)
    if block_id:
        stmt = stmt.where(Panchayat.block_id == block_id)
    rows = (await db.execute(stmt)).scalars().all()
    return _fc([{"type": "Feature", "geometry": p.geometry, "properties": {
        "id": p.id, "name": p.name, "block_id": p.block_id, "lgd_code": p.lgd_code,
        "centroid_lat": p.centroid_lat, "centroid_lon": p.centroid_lon, "soil_type": p.soil_type,
        "irrigated_fraction": p.irrigated_fraction, "is_synthetic": p.is_synthetic}} for p in rows])
