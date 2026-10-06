import numpy as np
import pandas as pd

from src.features.build_features import ALL_FEATURES, FEATURE_GROUPS, build
from src.features.geometry import baseline_curvature, neighbour_mean


def test_feature_table_has_all_groups(synthetic_positions, synthetic_transects):
    X = build(synthetic_positions, synthetic_transects, with_bank_height=False)
    for f in ALL_FEATURES:
        assert f in X.columns, f
    assert X["forecast_date"].nunique() == synthetic_positions["date"].nunique()
    # no location features in the model's list
    assert "chainage_m" not in ALL_FEATURES and "bank" not in ALL_FEATURES
    assert sum(len(v) for v in FEATURE_GROUPS.values()) == len(ALL_FEATURES)


def test_recent_retreat_is_positive_for_active_segments(synthetic_positions, synthetic_transects):
    X = build(synthetic_positions, synthetic_transects, with_bank_height=False)
    mons = X[X["forecast_date"].dt.month == 9]
    active = mons[mons["transect_id"] == "W-00100"]["ret_84_m"].median()
    quiet = mons[mons["transect_id"] == "W-00300"]["ret_84_m"].median()
    assert active > quiet + 50


def test_curvature_sign_concave_west_bank():
    # West bank bulging west (outer bend): x = -sqrt(R^2 - y^2) on a circle centred in the river.
    R = 3000.0
    ys = np.linspace(1500, -1500, 16)
    xs = -np.sqrt(R ** 2 - ys ** 2)
    # landward normals point away from the centre (0, 0)
    nx, ny = xs / R, ys / R
    tr = pd.DataFrame(dict(bank="W", chainage_m=np.arange(16) * 200.0, nx=nx, ny=ny))
    k = baseline_curvature(tr)
    assert np.nanmedian(k) > 0
    assert abs(np.nanmedian(k) - 1 / 3.0) < 0.05     # 1/R in 1/km


def test_neighbour_mean_excludes_self():
    df = pd.DataFrame(dict(bank="W", forecast_date=pd.Timestamp("2020-01-01"), chainage_m=[0, 200, 400, 600],
                           v=[1.0, 100.0, 3.0, np.nan]))
    out = neighbour_mean(df, "v", k=1)
    assert out.iloc[1] == 2.0
    assert out.iloc[0] == 100.0
