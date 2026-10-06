"use client";

import { AlertTriangle, Eye } from "lucide-react";
import type { Prediction } from "@/lib/api";
import { cn, pct, segmentLabel, signedMetres } from "@/lib/utils";
import { OUTCOME_COLOR } from "@/components/RiskLegend";

type Props = {
  preds: Prediction[];
  selected?: string | null;
  onSelect: (id: string) => void;
  revealed?: boolean;
  rankKey?: "rank" | "b0_rank";
  k?: number;
};

/** The ranked list officials actually use. */
export function TopList({ preds, selected, onSelect, revealed = false, rankKey = "rank", k = 20 }: Props) {
  const top = preds.filter((p) => p[rankKey] <= k).sort((a, b) => a[rankKey] - b[rankKey]);
  return (
    <ol className="divide-y rounded-lg border bg-card">
      {top.map((p) => {
        const outcome = revealed && p.y !== null ? (p.y ? "hit" : "false_alarm") : null;
        return (
          <li key={p.id}>
            <button
              onClick={() => onSelect(p.id)}
              className={cn("flex w-full items-start gap-2 px-3 py-2 text-left hover:bg-muted", selected === p.id && "bg-accent")}
            >
              <span className="mt-0.5 w-6 shrink-0 text-xs font-semibold tabular text-muted-foreground">#{p[rankKey]}</span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5 text-sm font-medium">
                  {rankKey === "rank" && p.tier === "warning_eligible" ? (
                    <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-status-critical" aria-label="Warning-eligible" />
                  ) : rankKey === "rank" ? (
                    <Eye className="h-3.5 w-3.5 shrink-0 text-[#c98500]" aria-label="Watch" />
                  ) : null}
                  <span className="truncate">{segmentLabel(p.id)}</span>
                </span>
                {p.reasons?.[0] && rankKey === "rank" && <span className="block truncate text-[11px] text-muted-foreground">{p.reasons[0]}</span>}
                {rankKey === "b0_rank" && <span className="block text-[11px] text-muted-foreground">retreat in last 12 weeks: {signedMetres(p.ret84)}</span>}
              </span>
              <span className="shrink-0 text-right">
                <span className="block text-sm font-semibold tabular">{rankKey === "rank" ? pct(p.p) : signedMetres(p.ret84)}</span>
                {outcome ? (
                  <span className="inline-flex items-center gap-1 text-[11px]">
                    <span className="inline-block h-2 w-2 rounded-full" style={{ background: OUTCOME_COLOR[outcome] }} />
                    {p.y ? `lost ${signedMetres(p.retreat)}` : `moved ${signedMetres(p.retreat)}`}
                  </span>
                ) : (
                  <span className="block text-[11px] text-muted-foreground tabular">last pass {signedMetres(p.last)}</span>
                )}
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
