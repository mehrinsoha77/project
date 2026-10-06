import numpy as np
import pandas as pd

from src.labels.make_labels import make_labels, target_index, window_stat


def test_target_index_nearest_within_tolerance():
    d = pd.DatetimeIndex(pd.to_datetime(["2020-01-01", "2020-01-13", "2020-01-25", "2020-02-06", "2020-04-01"]))
    ti = target_index(d, horizon=28, tol=8)
    assert ti[0] == 2       # Jan 29 -> Jan 25 (4 days)
    assert ti[3] == -1      # Mar 5 -> nearest Apr 1 is 27 days off
    assert ti[4] == -1


def test_window_stat_min_count():
    B = np.array([[1.0, np.nan, 3.0, 5.0]])
    sel = np.array([True, True, True, True])
    assert window_stat(B, sel, "median")[0] == 3.0
    assert np.isnan(window_stat(B, sel, "q25", min_n=4)[0])


def _positions(series: dict[str, list[float]], start="2020-01-05", step=12):
    dates = pd.date_range(start, periods=len(next(iter(series.values()))), freq=f"{step}D")
    return pd.DataFrame([dict(transect_id=t, date=d, bank_pos_m=v) for t, vals in series.items()
                         for d, v in zip(dates, vals)]), dates


def test_inundation_that_recedes_is_not_erosion():
    flood = [0, 0, 0, 0, 300, 300, 300, 300, 0, 0] + [0] * 16          # floods for ~48 d, then drains
    erode = [0, 0, 0, 0, 60, 60, 60, 60, 60, 60] + [60] * 16            # loses 60 m and keeps it
    flip = [0, 0, 0, 0, 0, -400, 0, 0, 0, 0] + [0] * 16                 # one bad pass
    pos, dates = _positions({"F": flood, "E": erode, "X": flip})
    lab = make_labels(pos, threshold_m=20.0).set_index(["transect_id", "forecast_date"])
    t = dates[2]                                                         # forecast just before the change
    assert lab.loc[("E", t), "y"] == 1
    assert lab.loc[("F", t), "y"] == 0          # landward jump that recedes within 180 days
    assert (lab.xs("X", level=0)["y"] == 0).all()   # a single riverward flip never makes a positive


def test_make_labels_on_synthetic(synthetic_positions):
    lab = make_labels(synthetic_positions, threshold_m=20.0)
    assert set(lab["y"].unique()) <= {0, 1}
    assert (lab["target_date"] > lab["forecast_date"]).all()
    assert ((lab["window_retreat_m"] >= 20) & (lab["permanent_retreat_m"] >= 20)).eq(lab["y"] == 1).all()
    assert 0 < lab["y"].mean() < 0.6
