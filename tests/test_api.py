"""API smoke tests on a throw-away SQLite database (no trained model needed)."""

import os
import tempfile
from datetime import date
from pathlib import Path

import pytest

_DB = Path(tempfile.mkdtemp()) / "varsha_test.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB.as_posix()}"
os.environ["OFFICER_USERNAME"] = "officer"
os.environ["OFFICER_PASSWORD"] = "test-pass"
os.environ["MESSAGING_MODE"] = "mock"

from fastapi.testclient import TestClient  # noqa: E402

from backend.db.models import (  # noqa: E402
    Advisory, Base, Block, District, Forecast, Panchayat, PanchayatForecast, Subscriber,
)
from backend.db.session import SyncSession, sync_engine  # noqa: E402
from backend.main import app  # noqa: E402
from backend.services.messaging import phone_hash  # noqa: E402

D = date(2023, 6, 12)
POLY = {"type": "Polygon", "coordinates": [[[78.0, 17.0], [78.2, 17.0], [78.2, 17.2], [78.0, 17.0]]]}
PROBS = dict(prob_onset=0.6, prob_false_onset=0.3, prob_dry_spell_7d=0.7, prob_dry_spell_14d=0.3,
             prob_heavy_rain=0.05, prob_very_heavy_rain=0.01, rainfall_q10=1, rainfall_q25=3,
             rainfall_median=6, rainfall_q75=12, rainfall_q90=20, rainfall_anomaly_pct=-70)


@pytest.fixture(scope="module")
def client():
    Base.metadata.drop_all(sync_engine)
    Base.metadata.create_all(sync_engine)
    with SyncSession() as s:
        s.add(District(id=1, name="Testdist", lgd_code=999, geometry=POLY))
        s.add(Block(id=1, name="Testblock", district_id=1, centroid_lat=17.1, centroid_lon=78.1, geometry=POLY))
        s.add(Panchayat(id=1, name="Test GP", block_id=1, centroid_lat=17.1, centroid_lon=78.1, geometry=POLY,
                        soil_type="red_loam", field_capacity=0.3, wilting_point=0.15, irrigated_fraction=0.2))
        s.flush()
        for h in (7, 14, 21, 30):
            s.add(Forecast(block_id=1, issue_date=D, horizon_days=h, valid_start=D, valid_end=D, **PROBS,
                           onset_status="provisional", current_regime="active", predicted_regime="break",
                           regime_probability=0.7, confidence_level="moderate", explanation_en="test",
                           top_drivers={"dry_spell_7d": [{"group": "MJO", "contribution": 0.4}]}, is_synthetic=True))
            s.add(PanchayatForecast(panchayat_id=1, block_id=1, issue_date=D, horizon_days=h, valid_start=D,
                                    valid_end=D, soil_moisture=0.3, **PROBS))
        s.add(Advisory(panchayat_id=1, issue_date=D, crop="cotton", action="WAIT", rule_id="sow_wait",
                       message_en="Wait 7 days", message_te="ఆగండి", message_hi="रुकें", sms_en="Varsha: WAIT",
                       sms_te="వర్ష: ఆగండి", sms_hi="वर्षा: रुकें", status="pending", reasoning={"x": 1}))
        s.add(Subscriber(name="F", phone="+910000001001", phone_hash=phone_hash("+910000001001"), role="farmer",
                         panchayat_id=1, block_id=1, crops=["cotton"], language="te", channel="sms"))
        s.commit()
    with TestClient(app) as c:
        yield c


AUTH = ("officer", "test-pass")


def test_health_and_dashboard(client):
    assert client.get("/health").json() == {"status": "ok"}
    d = client.get("/api/v1/dashboard/latest").json()
    assert d["issue_date"] == str(D)
    assert d["blocks"][0]["horizons"]["7"]["prob_dry_spell_7d"] == 0.7
    assert d["panchayats"][0]["advisories"]["cotton"]["action"] == "WAIT"


def test_geometry_round_trip(client):
    fc = client.get("/api/v1/boundaries/blocks").json()
    assert fc["features"][0]["geometry"]["type"] == "Polygon"


def test_forecast_endpoints(client):
    assert client.get("/api/v1/forecasts/block/1").json()["horizons"][0]["horizon_days"] == 7
    m = client.get("/api/v1/forecasts/map", params={"event": "dry_spell", "level": "panchayat"}).json()
    assert m["features"][0]["properties"]["value"] == 0.7
    assert client.get("/api/v1/forecasts/map", params={"horizon_days": 5}).status_code == 422


def test_officer_flow_and_dispatch(client):
    assert client.post("/api/v1/officer/approve-all").status_code == 401
    pending = client.get("/api/v1/officer/pending").json()
    adv_id = pending["advisories"][0]["id"]
    r = client.post(f"/api/v1/officer/review/{adv_id}", json={"action": "approve"}, auth=AUTH)
    assert r.json()["new_status"] == "approved"
    out = client.post("/api/v1/officer/dispatch", params={"issue_date": str(D)}, auth=AUTH).json()
    assert out["messages"] >= 1
    box = client.get("/api/v1/messaging/outbox").json()["messages"]
    assert any("వర్ష" in m["body"] for m in box)


def test_inbound_reply_creates_feedback(client):
    r = client.post("/api/v1/messaging/inbound", data={"from": "+910000001001", "text": "1"}).json()
    assert r["understood"] == "thanks" and r["subscriber_found"]
    s = client.get("/api/v1/feedback/summary/1").json()
    assert s["daily_summary"][0]["rain_yes"] == 1


def test_feedback_and_subscription(client):
    r = client.post("/api/v1/feedback/report", json={"panchayat_id": 1, "report_date": str(D), "rain_today": False})
    assert r.json()["status"] == "ok"
    r = client.post("/api/v1/messaging/subscribers", json={"phone": "+91 98765 43210", "panchayat_id": 1,
                                                            "crops": ["paddy"], "language": "hi"})
    assert r.json()["status"] == "created"
