# Data

All inputs are open data read over HTTPS from AWS Open Data buckets. Nothing
here needs an account, except that AWS lists the Sentinel-1 bucket as
Requester Pays (see `.env.example`).

## Sources and licences

| Source | Where | What we use | Licence |
|---|---|---|---|
| Copernicus Sentinel-1 IW GRD (Level-1) | `s3://sentinel-s1-l1c` (Sinergise, AWS Open Data) | VV, VH, calibration LUTs, GCPs, annotation; relative orbit 150, 2015–2025 | Copernicus free, full and open data policy |
| Copernicus Sentinel-2 L2A (COG) | `s3://sentinel-cogs` (Element 84, AWS Open Data) | B03, B04, B08, B11, SCL, TCI of tile 45RYH | Copernicus free, full and open data policy |
| Copernicus DEM GLO-30 | `s3://copernicus-dem-30m` | Tile N24 E089, optional bank-height feature | © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018, provided under COPERNICUS by the EU and ESA |
| JRC Global Surface Water v1.4 (Pekel et al., 2016) | `storage.googleapis.com/global-surface-water` | Occurrence layer, only to look at the river when choosing the reach | CC BY 4.0 |

Not used (not reachable from the build environment): FFWC gauge levels,
GloFAS. Drop CSVs into `raw/ffwc/` to use them (see
`src/features/water_level.py`).

## Layout

```
data/
├── raw/                         (gitignored, regenerable)
│   ├── sentinel1/               cached geocoded σ⁰, uint8 dB, 2 bands, ~40 MB/pass
│   ├── sentinel2/
│   ├── uncorrected_masks/       2015–2019 masks without the height fix (for the offset estimate)
│   ├── ffwc/                    optional gauge CSVs
│   └── dem/                     Copernicus DEM resampled to the reach grid
├── processed/
│   ├── s1_catalog.json          every track-150 pass over the reach (271)
│   ├── water_masks/             mask_<pass>.tif (gitignored) + mask_summary.csv
│   ├── bank_lines/baselines.geojson
│   ├── transects/transects.geojson, bank_positions.parquet
│   ├── features/features.parquet
│   ├── models/                  m1_lgbm.txt, m1_params.json, calibrators.pkl
│   └── metrics/                 every measured number (JSON) — the claims ledger reads these
├── labels/
│   ├── labels_all.parquet
│   ├── train_2015_2021.parquet
│   ├── val_2022.parquet
│   └── test_2023_2025.parquet
└── demo/
    ├── sirajganj_reach.geojson  reach box, baselines, 870 transects (WGS84)
    ├── predictions_2022..2025.parquet
    └── tier_thresholds.json
```

## Grid

All rasters share one grid: EPSG:32645 (UTM 45N), 10 m pixels,
4,427 × 8,397, upper-left corner (758690, 2751640). Defined by
`src.geo.reach_grid()` from the reach box in `src/config.py`.

## Columns

`bank_positions.parquet` — one row per (pass, transect):
`pass_id, transect_id, date, bank_pos_m` (signed metres from the baseline,
positive landward), `dist_main_channel_m, near_channel_width_m,
char_shield_frac, nearbank_water_frac, belt_area_km2, belt_water_km2,
water_area_km2, otsu_ok, coverage, platform`.

`labels_*.parquet` — `transect_id, forecast_date, target_date, retreat_m, y,
major, year`.

`predictions_<year>.parquet` — `transect_id, forecast_date, p` (calibrated
probability), `raw, rank, b0_rank, b0_p, tier, reasons` (JSON list),
feature snapshots, and the outcome `target_date, retreat_m, y, major` where
observed.
