"""Training labels: did segment s lose at least the threshold within 28 days?

Spec §Method 3:

    R_s(t1, t2) = b_s(t2) - b_s(t1)
    y_s(t)      = 1[ R_s(t, t + 28 d) >= threshold ]

b_s(t) is the bank position at the radar pass nearest to time t, measured
landward. Two safeguards keep mask noise out of the label:

* **Threshold** = max(20 m, 2 x the median bank-position error measured
  against Sentinel-2) — read from ``mask_validation.json``.
* **Forward confirmation.** A bank that moved landward because floodwater or
  a mis-classified pass pushed the water edge inland comes back on later
  passes; real erosion does not. For labels only, each position is replaced by
  the minimum over the passes in [t, t + CONFIRM_DAYS]:

      b*_s(t) = min{ b_s(tau) : t <= tau <= t + CONFIRM_DAYS }

  so a retreat only counts if the bank stays retreated for that long. This
  uses future passes, which is allowed for a *label*; features never see it
  (``tests/test_no_leakage.py`` checks both sides).

The target pass is the pass nearest to t + 28 days, accepted only if it is
within ``TARGET_TOLERANCE_DAYS``.

CLI::

    python -m src.labels.make_labels
"""
from __future__ import annotations

import argparse
import json
import logging

import numpy as np
import pandas as pd

from src import config
from src.banks.bank_position import load_positions
from src.masks.validate_masks import label_threshold_m

log = logging.getLogger(__name__)

CONFIRM_DAYS = 36            # three 12-day revisits
TARGET_TOLERANCE_DAYS = 8
LABELS_ALL = config.LABELS_DIR / "labels_all.parquet"


def wide(positions: pd.DataFrame, col: str = "bank_pos_m") -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    """transect x pass matrix of ``col`` with columns sorted by date."""
    w = positions.pivot_table(index="transect_id", columns="date", values=col, aggfunc="first")
    w = w.reindex(sorted(w.columns), axis=1)
    return w, pd.DatetimeIndex(w.columns)


def forward_confirmed(B: np.ndarray, dates: pd.DatetimeIndex, days: int = CONFIRM_DAYS) -> np.ndarray:
    """b*(t) = nanmin of b over passes in [t, t + days]; NaN where b(t) itself is NaN."""
    out = np.full_like(B, np.nan, dtype=float)
    d = dates.values
    for j in range(B.shape[1]):
        k = np.flatnonzero((d >= d[j]) & (d <= d[j] + np.timedelta64(days, "D")))
        with np.errstate(all="ignore"):
            out[:, j] = np.nanmin(B[:, k], axis=1)
    out[np.isnan(B)] = np.nan
    return out


def target_index(dates: pd.DatetimeIndex, horizon: int = config.HORIZON_DAYS,
                 tol: int = TARGET_TOLERANCE_DAYS) -> np.ndarray:
    """For each pass j, the index of the pass nearest dates[j] + horizon (or -1)."""
    d = dates.values
    out = np.full(len(d), -1)
    for j in range(len(d)):
        tgt = d[j] + np.timedelta64(horizon, "D")
        k = int(np.argmin(np.abs(d - tgt)))
        if k > j and abs((d[k] - tgt) / np.timedelta64(1, "D")) <= tol:
            out[j] = k
    return out


def make_labels(positions: pd.DataFrame, threshold_m: float | None = None) -> pd.DataFrame:
    threshold_m = threshold_m if threshold_m is not None else label_threshold_m()
    W, dates = wide(positions)
    B = W.to_numpy(dtype=float)
    Bc = forward_confirmed(B, dates)
    tix = target_index(dates)
    recs = []
    for j, k in enumerate(tix):
        if k < 0:
            continue
        R = Bc[:, k] - Bc[:, j]
        ok = np.isfinite(R)
        recs.append(pd.DataFrame({
            "transect_id": W.index[ok],
            "forecast_date": dates[j],
            "target_date": dates[k],
            "retreat_m": R[ok],
            "y": (R[ok] >= threshold_m).astype(np.int8),
            "major": (R[ok] >= config.MAJOR_EVENT_M).astype(np.int8),
        }))
    lab = pd.concat(recs, ignore_index=True)
    lab["year"] = lab["forecast_date"].dt.year
    lab.attrs["threshold_m"] = threshold_m
    return lab


def split(lab: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "train": lab[lab["year"].isin(config.TRAIN_YEARS)],
        "val": lab[lab["year"] == config.VAL_YEAR],
        "test": lab[lab["year"].isin(config.TEST_YEARS)],
    }


def main() -> None:
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    logging.basicConfig(level=logging.INFO)
    lab = make_labels(load_positions())
    config.LABELS_DIR.mkdir(parents=True, exist_ok=True)
    lab.to_parquet(LABELS_ALL, index=False)
    parts = split(lab)
    names = {"train": "train_2015_2021", "val": "val_2022", "test": "test_2023_2025"}
    stats = {"threshold_m": lab.attrs["threshold_m"], "confirm_days": CONFIRM_DAYS}
    for k, df in parts.items():
        df.to_parquet(config.LABELS_DIR / f"{names[k]}.parquet", index=False)
        stats[k] = dict(rows=int(len(df)), forecast_dates=int(df["forecast_date"].nunique()),
                        positive_rate=float(df["y"].mean()) if len(df) else None,
                        major_events=int(df["major"].sum()))
    (config.METRICS_DIR / "label_stats.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
