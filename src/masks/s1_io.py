"""Sentinel-1 GRD access without Earth Engine.

Reads Level-1 GRD products from the public ``sentinel-s1-l1c`` bucket on AWS
(Copernicus data, converted by Sinergise to tiled GeoTIFFs with GCPs). Only the
window covering the reach is fetched, over HTTP range requests.

Processing per pass (one relative orbit, one datatake):

1. find the slice(s) whose footprint intersects the reach;
2. read the VV (10 m) and VH (20 m overview) window around the reach;
3. calibrate DN to sigma0 with the product's own sigmaNought LUT;
4. apply a Lee speckle filter in radar geometry;
5. geocode onto the fixed reach grid by inverting the product's GCP grid
   (a bicubic spline through the 21 x 10 tie points, solved by Newton steps);
6. store VV and VH sigma0 in dB, quantised to uint8, as one GeoTIFF per pass.

Known simplifications (documented in docs/LIMITATIONS.md):
* no thermal-noise removal (matters mostly for VH over water, which is only a
  secondary check here);
* no radiometric terrain flattening (the reach is a flat floodplain);
* geolocation relies on the GCP grid, which is ellipsoid-plus-coarse-DEM based.
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.windows import Window
from scipy import ndimage
from scipy.interpolate import RectBivariateSpline
from shapely.geometry import box, shape

from src import config
from src.geo import Grid, reach_grid, to_lonlat

log = logging.getLogger(__name__)

GDAL_ENV = dict(
    GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
    CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tiff,.tif",
    GDAL_HTTP_MULTIRANGE="YES",
    GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES",
    GDAL_HTTP_MAX_RETRY="6",
    GDAL_HTTP_RETRY_DELAY="3",
    VSI_CACHE="TRUE",
    VSI_CACHE_SIZE=str(64 * 1024 * 1024),
)

_session = requests.Session()


def _get(url: str, **kw) -> requests.Response:
    for attempt in range(6):
        try:
            r = _session.get(url, timeout=90, **kw)
            if r.status_code in (500, 502, 503, 504):
                raise requests.HTTPError(f"{r.status_code}")
            return r
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError):
            if attempt == 5:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------

@dataclass
class Slice:
    product_id: str
    prefix: str
    platform: str
    start: str
    stop: str
    absolute_orbit: int
    relative_orbit: int
    datatake: int
    footprint: dict


@dataclass
class Pass:
    """All slices of one datatake that touch the reach (usually one or two)."""

    date: str               # UTC date of acquisition, YYYY-MM-DD
    platform: str
    relative_orbit: int
    slices: list[Slice] = field(default_factory=list)

    @property
    def pass_id(self) -> str:
        return f"{self.date.replace('-', '')}_{self.platform}"


def _list_prefixes(prefix: str) -> list[str]:
    out, token = [], None
    while True:
        params = {"list-type": "2", "prefix": prefix, "delimiter": "/", "max-keys": "1000"}
        if token:
            params["continuation-token"] = token
        text = _get(config.S1_BUCKET_URL, params=params).text
        out += re.findall(r"<Prefix>([^<]*)</Prefix>", text)[1:]
        m = re.search(r"<NextContinuationToken>([^<]*)<", text)
        if not m:
            return out
        token = m.group(1)


def relative_orbit_from_manifest(prefix: str) -> int:
    text = _get(f"{config.S1_BUCKET_URL}/{prefix}manifest.safe").text
    m = re.search(r'relativeOrbitNumber type="start">(\d+)<', text)
    if not m:
        raise ValueError(f"no relative orbit in manifest for {prefix}")
    return int(m.group(1))


def _candidates_for_day(day: dt.date) -> list[str]:
    lo, hi = config.S1_PASS_UTC_WINDOW
    lo_s, hi_s = lo.replace(":", ""), hi.replace(":", "")
    pref = f"GRD/{day.year}/{day.month}/{day.day}/IW/DV/"
    out = []
    for p in _list_prefixes(pref):
        name = p.rstrip("/").split("/")[-1]
        hhmmss = name.split("_")[4][9:15]
        if lo_s.ljust(6, "0") <= hhmmss <= hi_s.ljust(6, "0")[:6]:
            out.append(p)
    return out


def _slice_if_intersecting(prefix: str, aoi) -> Slice | None:
    info = _get(f"{config.S1_BUCKET_URL}/{prefix}productInfo.json")
    if info.status_code != 200:
        return None
    j = info.json()
    fp = shape(j["footprint"])
    if not fp.intersects(aoi):
        return None
    rel = relative_orbit_from_manifest(prefix)
    return Slice(
        product_id=j["id"], prefix=prefix, platform=j["missionId"],
        start=j["startTime"], stop=j["stopTime"],
        absolute_orbit=int(j["absoluteOrbitNumber"]), relative_orbit=rel,
        datatake=int(j["missionDataTakeId"]), footprint=j["footprint"],
    )


def build_catalog(start: str = config.S1_START, end: str = config.S1_END,
                  relative_orbit: int = config.S1_RELATIVE_ORBIT,
                  workers: int = 16, out: Path | None = None) -> list[Pass]:
    """Scan every day in [start, end] for slices of ``relative_orbit`` over the reach."""
    aoi = box(*config.REACH.bbox_lonlat)
    d0, d1 = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    days = [d0 + dt.timedelta(days=i) for i in range((d1 - d0).days + 1)]
    with cf.ThreadPoolExecutor(workers) as ex:
        cands = [p for ps in ex.map(_candidates_for_day, days) for p in ps]
    log.info("%d candidate slices in the UTC window", len(cands))
    with cf.ThreadPoolExecutor(workers) as ex:
        slices = [s for s in ex.map(lambda p: _slice_if_intersecting(p, aoi), cands) if s]
    slices = [s for s in slices if s.relative_orbit == relative_orbit]
    passes: dict[tuple[str, int], Pass] = {}
    for s in sorted(slices, key=lambda s: s.start):
        key = (s.platform, s.datatake)
        if key not in passes:
            passes[key] = Pass(date=s.start[:10], platform=s.platform, relative_orbit=s.relative_orbit)
        passes[key].slices.append(s)
    result = sorted(passes.values(), key=lambda p: p.date)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps([{**asdict(p), "pass_id": p.pass_id} for p in result], indent=1))
    return result


def load_catalog(path: Path) -> list[Pass]:
    raw = json.loads(path.read_text())
    return [Pass(date=p["date"], platform=p["platform"], relative_orbit=p["relative_orbit"],
                 slices=[Slice(**s) for s in p["slices"]]) for p in raw]


# ---------------------------------------------------------------------------
# Calibration and geocoding
# ---------------------------------------------------------------------------

def read_sigma_lut(prefix: str, pol: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (lines, pixels, sigmaNought[line, pixel]) from the calibration XML."""
    xml = _get(f"{config.S1_BUCKET_URL}/{prefix}annotation/calibration/calibration-iw-{pol}.xml").text
    root = ET.fromstring(xml)
    lines, pixels, vals = [], None, []
    for v in root.iter("calibrationVector"):
        lines.append(int(v.find("line").text))
        px = np.array(v.find("pixel").text.split(), dtype=np.int64)
        sg = np.array(v.find("sigmaNought").text.split(), dtype=np.float64)
        if pixels is None:
            pixels = px
        n = min(len(px), len(pixels))
        vals.append(np.interp(pixels, px[:n], sg[:n]))
    lines = np.array(lines)
    order = np.argsort(lines)
    lines, vals = lines[order], np.array(vals)[order]
    keep = np.concatenate([[True], np.diff(lines) > 0])  # duplicate lines happen at slice edges
    return lines[keep], pixels, vals[keep]


