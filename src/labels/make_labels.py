"""Training labels: did segment s permanently lose land within 28 days?

Spec §Method 3 defines R_s(t1, t2) = b_s(t2) - b_s(t1) and
y_s(t) = 1[R_s(t, t + 28 d) >= threshold]. Two things in the real archive
force a more careful version (found on 2015-2017 training data, before any
test-year result existed — see docs/VALIDATION.md):

* **Single-pass flips.** A narrow side channel can open or close between
  passes, so the traced bank jumps between discrete positions.
* **Inundation.** In June-August, low land next to the bank floods and the
  water edge moves landward by hundreds of metres; it comes back in
  September-November. That is not erosion.

So the label compares robust positions and requires the loss to persist:

    b0  = median of b over the passes in [t - 24 d, t]              (as at the forecast)
    b1  = median of b over the passes within +-12 d of t_target     (t_target = pass nearest t + 28 d, +-8 d)
    bp  = 25th percentile of b over the passes in [t_target, t_target + 180 d]   (>= 4 passes)
    R   = b1 - b0                     observed retreat in the window
    P   = bp - b0                     retreat that is still there through the next low water
    y   = 1[ R >= thr  and  P >= thr ]          thr = max(20 m, 2 x median bank error)
    major = 1[ R >= 100 m and P >= 100 m ]
    retreat_m = min(R, P)

The 180-day window always contains low-water passes, so flooded margins
drop out. Labels may use future passes; features never do
(``tests/test_no_leakage.py``). The cost: forecasts in the last ~6 months of
the archive have no label yet, and erosion of a low bank that is already
flooded at the forecast date can be missed (conservative).

CLI::

    python -m src.labels.make_labels
"""
from __future__ import annotations

import argparse
import json
import logging
import warnings

import numpy as np
import pandas as pd

from src import config
from src.banks.bank_position import load_positions
from src.masks.validate_masks import label_threshold_m

log = logging.getLogger(__name__)

START_WINDOW_DAYS = 24
TARGET_HALF_WINDOW_DAYS = 12
PERMANENCE_DAYS = 180
PERMANENCE_QUANTILE = 25
PERMANENCE_MIN_PASSES = 4
TARGET_TOLERANCE_DAYS = 8
LABELS_ALL = config.LABELS_DIR / "labels_all.parquet"


def wide(positions: pd.DataFrame, col: str = "bank_pos_m") -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    """transect x pass matrix of ``col`` with columns sorted by date."""
    w = positions.pivot_table(index="transect_id", columns="date", values=col, aggfunc="first")
    w = w.reindex(sorted(w.columns), axis=1)
    return w, pd.DatetimeIndex(w.columns)


def window_stat(B: np.ndarray, sel: np.ndarray, stat: str, min_n: int = 1) -> np.ndarray:
    """Row-wise statistic of B over the selected passes, NaN where fewer than ``min_n`` are valid."""
    v = B[:, sel]
    out = np.full(B.shape[0], np.nan)
    if v.shape[1] == 0:
        return out
    n = np.isfinite(v).sum(axis=1)
    ok = n >= min_n
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        if stat == "median":
            out[ok] = np.nanmedian(v[ok], axis=1)
        elif stat == "q25":
            out[ok] = np.nanpercentile(v[ok], PERMANENCE_QUANTILE, axis=1)
        else:
            raise ValueError(stat)
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


def label_components(B: np.ndarray, dates: pd.DatetimeIndex, j: int, k: int) -> tuple[np.ndarray, ...]:
    """(b0, b1, bp) for forecast pass j and target pass k."""
    d = dates.values
    day = np.timedelta64(1, "D")
    b0 = window_stat(B, (d <= d[j]) & (d >= d[j] - START_WINDOW_DAYS * day), "median")
    b1 = window_stat(B, np.abs(d - d[k]) <= TARGET_HALF_WINDOW_DAYS * day, "median")
    bp = window_stat(B, (d >= d[k]) & (d <= d[k] + PERMANENCE_DAYS * day), "q25", PERMANENCE_MIN_PASSES)
    return b0, b1, bp


def make_labels(positions: pd.DataFrame, threshold_m: float | None = None) -> pd.DataFrame:
    threshold_m = threshold_m if threshold_m is not None else label_threshold_m()
    W, dates = wide(positions)
    B = W.to_numpy(dtype=float)
    tix = target_index(dates)
    recs = []
    for j, k in enumerate(tix):
        if k < 0:
            continue
        b0, b1, bp = label_components(B, dates, j, k)
        R, P = b1 - b0, bp - b0
        ok = np.isfinite(R) & np.isfinite(P) & np.isfinite(B[:, j])
        recs.append(pd.DataFrame({
            "transect_id": W.index[ok],
            "forecast_date": dates[j],
            "target_date": dates[k],
            "retreat_m": np.minimum(R, P)[ok],
            "window_retreat_m": R[ok],
            "permanent_retreat_m": P[ok],
            "y": ((R >= threshold_m) & (P >= threshold_m))[ok].astype(np.int8),
            "major": ((R >= config.MAJOR_EVENT_M) & (P >= config.MAJOR_EVENT_M))[ok].astype(np.int8),
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
    stats = {"threshold_m": lab.attrs["threshold_m"], "permanence_days": PERMANENCE_DAYS,
             "permanence_quantile": PERMANENCE_QUANTILE, "start_window_days": START_WINDOW_DAYS,
             "target_half_window_days": TARGET_HALF_WINDOW_DAYS}
    for k, df in parts.items():
        df.to_parquet(config.LABELS_DIR / f"{names[k]}.parquet", index=False)
        stats[k] = dict(rows=int(len(df)), forecast_dates=int(df["forecast_date"].nunique()),
                        positive_rate=float(df["y"].mean()) if len(df) else None,
                        major_events=int(df["major"].sum()))
    (config.METRICS_DIR / "label_stats.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
