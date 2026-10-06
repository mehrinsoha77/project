"""Generate (and optionally execute) the seven analysis notebooks.

The notebooks read the pipeline outputs committed under ``data/`` and never
re-run the heavy steps, so they execute in about a minute.

    python notebooks/make_notebooks.py --execute
"""
from __future__ import annotations

import argparse
from pathlib import Path

import nbformat as nbf

HERE = Path(__file__).resolve().parent

SETUP = """import sys, json
from pathlib import Path
ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT))
import numpy as np, pandas as pd, matplotlib.pyplot as plt
from src import config
M = config.METRICS_DIR
def load(name):
    p = M / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None
plt.rcParams.update({"figure.dpi": 110, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": "#e1e0d9", "axes.edgecolor": "#c3c2b7"})
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"
"""

NB: dict[str, list[tuple[str, str]]] = {}

NB["01_data_exploration"] = [
    ("md", "# 01 · Data exploration\n\nWhat the Sentinel-1 archive over the Kazipur–Chauhali reach looks like: how many passes, how regular, and what the radar sees."),
    ("code", SETUP),
    ("code", """cat = json.loads((config.PROCESSED / "s1_catalog.json").read_text())
passes = pd.DataFrame([dict(pass_id=p["pass_id"], date=pd.Timestamp(p["date"]), platform=p["platform"], slices=len(p["slices"])) for p in cat])
print(len(passes), "passes of relative orbit", config.S1_RELATIVE_ORBIT, passes.date.min().date(), "→", passes.date.max().date())
passes.groupby([passes.date.dt.year, "platform"]).size().unstack(fill_value=0)"""),
    ("code", """gaps = passes.date.diff().dt.days
fig, ax = plt.subplots(figsize=(9, 2.6))
ax.plot(passes.date, gaps, color=C1, lw=1.5, marker="o", ms=3)
ax.axhline(12, color="#898781", lw=1)
ax.set_ylabel("days since previous pass"); ax.set_title("Revisit on track 150 (12 days nominal)")
plt.show()
passes.loc[gaps > 24, ["date"]].assign(gap_days=gaps[gaps > 24])"""),
    ("code", """s = pd.read_csv(config.MASK_DIR / "mask_summary.csv", parse_dates=["date"])
fig, axes = plt.subplots(2, 1, figsize=(9, 4.6), sharex=True)
axes[0].plot(s.date, s.t_vv, color=C1, lw=1.5, label="VV Otsu threshold")
axes[0].plot(s.date, s.t_vh, color=C2, lw=1.5, label="VH Otsu threshold")
axes[0].set_ylabel("dB"); axes[0].legend(frameon=False, ncol=2)
axes[1].plot(s.date, s.water_area_km2, color=C1, lw=1.5)
axes[1].set_ylabel("dark-pixel area (km²)")
axes[1].set_title("Reach-wide 'water' — inflated by boro rice fields in Jan–Mar, so NOT used as stage")
plt.tight_layout(); plt.show()
print("Otsu outside plausible range on", int((~s.otsu_ok).sum()), "of", len(s), "passes")"""),
    ("code", """from src.masks.s1_io import read_pass_db
p = config.S1_RAW / "S1_20230712_S1A_r150.tif"
if p.exists():
    vv, vh, tags = read_pass_db(p)
    fig, ax = plt.subplots(1, 2, figsize=(9, 8))
    ax[0].imshow(vv[::4, ::4], cmap="gray", vmin=-25, vmax=0); ax[0].set_title("VV dB, 12 Jul 2023 (monsoon)")
    ax[1].hist(vv[::3, ::3].ravel(), bins=150, range=(-30, 5), color=C1)
    ax[1].set_title("Bimodal: water ~ −19 dB, land ~ −9 dB"); ax[1].set_xlabel("dB")
    for a in ax[:1]: a.set_xticks([]); a.set_yticks([])
    plt.tight_layout(); plt.show()
else:
    print("radar cache not present in this checkout (data/raw is regenerable: scripts/download_data.sh)")"""),
]

