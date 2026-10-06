import { AlertTriangle, Eye, Radar } from "lucide-react";

export const TIER_COLOR = {
  warning_eligible: "#d03b3b",
  watch: "#fab219",
  monitor: "#ffffff",
  none: "#c3c2b7",
} as const;

export const OUTCOME_COLOR = { hit: "#0ca30c", miss: "#d03b3b", false_alarm: "#898781" } as const;

export function RiskLegend({ mode = "risk" }: { mode?: "risk" | "outcome" }) {
  if (mode === "outcome") {
    return (
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <LegendItem color={OUTCOME_COLOR.hit} label="Hit: flagged and eroded" />
        <LegendItem color={OUTCOME_COLOR.miss} label="Miss: eroded, not flagged" />
        <LegendItem color={OUTCOME_COLOR.false_alarm} label="False alarm: flagged, did not erode" />
      </div>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
      <span className="inline-flex items-center gap-1.5">
        <AlertTriangle className="h-3.5 w-3.5" style={{ color: TIER_COLOR.warning_eligible }} />
        <Swatch color={TIER_COLOR.warning_eligible} /> Warning-eligible (needs official approval)
      </span>
      <span className="inline-flex items-center gap-1.5">
        <Eye className="h-3.5 w-3.5" style={{ color: "#c98500" }} />
        <Swatch color={TIER_COLOR.watch} /> Watch: top 20 by calibrated risk
      </span>
      <span className="inline-flex items-center gap-1.5">
        <Radar className="h-3.5 w-3.5" />
        <span className="inline-block h-2.5 w-2.5 rounded-full border-2 border-foreground/70" /> Monitor: retreat ≥ threshold on this pass
      </span>
      <LegendItem color="#2a78d6" label="Bank line on this pass" line />
      <LegendItem color="#898781" label="Previous pass" line dashed />
    </div>
  );
}

function Swatch({ color }: { color: string }) {
  return <span className="inline-block h-1.5 w-4 rounded-full" style={{ background: color }} />;
}

function LegendItem({ color, label, line, dashed }: { color: string; label: string; line?: boolean; dashed?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      {line ? (
        <span className="inline-block w-5 border-t-2" style={{ borderColor: color, borderStyle: dashed ? "dashed" : "solid" }} />
      ) : (
        <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: color }} />
      )}
      {label}
    </span>
  );
}
