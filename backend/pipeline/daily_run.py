"""
Varsha — Daily pipeline orchestrator.

    python -m backend.pipeline.daily_run --date 2023-07-01     # one issue date
    python -m backend.pipeline.daily_run --replay              # whole 2023 demo season
    python -m backend.pipeline.daily_run --date 2026-07-01 --dispatch   # + send approved advisories

Steps for an issue date t
  1. Data     load block climate + teleconnections; store observations up to t-1
  2. Events   observed onset status, regime (HMM), soil moisture (water balance)
  3. Models   hybrid ML forecast per block x horizon (7/14/21/30 days)
  4. Downscale block -> panchayat (IDW) + panchayat soil water balance
  5. Advise   seedling survival (analog ensemble) + expert-system rules per crop
  6. Store    forecasts, panchayat forecasts, advisories (pending officer review)
  7. Deliver  optional: dispatch approved advisories by SMS / WhatsApp
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
from sqlalchemy import delete, func, insert, select, update

from backend.db.models import (
    Advisory, Base, DailyObservation, DrySpellRecord, Forecast, MessageLog, OnsetRecord, Panchayat,
    PanchayatForecast, PipelineRun, TeleconnectionIndex,
)
from backend.db.session import SyncSession, sync_engine
from data.sources import DEMO_YEAR, load_panchayats
from impact.advisory_engine import AdvisoryContext, advise, needs_survival
from impact.water_balance import crop_params, relative_soil_moisture_series
from models import events as ev
from models.downscaling.panchayat import idw_weights
from models.forecast_engine import ForecastEngine
from models.features import HORIZONS
from models.onset.status import onset_status

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("varsha.pipeline")

CROPS = list(crop_params()["crops"].keys())
PROB_COLS = ["prob_onset", "prob_false_onset", "prob_dry_spell_7d", "prob_dry_spell_14d",
             "prob_heavy_rain", "prob_very_heavy_rain"]
Q_COLS = ["rainfall_q10", "rainfall_q25", "rainfall_median", "rainfall_q75", "rainfall_q90"]
FORECAST_COLS = {c.name for c in Forecast.__table__.columns} - {"id"}
SEASON_DOY = (135, 288)   # May 15 - Oct 15


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class PipelineContext:
    """Expensive state shared across days (model, climate, weights, sowing state)."""

    def __init__(self, engine: ForecastEngine | None = None):
        self.engine = engine or ForecastEngine()
        self.blocks = self.engine.blocks
        self.panchayats = load_panchayats()
        self.W = idw_weights(self.panchayats, self.blocks)
        self.bpos = {b["id"]: i for i, b in enumerate(self.blocks)}
        self.p_block_pos = np.array([self.bpos[p["block_id"]] for p in self.panchayats])
        self._panch_soil: dict[int, np.ndarray] = {}
        self.sowing: dict[tuple[int, str], date] = {}

    def panchayat_soil(self, year: int) -> np.ndarray:
        """Relative soil moisture [T, n_panchayats] with each panchayat's own soil."""
        if year not in self._panch_soil:
            st = self.engine.season(year)
            rain = st.rain[:, self.p_block_pos]
            eto = st.eto[:, self.p_block_pos]
            fc = np.array([p["field_capacity"] for p in self.panchayats])
            wp = np.array([p["wilting_point"] for p in self.panchayats])
            sm = relative_soil_moisture_series(rain, eto, fc=fc, wp=wp)
            self._panch_soil[year] = np.vstack([sm[:1], sm[:-1]])  # value at start of day
        return self._panch_soil[year]

    def load_sowing_state(self, s, season_start: date, before: date):
        rows = s.execute(
            select(Advisory.panchayat_id, Advisory.crop, func.min(Advisory.issue_date))
            .where(Advisory.action == "SOW", Advisory.status != "rejected",
                   Advisory.issue_date >= season_start, Advisory.issue_date < before)
            .group_by(Advisory.panchayat_id, Advisory.crop)
        ).all()
        self.sowing = {(r[0], r[1]): r[2] for r in rows}


# ─── Step 1: observations ────────────────────────────────────────────────────

