"""
Varsha — Crop advisory expert system.

Deterministic, auditable rules (config/advisory_rules.yaml) turn panchayat
forecasts into one primary action per crop:

  SOW | WAIT | SWITCH | PROTECT | IRRIGATE | CONSERVE | PREPARE | ALERT | RESOW_ALERT | NORMAL

Inputs per (panchayat, crop, issue date):
  * panchayat forecast for 7/14/30-day windows (probabilities + rainfall quantiles)
  * observed onset status of the block (not_yet / provisional / established / false_onset)
  * soil moisture from the panchayat water balance
  * crop calendar state (sowing date -> FAO-56 growth stage)
  * P(seedling survival | sow today) from the analog ensemble + water balance
  * cost-loss ratio of the crop (sow only if P(failure) < C/L)

Every advisory stores the rule that fired and the numbers behind it
(`reasoning`), so extension officers can audit and override it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import yaml

from impact.water_balance import crop_params, crop_stage

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
LANGS = ("en", "te", "hi")


@lru_cache(maxsize=1)
def rules_config() -> dict:
    with open(CONFIG_DIR / "advisory_rules.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def crop_name(crop: str, lang: str) -> str:
    cp = crop_params()["crops"][crop]
    if lang == "en":
        return cp["display_name"].replace(" (Kharif)", "")
    return cp.get(f"display_name_{lang}", cp["display_name"])


def alternative_crop(crop: str, lang: str) -> str:
    cfg = rules_config()
    if lang == "en":
        return cfg["crop_alternatives"][crop][0]
    return cfg["crop_alternatives_i18n"][lang][crop][0]


def format_date(d: date, lang: str) -> str:
    return f"{d.day} {rules_config()['month_names'][lang][d.month - 1]}"


def cost_loss_ratio(crop: str) -> float:
    fw = rules_config()["decision_framework"]
    return float(fw["overrides"].get(crop, fw["default_cost_loss_ratio"]))


@dataclass
class AdvisoryContext:
    issue_date: date
    panchayat: dict
    crop: str
    forecast: dict                       # horizon -> {prob_*, rainfall_*}
    onset_status: str = "not_yet"
    onset_date: date | None = None
    current_regime: str = "pre_onset"
    soil_moisture: float = 0.3
    confidence: str = "low"
    sowing_date: date | None = None
    survival: float | None = None        # P(survival | sow today), None if not computed
    rain_14d_mm: float | None = None     # observed rain over the last 14 days (block)
    extras: dict = field(default_factory=dict)


def _pct(x) -> int:
    return int(round(100 * float(x)))


def decide(ctx: AdvisoryContext) -> dict:
    """Evaluate the rules in priority order. Returns action, rule_id, priority, params, reasoning."""
    R = rules_config()["rules"]
    cp = crop_params()["crops"][ctx.crop]
    win = cp["sowing_window"]
    f7, f14, f30 = ctx.forecast[7], ctx.forecast[14], ctx.forecast[30]
    doy = ctx.issue_date.timetuple().tm_yday
    days_since_sowing = (ctx.issue_date - ctx.sowing_date).days if ctx.sowing_date else -1
    stage = crop_stage(ctx.crop, days_since_sowing)
    cl = cost_loss_ratio(ctx.crop)
    survival_threshold = 1.0 - cl
    cond_false = min(1.0, f14["prob_false_onset"] / max(f14["prob_onset"], 0.05))

    reasoning = {
        "doy": doy,
        "crop_stage": stage,
        "onset_status": ctx.onset_status,
        "current_regime": ctx.current_regime,
        "soil_moisture": round(ctx.soil_moisture, 2),
        "prob_onset_7d": round(f7["prob_onset"], 2),
        "prob_false_onset_14d": round(f14["prob_false_onset"], 2),
        "false_onset_given_onset_14d": round(cond_false, 2),
        "prob_dry_spell_7d_7d": round(f7["prob_dry_spell_7d"], 2),
        "prob_dry_spell_7d_14d": round(f14["prob_dry_spell_7d"], 2),
        "prob_dry_spell_14d_14d": round(f14["prob_dry_spell_14d"], 2),
        "prob_heavy_rain_7d": round(f7["prob_heavy_rain"], 2),
        "prob_very_heavy_rain_7d": round(f7["prob_very_heavy_rain"], 2),
        "rain_median_7d": round(f7["rainfall_median"], 1),
        "rain_last_14d_mm": None if ctx.rain_14d_mm is None else round(ctx.rain_14d_mm, 1),
        "seedling_survival": None if ctx.survival is None else round(ctx.survival, 2),
        "survival_threshold": round(survival_threshold, 2),
        "cost_loss_ratio": cl,
        "sowing_window_doy": [win["earliest_doy"], win["latest_doy"]],
    }
    params = {
        "wait_days": R["sow_wait"]["wait_days"],
        "survival": _pct(ctx.survival or 0.0),
        "p_false": _pct(cond_false),
        "p_onset": _pct(f7["prob_onset"]),
        "p_dry": _pct(f7["prob_dry_spell_7d"]),
        "p_dry_2w": _pct(f14["prob_dry_spell_7d"]),
        "p_dry14": _pct(f14["prob_dry_spell_14d"]),
        "p_heavy": _pct(f7["prob_heavy_rain"]),
        "p_vheavy": _pct(f7["prob_very_heavy_rain"]),
        "rain_7d": int(round(f7["rainfall_median"])),
        "days_ahead": 7,
    }

    def out(rule_id: str, **extra):
        rule = R[rule_id]
        params.update(extra)
        return {"rule_id": rule_id, "action": rule["action"], "priority": rule["priority"],
                "crop_stage": stage, "params": params, "reasoning": reasoning}

    # 1. Very heavy rain overrides everything
    if f7["prob_very_heavy_rain"] >= R["very_heavy_alert"]["very_heavy_rain_probability_7d_min"]:
        return out("very_heavy_alert")

    if stage == "not_sown":
        # 2. Window closed, or onset hopelessly late
        if doy > win["latest_doy"] + R["switch_crop"]["days_after_latest_sowing"]:
            return out("switch_crop")
        if (doy >= R["switch_crop"]["late_onset_doy"] and ctx.onset_status in ("not_yet", "false_onset")
                and f14["prob_onset"] <= R["switch_crop"]["onset_probability_14d_max"]):
            return out("switch_crop")
        # 3. Too early
        if doy < win["earliest_doy"] - R["pre_season"]["days_before_earliest_sowing"]:
            start = date(ctx.issue_date.year, 1, 1) + timedelta(days=win["earliest_doy"] - 1)
            return out("pre_season", window_start=start)
        # 4. Sow / wait decision
        onset_signal = (ctx.onset_status in ("provisional", "established")
                        or f7["prob_onset"] >= R["sow_go"]["onset_probability_7d_min"])
        if onset_signal:
            ok_survival = ctx.survival is not None and ctx.survival >= survival_threshold
            ok_soil = ctx.soil_moisture >= R["sow_go"]["min_soil_moisture"]
            ok_false = cond_false <= R["sow_go"].get("false_onset_given_onset_max", 0.75)
            ok_rain = ctx.rain_14d_mm is None or ctx.rain_14d_mm >= R["sow_go"].get("min_rain_last_14d_mm", 0)
            reasoning["checks"] = {"survival_ok": ok_survival, "soil_ok": ok_soil, "false_onset_ok": ok_false,
                                   "enough_rain_ok": ok_rain}
            if ok_survival and ok_soil and ok_false and ok_rain:
                return out("sow_go")
            return out("sow_wait")
        return out("await_onset")

    if stage == "harvested":
        return out("normal")
    # 5. Standing crop
    if stage in R["resow_alert"]["stages"] and f14["prob_dry_spell_14d"] >= R["resow_alert"]["dry_spell_probability_14d_min"]:
        return out("resow_alert")
    if stage in R["protect"]["stages"] and f7["prob_dry_spell_7d"] >= R["protect"]["dry_spell_probability_7d_min"]:
        return out("protect")
    if (stage in R["irrigate"]["stages"] and ctx.soil_moisture <= R["irrigate"]["max_soil_moisture"]
            and f7["prob_dry_spell_7d"] >= R["irrigate"]["dry_spell_probability_7d_min"]):
        return out("irrigate")
    if f7["prob_heavy_rain"] >= R["heavy_prepare"]["heavy_rain_probability_7d_min"]:
        return out("heavy_prepare")
    bc = R["break_conserve"]
    dry_anom = f14["prob_dry_spell_7d"] - f14.get("clim_prob_dry_spell_7d", 0.0)
    reasoning["dry_spell_14d_window_vs_climatology"] = round(dry_anom, 2)
    if (ctx.current_regime == "active" and f14["prob_dry_spell_7d"] >= bc["dry_spell_probability_14d_min"]
            and dry_anom >= bc.get("anomaly_vs_climatology_min", 0.0)):
        days_ahead = 7 if f7["prob_dry_spell_7d"] >= 0.5 else 14
        return out("break_conserve", days_ahead=days_ahead)
    return out("normal")


def render(decision: dict, ctx: AdvisoryContext, lang: str) -> tuple[str, str]:
    """Localised full message and SMS text."""
    cfg = rules_config()
    p = dict(decision["params"])
    p["crop"] = crop_name(ctx.crop, lang)
    p["alternative_crop"] = alternative_crop(ctx.crop, lang)
    if isinstance(p.get("window_start"), date):
        p["window_start"] = format_date(p["window_start"], lang)
    p["confidence"] = cfg["confidence_words"].get(ctx.confidence, cfg["confidence_words"]["low"])[lang]
    p["panchayat"] = ctx.panchayat.get("name", "")
    p["action_word"] = cfg["action_words"][decision["action"]][lang]
    body = cfg["messages"][decision["rule_id"]][lang].format(**p)
    outlook = cfg["outlook"][lang].format(**p)
    sms = cfg["sms"][lang].format(**p)
    return f"{body} {outlook}", sms


def advise(ctx: AdvisoryContext) -> dict:
    """Full advisory record (all languages) for one panchayat and crop."""
    d = decide(ctx)
    rec = {
        "panchayat_id": ctx.panchayat["id"],
        "issue_date": ctx.issue_date,
        "valid_until": ctx.issue_date + timedelta(days=6),
        "crop": ctx.crop,
        "crop_stage": d["crop_stage"],
        "sowing_date": ctx.sowing_date,
        "action": d["action"],
        "rule_id": d["rule_id"],
        "priority": d["priority"],
        "reasoning": d["reasoning"],
        "seedling_survival_prob": None if ctx.survival is None else round(float(ctx.survival), 3),
        "soil_moisture": round(float(ctx.soil_moisture), 3),
        "confidence_level": ctx.confidence,
        "action_detail": cfg_action_word(d["action"]),
    }
    for lang in LANGS:
        msg, sms = render(d, ctx, lang)
        rec[f"message_{lang}"] = msg
        rec[f"sms_{lang}"] = sms
    return rec


def cfg_action_word(action: str) -> str:
    return rules_config()["action_words"][action]["en"]


def needs_survival(crop: str, issue_date: date, sowing_date: date | None) -> bool:
    """Survival is only needed for unsown crops inside the sowing window."""
    if sowing_date is not None:
        return False
    win = crop_params()["crops"][crop]["sowing_window"]
    doy = issue_date.timetuple().tm_yday
    return win["earliest_doy"] - 3 <= doy <= win["latest_doy"]
