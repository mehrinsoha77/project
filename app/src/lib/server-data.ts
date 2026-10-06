import "server-only";
import fs from "node:fs";
import path from "node:path";
import type { Metrics } from "./api";
import type { Wow } from "@/components/Hero";

const DATA = path.join(process.cwd(), "public", "data");

function read<T>(rel: string): T | null {
  try {
    return JSON.parse(fs.readFileSync(path.join(DATA, rel), "utf8")) as T;
  } catch {
    return null;
  }
}

/** Read at build time so the landing and method pages render real, measured numbers as static HTML. */
export const serverData = {
  metrics: () => read<Metrics>("metrics.json") ?? {},
  wow: () => read<NonNullable<Wow>>("wow/wow.json"),
};
