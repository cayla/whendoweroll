"""Admin sets mandatory attendees via POST /mandatory-attendees."""

from __future__ import annotations

from sqlmodel import Session, select

from app.models import Player
from tests.helpers import create_campaign_via_form


def test_set_single_mandatory_clears_others(client, engine):
    created = create_campaign_via_form(
        client, name="Mandatory Test", timezone="UTC", player_names=["Alice", "Bob"], horizon_weeks=2
    )
    public_id, secret = created.public_id, created.admin_secret
    with Session(engine) as s:
        first = s.exec(select(Player)).first()
        assert first is not None
        cid = first.campaign_id
        players = s.exec(select(Player).where(Player.campaign_id == cid)).all()
        assert len(players) == 2
        bob_id = next(p.id for p in players if p.display_name == "Bob")

    r = client.post(
        f"/c/{public_id}/admin/{secret}/mandatory-attendees",
        data={"mandatory_player_ids": [str(bob_id)]},
    )
    assert r.status_code in (200, 303)

    with Session(engine) as s:
        players = s.exec(select(Player).where(Player.campaign_id == cid)).all()
    by_name = {p.display_name: p.is_mandatory for p in players}
    assert by_name["Alice"] is False
    assert by_name["Bob"] is True


def test_set_multiple_mandatory_attendees(client, engine):
    created = create_campaign_via_form(
        client, name="Mandatory Test", timezone="UTC", player_names=["Alice", "Bob"], horizon_weeks=2
    )
    public_id, secret = created.public_id, created.admin_secret
    with Session(engine) as s:
        first = s.exec(select(Player)).first()
        assert first is not None
        cid = first.campaign_id
        players = s.exec(select(Player).where(Player.campaign_id == cid)).all()
        ids = [p.id for p in players]

    r = client.post(
        f"/c/{public_id}/admin/{secret}/mandatory-attendees",
        data={"mandatory_player_ids": [str(i) for i in ids]},
    )
    assert r.status_code in (200, 303)

    with Session(engine) as s:
        players = s.exec(select(Player).where(Player.campaign_id == cid)).all()
    assert all(p.is_mandatory for p in players)


def test_clear_mandatory_attendees_with_empty_form(client, engine):
    created = create_campaign_via_form(
        client, name="Mandatory Test", timezone="UTC", player_names=["Alice", "Bob"], horizon_weeks=2
    )
    public_id, secret = created.public_id, created.admin_secret
    with Session(engine) as s:
        first = s.exec(select(Player)).first()
        assert first is not None
        cid = first.campaign_id
        players = s.exec(select(Player).where(Player.campaign_id == cid)).all()
        bob_id = next(p.id for p in players if p.display_name == "Bob")

    client.post(
        f"/c/{public_id}/admin/{secret}/mandatory-attendees",
        data={"mandatory_player_ids": [str(bob_id)]},
    )
    r = client.post(
        f"/c/{public_id}/admin/{secret}/mandatory-attendees",
        data={},
    )
    assert r.status_code in (200, 303)
    with Session(engine) as s:
        players = s.exec(select(Player).where(Player.campaign_id == cid)).all()
    assert not any(p.is_mandatory for p in players)


def test_invalid_player_id_rejected(client):
    created = create_campaign_via_form(
        client, name="Mandatory Test", timezone="UTC", player_names=["Alice", "Bob"], horizon_weeks=2
    )
    r = client.post(
        f"/c/{created.public_id}/admin/{created.admin_secret}/mandatory-attendees",
        data={"mandatory_player_ids": ["999999"]},
    )
    assert r.status_code == 400
