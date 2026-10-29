"""
Varsha — Database Models (SQLAlchemy + GeoAlchemy2)

All spatial data uses EPSG:4326 (WGS84).
PostGIS geometry columns store block/panchayat boundaries.
"""

from datetime import date, datetime
from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean, Column, Date, DateTime, Enum, Float, ForeignKey,
    Integer, JSON, String, Text, UniqueConstraint, Index,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ─── Administrative Boundaries ───────────────────────────────────────────────

class District(Base):
    """District boundary with LGD code."""
    __tablename__ = "districts"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    state = Column(String(100), nullable=False, default="Telangana")
    lgd_code = Column(Integer, unique=True, nullable=False)
    geometry = Column(Geometry("MULTIPOLYGON", srid=4326))

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
    geometry = Column(Geometry("MULTIPOLYGON", srid=4326))

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
    geometry = Column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)

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

    # Rainfall (mm)
    rainfall_mm = Column(Float)
    rainfall_source = Column(String(20))  # 'chirps', 'imd', 'imerg'

    # Temperature (°C)
    tmax_c = Column(Float)
    tmin_c = Column(Float)

    # Derived
    eto_mm = Column(Float)          # Reference ET (Hargreaves)
    soil_moisture = Column(Float)   # Volumetric, from SMAP or model

    # Event flags (computed by event labeller)
    is_rainy_day = Column(Boolean)
    is_heavy_rain = Column(Boolean)
    is_very_heavy_rain = Column(Boolean)

    block = relationship("Block", back_populates="observations")


class OnsetRecord(Base):
    """Detected monsoon onset per block per year."""
    __tablename__ = "onset_records"
    __table_args__ = (
        UniqueConstraint("block_id", "year", name="uq_block_year_onset"),
    )

    id = Column(Integer, primary_key=True)
    block_id = Column(Integer, ForeignKey("blocks.id"), nullable=False)
    year = Column(Integer, nullable=False)
    onset_date = Column(Date, nullable=True)      # NULL if no onset detected
    onset_doy = Column(Integer, nullable=True)
    is_false_onset = Column(Boolean, default=False)
    dry_spell_start = Column(Date, nullable=True)  # If false onset
    dry_spell_length_days = Column(Integer, nullable=True)


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

class Forecast(Base):
    """Probabilistic forecast for a block on a given issue date."""
    __tablename__ = "forecasts"
    __table_args__ = (
        UniqueConstraint("block_id", "issue_date", "horizon_days", name="uq_block_issue_horizon"),
        Index("ix_forecast_issue", "issue_date"),
    )

    id = Column(Integer, primary_key=True)
    block_id = Column(Integer, ForeignKey("blocks.id"), nullable=False)
    issue_date = Column(Date, nullable=False)
    horizon_days = Column(Integer, nullable=False)  # 7, 14, 21, 30
    valid_start = Column(Date, nullable=False)
    valid_end = Column(Date, nullable=False)

    # Probabilistic outputs
    prob_onset = Column(Float)              # P(onset in window)
    prob_false_onset = Column(Float)        # P(false onset | onset signal)
    prob_dry_spell_7d = Column(Float)       # P(dry spell >= 7 days)
    prob_dry_spell_14d = Column(Float)      # P(dry spell >= 14 days)
    prob_heavy_rain = Column(Float)         # P(rain >= 64.5 mm on any day)
    prob_very_heavy_rain = Column(Float)    # P(rain >= 115.6 mm on any day)

    # Rainfall distribution
    rainfall_q10 = Column(Float)            # 10th percentile total rainfall (mm)
    rainfall_q25 = Column(Float)
    rainfall_median = Column(Float)
    rainfall_q75 = Column(Float)
    rainfall_q90 = Column(Float)

    # Regime
    predicted_regime = Column(String(20))   # 'active', 'break', 'transition'
    regime_probability = Column(Float)

    # Model info
    model_version = Column(String(50))
    is_synthetic = Column(Boolean, default=False)  # SYNTHETIC flag

    # SHAP-based explanation
    explanation_en = Column(Text)
    top_drivers = Column(JSON)  # e.g., [{"feature": "BSISO_phase", "shap_value": 0.15}, ...]

    # Confidence
    brier_skill_score = Column(Float)
    confidence_level = Column(String(20))   # 'high', 'moderate', 'low'

    block = relationship("Block", back_populates="forecasts")


# ─── Advisories ──────────────────────────────────────────────────────────────

class Advisory(Base):
    """Crop-specific advisory for a panchayat."""
    __tablename__ = "advisories"
    __table_args__ = (
        Index("ix_advisory_date", "issue_date"),
    )

    id = Column(Integer, primary_key=True)
    panchayat_id = Column(Integer, ForeignKey("panchayats.id"), nullable=False)
    forecast_id = Column(Integer, ForeignKey("forecasts.id"), nullable=True)
    issue_date = Column(Date, nullable=False)
    crop = Column(String(50), nullable=False)

    # Action
    action = Column(String(20), nullable=False)  # SOW, WAIT, SWITCH, PROTECT, ALERT
    action_detail = Column(Text)

    # Seedling survival probability
    seedling_survival_prob = Column(Float)

    # Advisory text in multiple languages
    message_en = Column(Text, nullable=False)
    message_te = Column(Text)
    message_hi = Column(Text)

    # Officer approval
    status = Column(String(20), default="pending")  # pending, approved, rejected, edited
    approved_by = Column(String(100))
    approved_at = Column(DateTime)
    officer_notes = Column(Text)
    edited_message = Column(Text)  # If officer edits the message

    # Delivery
    delivered_whatsapp = Column(Boolean, default=False)
    delivered_sms = Column(Boolean, default=False)
    delivered_at = Column(DateTime)

    panchayat = relationship("Panchayat", back_populates="advisories")


# ─── Farmer Feedback ─────────────────────────────────────────────────────────

class FarmerFeedback(Base):
    """Farmer-reported ground truth for verification."""
    __tablename__ = "farmer_feedback"

    id = Column(Integer, primary_key=True)
    panchayat_id = Column(Integer, ForeignKey("panchayats.id"), nullable=False)
    report_date = Column(Date, nullable=False)
    reported_at = Column(DateTime, default=datetime.utcnow)

    # Rain report
    rain_today = Column(Boolean)          # Did it rain today? yes/no
    rain_intensity = Column(String(20))   # 'none', 'light', 'moderate', 'heavy'

    # Crop report (optional)
    crop = Column(String(50))
    crop_condition = Column(String(20))   # 'good', 'stressed', 'damaged', 'failed'

    # Farmer info (anonymised)
    farmer_phone_hash = Column(String(64))  # SHA-256 of phone number
    language = Column(String(5), default="te")


# ─── Teleconnection Indices ──────────────────────────────────────────────────

class TeleconnectionIndex(Base):
    """Daily/weekly teleconnection indices for model drivers."""
    __tablename__ = "teleconnection_indices"
    __table_args__ = (
        UniqueConstraint("index_name", "obs_date", name="uq_index_date"),
    )

    id = Column(Integer, primary_key=True)
    index_name = Column(String(20), nullable=False)  # 'oni', 'dmi', 'rmm1', 'rmm2', 'bsiso1', 'bsiso2'
    obs_date = Column(Date, nullable=False)
    value = Column(Float, nullable=False)
    phase = Column(Integer)         # MJO/BSISO phase (1-8)
    amplitude = Column(Float)       # MJO/BSISO amplitude
