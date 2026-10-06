import { ClaimsLedger } from "@/components/ClaimsLedger";
import { AblationChart, ReliabilityChart } from "@/components/charts";
import { serverData } from "@/lib/server-data";
import { pct } from "@/lib/utils";
import type { Summary } from "@/lib/api";

export const metadata = { title: "Method & evidence — NadiNet" };

const GROUP_LABEL: Record<string, string> = {
  "-recent_retreat": "Recent retreat",
  "-history": "12-month history",
  "-channel_geometry": "Channel geometry",
  "-water_level": "River stage (radar)",
  "-season": "Season",
  "-neighbours": "Neighbouring segments",
  "-bank_height": "Bank height (DEM)",
};

function Row({ name, s, note }: { name: string; s?: Summary; note?: string }) {
  if (!s) return null;
  return (
    <tr className="border-b last:border-0">
      <td className="px-3 py-2 font-medium">
        {name}
        {note && <div className="text-[11px] font-normal text-muted-foreground">{note}</div>}
      </td>
      <td className="px-3 py-2 tabular">{pct(s.precision_at_k, 1)}</td>
      <td className="px-3 py-2 tabular">{pct(s.precision_at_k_monsoon, 1)}</td>
      <td className="px-3 py-2 tabular">{s.pr_auc.toFixed(3)}</td>
      <td className="px-3 py-2 tabular">{s.brier !== undefined ? s.brier.toFixed(4) : "–"}</td>
      <td className="px-3 py-2 tabular">
        {s.major.hits}/{s.major.total} ({pct(s.major.recall)})
      </td>
    </tr>
  );
}

