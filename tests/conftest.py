import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture
def synthetic_transects() -> pd.DataFrame:
    """Two straight banks, 30 transects each, 200 m apart, running north->south."""
    rows = []
    for bank, nx in (("W", -1.0), ("E", 1.0)):
        for i in range(30):
            rows.append(dict(transect_id=f"{bank}-{i * 200 + 100:05d}", bank=bank, chainage_m=i * 200.0 + 100,
                             x0=0.0, y0=-i * 200.0, nx=nx, ny=0.0, near_bridge=False))
    return pd.DataFrame(rows)


@pytest.fixture
def synthetic_positions(synthetic_transects) -> pd.DataFrame:
    """60 passes every 12 days; banks retreat at segment-specific rates, with noise and a flood spike."""
    rng = np.random.default_rng(0)
    dates = pd.date_range("2019-01-05", periods=60, freq="12D")
    recs = []
    for k, t in enumerate(synthetic_transects.itertuples()):
        rate = 0.5 + 3.0 * (k % 7 == 0)            # m/day for "active" segments
        pos = 0.0
        for j, d in enumerate(dates):
            pos += rate * 12 * (d.month in (6, 7, 8, 9)) + rng.normal(0, 2)
            val = pos + (150 if (k == 3 and j == 30) else 0)      # one flood spike that reverts
            if rng.random() < 0.03:
                val = np.nan
            recs.append(dict(pass_id=d.strftime("%Y%m%d") + "_S1A", transect_id=t.transect_id, date=d,
                             bank_pos_m=val, dist_main_channel_m=200 + rng.normal(0, 30),
                             near_channel_width_m=400.0, char_shield_frac=0.2, nearbank_water_frac=0.9,
                             belt_water_km2=500 + 200 * np.sin(2 * np.pi * d.dayofyear / 365.25),
                             water_area_km2=700.0, otsu_ok=True, coverage=1.0, platform="S1A"))
    return pd.DataFrame(recs)