def store_observations(s, ctx: PipelineContext, year: int, until: date):
    """Insert missing block observations for the season up to `until` (inclusive)."""
    st = ctx.engine.season(year)
    have = {(r[0], r[1]) for r in s.execute(
        select(DailyObservation.block_id, DailyObservation.obs_date)
        .where(DailyObservation.obs_date >= st.dates[0].date(), DailyObservation.obs_date <= until)).all()}
    th = ev.thresholds()["rainfall"]
    source = "synthetic" if ctx.engine.cd.is_synthetic else "chirps"
    rows = []
    for t, ts in enumerate(st.dates):
        d = ts.date()
        if d > until:
            break
        for b in ctx.blocks:
            if (b["id"], d) in have:
                continue
            bi = ctx.bpos[b["id"]]
            r = float(st.rain[t, bi])
            os_ = st.onset_idx[bi]
            regime = "pre_onset" if os_ < 0 or os_ > t else ("break" if st.p_break[min(t + 1, len(st.dates) - 1), bi] >= 0.5 else "active")
            rows.append({
                "block_id": b["id"], "obs_date": d, "rainfall_mm": r, "rainfall_source": source,
                "tmax_c": float(st.tmax[t, bi]), "tmin_c": float(st.tmin[t, bi]),
                "eto_mm": round(float(st.eto[t, bi]), 2),
                "soil_moisture": round(float(st.soil[min(t + 1, len(st.dates) - 1), bi]), 3),
                "is_rainy_day": r >= th["rainy_day"], "is_heavy_rain": r >= th["heavy"],
                "is_very_heavy_rain": r >= th["very_heavy"], "regime": regime,
            })
    if rows:
        s.execute(insert(DailyObservation), rows)
    return len(rows)


def store_teleconnections(s, ctx: PipelineContext, start: date, end: date):
    drv = ctx.engine.cd.drivers.loc[str(start):str(end)]
    s.execute(delete(TeleconnectionIndex).where(TeleconnectionIndex.obs_date >= start,
                                                TeleconnectionIndex.obs_date <= end))
    src = ctx.engine.cd.sources
    rows = []
    for ts, r in drv.iterrows():
        d = ts.date()
        rows += [
            {"index_name": "oni", "obs_date": d, "value": round(float(r["oni"]), 3), "source": src.get("oni")},
            {"index_name": "dmi", "obs_date": d, "value": round(float(r["dmi"]), 3), "source": src.get("dmi")},
            {"index_name": "mjo", "obs_date": d, "value": round(float(r["rmm1"]), 3), "phase": int(r["mjo_phase"]),
             "amplitude": round(float(r["mjo_amp"]), 3), "source": src.get("mjo")},
            {"index_name": "rmm2", "obs_date": d, "value": round(float(r["rmm2"]), 3), "source": src.get("mjo")},
        ]
        if "u850" in r:
            rows.append({"index_name": "u850", "obs_date": d, "value": round(float(r["u850"]), 2), "source": "simulated regional field"})
            rows.append({"index_name": "olr", "obs_date": d, "value": round(float(r["olr"]), 2), "source": "simulated regional field"})
    if rows:
        s.execute(insert(TeleconnectionIndex), rows)


