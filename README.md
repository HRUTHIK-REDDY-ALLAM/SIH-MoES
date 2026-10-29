# Varsha

Monsoon forecasting and crop advisory prototype, built for Smart India Hackathon 2024 (Ministry of Earth Sciences problem statement).

The idea: farmers often sow after the first few rains and then lose the crop when a long dry spell follows (a "false onset"). Regional forecasts are too coarse to help at village level, so we try to give block/panchayat level probabilities and turn them into simple sow / wait advice.

## What it does

- Pulls rainfall and climate index data (CHIRPS, ENSO, IOD, MJO)
- Labels onset, false onset, dry spell and heavy rain events from daily rainfall
- Trains a few baseline models and a downscaling step to get block-level probabilities
- Runs a simple water balance and rule-based advisory per crop
- Translates advisories to Telugu and Hindi
- Shows everything on a small Next.js web app with a map

## Pilot area

Telangana: Mahbubnagar, Nalgonda and Medak districts. Crops are cotton, soybean, groundnut and paddy. The demo uses the 2023 Kharif season, including the August break.

## Setup

You need Docker, or Python 3.11+ and Node 20+.

With Docker:

```bash
cp .env.example .env
docker compose up
docker compose exec backend python scripts/create_tables.py
docker compose exec backend python scripts/load_boundaries.py
```

Frontend runs on http://localhost:3000, API on http://localhost:8000 (docs at /docs).

Without Docker (needs a Postgres/PostGIS database configured in `.env`):

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload

cd frontend
npm install
npm run dev
```

Tests: `pytest`

## Folder layout

```
config/        thresholds and parameters (yaml)
data/          data fetchers, one per source
models/        baselines, downscaling, weather generator, onset model
impact/        water balance and advisory rules
translation/   Telugu / Hindi translation adapter
backend/       FastAPI app, DB models, pipeline
frontend/      Next.js app
scripts/       DB setup and boundary loading
tests/
```

## Event definitions

Defined in `config/event_thresholds.yaml`:

| Event | Definition |
|---|---|
| Rainy day | >= 2.5 mm |
| Onset | >= 20 mm over 3 consecutive days after May 15 |
| False onset | onset followed by a 7+ day dry spell within 30 days |
| Dry spell | 7+ consecutive days under 2.5 mm |
| Heavy rain | >= 64.5 mm/day |
| Very heavy rain | >= 115.6 mm/day |

## Data

CHIRPS, NOAA ONI, IOD DMI, MJO RMM and CFSv2 are open. IMD gridded data, ERA5 (needs a CDS API key) and SMAP (needs Earthdata login) are only partly wired up.

## Known limitations

- Block and panchayat boundaries are synthetic approximations, not real LGD boundaries. Panchayat names are generated. API responses carry `is_synthetic: true` for this.
- WhatsApp/SMS delivery is mocked.
- Only tested on the pilot districts.

## Team

Team Varsha, SIH 2024.

## License

MIT
