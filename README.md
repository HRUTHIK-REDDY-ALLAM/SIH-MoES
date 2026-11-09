# Varsha

**Hyperlocal monsoon onset & break prediction with crop advisories** — Smart India Hackathon 2026,
problem statement **26086** (Ministry of Earth Sciences / NCMRWF).

Farmers often sow after the first good rains, then lose the crop when a long dry spell follows (a *false onset*).
Regional forecasts are too coarse to help at village level. Varsha gives **block- and panchayat-level
probabilities, 1–4 weeks ahead**, of monsoon onset, false onset, dry spells (breaks) and heavy rain. It turns
them into **sow / wait / protect / switch** advice in **Telugu, Hindi and English**, sent by SMS / WhatsApp
after an extension officer approves it.

See **[ARCHITECTURE.md](ARCHITECTURE.md)** for the full design.

## What it does

- **Ingests planetary drivers:** ENSO (NOAA CPC ONI), IOD (NOAA PSL DMI) and MJO (BoM RMM), live with caching, plus regional low-level jet and OLR predictors.
- **Labels events** from daily rainfall: onset (≥ 20 mm in 3 days), false onset, 7/14-day dry spells, heavy (≥ 64.5 mm) and very heavy (≥ 115.6 mm) rain.
- **Hybrid downscaling model:** LightGBM on top of each block's climatology, with a 2-state HMM for active/break regimes and the projected MJO phase as a lead predictor. Outputs are calibrated probabilities for 7/14/21/30-day windows and rainfall quantiles, with TreeSHAP explanations.
- **Panchayat level:** block forecasts are interpolated to every gram panchayat, plus a panchayat water balance driven by local soil type and irrigation.
- **Expert system:** ICAR-CRIDA-style rules and a cost-loss sowing decision based on *seedling survival if sown today*. Survival comes from a forecast-conditioned analog weather generator run through an FAO-56 water balance.
- **Delivery:** officer console (review / edit / approve / dispatch), SMS and WhatsApp gateway (mock by default, real adapters included), and farmer replies (“1” = it rained) stored as ground truth.
- **Web app:** colour-coded risk maps (block / panchayat), a mobile farmer view, the officer console, a day-by-day 2023 season replay, and a verification page (BSS, AUC, reliability diagrams).

## Quick start (no Docker, SQLite)

Needs Python 3.11+ and Node 20+.

```bash
pip install -r requirements.txt
```

Build the database, train the model (about 90 s), replay the 2023 season and export static data:

```bash
python scripts/bootstrap_demo.py --reset
```

Start the API (docs at http://localhost:8000/docs):

```bash
uvicorn backend.main:app --reload
```

In another terminal, start the web app at http://localhost:3000:

```bash
cd frontend && npm install && npm run dev
```

Without `DATABASE_URL` set, everything uses SQLite at `data/varsha.db`. If your `.env` still points at the
Docker host `db`, comment that line out for local runs. The web app also works with the API stopped
(read-only, from `frontend/public/data/*.json`).

Officer console login: `OFFICER_USERNAME` / `OFFICER_PASSWORD` from `.env` (defaults `officer` / `varsha2024`).

## With Docker (PostgreSQL + PostGIS)

```bash
cp .env.example .env
```

```bash
docker compose up -d
```

```bash
docker compose exec backend python scripts/bootstrap_demo.py --reset
```

Daily operational run (for example from cron at 06:00 IST):

```bash
docker compose --profile pipeline run pipeline python -m backend.pipeline.daily_run --dispatch
```

## Everyday commands

| Task | Command |
|---|---|
| Retrain + hindcast verification | `python -m models.train` |
| Forecast + advisories for one date | `python -m backend.pipeline.daily_run --date 2023-07-01` |
| Replay a season | `python -m backend.pipeline.daily_run --replay` |
| Re-export static JSON for the web app | `python -m backend.services.export` |
| Use real CHIRPS rainfall | `pip install rasterio` then `python scripts/extract_chirps_blocks.py --start 1991 --end 2023` |
| Tests | `pytest` |

## Pilot

Telangana: Mahbubnagar, Nalgonda and Medak districts (25 blocks, 125 panchayats). Crops are cotton, soybean,
groundnut and paddy. The demo replays the 2023 Kharif season (15 May – 15 Oct) and opens on 12 June 2023,
just after the early-June false start.

## Current skill (leave-years-out hindcast 1991–2022, synthetic rainfall)

| Event | Week 1 BSS / AUC | Weeks 1–2 BSS / AUC |
|---|---|---|
| Onset | +0.17 / 0.81 | +0.08 / 0.80 |
| False onset | +0.08 / 0.74 | +0.04 / 0.72 |
| Dry spell (7+ days) | +0.08 / 0.77 | +0.04 / 0.74 |

BSS is measured against each block's own climatology. Skill fades towards climatology by weeks 3–4,
as expected for extended-range forecasts. Full tables, reliability diagrams and the held-out 2023 scores are on
the **Skill** page.

## Folder layout

```
config/        pilot region, event thresholds, crop parameters, advisory rules and texts (en/te/hi)
data/          fetchers (NOAA, BoM, CHIRPS, ERA5, ...), climate simulator, source layer, sample boundaries
models/        events, features, climatology, HMM regimes, hybrid downscaler, weather generator, verification, training
impact/        FAO-56 water balance, advisory expert system
translation/   Bhashini / glossary adapter, Telugu and Hindi glossaries
backend/       FastAPI app, DB models, daily pipeline, services (read models, export, messaging)
frontend/      Next.js app (risk map, farmer view, officer console, replay, skill)
scripts/       bootstrap_demo, load_boundaries, create_tables, extract_chirps_blocks
tests/
```

## Honest limitations

- **Rainfall is synthetic** for now: a teleconnection-driven simulator calibrated to Telangana. Real CHIRPS block means replace it automatically once extracted. ENSO and IOD are real; the 2023 MJO is a scripted scenario matched to the replay season.
- **Boundaries and soils are approximations**, not LGD boundaries; panchayat names are generated. Every payload carries `is_synthetic`.
- **Telugu and Hindi texts** need review by native-speaking agronomists before field use.
- **SMS / WhatsApp** run against a mock outbox by default. Demo subscribers use invalid numbers and are never messaged.
- Rainfall ranges are too narrow: the 10–90% interval holds the observed total 63–69% of the time instead of 80%. Interval calibration is still to do.
- The PostGIS code path is written for production but has only been exercised on SQLite in development.

## Team

Team Varsha, SIH 2026.

## License

MIT
