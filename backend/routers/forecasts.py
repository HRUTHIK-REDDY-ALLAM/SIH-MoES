"""
Varsha — Forecasts Router

Probabilistic 1-4 week outlooks for blocks and panchayats, and map-ready
GeoJSON risk layers.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Block, Forecast, Panchayat, PanchayatForecast
from backend.db.session import get_db
from backend.services import bundles

router = APIRouter()

EVENTS = {
    "onset": "prob_onset", "false_onset": "prob_false_onset", "dry_spell": "prob_dry_spell_7d",
    "dry_spell_14d": "prob_dry_spell_14d", "heavy_rain": "prob_heavy_rain",
    "very_heavy_rain": "prob_very_heavy_rain", "rainfall": "rainfall_median",
}
HORIZONS = (7, 14, 21, 30)


async def _issue_date(db: AsyncSession, issue_date: date | None) -> date | None:
    return issue_date or await db.run_sync(bundles.latest_issue_date)


def _check_horizon(h: int):
    if h not in HORIZONS:
        raise HTTPException(status_code=422, detail=f"horizon_days must be one of {HORIZONS}")


@router.get("/latest")
async def get_latest_forecasts(
    district_id: int | None = Query(None),
    horizon_days: int = Query(7, description="Forecast horizon: 7, 14, 21 or 30"),
    db: AsyncSession = Depends(get_db),
):
    """Latest forecast for every block at one horizon."""
    _check_horizon(horizon_days)
    d = await _issue_date(db, None)
    if d is None:
        return {"issue_date": None, "forecasts": []}
    stmt = (select(Forecast, Block.name.label("block_name"), Block.district_id)
            .join(Block, Forecast.block_id == Block.id)
            .where(and_(Forecast.issue_date == d, Forecast.horizon_days == horizon_days)))
    if district_id:
        stmt = stmt.where(Block.district_id == district_id)
    rows = (await db.execute(stmt)).all()
    return {"issue_date": str(d), "horizon_days": horizon_days, "forecasts": [{
        "block_id": r.Forecast.block_id, "block_name": r.block_name, "district_id": r.district_id,
        **bundles._forecast_dict(r.Forecast),
        "valid_start": str(r.Forecast.valid_start), "valid_end": str(r.Forecast.valid_end),
        "predicted_regime": r.Forecast.predicted_regime, "current_regime": r.Forecast.current_regime,
        "onset_status": r.Forecast.onset_status, "confidence_level": r.Forecast.confidence_level,
        "explanation_en": r.Forecast.explanation_en, "top_drivers": r.Forecast.top_drivers,
        "is_synthetic": r.Forecast.is_synthetic,
    } for r in rows]}


@router.get("/block/{block_id}")
async def get_block_forecast(block_id: int, issue_date: date | None = Query(None), db: AsyncSession = Depends(get_db)):
    """All horizons, explanations, recent observations and season timeseries for a block."""
    detail = await db.run_sync(lambda s: bundles.block_detail(s, block_id, issue_date))
    if not detail or not detail["horizons"]:
        raise HTTPException(status_code=404, detail="No forecasts found")
    return detail


@router.get("/panchayat/{panchayat_id}")
async def get_panchayat_forecast(panchayat_id: int, issue_date: date | None = Query(None),
                                 db: AsyncSession = Depends(get_db)):
    """Panchayat-level outlook (interpolated) with crop advisories."""
    detail = await db.run_sync(lambda s: bundles.panchayat_detail(s, panchayat_id, issue_date))
    if not detail:
        raise HTTPException(status_code=404, detail="Panchayat or forecast not found")
    return detail


@router.get("/map")
async def get_risk_map(
    event: str = Query("dry_spell", description=f"one of {list(EVENTS)}"),
    horizon_days: int = Query(7),
    level: str = Query("block", description="block or panchayat"),
    issue_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """GeoJSON risk layer: each feature carries `value` (probability 0-1, or mm for rainfall)."""
    _check_horizon(horizon_days)
    if event not in EVENTS:
        raise HTTPException(status_code=422, detail=f"event must be one of {list(EVENTS)}")
    d = await _issue_date(db, issue_date)
    if d is None:
        return {"type": "FeatureCollection", "features": [], "issue_date": None}
    col = EVENTS[event]
    if level == "panchayat":
        rows = (await db.execute(select(Panchayat, getattr(PanchayatForecast, col))
                                 .join(PanchayatForecast, PanchayatForecast.panchayat_id == Panchayat.id)
                                 .where(PanchayatForecast.issue_date == d,
                                        PanchayatForecast.horizon_days == horizon_days))).all()
        feats = [{"type": "Feature", "geometry": p.geometry,
                  "properties": {"id": p.id, "name": p.name, "block_id": p.block_id, "value": v}} for p, v in rows]
    else:
        rows = (await db.execute(select(Block, getattr(Forecast, col), Forecast.onset_status, Forecast.confidence_level)
                                 .join(Forecast, Forecast.block_id == Block.id)
                                 .where(Forecast.issue_date == d, Forecast.horizon_days == horizon_days))).all()
        feats = [{"type": "Feature", "geometry": b.geometry,
                  "properties": {"id": b.id, "name": b.name, "value": v, "onset_status": st,
                                 "confidence_level": conf}} for b, v, st, conf in rows]
    return {"type": "FeatureCollection", "issue_date": str(d), "event": event, "horizon_days": horizon_days,
            "level": level, "features": feats}


@router.get("/timeseries/{block_id}")
async def get_forecast_timeseries(
    block_id: int,
    horizon_days: int = Query(7),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Historical forecasts for a block (replay charts)."""
    _check_horizon(horizon_days)
    stmt = (select(Forecast).where(and_(Forecast.block_id == block_id, Forecast.horizon_days == horizon_days))
            .order_by(Forecast.issue_date))
    if start_date:
        stmt = stmt.where(Forecast.issue_date >= start_date)
    if end_date:
        stmt = stmt.where(Forecast.issue_date <= end_date)
    rows = (await db.execute(stmt)).scalars().all()
    return {"block_id": block_id, "horizon_days": horizon_days, "timeseries": [{
        "issue_date": str(f.issue_date), **bundles._forecast_dict(f),
        "confidence_level": f.confidence_level, "onset_status": f.onset_status,
    } for f in rows]}
