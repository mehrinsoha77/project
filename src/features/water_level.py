"""River stage for the features: rising or falling river (spec §Method 4).

What the spec asked for, and what this build actually uses
----------------------------------------------------------
The spec names FFWC gauge levels (Sirajganj, Bahadurabad) with GloFAS as
backup. Neither was reachable from the build environment (ffwc.gov.bd and the
Copernicus CDS / Open-Meteo flood API were blocked), so the committed results
use a **radar-derived stage proxy** instead:

    stage_km2(t) = open water inside the braid belt on pass t (km^2)

As the Jamuna rises, chars drown and channels widen, so in-belt water area
tracks stage. It is measured on the same passes as the banks, so it only
uses data up to the forecast date. It is *not* a forecast: no archived
water-level forecasts are used anywhere (spec §Validation, "No leakage").

If you obtain FFWC or GloFAS series, drop a CSV with columns
``date,value`` into ``data/raw/ffwc/<station>.csv`` (daily water level in m)
or ``data/raw/ffwc/glofas_discharge.csv`` (m^3/s) and pass
``--stage-source ffwc`` / ``glofas`` to ``build_features``; the loaders below
turn them into the same as-of features.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def stage_from_positions(positions: pd.DataFrame) -> pd.DataFrame:
    """One row per pass: date, stage proxy (km^2)."""
    s = positions.groupby("date", as_index=False).agg(stage_km2=("belt_water_km2", "first"))
    return s.sort_values("date").reset_index(drop=True)


def _back_index(d: np.ndarray, j: int, days: int, tol: int) -> int:
    """Index of the pass (<= j) nearest to d[j] - days, or -1 if none within tol days."""
    tgt = d[j] - np.timedelta64(days, "D")
    i = int(np.argmin(np.abs(d[: j + 1] - tgt)))
    if i == j or abs((d[i] - tgt) / np.timedelta64(1, "D")) > tol:
        return -1
    return i


def asof_stage_features(stage: pd.DataFrame) -> pd.DataFrame:
    """Stage features at each pass using only passes at or before it.

    * ``stage_km2`` – in-belt open water on the pass;
    * ``stage_change_12d`` / ``_24d`` – change since the pass ~12 / ~24 days earlier
      (rising or falling river);
    * ``stage_anom_km2`` – departure from an *as-of* climatology: the mean stage of
      earlier passes (at least 180 days earlier) within +-30 days of the same day of
      year; needs >= 3 such passes, else NaN.
    """
    s = stage.sort_values("date").reset_index(drop=True)
    d = s["date"].values
    v = s["stage_km2"].to_numpy(dtype=float)
    doy = s["date"].dt.dayofyear.to_numpy()
    rows = []
    for j in range(len(s)):
        k12 = _back_index(d, j, 12, 8)
        k24 = _back_index(d, j, 24, 8)
        prior = np.arange(j)
        dd = np.abs(doy[prior] - doy[j])
        dd = np.minimum(dd, 366 - dd)
        older = prior[(dd <= 30) & ((d[j] - d[prior]) > np.timedelta64(180, "D"))]
        clim = np.nanmean(v[older]) if len(older) >= 3 else np.nan
        rows.append(dict(date=s["date"].iloc[j], stage_km2=v[j],
                         stage_change_12d=v[j] - v[k12] if k12 >= 0 else np.nan,
                         stage_change_24d=v[j] - v[k24] if k24 >= 0 else np.nan,
                         stage_anom_km2=v[j] - clim))
    return pd.DataFrame(rows)


def load_series_csv(path: Path) -> pd.Series:
    df = pd.read_csv(path, parse_dates=["date"]).sort_values("date")
    return df.set_index("date")["value"]


def gauge_features(series: pd.Series, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """As-of gauge features (level, 7-day change) for each forecast date."""
    s = series.sort_index()
    rows = []
    for t in dates:
        hist = s[:t]
        if hist.empty:
            rows.append(dict(date=t, gauge=np.nan, gauge_change_7d=np.nan))
            continue
        now = hist.iloc[-1]
        past = s[: t - pd.Timedelta(days=7)]
        rows.append(dict(date=t, gauge=now, gauge_change_7d=now - past.iloc[-1] if len(past) else np.nan))
    return pd.DataFrame(rows)
