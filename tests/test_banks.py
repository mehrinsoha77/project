import numpy as np
from shapely.geometry import LineString

from src.banks import belt as belt_mod
from src.banks.bank_position import first_belt_from_land
from src.banks.transects import cast, landward_normal


def test_landward_normals_point_away_from_river():
    south = np.array([0.0, -1.0])
    assert np.allclose(landward_normal(south, "W"), [-1, 0])
    assert np.allclose(landward_normal(south, "E"), [1, 0])


def test_cast_spacing_and_direction():
    base = LineString([(0, 1000), (0, 0)])   # north -> south
    tr = cast(base, "W", spacing=200, riverward=100, landward=300)
    assert len(tr) == 6
    t = tr[0]
    (x0, _), (x1, _) = t["geometry"].coords
    assert x0 > x1                            # starts riverward (east), ends landward (west)
    assert t["transect_id"] == "W-00100"


def test_first_belt_from_land_skips_khal_specks_and_finds_bank():
    # sample 0 riverward ... sample n-1 landward; True = belt
    row = np.array([1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 0, 0], bool)   # isolated belt speck at 7 (run < 3)
    idx = first_belt_from_land(row[None, :], run=3)
    assert idx[0] == 4
    none = np.zeros((1, 10), bool)
    assert first_belt_from_land(none)[0] == -1


def test_river_belt_fills_chars_and_drops_ponds(monkeypatch):
    h, w = 400, 300
    mask = np.zeros((h, w), np.uint8)
    mask[:, 100:220] = 1               # river
    mask[150:250, 140:180] = 0         # a char inside it
    mask[50:60, 10:20] = 1             # floodplain pond
    monkeypatch.setattr(belt_mod, "bridge_mask", lambda: np.zeros((h, w), bool))
    b = belt_mod.river_belt(mask, pixel_m=100.0)    # 100 m pixels so the 5 km^2 rule keeps the river
    assert b[200, 160]                 # char filled
    assert not b[55, 15]               # pond removed
    assert not b[200, 50]              # mainland stays out
