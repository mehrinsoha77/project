"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { fmtDate } from "@/lib/utils";

const AXIS = { stroke: "var(--chart-axis)", tick: { fill: "var(--chart-muted)", fontSize: 11 }, tickLine: false };
const GRID = { stroke: "var(--chart-grid)", strokeDasharray: undefined, vertical: false };

function Tip({ active, payload, label, fmt }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border bg-card px-2.5 py-1.5 text-xs shadow-md">
      {label !== undefined && <div className="mb-0.5 font-medium">{fmt ? fmt(label) : label}</div>}
      {payload.map((p: any) => (
        <div key={p.dataKey} className="flex items-center gap-1.5 text-muted-foreground">
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: p.color ?? p.payload?.fill }} />
          <span>{p.name}</span>
          <span className="ml-auto pl-3 font-medium text-foreground tabular">{p.value === null ? "–" : p.value}</span>
        </div>
      ))}
    </div>
  );
}

function Legend({ items }: { items: { color: string; label: string; dashed?: boolean }[] }) {
  return (
    <div className="mb-1 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
      {items.map((i) => (
        <span key={i.label} className="inline-flex items-center gap-1.5">
          <span className="inline-block w-4 border-t-2" style={{ borderColor: i.color, borderStyle: i.dashed ? "dashed" : "solid" }} />
          {i.label}
        </span>
      ))}
    </div>
  );
}

