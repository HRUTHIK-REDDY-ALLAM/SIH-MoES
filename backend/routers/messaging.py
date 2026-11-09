"""
Varsha — Messaging Router (SMS / WhatsApp gateway)

  POST /subscribers              register a farmer or extension officer
  GET  /outbox                   recent messages (phone preview in the web app)
  POST /inbound                  generic SMS gateway webhook (form or JSON: from, text)
  GET  /whatsapp/webhook         WhatsApp Cloud API verification handshake
  POST /whatsapp/webhook         WhatsApp Cloud API incoming messages
"""

import os

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import MessageLog, Panchayat, Subscriber
from backend.db.session import get_db
from backend.services.messaging import handle_inbound, mode, phone_hash

router = APIRouter()


class SubscriberIn(BaseModel):
    name: str | None = None
    phone: str = Field(..., pattern=r"^\+?[0-9\- ]{10,16}$")
    panchayat_id: int
    crops: list[str] = ["cotton"]
    language: str = Field("te", pattern="^(en|te|hi)$")
    channel: str = Field("sms", pattern="^(sms|whatsapp)$")


@router.post("/subscribers")
async def register(sub: SubscriberIn, db: AsyncSession = Depends(get_db)):
    p = await db.get(Panchayat, sub.panchayat_id)
    if not p:
        raise HTTPException(status_code=404, detail="Unknown panchayat")
    h = phone_hash(sub.phone)
    existing = (await db.execute(select(Subscriber).where(Subscriber.phone_hash == h))).scalar_one_or_none()
    if existing:
        existing.panchayat_id, existing.block_id = p.id, p.block_id
        existing.crops, existing.language, existing.channel, existing.active = sub.crops, sub.language, sub.channel, True
        await db.flush()
        return {"status": "updated", "subscriber_id": existing.id}
    s = Subscriber(name=sub.name, phone=sub.phone, phone_hash=h, panchayat_id=p.id, block_id=p.block_id,
                   crops=sub.crops, language=sub.language, channel=sub.channel, role="farmer")
    db.add(s)
    await db.flush()
    return {"status": "created", "subscriber_id": s.id}


@router.get("/outbox")
async def outbox(limit: int = Query(50, le=500), phone: str | None = Query(None), db: AsyncSession = Depends(get_db)):
    stmt = select(MessageLog).order_by(MessageLog.id.desc()).limit(limit)
    if phone:
        stmt = stmt.where(MessageLog.phone == phone)
    rows = (await db.execute(stmt)).scalars().all()
    return {"mode": mode(), "messages": [{
        "id": m.id, "direction": m.direction, "phone": m.phone, "channel": m.channel, "language": m.language,
        "body": m.body, "status": m.status, "advisory_id": m.advisory_id, "created_at": str(m.created_at)}
        for m in rows]}


@router.post("/inbound")
async def inbound(request: Request, db: AsyncSession = Depends(get_db)):
    """Generic SMS gateway callback: accepts form or JSON with `from`/`sender` and `text`/`message`."""
    if request.headers.get("content-type", "").startswith("application/json"):
        data = await request.json()
    else:
        data = dict(await request.form())
    phone = data.get("from") or data.get("sender") or data.get("msisdn")
    text = data.get("text") or data.get("message") or data.get("body") or ""
    if not phone:
        raise HTTPException(status_code=422, detail="missing sender")
    return await db.run_sync(lambda s: handle_inbound(s, str(phone), str(text), "sms"))


@router.get("/whatsapp/webhook", response_class=PlainTextResponse)
async def whatsapp_verify(mode_: str = Query(None, alias="hub.mode"), token: str = Query(None, alias="hub.verify_token"),
                          challenge: str = Query(None, alias="hub.challenge")):
    if mode_ == "subscribe" and token and token == os.getenv("WHATSAPP_VERIFY_TOKEN"):
        return challenge or ""
    raise HTTPException(status_code=403, detail="verification failed")


@router.post("/whatsapp/webhook")
async def whatsapp_incoming(payload: dict, db: AsyncSession = Depends(get_db)):
    handled = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for msg in change.get("value", {}).get("messages", []):
                if msg.get("type") == "text":
                    phone = "+" + msg.get("from", "").lstrip("+")
                    text = msg.get("text", {}).get("body", "")
                    handled.append(await db.run_sync(lambda s, p=phone, t=text: handle_inbound(s, p, t, "whatsapp")))
    return {"handled": len(handled)}