NB["02_water_mask_validation"] = [
    ("md", "# 02 · Water-mask validation\n\nRadar masks against cloud-free Sentinel-2 (tile 45RYH), and the geolocation correction found on the way."),
    ("code", SETUP),
    ("code", """geo = load("geolocation_offset")
print(json.dumps(geo, indent=1))"""),
    ("md", "**The shift.** Before correction, radar banks sat ~100 m west of the optical banks on *both* sides — a geolocation offset from the GCP grid's terrain height (~60 m above the ellipsoid, while the floodplain is below it). The fit above uses 2017–2019 pairs only."),
    ("code", """mv = load("mask_validation"); print(json.dumps(mv, indent=1))
pairs = pd.read_csv(M / "mask_validation_pairs.csv")
pairs[["pass_id", "s2_id", "days_apart", "s2_cloud", "iou_water", "iou_active_channel", "median_abs_err_m", "p90_abs_err_m", "mean_signed_err_m", "n_transects"]]"""),
    ("code", """cal = set(geo["pairs"]) if geo else set()
pairs["used_for_offset_fit"] = pairs.pass_id.isin(cal)
pairs.groupby("used_for_offset_fit")[["iou_active_channel", "median_abs_err_m"]].median()"""),
    ("code", """thumbs = sorted((M / "mask_pairs").glob("*.npz"))[:3]
if thumbs:
    fig, axes = plt.subplots(1, len(thumbs), figsize=(4 * len(thumbs), 6))
    for ax, f in zip(np.atleast_1d(axes), thumbs):
        z = np.load(f); s1, s2 = z["s1"], z["s2_channel"]
        img = np.zeros(s1.shape + (3,)); img[(s1 == 1) & (s2 == 1)] = [0.16, 0.47, 0.84]
        img[(s1 == 1) & (s2 == 0)] = [0.92, 0.41, 0.2]; img[(s1 == 0) & (s2 == 1)] = [0.1, 0.69, 0.48]
        img[s2 == 255] = 0.85
        ax.imshow(img); ax.set_title(f.stem.split("__")[0], fontsize=9); ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle("blue: both · orange: radar only · green: optical only · grey: no optical data")
    plt.tight_layout(); plt.show()
else:
    print("thumbnails are regenerated by python -m src.masks.validate_masks")"""),
]

NB["03_bank_line_analysis"] = [
    ("md", "# 03 · Bank-line analysis\n\nBank position on 870 transects at every pass, 2015–2025."),
    ("code", SETUP),
    ("code", """from src.banks.bank_position import load_positions
pos = load_positions()
print(pos.shape, "valid share", round(pos.bank_pos_m.notna().mean(), 3))
pos.groupby(pos.date.dt.year)["bank_pos_m"].apply(lambda v: v.notna().mean()).rename("valid share by year")"""),
    ("code", """w = pos.pivot_table(index="transect_id", columns="date", values="bank_pos_m")
first = w.T.iloc[:20].median(); last = w.T.iloc[-20:].median()
(last - first).rename("net_retreat_m").sort_values(ascending=False).head(10).to_frame()"""),
    ("code", """from src.banks.transects import load_transects
tr = load_transects().set_index("transect_id")
net2 = (last - first).rename("net").to_frame().join(tr[["bank", "chainage_m"]])
fig, ax = plt.subplots(figsize=(9, 3))
for b, c in (("W", C1), ("E", C2)):
    g = net2[net2.bank == b].sort_values("chainage_m")
    ax.plot(g.chainage_m / 1000, g.net, color=c, lw=1.5, label={"W": "west bank", "E": "east bank"}[b])
ax.axhline(0, color="#898781", lw=1); ax.set_xlabel("km from the north end of the reach"); ax.set_ylabel("m landward")
ax.set_title("Net bank movement, first 20 passes → last 20 passes (positive = land lost)"); ax.legend(frameon=False)
plt.show()"""),
    ("code", """top = net2.net.sort_values(ascending=False).index[:4]
fig, ax = plt.subplots(figsize=(9, 3.4))
for k, t in enumerate(top):
    ax.plot(w.columns, w.loc[t], lw=1.5, marker="o", ms=2, label=t, color=[C1, C2, C3, "#4a3aa7"][k])
ax.set_ylabel("bank position (m, landward +)"); ax.legend(frameon=False, ncol=4); ax.set_title("The four most active segments")
plt.show()"""),
]

