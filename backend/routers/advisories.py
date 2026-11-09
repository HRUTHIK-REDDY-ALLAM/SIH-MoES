"""
Varsha — Advisories Router

Crop-specific advisories for panchayats and blocks.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Advisory, Panchayat
from backend.db.session import get_db
from backend.services import bundles

router = APIRouter()


@router.get("/panchayat/{panchayat_id}")
async def get_panchayat_advisories(
    panchayat_id: int,
    crop: str | None = Query(None),
    language: str = Query("en", description="Language: en, te, hi"),
    limit: int = Query(20, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Latest advisories for a panchayat (approved or pending), newest first."""
    stmt = (select(Advisory).where(Advisory.panchayat_id == panchayat_id)
            .where(Advisory.status.in_(["approved", "pending"]))
            .order_by(Advisory.issue_date.desc(), Advisory.priority).limit(limit))
    if crop:
        stmt = stmt.where(Advisory.crop == crop)
    rows = (await db.execute(stmt)).scalars().all()
    return {"panchayat_id": panchayat_id, "language": language,
            "advisories": [bundles.advisory_dict(a, language) for a in rows]}


@router.get("/block/{block_id}")
async def get_block_advisories(block_id: int, issue_date: date | None = Query(None),
                               db: AsyncSession = Depends(get_db)):
    """All advisories for the panchayats of a block on one issue date (default: latest)."""
    d = issue_date or await db.run_sync(bundles.latest_issue_date)
    stmt = (select(Advisory, Panchayat.name.label("panchayat_name"))
            .join(Panchayat, Advisory.panchayat_id == Panchayat.id)
            .where(Panchayat.block_id == block_id, Advisory.issue_date == d)
            .order_by(Panchayat.name, Advisory.crop))
    rows = (await db.execute(stmt)).all()
    return {"block_id": block_id, "issue_date": str(d) if d else None,
            "advisories": [{**bundles.advisory_dict(r.Advisory), "panchayat_name": r.panchayat_name} for r in rows]}
