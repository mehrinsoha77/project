"""Precompute everything the dashboard and the offline demo need.

Outputs
-------
data/demo/
    sirajganj_reach.geojson          reach box, baselines and transects (lon/lat)
    predictions_2022.parquet         calibration year (for tier thresholds / replay)
    predictions_2023..2025.parquet   held-out test years (+ the latest forecast)
app/public/data/                     the same content as static JSON for the web app
    reach.json, passes.json, metrics.json, banks/<year>.json,
    predictions/index.json, predictions/<date>.json, radar/<pass>.webp

Static JSON lets the dashboard run with no backend at all (Vercel-only or a
laptop with no network); FastAPI serves the same data plus the alert actions.

CLI::

    python -m src.api.export --images
"""
from __future__ import annotations

import argparse
import json
import logging
import math
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from affine import Affine
from PIL import Image
from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds
from rasterio.windows import from_bounds

from src import config
from src.alerts.send_alert import assign_tiers, tier_thresholds
from src.banks.bank_position import load_positions
from src.banks.baselines import load_baselines
from src.banks.belt import BRIDGE_LONLAT
from src.banks.transects import load_transects
from src.explain.shap_reasons import explain, global_importance
from src.features.build_features import load_features
from src.geo import reach_grid, to_lonlat
from src.labels.make_labels import LABELS_ALL
from src.masks.s1_io import GDAL_ENV
from src.models.calibrate import apply, load_calibrators
from src.models.train_lgbm import load_model, load_params

log = logging.getLogger(__name__)

APP_DATA = config.ROOT / "app" / "public" / "data"
REASONS_TOP = 40
IMAGE_YEARS = (2022, 2023, 2024, 2025)
IMAGE_PIXEL_M = 40.0


def _r(x, nd=1):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), nd)


def predictions_all(years: tuple[int, ...] = (config.VAL_YEAR, *config.TEST_YEARS)) -> pd.DataFrame:
    X = load_features()
    X = X[X["year"].isin(years)].copy()
    lab = pd.read_parquet(LABELS_ALL)[["transect_id", "forecast_date", "target_date", "retreat_m", "y", "major"]]
    X = X.merge(lab, on=["transect_id", "forecast_date"], how="left")
    model, info = load_model(), load_params()
    cals = load_calibrators()
    iso, fill = cals["M1_raw"]
    X["raw"] = model.predict(X[info["features"]])
    X["p"] = apply(iso, X["raw"], fill)
    biso, bfill = cals["B0_persistence"]
    X["b0_p"] = apply(biso, X["ret_84_m"], bfill)
    X = X.sort_values(["forecast_date", "p", "raw"], ascending=[True, False, False])
    X["rank"] = X.groupby("forecast_date").cumcount() + 1
    X = X.sort_values(["forecast_date", "ret_84_m"], ascending=[True, False], na_position="last")
    X["b0_rank"] = X.groupby("forecast_date").cumcount() + 1
    val = X[X["year"] == config.VAL_YEAR].rename(columns={"p": "M1"})
    stats = json.loads((config.METRICS_DIR / "label_stats.json").read_text())
    th = tier_thresholds(val.dropna(subset=["y"]), stats["threshold_m"])
    X["tier"] = assign_tiers(X, th)
    X["reasons"] = None
    top = X[X["rank"] <= REASONS_TOP]
    reasons = explain(model, top, info["features"])
    X.loc[top.index, "reasons"] = [json.dumps(r) for r in reasons]
    tr = load_transects()[["transect_id", "lon", "lat"]]
    X = X.merge(tr, on="transect_id", how="left")
    X.attrs["tier_thresholds"] = th.__dict__
    return X.sort_values(["forecast_date", "rank"]).reset_index(drop=True)


def save_predictions(pred: pd.DataFrame) -> None:
    config.DEMO_DIR.mkdir(parents=True, exist_ok=True)
    keep = ["transect_id", "forecast_date", "bank", "chainage_m", "lon", "lat", "p", "raw", "rank", "b0_rank",
            "b0_p", "tier", "reasons", "ret_28_m", "ret_84_m", "ret_365_m", "raw_last_change_m", "bank_pos_m",
            "dist_main_channel_m", "char_shield_frac", "target_date", "retreat_m", "y", "major"]
    for y, g in pred.groupby(pred["forecast_date"].dt.year):
        g[keep].to_parquet(config.DEMO_DIR / f"predictions_{y}.parquet", index=False)
    (config.DEMO_DIR / "tier_thresholds.json").write_text(json.dumps(pred.attrs.get("tier_thresholds", {}), indent=2))


