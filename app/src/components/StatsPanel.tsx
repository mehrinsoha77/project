import type { Pass, Prediction } from "@/lib/api";
import { fmtDate } from "@/lib/utils";

type Props = { pass: Pass | undefined; preds: Prediction[] | undefined; totalSegments: number };

/** Four stat tiles for the selected pass. Counts only; no unmeasured numbers. */
export function StatsPanel({ pass, preds, totalSegments }: Props) {
  const observed = preds?.length ?? 0;
  const monitor = preds?.filter((p) => (p.last ?? 0) > 0).length ?? 0;
  const watch = preds?.filter((p) => p.tier === "watch" || p.tier === "warning_eligible").length ?? 0;
  const warn = preds?.filter((p) => p.tier === "warning_eligible").length ?? 0;
  const tiles = [
    { label: "Radar pass", value: pass ? fmtDate(pass.date) : "–", sub: pass ? `${pass.platform} · track 150 · 05:56 local` : "" },
    { label: "Segments seen", value: `${observed} / ${totalSegments}`, sub: "200 m segments with a bank line on this pass" },
    { label: "Retreat on this pass", value: String(monitor), sub: "Monitor tier (unconfirmed until next pass)" },
    { label: "Watch · Warning-eligible", value: `${watch} · ${warn}`, sub: "Warnings still need an official's approval" },
  ];
  return (
    <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
      {tiles.map((t) => (
        <div key={t.label} className="rounded-lg border bg-card p-3">
          <div className="text-[11px] text-muted-foreground">{t.label}</div>
          <div className="mt-0.5 text-lg font-semibold leading-tight">{t.value}</div>
          <div className="mt-0.5 text-[11px] leading-snug text-muted-foreground">{t.sub}</div>
        </div>
      ))}
    </div>
  );
}
