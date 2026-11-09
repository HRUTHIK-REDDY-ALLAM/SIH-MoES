"""
Varsha — Database Models (SQLAlchemy 2.0)

All spatial data uses EPSG:4326 (WGS84). Geometry columns are PostGIS geometry
on PostgreSQL and GeoJSON text on SQLite (see backend/db/types.py).
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, JSON,
    String, Text, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship

from backend.db.types import GeoJSONGeometry


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    """Naive UTC timestamp (portable across SQLite and PostgreSQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ─── Administrative Boundaries ───────────────────────────────────────────────

class District(Base):
    """District boundary with LGD code."""
    __tablename__ = "districts"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    state = Column(String(100), nullable=False, default="Telangana")
    lgd_code = Column(Integer, unique=True, nullable=False)
    geometry = Column(GeoJSONGeometry("MULTIPOLYGON"))
    is_synthetic = Column(Boolean, default=True)

    blocks = relationship("Block", back_populates="district", lazy="selectin")


class Block(Base):
    """Block (mandal) boundary — primary forecast unit."""
    __tablename__ = "blocks"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    district_id = Column(Integer, ForeignKey("districts.id"), nullable=False)
    lgd_code = Column(Integer, unique=True, nullable=True)
    centroid_lat = Column(Float)
    centroid_lon = Column(Float)
    elevation_m = Column(Float)  # Mean elevation from DEM
    geometry = Column(GeoJSONGeometry("MULTIPOLYGON"))
    is_synthetic = Column(Boolean, default=True)

    # Forecast skill for this block (updated after hindcast verification)
    bss_onset = Column(Float)          # Brier Skill Score for onset
    bss_dry_spell = Column(Float)      # BSS for dry spell
    bss_heavy_rain = Column(Float)     # BSS for heavy rain
    trust_score = Column(Float)        # Composite trust score 0-1

    district = relationship("District", back_populates="blocks")
    panchayats = relationship("Panchayat", back_populates="block", lazy="selectin")
    observations = relationship("DailyObservation", back_populates="block")
    forecasts = relationship("Forecast", back_populates="block")


class Panchayat(Base):
    """Panchayat (gram panchayat) — finest advisory unit."""
    __tablename__ = "panchayats"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    block_id = Column(Integer, ForeignKey("blocks.id"), nullable=False)
    lgd_code = Column(Integer, unique=True, nullable=True)
    centroid_lat = Column(Float)
    centroid_lon = Column(Float)
    geometry = Column(GeoJSONGeometry("MULTIPOLYGON"), nullable=True)
    is_synthetic = Column(Boolean, default=True)

    # Soil hydraulic properties drive the panchayat-level water balance
    soil_type = Column(String(40))           # red_sandy_loam, black_cotton, red_loam
    field_capacity = Column(Float)           # m3/m3
    wilting_point = Column(Float)            # m3/m3
    irrigated_fraction = Column(Float)       # share of area with protective irrigation

    block = relationship("Block", back_populates="panchayats")
    advisories = relationship("Advisory", back_populates="panchayat")


# ─── Observations ────────────────────────────────────────────────────────────

class DailyObservation(Base):
    """Daily gridded observation mapped to block level."""
    __tablename__ = "daily_observations"
    __table_args__ = (
        UniqueConstraint("block_id", "obs_date", name="uq_block_date"),
        Index("ix_obs_date", "obs_date"),
    )

    id = Column(Integer, primary_key=True)
    block_id = Column(Integer, ForeignKey("blocks.id"), nullable=False)
    obs_date = Column(Date, nullable=False)

    rainfall_mm = Column(Float)
    rainfall_source = Column(String(20))  # 'chirps', 'imd', 'synthetic'
    tmax_c = Column(Float)
    tmin_c = Column(Float)
    eto_mm = Column(Float)          # Reference ET (Hargreaves)
    soil_moisture = Column(Float)   # Relative root-zone water (0-1), from water balance

    is_rainy_day = Column(Boolean)
    is_heavy_rain = Column(Boolean)
    is_very_heavy_rain = Column(Boolean)
    regime = Column(String(20))     # HMM-decoded 'active' / 'break' / 'pre_onset'

    block = relationship("Block", back_populates="observations")


class OnsetRecord(Base):
    """Detected monsoon onset per block per year."""
    __tablename__ = "onset_records"
    __table_args__ = (UniqueConstraint("block_id", "year", name="uq_block_year_onset"),)

    id = Column(Integer, primary_key=True)
    block_id = Column(Integer, ForeignKey("blocks.id"), nullable=False)
    year = Column(Integer, nullable=False)
    onset_date = Column(Date, nullable=True)
    onset_doy = Column(Integer, nullable=True)
    is_false_onset = Column(Boolean, default=False)
    dry_spell_start = Column(Date, nullable=True)
    dry_spell_length_days = Column(Integer, nullable=True)
    true_onset_date = Column(Date, nullable=True)   # first onset NOT followed by a false-onset dry spell


class DrySpellRecord(Base):
    """Detected dry spell events."""
    __tablename__ = "dry_spell_records"

    id = Column(Integer, primary_key=True)
    block_id = Column(Integer, ForeignKey("blocks.id"), nullable=False)
    year = Column(Integer, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    length_days = Column(Integer, nullable=False)
    season_phase = Column(String(20))  # 'pre_onset', 'early', 'mid', 'late'


# ─── Forecasts ───────────────────────────────────────────────────────────────

class _ForecastColumns:
    """Probability columns shared by block and panchayat forecasts."""
    issue_date = Column(Date, nullable=False)
    horizon_days = Column(Integer, nullable=False)  # 7, 14, 21, 30
    valid_start = Column(Date, nullable=False)
    valid_end = Column(Date, nullable=False)

    prob_onset = Column(Float)              # P(onset criterion met in window)
    prob_false_onset = Column(Float)        # P(onset in window followed by 7+ day dry spell)
    prob_dry_spell_7d = Column(Float)       # P(dry spell >= 7 days begins in window)
    prob_dry_spell_14d = Column(Float)      # P(dry spell >= 14 days begins in window)
    prob_heavy_rain = Column(Float)         # P(rain >= 64.5 mm on any day)
    prob_very_heavy_rain = Column(Float)    # P(rain >= 115.6 mm on any day)

    rainfall_q10 = Column(Float)
    rainfall_q25 = Column(Float)
    rainfall_median = Column(Float)
    rainfall_q75 = Column(Float)
    rainfall_q90 = Column(Float)
    rainfall_anomaly_pct = Column(Float)    # median vs climatological median (%)


class Forecast(_ForecastColumns, Base):
    """Probabilistic forecast for a block on a given issue date."""
    __tablename__ = "forecasts"
    __table_args__ = (
        UniqueConstraint("block_id", "issue_date", "horizon_days", name="uq_block_issue_horizon"),
        Index("ix_forecast_issue", "issue_date"),
    )

    id = Column(Integer, primary_key=True)
    block_id = Column(Integer, ForeignKey("blocks.id"), nullable=False)

    # Climatological reference for the same window (for anomaly display)
    clim_prob_onset = Column(Float)
    clim_prob_dry_spell_7d = Column(Float)
    clim_prob_heavy_rain = Column(Float)

    # Regime (HMM current state + ML break probability)
    current_regime = Column(String(20))     # 'pre_onset', 'active', 'break'
    predicted_regime = Column(String(20))   # 'active', 'break', 'transition'
    regime_probability = Column(Float)
    onset_status = Column(String(20))       # 'not_yet', 'occurred', 'false_onset_risk'
    onset_date_observed = Column(Date)

    model_version = Column(String(50))
    is_synthetic = Column(Boolean, default=False)

    explanation_en = Column(Text)
    top_drivers = Column(JSON)  # [{"feature": ..., "label": ..., "contribution": ...}, ...]

    brier_skill_score = Column(Float)
    confidence_level = Column(String(20))   # 'high', 'moderate', 'low'

    block = relationship("Block", back_populates="forecasts")


class PanchayatForecast(_ForecastColumns, Base):
    """Block forecast interpolated to a panchayat centroid (IDW over neighbouring blocks)."""
    __tablename__ = "panchayat_forecasts"
    __table_args__ = (
        UniqueConstraint("panchayat_id", "issue_date", "horizon_days", name="uq_panch_issue_horizon"),
        Index("ix_panch_forecast_issue", "issue_date"),
    )

    id = Column(Integer, primary_key=True)
    panchayat_id = Column(Integer, ForeignKey("panchayats.id"), nullable=False)
    block_id = Column(Integer, ForeignKey("blocks.id"), nullable=False)
    soil_moisture = Column(Float)           # relative root-zone water at issue (0-1)
    is_synthetic = Column(Boolean, default=False)


# ─── Advisories ──────────────────────────────────────────────────────────────

class Advisory(Base):
    """Crop-specific advisory for a panchayat."""
    __tablename__ = "advisories"
    __table_args__ = (
        Index("ix_advisory_date", "issue_date"),
        UniqueConstraint("panchayat_id", "issue_date", "crop", name="uq_advisory_panch_date_crop"),
    )

    id = Column(Integer, primary_key=True)
    panchayat_id = Column(Integer, ForeignKey("panchayats.id"), nullable=False)
    forecast_id = Column(Integer, ForeignKey("forecasts.id"), nullable=True)
    issue_date = Column(Date, nullable=False)
    valid_until = Column(Date)
    crop = Column(String(50), nullable=False)
    crop_stage = Column(String(20))          # not_sown, initial, development, mid_season, late_season
    sowing_date = Column(Date)               # assumed/recorded sowing date

    action = Column(String(20), nullable=False)  # SOW, WAIT, SWITCH, PROTECT, IRRIGATE, CONSERVE, PREPARE, ALERT, RESOW_ALERT, NORMAL
    rule_id = Column(String(60))             # which expert-system rule fired
    priority = Column(Integer, default=5)    # 1 = most urgent
    action_detail = Column(Text)
    reasoning = Column(JSON)                 # inputs and thresholds behind the decision

    seedling_survival_prob = Column(Float)
    soil_moisture = Column(Float)
    confidence_level = Column(String(20))

    message_en = Column(Text, nullable=False)
    message_te = Column(Text)
    message_hi = Column(Text)
    sms_en = Column(Text)                    # short SMS form
    sms_te = Column(Text)
    sms_hi = Column(Text)

    status = Column(String(20), default="pending")  # pending, approved, rejected
    approved_by = Column(String(100))
    approved_at = Column(DateTime)
    officer_notes = Column(Text)
    edited_message = Column(Text)

    delivered_whatsapp = Column(Boolean, default=False)
    delivered_sms = Column(Boolean, default=False)
    delivered_at = Column(DateTime)
    is_synthetic = Column(Boolean, default=False)

    panchayat = relationship("Panchayat", back_populates="advisories")


# ─── Messaging ───────────────────────────────────────────────────────────────

class Subscriber(Base):
    """A farmer or extension officer registered for advisories."""
    __tablename__ = "subscribers"
    __table_args__ = (UniqueConstraint("phone", name="uq_subscriber_phone"),)

    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    phone = Column(String(20), nullable=False)     # E.164, needed for delivery
    phone_hash = Column(String(64), nullable=False)
    role = Column(String(20), default="farmer")    # farmer, extension_officer
    panchayat_id = Column(Integer, ForeignKey("panchayats.id"), nullable=True)
    block_id = Column(Integer, ForeignKey("blocks.id"), nullable=True)
    crops = Column(JSON)                           # ["cotton", "paddy"]
    language = Column(String(5), default="te")
    channel = Column(String(20), default="sms")    # sms, whatsapp
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    is_synthetic = Column(Boolean, default=False)


class MessageLog(Base):
    """Every outbound and inbound message (outbox for the phone preview)."""
    __tablename__ = "message_log"
    __table_args__ = (Index("ix_message_created", "created_at"),)

    id = Column(Integer, primary_key=True)
    direction = Column(String(10), default="out")  # out, in
    subscriber_id = Column(Integer, ForeignKey("subscribers.id"), nullable=True)
    advisory_id = Column(Integer, ForeignKey("advisories.id"), nullable=True)
    phone = Column(String(20))
    channel = Column(String(20))
    language = Column(String(5))
    body = Column(Text)
    status = Column(String(30))                    # delivered_mock, sent, failed, received
    provider_response = Column(JSON)
    created_at = Column(DateTime, default=utcnow)


# ─── Farmer Feedback ─────────────────────────────────────────────────────────

class FarmerFeedback(Base):
    """Farmer-reported ground truth for verification."""
    __tablename__ = "farmer_feedback"

    id = Column(Integer, primary_key=True)
    panchayat_id = Column(Integer, ForeignKey("panchayats.id"), nullable=False)
    report_date = Column(Date, nullable=False)
    reported_at = Column(DateTime, default=utcnow)

    rain_today = Column(Boolean)
    rain_intensity = Column(String(20))   # 'none', 'light', 'moderate', 'heavy'
    crop = Column(String(50))
    crop_condition = Column(String(20))   # 'good', 'stressed', 'damaged', 'failed'
    farmer_phone_hash = Column(String(64))
    language = Column(String(5), default="te")
    source = Column(String(20), default="web")  # web, sms, whatsapp


# ─── Teleconnection Indices ──────────────────────────────────────────────────

class TeleconnectionIndex(Base):
    """Daily teleconnection indices for model drivers."""
    __tablename__ = "teleconnection_indices"
    __table_args__ = (UniqueConstraint("index_name", "obs_date", name="uq_index_date"),)

    id = Column(Integer, primary_key=True)
    index_name = Column(String(20), nullable=False)  # 'oni', 'dmi', 'rmm1', 'rmm2', 'mjo_amp', 'u850', 'olr'
    obs_date = Column(Date, nullable=False)
    value = Column(Float, nullable=False)
    phase = Column(Integer)
    amplitude = Column(Float)
    source = Column(String(40))


# ─── Pipeline bookkeeping ────────────────────────────────────────────────────

class PipelineRun(Base):
    """One execution of the daily pipeline."""
    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True)
    run_date = Column(Date, nullable=False)
    started_at = Column(DateTime, default=utcnow)
    finished_at = Column(DateTime)
    status = Column(String(20), default="running")  # running, success, failed, skipped
    model_version = Column(String(50))
    n_forecasts = Column(Integer, default=0)
    n_advisories = Column(Integer, default=0)
    data_sources = Column(JSON)
    message = Column(Text)
