"""Plain-language reasons for each flagged segment, from SHAP values.

For a segment's prediction, TreeSHAP splits the model's log-odds into one
contribution per feature. We take the features that pushed risk *up* the
most, group them (e.g. the three recent-retreat windows count as one
reason), and render each group with the segment's actual values, e.g.

    "Bank retreated 64 m in the last 4 weeks"
    "Main channel is 120 m from the bank and moved 90 m closer"

Reasons describe what the model used, not proven causes.

CLI::

    python -m src.explain.shap_reasons --date 2024-08-23
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from src.features.build_features import FEATURE_GROUPS

REASON_GROUP = {f: g for g, cols in FEATURE_GROUPS.items() for f in cols}
# finer split of channel geometry into its own reasons
for f in ("dist_main_channel_m", "d_dist_main_28_m"):
    REASON_GROUP[f] = "main_channel"
for f in ("char_shield_frac",):
    REASON_GROUP[f] = "char_shield"
for f in ("near_channel_width_m", "nearbank_water_frac"):
    REASON_GROUP[f] = "near_bank_channel"
for f in ("baseline_curvature", "embayment_m"):
    REASON_GROUP[f] = "bank_shape"


def _m(v: float) -> str:
    return f"{abs(v):,.0f} m"


def render(group: str, row: pd.Series) -> str | None:
    g = row.get
    if group == "recent_retreat":
        parts = []
        if np.isfinite(g("ret_28_m", np.nan)) and g("ret_28_m") > 5:
            parts.append(f"Bank retreated {_m(g('ret_28_m'))} in the last 4 weeks")
        elif np.isfinite(g("ret_84_m", np.nan)) and g("ret_84_m") > 5:
            parts.append(f"Bank retreated {_m(g('ret_84_m'))} in the last 12 weeks")
        if np.isfinite(g("raw_last_change_m", np.nan)) and g("raw_last_change_m") > 10:
            parts.append(f"latest pass shows a further {_m(g('raw_last_change_m'))} (unconfirmed)")
        if not parts:
            return "Little recent retreat, but the recent pattern still raises risk"
        return "; ".join(parts)
    if group == "history":
        v = g("ret_365_m", np.nan)
        return f"Lost {_m(v)} of bank over the past year" if np.isfinite(v) and v > 0 else "Past-year history raises risk"
    if group == "main_channel":
        d, dd = g("dist_main_channel_m", np.nan), g("d_dist_main_28_m", np.nan)
        s = f"Main flowing channel is {_m(d)} from the bank" if np.isfinite(d) else "Main channel position"
        if np.isfinite(dd) and dd < -20:
            s += f" and moved {_m(dd)} closer in 4 weeks"
        return s
    if group == "char_shield":
        v = g("char_shield_frac", np.nan)
        return "No char shields this bank from the flow" if np.isfinite(v) and v < 0.15 else "Little char protection in front of the bank"
    if group == "near_bank_channel":
        w = g("near_channel_width_m", np.nan)
        return f"A {_m(w)}-wide channel runs along the bank" if np.isfinite(w) else "Deep water close to the bank"
    if group == "bank_shape":
        return "Bank sits on an outer bend / in a recess"
    if group == "water_level":
        c = g("stage_change_12d", np.nan)
        if np.isfinite(c) and c > 5:
            return "River is rising (more open water than 12 days ago)"
        if np.isfinite(c) and c < -5:
            return "River is falling after high water"
        return "River stage is typical of high-erosion periods"
    if group == "season":
        return "Monsoon season"
    if group == "neighbours":
        v = g("nb_ret_84_m", np.nan)
        return f"Neighbouring segments retreated {_m(v)} on average in 12 weeks" if np.isfinite(v) and v > 0 else "Nearby segments are active"
    if group == "bank_height":
        h = g("bank_height_m", np.nan)
        return f"Bank height about {h:.1f} m above the river (DEM)" if np.isfinite(h) else None
    return None


def reasons_for(shap_row: np.ndarray, features: list[str], row: pd.Series, top: int = 3) -> list[dict]:
    contrib: dict[str, float] = {}
    for f, v in zip(features, shap_row):
        grp = REASON_GROUP.get(f, f)
        contrib[grp] = contrib.get(grp, 0.0) + float(v)
    ranked = sorted(((g, v) for g, v in contrib.items() if v > 0), key=lambda x: -x[1])[:top]
    out = []
    for g, v in ranked:
        text = render(g, row)
        if text:
            out.append(dict(group=g, text=text, shap=round(v, 4)))
    return out


def explain(model, X: pd.DataFrame, features: list[str], top: int = 3) -> list[list[dict]]:
    """Reasons for every row in X (use on the top-k rows; TreeSHAP is fast but not free)."""
    contribs = model.predict(X[features], pred_contrib=True)   # LightGBM's built-in TreeSHAP
    shap_vals = contribs[:, :-1]
    return [reasons_for(shap_vals[i], features, X.iloc[i], top) for i in range(len(X))]


def global_importance(model, X: pd.DataFrame, features: list[str]) -> list[dict]:
    """Mean |SHAP| per feature and per reason group."""
    contribs = model.predict(X[features], pred_contrib=True)[:, :-1]
    imp = np.abs(contribs).mean(axis=0)
    per_feature = sorted(({"feature": f, "mean_abs_shap": float(v)} for f, v in zip(features, imp)),
                         key=lambda r: -r["mean_abs_shap"])
    return per_feature


def main() -> None:
    from src.models.data import load_dataset
    from src.models.train_lgbm import load_model, load_params

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", required=True)
    ap.add_argument("--k", type=int, default=20)
    a = ap.parse_args()
    df = load_dataset()
    d = df[df["forecast_date"] == pd.Timestamp(a.date)].copy()
    model, info = load_model(), load_params()
    d["score"] = model.predict(d[info["features"]])
    top = d.nlargest(a.k, "score")
    for (_, r), rs in zip(top.iterrows(), explain(model, top, info["features"])):
        print(r["transect_id"], f"{r['score']:.3f}", json.dumps([x["text"] for x in rs]))


if __name__ == "__main__":
    main()
