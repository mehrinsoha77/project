"""Time the path from "pass available" to "updated ranked list" (claims ledger row).

For the N most recent passes in the catalogue, re-run every step for that pass
from scratch, as an operational update would, and time each stage:

1. download + calibrate + filter + geocode (``s1_io.process_pass``, network included);
2. water mask; 3. braid belt and bank position on all transects;
4. as-of features for the forecast date; 5. model + calibration + ranking.

Also reports the archive latency: time from sensing to the product appearing
in the AWS bucket (``s3Ingestion`` in productInfo.json). Results go to
``data/processed/metrics/timing.json``.

Usage::

    python scripts/time_pipeline.py --passes 5
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from src import config  # noqa: E402
from src.banks.bank_position import load_positions, positions_for_mask  # noqa: E402
from src.banks.transects import load_transects, sample_index  # noqa: E402
from src.features.build_features import build  # noqa: E402
from src.masks import s1_io  # noqa: E402
from src.masks.sentinel1_mask import mask_from_cache  # noqa: E402
from src.models.calibrate import apply, load_calibrators  # noqa: E402
from src.models.train_lgbm import load_model, load_params  # noqa: E402


def ingest_latency_h(p: s1_io.Pass) -> float | None:
    sl = p.slices[0]
    j = s1_io._get(f"{config.S1_BUCKET_URL}/{sl.prefix}productInfo.json").json()
    if "s3Ingestion" not in j:
        return None
    t0 = pd.Timestamp(j["startTime"]).tz_localize("UTC")
    t1 = pd.Timestamp(j["s3Ingestion"])
    return (t1 - t0).total_seconds() / 3600


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--passes", type=int, default=5)
    a = ap.parse_args()
    passes = s1_io.load_catalog(config.PROCESSED / "s1_catalog.json")[-a.passes:]
    tr = load_transects()
    rows, cols, s = sample_index(tr)
    history = load_positions()
    model, info = load_model(), load_params()
    iso, fill = load_calibrators()["M1_raw"]
    runs = []
    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp)
        orig = config.S1_RAW
        config.S1_RAW = cache
        try:
            for p in passes:
                t = {"pass_id": p.pass_id}
                t0 = time.perf_counter()
                path = s1_io.process_pass(p, overwrite=True)
                t["download_geocode_s"] = time.perf_counter() - t0
                t1 = time.perf_counter()
                mask, _ = mask_from_cache(path)
                t["mask_s"] = time.perf_counter() - t1
                t2 = time.perf_counter()
                pos = positions_for_mask(mask, rows, cols, s)
                t["banks_s"] = time.perf_counter() - t2
                t3 = time.perf_counter()
                d = pd.Timestamp(p.date)
                new = pos.assign(transect_id=tr["transect_id"].to_numpy(), pass_id=p.pass_id, date=d,
                                 coverage=1.0)
                hist = pd.concat([history[history["date"] < d], new], ignore_index=True)
                hist = hist[hist["date"] > d - pd.Timedelta(days=400)]    # features look back at most a year
                X = build(hist, tr, with_bank_height=True)
                X = X[X["forecast_date"] == d]
                t["features_s"] = time.perf_counter() - t3
                t4 = time.perf_counter()
                p_cal = apply(iso, pd.Series(model.predict(X[info["features"]])), fill)
                X = X.assign(p=p_cal).sort_values("p", ascending=False)
                t["rank_s"] = time.perf_counter() - t4
                t["total_s"] = time.perf_counter() - t0
                t["ingest_latency_h"] = ingest_latency_h(p)
                runs.append(t)
                print({k: (round(v, 1) if isinstance(v, float) else v) for k, v in t.items()})
        finally:
            config.S1_RAW = orig
    lat = [r["ingest_latency_h"] for r in runs if r["ingest_latency_h"] is not None]
    out = dict(
        n_passes=len(runs), runs=runs,
        processing_median_s=statistics.median(r["total_s"] for r in runs),
        processing_max_s=max(r["total_s"] for r in runs),
        ingest_latency_median_h=statistics.median(lat) if lat else None,
        machine=f"{os.cpu_count()} vCPU, {platform.system()} {platform.machine()}, Python {platform.python_version()}",
        note="single pass, one process; network time to the AWS bucket included",
    )
    config.METRICS_DIR.mkdir(parents=True, exist_ok=True)
    (config.METRICS_DIR / "timing.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({k: v for k, v in out.items() if k != "runs"}, indent=2))


if __name__ == "__main__":
    main()
