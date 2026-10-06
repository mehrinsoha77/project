import numpy as np
import pandas as pd

from src.labels.make_labels import forward_confirmed, make_labels, target_index


def test_target_index_nearest_within_tolerance():
    d = pd.DatetimeIndex(pd.to_datetime(["2020-01-01", "2020-01-13", "2020-01-25", "2020-02-06", "2020-04-01"]))
    ti = target_index(d, horizon=28, tol=8)
    assert ti[0] == 2       # Jan 29 -> Jan 25 (4 days)
    assert ti[3] == -1      # Mar 5 -> nearest Apr 1 is 27 days off
    assert ti[4] == -1


def test_forward_confirmation_removes_reverting_spikes():
    d = pd.DatetimeIndex(pd.date_range("2020-06-01", periods=5, freq="12D"))
    B = np.array([[0.0, 150.0, 0.0, 0.0, 0.0],     # flood spike that reverts
                  [0.0, 60.0, 60.0, 65.0, 70.0]])  # real retreat that stays
    Bc = forward_confirmed(B, d, days=36)
    assert Bc[0, 1] == 0.0
    assert Bc[1, 1] == 60.0


def test_make_labels_on_synthetic(synthetic_positions):
    lab = make_labels(synthetic_positions, threshold_m=20.0)
    assert set(lab["y"].unique()) <= {0, 1}
    assert (lab["target_date"] > lab["forecast_date"]).all()
    # the flood spike on segment index 3 at pass 30 must not create a positive label at the pass before it
    spike_seg = sorted(synthetic_positions["transect_id"].unique())[0]
    assert lab["y"].mean() < 0.5
    assert (lab["retreat_m"] >= 20).eq(lab["y"] == 1).all()
    assert spike_seg  # fixture sanity
