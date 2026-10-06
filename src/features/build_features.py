"""Feature table: one row per (segment, forecast date) — spec §Method 4.

A forecast is issued right after each radar pass, so forecast dates are pass
dates. **Every feature is as-of**: it is computed only from passes at or
before the forecast date. ``tests/test_no_leakage.py`` rebuilds the table from
positions truncated at random dates and fails if any value changes.

Bank positions for features are robust and strictly backward-looking:

    b0(t)   = median of b over passes in [t - 24 d, t]           (current bank, flips removed)
    perm(t) = 25th percentile of b over passes in [t - 180 d, t] (>= 4 passes; the
              "permanent" bank, with seasonally flooded margins removed)

The raw move on the newest pass is kept separately as ``raw_last_change_m``
(it drives the Monitor and Warning tiers). ``inundation_m`` = b0 - perm says
how far the current water edge sits landward of the permanent bank.

Feature groups (used by the ablation study):

========================  ====================================================
recent_retreat            ret_28_m, ret_56_m, ret_84_m (b0), raw_last_change_m
history                   ret_365_m (perm), n_obs_365
channel_geometry          dist_main_channel_m, d_dist_main_28_m,
                          near_channel_width_m, char_shield_frac,
                          nearbank_water_frac, baseline_curvature, embayment_m
water_level               stage_km2, stage_change_12d, stage_change_24d,
                          stage_anom_km2, inundation_m
season                    doy_sin, doy_cos
neighbours                nb_ret_84_m, nb_ret_365_m
bank_height (optional)    bank_height_m
coherence (optional)      not built — see docs/CLAIMS_LEDGER.md
========================  ====================================================

No location features (chainage, bank side) are given to the model, so it
cannot simply memorise hotspots; the spatial hold-out checks this.

CLI::

    python -m src.features.build_features
"""
from __future__ import annotations

import argparse
import logging

import numpy as np
import pandas as pd

from src import config
from src.banks.bank_position import load_positions
from src.banks.transects import load_transects
from src.features.geometry import bank_height, baseline_curvature, neighbour_mean
from src.features.water_level import _back_index, asof_stage_features, stage_from_positions
from src.labels.make_labels import window_stat

log = logging.getLogger(__name__)

FEATURES_PATH = config.FEATURE_DIR / "features.parquet"
CURRENT_WINDOW_DAYS = 24
PERMANENT_WINDOW_DAYS = 180

FEATURE_GROUPS: dict[str, list[str]] = {
    "recent_retreat": ["ret_28_m", "ret_56_m", "ret_84_m", "raw_last_change_m"],
    "history": ["ret_365_m", "n_obs_365"],
    "channel_geometry": ["dist_main_channel_m", "d_dist_main_28_m", "near_channel_width_m",
                         "char_shield_frac", "nearbank_water_frac", "baseline_curvature", "embayment_m"],
    "water_level": ["stage_km2", "stage_change_12d", "stage_change_24d", "stage_anom_km2", "inundation_m"],
    "season": ["doy_sin", "doy_cos"],
    "neighbours": ["nb_ret_84_m", "nb_ret_365_m"],
    "bank_height": ["bank_height_m"],
}
ALL_FEATURES = [f for g in FEATURE_GROUPS.values() for f in g]


def _pivot(pos: pd.DataFrame, col: str, tids: pd.Index, dates: pd.DatetimeIndex) -> np.ndarray:
    w = pos.pivot_table(index="transect_id", columns="date", values=col, aggfunc="first")
    return w.reindex(index=tids, columns=dates).to_numpy(dtype=float)


