# Varsha web app (Next.js 16)

| Route | What it shows |
|---|---|
| `/` | Colour-coded risk map (onset, false onset, dry spell, long break, heavy rain, rainfall) for weeks 1–4, at block or panchayat level, with block and panchayat detail panels |
| `/farmer` | Mobile-first farmer view in Telugu / Hindi / English: today's action for a crop, 4-week outlook, rain report, SMS/WhatsApp sign-up |
| `/officer` | Extension officer console: review, edit, approve, reject, bulk approve, dispatch, outbox, pipeline runs |
| `/replay` | Day-by-day replay of the 2023 Kharif season against observed rain |
| `/skill` | Hindcast verification: BSS / AUC tables, reliability diagrams, block trust scores |

```bash
npm install
npm run dev        # http://localhost:3000
```

The app reads the FastAPI backend at `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`). If the backend is
not reachable it falls back to the static snapshot in `public/data/*.json` (written by
`python -m backend.services.export`). The officer console, rain reports and sign-ups need the backend.
