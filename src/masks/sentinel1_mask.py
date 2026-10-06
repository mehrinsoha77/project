"""Water masks from Sentinel-1 sigma0 (one mask per pass).

Method (spec §Method 2):
* VV backscatter in dB, Lee-filtered (done at ingestion, see ``s1_io``);
* per-scene Otsu threshold on VV — calm water is dark in VV;
* VH as a second check: wind-roughened water can look bright in VV but stays
  dark in VH, so a pixel is also water if VH is below its own Otsu threshold
  and VV is within ``VH_RESCUE_MARGIN_DB`` of the VV threshold;
* morphological opening, then removal of water blobs and land specks smaller
  than 0.5 ha.

Output: uint8 GeoTIFF on the reach grid, 0 = land, 1 = water, 255 = no data.

CLI::

    python -m src.masks.sentinel1_mask --catalog data/processed/s1_catalog.json --workers 4
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from scipy import ndimage
from skimage.filters import threshold_otsu
from skimage.morphology import remove_small_holes, remove_small_objects

from src import config
from src.geo import reach_grid
from src.masks import s1_io

log = logging.getLogger(__name__)

# Plausible Otsu ranges. Outside them the histogram is not bimodal water/land
# (e.g. a scene with almost no water or with heavy wind); the pass is flagged.
VV_OTSU_RANGE = (-22.0, -11.0)
VH_OTSU_RANGE = (-28.0, -16.0)
VV_FALLBACK, VH_FALLBACK = -15.0, -21.0


@dataclass
class MaskInfo:
    pass_id: str
    date: str
    platform: str
    coverage: float
    t_vv: float
    t_vh: float
    otsu_ok: bool
    water_fraction: float
    water_area_km2: float
    vh_rescued_fraction: float


def otsu_db(db: np.ndarray, lo: float = -30.0, hi: float = 0.0, sample: int = 4) -> float:
    v = db[::sample, ::sample]
    v = v[np.isfinite(v) & (v > lo) & (v < hi)]
    if v.size < 1000:
        return float("nan")
    return float(threshold_otsu(v, nbins=256))


def classify(vv: np.ndarray, vh: np.ndarray) -> tuple[np.ndarray, dict]:
    """Return (mask, details). Pure function: tested in tests/test_masks.py."""
    valid = np.isfinite(vv)
    t_vv, t_vh = otsu_db(vv), otsu_db(vh, lo=-35.0, hi=-5.0)
    ok = (VV_OTSU_RANGE[0] <= t_vv <= VV_OTSU_RANGE[1]) and (VH_OTSU_RANGE[0] <= t_vh <= VH_OTSU_RANGE[1])
    if not (VV_OTSU_RANGE[0] <= t_vv <= VV_OTSU_RANGE[1]):
        t_vv = VV_FALLBACK
    if not (VH_OTSU_RANGE[0] <= t_vh <= VH_OTSU_RANGE[1]):
        t_vh = VH_FALLBACK
    with np.errstate(invalid="ignore"):
        dark_vv = vv < t_vv
        rescued = (vh < t_vh) & (vv < t_vv + config.VH_RESCUE_MARGIN_DB) & ~dark_vv
    water = (dark_vv | rescued) & valid
    water = ndimage.binary_opening(water, structure=np.ones((3, 3), bool))
    water = remove_small_objects(water, max_size=config.MIN_WATER_BLOB_PX)
    land = remove_small_objects(~water & valid, max_size=config.MIN_LAND_BLOB_PX)
    water = valid & ~land
    mask = np.where(valid, water.astype(np.uint8), 255).astype(np.uint8)
    n_valid = max(int(valid.sum()), 1)
    return mask, dict(t_vv=float(t_vv), t_vh=float(t_vh), otsu_ok=bool(ok),
                      vh_rescued_fraction=float(rescued.sum() / n_valid))


def mask_path(pass_id: str) -> Path:
    return config.MASK_DIR / f"mask_{pass_id}.tif"


def write_mask(mask: np.ndarray, path: Path, tags: dict) -> None:
    g = reach_grid()
    profile = dict(driver="GTiff", width=g.width, height=g.height, count=1, dtype="uint8",
                   crs=g.crs, transform=g.transform, nodata=255, tiled=True,
                   blockxsize=512, blockysize=512, compress="deflate", zlevel=9)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.tif")
    with rasterio.open(tmp, "w", **profile) as ds:
        ds.write(mask, 1)
        ds.update_tags(**{k: str(v) for k, v in tags.items()})
    tmp.replace(path)


def read_mask(path: Path) -> np.ndarray:
    with rasterio.open(path) as ds:
        return ds.read(1)


def mask_from_cache(db_path: Path) -> tuple[np.ndarray, MaskInfo]:
    vv, vh, tags = s1_io.read_pass_db(db_path)
    mask, d = classify(vv, vh)
    valid = mask != 255
    wf = float((mask == 1).sum() / max(valid.sum(), 1))
    info = MaskInfo(pass_id=tags["pass_id"], date=tags["date"], platform=tags["platform"],
                    coverage=float(valid.mean()), t_vv=d["t_vv"], t_vh=d["t_vh"], otsu_ok=d["otsu_ok"],
                    water_fraction=wf,
                    water_area_km2=float((mask == 1).sum() * config.REACH.pixel_m ** 2 / 1e6),
                    vh_rescued_fraction=d["vh_rescued_fraction"])
    return mask, info


def run_one(p: s1_io.Pass, keep_db: bool = True, overwrite: bool = False) -> MaskInfo | None:
    out = mask_path(p.pass_id)
    info_path = out.with_suffix(".json")
    if out.exists() and info_path.exists() and not overwrite:
        return MaskInfo(**json.loads(info_path.read_text()))
    try:
        db_path = s1_io.process_pass(p)
    except Exception as e:  # network or product problems: record and move on
        log.error("%s failed: %s", p.pass_id, e)
        return None
    if db_path is None:
        return None
    mask, info = mask_from_cache(db_path)
    write_mask(mask, out, asdict(info))
    info_path.write_text(json.dumps(asdict(info)))
    if not keep_db:
        db_path.unlink(missing_ok=True)
    return info


def run_all(catalog: Path, workers: int = 4, keep_db: bool = True, overwrite: bool = False,
            years: list[int] | None = None) -> pd.DataFrame:
    passes = s1_io.load_catalog(catalog)
    if years:
        passes = [p for p in passes if int(p.date[:4]) in years]
    log.info("processing %d passes with %d workers", len(passes), workers)
    infos = []
    with cf.ProcessPoolExecutor(workers) as ex:
        futs = {ex.submit(run_one, p, keep_db, overwrite): p for p in passes}
        for i, f in enumerate(cf.as_completed(futs)):
            info = f.result()
            if info:
                infos.append(asdict(info))
            if i % 20 == 0:
                log.info("%d / %d", i + 1, len(passes))
    df = pd.DataFrame(infos).sort_values("date").reset_index(drop=True)
    summary = config.MASK_DIR / "mask_summary.csv"
    if summary.exists() and years:
        old = pd.read_csv(summary)
        df = pd.concat([old[~old.pass_id.isin(df.pass_id)], df]).sort_values("date").reset_index(drop=True)
    df.to_csv(summary, index=False)
    return df


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", type=Path, default=config.PROCESSED / "s1_catalog.json")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--years", type=int, nargs="*")
    ap.add_argument("--drop-db", action="store_true", help="delete the cached dB rasters after masking")
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config.ensure_dirs()
    df = run_all(a.catalog, a.workers, keep_db=not a.drop_db, overwrite=a.overwrite, years=a.years)
    print(df.describe())


if __name__ == "__main__":
    main()
