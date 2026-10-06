"""Gateways and the alternative Earth Engine path, without real credentials.

The Twilio gateway is exercised against a mocked HTTP layer: we check the
exact requests (endpoint, auth, sender, body, TwiML with the recorded clip).
The Earth Engine scripts must import and show help without earthengine-api.
"""
import base64
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.alerts import send_alert

ROOT = Path(__file__).resolve().parents[1]


class _Resp:
    def __init__(self, sid):
        self.status_code = 201
        self._sid = sid

    def json(self):
        return {"sid": self._sid}


def test_twilio_gateway_builds_correct_requests(monkeypatch, tmp_path):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC123")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")
    monkeypatch.setenv("TWILIO_FROM", "+15550001111")
    monkeypatch.setattr(send_alert, "OUTBOX", tmp_path / "outbox.jsonl")
    calls = []

    def fake_post(url, headers=None, data=None, timeout=None):
        calls.append(dict(url=url, headers=headers, data=data))
        return _Resp(f"SM{len(calls)}")

    monkeypatch.setattr(send_alert.httpx, "post", fake_post)
    gw = send_alert.get_gateway("twilio")
    assert gw.name == "twilio"
    alert = send_alert.WarningAlert(segment_ids=["W-01000"], forecast_date="2024-08-01", place="Khasrajbari", probability=0.6)
    gw.send_sms("+8801700000000", alert.sms_text())
    gw.send_voice("+8801700000000", "https://example.org/warning_bangla.mp3", alert.voice_script())

    sms, call = calls
    assert sms["url"] == "https://api.twilio.com/2010-04-01/Accounts/AC123/Messages.json"
    assert call["url"] == "https://api.twilio.com/2010-04-01/Accounts/AC123/Calls.json"
    assert sms["headers"]["Authorization"] == "Basic " + base64.b64encode(b"AC123:tok").decode()
    assert sms["data"]["From"] == "+15550001111" and sms["data"]["To"] == "+8801700000000"
    assert "Khasrajbari" in sms["data"]["Body"] and "নদীভাঙন" in sms["data"]["Body"]
    assert call["data"]["Twiml"] == "<Response><Play>https://example.org/warning_bangla.mp3</Play></Response>"
    out = [json.loads(x) for x in (tmp_path / "outbox.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [o["kind"] for o in out] == ["sms", "voice"] and all(o["status"] == 201 for o in out)
    assert all("0000000" not in o["to"] for o in out)            # numbers masked in the log


def test_twilio_dispatch_still_needs_approval(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC123")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")
    monkeypatch.setenv("TWILIO_FROM", "+15550001111")
    monkeypatch.setattr(send_alert.httpx, "post", lambda *a, **k: pytest.fail("must not send"))
    alert = send_alert.WarningAlert(segment_ids=["W-01000"], forecast_date="2024-08-01", place="X", probability=0.6)
    with pytest.raises(PermissionError):
        send_alert.dispatch_warning(alert, send_alert.Approval(official_name="", role="UNO"),
                                    gateway=send_alert.get_gateway("twilio"))


@pytest.mark.parametrize("script", ["export_masks.py", "export_sentinel2.py", "verify_exports.py"])
def test_gee_scripts_run_help_without_earthengine(script):
    r = subprocess.run([sys.executable, str(ROOT / "gee" / script), "--help"], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    assert "usage" in r.stdout.lower()


def test_gee_otsu_matches_reference_on_a_histogram():
    """The Earth Engine Otsu helper, run against a tiny fake 'ee' that evaluates eagerly."""
    import numpy as np
    from skimage.filters import threshold_otsu

    spec = importlib.util.spec_from_file_location("gee_export", ROOT / "gee" / "export_masks.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rng = np.random.default_rng(0)
    # overlapping modes (as in real scenes) so the Otsu maximum is unique, not a plateau of empty bins
    v = np.concatenate([rng.normal(-20, 3.0, 4000), rng.normal(-9, 3.0, 9000)])
    counts, edges = np.histogram(v, bins=200)
    means = (edges[:-1] + edges[1:]) / 2
    t = mod._otsu(_FakeEE, _FakeDict({"histogram": counts.astype(float), "bucketMeans": means}))
    assert abs(float(t) - threshold_otsu(hist=(counts, means))) < 0.2


# ----- a minimal eager stand-in for the parts of the ee API _otsu uses -----------------------
import numpy as _np  # noqa: E402


class _FakeDict(dict):
    pass


class _Arr:
    def __init__(self, a):
        self.a = _np.asarray(a, dtype=float)

    def length(self):
        return _Arr([len(self.a)])

    def get(self, idx):
        return _Num(self.a[idx[0]])

    def reduce(self, _r, _axes):
        return _Arr([self.a.sum()])

    def multiply(self, o):
        return _Arr(self.a * (o.a if isinstance(o, _Arr) else o))

    def slice(self, _axis, start, end):
        return _Arr(self.a[int(start):int(end)])

    def sort(self, keys):
        return _Arr(self.a[_np.argsort(keys.a, kind="stable")])


class _Num(float):
    def divide(self, o):
        return _Num(float(self) / float(o))

    def subtract(self, o):
        return _Num(float(self) - float(o))

    def add(self, o):
        return _Num(float(self) + float(o))

    def multiply(self, o):
        return _Num(float(self) * float(o))

    def pow(self, p):
        return _Num(float(self) ** p)


class _List(list):
    def map(self, f):
        return _List(f(x) for x in self)


class _FakeEE:
    class Reducer:
        @staticmethod
        def sum():
            return None

    @staticmethod
    def Array(a):
        return a if isinstance(a, _Arr) else _Arr(a)

    class List:
        @staticmethod
        def sequence(a, b):
            return _List(range(int(a), int(b)))
