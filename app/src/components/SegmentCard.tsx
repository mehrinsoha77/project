"use client";

import { useEffect, useState } from "react";
import { MapPin, X } from "lucide-react";
import { api, type Prediction, type Reach } from "@/lib/api";
import { BankSeriesChart } from "@/components/charts";
import { Badge } from "@/components/ui/badge";
import { BANK_LABEL, cn, fmtDate, pct, segmentLabel, signedMetres } from "@/lib/utils";
import { TIER_COLOR } from "@/components/RiskLegend";

const YEARS = Array.from({ length: 11 }, (_, i) => 2015 + i);

/** Full bank-position history of one segment, from the per-year static files. */
export function useSegmentHistory(id: string | null) {
  const [data, setData] = useState<{ date: string; pos: number | null }[]>([]);
  useEffect(() => {
    if (!id) return;
    let alive = true;
    Promise.all(YEARS.map((y) => api.banks(y).catch(() => null))).then((all) => {
      if (!alive) return;
      const out: { date: string; pos: number | null }[] = [];
      for (const b of all) {
        if (!b) continue;
        const i = b.transects.indexOf(id);
        if (i < 0) continue;
        b.passes.forEach((pid, j) => out.push({ date: `${pid.slice(0, 4)}-${pid.slice(4, 6)}-${pid.slice(6, 8)}`, pos: b.pos[j][i] }));
      }
      setData(out.sort((a, b) => a.date.localeCompare(b.date)));
    });
    return () => {
      alive = false;
    };
  }, [id]);
  return data;
}

const TIER_LABEL: Record<string, string> = {
  warning_eligible: "Warning-eligible",
  watch: "Watch",
  monitor: "Monitor",
  none: "Below Watch",
};

type Props = {
  id: string;
  reach: Reach;
  pred?: Prediction;
  forecastDate: string;
  revealed?: boolean;
  onClose?: () => void;
};

export function SegmentCard({ id, reach, pred, forecastDate, revealed = true, onClose }: Props) {
  const t = reach.transects.find((x) => x.id === id);
  const history = useSegmentHistory(id);
  if (!t) return null;
  const outcome = revealed && pred?.y !== null && pred?.y !== undefined;
  return (
    <div className="rounded-lg border bg-card">
      <div className="flex items-start gap-2 p-3 pb-1">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold">{segmentLabel(id)}</h3>
            {pred && (
              <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                <span className="inline-block h-2 w-2 rounded-full" style={{ background: TIER_COLOR[pred.tier] }} />
                {TIER_LABEL[pred.tier]}
              </span>
            )}
          </div>
          <p className="mt-0.5 flex items-center gap-1 text-[11px] text-muted-foreground">
            <MapPin className="h-3 w-3" /> {BANK_LABEL[t.bank]} · {t.lat.toFixed(4)}°N {t.lon.toFixed(4)}°E · id {id}
            {t.near_bridge && " · near the bridge guide bunds"}
          </p>
        </div>
        {onClose && (
          <button onClick={onClose} aria-label="Close segment" className="rounded p-1 text-muted-foreground hover:bg-muted">
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
      {pred ? (
        <div className="grid grid-cols-3 gap-2 px-3 py-2 text-xs">
          <div>
            <div className="text-[11px] text-muted-foreground">28-day risk</div>
            <div className="text-base font-semibold">{pct(pred.p)}</div>
            <div className="mt-1 h-1.5 w-full rounded-full bg-river-light/60 dark:bg-river-dark/40">
              <div className="h-full rounded-full bg-river" style={{ width: `${Math.max(2, pred.p * 100)}%` }} />
            </div>
            <div className="mt-0.5 text-[10px] text-muted-foreground">rank {pred.rank} · persistence rank {pred.b0_rank}</div>
          </div>
          <div>
            <div className="text-[11px] text-muted-foreground">Retreat, last 4 / 12 wk</div>
            <div className="text-base font-semibold tabular">
              {signedMetres(pred.ret28)} / {signedMetres(pred.ret84)}
            </div>
            <div className="text-[10px] text-muted-foreground">confirmed on 2 passes</div>
          </div>
          <div>
            <div className="text-[11px] text-muted-foreground">Latest pass</div>
            <div className="text-base font-semibold tabular">{signedMetres(pred.last)}</div>
            <div className="text-[10px] text-muted-foreground">since previous pass (unconfirmed)</div>
          </div>
        </div>
      ) : (
        <p className="px-3 py-2 text-xs text-muted-foreground">No forecast for this segment on {fmtDate(forecastDate)}: its bank was not seen on this pass.</p>
      )}
      {pred?.reasons && pred.reasons.length > 0 && (
        <div className="px-3 pb-2">
          <div className="text-[11px] font-medium text-muted-foreground">Why the model ranks it here</div>
          <ul className="mt-1 space-y-0.5 text-xs">
            {pred.reasons.map((r) => (
              <li key={r} className="flex gap-1.5">
                <span className="mt-1.5 inline-block h-1 w-1 shrink-0 rounded-full bg-foreground/60" />
                {r}
              </li>
            ))}
          </ul>
        </div>
      )}
      {outcome && pred && (
        <div className={cn("mx-3 mb-2 rounded-md px-2.5 py-1.5 text-xs", pred.y ? "bg-[#0ca30c]/10" : "bg-muted")}>
          <span className="font-medium">What happened by {pred.target ? fmtDate(pred.target) : "the next pass"}:</span>{" "}
          {pred.retreat !== null ? `bank moved ${signedMetres(pred.retreat)} (confirmed)` : "not observed"}
          {pred.y ? " — lost land beyond the threshold." : " — below the threshold."}
          {pred.major ? <Badge className="ml-1" variant="notmet">major event ≥100 m</Badge> : null}
        </div>
      )}
      <div className="px-1 pb-2">
        <div className="px-2 text-[11px] text-muted-foreground">Bank position at every radar pass, 2015–2025 (up = land lost)</div>
        <BankSeriesChart data={history} forecastDate={forecastDate} targetDate={pred?.target} revealed={revealed} />
        {!revealed && <p className="px-2 text-[10px] text-muted-foreground">Passes after {fmtDate(forecastDate)} are hidden until you reveal the outcome.</p>}
      </div>
    </div>
  );
}
