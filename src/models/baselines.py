"""The two baselines every model claim is measured against (spec §Method 5).

* **B0 persistence** – rank segments by retreat over the last 84 days.
* **B1 history**     – rank segments by retreat over the previous 12 months.

Both are as-of features (``ret_84_m``, ``ret_365_m``), so they use exactly the
information the model has. For Brier scores they are turned into
probabilities by isotonic regression fitted on the validation year, the same
treatment the model gets.

CLI::

    python -m src.models.baselines      # scores both baselines on 2022
"""
from __future__ import annotations

import argparse
import json

import pandas as pd

from src import config
from src.models.data import load_dataset, temporal_split
from src.models.metrics import summarise

BASELINES = {"B0_persistence": "ret_84_m", "B1_history": "ret_365_m"}


def add_baseline_scores(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for name, col in BASELINES.items():
        df[name] = df[col]
    return df


def main() -> None:
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    _, val, _ = temporal_split(load_dataset())
    val = add_baseline_scores(val)
    res = {name: summarise(val, name) for name in BASELINES}
    config.METRICS_DIR.mkdir(parents=True, exist_ok=True)
    (config.METRICS_DIR / "baselines_val_2022.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
