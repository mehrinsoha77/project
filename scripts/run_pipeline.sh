#!/usr/bin/env bash
# Full pipeline: data -> masks -> banks -> validation -> labels -> features -> model -> export.
# The test years are NOT scored here; see scripts/evaluate_model.sh.
set -euo pipefail
cd "$(dirname "$0")/.."

bash scripts/download_data.sh

if [ ! -f data/processed/transects/transects.geojson ]; then
  echo "==> Baselines (from the first 12 months) and 200 m transects"
  python -m src.banks.baselines
  python -m src.banks.transects
fi
echo "==> Bank position on every transect, every pass"
python -m src.banks.bank_position --workers "${WORKERS:-3}"
echo "==> Check radar masks against cloud-free Sentinel-2; sets the label threshold"
python -m src.masks.validate_masks --max-pairs 16
echo "==> Labels and features"
python -m src.labels.make_labels
python -m src.features.build_features
bash scripts/train_model.sh
echo "Done. Next: bash scripts/evaluate_model.sh (scores the held-out years once)."
