"""Ablations: remove each feature group in turn and report the change.

Each ablated model is retrained on 2015–2021 with M1's tuned settings
(same tree count), recalibrated on 2022 and scored on 2022 and 2023–2025.
Ablations are reporting only — they never change which model is used.

Groups that were *not built* in this build are listed with status
``not_built`` instead of a number (coherence, neural-operator surrogate).

CLI::

    python -m src.models.ablate
"""
from __future__ import annotations

import argparse
import json
import logging

from src import config
from src.features.build_features import FEATURE_GROUPS
from src.models.calibrate import apply, fit_isotonic
from src.models.data import load_dataset, temporal_split
from src.models.metrics import summarise
from src.models.train_lgbm import fit, load_params

log = logging.getLogger(__name__)
OUT = config.METRICS_DIR / "ablation.json"


def run() -> dict:
    df = load_dataset()
    train, val, test = temporal_split(df)
    info = load_params()
    base_feats = info["features"]
    variants = {"full": base_feats}
    for g, cols in FEATURE_GROUPS.items():
        variants[f"-{g}"] = [f for f in base_feats if f not in cols]
    out = {}
    for name, feats in variants.items():
        m = fit(train, feats, info["params"], info["num_boost_round"])
        v = val.assign(raw=m.predict(val[feats]))
        iso = fit_isotonic(v["raw"], v["y"])
        fill = float(v["raw"].min())
        res = {}
        for split_name, part in (("val_2022", v), ("test_2023_2025", test.assign(raw=m.predict(test[feats])))):
            part = part.assign(p=apply(iso, part["raw"], fill) + 1e-9 * part["raw"])
            res[split_name] = summarise(part, "p", "p")
        out[name] = dict(n_features=len(feats), **res)
        log.info("%s: val P@20 %.3f, test P@20 %.3f", name, res["val_2022"]["precision_at_k"],
                 res["test_2023_2025"]["precision_at_k"])
    full = out["full"]
    for name, r in out.items():
        for sp in ("val_2022", "test_2023_2025"):
            r[sp]["delta_precision_at_k_vs_full"] = r[sp]["precision_at_k"] - full[sp]["precision_at_k"]
            r[sp]["delta_pr_auc_vs_full"] = r[sp]["pr_auc"] - full[sp]["pr_auc"]
    out["_not_built"] = {
        "coherence": "Sentinel-1 coherence needs SLC interferometric processing; not built in this run.",
        "surrogate_velocity": "Neural-operator surrogate (optional research track) not built.",
    }
    OUT.write_text(json.dumps(out, indent=2))
    return out


def main() -> None:
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    logging.basicConfig(level=logging.INFO)
    out = run()
    for k, v in out.items():
        if not k.startswith("_"):
            print(f"{k:22s} val {v['val_2022']['precision_at_k']:.3f}  test {v['test_2023_2025']['precision_at_k']:.3f}")


if __name__ == "__main__":
    main()
