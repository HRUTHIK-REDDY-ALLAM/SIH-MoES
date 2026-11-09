"""
Varsha — Messaging gateway (SMS / WhatsApp).

MESSAGING_MODE
  mock      (default) messages are logged in the message_log table and shown
            in the web app's phone preview; nothing leaves the server
  whatsapp  WhatsApp Cloud API (WHATSAPP_TOKEN, WHATSAPP_PHONE_ID)
  sms       generic HTTP SMS gateway (SMS_API_URL, SMS_API_KEY, SMS_SENDER_ID),
            e.g. a DLT-registered Indian bulk-SMS provider

Outbound: approved advisories -> every active subscriber of that panchayat who
grows the crop, in the subscriber's language (short SMS text or full WhatsApp
text). Extension officers get one block digest per day.

Inbound: farmer replies ("1" = it rained today, "2" = no rain, "STOP", "HELP")
arrive on /api/v1/messaging/inbound or the WhatsApp webhook and are stored as
FarmerFeedback ground truth for verification.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from collections import Counter
from datetime import date, datetime, timezone

import httpx
from sqlalchemy import select

from backend.db.models import Advisory, Block, FarmerFeedback, MessageLog, Panchayat, Subscriber

logger = logging.getLogger(__name__)


def mode() -> str:
    return os.getenv("MESSAGING_MODE", "mock")


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def phone_hash(phone: str) -> str:
    return hashlib.sha256(re.sub(r"\D", "", phone).encode()).hexdigest()


# ─── Provider adapters ───────────────────────────────────────────────────────

def send(channel: str, phone: str, body: str) -> dict:
    m = mode()
    if m == "whatsapp" and channel == "whatsapp":
        return _send_whatsapp(phone, body)
    if m in ("sms", "whatsapp") and channel == "sms":
        return _send_sms(phone, body)
    return {"status": "delivered_mock"}


def _send_whatsapp(phone: str, body: str) -> dict:
    token, phone_id = os.getenv("WHATSAPP_TOKEN"), os.getenv("WHATSAPP_PHONE_ID")
    if not token or not phone_id:
        logger.warning("WhatsApp credentials not set; message kept in mock outbox")
        return {"status": "delivered_mock", "note": "whatsapp credentials missing"}
    try:
        resp = httpx.post(
            f"https://graph.facebook.com/v20.0/{phone_id}/messages",
            headers={"Authorization": f"Bearer {token}"},
            json={"messaging_product": "whatsapp", "to": re.sub(r"\D", "", phone), "type": "text",
                  "text": {"body": body}},
            timeout=15,
        )
        resp.raise_for_status()
        return {"status": "sent", "response": resp.json()}
    except Exception as exc:  # provider failure is recorded, not raised
        logger.error("WhatsApp send failed: %s", exc)
        return {"status": "failed", "error": str(exc)[:300]}


def _send_sms(phone: str, body: str) -> dict:
    url, key = os.getenv("SMS_API_URL"), os.getenv("SMS_API_KEY")
    if not url or not key:
        return {"status": "delivered_mock", "note": "SMS gateway not configured"}
    try:
        resp = httpx.post(url, timeout=15, data={
            "apikey": key, "sender": os.getenv("SMS_SENDER_ID", "VARSHA"), "numbers": phone,
            "message": body, "unicode": "1"})
        resp.raise_for_status()
        return {"status": "sent", "response": resp.text[:300]}
    except Exception as exc:
        logger.error("SMS send failed: %s", exc)
        return {"status": "failed", "error": str(exc)[:300]}


# ─── Outbound dispatch ───────────────────────────────────────────────────────

def advisory_text(adv: Advisory, language: str, channel: str) -> str:
    if adv.edited_message:
        if language == "en":
            return adv.edited_message
        from translation.adapter import translate
        return translate(adv.edited_message, language)
    if channel == "sms":
        return getattr(adv, f"sms_{language}", None) or adv.sms_en or adv.message_en
    return getattr(adv, f"message_{language}", None) or adv.message_en


def dispatch_approved(s, issue_date: date, advisory_ids: list[int] | None = None) -> dict:
    """Send approved, undelivered advisories for a date to matching subscribers (sync session)."""
    q = select(Advisory).where(Advisory.issue_date == issue_date, Advisory.status == "approved")
    if advisory_ids:
        q = q.where(Advisory.id.in_(advisory_ids))
    advisories = s.execute(q).scalars().all()
    if not advisories:
        return {"advisories": 0, "messages": 0}
    subs = s.execute(select(Subscriber).where(Subscriber.active.is_(True), Subscriber.role == "farmer")).scalars().all()
    by_panch: dict[int, list[Subscriber]] = {}
    for sub in subs:
        by_panch.setdefault(sub.panchayat_id, []).append(sub)

    sent, failed = 0, 0
    for adv in advisories:
        for sub in by_panch.get(adv.panchayat_id, []):
            if sub.crops and adv.crop not in sub.crops:
                continue
            if sub.is_synthetic and mode() != "mock":
                continue  # never send real messages to demo (fake) numbers
            body = advisory_text(adv, sub.language or "te", sub.channel or "sms")
            res = send(sub.channel or "sms", sub.phone, body)
            s.add(MessageLog(direction="out", subscriber_id=sub.id, advisory_id=adv.id, phone=sub.phone,
                             channel=sub.channel, language=sub.language, body=body, status=res["status"],
                             provider_response=res))
            sent += res["status"] != "failed"
            failed += res["status"] == "failed"
        adv.delivered_sms = True
        adv.delivered_whatsapp = True
        adv.delivered_at = utcnow()

    sent += _officer_digests(s, issue_date, advisories)
    s.flush()
    return {"advisories": len(advisories), "messages": sent, "failed": failed}


def _officer_digests(s, issue_date: date, advisories: list[Advisory]) -> int:
    officers = s.execute(select(Subscriber).where(Subscriber.active.is_(True),
                                                  Subscriber.role == "extension_officer")).scalars().all()
    if not officers:
        return 0
    panch_block = dict(s.execute(select(Panchayat.id, Panchayat.block_id)).all())
    block_name = dict(s.execute(select(Block.id, Block.name)).all())
    per_block: dict[int, Counter] = {}
    for a in advisories:
        per_block.setdefault(panch_block.get(a.panchayat_id), Counter())[a.action] += 1
    n = 0
    for off in officers:
        counts = per_block.get(off.block_id)
        if not counts or (off.is_synthetic and mode() != "mock"):
            continue
        summary = ", ".join(f"{k} {v}" for k, v in counts.most_common())
        body = (f"Varsha {block_name.get(off.block_id, '')} block, {issue_date:%d %b}: "
                f"{sum(counts.values())} advisories sent ({summary}). Review: /officer")
        res = send(off.channel or "sms", off.phone, body)
        s.add(MessageLog(direction="out", subscriber_id=off.id, phone=off.phone, channel=off.channel,
                         language="en", body=body, status=res["status"], provider_response=res))
        n += 1
    return n


# ─── Inbound replies ─────────────────────────────────────────────────────────

YES = {"1", "yes", "y", "rain", "haan", "ha", "avunu", "అవును", "हाँ", "हां", "वर्षा"}
NO = {"2", "no", "n", "ledu", "లేదు", "नहीं", "nahi"}

REPLIES = {
    "thanks": {"en": "Thank you! Your rain report helps improve forecasts for your village.",
               "te": "ధన్యవాదాలు! మీ వర్ష సమాచారం మీ గ్రామానికి సూచనలను మెరుగుపరుస్తుంది.",
               "hi": "धन्यवाद! आपकी बारिश की जानकारी आपके गांव के पूर्वानुमान को बेहतर बनाती है।"},
    "stop": {"en": "You will no longer receive Varsha advisories. Send START to subscribe again.",
             "te": "మీకు ఇకపై వర్ష సలహాలు రావు. మళ్ళీ పొందడానికి START పంపండి.",
             "hi": "अब आपको वर्षा सलाह नहीं मिलेगी। फिर से पाने के लिए START भेजें।"},
    "start": {"en": "Welcome back to Varsha advisories.", "te": "వర్ష సలహాలకు మళ్ళీ స్వాగతం.",
              "hi": "वर्षा सलाह में आपका फिर से स्वागत है।"},
    "help": {"en": "Varsha: reply 1 if it rained today, 2 if not. STOP to unsubscribe.",
             "te": "వర్ష: ఈరోజు వర్షం పడితే 1, లేకపోతే 2 పంపండి. ఆపడానికి STOP.",
             "hi": "वर्षा: आज बारिश हुई तो 1, नहीं तो 2 भेजें। बंद करने के लिए STOP।"},
}


def handle_inbound(s, phone: str, text: str, channel: str = "sms", today: date | None = None) -> dict:
    """Parse a farmer reply, store feedback, log both directions, return the reply text."""
    today = today or date.today()
    word = (text or "").strip().lower().split()[0] if (text or "").strip() else ""
    sub = s.execute(select(Subscriber).where(Subscriber.phone_hash == phone_hash(phone))).scalar_one_or_none()
    lang = sub.language if sub else "en"
    s.add(MessageLog(direction="in", subscriber_id=sub.id if sub else None, phone=phone, channel=channel,
                     language=lang, body=text, status="received"))
    kind = "help"
    if word in ("stop", "unsubscribe"):
        kind = "stop"
        if sub:
            sub.active = False
    elif word == "start":
        kind = "start"
        if sub:
            sub.active = True
    elif sub and sub.panchayat_id and (word in YES or word in NO):
        kind = "thanks"
        s.add(FarmerFeedback(panchayat_id=sub.panchayat_id, report_date=today, rain_today=word in YES,
                             rain_intensity="unknown" if word in YES else "none",
                             farmer_phone_hash=sub.phone_hash, language=lang, source=channel))
    reply = REPLIES[kind][lang if lang in REPLIES[kind] else "en"]
    res = send(channel, phone, reply)
    s.add(MessageLog(direction="out", subscriber_id=sub.id if sub else None, phone=phone, channel=channel,
                     language=lang, body=reply, status=res["status"], provider_response=res))
    s.flush()
    return {"understood": kind, "reply": reply, "subscriber_found": sub is not None}
