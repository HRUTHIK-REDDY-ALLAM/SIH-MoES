"""
Varsha — Farmer Feedback Router

Ground-truth reports from farmers (web app or SMS/WhatsApp replies), used to
verify forecasts at village level.
"""

import hashlib
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Integer, and_, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import DailyObservation, FarmerFeedback, Panchayat
from backend.db.session import get_db

router = APIRouter()


class FeedbackReport(BaseModel):
    panchayat_id: int
    report_date: date
    rain_today: bool
    rain_intensity: str | None = Field(None, description="none, light, moderate, heavy")
    crop: str | None = None
    crop_condition: str | None = Field(None, description="good, stressed, damaged, failed")
    farmer_phone: str | None = None    # hashed before storage, never stored raw
    language: str = "te"


@router.post("/report")
async def submit_feedback(report: FeedbackReport, db: AsyncSession = Depends(get_db)):
    """Submit a farmer ground-truth report."""
    if not await db.get(Panchayat, report.panchayat_id):
        raise HTTPException(status_code=404, detail="Unknown panchayat")
    phone_hash = hashlib.sha256(report.farmer_phone.encode()).hexdigest() if report.farmer_phone else None
    fb = FarmerFeedback(
        panchayat_id=report.panchayat_id, report_date=report.report_date,
        reported_at=datetime.now(timezone.utc).replace(tzinfo=None), rain_today=report.rain_today,
        rain_intensity=report.rain_intensity, crop=report.crop, crop_condition=report.crop_condition,
        farmer_phone_hash=phone_hash, language=report.language, source="web",
    )
    db.add(fb)
    await db.flush()
    return {"status": "ok", "feedback_id": fb.id}


@router.get("/summary/{panchayat_id}")
async def get_feedback_summary(panchayat_id: int, db: AsyncSession = Depends(get_db)):
    """Daily aggregated reports for a panchayat, alongside the block's gridded rainfall."""
    p = await db.get(Panchayat, panchayat_id)
    if not p:
        raise HTTPException(status_code=404, detail="Unknown panchayat")
    rows = (await db.execute(
        select(FarmerFeedback.report_date, func.count().label("total_reports"),
               func.sum(cast(FarmerFeedback.rain_today, Integer)).label("rain_yes"))
        .where(FarmerFeedback.panchayat_id == panchayat_id)
        .group_by(FarmerFeedback.report_date)
        .order_by(FarmerFeedback.report_date.desc()).limit(30))).all()
    dates = [r.report_date for r in rows]
    obs = {}
    if dates:
        obs = {o.obs_date: o.rainfall_mm for o in (await db.execute(
            select(DailyObservation).where(and_(DailyObservation.block_id == p.block_id,
                                                DailyObservation.obs_date >= min(dates) - timedelta(days=1),
                                                DailyObservation.obs_date <= max(dates))))).scalars()}
    return {"panchayat_id": panchayat_id, "daily_summary": [{
        "date": str(r.report_date), "total_reports": r.total_reports, "rain_yes": r.rain_yes or 0,
        "rain_fraction": (r.rain_yes or 0) / r.total_reports if r.total_reports else 0,
        "gridded_rain_mm": obs.get(r.report_date),
    } for r in rows]}
