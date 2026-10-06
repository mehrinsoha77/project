"use client";
import { useEffect, useRef, useState } from "react";
import { Pause, Play, SkipBack, SkipForward } from "lucide-react";
import { Slider } from "@/components/ui/slider";
import { Button } from "@/components/ui/button";
import { fmtDate } from "@/lib/utils";

type Props = {
  dates: string[];
  value: number;
  onChange: (i: number) => void;
  marks?: { index: number; color: string; title: string }[];
  playMs?: number;
};

/** Pass-by-pass time slider with play/pause. Every stop is a real radar pass. */
export function Timeline({ dates, value, onChange, marks = [], playMs = 900 }: Props) {
  const [playing, setPlaying] = useState(false);
  const ref = useRef(value);
  ref.current = value;
  useEffect(() => {
    if (!playing) return;
    const t = setInterval(() => {
      if (ref.current >= dates.length - 1) {
        setPlaying(false);
        return;
      }
      onChange(ref.current + 1);
    }, playMs);
    return () => clearInterval(t);
  }, [playing, dates.length, onChange, playMs]);
  if (!dates.length) return null;
  const first = dates[0];
  const last = dates[dates.length - 1];
  return (
    <div className="flex items-center gap-2">
      <Button variant="ghost" size="icon" aria-label="Previous pass" onClick={() => onChange(Math.max(0, value - 1))}>
        <SkipBack className="h-4 w-4" />
      </Button>
      <Button variant="outline" size="icon" aria-label={playing ? "Pause" : "Play passes"} onClick={() => setPlaying((p) => !p)}>
        {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
      </Button>
      <Button variant="ghost" size="icon" aria-label="Next pass" onClick={() => onChange(Math.min(dates.length - 1, value + 1))}>
        <SkipForward className="h-4 w-4" />
      </Button>
      <div className="relative min-w-0 flex-1">
        <Slider min={0} max={dates.length - 1} step={1} value={[value]} onValueChange={(v) => onChange(v[0])} />
        <div className="pointer-events-none absolute inset-x-0 top-0 h-full">
          {marks.map((m) => (
            <span
              key={m.index}
              title={m.title}
              className="absolute top-[3px] h-1.5 w-0.5 rounded"
              style={{ left: `${(m.index / Math.max(1, dates.length - 1)) * 100}%`, background: m.color }}
            />
          ))}
        </div>
        <div className="mt-0.5 flex justify-between text-[10px] text-muted-foreground tabular">
          <span>{fmtDate(first, { month: "short", year: "numeric" })}</span>
          <span className="font-medium text-foreground">
            Pass {value + 1} of {dates.length} · {fmtDate(dates[value])}
          </span>
          <span>{fmtDate(last, { month: "short", year: "numeric" })}</span>
        </div>
      </div>
    </div>
  );
}
