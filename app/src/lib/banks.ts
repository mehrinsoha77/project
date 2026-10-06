import type { Banks, Reach, Transect } from "./api";
import { bankPoint } from "./utils";

export type LatLon = [number, number];

export type BankGeometry = {
  /** polylines per bank, broken where a transect has no valid position */
  lines: LatLon[][];
  /** bank point per transect id (only where valid) */
  points: Map<string, LatLon>;
  /** short polyline centred on each transect's bank point (for highlighting one 200 m segment) */
  segments: Map<string, LatLon[]>;
};

export function transectsByBank(reach: Reach): Record<"W" | "E", Transect[]> {
  const out: Record<"W" | "E", Transect[]> = { W: [], E: [] };
  for (const t of reach.transects) out[t.bank].push(t);
  out.W.sort((a, b) => a.chainage_m - b.chainage_m);
  out.E.sort((a, b) => a.chainage_m - b.chainage_m);
  return out;
}

export function positionsFor(banks: Banks | undefined, passId: string): Map<string, number> {
  const m = new Map<string, number>();
  if (!banks) return m;
  const j = banks.passes.indexOf(passId);
  if (j < 0) return m;
  const col = banks.pos[j];
  banks.transects.forEach((id, i) => {
    const v = col[i];
    if (v !== null && v !== undefined) m.set(id, v);
  });
  return m;
}

const mid = (a: LatLon, b: LatLon): LatLon => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];

export function bankGeometry(reach: Reach, pos: Map<string, number>): BankGeometry {
  const byBank = transectsByBank(reach);
  const lines: LatLon[][] = [];
  const points = new Map<string, LatLon>();
  const segments = new Map<string, LatLon[]>();
  for (const bank of ["W", "E"] as const) {
    const ts = byBank[bank];
    let cur: LatLon[] = [];
    const pts: (LatLon | null)[] = ts.map((t) => {
      const v = pos.get(t.id);
      return v === undefined ? null : bankPoint(t, v, reach);
    });
    pts.forEach((p, i) => {
      if (p) {
        cur.push(p);
        points.set(ts[i].id, p);
      } else if (cur.length) {
        lines.push(cur);
        cur = [];
      }
    });
    if (cur.length) lines.push(cur);
    pts.forEach((p, i) => {
      if (!p) return;
      const prev = pts[i - 1];
      const next = pts[i + 1];
      const seg: LatLon[] = [];
      seg.push(prev ? mid(prev, p) : p);
      seg.push(p);
      seg.push(next ? mid(p, next) : p);
      segments.set(ts[i].id, seg);
    });
  }
  return { lines, points, segments };
}
