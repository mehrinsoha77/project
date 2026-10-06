# Methodology

Six small, separately testable steps turn raw radar into a ranked list of
at-risk bank segments. Settings live in `src/config.py`; results live in
`data/processed/metrics/`. This document explains each choice; the numbers
that came out are in [CLAIMS_LEDGER.md](CLAIMS_LEDGER.md).

## 0. Reach and data choice (Week 1)

**Reach:** the Jamuna from Kazipur to Chauhali, 24.10–24.85 °N,
89.56–89.98 °E (~83 km of river, both mainland banks; Sirajganj district on
the west, Tangail on the east). Why this reach:

* active, well-documented erosion on both banks (Kazipur, Sirajganj,
  Chauhali; Bhuapur and Nagarpur), and protected stretches (Sirajganj town
  works, the Bangabandhu Bridge guide bunds) that should *not* erode — a
  built-in sanity check;
* fully covered by one Sentinel-1 track (descending relative orbit 150)
  and, for its northern two-thirds, by Sentinel-2 tile 45RYH;
* the bridge is a fixed, unmistakable radar target for checking geolocation.

**Track:** descending relative orbit 150, ~23:56 UTC (~05:56 local). Early
morning passes usually have less wind over the river, so open water stays
dark in VV. Ascending track 114 also covers the reach and was deliberately
left out: one viewing geometry means one set of geometric biases, which then
cancel when bank positions are differenced over time.

**Archive:** 271 passes between 19 Jan 2015 and 28 Dec 2025 were found in the
public `sentinel-s1-l1c` bucket. Revisit is 12 days most of the time; there
are gaps of 36–72 days in 2015–16, mid-2017, mid-2018, late 2023 and
June–August 2024. Sentinel-1B acquired this track only three times before it
failed (Dec 2021), and no Sentinel-1C product for this track was found in the
bucket for 2025.

## 1. Ingestion: from GRD to calibrated, geocoded σ⁰ (`src/masks/s1_io.py`)

Earth Engine was not available in the build environment, so the GRD products
are read directly from AWS. The measurement TIFFs are tiled with overviews,
so only the window covering the reach is fetched (HTTP range requests, ~10 s
per pass).

1. **Window:** invert the product's GCP grid (21 × 10 tie points) for the
   reach grid — a bicubic spline through the tie points, solved for
   (line, pixel) by Newton iterations on a 160 m sub-grid, then bilinearly
   upsampled. Accuracy on synthetic grids: < 0.05 px (`tests/test_masks.py`).
2. **Calibration:** σ⁰ = DN² / A², with A interpolated from the product's
   `sigmaNought` LUT. VV at full resolution (10 m), VH from the 2× overview
   (20 m) because it is only a secondary check.
3. **Speckle:** Lee filter (5 × 5 VV, 3 × 3 VH, ENL 4.4) in radar geometry.
4. **Geocoding:** bilinear resampling onto a fixed 10 m UTM 45N grid
   (4,427 × 8,397 px) shared by every pass.
5. **Height correction (a finding of this build).** The first comparison with
   Sentinel-2 showed radar bank lines ~100 m too far west on *both* banks
   (west bank too far landward, east bank too far riverward) — a shift, not
   noise. The GCP grid puts the reach at ~60 m above the WGS84 ellipsoid; the
   floodplain actually lies below it (the geoid is tens of metres below the
   ellipsoid in Bangladesh). For a point lower than assumed, radar places it
   too far from the sensor by Δh / tan θ; the sensor looks west, hence the
   westward shift. We correct each pixel's range position for a constant
   terrain height `S1_TERRAIN_HEIGHT_ELLIPSOID_M`:

   ```
   pixel_true = pixel_gcp − (H − h_gcp) / (tan θ · 10 m)
   ```

   H was estimated **only** from eight 2017–2019 radar/optical pairs
   (`scripts/estimate_geolocation_offset.py` → `metrics/geolocation_offset.json`):
   median shift 100.3 m along the look direction (per-pair 74–109 m),
   incidence 40.8°, GCP height 59.9 m → **H = −26.6 m**. Validation statistics
   are reported on the *other* pairs. Because every pass shares the same
   geometry, a residual constant offset would cancel in retreat measurements
   anyway; the correction matters for maps and absolute accuracy.

Not done: thermal-noise removal (matters for VH over water, which is only a
secondary check), radiometric terrain flattening (flat floodplain), and
precise-orbit re-geocoding.

## 2. Water masks (`src/masks/sentinel1_mask.py`)

* Otsu threshold per scene on VV dB in (−30, 0) dB. Accepted if it lands in
  [−22, −11] dB, else a fixed −15 dB fallback and the pass is flagged.
* VH rescue: a pixel is also water if VH is below its own Otsu threshold
  *and* VV is within 3 dB above the VV threshold — wind-roughened water.
* 3 × 3 opening; water blobs and land specks smaller than 0.5 ha removed.
* Output: one uint8 GeoTIFF per pass (0 land, 1 water, 255 no data).

**Known behaviour:** smooth, dry sand bars are as dark as water in C-band VV.
In the dry season the radar "water" mask is really *water + bare sand*. This
is visible as a low IoU against optical open water and a much higher IoU
against the optical active channel (water + bare sand). For the *mainland
bank* it does not matter: the bank is the edge between the active channel
and vegetated floodplain, which both sensors see.

## 3. Bank lines and transects (`src/banks/`)

* **Braid belt** (`belt.py`): water connected (within 20 m) to bodies larger
  than 5 km², plus every land patch it fully encloses (chars). The
  Bangabandhu Bridge deck — a bright line that would join chars to the
  mainland — is burnt in as water. Narrow side channels (khals) are cut with
  an opening of radius 70 m, and only large components are kept.
