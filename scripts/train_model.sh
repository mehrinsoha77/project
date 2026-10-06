#!/usr/bin/env bash
# Baselines on 2022, LightGBM trained on 2015–2021 and tuned on 2022, isotonic calibration on 2022.
set -euo pipefail
cd "$(dirname "$0")/.."
python -m src.models.baselines
python -m src.models.train_lgbm
python -m src.models.calibrate
