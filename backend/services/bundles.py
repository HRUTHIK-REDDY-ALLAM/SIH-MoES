"""
Varsha — Read models for the web app.

Synchronous builders over a SQLAlchemy Session. The async API calls them via
`await db.run_sync(...)`, and the static exporter calls them directly to
write frontend/public/data/*.json, so the app also works with no backend.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import func, select

from backend.db.models import (
    Advisory, Block, DailyObservation, District, DrySpellRecord, Forecast, OnsetRecord, Panchayat,
    PanchayatForecast, PipelineRun, TeleconnectionIndex,
)

ROOT = Path(__file__).resolve().parents[2]
SKILL_REPORT = ROOT / "artifacts" / "models" / "skill_report.json"
HORIZONS = [7, 14, 21, 30]
PROBS = ["prob_onset", "prob_false_onset", "prob_dry_spell_7d", "prob_dry_spell_14d",
         "prob_heavy_rain", "prob_very_heavy_rain"]
QUANTS = ["rainfall_q10", "rainfall_q25", "rainfall_median", "rainfall_q75", "rainfall_q90"]
CROPS = ["cotton", "soybean", "groundnut", "paddy"]
ACTION_CODES = ["SOW", "WAIT", "SWITCH", "PROTECT", "IRRIGATE", "CONSERVE", "PREPARE", "ALERT", "RESOW_ALERT", "NORMAL"]
ONSET_CODES = ["not_yet", "provisional", "established", "false_onset"]


def _r(x, n=3):
    return None if x is None else round(float(x), n)


def _demo_date() -> date | None:
    import yaml

    with open(ROOT / "config" / "pilot_region.yaml", encoding="utf-8") as f:
        d = yaml.safe_load(f).get("replay", {}).get("demo_issue_date")
    return date.fromisoformat(d) if d else None


def latest_issue_date(s) -> date | None:
    """Default issue date: the configured demo date in a replay database, else the newest forecast."""
    newest = s.execute(select(func.max(Forecast.issue_date))).scalar()
    demo = _demo_date()
    if newest and demo and newest.year == demo.year:
        has = s.execute(select(Forecast.id).where(Forecast.issue_date == demo).limit(1)).first()
        if has:
            return demo
    return newest


def skill_report() -> dict:
    if not SKILL_REPORT.exists():
        return {}
    with open(SKILL_REPORT, encoding="utf-8") as f:
        return json.load(f)


def compact_skill() -> dict:
    """BSS/AUC per event and horizon without reliability tables."""
    rep = skill_report()
    if not rep:
        return {}
    out = {"model_version": rep.get("model_version"), "trained_at": rep.get("trained_at"),
           "train_years": [min(rep.get("train_years", [0])), max(rep.get("train_years", [0]))],
           "n_training_rows": rep.get("n_training_rows")}
    for key, val in rep.get("skill", {}).items():
        if key == "blocks" or not val:
            continue
        out[key] = {e: {h: {"bss": m["bss"], "auc": m["auc"], "base_rate": m["base_rate"]} for h, m in by_h.items()}
                    for e, by_h in val.get("by_event", {}).items()}
    return out


def driver_state(s, d: date) -> dict:
    """Teleconnection snapshot as known on date d (publication lags applied)."""
    from data.sources import driver_snapshot

    rows = s.execute(select(TeleconnectionIndex.index_name, TeleconnectionIndex.obs_date, TeleconnectionIndex.value,
                            TeleconnectionIndex.source)
                     .where(TeleconnectionIndex.obs_date >= d - timedelta(days=60),
                            TeleconnectionIndex.obs_date <= d)).all()
    if not rows:
        return {}
    df = pd.DataFrame(rows, columns=["name", "date", "value", "source"])
    wide = df.pivot_table(index="date", columns="name", values="value")
    wide.index = pd.to_datetime(wide.index)
    wide = wide.rename(columns={"mjo": "rmm1"})
    snap = driver_snapshot(wide, d)
    snap["sources"] = dict(df.drop_duplicates("name").set_index("name")["source"])
    return snap


def _forecast_dict(f) -> dict:
    out = {k: _r(getattr(f, k), 4) for k in PROBS}
    out.update({k: _r(getattr(f, k), 1) for k in QUANTS})
    out["rainfall_anomaly_pct"] = _r(f.rainfall_anomaly_pct, 1)
    return out


def dashboard_bundle(s, issue_date: date | None = None) -> dict:
    d = issue_date or latest_issue_date(s)
    if d is None:
        return {"issue_date": None, "blocks": [], "panchayats": []}
    districts = {x.id: x.name for x in s.execute(select(District)).scalars()}
    blocks = {b.id: b for b in s.execute(select(Block)).scalars()}
    fcs = s.execute(select(Forecast).where(Forecast.issue_date == d)).scalars().all()
    by_block: dict[int, dict] = defaultdict(dict)
    for f in fcs:
        rec = _forecast_dict(f)
        rec.update({
            "clim_prob_onset": _r(f.clim_prob_onset), "clim_prob_dry_spell_7d": _r(f.clim_prob_dry_spell_7d),
            "clim_prob_heavy_rain": _r(f.clim_prob_heavy_rain),
            "predicted_regime": f.predicted_regime, "regime_probability": _r(f.regime_probability),
            "confidence_level": f.confidence_level, "brier_skill_score": _r(f.brier_skill_score),
            "explanation_en": f.explanation_en, "top_drivers": f.top_drivers,
        })
        by_block[f.block_id][str(f.horizon_days)] = rec
    state = {f.block_id: f for f in fcs if f.horizon_days == 7}

    block_list = []
    for bid, b in sorted(blocks.items()):
        st = state.get(bid)
        block_list.append({
            "id": bid, "name": b.name, "district": districts.get(b.district_id), "district_id": b.district_id,
            "lat": b.centroid_lat, "lon": b.centroid_lon, "elevation_m": b.elevation_m,
            "trust_score": _r(b.trust_score), "bss_onset": _r(b.bss_onset), "bss_dry_spell": _r(b.bss_dry_spell),
            "bss_heavy_rain": _r(b.bss_heavy_rain),
            "onset_status": st.onset_status if st else None,
            "onset_date": str(st.onset_date_observed) if st and st.onset_date_observed else None,
            "current_regime": st.current_regime if st else None,
            "horizons": by_block.get(bid, {}),
        })

    panchs = {p.id: p for p in s.execute(select(Panchayat)).scalars()}
    pfs = s.execute(select(PanchayatForecast).where(PanchayatForecast.issue_date == d)).scalars().all()
    p_h: dict[int, dict] = defaultdict(dict)
    soil = {}
    for f in pfs:
        p_h[f.panchayat_id][str(f.horizon_days)] = _forecast_dict(f)
        soil[f.panchayat_id] = f.soil_moisture
    advs = s.execute(select(Advisory).where(Advisory.issue_date == d)).scalars().all()
    p_adv: dict[int, dict] = defaultdict(dict)
    action_counts: dict[str, Counter] = defaultdict(Counter)
    for a in advs:
        p_adv[a.panchayat_id][a.crop] = {"action": a.action, "survival": _r(a.seedling_survival_prob, 2),
                                         "stage": a.crop_stage, "status": a.status, "id": a.id}
        action_counts[a.crop][a.action] += 1
    panch_list = [{
        "id": pid, "name": p.name, "block_id": p.block_id, "soil_type": p.soil_type,
        "irrigated_fraction": p.irrigated_fraction, "soil_moisture": _r(soil.get(pid)),
        "horizons": p_h.get(pid, {}), "advisories": p_adv.get(pid, {}),
    } for pid, p in sorted(panchs.items())]

    run = s.execute(select(PipelineRun).where(PipelineRun.status == "success")
                    .order_by(PipelineRun.id.desc()).limit(1)).scalar_one_or_none()
    any_f = fcs[0] if fcs else None
    return {
        "issue_date": str(d),
        "model_version": any_f.model_version if any_f else None,
        "is_synthetic": bool(any_f.is_synthetic) if any_f else True,
        "data_sources": run.data_sources if run else {},
        "horizons": HORIZONS,
        "blocks": block_list,
        "panchayats": panch_list,
        "drivers": driver_state(s, d),
        "skill": compact_skill(),
        "summary": {
            "actions_by_crop": {c: dict(v) for c, v in action_counts.items()},
            "onset_status": dict(Counter(b["onset_status"] for b in block_list if b["onset_status"])),
            "pending_advisories": sum(1 for a in advs if a.status == "pending"),
        },
    }


def block_detail(s, block_id: int, issue_date: date | None = None) -> dict | None:
    d = issue_date or latest_issue_date(s)
    b = s.get(Block, block_id)
    if b is None or d is None:
        return None
    dist = s.get(District, b.district_id)
    fcs = s.execute(select(Forecast).where(Forecast.block_id == block_id, Forecast.issue_date == d)
                    .order_by(Forecast.horizon_days)).scalars().all()
    obs = s.execute(select(DailyObservation).where(DailyObservation.block_id == block_id,
                                                   DailyObservation.obs_date >= d - timedelta(days=45),
                                                   DailyObservation.obs_date < d)
                    .order_by(DailyObservation.obs_date)).scalars().all()
    season_start = date(d.year, 5, 15)
    ts = s.execute(select(Forecast.issue_date, Forecast.prob_onset, Forecast.prob_dry_spell_7d,
                          Forecast.prob_heavy_rain, Forecast.rainfall_median, Forecast.clim_prob_dry_spell_7d)
                   .where(Forecast.block_id == block_id, Forecast.horizon_days == 7,
                          Forecast.issue_date >= season_start, Forecast.issue_date <= d)
                   .order_by(Forecast.issue_date)).all()
    panchs = s.execute(select(Panchayat).where(Panchayat.block_id == block_id).order_by(Panchayat.id)).scalars().all()
    advs = s.execute(select(Advisory).where(Advisory.issue_date == d,
                                            Advisory.panchayat_id.in_([p.id for p in panchs]))).scalars().all()
    adv_by: dict[int, list] = defaultdict(list)
    for a in advs:
        adv_by[a.panchayat_id].append(advisory_dict(a))
    onset = s.execute(select(OnsetRecord).where(OnsetRecord.block_id == block_id, OnsetRecord.year == d.year)).scalar_one_or_none()
    return {
        "id": b.id, "name": b.name, "district": dist.name if dist else None, "issue_date": str(d),
        "elevation_m": b.elevation_m, "trust_score": _r(b.trust_score),
        "skill": {"onset": _r(b.bss_onset), "dry_spell": _r(b.bss_dry_spell), "heavy_rain": _r(b.bss_heavy_rain)},
        "horizons": [{
            "horizon_days": f.horizon_days, "valid_start": str(f.valid_start), "valid_end": str(f.valid_end),
            **_forecast_dict(f),
            "clim_prob_onset": _r(f.clim_prob_onset), "clim_prob_dry_spell_7d": _r(f.clim_prob_dry_spell_7d),
            "clim_prob_heavy_rain": _r(f.clim_prob_heavy_rain),
            "predicted_regime": f.predicted_regime, "regime_probability": _r(f.regime_probability),
            "confidence_level": f.confidence_level, "brier_skill_score": _r(f.brier_skill_score),
            "explanation_en": f.explanation_en, "top_drivers": f.top_drivers,
            "onset_status": f.onset_status, "current_regime": f.current_regime,
            "onset_date": str(f.onset_date_observed) if f.onset_date_observed else None,
            "is_synthetic": f.is_synthetic,
        } for f in fcs],
        "observations": [{"date": str(o.obs_date), "rain": o.rainfall_mm, "soil": o.soil_moisture,
                          "regime": o.regime} for o in obs],
        "season_timeseries": [{"date": str(r[0]), "prob_onset": _r(r[1]), "prob_dry_spell_7d": _r(r[2]),
                               "prob_heavy_rain": _r(r[3]), "rainfall_median": _r(r[4], 1),
                               "clim_dry_spell_7d": _r(r[5])} for r in ts],
        "onset_record": _onset_as_of(onset, d),
        "panchayats": [{"id": p.id, "name": p.name, "soil_type": p.soil_type,
                        "irrigated_fraction": p.irrigated_fraction, "advisories": adv_by.get(p.id, [])}
                       for p in panchs],
    }


def _onset_as_of(onset: OnsetRecord | None, d: date) -> dict | None:
    """Observed onset facts as they were known on date d (avoids look-ahead in replay)."""
    if onset is None or onset.onset_date is None or onset.onset_date + timedelta(days=3) > d:
        return None
    false_known = bool(onset.is_false_onset and onset.dry_spell_start
                       and onset.dry_spell_start + timedelta(days=7) <= d)
    true_known = onset.true_onset_date and onset.true_onset_date + timedelta(days=30) <= d
    return {"first_onset": str(onset.onset_date), "is_false_onset": false_known,
            "true_onset": str(onset.true_onset_date) if true_known else None}


def advisory_dict(a: Advisory, language: str | None = None) -> dict:
    out = {
        "id": a.id, "panchayat_id": a.panchayat_id, "issue_date": str(a.issue_date),
        "valid_until": str(a.valid_until) if a.valid_until else None, "crop": a.crop,
        "crop_stage": a.crop_stage, "sowing_date": str(a.sowing_date) if a.sowing_date else None,
        "action": a.action, "rule_id": a.rule_id, "priority": a.priority,
        "seedling_survival_prob": _r(a.seedling_survival_prob, 2), "soil_moisture": _r(a.soil_moisture, 2),
        "confidence_level": a.confidence_level, "reasoning": a.reasoning,
        "message_en": a.message_en, "message_te": a.message_te, "message_hi": a.message_hi,
        "sms_en": a.sms_en, "sms_te": a.sms_te, "sms_hi": a.sms_hi,
        "status": a.status, "approved_by": a.approved_by, "edited_message": a.edited_message,
        "officer_notes": a.officer_notes,
        "delivered": bool(a.delivered_sms or a.delivered_whatsapp),
        "is_synthetic": a.is_synthetic,
    }
    if language:
        msg = getattr(a, f"message_{language}", None) or a.message_en
        if a.edited_message and a.status == "approved":
            msg = a.edited_message
        out["message"] = msg
    return out


def panchayat_detail(s, panchayat_id: int, issue_date: date | None = None) -> dict | None:
    p = s.get(Panchayat, panchayat_id)
    d = issue_date or latest_issue_date(s)
    if p is None or d is None:
        return None
    b = s.get(Block, p.block_id)
    pfs = s.execute(select(PanchayatForecast).where(PanchayatForecast.panchayat_id == panchayat_id,
                                                    PanchayatForecast.issue_date == d)
                    .order_by(PanchayatForecast.horizon_days)).scalars().all()
    advs = s.execute(select(Advisory).where(Advisory.panchayat_id == panchayat_id, Advisory.issue_date == d)
                     .order_by(Advisory.priority, Advisory.crop)).scalars().all()
    bf = s.execute(select(Forecast).where(Forecast.block_id == p.block_id, Forecast.issue_date == d,
                                          Forecast.horizon_days == 7)).scalar_one_or_none()
    return {
        "id": p.id, "name": p.name, "block_id": p.block_id, "block_name": b.name if b else None,
        "issue_date": str(d), "soil_type": p.soil_type, "irrigated_fraction": p.irrigated_fraction,
        "onset_status": bf.onset_status if bf else None, "current_regime": bf.current_regime if bf else None,
        "confidence_level": bf.confidence_level if bf else None,
        "horizons": [{"horizon_days": f.horizon_days, "valid_end": str(f.valid_end), **_forecast_dict(f),
                      "soil_moisture": _r(f.soil_moisture)} for f in pfs],
        "advisories": [advisory_dict(a) for a in advs],
        "is_synthetic": True if p.is_synthetic else bool(bf.is_synthetic if bf else False),
    }


def replay_bundle(s, year: int = 2023) -> dict:
    blocks = s.execute(select(Block).order_by(Block.id)).scalars().all()
    bidx = {b.id: i for i, b in enumerate(blocks)}
    districts = {x.id: x.name for x in s.execute(select(District)).scalars()}
    start, end = date(year, 5, 1), date(year, 10, 31)
    dates = [r[0] for r in s.execute(select(Forecast.issue_date).distinct()
                                     .where(Forecast.issue_date >= start, Forecast.issue_date <= end)
                                     .order_by(Forecast.issue_date)).all()]
    if not dates:
        return {"year": year, "dates": []}
    didx = {d: i for i, d in enumerate(dates)}
    nb, nd = len(blocks), len(dates)
    fields = ["prob_onset", "prob_false_onset", "prob_dry_spell_7d", "prob_dry_spell_14d", "prob_heavy_rain",
              "rainfall_median", "rainfall_anomaly_pct"]
    fc = {str(h): {k: [[None] * nb for _ in range(nd)] for k in fields} for h in HORIZONS}
    status = [[None] * nb for _ in range(nd)]
    regime = [[None] * nb for _ in range(nd)]
    rows = s.execute(select(Forecast.issue_date, Forecast.block_id, Forecast.horizon_days, Forecast.onset_status,
                            Forecast.current_regime, *[getattr(Forecast, k) for k in fields])
                     .where(Forecast.issue_date >= start, Forecast.issue_date <= end)).all()
    for r in rows:
        i, j = didx[r[0]], bidx[r[1]]
        for k, v in zip(fields, r[5:]):
            fc[str(r[2])][k][i][j] = _r(v, 2) if k.startswith("prob") else _r(v, 1)
        if r[2] == 7:
            status[i][j] = ONSET_CODES.index(r[3]) if r[3] in ONSET_CODES else None
            regime[i][j] = r[4]

    obs = [[None] * nb for _ in range(nd)]
    for d, bid, rain in s.execute(select(DailyObservation.obs_date, DailyObservation.block_id, DailyObservation.rainfall_mm)
                                  .where(DailyObservation.obs_date >= dates[0], DailyObservation.obs_date <= dates[-1])).all():
        if d in didx:
            obs[didx[d]][bidx[bid]] = _r(rain, 1)

    # Majority action per block, crop and date
    panch_block = dict(s.execute(select(Panchayat.id, Panchayat.block_id)).all())
    votes: dict[tuple, Counter] = defaultdict(Counter)
    for d, pid, crop, action in s.execute(select(Advisory.issue_date, Advisory.panchayat_id, Advisory.crop, Advisory.action)
                                          .where(Advisory.issue_date >= start, Advisory.issue_date <= end)).all():
        votes[(d, panch_block[pid], crop)][action] += 1
    advice = {c: [[None] * nb for _ in range(nd)] for c in CROPS}
    for (d, bid, crop), cnt in votes.items():
        if crop in advice and d in didx:
            advice[crop][didx[d]][bidx[bid]] = ACTION_CODES.index(cnt.most_common(1)[0][0])

    drv_rows = s.execute(select(TeleconnectionIndex.obs_date, TeleconnectionIndex.index_name, TeleconnectionIndex.value,
                                TeleconnectionIndex.phase, TeleconnectionIndex.amplitude)
                         .where(TeleconnectionIndex.obs_date >= dates[0], TeleconnectionIndex.obs_date <= dates[-1])).all()
    drv = defaultdict(dict)
    for d, name, val, phase, amp in drv_rows:
        if name == "mjo":
            drv[str(d)].update({"mjo_phase": phase, "mjo_amp": _r(amp, 2)})
        elif name in ("oni", "dmi"):
            drv[str(d)][name] = _r(val, 2)

    return {
        "year": year,
        "dates": [str(d) for d in dates],
        "blocks": [{"id": b.id, "name": b.name, "district": districts.get(b.district_id)} for b in blocks],
        "fields": fields,
        "forecast": fc,
        "observed_rain": obs,
        "onset_status": status, "onset_codes": ONSET_CODES,
        "regime": regime,
        "advice": advice, "action_codes": ACTION_CODES,
        "drivers": [drv.get(str(d), {}) for d in dates],
        "events": season_events(s, year),
    }


def season_events(s, year: int) -> list[dict]:
    """Notable events: configured narrative + events detected from observations."""
    import yaml

    with open(ROOT / "config" / "pilot_region.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    events = []
    if cfg.get("replay", {}).get("year") == year:
        events += [{"date": e["date"], "type": e["type"], "label": e["description"], "source": "narrative"}
                   for e in cfg["replay"]["notable_events"]]
    onsets = s.execute(select(OnsetRecord).where(OnsetRecord.year == year)).scalars().all()
    if onsets:
        firsts = sorted(o.onset_date for o in onsets if o.onset_date)
        n_false = sum(1 for o in onsets if o.is_false_onset)
        if firsts:
            events.append({"date": str(firsts[len(firsts) // 2]), "type": "detected_onset",
                           "label": f"Median first onset-criterion rain across {len(firsts)} blocks; "
                                    f"{n_false} of them turned out to be false onsets", "source": "detected"})
        trues = sorted(o.true_onset_date for o in onsets if o.true_onset_date)
        if trues:
            events.append({"date": str(trues[len(trues) // 2]), "type": "detected_true_onset",
                           "label": "Median date of a lasting (true) onset", "source": "detected"})
    spells = s.execute(select(DrySpellRecord).where(DrySpellRecord.year == year, DrySpellRecord.length_days >= 10,
                                                    DrySpellRecord.season_phase != "pre_onset")).scalars().all()
    by_start = Counter((sp.start_date - timedelta(days=sp.start_date.toordinal() % 5)) for sp in spells)
    for d0, n in by_start.most_common(3):
        if n >= 5:
            events.append({"date": str(d0), "type": "detected_dry_spell",
                           "label": f"10+ day dry spell starting in {n} blocks", "source": "detected"})
    return sorted(events, key=lambda e: e["date"])
