"""Ranking and calibration metrics (spec §Validation protocol, Metrics)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss

from src import config


def rank_within_date(df: pd.DataFrame, score: str, seed: int = config.RANDOM_SEED) -> pd.Series:
    """1 = highest score on that forecast date. NaN scores rank last; ties broken at random (seeded)."""
    rng = np.random.default_rng(seed)
    jitter = pd.Series(rng.random(len(df)), index=df.index)
    s = df[score].fillna(-np.inf)
    key = pd.DataFrame({"d": df["forecast_date"], "s": s, "j": jitter})
    key = key.sort_values(["d", "s", "j"], ascending=[True, False, True])
    key["rank"] = key.groupby("d").cumcount() + 1
    return key["rank"].reindex(df.index)


def precision_at_k(df: pd.DataFrame, score: str, k: int = config.TOP_K) -> pd.Series:
    """Per forecast date: share of the top-k segments that lost >= threshold within 28 days."""
    r = rank_within_date(df, score)
    top = df[r <= k]
    n = df.groupby("forecast_date").size()
    p = top.groupby("forecast_date")["y"].mean()
    return p[n.reindex(p.index) >= k]


def major_recall(df: pd.DataFrame, score: str, k: int = config.TOP_K) -> dict:
    """Share of major events (>= 100 m) whose segment was in the top k beforehand."""
    r = rank_within_date(df, score)
    m = df["major"] == 1
    hits = int((m & (r <= k)).sum())
    total = int(m.sum())
    return dict(hits=hits, total=total, recall=hits / total if total else float("nan"))


def moving_block_bootstrap(diff_by_date: pd.Series, n: int = 4000, block: int = 3,
                           seed: int = config.RANDOM_SEED) -> dict:
    """95% CI of the mean of a per-date series, resampling blocks of consecutive dates.

    Consecutive forecast dates share overlapping 28-day windows, so dates are
    not independent; blocks of 3 passes (~36 days) keep that dependence.
    """
    v = diff_by_date.sort_index().to_numpy(dtype=float)
    v = v[np.isfinite(v)]
    T = len(v)
    if T == 0:
        return dict(mean=float("nan"), lo=float("nan"), hi=float("nan"), n_dates=0)
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(T / block))
    starts = rng.integers(0, max(T - block + 1, 1), size=(n, nb))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(n, -1)[:, :T]
    idx = np.minimum(idx, T - 1)
    means = v[idx].mean(axis=1)
    return dict(mean=float(v.mean()), lo=float(np.percentile(means, 2.5)),
                hi=float(np.percentile(means, 97.5)), n_dates=int(T), block=block, n_boot=n)


def pr_auc(df: pd.DataFrame, score: str) -> float:
    s = df[score].fillna(df[score].min() - 1 if df[score].notna().any() else 0)
    if df["y"].nunique() < 2:
        return float("nan")
    return float(average_precision_score(df["y"], s))


def brier(df: pd.DataFrame, prob: str) -> float:
    return float(brier_score_loss(df["y"], df[prob].clip(0, 1)))


def reliability(df: pd.DataFrame, prob: str, bins: int = 10) -> list[dict]:
    """Reliability diagram data with quantile-free fixed bins on [0, 1]."""
    edges = np.linspace(0, 1, bins + 1)
    b = np.clip(np.digitize(df[prob].clip(0, 1), edges[1:-1]), 0, bins - 1)
    out = []
    for i in range(bins):
        sel = b == i
        if sel.sum() == 0:
            continue
        out.append(dict(bin_lo=float(edges[i]), bin_hi=float(edges[i + 1]), n=int(sel.sum()),
                        mean_pred=float(df.loc[sel, prob].mean()), observed=float(df.loc[sel, "y"].mean())))
    return out


def summarise(df: pd.DataFrame, score: str, prob: str | None = None, k: int = config.TOP_K) -> dict:
    p = precision_at_k(df, score, k)
    monsoon = p[p.index.month.isin([6, 7, 8, 9, 10])]
    out = dict(
        precision_at_k=float(p.mean()) if len(p) else float("nan"),
        precision_at_k_monsoon=float(monsoon.mean()) if len(monsoon) else float("nan"),
        n_dates=int(len(p)), n_dates_monsoon=int(len(monsoon)),
        pr_auc=pr_auc(df, score),
        major=major_recall(df, score, k),
    )
    if prob:
        out["brier"] = brier(df, prob)
    return out
