"""
Varsha — Pipeline Router

Trigger the daily pipeline (officer only) and see recent runs.
"""

import asyncio
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import require_officer
from backend.db.models import PipelineRun
from backend.db.session import get_db

router = APIRouter()
_lock = asyncio.Lock()


@router.get("/runs")
async def runs(limit: int = Query(20, le=200), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(PipelineRun).order_by(PipelineRun.id.desc()).limit(limit))).scalars().all()
    return {"runs": [{"id": r.id, "run_date": str(r.run_date), "status": r.status, "started_at": str(r.started_at),
                      "finished_at": str(r.finished_at) if r.finished_at else None, "model_version": r.model_version,
                      "n_forecasts": r.n_forecasts, "n_advisories": r.n_advisories, "message": r.message,
                      "data_sources": r.data_sources} for r in rows]}


@router.post("/run")
async def run(run_date: date = Query(..., description="Issue date YYYY-MM-DD"), dispatch: bool = Query(False),
              force: bool = Query(False), officer: str = Depends(require_officer)):
    """Run the forecast + advisory pipeline for one date (takes a few seconds)."""
    if _lock.locked():
        raise HTTPException(status_code=409, detail="A pipeline run is already in progress")
    from backend.pipeline.daily_run import run_pipeline

    async with _lock:
        try:
            res = await asyncio.to_thread(run_pipeline, run_date, None, dispatch, False, force)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Pipeline failed: {exc}") from exc
    return {"triggered_by": officer, "run_date": str(run_date), **res}
