"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Info, Layers } from "lucide-react";
import { api, type Banks, type Metrics, type Pass, type PredIndex, type Prediction, type Reach } from "@/lib/api";
import { bankGeometry, positionsFor, type LatLon } from "@/lib/banks";
import type { MapLine, MapMarker } from "@/components/Map";
import { RiskLegend, TIER_COLOR } from "@/components/RiskLegend";
import { StatsPanel } from "@/components/StatsPanel";
import { Timeline } from "@/components/Timeline";
import { TopList } from "@/components/TopList";
import { SegmentCard } from "@/components/SegmentCard";
import { AlertPanel } from "@/components/AlertPanel";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { fmtDate, segmentLabel } from "@/lib/utils";

const RiverMap = dynamic(() => import("@/components/Map"), {
  ssr: false,
  loading: () => <div className="flex h-full items-center justify-center text-sm text-muted-foreground">Loading map…</div>,
});

export default function Dashboard() {
  const [reach, setReach] = useState<Reach>();
  const [passes, setPasses] = useState<Pass[]>([]);
  const [index, setIndex] = useState<PredIndex>([]);
  const [metrics, setMetrics] = useState<Metrics>();
  const [i, setI] = useState(-1);
  const [preds, setPreds] = useState<Prediction[]>();
  const [banks, setBanks] = useState<Record<number, Banks>>({});
  const [sel, setSel] = useState<string | null>(null);
  const [tab, setTab] = useState("top");
  const [radar, setRadar] = useState(true);
  const [street, setStreet] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.reach(), api.passes(), api.predIndex(), api.metrics()])
      .then(([r, p, ix, m]) => {
        setReach(r);
        setPasses(p);
        setIndex(ix);
        setMetrics(m);
        setI(ix.length - 1);
      })
      .catch((e) => setError(String(e)));
  }, []);

  const date = index[i]?.date;
  const pass = passes.find((p) => p.date === date);
  const passIdx = passes.findIndex((p) => p.date === date);
  const prev = passIdx > 0 ? passes[passIdx - 1] : undefined;

  useEffect(() => {
    if (!date) return;
    api.predictions(date).then(setPreds);
    const years = new Set([Number(date.slice(0, 4)), prev ? Number(prev.date.slice(0, 4)) : Number(date.slice(0, 4))]);
    years.forEach((y) => {
      if (!banks[y]) api.banks(y).then((b) => setBanks((s) => ({ ...s, [y]: b })));
    });
  }, [date]); // eslint-disable-line react-hooks/exhaustive-deps

  const geom = useMemo(() => {
    if (!reach || !pass) return null;
    return bankGeometry(reach, positionsFor(banks[Number(pass.date.slice(0, 4))], pass.pass_id));
  }, [reach, pass, banks]);
  const prevGeom = useMemo(() => {
    if (!reach || !prev) return null;
    return bankGeometry(reach, positionsFor(banks[Number(prev.date.slice(0, 4))], prev.pass_id));
  }, [reach, prev, banks]);

  const { lines, markers } = useMemo(() => {
    const lines: MapLine[] = [];
    const markers: MapMarker[] = [];
    if (!geom || !preds) return { lines, markers };
    prevGeom?.lines.forEach((l, k) => lines.push({ id: `prev|${k}`, positions: l, color: "#c3c2b7", weight: 1.5, opacity: 0.8, dash: "4 4", interactive: false }));
    geom.lines.forEach((l, k) => lines.push({ id: `bank|${k}`, positions: l, color: "#6da7ec", weight: 2, interactive: false }));
    for (const p of preds) {
      const seg = geom.segments.get(p.id);
      const pt = geom.points.get(p.id);
      if (!seg || !pt) continue;
      if (p.tier === "watch" || p.tier === "warning_eligible") {
        lines.push({
          id: `${p.id}|hl`,
          positions: seg,
          color: TIER_COLOR[p.tier],
          weight: p.tier === "warning_eligible" ? 8 : 6,
          tooltip: `#${p.rank} ${segmentLabel(p.id)} · ${(p.p * 100).toFixed(0)}%`,
        });
        markers.push({ id: `${p.id}|rk`, at: pt, color: TIER_COLOR[p.tier], radius: 4, label: `${p.rank}`, stroke: "#000" });
      } else if ((p.last ?? 0) > 0) {
        markers.push({ id: `${p.id}|mon`, at: pt, color: "#000000", fillOpacity: 0, radius: 3, stroke: "#ffffff", tooltip: `${segmentLabel(p.id)}: retreat on this pass` });
      }
    }
    if (sel) {
      const pt = geom.points.get(sel);
      if (pt) markers.push({ id: `${sel}|sel`, at: pt, color: "#2a78d6", fillOpacity: 0.25, radius: 11, stroke: "#ffffff" });
    }
    return { lines, markers };
  }, [geom, prevGeom, preds, sel]);

  const select = useCallback((id: string) => {
    setSel(id);
    setTab("segment");
  }, []);
  const focus: LatLon | null = sel && geom ? geom.points.get(sel) ?? null : null;

  if (error) return <div className="container py-10 text-sm text-status-critical">Could not load data: {error}. Run `python -m src.api.export`.</div>;
  if (!reach || !date) return <div className="container py-10 text-sm text-muted-foreground">Loading…</div>;

  const entry = index[i];
  const radarUrl = pass?.image && radar ? `/data/${pass.image}` : null;
  return (
    <div className="container py-4">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">{reach.name}</h1>
          <p className="text-xs text-muted-foreground">
            Forecast issued after the pass of {fmtDate(date)} · horizon 28 days · {entry.split === "test" ? "held-out test year" : "calibration year"}
            {!entry.has_outcome && " · outcome not yet observed"}
          </p>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <label className="inline-flex items-center gap-1.5">
            <input type="checkbox" checked={radar} onChange={(e) => setRadar(e.target.checked)} /> Radar image
          </label>
          <label className="inline-flex items-center gap-1.5" title="Needs internet">
            <input type="checkbox" checked={street} onChange={(e) => setStreet(e.target.checked)} /> Street map (online)
          </label>
        </div>
      </div>
      <StatsPanel pass={pass} preds={preds} totalSegments={reach.transects.length} />
      <div className="mt-3 grid gap-3 lg:grid-cols-[1fr_380px]">
        <div className="flex min-w-0 flex-col gap-2">
          <div className="relative h-[62vh] min-h-[420px] overflow-hidden rounded-lg border">
            <RiverMap reach={reach} image={radarUrl ? { url: radarUrl, opacity: 1 } : null} lines={lines} markers={markers} onSelect={select} street={street} focus={focus} />
            {!pass?.image && (
              <div className="pointer-events-none absolute left-2 top-2 z-[500] inline-flex items-center gap-1 rounded bg-black/60 px-2 py-1 text-[11px] text-white">
                <Layers className="h-3 w-3" /> No radar preview exported for this pass
              </div>
            )}
          </div>
          <Timeline
            dates={index.map((d) => d.date)}
            value={i}
            onChange={setI}
            marks={index.map((d, k) => ({ index: k, color: d.split === "test" ? "#2a78d6" : "#898781", title: d.date }))}
          />
          <RiskLegend />
        </div>
        <aside className="min-w-0">
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList className="w-full">
              <TabsTrigger value="top" className="flex-1">
                Top 20
              </TabsTrigger>
              <TabsTrigger value="segment" className="flex-1">
                Segment
              </TabsTrigger>
              <TabsTrigger value="alerts" className="flex-1">
                Alerts
              </TabsTrigger>
            </TabsList>
            <TabsContent value="top">
              {preds ? <TopList preds={preds} selected={sel} onSelect={select} /> : <p className="text-sm text-muted-foreground">Loading…</p>}
              <p className="mt-2 flex gap-1.5 text-[11px] text-muted-foreground">
                <Info className="mt-0.5 h-3 w-3 shrink-0" />
                Risk = calibrated probability of losing ≥ {metrics?.label_stats?.threshold_m ?? 20} m within 28 days. The absence of an alert does not mean a bank is safe.
              </p>
            </TabsContent>
            <TabsContent value="segment">
              {sel ? (
                <SegmentCard id={sel} reach={reach} pred={preds?.find((p) => p.id === sel)} forecastDate={date} onClose={() => setSel(null)} />
              ) : (
                <p className="text-sm text-muted-foreground">Click a segment on the map or in the Top 20 list.</p>
              )}
            </TabsContent>
            <TabsContent value="alerts">{preds && <AlertPanel date={date} preds={preds} onFocus={select} />}</TabsContent>
          </Tabs>
        </aside>
      </div>
    </div>
  );
}
