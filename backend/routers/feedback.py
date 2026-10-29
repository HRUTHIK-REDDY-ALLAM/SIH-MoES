"""
Varsha — Farmer Feedback Router

Receives and stores ground-truth reports from farmers.
These are used for forecast verification.
"""

from datetime import date, datetime
import hashlib
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_db
from backend.db.models import FarmerFeedback

router = APIRouter()


class FeedbackReport(BaseModel):
    panchayat_id: int
    report_date: date
    rain_today: bool
    rain_intensity: Optional[str] = None  # 'light', 'moderate', 'heavy'
    crop: Optional[str] = None
    crop_condition: Optional[str] = None  # 'good', 'stressed', 'damaged', 'failed'
    farmer_phone: Optional[str] = None    # Will be hashed
    language: str = "te"


@router.post("/report")
async def submit_feedback(
    report: FeedbackReport,
    db: AsyncSession = Depends(get_db),
):
    """Submit a farmer ground-truth report."""
    phone_hash = None
    if report.farmer_phone:
        phone_hash = hashlib.sha256(report.farmer_phone.encode()).hexdigest()

    feedback = FarmerFeedback(
        panchayat_id=report.panchayat_id,
        report_date=report.report_date,
        reported_at=datetime.utcnow(),
        rain_today=report.rain_today,
        rain_intensity=report.rain_intensity,
        crop=report.crop,
        crop_condition=report.crop_condition,
        farmer_phone_hash=phone_hash,
        language=report.language,
    )
    db.add(feedback)
    await db.flush()

    return {"status": "ok", "feedback_id": feedback.id}


@router.get("/summary/{panchayat_id}")
async def get_feedback_summary(
    panchayat_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated feedback for a panchayat."""
    result = await db.execute(
        select(
            FarmerFeedback.report_date,
            func.count().label("total_reports"),
            func.sum(func.cast(FarmerFeedback.rain_today, Integer)).label("rain_yes"),
        )
        .where(FarmerFeedback.panchayat_id == panchayat_id)
        .group_by(FarmerFeedback.report_date)
        .order_by(FarmerFeedback.report_date.desc())
        .limit(30)
    )
    from sqlalchemy import Integer

    rows = result.all()
    return {
        "panchayat_id": panchayat_id,
        "daily_summary": [
            {
                "date": str(row.report_date),
                "total_reports": row.total_reports,
                "rain_yes": row.rain_yes or 0,
                "rain_fraction": (row.rain_yes or 0) / row.total_reports if row.total_reports > 0 else 0,
            }
            for row in rows
        ],
    }
