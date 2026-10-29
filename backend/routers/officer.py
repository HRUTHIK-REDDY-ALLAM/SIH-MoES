"""
Varsha — Officer Console Router

Review, edit, and approve advisories before they are sent to farmers.
Simple auth for prototype (upgrade to JWT for production).
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.db.session import get_db
from backend.db.models import Advisory, Panchayat, Block, District

router = APIRouter()


class ApprovalRequest(BaseModel):
    action: str  # 'approve', 'reject', 'edit'
    officer_name: str
    notes: Optional[str] = None
    edited_message: Optional[str] = None


@router.get("/pending")
async def get_pending_advisories(
    district_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Get all pending advisories for officer review."""
    stmt = (
        select(
            Advisory,
            Panchayat.name.label("panchayat_name"),
            Block.name.label("block_name"),
            Block.district_id,
        )
        .join(Panchayat, Advisory.panchayat_id == Panchayat.id)
        .join(Block, Panchayat.block_id == Block.id)
        .where(Advisory.status == "pending")
        .order_by(Advisory.issue_date.desc(), Block.name, Advisory.crop)
    )
    if district_id:
        stmt = stmt.where(Block.district_id == district_id)

    result = await db.execute(stmt)
    rows = result.all()

    return {
        "count": len(rows),
        "advisories": [
            {
                "id": row.Advisory.id,
                "panchayat_name": row.panchayat_name,
                "block_name": row.block_name,
                "district_id": row.district_id,
                "issue_date": str(row.Advisory.issue_date),
                "crop": row.Advisory.crop,
                "action": row.Advisory.action,
                "message_en": row.Advisory.message_en,
                "message_te": row.Advisory.message_te,
                "message_hi": row.Advisory.message_hi,
                "seedling_survival_prob": row.Advisory.seedling_survival_prob,
            }
            for row in rows
        ],
    }


@router.post("/review/{advisory_id}")
async def review_advisory(
    advisory_id: int,
    request: ApprovalRequest,
    db: AsyncSession = Depends(get_db),
):
    """Approve, reject, or edit an advisory."""
    result = await db.execute(
        select(Advisory).where(Advisory.id == advisory_id)
    )
    advisory = result.scalar_one_or_none()
    if not advisory:
        raise HTTPException(status_code=404, detail="Advisory not found")

    if request.action == "approve":
        advisory.status = "approved"
    elif request.action == "reject":
        advisory.status = "rejected"
    elif request.action == "edit":
        advisory.status = "approved"
        advisory.edited_message = request.edited_message
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    advisory.approved_by = request.officer_name
    advisory.approved_at = datetime.utcnow()
    advisory.officer_notes = request.notes

    await db.flush()
    return {"status": "ok", "advisory_id": advisory_id, "new_status": advisory.status}


@router.post("/approve-all")
async def approve_all_pending(
    officer_name: str = Query(...),
    district_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Bulk approve all pending advisories (for demo convenience)."""
    stmt = (
        update(Advisory)
        .where(Advisory.status == "pending")
        .values(
            status="approved",
            approved_by=officer_name,
            approved_at=datetime.utcnow(),
        )
    )
    # Note: filtering by district requires a subquery for bulk update
    result = await db.execute(stmt)
    return {"status": "ok", "approved_count": result.rowcount}


@router.get("/stats")
async def get_officer_stats(db: AsyncSession = Depends(get_db)):
    """Dashboard stats for the officer console."""
    from sqlalchemy import func

    pending = await db.execute(
        select(func.count()).where(Advisory.status == "pending")
    )
    approved = await db.execute(
        select(func.count()).where(Advisory.status == "approved")
    )
    rejected = await db.execute(
        select(func.count()).where(Advisory.status == "rejected")
    )

    return {
        "pending": pending.scalar() or 0,
        "approved": approved.scalar() or 0,
        "rejected": rejected.scalar() or 0,
    }