def load_predictions() -> pd.DataFrame:
    parts = sorted(config.DEMO_DIR.glob("predictions_*.parquet"))
    df = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
    stats = config.METRICS_DIR / "label_stats.json"
    if stats.exists():
        df.attrs["threshold_m"] = json.loads(stats.read_text())["threshold_m"]
    return df


# ---------------------------------------------------------------------------
# static JSON for the web app
# ---------------------------------------------------------------------------

def reach_json() -> dict:
    g = reach_grid()
    tr = load_transects()
    sx = tr["x0"] - config.TRANSECT_RIVERWARD_M * tr["nx"]
    sy = tr["y0"] - config.TRANSECT_RIVERWARD_M * tr["ny"]
    ex = tr["x0"] + config.TRANSECT_LANDWARD_M * tr["nx"]
    ey = tr["y0"] + config.TRANSECT_LANDWARD_M * tr["ny"]
    slon, slat = to_lonlat(sx.to_numpy(), sy.to_numpy())
    elon, elat = to_lonlat(ex.to_numpy(), ey.to_numpy())
    transects = [dict(id=r.transect_id, bank=r.bank, chainage_m=round(r.chainage_m), lon=r.lon, lat=r.lat,
                      start=[round(a, 6), round(b, 6)], end=[round(c, 6), round(d, 6)],
                      near_bridge=bool(r.near_bridge))
                 for r, a, b, c, d in zip(tr.itertuples(), slon, slat, elon, elat)]
    bl = load_baselines().to_crs("EPSG:4326")
    return dict(
        name=config.REACH.name, crs=config.REACH.crs, pixel_m=config.REACH.pixel_m,
        bbox=list(config.REACH.bbox_lonlat),
        s_range=[-config.TRANSECT_RIVERWARD_M, config.TRANSECT_LANDWARD_M],
        transect_spacing_m=config.TRANSECT_SPACING_M,
        bridge=[[lon, lat] for lon, lat in BRIDGE_LONLAT],
        baselines={r.bank: [[round(x, 6), round(y, 6)] for x, y in r.geometry.coords] for r in bl.itertuples()},
        transects=transects,
        grid_size=[g.width, g.height],
    )


def passes_json(positions: pd.DataFrame, images: set[str]) -> list[dict]:
    summary = pd.read_csv(config.MASK_DIR / "mask_summary.csv")
    stage = positions.groupby("pass_id").agg(stage_km2=("belt_water_km2", "first"),
                                             valid_share=("bank_pos_m", lambda v: float(v.notna().mean())))
    s = summary.merge(stage, left_on="pass_id", right_index=True, how="left")
    out = []
    for r in s.sort_values("date").itertuples():
        out.append(dict(pass_id=r.pass_id, date=r.date, platform=r.platform, otsu_ok=bool(r.otsu_ok),
                        t_vv=_r(r.t_vv, 2), water_area_km2=_r(r.water_area_km2), stage_km2=_r(r.stage_km2),
                        valid_share=_r(r.valid_share, 3),
                        image=f"radar/{r.pass_id}.webp" if r.pass_id in images else None))
    return out


def banks_by_year(positions: pd.DataFrame) -> dict[int, dict]:
    pos = positions.copy()
    pos["year"] = pos["date"].dt.year
    tids = sorted(pos["transect_id"].unique())
    out = {}
    for y, g in pos.groupby("year"):
        w = g.pivot_table(index="transect_id", columns="pass_id", values="bank_pos_m", aggfunc="first")
        w = w.reindex(index=tids)
        cols = sorted(w.columns)
        out[int(y)] = dict(passes=cols, transects=tids,
                           pos=[[None if not np.isfinite(v) else int(round(v)) for v in w[c].to_numpy()] for c in cols])
    return out


