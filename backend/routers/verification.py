"""
Varsha — Verification Router

Hindcast skill of the forecast system: Brier Skill Score against block
climatology, ROC AUC and reliability diagrams per event and lead time, per
block trust scores, and the held-out demo season.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Block
from backend.db.session import get_db
from backend.services import bundles

router = APIRouter()


@router.get("/skill")
async def skill():
    """Full skill report (includes reliability tables)."""
    rep = bundles.skill_report()
    return rep or {"detail": "No trained model yet. Run: python -m models.train"}


@router.get("/summary")
async def summary():
    """Compact BSS / AUC table per event and horizon."""
    return bundles.compact_skill()


@router.get("/blocks")
async def block_skill(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Block).order_by(Block.id))).scalars().all()
    return {"blocks": [{"id": b.id, "name": b.name, "bss_onset": b.bss_onset, "bss_dry_spell": b.bss_dry_spell,
                        "bss_heavy_rain": b.bss_heavy_rain, "trust_score": b.trust_score} for b in rows]}
