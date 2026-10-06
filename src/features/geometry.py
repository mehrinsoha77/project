"""Geometric features that are not tied to a single pass.

* ``baseline_curvature`` – signed curvature of the fixed baseline at each
  transect (1/km). Positive = the bank is concave seen from the river (an
  outer bend), where flow tends to attack the bank.
* ``bank_height_m`` (optional) – Copernicus DEM GLO-30 elevation 50–300 m
  landward of the current bank, minus the DEM's median over the river part of
  the same transect. The DEM was acquired 2011–2015 (TanDEM-X), before any
  forecast date in the test period, so it carries no future information about
  the test years. It is a coarse proxy: 30 m pixels, ~2–4 m vertical noise.
* neighbour helpers: values of nearby segments on the same bank.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.warp import Resampling, reproject

from src import config
from src.banks.transects import load_transects, sample_index
from src.geo import reach_grid
from src.masks.s1_io import GDAL_ENV

log = logging.getLogger(__name__)

DEM_URL = ("/vsicurl/https://copernicus-dem-30m.s3.amazonaws.com/"
           "Copernicus_DSM_COG_10_N24_00_E089_00_DEM/Copernicus_DSM_COG_10_N24_00_E089_00_DEM.tif")
DEM_PATH = config.RAW / "dem" / "copdem_glo30_reach.tif"


def baseline_curvature(transects: pd.DataFrame, half_window: int = 5) -> pd.Series:
    """Signed curvature (1/km) of the baseline, from transect normals.

    Uses the rotation of the landward normal along the bank: if normals
    converge landward the bank is concave (outer bend).
    """
    out = pd.Series(np.nan, index=transects.index, name="baseline_curvature")
    for bank, g in transects.groupby("bank"):
        g = g.sort_values("chainage_m")
        ang = np.unwrap(np.arctan2(g["ny"].to_numpy(), g["nx"].to_numpy()))
        ch = g["chainage_m"].to_numpy() / 1000.0
        k = np.full(len(g), np.nan)
        for i in range(len(g)):
            a, b = max(i - half_window, 0), min(i + half_window, len(g) - 1)
            if b > a:
                k[i] = (ang[b] - ang[a]) / (ch[b] - ch[a])
        # normals rotating towards each other landward -> concave bank.
        # For the west bank (normal = tangent rotated clockwise) a concave bank
        # has the normal turning counter-clockwise along the north->south line.
        sign = 1.0 if bank == "W" else -1.0
        out.loc[g.index] = sign * k
    return out


def fetch_dem(path: Path = DEM_PATH) -> Path:
    if path.exists():
        return path
    g = reach_grid()
    dst = np.full(g.shape, np.nan, np.float32)
    with rasterio.Env(**GDAL_ENV):
        with rasterio.open(DEM_URL) as src:
            reproject(rasterio.band(src, 1), dst, src_transform=src.transform, src_crs=src.crs,
                      dst_transform=g.transform, dst_crs=g.crs, resampling=Resampling.bilinear,
                      dst_nodata=np.nan)
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", width=g.width, height=g.height, count=1, dtype="float32",
                       crs=g.crs, transform=g.transform, nodata=np.nan, compress="deflate", tiled=True,
                       predictor=3) as ds:
        ds.write(dst, 1)
    return path


def bank_height(positions: pd.DataFrame) -> pd.Series:
    """Height proxy for every (transect, pass) row in ``positions``."""
    try:
        with rasterio.open(fetch_dem()) as ds:
            dem = ds.read(1)
    except Exception as e:  # optional feature: never block the pipeline
        log.warning("DEM unavailable (%s); bank_height_m left empty", e)
        return pd.Series(np.nan, index=positions.index, name="bank_height_m")
    tr = load_transects()
    rows, cols, s = sample_index(tr)
    Z = dem[rows, cols]                                   # (n_transects, n_samples)
    tid_index = {t: i for i, t in enumerate(tr["transect_id"])}
    step = s[1] - s[0]
    i = positions["transect_id"].map(tid_index).to_numpy()
    b = positions["bank_pos_m"].to_numpy()
    out = np.full(len(positions), np.nan)
    ok = np.isfinite(b)
    for r in np.flatnonzero(ok):
        j = int(round((b[r] - s[0]) / step))
        land = Z[i[r], j + 5: j + 31]
        river = Z[i[r], max(j - 200, 0): max(j - 20, 0)]
        if land.size and river.size and np.isfinite(land).any() and np.isfinite(river).any():
            out[r] = np.nanmean(land) - np.nanmedian(river)
    return pd.Series(out, index=positions.index, name="bank_height_m")


def neighbour_mean(df: pd.DataFrame, col: str, k: int = 3, exclude_self: bool = True) -> pd.Series:
    """Mean of ``col`` over the k segments either side on the same bank, per forecast date.

    ``df`` must contain bank, chainage_m, forecast_date and ``col``.
    """
    out = pd.Series(np.nan, index=df.index)
    for (_, _), g in df.groupby(["bank", "forecast_date"]):
        g = g.sort_values("chainage_m")
        v = g[col].to_numpy(dtype=float)
        n = len(v)
        csum = np.concatenate([[0.0], np.nancumsum(v)])
        ccnt = np.concatenate([[0], np.cumsum(np.isfinite(v))])
        lo = np.clip(np.arange(n) - k, 0, n)
        hi = np.clip(np.arange(n) + k + 1, 0, n)
        s = csum[hi] - csum[lo]
        c = (ccnt[hi] - ccnt[lo]).astype(float)
        if exclude_self:
            fin = np.isfinite(v)
            s = s - np.where(fin, v, 0.0)
            c = c - fin
        with np.errstate(invalid="ignore", divide="ignore"):
            out.loc[g.index] = np.where(c > 0, s / c, np.nan)
    return out