NB["04_feature_engineering"] = [
    ("md", "# 04 · Feature engineering\n\nAll features are as-of the forecast pass (see `tests/test_no_leakage.py`)."),
    ("code", SETUP),
    ("code", """from src.features.build_features import FEATURE_GROUPS, load_features
from src.models.data import load_dataset
df = load_dataset()
print(df.shape); pd.Series({g: ", ".join(v) for g, v in FEATURE_GROUPS.items()}, name="features").to_frame()"""),
    ("code", """train = df[df.year.isin(config.TRAIN_YEARS)]
rows = []
for g, cols in FEATURE_GROUPS.items():
    for c in cols:
        x = train[c]
        rows.append(dict(group=g, feature=c, coverage=x.notna().mean(), spearman_with_retreat=train[[c, "retreat_m"]].corr("spearman").iloc[0, 1]))
pd.DataFrame(rows).round(3)"""),
    ("code", """st = df.drop_duplicates("forecast_date")[["forecast_date", "stage_km2"]]
fig, ax = plt.subplots(figsize=(9, 2.8))
ax.plot(st.forecast_date, st.stage_km2, color=C1, lw=1.5)
ax.set_ylabel("km²"); ax.set_title("Stage proxy: open water inside the braid belt")
plt.show()"""),
    ("code", """m = df.groupby(df.forecast_date.dt.month)["y"].mean()
fig, ax = plt.subplots(figsize=(6, 2.6)); ax.bar(m.index, m.values * 100, color=C1, width=0.6)
ax.set_xlabel("month of forecast"); ax.set_ylabel("% positive"); ax.set_title("Share of segments losing ≥ threshold in 28 days")
plt.show()"""),
]

NB["05_model_training"] = [
    ("md", "# 05 · Model training\n\nLightGBM trained on 2015–2021, tuned on 2022 over a fixed grid; isotonic calibration on 2022."),
    ("code", SETUP),
    ("code", """p = json.loads((config.PROCESSED / "models/m1_params.json").read_text())
print({k: v for k, v in p.items() if k not in ("trials", "features")})
pd.DataFrame(p["trials"]).sort_values("val_precision_at_20", ascending=False)"""),
    ("code", """print(json.dumps(load("baselines_val_2022"), indent=1))"""),
    ("code", """cal = load("calibration_val_2022")
fig, ax = plt.subplots(figsize=(4.5, 4.5))
for name, c in (("M1_raw", C1), ("B0_persistence", C2)):
    r = pd.DataFrame(cal[name]["reliability_val"])
    ax.plot(r.mean_pred * 100, r.observed * 100, marker="o", color=c, lw=1.5, label=name)
ax.plot([0, 100], [0, 100], ls="--", color="#898781", lw=1)
ax.set_xlabel("predicted %"); ax.set_ylabel("observed %"); ax.legend(frameon=False); ax.set_title("Calibration on 2022 (in-sample for isotonic)")
plt.show()"""),
]

