"""The alert path: drafts need eligible segments, sends need a named official."""
import json

import pytest
from fastapi.testclient import TestClient

from src.alerts import send_alert
from src.api import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "predictions").mkdir(parents=True)
    rows = [
        dict(id="W-01000", p=0.62, rank=1, b0_rank=3, tier="warning_eligible", last=35, y=None),
        dict(id="E-02000", p=0.30, rank=2, b0_rank=1, tier="watch", last=0, y=None),
    ]
    (data / "predictions" / "2024-08-01.json").write_text(json.dumps(rows))
    (data / "reach.json").write_text(json.dumps(dict(transects=[])))
    monkeypatch.setattr(main, "DATA", data)
    monkeypatch.setattr(send_alert, "OUTBOX", tmp_path / "outbox.jsonl")
    monkeypatch.setattr(send_alert, "AUDIT", tmp_path / "audit.jsonl")
    monkeypatch.setenv("NADINET_ALERT_GATEWAY", "console")
    monkeypatch.setenv("NADINET_TEST_PHONE", "+8801700000000")
    return TestClient(main.app), tmp_path


def test_health(client):
    c, _ = client
    r = c.get("/api/health").json()
    assert r["status"] == "ok" and r["gateway"] == "console"


def test_draft_rejects_non_eligible_segments(client):
    c, _ = client
    r = c.post("/api/alerts/draft", json=dict(forecast_date="2024-08-01", segment_ids=["E-02000"], place="Char X"))
    assert r.status_code == 422


def test_warning_needs_named_official_then_is_logged_not_sent(client):
    c, tmp = client
    d = c.post("/api/alerts/draft", json=dict(forecast_date="2024-08-01", segment_ids=["W-01000"], place="Khasrajbari")).json()
    assert d["status"] == "awaiting_approval"
    assert "Khasrajbari" in d["sms"] and "নদীভাঙন" in d["sms"]
    bad = c.post(f"/api/alerts/{d['alert_id']}/approve", json=dict(official_name="", role="UNO"))
    assert bad.status_code == 422
    ok = c.post(f"/api/alerts/{d['alert_id']}/approve", json=dict(official_name="Test Official", role="UNO")).json()
    assert ok["status"] == "logged_not_sent"
    out = (tmp / "outbox.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(out) == 2 and all(json.loads(x)["status"] == "logged_not_sent" for x in out)
    assert "+8801700000000" not in (tmp / "outbox.jsonl").read_text()          # numbers are masked
    again = c.post(f"/api/alerts/{d['alert_id']}/approve", json=dict(official_name="Test Official", role="UNO"))
    assert again.status_code == 409


def test_dispatch_refuses_without_approval():
    alert = send_alert.WarningAlert(segment_ids=["W-01000"], forecast_date="2024-08-01", place="X", probability=0.6)
    with pytest.raises(PermissionError):
        send_alert.dispatch_warning(alert, None)
