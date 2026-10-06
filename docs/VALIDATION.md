# Validation protocol

**Status: fixed before the test years were scored.** This file and the success
criteria in the README were committed before `python -m src.models.evaluate`
was first run; `git log -- docs/VALIDATION.md` shows the order. Any change
after the first test run is listed at the bottom with its reason.

One comparison decides the project:

> Does the model rank at-risk bank segments better than persistence on
> years it never saw?

## Unit of prediction

* **Segment** — a 200 m stretch of one mainland bank, represented by one
  transect cast perpendicular to a fixed baseline (871 transects, both banks,
  Kazipur to Chauhali, 24.10–24.85 °N).
* **Forecast date** — every Sentinel-1 pass of descending relative orbit
  150. A forecast is issued right after a pass and uses only passes at or
  before it.
* **Target** — did the segment's bank move landward by at least the
  threshold between the forecast pass and the pass nearest to 28 days later
  (accepted only if within ±8 days)?

## Label

```
b0  = median of b over the passes in [t - 24 d, t]
b1  = median of b over the passes within +-12 d of t_target      (t_target = pass nearest t + 28 d, accepted if within +-8 d)
bp  = 25th percentile of b over the passes in [t_target, t_target + 180 d]   (at least 4 passes)
R   = b1 - b0          retreat observed in the 28-day window
P   = bp - b0          retreat still there through the next low water
y   = 1[ R >= threshold and P >= threshold ]
threshold   = max(20 m, 2 x median bank-position error vs Sentinel-2)
major event = R >= 100 m and P >= 100 m
```

The medians remove single-pass flips (a side channel opening or closing).
The permanence term removes inundation: low land next to the bank floods in
June–August and drains in September–November, which moves the water edge by
hundreds of metres without any erosion. A 180-day window always contains
low-water passes. Labels may use future passes; features never do.

## Splits

| Split | Years | Use |
|---|---|---|
| Train | 2015–2021 | fit the model |
| Validation | 2022 | choose hyper-parameters from a fixed grid, fit isotonic calibration, set alert-tier thresholds |
| Test | 2023–2025 | scored **once** |

* **Temporal hold-out**: as above.
* **Spatial hold-out**: train on the upstream (northern) half of each bank
  (split at the median chainage), tune and calibrate on upstream 2022, test
  on the downstream half in 2023–2025.
* **No leakage**: every feature is as-of the forecast date.
  `tests/test_no_leakage.py` rebuilds the feature table from positions
  truncated at random dates and fails if any value changes; it also proves it
  can catch a planted leak. No location features (chainage, bank side) are
  given to the model. No water-level *forecasts* are used anywhere (none were
  available); river stage is proxied by observed in-belt water area.

## Methods compared

| | Score |
|---|---|
| **B0 persistence** | retreat over the last 84 days of the current bank (3-pass median) |
| **B1 history** | retreat over the previous 12 months of the permanent bank (6-month 25th percentile) |
| **M1** | LightGBM on the feature table, isotonic-calibrated on 2022 |

## Metrics

* **Precision@20** per forecast date: share of the 20 highest-ranked
  segments that lost at least the threshold within 28 days. Reported as the
  mean over test dates, and over monsoon (Jun–Oct) dates.
* **Difference M1 − B0** in per-date precision@20, with a 95% interval from
  a moving-block bootstrap (blocks of 3 consecutive forecast dates,
  4,000 resamples) because consecutive dates share overlapping windows.
* **Recall of major events**: share of (segment, date) pairs with
  R ≥ 100 m whose segment was in the top 20 beforehand.
* **PR-AUC**, **Brier score**, **reliability diagram** (10 fixed bins).
  Baselines are isotonic-calibrated on 2022 the same way, so Brier scores
  compare like with like.
* **Detection accuracy**: water-mask IoU and median bank-position error
  against cloud-free Sentinel-2 (MNDWI) scenes within ±2 days.
* **Ablations**: drop each feature group, retrain with M1's settings,
  recalibrate on 2022, report the change. Reporting only — never used to
  pick the model.

## Success levels (evaluated mechanically in `src/models/evaluate.py`)

| Level | Criterion |
|---|---|
| Minimum | median bank-position error ≤ 20 m **and** detection ran on every catalogued pass 2015–2025 |
| Good | M1 beats B0 on test precision@20 with a bootstrap 95% interval that excludes zero |
| Strong | Good, **and** the same on the spatial hold-out, **and** a lower Brier score than B0 |

If the model does not beat persistence, that is reported plainly. Cloud-proof
detection plus a persistence ranking is still useful, and the negative result
is a finding.

## Test-once rule

`src/models/evaluate.py` refuses to run a second time unless
`--rerun-reason` is given; every run is appended to
`data/processed/metrics/test_runs.log` with the git revision.

## Deviations from the v3.0 spec (decided before the test run)

* **Water level**: FFWC gauges and GloFAS could not be reached from the build
  environment; a radar-derived stage proxy (open water inside the braid belt)
  is used instead. Loaders for FFWC/GloFAS CSVs exist for later use.
* **Ingestion**: Sentinel-1 GRD read from the public AWS archive instead of
  Earth Engine (no EE credentials in the build environment). The EE scripts in
  `gee/` implement the same method but produced none of the results.
* **Coherence** and the **neural-operator surrogate** were not built; the
  ledger says so instead of reporting a number.

## Changes made before the first test run (with reasons)

All decided on training-period data (2015–2017 bank positions and
2017–2019 Sentinel-2 pairs); no 2022–2025 outcome had been computed.

1. **Geolocation correction.** Sentinel-1 banks were ~100 m west of
   Sentinel-2 banks on both sides (GCP terrain height). A constant terrain
   height, fitted on 2017–2019 pairs, now corrects the range position; the
   validation statistics use the other pairs.
2. **Optical reference for bank error** = active channel (water + bare sand,
   MNDWI > 0 or NDVI < 0.15), because C-band sees dry sand as dark as water.
   IoU against open water alone is reported too.
3. **Label definition.** The first version (forward minimum over 36 days)
   turned single riverward flips into false retreats and could not separate
   monsoon inundation from erosion: in 2015–2017, landward jumps > 200 m hit
   13% of consecutive passes, clustered in June–August and reversed in
   September–November. Replaced by the median/permanence definition above.
   Features moved to the same robust positions (3-pass median; 6-month 25th
   percentile), and `inundation_m` was added to the stage group.
4. Transect count is 871 (baselines rebuilt from the corrected 2015 masks).

## Changes after the first test run

The test years were scored once (`data/processed/metrics/test_runs.log`).
Nothing that affects the model, labels or metrics changed afterwards. Added
afterwards, as reporting only:

* a sensitivity analysis excluding positives with retreat > 300 m or > 500 m
  (`metrics/sensitivity_large_events.json`): the model still beats
  persistence (+26.6 pts, 95% CI +19.8 to +34.6 at 300 m);
* export fixes (PDF brief path, smaller radar previews) — presentation only.