def prediction_files(pred: pd.DataFrame) -> tuple[list[dict], dict[str, list[dict]]]:
    index, files = [], {}
    thr = json.loads((config.METRICS_DIR / "label_stats.json").read_text())["threshold_m"]
    for d, g in pred.groupby("forecast_date"):
        ds = d.strftime("%Y-%m-%d")
        has_outcome = bool(g["y"].notna().any())
        rows = []
        for r in g.itertuples():
            rows.append(dict(
                id=r.transect_id, p=_r(r.p, 4), rank=int(r.rank), b0_rank=int(r.b0_rank), tier=r.tier,
                ret28=_r(r.ret_28_m, 0), ret84=_r(r.ret_84_m, 0), ret365=_r(r.ret_365_m, 0),
                last=_r(r.raw_last_change_m, 0), pos=_r(r.bank_pos_m, 0),
                mon=bool(np.isfinite(r.raw_last_change_m) and r.raw_last_change_m >= thr),
                y=None if pd.isna(r.y) else int(r.y), retreat=_r(r.retreat_m, 0),
                major=None if pd.isna(r.major) else int(r.major),
                target=None if pd.isna(r.target_date) else r.target_date.strftime("%Y-%m-%d"),
                reasons=[x["text"] for x in json.loads(r.reasons)] if isinstance(r.reasons, str) else None,
            ))
        files[ds] = rows
        sub = g.dropna(subset=["y"])

        def p20(col: str, sub: pd.DataFrame = sub) -> float | None:
            top = sub.nsmallest(config.TOP_K, col)
            return _r(top["y"].mean(), 3) if len(sub) >= config.TOP_K else None
        index.append(dict(date=ds, year=int(d.year), split="val" if d.year == config.VAL_YEAR else "test",
                          n=int(len(g)), has_outcome=has_outcome,
                          p20_model=p20("rank") if has_outcome else None,
                          p20_persistence=p20("b0_rank") if has_outcome else None,
                          positives=int(sub["y"].sum()) if has_outcome else None))
    return index, files


def metrics_json(pred: pd.DataFrame | None) -> dict:
    m = {}
    for name in ("mask_validation", "label_stats", "test_results", "ablation", "calibration_val_2022",
                 "baselines_val_2022"):
        p = config.METRICS_DIR / f"{name}.json"
        if p.exists():
            m[name] = json.loads(p.read_text())
    p = config.PROCESSED / "models" / "m1_params.json"
    if p.exists():
        info = json.loads(p.read_text())
        m["model"] = {k: v for k, v in info.items() if k != "trials"}
    tt = config.DEMO_DIR / "tier_thresholds.json"
    if tt.exists():
        m["tier_thresholds"] = json.loads(tt.read_text())
    if "test_results" in m:   # drop the long per-date list; the per-date files carry it
        for part in ("temporal", "spatial"):
            for k in ("M1_minus_B0", "M1_minus_B1"):
                if k in m["test_results"].get(part, {}):
                    m["test_results"][part][k] = {kk: vv for kk, vv in m["test_results"][part][k].items()
                                                  if kk != "per_date"}
    cl = config.METRICS_DIR / "claims.json"
    if cl.exists():
        m["claims"] = json.loads(cl.read_text())
    gi = config.METRICS_DIR / "importance.json"
    if gi.exists():
        m["importance"] = json.loads(gi.read_text())
    return m


def render_radar_png(pass_id: str, out: Path) -> tuple[list[float], tuple[int, int]] | None:
    """VV dB preview reprojected to Web Mercator (so a Leaflet image overlay lines up exactly)."""
    src_path = config.S1_RAW / f"S1_{pass_id}_r{config.S1_RELATIVE_ORBIT:03d}.tif"
    if not src_path.exists():
        return None
    g = reach_grid()
    with rasterio.open(src_path) as ds:
        q = ds.read(1)
    lon0, lat0, lon1, lat1 = config.REACH.bbox_lonlat
    dst_crs = "EPSG:3857"
    tr, w, h = calculate_default_transform(g.crs, dst_crs, g.width, g.height, *g.bounds, resolution=IMAGE_PIXEL_M)
    dst = np.full((h, w), 255, np.uint8)
    reproject(q, dst, src_transform=g.transform, src_crs=g.crs, src_nodata=255, dst_transform=tr,
              dst_crs=dst_crs, dst_nodata=255, resampling=Resampling.average)
    db = dst.astype(np.float32) / 254 * (config.DB_MAX - config.DB_MIN) + config.DB_MIN
    v = np.clip((db + 25.0) / 25.0, 0, 1) ** 0.9 * 255
    rgba = np.zeros((h, w, 4), np.uint8)
    rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = v.astype(np.uint8)
    rgba[..., 3] = np.where(dst == 255, 0, 255)
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, "RGBA").save(out, "WEBP", quality=62, method=6)
    from pyproj import Transformer
    t = Transformer.from_crs(dst_crs, "EPSG:4326", always_xy=True)
    x0, y1 = tr.c, tr.f
    x1, y0 = x0 + w * tr.a, y1 + h * tr.e
    (lw, ls), (le, ln) = t.transform(x0, y0), t.transform(x1, y1)
    return [ls, lw, ln, le], (w, h)


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))


