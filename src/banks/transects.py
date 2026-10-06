"""Cast transects every 200 m, perpendicular to each bank baseline.

Each transect starts ``TRANSECT_RIVERWARD_M`` riverward of the baseline and
ends ``TRANSECT_LANDWARD_M`` landward of it. Distances along a transect are
signed: 0 at the baseline, positive landward. One transect = one 200 m bank
segment; its id is ``<bank>-<chainage in metres from the reach's north end>``.

CLI::

    python -m src.banks.transects
"""
from __future__ import annotations

import argparse
import logging

import geopandas as gpd
import numpy as np
from shapely.geometry import LineString, Point

from src import config
from src.banks.baselines import load_baselines
from src.banks.belt import BRIDGE_LONLAT
from src.geo import from_lonlat, reach_grid, to_lonlat

log = logging.getLogger(__name__)

TRANSECTS_PATH = config.TRANSECT_DIR / "transects.geojson"


def landward_normal(tangent: np.ndarray, bank: str) -> np.ndarray:
    """Unit normal pointing away from the river.

    Baselines run north to south. For the west bank, landward is the
    tangent rotated clockwise; for the east bank, counter-clockwise.
    """
    tx, ty = tangent / np.linalg.norm(tangent)
    return np.array([ty, -tx]) if bank == "W" else np.array([-ty, tx])


def cast(baseline: LineString, bank: str, spacing: float = config.TRANSECT_SPACING_M,
         riverward: float = config.TRANSECT_RIVERWARD_M,
         landward: float = config.TRANSECT_LANDWARD_M) -> list[dict]:
    # make sure the line runs north -> south
    coords = np.asarray(baseline.coords)
    if coords[0, 1] < coords[-1, 1]:
        baseline = LineString(coords[::-1])
    out = []
    n = int(baseline.length // spacing)
    for i in range(n + 1):
        d = min(i * spacing + spacing / 2, baseline.length)
        p = baseline.interpolate(d)
        a = baseline.interpolate(max(d - 100.0, 0.0))
        b = baseline.interpolate(min(d + 100.0, baseline.length))
        nrm = landward_normal(np.array([b.x - a.x, b.y - a.y]), bank)
        start = (p.x - riverward * nrm[0], p.y - riverward * nrm[1])
        end = (p.x + landward * nrm[0], p.y + landward * nrm[1])
        out.append(dict(transect_id=f"{bank}-{int(round(d)):05d}", bank=bank,
                        chainage_m=float(d), x0=p.x, y0=p.y, nx=float(nrm[0]), ny=float(nrm[1]),
                        geometry=LineString([start, end])))
    return out


def build_transects() -> gpd.GeoDataFrame:
    g = reach_grid()
    rows = []
    for _, r in load_baselines().iterrows():
        rows += cast(r.geometry, r.bank)
    gdf = gpd.GeoDataFrame(rows, crs=g.crs)
    lon, lat = to_lonlat(gdf["x0"].to_numpy(), gdf["y0"].to_numpy())
    gdf["lon"], gdf["lat"] = np.round(lon, 6), np.round(lat, 6)
    bx, by = from_lonlat([p[0] for p in BRIDGE_LONLAT], [p[1] for p in BRIDGE_LONLAT])
    bridge = LineString(list(zip(bx, by)))
    gdf["near_bridge"] = [bridge.distance(Point(x, y)) < 1500.0 for x, y in zip(gdf.x0, gdf.y0)]
    # transect must stay inside the reach grid
    xmin, ymin, xmax, ymax = g.bounds
    inside = gdf.geometry.apply(lambda ln: all(xmin <= x <= xmax and ymin <= y <= ymax for x, y in ln.coords))
    dropped = int((~inside).sum())
    if dropped:
        log.info("dropping %d transects that leave the reach grid", dropped)
    return gdf[inside].reset_index(drop=True)


def sample_index(transects: gpd.GeoDataFrame, step: float | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Grid (row, col) of every sample point; returns rows, cols (n_tr, n_s) and the signed distances."""
    g = reach_grid()
    step = step or g.transform.a
    s = np.arange(-config.TRANSECT_RIVERWARD_M, config.TRANSECT_LANDWARD_M + step / 2, step)
    x = transects["x0"].to_numpy()[:, None] + s[None, :] * transects["nx"].to_numpy()[:, None]
    y = transects["y0"].to_numpy()[:, None] + s[None, :] * transects["ny"].to_numpy()[:, None]
    r, c = g.rc_of(x, y)
    r = np.clip(np.round(r).astype(int), 0, g.height - 1)
    c = np.clip(np.round(c).astype(int), 0, g.width - 1)
    return r, c, s


def load_transects() -> gpd.GeoDataFrame:
    return gpd.read_file(TRANSECTS_PATH)


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    logging.basicConfig(level=logging.INFO)
    gdf = build_transects()
    config.TRANSECT_DIR.mkdir(parents=True, exist_ok=True)
    gdf.to_file(TRANSECTS_PATH, driver="GeoJSON")
    print(gdf.groupby("bank").size().to_dict(), "transects")


if __name__ == "__main__":
    main()
