"""Bank position per transect per pass, plus per-pass channel geometry.

Bank position b_s(t) on transect s at pass t (spec §Method 3) is the signed
distance from the baseline (positive = landward) to the landward edge of the
braid belt. It is found by walking from the landward end of the transect
towards the river and stopping at the first run of ``BELT_RUN`` belt samples.
Equivalently: it is where the first land pixel would be found walking out of
the river, with chars already folded into the belt.

The same pass also yields the channel-geometry features (spec §Method 4),
which need the 2-D mask and are cheapest to compute here:

* ``dist_main_channel_m`` – distance from the bank point to the nearest pixel
  of a "main channel" (water at least ``MAIN_CHANNEL_HALF_WIDTH_PX`` from any
  land, i.e. a channel at least ~300 m wide);
* ``near_channel_width_m`` – width of the water body hugging the bank
  (2 x the largest water distance-to-land within 300 m riverward);
* ``char_shield_frac`` – share of land (chars) on the transect between the
  bank and 2 km riverward;
* ``nearbank_water_frac`` – share of water within 300 m riverward;
* ``belt_water_km2`` – open water inside the braid belt for the whole reach.
  This is the river-stage proxy: as the river rises, chars drown and channels
  widen. Reach-wide water area is *not* used, because irrigated boro rice
  fields flood the floodplain in January–March and look like water.

A position is set to NaN when the transect touches no-data near the bank, the
landward end is already in the belt (bank beyond the transect), or no belt is
found.

CLI::

    python -m src.banks.bank_position --workers 3
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import logging

import numpy as np
import pandas as pd
from scipy import ndimage

from src import config
from src.banks.belt import river_belt
from src.banks.transects import load_transects, sample_index
from src.masks.sentinel1_mask import mask_path, read_mask

log = logging.getLogger(__name__)

POSITIONS_PATH = config.TRANSECT_DIR / "bank_positions.parquet"
BELT_RUN = 3
MAIN_CHANNEL_HALF_WIDTH_PX = 15
NEAR_M = 300.0
SHIELD_M = 2000.0
NODATA_GUARD_M = 500.0


def first_belt_from_land(belt_samples: np.ndarray, run: int = BELT_RUN) -> np.ndarray:
    """Index of the bank on each transect, scanning from the landward end.

    ``belt_samples``: bool (n_transects, n_samples), sample 0 riverward.
    Returns the index of the landward-most sample of the first run of ``run``
    belt samples met from the landward end, or -1 if none.
    """
    rev = belt_samples[:, ::-1].astype(np.int32)
    # run-length of consecutive belt samples ending at each position (reversed order)
    k = np.ones(run, dtype=np.int32)
    conv = np.apply_along_axis(lambda v: np.convolve(v, k, mode="full")[: len(v)], 1, rev)
    hit = conv >= run
    has = hit.any(axis=1)
    j = hit.argmax(axis=1) - (run - 1)          # start of the run in reversed index
    idx = belt_samples.shape[1] - 1 - j          # back to forward index
    return np.where(has, idx, -1)


def positions_for_mask(mask: np.ndarray, rows: np.ndarray, cols: np.ndarray, s: np.ndarray) -> pd.DataFrame:
    belt = river_belt(mask)
    water = mask == 1
    nod = mask == 255
    step = float(s[1] - s[0])

    B = belt[rows, cols]
    N = nod[rows, cols]
    W = water[rows, cols]
    idx = first_belt_from_land(B)
    n_tr, n_s = B.shape
    pos = np.where(idx >= 0, s[np.clip(idx, 0, n_s - 1)], np.nan)

    # validity: landward end must be land; no nodata between (bank - guard) and the landward end
    landward_end_in_belt = B[:, -1]
    guard = int(NODATA_GUARD_M / step)
    nod_near = np.array([N[i, max(idx[i] - guard, 0):].any() if idx[i] >= 0 else N[i].any()
                         for i in range(n_tr)])
    valid = (idx >= 0) & ~landward_end_in_belt & ~nod_near
    pos = np.where(valid, pos, np.nan)

    # channel geometry
    dist_land = ndimage.distance_transform_edt(water)          # inside water: distance to land (px)
    core = dist_land >= MAIN_CHANNEL_HALF_WIDTH_PX
    if core.any():
        dist_core = ndimage.distance_transform_edt(~core) * config.REACH.pixel_m
    else:
        dist_core = np.full(mask.shape, np.nan)
    br = rows[np.arange(n_tr), np.clip(idx, 0, n_s - 1)]
    bc = cols[np.arange(n_tr), np.clip(idx, 0, n_s - 1)]
    d_main = np.where(valid, dist_core[br, bc], np.nan)

    near_n = int(NEAR_M / step)
    shield_n = int(SHIELD_M / step)
    DL = dist_land[rows, cols]
    width = np.full(n_tr, np.nan)
    shield = np.full(n_tr, np.nan)
    nearw = np.full(n_tr, np.nan)
    for i in np.flatnonzero(valid):
        a = idx[i]
        seg_near = slice(max(a - near_n, 0), a + 1)
        width[i] = 2.0 * DL[i, seg_near].max() * config.REACH.pixel_m
        nearw[i] = W[i, seg_near].mean()
        seg = slice(max(a - shield_n, 0), a + 1)
        shield[i] = 1.0 - W[i, seg].mean()
    return pd.DataFrame(dict(bank_pos_m=pos, dist_main_channel_m=d_main, near_channel_width_m=width,
                             char_shield_frac=shield, nearbank_water_frac=nearw,
                             belt_area_km2=float(belt.sum() * config.REACH.pixel_m ** 2 / 1e6),
                             belt_water_km2=float((belt & water).sum() * config.REACH.pixel_m ** 2 / 1e6)))


PER_PASS = config.TRANSECT_DIR / "per_pass"


def _one(pass_id: str, rows, cols, s, tids) -> pd.DataFrame | None:
    """Positions for one pass, cached per pass (re-used unless the mask is newer)."""
    p = mask_path(pass_id)
    if not p.exists():
        return None
    cache = PER_PASS / f"{pass_id}.parquet"
    if cache.exists() and cache.stat().st_mtime >= p.stat().st_mtime:
        return pd.read_parquet(cache)
    df = positions_for_mask(read_mask(p), rows, cols, s)
    df.insert(0, "transect_id", tids)
    df.insert(0, "pass_id", pass_id)
    PER_PASS.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache, index=False)
    return df


def run(workers: int = 3) -> pd.DataFrame:
    tr = load_transects()
    rows, cols, s = sample_index(tr)
    summary = pd.read_csv(config.MASK_DIR / "mask_summary.csv")
    tids = tr["transect_id"].to_numpy()
    out = []
    with cf.ProcessPoolExecutor(workers) as ex:
        futs = [ex.submit(_one, pid, rows, cols, s, tids) for pid in summary["pass_id"]]
        for i, f in enumerate(cf.as_completed(futs)):
            r = f.result()
            if r is not None:
                out.append(r)
            if i % 25 == 0:
                log.info("%d / %d", i + 1, len(futs))
    df = pd.concat(out, ignore_index=True)
    df = df.merge(summary[["pass_id", "date", "platform", "water_area_km2", "otsu_ok", "coverage"]], on="pass_id")
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["transect_id", "date"]).reset_index(drop=True)
    POSITIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(POSITIONS_PATH, index=False)
    return df


def load_positions() -> pd.DataFrame:
    return pd.read_parquet(POSITIONS_PATH)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO)
    df = run(a.workers)
    print(df.groupby("pass_id")["bank_pos_m"].apply(lambda v: v.notna().mean()).describe())


if __name__ == "__main__":
    main()
