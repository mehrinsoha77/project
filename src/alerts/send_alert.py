"""Alert tiers and the human-approved dispatch path (spec §Alerts, ethics and safety).

NadiNet never sends a public warning on its own:

* **Monitor** – any retreat detected on the latest pass → dashboard only.
* **Watch** – segment in the top 20 by calibrated risk → weekly brief to
  officials and NGO partners.
* **Warning** – high calibrated risk *and* retreat on the latest pass, *and*
  an official's approval → prerecorded Bangla voice call + SMS to registered
  (opt-in) households and local volunteers.

``dispatch_warning`` refuses to run without an ``Approval``. The default
gateway is ``console``: it writes to ``data/processed/alerts/outbox.jsonl``
and sends nothing. The ``twilio`` gateway sends real SMS / voice and is only
enabled when credentials are set; during the build it was used with a test
phone only (``NADINET_TEST_PHONE``).

Tier thresholds are set from the calibration year (``tier_thresholds``),
not chosen by hand.
"""
from __future__ import annotations

import base64
import dataclasses
import datetime as dt
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

from src import config

log = logging.getLogger(__name__)

OUTBOX = config.PROCESSED / "alerts" / "outbox.jsonl"
AUDIT = config.PROCESSED / "alerts" / "audit.jsonl"

SMS_BN = ("নদীভাঙন সতর্কবার্তা: আগামী কয়েক সপ্তাহে {place} এলাকার নদীতীরে ভাঙনের ঝুঁকি বেশি। "
          "মালামাল ও গবাদিপশু নিরাপদ স্থানে সরানোর প্রস্তুতি নিন। ইউনিয়ন পরিষদের নির্দেশনা মেনে চলুন।")
VOICE_BN = ("এটি নদীভাঙন সতর্কবার্তা। আগামী কয়েক সপ্তাহে {place} এলাকার নদীতীরে ভাঙনের ঝুঁকি বেশি। "
            "ঘরের মালামাল ও গবাদিপশু নিরাপদ স্থানে সরানোর প্রস্তুতি নিন এবং ইউনিয়ন পরিষদের নির্দেশনা মেনে চলুন।")
VOICE_EN = ("This is a riverbank erosion warning. Erosion risk is high along the bank at {place} in the coming "
            "weeks. Prepare to move belongings and livestock to a safe place, and follow the union parishad's guidance.")
DISCLAIMER = ("Advisory decision support. The absence of an alert does not mean a bank is safe. "
              "Public warnings are issued under an official's authority.")


@dataclass
class TierThresholds:
    watch_top_k: int = config.TOP_K
    warning_min_prob: float = 0.5
    warning_min_last_retreat_m: float = 20.0
    source: str = "default"


def tier_thresholds(val_scored: pd.DataFrame | None = None, label_threshold_m: float = 20.0) -> TierThresholds:
    """Warning probability floor = lowest calibrated probability whose 2022 hit rate is >= 50%.

    ``val_scored`` needs columns ``M1`` (calibrated probability) and ``y``.
    """
    if val_scored is None or val_scored.empty:
        return TierThresholds(warning_min_last_retreat_m=label_threshold_m)
    v = val_scored[["M1", "y"]].dropna().sort_values("M1", ascending=False)
    cum_hits = v["y"].cumsum().to_numpy()
    n = np.arange(1, len(v) + 1)
    rate = cum_hits / n
    ok = np.flatnonzero(rate >= 0.5)
    floor = float(v["M1"].iloc[ok[-1]]) if len(ok) else float(v["M1"].max())
    return TierThresholds(warning_min_prob=round(floor, 3), warning_min_last_retreat_m=label_threshold_m,
                          source="calibration year 2022: lowest probability with >= 50% precision above it")


def assign_tiers(pred: pd.DataFrame, th: TierThresholds) -> pd.Series:
    """pred needs rank, p (calibrated), raw_last_change_m."""
    tier = pd.Series("none", index=pred.index)
    tier[pred["raw_last_change_m"].fillna(0) > 0] = "monitor"
    watch = pred["rank"] <= th.watch_top_k
    tier[watch] = "watch"
    warn = watch & (pred["p"] >= th.warning_min_prob) & \
        (pred["raw_last_change_m"].fillna(0) >= th.warning_min_last_retreat_m)
    tier[warn] = "warning_eligible"      # becomes a Warning only after approval
    return tier


