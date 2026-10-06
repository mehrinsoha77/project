"""The one comparison that decides the project (spec §Validation protocol).

Does M1 rank at-risk segments better than persistence on years it never saw?

* **Temporal hold-out** – trained 2015–2021, tuned and calibrated on 2022,
  tested once on 2023–2025.
* **Spatial hold-out** – trained on the upstream half of the reach (2015–2021,
  tuned on upstream 2022), tested on the downstream half in 2023–2025.

Reported: precision@20 per forecast date (mean, monsoon-only mean), recall
of major (>= 100 m) events in the top 20, PR-AUC, Brier score, reliability
diagram, and a moving-block bootstrap 95% CI of the per-date precision@20
difference M1 - B0. Success levels are evaluated mechanically from these.

The test years are touched once. The first run writes
``test_results.json``; any re-run needs ``--rerun-reason`` and is appended
to ``test_runs.log`` so the history stays visible.

CLI::

    python -m src.models.evaluate
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import subprocess

import pandas as pd

from src import config
from src.models.baselines import BASELINES, add_baseline_scores
from src.models.calibrate import apply, calibrate, fit_isotonic, load_calibrators
from src.models.data import load_dataset, temporal_split, upstream_mask
from src.models.metrics import moving_block_bootstrap, precision_at_k, reliability, summarise
from src.models.train_lgbm import fit, load_model, load_params, tune

log = logging.getLogger(__name__)

RESULTS = config.METRICS_DIR / "test_results.json"
RUN_LOG = config.METRICS_DIR / "test_runs.log"
PRED_TEST = config.PROCESSED / "models" / "test_predictions.parquet"


def _git_rev() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=config.ROOT,
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


def score_temporal(df: pd.DataFrame) -> pd.DataFrame:
    _, _, test = temporal_split(df)
    model, info = load_model(), load_params()
    cals = load_calibrators()
    test = add_baseline_scores(test)
    test["M1_raw"] = model.predict(test[info["features"]])
    for name in ["M1_raw", *BASELINES]:
        iso, fill = cals[name]
        test[f"{name}_p"] = apply(iso, test[name], fill)
    test["M1"] = test["M1_raw_p"] + 1e-9 * test["M1_raw"]   # calibrated prob; raw score breaks isotonic ties
    return test


def compare(test: pd.DataFrame, model_col: str, base_col: str) -> dict:
    pm = precision_at_k(test, model_col)
    pb = precision_at_k(test, base_col)
    diff = (pm - pb).dropna()
    mon = diff[diff.index.month.isin([6, 7, 8, 9, 10])]
    return dict(all_dates=moving_block_bootstrap(diff), monsoon=moving_block_bootstrap(mon),
                per_date=[dict(date=d.strftime("%Y-%m-%d"), model=float(pm[d]), baseline=float(pb[d]))
                          for d in pm.index])


def spatial(df: pd.DataFrame) -> dict:
    train, val, test = temporal_split(df)
    up_tr, up_val = train[upstream_mask(train)], val[upstream_mask(val)]
    down_te = test[~upstream_mask(test)].copy()
    info = load_params()
    feats = info["features"]
    best, _ = tune(up_tr, up_val, feats)
    params = {k: best[k] for k in ("num_leaves", "min_child_samples", "learning_rate")}
    m = fit(up_tr, feats, params, best["best_iteration"])
    up_val = up_val.assign(raw=m.predict(up_val[feats]))
    iso = fit_isotonic(up_val["raw"], up_val["y"])
    down_te = add_baseline_scores(down_te)
    down_te["raw"] = m.predict(down_te[feats])
    down_te["M1_spatial"] = apply(iso, down_te["raw"], float(up_val["raw"].min())) + 1e-9 * down_te["raw"]
    b_iso = fit_isotonic(up_val["ret_84_m"], up_val["y"])
    down_te["B0_p"] = apply(b_iso, down_te["B0_persistence"], float(up_val["ret_84_m"].min()))
    return dict(
        params=params, num_boost_round=int(best["best_iteration"]),
        train_segments=int(up_tr["transect_id"].nunique()), test_segments=int(down_te["transect_id"].nunique()),
        M1=summarise(down_te, "M1_spatial", "M1_spatial"),
        B0_persistence=summarise(down_te, "B0_persistence", "B0_p"),
        M1_minus_B0=compare(down_te, "M1_spatial", "B0_persistence"),
    )


def success_levels(res: dict) -> dict:
    mv = json.loads((config.METRICS_DIR / "mask_validation.json").read_text())
    cov = res.get("detection_coverage", {})
    minimum = (mv["bank_error_median_m"] <= 20.0) and cov.get("passes_processed", 0) == cov.get("passes_in_catalog", -1)
    t = res["temporal"]["M1_minus_B0"]["all_dates"]
    good = t["lo"] > 0
    s = res["spatial"]["M1_minus_B0"]["all_dates"]
    strong = good and s["lo"] > 0 and res["temporal"]["M1"]["brier"] < res["temporal"]["B0_persistence"]["brier"]
    return dict(minimum=bool(minimum), good=bool(good), strong=bool(strong))


def run(rerun_reason: str | None = None) -> dict:
    if RESULTS.exists() and not rerun_reason:
        raise SystemExit(f"{RESULTS} exists: the test years were already used. "
                         "Pass --rerun-reason '<why>' to re-run; it will be logged.")
    df = load_dataset()
    calibrate(df)                                  # (re)fit calibrators on 2022 for the saved model
    test = score_temporal(df)
    PRED_TEST.parent.mkdir(parents=True, exist_ok=True)
    keep = ["transect_id", "forecast_date", "target_date", "bank", "chainage_m", "retreat_m", "y", "major",
            "M1", "M1_raw", "B0_persistence", "B1_history", "B0_persistence_p", "B1_history_p",
            "ret_84_m", "ret_365_m", "raw_last_change_m", "bank_pos_m"]
    test[keep].to_parquet(PRED_TEST, index=False)

    summary = pd.read_csv(config.MASK_DIR / "mask_summary.csv")
    catalog = json.loads((config.PROCESSED / "s1_catalog.json").read_text())
    res = dict(
        generated=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        git_rev=_git_rev(),
        test_years=list(config.TEST_YEARS),
        threshold_m=json.loads((config.METRICS_DIR / "label_stats.json").read_text())["threshold_m"],
        detection_coverage=dict(passes_in_catalog=len(catalog), passes_processed=int(len(summary))),
        temporal=dict(
            rows=int(len(test)), forecast_dates=int(test["forecast_date"].nunique()),
            positive_rate=float(test["y"].mean()),
            M1=summarise(test, "M1", "M1"),
            B0_persistence=summarise(test, "B0_persistence", "B0_persistence_p"),
            B1_history=summarise(test, "B1_history", "B1_history_p"),
            M1_minus_B0=compare(test, "M1", "B0_persistence"),
            M1_minus_B1=compare(test, "M1", "B1_history"),
            reliability_M1=reliability(test, "M1"),
            reliability_B0=reliability(test, "B0_persistence_p"),
            per_year={int(y): dict(M1=summarise(g, "M1", "M1"), B0=summarise(g, "B0_persistence", "B0_persistence_p"))
                      for y, g in test.groupby("year")},
        ),
        spatial=spatial(df),
    )
    res["success_levels"] = success_levels(res)
    entry = f"{res['generated']} rev={res['git_rev']} reason={rerun_reason or 'first run'}\n"
    with open(RUN_LOG, "a") as f:
        f.write(entry)
    RESULTS.write_text(json.dumps(res, indent=2))
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rerun-reason", default=None)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO)
    res = run(a.rerun_reason)
    t = res["temporal"]
    print(json.dumps(dict(M1=t["M1"], B0=t["B0_persistence"], B1=t["B1_history"],
                          diff=t["M1_minus_B0"]["all_dates"], spatial_diff=res["spatial"]["M1_minus_B0"]["all_dates"],
                          levels=res["success_levels"]), indent=2))


if __name__ == "__main__":
    main()
