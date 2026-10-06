"""Check a folder of exported masks (from either ingestion path) before modelling.

Checks: every catalogue pass has a mask, every mask is on the reach grid,
values are only {0, 1, 255}, coverage and water fraction are plausible.
Exit code 1 on any failure.

Usage::

    python gee/verify_exports.py --masks data/processed/water_masks
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import rasterio  # noqa: E402

from src import config  # noqa: E402
from src.geo import reach_grid  # noqa: E402


def verify(mask_dir: Path, catalog: Path | None) -> list[str]:
    g = reach_grid()
    problems = []
    files = sorted(mask_dir.glob("mask_*.tif"))
    if catalog and catalog.exists():
        want = {p["pass_id"] for p in json.loads(catalog.read_text())}
        have = {f.stem.replace("mask_", "") for f in files}
        for pid in sorted(want - have):
            problems.append(f"missing mask for pass {pid}")
    for f in files:
        with rasterio.open(f) as ds:
            if (ds.width, ds.height) != (g.width, g.height) or ds.crs.to_string() != g.crs:
                problems.append(f"{f.name}: wrong grid {ds.width}x{ds.height} {ds.crs}")
                continue
            if any(abs(a - b) > 1e-6 for a, b in zip(ds.transform, g.transform)):
                problems.append(f"{f.name}: transform differs from reach grid")
            a = ds.read(1, out_shape=(g.height // 8, g.width // 8))
        vals = set(np.unique(a).tolist())
        if not vals <= {0, 1, 255}:
            problems.append(f"{f.name}: unexpected values {sorted(vals)}")
        valid = a != 255
        if valid.mean() < 0.5:
            problems.append(f"{f.name}: coverage only {valid.mean():.0%}")
        wf = (a == 1).sum() / max(valid.sum(), 1)
        if not 0.05 <= wf <= 0.6:
            problems.append(f"{f.name}: implausible water fraction {wf:.2f}")
    return problems


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--masks", type=Path, default=config.MASK_DIR)
    ap.add_argument("--catalog", type=Path, default=config.PROCESSED / "s1_catalog.json")
    a = ap.parse_args()
    probs = verify(a.masks, a.catalog)
    for p in probs:
        print("FAIL", p)
    print(f"{len(list(a.masks.glob('mask_*.tif')))} masks checked, {len(probs)} problems")
    sys.exit(1 if probs else 0)


if __name__ == "__main__":
    main()
