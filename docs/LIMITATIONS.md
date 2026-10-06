# Limitations

Written to be read by a judge who knows rivers. Each item says what it
affects and what would fix it.

## Data and detection

| Limitation | Effect | What would fix it |
|---|---|---|
| **One track, 12-day revisit, with gaps.** Track 150 only; S1B rarely acquired it and failed in Dec 2021; no S1C product for this track was found in the AWS bucket for 2025. Gaps of 36–72 days occur (2015–16, mid-2017, mid-2018, late 2023, Jun–Aug 2024). | Erosion between passes is seen late; some 28-day windows have no target pass and are not labelled. | Add a second track (114 ascending) once validation shows it agrees; ingest S1C/S1D from the Copernicus Data Space. |
| **Dry sand looks like water in VV.** | Low IoU against optical open water in the dry season; char edges are unreliable. Mainland banks are much less affected (vegetation edge). | Use VH/VV ratio or a texture feature to separate sand; validate char edges separately (stretch goal). |
| **Geolocation needed a correction.** The GCP grid assumes the reach is ~60 m above the ellipsoid; we correct with a constant terrain height fitted on 2017–2019 pairs. | A residual offset of a few metres may remain; it cancels in retreat measurements because the geometry repeats. | Use precise orbits and a DEM + geoid model (EGM2008) for full range-Doppler terrain correction. |
| **No thermal-noise removal or terrain flattening.** | VH over water near the noise floor; flat terrain makes flattening unnecessary here. | Apply the product's noise vectors. |
| **Sentinel-2 validation covers part of the reach and only dry-season dates.** Tile 45RYH stops at ~24.30 °N; monsoon scenes are cloudy. | The bank-error figure describes the northern two-thirds in the dry season. | Add tile coverage to the south (zone 46 tiles) and use rare clear monsoon days. |
| **Bridge, guide bunds and towns.** Bright structures can bend the bank line locally. | A handful of transects near the bridge are noisy (flagged `near_bridge`). | Mask known structures. |

## Labels

| Limitation | Effect |
|---|---|
| Labels come from the **same radar masks** as the features. | Systematic mask errors (e.g. wet sand, flooded fields joined to the river) can enter both. Forward confirmation (36 days) removes transient errors but not persistent ones. |
| Threshold = max(20 m, 2 × measured median bank error). | Retreats smaller than the threshold are invisible to the model. |
| No ground truth from the field. | We measure agreement with the satellite record, not with households' experience. A pilot with ground reports is the next step. |

## Model

| Limitation | Effect |
|---|---|
| **No water-level forcing from gauges or forecasts.** FFWC and GloFAS could not be reached from the build environment; stage is proxied by in-belt open water on the pass. | The model cannot anticipate a flood peak that has not started. Loaders for FFWC/GloFAS CSVs exist. |
| **Coherence and the neural-operator surrogate were not built.** | No claim is made about them. |
| **One reach, one river.** | Nothing here shows the model transfers to the Padma, Teesta or anywhere else; each needs retraining and its own hold-out test. |
| **Reasons are SHAP attributions.** | They say what the model used, not what caused the erosion. |
| **Calibration was fitted on one year (2022).** | Probabilities may drift in years unlike 2022 (e.g. extreme floods). The reliability diagram on 2023–2025 is the check. |

## Product and ethics

| Limitation | Mitigation in this build |
|---|---|
| The tool has never been used by an official or NGO. | Labelled as advisory decision support; partners listed in [PARTNERS.md](PARTNERS.md); a pilot comes before any public use. |
| False "safe" is dangerous. | Every brief and the dashboard say the absence of an alert does not mean a bank is safe. |
| Raw risk maps can affect land values. | Raw maps stay with officials and partners; public views aggregate to union level. |
| People without phones. | Warning-tier messages also go to local volunteers and community announcement channels identified with partners. |
| The Bangla voice clip is **not recorded yet**. | It must be recorded by a native speaker from the target reach. NadiNet does not synthesise speech; the UI says so when the clip is missing. |
| Earth Engine scripts (`gee/`) were not run. | Results come from the AWS path only; the GEE path is offered for teams with an account. |
| AWS documents the Sentinel-1 bucket as Requester Pays. | In the build environment objects were readable over HTTPS; others may need AWS credentials and pay egress (~40 MB per pass for this reach). |
