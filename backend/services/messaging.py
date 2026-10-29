"""
Varsha — Messaging Service (Mock + Real Adapters)

Default: mock mode — logs messages and stores them for the phone preview UI.
Production: WhatsApp Cloud API and SMS gateway adapters.
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

MESSAGING_MODE = os.getenv("MESSAGING_MODE", "mock")

# Mock message store (in-memory for prototype; a real version uses DB)
_mock_messages: list[dict] = []


@dataclass
class Message:
    """A message to be delivered to a farmer."""
    recipient_phone: str
    panchayat_name: str
    crop: str
    action: str
    message_text: str
    language: str
    channel: str  # 'whatsapp', 'sms', 'ivr'
    sent_at: Optional[str] = None
    status: str = "queued"


def send_message(msg: Message) -> dict:
    """
    Send a message via the configured channel.
    In mock mode, stores the message for the phone preview UI.
    """
    if MESSAGING_MODE == "mock":
        return _send_mock(msg)
    elif MESSAGING_MODE == "whatsapp":
        return _send_whatsapp(msg)
    elif MESSAGING_MODE == "sms":
        return _send_sms(msg)
    else:
        return _send_mock(msg)


def _send_mock(msg: Message) -> dict:
    """Mock sender — logs and stores the message."""
    msg.sent_at = datetime.utcnow().isoformat()
    msg.status = "delivered_mock"
    record = asdict(msg)
    _mock_messages.append(record)
    logger.info(f"[MOCK] Message to {msg.recipient_phone}: {msg.message_text[:80]}...")

    # Also write to a JSON file for persistence
    mock_dir = Path("data/mock_messages")
    mock_dir.mkdir(parents=True, exist_ok=True)
    with open(mock_dir / "messages.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")

    return {"status": "mock_delivered", "message_id": len(_mock_messages)}


def _send_whatsapp(msg: Message) -> dict:
    """WhatsApp Cloud API sender (requires WHATSAPP_TOKEN)."""
    import httpx

    token = os.getenv("WHATSAPP_TOKEN")
    phone_id = os.getenv("WHATSAPP_PHONE_ID")

    if not token or not phone_id:
        logger.warning("WhatsApp credentials not set, falling back to mock")
        return _send_mock(msg)

    url = f"https://graph.facebook.com/v18.0/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": msg.recipient_phone,
        "type": "text",
        "text": {"body": msg.message_text},
    }

    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        return {"status": "sent", "response": resp.json()}
    except Exception as e:
        logger.error(f"WhatsApp send failed: {e}")
        return {"status": "failed", "error": str(e)}


def _send_sms(msg: Message) -> dict:
    """SMS gateway sender (placeholder — adapt to your provider)."""
    logger.warning("SMS sending not implemented, falling back to mock")
    return _send_mock(msg)


def get_mock_messages(limit: int = 50) -> list[dict]:
    """Return recent mock messages for the phone preview UI."""
    return _mock_messages[-limit:]


def clear_mock_messages():
    """Clear mock message store."""
    _mock_messages.clear()
