"""Sentinel-1 water masks on Google Earth Engine — the alternative ingestion path.

The committed results were produced WITHOUT Earth Engine, from the public
Sentinel-1 archive on AWS (``src/masks/s1_io.py`` + ``src/masks/sentinel1_mask.py``),
because the build environment had no Earth Engine credentials. This script
implements the same method on Earth Engine for teams that have an account
(free for research and education; commercial use needs a licence). It has
not been used to produce any number in this repository.

Differences you should expect versus the AWS path:
* EE's COPERNICUS/S1_GRD is already calibrated, thermal-noise-removed and
  terrain-corrected (SRTM 30 m), so absolute dB values differ slightly;
* EE resamples to its own 10 m grid; exports here are reprojected to the
  reach grid (EPSG:32645, same origin as ``src.geo.reach_grid``).

Usage::

    earthengine authenticate
    python gee/export_masks.py --start 2015-01-01 --end 2025-12-31 --bucket <gcs-bucket>   # or --drive
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config  # noqa: E402
from src.geo import reach_grid  # noqa: E402


def build(ee, start: str, end: str):
    aoi = ee.Geometry.Rectangle(list(config.REACH.bbox_lonlat), proj="EPSG:4326", geodesic=False)
    col = (ee.ImageCollection("COPERNICUS/S1_GRD")
           .filterBounds(aoi)
           .filterDate(start, end)
           .filter(ee.Filter.eq("instrumentMode", "IW"))
           .filter(ee.Filter.eq("orbitProperties_pass", "DESCENDING"))
           .filter(ee.Filter.eq("relativeOrbitNumber_start", config.S1_RELATIVE_ORBIT))
           .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
           .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH")))
    # one image per datatake/day: mosaic slices of the same date
    days = col.aggregate_array("system:time_start").map(lambda t: ee.Date(t).format("YYYY-MM-dd")).distinct()

    def per_day(d):
        d0 = ee.Date.parse("YYYY-MM-dd", d)
        img = col.filterDate(d0, d0.advance(1, "day")).mosaic().clip(aoi)
        # simple boxcar in linear power (EE has no Lee filter built in; refinedLee is available in community code)
        lin = ee.Image(10).pow(img.select(["VV", "VH"]).divide(10))
        lin = lin.focal_mean(radius=config.LEE_WINDOW // 2, kernelType="square", units="pixels")
        db = lin.log10().multiply(10)
        vv, vh = db.select("VV"), db.select("VH")

        def otsu(band, lo, hi, fallback):
            hist = band.reduceRegion(ee.Reducer.histogram(255, 0.1), aoi, 30, maxPixels=1e9).get(band.bandNames().get(0))
            return ee.Algorithms.If(hist, _otsu(ee, ee.Dictionary(hist)), fallback)

        t_vv = ee.Number(otsu(vv.clamp(-30, 0), -30, 0, -15.0))
        t_vh = ee.Number(otsu(vh.clamp(-35, -5), -35, -5, -21.0))
        water = vv.lt(t_vv).Or(vh.lt(t_vh).And(vv.lt(t_vv.add(config.VH_RESCUE_MARGIN_DB))))
        water = water.focal_min(1).focal_max(1)                      # opening
        water = water.updateMask(water.connectedPixelCount(100).gte(config.MIN_WATER_BLOB_PX).Or(water.Not()))
        return (water.rename("water").toByte()
                .set({"date": d, "t_vv": t_vv, "t_vh": t_vh, "system:time_start": d0.millis()}))

    return ee.ImageCollection(days.map(per_day)), aoi


def _otsu(ee, hist):
    counts = ee.Array(hist.get("histogram"))
    means = ee.Array(hist.get("bucketMeans"))
    size = means.length().get([0])
    total = counts.reduce(ee.Reducer.sum(), [0]).get([0])
    mean = counts.multiply(means).reduce(ee.Reducer.sum(), [0]).get([0]).divide(total)
    indices = ee.List.sequence(1, size)

    def bss(i):
        a = counts.slice(0, 0, i)
        ac = a.reduce(ee.Reducer.sum(), [0]).get([0])
        am = a.multiply(means.slice(0, 0, i)).reduce(ee.Reducer.sum(), [0]).get([0]).divide(ac)
        bc = total.subtract(ac)
        bm = total.multiply(mean).subtract(ac.multiply(am)).divide(bc)
        return ac.multiply(am.subtract(mean).pow(2)).add(bc.multiply(bm.subtract(mean).pow(2)))

    return means.sort(ee.Array(indices.map(bss))).get([-1])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default=config.S1_START)
    ap.add_argument("--end", default=config.S1_END)
    ap.add_argument("--bucket", help="GCS bucket for exports")
    ap.add_argument("--drive", action="store_true", help="export to Google Drive instead")
    ap.add_argument("--project", help="Earth Engine cloud project")
    a = ap.parse_args()
    import ee  # imported here so the rest of the repo never needs earthengine-api

    ee.Initialize(project=a.project)
    col, aoi = build(ee, a.start, a.end)
    g = reach_grid()
    transform = [g.transform.a, 0, g.transform.c, 0, g.transform.e, g.transform.f]
    dates = col.aggregate_array("date").getInfo()
    print(f"{len(dates)} passes on track {config.S1_RELATIVE_ORBIT}")
    for d in dates:
        img = col.filter(ee.Filter.eq("date", d)).first()
        kw = dict(image=img, description=f"nadinet_mask_{d}", crs=g.crs, crsTransform=transform,
                  dimensions=f"{g.width}x{g.height}", maxPixels=1e10, fileFormat="GeoTIFF")
        if a.drive:
            task = ee.batch.Export.image.toDrive(folder="nadinet_masks", **kw)
        else:
            task = ee.batch.Export.image.toCloudStorage(bucket=a.bucket, fileNamePrefix=f"nadinet/masks/mask_{d}", **kw)
        task.start()
        print("started", d)


if __name__ == "__main__":
    main()
