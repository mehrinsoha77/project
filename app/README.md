# NadiNet dashboard (Next.js 14)

Static-first web app for NadiNet: the landing page, the operational
dashboard, the replay demo and the method & evidence page.

```bash
npm install
npm run dev          # http://localhost:3000
npm run build && npm start
```

## Data

Everything the app shows lives in `public/data/`, exported by the Python
pipeline (`python -m src.api.export --images` from the repo root):

| File | Content |
|---|---|
| `reach.json` | reach box, baselines, 871 transects (start/end lon/lat), radar image bounds |
| `passes.json` | every Sentinel-1 pass: date, Otsu thresholds, stage proxy, preview image |
| `banks/<year>.json` | bank position (m from baseline) per transect per pass |
| `predictions/index.json` | forecast dates with per-date precision@20 (model, persistence) |
| `predictions/<date>.json` | per-segment calibrated risk, ranks, tier, reasons, outcome |
| `metrics.json` | all measured metrics + the claims ledger |
| `radar/<pass>.webp` | VV previews (40 m, Web Mercator) for 2022–2025 |
| `wow/` | a cloudy Sentinel-2 monsoon scene and the radar pass of the same week |
| `briefs/<date>.pdf` | weekly risk brief for each forecast date |

No backend is needed to browse. Alert actions go to `/api/proxy/*`, which
forwards to FastAPI when `NADINET_API_URL` is set; otherwise the app runs
them in a clearly labelled offline mode (logged in the browser, nothing sent).

## Stack

Next.js 14 (App Router) · React 18 · TypeScript · Tailwind CSS with
shadcn/ui-style primitives (Radix) · Leaflet (react-leaflet) with the radar
image as the base map · Recharts · Framer Motion · lucide-react.

## Deploy

Vercel: set the project root to `app/`. Optionally set `NADINET_API_URL` to a
deployed FastAPI (`uvicorn src.api.main:app`).