def lee_filter(intensity: np.ndarray, valid: np.ndarray, size: int, enl: float = 4.4) -> np.ndarray:
    """Classic Lee filter on linear intensity; nodata pixels are ignored (float32 throughout)."""
    img = np.where(valid, intensity, 0.0).astype(np.float32)
    cnt = ndimage.uniform_filter(valid.astype(np.float32), size)
    cnt[cnt <= 0] = np.nan
    mean = ndimage.uniform_filter(img, size) / cnt
    var = ndimage.uniform_filter(img * img, size) / cnt
    var -= mean * mean
    np.maximum(var, 0.0, out=var)
    cu2 = np.float32(1.0 / enl)
    var_x = np.maximum((var - mean * mean * cu2) / (1.0 + cu2), 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        k = np.where(var > 0, var_x / var, 0.0).astype(np.float32)
    del var, var_x, cnt
    out = mean + k * (img - mean)
    out[~valid] = np.nan
    return out.astype(np.float32)


class GcpModel:
    """Smooth (line, pixel) <-> (lon, lat) mapping from a regular GCP grid."""

    def __init__(self, gcps):
        rows = np.array(sorted({round(g.row) for g in gcps}), dtype=float)
        cols = np.array(sorted({round(g.col) for g in gcps}), dtype=float)
        lon = np.full((len(rows), len(cols)), np.nan)
        lat = np.full_like(lon, np.nan)
        ri = {r: i for i, r in enumerate(rows)}
        ci = {c: i for i, c in enumerate(cols)}
        for g in gcps:
            lon[ri[round(g.row)], ci[round(g.col)]] = g.x
            lat[ri[round(g.row)], ci[round(g.col)]] = g.y
        if np.isnan(lon).any():
            raise ValueError("GCPs do not form a full regular grid")
        k = 3 if min(len(rows), len(cols)) >= 4 else 1
        self.rows, self.cols = rows, cols
        self.slon = RectBivariateSpline(rows, cols, lon, kx=k, ky=k)
        self.slat = RectBivariateSpline(rows, cols, lat, kx=k, ky=k)
        # Affine first guess for the inverse
        R, C = np.meshgrid(rows, cols, indexing="ij")
        A = np.c_[lon.ravel(), lat.ravel(), np.ones(lon.size)]
        self._inv = np.linalg.lstsq(A, np.c_[R.ravel(), C.ravel()], rcond=None)[0]

    def inverse(self, lon: np.ndarray, lat: np.ndarray, iters: int = 6) -> tuple[np.ndarray, np.ndarray]:
        A = np.c_[lon.ravel(), lat.ravel(), np.ones(lon.size)]
        rc = A @ self._inv
        r, c = rc[:, 0], rc[:, 1]
        for _ in range(iters):
            f1 = self.slon.ev(r, c) - lon.ravel()
            f2 = self.slat.ev(r, c) - lat.ravel()
            a = self.slon.ev(r, c, dx=1); b = self.slon.ev(r, c, dy=1)
            cc = self.slat.ev(r, c, dx=1); d = self.slat.ev(r, c, dy=1)
            det = a * d - b * cc
            r = r - (d * f1 - b * f2) / det
            c = c - (-cc * f1 + a * f2) / det
        return r.reshape(lon.shape), c.reshape(lon.shape)


COARSE_STEP = 16


def coarse_radar_coords(model: GcpModel, grid: Grid, step: int = COARSE_STEP) -> tuple[np.ndarray, np.ndarray]:
    """Fractional (line, pixel) in the slice on a coarse subset of ``grid`` (every ``step`` px)."""
    rr = np.arange(0, grid.height + step, step)
    cc = np.arange(0, grid.width + step, step)
    R, C = np.meshgrid(rr, cc, indexing="ij")
    x, y = grid.xy_of(R, C)
    lon, lat = to_lonlat(x, y, grid.crs)
    return model.inverse(np.asarray(lon), np.asarray(lat))


def upsample_rows(coarse: np.ndarray, r0: int, r1: int, width: int, step: int = COARSE_STEP) -> np.ndarray:
    """Bilinear upsampling of a smooth coarse map for full-grid rows [r0, r1)."""
    fr = (np.arange(r0, r1, dtype=np.float32) / step)
    fc = (np.arange(width, dtype=np.float32) / step)
    FR, FC = np.meshgrid(fr, fc, indexing="ij")
    return ndimage.map_coordinates(coarse, [FR, FC], order=1).astype(np.float32)


def _read_slice(sl: Slice, grid: Grid, chunk: int = 512) -> dict[str, np.ndarray] | None:
    """Calibrated, speckle-filtered sigma0 (linear) for one slice on ``grid``; NaN outside."""
    url = f"/vsicurl/{config.S1_BUCKET_URL}/{sl.prefix}measurement/iw-%s.tiff"
    with rasterio.Env(**GDAL_ENV):
        with rasterio.open(url % "vv") as src:
            gcps, _ = src.gcps
            model = GcpModel(gcps)
            lr_c, lc_c = coarse_radar_coords(model, grid)
            H, W = src.height, src.width
            ins = (lr_c >= 0) & (lr_c <= H - 1) & (lc_c >= 0) & (lc_c <= W - 1)
            if ins.sum() < 4:
                return None
            r0 = int(max(np.floor(lr_c[ins].min()) - 64, 0))
            r1 = int(min(np.ceil(lr_c[ins].max()) + 64, H))
            c0 = int(max(np.floor(lc_c[ins].min()) - 64, 0))
            c1 = int(min(np.ceil(lc_c[ins].max()) + 64, W))
            r1 = r0 + 2 * ((r1 - r0) // 2)
            c1 = c0 + 2 * ((c1 - c0) // 2)
            vv = src.read(1, window=Window(c0, r0, c1 - c0, r1 - r0)).astype(np.float32)
        with rasterio.open(url % "vh") as src:
            # VH from the 2x overview: it is only a secondary check
            vh = src.read(1, window=Window(c0, r0, c1 - c0, r1 - r0),
                          out_shape=((r1 - r0) // 2, (c1 - c0) // 2)).astype(np.float32)

    filtered = {}
    for pol, dn, factor in (("vv", vv, 1), ("vh", vh, 2)):
        lines, pixels, lut = read_sigma_lut(sl.prefix, pol)
        rows = r0 + factor * np.arange(dn.shape[0]) + (factor - 1) / 2
        cols = c0 + factor * np.arange(dn.shape[1]) + (factor - 1) / 2
        spl = RectBivariateSpline(lines, pixels, lut, kx=1, ky=1)
        A = spl(np.clip(rows, lines[0], lines[-1]), np.clip(cols, pixels[0], pixels[-1])).astype(np.float32)
        valid = dn > 0
        sigma0 = np.where(valid, dn * dn / (A * A), np.nan).astype(np.float32)
        del A
        filtered[pol] = (lee_filter(sigma0, valid, config.LEE_WINDOW if factor == 1 else 3), factor)
        del sigma0, valid
    del vv, vh

    out = {pol: np.full(grid.shape, np.nan, np.float32) for pol in filtered}
    for a in range(0, grid.height, chunk):
        b = min(a + chunk, grid.height)
        line = upsample_rows(lr_c, a, b, grid.width)
        pix = upsample_rows(lc_c, a, b, grid.width)
        inside = (line >= 0) & (line <= H - 1) & (pix >= 0) & (pix <= W - 1)
        if not inside.any():
            continue
        for pol, (img, factor) in filtered.items():
            lr = (line - r0 - (factor - 1) / 2) / factor
            lc = (pix - c0 - (factor - 1) / 2) / factor
            g = ndimage.map_coordinates(img, [lr, lc], order=1, cval=np.nan, prefilter=False)
            g[~inside] = np.nan
            out[pol][a:b] = g
    return out


def to_db(x: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return 10.0 * np.log10(np.where(x > 0, x, np.nan))


def quantise_db(db: np.ndarray) -> np.ndarray:
    q = np.round((np.clip(db, config.DB_MIN, config.DB_MAX) - config.DB_MIN)
                 / (config.DB_MAX - config.DB_MIN) * 254.0)
    q = np.where(np.isfinite(db), q, 255)
    return q.astype(np.uint8)


def dequantise_db(q: np.ndarray) -> np.ndarray:
    db = q.astype(np.float32) / 254.0 * (config.DB_MAX - config.DB_MIN) + config.DB_MIN
    db[q == 255] = np.nan
    return db


def pass_path(p: Pass) -> Path:
    return config.S1_RAW / f"S1_{p.pass_id}_r{p.relative_orbit:03d}.tif"


def process_pass(p: Pass, grid: Grid | None = None, overwrite: bool = False) -> Path | None:
    """Fetch, calibrate, filter and geocode one pass; write a 2-band uint8 dB GeoTIFF."""
    grid = grid or reach_grid()
    dst = pass_path(p)
    if dst.exists() and not overwrite:
        return dst
    t0 = time.time()
    vv = np.full(grid.shape, np.nan, np.float32)
    vh = np.full(grid.shape, np.nan, np.float32)
    for sl in p.slices:
        res = _read_slice(sl, grid)
        if res is None:
            continue
        fill = np.isnan(vv) & np.isfinite(res["vv"])
        vv[fill] = res["vv"][fill]
        vh[fill] = res["vh"][fill]
    coverage = float(np.isfinite(vv).mean())
    if coverage < 0.05:
        log.warning("%s: no usable coverage", p.pass_id)
        return None
    dst.parent.mkdir(parents=True, exist_ok=True)
    profile = dict(driver="GTiff", width=grid.width, height=grid.height, count=2, dtype="uint8",
                   crs=grid.crs, transform=grid.transform, nodata=255, tiled=True,
                   blockxsize=512, blockysize=512, compress="deflate", predictor=2, zlevel=6)
    tmp = dst.with_suffix(".tmp.tif")
    with rasterio.open(tmp, "w", **profile) as ds:
        ds.write(quantise_db(to_db(vv)), 1)
        ds.write(quantise_db(to_db(vh)), 2)
        ds.set_band_description(1, "sigma0_VV_dB_q")
        ds.set_band_description(2, "sigma0_VH_dB_q")
        ds.update_tags(pass_id=p.pass_id, date=p.date, platform=p.platform,
                       relative_orbit=str(p.relative_orbit),
                       products=",".join(s.product_id for s in p.slices),
                       coverage=f"{coverage:.4f}",
                       db_quantisation=f"db = q/254*({config.DB_MAX}-{config.DB_MIN})+{config.DB_MIN}; 255=nodata")
    tmp.replace(dst)
    log.info("%s done in %.1fs (coverage %.2f)", p.pass_id, time.time() - t0, coverage)
    return dst


def read_pass_db(path: Path) -> tuple[np.ndarray, np.ndarray, dict]:
    with rasterio.open(path) as ds:
        vv = dequantise_db(ds.read(1))
        vh = dequantise_db(ds.read(2))
        tags = ds.tags()
    return vv, vh, tags
