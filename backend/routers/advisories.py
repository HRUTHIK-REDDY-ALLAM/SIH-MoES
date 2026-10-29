"""
Varsha — Advisories Router

Serves crop-specific advisories for panchayats.
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_db
from backend.db.models import Advisory, Panchayat, Block

router = APIRouter()


@router.get("/panchayat/{panchayat_id}")
async def get_panchayat_advisories(
    panchayat_id: int,
    crop: Optional[str] = Query(None),
    language: str = Query("en", description="Language: en, te, hi"),
    db: AsyncSession = Depends(get_db),
):
    """Get latest advisories for a panchayat, optionally filtered by crop."""
    stmt = (
        select(Advisory)
        .where(Advisory.panchayat_id == panchayat_id)
        .where(Advisory.status.in_(["approved", "pending"]))
        .order_by(Advisory.issue_date.desc())
        .limit(20)
    )
    if crop:
        stmt = stmt.where(Advisory.crop == crop)

    result = await db.execute(stmt)
    rows = result.scalars().all()

    advisories = []
    for a in rows:
        message = a.message_en
        if language == "te" and a.message_te:
            message = a.message_te
        elif language == "hi" and a.message_hi:
            message = a.message_hi

        # If officer edited, use edited version
        if a.edited_message and a.status == "approved":
            message = a.edited_message

        advisories.append({
            "id": a.id,
            "issue_date": str(a.issue_date),
            "crop": a.crop,
            "action": a.action,
            "message": message,
            "seedling_survival_prob": a.seedling_survival_prob,
            "status": a.status,
            "approved_by": a.approved_by,
        })

    return {"panchayat_id": panchayat_id, "advisories": advisories}


@router.get("/block/{block_id}")
async def get_block_advisories(
    block_id: int,
    issue_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Get all advisories for panchayats in a block."""
    stmt = (
        select(Advisory, Panchayat.name.label("panchayat_name"))
        .join(Panchayat, Advisory.panchayat_id == Panchayat.id)
        .where(Panchayat.block_id == block_id)
        .order_by(Advisory.issue_date.desc(), Advisory.crop)
    )
    if issue_date:
        stmt = stmt.where(Advisory.issue_date == issue_date)

    result = await db.execute(stmt)
    rows = result.all()

    return {
        "block_id": block_id,
        "advisories": [
            {
                "id": row.Advisory.id,
                "panchayat_id": row.Advisory.panchayat_id,
                "panchayat_name": row.panchayat_name,
                "issue_date": str(row.Advisory.issue_date),
                "crop": row.Advisory.crop,
                "action": row.Advisory.action,
                "message_en": row.Advisory.message_en,
                "message_te": row.Advisory.message_te,
                "message_hi": row.Advisory.message_hi,
                "seedling_survival_prob": row.Advisory.seedling_survival_prob,
                "status": row.Advisory.status,
            }
            for row in rows
        ],
    }
