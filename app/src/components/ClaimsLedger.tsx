import type { Claim } from "@/lib/api";
import { Badge } from "@/components/ui/badge";

const VARIANT: Record<Claim["status"], "measured" | "notmet" | "target" | "dropped"> = {
  Measured: "measured",
  "Not met": "notmet",
  Target: "target",
  "Not built": "target",
  Dropped: "dropped",
};

/** Every claim with its status. Only "Measured" rows may be quoted anywhere else. */
export function ClaimsLedger({ claims, compact = false }: { claims: Claim[]; compact?: boolean }) {
  const rows = compact ? claims.filter((c) => c.status !== "Dropped") : claims;
  return (
    <div className="overflow-x-auto rounded-lg border bg-card">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead className="border-b text-xs text-muted-foreground">
          <tr>
            <th className="px-3 py-2 font-medium">Claim</th>
            <th className="px-3 py-2 font-medium">Status</th>
            <th className="px-3 py-2 font-medium">Measured value / how</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.claim} className="border-b last:border-0 align-top">
              <td className="px-3 py-2 font-medium">{c.claim}</td>
              <td className="px-3 py-2">
                <Badge variant={VARIANT[c.status]}>{c.status}</Badge>
              </td>
              <td className="px-3 py-2 text-xs text-muted-foreground">
                {c.value && <div className="mb-0.5 text-foreground tabular">{c.value}</div>}
                {c.how}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
