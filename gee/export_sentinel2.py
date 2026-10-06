"""Cloud-free Sentinel-2 water masks on Earth Engine, for validating the radar masks.

Alternative to ``src/masks/validate_masks.py`` (which reads Sentinel-2 L2A
COGs from the public AWS bucket and was used for the committed results).
Not used to produce any number in this repository.

Usage::

    python gee/export_sentinel2.py --dates 2023-01-14 2023-02-08 --bucket <gcs-bucket>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config  # noqa: E402
from src.geo import reach_grid  # noqa: E402


def mndwi_mask(ee, date: str, aoi):
    d0 = ee.Date(date)
    img = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(aoi)
           .filterDate(d0, d0.advance(1, "day")).mosaic())
    scl = img.select("SCL")
    bad = scl.eq(0).Or(scl.eq(1)).Or(scl.eq(3)).Or(scl.eq(8)).Or(scl.eq(9)).Or(scl.eq(10))
    mndwi = img.normalizedDifference(["B3", "B11"])
    return mndwi.gt(0).updateMask(bad.Not()).rename("water").toByte()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dates", nargs="+", required=True)
    ap.add_argument("--bucket")
    ap.add_argument("--drive", action="store_true")
    ap.add_argument("--project")
    a = ap.parse_args()
    import ee

    ee.Initialize(project=a.project)
    aoi = ee.Geometry.Rectangle(list(config.REACH.bbox_lonlat))
    g = reach_grid()
    transform = [g.transform.a, 0, g.transform.c, 0, g.transform.e, g.transform.f]
    for d in a.dates:
        kw = dict(image=mndwi_mask(ee, d, aoi), description=f"nadinet_s2_{d}", crs=g.crs, crsTransform=transform,
                  dimensions=f"{g.width}x{g.height}", maxPixels=1e10)
        task = (ee.batch.Export.image.toDrive(folder="nadinet_s2", **kw) if a.drive else
                ee.batch.Export.image.toCloudStorage(bucket=a.bucket, fileNamePrefix=f"nadinet/s2/s2_{d}", **kw))
        task.start()
        print("started", d)


if __name__ == "__main__":
    main()