* **Baselines** (`baselines.py`): drawn once from the 10 passes of the first
  12 months of the archive (2015): pixels in the belt on ≥ 50 % of those
  passes, west- and east-most belt pixel per row, Gaussian-smoothed over
  1.5 km, 1 km trimmed at each end. Never moved afterwards.
* **Transects** (`transects.py`): every 200 m along each baseline,
  perpendicular to it, 1.5 km riverward to 4 km landward — 871 segments
  (408 west bank, 463 east bank). Segment id = bank + chainage in metres
  from the reach's north end, e.g. `W-12300`.
* **Bank position** (`bank_position.py`): walking from the landward end
  towards the river, the first run of ≥ 3 belt samples (30 m). Positive =
  landward of the baseline. NaN if the landward end is already in the belt,
  if there is no belt, or if no-data lies within 500 m of the bank.

This is the transect method of USGS DSAS, applied pass by pass.

## 4. Labels (`src/labels/make_labels.py`)

The spec's label is R = b(t+28) − b(t) ≥ threshold. On the real archive that
is not enough, for two reasons found on 2015–2017 data:

* **Flips.** A narrow side channel opens or closes between passes and the
  traced bank jumps between a few discrete positions.
* **Inundation.** Landward jumps of > 200 m hit 13% of consecutive passes,
  concentrated in June–August, and reversed in September–November: low land
  next to the bank floods and drains. That is not erosion.

So the label uses robust positions and a permanence test:

```
b0 = median of b over passes in [t − 24 d, t]
b1 = median of b over passes within ±12 d of t_target         (t_target = pass nearest t + 28 d, ±8 d)
bp = 25th percentile of b over passes in [t_target, t_target + 180 d]   (≥ 4 passes)
y  = 1[ b1 − b0 ≥ thr  and  bp − b0 ≥ thr ]       thr = max(20 m, 2 × median bank error)
```

In words: *the bank seen on the forecast pass moved landward by at least
the threshold within 28 days, and was still there six months later.* A
180-day window always contains low-water passes, so drained margins drop
out. Costs: forecasts in the last ~6 months of the archive have no label yet,
and erosion of a low bank that is already flooded at the forecast date can be
missed (conservative).

## 5. Features (`src/features/`)

All features are **as-of** the forecast pass. Bank positions for features
use the same robust statistics as the label, looking backwards only: the
current bank b0 (median over the last 24 days) and the permanent bank perm
(25th percentile over the last 180 days). The raw jump on the newest pass is
kept separately (`raw_last_change_m`).

| Group | Features | Spec item |
|---|---|---|
| Recent retreat | b0 retreat over 28 / 56 / 84 days; raw change on latest pass | Recent retreat |
| History | permanent-bank retreat over 12 months; number of observations in 12 months | Annual retreat |
| Channel geometry | distance from bank to the nearest main-channel core (water ≥ 150 m from land, i.e. ≥ ~300 m wide) and its 28-day change; width of the channel hugging the bank; share of land (chars) in the 2 km in front of the bank; share of water in the 300 m in front; baseline curvature; embayment vs neighbours | Distance to main channel, channel width, bank curvature, char shielding |
| River stage | open water inside the braid belt (km²), its 12- and 24-day change, anomaly vs an as-of climatology; `inundation_m` = b0 − perm | Water level and trend |
| Season | sin/cos day of year | Season |
| Neighbours | mean 84-day and 12-month retreat of the 3 segments either side | (added) |
| Bank height (optional) | Copernicus DEM 50–300 m landward of the bank minus DEM over the river on the same transect | Bank height |
| Coherence (optional) | **not built** | Coherence |

**River stage — a deviation from the spec.** FFWC gauge data and GloFAS were
not reachable from the build environment. In-belt open water is used as an
observed stage proxy; reach-wide water area is *not*, because irrigated
boro rice fields flood the floodplain in January–March and look like water.
CSV loaders for FFWC/GloFAS are in `water_level.py` for when data is
available. No forecasts are used, so the model has no forward-looking
forcing.

No location features (chainage, bank side, coordinates) are given to the
model.

## 6. Models (`src/models/`)

* **B0 persistence:** rank by 84-day retreat of the current bank (b0).
  **B1 history:** rank by 12-month retreat of the permanent bank.
* **M1:** LightGBM (binary), trained on 2015–2021. Grid of 12 settings
  (`num_leaves` 15/31/63 × `min_child_samples` 50/200 × learning rate
  0.03/0.1); trees chosen by early stopping on 2022 log-loss; the setting with
  the best mean precision@20 on 2022 is kept.
* **Calibration:** isotonic regression on 2022 (also applied to B0 and B1 for
  fair Brier scores).
* **Explanations:** LightGBM's TreeSHAP contributions, grouped (e.g. the three
  retreat windows count as one reason) and rendered with the segment's actual
  values ("Bank retreated 64 m in the last 4 weeks").
* **Alert tiers:** Watch = top 20; Warning-eligible = top 20 **and**
  probability above the lowest value whose 2022 precision is ≥ 50 % **and**
  retreat ≥ threshold on the latest pass. A Warning needs an official's
  approval.

## 7. Optional research track: neural-operator surrogate

Not built in this run. The plan stands as in the spec: train an FNO on
synthetic channel shapes run through an open 2-D shallow-water solver
(ANUGA) to predict near-bank velocity, and keep it as a feature only if it
improves the held-out results. It would never be presented as solving the
real Jamuna, which has no public bathymetry.