NB["06_validation_results"] = [
    ("md", "# 06 · Validation results\n\nThe held-out years 2023–2025, scored once. Every number is read from `test_results.json`."),
    ("code", SETUP),
    ("code", """r = load("test_results"); t = r["temporal"]
tab = pd.DataFrame({k: dict(precision_at_20=v["precision_at_k"], p20_monsoon=v["precision_at_k_monsoon"], pr_auc=v["pr_auc"], brier=v.get("brier"), major_recall=v["major"]["recall"])
                    for k, v in (("M1", t["M1"]), ("B0 persistence", t["B0_persistence"]), ("B1 history", t["B1_history"]))}).T
print("success levels:", r["success_levels"]); tab.round(4)"""),
    ("code", """print("M1 − B0, all dates:", t["M1_minus_B0"]["all_dates"])
print("M1 − B0, monsoon:  ", t["M1_minus_B0"]["monsoon"])
print("spatial M1 − B0:   ", r["spatial"]["M1_minus_B0"]["all_dates"])"""),
    ("code", """pd_ = pd.DataFrame(t["M1_minus_B0"]["per_date"]); pd_["date"] = pd.to_datetime(pd_.date)
fig, ax = plt.subplots(figsize=(9, 3))
ax.plot(pd_.date, pd_.model * 100, color=C1, lw=1.5, label="M1")
ax.plot(pd_.date, pd_.baseline * 100, color=C2, lw=1.5, label="B0 persistence")
ax.set_ylabel("precision@20 (%)"); ax.legend(frameon=False); ax.set_title("Per forecast date, 2023–2025")
plt.show()"""),
    ("code", """fig, ax = plt.subplots(figsize=(4.5, 4.5))
for name, c in (("reliability_M1", C1), ("reliability_B0", C2)):
    rr = pd.DataFrame(t[name]); ax.plot(rr.mean_pred * 100, rr.observed * 100, marker="o", color=c, lw=1.5, label=name.split("_")[1])
ax.plot([0, 100], [0, 100], ls="--", color="#898781", lw=1); ax.set_xlabel("predicted %"); ax.set_ylabel("observed %")
ax.legend(frameon=False); ax.set_title("Reliability on test years"); plt.show()"""),
    ("code", """pd.DataFrame({y: dict(M1=v["M1"]["precision_at_k"], B0=v["B0"]["precision_at_k"]) for y, v in t["per_year"].items()}).T.round(3)"""),
    ("md", "## Misses\n\nThe largest test-year retreats that the model did not put in its top 20."),
    ("code", """pred = pd.read_parquet(config.PROCESSED / "models/test_predictions.parquet") if (config.PROCESSED / "models/test_predictions.parquet").exists() else pd.concat([pd.read_parquet(p) for p in sorted(config.DEMO_DIR.glob("predictions_202[345].parquet"))])
rk = "rank" if "rank" in pred else None
if rk is None:
    pred["rank"] = pred.groupby("forecast_date")["M1"].rank(ascending=False)
miss = pred[(pred.y == 1) & (pred["rank"] > 20)].sort_values("retreat_m", ascending=False)
miss[["transect_id", "forecast_date", "retreat_m", "rank", "ret_84_m", "raw_last_change_m"]].head(10)"""),
]

NB["07_ablation_study"] = [
    ("md", "# 07 · Ablation study and feature importance\n\nRemove one feature group, retrain with M1's settings, recalibrate on 2022, score. Reporting only."),
    ("code", SETUP),
    ("code", """a = load("ablation")
rows = {k: dict(n_features=v["n_features"], val_p20=v["val_2022"]["precision_at_k"], test_p20=v["test_2023_2025"]["precision_at_k"],
                d_test_p20=v["test_2023_2025"]["delta_precision_at_k_vs_full"], test_pr_auc=v["test_2023_2025"]["pr_auc"])
        for k, v in a.items() if not k.startswith("_")}
print(a["_not_built"]); pd.DataFrame(rows).T.round(4)"""),
    ("code", """imp = pd.DataFrame(load("importance")).head(15)
fig, ax = plt.subplots(figsize=(6, 4.2)); ax.barh(imp.feature[::-1], imp.mean_abs_shap[::-1], color=C1, height=0.6)
ax.set_xlabel("mean |SHAP| (log-odds)"); ax.set_title("Global feature importance, test years"); plt.tight_layout(); plt.show()"""),
    ("code", """import shap
from src.models.train_lgbm import load_model, load_params
from src.models.data import load_dataset
model, info = load_model(), load_params()
df = load_dataset(); test = df[df.year.isin(config.TEST_YEARS)].sample(3000, random_state=0)
sv = shap.TreeExplainer(model).shap_values(test[info["features"]])
sv = sv[1] if isinstance(sv, list) else sv
shap.summary_plot(sv, test[info["features"]], show=False, max_display=12); plt.tight_layout(); plt.show()"""),
]


def build(execute: bool) -> None:
    for name, cells in NB.items():
        nb = nbf.v4.new_notebook()
        nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
        nb.cells = [nbf.v4.new_markdown_cell(src) if kind == "md" else nbf.v4.new_code_cell(src) for kind, src in cells]
        path = HERE / f"{name}.ipynb"
        if execute:
            from nbconvert.preprocessors import ExecutePreprocessor
            ExecutePreprocessor(timeout=900, kernel_name="python3").preprocess(nb, {"metadata": {"path": str(HERE)}})
        nbf.write(nb, path)
        print("wrote", path.name)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    build(ap.parse_args().execute)
