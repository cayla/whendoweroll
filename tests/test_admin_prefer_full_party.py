"""Admin settings: prefer full party checkbox."""

from __future__ import annotations

from sqlmodel import Session, select

from app.models import Campaign
from tests.helpers import create_campaign_via_form


def test_new_campaign_defaults_prefer_full_party_on(client, engine):
    created = create_campaign_via_form(
        client, name="Prefer full party test", timezone="UTC", player_names="", horizon_weeks=4
    )
    public_id = created.public_id
    with Session(engine) as s:
        c = s.exec(select(Campaign).where(Campaign.public_id == public_id)).one()
    assert c.prefer_full_party is True


def test_settings_form_round_trips_prefer_full_party(client, engine):
    created = create_campaign_via_form(
        client, name="Prefer full party test", timezone="UTC", player_names="", horizon_weeks=4
    )
    public_id, secret = created.public_id, created.admin_secret
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
