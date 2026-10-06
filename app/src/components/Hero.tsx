"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { useState } from "react";
import { ArrowRight, CloudRain, Satellite } from "lucide-react";
import { Button } from "@/components/ui/button";
import { fmtDate } from "@/lib/utils";

export type Wow = {
  s2: { url: string; date: string; cloud: number };
  s1: { url: string; date: string };
  bounds: [number, number, number, number];
} | null;

type Stat = { label: string; value: string; sub: string };

/** Landing hero: the monsoon blind spot, and what radar sees on the same days. */
export function Hero({ wow, stats }: { wow: Wow; stats: Stat[] }) {
  const [split, setSplit] = useState(50);
  return (
    <section className="relative overflow-hidden border-b">
      <div className="container grid gap-10 py-12 lg:grid-cols-[1.05fr_1fr] lg:py-16">
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
          <p className="mb-3 inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-xs text-muted-foreground">
            <Satellite className="h-3.5 w-3.5 text-river" /> Sentinel-1 radar · Jamuna, Bangladesh · 2015–2025
          </p>
          <h1 className="text-3xl font-semibold leading-tight tracking-tight sm:text-5xl">
            Watching the Jamuna&apos;s banks <span className="text-river">through monsoon cloud</span>.
          </h1>
          <p className="mt-4 max-w-xl text-base text-muted-foreground sm:text-lg">
            NadiNet maps the river&apos;s banks after every free Sentinel-1 radar pass and tells local officials which
            200&nbsp;m stretches are most likely to lose land in the next 28 days — tested against what really happened.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Button asChild size="lg">
              <Link href="/demo">
                Watch the replay <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline">
              <Link href="/dashboard">Open the dashboard</Link>
            </Button>
          </div>
          <div className="mt-8 grid grid-cols-1 gap-2 sm:grid-cols-3">
            {stats.map((s) => (
              <div key={s.label} className="rounded-lg border bg-card p-3">
                <div className="text-[11px] text-muted-foreground">{s.label}</div>
                <div className="mt-0.5 text-xl font-semibold">{s.value}</div>
                <div className="mt-0.5 text-[11px] leading-snug text-muted-foreground">{s.sub}</div>
              </div>
            ))}
          </div>
        </motion.div>

        <motion.div initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.6, delay: 0.1 }}>
          {wow ? (
            <figure className="overflow-hidden rounded-xl border bg-card">
              <div className="relative aspect-[4/5] w-full select-none bg-[#0f1113]">
                <img src={wow.s1.url} alt={`Sentinel-1 radar, ${wow.s1.date}`} className="absolute inset-0 h-full w-full object-cover" />
                <div className="absolute inset-0 overflow-hidden" style={{ clipPath: `inset(0 ${100 - split}% 0 0)` }}>
                  <img src={wow.s2.url} alt={`Sentinel-2 optical, ${wow.s2.date}`} className="absolute inset-0 h-full w-full object-cover" />
                </div>
                <div className="pointer-events-none absolute inset-y-0 w-0.5 bg-white/90 shadow" style={{ left: `${split}%` }} />
                <span className="absolute left-2 top-2 inline-flex items-center gap-1 rounded bg-black/60 px-2 py-0.5 text-[11px] text-white">
                  <CloudRain className="h-3 w-3" /> Optical, {fmtDate(wow.s2.date)} · {Math.round(wow.s2.cloud)}% cloud
                </span>
                <span className="absolute right-2 top-2 inline-flex items-center gap-1 rounded bg-black/60 px-2 py-0.5 text-[11px] text-white">
                  <Satellite className="h-3 w-3" /> Radar, {fmtDate(wow.s1.date)}
                </span>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={split}
                  onChange={(e) => setSplit(Number(e.target.value))}
                  aria-label="Drag to compare optical and radar"
                  className="absolute inset-x-0 bottom-3 mx-auto w-2/3 accent-white"
                />
              </div>
              <figcaption className="p-3 text-xs text-muted-foreground">
                Same reach, same monsoon week. Left: Sentinel-2 true colour, mostly cloud. Right: Sentinel-1 VV backscatter — water is dark, land bright, and the
                bank line is visible through the cloud. Drag the slider to compare.
              </figcaption>
            </figure>
          ) : (
            <div className="flex aspect-[4/5] items-center justify-center rounded-xl border bg-card text-sm text-muted-foreground">
              Run <code className="mx-1">python -m src.api.export --images</code> to render the comparison.
            </div>
          )}
        </motion.div>
      </div>
    </section>
  );
}
