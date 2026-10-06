"""Shared geometry helpers: the fixed 10 m analysis grid for the reach."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from affine import Affine
from pyproj import Transformer

from src.config import REACH, Reach


@dataclass(frozen=True)
class Grid:
    crs: str
    transform: Affine
    width: int
    height: int

    @property
    def shape(self) -> tuple[int, int]:
        return (self.height, self.width)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        x0, y1 = self.transform.c, self.transform.f
        px = self.transform.a
        return (x0, y1 - self.height * px, x0 + self.width * px, y1)

    def xy_of(self, rows: np.ndarray, cols: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Map pixel-centre (row, col) to projected (x, y)."""
        px = self.transform.a
        x = self.transform.c + (np.asarray(cols) + 0.5) * px
        y = self.transform.f - (np.asarray(rows) + 0.5) * px
        return x, y

    def rc_of(self, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Map projected (x, y) to fractional pixel (row, col) with centre at .0."""
        px = self.transform.a
        col = (np.asarray(x) - self.transform.c) / px - 0.5
        row = (self.transform.f - np.asarray(y)) / px - 0.5
        return row, col

    def coarsen(self, factor: int) -> "Grid":
        return Grid(self.crs, self.transform * Affine.scale(factor),
                    int(np.ceil(self.width / factor)), int(np.ceil(self.height / factor)))


@lru_cache(maxsize=4)
def reach_grid(reach: Reach = REACH) -> Grid:
    """Snap the reach's lon/lat box to a north-up grid in the reach CRS."""
    to_utm = Transformer.from_crs("EPSG:4326", reach.crs, always_xy=True)
    lons = np.array([reach.lon_min, reach.lon_max, reach.lon_min, reach.lon_max])
    lats = np.array([reach.lat_min, reach.lat_min, reach.lat_max, reach.lat_max])
    xs, ys = to_utm.transform(lons, lats)
    px = reach.pixel_m
    x0 = np.floor(min(xs) / px) * px
    x1 = np.ceil(max(xs) / px) * px
    y0 = np.floor(min(ys) / px) * px
    y1 = np.ceil(max(ys) / px) * px
    transform = Affine(px, 0.0, x0, 0.0, -px, y1)
    return Grid(reach.crs, transform, int(round((x1 - x0) / px)), int(round((y1 - y0) / px)))


@lru_cache(maxsize=4)
def transformer(src: str, dst: str) -> Transformer:
    return Transformer.from_crs(src, dst, always_xy=True)


def to_lonlat(x, y, crs: str = REACH.crs):
    return transformer(crs, "EPSG:4326").transform(x, y)


def from_lonlat(lon, lat, crs: str = REACH.crs):
    return transformer("EPSG:4326", crs).transform(lon, lat)
