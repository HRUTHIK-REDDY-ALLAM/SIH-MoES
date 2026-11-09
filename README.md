# Varsha (वर्षा)

Village-level monsoon onset and break outlooks for farmers, with crop advice they can act on.

Built for **Smart India Hackathon 2026**, problem statement **26086**: *Hyperlocal Monsoon Onset & Break
Prediction System (Block/Village Scale)*, from the Ministry of Earth Sciences / NCMRWF.

[![Live demo](https://img.shields.io/badge/live%20demo-open%20the%20site-138808?style=for-the-badge)](https://prompt-rowan-5b6qk1m.tmp.now/)

## Deployed link

**https://prompt-rowan-5b6qk1m.tmp.now/**

| Page | Address |
|---|---|
| Risk map | https://prompt-rowan-5b6qk1m.tmp.now/ |
| Farmer view | https://prompt-rowan-5b6qk1m.tmp.now/farmer |
| Officer console | https://prompt-rowan-5b6qk1m.tmp.now/officer |
| 2023 replay | https://prompt-rowan-5b6qk1m.tmp.now/replay |
| Forecast verification | https://prompt-rowan-5b6qk1m.tmp.now/skill |

This is the website only, running read-only on the committed 2023 data. The officer console, approvals and
rain reports need the backend, so run it locally (see below). The link is a temporary Vercel preview and may
expire, so if it doesn't open, run the project yourself using the steps further down.

---

## Why we built this

Every Kharif season the same thing happens in rain-fed Telangana. A few heavy showers arrive in early June,
the soil looks ready, and farmers sow cotton or groundnut. Then the rain stops for ten or fifteen days. The
seedlings dry out, and the family pays for seed a second time. Meteorologists call this a *false onset*.

The forecasts that exist today are issued for whole districts or meteorological subdivisions. They say
whether the monsoon has arrived over "Telangana". They don't say whether *this* mandal is likely to see
a dry week right after sowing. That's the question a farmer actually has.

Varsha tries to answer it. For every block (mandal) and every gram panchayat in the pilot, it gives the
probability, 1 to 4 weeks ahead, of:

- the monsoon setting in (onset),
- a false onset,
- a dry spell of 7+ or 14+ days (a "break"),
- heavy rain (64.5 mm or more in a day).

Those numbers are then turned into one plain instruction per crop: **sow now, wait, protect, irrigate,
switch crop**, and so on. The advice is written in Telugu, Hindi and English. An agricultural extension
officer checks it before it goes out by SMS or WhatsApp. No message reaches a farmer without that
officer's approval.

## What's in the box

| Part | What it does |
|---|---|
| Data layer | Pulls ENSO (NOAA CPC ONI), IOD (NOAA PSL DMI) and MJO (BoM RMM) indices, with the same publication delays the real feeds have |
| Forecast model | LightGBM on top of each block's own climatology, an active/break HMM, and the MJO phase projected into the forecast window |
| Panchayat downscaling | Spreads block forecasts to each panchayat and runs a soil water balance using that panchayat's soil type |
| Advisory engine | Rule base modelled on ICAR-CRIDA contingency plans, plus a cost-loss sowing decision based on "will the seedlings survive if sown today?" |
| Delivery | Officer console (review, edit, approve, dispatch), SMS and WhatsApp gateway, farmer replies stored as ground truth |
| Web app | Risk map, farmer view, officer console, a day-by-day replay of the 2023 season, and a forecast verification page |

The full design, with diagrams and the reasoning behind each choice, is in
[ARCHITECTURE.md](ARCHITECTURE.md).

## The pilot

- **Region:** Mahbubnagar, Nalgonda and Medak districts of Telangana. That's 25 blocks and 125 gram panchayats.
- **Crops:** cotton, soybean, groundnut and paddy.
- **Demo season:** Kharif 2023 (15 May to 15 October). We picked 2023 because it had exactly the problem we
  care about: an early-June false start in the west of the state, a proper onset in late June, and a long
  dry break in August.

---

## Running it on your machine

There are two ways to run Varsha. **Path A** needs only Python and Node, and stores everything in a single
SQLite file. It's the one we use for development and for demos. **Path B** runs the production setup
(PostgreSQL + PostGIS) inside Docker.

If you only want to look at the web app, skip to [Just the website](#just-the-website-no-backend).

### What you need

- **Python 3.11 or newer.** We test on 3.11 and 3.12.
- **Node.js 20 or newer**, with npm.
- **Git.**
- About 2 GB of free disk space and around 5 minutes for the first full setup.
- For Path B only: Docker Desktop.

On macOS, LightGBM also needs the OpenMP runtime: `brew install libomp`. Windows and Linux wheels include it.

### Path A: local setup with SQLite (recommended)

**Step 1. Get the code.**

```bash
git clone https://github.com/HRUTHIK-REDDY-ALLAM/SIH-MoES.git
cd SIH-MoES
```

**Step 2. Create a virtual environment and install the Python packages.**

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell refuses to run the activate script, run
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then try again.

**Step 3. Set up your environment file.**

```bash
cp .env.example .env
```

Open `.env` and check one thing. For a local run, `DATABASE_URL` must stay **commented out**. When it's
unset, Varsha uses SQLite at `data/varsha.db`. If you've copied a `.env` from a Docker setup and it points at
the host `db`, the backend will hang trying to reach a database that doesn't exist on your laptop.

While you're in `.env`, you can change the officer login (`OFFICER_USERNAME` and `OFFICER_PASSWORD`). The
defaults are `officer` / `varsha2024`.

**Step 4. Build the database, train the model and replay the season.** This one command does all of it:

```bash
python scripts/bootstrap_demo.py --reset
```

It takes 2 to 4 minutes on a normal laptop and prints each step as it goes:

1. Creates the tables. `--reset` drops any old ones first.
2. Builds block and panchayat boundaries and soil types, and loads them into the database.
3. Trains the forecast model and runs the leave-years-out hindcast over 1991–2022 (about 90 seconds). The
   model is saved to `artifacts/models/varsha_model.joblib`. Later runs reuse it unless you pass `--retrain`.
4. Writes each block's hindcast skill and "trust score" to the database.
5. Adds demo subscribers. Their phone numbers are invalid on purpose, so nobody is ever messaged by accident.
6. Replays the 2023 Kharif season one day at a time. Each morning it makes forecasts and advisories using only
   the data that was available on that day.
7. Exports static JSON for the web app into `frontend/public/data/`.

Useful flags:

| Flag | Effect |
|---|---|
| `--reset` | Drop and recreate every table |
| `--retrain` | Train a fresh model even if one is saved |
| `--skip-replay` | Stop after training. Faster, but the map will be empty. |
| `--step 3` | Replay every 3rd day instead of every day. Good for a quick check. |
| `--year 2023` | Which season to replay |

When it finishes you'll see `Done in ...s. Start the API: uvicorn backend.main:app --reload`.

**Step 5. Start the API.** Keep this terminal open.

```bash
uvicorn backend.main:app --reload
```

The API runs at http://localhost:8000. Open http://localhost:8000/docs for the interactive Swagger page,
where you can try every endpoint. http://localhost:8000/health should return `{"status": "ok"}`.

**Step 6. Start the web app.** Open a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. The header badge should say **● live API**. If it says **○ static snapshot**,
the web app can't reach the backend. Check that Step 5 is still running.

If your API runs somewhere other than `localhost:8000`, set `NEXT_PUBLIC_API_URL` before `npm run dev`.

**Step 7. Run the tests (optional, but please do before a pull request).**

```bash
pytest
```

There are 38 tests. They cover event labelling (onset, false onset, dry spells), the models, the advisory
rules and the API.

### Path B: Docker with PostgreSQL + PostGIS

This is the setup we'd deploy. It starts the database, the API and the web app in containers.

```bash
cp .env.example .env
```

Before starting, change `POSTGRES_PASSWORD` and `SECRET_KEY` in `.env`, even for a test run.

```bash
docker compose up -d --build
```

Wait for the database health check to pass (`docker compose ps` shows `healthy`), then build the demo data
inside the backend container:

```bash
docker compose exec backend python scripts/bootstrap_demo.py --reset
```

- Web app: http://localhost:3000
- API docs: http://localhost:8000/docs
- PostGIS: `localhost:5432` (credentials from `.env`)

To stop everything: `docker compose down`. Add `-v` only if you also want to delete the database volume.

### Just the website (no backend)

The exported JSON for the 2023 season is committed in `frontend/public/data/`, so the web app runs on its
own:

```bash
cd frontend
npm install
npm run dev
```

The map, farmer view, replay and skill pages all work read-only. Anything that writes data needs the API:
logging in as an officer, approving advisories, reporting rain, subscribing. Because of this, the whole
frontend can also be put on any static host for judges to browse.

---

## A five-minute tour of the demo

Once both servers are running, this is the path we walk judges through.

1. **Risk map** (`/`). The map opens on the latest issue date of the replayed season. Pick a risk along the
   top (Onset, False onset, Dry spell, Long break, Heavy rain, Rain mm), a lead time (Wk 1 to Wk 4), and
   Blocks or Panchayats. Darker means more likely. Click any block to see its probabilities against
   climatology (the dark tick on each bar), the drivers behind the forecast, a rainfall range, the season
   so far, and its panchayats.
2. **Farmer view** (`/farmer`). This is what a farmer sees on a phone. It's Telugu first, with Hindi and
   English one tap away. Choose a mandal, a village and a crop to get a single instruction ("Wait — do not
   sow yet"), the chance that seedlings survive if sown today, and a four-week rain outlook. The "Did it rain
   today?" buttons send a ground-truth report to the backend.
3. **Officer console** (`/officer`). Log in with the credentials from `.env`. Filter pending advisories by
   district, block or action. Read each one in any language, edit the wording, then approve or reject it.
   **Dispatch** sends the approved ones through the gateway, and the phone on the right shows what was
   delivered. You can also re-run the whole pipeline for any date from here.
4. **2023 replay** (`/replay`). Press **Play** to watch the season unfold one morning at a time. Click the
   event chips (the June false onset, the August break) to jump straight to them. The chart compares what
   Varsha forecast on that day with the rain that actually fell afterwards.
5. **Skill** (`/skill`). The honest scorecard: Brier skill score and ROC AUC for every event and lead time,
   reliability diagrams, rainfall interval coverage, and a trust score per block.

The officer console defaults to dispatching through a **mock gateway**. Messages land in a local outbox
table, not on real phones. See [Sending real SMS / WhatsApp](#sending-real-sms--whatsapp) if you want the
real thing.

---

## How a forecast gets made

This is what happens every morning, whether it's the replay or the real daily run
(`backend/pipeline/daily_run.py`). The issue date is *t*. Only data up to *t − 1* is used, so nothing
from the future leaks in.

**1. Collect yesterday's data.** Block rainfall and temperature are stored. The ocean and atmosphere indices
are refreshed with realistic delays: ONI arrives about 45 days late, DMI about 30 days, and the MJO about
1 day, matching when NOAA and BoM actually publish them.

**2. Work out where each block stands.** We label the observed onset status (not yet, provisional,
established, false onset) using fixed definitions in `models/events.py`:

- **Onset:** at least 20 mm of rain over 3 consecutive days, after 15 May.
- **False onset:** an onset spell followed by a dry spell of 7 or more days within 30 days.
- **Dry spell:** 7 (or 14) consecutive days with less than 2.5 mm each.
- **Heavy / very heavy rain:** a day with at least 64.5 / 115.6 mm (IMD thresholds).

A two-state hidden Markov model also estimates whether the block is currently in an active or a break phase,
and the water balance gives today's soil moisture.

**3. Build the features.** For each block and each lead time (7, 14, 21 and 30 days):

- **Planetary:** ENSO, IOD, the MJO phase and amplitude, and the MJO phase *projected to the middle of the
  forecast window*. The MJO drifts east at a fairly steady rate, which is the main source of skill at 2 to 4
  weeks.
- **Regional:** low-level jet strength and OLR anomalies.
- **Local:** recent rain over 3, 7, 14 and 30 days, the current dry run, season total, soil moisture and
  onset state.
- **Static:** location, elevation, day of year, and the block's own climatological chance of each event.

**4. Predict.** There's one LightGBM classifier per event. The trick we rely on is that each model starts
from the block's climatology (as the boosting `init_score`), so the trees only learn *how this year differs
from normal*. Quantile models give the rainfall range (10th to 90th percentile). Isotonic calibration then
makes sure a 40% forecast really means "about 4 times in 10". Finally a few consistency rules are applied. A
14-day dry spell can't be more likely than a 7-day one, and a false onset can't be more likely than onset.

**5. Explain.** TreeSHAP contributions are grouped into readable drivers ("MJO (projected)", "ENSO",
"Recent local rain") and stored with every forecast. That's where the ▲ / ▼ chips on the map panel come from.

**6. Go down to the panchayat.** Block forecasts are interpolated (inverse-distance weighting) to each of the
125 panchayats. Each panchayat then gets its own soil moisture from its soil type: red sandy loam, red loam
or black cotton soil.

**7. Decide what to advise.** For every panchayat and crop, a forecast-conditioned weather generator draws
about 650 historical 30-day rain sequences. They're re-weighted so that, together, they match today's
forecast, and each one is run through an FAO-56 water balance. The share of sequences in which the seedlings
survive is the **seedling survival probability**. The rule base in `config/advisory_rules.yaml` is then
checked in priority order: very heavy rain alert, switch crop, too early to sow, sow, wait, re-sow warning,
protect, irrigate, prepare for heavy rain, conserve moisture. "Sow" only fires when the expected survival
beats the farmer's cost-loss ratio.

**8. Store and wait for a human.** Forecasts and advisories go into the database with status `pending`. Each
advisory records the rule that fired and every number it looked at, so the officer can see *why*.

**9. Deliver.** Once an officer approves, dispatch sends each subscriber the advice in their own language
over their chosen channel. Farmers can reply `1` (it rained), `2` (no rain), `HELP` or `STOP`. Rain replies
are stored as ground truth for checking the forecasts later.

---

## Day-to-day commands

All of these run from the project root with the virtual environment active.

| What you want | Command |
|---|---|
| Retrain the model and redo the hindcast | `python -m models.train` |
| Forecast + advisories for one date | `python -m backend.pipeline.daily_run --date 2023-07-01` |
| Same, and send approved advisories | `python -m backend.pipeline.daily_run --date 2023-07-01 --dispatch` |
| Replay a whole season | `python -m backend.pipeline.daily_run --replay --year 2023` |
| Run outside the Kharif season (testing) | add `--force` |
| Re-export the static JSON for the web app | `python -m backend.services.export` |
| Rebuild boundaries only | `python scripts/load_boundaries.py` (add `--no-db` to just write GeoJSON) |
| Run the tests | `pytest` |
| Lint the frontend | `cd frontend && npm run lint` |
| Production build of the frontend | `cd frontend && npm run build && npm start` |

**Daily operational run.** In production, a scheduler runs this every morning at 06:00 IST:

```bash
docker compose --profile pipeline run --rm pipeline python -m backend.pipeline.daily_run --dispatch
```

On a plain Linux server, a cron line does the same job:

```
30 0 * * *  cd /opt/varsha && .venv/bin/python -m backend.pipeline.daily_run --dispatch
```

(00:30 UTC is 06:00 IST.)

### Using real CHIRPS rainfall instead of the simulator

The simulator exists only because we couldn't ship 30 years of gridded rainfall in a repository. To switch
to real satellite rainfall:

```bash
pip install rasterio
python scripts/extract_chirps_blocks.py --start 1991 --end 2023
python scripts/bootstrap_demo.py --reset --retrain
```

The extraction downloads one daily CHIRPS v2.0 GeoTIFF per day and averages it over each block, so a full
33-year pull is slow and large. Try `--start 2019` first. Once the block cache
(`data/processed/chirps_blocks.parquet`) exists, the data layer swaps real rain in for every complete season it
covers and keeps the simulator for the rest. The `is_synthetic` flag only clears when every season is real.

### Sending real SMS / WhatsApp

Set `MESSAGING_MODE` in `.env`:

- `mock` (default): everything goes to the outbox table, shown in the officer console.
- `whatsapp`: WhatsApp Cloud API. Fill in `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID` and `WHATSAPP_VERIFY_TOKEN`,
  and point the webhook at `/api/v1/messaging/whatsapp/webhook`.
- `sms`: a generic HTTP SMS gateway. Fill in `SMS_API_URL`, `SMS_API_KEY` and `SMS_SENDER_ID`. In India the
  sender ID and message templates must be DLT-registered first.

Demo subscribers have deliberately invalid numbers and stay unmessaged in every mode. Add real numbers
through the farmer view's subscribe form or `POST /api/v1/messaging/subscribers`.

### Working offline

Set `VARSHA_OFFLINE=1` in `.env` and Varsha will never call NOAA or BoM. It uses its cached or synthetic
driver data instead. This is handy at hackathon venues with unreliable Wi-Fi.

---

## API at a glance

Full, clickable documentation is at `/docs` when the backend is running. The main groups:

| Area | Endpoints |
|---|---|
| Dashboard | `GET /api/v1/dashboard/latest`, `/dashboard/drivers` |
| Forecasts | `GET /api/v1/forecasts/block/{id}`, `/panchayat/{id}`, `/map?event=&horizon_days=&level=` |
| Advisories | `GET /api/v1/advisories/panchayat/{id}?language=te` |
| Officer (HTTP Basic auth) | `GET /api/v1/officer/pending`, `POST /officer/review/{id}`, `/officer/approve-all`, `/officer/dispatch` |
| Messaging | `POST /api/v1/messaging/subscribers`, `GET /messaging/outbox`, `POST /messaging/inbound` |
| Farmer feedback | `POST /api/v1/feedback/report` |
| Replay | `GET /api/v1/replay/bundle`, `/replay/snapshot/{date}` |
| Verification | `GET /api/v1/verification/skill` |
| Pipeline | `POST /api/v1/pipeline/run?run_date=YYYY-MM-DD` |

---

## How good is it?

These numbers come from a leave-years-out hindcast over 1991–2022. Each year is forecast by a model that
never saw it. The baseline is each block's own climatology, so a Brier skill score (BSS) above zero means
"better than just using the long-term average for that block and date".

| Event | Week 1 (BSS / AUC) | Weeks 1–2 (BSS / AUC) |
|---|---|---|
| Onset | +0.17 / 0.81 | +0.08 / 0.80 |
| False onset | +0.08 / 0.74 | +0.04 / 0.72 |
| Dry spell (7+ days) | +0.08 / 0.77 | +0.04 / 0.74 |

Skill drops towards climatology by weeks 3 and 4, which is what you'd expect at extended range. The Skill
page in the app has the complete tables, reliability diagrams and the fully held-out 2023 scores.

**These scores are on synthetic rainfall** (see below), so treat them as evidence that the pipeline works,
not as a claim about real-world accuracy.

---

## What's real and what isn't (yet)

We'd rather say this up front than have a judge find it.

- **Rainfall is simulated.** A weather simulator calibrated to Telangana (driven by ENSO, IOD and the MJO)
  stands in for observed rain, until real CHIRPS data is extracted (see above).
- **ENSO and IOD are real** NOAA data. **The MJO is real** BoM data, except for the 2023 season, which uses a
  scripted path that matches the replay scenario.
- **Boundaries and soils are approximate**, and panchayat names are generated. They're not official LGD
  boundaries. Swap in the real GeoJSON in `data/sample/boundaries/`.
- **The Telugu and Hindi advisories** were drafted by us and need review by native-speaking agronomists
  before anyone relies on them in the field.
- **Rainfall ranges are too narrow.** The 10–90% interval should contain the observed total 80% of the time,
  but currently does so only 63–69% of the time. Fixing that interval calibration is next on our list.
- **PostGIS** is the production target and the code supports it, but most of our testing so far has been on
  SQLite.

Every forecast, advisory and API response carries an `is_synthetic` flag, and the web app shows a banner
whenever synthetic data is on screen.

---

## Project layout

```
config/        pilot region, event thresholds, crop parameters, advisory rules and message texts (en/te/hi)
data/          fetchers (NOAA, BoM, CHIRPS, ERA5 ...), rainfall simulator, sample boundaries
models/        event labels, features, climatology, HMM, hybrid model, weather generator, verification, training
impact/        FAO-56 water balance and the advisory rule engine
translation/   Bhashini adapter with Telugu and Hindi glossaries as a fallback
backend/       FastAPI app, database models, the daily pipeline, export and messaging services
frontend/      Next.js web app (risk map, farmer view, officer console, replay, skill)
scripts/       bootstrap_demo, load_boundaries, create_tables, extract_chirps_blocks
tests/         pytest suite
```

## Deploying the website yourself

The web app can be served as plain static files, with no server. It reads the committed JSON in
`frontend/public/data/` whenever the API isn't reachable.

```bash
cd frontend
npm install
STATIC_EXPORT=1 npm run build
```

On Windows PowerShell, set the variable first: `$env:STATIC_EXPORT="1"; npm run build`.

That writes the site to `frontend/out/`. Upload that folder to any static host. With Vercel:

```bash
npm install --global vercel@latest
vercel login
cd out
vercel deploy --prod
```

For the full system (officer console, SMS / WhatsApp), host the FastAPI backend somewhere too, then set
`NEXT_PUBLIC_API_URL` to its address before building.

## When something goes wrong

- **The backend hangs on start, or you see a "could not translate host name db" error.** Your `.env` has a
  Docker `DATABASE_URL`. Comment it out for local runs.
- **The header says "static snapshot" even though the API is running.** The web app looks for the API at
  `http://localhost:8000`. If yours is elsewhere, set `NEXT_PUBLIC_API_URL` and restart `npm run dev`.
- **"Static data /data/latest.json not found".** The export step hasn't run. Run
  `python scripts/bootstrap_demo.py` (or `python -m backend.services.export`).
- **The map is blank or grey.** The basemap tiles come from openstreetmap.org. On a blocked network, the
  coloured risk layers still draw, but without the background map.
- **The officer console says it needs the API.** Officer actions are write operations, so the backend must
  be running.
- **LightGBM import error on a Mac.** Run `brew install libomp`.
- **A hydration warning in the browser console mentioning `darkreader`.** That's the Dark Reader extension
  rewriting the page. The page asks it to stay off, so reloading usually fixes it, or disable the extension
  for localhost.

## Contributing

Make a branch off `main`, keep each pull request to one change, and run `pytest` and `npm run lint` before
opening it. If you change an event definition or an advisory rule, update `config/` and the matching tests
in the same pull request. The whole point is that training, verification and the advice farmers receive all
use the same definitions.


