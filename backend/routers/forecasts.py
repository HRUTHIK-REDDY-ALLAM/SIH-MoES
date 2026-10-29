"""
Varsha — Forecasts Router

Serves probabilistic forecasts for blocks.
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_db
from backend.db.models import Forecast, Block

router = APIRouter()


@router.get("/latest")
async def get_latest_forecasts(
    district_id: int = Query(None),
    horizon_days: int = Query(7, description="Forecast horizon: 7, 14, 21, or 30"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the latest forecast for all blocks, optionally filtered by district.
    Returns data suitable for the risk map layer.
    """
    # Find the latest issue date
    latest_stmt = select(Forecast.issue_date).order_by(Forecast.issue_date.desc()).limit(1)
    latest_result = await db.execute(latest_stmt)
    latest_date = latest_result.scalar_one_or_none()

    if not latest_date:
        return {"issue_date": None, "forecasts": []}

    # Get all forecasts for that date
    stmt = (
        select(Forecast, Block.name.label("block_name"), Block.district_id)
        .join(Block, Forecast.block_id == Block.id)
        .where(
            and_(
                Forecast.issue_date == latest_date,
                Forecast.horizon_days == horizon_days,
            )
        )
    )
    if district_id:
        stmt = stmt.where(Block.district_id == district_id)

    result = await db.execute(stmt)
    forecasts = []
    for row in result.all():
        f = row.Forecast
        forecasts.append({
            "block_id": f.block_id,
            "block_name": row.block_name,
            "district_id": row.district_id,
            "issue_date": str(f.issue_date),
            "horizon_days": f.horizon_days,
            "valid_start": str(f.valid_start),
            "valid_end": str(f.valid_end),
            "prob_onset": f.prob_onset,
            "prob_false_onset": f.prob_false_onset,
            "prob_dry_spell_7d": f.prob_dry_spell_7d,
            "prob_dry_spell_14d": f.prob_dry_spell_14d,
            "prob_heavy_rain": f.prob_heavy_rain,
            "prob_very_heavy_rain": f.prob_very_heavy_rain,
            "rainfall_median": f.rainfall_median,
            "rainfall_q10": f.rainfall_q10,
            "rainfall_q90": f.rainfall_q90,
            "predicted_regime": f.predicted_regime,
            "confidence_level": f.confidence_level,
            "explanation_en": f.explanation_en,
            "top_drivers": f.top_drivers,
            "is_synthetic": f.is_synthetic,
        })

    return {"issue_date": str(latest_date), "horizon_days": horizon_days, "forecasts": forecasts}


@router.get("/block/{block_id}")
async def get_block_forecast(
    block_id: int,
    issue_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Get all horizon forecasts for a specific block on a given date."""
    stmt = select(Forecast).where(Forecast.block_id == block_id)

    if issue_date:
        stmt = stmt.where(Forecast.issue_date == issue_date)
    else:
        # Latest available
        sub = select(Forecast.issue_date).order_by(Forecast.issue_date.desc()).limit(1)
        sub_result = await db.execute(sub)
        latest = sub_result.scalar_one_or_none()
        if latest:
            stmt = stmt.where(Forecast.issue_date == latest)

    stmt = stmt.order_by(Forecast.horizon_days)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    if not rows:
        raise HTTPException(status_code=404, detail="No forecasts found")

    return {
        "block_id": block_id,
        "issue_date": str(rows[0].issue_date),
        "horizons": [
            {
                "horizon_days": f.horizon_days,
                "valid_start": str(f.valid_start),
                "valid_end": str(f.valid_end),
                "prob_onset": f.prob_onset,
                "prob_false_onset": f.prob_false_onset,
                "prob_dry_spell_7d": f.prob_dry_spell_7d,
                "prob_dry_spell_14d": f.prob_dry_spell_14d,
                "prob_heavy_rain": f.prob_heavy_rain,
                "prob_very_heavy_rain": f.prob_very_heavy_rain,
                "rainfall_median": f.rainfall_median,
                "rainfall_q10": f.rainfall_q10,
                "rainfall_q90": f.rainfall_q90,
                "predicted_regime": f.predicted_regime,
                "confidence_level": f.confidence_level,
                "explanation_en": f.explanation_en,
                "top_drivers": f.top_drivers,
                "is_synthetic": f.is_synthetic,
            }
            for f in rows
        ],
    }


@router.get("/timeseries/{block_id}")
async def get_forecast_timeseries(
    block_id: int,
    horizon_days: int = Query(7),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Get historical forecasts for a block (for replay mode charts)."""
    stmt = (
        select(Forecast)
        .where(
            and_(
                Forecast.block_id == block_id,
                Forecast.horizon_days == horizon_days,
            )
        )
        .order_by(Forecast.issue_date)
    )
    if start_date:
        stmt = stmt.where(Forecast.issue_date >= start_date)
    if end_date:
        stmt = stmt.where(Forecast.issue_date <= end_date)

    result = await db.execute(stmt)
    rows = result.scalars().all()

    return {
        "block_id": block_id,
        "horizon_days": horizon_days,
        "timeseries": [
            {
                "issue_date": str(f.issue_date),
                "prob_onset": f.prob_onset,
                "prob_false_onset": f.prob_false_onset,
                "prob_dry_spell_7d": f.prob_dry_spell_7d,
                "prob_heavy_rain": f.prob_heavy_rain,
                "rainfall_median": f.rainfall_median,
                "confidence_level": f.confidence_level,
            }
            for f in rows
        ],
    }
