"""Tests for the crop advisory expert system."""

from datetime import date

from impact.advisory_engine import AdvisoryContext, advise, decide, needs_survival

PANCH = {"id": 1, "name": "Test GP", "block_id": 1, "field_capacity": 0.3, "wilting_point": 0.15,
         "irrigated_fraction": 0.2}


def fc(**over):
    base = {"prob_onset": 0.3, "prob_false_onset": 0.1, "prob_dry_spell_7d": 0.3, "prob_dry_spell_14d": 0.1,
            "prob_heavy_rain": 0.05, "prob_very_heavy_rain": 0.01, "rainfall_q10": 5, "rainfall_q25": 10,
            "rainfall_median": 20, "rainfall_q75": 35, "rainfall_q90": 50, "clim_prob_dry_spell_7d": 0.3}
    base.update(over)
    return {h: dict(base) for h in (7, 14, 21, 30)}


def ctx(**over):
    args = dict(issue_date=date(2023, 6, 20), panchayat=PANCH, crop="cotton", forecast=fc(),
                onset_status="provisional", current_regime="active", soil_moisture=0.4,
                confidence="moderate", sowing_date=None, survival=0.8)
    args.update(over)
    return AdvisoryContext(**args)


def test_very_heavy_rain_overrides_everything():
    d = decide(ctx(forecast=fc(prob_very_heavy_rain=0.4, prob_heavy_rain=0.6)))
    assert d["action"] == "ALERT"


def test_sow_when_onset_and_survival_high():
    assert decide(ctx())["action"] == "SOW"


def test_wait_until_50mm_of_rain_has_fallen():
    assert decide(ctx(rain_14d_mm=30))["rule_id"] == "sow_wait"
    assert decide(ctx(rain_14d_mm=60))["action"] == "SOW"


def test_wait_when_survival_below_cost_loss_threshold():
    d = decide(ctx(survival=0.5))
    assert d["action"] == "WAIT" and d["rule_id"] == "sow_wait"


def test_await_onset_before_any_onset_signal():
    d = decide(ctx(onset_status="not_yet", forecast=fc(prob_onset=0.3)))
    assert d["rule_id"] == "await_onset"


def test_pre_season_and_switch():
    assert decide(ctx(issue_date=date(2023, 5, 20)))["rule_id"] == "pre_season"
    assert decide(ctx(issue_date=date(2023, 7, 25), onset_status="false_onset"))["action"] == "SWITCH"


def test_standing_crop_rules():
    sown = date(2023, 6, 10)
    assert decide(ctx(sowing_date=sown, forecast=fc(prob_dry_spell_7d=0.7)))["action"] == "PROTECT"
    assert decide(ctx(sowing_date=sown, forecast=fc(prob_dry_spell_7d=0.7, prob_dry_spell_14d=0.6)))["action"] == "RESOW_ALERT"
    assert decide(ctx(sowing_date=sown, forecast=fc(prob_heavy_rain=0.6)))["action"] == "PREPARE"
    assert decide(ctx(sowing_date=sown))["action"] == "NORMAL"


def test_break_conserve_needs_anomaly_vs_climatology():
    sown = date(2023, 6, 1)
    day = date(2023, 7, 25)  # development stage
    usual = fc(prob_dry_spell_7d=0.62, clim_prob_dry_spell_7d=0.58)
    usual[7]["prob_dry_spell_7d"] = 0.45
    assert decide(ctx(issue_date=day, sowing_date=sown, forecast=usual))["action"] == "NORMAL"
    unusual = fc(prob_dry_spell_7d=0.62, clim_prob_dry_spell_7d=0.40)
    unusual[7]["prob_dry_spell_7d"] = 0.45
    assert decide(ctx(issue_date=day, sowing_date=sown, forecast=unusual))["action"] == "CONSERVE"


def test_messages_rendered_in_three_languages():
    rec = advise(ctx())
    for lang in ("en", "te", "hi"):
        assert rec[f"message_{lang}"] and "{" not in rec[f"message_{lang}"]
        assert rec[f"sms_{lang}"] and "{" not in rec[f"sms_{lang}"]
    assert "పత్తి" in rec["message_te"]
    assert "कपास" in rec["message_hi"]
    assert rec["reasoning"]["survival_threshold"] == 0.7


def test_needs_survival_only_in_window_and_unsown():
    assert needs_survival("cotton", date(2023, 6, 20), None)
    assert not needs_survival("cotton", date(2023, 6, 20), date(2023, 6, 15))
    assert not needs_survival("cotton", date(2023, 8, 20), None)
