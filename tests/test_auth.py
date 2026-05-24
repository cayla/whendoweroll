"""Capability-URL auth boundaries: bad secrets are 404, players can't
mutate other players' availability.
"""

from __future__ import annotations

from sqlmodel import select

from app.models import Availability
from tests.helpers import create_campaign_via_form


def test_bogus_admin_secret_returns_404(client):
    created = create_campaign_via_form(client, name="Test", player_names="Alice\nBob\nCayla", horizon_weeks=4)
    public_id = created.public_id
    assert client.get(f"/c/{public_id}/admin/not-the-secret").status_code == 404


def test_bogus_player_token_returns_404(client):
    created = create_campaign_via_form(client, name="Test", player_names="Alice\nBob\nCayla", horizon_weeks=4)
    public_id = created.public_id
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
    created = create_campaign_via_form(client, name="Test", player_names="Alice\nBob\nCayla", horizon_weeks=4)
    public_id, secret, tokens = created.public_id, created.admin_secret, created.player_tokens
    assert len(tokens) == 3
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
    a = create_campaign_via_form(client, name="A", player_names="Alice")
    b = create_campaign_via_form(client, name="B", player_names="Bob")
    assert client.get(f"/c/{b.public_id}/p/{a.player_tokens[0]}").status_code == 404


def test_admin_recurring_slot_shows_yes_no_vote_column(client):
    created = create_campaign_via_form(client, name="Test", player_names="Alice\nBob\nCayla", horizon_weeks=4)
    public_id, secret, tokens = created.public_id, created.admin_secret, created.player_tokens
    assert len(tokens) == 3
    client.post(
        f"/c/{public_id}/admin/{secret}/slots",
        data={"kind": "recurring", "weekday": "4", "start_local": "18:00", "duration_hours": "3"},
    )
    client.post(f"/c/{public_id}/p/{tokens[0]}/availability/1", data={"status": "yes"})
    client.post(f"/c/{public_id}/p/{tokens[1]}/availability/1", data={"status": "no"})
    admin = client.get(f"/c/{public_id}/admin/{secret}")
    assert admin.status_code == 200
    assert "Yes / no" in admin.text
    assert "1 / 1" in admin.text
