"""
Varsha — One-command demo setup.

    python scripts/bootstrap_demo.py            # build everything that is missing
    python scripts/bootstrap_demo.py --reset    # drop all tables first
    python scripts/bootstrap_demo.py --retrain  # retrain the model even if one exists

Steps
  1. Create tables (SQLite by default, PostGIS if DATABASE_URL points to Postgres)
  2. Build boundaries (blocks, panchayat polygons + soils) and load them
  3. Train the hybrid model + leave-years-out hindcast (artifacts/models/)
  4. Write per-block hindcast skill / trust scores to the blocks table
  5. Seed demo subscribers (fake numbers, flagged synthetic; never messaged for real)
  6. Replay the 2023 Kharif season day by day (forecasts + advisories)
  7. Export static JSON for the web app (frontend/public/data/)
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, select  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("bootstrap")


def seed_subscribers(s, panchayats: list[dict], blocks: list[dict]) -> int:
    from backend.db.models import Subscriber
    from backend.services.messaging import phone_hash

    if s.execute(select(Subscriber.id).limit(1)).first():
        return 0
    crops_cycle = [["cotton", "groundnut"], ["paddy"], ["soybean", "cotton"], ["groundnut", "paddy"]]
    langs = ["te", "te", "hi", "en"]
    n = 0
    for p in panchayats:
        for k in range(2):
            idx = (p["id"] + k) % 4
            phone = f"+910000{p['id']:03d}{k:03d}"   # invalid (leading 0) on purpose: demo only
            s.add(Subscriber(name=f"Demo farmer {p['id']}-{k + 1}", phone=phone, phone_hash=phone_hash(phone),
                             role="farmer", panchayat_id=p["id"], block_id=p["block_id"],
                             crops=crops_cycle[idx], language=langs[idx],
                             channel="whatsapp" if k else "sms", is_synthetic=True))
            n += 1
    for b in blocks:
        phone = f"+910001{b['id']:03d}000"
        s.add(Subscriber(name=f"AEO {b['name']}", phone=phone, phone_hash=phone_hash(phone),
                         role="extension_officer", block_id=b["id"], language="en", channel="sms",
                         is_synthetic=True))
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description="Set up the Varsha demo end to end")
    ap.add_argument("--reset", action="store_true", help="drop and recreate all tables")
    ap.add_argument("--retrain", action="store_true", help="retrain the model")
    ap.add_argument("--year", type=int, default=2023)
    ap.add_argument("--step", type=int, default=1, help="replay every N days")
    ap.add_argument("--skip-replay", action="store_true")
    args = ap.parse_args()
    t0 = time.time()

    from backend.db.models import Advisory, Base, Block, DailyObservation, Forecast, MessageLog, PanchayatForecast
    from backend.db.session import DATABASE_URL, SyncSession, sync_engine
    from backend.pipeline.daily_run import PipelineContext, run_season
    from backend.services.export import export_static
    from data.sources import load_blocks, load_panchayats
    from models.forecast_engine import ForecastEngine
    from models.train import BUNDLE_PATH, load_bundle, train
    from scripts.load_boundaries import build_all, load_config, load_to_database

    logger.info("Database: %s", DATABASE_URL.split("@")[-1])
    if args.reset:
        Base.metadata.drop_all(sync_engine)
    Base.metadata.create_all(sync_engine)

    logger.info("Step 2/7: boundaries")
    d, b, p = build_all(regenerate=False)
    load_to_database(load_config(), d, b, p)
    load_blocks.cache_clear()
    load_panchayats.cache_clear()

    logger.info("Step 3/7: model")
    bundle = None if args.retrain else load_bundle()
    if bundle is None:
        bundle = train()
    else:
        logger.info("Using existing model %s (%s)", bundle["model_version"], BUNDLE_PATH.name)

    logger.info("Step 4/7: block skill")
    with SyncSession() as s:
        for bid, sk in bundle["skill"]["blocks"].items():
            blk = s.get(Block, int(bid))
            if blk:
                blk.bss_onset = sk.get("bss_onset")
                blk.bss_dry_spell = sk.get("bss_dry_spell_7d")
                blk.bss_heavy_rain = sk.get("bss_heavy_rain")
                blk.trust_score = sk.get("trust_score")
        logger.info("Step 5/7: subscribers (+%d)", seed_subscribers(s, load_panchayats(), load_blocks()))
        s.commit()

    if not args.skip_replay:
        logger.info("Step 6/7: replay %s season", args.year)
        with SyncSession() as s:  # replay is idempotent per day; clear the season first
            from datetime import date
            lo, hi = date(args.year, 1, 1), date(args.year, 12, 31)
            from sqlalchemy import update
            season_adv = select(Advisory.id).where(Advisory.issue_date >= lo, Advisory.issue_date <= hi)
            s.execute(update(MessageLog).where(MessageLog.advisory_id.in_(season_adv)).values(advisory_id=None))
            for model in (Advisory, PanchayatForecast, Forecast, DailyObservation):
                col = model.obs_date if model is DailyObservation else model.issue_date
                s.execute(delete(model).where(col >= lo, col <= hi))
            s.commit()
        ctx = PipelineContext(ForecastEngine(bundle))
        run_season(args.year, step=args.step, ctx=ctx)

    logger.info("Step 7/7: static export")
    logger.info("%s", export_static(year=args.year))
    logger.info("Done in %.0fs. Start the API:  uvicorn backend.main:app --reload", time.time() - t0)


if __name__ == "__main__":
    main()
