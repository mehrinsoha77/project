#!/usr/bin/env bash
# Score the held-out test years (2023–2025) ONCE, run ablations, regenerate the
# claims ledger and export everything for the dashboard.
# A second evaluation needs: RERUN_REASON="why" bash scripts/evaluate_model.sh
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -n "${RERUN_REASON:-}" ]; then
  python -m src.models.evaluate --rerun-reason "$RERUN_REASON"
else
  python -m src.models.evaluate
fi
python -m src.models.ablate
python scripts/time_pipeline.py --passes 5 || echo "timing skipped"
python -m src.claims
python -m src.api.export --images
