"""Check radar water masks against cloud-free Sentinel-2 (spec §Method 2, "Check").

For each Sentinel-1 pass, look for a Sentinel-2 L2A scene of tile 45RYH
(covers the reach north of ~24.30 N) acquired within ``MAX_DAYS`` days, with
scene cloud cover below ``MAX_CLOUD``. Sentinel-2 L2A Cloud-Optimised GeoTIFFs
are read from the public ``sentinel-cogs`` bucket (Element 84 / AWS Open Data).

Optical water mask: MNDWI = (B03 - B11) / (B03 + B11) > 0, with B11 (20 m)
bilinearly resampled to 10 m; pixels flagged by the scene classification
(SCL) as cloud, cirrus, cloud shadow, saturated or no data are excluded.

Reported per pair and in aggregate:
* water IoU over pixels valid in both masks;
* bank-position error: the same transect / belt procedure run on both masks,
  absolute difference per transect, median over transects.

The result also sets the label threshold: ``max(20 m, 2 x median error)``.

CLI::

    python -m src.masks.validate_masks --max-pairs 16
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.warp import Resampling, reproject
from skimage.morphology import remove_small_objects

from src import config
from src.banks.bank_position import positions_for_mask
from src.banks.transects import load_transects, sample_index
from src.geo import reach_grid
from src.masks.s1_io import GDAL_ENV
from src.masks.sentinel1_mask import mask_path, read_mask

log = logging.getLogger(__name__)

S2_BUCKET = "https://sentinel-cogs.s3.us-west-2.amazonaws.com"
S2_TILES = ["45/R/YH"]
MAX_DAYS = 2
MAX_CLOUD = 5.0
DRY_MONTHS = (11, 12, 1, 2, 3, 4)
SCL_BAD = {0, 1, 3, 8, 9, 10}  # nodata, saturated, cloud shadow, cloud medium/high, cirrus
OUT_JSON = config.METRICS_DIR / "mask_validation.json"
OUT_CSV = config.METRICS_DIR / "mask_validation_pairs.csv"


def list_s2_items(tile: str, year: int, month: int) -> list[str]:
    url = f"{S2_BUCKET}/?list-type=2&prefix=sentinel-s2-l2a-cogs/{tile}/{year}/{month}/&delimiter=/&max-keys=1000"
    text = requests.get(url, timeout=60).text
    return re.findall(r"<Prefix>([^<]*L2A/)</Prefix>", text)


def item_meta(prefix: str) -> dict | None:
    iid = prefix.rstrip("/").split("/")[-1]
    r = requests.get(f"{S2_BUCKET}/{prefix}{iid}.json", timeout=60)
    if r.status_code != 200:
        return None
    p = r.json()["properties"]
    return dict(prefix=prefix, id=iid, datetime=p["datetime"], cloud=float(p.get("eo:cloud_cover", 100)),
                nodata=float(p.get("s2:nodata_pixel_percentage", 100)))


def find_pairs(summary: pd.DataFrame, max_pairs: int) -> pd.DataFrame:
    s1 = summary[summary["coverage"] > 0.95].copy()
    s1["d"] = pd.to_datetime(s1["date"])
    s1 = s1[s1["d"].dt.month.isin(DRY_MONTHS) & (s1["d"].dt.year >= 2017)]
    months = sorted({(d.year, d.month) for d in s1["d"]})
    items = []
    for tile in S2_TILES:
        for y, m in months:
            for pref in list_s2_items(tile, y, m):
                meta = item_meta(pref)
                if meta and meta["cloud"] <= MAX_CLOUD and meta["nodata"] < 20:
                    items.append(meta)
    s2 = pd.DataFrame(items)
    if s2.empty:
        return s2
    s2["d"] = pd.to_datetime(s2["datetime"]).dt.tz_localize(None).dt.normalize()
    rows = []
    for _, r in s1.iterrows():
        dd = (s2["d"] - r["d"]).dt.days.abs()
        c = s2[dd <= MAX_DAYS].assign(dd=dd[dd <= MAX_DAYS]).sort_values(["dd", "cloud"])
        if len(c):
            b = c.iloc[0]
            rows.append(dict(pass_id=r["pass_id"], s1_date=r["date"], s2_id=b["id"], s2_prefix=b["prefix"],
                             s2_datetime=b["datetime"], days_apart=int(b["dd"]), s2_cloud=b["cloud"]))
    pairs = pd.DataFrame(rows).drop_duplicates("s2_id")
    # spread across years: round-robin by year
    pairs["year"] = pairs["s1_date"].str[:4]
    pairs = (pairs.sort_values(["days_apart", "s2_cloud"]).groupby("year", group_keys=False)
             .apply(lambda d: d.assign(rank=np.arange(len(d)))).sort_values(["rank", "year"]))
    return pairs.head(max_pairs).reset_index(drop=True)


def _read_to_grid(url: str, resampling: Resampling, dtype="float32") -> np.ndarray:
    g = reach_grid()
    dst = np.full(g.shape, np.nan if dtype == "float32" else 0, dtype=dtype)
    with rasterio.Env(**GDAL_ENV):
        with rasterio.open(url) as src:
            reproject(source=rasterio.band(src, 1), destination=dst, src_transform=src.transform,
                      src_crs=src.crs, src_nodata=0, dst_transform=g.transform, dst_crs=g.crs,
                      dst_nodata=np.nan if dtype == "float32" else 0, resampling=resampling)
    return dst


def s2_water_mask(prefix: str) -> np.ndarray:
    """0 land, 1 water, 255 invalid, on the reach grid."""
    base = f"/vsicurl/{S2_BUCKET}/{prefix}"
    b03 = _read_to_grid(base + "B03.tif", Resampling.nearest)
    b11 = _read_to_grid(base + "B11.tif", Resampling.bilinear)
    scl = _read_to_grid(base + "SCL.tif", Resampling.nearest, dtype="uint8")
    with np.errstate(invalid="ignore", divide="ignore"):
        mndwi = (b03 - b11) / (b03 + b11)
    valid = np.isfinite(mndwi) & ~np.isin(scl, list(SCL_BAD))
    water = (mndwi > 0.0) & valid
    water = remove_small_objects(water, max_size=config.MIN_WATER_BLOB_PX)
    land = remove_small_objects(~water & valid, max_size=config.MIN_LAND_BLOB_PX)
    water = valid & ~land
    return np.where(valid, water.astype(np.uint8), 255).astype(np.uint8)


def compare(s1: np.ndarray, s2: np.ndarray, rows, cols, s) -> dict:
    both = (s1 != 255) & (s2 != 255)
    a, b = (s1 == 1) & both, (s2 == 1) & both
    iou = float((a & b).sum() / max((a | b).sum(), 1))
    p1 = positions_for_mask(s1, rows, cols, s)["bank_pos_m"].to_numpy()
    # restrict the optical mask's valid area to where radar is valid too
    p2 = positions_for_mask(np.where(both, s2, 255).astype(np.uint8), rows, cols, s)["bank_pos_m"].to_numpy()
    diff = p1 - p2
    ok = np.isfinite(diff)
    return dict(iou=iou, valid_share=float(both.mean()), n_transects=int(ok.sum()),
                median_abs_err_m=float(np.median(np.abs(diff[ok]))) if ok.any() else float("nan"),
                p90_abs_err_m=float(np.percentile(np.abs(diff[ok]), 90)) if ok.any() else float("nan"),
                mean_signed_err_m=float(diff[ok].mean()) if ok.any() else float("nan"),
                _diff=diff)


def run(max_pairs: int = 16) -> dict:
    summary = pd.read_csv(config.MASK_DIR / "mask_summary.csv")
    pairs = find_pairs(summary, max_pairs)
    log.info("%d S1/S2 pairs", len(pairs))
    tr = load_transects()
    rows, cols, s = sample_index(tr)
    recs, diffs = [], []
    for _, p in pairs.iterrows():
        s1 = read_mask(mask_path(p["pass_id"]))
        s2 = s2_water_mask(p["s2_prefix"])
        r = compare(s1, s2, rows, cols, s)
        diffs.append(r.pop("_diff"))
        recs.append({**p.drop(labels=["s2_prefix"]).to_dict(), **r})
        log.info("%s vs %s: IoU %.3f, median |err| %.1f m over %d transects", p["pass_id"], p["s2_id"],
                 r["iou"], r["median_abs_err_m"], r["n_transects"])
        thumb = config.METRICS_DIR / "mask_pairs" / f"{p['pass_id']}__{p['s2_id']}.npz"
        thumb.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(thumb, s1=s1[::3, ::3], s2=s2[::3, ::3])
    df = pd.DataFrame(recs)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)
    all_d = np.concatenate(diffs)
    all_d = all_d[np.isfinite(all_d)]
    med = float(np.median(np.abs(all_d)))
    res = dict(
        n_pairs=int(len(df)), s2_tile="45RYH", max_days_apart=MAX_DAYS, max_cloud_pct=MAX_CLOUD,
        iou_median=float(df["iou"].median()), iou_min=float(df["iou"].min()), iou_max=float(df["iou"].max()),
        bank_error_median_m=med,
        bank_error_p90_m=float(np.percentile(np.abs(all_d), 90)),
        bank_error_mean_signed_m=float(all_d.mean()),
        n_transect_comparisons=int(all_d.size),
        label_threshold_m=float(max(config.RETREAT_THRESHOLD_FLOOR_M, 2 * med)),
        generated=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    )
    OUT_JSON.write_text(json.dumps(res, indent=2))
    return res


def label_threshold_m() -> float:
    """The retreat threshold used for labels: max(floor, 2 x measured median bank error)."""
    if OUT_JSON.exists():
        return float(json.loads(OUT_JSON.read_text())["label_threshold_m"])
    log.warning("mask validation not run yet; using the %.0f m floor", config.RETREAT_THRESHOLD_FLOOR_M)
    return config.RETREAT_THRESHOLD_FLOOR_M


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max-pairs", type=int, default=16)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(run(a.max_pairs), indent=2))


if __name__ == "__main__":
    main()
