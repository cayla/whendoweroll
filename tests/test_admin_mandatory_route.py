"""Admin sets mandatory attendees via POST /mandatory-attendees."""

from __future__ import annotations

import re

from sqlmodel import Session, select

from app.models import Player


def _create_two_player_campaign(client) -> tuple[str, str, int]:
    r = client.post(
        "/",
        data={
            "name": "Mandatory Test",
            "timezone": "UTC",
            "player_names": "Alice\nBob",
            "horizon_weeks": "2",
        },
    )
    assert r.status_code == 200
    m = re.search(r"/c/([0-9a-f]+)/admin/([\w\-]+)", r.text)
    assert m
    return m.group(1), m.group(2), 0  # cid resolved by caller via DB if needed


def test_set_single_mandatory_clears_others(client, engine):
    public_id, secret, _ = _create_two_player_campaign(client)
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
    public_id, secret, _ = _create_two_player_campaign(client)
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
    public_id, secret, _ = _create_two_player_campaign(client)
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
    public_id, secret, _ = _create_two_player_campaign(client)
    r = client.post(
        f"/c/{public_id}/admin/{secret}/mandatory-attendees",
        data={"mandatory_player_ids": ["999999"]},
    )
    assert r.status_code == 400
