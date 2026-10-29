# 🌧️ Varsha — Monsoon Intelligence System

> **Smart India Hackathon 2024 — Ministry of Earth Sciences**  
> Hybrid probabilistic monsoon forecasting and crop advisory system  
> for Indian farmers at block and panchayat level.

## Problem

Indian farmers lose crops when they sow during a **"false onset"** of the monsoon — a few days of good rain followed by a long dry spell. Regional forecasts are too coarse for village-level planning.

## Solution

**Varsha** is a hybrid framework that:

1. **Ingests** global climate drivers (ENSO, IOD, MJO/BSISO) + regional atmospheric data
2. **Produces** 7–30 day probabilistic outlooks at Block and Panchayat level
3. **Shows** colour-coded risk maps for onset, dry spells, and heavy rain
4. **Converts** probabilities into crop-specific advisories via a deterministic expert-system engine
5. **Delivers** advisories in English, Telugu, and Hindi via mobile web app and WhatsApp/SMS

## Pilot Region

- **State:** Telangana
- **Districts:** Mahbubnagar, Nalgonda, Medak
- **Crops:** Cotton, Soybean, Groundnut, Paddy
- **Demo Season:** 2023 Kharif (including August 2023 monsoon break)

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Node.js 20+ (for frontend development)
- Python 3.11+ (for local development)

### Run Everything

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env with your API keys (optional — defaults work for demo)

# 2. Start all services
docker compose up

# 3. Initialize database tables and load boundaries
docker compose exec backend python scripts/create_tables.py
docker compose exec backend python scripts/load_boundaries.py

# 4. Access the app
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
# API docs: http://localhost:8000/docs
```

### Local Development (without Docker)

```bash
# Backend
pip install -r requirements.txt
uvicorn backend.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        DATA LAYER                                 │
│  CHIRPS │ IMD │ ERA5 │ ENSO │ IOD │ MJO/BSISO │ CFSv2 │ SMAP    │
└────────────────────────┬─────────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────────┐
│                    FORECAST PIPELINE                              │
│  Event Labelling → ML Downscaling → HMM Weather Gen → Calibration│
│  Onset Model → False Onset Classifier → Ensemble Probabilities    │
└────────────────────────┬─────────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────────┐
│                    IMPACT & ADVISORY                              │
│  FAO-56 Water Balance → ICAR-CRIDA Rules → Sow/Wait/Switch       │
│  → Translation (Telugu/Hindi) → Officer Approval                  │
└────────────────────────┬─────────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────────┐
│                    APPLICATION LAYER                              │
│  FastAPI Backend → PostgreSQL/PostGIS → Next.js PWA + MapLibre   │
│  WhatsApp/SMS Mock → Farmer Feedback → Verification              │
└──────────────────────────────────────────────────────────────────┘
```

## Repository Structure

```
varsha/
├── config/              # All tuneable thresholds and parameters
├── data/fetchers/       # One module per data source
├── models/              # ML models (baselines, downscaling, HMM, onset)
├── impact/              # Water balance and advisory engine
├── translation/         # Bhashini/IndicTrans2 adapter
├── backend/             # FastAPI app, routers, DB models, pipeline
├── frontend/            # Next.js PWA with MapLibre
├── scripts/             # DB init, boundary loading, utilities
├── tests/               # pytest test suite
└── docker-compose.yml   # Single command to run everything
```

## Data Sources

| Source | Resolution | Open? | Status |
|--------|-----------|-------|--------|
| CHIRPS 2.0 | 0.05° daily | ✅ Yes | Primary rainfall |
| IMD Gridded | 0.25° daily | ⚠️ Institutional | Documented, upgrade path |
| NOAA CPC ONI | Monthly | ✅ Yes | ENSO index |
| IOD DMI | Monthly | ✅ Yes | Indian Ocean Dipole |
| MJO RMM | Daily | ✅ Yes | MJO phase |
| ERA5 | 0.25° | ⚠️ CDS API key | Temperature, winds |
| CFSv2 | ~1° | ✅ Yes | Dynamical forecasts |
| SMAP | ~9 km | ⚠️ Earthdata | Soil moisture |

## ⚠️ SYNTHETIC Data Notice

The current prototype uses **SYNTHETIC** boundaries and placeholder data for:
- Block and panchayat boundaries (approximate polygons, not real LGD boundaries)
- Panchayat names (generated from block names)

All synthetic data is clearly labelled in the code, API responses (`is_synthetic: true`), and the UI. Never present synthetic results as real.

## Event Definitions

All thresholds are in [`config/event_thresholds.yaml`](config/event_thresholds.yaml):

| Event | Definition |
|-------|-----------|
| Rainy day | ≥ 2.5 mm |
| Agronomic onset | ≥ 20 mm over 3 consecutive days after May 15 |
| False onset | Onset met, followed by ≥ 7 dry days within 30 days |
| Dry spell | ≥ 7 consecutive days with < 2.5 mm |
| Heavy rain | ≥ 64.5 mm/day |
| Very heavy rain | ≥ 115.6 mm/day |

## Team

SIH 2024 — Team Varsha

## License

MIT — for hackathon prototype use.
