"""
Varsha — Forecast engine (inference).

Given an issue date, produce for every block and horizon (7/14/21/30 days):
probabilities of onset, false onset, 7/14-day dry spells, heavy and very heavy
rain; rainfall quantiles; climatological reference; regime state and outlook;
observed onset status; TreeSHAP driver attributions with a plain-language
explanation; and a confidence level from hindcast skill.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd

from data.sources import driver_snapshot, load_blocks, load_climate
from models import events as ev
from models.features import HORIZONS, SeasonState, rows_for_day
from models.hmm.regime import RegimeHMM
from models.onset.status import onset_status
from models.train import load_bundle
from models.verification.skill import confidence_label
from models.weather_generator import AnalogLibrary

logger = logging.getLogger(__name__)

EVENT_LABELS = {
    "onset": "monsoon onset",
    "false_onset": "false onset",
    "dry_spell_7d": "a dry spell of 7+ days",
    "dry_spell_14d": "a dry spell of 14+ days",
    "heavy_rain": "heavy rain (65+ mm/day)",
    "very_heavy_rain": "very heavy rain (115+ mm/day)",
}
EXPLAIN_EVENTS = ("onset", "false_onset", "dry_spell_7d", "heavy_rain")


class ModelNotTrained(RuntimeError):
    pass


class ForecastEngine:
    def __init__(self, bundle: dict | None = None, cd=None):
        self.bundle = bundle or load_bundle()
        if self.bundle is None:
            raise ModelNotTrained("No trained model found. Run: python -m models.train")
        self.model = self.bundle["model"]
        self.clim = self.bundle["climatology"]
        self.hmm = RegimeHMM.from_dict(self.bundle["hmm"])
        self.cd = cd or load_climate()
        self.blocks = load_blocks()
        self.block_index = {b["id"]: i for i, b in enumerate(self.blocks)}
        self.version = self.bundle["model_version"]
        self.skill = self.bundle["skill"]
        self._seasons: dict[int, SeasonState] = {}
        self._analogs: AnalogLibrary | None = None

    # ── cached helpers ──
    def season(self, year: int) -> SeasonState:
        if year not in self._seasons:
            self._seasons[year] = SeasonState(self.cd, year, self.blocks, hmm=self.hmm)
        return self._seasons[year]

    @property
    def analogs(self) -> AnalogLibrary:
        if self._analogs is None:
            self._analogs = AnalogLibrary(self.cd, self.bundle["train_years"], [b["id"] for b in self.blocks])
        return self._analogs

    def day_index(self, d: date) -> int | None:
        if d.year not in set(self.cd.dates.year):
            return None
        st = self.season(d.year)
        loc = st.dates.get_indexer([pd.Timestamp(d)])[0]
        return None if loc < 31 else int(loc)

    def has_data(self, d: date) -> bool:
        return self.day_index(d) is not None

    def headline_bss(self, event: str, h: int) -> float:
        try:
            return float(self.skill["hindcast"]["by_event"][event][h]["bss"])
        except (KeyError, TypeError):
            return float("nan")

    # ── main entry ──
    def forecast(self, d: date) -> pd.DataFrame:
        t = self.day_index(d)
        if t is None:
            raise ValueError(f"No observations available to issue a forecast on {d}")
        st = self.season(d.year)
        rows = pd.DataFrame(rows_for_day(st, t, self.blocks, self.clim, HORIZONS, with_labels=False))
        pred = self.model.predict(rows)
        out = pd.concat([rows.reset_index(drop=True), pred.reset_index(drop=True)], axis=1)

        expl = {e: self.model.explain(rows, e) for e in EXPLAIN_EVENTS}
        drivers = driver_snapshot(self.cd.drivers, d)

        # Block state (observations up to t-1)
        state = {}
        for b in self.blocks:
            bi = self.block_index[b["id"]]
            os_ = onset_status(st.rain[:, bi], st.doys, t)
            onset_date = st.dates[os_["onset_idx"]].date() if os_["onset_idx"] is not None else None
            p_brk = float(st.p_break[t, bi])
            if os_["status"] in ("not_yet",):
                regime = "pre_onset"
            else:
                regime = "break" if p_brk >= 0.5 else "active"
            state[b["id"]] = {"onset_status": os_["status"], "onset_date": onset_date,
                              "current_regime": regime, "p_break": p_brk,
                              "soil_moisture": float(st.soil[t, bi]),
                              "rain_7d_obs": float(st.rain_7d[t, bi]),
                              "rain_14d_obs": float(st.rain_14d[t, bi])}

        records = []
        for i, r in out.iterrows():
            b = int(r["block_id"])
            h = int(r["horizon"])
            s = state[b]
            headline = "onset" if s["onset_status"] in ("not_yet", "false_onset") else "dry_spell_7d"
            bss = self.headline_bss(headline, h)
            p_brk = float(r["prob_dry_spell_7d"])
            if s["current_regime"] == "pre_onset":
                pred_regime, reg_p = "pre_onset", 1.0 - float(r["prob_onset"])
            elif p_brk >= 0.6:
                pred_regime, reg_p = "break", p_brk
            elif p_brk <= 0.3:
                pred_regime, reg_p = "active", 1 - p_brk
            else:
                pred_regime, reg_p = "transition", max(p_brk, 1 - p_brk)
            top = {e: expl[e][i] for e in EXPLAIN_EVENTS}
            clim_med = float(r["clim_total_med"])
            records.append({
                "block_id": b,
                "issue_date": d,
                "horizon_days": h,
                "valid_start": d,
                "valid_end": d + timedelta(days=h - 1),
                **{f"prob_{k}": round(float(r[f"prob_{k}"]), 4) for k in ev.EVENT_KEYS},
                "rainfall_q10": round(float(r["rainfall_q10"]), 1),
                "rainfall_q25": round(float(r["rainfall_q25"]), 1),
                "rainfall_median": round(float(r["rainfall_median"]), 1),
                "rainfall_q75": round(float(r["rainfall_q75"]), 1),
                "rainfall_q90": round(float(r["rainfall_q90"]), 1),
                "rainfall_anomaly_pct": round(100 * (float(r["rainfall_median"]) - clim_med) / max(clim_med, 5.0), 1),
                "clim_prob_onset": round(float(r["clim_onset"]), 4),
                "clim_prob_dry_spell_7d": round(float(r["clim_dry_spell_7d"]), 4),
                "clim_prob_heavy_rain": round(float(r["clim_heavy_rain"]), 4),
                "clim_total_med": round(clim_med, 1),
                "current_regime": s["current_regime"],
                "predicted_regime": pred_regime,
                "regime_probability": round(float(reg_p), 3),
                "onset_status": s["onset_status"],
                "onset_date_observed": s["onset_date"],
                "soil_moisture": round(s["soil_moisture"], 3),
                "rain_7d_obs": round(s["rain_7d_obs"], 1),
                "rain_14d_obs": round(s["rain_14d_obs"], 1),
                "top_drivers": top,
                "explanation_en": explain_text(r, headline, h, top[headline] if headline in top else [], drivers),
                "brier_skill_score": None if not np.isfinite(bss) else round(bss, 3),
                "confidence_level": confidence_label(bss),
                "model_version": self.version,
                "is_synthetic": bool(self.cd.is_synthetic),
            })
        return pd.DataFrame(records)

    def seedling_survival(self, block_id: int, d: date, fc_row_14: dict, fc_row_30: dict,
                          crop: str, fc: float, wp: float, soil_rel: float) -> float:
        """P(seedlings survive establishment | sown on d) from the analog ensemble + water balance."""
        from impact.water_balance import hargreaves_eto, seedling_survival

        doy = d.timetuple().tm_yday
        probs14 = {k: fc_row_14[f"prob_{k}"] for k in ("dry_spell_7d", "heavy_rain", "onset")}
        q30 = {k: fc_row_30[k] for k in ("rainfall_q10", "rainfall_q25", "rainfall_median", "rainfall_q75", "rainfall_q90")}
        seq, w = self.analogs.ensemble(block_id, doy, probs14, q30)
        b = self.blocks[self.block_index[block_id]]
        eto = float(hargreaves_eto(31.0, 23.5, doy, b["lat"]))
        alive = seedling_survival(seq, eto, soil_rel, crop, fc, wp)
        return float(np.sum(w * alive))


def _driver_phrase(group: str, drivers: dict) -> str:
    if group.startswith("MJO"):
        return f"{group}: phase {drivers['mjo_phase']}, amplitude {drivers['mjo_amplitude']:.1f}"
    if group.startswith("ENSO"):
        return f"ENSO: ONI {drivers['oni']:+.1f} ({drivers['enso_phase']})"
    if group == "Indian Ocean Dipole":
        return f"IOD: DMI {drivers['dmi']:+.1f} ({drivers['iod_phase']})"
    return group


def explain_text(r, event: str, h: int, top: list[dict], drivers: dict) -> str:
    p = 100 * float(r[f"prob_{event}"])
    clim = 100 * float(r.get(f"clim_{event}", np.nan))
    label = EVENT_LABELS.get(event, event)
    head = f"Chance of {label} in the next {h} days: {int(p + 0.5)}%"   # round half up, like the UI
    if np.isfinite(clim):
        rel = "above" if p > clim + 5 else ("below" if p < clim - 5 else "close to")
        head += f" ({rel} the usual {int(clim + 0.5)}% for this time of year)."
    else:
        head += "."
    ups = [_driver_phrase(t["group"], drivers) for t in top if t["contribution"] > 0.05][:2]
    downs = [_driver_phrase(t["group"], drivers) for t in top if t["contribution"] < -0.05][:2]
    parts = [head]
    if ups:
        parts.append("Raised by: " + "; ".join(ups) + ".")
    if downs:
        parts.append("Lowered by: " + "; ".join(downs) + ".")
    return " ".join(parts)
