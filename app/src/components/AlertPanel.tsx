"use client";

import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, FileDown, Phone, ShieldAlert, ShieldCheck, Volume2 } from "lucide-react";
import { alertsApi, DISCLAIMER, type AlertDraft, type Prediction } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn, pct, segmentLabel, signedMetres } from "@/lib/utils";

type Props = { date: string; preds: Prediction[]; onFocus?: (id: string) => void };

/**
 * Human-in-the-loop alert path. The software proposes; an official decides.
 * Nothing reaches residents without a named official's approval, and in this
 * build the only recipient is a test phone (or the console outbox).
 */
export function AlertPanel({ date, preds, onFocus }: Props) {
  const eligible = useMemo(() => preds.filter((p) => p.tier === "warning_eligible").sort((a, b) => a.rank - b.rank), [preds]);
  const [selected, setSelected] = useState<string[]>([]);
  const [place, setPlace] = useState("");
  const [draft, setDraft] = useState<AlertDraft | null>(null);
  const [official, setOfficial] = useState("");
  const [role, setRole] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [backend, setBackend] = useState<string | null>(null);
  const [clip, setClip] = useState<boolean | null>(null);

  useEffect(() => {
    setSelected([]);
    setDraft(null);
    setError(null);
  }, [date]);
  useEffect(() => {
    alertsApi.health().then((h) => setBackend(h ? h.gateway : null));
    fetch("/voices/warning_bangla.mp3", { method: "HEAD" })
      .then((r) => setClip(r.ok && (r.headers.get("content-type") ?? "").includes("audio")))
      .catch(() => setClip(false));
  }, []);

  const doDraft = async () => {
    setBusy(true);
    setError(null);
    try {
      setDraft(await alertsApi.draft(date, selected, place.trim(), preds));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const doApprove = async () => {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      setDraft(await alertsApi.approve(draft, official.trim(), role.trim()));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const briefHref = backend !== null ? `/api/proxy/brief/${date}` : `/data/briefs/${date}.pdf`;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
        <Badge variant={backend ? "measured" : "target"}>{backend ? `Backend: ${backend} gateway` : "Offline demo mode"}</Badge>
        <span>{backend === "console" ? "Messages are written to the outbox, not sent." : backend ? "Sends to the registered test phone." : "No backend: approvals are logged in this browser only. Nothing is sent."}</span>
      </div>

      <a href={briefHref} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:underline">
        <FileDown className="h-3.5 w-3.5" /> Weekly risk brief for {date} (PDF, for officials and partners)
      </a>

      <div>
        <div className="mb-1 flex items-center gap-1.5 text-xs font-medium">
          <ShieldAlert className="h-3.5 w-3.5 text-status-critical" /> Warning-eligible segments ({eligible.length})
        </div>
        {eligible.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            None on this pass. Warning needs top-20 risk, probability above the floor set on the calibration year, and retreat on the latest pass.
          </p>
        ) : (
          <ul className="max-h-40 space-y-1 overflow-y-auto pr-1">
            {eligible.map((p) => (
              <li key={p.id}>
                <label className="flex cursor-pointer items-center gap-2 rounded-md border px-2 py-1 text-xs hover:bg-muted">
                  <input
                    type="checkbox"
                    checked={selected.includes(p.id)}
                    onChange={(e) => setSelected((s) => (e.target.checked ? [...s, p.id] : s.filter((x) => x !== p.id)))}
                  />
                  <span className="font-medium">#{p.rank}</span>
                  <button type="button" className="truncate text-left hover:underline" onClick={() => onFocus?.(p.id)}>
                    {segmentLabel(p.id)}
                  </button>
                  <span className="ml-auto tabular text-muted-foreground">
                    {pct(p.p)} · {signedMetres(p.last)}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}
      </div>

      {eligible.length > 0 && !draft && (
        <div className="space-y-2">
          <input
            className="w-full rounded-md border bg-card px-2.5 py-1.5 text-sm"
            placeholder="Village or union name for the message"
            value={place}
            onChange={(e) => setPlace(e.target.value)}
          />
          <Button size="sm" disabled={!selected.length || place.trim().length < 2 || busy} onClick={doDraft}>
            Draft Warning for official review
          </Button>
        </div>
      )}

      {draft && (
        <div className="space-y-2 rounded-md border p-2.5">
          <div className="text-xs font-medium">Draft {draft.alert_id}</div>
          <div className="rounded bg-muted p-2">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">SMS (Bangla)</div>
            <p className="bn text-sm" lang="bn">
              {draft.sms}
            </p>
          </div>
          <div className="rounded bg-muted p-2">
            <div className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-muted-foreground">
              <Volume2 className="h-3 w-3" /> Voice call (prerecorded clip)
            </div>
            <p className="bn text-sm" lang="bn">
              {draft.voice_bn}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">{draft.voice_en}</p>
            {clip ? (
              <audio className="mt-1 h-8 w-full" controls src="/voices/warning_bangla.mp3" />
            ) : (
              <p className="mt-1 text-[11px] text-muted-foreground">
                Clip not recorded yet. It must be recorded by a native speaker from the target reach; NadiNet does not synthesise speech.
              </p>
            )}
          </div>

          {draft.status === "awaiting_approval" ? (
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <input className="rounded-md border bg-card px-2 py-1.5 text-sm" placeholder="Official's name" value={official} onChange={(e) => setOfficial(e.target.value)} />
                <input className="rounded-md border bg-card px-2 py-1.5 text-sm" placeholder="Role (e.g. UNO, PIO)" value={role} onChange={(e) => setRole(e.target.value)} />
              </div>
              <p className="text-[11px] text-muted-foreground">{DISCLAIMER}</p>
              <div className="flex gap-2">
                <Button size="sm" variant="danger" disabled={official.trim().length < 3 || role.trim().length < 3 || busy} onClick={doApprove}>
                  <ShieldCheck className="h-4 w-4" /> Approve &amp; send Warning
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setDraft(null)}>
                  Discard
                </Button>
              </div>
            </div>
          ) : (
            <div className={cn("flex items-start gap-2 rounded-md p-2 text-xs", "bg-[#0ca30c]/10")}>
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-status-good" />
              <div>
                <div className="font-medium">
                  {draft.status === "sent" && "Approved and sent through the gateway."}
                  {draft.status === "logged_not_sent" && "Approved. Console gateway: written to the outbox, not sent."}
                  {draft.status === "offline_logged" && "Approved (offline demo). Logged in this browser; nothing was sent."}
                </div>
                {draft.dispatch?.messages?.map((m, i) => (
                  <div key={i} className="flex items-center gap-1 text-muted-foreground">
                    <Phone className="h-3 w-3" /> {m.kind} → {m.to} · {String(m.status)}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
      {error && <p className="text-xs text-status-critical">{error}</p>}
    </div>
  );
}
