"""Admin settings: prefer full party checkbox."""

from __future__ import annotations

import re

from sqlmodel import Session, select

from app.models import Campaign


def _new_campaign(client):
    r = client.post(
        "/",
        data={
            "name": "Prefer full party test",
            "timezone": "UTC",
            "player_names": "",
            "horizon_weeks": "4",
        },
    )
    assert r.status_code == 200
    m = re.search(r"/c/([0-9a-f]+)/admin/([\w\-]+)", r.text)
    assert m
    return m.group(1), m.group(2)


def test_new_campaign_defaults_prefer_full_party_on(client, engine):
    public_id, _secret = _new_campaign(client)
    with Session(engine) as s:
        c = s.exec(select(Campaign).where(Campaign.public_id == public_id)).one()
    assert c.prefer_full_party is True


def test_settings_form_round_trips_prefer_full_party(client, engine):
    public_id, secret = _new_campaign(client)
    with Session(engine) as s:
        c = s.exec(select(Campaign).where(Campaign.public_id == public_id)).one()

    r = client.post(
        f"/c/{public_id}/admin/{secret}/settings",
        data={
            "name": c.name,
            "timezone": c.timezone,
            "horizon_weeks": str(c.horizon_weeks),
            "consensus_policy": c.consensus_policy.value,
            "public_recurrence_mode": c.public_recurrence_mode.value,
        },
    )
    assert r.status_code in (200, 303)
    with Session(engine) as s:
        c = s.exec(select(Campaign).where(Campaign.public_id == public_id)).one()
    assert c.prefer_full_party is False

    r = client.post(
        f"/c/{public_id}/admin/{secret}/settings",
        data={
            "name": c.name,
            "timezone": c.timezone,
            "horizon_weeks": str(c.horizon_weeks),
            "consensus_policy": c.consensus_policy.value,
            "public_recurrence_mode": c.public_recurrence_mode.value,
            "prefer_full_party": "1",
        },
    )
    assert r.status_code in (200, 303)
    with Session(engine) as s:
        c = s.exec(select(Campaign).where(Campaign.public_id == public_id)).one()
    assert c.prefer_full_party is True
