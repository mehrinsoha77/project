import Link from "next/link";
import { ArrowRight, BellRing, Building2, CloudOff, Droplets, Layers, LineChart, Radar, Ruler, ShieldCheck, Users } from "lucide-react";
import { Hero } from "@/components/Hero";
import { ClaimsLedger } from "@/components/ClaimsLedger";
import { Button } from "@/components/ui/button";
import { serverData } from "@/lib/server-data";
import { pct } from "@/lib/utils";

export default function Home() {
  const m = serverData.metrics();
  const wow = serverData.wow();
  const mv = m.mask_validation;
  const t = m.test_results?.temporal;
  const cov = m.test_results?.detection_coverage;
  const stats = [
    {
      label: "Bank line vs Sentinel-2",
      value: mv ? `${Math.round(mv.bank_error_median_m)} m median error` : "pending",
      sub: mv ? `${mv.n_pairs} cloud-free scene pairs, ${mv.n_transect_comparisons.toLocaleString("en-US")} transect checks` : "not yet measured",
    },
    {
      label: "Top-20 hit rate, 2023–2025",
      value: t ? `${pct(t.M1.precision_at_k)} vs ${pct(t.B0_persistence.precision_at_k)}` : "pending",
      sub: t ? `model vs persistence, ${t.M1.n_dates} held-out forecast dates` : "test years not yet run",
    },
    {
      label: "Radar passes processed",
      value: cov ? `${cov.passes_processed} of ${cov.passes_in_catalog}` : "pending",
      sub: "every descending track-150 pass, Jan 2015 – Dec 2025",
    },
  ];
  const levels = m.test_results?.success_levels;
  return (
    <>
      <Hero wow={wow} stats={stats} />

      <section className="container py-14">
        <h2 className="text-2xl font-semibold tracking-tight">The problem</h2>
        <p className="mt-2 max-w-3xl text-muted-foreground">
          The Jamuna is one of the world&apos;s largest braided rivers. Its banks shift by tens to hundreds of metres in a single
          season, taking homes, farmland and embankments with them — and much of that happens during the monsoon, exactly when
          help has the least information to work with.
        </p>
        <div className="mt-6 grid gap-4 md:grid-cols-3">
          {[
            {
              icon: CloudOff,
              title: "Optical satellites go blind",
              text: "Monsoon cloud hides the river from Sentinel-2 and Landsat for weeks at a time, right when banks are failing.",
            },
            {
              icon: Droplets,
              title: "Boats can't survey safely",
              text: "High, fast water makes field surveys dangerous during peak flow, so bank lines go unmeasured for months.",
            },
            {
              icon: LineChart,
              title: "Predictions are annual",
              text: "CEGIS publishes respected annual erosion predictions. Nobody publishes a pass-by-pass monsoon update with a tested short-horizon ranking.",
            },
          ].map((c) => (
            <div key={c.title} className="rounded-lg border bg-card p-4">
              <c.icon className="h-5 w-5 text-river" />
              <h3 className="mt-2 font-medium">{c.title}</h3>
              <p className="mt-1 text-sm text-muted-foreground">{c.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="border-y bg-card/60">
        <div className="container py-14">
          <h2 className="text-2xl font-semibold tracking-tight">How it works</h2>
          <p className="mt-2 max-w-3xl text-muted-foreground">Six small steps, each tested on its own. Everything runs on open data.</p>
          <ol className="mt-6 grid gap-3 md:grid-cols-3 lg:grid-cols-6">
            {[
              { icon: Radar, title: "Radar pass", text: "Sentinel-1 VV/VH, track 150, every 12 days. Calibrated, speckle-filtered, geocoded to 10 m." },
              { icon: Droplets, title: "Water mask", text: "Per-scene Otsu threshold on VV, VH rescue for wind-roughened water, small blobs cleaned." },
              { icon: Ruler, title: "Bank lines", text: "Braid-belt edge measured on 871 transects, every 200 m along both mainland banks." },
              { icon: Layers, title: "Features", text: "Recent retreat, channel distance, char shielding, river stage, season — only data before the forecast date." },
              { icon: LineChart, title: "28-day risk", text: "LightGBM, isotonic calibration, SHAP reasons. Always shown next to persistence." },
              { icon: BellRing, title: "Human decides", text: "Officials get the brief. A Warning reaches residents only after an official approves it." },
            ].map((s, i) => (
              <li key={s.title} className="rounded-lg border bg-card p-4">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-accent text-[11px] font-semibold text-accent-foreground">{i + 1}</span>
                  <s.icon className="h-4 w-4" />
                </div>
                <h3 className="mt-2 text-sm font-medium">{s.title}</h3>
                <p className="mt-1 text-xs text-muted-foreground">{s.text}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="container py-14">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">Evidence, not claims</h2>
            <p className="mt-2 max-w-3xl text-muted-foreground">
              Every number below came out of an experiment in the repository. The test years 2023–2025 were held out and scored once.
              Anything not measured is labelled as a target.
            </p>
          </div>
          <Button asChild variant="outline">
            <Link href="/about#evidence">
              Full results <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
        </div>
        {levels && (
          <div className="mt-6 grid gap-3 sm:grid-cols-3">
            {(
              [
                ["Minimum", levels.minimum, "Median bank error ≤ 20 m and detection across the full 2015–2025 archive"],
                ["Good", levels.good, "Model beats persistence on test precision@20, bootstrap 95% CI excludes zero"],
                ["Strong", levels.strong, "Beats persistence on temporal and spatial hold-outs, with a lower Brier score"],
              ] as const
            ).map(([name, ok, text]) => (
              <div key={name} className="rounded-lg border bg-card p-4">
                <div className="flex items-center gap-2">
                  <ShieldCheck className={ok ? "h-4 w-4 text-status-good" : "h-4 w-4 text-muted-foreground"} />
                  <span className="text-sm font-medium">{name} level</span>
                  <span className={ok ? "ml-auto text-xs font-medium text-[#006300] dark:text-[#5fd35f]" : "ml-auto text-xs text-muted-foreground"}>
                    {ok ? "reached" : "not reached"}
                  </span>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{text}</p>
              </div>
            ))}
          </div>
        )}
        {m.claims && (
          <div className="mt-6">
            <ClaimsLedger claims={m.claims} compact />
          </div>
        )}
      </section>

      <section className="border-y bg-card/60">
        <div className="container grid gap-8 py-14 md:grid-cols-2">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">Who it&apos;s for</h2>
            <ul className="mt-4 space-y-3 text-sm">
              <li className="flex gap-3">
                <Building2 className="mt-0.5 h-5 w-5 shrink-0 text-river" />
                <span>
                  <b>Upazila and union disaster management committees</b> and <b>BWDB field offices</b> along the Sirajganj–Tangail
                  reach: a weekly ranked list of segments, with reasons, to target inspections and emergency works.
                </span>
              </li>
              <li className="flex gap-3">
                <Users className="mt-0.5 h-5 w-5 shrink-0 text-river" />
                <span>
                  <b>NGOs working in char and riverbank areas</b>: the same list to plan relocation support and cash transfers before a
                  segment fails.
                </span>
              </li>
              <li className="flex gap-3">
                <BellRing className="mt-0.5 h-5 w-5 shrink-0 text-river" />
                <span>
                  <b>Riverbank households</b>, reached only through those institutions: an official approves each Warning before a
                  prerecorded Bangla voice call and SMS goes out.
                </span>
              </li>
            </ul>
          </div>
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">What it does not claim</h2>
            <ul className="mt-4 space-y-2 text-sm text-muted-foreground">
              <li>No 24-hour collapse forecast — radar revisits every 12 days on this track.</li>
              <li>No sub-metre maps — pixels are 10 m; results are per 200 m segment.</li>
              <li>No bed shear stress or pore pressure — the riverbed can&apos;t be seen from space.</li>
              <li>No &ldquo;works on any river&rdquo; — every new river is retrained and retested.</li>
              <li>No all-clear — the absence of an alert does not mean a bank is safe.</li>
            </ul>
          </div>
        </div>
      </section>

      <section className="container py-14 text-center">
        <h2 className="text-2xl font-semibold tracking-tight">Pick any date in 2023–2025. See what the model knew, then what happened.</h2>
        <div className="mt-6 flex justify-center gap-3">
          <Button asChild size="lg">
            <Link href="/demo">
              Start the replay <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link href="/about">Read the method</Link>
          </Button>
        </div>
      </section>
    </>
  );
}
