"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Eye, EyeOff, Lock, Play, RotateCcw } from "lucide-react";
import { api, type Banks, type Metrics, type Pass, type PredIndex, type Prediction, type Reach } from "@/lib/api";
import { bankGeometry, positionsFor } from "@/lib/banks";
import type { MapLine, MapMarker } from "@/components/Map";
import { OUTCOME_COLOR, RiskLegend, TIER_COLOR } from "@/components/RiskLegend";
import { Timeline } from "@/components/Timeline";
import { TopList } from "@/components/TopList";
import { SegmentCard } from "@/components/SegmentCard";
import { PrecisionChart } from "@/components/charts";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { fmtDate, pct, segmentLabel, signedPct } from "@/lib/utils";

const RiverMap = dynamic(() => import("@/components/Map"), {
  ssr: false,
  loading: () => <div className="flex h-full items-center justify-center text-sm text-muted-foreground">Loading map…</div>,
});

type Stage = "monsoon" | "frozen" | "revealed";

function pickDefaultDate(index: PredIndex): string | undefined {
  // The test date in a monsoon month with the most observed erosion: a demanding, not a flattering, choice.
  const c = index.filter((d) => d.split === "test" && d.has_outcome && [6, 7, 8, 9].includes(Number(d.date.slice(5, 7))));
  return c.sort((a, b) => (b.positives ?? 0) - (a.positives ?? 0))[0]?.date ?? index.find((d) => d.has_outcome)?.date;
}

