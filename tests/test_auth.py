"""Capability-URL auth boundaries: bad secrets are 404, players can't
mutate other players' availability.
"""

from __future__ import annotations

import re

from sqlmodel import select

from app.models import Availability


def _create_campaign(client) -> tuple[str, str, list[str]]:
    r = client.post(
        "/",
        data={
            "name": "Test",
            "timezone": "America/New_York",
            "player_names": "Alice\nBob\nCayla",
            "horizon_weeks": "4",
        },
    )
    assert r.status_code == 200
    public_id, secret = re.search(r"/c/([0-9a-f]+)/admin/([\w\-]+)", r.text).groups()
    tokens = re.findall(r"/c/" + public_id + r"/p/([\w\-]+)", r.text)
    assert len(tokens) == 3
    return public_id, secret, tokens


def test_bogus_admin_secret_returns_404(client):
    public_id, _, _ = _create_campaign(client)
    assert client.get(f"/c/{public_id}/admin/not-the-secret").status_code == 404


def test_bogus_player_token_returns_404(client):
    public_id, _, _ = _create_campaign(client)
    assert client.get(f"/c/{public_id}/p/not-the-token").status_code == 404


def test_unknown_campaign_returns_404(client):
    assert client.get("/c/deadbeef/admin/anything").status_code == 404
    assert client.get("/c/deadbeef/p/anything").status_code == 404
    assert client.get("/c/deadbeef").status_code == 404


def test_player_token_cannot_write_to_someone_elses_slot(client, engine):
    """A player's URL is scoped to *their own* row server-side; passing a
    different player's id doesn't matter because the route resolves player
    from the token, not from a body parameter.
    """
    public_id, secret, tokens = _create_campaign(client)
    r = client.post(
        f"/c/{public_id}/admin/{secret}/slots",
        data={"kind": "recurring", "weekday": "4", "start_local": "18:00", "duration_hours": "3"},
    )
    assert r.status_code in (200, 303)

    r = client.post(
        f"/c/{public_id}/p/{tokens[0]}/availability/1",
        data={"status": "yes"},
    )
    assert r.status_code == 200

    from sqlmodel import Session

    with Session(engine) as s:
        rows = s.exec(select(Availability)).all()
    assert len(rows) == 1
    assert rows[0].player_id == 1  # only the token-owner's row was written


def test_player_route_404_when_token_belongs_to_different_campaign(client):
    _, _, a_tokens = _create_campaign(client)
    b_public, _, _ = _create_campaign(client)
    assert client.get(f"/c/{b_public}/p/{a_tokens[0]}").status_code == 404
