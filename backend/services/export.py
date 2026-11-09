"""
Varsha — Static export for the web app.

Writes frontend/public/data/{latest,replay,blocks,panchayats}.json from the
database so the frontend can run (read-only) without the API, e.g. on a
static host for judges. The officer console and feedback still need the API.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from backend.db.session import SyncSession
from backend.services import bundles

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "frontend" / "public" / "data"


def _dump(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"), default=str)
    logger.info("wrote %s (%.0f KB)", path.relative_to(ROOT), path.stat().st_size / 1024)


def export_static(out_dir: Path = OUT_DIR, year: int = 2023, issue_date: date | None = None) -> dict:
    with SyncSession() as s:
        latest = bundles.dashboard_bundle(s, issue_date)
        if not latest.get("issue_date"):
            raise RuntimeError("No forecasts in the database; run the pipeline first")
        d = date.fromisoformat(latest["issue_date"])
        _dump(latest, out_dir / "latest.json")
        _dump({str(b["id"]): bundles.block_detail(s, b["id"], d) for b in latest["blocks"]}, out_dir / "blocks.json")
        _dump({str(p["id"]): bundles.panchayat_detail(s, p["id"], d) for p in latest["panchayats"]},
              out_dir / "panchayats.json")
        _dump(bundles.replay_bundle(s, year), out_dir / "replay.json")
        _dump(bundles.skill_report(), out_dir / "skill.json")
    return {"issue_date": latest["issue_date"], "out_dir": str(out_dir)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    print(export_static())
