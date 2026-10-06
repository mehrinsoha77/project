#!/usr/bin/env bash
# Start the API (port 8000) and the dashboard (port 3000) from precomputed results.
# Works offline: all maps, rankings and briefs are in app/public/data.
# Without Python deps, the dashboard alone still runs (alerts switch to offline mode).
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d app/node_modules ]; then
  (cd app && npm install --no-audit --no-fund)
fi

API_PID=""
if python -c "import fastapi, uvicorn" 2>/dev/null; then
  echo "==> API on http://localhost:8000 (console gateway: nothing is really sent)"
  NADINET_ALERT_GATEWAY="${NADINET_ALERT_GATEWAY:-console}" uvicorn src.api.main:app --port 8000 &
  API_PID=$!
  export NADINET_API_URL="http://localhost:8000"
else
  echo "==> Python API not available: dashboard runs in offline demo mode"
fi
trap '[ -n "$API_PID" ] && kill $API_PID 2>/dev/null' EXIT

cd app
if [ "${DEV:-0}" = "1" ]; then
  npm run dev
else
  [ -d .next ] || npm run build
  echo "==> Dashboard on http://localhost:3000"
  npm run start
fi
