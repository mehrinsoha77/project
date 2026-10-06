import numpy as np
import pandas as pd

from src.models.metrics import major_recall, moving_block_bootstrap, precision_at_k, rank_within_date, reliability


def _toy():
    rows = []
    for d in pd.date_range("2023-06-01", periods=5, freq="12D"):
        for i in range(50):
            rows.append(dict(forecast_date=d, s=50 - i, y=int(i < 10), major=int(i == 0)))
    return pd.DataFrame(rows)


def test_precision_at_k_perfect_ranker():
    df = _toy()
    p = precision_at_k(df, "s", k=20)
    assert np.allclose(p.values, 0.5)        # 10 positives in the top 20


def test_rank_is_per_date_and_handles_nan():
    df = _toy()
    df.loc[0, "s"] = np.nan
    r = rank_within_date(df, "s")
    assert r.groupby(df["forecast_date"]).min().eq(1).all()
    assert r.iloc[0] == 50                   # NaN ranks last


def test_major_recall():
    m = major_recall(_toy(), "s", k=20)
    assert m["recall"] == 1.0 and m["total"] == 5


def test_bootstrap_ci_contains_mean():
    s = pd.Series(np.random.default_rng(0).normal(0.05, 0.1, 80), index=pd.date_range("2023-01-01", periods=80, freq="12D"))
    ci = moving_block_bootstrap(s, n=2000)
    assert ci["lo"] < ci["mean"] < ci["hi"]
    assert ci["n_dates"] == 80


def test_reliability_bins_sum():
    df = pd.DataFrame(dict(p=np.linspace(0, 1, 101), y=(np.linspace(0, 1, 101) > 0.5).astype(int)))
    rel = reliability(df, "p", bins=10)
    assert sum(r["n"] for r in rel) == 101
