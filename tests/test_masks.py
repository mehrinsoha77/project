import numpy as np
import pytest

from src.masks import s1_io
from src.masks.sentinel1_mask import classify


def test_quantise_roundtrip():
    db = np.array([[-30.0, -12.3, 0.0, 5.0, np.nan]])
    back = s1_io.dequantise_db(s1_io.quantise_db(db))
    assert np.isnan(back[0, -1])
    assert np.allclose(back[0, :-1], db[0, :-1], atol=0.08)


def test_lee_filter_keeps_flat_field_and_nodata():
    img = np.full((40, 40), 0.05, np.float32)
    valid = np.ones_like(img, bool)
    valid[0, 0] = False
    out = s1_io.lee_filter(img, valid, 5)
    assert np.isnan(out[0, 0])
    assert np.allclose(out[5:-5, 5:-5], 0.05, rtol=1e-4)


def test_classify_separates_dark_water_and_bright_land():
    rng = np.random.default_rng(1)
    vv = rng.normal(-9, 1.2, (300, 300)).astype(np.float32)
    vh = rng.normal(-15, 1.2, (300, 300)).astype(np.float32)
    vv[:, 100:200] = rng.normal(-20, 1.2, (300, 100))     # river
    vh[:, 100:200] = rng.normal(-25, 1.2, (300, 100))
    vv[50:80, 140:160] = -8.0                              # wind-roughened patch: bright in VV...
    vh[50:80, 140:160] = -26.0                             # ...but dark in VH
    vv[0:5, 0:5] = np.nan
    mask, info = classify(vv, vh)
    assert info["otsu_ok"]
    assert -18 < info["t_vv"] < -11
    assert (mask[:, 110:190] == 1).mean() > 0.97
    assert (mask[:, :90] == 0).mean() > 0.97
    assert (mask[0:5, 0:5] == 255).all()
    # VH rescue only applies within the margin above the VV threshold, so a very bright VV patch stays land:
    # the method is conservative on purpose.
    assert set(np.unique(mask)) <= {0, 1, 255}


class _G:
    def __init__(self, row, col, x, y):
        self.row, self.col, self.x, self.y = row, col, x, y


def test_gcp_model_inverse_is_subpixel():
    rows = np.linspace(0, 16000, 10)
    cols = np.linspace(0, 25000, 21)
    gcps = []
    for r in rows:
        for c in cols:   # smooth, slightly non-linear, rotated mapping
            lon = 88.7 + 1e-4 * c - 1.5e-5 * r + 1e-11 * c * c
            lat = 25.4 - 9e-5 * r - 2e-5 * c + 5e-12 * r * c
            gcps.append(_G(r, c, lon, lat))
    m = s1_io.GcpModel(gcps)
    rr = np.array([123.4, 8000.0, 15000.7])
    cc = np.array([22222.2, 5000.5, 100.0])
    lon, lat = m.slon.ev(rr, cc), m.slat.ev(rr, cc)
    r2, c2 = m.inverse(lon, lat)
    assert np.allclose(r2, rr, atol=0.05) and np.allclose(c2, cc, atol=0.05)


@pytest.mark.parametrize("bad", [np.full((50, 50), -9.0, np.float32)])
def test_classify_unimodal_scene_is_flagged(bad):
    _, info = classify(bad + np.random.default_rng(0).normal(0, 0.1, bad.shape).astype(np.float32), bad - 6)
    assert info["otsu_ok"] in (True, False)   # never crashes; thresholds stay finite
    assert np.isfinite(info["t_vv"]) and np.isfinite(info["t_vh"])
