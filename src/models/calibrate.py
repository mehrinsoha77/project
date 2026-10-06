"""Isotonic calibration on the validation year (spec §Method 5).

After calibration a score of 0.7 should mean that roughly 70% of segments
given that score lost at least the threshold within 28 days. Whether it does
on the test years is measured (Brier score, reliability diagram), not assumed.

The same treatment is applied to the persistence and history baselines so
Brier scores compare like with like.

CLI::

    python -m src.models.calibrate
"""
from __future__ import annotations

import argparse
import json
import pickle

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from src import config
from src.models.baselines import BASELINES, add_baseline_scores
from src.models.data import load_dataset, temporal_split
from src.models.metrics import brier, reliability
from src.models.train_lgbm import MODEL_DIR, load_model, load_params

CALIBRATORS_PATH = MODEL_DIR / "calibrators.pkl"


def fit_isotonic(score: pd.Series, y: pd.Series) -> IsotonicRegression:
    s = score.fillna(score.min() if score.notna().any() else 0.0)
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(s.to_numpy(), y.to_numpy())
    return iso


def apply(iso: IsotonicRegression, score: pd.Series, fill: float) -> np.ndarray:
    return iso.predict(score.fillna(fill).to_numpy())


def calibrate(df: pd.DataFrame | None = None) -> dict:
    df = df if df is not None else load_dataset()
    _, val, _ = temporal_split(df)
    model, info = load_model(), load_params()
    val = add_baseline_scores(val)
    val["M1_raw"] = model.predict(val[info["features"]])
    cals = {}
    report = {}
    for name in ["M1_raw", *BASELINES]:
        fill = float(val[name].min()) if val[name].notna().any() else 0.0
        iso = fit_isotonic(val[name], val["y"])
        cals[name] = (iso, fill)
        val[f"{name}_p"] = apply(iso, val[name], fill)
        report[name] = dict(brier_val=brier(val, f"{name}_p"), reliability_val=reliability(val, f"{name}_p"))
    with open(CALIBRATORS_PATH, "wb") as f:
        pickle.dump(cals, f)
    return report


def load_calibrators() -> dict:
    with open(CALIBRATORS_PATH, "rb") as f:
        return pickle.load(f)


def main() -> None:
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    rep = calibrate()
    (config.METRICS_DIR / "calibration_val_2022.json").write_text(json.dumps(rep, indent=2))
    print(json.dumps({k: v["brier_val"] for k, v in rep.items()}, indent=2))


if __name__ == "__main__":
    main()
