"""
Varsha — Dashboard Router

One-call payloads for the web app (identical in shape to the static files in
frontend/public/data/, so the app can fall back to them offline).
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_db
from backend.services import bundles

router = APIRouter()


@router.get("/latest")
async def latest(issue_date: date | None = Query(None), db: AsyncSession = Depends(get_db)):
    """Every block and panchayat outlook (all horizons), advisory actions, drivers and skill."""
    data = await db.run_sync(lambda s: bundles.dashboard_bundle(s, issue_date))
    if not data.get("issue_date"):
        raise HTTPException(status_code=404, detail="No forecasts yet. Run scripts/bootstrap_demo.py")
    return data


@router.get("/drivers")
async def drivers(issue_date: date | None = Query(None), db: AsyncSession = Depends(get_db)):
    """Current ENSO / IOD / MJO state and regional atmosphere."""
    d = issue_date or await db.run_sync(bundles.latest_issue_date)
    if d is None:
        raise HTTPException(status_code=404, detail="No data")
    return await db.run_sync(lambda s: bundles.driver_state(s, d))