def store_season_events(s, ctx: PipelineContext, year: int, until: date):
    """Observed onset / false onset / dry spells per block for the season so far."""
    st = ctx.engine.season(year)
    t_end = int(np.searchsorted(st.dates.values, np.datetime64(until)) + 1)
    s.execute(delete(OnsetRecord).where(OnsetRecord.year == year))
    s.execute(delete(DrySpellRecord).where(DrySpellRecord.year == year))
    th = ev.thresholds()
    onsets, spells = [], []
    for b in ctx.blocks:
        bi = ctx.bpos[b["id"]]
        r = st.rain[:t_end, bi]
        d = st.dates[:t_end]
        so = ev.season_onset(r, d)
        status = onset_status(st.rain[:, bi], st.doys, t_end)
        if so["onset_idx"] is not None:
            onsets.append({
                "block_id": b["id"], "year": year, "onset_date": d[so["onset_idx"]].date(),
                "onset_doy": int(d[so["onset_idx"]].dayofyear), "is_false_onset": bool(so["is_false"]),
                "dry_spell_start": d[so["dry_start_idx"]].date() if so["dry_start_idx"] is not None else None,
                "dry_spell_length_days": so["dry_len"] or None,
                "true_onset_date": (st.dates[status["onset_idx"]].date()
                                    if status["status"] in ("established", "provisional") else None),
            })
        doys = d.dayofyear.values
        onset_doy = int(d[so["onset_idx"]].dayofyear) if so["onset_idx"] is not None else 999
        for sp in ev.detect_dry_spells(r[np.flatnonzero(doys >= 135)[0]:] if (doys >= 135).any() else r,
                                       th["dry_spell"]["min_rain_threshold"], 7):
            off = int(np.flatnonzero(doys >= 135)[0]) if (doys >= 135).any() else 0
            a, z = sp["start"] + off, sp["end"] + off
            sd = int(doys[a])
            phase = "pre_onset" if sd < onset_doy else ("early" if sd < 196 else ("mid" if sd < 244 else "late"))
            spells.append({"block_id": b["id"], "year": year, "start_date": d[a].date(), "end_date": d[z].date(),
                           "length_days": int(sp["length"]), "season_phase": phase})
    if onsets:
        s.execute(insert(OnsetRecord), onsets)
    if spells:
        s.execute(insert(DrySpellRecord), spells)


# ─── Steps 3-6: forecast, downscale, advise, store ───────────────────────────

