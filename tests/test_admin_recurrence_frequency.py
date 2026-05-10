"""Admin: campaign-level meeting tempo (public page + ICS only)."""

from __future__ import annotations

import re

from sqlmodel import Session, select

from app.models import Campaign, PublicRecurrenceMode, Slot, SlotKind


def _new_campaign(client):
    r = client.post(
        "/",
        data={
            "name": "Public mode test",
            "timezone": "UTC",
            "player_names": "",
            "horizon_weeks": "4",
        },
    )
    assert r.status_code == 200
    m = re.search(r"/c/([0-9a-f]+)/admin/([\w\-]+)", r.text)
    assert m
    return m.group(1), m.group(2)


def test_admin_add_recurring_slot_does_not_change_campaign_tempo(client, engine):
    public_id, secret = _new_campaign(client)
    with Session(engine) as s:
        c = s.exec(select(Campaign).where(Campaign.public_id == public_id)).one()
        c.public_recurrence_mode = PublicRecurrenceMode.two_weeks
        s.add(c)
        s.commit()

    r = client.post(
        f"/c/{public_id}/admin/{secret}/slots",
        data={
            "kind": "recurring",
            "weekday": "4",
            "start_local": "19:00",
            "duration_hours": "3",
            "label": "Friday",
        },
    )
    assert r.status_code in (200, 303)
    with Session(engine) as s:
        slot = s.exec(select(Slot).where(Slot.kind == SlotKind.recurring)).one()
        c = s.exec(select(Campaign).where(Campaign.public_id == public_id)).one()
    assert slot.weekday == 4
    assert c.public_recurrence_mode == PublicRecurrenceMode.two_weeks


def test_admin_update_campaign_public_recurrence_mode(client, engine):
    public_id, secret = _new_campaign(client)
    client.post(
        f"/c/{public_id}/admin/{secret}/slots",
        data={
            "kind": "recurring",
            "weekday": "0",
            "start_local": "12:00",
            "duration_hours": "2",
        },
    )
    with Session(engine) as s:
        c = s.exec(select(Campaign).where(Campaign.public_id == public_id)).one()
    assert c.public_recurrence_mode == PublicRecurrenceMode.weekly

    r = client.post(
        f"/c/{public_id}/admin/{secret}/settings",
        data={
            "name": c.name,
            "timezone": c.timezone,
            "horizon_weeks": str(c.horizon_weeks),
            "consensus_policy": c.consensus_policy.value,
            "public_recurrence_mode": "once_per_month",
        },
    )
    assert r.status_code in (200, 303)
    with Session(engine) as s:
        c = s.exec(select(Campaign).where(Campaign.public_id == public_id)).one()
    assert c.public_recurrence_mode == PublicRecurrenceMode.once_per_month
