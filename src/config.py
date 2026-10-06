"""Central configuration for the NadiNet pipeline.

Every number here is a *setting*, not a result. Results live in
``data/processed/metrics/*.json`` and are only quoted after a run produces them.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("NADINET_DATA", ROOT / "data"))
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
LABELS_DIR = DATA / "labels"
DEMO_DIR = DATA / "demo"
METRICS_DIR = PROCESSED / "metrics"

S1_RAW = RAW / "sentinel1"          # cached, geocoded sigma0 (uint8-quantised dB)
S2_RAW = RAW / "sentinel2"
MASK_DIR = PROCESSED / "water_masks"
BANK_DIR = PROCESSED / "bank_lines"
TRANSECT_DIR = PROCESSED / "transects"
FEATURE_DIR = PROCESSED / "features"


@dataclass(frozen=True)
class Reach:
    """The study reach. Chosen in Week 1; see docs/METHODOLOGY.md for why."""

    name: str = "Jamuna — Kazipur to Chauhali (Sirajganj / Tangail)"
    slug: str = "sirajganj"
    lon_min: float = 89.56
    lon_max: float = 89.98
    lat_min: float = 24.10
    lat_max: float = 24.85
    crs: str = "EPSG:32645"          # UTM 45N; the reach sits at 89.6–90.0 E
    pixel_m: float = 10.0

    @property
    def bbox_lonlat(self) -> tuple[float, float, float, float]:
        return (self.lon_min, self.lat_min, self.lon_max, self.lat_max)


REACH = Reach()

# --- Sentinel-1 -------------------------------------------------------------
# Descending track 150 crosses the reach at ~23:56 UTC (~05:56 Bangladesh time).
# Early-morning passes are chosen because wind over the river is usually calmer,
# which keeps open water dark in VV. Track 114 (ascending, ~12:05 UTC) also
# covers the reach and is kept out on purpose: one geometry, one set of biases.
S1_BUCKET_URL = os.environ.get("NADINET_S1_BUCKET", "https://sentinel-s1-l1c.s3.amazonaws.com")
S1_RELATIVE_ORBIT = 150
S1_PASS_UTC_WINDOW = ("23:45", "23:59:59")
S1_START = "2015-01-01"
S1_END = "2025-12-31"

# Quantisation of cached sigma0 dB into uint8 (0..254, 255 = nodata).
DB_MIN, DB_MAX = -30.0, 5.0

# --- Water masks --------------------------------------------------------------
LEE_WINDOW = 5                # Lee speckle filter window (pixels)
VH_RESCUE_MARGIN_DB = 3.0     # VV may be this much above its threshold if VH says water
MIN_WATER_BLOB_PX = 50        # 0.5 ha; smaller water blobs are removed
MIN_LAND_BLOB_PX = 50         # smaller land specks inside water are filled

# --- Banks and transects -----------------------------------------------------
TRANSECT_SPACING_M = 200.0
TRANSECT_RIVERWARD_M = 1500.0  # transect extends this far riverward of the baseline
TRANSECT_LANDWARD_M = 4000.0   # ...and this far landward
LAND_RUN_PX = 5                # bank = start of the first run of >= 5 land pixels (50 m)

# --- Labels ------------------------------------------------------------------
HORIZON_DAYS = 28
# Set in Week 1 to at least twice the measured median bank-position error.
# 20 m is the floor from the spec; validate_masks.py writes the measured value
# to data/processed/metrics/mask_validation.json and make_labels.py enforces
# max(20, 2 * measured_error).
RETREAT_THRESHOLD_FLOOR_M = 20.0
MAJOR_EVENT_M = 100.0
TOP_K = 20

TRAIN_YEARS = tuple(range(2015, 2022))
VAL_YEAR = 2022
TEST_YEARS = (2023, 2024, 2025)

RANDOM_SEED = 20240601


def ensure_dirs() -> None:
    for p in (S1_RAW, S2_RAW, MASK_DIR, BANK_DIR, TRANSECT_DIR, FEATURE_DIR,
              LABELS_DIR, DEMO_DIR, METRICS_DIR):
        p.mkdir(parents=True, exist_ok=True)