export default function About() {
  const m = serverData.metrics();
  const mv = m.mask_validation;
  const ls = m.label_stats;
  const tr = m.test_results;
  const t = tr?.temporal;
  const sp = tr?.spatial;
  const ab = m.ablation;
  const abRows = ab
    ? Object.entries(ab)
        .filter(([k]) => k.startsWith("-"))
        .map(([k, v]: [string, any]) => ({ group: GROUP_LABEL[k] ?? k, delta: v.test_2023_2025.delta_precision_at_k_vs_full as number }))
        .sort((a, b) => a.delta - b.delta)
    : [];
  return (
    <div className="container max-w-5xl py-10">
      <h1 className="text-3xl font-semibold tracking-tight">Method &amp; evidence</h1>
      <p className="mt-2 max-w-3xl text-muted-foreground">
        One data source, one model family, one validation protocol, one alert path. Every number on this page was produced by code in the
        repository; the pipeline that made it is in <code>scripts/run_pipeline.sh</code>.
      </p>

      <section className="mt-10">
        <h2 className="text-xl font-semibold">1. Data and detection</h2>
        <ul className="mt-3 list-disc space-y-1.5 pl-5 text-sm text-muted-foreground">
          <li>
            <b className="text-foreground">Reach:</b> Jamuna from Kazipur to Chauhali, 24.10–24.85°N (~83 km), both mainland banks. Chosen for active
            erosion, the Bangabandhu Bridge as a fixed reference, and full coverage by one Sentinel-1 track.
          </li>
          <li>
            <b className="text-foreground">Radar:</b> every Sentinel-1 IW GRD pass of descending relative orbit 150 (~05:56 local) from Jan 2015 to Dec 2025,
            read straight from the public Copernicus archive on AWS. VV at 10 m and VH at 20 m are calibrated to σ⁰ with the product&apos;s own LUT,
            Lee-filtered, and geocoded onto a fixed 10 m UTM grid by inverting the product&apos;s GCP grid.
          </li>
          <li>
            <b className="text-foreground">Water mask:</b> per-scene Otsu threshold on VV dB; VH rescues wind-roughened water; opening and 0.5 ha blob cleaning.
          </li>
          <li>
            <b className="text-foreground">Bank line:</b> the braid belt (river-connected water plus the chars it encloses, with narrow khals cut away) is traced
            on 200 m transects cast from a baseline fixed once from the 2015 passes, as in USGS DSAS.
          </li>
          <li>
            <b className="text-foreground">Stage:</b> FFWC gauges and GloFAS were not reachable from the build environment, so river stage is proxied by open
            water inside the braid belt on each pass. No forecasts are used.
          </li>
        </ul>
        {mv && (
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <Tile label="Median bank-position error vs Sentinel-2" value={`${mv.bank_error_median_m.toFixed(0)} m`} sub={`90th percentile ${mv.bank_error_p90_m.toFixed(0)} m · mean signed ${mv.bank_error_mean_signed_m.toFixed(0)} m`} />
            <Tile label="Water-mask IoU (median)" value={mv.iou_median.toFixed(2)} sub={`range ${mv.iou_min.toFixed(2)}–${mv.iou_max.toFixed(2)} over ${mv.n_pairs} scene pairs`} />
            <Tile label="Label threshold" value={`${mv.label_threshold_m.toFixed(0)} m`} sub="max(20 m, 2 × measured median error)" />
          </div>
        )}
      </section>

      <section className="mt-10">
        <h2 className="text-xl font-semibold">2. Labels and features</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          A segment is positive if its bank moved landward by at least the threshold between the pass of the forecast date and the pass nearest 28 days
          later. For the label only, positions are confirmed forward over {ls?.confirm_days ?? 36} days (minimum over that window), so a flood edge that
          recedes is not counted as erosion. Features are strictly as-of: a unit test rebuilds them from data truncated at random dates and fails on any
          difference.
        </p>
        {ls && (
          <div className="mt-3 overflow-x-auto rounded-lg border bg-card">
            <table className="w-full min-w-[520px] text-sm">
              <thead className="border-b text-xs text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Split</th>
                  <th className="px-3 py-2 text-left font-medium">Forecast dates</th>
                  <th className="px-3 py-2 text-left font-medium">Segment-dates</th>
                  <th className="px-3 py-2 text-left font-medium">Positive rate</th>
                  <th className="px-3 py-2 text-left font-medium">Major (≥100 m) events</th>
                </tr>
              </thead>
              <tbody className="tabular">
                {(
                  [
                    ["Train 2015–2021", ls.train],
                    ["Calibrate 2022", ls.val],
                    ["Test 2023–2025", ls.test],
                  ] as const
                ).map(([n, s]) => (
                  <tr key={n} className="border-b last:border-0">
                    <td className="px-3 py-2 font-medium">{n}</td>
                    <td className="px-3 py-2">{s.forecast_dates}</td>
                    <td className="px-3 py-2">{s.rows.toLocaleString("en-US")}</td>
                    <td className="px-3 py-2">{pct(s.positive_rate, 1)}</td>
                    <td className="px-3 py-2">{s.major_events}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section id="evidence" className="mt-10 scroll-mt-20">
        <h2 className="text-xl font-semibold">3. Results on held-out years</h2>
        {t ? (
          <>
            <p className="mt-2 text-sm text-muted-foreground">
              Temporal hold-out: trained on 2015–2021, tuned and calibrated on 2022, scored once on {t.forecast_dates} forecast dates in 2023–2025
              ({t.rows.toLocaleString("en-US")} segment-dates, {pct(t.positive_rate, 1)} positive).
            </p>
            <div className="mt-3 overflow-x-auto rounded-lg border bg-card">
              <table className="w-full min-w-[680px] text-sm">
                <thead className="border-b text-xs text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Method</th>
                    <th className="px-3 py-2 text-left font-medium">Precision@20</th>
                    <th className="px-3 py-2 text-left font-medium">P@20, Jun–Oct</th>
                    <th className="px-3 py-2 text-left font-medium">PR-AUC</th>
                    <th className="px-3 py-2 text-left font-medium">Brier</th>
                    <th className="px-3 py-2 text-left font-medium">Major events in top 20</th>
                  </tr>
                </thead>
                <tbody>
                  <Row name="M1 — LightGBM, calibrated" s={t.M1} />
                  <Row name="B0 — persistence" s={t.B0_persistence} note="retreat over the last 84 days" />
                  <Row name="B1 — history" s={t.B1_history} note="retreat over the last 12 months" />
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-sm">
              Model − persistence, precision@20: <b>{(t.M1_minus_B0.all_dates.mean * 100).toFixed(1)} pts</b> (95% CI{" "}
              {(t.M1_minus_B0.all_dates.lo * 100).toFixed(1)} to {(t.M1_minus_B0.all_dates.hi * 100).toFixed(1)}); monsoon dates only{" "}
              {(t.M1_minus_B0.monsoon.mean * 100).toFixed(1)} pts ({(t.M1_minus_B0.monsoon.lo * 100).toFixed(1)} to{" "}
              {(t.M1_minus_B0.monsoon.hi * 100).toFixed(1)}).
            </p>
            {sp && (
              <p className="mt-2 text-sm">
                Spatial hold-out (trained on the {sp.train_segments} upstream segments, tested on the {sp.test_segments} downstream segments, 2023–2025):
                model {pct(sp.M1.precision_at_k, 1)} vs persistence {pct(sp.B0_persistence.precision_at_k, 1)}; difference{" "}
                <b>{(sp.M1_minus_B0.all_dates.mean * 100).toFixed(1)} pts</b> (95% CI {(sp.M1_minus_B0.all_dates.lo * 100).toFixed(1)} to{" "}
                {(sp.M1_minus_B0.all_dates.hi * 100).toFixed(1)}).
              </p>
            )}
            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <div className="rounded-lg border bg-card p-3">
                <h3 className="text-sm font-medium">Reliability on 2023–2025</h3>
                <p className="mb-2 text-xs text-muted-foreground">Does a predicted 30% mean 30% of segments eroded? Dot size = number of segment-dates.</p>
                <ReliabilityChart model={t.reliability_M1} baseline={t.reliability_B0} />
              </div>
              <div className="rounded-lg border bg-card p-3">
                <h3 className="text-sm font-medium">Ablation: remove one feature group</h3>
                <p className="mb-2 text-xs text-muted-foreground">Change in test precision@20 (percentage points) versus the full model. Coherence and the surrogate were not built.</p>
                {abRows.length ? <AblationChart rows={abRows} /> : <p className="text-xs text-muted-foreground">Not run yet.</p>}
              </div>
            </div>
          </>
        ) : (
          <p className="mt-2 text-sm text-muted-foreground">The test years have not been scored yet.</p>
        )}
      </section>

      <section className="mt-10">
        <h2 className="text-xl font-semibold">4. Claims ledger</h2>
        <p className="mt-2 text-sm text-muted-foreground">Generated by <code>python -m src.claims</code> from the metrics files. Only “Measured” rows are quoted anywhere.</p>
        <div className="mt-3">{m.claims ? <ClaimsLedger claims={m.claims} /> : <p className="text-sm text-muted-foreground">Not generated yet.</p>}</div>
      </section>

      <section className="mt-10">
        <h2 className="text-xl font-semibold">5. Limitations</h2>
        <ul className="mt-3 list-disc space-y-1.5 pl-5 text-sm text-muted-foreground">
          <li>One track, one reach. Revisit is 12 days on this track (S1B was lost in Dec 2021 and rarely acquired it), with longer gaps in 2015–16 and mid-2024.</li>
          <li>Stage is a radar proxy, not a gauge. Archived water-level forecasts were not available, so the model has no forward-looking forcing.</li>
          <li>Sentinel-2 validation covers only the part of the reach inside tile 45RYH (north of ~24.30°N) and dry-season dates.</li>
          <li>Labels come from the same radar masks as the features; systematic mask errors (e.g. bright wet sand) can affect both.</li>
          <li>No thermal-noise removal or terrain flattening; geolocation relies on the product&apos;s GCP grid.</li>
          <li>Reasons describe what the model used, not proven causes. The model has never been used with real officials.</li>
        </ul>
      </section>

      <section className="mt-10">
        <h2 className="text-xl font-semibold">6. Data and licences</h2>
        <ul className="mt-3 list-disc space-y-1.5 pl-5 text-sm text-muted-foreground">
          <li>Copernicus Sentinel-1 GRD and Sentinel-2 L2A (ESA/EU, free and open), via AWS Open Data buckets.</li>
          <li>Copernicus DEM GLO-30 (© DLR/Airbus, provided under COPERNICUS by the EU and ESA), optional bank-height feature.</li>
          <li>JRC Global Surface Water (Pekel et al., 2016) used only to look at the river before choosing the reach.</li>
        </ul>
      </section>
    </div>
  );
}

function Tile({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="rounded-lg border bg-card p-3">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-xl font-semibold">{value}</div>
      <div className="mt-0.5 text-[11px] text-muted-foreground">{sub}</div>
    </div>
  );
}
