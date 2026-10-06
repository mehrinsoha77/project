# Partners, sustainability and the honest moat

NadiNet stays free for residents. It is funded first by grants and pilots,
and by institutional contracts only after a pilot shows value.

## Who uses it

| User | What they get | How they use it |
|---|---|---|
| Upazila and union disaster management committees (Kazipur, Sirajganj Sadar, Chauhali, Shahjadpur; Bhuapur, Tangail Sadar, Nagarpur) | Weekly ranked list of 200 m segments with reasons, as a PDF brief and on the dashboard | Target inspections, pre-position sandbags and boats, decide whether to approve a Warning |
| BWDB field offices (Sirajganj, Tangail) | The same list plus the bank-line history of each segment | Prioritise emergency protection works during the monsoon |
| NGOs in char and riverbank areas | The list, aggregated to union level for public use | Plan relocation support and anticipatory cash transfers |
| Riverbank households | A prerecorded Bangla voice call and SMS, only after an official approves | Move belongings and livestock in time |

## Partners to approach

| Partner | Why | Ask |
|---|---|---|
| BUET Institute of Water and Flood Management / Water Resources Engineering | Independent technical review | Review the label definition, the transect method and the geolocation correction |
| CEGIS | Publishes annual erosion predictions for the Jamuna, Ganges and Padma (since 2004, as reported in the press) | Collaboration: NadiNet is a monsoon-season, per-pass complement to their annual pre-monsoon prediction, not a replacement |
| IWM | Morphological modelling for BWDB | Compare near-bank flow from their models with our channel-geometry features |
| FFWC (BWDB) | Gauge levels at Sirajganj and Bahadurabad | Historical and forecast water levels to replace the radar stage proxy |
| One NGO or upazila DMC in the reach | Pilot | One monsoon of weekly briefs, plus ground reports of actual erosion |
| Department of Disaster Management | 1090 line, official channels | Integration is a partnership goal after the build, not a claim |

## Who pays, in realistic order

1. Competition prizes, university innovation grants and climate-adaptation
   challenge funds pay for the build and a first pilot.
2. NGO and development projects working in char and riverbank areas fund
   monitoring of their reaches from project budgets.
3. BWDB and the Department of Disaster Management, after a free pilot;
   government procurement is slow.
4. Owners of bridges, embankments and power lines near the river, and their
   insurers, pay for monitoring of specific assets.

**Running costs.** The committed pipeline reads Sentinel-1 straight from AWS
Open Data and runs on one 4-vCPU machine. Reprocessing the 2015–2025 archive
for one ~83 km reach took about an hour; a new pass takes minutes (see the
claims ledger). AWS lists the Sentinel-1 bucket as Requester Pays, so a
production service should budget for egress (~40 MB per pass for this reach)
or use the Copernicus Data Space Ecosystem. Google Earth Engine is an
alternative for research and education; commercial use needs a licence.

## The honest moat

The data is open and the model is simple, so the code can be copied in a
week. Defensibility comes from three things that take seasons to build:

1. a validated, segment-level bank-retreat dataset for Bangladeshi rivers,
   pass by pass since 2015;
2. trust with local officials and NGOs, earned through a pilot that reports
   its misses;
3. ground reports from partners that improve labels over time.

If a large company built the same thing anyway, riverbank families would
still benefit.

## Scaling roadmap

| Stage | Scope | Gate |
|---|---|---|
| Build (done) | One Jamuna reach, validated hindcast | Every ledger claim measured |
| Pilot (one monsoon) | Weekly briefs to one partner, ground reports | Partner finds briefs useful; live performance matches the hindcast |
| Expand (1–2 years) | Full Jamuna, then Padma and Teesta, each retrained and retested | Per-river validation passes |
| Beyond Bangladesh | Other braided rivers | A local hindcast passes on each |
