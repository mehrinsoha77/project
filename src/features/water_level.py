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

from src import config


def stage_from_positions(positions: pd.DataFrame) -> pd.DataFrame:
    """One row per pass: date, stage proxy (km^2)."""
    s = (positions.groupby("date", as_index=False)
         .agg(stage_km2=("belt_water_km2", "first"), coverage=("coverage", "first")))
    return s.sort_values("date").reset_index(drop=True)


def climatology(stage: pd.DataFrame, years: tuple[int, ...] = config.TRAIN_YEARS) -> pd.Series:
    """Mean stage by day-of-year from *training years only*, smoothed over +-30 days."""
    s = stage[stage["date"].dt.year.isin(years)]
    doy = s["date"].dt.dayofyear.to_numpy()
    v = s["stage_km2"].to_numpy()
    grid = np.arange(1, 367)
    clim = []
    for d in grid:
        dd = np.minimum(np.abs(doy - d), 366 - np.abs(doy - d))
        w = dd <= 30
        clim.append(np.nanmean(v[w]) if w.any() else np.nan)
    return pd.Series(clim, index=grid, name="stage_clim_km2")


def stage_features(stage: pd.DataFrame, clim: pd.Series) -> pd.DataFrame:
    """As-of features at each pass date, using only passes at or before it."""
    s = stage.sort_values("date").reset_index(drop=True)
    d = s["date"].values
    v = s["stage_km2"].to_numpy()
    out = []
    for j in range(len(s)):
        def back(days: int) -> float:
            tgt = d[j] - np.timedelta64(days, "D")
            k = np.flatnonzero(d <= d[j])
            k = k[np.argmin(np.abs(d[k] - tgt))]
            gap = abs((d[k] - tgt) / np.timedelta64(1, "D"))
            return v[k] if (k != j and gap <= 8) else np.nan
        doy = pd.Timestamp(d[j]).dayofyear
        out.append(dict(
            date=pd.Timestamp(d[j]), stage_km2=v[j],
            stage_change_12d=v[j] - back(12), stage_change_24d=v[j] - back(24),
            stage_anom_km2=v[j] - clim.loc[min(doy, 366)],
        ))
    return pd.DataFrame(out)


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
