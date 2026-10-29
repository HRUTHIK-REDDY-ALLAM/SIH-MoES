"""
Varsha — Replay Mode Router

Steps through the 2023 Kharif demo season day by day,
showing what the system would have predicted and advised.
"""

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_db
from backend.db.models import Forecast, Advisory, DailyObservation, Block, Panchayat, OnsetRecord

router = APIRouter()


@router.get("/timeline")
async def get_replay_timeline(db: AsyncSession = Depends(get_db)):
    """
    Return the list of dates available for replay,
    with notable events marked.
    """
    # Get all unique issue dates
    result = await db.execute(
        select(Forecast.issue_date)
        .distinct()
        .order_by(Forecast.issue_date)
    )
    dates = [str(row[0]) for row in result.all()]

    notable_events = [
        {"date": "2023-06-09", "type": "onset_signal", "label": "First significant rain"},
        {"date": "2023-06-20", "type": "possible_false_onset", "label": "Possible false onset in western districts"},
        {"date": "2023-08-10", "type": "monsoon_break", "label": "August 2023 break begins"},
        {"date": "2023-08-25", "type": "break_end", "label": "Active monsoon resumes"},
    ]

    return {
        "season": "2023 Kharif",
        "start_date": "2023-05-15",
        "end_date": "2023-10-15",
        "available_dates": dates,
        "notable_events": notable_events,
    }


@router.get("/snapshot/{replay_date}")
async def get_replay_snapshot(
    replay_date: date,
    block_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the full state on a specific date during the replay:
    - What was the forecast issued on that date?
    - What was the actual observed rainfall?
    - What advisory would have been generated?
    """
    # Get forecasts issued on this date
    forecast_stmt = select(Forecast, Block.name.label("block_name")).join(
        Block, Forecast.block_id == Block.id
    ).where(Forecast.issue_date == replay_date)

    if block_id:
        forecast_stmt = forecast_stmt.where(Forecast.block_id == block_id)

    forecast_result = await db.execute(forecast_stmt)
    forecasts = forecast_result.all()

    # Get actual observations around this date (7-day context)
    obs_stmt = (
        select(DailyObservation, Block.name.label("block_name"))
        .join(Block, DailyObservation.block_id == Block.id)
        .where(
            and_(
                DailyObservation.obs_date >= replay_date - timedelta(days=7),
                DailyObservation.obs_date <= replay_date + timedelta(days=7),
            )
        )
        .order_by(DailyObservation.obs_date)
    )
    if block_id:
        obs_stmt = obs_stmt.where(DailyObservation.block_id == block_id)

    obs_result = await db.execute(obs_stmt)
    observations = obs_result.all()

    # Get advisories for this date
    adv_stmt = (
        select(Advisory, Panchayat.name.label("panchayat_name"))
        .join(Panchayat, Advisory.panchayat_id == Panchayat.id)
        .where(Advisory.issue_date == replay_date)
    )
    adv_result = await db.execute(adv_stmt)
    advisories = adv_result.all()

    return {
        "replay_date": str(replay_date),
        "forecasts": [
            {
                "block_id": f.Forecast.block_id,
                "block_name": f.block_name,
                "horizon_days": f.Forecast.horizon_days,
                "prob_onset": f.Forecast.prob_onset,
                "prob_false_onset": f.Forecast.prob_false_onset,
                "prob_dry_spell_7d": f.Forecast.prob_dry_spell_7d,
                "prob_heavy_rain": f.Forecast.prob_heavy_rain,
                "predicted_regime": f.Forecast.predicted_regime,
                "confidence_level": f.Forecast.confidence_level,
                "explanation_en": f.Forecast.explanation_en,
                "is_synthetic": f.Forecast.is_synthetic,
            }
            for f in forecasts
        ],
        "observations": [
            {
                "block_id": o.DailyObservation.block_id,
                "block_name": o.block_name,
                "date": str(o.DailyObservation.obs_date),
                "rainfall_mm": o.DailyObservation.rainfall_mm,
                "is_rainy_day": o.DailyObservation.is_rainy_day,
                "is_heavy_rain": o.DailyObservation.is_heavy_rain,
            }
            for o in observations
        ],
        "advisories": [
            {
                "panchayat_name": a.panchayat_name,
                "crop": a.Advisory.crop,
                "action": a.Advisory.action,
                "message_en": a.Advisory.message_en,
                "seedling_survival_prob": a.Advisory.seedling_survival_prob,
            }
            for a in advisories
        ],
    }