def export_static(pred: pd.DataFrame, images: bool = True, out: Path = APP_DATA) -> None:
    positions = load_positions()
    imgs: set[str] = set()
    bounds = None
    if images:
        for pid in positions["pass_id"].unique():
            if int(pid[:4]) in IMAGE_YEARS:
                res = render_radar_png(pid, out / "radar" / f"{pid}.webp")
                if res:
                    imgs.add(pid)
                    bounds = res[0]
    else:
        imgs = {p.stem for p in (out / "radar").glob("*.webp")}
    reach = reach_json()
    if bounds is None and (out / "reach.json").exists():
        bounds = json.loads((out / "reach.json").read_text()).get("image_bounds")
    reach["image_bounds"] = bounds
    write_json(out / "reach.json", reach)
    write_json(out / "passes.json", passes_json(positions, imgs))
    for y, obj in banks_by_year(positions).items():
        write_json(out / "banks" / f"{y}.json", obj)
    index, files = prediction_files(pred)
    write_json(out / "predictions" / "index.json", index)
    for d, rows in files.items():
        write_json(out / "predictions" / f"{d}.json", rows)
    write_json(out / "metrics.json", metrics_json(pred))
    gj = reach_geojson(reach)
    (config.DEMO_DIR / "sirajganj_reach.geojson").write_text(json.dumps(gj))


def reach_geojson(reach: dict) -> dict:
    lon0, lat0, lon1, lat1 = reach["bbox"]
    feats = [dict(type="Feature", properties=dict(kind="reach", name=reach["name"]),
                  geometry=dict(type="Polygon", coordinates=[[[lon0, lat0], [lon1, lat0], [lon1, lat1],
                                                              [lon0, lat1], [lon0, lat0]]]))]
    for bank, coords in reach["baselines"].items():
        feats.append(dict(type="Feature", properties=dict(kind="baseline", bank=bank),
                          geometry=dict(type="LineString", coordinates=coords)))
    for t in reach["transects"]:
        feats.append(dict(type="Feature", properties=dict(kind="transect", id=t["id"], bank=t["bank"],
                                                          chainage_m=t["chainage_m"]),
                          geometry=dict(type="LineString", coordinates=[t["start"], t["end"]])))
    return dict(type="FeatureCollection", features=feats)


def _render_to_mercator(arrays: list[np.ndarray], src_transform, src_crs, nodata, bounds_lonlat,
                        resampling=Resampling.average) -> tuple[np.ndarray, list[float]]:
    """Reproject bands to Web Mercator over a lon/lat box at IMAGE_PIXEL_M."""
    from pyproj import Transformer
    w_, s_, e_, n_ = bounds_lonlat
    t = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    (x0, y0), (x1, y1) = t.transform(w_, s_), t.transform(e_, n_)
    px = IMAGE_PIXEL_M / np.cos(np.radians((s_ + n_) / 2))      # ~40 m on the ground
    w, h = int(np.ceil((x1 - x0) / px)), int(np.ceil((y1 - y0) / px))
    dst_tr = Affine(px, 0, x0, 0, -px, y1)
    out = []
    for a in arrays:
        dst = np.full((h, w), nodata, a.dtype)
        reproject(a, dst, src_transform=src_transform, src_crs=src_crs, src_nodata=nodata, dst_transform=dst_tr,
                  dst_crs="EPSG:3857", dst_nodata=nodata, resampling=resampling)
        out.append(dst)
    return np.stack(out), [s_, w_, n_, e_]


