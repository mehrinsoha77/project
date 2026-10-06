"""Estimate the terrain-height correction for Sentinel-1 geolocation (run once per track).

Why: the GCP grid of every descending track-150 product places the reach at
~60 m above the WGS84 ellipsoid. The floodplain really lies below the
ellipsoid (geoid undulation here is roughly -45 m), so every pass is drawn
~100 m too far from the sensor (west). A constant terrain height fixes this.

How (calibration pairs only, 2017-2019):
1. build radar masks for the dry-season passes of 2017-2019 with the height
   correction switched OFF (``NADINET_TERRAIN_H`` unset -> NaN -> skipped);
2. for each pass with a cloud-free Sentinel-2 scene within 2 days, measure
   the per-transect bank-position difference radar - optical (active channel);
3. project it on the look direction: shift = median(diff / (n . u_look));
4. convert the median shift to a terrain height:
   H = h_gcp - shift * tan(theta), with h_gcp and theta from the annotation.

The validation in ``src/masks/validate_masks.py`` is then reported on pairs
from 2020-2025, which played no part in this estimate.

Usage::

    python scripts/estimate_geolocation_offset.py --uncorrected-masks <dir>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.interpolate import RectBivariateSpline  # noqa: E402

from src import config  # noqa: E402
from src.banks.transects import load_transects, sample_index  # noqa: E402
from src.geo import reach_grid  # noqa: E402
from src.masks import s1_io  # noqa: E402
from src.masks import validate_masks as vm  # noqa: E402
from src.masks.sentinel1_mask import read_mask  # noqa: E402

LOOK_AZIMUTH_DEG = 280.4   # pixel (range) direction of track 150 over the reach, from the GCP grid


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--uncorrected-masks", type=Path, required=True,
                    help="folder with mask_<pass>.tif/.json built with the correction off")
    ap.add_argument("--max-pairs", type=int, default=8)
    a = ap.parse_args()
    infos = [json.loads(p.read_text()) for p in sorted(a.uncorrected_masks.glob("mask_*.json"))]
    summary = pd.DataFrame(infos)
    summary = summary[summary["date"] < "2020-01-01"]
    pairs = vm.find_pairs(summary, a.max_pairs)
    tr = load_transects()
    rows, cols, s = sample_index(tr)
    az = np.radians(LOOK_AZIMUTH_DEG)
    proj = tr["nx"].to_numpy() * np.sin(az) + tr["ny"].to_numpy() * np.cos(az)
    shifts = []
    for _, p in pairs.iterrows():
        _, s2c = vm.s2_masks(p["s2_prefix"])
        s1 = read_mask(a.uncorrected_masks / f"mask_{p['pass_id']}.tif")
        r = vm.compare(s1, s2c, s2c, rows, cols, s)
        d = r["_diff"]
        ok = np.isfinite(d) & (np.abs(proj) > 0.5) & (np.abs(d) < 400)
        shifts.append(float(np.median(d[ok] / proj[ok])))
        print(p["pass_id"], p["s2_id"], f"shift {shifts[-1]:.1f} m ({ok.sum()} transects)")
    shift = float(np.median(shifts))
    cat = json.loads((config.PROCESSED / "s1_catalog.json").read_text())
    sl = next(x for x in cat if x["date"] >= "2018-11-01")["slices"][0]
    geo = s1_io.read_geolocation_grid(sl["prefix"])
    import rasterio
    with rasterio.Env(**s1_io.GDAL_ENV), rasterio.open(
            f"/vsicurl/{config.S1_BUCKET_URL}/{sl['prefix']}measurement/iw-vv.tiff") as src:
        model = s1_io.GcpModel(src.gcps[0])
    lr, lc = s1_io.coarse_radar_coords(model, reach_grid(), step=256)
    si = RectBivariateSpline(geo["lines"], geo["pixels"], geo["incidence"], kx=1, ky=1)
    sh = RectBivariateSpline(geo["lines"], geo["pixels"], geo["height"], kx=1, ky=1)
    ok = (lr > 0) & (lc > 0)
    theta = float(np.median(si.ev(lr[ok], lc[ok])))
    h_gcp = float(np.median(sh.ev(lr[ok], lc[ok])))
    H = h_gcp - shift * np.tan(np.radians(theta))
    out = dict(pairs=pairs["pass_id"].tolist(), shifts_m=shifts, median_shift_m=shift, incidence_deg=theta,
               gcp_height_m=h_gcp, terrain_height_ellipsoid_m=round(H, 1))
    (config.METRICS_DIR / "geolocation_offset.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    print(f"\nSet S1_TERRAIN_HEIGHT_ELLIPSOID_M = {H:.1f} in src/config.py")


if __name__ == "__main__":
    main()
