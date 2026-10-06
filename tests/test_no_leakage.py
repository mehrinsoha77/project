"""CRITICAL: no feature may use data from after its forecast date.

Strategy: build the feature table from all passes, then rebuild it from
positions truncated at a forecast date t and compare the rows for t. If any
feature looked past t, its value would change when the future is removed.
Runs on synthetic data always, and on the real archive when it is present.
"""
import numpy as np
import pandas as pd
import pytest

from src import config
from src.features.build_features import ALL_FEATURES, build

LABEL_COLUMNS = {"y", "retreat_m", "target_date", "major"}


def _compare(full: pd.DataFrame, positions: pd.DataFrame, transects, t: pd.Timestamp, with_bh: bool):
    trunc = build(positions[positions["date"] <= t], transects, with_bank_height=with_bh)
    a = full[full["forecast_date"] == t].set_index("transect_id")[ALL_FEATURES].sort_index()
    b = trunc[trunc["forecast_date"] == t].set_index("transect_id")[ALL_FEATURES].sort_index()
    assert list(a.index) == list(b.index)
    pd.testing.assert_frame_equal(a, b, check_exact=False, rtol=1e-9, atol=1e-9)


def test_no_future_data_synthetic(synthetic_positions, synthetic_transects):
    full = build(synthetic_positions, synthetic_transects, with_bank_height=False)
    dates = sorted(synthetic_positions["date"].unique())
    for t in [dates[5], dates[17], dates[33], dates[-2]]:
        _compare(full, synthetic_positions, synthetic_transects, pd.Timestamp(t), with_bh=False)


def test_leak_detector_detects_a_leak(synthetic_positions, synthetic_transects, monkeypatch):
    """The test above must be able to fail: inject a feature that peeks one pass ahead."""
    import src.features.build_features as bf

    real = bf.build

    def leaky(positions, transects=None, with_bank_height=True):
        X = real(positions, transects, with_bank_height)
        X = X.sort_values(["transect_id", "forecast_date"])
        X["ret_28_m"] = X.groupby("transect_id")["bank_pos_m"].shift(-1)   # the future
        return X.sort_values(["forecast_date", "transect_id"]).reset_index(drop=True)

    full = leaky(synthetic_positions, synthetic_transects, False)
    t = pd.Timestamp(sorted(synthetic_positions["date"].unique())[20])
    trunc = leaky(synthetic_positions[synthetic_positions["date"] <= t], synthetic_transects, False)
    a = full[full["forecast_date"] == t].set_index("transect_id")["ret_28_m"].sort_index()
    b = trunc[trunc["forecast_date"] == t].set_index("transect_id")["ret_28_m"].sort_index()
    assert not a.equals(b)


def test_model_features_exclude_labels_and_location():
    assert not LABEL_COLUMNS & set(ALL_FEATURES)
    assert not {"chainage_m", "bank", "transect_id", "lon", "lat"} & set(ALL_FEATURES)


REAL = config.TRANSECT_DIR / "bank_positions.parquet"


@pytest.mark.skipif(not REAL.exists(), reason="real archive not processed in this checkout")
def test_no_future_data_real_archive():
    from src.banks.bank_position import load_positions
    from src.banks.transects import load_transects

    pos = load_positions()
    tr = load_transects()
    full = build(pos, tr, with_bank_height=False)
    dates = sorted(pos["date"].unique())
    rng = np.random.default_rng(config.RANDOM_SEED)
    picks = sorted(rng.choice(np.arange(20, len(dates)), size=4, replace=False))
    for k in picks:
        _compare(full, pos, tr, pd.Timestamp(dates[k]), with_bh=False)


@pytest.mark.skipif(not (config.LABELS_DIR / "labels_all.parquet").exists(), reason="labels not built")
def test_splits_are_disjoint_in_time():
    lab = pd.read_parquet(config.LABELS_DIR / "labels_all.parquet")
    train = lab[lab["year"].isin(config.TRAIN_YEARS)]
    test = lab[lab["year"].isin(config.TEST_YEARS)]
    assert train["forecast_date"].max() < test["forecast_date"].min()
    # a training label's outcome window may not reach into the test period
    assert train["target_date"].max() < pd.Timestamp(f"{min(config.TEST_YEARS)}-01-01") + pd.Timedelta(days=60)