def export_wow(out: Path = APP_DATA, years=(2023, 2024, 2025), min_cloud: float = 85.0,
               max_cloud: float = 99.0) -> dict | None:
    """The monsoon blind spot: a real cloudy Sentinel-2 scene and the radar pass of the same week."""
    from src.masks.validate_masks import S2_BUCKET, item_meta, list_s2_items
    passes = pd.read_csv(config.MASK_DIR / "mask_summary.csv")
    passes["d"] = pd.to_datetime(passes["date"])
    best = None
    for y in years:
        for mth in (6, 7, 8, 9):
            for pref in list_s2_items("45/R/YH", y, mth):
                meta = item_meta(pref)
                # heavy but not total cloud: a flat 100% scene reads as a missing image, not as cloud
                if not meta or not (min_cloud <= meta["cloud"] <= max_cloud) or meta["nodata"] > 20:
                    continue
                d = pd.Timestamp(meta["datetime"][:10])
                gap = (passes["d"] - d).abs().dt.days
                k = gap.idxmin()
                if gap[k] > 2 or not (config.S1_RAW / f"S1_{passes.loc[k, 'pass_id']}_r{config.S1_RELATIVE_ORBIT:03d}.tif").exists():
                    continue
                score = (meta["cloud"], -gap[k])
                if best is None or score > best[0]:
                    best = (score, meta, passes.loc[k])
    if best is None:
        log.warning("no cloudy S2 / S1 pair found")
        return None
    _, meta, p = best
    bounds = (config.REACH.lon_min, 24.32, config.REACH.lon_max, config.REACH.lat_max)   # inside S2 tile 45RYH
    with rasterio.Env(**GDAL_ENV):
        with rasterio.open(f"/vsicurl/{S2_BUCKET}/{meta['prefix']}TCI.tif") as ds:
            wb = transform_bounds("EPSG:4326", ds.crs, *bounds)
            win = from_bounds(*wb, ds.transform).round_offsets().round_lengths()
            tci = ds.read(window=win)
            tci_tr = ds.window_transform(win)
            s2_crs = ds.crs
    rgb, b = _render_to_mercator([tci[i] for i in range(3)], tci_tr, s2_crs, 0, bounds)
    s2_img = np.moveaxis(rgb, 0, -1)
    alpha = np.where(s2_img.sum(-1) == 0, 0, 255).astype(np.uint8)
    (out / "wow").mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.dstack([s2_img, alpha]), "RGBA").save(out / "wow" / "s2.webp", "WEBP", quality=70)
    g = reach_grid()
    with rasterio.open(config.S1_RAW / f"S1_{p['pass_id']}_r{config.S1_RELATIVE_ORBIT:03d}.tif") as ds:
        q = ds.read(1)
    (qq,), _ = _render_to_mercator([q], g.transform, g.crs, 255, bounds)
    db = qq.astype(np.float32) / 254 * (config.DB_MAX - config.DB_MIN) + config.DB_MIN
    v = (np.clip((db + 25.0) / 25.0, 0, 1) ** 0.9 * 255).astype(np.uint8)
    a = np.where(qq == 255, 0, 255).astype(np.uint8)
    Image.fromarray(np.dstack([v, v, v, a]), "RGBA").save(out / "wow" / "s1.webp", "WEBP", quality=70)
    wow = dict(s2=dict(url="/data/wow/s2.webp", date=meta["datetime"][:10], cloud=meta["cloud"], id=meta["id"]),
               s1=dict(url="/data/wow/s1.webp", date=str(p["date"]), pass_id=p["pass_id"]), bounds=b)
    write_json(out / "wow" / "wow.json", wow)
    return wow


def export_briefs(pred: pd.DataFrame, out: Path = APP_DATA) -> int:
    """Precompute the weekly PDF brief for every forecast date (offline demo)."""
    from src.alerts.brief import build_brief
    pred = pred.copy()
    stats = config.METRICS_DIR / "label_stats.json"
    n = 0
    for d in sorted(pred["forecast_date"].unique()):
        ds = pd.Timestamp(d).strftime("%Y-%m-%d")
        sub = pred[pred["forecast_date"] == d].copy()
        if stats.exists():
            sub.attrs["threshold_m"] = json.loads(stats.read_text())["threshold_m"]
        (out / "briefs").mkdir(parents=True, exist_ok=True)
        build_brief(sub, ds, out / "briefs" / f"{ds}.pdf")
        n += 1
    return n


def write_importance() -> None:
    from src.models.data import load_dataset, temporal_split
    df = load_dataset()
    _, _, test = temporal_split(df)
    model, info = load_model(), load_params()
    sample = test.sample(min(20000, len(test)), random_state=config.RANDOM_SEED)
    (config.METRICS_DIR / "importance.json").write_text(
        json.dumps(global_importance(model, sample, info["features"]), indent=2))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--images", action="store_true", help="re-render radar previews (needs data/raw/sentinel1)")
    ap.add_argument("--no-briefs", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO)
    pred = predictions_all()
    save_predictions(pred)
    write_importance()
    from src.claims import ledger
    (config.METRICS_DIR / "claims.json").write_text(json.dumps(ledger(), indent=2, ensure_ascii=False))
    export_static(pred, images=a.images)
    if a.images:
        export_wow()
    if not a.no_briefs:
        log.info("%d briefs", export_briefs(pred))
    print("exported", pred["forecast_date"].nunique(), "forecast dates")


if __name__ == "__main__":
    main()