def run_day(s, ctx: PipelineContext, d: date, approve: bool = False, approver: str = "auto") -> dict:
    eng = ctx.engine
    fc = eng.forecast(d)
    t = eng.day_index(d)

    # Re-running a date replaces pending advisories only; officer-reviewed ones are kept
    reviewed = {(r[0], r[1]) for r in s.execute(
        select(Advisory.panchayat_id, Advisory.crop).where(Advisory.issue_date == d, Advisory.status != "pending")).all()}
    s.execute(delete(Advisory).where(Advisory.issue_date == d, Advisory.status == "pending"))
    s.execute(update(Advisory).where(Advisory.issue_date == d).values(forecast_id=None))

    # Block forecasts
    s.execute(delete(Forecast).where(Forecast.issue_date == d))
    rows = [{k: v for k, v in r.items() if k in FORECAST_COLS} for r in fc.to_dict("records")]
    for r in rows:
        r["onset_date_observed"] = r["onset_date_observed"] if pd.notna(r.get("onset_date_observed")) else None
    s.execute(insert(Forecast), rows)
    fid = {(r[0], r[1]): r[2] for r in s.execute(
        select(Forecast.block_id, Forecast.horizon_days, Forecast.id).where(Forecast.issue_date == d)).all()}

    # Panchayat forecasts (IDW over blocks for every horizon)
    soil_p = ctx.panchayat_soil(d.year)[t]
    s.execute(delete(PanchayatForecast).where(PanchayatForecast.issue_date == d))
    pf_rows, pf_by = [], {}
    for h in HORIZONS:
        g = fc[fc["horizon_days"] == h].set_index("block_id").loc[[b["id"] for b in ctx.blocks]]
        vals = ctx.W @ g[PROB_COLS + Q_COLS + ["clim_total_med", "clim_prob_dry_spell_7d"]].values
        for i, p in enumerate(ctx.panchayats):
            rec = dict(zip(PROB_COLS + Q_COLS, np.round(vals[i, :len(PROB_COLS) + len(Q_COLS)], 4)))
            clim_med = float(vals[i, -2])
            clim_dry7 = float(vals[i, -1])
            rec = {k: float(v) for k, v in rec.items()}
            rec.update({
                "panchayat_id": p["id"], "block_id": p["block_id"], "issue_date": d, "horizon_days": h,
                "valid_start": d, "valid_end": d + timedelta(days=h - 1),
                "rainfall_anomaly_pct": round(100 * (rec["rainfall_median"] - clim_med) / max(clim_med, 5.0), 1),
                "soil_moisture": round(float(soil_p[i]), 3), "is_synthetic": bool(eng.cd.is_synthetic),
            })
            pf_rows.append(rec)
            pf_by[(p["id"], h)] = {**rec, "clim_prob_dry_spell_7d": clim_dry7}
    s.execute(insert(PanchayatForecast), pf_rows)

    # Advisories
    bstate = fc[fc["horizon_days"] == 7].set_index("block_id")
    fc_by_block = {(int(r["block_id"]), int(r["horizon_days"])): r for r in fc.to_dict("records")}
    adv_rows = []
    lat_ok = {}
    for i, p in enumerate(ctx.panchayats):
        b = bstate.loc[p["block_id"]]
        forecast = {h: pf_by[(p["id"], h)] for h in HORIZONS}
        for crop in CROPS:
            if (p["id"], crop) in reviewed:
                continue
            sow = ctx.sowing.get((p["id"], crop))
            survival = None
            if needs_survival(crop, d, sow):
                key = (p["block_id"], p["soil_type"], round(soil_p[i], 2), crop)
                if key not in lat_ok:
                    lat_ok[key] = eng.seedling_survival(
                        p["block_id"], d, fc_by_block[(p["block_id"], 14)], fc_by_block[(p["block_id"], 30)],
                        crop, p["field_capacity"], p["wilting_point"], float(soil_p[i]))
                survival = lat_ok[key]
                if crop == "paddy":  # nurseries are mostly raised under irrigation
                    survival = p["irrigated_fraction"] + (1 - p["irrigated_fraction"]) * survival
            actx = AdvisoryContext(
                issue_date=d, panchayat=p, crop=crop, forecast=forecast,
                onset_status=b["onset_status"],
                onset_date=b["onset_date_observed"] if pd.notna(b["onset_date_observed"]) else None,
                current_regime=b["current_regime"], soil_moisture=float(soil_p[i]),
                confidence=b["confidence_level"], sowing_date=sow, survival=survival,
                rain_14d_mm=float(b["rain_14d_obs"]))
            rec = advise(actx)
            rec["forecast_id"] = fid.get((p["block_id"], 7))
            rec["is_synthetic"] = bool(eng.cd.is_synthetic)
            if approve:
                rec.update(status="approved", approved_by=approver, approved_at=utcnow())
            else:
                rec["status"] = "pending"
            adv_rows.append(rec)
            if rec["action"] == "SOW" and sow is None:
                ctx.sowing[(p["id"], crop)] = d
    if adv_rows:
        s.execute(insert(Advisory), adv_rows)
    actions = pd.Series([r["action"] for r in adv_rows]).value_counts().to_dict()
    return {"forecasts": len(rows), "panchayat_forecasts": len(pf_rows), "advisories": len(adv_rows),
            "actions": actions}


def in_season(d: date) -> bool:
    return SEASON_DOY[0] <= d.timetuple().tm_yday <= SEASON_DOY[1]


def run_pipeline(target_date: date | None = None, ctx: PipelineContext | None = None,
                 dispatch: bool = False, approve: bool = False, force: bool = False) -> dict:
    """Run the full pipeline for one issue date and record a PipelineRun."""
    target_date = target_date or date.today()
    Base.metadata.create_all(sync_engine)
    t0 = time.time()
    with SyncSession() as s:
        run = PipelineRun(run_date=target_date, status="running")
        s.add(run)
        s.commit()
        try:
            if not force and not in_season(target_date):
                run.status, run.message = "skipped", "Outside the Kharif forecast season (May 15 - Oct 15)"
                run.finished_at = utcnow()
                s.commit()
                logger.info(run.message)
                return {"status": "skipped", "message": run.message}
            ctx = ctx or PipelineContext()
            if not ctx.engine.has_data(target_date):
                raise ValueError(f"No observations available up to {target_date - timedelta(days=1)}")
            season_start = date(target_date.year, 4, 1)
            store_observations(s, ctx, target_date.year, target_date - timedelta(days=1))
            store_teleconnections(s, ctx, target_date - timedelta(days=60), target_date)
            ctx.load_sowing_state(s, season_start, target_date)
            res = run_day(s, ctx, target_date, approve=approve)
            store_season_events(s, ctx, target_date.year, target_date - timedelta(days=1))
            if dispatch:
                from backend.services.messaging import dispatch_approved
                res["dispatched"] = dispatch_approved(s, target_date)
            run.status, run.n_forecasts, run.n_advisories = "success", res["forecasts"], res["advisories"]
            run.model_version = ctx.engine.version
            run.data_sources = ctx.engine.cd.sources
            run.message = f"actions: {res['actions']}"
            run.finished_at = utcnow()
            s.commit()
            logger.info("Pipeline %s done in %.1fs: %s", target_date, time.time() - t0, res)
            return {"status": "success", **res}
        except Exception as exc:
            s.rollback()
            run = s.get(PipelineRun, run.id)
            run.status, run.message, run.finished_at = "failed", str(exc)[:500], utcnow()
            s.commit()
            logger.exception("Pipeline failed for %s", target_date)
            raise