def build(positions: pd.DataFrame, transects: pd.DataFrame | None = None,
          with_bank_height: bool = True) -> pd.DataFrame:
    """Return the as-of feature table for every (transect, pass date)."""
    tr = (transects if transects is not None else load_transects()).copy()
    tr = tr.set_index("transect_id", drop=False)
    tr["baseline_curvature"] = baseline_curvature(tr.reset_index(drop=True)).to_numpy()
    pos = positions.copy()
    pos["date"] = pd.to_datetime(pos["date"])
    if with_bank_height and "bank_height_m" not in pos:
        pos["bank_height_m"] = bank_height(pos).to_numpy()
    elif "bank_height_m" not in pos:
        pos["bank_height_m"] = np.nan
    dates = pd.DatetimeIndex(sorted(pos["date"].unique()))
    tids = pd.Index(tr["transect_id"])
    d = dates.values

    B = _pivot(pos, "bank_pos_m", tids, dates)
    DM = _pivot(pos, "dist_main_channel_m", tids, dates)
    CW = _pivot(pos, "near_channel_width_m", tids, dates)
    CS = _pivot(pos, "char_shield_frac", tids, dates)
    NW = _pivot(pos, "nearbank_water_frac", tids, dates)
    BH = _pivot(pos, "bank_height_m", tids, dates)

    # robust, backward-looking positions (see module docstring)
    day = np.timedelta64(1, "D")
    B0 = np.full_like(B, np.nan)
    PERM = np.full_like(B, np.nan)
    for j in range(len(d)):
        B0[:, j] = window_stat(B, (d <= d[j]) & (d >= d[j] - CURRENT_WINDOW_DAYS * day), "median")
        PERM[:, j] = window_stat(B, (d <= d[j]) & (d >= d[j] - PERMANENT_WINDOW_DAYS * day), "q25", 4)
    has_now = np.isfinite(B)
    B0[~has_now] = np.nan   # a forecast needs an observation on its own pass

    stage = asof_stage_features(stage_from_positions(pos)[["date", "stage_km2"]])
    stage = stage.set_index("date")

    frames = []
    for j, t in enumerate(dates):
        f = pd.DataFrame({"transect_id": tids, "forecast_date": t})
        now = B0[:, j]
        for days, tol, name in ((28, 12, "ret_28_m"), (56, 12, "ret_56_m"), (84, 12, "ret_84_m")):
            k = _back_index(d, j, days, tol)
            f[name] = now - B0[:, k] if k >= 0 else np.nan
        k365 = _back_index(d, j, 365, 30)
        f["ret_365_m"] = PERM[:, j] - PERM[:, k365] if k365 >= 0 else np.nan
        f["inundation_m"] = now - PERM[:, j]
        kp = j - 1 if j > 0 and (d[j] - d[j - 1]) <= np.timedelta64(30, "D") else -1
        f["raw_last_change_m"] = B[:, j] - B[:, kp] if kp >= 0 else np.nan
        last_year = (d <= d[j]) & (d > d[j] - np.timedelta64(365, "D"))
        f["n_obs_365"] = np.isfinite(B[:, last_year]).sum(axis=1)
        f["dist_main_channel_m"] = DM[:, j]
        k28 = _back_index(d, j, 28, 12)
        f["d_dist_main_28_m"] = DM[:, j] - DM[:, k28] if k28 >= 0 else np.nan
        f["near_channel_width_m"] = CW[:, j]
        f["char_shield_frac"] = CS[:, j]
        f["nearbank_water_frac"] = NW[:, j]
        f["bank_height_m"] = BH[:, j]
        f["bank_pos_m"] = now
        f["raw_bank_pos_m"] = B[:, j]
        frames.append(f)
    X = pd.concat(frames, ignore_index=True)
    X = X[np.isfinite(X["bank_pos_m"])].reset_index(drop=True)

    meta = tr[["transect_id", "bank", "chainage_m", "baseline_curvature"]].reset_index(drop=True)
    X = X.merge(meta, on="transect_id", how="left")
    X["nb_ret_84_m"] = neighbour_mean(X, "ret_84_m").to_numpy()
    X["nb_ret_365_m"] = neighbour_mean(X, "ret_365_m").to_numpy()
    X["embayment_m"] = (X["bank_pos_m"] - neighbour_mean(X, "bank_pos_m", k=5)).to_numpy()
    X = X.merge(stage, left_on="forecast_date", right_index=True, how="left")
    doy = X["forecast_date"].dt.dayofyear
    X["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    X["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    X["year"] = X["forecast_date"].dt.year
    return X.sort_values(["forecast_date", "transect_id"]).reset_index(drop=True)


def load_features() -> pd.DataFrame:
    return pd.read_parquet(FEATURES_PATH)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-bank-height", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO)
    X = build(load_positions(), with_bank_height=not a.no_bank_height)
    config.FEATURE_DIR.mkdir(parents=True, exist_ok=True)
    X.to_parquet(FEATURES_PATH, index=False)
    print(X[ALL_FEATURES].describe().T[["count", "mean", "50%"]])


if __name__ == "__main__":
    main()