@dataclass
class Approval:
    official_name: str
    role: str
    approved_at: str = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    note: str = ""

    def validate(self) -> None:
        if len(self.official_name.strip()) < 3 or len(self.role.strip()) < 3:
            raise PermissionError("A named official and role are required to approve a Warning.")


@dataclass
class WarningAlert:
    segment_ids: list[str]
    forecast_date: str
    place: str
    probability: float
    alert_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def sms_text(self) -> str:
        return SMS_BN.format(place=self.place)

    def voice_script(self) -> str:
        return VOICE_BN.format(place=self.place)


class ConsoleGateway:
    """Sends nothing. Writes every message to the outbox for review."""

    name = "console"

    def send_sms(self, to: str, text: str) -> dict:
        return self._log("sms", to, text)

    def send_voice(self, to: str, audio_url: str, fallback_text: str) -> dict:
        return self._log("voice", to, f"[clip {audio_url}] {fallback_text}")

    def _log(self, kind: str, to: str, body: str) -> dict:
        rec = dict(kind=kind, to=_mask(to), body=body, gateway=self.name, status="logged_not_sent",
                   at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
        _append(OUTBOX, rec)
        return rec


class TwilioGateway:
    """Real SMS / voice via Twilio's REST API. Needs TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM."""

    name = "twilio"

    def __init__(self) -> None:
        self.sid = os.environ["TWILIO_ACCOUNT_SID"]
        self.token = os.environ["TWILIO_AUTH_TOKEN"]
        self.sender = os.environ["TWILIO_FROM"]
        self.base = f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}"
        auth = base64.b64encode(f"{self.sid}:{self.token}".encode()).decode()
        self.headers = {"Authorization": f"Basic {auth}"}

    def send_sms(self, to: str, text: str) -> dict:
        r = httpx.post(f"{self.base}/Messages.json", headers=self.headers,
                       data={"To": to, "From": self.sender, "Body": text}, timeout=30)
        rec = dict(kind="sms", to=_mask(to), gateway=self.name, status=r.status_code, sid=r.json().get("sid"))
        _append(OUTBOX, rec)
        return rec

    def send_voice(self, to: str, audio_url: str, fallback_text: str) -> dict:
        twiml = f"<Response><Play>{audio_url}</Play></Response>"
        r = httpx.post(f"{self.base}/Calls.json", headers=self.headers,
                       data={"To": to, "From": self.sender, "Twiml": twiml}, timeout=30)
        rec = dict(kind="voice", to=_mask(to), gateway=self.name, status=r.status_code, sid=r.json().get("sid"))
        _append(OUTBOX, rec)
        return rec


def get_gateway(name: str | None = None):
    name = name or os.environ.get("NADINET_ALERT_GATEWAY", "console")
    if name == "twilio":
        return TwilioGateway()
    return ConsoleGateway()


def recipients() -> list[str]:
    """Opt-in recipients. During the build: the test phone only."""
    reg = config.RAW / "registry" / "optin.csv"
    if reg.exists():
        df = pd.read_csv(reg, dtype=str)
        return df.loc[df["opt_in"].str.lower() == "yes", "phone"].tolist()
    test = os.environ.get("NADINET_TEST_PHONE")
    return [test] if test else ["+880-TEST-PHONE"]


def dispatch_warning(alert: WarningAlert, approval: Approval | None, gateway=None,
                     audio_url: str | None = None) -> dict:
    """Send a Warning. Refuses without a valid human approval."""
    if approval is None:
        raise PermissionError("Warnings are never sent without an official's approval.")
    approval.validate()
    gateway = gateway or get_gateway()
    audio_url = audio_url or os.environ.get("NADINET_VOICE_CLIP_URL", "/voices/warning_bangla.mp3")
    sent = []
    for to in recipients():
        sent.append(gateway.send_sms(to, alert.sms_text()))
        sent.append(gateway.send_voice(to, audio_url, alert.voice_script()))
    rec = dict(alert=dataclasses.asdict(alert), approval=dataclasses.asdict(approval),
               gateway=gateway.name, messages=sent, disclaimer=DISCLAIMER)
    _append(AUDIT, rec)
    return rec


def _mask(phone: str) -> str:
    return phone[:4] + "…" + phone[-2:] if len(phone) > 6 else "…"


def _append(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
