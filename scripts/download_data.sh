#!/usr/bin/env bash
# Build the Sentinel-1 catalogue and fetch/calibrate/geocode every pass.
# Everything is read from public AWS Open Data buckets over HTTPS; nothing to sign up for.
# Disk: ~40 MB per pass of cached sigma0 (data/raw/sentinel1), ~0.4 MB per mask.
set -euo pipefail
cd "$(dirname "$0")/.."
WORKERS="${WORKERS:-4}"

if [ ! -f data/processed/s1_catalog.json ]; then
  echo "==> Catalogue of Sentinel-1 track-150 passes over the reach (2015–2025)"
  python -m src.masks.s1_io --workers 16
fi
echo "==> Radar passes -> calibrated, geocoded sigma0 -> water masks ($WORKERS workers)"
python -m src.masks.sentinel1_mask --workers "$WORKERS"
echo "==> Copernicus DEM GLO-30 for the optional bank-height feature"
python -c "from src.features.geometry import fetch_dem; print(fetch_dem())"
