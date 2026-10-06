"""NadiNet API (FastAPI).

Read endpoints serve the precomputed results (``python -m src.api.export``);
write endpoints implement the human-in-the-loop alert path.

Run::

    uvicorn src.api.main:app --reload --port 8000
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from src import config
from src.alerts.brief import build_brief
from src.alerts.send_alert import (
    AUDIT,
    DISCLAIMER,
    OUTBOX,
    VOICE_BN,
    VOICE_EN,
    Approval,
    WarningAlert,
    dispatch_warning,
    get_gateway,
)

DATA = Path(os.environ.get("NADINET_STATIC_DATA", config.ROOT / "app" / "public" / "data"))

app = FastAPI(title="NadiNet API", version="3.0.0",
              description="Sentinel-1 riverbank monitoring and 28-day erosion risk for the Jamuna. "
                          "Advisory decision support; public warnings need an official's approval.")
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("NADINET_CORS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])


def _json(rel: str):
    p = DATA / rel
    if not p.exists():
        raise HTTPException(404, f"{rel} not found — run `python -m src.api.export` first")
    return json.loads(p.read_text())


@lru_cache(maxsize=1)
def _predictions() -> pd.DataFrame:
    from src.api.export import load_predictions
    return load_predictions()


# --------------------------------------------------------------------- read

@app.get("/api/health")
def health() -> dict:
    return dict(status="ok", data_dir=str(DATA), has_data=(DATA / "reach.json").exists(),
                gateway=get_gateway().name, time=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))


@app.get("/api/reach")
def reach() -> dict:
    return _json("reach.json")


@app.get("/api/passes")
def passes() -> list:
    return _json("passes.json")


@app.get("/api/banks/{year}")
def banks(year: int) -> dict:
    return _json(f"banks/{year}.json")


@app.get("/api/predictions")
def predictions_index() -> list:
    return _json("predictions/index.json")


@app.get("/api/predictions/{date}")
def predictions(date: str, top: int | None = Query(None, ge=1, le=1000)) -> list:
    rows = _json(f"predictions/{date}.json")
    return rows[:top] if top else rows


@app.get("/api/segments/{segment_id}")
def segment(segment_id: str, until: str | None = None) -> dict:
    """Bank-position history of one segment (optionally only up to ``until``: no peeking)."""
    reach_ = _json("reach.json")
    meta = next((t for t in reach_["transects"] if t["id"] == segment_id), None)
    if meta is None:
        raise HTTPException(404, "unknown segment")
    series = []
    for p in sorted(DATA.glob("banks/*.json")):
        b = json.loads(p.read_text())
        i = b["transects"].index(segment_id) if segment_id in b["transects"] else None
        if i is None:
            continue
        for pid, col in zip(b["passes"], b["pos"]):
            d = f"{pid[:4]}-{pid[4:6]}-{pid[6:8]}"
            if until and d > until:
                continue
            series.append(dict(date=d, pos=col[i]))
    return dict(segment=meta, series=series)


@app.get("/api/metrics")
def metrics() -> dict:
    return _json("metrics.json")


@app.get("/api/brief/{date}")
def brief(date: str):
    buf = io.BytesIO()
    try:
        build_brief(_predictions(), date, buf)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": f'inline; filename="nadinet_brief_{date}.pdf"'})


# -------------------------------------------------------------------- alerts

class DraftIn(BaseModel):
    forecast_date: str
    segment_ids: list[str] = Field(min_length=1, max_length=20)
    place: str = Field(min_length=2, max_length=80, description="Village / union name for the message")


class ApproveIn(BaseModel):
    official_name: str = Field(min_length=3, max_length=80)
    role: str = Field(min_length=3, max_length=80)
    note: str = ""


_DRAFTS: dict[str, dict] = {}


@app.post("/api/alerts/draft")
def draft(body: DraftIn) -> dict:
    rows = {r["id"]: r for r in _json(f"predictions/{body.forecast_date}.json")}
    missing = [s for s in body.segment_ids if s not in rows]
    if missing:
        raise HTTPException(422, f"unknown segments: {missing}")
    eligible = [s for s in body.segment_ids if rows[s]["tier"] == "warning_eligible"]
    if not eligible:
        raise HTTPException(422, "None of these segments meets the Warning criteria "
                                 "(top-20 risk, probability above the calibrated floor, and retreat on the latest pass).")
    p = max(rows[s]["p"] for s in eligible)
    alert = WarningAlert(segment_ids=eligible, forecast_date=body.forecast_date, place=body.place, probability=p)
    rec = dict(alert_id=alert.alert_id, status="awaiting_approval", alert=alert.__dict__,
               sms=alert.sms_text(), voice_bn=alert.voice_script(), voice_en=VOICE_EN.format(place=body.place),
               disclaimer=DISCLAIMER, created=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    _DRAFTS[alert.alert_id] = rec
    return rec


@app.post("/api/alerts/{alert_id}/approve")
def approve(alert_id: str, body: ApproveIn) -> dict:
    rec = _DRAFTS.get(alert_id)
    if rec is None:
        raise HTTPException(404, "unknown or expired draft")
    if rec["status"] != "awaiting_approval":
        raise HTTPException(409, f"draft is {rec['status']}")
    alert = WarningAlert(**rec["alert"])
    try:
        sent = dispatch_warning(alert, Approval(body.official_name, body.role, note=body.note))
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    rec.update(status="sent" if sent["gateway"] != "console" else "logged_not_sent", dispatch=sent)
    return rec


@app.post("/api/alerts/{alert_id}/reject")
def reject(alert_id: str, body: ApproveIn) -> dict:
    rec = _DRAFTS.get(alert_id)
    if rec is None:
        raise HTTPException(404, "unknown or expired draft")
    rec.update(status="rejected", rejected_by=body.official_name, note=body.note)
    return rec


@app.get("/api/alerts")
def alerts_log(kind: Literal["audit", "outbox"] = "audit", limit: int = 50) -> list:
    path = AUDIT if kind == "audit" else OUTBOX
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()[-limit:]
    return [json.loads(x) for x in reversed(lines)]


@app.get("/api/voice/template")
def voice_template() -> dict:
    clip = config.ROOT / "app" / "public" / "voices" / "warning_bangla.mp3"
    return dict(bn=VOICE_BN, en=VOICE_EN, clip_available=clip.exists(),
                note="The clip must be recorded by a native speaker from the target reach; it is not synthesised.")


@app.get("/voices/warning_bangla.mp3")
def voice_clip():
    clip = config.ROOT / "app" / "public" / "voices" / "warning_bangla.mp3"
    if not clip.exists():
        raise HTTPException(404, "voice clip not recorded yet")
    return FileResponse(clip, media_type="audio/mpeg")
