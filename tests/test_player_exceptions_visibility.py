"""Recurring exception rows only appear when the player said yes to that slot."""

from __future__ import annotations

import re


def test_no_per_date_rows_until_standing_yes_then_cleared_on_no(client):
    r = client.post(
        "/",
        data={
            "name": "Vis",
            "timezone": "America/New_York",
            "player_names": "Rogue",
            "horizon_weeks": "4",
        },
    )
    assert r.status_code == 200
    m = re.search(r"/c/([0-9a-f]+)/admin/([\w\-]+)", r.text)
    assert m
    public_id, secret = m.group(1), m.group(2)
    tok = re.search(r"/c/" + public_id + r"/p/([\w\-]+)", r.text)
    assert tok
    player_token = tok.group(1)

    add = client.post(
        f"/c/{public_id}/admin/{secret}/slots",
        data={
            "kind": "recurring",
            "weekday": "4",
            "start_local": "18:00",
            "duration_hours": "3",
            "label": "Friday",
        },
    )
    assert add.status_code in (200, 303)

    p0 = client.get(f"/c/{public_id}/p/{player_token}")
    assert p0.status_code == 200
    assert b"Can't make it" not in p0.content

    client.post(f"/c/{public_id}/p/{player_token}/availability/1", data={"status": "yes"})
    p1 = client.get(f"/c/{public_id}/p/{player_token}")
    assert p1.status_code == 200
    assert b"Can't make it" in p1.content

    client.post(f"/c/{public_id}/p/{player_token}/availability/1", data={"status": "no"})
    p2 = client.get(f"/c/{public_id}/p/{player_token}")
    assert p2.status_code == 200
    assert b"Can't make it" not in p2.content


def test_availability_post_htmx_refreshes_exceptions_contract(client):
    """Row swap + HX-Trigger + GET fragment (Safari/Firefox-friendly; no multi-root OOB)."""
    r = client.post(
        "/",
        data={
            "name": "Vis",
            "timezone": "America/New_York",
            "player_names": "Rogue",
            "horizon_weeks": "4",
        },
    )
    assert r.status_code == 200
    m = re.search(r"/c/([0-9a-f]+)/admin/([\w\-]+)", r.text)
    assert m
    public_id, secret = m.group(1), m.group(2)
    tok = re.search(r"/c/" + public_id + r"/p/([\w\-]+)", r.text)
    assert tok
    player_token = tok.group(1)
    client.post(
        f"/c/{public_id}/admin/{secret}/slots",
        data={
            "kind": "recurring",
            "weekday": "4",
            "start_local": "18:00",
            "duration_hours": "3",
            "label": "Friday",
        },
    )
    post = client.post(
        f"/c/{public_id}/p/{player_token}/availability/1",
        data={"status": "yes"},
        headers={"HX-Request": "true"},
    )
    assert post.status_code == 200
    assert post.headers.get("HX-Trigger") == "refreshExceptions"
    assert b'id="slot-row-1"' in post.content
    frag = client.get(f"/c/{public_id}/p/{player_token}/_recurring-exceptions")
    assert frag.status_code == 200
    assert b"Can't make it" in frag.content