def run_season(year: int = DEMO_YEAR, start: date | None = None, end: date | None = None,
               step: int = 1, ctx: PipelineContext | None = None, pending_dates: set | None = None) -> dict:
    """Replay a whole season day by day. Advisories are auto-approved except on `pending_dates`
    (default: the configured demo date, else the last day), which are left for officer review."""
    start = start or date(year, 5, 15)
    end = end or date(year, 10, 15)
    Base.metadata.create_all(sync_engine)
    ctx = ctx or PipelineContext()
    t0 = time.time()
    days = [start + timedelta(days=i) for i in range(0, (end - start).days + 1, step)]
    if pending_dates is None:
        from backend.services.bundles import _demo_date
        demo = _demo_date()
        pending_dates = {demo} if demo and demo in days else {days[-1]}
    with SyncSession() as s:
        n_obs = store_observations(s, ctx, year, end)
        store_teleconnections(s, ctx, start - timedelta(days=60), end)
        ctx.load_sowing_state(s, date(year, 4, 1), start)
        s.commit()
        logger.info("Replay %s: %d issue dates, %d new observation rows", year, len(days), n_obs)
        totals = {}
        for i, d in enumerate(days):
            last = i == len(days) - 1
            res = run_day(s, ctx, d, approve=d not in pending_dates, approver="auto (replay)")
            for k, v in res["actions"].items():
                totals[k] = totals.get(k, 0) + v
            if i % 15 == 0 or last:
                s.commit()
                logger.info("  %s  (%d/%d, %.0fs) actions=%s", d, i + 1, len(days), time.time() - t0, res["actions"])
        store_season_events(s, ctx, year, end)
        s.add(PipelineRun(run_date=end, status="success", finished_at=utcnow(), model_version=ctx.engine.version,
                          n_forecasts=len(days) * len(ctx.blocks) * len(HORIZONS),
                          n_advisories=len(days) * len(ctx.panchayats) * len(CROPS),
                          data_sources=ctx.engine.cd.sources, message=f"replay {start}..{end}: {totals}"))
        s.commit()
    logger.info("Replay finished in %.0fs: %s", time.time() - t0, totals)
    return {"days": len(days), "actions": totals}


def main():
    ap = argparse.ArgumentParser(description="Varsha daily pipeline")
    ap.add_argument("--date", type=str, default=None, help="Issue date YYYY-MM-DD (default: today)")
    ap.add_argument("--replay", action="store_true", help="Replay the whole demo season")
    ap.add_argument("--year", type=int, default=DEMO_YEAR)
    ap.add_argument("--dispatch", action="store_true", help="Send approved advisories after the run")
    ap.add_argument("--approve", action="store_true", help="Auto-approve generated advisories")
    ap.add_argument("--force", action="store_true", help="Run even outside the Kharif season")
    args = ap.parse_args()
    if args.replay:
        run_season(args.year)
    else:
        d = date.fromisoformat(args.date) if args.date else date.today()
        run_pipeline(d, dispatch=args.dispatch, approve=args.approve, force=args.force)


if __name__ == "__main__":
    main()
