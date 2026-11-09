"""
Varsha — Replay Mode Router

Step through a past season (default: 2023 Kharif) day by day and see what
the system forecast and advised, against what was then observed.
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Advisory, Block, DailyObservation, Forecast, Panchayat
from backend.db.session import get_db
from backend.services import bundles

router = APIRouter()


@router.get("/bundle")
async def get_replay_bundle(year: int = Query(2023), db: AsyncSession = Depends(get_db)):
    """Whole season in one compact payload (forecasts, observations, majority advice, drivers, events)."""
    return await db.run_sync(lambda s: bundles.replay_bundle(s, year))


@router.get("/timeline")
async def get_replay_timeline(year: int = Query(2023), db: AsyncSession = Depends(get_db)):
    """Dates available for replay, with configured and detected notable events."""
    rows = (await db.execute(select(Forecast.issue_date).distinct()
                             .where(Forecast.issue_date >= date(year, 1, 1), Forecast.issue_date <= date(year, 12, 31))
                             .order_by(Forecast.issue_date))).all()
    dates = [str(r[0]) for r in rows]
    events = await db.run_sync(lambda s: bundles.season_events(s, year))
    return {"season": f"{year} Kharif", "start_date": dates[0] if dates else None,
            "end_date": dates[-1] if dates else None, "available_dates": dates, "notable_events": events}


@router.get("/snapshot/{replay_date}")
async def get_replay_snapshot(replay_date: date, block_id: int | None = Query(None), db: AsyncSession = Depends(get_db)):
    """Forecast issued on a date, the observed rain around it, and the advisories generated."""
    fstmt = (select(Forecast, Block.name.label("block_name")).join(Block, Forecast.block_id == Block.id)
             .where(Forecast.issue_date == replay_date))
    ostmt = (select(DailyObservation, Block.name.label("block_name"))
             .join(Block, DailyObservation.block_id == Block.id)
             .where(and_(DailyObservation.obs_date >= replay_date - timedelta(days=7),
                         DailyObservation.obs_date <= replay_date + timedelta(days=30)))
             .order_by(DailyObservation.obs_date))
    astmt = (select(Advisory, Panchayat.name.label("panchayat_name"))
             .join(Panchayat, Advisory.panchayat_id == Panchayat.id)
             .where(Advisory.issue_date == replay_date))
    if block_id:
        fstmt = fstmt.where(Forecast.block_id == block_id)
        ostmt = ostmt.where(DailyObservation.block_id == block_id)
        astmt = astmt.where(Panchayat.block_id == block_id)
    forecasts = (await db.execute(fstmt)).all()
    observations = (await db.execute(ostmt)).all()
    advisories = (await db.execute(astmt)).all()
    return {
        "replay_date": str(replay_date),
        "forecasts": [{"block_id": f.Forecast.block_id, "block_name": f.block_name,
                       "horizon_days": f.Forecast.horizon_days, **bundles._forecast_dict(f.Forecast),
                       "predicted_regime": f.Forecast.predicted_regime, "onset_status": f.Forecast.onset_status,
                       "confidence_level": f.Forecast.confidence_level, "explanation_en": f.Forecast.explanation_en,
                       "is_synthetic": f.Forecast.is_synthetic} for f in forecasts],
        "observations": [{"block_id": o.DailyObservation.block_id, "block_name": o.block_name,
                          "date": str(o.DailyObservation.obs_date), "rainfall_mm": o.DailyObservation.rainfall_mm,
                          "is_rainy_day": o.DailyObservation.is_rainy_day,
                          "is_heavy_rain": o.DailyObservation.is_heavy_rain,
                          "observed_after_issue": o.DailyObservation.obs_date >= replay_date} for o in observations],
        "advisories": [{"panchayat_name": a.panchayat_name, "crop": a.Advisory.crop, "action": a.Advisory.action,
                        "message_en": a.Advisory.message_en,
                        "seedling_survival_prob": a.Advisory.seedling_survival_prob} for a in advisories],
    }