/** Bank position over time for one segment. Up = landward = land lost. */
export function BankSeriesChart({
  data,
  forecastDate,
  targetDate,
  revealed = true,
  height = 180,
}: {
  data: { date: string; pos: number | null }[];
  forecastDate?: string;
  targetDate?: string | null;
  revealed?: boolean;
  height?: number;
}) {
  const shown = revealed || !forecastDate ? data : data.filter((d) => d.date <= forecastDate);
  const ts = shown.map((d) => ({ t: Date.parse(`${d.date}T00:00:00Z`), pos: d.pos, date: d.date }));
  const tf = forecastDate ? Date.parse(`${forecastDate}T00:00:00Z`) : undefined;
  const tt = targetDate ? Date.parse(`${targetDate}T00:00:00Z`) : undefined;
  const domain: [number, number] | undefined = data.length
    ? [Date.parse(`${data[0].date}T00:00:00Z`), Date.parse(`${data[data.length - 1].date}T00:00:00Z`)]
    : undefined;
  return (
    <div style={{ height }}>
      <ResponsiveContainer>
        <LineChart data={ts} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid {...GRID} />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={domain ?? ["dataMin", "dataMax"]}
            tickFormatter={(v) => new Date(v).getUTCFullYear().toString()}
            {...AXIS}
            minTickGap={24}
          />
          <YAxis width={44} {...AXIS} tickFormatter={(v) => `${v}`} label={{ value: "m landward", angle: -90, position: "insideLeft", fill: "var(--chart-muted)", fontSize: 10, dy: 30 }} />
          {tf && tt && revealed && <ReferenceArea x1={tf} x2={tt} fill="#2a78d6" fillOpacity={0.08} />}
          {tf && <ReferenceLine x={tf} stroke="var(--chart-ink-2)" strokeWidth={1} label={{ value: "forecast", fill: "var(--chart-muted)", fontSize: 10, position: "insideTopLeft" }} />}
          <Tooltip content={<Tip fmt={(v: number) => fmtDate(new Date(v).toISOString().slice(0, 10))} />} />
          <Line dataKey="pos" name="Bank position (m)" stroke="var(--series-1)" strokeWidth={2} dot={{ r: 2, strokeWidth: 0, fill: "var(--series-1)" }} activeDot={{ r: 4 }} connectNulls isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Precision@20 per forecast date: model vs persistence. */
export function PrecisionChart({
  data,
  height = 240,
  highlight,
}: {
  data: { date: string; model: number | null; persistence: number | null }[];
  height?: number;
  highlight?: string;
}) {
  const ts = data.map((d) => ({
    t: Date.parse(`${d.date}T00:00:00Z`),
    model: d.model === null ? null : Math.round(d.model * 100),
    persistence: d.persistence === null ? null : Math.round(d.persistence * 100),
  }));
  return (
    <div>
      <Legend
        items={[
          { color: "var(--series-1)", label: "NadiNet model (M1)" },
          { color: "var(--series-2)", label: "Persistence (B0): eroded in last 84 days" },
        ]}
      />
      <div style={{ height }}>
        <ResponsiveContainer>
          <LineChart data={ts} margin={{ top: 6, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid {...GRID} />
            <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} tickFormatter={(v) => fmtDate(new Date(v).toISOString().slice(0, 10), { month: "short", year: "2-digit" })} {...AXIS} minTickGap={36} />
            <YAxis width={40} domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tickFormatter={(v) => `${v}%`} {...AXIS} />
            {highlight && <ReferenceLine x={Date.parse(`${highlight}T00:00:00Z`)} stroke="var(--chart-ink-2)" />}
            <Tooltip content={<Tip fmt={(v: number) => fmtDate(new Date(v).toISOString().slice(0, 10))} />} />
            <Line dataKey="model" name="Model P@20 (%)" stroke="var(--series-1)" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
            <Line dataKey="persistence" name="Persistence P@20 (%)" stroke="var(--series-2)" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/** Reliability diagram: does a 0.7 mean 70%? */
export function ReliabilityChart({
  model,
  baseline,
  height = 260,
}: {
  model: { mean_pred: number; observed: number; n: number }[];
  baseline?: { mean_pred: number; observed: number; n: number }[];
  height?: number;
}) {
  const m = model.map((r) => ({ x: +(r.mean_pred * 100).toFixed(1), y: +(r.observed * 100).toFixed(1), n: r.n }));
  const b = (baseline ?? []).map((r) => ({ x: +(r.mean_pred * 100).toFixed(1), y: +(r.observed * 100).toFixed(1), n: r.n }));
  return (
    <div>
      <Legend
        items={[
          { color: "var(--series-1)", label: "Model, calibrated" },
          ...(baseline ? [{ color: "var(--series-2)", label: "Persistence, calibrated" }] : []),
          { color: "var(--chart-muted)", label: "Perfect calibration", dashed: true },
        ]}
      />
      <div style={{ height }}>
        <ResponsiveContainer>
          <ScatterChart margin={{ top: 6, right: 12, bottom: 14, left: 0 }}>
            <CartesianGrid {...GRID} vertical />
            <XAxis type="number" dataKey="x" domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tickFormatter={(v) => `${v}%`} {...AXIS} label={{ value: "predicted probability", position: "insideBottom", dy: 14, fill: "var(--chart-muted)", fontSize: 10 }} />
            <YAxis type="number" dataKey="y" domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tickFormatter={(v) => `${v}%`} width={40} {...AXIS} />
            <ZAxis type="number" dataKey="n" range={[40, 220]} />
            <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 100, y: 100 }]} stroke="var(--chart-muted)" strokeDasharray="4 4" />
            <Tooltip content={<Tip />} />
            <Scatter name="Model" data={m} fill="var(--series-1)" line={{ stroke: "var(--series-1)", strokeWidth: 2 }} isAnimationActive={false} />
            {baseline && <Scatter name="Persistence" data={b} fill="var(--series-2)" line={{ stroke: "var(--series-2)", strokeWidth: 2 }} isAnimationActive={false} />}
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/** Ablation: change in precision@20 when a feature group is removed. */
export function AblationChart({ rows, height = 260 }: { rows: { group: string; delta: number }[]; height?: number }) {
  const data = rows.map((r) => ({ ...r, pts: +(r.delta * 100).toFixed(1) }));
  return (
    <div style={{ height }}>
      <ResponsiveContainer>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, bottom: 0, left: 8 }}>
          <CartesianGrid {...GRID} horizontal={false} vertical />
          <XAxis type="number" {...AXIS} tickFormatter={(v) => `${v > 0 ? "+" : ""}${v}`} />
          <YAxis type="category" dataKey="group" width={128} {...AXIS} />
          <ReferenceLine x={0} stroke="var(--chart-axis)" />
          <Tooltip content={<Tip />} cursor={{ fill: "var(--chart-grid)", opacity: 0.4 }} />
          <Bar dataKey="pts" name="Δ precision@20 (pts)" barSize={14} isAnimationActive={false}>
            {data.map((d) => (
              <Cell key={d.group} fill="var(--series-1)" radius={(d.pts < 0 ? [4, 0, 0, 4] : [0, 4, 4, 0]) as any} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
