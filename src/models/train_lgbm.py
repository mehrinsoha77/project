"""Train M1: LightGBM on the feature table (spec §Method 5).

Train on 2015–2021, tune on 2022. Test years are not loaded here.

Tuning: a small grid over tree size, minimum leaf size and learning rate;
the number of trees is chosen by early stopping on 2022 log-loss, and the
configuration with the best mean precision@20 on 2022 wins (average precision
breaks ties). The grid is fixed in code, so the search is reproducible.

CLI::

    python -m src.models.train_lgbm
"""
from __future__ import annotations

import argparse
import itertools
import json
import logging
from pathlib import Path

import lightgbm as lgb
import pandas as pd

from src import config
from src.features.build_features import ALL_FEATURES
from src.models.data import load_dataset, temporal_split
from src.models.metrics import pr_auc, precision_at_k

log = logging.getLogger(__name__)

MODEL_DIR = config.PROCESSED / "models"
MODEL_PATH = MODEL_DIR / "m1_lgbm.txt"
PARAMS_PATH = MODEL_DIR / "m1_params.json"

GRID = {
    "num_leaves": [15, 31, 63],
    "min_child_samples": [50, 200],
    "learning_rate": [0.03, 0.1],
}
BASE_PARAMS = dict(objective="binary", feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1,
                   lambda_l2=1.0, verbose=-1, seed=config.RANDOM_SEED, num_threads=4,
                   deterministic=True, force_row_wise=True)


def fit(train: pd.DataFrame, features: list[str], params: dict, num_boost_round: int,
        valid: pd.DataFrame | None = None) -> lgb.Booster:
    dtrain = lgb.Dataset(train[features], label=train["y"], free_raw_data=False)
    kw = {}
    if valid is not None:
        dval = lgb.Dataset(valid[features], label=valid["y"], reference=dtrain)
        kw = dict(valid_sets=[dval], callbacks=[lgb.early_stopping(50, verbose=False)])
    return lgb.train({**BASE_PARAMS, **params}, dtrain, num_boost_round=num_boost_round, **kw)


def tune(train: pd.DataFrame, val: pd.DataFrame, features: list[str]) -> tuple[dict, list[dict]]:
    trials = []
    for nl, mcs, lr in itertools.product(*GRID.values()):
        params = dict(num_leaves=nl, min_child_samples=mcs, learning_rate=lr)
        b = fit(train, features, params, 2000, valid=val)
        v = val.assign(score=b.predict(val[features], num_iteration=b.best_iteration))
        p20 = float(precision_at_k(v, "score").mean())
        ap = pr_auc(v, "score")
        trials.append(dict(**params, best_iteration=int(b.best_iteration), val_precision_at_20=p20, val_pr_auc=ap))
        log.info("%s -> P@20 %.3f AP %.3f (%d trees)", params, p20, ap, b.best_iteration)
    best = max(trials, key=lambda r: (r["val_precision_at_20"], r["val_pr_auc"]))
    return best, trials


def train_model(df: pd.DataFrame | None = None, features: list[str] | None = None,
                save: bool = True) -> tuple[lgb.Booster, dict]:
    df = df if df is not None else load_dataset()
    features = features or ALL_FEATURES
    train, val, _ = temporal_split(df)
    best, trials = tune(train, val, features)
    params = {k: best[k] for k in GRID}
    model = fit(train, features, params, best["best_iteration"])
    info = dict(params=params, num_boost_round=best["best_iteration"], features=features,
                train_rows=int(len(train)), train_positive_rate=float(train["y"].mean()),
                val_rows=int(len(val)), val_precision_at_20=best["val_precision_at_20"],
                val_pr_auc=best["val_pr_auc"], trials=trials)
    if save:
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        model.save_model(str(MODEL_PATH))
        PARAMS_PATH.write_text(json.dumps(info, indent=2))
    return model, info


def load_model(path: Path = MODEL_PATH) -> lgb.Booster:
    return lgb.Booster(model_file=str(path))


def load_params() -> dict:
    return json.loads(PARAMS_PATH.read_text())


def main() -> None:
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    logging.basicConfig(level=logging.INFO)
    _, info = train_model()
    print(json.dumps({k: v for k, v in info.items() if k != "trials"}, indent=2))


if __name__ == "__main__":
    main()
