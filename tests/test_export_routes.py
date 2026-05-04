"""Admin export endpoints require the capability secret."""

from __future__ import annotations

import json
import re


def test_export_json_requires_admin_secret(client):
    r = client.post(
        "/",
        data={
            "name": "Export Test",
            "timezone": "UTC",
            "player_names": "A",
            "horizon_weeks": "2",
        },
    )
    assert r.status_code == 200
    m = re.search(r"/c/([0-9a-f]+)/admin/([\w\-]+)", r.text)
    assert m
    public_id, secret = m.groups()
    ok = client.get(f"/c/{public_id}/admin/{secret}/export.json")
    assert ok.status_code == 200
    data = json.loads(ok.text)
    assert data["campaign"]["public_id"] == public_id
    assert "availability" in data
    assert "occurrence_opt_outs" in data
    bad = client.get(f"/c/{public_id}/admin/wrong-secret/export.json")
    assert bad.status_code == 404


def test_consensus_ics_requires_admin_secret(client):
    r = client.post(
        "/",
        data={
            "name": "ICS Test",
            "timezone": "UTC",
            "player_names": "",
            "horizon_weeks": "2",
        },
    )
    assert r.status_code == 200
    m = re.search(r"/c/([0-9a-f]+)/admin/([\w\-]+)", r.text)
    assert m
    public_id, secret = m.groups()
    ok = client.get(f"/c/{public_id}/admin/{secret}/calendar-consensus.ics")
    assert ok.status_code == 200
    assert ok.headers["content-type"].startswith("text/calendar")
    assert b"VCALENDAR" in ok.content