export default function Demo() {
  const [reach, setReach] = useState<Reach>();
  const [passes, setPasses] = useState<Pass[]>([]);
  const [index, setIndex] = useState<PredIndex>([]);
  const [metrics, setMetrics] = useState<Metrics>();
  const [banks, setBanks] = useState<Record<number, Banks>>({});
  const [date, setDate] = useState<string>();
  const [preds, setPreds] = useState<Prediction[]>();
  const [stage, setStage] = useState<Stage>("monsoon");
  const [rankKey, setRankKey] = useState<"rank" | "b0_rank">("rank");
  const [sel, setSel] = useState<string | null>(null);
  const [mi, setMi] = useState(0);

  useEffect(() => {
    Promise.all([api.reach(), api.passes(), api.predIndex(), api.metrics()]).then(([r, p, ix, m]) => {
      setReach(r);
      setPasses(p);
      setIndex(ix);
      setMetrics(m);
      setDate(pickDefaultDate(ix));
    });
  }, []);

  const year = date ? Number(date.slice(0, 4)) : undefined;
  const monsoon = useMemo(
    () => passes.filter((p) => year && p.date.startsWith(String(year)) && p.date.slice(5, 7) >= "05" && p.date.slice(5, 7) <= "10" && p.image),
    [passes, year],
  );
  const needYear = useCallback(
    (y: number) => {
      if (!banks[y]) api.banks(y).then((b) => setBanks((s) => ({ ...s, [y]: b })));
    },
    [banks],
  );
  useEffect(() => {
    if (!date) return;
    api.predictions(date).then(setPreds);
    needYear(Number(date.slice(0, 4)));
    needYear(Number(date.slice(0, 4)) + 1);
    setMi(0);
  }, [date]); // eslint-disable-line react-hooks/exhaustive-deps

  const pass = passes.find((p) => p.date === date);
  const target = preds?.find((p) => p.target)?.target ?? null;
  const targetPass = passes.find((p) => p.date === target);
  const shownPass = stage === "monsoon" ? monsoon[mi] : stage === "revealed" && targetPass ? targetPass : pass;

  const geomAt = useCallback(
    (p: Pass | undefined) => (reach && p ? bankGeometry(reach, positionsFor(banks[Number(p.date.slice(0, 4))], p.pass_id)) : null),
    [reach, banks],
  );

  const { lines, markers, summary } = useMemo(() => {
    const lines: MapLine[] = [];
    const markers: MapMarker[] = [];
    const summary = { model: 0, persistence: 0, positives: 0, majors: 0, majorsCaught: 0 };
    if (!reach) return { lines, markers, summary };
    if (stage === "monsoon") {
      const g = geomAt(monsoon[mi]);
      const g0 = geomAt(monsoon[0]);
      g0?.lines.forEach((l, k) => lines.push({ id: `start|${k}`, positions: l, color: "#c3c2b7", weight: 1.5, dash: "4 4", interactive: false }));
      g?.lines.forEach((l, k) => lines.push({ id: `now|${k}`, positions: l, color: "#6da7ec", weight: 2.5, interactive: false }));
      return { lines, markers, summary };
    }
    const g = geomAt(pass);
    const gt = stage === "revealed" ? geomAt(targetPass) : null;
    g?.lines.forEach((l, k) => lines.push({ id: `t0|${k}`, positions: l, color: stage === "revealed" ? "#c3c2b7" : "#6da7ec", weight: 2, dash: stage === "revealed" ? "4 4" : undefined, interactive: false }));
    gt?.lines.forEach((l, k) => lines.push({ id: `t1|${k}`, positions: l, color: "#6da7ec", weight: 2, interactive: false }));
    for (const p of preds ?? []) {
      if (p.y === 1) summary.positives++;
      if (p.major === 1) summary.majors++;
      if (p.rank <= 20 && p.y === 1) summary.model++;
      if (p.b0_rank <= 20 && p.y === 1) summary.persistence++;
      if (p.rank <= 20 && p.major === 1) summary.majorsCaught++;
      const seg = g?.segments.get(p.id);
      const pt = g?.points.get(p.id);
      if (!seg || !pt) continue;
      const inTop = p[rankKey] <= 20;
      if (stage === "frozen" && inTop) {
        const color = rankKey === "rank" ? TIER_COLOR[p.tier === "warning_eligible" ? "warning_eligible" : "watch"] : "#eb6834";
        lines.push({ id: `${p.id}|hl`, positions: seg, color, weight: 7, tooltip: `#${p[rankKey]} ${segmentLabel(p.id)}` });
        markers.push({ id: `${p.id}|rk`, at: pt, color, radius: 4, label: `${p[rankKey]}`, stroke: "#000" });
      }
      if (stage === "revealed" && p.y !== null) {
        const kind = inTop ? (p.y ? "hit" : "false_alarm") : p.y ? "miss" : null;
        if (kind) {
          lines.push({ id: `${p.id}|oc`, positions: seg, color: OUTCOME_COLOR[kind], weight: 7, tooltip: `${segmentLabel(p.id)} · moved ${p.retreat ?? "?"} m` });
          if (inTop) markers.push({ id: `${p.id}|rk`, at: pt, color: OUTCOME_COLOR[kind], radius: 4, label: `${p[rankKey]}`, stroke: "#000" });
        }
      }
    }
    if (sel) {
      const pt = g?.points.get(sel);
      if (pt) markers.push({ id: `${sel}|sel`, at: pt, color: "#2a78d6", fillOpacity: 0.25, radius: 11 });
    }
    return { lines, markers, summary };
  }, [reach, stage, monsoon, mi, pass, targetPass, preds, rankKey, sel, geomAt]);

  if (!reach || !date) return <div className="container py-10 text-sm text-muted-foreground">Loading…</div>;

  const t = metrics?.test_results?.temporal;
  const testDates = index.filter((d) => d.split === "test" && d.has_outcome);
  const radarUrl = shownPass?.image ? `/data/${shownPass.image}` : null;

  return (
    <div className="container py-4">
      <div className="mb-3">
        <h1 className="text-xl font-semibold tracking-tight">Replay: what the model knew, then what happened</h1>
        <p className="text-sm text-muted-foreground">
          A replay of real history, not a live fetch. Every map is a real Sentinel-1 pass; every outcome is a measured bank line.
        </p>
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Step n={1} active={stage === "monsoon"} onClick={() => setStage("monsoon")} label="Watch the monsoon" />
        <Step n={2} active={stage === "frozen"} onClick={() => setStage("frozen")} label="Freeze the model" />
        <Step n={3} active={stage === "revealed"} onClick={() => setStage("revealed")} label="Reveal 28 days later" />
        <div className="ml-auto flex items-center gap-2 text-xs">
          <label htmlFor="date" className="text-muted-foreground">
            Forecast date (2023–2025)
          </label>
          <select
            id="date"
            className="rounded-md border bg-card px-2 py-1 text-sm"
            value={date}
            onChange={(e) => {
              setDate(e.target.value);
              setStage("frozen");
              setSel(null);
            }}
          >
            {testDates.map((d) => (
              <option key={d.date} value={d.date}>
                {d.date}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-[1fr_380px]">
        <div className="flex min-w-0 flex-col gap-2">
          <AnimatePresence mode="wait">
            <motion.div key={stage} initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="rounded-lg border bg-card px-3 py-2 text-sm">
              {stage === "monsoon" && (
                <span>
                  <b>Monsoon {year}, pass by pass.</b> Optical satellites saw almost nothing for weeks. Radar saw the bank on every pass. Dashed:
                  bank on {monsoon[0] ? fmtDate(monsoon[0].date) : "–"}; blue: bank on the pass shown.
                </span>
              )}
              {stage === "frozen" && (
                <span className="flex flex-wrap items-center gap-2">
                  <Lock className="h-4 w-4 text-river" />
                  <b>The model only knows data up to {fmtDate(date)}.</b>
                  <code className="rounded bg-muted px-1.5 py-0.5 text-[11px]">positions[positions.date &lt;= &quot;{date}&quot;] → build_features → M1</code>
                </span>
              )}
              {stage === "revealed" && (
                <span>
                  <b>{target ? fmtDate(target) : "Next pass"}:</b> model top 20 caught <b>{summary.model}</b>, persistence top 20 caught{" "}
                  <b>{summary.persistence}</b>, of <b>{summary.positives}</b> segments that lost ≥ {metrics?.label_stats?.threshold_m ?? 20} m. Major (≥100 m)
                  events in the model&apos;s top 20: {summary.majorsCaught} of {summary.majors}.
                </span>
              )}
            </motion.div>
          </AnimatePresence>
          <div className="relative h-[60vh] min-h-[420px] overflow-hidden rounded-lg border">
            <RiverMap reach={reach} image={radarUrl ? { url: radarUrl, opacity: 1 } : null} lines={lines} markers={markers} onSelect={(id) => setSel(id)} focus={null} />
            <div className="pointer-events-none absolute bottom-2 left-2 z-[500] rounded bg-black/60 px-2 py-1 text-[11px] text-white">
              Radar pass {shownPass ? fmtDate(shownPass.date) : "–"}
            </div>
          </div>
          {stage === "monsoon" ? (
            monsoon.length ? (
              <Timeline dates={monsoon.map((p) => p.date)} value={mi} onChange={setMi} playMs={1100} />
            ) : (
              <p className="text-xs text-muted-foreground">No radar previews exported for this monsoon.</p>
            )
          ) : (
            <RiskLegend mode={stage === "revealed" ? "outcome" : "risk"} />
          )}
          <div className="flex flex-wrap gap-2">
            {stage === "monsoon" && (
              <Button onClick={() => setStage("frozen")}>
                <Play className="h-4 w-4" /> Freeze the model on {fmtDate(date)}
              </Button>
            )}
            {stage === "frozen" && (
              <Button onClick={() => setStage("revealed")}>
                <Eye className="h-4 w-4" /> Reveal what happened
              </Button>
            )}
            {stage === "revealed" && (
              <Button variant="outline" onClick={() => setStage("frozen")}>
                <EyeOff className="h-4 w-4" /> Hide outcome
              </Button>
            )}
            <Button variant="ghost" onClick={() => { setStage("monsoon"); setMi(0); setSel(null); }}>
              <RotateCcw className="h-4 w-4" /> Restart
            </Button>
          </div>
        </div>

        <aside className="min-w-0 space-y-3">
          {stage !== "monsoon" && preds && (
            <>
              <Tabs value={rankKey} onValueChange={(v) => setRankKey(v as "rank" | "b0_rank")}>
                <TabsList className="w-full">
                  <TabsTrigger value="rank" className="flex-1">
                    Model top 20
                  </TabsTrigger>
                  <TabsTrigger value="b0_rank" className="flex-1">
                    Persistence top 20
                  </TabsTrigger>
                </TabsList>
              </Tabs>
              {sel ? (
                <SegmentCard id={sel} reach={reach} pred={preds.find((p) => p.id === sel)} forecastDate={date} revealed={stage === "revealed"} onClose={() => setSel(null)} />
              ) : (
                <TopList preds={preds} onSelect={setSel} revealed={stage === "revealed"} rankKey={rankKey} />
              )}
              <p className="text-[11px] text-muted-foreground">
                <b>Skeptic test:</b> pick any date above and click any segment. Its history is cut at the forecast date until you reveal the outcome.
              </p>
            </>
          )}
          {stage === "monsoon" && (
            <div className="rounded-lg border bg-card p-3 text-sm text-muted-foreground">
              Press play under the map to step through every radar pass of the {year} monsoon. Then freeze the model on {fmtDate(date)} and
              see its top 20 before the outcome is shown.
            </div>
          )}
        </aside>
      </div>

      <section className="mt-8">
        <h2 className="text-lg font-semibold tracking-tight">Every held-out forecast date, 2023–2025</h2>
        {t ? (
          <p className="mt-1 text-sm text-muted-foreground">
            Mean precision@20: model {pct(t.M1.precision_at_k, 1)}, persistence {pct(t.B0_persistence.precision_at_k, 1)}, history{" "}
            {pct(t.B1_history.precision_at_k, 1)}. Difference model − persistence {signedPct(t.M1_minus_B0.all_dates.mean)} (95% CI{" "}
            {signedPct(t.M1_minus_B0.all_dates.lo)} to {signedPct(t.M1_minus_B0.all_dates.hi)}, moving-block bootstrap over {t.M1_minus_B0.all_dates.n_dates} dates).
          </p>
        ) : (
          <p className="mt-1 text-sm text-muted-foreground">Test results not yet generated.</p>
        )}
        <div className="mt-3 rounded-lg border bg-card p-3">
          <PrecisionChart
            data={index.filter((d) => d.split === "test" && d.has_outcome).map((d) => ({ date: d.date, model: d.p20_model, persistence: d.p20_persistence }))}
            highlight={date}
          />
        </div>
      </section>
    </div>
  );
}

function Step({ n, active, onClick, label }: { n: number; active: boolean; onClick: () => void; label: string }) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs ${active ? "border-primary bg-accent text-accent-foreground" : "bg-card text-muted-foreground hover:text-foreground"}`}
    >
      <span className={`inline-flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-semibold ${active ? "bg-primary text-white" : "bg-muted"}`}>{n}</span>
      {label}
    </button>
  );
}
