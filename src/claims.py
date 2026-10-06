"""The claims ledger, computed from the metrics files (spec §Claims ledger).

No claim reaches a slide, the README or the dashboard unless its status here
is *Measured*. Statuses:

* Measured – an experiment in this repository produced the number;
* Not met  – measured, and the target was missed (reported, not hidden);
* Target   – not measured yet;
* Not built – the component was not built in this run;
* Dropped  – v2.0 claims that no experiment can support.

CLI::

    python -m src.claims          # prints the ledger and writes docs/CLAIMS_LEDGER.md's table
"""
from __future__ import annotations

import json

from src import config

M = config.METRICS_DIR


def _load(name: str) -> dict | None:
    p = M / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def _ece(rel: list[dict]) -> float:
    n = sum(r["n"] for r in rel)
    return sum(r["n"] * abs(r["mean_pred"] - r["observed"]) for r in rel) / n if n else float("nan")


def ledger() -> list[dict]:
    mv, tr, tm = _load("mask_validation"), _load("test_results"), _load("timing")
    out = []

    if mv:
        ok = mv["bank_error_median_m"] <= 20.0
        out.append(dict(claim="Radar bank lines match Sentinel-2 within a median of 20 m",
                        status="Measured" if ok else "Not met",
                        value=(f"median {mv['bank_error_median_m']:.0f} m, 90th pct {mv['bank_error_p90_m']:.0f} m over "
                               f"{mv['n_transect_comparisons']} transect comparisons in {mv['n_pairs']} S1/S2 pairs "
                               f"(≤{mv['max_days_apart']} days apart); water IoU median {mv['iou_median']:.2f}"),
                        how="Comparison against cloud-free Sentinel-2 L2A (MNDWI) scenes of tile 45RYH"))
    else:
        out.append(dict(claim="Radar bank lines match Sentinel-2 within a median of 20 m", status="Target",
                        how="Comparison against at least 10 cloud-free Sentinel-2 scenes"))

    if tr:
        cov = tr["detection_coverage"]
        ok = cov["passes_processed"] == cov["passes_in_catalog"]
        out.append(dict(claim="Detection runs on every pass from 2015 to 2025 for the chosen reach",
                        status="Measured" if ok else "Not met",
                        value=f"{cov['passes_processed']} of {cov['passes_in_catalog']} track-150 passes in the archive processed",
                        how="Count of passes processed versus passes available in the public Sentinel-1 archive"))
        t = tr["temporal"]
        d = t["M1_minus_B0"]["all_dates"]
        out.append(dict(claim="Model beats persistence on precision@20 for 2023–2025",
                        status="Measured" if d["lo"] > 0 else "Not met",
                        value=(f"P@20 {t['M1']['precision_at_k']:.1%} vs {t['B0_persistence']['precision_at_k']:.1%}; "
                               f"difference {d['mean']*100:+.1f} pts (95% CI {d['lo']*100:+.1f} to {d['hi']*100:+.1f}), "
                               f"{d['n_dates']} forecast dates"),
                        how="Temporal hold-out, moving-block bootstrap over forecast dates"))
        s = tr["spatial"]
        ds = s["M1_minus_B0"]["all_dates"]
        out.append(dict(claim="Model beats persistence on the downstream half of the reach",
                        status="Measured" if ds["lo"] > 0 else "Not met",
                        value=(f"P@20 {s['M1']['precision_at_k']:.1%} vs {s['B0_persistence']['precision_at_k']:.1%}; "
                               f"difference {ds['mean']*100:+.1f} pts (95% CI {ds['lo']*100:+.1f} to {ds['hi']*100:+.1f})"),
                        how="Spatial hold-out: trained upstream half, tested downstream half, 2023–2025"))
        ece = _ece(t["reliability_M1"])
        ok = ece <= 0.05 and t["M1"]["brier"] < t["B0_persistence"]["brier"]
        out.append(dict(claim="Risk probabilities are calibrated",
                        status="Measured" if ok else "Not met",
                        value=(f"Brier {t['M1']['brier']:.4f} vs persistence {t['B0_persistence']['brier']:.4f}; "
                               f"expected calibration error {ece:.3f}"),
                        how="Brier score and reliability diagram on test years (target: ECE ≤ 0.05 and Brier below persistence)"))
    else:
        for c, h in (("Detection runs on every pass from 2015 to 2025 for the chosen reach", "Count of passes processed versus passes available"),
                     ("Model beats persistence on precision@20 for 2023–2025", "Temporal hold-out with a bootstrap 95% interval"),
                     ("Model beats persistence on the downstream half of the reach", "Spatial hold-out"),
                     ("Risk probabilities are calibrated", "Brier score and reliability diagram on test years")):
            out.append(dict(claim=c, status="Target", how=h))

    if tm:
        out.append(dict(claim="Time from a pass becoming available to an updated map",
                        status="Measured",
                        value=(f"processing median {tm['processing_median_s']:.0f} s per pass on {tm['n_passes']} recent passes "
                               f"({tm['machine']}); archive latency (sensing → on AWS) median {tm['ingest_latency_median_h']:.1f} h"),
                        how="Timed end-to-end runs (download → mask → banks → features → ranked list)"))
    else:
        out.append(dict(claim="Time from a pass becoming available to an updated map", status="Target",
                        how="Timed end-to-end runs on five recent passes"))

    out.append(dict(claim="Radar coherence adds predictive value", status="Not built",
                    how="Needs SLC interferometric processing; not built in this run, so no claim is made"))
    for c, why in (("24-hour collapse forecast", "Not supported by the 6–12 day revisit"),
                   ("Sub-meter risk maps", "Not supported by 10 m pixels"),
                   ("Bed shear stress and pore pressure from satellite", "No bathymetry and no ground truth"),
                   ("Zero-shot use on any river on Earth", "Each river needs its own retraining and test"),
                   ("92.4% precision on 1,500 events, 1.42 s, 1.2 GB VRAM", "Never measured")):
        out.append(dict(claim=c, status="Dropped", how=why))
    return out


def markdown_table(rows: list[dict]) -> str:
    lines = ["| Claim | Status | Measured value | How it is measured |", "|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['claim']} | **{r['status']}** | {r.get('value', '–')} | {r['how']} |")
    return "\n".join(lines)


HEADER = """# Claims ledger

No claim reaches a slide, a pitch, the README or the dashboard until its
status here is **Measured**. Every number v2.0 asserted without an experiment
is **Dropped**. A measured miss is **Not met** and stays visible.

This file is generated by `python -m src.claims` from
`data/processed/metrics/*.json`; do not edit the table by hand.

"""

FOOTER = """

**Words that never appear in the pitch:** "world-first", "Newton-level",
"100% works", "unbreakable".

Sources for context figures used in the README (not NadiNet measurements):
see the *Sources* section of the README.
"""


def write_markdown(rows: list[dict]) -> None:
    (config.ROOT / "docs" / "CLAIMS_LEDGER.md").write_text(HEADER + markdown_table(rows) + FOOTER, encoding="utf-8")


def main() -> None:
    rows = ledger()
    (M / "claims.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    write_markdown(rows)
    print(markdown_table(rows))


if __name__ == "__main__":
    main()
