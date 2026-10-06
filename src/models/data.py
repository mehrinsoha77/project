"""Join features and labels into the modelling table, and split it."""
from __future__ import annotations

import pandas as pd

from src import config
from src.features.build_features import load_features
from src.labels.make_labels import LABELS_ALL


def load_dataset() -> pd.DataFrame:
    X = load_features()
    y = pd.read_parquet(LABELS_ALL)
    df = X.merge(y[["transect_id", "forecast_date", "target_date", "retreat_m", "y", "major"]],
                 on=["transect_id", "forecast_date"], how="inner")
    return df.sort_values(["forecast_date", "transect_id"]).reset_index(drop=True)


def temporal_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return (df[df["year"].isin(config.TRAIN_YEARS)].copy(),
            df[df["year"] == config.VAL_YEAR].copy(),
            df[df["year"].isin(config.TEST_YEARS)].copy())


def upstream_mask(df: pd.DataFrame) -> pd.Series:
    """Upstream (northern) half of each bank, split at the bank's median chainage.

    Chainage runs from the north end of the reach, so small chainage = upstream.
    """
    med = df.groupby("bank")["chainage_m"].transform(lambda c: c.drop_duplicates().median())
    return df["chainage_m"] <= med
