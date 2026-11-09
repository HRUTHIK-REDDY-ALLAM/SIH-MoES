"""
Varsha — Officer Console Router

Agricultural extension officers review, edit and approve advisories before
they are sent, then dispatch them. Write endpoints require officer login.
"""

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import require_officer
from backend.db.models import Advisory, Block, Panchayat
from backend.db.session import get_db
from backend.services import bundles

router = APIRouter()


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ApprovalRequest(BaseModel):
    action: str                      # 'approve', 'reject', 'edit'
    notes: str | None = None
    edited_message: str | None = None


@router.get("/whoami")
async def whoami(officer: str = Depends(require_officer)):
    return {"officer": officer}


@router.get("/pending")
async def get_pending_advisories(
    district_id: int | None = Query(None),
    block_id: int | None = Query(None),
    action: str | None = Query(None),
    issue_date: date | None = Query(None),
    limit: int = Query(200, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """Pending advisories for review, most urgent first."""
    stmt = (select(Advisory, Panchayat.name.label("panchayat_name"), Block.name.label("block_name"),
                   Block.district_id, Block.id.label("block_id"))
            .join(Panchayat, Advisory.panchayat_id == Panchayat.id)
            .join(Block, Panchayat.block_id == Block.id)
            .where(Advisory.status == "pending")
            .order_by(Advisory.issue_date.desc(), Advisory.priority, Block.name, Advisory.crop))
    if district_id:
        stmt = stmt.where(Block.district_id == district_id)
    if block_id:
        stmt = stmt.where(Block.id == block_id)
    if action:
        stmt = stmt.where(Advisory.action == action)
    if issue_date:
        stmt = stmt.where(Advisory.issue_date == issue_date)
    rows = (await db.execute(stmt.limit(limit))).all()
    total = (await db.execute(select(func.count()).select_from(Advisory).where(Advisory.status == "pending"))).scalar()
    return {"count": total, "returned": len(rows), "advisories": [{
        **bundles.advisory_dict(r.Advisory), "panchayat_name": r.panchayat_name, "block_name": r.block_name,
        "block_id": r.block_id, "district_id": r.district_id} for r in rows]}


@router.post("/review/{advisory_id}")
async def review_advisory(advisory_id: int, request: ApprovalRequest, db: AsyncSession = Depends(get_db),
                          officer: str = Depends(require_officer)):
    """Approve, reject, or edit-and-approve an advisory."""
    advisory = await db.get(Advisory, advisory_id)
    if not advisory:
        raise HTTPException(status_code=404, detail="Advisory not found")
    if request.action == "approve":
        advisory.status = "approved"
    elif request.action == "reject":
        advisory.status = "rejected"
    elif request.action == "edit":
        if not request.edited_message:
            raise HTTPException(status_code=422, detail="edited_message is required for edit")
        advisory.status = "approved"
        advisory.edited_message = request.edited_message
    else:
        raise HTTPException(status_code=400, detail="Invalid action")
    advisory.approved_by = officer
    advisory.approved_at = utcnow()
    advisory.officer_notes = request.notes
    await db.flush()
    return {"status": "ok", "advisory_id": advisory_id, "new_status": advisory.status}


@router.post("/approve-all")
async def approve_all_pending(
    district_id: int | None = Query(None),
    issue_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    officer: str = Depends(require_officer),
):
    """Bulk-approve pending advisories (optionally for one district / date)."""
    stmt = update(Advisory).where(Advisory.status == "pending")
    if district_id:
        panch_ids = select(Panchayat.id).join(Block, Panchayat.block_id == Block.id).where(Block.district_id == district_id)
        stmt = stmt.where(Advisory.panchayat_id.in_(panch_ids))
    if issue_date:
        stmt = stmt.where(Advisory.issue_date == issue_date)
    result = await db.execute(stmt.values(status="approved", approved_by=officer, approved_at=utcnow())
                              .execution_options(synchronize_session=False))
    return {"status": "ok", "approved_count": result.rowcount}


@router.post("/dispatch")
async def dispatch(issue_date: date | None = Query(None), db: AsyncSession = Depends(get_db),
                   officer: str = Depends(require_officer)):
    """Send approved advisories for a date to subscribed farmers and officers."""
    from backend.services.messaging import dispatch_approved

    d = issue_date or await db.run_sync(bundles.latest_issue_date)
    if d is None:
        raise HTTPException(status_code=404, detail="No advisories to dispatch")
    res = await db.run_sync(lambda s: dispatch_approved(s, d))
    return {"status": "ok", "issue_date": str(d), **res}


@router.get("/stats")
async def get_officer_stats(db: AsyncSession = Depends(get_db)):
    """Counts by status, plus today's actions."""
    rows = (await db.execute(select(Advisory.status, func.count()).group_by(Advisory.status))).all()
    counts = {k: v for k, v in rows}
    d = await db.run_sync(bundles.latest_issue_date)
    actions = {}
    if d:
        actions = {k: v for k, v in (await db.execute(
            select(Advisory.action, func.count()).where(Advisory.issue_date == d).group_by(Advisory.action))).all()}
    return {"pending": counts.get("pending", 0), "approved": counts.get("approved", 0),
            "rejected": counts.get("rejected", 0), "latest_issue_date": str(d) if d else None,
            "latest_actions": actions}
