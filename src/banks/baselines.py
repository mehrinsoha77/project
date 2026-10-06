"""Draw one fixed baseline per mainland bank (spec §Method 3).

The baseline is built once, from the earliest passes in the archive (the
first 12 months of the training period), and never moved. Bank positions in
every later pass are measured along transects cast perpendicular to it, as in
the USGS Digital Shoreline Analysis System (DSAS).

Construction:
1. braid belt per pass (``belt.river_belt``) for every pass in the first
   12 months;
2. pixels inside the belt on at least half of those passes form the
   reference belt;
3. for every grid row, take the westernmost and easternmost reference-belt
   pixel (the reach runs roughly north–south);
4. smooth each edge with a 1.5 km Gaussian and store it as a LineString.

CLI::

    python -m src.banks.baselines
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy import ndimage
from shapely.geometry import LineString

from src import config
from src.banks.belt import _large_components, river_belt
from src.geo import reach_grid
from src.masks.sentinel1_mask import mask_path, read_mask

log = logging.getLogger(__name__)

BASELINE_PATH = config.BANK_DIR / "baselines.geojson"
SMOOTH_SIGMA_M = 1500.0
END_TRIM_M = 1000.0      # drop the first/last km where the reach box cuts the river


def reference_belt(pass_ids: list[str], min_share: float = 0.5) -> np.ndarray:
    g = reach_grid()
    count = np.zeros(g.shape, np.uint16)
    seen = np.zeros(g.shape, np.uint16)
    for pid in pass_ids:
        m = read_mask(mask_path(pid))
        count += river_belt(m).astype(np.uint16)
        seen += (m != 255).astype(np.uint16)
    ref = (count >= np.maximum(1, min_share * seen)) & (seen > 0)
    ref = ndimage.binary_fill_holes(np.pad(ref, ((1, 1), (0, 0)), constant_values=True))[1:-1]
    return _large_components(ref, int(5e6 / config.REACH.pixel_m ** 2))


def edges_from_belt(ref: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-row westmost/eastmost belt column (NaN where the row has no belt)."""
    any_ = ref.any(axis=1)
    west = np.where(any_, ref.argmax(axis=1), np.nan).astype(float)
    east = np.where(any_, ref.shape[1] - 1 - ref[:, ::-1].argmax(axis=1), np.nan).astype(float)
    rows = np.arange(ref.shape[0], dtype=float)
    return rows, west, east


def smooth_line(rows: np.ndarray, cols: np.ndarray, sigma_px: float) -> tuple[np.ndarray, np.ndarray]:
    ok = np.isfinite(cols)
    r, c = rows[ok], cols[ok]
    c = ndimage.gaussian_filter1d(c, sigma_px, mode="nearest")
    return r, c


def build_baselines(pass_ids: list[str]) -> gpd.GeoDataFrame:
    g = reach_grid()
    ref = reference_belt(pass_ids)
    rows, west, east = edges_from_belt(ref)
    sigma = SMOOTH_SIGMA_M / g.transform.a
    trim = int(END_TRIM_M / g.transform.a)
    feats = []
    for bank, cols in (("W", west), ("E", east)):
        r, c = smooth_line(rows, cols, sigma)
        r, c = r[trim:-trim:10], c[trim:-trim:10]
        x, y = g.xy_of(r, c)
        feats.append({"bank": bank, "geometry": LineString(list(zip(x, y)))})
    gdf = gpd.GeoDataFrame(feats, crs=g.crs)
    gdf["source_passes"] = ",".join(pass_ids)
    return gdf


def first_year_passes(summary: pd.DataFrame, months: int = 12) -> list[str]:
    s = summary.sort_values("date")
    t0 = pd.Timestamp(s["date"].iloc[0])
    sel = s[(pd.to_datetime(s["date"]) < t0 + pd.DateOffset(months=months)) & (s["coverage"] > 0.95)]
    return sel["pass_id"].tolist()


def load_baselines(path: Path = BASELINE_PATH) -> gpd.GeoDataFrame:
    return gpd.read_file(path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--months", type=int, default=12)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO)
    summary = pd.read_csv(config.MASK_DIR / "mask_summary.csv")
    pids = first_year_passes(summary, a.months)
    log.info("baseline from %d passes: %s .. %s", len(pids), pids[0], pids[-1])
    gdf = build_baselines(pids)
    config.BANK_DIR.mkdir(parents=True, exist_ok=True)
    gdf.to_file(BASELINE_PATH, driver="GeoJSON")
    print(json.dumps({"passes": len(pids), "lengths_km": (gdf.length / 1000).round(2).tolist()}))


if __name__ == "__main__":
    main()
