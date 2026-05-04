"""Admin sets campaign DM via POST /dm."""

from __future__ import annotations

import re

from sqlmodel import Session, select

from app.models import Player


def test_set_dm_clears_others(client, engine):
    r = client.post(
        "/",
        data={
            "name": "DM Test",
            "timezone": "UTC",
            "player_names": "Alice\nBob",
            "horizon_weeks": "2",
        },
    )
    assert r.status_code == 200
    m = re.search(r"/c/([0-9a-f]+)/admin/([\w\-]+)", r.text)
    assert m
    public_id, secret = m.group(1), m.group(2)

    with Session(engine) as s:
        first = s.exec(select(Player)).first()
        assert first is not None
        cid = first.campaign_id
        players = s.exec(select(Player).where(Player.campaign_id == cid)).all()
        assert len(players) == 2
        bob_id = next(p.id for p in players if p.display_name == "Bob")

    r2 = client.post(
        f"/c/{public_id}/admin/{secret}/dm",
        data={"dm_player_id": str(bob_id)},
    )
    assert r2.status_code in (200, 303)

    with Session(engine) as s:
        players = s.exec(select(Player).where(Player.campaign_id == cid)).all()
    by_name = {p.display_name: p.is_dm for p in players}
    assert by_name["Alice"] is False
    assert by_name["Bob"] is True
