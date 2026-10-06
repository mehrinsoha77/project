"""From a per-pass water mask to the river *braid belt*.

The Jamuna is braided: between the two mainland banks lie many channels and
sand islands (chars). The outer bank of the river on a given pass is the
landward edge of the braid belt = river-connected water plus the chars it
encloses. Steps:

1. burn the Bangabandhu Bridge deck as water (it is a bright line that would
   otherwise join chars to the mainland);
2. keep only water connected to large river bodies (drops floodplain ponds);
3. fill chars: land regions fully enclosed by river water;
4. open the belt with a ~150 m disk to cut narrow khals (side channels) that
   would otherwise pull the bank landward, then keep only large components.

All operations are on the fixed 10 m reach grid; distance-transform based
morphology keeps it fast on ~37 M pixels.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
from rasterio.features import rasterize
from scipy import ndimage
from shapely.geometry import LineString

from src.geo import from_lonlat, reach_grid

# Bridge deck traced on the 2023-07-12 VV image (bright double-bounce line).
BRIDGE_LONLAT = [(89.75236, 24.40000), (89.76767, 24.40153), (89.78246, 24.40171), (89.80065, 24.40002)]
BRIDGE_HALF_WIDTH_M = 250.0

MIN_RIVER_KM2 = 5.0
KHAL_OPEN_RADIUS_PX = 7          # opening disk radius; removes channels narrower than ~150 m
CONNECT_DILATE_PX = 2


@lru_cache(maxsize=1)
def bridge_mask() -> np.ndarray:
    g = reach_grid()
    xs, ys = from_lonlat([p[0] for p in BRIDGE_LONLAT], [p[1] for p in BRIDGE_LONLAT])
    poly = LineString(list(zip(xs, ys))).buffer(BRIDGE_HALF_WIDTH_M, cap_style=2)
    return rasterize([(poly, 1)], out_shape=g.shape, transform=g.transform, dtype="uint8").astype(bool)


def _large_components(binary: np.ndarray, min_px: int, connect_px: int = 0) -> np.ndarray:
    probe = binary
    if connect_px:
        probe = ndimage.distance_transform_edt(~binary) <= connect_px
    lab, n = ndimage.label(probe)
    if n == 0:
        return np.zeros_like(binary)
    sizes = ndimage.sum_labels(binary, lab, index=np.arange(1, n + 1))
    keep = np.zeros(n + 1, bool)
    keep[1:] = sizes >= min_px
    return keep[lab] & binary


def river_belt(mask: np.ndarray, pixel_m: float = 10.0) -> np.ndarray:
    """Boolean braid-belt mask. ``mask``: 0 land, 1 water, 255 nodata."""
    water = mask == 1
    water |= bridge_mask() & (mask != 255)
    min_px = int(MIN_RIVER_KM2 * 1e6 / pixel_m ** 2)
    river = _large_components(water, min_px, CONNECT_DILATE_PX)
    # Chars cut by the top or bottom edge of the reach are closed off by
    # treating those edges as water before filling holes. Left and right
    # edges are mainland floodplain and stay open.
    padded = np.pad(river, ((1, 1), (0, 0)), constant_values=True)
    filled = ndimage.binary_fill_holes(padded)[1:-1]
    r = KHAL_OPEN_RADIUS_PX
    eroded = ndimage.distance_transform_edt(filled) > r
    opened = ndimage.distance_transform_edt(~eroded) <= r
    belt = _large_components(opened, min_px)
    return belt
