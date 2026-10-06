import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { Reach, Transect } from "./api";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const pct = (v: number | null | undefined, digits = 0) =>
  v === null || v === undefined || Number.isNaN(v) ? "–" : `${(v * 100).toFixed(digits)}%`;

export const signedPct = (v: number | null | undefined, digits = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? "–" : `${v >= 0 ? "+" : "−"}${Math.abs(v * 100).toFixed(digits)} pts`;

export const metres = (v: number | null | undefined) =>
  v === null || v === undefined || Number.isNaN(v) ? "–" : `${Math.round(v).toLocaleString("en-US")} m`;

export const signedMetres = (v: number | null | undefined) =>
  v === null || v === undefined || Number.isNaN(v) ? "–" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(Math.round(v))} m`;

export function fmtDate(d: string, opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "short", year: "numeric" }) {
  const dt = new Date(`${d}T00:00:00Z`);
  return dt.toLocaleDateString("en-GB", { ...opts, timeZone: "UTC" });
}

export function passDate(passId: string) {
  return `${passId.slice(0, 4)}-${passId.slice(4, 6)}-${passId.slice(6, 8)}`;
}

export function addDays(d: string, n: number) {
  const dt = new Date(`${d}T00:00:00Z`);
  dt.setUTCDate(dt.getUTCDate() + n);
  return dt.toISOString().slice(0, 10);
}

/** Bank point on a transect: linear interpolation between its riverward start and landward end. */
export function bankPoint(t: Transect, pos: number, reach: Reach): [number, number] {
  const [s0, s1] = reach.s_range;
  const f = (pos - s0) / (s1 - s0);
  const lon = t.start[0] + f * (t.end[0] - t.start[0]);
  const lat = t.start[1] + f * (t.end[1] - t.start[1]);
  return [lat, lon];
}

export const BANK_LABEL: Record<string, string> = {
  W: "West bank · Sirajganj side",
  E: "East bank · Tangail side",
};

export function segmentLabel(id: string) {
  const [bank, ch] = id.split("-");
  return `${bank === "W" ? "West" : "East"} bank, km ${(Number(ch) / 1000).toFixed(1)}`;
}
